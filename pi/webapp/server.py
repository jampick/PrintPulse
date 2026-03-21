"""PrintPulse Appliance — Web Configuration UI.

A lightweight Flask app that lets you configure the PrintPulse
news watcher from any device on your local network.

Access at http://<pi-ip>:5000

Security features:
- Basic authentication (username/password set during setup)
- CSRF tokens on all forms
- Security headers (CSP, X-Frame-Options, etc.)
- Rate limiting on sensitive endpoints
- Input validation on all user-submitted data
"""

import functools
import ipaddress
import os
import re
import secrets
import subprocess
import sys
import time
from urllib.parse import urlparse

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from flask import (
    Flask, render_template, request, redirect, url_for, jsonify,
    session, abort, g,
)
from pi.appliance import load_config, save_config, verify_password

app = Flask(__name__)

# Load secret key from config (generated during setup)
_cfg = load_config()
app.secret_key = _cfg.get("secret_key") or secrets.token_hex(32)


# ─── Rate Limiting ──────────────────────────────────────────────────────────

_rate_limit_store: dict[str, list[float]] = {}
RATE_LIMIT_MAX = 10       # max requests
RATE_LIMIT_WINDOW = 60    # per 60 seconds


def _check_rate_limit(key: str) -> bool:
    """Return True if rate limit exceeded."""
    now = time.time()
    if key not in _rate_limit_store:
        _rate_limit_store[key] = []

    # Remove old entries outside the window
    _rate_limit_store[key] = [
        t for t in _rate_limit_store[key] if now - t < RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_store[key]) >= RATE_LIMIT_MAX:
        return True

    _rate_limit_store[key].append(now)
    return False


# ─── Authentication ─────────────────────────────────────────────────────────

def _is_auth_configured() -> bool:
    """Check if authentication credentials are set."""
    cfg = load_config()
    return bool(cfg.get("auth_user")) and bool(cfg.get("auth_hash"))


def require_auth(f):
    """Decorator: require login for protected routes."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _is_auth_configured():
            # No auth configured — allow access (first-run scenario)
            return f(*args, **kwargs)

        if not session.get("authenticated"):
            return redirect(url_for("login"))

        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        client_ip = request.remote_addr or "unknown"
        if _check_rate_limit(f"login:{client_ip}"):
            error = "Too many attempts. Try again in a minute."
        else:
            cfg = load_config()
            username = request.form.get("username", "")
            password = request.form.get("password", "")

            if (username == cfg.get("auth_user", "")
                    and verify_password(password, cfg.get("auth_hash", ""))):
                session["authenticated"] = True
                return redirect(url_for("index"))
            else:
                error = "Invalid credentials."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))


# ─── CSRF Protection ────────────────────────────────────────────────────────

@app.before_request
def _csrf_protect():
    """Validate CSRF token on all POST requests."""
    if request.method == "POST":
        token = session.get("csrf_token")
        form_token = request.form.get("csrf_token")
        if not token or not form_token or not secrets.compare_digest(token, form_token):
            abort(403)


def _generate_csrf_token() -> str:
    """Generate and store a CSRF token in the session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


# Make csrf_token available in all templates
app.jinja_env.globals["csrf_token"] = _generate_csrf_token


# ─── Security Headers ───────────────────────────────────────────────────────

@app.after_request
def _add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline';"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ─── Input Validation ────────────────────────────────────────────────────────

# Allowed printer device patterns (whitelist)
_DEVICE_PATTERN = re.compile(r"^/dev/(usb/lp|ttyUSB|ttyACM)\d+$")

# Allowed themes
_VALID_THEMES = {"green", "amber"}

# Feed limits
_MAX_FEEDS = 20
_MAX_FEED_URL_LEN = 2048

# Private/reserved IP ranges to block in feed URLs (SSRF prevention)
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_hostname(hostname: str) -> bool:
    """Check if a hostname resolves to a private/reserved IP."""
    # Block obvious localhost aliases
    if hostname.lower() in ("localhost", "localhost.localdomain", "0.0.0.0"):
        return True

    # Check if hostname is a raw IP address in a private range
    try:
        addr = ipaddress.ip_address(hostname)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        pass  # Not a raw IP, could be a domain name — allow it

    return False


