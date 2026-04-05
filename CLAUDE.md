# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PrintPulse is a voice-to-print system with three hardware targets:
- **AxiDraw Desktop** — Type/speak text, render in Hershey single-stroke fonts, plot on pen plotter
- **Thermal Printer Desktop** — Watch RSS feeds, print headlines on 58mm receipt paper (ESC/POS)
- **Pi Zero News Appliance** — Headless RSS ticker with Flask web UI for configuration

Python 3.9+, GPL v3. Version tracked in both `printpulse/__init__.py` and `pyproject.toml`.

## Build & Development

```bash
pip install -e .                    # Install in dev mode
printpulse [OPTIONS]                # Run CLI
```

Optional extras installed separately: `pyaxidraw` (from ZIP, not PyPI), `pywin32` (Windows thermal), `flask` (Pi web UI), `vpype`/`vtracer` (SVG optimization).

## Testing & Linting

```bash
pytest tests/ -v                    # Run all tests
pytest tests/test_watch.py -v       # Run single test file
pytest tests/test_watch.py::TestFetchNewItems::test_dedup -v  # Single test
ruff check printpulse/ pi/          # Lint (only F* rules, ignores F401/F841)
```

CI (`.github/workflows/ci.yml`) runs ruff + pytest on Python 3.11 for every push/PR to main. A separate workflow auto-bumps the patch version after merges.

## Architecture

### Key Design Decisions

- **Lazy imports** — Heavy modules (numpy, svgwrite, pyaxidraw, whisper) are imported only when needed so the Pi web UI boots fast without loading ML/graphics libraries. Tests in `test_lazy_imports.py` enforce this.
- **Dual printer backends** — `thermal.py` (ESC/POS binary protocol) and `plotter.py` (pyaxidraw wrapper) share no base class; `app.py` dispatches based on `--printer` flag.
- **Secure filesystem** — `secure_fs.py` enforces Unix 0o600/0o700 on all config and state files.

### Main Package (`printpulse/`)

`app.py` is the orchestrator — parses CLI args, dispatches to the appropriate mode:
- **Standard mode**: optional voice input (`speech.py` → Whisper) → `text_to_svg.py` → plotter/thermal
- **Letter mode**: parse dictated text (`letter.py`) → optional DALL-E illustrations (`illustrations.py`) → SVG with ornaments (`ornaments.py`) + stationery profiles (`stationery.py`)
- **Watch mode**: poll RSS feeds (`watch.py`) → dedup → quiet hours queue → print via thermal/plotter

`text_to_svg.py` handles Hershey font rendering and text layout (binary search for line fitting). `ui.py` provides a retro Rich-based terminal UI.

### Pi Appliance (`pi/`)

- `pi/webapp/server.py` — Flask app (~600 lines): auth (SHA256+salt), CSRF, rate limiting, CSP headers, config save, test print, git-based auto-update, systemd restart
- `pi/appliance.py` — Config bridge between Flask UI and CLI watch mode
- `pi/webapp/wifi_routes.py` — WiFi provisioning blueprint (nmcli)
- Systemd units: `printpulse.service` (watch) + `printpulse-web.service` (Flask)
- `pi/setup.sh` — One-command Pi flashing + setup

### State Files (all in `~/`)

| File | Purpose |
|------|---------|
| `.printpulse_appliance.json` | Pi web UI config (feeds, interval, auth, quiet hours) |
| `.printpulse_seen.json` | RSS entry IDs already printed (dedup across restarts) |
| `.printpulse_history.json` | Print history (max 200 items) |
| `.printpulse_retry.json` | Failed prints for retry (max 3 attempts) |
| `.printpulse_quiet_queue.json` | Items queued during quiet hours |
| `.printpulse_journal.json` | Journal state (page position, timestamps) |

### Illustrations Pipeline

`illustrations.py` (~1350 lines): DALL-E 3 → downsample to 512px → preprocessing (blur, threshold, contrast) → vtracer SVG vectorization → GPT-4 Vision QA loop. Requires OpenAI API key.

## Important Constraints

- Hershey fonts only render ASCII + some extended chars; Unicode is sanitized to ASCII
- Thermal printer: 32 chars/line at Font A; ESC/POS compatible hardware required
- Pi setup assumes Raspberry Pi OS Lite 32-bit on Pi Zero 2 W
- Feed URL validation rejects `file://`, localhost, link-local, and private IPs
- Auto-update on Pi does `git pull` + systemd restart (assumes repo at `~/PrintPulse`)
