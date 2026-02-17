#!/usr/bin/env python3
import os
from argparse import ArgumentParser, RawTextHelpFormatter
from datetime import UTC, datetime
from getpass import getpass
from json import loads
from platform import machine
from plistlib import InvalidFileException
from plistlib import load as plistlib_load
from re import IGNORECASE, compile, escape
from shlex import quote
from shutil import move, rmtree, which
from subprocess import CalledProcessError, CompletedProcess, Popen, run
from sys import exit as sys_exit
from sys import platform as sys_platform
from tempfile import TemporaryDirectory, gettempdir
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

import typer

THRONE_URL = "https://api.github.com/repos/throneproj/Throne/releases/latest"
THRONE_APP_NAME = "Throne"
LINUX_SSID = "thronetools"
LINUX_TUN_IFACE = "nekoray-tun"
LINUX_NFT_TABLE = "throne_hotspot"
LINUX_REQUIRED_INET_TABLE = "sing-box"
HTTP_TIMEOUT = 15


GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"
BOLD = "\033[1m"


BANNER = r"""



████████╗██╗  ██╗██████╗  ██████╗ ███╗   ██╗███████╗
╚══██╔══╝██║  ██║██╔══██╗██╔═══██╗████╗  ██║██╔════╝
   ██║   ███████║██████╔╝██║   ██║██╔██╗ ██║█████╗
   ██║   ██╔══██║██╔══██╗██║   ██║██║╚██╗██║██╔══╝
   ██║   ██║  ██║██║  ██║╚██████╔╝██║ ╚████║███████╗
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝
██╗███╗   ██╗███████╗████████╗ █████╗ ██╗     ██╗     ███████╗██████╗
██║████╗  ██║██╔════╝╚══██╔══╝██╔══██╗██║     ██║     ██╔════╝██╔══██╗
██║██╔██╗ ██║███████╗   ██║   ███████║██║     ██║     █████╗  ██████╔╝
██║██║╚██╗██║╚════██║   ██║   ██╔══██║██║     ██║     ██╔══╝  ██╔══██╗
██║██║ ╚████║███████║   ██║   ██║  ██║███████╗███████╗███████╗██║  ██║
╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝


"""


def color(text, shade) -> str:
    return f"{shade}{text}{NC}"


def show_banner(platform_name) -> None:
    typer.echo(color(BANNER, YELLOW))
    typer.echo(color(f"{THRONE_APP_NAME} Installer for {platform_name}", BLUE))
    typer.echo()


def show_menu_linux() -> None:
    typer.echo(color("Please select an option:", YELLOW))
    typer.echo("1) Install Throne")
    typer.echo("2) Backup configuration")
    typer.echo("3) Restore configuration")
    typer.echo("4) Uninstall")
    typer.echo("5) Enable Hotspot")
    typer.echo("6) Disable Hotspot")
    typer.echo("7) Reinstall")
    typer.echo("8) Info")
    typer.echo("9) Exit")
    typer.echo()


def show_menu_macos() -> None:
    typer.echo(color("Please select an option:", YELLOW))
    typer.echo("1) Install Throne")
    typer.echo("2) Backup configuration")
    typer.echo("3) Restore configuration")
    typer.echo("4) Uninstall")
    typer.echo("5) Reinstall")
    typer.echo("6) Info")
    typer.echo("7) Exit")
    typer.echo()


def show_menu_windows() -> None:
    typer.echo(color("Please select an option:", YELLOW))
    typer.echo("1) Install Throne")
    typer.echo("2) Backup configuration")
    typer.echo("3) Restore configuration")
    typer.echo("4) Uninstall")
    typer.echo("5) Reinstall")
    typer.echo("6) Info")
    typer.echo("7) Exit")
    typer.echo()


def prompt_app_name(prompt_text):
    app_name = input(prompt_text).strip().lower()
    if app_name not in {"nekoray", "throne"}:
        typer.echo(color("Invalid app name. Only 'nekoray' or 'throne' allowed.", RED))
        sys_exit(1)
    return app_name


def run_cmd(cmd, dry_run=False, shell=False, check=True):
    if dry_run:
        if isinstance(cmd, list):
            typer.echo(color("→ " + " ".join(cmd), BLUE))
        else:
            typer.echo(color("→ " + cmd, BLUE))
        return CompletedProcess(cmd, 0)
    return run(cmd, shell=shell, check=check)


def run_capture(cmd):
    return run(cmd, text=True, capture_output=True)


def read_os_release():
    os_release = "/etc/os-release"
    data = {}
    if not os.path.exists(os_release):
        return data
    with open(os_release, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key] = value.strip().strip('"')
    return data


def check_installations(app_name):
    found = False
    if which("dpkg"):
        res = run_capture(["dpkg", "-l"])
        if res.returncode == 0 and app_name in res.stdout:
            typer.echo(color(f"{app_name} package is installed.", YELLOW))
            found = True
    if which("rpm"):
        res = run_capture(["rpm", "-q", app_name])
        if res.returncode == 0:
            typer.echo(color(f"{app_name} package is installed.", YELLOW))
            found = True

    app_variants = ["throne", "Throne"] if app_name == "throne" else ["nekoray", "NekoRay"]

    for variant in app_variants:
        locations = [
            f"/opt/{variant}",
            f"/usr/share/applications/{variant}.desktop",
            os.path.join(
                os.path.expanduser("~"),
                ".local/share/applications",
                f"{variant}.desktop",
            ),
            os.path.join(os.path.expanduser("~"), ".config", variant),
        ]
        for location in locations:
            if os.path.isdir(location) or os.path.isfile(location):
                typer.echo(color(f"Found system installation: {location}", YELLOW))
                found = True
    return found


def github_latest_release():
    req = Request(
        THRONE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ThroneInstaller",
        },
    )
    with urlopen(req, timeout=HTTP_TIMEOUT) as response:
        data = response.read()
    return loads(data.decode("utf-8"))


def download_file(url, dest_path) -> None:
    req = Request(url, headers={"User-Agent": "ThroneInstaller"})
    with (
        urlopen(req, timeout=HTTP_TIMEOUT) as response,
        open(dest_path, "wb") as handle,
    ):
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


