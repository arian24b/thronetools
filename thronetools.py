import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import new as hash_new
from importlib.metadata import version as pkg_version
from json import loads
from platform import machine
from plistlib import InvalidFileException
from plistlib import load as plistlib_load
from re import IGNORECASE, escape
from re import compile as re_compile
from shutil import move, rmtree, which
from subprocess import PIPE, Popen
from subprocess import run as subprocess_run
from sys import platform as sys_platform
from tempfile import TemporaryDirectory, gettempdir
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

import typer
import typer.core
from rich import box
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

THRONE_URL = "https://api.github.com/repos/throneproj/Throne/releases/latest"
THRONE_APP_NAME = "Throne"
DEFAULT_SSID = "thronetools"
LINUX_TUN_IFACE = "throne-tun"
LINUX_NFT_TABLE = "throne_hotspot"
LINUX_REQUIRED_INET_TABLE = "sing-box"
HTTP_TIMEOUT = 15
MIN_PASSWORD_LENGTH = 8

GEOIP_URL = "https://github.com/sagernet/sing-geoip/releases/latest/download/geoip.db"
GEOIP_SHA_URL = "https://github.com/sagernet/sing-geoip/releases/latest/download/geoip.db.sha256sum"
GEOSITE_URL = "https://github.com/sagernet/sing-geosite/releases/latest/download/geosite.db"
GEOSITE_SHA_URL = "https://github.com/sagernet/sing-geosite/releases/latest/download/geosite.db.sha256sum"
GEO_FILE_TYPES = {"geoip", "geosite"}
PROMPT_APP_TEXT = "Enter which app (throne, nekoray): "


BANNER = r"""
████████╗██╗  ██╗██████╗  ██████╗ ███╗   ██╗███████╗
╚══██╔══╝██║  ██║██╔══██╗██╔═══██╗████╗  ██║██╔════╝
   ██║   ███████║██████╔╝██║   ██║██╔██╗ ██║█████╗
   ██║   ██╔══██║██╔══██╗██║   ██║██║╚██╗██║██╔══╝
   ██║   ██║  ██║██║  ██║╚██████╔╝██║ ╚████║███████╗
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝
    ████████╗ ██████╗  ██████╗ ██╗     ███████╗
    ╚══██╔══╝██╔═══██╗██╔═══██╗██║     ██╔════╝
       ██║   ██║   ██║██║   ██║██║     ███████╗
       ██║   ██║   ██║██║   ██║██║     ╚════██║
       ██║   ╚██████╔╝╚██████╔╝███████╗███████║
       ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚══════╝
"""


@dataclass
class CMDOutput:
    output_text: str
    error_text: str
    return_code: int

    def __str__(self) -> str:
        return f"Output Text: {self.output_text}\nError Text: {self.error_text}\nReturn Code: {self.return_code}"


def run_command(command: list[str]) -> CMDOutput:
    process = Popen(  # noqa: S603
        command,
        stdout=PIPE,
        stderr=PIPE,
        stdin=PIPE,
        text=True,
        encoding="utf-8",
    )

    output_text, error_text = process.communicate()

    return CMDOutput(
        output_text=output_text.strip(),
        error_text=error_text.strip(),
        return_code=process.returncode,
    )


