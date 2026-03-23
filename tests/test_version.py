"""Tests for version info in the web UI server."""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pi.webapp.server import _get_version_info


class TestGetVersionInfo:
    """Test version string extraction."""

    def test_returns_string(self):
        version = _get_version_info()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_contains_semver(self):
        """Version should contain a semver-like pattern (X.Y.Z)."""
        version = _get_version_info()
        parts = version.split("+")[0]  # strip git hash
        assert "." in parts
        segments = parts.split(".")
        assert len(segments) >= 2
        # First segment should be numeric
        assert segments[0].isdigit()

    def test_contains_git_hash(self):
        """Version should have a +<hash> suffix when in a git repo."""
        version = _get_version_info()
        # We're running from within the repo, so hash should be present
        assert "+" in version
        git_hash = version.split("+")[1]
        assert len(git_hash) >= 7  # short hash is typically 7+ chars
