"""Position cache: the rule "every paid position is fetched once and kept". Two implementations with
the same interface: PostgresStore (production, PostGIS) and MemoryStore (dev/tests/mock mode)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional, Protocol

from app.engine.types import Analysis, Position


class Store(Protocol):
    def covered(self, imo: int, start_ms: int, end_ms: int) -> bool: ...
    def get_positions(self, imo: int, start_ms: int, end_ms: int) -> list[Position]: ...
    def put_positions(self, imo: int, pts: list[Position], provider: str, start_ms: int, end_ms: int, credits: int) -> None: ...
    def save_analysis(self, a: Analysis) -> None: ...
    def list_sanctions(self, imo: int) -> list[dict]: ...


class MemoryStore:
    def __init__(self) -> None:
        self.pos: dict[int, dict[int, Position]] = {}
        self.windows: dict[int, list[tuple[int, int]]] = {}
        self.sanctions: dict[int, list[dict]] = {}

    def covered(self, imo, start_ms, end_ms):
        return any(a <= start_ms and b >= end_ms - 6 * 3_600_000 for a, b in self.windows.get(imo, []))

    def get_positions(self, imo, start_ms, end_ms):
        return sorted((p for p in self.pos.get(imo, {}).values() if start_ms <= p.t <= end_ms), key=lambda p: p.t)

    def put_positions(self, imo, pts, provider, start_ms, end_ms, credits):
        d = self.pos.setdefault(imo, {})
        for p in pts:
            d[p.t] = p
        self.windows.setdefault(imo, []).append((start_ms, end_ms))

    def save_analysis(self, a):
        pass

    def list_sanctions(self, imo):
        return self.sanctions.get(imo, [])


class PostgresStore:
    """psycopg (v3) implementation. Only imported when DATABASE_URL is set."""

    def __init__(self, dsn: Optional[str] = None):
        import psycopg  # type: ignore
        self.dsn = dsn or os.environ["DATABASE_URL"]
        self.psycopg = psycopg

    def _conn(self):
        return self.psycopg.connect(self.dsn)

    @staticmethod
    def _ts(ms: int) -> datetime:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    def covered(self, imo, start_ms, end_ms):
        with self._conn() as c:
            row = c.execute("SELECT 1 FROM fetch_log WHERE imo=%s AND window_from<=%s AND window_to>=%s LIMIT 1",
                            (imo, self._ts(start_ms), self._ts(end_ms - 6 * 3_600_000))).fetchone()
        return row is not None

    def get_positions(self, imo, start_ms, end_ms):
        with self._conn() as c:
            rows = c.execute("SELECT ts, lat, lon, sog, cog, draught, nav, src FROM positions WHERE imo=%s AND ts BETWEEN %s AND %s ORDER BY ts",
                             (imo, self._ts(start_ms), self._ts(end_ms))).fetchall()
        return [Position(t=int(r[0].timestamp() * 1000), lat=r[1], lon=r[2], sog=r[3] or 0, cog=r[4] or 0, draught=r[5] or 0, nav=r[6] or 0, src=r[7] or "T") for r in rows]

    def put_positions(self, imo, pts, provider, start_ms, end_ms, credits):
        with self._conn() as c:
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO positions (imo, ts, geom, lat, lon, sog, cog, draught, nav, src, provider) "
                    "VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    [(imo, self._ts(p.t), p.lon, p.lat, p.lat, p.lon, p.sog, p.cog, p.draught, p.nav, p.src, provider) for p in pts])
                cur.execute("INSERT INTO fetch_log (imo, window_from, window_to, provider, positions, credits) VALUES (%s,%s,%s,%s,%s,%s)",
                            (imo, self._ts(start_ms), self._ts(end_ms), provider, len(pts), credits))
            c.commit()

    def save_analysis(self, a: Analysis):
        v = a.vessel
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute("""INSERT INTO vessels (imo, name, mmsi, callsign, flag, type, sub, dwt, gt, loa_m, beam_m, built, builder, draught_loaded, draught_ballast, region,
                               reg_owner, ben_owner, ism, operator, class_soc, pi, service_speed, updated_at)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                               ON CONFLICT (imo) DO UPDATE SET name=EXCLUDED.name, mmsi=EXCLUDED.mmsi, flag=EXCLUDED.flag, updated_at=now()""",
                            (v.imo, v.name, v.mmsi, v.callsign, v.flag, v.type, v.sub, v.dwt, v.gt, v.loa, v.beam, v.built, v.builder, v.draught_loaded, v.draught_ballast, v.region,
                             v.reg_owner, v.ben_owner, v.ism, v.operator, v.class_soc, v.pi, v.speed))
                cur.execute("DELETE FROM flags WHERE imo=%s", (v.imo,))
                cur.execute("DELETE FROM voyages WHERE imo=%s", (v.imo,))
                cur.execute("DELETE FROM port_calls WHERE imo=%s", (v.imo,))
                call_ids: dict[int, int] = {}
                for pc in a.port_calls:
                    row = cur.execute("INSERT INTO port_calls (imo, port_id, port_name, anchorage, arrived, departed, draught_in, draught_out, anch_hours, geom) "
                                      "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) RETURNING id",
                                      (v.imo, None if pc.port.pseudo else pc.port.id, pc.port.name, pc.anchorage, self._ts(pc.arrive), self._ts(pc.depart), pc.draught_in, pc.draught_out, pc.anch_hours, pc.lon, pc.lat)).fetchone()
                    call_ids[id(pc)] = row[0]
                voy_ids: dict[int, int] = {}
                for vg in a.voyages:
                    pts = [p for p in a.track[vg.i0:vg.i1 + 1] if not p.jump]
                    wkt = "LINESTRING(" + ",".join(f"{p.lon} {p.lat}" for p in pts) + ")" if len(pts) > 1 else None
                    row = cur.execute("INSERT INTO voyages (imo, n, from_call, to_call, departed, arrived, distance_nm, draught_out, draught_in, dark_hours, current, track) "
                                      "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s IS NULL THEN NULL ELSE ST_GeogFromText(%s) END) RETURNING id",
                                      (v.imo, vg.n, call_ids.get(id(vg.frm)), call_ids.get(id(vg.to)), self._ts(vg.depart), self._ts(vg.arrive) if vg.arrive else None,
                                       vg.nm, vg.draught_out, vg.draught_in, vg.dark_h, vg.current, wkt, wkt)).fetchone()
                    voy_ids[id(vg)] = row[0]
                for f in a.flags:
                    ev = {"before": [p.__dict__ for p in f.evidence_before], "after": [p.__dict__ for p in f.evidence_after]} if f.evidence_before or f.evidence_after else None
                    cur.execute("INSERT INTO flags (imo, voyage_id, rule, severity, title, lines, t0, t1, geom, evidence, partner_imo) "
                                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography END, %s, %s)",
                                (v.imo, voy_ids.get(id(f.voyage)) if f.voyage else None, f.rule, f.severity, f.title, json.dumps(f.lines), self._ts(f.t0), self._ts(f.t1) if f.t1 else None,
                                 f.lon, f.lon, f.lat, json.dumps(ev) if ev else None, f.partner_imo))
            c.commit()

    def list_sanctions(self, imo):
        with self._conn() as c:
            rows = c.execute("SELECT list_name, programme, listed_at FROM sanctions WHERE imo=%s AND delisted_at IS NULL", (imo,)).fetchall()
        return [{"list": r[0], "programme": r[1] or "", "t": int(datetime(r[2].year, r[2].month, r[2].day, tzinfo=timezone.utc).timestamp() * 1000)} for r in rows if r[2]]


def make_store() -> Store:
    return PostgresStore() if os.environ.get("DATABASE_URL") else MemoryStore()
