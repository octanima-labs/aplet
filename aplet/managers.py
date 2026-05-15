from urllib.parse import quote, urlparse
from pathlib import Path
from typing import Never
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
import fnmatch
import json
import shlex
import shutil
import tarfile
import tempfile
import zipfile
import os

from .inventory import App
from .repositories import GitRepo, GithubRepo, GitlabRepo
from .runners import Script, Probe
from . import utils as ut
import re
import requests
import yaml


logger = ut.get_logger(__name__)


IMPLEMENTED = {
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
    'flatpak',
    'snap',
    'npm',
    'pip',
    'pipx',
}

def _select_installed_manager(installed_mgrs: list[str] | None, default_manager: str | None = None) -> str:
    if not installed_mgrs:
        raise RuntimeError(f"[!] No package manager found. Custom OS?")

    implemented_mgrs = [manager for manager in installed_mgrs if manager in IMPLEMENTED]
    if not implemented_mgrs:
        raise RuntimeError(f"[!] Incompatible package manager '{installed_mgrs[0]}'. Custom OS?")

    preferred_manager = default_manager.lower() if isinstance(default_manager, str) else None
    if preferred_manager in implemented_mgrs:
        return preferred_manager

    if preferred_manager and preferred_manager not in IMPLEMENTED:
        logger.error(f"Configured default package manager '{default_manager}' is not implemented; using '{implemented_mgrs[0]}'")
    elif preferred_manager and preferred_manager not in installed_mgrs:
        logger.error(f"Configured default package manager '{default_manager}' is not installed; using '{implemented_mgrs[0]}'")

    return implemented_mgrs[0]


INSTALLED_MGR: str | None = None


def get_installed_manager() -> str:
    global INSTALLED_MGR
    if INSTALLED_MGR is None:
        INSTALLED_MGR = _select_installed_manager(
            ut.Platform.detect_package_managers(),
            ut.Config.get('DEFAULT_PACKAGE_MANAGER'),
        )
    return INSTALLED_MGR


class _PackageManager:
    
    TARGET_PLARFORMS: list[str] = []
    NAME: str = None
    REQUIRES_ELEVATION: bool = False

    @classmethod
    def _final_cmd(cls, cmd: str) -> str:
        if cls.REQUIRES_ELEVATION and os.name != 'nt' and (not hasattr(os, 'geteuid') or os.geteuid() != 0):
            return f"sudo {cmd}"
        return cmd

    @classmethod
    def _trace_cmd(cls, cmd: str, trace=None) -> None:
        message = trace(cmd) if callable(trace) else trace
        if message:
            logger.info(message)
            return
        logger.trace(f"cmd: {cmd}")

    @classmethod
    def _target_label(cls, targets) -> str:
        return ' '.join(str(target) for target in targets)

    @classmethod
    def _update_trace(cls, cmd: str) -> str:
        return f"Updating {cls.NAME} database ({cmd})"

    @classmethod
    def _install_trace(cls, targets):
        target_label = cls._target_label(targets)
        return lambda cmd: f"Installing {target_label} ({cmd})"

    @classmethod
    def _uninstall_trace(cls, targets):
        target_label = cls._target_label(targets)
        return lambda cmd: f"Removing {target_label} ({cmd})"

    @classmethod
    def _run_cmd(cls, cmd: str, *, trace=None, **kwargs):
        cmd = cls._final_cmd(cmd)
        cls._trace_cmd(cmd, trace=trace)
        return ut.Shell.run(cmd, **kwargs)

    @classmethod
    def _run_read_cmd(cls, cmd: str, **kwargs):
        cls._trace_cmd(cmd)
        return ut.Shell.run(cmd, **kwargs)

    @classmethod
    def available_on_host(cls) -> bool:
        if cls.NAME is None:
            return False
        try:
            installed = ut.Platform.detect_package_managers(announce=False)
        except TypeError:
            installed = ut.Platform.detect_package_managers()
        return cls.NAME in (installed or [])

    def list_gpg() -> Never:
        """List currently installed GPG keys"""
        raise NotImplementedError

    def add_gpg(url: str) -> Never:
        """Adds a GPG key from the package manager configuration"""
        raise NotImplementedError

    def remove_gpg(target: str | int) -> Never:
        """Removes a GPG key from the package manager configuration
        target is str (to look up the gpg, or index obtained from self.list_gpg())
        """
        raise NotImplementedError

    def list_repos() -> Never:
        """Returns active repos defined in the package manager configuration"""
        raise NotImplementedError

    def add_repo(repo: str) -> Never:
        """Adds a new repo to the package manager configuartion"""
        raise NotImplementedError

    def remove_repo(target: str | int) -> Never:
        """Removes a repo from the package manager configuration
        target is str (to look up the repo, or index obtained from self.list_repos())
        """
        raise NotImplementedError

    @classmethod
    def _derive_repo_target(cls, target_mgr: dict[str, str]) -> str | None:
        return target_mgr.get('repo')

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        if target_mgr.get('gpg'):
            cls.add_gpg(target_mgr['gpg'])
        if target_mgr.get('repo'):
            cls.add_repo(target_mgr['repo'])
        cls.update()

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        if not remove_repo:
            return
        repo_target = cls._derive_repo_target(target_mgr)
        if repo_target is None:
            logger.error("Unable to derive repo target")
            return
        cls.remove_repo(repo_target)

    def update() -> Never:
        """Runs the package manager update command"""
        raise NotImplementedError
    
    def install(*targets) -> Never:
        """Runs the package manager command to install target app(s)"""
        raise NotImplementedError

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        return None

    @classmethod
    def install_target(cls, target_mgr: dict[str, str], candidate: str, force: bool = False) -> None:
        cls.install(candidate)
    
    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        raise NotImplementedError

    @classmethod
    def uninstall_target(cls, target_mgr: dict[str, str], candidate: str) -> None:
        cls.uninstall(candidate)


class Apt(_PackageManager):
        
    TARGET_PLARFORMS: list[str] = ['Ubuntu', 'Debian']
    NAME: str = 'apt'
    REQUIRES_ELEVATION: bool = True
    KEYRING_DIR: Path = Path('/etc/apt/keyrings')
    SOURCES_DIR: Path = Path('/etc/apt/sources.list.d')

    def _list_files(directory: Path, pattern: str = '*') -> list[Path]:
        return sorted((path for path in directory.glob(pattern) if path.is_file()), key=lambda path: path.name)

    def _resolve_target(target: str | int, entries: list[Path], label: str) -> Path | None:
        if isinstance(target, int):
            if 1 <= target <= len(entries):
                return entries[target - 1]
        else:
            for entry in entries:
                if entry.name == target:
                    return entry
            target_path = Path(target)
            for entry in entries:
                if entry == target_path:
                    return entry
        logger.warning(f"No {label} match for '{target}'")
        return None

    def list_gpg() -> list[Path]:
        """List currently installed GPG keys"""
        gpg_files = Apt._list_files(Apt.KEYRING_DIR)
        if gpg_files:
            ut.Display.print_list([_.name for _ in gpg_files])
        else:
            ut.Display.print_list()
        return gpg_files

    def add_gpg(url: str):
        """Adds a GPG key from the package manager configuration"""
        gpg_file = Path(urlparse(url).path).stem
        Apt._run_cmd(f'install -d "{Apt.KEYRING_DIR}"')
        Apt._run_cmd(f"wget -qO - {url} | tee \"{Apt.KEYRING_DIR / f'{gpg_file}.asc'}\" > /dev/null")

    def remove_gpg(target: str | int):
        """Removes a GPG key from the package manager configuration
        target is str (to look up the gpg, or index obtained from self.list_gpg())
        """
        gpg_file = Apt._resolve_target(target, Apt._list_files(Apt.KEYRING_DIR), 'GPG key')
        if gpg_file is None:
            return
        ut.Files.remove_path(gpg_file)
        logger.success(f"Removed GPG key '{gpg_file.name}'")

    def list_repos() -> list[Path]:
        """Returns active repos defined in the package manager configuration"""
        repo_files = Apt._list_files(Apt.SOURCES_DIR, '*.sources')
        if repo_files:
            ut.Display.print_list([_.name for _ in repo_files])
        else:
            ut.Display.print_list()
        return repo_files

    def add_repo(repo: str, name: str | None = None):
        """Adds a new repo to the package manager configuartion"""
        if name is None:
            name = urlparse(re.search(r'https://[\w\.]+\.\w+', repo).group()).netloc.split('.')[-2]
        ut.Files.write_text(Apt.SOURCES_DIR / f"{name}.sources", repo, create_parents=True)


    def remove_repo(target: str | int):
        """Removes a repo from the package manager configuration
        target is str (to look up the repo, or index obtained from self.list_repos())
        """
        repo_file = Apt._resolve_target(target, Apt._list_files(Apt.SOURCES_DIR, '*.sources'), 'repo')
        if repo_file is None:
            return
        ut.Files.remove_path(repo_file)
        logger.success(f"Removed repo '{repo_file.name}'")

    def _derive_repo_target(target_mgr: dict[str, str]) -> str | None:
        repo = target_mgr.get('repo')
        if not repo:
            return None
        repo_match = re.search(r'https://[\w\.]+\.\w+', repo)
        if repo_match is None:
            return None
        name = urlparse(repo_match.group()).netloc.split('.')[-2]
        return f'{name}.sources'

    def update():
        """Runs the package manager update command"""
        Apt._run_cmd("apt-get update", trace=Apt._update_trace)
        Apt._run_cmd("apt-get upgrade -y", trace=Apt._update_trace)
    
    
    def install(*targets):
        """Runs the package manager install command to install target app"""
        Apt._run_cmd(f"apt-get install -y {' '.join(targets)}", trace=Apt._install_trace(targets))

    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        Apt._run_cmd(f"apt-get remove -y {' '.join(targets)}", trace=Apt._uninstall_trace(targets))

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        result = cls._run_read_cmd(f'dpkg-query -W -f="${{Status}}" {candidate}', check=False)
        return result.returncode == 0 and 'install ok installed' in result.stdout


