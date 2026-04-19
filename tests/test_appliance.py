"""Tests for pi.appliance module — config and credential management."""

import sys
import os

# Ensure pi/ is importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pi.appliance import (
    default_config,
    hash_password,
    verify_password,
    generate_secret_key,
)


class TestDefaultConfig:
    def test_has_required_keys(self):
        cfg = default_config()
        assert "feeds" in cfg
        assert "interval" in cfg
        assert "max_prints" in cfg
        assert "theme" in cfg
        assert "printer_device" in cfg
        assert "print_mode" in cfg

    def test_quiet_tz_defaults_to_empty_string(self):
        cfg = default_config()
        assert "quiet_tz" in cfg
        assert cfg["quiet_tz"] == ""

    def test_has_auth_fields(self):
        cfg = default_config()
        assert "auth_user" in cfg
        assert "auth_hash" in cfg
        assert "secret_key" in cfg

    def test_auth_fields_empty_by_default(self):
        cfg = default_config()
        assert cfg["auth_user"] == ""
        assert cfg["auth_hash"] == ""
        assert cfg["secret_key"] == ""

    def test_default_feed_is_https(self):
        cfg = default_config()
        for feed in cfg["feeds"]:
            assert feed.startswith("https://")

    def test_print_mode_default(self):
        cfg = default_config()
        assert cfg["print_mode"] == "scheduled"


class TestConfigMigration:
    """Test migration from legacy enabled/quiet_enabled to print_mode."""

    def test_legacy_disabled_migrates_to_off(self, tmp_path, monkeypatch):
        import json
        from pi import appliance
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"enabled": False, "quiet_enabled": True}))
        monkeypatch.setattr(appliance, "CONFIG_PATH", str(cfg_path))
        cfg = appliance.load_config()
        assert cfg["print_mode"] == "off"
        assert "enabled" not in cfg
        assert "quiet_enabled" not in cfg

    def test_legacy_enabled_quiet_on_migrates_to_scheduled(self, tmp_path, monkeypatch):
        import json
        from pi import appliance
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"enabled": True, "quiet_enabled": True}))
        monkeypatch.setattr(appliance, "CONFIG_PATH", str(cfg_path))
        cfg = appliance.load_config()
        assert cfg["print_mode"] == "scheduled"

    def test_legacy_enabled_quiet_off_migrates_to_on(self, tmp_path, monkeypatch):
        import json
        from pi import appliance
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"enabled": True, "quiet_enabled": False}))
        monkeypatch.setattr(appliance, "CONFIG_PATH", str(cfg_path))
        cfg = appliance.load_config()
        assert cfg["print_mode"] == "on"

    def test_new_config_no_migration(self, tmp_path, monkeypatch):
        import json
        from pi import appliance
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"print_mode": "off"}))
        monkeypatch.setattr(appliance, "CONFIG_PATH", str(cfg_path))
        cfg = appliance.load_config()
        assert cfg["print_mode"] == "off"


class TestPasswordHashing:
    def test_hash_produces_pbkdf2_format(self):
        result = hash_password("test123")
        assert result.startswith("pbkdf2:")
        parts = result.split(":")
        assert len(parts) == 4  # pbkdf2:iterations:salt:hash
        assert parts[0] == "pbkdf2"
        assert int(parts[1]) >= 600_000
        assert len(parts[2]) == 32  # 16 bytes hex = 32 chars
        assert len(parts[3]) == 64  # SHA-256 hex = 64 chars

    def test_verify_correct_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_empty_hash(self):
        assert verify_password("test", "") is False

    def test_verify_malformed_hash(self):
        assert verify_password("test", "nocolonhere") is False

    def test_different_hashes_for_same_password(self):
        # Salt should make each hash unique
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_both_still_verify(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert verify_password("same", h1) is True
        assert verify_password("same", h2) is True

    def test_legacy_sha256_format_still_verifies(self):
        """Existing configs with old SHA-256 hashes should still work."""
        import hashlib
        import secrets as _secrets
        salt = _secrets.token_hex(16)
        h = hashlib.sha256(f"{salt}:legacypass".encode()).hexdigest()
        legacy_hash = f"{salt}:{h}"
        assert verify_password("legacypass", legacy_hash) is True
        assert verify_password("wrongpass", legacy_hash) is False


class TestSecretKey:
    def test_generates_string(self):
        key = generate_secret_key()
        assert isinstance(key, str)
        assert len(key) == 64  # 32 bytes hex = 64 chars

    def test_unique_each_time(self):
        k1 = generate_secret_key()
        k2 = generate_secret_key()
        assert k1 != k2
