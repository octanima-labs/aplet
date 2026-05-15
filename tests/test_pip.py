from pathlib import Path
import shlex
from types import SimpleNamespace

from tests.conftest import completed


class TestPip:
    def test_repo_and_gpg_methods_are_noops(self, modules, capsys):
        assert modules.managers.Pip.list_gpg() == []
        assert modules.managers.Pip.list_repos() == []
        modules.managers.Pip.add_gpg('https://example.com/key')
        modules.managers.Pip.remove_gpg('key')
        modules.managers.Pip.add_repo('https://pypi.org/simple')
        modules.managers.Pip.remove_repo('repo')

        output = capsys.readouterr().out
        assert output.count('<empty list>') == 2

    def test_prepare_and_cleanup_are_noops(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Pip.prepare({'candidate': 'PyYAML'})
        modules.managers.Pip.cleanup({'candidate': 'PyYAML'}, remove_repo=True)

        assert commands == []

    def test_install_uninstall_and_update_support_versions(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Pip.install('PyYAML')
        modules.managers.Pip.install('PyYAML', version='1.1.1')
        modules.managers.Pip.install('mod-1', 'mod-2==1.1.1', 'mod-3>=1.5.1', 'mod-4', version='9.9.9')
        modules.managers.Pip.uninstall('PyYAML', version='1.1.1')
        modules.managers.Pip.update()
        modules.managers.Pip.update('PyYAML')
        modules.managers.Pip.update('PyYAML', version='1.1.1')
        modules.managers.Pip.update('PyYAML>=1.0', version='2.0.0')

        assert commands == [
            'pip install PyYAML',
            'pip install PyYAML==1.1.1',
            "pip install mod-1 mod-2==1.1.1 'mod-3>=1.5.1' mod-4",
            'pip uninstall -y PyYAML',
            'pip install --upgrade pip',
            'pip install --upgrade PyYAML',
            'pip install --upgrade PyYAML==1.1.1',
            "pip install --upgrade 'PyYAML>=1.0'",
        ]

    def test_install_creates_missing_venv_and_activates_it(self, modules, monkeypatch, tmp_path):
        commands = []
        traces = []
        infos = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())
        monkeypatch.setattr(modules.managers.logger, 'trace', lambda message: traces.append(message))
        monkeypatch.setattr(modules.managers.logger, 'info', lambda message: infos.append(message))
        venv_path = tmp_path / 'envs' / 'demo'

        modules.managers.Pip.install('PyYAML', venv=str(venv_path), version='1.1.1')

        assert venv_path.parent.exists()
        assert commands == [
            f"python -m venv {shlex.quote(str(venv_path))}",
            f"source {shlex.quote(str(venv_path / 'bin' / 'activate'))} && pip install PyYAML==1.1.1",
        ]
        assert traces == [
            f"cmd: python -m venv {shlex.quote(str(venv_path))}",
        ]
        assert infos == [
            f"Installing PyYAML==1.1.1 (source {shlex.quote(str(venv_path / 'bin' / 'activate'))} && pip install PyYAML==1.1.1)",
        ]

    def test_install_uses_powershell_activation_on_windows(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())
        monkeypatch.setattr(modules.managers.os, 'name', 'nt', raising=False)
        monkeypatch.setattr(
            modules.managers.Pip,
            '_ensure_venv',
            classmethod(lambda cls, venv: Path('C:/venvs/demo')),
        )

        modules.managers.Pip.install('PyYAML', venv='C:/venvs/demo')

        assert commands == [r"& 'C:\venvs\demo\Scripts\Activate.ps1'; pip install PyYAML"]

    def test_install_target_uses_manager_config(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Pip.install_target(
            {'candidate': 'PyYAML', 'version': '1.1.1', 'venv': '/tmp/demo-venv'},
            'PyYAML',
        )

        assert commands == [
            "python -m venv /tmp/demo-venv",
            "source /tmp/demo-venv/bin/activate && pip install PyYAML==1.1.1",
        ]

    def test_install_target_prefers_cli_specifier_and_venv_override(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Pip.install_target(
            {'candidate': 'PyYAML', 'version': '1.1.1', 'venv': '/tmp/inventory-venv'},
            'PyYAML',
            version_specifier='>=6.0',
            venv='/tmp/cli-venv',
        )

        assert commands == [
            'python -m venv /tmp/cli-venv',
            "source /tmp/cli-venv/bin/activate && pip install 'PyYAML>=6.0'",
        ]

    def test_uninstall_target_prefers_cli_venv_override(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: commands.append(cmd) or completed())

        modules.managers.Pip.uninstall_target(
            {'candidate': 'PyYAML', 'venv': '/tmp/inventory-venv'},
            'PyYAML',
            version_specifier='==1.1.1',
            venv='/tmp/cli-venv',
        )

        assert commands == ['source /tmp/cli-venv/bin/activate && pip uninstall -y PyYAML']

    def test_is_installed_target_checks_selected_environment(self, modules, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs.get('check', True)))
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        installed = modules.managers.Pip.is_installed_target(
            {'candidate': 'PyYAML==1.1.1', 'venv': '/tmp/demo-venv'},
            'PyYAML==1.1.1',
        )

        assert installed is True
        assert calls == [("source /tmp/demo-venv/bin/activate && pip show PyYAML", False)]