class Pacman(_PackageManager):
        
    TARGET_PLARFORMS: list[str] = ['Arch']
    NAME: str = 'pacman'
    REQUIRES_ELEVATION: bool = True
    CONF_FILE: Path = Path('/etc/pacman.conf')
    REPO_INCLUDE_FILE: Path = Path('/etc/pacman.d/aplet.conf')
    LEGACY_REPO_INCLUDE_FILE: Path = Path('/etc/pacman.d/applet.conf')
    REPO_INCLUDE_LINE: str = f'Include = {REPO_INCLUDE_FILE}'
    LEGACY_REPO_INCLUDE_LINE: str = f'Include = {LEGACY_REPO_INCLUDE_FILE}'

    def _list_key_entries() -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        fingerprint: str | None = None
        uid: str | None = None
        for raw_line in Pacman._run_cmd('pacman-key --finger').stdout.splitlines():
            line = raw_line.strip()
            if raw_line.startswith('pub '):
                if fingerprint is not None:
                    entries.append({'fingerprint': fingerprint, 'uid': uid or fingerprint})
                fingerprint = None
                uid = None
                continue
            if fingerprint is None:
                if re.fullmatch(r'(?:[A-F0-9]{4}\s+){9}[A-F0-9]{4}', line, re.IGNORECASE):
                    fingerprint = re.sub(r'\s+', '', line).upper()
                continue
            if uid is None and line.startswith('uid'):
                uid = line.split(']', 1)[-1].strip() if ']' in line else line[3:].strip()
        if fingerprint is not None:
            entries.append({'fingerprint': fingerprint, 'uid': uid or fingerprint})
        return entries

    def _format_key_entry(entry: dict[str, str]) -> str:
        return f"{entry['uid']} <{entry['fingerprint']}>"

    def _resolve_key_target(target: str | int, entries: list[dict[str, str]]) -> dict[str, str] | None:
        if isinstance(target, int):
            if 1 <= target <= len(entries):
                return entries[target - 1]
        else:
            normalized_target = re.sub(r'\s+', '', target).upper()
            for entry in entries:
                if entry['fingerprint'] == normalized_target:
                    return entry
            if re.fullmatch(r'[A-F0-9]+', normalized_target):
                matches = [entry for entry in entries if entry['fingerprint'].endswith(normalized_target)]
                if len(matches) == 1:
                    return matches[0]
                if len(matches) > 1:
                    logger.warning(f"Ambiguous GPG key match for '{target}'")
                    return None
        logger.warning(f"No GPG key match for '{target}'")
        return None

    def _ensure_repo_include() -> None:
        if not Pacman.REPO_INCLUDE_FILE.exists():
            ut.Files.write_text(Pacman.REPO_INCLUDE_FILE, '', create_parents=True)
        conf_text = Pacman.CONF_FILE.read_text() if Pacman.CONF_FILE.exists() else ''
        include_lines = {line.strip() for line in conf_text.splitlines()}
        if Pacman.REPO_INCLUDE_LINE in include_lines:
            return
        if conf_text and not conf_text.endswith('\n'):
            conf_text += '\n'
        conf_text += f"{Pacman.REPO_INCLUDE_LINE}\n"
        ut.Files.write_text(Pacman.CONF_FILE, conf_text)

    def _list_repo_entries() -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for repo_include_file in (Pacman.REPO_INCLUDE_FILE, Pacman.LEGACY_REPO_INCLUDE_FILE):
            if not repo_include_file.exists():
                continue
            entries.extend(Pacman._parse_repo_entries(repo_include_file))
        return entries

    def _parse_repo_entries(repo_include_file: Path) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        current_name: str | None = None
        current_lines: list[str] = []
        for line in repo_include_file.read_text().splitlines(keepends=True):
            match = re.match(r'^\s*\[([^\]]+)\]\s*$', line)
            if match:
                if current_name is not None:
                    entries.append({'name': current_name, 'repo': ''.join(current_lines).strip() + '\n', 'path': repo_include_file})
                current_name = match.group(1)
                current_lines = [line]
            elif current_name is not None:
                current_lines.append(line)
        if current_name is not None:
            entries.append({'name': current_name, 'repo': ''.join(current_lines).strip() + '\n', 'path': repo_include_file})
        return entries

    def _write_repo_entries(entries: list[dict[str, str]], repo_include_file: Path | None = None) -> None:
        if repo_include_file is None:
            repo_include_file = Pacman.REPO_INCLUDE_FILE
        content = '\n'.join(entry['repo'].rstrip('\n') for entry in entries)
        if content:
            content += '\n'
        ut.Files.write_text(repo_include_file, content, create_parents=True)

    def _write_repo_entries_by_path(entries: list[dict[str, str]]) -> None:
        for repo_include_file in (Pacman.REPO_INCLUDE_FILE, Pacman.LEGACY_REPO_INCLUDE_FILE):
            if repo_include_file == Pacman.LEGACY_REPO_INCLUDE_FILE and not repo_include_file.exists():
                continue
            Pacman._write_repo_entries(
                [entry for entry in entries if entry.get('path') == repo_include_file],
                repo_include_file,
            )

    def _resolve_repo_target(target: str | int, entries: list[dict[str, str]]) -> dict[str, str] | None:
        if isinstance(target, int):
            if 1 <= target <= len(entries):
                return entries[target - 1]
        else:
            for entry in entries:
                if entry['name'] == target:
                    return entry
        logger.warning(f"No repo match for '{target}'")
        return None

    def list_gpg() -> list[str]:
        """List currently installed GPG keys"""
        key_entries = Pacman._list_key_entries()
        if key_entries:
            ut.Display.print_list([Pacman._format_key_entry(entry) for entry in key_entries])
        else:
            ut.Display.print_list()
        return [entry['fingerprint'] for entry in key_entries]

    def add_gpg(url: str):
        """Adds a GPG key from the package manager configuration"""
        existing_keys = {entry['fingerprint'] for entry in Pacman._list_key_entries()}
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(urlparse(url).path).suffix or '.gpg')
        temp_path = Path(temp_file.name)
        temp_file.close()
        try:
            ut.Shell.run(f'curl -fsSL "{url}" -o "{temp_path}"')
            Pacman._run_cmd(f'pacman-key --add "{temp_path}"')
            imported_keys = sorted({entry['fingerprint'] for entry in Pacman._list_key_entries()} - existing_keys)
            if len(imported_keys) == 1:
                Pacman._run_cmd(f'pacman-key --lsign-key {imported_keys[0]}')
            elif len(imported_keys) == 0:
                logger.error('Imported key but no new primary key was detected for local signing')
            else:
                logger.error('Imported key but multiple new primary keys were detected; skipped local signing')
        finally:
            temp_path.unlink(missing_ok=True)

    def remove_gpg(target: str | int):
        """Removes a GPG key from the package manager configuration
        target is str (to look up the gpg, or index obtained from self.list_gpg())
        """
        key_entry = Pacman._resolve_key_target(target, Pacman._list_key_entries())
        if key_entry is None:
            return
        Pacman._run_cmd(f"pacman-key --delete {key_entry['fingerprint']}")
        logger.success(f"Removed GPG key '{key_entry['fingerprint']}'")

    def list_repos() -> list[str]:
        """Returns active repos defined in the package manager configuration"""
        repo_entries = Pacman._list_repo_entries()
        if repo_entries:
            ut.Display.print_list([entry['name'] for entry in repo_entries])
        else:
            ut.Display.print_list()
        return [entry['name'] for entry in repo_entries]

    def add_repo(repo: str):
        """Adds a new repo to the package manager configuartion"""
        repo_match = re.search(r'^\s*\[([^\]]+)\]\s*$', repo, re.MULTILINE)
        if repo_match is None:
            raise ValueError('[!] Pacman repo config must include a [repo-name] header')
        repo_entry = {'name': repo_match.group(1), 'repo': repo.strip() + '\n', 'path': Pacman.REPO_INCLUDE_FILE}
        Pacman._ensure_repo_include()
        repo_entries = Pacman._list_repo_entries()
        repo_entries = [entry for entry in repo_entries if entry['name'] != repo_entry['name']]
        repo_entries.append(repo_entry)
        Pacman._write_repo_entries_by_path(repo_entries)


    def remove_repo(target: str | int):
        """Removes a repo from the package manager configuration
        target is str (to look up the repo, or index obtained from self.list_repos())
        """
        repo_entries = Pacman._list_repo_entries()
        repo_entry = Pacman._resolve_repo_target(target, repo_entries)
        if repo_entry is None:
            return
        Pacman._write_repo_entries_by_path([
            entry for entry in repo_entries
            if entry.get('path') != repo_entry.get('path') or entry['name'] != repo_entry['name']
        ])
        logger.success(f"Removed repo '{repo_entry['name']}'")

    def _derive_repo_target(target_mgr: dict[str, str]) -> str | None:
        repo = target_mgr.get('repo')
        if not repo:
            return None
        repo_match = re.search(r'^\s*\[([^\]]+)\]\s*$', repo, re.MULTILINE)
        if repo_match is None:
            return None
        return repo_match.group(1)

    def update():
        """Runs the package manager update command"""
        Pacman._run_cmd("pacman -Syu --noconfirm", trace=Pacman._update_trace)
    
    def install(*targets):
        """Runs the package manager install command to install target app"""
        Pacman._run_cmd(f"pacman -S --noconfirm --needed {' '.join(targets)}", trace=Pacman._install_trace(targets))

    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        Pacman._run_cmd(f"pacman -Rns --noconfirm {' '.join(targets)}", trace=Pacman._uninstall_trace(targets))

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        return cls._run_read_cmd(f'pacman -Q {candidate}', check=False).returncode == 0


