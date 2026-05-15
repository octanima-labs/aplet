from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path
from rich.console import Console

import shutil
from . import utils as ut
from .inventory import AppInventory
from .runners import SCRIPT_INTERRUPTED


logger = ut.get_logger(__name__)
INVENTORY: AppInventory | None = None


def initialize_runtime(load_inventory: bool = True, log_level: str = 'INFO') -> AppInventory | None:
    global INVENTORY
    if not ut.Config.data:
        ut.Config.load()
    ut.configure_logging(level=log_level)
    if load_inventory and INVENTORY is None:
        INVENTORY = AppInventory().load()
    return INVENTORY


def _log_level_from_verbosity(verbosity: int) -> str:
    if verbosity <= 0:
        return 'INFO'
    if verbosity == 1:
        return 'DEBUG'
    return 'TRACE'


def cli_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog='aplet',
        description=(
            'Manage apps from your inventory. List, search, install, uninstall, '
            'or edit app definitions and config.'
        ),
        epilog=(
            'Examples:\n'
            '  aplet inventory\n'
            '  aplet inventory search -n firefox neovim\n'
            '  aplet install firefox\n'
            '  aplet uninstall firefox\n'
            '  aplet conf --read-only'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='count',
        default=0,
        help='increase log verbosity: -v for DEBUG, -vv for TRACE',
    )
    subparsers = parser.add_subparsers(dest='cmd', required=True, title='commands')

    install_parser = subparsers.add_parser(
        'install',
        help='install apps from the inventory',
        description=(
            'Install one or more apps by inventory name. You can override the '
            'installer backend or use a virtual environment for Python installs.'
        ),
        epilog=(
            'Examples:\n'
            '  aplet install firefox\n'
            '  aplet install firefox neovim\n'
            '  aplet install poetry --installer pip\n'
            '  aplet install black --venv .venv'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    install_parser.add_argument(
        'targets',
        nargs='+',
        metavar='TARGET',
        help='inventory app name(s) to install',
    )
    install_parser.add_argument(
        '-i', '--installer', help='use a specific installer backend'
    )
    install_parser.add_argument(
        '-f', '--force', action='store_true', help='skip prompts or overwrite safeguards'
    )
    install_parser.add_argument(
        '-n', '--needed', action='store_true', help='install missing dependencies before installing targets'
    )
    install_parser.add_argument(
        '--venv', help='use this virtual environment for Python installs'
    )

    uninstall_parser = subparsers.add_parser(
        'uninstall',
        help='uninstall apps from the inventory',
        description=(
            'Uninstall one or more apps by inventory name. Some backends can also '
            'remove the related repository definition.'
        ),
        epilog=(
            'Examples:\n'
            '  aplet uninstall firefox\n'
            '  aplet uninstall firefox neovim\n'
            '  aplet uninstall my-python-tool --venv .venv\n'
            '  aplet uninstall vscode --remove-repo'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    uninstall_parser.add_argument(
        'targets',
        nargs='+',
        metavar='TARGET',
        help='inventory app name(s) to uninstall',
    )
    uninstall_parser.add_argument(
        '-r',
        '--remove-repo',
        action='store_true',
        help='also remove the repository definition when supported',
    )
    uninstall_parser.add_argument(
        '--venv', help='use this virtual environment for Python installs'
    )

    inv_parser = subparsers.add_parser(
        'inventory',
        aliases=['inv'],
        help='list, search, or modify the inventory',
        description=(
            'List inventory entries, search by name/category/tag, or modify the '
            'inventory file. With no subcommand, all entries are shown.'
        ),
        epilog=(
            'Examples:\n'
            '  aplet inventory\n'
            '  aplet inventory list\n'
            '  aplet inventory search -n firefox neovim\n'
            '  aplet inventory search -c "dev > editors" -t favorite\n'
            '  aplet inventory edit\n'
            '  aplet inventory rm firefox\n'
            '  aplet inventory add --source ./apps/firefox.yml\n'
            '  aplet inventory set\n'
            '  aplet inventory set ~/my-inventory.yml\n'
            '  aplet inventory set builtin\n'
            '  aplet inventory new ~/my-inventory.yml\n'
            '  aplet inventory new ~/my-inventory.yml --inherit'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    inv_subparsers = inv_parser.add_subparsers(
        dest='inv_cmd', required=False, title='inventory commands'
    )

    inv_list_parser = inv_subparsers.add_parser(
        'list',
        help='list all inventory entries',
        description='List all app entries in the inventory file.',
        epilog=(
            'Examples:\n'
            '  aplet inventory list\n'
            '  aplet inventory list --details\n'
            '  aplet inventory list --categories\n'
            '  aplet inventory list --categories --show-tags\n'
            '  aplet inventory list --categories --show-methods\n'
            '  aplet inventory list --tags\n'
            '  aplet inventory list --tag-groups\n'
            '  aplet inventory list --all\n'
            '  aplet inv list'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    inv_list_view_group = inv_list_parser.add_mutually_exclusive_group()
    inv_list_view_group.add_argument(
        '-d',
        '--details',
        action='store_true',
        help='show managers, installers, uninstallers, post-install scripts, probes, installed state, dependencies, category, and tags for each app',
    )
    inv_list_view_group.add_argument(
        '-c',
        '--categories',
        action='store_true',
        help='show apps grouped by category hierarchy',
    )
    inv_list_view_group.add_argument(
        '-t',
        '--tags',
        action='store_true',
        help='show tags for each app on a single line',
    )
    inv_list_view_group.add_argument(
        '-T',
        '--tag-groups',
        action='store_true',
        help='show tags grouped with their related apps',
    )
    inv_list_view_group.add_argument(
        '-a',
        '--all',
        action='store_true',
        help='show all defined installation methods, including unavailable ones',
    )
    inv_list_parser.add_argument(
        '--show-tags',
        action='store_true',
        help='when used with --categories, append tags to app leaves',
    )
    inv_list_parser.add_argument(
        '--show-methods',
        action='store_true',
        help='when used with --categories, append available methods to app leaves',
    )
    inv_list_parser.add_argument(
        '-i',
        '--icons',
        action='store_true',
        help='show icons for apps, categories, or tags depending on the selected list view',
    )
    inv_list_parser.add_argument(
        '-I',
        '--installed',
        action='store_true',
        help='show only installed apps',
    )

    inv_search_parser = inv_subparsers.add_parser(
        'search',
        help='search inventory entries',
        description='Search apps by partial name, category path prefix, or tags.',
        epilog=(
            'Examples:\n'
            '  aplet inventory search -n http\n'
            '  aplet inventory search -c "dev > editors"\n'
            '  aplet inventory search -t recommended favorite\n'
            '  aplet inventory search -n code -t favorite --exclusive\n'
            '  aplet inv search -d -n sublime'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    inv_search_parser.add_argument(
        '-d',
        '--details',
        action='store_true',
        help='show managers, installers, uninstallers, post-install scripts, probes, installed state, dependencies, category, and tags for each app',
    )
    inv_search_parser.add_argument(
        '-n',
        '--name',
        nargs='+',
        metavar='APP',
        help='search inventory entries by partial app name or candidate',
    )
    inv_search_parser.add_argument(
        '-c',
        '--category',
        nargs='+',
        metavar='CAT',
        help='search inventory entries by category path prefix, e.g. "dev > editors"',
    )
    inv_search_parser.add_argument(
        '-t',
        '--tags',
        nargs='+',
        metavar='TAG',
        help='search inventory entries by tags',
    )
    inv_search_parser.add_argument(
        '-e',
        '--exclusive',
        action='store_true',
        help='require all provided filter groups to match',
    )

    inv_rm_parser = inv_subparsers.add_parser(
        'rm',
        help='remove an app from the inventory',
        description='Remove a single app entry from the inventory file.',
        epilog=(
            'Examples:\n'
            '  aplet inventory rm firefox\n'
            '  aplet inventory rm firefox --force'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    inv_rm_parser.add_argument('name', metavar='TARGET', help='inventory app name to remove')
    inv_rm_parser.add_argument(
        '-f', '--force', action='store_true', help='remove without prompting for confirmation'
    )

    inv_subparsers.add_parser(
        'edit',
        help='open the inventory file in your editor',
        description='Open the inventory file in your editor.',
        epilog=(
            'Examples:\n'
            '  aplet inventory edit'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )

    inv_add_parser = inv_subparsers.add_parser(
        'add',
        help='add an app to the inventory from YAML',
        description=(
            'Add a single app entry from a YAML file. The source file must contain '
            'exactly one inventory item.'
        ),
        epilog=(
            'Examples:\n'
            '  aplet inventory add --source ./apps/firefox.yml\n'
            '  aplet inventory add --source ./tmp/new-app.yaml --force'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    inv_add_parser.add_argument(
        '-f', '--force', action='store_true', help='overwrite an existing entry if needed'
    )
    inv_add_parser.add_argument(
        '-s',
        '--source',
        help='path to a YAML file with exactly one inventory item',
    )

    inv_set_parser = inv_subparsers.add_parser(
        'set',
        help='set the active inventory file',
        description='Set the active inventory file by path, index, or choose interactively.',
        epilog=(
            'Examples:\n'
            '  aplet inv set\n'
            '  aplet inv set ~/my-inventory.yml\n'
            '  aplet inv set 1\n'
            '  aplet inv set builtin'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    inv_set_parser.add_argument(
        'target',
        nargs='?',
        metavar='PATH|INDEX|builtin',
        help='path to an inventory file, index from discovered list, or "builtin"',
    )

    inv_new_parser = inv_subparsers.add_parser(
        'new',
        help='create a new inventory file',
        description='Create a new inventory file and point the config to it.',
        epilog=(
            'Examples:\n'
            '  aplet inv new ~/my-inventory.yml\n'
            '  aplet inv new ~/my-inventory.yml --inherit'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    inv_new_parser.add_argument(
        'path',
        metavar='INVENTORY_PATH',
        help='path to the new inventory file (must end in .yml or .yaml)',
    )
    inv_new_parser.add_argument(
        '-i', '--inherit',
        action='store_true',
        help='copy the current inventory contents into the new file',
    )

    conf_parser = subparsers.add_parser(
        'conf',
        help='open the config file',
        description='Open the Aplet config file for viewing or editing.',
        epilog=(
            'Examples:\n'
            '  aplet conf\n'
            '  aplet conf --read-only'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    conf_parser.add_argument(
        '-r', '--read-only', action='store_true', help='open the config file in read-only mode'
    )

    return parser


def _print_inventory_apps(apps, detailed: bool = False, tag_labels: bool = False) -> None:
    if not apps:
        ut.Display.print_list()
        return
    installed_states = [INVENTORY.is_app_installed(app) for app in apps]
    if detailed:
        ut.Display.print_list([
            app.inventory_details(installed=installed)
            for app, installed in zip(apps, installed_states)
        ])
        return
    if tag_labels:
        ut.Display.print_list([
            app.inventory_tag_label(installed=installed)
            for app, installed in zip(apps, installed_states)
        ])
        return
    ut.Display.print_list([
        app.inventory_label(
            INVENTORY._ordered_available_methods_for_status(app, installed),
            installed=installed,
            custom_methods=INVENTORY._custom_method_names_for_status(app, installed),
        )
        for app, installed in zip(apps, installed_states)
    ])


def _inventory_detail_with_icon(app, icon_resolver: ut.IconResolver, *, installed: bool = False) -> str:
    details = app.inventory_details(installed=installed)
    lines = details.splitlines()
    if not lines:
        return details
    lines[0] = icon_resolver.iconify_app_label(app, lines[0])
    return '\n'.join(lines)


def _installed_state_map(apps):
    installed_states = {}
    for app in apps:
        if app not in installed_states:
            installed_states[app] = INVENTORY.is_app_installed(app)
    return installed_states


def _installed_state_list(apps, installed_state_map=None):
    if installed_state_map is None:
        return [INVENTORY.is_app_installed(app) for app in apps]
    return [installed_state_map[app] if app in installed_state_map else INVENTORY.is_app_installed(app) for app in apps]


def _filter_inventory_apps(apps, *, installed_only: bool = False, installed_state_map=None):
    if not installed_only:
        return list(apps)
    if installed_state_map is None:
        return [app for app in apps if INVENTORY.is_app_installed(app)]
    return [app for app in apps if installed_state_map.get(app, False)]


def _print_inventory_list(
    apps,
    *,
    detailed: bool = False,
    tag_labels: bool = False,
    icons: bool = False,
    all_methods: bool = False,
    installed_state_map=None,
) -> None:
    if not apps:
        ut.Display.print_list()
        return
    icon_resolver = ut.IconResolver() if icons else None
    installed_states = _installed_state_list(apps, installed_state_map)
    if detailed:
        values = [
            _inventory_detail_with_icon(app, icon_resolver, installed=installed)
            if icon_resolver else app.inventory_details(installed=installed)
            for app, installed in zip(apps, installed_states)
        ]
        ut.Display.print_list(values)
        return
    if tag_labels:
        values = [
            app.inventory_tag_label(installed=installed)
            for app, installed in zip(apps, installed_states)
        ]
        if icon_resolver:
            values = [icon_resolver.iconify_app_label(app, label) for app, label in zip(apps, values)]
        ut.Display.print_list(values)
        return
    if all_methods:
        values = [
            app.inventory_all_methods_label(
                INVENTORY._ordered_defined_methods_for_status(app, installed),
                INVENTORY._available_method_names_for_status(app, installed),
                installed=installed,
                custom_methods=INVENTORY._custom_method_names_for_status(app, installed),
            )
            for app, installed in zip(apps, installed_states)
        ]
        if icon_resolver:
            values = [icon_resolver.iconify_app_label(app, label) for app, label in zip(apps, values)]
        ut.Display.print_list(values)
        return
    values = [
        app.inventory_label(
            INVENTORY._ordered_available_methods_for_status(app, installed),
            installed=installed,
            custom_methods=INVENTORY._custom_method_names_for_status(app, installed),
        )
        for app, installed in zip(apps, installed_states)
    ]
    if icon_resolver:
        values = [icon_resolver.iconify_app_label(app, label) for app, label in zip(apps, values)]
    ut.Display.print_list(values)


def _handle_new(args):
    new_path = Path(args.path)
    if new_path.suffix.lower() not in {'.yml', '.yaml'}:
        logger.warning("INVENTORY_PATH must end in .yml or .yaml")
        return
    new_path = ut.Files.expand_path(new_path)
    if new_path.exists():
        logger.warning(f"File already exists: '{new_path}'")
        return
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if args.inherit:
        current = ut.Config.data['DEFAULT_INVENTORY_PATH']
        if not current.exists():
            logger.warning(f"Current inventory not found: '{current}'")
            return
        shutil.copy2(current, new_path)
    else:
        new_path.write_text('### APLET INVENTORY ###\napps: {}\n')
    ut.Config.set_inventory_path(new_path)
    logger.success(f"Created new inventory at '{new_path}'")


def _handle_set(args):
    from .inventory import is_inventory_file, discover_inventories

    target = args.target

    if target is None:
        inventories = discover_inventories()
        if not inventories:
            logger.warning("No inventory files found in HOME directory")
            return
        current = ut.Config.data['DEFAULT_INVENTORY_PATH']
        display_items: list[str] = []
        for p in inventories:
            if p == current:
                display_items.append(f'[current] {p}')
            else:
                display_items.append(str(p))
        ut.Display.print_list(display_items)
        try:
            choice = logger.prompt("Select inventory by index (or Enter to keep current):").strip()
        except (KeyboardInterrupt, EOFError):
            Console().print()
            return
        if not choice:
            logger.debug("Keeping current inventory")
            return
        try:
            index = int(choice) - 1
        except ValueError:
            logger.warning(f"Invalid index: {choice}")
            return
        if index < 0 or index >= len(inventories):
            logger.warning(f"Invalid index: {choice}")
            return
        selected = inventories[index]
        if selected == current:
            logger.debug("Already using this inventory")
            return
        ut.Config.set_inventory_path(selected)
        logger.success(f"Switched inventory to '{selected}'")
        return

    if target.strip().lower() == 'builtin':
        ut.Config.set_inventory_path('builtin')
        logger.success("Switched to built-in inventory")
        return

    if target.isdigit():
        inventories = discover_inventories()
        if not inventories:
            logger.warning("No inventory files found in HOME directory")
            return
        index = int(target) - 1
        if index < 0 or index >= len(inventories):
            logger.warning(f"Invalid index: {target} (found {len(inventories)} inventories)")
            return
        ut.Config.set_inventory_path(inventories[index])
        logger.success(f"Switched inventory to '{inventories[index]}'")
        return

    path = ut.Files.expand_path(target)
    if not is_inventory_file(path):
        if path.exists():
            logger.warning(f"Not a valid Aplet inventory file: '{target}'")
        else:
            logger.warning(f"File not found: '{target}'")
        return
    ut.Config.set_inventory_path(path)
    logger.success(f"Switched inventory to '{path}'")


def _main(argv: list[str] | None = None) -> int:
    ARGS = cli_parser().parse_args(argv)
    initialize_runtime(load_inventory=ARGS.cmd != 'conf', log_level=_log_level_from_verbosity(ARGS.verbose))

    if ARGS.cmd == 'conf':
        ut.Config.open(ARGS.read_only)
        return 0

    if ARGS.cmd in {'inventory', 'inv'}:
        if ARGS.inv_cmd == 'edit':
            ut.Files.open_file(ut.Config.data['DEFAULT_INVENTORY_PATH'])
            return 0
        if ARGS.inv_cmd == 'rm':
            app = INVENTORY.get_app(ARGS.name)
            if app is None:
                logger.warning(f"No app match for '{ARGS.name}'")
                return 0
            if not ARGS.force:
                answer = logger.prompt(f"Remove '{app.name}' from inventory? [y/N]:").strip().lower()
                if answer not in {'y', 'yes'}:
                    logger.debug('Removal cancelled')
                    return 0
            INVENTORY.remove_app(app)
            INVENTORY.save(ut.Config.data['DEFAULT_INVENTORY_PATH'])
            logger.success(f"Removed '{app.name}' from inventory")
            return 0
        if ARGS.inv_cmd == 'add':
            if ARGS.source is None:
                logger.error('Interactive inventory add is not implemented yet')
                return 0
            source_path = Path(ARGS.source)
            if not source_path.exists():
                logger.warning(f"Source file not found: '{ARGS.source}'")
                return 0
            if source_path.suffix.lower() not in {'.yml', '.yaml'}:
                logger.warning(f"Source must be a YAML file: '{ARGS.source}'")
                return 0
            source_data = ut.Yaml.load(source_path)
            if not isinstance(source_data, dict) or len(source_data) != 1:
                logger.warning(f"Source must contain exactly one inventory item: '{ARGS.source}'")
                return 0
            app_name, app_data = next(iter(source_data.items()))
            try:
                app = INVENTORY.parse_app_item(app_name, app_data)
            except (TypeError, ValueError) as exc:
                logger.warning(str(exc))
                return 0
            if not INVENTORY.add_app(app, force=ARGS.force):
                return 0
            INVENTORY.save(ut.Config.data['DEFAULT_INVENTORY_PATH'])
            logger.success(f"Added '{app.name}' to inventory")
            return 0

        if ARGS.inv_cmd == 'set':
            _handle_set(ARGS)
            return 0

        if ARGS.inv_cmd == 'new':
            _handle_new(ARGS)
            return 0

        if ARGS.inv_cmd == 'search':
            if ARGS.name is None and ARGS.category is None and ARGS.tags is None:
                logger.warning('Specify at least one search filter with --name, --category, or --tags')
                return 0
            try:
                matches = INVENTORY.search_apps(
                    names=ARGS.name,
                    categories=ARGS.category,
                    tags=ARGS.tags,
                    exclusive=ARGS.exclusive,
                )
            except (TypeError, ValueError) as exc:
                logger.warning(str(exc))
                return 0
            _print_inventory_apps(matches, detailed=ARGS.details)
            return 0

        if ARGS.inv_cmd == 'list' and (ARGS.show_tags or ARGS.show_methods) and not ARGS.categories:
            logger.warning('--show-tags and --show-methods can only be used with --categories')
            return 0

        installed_state_map = (
            _installed_state_map(INVENTORY._apps)
            if getattr(ARGS, 'installed', False) else None
        )

        list_apps = _filter_inventory_apps(
            INVENTORY._apps,
            installed_only=getattr(ARGS, 'installed', False),
            installed_state_map=installed_state_map,
        )

        if ARGS.inv_cmd == 'list' and ARGS.categories:
            icon_resolver = ut.IconResolver() if ARGS.icons else None
            Console().print(
                INVENTORY.render_category_tree(
                    apps=list_apps,
                    show_tags=ARGS.show_tags,
                    show_methods=ARGS.show_methods,
                    icon_resolver=icon_resolver,
                    show_installed=True,
                    installed_states=installed_state_map,
                )
            )
            return 0

        if ARGS.inv_cmd == 'list' and ARGS.tag_groups:
            icon_resolver = ut.IconResolver() if ARGS.icons else None
            Console().print(
                INVENTORY.render_tag_groups(
                    apps=list_apps,
                    icon_resolver=icon_resolver,
                    show_installed=True,
                    installed_states=installed_state_map,
                )
            )
            return 0

        if ARGS.inv_cmd == 'list' and ARGS.details:
            _print_inventory_list(
                list_apps,
                detailed=True,
                icons=ARGS.icons,
                installed_state_map=installed_state_map,
            )
            return 0

        if ARGS.inv_cmd == 'list' and ARGS.tags:
            _print_inventory_list(
                list_apps,
                tag_labels=True,
                icons=ARGS.icons,
                installed_state_map=installed_state_map,
            )
            return 0

        if ARGS.inv_cmd == 'list' and ARGS.all:
            _print_inventory_list(
                list_apps,
                all_methods=True,
                icons=ARGS.icons,
                installed_state_map=installed_state_map,
            )
            return 0

        _print_inventory_list(
            list_apps,
            icons=getattr(ARGS, 'icons', False),
            installed_state_map=installed_state_map,
        )
    elif ARGS.cmd == 'install':
        return INVENTORY.install(*ARGS.targets, installer=ARGS.installer, force=ARGS.force, venv=ARGS.venv, needed=ARGS.needed)
    elif ARGS.cmd == 'uninstall':
        return INVENTORY.uninstall(*ARGS.targets, remove_repo=ARGS.remove_repo, venv=ARGS.venv)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except KeyboardInterrupt:
        Console().print()
        logger.warning("Execution interrupted by user")
        return SCRIPT_INTERRUPTED


if __name__ == '__main__':
    raise SystemExit(main())
