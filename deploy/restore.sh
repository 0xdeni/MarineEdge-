#!/usr/bin/env bash
# Restore a dump: deploy/restore.sh backups/marineedge-20261023-0300.dump
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T db pg_restore -U vvt -d vvt --clean --if-exists < "$1"
echo "restored $1"
