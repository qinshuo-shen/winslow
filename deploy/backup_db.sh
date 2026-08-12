#!/bin/bash
# Nightly VPS-side backup of the single sessions.db (cron: 0 3 * * *).
# Uses sqlite3's online .backup command rather than `cp`, so a backup taken
# mid-write never captures a half-flushed file. Old copies are pruned after
# 30 days; the Mac mini pulls this directory nightly over Tailscale
# (see README) so a copy also lives off the VPS.
set -euo pipefail

DB_PATH="/opt/winslow/app/data/sessions.db"
BACKUP_DIR="/opt/winslow/backups"
TS=$(date +%Y%m%d)

mkdir -p "$BACKUP_DIR"
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/sessions-$TS.db'"
find "$BACKUP_DIR" -name 'sessions-*.db' -mtime +30 -delete
