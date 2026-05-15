from tests.conftest import completed


class TestChoco:
    def test_list_repos_parses_limit_output_sources(self, modules, monkeypatch):
        monkeypatch.setattr(
            modules.managers.ut.Shell,
            'run',
            lambda cmd: completed(stdout='chocolatey|https://community.chocolatey.org/api/v2/\ninternal|https://repo.example/api/v2/\n'),
        )

        repos = modules.managers.Choco.list_repos()

        assert repos == [
            'chocolatey: https://community.chocolatey.org/api/v2/',
            'internal: https://repo.example/api/v2/',
        ]

    def test_prepare_and_cleanup_manage_named_source(self, modules, monkeypatch):
        commands = []
        state = {'sources': []}

        def fake_run(cmd):
            commands.append(cmd)
            if cmd == 'choco source list --limit-output':
                stdout = '\n'.join(f"{entry['name']}|{entry['source']}" for entry in state['sources'])
                return completed(stdout=stdout + ('\n' if stdout else ''))
            if cmd.startswith('choco source add '):
                state['sources'].append({'name': 'internal', 'source': 'https://repo.example/api/v2/'})
                return completed()
            if cmd.startswith('choco source remove '):
                state['sources'] = []
                return completed()
            return completed()

        monkeypatch.setattr(modules.managers.ut.Shell, 'run', fake_run)

        modules.managers.Choco.prepare({'candidate': 'demo', 'source_name': 'internal', 'source_url': 'https://repo.example/api/v2/'})
        modules.managers.Choco.cleanup({'candidate': 'demo', 'source_name': 'internal'}, remove_repo=True)

        assert commands == [
            'choco source list --limit-output',
            'choco source add -n="internal" -s="https://repo.example/api/v2/"',
            'choco source list --limit-output',
            'choco source remove -n="internal"',
        ]

    def test_commands_use_choco_cli(self, modules, monkeypatch):
        commands = []
        monkeypatch.setattr(modules.managers.ut.Shell, 'run', lambda cmd: commands.append(cmd))

        modules.managers.Choco.update()
        modules.managers.Choco.install('demo')
        modules.managers.Choco.uninstall('demo')

        assert commands == ['choco install -y demo', 'choco uninstall -y demo']
