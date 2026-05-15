from tests.conftest import completed


class TestSnap:
    def test_repo_and_gpg_methods_are_noops(self, modules, capsys):
        assert modules.managers.Snap.list_gpg() == []
        assert modules.managers.Snap.list_repos() == []
        modules.managers.Snap.add_gpg('https://example.com/key')
        modules.managers.Snap.remove_gpg('key')
        modules.managers.Snap.add_repo('repo')
        modules.managers.Snap.remove_repo('repo')

        output = capsys.readouterr().out
        assert output.count('<empty list>') == 2

    def test_prepare_and_cleanup_are_noops(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Snap.prepare({'candidate': 'vlc'})
        modules.managers.Snap.cleanup({'candidate': 'vlc'}, remove_repo=True)

        assert commands == []

    def test_install_supports_optional_channel_and_classic(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())
        monkeypatch.setattr(modules.managers.os, 'geteuid', lambda: 1000)

        modules.managers.Snap.install('vlc')
        modules.managers.Snap.install('vlc', channel='edge')
        modules.managers.Snap.install('code', classic=True)
        modules.managers.Snap.install('code', channel='stable', classic=True)

        assert commands == [
            'sudo snap install vlc',
            'sudo snap install --channel=edge vlc',
            'sudo snap install --classic code',
            'sudo snap install --channel=stable --classic code',
        ]

    def test_uninstall_and_update_commands(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())
        monkeypatch.setattr(modules.managers.os, 'geteuid', lambda: 1000)

        modules.managers.Snap.uninstall('vlc')
        modules.managers.Snap.update()
        modules.managers.Snap.update('vlc')

        assert commands == [
            'sudo snap remove vlc',
            'sudo snap refresh',
            'sudo snap refresh vlc',
        ]

    def test_list_installed_parses_snap_list_output(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            return completed(
                stdout='Name    Version    Rev    Tracking    Publisher    Notes\nvlc     3.0.21     2000   latest/stable  videolan✓  -\ncode    1.97.0     180    latest/stable  vscode✓    classic\n'
            )

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        installed = modules.managers.Snap.list_installed()

        assert installed == ['vlc', 'code']
        assert commands == ['sudo snap list']

    def test_install_target_uses_channel_and_classic_from_manager_config(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())
        monkeypatch.setattr(modules.managers.os, 'geteuid', lambda: 1000)

        modules.managers.Snap.install_target({'candidate': 'code', 'channel': 'edge', 'classic': True}, 'code')
        modules.managers.Snap.uninstall_target({'candidate': 'code', 'channel': 'edge', 'classic': True}, 'code')

        assert commands == [
            'sudo snap install --channel=edge --classic code',
            'sudo snap remove code',
        ]
