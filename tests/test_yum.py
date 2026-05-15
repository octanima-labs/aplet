class TestYum:
    def test_commands_use_yum_cli(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))

        modules.managers.Yum.update()
        modules.managers.Yum.install('demo')
        modules.managers.Yum.uninstall('demo')

        assert commands == ['sudo yum update -y', 'sudo yum install -y demo', 'sudo yum remove -y demo']
