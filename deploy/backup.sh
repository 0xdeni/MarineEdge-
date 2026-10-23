#!/usr/bin/env bash
# Nightly PostGIS backup. Keeps 14 local dumps; copies to object storage when RCLONE_REMOTE is set
# (e.g. RCLONE_REMOTE=hetzner:marineedge-backups). Install in cron: 0 3 * * * /opt/marineedge/deploy/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
stamp=$(date -u +%Y%m%d-%H%M)
docker compose exec -T db pg_dump -U vvt -d vvt -Fc > "backups/marineedge-$stamp.dump"
ls -1t backups/marineedge-*.dump | tail -n +15 | xargs -r rm -f
if [ -n "${RCLONE_REMOTE:-}" ]; then rclone copy "backups/marineedge-$stamp.dump" "$RCLONE_REMOTE/" --quiet; fi
echo "backup ok $stamp $(du -h "backups/marineedge-$stamp.dump" | cut -f1)"
