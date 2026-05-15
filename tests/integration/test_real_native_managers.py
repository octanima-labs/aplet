import os

import pytest


pytestmark = pytest.mark.integration

if os.environ.get('APLET_REAL_INSTALL_TESTS') != '1':
    pytest.skip('real package-manager tests are opt-in', allow_module_level=True)


def test_real_native_manager_is_available(real_manager):
    assert real_manager.available_on_host() is True


def test_real_native_manager_lists_gpg_and_repos(real_manager):
    assert isinstance(real_manager.list_gpg(), list)
    assert isinstance(real_manager.list_repos(), list)


def test_real_native_manager_installs_queries_and_uninstalls_package(real_manager, real_test_package):
    if real_manager.is_installed_target({}, real_test_package) is True:
        real_manager.uninstall(real_test_package)

    real_manager.install(real_test_package)
    assert real_manager.is_installed_target({}, real_test_package) is True

    real_manager.uninstall(real_test_package)
    assert real_manager.is_installed_target({}, real_test_package) is False
