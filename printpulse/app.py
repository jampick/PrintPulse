import argparse
import os
import sys

from rich.text import Text

from printpulse import ui
from printpulse.config import Config, FONT_MAP
from printpulse import speech
from printpulse import text_to_svg
from printpulse import plotter
from printpulse import thermal
from printpulse import journal
from printpulse.secure_fs import check_permissions
from printpulse.logging_config import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="printpulse",
        description="PrintPulse: voice-to-print for pen plotters and thermal printers",
    )
    parser.add_argument(
        "-i", "--input-mode",
        choices=["mic", "file", "text"],
        help="Input mode: mic (microphone), file (audio file), text (text input)",
    )
    parser.add_argument(
        "-a", "--audio-file",
        help="Path to audio file (used with -i file)",
    )
    parser.add_argument(
        "-t", "--text",
        help="Text string or path to a .txt file (used with -i text)",
    )
    parser.add_argument(
        "-f", "--font",
        help="Font name (e.g. cursive, block, gothic, futural, scripts)",
    )
    parser.add_argument(
        "--font-size",
        type=float,
        default=14.0,
        help="Font size in points (default: 14)",
    )
    parser.add_argument(
        "-m", "--model",
        default="base",
        help="Whisper model size: tiny, base, small, medium, large (default: base)",
    )
    parser.add_argument(
        "--page",
        choices=["letter", "a4", "a3"],
        default="letter",
        help="Page size preset (default: letter)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        default=None,
        help="Show SVG preview before plotting",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip SVG preview",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip plotter output (test without hardware)",
    )
    parser.add_argument(
        "--theme",
        choices=["green", "amber"],
        default="green",
        help="Color theme (default: green)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output SVG file path",
    )
    parser.add_argument(
        "-d", "--duration",
        type=float,
        help="Recording duration in seconds (default: open-ended)",
    )
    parser.add_argument(
        "--portrait",
        action="store_true",
        help="SVG in portrait orientation (default: landscape for AxiDraw)",
    )
    parser.add_argument(
        "--journal",
        action="store_true",
        help="Journal mode: timestamp each entry, resume on next line",
    )
    parser.add_argument(
        "--journal-reset",
        action="store_true",
        help="Reset journal (start fresh on a new page)",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip all confirmation prompts (auto-confirm)",
    )
    parser.add_argument(
        "--watch",
        metavar="URL",
        nargs="+",
        help="Watch one or more RSS/Atom feeds (space-separated URLs)",
    )
    parser.add_argument(
        "--watch-interval",
        type=int,
        default=300,
        help="Seconds between feed checks (default: 300)",
    )
    parser.add_argument(
        "--max-prints",
        type=int,
        default=3,
        help="Max items to plot per poll cycle (default: 3, 0=unlimited)",
    )
    parser.add_argument(
        "--printer",
        choices=["axidraw", "thermal", "both"],
        default="axidraw",
        help="Output device: axidraw (pen plotter), thermal (Rongta 58mm), or both",
    )
    parser.add_argument(
        "--quiet-start",
        metavar="HH:MM",
        default=None,
        help="Quiet hours start time (e.g. 22:00). No printing after this time.",
    )
    parser.add_argument(
        "--quiet-end",
        metavar="HH:MM",
        default=None,
        help="Quiet hours end time (e.g. 08:00). Resume printing at this time.",
    )
    # ── Letter mode ──
    parser.add_argument(
        "--letter",
        action="store_true",
        help="Letter writing mode: formal letter with ornate header and AI illustrations (AxiDraw only)",
    )
    parser.add_argument(
        "--stationery",
        default="victorian",
        help="Stationery profile name (default: victorian). See --list-stationery",
    )
    parser.add_argument(
        "--letter-template",
        action="store_true",
        help="Interactive letter template: prompts for recipient, body, closing",
    )
    parser.add_argument(
        "--no-illustrations",
        action="store_true",
        help="Skip AI-generated illustrations in letter mode",
    )
    parser.add_argument(
        "--list-stationery",
        action="store_true",
        help="List available stationery profiles and exit",
    )
    return parser


def _resolve_font(font_arg: str | None) -> str | None:
    """Resolve a font argument to a Hershey font ID."""
    if font_arg is None:
        return None

    # Direct font ID match
    from HersheyFonts import HersheyFonts
    hf = HersheyFonts()
    all_fonts = set(hf.default_font_names)
    if font_arg in all_fonts:
        return font_arg

    # Match from friendly name map (case-insensitive)
    for name, font_id in FONT_MAP.items():
        if font_arg.lower() == name.lower():
            return font_id

    return None


