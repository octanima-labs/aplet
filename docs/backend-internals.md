# Backend Internals

Backend manager classes are implementation details. They are tested directly and can be useful for contributors, but they are not the stable public Python API.

Stable library entry points are documented in [](api.md). Backend classes such as `Apt`, `Pacman`, `Flatpak`, `Pip`, and `GitManager` may change as adapter behavior evolves.

## Adapter Contract

Backends generally provide operations for:

- Preparing manager state before install, such as adding repos or GPG keys.
- Installing one or more targets.
- Checking whether a target is installed when supported.
- Uninstalling one or more targets.
- Cleaning up manager state after uninstall when requested.

The inventory layer selects adapters through runtime availability and preference order. Custom installer actions can also call implemented manager actions directly.

## Repository And GPG Support

Repo and GPG support varies by backend. Several list/remove flows are intentionally incomplete or backend-specific, so documentation should avoid promising consistent behavior across all managers until those implementations are complete.

## Contributor Guidance

When changing a backend adapter:

- Keep install/uninstall commands non-interactive where possible.
- Preserve the inventory-level behavior documented in [](package-managers.md).
- Add focused unit tests for command construction and target parsing.
- Use Docker integration tests only for real package-manager behavior.
