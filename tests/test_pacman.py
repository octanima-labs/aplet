from tests.conftest import completed


class TestPacman:
    def test_list_gpg_formats_fingerprint_entries(self, modules, monkeypatch, capsys):
        output = '''/etc/pacman.d/gnupg/pubring.gpg
-------------------------------
pub   rsa4096 2026-04-19 [SC]
      5C9E 46ED A15B D3DA 48C5  B6FE ABC5 4C6A 04F0 1098
uid           [ultimate] Pacman Keyring Master Key <pacman@localhost>
'''
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: completed(stdout=output))

        result = modules.managers.Pacman.list_gpg()

        assert result == ['5C9E46EDA15BD3DA48C5B6FEABC54C6A04F01098']
        assert 'Pacman Keyring Master Key <pacman@localhost>' in capsys.readouterr().out

    def test_primary_fingerprints_from_key_file_ignores_subkeys(self, modules, monkeypatch, tmp_path):
        key_file = tmp_path / 'repo.gpg'
        key_file.write_text('key')
        gpg_output = '''pub:-:4096:1:AAAAAAAAAAAAAAAA:1:::-:::scESC::::::23::0:
fpr:::::::::1111111111111111111111111111111111111111:
uid:-::::1::hash::Demo One <one@example.com>::::::::::0:
sub:-:4096:1:BBBBBBBBBBBBBBBB:1::::::e::::::23:
fpr:::::::::2222222222222222222222222222222222222222:
pub:-:4096:1:CCCCCCCCCCCCCCCC:1:::-:::scESC::::::23::0:
fpr:::::::::3333333333333333333333333333333333333333:
'''
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd, **kwargs: completed(stdout=gpg_output))

        result = modules.managers.Pacman._primary_fingerprints_from_key_file(key_file)

        assert result == [
            '1111111111111111111111111111111111111111',
            '3333333333333333333333333333333333333333',
        ]

    def test_add_gpg_locally_signs_all_primary_keys(self, modules, monkeypatch):
        gpg_output = '''pub:-:4096:1:AAAAAAAAAAAAAAAA:1:::-:::scESC::::::23::0:
fpr:::::::::1111111111111111111111111111111111111111:
pub:-:4096:1:BBBBBBBBBBBBBBBB:1:::-:::scESC::::::23::0:
fpr:::::::::2222222222222222222222222222222222222222:
'''
        commands = []

        def run(cmd, **kwargs):
            commands.append(cmd)
            if cmd.startswith('gpg --show-keys'):
                return completed(stdout=gpg_output)
            return completed()

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', run)

        modules.managers.Pacman.add_gpg('https://example.com/repo.gpg')

        assert any(command.startswith('curl -fsSL "https://example.com/repo.gpg"') for command in commands)
        assert commands.count('sudo pacman-key --lsign-key 1111111111111111111111111111111111111111') == 1
        assert commands.count('sudo pacman-key --lsign-key 2222222222222222222222222222222222222222') == 1

    def test_add_gpg_signs_existing_key_from_downloaded_file(self, modules, monkeypatch):
        commands = []

        def run(cmd, **kwargs):
            commands.append(cmd)
            if cmd.startswith('gpg --show-keys'):
                return completed(stdout='pub:-:4096:1:AAAAAAAAAAAAAAAA:1:::-:::scESC::::::23::0:\nfpr:::::::::1111111111111111111111111111111111111111:\n')
            return completed()

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', run)

        modules.managers.Pacman.add_gpg('https://example.com/repo.gpg')

        assert 'sudo pacman-key --lsign-key 1111111111111111111111111111111111111111' in commands

    def test_resolve_key_target_handles_unique_suffix_and_ambiguity(self, modules, caplog):
        entries = [
            {'fingerprint': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA', 'uid': 'first'},
            {'fingerprint': 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB12345678', 'uid': 'second'},
        ]

        assert modules.managers.Pacman._resolve_key_target('12345678', entries) == entries[1]
        assert modules.managers.Pacman._resolve_key_target(1, entries) == entries[0]
        assert modules.managers.Pacman._resolve_key_target('missing', entries) is None
        assert "No GPG key match for 'missing'" in caplog.text

    def test_add_repo_writes_managed_include_and_stanza(self, modules, monkeypatch, tmp_path):
        conf_file = tmp_path / 'pacman.conf'
        include_file = tmp_path / 'pacman.d' / 'aplet.conf'
        conf_file.write_text('[options]\nColor\n')
        monkeypatch.setattr(modules.managers.Pacman, 'CONF_FILE', conf_file)
        monkeypatch.setattr(modules.managers.Pacman, 'REPO_INCLUDE_FILE', include_file)
        monkeypatch.setattr(modules.managers.Pacman, 'REPO_INCLUDE_LINE', f'Include = {include_file}')

        modules.managers.Pacman.add_repo('\n[demo]\nServer = https://example.com/$arch')

        assert f'Include = {include_file}' in conf_file.read_text()
        assert '[demo]' in include_file.read_text()

    def test_remove_repo_rewrites_managed_include_file(self, modules, monkeypatch, tmp_path):
        include_file = tmp_path / 'pacman.d' / 'aplet.conf'
        include_file.parent.mkdir(parents=True)
        include_file.write_text('[first]\nServer = https://example.com/first\n\n[second]\nServer = https://example.com/second\n')
        monkeypatch.setattr(modules.managers.Pacman, 'REPO_INCLUDE_FILE', include_file)

        modules.managers.Pacman.remove_repo('second')

        contents = include_file.read_text()
        assert '[first]' in contents
        assert '[second]' not in contents

    def test_remove_repo_rewrites_legacy_managed_include_file(self, modules, monkeypatch, tmp_path):
        include_file = tmp_path / 'pacman.d' / 'aplet.conf'
        legacy_include_file = tmp_path / 'pacman.d' / 'applet.conf'
        include_file.parent.mkdir(parents=True)
        legacy_include_file.write_text('[demo]\nServer = https://example.com/demo\n')
        monkeypatch.setattr(modules.managers.Pacman, 'REPO_INCLUDE_FILE', include_file)
        monkeypatch.setattr(modules.managers.Pacman, 'LEGACY_REPO_INCLUDE_FILE', legacy_include_file)

        modules.managers.Pacman.remove_repo('demo')

        assert legacy_include_file.read_text() == ''

    def test_install_uses_single_sync_command(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))

        modules.managers.Pacman.install('demo')

        assert commands == ['sudo pacman -S --noconfirm --needed demo']
