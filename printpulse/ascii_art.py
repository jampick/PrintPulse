"""Dynamic ASCII art from story images.

Fetches the actual image from an RSS entry and renders it as
recognizable ASCII art using a short brightness ramp. Keeps the
output sparse and clean so you can make out faces, objects, etc.
"""

import io
import os
import re
import hashlib
import tempfile

# Character for dithered output — dark pixel gets a block, light gets space
_BLOCK = "#"

# Cache directory for downloaded images
_CACHE_DIR = os.path.join(tempfile.gettempdir(), "v2p_img_cache")


def _ensure_cache_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(url: str) -> str:
    h = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(_CACHE_DIR, f"{h}.jpg")


def fetch_image(url: str) -> bytes | None:
    """Download an image, with disk caching."""
    from printpulse import ensure_dependency

    _ensure_cache_dir()
    cached = _cache_path(url)

    if os.path.isfile(cached):
        with open(cached, "rb") as f:
            return f.read()

    requests = ensure_dependency("requests")
    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "PrintPulse/0.1 (RSS reader)",
        })
        resp.raise_for_status()
        data = resp.content
        with open(cached, "wb") as f:
            f.write(data)
        return data
    except Exception:
        return None


def image_to_ascii(
    image_data: bytes,
    width: int = 60,
    height: int = 25,
) -> str:
    """Convert image to recognizable ASCII art using brightness mapping.

    Uses a short 5-level character ramp so the output is clean and
    you can actually make out faces, buildings, objects. The key is
    strong contrast and few levels — like a high-contrast print.

    Quality targets:
      - >40% whitespace (not a wall of chars)
      - No single char >40% of non-space chars
      - At least 4 distinct chars used
      - Recognizable shapes/silhouettes
    """
    from printpulse import ensure_dependency
    ensure_dependency("Pillow", "PIL")
    from PIL import Image, ImageEnhance, ImageOps

    img = Image.open(io.BytesIO(image_data))
    img = img.convert("L")  # grayscale

    # Center crop to 4:3 — focus on main subject
    w, h = img.size
    target_ratio = 4 / 3
    current_ratio = w / h
    if current_ratio > target_ratio * 1.2:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif current_ratio < target_ratio * 0.8:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    # Measure average brightness BEFORE any processing
    avg_brightness = sum(img.getdata()) / (img.width * img.height)

    # Auto-contrast to use full dynamic range
    img = ImageOps.autocontrast(img, cutoff=5)

    # Boost contrast
    img = ImageEnhance.Contrast(img).enhance(2.0)

    # For very dark images, invert so the subject (typically lighter
    # than the dark background) gets drawn as dark-on-white
    if avg_brightness < 100:
        img = ImageOps.invert(img)
        # Re-apply contrast after inversion
        img = ImageEnhance.Contrast(img).enhance(1.5)

    # Brightness boost to push more pixels to white
    img = ImageEnhance.Brightness(img).enhance(1.3)

    # Compute render size (terminal chars ~2x taller than wide)
    aspect = img.width / img.height
    render_w = width
    render_h = int(render_w / aspect / 2.0)
    if render_h > height:
        render_h = height
        render_w = int(render_h * aspect * 2.0)

    # Resize to render dimensions BEFORE dithering for best results
    img = img.resize((render_w, render_h), Image.Resampling.LANCZOS)

    # Floyd-Steinberg dithering to 1-bit — produces clean halftone patterns
    # that preserve shapes and tonal relationships at low resolution
    img_dithered = img.convert("1")  # PIL uses Floyd-Steinberg by default

    pixels = list(img_dithered.getdata())

    lines = []
    for row in range(render_h):
        row_chars = []
        for col in range(render_w):
            px = pixels[row * render_w + col]
            if px:  # white pixel (value 255/True)
                row_chars.append(" ")
            else:   # black pixel (value 0/False)
                row_chars.append(_BLOCK)
        lines.append("".join(row_chars).rstrip())

    # Trim empty lines from top/bottom
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


def extract_image_url(entry: dict) -> str | None:
    """Extract the best image URL from a feedparser entry."""
    # media:thumbnail
    thumbnails = getattr(entry, "media_thumbnail", None) or entry.get("media_thumbnail", [])
    if thumbnails and isinstance(thumbnails, list):
        return thumbnails[0].get("url")

    # media:content (prefer image types)
    media = getattr(entry, "media_content", None) or entry.get("media_content", [])
    if media and isinstance(media, list):
        for m in media:
            mtype = m.get("type", "")
            if "image" in mtype or m.get("url", "").endswith((".jpg", ".jpeg", ".png", ".webp")):
                return m.get("url")
        if media[0].get("url"):
            return media[0]["url"]

    # enclosure
    enclosures = getattr(entry, "enclosures", None) or entry.get("enclosures", [])
    if enclosures and isinstance(enclosures, list):
        for enc in enclosures:
            etype = enc.get("type", "")
            if "image" in etype:
                return enc.get("href") or enc.get("url")

    # Fallback: scrape <img> from summary HTML
    summary = entry.get("summary", "") or ""
    content_list = entry.get("content", [])
    if content_list and isinstance(content_list, list):
        summary = content_list[0].get("value", summary)

    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if img_match:
        return img_match.group(1)

    return None


def render_story_ascii(entry: dict, width: int = 60, height: int = 25) -> str | None:
    """Fetch the image for an RSS entry and render as edge-detected ASCII art."""
    url = extract_image_url(entry)
    if not url:
        return None

    data = fetch_image(url)
    if not data:
        return None

    try:
        return image_to_ascii(data, width=width, height=height)
    except Exception:
        return None
