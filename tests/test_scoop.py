from tests.conftest import completed


class TestScoop:
    def test_list_repos_parses_bucket_output(self, modules, monkeypatch):
        monkeypatch.setattr(
            modules.managers.ut.Shell,
            'run',
            lambda cmd: completed(stdout='Name Source\n---- ------\nmain https://github.com/ScoopInstaller/Main\nextras https://github.com/ScoopInstaller/Extras\n'),
        )

        repos = modules.managers.Scoop.list_repos()

        assert repos == [
            'extras: https://github.com/ScoopInstaller/Extras',
            'main: https://github.com/ScoopInstaller/Main',
        ]

    def test_prepare_and_cleanup_manage_bucket(self, modules, monkeypatch):
        commands = []
        state = {'buckets': []}

        def fake_run(cmd):
            commands.append(cmd)
            if cmd == 'scoop bucket list':
                stdout = '\n'.join(f"{entry['name']} {entry['source']}".rstrip() for entry in state['buckets'])
                return completed(stdout=stdout + ('\n' if stdout else ''))
            if cmd == 'scoop bucket add "extras"':
                state['buckets'].append({'name': 'extras', 'source': ''})
                return completed()
            if cmd == 'scoop bucket rm "extras"':
                state['buckets'] = []
                return completed()
            return completed()

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        modules.managers.Scoop.prepare({'candidate': 'extras/demo', 'bucket_name': 'extras'})
        modules.managers.Scoop.cleanup({'candidate': 'extras/demo', 'bucket_name': 'extras'}, remove_repo=True)

        assert commands == [
            'scoop bucket list',
            'scoop bucket add "extras"',
            'scoop update',
            'scoop bucket list',
            'scoop bucket rm "extras"',
        ]

    def test_commands_use_scoop_cli(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))

        modules.managers.Scoop.update()
        modules.managers.Scoop.install('demo')
        modules.managers.Scoop.uninstall('demo')

        assert commands == ['scoop update', 'scoop install demo', 'scoop uninstall demo']
