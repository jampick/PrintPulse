# PrintPulse

Voice-to-print for AxiDraw pen plotters and thermal printers. Dictate a message, type something, or point it at RSS feeds — PrintPulse renders text in single-stroke Hershey fonts and sends it to a pen plotter or thermal receipt printer. Retro 80's terminal aesthetic throughout.

Three builds:

| | Build | What it does |
|---|-------|-------------|
| 🖊️ | AxiDraw desktop | Type or speak → pen-plotted output on paper |
| 🧾 | Thermal printer desktop | RSS feeds → headlines printed on receipt paper |
| 📰 | Pi Zero news appliance | Always-on headless ticker, configure from your phone |

---

## A Note from jampick

Hey folks — this is my first real use of Claude Code, so I hope you find it useful. I had some old hardware sitting around: an AxiDraw plotter and a thermal printer. Strange what you accumulate. I always wanted to use them in a coding project but never had the skills to interface with them directly. When Claude came along I knew that was the missing piece. Now these old printers actually get used — the thermal one is my analog news reader (just top stories), and the AxiDraw prints handwritten cards since my penmanship is illegible. I'm sure you'll find even better uses for this.

---

## Web UI (Pi Appliance)

Day-to-day the Pi is controlled entirely from your browser — no SSH required. Open `http://PI_IP:5000` from any device on your network.

Want to access it from outside your home network? Set up a [Cloudflare Tunnel](docs/cloudflare-tunnel.md) — no static IP or port forwarding needed.

**Configuration** — RSS feeds, poll interval, quiet hours, auto-update:

![PrintPulse web UI — configuration](docs/screenshot-config.png)

**Service control** — start, stop, update, test print:

![PrintPulse web UI — service control](docs/screenshot-controls.png)

**Print history** — every headline with source and timestamp:

![PrintPulse web UI — print history](docs/screenshot-history.png)

---

## What You Need

### AxiDraw build

