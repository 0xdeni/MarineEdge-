# Status — 23 Oct 2026

## Where things stand against the brief's milestones

| Milestone | State | Notes |
|---|---|---|
| M1 Foundations (steps 0–4) | **Done on mock data** | Repo, schema, adapter interface, mock provider, Datalastic adapter (untested against a live key), search endpoint, position cache rule with `fetch_log`. Acceptance needs a real provider key. |
| M2 Voyage map (5–6) | **Done on mock data** | Port calls, voyages, map screen (schematic coastlines; MapLibre tiles still to add). Acceptance needs one real vessel's 12 months. |
| M3 Red flags (7–8) | **Done on synthetic tracks** | All seven rules, 19 engine tests pass, flag panel with evidence and "show on chart". Acceptance needs one known real case. |
| M4 Report and go-live (9–10) | **Report done; deploy not started** | Jinja2 → Playwright PDF works. Docker Compose is written but untested on a server; no backups yet. |

Beyond the brief: iOS-style PWA shell (glass tab bar and sheet), login, Vessels/Alerts/Reports/Profile pages, Settings that edit rules, zones, provider, appearance; marketing landing page on a design canvas.

## Decisions taken

- **Frontend is plain HTML/JS, not React.** The brief allows it. The same code runs offline (in-browser engine + mock fleet) and online (`?source=server`), and it already works. React/TypeScript can replace it in M2b if hiring needs it; the API's JSON shapes are stable.
- **Engine is pure Python, no pandas/shapely.** The rules are simple loops over ≤10k points per vessel (1 s for a 40-vessel fleet). PostGIS does the heavy geo queries in production.
- **Mock provider ported to Python** so the backend, tests and demos run with no key and no credits.
- **Schematic coastlines** in the chart until MapLibre + OpenFreeMap tiles are wired (M2b). The chart engine is canvas-based and keeps working for the report snapshot.
- **Datalastic first** as the real adapter: public credit-based plans, historical area scan, no contract. Kpler stub ready for the second trial.

## What is blocked on Deni

1. AIS trial keys (Datalastic and Kpler): see `docs/PROVIDERS.md`.
2. GitHub connection, then the repo name to push to.
3. 5–10 real IMOs, including one known dark ship, for the first real pull.
4. Hosting choice (one small VPS; Hetzner/DigitalOcean/Fly) and the domain.
5. Identity provider for SSO (Google Workspace or Microsoft) and product name confirmed: MarineEdge (repo 0xdeni/MarineEdge-).

## Next steps, in order

1. Datalastic trial key → `VVT_PROVIDER=datalastic` → run `python -m app.cli pull <IMO>` for 5 vessels → compare with the mock shapes, fix field mapping in `datalastic.py`.
2. M1 acceptance demo: search a real name, pick the right IMO, confirm `fetch_log` shows one fetch per vessel.
3. MapLibre base map (OpenFreeMap tiles) behind the existing canvas layer; keep canvas for voyages/flags.
4. EU and UK list parsers (URLs in `loader.py`), daily cron, OpenSanctions commercial licence if wanted.
5. Deploy: `docker compose up` on the VPS, Caddy for TLS, nightly `pg_dump` to object storage.
6. React/TypeScript port of the frontend only if a second developer needs it.

## Known gaps

- Datalastic field names are from the public docs and not yet verified against a live response.
- `get_vessels_near` on a paid provider costs one historical area scan per STS candidate window; cap it per vessel (`sts.max_lookups`, to add) before enabling on Kpler.
- No auth on the API yet; the PWA login is a demo. Put the API behind the SSO proxy on deploy.
- Position-jump rule marks the bogus fix but does not yet suppress the matching return-fix jump in distance totals when two jumps are adjacent.
