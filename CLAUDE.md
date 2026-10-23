# MarineEdge — working rules for Claude Code

- Read `docs/BRIEF.md` before any task. `docs/STATUS.md` says what is done and what is next.
- Vessels are keyed on IMO number, never on name. Name, flag and MMSI are history rows per IMO.
- All thresholds live in `config/rules.yaml`; sensitive zones in `config/zones.geojson`; ports in `config/ports.csv`. Never hard-code a threshold.
- API keys only in `.env`; never commit `.env`; never paste a key into a prompt or a test.
- Every rule and every voyage function gets unit tests on synthetic tracks (`backend/tests/synth.py`). Run `cd backend && pytest -q` (or `python -m tests.run` without pytest) before every commit.
- The provider adapter (`backend/app/providers/base.py`) is the only place that talks to an AIS vendor. The engine (`backend/app/engine/`) is pure Python with no web or database imports.
- Every paid position is cached once (`store.covered()` before `provider.get_track()`); never fetch a window twice.
- The frontend (`frontend/public/`) is plain HTML/JS by choice (allowed by the brief): it runs offline with the in-browser mock engine and against the API with `?source=server`. Keep the JSON shapes in `backend/app/service.py` identical to what `core.js` builds, so screens never need two code paths.
- Draught-based flags are indicators, not proof; keep that sentence in the UI and the report.
- Do not scrape MarineTraffic or VesselFinder websites.

## Layout

```
backend/app/engine      clean → port calls → voyages → rules → pipeline (pure)
backend/app/providers   base (Protocol), mock (generated fleet), datalastic, kpler (stub)
backend/app/store.py    MemoryStore | PostgresStore (PostGIS), fetch_log for the cache rule
backend/app/service.py  orchestration + JSON shapes
backend/app/main.py     FastAPI routes (token auth via app/auth.py when API_TOKENS is set)
backend/app/cli.py      search · pull · report · region · fleet · first-pull · sanctions-refresh
backend/app/sanctions   OFAC/EU/UK loaders → sanctions table
backend/app/reports     Jinja2 report → Playwright PDF
backend/migrations      001_init.sql (PostGIS schema)
backend/tests           synth.py + test_engine.py + test_sanctions.py (23 tests)
frontend/public         index.html, styles.css, core.js (engine+mock), base.js (MapLibre), app.js (screens), api.js, sw.js, manifest
config/                 rules.yaml, zones.geojson, ports.csv, areas.json
docs/                   BRIEF.md, STATUS.md, PROVIDERS.md, ARCHITECTURE.md, DEPLOY.md, OWNER-CHECKLIST.md
deploy/                 Caddyfile, systemd unit, backup/restore, cron
```

## Commands

- `make test` · `make lint` · `make demo` (sample PDF) · `docker compose up --build` (db + api + web on :8080)
- Dev without Docker: `cd backend && VVT_PROVIDER=mock uvicorn app.main:app --reload`, then open `frontend/public/index.html?source=server` through any static server.
