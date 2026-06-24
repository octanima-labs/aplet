from pathlib import Path
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
import re
import shlex
import shutil
import subprocess
import yaml

from .runners import SCRIPT_ERROR, SCRIPT_INTERRUPTED, SCRIPT_OK, Script, Probe
from . import utils as ut


logger = ut.get_logger(__name__)


METADATA_TOKEN_PATTERN = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
INVENTORY_HEADERS = {'### APLET INVENTORY ###', '### APPLET INVENTORY ###'}


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _get_managers():
    from .managers import MANAGERS
    return MANAGERS


def _get_implemented():
    from .managers import IMPLEMENTED
    return IMPLEMENTED


def _format_exception_output(exc: Exception) -> str:
    details: list[str] = []
    for label, attr in (('stderr', 'stderr'), ('stdout', 'output')):
        value = getattr(exc, attr, None)
        if not value:
            continue
        if isinstance(value, bytes):
            text = value.decode(errors='replace')
        else:
            text = str(value)
        text = text.strip()
        if text:
            details.append(f"{label}:\n{text}")
    return '\n'.join(details)


def _manager_failure_message(operation: str, app_name: str, manager_name: str, exc: Exception) -> str:
    message = f"Package-manager {operation} failed for '{app_name}' via '{manager_name}': {exc}"
    details = _format_exception_output(exc)
    if details:
        message = f"{message}\n{details}"
    return message


class App:
    """A single application entry from an Aplet inventory.

    Args:
        name: Inventory name used to reference the application.
        candidate: Default package or executable candidate. Defaults to
            ``name`` when omitted.
        preference: Per-app method preference order prepended to the global
            preference order.
        category: Hierarchical category path for browsing inventory entries.
        tags: Flat labels for filtering and discovery.
        installed: Optional explicit installed state. ``None`` means unknown.
        dependencies: Other inventory app names that should be installed first.
    """

    def __init__(
        self,
        name: str,
        candidate: str | None = None,
        preference: list[str] | None = None,
        category: list[str] | None = None,
        tags: list[str] | None = None,
        installed: bool | None = None,
        dependencies: list[str] | None = None,
    ):
        if installed is not None and not isinstance(installed, bool):
            raise TypeError("[-] App 'installed' must be true, false, or null")
        if dependencies is not None and (not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies)):
            raise TypeError("[-] App 'dependencies' must be a list of strings")
        normalized_dependencies = _dedupe_preserve_order(list(dependencies or []))
        if name in normalized_dependencies:
            raise ValueError(f"[-] App '{name}' cannot depend on itself")
        self.name: str = name
        self.candidate: str = candidate if candidate else name
        self.preference: list[str] = list(preference or [])
        self.category: list[str] = list(category or [])
        self.tags: list[str] = list(tags or [])
        self.installed: bool | None = installed
        self.dependencies: list[str] = normalized_dependencies
        self._inventory = None
        self._managers: dict[str, dict[str, str]] = dict()
        self._installers: dict[str, Script] = dict()
        self._uninstallers: dict[str, Script] = dict()
        self._post_install: dict[str, Script] = dict()
        self._probes: dict[str, Probe | None] = dict()

    def __str__(self) -> str:
        return self.name

    def inventory_name_label(self, installed: bool = False) -> str:
        return ut.Display.bold_green(self.name) if installed else ut.Display.bold(self.name)

    def inventory_label(
        self,
        methods: list[str] | None = None,
        *,
        installed: bool = False,
        custom_methods: set[str] | None = None,
    ) -> str:
        if methods is None:
            methods = [*self.managers.keys(), *self.installers.keys()]
        if custom_methods is None:
            custom_methods = set(self.installers)
        app_name = self.inventory_name_label(installed=installed)
        if not methods:
            unavailable_label = 'uninstall unavailable' if installed else 'installation unavailable'
            return f"{app_name} ({ut.Display.color_dim(unavailable_label)})"
        return f"{app_name} ({self.rendered_methods_label(methods, custom_methods=custom_methods)})"

    def inventory_all_methods_label(
        self,
        methods: list[str],
        available_methods: set[str],
        *,
        installed: bool = False,
        custom_methods: set[str] | None = None,
    ) -> str:
        if custom_methods is None:
            custom_methods = set(self.installers)
        app_name = self.inventory_name_label(installed=installed)
        if not methods:
            unavailable_label = 'uninstall unavailable' if installed else 'installation unavailable'
            return f"{app_name} ({ut.Display.color_dim(unavailable_label)})"
        return f"{app_name} ({self.rendered_methods_availability_label(methods, available_methods, custom_methods=custom_methods)})"

    def rendered_methods_label(self, methods: list[str], *, custom_methods: set[str] | None = None) -> str:
        if custom_methods is None:
            custom_methods = set(self.installers)
        rendered_methods: list[str] = []
        for name in methods:
            if name in custom_methods:
                rendered_methods.append(ut.Display.color_special(f"x:{name}"))
            else:
                rendered_methods.append(ut.Display.color_value(name))
        return ', '.join(rendered_methods)

    def rendered_methods_availability_label(
        self,
        methods: list[str],
        available_methods: set[str],
        *,
        custom_methods: set[str] | None = None,
    ) -> str:
        if custom_methods is None:
            custom_methods = set(self.installers)
        rendered_methods: list[str] = []
        for name in methods:
            method_label = f"x:{name}" if name in custom_methods else name
            if name not in available_methods:
                rendered_methods.append(ut.Display.color_red(method_label))
            elif name in custom_methods:
                rendered_methods.append(ut.Display.color_special(method_label))
            else:
                rendered_methods.append(ut.Display.color_value(method_label))
        return ', '.join(rendered_methods)

    def _inventory_detail_value(self, value: str, *, dim: bool = False) -> str:
        return ut.Display.color_dim(value) if dim else ut.Display.color_value(value)

    def _inventory_detail_line(self, key: str, value: str, *, dim: bool = False) -> str:
        return f"  - {ut.Display.color_key(key)}: {self._inventory_detail_value(value, dim=dim)}"

    def inventory_details(self, *, installed: bool = False) -> str:
        app_name = self.inventory_name_label(installed=installed)
        managers = ', '.join(self.managers.keys()) if self.managers else 'None'
        installers = ', '.join(self.installers.keys()) if self.installers else 'None'
        uninstallers = ', '.join(self.uninstallers.keys()) if self.uninstallers else 'None'
        post_install = ', '.join(self.post_install.keys()) if self.post_install else 'None'
        probes = ', '.join(self.probes.keys()) if self.probes else 'None'
        installed_value = 'unknown' if self.installed is None else str(self.installed).lower()
        dependencies = ', '.join(self.dependencies) if self.dependencies else 'None'
        preference = ', '.join(self.preference) if self.preference else 'auto'
        category = ' > '.join(self.category) if self.category else 'None'
        tags = ', '.join(self.tags) if self.tags else 'None'
        return (
            f"{app_name}\n"
            f"{self._inventory_detail_line('managers', managers, dim=not self.managers)}\n"
            f"{self._inventory_detail_line('installers', installers, dim=not self.installers)}\n"
            f"{self._inventory_detail_line('uninstallers', uninstallers, dim=not self.uninstallers)}\n"
            f"{self._inventory_detail_line('post_install', post_install, dim=not self.post_install)}\n"
            f"{self._inventory_detail_line('probes', probes, dim=not self.probes)}\n"
            f"{self._inventory_detail_line('installed', installed_value, dim=self.installed is None)}\n"
            f"{self._inventory_detail_line('dependencies', dependencies, dim=not self.dependencies)}\n"
            f"{self._inventory_detail_line('preference', preference, dim=not self.preference)}\n"
            f"{self._inventory_detail_line('category', category, dim=not self.category)}\n"
            f"{self._inventory_detail_line('tags', tags, dim=not self.tags)}"
        )

    def inventory_tag_label(self, *, installed: bool = False) -> str:
        app_name = self.inventory_name_label(installed=installed)
        tags = ', '.join(ut.Display.color_key(tag) for tag in self.tags) if self.tags else ut.Display.color_dim('no-tags')
        return f"{app_name} [{tags}]"

    def is_custom_installer_only(self) -> bool:
        return bool(self.installers) and not bool(self.managers)

    def _set_inventory(self, inventory) -> None:
        self._inventory = inventory

    def _validate_dependency_name(self, app_name: str) -> None:
        if not isinstance(app_name, str):
            raise TypeError("[-] Dependency name must be a string")
        if app_name == self.name:
            raise ValueError(f"[-] App '{self.name}' cannot depend on itself")
        if self._inventory is None:
            raise RuntimeError(f"[-] Cannot validate dependency '{app_name}' without an inventory")
        if self._inventory.get_app(app_name) is None:
            raise ValueError(f"[-] App '{self.name}' dependency '{app_name}' is not declared")

    def add_dependency(self, app_name: str) -> None:
        self._validate_dependency_name(app_name)
        if app_name not in self.dependencies:
            self.dependencies.append(app_name)

    def rm_dependency(self, app_name: str) -> None:
        try:
            self.dependencies.remove(app_name)
        except ValueError:
            pass
    
    @property
    def managers(self) -> dict[str, dict[str, str]]:
        return self._managers

    @property
    def installers(self) -> dict[str, Script]:
        return self._installers

    @property
    def uninstallers(self) -> dict[str, Script]:
        return self._uninstallers

    @property
    def post_install(self) -> dict[str, Script]:
        return self._post_install

    @property
    def probes(self) -> dict[str, Probe | None]:
        return self._probes
    
    def add_manager(self, name: str, force: bool = False, **manager_data):
        """
        :param name: name of the manger. Must be one of: apt, pacman, yay, yum, dnf, zypper, brew, choco, scoop, flatpak, snap, npm, pip
        :param manager_data: manager-specific configuration
        :param force: overwrite existing manager configuration
        """
        if name in self.managers and not force:
            logger.error(f"Manager '{name}' already defined")
            return
        self._managers[name] = {key: value for key, value in manager_data.items() if value is not None}
    
    def remove_manager(self, name: str) -> None:
        try:
            del self._managers[name]
        except KeyError:
            pass

    def add_installer(self, installer: Script, force: bool = False) -> None:
        if installer.name in self.installers and not force:
            logger.error(f"Installer '{installer.name}' already defined")
            return
        self._installers[installer.name] = installer

    def remove_installer(self, name: str) -> None:
        try:
            del self._installers[name]
        except KeyError:
            pass

    def add_uninstaller(self, uninstaller: Script, force: bool = False) -> None:
        if uninstaller.name in self.uninstallers and not force:
            logger.error(f"Uninstaller '{uninstaller.name}' already defined")
            return
        self._uninstallers[uninstaller.name] = uninstaller

    def remove_uninstaller(self, name: str) -> None:
        try:
            del self._uninstallers[name]
        except KeyError:
            pass

    def add_post_install(self, installer: Script, force: bool = False) -> None:
        if installer.name in self.post_install and not force:
            logger.error(f"Post-install '{installer.name}' already defined")
            return
        self._post_install[installer.name] = installer

    def remove_post_install(self, name: str) -> None:
        try:
            del self._post_install[name]
        except KeyError:
            pass

    def add_probe(self, name: str, probe: Probe | None = None, force: bool = False) -> None:
        if name in self.probes and not force:
            logger.error(f"Probe '{name}' already defined")
            return
        self._probes[name] = probe

    def remove_probe(self, name: str) -> None:
        try:
            del self._probes[name]
        except KeyError:
            pass


