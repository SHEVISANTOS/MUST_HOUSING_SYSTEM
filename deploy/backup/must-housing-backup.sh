#!/usr/bin/env bash
# Nightly backup of the Ubuntu deployment's local Postgres database and
# local-disk media uploads (property photos) - unlike the Vercel/Neon
# deployment, there's no managed point-in-time recovery here, so this is
# the only backup this data gets. Mirrors the pattern in
# VOT-Stay/deploy/backup/backup.sh, adapted for a local (non-pooled) DB and
# for local media storage, which that app doesn't need to back up itself.
#
# Run by cron/systemd timer from the app directory:
#   APP_DIR=/srv/must_housing deploy/backup/must-housing-backup.sh
# Optional off-site copy: BACKUP_S3_URI=s3://bucket/must_housing (uses the
# aws CLI with AWS_* credentials and AWS_S3_ENDPOINT_URL for Cloudflare R2).
# Never prints the database URL.
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/must_housing}"
DIR="${BACKUP_DIR:-/var/backups/must_housing}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"

cd "$APP_DIR"
DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | sed -E "s/^DATABASE_URL=//; s/^['\"]//; s/['\"]\$//")"
: "${DATABASE_URL:?DATABASE_URL not found in $APP_DIR/.env}"

mkdir -p "$DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB_FILE="$DIR/must_housing-db-$STAMP.dump"
MEDIA_FILE="$DIR/must_housing-media-$STAMP.tar.gz"

pg_dump --format=custom --no-owner --no-privileges --compress=6 --file="$DB_FILE" --dbname="$DATABASE_URL"
pg_restore --list "$DB_FILE" > /dev/null   # the archive is readable
sha256sum "$DB_FILE" > "$DB_FILE.sha256"
echo "DB backup written: $DB_FILE ($(du -h "$DB_FILE" | cut -f1))"

if [ -d "$APP_DIR/media" ] && [ -n "$(ls -A "$APP_DIR/media" 2>/dev/null)" ]; then
  tar -czf "$MEDIA_FILE" -C "$APP_DIR" media
  sha256sum "$MEDIA_FILE" > "$MEDIA_FILE.sha256"
  echo "Media backup written: $MEDIA_FILE ($(du -h "$MEDIA_FILE" | cut -f1))"
else
  echo "No local media/ directory to back up (R2 storage is configured, or it's empty)."
fi

if [ -n "${BACKUP_S3_URI:-}" ]; then
  for f in "$DB_FILE" "$DB_FILE.sha256" "$MEDIA_FILE" "$MEDIA_FILE.sha256"; do
    [ -f "$f" ] && aws s3 cp "$f" "$BACKUP_S3_URI/" ${AWS_S3_ENDPOINT_URL:+--endpoint-url "$AWS_S3_ENDPOINT_URL"} --only-show-errors
  done
  echo "Copied off-site to $BACKUP_S3_URI/"
fi

find "$DIR" -name 'must_housing-*' -mtime +"$KEEP_DAYS" -delete
