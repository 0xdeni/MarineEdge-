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
