# Architecture

How MarineEdge is built and why. For what it does, read `PRODUCT.md`; for how a finding is decided, `METHODOLOGY.md`; for the HTTP routes, `API.md`.

## The system at a glance

```
iPhone / desktop PWA (frontend/public) — plain HTML/JS, no build step
   ├─ js/ui.js          formatting, icons, toasts, action sheets, draggable sheets, pushed pages
   ├─ js/api.js         same-origin fetch; HttpOnly session cookie; X-MarineEdge header on every change
   ├─ js/map.js         MapLibre GL (vendored, CSP build) with our own style: Natural Earth (bundled geo/ne.json)
   │                    + optional OpenStreetMap detail (/tiles/basemap.pmtiles via js/pmtiles.js, range requests)
   ├─ js/onboarding.js  welcome, intro, sign in, create account, forgot/reset, invites
   ├─ js/screens.js     Home (search, region overview), ship, voyage, finding, notes, alerts, lists
   ├─ js/profile.js     profile and settings pages; admin pages
   └─ js/app.js         state, hash router, theme, polling;  sw.js caches the shell, network-first API
   ▼
Caddy (HTTPS) ── /api/* ──► FastAPI (backend/app/main.py) ─┐
             └─ the rest ─► nginx (web): app files, /tiles/ from the shared data volume
                                                            │
app/routes.py   one framework-free router for every /api route (auth levels, CSRF, JSON errors);
                FastAPI and the stdlib dev server (app/devserver.py) both dispatch to it
app/accounts.py users, sessions, invites, password resets (scrypt; secrets stored as SHA-256)
app/service.py  search → identify → cached fetch → analyze → verdict → JSON; region overview; background sweep
   ├─ providers/  one adapter per vendor (base.py Protocol): aisstream (recorded feed), datalastic, kpler stub, gfw cross-check, mock (dev only)
   ├─ engine/     pure Python: clean → port calls → voyages → 7 rules → status
   ├─ verdict.py  the one-sentence verdict, figures and per-finding stories, by fixed rules
   ├─ store.py    MemoryStore (dev, tests) | PostgresStore (PostGIS); fetch_log enforces "fetch once"
   ├─ sanctions/  daily OFAC SDN / EU / UK (FCDO) refresh into the sanctions table
   ├─ reports/    Jinja2 HTML → Playwright PDF (chart with Natural Earth coastlines)
   ├─ recorder.py aisstream.io websocket → ais_live, mmsi_map (container `recorder`); status file for the app
   ├─ jobs.py     refresh (watchlist → alerts → push), sweep, sanctions, prune-live
   └─ maps.py     admin-triggered download of the OpenStreetMap extract (pinned go-pmtiles, checksum verified)
config/           rules.yaml · zones.geojson · ports.csv · areas.json
```

## Technology, and why each piece

| Layer | Choice | Why |
|---|---|---|
| App | Plain HTML, CSS and JavaScript, no framework and no build step (the brief allows it) | Nothing to compile or keep upgraded; every file is what runs; a strict Content-Security-Policy is easy to keep; one person can read all of it |
| Installable app | Progressive Web App: manifest, service worker (shell cache-first, API network-first with the last answer as fallback), Web Push | Installs from Safari to the Home Screen; no App Store account or review; ships opened before stay readable offline; notifications on iOS 16.4+ |
| Map | MapLibre GL JS 5 (BSD-3-Clause), vendored, CSP build; our own style | Smooth with thousands of track points; no Mapbox fees; no tiles or fonts fetched from anyone else |
| Map data | Natural Earth (public domain) bundled for the whole region; optional OpenStreetMap extract (Protomaps PMTiles) on our own server | The map works on first open and offline; detail without a map service, an API key or tracking |
| API | Python with FastAPI in production; one framework-free router (`routes.py`) that the standard-library dev server also uses | What is tested locally is exactly what runs on the server |
| Analysis engine | Pure Python, standard library, deterministic (`engine/`) | Unit-testable on synthetic tracks; no pandas or shapely needed for at most ~10,000 positions per ship |
| Database | PostgreSQL 16 with PostGIS | Positions, zones and distance queries in one place; the recorded feed in a slim table built for volume |
| Words | Fixed rules in `verdict.py` | The same facts always read the same way, in the app, the PDF and the notifications; nothing is generated or guessed |
| PDF | Jinja2 HTML printed by Playwright's Chromium | The report looks like the app and needs no PDF library |
| Web server | nginx for the app files and map tiles (range requests); Caddy in front for automatic HTTPS | Certificates without effort, including on a bare IP via sslip.io |
| Packaging | Docker Compose: db, api, recorder, web, caddy | One file describes the server; the same images run everywhere |
| Updates | `deploy/autoupdate.sh` every 10 minutes from GitHub `main`, gated by the full test suite | The server is the CI: a red build never reaches the phone |
| Email | SMTP from the standard library, configured in the app | Any provider works (Gmail with an app password, Microsoft 365, SES, Postmark…) |
| Accounts | scrypt password hashes (standard library); session and reset secrets stored only as SHA-256 | No auth vendor, nothing reusable stored |

