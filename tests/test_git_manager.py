import io
import tarfile
import zipfile


class FakeResponse:
    def __init__(self, *, payload=None, chunks=None, status_code=200):
        self._payload = payload
        self._chunks = list(chunks or [])
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'http {self.status_code}')

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=65536):
        return iter(self._chunks)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestGitManager:
    def test_github_repo_parses_https_url(self, modules):
        repo = modules.repositories.GithubRepo(url='https://github.com/Owner/Repo.Name.git')

        assert repo.remote == 'github.com'
        assert repo.owner == 'Owner'
        assert repo.repo_name == 'Repo.Name'
        assert repo.BASE_URL_HTTPS == 'https://github.com/'
        assert repo.BASE_URL_SSH is None
        assert repo.remote_url == 'https://github.com/Owner/Repo.Name.git'
        assert repo.path == modules.home / 'Apps' / 'Owner' / 'Repo.Name'

    def test_gitlab_repo_parses_ssh_url_and_rewrites_custom_remote(self, modules):
        repo = modules.repositories.GitlabRepo(url='git@gitlab.example.com:Wine/Wine.git')

        assert repo.remote == 'gitlab.example.com'
        assert repo.owner == 'Wine'
        assert repo.repo_name == 'Wine'
        assert repo.BASE_URL_HTTPS is None
        assert repo.BASE_URL_SSH == 'git@gitlab.example.com:'
        assert repo.remote_url == 'git@gitlab.example.com:Wine/Wine.git'

    def test_vendor_repo_can_be_built_from_owner_and_repo(self, modules):
        repo = modules.repositories.GithubRepo(owner='cli', repo='gh')

        assert repo.remote == 'github.com'
        assert repo.BASE_URL_SSH is None
        assert repo.remote_url == 'https://github.com/cli/gh.git'

    def test_git_repo_uses_configured_default_repo_dir(self, modules, monkeypatch):
        monkeypatch.setitem(modules.managers.ut.Config.data, 'DEFAULT_REPO_DIR', modules.home / 'Repos')

        repo = modules.repositories.GithubRepo(owner='cli', repo='gh')

        assert repo.path == modules.home / 'Repos' / 'cli' / 'gh'

    def test_git_repo_falls_back_to_root_dir_when_config_repo_dir_missing(self, modules, monkeypatch):
        monkeypatch.delitem(modules.managers.ut.Config.data, 'DEFAULT_REPO_DIR', raising=False)
        monkeypatch.setattr(modules.repositories.GithubRepo, 'ROOT_DIR', modules.managers.Path('~/Sources'))

        repo = modules.repositories.GithubRepo(owner='cli', repo='gh')

        assert repo.path == modules.home / 'Sources' / 'cli' / 'gh'

    def test_git_manager_requires_url(self, modules):
        try:
            modules.managers.GitManager._normalize_target_mgr({})
        except ValueError as exc:
            assert str(exc) == "[-] Git manager entries require 'url'"
        else:
            raise AssertionError('Expected missing git url to fail')

    def test_git_manager_selects_source_install_when_release_fields_missing(self, modules, monkeypatch):
        calls = []

        class FakeRepo:
            def install_from_source(self):
                calls.append('source')

            def install_from_release(self, tag, candidate):
                calls.append(('release', tag, candidate))

        monkeypatch.setattr(modules.managers.GitManager, '_repo_for_target', classmethod(lambda cls, target_mgr: FakeRepo()))

        modules.managers.GitManager.install_target({'url': 'https://github.com/cli/gh.git'}, 'app-candidate')

        assert calls == ['source']

    def test_source_install_traces_clone_command(self, modules, monkeypatch):
        commands = []
        traces = []
        monkeypatch.setattr(modules.repositories.ut.Shell, 'run', lambda cmd, **kwargs: commands.append((cmd, kwargs)))
        monkeypatch.setattr(modules.repositories.logger, 'trace', lambda message: traces.append(message))

        repo = modules.repositories.GithubRepo(url='https://github.com/cli/gh.git')
        repo.install_from_source()

        assert commands == [('git clone https://github.com/cli/gh.git ' + str(repo.path), {})]
        assert traces == ['cmd: git clone https://github.com/cli/gh.git ' + str(repo.path)]

    def test_git_manager_selects_release_install_when_candidate_or_release_present(self, modules, monkeypatch):
        calls = []

        class FakeRepo:
            def install_from_source(self):
                calls.append('source')

            def install_from_release(self, tag, candidate):
                calls.append((tag, candidate))

        monkeypatch.setattr(modules.managers.GitManager, '_repo_for_target', classmethod(lambda cls, target_mgr: FakeRepo()))

        modules.managers.GitManager.install_target(
            {
                'url': 'https://github.com/cli/gh.git',
                'release': 'v1.2.3',
                'candidate': '*.AppImage',
            },
            'ignored-app-candidate',
        )

        assert calls == [('v1.2.3', '*.AppImage')]

    def test_candidate_patterns_follow_platform_priority(self, modules, monkeypatch):
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'ubuntu', 'debian'})
        assert modules.repositories.GitRepo._candidate_patterns(None) == ['*.deb', '*.AppImage', '*.tar.gz']

        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        assert modules.repositories.GitRepo._candidate_patterns(None) == ['*.AppImage', '*.tar.gz']

        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'macos'})
        assert modules.repositories.GitRepo._candidate_patterns(None) == ['*.DMG']

        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'win'})
        assert modules.repositories.GitRepo._candidate_patterns(None) == ['*.exe', '*.msi', '*.zip']

        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'plan9'})
        assert modules.repositories.GitRepo._candidate_patterns(None) == ['*.tar.gz']

    def test_release_install_matches_case_insensitively_and_falls_back(self, modules, monkeypatch):
        repo = modules.repositories.GithubRepo(url='https://github.com/cli/gh.git')
        downloads = []

        monkeypatch.setattr(repo, 'get_latest_release', lambda: 'v2.0.0')
        monkeypatch.setattr(
            repo,
            'get_release_assets',
            lambda tag: [
                {'name': 'gh_2.0.0_Linux.AppImage', 'url': 'https://example.invalid/appimage'},
                {'name': 'gh_2.0.0_linux.tar.gz', 'url': 'https://example.invalid/targz'},
            ],
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        def fake_download(url, destination):
            downloads.append(destination.name)
            if destination.name.lower().endswith('.appimage'):
                raise modules.managers.requests.RequestException('missing')
            destination.write_bytes(b'archive')
            return destination

        monkeypatch.setattr(repo, '_download_file', fake_download)
        extracted = []
        monkeypatch.setattr(repo, '_extract_if_needed', lambda asset_path: extracted.append(asset_path.name))

        installed = repo.install_from_release(None, None)

        assert downloads == ['gh_2.0.0_Linux.AppImage', 'gh_2.0.0_linux.tar.gz']
        assert extracted == ['gh_2.0.0_linux.tar.gz']
        assert installed.name == 'gh_2.0.0_linux.tar.gz'

    def test_release_install_extracts_zip_and_tar_gz(self, modules):
        repo = modules.repositories.GithubRepo(url='https://github.com/cli/gh.git')
        release_dir = repo.release_dir / 'v1.0.0'
        release_dir.mkdir(parents=True)

        zip_path = release_dir / 'bundle.zip'
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as archive:
            archive.writestr('zip-content.txt', 'hello zip')
        zip_path.write_bytes(zip_buffer.getvalue())

        tar_path = release_dir / 'bundle.tar.gz'
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode='w:gz') as archive:
            data = b'hello tar'
            info = tarfile.TarInfo('tar-content.txt')
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        tar_path.write_bytes(tar_buffer.getvalue())

        repo._extract_if_needed(zip_path)
        repo._extract_if_needed(tar_path)

        assert (release_dir / 'zip-content.txt').read_text() == 'hello zip'
        assert (release_dir / 'tar-content.txt').read_text() == 'hello tar'

    def test_release_install_installs_deb_and_cleans_empty_dirs(self, modules, monkeypatch):
        repo = modules.repositories.GithubRepo(url='https://github.com/cli/gh.git')
        installs = []
        expected_path = repo.release_dir / 'v2.0.0' / 'gh_2.0.0_amd64.deb'

        monkeypatch.setattr(repo, 'get_latest_release', lambda: 'v2.0.0')
        monkeypatch.setattr(
            repo,
            'get_release_assets',
            lambda tag: [
                {'name': 'gh_2.0.0_amd64.deb', 'url': 'https://example.invalid/gh.deb'},
            ],
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'ubuntu', 'debian'})
        monkeypatch.setattr(modules.managers.Apt, 'available_on_host', classmethod(lambda cls: True))
        monkeypatch.setattr(modules.managers.Apt, 'install', lambda *targets: installs.extend(targets))

        def fake_download(url, destination):
            destination.write_bytes(b'deb')
            return destination

        monkeypatch.setattr(repo, '_download_file', fake_download)

        installed = repo.install_from_release(None, None)

        assert installed is None
        assert installs == [str(expected_path)]
        assert not expected_path.exists()
        assert not (repo.release_dir / 'v2.0.0').exists()
        assert not repo.path.exists()
        assert not repo.path.parent.exists()

    def test_release_install_deb_preserves_non_empty_repo_dirs(self, modules, monkeypatch):
        repo = modules.repositories.GithubRepo(url='https://github.com/cli/gh.git')
        installs = []
        expected_path = repo.release_dir / 'v2.0.0' / 'gh_2.0.0_amd64.deb'

        monkeypatch.setattr(repo, 'get_latest_release', lambda: 'v2.0.0')
        monkeypatch.setattr(
            repo,
            'get_release_assets',
            lambda tag: [
                {'name': 'gh_2.0.0_amd64.deb', 'url': 'https://example.invalid/gh.deb'},
            ],
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'ubuntu', 'debian'})
        monkeypatch.setattr(modules.managers.Apt, 'available_on_host', classmethod(lambda cls: True))
        monkeypatch.setattr(modules.managers.Apt, 'install', lambda *targets: installs.extend(targets))

        sibling_dir = repo.path / 'notes'
        sibling_dir.mkdir(parents=True)
        (sibling_dir / 'keep.txt').write_text('keep')

        def fake_download(url, destination):
            destination.write_bytes(b'deb')
            return destination

        monkeypatch.setattr(repo, '_download_file', fake_download)

        installed = repo.install_from_release(None, None)

        assert installed is None
        assert installs == [str(expected_path)]
        assert not expected_path.exists()
        assert not (repo.release_dir / 'v2.0.0').exists()
        assert repo.path.exists()
        assert repo.path.parent.exists()
        assert (sibling_dir / 'keep.txt').read_text() == 'keep'

    def test_release_install_deb_requires_apt_host(self, modules, monkeypatch):
        repo = modules.repositories.GithubRepo(url='https://github.com/cli/gh.git')

        monkeypatch.setattr(repo, 'get_latest_release', lambda: 'v2.0.0')
        monkeypatch.setattr(
            repo,
            'get_release_assets',
            lambda tag: [
                {'name': 'gh_2.0.0_amd64.deb', 'url': 'https://example.invalid/gh.deb'},
            ],
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'ubuntu', 'debian'})
        monkeypatch.setattr(modules.managers.Apt, 'available_on_host', classmethod(lambda cls: False))

        def fake_download(url, destination):
            destination.write_bytes(b'deb')
            return destination

        monkeypatch.setattr(repo, '_download_file', fake_download)

        try:
            repo.install_from_release(None, None)
        except ValueError as exc:
            assert str(exc) == '[-] .deb release assets require an apt-compatible host'
        else:
            raise AssertionError('Expected non-apt .deb release install to fail')

    def test_uninstall_removes_repo_tree(self, modules):
        target = modules.home / 'Apps' / 'cli' / 'gh' / '_releases' / 'v1.0.0'
        target.mkdir(parents=True)
        (target / 'gh.tar.gz').write_text('asset')

        modules.managers.GitManager.uninstall_target({'url': 'https://github.com/cli/gh.git'}, 'ignored')

        assert not (modules.home / 'Apps' / 'cli' / 'gh').exists()

    def test_available_on_host_depends_on_git_executable(self, modules, monkeypatch):
        monkeypatch.setattr(modules.managers.shutil, 'which', lambda name: '/usr/bin/git' if name == 'git' else None)
        assert modules.managers.GitManager.available_on_host() is True

        monkeypatch.setattr(modules.managers.shutil, 'which', lambda name: None)
        assert modules.managers.GitManager.available_on_host() is False

    def test_github_release_api_parsing_includes_fallback_archives(self, modules, monkeypatch):
        repo = modules.repositories.GithubRepo(url='https://github.com/cli/gh.git')
        monkeypatch.setattr(
            modules.managers.requests,
            'get',
            lambda url, **kwargs: FakeResponse(
                payload={
                    'tag_name': 'v2.0.0',
                    'assets': [{'name': 'gh.dmg', 'browser_download_url': 'https://example.invalid/gh.dmg'}],
                    'tarball_url': 'https://example.invalid/src.tar.gz',
                    'zipball_url': 'https://example.invalid/src.zip',
                }
            ),
        )

        assets = repo.get_release_assets('v2.0.0')

        assert assets == [
            {'name': 'gh.dmg', 'url': 'https://example.invalid/gh.dmg'},
            {'name': 'gh-v2.0.0.tar.gz', 'url': 'https://example.invalid/src.tar.gz'},
            {'name': 'gh-v2.0.0.zip', 'url': 'https://example.invalid/src.zip'},
        ]

    def test_gitlab_release_api_parsing_includes_link_and_source_assets(self, modules, monkeypatch):
        repo = modules.repositories.GitlabRepo(url='https://gitlab.com/group/project.git')
        monkeypatch.setattr(
            modules.managers.requests,
            'get',
            lambda url, **kwargs: FakeResponse(
                payload={
                    'tag_name': 'v1.0.0',
                    'assets': {
                        'links': [{'name': 'project.AppImage', 'url': 'https://example.invalid/project.AppImage'}],
                        'sources': [{'format': 'tar.gz', 'url': 'https://example.invalid/project.tar.gz'}],
                    },
                }
            ),
        )

        assets = repo.get_release_assets('v1.0.0')

        assert assets == [
            {'name': 'project.AppImage', 'url': 'https://example.invalid/project.AppImage'},
            {'name': 'project-v1.0.0.tar.gz', 'url': 'https://example.invalid/project.tar.gz'},
        ]

    def test_inventory_prefers_git_manager_when_available(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.managers.App('gh', preference=['git', 'brew'])
        app.add_manager('git', url='https://github.com/cli/gh.git')
        app.add_manager('brew', candidate='gh')
        api.add_app(app)

        monkeypatch.setattr(modules.managers.GitManager, 'available_on_host', classmethod(lambda cls: True))
        monkeypatch.setattr(modules.managers.Brew, 'available_on_host', classmethod(lambda cls: False))

        assert api._ordered_available_methods(app) == ['git']
