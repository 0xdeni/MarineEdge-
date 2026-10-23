"""Step 7: the seven red-flag rules. Each rule is a function (ctx) -> list[Flag] and shows its evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from .geo import fmt_dm, nm_dist
from .refdata import RefData
from .rules_config import Rules
from .types import D, H, YEAR, Flag, PortCall, Position, Vessel

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


# ---------------------------------------------------------------- rule 1: sanctions
def rule_sanctions(c: Ctx) -> list[Flag]:
    lookback = c.rules.sanctions.lookback_months * 30.4 * D
    hits = [s for s in c.vessel.sanctions if s["t"] <= c.now and s["t"] >= c.now - lookback]
    if not hits:
        return []
    lists = " and ".join(h["list"] for h in hits)
    lines = [f"{h['list']} · listed {fmt_dy(h['t'])} · {h['programme']}" for h in hits]
    lines.append(f"Screened against {', '.join(c.rules.sanctions.lists)} lists")
    return [Flag(rule="Sanctions hit", severity="high", vessel_level=True, t0=hits[0]["t"],
                 title=f"IMO {c.vessel.imo} on {lists} list{'s' if len(hits) > 1 else ''}", lines=lines)]


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
                               f"Draught in {pc.draught_in} m · out {pc.draught_out} m"]))
    return out


# ---------------------------------------------------------------- rule 3: AIS gap
def rule_ais_gap(c: Ctx) -> list[Flag]:
    out = []
    r = c.rules.ais_gap
    for i in range(1, len(c.track)):
        a, b = c.track[i - 1], c.track[i]
        dt = b.t - a.t
        if dt < r.min_hours * H or c.in_port[i - 1] or c.in_port[i]:
            continue
        zone, znm = c.ref.nearest_zone(a.lon, a.lat)
        hours = dt / H
        high = hours > r.high_hours or znm <= r.near_sensitive_nm
        out.append(Flag(rule="AIS gap", severity="high" if high else "medium", t0=a.t, t1=b.t, lat=a.lat, lon=a.lon, hours=hours,
                        title=f"AIS gap of {round(hours)} hours",
                        lines=[f"Off {fmt_dt(a.t)}, back on {fmt_dt(b.t)} UTC",
                               f"Last position {fmt_dm(a.lat, a.lon)} · {round(znm)} nm from {zone.name if zone else 'any sensitive zone'}",
                               f"Reappeared {round(nm_dist(a.lat, a.lon, b.lat, b.lon))} nm away · {'satellite' if a.src == 'S' else 'terrestrial'} AIS before the gap"],
                        evidence_before=c.track[max(0, i - 3):i], evidence_after=c.track[i:i + 3]))
    return out


# ---------------------------------------------------------------- rule 4: draught change at sea
def rule_draught(c: Ctx) -> list[Flag]:
    out = []
    for i in range(1, len(c.track)):
        a, b = c.track[i - 1], c.track[i]
        d = b.draught - a.draught
        if abs(d) < c.rules.draught_change.min_meters or c.in_port[i - 1] or c.in_port[i] or b.jump:
            continue
        port, pnm = c.ref.nearest_port(b.lon, b.lat, c.vessel.region)
        out.append(Flag(rule="Draught change at sea", severity="high", t0=b.t, t1=b.t, lat=b.lat, lon=b.lon,
                        title=f"Draught {'+' if d > 0 else ''}{d:.1f} m at sea",
                        lines=[f"{fmt_dt(b.t)} UTC · {fmt_dm(b.lat, b.lon)} · {round(pnm)} nm from {port.name if port else 'nearest port'}",
                               f"Reported draught {a.draught} m → {b.draught} m with no port call in between",
                               "Draught is typed in by the crew: indicator, not proof"],
                        evidence_before=c.track[max(0, i - 3):i], evidence_after=c.track[i:i + 3]))
    return out


# ---------------------------------------------------------------- rule 5: ship-to-ship transfer
def rule_sts(c: Ctx) -> list[Flag]:
    out = []
    r = c.rules.sts
    if c.vessels_near is None:
        return out
    n = len(c.track)
    i = 0
    while i < n:
        if c.track[i].sog < r.max_speed_kn and not c.in_port[i]:
            j = i
            while j + 1 < n and c.track[j + 1].sog < r.max_speed_kn and not c.in_port[j + 1] and c.track[j + 1].t - c.track[j].t < 6 * H:
                j += 1
            t0, t1 = c.track[i].t, c.track[j].t
            if t1 - t0 >= r.min_hours * H:
                mid = c.track[(i + j) // 2]
                for other, n0, n1 in c.vessels_near(mid.lat, mid.lon, r.max_dist_m, t0, t1):
                    if other.imo == c.vessel.imo or n1 - n0 < r.min_hours * H:
                        continue
                    port, pnm = c.ref.nearest_port(mid.lon, mid.lat, c.vessel.region)
                    out.append(Flag(rule="Possible ship-to-ship transfer", severity="high", t0=t0, t1=t1, lat=mid.lat, lon=mid.lon, partner_imo=other.imo,
                                    title=f"Possible STS with {other.name}",
                                    lines=[f"{fmt_dt(t0)} – {fmt_dt(t1)} UTC · {fmt_dur(t1 - t0)} both under {r.max_speed_kn} kn, within {r.max_dist_m} m",
                                           f"{other.name} · IMO {other.imo} · {other.flag} · {other.sub}",
                                           f"{fmt_dm(mid.lat, mid.lon)} · {round(pnm)} nm from {port.name if port else 'nearest port'}, outside port limits"],
                                    evidence_before=c.track[max(0, i - 2):i + 1], evidence_after=c.track[j:j + 3]))
            i = j + 1
        else:
            i += 1
    return out


# ---------------------------------------------------------------- rule 6: position jump
def rule_jump(c: Ctx) -> list[Flag]:
    out = []
    i = 1
    while i < len(c.track):
        a, b = c.track[i - 1], c.track[i]
        dt = (b.t - a.t) / H
        if dt > 0:
            kn = nm_dist(a.lat, a.lon, b.lat, b.lon) / dt
            if kn > c.rules.position_jump.max_implied_kn:
                jam = c.ref.jamming_at(b.lon, b.lat)
                b.jump = True
                out.append(Flag(rule="Position jump", severity="medium", t0=b.t, t1=b.t, lat=b.lat, lon=b.lon,
                                title=f"Position jump, {round(kn)} knots",
                                lines=[f"{fmt_dt(b.t)} UTC · fix at {fmt_dm(b.lat, b.lon)}, {round(nm_dist(a.lat, a.lon, b.lat, b.lon))} nm from the previous fix {round(dt * 60)} min earlier",
                                       f"Inside a known GPS jamming area ({jam['name']}) · possible GPS jamming" if jam else "Outside known jamming areas · check the receiver"],
                                evidence_before=c.track[max(0, i - 2):i], evidence_after=c.track[i:i + 3]))
                i += 1  # the return fix belongs to the same event
        i += 1
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
                 lines=[f"{fmt_dy(h['t'])} · {label.get(h['field'], h['field'])} {h['from']} → {h['to']}" for h in ch])]


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
    flags: list[Flag] = []
    for _, fn in RULES:
        flags.extend(fn(c))
    return flags
