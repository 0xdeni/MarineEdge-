# Free alternatives to the paid services — what is free, what it costs you instead, and what money still buys

Short version: **everything in MarineEdge can run at €0/month from day one.** The only thing a paid AIS plan adds is the *past* (positions from before you started recording) and *open-sea coverage* (satellite AIS). Both are bought per ship, only when a ship matters, and cached forever.

| Paid item in the brief | Free alternative | What you give up | Status |
|---|---|---|---|
| **AIS positions** (Datalastic / Kpler, ~€50–500+/mo) | **aisstream.io** — free live AIS websocket from a global network of coastal receivers; MarineEdge's `recorder` keeps the socket open for the Black Sea, Marmara, Aegean, Gulf, Hormuz, Oman and Arabian Sea boxes and stores every message in your own database. From that day on you have your own 12-month history, no credits, no per-query cost. | **No history before the day you start.** **No satellite coverage**: open sea beyond ~40–60 nm of a receiver (central Black Sea, Arabian Sea, Iranian waters) is dark. Free terms: no redistribution, one key, max 3 connections. | **Built.** Provider "aisstream.io (free)" in the app; `recorder` container; coverage-aware AIS-gap rule; 6 tests. |
| **Gap / STS cross-check** | **Global Fishing Watch API** — free token; GFW computes port visits, loitering, encounters and AIS-off events from *satellite + terrestrial* AIS for all large vessels. MarineEdge shows them beside its own flags with a **Cross-check** button. | Licence is **CC BY-NC 4.0 (non-commercial)** — fine for evaluation and research, ask GFW in writing before using it in a paid product. Field names unverified until the first live call. | **Built.** Token field in Profile › Data sources; `/api/vessels/{imo}/crosscheck`. |
| **Server** (Hetzner CX22 ≈ €4.5/mo) | **Oracle Cloud Always Free** — 2 Arm cores / 12 GB RAM / 200 GB disk, forever (halved from 4/24 in June 2026; a 4/24 instance on a free account can be stopped). **Or a trial:** AWS's new-account Free plan ($100–200 credit, 6 months, cannot charge the card) on a t4g.small (2 GB), or Google Cloud's $300 / 90 days on any size. Same cloud-init paste everywhere; the installer adapts to Arm, to 1–2 GB machines (swap, one API worker) and opens Oracle's image firewall. | Oracle sometimes refuses sign-ups, often has no free Arm capacity, and may reclaim instances that look idle for 7 days. Trials end: AWS closes the account after 6 months unless upgraded, Google stops the VM after 90 days — the database then has to move. Google's "always free" e2-micro is not quite free (its public IPv4 is billed, ~$3.65/mo) and has 1 GB RAM. | Installer handles all of them (step-by-step below). |
| **Domain + certificate** | `https://<ip-with-dashes>.sslip.io` — free hostname, Let's Encrypt cert via Caddy, zero setup. | URL is ugly; a real domain costs ~€10/yr whenever you want one. | Default since day one. |
| **Base map tiles** | **OpenFreeMap** vector tiles (no key, no quota) under MapLibre. | Nothing meaningful. | Default since day one. |
| **Sanctions lists** | Official OFAC SDN, EU consolidated list, UK sanctions list — all free downloads, refreshed nightly. | OpenSanctions (aggregator, paid for business) only adds convenience. | Done. |
| **Ports** | NGA World Port Index (free CSV) + the 68 hand-placed regional ports. | Nothing. | Importer written. |
| **Push notifications** | Web Push (VAPID) — free, no Apple developer account needed for a Home-Screen PWA on iOS 16.4+. | Nothing. | Done. |
| **Ownership data** | Equasis (free registration, manual lookups) | Not an API; no automated enrichment. | Owner registers when needed. |

## How the free AIS path behaves (so nobody is surprised)

1. **Day 0:** paste the aisstream key in the app. Within a minute "Recorded AIS" on the admin screen shows positions arriving. A ship under way reports every 2–10 s and at anchor every 3 min, so the recorder samples (`rules.yaml › live`): one stored fix per ship per 10 min under way and per 30 min stopped, plus an extra fix on every sharp turn, departure or arrival (with hysteresis, so an anchored ship swinging on its chain is not a departure) — about 4–5 stored fixes per ship-hour. Only cargo ships and tankers are kept once their type is known (ferries, fishing boats, tugs and yachts are dropped — but still counted for receiver coverage). Full resolution for 30 days, then one fix per 30 minutes, deleted after 14 months. With the slim table of migration 004 (~130 bytes per fix, indexes included) that is roughly **1 GB a month at full resolution and 0.5 GB a month once thinned for every 3,000 ships in receiver range — about 7–12 GB in the first year**. The admin screen shows disk free and database size; below 3 GB free the recorder pauses new positions by itself, so a full disk can never take the database down.
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
live:
  moving_interval_s: 600     # one stored fix per ship per 10 min under way...
  stationary_interval_s: 1800  # ...and per 30 min at anchor or moored
  turn_deg: 25               # plus a fix on a turn of 25° or more (above 3 kn), and on every departure or arrival
  keep_types: ["70-89"]      # cargo + tanker once the type is known; unknown types kept
  full_res_days: 30          # then thinned to one fix per thin_minutes by the daily prune-live job
  thin_minutes: 30
  retention_months: 14
  min_free_gb: 3             # positions pause below this much free disk
