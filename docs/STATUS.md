# Status — 23 Oct 2026

Links: repo https://github.com/0xdeni/MarineEdge- · PWA prototype https://claude.ai/artifact/58pvuQYeUG1SCMQPxCPUBF · website canvas https://claude.ai/artifact/4oWLpjGRkTYuwPXWBpYgmi · owner checklist `docs/OWNER-CHECKLIST.md`

## Where things stand against the brief's milestones

| Milestone | State | Notes |
|---|---|---|
| M1 Foundations (steps 0–4) | **Done on mock data; waiting for a key** | Repo, PostGIS schema, adapter interface, mock provider, Datalastic adapter (field names from public docs, unverified), Kpler stub, search endpoint, cache rule with `fetch_log`, CLI with `first-pull` acceptance checks, API token auth. |
| M2 Voyage map (5–6) | **Done on mock data** | Port calls, voyages, chart with MapLibre/OpenFreeMap tiles under the canvas overlay (verified with a stand-in map object; needs one look on a real network) and schematic fallback offline. |
| M3 Red flags (7–8) | **Done on synthetic tracks** | All seven rules, 23 tests pass (19 engine + 4 sanctions parsers), flag panel with evidence and "show on chart", OFAC/EU/UK/OpenSanctions parsers, STS lookup cap. |
| M4 Report and go-live (9–10) | **Report done; deploy files written, not yet run on a server** | Jinja2 → Playwright PDF; Docker Compose with Caddy (auto-HTTPS), systemd unit, nightly backup + restore scripts, cron for sanctions refresh, `docs/DEPLOY.md`. |

Beyond the brief: iOS-style PWA shell (glass tab bar and sheet), login, Vessels/Alerts/Reports/Profile pages, Settings that edit rules, zones, provider, appearance, map tiles; marketing landing page on a design canvas.

## Decisions taken

- **Product name: MarineEdge** (repo `0xdeni/MarineEdge-`). The brief's "Vessel Voyage Tracker" stays only inside `docs/BRIEF.md`.
- **Frontend is plain HTML/JS, not React.** The brief allows it; the same code runs offline (in-browser engine + mock fleet) and online (`?source=server`). React/TypeScript port only if a second developer needs it; the API JSON shapes are stable.
- **Engine is pure Python, no pandas/shapely.** Simple loops over ≤10k points per vessel (1 s for the 40-vessel fleet). PostGIS does the heavy geo queries in production.
- **Mock provider ported to Python** so the backend, tests and demos run with no key and no credits.
- **MapLibre + OpenFreeMap** as the base map (free, no key); the canvas overlay keeps voyages, flags, ships and the report snapshot. Schematic coastlines remain the offline fallback and the artifact's only mode (the artifact sandbox blocks tile fetches).
- **Datalastic first** as the real adapter (public credit plans, historical area scan, no contract). Kpler stub ready for the second trial.
- **Auth:** API tokens in `.env` now; SSO (Google/Microsoft via oauth2-proxy in front of Caddy) at go-live.

## Blocked on Deni

See `docs/OWNER-CHECKLIST.md`. Shortest version: Datalastic key → `first-pull` output; Kpler answers; 5–10 real IMOs; a VPS + domain; identity provider.

## Next engineering steps (no input needed)

1. World Port Index import script (all ports; the 68 regional ones are hand-placed now).
2. Background refresh job for watched vessels (cron inside the api container, `app.cli pull --refresh` on the watchlist) and PWA push notifications.
3. Flag-level unit tests on the generated fleet (regression: counts per rule per vessel are stable).
4. React port only on request.

## Known gaps

- Datalastic field names are from the public docs and not yet verified against a live response; `first-pull` reports exactly which check fails.
- MapLibre path exercised only with a stand-in map object here (no outbound network in this workspace); verify tiles, pinch and `fitBounds` padding on a phone after deploy.
- `get_vessels_near` on a paid provider costs one historical area scan per slow-drift window; capped at `sts.max_lookups_per_vessel` (12) per run.
- UK CSV link changes with each publication and is set by hand in `.env` for now.
- The PWA login is a token prompt in server mode and cosmetic in offline mode; SSO comes at go-live.
