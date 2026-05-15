import json

from tests.conftest import completed


class TestNpm:
    def test_repo_and_gpg_methods_are_noops(self, modules, capsys):
        assert modules.managers.Npm.list_gpg() == []
        assert modules.managers.Npm.list_repos() == []
        modules.managers.Npm.add_gpg('https://example.com/key')
        modules.managers.Npm.remove_gpg('key')
        modules.managers.Npm.add_repo('https://registry.example.com')
        modules.managers.Npm.remove_repo('registry')

        output = capsys.readouterr().out
        assert output.count('<empty list>') == 2

    def test_prepare_and_cleanup_are_noops(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Npm.prepare({'candidate': 'typescript'})
        modules.managers.Npm.cleanup({'candidate': 'typescript'}, remove_repo=True)

        assert commands == []

    def test_install_uninstall_and_update_support_global_and_local_modes(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Npm.install('typescript')
        modules.managers.Npm.install('eslint', global_install=False)
        modules.managers.Npm.uninstall('typescript')
        modules.managers.Npm.uninstall('eslint', global_install=False)
        modules.managers.Npm.update()
        modules.managers.Npm.update('typescript')
        modules.managers.Npm.update('eslint', global_install=False)

        assert commands == [
            'npm install -g typescript',
            'npm install eslint',
            'npm uninstall -g typescript',
            'npm uninstall eslint',
            'npm update -g',
            'npm update -g typescript',
            'npm update eslint',
        ]

    def test_list_installed_parses_json_output(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append((cmd, kwargs.get('check', True)))
            return completed(
                stdout=json.dumps(
                    {
                        'dependencies': {
                            '@types/node': {'version': '22.0.0'},
                            'typescript': {'version': '5.9.0'},
                        }
                    }
                )
            )

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        installed = modules.managers.Npm.list_installed()

        assert installed == ['@types/node', 'typescript']
        assert commands == [('npm ls -g --depth=0 --json', False)]

    def test_install_target_and_uninstall_target_are_always_global(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Npm.install_target({'candidate': 'typescript'}, 'typescript')
        modules.managers.Npm.uninstall_target({'candidate': 'typescript'}, 'typescript')

        assert commands == [
            'npm install -g typescript',
            'npm uninstall -g typescript',
        ]