class PlatformService(ABC):
    @abstractmethod
    def _config_dir(self, app_name: str) -> str: ...

    @abstractmethod
    def _base_dir(self, app_name: str) -> str: ...

    @abstractmethod
    def _current_version(self, app_name: str) -> str: ...

    def _download_and_verify_geo(self, name: str, url: str, sha_url: str, dest_dir: str) -> None:
        dest_path = os.path.join(dest_dir, f"{name}.db")
        console.print(f"Downloading {name}.db...")
        download_file(url, dest_path)
        console.print("Verifying SHA-256 checksum...")
        sha_dest = dest_path + ".sha256sum"
        download_file(sha_url, sha_dest)
        if verify_sha256(dest_path, sha_dest):
            console.print(f"[green]{name}.db checksum verified.[/green]")
        else:
            console.print(f"[red]{name}.db checksum verification failed.[/red]")
            os.remove(dest_path)
            raise typer.Exit(1)
        os.remove(sha_dest)

    @staticmethod
    def _resolve_dry_run(dry_run: bool | None) -> bool:
        if dry_run is None:
            dry_run = Confirm.ask("[yellow]Run in dry-run mode[/yellow]")
        if dry_run:
            console.print("[yellow]Running in dry-run mode — no changes will be made.[/yellow]")
        return dry_run

    def _detect_and_guide_install(self) -> bool:
        installed = detect_installed_apps()

        if "throne" in installed and "nekoray" in installed:
            console.print("[yellow]Both Throne and NekoRay are installed.[/yellow]")
            console.print("[yellow]NekoRay is deprecated. It is recommended to keep only Throne.[/yellow]")
            if Confirm.ask("[yellow]Remove NekoRay?[/yellow]", default=True):
                self.uninstall(app_name="nekoray", skip_check=True)
                console.print("[green]NekoRay removed. Throne is ready to use.[/green]")
            else:
                console.print("[yellow]Keeping NekoRay. You can remove it later with the remove command.[/yellow]")
            console.print()
            return False

        if "throne" in installed:
            console.print(f"[green]{THRONE_APP_NAME} is already installed.[/green]")
            console.print()
            return False

        if "nekoray" in installed:
            console.print("[yellow]NekoRay is installed.[/yellow]")
            console.print("[yellow]NekoRay is deprecated. Would you like to upgrade to Throne?[/yellow]")
            if Confirm.ask("[yellow]Upgrade to Throne? (This will remove NekoRay)[/yellow]", default=True):
                self.uninstall(app_name="nekoray", skip_check=True)
                console.print("[green]NekoRay removed. Proceeding with Throne installation...[/green]")
                console.print()
                return True
            console.print()
            return False

        return True

    @property
    @abstractmethod
    def platform_name(self) -> str: ...

    @abstractmethod
    def install(self) -> None: ...

    @abstractmethod
    def uninstall(self, app_name: str, skip_check: bool = False) -> None: ...

    @abstractmethod
    def version(self, app_name: str) -> None: ...

    def backup(self, app_name: str, output_path: str | None) -> str:
        console.print("[bold]BACKUP CONFIGURATION[/bold]")
        console.print()
        if not app_name:
            app_name = prompt_app_name()
        config_dir = self._config_dir(app_name)
        if not config_dir or not os.path.isdir(config_dir):
            console.print(f"[red]Config directory does not exist: {config_dir}[/red]")
            raise typer.Exit(1)
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        backup_name = f"{app_name}-backup-{date_str}.zip"
        if output_path:
            dest_path = os.path.join(output_path, backup_name) if os.path.isdir(output_path) else output_path
        else:
            dest_path = os.path.join(os.getcwd(), backup_name)
        console.print(f"Compressing config from {config_dir}...")
        zip_dir(config_dir, dest_path)
        console.print("[green]Backup created:[/green]")
        console.print(f"[green]{dest_path}[/green]")
        console.print()
        return dest_path

    def restore(self, app_name: str, zip_file: str) -> None:
        console.print("[bold]RESTORE CONFIGURATION[/bold]")
        console.print()
        if not zip_file:
            zip_file = Prompt.ask("[bold]Enter the path to the backup .zip file[/bold]").strip()
        if not zip_file:
            console.print("[red]Please provide the path to the backup .zip file.[/red]")
            raise typer.Exit(1)
        if not os.path.isfile(zip_file):
            console.print(f"[red]File not found: {zip_file}[/red]")
            raise typer.Exit(1)
        if not app_name:
            app_name = prompt_app_name()
        base_dir = self._base_dir(app_name)
        restore_dir = self._config_dir(app_name)
        if not base_dir:
            console.print("[red]Target configuration directory does not exist for this app.[/red]")
            raise typer.Exit(1)
        if not os.path.isdir(base_dir):
            os.makedirs(base_dir, exist_ok=True)
        if os.path.isdir(restore_dir):
            console.print(f"Removing existing config: {restore_dir}")
            rmtree(restore_dir)
        os.makedirs(restore_dir, exist_ok=True)
        console.print(f"Restoring backup to: {restore_dir}")
        with ZipFile(zip_file, "r") as handle:
            handle.extractall(restore_dir)
        console.print("[green]Restore complete![/green]")
        console.print()

    def reinstall(
        self,
        app_name: str,
        backup: bool = False,
        output_path: str | None = None,
        force: bool = False,
    ) -> None:
        if app_name == "nekoray":
            console.print(
                "[yellow]Installer only supports Throne packages; reinstall will install Throne.[/yellow]",
            )
        backup_path = None
        if backup:
            backup_path = self.backup(app_name=app_name, output_path=output_path)
        self.uninstall(app_name=app_name, skip_check=force)
        self.install()
        if backup_path:
            self.restore(app_name=app_name, zip_file=backup_path)

    def update(self, app_name: str) -> None:
        console.print("[bold]UPDATE[/bold]")
        console.print()
        if app_name == "throne":
            installed = detect_installed_apps()
            if "nekoray" in installed and "throne" not in installed:
                console.print("[yellow]NekoRay is installed. Would you like to upgrade to Throne?[/yellow]")
                if Confirm.ask("[yellow]Upgrade to Throne? (This will remove NekoRay)[/yellow]", default=True):
                    self.uninstall(app_name="nekoray", skip_check=True)
                    self.install()
                    return
                console.print()
                return
            if "nekoray" in installed:
                console.print("[yellow]NekoRay is installed alongside Throne. Remove it?[/yellow]")
                if Confirm.ask("[yellow]Remove NekoRay?[/yellow]", default=True):
                    self.uninstall(app_name="nekoray", skip_check=True)
        elif app_name == "nekoray":
            console.print("[yellow]NekoRay is deprecated. Use 'thronetools install' to upgrade to Throne.[/yellow]")
            console.print()
            return
        console.print(f"Checking current version of {app_name}...")
        current_version = self._current_version(app_name)
        console.print("Fetching latest release...")
        release = github_latest_release()
        latest_tag = release.get("tag_name", "")
        latest_version = latest_tag.lstrip("v")
        if current_version and current_version >= latest_version:
            console.print(f"[green]{app_name} is already up to date at version {current_version}.[/green]")
            console.print()
            return
        if current_version:
            console.print(f"Current version: {current_version}")
            console.print(f"Latest version: {latest_version}")
            console.print(f"Updating {app_name} to {latest_version}...")
        else:
            console.print(f"Latest version: {latest_version}")
            console.print(f"Installing {app_name} {latest_version}...")
        self.uninstall(app_name=app_name, skip_check=True)
        self.install()

    def install_geo(self) -> None:
        console.print("[bold]INSTALL GEO FILES[/bold]")
        console.print()
        app_name = prompt_app_name()
        config_dir = self._config_dir(app_name)
        base_dir = self._base_dir(app_name)
        if not base_dir or not config_dir:
            console.print("[red]Unrecognized app name.[/red]")
            raise typer.Exit(1)
        os.makedirs(config_dir, exist_ok=True)
        self._download_and_verify_geo("geoip", GEOIP_URL, GEOIP_SHA_URL, config_dir)
        self._download_and_verify_geo("geosite", GEOSITE_URL, GEOSITE_SHA_URL, config_dir)
        console.print("[green]Geo files installed successfully![/green]")
        console.print()

    # Optional: hotspot support (can raise NotImplementedError on Windows)
    def enable_hotspot(
        self,
        dry_run: bool | None = None,
        iface: str | None = None,
        ssid: str | None = None,
        password: str | None = None,
    ) -> None:
        msg = "Hotspot not supported on this platform"
        raise NotImplementedError(msg)

    def disable_hotspot(self, dry_run: bool | None = None) -> None:
        msg = "Hotspot not supported on this platform"
        raise NotImplementedError(msg)


