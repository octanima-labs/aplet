# Getting Started

## Install For Development

From the repository root, activate the virtual environment and install the project:

```bash
source .venv/bin/activate
python3 -m pip install -e .
```

Run the CLI from the repository root:

```bash
python3 -m aplet --help
python3 -m aplet inv
python3 -m aplet inv search -n sublime-text
```

After installation, the console script is also available as:

```bash
aplet --help
```

## Runtime Files

Aplet creates user runtime files when needed:

- Config: `~/.config/aplet/aplet.conf`
- Default inventory: `~/.local/share/aplet/inventory.yml`
- Logs: `~/.local/state/aplet/aplet.log`

For local smoke tests that should not read or write the real home directory, run commands with `HOME=$PWD`:

```bash
HOME=$PWD python3 -m aplet --help
HOME=$PWD python3 -m aplet inv
```

Do not use `python3 -m aplet install ...` as a routine smoke test. Install commands can call real package managers and write to system locations.

## Supported Managers

Aplet currently has adapters for:

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
