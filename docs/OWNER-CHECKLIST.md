# Owner checklist — everything you need to do, from an iPhone

No terminal is needed for any step. Items are in the order that unblocks the most. Everything not listed here is engineering and either done or in progress without you.

## A. Get a server running (15 minutes, one evening)

- [ ] **A1. Hetzner account** (or DigitalOcean/Vultr; Hetzner is cheapest and has an iPhone app). Sign up at hetzner.com › Cloud, add a payment method. **Free option:** Oracle Cloud "Always Free" (cloud.oracle.com; needs a card for identity only) — same paste, shape VM.Standard.A1.Flex 4 OCPU/24 GB, then add ingress rules for TCP 80 and 443 in the instance's VCN security list. If Oracle rejects the sign-up (it happens), Hetzner is €4.5/month.
- [ ] **A2. Copy the setup file.** In Safari open `github.com/0xdeni/MarineEdge-/blob/main/deploy/cloud-init.yaml`, tap **Raw**, select all, copy.
- [ ] **A3. Create the server.** Hetzner app › New server: location Helsinki or Falkenstein · image **Ubuntu 24.04** · type **CX22** (2 vCPU, 4 GB) · scroll to **Cloud config / user data** · paste · edit the line `ADMIN_TOKEN=` to a long passphrase of your choice (this becomes your sign-in password; keep it in your password manager) · leave `DOMAIN=` empty · Create.
- [ ] **A4. Open the app.** Wait 5–8 minutes, then open `https://<server IP with dashes>.sslip.io` (IP 95.217.12.34 → `https://95-217-12-34.sslip.io`). Sign in with any email and your ADMIN_TOKEN. Tap Share › **Add to Home Screen** so it runs as an app and can receive push.
  If the page does not load after 10 minutes, send me the server IP and I will tell you what to check in the Hetzner console.

## B. Connect real AIS data (same evening)

Two routes; do B0 tonight regardless, it costs nothing and history starts the moment it runs. Details in `docs/FREE-STACK.md`.

- [ ] **B0. Free live AIS (aisstream.io).** In Safari open aisstream.io › **Sign in with GitHub** (create a free GitHub account if you have none) › API keys › create › copy. In the app: Profile › AIS provider › **aisstream.io (free)** › paste › **Save key and switch**. Within a minute the **Recorded AIS** box on that screen starts counting positions. From today on you own your history; nothing is bought. Limits: no positions from before today, no open-sea (satellite) coverage.
- [ ] **B0b. Free cross-check (optional).** globalfishingwatch.org › Our APIs › register (free; say research/non-commercial) › create a token › paste in Profile › AIS provider › **Cross-check token**. Every vessel then gets a "Cross-check with Global Fishing Watch" button (their satellite-based port visits, loitering, encounters, AIS-off events). Their licence is non-commercial — fine for evaluation; ask them in writing before paid use.
- [ ] **B1. Datalastic trial** (paid; only needed for ships whose *past* 12 months you must see, or for open-sea coverage). datalastic.com › sign up (trial or Starter plan). The API key appears in their dashboard; copy it.
- [ ] **B2. Paste the key in the app.** Profile › AIS provider › tap **Datalastic** › paste in **Key** › **Save key and switch** › **Test connection**. The result line shows matches and credits used. Send me a screenshot of that line.
- [ ] **B3. First pull.** Still on that screen, type 3–5 IMO numbers of ships you care about (one that you know went dark or called a sanctioned port) and tap **Run first pull**. Each ship shows five checks. Screenshot the results to me. This is the M1 acceptance test; if any check fails I fix the field mapping and the server updates itself within 10 minutes.
- [ ] **B4. Kpler/MarineTraffic trial** (second provider, for comparison). kpler.com › MarineTraffic API › contact sales. Ask in writing: (1) price for 12 months of hourly history per IMO and for "vessels in area" polling of five boxes every 5 minutes; (2) whether historical "vessels within 500 m of a point" queries exist and what they cost; (3) confirmation you may store positions and show them in an internal tool. Forward the answers to me.

## C. Daily use (from now on)

- [ ] **C1. Watch ships.** Open a vessel › **Watch**. The server re-checks watched ships every 30 minutes; new High flags become alerts.
- [ ] **C2. Push notifications.** Profile › Notifications › **Enable push notifications on this device** (needs the Home Screen install, iOS 16.4+).
- [ ] **C3. Thresholds.** After a week of real data tell me which flags were noisy or missing; you can also change any number yourself in Profile › Rules & thresholds (the fleet re-runs immediately).

## D. Before wider rollout

- [ ] **D0. Unblock GitHub Actions (3 taps).** Actions is on, but every run dies before it starts ("startup_failure"), even a one-line test workflow, so the cause is your account or repo settings, not the code. In Safari: github.com/0xdeni/MarineEdge- › **Actions** › tap the top run and read the banner:
  - "…recent account payments have failed or your spending limit needs to be increased" → github.com/settings/billing › **Spending limits** › Actions: allow a small amount (e.g. $5) or fix the card. Private repos get 2,000 free minutes a month, so the bill stays $0; the limit just has to exist.
  - "…is not allowed to be used in…" → repo **Settings › Actions › General › Allow all actions and reusable workflows**.
  - "Your account has been flagged" → tap the support link in the banner (new accounts sometimes get this automatically).
  - Alternative that avoids all three: make the repo **public** (Settings › General › Danger zone) — Actions is then free and unrestricted. Nothing secret is in the repo (keys live only on the server), but it is your call.
  Once fixed, every push builds the Docker images, boots the whole stack and runs 38 tests against a real PostGIS: a green tick means a server install will work; a red cross I see and fix without you.

- [ ] **D1. Domain.** Buy or pick a subdomain (tracker.yourcompany.com), add an A record to the server IP, then tell me; the server switches to it with one setting change.
- [ ] **D2. Company login.** Google Workspace or Microsoft? I add SSO in front of the app; until then each user gets a token (ask me, I add it).
- [ ] **D3. UK sanctions link.** Once: open gov.uk/government/publications/the-uk-sanctions-list, copy the current CSV link, send it to me (the link changes with each publication; I will automate it).
- [ ] **D4. OpenSanctions** (optional aggregator): needs a commercial licence for business use; one email to them for a quote if you want it.
- [ ] **D5. Backups off-site.** Create a bucket (Hetzner Object Storage, Backblaze B2 or S3) and send me the access keys through your password manager, not chat; nightly dumps already run on the server.
- [ ] **D6. Zones.** Confirm the five sensitive zones (Crimea, occupied Azov coast, Syria, Iran coastal waters, North Korea) or name others (Venezuela, Russian Baltic ports…).

## Things I keep doing without you

World Port Index import, Kpler adapter when their answers arrive, SSO once you pick a provider, MapLibre polish after the first real-phone look, retuning on your feedback, and keeping STATUS.md current.
