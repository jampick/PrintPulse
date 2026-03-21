"""AI-generated SVG illustrations for letter mode.

Uses DALL-E 3 to generate pen-and-ink style raster images, then
traces them to single-stroke SVG paths using vtracer.  A GPT-4o
Vision QA loop evaluates quality and iterates with different
preprocessing / tracing parameters until the result is acceptable.
Results are cached by content hash.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from printpulse import ui
from printpulse.secure_fs import secure_makedirs

# ─── Constants ────────────────────────────────────────────────────────────────

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".printpulse", "cache")
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".printpulse", "config.json")

MAX_DALLE_ATTEMPTS = 3
DEFAULT_QA_MIN_SCORE = 7


# ─── Tracing Presets ─────────────────────────────────────────────────────────

@dataclass
class TracingPreset:
    """A combination of preprocessing and vtracer parameters."""
    name: str
    # Preprocessing
    blur_radius: float
    threshold: int
    autocontrast_cutoff: int
    # vtracer
    filter_speckle: int
    corner_threshold: int
    length_threshold: float
    splice_threshold: int


TRACING_PRESETS = [
    TracingPreset("default",       blur_radius=0.8, threshold=140, autocontrast_cutoff=5,
                  filter_speckle=4,  corner_threshold=60, length_threshold=4.0, splice_threshold=45),
    TracingPreset("high_contrast", blur_radius=0.5, threshold=100, autocontrast_cutoff=10,
                  filter_speckle=4,  corner_threshold=60, length_threshold=4.0, splice_threshold=45),
    TracingPreset("low_contrast",  blur_radius=0.8, threshold=170, autocontrast_cutoff=2,
                  filter_speckle=2,  corner_threshold=60, length_threshold=3.0, splice_threshold=45),
    TracingPreset("smooth",        blur_radius=1.5, threshold=140, autocontrast_cutoff=5,
                  filter_speckle=8,  corner_threshold=90, length_threshold=6.0, splice_threshold=60),
    TracingPreset("detailed",      blur_radius=0.3, threshold=120, autocontrast_cutoff=3,
                  filter_speckle=2,  corner_threshold=30, length_threshold=2.0, splice_threshold=30),
]


# ─── API Key ──────────────────────────────────────────────────────────────────

def _get_api_key() -> Optional[str]:
    """Retrieve OpenAI API key from env var or config file."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("openai_api_key")
        except Exception:
            pass
    return None


# ─── Cache ────────────────────────────────────────────────────────────────────

def _cache_key(text: str, kind: str, width: float, height: float) -> str:
    h = hashlib.sha256(f"{kind}:dalle:{width:.0f}x{height:.0f}:{text}".encode()).hexdigest()[:16]
    return f"{kind}_{h}"


