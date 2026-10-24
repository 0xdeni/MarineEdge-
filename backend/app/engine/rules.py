"""Step 7: the seven red-flag rules. Each rule is a function (ctx) -> list[Flag] and shows its evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from .geo import fmt_dm, nm_dist
from .refdata import RefData
from .rules_config import Rules
from .types import H, YEAR, Flag, PortCall, Position, Vessel

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_dt(t: int) -> str:
    d = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
    return f"{d.day} {MON[d.month - 1]} {d.hour:02d}:{d.minute:02d}"


def fmt_dy(t: int) -> str:
    d = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
    return f"{d.day} {MON[d.month - 1]} {d.year}"


def fmt_dur(ms: float) -> str:
    h = ms / H
    if h < 48:
        return f"{round(h)} h"
    days = h / 24
    return f"{days:.1f} d" if days < 10 else f"{days:.0f} d"


# A neighbour returned by the provider's get_vessels_near: (vessel, t0, t1)
Neighbour = tuple[Vessel, int, int]
NearFn = Callable[[float, float, float, int, int], list[Neighbour]]


@dataclass
class Ctx:
    vessel: Vessel
    track: list[Position]
    port_calls: list[PortCall]
    in_port: list[bool]
    ref: RefData
    rules: Rules
    now: int
    vessels_near: Optional[NearFn] = None
    coverage: Optional[Callable[[float, float], int]] = None   # fixes per cell near a point (terrestrial feeds only)


# ---------------------------------------------------------------- rule 1: sanctions
def rule_sanctions(c: Ctx) -> list[Flag]:
    """A listing in force is a hit however long ago it began: store.list_sanctions returns only listings still
    on the lists the server downloads, and `t` is the earliest date the server saw it there (or the listing date
    when the source gives one). Ships removed from a list are not tracked yet (docs/STATUS.md, next steps)."""
    hits = [s for s in c.vessel.sanctions if s["t"] <= c.now]
    if not hits:
        return []
    lists = " and ".join(h["list"] for h in hits)
    lines = [" · ".join(x for x in (h["list"], h.get("programme") or "", f"on the list since at least {fmt_dy(h['t'])}") if x) for h in hits]
    lines.append(f"Screened against {', '.join(c.rules.sanctions.lists)} lists")
    return [Flag(rule="Sanctions hit", severity="high", vessel_level=True, t0=hits[0]["t"],
                 title=f"IMO {c.vessel.imo} on {lists} list{'s' if len(hits) > 1 else ''}", lines=lines,
                 meta={"lists": [h["list"] for h in hits]})]


# ---------------------------------------------------------------- rule 2: sensitive port
def rule_sensitive_port(c: Ctx) -> list[Flag]:
    out = []
    for pc in c.port_calls:
        z = None
        if pc.port.zone and pc.port.zone in c.ref.zone_by_id and c.ref.zone_by_id[pc.port.zone].enabled:
            z = c.ref.zone_by_id[pc.port.zone]
        else:
            z = c.ref.zone_at(pc.lon, pc.lat)
        if z is None:
            continue
        out.append(Flag(rule="Call at a sensitive port", severity="high", t0=pc.arrive, t1=pc.depart, lat=pc.lat, lon=pc.lon, port_call=pc,
                        title=f"{'Anchored' if pc.anchorage else 'Called'} at {pc.port.name}",
                        lines=[f"{z.name} · {z.basis}",
                               f"Arrived {fmt_dt(pc.arrive)}, departed {fmt_dt(pc.depart)} UTC · {fmt_dur(pc.depart - pc.arrive)}",
                               f"Draught in {pc.draught_in} m · out {pc.draught_out} m"],
                        meta={"zone": z.short or z.name, "zone_id": z.id, "port": pc.port.name, "anchorage": pc.anchorage}))
    return out


# ---------------------------------------------------------------- rule 3: AIS gap
def rule_ais_gap(c: Ctx) -> list[Flag]:
    out = []
    r = c.rules.ais_gap
    for i in range(1, len(c.track)):
        a, b = c.track[i - 1], c.track[i]
        dt = b.t - a.t
        # Only a gap that lies wholly inside one port stay is harmless. Going dark at sea and reappearing
        # moored in a port (or the reverse) is exactly what this rule is for, so those count.
        if dt < r.min_hours * H or (c.in_port[i - 1] and c.in_port[i]):
            continue
        zone, znm = c.ref.nearest_zone(a.lon, a.lat)
        zone_b, znm_b = c.ref.nearest_zone(b.lon, b.lat)
        hours = dt / H
        high = hours > r.high_hours or min(znm, znm_b) <= r.near_sensitive_nm
        severity, title = ("high" if high else "medium"), f"AIS gap of {round(hours)} hours"
        back = f"Reappeared {round(nm_dist(a.lat, a.lon, b.lat, b.lon))} nm away"
        if zone_b is not None and znm_b < znm:
            back += f" · {'inside ' + zone_b.name if znm_b == 0 else f'{round(znm_b)} nm from {zone_b.name}'}"
        lines = [f"Off {fmt_dt(a.t)}, back on {fmt_dt(b.t)} UTC",
                 f"Last position {fmt_dm(a.lat, a.lon)} · {round(znm)} nm from {zone.name if zone else 'any sensitive zone'}",
                 f"{back} · {'satellite' if a.src == 'S' else 'terrestrial'} AIS before the gap"]
        if c.coverage is not None:
            cov = min(c.coverage(a.lon, a.lat), c.coverage(b.lon, b.lat))
            min_fixes = int(r.get("coverage_min_fixes", 50) or 0)
            if cov < min_fixes and hours <= r.get("coverage_max_hours", 72):
                severity, title = "info", f"No AIS received for {round(hours)} hours (outside receiver coverage)"
                lines.append(f"Receiver coverage at the last position: {cov} fixes in 30 days (below {min_fixes}); terrestrial feeds do not see open sea. Not treated as a deliberate gap.")
            else:
                lines.append(f"Receiver coverage at the last position: {cov} fixes in 30 days")
        nz, nnm = (zone_b, znm_b) if (zone_b is not None and znm_b < znm) else (zone, znm)
        out.append(Flag(rule="AIS gap", severity=severity, t0=a.t, t1=b.t, lat=a.lat, lon=a.lon, hours=hours, title=title, lines=lines,
                        evidence_before=c.track[max(0, i - 3):i], evidence_after=c.track[i:i + 3],
                        meta={"hours": round(hours, 1), "zone": (nz.short or nz.name) if nz else None, "zone_nm": round(nnm) if nz else None,
                              "near": bool(nz is not None and nnm <= r.near_sensitive_nm), "coverage": severity == "info"}))
    return out


# ---------------------------------------------------------------- rule 4: draught change at sea
def _slow_stretches(c: Ctx, i0: int, i1: int, max_kn: float, min_h: float) -> list[tuple[int, int]]:
    """Stretches of fixes i0..i1 (inclusive) slower than max_kn for at least min_h hours, outside port calls."""
    out = []
    i = i0
    while i <= i1:
        if c.track[i].sog < max_kn and not c.in_port[i]:
            j = i
            while j + 1 <= i1 and c.track[j + 1].sog < max_kn and not c.in_port[j + 1] and c.track[j + 1].t - c.track[j].t < 6 * H:
                j += 1
            if c.track[j].t - c.track[i].t >= min_h * H:
                out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def _draught_cause(c: Ctx, i0: int, i1: int) -> tuple[str, dict]:
    """What happened at sea between fixes i0 and i1 that could have moved cargo: a stop ("stop"), a period with AIS
    off where receivers can hear ("dark"), or only a period out of receiver range ("unheard"). "underway" when none."""
    sts, gap = c.rules.sts, c.rules.ais_gap
    stops = _slow_stretches(c, i0, i1, float(sts.max_speed_kn), float(sts.min_hours))
    if stops:
        a, b = max(stops, key=lambda s: c.track[s[1]].t - c.track[s[0]].t)
        return "stop", {"t0": c.track[a].t, "t1": c.track[b].t, "hours": round((c.track[b].t - c.track[a].t) / H, 1)}
    best = None
    for k in range(i0 + 1, i1 + 1):
        x, y = c.track[k - 1], c.track[k]
        hours = (y.t - x.t) / H
        if hours < gap.min_hours:
            continue
        unheard = False
        if c.coverage is not None:
            cov = min(c.coverage(x.lon, x.lat), c.coverage(y.lon, y.lat))
            unheard = cov < int(gap.get("coverage_min_fixes", 50) or 0) and hours <= gap.get("coverage_max_hours", 72)
        kind = "unheard" if unheard else "dark"
        if best is None or (kind == "dark" and best[0] == "unheard") or (kind == best[0] and hours > best[1]["hours"]):
            best = (kind, {"t0": x.t, "t1": y.t, "hours": round(hours, 1)})
    return best or ("underway", {})


def rule_draught(c: Ctx) -> list[Flag]:
    """Compares each reported draught with the last one known before it, at sea. A draught of 0 is "not known" in
    AIS (a recorded feed hears positions before a ship's static message), so it never counts as a value; a port call
    in between explains any change and starts the comparison afresh.

    Cargo moves only while a ship is stopped, so with `after_stop_or_dark_only` (the default) a change is a red flag
    when the ship stopped at sea or went dark since its last port call (or since the previous change). A change typed
    in while it was under way all along is the crew entering the last port's cargo late, and one after a period out
    of receiver range may follow a port call nobody heard: both are shown as Info and not counted."""
    out = []
    r = c.rules.draught_change
    strict = bool(r.get("after_stop_or_dark_only", True))
    last: Optional[int] = None      # the last fix at sea with a known draught
    since = 0                       # where to look for a cause: after the last port call or the last change
    left: Optional[PortCall] = None
    calls = iter(c.port_calls)
    nxt = next(calls, None)
    for i, b in enumerate(c.track):
        if c.in_port[i]:
            while nxt is not None and nxt.i1 < i:
                nxt = next(calls, None)
            left = nxt
            last, since = None, i + 1
            continue
        if b.jump or not b.draught or b.draught <= 0:
            continue
        if last is not None:
            a = c.track[last]
            d = b.draught - a.draught
            if abs(d) >= r.min_meters:
                cause, info = _draught_cause(c, since, i) if strict else ("", {})
                high = cause in ("", "stop", "dark")
                port, pnm = c.ref.nearest_port(b.lon, b.lat, c.vessel.region)
                lines = [f"{fmt_dt(b.t)} UTC · {fmt_dm(b.lat, b.lon)} · {round(pnm)} nm from {port.name if port else 'nearest port'}",
                         f"Reported draught {a.draught} m → {b.draught} m with no port call in between"]
                meta = {"delta": round(d, 1), "from": a.draught, "to": b.draught, "cause": cause or None}
                if cause == "stop":
                    lines.append(f"After a stop at sea: {fmt_dur(info['t1'] - info['t0'])} slower than {c.rules.sts.max_speed_kn} kn, {fmt_dt(info['t0'])} – {fmt_dt(info['t1'])} UTC")
                elif cause == "dark":
                    lines.append(f"After {round(info['hours'])} hours with no AIS, {fmt_dt(info['t0'])} – {fmt_dt(info['t1'])} UTC")
                elif cause == "unheard":
                    lines.append(f"After {round(info['hours'])} hours outside receiver coverage: a port call there may not have been heard. Not counted.")
                elif cause == "underway":
                    if left is not None:
                        since_h = (b.t - left.depart) / H
                        meta.update({"port": left.port.name, "since_h": round(since_h, 1)})
                        lines.append(f"Typed in while under way, {fmt_dur(b.t - left.depart)} after leaving {left.port.name}: most likely that call's cargo, entered late. Not counted.")
                    else:
                        lines.append("Typed in while under way, with no stop or port call on record before it. Not counted.")
                meta.update({k: info[k] for k in ("hours",) if k in info})
                lines.append("Draught is typed in by the crew: indicator, not proof")
                sign = "+" if d > 0 else ""
                title = (f"Draught {sign}{d:.1f} m at sea" if high else
                         f"Draught {sign}{d:.1f} m after no reception" if cause == "unheard" else f"Draught {sign}{d:.1f} m typed in under way")
                out.append(Flag(rule="Draught change at sea", severity="high" if high else "info", t0=b.t, t1=b.t, lat=b.lat, lon=b.lon,
                                title=title, lines=lines, evidence_before=c.track[max(0, i - 3):i], evidence_after=c.track[i:i + 3], meta=meta))
                since = i
        last = i
    return out


# ---------------------------------------------------------------- rule 5: ship-to-ship transfer
def rule_sts(c: Ctx) -> list[Flag]:
    out = []
    r = c.rules.sts
    if c.vessels_near is None:
        return out
    n = len(c.track)
    i = 0
    lookups = 0
    cap = int(r.get("max_lookups_per_vessel", 12) or 0)
    alongside_m = float(r.get("alongside_max_dist_m", r.max_dist_m) or r.max_dist_m)
    need_imo = bool(r.get("partner_needs_imo", True))
    while i < n:
        if cap and lookups >= cap:
            break
        if c.track[i].sog < r.max_speed_kn and not c.in_port[i]:
            j = i
            while j + 1 < n and c.track[j + 1].sog < r.max_speed_kn and not c.in_port[j + 1] and c.track[j + 1].t - c.track[j].t < 6 * H:
                j += 1
            t0, t1 = c.track[i].t, c.track[j].t
            if t1 - t0 >= r.min_hours * H:
                mid = c.track[(i + j) // 2]
                stop = c.track[i:j + 1]
                # At anchor or moored for most of the stop: a transfer needs the other ship alongside. In a busy
                # anchorage, ships 300–500 m apart are only neighbours swinging on their chains.
                still = 2 * sum(1 for p in stop if p.nav in (1, 5)) >= len(stop)
                radius = min(alongside_m, float(r.max_dist_m)) if still else float(r.max_dist_m)
                lookups += 1
                for other, n0, n1 in c.vessels_near(mid.lat, mid.lon, radius, t0, t1):
                    if other.imo == c.vessel.imo or n1 - n0 < r.min_hours * H:
                        continue
                    if need_imo and not other.imo:
                        continue                      # tugs, pilot boats and harbour craft broadcast no IMO number
                    port, pnm = c.ref.nearest_port(mid.lon, mid.lat, c.vessel.region)
                    out.append(Flag(rule="Possible ship-to-ship transfer", severity="high", t0=t0, t1=t1, lat=mid.lat, lon=mid.lon, partner_imo=other.imo,
                                    title=f"Possible STS with {other.name}",
                                    lines=[f"{fmt_dt(t0)} – {fmt_dt(t1)} UTC · {fmt_dur(t1 - t0)} both under {r.max_speed_kn} kn, within {radius:g} m"
                                           + (" (at anchor or moored: alongside)" if still else ""),
                                           f"{other.name} · IMO {other.imo} · {other.flag} · {other.sub}",
                                           f"{fmt_dm(mid.lat, mid.lon)} · {round(pnm)} nm from {port.name if port else 'nearest port'}, outside port limits"],
                                    evidence_before=c.track[max(0, i - 2):i + 1], evidence_after=c.track[j:j + 3],
                                    meta={"partner": other.name, "partner_imo": other.imo, "hours": round((t1 - t0) / H, 1), "alongside": still}))
            i = j + 1
        else:
            i += 1
    return out


# ---------------------------------------------------------------- rule 6: position jump
def _jumps(c: Ctx) -> list[tuple[int, float, float]]:
    """(index, implied knots, hours) of each fix impossibly far from the one before. The fix back on track after
    it belongs to the same event and is not listed."""
    out = []
    i = 1
    while i < len(c.track):
        a, b = c.track[i - 1], c.track[i]
        dt = (b.t - a.t) / H
        if dt > 0:
            kn = nm_dist(a.lat, a.lon, b.lat, b.lon) / dt
            if kn > c.rules.position_jump.max_implied_kn:
                out.append((i, kn, dt))
                i += 1  # the return fix belongs to the same event
        i += 1
    return out


def rule_jump(c: Ctx) -> list[Flag]:
    out = []
    for i, kn, dt in _jumps(c):
        a, b = c.track[i - 1], c.track[i]
        jam = c.ref.jamming_at(b.lon, b.lat)
        b.jump = True
        out.append(Flag(rule="Position jump", severity="medium", t0=b.t, t1=b.t, lat=b.lat, lon=b.lon,
                        title=f"Position jump, {round(kn)} knots",
                        lines=[f"{fmt_dt(b.t)} UTC · fix at {fmt_dm(b.lat, b.lon)}, {round(nm_dist(a.lat, a.lon, b.lat, b.lon))} nm from the previous fix {round(dt * 60)} min earlier",
                               f"Inside a known GPS jamming area ({jam['name']}) · possible GPS jamming" if jam else "Outside known jamming areas · check the receiver"],
                        evidence_before=c.track[max(0, i - 2):i], evidence_after=c.track[i:i + 3],
                        meta={"kn": round(kn), "jamming": jam["name"] if jam else None}))
    return out


# ---------------------------------------------------------------- rule 7: identity change
def rule_identity(c: Ctx) -> list[Flag]:
    ch = sorted([h for h in c.vessel.history if h["t"] >= c.now - YEAR], key=lambda h: h["t"])
    if not ch:
        return []
    label = {"name": "Name", "flag": "Flag", "mmsi": "MMSI"}
    sev = "medium" if len(ch) > c.rules.identity.medium_if_more_than else "info"
    return [Flag(rule="Identity change", severity=sev, vessel_level=True, t0=ch[0]["t"],
                 title=f"{len(ch)} identity change{'s' if len(ch) > 1 else ''} in 12 months",
                 lines=[f"{fmt_dy(h['t'])} · {label.get(h['field'], h['field'])} {h['from']} → {h['to']}" for h in ch],
                 meta={"changes": [{"field": h["field"], "from": h["from"], "to": h["to"], "t": h["t"]} for h in ch]})]


RULES: list[tuple[str, Callable[[Ctx], list[Flag]]]] = [
    ("sanctions", rule_sanctions),
    ("sensitive_port", rule_sensitive_port),
    ("ais_gap", rule_ais_gap),
    ("draught", rule_draught),
    ("sts", rule_sts),
    ("jump", rule_jump),
    ("identity", rule_identity),
]


def run_rules(c: Ctx) -> list[Flag]:
    for i, _, _ in _jumps(c):
        c.track[i].jump = True      # marked first: the draught rule runs before the jump rule and leaves these out
    flags: list[Flag] = []
    for _, fn in RULES:
        flags.extend(fn(c))
    return flags
