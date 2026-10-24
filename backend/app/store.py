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
    def name_seen(self, mmsi: int, old: Optional[str], new: str, t_ms: int) -> None: ...
    def names_for_imo(self, imo: int) -> list[dict]: ...                       # {name, first_seen, last_seen}, oldest first
    def sanctions_status(self) -> dict: ...                                     # {rows, refreshed}
    # alerts & push
    def add_alert(self, imo: int, rule: str, t0_ms: int, severity: str, title: str, detail: str) -> bool: ...
    def list_alerts(self, since_ms: int, limit: int = 200) -> list[dict]: ...
    def add_push_subscription(self, user: str, sub: dict, user_agent: str) -> None: ...
    def remove_push_subscription(self, endpoint: str) -> None: ...
    def list_push_subscriptions(self, users: Optional[list[str]] = None) -> list[dict]: ...
    def get_alerts_seen(self, user: str) -> int: ...
    def set_alerts_seen(self, user: str, t_ms: int) -> None: ...
    # accounts (app/accounts.py): users, sessions, invites, password resets — times are epoch ms
    def count_users(self) -> int: ...
    def get_user(self, user_id: int) -> Optional[dict]: ...
    def get_user_by_email(self, email: str) -> Optional[dict]: ...
    def create_user(self, email: str, name: str, role: str, password_hash: str) -> int: ...
    def adopt_user(self, legacy_email: str, email: str, name: str, role: str, password_hash: str) -> Optional[int]: ...
    def update_user(self, user_id: int, **fields) -> None: ...
    def delete_user(self, user_id: int) -> None: ...
    def list_users(self) -> list[dict]: ...
    def create_session(self, user_id: int, token_hash: str, user_agent: str, ip: str, expires_ms: int) -> int: ...
    def get_session(self, token_hash: str) -> Optional[dict]: ...
    def touch_session(self, session_id: int, seen_ms: int, expires_ms: int) -> None: ...
    def delete_session(self, session_id: int) -> None: ...
    def delete_user_sessions(self, user_id: int, except_id: Optional[int] = None) -> int: ...
    def list_sessions(self, user_id: int) -> list[dict]: ...
    def create_invite(self, code_hash: str, email: Optional[str], role: str, created_by: Optional[int], expires_ms: int) -> int: ...
    def get_invite(self, code_hash: str) -> Optional[dict]: ...
    def use_invite(self, invite_id: int, user_id: int) -> None: ...
    def list_invites(self) -> list[dict]: ...
    def delete_invite(self, invite_id: int) -> None: ...
    def create_reset(self, user_id: int, code_hash: Optional[str], token_hash: str, expires_ms: int, created_by: Optional[int]) -> int: ...
    def get_reset_by_token(self, token_hash: str) -> Optional[dict]: ...
    def get_active_reset(self, user_id: int) -> Optional[dict]: ...
    def bump_reset_attempts(self, reset_id: int) -> None: ...
    def mark_reset_used(self, reset_id: int) -> None: ...
    # team notes on a ship, a voyage ("voyage:N") or a finding ("flag:KEY")
    def list_vessel_notes(self, imo: int) -> list[dict]: ...
    def get_vessel_note(self, note_id: int) -> Optional[dict]: ...
    def add_vessel_note(self, imo: int, scope: str, user: str, text: str) -> int: ...
    def update_vessel_note(self, note_id: int, text: str) -> None: ...
    def delete_vessel_note(self, note_id: int) -> None: ...
    # risk summary per ship (written with every analysis) and sanctions membership, for the region overview
    def save_risk(self, imo: int, row: dict) -> None: ...
    def get_risk(self, imos: list[int]) -> dict[int, dict]: ...
    def sanctioned(self, imos: list[int]) -> set[int]: ...


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


def _ms_now() -> int:
    import time as _t
    return int(_t.time() * 1000)


