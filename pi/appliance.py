"""PrintPulse Appliance configuration for Raspberry Pi.

Reads and writes ~/.printpulse_appliance.json — the bridge between
the Flask web UI and the systemd watch service.
"""

import hashlib
import json
import os
import secrets

from printpulse.secure_fs import secure_write_json

# PBKDF2 iterations — OWASP 2023 recommends >= 600,000 for SHA-256
_PBKDF2_ITERATIONS = 600_000

CONFIG_PATH = os.path.expanduser("~/.printpulse_appliance.json")


def default_config() -> dict:
    """Return the default appliance configuration."""
    return {
        "feeds": [
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        ],
        "interval": 300,
        "max_prints": 3,
        "theme": "green",
        "printer_device": "/dev/usb/lp0",
        "quiet_enabled": True,
        "quiet_start": "22:00",
        "quiet_end": "08:00",
        "quiet_wake_mode": "latest",
        "enabled": True,
        "auth_user": "",
        "auth_hash": "",
        "secret_key": "",
        "auto_update_enabled": False,
        "auto_update_interval": 24,  # hours between checks (1, 6, 12, or 24)
    }


def load_config() -> dict:
    """Load appliance config from disk, falling back to defaults."""
    defaults = default_config()
    if not os.path.isfile(CONFIG_PATH):
        return defaults
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        # Merge saved values over defaults so new keys get defaults
        merged = {**defaults, **saved}
        return merged
    except Exception:
        return defaults


def save_config(data: dict) -> None:
    """Write appliance config to disk with secure permissions."""
    secure_write_json(CONFIG_PATH, data)


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt.

    Returns 'pbkdf2:iterations:salt:hash' string for storage.
    Previous format ('salt:sha256hash') is still accepted by verify_password
    for backward compatibility, but new hashes always use PBKDF2.
    """
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2:{_PBKDF2_ITERATIONS}:{salt}:{h}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash string.

    Supports both the new PBKDF2 format ('pbkdf2:iterations:salt:hash')
    and the legacy SHA-256 format ('salt:sha256hash') for backward
    compatibility with existing config files.
    """
    if not stored_hash or ":" not in stored_hash:
        return False

    if stored_hash.startswith("pbkdf2:"):
        # New PBKDF2 format
        parts = stored_hash.split(":", 3)
        if len(parts) != 4:
            return False
        _, iterations_str, salt, expected = parts
        try:
            iterations = int(iterations_str)
        except ValueError:
            return False
        h = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), iterations,
        ).hex()
        return secrets.compare_digest(h, expected)
    else:
        # Legacy SHA-256 format for backward compatibility
        salt, expected = stored_hash.split(":", 1)
        h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return secrets.compare_digest(h, expected)


def generate_secret_key() -> str:
    """Generate a random secret key for Flask sessions/CSRF."""
    return secrets.token_hex(32)
