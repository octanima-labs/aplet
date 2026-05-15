import sys
import yaml
from pathlib import Path


class TestCLI:
    def test_cli_parser_parses_install_installer(self, modules):
        args = modules.main.cli_parser().parse_args(['install', '--installer', 'linux', '-f', '--needed', '--venv', '/tmp/demo', 'demo'])

        assert args.cmd == 'install'
        assert args.verbose == 0
        assert args.targets == ['demo']
        assert args.installer == 'linux'
        assert args.force is True
        assert args.needed is True
        assert args.venv == '/tmp/demo'

    def test_cli_parser_parses_root_verbosity(self, modules):
        parser = modules.main.cli_parser()

        assert parser.parse_args(['install', 'demo']).verbose == 0
        assert parser.parse_args(['-v', 'install', 'demo']).verbose == 1
        assert parser.parse_args(['-vv', 'install', 'demo']).verbose == 2
        assert parser.parse_args(['-vvv', 'install', 'demo']).verbose == 3

    def test_log_level_from_verbosity(self, modules):
        assert modules.main._log_level_from_verbosity(0) == 'INFO'
        assert modules.main._log_level_from_verbosity(1) == 'DEBUG'
        assert modules.main._log_level_from_verbosity(2) == 'TRACE'
        assert modules.main._log_level_from_verbosity(3) == 'TRACE'

    def test_cli_parser_parses_uninstall_remove_repo(self, modules):
        args = modules.main.cli_parser().parse_args(['uninstall', '-r', '--venv', '/tmp/demo', 'demo'])

        assert args.cmd == 'uninstall'
        assert args.targets == ['demo']
        assert args.remove_repo is True
        assert args.venv == '/tmp/demo'

    def test_cli_parser_parses_inventory_subcommands(self, modules):
        list_args = modules.main.cli_parser().parse_args(['inv', 'list', '--tags', '--installed'])
        all_args = modules.main.cli_parser().parse_args(['inv', 'list', '--all'])
        tree_args = modules.main.cli_parser().parse_args(['inv', 'list', '--categories', '--show-tags', '--show-methods'])
        tag_group_args = modules.main.cli_parser().parse_args(['inv', 'list', '--tag-groups'])
        search_args = modules.main.cli_parser().parse_args([
            'inv', 'search', '-d', '-n', 'http', '-c', 'dev > editors', '-t', 'favorite', 'cli', '-e'
        ])
        rm_args = modules.main.cli_parser().parse_args(['inv', 'rm', '-f', 'demo'])
        edit_args = modules.main.cli_parser().parse_args(['inv', 'edit'])
        add_args = modules.main.cli_parser().parse_args(['inv', 'add', '-f', '--source', 'item.yml'])

        assert list_args.cmd == 'inv'
        assert list_args.inv_cmd == 'list'
        assert list_args.tags is True
        assert list_args.installed is True
        assert all_args.inv_cmd == 'list'
        assert all_args.all is True
        assert tree_args.inv_cmd == 'list'
        assert tree_args.categories is True
        assert tree_args.show_tags is True
        assert tree_args.show_methods is True
        assert tag_group_args.inv_cmd == 'list'
        assert tag_group_args.tag_groups is True
        assert search_args.inv_cmd == 'search'
        assert search_args.details is True
        assert search_args.name == ['http']
        assert search_args.category == ['dev > editors']
        assert search_args.tags == ['favorite', 'cli']
        assert search_args.exclusive is True
        assert rm_args.cmd == 'inv'
        assert rm_args.inv_cmd == 'rm'
        assert rm_args.name == 'demo'
        assert rm_args.force is True
        assert edit_args.inv_cmd == 'edit'
        assert add_args.inv_cmd == 'add'
        assert add_args.force is True
        assert add_args.source == 'item.yml'

    def test_main_conf_calls_open_conf(self, modules, monkeypatch):
        calls = []
        monkeypatch.setattr(sys, 'argv', ['aplet', 'conf', '-r'])
        monkeypatch.setattr(modules.main.ut.Config, 'open', lambda read_only: calls.append(read_only))

        modules.main.main()

        assert calls == [True]

    def test_main_install_calls_inventory_with_all_targets_and_installer(self, modules, monkeypatch):
        calls = []

        class FakeInventory:
            def install(self, *targets, installer=None, force=False, venv=None, needed=False):
                calls.append((targets, installer, force, venv, needed))

        monkeypatch.setattr(sys, 'argv', ['aplet', 'install', '--installer', 'linux', '-f', '--needed', '--venv', '/tmp/demo', 'one', 'two'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())

        modules.main.main()

        assert calls == [(('one', 'two'), 'linux', True, '/tmp/demo', True)]

    def test_main_configures_logging_from_verbosity(self, modules, monkeypatch):
        levels = []

        class FakeInventory:
            def install(self, *targets, installer=None, force=False, venv=None, needed=False):
                return 0

        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut, 'configure_logging', lambda level='INFO': levels.append(level))

        modules.main.main(['install', 'demo'])
        modules.main.main(['-v', 'install', 'demo'])
        modules.main.main(['-vv', 'install', 'demo'])
        modules.main.main(['-vvv', 'install', 'demo'])

        assert levels == ['INFO', 'DEBUG', 'TRACE', 'TRACE']

    def test_main_install_returns_inventory_status(self, modules, monkeypatch):
        class FakeInventory:
            def install(self, *targets, installer=None, force=False, venv=None, needed=False):
                return 1

        monkeypatch.setattr(sys, 'argv', ['aplet', 'install', 'demo'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())

        assert modules.main.main() == 1

    def test_main_keyboard_interrupt_returns_interrupted(self, modules, monkeypatch, caplog):
        class FakeInventory:
            def install(self, *targets, installer=None, force=False, venv=None, needed=False):
                raise KeyboardInterrupt()

        monkeypatch.setattr(sys, 'argv', ['aplet', 'install', 'demo'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())

        assert modules.main.main() == modules.runners.SCRIPT_INTERRUPTED
        assert 'Execution interrupted by user' in caplog.text

    def test_main_uninstall_passes_remove_repo_flag(self, modules, monkeypatch):
        calls = []

        class FakeInventory:
            def uninstall(self, *targets, remove_repo=False, venv=None):
                calls.append((targets, remove_repo, venv))

        monkeypatch.setattr(sys, 'argv', ['aplet', 'uninstall', '-r', '--venv', '/tmp/demo', 'demo'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())

        modules.main.main()

        assert calls == [(('demo',), True, '/tmp/demo')]

    def test_main_uninstall_returns_inventory_status(self, modules, monkeypatch):
        class FakeInventory:
            def uninstall(self, *targets, remove_repo=False, venv=None):
                return 2

        monkeypatch.setattr(sys, 'argv', ['aplet', 'uninstall', 'demo'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())

        assert modules.main.main() == 2

    def test_main_inventory_default_list_uses_availability_labels(self, modules, monkeypatch):
        printed = []

        class FakeApp:
            def inventory_label(self, methods=None, *, installed=False, custom_methods=None):
                state = 'installed' if installed else 'missing'
                return f"{state} demo ({', '.join(methods)})"

        class FakeInventory:
            _apps = [FakeApp()]

            def _ordered_available_methods_for_status(self, app, installed):
                return ['brew', 'linux'] if installed else ['apt']

            def _custom_method_names_for_status(self, app, installed):
                return {'linux'} if installed else set()

            def is_app_installed(self, app):
                return True

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['installed demo (brew, linux)']]

    def test_main_inventory_list_installed_filters_apps(self, modules, monkeypatch):
        printed = []
        calls = []

        class FakeApp:
            def __init__(self, name):
                self.name = name

            def inventory_label(self, methods=None, *, installed=False, custom_methods=None):
                return f"{self.name} ({', '.join(methods)}) installed={installed}"

        installed_app = FakeApp('installed-demo')
        missing_app = FakeApp('missing-demo')

        class FakeInventory:
            _apps = [installed_app, missing_app]

            def _ordered_available_methods_for_status(self, app, installed):
                return ['brew']

            def _custom_method_names_for_status(self, app, installed):
                return set()

            def is_app_installed(self, app):
                calls.append(app)
                return app is installed_app

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--installed'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['installed-demo (brew) installed=True']]
        assert calls == [installed_app, missing_app]

    def test_main_inventory_list_all_uses_defined_methods(self, modules, monkeypatch):
        printed = []

        class FakeApp:
            def inventory_all_methods_label(self, methods, available_methods, *, installed=False, custom_methods=None):
                return f"demo methods={','.join(methods)} available={','.join(sorted(available_methods))} installed={installed}"

        class FakeInventory:
            _apps = [FakeApp()]

            def _ordered_defined_methods_for_status(self, app, installed):
                return ['brew', 'linux']

            def _available_method_names_for_status(self, app, installed):
                return {'brew'}

            def _custom_method_names_for_status(self, app, installed):
                return {'linux'}

            def is_app_installed(self, app):
                return True

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--all'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['demo methods=brew,linux available=brew installed=True']]

    def test_main_inventory_list_all_respects_installed_filter(self, modules, monkeypatch):
        printed = []
        calls = []

        class FakeApp:
            def __init__(self, name):
                self.name = name

            def inventory_all_methods_label(self, methods, available_methods, *, installed=False, custom_methods=None):
                return f'{self.name} installed={installed}'

        installed_app = FakeApp('installed-demo')
        missing_app = FakeApp('missing-demo')

        class FakeInventory:
            _apps = [installed_app, missing_app]

            def _ordered_defined_methods_for_status(self, app, installed):
                return ['brew']

            def _available_method_names_for_status(self, app, installed):
                return {'brew'}

            def _custom_method_names_for_status(self, app, installed):
                return set()

            def is_app_installed(self, app):
                calls.append(app)
                return app is installed_app

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--all', '--installed'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['installed-demo installed=True']]
        assert calls == [installed_app, missing_app]

    def test_main_inventory_list_tags_uses_tag_labels(self, modules, monkeypatch):
        printed = []

        class FakeApp:
            def inventory_tag_label(self, *, installed=False):
                state = 'installed' if installed else 'missing'
                return f'{state} demo [favorite, cli]'

        class FakeInventory:
            _apps = [FakeApp()]

            def is_app_installed(self, app):
                return True

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--tags'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['installed demo [favorite, cli]']]

    def test_main_inventory_list_tags_respects_installed_filter_without_rechecking(self, modules, monkeypatch):
        printed = []
        calls = []

        class FakeApp:
            def __init__(self, name):
                self.name = name

            def inventory_tag_label(self, *, installed=False):
                return f'{self.name} installed={installed}'

        installed_app = FakeApp('installed-demo')
        missing_app = FakeApp('missing-demo')

        class FakeInventory:
            _apps = [installed_app, missing_app]

            def is_app_installed(self, app):
                calls.append(app)
                return app is installed_app

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--tags', '--installed'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['installed-demo installed=True']]
        assert calls == [installed_app, missing_app]

    def test_main_inventory_search_requires_at_least_one_filter(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'search'])

        modules.main.main()

        assert "Specify at least one search filter with --name, --category, or --tags" in caplog.text

    def test_main_inventory_search_prints_availability_labels(self, modules, monkeypatch):
        printed = []

        class FakeApp:
            def inventory_label(self, methods=None, *, installed=False, custom_methods=None):
                return f"demo ({', '.join(methods)})"

        class FakeInventory:
            def search_apps(self, names=None, categories=None, tags=None, exclusive=False):
                assert names == ['http']
                assert categories == ['dev > cli']
                assert tags == ['favorite']
                assert exclusive is True
                return [FakeApp()]

            def is_app_installed(self, app):
                return False

            def _ordered_available_methods_for_status(self, app, installed):
                return ['brew', 'linux']

            def _custom_method_names_for_status(self, app, installed):
                return {'linux'}

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'search', '-n', 'http', '-c', 'dev > cli', '-t', 'favorite', '-e'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['demo (brew, linux)']]

    def test_main_inventory_search_prints_uninstall_labels_for_installed_apps(self, modules, monkeypatch):
        printed = []

        class FakeApp:
            def inventory_label(self, methods=None, *, installed=False, custom_methods=None):
                return f"installed={installed} methods={', '.join(methods)} custom={', '.join(sorted(custom_methods))}"

        class FakeInventory:
            def search_apps(self, names=None, categories=None, tags=None, exclusive=False):
                return [FakeApp()]

            def is_app_installed(self, app):
                return True

            def _ordered_available_methods_for_status(self, app, installed):
                return ['linux', 'brew']

            def _custom_method_names_for_status(self, app, installed):
                return {'linux'}

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'search', '-n', 'demo'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['installed=True methods=linux, brew custom=linux']]

    def test_main_inventory_search_prints_detailed_results(self, modules, monkeypatch):
        printed = []

        class FakeApp:
            def inventory_details(self, *, installed=False):
                return 'demo\n  - managers: brew\n  - installers: None\n  - preference: auto\n  - category: dev\n  - tags: favorite'

        class FakeInventory:
            def search_apps(self, names=None, categories=None, tags=None, exclusive=False):
                return [FakeApp()]

            def is_app_installed(self, app):
                return False

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'search', '-d', '-n', 'demo'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main.ut.Display, 'print_list', lambda values=None: printed.append(values if values is not None else []))

        modules.main.main()

        assert printed == [['demo\n  - managers: brew\n  - installers: None\n  - preference: auto\n  - category: dev\n  - tags: favorite']]

    def test_main_inventory_edit_opens_default_inventory_path(self, modules, monkeypatch):
        calls = []
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'edit'])
        monkeypatch.setattr(modules.main.ut.Files, 'open_file', lambda path, read_only=False: calls.append((path, read_only)))

        modules.main.main()

        assert calls == [(modules.main.ut.Config.data['DEFAULT_INVENTORY_PATH'], False)]

    def test_main_inventory_rm_confirms_and_removes_exact_app(self, modules, monkeypatch, capsys, caplog):
        saved = []
        app = modules.managers.App('demo')
        modules.main.INVENTORY.add_app(app)
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'rm', 'demo'])
        monkeypatch.setattr('builtins.input', lambda prompt='': 'y')
        monkeypatch.setattr(modules.main.INVENTORY, 'save', lambda path: saved.append(path))

        modules.main.main()

        assert modules.main.INVENTORY.get_app('demo') is None
        assert saved == [modules.main.ut.Config.data['DEFAULT_INVENTORY_PATH']]
        assert "Removed 'demo' from inventory" in caplog.text

    def test_main_inventory_rm_cancelled_without_force(self, modules, monkeypatch, capsys, caplog):
        app = modules.managers.App('demo')
        modules.main.INVENTORY.add_app(app)
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'rm', 'demo'])
        monkeypatch.setattr('builtins.input', lambda prompt='': 'n')

        modules.main.main()

        assert modules.main.INVENTORY.get_app('demo') is app
        assert 'Removal cancelled' in caplog.text

    def test_main_inventory_rm_force_skips_prompt(self, modules, monkeypatch):
        saved = []
        app = modules.managers.App('demo')
        modules.main.INVENTORY.add_app(app)
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'rm', '-f', 'demo'])
        monkeypatch.setattr('builtins.input', lambda prompt='': (_ for _ in ()).throw(AssertionError('should not prompt')))
        monkeypatch.setattr(modules.main.INVENTORY, 'save', lambda path: saved.append(path))

        modules.main.main()

        assert modules.main.INVENTORY.get_app('demo') is None
        assert saved == [modules.main.ut.Config.data['DEFAULT_INVENTORY_PATH']]

    def test_main_inventory_add_without_source_prints_todo(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'add'])

        modules.main.main()

        assert 'Interactive inventory add is not implemented yet' in caplog.text

    def test_main_inventory_add_from_source_parses_and_saves(self, modules, monkeypatch, tmp_path):
        saved = []
        source = tmp_path / 'item.yml'
        source.write_text(
            yaml.safe_dump(
                {
                    'demo': {
                        'candidate': 'demo-app',
                        'managers': {'brew': {'candidate': '--cask demo'}},
                    }
                },
                sort_keys=False,
            )
        )
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'add', '--source', str(source)])
        monkeypatch.setattr(modules.main.INVENTORY, 'save', lambda path: saved.append(path))

        modules.main.main()

        app = modules.main.INVENTORY.get_app('demo')
        assert app is not None
        assert app.candidate == 'demo-app'
        assert app.managers['brew']['candidate'] == '--cask demo'
        assert saved == [modules.main.ut.Config.data['DEFAULT_INVENTORY_PATH']]

    def test_main_inventory_add_from_source_rejects_non_yaml_file(self, modules, monkeypatch, tmp_path, caplog):
        source = tmp_path / 'item.txt'
        source.write_text('demo')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'add', '--source', str(source)])

        modules.main.main()

        assert f"Source must be a YAML file: '{source}'" in caplog.text

    def test_main_inventory_add_from_source_rejects_missing_file(self, modules, monkeypatch, tmp_path, caplog):
        source = tmp_path / 'missing.yml'
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'add', '--source', str(source)])

        modules.main.main()

        assert f"Source file not found: '{source}'" in caplog.text

    def test_main_inventory_add_from_source_rejects_invalid_structure(self, modules, monkeypatch, tmp_path, caplog):
        source = tmp_path / 'item.yml'
        source.write_text(yaml.safe_dump({'demo': {}, 'extra': {}}))
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'add', '--source', str(source)])

        modules.main.main()

        assert f"Source must contain exactly one inventory item: '{source}'" in caplog.text

    def test_main_inventory_list_categories_renders_tree(self, modules, monkeypatch):
        printed = []

        class FakeInventory:
            _apps = []

            def render_category_tree(self, apps=None, show_tags=False, show_methods=False, icon_resolver=None, *, show_installed=False, installed_states=None):
                assert apps == []
                assert show_tags is False
                assert show_methods is False
                assert icon_resolver is None
                assert show_installed is True
                assert installed_states is None
                return 'tree-object'

        class FakeConsole:
            def print(self, value):
                printed.append(value)

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--categories'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main, 'Console', lambda: FakeConsole())

        modules.main.main()

        assert printed == ['tree-object']

    def test_main_inventory_list_categories_passes_tree_modifiers(self, modules, monkeypatch):
        printed = []

        class FakeInventory:
            _apps = []

            def render_category_tree(self, apps=None, show_tags=False, show_methods=False, icon_resolver=None, *, show_installed=False, installed_states=None):
                assert apps == []
                assert show_tags is True
                assert show_methods is True
                assert icon_resolver is None
                assert show_installed is True
                assert installed_states is None
                return 'tree-object'

        class FakeConsole:
            def print(self, value):
                printed.append(value)

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--categories', '--show-tags', '--show-methods'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main, 'Console', lambda: FakeConsole())

        modules.main.main()

        assert printed == ['tree-object']

    def test_main_inventory_list_categories_installed_filters_tree_apps(self, modules, monkeypatch):
        printed = []
        installed_app = object()
        missing_app = object()
        calls = []

        class FakeInventory:
            _apps = [installed_app, missing_app]

            def is_app_installed(self, app):
                calls.append(app)
                return app is installed_app

            def render_category_tree(self, apps=None, show_tags=False, show_methods=False, icon_resolver=None, *, show_installed=False, installed_states=None):
                assert apps == [installed_app]
                assert installed_states == {installed_app: True, missing_app: False}
                return 'tree-object'

        class FakeConsole:
            def print(self, value):
                printed.append(value)

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--categories', '--installed'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main, 'Console', lambda: FakeConsole())

        modules.main.main()

        assert printed == ['tree-object']
        assert calls == [installed_app, missing_app]

    def test_main_inventory_list_tag_groups_renders_panels(self, modules, monkeypatch):
        printed = []

        class FakeInventory:
            _apps = []

            def render_tag_groups(self, apps=None, icon_resolver=None, *, show_installed=False, installed_states=None):
                assert apps == []
                assert icon_resolver is None
                assert show_installed is True
                assert installed_states is None
                return 'tag-panels'

        class FakeConsole:
            def print(self, value):
                printed.append(value)

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--tag-groups'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main, 'Console', lambda: FakeConsole())

        modules.main.main()

        assert printed == ['tag-panels']

    def test_main_inventory_list_tag_groups_installed_filters_panel_apps(self, modules, monkeypatch):
        printed = []
        installed_app = object()
        missing_app = object()
        calls = []

        class FakeInventory:
            _apps = [installed_app, missing_app]

            def is_app_installed(self, app):
                calls.append(app)
                return app is installed_app

            def render_tag_groups(self, apps=None, icon_resolver=None, *, show_installed=False, installed_states=None):
                assert apps == [installed_app]
                assert installed_states == {installed_app: True, missing_app: False}
                return 'tag-panels'

        class FakeConsole:
            def print(self, value):
                printed.append(value)

        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--tag-groups', '--installed'])
        monkeypatch.setattr(modules.main, 'INVENTORY', FakeInventory())
        monkeypatch.setattr(modules.main, 'Console', lambda: FakeConsole())

        modules.main.main()

        assert printed == ['tag-panels']
        assert calls == [installed_app, missing_app]

    def test_main_inventory_list_rejects_tree_modifiers_without_categories(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'list', '--show-tags'])

        modules.main.main()

        assert '--show-tags and --show-methods can only be used with --categories' in caplog.text

    def test_cli_parser_parses_new_basic(self, modules):
        args = modules.main.cli_parser().parse_args(['inv', 'new', 'path.yml'])

        assert args.inv_cmd == 'new'
        assert args.path == 'path.yml'
        assert args.inherit is False

    def test_cli_parser_parses_new_inherit(self, modules):
        args_short = modules.main.cli_parser().parse_args(['inv', 'new', 'path.yml', '-i'])
        args_long = modules.main.cli_parser().parse_args(['inv', 'new', 'path.yml', '--inherit'])

        assert args_short.inv_cmd == 'new'
        assert args_short.path == 'path.yml'
        assert args_short.inherit is True
        assert args_long.inherit is True

    def test_main_new_rejects_non_yaml_extension(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'new', 'path.txt'])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert 'INVENTORY_PATH must end in .yml or .yaml' in caplog.text
        assert calls == []

    def test_main_new_rejects_existing_file(self, modules, monkeypatch, tmp_path, caplog):
        target = tmp_path / 'items.yml'
        target.write_text('apps: {}')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'new', str(target)])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert f"File already exists: '{target}'" in caplog.text
        assert calls == []

    def test_main_new_creates_empty_inventory(self, modules, monkeypatch, tmp_path, caplog):
        target = tmp_path / 'items.yml'
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'new', str(target)])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert target.read_text() == '### APLET INVENTORY ###\napps: {}\n'
        assert calls == [target]
        assert f"Created new inventory at '{target}'" in caplog.text

    def test_main_new_inherit_copies_current_inventory(self, modules, monkeypatch, tmp_path, caplog):
        current = tmp_path / 'current.yml'
        current.write_text('### APLET INVENTORY ###\napps:\n  demo:\n    candidate: demo\n')
        monkeypatch.setitem(modules.utils.Config.data, 'DEFAULT_INVENTORY_PATH', current)
        target = tmp_path / 'items.yml'
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'new', str(target), '--inherit'])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert target.read_text() == current.read_text()
        assert calls == [target]
        assert f"Created new inventory at '{target}'" in caplog.text

    def test_main_new_inherit_rejects_missing_current_inventory(self, modules, monkeypatch, tmp_path, caplog):
        missing = tmp_path / 'missing.yml'
        monkeypatch.setitem(modules.utils.Config.data, 'DEFAULT_INVENTORY_PATH', missing)
        target = tmp_path / 'items.yml'
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'new', str(target), '--inherit'])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert f"Current inventory not found: '{missing}'" in caplog.text
        assert calls == []

    def test_main_new_inherit_rejects_existing_target(self, modules, monkeypatch, tmp_path, caplog):
        current = tmp_path / 'current.yml'
        current.write_text('apps: {}')
        monkeypatch.setitem(modules.utils.Config.data, 'DEFAULT_INVENTORY_PATH', current)
        target = tmp_path / 'items.yml'
        target.write_text('existing')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'new', str(target), '--inherit'])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert f"File already exists: '{target}'" in caplog.text
        assert target.read_text() == 'existing'
        assert calls == []

    def test_main_new_creates_parent_dirs(self, modules, monkeypatch, tmp_path, capsys):
        target = tmp_path / 'a' / 'b' / 'items.yml'
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'new', str(target)])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert target.read_text() == '### APLET INVENTORY ###\napps: {}\n'
        assert calls == [target]
        assert (tmp_path / 'a' / 'b').is_dir()

    def test_cli_parser_parses_inv_set(self, modules):
        args_no_target = modules.main.cli_parser().parse_args(['inv', 'set'])
        args_path = modules.main.cli_parser().parse_args(['inv', 'set', 'foo.yml'])
        args_builtin = modules.main.cli_parser().parse_args(['inv', 'set', 'builtin'])
        args_index = modules.main.cli_parser().parse_args(['inv', 'set', '1'])

        assert args_no_target.inv_cmd == 'set'
        assert args_no_target.target is None
        assert args_path.inv_cmd == 'set'
        assert args_path.target == 'foo.yml'
        assert args_builtin.target == 'builtin'
        assert args_index.target == '1'

    def test_main_inv_set_interactive_no_inventories(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set'])
        monkeypatch.setattr(modules.inventory, 'discover_inventories', lambda search_root=None: [])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert 'No inventory files found in HOME directory' in caplog.text
        assert calls == []

    def test_main_inv_set_interactive_keeps_current(self, modules, monkeypatch, capsys, caplog):
        p = Path('/fake/inventory.yml')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set'])
        monkeypatch.setattr(modules.inventory, 'discover_inventories', lambda search_root=None: [p])
        monkeypatch.setitem(modules.utils.Config.data, 'DEFAULT_INVENTORY_PATH', Path('/different/current.yml'))
        monkeypatch.setattr('builtins.input', lambda prompt='': '')
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert 'Keeping current inventory' in caplog.text
        assert calls == []

    def test_main_inv_set_interactive_selects_index(self, modules, monkeypatch, capsys, caplog):
        p1 = Path('/fake/one.yml')
        p2 = Path('/fake/two.yml')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set'])
        monkeypatch.setattr(modules.inventory, 'discover_inventories', lambda search_root=None: [p1, p2])
        monkeypatch.setattr('builtins.input', lambda prompt='': '2')
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert calls == [p2]
        assert f"Switched inventory to '{p2}'" in caplog.text

    def test_main_inv_set_interactive_keyboard_interrupt(self, modules, monkeypatch, capsys):
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set'])
        monkeypatch.setattr(modules.inventory, 'discover_inventories', lambda search_root=None: [Path('/fake/one.yml')])
        monkeypatch.setattr('builtins.input', lambda prompt='': (_ for _ in ()).throw(KeyboardInterrupt()))
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert calls == []

    def test_main_inv_set_builtin(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set', 'builtin'])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert calls == ['builtin']
        assert 'Switched to built-in inventory' in caplog.text

    def test_main_inv_set_by_index(self, modules, monkeypatch, caplog):
        p1 = Path('/fake/one.yml')
        p2 = Path('/fake/two.yml')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set', '2'])
        monkeypatch.setattr(modules.inventory, 'discover_inventories', lambda search_root=None: [p1, p2])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert calls == [p2]
        assert f"Switched inventory to '{p2}'" in caplog.text

    def test_main_inv_set_by_path(self, modules, monkeypatch, tmp_path, caplog):
        inv = tmp_path / 'my-inventory.yml'
        inv.write_text('### APLET INVENTORY ###\napps:\n  demo:\n    candidate: demo\n')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set', str(inv)])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert calls == [inv]
        assert f"Switched inventory to '{inv}'" in caplog.text

    def test_main_inv_set_by_path_accepts_legacy_header(self, modules, monkeypatch, tmp_path, caplog):
        inv = tmp_path / 'my-inventory.yml'
        inv.write_text('### APPLET INVENTORY ###\napps:\n  demo:\n    candidate: demo\n')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set', str(inv)])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert calls == [inv]
        assert f"Switched inventory to '{inv}'" in caplog.text

    def test_main_inv_set_rejects_invalid_path(self, modules, monkeypatch, caplog):
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set', '/nonexistent/path.yml'])
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert "File not found: '/nonexistent/path.yml'" in caplog.text
        assert calls == []

    def test_main_inv_set_interactive_shows_current_marker(self, modules, monkeypatch, capsys, caplog):
        p1 = Path('/fake/one.yml')
        p2 = Path('/fake/two.yml')
        p3 = Path('/fake/three.yml')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set'])
        monkeypatch.setattr(modules.inventory, 'discover_inventories', lambda search_root=None: [p1, p2, p3])
        monkeypatch.setitem(modules.utils.Config.data, 'DEFAULT_INVENTORY_PATH', p2)
        monkeypatch.setattr('builtins.input', lambda prompt='': '1')
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert calls == [p1]
        assert f"Switched inventory to '{p1}'" in caplog.text

    def test_main_inv_set_interactive_selects_current_noop(self, modules, monkeypatch, capsys, caplog):
        p1 = Path('/fake/one.yml')
        p2 = Path('/fake/two.yml')
        monkeypatch.setattr(sys, 'argv', ['aplet', 'inv', 'set'])
        monkeypatch.setattr(modules.inventory, 'discover_inventories', lambda search_root=None: [p1, p2])
        monkeypatch.setitem(modules.utils.Config.data, 'DEFAULT_INVENTORY_PATH', p1)
        monkeypatch.setattr('builtins.input', lambda prompt='': '1')
        calls = []
        monkeypatch.setattr(modules.utils.Config, 'set_inventory_path', lambda new_path: calls.append(new_path))

        modules.main.main()

        assert 'Already using this inventory' in caplog.text
        assert calls == []
