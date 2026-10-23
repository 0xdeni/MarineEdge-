"""Free AIS path: aisstream.io (live, terrestrial receivers, no history) recorded continuously by this
server into the `ais_live` table, then served through the same provider interface as a paid vendor.

Two pieces:
  parse_message()   aisstream JSON → position / static rows (pure, unit-tested)
  OwnAISProvider    get_track / search / vessels_near / vessels_in_area / get_static from the store
The recorder loop that feeds the store lives in app/recorder.py.

What money would otherwise buy and this path does not give: positions before the day the recorder
started, and satellite coverage of open sea (Arabian Sea, central Black Sea, Iranian waters). Gaps in
places with no receivers are expected, so the AIS-gap rule consults coverage() and labels such gaps
"outside receiver coverage" instead of raising a High flag. Buy history per ship (Datalastic) only for
the vessels you actually fix; the cache keeps it forever."""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.engine.types import Position, Vessel
from .base import LiveStatic, Neighbour, VesselMatch

REGION_BOXES = [  # [[lat_min, lon_min], [lat_max, lon_max]] as aisstream wants them
    [[30.0, 22.5], [48.0, 43.0]],      # Black Sea · Marmara · Aegean · Eastern Mediterranean
    [[15.5, 44.0], [31.5, 64.5]],      # Gulf · Hormuz · Oman · Arabian Sea
]
CELL = 0.5   # degrees, coverage grid


def type_category(code: Optional[int]) -> str:
    """AIS ship type code → engine category. 70–79 cargo, 80–89 tanker; container ships are cargo codes."""
    if code is None:
        return "other"
    if 80 <= code <= 89:
        return "tanker"
    if 70 <= code <= 79:
        return "bulk"
    return "other"


