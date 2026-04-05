"""WiFi provisioning routes for the PrintPulse captive portal.

These routes are registered as a Flask Blueprint and handle:
- GET /wifi         — Show available networks + connect form
- POST /wifi/connect — Attempt to join a WiFi network
- POST /wifi/reset  — Drop back to AP mode (from main web UI)
- GET /wifi/state   — JSON endpoint for current WiFi state
"""

from __future__ import annotations

import logging

from flask import Blueprint, render_template, request, redirect, jsonify, abort

logger = logging.getLogger("printpulse.wifi_routes")

wifi_bp = Blueprint("wifi", __name__)


def _require_auth_for_reset():
    """Check auth for the wifi reset endpoint (imported lazily to avoid circular imports)."""
    from pi.webapp.server import _is_auth_configured, _check_rate_limit
    from flask import session, redirect, url_for

    if _is_auth_configured() and not session.get("authenticated"):
        return redirect(url_for("login"))

    client_ip = request.remote_addr or "unknown"
    if _check_rate_limit(f"wifi_reset:{client_ip}"):
        abort(429)

    return None


def _get_provision_module():
    """Lazy import to keep things testable."""
    from pi.wifi_provision import (
        scan_wifi_networks,
        connect_to_wifi,
        start_ap_mode,
        get_current_state,
        validate_wifi_input,
    )
    return {
        "scan": scan_wifi_networks,
        "connect": connect_to_wifi,
        "start_ap": start_ap_mode,
        "state": get_current_state,
        "validate": validate_wifi_input,
    }


@wifi_bp.route("/wifi")
def wifi_setup():
    """Captive portal landing page — list networks."""
    prov = _get_provision_module()
    networks = prov["scan"]()
    return render_template("wifi_setup.html", networks=networks, error=None, success=None)


@wifi_bp.route("/wifi/connect", methods=["POST"])
def wifi_connect():
    """Handle WiFi credential submission from the captive portal."""
    prov = _get_provision_module()

    ssid = request.form.get("ssid", "").strip()
    password = request.form.get("password", "")

    errors = prov["validate"](ssid, password)
    if errors:
        networks = prov["scan"]()
        return render_template(
            "wifi_setup.html",
            networks=networks,
            error=" ".join(errors),
            success=None,
        )

    success, message = prov["connect"](ssid, password)

    if success:
        return render_template(
            "wifi_setup.html",
            networks=[],
            error=None,
            success=f"Connected to {ssid}! Connect to your home WiFi and visit printpulse.local:5000",
        )
    else:
        networks = prov["scan"]()
        return render_template(
            "wifi_setup.html",
            networks=networks,
            error=f"Failed to connect: {message}",
            success=None,
        )


@wifi_bp.route("/wifi/reset", methods=["POST"])
def wifi_reset():
    """Drop back to AP mode (called from the main web UI).

    Requires authentication since this is a destructive network operation.
    """
    auth_redirect = _require_auth_for_reset()
    if auth_redirect is not None:
        return auth_redirect

    prov = _get_provision_module()
    ok = prov["start_ap"]()
    if ok:
        return jsonify({"ok": True, "message": "AP mode activated. Connect to PrintPulse-Setup WiFi."})
    return jsonify({"ok": False, "message": "Failed to start AP mode."}), 500


@wifi_bp.route("/wifi/state")
def wifi_state():
    """JSON endpoint returning current WiFi provisioning state."""
    prov = _get_provision_module()
    return jsonify({"state": prov["state"]()})
