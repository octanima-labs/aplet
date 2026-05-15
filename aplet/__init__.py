"""Public Python API for Aplet.

Most users interact with Aplet through the ``aplet`` command. The names
exported here are the supported library entry points for loading and working
with inventory data from Python.
"""

from .inventory import App, AppInventory, discover_inventories, is_inventory_file
from .runners import Action, Probe, Script


__all__ = [
    'Action',
    'App',
    'AppInventory',
    'Probe',
    'Script',
    'discover_inventories',
    'is_inventory_file',
    'load_inventory',
]


def load_inventory(path=None) -> AppInventory:
    """Load an Aplet inventory file.

    Args:
        path: Optional path to an inventory YAML file. When omitted, Aplet uses
            the configured default inventory path.

    Returns:
        A loaded :class:`aplet.inventory.AppInventory` instance.
    """
    return AppInventory().load(path)
