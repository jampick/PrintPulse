# Cloudflare Tunnel Setup for PrintPulse

Access your PrintPulse web UI from anywhere on the internet -- no static IP, no port forwarding, no DNS headaches. Cloudflare Tunnel creates a secure outbound connection from your Pi to Cloudflare's network, so your Pi is never directly exposed.

---

## Prerequisites

- PrintPulse already installed (run `pi/setup.sh` first)
- A free Cloudflare account: <https://dash.cloudflare.com/sign-up>
- A domain added to Cloudflare (even a cheap or free domain works -- Cloudflare just needs to manage DNS)

## Quick Setup

Run the automated setup script on your Pi:

```bash
bash ~/PrintPulse/pi/setup-cloudflare-tunnel.sh
```

The script will:

1. Install `cloudflared` (the Cloudflare Tunnel daemon)
2. Walk you through authenticating with your Cloudflare account
3. Create a tunnel named `printpulse`
4. Ask you for a hostname (e.g. `printpulse.yourdomain.com`)
5. Write the tunnel config and create a DNS record
6. Install and start a systemd service so the tunnel runs on boot

When it finishes, your web UI will be available at `https://YOUR_HOSTNAME`.

## How It Works

```
Browser --> Cloudflare Edge --> Cloudflare Tunnel --> Pi (127.0.0.1:5000)
```

- The Flask app binds to `127.0.0.1` (localhost only) when a tunnel is active, so it is not directly reachable from the network.
- `cloudflared` connects outbound to Cloudflare and proxies HTTPS traffic to the local Flask server.
- Cloudflare handles TLS, so you get HTTPS for free.

## Security Notes

- **Flask binds to localhost**: When the tunnel is set up, the setup script removes `PRINTPULSE_BIND_ALL` from the web service so Flask only listens on `127.0.0.1`. Traffic must go through the tunnel.
- **Authentication still applies**: The existing username/password login on the web UI still protects all routes.
- **Cloudflare Access (optional)**: For extra security, you can add Cloudflare Access (Zero Trust) policies to require SSO or email OTP before reaching your app. See <https://developers.cloudflare.com/cloudflare-one/applications/>.

## Manual Setup (Advanced)

If you prefer to configure things yourself instead of using the script:

### 1. Install cloudflared

```bash
# For Raspberry Pi (ARM)
curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm.deb \
  -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
```

### 2. Authenticate

```bash
cloudflared tunnel login
```

This prints a URL. Open it in a browser, select your domain, and authorize.

### 3. Create a tunnel

```bash
cloudflared tunnel create printpulse
```

### 4. Configure the tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/pi/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: printpulse.yourdomain.com
    service: http://127.0.0.1:5000
  - service: http_status:404
```

### 5. Create DNS record

```bash
cloudflared tunnel route dns printpulse printpulse.yourdomain.com
```

### 6. Install the systemd service

Copy the provided service file and update paths:

```bash
sudo cp ~/PrintPulse/pi/printpulse-tunnel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now printpulse-tunnel
```

### 7. Lock down Flask binding

Remove `PRINTPULSE_BIND_ALL=1` from the web service to bind Flask to localhost only:

```bash
sudo systemctl edit printpulse-web
# Add:
# [Service]
# Environment=PRINTPULSE_BIND_ALL=
```

Then restart: `sudo systemctl restart printpulse-web`

## Managing the Tunnel

```bash
# Check tunnel status
sudo systemctl status printpulse-tunnel

# View tunnel logs
sudo journalctl -u printpulse-tunnel -f

# Restart the tunnel
sudo systemctl restart printpulse-tunnel

# Stop the tunnel (web UI reverts to local-only access)
sudo systemctl stop printpulse-tunnel
```

## Reverting to LAN-Only Access

To disable the tunnel and go back to LAN-only:

```bash
sudo systemctl disable --now printpulse-tunnel
```

Then re-enable LAN binding:

```bash
sudo systemctl edit printpulse-web
# Add:
# [Service]
# Environment=PRINTPULSE_BIND_ALL=1
sudo systemctl restart printpulse-web
```

The web UI will be available at `http://<PI_IP>:5000` again.
