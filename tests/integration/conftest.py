from pathlib import Path
import os

import pytest


REAL_INSTALL_ENV = 'APLET_REAL_INSTALL_TESTS'
MANAGER_ENV = 'APLET_TEST_MANAGER'
CONTAINER_MARKERS = (Path('/.dockerenv'), Path('/run/.containerenv'))

NATIVE_MANAGER_PACKAGES = {
    'apt': 'tree',
    'dnf': 'tree',
    'yum': 'tree',
    'zypper': 'tree',
    'pacman': 'tree',
}


def _require_real_container() -> None:
    if os.environ.get(REAL_INSTALL_ENV) != '1':
        pytest.skip('real package-manager tests are opt-in')
    if not any(marker.exists() for marker in CONTAINER_MARKERS):
        pytest.fail('refusing to run real package-manager tests outside a container')


@pytest.fixture(scope='session')
def real_manager_name() -> str:
    _require_real_container()
    manager_name = os.environ.get(MANAGER_ENV)
    if manager_name not in NATIVE_MANAGER_PACKAGES:
        expected = ', '.join(sorted(NATIVE_MANAGER_PACKAGES))
        pytest.fail(f"{MANAGER_ENV} must be one of: {expected}")
    return manager_name


@pytest.fixture(scope='session')
def real_manager(real_manager_name):
    from aplet.managers import MANAGERS

    return MANAGERS[real_manager_name]


@pytest.fixture(scope='session')
def real_test_package(real_manager_name) -> str:
    return NATIVE_MANAGER_PACKAGES[real_manager_name]
