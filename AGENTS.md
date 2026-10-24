# AGENTS.md — MarineEdge

Instructions for AI coding agents working in this repository (Claude Code imports this file from `CLAUDE.md`). People should start with `README.md`.

## What this is

MarineEdge is a ship due-diligence web app for trading desks that fix ships for grain, oilseeds, vegetable oils and dry bulk in the Black Sea, the Strait of Hormuz, the Gulf of Oman and the UAE. Someone types a ship's name, former name, IMO or MMSI number and sees its last twelve months: every voyage on one map, every red flag with its evidence, a one-sentence verdict, team notes and a PDF report. It runs on the customer's own server, records the free aisstream.io AIS feed, and buys a ship's past from Datalastic only when asked.

- The specification is `docs/BRIEF.md` (read it before any task). `docs/STATUS.md` says what is done and what is next.
- How each red flag is decided: `docs/METHODOLOGY.md`. Capabilities and the comparison with other platforms: `docs/PRODUCT.md`. HTTP routes and JSON shapes: `docs/API.md`. System design: `docs/ARCHITECTURE.md`.

## Who you work for

The owner, Deni, works only from an iPhone: no terminal, no laptop. Anything an admin must change is built into the app (Profile › Data sources, Team, Email, Red-flag rules, Sensitive zones, Detailed maps, Server), never into a file on the server. When the owner has to act, say exactly what to tap, using the app's own labels. `docs/OWNER-CHECKLIST.md` lists what only the owner can do.

**Pushing to `main` deploys to the live server.** The server pulls `main` every 10 minutes, builds the images, runs the whole test suite and the migrations on a scratch database, and switches over only when everything passes (`deploy/autoupdate.sh`). Push to `main` only when the owner has said so; otherwise work on a branch and open a pull request.

## Rules that are never broken

- **Ships are keyed on the IMO number**, never on the name. Name, flag and MMSI are history rows on the IMO.
- **No hard-coded thresholds.** Defaults live in `config/rules.yaml`, sensitive zones in `config/zones.geojson`, ports in `config/ports.csv`, jamming and STS areas in `config/areas.json`. Admins override thresholds and switch zones in the app; the overrides live in `settings.json` on the data volume.
- **Secrets:** keys only in `.env` or in the app's settings on the data volume. Never commit `.env`; never put a key in a prompt, a test, a log line or a URL.
- **Every paid position is bought once:** call `store.covered()` before `provider.get_track()` and write what you bought with its `fetch_log` row. Never fetch a window twice.
- **One door to vendors:** only `backend/app/providers/` talks to an AIS vendor, through the `AISProvider` protocol in `providers/base.py`. The engine (`backend/app/engine/`) is pure Python with no web, database or network imports.
- **Nothing mock or fake on a server.** The generated fleet (`providers/mock.py`) is for tests and `make dev` only (`VVT_ALLOW_MOCK=1`). Never add placeholder data, sample text or fake sign-in options to the app; everything on screen comes from the API.
- **One place for each thing:** every API route in `backend/app/routes.py` (shared by FastAPI and the dev server); every verdict sentence and finding story in `backend/app/verdict.py`; JSON shapes in `backend/app/service.py` and `routes.py`.
- **Honest findings.** Draught-based flags are indicators, not proof: keep that sentence in the UI and the report. On the free terrestrial feed, a gap where no receiver can hear is Info, not a flag (the gap rule asks the provider for `coverage(lon, lat)`); keep that honest in the UI and the report. Findings are indicators for a person's judgement, never legal conclusions.
- **Global Fishing Watch** is a cross-check only, never a primary source. Its free licence (CC BY-NC 4.0) excludes internal use that supports a commercial business, so a trading desk needs GFW's written licence before relying on it; keep that said wherever the cross-check is offered.
- **Do not scrape** MarineTraffic or VesselFinder (their terms forbid it).
- **No third-party scripts, fonts or map services.** MapLibre, the fonts and Natural Earth are vendored; nginx sends a strict Content-Security-Policy: no inline scripts or inline event handlers, nothing loaded from other sites.
- **Migrations are append-only and idempotent** (`backend/migrations/NNN_name.sql`); every update re-applies all of them. Never edit one that has shipped; add the next number.

## Map of the code

```
backend/app/engine      pure pipeline: clean → port calls → voyages → seven rules → status (analyze() in pipeline.py)
backend/app/providers   base (Protocol), aisstream (recorded free feed), datalastic, kpler (stub), gfw (cross-check), mock (dev only)
backend/app/recorder.py aisstream.io websocket → ais_live, mmsi_map, mmsi_names; status file the app shows
backend/app/service.py  search → identify → cached fetch → analyze → verdict → JSON; region overview; background sweep
backend/app/verdict.py  verdict level, sentence, figures and per-finding stories (fixed rules)
backend/app/routes.py   every /api route: auth level, CSRF header, JSON errors; main.py (FastAPI) and devserver.py dispatch here
backend/app/accounts.py users, sessions, invites, password resets (scrypt; secrets stored as SHA-256); auth.py resolves callers
backend/app/store.py    MemoryStore (dev, tests) and PostgresStore (PostGIS); fetch_log enforces "buy once"
backend/app/jobs.py     refresh (watchlist → alerts → push), sweep, sanctions, prune-live; push.py (VAPID), mailer.py (SMTP)
backend/app/sanctions   OFAC SDN, EU and UK list downloads → sanctions table
backend/app/reports     Jinja2 report → Playwright PDF
backend/app/maps.py     admin-started download of the OpenStreetMap extract (Protomaps)
backend/migrations      001…006, append-only
backend/tests           synth.py (synthetic tracks) + test_*.py
frontend/public         plain HTML/JS, no build: js/ui.js, api.js, map.js, pmtiles.js, onboarding.js, screens.js, profile.js, app.js; css/app.css; sw.js
config/                 rules.yaml, zones.geojson, ports.csv, areas.json
deploy/                 cloud-init.yaml + install.sh (one paste), autoupdate.sh (the test gate), Caddyfile, cron, backup
docs/                   BRIEF, STATUS, PRODUCT, METHODOLOGY, API, ARCHITECTURE, DEPLOY, OWNER-CHECKLIST, PROVIDERS, FREE-STACK
```

