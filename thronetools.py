import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import new as hash_new
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

from cfui import App, Arg, Fail, ui

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
        ui.info(f"Downloading {name}.db...")
        download_file(url, dest_path)
        ui.info("Verifying SHA-256 checksum...")
        sha_dest = dest_path + ".sha256sum"
        download_file(sha_url, sha_dest)
        if verify_sha256(dest_path, sha_dest):
            ui.info(f"{name}.db checksum verified.")
        else:
            ui.error(f"{name}.db checksum verification failed.")
            os.remove(dest_path)
            raise SystemExit(1)
        os.remove(sha_dest)

    @staticmethod
    def _resolve_dry_run(dry_run: bool | None) -> bool:
        if dry_run is None:
            dry_run = ui.confirm("Run in dry-run mode")
        if dry_run:
            ui.warning("Running in dry-run mode — no changes will be made.")
        return dry_run

    def _detect_and_guide_install(self) -> bool:
        installed = detect_installed_apps()

        if "throne" in installed and "nekoray" in installed:
            ui.warning("Both Throne and NekoRay are installed.")
            ui.warning("NekoRay is deprecated. It is recommended to keep only Throne.")
            if ui.confirm("Remove NekoRay?", default=True):
                self.uninstall(app_name="nekoray", skip_check=True)
                ui.info("NekoRay removed. Throne is ready to use.")
            else:
                ui.warning("Keeping NekoRay. You can remove it later with the remove command.")
            ui.out()
            return False

        if "throne" in installed:
            ui.info(f"{THRONE_APP_NAME} is already installed.")
            ui.out()
            return False

        if "nekoray" in installed:
            ui.warning("NekoRay is installed.")
            ui.warning("NekoRay is deprecated. Would you like to upgrade to Throne?")
            if ui.confirm("Upgrade to Throne? (This will remove NekoRay)", default=True):
                self.uninstall(app_name="nekoray", skip_check=True)
                ui.info("NekoRay removed. Proceeding with Throne installation...")
                ui.out()
                return True
            ui.out()
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
        ui.heading("BACKUP CONFIGURATION")
        ui.out()
        if not app_name:
            app_name = prompt_app_name()
        config_dir = self._config_dir(app_name)
        if not config_dir or not os.path.isdir(config_dir):
            ui.error(f"Config directory does not exist: {config_dir}")
            raise SystemExit(1)
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        backup_name = f"{app_name}-backup-{date_str}.zip"
        if output_path:
            dest_path = os.path.join(output_path, backup_name) if os.path.isdir(output_path) else output_path
        else:
            dest_path = os.path.join(os.getcwd(), backup_name)
        ui.info(f"Compressing config from {config_dir}...")
        zip_dir(config_dir, dest_path)
        ui.info("Backup created:")
        ui.info(f"{dest_path}")
        ui.out()
        return dest_path

    def restore(self, app_name: str, zip_file: str) -> None:
        ui.heading("RESTORE CONFIGURATION")
        ui.out()
        if not zip_file:
            zip_file = ui.ask("Enter the path to the backup .zip file").strip()
        if not zip_file:
            ui.error("Please provide the path to the backup .zip file.")
            raise SystemExit(1)
        if not os.path.isfile(zip_file):
            ui.error(f"File not found: {zip_file}")
            raise SystemExit(1)
        if not app_name:
            app_name = prompt_app_name()
        base_dir = self._base_dir(app_name)
        restore_dir = self._config_dir(app_name)
        if not base_dir:
            ui.error("Target configuration directory does not exist for this app.")
            raise SystemExit(1)
        if not os.path.isdir(base_dir):
            os.makedirs(base_dir, exist_ok=True)
        if os.path.isdir(restore_dir):
            ui.info(f"Removing existing config: {restore_dir}")
            rmtree(restore_dir)
        os.makedirs(restore_dir, exist_ok=True)
        ui.info(f"Restoring backup to: {restore_dir}")
        with ZipFile(zip_file, "r") as handle:
            handle.extractall(restore_dir)
        ui.info("Restore complete!")
        ui.out()

    def reinstall(
        self,
        app_name: str,
        backup: bool = False,
        output_path: str | None = None,
        force: bool = False,
    ) -> None:
        if app_name == "nekoray":
            ui.warning("Installer only supports Throne packages; reinstall will install Throne.")
        backup_path = None
        if backup:
            backup_path = self.backup(app_name=app_name, output_path=output_path)
        self.uninstall(app_name=app_name, skip_check=force)
        self.install()
        if backup_path:
            self.restore(app_name=app_name, zip_file=backup_path)

    def update(self, app_name: str) -> None:
        ui.heading("UPDATE")
        ui.out()
        if app_name == "throne":
            installed = detect_installed_apps()
            if "nekoray" in installed and "throne" not in installed:
                ui.warning("NekoRay is installed. Would you like to upgrade to Throne?")
                if ui.confirm("Upgrade to Throne? (This will remove NekoRay)", default=True):
                    self.uninstall(app_name="nekoray", skip_check=True)
                    self.install()
                    return
                ui.out()
                return
            if "nekoray" in installed:
                ui.warning("NekoRay is installed alongside Throne. Remove it?")
                if ui.confirm("Remove NekoRay?", default=True):
                    self.uninstall(app_name="nekoray", skip_check=True)
        elif app_name == "nekoray":
            ui.warning("NekoRay is deprecated. Use 'thronetools install' to upgrade to Throne.")
            ui.out()
            return
        ui.info(f"Checking current version of {app_name}...")
        current_version = self._current_version(app_name)
        ui.info("Fetching latest release...")
        release = github_latest_release()
        latest_tag = release.get("tag_name", "")
        latest_version = latest_tag.lstrip("v")
        if current_version and current_version >= latest_version:
            ui.info(f"{app_name} is already up to date at version {current_version}.")
            ui.out()
            return
        if current_version:
            ui.info(f"Current version: {current_version}")
            ui.info(f"Latest version: {latest_version}")
            ui.info(f"Updating {app_name} to {latest_version}...")
        else:
            ui.info(f"Latest version: {latest_version}")
            ui.info(f"Installing {app_name} {latest_version}...")
        self.uninstall(app_name=app_name, skip_check=True)
        self.install()

    def install_geo(self) -> None:
        ui.heading("INSTALL GEO FILES")
        ui.out()
        app_name = prompt_app_name()
        config_dir = self._config_dir(app_name)
        base_dir = self._base_dir(app_name)
        if not base_dir or not config_dir:
            ui.error("Unrecognized app name.")
            raise SystemExit(1)
        os.makedirs(config_dir, exist_ok=True)
        self._download_and_verify_geo("geoip", GEOIP_URL, GEOIP_SHA_URL, config_dir)
        self._download_and_verify_geo("geosite", GEOSITE_URL, GEOSITE_SHA_URL, config_dir)
        ui.success("Geo files installed successfully!")
        ui.out()

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
        ui.heading("INSTALLATION")
        ui.out()
        if not self._detect_and_guide_install():
            return

        ui.info("Proceeding with Throne installation...")
        ui.out()

        os_release = read_os_release()
        distro = os_release.get("ID", "").lower()
        if not distro:
            ui.error("Cannot detect Linux distribution.")
            raise SystemExit(1)

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
            ui.error(f"Unsupported distribution: {distro}")
            ui.error("Supported distributions: Ubuntu, Debian, Fedora, RHEL, CentOS")
            raise SystemExit(1)

        if not which(package_manager):
            ui.error(f"{package_manager} is not installed.")
            raise SystemExit(1)

        ui.info("Fetching latest Throne release information...")
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
            ui.error(f"Could not find {package_type} package in the latest release.")
            ui.error("Available packages:")
            for asset in assets:
                ui.out(asset.get("name", ""))
            raise SystemExit(1)

        package_url = target_asset.get("browser_download_url")
        package_name = target_asset.get("name")
        ui.info(f"Downloading {package_name}...")

        with TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, package_name)
            download_file(package_url, dest)
            ui.info(f"Installing Throne {package_type} package...")
            result = run_cmd([*install_cmd, dest])
            if result and result.return_code == 0:
                ui.success("Throne installed successfully!")
            else:
                ui.warning("Installation completed with some warnings. Fixing dependencies...")
                run_cmd(fix_cmd)

        ui.out()
        ui.success("Done! Throne has been installed system-wide. You can find it in your applications menu!")
        ui.out()

    def uninstall(self, app_name: str, skip_check: bool = False) -> None:
        ui.heading("UNINSTALL")

        ui.out()
        if not app_name:
            app_name = prompt_app_name("Enter which app (nekoray, throne): ")
        ui.info(f"\nUninstalling {app_name}...")

        if not skip_check and not check_installations(app_name):
            ui.warning(f"\nNo {app_name} installations found on this system.")
            ui.out()
            return

        if which("dpkg"):
            res = run_cmd(["dpkg", "-l"])
            if res.return_code == 0 and app_name in res.output_text:
                ui.info(f"Removing {app_name} .deb package...")
                run_cmd(["sudo", "dpkg", "-r", app_name])
        if which("rpm"):
            res = run_cmd(["rpm", "-q", app_name])
            if res.return_code == 0:
                ui.info(f"Removing {app_name} .rpm package...")
                run_cmd(["sudo", "rpm", "-e", app_name])

            for variant in _get_app_variants(app_name):
                for location in _linux_variant_paths(variant):
                    if os.path.isdir(location) or os.path.isfile(location):
                        run_cmd(["sudo", "rm", "-rf", location])

        ui.info(f"\n{app_name} installations have been removed.")
        ui.out()

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
        ui.heading("ENABLE HOTSPOT")
        ui.out()
        ui.info("Starting Throne Hotspot...")
        dry_run = self._resolve_dry_run(dry_run)

        if not ensure_linux_command(
            "nmcli",
            "   Debian/Ubuntu: sudo apt install network-manager\n"
            "   Fedora:        sudo dnf install NetworkManager\n"
            "   Arch:          sudo pacman -S networkmanager",
        ):
            raise SystemExit(1)
        if not ensure_linux_command(
            "iw",
            "   Debian/Ubuntu: sudo apt install iw\n"
            "   Fedora:        sudo dnf install iw\n"
            "   Arch:          sudo pacman -S iw",
        ):
            raise SystemExit(1)
        if not ensure_linux_command(
            "nft",
            "   Debian/Ubuntu: sudo apt install nftables\n"
            "   Fedora:        sudo dnf install nftables\n"
            "   Arch:          sudo pacman -S nftables",
        ):
            raise SystemExit(1)

        hotspot_iface = find_linux_wifi_iface(iface)
        if not hotspot_iface:
            if iface:
                ui.error(f"Wi-Fi interface not found: {iface}")
            else:
                ui.error("No Wi-Fi interface found. Exiting.")
            raise SystemExit(1)
        ui.info(f"Wi-Fi interface: {hotspot_iface}")

        res = run_cmd(["sudo", "nft", "list", "table", "inet", LINUX_REQUIRED_INET_TABLE])
        if res.return_code != 0:
            ui.error(f"Missing 'inet {LINUX_REQUIRED_INET_TABLE}' nftables table.")
            ui.info("   Please enable 'Tun Mode' in Throne/NekoRay GUI settings.")
            raise SystemExit(1)

        ui.info("Enabling Wi-Fi...")
        run_cmd(["nmcli", "radio", "wifi", "on"], dry_run=dry_run)

        res = run_cmd(["iw", "dev", hotspot_iface, "info"])
        if res.return_code == 0 and "type AP" in res.output_text:
            ui.warning(f"A Wi-Fi hotspot is already active on {hotspot_iface}. Skipping creation.")
            return

        ui.info("Starting hotspot...")
        password = password or _prompt_password()

        ssid = ssid or DEFAULT_SSID

        if dry_run:
            ui.hint(f'→ nmcli dev wifi hotspot ifname "{hotspot_iface}" ssid "{ssid}" password "********"')
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
                ui.error("Failed to start hotspot — maybe AP mode is unsupported.")
                raise SystemExit(1)

        ui.info("Setting up nftables rules...")

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

        ui.out()
        ui.info("[bold green]Hotspot is ready and running![/bold green]")
        ui.info(f"SSID: {ssid}")
        ui.info(f"Password: {password}")
        ui.out()

    def disable_hotspot(self, dry_run: bool | None = None) -> None:
        ui.heading("DISABLE HOTSPOT")
        ui.out()
        dry_run = self._resolve_dry_run(dry_run)

        ui.info("Stopping hotspot...")
        run_cmd(["nmcli", "connection", "down", "Hotspot"], dry_run=dry_run)
        run_cmd(["nmcli", "connection", "delete", "Hotspot"], dry_run=dry_run)

        ui.info("Removing nftables table...")
        run_cmd(["sudo", "nft", "delete", "table", "ip", LINUX_NFT_TABLE], dry_run=dry_run)

        ui.out()
        ui.info("[bold green]Hotspot stopped and nftables rules removed.[/bold green]")
        ui.out()


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
        ui.heading("INSTALLATION")
        ui.out()
        if not self._detect_and_guide_install():
            return

        ui.info(f"Fetching latest {THRONE_APP_NAME} release...")
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
            ui.error(f"Failed to find download URL for macOS {arch}.")
            raise SystemExit(1)

        download_url = target_asset.get("browser_download_url")
        ui.info(f"Downloading from: {download_url}")

        with TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, f"{THRONE_APP_NAME}.zip")
            download_file(download_url, zip_path)
            ui.info("Installing...")
            with ZipFile(zip_path, "r") as handle:
                handle.extractall(tmpdir)

            app_src = os.path.join(tmpdir, THRONE_APP_NAME, f"{THRONE_APP_NAME}.app")
            if not os.path.isdir(app_src):
                ui.error("Extracted app not found in archive.")
                raise SystemExit(1)

            try:
                move(app_src, "/Applications/")
            except PermissionError:
                ui.error("Permission denied while moving app to /Applications. Run this script with sudo.")
                raise SystemExit(1) from None

        ui.out()
        ui.info(f"Done! {THRONE_APP_NAME} has been installed to /Applications.")
        ui.info(f"You can now launch '{THRONE_APP_NAME}' from Spotlight or Launchpad.")
        ui.out()

    def uninstall(self, app_name: str, skip_check: bool = False) -> None:
        ui.heading("UNINSTALL")
        ui.out()
        if not app_name:
            app_name = prompt_app_name()
        prefs_dir = os.path.join(os.path.expanduser("~"), "Library/Preferences", app_name)
        app_bundle = f"/Applications/{app_name}.app"

        ui.info(f"\nUninstalling {app_name}...")
        if os.path.isdir(prefs_dir):
            ui.info(f"Removing preferences: {prefs_dir}")
            run_cmd(["sudo", "rm", "-rvf", prefs_dir])
        else:
            ui.info(f"No preferences folder found at: {prefs_dir}")

        if os.path.isdir(app_bundle):
            ui.info(f"Removing app bundle: {app_bundle}")
            run_cmd(["sudo", "rm", "-rvf", app_bundle])
        else:
            ui.info(f"No app found at: {app_bundle}")

        ui.success(f"\n{app_name} has been successfully uninstalled.")
        ui.out()

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
        ui.heading("ENABLE HOTSPOT")
        ui.out()
        ui.info("Starting Throne Hotspot (best-effort on macOS)...")

        dry_run = self._resolve_dry_run(dry_run)

        if not which("networksetup"):
            ui.error("'networksetup' not found. macOS hotspot is unavailable.")
            raise SystemExit(1)

        airport_tool = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
        if not os.path.exists(airport_tool):
            ui.error("'airport' tool not found. macOS hotspot is unavailable.")
            raise SystemExit(1)

        if not iface:
            iface = detect_macos_wifi_iface()
        if not iface:
            ui.error("Wi-Fi interface not found on macOS.")
            raise SystemExit(1)

        ssid = ssid or DEFAULT_SSID

        password = password or _prompt_password()

        ui.info("Enabling Wi-Fi...")
        run_cmd(["networksetup", "-setairportpower", iface, "on"], dry_run=dry_run)

        ui.info("Attempting to create hotspot...")
        create_cmd = [airport_tool, "--create", ssid, password]
        if dry_run:
            run_cmd(create_cmd, dry_run=True)
            res = CMDOutput(output_text="", error_text="", return_code=0)
        else:
            res = run_cmd(create_cmd)
        if res.return_code != 0:
            ui.warning("Failed to create hotspot via 'airport'.")
            ui.info("   macOS hotspot setup can require manual configuration.")

        sharing_plist = "/System/Library/LaunchDaemons/com.apple.InternetSharing.plist"
        if os.path.exists(sharing_plist):
            ui.info("Attempting to enable Internet Sharing...")
            run_cmd(
                ["sudo", "launchctl", "load", "-w", sharing_plist],
                dry_run=dry_run,
            )
        else:
            ui.warning("Internet Sharing plist not found.")

        ui.out()
        ui.info("[bold green]Hotspot command completed (best-effort).[/bold green]")
        ui.info(f"SSID: {ssid}")
        ui.info(f"Password: {password}")
        ui.info("Verify in System Settings → General → Sharing → Internet Sharing.")
        ui.out()

    def disable_hotspot(self, dry_run: bool | None = None) -> None:
        ui.heading("DISABLE HOTSPOT")
        ui.out()
        dry_run = self._resolve_dry_run(dry_run)

        sharing_plist = "/System/Library/LaunchDaemons/com.apple.InternetSharing.plist"
        if os.path.exists(sharing_plist):
            ui.info("Attempting to disable Internet Sharing...")
            run_cmd(
                ["sudo", "launchctl", "unload", "-w", sharing_plist],
                dry_run=dry_run,
            )
        else:
            ui.warning("Internet Sharing plist not found.")

        ui.out()
        ui.info("[bold green]Hotspot stop command completed (best-effort).[/bold green]")
        ui.out()


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
        ui.heading("INSTALLATION")
        ui.out()
        if not self._detect_and_guide_install():
            return

        ui.info("Fetching latest Throne release...")

        release = github_latest_release()
        assets = release.get("assets", [])
        target_asset = find_windows_installer_asset(assets)

        if not target_asset:
            ui.error("No Windows installer found in the latest release.")
            raise SystemExit(1)

        installer_url = target_asset.get("browser_download_url", "")
        installer_name = target_asset.get("name", "")
        temp_dir = gettempdir()
        installer_path = os.path.join(temp_dir, "throne_installer.exe")

        ui.info(f"Found installer: {installer_name}")
        ui.info("Downloading Throne installer...")
        download_file(installer_url, installer_path)

        if os.path.isfile(installer_path):
            ui.info(f"Download completed: {installer_path}")
            ui.info("Launching installer...")
            try:
                Popen([installer_path], shell=False)  # noqa: S603
            except OSError as exc:
                ui.error(f"Failed to launch installer: {exc}")
                raise SystemExit(1) from exc
            ui.info("Installer launched. Exiting.")
        else:
            ui.error("Download failed.")
            raise SystemExit(1)

    def uninstall(self, app_name: str, skip_check: bool = False) -> None:
        ui.heading("UNINSTALL")
        ui.out()
        if not app_name:
            app_name = prompt_app_name("Enter which app (nekoray, throne): ")

        ui.info(f"\nUninstalling {app_name}...")
        base_dir = windows_config_base(app_name)
        config_dir = os.path.join(base_dir, "config") if base_dir else ""
        if config_dir and os.path.isdir(config_dir):
            ui.info(f"Removing config: {config_dir}")
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
            ui.info(f"Launching uninstaller: {uninstallers[0]}")
            try:
                Popen([uninstallers[0]], shell=False)  # noqa: S603
            except OSError as exc:
                ui.error(f"Failed to launch uninstaller: {exc}")
                ui.info("Please uninstall using Windows Apps & Features.")
                raise SystemExit(1) from exc
        else:
            ui.warning("Uninstaller not found.")
            ui.info("Please uninstall using Windows Apps & Features.")

        ui.info(f"\n{app_name} uninstall steps completed.")
        ui.out()

    def version(self, app_name: str) -> None:
        candidates = windows_exe_candidates(app_name)
        exe_path = next((path for path in candidates if os.path.isfile(path)), "")
        version = windows_exe_version(exe_path) if exe_path else ""
        _show_version_table(app_name, version, exe_path or "not found")


