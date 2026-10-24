# Deploy — one paste, no terminal

MarineEdge installs itself on a fresh Ubuntu 24.04 server from a cloud-init file. The whole setup can be
done from a phone in the hosting provider's app or website. After that, every setting (AIS provider key,
rules, zones, watchlist, push) is changed inside the app.

## 1. Create the server (5 minutes)

Hetzner Cloud (recommended, ~€4–8/month), DigitalOcean, Vultr or Scaleway all take a cloud-init file. **Oracle Cloud Always Free** (€0, VM.Standard.A1.Flex **2 OCPU / 12 GB** since June 2026, Ubuntu 24.04) works with the same paste — put it under Advanced › Cloud-init, and afterwards add ingress rules for TCP 80 and 443 to the instance's VCN security list; the installer opens the same ports in the image's own firewall. See `docs/FREE-STACK.md` for the trade-offs.

1. Open `deploy/cloud-init.yaml` on GitHub, tap Raw, select all, copy.
2. In the provider's "create server" screen pick **Ubuntu 24.04**, the smallest 2 vCPU / 4 GB size, any EU location.
3. Find the **cloud-init / user data** field, paste the file, and edit the lines inside it:
   - `ADMIN_TOKEN=` → a long passphrase of your choice (this is your sign-in password)
   - `DOMAIN=` → leave empty for now (you get `https://<ip>.sslip.io` with a real certificate), or your own domain once its A record points at the server
   - `GITHUB_TOKEN=` → only while the repository is private: a fine-grained personal access token for this one repository with Contents: Read-only. A public repository needs nothing here.
4. Create the server. Note its IPv4 address.

Five minutes later: `https://<ip with dashes>.sslip.io` (example: IP 95.217.12.34 → `https://95-217-12-34.sslip.io`). Sign in with any email and the ADMIN_TOKEN.

The server pulls every new commit from GitHub within 10 minutes (`AUTO_UPDATE=1`), so fixes arrive without touching it. Set `AUTO_UPDATE=0` in the file later when you want releases to be deliberate.

**The server is the CI.** `deploy/autoupdate.sh` does not blindly deploy: it builds the new image while the old one keeps serving, runs the full test suite inside the new image, and only then switches over, applies migrations and waits for `/api/health`. When the database is up it also applies the new migrations to a scratch database (`vvt_test`) and runs the PostGIS store test against it, so a broken migration or query never reaches the live data. A failed build, a failed migration, a red test or an unhealthy API puts the previous commit back and the old containers stay up; that commit is not retried until a newer one lands. The verdict (commit, test summary, time, failure detail) is written to `state/update.json` and shown in the app under **Profile › AIS provider › Server updates** — green/red on the phone, no GitHub Actions needed.

**Free trials** take the same file: AWS EC2 › Launch instance › Advanced details › **User data** (Free plan, t4g.small, 30 GiB gp3, allow HTTP + HTTPS); Google Compute Engine › Advanced › Metadata › key **`user-data`** (allow HTTP + HTTPS). Click paths in `docs/FREE-STACK.md`.

**Small machines (1–2 GB RAM)** are handled by the installer: it adds a 2 GB swap file, runs one API worker and keeps Postgres at its defaults; on bigger machines Postgres gets a quarter of the RAM as cache. Arm machines get the multi-arch PostGIS image. All of it is written to `.env` (`API_WORKERS`, `PG_SHARED_BUFFERS`, `PG_EFFECTIVE_CACHE`, `POSTGIS_IMAGE`); a value set by hand there wins.

## 2. Inside the app (phone)

- **Add to Home Screen** (Safari share sheet) so it runs full-screen and can receive push notifications (iOS 16.4+).
- **Profile › AIS provider**: free path — tap **aisstream.io (free)**, paste the key from aisstream.io, "Save key and switch"; the **Recorded AIS** box starts counting within a minute. Paid path — tap Datalastic, paste the key, "Save key and switch", "Test connection", then type the IMOs and "Run first pull". Optional **Cross-check token** (Global Fishing Watch) on the same screen.
- **Profile › Notifications**: "Enable push notifications on this device".
- **Watch** a vessel: the refresh job (every 30 minutes) re-analyses watched ships and pushes new High flags.

## 3. What runs on the server

`install.sh` installs Docker, clones the repo to `/opt/marineedge`, writes `.env` (random database password, your admin token, push keys), and starts five containers: PostGIS, the API, the **recorder** (one websocket to aisstream.io, idle until a key is pasted in the app), the web app, and Caddy (automatic HTTPS). Cron runs the nightly backup (03:00), the sanctions refresh (04:30), the watchlist refresh (every 30 min), the auto-update (every 10 min) and the daily `prune-live` job (thins recorded positions older than 30 days to one per 15 minutes, deletes them after 14 months — all three numbers in `rules.yaml › live`). Logs: `/var/log/marineedge-*.log`; recorder logs with `docker compose logs -f recorder`.

## 4. With a terminal (optional)

```bash
ssh root@<ip>
cat /opt/marineedge/.env                               # tokens, keys
cd /opt/marineedge && docker compose logs -f api       # live logs
docker compose exec api python -m app.cli first-pull 9000036
deploy/backup.sh                                       # manual backup; restore with deploy/restore.sh <file>
```

Add a second user: append `,ana:<token>` (analyst) or `,ana:<token>:admin` to `API_TOKENS` in `.env`, then `docker compose restart api`. Company SSO (Google Workspace / Microsoft Entra) goes in front of Caddy with oauth2-proxy when you are ready; tokens remain for the CLI and cron.

## 5. Backups

`deploy/backup.sh` keeps 14 nightly `pg_dump` files in `/opt/marineedge/backups/` and copies them off-site when `RCLONE_REMOTE` is set in `.env` (any S3-compatible bucket). Test one restore before trusting it.

## 6. Costs

`fetch_log` has one row per paid fetch with its credit estimate; the admin screen shows credits used since the last restart:
```sql
SELECT provider, date_trunc('month', fetched_at) m, count(*) fetches, sum(credits) credits FROM fetch_log GROUP BY 1,2 ORDER BY 2 DESC;
```
