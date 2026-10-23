"""Datalastic adapter (https://datalastic.com/api-reference/). Credit costs: basic position lookup 1,
Pro query 3, historical query ~5 (per Datalastic's pricing page at time of writing). Failed or empty
responses are not charged. Every call is logged with its credit estimate so the monthly cap is visible.

Field names below follow the public docs; confirm them on the first real pull (docs/PROVIDERS.md,
"First real pull") and adjust _position() if the trial returns different keys."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from app.engine.types import Position, Vessel
from .base import CreditsExhausted, LiveStatic, Neighbour, ProviderError, VesselMatch

log = logging.getLogger("vvt.datalastic")
BASE = "https://api.datalastic.com/api/v0"
TYPE_MAP = {"tanker": "tanker", "bulk": "bulk", "container": "container", "lng": "gas", "lpg": "gas", "gas": "gas"}


class DatalasticProvider:
    name = "Datalastic"

    def __init__(self, api_key: Optional[str] = None, session: Optional[requests.Session] = None):
        self.key = api_key or os.environ.get("DATALASTIC_API_KEY", "")
        if not self.key:
            raise ProviderError("DATALASTIC_API_KEY is not set")
        self.http = session or requests.Session()
        self.credits_used = 0

    # ---- http ----
    def _redact(self, text: str) -> str:
        return text.replace(self.key, "***") if self.key else text

    def _get(self, path: str, credits: int, **params) -> dict:
        params["api-key"] = self.key
        try:
            r = self.http.get(f"{BASE}/{path}", params=params, timeout=60)
        except requests.RequestException as e:
            raise ProviderError(f"Datalastic unreachable on {path}: {self._redact(str(e))[:200]}") from e
        if r.status_code == 402 or r.status_code == 429:
            raise CreditsExhausted(f"Datalastic {r.status_code}: {self._redact(r.text[:200])}")
        if r.status_code >= 400:
            raise ProviderError(f"Datalastic {r.status_code} on {path}: {self._redact(r.text[:200])}")
        self.credits_used += credits
        log.info("datalastic %s credits≈%d total≈%d", path, credits, self.credits_used)
        return r.json()

    # ---- mapping ----
    @staticmethod
    def _type(raw: str) -> str:
        s = (raw or "").lower()
        for k, v in TYPE_MAP.items():
            if k in s:
                return v
        return "other"

    @staticmethod
    def _position(p: dict) -> Position:
        t = p.get("last_position_epoch")
        if t is None and p.get("last_position_UTC"):
            t = datetime.fromisoformat(p["last_position_UTC"].replace("Z", "+00:00")).timestamp()
        return Position(t=int(float(t) * 1000), lat=float(p["lat"]), lon=float(p["lon"]),
                        sog=float(p.get("speed") or 0), cog=float(p.get("course") or p.get("heading") or 0),
                        draught=float(p.get("current_draught") or p.get("draught") or 0),
                        nav={"Under way using engine": 0, "At anchor": 1, "Moored": 5}.get(p.get("navigation_status", ""), 0),
                        src="S" if "sat" in str(p.get("source", "")).lower() else "T")

    @staticmethod
    def _vessel(d: dict) -> Vessel:
        return Vessel(imo=int(d.get("imo") or 0), name=d.get("name", ""), mmsi=str(d.get("mmsi", "")), callsign=d.get("callsign", ""),
                      flag=d.get("country_name") or d.get("country_iso", ""), type=DatalasticProvider._type(d.get("type", "")),
                      sub=d.get("type_specific") or d.get("type", ""), dwt=int(d.get("deadweight") or 0), gt=int(d.get("gross_tonnage") or 0),
                      loa=float(d.get("length") or 0), beam=float(d.get("breadth") or 0), built=int(d.get("year_built") or 0),
                      draught_loaded=float(d.get("draught") or 0))

    # ---- adapter ----
    def search_vessel(self, query: str) -> list[VesselMatch]:
        q = query.strip()
        params = {"imo": q} if q.isdigit() and len(q) == 7 else {"mmsi": q} if q.isdigit() and len(q) == 9 else {"name": q, "fuzzy": 1}
        data = self._get("vessel_find", 1, **params).get("data", [])
        out = []
        for d in data if isinstance(data, list) else [data]:
            if not d.get("imo"):
                continue
            out.append(VesselMatch(imo=int(d["imo"]), name=d.get("name", ""), mmsi=str(d.get("mmsi", "")), flag=d.get("country_name", ""),
                                   type=self._type(d.get("type", "")), sub=d.get("type_specific", ""), dwt=int(d.get("deadweight") or 0), built=int(d.get("year_built") or 0)))
        return out[:12]

    def get_vessel(self, imo: int) -> Optional[Vessel]:
        d = self._get("vessel_info", 1, imo=imo).get("data")
        return self._vessel(d) if d else None

    def get_track(self, imo: int, start_ms: int, end_ms: int) -> list[Position]:
        f = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        t = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        d = self._get("vessel_history", 5, imo=imo, **{"from": f, "to": t}).get("data", {})
        pts = d.get("positions", []) if isinstance(d, dict) else []
        return [self._position(p) for p in pts if p.get("lat") is not None]

    def get_vessels_near(self, lat: float, lon: float, radius_m: float, t0: int, t1: int) -> list[Neighbour]:
        # Datalastic's history scan is by area and date; one call per STS candidate window.
        f = datetime.fromtimestamp(t0 / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        t = datetime.fromtimestamp(t1 / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        d = self._get("vessel_history_inradius", 5, lat=lat, lon=lon, radius=max(1, round(radius_m / 1852, 2)), **{"from": f, "to": t})
        out = []
        for v in d.get("data", {}).get("vessels", []) if isinstance(d.get("data"), dict) else []:
            vs = self._vessel(v)
            out.append(Neighbour(vessel=vs, t0=t0, t1=t1, lat=lat, lon=lon))
        return out

    def get_vessels_in_area(self, bbox):
        min_lon, min_lat, max_lon, max_lat = bbox
        d = self._get("vessel_inarea", 1, lat_min=min_lat, lat_max=max_lat, lon_min=min_lon, lon_max=max_lon)
        out = []
        for v in d.get("data", []) if isinstance(d.get("data"), list) else []:
            if not v.get("imo"):
                continue
            try:
                out.append((self._vessel(v), self._position(v)))
            except (KeyError, ValueError):
                continue
        return out

    def get_static(self, imo: int) -> LiveStatic:
        d = self._get("vessel_pro", 3, imo=imo).get("data") or {}
        eta = d.get("eta_epoch")
        return LiveStatic(destination=d.get("destination", "") or "", eta=int(eta * 1000) if eta else None,
                          draught=float(d["current_draught"]) if d.get("current_draught") else None)