def install_app_linux() -> None:
    typer.echo(color("=== INSTALLATION ===", BLUE))
    typer.echo()
    typer.echo("Checking for existing Throne installations...")
    if check_installations("throne") or check_installations("nekoray"):
        typer.echo(
            color(
                "Please uninstall existing Throne or NekoRay installations first using option 4 (Uninstall).",
                YELLOW,
            ),
        )
        typer.echo()
        return

    typer.echo(color("✅ No existing installations found. Proceeding with installation...", GREEN))
    typer.echo()

    os_release = read_os_release()
    distro = os_release.get("ID", "").lower()
    if not distro:
        typer.echo(color("Cannot detect Linux distribution.", RED))
        sys_exit(1)

    if distro in {"ubuntu", "debian", "linuxmint", "pop"}:
        package_type = "deb"
        package_manager = "dpkg"
        install_cmd = ["sudo", "dpkg", "-i"]
        fix_cmd = ["sudo", "apt-get", "install", "-f", "-y"]
        package_pattern = r"Throne.*debian.*\.deb"
    elif distro in {"fedora", "rhel", "centos", "rocky", "almalinux"}:
        package_type = "rpm"
        package_manager = "rpm"
        install_cmd = ["sudo", "rpm", "-i"]
        fix_cmd = ["sudo", "dnf", "install", "-y"]
        package_pattern = r"Throne.*\.el.*\.rpm"
    else:
        typer.echo(color(f"Unsupported distribution: {distro}", RED))
        typer.echo(color("Supported distributions: Ubuntu, Debian, Fedora, RHEL, CentOS", RED))
        sys_exit(1)

    if not which(package_manager):
        typer.echo(color(f"{package_manager} is not installed.", RED))
        sys_exit(1)

    typer.echo("Fetching latest Throne release information...")
    release = github_latest_release()
    assets = release.get("assets", [])
    target_asset = None
    pattern = compile(package_pattern)
    for asset in assets:
        name = asset.get("name", "")
        if pattern.search(name):
            target_asset = asset
            break

    if not target_asset:
        typer.echo(color(f"Could not find {package_type} package in the latest release.", RED))
        typer.echo(color("Available packages:", RED))
        for asset in assets:
            typer.echo(asset.get("name", ""))
        sys_exit(1)

    package_url = target_asset.get("browser_download_url")
    package_name = target_asset.get("name")
    typer.echo(f"Downloading {package_name}...")

    with TemporaryDirectory() as tmpdir:
        dest = os.path.join(tmpdir, package_name)
        download_file(package_url, dest)
        typer.echo(f"Installing Throne {package_type} package...")
        try:
            run_cmd([*install_cmd, dest], check=True)
            typer.echo(color("✅ Throne installed successfully!", GREEN))
        except CalledProcessError:
            typer.echo(
                color(
                    "Installation completed with some warnings. Fixing dependencies...",
                    YELLOW,
                ),
            )
            run_cmd(fix_cmd, check=False)

    typer.echo()
    typer.echo(
        color(
            "✅ Done! Throne has been installed system-wide. You can find it in your applications menu!",
            GREEN,
        ),
    )
    typer.echo()


def zip_dir(source_dir, dest_zip) -> None:
    with ZipFile(dest_zip, "w", compression=ZIP_DEFLATED) as handle:
        for root, _, files in os.walk(source_dir):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, source_dir)
                handle.write(full_path, rel_path)


def backup_config_linux(app_name=None, output_path=None):
    typer.echo(color("=== BACKUP CONFIGURATION ===", BLUE))
    typer.echo()
    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")

    config_dir = ""
    if app_name == "nekoray":
        candidate = os.path.join(os.path.expanduser("~"), ".config/nekoray/config")
        if os.path.isdir(candidate):
            config_dir = candidate
    elif app_name == "throne":
        candidate = os.path.join(os.path.expanduser("~"), ".config/Throne/config")
        if os.path.isdir(candidate):
            config_dir = candidate

    if not config_dir or not os.path.isdir(config_dir):
        typer.echo(color(f"Config directory does not exist: {config_dir}", RED))
        sys_exit(1)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    backup_name = f"{app_name}-backup-{date_str}.zip"
    if output_path:
        dest_path = os.path.join(output_path, backup_name) if os.path.isdir(output_path) else output_path
    else:
        dest_path = os.path.join(os.getcwd(), backup_name)

    typer.echo("📦 Compressing config ...")
    typer.echo(f"Compressing config from {config_dir}...")
    zip_dir(config_dir, dest_path)

    typer.echo(color("✅ Backup created:", GREEN))
    typer.echo(color(dest_path, GREEN))
    typer.echo()
    return dest_path


def restore_config_linux(app_name=None, zip_file=None) -> None:
    typer.echo(color("=== RESTORE CONFIGURATION ===", BLUE))
    typer.echo()
    if not zip_file:
        zip_file = input("Enter the path to the backup .zip file: ").strip()
    if not zip_file:
        typer.echo(color("Please provide the path to the backup .zip file.", RED))
        sys_exit(1)
    if not os.path.isfile(zip_file):
        typer.echo(color(f"File not found: {zip_file}", RED))
        sys_exit(1)

    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")
    restore_dir = ""
    base = ""
    if app_name == "nekoray":
        base = os.path.join(os.path.expanduser("~"), ".config/nekoray")
        restore_dir = os.path.join(base, "config")
    elif app_name == "throne":
        base = os.path.join(os.path.expanduser("~"), ".config/Throne")
        restore_dir = os.path.join(base, "config")

    if not restore_dir:
        typer.echo(color("Target configuration directory does not exist for this app.", RED))
        sys_exit(1)

    if base and not os.path.isdir(base):
        os.makedirs(base, exist_ok=True)

    if os.path.isdir(restore_dir):
        typer.echo(f"Removing existing config: {restore_dir}")
        rmtree(restore_dir)
    os.makedirs(restore_dir, exist_ok=True)

    typer.echo(f"📦 Restoring backup to: {restore_dir}")
    with ZipFile(zip_file, "r") as handle:
        handle.extractall(restore_dir)

    typer.echo(color("✅ Restore complete!", GREEN))
    typer.echo()


