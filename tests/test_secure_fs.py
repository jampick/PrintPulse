"""Tests for printpulse.secure_fs module."""

import json
import os
import platform
import sys
import tempfile

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from printpulse.secure_fs import (
    secure_makedirs,
    secure_write_json,
    secure_tempfile,
    secure_delete,
    check_permissions,
)

_IS_UNIX = platform.system() != "Windows"


class TestSecureMakedirs:
    def test_creates_directory(self, tmp_path):
        target = os.path.join(str(tmp_path), "testdir")
        secure_makedirs(target)
        assert os.path.isdir(target)

    def test_idempotent(self, tmp_path):
        target = os.path.join(str(tmp_path), "testdir")
        secure_makedirs(target)
        secure_makedirs(target)  # Should not raise
        assert os.path.isdir(target)

    def test_nested_directories(self, tmp_path):
        target = os.path.join(str(tmp_path), "a", "b", "c")
        secure_makedirs(target)
        assert os.path.isdir(target)


class TestSecureWriteJson:
    def test_writes_valid_json(self, tmp_path):
        path = os.path.join(str(tmp_path), "test.json")
        data = {"key": "value", "num": 42}
        secure_write_json(path, data)

        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data

    def test_creates_parent_directories(self, tmp_path):
        path = os.path.join(str(tmp_path), "sub", "dir", "test.json")
        secure_write_json(path, {"test": True})
        assert os.path.isfile(path)

    def test_unicode_content(self, tmp_path):
        path = os.path.join(str(tmp_path), "unicode.json")
        data = {"text": "Hello \u2019 world"}
        secure_write_json(path, data)

        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["text"] == "Hello \u2019 world"

    def test_overwrites_existing(self, tmp_path):
        path = os.path.join(str(tmp_path), "overwrite.json")
        secure_write_json(path, {"v": 1})
        secure_write_json(path, {"v": 2})

        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["v"] == 2


class TestSecureTempfile:
    def test_creates_file(self):
        path = secure_tempfile(suffix=".test")
        try:
            assert os.path.isfile(path)
        finally:
            os.unlink(path)

    def test_custom_suffix(self):
        path = secure_tempfile(suffix=".wav")
        try:
            assert path.endswith(".wav")
        finally:
            os.unlink(path)

    def test_file_is_writable(self):
        path = secure_tempfile()
        try:
            with open(path, "w") as f:
                f.write("test")
            with open(path, "r") as f:
                assert f.read() == "test"
        finally:
            os.unlink(path)


class TestSecureDelete:
    def test_deletes_file(self, tmp_path):
        path = os.path.join(str(tmp_path), "delete_me.txt")
        with open(path, "w") as f:
            f.write("sensitive data")
        secure_delete(path)
        assert not os.path.exists(path)

    def test_handles_nonexistent_file(self, tmp_path):
        path = os.path.join(str(tmp_path), "nonexistent.txt")
        secure_delete(path)  # Should not raise

    def test_handles_empty_file(self, tmp_path):
        path = os.path.join(str(tmp_path), "empty.txt")
        with open(path, "w") as f:
            pass  # Empty file
        secure_delete(path)
        assert not os.path.exists(path)


class TestCheckPermissions:
    def test_returns_list(self, tmp_path):
        result = check_permissions(str(tmp_path))
        assert isinstance(result, list)

    def test_nonexistent_path_returns_empty(self):
        result = check_permissions("/nonexistent/path/xyz")
        assert result == []

    def test_returns_empty_on_windows(self, tmp_path):
        if _IS_UNIX:
            return  # Skip on Unix
        result = check_permissions(str(tmp_path))
        assert result == []
