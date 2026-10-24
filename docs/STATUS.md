# Status — 24 Oct 2026

Links: repo https://github.com/0xdeni/MarineEdge- · PWA prototype https://claude.ai/artifact/58pvuQYeUG1SCMQPxCPUBF · website canvas https://claude.ai/artifact/4oWLpjGRkTYuwPXWBpYgmi · owner checklist `docs/OWNER-CHECKLIST.md`

**Live since 24 Oct 04:03 (São Paulo):** first server on an AWS Free-plan trial — t4g.small (2 Arm cores, 2 GB), Ubuntu 26.04, us-east-1, `https://44-197-249-76.sslip.io`. Installed from the owner's iPhone through EC2 Instance Connect; updates itself from GitHub every 10 minutes, each update gated by the full test suite plus migrations and the PostGIS store test on a scratch database. The trial ends six months after sign-up (late April 2027): an in-app export/import is the next engineering item.

## Where things stand against the brief's milestones (honest, 24 Oct)

| Milestone | Accepted when (brief) | Where we are |
|---|---|---|
| M1 Foundations | I can search a vessel by name or IMO and pick the right ship; positions are cached | Built and proven on demo data. On the live server, search only covers ships recorded since 24 Oct (free feed) and filters what the app has loaded instead of asking the server. A paid provider is wired but unproven (no key yet). **Not accepted.** |
| M2 Voyage map | 12 months of a real vessel shows as separate coloured voyages with correct ports and dates | Engine and map built; never run on 12 months of real data, which needs a paid history pull. Port detection uses 68 hand-placed ports until the World Port Index is imported. **Not accepted.** |
| M3 Red flags | All seven rules fire correctly on test tracks and on one known real case | Synthetic test tracks pass; no real case yet. **Half.** |
| M4 Report and go-live | PDF report exports; tool runs on the server with backups; tests pass | Server live since 24 Oct with test-gated auto-updates; nightly backup only on the server's own disk (no off-site copy); PDF export not yet verified on the server. **Partly.** |

**Assessment.** The infrastructure is ahead of plan; the product is behind it. The core job of the brief — 12 months of a specific ship's voyages and red flags before a fixture — has not been demonstrated on real data, because that history only comes from a paid provider, and the free feed can only build history from 24 Oct onward. Meanwhile effort went into things the brief puts out of scope (fleet map, alerts and push, PWA polish, marketing site, own recording), partly on request. The owner's verdict on the UI — raw, gimmicky, oversized, abstract, unintuitive — is fair: it was built mock-first and decorated for screenshots (glass, animations, fake sign-in options, demo text leaking into the live build, developer jargon on user screens) instead of designed around the two screens the brief asks for.

