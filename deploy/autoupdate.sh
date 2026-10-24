#!/usr/bin/env bash
# The server is the CI. Every 10 minutes (cron, installed by install.sh when AUTO_UPDATE=1):
#   1. fetch main; stop if nothing new, or if the newest commit already failed here
#   2. build the new api image WITHOUT touching the running containers
#   3. run the whole test suite inside that image (in-memory store, no credits, no DB writes)
#   4. only when green: switch the stack over, apply migrations, wait for /api/health
#   5. if anything fails: put the previous commit back, keep the old containers running
# The verdict is written to state/update.json, which the app shows under Profile › Server › Updates
# updates, so the owner sees green/red on the phone without GitHub Actions. Remove
# /etc/cron.d/marineedge-update to stop auto-updating.
set -uo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
[ -f .env ] && { set -a; . ./.env; set +a; }
mkdir -p state
STATE=state/update.json
API_URL="${API_URL:-http://127.0.0.1:8000/api/health}"

now() { date -u +%FT%TZ; }
write_state() {   # result, tests, detail
  python3 - "$1" "$2" "$3" "$LOCAL" "$REMOTE" <<'PY' > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
import json, sys, datetime
res, tests, detail, prev, new = sys.argv[1:6]
print(json.dumps({"result": res, "tests": tests, "detail": detail[:600], "previous": prev[:12], "commit": new[:12],
                  "checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}))
PY
}

git fetch -q origin main || { echo "== $(now) fetch failed"; exit 0; }
LOCAL=$(git rev-parse HEAD); REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0
if [ -f "$STATE" ] && python3 -c "import json,sys; d=json.load(open('$STATE')); sys.exit(0 if d.get('commit')=='${REMOTE:0:12}' and d.get('result')!='ok' else 1)"; then
  exit 0   # this commit already failed here; wait for the next one
fi
echo "== $(now) candidate $LOCAL → $REMOTE"
git reset -q --hard origin/main

# 2. build the new images (the running containers keep serving the old ones); a broken web image stops the update too
if ! BUILD=$(docker compose build api web 2>&1 | tail -n 30); then
  echo "$BUILD"; echo "== build failed, staying on $LOCAL"
  write_state "build_failed" "" "$BUILD"; git reset -q --hard "$LOCAL"; exit 0
fi

# 3. the test suite inside the new image. When the database is up, the new migrations are applied to a scratch
#    database (vvt_test) and the PostGIS store test runs against it too; the live database is never touched.
TEST_DB="-e DATABASE_URL="
if docker compose exec -T db pg_isready -q -U vvt >/dev/null 2>&1; then
  docker compose exec -T db psql -q -U vvt -d postgres -c "DROP DATABASE IF EXISTS vvt_test" -c "CREATE DATABASE vvt_test" >/dev/null 2>&1
  MIG_ERR=""
  for f in backend/migrations/*.sql; do
    if ! OUT=$(docker compose exec -T db psql -q -v ON_ERROR_STOP=1 -U vvt -d vvt_test -f "/docker-entrypoint-initdb.d/$(basename "$f")" 2>&1); then
      MIG_ERR="$(basename "$f"): $(echo "$OUT" | grep -m 3 -E 'ERROR|FATAL')"; break
    fi
  done
  if [ -n "$MIG_ERR" ]; then
    echo "$MIG_ERR"; echo "== migration failed on a scratch database, staying on $LOCAL"
    write_state "migration_failed" "" "$MIG_ERR"; git reset -q --hard "$LOCAL"; exit 0
  fi
  TEST_DB="-e DATABASE_URL=postgresql://vvt:${POSTGRES_PASSWORD:-vvt}@db:5432/vvt_test"
fi
# shellcheck disable=SC2086
TESTS=$(docker compose run --rm --no-deps -T $TEST_DB -e VVT_DATA_DIR=/tmp api python -m tests.run 2>&1 | tail -n 40)
SUMMARY=$(echo "$TESTS" | grep -E '^[0-9]+ passed' | tail -n 1)
if ! echo "$SUMMARY" | grep -qE 'passed, 0 failed'; then
  echo "$TESTS"; echo "== tests failed, staying on $LOCAL"
  write_state "tests_failed" "${SUMMARY:-no summary}" "$(echo "$TESTS" | grep -E 'FAIL|Error|assert' | head -n 8)"; git reset -q --hard "$LOCAL"; exit 0
fi
echo "== tests: $SUMMARY"

# 4. switch over
docker compose --profile prod up -d --build --remove-orphans
for f in backend/migrations/*.sql; do
  docker compose exec -T db psql -q -U vvt -d vvt -f "/docker-entrypoint-initdb.d/$(basename "$f")" >/dev/null 2>&1 || true
done
HEALTHY=0
for _ in $(seq 1 30); do
  if curl -fsS "$API_URL" >/dev/null 2>&1; then HEALTHY=1; break; fi
  sleep 3
done
if [ "$HEALTHY" = "1" ]; then
  write_state "ok" "$SUMMARY" "healthy $(now)"
  # scheduled jobs travel with the code: new entries (e.g. the background checks) reach the server with the update
  if [ -w /etc/cron.d ] && ! cmp -s deploy/cron.d-marineedge /etc/cron.d/marineedge; then
    install -m 0644 deploy/cron.d-marineedge /etc/cron.d/marineedge && echo "== cron entries updated"
  fi
  docker image prune -f >/dev/null 2>&1 || true
  echo "== updated to $REMOTE"
  exit 0
fi

# 5. roll back
echo "== API unhealthy after update, rolling back to $LOCAL"
write_state "unhealthy" "$SUMMARY" "$(docker compose logs --tail 20 api 2>&1 | tail -n 20)"
git reset -q --hard "$LOCAL"
docker compose --profile prod up -d --build --remove-orphans
