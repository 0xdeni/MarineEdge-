# Deploy — one small server, 30 minutes

Target: a 2 vCPU / 4 GB VPS (Hetzner CX22 or similar) with Ubuntu 24.04, Docker and a domain.

## 1. Server
```bash
apt update && apt install -y docker.io docker-compose-v2 git
git clone https://github.com/0xdeni/MarineEdge-.git /opt/marineedge && cd /opt/marineedge
cp .env.example .env            # fill in: VVT_PROVIDER, the provider key, API_TOKENS, UK_SANCTIONS_CSV_URL
sed -i 's/tracker.example.com/YOUR.DOMAIN/' deploy/Caddyfile
```
DNS: an A record for YOUR.DOMAIN pointing at the server. Caddy fetches the certificate on first start.

## 2. Start
```bash
docker compose --profile prod up -d --build
docker compose exec api python -m app.cli first-pull <IMO> <IMO>     # acceptance checks on real ships
cp deploy/marineedge.service /etc/systemd/system/ && systemctl enable marineedge
cp deploy/cron.d-marineedge /etc/cron.d/marineedge                   # 03:00 backup, 04:30 sanctions refresh
```
Open https://YOUR.DOMAIN on the phone, "Add to Home Screen", sign in with your email and the API token from `.env`.

## 3. Backups
`deploy/backup.sh` keeps 14 nightly `pg_dump` files in `backups/` and copies them off-site when `RCLONE_REMOTE` is set (any S3-compatible bucket). Restore with `deploy/restore.sh <file>`. Test a restore once before trusting it.

## 4. Access control
- `API_TOKENS` protects every `/api/*` route (Bearer token or `X-API-Key`); `/api/health` stays open.
- For company SSO, put oauth2-proxy (Google Workspace or Microsoft Entra) in front of Caddy's `web` handler and keep tokens for the CLI and cron. The frontend only needs the `Authorization` header to reach the API.
- Never commit `.env`. Rotate a token by editing `.env` and `docker compose restart api`.

## 5. Updating
```bash
cd /opt/marineedge && git pull && docker compose --profile prod up -d --build
```
Bump `VERSION` in `frontend/public/sw.js` with every frontend change so installed phones refresh their cache.

## 6. Watching costs
`fetch_log` in Postgres has one row per paid fetch with its credit estimate:
```sql
SELECT provider, date_trunc('month', fetched_at) m, count(*) fetches, sum(credits) credits FROM fetch_log GROUP BY 1,2 ORDER BY 2 DESC;
```
