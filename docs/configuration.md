# Configuration

Aplet reads runtime configuration from `~/.config/aplet/aplet.conf`. When the file is missing, it is created from `aplet/resources/aplet.conf`.

## Preference Order

Aplet resolves installation methods by runtime preference order. The default global order is:

```yaml
PREFERENCE:
- apt
- pacman
- yay
- yum
- dnf
- zypper
- brew
- choco
- scoop
- git
- npm
- pip
- pipx
- flatpak
- snap
- custom_installers
```

Per-app preference can prepend and override the global order:

```yaml
apps:
  my-app:
    candidate: myapp
    preference:
      - apt
      - ubuntu_debian
      - flatpak
      - snap
    managers:
      apt:
      flatpak:
        candidate: org.example.MyApp
      snap:
    installers:
      ubuntu_debian:
        - cmd:
          - 'echo install me'
```

Rules:

- App-level `preference` is prepended to global `PREFERENCE`.
- `custom_installers` expands to all declared custom installers not already explicitly listed.
- Only methods available on the current host are considered.
- If no methods are available, inventory listing shows `<app> (installation unavailable)`.
- `aplet install -f ...` skips already-installed checks and runs the selected install command anyway. This is not guaranteed to be a true reinstall for every manager or custom installer.

## Icons

`aplet inventory list --icons` can prepend icons to apps, categories, and tag labels depending on the selected list view.

Built-in app and keyword icon mappings live in `aplet/resources/icons.yml`.

`~/.config/aplet/aplet.conf` can override those defaults with a nested `ICON_OVERRIDES` section:

```yaml
ICON_OVERRIDES:
  defaults:
    app: "📦"
    category: "📁"
    tag: "🏷️"

  apps:
    firefox: "🦊"
    vscode: ""

  categories:
    development: "🛠️"

  tags:
    recommended: "👍"

  keywords:
    browser: "🌐"
    favorite: "⭐"
```

Notes:

- `apps`, `categories`, and `tags` use exact case-insensitive matches.
- `keywords` are shared fallback heuristics used after exact matches.
- Exact config matches override `aplet/resources/icons.yml` icon mappings.
- Unknown keys under `ICON_OVERRIDES` are ignored.
- Blank strings disable the icon for that specific match level.

Resolution order:

- Apps: config exact app match, built-in exact app match, config keyword match, built-in keyword match, config app default, built-in app default.
- Categories: config exact category match, config keyword match, built-in keyword match, config category default, built-in category default.
- Tags: config exact tag match, config keyword match, built-in keyword match, config tag default, built-in tag default.

When a config match resolves to `""`, Aplet stops there and leaves the label unprefixed instead of falling back to lower-priority matches.