class LinuxService(PlatformService):
    @property
    def platform_name(self) -> str:
        return "Linux"

    def _config_dir(self, app_name: str) -> str:
        if app_name == "nekoray":
            return os.path.join(os.path.expanduser("~"), ".config/nekoray/config")
        return os.path.join(os.path.expanduser("~"), ".config/Throne/config")

    def _base_dir(self, app_name: str) -> str:
        if app_name == "nekoray":
            return os.path.join(os.path.expanduser("~"), ".config/nekoray")
        return os.path.join(os.path.expanduser("~"), ".config/Throne")

    def _current_version(self, app_name: str) -> str:
        return linux_package_version(app_name) or ""

    def install(self) -> None:
        console.print("[bold]INSTALLATION[/bold]")
        console.print()
        if not self._detect_and_guide_install():
            return

        console.print("[green]Proceeding with Throne installation...[/green]")
        console.print()

        os_release = read_os_release()
        distro = os_release.get("ID", "").lower()
        if not distro:
            console.print("[red]Cannot detect Linux distribution.[/red]")
            raise typer.Exit(1)

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
            console.print(f"[red]Unsupported distribution: {distro}[/red]")
            console.print("[red]Supported distributions: Ubuntu, Debian, Fedora, RHEL, CentOS[/red]")
            raise typer.Exit(1)

        if not which(package_manager):
            console.print(f"[red]{package_manager} is not installed.[/red]")
            raise typer.Exit(1)

        console.print("Fetching latest Throne release information...")
        release = github_latest_release()
        assets = release.get("assets", [])
        target_asset = None
        pattern = re_compile(package_pattern)
        for asset in assets:
            name = asset.get("name", "")
            if pattern.search(name):
                target_asset = asset
                break

        if not target_asset:
            console.print(f"[red]Could not find {package_type} package in the latest release.[/red]")
            console.print("[red]Available packages:[/red]")
            for asset in assets:
                console.print(asset.get("name", ""))
            raise typer.Exit(1)

        package_url = target_asset.get("browser_download_url")
        package_name = target_asset.get("name")
        console.print(f"Downloading {package_name}...")

        with TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, package_name)
            download_file(package_url, dest)
            console.print(f"Installing Throne {package_type} package...")
            result = run_cmd([*install_cmd, dest])
            if result and result.return_code == 0:
                console.print("[green]Throne installed successfully![/green]")
            else:
                console.print(
                    "[yellow]Installation completed with some warnings. Fixing dependencies...[/yellow]",
                )
                run_cmd(fix_cmd)

        console.print()
        console.print(
            "[green]Done! Throne has been installed system-wide. You can find it in your applications menu![/green]",
        )
        console.print()

    def uninstall(self, app_name: str, skip_check: bool = False) -> None:
        console.print("[bold]UNINSTALL[/bold]")

        console.print()
        if not app_name:
            app_name = prompt_app_name("Enter which app (nekoray, throne): ")
        console.print(f"\nUninstalling {app_name}...")

        if not skip_check and not check_installations(app_name):
            console.print(f"[yellow]\nNo {app_name} installations found on this system.[/yellow]")
            console.print()
            return

        if which("dpkg"):
            res = run_cmd(["dpkg", "-l"])
            if res.return_code == 0 and app_name in res.output_text:
                console.print(f"Removing {app_name} .deb package...")
                run_cmd(["sudo", "dpkg", "-r", app_name])
        if which("rpm"):
            res = run_cmd(["rpm", "-q", app_name])
            if res.return_code == 0:
                console.print(f"Removing {app_name} .rpm package...")
                run_cmd(["sudo", "rpm", "-e", app_name])

            for variant in _get_app_variants(app_name):
                for location in _linux_variant_paths(variant):
                    if os.path.isdir(location) or os.path.isfile(location):
                        run_cmd(["sudo", "rm", "-rf", location])

        console.print(f"[green]\n{app_name} installations have been removed.[/green]")
        console.print()

    def version(self, app_name: str) -> None:
        version = linux_package_version(app_name) or "unknown"
        paths = linux_install_paths(app_name)
        _show_version_table(app_name, version, paths[0] if paths else "not found")

    def enable_hotspot(
        self,
        dry_run: bool | None = None,
        iface: str | None = None,
        ssid: str | None = None,
        password: str | None = None,
    ) -> None:
        console.print("[bold]ENABLE HOTSPOT[/bold]")
        console.print()
        console.print("[green]Starting Throne Hotspot...[/green]")
        dry_run = self._resolve_dry_run(dry_run)

        if not ensure_linux_command(
            "nmcli",
            "   Debian/Ubuntu: sudo apt install network-manager\n"
            "   Fedora:        sudo dnf install NetworkManager\n"
            "   Arch:          sudo pacman -S networkmanager",
        ):
            raise typer.Exit(1)
        if not ensure_linux_command(
            "iw",
            "   Debian/Ubuntu: sudo apt install iw\n"
            "   Fedora:        sudo dnf install iw\n"
            "   Arch:          sudo pacman -S iw",
        ):
            raise typer.Exit(1)
        if not ensure_linux_command(
            "nft",
            "   Debian/Ubuntu: sudo apt install nftables\n"
            "   Fedora:        sudo dnf install nftables\n"
            "   Arch:          sudo pacman -S nftables",
        ):
            raise typer.Exit(1)

        hotspot_iface = find_linux_wifi_iface(iface)
        if not hotspot_iface:
            if iface:
                console.print(f"[red]Wi-Fi interface not found: {iface}[/red]")
            else:
                console.print("[red]No Wi-Fi interface found. Exiting.[/red]")
            raise typer.Exit(1)
        console.print(f"[green]Wi-Fi interface: [bold]{hotspot_iface}[/bold][/green]")

        res = run_cmd(["sudo", "nft", "list", "table", "inet", LINUX_REQUIRED_INET_TABLE])
        if res.return_code != 0:
            console.print(f"[red]Missing 'inet {LINUX_REQUIRED_INET_TABLE}' nftables table.[/red]")
            console.print("   Please enable 'Tun Mode' in Throne/NekoRay GUI settings.")
            raise typer.Exit(1)

        console.print("[green]Enabling Wi-Fi...[/green]")
        run_cmd(["nmcli", "radio", "wifi", "on"], dry_run=dry_run)

        res = run_cmd(["iw", "dev", hotspot_iface, "info"])
        if res.return_code == 0 and "type AP" in res.output_text:
            console.print(f"[yellow]A Wi-Fi hotspot is already active on {hotspot_iface}. Skipping creation.[/yellow]")
            return

        console.print("[green]Starting hotspot...[/green]")
        password = password or _prompt_password()

        ssid = ssid or DEFAULT_SSID

        if dry_run:
            console.print(
                f'[blue]→ nmcli dev wifi hotspot ifname "{hotspot_iface}" ssid "{ssid}" password "********"[/blue]'
            )
        else:
            res = run_cmd(
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
            if res.return_code != 0:
                console.print("[red]Failed to start hotspot — maybe AP mode is unsupported.[/red]")
                raise typer.Exit(1)

        console.print("[green]Setting up nftables rules...[/green]")

        table = LINUX_NFT_TABLE
        tun_iface = LINUX_TUN_IFACE
        hs_iface = hotspot_iface

        run_cmd(["sudo", "nft", "delete", "table", "ip", table], dry_run=dry_run)
        run_cmd(["sudo", "nft", "add", "table", "ip", table], dry_run=dry_run)
        run_cmd(
            [
                "sudo",
                "nft",
                "add",
                "chain",
                "ip",
                table,
                "postrouting",
                "{",
                "type",
                "nat",
                "hook",
                "postrouting",
                "priority",
                "srcnat",
                ";",
                "policy",
                "accept",
                ";",
                "}",
            ],
            dry_run=dry_run,
        )
        run_cmd(
            ["sudo", "nft", "add", "rule", "ip", table, "postrouting", "oifname", tun_iface, "masquerade"],
            dry_run=dry_run,
        )
        run_cmd(
            [
                "sudo",
                "nft",
                "add",
                "chain",
                "ip",
                table,
                "forward",
                "{",
                "type",
                "filter",
                "hook",
                "forward",
                "priority",
                "filter",
                ";",
                "policy",
                "accept",
                ";",
                "}",
            ],
            dry_run=dry_run,
        )
        run_cmd(
            ["sudo", "nft", "add", "rule", "ip", table, "forward", "iifname", hs_iface, "oifname", tun_iface, "accept"],
            dry_run=dry_run,
        )
        run_cmd(
            [
                "sudo",
                "nft",
                "add",
                "rule",
                "ip",
                table,
                "forward",
                "iifname",
                tun_iface,
                "oifname",
                hs_iface,
                "ct",
                "state",
                "established,related",
                "accept",
            ],
            dry_run=dry_run,
        )

        console.print()
        console.print("[bold green]Hotspot is ready and running![/bold green]")
        console.print(f"SSID: {ssid}")
        console.print(f"Password: {password}")
        console.print()

    def disable_hotspot(self, dry_run: bool | None = None) -> None:
        console.print("[bold]DISABLE HOTSPOT[/bold]")
        console.print()
        dry_run = self._resolve_dry_run(dry_run)

        console.print("[green]Stopping hotspot...[/green]")
        run_cmd(["nmcli", "connection", "down", "Hotspot"], dry_run=dry_run)
        run_cmd(["nmcli", "connection", "delete", "Hotspot"], dry_run=dry_run)

        console.print("[green]Removing nftables table...[/green]")
        run_cmd(["sudo", "nft", "delete", "table", "ip", LINUX_NFT_TABLE], dry_run=dry_run)

        console.print()
        console.print("[bold green]Hotspot stopped and nftables rules removed.[/bold green]")
        console.print()


class MacOSService(PlatformService):
    @property
    def platform_name(self) -> str:
        return "macOS"

    def _config_dir(self, app_name: str) -> str:
        return os.path.join(os.path.expanduser("~"), "Library/Preferences", app_name, "config")

    def _base_dir(self, app_name: str) -> str:
        return os.path.join(os.path.expanduser("~"), "Library/Preferences", app_name)

    def _current_version(self, app_name: str) -> str:
        app_bundle = macos_app_bundle(app_name)
        return macos_app_version(app_bundle) if app_bundle else ""

    def install(self) -> None:
        console.print("[bold]INSTALLATION[/bold]")
        console.print()
        if not self._detect_and_guide_install():
            return

        console.print(f"Fetching latest {THRONE_APP_NAME} release...")
        release = github_latest_release()
        assets = release.get("assets", [])

        arch = machine()
        pattern = re_compile(rf"{escape(THRONE_APP_NAME)}.*macos-{escape(arch)}\.zip")
        target_asset = None
        for asset in assets:
            name = asset.get("name", "")
            if pattern.search(name):
                target_asset = asset
                break

        if not target_asset:
            console.print(f"[red]Failed to find download URL for macOS {arch}.[/red]")
            raise typer.Exit(1)

        download_url = target_asset.get("browser_download_url")
        console.print(f"Downloading from: {download_url}")

        with TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, f"{THRONE_APP_NAME}.zip")
            download_file(download_url, zip_path)
            console.print("Installing...")
            with ZipFile(zip_path, "r") as handle:
                handle.extractall(tmpdir)

            app_src = os.path.join(tmpdir, THRONE_APP_NAME, f"{THRONE_APP_NAME}.app")
            if not os.path.isdir(app_src):
                console.print("[red]Extracted app not found in archive.[/red]")
                raise typer.Exit(1)

            try:
                move(app_src, "/Applications/")
            except PermissionError:
                console.print(
                    "[red]Permission denied while moving app to /Applications. Run this script with sudo.[/red]",
                )
                raise typer.Exit(1) from None

        console.print()
        console.print(f"[green]Done! {THRONE_APP_NAME} has been installed to /Applications.[/green]")
        console.print(f"[green]You can now launch '{THRONE_APP_NAME}' from Spotlight or Launchpad.[/green]")
        console.print()

    def uninstall(self, app_name: str, skip_check: bool = False) -> None:
        console.print("[bold]UNINSTALL[/bold]")
        console.print()
        if not app_name:
            app_name = prompt_app_name()
        prefs_dir = os.path.join(os.path.expanduser("~"), "Library/Preferences", app_name)
        app_bundle = f"/Applications/{app_name}.app"

        console.print(f"\nUninstalling {app_name}...")
        if os.path.isdir(prefs_dir):
            console.print(f"Removing preferences: {prefs_dir}")
            run_cmd(["sudo", "rm", "-rvf", prefs_dir])
        else:
            console.print(f"No preferences folder found at: {prefs_dir}")

        if os.path.isdir(app_bundle):
            console.print(f"Removing app bundle: {app_bundle}")
            run_cmd(["sudo", "rm", "-rvf", app_bundle])
        else:
            console.print(f"No app found at: {app_bundle}")

        console.print(f"[green]\n{app_name} has been successfully uninstalled.[/green]")
        console.print()

    def version(self, app_name: str) -> None:
        app_bundle = macos_app_bundle(app_name)
        version = macos_app_version(app_bundle) if app_bundle else ""
        _show_version_table(app_name, version, app_bundle or "not found")

    def enable_hotspot(
        self,
        dry_run: bool | None = None,
        iface: str | None = None,
        ssid: str | None = None,
        password: str | None = None,
    ) -> None:
        console.print("[bold]ENABLE HOTSPOT[/bold]")
        console.print()
        console.print("[green]Starting Throne Hotspot (best-effort on macOS)...[/green]")

        dry_run = self._resolve_dry_run(dry_run)

        if not which("networksetup"):
            console.print("[red]'networksetup' not found. macOS hotspot is unavailable.[/red]")
            raise typer.Exit(1)

        airport_tool = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
        if not os.path.exists(airport_tool):
            console.print("[red]'airport' tool not found. macOS hotspot is unavailable.[/red]")
            raise typer.Exit(1)

        if not iface:
            iface = detect_macos_wifi_iface()
        if not iface:
            console.print("[red]Wi-Fi interface not found on macOS.[/red]")
            raise typer.Exit(1)

        ssid = ssid or DEFAULT_SSID

        password = password or _prompt_password()

        console.print("[green]Enabling Wi-Fi...[/green]")
        run_cmd(["networksetup", "-setairportpower", iface, "on"], dry_run=dry_run)

        console.print("[green]Attempting to create hotspot...[/green]")
        create_cmd = [airport_tool, "--create", ssid, password]
        if dry_run:
            run_cmd(create_cmd, dry_run=True)
            res = CMDOutput(output_text="", error_text="", return_code=0)
        else:
            res = run_cmd(create_cmd)
        if res.return_code != 0:
            console.print("[yellow]Failed to create hotspot via 'airport'.[/yellow]")
            console.print("   macOS hotspot setup can require manual configuration.")

        sharing_plist = "/System/Library/LaunchDaemons/com.apple.InternetSharing.plist"
        if os.path.exists(sharing_plist):
            console.print("[green]Attempting to enable Internet Sharing...[/green]")
            run_cmd(
                ["sudo", "launchctl", "load", "-w", sharing_plist],
                dry_run=dry_run,
            )
        else:
            console.print("[yellow]Internet Sharing plist not found.[/yellow]")

        console.print()
        console.print("[bold green]Hotspot command completed (best-effort).[/bold green]")
        console.print(f"SSID: {ssid}")
        console.print(f"Password: {password}")
        console.print("Verify in System Settings → General → Sharing → Internet Sharing.")
        console.print()

    def disable_hotspot(self, dry_run: bool | None = None) -> None:
        console.print("[bold]DISABLE HOTSPOT[/bold]")
        console.print()
        dry_run = self._resolve_dry_run(dry_run)

        sharing_plist = "/System/Library/LaunchDaemons/com.apple.InternetSharing.plist"
        if os.path.exists(sharing_plist):
            console.print("[green]Attempting to disable Internet Sharing...[/green]")
            run_cmd(
                ["sudo", "launchctl", "unload", "-w", sharing_plist],
                dry_run=dry_run,
            )
        else:
            console.print("[yellow]Internet Sharing plist not found.[/yellow]")

        console.print()
        console.print("[bold green]Hotspot stop command completed (best-effort).[/bold green]")
        console.print()


