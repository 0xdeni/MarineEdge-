"""Orchestration: search → identify → fetch (cached) → analyze → serialise. The API layer is thin
on purpose so the same calls work from a CLI, a scheduled job or a test."""
from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Any, Optional

from app.engine import analyze, load_refdata, load_rules
from app.engine.refdata import RefData
from app.engine.rules_config import Rules
from app.engine.types import YEAR, Analysis, Flag, PortCall, Position, Vessel, Voyage
from app.providers import AISProvider, make_provider
from app.store import Store, make_store

log = logging.getLogger("vvt.service")


class Service:
    def __init__(self, provider: Optional[AISProvider] = None, store: Optional[Store] = None, ref: Optional[RefData] = None, rules: Optional[Rules] = None, now_ms: Optional[int] = None):
        self.ref = ref or load_refdata()
        self.rules = rules or load_rules()
        self.store = store or make_store()
        self.provider = provider or make_provider(ref=self.ref) if provider is None and _is_mock() else (provider or make_provider())
        self.now = now_ms
        self.fetches = 0
        self._cache: dict[int, Analysis] = {}

    # ---- helpers ----
    def _now(self) -> int:
        return self.now or int(time.time() * 1000)

    def reload_rules(self) -> Rules:
        self.rules = load_rules()
        self._cache.clear()
        return self.rules

    def set_zone(self, zone_id: str, enabled: bool) -> None:
        z = self.ref.zone_by_id[zone_id]
        z.enabled = enabled
        self._cache.clear()

    # ---- steps 1-2 ----
    def search(self, q: str):
        return self.provider.search_vessel(q)

    # ---- steps 3-8 ----
    def track(self, imo: int) -> list[Position]:
        """Step 3 with the cache rule: a window is fetched once. On later calls only the uncovered tail
        (from the last fetched moment, with one hour of overlap, to now) is bought."""
        end = self._now()
        start = end - int(self.rules.history_months * 30.4 * 24 * 3_600_000)
        if self.store.covered(imo, start, end):
            return self.store.get_positions(imo, start, end)
        last = self.store.latest_window_end(imo)
        fetch_from = start if last is None or last < start else max(start, last - 3_600_000)
        if end - fetch_from < 15 * 60_000:                       # nothing new to buy yet
            return self.store.get_positions(imo, start, end)
        pts = self.provider.get_track(imo, fetch_from, end)
        credits = getattr(self.provider, "last_credits", 5)
        self.store.put_positions(imo, pts, getattr(self.provider, "name", "provider"), fetch_from, end, credits)
        self.fetches += 1
        return self.store.get_positions(imo, start, end) or pts

    def analysis(self, imo: int, refresh: bool = False) -> Analysis:
        if not refresh and imo in self._cache:
            return self._cache[imo]
        v = self.provider.get_vessel(imo)
        if v is None:
            raise KeyError(imo)
        v.sanctions = v.sanctions or self.store.list_sanctions(imo)
        st = self.provider.get_static(imo)

        def near(lat, lon, r_m, t0, t1):
            return [(n.vessel, n.t0, n.t1) for n in self.provider.get_vessels_near(lat, lon, r_m, t0, t1)]

        a = analyze(v, self.track(imo), self.ref, self.rules, now=self._now(), vessels_near=near, destination=st.destination, eta=st.eta)
        try:
            self.store.save_analysis(a)
        except Exception:  # the analysis is still served if the DB write fails
            log.exception("save_analysis failed for %s", imo)
        self._cache[imo] = a
        return a

    def region(self, bbox: tuple[float, float, float, float]) -> list[dict]:
        out = []
        for v, p in self.provider.get_vessels_in_area(bbox):
            a = self._cache.get(v.imo)
            out.append({"vessel": vessel_json(v), "last": pos_json(p),
                        "flags": len(a.flags) if a else None, "high": a.sev["high"] if a else None,
                        "status": status_json(a) if a else None})
        return out


def _is_mock() -> bool:
    import os
    return os.environ.get("VVT_PROVIDER", "mock").lower() == "mock"


# ---------------------------------------------------------------- JSON shapes (mirror the frontend's)
def pos_json(p: Position) -> dict:
    return {"t": p.t, "lat": round(p.lat, 5), "lon": round(p.lon, 5), "sog": p.sog, "cog": p.cog, "draught": p.draught, "nav": p.nav, "src": p.src, **({"jump": True} if p.jump else {})}


def vessel_json(v: Vessel) -> dict:
    d = asdict(v)
    d["exNames"] = d.pop("ex_names")
    for k_old, k_new in [("draught_loaded", "draughtLoaded"), ("draught_ballast", "draughtBallast"), ("reg_owner", "regOwner"), ("ben_owner", "benOwner"), ("class_soc", "classSoc")]:
        d[k_new] = d.pop(k_old)
    return d


def port_call_json(pc: PortCall) -> dict:
    return {"port": {"id": pc.port.id, "name": pc.port.name, "c": pc.port.country, "b": [pc.port.lon, pc.port.lat], "zone": pc.port.zone, "pseudo": pc.port.pseudo},
            "anchorage": pc.anchorage, "arrive": pc.arrive, "depart": pc.depart, "lat": pc.lat, "lon": pc.lon, "i0": pc.i0, "i1": pc.i1,
            "draughtIn": pc.draught_in, "draughtOut": pc.draught_out, "anchHours": pc.anch_hours}


def flag_json(f: Flag) -> dict:
    return {"id": f.id, "rule": f.rule, "severity": f.severity, "title": f.title, "lines": f.lines, "t0": f.t0, "t1": f.t1, "lat": f.lat, "lon": f.lon,
            "vesselLevel": f.vessel_level, "hours": f.hours, "voyage": f.voyage.n if f.voyage else None, "partnerImo": f.partner_imo,
            "evidence": {"before": [pos_json(p) for p in f.evidence_before], "after": [pos_json(p) for p in f.evidence_after]} if (f.evidence_before or f.evidence_after) else None}


def voyage_json(v: Voyage) -> dict:
    return {"n": v.n, "color": v.color, "from": port_call_json(v.frm) if v.frm else None, "to": port_call_json(v.to) if v.to else None, "i0": v.i0, "i1": v.i1,
            "depart": v.depart, "arrive": v.arrive, "nm": v.nm, "draughtOut": v.draught_out, "draughtIn": v.draught_in, "current": v.current,
            "flags": [f.id for f in v.flags], "darkH": v.dark_h}


def status_json(a: Analysis) -> dict:
    s = a.status
    port = lambda p: {"id": p.id, "name": p.name} if p else None
    return {"state": s.state, "destination": s.destination, "eta": s.eta, "since": s.since, "port": port(s.port), "lastPort": port(s.last_port), "nextPort": port(s.next_port)}


def analysis_json(a: Analysis, include_track: bool = True) -> dict[str, Any]:
    return {"vessel": vessel_json(a.vessel), "track": [pos_json(p) for p in a.track] if include_track else None,
            "portCalls": [port_call_json(pc) for pc in a.port_calls], "voyages": [voyage_json(v) for v in a.voyages],
            "flags": [flag_json(f) for f in a.flags], "sev": a.sev, "status": status_json(a), "stats": a.stats,
            "last": pos_json(a.track[-1]) if a.track else None}