def _cache_get(key: str) -> Optional[str]:
    path = os.path.join(CACHE_DIR, f"{key}.svg")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def _cache_put(key: str, svg_data: str):
    secure_makedirs(CACHE_DIR)
    path = os.path.join(CACHE_DIR, f"{key}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg_data)


def _cache_image_get(key: str) -> Optional[bytes]:
    """Check for a cached DALL-E raster image."""
    path = os.path.join(CACHE_DIR, f"{key}.png")
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read()
    return None


def _cache_image_put(key: str, image_bytes: bytes):
    """Cache a DALL-E raster image."""
    secure_makedirs(CACHE_DIR)
    path = os.path.join(CACHE_DIR, f"{key}.png")
    with open(path, "wb") as f:
        f.write(image_bytes)


# ─── SVG Path Extraction ────────────────────────────────────────────────────

def _extract_svg_paths(svg_text: str) -> list[str]:
    """Extract path `d` attributes from an SVG string (e.g. vtracer output)."""
    paths: list[str] = []

    cleaned = svg_text.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl >= 0:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()

    try:
        if not cleaned.strip().startswith("<"):
            return paths
        root = ET.fromstring(cleaned)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "path":
                d = elem.get("d", "").strip()
                if d:
                    paths.append(d)
    except ET.ParseError:
        for m in re.finditer(r'd\s*=\s*"([^"]+)"', svg_text):
            d = m.group(1).strip()
            if d:
                paths.append(d)

    return paths


# ─── Path Scaling ────────────────────────────────────────────────────────────

def _scale_paths(
    paths: list[str],
    target_w: float,
    target_h: float,
    fill_width: bool = False,
) -> list[str]:
    """Scale a list of SVG path `d` strings to fit within target dimensions.

    If fill_width=True, scales to fill the target width exactly (height may
    be less than target_h). Use this for hero illustrations that must span
    margin-to-margin.
    """
    if not paths:
        return paths

    xs: list[float] = []
    ys: list[float] = []
    for d in paths:
        tokens = re.findall(r'[MmLlQqCcZzHhVvSsTtAa]|[-+]?\d*\.?\d+', d)
        cmd = 'M'
        coord_idx = 0
        for tok in tokens:
            if tok.isalpha() and len(tok) == 1:
                cmd = tok
                coord_idx = 0
                continue
            try:
                val = float(tok)
            except ValueError:
                continue
            if cmd in ('Z', 'z'):
                pass
            elif cmd == 'H':
                xs.append(val)
            elif cmd == 'V':
                ys.append(val)
            elif cmd in ('m', 'l', 'q', 'c', 't', 's', 'h', 'v'):
                coord_idx += 1  # skip relative for bounding box
            elif cmd in ('M', 'L', 'Q', 'C', 'T', 'S'):
                if coord_idx % 2 == 0:
                    xs.append(val)
                else:
                    ys.append(val)
                coord_idx += 1

    if not xs or not ys:
        return paths

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    src_w = max_x - min_x or 1
    src_h = max_y - min_y or 1
    if fill_width:
        # Scale to fill width, but never exceed target height
        scale = target_w / src_w
        if src_h * scale > target_h:
            scale = target_h / src_h
    else:
        scale = min(target_w / src_w, target_h / src_h)
    # For fill_width, top-align (no vertical centering gap)
    offset_x = (target_w - src_w * scale) / 2
    offset_y = 0.0 if fill_width else (target_h - src_h * scale) / 2

    def _transform_num(val: float, is_x: bool) -> float:
        if is_x:
            return (val - min_x) * scale + offset_x
        return (val - min_y) * scale + offset_y

    scaled: list[str] = []
    for d in paths:
        tokens = re.findall(r'[MmLlQqCcZzHhVvSsTtAa]|[-+]?\d*\.?\d+', d)
        result: list[str] = []
        cmd = 'M'
        coord_idx = 0
        for tok in tokens:
            if tok.isalpha() and len(tok) == 1:
                cmd = tok
                coord_idx = 0
                result.append(tok)
                continue
            try:
                val = float(tok)
            except ValueError:
                result.append(tok)
                continue
            if cmd in ('Z', 'z'):
                result.append(tok)
            elif cmd == 'H':
                result.append(f"{_transform_num(val, True):.1f}")
            elif cmd == 'V':
                result.append(f"{_transform_num(val, False):.1f}")
            elif cmd in ('m', 'l', 'q', 'c', 't', 's', 'h', 'v'):
                result.append(f"{val * scale:.1f}")
                coord_idx += 1
            else:
                is_x = coord_idx % 2 == 0
                result.append(f"{_transform_num(val, is_x):.1f}")
                coord_idx += 1
        scaled.append(" ".join(result))

    return scaled


# ─── Path Measurement ────────────────────────────────────────────────────────

def get_paths_height(paths: list[str]) -> float:
    """Return the height of the bounding box of the given SVG path `d` strings."""
    ys: list[float] = []
    for d in paths:
        tokens = re.findall(r'[MmLlQqCcZzHhVvSsTtAa]|[-+]?\d*\.?\d+', d)
        cmd = 'M'
        coord_idx = 0
        for tok in tokens:
            if tok.isalpha() and len(tok) == 1:
                cmd = tok
                coord_idx = 0
                continue
            try:
                val = float(tok)
            except ValueError:
                continue
            if cmd == 'V':
                ys.append(val)
            elif cmd in ('M', 'L', 'Q', 'C', 'T', 'S'):
                if coord_idx % 2 == 1:
                    ys.append(val)
                coord_idx += 1
            elif cmd in ('m', 'l', 'q', 'c', 't', 's', 'h', 'v'):
                coord_idx += 1
            elif cmd == 'H':
                pass
    if not ys:
        return 0.0
    return max(ys) - min(ys)


# ─── Image Preprocessing (parameterized) ────────────────────────────────────

def _preprocess_image_with_params(image_bytes: bytes, preset: TracingPreset) -> bytes:
    """Convert DALL-E image to high-contrast B&W using given preset params."""
    from printpulse import ensure_dependency
    ensure_dependency("Pillow", "PIL")
    from PIL import Image, ImageFilter, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("L")
    img = ImageOps.autocontrast(img, cutoff=preset.autocontrast_cutoff)
    img = img.filter(ImageFilter.GaussianBlur(radius=preset.blur_radius))
    threshold = preset.threshold
    img = img.point(lambda x: 0 if x < threshold else 255, "1")
    img = img.convert("L")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _preprocess_image(image_bytes: bytes) -> bytes:
    """Convert DALL-E image to high-contrast B&W (default preset)."""
    return _preprocess_image_with_params(image_bytes, TRACING_PRESETS[0])


# ─── Image Tracing (parameterized) ──────────────────────────────────────────

def _trace_image_to_svg_with_params(
    image_bytes: bytes, preset: TracingPreset
) -> Optional[str]:
    """Trace a preprocessed B&W image to SVG using vtracer with given params."""
    from printpulse import ensure_dependency
    vtracer = ensure_dependency("vtracer")

    secure_makedirs(CACHE_DIR)
    tmp_in = None
    tmp_out = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, dir=CACHE_DIR
        ) as f_in:
            f_in.write(image_bytes)
            tmp_in = f_in.name

        tmp_out = tmp_in.replace(".png", "_traced.svg")

        vtracer.convert_image_to_svg_py(
            tmp_in,
            tmp_out,
            colormode="binary",
            mode="spline",
            filter_speckle=preset.filter_speckle,
            corner_threshold=preset.corner_threshold,
            length_threshold=preset.length_threshold,
            splice_threshold=preset.splice_threshold,
        )

        if os.path.isfile(tmp_out):
            with open(tmp_out, "r", encoding="utf-8") as f:
                return f.read()
        return None
    except Exception:
        return None
    finally:
        for p in (tmp_in, tmp_out):
            if p and os.path.isfile(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def _trace_image_to_svg(image_bytes: bytes) -> Optional[str]:
    """Trace using default preset."""
    return _trace_image_to_svg_with_params(image_bytes, TRACING_PRESETS[0])


# ─── Noise Removal ──────────────────────────────────────────────────────────

def _convert_fills_to_strokes(paths: list[str]) -> list[str]:
    """Filter noise paths and remove the white background outline."""
    if not paths:
        return paths

    cleaned: list[str] = []
    for d in paths:
        nums = re.findall(r'[-+]?\d*\.?\d+', d)
        if len(nums) < 6:
            continue
        cleaned.append(d)

    if not cleaned:
        return paths

    # Remove very short paths (ink noise — paths with < 10 coordinate values)
    cleaned = [d for d in cleaned if len(re.findall(r'[-+]?\d*\.?\d+', d)) >= 10]
    if not cleaned:
        return paths

    # Remove largest bounding path if it's 3x bigger than the next (background)
    if len(cleaned) > 2:
        areas: list[float] = []
        for d in cleaned:
            tokens = re.findall(r'[-+]?\d*\.?\d+', d)
            if len(tokens) >= 4:
                nums_f = [float(t) for t in tokens]
                xs_local = nums_f[0::2]
                ys_local = nums_f[1::2]
                if xs_local and ys_local:
                    areas.append(
                        (max(xs_local) - min(xs_local))
                        * (max(ys_local) - min(ys_local))
                    )
                else:
                    areas.append(0)
            else:
                areas.append(0)

        if areas:
            max_idx = areas.index(max(areas))
            sorted_areas = sorted(areas, reverse=True)
            if len(sorted_areas) > 1 and sorted_areas[0] > sorted_areas[1] * 3:
                cleaned.pop(max_idx)

    return cleaned


def _trim_whitespace(paths: list[str], margin_pct: float = 0.05) -> list[str]:
    """Remove outlier paths that inflate the bounding box with whitespace.

    Computes the centroid of all path centres, then removes paths whose
    centre is far from the 5th-95th percentile ink region. This tightens
    the effective bounding box so scaling fills the target area properly.
    """
    if len(paths) < 5:
        return paths

    # Compute per-path centre coordinates
    centres: list[tuple[float, float, int]] = []  # (cx, cy, index)
    for i, d in enumerate(paths):
        nums = re.findall(r'[-+]?\d*\.?\d+', d)
        if len(nums) < 4:
            centres.append((0.0, 0.0, i))
            continue
        vals = [float(n) for n in nums]
        xs = vals[0::2]
        ys = vals[1::2]
        if xs and ys:
            centres.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, i))
        else:
            centres.append((0.0, 0.0, i))

    if not centres:
        return paths

    # Find the 5th-95th percentile range of centre coordinates
    sorted_x = sorted(c[0] for c in centres)
    sorted_y = sorted(c[1] for c in centres)
    n = len(sorted_x)
    lo_idx = max(0, int(n * margin_pct))
    hi_idx = min(n - 1, int(n * (1 - margin_pct)))

    x_lo, x_hi = sorted_x[lo_idx], sorted_x[hi_idx]
    y_lo, y_hi = sorted_y[lo_idx], sorted_y[hi_idx]

    # Expand the range by 20% for tolerance
    x_range = (x_hi - x_lo) or 1
    y_range = (y_hi - y_lo) or 1
    x_lo -= x_range * 0.2
    x_hi += x_range * 0.2
    y_lo -= y_range * 0.2
    y_hi += y_range * 0.2

    # Keep paths whose centre falls within the expanded range
    trimmed = []
    for cx, cy, idx in centres:
        if x_lo <= cx <= x_hi and y_lo <= cy <= y_hi:
            trimmed.append(paths[idx])

    return trimmed if trimmed else paths


