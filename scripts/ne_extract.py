"""Natural Earth (public domain) → one compact GeoJSON for the app's offline base map.
Clipped to the MarineEdge regions, simplified for zooms 0–8, coordinates to 3 decimals."""
import json
import math
import sys
from pathlib import Path

NE = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/ne/geojson")   # Natural Earth 10m layers as GeoJSON (naturalearthdata.com)
OUT = Path(sys.argv[1])
BOX = (8.0, 5.0, 76.0, 58.0)   # lon/lat; the map stops a degree inside it (map.js maxBounds)


def clip_ring(ring, box):
    """Sutherland–Hodgman against an axis-aligned box. Returns a closed ring or []."""
    x0, y0, x1, y1 = box

    def clip(pts, inside, inter):
        out = []
        if not pts:
            return out
        prev = pts[-1]
        for cur in pts:
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
            prev = cur
        return out

    def ix(a, b, x):
        t = (x - a[0]) / ((b[0] - a[0]) or 1e-12)
        return (x, a[1] + t * (b[1] - a[1]))

    def iy(a, b, y):
        t = (y - a[1]) / ((b[1] - a[1]) or 1e-12)
        return (a[0] + t * (b[0] - a[0]), y)

    pts = [tuple(p[:2]) for p in ring]
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    pts = clip(pts, lambda p: p[0] >= x0, lambda a, b: ix(a, b, x0))
    pts = clip(pts, lambda p: p[0] <= x1, lambda a, b: ix(a, b, x1))
    pts = clip(pts, lambda p: p[1] >= y0, lambda a, b: iy(a, b, y0))
    pts = clip(pts, lambda p: p[1] <= y1, lambda a, b: iy(a, b, y1))
    if len(pts) < 3:
        return []
    return pts + [pts[0]]


def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy)
        dmax, idx = 0.0, -1
        for i in range(a + 1, b):
            x0, y0 = pts[i]
            d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / n if n else math.hypot(x0 - x1, y0 - y1)
            if d > dmax:
                dmax, idx = d, i
        if dmax > eps and idx > 0:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def r3(p):
    return [round(p[0], 3), round(p[1], 3)]


def area(r):
    return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2


def polys(name, eps, min_area=0.0, filt=None):
    d = json.loads((NE / f"{name}.geojson").read_text())
    out = []
    for f in d["features"]:
        if filt and not filt(f["properties"]):
            continue
        g = f["geometry"]
        if not g:
            continue
        ps = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in ps:
            rings = []
            for k, ring in enumerate(poly):
                c = clip_ring(ring, BOX)
                if not c:
                    if k == 0:
                        break
                    continue
                s = rdp(c, eps)
                if len(s) < 4 or area(s) < (min_area if k == 0 else min_area / 4):
                    if k == 0:
                        break
                    continue
                rings.append([r3(p) for p in s])
            if rings:
                out.append(rings)
    return out


def lines(name, eps, filt=None):
    d = json.loads((NE / f"{name}.geojson").read_text())
    x0, y0, x1, y1 = BOX
    out = []
    for f in d["features"]:
        if filt and not filt(f["properties"]):
            continue
        g = f["geometry"]
        if not g:
            continue
        ls = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for line in ls:
            seg = []
            for p in line:
                if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                    seg.append(p[:2])
                else:
                    if len(seg) > 1:
                        out.append([r3(q) for q in rdp(seg, eps)])
                    seg = []
            if len(seg) > 1:
                out.append([r3(q) for q in rdp(seg, eps)])
    return out


feats = []


def add_polys(layer, ps, **props):
    for rings in ps:
        feats.append({"type": "Feature", "properties": {"l": layer, **props}, "geometry": {"type": "Polygon", "coordinates": rings}})


add_polys("land", polys("ne_10m_land", 0.008, 0.00002))
add_polys("land", polys("ne_10m_minor_islands", 0.004, 0.00001))
for depth, name in [(200, "ne_10m_bathymetry_K_200"), (1000, "ne_10m_bathymetry_J_1000"), (2000, "ne_10m_bathymetry_I_2000"), (3000, "ne_10m_bathymetry_H_3000"), (4000, "ne_10m_bathymetry_G_4000")]:
    add_polys("depth", polys(name, 0.02, 0.0005), d=depth)
add_polys("lake", polys("ne_10m_lakes", 0.01, 0.0005, filt=lambda p: (p.get("scalerank") or 9) <= 8))
for ln in lines("ne_10m_rivers_lake_centerlines", 0.01, filt=lambda p: (p.get("scalerank") or 9) <= 7):
    feats.append({"type": "Feature", "properties": {"l": "river"}, "geometry": {"type": "LineString", "coordinates": ln}})
for ln in lines("ne_10m_admin_0_boundary_lines_land", 0.006):
    feats.append({"type": "Feature", "properties": {"l": "border"}, "geometry": {"type": "LineString", "coordinates": ln}})

pp = json.loads((NE / "ne_10m_populated_places_simple.geojson").read_text())
n_places = 0
for f in pp["features"]:
    p = f["properties"]
    lon, lat = f["geometry"]["coordinates"][:2]
    if not (BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]):
        continue
    sr = p.get("scalerank", 10)
    if sr > 7:
        continue
    cap = 1 if (p.get("featurecla") or "").startswith("Admin-0 capital") else 0
    feats.append({"type": "Feature", "properties": {"l": "place", "n": p.get("name"), "r": sr, "c": cap, "pop": p.get("pop_max") or 0},
                  "geometry": {"type": "Point", "coordinates": r3([lon, lat])}})
    n_places += 1

cl = json.loads((NE / "ne_10m_admin_0_label_points.geojson").read_text())
for f in cl["features"]:
    p = f["properties"]
    lon, lat = f["geometry"]["coordinates"][:2]
    if not (BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]):
        continue
    nm = p.get("name") or p.get("sr_subunit")
    if not nm or (p.get("scalerank") or 10) > 4:
        continue
    feats.append({"type": "Feature", "properties": {"l": "country", "n": nm, "r": p.get("scalerank") or 4}, "geometry": {"type": "Point", "coordinates": r3([lon, lat])}})

mp = json.loads((NE / "ne_10m_geography_marine_polys.geojson").read_text())
SEA_LABELS = {"Black Sea": (34.2, 43.4), "Sea of Azov": (36.4, 46.2), "Aegean Sea": (25.0, 38.6), "Sea of Marmara": (28.0, 40.75), "Mediterranean Sea": (30.5, 33.6),
              "Persian Gulf": (51.6, 27.1), "Gulf of Oman": (58.8, 24.5), "Arabian Sea": (62.0, 17.5), "Red Sea": (38.5, 20.5), "Caspian Sea": (51.0, 41.5),
              "Sea of Crete": (25.0, 35.9), "Gulf of Aden": (48.0, 12.6), "Ionian Sea": (18.6, 37.4), "Adriatic Sea": (15.6, 43.0)}
for name, (lon, lat) in SEA_LABELS.items():
    feats.append({"type": "Feature", "properties": {"l": "sea", "n": name}, "geometry": {"type": "Point", "coordinates": [lon, lat]}})

OUT.write_text(json.dumps({"type": "FeatureCollection", "attribution": "Natural Earth (public domain)", "features": feats}, separators=(",", ":")))
print(OUT, OUT.stat().st_size, "bytes", len(feats), "features", n_places, "places")
