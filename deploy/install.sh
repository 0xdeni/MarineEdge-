#!/usr/bin/env bash
# MarineEdge one-shot server install. Runs from cloud-init (deploy/cloud-init.yaml) or by hand:
#   curl -fsSL https://raw.githubusercontent.com/0xdeni/MarineEdge-/main/deploy/install.sh | sudo bash
# Reads /opt/marineedge-setup.env if present (ADMIN_TOKEN, DOMAIN, AUTO_UPDATE, GITHUB_TOKEN, PROVIDER, DATALASTIC_API_KEY).
# GITHUB_TOKEN (fine-grained, Contents: read) is only needed while the repository is private; it is stored in
# the clone's remote URL so the auto-updater can fetch.
# Idempotent: re-running updates the code and restarts the stack without touching .env.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
REPO="${REPO:-https://github.com/0xdeni/MarineEdge-.git}"
DIR="${DIR:-/opt/marineedge}"
SETUP_ENV="${SETUP_ENV:-/opt/marineedge-setup.env}"
LOG=/var/log/marineedge-install.log
exec > >(tee -a "$LOG") 2>&1
echo "== MarineEdge install $(date -u +%FT%TZ)"

# 1. Settings from the cloud-init file (if any)
ADMIN_TOKEN=""; DOMAIN=""; AUTO_UPDATE="1"; GITHUB_TOKEN=""; PROVIDER="mock"; DATALASTIC_API_KEY=""
if [ -f "$SETUP_ENV" ]; then
  # shellcheck disable=SC1090
  set -a; . "$SETUP_ENV"; set +a
fi
if [ -n "$GITHUB_TOKEN" ]; then
  REPO="https://x-access-token:${GITHUB_TOKEN}@github.com/0xdeni/MarineEdge-.git"
fi

# 2. Docker
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git gnupg >/dev/null
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null
  systemctl enable --now docker
fi
command -v git >/dev/null 2>&1 || { apt-get update -qq; apt-get install -y -qq git >/dev/null; }

# 2b. Oracle Cloud "Always Free" Ubuntu images ship iptables rules that REJECT everything but SSH.
#     Open 80/443 there (no-op on Hetzner/DigitalOcean images, which have no such rule).
if command -v iptables >/dev/null 2>&1 && iptables -S INPUT 2>/dev/null | grep -q -- '-j REJECT'; then
  for port in 80 443; do
    iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null || iptables -I INPUT 5 -p tcp --dport "$port" -j ACCEPT
  done
  command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save >/dev/null 2>&1 || true
  echo "== opened ports 80/443 in iptables (Oracle image); also allow them in the VCN security list"
fi

# 3. Code
if [ -d "$DIR/.git" ]; then
  [ -n "$GITHUB_TOKEN" ] && git -C "$DIR" remote set-url origin "$REPO"
  git -C "$DIR" pull -q --ff-only
else
  if ! git clone -q "$REPO" "$DIR" 2>/tmp/clone.err; then
    sed "s#${GITHUB_TOKEN:-__none__}#***#g" /tmp/clone.err
    echo "== clone failed. If the GitHub repository is private, put a fine-grained token (Contents: Read-only) in GITHUB_TOKEN= in $SETUP_ENV and re-run; or make the repository public."
    exit 1
  fi
fi
cd "$DIR"

# 4. Domain: given, or <ip>.sslip.io (works without buying a domain; Let's Encrypt issues certificates for it)
if [ -z "$DOMAIN" ]; then
  IP=$(curl -fsS https://api.ipify.org || curl -fsS https://ifconfig.me || hostname -I | awk '{print $1}')
  DOMAIN="$(echo "$IP" | tr . -).sslip.io"
fi

# 4b. This machine: CPU architecture and memory decide a few settings (written to .env in step 5b)
#     Arm (Oracle Always Free, Raspberry Pi): the official PostGIS image is amd64 only, use a multi-arch twin.
case "$(uname -m)" in
  aarch64|arm64) POSTGIS_IMAGE="${POSTGIS_IMAGE:-imresamu/postgis:16-3.4-bookworm}"; echo "== arm64 detected: PostGIS image ${POSTGIS_IMAGE}" ;;
  *) POSTGIS_IMAGE="${POSTGIS_IMAGE:-postgis/postgis:16-3.4}" ;;
esac
#     Memory: 1–2 GB machines (Google e2-micro, Azure B1s, AWS t4g.small, Oracle AMD micro) get a swap file so
#     image builds and PDF rendering fit, one API worker, and Postgres defaults; bigger ones give Postgres a
#     quarter of the RAM for its cache (the standard rule), capped at 4 GB.
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 3000 ] && [ -z "$(swapon --show --noheadings 2>/dev/null)" ]; then
  FREE_GB=$(df --output=avail -BG / | tail -n 1 | tr -dc '0-9')
  if [ "${FREE_GB:-0}" -ge 8 ]; then
    if { fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none; } \
       && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile; then
      grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
      echo "== ${MEM_MB} MB RAM: added a 2 GB swap file"
    else
      rm -f /swapfile; echo "== ${MEM_MB} MB RAM: could not add swap; continuing without it"
    fi
  fi
