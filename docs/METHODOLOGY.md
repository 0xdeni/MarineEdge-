# How MarineEdge judges a ship

MarineEdge turns a ship's last twelve months of AIS positions into findings, and the findings into a one-sentence verdict. Everything is done by fixed, published rules: the same data always gives the same findings and the same words, every threshold can be read and changed in the app (Profile › Red-flag rules), and every finding shows the positions it rests on.

A finding is an **indicator for a person's judgement, not a legal conclusion**. The rules point at behaviour that sanctions authorities and the industry name as red flags; deciding what it means for a fixture or a cargo stays with the desk and its compliance advisers.

This page is the reference for the rules. The code is `backend/app/engine/` (rules), `backend/app/verdict.py` (words) and `config/` (thresholds, zones, ports).

## 1. What a check uses

| Input | Source | Notes |
|---|---|---|
| Positions, 12 months (`history_months`) | The server's own recording of the free aisstream.io feed; plus history bought for that ship (Datalastic), merged one fix per minute | Terrestrial receivers only on the free feed: ships far offshore go unheard. The recorder stores about one fix per 10 minutes under way and per 30 minutes stopped, plus every turn, departure and arrival |
| Particulars and identity history | The provider: name, flag, MMSI, type, size; registered and beneficial owner, manager, class and insurer when a paid source has them | Every change of name, flag or MMSI is a history row on the IMO number |
| Sanctions lists | OFAC SDN (US), the EU consolidated financial-sanctions list and the UK Sanctions List (FCDO), downloaded daily | Matched on the **IMO number only**, never on the name. The EU's separate list of ships banned from its ports (Annex XLII) is not imported yet (section 5) |
| Sensitive zones | `config/zones.geojson`: Crimea, the occupied Azov coast, Syria, Iranian waters, North Korean waters | Each zone carries its legal basis; an admin switches zones on or off |
| Ports | `config/ports.csv`: 68 ports and anchorages in the Black Sea, the Eastern Mediterranean, the Gulf, Hormuz and Oman | The NGA World Port Index import comes next |
| Known GPS-jamming areas | `config/areas.json`: the Black Sea, the Eastern Mediterranean, the Gulf and Hormuz | Used to label position jumps |
| Receiver coverage | Fixes heard per 0.5° cell over 30 days on the free feed | Used to tell "nobody could hear it" from "it went quiet" |

## 2. From positions to voyages

1. **Clean.** Positions with impossible coordinates and duplicate timestamps are dropped; the rest are sorted by time.
2. **Port calls.** A ship is in a port call when it stays slower than 0.5 kn (`port_call.max_speed_kn`) for at least 6 hours (`min_hours`) within 5 nm of a known berth (`port_radius_nm`), inside a port's anchorage circle, or inside a sensitive zone (an anchorage with no listed port, shown as "Anchorage · <zone>"). An anchorage wait and the berth at the same port within 36 hours (`merge_within_hours`) are one call. A stop still going at the end of the track counts even if it is shorter.
3. **Voyages.** A voyage runs from one port call to the next. The track before the first call is the start of the history; the track after the last call is the current voyage, drawn dashed to the ship's latest position. A voyage's distance leaves out position jumps; its draught out and in are the values reported as it left and as it arrived.
4. **Status.** Under way, at anchor or moored, since when, and the destination and ETA the crew typed into AIS.

## 3. The seven rules

Severity is **High**, **Medium** or **Info**. Info items are shown, explained and never counted.

### Sanctions hit — High

- **Fires when** the ship's IMO number is on a sanctions list the server holds: OFAC SDN, the EU financial-sanctions list or the UK Sanctions List, as of the latest daily download. How long ago it was listed does not matter.
- **Shows** each list, its programme, and the earliest date the server saw the listing.
- **Why it matters:** chartering, insuring, financing or paying a listed ship is prohibited or restricted for anyone bound by that list.
- **Limits:** the match is on the ship's own IMO number. Companies that own, manage or operate the ship are not screened against the lists. The verdict names only the lists the server has actually downloaded, and says "not checked" rather than "not listed" when none are there. Ships removed from a list are not flagged after their removal yet (the brief asks for twelve months; it is a next step).

### Call at a sensitive port — High