```

## Owner steps (iPhone only)

1. aisstream.io › **Sign in with GitHub** (free) › API keys › create one › copy.
2. In the app: the map screen's **Connect the live feed** card (or Profile › Data sources › aisstream.io) › paste › **Start recording** / **Save**. The recorder picks the key up within a minute; Data sources shows "Recording since …" or why the key was refused.
3. Optional cross-check: globalfishingwatch.org › API portal › register (free, state non-commercial/research use) › create token › paste in Profile › Data sources › **Global Fishing Watch**.
4. **Server on a free trial — AWS (recommended when Oracle refuses you): 6 months, cannot charge your card.**
   1. aws.amazon.com › **Create a free account** · email + account name › verify the code › root password › choose the **Free plan** (not Paid) › contact info (Personal) › card (identity only; the Free plan cannot bill it) › SMS check › Basic support. Activation takes minutes, sometimes a few hours (you get an email).
   2. Console (Safari; if a screen is cramped use **aA › Request Desktop Website**) › region menu top right › **US East (N. Virginia)** — the cheapest region, so the credit lasts the full 6 months (São Paulo works too but uses the credit ~1.5× faster).
   3. **EC2 › Launch instance**: Name `marineedge` · Application and OS image: **Ubuntu** › *Ubuntu Server 24.04 LTS* › Architecture **64-bit (Arm)** · Instance type **t4g.small** (Free tier eligible: 2 cores, 2 GB) · Key pair: **Proceed without a key pair** · Network settings: tick **Allow HTTPS traffic from the internet** and **Allow HTTP traffic from the internet** (SSH can be unticked) · Configure storage: **30** GiB **gp3** (the default 8 GB is too small) · **Advanced details › User data**: paste the cloud-init file · **Launch instance**.
   4. Instances › your instance › copy **Public IPv4 address** → after 15–20 minutes (a 2 GB machine builds slowly the first time; the installer adds swap and uses one API worker) open `https://<ip-with-dashes>.sslip.io`.
   5. Credit: $100 on sign-up covers about 5½ months of this machine (~$18/month including disk and IP). The console home has an **Earn credits** card with small tasks worth $20 each — **Set up a cost budget** takes a minute and makes the 6 months certain.
   6. Before month 6 the database moves to the next server (backup and restore are built; a one-tap move from the app is on the engineering list), or the AWS account is upgraded to paid (~$18/month).
5. **Alternative trial — Google Cloud: $300 for 90 days, any size.** console.cloud.google.com › **Start free** › card (identity only) › Compute Engine › VM instances › **Create instance**: region **southamerica-east1 (São Paulo)** · machine **e2-medium** (2 cores, 4 GB) · OS and storage › Change › **Ubuntu 24.04 LTS (x86/64)**, **30 GB** · Networking › Firewall: tick **Allow HTTP traffic** and **Allow HTTPS traffic** · Advanced › Metadata › **Add item**: key `user-data`, value = the cloud-init file · Create. About $45/month of the $300, so 90 days fit easily. At day 90 the VM stops; 30 days of grace to upgrade or move.
6. Free forever, when it accepts you — **Oracle Cloud Always Free** (2 Arm cores, 12 GB RAM, up to 200 GB disk):
   1. cloud.oracle.com › **Start for free**. A card is required for identity and is not charged on Always Free resources; a phone number is verified. Pick the **home region** with care — it cannot be changed, and the free Arm shape is often "out of capacity" in the busiest regions (Frankfurt, Ashburn). São Paulo, Marseille, Stockholm or Jerusalem tend to have room. Oracle refuses some sign-ups without a reason; there is no appeal worth the time — use AWS or Google above.
   2. Menu › Compute › Instances › **Create instance** · name `marineedge` · Image **Canonical Ubuntu 24.04** · Shape › **Ampere** › **VM.Standard.A1.Flex** → **2 OCPUs, 12 GB** memory (the Always Free maximum since June 2026; more can get the instance stopped on a free account) · Networking: create a new VCN with a public subnet, **assign a public IPv4 address** · SSH keys: **No SSH keys** · Boot volume: **Specify a custom boot volume size → 100 GB** (free up to 200 GB total) · **Show advanced options › Management › Initialization script › Paste cloud-init script** → paste the same file · Create.
   3. If it says *Out of host capacity*: try again in a few hours (capacity frees up at odd hours) or with 1 OCPU / 6 GB.
   4. Open the instance › **Primary VNIC › Subnet › Default Security List › Add Ingress Rules**: source `0.0.0.0/0`, protocol TCP, destination port `80`; repeat for `443`. (The installer opens the same ports inside the server's own firewall.)
   5. Copy the **Public IP** → after about 10 minutes open `https://<ip-with-dashes>.sslip.io`. The installer picks the Arm build of PostGIS automatically.
   6. Oracle may reclaim Always Free instances that look idle for 7 days (CPU, network and memory all under 20%). The recorder alone may not keep a 12 GB box above that; Postgres is given a quarter of the RAM as cache, which fills as history grows. If Oracle emails an idle warning, tell me.
