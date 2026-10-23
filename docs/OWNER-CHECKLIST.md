# Owner checklist — everything you need to do, from an iPhone

No terminal is needed for any step. Items are in the order that unblocks the most. Everything not listed here is engineering and either done or in progress without you.

## A. Get a server running (15 minutes, one evening)

- [ ] **A1. Hetzner account** (or DigitalOcean/Vultr; Hetzner is cheapest and has an iPhone app). Sign up at hetzner.com › Cloud, add a payment method.
- [ ] **A2. Copy the setup file.** In Safari open `github.com/0xdeni/MarineEdge-/blob/main/deploy/cloud-init.yaml`, tap **Raw**, select all, copy.
- [ ] **A3. Create the server.** Hetzner app › New server: location Helsinki or Falkenstein · image **Ubuntu 24.04** · type **CX22** (2 vCPU, 4 GB) · scroll to **Cloud config / user data** · paste · edit the line `ADMIN_TOKEN=` to a long passphrase of your choice (this becomes your sign-in password; keep it in your password manager) · leave `DOMAIN=` empty · Create.
- [ ] **A4. Open the app.** Wait 5–8 minutes, then open `https://<server IP with dashes>.sslip.io` (IP 95.217.12.34 → `https://95-217-12-34.sslip.io`). Sign in with any email and your ADMIN_TOKEN. Tap Share › **Add to Home Screen** so it runs as an app and can receive push.
  If the page does not load after 10 minutes, send me the server IP and I will tell you what to check in the Hetzner console.

## B. Connect real AIS data (same evening)

- [ ] **B1. Datalastic trial.** datalastic.com › sign up (trial or Starter plan). The API key appears in their dashboard; copy it.
- [ ] **B2. Paste the key in the app.** Profile › AIS provider › tap **Datalastic** › paste in **Key** › **Save key and switch** › **Test connection**. The result line shows matches and credits used. Send me a screenshot of that line.
- [ ] **B3. First pull.** Still on that screen, type 3–5 IMO numbers of ships you care about (one that you know went dark or called a sanctioned port) and tap **Run first pull**. Each ship shows five checks. Screenshot the results to me. This is the M1 acceptance test; if any check fails I fix the field mapping and the server updates itself within 10 minutes.
- [ ] **B4. Kpler/MarineTraffic trial** (second provider, for comparison). kpler.com › MarineTraffic API › contact sales. Ask in writing: (1) price for 12 months of hourly history per IMO and for "vessels in area" polling of five boxes every 5 minutes; (2) whether historical "vessels within 500 m of a point" queries exist and what they cost; (3) confirmation you may store positions and show them in an internal tool. Forward the answers to me.

## C. Daily use (from now on)

- [ ] **C1. Watch ships.** Open a vessel › **Watch**. The server re-checks watched ships every 30 minutes; new High flags become alerts.
- [ ] **C2. Push notifications.** Profile › Notifications › **Enable push notifications on this device** (needs the Home Screen install, iOS 16.4+).
- [ ] **C3. Thresholds.** After a week of real data tell me which flags were noisy or missing; you can also change any number yourself in Profile › Rules & thresholds (the fleet re-runs immediately).

## D. Before wider rollout

- [ ] **D1. Domain.** Buy or pick a subdomain (tracker.yourcompany.com), add an A record to the server IP, then tell me; the server switches to it with one setting change.
- [ ] **D2. Company login.** Google Workspace or Microsoft? I add SSO in front of the app; until then each user gets a token (ask me, I add it).
- [ ] **D3. UK sanctions link.** Once: open gov.uk/government/publications/the-uk-sanctions-list, copy the current CSV link, send it to me (the link changes with each publication; I will automate it).
- [ ] **D4. OpenSanctions** (optional aggregator): needs a commercial licence for business use; one email to them for a quote if you want it.
- [ ] **D5. Backups off-site.** Create a bucket (Hetzner Object Storage, Backblaze B2 or S3) and send me the access keys through your password manager, not chat; nightly dumps already run on the server.
- [ ] **D6. Zones.** Confirm the five sensitive zones (Crimea, occupied Azov coast, Syria, Iran coastal waters, North Korea) or name others (Venezuela, Russian Baltic ports…).

## Things I keep doing without you

World Port Index import, Kpler adapter when their answers arrive, SSO once you pick a provider, MapLibre polish after the first real-phone look, retuning on your feedback, and keeping STATUS.md current.
