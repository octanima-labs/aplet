class TestPackageManagerBase:
    def test_select_installed_manager_prefers_configured_manager(self, modules):
        selected = modules.managers._select_installed_manager(['choco', 'scoop'], 'scoop')

        assert selected == 'scoop'

    def test_select_installed_manager_falls_back_when_default_missing(self, modules, caplog):
        selected = modules.managers._select_installed_manager(['choco', 'scoop'], 'winget')

        assert selected == 'choco'
        assert "using 'choco'" in caplog.text

    def test_select_installed_manager_prefers_os_manager_before_flatpak_snap_and_npm(self, modules):
        selected = modules.managers._select_installed_manager(['apt', 'flatpak', 'snap', 'npm'])

        assert selected == 'apt'

    def test_select_installed_manager_prefers_pacman_before_yay(self, modules):
        selected = modules.managers._select_installed_manager(['pacman', 'yay'])

        assert selected == 'pacman'

    def test_prepare_calls_gpg_repo_and_update_when_present(self, modules):
        calls = []

        class Dummy(modules.managers._PackageManager):
            @staticmethod
            def add_gpg(url):
                calls.append(('gpg', url))

            @staticmethod
            def add_repo(repo):
                calls.append(('repo', repo))

            @staticmethod
            def update():
                calls.append(('update', None))

        Dummy.prepare({'gpg': 'https://example.com/key', 'repo': 'demo-repo'})

        assert calls == [
            ('gpg', 'https://example.com/key'),
            ('repo', 'demo-repo'),
            ('update', None),
        ]

    def test_cleanup_uses_derived_repo_target(self, modules):
        calls = []

        class Dummy(modules.managers._PackageManager):
            @classmethod
            def _derive_repo_target(cls, target_mgr):
                return target_mgr.get('repo_name')

            @staticmethod
            def remove_repo(target):
                calls.append(target)

        Dummy.cleanup({'repo_name': 'demo-repo'}, remove_repo=True)

        assert calls == ['demo-repo']

    def test_run_cmd_prefixes_sudo_for_privileged_managers(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))
        monkeypatch.setattr(modules.managers.os, 'geteuid', lambda: 1000)

        modules.managers.Apt._run_cmd('apt-get update')
        modules.managers.Brew._run_cmd('brew update')

        assert commands == ['sudo apt-get update', 'brew update']
