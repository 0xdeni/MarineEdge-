# MarineEdge — working rules for Claude Code

- Read `docs/BRIEF.md` before any task. `docs/STATUS.md` says what is done and what is next.
- Vessels are keyed on IMO number, never on name. Name, flag and MMSI are history rows per IMO.
- All thresholds live in `config/rules.yaml`; sensitive zones in `config/zones.geojson`; ports in `config/ports.csv`. Never hard-code a threshold.
- API keys only in `.env`; never commit `.env`; never paste a key into a prompt or a test.
- Every rule and every voyage function gets unit tests on synthetic tracks (`backend/tests/synth.py`). Run `cd backend && pytest -q` (or `python -m tests.run` without pytest) before every commit.
- The provider adapter (`backend/app/providers/base.py`) is the only place that talks to an AIS vendor. The engine (`backend/app/engine/`) is pure Python with no web or database imports.
- Every paid position is cached once (`store.covered()` before `provider.get_track()`); never fetch a window twice.
- The owner operates from an iPhone: anything an admin must change goes into the app (Profile › AIS provider etc.), never into a file on the server.
- The frontend (`frontend/public/`) is plain HTML/JS by choice (allowed by the brief): it runs offline with the in-browser mock engine and against the API with `?source=server`. Keep the JSON shapes in `backend/app/service.py` identical to what `core.js` builds, so screens never need two code paths.
- Draught-based flags are indicators, not proof; keep that sentence in the UI and the report.
- On the free feed (aisstream) gaps where no receiver can hear are Info, not flags: the gap rule takes `coverage(lon, lat)` from the provider; keep that honest in UI and report. GFW data is non-commercial-licensed: cross-check only, never a primary source.
- Do not scrape MarineTraffic or VesselFinder websites.

## Layout

```
backend/app/engine      clean → port calls → voyages → rules → pipeline (pure)
backend/app/providers   base (Protocol), mock (generated fleet), aisstream (free live feed recorded by app/recorder.py → OwnAISProvider), datalastic, kpler (stub), gfw (free cross-check, non-commercial)
backend/app/store.py    MemoryStore | PostgresStore (PostGIS), fetch_log for the cache rule
backend/app/service.py  orchestration + JSON shapes
backend/app/main.py     FastAPI routes (token auth via app/auth.py when API_TOKENS is set)
backend/app/cli.py      search · pull · report · region · fleet · first-pull · sanctions-refresh
backend/app/jobs.py     refresh (watchlist → alerts → push) · sanctions · region · prune-live (tiered retention of the recorded feed); app/push.py (VAPID); app/devserver.py (stdlib dev server)
backend/app/settings_store.py  provider + key chosen from the app, stored on the data volume; app/auth.py roles (name:token[:admin])
backend/app/sanctions   OFAC/EU/UK loaders → sanctions table
backend/app/reports     Jinja2 report → Playwright PDF
backend/migrations      001_init.sql (PostGIS schema) · 002_alerts_push.sql · 003_live_ais.sql (ais_live, mmsi_map) · 004_slim_live.sql (idempotent; migrations are append-only, re-applied on every update)
backend/tests           synth.py + test_engine.py + test_sanctions.py + test_service.py + test_fleet.py + test_aisstream.py + test_pgstore.py (39 tests; the PostGIS one runs when DATABASE_URL is set — the server's auto-updater does, on a scratch DB)
frontend/public         index.html, styles.css, core.js (engine+mock), base.js (MapLibre), app.js (screens), api.js, sw.js, manifest
config/                 rules.yaml, zones.geojson, ports.csv, areas.json
docs/                   BRIEF.md, STATUS.md, PROVIDERS.md, FREE-STACK.md, ARCHITECTURE.md, DEPLOY.md, OWNER-CHECKLIST.md
deploy/                 cloud-init.yaml + install.sh (one-paste server), autoupdate.sh, Caddyfile ({$DOMAIN}), systemd unit, backup/restore, cron
```

## Commands

- `make test` · `make lint` · `make demo` (sample PDF) · `docker compose up --build` (db + api + recorder + web on :8080)
- Dev without Docker: `cd backend && VVT_PROVIDER=mock uvicorn app.main:app --reload`, then open `frontend/public/index.html?source=server` through any static server; or `python -m app.devserver` (stdlib only) which serves both on :8080.