def prompt_app_name(prompt_text: str | None = None) -> str:
    app_name = ui.ask(prompt_text or PROMPT_APP_TEXT).strip().lower()
    if app_name not in {"nekoray", "throne"}:
        ui.error("Invalid app name. Only 'nekoray' or 'throne' allowed.")
        raise SystemExit(1)
    return app_name


def run_cmd(cmd: str | list[str], dry_run: bool = False, shell: bool = False) -> CMDOutput:
    if dry_run:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        ui.hint(f"{cmd_str}")
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
            ui.warning(f"{app_name} package is installed.")
            found = True
    if which("rpm"):
        res = run_cmd(["rpm", "-q", app_name])
        if res.return_code == 0:
            ui.warning(f"{app_name} package is installed.")
            found = True

    for variant in _get_app_variants(app_name):
        for location in _linux_variant_paths(variant):
            if os.path.isdir(location) or os.path.isfile(location):
                ui.warning(f"Found system installation: {location}")
                found = True
    return found


def github_latest_release() -> dict:
    req = Request(
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
    ):
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
    ui.error(f"'{cmd}' command not found. Please install it.")
    if hint:
        ui.hint(hint)
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
        _pw_prompt = f"Hotspot password (min {min_length} chars)"
        password = ui.ask(_pw_prompt, secret=True)
        if len(password) >= min_length:
            return password
        ui.error(f"Password must be at least {min_length} characters.")


