"""Secure filesystem operations for PrintPulse.

Centralizes directory/file creation with proper permissions
and provides secure temp file and cleanup utilities.
"""

import os
import platform
import stat
import tempfile

_IS_UNIX = platform.system() != "Windows"

# Default permissions: owner-only
_DIR_MODE = 0o700   # rwx------
_FILE_MODE = 0o600  # rw-------


def secure_makedirs(path: str, mode: int = _DIR_MODE) -> None:
    """Create directory with secure permissions (owner-only on Unix)."""
    os.makedirs(path, exist_ok=True)
    if _IS_UNIX:
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def secure_write_json(path: str, data, indent: int = 2) -> None:
    """Write JSON to a file with secure permissions.

    Uses atomic write (temp file + rename) to avoid partial writes on crash.
    On Unix, the file is created with owner-only permissions from the start
    (no TOCTOU window where the file is world-readable).
    """
    import json

    dir_path = os.path.dirname(path)
    if dir_path:
        secure_makedirs(dir_path)

    content = json.dumps(data, indent=indent, ensure_ascii=False)

    if _IS_UNIX:
        # Open with restrictive permissions from the start (no chmod race)
        fd = os.open(
            path + ".tmp",
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            _FILE_MODE,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(path + ".tmp", path)
        except BaseException:
            # Clean up temp file on failure
            try:
                os.unlink(path + ".tmp")
            except OSError:
                pass
            raise
    else:
        # Windows fallback — no atomic rename guarantees
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()


def secure_tempfile(suffix: str = ".tmp", prefix: str = "printpulse_") -> str:
    """Create a temporary file with secure permissions.

    Returns the path to the temp file (closed, ready for writing).
    """
    fd = tempfile.mkstemp(suffix=suffix, prefix=prefix)
    path = fd[1]
    os.close(fd[0])

    if _IS_UNIX:
        try:
            os.chmod(path, _FILE_MODE)
        except OSError:
            pass

    return path


def secure_delete(path: str) -> None:
    """Securely delete a file by overwriting with zeros before removal.

    Best-effort: if overwrite fails, still removes the file.
    """
    try:
        if os.path.isfile(path):
            size = os.path.getsize(path)
            if size > 0:
                with open(path, "wb") as f:
                    f.write(b"\x00" * size)
                    f.flush()
                    os.fsync(f.fileno())
            os.unlink(path)
    except OSError:
        # Best effort — try plain removal
        try:
            os.unlink(path)
        except OSError:
            pass


def check_permissions(path: str) -> list[str]:
    """Check if a file/directory has overly permissive permissions.

    Returns a list of warning messages (empty if everything is fine).
    Only meaningful on Unix systems.
    """
    warnings = []

    if not _IS_UNIX or not os.path.exists(path):
        return warnings

    try:
        st = os.stat(path)
        mode = st.st_mode

        if os.path.isdir(path):
            # Directory should be 0o700 or stricter
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                warnings.append(
                    f"Directory {path} is accessible by group/others. "
                    f"Run: chmod 700 {path}"
                )
        else:
            # File should be 0o600 or stricter
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                warnings.append(
                    f"File {path} is readable by group/others. "
                    f"Run: chmod 600 {path}"
                )
    except OSError:
        pass

    return warnings
