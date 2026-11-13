#!/usr/bin/env bash
# Copies CiteSure from this laptop to the server and installs or updates it there.
#   deploy/deploy.sh                       # to citesure.duckdns.org
#   HOST=ubuntu@1.2.3.4 deploy/deploy.sh   # by IP, before DNS is set up
# The private sample theses (data/theses) and zip files (design drafts may hold report data)
# are never copied.
set -euo pipefail

HOST=${HOST:-ubuntu@citesure.duckdns.org}
KEY=${KEY:-$HOME/.ssh/citesure}
DOMAIN=${DOMAIN:-citesure.duckdns.org}
cd "$(dirname "$0")/.."

ssh_() { ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$@"; }

echo "==> copying the code to $HOST"
rsync -az --delete -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  --exclude .git/ --exclude .venv/ --exclude data/theses/ --exclude tests/ \
  --exclude __pycache__/ --exclude .pytest_cache/ --exclude .ruff_cache/ \
  --exclude jobs/ --exclude .env --exclude '*.gguf' --exclude '*.zip' \
  ./ "$HOST:citesure-src/"

echo "==> installing on the server"
ssh_ -t "$HOST" "sudo rsync -a --delete ~/citesure-src/ /opt/citesure/ && sudo DOMAIN=$DOMAIN bash /opt/citesure/deploy/setup_server.sh"
