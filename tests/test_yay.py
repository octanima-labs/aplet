from tests.conftest import completed


class TestYay:
    def test_repo_and_gpg_methods_are_noops(self, modules, capsys):
        assert modules.managers.Yay.list_gpg() == []
        assert modules.managers.Yay.list_repos() == []
        modules.managers.Yay.add_gpg('https://example.com/key')
        modules.managers.Yay.remove_gpg('key')
        modules.managers.Yay.add_repo('repo')
        modules.managers.Yay.remove_repo('repo')

        output = capsys.readouterr().out
        assert output.count('<empty list>') == 2

    def test_prepare_and_cleanup_are_noops(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Yay.prepare({'candidate': 'visual-studio-code-bin'})
        modules.managers.Yay.cleanup({'candidate': 'visual-studio-code-bin'}, remove_repo=True)

        assert commands == []

    def test_install_uninstall_and_update_commands(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Yay.install('visual-studio-code-bin')
        modules.managers.Yay.uninstall('visual-studio-code-bin')
        modules.managers.Yay.update()

        assert commands == [
            'yay -S --noconfirm --needed visual-studio-code-bin',
            'yay -Rns --noconfirm visual-studio-code-bin',
            'yay -Syu --noconfirm',
        ]

    def test_list_installed_parses_qq_output(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append((cmd, kwargs.get('check', True)))
            return completed(stdout='git\nvisual-studio-code-bin\n')

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        installed = modules.managers.Yay.list_installed()

        assert installed == ['git', 'visual-studio-code-bin']
        assert commands == [('yay -Qq', False)]

    def test_install_target_and_uninstall_target_use_manager_candidate(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Yay.install_target({'candidate': 'visual-studio-code-bin'}, 'visual-studio-code-bin')
        modules.managers.Yay.uninstall_target({'candidate': 'visual-studio-code-bin'}, 'visual-studio-code-bin')

        assert commands == [
            'yay -S --noconfirm --needed visual-studio-code-bin',
            'yay -Rns --noconfirm visual-studio-code-bin',
        ]
