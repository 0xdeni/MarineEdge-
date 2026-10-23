# Providers — what we need and what to do

One paid feed, several free ones. Only the AIS feed is a recurring cost.

| # | Need | Candidate | Cost | Status | Action (Deni) |
|---|---|---|---|---|---|
| 0 | AIS live positions, recorded into our own history | **aisstream.io** (free websocket, coastal receivers) recorded by the `recorder` container | Free (one key, ≤3 connections, no redistribution) | **Built**: provider `aisstream` in the app, `ais_live`/`mmsi_map` tables, coverage-aware gap rule | Sign in with GitHub at aisstream.io, create a key, paste it in Profile › AIS provider › aisstream.io (free). |
| 1 | AIS *past* history + satellite coverage, per ship | **Datalastic** (first) · Kpler/MarineTraffic (second trial) | Datalastic: Starter 20k credits/mo, Growth 80k, Developer Pro unlimited; prices on request; history ≈5 credits/query, basic lookup 1, Pro 3; hard cap, no overage. Kpler: contract. | Adapter written (`datalastic.py`), Kpler stub | Request both trials. Ask each: price of 12 months of history per IMO; cost of polling the five regions every 5 min; written OK to store positions and show them in an internal tool. |
| 2 | Sanctions | OFAC SDN + EU + UK official downloads; OpenSanctions as aggregator | Free; OpenSanctions needs a commercial licence for business use | OFAC parser done and tested; EU/UK parsers drafted | Nothing for the official lists. Ask OpenSanctions for a quote if you want their maritime dataset (Vessel entities keyed by IMO, flags, owners). |
| 3 | Ports | NGA World Port Index | Free | 68 regional ports in `config/ports.csv`; WPI import script to add | Nothing. |
| 4 | Gap / STS cross-check | Global Fishing Watch API v3 (events: port visits, loitering, encounters, AIS-off) | Free token; data CC BY-NC 4.0 (non-commercial) | **Built**: token in Profile › AIS provider, "Cross-check" button on each vessel, `/api/vessels/{imo}/crosscheck`; field names unverified until the first live call | Register at globalfishingwatch.org (research use), create a token, paste it in the app; ask GFW in writing before any paid use. |
| 5 | Base map | MapLibre + OpenFreeMap (or MapTiler) | Free / low | Canvas schematic now | Nothing, unless you want MapTiler styling (key). |
| 6 | Hosting, domain, SSO | One VPS + Caddy; Google Workspace or Microsoft Entra | Hetzner CX22 ≈ €4.5/mo, or **Oracle Always Free €0** (installer opens its firewall); sslip.io hostname free | Compose + cloud-init written | Pick the host, tell me the domain and the identity provider. |
| 7 | Ownership (optional) | Equasis (manual), later a paid registry | Free / paid | Not wired | Register an Equasis account. |

## First real pull (the day a key arrives)

```
cp .env.example .env            # add DATALASTIC_API_KEY, VVT_PROVIDER=datalastic
cd backend && python -c "from app.service import Service; s=Service(); print(s.search('<name>')); a=s.analysis(<imo>); print(a.stats, a.sev)"
```

Check, in this order: the search returns the right IMO; `stats.raw` is in the thousands for a working ship (hourly fixes); draught is populated (if always 0, the field mapping in `datalastic.py:_position` is wrong); port calls land on the right ports; `fetch_log` has exactly one row per vessel after a second run. Then decide STS: one `vessel_history_inradius` call per slow-drift window at ~5 credits each; a dark tanker can have 20 windows a year, so budget ~100 credits per risky vessel or move STS to phase 2.

## Sanctions download URLs

- OFAC SDN CSV: `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV` (vessel rows carry `IMO 1234567` in remarks)
- EU consolidated list (CSV): `https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList/content?token=dG9rZW4tMjAxNw`
- UK consolidated list: `https://www.gov.uk/government/publications/the-uk-sanctions-list` (CSV/ODS link on the page)
- OpenSanctions maritime: `https://www.opensanctions.org/datasets/maritime/`
