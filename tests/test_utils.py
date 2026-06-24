from pathlib import Path
import importlib
import sys


class TestUtils:
    def test_configure_logging_uses_requested_level(self, modules, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(modules.utils, 'LOG_FILE', tmp_path / 'state' / 'aplet.log')
        monkeypatch.setattr(modules.utils.tuning, 'basicConfig', lambda **kwargs: calls.append(kwargs))

        modules.utils.configure_logging(level='DEBUG')

        assert calls == [
            {
                'filename': str(tmp_path / 'state' / 'aplet.log'),
                'console': True,
                'level': 'DEBUG',
                'max_bytes': '10 MB',
                'backup_count': 3,
            }
        ]
        assert (tmp_path / 'state').exists()

    def test_conf_loads_default_preference_list(self, modules):
        assert modules.utils.Config.data['PREFERENCE'] == modules.utils.Config.DEFAULT_PREFERENCE

    def test_conf_expands_default_repo_dir(self, modules):
        assert modules.utils.Config.data['DEFAULT_REPO_DIR'] == modules.home / 'Apps'

    def test_utils_does_not_import_file_helper_at_module_load(self, modules):
        assert 'aplet.file_helper' not in sys.modules

    def test_inventory_icon_resolver_loads_icons_from_icons_file(self, modules, monkeypatch, tmp_path):
        icons_file = tmp_path / 'icons.yml'
        icons_file.write_text(
            'apps:\n'
            '  demo-app: "X"\n'
            'keywords:\n'
            '  browser: "Y"\n'
        )
        monkeypatch.setattr(modules.utils.Icons, 'FILE', icons_file)

        resolver = modules.utils.IconResolver(overrides={})
        app = type('App', (), {'name': 'demo-app', 'candidate': '', 'category': [], 'tags': []})()

        assert resolver.app_icon(app) == 'X'
        assert resolver.category_icon('browser tools') == 'Y'

    def test_inventory_icon_resolver_overrides_file_backed_icons(self, modules, monkeypatch, tmp_path):
        icons_file = tmp_path / 'icons.yml'
        icons_file.write_text(
            'apps:\n'
            '  firefox: "F"\n'
            'keywords:\n'
            '  browser: "B"\n'
        )
        monkeypatch.setattr(modules.utils.Icons, 'FILE', icons_file)

        resolver = modules.utils.IconResolver(
            overrides={
                'apps': {'firefox': 'X'},
                'keywords': {'browser': 'Y'},
            }
        )
        app = type('App', (), {'name': 'firefox', 'candidate': '', 'category': ['browser'], 'tags': []})()

        assert resolver.app_icon(app) == 'X'
        assert resolver.category_icon('browser tools') == 'Y'

    def test_inventory_icon_resolver_blank_exact_override_disables_icon(self, modules, monkeypatch, tmp_path):
        icons_file = tmp_path / 'icons.yml'
        icons_file.write_text(
            'apps:\n'
            '  firefox: "F"\n'
            'keywords:\n'
            '  browser: "B"\n'
        )
        monkeypatch.setattr(modules.utils.Icons, 'FILE', icons_file)

        resolver = modules.utils.IconResolver(overrides={'apps': {'firefox': ''}})
        app = type('App', (), {'name': 'firefox', 'candidate': '', 'category': ['browser'], 'tags': []})()

        assert resolver.app_icon(app) is None

    def test_installer_platform_tokens_normalize_aliases(self, modules):
        assert modules.utils.Platform.installer_tokens('windows_archlinux') == ['win', 'arch']

    def test_installer_platform_tokens_allow_linux_with_cross_family_tokens(self, modules):
        assert modules.utils.Platform.installer_tokens('linux_macos') == ['linux', 'macos']
        assert modules.utils.Platform.installer_tokens('win_linux') == ['win', 'linux']

    def test_installer_platform_tokens_reject_linux_mixed_with_distro(self, modules):
        try:
            modules.utils.Platform.installer_tokens('linux_ubuntu')
        except ValueError as exc:
            assert str(exc) == "[-] Installer 'linux_ubuntu' cannot mix 'linux' with Linux distro-specific tokens"
        else:
            raise AssertionError('Expected invalid installer token mix to fail')

    def test_get_host_install_tokens_uses_linux_id_and_id_like(self, modules, monkeypatch):
        monkeypatch.setattr(modules.utils.platform, 'system', lambda: 'Linux')
        monkeypatch.setattr(
            modules.utils.platform,
            'freedesktop_os_release',
            lambda: {'ID': 'ubuntu', 'ID_LIKE': 'debian'},
        )

        assert modules.utils.Platform.host_install_tokens() == {'linux', 'ubuntu', 'debian'}

    def test_get_host_install_tokens_ignores_unknown_linux_id_and_uses_id_like(self, modules, monkeypatch):
        monkeypatch.setattr(modules.utils.platform, 'system', lambda: 'Linux')
        monkeypatch.setattr(
            modules.utils.platform,
            'freedesktop_os_release',
            lambda: {'ID': 'endeavouros', 'ID_LIKE': 'arch'},
        )

        assert modules.utils.Platform.host_install_tokens() == {'linux', 'arch'}

    def test_highlight_yaml_adds_ansi_codes_to_keys_comments_and_values(self, modules):
        rendered = modules.utils.Yaml.highlight(
            'candidate: sublime-text\n# comment\nDEFAULT_PACKAGE_MANAGER: null\n'
        )

        assert '\033[92mcandidate\033[0m:' in rendered
        assert '\033[96msublime-text\033[0m' in rendered
        assert '\033[90m# comment\033[0m' in rendered
        assert '\033[93mnull\033[0m' in rendered

    def test_open_conf_read_only_prints_plain_text_when_color_disabled(self, modules, monkeypatch, capsys):
        monkeypatch.setattr(modules.utils.Display, 'supports_color', lambda: False)

        modules.utils.Config.open(read_only=True)

        assert capsys.readouterr().out == modules.utils.Config.FILE.read_text()

    def test_open_conf_read_only_prints_highlighted_text_when_color_enabled(self, modules, monkeypatch, capsys):
        monkeypatch.setattr(modules.utils.Display, 'supports_color', lambda: True)
        monkeypatch.setattr(modules.utils.Yaml, 'highlight', lambda text: f'<hl>{text}</hl>')

        modules.utils.Config.open(read_only=True)

        assert capsys.readouterr().out == f"<hl>{modules.utils.Config.FILE.read_text()}</hl>"

    def test_patch_file_expands_path_and_creates_parent_dirs(self, modules):
        modules.utils.Files.patch_file('~/.config/demo/config.sh', 'demo-block', ['export DEMO=1'], app_name='demo')

        target = modules.home / '.config' / 'demo' / 'config.sh'
        assert target.read_text() == (
            '### APLET - demo:demo-block ###\n'
            'export DEMO=1\n'
            '### END - demo:demo-block ###\n'
        )

    def test_shell_run_terminates_child_on_keyboard_interrupt_by_default(self, modules, monkeypatch):
        events = []

        class FakePopen:
            args = 'sleep 10'
            pid = 1234
            returncode = None

            def __init__(self, *args, **kwargs):
                events.append(('popen', args, kwargs))

            def communicate(self, input=None, timeout=None):
                events.append(('communicate', input, timeout))
                raise KeyboardInterrupt()

            def terminate(self):
                events.append(('terminate',))

            def wait(self, timeout=None):
                events.append(('wait', timeout))
                self.returncode = -15

            def kill(self):
                events.append(('kill',))

        monkeypatch.setattr(modules.utils.subprocess, 'Popen', FakePopen)
        monkeypatch.setattr(modules.utils.os, 'killpg', lambda pid, sig: events.append(('killpg', pid, sig)))

        try:
            modules.utils.Shell.run('sleep 10')
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError('Expected KeyboardInterrupt to propagate')

        assert events[0][0] == 'popen'
        assert 'start_new_session' not in events[0][2]
        assert ('terminate',) in events
        assert ('killpg', 1234, modules.utils.signal.SIGTERM) not in events
        assert ('wait', 5) in events
        assert ('killpg', 1234, modules.utils.signal.SIGKILL) not in events
        assert ('kill',) not in events

    def test_shell_run_terminates_process_group_when_new_session_requested(self, modules, monkeypatch):
        events = []

        class FakePopen:
            args = 'sleep 10'
            pid = 1234
            returncode = None

            def __init__(self, *args, **kwargs):
                events.append(('popen', args, kwargs))

            def communicate(self, input=None, timeout=None):
                events.append(('communicate', input, timeout))
                raise KeyboardInterrupt()

            def terminate(self):
                events.append(('terminate',))

            def wait(self, timeout=None):
                events.append(('wait', timeout))
                self.returncode = -15

            def kill(self):
                events.append(('kill',))

        monkeypatch.setattr(modules.utils.subprocess, 'Popen', FakePopen)
        monkeypatch.setattr(modules.utils.os, 'killpg', lambda pid, sig: events.append(('killpg', pid, sig)))

        try:
            modules.utils.Shell.run('sleep 10', start_new_session=True)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError('Expected KeyboardInterrupt to propagate')

        assert events[0][2]['start_new_session'] is True
        assert ('killpg', 1234, modules.utils.signal.SIGTERM) in events
        assert ('terminate',) not in events
        assert ('wait', 5) in events
        assert ('killpg', 1234, modules.utils.signal.SIGKILL) not in events
        assert ('kill',) not in events

    def test_patch_file_replaces_existing_block_without_duplicates(self, modules, tmp_path):
        target = tmp_path / 'config.sh'
        target.write_text(
            'export KEEP=1\n'
            '### APPLET - demo:demo-block ###\n'
            'export DEMO=0\n'
            '### END - demo:demo-block ###\n'
        )

        modules.utils.Files.patch_file(target, 'demo-block', ['export DEMO=1'], app_name='demo')
        first_pass = target.read_text()
        modules.utils.Files.patch_file(target, 'demo-block', ['export DEMO=1'], app_name='demo')

        assert first_pass == (
            'export KEEP=1\n'
            '### APLET - demo:demo-block ###\n'
            'export DEMO=1\n'
            '### END - demo:demo-block ###\n'
        )
        assert target.read_text() == first_pass

    def test_patch_file_keeps_raw_shell_substitution_literal(self, modules, tmp_path):
        target = tmp_path / 'config.sh'

        modules.utils.Files.patch_file(target, 'demo-block', ['eval "$(pyenv init - bash)"'], app_name='demo')

        assert target.read_text() == (
            '### APLET - demo:demo-block ###\n'
            'eval "$(pyenv init - bash)"\n'
            '### END - demo:demo-block ###\n'
        )

    def test_patch_file_expands_explicit_cmd_placeholders(self, modules, monkeypatch, tmp_path):
        target = tmp_path / 'config.sh'
        commands = []
        monkeypatch.setattr(
            modules.utils.Shell,
            'run',
            lambda command, **kwargs: commands.append(command) or type('Result', (), {'stdout': 'amd64\n'})(),
        )

        modules.utils.Files.patch_file(
            target,
            'demo-block',
            ['Architectures: {{cmd:dpkg --print-architecture}}'],
            app_name='demo',
        )

        assert commands == ['dpkg --print-architecture']
        assert 'Architectures: amd64\n' in target.read_text()

    def test_patch_file_supports_multiple_placeholders_per_line(self, modules, monkeypatch, tmp_path):
        target = tmp_path / 'config.sh'
        outputs = {
            'whoami': 'alice\n',
            'uname -m': 'x86_64\n',
        }
        monkeypatch.setattr(
            modules.utils.Shell,
            'run',
            lambda command, **kwargs: type('Result', (), {'stdout': outputs[command]})(),
        )

        modules.utils.Files.patch_file(
            target,
            'demo-block',
            ['User={{cmd:whoami}} Arch={{cmd:uname -m}}'],
            app_name='demo',
        )

        assert 'User=alice Arch=x86_64\n' in target.read_text()

    def test_patch_file_rejects_malformed_placeholders(self, modules, tmp_path):
        target = tmp_path / 'config.sh'

        try:
            modules.utils.Files.patch_file(target, 'demo-block', ['Arch={{cmd:uname -m}'], app_name='demo')
        except ValueError as exc:
            assert 'Malformed patch placeholder' in str(exc)
        else:
            raise AssertionError('Expected malformed placeholder to fail')

    def test_patch_file_rejects_multiline_placeholder_output(self, modules, monkeypatch, tmp_path):
        target = tmp_path / 'config.sh'
        monkeypatch.setattr(
            modules.utils.Shell,
            'run',
            lambda command, **kwargs: type('Result', (), {'stdout': 'one\ntwo\n'})(),
        )

        try:
            modules.utils.Files.patch_file(target, 'demo-block', ['Arch={{cmd:uname -m}}'], app_name='demo')
        except ValueError as exc:
            assert 'returned multiple lines' in str(exc)
        else:
            raise AssertionError('Expected multiline placeholder output to fail')

    def test_patch_file_propagates_placeholder_command_failures(self, modules, monkeypatch, tmp_path):
        target = tmp_path / 'config.sh'
        monkeypatch.setattr(
            modules.utils.Shell,
            'run',
            lambda command, **kwargs: (_ for _ in ()).throw(RuntimeError('command failed')),
        )

        try:
            modules.utils.Files.patch_file(target, 'demo-block', ['Arch={{cmd:uname -m}}'], app_name='demo')
        except RuntimeError as exc:
            assert str(exc) == 'command failed'
        else:
            raise AssertionError('Expected placeholder command failure to propagate')

    def test_patch_file_expands_placeholders_before_helper_dispatch(self, modules, monkeypatch, tmp_path):
        target = tmp_path / 'config.sh'
        helper_calls = []
        monkeypatch.setattr(modules.utils.Files, '_can_patch_directly', lambda path: False)
        monkeypatch.setattr(
            modules.utils.Shell,
            'run',
            lambda command, **kwargs: type('Result', (), {'stdout': 'amd64\n'})(),
        )
        monkeypatch.setattr(modules.utils.Files, '_run_privileged_helper', lambda payload: helper_calls.append(payload))

        modules.utils.Files.patch_file(
            target,
            'demo-block',
            ['Architectures: {{cmd:dpkg --print-architecture}}'],
            app_name='demo',
        )

        assert helper_calls == [
            {
                'action': 'patch_file',
                'path': str(target),
                'app_name': 'demo',
                'block_id': 'demo-block',
                'lines': ['Architectures: amd64'],
            }
        ]

    def test_patch_file_falls_back_to_helper_on_permission_error(self, modules, monkeypatch, tmp_path):
        target = tmp_path / 'config.sh'
        helper_calls = []
        monkeypatch.setattr(modules.utils.Files, '_run_privileged_helper', lambda payload: helper_calls.append(payload))
        file_helper = importlib.import_module('aplet.file_helper')
        monkeypatch.setattr(
            file_helper,
            'patch_file_impl',
            lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError('denied')),
        )

        modules.utils.Files.patch_file(target, 'demo-block', ['export DEMO=1'], app_name='demo')

        assert helper_calls == [
            {
                'action': 'patch_file',
                'path': str(target),
                'app_name': 'demo',
                'block_id': 'demo-block',
                'lines': ['export DEMO=1'],
            }
        ]

    def test_config_set_inventory_path_replaces_existing(self, modules, monkeypatch, tmp_path):
        config_file = tmp_path / 'aplet.conf'
        config_file.write_text('DEFAULT_INVENTORY_PATH: builtin\nPREFERENCE:\n  - apt\n')
        monkeypatch.setattr(modules.utils.Config, 'FILE', config_file)

        modules.utils.Config.set_inventory_path(Path('/tmp/inventory.yml'))

        lines = config_file.read_text().splitlines()
        assert lines[0] == 'DEFAULT_INVENTORY_PATH: /tmp/inventory.yml'
        assert lines[1] == 'PREFERENCE:'

    def test_config_set_inventory_path_inserts_when_missing(self, modules, monkeypatch, tmp_path):
        config_file = tmp_path / 'aplet.conf'
        config_file.write_text('PREFERENCE:\n  - apt\n')
        monkeypatch.setattr(modules.utils.Config, 'FILE', config_file)

        modules.utils.Config.set_inventory_path(Path('/tmp/inventory.yml'))

        lines = config_file.read_text().splitlines()
        assert lines[0] == 'DEFAULT_INVENTORY_PATH: /tmp/inventory.yml'
        assert lines[1] == 'PREFERENCE:'

    def test_config_set_inventory_path_preserves_other_content(self, modules, monkeypatch, tmp_path):
        config_file = tmp_path / 'aplet.conf'
        original = (
            'DEFAULT_INVENTORY_PATH: builtin\n'
            'DEFAULT_REPO_DIR: ~/Apps/\n'
            '# A comment\n'
            'PREFERENCE:\n'
            '  - apt\n'
            '  - pacman\n'
            '# Another comment\n'
        )
        config_file.write_text(original)
        monkeypatch.setattr(modules.utils.Config, 'FILE', config_file)

        modules.utils.Config.set_inventory_path(Path('/tmp/inventory.yml'))

        lines = config_file.read_text().splitlines()
        assert lines[0] == 'DEFAULT_INVENTORY_PATH: /tmp/inventory.yml'
        assert lines[1] == 'DEFAULT_REPO_DIR: ~/Apps/'
        assert lines[2] == '# A comment'
        assert lines[3] == 'PREFERENCE:'
        assert lines[4] == '  - apt'
        assert lines[5] == '  - pacman'
        assert lines[6] == '# Another comment'

    def test_config_set_inventory_path_uses_tilde_for_home_path(self, modules, monkeypatch, tmp_path):
        config_file = tmp_path / 'aplet.conf'
        config_file.write_text('DEFAULT_INVENTORY_PATH: builtin\n')
        monkeypatch.setattr(modules.utils.Config, 'FILE', config_file)

        home_inventory = tmp_path / 'inventory.yml'
        modules.utils.Config.set_inventory_path(home_inventory)

        lines = config_file.read_text().splitlines()
        assert lines[0] == f'DEFAULT_INVENTORY_PATH: ~/inventory.yml'

    def test_config_set_inventory_path_uses_absolute_for_non_home_path(self, modules, monkeypatch, tmp_path):
        config_file = tmp_path / 'aplet.conf'
        config_file.write_text('DEFAULT_INVENTORY_PATH: builtin\n')
        monkeypatch.setattr(modules.utils.Config, 'FILE', config_file)

        modules.utils.Config.set_inventory_path(Path('/etc/inventory.yml'))

        lines = config_file.read_text().splitlines()
        assert lines[0] == 'DEFAULT_INVENTORY_PATH: /etc/inventory.yml'

    def test_config_set_inventory_path_builtin(self, modules, monkeypatch, tmp_path):
        config_file = tmp_path / 'aplet.conf'
        config_file.write_text('DEFAULT_INVENTORY_PATH: /old/path.yml\n')
        monkeypatch.setattr(modules.utils.Config, 'FILE', config_file)

        modules.utils.Config.set_inventory_path('builtin')

        lines = config_file.read_text().splitlines()
        assert lines[0] == 'DEFAULT_INVENTORY_PATH: builtin'
