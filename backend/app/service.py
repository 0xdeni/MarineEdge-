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
from app.engine.types import Analysis, Flag, PortCall, Position, Vessel, Voyage
from app.providers import AISProvider, make_provider
from app.store import Store, make_store

log = logging.getLogger("vvt.service")


class Service:
    def __init__(self, provider: Optional[AISProvider] = None, store: Optional[Store] = None, ref: Optional[RefData] = None, rules: Optional[Rules] = None, now_ms: Optional[int] = None):
        self.ref = ref or load_refdata()
        self.rules = rules or load_rules()
        self.store = store or make_store()
        self._pinned = provider is not None          # tests pass a provider: never swapped by the settings file
        self.provider = provider or self._make(None)
        from app import settings_store
        self._settings_version = settings_store.version()
        self.now = now_ms
        self.fetches = 0
        self._cache: dict[int, Analysis] = {}

    # ---- helpers ----
    def _now(self) -> int:
        return self.now or int(time.time() * 1000)

    def _make(self, name: Optional[str], api_key: Optional[str] = None) -> AISProvider:
        from app import settings_store
        nm = (name or settings_store.provider_name()).lower()
        if nm == "mock":
            return make_provider(nm, api_key=api_key, ref=self.ref)
        if nm == "aisstream":
            return make_provider(nm, store=self.store)
        return make_provider(nm, api_key=api_key)

    def _sync(self) -> None:
        """Rebuild the provider when another worker (or the CLI) changed the settings file."""
        if self._pinned:
            return
        from app import settings_store
        v = settings_store.version()
        if v != self._settings_version:
            self.provider = self._make(None)
            self._settings_version = v
            self._cache.clear()

    def set_provider(self, name: str, api_key: Optional[str] = None) -> dict:
        """Admin action from the app: switch provider and/or key without a restart. The old provider's
        analyses are dropped from the memory cache; stored positions stay (they are keyed on IMO)."""
        from app import settings_store
        settings_store.set_provider(name, api_key)
        self.provider = self._make(name, api_key)
        self._settings_version = settings_store.version()
        self._cache.clear()
        return {"provider": getattr(self.provider, "name", name)}

    def test_provider(self) -> dict:
        """One cheap call to prove the key works: a name search (1 credit on Datalastic, 0 on mock)."""
        self._sync()
        t0 = time.perf_counter()
        try:
            res = self.provider.search_vessel("MAERSK")
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            k = getattr(self.provider, "key", "")
            if k:
                msg = msg.replace(k, "***")
            return {"ok": False, "provider": getattr(self.provider, "name", "?"), "error": msg[:300]}
        return {"ok": True, "provider": getattr(self.provider, "name", "?"), "matches": len(res), "sample": [m.name for m in res[:3]],
                "credits_used": getattr(self.provider, "credits_used", 0), "ms": round((time.perf_counter() - t0) * 1000)}

    def first_pull(self, imos: list[int]) -> list[dict]:
        """The acceptance checklist from docs/PROVIDERS.md, as data for the app or the CLI."""
        out = []
        for imo in imos:
            try:
                a = self.analysis(imo)
            except KeyError:
                out.append({"imo": imo, "ok": False, "error": "unknown IMO for this provider"})
                continue
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                for k in [getattr(self.provider, "key", "")]:
                    if k:
                        msg = msg.replace(k, "***")
                out.append({"imo": imo, "ok": False, "error": msg[:300]})
                continue
            s = a.stats
            start = self._now() - int(self.rules.history_months * 30.4 * 24 * 3_600_000)
            checks = {"hourly positions for a year (≥ 1000)": s["clean"] >= 1000,
                      "draught populated": any(p.draught > 0 for p in a.track),
                      "port calls found (≥ 2)": s["port_calls"] >= 2,
                      "voyages split": s["voyages"] >= 1,
                      "cached for next time": self.store.covered(imo, start, self._now())}
            out.append({"imo": imo, "name": a.vessel.name, "ok": all(checks.values()), "checks": checks, "stats": s, "sev": a.sev, "status": a.status.state})
        return out

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
        self._sync()
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
        self._sync()
        if not refresh and imo in self._cache:
            return self._cache[imo]
        v = self.provider.get_vessel(imo)
        if v is None:
            raise KeyError(imo)
        v.sanctions = v.sanctions or self.store.list_sanctions(imo)
        st = self.provider.get_static(imo)

        def near(lat, lon, r_m, t0, t1):
            return [(n.vessel, n.t0, n.t1) for n in self.provider.get_vessels_near(lat, lon, r_m, t0, t1)]

        cov = getattr(self.provider, "coverage", None)
        a = analyze(v, self.track(imo), self.ref, self.rules, now=self._now(), vessels_near=near, destination=st.destination, eta=st.eta, coverage=cov)
        a.stats["source"] = getattr(self.provider, "name", "provider")
        if cov is not None:                       # recorded feed: history cannot start before the recorder did
            try:
                a.stats["history_since"] = (self.provider.stats() or {}).get("oldest")
            except Exception:  # noqa: BLE001
                a.stats["history_since"] = None
        try:
            self.store.save_analysis(a)
        except Exception:  # the analysis is still served if the DB write fails
            log.exception("save_analysis failed for %s", imo)
        self._cache[imo] = a
        return a

    def region(self, bbox: tuple[float, float, float, float]) -> list[dict]:
        self._sync()
        out = []
        for v, p in self.provider.get_vessels_in_area(bbox):
            a = self._cache.get(v.imo)
            out.append({"vessel": vessel_json(v), "last": pos_json(p),
                        "flags": len(a.flags) if a else None, "high": a.sev["high"] if a else None,
                        "status": status_json(a) if a else None})
        return out


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
