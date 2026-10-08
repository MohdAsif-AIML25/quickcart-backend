#!/usr/bin/env bash
# Restore the uploaded product images from a backup made by deploy/backup.sh.
#
#   Run from the repository folder:   bash deploy/restore-uploads.sh backups/<timestamp>
#
# The API container must be running: the files are unpacked inside it, as the
# same user the API runs as, into the uploads volume. Paths are kept exactly
# (products/<name>), so the image_url values in the database keep working.
# Existing files are kept; a file with the same name is overwritten.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

backup_dir="${1:-}"
archive="${backup_dir%/}/uploads.tar.gz"
if [ -z "$backup_dir" ] || [ ! -f "$archive" ]; then
    echo "Usage: bash deploy/restore-uploads.sh backups/<timestamp>" >&2
    exit 1
fi
(cd "$backup_dir" && grep -E '[ *]uploads\.tar\.gz$' MANIFEST.txt | sha256sum -c --status -) \
    || { echo "Checksum mismatch: the archive is damaged or incomplete." >&2; exit 1; }

docker compose cp "$archive" api:/tmp/uploads.tar.gz
docker compose exec -T api tar -C /app/uploads -xzf /tmp/uploads.tar.gz
docker compose exec -T -u root api rm -f /tmp/uploads.tar.gz

sql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"' sh "$1" | tr -d '\r'; }

echo "==> Checking that every product image in the database exists on disk"
missing=0
while IFS= read -r url; do
    [ -z "$url" ] && continue
    # image_url is "/uploads/products/<file>"; the volume is mounted at /app/uploads
    if ! docker compose exec -T api test -f "/app${url}"; then
        echo "    MISSING: ${url}"
        missing=$((missing + 1))
    fi
done < <(sql "SELECT image_url FROM products WHERE image_url IS NOT NULL")

files="$(docker compose exec -T api sh -c 'find /app/uploads -type f | wc -l' | tr -d '\r ')"
echo "files in the uploads volume: ${files}; images referenced but missing: ${missing}"
[ "$missing" -eq 0 ]
