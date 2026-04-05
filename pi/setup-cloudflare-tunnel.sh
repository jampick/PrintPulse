#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  PrintPulse — Cloudflare Tunnel Setup
#
#  Exposes the PrintPulse web UI to the internet via Cloudflare
#  Tunnel (no static IP, no port forwarding required).
#
#  Prerequisites:
#    - A free Cloudflare account (https://dash.cloudflare.com/sign-up)
#    - A domain managed by Cloudflare (even a free one works)
#    - PrintPulse already set up (run setup.sh first)
#
#  Usage:  bash setup-cloudflare-tunnel.sh
# ═══════════════════════════════════════════════════════════════════

set -e

PP_USER="$(whoami)"
PP_HOME="$(eval echo ~$PP_USER)"

echo ""
echo "╔═════════════════════════════════════════════════════╗"
echo "║     PRINTPULSE — CLOUDFLARE TUNNEL SETUP           ║"
echo "╚═════════════════════════════════════════════════════╝"
echo ""

# ── 1. Install cloudflared ─────────────────────────────────────────
echo "[1/5] Installing cloudflared..."

if command -v cloudflared &> /dev/null; then
    echo "  cloudflared already installed: $(cloudflared --version)"
else
    # Detect architecture for correct package
    ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
    case "$ARCH" in
        armhf|armv7l|armv6l)
            CF_ARCH="arm"
            ;;
        arm64|aarch64)
            CF_ARCH="arm64"
            ;;
        amd64|x86_64)
            CF_ARCH="amd64"
            ;;
        *)
            echo "  ERROR: Unsupported architecture: $ARCH"
            exit 1
            ;;
    esac

    echo "  Detected architecture: $ARCH -> cloudflared $CF_ARCH"

    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}.deb"
    TMP_DEB="/tmp/cloudflared.deb"

    echo "  Downloading cloudflared..."
    curl -sL "$CF_URL" -o "$TMP_DEB"
    sudo dpkg -i "$TMP_DEB" > /dev/null 2>&1 || sudo apt-get install -f -y -qq > /dev/null 2>&1
    rm -f "$TMP_DEB"

    echo "  Installed: $(cloudflared --version)"
fi

# ── 2. Authenticate with Cloudflare ────────────────────────────────
echo ""
echo "[2/5] Authenticating with Cloudflare..."
echo ""

CF_CERT="$PP_HOME/.cloudflared/cert.pem"
if [ -f "$CF_CERT" ]; then
    echo "  Already authenticated (cert.pem found)."
else
    echo "  You need to log in to your Cloudflare account."
    echo "  A URL will open (or be printed) — paste it into a browser"
    echo "  on your phone or laptop, pick your domain, and authorize."
    echo ""
    cloudflared tunnel login
    echo ""
    echo "  Authentication successful."
fi

# ── 3. Create the tunnel ──────────────────────────────────────────
echo "[3/5] Creating Cloudflare tunnel..."

TUNNEL_NAME="printpulse"

# Check if the tunnel already exists
if cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
    echo "  Tunnel '$TUNNEL_NAME' already exists."
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')
else
    cloudflared tunnel create "$TUNNEL_NAME"
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')
    echo "  Created tunnel: $TUNNEL_NAME (ID: $TUNNEL_ID)"
fi

echo "  Tunnel ID: $TUNNEL_ID"

# ── 4. Configure the tunnel ───────────────────────────────────────
echo ""
echo "[4/5] Configuring tunnel..."

CF_CONFIG_DIR="$PP_HOME/.cloudflared"
CF_CONFIG="$CF_CONFIG_DIR/config.yml"
mkdir -p "$CF_CONFIG_DIR"

echo ""
echo "  Your tunnel needs a hostname on your Cloudflare domain."
echo "  Example: printpulse.yourdomain.com"
echo ""
read -p "  Enter the full hostname (e.g. printpulse.example.com): " TUNNEL_HOSTNAME

while [ -z "$TUNNEL_HOSTNAME" ]; do
    read -p "  Hostname cannot be empty. Try again: " TUNNEL_HOSTNAME
done

cat > "$CF_CONFIG" << CFGEOF
tunnel: $TUNNEL_ID
credentials-file: $CF_CONFIG_DIR/${TUNNEL_ID}.json

ingress:
  - hostname: $TUNNEL_HOSTNAME
    service: http://127.0.0.1:5000
  - service: http_status:404
CFGEOF

echo "  Config written to $CF_CONFIG"

# Create DNS record
echo "  Creating DNS record for $TUNNEL_HOSTNAME..."
cloudflared tunnel route dns "$TUNNEL_NAME" "$TUNNEL_HOSTNAME" 2>/dev/null || true
echo "  DNS route configured."

# ── 5. Install systemd service ────────────────────────────────────
echo "[5/5] Installing systemd service..."

sudo tee /etc/systemd/system/printpulse-tunnel.service > /dev/null << SVCEOF
[Unit]
Description=PrintPulse Cloudflare Tunnel
After=network-online.target printpulse-web.service
Wants=network-online.target

[Service]
Type=simple
User=$PP_USER
ExecStart=$(command -v cloudflared) tunnel run $TUNNEL_NAME
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

# Add sudoers entry for tunnel service control
sudo tee -a /etc/sudoers.d/printpulse > /dev/null << SUDEOF
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart printpulse-tunnel
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl stop printpulse-tunnel
$PP_USER ALL=(ALL) NOPASSWD: /bin/systemctl start printpulse-tunnel
SUDEOF
sudo chmod 440 /etc/sudoers.d/printpulse

# Lock Flask to localhost (traffic goes through the tunnel now)
# Remove PRINTPULSE_BIND_ALL so Flask binds to 127.0.0.1
sudo mkdir -p /etc/systemd/system/printpulse-web.service.d
sudo tee /etc/systemd/system/printpulse-web.service.d/tunnel.conf > /dev/null << DROPEOF
[Service]
Environment=PRINTPULSE_BIND_ALL=
DROPEOF

sudo systemctl daemon-reload
sudo systemctl enable printpulse-tunnel
sudo systemctl restart printpulse-web
sudo systemctl start printpulse-tunnel

echo "  Tunnel service installed and started."
echo "  Flask now binds to 127.0.0.1 (tunnel-only access)."

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "╔═════════════════════════════════════════════════════╗"
echo "║           CLOUDFLARE TUNNEL READY!                 ║"
echo "╠═════════════════════════════════════════════════════╣"
echo "║                                                     ║"
echo "║  Your PrintPulse web UI is now accessible at:       ║"
echo "║                                                     ║"
echo "║    https://$TUNNEL_HOSTNAME"
echo "║                                                     ║"
echo "║  The tunnel runs automatically on boot.             ║"
echo "║                                                     ║"
echo "║  Useful commands:                                   ║"
echo "║  sudo systemctl status printpulse-tunnel            ║"
echo "║  sudo journalctl -u printpulse-tunnel -f            ║"
echo "║  sudo systemctl restart printpulse-tunnel           ║"
echo "║                                                     ║"
echo "╚═════════════════════════════════════════════════════╝"
echo ""