class AppInventory:
    """Load, query, render, install, and uninstall inventory entries.

    ``AppInventory`` is the main library object behind the CLI. It owns a list
    of :class:`App` instances, validates inventory data, resolves available
    install methods for the current host, and dispatches install or uninstall
    operations through backend adapters.
    """

    TARGET_VERSION_PATTERN = re.compile(r'^(?P<name>.+?)(?P<specifier>(==|>=|<=|~=|!=|<|>)[^\s]+)$')
    
    def __init__(self) -> None:
        self._apps: list[App] = list()
    
    @property
    def apps(self) -> list[App]:
        return self._apps

    def load(self, path: str | Path | None = None):
        """
        :param path: if equals is None loads default inventory. Else load from path
        """
        logger.debug("Loading inventory...")
        if path is None: # Use default inventory
            path = ut.Config.data['DEFAULT_INVENTORY_PATH']
        _data = ut.Yaml.load(path) or {}
        res: list[App] = list()
        for _app_name, _app_data in _data.get('apps', {}).items():
            res.append(self.parse_app_item(_app_name, _app_data))
        logger.success(f"{len(res)} app(s) loaded")
        self._apps = list(res)
        for app in self._apps:
            app._set_inventory(self)
        self._validate_dependencies()
        return self

    def _normalize_metadata_token(self, token: str, *, field: str, subject: str = 'Inventory entry field') -> str:
        if not isinstance(token, str):
            raise TypeError(f"[-] {subject} '{field}' must contain only strings")
        normalized = token.strip()
        if not normalized or not METADATA_TOKEN_PATTERN.fullmatch(normalized):
            raise ValueError(f"[-] {subject} '{field}' has invalid token '{token}'")
        return normalized

    def _normalize_category(self, value: list[str] | None, *, subject: str = 'Inventory entry field') -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError(f"[-] {subject} 'category' must be a list of strings")
        return [self._normalize_metadata_token(token, field='category', subject=subject) for token in value]

    def _normalize_tags(self, value: list[str] | None, *, subject: str = 'Inventory entry field') -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError(f"[-] {subject} 'tags' must be a list of strings")
        return _dedupe_preserve_order([
            self._normalize_metadata_token(token, field='tags', subject=subject) for token in value
        ])

    def _normalize_dependencies(self, value: list[str] | None, *, subject: str = 'Inventory entry field') -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise TypeError(f"[-] {subject} 'dependencies' must be a list of strings")
        return _dedupe_preserve_order(list(value))

    def _validate_app_dependencies(self, app: App) -> None:
        for dependency in app.dependencies:
            if dependency == app.name:
                raise ValueError(f"[-] Inventory entry '{app.name}' cannot depend on itself")
            if self.get_app(dependency) is None:
                raise ValueError(f"[-] Inventory entry '{app.name}' dependency '{dependency}' is not declared")

    def _validate_dependencies(self) -> None:
        for app in self._apps:
            self._validate_app_dependencies(app)

    def _parse_category_filter(self, value: str) -> list[str]:
        if not isinstance(value, str):
            raise TypeError("[-] Search category filters must be strings")
        raw_segments = [segment.strip() for segment in value.split('>')]
        if any(segment == '' for segment in raw_segments):
            raise ValueError(f"[-] Search category filter '{value}' is invalid")
        return [
            self._normalize_metadata_token(segment, field='category', subject='Search category filter')
            for segment in raw_segments
        ]

    def _category_matches(self, app: App, filter_path: list[str]) -> bool:
        return len(filter_path) <= len(app.category) and app.category[: len(filter_path)] == filter_path

    def _name_matches(self, app: App, term: str) -> bool:
        lowered = term.lower()
        return lowered in app.name.lower() or lowered in app.candidate.lower()

    def parse_app_item(self, name: str, data: dict) -> App:
        if not isinstance(data, dict):
            raise TypeError(f"[-] Inventory entry '{name}' must be a mapping")
        managers_data = data.get('managers') or {}
        installers_data = data.get('installers') or {}
        uninstallers_data = data.get('uninstallers') or {}
        post_install_data = data.get('post_install') or {}
        probes_data = data.get('probes') or {}
        preference_data = data.get('preference') or []
        category_data = self._normalize_category(data.get('category'))
        tags_data = self._normalize_tags(data.get('tags'))
        dependencies_data = self._normalize_dependencies(data.get('dependencies'))
        installed_data = data.get('installed')
        if name in dependencies_data:
            raise ValueError(f"[-] Inventory entry '{name}' cannot depend on itself")
        if not isinstance(managers_data, dict):
            raise TypeError(f"[-] Inventory entry '{name}' field 'managers' must be a mapping")
        if not isinstance(installers_data, dict):
            raise TypeError(f"[-] Inventory entry '{name}' field 'installers' must be a mapping")
        if not isinstance(uninstallers_data, dict):
            raise TypeError(f"[-] Inventory entry '{name}' field 'uninstallers' must be a mapping")
        if not isinstance(post_install_data, dict):
            raise TypeError(f"[-] Inventory entry '{name}' field 'post_install' must be a mapping")
        if not isinstance(probes_data, dict):
            raise TypeError(f"[-] Inventory entry '{name}' field 'probes' must be a mapping")
        if not isinstance(preference_data, list) or not all(isinstance(item, str) for item in preference_data):
            raise TypeError(f"[-] Inventory entry '{name}' field 'preference' must be a list of strings")
        if installed_data is not None and not isinstance(installed_data, bool):
            raise TypeError(f"[-] Inventory entry '{name}' field 'installed' must be true, false, or null")
        declared_manager_names = list(managers_data.keys())
        declared_installer_names = list(installers_data.keys())
        declared_uninstaller_names = list(uninstallers_data.keys())
        valid_preference_tokens = set(declared_manager_names) | set(declared_installer_names) | set(declared_uninstaller_names) | {'custom_installers'}
        invalid_preference = [item for item in preference_data if item not in valid_preference_tokens]
        if invalid_preference:
            raise ValueError(f"[-] Inventory entry '{name}' has invalid preference entries: {', '.join(invalid_preference)}")
        app = App(
            name=name,
            candidate=data.get('candidate'),
            preference=list(preference_data),
            category=category_data,
            tags=tags_data,
            installed=installed_data,
            dependencies=dependencies_data,
        )
        implemented = _get_implemented()
        for manager_name, manager_data in managers_data.items():
            manager_data = manager_data or {}
            if not isinstance(manager_data, dict):
                raise TypeError(f"[-] Inventory entry '{name}' manager '{manager_name}' must be a mapping")
            app.add_manager(manager_name, **manager_data)
        for installer_name, installer_data in installers_data.items():
            if installer_data is None or not isinstance(installer_data, list):
                raise TypeError(f"[-] Inventory entry '{name}' installer '{installer_name}' expects a list of actions")
            ut.Platform.installer_tokens(installer_name)
            app.add_installer(
                Script.from_data(
                    installer_name,
                    installer_data,
                    allowed_manager_actions=implemented,
                )
            )
        for uninstaller_name, uninstaller_data in uninstallers_data.items():
            if uninstaller_data is None or not isinstance(uninstaller_data, list):
                raise TypeError(f"[-] Inventory entry '{name}' uninstaller '{uninstaller_name}' expects a list of actions")
            ut.Platform.installer_tokens(uninstaller_name)
            app.add_uninstaller(
                Script.from_data(
                    uninstaller_name,
                    uninstaller_data,
                    allowed_manager_actions=implemented,
                )
            )
        for post_install_name, installer_data in post_install_data.items():
            if installer_data is None or not isinstance(installer_data, list):
                raise TypeError(f"[-] Inventory entry '{name}' post-install '{post_install_name}' expects a list of actions")
            ut.Platform.installer_tokens(post_install_name)
            app.add_post_install(
                Script.from_data(
                    post_install_name,
                    installer_data,
                    allowed_manager_actions=implemented,
                )
            )
        for probe_name, probe_data in probes_data.items():
            if probe_name in implemented:
                if probe_name not in managers_data:
                    raise ValueError(
                        f"[-] Inventory entry '{name}' probe manager '{probe_name}' requires a matching manager entry"
                    )
                if probe_data not in ({}, None):
                    raise TypeError(
                        f"[-] Inventory entry '{name}' probe manager '{probe_name}' must be empty"
                    )
                app.add_probe(probe_name)
                continue
            if probe_data is None or not isinstance(probe_data, list):
                raise TypeError(f"[-] Inventory entry '{name}' probe '{probe_name}' expects a list of actions")
            ut.Platform.installer_tokens(probe_name)
            app.add_probe(probe_name, Probe.from_data(probe_name, probe_data))
        return app

    def _cleanup_empty_inventory_mappings(self, text: str) -> str:
        cleaned_lines: list[str] = []
        current_section: str | None = None
        section_indent: int | None = None

        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                cleaned_lines.append(line)
                continue

            indent = len(line) - len(line.lstrip(' '))
            if section_indent is not None and indent <= section_indent:
                current_section = None
                section_indent = None

            if stripped in {'managers: {}', 'managers: null'}:
                cleaned_lines.append(f"{' ' * indent}managers:{'\n' if line.endswith('\n') else ''}")
                current_section = 'managers'
                section_indent = indent
                continue

            if stripped in {
                'installers: {}',
                'installers: null',
                'uninstallers: {}',
                'uninstallers: null',
                'post_install: {}',
                'post_install: null',
                'probes: {}',
                'probes: null',
            }:
                section = stripped.split(':', 1)[0]
                cleaned_lines.append(f"{' ' * indent}{section}:{'\n' if line.endswith('\n') else ''}")
                current_section = section
                section_indent = indent
                continue

            if stripped == 'managers:':
                current_section = 'managers'
                section_indent = indent
                cleaned_lines.append(line)
                continue

            if stripped in {'installers:', 'uninstallers:', 'post_install:', 'probes:'}:
                current_section = stripped[:-1]
                section_indent = indent
                cleaned_lines.append(line)
                continue

            if current_section in {'managers', 'probes'} and stripped.endswith(': {}'):
                key = stripped[:-4]
                cleaned_lines.append(f"{' ' * indent}{key}:{'\n' if line.endswith('\n') else ''}")
                continue

            if current_section in {'managers', 'probes'} and stripped.endswith(': null'):
                key = stripped[:-6]
                cleaned_lines.append(f"{' ' * indent}{key}:{'\n' if line.endswith('\n') else ''}")
                continue

            cleaned_lines.append(line)

        return ''.join(cleaned_lines)
    
    def save(self, path: str | Path):
        data = {'apps': {} if len(self._apps) == 0 else dict()}
        for app in self._apps:
            app_data = {
                'candidate': app.candidate,
                'managers': dict(),
            }
            if app.installed is not None:
                app_data['installed'] = app.installed
            if app.preference:
                app_data['preference'] = list(app.preference)
            if app.category:
                app_data['category'] = list(app.category)
            if app.tags:
                app_data['tags'] = list(app.tags)
            if app.dependencies:
                app_data['dependencies'] = list(app.dependencies)
            for manager_name, manager_data in app.managers.items():
                app_data['managers'][manager_name] = dict(manager_data)
            if app.installers:
                app_data['installers'] = {
                    installer_name: installer.to_data()
                    for installer_name, installer in app.installers.items()
                }
            if app.uninstallers:
                app_data['uninstallers'] = {
                    uninstaller_name: uninstaller.to_data()
                    for uninstaller_name, uninstaller in app.uninstallers.items()
                }
            if app.post_install:
                app_data['post_install'] = {
                    post_install_name: installer.to_data()
                    for post_install_name, installer in app.post_install.items()
                }
            if app.probes:
                app_data['probes'] = {
                    probe_name: dict() if probe is None else probe.to_data()
                    for probe_name, probe in app.probes.items()
                }
            data['apps'][app.name] = app_data

        dumped = yaml.safe_dump(data, sort_keys=False)
        with open(path, 'w') as file:
            file.write('### APLET INVENTORY ###\n')
            file.write(self._cleanup_empty_inventory_mappings(dumped))

    def list_apps(self, detailed: bool = False) -> list[str]:
        if detailed:
            return [app.inventory_label(self._ordered_available_methods(app)) for app in self._apps]
        return [app.name for app in self._apps]

    def list_app_details(self) -> list[str]:
        return [app.inventory_details() for app in self._apps]

    def list_app_tags(self) -> list[str]:
        return [app.inventory_tag_label() for app in self._apps]

    def _installed_state_map(self, apps: list[App]) -> dict[App, bool]:
        installed_states: dict[App, bool] = {}
        for app in apps:
            if app not in installed_states:
                installed_states[app] = self.is_app_installed(app)
        return installed_states

    def build_tag_groups(self, apps: list[App] | None = None) -> dict[str, list[App]]:
        groups: dict[str, list[App]] = {}
        untagged: list[App] = []

        source_apps = self._apps if apps is None else apps
        for app in sorted(source_apps, key=lambda item: item.name):
            if not app.tags:
                untagged.append(app)
                continue
            for tag in app.tags:
                groups.setdefault(tag, []).append(app)

        return {'tags': groups, 'untagged': untagged}

    def render_tag_groups(
        self,
        apps: list[App] | None = None,
        icon_resolver=None,
        *,
        show_installed: bool = False,
        installed_states: dict[App, bool] | None = None,
    ) -> Group:
        source_apps = self._apps if apps is None else apps
        tag_groups = self.build_tag_groups(apps=source_apps)
        if installed_states is None:
            installed_states = self._installed_state_map(source_apps) if show_installed else {}
        panels: list[Panel] = []

        def render_app_names(apps: list[App]) -> Text:
            label = Text(style='white')
            for index, app in enumerate(apps):
                if index > 0:
                    label.append(', ', style='white')
                style = 'bold green' if show_installed and installed_states.get(app, False) else 'bold white'
                label.append(app.name, style=style)
            return label

        for tag_name in sorted(tag_groups['tags']):
            apps = sorted(tag_groups['tags'][tag_name], key=lambda item: item.name)
            title = f'{tag_name} ({len(apps)})'
            if icon_resolver is not None:
                title = icon_resolver.iconify_label(icon_resolver.tag_icon(tag_name), title)
            panels.append(
                Panel(
                    render_app_names(apps),
                    title=Text(title, style='bold cyan'),
                    title_align='left',
                    border_style='cyan',
                )
            )

        if tag_groups['untagged']:
            title = f"untagged ({len(tag_groups['untagged'])})"
            if icon_resolver is not None:
                title = icon_resolver.iconify_label(icon_resolver.tag_icon('untagged'), title)
            panels.append(
                Panel(
                    render_app_names(tag_groups['untagged']),
                    title=Text(title, style='bold yellow'),
                    title_align='left',
                    border_style='yellow',
                )
            )

        if not panels:
            panels.append(
                Panel(
                    Text('<empty list>', style='dim'),
                    title=Text('tag-groups (0)', style='bold dim'),
                    title_align='left',
                    border_style='dim',
                )
            )

        return Group(*panels)

    def _new_category_tree_node(self) -> dict[str, object]:
        return {'children': {}, 'apps': [], 'total_apps': 0}

    def _populate_category_tree_counts(self, node: dict[str, object]) -> int:
        total_apps = len(node['apps'])
        for child in node['children'].values():
            total_apps += self._populate_category_tree_counts(child)
        node['total_apps'] = total_apps
        return total_apps

    def _tree_category_label(self, name: str, total_apps: int, *, uncategorized: bool = False, icon_resolver=None) -> Text:
        label = Text(style='bold yellow' if uncategorized else 'bold cyan')
        category_name = name
        if icon_resolver is not None:
            category_name = icon_resolver.iconify_label(icon_resolver.category_icon(name), name)
        label.append(category_name)
        label.append(f' ({total_apps})', style='dim')
        return label

    def _tree_app_label(
        self,
        app: App,
        show_tags: bool = False,
        show_methods: bool = False,
        icon_resolver=None,
        *,
        show_installed: bool = False,
        installed: bool | None = None,
    ) -> Text:
        installed_state = installed
        if installed_state is None and (show_installed or show_methods):
            installed_state = self.is_app_installed(app)
        label = Text()
        if icon_resolver is not None:
            icon = icon_resolver.app_icon(app)
            if icon:
                label.append(f'{icon} ')
        label.append(app.name, style='bold green' if show_installed and installed_state else 'bold')
        if app.is_custom_installer_only():
            label.append(' [custom]', style='yellow')
        if show_methods:
            methods = self._ordered_available_methods_for_status(app, installed_state)
            if methods:
                label.append(
                    f" ({app.rendered_methods_label(methods, custom_methods=self._custom_method_names_for_status(app, installed_state))})",
                    style='dim',
                )
            else:
                unavailable_label = 'uninstall unavailable' if installed_state else 'installation unavailable'
                label.append(f' ({unavailable_label})', style='dim')
        if show_tags and app.tags:
            label.append(f" [{', '.join(app.tags)}]", style='green')
        return label

    def build_category_tree(self, apps: list[App] | None = None) -> dict[str, object]:
        tree: dict[str, dict[str, object]] = {}
        uncategorized: list[App] = []

        source_apps = self._apps if apps is None else apps
        for app in sorted(source_apps, key=lambda item: item.name):
            if not app.category:
                uncategorized.append(app)
                continue
            node: dict[str, dict[str, object]] = tree
            for segment in app.category:
                category_node = node.setdefault(segment, self._new_category_tree_node())
                node = category_node['children']
            category_node['apps'].append(app)

        total_apps = len(uncategorized)
        for category_node in tree.values():
            total_apps += self._populate_category_tree_counts(category_node)

        return {
            'categories': tree,
            'uncategorized': uncategorized,
            'uncategorized_total_apps': len(uncategorized),
            'total_apps': total_apps,
        }

    def render_category_tree(
        self,
        apps: list[App] | None = None,
        show_tags: bool = False,
        show_methods: bool = False,
        icon_resolver=None,
        *,
        show_installed: bool = False,
        installed_states: dict[App, bool] | None = None,
    ) -> Tree:
        source_apps = self._apps if apps is None else apps
        tree_data = self.build_category_tree(apps=source_apps)
        if installed_states is None:
            installed_states = self._installed_state_map(source_apps) if show_installed or show_methods else {}
        root_label = Text('apps', style='bold')
        root_label.append(f" ({tree_data['total_apps']})", style='dim')
        root = Tree(root_label)

        def add_nodes(parent: Tree, nodes: dict[str, dict[str, object]]) -> None:
            for category_name in sorted(nodes):
                category_node = nodes[category_name]
                branch = parent.add(
                    self._tree_category_label(
                        category_name,
                        category_node['total_apps'],
                        icon_resolver=icon_resolver,
                    )
                )
                add_nodes(branch, category_node['children'])
                for app in sorted(category_node['apps'], key=lambda item: item.name):
                    branch.add(
                        self._tree_app_label(
                            app,
                            show_tags=show_tags,
                            show_methods=show_methods,
                            icon_resolver=icon_resolver,
                            show_installed=show_installed,
                            installed=installed_states.get(app),
                        )
                    )

        add_nodes(root, tree_data['categories'])
        if tree_data['uncategorized']:
            branch = root.add(
                self._tree_category_label(
                    'uncategorized',
                    tree_data['uncategorized_total_apps'],
                    uncategorized=True,
                    icon_resolver=icon_resolver,
                )
            )
            for app in tree_data['uncategorized']:
                branch.add(
                    self._tree_app_label(
                        app,
                        show_tags=show_tags,
                        show_methods=show_methods,
                        icon_resolver=icon_resolver,
                        show_installed=show_installed,
                        installed=installed_states.get(app),
                    )
                )
        return root

    def search(self, name: str) -> App | None:
        for app in self._apps:
            if app.name == name or app.candidate == name:
                return app
        return None

    def search_apps(
        self,
        names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        exclusive: bool = False,
    ) -> list[App]:
        normalized_names = [name.lower() for name in (names or [])]
        normalized_categories = [self._parse_category_filter(category) for category in (categories or [])]
        normalized_tags = self._normalize_tags(tags, subject='Search tag filter')
        matches: list[App] = []

        for app in self._apps:
            group_matches: list[bool] = []
            if normalized_names:
                group_matches.append(any(self._name_matches(app, name) for name in normalized_names))
            if normalized_categories:
                group_matches.append(any(self._category_matches(app, category) for category in normalized_categories))
            if normalized_tags:
                app_tags = set(app.tags)
                group_matches.append(any(tag in app_tags for tag in normalized_tags))

            if not group_matches:
                continue
            if exclusive and all(group_matches):
                matches.append(app)
            elif not exclusive and any(group_matches):
                matches.append(app)

        return matches

    def get_app(self, name: str) -> App | None:
        for app in self._apps:
            if app.name == name:
                return app
        return None

    def add_app(self, app: App, force: bool = False) -> bool:
        for index, existing in enumerate(self._apps):
            if existing.name == app.name:
                if not force:
                    logger.error(f"App '{app.name}' already defined")
                    return False
                previous_inventory = app._inventory
                app._set_inventory(self)
                try:
                    self._validate_app_dependencies(app)
                except Exception:
                    app._set_inventory(previous_inventory)
                    raise
                existing._set_inventory(None)
                self._apps[index] = app
                return True
        previous_inventory = app._inventory
        app._set_inventory(self)
        try:
            self._validate_app_dependencies(app)
        except Exception:
            app._set_inventory(previous_inventory)
            raise
        self._apps.append(app)
        return True

    def remove_app(self, app: App) -> App | None:
        for index, existing in enumerate(self._apps):
            if existing.name == app.name:
                removed = self._apps.pop(index)
                removed._set_inventory(None)
                return removed
        logger.error(f"No app match for '{app.name}'")
        return None

    def _get_manager_candidate(self, app: App, target_mgr: dict[str, str]) -> str:
        return target_mgr['candidate'] if 'candidate' in target_mgr else app.candidate

    def _flatten_targets(self, targets: tuple[str | App | list[str | App], ...]) -> list[str | App]:
        flattened: list[str | App] = []
        for target in targets:
            if isinstance(target, list):
                flattened.extend(target)
            else:
                flattened.append(target)
        return flattened

    def _resolve_app(self, target: str | App) -> App | None:
        return target if isinstance(target, App) else self.search(target)

    def _parse_target(self, target: str | App) -> tuple[str | App, str | None]:
        if isinstance(target, App):
            return target, None
        match = self.TARGET_VERSION_PATTERN.fullmatch(target)
        if match is None:
            return target, None
        return match.group('name'), match.group('specifier')

    def _resolve_target_request(self, target: str | App) -> tuple[App | None, str | None, str | App]:
        lookup_target, version_specifier = self._parse_target(target)
        return self._resolve_app(lookup_target), version_specifier, lookup_target

    def _host_managers(self) -> set[str]:
        try:
            managers = ut.Platform.detect_package_managers(announce=False)
        except TypeError:
            managers = ut.Platform.detect_package_managers()
        return set(managers or [])

    def _host_install_tokens(self) -> set[str]:
        return ut.Platform.host_install_tokens()

    def _installer_available(self, installer_name: str) -> bool:
        tokens = ut.Platform.installer_tokens(installer_name)
        host_tokens = self._host_install_tokens()
        return any(token in host_tokens for token in tokens)

    def _probe_available(self, app: App, probe_name: str) -> bool:
        managers = _get_managers()
        if probe_name in managers:
            return probe_name in app.managers and managers[probe_name].available_on_host()
        probe = app.probes.get(probe_name)
        return probe is not None and self._installer_available(probe_name)

    def _candidate_for_path_probe(self, value: str) -> str | None:
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if not candidate:
            return None
        try:
            tokens = shlex.split(candidate)
        except ValueError:
            return None
        if len(tokens) != 1:
            return None
        token = tokens[0]
        if token.startswith('-'):
            return None
        if any(marker in token for marker in ('/', ':', '=', '@')):
            return None
        if token.count('.') >= 2:
            return None
        return token

    def _is_installed_via_path(self, app: App) -> bool:
        probe_targets = [app.name]
        candidate = self._candidate_for_path_probe(app.candidate)
        if candidate is not None and candidate not in probe_targets:
            probe_targets.append(candidate)
        return any(shutil.which(target) is not None for target in probe_targets if target)

    def _available_methods(self, app: App, include_installers: bool = True) -> dict[str, list[str]]:
        managers = _get_managers()
        available_managers = [
            name for name in app.managers
            if name in managers and managers[name].available_on_host()
        ]
        available_installers = [
            name for name in app.installers.keys()
            if include_installers and self._installer_available(name)
        ]
        return {'managers': available_managers, 'installers': available_installers}

    def _available_uninstall_methods(self, app: App) -> dict[str, list[str]]:
        managers = _get_managers()
        available_managers = [
            name for name in app.managers
            if name in managers and managers[name].available_on_host()
        ]
        available_uninstallers = [
            name for name in app.uninstallers.keys()
            if self._installer_available(name)
        ]
        return {'managers': available_managers, 'uninstallers': available_uninstallers}

    def _select_post_install(self, app: App) -> str | None:
        for post_install_name in app.post_install:
            if self._installer_available(post_install_name):
                return post_install_name
        return None

    def _effective_preference(self, app: App) -> list[str]:
        return _dedupe_preserve_order([*app.preference, *ut.Config.data['PREFERENCE']])

    def _ordered_available_methods(self, app: App, include_installers: bool = True) -> list[str]:
        available = self._available_methods(app, include_installers=include_installers)
        available_managers = set(available['managers'])
        available_installers = list(available['installers'])
        explicit_installers = set(item for item in app.preference if item in app.installers)
        ordered: list[str] = []

        for token in self._effective_preference(app):
            if token == 'custom_installers':
                for installer_name in available_installers:
                    if installer_name in explicit_installers or installer_name in ordered:
                        continue
                    ordered.append(installer_name)
                continue
            if token in available_managers or token in available_installers:
                if token not in ordered:
                    ordered.append(token)

        return ordered

    def _ordered_defined_methods(self, app: App) -> list[str]:
        defined_managers = set(app.managers)
        defined_installers = list(app.installers)
        explicit_installers = set(item for item in app.preference if item in app.installers)
        ordered: list[str] = []

        for token in self._effective_preference(app):
            if token == 'custom_installers':
                for installer_name in defined_installers:
                    if installer_name in explicit_installers or installer_name in ordered:
                        continue
                    ordered.append(installer_name)
                continue
            if token in defined_managers or token in defined_installers:
                if token not in ordered:
                    ordered.append(token)

        return ordered

    def _available_method_names(self, app: App) -> set[str]:
        available = self._available_methods(app, include_installers=True)
        return set(available['managers']) | set(available['installers'])

    def _ordered_defined_uninstall_methods(self, app: App) -> list[str]:
        defined_managers = set(app.managers)
        defined_uninstallers = list(app.uninstallers)
        explicit_uninstallers = set(item for item in app.preference if item in app.uninstallers)
        ordered: list[str] = []

        for token in self._effective_preference(app):
            if token == 'custom_installers':
                for uninstaller_name in defined_uninstallers:
                    if uninstaller_name in explicit_uninstallers or uninstaller_name in ordered:
                        continue
                    ordered.append(uninstaller_name)
                continue
            if token in defined_managers or token in defined_uninstallers:
                if token not in ordered:
                    ordered.append(token)

        return ordered

    def _available_uninstall_method_names(self, app: App) -> set[str]:
        available = self._available_uninstall_methods(app)
        return set(available['managers']) | set(available['uninstallers'])

    def _ordered_available_methods_for_status(self, app: App, installed: bool) -> list[str]:
        if installed:
            return self._ordered_available_uninstall_methods(app)
        return self._ordered_available_methods(app)

    def _ordered_defined_methods_for_status(self, app: App, installed: bool) -> list[str]:
        if installed:
            return self._ordered_defined_uninstall_methods(app)
        return self._ordered_defined_methods(app)

    def _available_method_names_for_status(self, app: App, installed: bool) -> set[str]:
        if installed:
            return self._available_uninstall_method_names(app)
        return self._available_method_names(app)

    def _custom_method_names_for_status(self, app: App, installed: bool) -> set[str]:
        if installed:
            return set(app.uninstallers)
        return set(app.installers)

    def _ordered_available_uninstall_methods(self, app: App) -> list[str]:
        available = self._available_uninstall_methods(app)
        available_managers = set(available['managers'])
        available_uninstallers = list(available['uninstallers'])
        explicit_uninstallers = set(item for item in app.preference if item in app.uninstallers)
        ordered: list[str] = []

        for token in self._effective_preference(app):
            if token == 'custom_installers':
                for uninstaller_name in available_uninstallers:
                    if uninstaller_name in explicit_uninstallers or uninstaller_name in ordered:
                        continue
                    ordered.append(uninstaller_name)
                continue
            if token in available_managers or token in available_uninstallers:
                if token not in ordered:
                    ordered.append(token)

        return ordered

    def _select_method(self, app: App, include_installers: bool = True) -> str | None:
        methods = self._ordered_available_methods(app, include_installers=include_installers)
        return methods[0] if methods else None

    def _select_uninstall_method(self, app: App) -> str | None:
        methods = self._ordered_available_uninstall_methods(app)
        return methods[0] if methods else None

    def _is_installed_via_named_manager(self, app: App, manager_name: str) -> bool | None:
        managers = _get_managers()
        target_mgr = app.managers[manager_name]
        candidate = self._get_manager_candidate(app, target_mgr)
        return managers[manager_name].is_installed_target(target_mgr, candidate)

    def _probe_app_via_named_probe(self, app: App, probe_name: str) -> bool | None:
        managers = _get_managers()
        if probe_name in managers:
            if probe_name not in app.managers:
                return None
            return self._is_installed_via_named_manager(app, probe_name)
        probe = app.probes.get(probe_name)
        if probe is None:
            return None
        return probe.check()

    def _probe_app_via_probes(self, app: App) -> bool | None:
        if not app.probes:
            return None
        for probe_name in app.probes:
            if not self._probe_available(app, probe_name):
                continue
            try:
                if self._probe_app_via_named_probe(app, probe_name) is True:
                    return True
            except Exception:
                continue
        return self._is_installed_via_path(app)

    def is_app_installed(self, app: App) -> bool:
        if app.installed is not None:
            return app.installed
        probe_state = self._probe_app_via_probes(app)
        if probe_state is not None:
            return probe_state
        checked_manager = False
        for manager_name in self._ordered_available_methods(app, include_installers=False):
            if manager_name not in app.managers:
                continue
            checked_manager = True
            try:
                if self._is_installed_via_named_manager(app, manager_name) is True:
                    return True
            except Exception:
                continue
        return self._is_installed_via_path(app)

    def _installed_state_for_method(self, app: App, method_name: str) -> bool | None:
        if app.installed is not None:
            return app.installed
        probe_state = self._probe_app_via_probes(app)
        if probe_state is not None:
            return probe_state
        if method_name in app.managers:
            return self._is_installed_via_named_manager(app, method_name)
        return self.is_app_installed(app)

    def _set_installed_state(self, app: App, installed: bool) -> None:
        app.installed = installed
        self.save(ut.Config.data['DEFAULT_INVENTORY_PATH'])

    def _normalize_script_status(self, status: int | None) -> int:
        return SCRIPT_OK if status is None else status

    def _warn_ignored_venv(self, method_name: str, warned_methods: set[str]) -> None:
        if method_name in warned_methods:
            return
        logger.error(f"Ignoring '--venv' for non-pip method '{method_name}'")
        warned_methods.add(method_name)

    def _run_manager_operation(self, operation: str, app: App, manager_name: str, action) -> tuple[int, object]:
        try:
            return SCRIPT_OK, action()
        except KeyboardInterrupt:
            label = 'Install' if operation == 'install' else 'Uninstall'
            logger.warning(f"{label} interrupted by user")
            return SCRIPT_INTERRUPTED, None
        except subprocess.CalledProcessError as exc:
            action_label = 'install' if operation == 'install' else 'remove'
            logger.error(f"Failed to {action_label} '{app.name}'")
            logger.error(_manager_failure_message(operation, app.name, manager_name, exc))
            return SCRIPT_ERROR, None
        except Exception as exc:
            action_label = 'install' if operation == 'install' else 'remove'
            logger.error(f"Failed to {action_label} '{app.name}'")
            logger.exception(_manager_failure_message(operation, app.name, manager_name, exc))
            return SCRIPT_ERROR, None

    def _install_via_named_manager(
        self,
        app: App,
        manager_name: str,
        force: bool = False,
        version_specifier: str | None = None,
        venv: str | None = None,
    ) -> None:
        managers = _get_managers()
        target_mgr = app.managers[manager_name]
        candidate = self._get_manager_candidate(app, target_mgr)
        manager = managers[manager_name]
        manager.prepare(target_mgr)
        if manager_name == 'pip':
            manager.install_target(target_mgr, candidate, force=force, version_specifier=version_specifier, venv=venv)
            return
        manager.install_target(target_mgr, candidate, force=force)

    def _uninstall_via_named_manager(
        self,
        app: App,
        manager_name: str,
        remove_repo: bool = False,
        version_specifier: str | None = None,
        venv: str | None = None,
    ) -> None:
        managers = _get_managers()
        target_mgr = app.managers[manager_name]
        candidate = self._get_manager_candidate(app, target_mgr)
        manager = managers[manager_name]
        if manager_name == 'pip':
            manager.uninstall_target(target_mgr, candidate, version_specifier=version_specifier, venv=venv)
        else:
            manager.uninstall_target(target_mgr, candidate)
        manager.cleanup(target_mgr, remove_repo=remove_repo)

    def _run_installer(self, app: App, installer_name: str) -> int:
        try:
            installer = app.installers[installer_name]
        except KeyError as exc:
            raise ValueError(f"[-] Installer '{installer_name}' not available for '{app.name}'") from exc
        return installer.run(app_name=app.name, manager_map=_get_managers())

    def _run_uninstaller(self, app: App, uninstaller_name: str) -> int:
        try:
            uninstaller = app.uninstallers[uninstaller_name]
        except KeyError as exc:
            raise ValueError(f"[-] Uninstaller '{uninstaller_name}' not available for '{app.name}'") from exc
        return uninstaller.run(app_name=app.name, manager_map=_get_managers(), operation='uninstall')

    def _run_post_install(self, app: App, post_install_name: str) -> int:
        try:
            installer = app.post_install[post_install_name]
        except KeyError as exc:
            raise ValueError(f"[-] Post-install '{post_install_name}' not available for '{app.name}'") from exc
        return installer.run(app_name=app.name, manager_map=_get_managers(), label='post-install')

    def _warn_ignored_post_install_venv(self, post_install_name: str, warned_methods: set[str]) -> None:
        warning_key = f'post_install:{post_install_name}'
        if warning_key in warned_methods:
            return
        logger.error(f"Ignoring '--venv' for post-install '{post_install_name}'")
        warned_methods.add(warning_key)

    def _run_post_install_if_available(
        self,
        app: App,
        *,
        venv: str | None = None,
        warned_methods: set[str] | None = None,
    ) -> int:
        post_install_name = self._select_post_install(app)
        if post_install_name is None:
            return SCRIPT_OK
        if warned_methods is None:
            warned_methods = set()
        if venv is not None:
            self._warn_ignored_post_install_venv(post_install_name, warned_methods)
        try:
            return self._normalize_script_status(self._run_post_install(app, post_install_name))
        except Exception as exc:
            logger.exception(f"Post-install '{post_install_name}' failed for '{app.name}': {exc}")
            return SCRIPT_ERROR

    def _missing_dependencies(self, app: App) -> tuple[list[App], list[str]]:
        missing: list[App] = []
        unresolved: list[str] = []
        for dependency_name in app.dependencies:
            dependency = self.get_app(dependency_name)
            if dependency is None:
                unresolved.append(dependency_name)
                continue
            if not self.is_app_installed(dependency):
                missing.append(dependency)
        return missing, unresolved

    def _install_app(
        self,
        app: App,
        *,
        version_specifier: str | None = None,
        installer: str | None = None,
        force: bool = False,
        venv: str | None = None,
        needed: bool = False,
        warned_methods: set[str] | None = None,
        installing: set[str] | None = None,
    ) -> int:
        if warned_methods is None:
            warned_methods = set()
        if installing is None:
            installing = set()
        if app.name in installing:
            logger.warning(f"Dependency cycle detected: {app.name}")
            return SCRIPT_ERROR

        installing.add(app.name)
        try:
            if installer is not None:
                if installer not in app.installers:
                    raise ValueError(f"[-] Installer '{installer}' not available for '{app.name}'")
                selected_method = installer
            else:
                selected_method = self._select_method(app, include_installers=True)
                if selected_method is None:
                    logger.warning(f"No installation method available for '{app.name}' on this host")
                    return SCRIPT_OK

            if selected_method in app.managers:
                status, installed = self._run_manager_operation(
                    'install',
                    app,
                    selected_method,
                    lambda: self._installed_state_for_method(app, selected_method),
                )
                if status != SCRIPT_OK:
                    return status
            else:
                installed = self._installed_state_for_method(app, selected_method)
            if installed is True and not force:
                logger.warning(f"'{app.name}' is already installed via '{selected_method}'")
                return SCRIPT_OK

            missing_dependencies, unresolved_dependencies = self._missing_dependencies(app)
            missing_dependency_names = [dependency.name for dependency in missing_dependencies] + unresolved_dependencies
            if missing_dependency_names:
                if not needed or unresolved_dependencies:
                    logger.warning(f"Missing dependencies: {', '.join(missing_dependency_names)}")
                    return SCRIPT_OK
                for dependency in missing_dependencies:
                    status = self._install_app(
                        dependency,
                        force=force,
                        venv=venv,
                        needed=True,
                        warned_methods=warned_methods,
                        installing=installing,
                    )
                    if status != SCRIPT_OK:
                        return status

            if selected_method in app.managers:
                if venv is not None and selected_method != 'pip':
                    self._warn_ignored_venv(selected_method, warned_methods)
                status, _ = self._run_manager_operation(
                    'install',
                    app,
                    selected_method,
                    lambda: self._install_via_named_manager(
                        app,
                        selected_method,
                        force=force,
                        version_specifier=version_specifier,
                        venv=venv,
                    ),
                )
                if status != SCRIPT_OK:
                    return status
                self._set_installed_state(app, True)
                logger.success(f"Installed '{app.name}'")
                return self._run_post_install_if_available(app, venv=venv, warned_methods=warned_methods)

            if venv is not None:
                self._warn_ignored_venv(selected_method, warned_methods)
            status = self._normalize_script_status(self._run_installer(app, selected_method))
            if status != SCRIPT_OK:
                if status == SCRIPT_ERROR:
                    logger.error(f"Failed to install '{app.name}'")
                return status
            self._set_installed_state(app, True)
            logger.success(f"Installed '{app.name}'")
            return self._run_post_install_if_available(app, venv=venv, warned_methods=warned_methods)
        finally:
            installing.remove(app.name)

    def install(
        self,
        *targets: str | App | list[str | App],
        installer: str | None = None,
        force: bool = False,
        venv: str | None = None,
        needed: bool = False,
    ) -> int:
        flattened = self._flatten_targets(targets)
        if len(flattened) == 0:
            logger.warning("Specify a package to install")
            return SCRIPT_OK
        warned_methods: set[str] = set()
        installing: set[str] = set()
        final_status = SCRIPT_OK
        for target in flattened:
            app, version_specifier, _lookup_target = self._resolve_target_request(target)
            if app is None:
                logger.warning(f"No match for '{target}'")
                continue
            status = self._install_app(
                app,
                version_specifier=version_specifier,
                installer=installer,
                force=force,
                venv=venv,
                needed=needed,
                warned_methods=warned_methods,
                installing=installing,
            )
            if status == SCRIPT_INTERRUPTED:
                return SCRIPT_INTERRUPTED
            if status == SCRIPT_ERROR:
                final_status = SCRIPT_ERROR
        return final_status

    def uninstall(self, *targets: str | App | list[str | App], remove_repo: bool = False, venv: str | None = None) -> int:
        flattened = self._flatten_targets(targets)
        if len(flattened) == 0:
            logger.warning("Specify a package to uninstall")
            return SCRIPT_OK
        warned_methods: set[str] = set()
        final_status = SCRIPT_OK
        for target in flattened:
            app, version_specifier, _lookup_target = self._resolve_target_request(target)
            if app is None:
                logger.warning(f"No match for '{target}'")
                continue
            selected_method = self._select_uninstall_method(app)
            if selected_method is None:
                logger.warning(f"No uninstallation method available for '{app.name}' on this host")
                continue
            if venv is not None and selected_method != 'pip':
                self._warn_ignored_venv(selected_method, warned_methods)
            if selected_method in app.managers:
                status, _ = self._run_manager_operation(
                    'uninstall',
                    app,
                    selected_method,
                    lambda: self._uninstall_via_named_manager(app, selected_method, remove_repo=remove_repo, version_specifier=version_specifier, venv=venv),
                )
                if status == SCRIPT_INTERRUPTED:
                    return SCRIPT_INTERRUPTED
                if status == SCRIPT_ERROR:
                    final_status = SCRIPT_ERROR
                    continue
            else:
                status = self._normalize_script_status(self._run_uninstaller(app, selected_method))
                if status == SCRIPT_INTERRUPTED:
                    return SCRIPT_INTERRUPTED
                if status == SCRIPT_ERROR:
                    logger.error(f"Failed to remove '{app.name}'")
                    final_status = SCRIPT_ERROR
                    continue
            self._set_installed_state(app, False)
            logger.success(f"Removed '{app.name}'")
        return final_status

