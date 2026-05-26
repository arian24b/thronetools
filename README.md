# ThroneTools

Cross-platform CLI to install, reinstall, uninstall, and manage configuration for **Throne**(NekoRay) on Linux, macOS, and Windows.

[![GitHub stars](https://img.shields.io/github/stars/arian24b/thronetools.svg?style=social&label=Star)](https://github.com/arian24b/thronetools)
[![GitHub forks](https://img.shields.io/github/forks/arian24b/thronetools.svg?style=social&label=Fork)](https://github.com/arian24b/thronetools)
[![GitHub issues](https://img.shields.io/github/issues/arian24b/thronetools.svg)](https://github.com/arian24b/thronetools/issues)
[![Actions Status](https://github.com/arian24b/thronetools/workflows/Test/badge.svg)](https://github.com/arian24b/thronetools/actions)
[![Coverage Status](https://coveralls.io/repos/github/arian24b/thronetools/badge.svg?branch=main)](https://coveralls.io/github/arian24b/thronetools?branch=main)
[![License: MIT](https://thronetools.readthedocs.io/en/stable/_static/license.svg)](https://github.com/arian24b/thronetools/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/thronetools)](https://pypi.org/project/thronetools/)
[![Supported Python Versions](https://img.shields.io/pypi/pyversions/thronetools?color=brightgreen)](https://pypi.org/project/thronetools)

## Requirements

- [uv](https://docs.astral.sh/uv/)

## Features

- **Cross-platform** — Linux, macOS, and Windows support
- **Self-update** — Update Throne to the latest release with one command
- **Geo data management** — Install and verify geoip/geosite databases for sing-box

## Quick Start (uv)

```bash
# from repo root
uv sync
uv run thronetools --help
```

Run without subcommands to show the styled help:

```bash
uv run thronetools
```

## Commands

```bash
thronetools install
thronetools update --app {throne|nekoray}
thronetools backup --app {throne|nekoray} [--output <path-or-dir>]
thronetools restore --app {throne|nekoray} --zip <backup.zip>
thronetools remove --app {throne|nekoray}
thronetools reinstall --app {throne|nekoray} [--backup] [--output <path-or-dir>] [--force]
thronetools version --app {throne|nekoray}
thronetools geo-install --app {throne|nekoray}
thronetools hotspot enable [--iface <iface>] [--ssid <name>] [--password <pass>] [--dry-run]
thronetools hotspot disable [--dry-run]
```

## Common Examples

```bash
# Install Throne
uv run thronetools install

# Update Throne to the latest version
uv run thronetools update --app throne

# Install/update geoip and geosite databases
uv run thronetools geo-install --app throne

# Backup Throne config to current directory
uv run thronetools backup --app throne

# Backup NekoRay config to a specific folder
uv run thronetools backup --app nekoray --output ~/Backups

# Restore Throne config
uv run thronetools restore --app throne --zip ~/Backups/throne-backup-2026-02-17.zip

# Reinstall with backup + restore flow
uv run thronetools reinstall --app throne --backup

# Show installed app details
uv run thronetools version --app throne

# Preview hotspot commands without applying changes
uv run thronetools hotspot enable --iface wlp2s0 --dry-run
```

## Notes

- `hotspot` commands are supported on Linux and macOS. On Windows, hotspot subcommands are not available.
- Some operations require elevated privileges depending on platform/package manager.

## Development

```bash
# Lint/format (Ruff is configured in pyproject.toml)
uv run ruff check .
uv run ruff format .

# Build package
uv build
```

## Related Projects

Explore other CLI tools by Arian Omrani:

- **[LinkCovery](https://github.com/arian24b/linkcovery)** - Modern bookmark management CLI tool
- **[PEM](https://github.com/arian24b/pem)** - Python Execution Manager - Schedule and execute Python scripts
- **[OllamaTools](https://github.com/arian24b/ollamatools)** - CLI tool for managing Ollama models

## Install as a tool (optional)

If you want a globally available command via `uv`:

```bash
uv tool install .
thronetools --help
```

To update later:

```bash
uv tool upgrade thronetools
```

## License

MIT License — see the LICENSE file for details.

## Contributing

Contributions are welcome! Feel free to submit a pull request.
