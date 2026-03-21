import os
import platform
import subprocess
import tempfile

import svgwrite

from printpulse.config import Config, FONT_MAP
from printpulse import ui


def get_available_fonts() -> list[tuple[str, str]]:
    """Return a list of (font_id, display_label) tuples for available Hershey fonts."""
    from HersheyFonts import HersheyFonts

    hf = HersheyFonts()
    all_fonts = set(hf.default_font_names)

    # Start with curated map entries (nicely named)
    result = []
    seen = set()
    for display_name, font_id in FONT_MAP.items():
        if font_id in all_fonts:
            result.append((font_id, f"{display_name} ({font_id})"))
            seen.add(font_id)

    # Add any remaining fonts not in the curated map
    for font_id in sorted(all_fonts - seen):
        result.append((font_id, font_id))

    return result


def _sanitize_text(text: str) -> str:
    """Replace Unicode typographic characters with ASCII equivalents.

    RSS feeds and word processors often use smart quotes, em-dashes, and
    other fancy Unicode that Hershey fonts / thermal printers can't render.
    """
    replacements = {
        "\u2018": "'",   # left single curly quote
        "\u2019": "'",   # right single curly quote (smart apostrophe)
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
        "\u00AB": '"',   # left guillemet
        "\u00BB": '"',   # right guillemet
        "\u2039": "'",   # single left angle quote
        "\u203A": "'",   # single right angle quote
        "\uFEFF": "",    # BOM / zero-width no-break space
        "\u200B": "",    # zero-width space
        "\u200C": "",    # zero-width non-joiner
        "\u200D": "",    # zero-width joiner
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def _measure_text_width(font, text: str) -> float:
    """Measure the width of text rendered with the given Hershey font."""
    if not text.strip():
        return 0.0
    xs = []
    for (x1, _), (x2, _) in font.lines_for_text(text):
        xs.extend([x1, x2])
    if not xs:
        return 0.0
    return max(xs) - min(xs)


def _word_wrap(font, text: str, max_width: float) -> list[str]:
    """Wrap text into lines that fit within max_width."""
    paragraphs = text.split("\n")
    lines = []

    for paragraph in paragraphs:
        if not paragraph.strip():
            lines.append("")
            continue

        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current_line = words[0]
        for word in words[1:]:
            test_line = current_line + " " + word
            width = _measure_text_width(font, test_line)
            if width > max_width:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        lines.append(current_line)

    return lines


def _segments_to_paths(segments, x_offset: float, y_offset: float) -> list[str]:
    """Convert Hershey line segments to SVG path data strings.

    Groups consecutive connected segments into single paths to minimize
    pen-up/pen-down movements.
    """
    paths = []
    current_path = None
    prev_end = None

    for (x1, y1), (x2, y2) in segments:
        ax1 = x1 + x_offset
        ay1 = y1 + y_offset
        ax2 = x2 + x_offset
        ay2 = y2 + y_offset

        if (
            prev_end is not None
            and abs(ax1 - prev_end[0]) < 0.01
            and abs(ay1 - prev_end[1]) < 0.01
        ):
            # Continue the current stroke
            current_path += f" L {ax2:.2f},{ay2:.2f}"
        else:
            # Start a new stroke
            if current_path:
                paths.append(current_path)
            current_path = f"M {ax1:.2f},{ay1:.2f} L {ax2:.2f},{ay2:.2f}"

        prev_end = (ax2, ay2)

    if current_path:
        paths.append(current_path)

    return paths


def estimate_lines(text: str, config: Config) -> int:
    """Estimate how many wrapped lines the text will occupy."""
    from HersheyFonts import HersheyFonts

    font = HersheyFonts()
    font.load_default_font(config.font_name)
    font.normalize_rendering(config.font_size)

    max_text_width = config.text_area_width_pt
    wrapped_lines = _word_wrap(font, text, max_text_width)
    return len(wrapped_lines)


def render_text_to_svg(
    text: str, config: Config, start_line: int = 0
) -> list[tuple[str, int]]:
    """Render text as single-stroke Hershey font paths, splitting across pages.

    Args:
        text: The text to render.
        config: Configuration object.
        start_line: Line index to start rendering at (for journal mode).

    Returns:
        List of (svg_file_path, lines_used) tuples — one per page.
    """
    from HersheyFonts import HersheyFonts

    # Setup font
    font = HersheyFonts()
    font.load_default_font(config.font_name)
    font.normalize_rendering(config.font_size)

    # Sanitize Unicode typographic characters
    text = _sanitize_text(text)

    # Page dimensions in points
    page_w = config.page_width_pt
    page_h = config.page_height_pt
    margin = config.margin_pt
    margin_top = config.margin_top_pt
    max_text_width = config.text_area_width_pt

    # Word wrap
    wrapped_lines = _word_wrap(font, text, max_text_width)

    # Determine base output path
    if config.output_path:
        base_path = config.output_path
    else:
        base_path = os.path.join(os.getcwd(), "printpulse_output.svg")

    # Calculate how many lines fit on one page
    line_height = config.font_size * config.line_spacing
    max_lines_per_page = max(1, int(config.text_area_height_pt / line_height))

    # Split wrapped_lines into page-sized chunks.
    # First page accounts for start_line offset (journal mode).
    first_page_capacity = max(1, max_lines_per_page - start_line)
    pages_lines: list[list[str]] = []

    if len(wrapped_lines) <= first_page_capacity:
        pages_lines.append(wrapped_lines)
    else:
        pages_lines.append(wrapped_lines[:first_page_capacity])
        remaining = wrapped_lines[first_page_capacity:]
        while remaining:
            pages_lines.append(remaining[:max_lines_per_page])
            remaining = remaining[max_lines_per_page:]

    # Landscape setup
    if config.landscape:
        svg_w_in = config.page_height_in
        svg_h_in = config.page_width_in
        svg_w_pt = config.page_height_pt
        svg_h_pt = config.page_width_pt
    else:
        svg_w_in = config.page_width_in
        svg_h_in = config.page_height_in
        svg_w_pt = page_w
        svg_h_pt = page_h

    results: list[tuple[str, int]] = []

    for page_idx, page_lines in enumerate(pages_lines):
        # Output path: page 1 = base, page 2+ = base_p2.svg, etc.
        if page_idx == 0:
            output_path = base_path
        else:
            stem, ext = os.path.splitext(base_path)
            output_path = f"{stem}_p{page_idx + 1}{ext}"

        dwg = svgwrite.Drawing(
            output_path,
            size=(f"{svg_w_in}in", f"{svg_h_in}in"),
            viewBox=f"0 0 {svg_w_pt:.0f} {svg_h_pt:.0f}",
        )

        if config.landscape:
            content_group = dwg.g(
                transform=f"translate(0, {svg_h_pt:.0f}) rotate(-90)"
            )
        else:
            content_group = dwg.g()

        # On the first page, use start_line offset; subsequent pages start at top
        page_start_line = start_line if page_idx == 0 else 0

        all_paths = []
        for line_idx, line_text in enumerate(page_lines):
            if not line_text.strip():
                continue

            y_offset = margin_top + (page_start_line + line_idx) * line_height
            x_offset = margin

            segments = list(font.lines_for_text(line_text))
            if not segments:
                continue

            all_x = []
            all_y = []
            for (x1, y1), (x2, y2) in segments:
                all_x.extend([x1, x2])
                all_y.extend([-y1, -y2])
            min_x = min(all_x) if all_x else 0
            min_y = min(all_y) if all_y else 0

            adjusted_x_offset = x_offset - min_x
            flipped_segments = [
                ((x1, -y1), (x2, -y2)) for (x1, y1), (x2, y2) in segments
            ]
            adjusted_y_offset = y_offset - min_y
            paths = _segments_to_paths(
                flipped_segments, adjusted_x_offset, adjusted_y_offset
            )
            all_paths.extend(paths)

        for path_data in all_paths:
            content_group.add(
                dwg.path(
                    d=path_data,
                    fill="none",
                    stroke="black",
                    stroke_width=0.5,
                    stroke_linecap="round",
                    stroke_linejoin="round",
                )
            )

        dwg.add(content_group)
        dwg.save()
        _optimize_svg(output_path)
        results.append((output_path, len(page_lines)))

    return results


def _render_line(font, text: str, x_offset: float, y_offset: float) -> list[str]:
    """Render a single line of Hershey font text and return SVG path data strings.

    Handles y-flip (Hershey is y-up, SVG is y-down) and positioning.
    """
    if not text.strip():
        return []

    segments = list(font.lines_for_text(text))
    if not segments:
        return []

    # Find bounds for y-flip normalization
    all_x = []
    all_y = []
    for (x1, y1), (x2, y2) in segments:
        all_x.extend([x1, x2])
        all_y.extend([-y1, -y2])
    min_x = min(all_x) if all_x else 0
    min_y = min(all_y) if all_y else 0

    adjusted_x = x_offset - min_x
    flipped = [((x1, -y1), (x2, -y2)) for (x1, y1), (x2, y2) in segments]
    adjusted_y = y_offset - min_y

    return _segments_to_paths(flipped, adjusted_x, adjusted_y)


def _word_wrap_variable(font, text: str, max_widths: list[tuple[int, float]],
                        default_width: float) -> list[str]:
    """Word-wrap text where different line indices have different max widths.

    max_widths: list of (line_index, width) pairs defining narrower regions.
    default_width: width for lines not in max_widths.

    Returns list of wrapped text lines.
    """
    width_map = dict(max_widths)
    paragraphs = text.split("\n")
    lines: list[str] = []

    for paragraph in paragraphs:
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current_line = words[0]
        for word in words[1:]:
            line_idx = len(lines)
            max_w = width_map.get(line_idx, default_width)
            test_line = current_line + " " + word
            width = _measure_text_width(font, test_line)
            if width > max_w:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        lines.append(current_line)

    return lines


def render_letter_to_svg(
    letter_doc,
    profile,
    config: Config,
    no_illustrations: bool = False,
    theme: str = "green",
) -> str:
    """Render a full Victorian letter to SVG.

    Args:
        letter_doc: LetterDocument with parsed letter content.
        profile: StationeryProfile with visual settings.
        config: Config object for page dimensions.
        no_illustrations: Skip AI illustrations.
        theme: Color theme for UI messages.

    Returns:
        Path to the saved SVG file.
    """
    from HersheyFonts import HersheyFonts

    # Sanitize any Unicode typographic characters in the letter text
    letter_doc.sanitize(_sanitize_text)

    # ── Page setup ──
    page_w = config.page_width_pt
    page_h = config.page_height_pt
    margin = config.margin_pt
    text_area_w = config.text_area_width_pt
    gutter = 3.0  # tight gap between text and inline sketch

    # Output path
    if config.output_path:
        output_path = config.output_path
    else:
        output_path = os.path.join(os.getcwd(), "printpulse_letter.svg")

    # SVG dimensions (landscape mode swaps w/h for AxiDraw)
    if config.landscape:
        svg_w_in = config.page_height_in
        svg_h_in = config.page_width_in
        svg_w_pt = config.page_height_pt
        svg_h_pt = config.page_width_pt
    else:
        svg_w_in = config.page_width_in
        svg_h_in = config.page_height_in
        svg_w_pt = page_w
        svg_h_pt = page_h

    dwg = svgwrite.Drawing(
        output_path,
        size=(f"{svg_w_in}in", f"{svg_h_in}in"),
        viewBox=f"0 0 {svg_w_pt:.0f} {svg_h_pt:.0f}",
    )

    if config.landscape:
        content_group = dwg.g(transform=f"translate(0, {svg_h_pt:.0f}) rotate(-90)")
    else:
        content_group = dwg.g()

    all_paths: list[str] = []
    illustration_paths: list[str] = []  # separate for thinner stroke rendering
    margin_top = config.margin_top_pt
    cursor_y = margin_top

    # ── Load fonts ──
    header_font = HersheyFonts()
    header_font.load_default_font(profile.header.font)
    header_font.normalize_rendering(profile.header.font_size)

    body_font = HersheyFonts()
    body_font.load_default_font(profile.body_font)
    body_font.normalize_rendering(profile.body_font_size)

    line_height = profile.body_font_size * 1.6

    # ── 1. Header layout ──
    header_h = profile.header.font_size * 3.5

    # Render "FROM THE DESK OF" prefix text
    prefix_y = cursor_y + profile.header.font_size * 1.0
    prefix_x = margin + 10
    prefix_font = HersheyFonts()
    prefix_font.load_default_font(profile.header.font)
    prefix_font.normalize_rendering(profile.header.font_size * 0.5)
    all_paths.extend(_render_line(prefix_font, profile.header.prefix, prefix_x, prefix_y))

    # Render sender name
    name_y = prefix_y + profile.header.font_size * 1.0
    all_paths.extend(_render_line(header_font, profile.header.name, prefix_x, name_y))

    # Render title (smaller)
    if profile.header.title:
        title_font = HersheyFonts()
        title_font.load_default_font(profile.header.font)
        title_font.normalize_rendering(profile.header.font_size * 0.45)
        title_y = name_y + profile.header.font_size * 0.8
        all_paths.extend(_render_line(title_font, profile.header.title, prefix_x, title_y))

    cursor_y += header_h + 12  # gap below header

    # ── 3. Hero illustration (AI-generated) ──
    hero_paths: list[str] | None = None
    if not no_illustrations and profile.illustrations.hero.enabled:
        from printpulse import illustrations
        hero_h = profile.illustrations.hero.max_height_in * 72
        hero_w = text_area_w
        hero_paths = illustrations.generate_hero_illustration(
            letter_doc.full_text(), hero_w, hero_h, theme,
        )
        if hero_paths:
            # Compute actual rendered height from path bounding box
            actual_hero_h = illustrations.get_paths_height(hero_paths)
            if actual_hero_h <= 0:
                actual_hero_h = hero_h
            # Offset hero paths — tracked separately for thinner stroke
            hero_origin_x = margin
            hero_origin_y = cursor_y
            for p in hero_paths:
                illustration_paths.append(_offset_path(p, hero_origin_x, hero_origin_y))
            # Add hero annotation (label + arrow)
            hero_anno = illustrations.generate_hero_annotation(
                letter_doc.full_text(), hero_w, actual_hero_h, theme,
            )
            for p in hero_anno:
                illustration_paths.append(_offset_path(p, hero_origin_x, hero_origin_y))
            cursor_y += actual_hero_h + 14  # compact space for annotation below

    # ── 4. Supporting sketch setup ──
    sketch_paths: list[str] | None = None
    sketch_w = 0.0
    sketch_h = 0.0

    if not no_illustrations and profile.illustrations.supporting.enabled:
        from printpulse import illustrations
        sketch_h = profile.illustrations.supporting.max_height_in * 72
        sketch_w = text_area_w * 0.40  # 40% of text width
        hero_subject = letter_doc.body[:100] if letter_doc.body else ""
        sketch_paths = illustrations.generate_supporting_sketch(
            letter_doc.full_text(), hero_subject, sketch_w, sketch_h, theme,
        )

    # ── 5. Date ──
    if letter_doc.date:
        date_font = HersheyFonts()
        date_font.load_default_font(profile.body_font)
        date_font.normalize_rendering(profile.body_font_size * 0.85)
        # Right-align date
        date_w = _measure_text_width(date_font, letter_doc.date)
        date_x = margin + text_area_w - date_w
        all_paths.extend(_render_line(date_font, letter_doc.date, date_x, cursor_y))
        cursor_y += line_height * 1.2

    # ── 6. Salutation ──
    if letter_doc.salutation:
        all_paths.extend(_render_line(body_font, letter_doc.salutation, margin, cursor_y))
        cursor_y += line_height * 1.5

    # ── 7. Body with variable-width wrapping ──
    body_text = letter_doc.body or ""

    # Estimate total body lines to decide sketch placement
    full_width_lines = _word_wrap(body_font, body_text, text_area_w)
    total_body_lines = len(full_width_lines)

    sketch_start_line = -1
    if sketch_paths and total_body_lines > 4:
        sketch_start_line = max(2, int(total_body_lines * 0.3))
        sketch_lines_needed = max(1, int(sketch_h / line_height))
        sketch_end_line = sketch_start_line + sketch_lines_needed

        # Lines in sketch range get reduced width
        narrow_width = text_area_w - sketch_w - gutter
        variable_widths = [
            (i, narrow_width)
            for i in range(sketch_start_line, sketch_end_line + 1)
        ]
        wrapped_body = _word_wrap_variable(body_font, body_text, variable_widths, text_area_w)
    else:
        wrapped_body = _word_wrap(body_font, body_text, text_area_w)

    # Render body lines
    body_start_y = cursor_y
    for line_idx, line_text in enumerate(wrapped_body):
        if not line_text.strip():
            cursor_y += line_height
            continue
        all_paths.extend(_render_line(body_font, line_text, margin, cursor_y))
        cursor_y += line_height

    # Place sketch at the right position
    if sketch_paths and sketch_start_line >= 0:
        sketch_x = margin + text_area_w - sketch_w
        sketch_y = body_start_y + sketch_start_line * line_height
        for p in sketch_paths:
            illustration_paths.append(_offset_path(p, sketch_x, sketch_y))
        # Add sketch annotation label
        from printpulse import illustrations
        sketch_anno = illustrations.generate_sketch_annotation(
            letter_doc.full_text(), sketch_w, sketch_h, theme,
        )
        for p in sketch_anno:
            illustration_paths.append(_offset_path(p, sketch_x, sketch_y))

    cursor_y += line_height * 0.5

    # ── 8. Closing ──
    if letter_doc.closing:
        all_paths.extend(_render_line(body_font, letter_doc.closing, margin, cursor_y))
        cursor_y += line_height * 1.5

    # ── 9. Signature ──
    if letter_doc.signature_name:
        sig_font = HersheyFonts()
        sig_font.load_default_font(profile.header.font)
        sig_font.normalize_rendering(profile.body_font_size * 1.2)
        all_paths.extend(_render_line(sig_font, letter_doc.signature_name, margin + 20, cursor_y))
        cursor_y += line_height
        pass  # ornaments removed

    # ── 10. Postscript ──
    if letter_doc.postscript:
        cursor_y += line_height
        ps_font = HersheyFonts()
        ps_font.load_default_font(profile.body_font)
        ps_font.normalize_rendering(profile.body_font_size * 0.85)
        ps_text = f"P.S. {letter_doc.postscript}"
        ps_lines = _word_wrap(ps_font, ps_text, text_area_w)
        for ps_line in ps_lines:
            if ps_line.strip():
                all_paths.extend(_render_line(ps_font, ps_line, margin, cursor_y))
            cursor_y += line_height * 0.9

    # ── Add all paths to SVG ──
    for path_data in all_paths:
        content_group.add(
            dwg.path(
                d=path_data,
                fill="none",
                stroke="black",
                stroke_width=0.5,
                stroke_linecap="round",
                stroke_linejoin="round",
            )
        )

    # Illustration paths rendered with thinner stroke for lighter ink density
    for path_data in illustration_paths:
        content_group.add(
            dwg.path(
                d=path_data,
                fill="none",
                stroke="black",
                stroke_width=0.3,
                stroke_linecap="round",
                stroke_linejoin="round",
            )
        )

    dwg.add(content_group)
    dwg.save()

    _optimize_svg(output_path)
    return output_path


def _offset_path(d: str, dx: float, dy: float) -> str:
    """Offset all absolute coordinates in an SVG path by (dx, dy)."""
    import re as _re
    tokens = _re.findall(r'[MmLlQqCcZzHhVvSsTtAa]|[-+]?\d*\.?\d+', d)
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

        if cmd in ('Z', 'z', 'm', 'l', 'q', 'c', 't', 's', 'h', 'v'):
            result.append(f"{val:.1f}")
        elif cmd == 'H':
            result.append(f"{val + dx:.1f}")
        elif cmd == 'V':
            result.append(f"{val + dy:.1f}")
        else:
            is_x = coord_idx % 2 == 0
            result.append(f"{val + dx:.1f}" if is_x else f"{val + dy:.1f}")
            coord_idx += 1

    return " ".join(result)


def _optimize_svg(svg_path: str):
    """Optimize SVG paths using vpype for efficient plotting."""
    try:
        from vpype_cli import execute as vpype_execute

        vpype_execute(
            f'read "{svg_path}" '
            f"linemerge --tolerance 0.5mm "
            f"linesort "
            f"linesimplify "
            f'write "{svg_path}"'
        )
        ui.success_message("SVG optimized with vpype.")
    except ImportError:
        ui.success_message("vpype not installed, skipping path optimization.")
    except Exception as e:
        ui.success_message(f"vpype optimization skipped: {e}")


def open_in_viewer(svg_path: str):
    """Open the SVG file in the system's default viewer."""
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(svg_path)
        elif system == "Darwin":
            subprocess.run(["open", svg_path], check=True)
        else:
            subprocess.run(["xdg-open", svg_path], check=True)
    except Exception as e:
        ui.error_panel(f"Could not open SVG viewer: {e}")
