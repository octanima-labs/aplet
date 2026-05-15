# Inventory Format

Aplet inventories are YAML files with an Aplet inventory header and an `apps` mapping.

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

## App Fields

Supported top-level app fields include:

- `candidate`: Default package, executable, or manager target. Defaults to the inventory app name.
- `preference`: Per-app install method preference tokens.
- `category`: Hierarchical category path as a YAML list.
- `tags`: Flat labels for search and grouping.
- `installed`: Optional explicit state, one of `true`, `false`, or `null`.
- `dependencies`: Other inventory app names to install first when using `aplet install --needed`.
- `managers`: Package-manager target definitions.
- `installers`: Custom installer scripts.
- `uninstallers`: Custom uninstaller scripts.
- `post_install`: Custom scripts to run after installation.
- `probes`: Read-only checks used to detect whether an app is already installed.

## Managers

Manager entries can be empty or define manager-specific fields:

```yaml
apps:
  vscode:
    candidate: code
    managers:
      apt:
        candidate: code
        repo: https://packages.microsoft.com/repos/code
      snap:
        candidate: code
        classic: true
```

An empty manager entry means the app-level `candidate` should be used:

```yaml
managers:
  apt:
```

## Dependencies

Dependencies must reference other apps in the same inventory:

```yaml
apps:
  yay:
    dependencies:
      - git
    installers:
      arch:
        - pacman: git base-devel
        - cmd:
          - git clone https://aur.archlinux.org/yay-bin.git ~/.local/share/yay-bin
          - cd ~/.local/share/yay-bin && makepkg -si
```

Dependencies are installed only when requested with `aplet install --needed`.

## Classification

Use `category` for hierarchy and `tags` for cross-cutting filters. See [](taxonomies.md) for the recommended shared vocabulary.