def uninstall_app_linux(app_name=None, skip_check=False) -> None:
    typer.echo(color("=== UNINSTALL ===", BLUE))
    typer.echo()
    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")
    typer.echo(f"\nUninstalling {app_name}...")

    if not skip_check and not check_installations(app_name):
        typer.echo(color(f"\n⚠ No {app_name} installations found on this system.", YELLOW))
        typer.echo()
        return

    if which("dpkg"):
        res = run_capture(["dpkg", "-l"])
        if res.returncode == 0 and app_name in res.stdout:
            typer.echo(f"Removing {app_name} .deb package...")
            run_cmd(["sudo", "dpkg", "-r", app_name], check=False)
    if which("rpm"):
        res = run_capture(["rpm", "-q", app_name])
        if res.returncode == 0:
            typer.echo(f"Removing {app_name} .rpm package...")
            run_cmd(["sudo", "rpm", "-e", app_name], check=False)

    app_variants = ["throne", "Throne"] if app_name == "throne" else ["nekoray", "NekoRay"]

    for variant in app_variants:
        locations = [
            f"/opt/{variant}",
            f"/usr/share/applications/{variant}.desktop",
            os.path.join(
                os.path.expanduser("~"),
                ".local/share/applications",
                f"{variant}.desktop",
            ),
            os.path.join(os.path.expanduser("~"), ".config", variant),
        ]
        for location in locations:
            if os.path.isdir(location) or os.path.isfile(location):
                run_cmd(["sudo", "rm", "-rf", location], check=False)

    typer.echo(color(f"\n✅ {app_name} installations have been removed.", GREEN))
    typer.echo()


def ensure_linux_command(cmd, hint=None) -> bool:
    if which(cmd):
        return True
    typer.echo(color(f"❌ '{cmd}' command not found. Please install it.", RED))
    if hint:
        typer.echo(hint)
    return False


def detect_wifi_iface():
    res = run_capture(["nmcli", "device", "status"])
    if res.returncode != 0:
        return ""
    for line in res.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "wifi":
            return parts[0]
    return ""