**Next, in order:**
1. Live map on the recorded feed (in the update queue; verify on the owner's phone).
2. Real history: a Datalastic trial key → first pull of 5–10 real vessels including one known AIS-gap case → validate voyages, ports and flags against reality (M2/M3 acceptance). Needs the owner.
3. Real-data hardening: World Port Index fetched and imported on the server; server-side search across recorded and provider data; PDF verified on the server; off-site backups.
4. Redesign from the brief's two screens, with clickable mockups for sign-off before rebuilding: search-first home; one vessel page that reads like the report (plain-language verdict, voyage map, voyage list, findings with evidence); dense, quiet typography; no fake features; technical details behind a disclosure.

## UI/UX state (reviewed 23 Oct at iPhone 15 size, every screen, light and dark)

Done: iOS-style shell (glass tab bar, bottom sheet with search, large titles, grouped settings), login, chart with regions/zones/ports/ships, vessel sheet (voyages · flags with evidence and "show on chart" · identity history · sanctions · particulars), voyage detail with analyst note, alerts feed, reports page and in-app report, profile + settings (provider, rules, zones, appearance, notifications, about), admin screens. Polish pass this night: transparent top bar until scroll, seamless schematic chart when zoomed out, zone labels kept on screen, flags ordered by severity, KPI typography, empty-state CTA. The prototype link is now built from the repo's frontend (same code as production), so it stays in sync.
Open: MapLibre tiles and pinch gestures unverified on a real phone (needs the server); a proper app icon and wordmark (placeholder glyph now); onboarding/empty states for a brand-new server (no ships recorded yet); desktop layout is functional but not designed; marketing site exists only as a design canvas, not as pages.

## Design pass (23 Oct, 04:00)

Screens were captured at iPhone size in light and dark and reviewed one by one. Fixed: graticule labels bleeding under the sheet, port labels colliding, 13 identical flag pins stacking (now clustered with counts; tapping a cluster zooms in), 42 voyages drawn with equal weight (older ones now recede), "Now" marker lost under labels (now an accent pill). Added: lens-edge lighting on every glass surface, press feedback on everything tappable, a tab bar that minimises while reading and returns on scroll-up, empty states with marks, a sonar-and-chart-grid sign-in backdrop. The prototype link and `scripts/build_single.py` (one-file demo) are rebuilt from the real frontend. Still generic by my own judgment: the settings pages (iOS grouped lists do the job but carry no identity), the login card itself, and the schematic coastlines until MapLibre tiles are seen on a real phone. Next in design: a bespoke icon set, a chart-paper light theme for the map, Dynamic Type and iPad layout checks.

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

- **The update gate earned its keep on day one (24 Oct, 04:40):** it refused `f0e54f6` because a refactor had deleted the neighbour-search query (`LIVE_NEAR_SQL`); the server stayed on the previous version and the app showed the failing test. Fixed, and `test_postgres_store_static` now checks on any machine, without a database, that every attribute PostgresStore uses exists and every statement gets as many parameters as it has placeholders.
- **Live map on the recorded feed (24 Oct, 04:40):** with a real provider the app loads live ships per region from `/api/regions/{region}/vessels` (one joined query per region on the server, no per-ship lookups), refreshes every 3 minutes, and builds a ship's full analysis when it is opened; switching provider in the app drops the old source's data and reloads. The app no longer queries the server before sign-in (that left the admin controls hidden after the first sign-in). Recorded tracks are read straight from the live table, never copied into the paid-data cache. Verified end to end against a dev server fed simulated AIS for five Black Sea ships (sign-in, live list and map, vessel analysis, admin controls, reload, region switch; no JS errors).
- **The first real install found four bugs, all fixed the same night:** the installer died generating secrets (`tr </dev/urandom | head` under `pipefail`, on every provider); Docker's buildx plugin was not installed; the server's web app opened the offline demo unless `?source=server` was added; migration 003 failed when re-applied after 004. The installer is now drilled end to end with faked system commands (fresh install, re-run, Docker-repository fallback) and every migration is run with stop-on-error against PostgreSQL 16 (fresh and upgraded databases, repeated passes).

- **Server: Oracle refused the owner's sign-up and Hetzner is paid, so the first server is an AWS Free-plan trial** (t4g.small, 2 GB, Arm; ~$18/month of credit, 6 months, cannot bill the card). The installer was made to fit it: swap on 1–2 GB machines, one API worker, memory-sized Postgres settings, Arm PostGIS image now actually written to `.env` (the 23 Oct Arm change computed it but never saved it — fixed). Before month 6 the data must move: an in-app export/import is next on the engineering list.
- Oracle's Always Free tier was halved in June 2026 (now 2 OCPU / 12 GB); docs corrected.
- Recorded-AIS storage re-estimated: the 23 Oct policy (one fix per 2 min) would have been ~45–80 GB/year with full coverage, too much for 30–40 GB disks. Now: significance sampling (10 min under way / 30 min stopped / turns / starts and stops, with hysteresis), slim rows (migration 004: no geography column or GIST index, REAL lat/lon, primary key (ts, mmsi)) — ~130 bytes per fix, ~7–12 GB/year per 3,000 ships; plus a disk guard (positions pause below 3 GB free) and disk/database size on the admin screen. Migration 004 and every live-table query were run against a real PostgreSQL 16 here (without PostGIS, which the live table no longer needs).

- The repository is private, so a fresh server cannot download the code anonymously. The installer now takes an optional read-only `GITHUB_TOKEN` (fine-grained PAT) from the cloud-init file and stores it in the clone's remote so auto-update works; making the repository public is the simpler route (checklist A0).

- aisstream.io message field names follow their public docs and sample payloads; the recorder logs any message it cannot parse, and the parser is unit-tested on those shapes. First hour on a real key confirms them.
- Global Fishing Watch v3 endpoint and dataset names are from the public docs, unverified; the cross-check reports per-dataset errors instead of failing.
- The recorder is a second container on the same image; it idles (logs a warning every 60 s) until a key exists, so a server without a key wastes nothing. Volume policy (one fix per ship per 2 min, cargo/tanker only once known, 30 days full resolution then 15-min, 14-month retention via the daily `prune-live` job) keeps PostGIS near 15 GB/year; the first week of real traffic will show whether the estimate holds.
- `ais_live` row counts on the admin screen are planner estimates (exact counting a 100M-row table on every page view is not worth it); "latest" and "since" are exact.

- Datalastic field names are from the public docs and not yet verified against a live response; `first-pull` reports exactly which check fails.
- MapLibre path exercised only with a stand-in map object here (no outbound network in this workspace); verify tiles, pinch and `fitBounds` padding on a phone after deploy.
- Web Push delivery needs `pip install pywebpush` and VAPID keys (`python -m app.push keygen`); without them alerts are stored and shown in the app but not pushed.
- The refresh job re-analyses watched vessels every 30 min and buys only the new tail of positions (one hour of overlap); the first run after deploy buys the full 12 months for each watched ship.
- `get_vessels_near` on a paid provider costs one historical area scan per slow-drift window; capped at `sts.max_lookups_per_vessel` (12) per run.
- UK CSV link changes with each publication and is set by hand in `.env` for now.
- The PWA login is a token prompt in server mode and cosmetic in offline mode; SSO comes at go-live.
- The installer and Docker build have not run on a real server yet (no Docker here). CI now does what I cannot do locally: builds the images, boots db + api + recorder + web, probes search/region/analysis/admin/cross-check/PDF, and runs the PostgresStore test against a real PostGIS. **Actions is enabled and fires on every push, but all 17 runs since the first commit end in `startup_failure` before any job starts — including a trivial probe workflow with no third-party actions, so the workflow files are not the cause; it is account- or repo-level (billing/spending limit, a flagged account, or an Actions policy). The banner on any run in the Actions tab names it; D0 in the checklist says what to tap.** One real bug was already caught by writing that test: the first positions insert for a new ship violated the `positions → vessels` foreign key; fixed in `put_positions`.
- Two lint errors (unused imports) that `ruff` would have failed on were fixed; CI lints on every push once enabled.
- **Alternative to GitHub Actions, built:** the server is the CI. `deploy/autoupdate.sh` builds the new image beside the running one, runs all tests inside it, switches over only when green, health-checks, rolls back otherwise, and writes the verdict to `state/update.json`, which the admin screen shows (Profile › AIS provider › Server updates). GitHub Actions stays as a bonus if the account gets unblocked.
