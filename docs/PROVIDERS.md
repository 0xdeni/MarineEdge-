# Data providers — what MarineEdge uses, what it costs, what to do

Free first, paid per ship. The only recurring cost is the server; paid AIS history is bought one ship at a time, when a ship matters, and kept for good. Every vendor sits behind one adapter (`backend/app/providers/base.py`), so a provider can be swapped without touching the rest of the code.

| # | Need | Source | Cost | Status | What the owner does |
|---|---|---|---|---|---|
| 0 | Live positions, recorded into our own history | **aisstream.io**: free websocket from coastal receivers, recorded by the `recorder` container | Free (one key, at most 3 connections, no redistribution) | **Built.** Provider `aisstream`; tables `ais_live`, `mmsi_map`, `mmsi_names`; coverage-aware gap rule; 10 tests | Sign in with GitHub at aisstream.io, create a key, paste it on the map screen (**Connect the live feed**) or in Profile › Data sources |
| 1 | A ship's *past* 12 months and open-sea (satellite) coverage | **Datalastic** first; Kpler / MarineTraffic as a second trial | Datalastic, as published when this was written (Oct 2026): Starter 20k credits a month, Growth 80k, Developer Pro unlimited, prices on request; a history query ≈ 5 credits, a basic lookup 1, a Pro query 3; hard monthly cap, no overage. Kpler: by contract | Datalastic adapter written (`datalastic.py`), field mapping to confirm on the first pull; Kpler adapter is a stub | Ask both for a trial. Paste the Datalastic key in Profile › Data sources; each ship page then offers **Get the last 12 months** (you confirm before credits are used) |
| 2 | Sanctions lists | OFAC SDN, EU and UK (FCDO) official downloads; OpenSanctions as an optional aggregator | Free; OpenSanctions needs a commercial licence for business use | **Built.** Parsers for all four, tested; downloaded daily (04:30 server time) and on demand (Profile › Sanctions lists › **Download the lists now**) | Nothing. Ask OpenSanctions for a quote only if you want its maritime dataset |
| 3 | Ports | 68 hand-placed regional ports (`config/ports.csv`); NGA World Port Index next | Free | Import script written (`scripts/import_wpi.py`), not yet run | Nothing |
| 4 | Second opinion on gaps and ship-to-ship meetings | **Global Fishing Watch** API v3: port visits, loitering, encounters, AIS-off events from satellite and terrestrial AIS | Free token; data CC BY-NC 4.0 (non-commercial) | **Built.** Token in Profile › Data sources; **Compare with Global Fishing Watch** on each ship page; never a primary source | Register at globalfishingwatch.org (research use), create a token, paste it. Ask GFW in writing before any paid use |
| 5 | Base map | **Our own:** MapLibre GL (vendored) with Natural Earth inside the app; OpenStreetMap detail (Protomaps extract) downloaded to the server | Free; no key, no third-party map service | **Built.** Detail download from Profile › Detailed maps | Optional: Profile › Detailed maps › Download |
| 6 | Hosting, domain, sign-in | One server with Docker and Caddy (HTTPS); `https://<ip>.sslip.io` until a domain exists | AWS Free-plan trial now (~$18 a month of credit, six months); Oracle Always Free, Google Cloud or Hetzner take the same setup file | **Live** since 24 Oct 2026 on AWS | Before the trial ends (late April 2027): move or upgrade. A domain whenever wanted |
| 7 | Ownership | Registered owner, manager, class and insurer from the paid provider's particulars when it has them; Equasis for manual checks | Free (Equasis registration) / paid | Shown on the ship page and in the report when the provider supplies it; otherwise the ship page links to the IMO in Equasis | Register an Equasis account for manual look-ups |

## First real pull (the day a paid key arrives)

In the app: Profile › Data sources › **Buy history for several ships** › three to five IMO numbers you know (one that went dark or called at a sanctioned port) › Buy. Each line reports the checks below; screenshot them for the developer.

With a terminal (developers): `docker compose exec api python -m app.cli first-pull <imo> <imo> …`

What the checks look for, in order:
1. The search returns the right IMO.
2. Positions are in the thousands for a working ship (hourly fixes over a year).
3. Draught is filled in. If it is always 0, the field mapping in `datalastic.py:_position` is wrong.
4. Port calls land on the right ports.
5. A second run buys nothing: `fetch_log` has exactly one row per ship and window.

Ship-to-ship detection on a paid provider costs one "vessels near this point" query (≈ 5 credits on Datalastic) per slow-drift window at sea. A ship that drifts often can have 20 such windows a year, so budget about 100 credits per risky ship. The rule caps these lookups at `sts.max_lookups_per_vessel` (12) per run. On the recorded free feed the partner search costs nothing but only sees ships our receivers heard.

## Sanctions download addresses

- OFAC SDN (CSV): `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV`; vessel rows carry `IMO 1234567` in the remarks.
- EU consolidated list (CSV): `https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList/content?token=dG9rZW4tMjAxNw`
- UK Sanctions List (FCDO, CSV): `https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.csv`; `UK_SANCTIONS_CSV_URL` in `.env` overrides it (`off` skips it).
- OpenSanctions maritime: `https://www.opensanctions.org/datasets/maritime/` (only with `OPENSANCTIONS=1` and a licence).

## Terms to keep

- Do not scrape MarineTraffic or VesselFinder websites; use their APIs under contract or not at all.
- aisstream.io: no redistribution of the raw feed. Showing positions inside your own tool is the intended use; confirm in writing before reselling anything built on it.
- Global Fishing Watch: non-commercial licence. A cross-check, never a primary source, and never in a paid product without their written permission.
- Paid history: confirm with each vendor, in writing, that positions may be stored and shown in an internal tool (the brief's open question).