def find_linux_wifi_iface(requested_iface):
    if not requested_iface:
        return detect_wifi_iface()
    res = run_capture(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"])
    if res.returncode != 0:
        return ""
    for line in res.stdout.splitlines():
        if ":" not in line:
            continue
        device, dev_type = line.split(":", 1)
        if device == requested_iface and dev_type == "wifi":
            return device
    return ""


def enable_hotspot_linux(dry_run=None, iface=None, ssid=None, password=None) -> None:
    typer.echo(color("=== ENABLE HOTSPOT ===", BLUE))
    typer.echo()
    typer.echo(color("🚀 Starting Throne Hotspot...", GREEN))
    if dry_run is None:
        dry_choice = input("Run in dry-run mode? (y/N): ").strip().lower()
        dry_run = dry_choice == "y"
    if dry_run:
        typer.echo(color("🧪 Running in dry-run mode — no changes will be made.", YELLOW))

    if not ensure_linux_command(
        "nmcli",
        "   Debian/Ubuntu: sudo apt install network-manager\n   Fedora:        sudo dnf install NetworkManager\n   Arch:          sudo pacman -S networkmanager",
    ):
        sys_exit(1)
    if not ensure_linux_command(
        "iw",
        "   Debian/Ubuntu: sudo apt install iw\n   Fedora:        sudo dnf install iw\n   Arch:          sudo pacman -S iw",
    ):
        sys_exit(1)
    if not ensure_linux_command(
        "nft",
        "   Debian/Ubuntu: sudo apt install nftables\n   Fedora:        sudo dnf install nftables\n   Arch:          sudo pacman -S nftables",
    ):
        sys_exit(1)

    hotspot_iface = find_linux_wifi_iface(iface)
    if not hotspot_iface:
        if iface:
            typer.echo(color(f"❌ Wi-Fi interface not found: {iface}", RED))
        else:
            typer.echo(color("❌ No Wi-Fi interface found. Exiting.", RED))
        sys_exit(1)
    typer.echo(color(f"✅ Wi-Fi interface: {BOLD}{hotspot_iface}{NC}", GREEN))

    res = run_capture(["sudo", "nft", "list", "table", "inet", LINUX_REQUIRED_INET_TABLE])
    if res.returncode != 0:
        typer.echo(color(f"❌ Missing 'inet {LINUX_REQUIRED_INET_TABLE}' nftables table.", RED))
        typer.echo("   Please enable 'Tun Mode' in Throne/NekoRay GUI settings.")
        sys_exit(1)

    typer.echo(color("✅ Enabling Wi-Fi...", GREEN))
    run_cmd(["nmcli", "radio", "wifi", "on"], dry_run=dry_run, check=False)

    res = run_capture(["iw", "dev", hotspot_iface, "info"])
    if res.returncode == 0 and "type AP" in res.stdout:
        typer.echo(
            color(
                f"⚠ A Wi-Fi hotspot is already active on {hotspot_iface}. Skipping creation.",
                YELLOW,
            ),
        )
        return

    typer.echo(color("✅ Starting hotspot...", GREEN))
    if not password:
        while True:
            password = getpass("\n🔒 Enter hotspot password (min 8 chars): ")
            if len(password) >= 8:
                break
            typer.echo(color("❌ Password must be at least 8 characters.", RED))
    if len(password) < 8:
        typer.echo(color("❌ Password must be at least 8 characters.", RED))
        sys_exit(1)

    ssid = ssid or LINUX_SSID

    if dry_run:
        typer.echo(
            color(
                f'→ nmcli dev wifi hotspot ifname "{hotspot_iface}" ssid "{ssid}" password "********"',
                BLUE,
            ),
        )
    else:
        res = run_capture(
            [
                "nmcli",
                "dev",
                "wifi",
                "hotspot",
                "ifname",
                hotspot_iface,
                "ssid",
                ssid,
                "password",
                password,
            ],
        )
        if res.returncode != 0:
            typer.echo(color("❌ Failed to start hotspot — maybe AP mode is unsupported.", RED))
            sys_exit(1)

    typer.echo(color("✅ Setting up nftables rules...", GREEN))

    table = quote(LINUX_NFT_TABLE)
    tun_iface = quote(LINUX_TUN_IFACE)
    hs_iface = quote(hotspot_iface)

    run_cmd(
        f"sudo nft delete table ip {table} 2>/dev/null || true",
        dry_run=dry_run,
        shell=True,
        check=False,
    )
    run_cmd(f"sudo nft add table ip {table}", dry_run=dry_run, shell=True, check=False)
    run_cmd(
        f"sudo nft add chain ip {table} postrouting {{ type nat hook postrouting priority srcnat; policy accept; }}",
        dry_run=dry_run,
        shell=True,
        check=False,
    )
    run_cmd(
        f'sudo nft add rule ip {table} postrouting oifname "{tun_iface}" masquerade',
        dry_run=dry_run,
        shell=True,
        check=False,
    )
    run_cmd(
        f"sudo nft add chain ip {table} forward {{ type filter hook forward priority filter; policy accept; }}",
        dry_run=dry_run,
        shell=True,
        check=False,
    )
    run_cmd(
        f'sudo nft add rule ip {table} forward iifname "{hs_iface}" oifname "{tun_iface}" accept',
        dry_run=dry_run,
        shell=True,
        check=False,
    )
    run_cmd(
        f'sudo nft add rule ip {table} forward iifname "{tun_iface}" oifname "{hs_iface}" ct state established,related accept',
        dry_run=dry_run,
        shell=True,
        check=False,
    )

    typer.echo()
    typer.echo(color("✔ Hotspot is ready and running!", GREEN + BOLD))
    typer.echo(f"SSID: {ssid}")
    typer.echo(f"Password: {password}")
    typer.echo()


def disable_hotspot_linux(dry_run=None) -> None:
    typer.echo(color("=== DISABLE HOTSPOT ===", BLUE))
    typer.echo()
    if dry_run is None:
        dry_choice = input("Run in dry-run mode? (y/N): ").strip().lower()
        dry_run = dry_choice == "y"
    if dry_run:
        typer.echo(color("🧪 Running in dry-run mode — no changes will be made.", YELLOW))

    typer.echo(color("✅ Stopping hotspot...", GREEN))
    run_cmd(["nmcli", "connection", "down", "Hotspot"], dry_run=dry_run, check=False)
    run_cmd(["nmcli", "connection", "delete", "Hotspot"], dry_run=dry_run, check=False)

    typer.echo(color("✅ Removing nftables table...", GREEN))
    run_cmd(
        f"sudo nft delete table ip {quote(LINUX_NFT_TABLE)} 2>/dev/null || true",
        dry_run=dry_run,
        shell=True,
        check=False,
    )

    typer.echo()
    typer.echo(color("✔ Hotspot stopped and nftables rules removed.", GREEN + BOLD))
    typer.echo()


def detect_macos_wifi_iface():
    res = run_capture(["networksetup", "-listallhardwareports"])
    if res.returncode != 0:
        return ""
    lines = res.stdout.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("Hardware Port:"):
            port = line.split(":", 1)[1].strip().lower()
            if port in {"wi-fi", "airport"}:
                for next_line in lines[idx + 1 : idx + 3]:
                    if next_line.startswith("Device:"):
                        return next_line.split(":", 1)[1].strip()
    return ""


def enable_hotspot_macos(dry_run=None, iface=None, ssid=None, password=None) -> None:
    typer.echo(color("=== ENABLE HOTSPOT ===", BLUE))
    typer.echo()
    typer.echo(color("🚀 Starting Throne Hotspot (best-effort on macOS)...", GREEN))

    if dry_run is None:
        dry_choice = input("Run in dry-run mode? (y/N): ").strip().lower()
        dry_run = dry_choice == "y"
    if dry_run:
        typer.echo(color("🧪 Running in dry-run mode — no changes will be made.", YELLOW))

    if not which("networksetup"):
        typer.echo(color("❌ 'networksetup' not found. macOS hotspot is unavailable.", RED))
        sys_exit(1)

    airport_tool = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
    if not os.path.exists(airport_tool):
        typer.echo(color("❌ 'airport' tool not found. macOS hotspot is unavailable.", RED))
        sys_exit(1)

    if not iface:
        iface = detect_macos_wifi_iface()
    if not iface:
        typer.echo(color("❌ Wi-Fi interface not found on macOS.", RED))
        sys_exit(1)

    ssid = ssid or LINUX_SSID

    if not password:
        while True:
            password = getpass("\n🔒 Enter hotspot password (min 8 chars): ")
            if len(password) >= 8:
                break
            typer.echo(color("❌ Password must be at least 8 characters.", RED))
    if len(password) < 8:
        typer.echo(color("❌ Password must be at least 8 characters.", RED))
        sys_exit(1)

    typer.echo(color("✅ Enabling Wi-Fi...", GREEN))
    run_cmd(["networksetup", "-setairportpower", iface, "on"], dry_run=dry_run, check=False)

    typer.echo(color("✅ Attempting to create hotspot...", GREEN))
    create_cmd = [airport_tool, "--create", ssid, password]
    if dry_run:
        run_cmd(create_cmd, dry_run=True, check=False)
        res = CompletedProcess(create_cmd, 0)
    else:
        res = run_capture(create_cmd)
    if res.returncode != 0:
        typer.echo(color("⚠ Failed to create hotspot via 'airport'.", YELLOW))
        typer.echo("   macOS hotspot setup can require manual configuration.")

    sharing_plist = "/System/Library/LaunchDaemons/com.apple.InternetSharing.plist"
    if os.path.exists(sharing_plist):
        typer.echo(color("✅ Attempting to enable Internet Sharing...", GREEN))
        run_cmd(
            ["sudo", "launchctl", "load", "-w", sharing_plist],
            dry_run=dry_run,
            check=False,
        )
    else:
        typer.echo(color("⚠ Internet Sharing plist not found.", YELLOW))

    typer.echo()
    typer.echo(color("✔ Hotspot command completed (best-effort).", GREEN + BOLD))
    typer.echo(f"SSID: {ssid}")
    typer.echo(f"Password: {password}")
    typer.echo("Verify in System Settings → General → Sharing → Internet Sharing.")
    typer.echo()


def disable_hotspot_macos(dry_run=None) -> None:
    typer.echo(color("=== DISABLE HOTSPOT ===", BLUE))
    typer.echo()
    if dry_run is None:
        dry_choice = input("Run in dry-run mode? (y/N): ").strip().lower()
        dry_run = dry_choice == "y"
    if dry_run:
        typer.echo(color("🧪 Running in dry-run mode — no changes will be made.", YELLOW))

    sharing_plist = "/System/Library/LaunchDaemons/com.apple.InternetSharing.plist"
    if os.path.exists(sharing_plist):
        typer.echo(color("✅ Attempting to disable Internet Sharing...", GREEN))
        run_cmd(
            ["sudo", "launchctl", "unload", "-w", sharing_plist],
            dry_run=dry_run,
            check=False,
        )
    else:
        typer.echo(color("⚠ Internet Sharing plist not found.", YELLOW))

    typer.echo()
    typer.echo(color("✔ Hotspot stop command completed (best-effort).", GREEN + BOLD))
    typer.echo()


def install_app_macos() -> None:
    typer.echo(color("=== INSTALLATION ===", BLUE))
    typer.echo()

    app_path = f"/Applications/{THRONE_APP_NAME}.app"
    if os.path.isdir(app_path):
        typer.echo(color(f"{THRONE_APP_NAME} is already installed at {app_path}.", YELLOW))
        typer.echo(color("Please back it up and delete it if you want to reinstall.", YELLOW))
        typer.echo()
        return

    typer.echo(f"Fetching latest {THRONE_APP_NAME} release...")
    release = github_latest_release()
    assets = release.get("assets", [])

    arch = machine()
    pattern = compile(rf"{escape(THRONE_APP_NAME)}.*macos-{escape(arch)}\.zip")
    target_asset = None
    for asset in assets:
        name = asset.get("name", "")
        if pattern.search(name):
            target_asset = asset
            break

    if not target_asset:
        typer.echo(color(f"Failed to find download URL for macOS {arch}.", RED))
        sys_exit(1)

    download_url = target_asset.get("browser_download_url")
    typer.echo(f"Downloading from: {download_url}")

    with TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, f"{THRONE_APP_NAME}.zip")
        download_file(download_url, zip_path)
        typer.echo("Installing...")
        with ZipFile(zip_path, "r") as handle:
            handle.extractall(tmpdir)

        app_src = os.path.join(tmpdir, THRONE_APP_NAME, f"{THRONE_APP_NAME}.app")
        if not os.path.isdir(app_src):
            typer.echo(color("Extracted app not found in archive.", RED))
            sys_exit(1)

        try:
            move(app_src, "/Applications/")
        except PermissionError:
            typer.echo(
                color(
                    "Permission denied while moving app to /Applications. Run this script with sudo.",
                    RED,
                ),
            )
            sys_exit(1)

    typer.echo()
    typer.echo(color(f"✅ Done! {THRONE_APP_NAME} has been installed to /Applications.", GREEN))
    typer.echo(
        color(
            f"You can now launch '{THRONE_APP_NAME}' from Spotlight or Launchpad.",
            GREEN,
        ),
    )
    typer.echo()


