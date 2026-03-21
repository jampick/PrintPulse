"""Tests for printpulse.thermal module."""

from printpulse.thermal import _sanitize_for_thermal, _wrap, _build_qr_data, LINE_WIDTH


class TestSanitizeForThermal:
    def test_smart_apostrophe(self):
        assert _sanitize_for_thermal("what\u2019s") == "what's"
        assert _sanitize_for_thermal("Iran\u2019s") == "Iran's"

    def test_curly_quotes(self):
        assert _sanitize_for_thermal("\u201CHello\u201D") == '"Hello"'
        assert _sanitize_for_thermal("\u2018Hi\u2019") == "'Hi'"

    def test_em_dash(self):
        assert _sanitize_for_thermal("yes\u2014no") == "yes--no"

    def test_en_dash(self):
        assert _sanitize_for_thermal("2020\u20132025") == "2020-2025"

    def test_ellipsis(self):
        assert _sanitize_for_thermal("wait\u2026") == "wait..."

    def test_non_breaking_space(self):
        assert _sanitize_for_thermal("hello\u00A0world") == "hello world"

    def test_zero_width_chars_stripped(self):
        assert _sanitize_for_thermal("he\u200Bllo") == "hello"
        assert _sanitize_for_thermal("\uFEFFstart") == "start"

    def test_plain_ascii_unchanged(self):
        text = "Hello, World! 123 - test."
        assert _sanitize_for_thermal(text) == text

    def test_guillemets(self):
        assert _sanitize_for_thermal("\u00ABhello\u00BB") == '"hello"'

    def test_modifier_apostrophe(self):
        assert _sanitize_for_thermal("it\u02BCs") == "it's"


class TestWrap:
    def test_short_text_unchanged(self):
        assert _wrap("Hello") == "Hello"

    def test_wraps_at_line_width(self):
        long_text = "word " * 20  # 100 chars
        wrapped = _wrap(long_text.strip())
        for line in wrapped.split('\n'):
            assert len(line) <= LINE_WIDTH

    def test_preserves_blank_lines(self):
        text = "Paragraph one.\n\nParagraph two."
        wrapped = _wrap(text)
        lines = wrapped.split('\n')
        assert '' in lines

    def test_custom_width(self):
        text = "Hello World Test"
        wrapped = _wrap(text, width=10)
        for line in wrapped.split('\n'):
            assert len(line) <= 10


class TestBuildQrData:
    def test_returns_bytes(self):
        result = _build_qr_data("https://example.com")
        assert isinstance(result, bytes)

    def test_contains_url(self):
        url = "https://example.com"
        result = _build_qr_data(url)
        assert url.encode('utf-8') in result

    def test_starts_with_gs_prefix(self):
        result = _build_qr_data("https://example.com")
        # GS ( k is the QR command prefix
        assert b'\x1d\x28\x6b' in result