class WindowsService(PlatformService):
    @property
    def platform_name(self) -> str:
        return "Windows"

    def _config_dir(self, app_name: str) -> str:
        base = windows_config_base(app_name)
        return os.path.join(base, "config") if base else ""

    def _base_dir(self, app_name: str) -> str:
        return windows_config_base(app_name)

    def _current_version(self, app_name: str) -> str:
        candidates = windows_exe_candidates(app_name)
        exe_path = next((path for path in candidates if os.path.isfile(path)), "")
        return windows_exe_version(exe_path) if exe_path else ""

    def install(self) -> None:
        console.print("[bold]INSTALLATION[/bold]")
        console.print()
        if not self._detect_and_guide_install():
            return

        console.print("Fetching latest Throne release...")

        release = github_latest_release()
        assets = release.get("assets", [])
        target_asset = find_windows_installer_asset(assets)

        if not target_asset:
            console.print("[red]No Windows installer found in the latest release.[/red]")
            raise typer.Exit(1)

        installer_url = target_asset.get("browser_download_url", "")
        installer_name = target_asset.get("name", "")
        temp_dir = gettempdir()
        installer_path = os.path.join(temp_dir, "throne_installer.exe")

        console.print(f"Found installer: {installer_name}")
        console.print("Downloading Throne installer...")
        download_file(installer_url, installer_path)

        if os.path.isfile(installer_path):
            console.print(f"Download completed: {installer_path}")
            console.print("Launching installer...")
            try:
                Popen([installer_path], shell=False)  # noqa: S603
            except OSError as exc:
                console.print(f"[red]Failed to launch installer: {exc}[/red]")
                raise typer.Exit(1) from exc
            console.print("Installer launched. Exiting.")
        else:
            console.print("[red]Download failed.[/red]")
            raise typer.Exit(1)

    def uninstall(self, app_name: str, skip_check: bool = False) -> None:
        console.print("[bold]UNINSTALL[/bold]")
        console.print()
        if not app_name:
            app_name = prompt_app_name("Enter which app (nekoray, throne): ")

        console.print(f"\nUninstalling {app_name}...")
        base_dir = windows_config_base(app_name)
        config_dir = os.path.join(base_dir, "config") if base_dir else ""
        if config_dir and os.path.isdir(config_dir):
            console.print(f"Removing config: {config_dir}")
            rmtree(config_dir)

        local_appdata = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("PROGRAMFILES", "")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")

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
            console.print(f"Launching uninstaller: {uninstallers[0]}")
            try:
                Popen([uninstallers[0]], shell=False)  # noqa: S603
            except OSError as exc:
                console.print(f"[red]Failed to launch uninstaller: {exc}[/red]")
                console.print("Please uninstall using Windows Apps & Features.")
                raise typer.Exit(1) from exc
        else:
            console.print("[yellow]Uninstaller not found.[/yellow]")
            console.print("Please uninstall using Windows Apps & Features.")

        console.print(f"[green]\n{app_name} uninstall steps completed.[/green]")
        console.print()

    def version(self, app_name: str) -> None:
        candidates = windows_exe_candidates(app_name)
        exe_path = next((path for path in candidates if os.path.isfile(path)), "")
        version = windows_exe_version(exe_path) if exe_path else ""
        _show_version_table(app_name, version, exe_path or "not found")


