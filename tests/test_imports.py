"""Smoke tests: verify all modules import without errors."""


def test_import_config():
    from printpulse import config  # noqa: F401


def test_import_thermal():
    from printpulse import thermal  # noqa: F401


def test_import_letter():
    from printpulse import letter  # noqa: F401


def test_import_ui():
    from printpulse import ui  # noqa: F401


def test_import_watch():
    from printpulse import watch  # noqa: F401


def test_import_illustrations():
    from printpulse import illustrations  # noqa: F401


def test_import_stationery():
    from printpulse import stationery  # noqa: F401


def test_import_text_to_svg():
    from printpulse import text_to_svg  # noqa: F401


def test_import_plotter():
    from printpulse import plotter  # noqa: F401


def test_import_journal():
    from printpulse import journal  # noqa: F401


def test_import_app():
    from printpulse import app  # noqa: F401
