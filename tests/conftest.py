import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def completed(stdout: str = '', stderr: str = ''):
    return SimpleNamespace(stdout=stdout, stderr=stderr)


@pytest.fixture(autouse=True)
def capture_all_logs(caplog):
    caplog.set_level(0)


@pytest.fixture
def modules(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root))
    monkeypatch.setenv('HOME', str(tmp_path))

    for name in tuple(sys.modules):
        if name == 'aplet' or name.startswith('aplet.'):
            sys.modules.pop(name, None)
    for name in ('main', 'managers', 'utils', 'runners', 'inventory', 'repositories'):
        sys.modules.pop(name, None)

    utils = importlib.import_module('aplet.utils')
    utils.Config.load()

    temp_inventory = tmp_path / 'inventory.yml'
    temp_inventory.write_text('### APLET INVENTORY ###\napps: {}\n')
    utils.Config.data['DEFAULT_INVENTORY_PATH'] = temp_inventory

    runners = importlib.import_module('aplet.runners')
    inventory = importlib.import_module('aplet.inventory')
    repositories = importlib.import_module('aplet.repositories')
    managers = importlib.import_module('aplet.managers')
    main = importlib.import_module('aplet.cli')
    main.INVENTORY = inventory.AppInventory().load(temp_inventory)

    return SimpleNamespace(
        repo_root=repo_root,
        home=tmp_path,
        utils=utils,
        runners=runners,
        inventory=inventory,
        repositories=repositories,
        managers=managers,
        main=main,
        inventory_path=temp_inventory,
    )
