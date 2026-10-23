"""Step 6: voyages. One voyage per departure → arrival between consecutive port calls; the track
before the first call is 'history start', the track after the last call is the current voyage."""
from __future__ import annotations

from typing import Optional

from .geo import nm_dist
from .types import PortCall, Position, Voyage


def split_voyages(track: list[Position], calls: list[PortCall]) -> list[Voyage]:
    voyages: list[Voyage] = []

    def add(frm: Optional[PortCall], to: Optional[PortCall], i0: int, i1: int) -> None:
        pts = track[i0:i1 + 1]
        if len(pts) < 2:
            return
        nm = 0.0
        for k in range(1, len(pts)):
            if not pts[k].jump and not pts[k - 1].jump:
                nm += nm_dist(pts[k - 1].lat, pts[k - 1].lon, pts[k].lat, pts[k].lon)
        depart = frm.depart if frm else pts[0].t
        arrive = to.arrive if to else None
        voyages.append(Voyage(n=0, frm=frm, to=to, i0=i0, i1=i1, depart=depart, arrive=arrive, nm=round(nm),
                              draught_out=pts[min(2, len(pts) - 1)].draught, draught_in=pts[-1].draught, current=to is None))

    if not calls:
        add(None, None, 0, len(track) - 1)
    else:
        if calls[0].i0 > 3:
            add(None, calls[0], 0, calls[0].i0)
        for k in range(len(calls) - 1):
            add(calls[k], calls[k + 1], calls[k].i1, calls[k + 1].i0)
        last = calls[-1]
        if len(track) - 1 - last.i1 > 3:
            add(last, None, last.i1, len(track) - 1)
    for i, v in enumerate(voyages):
        v.n = i + 1
    return voyages
