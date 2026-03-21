"""PrintPulse Appliance configuration for Raspberry Pi.

Reads and writes ~/.printpulse_appliance.json — the bridge between
the Flask web UI and the systemd watch service.
"""

import json
import os

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
        "enabled": True,
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
    """Write appliance config to disk."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
