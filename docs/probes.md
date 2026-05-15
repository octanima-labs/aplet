# Probes

`probes` let Aplet detect whether an app is already installed before it falls back to manager scans or `PATH` lookups.

There are two probe forms:

- Manager-backed probes reuse a declared manager entry and must stay empty.
- Command probes run read-only `cmd` actions defined in YAML.

Command probes should not change system state. They are meant for checks such as `--version`, `which`, or similar existence tests.

```yaml
apps:
  demo:
    managers:
      flatpak:
        candidate: org.example.Demo
    probes:
      flatpak:
      linux:
        - cmd:
          - 'demo --version'
          - 'which demo'
```

Notes:

- Manager-backed probes require a matching entry under `managers`.
- Command probes currently support only `cmd` actions.
- If a probe succeeds, Aplet treats the app as installed.
