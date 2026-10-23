# Vessel Voyage Tracker — Developer Brief

*Oct 13, 2026 · @Djam · transcribed from the original PDF (docs/BRIEF.pdf)*

## Purpose and scope

Build an internal web tool where I type a vessel name or IMO number and see every voyage that ship made over the last 12 months, drawn on a map: the current voyage, the one before it, and so on, with suspicious behaviour flagged. I will use it for vessel due diligence before fixing a ship or accepting a cargo (grains, oilseeds, vegetable oils, dry bulk).

**In scope for the first version (MVP):**

- Search by vessel name, IMO or MMSI
- 12 months of position history, split into voyages from port to port
- A map with one coloured line per voyage; the current voyage dashed and updating
- A voyage list and a voyage detail view (ports, dates, draught on departure and arrival)
- Red-flag detection: AIS gaps, draught change at sea, possible ship-to-ship transfers, position jumps, calls at sensitive ports, name/flag/MMSI changes, sanctions-list hits
- A one-click PDF vessel report

**Out of scope for now:** fleet-wide monitoring and alerts, our own AIS receivers, a mobile app, and selling the tool to third parties. Build it so that a later product version is not blocked.

## How it works

Every search runs the same eight steps. Only step 3 costs money; everything after it runs on our own cached data.

1. **Search** — name, IMO or MMSI
2. **Identify ship** — pick the IMO from matching ships
3. **Fetch track** — 12 months of AIS positions, cached *(AIS provider API)*
4. **Clean** — drop duplicates and bad fixes
5. **Port calls** — slow 6 h+ near a port or anchorage
6. **Voyages** — port to port, one line each
7. **Red flags** — gaps, draught, STS, sanctions, ports *(sanctions lists + sensitive zones)*
8. **Map and report** — coloured voyages, flags, PDF export

## Data sources

The tool is only as good as its historical AIS data, so budget for one paid global AIS API from day one. Free feeds are fine for testing and for live top-ups only.

| Source | Coverage | History | Cost model | Role |
|---|---|---|---|---|
| Kpler / MarineTraffic API | Global, coastal + satellite | Yes | Paid credits / contract | Primary candidate |
| Kpler / Spire Maritime (Kpler bought Spire Maritime in April 2025) | Global, strong satellite | Yes | Paid contract | Primary candidate |
| Datalastic | Global | Yes | Paid monthly plans | Lower-cost option |
| VesselFinder API | Global | Limited | Paid credits | Alternative |
| aisstream.io | Coastal receivers only | Live only | Free | Testing, live top-up |
| Global Fishing Watch API | Global, focus on fishing and carrier vessels | Events (port visits, gaps) | Free, non-commercial terms | Cross-check of gaps |
| World Port Index (NGA) | Global port coordinates | n/a | Free | Port-call detection |
| OFAC SDN, EU and UK sanctions lists | Vessels listed by IMO | n/a | Free downloads | Sanctions screening |

**Rules for the developer:**

- Key every vessel on its **IMO number**. Names change on sale; MMSI changes with the flag. Keep a history of name, flag and MMSI per IMO.
- Hide the provider behind one adapter interface, so we can switch provider without touching the rest of the app.
- Cache every position we pay for in our own database; never pay twice for the same history.
- Confirm each provider's licence allows us to store the data and show it in our own tool. Get current pricing directly from the vendors.
- Do not scrape the MarineTraffic or VesselFinder websites. It breaks their terms of use and they block it.

## Screens

Two screens carry the MVP: the voyage map and the voyage detail.

**Main screen: every voyage of the vessel on one map.** One colour per voyage, newest first in the list. The current voyage is dashed and ends at the ship's live position. AIS gaps are dotted red, sensitive zones are shaded red, and each red flag is a marker on the map. Clicking a voyage in the list highlights it on the map and opens its detail.

**Voyage detail: every red flag shows its evidence.** Voyage facts (departed, arrived, duration, draught out/in, time dark), buttons Show on map / Add note / Export PDF, and the red flags on this voyage. Every flag shows its rule, severity, times and position, with a button that zooms the map to that spot and time window. The same content goes into the PDF report.

## Voyage splitting and red-flag rules

A voyage runs from one port call to the next. Put every threshold below in one config file so I can tune them without a code change.

**Port call:** speed under 0.5 knots for at least 6 hours, within 5 nm of a World Port Index port or inside an anchorage zone. Anchorage waiting time belongs to the port call it precedes.

| Red flag | Rule (starting threshold) | Severity |
|---|---|---|
| Sanctions hit | IMO on OFAC, EU or UK lists, now or in the past 12 months | High |
| Call at a sensitive port | Port call or anchorage inside a listed zone (e.g. Crimea, occupied Ukrainian ports, Syria, Iran, North Korea); zone list editable by me | High |
| AIS gap | No position for more than 6 hours at sea; raise to High if over 24 hours or within 100 nm of a sensitive zone | Medium / High |
| Draught change at sea | Reported draught changes by 1.0 m or more with no port call in between | High |
| Possible ship-to-ship transfer | Another vessel within 500 m, both under 1 knot, for 2 hours or more, outside port limits | High |
| Position jump | Implied speed between two fixes above 30 knots; label "possible GPS jamming" in known jamming areas (Black Sea, Baltic, Eastern Mediterranean, Gulf) | Medium |
| Identity change | Name, flag or MMSI changed in the period | Info (Medium if more than one) |

