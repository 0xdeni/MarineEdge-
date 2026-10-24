"""The verdict at the top of a ship page: a level, a one-line sentence and up to three figures.

Written by fixed rules from the findings — never generated or guessed — so the same analysis always reads
the same way, in the app and in the PDF. Order of importance when choosing the sentence:
sanctions, sensitive-port calls, ship-to-ship stops, long or nearby AIS gaps, draught changes at sea,
identity changes, other AIS gaps, position jumps."""
from __future__ import annotations

from typing import Any, Optional

from app.engine.types import D, Analysis, Flag

WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
LABELS = {"high": "High risk", "review": "Review", "clear": "No red flags", "insufficient": "Not enough history"}
MIN_DAYS = 14          # less history than this, and nothing found: say so instead of "no red flags"
MIN_FIXES = 50


def word(n: int) -> str:
    return WORDS[n] if 0 <= n < len(WORDS) else str(n)


def times(n: int) -> str:
    return "once" if n == 1 else "twice" if n == 2 else f"{word(n)} times"


LIST_ORDER = ["OFAC SDN", "EU", "UK"]
LIST_SHORT = {"OFAC SDN": "OFAC", "EU": "EU", "UK": "UK"}


def plural(n: int, one: str, many: Optional[str] = None) -> str:
    return one if n == 1 else (many or one + "s")


def hours_text(h: float) -> str:
    h = round(h)
    if h < 48:
        return f"{h} {plural(h, 'hour')}"
    d = round(h / 24)
    return f"{d} days"


