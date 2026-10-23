# Owner checklist — the parts only Deni can do

Everything not on this list is engineering and is either done or can be done without you. Items are in the order that unblocks the most.

## A. This week

- [ ] **A1. Datalastic trial.** Sign up at datalastic.com, pick the trial/Starter plan. Paste the key into `.env` on the server (or your laptop): `DATALASTIC_API_KEY=…`, `VVT_PROVIDER=datalastic`. Never paste it into chat.
  Then run `cd backend && python -m app.cli first-pull <IMO> <IMO> <IMO>` and send me the output (it has no secrets). That is the M1 acceptance test and the moment we find out whether the field mapping is right.
- [ ] **A2. Kpler/MarineTraffic trial.** Sales form at kpler.com (MarineTraffic API). Ask in writing:
  1. price for 12 months of hourly history per IMO, and for "vessels in area" polling of five boxes every 5 minutes;
  2. whether historical "vessels within 500 m of a point" queries are available and what they cost (this is STS detection);
  3. confirmation that we may store positions and display them in an internal tool.
  Forward the answers; I fill in `backend/app/providers/kpler.py` the same day.
- [ ] **A3. Real vessels.** Send 5–10 IMO numbers you care about, including at least one ship you already know went dark or called a sanctioned port. One known case proves the seven rules on real data (M3 acceptance).
- [ ] **A4. Hosting.** Create one VPS (Hetzner CX22 / DigitalOcean 4 GB / Fly) and a domain or subdomain (e.g. tracker.yourcompany.com) with an A record to it. Give me SSH access or run `docs/DEPLOY.md` yourself (30 minutes, copy-paste).

## B. Before go-live

- [ ] **B1. Identity provider.** Tell me whether logins come from Google Workspace or Microsoft Entra, and who the first users are (emails). Until then the app uses API tokens from `.env` (`API_TOKENS=name:token,…`); generate one with `python -c "import secrets;print(secrets.token_urlsafe(32))"`.
- [ ] **B2. Sanctions sources.** Nothing for OFAC and EU (official downloads, automated). For UK, open https://www.gov.uk/government/publications/the-uk-sanctions-list once, copy the current CSV link into `UK_SANCTIONS_CSV_URL` in `.env` (the link changes with each publication; a small job can track it later). Decide whether you want OpenSanctions as an aggregator: it needs a commercial licence for business use (ask them for a quote; one email).
- [ ] **B3. Global Fishing Watch.** Create an API account at globalfishingwatch.org and ask in writing whether a trading desk's internal use is covered by their non-commercial terms. If not, we skip the cross-check; the tool works without it.
- [ ] **B4. Off-site backups.** Pick a bucket (Hetzner Object Storage, Backblaze B2, S3) and give me the rclone credentials, or set `RCLONE_REMOTE` yourself. Nightly dumps already run locally once the cron is installed.
- [ ] **B5. Sensitive zones.** Confirm the five zones (Crimea, occupied Azov coast, Syria, Iran coastal waters, North Korea) and tell me if you want others (e.g. Venezuela, Russian Baltic ports). Zones are polygons in `config/zones.geojson`; I draw them, you approve.
- [ ] **B6. Thresholds.** The brief's starting numbers are in `config/rules.yaml` and editable in the app's Settings › Rules. After the first real pulls, tell me which flags felt noisy or missing and I retune.

## C. Nice to have, no rush

- [ ] **C1. Equasis account** (free) for manual ownership checks while we decide on a paid registry.
- [ ] **C2. Website.** The landing page is on the design canvas (link in STATUS.md). Tell me the tagline/positioning you want and whether it goes live on the same domain; it needs a hosting target and a form backend (CRM or email).
- [ ] **C3. Name and icon.** "MarineEdge" is now the product name across app, repo and reports. If you want a wordmark/logo beyond the current mark, say so.
- [ ] **C4. Users and roles.** Who should see what: analysts (everything), viewers (reports only), admin (settings). The schema has a `users.role` column ready.

## What I keep doing without you

MapLibre polish, React port if a second developer needs it, World Port Index import (all ports, not just the 68 regional ones), background job that refreshes watched vessels, push notifications for the PWA, tests on the real tracks you send, and the Kpler adapter once their answers arrive.
