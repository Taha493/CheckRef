#!/usr/bin/env bash
# Installs or updates CiteSure on the Ubuntu 24.04 server (run as root by deploy/deploy.sh,
# after the code has been copied to /opt/citesure). Safe to run again on every update.
set -euo pipefail

DOMAIN=${DOMAIN:-citesure.duckdns.org}
APP=/opt/citesure
UV_VERSION=0.12.7
export DEBIAN_FRONTEND=noninteractive
export UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_CACHE_DIR=/opt/uv/cache

say() { printf '\n==> %s\n' "$*"; }

# ------------------------------------------------------------------ system packages
say "system packages"
apt-get update -qq
apt-get install -y -qq curl ca-certificates gnupg rsync unattended-upgrades netfilter-persistent \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation2 fonts-dejavu-core >/dev/null

if ! command -v caddy >/dev/null; then
  say "Caddy (official repository)"
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi

if [[ "$(uv --version 2>/dev/null)" != "uv $UV_VERSION"* ]]; then
  say "uv $UV_VERSION"
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

# ------------------------------------------------------------------ swap on small servers
# The 1 GB E2.1.Micro needs swap as a safety net (a check peaks at about 0.2 GB).
if (( $(awk '/MemTotal/ {print $2}' /proc/meminfo) < 3000000 )) && ! swapon --show | grep -q /swapfile; then
  say "2 GB swap (small server)"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ------------------------------------------------------------------ firewall inside the server
# Oracle's Ubuntu image rejects everything but SSH in iptables; open 80 and 443 before the
# final REJECT rule (Oracle's own security list is opened by oci_create_server.sh).
say "firewall: ports 80 and 443"
for port in 80 443; do
  if ! iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
    reject=$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" {print $1; exit}')
    iptables -I INPUT "${reject:-1}" -p tcp -m state --state NEW --dport "$port" -j ACCEPT
  fi
done
netfilter-persistent save >/dev/null

# ------------------------------------------------------------------ the app
say "app user and Python environment"
id citesure >/dev/null 2>&1 || useradd --system --home-dir /var/lib/citesure --shell /usr/sbin/nologin citesure
mkdir -p /opt/uv
cd "$APP"
uv sync --frozen --no-default-groups --python 3.12 -q
chmod -R a+rX /opt/uv "$APP"
"$APP/.venv/bin/python" -m compileall -q src >/dev/null || true
test -d "$APP/data/theses" && { echo "data/theses must never be on the server" >&2; exit 1; }

if [[ ! -f /etc/citesure.env ]]; then
  install -m 640 -g citesure "$APP/deploy/checkref.env.example" /etc/citesure.env
fi
chgrp citesure /etc/citesure.env && chmod 640 /etc/citesure.env

# ------------------------------------------------------------------ DuckDNS (optional)
# The server's public IP never changes while it exists, so entering it once on duckdns.org is
# enough. To let the server keep it updated anyway, create /etc/duckdns.env (mode 600) with
# DUCKDNS_DOMAIN=citesure and DUCKDNS_TOKEN=... and run this script again.
DUCKDNS=no
[[ -f /etc/duckdns.env ]] && chmod 600 /etc/duckdns.env && DUCKDNS=yes

# ------------------------------------------------------------------ services
say "services"
install -m 644 "$APP/deploy/citesure.service" "$APP/deploy/duckdns.service" "$APP/deploy/duckdns.timer" /etc/systemd/system/
sed "s/^DOMAIN {/$DOMAIN {/" "$APP/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl daemon-reload
if [[ $DUCKDNS == yes ]]; then
  systemctl enable --now duckdns.timer >/dev/null
  systemctl start duckdns.service || echo "warning: DuckDNS update failed (check the token in /etc/duckdns.env)"
fi
systemctl enable citesure caddy >/dev/null
systemctl restart citesure
systemctl reload-or-restart caddy

say "checking"
for _ in $(seq 30); do curl -fsS -o /dev/null http://127.0.0.1:8000/healthz && break; sleep 1; done
curl -fsS http://127.0.0.1:8000/healthz >/dev/null && echo "CiteSure is running on 127.0.0.1:8000"
systemctl is-active --quiet caddy && echo "Caddy is running: https://$DOMAIN"
