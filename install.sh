#!/usr/bin/env bash
#
# Home Server installation script.
# Sets up the Python environment, database, systemd service, and Nginx config.
# Safe to re-run: it will not overwrite an existing .env or existing Nginx
# config unless you explicitly confirm.

set -euo pipefail

APP_DIR="/opt/home-server"
SERVICE_USER="server"

echo "=== Home Server Installer ==="

# 1. Verify OS
if [ ! -f /etc/debian_version ]; then
  echo "Warning: this script is written for Debian/Ubuntu. Continuing anyway..."
fi

# 2. Verify we're running from the project directory (or copy ourselves there)
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$CURRENT_DIR" != "$APP_DIR" ]; then
  echo "Copying project to $APP_DIR ..."
  sudo mkdir -p "$APP_DIR"
  sudo rsync -a --exclude 'data' --exclude '.venv' --exclude '.git' "$CURRENT_DIR"/ "$APP_DIR"/
fi

cd "$APP_DIR"

# 3. Create service user (no login shell, no home directory needed)
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Creating system user '$SERVICE_USER'..."
  sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# 4. Create directories
echo "Creating data directories..."
sudo mkdir -p \
  "$APP_DIR"/data/database \
  "$APP_DIR"/data/users \
  "$APP_DIR"/data/shared \
  "$APP_DIR"/data/media/{photos,videos,audio,other} \
  "$APP_DIR"/data/thumbnails \
  "$APP_DIR"/logs \
  "$APP_DIR"/backups

# 5. Python virtual environment
if [ ! -d "$APP_DIR/.venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$APP_DIR/.venv"
fi
echo "Installing Python dependencies..."
"$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 6. Environment file
if [ ! -f "$APP_DIR/.env" ]; then
  echo "Creating .env from .env.example..."
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  SECRET=$("$APP_DIR/.venv/bin/python" -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET/" "$APP_DIR/.env"
  echo "Generated a new SECRET_KEY in .env"
else
  echo ".env already exists, leaving it untouched."
fi

# 7. Permissions (application code root-owned, runtime data owned by service user)
echo "Setting ownership and permissions..."

sudo chown -R root:root "$APP_DIR"

sudo chown -R "$SERVICE_USER":"$SERVICE_USER" \
  "$APP_DIR/data" \
  "$APP_DIR/logs" \
  "$APP_DIR/backups"

sudo chmod 755 "$APP_DIR"
sudo chmod -R a+rX "$APP_DIR/app"
sudo chmod 644 "$APP_DIR/requirements.txt"

sudo chmod -R 750 "$APP_DIR/data"
sudo chmod -R 750 "$APP_DIR/logs"
sudo chmod -R 750 "$APP_DIR/backups"

sudo chmod 640 "$APP_DIR/.env"
sudo chown root:"$SERVICE_USER" "$APP_DIR/.env"

# 8. Initialize database + create first admin
echo ""
echo "Initializing database and creating the first administrator account..."
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/python" -m app.create_admin

# 9. systemd service
echo "Installing systemd service..."
sudo cp "$APP_DIR/home-server.service" /etc/systemd/system/home-server.service
sudo systemctl daemon-reload
sudo systemctl enable home-server

# 10. Nginx
if command -v nginx >/dev/null 2>&1; then
  if [ ! -f /etc/nginx/sites-available/home-server ]; then
    echo "Installing Nginx site config..."
    sudo cp "$APP_DIR/nginx/home-server" /etc/nginx/sites-available/home-server
    sudo ln -sf /etc/nginx/sites-available/home-server /etc/nginx/sites-enabled/home-server
    sudo nginx -t
    sudo systemctl reload nginx
  else
    echo "Nginx site config already exists at /etc/nginx/sites-available/home-server, leaving it untouched."
    echo "Compare it against $APP_DIR/nginx/home-server if you want to update it manually."
  fi
else
  echo "Nginx not found. Install it with: sudo apt install nginx"
fi

# 11. Start the service
echo "Starting home-server..."
sudo systemctl restart home-server
sleep 1
sudo systemctl status home-server --no-pager || true

echo ""
echo "=== Installation complete ==="
echo "Visit the server from your LAN at: http://<this-machine-ip>/"
echo "Check logs with: sudo journalctl -u home-server -f"
