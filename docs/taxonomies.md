# Taxonomy Guide

This document defines the recommended category and tag taxonomy for `aplet` inventories.

## Goals

- Keep category trees predictable and easy to browse.
- Use categories for hierarchical classification.
- Use tags for cross-cutting traits and search filters.
- Reuse a shared vocabulary so inventories remain consistent.

## Categories

Categories are hierarchical and must be declared as a YAML list.

Example:

```yaml
category: [development, python, tooling]
```

Rules:

- Categories use plural bucket names where appropriate, such as `editors`, `browsers`, `libraries`, and `containers`.
- Category tokens must be lowercase.
- Words inside a token must use `-` as separator.
- Digits are allowed.
- Categories should usually be 2-3 levels deep.
- Categories describe what the app is primarily for.

Recommended top-level categories:

- `development`
- `system`
- `productivity`
- `internet`
- `media`
- `gaming`
- `security`

Recommended hierarchy:

```text
development
  ai
    tools
  api
    clients
  containers
  editors
  ide
    python
  javascript
    runtimes
  python
    libraries
    runtimes
    tooling
  terminal
    multiplexers
  version-control

system
  desktop
    compositors
  package-management
    arch
    universal

productivity
  notes
  utilities
    screenshots

internet
  browsers

media
  graphics
    drawing
  video
    streaming

gaming
  launchers

security
  password-managers
```

## Tags

Tags are flat labels used for filtering and discovery.

Example:

```yaml
tags: [python, cli, essential]
```

Rules:

- Tags must be lowercase.
- Words inside a tag must use `-` as separator.
- Digits are allowed.
- Tags should describe traits, not hierarchy.
- Reuse existing tags instead of inventing near-duplicates.

Recommended shared tag vocabulary:

- Interface and style: `cli`, `gui`, `tui`.
- Importance: `essential`, `recommended`, `popular`.
- Ecosystems: `python`, `javascript`, `jetbrains`.
- Usage: `editor`, `browser`, `terminal`, `container`, `devops`, `testing`, `coding`.
- Platform and desktop: `desktop`, `wayland`, `tiling`, `cross-platform`, `sandboxed`.
- Domain: `ai`, `http`, `yaml`, `html`, `scraping`, `markdown`, `sync`, `privacy`, `gaming`, `recording`, `streaming`, `art`, `creative`, `encryption`, `runtime`, `aur`.

## How To Choose Categories

- Use categories for the app's main role.
- Prefer stable product domains over temporary usage context.
- Put infrastructure and developer tooling under `development` when the main audience is developers.
- Put OS-level package ecosystems under `system`.

Examples:

- `git` -> `[development, version-control]`
- `tmux` -> `[development, terminal, multiplexers]`
- `docker` -> `[development, containers]`
- `flatpak` -> `[system, package-management, universal]`
- `firefox` -> `[internet, browsers]`

## How To Choose Tags

- Use tags for traits users may want to search across categories.
- Keep tags compact and reusable.
- Prefer 2-4 tags per app.
- Avoid category duplication unless the tag is genuinely useful as a search keyword.

Examples:

- `httpie` -> `[cli, http, testing]`
- `vscode` -> `[gui, editor, popular]`
- `keepassxc` -> `[gui, desktop, encryption]`

## Example Inventory Snippet

```yaml
apps:
  pipx:
    candidate: pipx
    category: [development, python, tooling]
    tags: [python, cli, essential]
    managers:
      brew:
      scoop:
```
