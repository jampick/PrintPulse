import json
import os
from datetime import datetime

from printpulse.config import Config
from printpulse.secure_fs import secure_write_json

DEFAULT_JOURNAL_PATH = os.path.join(os.path.expanduser("~"), ".printpulse_journal.json")


def _load_state(journal_path: str) -> dict:
    """Load journal state from disk."""
    if os.path.isfile(journal_path):
        with open(journal_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"next_line": 0, "entries": []}


def _save_state(state: dict, journal_path: str):
    """Save journal state to disk."""
    secure_write_json(journal_path, state)


def get_next_line(journal_path: str = DEFAULT_JOURNAL_PATH) -> int:
    """Return the next line index to write on."""
    state = _load_state(journal_path)
    return state["next_line"]


def format_journal_entry(text: str) -> str:
    """Prepend a timestamp to the journal entry text."""
    now = datetime.now()
    timestamp = now.strftime("%m/%d %I:%M %p")
    return f"{timestamp} - {text}"


def record_entry(
    text: str,
    lines_used: int,
    journal_path: str = DEFAULT_JOURNAL_PATH,
):
    """Record that an entry was plotted and advance the line counter."""
    state = _load_state(journal_path)
    state["entries"].append({
        "text": text,
        "timestamp": datetime.now().isoformat(),
        "start_line": state["next_line"],
        "lines_used": lines_used,
    })
    state["next_line"] += lines_used
    _save_state(state, journal_path)


def reset_journal(journal_path: str = DEFAULT_JOURNAL_PATH):
    """Reset journal state (new page)."""
    state = {"next_line": 0, "entries": []}
    _save_state(state, journal_path)


def total_lines(config: Config) -> int:
    """Return total number of lines that fit on the page."""
    line_height = config.font_size * config.line_spacing
    return int(config.text_area_height_pt / line_height)


def lines_remaining(config: Config, journal_path: str = DEFAULT_JOURNAL_PATH) -> int:
    """Estimate how many lines remain on the current page."""
    max_lines = total_lines(config)
    next_line = get_next_line(journal_path)
    return max(0, max_lines - next_line)