def show_banner(platform_name) -> None:
    console.print(BANNER, style="cyan")
    console.print(f"[bold]{THRONE_APP_NAME} Tools for {platform_name}[/bold]")


def prompt_app_name(prompt_text: str | None = None) -> str:
    app_name = Prompt.ask(prompt_text or PROMPT_APP_TEXT).strip().lower()
    if app_name not in {"nekoray", "throne"}:
        console.print("[red]Invalid app name. Only 'nekoray' or 'throne' allowed.[/red]")
        raise typer.Exit(1)
    return app_name


def run_cmd(cmd: str | list[str], dry_run: bool = False, shell: bool = False) -> CMDOutput:
    if dry_run:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        console.print(f"[blue]{cmd_str}[/blue]")
        return CMDOutput(output_text="", error_text="", return_code=0)
    if shell or isinstance(cmd, str):
        result = subprocess_run(cmd, shell=shell, capture_output=True, text=True)  # noqa: S603
        return CMDOutput(
            output_text=result.stdout.strip(),
            error_text=result.stderr.strip(),
            return_code=result.returncode,
        )
    return run_command(cmd)


def read_os_release() -> dict[str, str]:
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


def check_installations(app_name: str) -> bool:
    found = False
    if which("dpkg"):
        res = run_cmd(["dpkg", "-l"])
        if res.return_code == 0 and app_name in res.output_text:
            console.print(f"[yellow]{app_name} package is installed.[/yellow]")
            found = True
    if which("rpm"):
        res = run_cmd(["rpm", "-q", app_name])
        if res.return_code == 0:
            console.print(f"[yellow]{app_name} package is installed.[/yellow]")
            found = True

    for variant in _get_app_variants(app_name):
        for location in _linux_variant_paths(variant):
            if os.path.isdir(location) or os.path.isfile(location):
                console.print(f"[yellow]Found system installation: {location}[/yellow]")
                found = True
    return found