def validate_save_input(form) -> tuple[dict | None, list[str]]:
    """Validate all fields from the /save form.

    Returns (parsed_data, errors) where parsed_data is None if
    there are validation errors.
    """
    errors: list[str] = []

    # --- Feeds ---
    feeds_raw = form.get("feeds", "").strip()
    feeds = [f.strip() for f in feeds_raw.splitlines() if f.strip()]

    if len(feeds) > _MAX_FEEDS:
        errors.append(f"Too many feeds (max {_MAX_FEEDS}).")
        feeds = feeds[:_MAX_FEEDS]

    validated_feeds = []
    for url in feeds:
        if len(url) > _MAX_FEED_URL_LEN:
            errors.append(f"Feed URL too long (max {_MAX_FEED_URL_LEN} chars): {url[:60]}...")
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            errors.append(f"Feed URL must use http:// or https://: {url[:60]}")
            continue
        if not parsed.hostname:
            errors.append(f"Feed URL has no hostname: {url[:60]}")
            continue
        if _is_private_hostname(parsed.hostname):
            errors.append(f"Feed URL points to a private/local address: {url[:60]}")
            continue
        validated_feeds.append(url)

    # --- Interval ---
    try:
        interval = int(form.get("interval", 300))
    except (ValueError, TypeError):
        errors.append("Poll interval must be a number.")
        interval = 300

    if interval < 60:
        errors.append("Poll interval must be at least 60 seconds.")
        interval = 60
    elif interval > 3600:
        errors.append("Poll interval must be at most 3600 seconds.")
        interval = 3600

    # --- Max prints ---
    try:
        max_prints = int(form.get("max_prints", 3))
    except (ValueError, TypeError):
        errors.append("Max prints must be a number.")
        max_prints = 3

    if max_prints < 1:
        errors.append("Max prints must be at least 1.")
        max_prints = 1
    elif max_prints > 20:
        errors.append("Max prints must be at most 20.")
        max_prints = 20

    # --- Theme ---
    theme = form.get("theme", "green")
    if theme not in _VALID_THEMES:
        errors.append(f"Invalid theme. Must be one of: {', '.join(sorted(_VALID_THEMES))}.")
        theme = "green"

    # --- Printer device ---
    printer_device = form.get("printer_device", "/dev/usb/lp0").strip()
    if len(printer_device) > 64:
        errors.append("Printer device path too long.")
        printer_device = "/dev/usb/lp0"
    elif not _DEVICE_PATTERN.match(printer_device):
        errors.append(
            "Invalid printer device. Must match /dev/usb/lp*, "
            "/dev/ttyUSB*, or /dev/ttyACM*."
        )
        printer_device = "/dev/usb/lp0"

    if errors:
        return None, errors

    return {
        "feeds": validated_feeds,
        "interval": interval,
        "max_prints": max_prints,
        "theme": theme,
        "printer_device": printer_device,
    }, []


# ─── Service Helpers ─────────────────────────────────────────────────────────

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


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
@require_auth
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
        errors=[],
    )


@app.route("/save", methods=["POST"])
@require_auth
def save():
    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"save:{client_ip}"):
        abort(429)

    validated, errors = validate_save_input(request.form)

    if errors:
        # Re-render the page with error messages and submitted values
        config = load_config()
        status = _service_status()
        printer_ok = _printer_detected()
        return render_template(
            "index.html",
            config=config,
            status=status,
            printer_ok=printer_ok,
            feeds_text=request.form.get("feeds", ""),
            errors=errors,
        )

    config = load_config()
    config["feeds"] = validated["feeds"]
    config["interval"] = validated["interval"]
    config["max_prints"] = validated["max_prints"]
    config["theme"] = validated["theme"]
    config["printer_device"] = validated["printer_device"]
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
@require_auth
def start():
    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"control:{client_ip}"):
        abort(429)

    try:
        subprocess.run(["sudo", "systemctl", "start", "printpulse"], timeout=10)
    except Exception:
        pass
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
@require_auth
def stop():
    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"control:{client_ip}"):
        abort(429)

    try:
        subprocess.run(["sudo", "systemctl", "stop", "printpulse"], timeout=10)
    except Exception:
        pass
    return redirect(url_for("index"))


@app.route("/status")
@require_auth
def status_api():
    """JSON endpoint for live status polling."""
    return jsonify({
        "service": _service_status(),
        "printer": _printer_detected(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
