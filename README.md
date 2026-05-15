<p align="center">
  <img src="docs/_static/full_logo.png" alt="Aplet" width="360">
</p>

# An Application Library Easibily Tunable

Aplet is a customizable application inventory. It allows you to install/uninstall applications automatically from different sources, being cross-platform ready. You can also define custom automatizations for your apps.

Available applications are declared in a YAML inventory. When the user run `install`, aplet detects available package managers on the current host, chooses an installation method by preference order and executes it. 

## Documentation

Full documentation is published with GitHub Pages:

https://octanima-labs.github.io/aplet/

Build it locally with:

```bash
python3 -m pip install -e '.[docs]'
python3 -m sphinx -W -b html docs docs/_build/html
```

Important local pages:

- Inventory format: `docs/inventory.md`
- Configuration: `docs/configuration.md`
- Custom installers: `docs/custom-installers.md`
- Package-manager notes: `docs/package-managers.md`
- Taxonomy guide: `docs/taxonomies.md`
- Python API: `docs/api.md`

## Supported Managers

- `apt`
- `pacman`
- `yay`
- `yum`
- `dnf`
- `zypper`
- `brew`
- `choco`
- `scoop`
- `git`
- `flatpak`
- `snap`
- `npm`
- `pip`
- `pipx`

`apk` is not implemented yet.

## Quick Start

From the repository root:

```bash
source .venv/bin/activate
python3 -m pip install -e .
python3 -m aplet --help
```

Useful non-mutating smoke tests:

```bash
HOME=$PWD python3 -m aplet --help
HOME=$PWD python3 -m aplet inv
HOME=$PWD python3 -m aplet inv search -n sublime-text
```

Avoid using `python3 -m aplet install ...` for routine smoke tests because install commands can invoke real package managers and write to system locations.

## Examples

List inventory entries:

```bash
aplet inv
aplet inv list --categories --show-tags
```

Search inventory entries:

```bash
aplet inv search -n firefox neovim
aplet inv search -c "development > editors" -t favorite
```

Install and uninstall apps from the inventory:

```bash
aplet install firefox
aplet install --needed pyenv
aplet uninstall firefox
```

## Minimal Inventory

```yaml
### APLET INVENTORY ###
apps:
  firefox:
    candidate: firefox
    category: [internet, browsers]
    tags: [gui, browser, popular]
    managers:
      apt:
      flatpak:
        candidate: org.mozilla.firefox
```

See `docs/inventory.md` and `docs/taxonomies.md` for the full format and classification guidance.

## Development

Run syntax checks and tests:

```bash
python3 -m py_compile aplet/*.py
pytest
```

Real package-manager integration tests are opt-in and run in disposable containers. See `docs/development.md`.
