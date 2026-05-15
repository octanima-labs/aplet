# Custom Installers

Custom installers are named YAML scripts for install flows that cannot be represented by a package-manager entry alone.

Package-manager wrappers remain the default install path. A custom installer can be forced explicitly with `aplet install --installer <name> <app>`, but otherwise installer selection is preference-driven.

Custom installer names should follow platform-token conventions such as `linux`, `ubuntu_debian`, `macos`, `win`, or combined forms like `macos_linux`.

On Linux, distro-specific installer matching is based primarily on distribution family compatibility from `ID_LIKE`, and only secondarily on exact distro `ID`. Downstream distros like EndeavourOS can therefore match `arch` installers.

## Actions

Custom installer actions currently support:

- `cmd`: executes a shell command.
- `patch_file`: patches a file using an Aplet-managed tagged block.
- Any implemented package manager key: `apt`, `pacman`, `yay`, `yum`, `dnf`, `zypper`, `brew`, `choco`, `scoop`, `flatpak`, `snap`, `npm`, `pip`.
- `git` as an inventory manager and valid preference token.

Linux distro package-manager actions such as `apt`, `pacman`, `yum`, `dnf`, and `zypper` are automatically executed with `sudo`. `brew`, `scoop`, and `choco` are not auto-elevated.

## Example

```yaml
apps:
  demo:
    preference:
      - linux
      - apt
    managers:
      apt:
        candidate: demo
    installers:
      linux:
        - cmd:
          - "curl -fsSL https://pyenv.run | bash"
        - patch_file:
          - '~/.bashrc'
          - 'pyenv-init'
          - 'export PYENV_ROOT="$HOME/.pyenv"'
          - '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"'
          - 'eval "$(pyenv init - bash)"'
        - apt:
          - make
          - build-essential
```

## Managed File Blocks

Custom installers often need to modify `PATH` or other shell config files. To avoid duplicate injections, Aplet owns each managed block using app and block identifiers.

Managed blocks look like this:

```text
### APLET - {APP_NAME}:{BLOCK_ID} ###
[...] # custom lines here
### END - {APP_NAME}:{BLOCK_ID} ###
```

If the same app and block id are patched again, Aplet updates that block in place instead of appending a duplicate.

`patch_file` lines are written literally by default. Aplet does not auto-expand `$VAR` or `$(...)` inside file patches. If a line needs command output at install time, use an explicit placeholder:

```yaml
- 'Architectures: {{cmd:dpkg --print-architecture}}'
```

Placeholder commands are executed through Aplet's shell runner when the patch is applied. Malformed placeholders fail fast. Placeholder command output must be a single line.

`patch_file` automatically uses a privileged helper when the target file cannot be patched directly with the current user's permissions. Placeholder commands are still resolved before that helper is invoked, so `{{cmd:...}}` runs in the invoking user's context.

## Command Actions

Each `cmd` action runs in its own subprocess. Environment changes from one `cmd` do not carry over to the next one automatically. If a later command needs a freshly sourced file or updated `PATH` immediately, chain those operations in the same command:

```yaml
- cmd:
  - 'source ~/.bashrc && pyenv install 3.12.2'
```

On Unix-like systems Aplet runs `cmd` actions through `bash`. On Windows Aplet runs them through PowerShell.
