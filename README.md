# MarineEdge

Vessel due diligence for grain, oilseed, vegetable-oil and dry-bulk desks working the Black Sea, the Strait of Hormuz and the Gulf. Type a name or IMO, see twelve months of voyages on one chart, every red flag with its evidence, and export a PDF report.

Mobile-first PWA (installs on a phone, works offline) + FastAPI/PostGIS backend + a rule engine with seven red-flag rules. Read `docs/BRIEF.md` for the full specification and `docs/STATUS.md` for where things stand.

## Run it in two minutes (no API key)

```bash
cd backend
pip install -e ".[dev]"                 # or: pip install fastapi "uvicorn[standard]" pyyaml jinja2 requests playwright
VVT_PROVIDER=mock uvicorn app.main:app --reload --port 8000
# in another shell
cd frontend/public && python3 -m http.server 8080
```

Or, with nothing installed but PyYAML: `cd backend && VVT_PROVIDER=mock python -m app.devserver` serves both on :8080.

Open `http://localhost:8080/?source=server` (backend) or `http://localhost:8080/` (everything in the browser). Any email signs in to the demo. Sample fleet of 40 fictional vessels with generated tracks; `HORMUZ QUEEN`, `KUBAN SPIRIT` and `LEVANT STAR` are the interesting ones.

Full stack with PostGIS: `cp .env.example .env && docker compose up --build`, then `http://localhost:8080`.

## Tests

```bash
cd backend && pytest -q          # or: python -m tests.run
```

29 tests: 19 on synthetic tracks (clean, port calls, anchorage merge, voyages, each of the seven rules with positive and negative cases) 4 on sanctions-list fixtures (OFAC, EU, UK, OpenSanctions), 4 on the service layer (cache rule, incremental fetch, user state, alert de-duplication) and 2 regression tests on the generated fleet.

## Command line

```bash
cd backend
python -m app.cli search hormuz            # candidates with IMO
python -m app.cli pull 9000036             # fetch (cached) + analyse, prints stats and flags
python -m app.cli report 9000036           # PDF
python -m app.cli first-pull 9000036 …     # acceptance checks on real IMOs once a key is in .env
```

## Switching to a real AIS provider

Put the key in `.env`, set `VVT_PROVIDER=datalastic` (or `kpler` once the adapter is filled in), restart. Nothing else changes; see `docs/PROVIDERS.md` for the trial checklist and the first-pull sanity checks.

## API

| Route | What |
|---|---|
| `GET /api/health` | provider, rules, zones |
| `GET /api/vessels/search?q=` | name, IMO or MMSI → candidates |
| `GET /api/vessels/{imo}` | particulars |
| `GET /api/vessels/{imo}/analysis` | track, port calls, voyages, flags, status (cached fetch) |
| `GET /api/regions/{blacksea,hormuz,iran,oman,uae}/vessels` | live positions in the region |
| `POST /api/vessels/{imo}/report?fmt=pdf` | PDF report |
| `GET /api/rules` · `POST /api/rules/reload` | thresholds from `config/rules.yaml` |
| `GET /api/me` · `PUT /api/me/watchlist` · `GET/PUT /api/me/notes/{imo}[/{n}]` | per-user watchlist and analyst notes |
| `GET /api/alerts` · `POST /api/jobs/refresh` | alerts raised by the refresh job; manual trigger |
| `POST/DELETE /api/push/subscribe` | Web Push subscriptions (VAPID) |
| `POST /api/zones/{id}` `{enabled}` | toggle a sensitive zone |

## Deploy

`docs/DEPLOY.md`: one VPS, Docker Compose with Caddy for HTTPS, nightly backups, sanctions cron. Set `API_TOKENS` in `.env` to protect the API.

## Layout

See `CLAUDE.md`.
