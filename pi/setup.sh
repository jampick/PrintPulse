#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  PrintPulse Appliance — One-Shot Setup Script
#  Run this once on a fresh Raspberry Pi OS Lite installation.
#
#  Usage:  bash setup.sh
# ═══════════════════════════════════════════════════════════════════

set -e  # Stop on any error

# Auto-detect current user and home directory
PP_USER="$(whoami)"
PP_HOME="$(eval echo ~$PP_USER)"

echo ""
echo "╔═════════════════════════════════════════════════════╗"
echo "║         PRINTPULSE APPLIANCE SETUP                 ║"
echo "╚═════════════════════════════════════════════════════╝"
echo ""
echo "  User: $PP_USER"
echo "  Home: $PP_HOME"
echo ""

# ── 1. System packages ──────────────────────────────────────────
echo "[1/8] Installing system packages..."
sudo apt update -qq
sudo apt install -y -qq python3 python3-venv python3-pip git network-manager avahi-daemon > /dev/null 2>&1
# Ensure NetworkManager manages wlan0 (needed for AP mode)
sudo systemctl enable NetworkManager 2>/dev/null || true
sudo systemctl start NetworkManager 2>/dev/null || true
# Enable mDNS for .local hostname resolution
sudo systemctl enable avahi-daemon 2>/dev/null || true
sudo systemctl start avahi-daemon 2>/dev/null || true
echo "  OK"

# ── 2. Clone repo (or update if already cloned) ─────────────────
echo "[2/8] Setting up PrintPulse..."
cd "$PP_HOME"

if [ -d "PrintPulse" ]; then
    echo "  Repository exists, pulling latest..."
    cd PrintPulse
    git pull --ff-only || true
    cd "$PP_HOME"
else
    echo "  Cloning repository..."
    git clone https://github.com/jampick/PrintPulse.git
fi

# ── 3. Create virtual environment and install ────────────────────
echo "[3/8] Creating Python environment..."
python3 -m venv "$PP_HOME/printpulse-venv"
source "$PP_HOME/printpulse-venv/bin/activate"

# Install only what's needed for thermal watch mode (lightweight)
pip install --quiet --upgrade pip
pip install --quiet feedparser rich requests flask

# Install the package itself (without heavy deps like whisper)
pip install --quiet --no-deps -e "$PP_HOME/PrintPulse"

echo "  OK"

# ── 4. USB printer permissions ───────────────────────────────────
echo "[4/8] Setting up printer permissions..."
sudo usermod -a -G lp "$PP_USER" 2>/dev/null || true
echo "  Added user '$PP_USER' to 'lp' group for USB printer access"

# ── 5. Sudoers for service control (Flask needs this) ────────────
echo "[5/8] Configuring service permissions..."
sudo tee /etc/sudoers.d/printpulse > /dev/null << SUDOERS
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart printpulse
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl stop printpulse
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl start printpulse
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl is-active printpulse
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart printpulse-web
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart printpulse-wifi
$PP_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli
SUDOERS
sudo chmod 440 /etc/sudoers.d/printpulse
echo "  OK"

# ── 6. Install systemd services ─────────────────────────────────
echo "[6/8] Installing systemd services..."

# Generate service files with correct user and paths
sudo tee /etc/systemd/system/printpulse.service > /dev/null << SVCFILE
[Unit]
Description=PrintPulse News Watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$PP_USER
ExecStart=$PP_HOME/printpulse-venv/bin/python -m printpulse.pi_launcher
WorkingDirectory=$PP_HOME/PrintPulse
Restart=on-failure
RestartSec=10
Environment=HOME=$PP_HOME
Environment=PYTHONPATH=$PP_HOME/PrintPulse
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCFILE

sudo tee /etc/systemd/system/printpulse-web.service > /dev/null << WEBFILE
[Unit]
Description=PrintPulse Web Config UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$PP_USER
ExecStart=$PP_HOME/printpulse-venv/bin/python $PP_HOME/PrintPulse/pi/webapp/server.py
WorkingDirectory=$PP_HOME/PrintPulse
Restart=on-failure
RestartSec=5
Environment=HOME=$PP_HOME
Environment=PYTHONPATH=$PP_HOME/PrintPulse
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
WEBFILE

sudo tee /etc/systemd/system/printpulse-wifi.service > /dev/null << WIFIFILE
[Unit]
Description=PrintPulse WiFi Provisioning
Before=printpulse.service printpulse-web.service
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
User=root
ExecStart=$PP_HOME/printpulse-venv/bin/python -c "import sys; sys.path.insert(0, '$PP_HOME/PrintPulse'); from pi.wifi_provision import run_provisioning_check; run_provisioning_check()"
Environment=HOME=$PP_HOME
Environment=PYTHONPATH=$PP_HOME/PrintPulse
RemainAfterExit=yes
TimeoutStartSec=60

[Install]
WantedBy=multi-user.target
WIFIFILE

sudo systemctl daemon-reload
sudo systemctl enable printpulse printpulse-web printpulse-wifi
echo "  Services enabled (will start on boot)"

# ── 7. Set hostname for mDNS ───────────────────────────────────
echo "[7/8] Setting up mDNS hostname..."
# Set hostname to 'printpulse' so the device is reachable at printpulse.local
if [ "$(hostname)" != "printpulse" ]; then
    sudo hostnamectl set-hostname printpulse 2>/dev/null || true
    echo "  Hostname set to 'printpulse' (reachable at printpulse.local)"
else
    echo "  Hostname already set"
fi

# ── 8. Create config and set up web UI credentials ──────────────
echo "[8/8] Setting up configuration and credentials..."
echo ""
echo "  The web UI requires a username and password."
echo "  You'll use these to log in from your phone/laptop."
echo ""

# Prompt for web UI credentials
read -p "  Choose a web UI username: " WEB_USER
while [ -z "$WEB_USER" ]; do
    read -p "  Username cannot be empty. Try again: " WEB_USER
done

read -s -p "  Choose a web UI password: " WEB_PASS
echo ""
while [ -z "$WEB_PASS" ]; do
    read -s -p "  Password cannot be empty. Try again: " WEB_PASS
    echo ""
done

# Create config with hashed credentials
python3 -c "
import sys
sys.path.insert(0, '$PP_HOME/PrintPulse')
from pi.appliance import save_config, load_config, default_config, hash_password, generate_secret_key, CONFIG_PATH
import os

if os.path.isfile(CONFIG_PATH):
    config = load_config()
    print('  Existing config found, updating credentials...')
else:
    config = default_config()
    print('  Creating new config...')

config['auth_user'] = '$WEB_USER'
config['auth_hash'] = hash_password('$WEB_PASS')
config['secret_key'] = generate_secret_key()
save_config(config)
print('  Credentials saved (password hashed, not stored in plaintext)')
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
