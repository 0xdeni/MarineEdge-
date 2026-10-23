"""Step 5: port calls. A call is a run of positions slower than max_speed_kn lasting min_hours or more,
within port_radius_nm of a berth, inside a port's anchorage circle, or inside a sensitive zone
(an anchorage with no listed port). Anchorage + berth at the same port within merge_within_hours
count as one call."""
from __future__ import annotations

from typing import Optional

from .geo import nm_dist
from .refdata import RefData
from .rules_config import Rules
from .types import H, Port, PortCall, Position


def match_port(lat: float, lon: float, region: Optional[str], ref: RefData, rules: Rules) -> Optional[tuple[Port, bool]]:
    best, bd = ref.nearest_port(lon, lat, region)
    if best is not None and bd <= rules.port_call.port_radius_nm:
        return best, False
    for p in ref.ports_in(region):
        if p.anch and nm_dist(lat, lon, p.anch[1], p.anch[0]) <= p.anch[2]:
            return p, True
    z = ref.zone_at(lon, lat)
    if z is not None:
        pseudo = Port(id="Z-" + z.id, name="Anchorage · " + z.name, country="", region=region or "", lon=lon, lat=lat,
                      approach_lon=lon, approach_lat=lat, kinds="any", zone=z.id, pseudo=True)
        return pseudo, True
    return None


def detect_port_calls(track: list[Position], region: Optional[str], ref: RefData, rules: Rules) -> list[PortCall]:
    calls: list[PortCall] = []
    n = len(track)
    i = 0
    max_kn = rules.port_call.max_speed_kn
    while i < n:
        if track[i].sog < max_kn:
            j = i
            while j + 1 < n and track[j + 1].sog < max_kn and track[j + 1].t - track[j].t < 12 * H:
                j += 1
            # an ongoing call at the very end of the track counts even if it is still short
            if track[j].t - track[i].t >= rules.port_call.min_hours * H or j == n - 1:
                mid = track[(i + j) // 2]
                m = match_port(mid.lat, mid.lon, region, ref, rules)
                if m is not None:
                    port, anchorage = m
                    calls.append(PortCall(port=port, anchorage=anchorage, arrive=track[i].t, depart=track[j].t,
                                          lat=mid.lat, lon=mid.lon, i0=i, i1=j,
                                          draught_in=track[i].draught, draught_out=track[j].draught,
                                          anch_hours=(track[j].t - track[i].t) / H if anchorage else 0.0))
            i = j + 1
        else:
            i += 1
    merged: list[PortCall] = []
    for c in calls:
        last = merged[-1] if merged else None
        if last and last.port.id == c.port.id and c.arrive - last.depart < rules.port_call.merge_within_hours * H and (last.anchorage or c.anchorage):
            last.depart = c.depart
            last.i1 = c.i1
            last.draught_out = c.draught_out
            last.anch_hours += c.anch_hours
            if last.anchorage and not c.anchorage:
                last.anchorage = False
                last.lat, last.lon = c.lat, c.lon
        else:
            merged.append(PortCall(**c.__dict__))
    return merged
