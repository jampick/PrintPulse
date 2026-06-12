"""Headline translation for bilingual printing.

Translates news titles/summaries with the OpenAI chat API so watch mode
can print English plus a second language on the same ticket. Calls the
REST API directly via requests — the Pi appliance venv has requests but
not the openai package, and a translation call doesn't need an SDK.

Failure is always soft: any error (no key, no network, API error) returns
None and the caller prints English only.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# Latin-script languages only: the print pipeline sanitizes text to
# ASCII (text_sanitize.py), so non-Latin scripts would be stripped
# entirely. Accents are folded (mañana -> manana) but stay readable.
SUPPORTED_LANGUAGES = {
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
}

# English (or no selection) means "don't translate" — never costs an API call.
_NO_TRANSLATE = ("", "en")

_MODEL = "gpt-4o-mini"
_MAX_INPUT_CHARS = 600

_ILLUSTRATIONS_CONFIG = os.path.expanduser("~/.printpulse/config.json")


def needs_translation(lang_code: str | None) -> bool:
    """True if lang_code is a supported non-English target."""
    if not lang_code or lang_code.lower() in _NO_TRANSLATE:
        return False
    return lang_code.lower() in SUPPORTED_LANGUAGES


def _get_api_key() -> str | None:
    """OpenAI key from env, desktop config, or Pi appliance config.

    Keys are stripped of whitespace — .env files with CRLF line endings
    otherwise leave a trailing \\r that httpx rejects as an illegal header.
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    if os.path.isfile(_ILLUSTRATIONS_CONFIG):
        try:
            with open(_ILLUSTRATIONS_CONFIG, "r", encoding="utf-8") as f:
                key = (json.load(f).get("openai_api_key") or "").strip()
            if key:
                return key
        except Exception:
            pass
    try:
        from pi.appliance import load_config
        return load_config().get("openai_api_key", "").strip() or None
    except Exception:
        return None


def translate_text(text: str, lang_code: str) -> str | None:
    """Translate text into the target language. None on any failure."""
    text = (text or "").strip()
    if not text or not needs_translation(lang_code):
        return None

    api_key = _get_api_key()
    if not api_key:
        logger.warning("Translation skipped: no OpenAI API key configured.")
        return None

    language = SUPPORTED_LANGUAGES[lang_code.lower()]
    try:
        import requests
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"Translate the user's news text into {language}. "
                            "Reply with only the translation — no quotes, "
                            "no commentary."
                        ),
                    },
                    {"role": "user", "content": text[:_MAX_INPUT_CHARS]},
                ],
                "max_tokens": 300,
                "temperature": 0.2,
            },
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"] or ""
        return content.strip() or None
    except Exception as e:
        logger.warning("Translation to %s failed: %s", language, e)
        return None
