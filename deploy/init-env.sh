#!/usr/bin/env bash
# Create the production env file (.env) on the SERVER with new random secrets.
#
#   Run on the SERVER, from the repository folder:   bash deploy/init-env.sh
#
# The secrets are generated here and written straight to the file. They are
# never printed, never typed by a person, and never leave the server.
# .env is in .gitignore, so it cannot be pushed to GitHub.
#
# On the server this file is named .env (not .env.prod) on purpose: Docker
# Compose reads .env automatically, and COMPOSE_FILE below tells it which
# compose files to use. So every command on the server is simply
# "docker compose ..." with no -f or --env-file flags to forget.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -e .env ]; then
    echo ".env already exists. Refusing to overwrite it: the database password inside" >&2
    echo "is the one PostgreSQL was initialised with. Delete it yourself only if you are sure." >&2
    exit 1
fi

umask 077   # the file is created readable by this user only
{
    echo "# Production settings for this server. Created $(date -u +%Y-%m-%dT%H:%M:%SZ). Never commit this file."
    echo "COMPOSE_PROJECT_NAME=quickcart"
    echo "# HTTP only. deploy/enable-https.sh adds docker-compose.https.yml here."
    echo "COMPOSE_FILE=docker-compose.prod.yml"
    echo "POSTGRES_USER=quickcart"
    echo "POSTGRES_DB=quickcart"
    # hex only: the password is placed inside a database URL, where symbols need escaping
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
    echo "JWT_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n' | tr '+/' '-_')"
    echo "SITE_ADDRESS="
} > .env

echo "Created .env with new random secrets (not shown). Permissions:"
ls -l .env
