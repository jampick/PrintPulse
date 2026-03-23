"""Tests for watch module — quiet hours logic and quiet queue."""

import json
import os
from datetime import time as dtime
from unittest.mock import patch

import pytest

from printpulse.watch import (
    QUIET_QUEUE_FILE,
    _enqueue_quiet_items,
    _is_in_quiet_hours,
    _load_quiet_queue,
    _save_quiet_queue,
)


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


class TestQuietQueue:
    """Test persistent quiet-hours queue."""

    @pytest.fixture(autouse=True)
    def _patch_queue_file(self, tmp_path, monkeypatch):
        """Redirect QUIET_QUEUE_FILE to a temp path for each test."""
        tmp_queue = str(tmp_path / "quiet_queue.json")
        monkeypatch.setattr("printpulse.watch.QUIET_QUEUE_FILE", tmp_queue)
        # Also patch secure_write_json to write normally (it already does, but keep it real)
        yield
        # Cleanup handled by tmp_path fixture

    def test_empty_queue_on_missing_file(self):
        assert _load_quiet_queue() == []

    def test_save_and_load_roundtrip(self):
        items = [{"id": "1", "title": "Story A", "summary": "", "_source": "Feed X"}]
        _save_quiet_queue(items)
        loaded = _load_quiet_queue()
        assert len(loaded) == 1
        assert loaded[0]["title"] == "Story A"

    def test_enqueue_adds_new_items(self):
        items = [
            {"id": "a1", "title": "Alpha", "summary": "s1", "_source": "Src1"},
            {"id": "a2", "title": "Beta", "summary": "s2", "_source": "Src2"},
        ]
        _enqueue_quiet_items(items)
        queue = _load_quiet_queue()
        assert len(queue) == 2
        assert queue[0]["id"] == "a1"
        assert queue[1]["id"] == "a2"

    def test_enqueue_skips_duplicates(self):
        item = {"id": "dup", "title": "Dupe Story", "summary": "", "_source": "X"}
        _enqueue_quiet_items([item])
        _enqueue_quiet_items([item])  # second call — same id
        assert len(_load_quiet_queue()) == 1

    def test_enqueue_preserves_existing_items(self):
        first = {"id": "first", "title": "First", "summary": "", "_source": "X"}
        second = {"id": "second", "title": "Second", "summary": "", "_source": "X"}
        _enqueue_quiet_items([first])
        _enqueue_quiet_items([second])
        queue = _load_quiet_queue()
        assert len(queue) == 2

    def test_save_empty_clears_queue(self):
        _save_quiet_queue([{"id": "x", "title": "T", "summary": "", "_source": "S"}])
        _save_quiet_queue([])
        assert _load_quiet_queue() == []

    def test_load_tolerates_corrupt_file(self, monkeypatch, tmp_path):
        bad_file = str(tmp_path / "bad.json")
        with open(bad_file, "w") as f:
            f.write("not valid json{{{")
        monkeypatch.setattr("printpulse.watch.QUIET_QUEUE_FILE", bad_file)
        assert _load_quiet_queue() == []
