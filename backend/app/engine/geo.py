"""Geometry helpers. Positions are (lat, lon) in degrees; distances in nautical miles."""
from __future__ import annotations

import math
from typing import Sequence

EARTH_NM = 3440.065
RAD = math.pi / 180.0


def nm_dist(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles (haversine)."""
    dl = (lat2 - lat1) * RAD
    dn = (lon2 - lon1) * RAD
    a = math.sin(dl / 2) ** 2 + math.cos(lat1 * RAD) * math.cos(lat2 * RAD) * math.sin(dn / 2) ** 2
    return 2 * EARTH_NM * math.asin(math.sqrt(min(1.0, a)))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    y = math.sin((lon2 - lon1) * RAD) * math.cos(lat2 * RAD)
    x = math.cos(lat1 * RAD) * math.sin(lat2 * RAD) - math.sin(lat1 * RAD) * math.cos(lat2 * RAD) * math.cos((lon2 - lon1) * RAD)
    return (math.atan2(y, x) / RAD + 360.0) % 360.0


def dest_point(lat: float, lon: float, brg: float, nm: float) -> tuple[float, float]:
    la, lo, b, d = lat * RAD, lon * RAD, brg * RAD, nm / EARTH_NM
    la2 = math.asin(math.sin(la) * math.cos(d) + math.cos(la) * math.sin(d) * math.cos(b))
    lo2 = lo + math.atan2(math.sin(b) * math.sin(d) * math.cos(la), math.cos(d) - math.sin(la) * math.sin(la2))
    return la2 / RAD, lo2 / RAD


def point_in_poly(lon: float, lat: float, poly: Sequence[Sequence[float]]) -> bool:
    """Ray casting. poly is a list of [lon, lat] vertices (open or closed ring)."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > lat) != (yj > lat) and lon < xi + (lat - yi) * (xj - xi) / (yj - yi):
            inside = not inside
        j = i
    return inside


def poly_dist_nm(lon: float, lat: float, poly: Sequence[Sequence[float]]) -> float:
    """Distance from a point to a polygon outline in nm; 0 when inside. Flat approximation, fine for < 500 nm."""
    if point_in_poly(lon, lat, poly):
        return 0.0
    k = math.cos(lat * RAD) * 60.0
    px, py = lon * k, lat * 60.0
    best = float("inf")
    n = len(poly)
    j = n - 1
    for i in range(n):
        ax, ay = poly[j][0] * k, poly[j][1] * 60.0
        bx, by = poly[i][0] * k, poly[i][1] * 60.0
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
        j = i
    return best


def fmt_dm(lat: float, lon: float) -> str:
    """44°43.0′N 037°46.0′E"""
    def f(v: float, pos: str, neg: str, w: int) -> str:
        a = abs(v)
        d = int(a)
        m = (a - d) * 60
        return f"{d:0{w}d}°{m:04.1f}′{pos if v >= 0 else neg}"
    return f"{f(lat, 'N', 'S', 2)} {f(lon, 'E', 'W', 3)}"
