"""Letter document model and text parser.

Parses raw / dictated text into a structured LetterDocument with
salutation, body, closing, and signature — ready for rendering.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# Closing phrases (longest first so greedy match works)
_CLOSING_PHRASES = sorted([
    "Yours sincerely",
    "Yours faithfully",
    "Yours truly",
    "Sincerely yours",
    "Sincerely",
    "Best regards",
    "Kind regards",
    "Warm regards",
    "Regards",
    "With love",
    "With warmth",
    "Love",
    "Fondly",
    "Affectionately",
    "Stay safe",
    "Until next time",
    "Ever yours",
    "Your friend",
    "Your humble servant",
    "Your obedient servant",
    "Respectfully",
    "Cheers",
    "All the best",
    "Best wishes",
    "Take care",
    "Godspeed",
], key=len, reverse=True)


@dataclass
class LetterDocument:
    date: str = ""
    salutation: str = ""          # e.g. "Dear Joshua,"  or "Joshua --"
    body: str = ""                # main letter body
    closing: str = ""             # e.g. "Stay safe!"
    signature_name: str = ""      # filled from stationery profile

    # After closing, any remaining text (rare)
    postscript: str = ""

    def sanitize(self, fn) -> None:
        """Apply a sanitization function to all text fields."""
        self.date = fn(self.date)
        self.salutation = fn(self.salutation)
        self.body = fn(self.body)
        self.closing = fn(self.closing)
        self.signature_name = fn(self.signature_name)
        self.postscript = fn(self.postscript)

    def full_text(self) -> str:
        """Reconstruct the letter as a single string for analysis."""
        parts = []
        if self.date:
            parts.append(self.date)
        if self.salutation:
            parts.append(self.salutation)
        if self.body:
            parts.append(self.body)
        if self.closing:
            parts.append(self.closing)
        if self.signature_name:
            parts.append(self.signature_name)
        if self.postscript:
            parts.append(f"P.S. {self.postscript}")
        return "\n\n".join(parts)


def parse_letter(raw_text: str, sender_name: str = "") -> LetterDocument:
    """Parse raw/dictated text into a structured LetterDocument.

    Heuristics:
        - First line starting with "Dear" or a name followed by dash/comma -> salutation
        - Known closing phrases near the end -> closing + everything after
        - Everything between salutation and closing -> body
        - Date auto-generated if not present
    """
    doc = LetterDocument()
    doc.date = datetime.now().strftime("%B %d, %Y")
    doc.signature_name = sender_name

    lines = raw_text.strip().splitlines()
    if not lines:
        return doc

    # ── Detect salutation ──
    # Patterns: "Dear Name," / "Dear Name --" / "Name --" / "Name,"
    first_line = lines[0].strip()
    salutation_pattern = re.compile(
        r'^(Dear\s+.+?[,\-\u2014]|[A-Z][a-z]+\s*[\-\u2014]+)',
        re.IGNORECASE,
    )

    body_start = 0
    match = salutation_pattern.match(first_line)
    if match:
        doc.salutation = first_line
        body_start = 1
    elif first_line.lower().startswith("dear "):
        doc.salutation = first_line
        body_start = 1

    # ── Detect closing phrase ──
    # Search from the end upward for a known closing phrase
    body_lines = lines[body_start:]
    closing_idx = None
    closing_phrase = ""

    for i in range(len(body_lines) - 1, max(len(body_lines) - 6, -1), -1):
        if i < 0:
            break
        line = body_lines[i].strip()
        line_lower = line.lower().rstrip("!.,")
        for phrase in _CLOSING_PHRASES:
            if line_lower.startswith(phrase.lower()):
                closing_idx = i
                closing_phrase = line
                break
        if closing_idx is not None:
            break

    if closing_idx is not None:
        doc.body = "\n".join(body_lines[:closing_idx]).strip()
        # Everything from closing_idx onward is closing + possible postscript
        remaining = body_lines[closing_idx:]
        doc.closing = remaining[0].strip()
        if len(remaining) > 1:
            # Lines after closing before signature could be postscript
            extra = "\n".join(remaining[1:]).strip()
            if extra:
                doc.postscript = extra
    else:
        doc.body = "\n".join(body_lines).strip()

    return doc


def format_letter_interactive(theme: str = "green") -> LetterDocument:
    """Interactive template — prompts user for each letter part.

    Returns a populated LetterDocument.
    """
    doc = LetterDocument()
    doc.date = datetime.now().strftime("%B %d, %Y")

    ui_mod = None
    try:
        from printpulse import ui as ui_mod
    except ImportError:
        pass

    def _prompt(label: str, default: str = "") -> str:
        if ui_mod:
            ui_mod.console.print(
                f"\n  {label}: ",
                style=ui_mod.get_theme(theme)["primary"],
                end="",
            )
        else:
            print(f"  {label}: ", end="")
        val = input().strip()
        return val or default

    if ui_mod:
        ui_mod.retro_panel("LETTER TEMPLATE", "Fill in each section below.", theme)

    doc.salutation = _prompt("Recipient (e.g. 'Dear Joshua,')", "Dear Friend,")
    if not doc.salutation.startswith("Dear"):
        doc.salutation = f"Dear {doc.salutation},"

    if ui_mod:
        ui_mod.retro_panel("BODY", "Enter the letter body (press Enter twice to finish):", theme)
    body_lines: list[str] = []
    while True:
        line = input()
        if line == "" and body_lines and body_lines[-1] == "":
            body_lines.pop()
            break
        body_lines.append(line)
    doc.body = "\n".join(body_lines)

    doc.closing = _prompt("Closing (e.g. 'Yours sincerely,')", "Yours sincerely,")
    doc.signature_name = _prompt("Your name", "")

    return doc
