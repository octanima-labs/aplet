class TestApt:
    def test_list_gpg_returns_sorted_keyring_files(self, modules, monkeypatch, tmp_path, capsys):
        keyring_dir = tmp_path / 'keyrings'
        keyring_dir.mkdir()
        (keyring_dir / 'b.asc').write_text('b')
        (keyring_dir / 'a.asc').write_text('a')
        monkeypatch.setattr(modules.managers.Apt, 'KEYRING_DIR', keyring_dir)

        result = modules.managers.Apt.list_gpg()

        assert [path.name for path in result] == ['a.asc', 'b.asc']
        assert '  1. a.asc' in capsys.readouterr().out

    def test_add_repo_writes_named_sources_file(self, modules, monkeypatch, tmp_path):
        sources_dir = tmp_path / 'sources.list.d'
        monkeypatch.setattr(modules.managers.Apt, 'SOURCES_DIR', sources_dir)

        modules.managers.Apt.add_repo('Types: deb\nURIs: https://example.com/', name='demo')

        assert (sources_dir / 'demo.sources').read_text() == 'Types: deb\nURIs: https://example.com/'

    def test_remove_repo_by_index_unlinks_target_file(self, modules, monkeypatch, tmp_path):
        sources_dir = tmp_path / 'sources.list.d'
        sources_dir.mkdir()
        (sources_dir / 'a.sources').write_text('a')
        (sources_dir / 'b.sources').write_text('b')
        monkeypatch.setattr(modules.managers.Apt, 'SOURCES_DIR', sources_dir)

        modules.managers.Apt.remove_repo(2)

        assert (sources_dir / 'a.sources').exists()
        assert not (sources_dir / 'b.sources').exists()

    def test_commands_use_apt_cli(self, modules, monkeypatch):
        commands = []
        infos = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))
        monkeypatch.setattr(modules.managers.logger, 'info', lambda message: infos.append(message))

        modules.managers.Apt.update()
        modules.managers.Apt.install('demo')
        modules.managers.Apt.uninstall('demo')

        assert commands == [
            'sudo apt-get update',
            'sudo apt-get upgrade -y',
            'sudo apt-get install -y demo',
            'sudo apt-get remove -y demo',
        ]
        assert infos == [
            'Updating apt database (sudo apt-get update)',
            'Updating apt database (sudo apt-get upgrade -y)',
            'Installing demo (sudo apt-get install -y demo)',
            'Removing demo (sudo apt-get remove -y demo)',
        ]

    def test_add_gpg_traces_final_preparation_commands(self, modules, monkeypatch, tmp_path):
        commands = []
        traces = []
        monkeypatch.setattr(modules.managers.Apt, 'KEYRING_DIR', tmp_path / 'keyrings')
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))
        monkeypatch.setattr(modules.managers.logger, 'trace', lambda message: traces.append(message))

        modules.managers.Apt.add_gpg('https://example.com/demo.asc')

        assert commands == [
            f'sudo install -d "{tmp_path / "keyrings"}"',
            f'sudo wget -qO - https://example.com/demo.asc | tee "{tmp_path / "keyrings" / "demo.asc"}" > /dev/null',
        ]
        assert traces == [f'cmd: {command}' for command in commands]
