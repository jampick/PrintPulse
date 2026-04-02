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
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

logger = logging.getLogger("printpulse.webapp")

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

# Register WiFi provisioning routes
from pi.webapp.wifi_routes import wifi_bp
app.register_blueprint(wifi_bp)


# ─── Timezone Info ─────────────────────────────────────────────────────────

def _get_system_timezone() -> str:
    """Get a human-readable system timezone string."""
    try:
        from datetime import datetime, timezone
        local_tz = datetime.now().astimezone().tzinfo
        offset = datetime.now().astimezone().strftime("%z")
        # Format as e.g. "PDT (UTC-0700)"
        tz_name = datetime.now().astimezone().strftime("%Z")
        return f"{tz_name} (UTC{offset[:3]}:{offset[3:]})"
    except Exception:
        return "unknown"


# ─── Version Info ──────────────────────────────────────────────────────────

def _get_version_info() -> str:
    """Get version string from pyproject.toml + git short hash."""
    version = "unknown"
    try:
        toml_path = os.path.join(_project_root, "pyproject.toml")
        with open(toml_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("version"):
                    version = line.split("=")[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass

    # Append git short hash
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=_project_root,
        )
        if result.returncode == 0:
            version += f"+{result.stdout.strip()}"
    except Exception:
        pass

    return version


_APP_VERSION = _get_version_info()

# Load secret key from config (generated during setup)
_cfg = load_config()
app.secret_key = _cfg.get("secret_key") or secrets.token_hex(32)


# ─── Auto-Update ────────────────────────────────────────────────────────────

_UPDATE_LOG_FILE = os.path.join(os.path.expanduser("~"), ".printpulse_update_log.json")
_UPDATE_LOG_MAX = 50

# In-memory record of the most recent auto-update attempt
_auto_update_state: dict = {
    "last_check": None,   # ISO timestamp of last check
    "last_result": None,  # human-readable result string
    "last_changed": False,  # whether git pull fetched new commits
}


def _load_update_log() -> list[dict]:
    """Load auto-update log from disk."""
    if os.path.isfile(_UPDATE_LOG_FILE):
        try:
            with open(_UPDATE_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _append_update_log(result: str, changed: bool, *,
                       status: str = "", description: str = ""):
    """Append one entry to the update log and trim to max size.

    status: "up_to_date", "updated", or "error"
    description: brief summary of what changed (commit subjects) or error detail
    """
    from datetime import datetime
    log = _load_update_log()
    log.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"),
        "result": result,
        "changed": changed,
        "status": status or ("updated" if changed else "up_to_date"),
        "description": description,
    })
    if len(log) > _UPDATE_LOG_MAX:
        log = log[-_UPDATE_LOG_MAX:]
    try:
        from printpulse.secure_fs import secure_write_json
        secure_write_json(_UPDATE_LOG_FILE, log)
    except Exception as exc:
        logger.warning("Could not write update log: %s", exc)


