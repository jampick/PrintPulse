"""Tests for input validation in the Pi web UI."""

import sys
import os

# Ensure pi/ is importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pi.webapp.server import validate_save_input, _is_private_hostname


class FakeForm(dict):
    """Mimic Flask's request.form (a MultiDict)."""
    def get(self, key, default=None):
        return super().get(key, default)


# ─── Feed URL Validation ────────────────────────────────────────────────────


class TestFeedValidation:
    def _form(self, feeds="", **kw):
        return FakeForm(
            feeds=feeds,
            interval=kw.get("interval", "300"),
            max_prints=kw.get("max_prints", "3"),
            theme=kw.get("theme", "green"),
            printer_device=kw.get("printer_device", "/dev/usb/lp0"),
        )

    def test_valid_https_feed(self):
        data, errors = validate_save_input(self._form(
            feeds="https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"
        ))
        assert not errors
        assert len(data["feeds"]) == 1

    def test_valid_http_feed_allowed(self):
        data, errors = validate_save_input(self._form(
            feeds="http://feeds.bbci.co.uk/news/rss.xml"
        ))
        assert not errors
        assert len(data["feeds"]) == 1

    def test_rejects_file_scheme(self):
        _, errors = validate_save_input(self._form(
            feeds="file:///etc/passwd"
        ))
        assert any("http" in e.lower() or "https" in e.lower() for e in errors)

    def test_rejects_ftp_scheme(self):
        _, errors = validate_save_input(self._form(
            feeds="ftp://example.com/feed.xml"
        ))
        assert len(errors) > 0

    def test_rejects_localhost(self):
        _, errors = validate_save_input(self._form(
            feeds="http://localhost/secret"
        ))
        assert any("private" in e.lower() or "local" in e.lower() for e in errors)

    def test_rejects_private_ip(self):
        _, errors = validate_save_input(self._form(
            feeds="http://192.168.1.1/feed"
        ))
        assert any("private" in e.lower() or "local" in e.lower() for e in errors)

    def test_rejects_link_local(self):
        _, errors = validate_save_input(self._form(
            feeds="http://169.254.169.254/metadata"
        ))
        assert len(errors) > 0

    def test_rejects_loopback_ip(self):
        _, errors = validate_save_input(self._form(
            feeds="http://127.0.0.1/admin"
        ))
        assert len(errors) > 0

    def test_too_many_feeds(self):
        feeds = "\n".join(f"https://example.com/feed{i}.xml" for i in range(25))
        _, errors = validate_save_input(self._form(feeds=feeds))
        assert any("too many" in e.lower() for e in errors)

    def test_feed_url_too_long(self):
        url = "https://example.com/" + "a" * 2100
        _, errors = validate_save_input(self._form(feeds=url))
        assert any("too long" in e.lower() for e in errors)

    def test_empty_feeds_ok(self):
        data, errors = validate_save_input(self._form(feeds=""))
        assert not errors
        assert data["feeds"] == []

    def test_multiple_valid_feeds(self):
        feeds = "https://a.com/feed\nhttps://b.com/feed\nhttps://c.com/feed"
        data, errors = validate_save_input(self._form(feeds=feeds))
        assert not errors
        assert len(data["feeds"]) == 3


# ─── Integer Field Validation ───────────────────────────────────────────────


class TestIntegerValidation:
    def _form(self, **kw):
        defaults = {
            "feeds": "",
            "interval": "300",
            "max_prints": "3",
            "theme": "green",
            "printer_device": "/dev/usb/lp0",
        }
        defaults.update(kw)
        return FakeForm(defaults)

    def test_valid_interval(self):
        data, errors = validate_save_input(self._form(interval="120"))
        assert not errors
        assert data["interval"] == 120

    def test_interval_too_low(self):
        _, errors = validate_save_input(self._form(interval="10"))
        assert any("60" in e for e in errors)

    def test_interval_too_high(self):
        _, errors = validate_save_input(self._form(interval="9999"))
        assert any("3600" in e for e in errors)

    def test_interval_not_a_number(self):
        _, errors = validate_save_input(self._form(interval="abc"))
        assert any("number" in e.lower() for e in errors)

    def test_max_prints_valid(self):
        data, errors = validate_save_input(self._form(max_prints="10"))
        assert not errors
        assert data["max_prints"] == 10

    def test_max_prints_too_low(self):
        _, errors = validate_save_input(self._form(max_prints="0"))
        assert any("1" in e for e in errors)

    def test_max_prints_too_high(self):
        _, errors = validate_save_input(self._form(max_prints="100"))
        assert any("20" in e for e in errors)

    def test_max_prints_not_a_number(self):
        _, errors = validate_save_input(self._form(max_prints="xyz"))
        assert any("number" in e.lower() for e in errors)