def find_windows_installer_asset(assets):
    pattern = compile(r"windows.*installer\.exe$", IGNORECASE)
    for asset in assets:
        name = asset.get("name", "")
        if pattern.search(name):
            return asset
    return None


def install_app_windows() -> None:
    typer.echo(color("=== INSTALLATION ===", BLUE))
    typer.echo()
    typer.echo("Fetching latest Throne release...")

    release = github_latest_release()
    assets = release.get("assets", [])
    target_asset = find_windows_installer_asset(assets)

    if not target_asset:
        typer.echo(color("No Windows installer found in the latest release.", RED))
        sys_exit(1)

    installer_url = target_asset.get("browser_download_url")
    installer_name = target_asset.get("name")
    temp_dir = gettempdir()
    installer_path = os.path.join(temp_dir, "throne_installer.exe")

    typer.echo(f"Found installer: {installer_name}")
    typer.echo("Downloading Throne installer...")
    download_file(installer_url, installer_path)

    if os.path.isfile(installer_path):
        typer.echo(f"Download completed: {installer_path}")
        typer.echo("Launching installer...")
        try:
            Popen([installer_path], shell=False)
        except OSError as exc:
            typer.echo(color(f"Failed to launch installer: {exc}", RED))
            sys_exit(1)
        typer.echo("Installer launched. Exiting.")
    else:
        typer.echo(color("Download failed.", RED))
        sys_exit(1)


def windows_config_base(app_name):
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return ""
    if app_name == "throne":
        return os.path.join(appdata, "Throne")
    return os.path.join(appdata, "nekoray")


def backup_config_windows(app_name=None, output_path=None):
    typer.echo(color("=== BACKUP CONFIGURATION ===", BLUE))
    typer.echo()
    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")

    base_dir = windows_config_base(app_name)
    config_dir = os.path.join(base_dir, "config") if base_dir else ""
    if not config_dir or not os.path.isdir(config_dir):
        typer.echo(color(f"Config directory does not exist: {config_dir}", RED))
        sys_exit(1)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    backup_name = f"{app_name}-backup-{date_str}.zip"
    if output_path:
        dest_path = os.path.join(output_path, backup_name) if os.path.isdir(output_path) else output_path
    else:
        dest_path = os.path.join(os.getcwd(), backup_name)

    typer.echo("📦 Compressing config ...")
    typer.echo(f"Compressing config from {config_dir}...")
    zip_dir(config_dir, dest_path)

    typer.echo(color("✅ Backup created:", GREEN))
    typer.echo(color(dest_path, GREEN))
    typer.echo()
    return dest_path


def restore_config_windows(app_name=None, zip_file=None) -> None:
    typer.echo(color("=== RESTORE CONFIGURATION ===", BLUE))
    typer.echo()
    if not zip_file:
        zip_file = input("Enter the path to the backup .zip file: ").strip()
    if not zip_file:
        typer.echo(color("Please provide the path to the backup .zip file.", RED))
        sys_exit(1)
    if not os.path.isfile(zip_file):
        typer.echo(color(f"File not found: {zip_file}", RED))
        sys_exit(1)

    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")

    base_dir = windows_config_base(app_name)
    if not base_dir:
        typer.echo(color("APPDATA is not available on this system.", RED))
        sys_exit(1)

    restore_dir = os.path.join(base_dir, "config")
    if os.path.isdir(restore_dir):
        typer.echo(f"Removing existing config: {restore_dir}")
        rmtree(restore_dir)
    os.makedirs(restore_dir, exist_ok=True)

    typer.echo(f"📦 Restoring backup to: {restore_dir}")
    with ZipFile(zip_file, "r") as handle:
        handle.extractall(restore_dir)

    typer.echo(color("✅ Restore complete!", GREEN))
    typer.echo()


