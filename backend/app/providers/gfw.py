"""Global Fishing Watch cross-check (free API token; data licensed CC BY-NC 4.0, i.e. non-commercial use only —
read https://globalfishingwatch.org/our-apis/documentation#terms-of-use before relying on it in a paid service).

This is NOT an AIS provider. GFW publishes events it computed from its own satellite + terrestrial AIS feed:
port visits, loitering, encounters (two ships side by side at sea), AIS-off gaps. We show them beside our own
flags as an independent second opinion — handy exactly where the free aisstream feed sees nothing (open sea).
Field names follow the public v3 docs and are read defensively; `first call` tells you if a dataset is unavailable."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

BASE = "https://gateway.api.globalfishingwatch.org/v3"
IDENTITY = "public-global-vessel-identity:latest"
DATASETS = {
    "port_visit": "public-global-port-visits-events:latest",
    "loitering": "public-global-loitering-events:latest",
    "encounter": "public-global-encounters-events:latest",
    "gap": "public-global-gaps-events:latest",
}
LABEL = {"port_visit": "Port visit", "loitering": "Loitering", "encounter": "Encounter (possible STS)", "gap": "AIS off"}


def _iso_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _ms(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def normalise_event(e: dict) -> dict:
    """One GFW event → {kind, label, t0, t1, lat, lon, detail}."""
    kind = str(e.get("type") or "").lower()
    pos = e.get("position") or {}
    detail = ""
    if kind == "port_visit":
        pv = e.get("port_visit") or {}
        a = pv.get("startAnchorage") or pv.get("intermediateAnchorage") or pv.get("endAnchorage") or {}
        detail = f"{a.get('name') or a.get('id') or 'unknown port'} ({a.get('flag') or '?'})" + (f" · confidence {pv.get('confidence')}" if pv.get("confidence") else "")
    elif kind == "encounter":
        en = e.get("encounter") or {}
        other = en.get("vessel") or {}
        detail = f"with {other.get('name') or other.get('ssvid') or 'unknown vessel'} ({other.get('flag') or '?'})"
        if en.get("medianDistanceKilometers") is not None:
            detail += f" · median distance {float(en['medianDistanceKilometers']):.2f} km"
        if en.get("medianSpeedKnots") is not None:
            detail += f" · {float(en['medianSpeedKnots']):.1f} kn"
    elif kind == "loitering":
        lo = e.get("loitering") or {}
        if lo.get("totalDistanceKm") is not None:
            detail = f"{float(lo['totalDistanceKm']):.1f} km covered"
        if lo.get("averageSpeedKnots") is not None:
            detail += f" · {float(lo['averageSpeedKnots']):.1f} kn average"
    elif kind == "gap":
        g = e.get("gap") or {}
        if g.get("distanceKm") is not None:
            detail = f"reappeared {float(g['distanceKm']):.0f} km away"
        if g.get("durationHours") is not None:
            detail += f" · {float(g['durationHours']):.0f} h"
        if g.get("intentionalDisabling") is not None:
            detail += " · GFW model: likely intentional" if g["intentionalDisabling"] else " · GFW model: probably reception"
    return {"kind": kind, "label": LABEL.get(kind, kind or "event"), "t0": _ms(e.get("start")), "t1": _ms(e.get("end")),
            "lat": pos.get("lat"), "lon": pos.get("lon"), "detail": detail.strip(" ·")}


class GFWClient:
    def __init__(self, token: str, timeout: float = 20.0, session: Optional[requests.Session] = None):
        self.token = token.strip()
        self.timeout = timeout
        self.http = session or requests.Session()

    def _get(self, path: str, params: list[tuple[str, Any]]) -> dict:
        r = self.http.get(BASE + path, params=params, headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"}, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"GFW {r.status_code} on {path}: {r.text[:200]}")
        return r.json()

    def find_vessel(self, imo: int) -> list[dict]:
        """Vessel identity records whose IMO matches. GFW keys on its own vessel id, one per identity segment."""
        data = self._get("/vessels/search", [("query", str(imo)), ("datasets[0]", IDENTITY), ("includes[0]", "MATCH_CRITERIA"), ("limit", 10)])
        out = []
        for ent in data.get("entries", []):
            ids = []
            for s in ent.get("selfReportedInfo") or []:
                if str(s.get("imo") or "") == str(imo):
                    ids.append(s.get("id"))
            if not ids and str(ent.get("imo") or "") == str(imo):
                ids.append(ent.get("id"))
            for vid in [i for i in ids if i]:
                sri = (ent.get("selfReportedInfo") or [{}])[0]
                out.append({"id": vid, "name": sri.get("shipname") or ent.get("name"), "mmsi": sri.get("ssvid"), "flag": sri.get("flag")})
        return out

    def events(self, vessel_ids: list[str], kind: str, start_ms: int, end_ms: int, limit: int = 100) -> list[dict]:
        params: list[tuple[str, Any]] = [("datasets[0]", DATASETS[kind]), ("start-date", _iso_day(start_ms)), ("end-date", _iso_day(end_ms)), ("limit", limit), ("offset", 0)]
        params += [(f"vessels[{i}]", v) for i, v in enumerate(vessel_ids)]
        data = self._get("/events", params)
        return [normalise_event(e) for e in data.get("entries", [])]

    def crosscheck(self, imo: int, start_ms: int, end_ms: int) -> dict:
        t = time.time()
        try:
            found = self.find_vessel(imo)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "imo": imo, "error": str(e)[:300], "source": "Global Fishing Watch"}
        if not found:
            return {"ok": True, "imo": imo, "source": "Global Fishing Watch", "matches": [], "events": [], "errors": [], "note": "IMO not in the GFW identity dataset", "ms": int((time.time() - t) * 1000)}
        ids = sorted({f["id"] for f in found})
        events, errors = [], []
        for kind in DATASETS:
            try:
                events += self.events(ids, kind, start_ms, end_ms)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{kind}: {str(e)[:160]}")
        events.sort(key=lambda e: e["t0"] or 0)
        return {"ok": True, "imo": imo, "source": "Global Fishing Watch", "matches": found, "events": events, "errors": errors,
                "licence": "CC BY-NC 4.0 — non-commercial use only", "ms": int((time.time() - t) * 1000)}
