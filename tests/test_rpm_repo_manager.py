from tests.conftest import completed


class TestRpmRepoManager:
    def test_list_rpm_gpg_entries_parses_package_query(self, modules, monkeypatch):
        output = 'gpg-pubkey-11111111-22222222\tExample Signing Key\n'
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: completed(stdout=output))

        entries = modules.managers._RpmRepoManager._list_rpm_gpg_entries()

        assert entries == [{'package': 'gpg-pubkey-11111111-22222222', 'summary': 'Example Signing Key'}]

    def test_list_repos_formats_aplet_owned_repo_files(self, modules, monkeypatch, tmp_path, capsys):
        repo_dir = tmp_path / 'repos.d'
        repo_dir.mkdir()
        (repo_dir / 'aplet-demo.repo').write_text('[demo]\nname=Demo\nbaseurl=https://example.com/demo\n')
        (repo_dir / 'other.repo').write_text('[other]\nname=Other\nbaseurl=https://example.com/other\n')

        class Dummy(modules.managers._RpmRepoManager):
            REPO_DIR = repo_dir

        result = Dummy.list_repos()

        assert result == ['aplet-demo.repo: demo']
        assert 'aplet-demo.repo: demo' in capsys.readouterr().out

    def test_list_repos_includes_legacy_applet_owned_repo_files(self, modules, monkeypatch, tmp_path, capsys):
        repo_dir = tmp_path / 'repos.d'
        repo_dir.mkdir()
        (repo_dir / 'applet-demo.repo').write_text('[demo]\nname=Demo\nbaseurl=https://example.com/demo\n')

        class Dummy(modules.managers._RpmRepoManager):
            REPO_DIR = repo_dir

        result = Dummy.list_repos()

        assert result == ['applet-demo.repo: demo']
        assert 'applet-demo.repo: demo' in capsys.readouterr().out

    def test_remove_repo_by_section_rewrites_remaining_sections(self, modules, tmp_path):
        repo_dir = tmp_path / 'repos.d'
        repo_dir.mkdir()
        repo_file = repo_dir / 'aplet-demo.repo'
        repo_file.write_text('[first]\nname=First\nbaseurl=https://example.com/first\n\n[second]\nname=Second\nbaseurl=https://example.com/second\n')

        class Dummy(modules.managers._RpmRepoManager):
            REPO_DIR = repo_dir

        Dummy.remove_repo('second')

        contents = repo_file.read_text()
        assert '[first]' in contents
        assert '[second]' not in contents

    def test_derive_repo_target_uses_prefixed_repo_filename(self, modules):
        class Dummy(modules.managers._RpmRepoManager):
            pass

        target = Dummy._derive_repo_target({'repo': 'https://example.com/demo.repo'})

        assert target == 'aplet-demo.repo'
