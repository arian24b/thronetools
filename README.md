# ThroneTools

Cross-platform CLI to install, reinstall, uninstall, and manage configuration for **Throne** and **NekoRay** on Linux, macOS, and Windows.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

## Quick Start (uv)

```bash
# from repo root
uv sync
uv run thronetools --help
```

### Interactive mode

Run without subcommands to open the interactive menu:

```bash
uv run python thronetools.py
```

## Commands

```bash
thronetools install
thronetools backup --app {throne|nekoray} [--output <path-or-dir>]
thronetools restore --app {throne|nekoray} --zip <backup.zip>
thronetools remove --app {throne|nekoray}
thronetools reinstall --app {throne|nekoray} [--backup] [--output <path-or-dir>] [--force]
thronetools info --app {throne|nekoray}
thronetools hotspot enable [--iface <iface>] [--ssid <name>] [--password <pass>] [--dry-run]
thronetools hotspot disable [--dry-run]
```

## Common Examples

```bash
# Install Throne
uv run thronetools install

# Backup Throne config to current directory
uv run thronetools backup --app throne

# Backup NekoRay config to a specific folder
uv run thronetools backup --app nekoray --output ~/Backups

# Restore Throne config
uv run thronetools restore --app throne --zip ~/Backups/throne-backup-2026-02-17.zip

# Reinstall with backup + restore flow
uv run thronetools reinstall --app throne --backup

# Show installed app details
uv run thronetools info --app throne

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