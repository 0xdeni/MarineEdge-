"""Reference data: ports (config/ports.csv), sensitive zones (config/zones.geojson) and
known GPS-jamming / STS areas (config/areas.json)."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Optional

from .geo import nm_dist, point_in_poly, poly_dist_nm
from .types import Port, Zone

CONFIG_DIR = Path(os.environ.get("VVT_CONFIG", Path(__file__).resolve().parents[3] / "config"))


class RefData:
    def __init__(self, ports: list[Port], zones: list[Zone], jamming: list[dict], sts_areas: list[dict]):
        self.ports = ports
        self.zones = zones
        self.jamming = jamming
        self.sts_areas = sts_areas
        self.by_id = {p.id: p for p in ports}
        self.zone_by_id = {z.id: z for z in zones}

    # ---- zones ----
    def zone_at(self, lon: float, lat: float) -> Optional[Zone]:
        for z in self.zones:
            if z.enabled and point_in_poly(lon, lat, z.poly):
                return z
        return None

    def nearest_zone(self, lon: float, lat: float) -> tuple[Optional[Zone], float]:
        best, bd = None, float("inf")
        for z in self.zones:
            if not z.enabled:
                continue
            d = poly_dist_nm(lon, lat, z.poly)
            if d < bd:
                best, bd = z, d
        return best, bd

    def jamming_at(self, lon: float, lat: float) -> Optional[dict]:
        for j in self.jamming:
            b = j["box"]
            if b[0] <= lon <= b[2] and b[1] <= lat <= b[3]:
                return j
        return None

    # ---- ports ----
    def ports_in(self, region: Optional[str]) -> list[Port]:
        return [p for p in self.ports if region is None or p.region == region]

    def nearest_port(self, lon: float, lat: float, region: Optional[str] = None) -> tuple[Optional[Port], float]:
        best, bd = None, float("inf")
        for p in self.ports_in(region):
            d = nm_dist(lat, lon, p.lat, p.lon)
            if d < bd:
                best, bd = p, d
        return best, bd


def load_refdata(config_dir: str | os.PathLike | None = None) -> RefData:
    d = Path(config_dir or CONFIG_DIR)
    ports: list[Port] = []
    with open(d / "ports.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            anch = None
            if r.get("anch_lon"):
                anch = (float(r["anch_lon"]), float(r["anch_lat"]), float(r["anch_radius_nm"]))
            ports.append(Port(id=r["id"], name=r["name"], country=r["country"], region=r["region"],
                              lon=float(r["berth_lon"]), lat=float(r["berth_lat"]),
                              approach_lon=float(r["approach_lon"]), approach_lat=float(r["approach_lat"]),
                              kinds=r["kinds"], major=r["major"] == "1", zone=r["zone"] or None, anch=anch))
    zones: list[Zone] = []
    with open(d / "zones.geojson", encoding="utf-8") as f:
        for ft in json.load(f)["features"]:
            pr = ft["properties"]
            ring = ft["geometry"]["coordinates"][0]
            zones.append(Zone(id=pr["id"], name=pr["name"], basis=pr.get("basis", ""), poly=[list(p) for p in ring], enabled=pr.get("enabled", True),
                              short=pr.get("short") or pr["name"], default_on=pr.get("enabled", True)))
    jamming, sts_areas = [], []
    ap = d / "areas.json"
    if ap.exists():
        with open(ap, encoding="utf-8") as f:
            a = json.load(f)
            jamming, sts_areas = a.get("jamming", []), a.get("sts_areas", [])
    return RefData(ports, zones, jamming, sts_areas)
