class TestPackageManger:
    def test_list_methods_return_underlying_values(self, modules, monkeypatch):
        dummy = type(
            'DummyManager',
            (),
            {
                'list_gpg': staticmethod(lambda: ['key-entry']),
                'list_repos': staticmethod(lambda: ['repo-entry']),
            },
        )
        monkeypatch.setattr(modules.managers.PackageManger, 'MANAGER', dummy)

        assert modules.managers.PackageManger.list_gpg() == ['key-entry']
        assert modules.managers.PackageManger.list_repos() == ['repo-entry']

    def test_prepare_and_cleanup_delegate_to_active_manager(self, modules, monkeypatch):
        calls = []
        dummy = type(
            'DummyManager',
            (),
            {
                'prepare': staticmethod(lambda target_mgr: calls.append(('prepare', target_mgr.copy()))),
                'cleanup': staticmethod(lambda target_mgr, remove_repo=False: calls.append(('cleanup', target_mgr.copy(), remove_repo))),
            },
        )
        monkeypatch.setattr(modules.managers.PackageManger, 'MANAGER', dummy)

        modules.managers.PackageManger.prepare({'candidate': 'demo'})
        modules.managers.PackageManger.cleanup({'candidate': 'demo'}, remove_repo=True)

        assert calls == [
            ('prepare', {'candidate': 'demo'}),
            ('cleanup', {'candidate': 'demo'}, True),
        ]

    def test_install_target_passes_force_to_active_manager(self, modules, monkeypatch):
        calls = []
        dummy = type(
            'DummyManager',
            (),
            {
                'install_target': staticmethod(lambda target_mgr, candidate, force=False: calls.append((target_mgr.copy(), candidate, force))),
            },
        )
        monkeypatch.setattr(modules.managers.PackageManger, 'MANAGER', dummy)

        modules.managers.PackageManger.install_target({'candidate': 'demo'}, 'demo', force=True)

        assert calls == [({'candidate': 'demo'}, 'demo', True)]