def uninstall_app_windows(app_name=None, skip_check=False) -> None:
    typer.echo(color("=== UNINSTALL ===", BLUE))
    typer.echo()
    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")

    typer.echo(f"\nUninstalling {app_name}...")
    base_dir = windows_config_base(app_name)
    config_dir = os.path.join(base_dir, "config") if base_dir else ""
    if config_dir and os.path.isdir(config_dir):
        typer.echo(f"Removing config: {config_dir}")
        rmtree(config_dir)

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")

    uninstallers = []
    if app_name == "throne":
        uninstallers = [
            os.path.join(local_appdata, "Programs", "Throne", "Uninstall Throne.exe"),
            os.path.join(program_files, "Throne", "Uninstall Throne.exe"),
            os.path.join(program_files_x86, "Throne", "Uninstall Throne.exe"),
        ]
    else:
        uninstallers = [
            os.path.join(local_appdata, "Programs", "NekoRay", "Uninstall NekoRay.exe"),
            os.path.join(program_files, "NekoRay", "Uninstall NekoRay.exe"),
            os.path.join(program_files_x86, "NekoRay", "Uninstall NekoRay.exe"),
        ]

    uninstallers = [path for path in uninstallers if path and os.path.isfile(path)]
    if uninstallers:
        typer.echo(f"Launching uninstaller: {uninstallers[0]}")
        try:
            Popen([uninstallers[0]], shell=False)
        except OSError as exc:
            typer.echo(color(f"Failed to launch uninstaller: {exc}", RED))
            typer.echo("Please uninstall using Windows Apps & Features.")
    else:
        typer.echo(color("Uninstaller not found.", YELLOW))
        typer.echo("Please uninstall using Windows Apps & Features.")

    typer.echo(color(f"\n✅ {app_name} uninstall steps completed.", GREEN))
    typer.echo()


def reinstall_linux(app_name, backup=False, output_path=None, force=False) -> None:
    if app_name == "nekoray":
        typer.echo(
            color(
                "⚠ Installer only supports Throne packages; reinstall will install Throne.",
                YELLOW,
            ),
        )
    backup_path = None
    if backup:
        backup_path = backup_config_linux(app_name=app_name, output_path=output_path)
    uninstall_app_linux(app_name=app_name, skip_check=force)
    install_app_linux()
    if backup_path:
        restore_config_linux(app_name=app_name, zip_file=backup_path)


def reinstall_macos(app_name, backup=False, output_path=None, force=False) -> None:
    if app_name == "nekoray":
        typer.echo(
            color(
                "⚠ Installer only supports Throne packages; reinstall will install Throne.",
                YELLOW,
            ),
        )
    backup_path = None
    if backup:
        backup_path = backup_config_macos(app_name=app_name, output_path=output_path)
    uninstall_app_macos(app_name=app_name, skip_check=force)
    install_app_macos()
    if backup_path:
        restore_config_macos(app_name=app_name, zip_file=backup_path)


def reinstall_windows(app_name, backup=False, output_path=None, force=False) -> None:
    if app_name == "nekoray":
        typer.echo(
            color(
                "⚠ Installer only supports Throne packages; reinstall will install Throne.",
                YELLOW,
            ),
        )
    backup_path = None
    if backup:
        backup_path = backup_config_windows(app_name=app_name, output_path=output_path)
    uninstall_app_windows(app_name=app_name, skip_check=force)
    install_app_windows()
    if backup_path:
        restore_config_windows(app_name=app_name, zip_file=backup_path)


def linux_package_version(app_name):
    if which("dpkg"):
        res = run_capture(["dpkg", "-s", app_name])
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
    if which("rpm"):
        res = run_capture(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", app_name])
        if res.returncode == 0:
            return res.stdout.strip()
    return ""


def linux_install_paths(app_name):
    variants = ["Throne", "throne"] if app_name == "throne" else ["NekoRay", "nekoray"]
    paths = []
    for variant in variants:
        paths.extend(
            [
                f"/opt/{variant}",
                f"/usr/share/applications/{variant}.desktop",
                os.path.join(
                    os.path.expanduser("~"),
                    ".local/share/applications",
                    f"{variant}.desktop",
                ),
            ],
        )
    return [path for path in paths if os.path.exists(path)]


def info_linux(app_name) -> None:
    typer.echo(color("=== INFO ===", BLUE))
    typer.echo()
    version = linux_package_version(app_name) or "unknown"
    paths = linux_install_paths(app_name)
    install_path = paths[0] if paths else "not found"
    typer.echo(f"App: {app_name}")
    typer.echo(f"Version: {version}")
    typer.echo(f"Install path: {install_path}")
    typer.echo()


def macos_app_bundle(app_name):
    candidates = ["Throne.app"] if app_name == "throne" else ["NekoRay.app", "nekoray.app"]
    for name in candidates:
        path = os.path.join("/Applications", name)
        if os.path.isdir(path):
            return path
    return ""


def macos_app_version(app_bundle):
    info_plist = os.path.join(app_bundle, "Contents", "Info.plist")
    if not os.path.isfile(info_plist):
        return ""
    try:
        with open(info_plist, "rb") as handle:
            data = plistlib_load(handle)
    except (OSError, InvalidFileException):
        return ""
    return data.get("CFBundleShortVersionString") or data.get("CFBundleVersion") or ""


def info_macos(app_name) -> None:
    typer.echo(color("=== INFO ===", BLUE))
    typer.echo()
    app_bundle = macos_app_bundle(app_name)
    version = macos_app_version(app_bundle) if app_bundle else ""
    typer.echo(f"App: {app_name}")
    typer.echo(f"Version: {version or 'unknown'}")
    typer.echo(f"Install path: {app_bundle or 'not found'}")
    typer.echo()


def windows_exe_candidates(app_name):
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    exe_name = "Throne.exe" if app_name == "throne" else "NekoRay.exe"
    app_dir = "Throne" if app_name == "throne" else "NekoRay"
    return [
        os.path.join(local_appdata, "Programs", app_dir, exe_name),
        os.path.join(program_files, app_dir, exe_name),
        os.path.join(program_files_x86, app_dir, exe_name),
    ]


def windows_exe_version(exe_path):
    if not exe_path:
        return ""
    escaped = exe_path.replace("'", "''")
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-Item '{escaped}').VersionInfo.ProductVersion",
    ]
    res = run_capture(cmd)
    if res.returncode == 0:
        return res.stdout.strip()
    return ""