# ─── Annotation Labels ──────────────────────────────────────────────────────

_LABEL_PROMPT = (
    "Based on this letter text, give a 1-2 word label for the {kind} "
    "illustration. The label should describe what the illustration depicts "
    "(e.g. 'Tahitian sunset', 'sea turtle', 'palm grove'). Reply with ONLY "
    "the label, nothing else.\n\n{snippet}"
)


def _get_illustration_label(
    letter_text: str, kind: str, api_key: str
) -> str:
    """Ask GPT-4o for a 1-2 word annotation label for an illustration."""
    from printpulse import ensure_dependency
    openai = ensure_dependency("openai")

    snippet = letter_text[:400].strip()
    prompt = _LABEL_PROMPT.format(kind=kind, snippet=snippet)

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
        )
        label = response.choices[0].message.content or ""
        # Clean up: remove quotes, trim to 2 words max
        label = label.strip().strip('"').strip("'")
        words = label.split()
        if len(words) > 3:
            words = words[:3]
        return " ".join(words)
    except Exception:
        return ""


def _generate_annotation_paths(
    label: str,
    x: float,
    y: float,
    font_size: float = 10.0,
    angle_deg: float = -12.0,
) -> list[str]:
    """Render a Hershey font label at an angle, returning SVG path `d` strings.

    The label is positioned at (x, y) and rotated by angle_deg.
    """
    if not label:
        return []

    from HersheyFonts import HersheyFonts

    font = HersheyFonts()
    font.load_default_font("cursive")
    font.normalize_rendering(font_size)

    segments = list(font.lines_for_text(label))
    if not segments:
        return []

    # Collect all coords for normalization
    all_x = []
    all_y = []
    for (x1, y1), (x2, y2) in segments:
        all_x.extend([x1, x2])
        all_y.extend([-y1, -y2])  # flip y for SVG

    if not all_x or not all_y:
        return []

    min_gx = min(all_x)
    min_gy = min(all_y)

    # Apply rotation transform
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    def rotate(px: float, py: float) -> tuple[float, float]:
        # Translate to origin, rotate, translate to position
        rx = px * cos_a - py * sin_a + x
        ry = px * sin_a + py * cos_a + y
        return (rx, ry)

    paths: list[str] = []
    for (x1, y1), (x2, y2) in segments:
        # Normalize and flip y
        nx1 = x1 - min_gx
        ny1 = -y1 - min_gy
        nx2 = x2 - min_gx
        ny2 = -y2 - min_gy
        rx1, ry1 = rotate(nx1, ny1)
        rx2, ry2 = rotate(nx2, ny2)
        paths.append(f"M {rx1:.1f} {ry1:.1f} L {rx2:.1f} {ry2:.1f}")

    return paths


