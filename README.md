# 🏠 Personal Home Server

A production-grade, self-hosted personal & family cloud server. Designed from the ground up to run blazing fast on low-power hardware (such as an old laptop with an Intel i3, 4 GB RAM, 1 TB HDD, or a Raspberry Pi) while providing a sleek, modern browser dashboard.

```
[ Public Internet / LAN Visitor ]
                 │
  (Cloudflare Tunnel / Nginx Proxy)
                 │
                 ▼
      [ Nginx Reverse Proxy ]
                 │
      ┌──────────┴──────────┐
      ▼                     ▼
/static/ Assets      FastAPI / Uvicorn
(Served Direct)      (127.0.0.1:8000)
                            │
                    ┌───────┴───────┐
                    ▼               ▼
               SQLite DB       Filesystem
           (data/database)   (data/ storage)
```

---

## 🚀 Why Personal Home Server? (Features & Advantages)

* ⚡ **Ultra-Lightweight Footprint:** Consumes **less than 40 MB of RAM** at idle. Perfect for breathing new life into old laptops or low-spec hardware without needing heavy cloud instances.
* 🔐 **Enterprise-Grade Security:** 
  * Passwords hashed using **Argon2id** (winner of the Password Hashing Competition).
  * Session cookies store 384-bit random tokens (only SHA-256 hashes are kept in the database).
  * Automatic rate-limiting on login endpoints to prevent brute-force attacks.
  * Double-submit CSRF token validation on all state-changing requests.
* 🛡️ **Zero Path-Traversal Risk:** All filesystem queries pass through a strict `safe_join()` validator that mathematically guarantees requests cannot escape user storage roots (protecting against `../../etc/passwd` style attacks).
* 📁 **Personal File Vault:** Per-user private file storage with directory tree navigation, live upload progress, text previewing (`.txt`, `.md`, `.log`, `.csv`), PDF viewing, and in-browser file management.
* 🤝 **Admin-Controlled Shared Drive:** A centralized shared folder accessible to all authenticated users for reading and downloading shared family documents.
* 🎬 **Lag-Free 4K/1080p Video Streaming:** Native HTTP Range request support (`206 Partial Content`). Play and seek through multi-gigabyte video/audio files instantly without loading the full file into server RAM.
* 👑 **Full Admin Power Panel:** 
  * View real-time CPU, RAM, and Disk metrics via `psutil`.
  * Browse, download, rename, or delete files directly inside **any user's storage**.
  * Reset passwords, toggle user active status, enforce individual storage quotas, or force-logout compromised sessions.
* 📜 **Full Audit Logging:** Detailed audit logging recording timestamps, IP addresses, usernames, and targets for every download, login, user creation, and file deletion.
* 🌐 **Public Access Ready:** Supports instant free temporary URLs as well as permanent custom domain integration via **Cloudflare Tunnels**.

---

## 🌐 Public Internet Access Setup

Expose your server securely to the public internet without port forwarding or opening firewall ports:

### Method 1: Instant Free Public Tunnel (No Domain Needed)
Get a quick, secure HTTPS link (`https://xxxx.trycloudflare.com`) instantly:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

---

### Method 2: Permanent Custom Domain (Production Setup)
Connect your custom domain (e.g., `drive.yourdomain.com`) with free Cloudflare SSL & DDoS protection:

```bash
# 1. Login to Cloudflare
cloudflared tunnel login

# 2. Create a named tunnel
cloudflared tunnel create home-server

# 3. Route your domain to the tunnel
cloudflared tunnel route dns home-server drive.yourdomain.com

# 4. Install Cloudflare Tunnel as a persistent system service
sudo cloudflared service install <YOUR_CLOUDFLARE_TUNNEL_TOKEN>
```

---

## ⚡ Choose Your Setup Path

| Setup Method | Best For | Difficulty | Est. Time |
| --- | --- | --- | --- |
| **[Option A: 2-Minute Quick Auto-Installer](#option-a-2-minute-quick-auto-installer-any-existing-linux-os)** | Any existing Linux (Ubuntu, Debian, Raspbian, Mint, etc.) | 🟢 Very Easy | 2 mins |
| **[Option B: Local Testing / Prototyping](#option-b-local-testing--development-windows--mac--linux)** | Testing or running locally on Windows, Mac, or Linux | 🟢 Very Easy | 1 min |
| **[Option C: Bare-Metal Bare-Minimum Setup](#option-c-bare-metal-dedicated-server-debian-from-scratch)** | Turning an old laptop/PC into a dedicated 24/7 server from zero | 🟡 Intermediate | 10 mins |
| **[Option D: Manual / Custom Installation](#option-d-manual--custom-installation)** | Custom servers, non-systemd distros, or custom Nginx setups | 🔵 Flexible | 5 mins |

---

### Option A: 2-Minute Quick Auto-Installer (Any Existing Linux OS)

```bash
# 1. Clone the repository
git clone https://github.com/NIKHIL-bytes/Personal_Home_Server.git
cd Personal_Home_Server

# 2. Run the automated installer
sudo ./install.sh

# 3. Create the first Administrator account
.venv/bin/python -m app.create_admin

# 4. Open http://<your-server-ip>/ in your browser!
```

---

### Option B: Local Testing / Development (Windows / Mac / Linux)

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# 2. Install dependencies & configure .env
pip install -r requirements.txt
cp .env.example .env

# 3. Create initial admin account
python -m app.create_admin

# 4. Run server directly
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open `http://127.0.0.1:8000/` in your browser!

---

### Option C: Bare-Metal Dedicated Server (Debian from Scratch)

Turning an old laptop into a 24/7 Home Server? Refer to the comprehensive guide:

👉 **[SETUP_GUIDE.md](SETUP_GUIDE.md)** for:
1. Installing minimal Debian Linux from USB.
2. Resolving Wi-Fi driver hardware locks (`ifupdown` handover to `NetworkManager`).
3. Configuring persistent auto-connecting Wi-Fi and SSH.
4. Hardened systemd service deployment & Nginx configuration.
5. Cloudflare Tunnel setup for remote custom domain access.

---

### Option D: Manual / Custom Installation

```bash
# 1. Install dependencies & set up .venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

# 2. Generate a secure secret key in .env
python3 -c "import secrets; print(secrets.token_hex(32))"

# 3. Create administrator account
.venv/bin/python -m app.create_admin

# 4. Copy systemd service unit & start service
sudo cp home-server.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now home-server

# 5. Copy Nginx site config & reload Nginx
sudo cp nginx/home-server /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/home-server /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 📚 Complete Documentation

* 📖 **[SETUP_GUIDE.md](SETUP_GUIDE.md)** — Complete deployment guide covering OS installation, Wi-Fi driver fixes, Nginx reverse proxy, systemd hardening, and Cloudflare Tunnels.
* 🏡 **[HOW_IT_RUNS.md](HOW_IT_RUNS.md)** — A clear, non-technical architecture breakdown explaining how request flows, SQLite WAL mode, video streaming, and security guards work under the hood.

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.
