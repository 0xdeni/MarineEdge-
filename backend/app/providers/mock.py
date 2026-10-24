"""Mock AIS provider: 40 fictional vessels with deterministic generated 12-month tracks that follow
sea lanes between real ports, with planted events (gaps, draught changes, STS, jumps, sensitive calls)
by risk profile. No network, no credits. Used by the tests and the development server (`make dev`) only:
a server refuses it unless VVT_ALLOW_MOCK=1 (settings_store.mock_allowed), so real users never see it."""
from __future__ import annotations

import heapq
import json
import math
import time
from pathlib import Path
from typing import Optional

from app.engine.geo import bearing, dest_point, nm_dist
from app.engine.refdata import RefData, load_refdata
from app.engine.types import D, H, YEAR, Position, Vessel
from .base import LiveStatic, Neighbour, VesselMatch

DATA = Path(__file__).resolve().parents[1] / "data"


# ---------------------------------------------------------------- deterministic RNG (mulberry32)
class RNG:
    def __init__(self, seed: int):
        self.s = seed & 0xFFFFFFFF

    def __call__(self) -> float:
        self.s = (self.s + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.s
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t
        t &= 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    def pick(self, arr):
        return arr[int(self() * len(arr))]


# ---------------------------------------------------------------- sea-lane router
class Router:
    def __init__(self, region: dict):
        self.nodes = region["nodes"]
        self.adj: dict[int, list[tuple[int, float]]] = {}
        for a, b in region["edges"]:
            w = nm_dist(self.nodes[a][1], self.nodes[a][0], self.nodes[b][1], self.nodes[b][0])
            self.adj.setdefault(a, []).append((b, w))
            self.adj.setdefault(b, []).append((a, w))
        self.cache: dict[tuple[int, int], list] = {}

    def route(self, a: int, b: int) -> list[list[float]]:
        key = (a, b)
        if key in self.cache:
            return self.cache[key]
        dist = {a: 0.0}
        prev: dict[int, int] = {}
        pq = [(0.0, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == b:
                break
            if d > dist.get(u, math.inf):
                continue
            for v, w in self.adj.get(u, []):
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        path = [b]
        while path[-1] != a and path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        pts = [self.nodes[i] for i in path]
        self.cache[key] = pts
        return pts


# ---------------------------------------------------------------- particulars helpers
def particulars(vtype: str, sub: str, dwt: int) -> tuple[int, float, float]:
    s = sub.lower()
    if vtype == "bulk":
        return (22000, 180, 30) if "handysize" in s else (27500, 190, 30) if "handymax" in s else (32000, 190, 32.3) if "supramax" in s else (36000, 200, 32.3) if "ultramax" in s else (44500, 229, 32.3) if "kamsarmax" in s else (41000, 225, 32.3)
    if vtype == "tanker":
        return (160000, 333, 60) if "vlcc" in s else (83000, 274, 48) if "suezmax" in s else (60000, 250, 44) if ("aframax" in s or "lr2" in s) else (29500, 183, 32.2)
    if vtype == "container":
        return (95000, 335, 43) if dwt > 80000 else (55000, 294, 32.2) if dwt > 60000 else (40000, 230, 32.2) if dwt > 40000 else (28000, 210, 30) if dwt > 30000 else (20000, 175, 28) if dwt > 22000 else (17000, 170, 27)
    if vtype == "gas":
        return (115000, 295, 46) if "lng" in s else (48000, 230, 36)
    return (12000, 150, 23) if "ro-ro" in s else (8000, 140, 20) if dwt > 10000 else (3800, 100, 16)


def draughts(vtype: str, dwt: int) -> tuple[float, float]:
    if vtype == "bulk":
        return (14.2, 7.2) if dwt > 70000 else (12.6, 6.6) if dwt > 55000 else (11.4, 6.0) if dwt > 40000 else (10.2, 5.6)
    if vtype == "tanker":
        return (20.6, 11.0) if dwt > 250000 else (17.0, 9.0) if dwt > 140000 else (14.9, 8.1) if dwt > 90000 else (11.8, 6.4)
    if vtype == "gas":
        return (11.8, 9.6) if dwt > 80000 else (11.0, 8.4)
    if vtype == "container":
        return (14.0, 11.5) if dwt > 80000 else (12.5, 10.0) if dwt > 40000 else (10.5, 8.2)
    return (8.2, 4.6) if dwt > 10000 else (6.4, 3.8)


# ---------------------------------------------------------------- provider
class MockProvider:
    name = "Mock AIS provider (generated tracks)"

    def __init__(self, ref: Optional[RefData] = None, now_ms: Optional[int] = None):
        self.ref = ref or load_refdata()
        self.now = now_ms or int(time.time() * 1000)
        self.geo = json.loads((DATA / "geo.json").read_text(encoding="utf-8"))
        self.cfg = json.loads((DATA / "fleet.json").read_text(encoding="utf-8"))
        self.routers = {k: Router(self.geo["regions"][k]) for k in ("A", "B")}
        self.fleet: list[Vessel] = [self._build_vessel(d) for d in self.cfg["fleet"]]
        self.by_imo = {v.imo: v for v in self.fleet}
        self._risk = {d["imo"]: d["risk"] for d in self.cfg["fleet"]}
        self._trade = {d["imo"]: d["trade"] for d in self.cfg["fleet"]}
        self._tracks: dict[int, list[Position]] = {}
        self._static: dict[int, LiveStatic] = {}
        self._sts: list[dict] = []
        # geo.json port nodes (approach node index) by port id
        self._port_nodes = {p["id"]: (p["an"], p["bn"]) for k in ("A", "B") for p in self.geo["regions"][k]["ports"]}

    # ---- static ----
    def _build_vessel(self, d: dict) -> Vessel:
        rng = RNG(d["imo"] * 7919)
        mids = self.cfg["mid"].get(d["flag"], ["352"])
        d6 = lambda: str(int(rng() * 900000) + 100000)
        mmsi = rng.pick(mids) + d6()
        prefix = self.cfg["callsign_prefix"].get(d["flag"], "3F")
        callsign = prefix + chr(65 + int(rng() * 26)) + str(int(rng() * 90) + 10) + chr(65 + int(rng() * 26))
        gt, loa, beam = particulars(d["type"], d["sub"], d["dwt"])
        dl, db = draughts(d["type"], d["dwt"])
        opts = d.get("opts", {})
        cos = self.cfg["opaque"] if opts.get("opaque") else self.cfg["companies"][d["region"]]
        co, co2 = rng.pick(cos), rng.pick(cos)
        history = []
        for field, frm, to, months in opts.get("hist", []):
            t = self.now - int(months * 30.4 * D) - int(rng() * 10) * D
            history.append({"field": field, "from": (frm + d6()) if field == "mmsi" else frm, "to": mmsi if field == "mmsi" else to, "t": t})
        sanctions = []
        for lst, date, prog in opts.get("sanctions", []):
            y, m, dd = (int(x) for x in date.split("-"))
            import datetime as _dt
            sanctions.append({"list": lst, "programme": prog, "t": int(_dt.datetime(y, m, dd, tzinfo=_dt.timezone.utc).timestamp() * 1000)})
        builders = self.cfg["builders"][d["type"]]
        risk = d["risk"]
        speed = 15 + rng() * 4 if d["type"] == "container" else 15 + rng() * 2 if d["type"] == "gas" else 9 + rng() * 2 if d["type"] == "other" else 11 + rng() * 2.3
        return Vessel(imo=d["imo"], name=d["name"], mmsi=mmsi, callsign=callsign, flag=d["flag"], type=d["type"], sub=d["sub"], dwt=d["dwt"],
                      gt=gt, loa=loa, beam=beam, built=d["built"], builder=rng.pick(builders), draught_loaded=dl, draught_ballast=db,
                      region=d["region"], ex_names=opts.get("ex", []), history=history, sanctions=sanctions,
                      reg_owner=f"{co[0]} ({co[1]})", ben_owner="Not identified · nominee director" if opts.get("opaque") else f"{co[0]} group",
                      ism=f"{co2[0]} ({co2[1]})", operator="Undisclosed" if opts.get("opaque") else f"{co[0]} ({co[1]})",
                      class_soc=("Not IACS · register unverified" if rng() < 0.5 else "Withdrawn from IACS class (2025)") if risk > 0.8 else rng.pick(self.cfg["iacs"]),
                      pi="Non-IG insurer · cover unverified" if risk > 0.8 else rng.pick(self.cfg["ig_pi"]), speed=speed)

    # ---- adapter ----
    def search_vessel(self, query: str) -> list[VesselMatch]:
        s = query.strip().upper()
        if not s:
            return []
        out = []
        for v in self.fleet:
            if s in v.name or str(v.imo).startswith(s) or v.mmsi.startswith(s) or any(s in n for n in v.ex_names):
                out.append(VesselMatch(imo=v.imo, name=v.name, mmsi=v.mmsi, flag=v.flag, type=v.type, sub=v.sub, dwt=v.dwt, built=v.built, ex_names=v.ex_names))
        return out[:12]

    def get_vessel(self, imo: int) -> Optional[Vessel]:
        return self.by_imo.get(imo)

    def get_track(self, imo: int, start_ms: int, end_ms: int) -> list[Position]:
        if imo not in self._tracks:
            self._generate(self.by_imo[imo])
        return [p for p in self._tracks[imo] if start_ms <= p.t <= end_ms]

    def get_vessels_near(self, lat: float, lon: float, radius_m: float, t0: int, t1: int) -> list[Neighbour]:
        r_nm = radius_m / 1852
        out = []
        for e in self._sts:
            if e["t0"] < t1 and e["t1"] > t0 and nm_dist(lat, lon, e["lat"], e["lon"]) <= r_nm + 0.05:
                out.append(Neighbour(vessel=self.by_imo[e["partner"]], t0=max(e["t0"], t0), t1=min(e["t1"], t1), lat=e["lat"], lon=e["lon"]))
        return out

    def get_vessels_in_area(self, bbox):
        min_lon, min_lat, max_lon, max_lat = bbox
        out = []
        for v in self.fleet:
            tr = self.get_track(v.imo, 0, self.now)
            if tr and min_lon <= tr[-1].lon <= max_lon and min_lat <= tr[-1].lat <= max_lat:
                out.append((v, tr[-1]))
        return out

    def get_static(self, imo: int) -> LiveStatic:
        if imo not in self._static:
            self._generate(self.by_imo[imo])
        return self._static[imo]

    def generate_all(self) -> None:
        """Generate every track up front so STS partner lookups see the whole fleet."""
        for v in self.fleet:
            if v.imo not in self._tracks:
                self._generate(v)

    # ---- generator (port of the prototype's _generate) ----
    def _generate(self, v: Vessel) -> None:
        rng = RNG(v.imo)
        risk, trade_key = self._risk[v.imo], self._trade[v.imo]
        kinds = {"tanker": "tanker", "bulk": "bulk", "container": "container", "gas": "gas", "other": "any"}
        fits = lambda p: kinds[v.type] in p.kinds or "any" in p.kinds or (v.type == "other" and "bulk" in p.kinds)
        trade = [self.ref.by_id[i] for i in self.cfg["trades"][trade_key]]
        sens = [self.ref.by_id[i] for i in self.cfg["sensitive_ports"][v.region] if fits(self.ref.by_id[i])]
        liquid = v.type in ("tanker", "bulk", "gas")
        T0 = self.now - YEAR - int((12 + rng() * 25) * D)
        router = self.routers[v.region]
        # phase 1: port sequence
        t = T0
        cur = rng.pick(trade)
        sens_left = 0 if risk < 0.3 else 1 if risk < 0.6 else 1 + int(risk * 3)
        legs = []
        while t < self.now + 20 * D:
            stay_h = 14 + rng() * 26 if v.type == "container" else 24 + rng() * 40 if v.type == "gas" else 48 + rng() * 150
            while True:
                nxt = rng.pick(sens) if (sens_left > 0 and rng() < risk * 0.3 and sens) else rng.pick(trade)
                if nxt.id != cur.id:
                    break
            if nxt.zone:
                sens_left -= 1
            anchor_h = 0.0
            if nxt.anch and rng() < (0.3 if v.type == "container" else 0.55):
                anchor_h = 6 + rng() * 40 if v.type == "container" else 10 + rng() * 130
            route = router.route(self._port_nodes[cur.id][0], self._port_nodes[nxt.id][0])
            path = [[cur.lon, cur.lat], [cur.approach_lon, cur.approach_lat], *route[1:-1], [nxt.approach_lon, nxt.approach_lat]]
            nm_total = sum(nm_dist(path[i - 1][1], path[i - 1][0], path[i][1], path[i][0]) for i in range(1, len(path)))
            speed = v.speed * (0.92 + rng() * 0.16)
            leg = {"from": cur, "to": nxt, "stay_h": stay_h, "anchor_h": anchor_h, "path": path, "nm": nm_total, "speed": speed, "events": [], "t_start": t}
            t += int(stay_h * H + nm_total / speed * H + anchor_h * H + 2 * H)
            leg["t_end"] = t
            legs.append(leg)
            cur = nxt
        # phase 2: plant events
        n_gaps = (1 if rng() < 0.45 else 0) if risk < 0.25 else 1 + (1 if rng() < 0.5 else 0) if risk < 0.6 else 2 + int(rng() * 2)
        n_dr = 0 if risk < 0.4 else (1 if rng() < risk else 0) + (1 if risk > 0.8 else 0)
        n_sts = 0 if risk < 0.4 else (1 if rng() < risk else 0) + (1 if (risk > 0.85 and rng() < 0.6) else 0)
        n_jump = int(rng() * 2.4)
        long_legs = [l for l in legs if l["nm"] / l["speed"] > 14 and l["t_end"] < self.now - 2 * D and not l["events"]]
        sens_legs = [l for l in long_legs if l["to"].zone or l["from"].zone]

        def take(pool):
            free = [l for l in pool if not l["events"]]
            return rng.pick(free) if free else None

        def choose(pref, typ, payload):
            leg = (take(pref) if (pref and rng() < 0.8) else None) or take(long_legs)
            if leg:
                leg["events"].append({"type": typ, **payload})
            return leg

        for _ in range(n_gaps):
            choose(sens_legs, "gap", {"hours": 18 + rng() * 40 if risk > 0.6 else 7 + rng() * 14, "at": 0.25 + rng() * 0.5})
        sts_legs = []
        for _ in range(n_sts):
            partners = [o for o in self.fleet if o.imo != v.imo and o.region == v.region and (v.type != "tanker" or o.type == "tanker")]
            leg = choose([], "sts", {"hours": 2.5 + rng() * 5, "at": 0.3 + rng() * 0.4, "partner": rng.pick(partners).imo})
            if leg:
                sts_legs.append(leg)
        for _ in range(n_dr):
            leg = sts_legs.pop(0) if (sts_legs and rng() < 0.8) else take(long_legs)
            if leg:
                leg["events"].append({"type": "draught", "at": 0.3 + rng() * 0.4, "delta": 1.3 + rng() * 2.8})
        for _ in range(n_jump):
            choose([], "jump", {"at": 0.2 + rng() * 0.6, "nm": 45 + rng() * 60})
        # phase 3: emit positions
        pts: list[Position] = []
        sts_reg: list[dict] = []
        loaded = rng() < 0.5
        draught = v.draught_loaded if loaded else v.draught_ballast
        jitter = lambda: int((rng() - 0.5) * 16 * 60e3)
        ports_r = self.ref.ports_in(v.region)

        def src_of(lat, lon):
            for p in ports_r:
                if abs(lat - p.lat) < 0.75 and abs(lon - p.lon) < 0.9 and nm_dist(lat, lon, p.lat, p.lon) < 45:
                    return "T"
            return "S"

        def emit(tt, lat, lon, sog, cog, nav):
            pts.append(Position(t=int(tt), lat=lat, lon=lon, sog=round(sog, 1), cog=round((cog + 360) % 360), draught=round(draught, 1), nav=nav, src=src_of(lat, lon)))
            if rng() < 0.003:
                pts.append(Position(**pts[-1].__dict__))
            if rng() < 0.0006:
                bad = Position(**pts[-1].__dict__)
                bad.t = int(tt) + 60_000
                bad.lat = 91.0
                pts.append(bad)

        transit_h = lambda a, b: max(1.0, nm_dist(a[1], a[0], b[1], b[0]) / 6)
        status: Optional[LiveStatic] = None
        t = T0
        for leg in legs:
            frm, to = leg["from"], leg["to"]
            h = 0.0
            while h < leg["stay_h"]:
                emit(t + h * H + jitter(), frm.lat + (rng() - 0.5) * 0.0012, frm.lon + (rng() - 0.5) * 0.0012, 0, 90 + rng() * 180, 5)
                h += 3
            if t + leg["stay_h"] * H > self.now:
                status = LiveStatic(destination=to.name.upper(), eta=None)
                break
            t += int(leg["stay_h"] * H + 0.5 * H)
            if liquid:
                loaded = not loaded
                draught = (v.draught_loaded if loaded else v.draught_ballast) + (rng() - 0.5) * 0.4
            else:
                draught += (rng() - 0.5) * 0.8
            path = leg["path"]
            seg, total = [], 0.0
            for i in range(1, len(path)):
                d = nm_dist(path[i - 1][1], path[i - 1][0], path[i][1], path[i][0])
                seg.append((path[i - 1], path[i], d, total))
                total += d

            def pos_at(dist):
                s = next((s for s in seg if dist <= s[3] + s[2]), seg[-1])
                f = max(0.0, min(1.0, (dist - s[3]) / (s[2] or 1)))
                return s[0][1] + (s[1][1] - s[0][1]) * f, s[0][0] + (s[1][0] - s[0][0]) * f, bearing(s[0][1], s[0][0], s[1][1], s[1][0])

            leg_h = total / leg["speed"]
            ev = leg["events"]
            gap = next((e for e in ev if e["type"] == "gap"), None)
            sts = next((e for e in ev if e["type"] == "sts"), None)
            dch = next((e for e in ev if e["type"] == "draught"), None)
            jump = next((e for e in ev if e["type"] == "jump"), None)
            gap_h0 = gap["at"] * leg_h if gap else -1
            gap_h1 = gap_h0 + gap["hours"] if gap else -1
            sts_h = sts["at"] * leg_h if sts else -1
            dr_h = (sts_h + sts["hours"] + 0.5 if sts else dch["at"] * leg_h) if dch else -1
            jmp_h = jump["at"] * leg_h if jump else -1
            t_leg = t
            sts_done = dr_done = jmp_done = cut = False
            dest = "FOR ORDERS" if (risk > 0.8 and rng() < 0.5) else to.name.upper()
            hh = 0
            while hh <= leg_h:
                plat, plon, pcog = pos_at(hh * leg["speed"])
                if sts and not sts_done and hh >= sts_h:
                    areas = sorted(self.ref.sts_areas, key=lambda a: nm_dist(plat, plon, a["lonlat"][1], a["lonlat"][0]))
                    area = areas[0]
                    ad = nm_dist(plat, plon, area["lonlat"][1], area["lonlat"][0])
                    slat, slon = (area["lonlat"][1], area["lonlat"][0]) if ad < 90 else (plat, plon)
                    tr = math.ceil(ad / leg["speed"]) if ad < 90 else 0
                    for k in range(1, tr + 1):
                        f = k / tr
                        emit(t_leg + k * H + jitter(), plat + (slat - plat) * f, plon + (slon - plon) * f, leg["speed"], bearing(plat, plon, slat, slon), 0)
                    t_leg += tr * H + H
                    t0 = t_leg
                    k = 0.0
                    while k <= sts["hours"]:
                        emit(t_leg + k * H + jitter() / 4, slat + (rng() - 0.5) * 0.0008, slon + (rng() - 0.5) * 0.0008, 0.2 + rng() * 0.4, rng() * 360, 0)
                        k += 0.5
                    t_leg += int(sts["hours"] * H + H)
                    sts_reg.append({"imo": v.imo, "partner": sts["partner"], "lat": slat, "lon": slon, "t0": t0, "t1": t_leg - H, "area": area["name"]})
                    for k in range(1, tr + 1):
                        f = k / tr
                        emit(t_leg + k * H + jitter(), slat + (plat - slat) * f, slon + (plon - slon) * f, leg["speed"], bearing(slat, slon, plat, plon), 0)
                    t_leg += tr * H
                    sts_done = True
                if dch and not dr_done and hh >= dr_h:
                    draught += -dch["delta"] if loaded else dch["delta"]
                    dr_done = True
                if gap and gap_h0 <= hh < gap_h1:
                    t_leg += H
                    hh += 1
                    if t_leg > self.now:
                        cut = True
                        break
                    continue
                if jump and not jmp_done and hh >= jmp_h:
                    jlat, jlon = dest_point(plat, plon, rng() * 360, jump["nm"])
                    emit(t_leg + 0.5 * H, jlat, jlon, leg["speed"], pcog, 0)
                    jmp_done = True
                emit(t_leg + jitter(), plat, plon, leg["speed"] + (rng() - 0.5) * 0.8, pcog + (rng() - 0.5) * 6, 0)
                t_leg += H
                hh += 1
                if t_leg > self.now:
                    cut = True
                    break
            if cut:
                rem = max(0.0, total - (t_leg - t) / H * leg["speed"])
                status = LiveStatic(destination=dest, eta=int(self.now + rem / leg["speed"] * H))
                break
            t = t_leg
            pos = path[-1]
            if leg["anchor_h"]:
                alon, alat, ar = to.anch
                plat, plon = dest_point(alat, alon, rng() * 360, rng() * ar * 0.6)
                t += int(transit_h(pos, [plon, plat]) * H)
                h = 0.0
                while h < leg["anchor_h"]:
                    emit(t + h * H + jitter(), plat + (rng() - 0.5) * 0.002, plon + (rng() - 0.5) * 0.002, rng() * 0.2, rng() * 360, 1)
                    h += 3
                if t + leg["anchor_h"] * H > self.now:
                    status = LiveStatic(destination=dest, eta=None)
                    break
                t += int(leg["anchor_h"] * H + 0.5 * H)
                pos = [plon, plat]
            t += int(transit_h(pos, [to.lon, to.lat]) * H)
        track = sorted((p for p in pts if p.t <= self.now), key=lambda p: p.t)
        self._tracks[v.imo] = track
        self._sts.extend(sts_reg)
        self._static[v.imo] = status or LiveStatic(destination="", eta=None)