# ─── Theme Validation ───────────────────────────────────────────────────────


class TestThemeValidation:
    def _form(self, theme="green"):
        return FakeForm(
            feeds="", interval="300", max_prints="3",
            theme=theme, printer_device="/dev/usb/lp0",
        )

    def test_green_valid(self):
        data, errors = validate_save_input(self._form("green"))
        assert not errors
        assert data["theme"] == "green"

    def test_amber_valid(self):
        data, errors = validate_save_input(self._form("amber"))
        assert not errors
        assert data["theme"] == "amber"

    def test_invalid_theme_rejected(self):
        _, errors = validate_save_input(self._form("hacker"))
        assert any("theme" in e.lower() for e in errors)

    def test_script_injection_rejected(self):
        _, errors = validate_save_input(self._form("<script>alert(1)</script>"))
        assert len(errors) > 0


# ─── Printer Device Validation ──────────────────────────────────────────────


class TestPrinterDeviceValidation:
    def _form(self, device="/dev/usb/lp0"):
        return FakeForm(
            feeds="", interval="300", max_prints="3",
            theme="green", printer_device=device,
        )

    def test_lp0_valid(self):
        data, errors = validate_save_input(self._form("/dev/usb/lp0"))
        assert not errors
        assert data["printer_device"] == "/dev/usb/lp0"

    def test_lp1_valid(self):
        data, errors = validate_save_input(self._form("/dev/usb/lp1"))
        assert not errors

    def test_ttyUSB0_valid(self):
        data, errors = validate_save_input(self._form("/dev/ttyUSB0"))
        assert not errors

    def test_ttyACM0_valid(self):
        data, errors = validate_save_input(self._form("/dev/ttyACM0"))
        assert not errors

    def test_rejects_path_traversal(self):
        _, errors = validate_save_input(self._form("/dev/../../etc/passwd"))
        assert len(errors) > 0

    def test_rejects_etc_passwd(self):
        _, errors = validate_save_input(self._form("/etc/passwd"))
        assert len(errors) > 0

    def test_rejects_dev_sda(self):
        _, errors = validate_save_input(self._form("/dev/sda"))
        assert len(errors) > 0

    def test_rejects_arbitrary_path(self):
        _, errors = validate_save_input(self._form("/tmp/evil"))
        assert len(errors) > 0

    def test_rejects_too_long_path(self):
        _, errors = validate_save_input(self._form("/dev/usb/lp" + "0" * 100))
        assert len(errors) > 0


# ─── Private Hostname Detection ─────────────────────────────────────────────


class TestPrivateHostname:
    def test_localhost_is_private(self):
        assert _is_private_hostname("localhost") is True

    def test_127_0_0_1_is_private(self):
        assert _is_private_hostname("127.0.0.1") is True

    def test_192_168_is_private(self):
        assert _is_private_hostname("192.168.1.1") is True

    def test_10_x_is_private(self):
        assert _is_private_hostname("10.0.0.1") is True

    def test_169_254_is_private(self):
        assert _is_private_hostname("169.254.169.254") is True

    def test_public_ip_is_not_private(self):
        assert _is_private_hostname("8.8.8.8") is False

    def test_domain_is_not_private(self):
        assert _is_private_hostname("example.com") is False

    def test_zero_addr_is_private(self):
        assert _is_private_hostname("0.0.0.0") is True


# ─── Quiet Hours Timezone Validation ────────────────────────────────────────


class TestQuietTzValidation:
    def _form(self, quiet_tz=""):
        return FakeForm(
            feeds="", interval="300", max_prints="3",
            theme="green", printer_device="/dev/usb/lp0",
            quiet_tz=quiet_tz,
        )

    def test_empty_string_accepted(self):
        data, errors = validate_save_input(self._form(""))
        assert not errors
        assert data["quiet_tz"] == ""

    def test_valid_iana_tz_accepted(self):
        data, errors = validate_save_input(self._form("America/New_York"))
        assert not errors
        assert data["quiet_tz"] == "America/New_York"

    def test_utc_accepted(self):
        data, errors = validate_save_input(self._form("UTC"))
        assert not errors
        assert data["quiet_tz"] == "UTC"

    def test_invalid_tz_rejected(self):
        _, errors = validate_save_input(self._form("Not/AReal_Zone"))
        assert any("timezone" in e.lower() for e in errors)

    def test_injection_attempt_rejected(self):
        _, errors = validate_save_input(self._form("<script>alert(1)</script>"))
        assert any("timezone" in e.lower() for e in errors)
