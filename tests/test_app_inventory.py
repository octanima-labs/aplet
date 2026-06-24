import subprocess

import yaml


class TestAppInventory:
    def test_load_supports_candidate_and_installers(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {
                    'apps': {
                        'demo': {
                            'candidate': 'demo-app',
                            'installed': True,
                            'dependencies': ['dep-app'],
                            'category': ['dev', 'editors'],
                            'tags': ['favorite', 'cli', 'favorite'],
                            'preference': ['brew', 'custom_installers'],
                            'managers': {
                                'brew': {'candidate': '--cask demo'}
                            },
                            'installers': {
                                'linux': [
                                    {'cmd': ['echo demo']},
                                    {'brew': 'openssl readline'},
                                ]
                            },
                            'uninstallers': {
                                'linux': [
                                    {'cmd': ['echo remove demo']},
                                ]
                            },
                            'post_install': {
                                'linux': [
                                    {'cmd': ['echo post install demo']},
                                ]
                            },
                        },
                        'dep-app': {},
                    }
                },
                sort_keys=False,
            )
        )

        api = modules.inventory.AppInventory().load(inventory_path)

        app = api.search('demo')
        assert app is not None
        assert app.candidate == 'demo-app'
        assert app.installed is True
        assert app.dependencies == ['dep-app']
        assert app.category == ['dev', 'editors']
        assert app.tags == ['favorite', 'cli']
        assert app.preference == ['brew', 'custom_installers']
        assert app.managers['brew']['candidate'] == '--cask demo'
        assert [action.type for action in app.installers['linux'].actions] == ['cmd', 'brew']
        assert [action.type for action in app.uninstallers['linux'].actions] == ['cmd']
        assert [action.type for action in app.post_install['linux'].actions] == ['cmd']

    def test_load_supports_probe_manager_refs_and_custom_probes(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {
                    'apps': {
                        'demo': {
                            'managers': {
                                'flatpak': {'candidate': 'org.demo.App'},
                            },
                            'probes': {
                                'flatpak': None,
                                'linux': [
                                    {'cmd': ['demo --version']},
                                ],
                            },
                        }
                    }
                },
                sort_keys=False,
            )
        )

        api = modules.inventory.AppInventory().load(inventory_path)

        app = api.get_app('demo')
        assert list(app.probes) == ['flatpak', 'linux']
        assert app.probes['flatpak'] is None
        assert [action.type for action in app.probes['linux'].actions] == ['cmd']

    def test_load_treats_missing_or_null_managers_and_installers_as_empty_mappings(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {
                    'apps': {
                        'demo': {},
                        'demo-null': {'managers': None, 'installers': None, 'uninstallers': None, 'post_install': None, 'probes': None},
                    }
                },
                sort_keys=False,
            )
        )

        api = modules.inventory.AppInventory().load(inventory_path)

        assert api.get_app('demo').managers == {}
        assert api.get_app('demo').installers == {}
        assert api.get_app('demo').uninstallers == {}
        assert api.get_app('demo').post_install == {}
        assert api.get_app('demo').probes == {}
        assert api.get_app('demo').installed is None
        assert api.get_app('demo-null').managers == {}
        assert api.get_app('demo-null').installers == {}
        assert api.get_app('demo-null').uninstallers == {}
        assert api.get_app('demo-null').post_install == {}
        assert api.get_app('demo-null').probes == {}
        assert api.get_app('demo-null').installed is None

    def test_load_treats_null_manager_entry_as_empty_mapping(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {
                    'apps': {
                        'demo': {
                            'managers': {
                                'apt': None,
                                'flatpak': {'candidate': 'org.demo.App'},
                            }
                        }
                    }
                },
                sort_keys=False,
            )
        )

        api = modules.inventory.AppInventory().load(inventory_path)

        assert api.get_app('demo').managers['apt'] == {}
        assert api.get_app('demo').managers['flatpak']['candidate'] == 'org.demo.App'

    def test_load_rejects_null_installer_entry(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'installers': {'linux': None}}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except TypeError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' installer 'linux' expects a list of actions"
        else:
            raise AssertionError('Expected null installer entry to fail')

    def test_load_rejects_null_uninstaller_entry(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'uninstallers': {'linux': None}}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except TypeError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' uninstaller 'linux' expects a list of actions"
        else:
            raise AssertionError('Expected null uninstaller entry to fail')

    def test_load_rejects_null_post_install_entry(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'post_install': {'linux': None}}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except TypeError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' post-install 'linux' expects a list of actions"
        else:
            raise AssertionError('Expected null post-install entry to fail')

    def test_load_rejects_null_probe_entry(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'probes': {'linux': None}}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except TypeError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' probe 'linux' expects a list of actions"
        else:
            raise AssertionError('Expected null probe entry to fail')

    def test_load_rejects_probe_manager_without_matching_manager_entry(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'probes': {'flatpak': None}}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except ValueError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' probe manager 'flatpak' requires a matching manager entry"
        else:
            raise AssertionError('Expected missing probe manager config to fail')

    def test_load_rejects_non_cmd_probe_actions(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {
                    'apps': {
                        'demo': {
                            'probes': {
                                'linux': [
                                    {'patch_file': ['~/.bashrc', 'demo-block', 'export DEMO=1']},
                                ]
                            }
                        }
                    }
                },
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except ValueError as exc:
            assert str(exc) == "[-] Unknown action 'patch_file'. Allowed: cmd"
        else:
            raise AssertionError('Expected invalid probe action to fail')

    def test_load_rejects_invalid_preference_entries(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {
                    'apps': {
                        'demo': {
                            'managers': {'brew': {}},
                            'preference': ['apt'],
                        }
                    }
                },
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except ValueError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' has invalid preference entries: apt"
        else:
            raise AssertionError('Expected invalid app preference to fail')

    def test_load_rejects_invalid_category_tokens(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'category': ['Dev']}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except ValueError as exc:
            assert str(exc) == "[-] Inventory entry field 'category' has invalid token 'Dev'"
        else:
            raise AssertionError('Expected invalid category token to fail')

    def test_load_rejects_invalid_tags_shape(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'tags': 'favorite'}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except TypeError as exc:
            assert str(exc) == "[-] Inventory entry field 'tags' must be a list of strings"
        else:
            raise AssertionError('Expected invalid tags shape to fail')

    def test_load_rejects_invalid_installed_value(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'installed': 'true'}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except TypeError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' field 'installed' must be true, false, or null"
        else:
            raise AssertionError('Expected invalid installed value to fail')

    def test_load_rejects_invalid_dependencies_shape(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'dependencies': 'git'}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except TypeError as exc:
            assert str(exc) == "[-] Inventory entry field 'dependencies' must be a list of strings"
        else:
            raise AssertionError('Expected invalid dependencies shape to fail')

    def test_load_rejects_unknown_dependency(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'dependencies': ['missing']}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except ValueError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' dependency 'missing' is not declared"
        else:
            raise AssertionError('Expected unknown dependency to fail')

    def test_load_rejects_self_dependency(self, modules, tmp_path):
        inventory_path = tmp_path / 'inventory.yml'
        inventory_path.write_text(
            yaml.safe_dump(
                {'apps': {'demo': {'dependencies': ['demo']}}},
                sort_keys=False,
            )
        )

        try:
            modules.inventory.AppInventory().load(inventory_path)
        except ValueError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' cannot depend on itself"
        else:
            raise AssertionError('Expected self dependency to fail')

    def test_save_preserves_installers_and_manager_specific_fields(self, modules, tmp_path):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App(
            'demo',
            preference=['linux', 'brew'],
            category=['dev', 'cli'],
            tags=['favorite', 'python'],
            installed=False,
            dependencies=['git', 'curl'],
        )
        app.add_manager(
            'choco',
            candidate='demo',
            source_name='internal',
            source_url='https://repo.example/api/v2/',
        )
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [
                    {'cmd': ['echo demo']},
                    {'patch_file': ['~/.bashrc', 'demo-block', 'export DEMO=1']},
                ],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'linux',
                [
                    {'cmd': ['echo remove demo']},
                    {'apt': ['demo-helper']},
                ],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_post_install(
            modules.runners.Script.from_data(
                'linux',
                [
                    {'cmd': ['echo post install demo']},
                ],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(modules.inventory.App('git'))
        api.add_app(modules.inventory.App('curl'))
        api.add_app(app)

        save_path = tmp_path / 'saved.yml'
        api.save(save_path)

        saved = yaml.safe_load(save_path.read_text())
        assert saved['apps']['demo']['candidate'] == 'demo'
        assert saved['apps']['demo']['installed'] is False
        assert saved['apps']['demo']['dependencies'] == ['git', 'curl']
        assert saved['apps']['demo']['category'] == ['dev', 'cli']
        assert saved['apps']['demo']['tags'] == ['favorite', 'python']
        assert saved['apps']['demo']['preference'] == ['linux', 'brew']
        assert saved['apps']['demo']['managers']['choco'] == {
            'candidate': 'demo',
            'source_name': 'internal',
            'source_url': 'https://repo.example/api/v2/',
        }
        assert saved['apps']['demo']['installers']['linux'] == [
            {'cmd': ['echo demo']},
            {'patch_file': ['~/.bashrc', 'demo-block', 'export DEMO=1']},
        ]
        assert saved['apps']['demo']['uninstallers']['linux'] == [
            {'cmd': ['echo remove demo']},
            {'apt': ['demo-helper']},
        ]
        assert saved['apps']['demo']['post_install']['linux'] == [
            {'cmd': ['echo post install demo']},
        ]

    def test_save_preserves_probes_and_formats_manager_refs_without_braces(self, modules, tmp_path):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('flatpak', candidate='org.demo.App')
        app.add_probe('flatpak')
        app.add_probe(
            'linux',
            modules.runners.Probe.from_data(
                'linux',
                [{'cmd': ['demo --version']}],
            ),
        )
        api.add_app(app)

        save_path = tmp_path / 'saved.yml'
        api.save(save_path)

        saved = yaml.safe_load(save_path.read_text())
        assert saved['apps']['demo']['probes']['flatpak'] is None
        assert saved['apps']['demo']['probes']['linux'] == [
            {'cmd': ['demo --version']},
        ]

        contents = save_path.read_text()
        assert 'probes:\n' in contents
        assert 'flatpak:\n' in contents
        assert 'flatpak: {}' not in contents

    def test_save_formats_empty_managers_and_manager_entries_without_braces(self, modules, tmp_path):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('apt')
        app.add_manager('flatpak', candidate='org.demo.App')
        api.add_app(app)

        save_path = tmp_path / 'saved.yml'
        api.save(save_path)

        contents = save_path.read_text()
        assert 'managers:\n' in contents
        assert 'installed:' not in contents
        assert 'uninstallers:' not in contents
        assert 'apt:\n' in contents
        assert 'apt: {}' not in contents
        assert 'flatpak:\n' in contents
        assert 'candidate: org.demo.App' in contents

    def test_save_preserves_unrelated_null_values_outside_manager_cleanup(self, modules):
        api = modules.inventory.AppInventory()

        cleaned = api._cleanup_empty_inventory_mappings('apps:\n  demo:\n    channel: null\n    managers: {}\n    uninstallers: {}\n')

        assert 'channel: null' in cleaned
        assert 'managers:\n' in cleaned
        assert 'uninstallers:\n' in cleaned

    def test_list_apps_detailed_uses_runtime_preference_order(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', preference=['flatpak', 'arch'])
        app.add_manager('brew', candidate='--cask demo')
        app.add_manager('flatpak', candidate='org.demo.App')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_installer(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo extra']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew', 'flatpak'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})

        assert api.list_apps(detailed=True) == ['demo (flatpak, x:arch, brew, x:linux)']

    def test_list_apps_detailed_marks_unavailable_apps(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='--cask demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['apt'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})

        assert api.list_apps(detailed=True) == ['demo (installation unavailable)']

    def test_parse_app_item_builds_app_from_single_inventory_entry(self, modules):
        api = modules.inventory.AppInventory()

        app = api.parse_app_item(
            'demo',
            {
                'candidate': 'demo-app',
                'category': ['dev', 'editors'],
                'tags': ['favorite', 'cli', 'favorite'],
                'preference': ['linux', 'brew'],
                'managers': {'brew': {'candidate': '--cask demo'}},
                'installers': {'linux': [{'cmd': ['echo demo']}]},
                'post_install': {'linux': [{'cmd': ['echo post install demo']}]},
                'probes': {
                    'brew': None,
                    'linux': [{'cmd': ['demo --version']}],
                },
            },
        )

        assert app.name == 'demo'
        assert app.candidate == 'demo-app'
        assert app.category == ['dev', 'editors']
        assert app.tags == ['favorite', 'cli']
        assert app.preference == ['linux', 'brew']
        assert app.managers['brew']['candidate'] == '--cask demo'
        assert [action.type for action in app.installers['linux'].actions] == ['cmd']
        assert [action.type for action in app.post_install['linux'].actions] == ['cmd']
        assert list(app.probes) == ['brew', 'linux']
        assert app.probes['brew'] is None
        assert [action.type for action in app.probes['linux'].actions] == ['cmd']

    def test_inventory_details_include_category_and_tags(self, modules):
        app = modules.inventory.App(
            'demo',
            category=['dev', 'editors'],
            tags=['favorite', 'cli'],
            preference=['brew'],
        )
        app.add_manager('brew', candidate='--cask demo')

        assert app.inventory_details() == (
            'demo\n'
            '  - managers: brew\n'
            '  - installers: None\n'
            '  - uninstallers: None\n'
            '  - post_install: None\n'
            '  - probes: None\n'
            '  - installed: unknown\n'
            '  - dependencies: None\n'
            '  - preference: brew\n'
            '  - category: dev > editors\n'
            '  - tags: favorite, cli'
        )

    def test_search_apps_matches_partial_name_category_prefix_and_tags(self, modules):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('httpie', category=['dev', 'cli'], tags=['favorite'])
        second = modules.inventory.App('sublime-text', category=['dev', 'editors'], tags=['gui'])
        third = modules.inventory.App('vlc', category=['media'], tags=['favorite'])
        api.add_app(first)
        api.add_app(second)
        api.add_app(third)

        assert [app.name for app in api.search_apps(names=['http'])] == ['httpie']
        assert [app.name for app in api.search_apps(categories=['dev'])] == ['httpie', 'sublime-text']
        assert [app.name for app in api.search_apps(categories=['dev > editors'])] == ['sublime-text']
        assert [app.name for app in api.search_apps(tags=['favorite'])] == ['httpie', 'vlc']

    def test_search_apps_respects_exclusive_group_matching(self, modules):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('httpie', category=['dev', 'cli'], tags=['favorite'])
        second = modules.inventory.App('http-server', category=['dev', 'servers'], tags=['network'])
        third = modules.inventory.App('vlc', category=['media'], tags=['favorite'])
        api.add_app(first)
        api.add_app(second)
        api.add_app(third)

        assert [app.name for app in api.search_apps(names=['http'], tags=['favorite'])] == ['httpie', 'http-server', 'vlc']
        assert [app.name for app in api.search_apps(names=['http'], tags=['favorite'], exclusive=True)] == ['httpie']

    def test_build_category_tree_groups_apps_and_uncategorized(self, modules):
        api = modules.inventory.AppInventory()
        api.add_app(modules.inventory.App('httpie', category=['dev', 'cli']))
        api.add_app(modules.inventory.App('zed', category=['dev', 'editors']))
        api.add_app(modules.inventory.App('helix', category=['dev', 'editors']))
        api.add_app(modules.inventory.App('vlc', category=['media']))
        api.add_app(modules.inventory.App('misc-tool'))

        tree = api.build_category_tree()

        assert sorted(tree['categories']) == ['dev', 'media']
        assert tree['categories']['dev']['total_apps'] == 3
        assert tree['categories']['dev']['children']['editors']['total_apps'] == 2
        assert tree['categories']['media']['total_apps'] == 1
        assert tree['uncategorized_total_apps'] == 1
        assert tree['total_apps'] == 5
        assert sorted(tree['categories']['dev']['children']) == ['cli', 'editors']
        assert [app.name for app in tree['categories']['dev']['children']['cli']['apps']] == ['httpie']
        assert [app.name for app in tree['categories']['dev']['children']['editors']['apps']] == ['helix', 'zed']
        assert [app.name for app in tree['categories']['media']['apps']] == ['vlc']
        assert [app.name for app in tree['uncategorized']] == ['misc-tool']

    def test_render_category_tree_uses_counts_and_custom_annotations(self, modules):
        api = modules.inventory.AppInventory()
        api.add_app(modules.inventory.App('docker', category=['dev', 'containers']))
        api.add_app(modules.inventory.App('httpie', category=['dev', 'cli']))
        custom_app = modules.inventory.App('script-tool')
        custom_app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(custom_app)
        api.add_app(modules.inventory.App('misc-tool'))

        tree = api.render_category_tree()

        assert tree.label.plain == 'apps (4)'
        assert [child.label.plain for child in tree.children] == ['dev (2)', 'uncategorized (2)']
        assert [child.label.plain for child in tree.children[0].children] == ['cli (1)', 'containers (1)']
        assert [child.label.plain for child in tree.children[0].children[0].children] == ['httpie']
        assert [child.label.plain for child in tree.children[0].children[1].children] == ['docker']
        assert [child.label.plain for child in tree.children[1].children] == ['misc-tool', 'script-tool [custom]']

    def test_render_category_tree_can_show_tags_and_methods(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('httpie', category=['dev', 'cli'], tags=['cli', 'http'])
        app.add_manager('brew', candidate='httpie')
        api.add_app(app)
        custom_app = modules.inventory.App('script-tool', category=['dev', 'cli'], tags=['automation'])
        custom_app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(custom_app)
        unavailable = modules.inventory.App('offline-tool', category=['dev', 'cli'])
        unavailable.add_manager('brew', candidate='offline-tool')
        api.add_app(unavailable)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        tree = api.render_category_tree(show_tags=True, show_methods=True)

        leaves = [child.label.plain for child in tree.children[0].children[0].children]
        assert leaves == [
            'httpie (brew) [cli, http]',
            'offline-tool (brew)',
            'script-tool [custom] (x:linux) [automation]',
        ]

    def test_render_category_tree_show_methods_marks_unavailable_apps(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', category=['dev'])
        app.add_manager('brew', candidate='demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['apt'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        tree = api.render_category_tree(show_methods=True)

        assert [child.label.plain for child in tree.children[0].children] == ['demo (installation unavailable)']

    def test_render_category_tree_show_methods_uses_uninstall_methods_for_installed_apps(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', category=['dev'], installed=True, preference=['linux', 'brew'])
        app.add_manager('brew', candidate='demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo remove demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})

        tree = api.render_category_tree(show_methods=True)

        assert [child.label.plain for child in tree.children[0].children] == ['demo (x:linux, brew)']

    def test_render_category_tree_show_methods_marks_uninstall_unavailable_for_installed_apps(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', category=['dev'], installed=True)
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        tree = api.render_category_tree(show_methods=True)

        assert [child.label.plain for child in tree.children[0].children] == ['demo [custom] (uninstall unavailable)']

    def test_render_category_tree_reuses_installed_state_per_app(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        demo = modules.inventory.App('demo', category=['dev'])
        demo.add_manager('brew', candidate='demo')
        tool = modules.inventory.App('tool', category=['dev'])
        tool.add_manager('brew', candidate='tool')
        api.add_app(demo)
        api.add_app(tool)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        calls = {'demo': 0, 'tool': 0}

        def fake_is_app_installed(app):
            calls[app.name] += 1
            return app.name == 'demo'

        monkeypatch.setattr(api, 'is_app_installed', fake_is_app_installed)

        tree = api.render_category_tree(show_methods=True, show_installed=True)

        assert [child.label.plain for child in tree.children[0].children] == ['demo (brew)', 'tool (brew)']
        assert calls == {'demo': 1, 'tool': 1}

    def test_is_app_installed_checks_available_manager_methods(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(
            modules.managers.Brew,
            'is_installed_target',
            staticmethod(lambda target_mgr, candidate: candidate == 'demo'),
        )

        assert api.is_app_installed(app) is True

    def test_is_app_installed_uses_probe_manager_refs_when_defined(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        app.add_probe('brew')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(
            modules.managers.Brew,
            'is_installed_target',
            staticmethod(lambda target_mgr, candidate: candidate == 'demo'),
        )

        assert api.is_app_installed(app) is True

    def test_is_app_installed_uses_explicit_probe_list_before_manager_scan(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        app.add_probe(
            'linux',
            modules.runners.Probe.from_data(
                'linux',
                [{'cmd': ['demo --version']}],
            ),
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(
            modules.managers.Brew,
            'is_installed_target',
            staticmethod(lambda target_mgr, candidate: (_ for _ in ()).throw(AssertionError('should not use manager scan'))),
        )
        monkeypatch.setattr(modules.runners.ut.Shell, 'run', lambda command: None)

        assert api.is_app_installed(app) is True

    def test_is_app_installed_uses_explicit_state_without_manager_checks(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        installed = modules.inventory.App('installed', installed=True)
        installed.add_manager('brew', candidate='installed')
        missing = modules.inventory.App('missing', installed=False)
        missing.add_manager('brew', candidate='missing')
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(
            modules.managers.Brew,
            'is_installed_target',
            staticmethod(lambda target_mgr, candidate: (_ for _ in ()).throw(AssertionError('should not guess'))),
        )

        assert api.is_app_installed(installed) is True
        assert api.is_app_installed(missing) is False

    def test_is_app_installed_falls_back_to_path_for_managerless_apps(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', candidate='demo-cli')
        api.add_app(app)

        calls = []

        def fake_which(target):
            calls.append(target)
            return '/usr/bin/demo-cli' if target == 'demo-cli' else None

        monkeypatch.setattr(modules.managers.shutil, 'which', fake_which)

        assert api.is_app_installed(app) is True
        assert calls == ['demo', 'demo-cli']

    def test_build_tag_groups_sorts_tags_and_collects_untagged(self, modules):
        api = modules.inventory.AppInventory()
        api.add_app(modules.inventory.App('brave', tags=['browser', 'gui']))
        api.add_app(modules.inventory.App('firefox', tags=['browser']))
        api.add_app(modules.inventory.App('tmux', tags=['cli']))
        api.add_app(modules.inventory.App('misc-tool'))

        groups = api.build_tag_groups()

        assert sorted(groups['tags']) == ['browser', 'cli', 'gui']
        assert [app.name for app in groups['tags']['browser']] == ['brave', 'firefox']
        assert [app.name for app in groups['tags']['cli']] == ['tmux']
        assert [app.name for app in groups['tags']['gui']] == ['brave']
        assert [app.name for app in groups['untagged']] == ['misc-tool']

    def test_render_tag_groups_renders_panels_with_counts(self, modules):
        api = modules.inventory.AppInventory()
        api.add_app(modules.inventory.App('brave', tags=['browser', 'gui']))
        api.add_app(modules.inventory.App('firefox', tags=['browser']))
        api.add_app(modules.inventory.App('misc-tool'))

        renderable = api.render_tag_groups()
        panels = list(renderable.renderables)

        assert [panel.title.plain for panel in panels] == ['browser (2)', 'gui (1)', 'untagged (1)']
        assert [panel.renderable.plain for panel in panels] == [
            'brave, firefox',
            'brave',
            'misc-tool',
        ]

    def test_render_tag_groups_reuses_installed_state_for_multi_tag_apps(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        brave = modules.inventory.App('brave', tags=['browser', 'gui'])
        firefox = modules.inventory.App('firefox', tags=['browser'])
        api.add_app(brave)
        api.add_app(firefox)

        calls = {'brave': 0, 'firefox': 0}

        def fake_is_app_installed(app):
            calls[app.name] += 1
            return app.name == 'brave'

        monkeypatch.setattr(api, 'is_app_installed', fake_is_app_installed)

        renderable = api.render_tag_groups(show_installed=True)
        panels = list(renderable.renderables)

        assert [panel.renderable.plain for panel in panels] == ['brave, firefox', 'brave']
        assert calls == {'brave': 1, 'firefox': 1}

    def test_render_tag_groups_shows_empty_state_when_inventory_has_no_apps(self, modules):
        api = modules.inventory.AppInventory()

        renderable = api.render_tag_groups()
        panels = list(renderable.renderables)

        assert len(panels) == 1
        assert panels[0].title.plain == 'tag-groups (0)'
        assert panels[0].renderable.plain == '<empty list>'

    def test_add_app_warns_on_duplicate_without_force(self, modules, caplog):
        api = modules.inventory.AppInventory()
        api.add_app(modules.inventory.App('demo'))

        api.add_app(modules.inventory.App('demo'))

        assert len(api.apps) == 1
        assert "App 'demo' already defined" in caplog.text

    def test_remove_app_returns_removed_instance(self, modules):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        api.add_app(app)

        removed = api.remove_app(modules.inventory.App('demo'))

        assert removed is app
        assert api.apps == []
        assert app._inventory is None

    def test_add_app_sets_owner_and_validates_existing_dependencies(self, modules):
        api = modules.inventory.AppInventory()
        dependency = modules.inventory.App('git')
        app = modules.inventory.App('demo', dependencies=['git'])

        api.add_app(dependency)
        api.add_app(app)

        assert app._inventory is api

    def test_add_app_rejects_unknown_existing_dependencies(self, modules):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', dependencies=['missing'])

        try:
            api.add_app(app)
        except ValueError as exc:
            assert str(exc) == "[-] Inventory entry 'demo' dependency 'missing' is not declared"
        else:
            raise AssertionError('Expected unknown dependency to fail')

        assert app._inventory is None

    def test_install_uses_manager_candidate_and_prepare_by_default(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='--cask demo')
        api.add_app(app)

        calls = []
        monkeypatch.setattr(modules.managers, 'INSTALLED_MGR', 'brew')
        monkeypatch.setattr(modules.managers.Brew, 'prepare', staticmethod(lambda target_mgr: calls.append(('prepare', target_mgr.copy()))))
        monkeypatch.setattr(modules.managers.Brew, 'install_target', staticmethod(lambda target_mgr, candidate, force=False: calls.append(('install', target_mgr.copy(), candidate, force))))
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])

        api.install('demo')

        assert calls == [
            ('prepare', {'candidate': '--cask demo'}),
            ('install', {'candidate': '--cask demo'}, '--cask demo', False),
        ]

    def test_install_warns_and_skips_when_dependencies_are_missing_without_needed(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        dependency = modules.inventory.App('git', installed=False)
        dependency.add_manager('brew', candidate='git')
        app = modules.inventory.App('demo', installed=False, dependencies=['git'])
        app.add_manager('brew', candidate='demo')
        api.add_app(dependency)
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(app.name))

        api.install('demo')

        assert calls == []
        assert 'Missing dependencies: git' in caplog.text

    def test_install_ignores_dependencies_that_are_already_installed(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        dependency = modules.inventory.App('git', installed=True)
        dependency.add_manager('brew', candidate='git')
        app = modules.inventory.App('demo', installed=False, dependencies=['git'])
        app.add_manager('brew', candidate='demo')
        api.add_app(dependency)
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(app.name))
        monkeypatch.setattr(api, 'save', lambda path: None)

        api.install('demo')

        assert calls == ['demo']

    def test_install_needed_installs_dependencies_before_parent(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        dependency = modules.inventory.App('git', installed=False)
        dependency.add_manager('brew', candidate='git')
        app = modules.inventory.App('demo', installed=False, dependencies=['git'])
        app.add_manager('brew', candidate='demo')
        api.add_app(dependency)
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(app.name))
        monkeypatch.setattr(api, 'save', lambda path: None)

        api.install('demo', needed=True)

        assert calls == ['git', 'demo']

    def test_install_needed_stops_when_dependency_install_fails(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        dependency = modules.inventory.App('git', installed=False)
        dependency.add_manager('brew', candidate='git')
        app = modules.inventory.App('demo', installed=False, dependencies=['git'])
        app.add_manager('brew', candidate='demo')
        api.add_app(dependency)
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])

        calls = []

        def install_named(app, manager_name, force=False, version_specifier=None, venv=None):
            calls.append(app.name)
            if app.name == 'git':
                raise RuntimeError('dependency failed')

        monkeypatch.setattr(api, '_install_via_named_manager', install_named)
        monkeypatch.setattr(api, 'save', lambda path: None)

        status = api.install('demo', needed=True)

        assert status == modules.runners.SCRIPT_ERROR
        assert calls == ['git']
        assert dependency.installed is False
        assert app.installed is False
        assert "Package-manager install failed for 'git' via 'brew': dependency failed" in caplog.text

    def test_install_needed_handles_nested_dependencies_in_order(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        base = modules.inventory.App('base', installed=False)
        base.add_manager('brew', candidate='base')
        middle = modules.inventory.App('middle', installed=False, dependencies=['base'])
        middle.add_manager('brew', candidate='middle')
        app = modules.inventory.App('demo', installed=False, dependencies=['middle'])
        app.add_manager('brew', candidate='demo')
        api.add_app(base)
        api.add_app(middle)
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(app.name))
        monkeypatch.setattr(api, 'save', lambda path: None)

        api.install('demo', needed=True)

        assert calls == ['base', 'middle', 'demo']

    def test_install_needed_detects_dependency_cycles(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first', installed=False)
        first.add_manager('brew', candidate='first')
        second = modules.inventory.App('second', installed=False)
        second.add_manager('brew', candidate='second')
        api.add_app(first)
        api.add_app(second)
        first.dependencies = ['second']
        second.dependencies = ['first']
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(app.name))

        api.install('first', needed=True)

        assert calls == []
        assert 'Dependency cycle detected: first' in caplog.text

    def test_install_needed_does_not_apply_parent_installer_override_to_dependencies(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        dependency = modules.inventory.App('git', installed=False)
        dependency.add_manager('brew', candidate='git')
        app = modules.inventory.App('demo', installed=False, dependencies=['git'])
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(dependency)
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(('manager', app.name, manager_name)))
        monkeypatch.setattr(api, '_run_installer', lambda app, installer_name: calls.append(('installer', app.name, installer_name)))
        monkeypatch.setattr(api, 'save', lambda path: None)

        api.install('demo', installer='linux', needed=True)

        assert calls == [
            ('manager', 'git', 'brew'),
            ('installer', 'demo', 'linux'),
        ]

    def test_install_runs_explicit_installer_from_cli_or_inventory(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', preference=['linux'])
        app.add_manager('brew', candidate='--cask demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo from default installer']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_installer(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo from cli installer']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})

        calls = []
        monkeypatch.setattr(
            modules.runners.Script,
            'run',
            lambda self, *, app_name, manager_map: calls.append((self.name, app_name, sorted(manager_map))),
        )

        api.install('demo')
        api.install('demo', installer='arch', force=True)

        assert calls == [
            ('linux', 'demo', sorted(modules.managers.MANAGERS)),
            ('arch', 'demo', sorted(modules.managers.MANAGERS)),
        ]

    def test_install_resolves_inline_pip_specifier_and_cli_venv(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('pyyaml', candidate='PyYAML')
        app.add_manager('pip', candidate='PyYAML', version='1.1.1', venv='/tmp/inventory-venv')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['pip'])
        monkeypatch.setattr(modules.managers.Pip, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))

        calls = []
        monkeypatch.setattr(
            modules.managers.Pip,
            'install_target',
            staticmethod(
                lambda target_mgr, candidate, force=False, version_specifier=None, venv=None: calls.append(
                    (target_mgr.copy(), candidate, force, version_specifier, venv)
                )
            ),
        )

        api.install('pyyaml==6.0.3', venv='/tmp/cli-venv')

        assert calls == [
            ({'candidate': 'PyYAML', 'version': '1.1.1', 'venv': '/tmp/inventory-venv'}, 'PyYAML', False, '==6.0.3', '/tmp/cli-venv')
        ]

    def test_install_non_pip_ignores_inline_specifier_and_warns_once_for_venv(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('demo')
        first.add_manager('brew', candidate='--cask demo')
        second = modules.inventory.App('demo-two')
        second.add_manager('brew', candidate='--cask demo-two')
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))

        calls = []
        monkeypatch.setattr(
            api,
            '_install_via_named_manager',
            lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(
                (app.name, manager_name, force, version_specifier, venv)
            ),
        )

        api.install('demo==1.2.3', 'demo-two>=2.0', venv='/tmp/demo')

        assert calls == [
            ('demo', 'brew', False, '==1.2.3', '/tmp/demo'),
            ('demo-two', 'brew', False, '>=2.0', '/tmp/demo'),
        ]
        assert caplog.text.count("Ignoring '--venv' for non-pip method 'brew'") == 1

    def test_install_uses_flatpak_manager_candidate_with_defaults(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('firefox', candidate='firefox')
        app.add_manager('flatpak', candidate='org.mozilla.firefox')
        api.add_app(app)

        calls = []
        monkeypatch.setattr(modules.managers, 'INSTALLED_MGR', 'flatpak')
        monkeypatch.setattr(modules.managers.Flatpak, 'prepare', staticmethod(lambda target_mgr: calls.append(('prepare', target_mgr.copy()))))
        monkeypatch.setattr(modules.managers.Flatpak, 'install_target', staticmethod(lambda target_mgr, candidate, force=False: calls.append(('install', target_mgr.copy(), candidate, force))))
        monkeypatch.setattr(modules.managers.Flatpak, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['flatpak'])

        api.install('firefox')

        assert calls == [
            ('prepare', {'candidate': 'org.mozilla.firefox'}),
            ('install', {'candidate': 'org.mozilla.firefox'}, 'org.mozilla.firefox', False),
        ]

    def test_install_with_npm_uses_global_install_without_update(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('typescript')
        app.add_manager('npm', candidate='typescript')
        api.add_app(app)

        commands = []
        monkeypatch.setattr(modules.managers, 'INSTALLED_MGR', 'npm')
        monkeypatch.setattr(modules.managers.PackageManger, 'MANAGER', modules.managers.Npm)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['npm'])
        monkeypatch.setattr(modules.managers.Npm, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(
            modules.managers.ut.Shell,
            'run',
            lambda cmd, **kwargs: commands.append(cmd),
        )

        api.install('typescript')

        assert commands == ['npm install -g typescript']

    def test_install_with_yay_uses_manager_candidate_without_update(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('vscode', candidate='code')
        app.add_manager('yay', candidate='visual-studio-code-bin')
        api.add_app(app)

        commands = []
        monkeypatch.setattr(modules.managers, 'INSTALLED_MGR', 'yay')
        monkeypatch.setattr(modules.managers.PackageManger, 'MANAGER', modules.managers.Yay)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['yay'])
        monkeypatch.setattr(modules.managers.Yay, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(
            modules.managers.ut.Shell,
            'run',
            lambda cmd, **kwargs: commands.append(cmd),
        )

        api.install('vscode')

        assert commands == ['yay -S --noconfirm --needed visual-studio-code-bin']

    def test_install_with_snap_uses_manager_candidate_channel_and_classic_without_update(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('vscode', candidate='code')
        app.add_manager('snap', candidate='code', channel='edge', classic=True)
        api.add_app(app)

        commands = []
        monkeypatch.setattr(modules.managers, 'INSTALLED_MGR', 'snap')
        monkeypatch.setattr(modules.managers.PackageManger, 'MANAGER', modules.managers.Snap)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['snap'])
        monkeypatch.setattr(modules.managers.Snap, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(modules.managers.os, 'geteuid', lambda: 1000)
        monkeypatch.setattr(
            modules.managers.ut.Shell,
            'run',
            lambda cmd, **kwargs: commands.append(cmd),
        )

        api.install('vscode')

        assert commands == ['sudo snap install --channel=edge --classic code']

    def test_install_force_with_pipx_uses_reinstall_without_update(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('httpie')
        app.add_manager('pipx', candidate='httpie', **{'global': True, 'python': 'python3.12', 'fetch_missing_python': True})
        api.add_app(app)

        commands = []
        monkeypatch.setattr(modules.managers, 'INSTALLED_MGR', 'pipx')
        monkeypatch.setattr(modules.managers.PackageManger, 'MANAGER', modules.managers.Pipx)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['pipx'])
        monkeypatch.setattr(modules.managers.Pipx, 'is_installed_target', staticmethod(lambda target_mgr, candidate: True))
        monkeypatch.setattr(
            modules.managers.ut.Shell,
            'run',
            lambda cmd, **kwargs: commands.append(cmd),
        )

        api.install('httpie', force=True)

        assert commands == ['pipx reinstall --global --python python3.12 --fetch-missing-python httpie']

    def test_install_prefers_first_available_method_from_runtime_preferences(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', preference=['flatpak', 'brew'])
        app.add_manager('brew', candidate='--cask demo')
        app.add_manager('flatpak', candidate='org.demo.App')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})

        calls = []
        monkeypatch.setattr(
            api,
            '_install_via_named_manager',
            lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append((app.name, manager_name, force, version_specifier, venv)),
        )

        api.install('demo')

        assert calls == [('demo', 'brew', False, None, None)]

    def test_install_skips_when_selected_manager_reports_installed(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='--cask demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: True))

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append((app.name, manager_name, force, version_specifier, venv)))

        api.install('demo')

        assert calls == []
        assert "'demo' is already installed via 'brew'" in caplog.text

    def test_install_skips_explicit_installed_state_without_manager_check(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', installed=True)
        app.add_manager('brew', candidate='--cask demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(
            modules.managers.Brew,
            'is_installed_target',
            staticmethod(lambda target_mgr, candidate: (_ for _ in ()).throw(AssertionError('should not guess'))),
        )

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(app.name))

        api.install('demo')

        assert calls == []
        assert "'demo' is already installed via 'brew'" in caplog.text

    def test_install_force_runs_even_when_selected_manager_reports_installed(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='--cask demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: True))

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append((app.name, manager_name, force, version_specifier, venv)))

        api.install('demo', force=True)

        assert calls == [('demo', 'brew', True, None, None)]

    def test_install_sets_and_saves_installed_after_manager_success(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: None)

        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        api.install('demo')

        assert app.installed is True
        assert saved == [modules.managers.ut.Config.data['DEFAULT_INVENTORY_PATH']]
        assert "Installed 'demo'" in caplog.text

    def test_install_runs_first_available_post_install_after_manager_success(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        app.add_post_install(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo post install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_post_install(
            modules.runners.Script.from_data(
                'ubuntu_debian',
                [{'cmd': ['echo post install ubuntu demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'ubuntu', 'debian'})
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(('install', app.name, manager_name)))
        monkeypatch.setattr(api, '_run_post_install', lambda app, post_install_name: calls.append(('post_install', app.name, post_install_name)))
        monkeypatch.setattr(api, 'save', lambda path: None)

        api.install('demo')

        assert calls == [
            ('install', 'demo', 'brew'),
            ('post_install', 'demo', 'linux'),
        ]

    def test_install_post_install_failure_warns_without_undoing_install(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        app.add_post_install(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo post install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: None)
        monkeypatch.setattr(api, '_run_post_install', lambda app, post_install_name: (_ for _ in ()).throw(RuntimeError('boom')))

        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        api.install('demo')

        assert app.installed is True
        assert saved == [modules.managers.ut.Config.data['DEFAULT_INVENTORY_PATH']]
        assert "Installed 'demo'" in caplog.text
        assert "Post-install 'linux' failed for 'demo': boom" in caplog.text

    def test_install_sets_and_saves_installed_after_custom_installer_success(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(modules.runners.Script, 'run', lambda self, *, app_name, manager_map: None)

        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        api.install('demo')

        assert app.installed is True
        assert saved == [modules.managers.ut.Config.data['DEFAULT_INVENTORY_PATH']]
        assert "Installed 'demo'" in caplog.text

    def test_install_custom_installer_error_continues_and_returns_error(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first')
        first.add_installer(
            modules.runners.Script.from_data('linux', [{'cmd': ['echo first']}], allowed_manager_actions=modules.managers.IMPLEMENTED)
        )
        second = modules.inventory.App('second')
        second.add_installer(
            modules.runners.Script.from_data('linux', [{'cmd': ['echo second']}], allowed_manager_actions=modules.managers.IMPLEMENTED)
        )
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(api, 'save', lambda path: None)
        calls = []

        def run_script(self, *, app_name, manager_map, operation='install', label=None):
            calls.append(app_name)
            return modules.runners.SCRIPT_ERROR if app_name == 'first' else modules.runners.SCRIPT_OK

        monkeypatch.setattr(modules.runners.Script, 'run', run_script)

        status = api.install('first', 'second')

        assert status == modules.runners.SCRIPT_ERROR
        assert calls == ['first', 'second']
        assert first.installed is None
        assert second.installed is True
        assert "Failed to install 'first'" in caplog.text
        assert "Installed 'second'" in caplog.text

    def test_install_custom_installer_interrupt_stops_and_returns_interrupted(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first')
        first.add_installer(
            modules.runners.Script.from_data('linux', [{'cmd': ['echo first']}], allowed_manager_actions=modules.managers.IMPLEMENTED)
        )
        second = modules.inventory.App('second')
        second.add_installer(
            modules.runners.Script.from_data('linux', [{'cmd': ['echo second']}], allowed_manager_actions=modules.managers.IMPLEMENTED)
        )
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        calls = []

        def run_script(self, *, app_name, manager_map, operation='install', label=None):
            calls.append(app_name)
            return modules.runners.SCRIPT_INTERRUPTED

        monkeypatch.setattr(modules.runners.Script, 'run', run_script)

        status = api.install('first', 'second')

        assert status == modules.runners.SCRIPT_INTERRUPTED
        assert calls == ['first']
        assert first.installed is None
        assert second.installed is None

    def test_install_manager_interrupt_stops_and_returns_interrupted(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first')
        first.add_manager('brew', candidate='first')
        second = modules.inventory.App('second')
        second.add_manager('brew', candidate='second')
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        calls = []

        def install_named(app, manager_name, force=False, version_specifier=None, venv=None):
            calls.append(app.name)
            raise KeyboardInterrupt()

        monkeypatch.setattr(api, '_install_via_named_manager', install_named)

        status = api.install('first', 'second')

        assert status == modules.runners.SCRIPT_INTERRUPTED
        assert calls == ['first']
        assert first.installed is None
        assert second.installed is None
        assert 'Install interrupted by user' in caplog.text

    def test_install_runs_post_install_after_custom_installer_success(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_post_install(
            modules.runners.Script.from_data(
                'ubuntu_debian',
                [{'cmd': ['echo post install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'ubuntu', 'debian'})

        calls = []

        def run_installer(self, *, app_name, manager_map, operation='install', label=None):
            calls.append((self.name, label, operation, app_name))

        monkeypatch.setattr(modules.runners.Script, 'run', run_installer)
        monkeypatch.setattr(api, 'save', lambda path: None)

        api.install('demo')

        assert calls == [
            ('linux', None, 'install', 'demo'),
            ('ubuntu_debian', 'post-install', 'install', 'demo'),
        ]

    def test_install_returns_error_when_post_install_script_fails_after_install_success(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        app.add_post_install(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo post install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: None)
        monkeypatch.setattr(api, '_run_post_install', lambda app, post_install_name: modules.runners.SCRIPT_ERROR)
        monkeypatch.setattr(api, 'save', lambda path: None)

        status = api.install('demo')

        assert status == modules.runners.SCRIPT_ERROR
        assert app.installed is True

    def test_install_skips_post_install_when_app_is_already_installed(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        app.add_post_install(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo post install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: True))

        calls = []
        monkeypatch.setattr(api, '_run_post_install', lambda app, post_install_name: calls.append((app.name, post_install_name)))

        api.install('demo')

        assert calls == []
        assert "'demo' is already installed via 'brew'" in caplog.text

    def test_install_needed_runs_post_install_for_dependencies_and_parent(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        dependency = modules.inventory.App('git', installed=False)
        dependency.add_manager('brew', candidate='git')
        dependency.add_post_install(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo post install git']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app = modules.inventory.App('demo', installed=False, dependencies=['git'])
        app.add_manager('brew', candidate='demo')
        app.add_post_install(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo post install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(dependency)
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(('install', app.name)))
        monkeypatch.setattr(api, '_run_post_install', lambda app, post_install_name: calls.append(('post_install', app.name, post_install_name)))
        monkeypatch.setattr(api, 'save', lambda path: None)

        api.install('demo', needed=True)

        assert calls == [
            ('install', 'git'),
            ('post_install', 'git', 'linux'),
            ('install', 'demo'),
            ('post_install', 'demo', 'linux'),
        ]

    def test_install_post_install_ignores_venv_with_warning(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('pip', candidate='demo')
        app.add_post_install(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo post install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['pip'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(modules.managers.Pip, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: None)
        monkeypatch.setattr(api, '_run_post_install', lambda app, post_install_name: None)
        monkeypatch.setattr(api, 'save', lambda path: None)

        api.install('demo', venv='.venv')

        assert "Ignoring '--venv' for post-install 'linux'" in caplog.text

    def test_install_skips_custom_installer_when_probe_reports_installed(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_probe(
            'linux',
            modules.runners.Probe.from_data(
                'linux',
                [{'cmd': ['demo --version']}],
            ),
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(modules.runners.ut.Shell, 'run', lambda command: None)

        calls = []
        monkeypatch.setattr(modules.runners.Script, 'run', lambda self, *, app_name, manager_map: calls.append(app_name))

        api.install('demo')

        assert calls == []
        assert "'demo' is already installed via 'linux'" in caplog.text

    def test_install_status_check_failure_returns_error(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda *args, **kwargs: ['brew'])

        def check_installed(target_mgr, candidate):
            raise RuntimeError('status failed')

        calls = []
        saved = []
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(check_installed))
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append(app.name))
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        status = api.install('demo')

        assert status == modules.runners.SCRIPT_ERROR
        assert calls == []
        assert saved == []
        assert app.installed is None
        assert "Failed to install 'demo'" in caplog.text
        assert "Package-manager install failed for 'demo' via 'brew': status failed" in caplog.text

    def test_install_failure_does_not_update_or_save_installed_state(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        monkeypatch.setattr(
            api,
            '_install_via_named_manager',
            lambda app, manager_name, force=False, version_specifier=None, venv=None: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, 'demo install', stderr='manager stderr')
            ),
        )

        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))
        exception_logs = []
        monkeypatch.setattr(modules.inventory.logger, 'exception', lambda *args, **kwargs: exception_logs.append(args))

        status = api.install('demo')

        assert status == modules.runners.SCRIPT_ERROR
        assert app.installed is None
        assert saved == []
        assert exception_logs == []
        assert "Failed to install 'demo'" in caplog.text
        assert "Package-manager install failed for 'demo' via 'brew': Command 'demo install' returned non-zero exit status 1." in caplog.text
        assert 'stderr:\nmanager stderr' in caplog.text

    def test_install_manager_error_continues_and_returns_error(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first')
        first.add_manager('brew', candidate='first')
        second = modules.inventory.App('second')
        second.add_manager('brew', candidate='second')
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: False))
        calls = []

        def install_named(app, manager_name, force=False, version_specifier=None, venv=None):
            calls.append(app.name)
            if app.name == 'first':
                raise RuntimeError('boom')

        monkeypatch.setattr(api, '_install_via_named_manager', install_named)
        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        status = api.install('first', 'second')

        assert status == modules.runners.SCRIPT_ERROR
        assert calls == ['first', 'second']
        assert first.installed is None
        assert second.installed is True
        assert saved == [modules.managers.ut.Config.data['DEFAULT_INVENTORY_PATH']]
        assert "Failed to install 'first'" in caplog.text
        assert "Installed 'second'" in caplog.text
        assert "Package-manager install failed for 'first' via 'brew': boom" in caplog.text

    def test_install_proceeds_when_manager_installed_state_is_unknown(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='--cask demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.Brew, 'is_installed_target', staticmethod(lambda target_mgr, candidate: None))

        calls = []
        monkeypatch.setattr(api, '_install_via_named_manager', lambda app, manager_name, force=False, version_specifier=None, venv=None: calls.append((app.name, manager_name, force, version_specifier, venv)))

        api.install('demo')

        assert calls == [('demo', 'brew', False, None, None)]

    def test_runtime_preference_prepends_app_preference_and_expands_custom_installers(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', preference=['flatpak', 'arch'])
        app.add_manager('brew', candidate='--cask demo')
        app.add_manager('flatpak', candidate='org.demo.App')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_installer(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo extra']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew', 'flatpak'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})
        monkeypatch.setitem(modules.managers.ut.Config.data, 'PREFERENCE', ['apt', 'brew', 'custom_installers'])

        assert api._ordered_available_methods(app) == ['flatpak', 'arch', 'brew', 'linux']

    def test_defined_methods_include_unavailable_managers_and_installers_in_preference_order(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', preference=['flatpak', 'arch'])
        app.add_manager('brew', candidate='--cask demo')
        app.add_manager('flatpak', candidate='org.demo.App')
        app.add_manager('apt', candidate='demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_installer(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo extra']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setitem(modules.managers.ut.Config.data, 'PREFERENCE', ['apt', 'brew', 'custom_installers'])

        assert api._ordered_defined_methods(app) == ['flatpak', 'arch', 'apt', 'brew', 'linux']

    def test_status_methods_use_uninstallers_when_app_is_installed(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', installed=True, preference=['linux', 'brew'])
        app.add_manager('brew', candidate='demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo remove demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})
        monkeypatch.setitem(modules.managers.ut.Config.data, 'PREFERENCE', ['custom_installers', 'brew'])

        assert api._ordered_available_methods_for_status(app, installed=True) == ['linux', 'brew']
        assert api._ordered_defined_methods_for_status(app, installed=True) == ['linux', 'brew']
        assert api._custom_method_names_for_status(app, installed=True) == {'linux'}

    def test_status_methods_use_installers_when_app_is_not_installed(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', installed=False, preference=['linux', 'brew'])
        app.add_manager('brew', candidate='demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo install demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo remove demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})

        assert api._ordered_available_methods_for_status(app, installed=False) == ['linux', 'brew']
        assert api._ordered_defined_methods_for_status(app, installed=False) == ['linux', 'brew']
        assert api._custom_method_names_for_status(app, installed=False) == {'linux'}

    def test_available_installers_use_linux_family_tokens_from_id_like(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo arch']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo linux']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_installer(
            modules.runners.Script.from_data(
                'ubuntu_debian',
                [{'cmd': ['echo ubuntu']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})

        assert api._available_methods(app)['installers'] == ['arch', 'linux']

    def test_install_ignores_uninstallers(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo remove demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        api.install('demo')

        assert "No installation method available for 'demo' on this host" in caplog.text

    def test_runtime_preference_orders_uninstallers_and_expands_custom_installers(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', preference=['linux'])
        app.add_manager('brew', candidate='demo')
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo remove demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'arch',
                [{'cmd': ['echo remove extra']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})
        monkeypatch.setitem(modules.managers.ut.Config.data, 'PREFERENCE', ['brew', 'custom_installers'])

        assert api._ordered_available_uninstall_methods(app) == ['linux', 'brew', 'arch']

    def test_uninstall_prefers_first_available_manager_from_runtime_preferences(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', preference=['linux', 'flatpak', 'brew'])
        app.add_manager('brew', candidate='--cask demo')
        app.add_manager('flatpak', candidate='org.demo.App')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux', 'arch'})

        calls = []
        monkeypatch.setattr(
            api,
            '_uninstall_via_named_manager',
            lambda app, manager_name, remove_repo=False, version_specifier=None, venv=None: calls.append((app.name, manager_name, remove_repo, version_specifier, venv)),
        )

        api.uninstall('demo', remove_repo=True)

        assert calls == [('demo', 'brew', True, None, None)]

    def test_uninstall_runs_preferred_custom_uninstaller(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', preference=['linux', 'brew'], installed=True)
        app.add_manager('brew', candidate='demo')
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo remove demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})

        calls = []
        monkeypatch.setattr(api, '_uninstall_via_named_manager', lambda app, manager_name, remove_repo=False, version_specifier=None, venv=None: calls.append(('manager', manager_name)))
        monkeypatch.setattr(api, '_run_uninstaller', lambda app, uninstaller_name: calls.append(('uninstaller', uninstaller_name)))
        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        api.uninstall('demo')

        assert calls == [('uninstaller', 'linux')]
        assert app.installed is False
        assert saved == [modules.managers.ut.Config.data['DEFAULT_INVENTORY_PATH']]

    def test_uninstall_custom_uninstaller_error_continues_and_returns_error(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first', installed=True)
        first.add_uninstaller(
            modules.runners.Script.from_data('linux', [{'cmd': ['echo first']}], allowed_manager_actions=modules.managers.IMPLEMENTED)
        )
        second = modules.inventory.App('second', installed=True)
        second.add_uninstaller(
            modules.runners.Script.from_data('linux', [{'cmd': ['echo second']}], allowed_manager_actions=modules.managers.IMPLEMENTED)
        )
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(api, 'save', lambda path: None)
        calls = []

        def run_script(self, *, app_name, manager_map, operation='install', label=None):
            calls.append(app_name)
            return modules.runners.SCRIPT_ERROR if app_name == 'first' else modules.runners.SCRIPT_OK

        monkeypatch.setattr(modules.runners.Script, 'run', run_script)

        status = api.uninstall('first', 'second')

        assert status == modules.runners.SCRIPT_ERROR
        assert calls == ['first', 'second']
        assert first.installed is True
        assert second.installed is False
        assert "Failed to remove 'first'" in caplog.text
        assert "Removed 'second'" in caplog.text

    def test_uninstall_custom_uninstaller_interrupt_stops_and_returns_interrupted(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first', installed=True)
        first.add_uninstaller(
            modules.runners.Script.from_data('linux', [{'cmd': ['echo first']}], allowed_manager_actions=modules.managers.IMPLEMENTED)
        )
        second = modules.inventory.App('second', installed=True)
        second.add_uninstaller(
            modules.runners.Script.from_data('linux', [{'cmd': ['echo second']}], allowed_manager_actions=modules.managers.IMPLEMENTED)
        )
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        calls = []

        def run_script(self, *, app_name, manager_map, operation='install', label=None):
            calls.append(app_name)
            return modules.runners.SCRIPT_INTERRUPTED

        monkeypatch.setattr(modules.runners.Script, 'run', run_script)

        status = api.uninstall('first', 'second')

        assert status == modules.runners.SCRIPT_INTERRUPTED
        assert calls == ['first']
        assert first.installed is True
        assert second.installed is True

    def test_uninstall_manager_interrupt_stops_and_returns_interrupted(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first', installed=True)
        first.add_manager('brew', candidate='first')
        second = modules.inventory.App('second', installed=True)
        second.add_manager('brew', candidate='second')
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        calls = []

        def uninstall_named(app, manager_name, remove_repo=False, version_specifier=None, venv=None):
            calls.append(app.name)
            raise KeyboardInterrupt()

        monkeypatch.setattr(api, '_uninstall_via_named_manager', uninstall_named)

        status = api.uninstall('first', 'second')

        assert status == modules.runners.SCRIPT_INTERRUPTED
        assert calls == ['first']
        assert first.installed is True
        assert second.installed is True
        assert 'Uninstall interrupted by user' in caplog.text

    def test_uninstall_resolves_inline_pip_specifier_and_cli_venv(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('pyyaml', candidate='PyYAML')
        app.add_manager('pip', candidate='PyYAML', venv='/tmp/inventory-venv')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['pip'])

        calls = []
        monkeypatch.setattr(
            modules.managers.Pip,
            'uninstall_target',
            staticmethod(
                lambda target_mgr, candidate, version_specifier=None, venv=None: calls.append(
                    (target_mgr.copy(), candidate, version_specifier, venv)
                )
            ),
        )

        api.uninstall('pyyaml==6.0.3', venv='/tmp/cli-venv')

        assert calls == [({'candidate': 'PyYAML', 'venv': '/tmp/inventory-venv'}, 'PyYAML', '==6.0.3', '/tmp/cli-venv')]

    def test_uninstall_uses_cleanup_with_remove_repo_flag(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        app.add_manager('scoop', candidate='extras/demo', bucket_name='extras')
        api.add_app(app)

        calls = []
        monkeypatch.setattr(modules.managers, 'INSTALLED_MGR', 'scoop')
        monkeypatch.setattr(modules.managers.Scoop, 'uninstall_target', staticmethod(lambda target_mgr, candidate: calls.append(('uninstall', target_mgr.copy(), candidate))))
        monkeypatch.setattr(modules.managers.Scoop, 'cleanup', staticmethod(lambda target_mgr, remove_repo=False: calls.append(('cleanup', target_mgr.copy(), remove_repo))))
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['scoop'])

        api.uninstall('demo', remove_repo=True)

        assert calls == [
            ('uninstall', {'candidate': 'extras/demo', 'bucket_name': 'extras'}, 'extras/demo'),
            ('cleanup', {'candidate': 'extras/demo', 'bucket_name': 'extras'}, True),
        ]

    def test_uninstall_sets_and_saves_installed_false_after_success(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', installed=True)
        app.add_manager('brew', candidate='demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(api, '_uninstall_via_named_manager', lambda app, manager_name, remove_repo=False, version_specifier=None, venv=None: None)

        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        api.uninstall('demo')

        assert app.installed is False
        assert saved == [modules.managers.ut.Config.data['DEFAULT_INVENTORY_PATH']]
        assert "Removed 'demo'" in caplog.text

    def test_uninstall_custom_uninstaller_failure_does_not_update_or_save_installed_state(self, modules, monkeypatch):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', installed=True)
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo remove demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'host_install_tokens', lambda: {'linux'})
        monkeypatch.setattr(api, '_run_uninstaller', lambda app, uninstaller_name: (_ for _ in ()).throw(RuntimeError('boom')))

        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        try:
            api.uninstall('demo')
        except RuntimeError as exc:
            assert str(exc) == 'boom'
        else:
            raise AssertionError('Expected uninstall failure')

        assert app.installed is True
        assert saved == []

    def test_uninstall_failure_does_not_update_or_save_installed_state(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo', installed=True)
        app.add_manager('brew', candidate='demo')
        api.add_app(app)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        monkeypatch.setattr(api, '_uninstall_via_named_manager', lambda app, manager_name, remove_repo=False, version_specifier=None, venv=None: (_ for _ in ()).throw(RuntimeError('boom')))

        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        status = api.uninstall('demo')

        assert status == modules.runners.SCRIPT_ERROR
        assert app.installed is True
        assert saved == []
        assert "Failed to remove 'demo'" in caplog.text
        assert "Package-manager uninstall failed for 'demo' via 'brew': boom" in caplog.text

    def test_uninstall_manager_error_continues_and_returns_error(self, modules, monkeypatch, caplog):
        api = modules.inventory.AppInventory()
        first = modules.inventory.App('first', installed=True)
        first.add_manager('brew', candidate='first')
        second = modules.inventory.App('second', installed=True)
        second.add_manager('brew', candidate='second')
        api.add_app(first)
        api.add_app(second)
        monkeypatch.setattr(modules.managers.ut.Platform, 'detect_package_managers', lambda: ['brew'])
        calls = []

        def uninstall_named(app, manager_name, remove_repo=False, version_specifier=None, venv=None):
            calls.append(app.name)
            if app.name == 'first':
                raise RuntimeError('boom')

        monkeypatch.setattr(api, '_uninstall_via_named_manager', uninstall_named)
        saved = []
        monkeypatch.setattr(api, 'save', lambda path: saved.append(path))

        status = api.uninstall('first', 'second')

        assert status == modules.runners.SCRIPT_ERROR
        assert calls == ['first', 'second']
        assert first.installed is True
        assert second.installed is False
        assert saved == [modules.managers.ut.Config.data['DEFAULT_INVENTORY_PATH']]
        assert "Failed to remove 'first'" in caplog.text
        assert "Removed 'second'" in caplog.text
        assert "Package-manager uninstall failed for 'first' via 'brew': boom" in caplog.text
