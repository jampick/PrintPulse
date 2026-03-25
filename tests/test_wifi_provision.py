"""Tests for the OOBE WiFi provisioning module.

All system calls are mocked — no real hardware or NetworkManager needed.
"""

import os
from unittest import mock

import pytest

from pi.wifi_provision import (
    AP_SSID,
    NM_AP_CONNECTION,
    NM_HOME_CONNECTION,
    WifiState,
    check_wifi_connected,
    connect_to_wifi,
    find_wifi_config_file,
    get_current_state,
    parse_wifi_config_file,
    process_sd_card_config,
    run_provisioning_check,
    scan_wifi_networks,
    start_ap_mode,
    stop_ap_mode,
    validate_wifi_input,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_run(stdout="", stderr="", returncode=0):
    """Create a mock CompletedProcess."""
    result = mock.MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


# ── parse_wifi_config_file ───────────────────────────────────────────────────

class TestParseWifiConfigFile:
    def test_basic(self):
        ssid, pw = parse_wifi_config_file("SSID=MyNetwork\nPASSWORD=MySecret")
        assert ssid == "MyNetwork"
        assert pw == "MySecret"

    def test_case_insensitive(self):
        ssid, pw = parse_wifi_config_file("ssid=Test\npassword=pass123")
        assert ssid == "Test"
        assert pw == "pass123"

    def test_with_spaces(self):
        ssid, pw = parse_wifi_config_file("SSID = My Network\nPASSWORD = my pass")
        assert ssid == "My Network"
        assert pw == "my pass"

    def test_comments_ignored(self):
        content = "# WiFi config\nSSID=Net\n# password below\nPASSWORD=pass"
        ssid, pw = parse_wifi_config_file(content)
        assert ssid == "Net"
        assert pw == "pass"

    def test_empty_file(self):
        ssid, pw = parse_wifi_config_file("")
        assert ssid is None
        assert pw is None

    def test_ssid_only_open_network(self):
        ssid, pw = parse_wifi_config_file("SSID=OpenNet")
        assert ssid == "OpenNet"
        assert pw is None

    def test_blank_lines(self):
        content = "\n\nSSID=Net\n\nPASSWORD=pass\n\n"
        ssid, pw = parse_wifi_config_file(content)
        assert ssid == "Net"
        assert pw == "pass"

    def test_malformed_lines_ignored(self):
        content = "not a real line\nSSID=Good\ngarbage\nPASSWORD=yes"
        ssid, pw = parse_wifi_config_file(content)
        assert ssid == "Good"
        assert pw == "yes"


# ── validate_wifi_input ──────────────────────────────────────────────────────

class TestValidateWifiInput:
    def test_valid(self):
        assert validate_wifi_input("MyNetwork", "password123") == []

    def test_empty_ssid(self):
        errors = validate_wifi_input("", "pass")
        assert len(errors) == 1
        assert "required" in errors[0].lower()

    def test_ssid_too_long(self):
        errors = validate_wifi_input("A" * 33, "pass")
        assert len(errors) == 1
        assert "32" in errors[0]

    def test_password_too_long(self):
        errors = validate_wifi_input("Net", "A" * 64)
        assert len(errors) == 1
        assert "63" in errors[0]

    def test_open_network_no_password(self):
        assert validate_wifi_input("OpenNet", "") == []

    def test_whitespace_only_ssid(self):
        errors = validate_wifi_input("   ", "pass")
        assert len(errors) == 1


# ── check_wifi_connected ─────────────────────────────────────────────────────

class TestCheckWifiConnected:
    @mock.patch("pi.wifi_provision._run")
    def test_connected(self, mock_run):
        mock_run.side_effect = [
            _mock_run(stdout="wlan0:connected\n"),
            _mock_run(stdout="my-home-wifi:wlan0\n"),
        ]
        assert check_wifi_connected() is True

    @mock.patch("pi.wifi_provision._run")
    def test_not_connected(self, mock_run):
        mock_run.return_value = _mock_run(stdout="wlan0:disconnected\n")
        assert check_wifi_connected() is False

    @mock.patch("pi.wifi_provision._run")
    def test_connected_to_ap_only(self, mock_run):
        mock_run.side_effect = [
            _mock_run(stdout="wlan0:connected\n"),
            _mock_run(stdout=f"{NM_AP_CONNECTION}:wlan0\n"),
        ]
        assert check_wifi_connected() is False

    @mock.patch("pi.wifi_provision._run")
    def test_nmcli_fails(self, mock_run):
        mock_run.return_value = _mock_run(returncode=1)
        assert check_wifi_connected() is False

    @mock.patch("pi.wifi_provision._run")
    def test_os_error(self, mock_run):
        mock_run.side_effect = OSError("nmcli not found")
        assert check_wifi_connected() is False


# ── get_current_state ────────────────────────────────────────────────────────

class TestGetCurrentState:
    @mock.patch("pi.wifi_provision.check_wifi_connected")
    @mock.patch("pi.wifi_provision._run")
    def test_ap_mode(self, mock_run, mock_connected):
        mock_run.return_value = _mock_run(stdout=f"{NM_AP_CONNECTION}:wlan0:wifi\n")
        assert get_current_state() == WifiState.AP_MODE

    @mock.patch("pi.wifi_provision.check_wifi_connected")
    @mock.patch("pi.wifi_provision._run")
    def test_connected(self, mock_run, mock_connected):
        mock_run.return_value = _mock_run(stdout="my-wifi:wlan0:wifi\n")
        mock_connected.return_value = True
        assert get_current_state() == WifiState.CONNECTED

    @mock.patch("pi.wifi_provision.check_wifi_connected")
    @mock.patch("pi.wifi_provision._run")
    def test_unknown(self, mock_run, mock_connected):
        mock_run.return_value = _mock_run(stdout="")
        mock_connected.return_value = False
        assert get_current_state() == WifiState.UNKNOWN


# ── scan_wifi_networks ───────────────────────────────────────────────────────

class TestScanWifiNetworks:
    @mock.patch("pi.wifi_provision._run")
    def test_scan_returns_sorted(self, mock_run):
        mock_run.side_effect = [
            _mock_run(),  # rescan
            _mock_run(stdout="WeakNet:30:WPA2\nStrongNet:90:WPA2\nMidNet:60:Open\n"),
        ]
        networks = scan_wifi_networks()
        assert len(networks) == 3
        assert networks[0]["ssid"] == "StrongNet"
        assert networks[0]["signal"] == 90
        assert networks[2]["ssid"] == "WeakNet"
        assert networks[1]["security"] == "Open"

    @mock.patch("pi.wifi_provision._run")
    def test_deduplicates(self, mock_run):
        mock_run.side_effect = [
            _mock_run(),
            _mock_run(stdout="Net:80:WPA2\nNet:70:WPA2\n"),
        ]
        networks = scan_wifi_networks()
        assert len(networks) == 1

    @mock.patch("pi.wifi_provision._run")
    def test_excludes_own_ap(self, mock_run):
        mock_run.side_effect = [
            _mock_run(),
            _mock_run(stdout=f"{AP_SSID}:100:Open\nReal:80:WPA2\n"),
        ]
        networks = scan_wifi_networks()
        assert len(networks) == 1
        assert networks[0]["ssid"] == "Real"

    @mock.patch("pi.wifi_provision._run")
    def test_empty_scan(self, mock_run):
        mock_run.side_effect = [
            _mock_run(),
            _mock_run(stdout=""),
        ]
        assert scan_wifi_networks() == []

    @mock.patch("pi.wifi_provision._run")
    def test_scan_failure(self, mock_run):
        mock_run.side_effect = OSError("no nmcli")
        assert scan_wifi_networks() == []


# ── start_ap_mode / stop_ap_mode ─────────────────────────────────────────────

class TestAPMode:
    @mock.patch("pi.wifi_provision._run")
    def test_start_success(self, mock_run):
        mock_run.return_value = _mock_run()
        assert start_ap_mode() is True

    @mock.patch("pi.wifi_provision._run")
    def test_start_create_fails(self, mock_run):
        mock_run.side_effect = [
            _mock_run(),  # delete old
            _mock_run(returncode=1, stderr="failed"),  # create fails
        ]
        assert start_ap_mode() is False

    @mock.patch("pi.wifi_provision._run")
    def test_start_activate_fails(self, mock_run):
        mock_run.side_effect = [
            _mock_run(),  # delete old
            _mock_run(),  # create ok
            _mock_run(returncode=1, stderr="activate failed"),  # up fails
        ]
        assert start_ap_mode() is False

    @mock.patch("pi.wifi_provision._run")
    def test_stop_success(self, mock_run):
        mock_run.return_value = _mock_run()
        assert stop_ap_mode() is True

    @mock.patch("pi.wifi_provision._run")
    def test_stop_os_error(self, mock_run):
        mock_run.side_effect = OSError("fail")
        assert stop_ap_mode() is False


# ── connect_to_wifi ──────────────────────────────────────────────────────────

class TestConnectToWifi:
    @mock.patch("pi.wifi_provision._run")
    @mock.patch("pi.wifi_provision.stop_ap_mode")
    def test_success(self, mock_stop_ap, mock_run):
        mock_stop_ap.return_value = True
        mock_run.return_value = _mock_run()
        ok, msg = connect_to_wifi("MyNet", "pass123")
        assert ok is True
        assert "MyNet" in msg

    @mock.patch("pi.wifi_provision._run")
    @mock.patch("pi.wifi_provision.stop_ap_mode")
    def test_failure(self, mock_stop_ap, mock_run):
        mock_stop_ap.return_value = True
        mock_run.side_effect = [
            _mock_run(),  # delete old connection
            _mock_run(returncode=1, stderr="Wrong password"),  # connect fails
        ]
        ok, msg = connect_to_wifi("MyNet", "wrong")
        assert ok is False
        assert "Wrong password" in msg

    def test_empty_ssid(self):
        ok, msg = connect_to_wifi("", "pass")
        assert ok is False
        assert "empty" in msg.lower()

    def test_ssid_too_long(self):
        ok, msg = connect_to_wifi("A" * 33, "pass")
        assert ok is False
        assert "long" in msg.lower()

    @mock.patch("pi.wifi_provision._run")
    @mock.patch("pi.wifi_provision.stop_ap_mode")
    def test_timeout(self, mock_stop_ap, mock_run):
        mock_stop_ap.return_value = True
        import subprocess
        mock_run.side_effect = [
            _mock_run(),  # delete
            subprocess.TimeoutExpired(cmd="nmcli", timeout=30),
        ]
        ok, msg = connect_to_wifi("Net", "pass")
        assert ok is False
        assert "timed out" in msg.lower()


# ── SD Card Provisioning ────────────────────────────────────────────────────

class TestSDCardProvisioning:
    @mock.patch("pi.wifi_provision._file_exists")
    def test_find_bookworm_path(self, mock_exists):
        bookworm = os.path.join("/boot/firmware", "printpulse-wifi.txt")
        mock_exists.side_effect = lambda p: p == bookworm
        assert find_wifi_config_file() == bookworm

    @mock.patch("pi.wifi_provision._file_exists")
    def test_find_bullseye_path(self, mock_exists):
        bookworm = os.path.join("/boot/firmware", "printpulse-wifi.txt")
        bullseye = os.path.join("/boot", "printpulse-wifi.txt")
        # Bookworm path not found, Bullseye path found
        mock_exists.side_effect = lambda p: p == bullseye
        assert find_wifi_config_file() == bullseye

    @mock.patch("pi.wifi_provision._file_exists")
    def test_find_not_found(self, mock_exists):
        mock_exists.return_value = False
        assert find_wifi_config_file() is None

    @mock.patch("pi.wifi_provision._delete_file")
    @mock.patch("pi.wifi_provision.connect_to_wifi")
    @mock.patch("pi.wifi_provision._read_file")
    @mock.patch("pi.wifi_provision.find_wifi_config_file")
    def test_process_success(self, mock_find, mock_read, mock_connect, mock_delete):
        mock_find.return_value = "/boot/printpulse-wifi.txt"
        mock_read.return_value = "SSID=TestNet\nPASSWORD=secret"
        mock_connect.return_value = (True, "Connected")
        ok, msg = process_sd_card_config()
        assert ok is True
        mock_connect.assert_called_once_with("TestNet", "secret")
        mock_delete.assert_called_once_with("/boot/printpulse-wifi.txt")

    @mock.patch("pi.wifi_provision.find_wifi_config_file")
    def test_process_no_file(self, mock_find):
        mock_find.return_value = None
        ok, msg = process_sd_card_config()
        assert ok is False
        assert "No SD card" in msg

    @mock.patch("pi.wifi_provision._delete_file")
    @mock.patch("pi.wifi_provision.connect_to_wifi")
    @mock.patch("pi.wifi_provision._read_file")
    @mock.patch("pi.wifi_provision.find_wifi_config_file")
    def test_process_no_ssid(self, mock_find, mock_read, mock_connect, mock_delete):
        mock_find.return_value = "/boot/printpulse-wifi.txt"
        mock_read.return_value = "PASSWORD=secret"
        ok, msg = process_sd_card_config()
        assert ok is False
        assert "no ssid" in msg.lower()

    @mock.patch("pi.wifi_provision._delete_file")
    @mock.patch("pi.wifi_provision.connect_to_wifi")
    @mock.patch("pi.wifi_provision._read_file")
    @mock.patch("pi.wifi_provision.find_wifi_config_file")
    def test_file_deleted_on_failure(self, mock_find, mock_read, mock_connect, mock_delete):
        mock_find.return_value = "/boot/printpulse-wifi.txt"
        mock_read.return_value = "SSID=BadNet\nPASSWORD=wrong"
        mock_connect.return_value = (False, "Auth failed")
        ok, msg = process_sd_card_config()
        assert ok is False
        # File should still be deleted (contains credentials)
        mock_delete.assert_called_once()


# ── run_provisioning_check (boot orchestrator) ──────────────────────────────

class TestRunProvisioningCheck:
    @mock.patch("pi.wifi_provision.check_wifi_connected")
    def test_already_connected(self, mock_connected):
        mock_connected.return_value = True
        assert run_provisioning_check() == WifiState.CONNECTED

    @mock.patch("pi.wifi_provision.start_ap_mode")
    @mock.patch("pi.wifi_provision.process_sd_card_config")
    @mock.patch("pi.wifi_provision.check_wifi_connected")
    def test_sd_card_success(self, mock_connected, mock_sd, mock_ap):
        mock_connected.return_value = False
        mock_sd.return_value = (True, "Connected via SD card")
        assert run_provisioning_check() == WifiState.CONNECTED
        mock_ap.assert_not_called()

    @mock.patch("pi.wifi_provision.start_ap_mode")
    @mock.patch("pi.wifi_provision.process_sd_card_config")
    @mock.patch("pi.wifi_provision.check_wifi_connected")
    def test_falls_through_to_ap(self, mock_connected, mock_sd, mock_ap):
        mock_connected.return_value = False
        mock_sd.return_value = (False, "No config")
        mock_ap.return_value = True
        assert run_provisioning_check() == WifiState.AP_MODE

    @mock.patch("pi.wifi_provision.start_ap_mode")
    @mock.patch("pi.wifi_provision.process_sd_card_config")
    @mock.patch("pi.wifi_provision.check_wifi_connected")
    def test_ap_mode_fails(self, mock_connected, mock_sd, mock_ap):
        mock_connected.return_value = False
        mock_sd.return_value = (False, "No config")
        mock_ap.return_value = False
        assert run_provisioning_check() == WifiState.FAILED
