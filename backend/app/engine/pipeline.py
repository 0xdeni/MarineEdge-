"""The eight steps, 3 to 8: fetch (caller) → clean → port calls → voyages → rules → status.
analyze() is pure: give it a vessel, a raw track and the reference data and it returns an Analysis."""
from __future__ import annotations

import time
from typing import Optional

from .clean import clean_track
from .portcalls import detect_port_calls
from .refdata import RefData
from .rules import Ctx, NearFn, run_rules
from .rules_config import Rules
from .types import H, Analysis, Position, Status, Vessel
from .voyages import split_voyages


def derive_status(track: list[Position], voyages, calls, ref: RefData, region: str, destination: str = "", eta: Optional[int] = None) -> Status:
    """Live status from the end of the track. AIS destination/ETA come from the provider when known."""
    if not track:
        return Status(state="unknown")
    last = track[-1]
    cur = voyages[-1] if voyages and voyages[-1].current else None
    last_call = calls[-1] if calls else None
    if cur is not None and last.sog >= 0.5:
        return Status(state="underway", destination=destination, eta=eta, since=cur.depart,
                      last_port=last_call.port if last_call else None)
    if last_call is not None and last_call.i1 >= len(track) - 1:
        state = "anchored" if last_call.anchorage else "moored"
        return Status(state=state, destination=destination, eta=eta, since=last_call.arrive, port=last_call.port,
                      last_port=calls[-2].port if len(calls) > 1 else None)
    return Status(state="underway" if last.sog >= 0.5 else "moored", destination=destination, eta=eta,
                  since=cur.depart if cur else last.t, last_port=last_call.port if last_call else None)


def analyze(vessel: Vessel, raw: list[Position], ref: RefData, rules: Rules, now: Optional[int] = None,
            vessels_near: Optional[NearFn] = None, destination: str = "", eta: Optional[int] = None, coverage=None) -> Analysis:
    t_start = time.perf_counter()
    now = now if now is not None else int(time.time() * 1000)
    track, dup, bad = clean_track(raw)
    calls = detect_port_calls(track, vessel.region, ref, rules)
    in_port = [False] * len(track)
    for pc in calls:
        for i in range(pc.i0, pc.i1 + 1):
            in_port[i] = True
    ctx = Ctx(vessel=vessel, track=track, port_calls=calls, in_port=in_port, ref=ref, rules=rules, now=now, vessels_near=vessels_near, coverage=coverage)
    flags = run_rules(ctx)
    voyages = split_voyages(track, calls)      # after rules so jump fixes are excluded from distances
    for i, f in enumerate(flags):
        f.id = f"{vessel.imo}-{i}"
        if f.vessel_level:
            continue
        vg = None
        if f.port_call is not None:
            vg = next((v for v in voyages if v.to is f.port_call), None)
        if vg is None:
            vg = next((v for v in voyages if f.t0 >= v.depart - H and (v.arrive is None or f.t0 <= v.arrive + H)), None)
        if vg is None and voyages:
            vg = voyages[-1]
        if vg is not None:
            f.voyage = vg
            vg.flags.append(f)
            if f.rule == "AIS gap":
                vg.dark_h += f.hours
    sev = {"high": 0, "medium": 0, "info": 0}
    for f in flags:
        sev[f.severity] += 1
    status = derive_status(track, voyages, calls, ref, vessel.region, destination, eta)
    stats = {"raw": len(raw), "dup": dup, "bad": bad, "clean": len(track), "port_calls": len(calls),
             "voyages": len(voyages), "flags": len(flags), "ms": round((time.perf_counter() - t_start) * 1000)}
    return Analysis(vessel=vessel, track=track, port_calls=calls, voyages=voyages, flags=flags, status=status, stats=stats, sev=sev)
