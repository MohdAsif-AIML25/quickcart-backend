#!/usr/bin/env bash
# Back up the database AND the uploaded product images of the running stack.
#
#   Run from the repository folder:   bash deploy/backup.sh
#   (on the laptop it backs up the development stack, on the server the production stack)
#
# Result: backups/<timestamp>/ with
#   quickcart.dump    the whole database (pg_dump custom format, compressed)
#   uploads.tar.gz    every file in the uploads volume
#   MANIFEST.txt      when, which migration revision, row counts, checksums
#
# The two files belong together: products in the dump point to image files in
# the archive. The database is dumped FIRST. Images are only ever added (each
# upload gets a new random name), so an archive taken afterwards contains every
# image the dump refers to.
#
# backups/ is in .gitignore. A backup holds email addresses and password
# hashes: never commit it, never share it.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: do not rewrite /tmp/... paths

stamp="$(date -u +%Y%m%d-%H%M%S)"
target="backups/${stamp}"
mkdir -p "$target"
chmod 700 backups "$target" 2>/dev/null || true

echo "==> Database"
# pg_dump reads one consistent snapshot, even while the shop is in use.
# --no-owner / --no-privileges: the dump can be restored under any user name.
docker compose exec -T db sh -c \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges -f /tmp/quickcart.dump'
docker compose cp db:/tmp/quickcart.dump "$target/quickcart.dump"
docker compose exec -T db rm -f /tmp/quickcart.dump

echo "==> Uploaded images"
docker compose exec -T api tar -C /app/uploads -czf /tmp/uploads.tar.gz .
docker compose cp api:/tmp/uploads.tar.gz "$target/uploads.tar.gz"
docker compose exec -T api rm -f /tmp/uploads.tar.gz

echo "==> Manifest"
sql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"' sh "$1" | tr -d '\r'; }
{
    echo "created_utc=${stamp}"
    echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "alembic_revision=$(sql 'SELECT version_num FROM alembic_version')"
    for table in users products orders order_items cart_items; do
        echo "rows_${table}=$(sql "SELECT count(*) FROM ${table}")"
    done
    echo "products_with_image=$(sql 'SELECT count(*) FROM products WHERE image_url IS NOT NULL')"
    echo "upload_files=$(tar -tzf "$target/uploads.tar.gz" | grep -vc '/$' || true)"
    (cd "$target" && sha256sum quickcart.dump uploads.tar.gz)
} > "$target/MANIFEST.txt"

cat "$target/MANIFEST.txt"
echo
echo "Backup written to ${target}/"