def _generate_arrow_paths(
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
) -> list[str]:
    """Generate a simple hand-drawn style arrow from (from_x, from_y) pointing
    toward (to_x, to_y). Returns SVG path `d` strings."""
    # Main shaft with slight curve for hand-drawn feel
    mid_x = (from_x + to_x) / 2 + 5
    mid_y = (from_y + to_y) / 2 - 3
    shaft = f"M {from_x:.1f} {from_y:.1f} Q {mid_x:.1f} {mid_y:.1f} {to_x:.1f} {to_y:.1f}"

    # Arrowhead
    dx = to_x - from_x
    dy = to_y - from_y
    length = math.sqrt(dx * dx + dy * dy) or 1
    ux, uy = dx / length, dy / length
    # Perpendicular
    px, py = -uy, ux
    head_size = 8
    ax = to_x - ux * head_size + px * head_size * 0.4
    ay = to_y - uy * head_size + py * head_size * 0.4
    bx = to_x - ux * head_size - px * head_size * 0.4
    by = to_y - uy * head_size - py * head_size * 0.4
    head1 = f"M {to_x:.1f} {to_y:.1f} L {ax:.1f} {ay:.1f}"
    head2 = f"M {to_x:.1f} {to_y:.1f} L {bx:.1f} {by:.1f}"

    return [shaft, head1, head2]


# ─── DALL-E Image Generation ────────────────────────────────────────────────

_HERO_DALLE_PROMPT = (
    "Victorian naturalist field journal pen-and-ink illustration. "
    "Black ink on white paper, no colour. Detailed line work with "
    "cross-hatching for shading. Wide landscape scene depicting: {subject}\n\n"
    "Style: 19th-century scientific expedition sketch with fine crosshatch "
    "shading. Single continuous ink strokes only, no solid fills, no washes. "
    "No text, no labels, no lettering, no border frame."
)

_SUPPORTING_DALLE_PROMPT = (
    "Victorian naturalist specimen study, pen-and-ink sketch on white paper. "
    "Single centred subject: {subject}\n\n"
    "Style: 19th-century botanical or zoological plate with fine ink detail "
    "and crosshatch shading. No text, no labels, no lettering, no border. "
    "Black ink only, no colour, no grey washes."
)

# Stricter prompts appended on retry attempts
_RETRY_SUFFIX_1 = (
    "\n\nCRITICAL: The previous image was too complex for vector tracing. "
    "Use ONLY thin black line strokes on pure white paper. NO shading, "
    "NO cross-hatching, NO grey tones, NO solid filled areas. "
    "Simple, clean outlines only. High contrast."
)

_RETRY_SUFFIX_2 = (
    "\n\nCRITICAL: Extremely simple line drawing needed. Draw the subject "
    "using the absolute minimum number of clean, thin black lines on "
    "pure white. Think single-stroke sketch — just the essential outline "
    "shapes. No texture, no detail, no hatching whatsoever."
)


def _summarize_for_dalle(letter_text: str, kind: str = "hero") -> str:
    """Extract a concise visual subject from letter text for DALL-E."""
    snippet = letter_text[:400].strip()
    if kind == "hero":
        return (
            f"Based on this letter, illustrate the main scene described:\n"
            f"{snippet}"
        )
    return (
        f"Based on this letter, pick ONE small specific object or detail "
        f"mentioned and illustrate it as a specimen study:\n{snippet}"
    )


def _generate_dalle_image(
    prompt: str,
    api_key: str,
    size: str = "1792x1024",
    theme: str = "green",
) -> Optional[bytes]:
    """Generate an image via DALL-E 3 API. Returns PNG bytes or None."""
    from printpulse import ensure_dependency
    openai = ensure_dependency("openai")
    requests = ensure_dependency("requests")

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size=size,
            quality="hd",
            response_format="url",
        )

        image_url = response.data[0].url
        if not image_url:
            ui.error_panel("DALL-E returned no image URL.", theme)
            return None

        resp = requests.get(image_url, timeout=120)
        resp.raise_for_status()
        return resp.content

    except Exception as e:
        ui.error_panel(f"DALL-E image generation failed: {e}", theme)
        return None


