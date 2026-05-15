from tests.conftest import completed


class TestBrew:
    def test_list_gpg_returns_empty(self, modules, capsys):
        result = modules.managers.Brew.list_gpg()

        assert result == []
        assert '<empty list>' in capsys.readouterr().out

    def test_list_repos_and_remove_repo_by_index(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd):
            commands.append(cmd)
            if cmd == 'brew tap':
                return completed(stdout='homebrew/cask\ncustom/tools\n')
            return completed()

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        repos = modules.managers.Brew.list_repos()
        modules.managers.Brew.remove_repo(2)

        assert repos == ['custom/tools', 'homebrew/cask']
        assert commands == ['brew tap', 'brew tap', 'brew untap "homebrew/cask"']

    def test_commands_use_brew_cli(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))

        modules.managers.Brew.update()
        modules.managers.Brew.install('demo')
        modules.managers.Brew.uninstall('demo')

        assert commands == ['brew update', 'brew install demo', 'brew uninstall demo']
