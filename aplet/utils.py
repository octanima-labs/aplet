from pathlib import Path

import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tuning
import yaml

from . import file_helper


PACKAGE_DIR: Path = Path(__file__).parent
RESOURCE_DIR: Path = PACKAGE_DIR / 'resources'
LOG_FILE: Path = Path.home() / '.local' / 'state' / 'aplet' / 'aplet.log'


def configure_logging(level: str = 'INFO') -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tuning.basicConfig(
        filename=str(LOG_FILE),
        console=True,
        level=level,
        max_bytes='10 MB',
        backup_count=3,
    )


def get_logger(name: str):
    return tuning.getLogger(name)


class Display:
    ANSI_RESET = '\033[0m'
    ANSI_BOLD = '\033[1m'
    ANSI_BOLD_GREEN = '\033[1;92m'
    ANSI_DIM = '\033[90m'
    ANSI_RED = '\033[91m'
    ANSI_KEY = '\033[92m'
    ANSI_VALUE = '\033[96m'
    ANSI_SPECIAL = '\033[93m'

    @staticmethod
    def supports_color() -> bool:
        return sys.stdout.isatty() and 'NO_COLOR' not in os.environ

    @staticmethod
    def apply(text: str, color: str, *, force: bool = False) -> str:
        if not force and not Display.supports_color():
            return text
        return f"{color}{text}{Display.ANSI_RESET}"

    @staticmethod
    def color_key(text: str, *, force: bool = False) -> str:
        return Display.apply(text, Display.ANSI_KEY, force=force)

    @staticmethod
    def color_value(text: str, *, force: bool = False) -> str:
        return Display.apply(text, Display.ANSI_VALUE, force=force)

    @staticmethod
    def color_special(text: str, *, force: bool = False) -> str:
        return Display.apply(text, Display.ANSI_SPECIAL, force=force)

    @staticmethod
    def color_dim(text: str, *, force: bool = False) -> str:
        return Display.apply(text, Display.ANSI_DIM, force=force)

    @staticmethod
    def color_red(text: str, *, force: bool = False) -> str:
        return Display.apply(text, Display.ANSI_RED, force=force)

    @staticmethod
    def bold(text: str, *, force: bool = False) -> str:
        return Display.apply(text, Display.ANSI_BOLD, force=force)

    @staticmethod
    def bold_green(text: str, *, force: bool = False) -> str:
        return Display.apply(text, Display.ANSI_BOLD_GREEN, force=force)

    @staticmethod
    def print_list(*args) -> None:
        if len(args) == 0:
            print('<empty list>')
            return
        if len(args) == 1 and isinstance(args[0], list):
            values = args[0]
        else:
            values = list(args)
        for ind, val in enumerate(values, 1):
            print(f"{ind:>3d}. {val}")


class Yaml:
    @staticmethod
    def load(path: str | Path):
        with open(path, 'r') as file:
            return yaml.safe_load(file)

    @staticmethod
    def _colorize_value(value: str) -> str:
        stripped = value.strip()
        if stripped in {'null', 'true', 'false'}:
            return Display.color_special(value, force=True)
        if re.fullmatch(r'-?\d+(?:\.\d+)?', stripped):
            return Display.color_special(value, force=True)
        return Display.color_value(value, force=True)

    @staticmethod
    def highlight(text: str) -> str:
        highlighted_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            newline = '\n' if line.endswith('\n') else ''
            body = line[:-1] if newline else line
            if not body.strip():
                highlighted_lines.append(line)
                continue
            if body.lstrip().startswith('#'):
                highlighted_lines.append(f"{Display.color_dim(body, force=True)}{newline}")
                continue

            key_match = re.match(r'^(\s*(?:-\s+)?)?([^:#\n][^:#\n]*?):(?:\s*(.*))?$', body)
            if key_match is None:
                highlighted_lines.append(f"{body}{newline}")
                continue

            prefix = key_match.group(1) or ''
            key = key_match.group(2)
            value = key_match.group(3)
            rendered = f"{prefix}{Display.color_key(key, force=True)}:"
            if value is not None and value != '':
                if '#' in value:
                    value_part, comment = value.split('#', 1)
                    rendered += f" {Yaml._colorize_value(value_part.rstrip())}"
                    rendered += f" {Display.color_dim(f'#{comment}', force=True)}"
                else:
                    rendered += f" {Yaml._colorize_value(value)}"
            highlighted_lines.append(f"{rendered}{newline}")

        return ''.join(highlighted_lines)


