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

- **Compare with Global Fishing Watch:** their satellite-based events (AIS off, encounters, loitering, port visits) beside our findings, as a cross-check. Their free licence is non-commercial and does not cover a business's internal use, so a trading desk switches it on only with GFW's written licence.
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
| Second opinion | Global Fishing Watch | A cross-check, never a source. Its free licence excludes internal use that supports a business, so a trading desk needs GFW's written licence first |
| Maps | Natural Earth and OpenStreetMap, on your own server | No map service, no key, no tracking |

`METHODOLOGY.md` explains every rule and its limits; `PROVIDERS.md` the sources and their terms.

## How MarineEdge compares

Two kinds of tool do parts of this job. **Risk and compliance platforms** (Windward, Lloyd's List Intelligence, S&P Global, Kpler's MarineTraffic, Pole Star) screen ships worldwide for banks, insurers, traders and governments. **Public ship trackers** (VesselFinder, MarineTraffic's own plans) show where ships are, without screening. MarineEdge does the screening part of the first, for one desk's trade lanes, at close to the price of the second, on a server you control.

Facts as published on 24 October 2026; sources at the end of this section.

| | Owner | Data behind it | Published price | How a finding is decided |
|---|---|---|---|---|
| **Windward** | FTV Capital (private since March 2025) | AIS from S&P Global; optical, radar and radio-frequency satellite sensing; LSEG World-Check and Dun & Bradstreet for ownership | $29,000 per user per year (Trading and Shipping plan, AWS Marketplace list price, terms negotiated privately) | More than 15 proprietary models; evidence shown for each risk; the models are not published |
| **Lloyd's List Intelligence** (Seasearcher) | Montagu Private Equity (since 2022) | Its own AIS network (coastal, on-ship and satellite receivers); Lloyd's Agents for casualties; ownership to the ultimate owner, OFAC 50% rule | By quote. A UK public body paid £36,785 for two years of Seasearcher Premium (2025–27) | Red, amber, green with machine learning; weightings not disclosed |
| **S&P Global** (Sea-web, Maritime Intelligence Risk Suite) | S&P Global | The registry behind IMO ship and company numbers; satellite and coastal AIS (ORBCOMM's AIS business, bought in 2025); ownership to seven levels | £28,000 to £96,000 per user (UK government G-Cloud listing, 2024) | No public description found |
| **Kpler** (MarineTraffic Risk & Compliance) | Private, management majority; Sixth Street minority stake (2026) | Coastal, open-ocean and satellite AIS (it owns MarineTraffic, FleetMon and Spire Maritime); Airbus satellite imagery from October 2026 | An add-on to MarineTraffic Enterprise, priced on request | Some thresholds published (an AIS gap is "no signal for over 20 hours", checked against coverage); the overall method is not public |
| **Pole Star** (PurpleTRAC) | Wavecrest Growth Partners and Abry Partners | AIS with Inmarsat positions; Dow Jones sanctions lists; screens owners and managers too | Credits per screening; price not published | Rating method not published |
| **VesselFinder** | AstraPaging Ltd | Coastal AIS; satellite on the top plan | Free; Premium $34 a month; Satellite $139 a month | No screening |
| **Global Fishing Watch** | Independent non-profit | Satellite and coastal AIS, Sentinel-1 radar | Free, non-commercial licence only | Published definitions (an encounter is two vessels within 500 m for 2 hours) |
| **MarineEdge** | You | Free coastal AIS recorded on your server; a ship's full year bought per ship (Datalastic); OFAC, EU and UK lists | A server (free tiers up to about $18 a month) plus the ship histories you buy; no per-user fees | Seven published rules; every threshold editable; every finding shows its positions |

### Where the big platforms are stronger

- **Coverage and history.** They own or buy satellite, coastal and on-ship AIS and keep years of it (MarineTraffic Enterprise: five years; Kpler's compliance data starts in January 2022). MarineEdge hears coastal receivers only and buys a ship's past year when it matters; far offshore it says "not heard" rather than "went dark".
- **Independent confirmation.** Windward, Kpler and Lloyd's List Intelligence check AIS against satellite imagery or radio signals, so they can confirm a dark ship-to-ship transfer or a spoofed position. MarineEdge sees AIS only: it can flag a pattern, not confirm it.
- **Ownership.** Owners and managers up to the ultimate beneficial owner, and exposure under the OFAC 50% rule (Lloyd's List Intelligence, S&P Global, Windward); Pole Star screens owners and managers against the lists. MarineEdge screens the ship's IMO number only.
- **Curated data and people:** commercial watch lists (World-Check, Dow Jones), casualty and inspection histories, class and P&I, analyst teams and support desks, every ship type worldwide.

### Where MarineEdge is the better fit

- **You can see why.** Every rule, threshold and sentence is published in [METHODOLOGY.md](METHODOLOGY.md), every finding carries the positions it rests on, and the same data always gives the same answer, so an auditor can re-run it. The platforms keep audit trails and let customers set thresholds too, but they publish little about how a score is reached: Windward cites more than 15 proprietary models, Lloyd's List Intelligence does not disclose its weightings, and no method was found for S&P's risk suite or PurpleTRAC.
- **The cost does not grow with the team.** Published platform prices are per user per year ($29,000 at Windward; £28,000 to £96,000 for S&P's risk suite). MarineEdge costs a server plus the ship histories you choose to buy, however many people use it.
- **Your screening stays on your server.** Every platform reviewed is a hosted service. With MarineEdge, which ships you are about to fix, your notes and your reports stay on your server; an IMO number leaves it only when you buy that ship's history or ask for a cross-check.
- **Made for these lanes and this desk.** Grain from occupied Crimea and the Azov coast, the Turkish Straits, Hormuz and the Gulf; an iPhone app with notifications that open the finding; notes on a single finding; a verdict in plain words; a PDF that says what the app says.
- **Honest about what it cannot hear.** A quiet period where no receiver listens is shown as information, not as "went dark", the same check Kpler and Global Fishing Watch make before calling a gap deliberate.
- **Yours to change.** Thresholds in the app, rules in plain Python with tests, data providers behind one adapter (Datalastic today; Kpler when its terms arrive).

### Using both

Run MarineEdge on every ship you look at. For the one you are about to fix, when the stakes justify it, add a platform check: some sell single screenings (Pole Star charges credits per screening).

### Sources

- Windward: [FTV Capital completes acquisition, 18 Mar 2025](https://ftvcapital.com/2025/ftv-capital-completes-acquisition-of-maritime-ai-leader-windward/) · [Risk & Compliance](https://windward.ai/solutions/due-diligence/) · [vessel screening](https://windward.ai/solutions/vessel-screening/) · [AIS feeds through 2030](https://windward.ai/news/windward-secures-long-term-ais-data-feeds-through-2030/) · [AWS Marketplace listing](https://aws.amazon.com/marketplace/pp/prodview-poyecpezfq2ee)
- Lloyd's List Intelligence: [Advanced Compliance](https://www.lloydslistintelligence.com/solutions/seasearcher/advanced-compliance) · [SeaOrbis AIS launch](https://www.hellenicshippingnews.com/lloyds-list-intelligence-launches-ais-seaorbis-the-next-evolution-in-ais-vessel-tracking-intelligence/) · [Montagu acquisition, 2022](https://splash247.com/?p=170810) · [Trinity House award, 2025](https://www.find-tender.service.gov.uk/Notice/044696-2025) · [weightings and audit trail](https://www.lloydslistintelligence.com/thought-leadership/blogs/seasearcher-advanced-risk-and-compliance-vs-the-competition)
- S&P Global: [G-Cloud 14 listing](https://www.applytosupply.digitalmarketplace.service.gov.uk/g-cloud/services/970655660023601) · [ORBCOMM AIS acquisition completed](https://press.spglobal.com/2025-11-10-S-P-Global-Announces-Successful-Completion-of-its-Acquisition-of-ORBCOMMs-Automatic-Identification-System-Business) · [Sea-web Companies](https://prod.azure.ihsmarkit.com/marketintelligence/en/mi/products/sea-web-companies.html)
- Kpler: [Risk & Compliance](https://www.kpler.com/solutions/derived-insights/risk-compliance) · [4 Jun 2024 release: gaps over 20 hours](https://help.kpler.com/en/articles/9419631-4-june-2024-new-risk-compliance-features) · [Airbus satellite detection](https://www.kpler.com/blog/kpler-strengthens-vessel-tracking-with-airbus-satellite-detection) · [Spire Maritime closing](https://maritime-executive.com/article/kpler-closes-spire-maritime-acquisition-as-uk-proceeds-with-investigation) · [Sixth Street investment, 2026](https://www.businesswire.com/news/home/20260603796346/en/Kpler-Announces-Strategic-Growth-Equity-Investment-from-Sixth-Street) · [Enterprise add-on](https://support.marinetraffic.com/en/articles/12557133-10-october-2025-pdf-download-now-available-in-risk-compliance-on-marinetraffic) · [MarineTraffic plans on G2](https://g2.com/products/kpler-marinetraffic/pricing)
- Pole Star: [PurpleTRAC](https://www.polestarglobal.com/purpletrac) · [screening credits](https://ondemand.support.polestarglobal.com/en/article/screening-tab)
- VesselFinder: [plans](https://www.vesselfinder.com/get-premium)
- Global Fishing Watch: [events and definitions](https://globalfishingwatch.org/our-apis/documentation/docs/v3/events.md) · [licence and rate limits](https://globalfishingwatch.org/our-apis/documentation/docs/license-rate-limits) · [commercial use](https://globalfishingwatch.org/faqs/can-i-use-global-fishing-watch-apis-for-commercial-purposes/) · [data caveats](https://globalfishingwatch.org/our-apis/documentation/docs/v3/general-api-doc/data-caveats)

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
- The EU's list of 673 ships banned from its ports (Annex XLII) is separate from the EU file the server downloads, and is not imported yet; until it is, "not on the EU list" covers EU financial sanctions only.
- On the free feed it hears coastal receivers only, and its history starts when recording started; buy a ship's year when the gap matters.
- No satellite imagery, and no detection of smooth position spoofing or of a ship broadcasting another ship's identity.
- Port calls are found at the 68 ports and anchorages it knows until the World Port Index is imported.
- Findings are indicators for your judgement, not legal conclusions.

## What comes next

The World Port Index import, the first paid pull of real ships (including a known dark-voyage case) to accept the voyage and red-flag milestones, keeping ships flagged for a year after they leave a sanctions list, screening owners and managers when a paid source supplies them, and an in-app move to a new server before the AWS trial ends. `STATUS.md` has the current list.
