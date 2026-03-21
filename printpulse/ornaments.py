"""Static decorative ornaments for letter mode.

All paths are single-stroke line art suitable for pen plotters.
Coordinates are in points (72/inch). Each function returns a list of
SVG path `d` attribute strings that can be added to an <svg> document.
"""

from __future__ import annotations

import math
from typing import List

# ─── Helper ───────────────────────────────────────────────────────────────────

def _gear(cx: float, cy: float, outer_r: float, inner_r: float, teeth: int = 8) -> str:
    """Generate a single-stroke gear/cog path centered at (cx, cy)."""
    pts: list[tuple[float, float]] = []
    for i in range(teeth * 2):
        angle = math.pi * 2 * i / (teeth * 2) - math.pi / 2
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    # Close the gear
    pts.append(pts[0])
    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f}"
    for x, y in pts[1:]:
        d += f" L {x:.1f},{y:.1f}"

    # Add axle circle (small center circle)
    axle_r = inner_r * 0.35
    steps = 16
    d += f" M {cx + axle_r:.1f},{cy:.1f}"
    for i in range(1, steps + 1):
        angle = math.pi * 2 * i / steps
        d += f" L {cx + axle_r * math.cos(angle):.1f},{cy + axle_r * math.sin(angle):.1f}"
    return d


def _flourish_corner(cx: float, cy: float, size: float, flip_x: bool = False, flip_y: bool = False) -> str:
    """Generate a Victorian scroll/vine corner ornament.

    The ornament is drawn in the quadrant facing inward from (cx, cy).
    flip_x / flip_y mirror the curves for different corners.
    """
    sx = -1 if flip_x else 1
    sy = -1 if flip_y else 1
    s = size

    # A flowing scroll with two curls
    points = [
        (cx, cy + sy * s * 0.1),
        # Main spiral outward
        (cx + sx * s * 0.15, cy + sy * s * 0.05),
        (cx + sx * s * 0.3, cy + sy * s * 0.15),
        (cx + sx * s * 0.25, cy + sy * s * 0.3),
        (cx + sx * s * 0.1, cy + sy * s * 0.25),
        (cx + sx * s * 0.15, cy + sy * s * 0.4),
        (cx + sx * s * 0.3, cy + sy * s * 0.5),
        # Second curl
        (cx + sx * s * 0.4, cy + sy * s * 0.35),
        (cx + sx * s * 0.5, cy + sy * s * 0.15),
        (cx + sx * s * 0.45, cy + sy * s * 0.05),
    ]

    d = f"M {points[0][0]:.1f},{points[0][1]:.1f}"
    # Use quadratic bezier curves for flowing lines
    for i in range(1, len(points) - 1, 2):
        cp = points[i]
        ep = points[i + 1] if i + 1 < len(points) else points[i]
        d += f" Q {cp[0]:.1f},{cp[1]:.1f} {ep[0]:.1f},{ep[1]:.1f}"

    # Small decorative dot (tiny circle) at the end
    ex, ey = points[-1]
    dot_r = s * 0.02
    d += f" M {ex + dot_r:.1f},{ey:.1f}"
    for j in range(1, 9):
        a = math.pi * 2 * j / 8
        d += f" L {ex + dot_r * math.cos(a):.1f},{ey + dot_r * math.sin(a):.1f}"

    return d


def _simple_corner(cx: float, cy: float, size: float, flip_x: bool = False, flip_y: bool = False) -> str:
    """Small decorative L-bracket with a diamond."""
    sx = -1 if flip_x else 1
    sy = -1 if flip_y else 1
    s = size * 0.4

    # L-bracket
    d = (
        f"M {cx:.1f},{cy + sy * s:.1f} "
        f"L {cx:.1f},{cy:.1f} "
        f"L {cx + sx * s:.1f},{cy:.1f}"
    )
    # Small diamond at corner
    ds = s * 0.15
    d += (
        f" M {cx + sx * ds:.1f},{cy:.1f} "
        f"L {cx:.1f},{cy + sy * ds:.1f} "
        f"L {cx - sx * ds:.1f},{cy:.1f} "
        f"L {cx:.1f},{cy - sy * ds:.1f} Z"
    )
    return d


# ─── Public API ───────────────────────────────────────────────────────────────