def join_and(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def history_days(a: Analysis) -> float:
    if len(a.track) < 2:
        return 0.0
    return (a.track[-1].t - a.track[0].t) / D


def _former_name(a: Analysis, before_t: int) -> Optional[str]:
    """Name the ship used at `before_t`, when it has been renamed since."""
    names = sorted((h for h in a.vessel.history if h.get("field") == "name" and h.get("t", 0) > before_t), key=lambda h: h["t"])
    return names[0]["from"] if names else None


class _Cat:
    """One kind of finding, with its sentence and fragment."""

    def __init__(self, key: str, severity: str, sentence: str, fragment: str, tile: Optional[tuple[str, str]]):
        self.key, self.severity, self.sentence, self.fragment, self.tile = key, severity, sentence, fragment, tile


def _categories(a: Analysis) -> list[_Cat]:
    by: dict[str, list[Flag]] = {}
    for f in a.flags:
        by.setdefault(f.rule, []).append(f)
    out: list[_Cat] = []

    s = by.get("Sanctions hit", [])
    if s:
        found = {x for f in s for x in (f.meta.get("lists") or [])}
        lists = [x for x in LIST_ORDER if x in found] + sorted(found - set(LIST_ORDER))
        lx = join_and(lists) or "a"
        many = len(lists) > 1
        out.append(_Cat("sanctions", "high", f"On the {lx} sanctions {plural(len(lists), 'list')}.", f"is on the {lx} sanctions {plural(len(lists), 'list')}",
                        (str(len(lists)), "sanctions lists") if many else (LIST_SHORT.get(lists[0], lists[0]) if lists else "1", "sanctions list")))

    p = by.get("Call at a sensitive port", [])
    if p:
        zones: dict[str, list[Flag]] = {}
        for f in p:
            zones.setdefault(f.meta.get("zone") or "a sensitive zone", []).append(f)
        n = len(p)
        if len(zones) == 1:
            zone, fl = next(iter(zones.items()))
            ports = sorted({f.meta.get("port") or "a port" for f in fl})
            if n == 1:
                core = f"called at {ports[0]} in {zone}"
            elif len(ports) == 1:
                core = f"called at {ports[0]} in {zone} {times(n)}"
            else:
                core = f"called at {word(len(ports))} ports in {zone}" + (f", {n} calls in all" if n > len(ports) else "")
            tile_label = f"{plural(n, 'call')} in {zone}"
        else:
            core = f"called at ports in {join_and(sorted(zones))}"
            tile_label = f"sensitive-port {plural(n, 'call')}"
        former = _former_name(a, max(f.t1 or f.t0 for f in p))
        if former:
            core += f", under its former name {former}"
        out.append(_Cat("ports", "high", _cap(core) + ".", core, (str(n), tile_label)))

    sts = by.get("Possible ship-to-ship transfer", [])
    if sts:
        n = len(sts)
        if n == 1:
            f = sts[0]
            core = f"stopped {hours_text(f.meta.get('hours') or (((f.t1 or f.t0) - f.t0) / 3_600_000))} beside {f.meta.get('partner') or 'another ship'} at sea"
        else:
            partners = sorted({f.meta.get("partner") for f in sts if f.meta.get("partner")})
            core = f"stopped beside other ships at sea {times(n)}" + (f", including {partners[0]}" if partners else "")
        out.append(_Cat("sts", "high", _cap(core) + ".", core, (str(n), f"ship-to-ship {plural(n, 'stop')}")))

    gaps = [f for f in by.get("AIS gap", []) if f.severity in ("high", "medium")]
    hi = [f for f in gaps if f.severity == "high"]
    total_h = sum(f.hours for f in gaps)
    if hi:
        n = len(hi)
        near = sorted({f.meta.get("zone") for f in hi if f.meta.get("near") and f.meta.get("zone")})
        where = f" near {join_and(near)}" if near else ""
        if n == 1:
            core = f"went dark for {hours_text(hi[0].hours)}{where}"
        else:
            core = f"went dark {times(n)}, {hours_text(sum(f.hours for f in hi))} in all{where}"
        out.append(_Cat("gaps", "high", _cap(core) + ".", core, (f"{round(total_h)} h", "with AIS off")))

    dr = by.get("Draught change at sea", [])
    if dr:
        n = len(dr)
        if n == 1:
            d = abs(dr[0].meta.get("delta") or 0)
            core = f"changed draught by {d:.1f} m at sea with no port call"
        else:
            core = f"changed draught at sea {times(n)} with no port call"
        out.append(_Cat("draught", "high", _cap(core) + ".", core, (str(n), f"draught {plural(n, 'change')} at sea")))

    idc = by.get("Identity change", [])
    if idc:
        ch = [c for f in idc for c in (f.meta.get("changes") or [])]
        sev = "medium" if any(f.severity == "medium" for f in idc) else "info"
        names = [c for c in ch if c["field"] == "name"]
        flags_ = [c for c in ch if c["field"] == "flag"]
        if len(ch) == 1 and names:
            core = f"was renamed from {names[0]['from']} to {names[0]['to']}"
        elif len(ch) == 1 and flags_:
            core = f"was reflagged from {flags_[0]['from']} to {flags_[0]['to']}"
        elif names and flags_:
            core = "was renamed and reflagged"
        else:
            core = f"changed name, flag or MMSI {times(len(ch))}"
        out.append(_Cat("identity", sev, _cap(core) + ".", core, (str(len(ch)), f"identity {plural(len(ch), 'change')}")))

    med = [f for f in gaps if f.severity == "medium"]
    if med and not hi:
        n = len(med)
        core = f"went dark at sea for {hours_text(med[0].hours)}" if n == 1 else f"went dark at sea {times(n)}, {hours_text(sum(f.hours for f in med))} in all"
        out.append(_Cat("gaps", "medium", _cap(core) + ".", core, (f"{round(total_h)} h", "with AIS off")))

    jumps = by.get("Position jump", [])
    if jumps:
        n = len(jumps)
        jam = any(f.meta.get("jamming") for f in jumps)
        core = f"reported {word(n)} position {plural(n, 'jump')}" + (", consistent with GPS jamming" if jam else "")
        out.append(_Cat("jumps", "medium", _cap(core) + ".", core, (str(n), f"position {plural(n, 'jump')}")))
    return out


def lists_text(lists: Optional[list[str]], conj: str = "or") -> str:
    """'OFAC, EU or UK' for the lists actually loaded, in the usual order."""
    names = [LIST_SHORT.get(x, x) for x in LIST_ORDER if x in (lists or [])] + [x for x in (lists or []) if x not in LIST_ORDER]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + f" {conj} " + names[-1]


def build(a: Analysis, sanctions_checked: bool = True, lists: Optional[list[str]] = None) -> dict[str, Any]:
    """`sanctions_checked`: the server holds downloaded sanctions lists. Without them the page must not say "not listed".
    `lists`: which ones, so the sentence names only lists that were really checked."""
    if lists is None:
        lists = list(LIST_ORDER) if sanctions_checked else []
    days = history_days(a)
    sev = a.sev
    cats = _categories(a)
    high = [c for c in cats if c.severity == "high"]
    medium = [c for c in cats if c.severity == "medium"]
    thin = days < MIN_DAYS or len(a.track) < MIN_FIXES
    if high:
        level = "high"
    elif medium:
        level = "review"
    elif thin:
        level = "insufficient"
    else:
        level = "clear"

    detail: Optional[str] = None
    if level in ("high", "review"):
        ranked = high + medium
        primary = ranked[0]
        sentence = primary.sentence
        rest = [c.fragment for c in ranked[1:3]]
        if rest:
            detail = "It also " + join_and(rest) + "."
    elif level == "insufficient":
        d = round(days)
        sentence = "No positions yet." if not a.track else (f"Only {d} {plural(d, 'day')} of positions so far." if d >= 1 else "Only a few hours of positions so far.")
        detail = (f"Not on the {lists_text(lists)} sanctions {plural(len(lists), 'list')}. Behaviour checks need a few weeks of voyages." if sanctions_checked and lists else
                  "Behaviour checks need a few weeks of voyages. Sanctions lists haven't been downloaded to this server yet.")
    else:
        sentence = f"Nothing found in {round(days / 30.4)} months of positions." if days >= 60 else f"Nothing found in {round(days)} days of positions."
        info_gaps = [f for f in a.flags if f.rule == "AIS gap" and f.severity == "info"]
        if info_gaps:
            detail = f"{_cap(word(len(info_gaps)))} quiet {plural(len(info_gaps), 'period')} fell outside receiver coverage, so {plural(len(info_gaps), 'it does', 'they do')} not count."

    n_findings = sev.get("high", 0) + sev.get("medium", 0)
    span = "12 months" if days >= 330 else (f"{round(days / 30.4)} months" if days >= 60 else f"{max(0, round(days))} {plural(max(0, round(days)), 'day')}")
    meta = f"{n_findings} {plural(n_findings, 'finding')}, {span}" if n_findings else f"{span} of positions"

    tiles: list[dict[str, Any]] = [{"value": c.tile[0], "label": c.tile[1], "risk": c.severity in ("high", "medium")} for c in (high + medium) if c.tile][:3]
    neutral = [(str(len(a.voyages)), plural(len(a.voyages), "voyage")), (str(len(a.port_calls)), plural(len(a.port_calls), "port call")),
               (str(round(days)), plural(round(days), "day") + " of history")]
    for v, lab in neutral:
        if len(tiles) >= 3:
            break
        if not any(t["label"] == lab for t in tiles):
            tiles.append({"value": v, "label": lab, "risk": False})

    headline = sentence.rstrip(".") if level in ("high", "review") else None
    return {"level": level, "label": LABELS[level], "sentence": sentence, "detail": detail, "meta": meta, "tiles": tiles,
            "historyDays": round(days, 1), "historyFrom": a.track[0].t if a.track else None, "findings": n_findings, "headline": headline}


def risk_row(a: Analysis, v: dict[str, Any]) -> dict[str, Any]:
    """What the region overview needs about a ship, stored after every analysis."""
    return {"name": a.vessel.name, "level": v["level"], "high": a.sev.get("high", 0), "medium": a.sev.get("medium", 0), "info": a.sev.get("info", 0),
            "headline": v.get("headline"), "sentence": v["sentence"], "sanctioned": bool(a.vessel.sanctions), "history_days": v["historyDays"]}


# ---------------------------------------------------------------- one plain line per finding, for the timeline
_SEAS: Optional[list] = None


def sea_at(lon: float, lat: float) -> Optional[str]:
    """Name of the sea at a point (Natural Earth marine areas), the smallest one that contains it."""
    global _SEAS
    if _SEAS is None:
        import json
        from pathlib import Path
        try:
            raw = json.loads((Path(__file__).parent / "data" / "seas.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = []

        def area(r):
            return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2
        _SEAS = sorted(((s["name"], ring, area(ring)) for s in raw for ring in s["rings"]), key=lambda x: x[2])
    for name, ring, _ in _SEAS:
        inside = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
                inside = not inside
            j = i
        if inside:
            return name
    return None


def _place(ref, lon: float, lat: float, region: Optional[str], port_within: float = 60) -> str:
    """'off Sevastopol', '40 nm from Istanbul' or 'in the Aegean Sea' — the nearest known port or the sea, in words."""
    if ref is None or lon is None or lat is None:
        return "at sea"
    p, nm = ref.nearest_port(lon, lat, region)
    if p is not None and nm < 3:
        return f"at {p.name}"
    if p is not None and nm < 25:
        return f"off {p.name}"
    sea = sea_at(lon, lat)
    if sea and (p is None or nm > port_within):
        return f"in the {sea}"
    if p is None:
        return "at sea"
    return f"{round(nm)} nm from {p.name}"


def story(f: Flag, a: Analysis, ref=None) -> dict[str, str]:
    """A short title and one sentence for a finding, written by fixed rules from its facts."""
    from app.engine.geo import nm_dist
    m = f.meta or {}
    region = a.vessel.region
    dur_h = ((f.t1 or f.t0) - f.t0) / 3_600_000
    if f.rule == "AIS gap":
        before = f.evidence_before[-1] if f.evidence_before else None
        after = f.evidence_after[0] if f.evidence_after else None
        if f.severity == "info":
            return {"title": f"No AIS for {hours_text(f.hours)}", "text": "Outside our receivers' coverage, so it doesn't count as going dark."}
        if before and after:
            moved = round(nm_dist(before.lat, before.lon, after.lat, after.lon))
            a_txt = _place(ref, before.lon, before.lat, region)
            b_moored = after.sog < 0.5 and after.nav in (1, 5)
            p, pnm = (ref.nearest_port(after.lon, after.lat, region) if ref else (None, 99))
            b_txt = f"already {'moored' if after.nav == 5 else 'at anchor'} {('in ' + p.name) if p and pnm < 5 else _place(ref, after.lon, after.lat, region)}" if b_moored else _place(ref, after.lon, after.lat, region)
            near = f" Near {m.get('zone')}." if m.get("near") and m.get("zone") else ""
            return {"title": f"AIS off for {hours_text(f.hours)}", "text": f"Went dark {a_txt}, back on {b_txt}, {moved} nm away.{near}"}
        return {"title": f"AIS off for {hours_text(f.hours)}", "text": "No positions while at sea."}
    if f.rule == "Call at a sensitive port":
        verb = "Anchored off" if m.get("anchorage") else "Called at"
        days = dur_h / 24
        stay = f"{days:.1f} days" if days >= 1 else f"{round(dur_h)} hours"
        return {"title": f"{verb} {m.get('port') or 'a port'}", "text": f"{_cap(m.get('zone') or 'A sensitive zone')}, a sanctioned area. {stay} {'at anchor' if m.get('anchorage') else 'alongside'}."}
    if f.rule == "Possible ship-to-ship transfer":
        return {"title": f"Stopped beside {m.get('partner') or 'another ship'}",
                "text": f"{hours_text(m.get('hours') or dur_h)} at sea, {_place(ref, f.lon, f.lat, region, 150)}, both under 1 knot. A possible ship-to-ship transfer."}
    if f.rule == "Draught change at sea":
        d = m.get("delta") or 0
        return {"title": f"Draught {'fell' if d < 0 else 'rose'} {abs(d):.1f} m at sea",
                "text": f"{m.get('from')} m to {m.get('to')} m with no port call between, {_place(ref, f.lon, f.lat, region, 150)}. An indicator, not proof."}
    if f.rule == "Position jump":
        jam = m.get("jamming")
        return {"title": f"Position jumped at {m.get('kn')} knots",
                "text": f"Inside a known GPS-jamming area ({jam}), so likely interference." if jam else "Outside the known jamming areas: check the receiver or the ship's GPS."}
    if f.rule == "Identity change":
        ch = m.get("changes") or []
        names = [c for c in ch if c["field"] == "name"]
        flags_ = [c for c in ch if c["field"] == "flag"]
        mm = [c for c in ch if c["field"] == "mmsi"]
        title = "Renamed and reflagged" if names and flags_ else "Renamed" if names else "Reflagged" if flags_ else "New MMSI" if mm else "Identity changed"
        bits = []
        if names:
            bits.append(f"{names[0]['from']} became {names[-1]['to']}.")
        if flags_:
            bits.append(f"Flag {flags_[0]['from']} to {flags_[-1]['to']}{', new MMSI' if mm else ''}.")
        elif mm:
            bits.append(f"MMSI {mm[0]['from']} to {mm[-1]['to']}.")
        return {"title": title, "text": " ".join(bits) or "Name, flag or MMSI changed."}
    if f.rule == "Sanctions hit":
        lists = [x for x in LIST_ORDER if x in (m.get("lists") or [])] or (m.get("lists") or [])
        return {"title": f"On the {join_and(lists)} {plural(len(lists), 'list')}", "text": f.lines[0] if f.lines else "Listed by IMO number."}
    return {"title": f.title, "text": f.lines[0] if f.lines else ""}
