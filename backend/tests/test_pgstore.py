"""PostgresStore against a real PostGIS — runs only when DATABASE_URL points at a database with the
migrations applied (CI's postgis service, or `docker compose up db`). Skipped otherwise, so the
default `pytest -q` / `python -m tests.run` stays dependency-free. Exercises every SQL statement the
free data path added (ais_live, mmsi_map, coverage_cells) plus the paid cache and the alert dedup."""
from __future__ import annotations

import os
import time

from app.engine.types import Position

DSN = os.environ.get("DATABASE_URL", "")


def test_postgres_store_roundtrip():
    if not DSN:
        try:
            import pytest  # type: ignore
            pytest.skip("DATABASE_URL not set")
        except ImportError:
            return
    from app.store import PostgresStore
    st = PostgresStore(DSN)
    now = int(time.time() * 1000)
    imo, mmsi = 9900001, 271099001
    with st._conn() as c:   # clean slate for this IMO so the test is repeatable
        for sql in ("DELETE FROM ais_live WHERE mmsi IN (%s, %s)", "DELETE FROM mmsi_map WHERE mmsi IN (%s, %s)"):
            c.execute(sql, (mmsi, mmsi + 1))
        c.execute("DELETE FROM positions WHERE imo=%s", (imo,))
        c.execute("DELETE FROM fetch_log WHERE imo=%s", (imo,))
        c.execute("DELETE FROM alerts WHERE imo=%s", (imo,))
        c.commit()

    # ---- paid cache
    pts = [Position(t=now - 3_600_000 + i * 600_000, lat=41.0 + i * 0.01, lon=29.0 + i * 0.01, sog=10.0, cog=45.0, draught=9.5) for i in range(6)]
    st.put_positions(imo, pts, "test", now - 3_600_000, now, credits=0)
    assert st.covered(imo, now - 3_600_000, now) and not st.covered(imo, now - 48 * 3_600_000, now)
    assert len(st.get_positions(imo, now - 3_600_000, now)) == 6 and st.latest_window_end(imo) >= now - 1000

    # ---- live feed tables
    st.mmsi_upsert({"mmsi": mmsi, "imo": None, "name": "PG TEST SHIP", "callsign": "PGT1", "type_code": 80, "destination": "NOVOROSSIYSK", "eta": now + 86_400_000, "draught": 11.2, "dim": [150, 30, 14, 18]})
    st.mmsi_upsert({"mmsi": mmsi, "imo": imo})                         # COALESCE keeps the name, adds the IMO
    rows = [{"mmsi": mmsi, "t": now - 1_800_000 + i * 120_000, "lat": 41.0 + i * 0.001, "lon": 29.0 + i * 0.001, "sog": 10.0, "cog": 45.0, "heading": 44.0, "nav": 0, "draught": 11.2, "imo": None} for i in range(10)]
    st.live_put(rows)
    st.live_put(rows[:3])                                                 # ON CONFLICT DO NOTHING
    st.live_backfill_imo(mmsi, imo)
    tr = st.live_track(imo, now - 3_600_000, now)
    assert len(tr) == 10 and tr[0]["imo"] == imo and abs(tr[0]["draught"] - 11.2) < 1e-4 and tr[-1]["t"] > tr[0]["t"]   # REAL column
    assert st.live_last(imo)["t"] == rows[-1]["t"]
    latest = st.live_latest((28.0, 40.0, 30.0, 42.0))
    me = [r for r in latest if r["mmsi"] == mmsi]
    assert len(me) == 1 and me[0]["name"] == "PG TEST SHIP" and me[0]["imo"] == imo
    near = st.live_near(41.0, 29.0, 500, now - 3_600_000, now)
    assert any(n["mmsi"] == mmsi and n["imo"] == imo for n in near)
    assert any(r["imo"] == imo for r in st.live_search("pg test"))
    m = st.mmsi_by_imo(imo)
    assert len(m) == 1 and m[0]["callsign"] == "PGT1" and m[0]["dim"] == [150.0, 30.0, 14.0, 18.0] and m[0]["eta"] is not None
    assert any(r["mmsi"] == mmsi for r in st.mmsi_all())

    # ---- coverage cells and tiered retention
    day = now // 86_400_000 * 86_400
    st.coverage_add([(58, 82, day, 5), (58, 82, day, 7), (-1, -1, day - 40 * 86_400, 3)])
    cov = st.live_coverage(days=30)
    assert cov.get((58, 82), 0) >= 12 and (-1, -1) not in cov
    old = [{"mmsi": mmsi + 1, "t": now - 60 * 86_400_000 + i * 120_000, "lat": 20.0, "lon": 57.0, "sog": 8.0, "cog": 0.0, "heading": None, "nav": 0, "draught": None, "imo": None} for i in range(30)]
    old.append({"mmsi": mmsi + 1, "t": now - 500 * 86_400_000, "lat": 20.0, "lon": 57.0, "sog": 0.0, "cog": 0.0, "heading": None, "nav": 1, "draught": None, "imo": None})
    st.live_put(old)
    r = st.live_prune(full_res_days=30, thin_minutes=15, retention_months=14, window_days=None)
    assert r["deleted"] >= 1 and r["thinned"] >= 25
    with st._conn() as c:
        left = c.execute("SELECT count(*) FROM ais_live WHERE mmsi=%s", (mmsi + 1,)).fetchone()[0]
    assert 4 <= left <= 5
    s = st.live_stats()
    assert s["newest"] is not None and s["mmsi"] >= 1 and s["with_imo"] >= 1

    # ---- alerts dedup by hour
    assert st.add_alert(imo, "AIS gap", now, "high", "t", "d") is True
    assert st.add_alert(imo, "AIS gap", now + 1000, "high", "t", "d") is False
    assert any(a["imo"] == imo for a in st.list_alerts(now - 60_000))