class MemoryStore:
    def __init__(self) -> None:
        self.pos: dict[int, dict[int, Position]] = {}
        self.windows: dict[int, list[tuple[int, int]]] = {}
        self.sanctions: dict[int, list[dict]] = {}
        self.watch: dict[int, list[int]] = {}             # user id -> IMOs
        self.notes: dict[tuple[int, int], dict[str, str]] = {}
        self.alerts: dict[tuple[int, str, int], dict] = {}
        self.subs: dict[str, dict] = {}
        self.live: dict[int, dict[int, dict]] = {}       # mmsi -> {t: row}
        self.mmsi: dict[int, dict] = {}
        self.cov: dict[tuple[int, int, int], int] = {}    # (cx, cy, day) -> fixes
        self.users: dict[int, dict] = {}
        self.sess: dict[int, dict] = {}
        self.invites: dict[int, dict] = {}
        self.resets: dict[int, dict] = {}
        self.vnotes: dict[int, dict] = {}
        self.risk: dict[int, dict] = {}
        self.seen: dict[int, int] = {}
        self.names: dict[int, dict[str, list[int]]] = {}  # mmsi -> {name: [first_seen, last_seen]}
        self._ids = 0

    def _next(self) -> int:
        self._ids += 1
        return self._ids

    # ---- accounts
    def count_users(self):
        return sum(1 for u in self.users.values() if u.get("password_hash"))

    def get_user(self, user_id):
        u = self.users.get(user_id)
        return dict(u) if u else None

    def get_user_by_email(self, email):
        e = (email or "").lower()
        for u in self.users.values():
            if u["email"] == e and u.get("password_hash"):
                return dict(u)
        return None

    def _by_email_any(self, email):
        e = (email or "").lower()
        return next((u for u in self.users.values() if u["email"] == e), None)

    def create_user(self, email, name, role, password_hash):
        e = email.lower()
        if self._by_email_any(e):
            u = self._by_email_any(e)
            if u.get("password_hash"):
                raise ValueError("email exists")
            u.update(name=name, role=role, password_hash=password_hash, status="active", updated_at=_ms_now())
            return u["id"]
        uid = self._next()
        self.users[uid] = {"id": uid, "email": e, "name": name, "role": role, "password_hash": password_hash, "status": "active", "prefs": {},
                           "created_at": _ms_now(), "updated_at": _ms_now(), "last_login_at": None, "last_seen_at": None}
        return uid

    def adopt_user(self, legacy_email, email, name, role, password_hash):
        u = self._by_email_any(legacy_email)
        if not u or u.get("password_hash"):
            return None
        u.update(email=email.lower(), name=name, role=role, password_hash=password_hash, status="active", updated_at=_ms_now())
        return u["id"]

    def update_user(self, user_id, **fields):
        u = self.users.get(user_id)
        if u:
            if "email" in fields:
                fields["email"] = fields["email"].lower()
            u.update(fields)
            u["updated_at"] = _ms_now()

    def delete_user(self, user_id):
        self.users.pop(user_id, None)
        for sid in [s for s, v in self.sess.items() if v["user_id"] == user_id]:
            self.sess.pop(sid)
        self.watch.pop(user_id, None)
        for k in [k for k in self.notes if k[0] == user_id]:
            self.notes.pop(k)
        for ep in [ep for ep, v in self.subs.items() if v["user_id"] == user_id]:
            self.subs.pop(ep)
        for n in self.vnotes.values():
            if n.get("user_id") == user_id:
                n["user_id"] = None

    def list_users(self):
        return [dict(u) for u in self.users.values()]

    def create_session(self, user_id, token_hash, user_agent, ip, expires_ms):
        sid = self._next()
        self.sess[sid] = {"id": sid, "user_id": user_id, "token_hash": token_hash, "user_agent": user_agent, "ip": ip,
                          "created_at": _ms_now(), "last_seen_at": _ms_now(), "expires_at": expires_ms}
        return sid

    def get_session(self, token_hash):
        s = next((v for v in self.sess.values() if v["token_hash"] == token_hash), None)
        return dict(s) if s else None

    def touch_session(self, session_id, seen_ms, expires_ms):
        if session_id in self.sess:
            self.sess[session_id].update(last_seen_at=seen_ms, expires_at=expires_ms)

    def delete_session(self, session_id):
        self.sess.pop(session_id, None)

    def delete_user_sessions(self, user_id, except_id=None):
        gone = [s for s, v in self.sess.items() if v["user_id"] == user_id and s != except_id]
        for s in gone:
            self.sess.pop(s)
        return len(gone)

    def list_sessions(self, user_id):
        t = _ms_now()
        return [dict(v) for v in self.sess.values() if v["user_id"] == user_id and v["expires_at"] > t]

    def create_invite(self, code_hash, email, role, created_by, expires_ms):
        iid = self._next()
        self.invites[iid] = {"id": iid, "code_hash": code_hash, "email": email, "role": role, "created_by": created_by, "created_at": _ms_now(),
                             "expires_at": expires_ms, "used_at": None, "used_by": None}
        return iid

    def get_invite(self, code_hash):
        i = next((v for v in self.invites.values() if v["code_hash"] == code_hash), None)
        return dict(i) if i else None

    def use_invite(self, invite_id, user_id):
        if invite_id in self.invites:
            self.invites[invite_id].update(used_at=_ms_now(), used_by=user_id)

    def list_invites(self):
        return sorted((dict(v) for v in self.invites.values()), key=lambda i: -i["created_at"])

    def delete_invite(self, invite_id):
        self.invites.pop(invite_id, None)

    def create_reset(self, user_id, code_hash, token_hash, expires_ms, created_by):
        rid = self._next()
        self.resets[rid] = {"id": rid, "user_id": user_id, "code_hash": code_hash, "token_hash": token_hash, "created_by": created_by,
                            "created_at": _ms_now(), "expires_at": expires_ms, "attempts": 0, "used_at": None}
        return rid

    def get_reset_by_token(self, token_hash):
        r = next((v for v in self.resets.values() if v["token_hash"] == token_hash), None)
        return dict(r) if r else None

    def get_active_reset(self, user_id):
        rs = [v for v in self.resets.values() if v["user_id"] == user_id and v.get("code_hash") and not v.get("used_at")]
        return dict(max(rs, key=lambda r: r["id"])) if rs else None

    def bump_reset_attempts(self, reset_id):
        if reset_id in self.resets:
            self.resets[reset_id]["attempts"] += 1

    def mark_reset_used(self, reset_id):
        if reset_id in self.resets:
            self.resets[reset_id]["used_at"] = _ms_now()

    # ---- team notes
    def _note_out(self, n):
        u = self.users.get(n.get("user_id")) if n.get("user_id") else None
        return {**n, "author": (u or {}).get("name") or ((u or {}).get("email") or "").split("@")[0] or None, "author_email": (u or {}).get("email")}

    def list_vessel_notes(self, imo):
        return [self._note_out(n) for n in sorted(self.vnotes.values(), key=lambda n: n["created_at"]) if n["imo"] == imo]

    def get_vessel_note(self, note_id):
        n = self.vnotes.get(note_id)
        return self._note_out(n) if n else None

    def add_vessel_note(self, imo, scope, user, text):
        nid = self._next()
        self.vnotes[nid] = {"id": nid, "imo": imo, "scope": scope, "user_id": self.user_id(user), "text": text, "created_at": _ms_now(), "updated_at": _ms_now()}
        return nid

    def update_vessel_note(self, note_id, text):
        if note_id in self.vnotes:
            self.vnotes[note_id].update(text=text, updated_at=_ms_now())

    def delete_vessel_note(self, note_id):
        self.vnotes.pop(note_id, None)

    # ---- risk summary
    def save_risk(self, imo, row):
        self.risk[imo] = {**row, "imo": imo, "analysed_at": _ms_now()}

    def get_risk(self, imos):
        return {i: dict(self.risk[i]) for i in imos if i in self.risk}

    def sanctioned(self, imos):
        return {i for i in imos if self.sanctions.get(i)}

    def get_alerts_seen(self, user):
        return self.seen.get(self.user_id(user), 0)

    def set_alerts_seen(self, user, t_ms):
        self.seen[self.user_id(user)] = t_ms

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
        """Find-or-create by email, like PostgresStore: account emails and API-token names share the table."""
        u = self._by_email_any(name)
        if u:
            return u["id"]
        uid = self._next()
        self.users[uid] = {"id": uid, "email": (name or "").lower(), "name": name, "role": "analyst", "password_hash": None, "status": "active",
                           "prefs": {}, "created_at": _ms_now(), "updated_at": _ms_now(), "last_login_at": None, "last_seen_at": None}
        return uid

    def get_watchlist(self, user):
        return list(self.watch.get(self.user_id(user), []))

    def set_watchlist(self, user, imos):
        self.watch[self.user_id(user)] = sorted(set(int(i) for i in imos))

    def all_watched(self):
        return sorted({i for v in self.watch.values() for i in v})

    def get_notes(self, user, imo):
        return dict(self.notes.get((self.user_id(user), imo), {}))

    def set_note(self, user, imo, voyage_n, text):
        d = self.notes.setdefault((self.user_id(user), imo), {})
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
                out.append({**r, "imo": m.get("imo") or r.get("imo"), "name": m.get("name") or r.get("name"), "callsign": m.get("callsign"),
                            "type_code": m.get("type_code"), "destination": m.get("destination"), "eta": m.get("eta"),
                            "static_draught": m.get("draught"), "dim": m.get("dim")})
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
        out = []
        for m in self.mmsi.values():
            former = next((n for n in self.names.get(m["mmsi"], {}) if qu in n.upper() and n != m.get("name")), None)
            if qu in (m.get("name") or "").upper() or str(m.get("imo") or "").startswith(qu) or str(m["mmsi"]).startswith(qu) or former:
                out.append({**m, "former": former if former and qu not in (m.get("name") or "").upper() else None})
        return out

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

    def name_seen(self, mmsi, old, new, t_ms):
        d = self.names.setdefault(mmsi, {})
        if old and old != new and old not in d:
            d[old] = [t_ms - 1, t_ms - 1]
        if new in d:
            d[new][1] = max(d[new][1], t_ms)
        else:
            d[new] = [t_ms, t_ms]

    def names_for_imo(self, imo):
        out = []
        for mmsi, m in self.mmsi.items():
            if m.get("imo") == imo:
                out += [{"name": n, "first_seen": v[0], "last_seen": v[1]} for n, v in self.names.get(mmsi, {}).items()]
        return sorted(out, key=lambda r: r["first_seen"])

    def sanctions_status(self):
        lists: dict[str, int] = {}
        for rows in self.sanctions.values():
            for r in rows:
                lists[r.get("list", "?")] = lists.get(r.get("list", "?"), 0) + 1
        return {"rows": sum(len(v) for v in self.sanctions.values()), "refreshed": None, "lists": lists}

    def add_alert(self, imo, rule, t0_ms, severity, title, detail):
        key = (imo, rule, t0_ms // 3_600_000)
        if key in self.alerts:
            return False
        self.alerts[key] = {"imo": imo, "rule": rule, "t0": t0_ms, "severity": severity, "title": title, "detail": detail, "created_at": int(__import__("time").time() * 1000)}
        return True

    def list_alerts(self, since_ms, limit=200):
        return sorted((a for a in self.alerts.values() if a["created_at"] >= since_ms), key=lambda a: -a["created_at"])[:limit]

    def add_push_subscription(self, user, sub, user_agent):
        self.subs[sub["endpoint"]] = {"user_id": self.user_id(user), "sub": sub, "user_agent": user_agent}

    def remove_push_subscription(self, endpoint):
        self.subs.pop(endpoint, None)

    def list_push_subscriptions(self, users=None):
        out = []
        for v in self.subs.values():
            u = self.users.get(v["user_id"])
            if u and (users is None or u["email"] in users):
                out.append({"user": u["email"], "sub": v["sub"], "user_agent": v.get("user_agent")})
        return out


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
            rows = c.execute("SELECT list_name, programme, listed_at, refreshed_at FROM sanctions WHERE imo=%s AND delisted_at IS NULL", (imo,)).fetchall()
        # a listing with no date still counts: it falls back to when the list was downloaded
        return [{"list": r[0], "programme": r[1] or "",
                 "t": int(datetime(r[2].year, r[2].month, r[2].day, tzinfo=timezone.utc).timestamp() * 1000) if r[2] else self._ms(r[3])} for r in rows]

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
        """Latest fix per ship in the box over the last 6 hours, with its static data — one query for a whole region."""
        with self._conn() as c:
            rows = c.execute("""SELECT DISTINCT ON (a.mmsi) a.mmsi, a.ts, a.lat, a.lon, a.sog, a.cog, a.heading, a.nav, a.draught, COALESCE(a.imo, m.imo),
                                       m.name, m.callsign, m.type_code, m.destination, m.eta, m.draught, m.dim_a, m.dim_b, m.dim_c, m.dim_d
                                FROM ais_live a LEFT JOIN mmsi_map m ON m.mmsi = a.mmsi
                                WHERE a.ts > now() - interval '6 hours' AND a.lon BETWEEN %s AND %s AND a.lat BETWEEN %s AND %s
                                ORDER BY a.mmsi, a.ts DESC""", (bbox[0], bbox[2], bbox[1], bbox[3])).fetchall()
        return [{**self._live_row(r[:10]), "name": r[10], "callsign": r[11], "type_code": r[12], "destination": r[13],
                 "eta": int(r[14].timestamp() * 1000) if r[14] else None, "static_draught": r[15], "dim": [r[16], r[17], r[18], r[19]]} for r in rows]

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

    LIVE_SEARCH_SQL = """SELECT m.mmsi, m.imo, m.name, m.callsign, m.type_code, m.destination, m.draught,
            (SELECT n.name FROM mmsi_names n WHERE n.mmsi = m.mmsi AND upper(n.name) LIKE %s AND n.name IS DISTINCT FROM m.name ORDER BY n.last_seen DESC LIMIT 1)
        FROM mmsi_map m
        WHERE upper(m.name) LIKE %s OR CAST(m.imo AS TEXT) LIKE %s OR CAST(m.mmsi AS TEXT) LIKE %s
           OR m.mmsi IN (SELECT n2.mmsi FROM mmsi_names n2 WHERE upper(n2.name) LIKE %s)
        LIMIT 24"""

    def live_search(self, q):
        qu = q.upper()
        like = f"%{qu}%"
        with self._conn() as c:
            rows = c.execute(self.LIVE_SEARCH_SQL, (like, like, f"{qu}%", f"{qu}%", like)).fetchall()
        return [{"mmsi": r[0], "imo": r[1], "name": r[2], "callsign": r[3], "type_code": r[4], "destination": r[5], "draught": r[6],
                 "former": r[7] if r[7] and qu not in (r[2] or "").upper() else None} for r in rows]

    def name_seen(self, mmsi, old, new, t_ms):
        with self._conn() as c:
            with c.cursor() as cur:
                if old and old != new:
                    cur.execute("INSERT INTO mmsi_names (mmsi, name, first_seen, last_seen) VALUES (%s, %s, %s, %s) ON CONFLICT (mmsi, name) DO NOTHING",
                                (mmsi, old, self._ts(t_ms - 1), self._ts(t_ms - 1)))
                cur.execute("INSERT INTO mmsi_names (mmsi, name, first_seen, last_seen) VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (mmsi, name) DO UPDATE SET last_seen = GREATEST(mmsi_names.last_seen, EXCLUDED.last_seen)",
                            (mmsi, new, self._ts(t_ms), self._ts(t_ms)))
            c.commit()

    def names_for_imo(self, imo):
        with self._conn() as c:
            rows = c.execute("SELECT n.name, min(n.first_seen), max(n.last_seen) FROM mmsi_names n JOIN mmsi_map m ON m.mmsi = n.mmsi "
                             "WHERE m.imo = %s GROUP BY n.name ORDER BY min(n.first_seen)", (imo,)).fetchall()
        return [{"name": r[0], "first_seen": self._ms(r[1]), "last_seen": self._ms(r[2])} for r in rows]

    def sanctions_status(self):
        with self._conn() as c:
            n, t = c.execute("SELECT count(*), max(refreshed_at) FROM sanctions WHERE delisted_at IS NULL").fetchone()
            per = c.execute("SELECT list_name, count(*) FROM sanctions WHERE delisted_at IS NULL GROUP BY list_name").fetchall()
        return {"rows": int(n or 0), "refreshed": self._ms(t), "lists": {r[0]: int(r[1]) for r in per}}

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

    def get_alerts_seen(self, user):
        uid = self.user_id(user)
        with self._conn() as c:
            row = c.execute("SELECT seen_until FROM alert_seen WHERE user_id=%s", (uid,)).fetchone()
        return self._ms(row[0]) if row else 0

    def set_alerts_seen(self, user, t_ms):
        uid = self.user_id(user)
        with self._conn() as c:
            c.execute("INSERT INTO alert_seen (user_id, seen_until) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET seen_until=EXCLUDED.seen_until", (uid, self._ts(t_ms)))
            c.commit()

    # ---- accounts (migration 005)
    @staticmethod
    def _ms(dt) -> Optional[int]:
        return int(dt.timestamp() * 1000) if dt is not None else None

    USER_COLS = "id, email, name, role, password_hash, status, prefs, created_at, updated_at, last_login_at, last_seen_at"

    def _user_row(self, r):
        if not r:
            return None
        return {"id": r[0], "email": r[1], "name": r[2], "role": r[3] or "analyst", "password_hash": r[4], "status": r[5] or "active", "prefs": r[6] or {},
                "created_at": self._ms(r[7]), "updated_at": self._ms(r[8]), "last_login_at": self._ms(r[9]), "last_seen_at": self._ms(r[10])}

    def count_users(self):
        with self._conn() as c:
            return int(c.execute("SELECT count(*) FROM users WHERE password_hash IS NOT NULL").fetchone()[0])

    def get_user(self, user_id):
        with self._conn() as c:
            return self._user_row(c.execute(f"SELECT {self.USER_COLS} FROM users WHERE id=%s", (user_id,)).fetchone())

    def get_user_by_email(self, email):
        with self._conn() as c:
            return self._user_row(c.execute(f"SELECT {self.USER_COLS} FROM users WHERE email=%s AND password_hash IS NOT NULL", ((email or "").lower(),)).fetchone())

    def create_user(self, email, name, role, password_hash):
        with self._conn() as c:
            row = c.execute("INSERT INTO users (email, name, role, password_hash, status) VALUES (%s, %s, %s, %s, 'active') "
                            "ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name, role=EXCLUDED.role, password_hash=EXCLUDED.password_hash, status='active', updated_at=now() "
                            "WHERE users.password_hash IS NULL RETURNING id", (email.lower(), name, role, password_hash)).fetchone()
            c.commit()
        if not row:
            raise ValueError("email exists")
        return row[0]

    def adopt_user(self, legacy_email, email, name, role, password_hash):
        with self._conn() as c:
            row = c.execute("UPDATE users SET email=%s, name=%s, role=%s, password_hash=%s, status='active', updated_at=now() "
                            "WHERE email=%s AND password_hash IS NULL AND NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.email=%s) RETURNING id",
                            (email.lower(), name, role, password_hash, legacy_email.lower(), email.lower())).fetchone()
            c.commit()
        return row[0] if row else None

    USER_FIELDS = {"name", "email", "role", "status", "password_hash", "prefs", "last_login_at", "last_seen_at"}

    def update_user(self, user_id, **fields):
        sets, vals = [], []
        for k, v in fields.items():
            if k not in self.USER_FIELDS:
                raise ValueError(f"unknown user field {k}")
            if k == "prefs":
                sets.append("prefs=%s::jsonb")
                vals.append(json.dumps(v or {}))
            elif k in ("last_login_at", "last_seen_at"):
                sets.append(f"{k}=%s")
                vals.append(self._ts(v) if v else None)
            else:
                sets.append(f"{k}=%s")
                vals.append(v.lower() if k == "email" else v)
        if not sets:
            return
        with self._conn() as c:
            c.execute(f"UPDATE users SET {', '.join(sets)}, updated_at=now() WHERE id=%s", (*vals, user_id))
            c.commit()

    def delete_user(self, user_id):
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM watchlist WHERE user_id=%s", (user_id,))
                cur.execute("DELETE FROM notes WHERE user_id=%s", (user_id,))
                cur.execute("DELETE FROM push_subscriptions WHERE user_id=%s", (user_id,))
                cur.execute("DELETE FROM alert_seen WHERE user_id=%s", (user_id,))
                cur.execute("UPDATE reports SET user_id=NULL WHERE user_id=%s", (user_id,))
                cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
            c.commit()

    def list_users(self):
        with self._conn() as c:
            rows = c.execute(f"SELECT {self.USER_COLS} FROM users ORDER BY created_at").fetchall()
        return [self._user_row(r) for r in rows]

    SESSION_COLS = "id, user_id, token_hash, user_agent, ip, created_at, last_seen_at, expires_at"

    def _session_row(self, r):
        if not r:
            return None
        return {"id": r[0], "user_id": r[1], "token_hash": r[2], "user_agent": r[3], "ip": r[4], "created_at": self._ms(r[5]),
                "last_seen_at": self._ms(r[6]), "expires_at": self._ms(r[7])}

    def create_session(self, user_id, token_hash, user_agent, ip, expires_ms):
        with self._conn() as c:
            row = c.execute("INSERT INTO sessions (user_id, token_hash, user_agent, ip, expires_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                            (user_id, token_hash, user_agent, ip, self._ts(expires_ms))).fetchone()
            c.commit()
        return row[0]

    def get_session(self, token_hash):
        with self._conn() as c:
            return self._session_row(c.execute(f"SELECT {self.SESSION_COLS} FROM sessions WHERE token_hash=%s", (token_hash,)).fetchone())

    def touch_session(self, session_id, seen_ms, expires_ms):
        with self._conn() as c:
            c.execute("UPDATE sessions SET last_seen_at=%s, expires_at=%s WHERE id=%s", (self._ts(seen_ms), self._ts(expires_ms), session_id))
            c.commit()

    def delete_session(self, session_id):
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
            c.commit()

    def delete_user_sessions(self, user_id, except_id=None):
        with self._conn() as c:
            n = c.execute("DELETE FROM sessions WHERE user_id=%s AND id <> %s", (user_id, except_id or 0)).rowcount
            c.commit()
        return n

    def list_sessions(self, user_id):
        with self._conn() as c:
            rows = c.execute(f"SELECT {self.SESSION_COLS} FROM sessions WHERE user_id=%s AND expires_at > now() ORDER BY last_seen_at DESC", (user_id,)).fetchall()
        return [self._session_row(r) for r in rows]

    INVITE_COLS = "id, code_hash, email, role, created_by, created_at, expires_at, used_at, used_by"

    def _invite_row(self, r):
        if not r:
            return None
        return {"id": r[0], "code_hash": r[1], "email": r[2], "role": r[3], "created_by": r[4], "created_at": self._ms(r[5]), "expires_at": self._ms(r[6]),
                "used_at": self._ms(r[7]), "used_by": r[8]}

    def create_invite(self, code_hash, email, role, created_by, expires_ms):
        with self._conn() as c:
            row = c.execute("INSERT INTO invites (code_hash, email, role, created_by, expires_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                            (code_hash, email, role, created_by, self._ts(expires_ms))).fetchone()
            c.commit()
        return row[0]

    def get_invite(self, code_hash):
        with self._conn() as c:
            return self._invite_row(c.execute(f"SELECT {self.INVITE_COLS} FROM invites WHERE code_hash=%s", (code_hash,)).fetchone())

    def use_invite(self, invite_id, user_id):
        with self._conn() as c:
            c.execute("UPDATE invites SET used_at=now(), used_by=%s WHERE id=%s", (user_id, invite_id))
            c.commit()

    def list_invites(self):
        with self._conn() as c:
            rows = c.execute(f"SELECT {self.INVITE_COLS} FROM invites ORDER BY created_at DESC LIMIT 200").fetchall()
        return [self._invite_row(r) for r in rows]

    def delete_invite(self, invite_id):
        with self._conn() as c:
            c.execute("DELETE FROM invites WHERE id=%s", (invite_id,))
            c.commit()

    RESET_COLS = "id, user_id, code_hash, token_hash, created_by, created_at, expires_at, attempts, used_at"

    def _reset_row(self, r):
        if not r:
            return None
        return {"id": r[0], "user_id": r[1], "code_hash": r[2], "token_hash": r[3], "created_by": r[4], "created_at": self._ms(r[5]),
                "expires_at": self._ms(r[6]), "attempts": r[7] or 0, "used_at": self._ms(r[8])}

    def create_reset(self, user_id, code_hash, token_hash, expires_ms, created_by):
        with self._conn() as c:
            row = c.execute("INSERT INTO password_resets (user_id, code_hash, token_hash, expires_at, created_by) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                            (user_id, code_hash, token_hash, self._ts(expires_ms), created_by)).fetchone()
            c.commit()
        return row[0]

    def get_reset_by_token(self, token_hash):
        with self._conn() as c:
            return self._reset_row(c.execute(f"SELECT {self.RESET_COLS} FROM password_resets WHERE token_hash=%s", (token_hash,)).fetchone())

    def get_active_reset(self, user_id):
        with self._conn() as c:
            return self._reset_row(c.execute(f"SELECT {self.RESET_COLS} FROM password_resets WHERE user_id=%s AND code_hash IS NOT NULL AND used_at IS NULL "
                                             "ORDER BY id DESC LIMIT 1", (user_id,)).fetchone())

    def bump_reset_attempts(self, reset_id):
        with self._conn() as c:
            c.execute("UPDATE password_resets SET attempts = attempts + 1 WHERE id=%s", (reset_id,))
            c.commit()

    def mark_reset_used(self, reset_id):
        with self._conn() as c:
            c.execute("UPDATE password_resets SET used_at=now() WHERE id=%s", (reset_id,))
            c.commit()

    # ---- team notes
    NOTE_SQL = ("SELECT n.id, n.imo, n.scope, n.user_id, n.text, n.created_at, n.updated_at, u.name, u.email "
                "FROM vessel_notes n LEFT JOIN users u ON u.id = n.user_id")

    def _note_row(self, r):
        return {"id": r[0], "imo": r[1], "scope": r[2], "user_id": r[3], "text": r[4], "created_at": self._ms(r[5]), "updated_at": self._ms(r[6]),
                "author": r[7] or ((r[8] or "").split("@")[0] or None), "author_email": r[8]}

    def list_vessel_notes(self, imo):
        with self._conn() as c:
            rows = c.execute(self.NOTE_SQL + " WHERE n.imo=%s ORDER BY n.created_at", (imo,)).fetchall()
        return [self._note_row(r) for r in rows]

    def get_vessel_note(self, note_id):
        with self._conn() as c:
            r = c.execute(self.NOTE_SQL + " WHERE n.id=%s", (note_id,)).fetchone()
        return self._note_row(r) if r else None

    def add_vessel_note(self, imo, scope, user, text):
        uid = self.user_id(user)
        with self._conn() as c:
            row = c.execute("INSERT INTO vessel_notes (imo, scope, user_id, text) VALUES (%s, %s, %s, %s) RETURNING id", (imo, scope, uid, text)).fetchone()
            c.commit()
        return row[0]

    def update_vessel_note(self, note_id, text):
        with self._conn() as c:
            c.execute("UPDATE vessel_notes SET text=%s, updated_at=now() WHERE id=%s", (text, note_id))
            c.commit()

    def delete_vessel_note(self, note_id):
        with self._conn() as c:
            c.execute("DELETE FROM vessel_notes WHERE id=%s", (note_id,))
            c.commit()

    # ---- risk summary (vessel_risk) and sanctions membership
    def save_risk(self, imo, row):
        with self._conn() as c:
            c.execute("""INSERT INTO vessel_risk (imo, name, level, high, medium, info, headline, sentence, sanctioned, history_days, engine, analysed_at)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                         ON CONFLICT (imo) DO UPDATE SET name=EXCLUDED.name, level=EXCLUDED.level, high=EXCLUDED.high, medium=EXCLUDED.medium, info=EXCLUDED.info,
                           headline=EXCLUDED.headline, sentence=EXCLUDED.sentence, sanctioned=EXCLUDED.sanctioned, history_days=EXCLUDED.history_days,
                           engine=EXCLUDED.engine, analysed_at=now()""",
                      (imo, row.get("name"), row.get("level") or "clear", int(row.get("high") or 0), int(row.get("medium") or 0), int(row.get("info") or 0),
                       row.get("headline"), row.get("sentence"), bool(row.get("sanctioned")), row.get("history_days"), row.get("engine")))
            c.commit()

    def get_risk(self, imos):
        if not imos:
            return {}
        with self._conn() as c:
            rows = c.execute("SELECT imo, name, level, high, medium, info, headline, sentence, sanctioned, history_days, analysed_at, engine FROM vessel_risk "
                             "WHERE imo = ANY(%s)", (list(imos),)).fetchall()
        return {r[0]: {"imo": r[0], "name": r[1], "level": r[2], "high": r[3], "medium": r[4], "info": r[5], "headline": r[6], "sentence": r[7],
                       "sanctioned": r[8], "history_days": r[9], "analysed_at": self._ms(r[10]), "engine": r[11]} for r in rows}

    def sanctioned(self, imos):
        if not imos:
            return set()
        with self._conn() as c:
            rows = c.execute("SELECT DISTINCT imo FROM sanctions WHERE imo = ANY(%s) AND delisted_at IS NULL", (list(imos),)).fetchall()
        return {r[0] for r in rows}


def make_store() -> Store:
    return PostgresStore() if os.environ.get("DATABASE_URL") else MemoryStore()
