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

backup_file="${1:-}"
if [ -z "$backup_file" ]; then
  backup_file="$(find /backups -type f -name 'netsuro-*.dump' | sort | tail -n 1)"
fi
if [ -z "$backup_file" ] || [ ! -f "$backup_file" ]; then
  echo "No backup file found" >&2
  exit 1
fi

test_database="netsuro_restore_test"
dropdb --host="$POSTGRES_HOST" --username="$POSTGRES_USER" --if-exists "$test_database"
createdb --host="$POSTGRES_HOST" --username="$POSTGRES_USER" "$test_database"
pg_restore --host="$POSTGRES_HOST" --username="$POSTGRES_USER" \
  --dbname="$test_database" --no-owner --no-privileges "$backup_file"
psql --host="$POSTGRES_HOST" --username="$POSTGRES_USER" --dbname="$test_database" \
  --command="SELECT COUNT(*) AS restored_monitors FROM monitors;"
dropdb --host="$POSTGRES_HOST" --username="$POSTGRES_USER" "$test_database"
printf '{"file":"%s","verified_at":"%s"}\n' \
  "$(basename "$backup_file")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > /backups/.last-verified
echo "restore verification completed file=$(basename "$backup_file")"
