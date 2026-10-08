#!/usr/bin/env bash
# Restore a database backup made by deploy/backup.sh.
#
#   Run from the repository folder:   bash deploy/restore-db.sh backups/<timestamp>
#
# Order on a NEW server (the API must not have started yet):
#   1. docker compose up -d db                 only PostgreSQL
#   2. bash deploy/restore-db.sh backups/...   this script
#   3. docker compose up -d --build            the API starts and applies newer migrations, if any
#   4. bash deploy/restore-uploads.sh backups/...
#
# Why this order: the dump contains the tables AND the alembic_version row that
# says which migration they are at. Restored into an empty database, the API
# then knows exactly which migrations are still missing. If the API started
# first, it would create empty tables and the restore would collide with them.
#
# Safety: the script REFUSES to touch a database that already contains tables.
# To replace an existing database on purpose, make a backup first, then pass
# --replace-existing. That deletes the current data.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

backup_dir="${1:-}"
mode="${2:-}"
dump="${backup_dir%/}/quickcart.dump"
if [ -z "$backup_dir" ] || [ ! -f "$dump" ]; then
    echo "Usage: bash deploy/restore-db.sh backups/<timestamp> [--replace-existing]" >&2
    exit 1
fi

echo "==> Checking the backup file"
(cd "$backup_dir" && grep -E '[ *]quickcart\.dump$' MANIFEST.txt | sha256sum -c --status -) \
    || { echo "Checksum mismatch: the dump is damaged or incomplete." >&2; exit 1; }

if [ -n "$(docker compose ps -q --status running api 2>/dev/null)" ]; then
    echo "The API container is running. Stop it first, so nothing writes during the restore:" >&2
    echo "    docker compose stop api" >&2
    exit 1
fi

sql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"' sh "$1" | tr -d '\r'; }

tables="$(sql "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
restore_flags="--no-owner --no-privileges --exit-on-error --single-transaction"
if [ "$tables" != "0" ]; then
    echo "The target database is NOT empty (${tables} tables):"
    for table in users products orders; do
        echo "    ${table}: $(sql "SELECT count(*) FROM ${table}" 2>/dev/null || echo '?') rows"
    done
    if [ "$mode" != "--replace-existing" ]; then
        echo "Nothing was changed. To replace this data on purpose, back it up first, then run:" >&2
        echo "    bash deploy/restore-db.sh ${backup_dir} --replace-existing" >&2
        exit 1
    fi
    echo "--replace-existing given: the current tables will be dropped and replaced."
    restore_flags="$restore_flags --clean --if-exists"
fi

echo "==> Restoring"
docker compose cp "$dump" db:/tmp/restore.dump
# --single-transaction: either the whole backup is restored, or nothing changes
docker compose exec -T db sh -c \
    "pg_restore -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" $restore_flags /tmp/restore.dump"
docker compose exec -T -u root db rm -f /tmp/restore.dump

echo "==> Result (compare with ${backup_dir%/}/MANIFEST.txt)"
echo "alembic_revision=$(sql 'SELECT version_num FROM alembic_version')"
for table in users products orders order_items cart_items; do
    echo "rows_${table}=$(sql "SELECT count(*) FROM ${table}")"
done