def _check_config_permissions():
    """Warn if config files have overly permissive permissions."""
    config_dir = os.path.expanduser("~/.printpulse")
    appliance_config = os.path.expanduser("~/.printpulse_appliance.json")

    paths_to_check = [config_dir, appliance_config]
    # Also check files inside config dir
    if os.path.isdir(config_dir):
        for name in os.listdir(config_dir):
            paths_to_check.append(os.path.join(config_dir, name))

    all_warnings = []
    for path in paths_to_check:
        all_warnings.extend(check_permissions(path))

    if all_warnings:
        import warnings
        for w in all_warnings:
            warnings.warn(w, stacklevel=2)


def run(argv: list[str]):
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Initialize structured logging
    setup_logging()

    # Check config file permissions on startup
    _check_config_permissions()

    # Build config
    config = Config()
    config.color_theme = args.theme
    config.whisper_model = args.model
    config.font_size = args.font_size
    config.dry_run = args.dry_run
    config.apply_page_preset(args.page)
    if args.portrait:
        config.landscape = False

    if args.output:
        config.output_path = args.output

    # Resolve preview setting
    if args.no_preview:
        config.preview = False
    elif args.preview:
        config.preview = True
    # else: will prompt interactively

    # Resolve font from CLI arg
    if args.font:
        resolved = _resolve_font(args.font)
        if resolved:
            config.font_name = resolved
        else:
            ui.error_panel(f"Unknown font '{args.font}'. Will prompt for selection.", config.color_theme)
            args.font = None  # Fall through to interactive selection

    theme = config.color_theme
    journal_mode = args.journal

    # ─── JOURNAL RESET ───
    if args.journal_reset:
        journal.reset_journal()
        ui.success_message("Journal reset. Ready for a new page.", theme)
        if not journal_mode:
            return

    # ─── LIST STATIONERY ───
    if args.list_stationery:
        from printpulse import stationery
        profiles = stationery.list_profiles()
        if profiles:
            ui.retro_panel(
                "STATIONERY PROFILES",
                "\n".join(f"  {name}" for name in profiles),
                theme,
            )
        else:
            ui.success_message("No stationery profiles found.", theme)
        return

    # ─── SPLASH ───
    ui.show_splash(theme)

    # ─── LETTER MODE GUARD ───
    if args.letter and args.printer == "thermal":
        ui.error_panel("Letter mode is only available for AxiDraw (pen plotter). "
                       "Use --printer axidraw or --printer both.", theme)
        return

    # ─── LETTER MODE ───
    if args.letter or args.letter_template:
        from printpulse import stationery, letter as letter_mod

        # Load stationery profile
        profile = stationery.load_profile(args.stationery)
        ui.retro_panel(
            "LETTER MODE",
            f"Stationery: {profile.name}\n"
            f"Header: {profile.header.prefix} {profile.header.name}\n"
            f"Ornaments: {profile.corner_ornaments}  |  Font: {profile.body_font}\n"
            f"Illustrations: hero={'on' if profile.illustrations.hero.enabled else 'off'}, "
            f"supporting={'on' if profile.illustrations.supporting.enabled else 'off'}",
            theme,
        )

        # Get letter content
        if args.letter_template:
            letter_doc = letter_mod.format_letter_interactive(theme)
        else:
            # Get text from input mode or -t flag
            raw_text = None
            if args.text:
                if args.text.endswith(".txt") and os.path.isfile(args.text):
                    with open(args.text, "r", encoding="utf-8") as f:
                        raw_text = f.read()
                else:
                    raw_text = args.text
            elif args.input_mode == "mic":
                ui.scan_line("INITIALIZING MICROPHONE", theme, duration=0.5)
                temp_audio = speech.record_audio(duration=args.duration, theme_name=theme)
                ui.scan_line("PROCESSING AUDIO", theme, duration=0.5)
                raw_text = speech.transcribe(temp_audio, config.whisper_model, theme)
                if temp_audio and os.path.isfile(temp_audio):
                    try:
                        os.unlink(temp_audio)
                    except OSError:
                        pass
            else:
                ui.retro_panel("LETTER INPUT", "Enter your letter text (press Enter twice to finish):", theme)
                lines = []
                while True:
                    line = input()
                    if line == "" and lines and lines[-1] == "":
                        lines.pop()
                        break
                    lines.append(line)
                raw_text = "\n".join(lines)

            if not raw_text or not raw_text.strip():
                ui.error_panel("No letter text provided. Exiting.", theme)
                return

            letter_doc = letter_mod.parse_letter(raw_text, sender_name=profile.header.name)

        # Fill in signature from profile if not set
        if not letter_doc.signature_name:
            letter_doc.signature_name = profile.header.name

        # Show parsed letter
        ui.retro_panel("LETTER PREVIEW", letter_doc.full_text(), theme)

        if not args.yes and not ui.confirm("Render this letter?", theme):
            ui.success_message("Aborted.", theme)
            return

        # Generate SVG
        no_illust = True  # illustrations disabled — pass files through as-is
        ui.scan_line("RENDERING LETTER TO SVG", theme, duration=0.8)

        with ui.live_status("Rendering letter...", theme):
            svg_path = text_to_svg.render_letter_to_svg(
                letter_doc, profile, config,
                no_illustrations=no_illust,
                theme=theme,
            )

        ui.success_message(f"Letter SVG saved: {svg_path}", theme)

        # Preview
        if config.preview is True or (config.preview is not False and args.preview is None):
            choice = ui.retro_prompt(
                [
                    ("V", "View SVG in default viewer"),
                    ("C", "Continue to plot"),
                    ("Q", "Quit"),
                ],
                theme,
            )
            if choice == "V":
                text_to_svg.open_in_viewer(svg_path)
                if not ui.confirm("Continue to plot?", theme):
                    ui.success_message("Done. Letter SVG saved for later use.", theme)
                    return
            elif choice == "Q":
                ui.success_message("Done. Letter SVG saved for later use.", theme)
                return

        # Plot
        if not config.dry_run:
            ui.retro_panel("PLOTTER CHECK", "Checking AxiDraw connection...", theme)
            if not plotter.check_plotter_connection():
                ui.error_panel(
                    "No AxiDraw detected. Check USB connection.\n"
                    "  Use --dry-run to test without hardware.",
                    theme,
                )
                if not ui.confirm("Try plotting anyway?", theme):
                    return

            ui.scan_line("INITIATING PLOT SEQUENCE", theme, duration=0.5)
            plotter.plot_svg(svg_path, config)

        ui.mission_complete(theme)
        return

    # ─── WATCH MODE ───
    if args.watch:
        from printpulse import watch
        # Resolve font upfront for watch mode
        if args.font:
            resolved = _resolve_font(args.font)
            if resolved:
                config.font_name = resolved
        config.preview = False  # no preview in watch mode

        use_axidraw = args.printer in ("axidraw", "both")
        use_thermal = args.printer in ("thermal", "both")

        def _plot_item(text: str, feed_item: dict | None = None):
            """Plot a single text item through the configured printer(s)."""
            # ── THERMAL PRINTER ──
            if use_thermal:
                from datetime import datetime
                ts = datetime.now().strftime("%m/%d %I:%M %p")
                title = text
                summary = ""
                source = ""
                url = ""
                if feed_item:
                    summary = feed_item.get("summary", "")
                    source = feed_item.get("_source", "")
                    entry = feed_item.get("_entry")
                    if entry:
                        if not source:
                            source = getattr(entry, "source", {}).get("title", "")
                        if not source:
                            link = getattr(entry, "link", "")
                            if link:
                                from urllib.parse import urlparse
                                source = urlparse(link).netloc
                        url = getattr(entry, "link", "")
                thermal.print_news_item(
                    title=title,
                    summary=summary,
                    source=source,
                    url=url,
                    timestamp=ts,
                    theme=theme,
                    dry_run=config.dry_run,
                )
                ui.success_message("Thermal print sent.", theme)

            # ── AXIDRAW PLOTTER ──
            if use_axidraw:
                plot_text = text
                start_line = 0
                max_lines = journal.total_lines(config)
                if journal_mode:
                    plot_text = journal.format_journal_entry(text)
                    start_line = journal.get_next_line()
                    remaining = journal.lines_remaining(config)
                    ui.retro_panel(
                        "JOURNAL",
                        f"Line {start_line + 1} of {max_lines}  |  {remaining} lines remaining",
                        theme,
                    )
                    if remaining <= 0:
                        ui.retro_panel(
                            "PAGE FULL",
                            "Page is full. Insert new page and press Enter.",
                            theme,
                        )
                        journal.reset_journal()
                        start_line = 0
                        if not args.yes:
                            input()

                ui.scan_line("GENERATING SVG PATHS", theme, duration=0.3)
                svg_path, lines_used = text_to_svg.render_text_to_svg(plot_text, config, start_line)
                ui.success_message(f"SVG saved: {svg_path}", theme)

                if not config.dry_run:
                    ui.scan_line("PLOTTING", theme, duration=0.3)
                    plotter.plot_svg(svg_path, config)

                if journal_mode:
                    journal.record_entry(plot_text, lines_used)
                    new_pos = journal.get_next_line()
                    remaining = journal.lines_remaining(config)
                    ui.success_message(
                        f"Journal: {lines_used} lines plotted. Now at line {new_pos} of {max_lines} ({remaining} remaining).",
                        theme,
                    )

        watch.run_watch_loop(
            feed_urls=args.watch,
            interval=args.watch_interval,
            max_prints=args.max_prints,
            plot_callback=_plot_item,
            theme=theme,
            quiet_start=args.quiet_start,
            quiet_end=args.quiet_end,
        )
        return

    # ─── INPUT MODE SELECTION ───
    input_mode = args.input_mode
    if not input_mode:
        input_mode_key = ui.retro_prompt(
            [
                ("M", "Microphone Recording"),
                ("F", "Audio File Import"),
                ("T", "Text Input"),
            ],
            theme,
        )
        input_mode = {"M": "mic", "F": "file", "T": "text"}[input_mode_key]

    # ─── ACQUIRE TEXT ───
    text = None
    temp_audio = None

    try:
        if input_mode == "mic":
            ui.scan_line("INITIALIZING MICROPHONE", theme, duration=0.5)
            temp_audio = speech.record_audio(
                duration=args.duration,
                theme_name=theme,
            )
            ui.scan_line("PROCESSING AUDIO", theme, duration=0.5)
            text = speech.transcribe(temp_audio, config.whisper_model, theme)

        elif input_mode == "file":
            audio_path = args.audio_file
            if not audio_path:
                ui.console.print(
                    Text("\n  Enter audio file path: ", style=ui.get_theme(theme)["primary"]),
                    end="",
                )
                audio_path = input().strip().strip('"').strip("'")

            audio_path = speech.load_audio_file(audio_path)
            ui.scan_line("PROCESSING AUDIO", theme, duration=0.5)
            text = speech.transcribe(audio_path, config.whisper_model, theme)

        elif input_mode == "text":
            text_input = args.text
            if not text_input:
                ui.retro_panel("TEXT INPUT", "Enter your message (press Enter twice to finish):", theme)
                lines = []
                while True:
                    line = input()
                    if line == "" and lines and lines[-1] == "":
                        lines.pop()  # Remove trailing blank
                        break
                    lines.append(line)
                text = "\n".join(lines)
            else:
                # Check if it's a file path
                if text_input.endswith(".txt") and os.path.isfile(text_input):
                    with open(text_input, "r", encoding="utf-8") as f:
                        text = f.read()
                else:
                    text = text_input

        if not text or not text.strip():
            ui.error_panel("No text to plot. Exiting.", theme)
            return

        # ─── SHOW TEXT ───
        ui.show_text_result(text, theme)
        ui.show_story_art(text, theme)

        if not args.yes and not ui.confirm("Use this text?", theme):
            ui.success_message("Aborted. Run again to retry.", theme)
            return

        # ─── AXIDRAW PREPARATION (font, journal, SVG, preview) ───
        svg_path = None
        lines_used = 0
        start_line = 0
        needs_axidraw = args.printer in ("axidraw", "both")

        if needs_axidraw:
            # ─── FONT SELECTION ───
            if not args.font:
                available_fonts = text_to_svg.get_available_fonts()
                font_id = ui.retro_menu(
                    "SELECT FONT",
                    [(fid, label) for fid, label in available_fonts],
                    theme,
                )
                config.font_name = font_id

            ui.success_message(f"Font: {config.font_name}", theme)

            # ─── JOURNAL SETUP ───
            if journal_mode:
                text = journal.format_journal_entry(text)
                start_line = journal.get_next_line()
                remaining = journal.lines_remaining(config)
                max_lines = journal.total_lines(config)
                ui.retro_panel(
                    "JOURNAL",
                    f"Line {start_line + 1} of {max_lines}  |  {remaining} lines remaining",
                    theme,
                )

            # ─── SVG GENERATION (auto-paginates) ───
            ui.scan_line("GENERATING SVG PATHS", theme, duration=0.8)

            with ui.live_status("Rendering text to SVG...", theme):
                pages = text_to_svg.render_text_to_svg(text, config, start_line)

            total_pages = len(pages)
            total_lines_used = sum(lu for _, lu in pages)

            if total_pages > 1:
                ui.retro_panel(
                    "MULTI-PAGE",
                    f"Text spans {total_pages} pages ({total_lines_used} lines total).",
                    theme,
                )

            for pg_idx, (svg_path, lines_used) in enumerate(pages):
                pg_num = pg_idx + 1
                ui.success_message(
                    f"Page {pg_num}/{total_pages} SVG saved: {svg_path}", theme
                )

            # ─── PREVIEW ───
            if config.preview is True or (config.preview is not False and args.preview is None):
                choice = ui.retro_prompt(
                    [
                        ("V", "View SVG in default viewer"),
                        ("C", "Continue to plot"),
                        ("Q", "Quit"),
                    ],
                    theme,
                )
                if choice == "V":
                    text_to_svg.open_in_viewer(pages[0][0])
                    if not ui.confirm("Continue to plot?", theme):
                        ui.success_message("Done. SVG saved for later use.", theme)
                        return
                elif choice == "Q":
                    ui.success_message("Done. SVG saved for later use.", theme)
                    return

        # ─── OUTPUT ───
        use_axidraw = args.printer in ("axidraw", "both")
        use_thermal = args.printer in ("thermal", "both")
        success = True

        # ── Thermal printer ──
        if use_thermal:
            ui.scan_line("SENDING TO THERMAL PRINTER", theme, duration=0.3)
            thermal_ok = thermal.print_text(text, theme, dry_run=config.dry_run)
            if thermal_ok:
                ui.success_message("Thermal print sent.", theme)
            else:
                ui.error_panel("Thermal print failed.", theme)
                success = False

        # ── AxiDraw plotter ──
        if use_axidraw:
            if not config.dry_run:
                ui.retro_panel("PLOTTER CHECK", "Checking AxiDraw connection...", theme)
                if not plotter.check_plotter_connection():
                    ui.error_panel(
                        "No AxiDraw detected. Check USB connection.\n"
                        "  Use --dry-run to test without hardware.",
                        theme,
                    )
                    if not ui.confirm("Try plotting anyway?", theme):
                        if use_thermal:
                            ui.mission_complete(theme)
                        return

            for pg_idx, (svg_path, lines_used) in enumerate(pages):
                pg_num = pg_idx + 1

                # Pause for paper flip between pages
                if pg_idx > 0:
                    ui.retro_panel(
                        "PAGE BREAK",
                        f"Page {pg_idx} complete. Load fresh paper for page {pg_num}/{total_pages}, then press Enter.",
                        theme,
                    )
                    input()

                ui.scan_line(
                    f"PLOTTING PAGE {pg_num}/{total_pages}", theme, duration=0.5
                )
                axidraw_ok = plotter.plot_svg(svg_path, config)
                if not axidraw_ok:
                    ui.error_panel(
                        f"AxiDraw plotting page {pg_num} did not complete successfully.",
                        theme,
                    )
                    success = False
                    break

        if success:
            if journal_mode and use_axidraw:
                journal.record_entry(text, total_lines_used)
                new_pos = journal.get_next_line()
                remaining = journal.lines_remaining(config)
                max_lines = journal.total_lines(config)
                ui.success_message(
                    f"Journal: {total_lines_used} lines plotted. "
                    f"Now at line {new_pos} of {max_lines} ({remaining} remaining).",
                    theme,
                )
            ui.mission_complete(theme)
        else:
            ui.error_panel("Output did not complete successfully.", theme)

    except FileNotFoundError as e:
        ui.error_panel(str(e), theme)
    except ValueError as e:
        ui.error_panel(str(e), theme)
    except Exception as e:
        ui.error_panel(f"Unexpected error: {e}", theme)
        raise
    finally:
        # Cleanup temp audio files
        if temp_audio and os.path.isfile(temp_audio):
            try:
                os.unlink(temp_audio)
            except OSError:
                pass