def test_postgres_store_static():
    """Runs everywhere, no database: every `self.X` that PostgresStore uses exists, and every SQL statement gets
    exactly as many parameters as it has %s placeholders. (A refactor once deleted LIVE_NEAR_SQL; only the
    server's PostGIS test noticed. This catches that class of mistake on any machine.)"""
    import ast
    import inspect
    import textwrap
    from app.store import PostgresStore
    tree = ast.parse(textwrap.dedent(inspect.getsource(PostgresStore)))
    cls = tree.body[0]
    defined = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    defined |= {t.id for n in cls.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    defined |= {n.attr for n in ast.walk(cls) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                and isinstance(n.value, ast.Name) and n.value.id == "self"}
    used = {n.attr for n in ast.walk(cls) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load)
            and isinstance(n.value, ast.Name) and n.value.id == "self"}
    assert used <= defined, f"PostgresStore uses undefined attributes: {sorted(used - defined)}"

    consts = {t.id: n.value.value for n in cls.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
              for t in n.targets if isinstance(t, ast.Name)}
    checked = 0
    for call in (n for n in ast.walk(cls) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("execute", "executemany") and len(n.args) >= 2):
        sql_node, params = call.args[0], call.args[1]
        if isinstance(sql_node, ast.Constant) and isinstance(sql_node.value, str):
            sql = sql_node.value
        elif isinstance(sql_node, ast.Attribute) and sql_node.attr in consts:
            sql = consts[sql_node.attr]
        else:
            continue                                   # f-strings with optional clauses are checked by the PostGIS test
        if isinstance(params, ast.ListComp):
            params = params.elt
        if isinstance(params, (ast.Tuple, ast.List)):
            assert sql.count("%s") == len(params.elts), f"line {call.lineno}: {sql.count('%s')} placeholders, {len(params.elts)} parameters"
            checked += 1
    assert checked >= 15


def test_postgres_accounts_roundtrip():
    """Accounts, sessions, invites, resets, team notes, risk rows and former names against the real schema
    (migration 005). Unique emails, cleaned up afterwards, so it can run on any scratch database."""
    if not DSN:
        try:
            import pytest  # type: ignore
            pytest.skip("DATABASE_URL not set")
        except ImportError:
            return
    from app import accounts as acc
    from app.store import PostgresStore
    st = PostgresStore(DSN)
    tag = str(int(time.time() * 1000))[-8:]
    owner_email, ana_email = f"owner{tag}@example.com", f"ana{tag}@example.com"

    class Mail:
        sent: list = []

        def configured(self):
            return True

        def send(self, to, subject, text, html=None):
            self.sent.append((to, text))

    acc.LIMITS.reset()
    a = acc.Accounts(st, Mail())
    uid = st.create_user(owner_email, "Owner", "admin", acc.hash_password("owner-pass-phrase-1"))
    try:
        s = a.login(owner_email, "owner-pass-phrase-1", ua="iPhone Safari", ip="10.0.0.1")
        assert a.session_user(s.token)[0]["email"] == owner_email
        inv = a.create_invite(s.user, email=ana_email, role="analyst", base_url="https://x")
        assert a.invite_info(inv["code"])["valid"] and inv["emailed"]
        ana = a.signup("Ana Silva", ana_email, "another-long-pass", invite=inv["code"], ua="Mac Chrome")
        assert ana.user["role"] == "analyst" and not a.invite_info(inv["code"])["valid"]
        a.forgot(ana_email, "https://x")
        code = [w for w in Mail.sent[-1][1].replace(".", " ").split() if w.isdigit() and len(w) == 6][0]
        s2 = a.reset("brand-new-pass-77", email=ana_email, code=code)
        assert a.session_user(ana.token) is None and a.session_user(s2.token)[0]["email"] == ana_email
        link = a.admin_reset_link(s.user, s2.user["id"], "https://x")
        assert a.reset_info(link["link"].split("/reset/")[1])["valid"]
        u = a.update_profile(s.user, name="Owner Two", prefs={"theme": "dark", "pushMin": "medium"})
        assert u["name"] == "Owner Two" and u["prefs"]["pushMin"] == "medium"
        assert a.set_member(u, s2.user["id"], role="admin")["role"] == "admin"
        nid = st.add_vessel_note(9900002, "voyage:3", owner_email, "first")
        st.update_vessel_note(nid, "edited")
        n = st.get_vessel_note(nid)
        assert n["text"] == "edited" and n["scope"] == "voyage:3" and n["author"] == "Owner Two"
        st.delete_vessel_note(nid)
        assert st.get_vessel_note(nid) is None
        st.save_risk(9900002, {"name": "TEST", "level": "high", "high": 2, "medium": 0, "info": 1, "headline": "h", "sentence": "s", "sanctioned": False, "history_days": 300.0,
                               "engine": "test-1"})
        assert st.get_risk([9900002])[9900002]["level"] == "high" and st.get_risk([9900002])[9900002]["engine"] == "test-1"
        st.set_alerts_seen(owner_email, int(time.time() * 1000))
        assert st.get_alerts_seen(owner_email) > 0
        a.remove_member(u, s2.user["id"])
        assert ana_email not in [x["email"] for x in a.team()["users"]]
        status = st.sanctions_status()
        assert "lists" in status and isinstance(status["lists"], dict)
    finally:
        with st._conn() as c:
            c.execute("DELETE FROM vessel_risk WHERE imo=%s", (9900002,))
            c.commit()
        for e in (owner_email, ana_email):
            row = st.get_user_by_email(e)
            if row:
                st.delete_user_sessions(row["id"])
                st.delete_user(row["id"])
        del uid
