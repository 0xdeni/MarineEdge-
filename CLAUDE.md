# MarineEdge — working rules for Claude Code

- Read `docs/BRIEF.md` before any task. `docs/STATUS.md` says what is done and what is next.
- Vessels are keyed on IMO number, never on name. Name, flag and MMSI are history rows per IMO.
- All thresholds live in `config/rules.yaml`; sensitive zones in `config/zones.geojson`; ports in `config/ports.csv`. Never hard-code a threshold.
- API keys only in `.env`; never commit `.env`; never paste a key into a prompt or a test.
- Every rule and every voyage function gets unit tests on synthetic tracks (`backend/tests/synth.py`). Run `cd backend && pytest -q` (or `python -m tests.run` without pytest) before every commit.
- The provider adapter (`backend/app/providers/base.py`) is the only place that talks to an AIS vendor. The engine (`backend/app/engine/`) is pure Python with no web or database imports.
- Every paid position is cached once (`store.covered()` before `provider.get_track()`); never fetch a window twice.
- The owner operates from an iPhone: anything an admin must change goes into the app (Profile › Data sources, Team, Email, Rules…), never into a file on the server.
- The frontend (`frontend/public/`) is plain HTML/JS by choice (allowed by the brief), no build step: `js/ui.js, api.js, map.js, onboarding.js, screens.js, profile.js, app.js`. Everything on screen comes from the API; the app holds no demo data. The JSON shapes are defined in `backend/app/service.py` and `app/routes.py`.
- Nothing mock or fake on a server: the generated fleet (`providers/mock.py`) is for tests and `make dev` only (`VVT_ALLOW_MOCK=1`); never add placeholder data, fake sign-in options or sample text to the app.
- Every API route lives in `backend/app/routes.py` (shared by FastAPI and `app/devserver.py`); verdict and finding wording only in `backend/app/verdict.py`.
- No third-party scripts, fonts or map services: MapLibre, fonts and Natural Earth are vendored; nginx sends a strict CSP (no inline scripts).
- Draught-based flags are indicators, not proof; keep that sentence in the UI and the report.
- On the free feed (aisstream) gaps where no receiver can hear are Info, not flags: the gap rule takes `coverage(lon, lat)` from the provider; keep that honest in UI and report. GFW data is non-commercial-licensed: cross-check only, never a primary source.
- Do not scrape MarineTraffic or VesselFinder websites.

## Layout

```
backend/app/engine      clean → port calls → voyages → rules → pipeline (pure)
backend/app/providers   base (Protocol), mock (generated fleet), aisstream (free live feed recorded by app/recorder.py → OwnAISProvider), datalastic, kpler (stub), gfw (free cross-check, non-commercial)
backend/app/store.py    MemoryStore | PostgresStore (PostGIS), fetch_log for the cache rule
backend/app/service.py  orchestration + JSON shapes
backend/app/routes.py   every /api route (auth levels, CSRF); app/main.py (FastAPI) and app/devserver.py dispatch to it
backend/app/accounts.py users, sessions, invites, resets (scrypt); app/auth.py resolves cookie or API token; app/mailer.py SMTP set in the app
backend/app/verdict.py  verdict sentence, figures and per-finding stories (fixed rules)
backend/app/cli.py      search · pull · report · region · fleet · first-pull · sanctions-refresh
backend/app/jobs.py     refresh (watchlist → alerts → push) · sweep (check ships in range) · sanctions · region · prune-live (tiered retention of the recorded feed); app/push.py (VAPID); app/devserver.py (stdlib dev server)
backend/app/settings_store.py  provider + key chosen from the app, stored on the data volume; app/auth.py roles (name:token[:admin])
backend/app/sanctions   OFAC/EU/UK loaders → sanctions table
backend/app/reports     Jinja2 report → Playwright PDF
backend/migrations      001_init.sql (PostGIS schema) · 002_alerts_push.sql · 003_live_ais.sql (ais_live, mmsi_map) · 004_slim_live.sql · 005_accounts.sql · 006_purge_demo.sql (all idempotent; append-only, re-applied on every update)
backend/tests           synth.py + test_engine, test_sanctions, test_service, test_fleet, test_aisstream, test_accounts, test_routes, test_report_push, test_pgstore (65 tests; the PostGIS ones run when DATABASE_URL is set — the server's auto-updater does, on a scratch DB)
frontend/public         index.html, css/app.css, js/*.js, sw.js, manifest, vendor/maplibre, fonts/ (Noto Sans pbf), geo/ne.json (Natural Earth), img/, icons/
config/                 rules.yaml, zones.geojson, ports.csv, areas.json
docs/                   BRIEF.md, STATUS.md, PROVIDERS.md, FREE-STACK.md, ARCHITECTURE.md, DEPLOY.md, OWNER-CHECKLIST.md
deploy/                 cloud-init.yaml + install.sh (one-paste server), autoupdate.sh (builds api+web, tests, switches, refreshes cron), Caddyfile ({$DOMAIN}), systemd unit, backup/restore, cron
scripts/                ne_extract.py (Natural Earth → geo/ne.json), import_wpi.py, refresh_sanctions.py
```

## Commands

- `make dev` (app + API + demo fleet on :8080; first account's server admin password: `dev-setup-code`) · `make test` · `make lint` · `make demo` (sample PDF) · `docker compose up --build` (db + api + recorder + web on :8080)
- Dev without Docker: `cd backend && API_TOKENS=admin:dev-setup-code:admin python -m app.devserver` (stdlib only) serves the app and the API on :8080 with the demo fleet.