def github_latest_release() -> dict:
    req = Request(  # noqa: S310
        THRONE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ThroneInstaller",
        },
    )
    with urlopen(req, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
        data = response.read()
    return loads(data.decode("utf-8"))


def download_file(url: str, dest_path: str) -> None:
    req = Request(url, headers={"User-Agent": "ThroneTools"})  # noqa: S310
    with (
        urlopen(req, timeout=HTTP_TIMEOUT) as response,  # noqa: S310
        open(dest_path, "wb") as handle,
        Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress,
    ):
        progress.add_task("[cyan]Downloading...", total=None)
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


def verify_sha256(file_path: str, sha_file_path: str) -> bool:
    with open(sha_file_path) as handle:
        expected = handle.read().strip().split()[0]
    hasher = hash_new("sha256")
    with open(file_path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest() == expected


def zip_dir(source_dir: str, dest_zip: str) -> None:
    with ZipFile(dest_zip, "w", compression=ZIP_DEFLATED) as handle:
        for root, _, files in os.walk(source_dir):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, source_dir)
                handle.write(full_path, rel_path)


def ensure_linux_command(cmd: str, hint: str | None = None) -> bool:
    if which(cmd):
        return True
    console.print(f"[red]'{cmd}' command not found. Please install it.[/red]")
    if hint:
        console.print(hint)
    return False


def detect_wifi_iface() -> str:
    res = run_cmd(["nmcli", "device", "status"])
    if res.return_code != 0:
        return ""
    for line in res.output_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "wifi":
            return parts[0]
    return ""


def find_linux_wifi_iface(requested_iface: str | None) -> str:
    if not requested_iface:
        return detect_wifi_iface()
    res = run_cmd(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"])
    if res.return_code != 0:
        return ""
    for line in res.output_text.splitlines():
        if ":" not in line:
            continue
        device, dev_type = line.split(":", 1)
        if device == requested_iface and dev_type == "wifi":
            return device
    return ""


def detect_macos_wifi_iface() -> str:
    res = run_cmd(["networksetup", "-listallhardwareports"])
    if res.return_code != 0:
        return ""
    lines = res.output_text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("Hardware Port:"):
            port = line.split(":", 1)[1].strip().lower()
            if port in {"wi-fi", "airport"}:
                for next_line in lines[idx + 1 : idx + 3]:
                    if next_line.startswith("Device:"):
                        return next_line.split(":", 1)[1].strip()
    return ""


def find_windows_installer_asset(assets: list) -> dict | None:
    pattern = re_compile(r"windows.*installer\.exe$", IGNORECASE)
    for asset in assets:
        name = asset.get("name", "")
        if pattern.search(name):
            return asset
    return None


def windows_config_base(app_name: str) -> str:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return ""
    if app_name == "throne":
        return os.path.join(appdata, "Throne")
    return os.path.join(appdata, "nekoray")


def linux_install_paths(app_name: str) -> list[str]:
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


def macos_app_bundle(app_name: str) -> str:
    candidates = ["Throne.app"] if app_name == "throne" else ["NekoRay.app", "nekoray.app"]
    for name in candidates:
        path = os.path.join("/Applications", name)
        if os.path.isdir(path):
            return path
    return ""


def macos_app_version(app_bundle: str) -> str:
    info_plist = os.path.join(app_bundle, "Contents", "Info.plist")
    if not os.path.isfile(info_plist):
        return ""
    try:
        with open(info_plist, "rb") as handle:
            data = plistlib_load(handle)
    except (OSError, InvalidFileException):
        return ""
    return data.get("CFBundleShortVersionString") or data.get("CFBundleVersion") or ""


def linux_package_version(app_name: str) -> str:
    if which("dpkg"):
        res = run_cmd(["dpkg", "-s", app_name])
        if res.return_code == 0:
            for line in res.output_text.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
    if which("rpm"):
        res = run_cmd(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", app_name])
        if res.return_code == 0:
            return res.output_text.strip()
    return ""


def windows_exe_candidates(app_name: str) -> list[str]:
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", "")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
    exe_name = "Throne.exe" if app_name == "throne" else "NekoRay.exe"
    app_dir = "Throne" if app_name == "throne" else "NekoRay"
    return [
        os.path.join(local_appdata, "Programs", app_dir, exe_name),
        os.path.join(program_files, app_dir, exe_name),
        os.path.join(program_files_x86, app_dir, exe_name),
    ]


def windows_exe_version(exe_path: str) -> str:
    if not exe_path:
        return ""
    escaped = exe_path.replace("'", "''")
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-Item '{escaped}').VersionInfo.ProductVersion",
    ]
    res = run_cmd(cmd)
    if res.return_code == 0:
        return res.output_text.strip()
    return ""


def _get_app_variants(app_name: str) -> list[str]:
    return ["throne", "Throne"] if app_name == "throne" else ["nekoray", "NekoRay"]


def _linux_variant_paths(variant: str) -> list[str]:
    return [
        f"/opt/{variant}",
        f"/usr/share/applications/{variant}.desktop",
        os.path.join(os.path.expanduser("~"), ".local/share/applications", f"{variant}.desktop"),
        os.path.join(os.path.expanduser("~"), ".config", variant),
    ]


def detect_installed_apps() -> set[str]:
    installed: set[str] = set()
    for app_name in ("throne", "nekoray"):
        if sys_platform.startswith("linux"):
            if which("dpkg"):
                res = run_cmd(["dpkg", "-l"])
                if res.return_code == 0 and app_name in res.output_text:
                    installed.add(app_name)
            if which("rpm"):
                res = run_cmd(["rpm", "-q", app_name])
                if res.return_code == 0:
                    installed.add(app_name)
            for variant in _get_app_variants(app_name):
                for location in _linux_variant_paths(variant):
                    if os.path.isdir(location) or os.path.isfile(location):
                        installed.add(app_name)
        elif sys_platform == "darwin":
            if macos_app_bundle(app_name):
                installed.add(app_name)
        elif sys_platform.startswith("win"):
            candidates = windows_exe_candidates(app_name)
            if any(os.path.isfile(p) for p in candidates):
                installed.add(app_name)
            base = windows_config_base(app_name)
            if base and os.path.isdir(base):
                installed.add(app_name)
    return installed


def _prompt_password(min_length: int = MIN_PASSWORD_LENGTH) -> str:
    while True:
        _pw_prompt = f"\n[bold]Enter hotspot password (min {min_length} chars)[/bold]"
        password = Prompt.ask(_pw_prompt, password=True)
        if len(password) >= min_length:
            return password
        console.print(f"[red]Password must be at least {min_length} characters.[/red]")


_THRONETOOLS_VERSION: str | None = None


def _get_thronetools_version() -> str:
    global _THRONETOOLS_VERSION
    if _THRONETOOLS_VERSION is None:
        _THRONETOOLS_VERSION = pkg_version("thronetools")
    return _THRONETOOLS_VERSION


def _show_version_table(app_name: str, version: str, install_path: str) -> None:
    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("App", app_name)
    table.add_row("Version", version or "unknown")
    table.add_row("ThroneTools", _get_thronetools_version())
    table.add_row("Install path", install_path or "not found")
    console.print(table)


def get_service() -> PlatformService:
    """Get the appropriate service for the current platform."""
    if sys_platform.startswith("linux"):
        return LinuxService()
    if sys_platform == "darwin":
        return MacOSService()
    if sys_platform.startswith("win"):
        return WindowsService()
    console.print("[red]Unsupported platform. This tool supports Linux, macOS, and Windows.[/red]")
    raise typer.Exit(1)


class StyledGroup(typer.core.TyperGroup):
    def format_help(self, ctx: typer.Context, formatter: object) -> None:
        show_styled_help(ctx)


def show_styled_help(ctx: typer.Context) -> None:
    group = ctx.parent.command if ctx.parent is not None else ctx.command
    cmd_path = ctx.parent.command_path if ctx.parent is not None else ctx.command_path

    console.print("[bold]Usage:[/bold]")
    console.print(f"  {cmd_path} [OPTIONS] COMMAND [ARGS]...\n")

    commands = group.commands
    if commands:
        console.print("[bold]Commands:[/bold]")
        table = Table(show_header=False, box=box.SIMPLE, padding=0)
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("Description")
        for name, cmd in sorted(commands.items()):
            if cmd.hidden:
                continue
            short_help = cmd.get_short_help_str(limit=60)
            table.add_row(f"  {name}", short_help)
        console.print(table)
        console.print()

    console.print("[bold]Options:[/bold]")
    table = Table(show_header=False, box=box.SIMPLE, padding=0)
    table.add_column("Option", style="cyan", no_wrap=True)
    table.add_column("Description")
    for param in group.params:
        if param.name in ("help", "install_completion", "show_completion"):
            continue
        opts = ", ".join(param.opts)
        help_text = param.help or ""
        table.add_row(f"  {opts}", help_text)
    table.add_row("  -h/--help", "Show this message and exit")
    console.print(table)


app = typer.Typer(
    name="thronetools",
    cls=StyledGroup,
    context_settings={"help_option_names": ["--help", "-h"]},
)


@app.callback(invoke_without_command=True)
def master(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        show_styled_help(ctx)
        raise typer.Exit()


@app.command()
def install() -> None:
    """Install Throne."""
    get_service().install()


@app.command()
def backup(
    app: str = typer.Option("throne", "--app", help="throne or nekoray"),
    output: str | None = typer.Option(None, "--output", help="Output directory or file path"),
) -> None:
    """Backup configuration."""
    get_service().backup(app_name=app, output_path=output)


@app.command()
def restore(
    app: str = typer.Option(..., "--app", help="throne or nekoray"),
    zip_file: str = typer.Option(..., "--zip", help="Path to backup .zip file"),
) -> None:
    """Restore configuration."""
    get_service().restore(app_name=app, zip_file=zip_file)


@app.command()
def remove(
    app: str | None = typer.Option(None, "--app", help="throne or nekoray"),
) -> None:
    """Uninstall Throne or NekoRay."""
    service = get_service()
    if not app:
        installed = detect_installed_apps()
        if not installed:
            console.print("[yellow]No Throne or NekoRay installations found.[/yellow]")
            raise typer.Exit()
        if len(installed) == 1:
            app = installed.pop()
        else:
            console.print("[yellow]Multiple apps detected. Which one to remove?[/yellow]")
            app = prompt_app_name()
    service.uninstall(app_name=app)


@app.command()
def reinstall(
    app: str = typer.Option(..., "--app", help="throne or nekoray"),
    backup: bool = typer.Option(False, "--backup", help="Backup config before reinstall"),
    output: str | None = typer.Option(None, "--output", help="Backup output path"),
    force: bool = typer.Option(False, "--force", help="Proceed even if not installed"),
) -> None:
    """Reinstall Throne."""
    get_service().reinstall(app_name=app, backup=backup, output_path=output, force=force)


@app.command()
def version(
    app: str = typer.Option("throne", "--app", help="throne or nekoray"),
) -> None:
    """Show installed version and path."""
    get_service().version(app_name=app)


@app.command()
def update(
    app: str = typer.Option("throne", "--app", help="throne or nekoray"),
) -> None:
    """Update Throne to the latest version."""
    get_service().update(app_name=app)


@app.command()
def geo_install(
    app: str = typer.Option("throne", "--app", help="throne or nekoray"),
) -> None:
    """Install geoip and geosite files."""
    get_service().install_geo()


hotspot_app = typer.Typer(help="Hotspot controls (Linux/macOS only)")


@hotspot_app.command("enable")
def hotspot_enable(
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without making changes"),
    iface: str | None = typer.Option(None, "--iface", help="Wi-Fi interface"),
    ssid: str | None = typer.Option(None, "--ssid", help="Hotspot SSID"),
    password: str | None = typer.Option(None, "--password", help="Hotspot password (min 8 chars)"),
) -> None:
    """Enable hotspot."""
    service = get_service()
    if not isinstance(service, (LinuxService, MacOSService)):
        console.print("[red]Hotspot commands are supported on Linux/macOS only.[/red]")
        raise typer.Exit(1)
    service.enable_hotspot(dry_run=dry_run, iface=iface, ssid=ssid, password=password)


@hotspot_app.command("disable")
def hotspot_disable(
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without making changes"),
) -> None:
    """Disable hotspot."""
    service = get_service()
    if not isinstance(service, (LinuxService, MacOSService)):
        console.print("[red]Hotspot commands are supported on Linux/macOS only.[/red]")
        raise typer.Exit(1)
    service.disable_hotspot(dry_run=dry_run)


app.add_typer(hotspot_app, name="hotspot")


def main() -> None:
    show_banner(get_service().platform_name)
    app()


if __name__ == "__main__":
    main()
