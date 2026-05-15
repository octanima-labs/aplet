class TestApp:
    def test_add_manager_stores_only_defined_values(self, modules):
        app = modules.inventory.App('demo')

        assert app.installed is None
        assert app.probes == {}
        assert app.post_install == {}
        assert app.uninstallers == {}
        assert app.dependencies == []

        app.add_manager('brew', candidate='--cask demo')

        assert app.managers['brew'] == {'candidate': '--cask demo'}

    def test_add_manager_warns_without_force(self, modules, caplog):
        app = modules.inventory.App('demo')
        app.add_manager('brew', candidate='demo')

        app.add_manager('brew', candidate='other-demo')

        assert app.managers['brew']['candidate'] == 'demo'
        assert "Manager 'brew' already defined" in caplog.text

    def test_remove_manager_ignores_missing_entries(self, modules):
        app = modules.inventory.App('demo')

        app.remove_manager('missing')

        assert app.managers == {}

    def test_add_installer_stores_named_installer(self, modules):
        app = modules.inventory.App('demo', preference=['linux'])
        installer = modules.runners.Script.from_data(
            'linux',
            [{'cmd': ['echo demo']}],
            allowed_manager_actions=modules.managers.IMPLEMENTED,
        )

        app.add_installer(installer)

        assert app.preference == ['linux']
        assert app.installers['linux'] is installer

    def test_add_uninstaller_stores_named_uninstaller(self, modules):
        app = modules.inventory.App('demo', preference=['linux'])
        uninstaller = modules.runners.Script.from_data(
            'linux',
            [{'cmd': ['echo remove demo']}],
            allowed_manager_actions=modules.managers.IMPLEMENTED,
        )

        app.add_uninstaller(uninstaller)

        assert app.preference == ['linux']
        assert app.uninstallers['linux'] is uninstaller

    def test_add_post_install_stores_named_installer(self, modules):
        app = modules.inventory.App('demo', preference=['linux'])
        installer = modules.runners.Script.from_data(
            'linux',
            [{'cmd': ['echo post install demo']}],
            allowed_manager_actions=modules.managers.IMPLEMENTED,
        )

        app.add_post_install(installer)

        assert app.preference == ['linux']
        assert app.post_install['linux'] is installer

    def test_add_probe_stores_manager_refs_and_custom_probes(self, modules):
        app = modules.inventory.App('demo')
        probe = modules.runners.Probe.from_data(
            'linux',
            [{'cmd': ['demo --version']}],
        )

        app.add_probe('brew')
        app.add_probe('linux', probe)

        assert app.probes['brew'] is None
        assert app.probes['linux'] is probe

    def test_installed_accepts_only_bool_or_none(self, modules):
        assert modules.inventory.App('unknown').installed is None
        assert modules.inventory.App('installed', installed=True).installed is True
        assert modules.inventory.App('missing', installed=False).installed is False

        try:
            modules.inventory.App('bad', installed='true')
        except TypeError as exc:
            assert str(exc) == "[-] App 'installed' must be true, false, or null"
        else:
            raise AssertionError('Expected invalid installed value to fail')

    def test_dependencies_accept_list_and_dedupe(self, modules):
        app = modules.inventory.App('demo', dependencies=['git', 'curl', 'git'])

        assert app.dependencies == ['git', 'curl']

    def test_dependencies_reject_invalid_values_and_self_dependency(self, modules):
        try:
            modules.inventory.App('demo', dependencies='git')
        except TypeError as exc:
            assert str(exc) == "[-] App 'dependencies' must be a list of strings"
        else:
            raise AssertionError('Expected invalid dependencies value to fail')

        try:
            modules.inventory.App('demo', dependencies=['demo'])
        except ValueError as exc:
            assert str(exc) == "[-] App 'demo' cannot depend on itself"
        else:
            raise AssertionError('Expected self dependency to fail')

    def test_add_dependency_validates_against_inventory(self, modules):
        api = modules.inventory.AppInventory()
        app = modules.inventory.App('demo')
        dependency = modules.inventory.App('git')
        api.add_app(dependency)
        api.add_app(app)

        app.add_dependency('git')
        app.add_dependency('git')

        assert app.dependencies == ['git']

        try:
            app.add_dependency('missing')
        except ValueError as exc:
            assert str(exc) == "[-] App 'demo' dependency 'missing' is not declared"
        else:
            raise AssertionError('Expected unknown dependency to fail')

    def test_add_dependency_requires_inventory_owner(self, modules):
        app = modules.inventory.App('demo')

        try:
            app.add_dependency('git')
        except RuntimeError as exc:
            assert str(exc) == "[-] Cannot validate dependency 'git' without an inventory"
        else:
            raise AssertionError('Expected missing inventory owner to fail')

    def test_rm_dependency_removes_and_ignores_missing_values(self, modules):
        app = modules.inventory.App('demo', dependencies=['git', 'curl'])

        app.rm_dependency('git')
        app.rm_dependency('missing')

        assert app.dependencies == ['curl']

    def test_inventory_label_uses_runtime_methods_when_provided(self, modules):
        app = modules.inventory.App('demo')
        modules.managers.ut.Display.supports_color = lambda: False

        assert app.inventory_label(['apt', 'linux', 'flatpak']) == 'demo (apt, linux, flatpak)'

    def test_inventory_label_prefixes_custom_installers(self, modules):
        app = modules.inventory.App('demo')
        modules.managers.ut.Display.supports_color = lambda: False
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )

        assert app.inventory_label(['apt', 'linux']) == 'demo (apt, x:linux)'

    def test_inventory_label_marks_unavailable_when_no_methods(self, modules):
        app = modules.inventory.App('demo')
        modules.managers.ut.Display.supports_color = lambda: False

        assert app.inventory_label([]) == 'demo (installation unavailable)'
        assert app.inventory_label([], installed=True) == 'demo (uninstall unavailable)'
        assert app.inventory_all_methods_label([], set(), installed=True) == 'demo (uninstall unavailable)'

    def test_inventory_label_colors_managers_and_custom_installers(self, modules, monkeypatch):
        app = modules.inventory.App('demo')
        app.add_installer(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setattr(modules.managers.ut.Display, 'supports_color', lambda: True)

        assert app.inventory_label(['apt', 'linux']) == (
            f"{modules.managers.ut.Display.ANSI_BOLD}demo{modules.managers.ut.Display.ANSI_RESET} "
            f"({modules.managers.ut.Display.ANSI_VALUE}apt{modules.managers.ut.Display.ANSI_RESET}, "
            f"{modules.managers.ut.Display.ANSI_SPECIAL}x:linux{modules.managers.ut.Display.ANSI_RESET})"
        )

    def test_inventory_label_uses_bold_green_for_installed_apps(self, modules, monkeypatch):
        app = modules.inventory.App('demo')
        monkeypatch.setattr(modules.managers.ut.Display, 'supports_color', lambda: True)

        assert app.inventory_label(['apt'], installed=True) == (
            f"{modules.managers.ut.Display.ANSI_BOLD_GREEN}demo{modules.managers.ut.Display.ANSI_RESET} "
            f"({modules.managers.ut.Display.ANSI_VALUE}apt{modules.managers.ut.Display.ANSI_RESET})"
        )

    def test_inventory_all_methods_label_colors_unavailable_methods_red(self, modules, monkeypatch):
        app = modules.inventory.App('demo')
        app.add_manager('apt')
        app.add_manager('brew')
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
                [{'cmd': ['echo arch']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setattr(modules.managers.ut.Display, 'supports_color', lambda: True)

        assert app.inventory_all_methods_label(['apt', 'brew', 'linux', 'arch'], {'apt', 'linux'}) == (
            f"{modules.managers.ut.Display.ANSI_BOLD}demo{modules.managers.ut.Display.ANSI_RESET} "
            f"({modules.managers.ut.Display.ANSI_VALUE}apt{modules.managers.ut.Display.ANSI_RESET}, "
            f"{modules.managers.ut.Display.ANSI_RED}brew{modules.managers.ut.Display.ANSI_RESET}, "
            f"{modules.managers.ut.Display.ANSI_SPECIAL}x:linux{modules.managers.ut.Display.ANSI_RESET}, "
            f"{modules.managers.ut.Display.ANSI_RED}x:arch{modules.managers.ut.Display.ANSI_RESET})"
        )

    def test_inventory_all_methods_label_can_render_uninstaller_methods(self, modules, monkeypatch):
        app = modules.inventory.App('demo', installed=True)
        app.add_manager('brew')
        app.add_uninstaller(
            modules.runners.Script.from_data(
                'linux',
                [{'cmd': ['echo remove demo']}],
                allowed_manager_actions=modules.managers.IMPLEMENTED,
            )
        )
        monkeypatch.setattr(modules.managers.ut.Display, 'supports_color', lambda: True)

        assert app.inventory_all_methods_label(['brew', 'linux'], {'brew'}, installed=True, custom_methods={'linux'}) == (
            f"{modules.managers.ut.Display.ANSI_BOLD_GREEN}demo{modules.managers.ut.Display.ANSI_RESET} "
            f"({modules.managers.ut.Display.ANSI_VALUE}brew{modules.managers.ut.Display.ANSI_RESET}, "
            f"{modules.managers.ut.Display.ANSI_RED}x:linux{modules.managers.ut.Display.ANSI_RESET})"
        )

    def test_inventory_details_uses_plain_text_without_color(self, modules, monkeypatch):
        app = modules.inventory.App('demo')
        monkeypatch.setattr(modules.managers.ut.Display, 'supports_color', lambda: False)

        assert app.inventory_details() == (
            'demo\n'
            '  - managers: None\n'
            '  - installers: None\n'
            '  - uninstallers: None\n'
            '  - post_install: None\n'
            '  - probes: None\n'
            '  - installed: unknown\n'
            '  - dependencies: None\n'
            '  - preference: auto\n'
            '  - category: None\n'
            '  - tags: None'
        )

    def test_inventory_details_colors_keys_values_and_dim_placeholders(self, modules, monkeypatch):
        app = modules.inventory.App('demo', preference=['brew'], category=['dev'], tags=['cli'])
        app.add_manager('brew', candidate='demo')
        monkeypatch.setattr(modules.managers.ut.Display, 'supports_color', lambda: True)

        rendered = app.inventory_details()

        assert f"  - {modules.managers.ut.Display.ANSI_KEY}managers{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_VALUE}brew{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}installers{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_DIM}None{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}uninstallers{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_DIM}None{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}post_install{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_DIM}None{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}probes{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_DIM}None{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}installed{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_DIM}unknown{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}dependencies{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_DIM}None{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}preference{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_VALUE}brew{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}category{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_VALUE}dev{modules.managers.ut.Display.ANSI_RESET}" in rendered
        assert f"  - {modules.managers.ut.Display.ANSI_KEY}tags{modules.managers.ut.Display.ANSI_RESET}: {modules.managers.ut.Display.ANSI_VALUE}cli{modules.managers.ut.Display.ANSI_RESET}" in rendered

    def test_inventory_tag_label_colors_tags_and_dims_no_tags(self, modules, monkeypatch):
        tagged = modules.inventory.App('demo', tags=['cli', 'python'])
        untagged = modules.inventory.App('plain')
        monkeypatch.setattr(modules.managers.ut.Display, 'supports_color', lambda: True)

        assert tagged.inventory_tag_label() == (
            f"{modules.managers.ut.Display.ANSI_BOLD}demo{modules.managers.ut.Display.ANSI_RESET} "
            f"[{modules.managers.ut.Display.ANSI_KEY}cli{modules.managers.ut.Display.ANSI_RESET}, "
            f"{modules.managers.ut.Display.ANSI_KEY}python{modules.managers.ut.Display.ANSI_RESET}]"
        )
        assert untagged.inventory_tag_label() == (
            f"{modules.managers.ut.Display.ANSI_BOLD}plain{modules.managers.ut.Display.ANSI_RESET} "
            f"[{modules.managers.ut.Display.ANSI_DIM}no-tags{modules.managers.ut.Display.ANSI_RESET}]"
        )