# ─── QA: GPT-4o Vision Evaluation ───────────────────────────────────────────

_DALLE_QA_PROMPT = """You are evaluating an AI-generated pen-and-ink illustration for suitability \
as input to a vector tracing algorithm that will convert it to single-stroke \
SVG paths for a pen plotter.

The intended subject is: {subject}

Evaluate the image on these criteria:
1. Are the lines clean black ink on a white background? (no grey washes, \
no gradients, no filled regions)
2. Is the subject clearly recognizable?
3. Are the strokes well-separated (not merged into solid black areas)?
4. Is the composition suitable for tracing to clean vector paths?

Respond in EXACTLY this format (nothing else):
SCORE: <number 1-10>
FEEDBACK: <one sentence explaining the main issue, or "Good" if score >= 7>"""

_TRACE_QA_PROMPT = """You are evaluating a vector-traced illustration that will be drawn by a pen \
plotter. The image shows black strokes on a white background — this is the \
traced output from a pen-and-ink illustration.

The intended subject was: {subject}

Evaluate the traced result:
1. Is the subject still recognizable after tracing?
2. Are the main elements (shapes, objects, scene) preserved and identifiable?
3. Are the strokes clean and well-defined (not fragmented noise)?
4. Would a viewer understand what this depicts?

Respond in EXACTLY this format (nothing else):
SCORE: <number 1-10>
FEEDBACK: <one sentence explaining the main issue, or "Good" if score >= 7>"""


def _qa_vision_call(
    image_bytes: bytes, prompt: str, api_key: str
) -> tuple[int, str]:
    """Send an image to GPT-4o Vision for evaluation.

    Returns (score 1-10, feedback string).
    """
    from printpulse import ensure_dependency
    openai = ensure_dependency("openai")

    try:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        client = openai.OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=150,
        )
        text = response.choices[0].message.content or ""

        score_match = re.search(r"SCORE:\s*(\d+)", text)
        feedback_match = re.search(r"FEEDBACK:\s*(.+)", text)
        score = int(score_match.group(1)) if score_match else 5
        feedback = feedback_match.group(1).strip() if feedback_match else text.strip()
        return (min(max(score, 1), 10), feedback)

    except Exception as e:
        return (5, f"QA evaluation failed: {e}")


# ─── Path-to-Raster Preview Rendering ───────────────────────────────────────

