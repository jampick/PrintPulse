"""Thermal receipt printer output (ESC/POS) for Rongta 58mm and compatibles.

Supports two transport backends:
- Windows: win32print (pywin32) via named printer
- Linux: direct write to /dev/usb/lp0 (Pi Zero, no extra deps)
"""

import os
import platform
import re
import struct
import textwrap

from printpulse import ui

# ─── Printer Defaults ───
PRINTER_NAME_WIN = "PrintMojo"          # Windows printer name
PRINTER_DEVICE_LINUX = "/dev/usb/lp0"   # Linux USB device path
LINE_WIDTH = 32  # chars per line at Font A normal width

_IS_LINUX = platform.system() == "Linux"


# ─── ESC/POS CONSTANTS ───
ESC = b'\x1b'
GS = b'\x1d'

CMD_INIT = ESC + b'@'
CMD_CENTER = ESC + b'\x61\x01'
CMD_LEFT = ESC + b'\x61\x00'
CMD_BOLD_ON = ESC + b'\x45\x01'
CMD_BOLD_OFF = ESC + b'\x45\x00'
CMD_DOUBLE_H = GS + b'\x21\x01'
CMD_NORMAL_SIZE = GS + b'\x21\x00'
CMD_PARTIAL_CUT = GS + b'\x56\x01'

SEPARATOR = b'-' * LINE_WIDTH + b'\n'
THICK_SEP = b'=' * LINE_WIDTH + b'\n'


