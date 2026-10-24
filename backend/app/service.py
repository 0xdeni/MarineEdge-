"""Orchestration: search → identify → fetch (cached) → analyze → verdict → serialise. The HTTP layer
(app/routes.py) is thin on purpose so the same calls work from a CLI, a scheduled job or a test.

Data sources, free first:
  * the analysis provider — on a server the recorded free feed (aisstream.io → ais_live); a paid provider
    (Datalastic, Kpler) only when an admin switches to it; the generated demo fleet only in tests/dev
  * the live map and the region overview always read the recorded feed on a server, never a paid area query
  * 12 months of history for one ship can be bought with a paid key (`buy_history`); bought positions are
    cached forever and merged with the recorded ones."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict
from typing import Any, Optional

from app import verdict as verdict_mod
from app.engine import analyze, load_refdata, load_rules
from app.engine.refdata import RefData
from app.engine.rules_config import Rules, _merge
from app.engine.types import D, Analysis, Flag, PortCall, Position, Vessel, Voyage
from app.providers import AISProvider, ProviderError, make_provider
from app.store import Store, make_store

log = logging.getLogger("vvt.service")

REGIONS: dict[str, dict[str, Any]] = {
    "blacksea": {"name": "Black Sea", "bbox": (27.2, 40.6, 42.0, 47.4)},
    "hormuz": {"name": "Strait of Hormuz", "bbox": (55.3, 25.3, 57.7, 27.5)},
    "iran": {"name": "Iran coast", "bbox": (48.0, 24.4, 61.8, 31.0)},
    "oman": {"name": "Gulf of Oman", "bbox": (52.8, 16.0, 62.6, 26.9)},
    "uae": {"name": "UAE", "bbox": (51.3, 23.6, 57.3, 26.6)},
}
PAID = ("datalastic", "kpler")
SWEEP_STALE_MS = 6 * 3_600_000
LIVE_WINDOW_MS = 6 * 3_600_000


class Service:
    def __init__(self, provider: Optional[AISProvider] = None, store: Optional[Store] = None, ref: Optional[RefData] = None, rules: Optional[Rules] = None, now_ms: Optional[int] = None):
        self.ref = ref or load_refdata()
        self._pinned = provider is not None          # tests pass a provider: never swapped by the settings file
        self._rules_pinned = rules is not None
        self.rules = rules or self._load_rules()
        self.store = store or make_store()
        if not self._pinned:
            self._apply_zone_settings()
        self.provider = provider or self._make(None)
        from app import settings_store
        self._settings_version = settings_store.version()
        self.now = now_ms
        self.fetches = 0
        self._cache: dict[int, Analysis] = {}
        self._sweep_lock = threading.Lock()
        self._sweep_state: dict[str, Any] = {"running": False, "last": None, "analysed": 0}

    # ---- helpers ----
    def _now(self) -> int:
        return self.now or int(time.time() * 1000)

    @staticmethod
    def _load_rules() -> Rules:
        from app import settings_store
        base = load_rules()
        over = settings_store.rule_overrides()
        return Rules(_merge(dict(base), over)) if over else base

    def _apply_zone_settings(self) -> None:
        from app import settings_store
        off, on = set(settings_store.zones_off()), set(settings_store.zones_on())
        for z in self.ref.zones:
            z.enabled = z.id in on or (z.default_on and z.id not in off)

    def _make(self, name: Optional[str], api_key: Optional[str] = None) -> AISProvider:
        from app import settings_store
        nm = (name or settings_store.provider_name()).lower()
        if nm == "mock":
            return make_provider(nm, api_key=api_key, ref=self.ref)
        if nm == "aisstream":
            return make_provider(nm, store=self.store)
        return make_provider(nm, api_key=api_key)

    def _sync(self) -> None:
        """Rebuild the provider (and rules, zones) when another worker or the CLI changed the settings file."""
        if self._pinned:
            return
        from app import settings_store
        v = settings_store.version()
        if v != self._settings_version:
            self.provider = self._make(None)
            if not self._rules_pinned:
                self.rules = self._load_rules()
            self._apply_zone_settings()
            self._settings_version = v
            self._cache.clear()

    @property
    def is_mock(self) -> bool:
        return getattr(self.provider, "name", "") == "mock" or type(self.provider).__name__ == "MockProvider"

    def live_source(self) -> AISProvider:
        """Where live positions come from: the recorded feed on a server; the demo fleet only in dev/tests."""
        if self.is_mock:
            return self.provider
        if getattr(self.provider, "local", False):
            return self.provider
        return make_provider("aisstream", store=self.store)

    def history_provider(self) -> Optional[AISProvider]:
        """A paid provider that can sell 12 months of one ship's track, when a key is saved."""
        from app import settings_store
        if not self.is_mock and getattr(self.provider, "name", "").lower().startswith(PAID):
            return self.provider
        for nm in PAID:
            if settings_store.provider_key(nm):
                try:
                    return make_provider(nm)
                except ProviderError:
                    continue
        return None

    def set_provider(self, name: str, api_key: Optional[str] = None) -> dict:
        """Admin action from the app: switch provider and/or key without a restart. The old provider's
        analyses are dropped from the memory cache; stored positions stay (they are keyed on IMO)."""
        from app import settings_store
        if name == "mock" and not settings_store.mock_allowed():
            raise ProviderError("the demo fleet is only available on a development machine")
        settings_store.set_provider(name, api_key)
        self.provider = self._make(name, api_key)
        self._settings_version = settings_store.version()
        self._cache.clear()
        return {"provider": getattr(self.provider, "name", name)}

    def test_provider(self) -> dict:
        """One cheap call to prove the key works: a name search (1 credit on Datalastic, 0 on the recorded feed)."""
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
        self.rules = self._load_rules()
        self._cache.clear()
        return self.rules

    def set_rule_overrides(self, over: dict) -> Rules:
        from app import settings_store
        settings_store.set_rule_overrides(over)
        self._settings_version = settings_store.version()
        return self.reload_rules()

    def set_zone(self, zone_id: str, enabled: bool) -> None:
        from app import settings_store
        z = self.ref.zone_by_id[zone_id]
        z.enabled = enabled
        if not self._pinned:
            settings_store.set_zone_enabled(zone_id, enabled)
            self._settings_version = settings_store.version()
        self._cache.clear()

    def engine_stamp(self) -> str:
        """Which rules wrote a verdict: the engine version, the thresholds in force and the zones switched on. A verdict
        stored under another stamp counts as not checked, so changing a rule or a zone in the app re-checks every ship."""
        from app.engine import ENGINE_VERSION
        zones = sorted(z.id for z in self.ref.zones if z.enabled)
        digest = hashlib.sha256(json.dumps([self.rules, zones], sort_keys=True, default=str).encode()).hexdigest()[:10]
        return f"{ENGINE_VERSION}:{digest}"

    def fresh_risk(self, imos: list[int]) -> dict[int, dict]:
        """Stored verdicts written under the current rules and zones. Others count as not checked (the sweep re-checks them)."""
        try:
            rows = self.store.get_risk(imos)
        except Exception:  # noqa: BLE001
            return {}
        stamp = self.engine_stamp()
        return {i: r for i, r in rows.items() if r.get("engine") == stamp}

    # ---- steps 1-2 ----
    def search(self, q: str):
        self._sync()
        return self.provider.search_vessel(q)

    def search_json(self, q: str) -> list[dict]:
        """Search results with each ship's last verdict (if it was ever checked) and the former name that matched."""
        matches = self.search(q)
        risk = self.fresh_risk([m.imo for m in matches if m.imo])
        qu = q.strip().upper()
        out = []
        for m in matches:
            ex = list(m.ex_names or [])
            former = next((n for n in ex if qu and qu in n.upper()), None) if qu and qu not in (m.name or "").upper() else None
            r = risk.get(m.imo)
            out.append({"imo": m.imo, "name": m.name, "mmsi": m.mmsi, "flag": m.flag, "type": m.type, "sub": m.sub, "dwt": m.dwt, "built": m.built,
                        "exNames": ex, "matchedFormer": former,
                        "verdict": {"level": r["level"], "label": verdict_mod.LABELS.get(r["level"], r["level"]), "headline": r.get("headline"), "checked": r.get("analysed_at")} if r else None})
        return out

    # ---- steps 3-8 ----
    def track(self, imo: int) -> list[Position]:
        """Step 3 with the cache rule: a window is fetched once. On later calls only the uncovered tail
        (from the last fetched moment, with one hour of overlap, to now) is bought. On the recorded feed the
        positions are already ours; history bought for this ship (if any) is merged in."""
        end = self._now()
        start = end - int(self.rules.history_months * 30.4 * 24 * 3_600_000)
        if getattr(self.provider, "local", False):          # recorded feed: already in our database, nothing to buy or copy
            rec = self.provider.get_track(imo, start, end)
            bought = self.store.get_positions(imo, start, end)
            return merge_tracks(rec, bought) if bought else rec
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

    def history_status(self, imo: int) -> dict[str, Any]:
        end = self._now()
        start = end - int(self.rules.history_months * 30.4 * 24 * 3_600_000)
        hp = self.history_provider()
        return {"available": hp is not None, "provider": getattr(hp, "name", None) if hp else None,
                "bought": bool(hp is not None and self.store.covered(imo, start, end))}

    def buy_history(self, imo: int) -> dict[str, Any]:
        """Buy the missing part of the last 12 months for one ship from the paid provider (cache rule applies)."""
        hp = self.history_provider()
        if hp is None:
            raise ProviderError("no paid history provider is set up — an admin adds a Datalastic key in Profile › Data sources")
        end = self._now()
        start = end - int(self.rules.history_months * 30.4 * 24 * 3_600_000)
        if self.store.covered(imo, start, end):
            self._cache.pop(imo, None)
            return {"ok": True, "bought": 0, "already": True}
        last = self.store.latest_window_end(imo)
        fetch_from = start if last is None or last < start else max(start, last - 3_600_000)
        pts = hp.get_track(imo, fetch_from, end)
        self.store.put_positions(imo, pts, getattr(hp, "name", "provider"), fetch_from, end, getattr(hp, "last_credits", 5))
        self.fetches += 1
        self._cache.pop(imo, None)
        return {"ok": True, "bought": len(pts), "credits": getattr(hp, "last_credits", None)}

    def sanctions_lists(self) -> list[str]:
        """Names of the sanctions lists the server holds (downloaded and not empty). The page only says
        "not listed" for these."""
        if self.is_mock:
            return ["OFAC SDN", "EU", "UK"]
        try:
            st = self.store.sanctions_status() or {}
        except Exception:  # noqa: BLE001
            return []
        lists = [k for k, v in (st.get("lists") or {}).items() if v]
        if not lists and st.get("rows", 0) > 0:
            lists = ["OFAC SDN", "EU"]
        return lists

    def sanctions_checked(self) -> bool:
        return bool(self.sanctions_lists())

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
        lists = self.sanctions_lists()
        a.verdict = verdict_mod.build(a, sanctions_checked=bool(lists), lists=lists)
        try:
            self.store.save_analysis(a)
        except Exception:  # the analysis is still served if the DB write fails
            log.exception("save_analysis failed for %s", imo)
        try:
            self.store.save_risk(imo, verdict_mod.risk_row(a, a.verdict, engine=self.engine_stamp()))
        except Exception:  # noqa: BLE001
            log.exception("save_risk failed for %s", imo)
        self._cache[imo] = a
        return a

    # ---- live map, region overview, background sweep ----
    def live_rows(self, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
        """Latest position of every ship in the box (last 6 hours), compact, with verdicts when known."""
        self._sync()
        src = self.live_source()
        rows = src.get_vessels_in_area(bbox)
        statics = getattr(src, "area_static", {}) or {}
        imos = [v.imo for v, _ in rows if v.imo]
        risk = self.fresh_risk(imos)
        try:
            sanc = self.store.sanctioned(imos)
        except Exception:  # noqa: BLE001
            sanc = set()
        out = []
        for v, p in rows:
            r = risk.get(v.imo)
            st = statics.get(v.imo)
            sanctioned = v.imo in sanc or bool(v.sanctions)
            level = r["level"] if r else None
            if sanctioned and level != "high":
                level = "high"
            out.append({"imo": v.imo, "name": v.name, "mmsi": v.mmsi, "type": v.type, "sub": v.sub, "flag": v.flag,
                        "lat": round(p.lat, 5), "lon": round(p.lon, 5), "sog": round(p.sog or 0, 1), "cog": round(p.cog or 0), "t": p.t, "nav": p.nav,
                        "level": level, "headline": (r or {}).get("headline"), "checked": (r or {}).get("analysed_at"), "sanctioned": sanctioned,
                        **({"destination": st.destination} if st and st.destination else {})})
        return out

    def overview(self, region_id: str, user: Optional[str] = None) -> dict[str, Any]:
        reg = REGIONS[region_id]
        rows = self.live_rows(reg["bbox"])
        checked = [r for r in rows if r["checked"]]
        high = [r for r in rows if r["level"] == "high"]
        sanc = [r for r in rows if r["sanctioned"]]
        newest = max((r["t"] for r in rows), default=None)
        recorder = None
        if not self.is_mock:
            try:
                recorder = self.store.live_stats()
            except Exception:  # noqa: BLE001
                recorder = None
        order = sorted(high, key=lambda r: (not r["sanctioned"], -(r["t"] or 0)))
        self.maybe_sweep()
        return {"region": region_id, "name": reg["name"], "bbox": reg["bbox"], "now": self._now(),
                "counts": {"inRange": len(rows), "checked": len(checked), "high": len(high), "sanctioned": len(sanc)},
                "newest": newest, "recorder": recorder, "source": "demo" if self.is_mock else "recorded",
                "highest": order[:8], "sweep": dict(self._sweep_state)}

    def maybe_sweep(self, budget_s: float = 45.0) -> None:
        """Check unchecked or stale ships in range in a background thread, at most one at a time and at most every 10 min."""
        st = self._sweep_state
        if st["running"] or (st["last"] and self._now() - st["last"] < 10 * 60_000):
            return
        threading.Thread(target=self.sweep, kwargs={"budget_s": budget_s}, daemon=True).start()

    def sweep(self, budget_s: float = 60.0, regions: Optional[list[str]] = None) -> dict[str, Any]:
        """Run the full analysis on ships in range that were never checked or were checked more than 6 hours
        ago, newest-heard first, until the time budget is spent. Recorded data only: costs nothing."""
        if not self._sweep_lock.acquire(blocking=False):
            return {"skipped": "already running"}
        st = self._sweep_state
        st["running"] = True
        t_end = time.monotonic() + budget_s
        done = errors = 0
        try:
            cands: dict[int, int] = {}
            for rid in regions or list(REGIONS):
                for r in self.live_rows(REGIONS[rid]["bbox"]):
                    if r["imo"] and (not r["checked"] or self._now() - r["checked"] > SWEEP_STALE_MS):
                        cands[r["imo"]] = max(cands.get(r["imo"], 0), r["t"] or 0)
            for imo in sorted(cands, key=lambda i: -cands[i]):
                if time.monotonic() > t_end:
                    break
                try:
                    self.analysis(imo, refresh=True)
                    done += 1
                except KeyError:
                    continue
                except Exception:  # noqa: BLE001  one bad ship must not stop the sweep
                    errors += 1
                    log.exception("sweep: analysis failed for %s", imo)
                time.sleep(0.01)                     # let API requests in between
            st.update(last=self._now(), analysed=done, errors=errors, waiting=max(0, len(cands) - done))
            return {"analysed": done, "errors": errors, "candidates": len(cands)}
        finally:
            st["running"] = False
            self._sweep_lock.release()


def merge_tracks(a: list[Position], b: list[Position]) -> list[Position]:
    """Recorded and bought positions together, one fix per minute (recorded wins on a tie)."""
    seen: dict[int, Position] = {}
    for p in b:
        seen[p.t // 60_000] = p
    for p in a:
        seen[p.t // 60_000] = p
    return [seen[k] for k in sorted(seen)]


# ---------------------------------------------------------------- JSON shapes
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


def flag_json(f: Flag, a: Optional[Analysis] = None, ref=None) -> dict:
    st = verdict_mod.story(f, a, ref) if a is not None else None
    return {"id": f.id, "key": f.key, "rule": f.rule, "severity": f.severity, "title": f.title, "lines": f.lines, "t0": f.t0, "t1": f.t1, "lat": f.lat, "lon": f.lon,
            "story": st,
            "vesselLevel": f.vessel_level, "hours": f.hours, "voyage": f.voyage.n if f.voyage else None, "partnerImo": f.partner_imo, "meta": f.meta,
            "evidence": {"before": [pos_json(p) for p in f.evidence_before], "after": [pos_json(p) for p in f.evidence_after]} if (f.evidence_before or f.evidence_after) else None}


def voyage_json(v: Voyage) -> dict:
    return {"n": v.n, "color": v.color, "from": port_call_json(v.frm) if v.frm else None, "to": port_call_json(v.to) if v.to else None, "i0": v.i0, "i1": v.i1,
            "depart": v.depart, "arrive": v.arrive, "nm": v.nm, "draughtOut": v.draught_out, "draughtIn": v.draught_in, "current": v.current,
            "flags": [f.id for f in v.flags], "darkH": v.dark_h}


def status_json(a: Analysis) -> dict:
    s = a.status
    port = lambda p: {"id": p.id, "name": p.name} if p else None
    return {"state": s.state, "destination": s.destination, "eta": s.eta, "since": s.since, "port": port(s.port), "lastPort": port(s.last_port), "nextPort": port(s.next_port)}


def stats_json(stats: dict) -> dict:
    ren = {"port_calls": "portCalls", "history_since": "historySince"}
    return {ren.get(k, k): v for k, v in stats.items()}


def analysis_json(a: Analysis, include_track: bool = True, ref=None) -> dict[str, Any]:
    return {"vessel": vessel_json(a.vessel), "track": [pos_json(p) for p in a.track] if include_track else None,
            "portCalls": [port_call_json(pc) for pc in a.port_calls], "voyages": [voyage_json(v) for v in a.voyages],
            "flags": [flag_json(f, a, ref) for f in a.flags], "sev": a.sev, "status": status_json(a), "stats": stats_json(a.stats),
            "last": pos_json(a.track[-1]) if a.track else None, "verdict": a.verdict or None, "positions": len(a.track)}


def regions_json() -> list[dict]:
    return [{"id": k, "name": v["name"], "bbox": list(v["bbox"])} for k, v in REGIONS.items()]


_ = D  # re-exported for callers that import time constants from here
