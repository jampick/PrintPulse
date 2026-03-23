"""Tests for watch module — quiet hours logic."""

from datetime import time as dtime
from unittest.mock import patch

from printpulse.watch import _is_in_quiet_hours


class TestIsInQuietHours:
    """Test quiet hours with midnight crossover and same-day ranges."""

    def _mock_time(self, hour, minute=0):
        """Return a patch that sets datetime.now().time() to the given time."""
        mock_dt = dtime(hour, minute)
        return patch(
            "printpulse.watch.datetime",
            wraps=__import__("datetime").datetime,
            **{"now.return_value": type("FakeNow", (), {"time": lambda self: mock_dt})()},
        )

    # ── Midnight crossover (22:00–08:00) ──

    def test_midnight_cross_inside_late_night(self):
        with self._mock_time(23, 30):
            assert _is_in_quiet_hours("22:00", "08:00") is True

    def test_midnight_cross_inside_early_morning(self):
        with self._mock_time(5, 0):
            assert _is_in_quiet_hours("22:00", "08:00") is True

    def test_midnight_cross_at_start(self):
        with self._mock_time(22, 0):
            assert _is_in_quiet_hours("22:00", "08:00") is True

    def test_midnight_cross_just_before_end(self):
        with self._mock_time(7, 59):
            assert _is_in_quiet_hours("22:00", "08:00") is True

    def test_midnight_cross_at_end(self):
        with self._mock_time(8, 0):
            assert _is_in_quiet_hours("22:00", "08:00") is False

    def test_midnight_cross_outside_afternoon(self):
        with self._mock_time(14, 0):
            assert _is_in_quiet_hours("22:00", "08:00") is False

    def test_midnight_cross_just_before_start(self):
        with self._mock_time(21, 59):
            assert _is_in_quiet_hours("22:00", "08:00") is False

    # ── Same-day range (09:00–17:00) ──

    def test_sameday_inside(self):
        with self._mock_time(12, 0):
            assert _is_in_quiet_hours("09:00", "17:00") is True

    def test_sameday_at_start(self):
        with self._mock_time(9, 0):
            assert _is_in_quiet_hours("09:00", "17:00") is True

    def test_sameday_at_end(self):
        with self._mock_time(17, 0):
            assert _is_in_quiet_hours("09:00", "17:00") is False

    def test_sameday_outside_morning(self):
        with self._mock_time(7, 0):
            assert _is_in_quiet_hours("09:00", "17:00") is False

    def test_sameday_outside_evening(self):
        with self._mock_time(20, 0):
            assert _is_in_quiet_hours("09:00", "17:00") is False

    # ── Edge: midnight exactly ──

    def test_midnight_exactly_in_range(self):
        with self._mock_time(0, 0):
            assert _is_in_quiet_hours("22:00", "06:00") is True

    def test_midnight_exactly_out_of_range(self):
        with self._mock_time(0, 0):
            assert _is_in_quiet_hours("01:00", "23:00") is False
