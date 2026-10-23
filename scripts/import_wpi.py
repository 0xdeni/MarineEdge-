#!/usr/bin/env python3
"""Import the NGA World Port Index into config/ports.csv.

Download (free, no account): https://msi.nga.mil/Publications/WPI → "World Port Index CSV" (or the
shapefile converted to CSV with ogr2ogr). Then:

    python scripts/import_wpi.py path/to/WPI.csv            # merge, keep hand-placed rows
    python scripts/import_wpi.py path/to/WPI.csv --dry-run  # show what would change

The NGA export uses the field names from the WPI feature service (World_Port_Index_Number /
wpinumber, Main_Port_Name / main_port_name, Latitude/Longitude or point geometry, Harbor_Size /
harbor_size_code, Country_Code / wpi_cc, UN_LOCODE / unlocode, fac_solidbulk, fac_liquidbulk,
fac_container, fac_lngterm, fac_oilterm). Names are matched case-insensitively with underscores or
spaces, so either spelling works.

Rules:
  - Hand-placed ports already in config/ports.csv (with approach points, anchorages, zones) are kept as
    they are; WPI rows that match them by UN/LOCODE or by name within 3 nm only fill blank fields.
  - New ports get approach = berth (the router uses the nearest sea-lane node) and no anchorage circle.
  - Only ports inside the configured regions are imported (bounding boxes in REGIONS below), so the
    file stays small and the port-call detector stays fast. Pass --all to import the whole world.
  - Kinds come from the facilities flags: solid bulk → bulk, liquid bulk/oil terminal → tanker,
    container → container, LNG → gas; none → any. Harbor size L/M → major.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTS = ROOT / "config" / "ports.csv"
REGIONS = {"A": (22.5, 30.0, 43.0, 48.0), "B": (44.0, 15.5, 64.5, 31.5)}   # Black Sea + E. Med · Gulf + Arabian Sea
FIELDS = ["id", "name", "country", "region", "berth_lon", "berth_lat", "approach_lon", "approach_lat", "kinds", "major", "zone", "anch_lon", "anch_lat", "anch_radius_nm"]


def norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def pick(row: dict, *names: str) -> str:
    keys = {norm(k): k for k in row}
    for n in names:
        k = keys.get(norm(n))
        if k is not None and row[k] not in (None, ""):
            return str(row[k]).strip()
    return ""


def nm(lat1, lon1, lat2, lon2) -> float:
    r = math.pi / 180
    a = math.sin((lat2 - lat1) * r / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2
    return 2 * 3440.065 * math.asin(math.sqrt(a))


def yes(v: str) -> bool:
    return v.strip().lower() in ("y", "yes", "1", "true", "t")


def region_of(lon: float, lat: float) -> str | None:
    for k, (x0, y0, x1, y1) in REGIONS.items():
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            return k
    return None


def read_wpi(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        name = pick(r, "Main_Port_Name", "main_port_name", "PORT_NAME", "Main Port Name")
        lat, lon = pick(r, "Latitude", "LATITUDE", "lat", "Y"), pick(r, "Longitude", "LONGITUDE", "lon", "X")
        if not name or not lat or not lon:
            continue
        try:
            lat_f, lon_f = float(lat), float(lon)
        except ValueError:
            continue
        kinds = []
        if yes(pick(r, "fac_solidbulk", "Facilities_Solid_Bulk", "SOLID_BULK")): kinds.append("bulk")
        if yes(pick(r, "fac_liquidbulk", "Facilities_Liquid_Bulk", "LIQUID_BULK")) or yes(pick(r, "fac_oilterm", "Facilities_Oil_Terminal", "OIL_TERMINAL")): kinds.append("tanker")
        if yes(pick(r, "fac_container", "Facilities_Container", "CONTAINER")): kinds.append("container")
        if yes(pick(r, "fac_lngterm", "Facilities_LNG_Terminal", "LNG_TERMINAL")): kinds.append("gas")
        size = pick(r, "harbor_size_code", "Harbor_Size", "HARBORSIZE").upper()[:1]
        out.append({
            "wpi": pick(r, "wpinumber", "World_Port_Index_Number", "INDEX_NO"),
            "name": name.title() if name.isupper() else name,
            "country": pick(r, "wpi_cc", "Country_Code", "COUNTRY"),
            "unlocode": pick(r, "unlocode", "UN_LOCODE", "UNLOCODE").replace(" ", ""),
            "lat": lat_f, "lon": lon_f,
            "kinds": ",".join(kinds) or "any",
            "major": size in ("L", "M"),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wpi_csv", type=Path)
    ap.add_argument("--all", action="store_true", help="import every port, not only the configured regions")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path, default=PORTS)
    a = ap.parse_args()

    existing: list[dict] = []
    if a.out.exists():
        with open(a.out, newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    by_id = {r["id"] for r in existing}
    wpi = read_wpi(a.wpi_csv)
    added, filled, skipped = 0, 0, 0
    for w in wpi:
        region = region_of(w["lon"], w["lat"])
        if region is None and not a.all:
            skipped += 1
            continue
        # match a hand-placed port by UN/LOCODE id or by name within 3 nm
        match = None
        for e in existing:
            if w["unlocode"] and e["id"].upper() == w["unlocode"].upper():
                match = e
                break
            if norm(e["name"]) == norm(w["name"]) and nm(float(e["berth_lat"]), float(e["berth_lon"]), w["lat"], w["lon"]) <= 3:
                match = e
                break
        if match is not None:
            changed = False
            if not match.get("country") and w["country"]:
                match["country"] = w["country"]; changed = True
            if match.get("kinds") in ("", "any") and w["kinds"] != "any":
                match["kinds"] = w["kinds"]; changed = True
            filled += changed
            continue
        pid = w["unlocode"] or ("WPI" + w["wpi"] if w["wpi"] else norm(w["name"])[:10].upper())
        if pid in by_id:
            pid = pid + "-" + (w["wpi"] or str(added))
        by_id.add(pid)
        existing.append({"id": pid, "name": w["name"], "country": w["country"], "region": region or "",
                         "berth_lon": f"{w['lon']:.4f}", "berth_lat": f"{w['lat']:.4f}", "approach_lon": f"{w['lon']:.4f}", "approach_lat": f"{w['lat']:.4f}",
                         "kinds": w["kinds"], "major": "1" if w["major"] else "0", "zone": "", "anch_lon": "", "anch_lat": "", "anch_radius_nm": ""})
        added += 1
    print(f"WPI rows read: {len(wpi)} · added: {added} · filled: {filled} · outside regions: {skipped} · total ports: {len(existing)}")
    if a.dry_run:
        return 0
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in existing:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
