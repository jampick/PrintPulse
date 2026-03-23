"""PrintPulse Appliance configuration for Raspberry Pi.

Reads and writes ~/.printpulse_appliance.json — the bridge between
the Flask web UI and the systemd watch service.
"""

import hashlib
import json
import os
import secrets

from printpulse.secure_fs import secure_write_json

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
    """Hash a password with a random salt using SHA-256.

    Returns 'salt:hash' string for storage.
    """
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored 'salt:hash' string."""
    if ":" not in stored_hash:
        return False
    salt, expected = stored_hash.split(":", 1)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return secrets.compare_digest(h, expected)


def generate_secret_key() -> str:
    """Generate a random secret key for Flask sessions/CSRF."""
    return secrets.token_hex(32)
