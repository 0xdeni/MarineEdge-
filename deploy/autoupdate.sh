#!/usr/bin/env bash
# Pulls new commits from GitHub and rebuilds the stack when main moved. Installed by install.sh
# when AUTO_UPDATE=1 (every 10 minutes). Remove /etc/cron.d/marineedge-update to stop.
set -euo pipefail
cd "$(dirname "$0")/.."
git fetch -q origin main
LOCAL=$(git rev-parse HEAD); REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0
echo "== $(date -u +%FT%TZ) updating $LOCAL → $REMOTE"
git reset -q --hard origin/main
docker compose --profile prod up -d --build --remove-orphans
for f in backend/migrations/*.sql; do
  docker compose exec -T db psql -q -U vvt -d vvt -f "/docker-entrypoint-initdb.d/$(basename "$f")" >/dev/null 2>&1 || true
done
docker image prune -f >/dev/null 2>&1 || true
echo "== updated"