def _render_paths_to_image(
    paths: list[str], width: int = 800, height: int = 600
) -> bytes:
    """Render SVG path `d` strings to a PIL raster preview for QA.

    Returns PNG bytes. Handles M/L/C/Q/H/V/Z commands with cubic bezier
    sampling for reasonable visual accuracy.
    """
    from printpulse import ensure_dependency
    ensure_dependency("Pillow", "PIL")
    from PIL import Image, ImageDraw

    # ── Pass 1: collect all coordinates for bounding box ──
    all_coords: list[tuple[float, float]] = []

    for d in paths:
        tokens = re.findall(r'[MmLlQqCcZzHhVvSsTtAa]|[-+]?\d*\.?\d+', d)
        cmd = 'M'
        cx, cy = 0.0, 0.0
        nums: list[float] = []

        for tok in tokens:
            if tok.isalpha() and len(tok) == 1:
                cmd = tok
                nums = []
                continue
            try:
                nums.append(float(tok))
            except ValueError:
                continue

            if cmd == 'M' and len(nums) >= 2:
                cx, cy = nums[-2], nums[-1]
                all_coords.append((cx, cy))
                if len(nums) >= 2:
                    nums = []
            elif cmd == 'L' and len(nums) >= 2:
                cx, cy = nums[-2], nums[-1]
                all_coords.append((cx, cy))
                nums = []
            elif cmd == 'C' and len(nums) >= 6:
                # Cubic bezier — sample control and end points
                all_coords.append((nums[0], nums[1]))
                all_coords.append((nums[2], nums[3]))
                cx, cy = nums[4], nums[5]
                all_coords.append((cx, cy))
                nums = []
            elif cmd == 'Q' and len(nums) >= 4:
                all_coords.append((nums[0], nums[1]))
                cx, cy = nums[2], nums[3]
                all_coords.append((cx, cy))
                nums = []
            elif cmd == 'H' and len(nums) >= 1:
                cx = nums[-1]
                all_coords.append((cx, cy))
                nums = []
            elif cmd == 'V' and len(nums) >= 1:
                cy = nums[-1]
                all_coords.append((cx, cy))
                nums = []

    if not all_coords:
        # Return blank white image
        img = Image.new("L", (width, height), 255)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    min_x = min(c[0] for c in all_coords)
    max_x = max(c[0] for c in all_coords)
    min_y = min(c[1] for c in all_coords)
    max_y = max(c[1] for c in all_coords)

    src_w = max_x - min_x or 1
    src_h = max_y - min_y or 1
    padding = 0.05
    usable_w = width * (1 - 2 * padding)
    usable_h = height * (1 - 2 * padding)
    sc = min(usable_w / src_w, usable_h / src_h)
    pad_x = (width - src_w * sc) / 2
    pad_y = (height - src_h * sc) / 2

    def tx(x: float, y: float) -> tuple[float, float]:
        return ((x - min_x) * sc + pad_x, (y - min_y) * sc + pad_y)

    # ── Pass 2: draw paths ──
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)

    for d in paths:
        tokens = re.findall(r'[MmLlQqCcZzHhVvSsTtAa]|[-+]?\d*\.?\d+', d)
        cmd = 'M'
        cx, cy = 0.0, 0.0
        mx, my = 0.0, 0.0  # moveto anchor for Z
        nums = []

        for tok in tokens:
            if tok.isalpha() and len(tok) == 1:
                cmd = tok
                nums = []
                continue
            try:
                nums.append(float(tok))
            except ValueError:
                continue

            if cmd == 'M' and len(nums) >= 2:
                cx, cy = nums[-2], nums[-1]
                mx, my = cx, cy
                nums = []
            elif cmd == 'L' and len(nums) >= 2:
                draw.line([tx(cx, cy), tx(nums[-2], nums[-1])], fill=0, width=2)
                cx, cy = nums[-2], nums[-1]
                nums = []
            elif cmd == 'C' and len(nums) >= 6:
                p0 = (cx, cy)
                p1 = (nums[0], nums[1])
                p2 = (nums[2], nums[3])
                p3 = (nums[4], nums[5])
                prev = tx(*p0)
                for i in range(1, 11):
                    t = i / 10.0
                    u = 1 - t
                    bx = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
                    by = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
                    cur = tx(bx, by)
                    draw.line([prev, cur], fill=0, width=2)
                    prev = cur
                cx, cy = p3
                nums = []
            elif cmd == 'Q' and len(nums) >= 4:
                p0 = (cx, cy)
                p1 = (nums[0], nums[1])
                p2 = (nums[2], nums[3])
                prev = tx(*p0)
                for i in range(1, 11):
                    t = i / 10.0
                    u = 1 - t
                    bx = u**2 * p0[0] + 2 * u * t * p1[0] + t**2 * p2[0]
                    by = u**2 * p0[1] + 2 * u * t * p1[1] + t**2 * p2[1]
                    cur = tx(bx, by)
                    draw.line([prev, cur], fill=0, width=2)
                    prev = cur
                cx, cy = p2
                nums = []
            elif cmd == 'H' and len(nums) >= 1:
                draw.line([tx(cx, cy), tx(nums[-1], cy)], fill=0, width=2)
                cx = nums[-1]
                nums = []
            elif cmd == 'V' and len(nums) >= 1:
                draw.line([tx(cx, cy), tx(cx, nums[-1])], fill=0, width=2)
                cy = nums[-1]
                nums = []
            elif cmd in ('Z', 'z'):
                draw.line([tx(cx, cy), tx(mx, my)], fill=0, width=2)
                cx, cy = mx, my
                nums = []

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─── QA Orchestrator ─────────────────────────────────────────────────────────

