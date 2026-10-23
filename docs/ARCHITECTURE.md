# Architecture

```
phone / desktop PWA (frontend/public)
   │  ?source=mock  → core.js runs the whole pipeline in the browser on the generated fleet
   │  ?source=server → api.js fetches the same JSON shapes from the API
   ▼
FastAPI (backend/app/main.py)
   │ Service (service.py): search → identify → cached fetch → analyze → JSON
   ├─ providers/  one adapter per vendor; Protocol in base.py
   ├─ engine/     pure Python: clean → port calls → voyages → 7 rules → status
   ├─ store.py    MemoryStore (dev) | PostgresStore (PostGIS); fetch_log enforces "fetch once"
   ├─ sanctions/  daily refresh of OFAC / EU / UK into the sanctions table
   └─ reports/    Jinja2 HTML → Playwright PDF
config/           rules.yaml · zones.geojson · ports.csv · areas.json
```

**Engine invariants.** `analyze(vessel, raw_track, ref, rules, now)` is deterministic and side-effect free. Port calls are detected before rules (rules need `in_port`), voyages are split after rules (jump fixes are excluded from distances), and every flag is attached to the voyage whose time window contains it; vessel-level flags (sanctions, identity) stay unattached.

**Cost control.** `Service.track()` asks `store.covered(imo, window)` first; the provider is called only for an uncovered window and the result is written with a `fetch_log` row carrying the credit estimate. STS partner lookups are the second paid call type; cap them per vessel before enabling on a contract provider.

**Frontend parity.** `service.analysis_json()` mirrors the object `core.js` builds (`track`, `portCalls`, `voyages`, `flags`, `sev`, `status`, `stats`), and `api.js:hydrate()` restores the cross-references (voyage ↔ flags ↔ port calls). Screens never know which source filled the object.

**What changes for M2b.** MapLibre GL with OpenFreeMap tiles as the base layer; the canvas chart becomes an overlay for voyages, flags and the live marker (it already renders in its own layer).

## Free data path (added 23 Oct 2026)

```
aisstream.io websocket ──► app/recorder.py (container `recorder`) ──► ais_live, mmsi_map (PostGIS)
                                                                        │
                       OwnAISProvider (app/providers/aisstream.py) ◄────┘   same Protocol as Datalastic/Kpler
                              │  get_track / search / vessels_near / vessels_in_area / get_static / coverage()
                              ▼
                       Service.analysis() ─► engine.analyze(..., coverage=provider.coverage)
                                                 └─ rule_ais_gap: gap in a cell with < coverage_min_fixes fixes → Info
Global Fishing Watch API v3 (app/providers/gfw.py) ─► /api/vessels/{imo}/crosscheck ─► "Cross-check" section (second opinion only)
```

Positions are keyed by MMSI on arrival (that is what AIS transmits) and get their IMO from the ship's static broadcast; `live_backfill_imo` links earlier rows once the MMSI→IMO pair is known. Several MMSIs for one IMO become MMSI-history rows on the vessel (identity-change rule).

