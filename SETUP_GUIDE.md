# 🚀 Personal Home Server Complete Setup & Deployment Guide

This guide covers everything you need to know to deploy **Personal Home Server**, whether you are setting up an old laptop from scratch, installing on an existing Linux OS (Ubuntu/Debian/Raspberry Pi), or running a local development instance on Windows/Mac.

---

## 🎯 Choose Your Installation Track

- 🟢 **[Track 1: Quick 2-Minute Setup on Any Running Linux OS](#track-1-quick-2-minute-setup-on-any-running-linux-os)** (Ubuntu, Debian, Raspberry Pi, Linux Mint)
- 🟢 **[Track 2: Local Testing & Development](#track-2-local-testing--development-windows--mac--linux)** (Run without Nginx/systemd on Windows/Mac/Linux)
- 🟡 **[Track 3: Complete Bare-Metal Setup (Debian from Zero)](#track-3-complete-bare-metal-setup-debian-from-zero)** (ISO flashing, Wi-Fi driver fix, Nginx, systemd, Admin setup, Public Tunnels)

---

## Track 1: Quick 2-Minute Setup on Any Running Linux OS

If you already have a working Linux machine (Ubuntu, Debian, Raspberry Pi OS, Fedora, etc.):

### 1. Download & Run Installer
```bash
# Clone the repository
git clone https://github.com/NIKHIL-bytes/Personal_Home_Server.git
cd Personal_Home_Server

# Run the installer (creates system user, venv, database, systemd service, Nginx config)
sudo ./install.sh
```

### 2. Create Administrator Account
```bash
.venv/bin/python -m app.create_admin
```

### 3. Open in Browser
Visit `http://<your-server-ip>/` from any device on your local network!

---

## Track 2: Local Testing & Development (Windows / Mac / Linux)

Run Home Server locally for testing or development without Nginx or systemd:

### 1. Set Up Python Virtual Environment
```bash
# Linux / Mac:
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell):
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Requirements & Environment
```bash
pip install -r requirements.txt
cp .env.example .env
```

### 3. Initialize Admin & Launch
```bash
python -m app.create_admin
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open `http://127.0.0.1:8000/` in your browser!

---

## Track 3: Complete Bare-Metal Setup (Debian from Zero)

Use this step-by-step guide to turn an old laptop, mini-PC, or desktop into a dedicated 24/7 Home Server.

---

### Step 1: Base OS Installation
1. Download [Debian NetInst ISO](https://www.debian.org/distrib/netinst).
2. Flash to a USB drive using Rufus or BalenaEtcher.
3. Install Debian minimal server (uncheck desktop environment during tasksel to keep it lightweight).
4. Create your default user (`server`) and root password.

---

### Step 2: System Update & Package Installation
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nginx openssh-server NetworkManager rfkill wpasupplicant git curl wget zip sqlite3
```

---

### Step 3: Wi-Fi Driver Handover & NetworkManager Fix
> [!IMPORTANT]
> **Debian Wi-Fi Issue:** Minimal Debian installs use legacy `ifupdown` via `/etc/network/interfaces`. This locks the `wlan0` interface, causing `nmcli` to report device unavailable or busy.

Run these commands to force `ifupdown` to release the Wi-Fi card:

```bash
# 1. Stop legacy networking service
sudo systemctl stop networking 2>/dev/null || true

# 2. Comment out wlan0 lines in /etc/network/interfaces so ifupdown releases it
sudo sed -i 's/^allow-hotplug wlan0/#allow-hotplug wlan0/' /etc/network/interfaces
sudo sed -i 's/^iface wlan0/#iface wlan0/' /etc/network/interfaces

# 3. Enable NetworkManager management
sudo sed -i 's/managed=false/managed=true/' /etc/NetworkManager/NetworkManager.conf

# 4. Unblock wireless radio
sudo rfkill unblock wlan

# 5. Restart NetworkManager
sudo systemctl restart NetworkManager
```

---

### Step 4: Connect Wi-Fi & Enable Persistent Auto-Connect
```bash
# Scan available Wi-Fi networks
sudo nmcli device wifi rescan
sudo nmcli device wifi list

# Connect to your Wi-Fi router (replace SSID and password)
sudo nmcli device wifi connect "YOUR_WIFI_SSID" password "YOUR_WIFI_PASSWORD"

# Configure persistent auto-connection on boot (no user login required)
sudo nmcli connection modify "YOUR_WIFI_SSID" connection.autoconnect yes
sudo nmcli connection modify "YOUR_WIFI_SSID" connection.autoconnect-priority 100
sudo nmcli connection modify "YOUR_WIFI_SSID" connection.autoconnect-retries 0
sudo nmcli connection modify "YOUR_WIFI_SSID" connection.permissions ""

# Enable NetworkManager & SSH services to start on boot
sudo systemctl enable NetworkManager
sudo systemctl enable --now ssh
```

---

### Step 5: Directory & Storage Setup
```bash
# Create dedicated unprivileged service user
sudo useradd -r -s /bin/false server 2>/dev/null || true

# Set up main deployment folder
sudo mkdir -p /opt/home-server
sudo chown -R server:server /opt/home-server

# Create storage directories
sudo mkdir -p /opt/home-server/data/{database,users,shared,media,thumbnails}
sudo mkdir -p /opt/home-server/logs

sudo chown -R server:server /opt/home-server/data /opt/home-server/logs
sudo chmod -R 750 /opt/home-server/data /opt/home-server/logs
```

---

### Step 6: Environment Configuration (`.env`)

Create `/opt/home-server/.env`:

```bash
cat << 'EOF' | sudo tee /opt/home-server/.env
APP_NAME=Home Server
APP_ENV=production
COOKIE_SECURE=false

# Generate secret key: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=YOUR_GENERATED_SECRET_KEY_HERE

DATABASE_PATH=/opt/home-server/data/database/server.db
USER_STORAGE_PATH=/opt/home-server/data/users
SHARED_STORAGE_PATH=/opt/home-server/data/shared
MEDIA_STORAGE_PATH=/opt/home-server/data/media
THUMBNAIL_PATH=/opt/home-server/data/thumbnails

MAX_UPLOAD_SIZE=5368709120
SESSION_TIMEOUT_HOURS=168
DEFAULT_USER_QUOTA_BYTES=21474836480
EOF

sudo chown root:server /opt/home-server/.env
sudo chmod 640 /opt/home-server/.env
```

---

### Step 7: Create Virtual Environment & Admin Account
```bash
python3 -m venv /opt/home-server/.venv
/opt/home-server/.venv/bin/pip install -r /opt/home-server/requirements.txt

cd /opt/home-server
sudo -u server /opt/home-server/.venv/bin/python3 -m app.create_admin
```

---

### Step 8: systemd Hardened Service (`home-server.service`)

Create `/etc/systemd/system/home-server.service`:

```ini
[Unit]
Description=Home Server (FastAPI backend)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=server
Group=server
WorkingDirectory=/opt/home-server
EnvironmentFile=/opt/home-server/.env
ExecStart=/opt/home-server/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=3

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/home-server/data /opt/home-server/logs
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now home-server
sudo systemctl status home-server --no-pager
```

---

### Step 9: Nginx Reverse Proxy Setup

Create `/etc/nginx/sites-available/home-server`:

```nginx
server {
    listen 80;
    server_tokens off;
    server_name _;

    client_max_body_size 5G;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    # Security block: prevent serving hidden/sensitive files
    location ~* \.(env|db|db-journal|db-wal|db-shm|log)$ {
        deny all;
        return 404;
    }
    location ~ /\.git {
        deny all;
        return 404;
    }
    location ^~ /logs/ {
        deny all;
        return 404;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Range headers for video/audio seeking
        proxy_set_header Range $http_range;
        proxy_set_header If-Range $http_if_range;
        proxy_buffering off;
    }

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "same-origin" always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'" always;
}
```

Enable Nginx config and reload:
```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/home-server /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

### Step 10: Making Your Server Public (Cloudflare Tunnels)

Expose your server securely over the public internet without port forwarding or opening router ports:

#### Option A: Instant Free Public Link (No Domain Required)
Generate a temporary, encrypted HTTPS link (`https://xxxx.trycloudflare.com`) instantly:
```bash
# Run cloudflared against local port 8000 (or port 80 via Nginx)
cloudflared tunnel --url http://127.0.0.1:8000
```

#### Option B: Permanent Production Custom Domain Setup
Connect a custom domain (e.g. `drive.yourdomain.com`) with free Cloudflare SSL & DDoS mitigation:
```bash
# 1. Install Cloudflare package repo
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install cloudflared -y

# 2. Login to Cloudflare account
cloudflared tunnel login

# 3. Create named tunnel
cloudflared tunnel create home-server

# 4. Route domain hostname to tunnel
cloudflared tunnel route dns home-server drive.yourdomain.com

# 5. Install tunnel as system service
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
```

---

### Step 11: Operational Commands Cheat Sheet

| Action | Command |
| --- | --- |
| **Check App Logs** | `sudo journalctl -u home-server -n 100 -f` |
| **Check Service Status** | `sudo systemctl status home-server` |
| **Restart Backend** | `sudo systemctl restart home-server` |
| **Reload Nginx** | `sudo nginx -t && sudo systemctl reload nginx` |
| **Promote User to Admin** | `sudo sqlite3 /opt/home-server/data/database/server.db "UPDATE users SET role='admin' WHERE username='<username>';"` |
| **Run Backup Script** | `sudo /opt/home-server/backup.sh` |
