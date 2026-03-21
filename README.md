# PrintPulse

**Voice-to-print for AxiDraw pen plotters and thermal printers.**

Dictate a message, paste text, or monitor live news feeds — PrintPulse renders it in single-stroke vector fonts and sends it to an AxiDraw pen plotter or ESC/POS thermal printer. Built with a retro 80's terminal aesthetic.

---

## Features

- **Voice input** — Record from your microphone, transcribe with OpenAI Whisper
- **Text & file input** — Type directly or pass a `.txt` file
- **Watch mode** — Monitor RSS/Atom feeds and auto-print breaking news
- **Letter mode** — Formal letters with decorative headers and stationery profiles
- **Journal mode** — Timestamped entries with multi-page tracking
- **22+ Hershey fonts** — Single-stroke vector fonts designed for pen plotters
- **Dual output** — AxiDraw pen plotter, thermal receipt printer, or both
- **Multi-page support** — Automatic pagination with paper-flip prompts
- **Retro CLI** — Green or amber terminal themes with ASCII art splash screen

---

## Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/PrintPulse.git
cd PrintPulse

# Install core package
pip install -e .

# Optional extras
pip install -e ".[optimize]"    # vpype SVG path optimization
pip install -e ".[thermal]"     # Windows thermal printer support (pywin32)
```

### AxiDraw Setup

The AxiDraw Python API is not on PyPI. Install manually:

1. Download the API zip from [Evil Mad Scientist](https://cdn.evilmadscientist.com/dl/ad/public/AxiDraw_API.zip)
2. Extract and install: `pip install .` from the extracted directory

### Whisper Models

On first use, Whisper downloads the selected model automatically. Available models:

| Model | Parameters | Speed | Accuracy |
|-------|-----------|-------|----------|
| `tiny` | 39M | Fastest | Basic |
| `base` | 74M | Fast | Good (default) |
| `small` | 244M | Moderate | Better |
| `medium` | 769M | Slow | Great |
| `large` | 1.5B | Slowest | Best |

---

## Usage

### Quick Start

```bash
# Interactive mode — prompts for input method
printpulse

# Type text directly
printpulse -i text -t "Hello from the plotter!"

# Print from a text file
printpulse -i text -t letter.txt

# Record from microphone (press Enter to stop)
printpulse -i mic

# Record for exactly 10 seconds
printpulse -i mic -d 10

# Transcribe an audio file
printpulse -i file -a recording.wav
```

### Fonts

```bash
# Use a specific font
printpulse -i text -t "Hello" -f block
printpulse -i text -t "Hello" -f cursive
printpulse -i text -t "Hello" -f gothic

# List all available fonts in the interactive menu
printpulse
```

Available fonts:

| Friendly Name | Hershey ID | Style |
|--------------|------------|-------|
| Block | `futural` | Clean, architectural lettering |
| Cursive | `scripts` | Flowing handwriting |
| Script Bold | `scriptc` | Heavy calligraphic |
| Roman | `rowmans` | Classic serif |
| Typewriter | `rowmant` | Monospaced feel |
| Typewriter Light | `rowmand` | Lighter monospaced |
| Times | `timesr` | Serif body text |
| Times Bold | `timesrb` | Heavy serif |
| Times Italic | `timesi` | Italic serif |
| Gothic | `gothiceng` | Old English blackletter |
| Gothic Bold | `gothgbt` | Heavy blackletter |
| Italic | `futuram` | Sans-serif italic |
| Greek | `greek` | Greek alphabet |
| Cyrillic | `cyrilc` | Cyrillic alphabet |
| Japanese | `japanese` | Japanese characters |
| Markers | `markers` | Marker-drawn style |
| Symbolic | `symbolic` | Symbol set |
| Astrology | `astrology` | Zodiac symbols |
| Math | `mathlow` | Mathematical notation |
| Music | `music` | Musical notation |
| Meteorology | `meteorology` | Weather symbols |

### Watch Mode (RSS/Atom Feeds)

Monitor news feeds and auto-print new stories as they appear:

```bash
# Watch AP News top stories
printpulse --watch "https://rsshub.app/apnews/topics/apf-topnews"

# Watch BBC World News
printpulse --watch "http://feeds.bbci.co.uk/news/world/rss.xml"

# Watch multiple feeds, print to thermal printer
printpulse --watch "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml" \
                   "http://feeds.bbci.co.uk/news/world/rss.xml" \
           --printer thermal

# Custom poll interval (10 minutes) and max 5 items per cycle
printpulse --watch "https://feeds.npr.org/1001/rss.xml" \
           --watch-interval 600 --max-prints 5

# Both printers simultaneously
printpulse --watch "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml" \
           --printer both