class Yay(_PackageManager):

    TARGET_PLARFORMS: list[str] = ['Arch']
    NAME: str = 'yay'

    @classmethod
    def list_gpg(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_gpg(cls, url: str):
        return

    @classmethod
    def remove_gpg(cls, target: str | int):
        return

    @classmethod
    def list_repos(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_repo(cls, repo: str):
        return

    @classmethod
    def remove_repo(cls, target: str | int):
        return

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        return

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        return

    @classmethod
    def update(cls):
        cls._run_cmd('yay -Syu --noconfirm', trace=cls._update_trace)

    @classmethod
    def install(cls, *targets):
        if len(targets) == 0:
            return
        cls._run_cmd(f"yay -S --noconfirm --needed {' '.join(targets)}", trace=cls._install_trace(targets))

    @classmethod
    def install_target(cls, target_mgr: dict[str, str], candidate: str, force: bool = False) -> None:
        cls.install(candidate)

    @classmethod
    def uninstall(cls, *targets) -> Never:
        if len(targets) == 0:
            return
        cls._run_cmd(f"yay -Rns --noconfirm {' '.join(targets)}", trace=cls._uninstall_trace(targets))

    @classmethod
    def uninstall_target(cls, target_mgr: dict[str, str], candidate: str) -> None:
        cls.uninstall(candidate)

    @classmethod
    def list_installed(cls) -> list[str]:
        result = cls._run_cmd('yay -Qq', check=False)
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if names:
            ut.Display.print_list(names)
        else:
            ut.Display.print_list()
        return names

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        return cls._run_cmd(f'pacman -Q {candidate}', check=False).returncode == 0


class _RpmRepoManager(_PackageManager):

    REQUIRES_ELEVATION: bool = True
    REPO_DIR: Path = Path('/etc/yum.repos.d')
    REPO_FILE_PREFIX: str = 'aplet-'
    LEGACY_REPO_FILE_PREFIX: str = 'applet-'

    @classmethod
    def _list_rpm_gpg_entries(cls) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        query = "rpm -qa 'gpg-pubkey*' --qf '%{NAME}-%{VERSION}-%{RELEASE}\t%{SUMMARY}\n'"
        for line in cls._run_cmd(query).stdout.splitlines():
            if not line.strip():
                continue
            package, summary = (line.split('\t', 1) + [''])[:2]
            entries.append({'package': package.strip(), 'summary': summary.strip()})
        return sorted(entries, key=lambda entry: entry['package'])

    @staticmethod
    def _format_rpm_gpg_entry(entry: dict[str, str]) -> str:
        return f"{entry['package']} {entry['summary']}".rstrip()

    @classmethod
    def _resolve_rpm_gpg_target(cls, target: str | int, entries: list[dict[str, str]]) -> dict[str, str] | None:
        if isinstance(target, int):
            if 1 <= target <= len(entries):
                return entries[target - 1]
        else:
            for entry in entries:
                if entry['package'] == target:
                    return entry
        logger.warning(f"No GPG key match for '{target}'")
        return None

    @classmethod
    def _repo_file_name_from_url(cls, repo: str) -> str:
        parsed = urlparse(repo)
        repo_name = Path(parsed.path).name
        if not parsed.scheme or not repo_name:
            raise ValueError('[!] RPM repo config must be a repository URL')
        if not repo_name.endswith('.repo'):
            repo_name = f"{repo_name}.repo"
        if not repo_name.startswith(cls.REPO_FILE_PREFIX):
            repo_name = f"{cls.REPO_FILE_PREFIX}{repo_name}"
        return repo_name

    @classmethod
    def _repo_target_names(cls, target: str) -> set[str]:
        target_name = Path(target).name
        names = {target, target_name}
        if target_name.startswith(cls.REPO_FILE_PREFIX):
            names.add(f"{cls.LEGACY_REPO_FILE_PREFIX}{target_name.removeprefix(cls.REPO_FILE_PREFIX)}")
        if target_name.startswith(cls.LEGACY_REPO_FILE_PREFIX):
            names.add(f"{cls.REPO_FILE_PREFIX}{target_name.removeprefix(cls.LEGACY_REPO_FILE_PREFIX)}")
        return names

    @classmethod
    def _list_repo_files(cls) -> list[Path]:
        if not cls.REPO_DIR.exists():
            return []
        patterns = {f"{cls.REPO_FILE_PREFIX}*.repo", f"{cls.LEGACY_REPO_FILE_PREFIX}*.repo"}
        return sorted(
            {path for pattern in patterns for path in cls.REPO_DIR.glob(pattern) if path.is_file()},
            key=lambda path: path.name,
        )

    @classmethod
    def _parse_repo_sections(cls, path: Path) -> list[dict[str, str]]:
        sections: list[dict[str, str]] = []
        current_name: str | None = None
        current_lines: list[str] = []
        preamble: list[str] = []

        for line in path.read_text().splitlines(keepends=True):
            match = re.match(r'^\s*\[([^\]]+)\]\s*$', line)
            if match:
                if current_name is not None:
                    sections.append({'name': current_name, 'content': ''.join(current_lines).strip() + '\n'})
                current_name = match.group(1)
                current_lines = preamble + [line]
                preamble = []
            elif current_name is None:
                preamble.append(line)
            else:
                current_lines.append(line)

        if current_name is not None:
            sections.append({'name': current_name, 'content': ''.join(current_lines).strip() + '\n'})
        return sections

    @classmethod
    def _list_repo_entries(cls) -> list[dict[str, object]]:
        return [
            {'path': path, 'file': path.name, 'sections': cls._parse_repo_sections(path)}
            for path in cls._list_repo_files()
        ]

    @staticmethod
    def _format_repo_entry(entry: dict[str, object]) -> str:
        repo_ids = ', '.join(section['name'] for section in entry['sections'])
        return f"{entry['file']}: {repo_ids}" if repo_ids else str(entry['file'])

    @classmethod
    def _write_repo_sections(cls, path: Path, sections: list[dict[str, str]]) -> None:
        content = '\n'.join(section['content'].rstrip('\n') for section in sections)
        if content:
            content += '\n'
        ut.Files.write_text(path, content, create_parents=True)

    @classmethod
    def _resolve_repo_target(cls, target: str | int, entries: list[dict[str, object]]) -> dict[str, object] | None:
        if isinstance(target, int):
            if 1 <= target <= len(entries):
                return {'entry': entries[target - 1], 'section': None}
        else:
            target_names = cls._repo_target_names(target)
            for entry in entries:
                if entry['file'] in target_names:
                    return {'entry': entry, 'section': None}

            matches = []
            for entry in entries:
                for section in entry['sections']:
                    if section['name'] == target:
                        matches.append({'entry': entry, 'section': section})

            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                logger.warning(f"Ambiguous repo match for '{target}'")
                return None

        logger.warning(f"No repo match for '{target}'")
        return None

    @classmethod
    def list_gpg(cls) -> list[str]:
        """List currently installed GPG keys"""
        key_entries = cls._list_rpm_gpg_entries()
        if key_entries:
            ut.Display.print_list([cls._format_rpm_gpg_entry(entry) for entry in key_entries])
        else:
            ut.Display.print_list()
        return [entry['package'] for entry in key_entries]

    @classmethod
    def add_gpg(cls, url: str):
        """Adds a GPG key from the package manager configuration"""
        cls._run_cmd(f'rpm -v --import "{url}"')

    @classmethod
    def remove_gpg(cls, target: str | int):
        """Removes a GPG key from the package manager configuration
        target is str (to look up the gpg, or index obtained from self.list_gpg())
        """
        key_entry = cls._resolve_rpm_gpg_target(target, cls._list_rpm_gpg_entries())
        if key_entry is None:
            return
        cls._run_cmd(f"rpm -e {key_entry['package']}")
        logger.success(f"Removed GPG key '{key_entry['package']}'")

    @classmethod
    def list_repos(cls) -> list[str]:
        """Returns active repos defined in the package manager configuration"""
        repo_entries = cls._list_repo_entries()
        if repo_entries:
            ut.Display.print_list([cls._format_repo_entry(entry) for entry in repo_entries])
        else:
            ut.Display.print_list()
        return [cls._format_repo_entry(entry) for entry in repo_entries]

    @classmethod
    def add_repo(cls, repo: str):
        """Adds a new repo to the package manager configuartion"""
        repo_file = cls.REPO_DIR / cls._repo_file_name_from_url(repo)
        cls._run_cmd(f'install -d "{cls.REPO_DIR}"')
        cls._run_cmd(f'curl -fsSL "{repo}" -o "{repo_file}"')

    @classmethod
    def remove_repo(cls, target: str | int):
        """Removes a repo from the package manager configuration
        target is str (to look up the repo, or index obtained from self.list_repos())
        """
        repo_target = cls._resolve_repo_target(target, cls._list_repo_entries())
        if repo_target is None:
            return

        repo_entry = repo_target['entry']
        section = repo_target['section']
        if section is None:
            ut.Files.remove_path(repo_entry['path'])
            logger.success(f"Removed repo file '{repo_entry['file']}'")
            return

        remaining_sections = [entry for entry in repo_entry['sections'] if entry['name'] != section['name']]
        if remaining_sections:
            cls._write_repo_sections(repo_entry['path'], remaining_sections)
        else:
            ut.Files.remove_path(repo_entry['path'])
        logger.success(f"Removed repo '{section['name']}'")

    @classmethod
    def _derive_repo_target(cls, target_mgr: dict[str, str]) -> str | None:
        repo = target_mgr.get('repo')
        if not repo:
            return None
        return cls._repo_file_name_from_url(repo)

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        return cls._run_read_cmd(f'rpm -q {candidate}', check=False).returncode == 0


class Yum(_RpmRepoManager):
        
    TARGET_PLARFORMS: list[str] = ['CentOS']
    NAME: str = 'yum'

    def update():
        """Runs the package manager update command"""
        Yum._run_cmd("yum update -y", trace=Yum._update_trace)
    
    def install(*targets):
        """Runs the package manager install command to install target app"""
        Yum._run_cmd(f"yum install -y {' '.join(targets)}", trace=Yum._install_trace(targets))
    
    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        Yum._run_cmd(f"yum remove -y {' '.join(targets)}", trace=Yum._uninstall_trace(targets))


class Dnf(_RpmRepoManager):
        
    TARGET_PLARFORMS: list[str] = ['Fedora']
    NAME: str = 'dnf'

    def update():
        """Runs the package manager update command"""
        Dnf._run_cmd("dnf upgrade --refresh -y", trace=Dnf._update_trace)
    
    def install(*targets):
        """Runs the package manager install command to install target app"""
        Dnf._run_cmd(f"dnf install -y {' '.join(targets)}", trace=Dnf._install_trace(targets))
    
    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        Dnf._run_cmd(f"dnf remove -y {' '.join(targets)}", trace=Dnf._uninstall_trace(targets))


class Zypper(_RpmRepoManager):
        
    TARGET_PLARFORMS: list[str] = ['openSUSE']
    NAME: str = 'zypper'
    REPO_DIR: Path = Path('/etc/zypp/repos.d')

    def update():
        """Runs the package manager update command"""
        Zypper._run_cmd('zypper --non-interactive update', trace=Zypper._update_trace)
    
    def install(*targets):
        """Runs the package manager install command to install target app"""
        Zypper._run_cmd(f"zypper --non-interactive install {' '.join(targets)}", trace=Zypper._install_trace(targets))
    
    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        Zypper._run_cmd(f"zypper --non-interactive remove {' '.join(targets)}", trace=Zypper._uninstall_trace(targets))


class Brew(_PackageManager):

    TARGET_PLARFORMS: list[str] = ['macOS', 'Linux']
    NAME: str = 'brew'

    def _list_taps() -> list[str]:
        return sorted(line.strip() for line in Brew._run_cmd('brew tap').stdout.splitlines() if line.strip())

    def _resolve_tap_target(target: str | int, taps: list[str]) -> str | None:
        if isinstance(target, int):
            if 1 <= target <= len(taps):
                return taps[target - 1]
        else:
            for tap in taps:
                if tap == target:
                    return tap
        logger.warning(f"No repo match for '{target}'")
        return None

    def list_gpg() -> list[str]:
        """List currently installed GPG keys"""
        ut.Display.print_list()
        return []

    def add_gpg(url: str):
        """Adds a GPG key from the package manager configuration"""
        return

    def remove_gpg(target: str | int):
        """Removes a GPG key from the package manager configuration
        target is str (to look up the gpg, or index obtained from self.list_gpg())
        """
        return

    def list_repos() -> list[str]:
        """Returns active repos defined in the package manager configuration"""
        taps = Brew._list_taps()
        if taps:
            ut.Display.print_list(taps)
        else:
            ut.Display.print_list()
        return taps

    def add_repo(repo: str):
        """Adds a new repo to the package manager configuartion"""
        if not repo:
            return
        Brew._run_cmd(f'brew tap "{repo}"')

    def remove_repo(target: str | int):
        """Removes a repo from the package manager configuration
        target is str (to look up the repo, or index obtained from self.list_repos())
        """
        tap = Brew._resolve_tap_target(target, Brew._list_taps())
        if tap is None:
            return
        Brew._run_cmd(f'brew untap "{tap}"')
        logger.success(f"Removed repo '{tap}'")

    def _derive_repo_target(target_mgr: dict[str, str]) -> str | None:
        return target_mgr.get('repo')

    def update():
        """Runs the package manager update command"""
        Brew._run_cmd('brew update', trace=Brew._update_trace)

    def install(*targets):
        """Runs the package manager command to install target app(s)"""
        Brew._run_cmd(f"brew install {' '.join(targets)}", trace=Brew._install_trace(targets))

    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        Brew._run_cmd(f"brew uninstall {' '.join(targets)}", trace=Brew._uninstall_trace(targets))

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        tokens = shlex.split(candidate)
        if tokens and tokens[0] == '--cask' and len(tokens) > 1:
            return cls._run_cmd(f'brew list --cask {tokens[1]}', check=False).returncode == 0
        target = tokens[-1] if tokens else candidate
        return cls._run_cmd(f'brew list --formula {target}', check=False).returncode == 0


class _WindowsPackageManager(_PackageManager):

    TARGET_PLARFORMS: list[str] = ['Windows']

    def list_gpg() -> list[str]:
        """List currently installed GPG keys"""
        ut.Display.print_list()
        return []

    def add_gpg(url: str):
        """Adds a GPG key from the package manager configuration"""
        return

    def remove_gpg(target: str | int):
        """Removes a GPG key from the package manager configuration
        target is str (to look up the gpg, or index obtained from self.list_gpg())
        """
        return

    def _resolve_named_target(target: str | int, entries: list[dict[str, str]], label: str) -> dict[str, str] | None:
        if isinstance(target, int):
            if 1 <= target <= len(entries):
                return entries[target - 1]
        else:
            for entry in entries:
                if entry['name'] == target:
                    return entry
        logger.warning(f"No {label} match for '{target}'")
        return None


class Choco(_WindowsPackageManager):

    NAME: str = 'choco'

    def _list_sources() -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for line in Choco._run_cmd('choco source list --limit-output').stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split('|')
            name = parts[0].strip()
            source = parts[1].strip() if len(parts) > 1 else ''
            entries.append({'name': name, 'source': source})
        return sorted(entries, key=lambda entry: entry['name'])

    def list_repos() -> list[str]:
        """Returns active repos defined in the package manager configuration"""
        sources = Choco._list_sources()
        labels = [f"{entry['name']}: {entry['source']}" if entry['source'] else entry['name'] for entry in sources]
        if labels:
            ut.Display.print_list(labels)
        else:
            ut.Display.print_list()
        return labels

    def add_repo(repo: str):
        """Adds a new repo to the package manager configuartion"""
        if not repo:
            return
        source_name = Path(urlparse(repo).path.rstrip('/')).name or urlparse(repo).netloc.split('.')[0]
        if any(entry['name'] == source_name for entry in Choco._list_sources()):
            return
        Choco._run_cmd(f'choco source add -n="{source_name}" -s="{repo}"')

    def remove_repo(target: str | int):
        """Removes a repo from the package manager configuration
        target is str (to look up the repo, or index obtained from self.list_repos())
        """
        source = Choco._resolve_named_target(target, Choco._list_sources(), 'repo')
        if source is None:
            return
        Choco._run_cmd(f"choco source remove -n=\"{source['name']}\"")
        logger.success(f"Removed repo '{source['name']}'")

    def _derive_repo_target(target_mgr: dict[str, str]) -> str | None:
        return target_mgr.get('source_name')

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        source_name = target_mgr.get('source_name')
        source_url = target_mgr.get('source_url')
        if source_name and source_url and not any(entry['name'] == source_name for entry in cls._list_sources()):
            cls._run_cmd(f'choco source add -n="{source_name}" -s="{source_url}"')
        cls.update()

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        if not remove_repo:
            return
        source_name = target_mgr.get('source_name')
        if not source_name:
            logger.error("Unable to derive repo target")
            return
        cls.remove_repo(source_name)

    def update():
        """Runs the package manager update command"""
        return

    def install(*targets):
        """Runs the package manager command to install target app(s)"""
        Choco._run_cmd(f"choco install -y {' '.join(targets)}", trace=Choco._install_trace(targets))

    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        Choco._run_cmd(f"choco uninstall -y {' '.join(targets)}", trace=Choco._uninstall_trace(targets))

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        result = cls._run_cmd(f'choco list --local-only --exact "{candidate}" --limit-output', check=False)
        if result.returncode != 0:
            return False
        return any(line.split('|', 1)[0].strip().lower() == candidate.lower() for line in result.stdout.splitlines() if line.strip())


class Scoop(_WindowsPackageManager):

    NAME: str = 'scoop'

    def _list_buckets() -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for line in Scoop._run_cmd('scoop bucket list').stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.lower().startswith('name') or set(stripped) <= {'-', ' '}:
                continue
            parts = stripped.split()
            name = parts[0]
            source = ' '.join(parts[1:])
            entries.append({'name': name, 'source': source})
        return sorted(entries, key=lambda entry: entry['name'])

    def list_repos() -> list[str]:
        """Returns active repos defined in the package manager configuration"""
        buckets = Scoop._list_buckets()
        labels = [f"{entry['name']}: {entry['source']}" if entry['source'] else entry['name'] for entry in buckets]
        if labels:
            ut.Display.print_list(labels)
        else:
            ut.Display.print_list()
        return labels

    def add_repo(repo: str):
        """Adds a new repo to the package manager configuartion"""
        if not repo:
            return
        if any(entry['name'] == repo for entry in Scoop._list_buckets()):
            return
        Scoop._run_cmd(f'scoop bucket add "{repo}"')

    def remove_repo(target: str | int):
        """Removes a repo from the package manager configuration
        target is str (to look up the repo, or index obtained from self.list_repos())
        """
        bucket = Scoop._resolve_named_target(target, Scoop._list_buckets(), 'repo')
        if bucket is None:
            return
        Scoop._run_cmd(f"scoop bucket rm \"{bucket['name']}\"")
        logger.success(f"Removed repo '{bucket['name']}'")

    def _derive_repo_target(target_mgr: dict[str, str]) -> str | None:
        return target_mgr.get('bucket_name')

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        bucket_name = target_mgr.get('bucket_name')
        bucket_url = target_mgr.get('bucket_url')
        if bucket_name and any(entry['name'] == bucket_name for entry in cls._list_buckets()):
            pass
        elif bucket_name and bucket_url:
            cls._run_cmd(f'scoop bucket add "{bucket_name}" "{bucket_url}"')
        elif bucket_name:
            cls._run_cmd(f'scoop bucket add "{bucket_name}"')
        cls.update()

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        if not remove_repo:
            return
        bucket_name = target_mgr.get('bucket_name')
        if not bucket_name:
            logger.error("Unable to derive repo target")
            return
        cls.remove_repo(bucket_name)

    def update():
        """Runs the package manager update command"""
        Scoop._run_cmd('scoop update', trace=Scoop._update_trace)

    def install(*targets):
        """Runs the package manager command to install target app(s)"""
        Scoop._run_cmd(f"scoop install {' '.join(targets)}", trace=Scoop._install_trace(targets))

    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        Scoop._run_cmd(f"scoop uninstall {' '.join(targets)}", trace=Scoop._uninstall_trace(targets))

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        return cls._run_cmd(f'scoop list {candidate}', check=False).returncode == 0


class Flatpak(_PackageManager):

    TARGET_PLARFORMS: list[str] = ['Linux']
    NAME: str = 'flatpak'
    DEFAULT_REMOTE_NAME: str = 'flathub'
    DEFAULT_REPO: str = 'https://flathub.org/repo/flathub.flatpakrepo'

    @staticmethod
    def _scope_flag(user: bool) -> str:
        return '--user' if user else '--system'

    @classmethod
    def _run_flatpak_cmd(cls, cmd: str, *, user: bool = False, mutate: bool = False, trace=None):
        if mutate and not user and os.name != 'nt' and (not hasattr(os, 'geteuid') or os.geteuid() != 0):
            cmd = f"sudo {cmd}"
        cls._trace_cmd(cmd, trace=trace)
        return ut.Shell.run(cmd)

    @staticmethod
    def _split_columns(line: str, expected_fields: int) -> list[str]:
        parts = line.rstrip('\n').split('\t')
        if len(parts) == 1:
            parts = re.split(r'\s{2,}', line.strip(), maxsplit=expected_fields - 1)
        if len(parts) < expected_fields:
            parts.extend([''] * (expected_fields - len(parts)))
        return [part.strip() for part in parts[:expected_fields]]

    @classmethod
    def _normalize_target_mgr(
        cls,
        target_mgr: dict[str, str],
        *,
        candidate: str | None = None,
        require_candidate: bool = True,
    ) -> dict[str, object]:
        repo = target_mgr.get('repo')
        remote_name = target_mgr.get('remote_name')
        if remote_name is None:
            if repo is None or repo == cls.DEFAULT_REPO:
                remote_name = cls.DEFAULT_REMOTE_NAME
            else:
                raise ValueError("[-] Flatpak custom repo entries require 'remote_name'")
        effective_candidate = candidate if candidate is not None else target_mgr.get('candidate')
        if require_candidate and not effective_candidate:
            raise ValueError("[-] Flatpak manager entries require 'candidate'")
        return {
            'candidate': effective_candidate,
            'remote_name': remote_name,
            'repo': repo or cls.DEFAULT_REPO,
            'user': bool(target_mgr.get('user', False)),
            'no_gpg_verify': bool(target_mgr.get('no_gpg_verify', False)),
            'explicit_remote': any(key in target_mgr for key in ('remote_name', 'repo')),
        }

    @classmethod
    def _list_remote_entries(cls, user: bool = False) -> list[dict[str, str]]:
        output = cls._run_flatpak_cmd(
            f"flatpak remotes {cls._scope_flag(user)} --columns=name,url,options",
            user=user,
            mutate=False,
        ).stdout
        entries: list[dict[str, str]] = []
        for raw_line in output.splitlines():
            if not raw_line.strip():
                continue
            name, url, options = cls._split_columns(raw_line, 3)
            if name.lower() == 'name':
                continue
            entries.append({'name': name, 'url': url, 'options': options})
        return entries

    @staticmethod
    def _resolve_remote_target(target: str | int, entries: list[dict[str, str]]) -> dict[str, str] | None:
        if isinstance(target, int):
            if 1 <= target <= len(entries):
                return entries[target - 1]
        else:
            for entry in entries:
                if entry['name'] == target:
                    return entry
        logger.warning(f"No repo match for '{target}'")
        return None

    @classmethod
    def list_gpg(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_gpg(cls, url: str):
        return

    @classmethod
    def remove_gpg(cls, target: str | int):
        return

    @classmethod
    def list_repos(cls, user: bool = False) -> list[str]:
        entries = cls._list_remote_entries(user=user)
        labels = [f"{entry['name']}: {entry['url']}" if entry['url'] else entry['name'] for entry in entries]
        if labels:
            ut.Display.print_list(labels)
        else:
            ut.Display.print_list()
        return [entry['name'] for entry in entries]

    @classmethod
    def add_repo(
        cls,
        repo: str,
        name: str | None = None,
        user: bool = False,
        no_gpg_verify: bool = False,
    ):
        if not repo:
            return
        if name is None:
            if repo != cls.DEFAULT_REPO:
                raise ValueError("[-] Flatpak custom repo entries require 'remote_name'")
            name = cls.DEFAULT_REMOTE_NAME
        if any(entry['name'] == name for entry in cls._list_remote_entries(user=user)):
            return
        verify_flag = ' --no-gpg-verify' if no_gpg_verify else ''
        cls._run_flatpak_cmd(
            f'flatpak remote-add --if-not-exists {cls._scope_flag(user)}{verify_flag} {name} "{repo}"',
            user=user,
            mutate=True,
        )

    @classmethod
    def remove_repo(cls, target: str | int, user: bool = False):
        entry = cls._resolve_remote_target(target, cls._list_remote_entries(user=user))
        if entry is None:
            return
        cls._run_flatpak_cmd(
            f'flatpak remote-delete {cls._scope_flag(user)} "{entry["name"]}"',
            user=user,
            mutate=True,
        )
        logger.success(f"Removed repo '{entry['name']}'")

    @classmethod
    def list_apps(cls, user: bool = False) -> list[str]:
        output = cls._run_flatpak_cmd(
            f"flatpak list --app {cls._scope_flag(user)} --columns=application,origin,installation",
            user=user,
            mutate=False,
        ).stdout
        entries: list[dict[str, str]] = []
        for raw_line in output.splitlines():
            if not raw_line.strip():
                continue
            application, origin, installation = cls._split_columns(raw_line, 3)
            if application.lower() == 'application':
                continue
            entries.append({'application': application, 'origin': origin, 'installation': installation})
        labels = [
            f"{entry['application']} ({entry['origin'] or 'unknown'}, {entry['installation'] or ('user' if user else 'system')})"
            for entry in entries
        ]
        if labels:
            ut.Display.print_list(labels)
        else:
            ut.Display.print_list()
        return [entry['application'] for entry in entries]

    @classmethod
    def _derive_repo_target(cls, target_mgr: dict[str, str]) -> str | None:
        config = cls._normalize_target_mgr(target_mgr, require_candidate=False)
        return str(config['remote_name'])

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        config = cls._normalize_target_mgr(target_mgr, require_candidate=False)
        cls.add_repo(
            str(config['repo']),
            name=str(config['remote_name']),
            user=bool(config['user']),
            no_gpg_verify=bool(config['no_gpg_verify']),
        )
        cls.update(user=bool(config['user']))

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        if not remove_repo:
            return
        config = cls._normalize_target_mgr(target_mgr, require_candidate=False)
        if not config['explicit_remote']:
            return
        cls.remove_repo(str(config['remote_name']), user=bool(config['user']))

    @classmethod
    def update(cls, *targets, user: bool = False):
        cmd = f"flatpak update --assumeyes --noninteractive {cls._scope_flag(user)}"
        if targets:
            cmd = f"{cmd} {' '.join(targets)}"
        cls._run_flatpak_cmd(cmd, user=user, mutate=True, trace=cls._update_trace)

    @classmethod
    def install(cls, *targets, remote_name: str = DEFAULT_REMOTE_NAME, user: bool = False):
        if len(targets) == 0:
            return
        cls._run_flatpak_cmd(
            f"flatpak install --assumeyes --noninteractive {cls._scope_flag(user)} {remote_name} {' '.join(targets)}",
            user=user,
            mutate=True,
            trace=cls._install_trace(targets),
        )

    @classmethod
    def install_target(cls, target_mgr: dict[str, str], candidate: str, force: bool = False) -> None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        cls.install(str(config['candidate']), remote_name=str(config['remote_name']), user=bool(config['user']))

    @classmethod
    def uninstall(cls, *targets, user: bool = False) -> Never:
        if len(targets) == 0:
            return
        cls._run_flatpak_cmd(
            f"flatpak uninstall --assumeyes --noninteractive {cls._scope_flag(user)} {' '.join(targets)}",
            user=user,
            mutate=True,
            trace=cls._uninstall_trace(targets),
        )

    @classmethod
    def uninstall_target(cls, target_mgr: dict[str, str], candidate: str) -> None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        cls.uninstall(str(config['candidate']), user=bool(config['user']))

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        output = cls._run_flatpak_cmd(
            f"flatpak list --app {cls._scope_flag(bool(config['user']))} --columns=application",
            user=bool(config['user']),
            mutate=False,
        ).stdout
        installed = [line.strip() for line in output.splitlines() if line.strip() and line.strip().lower() != 'application']
        return str(config['candidate']) in installed


class Npm(_PackageManager):

    TARGET_PLARFORMS: list[str] = ['Linux', 'macOS', 'Windows']
    NAME: str = 'npm'

    @staticmethod
    def _global_flag(global_install: bool) -> str:
        return '-g ' if global_install else ''

    @classmethod
    def list_gpg(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_gpg(cls, url: str):
        return

    @classmethod
    def remove_gpg(cls, target: str | int):
        return

    @classmethod
    def list_repos(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_repo(cls, repo: str):
        return

    @classmethod
    def remove_repo(cls, target: str | int):
        return

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        return

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        return

    @classmethod
    def update(cls, *targets, global_install: bool = True):
        cmd = f"npm update {cls._global_flag(global_install)}"
        if targets:
            cmd = f"{cmd}{' '.join(targets)}"
        cls._run_cmd(cmd.rstrip(), trace=cls._update_trace)

    @classmethod
    def install(cls, *targets, global_install: bool = True):
        if len(targets) == 0:
            return
        cmd = f"npm install {cls._global_flag(global_install)}{' '.join(targets)}"
        cls._run_cmd(cmd.rstrip(), trace=cls._install_trace(targets))

    @classmethod
    def install_target(cls, target_mgr: dict[str, str], candidate: str, force: bool = False) -> None:
        cls.install(candidate, global_install=True)

    @classmethod
    def uninstall(cls, *targets, global_install: bool = True) -> Never:
        if len(targets) == 0:
            return
        cmd = f"npm uninstall {cls._global_flag(global_install)}{' '.join(targets)}"
        cls._run_cmd(cmd.rstrip(), trace=cls._uninstall_trace(targets))

    @classmethod
    def uninstall_target(cls, target_mgr: dict[str, str], candidate: str) -> None:
        cls.uninstall(candidate, global_install=True)

    @classmethod
    def list_installed(cls, global_install: bool = True) -> list[str]:
        cmd = f"npm ls {cls._global_flag(global_install)}--depth=0 --json"
        result = cls._run_cmd(cmd.rstrip(), check=False)
        data = json.loads(result.stdout or '{}')
        dependencies = data.get('dependencies') or {}
        names = sorted(dependencies)
        labels = [
            f"{name}@{dependencies[name].get('version')}" if dependencies[name].get('version') else name
            for name in names
        ]
        if labels:
            ut.Display.print_list(labels)
        else:
            ut.Display.print_list()
        return names

    @classmethod
    def _installed_name(cls, candidate: str) -> str:
        if candidate.startswith('@') and '@' in candidate[1:]:
            return candidate.rsplit('@', 1)[0]
        if not candidate.startswith('@') and '@' in candidate:
            return candidate.split('@', 1)[0]
        return candidate

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        cmd = f"npm ls {cls._global_flag(True)}--depth=0 --json"
        result = cls._run_cmd(cmd.rstrip(), check=False)
        data = json.loads(result.stdout or '{}')
        dependencies = data.get('dependencies') or {}
        return cls._installed_name(candidate) in dependencies


class Pip(_PackageManager):

    TARGET_PLARFORMS: list[str] = ['Linux', 'macOS', 'Windows']
    NAME: str = 'pip'
    VERSION_OPERATORS = ('==', '>=', '<=', '~=', '!=', '<', '>')

    @classmethod
    def _normalize_target_mgr(
        cls,
        target_mgr: dict[str, str],
        *,
        candidate: str | None = None,
        require_candidate: bool = True,
    ) -> dict[str, str | None]:
        effective_candidate = candidate if candidate is not None else target_mgr.get('candidate')
        if require_candidate and not effective_candidate:
            raise ValueError("[-] Pip manager entries require 'candidate'")

        version = target_mgr.get('version')
        if version is not None and not isinstance(version, str):
            raise TypeError("[-] Pip manager field 'version' must be a string")

        venv = target_mgr.get('venv')
        if venv is not None and not isinstance(venv, str):
            raise TypeError("[-] Pip manager field 'venv' must be a string")

        return {
            'candidate': effective_candidate,
            'version': version,
            'venv': venv,
        }

    @classmethod
    def _target_has_version_specifier(cls, target: str) -> bool:
        return any(operator in target for operator in cls.VERSION_OPERATORS)

    @classmethod
    def _target_for_install(cls, target: str, version: str | None = None) -> str:
        if version is None or cls._target_has_version_specifier(target):
            return target
        return f'{target}=={version}'

    @classmethod
    def _target_with_version_specifier(cls, target: str, version_specifier: str | None = None) -> str:
        if version_specifier is None or cls._target_has_version_specifier(target):
            return target
        return f'{cls._package_name_for_show(target)}{version_specifier}'

    @classmethod
    def _targets_for_install(cls, targets: tuple[str, ...], version: str | None = None) -> list[str]:
        if len(targets) == 1:
            return [cls._target_for_install(targets[0], version=version)]
        return list(targets)

    @classmethod
    def _package_name_for_show(cls, target: str) -> str:
        package_name = target
        for operator in cls.VERSION_OPERATORS:
            if operator in package_name:
                package_name = package_name.split(operator, 1)[0]
                break
        return package_name.strip()

    @classmethod
    def _venv_path(cls, venv: str | None) -> Path | None:
        return ut.Files.expand_path(venv) if venv is not None else None

    @classmethod
    def _ensure_venv(cls, venv: str | None) -> Path | None:
        venv_path = cls._venv_path(venv)
        if venv_path is None or venv_path.exists():
            return venv_path
        venv_path.parent.mkdir(parents=True, exist_ok=True)
        cls._run_cmd(f"python -m venv {shlex.quote(str(venv_path))}")
        return venv_path

    @classmethod
    def _run_pip_cmd(cls, pip_cmd: str, *, venv: str | None = None, ensure_venv: bool = False, trace=None, **kwargs):
        venv_path = cls._ensure_venv(venv) if ensure_venv else cls._venv_path(venv)
        if venv_path is None:
            return cls._run_cmd(pip_cmd, trace=trace, **kwargs)
        if os.name == 'nt':
            activate_path = f"{str(venv_path).rstrip('/\\')}\\Scripts\\Activate.ps1"
            cmd = f"& {shlex.quote(activate_path)}; {pip_cmd}"
            cls._trace_cmd(cmd, trace=trace)
            return ut.Shell.run(cmd, **kwargs)
        activate_path = venv_path / 'bin' / 'activate'
        return cls._run_cmd(f"source {shlex.quote(str(activate_path))} && {pip_cmd}", trace=trace, **kwargs)

    @classmethod
    def list_gpg(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_gpg(cls, url: str):
        return

    @classmethod
    def remove_gpg(cls, target: str | int):
        return

    @classmethod
    def list_repos(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_repo(cls, repo: str):
        return

    @classmethod
    def remove_repo(cls, target: str | int):
        return

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        return

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        return

    @classmethod
    def update(cls, *targets, venv: str | None = None, version: str | None = None):
        if len(targets) == 0:
            cls._run_pip_cmd('pip install --upgrade pip', venv=venv, ensure_venv=venv is not None, trace=cls._update_trace)
            return
        effective_targets = cls._targets_for_install(tuple(targets), version=version)
        cls._run_pip_cmd(
            f"pip install --upgrade {' '.join(shlex.quote(target) for target in effective_targets)}",
            venv=venv,
            ensure_venv=venv is not None,
            trace=cls._update_trace,
        )

    @classmethod
    def install(cls, *targets, venv: str | None = None, version: str | None = None):
        if len(targets) == 0:
            return
        effective_targets = cls._targets_for_install(tuple(targets), version=version)
        cls._run_pip_cmd(
            f"pip install {' '.join(shlex.quote(target) for target in effective_targets)}",
            venv=venv,
            ensure_venv=venv is not None,
            trace=cls._install_trace(effective_targets),
        )

    @classmethod
    def install_target(
        cls,
        target_mgr: dict[str, str],
        candidate: str,
        force: bool = False,
        version_specifier: str | None = None,
        venv: str | None = None,
    ) -> None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        effective_candidate = cls._target_with_version_specifier(str(config['candidate']), version_specifier=version_specifier)
        cls.install(
            effective_candidate,
            venv=venv if venv is not None else (str(config['venv']) if config['venv'] is not None else None),
            version=str(config['version']) if config['version'] is not None else None,
        )

    @classmethod
    def uninstall(cls, *targets, venv: str | None = None, version: str | None = None) -> Never:
        if len(targets) == 0:
            return
        cls._run_pip_cmd(
            f"pip uninstall -y {' '.join(shlex.quote(target) for target in targets)}",
            venv=venv,
            ensure_venv=False,
            trace=cls._uninstall_trace(targets),
        )

    @classmethod
    def uninstall_target(
        cls,
        target_mgr: dict[str, str],
        candidate: str,
        version_specifier: str | None = None,
        venv: str | None = None,
    ) -> None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        cls.uninstall(
            str(config['candidate']),
            venv=venv if venv is not None else (str(config['venv']) if config['venv'] is not None else None),
            version=str(config['version']) if config['version'] is not None else None,
        )

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        package_name = cls._package_name_for_show(str(config['candidate']))
        if not package_name:
            return False
        result = cls._run_pip_cmd(
            f"pip show {shlex.quote(package_name)}",
            venv=str(config['venv']) if config['venv'] is not None else None,
            ensure_venv=False,
            check=False,
        )
        return result.returncode == 0


class Snap(_PackageManager):

    TARGET_PLARFORMS: list[str] = ['Linux']
    NAME: str = 'snap'
    REQUIRES_ELEVATION: bool = True

    @classmethod
    def list_gpg(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_gpg(cls, url: str):
        return

    @classmethod
    def remove_gpg(cls, target: str | int):
        return

    @classmethod
    def list_repos(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_repo(cls, repo: str):
        return

    @classmethod
    def remove_repo(cls, target: str | int):
        return

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        return

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        return

    @classmethod
    def update(cls, *targets):
        cmd = 'snap refresh'
        if targets:
            cmd = f"{cmd} {' '.join(targets)}"
        cls._run_cmd(cmd, trace=cls._update_trace)

    @classmethod
    def install(cls, *targets, channel: str | None = None, classic: bool = False):
        if len(targets) == 0:
            return
        flags: list[str] = []
        if channel:
            flags.append(f'--channel={channel}')
        if classic:
            flags.append('--classic')
        flag_prefix = f"{' '.join(flags)} " if flags else ''
        cls._run_cmd(f"snap install {flag_prefix}{' '.join(targets)}", trace=cls._install_trace(targets))

    @classmethod
    def install_target(cls, target_mgr: dict[str, str], candidate: str, force: bool = False) -> None:
        cls.install(candidate, channel=target_mgr.get('channel'), classic=bool(target_mgr.get('classic', False)))

    @classmethod
    def uninstall(cls, *targets) -> Never:
        if len(targets) == 0:
            return
        cls._run_cmd(f"snap remove {' '.join(targets)}", trace=cls._uninstall_trace(targets))

    @classmethod
    def uninstall_target(cls, target_mgr: dict[str, str], candidate: str) -> None:
        cls.uninstall(candidate)

    @classmethod
    def list_installed(cls) -> list[str]:
        result = cls._run_cmd('snap list')
        names = [
            line.split()[0]
            for line in result.stdout.splitlines()
            if line.strip() and not line.lower().startswith('name ')
        ]
        if names:
            ut.Display.print_list(names)
        else:
            ut.Display.print_list()
        return names

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        return cls._run_read_cmd(f'snap list {candidate}', check=False).returncode == 0


class Pipx(_PackageManager):

    TARGET_PLARFORMS: list[str] = ['Linux', 'macOS', 'Windows']
    NAME: str = 'pipx'

    @classmethod
    def _normalize_target_mgr(
        cls,
        target_mgr: dict[str, str],
        *,
        candidate: str | None = None,
        require_candidate: bool = True,
    ) -> dict[str, object]:
        effective_candidate = candidate if candidate is not None else target_mgr.get('candidate')
        if require_candidate and not effective_candidate:
            raise ValueError("[-] Pipx manager entries require 'candidate'")

        preinstall = target_mgr.get('preinstall')
        if preinstall is None:
            preinstall_list: list[str] = []
        elif isinstance(preinstall, str):
            preinstall_list = [preinstall]
        elif isinstance(preinstall, list) and all(isinstance(item, str) for item in preinstall):
            preinstall_list = list(preinstall)
        else:
            raise TypeError("[-] Pipx manager field 'preinstall' must be a string or list of strings")

        python = target_mgr.get('python')
        if python is not None and not isinstance(python, str):
            raise TypeError("[-] Pipx manager field 'python' must be a string")

        index_url = target_mgr.get('index_url')
        if index_url is not None and not isinstance(index_url, str):
            raise TypeError("[-] Pipx manager field 'index_url' must be a string")

        pip_args = target_mgr.get('pip_args')
        if pip_args is not None and not isinstance(pip_args, str):
            raise TypeError("[-] Pipx manager field 'pip_args' must be a string")

        return {
            'candidate': effective_candidate,
            'global': bool(target_mgr.get('global', False)),
            'include_deps': bool(target_mgr.get('include_deps', False)),
            'python': python,
            'fetch_missing_python': bool(target_mgr.get('fetch_missing_python', False)),
            'preinstall': preinstall_list,
            'system_site_packages': bool(target_mgr.get('system_site_packages', False)),
            'index_url': index_url,
            'editable': bool(target_mgr.get('editable', False)),
            'pip_args': pip_args,
            'include_injected': bool(target_mgr.get('include_injected', False)),
        }

    @staticmethod
    def _global_flag(global_install: bool) -> str:
        return '--global ' if global_install else ''

    @classmethod
    def _install_flags(cls, config: dict[str, object]) -> str:
        flags: list[str] = []
        if config['global']:
            flags.append('--global')
        if config['include_deps']:
            flags.append('--include-deps')
        if config['python'] is not None:
            flags.extend(['--python', shlex.quote(str(config['python']))])
        if config['fetch_missing_python']:
            flags.append('--fetch-missing-python')
        for package in config['preinstall']:
            flags.extend(['--preinstall', shlex.quote(str(package))])
        if config['system_site_packages']:
            flags.append('--system-site-packages')
        if config['index_url'] is not None:
            flags.extend(['--index-url', shlex.quote(str(config['index_url']))])
        if config['editable']:
            flags.append('--editable')
        if config['pip_args'] is not None:
            flags.extend(['--pip-args', shlex.quote(str(config['pip_args']))])
        return ' '.join(flags)

    @classmethod
    def _upgrade_flags(cls, config: dict[str, object]) -> str:
        flags: list[str] = []
        if config['global']:
            flags.append('--global')
        if config['include_injected']:
            flags.append('--include-injected')
        if config['python'] is not None:
            flags.extend(['--python', shlex.quote(str(config['python']))])
        if config['fetch_missing_python']:
            flags.append('--fetch-missing-python')
        if config['system_site_packages']:
            flags.append('--system-site-packages')
        if config['index_url'] is not None:
            flags.extend(['--index-url', shlex.quote(str(config['index_url']))])
        if config['editable']:
            flags.append('--editable')
        if config['pip_args'] is not None:
            flags.extend(['--pip-args', shlex.quote(str(config['pip_args']))])
        return ' '.join(flags)

    @classmethod
    def list_gpg(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_gpg(cls, url: str):
        return

    @classmethod
    def remove_gpg(cls, target: str | int):
        return

    @classmethod
    def list_repos(cls) -> list[str]:
        ut.Display.print_list()
        return []

    @classmethod
    def add_repo(cls, repo: str):
        return

    @classmethod
    def remove_repo(cls, target: str | int):
        return

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        return

    @classmethod
    def cleanup(cls, target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        return

    @classmethod
    def update(cls, *targets, global_install: bool = False, include_injected: bool = False):
        flags: list[str] = []
        if global_install:
            flags.append('--global')
        if include_injected:
            flags.append('--include-injected')
        flag_prefix = f"{' '.join(flags)} " if flags else ''
        if targets:
            cls._run_cmd(f"pipx upgrade {flag_prefix}{' '.join(targets)}".rstrip(), trace=cls._update_trace)
            return
        cls._run_cmd(f"pipx upgrade-all {flag_prefix}".rstrip(), trace=cls._update_trace)

    @classmethod
    def install(cls, *targets, global_install: bool = False, install_flags: str = ''):
        if len(targets) == 0:
            return
        flags = install_flags.strip()
        flag_prefix = f'{flags} ' if flags else ''
        if global_install and '--global' not in flags.split():
            flag_prefix = f'--global {flag_prefix}'
        cls._run_cmd(
            f"pipx install {flag_prefix}{' '.join(shlex.quote(target) for target in targets)}".rstrip(),
            trace=cls._install_trace(targets),
        )

    @classmethod
    def reinstall(cls, *targets, global_install: bool = False, python: str | None = None, fetch_missing_python: bool = False):
        if len(targets) == 0:
            return
        flags: list[str] = []
        if global_install:
            flags.append('--global')
        if python is not None:
            flags.extend(['--python', shlex.quote(python)])
        if fetch_missing_python:
            flags.append('--fetch-missing-python')
        flag_prefix = f"{' '.join(flags)} " if flags else ''
        cls._run_cmd(
            f"pipx reinstall {flag_prefix}{' '.join(shlex.quote(target) for target in targets)}".rstrip(),
            trace=cls._install_trace(targets),
        )

    @classmethod
    def install_target(cls, target_mgr: dict[str, str], candidate: str, force: bool = False) -> None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        if force and cls.is_installed_target(target_mgr, candidate) is True:
            cls.reinstall(
                str(config['candidate']),
                global_install=bool(config['global']),
                python=str(config['python']) if config['python'] is not None else None,
                fetch_missing_python=bool(config['fetch_missing_python']),
            )
            return
        cls.install(
            str(config['candidate']),
            global_install=bool(config['global']),
            install_flags=cls._install_flags(config),
        )

    @classmethod
    def uninstall(cls, *targets, global_install: bool = False) -> Never:
        if len(targets) == 0:
            return
        flag_prefix = cls._global_flag(global_install)
        cls._run_cmd(
            f"pipx uninstall {flag_prefix}{' '.join(shlex.quote(target) for target in targets)}".rstrip(),
            trace=cls._uninstall_trace(targets),
        )

    @classmethod
    def uninstall_target(cls, target_mgr: dict[str, str], candidate: str) -> None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        cls.uninstall(str(config['candidate']), global_install=bool(config['global']))

    @classmethod
    def _list_installed_names(cls, global_install: bool = False) -> list[str]:
        result = cls._run_cmd(f"pipx list {cls._global_flag(global_install)}--short".rstrip(), check=False)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    @classmethod
    def list_installed(cls, global_install: bool = False) -> list[str]:
        names = cls._list_installed_names(global_install=global_install)
        if names:
            ut.Display.print_list(names)
        else:
            ut.Display.print_list()
        return names

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        config = cls._normalize_target_mgr(target_mgr, candidate=candidate)
        return str(config['candidate']) in cls._list_installed_names(global_install=bool(config['global']))


class GitManager(_PackageManager):
    NAME = 'git'

    @classmethod
    def available_on_host(cls) -> bool:
        return shutil.which('git') is not None

    @classmethod
    def _normalize_target_mgr(cls, target_mgr: dict[str, str]) -> dict[str, str | None]:
        url = target_mgr.get('url')
        if not url:
            raise ValueError("[-] Git manager entries require 'url'")
        return {
            'url': url,
            'release': target_mgr.get('release'),
            'candidate': target_mgr.get('candidate'),
        }

    @classmethod
    def _repo_for_target(cls, target_mgr: dict[str, str]) -> GitRepo:
        config = cls._normalize_target_mgr(target_mgr)
        repo_cls = GithubRepo if 'github' in str(config['url']).lower() else GitlabRepo
        return repo_cls(url=str(config['url']))

    @classmethod
    def prepare(cls, target_mgr: dict[str, str]) -> None:
        return

    @classmethod
    def update(cls):
        return

    @classmethod
    def install(cls, *targets):
        return

    @classmethod
    def install_target(cls, target_mgr: dict[str, str], candidate: str, force: bool = False) -> None:
        config = cls._normalize_target_mgr(target_mgr)
        repo = cls._repo_for_target(target_mgr)
        if config['release'] is None and config['candidate'] is None:
            repo.install_from_source()
            return
        repo.install_from_release(str(config['release']) if config['release'] is not None else None, str(config['candidate']) if config['candidate'] is not None else None)

    @classmethod
    def uninstall(cls, *targets) -> Never:
        return

    @classmethod
    def uninstall_target(cls, target_mgr: dict[str, str], candidate: str) -> None:
        repo = cls._repo_for_target(target_mgr)
        ut.Files.remove_path(repo.path, missing_ok=True)

    @classmethod
    def is_installed_target(cls, target_mgr: dict[str, str], candidate: str) -> bool | None:
        return cls._repo_for_target(target_mgr).path.exists()



MANAGERS = {
    'apt': Apt,
    'pacman': Pacman,
    'yay': Yay,
    'yum': Yum,
    'dnf': Dnf,
    'zypper': Zypper,
    'brew': Brew,
    'choco': Choco,
    'scoop': Scoop,
    'git': GitManager,
    'flatpak': Flatpak,
    'snap': Snap,
    'npm': Npm,
    'pip': Pip,
    'pipx': Pipx,
}

class PackageManger:
    
    MANAGER: type[_PackageManager] | None = None

    @staticmethod
    def _manager() -> type[_PackageManager]:
        if PackageManger.MANAGER is not None:
            return PackageManger.MANAGER
        return MANAGERS[get_installed_manager()]

    def list_gpg():
        """List currently installed GPG keys"""
        return PackageManger._manager().list_gpg()

    def add_gpg(url: str):
        """Adds a GPG key from the package manager configuration"""
        PackageManger._manager().add_gpg(url)

    def remove_gpg(target: str | int):
        """Removes a GPG key from the package manager configuration
        target is str (to look up the gpg, or index obtained from self.list_gpg())
        """
        PackageManger._manager().remove_gpg(target)

    def list_repos():
        """Returns active repos defined in the package manager configuration"""
        return PackageManger._manager().list_repos()

    def add_repo(repo: str):
        """Adds a new repo to the package manager configuartion"""
        PackageManger._manager().add_repo(repo)

    def remove_repo(target: str | int):
        """Removes a repo from the package manager configuration
        target is str (to look up the repo, or index obtained from self.list_repos())
        """
        PackageManger._manager().remove_repo(target)

    def prepare(target_mgr: dict[str, str]) -> None:
        """Prepares package manager state before installation"""
        PackageManger._manager().prepare(target_mgr)

    def cleanup(target_mgr: dict[str, str], remove_repo: bool = False) -> None:
        """Cleans package manager state after uninstallation"""
        PackageManger._manager().cleanup(target_mgr, remove_repo=remove_repo)

    def update():
        """Runs the package manager update command"""
        PackageManger._manager().update()
    
    def install(*targets):
        """Runs the package manager install command to install target app"""
        PackageManger._manager().install(*targets)

    def install_target(target_mgr: dict[str, str], candidate: str, force: bool = False) -> None:
        """Runs the package manager install command for a manager-specific target config"""
        PackageManger._manager().install_target(target_mgr, candidate, force=force)

    def uninstall(*targets) -> Never:
        """Runs the package manager command to uninstall target app(s)"""
        PackageManger._manager().uninstall(*targets)

    def uninstall_target(target_mgr: dict[str, str], candidate: str) -> None:
        """Runs the package manager uninstall command for a manager-specific target config"""
        PackageManger._manager().uninstall_target(target_mgr, candidate)
