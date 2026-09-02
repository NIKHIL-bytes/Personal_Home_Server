#!/usr/bin/env bash
#
# Home Server backup script.
# Backs up the SQLite database and configuration (the things that are hard
# to reconstruct). Does NOT copy the media/user file library by default —
# that can be terabytes and should be backed up separately (e.g. rsync to
# external storage) rather than duplicated on every run.

set -euo pipefail

APP_DIR="/opt/home-server"
BACKUP_DIR="$APP_DIR/backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/backup-$TIMESTAMP"

mkdir -p "$DEST"

echo "Backing up database..."
sqlite3 "$APP_DIR/data/database/server.db" ".backup '$DEST/server.db'"

echo "Backing up configuration..."
cp "$APP_DIR/.env" "$DEST/.env" 2>/dev/null || echo "  (no .env found, skipping)"
cp "$APP_DIR/nginx/home-server" "$DEST/nginx-home-server" 2>/dev/null || true
cp "$APP_DIR/home-server.service" "$DEST/home-server.service" 2>/dev/null || true

echo "Compressing..."
tar -czf "$BACKUP_DIR/backup-$TIMESTAMP.tar.gz" -C "$BACKUP_DIR" "backup-$TIMESTAMP"
rm -rf "$DEST"

echo "Backup written to: $BACKUP_DIR/backup-$TIMESTAMP.tar.gz"

# Keep the last 14 backups, delete older ones.
ls -1t "$BACKUP_DIR"/backup-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm --

echo "Done."
