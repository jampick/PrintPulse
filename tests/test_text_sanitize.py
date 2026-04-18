"""Tests for the shared text_sanitize helper."""

from printpulse.text_sanitize import sanitize_for_print


class TestTypographicReplacements:
    def test_smart_apostrophe(self):
        assert sanitize_for_print("what\u2019s") == "what's"

    def test_curly_quotes(self):
        assert sanitize_for_print("\u201CHello\u201D") == '"Hello"'

    def test_em_dash(self):
        assert sanitize_for_print("yes\u2014no") == "yes--no"

    def test_en_dash(self):
        assert sanitize_for_print("2020\u20132025") == "2020-2025"

    def test_ellipsis(self):
        assert sanitize_for_print("wait\u2026") == "wait..."

    def test_non_breaking_space(self):
        assert sanitize_for_print("hello\u00A0world") == "hello world"

    def test_guillemets(self):
        assert sanitize_for_print("\u00ABhello\u00BB") == '"hello"'

    def test_zero_width_chars_stripped(self):
        assert sanitize_for_print("he\u200Bllo") == "hello"
        assert sanitize_for_print("\uFEFFstart") == "start"


class TestAccentFolding:
    def test_basic_accents(self):
        assert sanitize_for_print("café") == "cafe"
        assert sanitize_for_print("piñata") == "pinata"
        assert sanitize_for_print("naïve") == "naive"

    def test_uppercase_accents(self):
        assert sanitize_for_print("RÉSUMÉ") == "RESUME"

    def test_ligature(self):
        # NFKD decomposes ﬁ (U+FB01) into "fi"
        assert sanitize_for_print("\ufb01nish") == "finish"


class TestEmojiAndSymbolStripping:
    def test_turtle_emoji_stripped(self):
        # The beehiiv feed case: 🐢 prefix on every title
        assert sanitize_for_print("🐢 Juries hold Meta liable") == "Juries hold Meta liable"

    def test_trailing_emoji_stripped(self):
        assert sanitize_for_print("good news 🎉") == "good news"

    def test_collapses_double_spaces_after_strip(self):
        # Emoji surrounded by spaces shouldn't leave "  "
        assert sanitize_for_print("hello 🚀 world") == "hello world"

    def test_cjk_stripped(self):
        assert sanitize_for_print("Tokyo 東京 report") == "Tokyo report"

    def test_all_emoji_returns_empty(self):
        assert sanitize_for_print("🐢🎉🚀") == ""


class TestPassthrough:
    def test_plain_ascii_unchanged(self):
        text = "Hello, World! 123 - test."
        assert sanitize_for_print(text) == text

    def test_empty_string(self):
        assert sanitize_for_print("") == ""

    def test_newlines_preserved(self):
        assert sanitize_for_print("line1\nline2") == "line1\nline2"

    def test_tabs_preserved(self):
        assert sanitize_for_print("a\tb") == "a\tb"