```

### Letter Mode

Write formal letters with decorative headers:

```bash
# Write a letter from a text file
printpulse -i text -t letter.txt --letter

# Interactive letter composition
printpulse --letter-template

# Use a specific stationery profile
printpulse -i text -t letter.txt --letter --stationery victorian

# List available stationery profiles
printpulse --list-stationery
```

### Journal Mode

Timestamped entries that track position across pages:

```bash
# Add a journal entry via voice
printpulse -i mic --journal

# Add a text entry
printpulse -i text -t "Met with the team today." --journal

# Reset journal (start fresh page)
printpulse -i text -t "New chapter." --journal --journal-reset
```

### Output Options

```bash
# Dry run (no hardware needed)
printpulse -i text -t "Test" --dry-run

# Send to thermal printer instead of AxiDraw
printpulse -i text -t "Breaking news" --printer thermal

# Send to both printers
printpulse -i text -t "Hello" --printer both

# Skip confirmation prompts
printpulse -i text -t "Quick print" -y

# Custom output SVG path
printpulse -i text -t "Hello" -o output.svg

# Portrait orientation (default is landscape for AxiDraw)
printpulse -i text -t "Hello" --portrait
```

### Page & Theme

```bash
# A4 paper size
printpulse -i text -t "Hello" --page a4

# Amber retro theme
printpulse -i text -t "Hello" --theme amber

# Custom font size
printpulse -i text -t "Hello" --font-size 18
```

---

## CLI Reference

```
printpulse [-h] [-i {mic,file,text}] [-a AUDIO_FILE] [-t TEXT]
           [-d DURATION] [-f FONT] [--font-size POINTS]
           [--page {letter,a4,a3}] [--portrait] [-o OUTPUT]
           [--preview | --no-preview] [--dry-run] [-y]
           [-m {tiny,base,small,medium,large}]
           [--theme {green,amber}]
           [--journal] [--journal-reset]
           [--watch URL [URL ...]] [--watch-interval SECONDS]
           [--max-prints N]
           [--printer {axidraw,thermal,both}]
           [--letter] [--letter-template]
           [--stationery PROFILE] [--no-illustrations]
           [--list-stationery]
```

---

## Configuration

User configuration lives in `~/.printpulse/`:

```
~/.printpulse/
  config.json          # Global settings (API keys, defaults)
  stationery/          # Custom stationery profiles (JSON)
  cache/               # Cached illustrations
```

### Stationery Profiles

Create custom letter stationery by adding JSON files to `~/.printpulse/stationery/`:

```json
{
  "name": "victorian",
  "header": {
    "prefix": "FROM THE DESK OF",
    "name": "Your Name",
    "title": "Your Title",
    "font": "scripts",
    "font_size": 20.0,
    "frame_style": "ornamental"
  },
  "corner_ornaments": "gears",
  "body_font": "futural",
  "body_font_size": 12.0
}
```

---

## Hardware

### AxiDraw

PrintPulse supports AxiDraw pen plotters from [Evil Mad Scientist](https://www.axidraw.com/). The plotter draws text using single-stroke Hershey fonts — each letter is drawn as continuous pen strokes, not filled outlines.

Default pen settings:
- Pen down speed: 25%
- Pen up speed: 75%
- Servo positions: up=60, down=40

### Thermal Printer

Supports ESC/POS compatible thermal receipt printers (tested with Rongta 58mm). Features include bold headlines, QR codes for article URLs, and automatic text wrapping.

- **Windows**: requires `pywin32` (`pip install pywin32`)
- **Linux / Raspberry Pi**: writes directly to `/dev/usb/lp0` (no extra deps)

### Raspberry Pi Zero Appliance

Turn a Pi Zero into a standalone, always-on news ticker. Prints headlines automatically, configurable from your phone via a web UI.

See **[pi/README.md](pi/README.md)** for the complete setup guide — written for first-time Pi users.

---

## Architecture

```
printpulse/
  __main__.py      Entry point
  app.py           CLI orchestrator & argparse
  config.py        Config dataclass, font map, page presets
  ui.py            Retro terminal UI (Rich library)
  speech.py        Microphone recording & Whisper transcription
  text_to_svg.py   Hershey font rendering & SVG generation
  plotter.py       AxiDraw control
  thermal.py       ESC/POS thermal printer output
  letter.py        Letter document model & parser
  stationery.py    Stationery profile system
  illustrations.py AI illustration pipeline (DALL-E + vtracer)
  stationery/      Bundled stationery profiles (JSON)
```

---

## Requirements

- Python 3.9+
- Windows, macOS, or Linux
- AxiDraw pen plotter (optional — use `--dry-run` without hardware)
- ESC/POS thermal printer (optional, Windows only)
- Microphone (optional — for voice input)

---

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.
