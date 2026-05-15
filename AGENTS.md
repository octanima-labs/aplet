# AGENTS.md

## Entry Points
- First of all, activate virtual environment: `source .venv/bin/activate` 
- Run the CLI as `python3 -m aplet ...` from the repo root, or as `aplet ...` after installation.
- `aplet/cli.py` is the wired CLI entrypoint. `aplet/managers.py` contains the package-manager adapters, `aplet/inventory.py` contains `AppInventory`, and `aplet/utils.py` contains config loading and shell helpers.
- `apps/` holds reference shell snippets for package setup; nothing under `aplet/` imports those scripts.

## Environment And Side Effects
- Importing `aplet` modules should be side-effect light for library use; CLI initialization loads user config, configures logging, detects package managers, and loads inventory.
- Runtime config is created at `~/.config/aplet/aplet.conf` from `aplet/resources/aplet.conf` when missing.
- The default user inventory path is `~/.local/share/aplet/inventory.yml`; use `HOME=$PWD` for local smoke tests if you want reads and writes to stay inside the repo.
- Runtime dependencies are declared in `pyproject.toml`; development dependencies live under the `dev` optional dependency group.

## Verification

- Use `pytest` to create the test suite in the dir `tests/`. Test only 
- The reliable lightweight syntax check is `python3 -m py_compile aplet/*.py`.
- Useful smoke tests that avoid system mutation: `HOME=$PWD python3 -m aplet --help`, `HOME=$PWD python3 -m aplet inv`, and `HOME=$PWD python3 -m aplet inv search -n sublime-text`.
- Do not use `python3 -m aplet install ...` for routine verification. The code shells out with `subprocess.run(..., shell=True, check=True)` and backend methods can write to `/etc` or invoke the real package manager.
- NEVER test `install`.

## Incomplete Or Misleading Paths
- `AppInventory.save`, `AppInventory.add_app`, and `AppInventory.remove_app` are still TODOs.
- Most repo/GPG list and remove methods in the package-manager backends are stubs; do not assume non-install flows work across managers.
- `python3 -m aplet conf -r` is not a reliable readback check today because config read-only output is rendered directly and should be verified through focused tests instead.

## Docs Build

Install documentation dependencies and build the site locally:

```bash
python3 -m pip install -e '.[docs]'
python3 -m sphinx -W -b html docs docs/_build/html
```

The published site is deployed to GitHub Pages from release tags and manual workflow runs.


## Search Hygiene
- A project-local `.venv/` exists at the repo root and will pollute file searches. Restrict searches to `aplet/`, tests, and root docs/config files, unless you explicitly need the virtualenv.

## TODOs
- [X] Review `pip` manager detection. It says I have it installed but `which` and `python -m pip` report errors. Of course, it is visible because of the virtual environment.
- [ ] Test install/uninstall apps (heavy testing with docker)
  - Add test to test every possible app in each platform. The test output shoul crearly which app installed, which failed, which installed but post-install failed, and which were escaped.
- [ ] Refactoring for better code readability
  - [ ] `AppInventory` is a mix of logic and display methods, isnt it? 


## Future version features
- Create simple GUI for install/uninstall.
  - show a selectable row.
  - The selected row is expanded, like in detailed, view. The rest of rows follow the "normal" display. Select/deselect apps with space. Press enter to confirm the selection (press enter again to confirm) then proceed with the batch installation included the `needed` flag.
  - Use `rich`/`Textual` python libraries to generate a beautiful TUI


- the left hand should be "thumb-up"
- The gear on the book, make it simple, just the gear. Then place an `A` inside the gear