def _show_version_table(app_name: str, version: str, install_path: str) -> None:
    ui.table([("App", app_name), ("Version", version or "unknown"), ("Install path", install_path or "not found")])


def get_service() -> PlatformService:
    """Get the appropriate service for the current platform."""
    if sys_platform.startswith("linux"):
        return LinuxService()
    if sys_platform == "darwin":
        return MacOSService()
    if sys_platform.startswith("win"):
        return WindowsService()
    ui.error("Unsupported platform. This tool supports Linux, macOS, and Windows.")
    raise SystemExit(1)


APP_ARG = Arg("--app", default="throne", choices=["throne", "nekoray"], help="throne or nekoray")
cli = App(
    "thronetools",
    repo="https://github.com/arian24b/thronetools",
    description="Install, back up, restore and manage Throne / NekoRay, plus a Wi-Fi hotspot helper.",
)


@cli.command("install", "Install Throne", banner=True)
def install(a) -> None:
    get_service().install()


@cli.command(
    "backup",
    "Backup configuration",
    args=[APP_ARG, Arg("--output", help="Output directory or file path")],
)
def backup(a) -> None:
    get_service().backup(app_name=a.app, output_path=a.output)


@cli.command(
    "restore",
    "Restore configuration",
    args=[
        Arg("--app", required=True, choices=["throne", "nekoray"], prompt="Which app", help="throne or nekoray"),
        Arg(
            "--zip",
            required=True,
            dest="zip_file",
            prompt="Path to the backup .zip file",
            help="Path to backup .zip file",
        ),
    ],
)
def restore(a) -> None:
    get_service().restore(app_name=a.app, zip_file=a.zip_file)


