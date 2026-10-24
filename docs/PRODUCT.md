# MarineEdge — the product

**Check any ship's last twelve months before you fix it: every voyage, every red flag, with the evidence.**

MarineEdge is a ship due-diligence app for trading desks that charter ships or accept cargoes of grain, oilseeds, vegetable oils and dry bulk in the Black Sea, the Strait of Hormuz, the Gulf of Oman and the UAE. Type a ship's name, a former name, its IMO or MMSI number, and within seconds you see where it has been for a year, what it did that sanctions authorities treat as a red flag, the positions that show it, and a one-sentence verdict you can repeat to a colleague or put in a file. It runs on your own server, installs on an iPhone like an app, and costs little more than that server.

## Who it is for, and the decision it supports

- **Chartering and operations desks** deciding whether to fix a ship, accept a nomination or load a cargo.
- **Compliance and risk** people who must show why a ship was accepted or refused, with evidence that holds up later.
- **Owners of a small trading business** who need the screening the large houses have, without an enterprise contract.

The question it answers: *has this ship, in the last twelve months, been somewhere or done something that makes this fixture a sanctions or reputational risk?* It answers with facts and evidence; the decision stays with you.

## What you can do

### Find a ship

- Search by name, **former name**, IMO or MMSI. Results show each ship's type, size, flag, year built and its last verdict, and say which former name matched ("formerly SILVER DUNE").
- Type a seven-digit number to look up an IMO directly.
- Ships are identified by IMO number, so renamed and reflagged ships are always the same ship.

### See your region now

- The home screen is a map of the region you work in (Black Sea, Strait of Hormuz, Iran coast, Gulf of Oman or UAE) with every ship heard in the last six hours, coloured by its last verdict.
- Three figures: ships in range, high risk, on sanctions lists. Tap high risk or sanctions for the list of ships.
- **Highest risk in range:** the ships to worry about first, each with the reason in plain words.
- **Watching:** the ships you starred, with their latest verdict and last position.
- A background job checks every ship the feed hears, free, so the overview fills itself.

### Read a ship in one minute

- **Verdict** at the top: High risk, Review, No red flags, or Not enough history, in one sentence written by fixed rules ("Called at three ports in Crimea, under its former name SILVER DUNE."), with up to two more facts and three figures.
- **Status:** under way, at anchor or moored, where, since when, and the next port the crew typed.
- **What happened:** the findings as a dated story ("Went dark in the Aegean Sea, back on in the Black Sea, 459 nm away. Near Crimea."), and the year at a glance.
- **Voyages,** port to port, one colour each on the map, the current one dashed to the ship's position.
- **Identity and sanctions:** name, flag and MMSI with their history, and which lists the ship is on, naming only lists the server really holds.
- **Particulars:** type, size, build, and owner, manager, class and P&I insurer when a paid source supplies them, with a link to look the IMO up in Equasis.

### Follow the evidence

- **Voyage page:** departure and arrival, time at sea, distance, draught out and in, hours dark, the findings on that voyage, and Show on map, Add note and PDF.
- **Finding page:** a close-up map, the plain-language story, the positions before and after with the event rows marked, the record exactly as the rule wrote it, and the rule with this server's thresholds.
- Every finding says how sure the data is: draught findings are labelled "indicator, not proof"; quiet periods where no receiver can hear are shown as information and never counted.

### Watch ships and hear first

- Star a ship to watch it. The server re-checks watched ships every 30 minutes; new findings appear in Alerts and as notifications on the iPhone (High only, or High and Medium; each person chooses). A notification opens the finding itself.

### Work as a team

- Accounts by invitation: a link to share (WhatsApp, Mail) or an email. Roles: admin and analyst.
- **Team notes** on a ship, a voyage or a single finding, signed by their author, editable by them, and printed in the PDF.
- Forgot password by emailed code, or a reset link an admin makes; signed-in devices you can sign out remotely.

### Hand over a report

