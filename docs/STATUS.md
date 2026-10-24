# Status — 24 Oct 2026, morning (São Paulo)

Links: repo https://github.com/0xdeni/MarineEdge- · approved redesign (round 2) https://claude.ai/artifact/FDkxLFJcLM4yhuuFj9CDhR · owner checklist `docs/OWNER-CHECKLIST.md` · what it does and how it compares `docs/PRODUCT.md` · how findings are decided `docs/METHODOLOGY.md`

**Live since 24 Oct 04:03 (São Paulo):** AWS Free-plan trial, t4g.small (2 Arm cores, 2 GB), Ubuntu, us-east-1, `https://44-197-249-76.sslip.io`. It updates itself from GitHub `main` every 10 minutes, and only after the full test suite, the migrations and the PostGIS store test pass on a scratch database. The trial ends six months after sign-up (late April 2027): an in-app export/import comes before then.

## Version 1.0 — the approved redesign, live (24 Oct)

Pushed to `main` on 24 Oct at about 09:10 (São Paulo) and installed by the server's update gate within 15 minutes: `/api/health` reports version 1.0.0 with accounts, and the server is waiting for its first (owner) account.

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
| M2 Voyage map | 12 months of a real vessel as coloured voyages with correct ports and dates | Built; never run on 12 months of real data (needs a paid pull). Ports: 113 hand-placed (Danube, Bug, Azov and the main grain, oil and bulk terminals added 24 Oct) until the World Port Index import. **Not accepted.** |
| M3 Red flags | Seven rules fire correctly on test tracks and one known real case | Synthetic tracks pass; no real case yet. **Half.** |
| M4 Report and go-live | PDF exports; runs on the server with backups; tests pass | Server live with test-gated updates; PDF verified here, to verify on the server; backups only on the server's disk. **Partly.** |

## Needs the owner (all from the iPhone)

1. Done 24 Oct, 09:37: the owner account exists. If it was made by signing in the old way, its password is the admin password: change it in Profile › Password.
2. Paste the free aisstream.io key on the map screen if it asks for it. Recording starts within a minute; Profile › Data sources shows whether aisstream accepts it.
3. Done 24 Oct: the Syria zone is off by default, as the owner asked (the US ended its Syria sanctions programme in 2025 and the EU and UK lifted most economic sanctions; details in `docs/METHODOLOGY.md`). Switch it back on in Profile › Sensitive zones if a customer's policy needs it.
4. Global Fishing Watch: ask them for a licence before adding the token (their free terms exclude internal use that supports a business).
5. Optional now: Datalastic key (12 months per ship), email settings, detailed maps download.

## Since the release (24 Oct)

- **iPhone fixes (pushed about 09:53):** the Home Screen app stopped a status bar short of the bottom edge, showing a grey or black strip, on the owner's iOS 27.0.1. iOS gives a page shorter than the screen a viewport that ends early (WebKit bug 301108, reported since iOS 26); the page is now at least as tall as the screen. Also: the keyboard closes as soon as sign-in is sent, and the map re-frames the region once it has gone (it was showing the Mediterranean). To confirm on the phone.
- **Sanctions rule fixed.** A ship stayed flagged only if the server had first seen its listing in the last 12 months, so a year after the first download every long-standing listing would have stopped counting. Now a listing in force counts however old it is; the finding says "on the list since at least <date>" (the server's first sighting, not the official listing date). New test.
- **Documentation for people and agents:** `README.md` rewritten; `docs/PRODUCT.md` (capabilities and how MarineEdge compares), `docs/METHODOLOGY.md` (every rule, the verdict, the official guidance behind each red flag), `docs/API.md` (every route), `AGENTS.md` (rules for AI coding agents; `CLAUDE.md` imports it), `llms.txt`; ARCHITECTURE, PROVIDERS, FREE-STACK and DEPLOY brought up to date; stale comments in the code fixed.
- **Lint pinned** to ruff's classic rules in `backend/pyproject.toml`, so `make lint` means the same with any ruff version (clean).
- **False alarms cleared from the High-risk list (owner's screenshots, 24 Oct).** 46 Black Sea ships showed High, almost all for "changed draught at sea with no port call", a few for "stopped beside" a harbour craft. Fixes:
  - A draught of 0 means "not known" in AIS (the draught comes in a separate message, so a recording hears a ship's first positions without it). It never counts as a value now; it read as a change of 9 or 12 m at sea.
  - A draught change is High only when the ship stopped at sea or went dark since its last port call. Typed in while under way all along, it is the last port's cargo entered late, and is Info ("Draught entered late"); after a quiet period out of receiver range it is Info too. A switch in Red-flag rules restores the old rule.
  - Ship-to-ship: at anchor or moored, the other ship must be alongside (150 m, not 500 m), and must broadcast an IMO number (tugs, pilot boats and harbour craft don't). Both are settings in Red-flag rules, which now has on/off switches as well as numbers.
  - 45 more ports, so loading at Izmail, Reni, Mykolaiv, Rostov, Azov, Taganrog, Yeysk, the Romanian Danube ports, Aliağa or Mina Zayed is a port call, not a stop at sea: 113 in all.
  - Position jumps are left out of the draught check as documented (the jump marks were set after the draught rule ran).
  - Stored verdicts carry a stamp of the rules and zones that wrote them (migration 007). After this update, and whenever an admin changes a rule or a zone, older verdicts read as not checked and the background check re-checks those ships, newest first; until then the list shows only what has been checked under the rules in force.
  - Syria ships switched off (owner's decision); an admin's switch in the app wins either way.
  - 73 backend tests (new: unknown draught, draught causes, ship-to-ship at anchor and without IMO, on/off rule settings, zone defaults, stale verdicts).

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
3. Import the EU's list of ships banned from EU ports and services (Annex XLII of Regulation 833/2014, 673 ships after the 21st package), which is separate from the EU financial-sanctions file the server downloads today; then check every ship-to-ship partner against the lists and weigh night-time transfers (`docs/METHODOLOGY.md` § 5).
4. Ships removed from a sanctions list: keep flagging them for 12 months after removal, as the brief asks (the server already records the removal date; the rule, the ship page and the report need it).
5. Screen the registered owner, manager and operator against the lists when a paid source supplies their names.
6. Check the real-data false positives: in the first hours on the live server, 42 of 108 ships in range were High risk, many of them clustered at the Bosphorus anchorages. Likely cause: ships anchored near each other there count as ship-to-ship stops, because those anchorages are not in the port list. Confirm from "See all", then add the Turkish Straits anchorages (and others) or require ships at anchor to be alongside.
7. In-app export/import before the AWS trial ends; off-site backups when a bucket exists (the runtime settings file too, which the database dump leaves out).
8. Kpler adapter when their answers arrive.
