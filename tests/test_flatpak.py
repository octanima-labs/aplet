from tests.conftest import completed


class TestFlatpak:
    def test_list_repos_parses_named_remotes(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd):
            commands.append(cmd)
            return completed(stdout='Name\tUrl\tOptions\nflathub\thttps://flathub.org/repo/flathub.flatpakrepo\tsystem\n')

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        repos = modules.managers.Flatpak.list_repos()

        assert repos == ['flathub']
        assert commands == ['flatpak remotes --system --columns=name,url,options']

    def test_list_apps_parses_installed_apps(self, modules, monkeypatch):
        monkeypatch.setattr(
            modules.managers.ut.Shell,
            'run',
            lambda cmd: completed(
                stdout='Application\tOrigin\tInstallation\norg.mozilla.firefox\tflathub\tsystem\n'
            ),
        )

        apps = modules.managers.Flatpak.list_apps()

        assert apps == ['org.mozilla.firefox']

    def test_prepare_adds_default_flathub_and_updates_system_scope(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd):
            commands.append(cmd)
            if cmd == 'flatpak remotes --system --columns=name,url,options':
                return completed(stdout='')
            return completed()

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)
        monkeypatch.setattr(modules.managers.os, 'geteuid', lambda: 1000)

        modules.managers.Flatpak.prepare({'candidate': 'org.mozilla.firefox'})

        assert commands == [
            'flatpak remotes --system --columns=name,url,options',
            'sudo flatpak remote-add --if-not-exists --system flathub "https://flathub.org/repo/flathub.flatpakrepo"',
            'sudo flatpak update --assumeyes --noninteractive --system',
        ]

    def test_prepare_uses_user_scope_and_custom_remote_without_sudo(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd):
            commands.append(cmd)
            if cmd == 'flatpak remotes --user --columns=name,url,options':
                return completed(stdout='')
            return completed()

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        modules.managers.Flatpak.prepare(
            {
                'candidate': 'org.example.App',
                'remote_name': 'testing',
                'repo': 'https://example.com/testing.flatpakrepo',
                'user': True,
                'no_gpg_verify': True,
            }
        )

        assert commands == [
            'flatpak remotes --user --columns=name,url,options',
            'flatpak remote-add --if-not-exists --user --no-gpg-verify testing "https://example.com/testing.flatpakrepo"',
            'flatpak update --assumeyes --noninteractive --user',
        ]

    def test_prepare_rejects_custom_repo_without_remote_name(self, modules):
        try:
            modules.managers.Flatpak.prepare(
                {
                    'candidate': 'org.example.App',
                    'repo': 'https://example.com/testing.flatpakrepo',
                }
            )
        except ValueError as exc:
            assert str(exc) == "[-] Flatpak custom repo entries require 'remote_name'"
        else:
            raise AssertionError('Expected custom Flatpak repo without remote_name to fail')

    def test_install_and_uninstall_targets_use_scope_and_remote(self, modules, monkeypatch):
        commands = []
        infos = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd) or completed())
        monkeypatch.setattr(modules.managers.logger, 'info', lambda message: infos.append(message))

        modules.managers.Flatpak.install_target({'candidate': 'org.mozilla.firefox'}, 'org.mozilla.firefox')
        modules.managers.Flatpak.uninstall_target({'candidate': 'org.mozilla.firefox', 'user': True}, 'org.mozilla.firefox')

        assert commands == [
            'sudo flatpak install --assumeyes --noninteractive --system flathub org.mozilla.firefox',
            'flatpak uninstall --assumeyes --noninteractive --user org.mozilla.firefox',
        ]
        assert infos == [
            'Installing org.mozilla.firefox (sudo flatpak install --assumeyes --noninteractive --system flathub org.mozilla.firefox)',
            'Removing org.mozilla.firefox (flatpak uninstall --assumeyes --noninteractive --user org.mozilla.firefox)',
        ]

    def test_cleanup_does_not_remove_implicit_flathub(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd) or completed())

        modules.managers.Flatpak.cleanup({'candidate': 'org.mozilla.firefox'}, remove_repo=True)

        assert commands == []

    def test_cleanup_removes_explicit_remote(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd):
            commands.append(cmd)
            if cmd == 'flatpak remotes --system --columns=name,url,options':
                return completed(stdout='Name\tUrl\tOptions\ntesting\thttps://example.com/testing.flatpakrepo\tsystem\n')
            return completed()

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)
        monkeypatch.setattr(modules.managers.os, 'geteuid', lambda: 1000)

        modules.managers.Flatpak.cleanup(
            {
                'candidate': 'org.example.App',
                'remote_name': 'testing',
                'repo': 'https://example.com/testing.flatpakrepo',
            },
            remove_repo=True,
        )

        assert commands == [
            'flatpak remotes --system --columns=name,url,options',
            'sudo flatpak remote-delete --system "testing"',
        ]
