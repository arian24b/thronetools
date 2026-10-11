# ThroneTools

[فارسی](README.fa.md)

Cross-platform CLI to install, update, back up, restore and remove **Throne** (and the older NekoRay) on Linux, macOS and Windows. It can also install the geoip/geosite databases and turn a Wi-Fi hotspot on and off (Linux and macOS).

## Install

Python 3.12 to 3.15.

```bash
uv tool install thronetools      # or: pipx install thronetools
thronetools --help
```

From a clone: `uv sync && uv run thronetools --help`.

## Commands

| Command | What it does |
|---|---|
| `install` | install Throne |
| `app-update --app {throne,nekoray}` | update Throne to the latest release |
| `app-version --app {throne,nekoray}` | show the installed version and install path |
| `backup --app A [--output PATH]` | back the configuration up to a zip |
| `restore --app A --zip FILE` | restore a backup |
| `remove [--app A]` | uninstall Throne or NekoRay (asks which one if both are installed) |
| `reinstall --app A [--backup] [--output PATH] [--force]` | uninstall and install again, optionally keeping a backup |
| `geo-install --app A` | install or refresh the geoip and geosite databases |
| `hotspot enable [--iface I] [--ssid S] [--password P] [--dry-run]` | start a hotspot (Linux, macOS) |
| `hotspot disable [--dry-run]` | stop it |

`--app` defaults to `throne` where it is optional. `restore` and `reinstall` ask for `--app` when you leave it out, and `hotspot enable` asks for the password.

> `app-version` and `app-update` used to be called `version` and `update`. Those names now belong to the tool itself (see below).

## Examples

```bash
thronetools install
thronetools app-update --app throne
thronetools geo-install --app throne
thronetools backup --app nekoray --output ~/Backups
thronetools restore --app throne --zip ~/Backups/throne-backup-2026-02-17.zip
thronetools reinstall --app throne --backup
thronetools hotspot enable --iface wlp2s0 --dry-run     # print the commands, change nothing
```

Some operations need elevated privileges, depending on the platform and package manager.

## Common commands

Built on [cfuicli](https://github.com/arian24b/cfui), so it looks and behaves like the other tools in this family.

```bash
thronetools help [command]     # help; -h works on any command
thronetools version            # version and git repository (also: -v)
thronetools update [--check]   # update the tool itself; --check only compares versions
thronetools -q ...             # quiet: no banner or notes (or THRONETOOLS_QUIET=1)
```

- A missing required option is asked for when you run the tool in a terminal. In a pipe or in CI it stops with `--flag is required. Pass --flag <value> or run interactively.` (exit code 2).
- Errors appear in a red box on stderr with a non-zero exit code. Ctrl-C exits with 130.
- Color is used only on a terminal. `NO_COLOR=1` turns it off.

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv build
```

Related tools: [LinkCovery](https://github.com/arian24b/linkcovery), [PEM](https://github.com/arian24b/pem), [ollama-tool-cli](https://github.com/arian24b/ollamatools).

## License

MIT
