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


class TestAutoUpdateValidation:
    """Test validate_save_input() for auto-update fields."""

    def _base_form(self, **overrides):
        data = {
            "feeds": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "interval": "300",
            "max_prints": "3",
            "theme": "green",
            "printer_device": "/dev/usb/lp0",
            "print_mode": "scheduled",
            "quiet_start": "22:00",
            "quiet_end": "08:00",
            "auto_update_enabled": "",
            "auto_update_interval": "24",
        }
        data.update(overrides)
        return data

    def test_auto_update_disabled_by_default(self):
        from pi.webapp.server import validate_save_input
        validated, errors = validate_save_input(self._base_form())
        assert errors == []
        assert validated["auto_update_enabled"] is False

    def test_auto_update_enabled_flag(self):
        from pi.webapp.server import validate_save_input
        validated, errors = validate_save_input(self._base_form(auto_update_enabled="1"))
        assert errors == []
        assert validated["auto_update_enabled"] is True

    def test_auto_update_interval_valid_values(self):
        from pi.webapp.server import validate_save_input
        for hours in [1, 6, 12, 24]:
            validated, errors = validate_save_input(
                self._base_form(auto_update_interval=str(hours))
            )
            assert errors == [], f"Unexpected errors for interval={hours}: {errors}"
            assert validated["auto_update_interval"] == hours

    def test_auto_update_interval_invalid_value(self):
        from pi.webapp.server import validate_save_input
        _, errors = validate_save_input(self._base_form(auto_update_interval="7"))
        assert any("interval" in e.lower() for e in errors)

    def test_auto_update_interval_non_numeric(self):
        from pi.webapp.server import validate_save_input
        _, errors = validate_save_input(self._base_form(auto_update_interval="daily"))
        assert any("number" in e.lower() or "interval" in e.lower() for e in errors)

    def test_auto_update_interval_returns_error_on_bad_input(self):
        from pi.webapp.server import validate_save_input
        validated, errors = validate_save_input(self._base_form(auto_update_interval="999"))
        assert validated is None
        assert any("interval" in e.lower() for e in errors)


class TestAutoUpdateRoutes:
    """Test /status includes auto_update and /update_log renders."""

    def test_status_includes_auto_update_key(self):
        client = _make_client()
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "auto_update" in data
        assert "last_check" in data["auto_update"]
        assert "last_result" in data["auto_update"]

    def test_update_log_renders(self):
        client = _make_client()
        with patch("pi.webapp.server._load_update_log", return_value=[]):
            resp = client.get("/update_log")
        assert resp.status_code == 200
        assert b"UPDATE" in resp.data

    def test_update_log_backward_compat_old_entries(self):
        """Old log entries without status/description should render gracefully."""
        client = _make_client()
        old_entry = {"timestamp": "2026-03-20 09:00:00 AM", "result": "Already up to date.", "changed": False}
        with patch("pi.webapp.server._load_update_log", return_value=[old_entry]):
            resp = client.get("/update_log")
        assert resp.status_code == 200
        assert b"No changes" in resp.data

    def test_update_log_shows_entries(self):
        client = _make_client()
        fake_log = [
            {"timestamp": "2026-03-23 10:00:00 AM", "result": "Already up to date.",
             "changed": False, "status": "up_to_date", "description": ""},
            {"timestamp": "2026-03-23 11:00:00 AM", "result": "git pull: 1 file changed",
             "changed": True, "status": "updated", "description": "feat: add new feature"},
        ]
        with patch("pi.webapp.server._load_update_log", return_value=fake_log):
            resp = client.get("/update_log")
        assert resp.status_code == 200
        assert b"No changes" in resp.data
        assert b"Updated" in resp.data
        assert b"feat: add new feature" in resp.data


class TestRunAutoUpdate:
    """Test _run_auto_update logic for changed vs unchanged."""

    def test_already_up_to_date(self):
        from pi.webapp.server import _run_auto_update
        mock_result = type("R", (), {"returncode": 0, "stdout": "Already up to date.\n", "stderr": ""})()
        with patch("subprocess.run", return_value=mock_result):
            msg, changed, status, description = _run_auto_update()
        assert changed is False
        assert status == "up_to_date"
        assert "up to date" in msg.lower()

    def test_new_commits_triggers_restart(self):
        from pi.webapp.server import _run_auto_update
        pull_result = type("R", (), {
            "returncode": 0,
            "stdout": "Updating abc..def\nFast-forward\n 1 file changed",
            "stderr": "",
        })()
        restart_result = type("R", (), {"returncode": 0})()
        log_result = type("R", (), {
            "returncode": 0,
            "stdout": "abc1234 feat: add cool feature\ndef5678 fix: repair widget",
            "stderr": "",
        })()
        call_results = [pull_result, log_result, restart_result]
        popen_calls = []

        def fake_run(cmd, **kwargs):
            return call_results.pop(0)

        def fake_popen(cmd):
            popen_calls.append(cmd)

        with patch("subprocess.run", side_effect=fake_run), \
             patch("subprocess.Popen", side_effect=fake_popen):
            msg, changed, status, description = _run_auto_update()

        assert changed is True
        assert status == "updated"
        assert "feat: add cool feature" in description
        assert len(popen_calls) == 1  # printpulse-web restart via Popen

    def test_git_pull_failure(self):
        from pi.webapp.server import _run_auto_update
        with patch("subprocess.run", side_effect=OSError("not found")):
            msg, changed, status, description = _run_auto_update()
        assert changed is False
        assert status == "error"
        assert "failed" in msg.lower()