def _generate_with_qa(
    letter_text: str,
    kind: str,
    prompt_template: str,
    dalle_size: str,
    width_pt: float,
    height_pt: float,
    theme: str,
    api_key: str,
    extra_prompt_suffix: str = "",
    min_score: int = DEFAULT_QA_MIN_SCORE,
    fill_width: bool = False,
) -> Optional[list[str]]:
    """Generate a DALL-E illustration with GPT-4o Vision QA feedback loop.

    Tries up to MAX_DALLE_ATTEMPTS DALL-E generations. For each, tries
    all TRACING_PRESETS and evaluates traced output with GPT-4o Vision.
    Returns the best list of path `d` strings, or None on total failure.
    """
    label = "HERO ILLUSTRATION" if kind == "hero" else "SUPPORTING SKETCH"
    subject = _summarize_for_dalle(letter_text, kind)
    best_paths: Optional[list[str]] = None
    best_trace_score = 0
    best_svg_str: Optional[str] = None
    api_calls = {"dalle": 0, "qa": 0}

    ui.retro_panel(
        f"[ QA PIPELINE — {label} ]",
        f"Starting DALL-E 3 + vtracer + GPT-4o Vision QA loop\n"
        f"  Min acceptable score: {min_score}/10\n"
        f"  Max DALL-E attempts:  {MAX_DALLE_ATTEMPTS}\n"
        f"  Tracing presets:      {len(TRACING_PRESETS)}",
        theme,
    )

    for attempt in range(MAX_DALLE_ATTEMPTS):
        # ── Build prompt (stricter on retries) ──
        full_subject = subject + extra_prompt_suffix
        prompt = prompt_template.format(subject=full_subject)
        if attempt == 1:
            prompt += _RETRY_SUFFIX_1
        elif attempt >= 2:
            prompt += _RETRY_SUFFIX_2

        ui.success_message(
            f"{'═' * 60}", theme
        )
        ui.success_message(
            f"  DALL-E ATTEMPT {attempt + 1}/{MAX_DALLE_ATTEMPTS}"
            + (" (stricter prompt)" if attempt > 0 else ""),
            theme,
        )
        ui.success_message(
            f"{'─' * 60}", theme
        )

        # ── Step 1: Generate or load DALL-E image ──
        img_ck = _cache_key(
            letter_text + extra_prompt_suffix,
            f"{kind}_img_v{attempt}",
            width_pt,
            height_pt,
        )
        image_bytes = _cache_image_get(img_ck)

        if image_bytes:
            ui.success_message(
                "  [CACHE HIT] DALL-E image loaded from cache.", theme
            )
        else:
            ui.success_message(
                f"  [DALL-E 3] Generating {kind} illustration...", theme
            )
            image_bytes = _generate_dalle_image(prompt, api_key, dalle_size, theme)
            api_calls["dalle"] += 1
            if not image_bytes:
                ui.success_message(
                    "  [FAIL] DALL-E generation failed, trying next attempt...",
                    theme,
                )
                continue
            _cache_image_put(img_ck, image_bytes)
            ui.success_message(
                f"  [OK] DALL-E image received ({len(image_bytes):,} bytes).", theme
            )

        # ── Step 2 (Stage A): Evaluate raw DALL-E image ──
        ui.success_message(
            "  [STAGE A] Evaluating DALL-E image with GPT-4o Vision...", theme
        )
        dalle_qa_prompt = _DALLE_QA_PROMPT.format(subject=full_subject)
        dalle_score, dalle_feedback = _qa_vision_call(
            image_bytes, dalle_qa_prompt, api_key
        )
        api_calls["qa"] += 1

        score_bar = "█" * dalle_score + "░" * (10 - dalle_score)
        verdict = "✓ PASS" if dalle_score >= min_score else "✗ FAIL"
        ui.success_message(
            f"  [STAGE A] Score: [{score_bar}] {dalle_score}/10 {verdict}",
            theme,
        )
        ui.success_message(
            f"  [STAGE A] Feedback: {dalle_feedback}", theme
        )

        if dalle_score < min_score and attempt < MAX_DALLE_ATTEMPTS - 1:
            ui.success_message(
                "  [STAGE A] Image quality too low — will regenerate with "
                "stricter prompt...",
                theme,
            )
            continue

        # ── Step 3 (Stage B): Try tracing presets ──
        ui.success_message(
            f"  [STAGE B] Trying {len(TRACING_PRESETS)} tracing presets...", theme
        )

        for pi, preset in enumerate(TRACING_PRESETS):
            ui.success_message(
                f"    [{pi + 1}/{len(TRACING_PRESETS)}] Preset '{preset.name}': "
                f"blur={preset.blur_radius} thresh={preset.threshold} "
                f"speckle={preset.filter_speckle} len={preset.length_threshold}",
                theme,
            )

            processed = _preprocess_image_with_params(image_bytes, preset)
            svg_str = _trace_image_to_svg_with_params(processed, preset)
            if not svg_str:
                ui.success_message(
                    f"    [{pi + 1}/{len(TRACING_PRESETS)}] Tracing failed, "
                    f"skipping...",
                    theme,
                )
                continue

            paths = _extract_svg_paths(svg_str)
            if not paths:
                continue
            paths = _convert_fills_to_strokes(paths)
            if not paths:
                continue
            paths = _trim_whitespace(paths)

            ui.success_message(
                f"    [{pi + 1}/{len(TRACING_PRESETS)}] Traced {len(paths)} "
                f"paths (trimmed), rendering preview for QA...",
                theme,
            )

            # Render preview and evaluate with GPT-4o Vision
            preview = _render_paths_to_image(paths, 800, 600)
            trace_qa_prompt = _TRACE_QA_PROMPT.format(subject=full_subject)
            trace_score, trace_feedback = _qa_vision_call(
                preview, trace_qa_prompt, api_key
            )
            api_calls["qa"] += 1

            score_bar = "█" * trace_score + "░" * (10 - trace_score)
            verdict = "✓ PASS" if trace_score >= min_score else "✗ FAIL"
            ui.success_message(
                f"    [{pi + 1}/{len(TRACING_PRESETS)}] Score: [{score_bar}] "
                f"{trace_score}/10 {verdict}",
                theme,
            )
            ui.success_message(
                f"    [{pi + 1}/{len(TRACING_PRESETS)}] Feedback: "
                f"{trace_feedback}",
                theme,
            )

            if trace_score > best_trace_score:
                best_trace_score = trace_score
                best_paths = paths
                best_svg_str = svg_str

            if trace_score >= min_score:
                ui.success_message(
                    f"  [STAGE B] ✓ Accepted preset '{preset.name}' with "
                    f"score {trace_score}/10!",
                    theme,
                )
                break

        if best_trace_score >= min_score:
            break  # Done — we have a good result

        if attempt < MAX_DALLE_ATTEMPTS - 1:
            ui.success_message(
                f"  [STAGE B] Best trace score {best_trace_score}/10 "
                f"(need {min_score}), regenerating DALL-E image...",
                theme,
            )

    # ── Final result ──
    ui.success_message(f"{'═' * 60}", theme)

    if best_paths and best_svg_str:
        ck = _cache_key(
            letter_text + extra_prompt_suffix, kind, width_pt, height_pt
        )
        _cache_put(ck, best_svg_str)

        scaled = _scale_paths(best_paths, width_pt, height_pt, fill_width=fill_width)
        ui.retro_panel(
            f"[ {label} — COMPLETE ]",
            f"Result: {len(scaled)} paths, QA score {best_trace_score}/10\n"
            f"API calls: {api_calls['dalle']} DALL-E + {api_calls['qa']} QA "
            f"evaluations",
            theme,
        )
        return scaled

    ui.error_panel(
        f"Could not generate acceptable {label.lower()} after "
        f"{MAX_DALLE_ATTEMPTS} DALL-E attempts x {len(TRACING_PRESETS)} "
        f"tracing presets.",
        theme,
    )
    return None


