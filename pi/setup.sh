#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  PrintPulse Appliance — One-Shot Setup Script
#  Run this once on a fresh Raspberry Pi OS Lite installation.
#
#  Usage:  bash setup.sh
# ═══════════════════════════════════════════════════════════════════

set -e  # Stop on any error

echo ""
echo "╔═════════════════════════════════════════════════════╗"
echo "║         PRINTPULSE APPLIANCE SETUP                 ║"
echo "╚═════════════════════════════════════════════════════╝"
echo ""

# ── 1. System packages ──────────────────────────────────────────
echo "[1/7] Installing system packages..."
sudo apt update -qq
sudo apt install -y -qq python3 python3-venv python3-pip git > /dev/null 2>&1
echo "  OK"

# ── 2. Clone repo (or update if already cloned) ─────────────────
echo "[2/7] Setting up PrintPulse..."
cd /home/pi

if [ -d "PrintPulse" ]; then
    echo "  Repository exists, pulling latest..."
    cd PrintPulse
    git pull --ff-only || true
    cd /home/pi
else
    echo "  Cloning repository..."
    git clone https://github.com/jampick/PrintPulse.git
fi

# ── 3. Create virtual environment and install ────────────────────
echo "[3/7] Creating Python environment..."
python3 -m venv printpulse-venv
source printpulse-venv/bin/activate

# Install only what's needed for thermal watch mode (lightweight)
pip install --quiet --upgrade pip
pip install --quiet feedparser rich requests flask

# Install the package itself (without heavy deps like whisper)
pip install --quiet --no-deps -e PrintPulse

echo "  OK"

# ── 4. USB printer permissions ───────────────────────────────────
echo "[4/7] Setting up printer permissions..."
sudo usermod -a -G lp pi 2>/dev/null || true
echo "  Added user 'pi' to 'lp' group for USB printer access"

# ── 5. Sudoers for service control (Flask needs this) ────────────
echo "[5/7] Configuring service permissions..."
sudo tee /etc/sudoers.d/printpulse > /dev/null << 'SUDOERS'
pi ALL=(ALL) NOPASSWD: /bin/systemctl restart printpulse
pi ALL=(ALL) NOPASSWD: /bin/systemctl stop printpulse
pi ALL=(ALL) NOPASSWD: /bin/systemctl start printpulse
pi ALL=(ALL) NOPASSWD: /bin/systemctl is-active printpulse
SUDOERS
sudo chmod 440 /etc/sudoers.d/printpulse
echo "  OK"

# ── 6. Install systemd services ─────────────────────────────────
echo "[6/7] Installing systemd services..."
sudo cp /home/pi/PrintPulse/pi/printpulse.service /etc/systemd/system/
sudo cp /home/pi/PrintPulse/pi/printpulse-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable printpulse printpulse-web
echo "  Services enabled (will start on boot)"

# ── 7. Create default config and start ───────────────────────────
echo "[7/7] Creating default configuration..."
python3 -c "
import sys
sys.path.insert(0, '/home/pi/PrintPulse')
from pi.appliance import save_config, default_config, CONFIG_PATH
import os
if not os.path.isfile(CONFIG_PATH):
    save_config(default_config())
    print('  Default config created')
else:
    print('  Config already exists, keeping it')
"

# Start the services
echo ""
echo "Starting services..."
sudo systemctl start printpulse-web
echo "  Web UI started"

# Get the Pi's IP address
PI_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "╔═════════════════════════════════════════════════════╗"
echo "║              SETUP COMPLETE!                       ║"
echo "╠═════════════════════════════════════════════════════╣"
echo "║                                                     ║"
echo "║  Web UI:  http://${PI_IP}:5000                  ║"
echo "║                                                     ║"
echo "║  Next steps:                                        ║"
echo "║  1. Plug in your thermal printer via USB            ║"
echo "║  2. Open the web UI from your phone or laptop       ║"
echo "║  3. Add your RSS feeds and click Save & Restart     ║"
echo "║                                                     ║"
echo "║  Useful commands:                                   ║"
echo "║  sudo systemctl status printpulse    (check watcher)║"
echo "║  sudo journalctl -u printpulse -f   (live logs)    ║"
echo "║  sudo systemctl restart printpulse   (restart)      ║"
echo "║                                                     ║"
echo "╚═════════════════════════════════════════════════════╝"
echo ""
echo "NOTE: You may need to reboot for printer permissions"
echo "to take effect:  sudo reboot"
echo ""