class Shell:
    @staticmethod
    def run(cmd: str, **kwargs) -> subprocess.CompletedProcess:
        capture_output = kwargs.pop('capture_output', True)
        check = kwargs.pop('check', True)
        timeout = kwargs.pop('timeout', None)
        input_data = kwargs.pop('input', None)
        kwargs.setdefault('text', True)
        if capture_output:
            kwargs.setdefault('stdout', subprocess.PIPE)
            kwargs.setdefault('stderr', subprocess.PIPE)
        if input_data is not None:
            kwargs.setdefault('stdin', subprocess.PIPE)
        if platform.system() == 'Windows':
            popen_args = (['powershell.exe', '-NoProfile', '-Command', cmd],)
            use_process_group = False
        else:
            popen_args = (cmd,)
            kwargs.setdefault('shell', True)
            kwargs.setdefault('executable', 'bash')
            use_process_group = kwargs.get('start_new_session') is True
        process = subprocess.Popen(*popen_args, **kwargs)
        try:
            stdout, stderr = process.communicate(input=input_data, timeout=timeout)
        except KeyboardInterrupt:
            if use_process_group:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if use_process_group:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait()
            raise
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, stderr = process.communicate()
            exc.output = stdout
            exc.stderr = stderr
            raise

        result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result


class Platform:
    PACKAGE_MANAGERS = {
        'apt': 'Debian/Ubuntu/Kali',
        'dnf': 'Fedora/RHEL/CentOS',
        'yum': 'RHEL/CentOS (Older)',
        'pacman': 'Arch/Manjaro',
        'yay': 'Arch/Manjaro (AUR)',
        'zypper': 'openSUSE',
        'brew': 'macOS (Homebrew)',
        'choco': 'Windows (Chocolatey)',
        'scoop': 'Windows (Scoop)',
        'flatpak': 'Flatpak',
        'snap': 'Snap',
        'npm': 'npm',
        'pip': 'pip',
        'pipx': 'pipx',
    }
    INSTALLER_ALIASES = {
        'windows': 'win',
        'archlinux': 'arch',
    }
    VALID_INSTALLER_TOKENS = {
        'linux',
        'ubuntu',
        'debian',
        'arch',
        'manjaro',
        'centos',
        'fedora',
        'rhel',
        'opensuse',
        'kali',
        'macos',
        'win',
    }
    LINUX_DISTRO_TOKENS = {
        'ubuntu',
        'debian',
        'arch',
        'manjaro',
        'centos',
        'fedora',
        'rhel',
        'opensuse',
        'kali',
    }

    @classmethod
    def detect_package_managers(cls, announce: bool = True) -> list[str] | None:
        found: list[str] = []
        for cmd in cls.PACKAGE_MANAGERS:
            if shutil.which(cmd):
                found.append(cmd)
        if announce:
            get_logger(__name__).debug(f"Package managers found: {', '.join(found)}")
        return found if found else None

    @classmethod
    def normalize_installer_token(cls, token: str) -> str:
        normalized = cls.INSTALLER_ALIASES.get(token.lower(), token.lower())
        if normalized not in cls.VALID_INSTALLER_TOKENS:
            raise ValueError(f"[-] Unknown installer platform token '{token}'")
        return normalized

    @classmethod
    def maybe_normalize_installer_token(cls, token: str) -> str | None:
        normalized = cls.INSTALLER_ALIASES.get(token.lower(), token.lower())
        return normalized if normalized in cls.VALID_INSTALLER_TOKENS else None

    @classmethod
    def installer_tokens(cls, name: str) -> list[str]:
        tokens = [cls.normalize_installer_token(token) for token in name.split('_') if token]
        if not tokens:
            raise ValueError(f"[-] Invalid installer name '{name}'")
        if 'linux' in tokens and any(token in cls.LINUX_DISTRO_TOKENS for token in tokens if token != 'linux'):
            raise ValueError(f"[-] Installer '{name}' cannot mix 'linux' with Linux distro-specific tokens")
        return tokens

    @classmethod
    def host_install_tokens(cls) -> set[str]:
        system = platform.system().lower()
        if system == 'linux':
            tokens = {'linux'}
            release_data = platform.freedesktop_os_release()
            id_like = release_data.get('ID_LIKE', '')
            for token in id_like.split():
                normalized = cls.maybe_normalize_installer_token(token)
                if normalized is not None:
                    tokens.add(normalized)
            distro_id = release_data.get('ID')
            if distro_id:
                normalized = cls.maybe_normalize_installer_token(distro_id)
                if normalized is not None:
                    tokens.add(normalized)
            return tokens
        if system == 'windows':
            return {'win'}
        if system == 'darwin':
            return {'macos'}
        return {system}


