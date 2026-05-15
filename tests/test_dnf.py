class TestDnf:
    def test_commands_use_dnf_cli(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))

        modules.managers.Dnf.update()
        modules.managers.Dnf.install('demo')
        modules.managers.Dnf.uninstall('demo')

        assert commands == ['sudo dnf upgrade --refresh -y', 'sudo dnf install -y demo', 'sudo dnf remove -y demo']
