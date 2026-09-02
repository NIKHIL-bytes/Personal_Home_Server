#!/usr/bin/env bash
#
# Home Server update script.
# Pulls the latest code (if this is a git checkout), reinstalls dependencies,
# and restarts the service. Never touches the data/ directory.

set -euo pipefail

APP_DIR="/opt/home-server"
cd "$APP_DIR"

echo "=== Home Server Updater ==="

if [ -d .git ]; then
  echo "Pulling latest changes..."
  git pull
else
  echo "Not a git checkout — skipping git pull. Replace application files manually, then re-run this script."
fi

echo "Installing/updating Python dependencies..."
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "Restarting service..."
sudo systemctl restart home-server
sleep 1

echo "Verifying service health..."
sleep 1
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then
  echo "Service is healthy."
else
  echo "Warning: health check failed. Check logs with: sudo journalctl -u home-server -n 100"
  exit 1
fi

echo "=== Update complete ==="