- **PDF report** in one tap, shared from the iPhone's share sheet: verdict and figures, the chart of the year with numbered findings, what happened, identity and sanctions, particulars, voyages, team notes, and the thresholds in force. It says the same as the app, word for word.

### Get a second opinion, buy the past

- **Compare with Global Fishing Watch:** their satellite-based events (AIS off, encounters, loitering, port visits) beside our findings, as a cross-check (non-commercial licence).
- **Get the last 12 months:** when a ship matters and the free feed has not heard all of its year, an admin buys that ship's history from Datalastic once; it is kept for good and merged with what the server recorded.

### Run it from the phone

Every admin task is in the app: data-source keys and live recorder status, the team, email delivery, sanctions lists (counts per list, download now), red-flag thresholds (back to the defaults in one tap), sensitive zones (on or off), detailed maps (download OpenStreetMap detail to the server), the server (update result, disk, run jobs now). Nothing needs a terminal.

### Install it

Open the address in Safari and add it to the Home Screen: it runs full screen, receives notifications (iOS 16.4+), and ships you opened stay readable offline. Light and dark, Reduce Motion, iPad and desktop layouts are built in.

## Where the data comes from, and what it cannot see

| Data | Source | What to know |
|---|---|---|
| Live positions and the last year | aisstream.io, free, recorded by your server around the clock | Coastal receivers only: open sea far offshore is unheard; history starts the day recording began |
| A ship's full past year, open sea included | Datalastic, bought per ship when you choose | Paid by credits; bought once, kept for good |
| Sanctions | OFAC SDN, EU consolidated list, UK Sanctions List; official downloads, daily | Matched on the IMO number |
| Sensitive zones and ports | MarineEdge's own reference files, editable | Five zones and 68 regional ports today |
| Second opinion | Global Fishing Watch | Non-commercial licence: a cross-check, never a source |
| Maps | Natural Earth and OpenStreetMap, on your own server | No map service, no key, no tracking |

`METHODOLOGY.md` explains every rule and its limits; `PROVIDERS.md` the sources and their terms.

## How MarineEdge compares

COMPARISON_PLACEHOLDER

## Security and privacy

- **Your server, your data.** Positions, findings, notes and reports live in your database; the app loads nothing from other sites, and with the free feed as the main source a vendor learns about a ship only when you buy its history or ask Global Fishing Watch for a second opinion.
- **Accounts:** invitation only; passwords hashed with scrypt; sessions in HttpOnly cookies with CSRF protection; rate limits on every sign-in path; devices you can sign out.
- **A strict Content-Security-Policy** and no third-party scripts, fonts or map services.
- **Updates are tested before they arrive:** the server installs a new version only after the whole test suite passes on it.

## What it costs to run

- **Server:** from free (Oracle Always Free, or a 6-month AWS or 90-day Google Cloud trial) to the price of a small cloud server; the live one runs on an AWS trial worth about $18 a month.
- **Live data:** free (aisstream.io). **Sanctions lists, maps, notifications, email:** free (email needs any SMTP account).
- **History:** paid per ship, only when you buy it (Datalastic credits). Nothing else is metered: no seats, no per-search fees.

## Limits, plainly

- It screens the ship, not the companies behind it: owners, managers and operators are not matched against sanctions lists yet.
- On the free feed it hears coastal receivers only, and its history starts when recording started; buy a ship's year when the gap matters.
- No satellite imagery, and no detection of smooth position spoofing or of a ship broadcasting another ship's identity.
- Port calls are found at the 68 ports and anchorages it knows until the World Port Index is imported.
- Findings are indicators for your judgement, not legal conclusions.

## What comes next

The World Port Index import, the first paid pull of real ships (including a known dark-voyage case) to accept the voyage and red-flag milestones, keeping ships flagged for a year after they leave a sanctions list, screening owners and managers when a paid source supplies them, and an in-app move to a new server before the AWS trial ends. `STATUS.md` has the current list.
