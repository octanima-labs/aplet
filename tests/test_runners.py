class TestRunners:
    def test_action_from_dict_normalizes_manager_action_string(self, modules):
        action = modules.runners.Action.from_dict(
            {'brew': 'openssl readline sqlite3'},
            allowed_manager_actions=modules.managers.IMPLEMENTED,
        )

        assert action.type == 'brew'
        assert action.steps == ['openssl', 'readline', 'sqlite3']

    def test_custom_installer_run_dispatches_all_supported_action_types(self, modules, monkeypatch):
        calls = []
        traces = []
        monkeypatch.setattr(modules.runners.logger, 'trace', lambda message: traces.append(message))
        monkeypatch.setattr(
            modules.runners.ut.Shell,
            'run',
            lambda command: calls.append(('cmd', command)),
        )
        monkeypatch.setattr(
            modules.runners.ut.Files,
            'patch_file',
            lambda path, block_id, patch, app_name='PATCH': calls.append(
                ('patch_file', path, block_id, tuple(patch), app_name)
            ),
        )

        class FakeManager:
            @staticmethod
            def install(*targets):
                calls.append(('install', targets))

            @staticmethod
            def uninstall(*targets):
                calls.append(('uninstall', targets))

        installer = modules.runners.Script.from_data(
            'linux',
            [
                {'cmd': ['echo demo', 'echo done']},
                {'patch_file': ['~/.bashrc', 'demo-block', 'export DEMO=1']},
                {'apt': ['curl', 'git']},
            ],
            allowed_manager_actions=modules.managers.IMPLEMENTED,
        )

        status = installer.run(app_name='demo', manager_map={'apt': FakeManager})

        assert status == modules.runners.SCRIPT_OK
        assert calls == [
            ('cmd', 'echo demo'),
            ('cmd', 'echo done'),
            ('patch_file', '~/.bashrc', 'demo-block', ('export DEMO=1',), 'demo'),
            ('install', ('curl', 'git')),
        ]
        assert traces == [
            'cmd: echo demo',
            'cmd: echo done',
            'patch_file: ~/.bashrc demo-block',
        ]

    def test_custom_installer_run_uninstall_operation_dispatches_manager_uninstall(self, modules):
        calls = []

        class FakeManager:
            @staticmethod
            def install(*targets):
                calls.append(('install', targets))

            @staticmethod
            def uninstall(*targets):
                calls.append(('uninstall', targets))

        installer = modules.runners.Script.from_data(
            'linux',
            [{'apt': ['curl', 'git']}],
            allowed_manager_actions=modules.managers.IMPLEMENTED,
        )

        status = installer.run(app_name='demo', manager_map={'apt': FakeManager}, operation='uninstall')

        assert status == modules.runners.SCRIPT_OK
        assert calls == [('uninstall', ('curl', 'git'))]

    def test_custom_installer_run_returns_interrupted_on_keyboard_interrupt(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(
            modules.runners.ut.Shell,
            'run',
            lambda command: (_ for _ in ()).throw(KeyboardInterrupt()),
        )
        installer = modules.runners.Script.from_data('linux', [{'cmd': ['sleep 10']}])

        status = installer.run(app_name='demo', manager_map={})

        assert status == modules.runners.SCRIPT_INTERRUPTED
        assert "Installer 'linux' interrupted by user" in caplog.text

    def test_custom_installer_run_logs_exception_and_returns_error(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(
            modules.runners.ut.Shell,
            'run',
            lambda command: (_ for _ in ()).throw(RuntimeError('boom')),
        )
        installer = modules.runners.Script.from_data('linux', [{'cmd': ['false']}])

        status = installer.run(app_name='demo', manager_map={})

        assert status == modules.runners.SCRIPT_ERROR
        assert 'RuntimeError: boom' in caplog.text

    def test_custom_probe_check_runs_all_cmd_actions(self, modules, monkeypatch):
        calls = []
        monkeypatch.setattr(
            modules.runners.ut.Shell,
            'run',
            lambda command: calls.append(command),
        )

        probe = modules.runners.Probe.from_data(
            'linux',
            [{'cmd': ['demo --version', 'which demo']}],
        )

        assert probe.check() is True
        assert calls == ['demo --version', 'which demo']

    def test_custom_probe_rejects_non_cmd_actions(self, modules):
        try:
            modules.runners.Probe.from_data(
                'linux',
                [{'patch_file': ['~/.bashrc', 'demo-block', 'export DEMO=1']}],
            )
        except ValueError as exc:
            assert str(exc) == "[-] Unknown action 'patch_file'. Allowed: cmd"
        else:
            raise AssertionError('Expected invalid probe action to fail')
