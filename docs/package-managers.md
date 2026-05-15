# Package Managers

Package-manager entries define how an inventory app maps to one or more backend adapters. Backends are selected by availability and preference order.

## Flatpak

```yaml
apps:
  firefox:
    candidate: firefox
    managers:
      flatpak:
        candidate: org.mozilla.firefox
        # remote_name: flathub
        # repo: https://flathub.org/repo/flathub.flatpakrepo
        # user: false
```

Flatpak defaults:

- `remote_name`: `flathub`
- `repo`: `https://flathub.org/repo/flathub.flatpakrepo`
- `user`: `false`

If a custom Flatpak repo is used, `remote_name` must be set explicitly.

## Git

`git` is supported as an inventory manager for public GitHub and GitLab repositories.

```yaml
apps:
  neovim-nightly:
    preference:
      - git
      - apt
    managers:
      git:
        url: https://github.com/neovim/neovim.git
        release: latest
        candidate: '*AppImage'
```

Git manager notes:

- `url` is required and must use either `https://host/OWNER/REPO.git` or `git@host:OWNER/REPO.git`.
- If both `release` and `candidate` are omitted, Aplet installs from source by cloning into `~/Apps/<owner>/<repo>`.
- If either `release` or `candidate` is provided, Aplet resolves a release and downloads the first matching asset.
- Wildcard asset matching is case-insensitive.
- Default release candidates are platform-aware.
- Downloaded release assets are stored under `~/Apps/<owner>/<repo>/_releases/<tag>`.
- `.zip` and `.tar.gz` assets are extracted after download.
- `.deb` assets are installed then removed.
- Other asset types are only downloaded.
- Uninstall removes the full `~/Apps/<owner>/<repo>` tree, including downloaded assets.

Default release candidates:

- Ubuntu/Debian: `*.deb`, then `*.AppImage`, then `*.tar.gz`.
- Linux: `*.AppImage`, then `*.tar.gz`.
- macOS: `*.DMG`.
- Windows: `*.exe`, then `*.msi`, then `*.zip`.
- Unknown hosts: `*.tar.gz`.

## npm

```yaml
apps:
  typescript:
    candidate: typescript
    managers:
      npm:
        candidate: typescript
```

npm notes:

- npm does not use Aplet-managed repo or GPG configuration.
- Inventory-driven npm installs always use global npm installs.
- `Npm.prepare()` is intentionally a no-op, so npm installs do not trigger `npm update`.
- Local npm install, uninstall, update, and list-installed behavior remain available only through the direct `Npm` wrapper API using `global_install=False`.

## yay

```yaml
apps:
  visual-studio-code:
    candidate: code
    managers:
      yay:
        candidate: visual-studio-code-bin
```

yay notes:

- yay does not use Aplet-managed repo or GPG configuration.
- Inventory-driven yay installs do not trigger `yay update`.
- Direct `Yay.install()` uses `--noconfirm --needed`.
- Direct `Yay.uninstall()` uses `--noconfirm`.
- `Yay.list_installed()` is available as a wrapper-only feature.

## snap

```yaml
apps:
  vscode:
    candidate: code
    managers:
      snap:
        candidate: code
        # channel: edge
        # classic: true
```

snap notes:

- snap does not use Aplet-managed repo or GPG configuration.
- Inventory-driven snap installs do not trigger `snap refresh`.
- `channel` is optional and only affects install.
- `classic` is optional, defaults to `false`, and only affects install.
- `Snap.list_installed()` is available as a wrapper-only feature.

## pipx

```yaml
apps:
  httpie:
    candidate: httpie
    managers:
      pipx:
        candidate: httpie
        # global: false
        # include_deps: false
        # python: python3.12
        # fetch_missing_python: false
        # preinstall:
        #   - setuptools
        # index_url: https://pypi.org/simple
        # system_site_packages: false
        # editable: false
        # pip_args: "--pre"
        # include_injected: false
```

pipx notes:

- pipx does not use Aplet-managed repo or GPG configuration.
- Inventory-driven pipx installs do not trigger `pipx upgrade` or `pipx upgrade-all`.
- `aplet install -f ...` becomes a true `pipx reinstall` when the app is already installed.
- Inventory-managed pipx installs default to user scope; set `global: true` to use `pipx --global`.
- `suffix` is intentionally not supported yet in inventory entries.

## pip

```yaml
apps:
  pyyaml:
    candidate: PyYAML
    managers:
      pip:
        candidate: PyYAML
        # version: 1.1.1
        # venv: ~/.venvs/demo
```

pip notes:

- pip does not use Aplet-managed repo or GPG configuration.
- Inventory-driven pip installs do not trigger `pip update`.
- `version` and `venv` are both optional inventory fields.
- When `venv` is set and missing, Aplet creates the parent directories and runs `python -m venv <path>` before installing or updating.
- If `venv` is omitted, Aplet runs plain system `pip`, which may fail on hosts that block system-level installs.
- `version` is only applied automatically when exactly one target is being installed or updated; inline target specifiers like `pkg==1.2.3` are preserved as-is.
- `Pip.update()` is implemented but inventory-managed installs intentionally do not call it.
- `Pip.update()` with no targets runs `pip install --upgrade pip`.
- The CLI supports `--venv PATH` on `aplet install` and `aplet uninstall`; it is honored only for pip-managed targets and ignored with a warning for other methods.
- The CLI also supports inline pip-style target specifiers such as `aplet install pyyaml==6.0.3` or `aplet install requests>=2.31`; those specifiers only affect pip-managed targets and are ignored by other managers.
