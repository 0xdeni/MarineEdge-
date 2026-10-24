# How MarineEdge judges a ship

MarineEdge turns a ship's last twelve months of AIS positions into findings, and the findings into a one-sentence verdict. Everything is done by fixed, published rules: the same data always gives the same findings and the same words, every threshold can be read and changed in the app (Profile › Red-flag rules), and every finding shows the positions it rests on.

A finding is an **indicator for a person's judgement, not a legal conclusion**. The rules point at behaviour that sanctions authorities and the industry name as red flags; deciding what it means for a fixture or a cargo stays with the desk and its compliance advisers.

This page is the reference for the rules. The code is `backend/app/engine/` (rules), `backend/app/verdict.py` (words) and `config/` (thresholds, zones, ports).

## 1. What a check uses

| Input | Source | Notes |
|---|---|---|
| Positions, 12 months (`history_months`) | The server's own recording of the free aisstream.io feed; plus history bought for that ship (Datalastic), merged one fix per minute | Terrestrial receivers only on the free feed: ships far offshore go unheard. The recorder stores about one fix per 10 minutes under way and per 30 minutes stopped, plus every turn, departure and arrival |
| Particulars and identity history | The provider: name, flag, MMSI, type, size; registered and beneficial owner, manager, class and insurer when a paid source has them | Every change of name, flag or MMSI is a history row on the IMO number |
| Sanctions lists | OFAC SDN (US), the EU consolidated list and the UK Sanctions List (FCDO), downloaded daily | Matched on the **IMO number only**, never on the name |
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

- **Fires when** the ship's IMO number is on a sanctions list the server holds: OFAC SDN, the EU list or the UK list, as of the latest daily download. How long ago it was listed does not matter.
- **Shows** each list, its programme, and the earliest date the server saw the listing.
- **Why it matters:** chartering, insuring, financing or paying a listed ship is prohibited or restricted for anyone bound by that list.
- **Limits:** the match is on the ship's own IMO number. Companies that own, manage or operate the ship are not screened against the lists. The verdict names only the lists the server has actually downloaded, and says "not checked" rather than "not listed" when none are there. Ships removed from a list are not flagged after their removal yet (the brief asks for twelve months; it is a next step).

### Call at a sensitive port — High

- **Fires when** a port call (section 2) is at a port in an enabled sensitive zone or lies inside one, including anchoring inside a zone.
- **Shows** the port, the zone and its legal basis, arrival and departure times, the length of the stay, draught in and out.
- **Why it matters:** cargo loaded or discharged there can breach sanctions or import bans (for example grain from occupied Crimea).
- **Zones shipped:** Crimea (sanctioned ports) and the occupied Azov coast (EU, UK and US measures), Syria (OFAC and EU programmes), Iranian coastal waters (OFAC, EU, UK programmes), North Korean waters (UN, OFAC, EU, UK). Which zones apply is a policy choice: switch them in Profile › Sensitive zones.

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
- **Limits:** a transfer where the other ship had its AIS off is not found (the Global Fishing Watch cross-check is a second opinion there). Lawful transfers in recognised STS areas (off Fujairah or Khor Fakkan, for example) flag like any other; the evidence shows where it happened.

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

GUIDANCE_PLACEHOLDER

## 6. What MarineEdge does not do

- It does not screen owners, managers or operators against sanctions lists, or map company networks. Those need an ownership database (Lloyd's List Intelligence, S&P Global, Equasis for manual checks).
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
