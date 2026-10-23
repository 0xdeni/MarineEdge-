# Free alternatives to the paid services — what is free, what it costs you instead, and what money still buys

Short version: **everything in MarineEdge can run at €0/month from day one.** The only thing a paid AIS plan adds is the *past* (positions from before you started recording) and *open-sea coverage* (satellite AIS). Both are bought per ship, only when a ship matters, and cached forever.

| Paid item in the brief | Free alternative | What you give up | Status |
|---|---|---|---|
| **AIS positions** (Datalastic / Kpler, ~€50–500+/mo) | **aisstream.io** — free live AIS websocket from a global network of coastal receivers; MarineEdge's `recorder` keeps the socket open for the Black Sea, Marmara, Aegean, Gulf, Hormuz, Oman and Arabian Sea boxes and stores every message in your own database. From that day on you have your own 12-month history, no credits, no per-query cost. | **No history before the day you start.** **No satellite coverage**: open sea beyond ~40–60 nm of a receiver (central Black Sea, Arabian Sea, Iranian waters) is dark. Free terms: no redistribution, one key, max 3 connections. | **Built.** Provider "aisstream.io (free)" in the app; `recorder` container; coverage-aware AIS-gap rule; 6 tests. |
| **Gap / STS cross-check** | **Global Fishing Watch API** — free token; GFW computes port visits, loitering, encounters and AIS-off events from *satellite + terrestrial* AIS for all large vessels. MarineEdge shows them beside its own flags with a **Cross-check** button. | Licence is **CC BY-NC 4.0 (non-commercial)** — fine for evaluation and research, ask GFW in writing before using it in a paid product. Field names unverified until the first live call. | **Built.** Token field in Profile › AIS provider; `/api/vessels/{imo}/crosscheck`. |
| **Server** (Hetzner CX22 ≈ €4–5/mo) | **Oracle Cloud Always Free** — 4 Arm cores / 24 GB RAM / 200 GB disk, forever free, more than enough. Same cloud-init paste; the installer opens ports 80/443 in Oracle's image firewall. | Oracle needs a card for identity, sometimes rejects sign-ups, and reclaims idle free instances; Hetzner is €4.5/mo of certainty. | Installer handles both. |
| **Domain + certificate** | `https://<ip-with-dashes>.sslip.io` — free hostname, Let's Encrypt cert via Caddy, zero setup. | URL is ugly; a real domain costs ~€10/yr whenever you want one. | Default since day one. |
| **Base map tiles** | **OpenFreeMap** vector tiles (no key, no quota) under MapLibre. | Nothing meaningful. | Default since day one. |
| **Sanctions lists** | Official OFAC SDN, EU consolidated list, UK sanctions list — all free downloads, refreshed nightly. | OpenSanctions (aggregator, paid for business) only adds convenience. | Done. |
| **Ports** | NGA World Port Index (free CSV) + the 68 hand-placed regional ports. | Nothing. | Importer written. |
| **Push notifications** | Web Push (VAPID) — free, no Apple developer account needed for a Home-Screen PWA on iOS 16.4+. | Nothing. | Done. |
| **Ownership data** | Equasis (free registration, manual lookups) | Not an API; no automated enrichment. | Owner registers when needed. |

## How the free AIS path behaves (so nobody is surprised)

1. **Day 0:** paste the aisstream key in the app. Within minutes "Recorded AIS" on the admin screen shows positions arriving (expect 1–3 M positions/day across both regions; ~0.5 GB/month in PostGIS with the indexes, pruned after 14 months).
2. **Week 1:** search works for every ship that broadcast its static data (name, IMO, call sign, destination, draught). Voyages exist from the first port call you recorded. Red flags are computed on what you have; the AIS-gap rule knows where your receivers can't hear (0.5° cells with < `coverage_min_fixes` fixes in 30 days) and labels gaps there **Info · outside receiver coverage** instead of Medium/High. Gaps longer than `coverage_max_hours` (72 h) are flagged regardless.
3. **Month 1–12:** history fills in; everything the brief asks for is there for ships that stayed in receiver range. For a ship you *must* fix completely (court case, counterparty check), switch the provider to Datalastic for one **first pull** of its 12 months — that single purchase is cached and the switch back costs nothing.
4. **What you never get for free:** what a ship did last year, and where it went when it was 200 nm offshore. Those two are exactly what Datalastic/Kpler sell; buy them per ship, not per month.

## Coverage honesty in the UI

- Admin screen: positions stored, ships seen, "recording since" date.
- Every AIS-gap flag line states the receiver coverage at the last position.
- The report keeps the sentence "Draught-based flags are indicators, not proof" and, on the free feed, prints the recording start date as the history start.

## Thresholds involved (config/rules.yaml)

```yaml
ais_gap:
  coverage_min_fixes: 50     # fewer fixes than this in a 0.5° cell over 30 days = no receiver there
  coverage_max_hours: 72     # gaps longer than this are flagged even without coverage
```

## Owner steps (iPhone only)

1. aisstream.io › **Sign in with GitHub** (free) › API keys › create one › copy.
2. In the app: Profile › AIS provider › **aisstream.io (free)** › paste › **Save key and switch**. The recorder picks the key up within a minute; "Recorded AIS" starts counting.
3. Optional cross-check: globalfishingwatch.org › API portal › register (free, state non-commercial/research use) › create token › paste in Profile › AIS provider › **Cross-check token**.
4. Optional free server: cloud.oracle.com › Always Free › Create instance › Ubuntu 24.04 · shape **VM.Standard.A1.Flex** (4 OCPU, 24 GB) · Advanced › **Cloud-init** paste (same file as Hetzner) · in the instance's VCN security list add ingress rules for TCP 80 and 443 · open `https://<ip-with-dashes>.sslip.io`.