_SKIP_DIRS = frozenset({
    '.cache', '.cargo', '.local', '.npm', '.rustup',
    '.venv', 'venv', 'node_modules', '__pycache__',
    '.Trash', '.git', '.svn', '.gradle', '.m2', 'Code - OSS'
})


def is_inventory_file(path: str | Path) -> bool:
    """Return whether a path looks like an Aplet inventory YAML file.

    A valid inventory file must be readable YAML and start with an Aplet
    inventory header such as ``### APLET INVENTORY ###``.

    Args:
        path: File path to inspect.

    Returns:
        ``True`` when the file is an Aplet inventory, otherwise ``False``.
    """
    path = Path(path)
    try:
        with path.open('r', encoding='utf-8') as f:
            content = yaml.safe_load(f) # validate yaml content
            if content is None: # empty yaml file
                return False
            f.seek(0)
            if f.readline().strip() in INVENTORY_HEADERS:
                return True
            return False
    except (yaml.YAMLError, PermissionError, UnicodeDecodeError, OSError):
        # Ignore parsing, permission, and binary file errors
        return False


def discover_inventories(search_root: Path | None = None) -> list[Path]:
    """Discover Aplet inventory files below a directory.

    Args:
        search_root: Directory to scan. Defaults to the current user's home
            directory.

    Returns:
        A list of matching inventory file paths.
    """
    if search_root is None:
        search_root = Path.home()
    results: list[Path] = []

    def _walk(root: Path) -> None:
        try:
            for entry in root.iterdir():
                if entry.is_dir():
                    if entry.name in _SKIP_DIRS:
                        continue
                    _walk(entry)
                elif entry.suffix in ('.yml', '.yaml'):
                    if is_inventory_file(entry):
                        results.append(entry)
        except PermissionError:
            pass

    _walk(search_root)
    return results