def corner_ornaments(
    page_w: float, page_h: float, margin: float,
    style: str = "gears", size: float = 36.0,
) -> List[str]:
    """Generate corner ornaments for all four corners.

    Returns list of SVG path `d` strings.
    """
    paths: list[str] = []
    inset = margin * 0.5  # Place ornaments just inside the margin

    corners = [
        (inset, inset, False, False),                         # top-left
        (page_w - inset, inset, True, False),                 # top-right
        (inset, page_h - inset, False, True),                 # bottom-left
        (page_w - inset, page_h - inset, True, True),         # bottom-right
    ]

    for cx, cy, fx, fy in corners:
        if style == "gears":
            outer_r = size * 0.5
            inner_r = size * 0.35
            paths.append(_gear(cx, cy, outer_r, inner_r, teeth=8))
        elif style == "flourishes":
            paths.append(_flourish_corner(cx, cy, size, flip_x=fx, flip_y=fy))
        elif style == "simple":
            paths.append(_simple_corner(cx, cy, size, flip_x=fx, flip_y=fy))
        else:
            paths.append(_gear(cx, cy, size * 0.5, size * 0.35, teeth=8))

    return paths


def header_banner(
    x: float, y: float, width: float, height: float,
    frame_style: str = "ornamental",
) -> List[str]:
    """Generate the decorative frame around the header text area.

    Returns list of SVG path `d` strings for the frame border and
    decorative elements. Text rendering is done separately.
    """
    paths: list[str] = []

    # Main rectangle
    paths.append(
        f"M {x:.1f},{y:.1f} "
        f"L {x + width:.1f},{y:.1f} "
        f"L {x + width:.1f},{y + height:.1f} "
        f"L {x:.1f},{y + height:.1f} Z"
    )

    if frame_style == "ornamental":
        # Double-line border (inset by 3pt)
        inset = 3.0
        ix, iy = x + inset, y + inset
        iw, ih = width - 2 * inset, height - 2 * inset
        paths.append(
            f"M {ix:.1f},{iy:.1f} "
            f"L {ix + iw:.1f},{iy:.1f} "
            f"L {ix + iw:.1f},{iy + ih:.1f} "
            f"L {ix:.1f},{iy + ih:.1f} Z"
        )

        # Top decorative bar — small notches
        notch_w = 6.0
        notch_h = 3.0
        cx = x + width / 2
        for offset in (-40, -20, 0, 20, 40):
            nx = cx + offset - notch_w / 2
            paths.append(
                f"M {nx:.1f},{y:.1f} "
                f"L {nx:.1f},{y - notch_h:.1f} "
                f"L {nx + notch_w:.1f},{y - notch_h:.1f} "
                f"L {nx + notch_w:.1f},{y:.1f}"
            )

        # Small corner diamonds inside the frame
        diamond_size = 4.0
        for dx, dy in [(ix, iy), (ix + iw, iy), (ix, iy + ih), (ix + iw, iy + ih)]:
            paths.append(
                f"M {dx:.1f},{dy - diamond_size:.1f} "
                f"L {dx + diamond_size:.1f},{dy:.1f} "
                f"L {dx:.1f},{dy + diamond_size:.1f} "
                f"L {dx - diamond_size:.1f},{dy:.1f} Z"
            )

    elif frame_style == "simple":
        # Just the outer rectangle (already added)
        pass

    return paths


def header_rule(x: float, y: float, width: float, style: str = "ornamental") -> List[str]:
    """Decorative horizontal rule below the header.

    Returns list of SVG path `d` strings.
    """
    paths: list[str] = []

    if style == "ornamental":
        # Main line
        paths.append(f"M {x:.1f},{y:.1f} L {x + width:.1f},{y:.1f}")
        # Small diamond in center
        cx = x + width / 2
        ds = 4.0
        paths.append(
            f"M {cx:.1f},{y - ds:.1f} "
            f"L {cx + ds:.1f},{y:.1f} "
            f"L {cx:.1f},{y + ds:.1f} "
            f"L {cx - ds:.1f},{y:.1f} Z"
        )
        # Small ticks at ends
        tick = 3.0
        paths.append(f"M {x:.1f},{y - tick:.1f} L {x:.1f},{y + tick:.1f}")
        paths.append(f"M {x + width:.1f},{y - tick:.1f} L {x + width:.1f},{y + tick:.1f}")

    elif style == "double":
        gap = 2.0
        paths.append(f"M {x:.1f},{y:.1f} L {x + width:.1f},{y:.1f}")
        paths.append(f"M {x:.1f},{y + gap:.1f} L {x + width:.1f},{y + gap:.1f}")

    else:
        # Single line
        paths.append(f"M {x:.1f},{y:.1f} L {x + width:.1f},{y:.1f}")

    return paths


def signature_rule(x: float, y: float, width: float) -> List[str]:
    """Short line for signature placement."""
    return [f"M {x:.1f},{y:.1f} L {x + width:.1f},{y:.1f}"]
