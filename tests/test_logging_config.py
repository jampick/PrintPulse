"""Tests for printpulse.logging_config module."""

import logging
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Reset the _configured flag before each import to allow re-setup
import printpulse.logging_config as lc


class TestSetupLogging:
    def setup_method(self):
        """Reset logging state between tests."""
        lc._configured = False
        logger = logging.getLogger("printpulse")
        logger.handlers.clear()

    def test_returns_logger(self):
        logger = lc.setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "printpulse"

    def test_sets_level_from_argument(self):
        logger = lc.setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_idempotent(self):
        logger1 = lc.setup_logging()
        handler_count = len(logger1.handlers)
        lc.setup_logging()  # Should not add more handlers
        assert len(logger1.handlers) == handler_count

    def test_default_level_is_info(self):
        # Clear env var if set
        old = os.environ.pop("PRINTPULSE_LOG_LEVEL", None)
        try:
            logger = lc.setup_logging()
            assert logger.level == logging.INFO
        finally:
            if old is not None:
                os.environ["PRINTPULSE_LOG_LEVEL"] = old

    def test_env_var_override(self):
        os.environ["PRINTPULSE_LOG_LEVEL"] = "WARNING"
        try:
            logger = lc.setup_logging()
            assert logger.level == logging.WARNING
        finally:
            del os.environ["PRINTPULSE_LOG_LEVEL"]


class TestGetLogger:
    def setup_method(self):
        lc._configured = False
        logging.getLogger("printpulse").handlers.clear()

    def test_returns_child_logger(self):
        logger = lc.get_logger("mymodule")
        assert logger.name == "printpulse.mymodule"

    def test_is_logging_logger(self):
        logger = lc.get_logger("test")
        assert isinstance(logger, logging.Logger)

    def test_initializes_parent(self):
        lc.get_logger("test")
        assert lc._configured is True