class Files:
    PATCH_CMD_TOKEN = '{{cmd:'

    @staticmethod
    def expand_path(path: str | Path) -> Path:
        return Path(os.path.expanduser(os.path.expandvars(str(path))))

    @staticmethod
    def _expand_patch_placeholder(line: str) -> str:
        parts: list[str] = []
        cursor = 0
        while True:
            start = line.find(Files.PATCH_CMD_TOKEN, cursor)
            if start < 0:
                parts.append(line[cursor:])
                return ''.join(parts)
            parts.append(line[cursor:start])
            end = line.find('}}', start + len(Files.PATCH_CMD_TOKEN))
            if end < 0:
                raise ValueError(f"[-] Malformed patch placeholder in line: {line!r}")
            command = line[start + len(Files.PATCH_CMD_TOKEN):end]
            if not command.strip() or Files.PATCH_CMD_TOKEN in command:
                raise ValueError(f"[-] Malformed patch placeholder in line: {line!r}")
            output = Shell.run(command).stdout.rstrip('\n')
            if '\n' in output:
                raise ValueError(f"[-] Patch placeholder command returned multiple lines: {command}")
            parts.append(output)
            cursor = end + 2

    @staticmethod
    def _expand_patch_placeholders(lines: list[str]) -> list[str]:
        return [Files._expand_patch_placeholder(line) for line in lines]

    @staticmethod
    def _nearest_existing_parent(path: Path) -> Path:
        current = path
        while not current.exists():
            if current.parent == current:
                return current
            current = current.parent
        return current

    @staticmethod
    def _can_create_directly(path: Path) -> bool:
        existing_parent = Files._nearest_existing_parent(path.parent)
        return os.access(existing_parent, os.W_OK | os.X_OK)

    @staticmethod
    def _can_patch_directly(path: Path) -> bool:
        if path.exists():
            return os.access(path, os.R_OK) and os.access(path, os.W_OK)
        return Files._can_create_directly(path)

    @staticmethod
    def _can_write_directly(path: Path) -> bool:
        if path.exists():
            return os.access(path, os.W_OK)
        return Files._can_create_directly(path)

    @staticmethod
    def _can_remove_directly(path: Path) -> bool:
        if not path.exists():
            return True
        parent = Files._nearest_existing_parent(path.parent)
        return os.access(parent, os.W_OK | os.X_OK)

    @staticmethod
    def _run_privileged_helper(payload: dict) -> None:
        if platform.system() == 'Windows':
            raise PermissionError('[!] Automatic elevated file operations are not supported on Windows; run Aplet from an elevated PowerShell')

        helper_cmd = [sys.executable, '-m', 'aplet.file_helper']
        if not hasattr(os, 'geteuid') or os.geteuid() != 0:
            helper_cmd.insert(0, 'sudo')
        subprocess.run(helper_cmd, input=json.dumps(payload), text=True, check=True)

    @staticmethod
    def open_file(path: str | Path, read_only: bool = False) -> None:
        target_path = Files.expand_path(path)
        if read_only:
            contents = target_path.read_text()
            print(Yaml.highlight(contents) if Display.supports_color() else contents, end='')
            return
        editor_cmd = shlex.split(os.environ.get('EDITOR', 'nano')) or ['nano']
        subprocess.run([*editor_cmd, str(target_path)], check=True)

    @staticmethod
    def write_text(path: str | Path, content: str, create_parents: bool = False) -> None:
        target_path = Files.expand_path(path)
        if Files._can_write_directly(target_path):
            try:
                file_helper.write_text_impl(target_path, content, create_parents=create_parents)
                return
            except PermissionError:
                pass
        Files._run_privileged_helper(
            {
                'action': 'write_text',
                'path': str(target_path),
                'content': content,
                'create_parents': create_parents,
            }
        )

    @staticmethod
    def remove_path(path: str | Path, missing_ok: bool = False) -> None:
        target_path = Files.expand_path(path)
        if Files._can_remove_directly(target_path):
            try:
                file_helper.remove_path_impl(target_path, missing_ok=missing_ok)
                return
            except PermissionError:
                pass
        Files._run_privileged_helper(
            {
                'action': 'remove_path',
                'path': str(target_path),
                'missing_ok': missing_ok,
            }
        )

    @staticmethod
    def patch_file(path: str | Path, block_id: str, patch: str | list[str], app_name: str = 'PATCH') -> None:
        target_path = Files.expand_path(path)
        if isinstance(patch, str):
            lines = [patch]
        elif isinstance(patch, list) and all(isinstance(line, str) for line in patch):
            lines = list(patch)
        else:
            raise TypeError(f"Unsupported type for param 'patch' ({type(patch)})")
        lines = Files._expand_patch_placeholders(lines)
        if Files._can_patch_directly(target_path):
            try:
                file_helper.patch_file_impl(target_path, app_name, block_id, lines)
                return
            except PermissionError:
                pass
        Files._run_privileged_helper(
            {
                'action': 'patch_file',
                'path': str(target_path),
                'app_name': app_name,
                'block_id': block_id,
                'lines': lines,
            }
        )