def _sanitize_for_thermal(text: str) -> str:
    """Replace Unicode typographic characters with ASCII equivalents.

    Thermal printers typically support only ASCII / Latin-1 and will render
    multi-byte UTF-8 characters (smart quotes, em-dashes, etc.) as garbage.
    """
    replacements = {
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
        "\u200B": "",    # zero-width space
        "\u00AB": '"',   # left guillemet
        "\u00BB": '"',   # right guillemet
        "\u2039": "'",   # single left angle quote
        "\u203A": "'",   # single right angle quote
        "\u02BC": "'",   # modifier letter apostrophe
        "\u2032": "'",   # prime
        "\u2033": '"',   # double prime
        "\u2010": "-",   # hyphen
        "\u2011": "-",   # non-breaking hyphen
        "\u2012": "-",   # figure dash
        "\uFEFF": "",    # BOM / zero-width no-break space
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _wrap(text: str, width: int = LINE_WIDTH) -> str:
    """Word-wrap text to fit printer line width."""
    lines = []
    for paragraph in text.split('\n'):
        if paragraph.strip():
            lines.extend(textwrap.wrap(paragraph, width=width))
        else:
            lines.append('')
    return '\n'.join(lines)


def _build_qr_data(url: str) -> bytes:
    """Build ESC/POS QR code command sequence."""
    url_bytes = url.encode('utf-8')
    data = b''
    # QR model 2
    data += GS + b'\x28\x6b\x04\x00\x31\x41\x32\x00'
    # QR module size 4
    data += GS + b'\x28\x6b\x03\x00\x31\x43\x04'
    # QR error correction L
    data += GS + b'\x28\x6b\x03\x00\x31\x45\x30'
    # Store QR data
    store_len = len(url_bytes) + 3
    data += GS + b'\x28\x6b' + struct.pack('<H', store_len) + b'\x31\x50\x30' + url_bytes
    # Print QR
    data += GS + b'\x28\x6b\x03\x00\x31\x51\x30'
    return data


# ─── Transport Layer ────────────────────────────────────────────────────────


def _get_device_path() -> str:
    """Get the Linux device path, checking appliance config first."""
    try:
        from pi.appliance import load_config
        cfg = load_config()
        return cfg.get("printer_device", PRINTER_DEVICE_LINUX)
    except Exception:
        return PRINTER_DEVICE_LINUX


def _send_raw(data: bytes, theme: str = "green") -> bool:
    """Send raw ESC/POS bytes to the thermal printer.

    Auto-detects platform:
    - Linux: writes directly to /dev/usb/lp0 (or configured device)
    - Windows: uses win32print API
    """
    if _IS_LINUX:
        return _send_raw_linux(data, theme)
    return _send_raw_windows(data, theme)


def _send_raw_linux(data: bytes, theme: str = "green") -> bool:
    """Send raw bytes to Linux USB printer device."""
    device = _get_device_path()
    try:
        with open(device, "wb") as f:
            f.write(data)
            f.flush()
        return True
    except FileNotFoundError:
        ui.error_panel(
            f"Printer device not found: {device}\n"
            "Is the thermal printer plugged in via USB?",
            theme,
        )
        return False
    except PermissionError:
        ui.error_panel(
            f"Permission denied: {device}\n"
            "Run: sudo usermod -a -G lp $USER  (then reboot)",
            theme,
        )
        return False
    except Exception as e:
        ui.error_panel(f"Thermal printer error: {e}", theme)
        return False


def _send_raw_windows(data: bytes, theme: str = "green") -> bool:
    """Send raw bytes via Windows win32print API."""
    try:
        import win32print
    except ImportError:
        ui.error_panel(
            "pywin32 is not installed. Run: pip install pywin32",
            theme,
        )
        return False

    try:
        hprinter = win32print.OpenPrinter(PRINTER_NAME_WIN)
        try:
            win32print.StartDocPrinter(hprinter, 1, ('PrintPulse', None, 'RAW'))
            win32print.StartPagePrinter(hprinter)
            win32print.WritePrinter(hprinter, data)
            win32print.EndPagePrinter(hprinter)
            win32print.EndDocPrinter(hprinter)
        finally:
            win32print.ClosePrinter(hprinter)
        return True
    except Exception as e:
        ui.error_panel(f"Thermal printer error: {e}", theme)
        return False


def check_printer() -> bool:
    """Check if the thermal printer is available."""
    if _IS_LINUX:
        device = _get_device_path()
        return os.path.exists(device) and os.access(device, os.W_OK)

    # Windows
    try:
        import win32print
        hprinter = win32print.OpenPrinter(PRINTER_NAME_WIN)
        win32print.ClosePrinter(hprinter)
        return True
    except Exception:
        return False


# ─── Public API ─────────────────────────────────────────────────────────────


def print_text(text: str, theme: str = "green", dry_run: bool = False) -> bool:
    """Print plain text to the thermal printer.

    Used for regular (non-watch) text input mode.
    Returns True on success.
    """
    if dry_run:
        ui.retro_panel(
            "DRY RUN (THERMAL)",
            f"Would print to thermal printer:\n  {text[:80]}...",
            theme,
        )
        return True

    text = _sanitize_for_thermal(text)
    wrapped = _wrap(text)

    data = CMD_INIT
    data += CMD_CENTER
    data += CMD_BOLD_ON
    data += b'PRINTPULSE\n'
    data += CMD_BOLD_OFF
    data += SEPARATOR
    data += CMD_LEFT
    data += CMD_BOLD_ON
    data += CMD_DOUBLE_H
    # First line as headline (bold + double height)
    first_line = text.split('\n')[0][:80]
    data += _wrap(first_line, LINE_WIDTH).encode('utf-8', errors='replace') + b'\n'
    data += CMD_NORMAL_SIZE
    data += CMD_BOLD_OFF
    data += SEPARATOR
    # Full body
    data += wrapped.encode('utf-8', errors='replace') + b'\n'
    data += THICK_SEP
    data += b'\n\n'
    data += CMD_PARTIAL_CUT

    return _send_raw(data, theme)


def print_news_item(title: str, summary: str = "", source: str = "",
                    url: str = "", timestamp: str = "",
                    theme: str = "green", dry_run: bool = False) -> bool:
    """Print a formatted news story to the thermal printer.

    Used for watch mode with RSS/Atom feeds.
    Returns True on success.
    """
    # Sanitize all text fields for thermal printer compatibility
    title = _sanitize_for_thermal(title)
    summary = _sanitize_for_thermal(summary)
    source = _sanitize_for_thermal(source)

    if dry_run:
        ui.retro_panel(
            "DRY RUN (THERMAL)",
            f"Would print to thermal printer:\n  {title}",
            theme,
        )
        return True

    data = CMD_INIT

    # Header
    data += CMD_CENTER
    data += CMD_BOLD_ON
    data += b'PRINTPULSE\n'
    data += CMD_BOLD_OFF
    data += SEPARATOR

    # Timestamp
    if timestamp:
        data += CMD_LEFT
        data += timestamp.encode('utf-8', errors='replace') + b'\n'
        data += SEPARATOR

    # Headline — same font as body, bold + double height
    data += CMD_LEFT
    data += CMD_BOLD_ON
    data += CMD_DOUBLE_H
    wrapped_title = _wrap(title, LINE_WIDTH)
    data += wrapped_title.encode('utf-8', errors='replace') + b'\n'
    data += CMD_NORMAL_SIZE
    data += CMD_BOLD_OFF
    data += SEPARATOR

    # Summary
    if summary:
        data += CMD_LEFT
        clean = re.sub(r'<[^>]+>', '', summary).strip()
        if clean:
            wrapped_summary = _wrap(clean, LINE_WIDTH)
            data += wrapped_summary.encode('utf-8', errors='replace') + b'\n'
            data += SEPARATOR

    # Source
    if source:
        data += CMD_CENTER
        data += f'Source: {source}\n'.encode('utf-8', errors='replace')

    # QR code
    if url:
        data += CMD_CENTER
        data += b'\n'
        data += _build_qr_data(url)
        data += b'\n'

    data += THICK_SEP
    data += b'\n\n'
    data += CMD_PARTIAL_CUT

    return _send_raw(data, theme)
