"""Tests for version info in the web UI server."""

import re
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


class TestVersionSync:
    """Ensure __init__.py and pyproject.toml stay in sync.

    The auto-bump workflow updates both files atomically; this test
    catches any manual desync between them.
    """

    def test_init_version_matches_pyproject(self):
        from printpulse import __version__

        toml_path = os.path.join(_project_root, "pyproject.toml")
        toml_version = None
        with open(toml_path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^\s*version\s*=\s*["\']([^"\']+)["\']', line)
                if m:
                    toml_version = m.group(1)
                    break

        assert toml_version is not None, "Could not find version in pyproject.toml"
        assert __version__ == toml_version, (
            f"printpulse/__init__.py has __version__={__version__!r} "
            f"but pyproject.toml has version={toml_version!r} — "
            f"run the bump-version workflow or update both files together"
        )