class Icons:
    FILE = RESOURCE_DIR / 'icons.yml'
    OVERRIDE_SECTIONS = {'defaults', 'apps', 'categories', 'tags', 'keywords'}
    _ICON_SETS: dict[str, dict[str, str]] | None = None

    @staticmethod
    def _normalize_override_value(value: str) -> str:
        stripped = value.strip()
        return stripped if stripped else ''

    @classmethod
    def _normalize_override_mapping(cls, section_name: str, mapping: object) -> dict[str, str]:
        if not isinstance(mapping, dict):
            raise TypeError(f"[-] Config key 'ICON_OVERRIDES.{section_name}' must be a mapping")
        normalized: dict[str, str] = {}
        for key, value in mapping.items():
            if not isinstance(key, str):
                raise TypeError(f"[-] Config key 'ICON_OVERRIDES.{section_name}' must use string keys")
            if not isinstance(value, str):
                raise TypeError(f"[-] Config key 'ICON_OVERRIDES.{section_name}.{key}' must be a string")
            normalized[key.strip().lower()] = cls._normalize_override_value(value)
        return normalized

    @classmethod
    def normalize_overrides(cls, overrides: object) -> dict[str, dict[str, str]]:
        if overrides is None:
            return {}
        if not isinstance(overrides, dict):
            raise TypeError("[-] Config key 'ICON_OVERRIDES' must be a mapping")
        normalized: dict[str, dict[str, str]] = {}
        for section_name, section_value in overrides.items():
            if not isinstance(section_name, str):
                continue
            section_key = section_name.strip().lower()
            if section_key not in cls.OVERRIDE_SECTIONS:
                continue
            normalized[section_key] = cls._normalize_override_mapping(section_key, section_value)
        return normalized

    @classmethod
    def _normalize_file_mapping(cls, section_name: str, mapping: object) -> dict[str, str]:
        if mapping is None:
            return {}
        if not isinstance(mapping, dict):
            raise TypeError(f"[-] Icon file section '{section_name}' must be a mapping")
        normalized: dict[str, str] = {}
        for key, value in mapping.items():
            if not isinstance(key, str):
                raise TypeError(f"[-] Icon file section '{section_name}' must use string keys")
            if not isinstance(value, str):
                raise TypeError(f"[-] Icon file section '{section_name}.{key}' must be a string")
            normalized[key.strip().lower()] = cls._normalize_override_value(value)
        return normalized

    @classmethod
    def _load_icon_sets(cls) -> dict[str, dict[str, str]]:
        icon_data = Yaml.load(cls.FILE) or {}
        if not isinstance(icon_data, dict):
            raise TypeError(f"[-] Icon file '{cls.FILE.name}' must contain a mapping")
        return {
            'apps': cls._normalize_file_mapping('apps', icon_data.get('apps')),
            'keywords': cls._normalize_file_mapping('keywords', icon_data.get('keywords')),
        }

    @classmethod
    def icon_sets(cls) -> dict[str, dict[str, str]]:
        if cls._ICON_SETS is None:
            cls._ICON_SETS = cls._load_icon_sets()
        return cls._ICON_SETS


