# 🏠 Home Server

A lightweight, self-hosted personal/family file, media, and administration cloud server. Built to run smoothly on low-power hardware (such as an old laptop with an Intel i3, 4 GB RAM, 1 TB HDD, or a Raspberry Pi) while providing a modern, responsive browser interface.

```
[ Visitor in Browser ] ──(HTTP/HTTPS)──> [ Nginx Reverse Proxy ]
                                                  │
                                       ┌──────────┴──────────┐
                                       ▼                     ▼
                               /static/ Assets        FastAPI / Uvicorn
                              (Served Direct)         (127.0.0.1:8000)
                                                             │
                                                     ┌───────┴───────┐
                                                     ▼               ▼
                                                SQLite DB       Filesystem
                                            (data/database)   (data/ storage)
```

---

## 🌟 Key Features

* 🔐 **Secure Multi-User Authentication:** Passwords hashed with **Argon2id**, high-entropy 384-bit session tokens, rate-limited login endpoints, and double-submit CSRF protection.
* 📁 **Personal File Vault:** Per-user private file storage with directory tree navigation, file upload quota checks, text previewing, PDF viewing, and in-browser download management.
* 🛡️ **Path Traversal Protection:** Deterministic path isolation via `safe_join()` preventing unauthorized filesystem navigation beyond permitted roots.
* 🤝 **Shared Repository:** Admin-controlled shared folder accessible to all authenticated users for reading and downloading shared documents.
* 🎬 **Lag-Free Media Streaming:** Video and audio streaming powered by HTTP Range requests (`206 Partial Content`), allowing seeking in multi-gigabyte files without overloading RAM.
* ⚙️ **Admin Control Panel:** User creation/editing, storage usage stats, password resetting, session force-logout, full storage wiping, in-browser user file manager, and system resource monitoring (CPU, RAM, Disk).
* 📜 **Audit Logging:** System-wide audit logging tracking all administrative actions, logins, and file operations.
* 🌐 **Cloudflare Tunnel Ready:** Pre-configured for optional public access via `cloudflared` named tunnels.

---

## ⚡ Choose Your Setup Path

Choose the setup method that best matches your hardware and operating system:

| Setup Method | Best For | Difficulty | Est. Time |
| --- | --- | --- | --- |
| **[Option A: 2-Minute Quick Auto-Installer](#option-a-2-minute-quick-auto-installer-any-existing-linux-os)** | Any existing Linux (Ubuntu, Debian, Raspbian, Mint, etc.) | 🟢 Very Easy | 2 mins |
| **[Option B: Local Testing / Prototyping](#option-b-local-testing--development-windows--mac--linux)** | Testing or running locally on Windows, Mac, or Linux | 🟢 Very Easy | 1 min |
| **[Option C: Bare-Metal Bare-Minimum Setup](#option-c-bare-metal-dedicated-server-debian-from-scratch)** | Turning an old laptop/PC into a dedicated 24/7 server from zero | 🟡 Intermediate | 10 mins |
| **[Option D: Manual / Custom OS Installation](#option-d-manual--custom-installation)** | Custom servers, non-systemd distros, or custom Nginx setups | 🔵 Flexible | 5 mins |

---

### Option A: 2-Minute Quick Auto-Installer (Any Existing Linux OS)

If you already have a Linux OS running (Ubuntu, Debian, Raspberry Pi OS, Linux Mint, Fedora, etc.):

```bash
# 1. Clone the repository
git clone https://github.com/your-username/home-server.git
cd home-server

# 2. Run the automated installer (creates user, venv, database, systemd service & Nginx config)
sudo ./install.sh

# 3. Create the first Administrator account
.venv/bin/python -m app.create_admin

# 4. Open http://<your-server-ip>/ in your browser!
```

---

### Option B: Local Testing / Development (Windows / Mac / Linux)

Want to test Home Server locally on your computer without Nginx or systemd?

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy example configuration
cp .env.example .env

# 4. Create the initial admin account
python -m app.create_admin

# 5. Run the server directly
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open `http://127.0.0.1:8000/` in your browser!

---

### Option C: Bare-Metal Dedicated Server (Debian from Scratch)

Turning an old laptop or mini-PC into a 24/7 Home Server? Refer to the comprehensive guide:

👉 **[SETUP_GUIDE.md](SETUP_GUIDE.md)** for:
1. Installing minimal Debian Linux from USB.
2. Resolving Wi-Fi driver hardware locks (`ifupdown` handover to `NetworkManager`).
3. Configuring persistent auto-connecting Wi-Fi and SSH.
4. Hardened systemd service deployment & Nginx configuration.
5. Cloudflare Tunnel setup for remote domain access.

---

### Option D: Manual / Custom Installation

If you prefer to configure systemd and Nginx manually step-by-step:

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

* 📖 **[SETUP_GUIDE.md](SETUP_GUIDE.md)** — Step-by-step setup guide covering OS installation, Wi-Fi driver fixes, Nginx reverse proxy, systemd hardening, and Cloudflare Tunnels.
* 🏡 **[HOW_IT_RUNS.md](HOW_IT_RUNS.md)** — A clear, non-technical architecture breakdown explaining how request flows, SQLite WAL mode, video streaming, and security guards work under the hood.

---

## 🛡️ Security Features

* **Zero Plaintext Passwords:** Hashes generated with Argon2id.
* **Token Hashing:** Only SHA-256 hashes of session tokens are stored in the database.
* **Storage Isolation:** Every file path is validated via `safe_join()` before touching disk.
* **Hardened Service:** systemd service unit runs with `NoNewPrivileges=true`, `PrivateTmp=true`, and `ProtectSystem=strict`.

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.
