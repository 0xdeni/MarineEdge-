"""Position cache: the rule "every paid position is fetched once and kept". Two implementations with
the same interface: PostgresStore (production, PostGIS) and MemoryStore (dev/tests/mock mode)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional, Protocol

from app.engine.types import Analysis, Position


class Store(Protocol):
    # positions (the cache rule)
    def covered(self, imo: int, start_ms: int, end_ms: int) -> bool: ...
    def latest_window_end(self, imo: int) -> Optional[int]: ...
    def get_positions(self, imo: int, start_ms: int, end_ms: int) -> list[Position]: ...
    def put_positions(self, imo: int, pts: list[Position], provider: str, start_ms: int, end_ms: int, credits: int) -> None: ...
    def save_analysis(self, a: Analysis) -> None: ...
    def list_sanctions(self, imo: int) -> list[dict]: ...
    # per-user state
    def user_id(self, name: str) -> int: ...
    def get_watchlist(self, user: str) -> list[int]: ...
    def set_watchlist(self, user: str, imos: list[int]) -> None: ...
    def all_watched(self) -> list[int]: ...
    def get_notes(self, user: str, imo: int) -> dict[str, str]: ...
    def set_note(self, user: str, imo: int, voyage_n: int, text: str) -> None: ...
    # live AIS recorded from aisstream (free path)
    def live_put(self, rows: list[dict]) -> None: ...
    def live_backfill_imo(self, mmsi: int, imo: int) -> None: ...
    def live_track(self, imo: int, start_ms: int, end_ms: int) -> list[dict]: ...
    def live_last(self, imo: int) -> Optional[dict]: ...
    def live_latest(self, bbox: tuple[float, float, float, float]) -> list[dict]: ...
    def live_near(self, lat: float, lon: float, radius_m: float, t0: int, t1: int) -> list[dict]: ...
    def live_search(self, q: str) -> list[dict]: ...
    def coverage_add(self, rows: list[tuple[int, int, int, int]]) -> None: ...   # (cx, cy, day_epoch_s, fixes)
    def live_coverage(self, days: int = 30) -> dict[tuple[int, int], int]: ...
    def live_prune(self, full_res_days: int, thin_minutes: int, retention_months: int, window_days: int = 3) -> dict: ...
    def live_stats(self) -> dict: ...
    def db_size(self) -> Optional[int]: ...                                     # bytes; None when not a database
    def mmsi_upsert(self, row: dict) -> None: ...
    def mmsi_by_imo(self, imo: int) -> list[dict]: ...
    def mmsi_all(self) -> list[dict]: ...
    # alerts & push
    def add_alert(self, imo: int, rule: str, t0_ms: int, severity: str, title: str, detail: str) -> bool: ...
    def list_alerts(self, since_ms: int, limit: int = 200) -> list[dict]: ...
    def add_push_subscription(self, user: str, sub: dict, user_agent: str) -> None: ...
    def remove_push_subscription(self, endpoint: str) -> None: ...
    def list_push_subscriptions(self, users: Optional[list[str]] = None) -> list[dict]: ...


def _chain_covers(windows: list[tuple[int, int]], start_ms: int, end_ms: int, slack_ms: int = 6 * 3_600_000) -> bool:
    """True when fetched windows, joined end to end (1 h overlap allowed), span [start, end - slack]."""
    reach = None
    for a, b in sorted(windows):
        if reach is None:
            if a <= start_ms:
                reach = b
        elif a <= reach + 3_600_000:
            reach = max(reach, b)
        if reach is not None and reach >= end_ms - slack_ms:
            return True
    return False


class MemoryStore:
    def __init__(self) -> None:
        self.pos: dict[int, dict[int, Position]] = {}
        self.windows: dict[int, list[tuple[int, int]]] = {}
        self.sanctions: dict[int, list[dict]] = {}
        self.watch: dict[str, list[int]] = {}
        self.notes: dict[tuple[str, int], dict[str, str]] = {}
        self.alerts: dict[tuple[int, str, int], dict] = {}
        self.subs: dict[str, dict] = {}
        self.live: dict[int, dict[int, dict]] = {}       # mmsi -> {t: row}
        self.mmsi: dict[int, dict] = {}
        self.cov: dict[tuple[int, int, int], int] = {}    # (cx, cy, day) -> fixes

    def covered(self, imo, start_ms, end_ms):
        return _chain_covers(self.windows.get(imo, []), start_ms, end_ms)

    def latest_window_end(self, imo):
        w = self.windows.get(imo)
        return max(b for _, b in w) if w else None

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

    def user_id(self, name):
        return abs(hash(name)) % 10_000_000

    def get_watchlist(self, user):
        return list(self.watch.get(user, []))

    def set_watchlist(self, user, imos):
        self.watch[user] = sorted(set(int(i) for i in imos))

    def all_watched(self):
        return sorted({i for v in self.watch.values() for i in v})

    def get_notes(self, user, imo):
        return dict(self.notes.get((user, imo), {}))

    def set_note(self, user, imo, voyage_n, text):
        d = self.notes.setdefault((user, imo), {})
        if text.strip():
            d[str(voyage_n)] = text
        else:
            d.pop(str(voyage_n), None)

    # ---- live AIS
    def live_put(self, rows):
        for r in rows:
            self.live.setdefault(r["mmsi"], {})[r["t"]] = dict(r)

    def live_backfill_imo(self, mmsi, imo):
        for r in self.live.get(mmsi, {}).values():
            if not r.get("imo"):
                r["imo"] = imo

    def _rows_for_imo(self, imo):
        for mmsi, m in self.mmsi.items():
            if m.get("imo") == imo:
                for r in self.live.get(mmsi, {}).values():
                    yield {**r, "imo": imo}

    def live_track(self, imo, start_ms, end_ms):
        return sorted((r for r in self._rows_for_imo(imo) if start_ms <= r["t"] <= end_ms), key=lambda r: r["t"])

    def live_last(self, imo):
        rows = self.live_track(imo, 0, 1 << 62)
        return rows[-1] if rows else None

    def live_latest(self, bbox):
        out = []
        for mmsi, pts in self.live.items():
            if not pts:
                continue
            r = pts[max(pts)]
            if bbox[0] <= r["lon"] <= bbox[2] and bbox[1] <= r["lat"] <= bbox[3]:
                m = self.mmsi.get(mmsi, {})
                out.append({**r, "imo": m.get("imo") or r.get("imo"), "name": m.get("name") or r.get("name")})
        return out

    def live_near(self, lat, lon, radius_m, t0, t1):
        from app.engine.geo import nm_dist
        out = {}
        for mmsi, pts in self.live.items():
            for t, r in pts.items():
                if t0 <= t <= t1 and nm_dist(lat, lon, r["lat"], r["lon"]) * 1852 <= radius_m:
                    o = out.setdefault(mmsi, {"mmsi": mmsi, "imo": self.mmsi.get(mmsi, {}).get("imo"), "name": self.mmsi.get(mmsi, {}).get("name"), "t0": t, "t1": t, "lat": r["lat"], "lon": r["lon"]})
                    o["t0"], o["t1"] = min(o["t0"], t), max(o["t1"], t)
        return list(out.values())

    def live_search(self, q):
        qu = q.upper()
        return [m for m in self.mmsi.values() if qu in (m.get("name") or "").upper() or str(m.get("imo") or "").startswith(qu) or str(m["mmsi"]).startswith(qu)]

    def coverage_add(self, rows):
        for cx, cy, day, n in rows:
            self.cov[(cx, cy, day)] = self.cov.get((cx, cy, day), 0) + n

    def live_coverage(self, days=30):
        import time as _t
        since = int(_t.time()) // 86_400 * 86_400 - days * 86_400
        cov: dict[tuple[int, int], int] = {}
        for (cx, cy, day), n in self.cov.items():
            if day >= since:
                cov[(cx, cy)] = cov.get((cx, cy), 0) + n
        return cov

    def live_prune(self, full_res_days, thin_minutes, retention_months, window_days=3):
        import time as _t
        now = int(_t.time() * 1000)
        cutoff_del = now - int(retention_months * 30.4 * 86_400_000)
        cutoff_thin = now - full_res_days * 86_400_000
        deleted = thinned = 0
        for mmsi, pts in self.live.items():
            for t in [t for t in pts if t < cutoff_del]:
                del pts[t]
                deleted += 1
            seen: set[int] = set()
            for t in sorted(pts):
                if t >= cutoff_thin:
                    break
                b = t // (thin_minutes * 60_000)
                if b in seen:
                    del pts[t]
                    thinned += 1
                else:
                    seen.add(b)
        return {"deleted": deleted, "thinned": thinned}

    def live_stats(self):
        n = sum(len(p) for p in self.live.values())
        ts = [t for p in self.live.values() for t in p]
        return {"positions": n, "mmsi": len(self.mmsi) or len(self.live), "with_imo": sum(1 for m in self.mmsi.values() if m.get("imo")), "oldest": min(ts) if ts else None, "newest": max(ts) if ts else None}

    def db_size(self):
        return None

    def mmsi_upsert(self, row):
        self.mmsi[row["mmsi"]] = {**self.mmsi.get(row["mmsi"], {}), **row}

    def mmsi_by_imo(self, imo):
        return [m for m in self.mmsi.values() if m.get("imo") == imo]

    def mmsi_all(self):
        return list(self.mmsi.values())

    def add_alert(self, imo, rule, t0_ms, severity, title, detail):
        key = (imo, rule, t0_ms // 3_600_000)
        if key in self.alerts:
            return False
        self.alerts[key] = {"imo": imo, "rule": rule, "t0": t0_ms, "severity": severity, "title": title, "detail": detail, "created_at": int(__import__("time").time() * 1000)}
        return True

    def list_alerts(self, since_ms, limit=200):
        return sorted((a for a in self.alerts.values() if a["created_at"] >= since_ms), key=lambda a: -a["created_at"])[:limit]

    def add_push_subscription(self, user, sub, user_agent):
        self.subs[sub["endpoint"]] = {"user": user, "sub": sub, "user_agent": user_agent}

    def remove_push_subscription(self, endpoint):
        self.subs.pop(endpoint, None)

    def list_push_subscriptions(self, users=None):
        return [v for v in self.subs.values() if users is None or v["user"] in users]


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
            rows = c.execute("SELECT window_from, window_to FROM fetch_log WHERE imo=%s ORDER BY window_from", (imo,)).fetchall()
        return _chain_covers([(int(a.timestamp() * 1000), int(b.timestamp() * 1000)) for a, b in rows], start_ms, end_ms)

    def latest_window_end(self, imo):
        with self._conn() as c:
            row = c.execute("SELECT max(window_to) FROM fetch_log WHERE imo=%s", (imo,)).fetchone()
        return int(row[0].timestamp() * 1000) if row and row[0] else None

    def get_positions(self, imo, start_ms, end_ms):
        with self._conn() as c:
            rows = c.execute("SELECT ts, lat, lon, sog, cog, draught, nav, src FROM positions WHERE imo=%s AND ts BETWEEN %s AND %s ORDER BY ts",
                             (imo, self._ts(start_ms), self._ts(end_ms))).fetchall()
        return [Position(t=int(r[0].timestamp() * 1000), lat=r[1], lon=r[2], sog=r[3] or 0, cog=r[4] or 0, draught=r[5] or 0, nav=r[6] or 0, src=r[7] or "T") for r in rows]

    def put_positions(self, imo, pts, provider, start_ms, end_ms, credits):
        with self._conn() as c:
            with c.cursor() as cur:
                # positions.imo references vessels(imo); the first fetch for a ship happens before save_analysis
                # writes its particulars, so make sure the parent row exists (name is filled in later).
                cur.execute("INSERT INTO vessels (imo, name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (imo, str(imo)))
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

    # ---- per-user state (users.email holds the token name until SSO maps real emails)
    def user_id(self, name):
        with self._conn() as c:
            row = c.execute("INSERT INTO users (email, name) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET email=EXCLUDED.email RETURNING id", (name, name)).fetchone()
            c.commit()
        return row[0]

    def get_watchlist(self, user):
        uid = self.user_id(user)
        with self._conn() as c:
            rows = c.execute("SELECT imo FROM watchlist WHERE user_id=%s ORDER BY added_at", (uid,)).fetchall()
        return [r[0] for r in rows]

    def set_watchlist(self, user, imos):
        uid = self.user_id(user)
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM watchlist WHERE user_id=%s AND NOT (imo = ANY(%s))", (uid, list(imos) or [0]))
                for imo in imos:
                    cur.execute("INSERT INTO vessels (imo, name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (imo, str(imo)))
                    cur.execute("INSERT INTO watchlist (user_id, imo) VALUES (%s, %s) ON CONFLICT DO NOTHING", (uid, imo))
            c.commit()

    def all_watched(self):
        with self._conn() as c:
            rows = c.execute("SELECT DISTINCT imo FROM watchlist ORDER BY imo").fetchall()
        return [r[0] for r in rows]

    def get_notes(self, user, imo):
        uid = self.user_id(user)
        with self._conn() as c:
            rows = c.execute("SELECT voyage_n, text FROM notes WHERE user_id=%s AND imo=%s", (uid, imo)).fetchall()
        return {str(r[0]): r[1] for r in rows}

    def set_note(self, user, imo, voyage_n, text):
        uid = self.user_id(user)
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM notes WHERE user_id=%s AND imo=%s AND voyage_n=%s", (uid, imo, voyage_n))
                if text.strip():
                    cur.execute("INSERT INTO notes (user_id, imo, voyage_n, text) VALUES (%s,%s,%s,%s)", (uid, imo, voyage_n, text))
            c.commit()

    # ---- live AIS (ais_live + mmsi_map)
    def live_put(self, rows):
        with self._conn() as c:
            with c.cursor() as cur:
                cur.executemany("INSERT INTO ais_live (mmsi, ts, lat, lon, sog, cog, heading, nav, draught, imo) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                [(r["mmsi"], self._ts(r["t"]), r["lat"], r["lon"], r.get("sog"), r.get("cog"), r.get("heading"), r.get("nav"), r.get("draught"), r.get("imo")) for r in rows])
            c.commit()

    def live_backfill_imo(self, mmsi, imo):
        with self._conn() as c:
            c.execute("UPDATE ais_live SET imo=%s WHERE mmsi=%s AND imo IS NULL", (imo, mmsi))
            c.commit()

    @staticmethod
    def _live_row(r):
        return {"mmsi": r[0], "t": int(r[1].timestamp() * 1000), "lat": r[2], "lon": r[3], "sog": r[4], "cog": r[5], "heading": r[6], "nav": r[7], "draught": r[8], "imo": r[9]}

    def live_track(self, imo, start_ms, end_ms):
        with self._conn() as c:
            rows = c.execute("SELECT mmsi, ts, lat, lon, sog, cog, heading, nav, draught, imo FROM ais_live WHERE imo=%s AND ts BETWEEN %s AND %s ORDER BY ts",
                             (imo, self._ts(start_ms), self._ts(end_ms))).fetchall()
        return [self._live_row(r) for r in rows]

    def live_last(self, imo):
        with self._conn() as c:
            r = c.execute("SELECT mmsi, ts, lat, lon, sog, cog, heading, nav, draught, imo FROM ais_live WHERE imo=%s ORDER BY ts DESC LIMIT 1", (imo,)).fetchone()
        return self._live_row(r) if r else None

    def live_latest(self, bbox):
        with self._conn() as c:
            rows = c.execute("""SELECT DISTINCT ON (a.mmsi) a.mmsi, a.ts, a.lat, a.lon, a.sog, a.cog, a.heading, a.nav, a.draught, COALESCE(a.imo, m.imo), m.name
                                FROM ais_live a LEFT JOIN mmsi_map m ON m.mmsi = a.mmsi
                                WHERE a.ts > now() - interval '6 hours' AND a.lon BETWEEN %s AND %s AND a.lat BETWEEN %s AND %s
                                ORDER BY a.mmsi, a.ts DESC""", (bbox[0], bbox[2], bbox[1], bbox[3])).fetchall()
        return [{**self._live_row(r[:10]), "name": r[10]} for r in rows]

    LIVE_NEAR_SQL = """SELECT a.mmsi, COALESCE(a.imo, m.imo), m.name, min(a.ts), max(a.ts), avg(a.lat), avg(a.lon)
        FROM ais_live a LEFT JOIN mmsi_map m ON m.mmsi = a.mmsi
        WHERE a.ts BETWEEN %s AND %s
          AND a.lat BETWEEN %s AND %s AND a.lon BETWEEN %s AND %s
          AND 2 * 6371008.8 * asin(least(1, sqrt(power(sin(radians(a.lat - %s) / 2), 2)
                + cos(radians(%s)) * cos(radians(a.lat)) * power(sin(radians(a.lon - %s) / 2), 2)))) <= %s
        GROUP BY a.mmsi, COALESCE(a.imo, m.imo), m.name"""

    def live_near(self, lat, lon, radius_m, t0, t1):
        """Ships within radius_m of a point during [t0, t1]: the primary key (ts, mmsi) narrows the time window,
        a lat/lon box narrows the place, a great-circle distance decides. No PostGIS needed for the live table."""
        import math
        dlat = radius_m / 111_320.0
        dlon = radius_m / (111_320.0 * max(0.01, math.cos(math.radians(lat))))
        with self._conn() as c:
            rows = c.execute(self.LIVE_NEAR_SQL, (self._ts(t0), self._ts(t1), lat - dlat, lat + dlat, lon - dlon, lon + dlon, lat, lat, lon, radius_m)).fetchall()
        return [{"mmsi": r[0], "imo": r[1], "name": r[2], "t0": int(r[3].timestamp() * 1000), "t1": int(r[4].timestamp() * 1000), "lat": r[5], "lon": r[6]} for r in rows]

    def live_search(self, q):
        qu = q.upper()
        with self._conn() as c:
            rows = c.execute("SELECT mmsi, imo, name, callsign, type_code, destination, draught FROM mmsi_map WHERE upper(name) LIKE %s OR CAST(imo AS TEXT) LIKE %s OR CAST(mmsi AS TEXT) LIKE %s LIMIT 24",
                             (f"%{qu}%", f"{qu}%", f"{qu}%")).fetchall()
        return [{"mmsi": r[0], "imo": r[1], "name": r[2], "callsign": r[3], "type_code": r[4], "destination": r[5], "draught": r[6]} for r in rows]

    def coverage_add(self, rows):
        if not rows:
            return
        with self._conn() as c:
            with c.cursor() as cur:
                cur.executemany("INSERT INTO coverage_cells (cx, cy, day, fixes) VALUES (%s, %s, to_timestamp(%s)::date, %s) "
                                "ON CONFLICT (cx, cy, day) DO UPDATE SET fixes = coverage_cells.fixes + EXCLUDED.fixes", rows)
            c.commit()

    def live_coverage(self, days=30):
        with self._conn() as c:
            rows = c.execute("SELECT cx, cy, sum(fixes) FROM coverage_cells WHERE day >= current_date - %s GROUP BY 1, 2", (days,)).fetchall()
        return {(r[0], r[1]): int(r[2]) for r in rows}

    def live_prune(self, full_res_days, thin_minutes, retention_months, window_days=3):
        """Tiered retention. Thinning only looks at the slice that just crossed full_res_days (plus a few
        days of catch-up) so the daily job stays cheap; window_days=None thins the whole old table once."""
        with self._conn() as c:
            deleted = c.execute("DELETE FROM ais_live WHERE ts < now() - make_interval(months => %s)", (retention_months,)).rowcount
            lower = "" if window_days is None else "AND ts >= now() - make_interval(days => %s)"
            params: list = [thin_minutes * 60, full_res_days] + ([] if window_days is None else [full_res_days + window_days])
            thinned = c.execute(f"""DELETE FROM ais_live a USING (
                    SELECT mmsi, ts, row_number() OVER (PARTITION BY mmsi, floor(extract(epoch FROM ts) / %s) ORDER BY ts) rn
                    FROM ais_live WHERE ts < now() - make_interval(days => %s) {lower}) t
                WHERE a.mmsi = t.mmsi AND a.ts = t.ts AND t.rn > 1""", params).rowcount
            c.execute("DELETE FROM coverage_cells WHERE day < current_date - %s", (int(retention_months * 30.4),))
            c.commit()
        return {"deleted": deleted, "thinned": thinned}

    def live_stats(self):
        with self._conn() as c:
            est = c.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'ais_live'").fetchone()
            newest = c.execute("SELECT max(ts) FROM ais_live").fetchone()[0]
            oldest = c.execute("SELECT min(ts) FROM ais_live").fetchone()[0]
            n_mmsi, n_imo = c.execute("SELECT count(*), count(imo) FROM mmsi_map").fetchone()
        n = int(est[0]) if est and est[0] is not None and est[0] >= 0 else 0
        if n == 0 and newest is not None:   # before the first ANALYZE the estimate is 0 or -1: count exactly, capped at 1M rows
            n = self._count_small()
        return {"positions": n, "mmsi": n_mmsi, "with_imo": n_imo, "oldest": int(oldest.timestamp() * 1000) if oldest else None, "newest": int(newest.timestamp() * 1000) if newest else None, "estimate": True}

    def db_size(self):
        with self._conn() as c:
            return int(c.execute("SELECT pg_database_size(current_database())").fetchone()[0])

    def _count_small(self):
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM (SELECT 1 FROM ais_live LIMIT 1000000) s").fetchone()[0]

    def mmsi_upsert(self, row):
        dim = row.get("dim") or [None, None, None, None]
        with self._conn() as c:
            c.execute("""INSERT INTO mmsi_map (mmsi, imo, name, callsign, type_code, destination, eta, draught, dim_a, dim_b, dim_c, dim_d, updated_at)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                         ON CONFLICT (mmsi) DO UPDATE SET imo=COALESCE(EXCLUDED.imo, mmsi_map.imo), name=COALESCE(EXCLUDED.name, mmsi_map.name), callsign=COALESCE(EXCLUDED.callsign, mmsi_map.callsign),
                           type_code=COALESCE(EXCLUDED.type_code, mmsi_map.type_code), destination=COALESCE(EXCLUDED.destination, mmsi_map.destination), eta=COALESCE(EXCLUDED.eta, mmsi_map.eta),
                           draught=COALESCE(EXCLUDED.draught, mmsi_map.draught), dim_a=COALESCE(EXCLUDED.dim_a, mmsi_map.dim_a), dim_b=COALESCE(EXCLUDED.dim_b, mmsi_map.dim_b),
                           dim_c=COALESCE(EXCLUDED.dim_c, mmsi_map.dim_c), dim_d=COALESCE(EXCLUDED.dim_d, mmsi_map.dim_d), updated_at=now()""",
                      (row["mmsi"], row.get("imo"), row.get("name"), row.get("callsign"), row.get("type_code"), row.get("destination"),
                       self._ts(row["eta"]) if row.get("eta") else None, row.get("draught"), dim[0], dim[1], dim[2], dim[3]))
            c.commit()

    @staticmethod
    def _mmsi_row(r):
        return {"mmsi": r[0], "imo": r[1], "name": r[2], "callsign": r[3], "type_code": r[4], "destination": r[5], "eta": int(r[6].timestamp() * 1000) if r[6] else None,
                "draught": r[7], "dim": [r[8], r[9], r[10], r[11]], "updated_at": int(r[12].timestamp() * 1000) if r[12] else None}

    def mmsi_by_imo(self, imo):
        with self._conn() as c:
            rows = c.execute("SELECT mmsi, imo, name, callsign, type_code, destination, eta, draught, dim_a, dim_b, dim_c, dim_d, updated_at FROM mmsi_map WHERE imo=%s", (imo,)).fetchall()
        return [self._mmsi_row(r) for r in rows]

    def mmsi_all(self):
        with self._conn() as c:
            rows = c.execute("SELECT mmsi, imo, name, callsign, type_code, destination, eta, draught, dim_a, dim_b, dim_c, dim_d, updated_at FROM mmsi_map").fetchall()
        return [self._mmsi_row(r) for r in rows]

    # ---- alerts & push
    def add_alert(self, imo, rule, t0_ms, severity, title, detail):
        hour = self._ts(t0_ms - t0_ms % 3_600_000)
        with self._conn() as c:
            row = c.execute("INSERT INTO alerts (imo, rule, t0_hour, severity, title, detail) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                            (imo, rule, hour, severity, title, detail)).fetchone()
            c.commit()
        return row is not None

    def list_alerts(self, since_ms, limit=200):
        with self._conn() as c:
            rows = c.execute("SELECT imo, rule, t0_hour, severity, title, detail, created_at FROM alerts WHERE created_at >= %s ORDER BY created_at DESC LIMIT %s",
                             (self._ts(since_ms), limit)).fetchall()
        return [{"imo": r[0], "rule": r[1], "t0": int(r[2].timestamp() * 1000), "severity": r[3], "title": r[4], "detail": r[5], "created_at": int(r[6].timestamp() * 1000)} for r in rows]

    def add_push_subscription(self, user, sub, user_agent):
        uid = self.user_id(user)
        keys = sub.get("keys", {})
        with self._conn() as c:
            c.execute("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent) VALUES (%s,%s,%s,%s,%s) "
                      "ON CONFLICT (endpoint) DO UPDATE SET p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth, failed_at=NULL", (uid, sub["endpoint"], keys.get("p256dh", ""), keys.get("auth", ""), user_agent))
            c.commit()

    def remove_push_subscription(self, endpoint):
        with self._conn() as c:
            c.execute("DELETE FROM push_subscriptions WHERE endpoint=%s", (endpoint,))
            c.commit()

    def list_push_subscriptions(self, users=None):
        with self._conn() as c:
            if users is None:
                rows = c.execute("SELECT u.email, s.endpoint, s.p256dh, s.auth FROM push_subscriptions s JOIN users u ON u.id=s.user_id WHERE s.failed_at IS NULL").fetchall()
            else:
                rows = c.execute("SELECT u.email, s.endpoint, s.p256dh, s.auth FROM push_subscriptions s JOIN users u ON u.id=s.user_id WHERE s.failed_at IS NULL AND u.email = ANY(%s)", (list(users),)).fetchall()
        return [{"user": r[0], "sub": {"endpoint": r[1], "keys": {"p256dh": r[2], "auth": r[3]}}} for r in rows]


def make_store() -> Store:
    return PostgresStore() if os.environ.get("DATABASE_URL") else MemoryStore()