def info_windows(app_name) -> None:
    typer.echo(color("=== INFO ===", BLUE))
    typer.echo()
    candidates = windows_exe_candidates(app_name)
    exe_path = next((path for path in candidates if os.path.isfile(path)), "")
    version = windows_exe_version(exe_path) if exe_path else ""
    typer.echo(f"App: {app_name}")
    typer.echo(f"Version: {version or 'unknown'}")
    typer.echo(f"Install path: {exe_path or 'not found'}")
    typer.echo()


def backup_config_macos(app_name=None, output_path=None):
    typer.echo(color("=== BACKUP CONFIGURATION ===", BLUE))
    typer.echo()
    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (Throne or oldest nekoray): ")

    config_dir = os.path.join(os.path.expanduser("~"), "Library/Preferences", app_name, "config")
    if not os.path.isdir(config_dir):
        typer.echo(color(f"Config directory does not exist: {config_dir}", RED))
        sys_exit(1)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    backup_name = f"{app_name}-backup-{date_str}.zip"
    if output_path:
        dest_path = os.path.join(output_path, backup_name) if os.path.isdir(output_path) else output_path
    else:
        dest_path = os.path.join(os.getcwd(), backup_name)

    typer.echo("📦 Compressing config ...")
    typer.echo(f"Compressing config from {config_dir}...")
    zip_dir(config_dir, dest_path)

    typer.echo(color("✅ Backup created:", GREEN))
    typer.echo(color(dest_path, GREEN))
    typer.echo()
    return dest_path


def restore_config_macos(app_name=None, zip_file=None) -> None:
    typer.echo(color("=== RESTORE CONFIGURATION ===", BLUE))
    typer.echo()
    if not zip_file:
        zip_file = input("Enter the path to the backup .zip file: ").strip()
    if not zip_file:
        typer.echo(color("Please provide the path to the backup .zip file.", RED))
        sys_exit(1)
    if not os.path.isfile(zip_file):
        typer.echo(color(f"File not found: {zip_file}", RED))
        sys_exit(1)

    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (Throne or oldest nekoray): ")
    base = os.path.join(os.path.expanduser("~"), "Library/Preferences", app_name)
    restore_dir = os.path.join(base, "config")

    if not os.path.isdir(base):
        os.makedirs(base, exist_ok=True)

    if os.path.isdir(restore_dir):
        typer.echo(f"Removing existing config: {restore_dir}")
        rmtree(restore_dir)
    os.makedirs(restore_dir, exist_ok=True)

    typer.echo(f"📦 Restoring backup to: {restore_dir}")
    with ZipFile(zip_file, "r") as handle:
        handle.extractall(restore_dir)

    typer.echo(color("✅ Restore complete!", GREEN))
    typer.echo()


def uninstall_app_macos(app_name=None, skip_check=False) -> None:
    typer.echo(color("=== UNINSTALL ===", BLUE))
    typer.echo()
    if not app_name:
        app_name = prompt_app_name("👉 Enter which app (Throne or oldest nekoray): ")
    prefs_dir = os.path.join(os.path.expanduser("~"), "Library/Preferences", app_name)
    app_bundle = f"/Applications/{app_name}.app"

    typer.echo(f"\nUninstalling {app_name}...")
    if os.path.isdir(prefs_dir):
        typer.echo(f"Removing preferences: {prefs_dir}")
        run_cmd(["sudo", "rm", "-rvf", prefs_dir], check=False)
    else:
        typer.echo(f"No preferences folder found at: {prefs_dir}")

    if os.path.isdir(app_bundle):
        typer.echo(f"Removing app bundle: {app_bundle}")
        run_cmd(["sudo", "rm", "-rvf", app_bundle], check=False)
    else:
        typer.echo(f"No app found at: {app_bundle}")

    typer.echo(color(f"\n✅ {app_name} has been successfully uninstalled.", GREEN))
    typer.echo()


def main_linux() -> None:
    show_banner("Linux")
    while True:
        show_menu_linux()
        choice = input("Enter your choice (1-9): ").strip()
        typer.echo()
        if choice == "1":
            install_app_linux()
        elif choice == "2":
            backup_config_linux()
        elif choice == "3":
            restore_config_linux()
        elif choice == "4":
            uninstall_app_linux()
        elif choice == "5":
            enable_hotspot_linux()
        elif choice == "6":
            disable_hotspot_linux()
        elif choice == "7":
            app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")
            reinstall_linux(app_name=app_name, backup=False, output_path=None, force=False)
        elif choice == "8":
            app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")
            info_linux(app_name)
        elif choice == "9":
            typer.echo(color("Goodbye!", GREEN))
            sys_exit(0)
        else:
            typer.echo(color("Invalid choice. Please select 1-9.", RED))
            typer.echo()

        input("Press Enter to continue...")
        typer.echo()


def main_macos() -> None:
    show_banner("macOS")
    while True:
        show_menu_macos()
        choice = input("Enter your choice (1-7): ").strip()
        typer.echo()
        if choice == "1":
            install_app_macos()
        elif choice == "2":
            backup_config_macos()
        elif choice == "3":
            restore_config_macos()
        elif choice == "4":
            uninstall_app_macos()
        elif choice == "5":
            app_name = prompt_app_name("👉 Enter which app (Throne or oldest nekoray): ")
            reinstall_macos(app_name=app_name, backup=False, output_path=None, force=False)
        elif choice == "6":
            app_name = prompt_app_name("👉 Enter which app (Throne or oldest nekoray): ")
            info_macos(app_name)
        elif choice == "7":
            typer.echo(color("Goodbye!", GREEN))
            sys_exit(0)
        else:
            typer.echo(color("Invalid choice. Please select 1-7.", RED))
            typer.echo()

        input("Press Enter to continue...")
        typer.echo()


def main_windows() -> None:
    show_banner("Windows")
    while True:
        show_menu_windows()
        choice = input("Enter your choice (1-7): ").strip()
        typer.echo()
        if choice == "1":
            install_app_windows()
        elif choice == "2":
            backup_config_windows()
        elif choice == "3":
            restore_config_windows()
        elif choice == "4":
            uninstall_app_windows()
        elif choice == "5":
            app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")
            reinstall_windows(app_name=app_name, backup=False, output_path=None, force=False)
        elif choice == "6":
            app_name = prompt_app_name("👉 Enter which app (nekoray, throne): ")
            info_windows(app_name)
        elif choice == "7":
            typer.echo(color("Goodbye!", GREEN))
            sys_exit(0)
        else:
            typer.echo(color("Invalid choice. Please select 1-7.", RED))
            typer.echo()

        input("Press Enter to continue...")
        typer.echo()


