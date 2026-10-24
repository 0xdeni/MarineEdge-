# Owner checklist — everything you need to do, from an iPhone

No terminal is needed for any step. Items are in the order that unblocks the most. Everything not listed here is engineering and either done or in progress without you.

## A. The server

- [x] **A0. Repository public** (23 Oct) — a fresh server downloads the code without a token.
- [x] **A1. Server running** on an AWS Free-plan trial since 24 Oct: `https://44-197-249-76.sslip.io`. Click path for a new one (AWS, Google Cloud, Oracle) in `docs/FREE-STACK.md` § Owner steps 4–6 and `docs/DEPLOY.md`.
- [x] **A2. The setup file** with your admin password (`ADMIN_TOKEN=`) — keep that password in your password manager: it is the **server admin password** that creates the first account.
- [ ] **A3. Your account (once; 1.0 is live since 24 Oct).** Open the address in Safari › **Get started** › swipe through the three pages › **Create account** › your name, email, a password of your own, and the server admin password › **Create owner account**. Then Share › **Add to Home Screen**, and open MarineEdge from the Home Screen from now on.
- [ ] **A4. Before the trial ends** (6 months after the AWS sign-up): we move to the next server, or you upgrade the AWS account to paid (~$18/month). The move will be ready in the app well before then.

## B. Real ship data

- [ ] **B0. Free live AIS (aisstream.io) — do it tonight.** In Safari open aisstream.io › **Sign in with GitHub** (a free GitHub account is enough) › API keys › create › copy. In MarineEdge the map screen shows **Connect the live feed**: paste the key › **Start recording**. Within a minute ships appear on the map; Profile › Data sources shows "Recording since …" or, if aisstream refuses the key, why. Nothing is bought; no positions from before today; coastal receivers only.
- [ ] **B0b. Cross-check (optional, licence first).** Global Fishing Watch's free terms do not cover internal use that supports a business, and a trading desk is one. Email them through the commercial-use page (globalfishingwatch.org › FAQs › "Can I use Global Fishing Watch APIs for commercial purposes?") and ask for a licence for an internal cross-check. Once they agree: Our APIs › register › create a token › Profile › Data sources › **Global Fishing Watch** › paste › Save. Every ship page then has "Compare with Global Fishing Watch".
- [ ] **B1. Datalastic trial** (paid; only for ships whose *past* 12 months you must see, or open-sea coverage). datalastic.com › sign up › copy the API key.
- [ ] **B2. Paste it:** Profile › Data sources › **Datalastic** › paste › Save. Ship pages now show **Get the last 12 months** (you confirm before any credits are used).
- [ ] **B3. First pull (the M1/M2 test).** Profile › Data sources › **Buy history for several ships** › 3–5 IMO numbers you know (one that went dark or called a sanctioned port) › Buy. Screenshot the result lines to me; if a check fails I fix the mapping and the server updates itself within 10 minutes.
- [ ] **B4. Kpler/MarineTraffic trial** (comparison). kpler.com › MarineTraffic API › contact sales. Ask in writing: (1) price for 12 months of hourly history per IMO and "vessels in area" polling of five boxes every 5 minutes; (2) whether historical "vessels within 500 m of a point" queries exist and their cost; (3) that you may store positions in an internal tool. Forward the answers.

## C. Daily use

- [ ] **C1. Watch ships:** the star on a ship's page. The server re-checks watched ships every 30 minutes; new red flags appear in Alerts (the bell).
- [ ] **C2. Notifications:** Profile › Notifications › **On this device** (needs the Home Screen install, iOS 16.4+). Choose High only, or High and Medium. "Send a test notification" proves it.
- [ ] **C3. Thresholds:** after a week of real data, tell me which flags were noisy or missing — or change any number yourself in Profile › Red-flag rules (back to the defaults with one tap).
- [ ] **C4. Your team:** Profile › Team › **Invite someone** › their email (optional) and role › Share the link (WhatsApp, Mail…). It works once, for seven days. Analysts check ships, watch and write notes; admins also manage the team and the server.

## D. When you're ready

- [ ] **D1. Email** (so password reset codes and invites go out by themselves): Profile › Email › your SMTP server (Gmail or Microsoft 365 need an app password) › Save › **Send a test email to me**. Until then, reset a teammate's password with Team › their name › **Make a password reset link**.
- [ ] **D2. Detailed maps:** Profile › Detailed maps › pick the detail › Download (5–30 minutes on the server, 0.5–4 GB). Harbours and coastlines then show up close; without it the app uses its built-in Natural Earth maps.
- [ ] **D3. Domain:** buy or pick a subdomain (tracker.yourcompany.com), add an A record to the server's IP, tell me; one setting change moves the server to it.
- [x] **D4. UK sanctions list:** automatic since 1.0 (the FCDO list has a fixed address now). Profile › Sanctions lists shows the count per list after each daily download.
- [ ] **D5. Backups off-site:** a bucket (Hetzner Object Storage, Backblaze B2 or S3); send me the access keys through your password manager, not chat. Nightly dumps already run on the server's own disk.
- [ ] **D6. Zones:** confirm the five sensitive zones (Crimea, occupied Azov coast, Syria, Iran coastal waters, North Korea) or name others; you can switch each one on or off in Profile › Sensitive zones. **Syria first:** the US ended its Syria sanctions programme in 2025 and the EU and UK lifted most economic sanctions, so keep that zone only if your policy still treats Syria as high-risk (`docs/METHODOLOGY.md` has the details).
- [ ] **D7. OpenSanctions** (optional aggregator): needs a commercial licence for business use; one email for a quote if you want it.

## Things I keep doing without you

World Port Index import, the Datalastic mapping check on your first pull, Kpler adapter when their answers arrive, export/import before the trial ends, retuning on your feedback, and keeping STATUS.md current.
