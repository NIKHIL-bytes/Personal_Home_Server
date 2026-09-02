# 🏡 How Home Server Works: Explained Simply!

Welcome! If you ever wondered how **Home Server** works under the hood, imagine it as a **super-smart, 24/7 Digital Apartment Building**. 

Here is the simple story of how every piece of code and file works together to keep your files safe, stream videos, and let administrators manage users!

---

## 🏰 The Main Characters (The Architecture)

Imagine your server machine as a high-security building:

```
[ Visitor in Browser ]
         │
         ▼
🕵️‍♂️ Nginx (The Front Gate Doorman)
         │
         ▼
👮‍♂️ FastAPI (The Central Building Manager)
      ├── 🔑 Security & Guard (security.py, dependencies.py)
      ├── 🛡️ Safe Join Guard (utils.py)
      ├── 🗄️ SQLite Record Book (database.py)
      └── 📁 Storage Vaults (data/users, data/shared, data/media)
```

---

## 🚪 Step 1: The Front Gate Doorman — Nginx
📁 **File location:** `/etc/nginx/sites-available/home-server`

Whenever a user opens `http://<your-server-ip>/` in their browser:
1. **Nginx** is the first person to meet the request.
2. It acts as a guard. If an intruder tries to steal secret files (like `.env` or `server.db`), Nginx immediately blocks them with a `404 Not Found`.
3. If the request is safe, Nginx hands it over internally to our Python backend listening privately at `http://127.0.0.1:8000`.

---

## ⚡ Step 2: The Heartbeat Engine — systemd & Uvicorn
📁 **File location:** `/etc/systemd/system/home-server.service` & `app/main.py`

* **systemd (`home-server.service`)** is like the building's emergency generator. If the server restarts or the app crashes, systemd automatically revives it within 3 seconds!
* **Uvicorn & FastAPI (`app/main.py`)** is the engine. When FastAPI starts up:
  - It runs `init_db()` from `app/database.py` to make sure the SQLite database tables (`users`, `sessions`, `audit_logs`) exist.
  - It attaches security middlewares like CSRF token validation (`csrf_middleware`).
  - It mounts all feature routes (`admin`, `auth`, `files`, `media`, `pages`, `shared`, `system`).

---

## 🗄️ Step 3: The Secret Filing Cabinet — SQLite Database
📁 **File location:** `app/database.py` & `data/database/server.db`

Instead of running a heavy database that eats up all memory, our server uses **SQLite** (`server.db`).
* `app/database.py` manages connections using Python's built-in `sqlite3`.
* It uses **WAL Mode (Write-Ahead Logging)** so multiple operations can happen at once without locking up.
* It maintains 3 simple tables:
  1. `users`: Stores usernames, roles (`admin` or `user`), active status, storage quota, and password hashes.
  2. `sessions`: Stores active login session tokens (hashed with SHA-256 so raw tokens are never saved on disk).
  3. `audit_logs`: Records who did what and when (e.g., `USER_CREATED`, `FILE_DELETE`, `PASSWORD_CHANGED`).

---

## 🔐 Step 4: The Vault & Security Guard — Argon2id & `safe_join()`
📁 **File location:** `app/security.py` & `app/utils.py`

### How Passwords Work (`app/security.py`)
Passwords are **never stored in plain text**. When a user types a password:
* `hash_password()` converts it into a scrambled string using **Argon2id** (the gold standard for password hashing).
* When logging in, `verify_password()` checks the math. Even if an attacker steals `server.db`, they cannot reverse the hashes into plain passwords.

### How File Safety Works (`app/utils.py` -> `safe_join()`)
Imagine someone tries a trick like requesting `../../../etc/passwd` to read system files.
* `safe_join(root, relative_path)` inspects every path request.
* If a path tries to jump outside the user's permitted folder (`data/users/<id>/`), `safe_join()` catches it and throws a `PathSecurityError`.

---

## 🎬 Step 5: Streaming Videos & Audio Without Lag
📁 **File location:** `app/utils.py` -> `range_streaming_response()` & `app/routers/media.py`

If you play a 2 GB movie in the Media tab:
* The server **does NOT load the 2 GB file into memory** (which would crash a 4 GB RAM laptop!).
* Instead, `range_streaming_response()` streams the video in tiny **1 MB chunks** on demand as you watch or seek through the timeline.

---

## 🛠️ Step 6: The Admin Command Center
📁 **File location:** `app/routers/admin.py`, `app/templates/admin.html`, `app/static/js/admin.js`

When an Administrator opens `http://<your-server-ip>/admin`:

1. **HTML Shell (`admin.html`):** Renders the clean user interface with tabs for `Overview`, `Users`, and `Activity`.
2. **Client Logic (`admin.js`):**
   * Calls `/api/admin/stats` to display real-time CPU, RAM, and Disk usage via `psutil`.
   * Calls `/api/admin/users` to fetch the list of registered users.
   * Renders action buttons for every user: **Browse**, **Disable/Enable**, **Reset PW**, and **Delete**.
3. **Storage Browser (`openUserDetail` in `admin.js`):**
   * When an Admin clicks **Browse** next to a user, it calls `/api/admin/users/{user_id}/files`.
   * The Admin can browse that specific user's folders, view/preview files, download items, rename entries, or delete files directly.

---

## 🧩 Map of All Code Files

| File Name | Simple Explanation |
| --- | --- |
| `app/main.py` | **The Master Switch:** Connects all routers, static files, and security middlewares. |
| `app/database.py` | **The Accountant:** Creates database tables and manages SQLite connections. |
| `app/security.py` | **The Locksmith:** Hashes passwords with Argon2id and generates secure session tokens. |
| `app/utils.py` | **The Inspector:** Protects against path traversal (`safe_join`), streams videos in chunks, and checks file sizes. |
| `app/routers/auth.py` | **The Receptionist:** Handles user login, logout, and login rate limiting. |
| `app/routers/files.py` | **Personal Storage Manager:** Lets users upload, view, rename, and delete their own files in `data/users/<id>/`. |
| `app/routers/shared.py` | **Shared Folder Manager:** Handles the public read-only shared drive in `data/shared/`. |
| `app/routers/media.py` | **Cinema Manager:** Scans photos/videos in `data/media/` and generates thumbnail previews. |
| `app/routers/admin.py` | **The Control Center:** Full admin endpoints for user creation, password reset, storage browsing, and audit logs. |
| `backup.sh` | **The Safety Net:** Automatically packages the database and `.env` config into `.tar.gz` backups. |

---

### 🎉 That's It!
Your Home Server is designed like a well-oiled machine: minimal memory footprint, maximum security, and lightning-fast speed on low-power hardware.
