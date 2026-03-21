"""Tests for printpulse.letter module."""

from printpulse.letter import parse_letter, LetterDocument


class TestParseLetter:
    def test_basic_letter(self):
        text = "Dear Josh,\n\nHello from Tahiti!\n\nSincerely,\nJames"
        doc = parse_letter(text)
        assert doc.salutation == "Dear Josh,"
        assert "Hello from Tahiti!" in doc.body
        assert "Sincerely" in doc.closing

    def test_no_salutation(self):
        text = "Just some text without a greeting.\n\nYours truly,\nJames"
        doc = parse_letter(text)
        assert doc.body.strip() != ""

    def test_auto_date(self):
        text = "Dear Josh,\n\nHello.\n\nBest regards,\nJames"
        doc = parse_letter(text)
        assert doc.date  # should have auto-generated date

    def test_empty_input(self):
        doc = parse_letter("")
        assert isinstance(doc, LetterDocument)


class TestLetterDocument:
    def test_full_text_roundtrip(self):
        doc = LetterDocument(
            date="March 20, 2026",
            salutation="Dear Josh,",
            body="Hello from Tahiti!",
            closing="Sincerely,",
            signature_name="James",
        )
        full = doc.full_text()
        assert "Dear Josh," in full
        assert "Hello from Tahiti!" in full
        assert "Sincerely," in full

    def test_sanitize(self):
        doc = LetterDocument(
            date="March 20, 2026",
            salutation="Dear Josh,",
            body="Hello\u2019s world",
            closing="Sincerely,",
            signature_name="James",
        )
        doc.sanitize(lambda s: s.replace("\u2019", "'"))
        assert "\u2019" not in doc.body
        assert "'" in doc.body
