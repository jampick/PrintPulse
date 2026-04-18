"""Shared text sanitization for print targets (Hershey plotter + thermal).

Hershey fonts render only ASCII glyphs, and most 58mm thermal printers
support only ASCII / Latin-1. Feeding them raw UTF-8 (smart quotes,
em-dashes, emoji, accented letters, CJK) produces missing glyphs or
garbage bytes. This module folds arbitrary input down to printable
ASCII in three passes so both backends behave consistently.
"""

import re
import unicodedata

# Pass 1: targeted typographic replacements — preserve readable punctuation
# that NFKD folding would otherwise drop or distort.
_TYPOGRAPHIC_REPLACEMENTS = {
    "\u2018": "'",   # left single curly quote
    "\u2019": "'",   # right single curly quote / smart apostrophe
    "\u201A": "'",   # single low-9 quotation mark
    "\u201C": '"',   # left double curly quote
    "\u201D": '"',   # right double curly quote
    "\u201E": '"',   # double low-9 quotation mark
    "\u2013": "-",   # en-dash
    "\u2014": "--",  # em-dash
    "\u2026": "...", # ellipsis
    "\u00A0": " ",   # non-breaking space
    "\u2032": "'",   # prime
    "\u2033": '"',   # double prime
    "\u2010": "-",   # hyphen
    "\u2011": "-",   # non-breaking hyphen
    "\u2012": "-",   # figure dash
    "\u00AB": '"',   # left guillemet
    "\u00BB": '"',   # right guillemet
    "\u2039": "'",   # single left angle quote
    "\u203A": "'",   # single right angle quote
    "\u02BC": "'",   # modifier letter apostrophe
    "\uFEFF": "",    # BOM / zero-width no-break space
    "\u200B": "",    # zero-width space
    "\u200C": "",    # zero-width non-joiner
    "\u200D": "",    # zero-width joiner
}

_MULTI_SPACE = re.compile(r" {2,}")


def sanitize_for_print(text: str) -> str:
    """Fold arbitrary Unicode down to printable ASCII for plot/thermal output.

    Pipeline:
      1. Apply targeted typographic replacements (smart quotes, dashes, etc.).
      2. NFKD-normalize + ASCII-encode-with-ignore to fold accented Latin
         (é→e, ñ→n, ﬁ→fi) and drop combining marks.
      3. Strip any remaining non-printable bytes (emoji, CJK, symbols that
         had no ASCII equivalent) and collapse resulting double spaces.
    """
    if not text:
        return text

    for src, dst in _TYPOGRAPHIC_REPLACEMENTS.items():
        text = text.replace(src, dst)

    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    text = "".join(c for c in text if c == "\n" or c == "\t" or 0x20 <= ord(c) <= 0x7E)

    text = _MULTI_SPACE.sub(" ", text).strip(" ")

    return text