# ─── Public API ──────────────────────────────────────────────────────────────

def generate_hero_illustration(
    letter_text: str,
    width_pt: float,
    height_pt: float,
    theme: str = "green",
) -> Optional[list[str]]:
    """Generate a hero illustration via DALL-E 3 + vtracer + QA loop.

    Returns list of SVG path `d` strings scaled to fit width_pt x height_pt,
    or None on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        ui.error_panel(
            "No OpenAI API key found. Set OPENAI_API_KEY env var or add to "
            "~/.printpulse/config.json. Skipping illustrations.",
            theme,
        )
        return None

    # Check SVG cache (fully QA-approved result)
    ck = _cache_key(letter_text, "hero", width_pt, height_pt)
    cached = _cache_get(ck)
    if cached:
        ui.success_message("Hero illustration loaded from cache.", theme)
        paths = _extract_svg_paths(cached)
        return _scale_paths(paths, width_pt, height_pt, fill_width=True) if paths else None

    return _generate_with_qa(
        letter_text=letter_text,
        kind="hero",
        prompt_template=_HERO_DALLE_PROMPT,
        dalle_size="1792x1024",
        width_pt=width_pt,
        height_pt=height_pt,
        theme=theme,
        api_key=api_key,
        fill_width=True,
    )


def generate_hero_annotation(
    letter_text: str,
    hero_width: float,
    hero_height: float,
    theme: str = "green",
) -> list[str]:
    """Generate annotation paths for the hero illustration.

    Returns SVG path `d` strings for a label + arrow, positioned relative
    to the hero's top-left (0, 0) corner.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    label = _get_illustration_label(letter_text, "hero scene", api_key)
    if not label:
        return []

    ui.success_message(f"Hero annotation label: '{label}'", theme)

    paths: list[str] = []
    # Place label tight to bottom-right of hero, at a slight angle
    label_x = hero_width * 0.68
    label_y = hero_height + 2
    paths.extend(
        _generate_annotation_paths(label, label_x, label_y, font_size=8.0, angle_deg=-6.0)
    )

    # Short arrow from label pointing into the illustration
    arrow_from_x = label_x - 3
    arrow_from_y = label_y - 2
    arrow_to_x = hero_width * 0.60
    arrow_to_y = hero_height * 0.85
    paths.extend(_generate_arrow_paths(arrow_from_x, arrow_from_y, arrow_to_x, arrow_to_y))

    return paths


def generate_sketch_annotation(
    letter_text: str,
    sketch_width: float,
    sketch_height: float,
    theme: str = "green",
) -> list[str]:
    """Generate annotation paths for the supporting sketch.

    Returns SVG path `d` strings for a handwritten label at an angle,
    positioned relative to the sketch's top-left (0, 0) corner.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    label = _get_illustration_label(letter_text, "supporting specimen detail", api_key)
    if not label:
        return []

    ui.success_message(f"Sketch annotation label: '{label}'", theme)

    paths: list[str] = []
    # Place label below the sketch, tilted
    label_x = sketch_width * 0.15
    label_y = sketch_height + 4
    paths.extend(
        _generate_annotation_paths(label, label_x, label_y, font_size=7.0, angle_deg=-12.0)
    )

    # Small arrow from label pointing up into the sketch
    arrow_from_x = label_x - 2
    arrow_from_y = label_y - 2
    arrow_to_x = sketch_width * 0.35
    arrow_to_y = sketch_height * 0.7
    paths.extend(_generate_arrow_paths(arrow_from_x, arrow_from_y, arrow_to_x, arrow_to_y))

    return paths


def generate_supporting_sketch(
    letter_text: str,
    hero_subject: str,
    width_pt: float,
    height_pt: float,
    theme: str = "green",
) -> Optional[list[str]]:
    """Generate a supporting specimen sketch via DALL-E 3 + vtracer + QA loop.

    Returns list of SVG path `d` strings scaled to fit width_pt x height_pt,
    or None on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    extra = ""
    if hero_subject:
        extra = (
            f"\n\nIMPORTANT: Do NOT illustrate the main landscape scene. "
            f"The hero illustration already covers: {hero_subject[:150]}. "
            f"Pick a different, smaller detail from the letter."
        )

    # Check SVG cache
    ck = _cache_key(letter_text + hero_subject, "supporting", width_pt, height_pt)
    cached = _cache_get(ck)
    if cached:
        ui.success_message("Supporting sketch loaded from cache.", theme)
        paths = _extract_svg_paths(cached)
        return _scale_paths(paths, width_pt, height_pt) if paths else None

    return _generate_with_qa(
        letter_text=letter_text,
        kind="supporting",
        prompt_template=_SUPPORTING_DALLE_PROMPT,
        dalle_size="1024x1024",
        width_pt=width_pt,
        height_pt=height_pt,
        theme=theme,
        api_key=api_key,
        extra_prompt_suffix=extra,
    )
