#!/usr/bin/env bash
# Switch the server from HTTP to HTTPS for one domain name.
#
#   Run on the SERVER, from the repository folder:   bash deploy/enable-https.sh shop.example.com
#
# Before running it: the domain's DNS "A" record must already point to this
# server's public IP address, and ports 80 and 443 must be open. Let's Encrypt
# connects to the domain to prove that you control it.
set -euo pipefail
cd "$(dirname "$0")/.."

domain="${1:-}"
if [ -z "$domain" ] || [[ "$domain" == *"/"* ]] || [[ "$domain" == *":"* ]]; then
    echo "Usage: bash deploy/enable-https.sh your.domain.name   (no https://, no path)" >&2
    exit 1
fi
[ -f .env ] || { echo ".env not found. Run deploy/init-env.sh first." >&2; exit 1; }

sed -i "s|^SITE_ADDRESS=.*|SITE_ADDRESS=${domain}|" .env
sed -i "s|^COMPOSE_FILE=.*|COMPOSE_FILE=docker-compose.prod.yml:docker-compose.https.yml|" .env

echo "Starting Caddy for https://${domain} ..."
docker compose up -d
echo
echo "Caddy now requests the certificate. Follow it with:  docker compose logs -f caddy"
echo "Then open: https://${domain}/"