class Config:
    FILE = Path.home() / '.config' / 'aplet' / 'aplet.conf'
    DEFAULT_CONFIG_FILE = RESOURCE_DIR / 'aplet.conf'
    DEFAULT_INVENTORY_FILE = RESOURCE_DIR / 'inventory.yml'
    BUILTIN_INVENTORY_PATH = DEFAULT_INVENTORY_FILE
    DEFAULT_PREFERENCE = [
        'apt',
        'pacman',
        'yay',
        'yum',
        'dnf',
        'zypper',
        'brew',
        'choco',
        'scoop',
        'git',
        'npm',
        'pip',
        'pipx',
        'flatpak',
        'snap',
        'custom_installers',
    ]
    VALID_PREFERENCE_TOKENS = set(DEFAULT_PREFERENCE)
    data: dict[str, object] = {}

    @classmethod
    def _normalize_loaded_data(cls, data: object) -> dict[str, object]:
        if not isinstance(data, dict):
            raise TypeError(f"[-] Config file '{cls.FILE.name}' must contain a mapping")
        conf: dict[str, object] = dict(data)
        raw = conf.get('DEFAULT_INVENTORY_PATH')
        if isinstance(raw, str) and raw.strip().lower() == 'builtin':
            conf['DEFAULT_INVENTORY_PATH'] = cls.BUILTIN_INVENTORY_PATH
        else:
            expanded = Files.expand_path(raw)
            if expanded.suffix.lower() not in {'.yml', '.yaml'}:
                raise ValueError(
                    f"[-] Config key 'DEFAULT_INVENTORY_PATH' must be 'builtin' "
                    f"or a path ending in .yml / .yaml"
                )
            conf['DEFAULT_INVENTORY_PATH'] = expanded
        if conf.get('DEFAULT_REPO_DIR') is not None:
            conf['DEFAULT_REPO_DIR'] = Files.expand_path(conf['DEFAULT_REPO_DIR'])
        if conf.get('DEFAULT_PACKAGE_MANAGER'):
            conf['DEFAULT_PACKAGE_MANAGER'] = str(conf['DEFAULT_PACKAGE_MANAGER']).lower()
        preference = conf.get('PREFERENCE')
        if preference is None:
            conf['PREFERENCE'] = list(cls.DEFAULT_PREFERENCE)
        elif isinstance(preference, list) and all(isinstance(item, str) for item in preference):
            invalid = [item for item in preference if item not in cls.VALID_PREFERENCE_TOKENS]
            if invalid:
                raise ValueError(f"[-] Invalid PREFERENCE entries: {', '.join(invalid)}")
            conf['PREFERENCE'] = list(preference)
        else:
            raise TypeError("[-] Config key 'PREFERENCE' must be a list of strings")
        conf['ICON_OVERRIDES'] = Icons.normalize_overrides(conf.get('ICON_OVERRIDES'))
        return conf

    @staticmethod
    def _ensure_config_file() -> None:
        if Config.FILE.exists():
            return
        Config.FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Config.DEFAULT_CONFIG_FILE, Config.FILE)

    @staticmethod
    def _ensure_inventory_file(conf: dict[str, object]) -> None:
        inventory_path = conf['DEFAULT_INVENTORY_PATH']
        if not isinstance(inventory_path, Path):
            raise TypeError("[-] Config key 'DEFAULT_INVENTORY_PATH' must resolve to a path")
        if inventory_path.exists():
            return
        if inventory_path == Config.BUILTIN_INVENTORY_PATH:
            raise FileNotFoundError(f"[-] Built-in inventory not found at '{inventory_path}'")
        inventory_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Config.DEFAULT_INVENTORY_FILE, inventory_path)

    @classmethod
    def load(cls) -> dict[str, object]:
        cls._ensure_config_file()
        conf = cls._normalize_loaded_data(Yaml.load(cls.FILE))
        cls._ensure_inventory_file(conf)
        cls.data.clear()
        cls.data.update(conf)
        return cls.data

    @classmethod
    def get(cls, key: str, default=None):
        return cls.data.get(key, default)

    @classmethod
    def open(cls, read_only: bool = False) -> None:
        Files.open_file(cls.FILE, read_only=read_only)

    @classmethod
    def set_inventory_path(cls, new_path: str | Path) -> None:
        if isinstance(new_path, str) and new_path.strip().lower() == 'builtin':
            display = 'builtin'
        else:
            if isinstance(new_path, str):
                new_path = Path(new_path)
            home = Path.home()
            try:
                display = f'~/{new_path.relative_to(home)}'
            except ValueError:
                display = str(new_path)
        lines = cls.FILE.read_text().splitlines(keepends=True)
        new_line = f'DEFAULT_INVENTORY_PATH: {display}\n'
        replaced = False
        for i, line in enumerate(lines):
            if re.match(r'^DEFAULT_INVENTORY_PATH:', line):
                lines[i] = new_line
                replaced = True
                break
        if not replaced:
            lines.insert(0, new_line)
        cls.FILE.write_text(''.join(lines))


