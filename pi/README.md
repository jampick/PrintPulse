# PrintPulse Pi Zero Appliance

Turn a Raspberry Pi Zero into a standalone news ticker that automatically prints headlines on a thermal receipt printer — no screen, no keyboard, just plug in and go.

Configure everything from your phone or laptop via a web page on your local network.

---

## What You Need

| Item | Notes |
|------|-------|
| **Raspberry Pi Zero W** or **Zero 2 W** | The "W" means it has Wi-Fi built in. ~$10-15. [Buy here](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) |
| **Micro SD card** | 16GB or bigger. Any brand is fine. |
| **USB thermal printer** | Rongta 58mm, or any ESC/POS compatible receipt printer. ~$20-30 on Amazon. |
| **Micro USB OTG adapter** | A tiny adapter that converts the Pi's micro-USB port to a regular USB port so you can plug in the printer. ~$5. Search "micro USB OTG adapter" on Amazon. |
| **USB-C power supply** (for Zero 2 W) or **Micro USB power supply** (for Zero W) | The official Raspberry Pi power supply works great. Any 5V/2.5A phone charger will also work. |
| **A computer** | Your Windows PC, to set up the SD card and SSH in. You only need this for initial setup. |

**You do NOT need**: a monitor, keyboard, mouse, or HDMI cable. We'll set everything up "headlessly" over Wi-Fi.

---

## Step 1: Flash the SD Card

This puts the operating system onto your SD card.