Each flag stores its evidence: start and end time, coordinates, the positions before and after, and the rule that fired. It shows on the map as a marker and in the flag list.

Draught is typed in by the crew, so draught-based flags are indicators, not proof. Ship-to-ship detection needs positions of other ships in an area, which costs more API calls; it can move to phase 2 if the provider makes it expensive.

## Tech stack

A standard, low-cost web stack is enough. These are suggestions; the developer may propose alternatives with a reason.

| Layer | Suggested choice | Why |
|---|---|---|
| Frontend | React + TypeScript | Common, easy to hire for |
| Map | MapLibre GL JS (free) with a free or low-cost base map | Draws thousands of track points smoothly, no Mapbox fees |
| Backend API | Python + FastAPI | Strong geodata libraries (pandas, shapely) for voyage and flag logic |
| Database | PostgreSQL + PostGIS | Stores positions and does distance / zone queries natively |
| Background jobs | Scheduled worker (e.g. cron or a task queue) | Refreshes positions of vessels I am watching |
| PDF report | Headless browser (Playwright) printing the report page | Report looks exactly like the screen |
| Secrets | `.env` file, never committed | API keys stay private |
| Hosting | One small cloud server or container host | Enough for internal use |

## Building it with Claude Code, step by step

Build in small steps: one prompt per step, run the tests, review the diff, commit, then move on.

- **Step 0 — Set up.** Install Claude Code, create an empty Git repository, save this brief as `docs/BRIEF.md`, run `/init` to create `CLAUDE.md` and add: read docs/BRIEF.md before any task; vessels are keyed on IMO number, never on name; all thresholds live in config/rules.yaml; API keys only in .env, never commit .env; every rule and every voyage function gets unit tests.
- **Step 1 — Plan before code.** Propose the folder structure, the database schema (vessels, identity history, positions, port calls, voyages, flags) and the API endpoints for the MVP.
- **Step 2 — Scaffold the project.** FastAPI backend, React + TypeScript frontend with MapLibre, docker-compose with PostgreSQL + PostGIS, health-check endpoint, README.
- **Step 3 — Data provider adapter.** Interface with `search_vessel(query)`, `get_track(imo, start, end)`, `get_vessels_near(lat, lon, radius, start, end)`. A MockProvider reading sample tracks, one real provider using the API key in .env. Cache every fetched position in PostGIS and only fetch periods we do not already have.
- **Step 4 — Vessel search.** `GET /vessels/search?q=` accepting name, IMO or MMSI, returning candidates with name, IMO, flag, type and size. Store name/flag/MMSI history per IMO.
- **Step 5 — Port calls and voyages.** Exactly as in the rules section, thresholds from config/rules.yaml. Unit tests on synthetic tracks: a normal two-port voyage, a long anchorage wait, a voyage with a gap.
- **Step 6 — The map screen.** Search bar on top, map on the left, voyage list on the right. One colour per voyage, current voyage dashed, port calls as dots with names, AIS gaps as dotted red segments.
- **Step 7 — Red-flag engine.** Each rule as its own module with tests. Each flag stores rule, severity, start/end time, coordinates and evidence positions. Sensitive zones from config/zones.geojson, sanctions from the official OFAC, EU and UK downloads, refreshed daily.
- **Step 8 — Voyage detail and flag panel.** Clicking a flag zooms the map to its location and time window.
- **Step 9 — PDF report.** "Export report" produces a PDF with vessel identity, the map, the voyage table and all flags with evidence, using Playwright.
- **Step 10 — Review, test and deploy.** Review against this brief, fix anything missing or wrong, security issues (keys, input validation) and slow queries. Test on 5–10 real vessels including at least one known case with AIS gaps. Deploy with a daily database backup.

**Checkpoints after every step:** tests pass, the developer reads the diff, the work is committed to Git. Never paste API keys into a prompt.

## Milestones and acceptance

| Milestone | Covers steps | Accepted when |
|---|---|---|
| M1 Foundations | 0–4 | I can search a vessel by name or IMO and pick the right ship; positions are cached |
| M2 Voyage map | 5–6 | 12 months of a real vessel shows as separate coloured voyages with correct ports and dates |
| M3 Red flags | 7–8 | All seven rules fire correctly on test tracks and on one known real case |
| M4 Report and go-live | 9–10 | PDF report exports; tool runs on the server with backups; tests pass |

## Open questions for the developer

- [ ] Which AIS provider do you recommend after trialling two, and what is the monthly cost at the volume I will give you?
- [ ] Does that provider's licence allow us to store positions and show them in our own tool?
- [ ] Is ship-to-ship detection affordable in the MVP, or should it move to phase 2?
- [ ] Time estimate per milestone and total.