## What happens when someone opens a ship

1. The app calls `GET /api/vessels/{imo}/analysis`. `routes.py` resolves the caller (cookie or token), checks the auth level, then asks `Service.analysis()`.
2. `Service` asks the provider for the ship's particulars and latest static data, then `track()` gets twelve months of positions under the cache rule: on the recorded feed they are read in place (plus any history bought for this ship); on a paid provider only the window not already in `fetch_log` is bought.
3. `engine.analyze()` cleans the track, finds port calls, runs the seven rules, splits voyages and attaches each finding to its voyage, then derives the live status. It is pure: same input, same output.
4. `verdict.build()` chooses the level, the sentence, the detail and three figures; `verdict.story()` writes each finding's title and line.
5. The analysis is saved (`save_analysis`) and the ship's risk row updated (`vessel_risk`), so search results, the region overview and the watchlist show the verdict without re-running it. The row carries a stamp of the engine version, thresholds and zones that wrote it (`Service.engine_stamp`); a row under another stamp reads as not checked, and the background sweep checks that ship again.
6. `analysis_json()` returns the shape the app draws: the map, the verdict card, the timeline, voyages and evidence.

## Data model (PostgreSQL)

| Area | Tables |
|---|---|
| Ships | `vessels` (particulars by IMO), `vessel_identity_history` (name, flag, MMSI changes) |
| Bought positions | `positions` (PostGIS points by IMO and time), `fetch_log` (every paid window with its credits) |
| Recorded feed | `ais_live` (slim: one row per sampled fix, keyed by MMSI and time), `mmsi_map` (MMSI → IMO, static data), `mmsi_names` (every name an MMSI broadcast, for former-name search), `coverage_cells` |
| Analysis | `port_calls`, `voyages`, `flags`, `vessel_risk` (the last verdict per ship), `reports` |
| Reference | `ports`, `zones` (also read from `config/`) |
| Sanctions | `sanctions` (list, IMO, name, programme, listed and refreshed dates) |
| People | `users`, `sessions`, `invites`, `password_resets` |
| Team | `watchlist`, `vessel_notes` (ship, voyage or finding scope), `notes` (earlier per-voyage notes, migrated), `alerts`, `alert_seen`, `push_subscriptions` |
| Housekeeping | `schema_marks` (one-time data migrations already done) |

Migrations live in `backend/migrations/` (001 to 006), are idempotent and append-only, and are re-applied on every update. Runtime settings an admin changes in the app (provider, keys, rule overrides, zones switched off, SMTP) live in `settings.json` on the data volume (mode 0600), not in the database, so the nightly database dump does not contain them.

## Engine invariants

`analyze(vessel, raw_track, ref, rules, now)` is deterministic and side-effect free. Port calls are detected before the rules (rules need `in_port`), voyages are split after the rules (position-jump fixes are excluded from distances), and every finding is attached to the voyage whose time window contains it; ship-level findings (sanctions, identity) stay unattached.

## Cost control

`Service.track()` asks `store.covered(imo, window)` first; the paid provider is called only for an uncovered window and the result is written with a `fetch_log` row carrying the credit estimate. On the recorded feed the positions are read in place and any history bought for that ship is merged in, one fix per minute, the recorded one winning a tie. Ship-to-ship partner lookups are the second paid call type, capped per ship per run (`sts.max_lookups_per_vessel`).