@cli.command(
    "remove",
    "Uninstall Throne or NekoRay",
    args=[Arg("--app", choices=["throne", "nekoray"], help="throne or nekoray")],
)
def remove(a) -> None:
    app_name = a.app
    if not app_name:
        installed = detect_installed_apps()
        if not installed:
            ui.warning("No Throne or NekoRay installations found.")
            return
        if len(installed) == 1:
            app_name = installed.pop()
        else:
            ui.warning("Multiple apps detected. Which one to remove?")
            app_name = prompt_app_name()
    get_service().uninstall(app_name=app_name)


@cli.command(
    "reinstall",
    "Reinstall Throne",
    args=[
        Arg("--app", required=True, choices=["throne", "nekoray"], prompt="Which app", help="throne or nekoray"),
        Arg("--backup", action="store_true", help="Backup config before reinstall"),
        Arg("--output", help="Backup output path"),
        Arg("--force", action="store_true", help="Proceed even if not installed"),
    ],
)
def reinstall(a) -> None:
    get_service().reinstall(app_name=a.app, backup=a.backup, output_path=a.output, force=a.force)


@cli.command("app-version", "Show installed Throne/NekoRay version and path", args=[APP_ARG])
def app_version(a) -> None:
    get_service().version(app_name=a.app)


@cli.command("app-update", "Update Throne/NekoRay to the latest version", args=[APP_ARG])
def app_update(a) -> None:
    get_service().update(app_name=a.app)


@cli.command("geo-install", "Install geoip and geosite files", args=[APP_ARG])
def geo_install(a) -> None:
    get_service().install_geo()


def _hotspot_service():
    service = get_service()
    if not isinstance(service, (LinuxService, MacOSService)):
        raise Fail("Hotspot commands are supported on Linux/macOS only.")
    return service


hotspot = cli.group("hotspot", "Hotspot controls (Linux/macOS only)")
DRY_RUN = Arg("--dry-run", action="store_true", help="Run without making changes")


@hotspot.command(
    "enable",
    "Enable hotspot",
    args=[
        DRY_RUN,
        Arg("--iface", help="Wi-Fi interface"),
        Arg("--ssid", help="Hotspot SSID"),
        Arg("--password", help="Hotspot password (min 8 chars)"),
    ],
)
def hotspot_enable(a) -> None:
    _hotspot_service().enable_hotspot(dry_run=a.dry_run, iface=a.iface, ssid=a.ssid, password=a.password)


@hotspot.command("disable", "Disable hotspot", args=[DRY_RUN])
def hotspot_disable(a) -> None:
    _hotspot_service().disable_hotspot(dry_run=a.dry_run)


def main() -> None:
    cli.main()


if __name__ == "__main__":
    main()
