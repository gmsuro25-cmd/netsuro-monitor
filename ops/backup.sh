#!/bin/sh
set -eu

if [ -n "${POSTGRES_PASSWORD_FILE:-}" ]; then
  PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
  export PGPASSWORD
fi
if [ -z "${PGPASSWORD:-}" ]; then
  echo "PostgreSQL password is required" >&2
  exit 1
fi

mkdir -p /backups

while true; do
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  target="/backups/netsuro-${timestamp}.dump"
  temporary="${target}.tmp"
  pg_dump --host="$POSTGRES_HOST" --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" --format=custom --file="$temporary"
  mv "$temporary" "$target"
  find /backups -type f -name 'netsuro-*.dump' -mtime "+$BACKUP_RETENTION_DAYS" -delete
  echo "backup completed file=$(basename "$target")"
  sleep "$BACKUP_INTERVAL_SECONDS"
done