class IconResolver:
    DEFAULT_APP_ICON = '📦'
    DEFAULT_CATEGORY_ICON = '📁'
    DEFAULT_TAG_ICON = '🏷️'

    def __init__(self, overrides: dict | None = None):
        if overrides is None:
            overrides = Config.get('ICON_OVERRIDES', {})
        icon_sets = Icons.icon_sets()
        self._defaults = {
            'app': self.DEFAULT_APP_ICON,
            'category': self.DEFAULT_CATEGORY_ICON,
            'tag': self.DEFAULT_TAG_ICON,
        }
        self._defaults.update(overrides.get('defaults', {}))
        self._app_icons = dict(icon_sets['apps'])
        self._app_icons.update(overrides.get('apps', {}))
        self._category_icons = dict(overrides.get('categories', {}))
        self._tag_icons = dict(overrides.get('tags', {}))
        self._keyword_icons = dict(icon_sets['keywords'])
        self._keyword_icons.update(overrides.get('keywords', {}))

    def _normalize(self, value: str) -> str:
        return value.strip().lower()

    def _tokens(self, *values: str) -> list[str]:
        tokens: list[str] = []
        for value in values:
            if not value:
                continue
            normalized = self._normalize(value)
            tokens.extend(token for token in re.split(r'[^a-z0-9]+', normalized) if token)
        return tokens

    def _exact_override(self, mapping: dict[str, str], value: str) -> tuple[bool, str | None]:
        normalized = self._normalize(value)
        if normalized not in mapping:
            return False, None
        resolved = mapping[normalized]
        return True, resolved or None

    def _keyword_override(self, values: list[str]) -> tuple[bool, str | None]:
        for value in values:
            normalized = self._normalize(value)
            if normalized in self._keyword_icons:
                return True, self._keyword_icons[normalized] or None
            for token in self._tokens(normalized):
                if token in self._keyword_icons:
                    return True, self._keyword_icons[token] or None
        return False, None

    def app_icon(self, app) -> str | None:
        app_names = [app.name, getattr(app, 'candidate', '')]
        for name in app_names:
            found, icon = self._exact_override(self._app_icons, name)
            if found:
                return icon
        found, keyword_icon = self._keyword_override([
            *app_names,
            *getattr(app, 'category', []),
            *getattr(app, 'tags', []),
        ])
        if found:
            return keyword_icon
        return self._defaults.get('app') or None

    def category_icon(self, name: str) -> str | None:
        found, icon = self._exact_override(self._category_icons, name)
        if found:
            return icon
        found, icon = self._keyword_override([name])
        if found:
            return icon
        return self._defaults.get('category') or None

    def tag_icon(self, name: str) -> str | None:
        found, icon = self._exact_override(self._tag_icons, name)
        if found:
            return icon
        found, icon = self._keyword_override([name])
        if found:
            return icon
        return self._defaults.get('tag') or None

    def iconify_label(self, icon: str | None, label: str) -> str:
        if not icon:
            return label
        return f'{icon} {label}'

    def iconify_app_label(self, app, label: str) -> str:
        return self.iconify_label(self.app_icon(app), label)