## No demo on a server

The generated fleet (`providers/mock.py`) exists for tests and development only. `settings_store.provider_name()` falls back to the recorded feed unless `VVT_ALLOW_MOCK=1`, and migration 006 removed what earlier demo runs left in a server's database (people's notes are kept).

## One source of truth for words

The verdict sentence, the figures and each finding's title and line are produced by `app/verdict.py` from the findings' structured facts (`Flag.meta`), so the app, the PDF and the notifications say the same thing.

## Security

- **Accounts by invitation.** The first account needs the server admin password and becomes the owner; everyone else joins with a single-use invite link (7 days). Roles: admin, analyst.
- **Sessions:** HttpOnly cookie, SameSite=Lax, Secure behind HTTPS, 90 days sliding; listed in Profile › Signed-in devices, where any other device can be signed out. Changing or resetting a password ends the other sessions.
- **CSRF:** every state-changing cookie request must carry `X-MarineEdge: 1`, which a page on another site cannot send.
- **Rate limits** on sign-in, sign-up, forgot, reset and password change.
- **Secrets:** passwords hashed with scrypt; session, invite and reset secrets stored only as SHA-256; provider keys masked in every response and scrubbed from error messages; `.env` and `settings.json` are `0600`.
- **Browser:** a strict Content-Security-Policy from nginx: scripts, styles, fonts, map data and workers only from the app's own origin; no inline scripts; `frame-ancestors 'none'`. The app loads nothing from other sites. With the free feed as the main source, searches and ship checks run on your server against data it holds; a vendor learns an IMO number only when you buy that ship's history or ask Global Fishing Watch for a second opinion.
- **Updates:** nothing reaches the server unless the full test suite passes on it first.

## Free data path

```
aisstream.io websocket ──► app/recorder.py (container `recorder`) ──► ais_live, mmsi_map, mmsi_names (PostGIS)
                                                                        │
                       OwnAISProvider (app/providers/aisstream.py) ◄────┘   same Protocol as Datalastic/Kpler
                              │  get_track / search (incl. former names) / vessels_near / vessels_in_area / get_static / coverage()
                              ▼
                       Service.analysis() ─► engine.analyze(..., coverage=provider.coverage)
                                                 └─ rule_ais_gap: gap in a cell with < coverage_min_fixes fixes → Info
Global Fishing Watch API v3 (app/providers/gfw.py) ─► /api/vessels/{imo}/crosscheck ─► "Compare with Global Fishing Watch" (second opinion only)
```

Positions are keyed by MMSI on arrival (that is what AIS transmits) and get their IMO from the ship's static broadcast; `live_backfill_imo` links earlier rows once the MMSI→IMO pair is known. Several MMSIs for one IMO become MMSI-history rows on the ship (identity-change rule); a changed broadcast name is kept in `mmsi_names`, so search finds ships by former names.

The recorder samples instead of storing every message (a ship under way reports every 2–10 seconds): one fix per ship per 10 minutes under way and per 30 minutes stopped, plus a fix on every sharp turn, departure or arrival, about 4–5 fixes per ship-hour. Only cargo ships and tankers are kept once their type is known. After 30 days the daily `prune-live` job thins positions to one per 30 minutes and deletes them after 14 months; below 3 GB of free disk the recorder pauses. All of these numbers are in `rules.yaml › live`.

## Running it

| Container | What it does |
|---|---|
| `db` | PostgreSQL 16 + PostGIS (the Arm image on Arm servers) |
| `api` | FastAPI (uvicorn) with the engine, jobs and Playwright's Chromium for PDFs |
| `recorder` | The aisstream.io websocket; idle until a key is saved in the app |
| `web` | nginx with the app, the CSP and `/tiles/` from the data volume |
| `caddy` | HTTPS in front of everything (production profile) |

Cron (`deploy/cron.d-marineedge`, reinstalled by every successful update): watchlist refresh every 30 minutes, background check of ships in range every 20 minutes, sanctions download daily at 04:30, `prune-live` daily at 03:40, database backup daily at 03:00 (14 kept; off-site when `RCLONE_REMOTE` is set). Auto-update every 10 minutes from its own cron entry. Logs in `/var/log/marineedge-*.log`.