def _ts(meta: dict) -> int:
    """MetaData.time_utc like '2023-05-10 11:46:52.509865357 +0000 UTC' → epoch ms."""
    s = str(meta.get("time_utc") or "").replace(" UTC", "").strip()
    if not s:
        return int(time.time() * 1000)
    try:
        date, tm, *rest = s.split(" ")
        tm = tm.split(".")[0]
        d = datetime.strptime(f"{date} {tm}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return int(d.timestamp() * 1000)
    except ValueError:
        return int(time.time() * 1000)


def parse_message(obj: dict) -> Optional[tuple[str, dict]]:
    """Returns ('pos', row) | ('static', row) | None for one aisstream websocket message."""
    mt = obj.get("MessageType")
    meta = obj.get("MetaData") or {}
    msg = obj.get("Message") or {}
    mmsi = meta.get("MMSI") or (msg.get(mt) or {}).get("UserID")
    if not mmsi:
        return None
    t = _ts(meta)
    if mt in ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport"):
        p = msg.get(mt) or {}
        lat = p.get("Latitude", meta.get("latitude"))
        lon = p.get("Longitude", meta.get("longitude"))
        if lat is None or lon is None or abs(float(lat)) > 90 or abs(float(lon)) > 180:
            return None
        hdg = p.get("TrueHeading")
        return "pos", {"mmsi": int(mmsi), "t": t, "lat": float(lat), "lon": float(lon), "sog": float(p.get("Sog") or 0.0),
                       "cog": float(p.get("Cog") or 0.0), "heading": None if hdg in (None, 511) else float(hdg),
                       "nav": int(p.get("NavigationalStatus", 15) or 0), "name": (meta.get("ShipName") or "").strip() or None}
    if mt == "ShipStaticData":
        s = msg.get("ShipStaticData") or {}
        eta = s.get("Eta") or {}
        eta_ms = None
        try:
            if eta.get("Month") and eta.get("Day"):
                now = datetime.now(timezone.utc)
                yr = now.year + (1 if int(eta["Month"]) < now.month - 6 else 0)
                eta_ms = int(datetime(yr, int(eta["Month"]), int(eta["Day"]), min(23, int(eta.get("Hour", 0) or 0)), min(59, int(eta.get("Minute", 0) or 0)), tzinfo=timezone.utc).timestamp() * 1000)
        except (ValueError, TypeError):
            eta_ms = None
        dim = s.get("Dimension") or {}
        imo = s.get("ImoNumber")
        return "static", {"mmsi": int(mmsi), "t": t, "imo": int(imo) if imo and 1_000_000 <= int(imo) <= 9_999_999 else None,
                          "name": (s.get("Name") or meta.get("ShipName") or "").strip() or None, "callsign": (s.get("CallSign") or "").strip() or None,
                          "type_code": int(s.get("Type") or 0) or None, "destination": (s.get("Destination") or "").strip() or None, "eta": eta_ms,
                          "draught": float(s.get("MaximumStaticDraught") or 0) or None,
                          "dim": [float(dim.get(k) or 0) for k in ("A", "B", "C", "D")]}
    return None


def cell_of(lon: float, lat: float) -> tuple[int, int]:
    return int(math.floor(lon / CELL)), int(math.floor(lat / CELL))


class OwnAISProvider:
    """Serves everything from positions this server recorded. No credits, ever."""
    name = "Recorded AIS (aisstream.io, own receivers feed)"
    credits_used = 0      # the Service logs last_credits per fetch; here every fetch is free
    last_credits = 0

    def __init__(self, store):
        self.store = store
        self._cov: Optional[dict[tuple[int, int], int]] = None
        self._cov_at = 0.0

    # ---- adapter ----
    def search_vessel(self, query: str) -> list[VesselMatch]:
        out = []
        for r in self.store.live_search(query.strip())[:12]:
            out.append(VesselMatch(imo=r["imo"] or 0, name=r.get("name") or str(r["mmsi"]), mmsi=str(r["mmsi"]), flag=mid_flag(r["mmsi"]),
                                   type=type_category(r.get("type_code")), sub=type_label(r.get("type_code")), dwt=0, built=0))
        return [m for m in out if m.imo]

    def get_vessel(self, imo: int) -> Optional[Vessel]:
        rows = self.store.mmsi_by_imo(imo)
        if not rows:
            return None
        r = sorted(rows, key=lambda x: x.get("updated_at") or 0)[-1]
        dim = r.get("dim") or [0, 0, 0, 0]
        v = Vessel(imo=imo, name=r.get("name") or str(imo), mmsi=str(r["mmsi"]), callsign=r.get("callsign") or "", flag=mid_flag(r["mmsi"]),
                   type=type_category(r.get("type_code")), sub=type_label(r.get("type_code")), loa=(dim[0] + dim[1]) or 0, beam=(dim[2] + dim[3]) or 0,
                   draught_loaded=r.get("draught") or 0, region=region_of(self.store.live_last(imo)))
        # MMSI history from the map: several MMSIs for one IMO means a reflag
        hist = [x for x in rows if x["mmsi"] != r["mmsi"]]
        for h in hist:
            v.history.append({"field": "mmsi", "from": str(h["mmsi"]), "to": str(r["mmsi"]), "t": r.get("updated_at") or int(time.time() * 1000)})
        return v

    def get_track(self, imo: int, start_ms: int, end_ms: int) -> list[Position]:
        return [Position(t=r["t"], lat=r["lat"], lon=r["lon"], sog=r.get("sog") or 0.0, cog=r.get("cog") or 0.0, draught=r.get("draught") or 0.0,
                         nav=r.get("nav") or 0, src="T") for r in self.store.live_track(imo, start_ms, end_ms)]

    def get_vessels_near(self, lat: float, lon: float, radius_m: float, t0: int, t1: int) -> list[Neighbour]:
        out = []
        for r in self.store.live_near(lat, lon, radius_m, t0, t1):
            v = self.get_vessel(r["imo"]) if r.get("imo") else None
            if v is None:
                v = Vessel(imo=r.get("imo") or 0, name=r.get("name") or f"MMSI {r['mmsi']}", mmsi=str(r["mmsi"]), flag=mid_flag(r["mmsi"]))
            out.append(Neighbour(vessel=v, t0=r["t0"], t1=r["t1"], lat=r["lat"], lon=r["lon"]))
        return out

    def get_vessels_in_area(self, bbox):
        out = []
        for r in self.store.live_latest(bbox):
            if not r.get("imo"):
                continue
            v = self.get_vessel(r["imo"]) or Vessel(imo=r["imo"], name=r.get("name") or str(r["imo"]), mmsi=str(r["mmsi"]))
            out.append((v, Position(t=r["t"], lat=r["lat"], lon=r["lon"], sog=r.get("sog") or 0.0, cog=r.get("cog") or 0.0, draught=r.get("draught") or 0.0, nav=r.get("nav") or 0, src="T")))
        return out

    def get_static(self, imo: int) -> LiveStatic:
        rows = self.store.mmsi_by_imo(imo)
        if not rows:
            return LiveStatic()
        r = sorted(rows, key=lambda x: x.get("updated_at") or 0)[-1]
        return LiveStatic(destination=r.get("destination") or "", eta=r.get("eta"), draught=r.get("draught"))

    # ---- coverage (fixes per 0.5° cell over the last 30 days), cached for an hour ----
    def coverage(self, lon: float, lat: float) -> int:
        if self._cov is None or time.time() - self._cov_at > 3600:
            self._cov = self.store.live_coverage(days=30)
            self._cov_at = time.time()
        return self._cov.get(cell_of(lon, lat), 0)

    def stats(self) -> dict:
        return self.store.live_stats()


# ---------------------------------------------------------------- small lookups
MID_FLAG = {"201": "Albania", "205": "Belgium", "209": "Cyprus", "210": "Cyprus", "212": "Cyprus", "213": "Georgia", "215": "Malta", "218": "Germany", "219": "Denmark", "220": "Denmark",
            "224": "Spain", "226": "France", "229": "Malta", "232": "United Kingdom", "235": "United Kingdom", "236": "Gibraltar", "237": "Greece", "239": "Greece", "240": "Greece", "241": "Greece",
            "244": "Netherlands", "245": "Netherlands", "246": "Netherlands", "247": "Italy", "248": "Malta", "249": "Malta", "255": "Portugal (Madeira)", "256": "Malta", "257": "Norway", "258": "Norway", "259": "Norway",
            "261": "Poland", "263": "Portugal", "264": "Romania", "265": "Sweden", "266": "Sweden", "271": "Türkiye", "272": "Ukraine", "273": "Russia", "275": "Latvia", "276": "Estonia", "277": "Lithuania",
            "303": "USA (Alaska)", "304": "Antigua and Barbuda", "305": "Antigua and Barbuda", "308": "Bahamas", "309": "Bahamas", "311": "Bahamas", "314": "Barbados", "319": "Cayman Islands", "338": "USA", "341": "St Kitts and Nevis",
            "351": "Panama", "352": "Panama", "353": "Panama", "354": "Panama", "355": "Panama", "356": "Panama", "357": "Panama", "370": "Panama", "371": "Panama", "372": "Panama", "373": "Panama", "374": "Panama", "375": "Panama", "376": "Panama", "377": "Panama",
            "403": "Saudi Arabia", "405": "Bangladesh", "412": "China", "413": "China", "414": "China", "416": "Taiwan", "419": "India", "422": "Iran", "423": "Azerbaijan", "425": "Iraq", "428": "Israel", "431": "Japan", "432": "Japan",
            "440": "South Korea", "441": "South Korea", "445": "North Korea", "447": "Kuwait", "450": "Lebanon", "457": "Mongolia", "461": "Oman", "463": "Pakistan", "466": "Qatar", "468": "Syria", "470": "UAE", "471": "UAE", "477": "Hong Kong",
            "511": "Palau", "525": "Indonesia", "533": "Malaysia", "538": "Marshall Islands", "548": "Philippines", "563": "Singapore", "564": "Singapore", "565": "Singapore", "566": "Singapore", "567": "Thailand", "574": "Vietnam", "577": "Vanuatu",
            "613": "Cameroon", "616": "Comoros", "620": "Comoros", "626": "Gabon", "636": "Liberia", "637": "Liberia", "642": "Libya", "657": "Nigeria", "664": "Seychelles", "667": "Sierra Leone", "671": "Togo", "672": "Tunisia", "677": "Tanzania",
            "710": "Brazil", "720": "Bolivia", "725": "Chile", "730": "Colombia", "735": "Ecuador", "760": "Peru", "770": "Uruguay", "775": "Venezuela"}


def mid_flag(mmsi: int | str) -> str:
    return MID_FLAG.get(str(mmsi)[:3], "")


def type_label(code: Optional[int]) -> str:
    if code is None:
        return "Unknown type"
    if 80 <= code <= 89:
        return "Tanker (AIS type %d)" % code
    if 70 <= code <= 79:
        return "Cargo ship (AIS type %d)" % code
    if 30 <= code <= 37:
        return {30: "Fishing", 31: "Towing", 32: "Towing (large)", 33: "Dredging", 34: "Diving", 35: "Military", 36: "Sailing", 37: "Pleasure craft"}[code]
    if 60 <= code <= 69:
        return "Passenger ship"
    return "AIS type %d" % code


def region_of(last: Optional[dict]) -> str:
    if not last:
        return "A"
    return "B" if last["lon"] >= 43.5 else "A"


def utc_now_ms() -> int:
    return int(time.time() * 1000)


__all__: list[Any] = ["parse_message", "OwnAISProvider", "REGION_BOXES", "cell_of", "type_category", "mid_flag"]
