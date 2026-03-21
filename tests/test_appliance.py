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
        assert "enabled" in cfg

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


class TestPasswordHashing:
    def test_hash_produces_salt_colon_hash(self):
        result = hash_password("test123")
        assert ":" in result
        parts = result.split(":", 1)
        assert len(parts) == 2
        assert len(parts[0]) == 32  # 16 bytes hex = 32 chars
        assert len(parts[1]) == 64  # SHA-256 hex = 64 chars

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


class TestSecretKey:
    def test_generates_string(self):
        key = generate_secret_key()
        assert isinstance(key, str)
        assert len(key) == 64  # 32 bytes hex = 64 chars

    def test_unique_each_time(self):
        k1 = generate_secret_key()
        k2 = generate_secret_key()
        assert k1 != k2