fi
if [ "$MEM_MB" -lt 2500 ]; then
  API_WORKERS=1; PG_SHARED_BUFFERS=128MB; PG_EFFECTIVE_CACHE=512MB
else
  API_WORKERS=2; SB=$(( MEM_MB / 4 )); [ "$SB" -gt 4096 ] && SB=4096
  PG_SHARED_BUFFERS="${SB}MB"; PG_EFFECTIVE_CACHE="$(( MEM_MB / 2 ))MB"
fi
echo "== ${MEM_MB} MB RAM: ${API_WORKERS} API worker(s), Postgres cache ${PG_SHARED_BUFFERS}"

# 5. .env (created once; later runs keep it)
if [ ! -f .env ]; then
  [ -n "$ADMIN_TOKEN" ] || ADMIN_TOKEN=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 28)
  DBPASS=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)
  cat > .env <<EOF
# generated by deploy/install.sh on $(date -u +%F)
VVT_PROVIDER=${PROVIDER}
DATALASTIC_API_KEY=${DATALASTIC_API_KEY}
KPLER_API_KEY=
DATABASE_URL=postgresql://vvt:${DBPASS}@db:5432/vvt
POSTGRES_PASSWORD=${DBPASS}
API_TOKENS=admin:${ADMIN_TOKEN}:admin
CORS_ORIGINS=https://${DOMAIN}
DOMAIN=${DOMAIN}
LOG_LEVEL=INFO
VVT_REPORT_DIR=/data/reports
VVT_DATA_DIR=/data
PUSH_MIN_SEVERITY=high
UK_SANCTIONS_CSV_URL=
# AIS keys are normally pasted in the app (Profile › AIS provider); these are only fallbacks.
AISSTREAM_API_KEY=
GFW_API_TOKEN=
RCLONE_REMOTE=
OPENSANCTIONS=0
EOF
  chmod 600 .env
  echo "== .env written. ADMIN TOKEN: ${ADMIN_TOKEN}  (also in ${DIR}/.env)"
fi
# 5b. Machine-dependent settings: added when missing or empty, also on re-runs (an existing value is kept,
#     so a value set by hand wins).
ensure_env() { grep -q "^$1=." .env || { sed -i "/^$1=/d" .env; echo "$1=$2" >> .env; }; }
ensure_env POSTGIS_IMAGE "$POSTGIS_IMAGE"
ensure_env API_WORKERS "$API_WORKERS"
ensure_env PG_SHARED_BUFFERS "$PG_SHARED_BUFFERS"
ensure_env PG_EFFECTIVE_CACHE "$PG_EFFECTIVE_CACHE"
# shellcheck disable=SC1091
set -a; . ./.env; set +a

# 6. Build and start (db + api + web + caddy)
docker compose --profile prod pull -q db caddy 2>/dev/null || true
docker compose --profile prod up -d --build --remove-orphans
sleep 8
# apply migrations that initdb did not run (initdb only runs on first database creation)
for f in backend/migrations/*.sql; do
  docker compose exec -T db psql -q -U vvt -d vvt -f "/docker-entrypoint-initdb.d/$(basename "$f")" >/dev/null 2>&1 || true
done

# 7. Web push keys, once (needs pywebpush inside the api image)
if ! grep -q '^VAPID_PUBLIC_KEY=.\+' .env; then
  if KEYS=$(docker compose exec -T api python -m app.push keygen 2>/dev/null) && echo "$KEYS" | grep -q VAPID_PUBLIC_KEY; then
    sed -i '/^VAPID_/d' .env
    echo "$KEYS" >> .env
    docker compose --profile prod up -d api
    echo "== push keys generated"
  else
    echo "== push keys skipped (pywebpush missing in image); alerts still show in the app"
  fi
fi

# 8. Cron: backups, sanctions refresh, watchlist refresh, auto-update
install -m 0644 deploy/cron.d-marineedge /etc/cron.d/marineedge
if [ "${AUTO_UPDATE}" = "1" ]; then
  echo "*/10 * * * * root ${DIR}/deploy/autoupdate.sh >> /var/log/marineedge-update.log 2>&1" > /etc/cron.d/marineedge-update
fi
install -m 0644 deploy/marineedge.service /etc/systemd/system/marineedge.service
systemctl daemon-reload && systemctl enable marineedge >/dev/null 2>&1 || true

# 9. Health
sleep 5
if curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
  echo "== API healthy"
else
  echo "== API not answering yet; check: docker compose logs api"
fi
echo "== MarineEdge is at https://${DOMAIN}  (certificate appears within a minute of DNS/IP being reachable)"
echo "== Sign in with any email and the admin token. Then Profile › AIS provider: aisstream.io (free) or Datalastic."
