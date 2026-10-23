"""Synthetic track builder for the rule-engine tests. Builds hourly positions along straight legs
between real ports from config/ports.csv, with helpers to plant each kind of event."""
from __future__ import annotations

from app.engine.geo import bearing, dest_point, nm_dist
from app.engine.types import H, Port, Position


class Track:
    def __init__(self, t0: int, lat: float, lon: float, draught: float = 9.0, speed: float = 12.0):
        self.t = t0
        self.lat, self.lon = lat, lon
        self.draught = draught
        self.speed = speed
        self.pts: list[Position] = []

    def _emit(self, sog: float, cog: float, nav: int, src: str = "T") -> Position:
        p = Position(t=self.t, lat=self.lat, lon=self.lon, sog=sog, cog=cog, draught=round(self.draught, 1), nav=nav, src=src)
        self.pts.append(p)
        return p

    def _no_dup(self) -> None:
        if self.pts and self.pts[-1].t >= self.t:
            self.t = self.pts[-1].t + 60_000

    def moor(self, hours: float, nav: int = 5) -> "Track":
        """Stay put, one fix every 3 h (plus one at the end)."""
        self._no_dup()
        end = self.t + int(hours * H)
        while self.t < end:
            self._emit(0.0, 90.0, nav)
            self.t += 3 * H
        self.t = end
        self._emit(0.0, 90.0, nav)
        return self

    def sail_to(self, lat: float, lon: float, gap: tuple[float, float] | None = None, src: str = "T") -> "Track":
        """Hourly fixes along the rhumb line. gap=(at_fraction, hours) suppresses fixes for that window."""
        total = nm_dist(self.lat, self.lon, lat, lon)
        cog = bearing(self.lat, self.lon, lat, lon)
        hours = total / self.speed
        n = int(hours)
        lat0, lon0 = self.lat, self.lon
        gap_start = gap_end = -1.0
        if gap:
            gap_start = gap[0] * hours
            gap_end = gap_start + gap[1]
        h = 1
        while h <= n:
            f = h / hours
            self.lat = lat0 + (lat - lat0) * f
            self.lon = lon0 + (lon - lon0) * f
            self.t += H
            if not (gap_start <= h < gap_end):
                self._emit(self.speed, cog, 0, src)
            h += 1
        # final fix at the destination
        self.lat, self.lon = lat, lon
        self.t += int((hours - n) * H) + 1
        self._emit(self.speed, cog, 0, src)
        return self

    def sail_to_port(self, p: Port, **kw) -> "Track":
        return self.sail_to(p.lat, p.lon, **kw)

    def drift(self, hours: float, sog: float = 0.3) -> "Track":
        """Loiter at the current position (STS / dark activity), fixes every 30 min."""
        self._no_dup()
        end = self.t + int(hours * H)
        while self.t <= end:
            self._emit(sog, 10.0, 0)
            self.t += H // 2
        return self

    def set_draught(self, d: float) -> "Track":
        self.draught = d
        return self

    def jump(self, nm: float, brg: float = 45.0) -> "Track":
        """One bogus fix nm away, 30 min after the last, then back on track."""
        jlat, jlon = dest_point(self.lat, self.lon, brg, nm)
        self.pts.append(Position(t=self.t + H // 2, lat=jlat, lon=jlon, sog=self.speed, cog=90.0, draught=round(self.draught, 1)))
        return self

    def duplicate_last(self) -> "Track":
        self.pts.append(Position(**self.pts[-1].__dict__))
        return self

    def bad_fix(self) -> "Track":
        self.pts.append(Position(t=self.t + 60_000, lat=91.0, lon=self.lon, sog=0, cog=0, draught=self.draught))
        return self