def _run_auto_update() -> tuple[str, bool, str, str]:
    """Run git pull and, if new commits landed, restart services.

    Returns (result_message, changed, status, description) where:
    - changed is True if git pull fetched new commits
    - status is "up_to_date", "updated", or "error"
    - description is a brief summary of what changed or error detail
    """
    global _APP_VERSION

    # Git pull
    try:
        result = subprocess.run(
            ["git", "-C", _project_root, "pull", "--ff-only"],
            capture_output=True, text=True, timeout=30,
        )
        pull_output = (result.stdout.strip() or result.stderr.strip()
                       or "no output")
        logger.info("Auto-update git pull: %s", pull_output)
    except (OSError, subprocess.TimeoutExpired) as exc:
        msg = f"git pull failed: {type(exc).__name__}"
        logger.error("Auto-update %s", msg)
        return msg, False, "error", str(exc)

    changed = "already up to date" not in pull_output.lower()

    if not changed:
        return "Already up to date.", False, "up_to_date", ""

    # Capture commit summaries for the description
    description = ""
    try:
        log_result = subprocess.run(
            ["git", "-C", _project_root, "log", "--oneline", "-5", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if log_result.returncode == 0 and log_result.stdout.strip():
            # Take just the subject lines (drop the hash prefix)
            subjects = []
            for line in log_result.stdout.strip().splitlines()[:5]:
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    subjects.append(parts[1])
            description = "; ".join(subjects) if subjects else pull_output
    except Exception:
        description = pull_output

    # New commits — restart services
    msgs = [f"git pull: {pull_output}"]
    try:
        subprocess.run(["sudo", "systemctl", "restart", "printpulse"], timeout=10)
        msgs.append("printpulse: restarted")
        logger.info("Auto-update restarted printpulse")
    except (OSError, subprocess.TimeoutExpired) as exc:
        msgs.append(f"printpulse: restart failed ({type(exc).__name__})")
        logger.error("Auto-update failed to restart printpulse: %s", exc)

    # Refresh in-process version string before restarting the web service
    _APP_VERSION = _get_version_info()

    # Restart printpulse-web last (kills this process — use Popen so we don't block)
    try:
        subprocess.Popen(["sudo", "systemctl", "restart", "printpulse-web"])
        msgs.append("printpulse-web: restarting")
        logger.info("Auto-update triggered printpulse-web restart")
    except OSError as exc:
        msgs.append(f"printpulse-web: restart failed ({type(exc).__name__})")
        logger.error("Auto-update failed to restart printpulse-web: %s", exc)

    return " | ".join(msgs), True, "updated", description


def _auto_update_worker():
    """Daemon thread: check for code updates on the configured schedule."""
    # Record startup time as the baseline so we don't update immediately
    last_check_at = time.time()

    while True:
        time.sleep(60)  # Wake up every minute to re-read config
        try:
            cfg = load_config()
            if not cfg.get("auto_update_enabled", False):
                continue
            interval_sec = int(cfg.get("auto_update_interval", 24)) * 3600
            now = time.time()
            if now - last_check_at < interval_sec:
                continue

            last_check_at = now
            from datetime import datetime
            check_ts = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
            logger.info("Auto-update: running scheduled check")

            result_msg, changed, status, description = _run_auto_update()

            _auto_update_state["last_check"] = check_ts
            _auto_update_state["last_result"] = result_msg
            _auto_update_state["last_changed"] = changed
            _append_update_log(result_msg, changed,
                               status=status, description=description)
        except Exception as exc:
            logger.error("Auto-update worker error: %s", exc)


# Start the background auto-update thread
_update_thread = threading.Thread(target=_auto_update_worker, daemon=True, name="auto-updater")
_update_thread.start()


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

    theme = load_config().get("theme", "green")
    return render_template("login.html", error=error, theme=theme)


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

    # --- Quiet hours ---
    quiet_enabled = form.get("quiet_enabled") == "1"

    quiet_start = form.get("quiet_start", "22:00").strip()
    quiet_end = form.get("quiet_end", "08:00").strip()
    _time_re = re.compile(r"^\d{2}:\d{2}$")
    for label, val in [("Quiet start", quiet_start), ("Quiet end", quiet_end)]:
        if not _time_re.match(val):
            errors.append(f"{label} must be in HH:MM format.")
        else:
            hh, mm = int(val[:2]), int(val[3:5])
            if hh > 23 or mm > 59:
                errors.append(f"{label} is not a valid time.")

    quiet_wake_mode = form.get("quiet_wake_mode", "latest")
    if quiet_wake_mode not in ("latest", "all"):
        errors.append("Quiet wake mode must be 'latest' or 'all'.")
        quiet_wake_mode = "latest"

    # --- Auto-update ---
    auto_update_enabled = form.get("auto_update_enabled") == "1"
    _valid_intervals = {1, 6, 12, 24}
    try:
        auto_update_interval = int(form.get("auto_update_interval", 24))
    except (ValueError, TypeError):
        errors.append("Auto-update interval must be a number.")
        auto_update_interval = 24
    if auto_update_interval not in _valid_intervals:
        errors.append(
            f"Auto-update interval must be one of: {', '.join(str(v) for v in sorted(_valid_intervals))} hours."
        )
        auto_update_interval = 24

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
        "quiet_enabled": quiet_enabled,
        "quiet_start": quiet_start,
        "quiet_end": quiet_end,
        "quiet_wake_mode": quiet_wake_mode,
        "auto_update_enabled": auto_update_enabled,
        "auto_update_interval": auto_update_interval,
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
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Failed to check service status: %s", type(exc).__name__)
        return "unknown"


def _printer_detected() -> bool:
    """Check if the thermal printer USB device exists."""
    config = load_config()
    device = config.get("printer_device", "/dev/usb/lp0")
    return os.path.exists(device)


def _quiet_hours_active() -> dict:
    """Check if quiet hours are currently active.

    Returns dict with 'enabled', 'active', 'start', 'end' keys.
    """
    from datetime import datetime, time as dtime

    config = load_config()
    enabled = config.get("quiet_enabled", False)
    start_str = config.get("quiet_start", "22:00")
    end_str = config.get("quiet_end", "08:00")

    if not enabled:
        return {"enabled": False, "active": False, "start": start_str, "end": end_str}

    now = datetime.now().time()
    start_h, start_m = int(start_str[:2]), int(start_str[3:5])
    end_h, end_m = int(end_str[:2]), int(end_str[3:5])
    start = dtime(start_h, start_m)
    end = dtime(end_h, end_m)

    if start <= end:
        active = start <= now < end
    else:
        active = now >= start or now < end

    return {"enabled": True, "active": active, "start": start_str, "end": end_str}


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
@require_auth
def index():
    config = load_config()
    status = _service_status()
    printer_ok = _printer_detected()
    quiet_hours = _quiet_hours_active()
    return render_template(
        "index.html",
        config=config,
        status=status,
        printer_ok=printer_ok,
        quiet_hours=quiet_hours,
        feeds_text="\n".join(config.get("feeds", [])),
        errors=[],
        version=_APP_VERSION,
        timezone=_get_system_timezone(),
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
            version=_APP_VERSION,
            timezone=_get_system_timezone(),
        )

    config = load_config()
    config["feeds"] = validated["feeds"]
    config["interval"] = validated["interval"]
    config["max_prints"] = validated["max_prints"]
    config["theme"] = validated["theme"]
    config["printer_device"] = validated["printer_device"]
    config["quiet_enabled"] = validated["quiet_enabled"]
    config["quiet_start"] = validated["quiet_start"]
    config["quiet_end"] = validated["quiet_end"]
    config["quiet_wake_mode"] = validated["quiet_wake_mode"]
    config["auto_update_enabled"] = validated["auto_update_enabled"]
    config["auto_update_interval"] = validated["auto_update_interval"]
    save_config(config)

    # Restart the watcher service to pick up new config
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", "printpulse"],
            timeout=10,
        )
        logger.info("Config saved and watcher service restarted.")
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("Failed to restart watcher service: %s", type(exc).__name__)

    return redirect(url_for("index"))


@app.route("/start", methods=["POST"])
@require_auth
def start():
    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"control:{client_ip}"):
        abort(429)

    try:
        subprocess.run(["sudo", "systemctl", "start", "printpulse"], timeout=10)
        logger.info("Watcher service started.")
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("Failed to start watcher service: %s", type(exc).__name__)
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
@require_auth
def stop():
    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"control:{client_ip}"):
        abort(429)

    try:
        subprocess.run(["sudo", "systemctl", "stop", "printpulse"], timeout=10)
        logger.info("Watcher service stopped.")
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("Failed to stop watcher service: %s", type(exc).__name__)
    return redirect(url_for("index"))


