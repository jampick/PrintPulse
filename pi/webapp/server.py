"""PrintPulse Appliance — Web Configuration UI.

A lightweight Flask app that lets you configure the PrintPulse
news watcher from any device on your local network.

Access at http://<pi-ip>:5000

Security features:
- Basic authentication (username/password set during setup)
- CSRF tokens on all forms
- Security headers (CSP, X-Frame-Options, etc.)
- Rate limiting on sensitive endpoints
"""

import functools
import os
import secrets
import subprocess
import sys
import time

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
    )


@app.route("/save", methods=["POST"])
@require_auth
def save():
    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"save:{client_ip}"):
        abort(429)

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