- **Fires when** a port call (section 2) is at a port in an enabled sensitive zone or lies inside one, including anchoring inside a zone.
- **Shows** the port, the zone and its legal basis, arrival and departure times, the length of the stay, draught in and out.
- **Why it matters:** cargo loaded or discharged there can breach sanctions or import bans (for example grain from occupied Crimea).
- **Zones shipped:** Crimea (sanctioned ports) and the occupied Azov coast (EU, UK and US measures), Syria, Iranian coastal waters (OFAC, EU, UK programmes), North Korean waters (UN, OFAC, EU, UK). Which zones apply is a policy choice: switch them in Profile › Sensitive zones.
- **Syria changed in 2025.** The US ended its Syria sanctions programme (Executive Order 14312, 30 June 2025, after General License 25 in May), the EU lifted nearly all of its economic sanctions on 28 May 2025, and the UK lifted most sectoral measures in April 2025. Designations of people tied to the former government, the arms embargo and some trade bans remain. A Syrian port call is therefore no longer a sanctions breach in itself, yet the zone still calls Syria "a sanctioned area". Keep it on only if your policy still treats Syria as high-risk. Sources: [Cleary Gottlieb, July 2025](https://www.clearygottlieb.com/news-and-insights/publication-listing/us-government-formally-terminates-economic-sanctions-on-syria), [Herbert Smith Freehills Kramer, June 2025](https://www.hsfkramer.com/notes/fsrandcorpcrime/2025-posts/recent-developments-on-sanctions-on-syria-in-the-uk-eu-and-us).

### AIS gap — Medium or High (Info outside receiver coverage)

- **Fires when** no position arrives for more than 6 hours (`ais_gap.min_hours`) at sea. A gap that lies wholly inside one port stay is ignored; going dark at sea and reappearing moored in a port counts.
- **High when** the gap is longer than 24 hours (`high_hours`) or either end lies within 100 nm of an enabled sensitive zone (`near_sensitive_nm`). Otherwise Medium.
- **Coverage on the free feed:** when the cell around either end had fewer than 50 fixes in 30 days (`coverage_min_fixes`), there is no receiver there; a gap of up to 72 hours (`coverage_max_hours`) there becomes Info, "outside receiver coverage", and does not count. Longer gaps count anyway.
- **Shows** when it went dark and came back, the last position, how far the ship moved, the nearest sensitive zone, whether the data was satellite or terrestrial, the receiver coverage, and the three positions before and after.
- **Limits:** AIS also drops for innocent reasons (equipment, interference, crowded channels, satellite revisit times), and masters may switch AIS off where it puts the ship at risk. The evidence lets the reader judge which.

### Draught change at sea — High

- **Fires when** the reported draught changes by 1.0 m or more (`draught_change.min_meters`) between two positions that are both outside port calls (and not a position jump).
- **Shows** the time and place, the nearest port, and the draught before and after.
- **Why it matters:** a ship that sits deeper after a stop at sea may have loaded cargo from another ship; one that rises may have discharged.
- **Indicator, not proof:** the draught is typed in by the crew and is often updated late, after leaving port. The app and the report say so on every such finding.

### Possible ship-to-ship transfer — High

- **Fires when** the ship stays slower than 1.0 kn (`sts.max_speed_kn`) outside port calls for at least 2 hours (`min_hours`) and another ship was within 500 m (`max_dist_m`) for at least 2 hours of that time.
- **Shows** the window, the other ship (name, IMO, flag, type), the position and the distance to the nearest port.
- **Cost:** on the recorded feed the partner search is free but only sees ships our receivers heard. On a paid provider each search is one paid query, at most 12 per ship per run (`max_lookups_per_vessel`).
- **Limits:** a transfer where the other ship had its AIS off is not found. The Global Fishing Watch cross-check helps less than it seems here: its listed encounter types all involve a fishing, carrier, support or bunker vessel, so two cargo ships or two tankers side by side are not among them. Lawful transfers in recognised STS areas (off Fujairah or Khor Fakkan, for example) flag like any other; the evidence shows where it happened.

### Position jump — Medium

- **Fires when** two consecutive positions imply a speed above 30 kn (`position_jump.max_implied_kn`). The bad fix and the return are one event, and the bad fix is left out of distances and draught checks.
- **Shows** the jump, its implied speed, and whether it lies in a known GPS-jamming area ("possible GPS jamming") or outside one ("check the receiver").
- **Limits:** spoofing that moves the reported position smoothly, at believable speeds, does not trip this rule.

### Identity change — Info, or Medium for more than one

- **Fires when** the ship's name, flag or MMSI changed in the last 12 months. One change is Info; more than one (`identity.medium_if_more_than`) is Medium.
- **Shows** each change with its date: old and new name, flag or MMSI.
- **Why it matters:** repeated renaming and reflagging is a pattern of ships avoiding scrutiny; a single change after a sale is common and harmless.

## 4. The verdict

| Level | When |
|---|---|
| **High risk** | At least one High finding |
| **Review** | No High finding, at least one Medium |
| **Not enough history** | Nothing found, but less than 14 days or fewer than 50 positions to judge from |
| **No red flags** | Nothing found in enough history |

The **sentence** names the most important finding, in this order: sanctions, sensitive-port calls, ship-to-ship stops, long or nearby AIS gaps, draught changes at sea, identity changes, other AIS gaps, position jumps. The **detail** adds up to two more ("It also…"). If the ship used another name at the time, the sentence says so ("under its former name …"). Up to **three figures** follow: the risk figures first (sanctions lists, sensitive-port calls, hours with AIS off…), then voyages, port calls and days of history. Info items never change the level; when quiet periods fell outside receiver coverage, the detail says they do not count.

Each finding's title and line ("Went dark in the Aegean Sea, back on in the Black Sea, 459 nm away. Near Crimea.") are written by the same fixed rules from the finding's facts. The app, the PDF report and the notifications use the same words. Nothing is generated by a language model.

## 5. Grounding in official guidance

Each rule follows behaviour that sanctions authorities and the IMO name as red flags. The documents below were checked against their primary sources on 24 October 2026; links are at the end of this section.

| Rule | Named as a red flag by | What the guidance adds |
|---|---|---|
| **AIS gap** | US: the OFAC, State and Coast Guard maritime advisory (14 May 2020); OFAC's Iranian oil guidance (16 Apr 2025); OFAC's maritime Compliance Communiqué (31 Oct 2024: "extended periods of time without transmission"). Price Cap Coalition alert (1 Feb 2024: "Repeated, prolonged, and unexplained gaps in AIS … particularly in sensitive locations"). UK: OFSI maritime guidance §4.8. EU: Regulation 833/2014, Art. 3ec. IMO: Assembly resolution A.1192(33) | Gaps near sensitive locations weigh more, as the 100 nm rule does. A switch-off for safety "should not be considered a red flag" (Coalition alert), and IMO resolution A.1106(29) lets the master switch AIS off when it endangers the ship. That is why every gap shows its evidence and coverage gaps are Info |
| **Call at a sensitive port** | US: Executive Order 13685 (the Crimea embargo) and OFAC's Crimea advisory (30 Jul 2015); FinCEN's Iran advisory (6 Jun 2025: "a vessel called in an Iranian port"). EU: Regulation 692/2014 (goods from Crimea and Sevastopol) and Regulations 2022/263 and 2022/1903 (goods from occupied Donetsk, Luhansk, Kherson and Zaporizhzhia). UK: the Crimean and Kherson–Zaporizhzhia ports directions. Ukraine closed the Crimean ports in 2014 and Berdiansk, Mariupol, Kherson and Skadovsk in 2022 | For a cargo ship the EU and US measures bite on the cargo's origin rather than on the call itself, and the EU and UK port bans cover cruise ships and British ships. The plain reading is "called at a port Ukraine has closed in occupied territory; cargo loaded there may be of sanctioned origin". The EU lists ships for "the transport of stolen Ukrainian grain" (Regulation 833/2014, Art. 3s(2)(d)) |
| **Possible ship-to-ship transfer** | US: the 2020 maritime advisory ("especially at night or in areas determined to be high-risk"); OFAC's Iranian oil guidance (2025: near sanctioned jurisdictions, outside territorial waters, "usually three to five" per shipment); FinCEN (2025); Treasury, 10 Apr 2025 (Iranian oil transfers "in waters off Iraq, Iran, the UAE, and the Gulf of Oman"). Coalition alert (2024). UK: OFSI §4.2. EU: Art. 3eb (notice of transfers), Art. 3s(1)(h) (no transfers with a listed ship). IMO: A.1192(33) | Night-time and high-risk areas aggravate; MarineEdge does not weigh the time of day yet. Transfers also have legitimate uses (the 2020 advisory; OFSI). The partner matters: a transfer with an EU-listed ship is prohibited for EU persons, and since 24 July 2026 it is itself a ground for listing (Art. 3s(2)(i)) |
| **Draught change at sea** | No official red-flag document reviewed names it. It comes from the owner's brief: a ship that sits deeper or higher after a stop at sea may have moved cargo without a port | The IMO's AIS guidelines (A.1106(29)) say the draught is entered by hand "at the start of the voyage … and amended as required", and a 2026 proposal to the IMO (MSC 111/19/6) seeks to standardise the field because it is unreliable. Hence "an indicator, not proof" |
| **Position jump** | Spoofing is named by OFAC's price-cap evasion alert (17 Apr 2023: "Spoofing can also be used to mask ship-to-ship transfers"), OFAC's 2024 Communiqué and OFSI §4.8 | A jump catches impossible movement only; smooth spoofing needs other sources |
| **Identity change** | US: the 2020 advisory ("flag hopping"); OFAC's 2019 Iran advisory (owners "change the name of a vessel", so research it by IMO number); OFAC's 2025 Iran guidance ("flown multiple flags in an uncommonly short period of time", borrowed MMSI and IMO numbers); FinCEN (2025: "recent or multiple name or flag changes"). Coalition advisory (21 Oct 2024: "re-flagging, vessel name changes"). UK: OFSI §4.1 and §4.5. IMO: resolution A.1215(34) keeps the IMO number with the ship through a change of flag | "Medium for more than one" follows the "multiple changes in a short period" wording |
| **Sanctions hit** | OFAC's SDN list (ships "identified as blocked property"); the UK Sanctions List (the only UK source since 28 January 2026; the UK reported "nearly 600 tankers" sanctioned by 1 October 2026); the EU's Annex XLII of Regulation 833/2014 (673 ships after the 21st package of 23 July 2026). The Coalition's 2024 advisory (Recommendation 10): screen vessels | See "What the lists cover" below |

**Indicator, not proof.** The Price Cap Coalition's alert says "No single vessel behaviour should be viewed in isolation" and that monitoring "should take into account legitimate reasons for apparent evasion red flags"; IMO resolution A.1192(33) asks port states to look for legitimate reasons first. MarineEdge follows that: it says what happened, shows the evidence, and leaves the judgement to the reader.

**What the lists cover.**
- **OFAC SDN:** ships listed in their own right, by IMO number. A ship blocked only because its owner is listed (OFAC's 50 percent rule) may have no entry of its own.
- **UK:** the FCDO's UK Sanctions List, which includes specified ships.
- **EU:** the file MarineEdge downloads is the EU's consolidated list of persons, groups and entities under financial sanctions (asset freezes). The ships banned from EU ports and services are designated separately, in Annex XLII of Regulation 833/2014 (673 after the 21st package). MarineEdge does not import Annex XLII yet and has not confirmed that the financial-sanctions file carries those ships, so for now "not on the EU list" covers the financial-sanctions file only. Importing Annex XLII is the next step (`STATUS.md`).

**Sources**
- US: [OFAC, State and USCG maritime advisory, 14 May 2020](https://ofac.treasury.gov/media/37751/download?inline) · [OFAC Iran petroleum shipping advisory, 4 Sep 2019](https://ofac.treasury.gov/media/46006/download) · [OFAC guidance on Iranian oil sanctions evasion, 16 Apr 2025](https://ofac.treasury.gov/media/934236/download?inline) · [FinCEN advisory FIN-2025-A002, 6 Jun 2025](https://www.fincen.gov/system/files/FinCEN-Advisory-Illicit-Oil-Smuggling-508.pdf) · [OFAC alert on price-cap evasion, 17 Apr 2023](https://ofac.treasury.gov/system/files/2023-04/20230417_price_cap_alert.pdf) · [OFAC Compliance Communiqué for the maritime industry, 31 Oct 2024](https://ofac.treasury.gov/media/933556/download) · [OFAC Crimea advisory, 30 Jul 2015](https://ofac.treasury.gov/media/8676/download) · [Treasury on Iranian oil transfers off the UAE and Oman, 10 Apr 2025](https://home.treasury.gov/news/press-releases/sb0082) · [Treasury on stolen Ukrainian grain from Crimea, 2 Apr 2025](https://home.treasury.gov/news/press-releases/sb0068)
- Price Cap Coalition: [advisory, 12 Oct 2023](https://ofac.treasury.gov/media/932201/download) · [compliance and enforcement alert, 1 Feb 2024](https://ofac.treasury.gov/media/932571/download) · [updated advisory, 21 Oct 2024](https://ofac.treasury.gov/media/933506/download?inline)
- UK: [OFSI financial sanctions guidance for maritime shipping](https://www.gov.uk/government/publications/financial-sanctions-guidance-for-maritime-shipping/financial-sanctions-guidance-for-maritime-shipping) · [the UK Sanctions List](https://gov.uk/government/publications/the-uk-sanctions-list) · [transport sanctions (DfT)](https://www.gov.uk/guidance/transport-sanctions) · [SI 2023/665, Kherson and Zaporizhzhia ports direction](https://www.legislation.gov.uk/uksi/2023/665/made)
- EU: [Regulation 2023/1214 (Art. 3eb, 3ec)](https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32023R1214) · [Regulation 2024/1745 (Art. 3s, Annex XLII)](https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202401745) · [Regulation 2026/1848, 21st package](https://eur-lex.europa.eu/eli/reg/2026/1848/oj/eng) · [Commission FAQ on targeted vessels](https://finance.ec.europa.eu/publications/targeted-vessels_en) · [Regulation 692/2014 (Crimea, Sevastopol)](https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32014R0692) · [Regulation 2022/263](https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R0263) · [Regulation 2022/1903](https://eur-lex.europa.eu/eli/reg/2022/1903/oj/eng)
- IMO: [Assembly 33 summary, incl. A.1192(33)](https://www.imo.org/en/mediacentre/meetingsummaries/pages/imo-assembly%2C-33rd-session%2C-27-november---6-december-2023-.aspx) · [A.1215(34), IMO identification numbers](https://wwwcdn.imo.org/localresources/en/OurWork/IIIS/Documents/A%2034-Res.1215%20-%20INTEGRATED%20IMO%20IDENTIFICATION%20NUMBER%20SCHEME%20%28Secretariat%29.pdf) · [MSC 111/19/6 on AIS destination, ETA and draught fields](https://www.ics-shipping.org/wp-content/uploads/2026/04/MSC-111-19-6-Revision-of-the-Revised-guidelines-for-the-onboard-operational-use-of-shipborne-automatic.-Austria-Belgium-Bulgari.pdf)
- Ukraine: [President's office on sanctions against 56 ships that loaded in Sevastopol and Feodosia, 25 Nov 2025](https://www.president.gov.ua/en/news/ukrayina-zastosuvala-sankciyi-do-56-morskih-suden-sho-nezako-101589)

## 6. What MarineEdge does not do

- It does not screen owners, managers or operators against sanctions lists, or map company networks. Those need an ownership database (Lloyd's List Intelligence, S&P Global, Equasis for manual checks).
- It does not yet import the EU's list of ships banned from EU ports (Annex XLII of Regulation 833/2014), check a ship-to-ship partner against the lists, or weigh a transfer by time of day (section 5).
- It does not use satellite imagery (radar or optical) to confirm where a dark ship was.
- On the free feed it hears only coastal receivers, and its history starts the day recording began; open-sea and older positions are bought per ship.
- It finds port calls only at the 68 ports and anchorages it knows until the World Port Index is imported; a long stop elsewhere is not a port call.
- It does not detect smooth position spoofing, or ships broadcasting another ship's identity.
- It does not tell you whether a fixture is lawful. It tells you what the ship did, where, when, and how sure the data is.

## 7. Changing the rules

- **Thresholds:** Profile › Red-flag rules changes any number for the whole server; **Back to the defaults** returns to `config/rules.yaml`.
- **Zones:** Profile › Sensitive zones switches each zone on or off. New zones are polygons in `config/zones.geojson` with an `id`, `name`, `short` (how a sentence names it) and `basis` (the legal basis shown on the finding).
- **Ports:** `config/ports.csv`, one row per port with its berth, approach and optional anchorage circle.
- Every rule has unit tests on synthetic tracks (`backend/tests/test_engine.py`); a change to a rule changes its tests, and `docs/METHODOLOGY.md` is updated in the same commit.