@app.route("/update", methods=["POST"])
@require_auth
def update():
    """Pull latest code from GitHub and restart services."""
    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"update:{client_ip}"):
        abort(429)

    results = []

    # Git pull
    try:
        result = subprocess.run(
            ["git", "-C", _project_root, "pull", "--ff-only"],
            capture_output=True, text=True, timeout=30,
        )
        pull_output = result.stdout.strip()
        if result.returncode != 0:
            pull_output = result.stderr.strip() or "git pull failed"
        results.append(f"git pull: {pull_output}")
        logger.info("Update git pull: %s", pull_output)
    except (OSError, subprocess.TimeoutExpired) as exc:
        results.append(f"git pull failed: {type(exc).__name__}")
        logger.error("Update git pull failed: %s", type(exc).__name__)

    # Restart services
    for svc in ["printpulse", "printpulse-web"]:
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", svc],
                timeout=10,
            )
            results.append(f"{svc}: restarted")
            logger.info("Update restarted %s", svc)
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append(f"{svc}: restart failed ({type(exc).__name__})")
            logger.error("Update failed to restart %s: %s", svc, type(exc).__name__)

    # Refresh version after update
    global _APP_VERSION
    _APP_VERSION = _get_version_info()

    return redirect(url_for("index"))


@app.route("/history")
@require_auth
def history():
    """Show print history page."""
    from printpulse.watch import load_history
    items = load_history()
    items.reverse()  # newest first
    total = len(items)
    items = items[:10]  # cap to 10 most recent for mobile performance
    config = load_config()
    return render_template(
        "history.html",
        items=items,
        total=total,
        config=config,
        version=_APP_VERSION,
    )


@app.route("/test_print", methods=["POST"])
@require_auth
def test_print():
    """Send a test news story to the thermal printer."""
    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"test_print:{client_ip}"):
        return jsonify({"ok": False, "message": "Rate limit exceeded. Try again shortly."}), 429

    from datetime import datetime
    from printpulse.thermal import print_news_item

    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    ok = print_news_item(
        title="PrintPulse Test Print",
        summary=(
            "This is a test print from the PrintPulse web UI. "
            "If you can read this, your thermal printer is working correctly."
        ),
        source="PrintPulse Appliance",
        timestamp=timestamp,
    )
    logger.info("Test print requested: %s", "success" if ok else "failed")
    if ok:
        return jsonify({"ok": True, "message": "Test print sent successfully."})
    return jsonify({"ok": False, "message": "Print failed — check printer connection."})


@app.route("/status")
@require_auth
def status_api():
    """JSON endpoint for live status polling."""
    return jsonify({
        "service": _service_status(),
        "printer": _printer_detected(),
        "auto_update": _auto_update_state.copy(),
        "quiet_hours": _quiet_hours_active(),
    })


@app.route("/update_log")
@require_auth
def update_log():
    """Show auto-update log page."""
    items = _load_update_log()
    items = list(reversed(items))  # newest first
    config = load_config()
    return render_template(
        "update_log.html",
        items=items,
        config=config,
        version=_APP_VERSION,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