- [AxiDraw V3](https://shop.evilmadscientist.com/productsmenu/846) or any AxiDraw model (~$475)
- Pens — Pilot G2, Uni-ball, Staedtler, anything that fits the pen holder
- Paper — copy paper is fine
- A computer with Python 3.9+

### Thermal printer build

- [Travelmate 58mm USB thermal printer](https://www.amazon.com/dp/B08V4H7T47) (~$35) — or any ESC/POS compatible 58mm printer
- 58mm paper rolls (usually included; cheap to replace)
- A computer with Python 3.9+

### Pi Zero appliance (standalone, always-on)

Everything in the thermal printer list, plus:

- Raspberry Pi Zero 2 W (~$15) — [buy here](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
- Micro SD card, 16GB+
- Micro USB OTG adapter (~$5) — converts the Pi's USB port so you can plug in the printer
- 5V micro USB power supply (an old phone charger works)

---

## Build 1: AxiDraw Desktop

### Install

```bash
git clone https://github.com/jampick/PrintPulse.git
cd PrintPulse
pip install -e .
```

### Install the AxiDraw API

The AxiDraw library isn't on PyPI — Evil Mad Scientist distributes it separately:

1. Download: [AxiDraw API zip](https://cdn.evilmadscientist.com/dl/ad/public/AxiDraw_API.zip)
2. Extract and run `pip install .` from inside the extracted folder

### Plot something

Plug in the AxiDraw, load paper and a pen, then:

```bash
# Type and plot
printpulse -i text -t "Hello from the plotter!"

# Record from mic (press Enter to stop)
printpulse -i mic

# Different font
printpulse -i text -t "In the year 2525" -f gothic

# Render to SVG without touching the hardware
printpulse -i text -t "Test layout" --dry-run
```

---

## Build 2: Thermal Printer Desktop

### Install

```bash
git clone https://github.com/jampick/PrintPulse.git
cd PrintPulse
pip install -e .
```

On Windows, also run `pip install pywin32`. On Linux the printer shows up at `/dev/usb/lp0` with no extra drivers needed.

### Print something

```bash
printpulse -i text -t "Extra! Extra!" --printer thermal

# Watch a feed and print new headlines as they appear
printpulse --watch "https://feeds.npr.org/1002/rss.xml" --printer thermal

# Multiple feeds
printpulse --watch "https://feeds.npr.org/1002/rss.xml" \
           --watch "http://feeds.bbci.co.uk/news/world/rss.xml" \
           --printer thermal --max-prints 3
```

---

## Build 3: Pi Zero News Appliance

The goal is a box that sits on a shelf, stays on, and prints news. No screen, no keyboard after initial setup — everything runs over Wi-Fi.

### Step 1 — Flash the SD card

Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/), insert your SD card, and:

- Choose **Raspberry Pi OS Lite (32-bit)** under "Raspberry Pi OS (other)"
- Click the gear icon ⚙ before writing — this is where you pre-configure SSH, Wi-Fi credentials, and your timezone so you don't need a monitor at all

Write it out (~5 min), put the card in the Pi, and plug in power. First boot takes a couple of minutes.

### Step 2 — Find the Pi on your network

Check your router's device list for `raspberrypi`, or from your computer:

```
ping raspberrypi.local
```

If that doesn't work, the [Fing app](https://www.fing.com/products/fing-app) (free, phone) will find it in a few seconds.

### Step 3 — SSH in

```bash
ssh pi@YOUR_PI_IP
```

Type `yes` on the fingerprint prompt, enter your password. You'll land at `pi@raspberrypi:~ $`.

### Step 4 — Run setup

```bash
git clone https://github.com/jampick/PrintPulse.git
bash PrintPulse/pi/setup.sh
```

Takes 5–10 minutes on a Pi Zero. When it finishes, reboot once:

```bash
sudo reboot
```

### Step 5 — Connect the printer

The Pi Zero has two micro-USB ports — one is power-only, the other is data. Use the data port (closer to center). Plug in your OTG adapter there, then connect the printer to that. Power on the printer and check the Pi sees it:

```bash
ls /dev/usb/lp0
```

### Step 6 — Configure from your phone

Open `http://YOUR_PI_IP:5000`, paste in your RSS feed URLs, and hit **[ SAVE & RESTART ]**. Headlines start printing as new stories appear.

Some feeds to start with:
```
https://feeds.npr.org/1002/rss.xml
http://feeds.bbci.co.uk/news/world/rss.xml
https://rsshub.app/apnews/topics/apf-topnews
https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml
```

After that, you don't need SSH again. Settings live at `http://YOUR_PI_IP:5000`, the **Update** button pulls the latest code from GitHub, and everything restarts automatically on power loss.

### Troubleshooting

```bash
# Is the watcher running?
sudo systemctl status printpulse

# Live logs
sudo journalctl -u printpulse -f

# Printer not found?
lsusb
ls -la /dev/usb/

# Restart
sudo systemctl restart printpulse printpulse-web
```

---

## Watch Mode

Polls feeds on a configurable interval and prints new stories. Remembers what it's already printed so you don't get duplicates across restarts.

```bash
# Single feed
printpulse --watch "http://feeds.bbci.co.uk/news/world/rss.xml"

# Multiple feeds, thermal printer, check every 10 minutes
printpulse --watch "https://feeds.npr.org/1002/rss.xml" \
           --watch "http://feeds.bbci.co.uk/news/world/rss.xml" \
           --printer thermal --watch-interval 600

# Quiet hours — nothing prints overnight, queued items print in the morning
printpulse --watch "https://feeds.npr.org/1002/rss.xml" \
           --printer thermal \
           --quiet-start 23:00 --quiet-end 07:00

# Both printers at once
printpulse --watch "..." --printer both
```

Items found during quiet hours are saved to disk, not just skipped — so nothing gets lost even if the story has rotated out of the feed by morning.

---

## Voice Input

Uses [OpenAI Whisper](https://github.com/openai/whisper) running locally — no API key or internet connection required for transcription.

```bash
printpulse -i mic           # press Enter to stop
printpulse -i mic -d 15     # record for 15 seconds
printpulse -i file -a recording.wav
```

Whisper downloads the model on first use. The `base` model (~150MB) is fine for most uses. If accuracy matters more than speed, try `small` or `medium`:

```bash
printpulse -i mic -m small
```

Models in order: `tiny` → `base` (default) → `small` → `medium` → `large`

---

## Fonts

PrintPulse uses [Hershey fonts](https://en.wikipedia.org/wiki/Hershey_fonts) — single-stroke vector fonts designed for plotters and CNC machines, where each letter is drawn as a continuous path rather than filled outlines. They're what makes the output look hand-drawn.

```bash
printpulse -i text -t "Hello" -f cursive
printpulse -i text -t "Hello" -f gothic
printpulse -i text -t "Hello" -f roman
```

Available: `block` (default), `cursive`, `script-bold`, `roman`, `typewriter`, `times`, `gothic`, `italic`, and several others including Greek, Cyrillic, Japanese, and symbol sets.

---

## Letter & Journal Modes

**Letter mode** formats text with a decorative letterhead — useful for actually printing correspondence on the plotter:

```bash
printpulse -i text -t letter.txt --letter
printpulse --letter-template        # interactive compose
printpulse -i text -t letter.txt --letter --stationery victorian
```

**Journal mode** adds a timestamp and tracks page position across multiple entries:

```bash
printpulse -i mic --journal
printpulse -i text -t "Finished the prototype today." --journal
```

---

## Output Options

```bash
--dry-run           # render SVG and preview without printing
--printer thermal   # thermal instead of AxiDraw
--printer both      # both at once
-y                  # skip confirmation prompts
-o output.svg       # save the SVG
--portrait          # portrait orientation (default is landscape)
--theme amber       # amber instead of green terminal theme
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
           [--max-prints N] [--quiet-start HH:MM] [--quiet-end HH:MM]
           [--printer {axidraw,thermal,both}]
           [--letter] [--letter-template]
           [--stationery PROFILE] [--list-stationery]
```

---

## Configuration

State files in your home directory:

```
~/.printpulse_seen.json        # which RSS items have been printed
~/.printpulse_history.json     # print history
~/.printpulse_retry.json       # retry queue for failed prints
~/.printpulse_quiet_queue.json # items held during quiet hours
~/.printpulse/config.json      # settings and defaults
~/.printpulse/stationery/      # custom letterhead profiles (JSON)
```

Custom stationery example:

```json
{
  "name": "myheader",
  "header": {
    "prefix": "FROM THE DESK OF",
    "name": "Your Name",
    "title": "Your Title",
    "font": "scripts",
    "font_size": 20.0,
    "frame_style": "ornamental"
  },
  "body_font": "futural",
  "body_font_size": 12.0
}
```

---

## Architecture

```
printpulse/
  app.py           CLI + argparse
  config.py        Config dataclass, font map, page presets
  ui.py            Retro terminal UI (Rich)
  speech.py        Mic recording + Whisper transcription
  text_to_svg.py   Hershey font rendering + SVG generation
  plotter.py       AxiDraw control
  thermal.py       ESC/POS thermal output
  watch.py         RSS polling, quiet hours, retry queue
  letter.py        Letter document model
  journal.py       Timestamped journal entries
  illustrations.py DALL-E + vtracer illustration pipeline

pi/
  webapp/          Flask web UI
  setup.sh         One-command Pi setup
  appliance.py     Pi-specific config
```

---

## Requirements

- Python 3.9+
- Windows, macOS, or Linux
- AxiDraw plotter (optional — `--dry-run` works without hardware)
- ESC/POS thermal printer (optional)
- Microphone (optional)

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