def main() -> None:
    parser = ArgumentParser(
        prog="throne-tool",
        description="Throne installer and management tool (Linux/macOS/Windows).",
        formatter_class=RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  throne-tool install\n"
            "  throne-tool backup --app throne --output /path/to/dir\n"
            "  throne-tool restore --app throne --zip /path/to/backup.zip\n"
            "  throne-tool remove --app throne\n"
            "  throne-tool reinstall --app throne --backup --force\n"
            "  throne-tool info --app throne\n"
            "  throne-tool hotspot enable --iface wlp2s0 --dry-run\n"
            "\n"
            "Run without subcommands for interactive mode:\n"
            "  python3 throne.py\n"
            "  python3 -m thronetool\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("install", help="Install Throne")

    backup_parser = subparsers.add_parser("backup", help="Backup configuration")
    backup_parser.add_argument("--app", choices=["throne", "nekoray"], required=True)
    backup_parser.add_argument("--output", help="Output .zip file path or destination directory")

    restore_parser = subparsers.add_parser("restore", help="Restore configuration")
    restore_parser.add_argument("--app", choices=["throne", "nekoray"], required=True)
    restore_parser.add_argument("--zip", dest="zip_file", required=True, help="Path to backup .zip file")

    remove_parser = subparsers.add_parser("remove", help="Uninstall Throne/NekoRay")
    remove_parser.add_argument("--app", choices=["throne", "nekoray"], required=True)

    reinstall_parser = subparsers.add_parser("reinstall", help="Reinstall Throne")
    reinstall_parser.add_argument("--app", choices=["throne", "nekoray"], required=True)
    reinstall_parser.add_argument(
        "--backup",
        action="store_true",
        help="Backup config before reinstall and restore after install",
    )
    reinstall_parser.add_argument("--output", help="Backup .zip file path or destination directory")
    reinstall_parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even if installation is not detected",
    )

    info_parser = subparsers.add_parser("info", help="Show installed version and path")
    info_parser.add_argument("--app", choices=["throne", "nekoray"], required=True)

    hotspot_parser = subparsers.add_parser("hotspot", help="Hotspot controls")
    hotspot_sub = hotspot_parser.add_subparsers(dest="hotspot_command")
    hotspot_enable = hotspot_sub.add_parser("enable", help="Enable hotspot")
    hotspot_enable.add_argument("--dry-run", action="store_true")
    hotspot_enable.add_argument("--iface", help="Wi-Fi interface to use")
    hotspot_enable.add_argument("--ssid", help="Hotspot SSID (optional)")
    hotspot_enable.add_argument("--password", help="Hotspot password (min 8 chars)")
    hotspot_disable = hotspot_sub.add_parser("disable", help="Disable hotspot")
    hotspot_disable.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if not args.command:
        if sys_platform.startswith("linux"):
            main_linux()
        elif sys_platform == "darwin":
            main_macos()
        elif sys_platform.startswith("win"):
            main_windows()
        else:
            typer.echo(
                color(
                    "Unsupported platform. This script supports Linux, macOS, and Windows only.",
                    RED,
                ),
            )
            sys_exit(1)
        return

    if sys_platform.startswith("linux"):
        if args.command == "install":
            install_app_linux()
        elif args.command == "backup":
            backup_config_linux(app_name=args.app, output_path=args.output)
        elif args.command == "restore":
            restore_config_linux(app_name=args.app, zip_file=args.zip_file)
        elif args.command == "remove":
            uninstall_app_linux(app_name=args.app)
        elif args.command == "reinstall":
            reinstall_linux(
                app_name=args.app,
                backup=args.backup,
                output_path=args.output,
                force=args.force,
            )
        elif args.command == "info":
            info_linux(args.app)
        elif args.command == "hotspot":
            if args.hotspot_command == "enable":
                enable_hotspot_linux(
                    dry_run=args.dry_run,
                    iface=args.iface,
                    ssid=args.ssid,
                    password=args.password,
                )
            elif args.hotspot_command == "disable":
                disable_hotspot_linux(dry_run=args.dry_run)
            else:
                hotspot_parser.print_help()
        else:
            parser.print_help()
    elif sys_platform == "darwin":
        if args.command == "install":
            install_app_macos()
        elif args.command == "backup":
            backup_config_macos(app_name=args.app, output_path=args.output)
        elif args.command == "restore":
            restore_config_macos(app_name=args.app, zip_file=args.zip_file)
        elif args.command == "remove":
            uninstall_app_macos(app_name=args.app)
        elif args.command == "reinstall":
            reinstall_macos(
                app_name=args.app,
                backup=args.backup,
                output_path=args.output,
                force=args.force,
            )
        elif args.command == "info":
            info_macos(args.app)
        elif args.command == "hotspot":
            if args.hotspot_command == "enable":
                enable_hotspot_macos(
                    dry_run=args.dry_run,
                    iface=args.iface,
                    ssid=args.ssid,
                    password=args.password,
                )
            elif args.hotspot_command == "disable":
                disable_hotspot_macos(dry_run=args.dry_run)
            else:
                hotspot_parser.print_help()
        else:
            parser.print_help()
    elif sys_platform.startswith("win"):
        if args.command == "install":
            install_app_windows()
        elif args.command == "backup":
            backup_config_windows(app_name=args.app, output_path=args.output)
        elif args.command == "restore":
            restore_config_windows(app_name=args.app, zip_file=args.zip_file)
        elif args.command == "remove":
            uninstall_app_windows(app_name=args.app)
        elif args.command == "reinstall":
            reinstall_windows(
                app_name=args.app,
                backup=args.backup,
                output_path=args.output,
                force=args.force,
            )
        elif args.command == "info":
            info_windows(args.app)
        elif args.command == "hotspot":
            typer.echo(color("Hotspot commands are supported on Linux/macOS only.", RED))
            sys_exit(1)
        else:
            parser.print_help()
    else:
        typer.echo(
            color(
                "Unsupported platform. This script supports Linux, macOS, and Windows only.",
                RED,
            ),
        )
        sys_exit(1)


if __name__ == "__main__":
    main()
