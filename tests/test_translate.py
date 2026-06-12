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
    def _mock_openai(self, monkeypatch, content="Hola"):
        mock_openai = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = content
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = response
        monkeypatch.setitem(sys.modules, "openai", mock_openai)
        return mock_openai

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
        mock = self._mock_openai(monkeypatch, "Hola Mundo")
        assert translate.translate_text("Hello World", "es") == "Hola Mundo"
        call = mock.OpenAI.return_value.chat.completions.create.call_args
        assert "Spanish" in call.kwargs["messages"][0]["content"]

    def test_api_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: "sk-test")
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value.chat.completions.create.side_effect = \
            RuntimeError("boom")
        monkeypatch.setitem(sys.modules, "openai", mock_openai)
        assert translate.translate_text("Hello", "es") is None

    def test_empty_response_returns_none(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: "sk-test")
        self._mock_openai(monkeypatch, "")
        assert translate.translate_text("Hello", "es") is None

    def test_long_input_truncated(self, monkeypatch):
        monkeypatch.setattr(translate, "_get_api_key", lambda: "sk-test")
        mock = self._mock_openai(monkeypatch, "Hola")
        translate.translate_text("x" * 5000, "es")
        call = mock.OpenAI.return_value.chat.completions.create.call_args
        sent = call.kwargs["messages"][1]["content"]
        assert len(sent) <= translate._MAX_INPUT_CHARS
