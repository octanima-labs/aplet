from urllib.parse import quote, urlparse
from pathlib import Path
import fnmatch
import re
import requests
import shlex
import tarfile
import zipfile

from . import utils as ut


logger = ut.get_logger(__name__)


class GitRepo:
    BASE_URL_HTTPS: str | None = None
    BASE_URL_SSH: str | None = None
    ROOT_DIR: Path = Path('~/Apps')
    HTTPS_URL_PATTERN = re.compile(
        r'^https://(?P<remote>[^/]+)/(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)\.git$'
    )
    SSH_URL_PATTERN = re.compile(
        r'^git@(?P<remote>[^:]+):(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)\.git$'
    )

    def __init__(self, url: str | None = None, owner: str | None = None, repo: str | None = None):
        if url is not None:
            parsed = self._parse_url(url)
            self.remote = parsed['remote']
            self.owner = parsed['owner']
            self.repo_name = parsed['repo_name']
            self.BASE_URL_HTTPS, self.BASE_URL_SSH = self._normalize_base_urls(parsed['scheme'], self.remote)
        elif owner is not None and repo is not None:
            self._validate_repo_part(owner, 'owner')
            self._validate_repo_part(repo, 'repo')
            self.owner = owner
            self.repo_name = repo
            base_url = self.BASE_URL_HTTPS
            if not base_url:
                raise ValueError('[-] Cannot derive repository URL without BASE_URL_HTTPS')
            self.remote = urlparse(base_url).netloc
            self.BASE_URL_SSH = None
        else:
            raise ValueError("[-] Git repo expects either 'url' or both 'owner' and 'repo'")
        repo_root_dir = ut.Config.get('DEFAULT_REPO_DIR')
        if repo_root_dir is None:
            repo_root_dir = self.ROOT_DIR
        self.path = ut.Files.expand_path(repo_root_dir / self.owner / self.repo_name)

    @classmethod
    def _validate_repo_part(cls, value: str, field_name: str) -> None:
        if re.fullmatch(r'[A-Za-z0-9._-]+', value) is None:
            raise ValueError(f"[-] Invalid git {field_name} '{value}'")

    @classmethod
    def _parse_url(cls, url: str) -> dict[str, str]:
        match = cls.HTTPS_URL_PATTERN.fullmatch(url)
        if match is not None:
            return {
                'scheme': 'https',
                'remote': match.group('remote'),
                'owner': match.group('owner'),
                'repo_name': match.group('repo'),
            }
        match = cls.SSH_URL_PATTERN.fullmatch(url)
        if match is not None:
            return {
                'scheme': 'ssh',
                'remote': match.group('remote'),
                'owner': match.group('owner'),
                'repo_name': match.group('repo'),
            }
        raise ValueError(f"[-] Unsupported git repository URL '{url}'")

    def _normalize_base_urls(self, scheme: str, remote: str) -> tuple[str | None, str | None]:
        https_url = self.BASE_URL_HTTPS
        ssh_url = self.BASE_URL_SSH
        if scheme == 'https':
            ssh_url = None
            expected_remote = urlparse(https_url).netloc if https_url else None
            if expected_remote != remote:
                https_url = f'https://{remote}/'
        else:
            https_url = None
            expected_remote = ssh_url[4:-1] if ssh_url and ssh_url.startswith('git@') and ssh_url.endswith(':') else None
            if expected_remote != remote:
                ssh_url = f'git@{remote}:'
        return https_url, ssh_url

    @property
    def remote_url(self) -> str:
        base_url = self.BASE_URL_HTTPS if self.BASE_URL_HTTPS is not None else self.BASE_URL_SSH
        if base_url is None:
            raise ValueError('[-] Git repo has no usable base URL')
        return f'{base_url}{self.owner}/{self.repo_name}.git'

    @property
    def release_dir(self) -> Path:
        return self.path / '_releases'

    def _run_cmd(self, cmd: str, **kwargs):
        logger.trace(f"cmd: {cmd}")
        return ut.Shell.run(cmd, cwd=self.path, **kwargs)

    def _clone(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        cmd = f'git clone {shlex.quote(self.remote_url)} {shlex.quote(str(self.path))}'
        logger.trace(f"cmd: {cmd}")
        ut.Shell.run(cmd)

    def _fetch(self):
        self._run_cmd('git fetch --all --tags')

    def _pull(self):
        self._run_cmd('git pull')

    def _request_json(self, url: str):
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _asset_name(url: str) -> str:
        return Path(urlparse(url).path).name

    @staticmethod
    def _match_asset(name: str, pattern: str) -> bool:
        return fnmatch.fnmatch(name.lower(), pattern.lower())

    @staticmethod
    def _download_file(url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(destination, 'wb') as file:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        file.write(chunk)
        return destination

    @staticmethod
    def _extract_if_needed(asset_path: Path) -> None:
        asset_name = asset_path.name.lower()
        if asset_name.endswith('.zip'):
            with zipfile.ZipFile(asset_path, 'r') as archive:
                archive.extractall(asset_path.parent)
            return
        if asset_name.endswith('.tar.gz'):
            with tarfile.open(asset_path, 'r:gz') as archive:
                archive.extractall(asset_path.parent)

    @staticmethod
    def _is_deb_asset(asset_path: Path) -> bool:
        return asset_path.name.lower().endswith('.deb')

    @staticmethod
    def _remove_dir_if_empty(path: Path) -> None:
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            ut.Files.remove_path(path)

    def _cleanup_deb_release_dirs(self, release_dir: Path) -> None:
        self._remove_dir_if_empty(release_dir)
        self._remove_dir_if_empty(self.release_dir)
        self._remove_dir_if_empty(self.path)
        self._remove_dir_if_empty(self.path.parent)

    @staticmethod
    def _candidate_patterns(candidate: str | None) -> list[str]:
        if candidate is not None:
            return [candidate]
        host_tokens = ut.Platform.host_install_tokens()
        if 'ubuntu' in host_tokens or 'debian' in host_tokens:
            return ['*.deb', '*.AppImage', '*.tar.gz']
        if 'linux' in host_tokens:
            return ['*.AppImage', '*.tar.gz']
        if 'macos' in host_tokens:
            return ['*.DMG']
        if 'win' in host_tokens:
            return ['*.exe', '*.msi', '*.zip']
        return ['*.tar.gz']

    def update(self):
        if not (self.path / '.git').exists():
            return
        self._fetch()
        self._pull()

    def get_latest_release(self) -> str:
        raise NotImplementedError

    def get_release_assets(self, tag: str) -> list[dict[str, str]]:
        raise NotImplementedError

    def install_from_source(self):
        if (self.path / '.git').exists():
            self.update()
            return
        if self.path.exists() and any(self.path.iterdir()):
            raise ValueError(f"[-] Target path '{self.path}' already exists and is not a git checkout")
        self._clone()

    def install_from_release(self, tag: str | None = None, candidate: str | None = None) -> Path | None:
        release_tag = self.get_latest_release() if tag in {None, 'latest'} else tag
        assets = self.get_release_assets(release_tag)
        if len(assets) == 0:
            raise ValueError(f"[-] No downloadable assets found for release '{release_tag}'")
        candidate_patterns = self._candidate_patterns(candidate)
        target_release_dir = self.release_dir / release_tag
        target_release_dir.mkdir(parents=True, exist_ok=True)
        for pattern in candidate_patterns:
            for asset in assets:
                if not self._match_asset(asset['name'], pattern):
                    continue
                asset_path = target_release_dir / asset['name']
                try:
                    self._download_file(asset['url'], asset_path)
                except requests.RequestException:
                    continue
                if self._is_deb_asset(asset_path):
                    from .managers import Apt
                    if not Apt.available_on_host():
                        raise ValueError('[-] .deb release assets require an apt-compatible host')
                    Apt.install(str(asset_path))
                    ut.Files.remove_path(asset_path)
                    self._cleanup_deb_release_dirs(target_release_dir)
                    return None
                self._extract_if_needed(asset_path)
                return asset_path
        raise ValueError(
            f"[-] No release asset matched candidates: {', '.join(candidate_patterns)}"
        )


class GithubRepo(GitRepo):
    BASE_URL_HTTPS = 'https://github.com/'
    BASE_URL_SSH = 'git@github.com:'
    API_BASE_URL = 'https://api.github.com'

    def __init__(self, url: str | None = None, owner: str | None = None, repo: str | None = None):
        super().__init__(url=url, owner=owner, repo=repo)

    def _release_payload(self, tag: str | None = None):
        if tag is None:
            url = f'{self.API_BASE_URL}/repos/{self.owner}/{self.repo_name}/releases/latest'
        else:
            url = f'{self.API_BASE_URL}/repos/{self.owner}/{self.repo_name}/releases/tags/{quote(tag, safe="")}'
        return self._request_json(url)

    def get_latest_release(self) -> str:
        return str(self._release_payload().get('tag_name'))

    def get_release_assets(self, tag: str) -> list[dict[str, str]]:
        payload = self._release_payload(tag)
        assets = [
            {'name': asset['name'], 'url': asset['browser_download_url']}
            for asset in payload.get('assets', [])
            if asset.get('name') and asset.get('browser_download_url')
        ]
        if payload.get('tarball_url'):
            assets.append({'name': f'{self.repo_name}-{tag}.tar.gz', 'url': payload['tarball_url']})
        if payload.get('zipball_url'):
            assets.append({'name': f'{self.repo_name}-{tag}.zip', 'url': payload['zipball_url']})
        return assets


class GitlabRepo(GitRepo):
    BASE_URL_HTTPS = 'https://gitlab.com/'
    BASE_URL_SSH = 'git@gitlab.com:'
    API_BASE_URL = 'https://gitlab.com/api/v4'

    def __init__(self, url: str | None = None, owner: str | None = None, repo: str | None = None):
        super().__init__(url=url, owner=owner, repo=repo)

    @property
    def _project_id(self) -> str:
        return quote(f'{self.owner}/{self.repo_name}', safe='')

    def _release_payload(self, tag: str | None = None):
        if tag is None:
            url = f'{self.API_BASE_URL}/projects/{self._project_id}/releases/permalink/latest'
        else:
            url = f'{self.API_BASE_URL}/projects/{self._project_id}/releases/{quote(tag, safe="")}'
        return self._request_json(url)

    def get_latest_release(self) -> str:
        return str(self._release_payload().get('tag_name'))

    def get_release_assets(self, tag: str) -> list[dict[str, str]]:
        payload = self._release_payload(tag)
        assets: list[dict[str, str]] = []
        for asset in payload.get('assets', {}).get('links', []):
            if asset.get('name') and asset.get('url'):
                assets.append({'name': asset['name'], 'url': asset['url']})
        for source in payload.get('assets', {}).get('sources', []):
            if source.get('url') and source.get('format'):
                assets.append(
                    {
                        'name': f'{self.repo_name}-{tag}.{source["format"]}',
                        'url': source['url'],
                    }
                )
        return assets
