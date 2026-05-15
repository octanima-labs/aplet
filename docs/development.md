# Development

## Setup

Activate the project virtual environment before running development commands:

```bash
source .venv/bin/activate
```

Install development dependencies:

```bash
python3 -m pip install -e '.[dev,docs]'
```

## Verification

Run the lightweight syntax check:

```bash
python3 -m py_compile aplet/*.py
```

Run the test suite:

```bash
pytest
```

Build documentation with warnings treated as errors:

```bash
python3 -m sphinx -W -b html docs docs/_build/html
```

Useful smoke tests that avoid system mutation:

```bash
HOME=$PWD python3 -m aplet --help
HOME=$PWD python3 -m aplet inv
HOME=$PWD python3 -m aplet inv search -n sublime-text
```

Do not use `python3 -m aplet install ...` for routine verification. The install path can invoke real package managers and write to system locations.

## Docker Integration Tests

Real package-manager install/remove tests live under `tests/integration/` and are opt-in. They refuse to run unless `APLET_REAL_INSTALL_TESTS=1` is set and the test process is inside a container.

Run all current Linux manager targets:

```bash
scripts/docker-integration
```

Run selected targets:

```bash
scripts/docker-integration apt
scripts/docker-integration dnf pacman
```

Current targets are `apt-debian`, `apt-ubuntu`, `dnf`, `yum`, `zypper`, and `pacman`. The tests call the manager classes directly and verify real package install, installed-state query, uninstall, repo listing, and GPG listing against disposable containers.
