# MarineEdge

Ship due diligence for grain, oilseed, vegetable-oil and dry-bulk desks working the Black Sea, the Strait of Hormuz and the Gulf. Type a name, a former name, an IMO or MMSI number and see the ship's last twelve months: every voyage on one map, every red flag with its evidence, a one-sentence verdict, team notes, and a PDF report.

An iPhone-first web app (installs to the Home Screen, works offline for ships you opened) on a FastAPI/PostGIS backend with a rule engine of seven red-flag rules. It records the free aisstream.io AIS feed on your own server; history for a specific ship can be bought once from Datalastic. Read `docs/BRIEF.md` for the specification and `docs/STATUS.md` for where things stand.

## Run it on a laptop (no key, no database)

```bash
make dev            # = cd backend && API_TOKENS=admin:dev-setup-code:admin python3 -m app.devserver
```

Open `http://localhost:8080`, tap **Get started › Create account** and use `dev-setup-code` as the server admin password. The development server shows a generated demo fleet (`AZOV CRESCENT`, `LEVANT STAR`, `SILVER REACH`, `DOBRUJA STAR` are the interesting ones) — a real server never does. It needs only Python and PyYAML; the PDF needs Playwright's Chromium.

Full stack with PostGIS: `cp .env.example .env`, set `API_TOKENS` (and `VVT_PROVIDER=mock` + `VVT_ALLOW_MOCK=1` for the demo fleet), then `docker compose up --build` and open `http://localhost:8080`.

## Tests

```bash
make test           # pytest -q, or python -m tests.run without pytest
```

65 tests: the seven rules and the voyage functions on synthetic tracks, sanctions-list parsers (OFAC, EU, UK FCDO, OpenSanctions), the service (fetch-once cache, incremental fetch, alerts), accounts (setup, invites, rate limits, resets, sessions), the HTTP router (auth levels, CSRF, notes permissions, no demo fleet on a server), the verdict wording, the report and notifications, the recorded feed, and PostgresStore (fully against PostGIS when `DATABASE_URL` is set).

## Command line

```bash
cd backend
python -m app.cli search silver            # candidates with IMO
python -m app.cli pull 9000013             # fetch (cached) + analyse, prints stats and flags
python -m app.cli report 9000013           # PDF
python -m app.cli first-pull 9321483 …     # acceptance checks on real IMOs once a Datalastic key is set
```

## API (all under `/api`, JSON; the app uses a session cookie, scripts a `Bearer` API token)

| Route | What |
|---|---|
| `GET /health` · `GET /auth/state` | liveness; whether the server needs its first account |
| `POST /auth/signup · /login · /logout · /forgot · /reset` | accounts |
| `GET/PATCH /me` · `POST /me/password` · `GET /me/sessions` | profile, preferences, devices |
| `GET /regions/{id}/overview` · `GET /regions/{id}/vessels` | the region now: counts, highest risk, live positions |
| `GET /vessels/search?q=` | name, former name, IMO or MMSI |
| `GET /vessels/{imo}/analysis` | track, voyages, findings with stories, verdict, status |
| `GET /vessels/{imo}/report.pdf` | the PDF report |
| `GET/POST /vessels/{imo}/notes` · `PATCH/DELETE /notes/{id}` | team notes |
| `GET /alerts` · `PUT /me/watchlist` · `POST/DELETE /push/subscribe` | watching and alerts |
| `/admin/…` | data sources, team and invites, email, rules, zones, maps, jobs (admins) |

## Deploy

One paste: `deploy/cloud-init.yaml` into an Ubuntu server's user-data field (AWS, Google Cloud, Oracle, Hetzner…). It installs Docker, PostGIS, the API, the recorder, the web app and Caddy with HTTPS, and updates itself from GitHub behind the test suite. Everything else is done inside the app. Details: `docs/DEPLOY.md`.

## Layout

See `CLAUDE.md`. Map data: Natural Earth (public domain), OpenStreetMap contributors (ODbL) via Protomaps; map engine MapLibre GL JS (BSD-3-Clause); map fonts Noto Sans (OFL).
