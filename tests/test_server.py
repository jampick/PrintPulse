"""Tests for the Pi web UI Flask routes."""

import sys
import os
from unittest.mock import patch

# Ensure pi/ is importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _make_client():
    """Create a Flask test client with auth bypassed and a valid session."""
    from pi.webapp.server import app
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    # Establish a session with a CSRF token and authentication
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["csrf_token"] = "testtoken"

    return client


class TestTestPrintRoute:
    def test_test_print_success(self):
        client = _make_client()
        with patch("printpulse.thermal.print_news_item", return_value=True) as mock_print:
            resp = client.post(
                "/test_print",
                data={"csrf_token": "testtoken"},
                content_type="application/x-www-form-urlencoded",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "success" in data["message"].lower()
        mock_print.assert_called_once()

    def test_test_print_printer_failure(self):
        client = _make_client()
        with patch("printpulse.thermal.print_news_item", return_value=False):
            resp = client.post(
                "/test_print",
                data={"csrf_token": "testtoken"},
                content_type="application/x-www-form-urlencoded",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert "failed" in data["message"].lower() or "check" in data["message"].lower()

    def test_test_print_sends_title_and_source(self):
        client = _make_client()
        with patch("printpulse.thermal.print_news_item", return_value=True) as mock_print:
            client.post(
                "/test_print",
                data={"csrf_token": "testtoken"},
                content_type="application/x-www-form-urlencoded",
            )
        call_kwargs = mock_print.call_args
        # Verify a meaningful title and source are passed
        assert call_kwargs is not None
        args, kwargs = call_kwargs
        title = kwargs.get("title") or (args[0] if args else "")
        source = kwargs.get("source") or (args[2] if len(args) > 2 else "")
        assert len(title) > 0
        assert len(source) > 0

    def test_test_print_requires_csrf(self):
        from pi.webapp.server import app
        app.config["TESTING"] = True
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["csrf_token"] = "realtoken"

        # Send wrong token — should be rejected with 403
        resp = client.post(
            "/test_print",
            data={"csrf_token": "wrongtoken"},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 403

    def test_test_print_requires_auth(self):
        from pi.webapp.server import app
        app.config["TESTING"] = True
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["csrf_token"] = "testtoken"
            # No 'authenticated' key

        with patch("pi.webapp.server._is_auth_configured", return_value=True):
            resp = client.post(
                "/test_print",
                data={"csrf_token": "testtoken"},
                content_type="application/x-www-form-urlencoded",
            )
        # Should redirect to login
        assert resp.status_code in (302, 403)
