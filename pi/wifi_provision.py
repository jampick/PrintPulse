"""PrintPulse OOBE — WiFi provisioning via AP mode + captive portal.

On first boot (or when no known network is available), the Pi creates
a hotspot named 'PrintPulse-Setup'.  Users connect from a phone or laptop,
pick their home WiFi in the captive portal, and the Pi joins automatically.

This module also supports an SD-card fallback: drop a file called
``printpulse-wifi.txt`` onto the boot partition with::

    SSID=MyNetwork
    PASSWORD=MySecret

and the Pi will configure WiFi on first boot without needing AP mode.

All system calls are routed through helper functions so they can be
mocked in tests (no real hardware required in CI).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time

logger = logging.getLogger("printpulse.wifi")

# ── Constants ────────────────────────────────────────────────────────────────

AP_SSID = "PrintPulse-Setup"
AP_CHANNEL = 7
AP_IP = "192.168.4.1"
AP_SUBNET = "192.168.4.0/24"
AP_DHCP_START = "192.168.4.10"
AP_DHCP_END = "192.168.4.50"

# SD-card provisioning file — Bookworm moved /boot to /boot/firmware
_BOOT_PATHS = ["/boot/firmware", "/boot"]
WIFI_CONFIG_FILENAME = "printpulse-wifi.txt"

# NetworkManager connection name used by AP mode
NM_AP_CONNECTION = "printpulse-ap"
NM_HOME_CONNECTION = "printpulse-home"


# ── State Machine ────────────────────────────────────────────────────────────

class WifiState:
    """Simple enum for the provisioning state machine."""
    UNKNOWN = "unknown"
    CONNECTED = "connected"       # On home WiFi — normal operation
    AP_MODE = "ap_mode"           # Broadcasting setup hotspot
    PROVISIONING = "provisioning"  # Credentials received, attempting connect
    FAILED = "failed"             # Connection attempt failed


# ── System helpers (mockable) ────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 30, check: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess and return the result."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)


def _file_exists(path: str) -> bool:
    return os.path.isfile(path)


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _delete_file(path: str) -> None:
    os.remove(path)


# ── Network State Detection ─────────────────────────────────────────────────

def check_wifi_connected() -> bool:
    """Return True if the wlan0 interface has an IP on a non-AP network."""
    try:
        result = _run(["nmcli", "-t", "-f", "DEVICE,STATE", "device"])
        if result.returncode != 0:
            return False
        for line in result.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[0] == "wlan0" and parts[1] == "connected":
                # Make sure it's not our own AP connection
                active = _run(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"])
                for aline in active.stdout.strip().splitlines():
                    aparts = aline.split(":")
                    if len(aparts) >= 2 and aparts[1] == "wlan0" and aparts[0] != NM_AP_CONNECTION:
                        return True
        return False
    except (OSError, subprocess.TimeoutExpired):
        return False


def get_current_state() -> str:
    """Determine current WiFi provisioning state."""
    try:
        result = _run(["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "connection", "show", "--active"])
        for line in result.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[0] == NM_AP_CONNECTION:
                return WifiState.AP_MODE
        if check_wifi_connected():
            return WifiState.CONNECTED
        return WifiState.UNKNOWN
    except (OSError, subprocess.TimeoutExpired):
        return WifiState.UNKNOWN


# ── Network Scanning ─────────────────────────────────────────────────────────

def scan_wifi_networks() -> list[dict]:
    """Scan for available WiFi networks.

    Returns a list of dicts with keys: ssid, signal, security.
    """
    networks: list[dict] = []
    try:
        # Rescan
        _run(["nmcli", "device", "wifi", "rescan"], timeout=10)
        time.sleep(2)

        result = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"])
        if result.returncode != 0:
            return networks

        seen: set[str] = set()
        for line in result.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) < 3:
                continue
            ssid = parts[0].strip()
            if not ssid or ssid in seen or ssid == AP_SSID:
                continue
            seen.add(ssid)
            try:
                signal = int(parts[1])
            except ValueError:
                signal = 0
            security = parts[2].strip() if parts[2].strip() else "Open"
            networks.append({"ssid": ssid, "signal": signal, "security": security})

        # Sort by signal strength descending
        networks.sort(key=lambda n: n["signal"], reverse=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("WiFi scan failed: %s", exc)

    return networks


# ── AP Mode Control ──────────────────────────────────────────────────────────

def start_ap_mode() -> bool:
    """Activate the PrintPulse-Setup WiFi hotspot via NetworkManager.

    Returns True on success.
    """
    logger.info("Starting AP mode: SSID=%s", AP_SSID)
    try:
        # Remove any existing AP connection first
        _run(["nmcli", "connection", "delete", NM_AP_CONNECTION])

        # Create AP hotspot
        result = _run([
            "nmcli", "connection", "add",
            "type", "wifi",
            "ifname", "wlan0",
            "con-name", NM_AP_CONNECTION,
            "autoconnect", "no",
            "ssid", AP_SSID,
            "mode", "ap",
            "ipv4.method", "shared",
            "ipv4.addresses", f"{AP_IP}/24",
            "wifi-sec.key-mgmt", "none",
        ])
        if result.returncode != 0:
            logger.error("Failed to create AP connection: %s", result.stderr)
            return False

        # Bring it up
        result = _run(["nmcli", "connection", "up", NM_AP_CONNECTION])
        if result.returncode != 0:
            logger.error("Failed to activate AP: %s", result.stderr)
            return False

        logger.info("AP mode active at %s", AP_IP)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("AP mode start failed: %s", exc)
        return False


def stop_ap_mode() -> bool:
    """Deactivate and remove the AP hotspot."""
    logger.info("Stopping AP mode")
    try:
        _run(["nmcli", "connection", "down", NM_AP_CONNECTION])
        _run(["nmcli", "connection", "delete", NM_AP_CONNECTION])
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("AP mode stop failed: %s", exc)
        return False


# ── WiFi Connection ──────────────────────────────────────────────────────────

def connect_to_wifi(ssid: str, password: str) -> tuple[bool, str]:
    """Connect to a WiFi network.

    Returns (success, message).
    """
    if not ssid or not ssid.strip():
        return False, "SSID cannot be empty"
    if len(ssid) > 32:
        return False, "SSID too long (max 32 characters)"
    if password and len(password) > 63:
        return False, "Password too long (max 63 characters)"

    logger.info("Attempting to connect to WiFi: %s", ssid)

    try:
        # Stop AP mode first if active
        stop_ap_mode()
        time.sleep(1)

        # Remove any previous home connection
        _run(["nmcli", "connection", "delete", NM_HOME_CONNECTION])

        # Connect
        cmd = [
            "nmcli", "device", "wifi", "connect", ssid,
            "name", NM_HOME_CONNECTION,
        ]
        if password:
            cmd.extend(["password", password])

        result = _run(cmd, timeout=30)

        if result.returncode == 0:
            logger.info("Connected to %s", ssid)
            return True, f"Connected to {ssid}"
        else:
            err = result.stderr.strip() or result.stdout.strip() or "Connection failed"
            logger.warning("Failed to connect to %s: %s", ssid, err)
            return False, err

    except subprocess.TimeoutExpired:
        return False, "Connection timed out"
    except OSError as exc:
        return False, f"System error: {exc}"


# ── SD Card Provisioning ────────────────────────────────────────────────────

def parse_wifi_config_file(content: str) -> tuple[str | None, str | None]:
    """Parse a printpulse-wifi.txt file.

    Expected format (one key=value per line)::

        SSID=MyNetwork
        PASSWORD=MySecret

    Returns (ssid, password).  Password may be None for open networks.
    """
    ssid = None
    password = None

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = re.match(r"^(SSID|PASSWORD)\s*=\s*(.+)$", line, re.IGNORECASE)
        if match:
            key = match.group(1).upper()
            value = match.group(2).strip()
            if key == "SSID":
                ssid = value
            elif key == "PASSWORD":
                password = value

    return ssid, password


def find_wifi_config_file() -> str | None:
    """Look for printpulse-wifi.txt on the boot partition.

    Returns the full path if found, else None.
    """
    for boot_dir in _BOOT_PATHS:
        path = os.path.join(boot_dir, WIFI_CONFIG_FILENAME)
        if _file_exists(path):
            return path
    return None


def process_sd_card_config() -> tuple[bool, str]:
    """Check for and process SD-card WiFi config.

    If found, configures WiFi and deletes the file.
    Returns (success, message).
    """
    config_path = find_wifi_config_file()
    if config_path is None:
        return False, "No SD card WiFi config found"

    logger.info("Found SD card WiFi config at %s", config_path)

    try:
        content = _read_file(config_path)
    except OSError as exc:
        return False, f"Cannot read config file: {exc}"

    ssid, password = parse_wifi_config_file(content)
    if not ssid:
        logger.warning("SD card config has no SSID")
        return False, "Config file has no SSID"

    success, msg = connect_to_wifi(ssid, password or "")

    # Delete the file regardless of success (contains credentials)
    try:
        _delete_file(config_path)
        logger.info("Deleted SD card config file: %s", config_path)
    except OSError as exc:
        logger.warning("Could not delete config file: %s", exc)

    return success, msg


# ── Boot-Time Provisioning Orchestrator ──────────────────────────────────────

def run_provisioning_check() -> str:
    """Run the full provisioning check sequence at boot.

    1. If already connected to WiFi → done
    2. Try SD card config → if success, done
    3. Start AP mode for captive portal

    Returns the resulting WifiState.
    """
    # Already connected?
    if check_wifi_connected():
        logger.info("WiFi already connected — skipping provisioning")
        return WifiState.CONNECTED

    # Try SD card first
    success, msg = process_sd_card_config()
    if success:
        logger.info("WiFi configured via SD card: %s", msg)
        return WifiState.CONNECTED

    # Fall through to AP mode
    if start_ap_mode():
        logger.info("AP mode started — waiting for user to configure WiFi")
        return WifiState.AP_MODE
    else:
        logger.error("Failed to start AP mode")
        return WifiState.FAILED


# ── Input Validation ─────────────────────────────────────────────────────────

def validate_wifi_input(ssid: str, password: str) -> list[str]:
    """Validate WiFi SSID and password from the captive portal form.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []

    if not ssid or not ssid.strip():
        errors.append("Network name (SSID) is required.")
    elif len(ssid) > 32:
        errors.append("Network name too long (max 32 characters).")

    if password and len(password) > 63:
        errors.append("Password too long (max 63 characters).")
    # Note: empty password is valid for open networks

    return errors
