"""PrintPulse Appliance — Web Configuration UI.

A lightweight Flask app that lets you configure the PrintPulse
news watcher from any device on your local network.

Access at http://<pi-ip>:5000
"""

import os
import subprocess
import sys

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from flask import Flask, render_template, request, redirect, url_for, jsonify
from pi.appliance import load_config, save_config

app = Flask(__name__)


def _service_status() -> str:
    """Get the systemd service status (active/inactive/failed)."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "printpulse"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _printer_detected() -> bool:
    """Check if the thermal printer USB device exists."""
    config = load_config()
    device = config.get("printer_device", "/dev/usb/lp0")
    return os.path.exists(device)


@app.route("/")
def index():
    config = load_config()
    status = _service_status()
    printer_ok = _printer_detected()
    return render_template(
        "index.html",
        config=config,
        status=status,
        printer_ok=printer_ok,
        feeds_text="\n".join(config.get("feeds", [])),
    )


@app.route("/save", methods=["POST"])
def save():
    feeds_raw = request.form.get("feeds", "").strip()
    feeds = [f.strip() for f in feeds_raw.splitlines() if f.strip()]

    config = load_config()
    config["feeds"] = feeds
    config["interval"] = int(request.form.get("interval", 300))
    config["max_prints"] = int(request.form.get("max_prints", 3))
    config["theme"] = request.form.get("theme", "green")
    config["printer_device"] = request.form.get("printer_device", "/dev/usb/lp0")
    save_config(config)

    # Restart the watcher service to pick up new config
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", "printpulse"],
            timeout=10,
        )
    except Exception:
        pass

    return redirect(url_for("index"))


@app.route("/start", methods=["POST"])
def start():
    try:
        subprocess.run(["sudo", "systemctl", "start", "printpulse"], timeout=10)
    except Exception:
        pass
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
def stop():
    try:
        subprocess.run(["sudo", "systemctl", "stop", "printpulse"], timeout=10)
    except Exception:
        pass
    return redirect(url_for("index"))


@app.route("/status")
def status_api():
    """JSON endpoint for live status polling."""
    return jsonify({
        "service": _service_status(),
        "printer": _printer_detected(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
