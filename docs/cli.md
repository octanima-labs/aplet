# CLI Reference

Run the CLI as `python3 -m aplet ...` from the repository root, or as `aplet ...` after installation.

## Global Options

```bash
aplet [-v|-vv] <command> ...
```

Verbosity levels:

- No `-v`: `INFO`
- `-v`: `DEBUG`
- `-vv` or higher: `TRACE`

## Install

```bash
aplet install [--installer NAME] [--force] [--needed] [--venv PATH] TARGET [TARGET ...]
```

Examples:

```bash
aplet install firefox
aplet install firefox neovim
aplet install poetry --installer pip
aplet install black --venv .venv
aplet install --needed pyenv
```

## Uninstall

```bash
aplet uninstall [--remove-repo] [--venv PATH] TARGET [TARGET ...]
```

Examples:

```bash
aplet uninstall firefox
aplet uninstall firefox neovim
aplet uninstall my-python-tool --venv .venv
aplet uninstall vscode --remove-repo
```

## Inventory

The `inventory` command has the alias `inv`.

```bash
aplet inventory
aplet inv list
aplet inv search -n firefox neovim
aplet inv search -c "development > editors" -t favorite
aplet inv edit
aplet inv add --source ./apps/firefox.yml
aplet inv rm firefox
aplet inv set ~/my-inventory.yml
aplet inv set builtin
aplet inv new ~/my-inventory.yml --inherit
```

List views:

```bash
aplet inv list --details
aplet inv list --categories
aplet inv list --categories --show-tags --show-methods
aplet inv list --tags
aplet inv list --tag-groups
aplet inv list --all
aplet inv list --icons
```

## Config

```bash
aplet conf
aplet conf --read-only
```

`aplet conf --read-only` is meant for inspecting the current config without editing it.
