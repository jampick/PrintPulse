"""Logging configuration for PrintPulse.

Sets up structured logging with:
- Rotating file handler (~/.printpulse/printpulse.log)
- Console handler (for systemd journal capture on Pi)
- Configurable log level via PRINTPULSE_LOG_LEVEL env var
"""

import logging
import os
import platform
from logging.handlers import RotatingFileHandler

from printpulse.secure_fs import secure_makedirs

_LOG_DIR = os.path.join(os.path.expanduser("~"), ".printpulse")
_LOG_FILE = os.path.join(_LOG_DIR, "printpulse.log")
_MAX_BYTES = 1_000_000  # 1 MB per log file
_BACKUP_COUNT = 3        # Keep 3 rotated files

_configured = False


def setup_logging(level: str | None = None) -> logging.Logger:
    """Configure and return the root PrintPulse logger.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
               Falls back to PRINTPULSE_LOG_LEVEL env var, then INFO.
    """
    global _configured

    logger = logging.getLogger("printpulse")

    if _configured:
        return logger

    # Determine log level
    if level is None:
        level = os.environ.get("PRINTPULSE_LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler with rotation
    try:
        secure_makedirs(_LOG_DIR)
        file_handler = RotatingFileHandler(
            _LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(numeric_level)
        logger.addHandler(file_handler)

        # Set file permissions on the log file
        if platform.system() != "Windows":
            try:
                os.chmod(_LOG_FILE, 0o600)
            except OSError:
                pass
    except OSError:
        pass  # Can't write logs — non-fatal

    # Stream handler (stderr → systemd journal on Pi)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.WARNING)  # Only warnings+ to console
    logger.addHandler(stream_handler)

    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger for a specific module.

    Usage: logger = get_logger(__name__)
    """
    setup_logging()
    return logging.getLogger(f"printpulse.{name}")
