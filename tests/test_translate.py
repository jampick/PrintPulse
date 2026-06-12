"""Tests for printpulse.translate module."""

import sys
from unittest.mock import MagicMock

from printpulse import translate


class TestNeedsTranslation:
    def test_none_and_empty_skipped(self):
        assert not translate.needs_translation(None)
        assert not translate.needs_translation("")

    def test_english_skipped(self):
        assert not translate.needs_translation("en")
        assert not translate.needs_translation("EN")

    def test_supported_languages(self):
        for code in translate.SUPPORTED_LANGUAGES:
            assert translate.needs_translation(code)

    def test_unsupported_language(self):
        assert not translate.needs_translation("zz")
        assert not translate.needs_translation("ja")  # non-Latin script


class TestTranslateText:
    def _mock_requests(self, monkeypatch, content="Hola"):
        mock_requests = MagicMock()
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": content}}],
        }
        mock_requests.post.return_value = response
        monkeypatch.setitem(sys.modules, "requests", mock_requests)
        return mock_requests

    def test_empty_text_returns_none(self):
        assert translate.translate_text("", "es") is None
        assert translate.translate_text("   ", "es") is None

    def test_english_never_touches_api(self, monkeypatch):
        def boom():
            raise AssertionError("English must not trigger an API key lookup")
        monkeypatch.setattr(translate, "_get_api_key", boom)
        assert translate.translate_text("Hello", "en") is None
        assert translate.translate_text("Hello", "") is None

    def test_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: None)
        assert translate.translate_text("Hello", "es") is None

    def test_successful_translation(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: "sk-test")
        mock = self._mock_requests(monkeypatch, "Hola Mundo")
        assert translate.translate_text("Hello World", "es") == "Hola Mundo"
        call = mock.post.call_args
        assert "Spanish" in call.kwargs["json"]["messages"][0]["content"]

    def test_api_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: "sk-test")
        mock_requests = MagicMock()
        mock_requests.post.side_effect = RuntimeError("boom")
        monkeypatch.setitem(sys.modules, "requests", mock_requests)
        assert translate.translate_text("Hello", "es") is None

    def test_http_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: "sk-test")
        mock = self._mock_requests(monkeypatch)
        mock.post.return_value.raise_for_status.side_effect = RuntimeError("401")
        assert translate.translate_text("Hello", "es") is None

    def test_empty_response_returns_none(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: "sk-test")
        self._mock_requests(monkeypatch, "")
        assert translate.translate_text("Hello", "es") is None

    def test_long_input_truncated(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: "sk-test")
        mock = self._mock_requests(monkeypatch, "Hola")
        translate.translate_text("x" * 5000, "es")
        sent = mock.post.call_args.kwargs["json"]["messages"][1]["content"]
        assert len(sent) <= translate._MAX_INPUT_CHARS
