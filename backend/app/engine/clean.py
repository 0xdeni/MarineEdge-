"""Step 4: clean the raw track. Drop impossible coordinates, duplicate timestamps, and sort."""
from __future__ import annotations

from .types import Position


def clean_track(raw: list[Position]) -> tuple[list[Position], int, int]:
    """Returns (clean_track, duplicates_dropped, bad_fixes_dropped)."""
    seen: set[int] = set()
    out: list[Position] = []
    dup = bad = 0
    for p in sorted(raw, key=lambda p: p.t):
        if not (isinstance(p.lat, (int, float)) and isinstance(p.lon, (int, float))) or abs(p.lat) > 90 or abs(p.lon) > 180:
            bad += 1
            continue
        if p.t in seen:
            dup += 1
            continue
        seen.add(p.t)
        out.append(Position(t=p.t, lat=p.lat, lon=p.lon, sog=p.sog, cog=p.cog, draught=p.draught, nav=p.nav, src=p.src))
    return out, dup, bad
