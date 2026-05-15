Python API
==========

Most users should use the ``aplet`` CLI. The Python API is intentionally small
and centered on loading and working with inventory data.

Public Package API
------------------

.. automodule:: aplet
   :members: load_inventory

Inventory Objects
-----------------

.. autoclass:: aplet.App

.. autoclass:: aplet.AppInventory

.. autofunction:: aplet.discover_inventories

.. autofunction:: aplet.is_inventory_file

Runner Objects
--------------

.. autoclass:: aplet.Action

.. autoclass:: aplet.Script

.. autoclass:: aplet.Probe