1. **Download Raspberry Pi Imager** from [raspberrypi.com/software](https://www.raspberrypi.com/software/) and install it on your Windows PC.

2. **Insert your SD card** into your PC (use an adapter if needed).

3. **Open Raspberry Pi Imager** and:
   - Click **"Choose OS"** → select **"Raspberry Pi OS (other)"** → select **"Raspberry Pi OS Lite (32-bit)"**
     - Pick the "Lite" version — no desktop needed, saves memory
   - Click **"Choose Storage"** → select your SD card

4. **Click the gear icon** (⚙) in the bottom-right corner. This is the important part:
   - **Enable SSH**: check "Use password authentication"
   - **Set username and password**: username = `pi`, pick a password you'll remember
   - **Configure wireless LAN**: enter your Wi-Fi network name (SSID) and password
   - **Set locale**: your timezone and keyboard layout
   - Click **Save**

5. Click **"Write"** and wait for it to finish (~5 minutes).

6. **Put the SD card in the Pi** and plug in power. The Pi will boot up and connect to your Wi-Fi automatically. Give it 2-3 minutes on the first boot.

---

## Step 2: Find Your Pi on the Network

You need to find the Pi's IP address so you can connect to it.

### Option A: Use your router
Log into your router's admin page (usually `192.168.1.1` or `192.168.0.1`). Look for a device named `raspberrypi` in the connected devices list.

### Option B: Use a command
Open **Command Prompt** on your Windows PC and try:

```
ping raspberrypi.local
```

If it responds, your Pi's address is shown. If not, try:

```
arp -a
```

Look for an IP that wasn't there before (usually something like `192.168.1.XXX`).

### Option C: Use an app
Download **Fing** on your phone (free). It scans your network and shows all devices.

---

## Step 3: Connect to the Pi via SSH

SSH lets you type commands on the Pi from your Windows PC.

1. Open **Command Prompt** (or PowerShell) on your Windows PC.

2. Type:
   ```
   ssh pi@YOUR_PI_IP
   ```
   Replace `YOUR_PI_IP` with the IP you found in Step 2 (e.g., `ssh pi@192.168.1.42`).

3. It will ask "Are you sure you want to continue connecting?" — type `yes` and press Enter.

4. Enter the password you set in Step 1.

You should now see a prompt like:
```
pi@raspberrypi:~ $
```

You're in! Everything from here is typed into this SSH window.

---

## Step 4: Run the Setup Script

This one command installs everything:

```bash
git clone https://github.com/jampick/PrintPulse.git
bash PrintPulse/pi/setup.sh
```

This takes about 5-10 minutes on a Pi Zero (it's a slow processor — be patient). It will:
- Install Python and required packages
- Set up the PrintPulse software
- Configure auto-start on boot
- Start the web config UI

When it's done, you'll see a message like:

```
╔═════════════════════════════════════════════════════╗
║              SETUP COMPLETE!                       ║
║                                                     ║
║  Web UI:  http://192.168.1.42:5000                  ║
╚═════════════════════════════════════════════════════╝
```

**Reboot once** to activate printer permissions:

```bash
sudo reboot
```

Wait a minute, then SSH back in if needed.

---

## Step 5: Plug in the Printer

1. Plug the **USB OTG adapter** into the Pi's data USB port (the one closest to the center, NOT the power port).
2. Plug your **thermal printer's USB cable** into the OTG adapter.
3. Turn on the thermal printer.

To verify the Pi sees the printer:

```bash
ls /dev/usb/lp0
```

If you see `/dev/usb/lp0`, the printer is connected.

---

## Step 6: Configure from Your Phone

1. Open a web browser on your phone or laptop.
2. Go to `http://YOUR_PI_IP:5000` (the URL from the setup output).
3. You'll see the PrintPulse configuration page.

### Add RSS Feeds

Paste one feed URL per line. Here are some good ones:

```
https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml
http://feeds.bbci.co.uk/news/world/rss.xml
https://feeds.npr.org/1001/rss.xml
```

### Adjust Settings

- **Poll interval**: How often to check for new stories (300 = every 5 minutes)
- **Max prints per cycle**: How many stories to print each time (3 is a good default)

### Save & Go

Click **[ SAVE & RESTART ]**. The watcher will restart with your new settings and start printing new headlines as they appear.

---

## Daily Use

Once set up, you never need to SSH in again. Just:

1. **Leave it plugged in** — it starts automatically on boot
2. **Change settings** from your phone at `http://YOUR_PI_IP:5000`
3. **Tear off printed stories** from the thermal printer

### What happens when...

| Situation | What happens |
|-----------|-------------|
| Power goes out and comes back | Pi reboots, services auto-start, resumes printing |
| Wi-Fi drops temporarily | Watcher retries automatically, resumes when connected |
| Printer runs out of paper | Replace paper roll, stories queue and print when ready |
| You want to stop printing | Hit [ STOP ] on the web UI |

---

## Troubleshooting

### Check if the watcher is running

```bash
sudo systemctl status printpulse
```

### See live logs

```bash
sudo journalctl -u printpulse -f
```

(Press Ctrl+C to stop watching logs)

### Printer not found

```bash
# Check if the device exists
ls -la /dev/usb/lp0

# If not, check USB devices
lsusb

# Make sure you're in the lp group
groups pi
```

### Restart everything

```bash
sudo systemctl restart printpulse
sudo systemctl restart printpulse-web
```

### Web UI not loading

```bash
sudo systemctl status printpulse-web
sudo journalctl -u printpulse-web -f
```

### Update to latest version

```bash
cd ~/PrintPulse
git pull
sudo systemctl restart printpulse printpulse-web
```

---

## Architecture

```
Your Phone/Laptop                    Raspberry Pi Zero
┌──────────────┐                    ┌─────────────────────┐
│   Browser    │───── Wi-Fi ──────▶│  Flask Web UI       │
│  (port 5000) │                    │  (printpulse-web)   │
└──────────────┘                    │         │           │
                                    │    writes config    │
                                    │         ▼           │
                                    │  ~/.printpulse_     │
                                    │  appliance.json     │
                                    │         │           │
                                    │    restarts service  │
                                    │         ▼           │
                                    │  Watch Mode         │──▶ USB ──▶ Thermal
                                    │  (printpulse)       │           Printer
                                    │  polls RSS feeds    │
                                    └─────────────────────┘
```
