# Status — 24 Oct 2026, evening

Links: repo https://github.com/0xdeni/MarineEdge- · approved redesign (round 2) https://claude.ai/artifact/FDkxLFJcLM4yhuuFj9CDhR · owner checklist `docs/OWNER-CHECKLIST.md`

**Live since 24 Oct 04:03 (São Paulo):** AWS Free-plan trial, t4g.small (2 Arm cores, 2 GB), Ubuntu, us-east-1, `https://44-197-249-76.sslip.io`. It updates itself from GitHub `main` every 10 minutes, and only after the full test suite, the migrations and the PostGIS store test pass on a scratch database. The trial ends six months after sign-up (late April 2027): an in-app export/import comes before then.

## Version 1.0 — the approved redesign, built (24 Oct)

On branch `redesign-r2`, with a pull request into `main`; the server installs it within 10 minutes of the merge, behind its usual gate.

Everything on screen now comes from the server; the app has no demo data of its own any more, and a server refuses the generated demo fleet (only a development machine with `VVT_ALLOW_MOCK=1` shows it).

- **Welcome, logo, intro.** A new mark (a ship's track drawn as an M, ending at its position now), animated on first open; three intro pages (voyages on one map, red flags with evidence, watch and hear first) over the app's own night chart. Reduce Motion turns all of it into fades.
- **Real accounts.** Create account (first person on a server uses the server admin password and becomes the owner; everyone else joins by invite link), sign in, forgot password (6-digit code by email, or a reset link an admin makes when email isn't set up), signed-in devices, change name, email and password, sign out. Passwords are scrypt-hashed; sessions are HttpOnly cookies; every state-changing request carries a header a foreign site can't send.
- **Home = search + the region now.** Ships in range, high risk, on sanctions lists; Watching; highest risk in range with the plain-language reason; region switcher. A background job checks every ship the feed hears (free, recorded data), so the overview fills itself.
- **A ship reads like the report.** Verdict in one sentence by fixed rules, three figures, status, "what happened" as a dated story (where it went dark and where it came back, the port and the zone, the ship it stopped beside), the year at a glance, voyages, identity and sanctions (naming only the lists the server really holds), particulars, team notes, Global Fishing Watch cross-check, watch, PDF.
- **Voyage and finding pages.** Route, times, distance, draught, dark hours, findings on the voyage; for a finding: a close-up map, the positions before and after (the event rows marked), the rule with this server's thresholds, notes.
- **Team.** Invites (link to share, or by email), roles (admin, analyst), turn an account off, reset link, remove. Team notes on a ship, a voyage or a finding, with author; editable by their author; printed in the PDF.
- **Admin in the app, nothing in files:** data sources (aisstream.io key with the recorder's live status, Datalastic key and per-ship 12-month purchase, GFW token, test), sanctions lists (counts per list, download now), rules (every threshold editable, back to defaults), zones, detailed maps (download OpenStreetMap detail to the server), email (SMTP, test), server (update gate result, disk, background checks, run jobs now).
- **Maps of our own.** MapLibre GL, vendored; Natural Earth (public domain) ships inside the app for the whole region, so the map works on first open and offline; OpenStreetMap detail (Protomaps extract) is an admin download to the server, served from it with range requests. No third-party map service, no key, no tracking.
- **PDF report rebuilt** to match the app: verdict, chart with coastlines and numbered findings, the findings in plain language with their record and positions, identity and sanctions, particulars, voyages, team notes, the thresholds in force.
- **Notifications** link straight to the finding; each person chooses High only or High and Medium.
- **Clean-up on update:** migration 006 deletes what the demo fleet left in a server's database (generated positions, and alerts and risk rows built from them); people's notes are kept.

**Verified here:** 65 backend tests; an end-to-end click-through in Chromium at iPhone size (welcome, intro, create owner account, home, search by former name, ship, finding, voyage, note add/edit/delete, watch, PDF to share sheet, alerts from the 30-minute job and tapping one to its finding, region switch, every profile page, appearance light/dark, invites by link and by email, joining as an analyst, forgot password with an emailed code, team role/off/reset link/remove, rules change and reset, zone toggle, sign out) with **zero console errors**; screenshots in dark, light, iPad landscape and Reduce Motion reviewed.

## Against the brief's milestones (honest)

| Milestone | Accepted when (brief) | Where we are |
|---|---|---|
| M1 Foundations | Search a vessel by name or IMO and pick the right ship; positions cached | Server-side search over the recorded feed, including former names. Covers ships heard since recording started; a Datalastic key adds any ship's past. **Accept on the live server once the aisstream key is in and a day of ships is recorded.** |
| M2 Voyage map | 12 months of a real vessel as coloured voyages with correct ports and dates | Built; never run on 12 months of real data (needs a paid pull). Ports: 68 hand-placed until the World Port Index import. **Not accepted.** |
| M3 Red flags | Seven rules fire correctly on test tracks and one known real case | Synthetic tracks pass; no real case yet. **Half.** |
| M4 Report and go-live | PDF exports; runs on the server with backups; tests pass | Server live with test-gated updates; PDF verified here, to verify on the server; backups only on the server's disk. **Partly.** |

## Needs the owner (all from the iPhone)

1. Once 1.0 is merged into `main` (the server installs it within 10 minutes): Get started › Create account, with the admin password as the server admin password. Signing in the old way (your email and the admin password) also works once and becomes the owner account; notes from the old sign-in carry over.
2. Paste the free aisstream.io key on the map screen. Recording starts within a minute; Profile › Data sources shows whether aisstream accepts it.
3. Optional now: Datalastic key (12 months per ship), GFW token, email settings, detailed maps download.

## Unverified (no access from this workspace)

- aisstream.io message shapes on the real feed (parser built from their docs; the recorder now reports refusals in the app).
- The Protomaps extract download on the server (hosts unreachable here; the app falls back to Natural Earth).
- The FCDO UK Sanctions List CSV against the real file (parser follows the published format guide; the sanctions page shows the per-list count after each download).
- Push on iPhone (needs the Home Screen install, iOS 16.4+); Apple's push service now gets the server's https address as sender.
- Datalastic field mapping against a live response (`first-pull` reports exactly which check fails).

## Decisions

- Plain HTML/JS frontend (allowed by the brief), split into `ui`, `api`, `map`, `onboarding`, `screens`, `profile`, `app`; one shared router (`app/routes.py`) serves the API for FastAPI and the stdlib dev server alike.
- Engine pure Python; PostGIS for the heavy queries; recorded feed read in place, bought history cached once and merged.
- Free first, paid per ship; coverage honesty (gaps where no receiver hears are Info, shown and not counted); GFW cross-check only.
- Verdict and stories written by fixed rules from the findings' facts, never generated, so the app and the PDF always say the same.
- Self-hosted maps and fonts; strict Content-Security-Policy (no inline scripts, nothing from other sites).

## Next engineering steps

1. World Port Index import (`scripts/import_wpi.py`), then validate port calls on real tracks.
2. Datalastic mapping on a live response, first pull of 5–10 real ships including a known dark-voyage case (M2/M3).
3. In-app export/import before the AWS trial ends; off-site backups when a bucket exists.
4. Kpler adapter when their answers arrive.
