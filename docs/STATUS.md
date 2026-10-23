# Status — 23 Oct 2026 (late night)

Links: repo https://github.com/0xdeni/MarineEdge- · PWA prototype https://claude.ai/artifact/58pvuQYeUG1SCMQPxCPUBF · website canvas https://claude.ai/artifact/4oWLpjGRkTYuwPXWBpYgmi · owner checklist `docs/OWNER-CHECKLIST.md`

## Where things stand against the brief's milestones

| Milestone | State | Notes |
|---|---|---|
| M0 Free data path (not in the brief) | **Built, waiting for the free aisstream key** | `recorder` container records aisstream.io live AIS for both regions into `ais_live`/`mmsi_map`; `OwnAISProvider` serves search, tracks, neighbours, static data from it with zero credits; AIS-gap rule is coverage-aware (Info "outside receiver coverage" where no receiver can hear); Global Fishing Watch cross-check button (free, non-commercial licence); Oracle Always Free supported by the installer. `docs/FREE-STACK.md`. |
| M1 Foundations (steps 0–4) | **Done on mock data; waiting for a key** | Repo, PostGIS schema, adapter interface, mock provider, Datalastic adapter (field names from public docs, unverified), Kpler stub, search endpoint, cache rule with `fetch_log`, CLI with `first-pull` acceptance checks, API token auth. |
| M2 Voyage map (5–6) | **Done on mock data** | Port calls, voyages, chart with MapLibre/OpenFreeMap tiles under the canvas overlay (verified with a stand-in map object; needs one look on a real network) and schematic fallback offline. |
| M3 Red flags (7–8) | **Done on synthetic tracks** | All seven rules, 35 tests pass (19 engine, 4 sanctions parsers, 4 service/cache, 2 fleet regression, 6 free-path: parser, live store, recorder, provider, coverage rule, GFW normaliser), flag panel with evidence and "show on chart", OFAC/EU/UK/OpenSanctions parsers, STS lookup cap. |
| M4 Report and go-live (9–10) | **Report done; one-paste installer written, not yet run on a server** | Jinja2 → Playwright PDF; `deploy/cloud-init.yaml` + `install.sh` set up Docker, PostGIS, API, web, Caddy (auto-HTTPS on a domain or `<ip>.sslip.io`), push keys, cron (backup, sanctions, watchlist refresh, auto-update from GitHub). |

Phone-only operation: the AIS provider and its key, the connection test, the first-pull acceptance checks and the job triggers are all in the app (Profile › AIS provider, admin token). The server installs itself from a cloud-init paste in the hosting provider's app and auto-updates from GitHub.

Beyond the brief: iOS-style PWA shell (glass tab bar and sheet), login, Vessels/Alerts/Reports/Profile pages, Settings that edit rules, zones, provider, appearance, map tiles; watchlist refresh job that turns new flags into alerts and Web Push notifications; server-side watchlist and notes per user; World Port Index importer; dependency-free dev server; marketing landing page on a design canvas.

## Decisions taken

- **Product name: MarineEdge** (repo `0xdeni/MarineEdge-`). The brief's "Vessel Voyage Tracker" stays only inside `docs/BRIEF.md`.
- **Frontend is plain HTML/JS, not React.** The brief allows it; the same code runs offline (in-browser engine + mock fleet) and online (`?source=server`). React/TypeScript port only if a second developer needs it; the API JSON shapes are stable.
- **Engine is pure Python, no pandas/shapely.** Simple loops over ≤10k points per vessel (1 s for the 40-vessel fleet). PostGIS does the heavy geo queries in production.
- **Mock provider ported to Python** so the backend, tests and demos run with no key and no credits.
- **MapLibre + OpenFreeMap** as the base map (free, no key); the canvas overlay keeps voyages, flags, ships and the report snapshot. Schematic coastlines remain the offline fallback and the artifact's only mode (the artifact sandbox blocks tile fetches).
- **Free first, paid per ship.** aisstream.io (free live feed) is recorded from day one so history accrues at €0; Datalastic is bought per IMO only for the past 12 months or open-sea coverage of ships that matter, and cached forever. Kpler stub ready for the second trial.
- **Coverage honesty.** On a terrestrial feed a gap where no receiver can hear is not evidence. The gap rule asks the provider for receiver coverage (fixes per 0.5° cell over 30 days) and downgrades such gaps to Info up to `coverage_max_hours`; the admin screen shows what has been recorded since when.
- **GFW is a cross-check, never a source.** Its licence is non-commercial; events are shown beside our flags with the licence line printed.
- **Auth:** API tokens in `.env` now; SSO (Google/Microsoft via oauth2-proxy in front of Caddy) at go-live.

## Blocked on Deni (iPhone only, no terminal needed)

See `docs/OWNER-CHECKLIST.md`. Shortest version: create a server with the cloud-init paste (Hetzner €4.5/mo or Oracle Always Free €0) → open the app → paste the free aisstream.io key (B0) → history starts. Then, only when a ship's past matters: Datalastic key → first pull → screenshots to me. Then Kpler answers, a domain, the identity provider.

## Next engineering steps (no input needed)

1. Run `scripts/import_wpi.py` on the NGA World Port Index CSV once downloaded (free; the 68 regional ports are hand-placed now).
2. Verify the MapLibre tiles, pinch and `fitBounds` padding on a real phone after the first deploy.
3. Datalastic field mapping against a live response (`first-pull`), then the Kpler adapter when their answers arrive.
4. React port only on request.

## Known gaps

- aisstream.io message field names follow their public docs and sample payloads; the recorder logs any message it cannot parse, and the parser is unit-tested on those shapes. First hour on a real key confirms them.
- Global Fishing Watch v3 endpoint and dataset names are from the public docs, unverified; the cross-check reports per-dataset errors instead of failing.
- The recorder is a second container on the same image; it idles (logs a warning every 60 s) until a key exists, so a server without a key wastes nothing.

- Datalastic field names are from the public docs and not yet verified against a live response; `first-pull` reports exactly which check fails.
- MapLibre path exercised only with a stand-in map object here (no outbound network in this workspace); verify tiles, pinch and `fitBounds` padding on a phone after deploy.
- Web Push delivery needs `pip install pywebpush` and VAPID keys (`python -m app.push keygen`); without them alerts are stored and shown in the app but not pushed.
- The refresh job re-analyses watched vessels every 30 min and buys only the new tail of positions (one hour of overlap); the first run after deploy buys the full 12 months for each watched ship.
- `get_vessels_near` on a paid provider costs one historical area scan per slow-drift window; capped at `sts.max_lookups_per_vessel` (12) per run.
- UK CSV link changes with each publication and is set by hand in `.env` for now.
- The PWA login is a token prompt in server mode and cosmetic in offline mode; SSO comes at go-live.
- The installer and Docker build have not run on a real server yet (no Docker here); first boot may need one fix, which auto-update delivers within 10 minutes of the push.