## Commands

```bash
make dev        # app + API on http://localhost:8080 with the demo fleet; first account's server admin password: dev-setup-code
make test       # cd backend && pytest -q, or python3 -m tests.run without pytest (65 tests)
make lint       # ruff check app tests (config in backend/pyproject.toml)
make demo       # a sample PDF from the demo fleet (needs Playwright's Chromium)
node --check frontend/public/js/*.js          # syntax check the app (also run by CI)
cd backend && VVT_PROVIDER=aisstream python3 -m app.devserver   # the recorded-feed path instead of the demo fleet
cd backend && python3 -m app.cli pull 9000013 # one ship through the pipeline, printed
docker compose up --build                     # db + api + recorder + web on :8080 (needs Docker)
```

The PostGIS tests in `test_pgstore.py` run only when `DATABASE_URL` points at a scratch database; the server's update gate runs them on `vvt_test`. `test_postgres_store_static` checks every PostgresStore statement's placeholders without a database.

## Making common changes

- **A threshold:** change the default in `config/rules.yaml`, then mention it in `docs/METHODOLOGY.md`. Admins can already override it in the app.
- **A red-flag rule:** a function in `engine/rules.py` added to `RULES`; its thresholds in `rules.yaml` and in `DEFAULTS` in `engine/rules_config.py`; its sentence and story in `verdict.py` (`_categories` and `story`); tests on synthetic tracks in `tests/test_engine.py` using `tests/synth.py` (`Track(...).sail_to_port(...)`, `.drift()`, `.set_draught()`, `.jump()`, `gap=(fraction, hours)`); a section in `docs/METHODOLOGY.md`.
- **A data provider:** implement `AISProvider` in `providers/<name>.py`, register it in `providers/__init__.py`, add its key name to `settings_store.KEY_ENV` and to Profile › Data sources (`profile.js`), log credits per call, and document it in `docs/PROVIDERS.md`.
- **An API route:** `@route(method, path, level)` in `routes.py`, a test in `tests/test_routes.py`, the call in `frontend/public/js/api.js`, a row in `docs/API.md`.
- **A screen or a profile page:** `screens.js` or `profile.js`, the route in `app.js` (`parse()` and `route()`), styles in `css/app.css`. A new static file must be added to `SHELL` in `sw.js`. The web image stamps a content hash into `sw.js` at build time, so phones pick up the new version by themselves.
- **A database change:** a new `backend/migrations/00N_*.sql` that can run twice without harm, the same change in both stores in `store.py`, and a test.

## Conventions

- Python 3.11+, standard library first; `ruff` clean. Times are epoch milliseconds, UTC, everywhere (`Position.t`, JSON, database helpers). Units: nm, knots, metres, hours.
- JavaScript: plain ES modules-by-convention (globals per file, no bundler, no framework), `'use strict'`, no inline handlers (CSP). MapLibre zoom expressions must sit inside a top-level `interpolate` or `step`.
- Words on screen: short, plain sentences in the person's terms ("went dark", "stopped beside"), never developer jargon. Wording for findings and verdicts belongs in `verdict.py` so the app, the PDF and the notifications match.
- Errors shown to people are sentences (`{"detail": …}`); never echo a stack trace or a key.
- Accessibility: every control has a label; respect Reduce Motion; text stays readable in light and dark.

## Done means

1. `make test` passes and `make lint` is clean; `node --check` passes on every changed JS file.
2. For screens: you clicked through the change at iPhone size (390 × 844) in light and dark with `make dev`, with no console errors.
3. The docs that describe the change are updated (`STATUS.md` always; `METHODOLOGY.md`, `API.md`, `PRODUCT.md`, `OWNER-CHECKLIST.md` when they are affected).
4. Commit messages say what changed for the person using the app. No secrets, no generated demo data, no stray files.

## Words you will meet

IMO: the ship's permanent seven-digit number. MMSI: the radio identity, changes with the flag. AIS: the position messages ships broadcast; received by coastal receivers (terrestrial) or satellites. SOG/COG: speed and course over ground. Draught: how deep the hull sits, typed in by the crew; it rises when cargo is loaded. Port call: stopped under 0.5 kn for 6 hours or more at a port or anchorage. Going dark: an AIS gap at sea. STS: a ship-to-ship transfer, two ships stopped side by side outside a port. Sanctions lists: OFAC SDN (US), EU, UK (FCDO). Flag: the ship's country of registration.
