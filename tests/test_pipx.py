from tests.conftest import completed


class TestPipx:
    def test_repo_and_gpg_methods_are_noops(self, modules, capsys):
        assert modules.managers.Pipx.list_gpg() == []
        assert modules.managers.Pipx.list_repos() == []
        modules.managers.Pipx.add_gpg('https://example.com/key')
        modules.managers.Pipx.remove_gpg('key')
        modules.managers.Pipx.add_repo('https://example.com/repo')
        modules.managers.Pipx.remove_repo('repo')

        output = capsys.readouterr().out
        assert output.count('<empty list>') == 2

    def test_prepare_and_cleanup_are_noops(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Pipx.prepare({'candidate': 'httpie'})
        modules.managers.Pipx.cleanup({'candidate': 'httpie'}, remove_repo=True)

        assert commands == []

    def test_install_update_uninstall_and_reinstall_commands(self, modules, monkeypatch):
        commands = []
        infos = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())
        monkeypatch.setattr(modules.managers.logger, 'info', lambda message: infos.append(message))

        modules.managers.Pipx.install('httpie')
        modules.managers.Pipx.install('poetry', global_install=True)
        modules.managers.Pipx.update()
        modules.managers.Pipx.update('httpie')
        modules.managers.Pipx.update('poetry', global_install=True, include_injected=True)
        modules.managers.Pipx.reinstall('httpie')
        modules.managers.Pipx.reinstall('poetry', global_install=True, python='python3.12', fetch_missing_python=True)
        modules.managers.Pipx.uninstall('httpie')
        modules.managers.Pipx.uninstall('poetry', global_install=True)

        assert commands == [
            'pipx install httpie',
            'pipx install --global poetry',
            'pipx upgrade-all',
            'pipx upgrade httpie',
            'pipx upgrade --global --include-injected poetry',
            'pipx reinstall httpie',
            "pipx reinstall --global --python python3.12 --fetch-missing-python poetry",
            'pipx uninstall httpie',
            'pipx uninstall --global poetry',
        ]
        assert infos == [
            'Installing httpie (pipx install httpie)',
            'Installing poetry (pipx install --global poetry)',
            'Updating pipx database (pipx upgrade-all)',
            'Updating pipx database (pipx upgrade httpie)',
            'Updating pipx database (pipx upgrade --global --include-injected poetry)',
            'Installing httpie (pipx reinstall httpie)',
            'Installing poetry (pipx reinstall --global --python python3.12 --fetch-missing-python poetry)',
            'Removing httpie (pipx uninstall httpie)',
            'Removing poetry (pipx uninstall --global poetry)',
        ]

    def test_install_target_builds_command_from_manager_config(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Pipx.install_target(
            {
                'candidate': 'httpie',
                'global': True,
                'include_deps': True,
                'python': 'python3.12',
                'fetch_missing_python': True,
                'preinstall': ['setuptools', 'wheel'],
                'system_site_packages': True,
                'index_url': 'https://pypi.org/simple',
                'editable': True,
                'pip_args': '--pre',
            },
            'httpie',
        )

        assert commands == [
            "pipx install --global --include-deps --python python3.12 --fetch-missing-python --preinstall setuptools --preinstall wheel --system-site-packages --index-url https://pypi.org/simple --editable --pip-args --pre httpie"
        ]

    def test_install_target_uses_reinstall_when_forced_and_installed(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())
        monkeypatch.setattr(modules.managers.Pipx, 'is_installed_target', staticmethod(lambda target_mgr, candidate: True))

        modules.managers.Pipx.install_target(
            {'candidate': 'httpie', 'global': True, 'python': 'python3.12', 'fetch_missing_python': True},
            'httpie',
            force=True,
        )

        assert commands == ['pipx reinstall --global --python python3.12 --fetch-missing-python httpie']

    def test_list_installed_parses_short_output(self, modules, monkeypatch):
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append((cmd, kwargs.get('check', True)))
            return completed(stdout='httpie\npoetry\n')

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        installed = modules.managers.Pipx.list_installed(global_install=True)

        assert installed == ['httpie', 'poetry']
        assert commands == [('pipx list --global --short', False)]

    def test_is_installed_target_checks_scope_specific_list(self, modules, monkeypatch):
        calls = []
        monkeypatch.setattr(
            modules.managers.Pipx,
            '_list_installed_names',
            staticmethod(lambda global_install=False: calls.append(global_install) or ['httpie']),
        )

        assert modules.managers.Pipx.is_installed_target({'candidate': 'httpie', 'global': True}, 'httpie') is True
        assert calls == [True]
