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
| **A computer or phone** | For initial SD card flashing and WiFi setup. |

**You do NOT need**: a monitor, keyboard, mouse, or HDMI cable. We'll set everything up "headlessly" over Wi-Fi.

---

## Getting Started (New OOBE Flow)

PrintPulse has a built-in WiFi setup experience. On first boot, the Pi creates its own WiFi hotspot so you can configure it from your phone — no need to pre-configure WiFi credentials.

### Step 1: Flash the SD Card

1. **Download Raspberry Pi Imager** from [raspberrypi.com/software](https://www.raspberrypi.com/software/) and install it.

2. **Insert your SD card** into your PC (use an adapter if needed).

3. **Open Raspberry Pi Imager** and:
   - Click **"Choose OS"** → select **"Raspberry Pi OS (other)"** → select **"Raspberry Pi OS Lite (32-bit)"**
     - Pick the "Lite" version — no desktop needed, saves memory
   - Click **"Choose Storage"** → select your SD card

4. **Click the gear icon** (⚙) in the bottom-right corner:
   - **Enable SSH**: check "Use password authentication"
   - **Set username and password**: pick a username and password you'll remember
   - **Skip "Configure wireless LAN"** — PrintPulse handles WiFi setup for you!
   - **Set locale**: your timezone and keyboard layout
   - Click **Save**

5. Click **"Write"** and wait for it to finish (~5 minutes).

### Step 2: Initial Setup (one-time, requires temporary WiFi)

For the initial setup script, you need the Pi on your network temporarily. You can either:

**Option A — Use Raspberry Pi Imager's WiFi setting** for this first boot only, then use PrintPulse's WiFi management going forward. Or:

**Option B — Use the SD card WiFi file** (see [SD Card WiFi Provisioning](#sd-card-wifi-provisioning-power-user-alternative) below).

Once the Pi is on your network:

1. **Find the Pi's IP** — check your router's admin page, or try `ping raspberrypi.local`
2. **SSH in**: `ssh YOUR_USERNAME@YOUR_PI_IP`
3. **Run the setup script**:

```bash
git clone https://github.com/jampick/PrintPulse.git
bash PrintPulse/pi/setup.sh
```

This takes about 5-10 minutes on a Pi Zero (it's a slow processor — be patient). It will:
- Install Python, NetworkManager, and avahi (mDNS)
- Set up the PrintPulse software
- Configure WiFi provisioning service
- Set hostname to `printpulse` (reachable at `printpulse.local`)
- Configure auto-start on boot
- Start the web config UI

**Reboot** to activate everything:

```bash
sudo reboot
```

### Step 3: Connect to PrintPulse WiFi (on subsequent boots)

After setup, whenever the Pi can't find a known WiFi network, it automatically creates a hotspot:

1. **On your phone or laptop**, look for the WiFi network **`PrintPulse-Setup`**
2. **Connect to it** — a setup page will appear automatically (captive portal)
3. **Select your home WiFi** from the list and enter your password
4. **The Pi joins your network** — the setup hotspot disappears

Now connect back to your home WiFi and visit:

```
http://printpulse.local:5000
```

(If `.local` doesn't work, find the Pi's IP in your router's admin page.)

### Step 4: Plug in the Printer

1. Plug the **USB OTG adapter** into the Pi's data USB port (the one closest to the center, NOT the power port).
2. Plug your **thermal printer's USB cable** into the OTG adapter.
3. Turn on the thermal printer.

To verify the Pi sees the printer:

```bash
ls /dev/usb/lp0
```

If you see `/dev/usb/lp0`, the printer is connected.

### Step 5: Configure from Your Phone

1. Open a web browser on your phone or laptop.
2. Go to `http://printpulse.local:5000`
3. Log in with the credentials you set during setup.
4. Add your RSS feeds and click **[ SAVE & RESTART ]**.

---

## SD Card WiFi Provisioning (Power User Alternative)

If you prefer to pre-configure WiFi without using the hotspot, create a text file called `printpulse-wifi.txt` on the SD card's boot partition:

```
SSID=YourNetworkName
PASSWORD=YourWiFiPassword
```

**How it works:**
- On first boot, PrintPulse checks for this file before starting AP mode
- If found, it configures WiFi using the credentials and **deletes the file** (for security)
- The AP hotspot is skipped entirely

**File location:**
- **Raspberry Pi OS Bookworm** (newer): place on the `bootfs` partition (shows as `/boot/firmware/` on the Pi)
- **Raspberry Pi OS Bullseye** (older): place on the `boot` partition (shows as `/boot/` on the Pi)

**Notes:**
- The file is deleted after use — your password is not left on the SD card
- Leave `PASSWORD=` empty for open (unsecured) networks
- Lines starting with `#` are treated as comments

---

## Resetting WiFi

If you move the appliance to a new network, or need to reconfigure WiFi:

### From the Web UI
Click the **[ RESET WIFI ]** button on the main configuration page. The Pi will drop back into AP mode (`PrintPulse-Setup` hotspot) so you can pick a new network.

### From SSH
```bash
sudo systemctl restart printpulse-wifi
```

This re-runs the provisioning check. If the current WiFi is unavailable, the Pi will start AP mode.

---

## Daily Use

Once set up, you never need to SSH in again. Just:

1. **Leave it plugged in** — it starts automatically on boot
2. **Change settings** from your phone at `http://printpulse.local:5000`
3. **Tear off printed stories** from the thermal printer

### What happens when...

| Situation | What happens |
|-----------|-------------|
| Power goes out and comes back | Pi reboots, services auto-start, resumes printing |
| Wi-Fi drops temporarily | Watcher retries automatically, resumes when connected |
| Printer runs out of paper | Replace paper roll, stories queue and print when ready |
| You want to stop printing | Hit [ STOP ] on the web UI |
| You move to a new WiFi network | Pi can't connect → starts AP mode → reconfigure from phone |

---

## Troubleshooting

### WiFi Setup Issues

**AP hotspot (`PrintPulse-Setup`) doesn't appear:**
```bash
# SSH in via ethernet or temporary WiFi and check:
sudo systemctl status printpulse-wifi
sudo journalctl -u printpulse-wifi -f

# Verify NetworkManager is running:
sudo systemctl status NetworkManager

# Manually trigger AP mode:
sudo nmcli connection up printpulse-ap
```

**Can't reach `printpulse.local`:**
```bash
# Check avahi is running:
sudo systemctl status avahi-daemon

# If .local doesn't work, find the IP directly:
hostname -I
```

**Connected to AP but no captive portal:**
- Open a browser manually and go to `http://192.168.4.1:5000/wifi`

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
groups $(whoami)
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
                                     First Boot / No WiFi
                                    ┌─────────────────────────┐
                                    │  printpulse-wifi.service │
                                    │  (runs before web/watch) │
                                    │                          │
                                    │  1. WiFi connected? ─yes─▶ Done
                                    │  2. SD card config? ─yes─▶ Connect + Done
                                    │  3. Start AP mode        │
                                    │     SSID: PrintPulse-Setup│
                                    └──────────┬──────────────┘
                                               │
                                    User connects to hotspot
                                    picks home WiFi in portal
                                               │
                                               ▼
Your Phone/Laptop                    Raspberry Pi Zero
┌──────────────┐                    ┌─────────────────────┐
│   Browser    │───── Wi-Fi ──────▶│  Flask Web UI       │
│  (port 5000) │                    │  (printpulse-web)   │
│              │                    │         │           │
│  printpulse  │                    │    writes config    │
│  .local:5000 │                    │         ▼           │
└──────────────┘                    │  ~/.printpulse_     │
                                    │  appliance.json     │
                                    │         │           │
                                    │    restarts service  │
                                    │         ▼           │
                                    │  Watch Mode         │──▶ USB ──▶ Thermal
                                    │  (printpulse)       │           Printer
                                    │  polls RSS feeds    │
                                    └─────────────────────┘
```

### Systemd Services

| Service | Purpose |
|---------|---------|
| `printpulse-wifi` | Runs once at boot: checks WiFi, tries SD card config, falls back to AP mode |
| `printpulse-web` | Flask web UI on port 5000 (also serves the WiFi captive portal) |
| `printpulse` | RSS feed watcher + thermal printer |
