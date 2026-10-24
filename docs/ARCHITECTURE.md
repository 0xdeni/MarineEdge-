# Architecture

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

**Engine invariants.** `analyze(vessel, raw_track, ref, rules, now)` is deterministic and side-effect free. Port calls are detected before rules (rules need `in_port`), voyages are split after rules (jump fixes are excluded from distances), and every flag is attached to the voyage whose time window contains it; vessel-level flags (sanctions, identity) stay unattached.

**Cost control.** `Service.track()` asks `store.covered(imo, window)` first; the paid provider is called only for an uncovered window and the result is written with a `fetch_log` row carrying the credit estimate. On the recorded feed the positions are read in place and any bought history for that ship is merged in. STS partner lookups are the second paid call type, capped per vessel.

**No demo on a server.** The generated fleet (`providers/mock.py`) exists for tests and development only; `settings_store.provider_name()` falls back to the recorded feed unless `VVT_ALLOW_MOCK=1`, and migration 006 removed what earlier demo runs left in a server's database.

**One source of truth for words.** The verdict sentence, the figures and each finding's title and line are produced by `app/verdict.py` from the findings' structured facts (`Flag.meta`), so the app, the PDF and the notifications say the same thing.

**Security.** Accounts by invitation (the first one needs the server admin password). Session cookie HttpOnly, SameSite=Lax, Secure behind HTTPS; unsafe methods need the `X-MarineEdge` header unless a script uses an API token. Rate limits on sign-in, sign-up, reset and password change. Strict CSP from nginx: scripts, styles, fonts, map data and workers only from the app itself.

## Free data path

```
aisstream.io websocket ──► app/recorder.py (container `recorder`) ──► ais_live, mmsi_map, mmsi_names (PostGIS)
                                                                        │
                       OwnAISProvider (app/providers/aisstream.py) ◄────┘   same Protocol as Datalastic/Kpler
                              │  get_track / search (incl. former names) / vessels_near / vessels_in_area / get_static / coverage()
                              ▼
                       Service.analysis() ─► engine.analyze(..., coverage=provider.coverage)
                                                 └─ rule_ais_gap: gap in a cell with < coverage_min_fixes fixes → Info
Global Fishing Watch API v3 (app/providers/gfw.py) ─► /api/vessels/{imo}/crosscheck ─► "Cross-check" section (second opinion only)
```

Positions are keyed by MMSI on arrival (that is what AIS transmits) and get their IMO from the ship's static broadcast; `live_backfill_imo` links earlier rows once the MMSI→IMO pair is known. Several MMSIs for one IMO become MMSI-history rows on the vessel (identity-change rule); a changed broadcast name is kept in `mmsi_names`, so search finds ships by former names.
