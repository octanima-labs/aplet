from pathlib import Path


class TestZypper:
    def test_repo_dir_points_to_zypp_repos_directory(self, modules):
        assert modules.managers.Zypper.REPO_DIR == Path('/etc/zypp/repos.d')

    def test_commands_use_zypper_cli(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))

        modules.managers.Zypper.update()
        modules.managers.Zypper.install('demo')
        modules.managers.Zypper.uninstall('demo')

        assert commands == [
            'sudo zypper --non-interactive update',
            'sudo zypper --non-interactive install demo',
            'sudo zypper --non-interactive remove demo',
        ]
