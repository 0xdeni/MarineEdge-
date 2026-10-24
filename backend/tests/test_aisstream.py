"""Free AIS path: aisstream message parsing, the in-memory live store, the recorder loop's bookkeeping,
the OwnAISProvider adapter and the coverage-aware AIS-gap severity. No network anywhere."""
from __future__ import annotations

from pathlib import Path

from app.engine import analyze, load_refdata, load_rules
from app.engine.types import H
from app.providers import make_provider
from app.providers.aisstream import OwnAISProvider, cell_of, parse_message, type_category
from app.providers.gfw import normalise_event
from app.recorder import Recorder
from app.store import MemoryStore
from tests.synth import Track
from tests.test_engine import NOW, P, T0, vessel

CONFIG = Path(__file__).resolve().parents[2] / "config"
REF = load_refdata(CONFIG)
RULES = load_rules(CONFIG / "rules.yaml")

POS = {"MessageType": "PositionReport", "MetaData": {"MMSI": 271044144, "ShipName": "BOSPHORUS QUEEN ", "latitude": 41.02, "longitude": 28.99, "time_utc": "2026-10-20 11:46:52.509865357 +0000 UTC"},
       "Message": {"PositionReport": {"UserID": 271044144, "Latitude": 41.0201, "Longitude": 28.9912, "Sog": 11.4, "Cog": 212.5, "TrueHeading": 210, "NavigationalStatus": 0}}}
STATIC = {"MessageType": "ShipStaticData", "MetaData": {"MMSI": 271044144, "ShipName": "BOSPHORUS QUEEN", "time_utc": "2026-10-20 11:50:00 +0000 UTC"},
          "Message": {"ShipStaticData": {"UserID": 271044144, "ImoNumber": 9100001, "Name": "BOSPHORUS QUEEN", "CallSign": "TCAB2", "Type": 80, "Destination": "NOVOROSSIYSK",
                                         "Eta": {"Month": 10, "Day": 24, "Hour": 6, "Minute": 30}, "MaximumStaticDraught": 11.2, "Dimension": {"A": 150, "B": 30, "C": 14, "D": 18}}}}
T_POS = 1_792_496_812_000   # 2026-10-20 11:46:52Z


def test_parse_position_report():
    kind, row = parse_message(POS)
    assert kind == "pos"
    assert row["mmsi"] == 271044144 and row["t"] == T_POS
    assert abs(row["lat"] - 41.0201) < 1e-9 and abs(row["lon"] - 28.9912) < 1e-9
    assert row["sog"] == 11.4 and row["heading"] == 210 and row["nav"] == 0 and row["name"] == "BOSPHORUS QUEEN"
    # heading 511 = not available; bad coordinates and missing MMSI are dropped
    _k2, r2 = parse_message({**POS, "Message": {"PositionReport": {**POS["Message"]["PositionReport"], "TrueHeading": 511}}})
    assert r2["heading"] is None
    assert parse_message({**POS, "Message": {"PositionReport": {"Latitude": 91, "Longitude": 0}}}) is None
    assert parse_message({"MessageType": "PositionReport", "MetaData": {}, "Message": {"PositionReport": {}}}) is None
    assert parse_message({"MessageType": "AidsToNavigationReport", "MetaData": {"MMSI": 1}, "Message": {}}) is None


def test_parse_static_data():
    kind, row = parse_message(STATIC)
    assert kind == "static"
    assert row["imo"] == 9100001 and row["callsign"] == "TCAB2" and row["type_code"] == 80 and row["destination"] == "NOVOROSSIYSK"
    assert row["draught"] == 11.2 and row["dim"] == [150.0, 30.0, 14.0, 18.0]
    assert row["eta"] is not None and row["eta"] % 60_000 == 0
    assert type_category(80) == "tanker" and type_category(70) == "bulk" and type_category(30) == "other" and type_category(None) == "other"
    # an IMO outside the 7-digit range is noise, not an identity
    _, r2 = parse_message({**STATIC, "Message": {"ShipStaticData": {**STATIC["Message"]["ShipStaticData"], "ImoNumber": 0}}})
    assert r2["imo"] is None


def test_memory_store_live_roundtrip():
    st = MemoryStore()
    st.mmsi_upsert({"mmsi": 271044144, "imo": 9100001, "name": "BOSPHORUS QUEEN", "type_code": 80, "draught": 11.2, "updated_at": T_POS})
    st.mmsi_upsert({"mmsi": 636019999, "imo": None, "name": "NO IMO YET", "updated_at": T_POS})
    rows = [{"mmsi": 271044144, "t": T_POS + i * 600_000, "lat": 41.0 + i * 0.01, "lon": 29.0 + i * 0.01, "sog": 10.0, "cog": 45.0, "heading": 45.0, "nav": 0, "draught": 11.2, "imo": None} for i in range(6)]
    rows.append({"mmsi": 636019999, "t": T_POS, "lat": 41.5, "lon": 29.5, "sog": 0.0, "cog": 0.0, "heading": None, "nav": 1, "draught": None, "imo": None})
    st.live_put(rows)
    st.live_put(rows[:2])                                   # duplicates are idempotent
    st.live_backfill_imo(271044144, 9100001)
    tr = st.live_track(9100001, T_POS, T_POS + 3_600_000)
    assert [r["t"] for r in tr] == sorted(r["t"] for r in tr) and len(tr) == 6 and all(r["imo"] == 9100001 for r in tr)
    assert st.live_last(9100001)["t"] == T_POS + 5 * 600_000
    latest = st.live_latest((28.0, 40.0, 30.0, 42.0))
    assert {r["mmsi"] for r in latest} == {271044144, 636019999} and next(r for r in latest if r["mmsi"] == 271044144)["name"] == "BOSPHORUS QUEEN"
    near = st.live_near(41.0, 29.0, 3000, T_POS - 1, T_POS + 1)
    assert [n["mmsi"] for n in near] == [271044144]
    assert [m["imo"] for m in st.live_search("bosph")] == [9100001] and st.live_search("9100")[0]["mmsi"] == 271044144
    s = st.live_stats()
    assert s["positions"] == 7 and s["mmsi"] == 2 and s["with_imo"] == 1 and s["oldest"] == T_POS
    assert cell_of(29.0, 41.0) == (58, 82) and cell_of(-0.1, -0.1) == (-1, -1)
    assert st.mmsi_by_imo(9100001)[0]["mmsi"] == 271044144 and len(st.mmsi_all()) == 2


def test_recorder_bookkeeping_and_provider():
    st = MemoryStore()
    rec = Recorder(st, rules=RULES)
    rec.warm()
    rec.handle(STATIC)                                        # static first → map entry, draught known
    rec.handle(POS)
    rec.handle({**POS, "MetaData": {**POS["MetaData"], "time_utc": "2026-10-20 11:56:52 +0000 UTC"}})
    assert rec.counts["received"] == 2 and rec.counts["stored"] == 2 and rec.counts["static"] == 1 and len(rec.buf) == 2
    assert rec.buf[0]["imo"] == 9100001 and rec.buf[0]["draught"] == 11.2   # enriched from the static message
    rec.flush()
    assert rec.counts["written"] == 2 and not rec.buf
    assert st.live_coverage(days=36500)[cell_of(28.9912, 41.0201)] == 2       # both fixes counted in their cell

    pv = OwnAISProvider(st)
    assert pv.get_track(9100001, T_POS - 1, T_POS + H)[0].draught == 11.2
    v = pv.get_vessel(9100001)
    assert v is not None and v.type == "tanker" and v.flag == "Türkiye" and v.callsign == "TCAB2" and v.loa == 180 and v.beam == 32 and v.region == "A"
    assert pv.search_vessel("bosph")[0].imo == 9100001 and pv.search_vessel("zzz") == []
    st.mmsi_upsert({"mmsi": 636019999, "imo": 9100001, "name": "BOSPHORUS QUEEN", "updated_at": T_POS - 86_400_000})   # earlier MMSI, same hull
    v = pv.get_vessel(9100001)
    assert [h["field"] for h in v.history] == ["mmsi"] and v.history[0]["from"] == "636019999" and v.mmsi == "271044144"
    assert pv.get_static(9100001).destination == "NOVOROSSIYSK"
    assert pv.coverage(29.0, 41.0) >= 0 and pv.stats()["positions"] == 2
    area = pv.get_vessels_in_area((28.0, 40.0, 30.0, 42.0))
    assert len(area) == 1 and area[0][0].imo == 9100001

    # the factory wires the store in; the Service passes it automatically
    assert isinstance(make_provider("aisstream", store=st), OwnAISProvider)


def test_gap_outside_receiver_coverage_is_info():
    # same 9 h open-sea gap as test_ais_gap_medium_in_open_sea, now with a coverage function
    tr = Track(T0, P["SAM"].lat, P["SAM"].lon).moor(12).sail_to_port(P["BOJ"], gap=(0.5, 9)).moor(12)
    a = analyze(vessel(), tr.pts, REF, RULES, now=NOW, coverage=lambda lon, lat: 0)
    gaps = [f for f in a.flags if f.rule == "AIS gap"]
    assert len(gaps) == 1 and gaps[0].severity == "info" and "outside receiver coverage" in gaps[0].title
    assert any("Receiver coverage" in ln for ln in gaps[0].lines)
    a2 = analyze(vessel(), tr.pts, REF, RULES, now=NOW, coverage=lambda lon, lat: 5000)
    g2 = [f for f in a2.flags if f.rule == "AIS gap"]
    assert len(g2) == 1 and g2[0].severity == "medium"           # well-covered cell: the gap stands
    # a long gap stays a flag even with no coverage: beyond coverage_max_hours the benefit of the doubt ends
    tr3 = Track(T0, P["JEA"].lat, P["JEA"].lon, speed=5.0).moor(12).sail_to(25.9, 56.5).sail_to(24.0, 59.5).sail_to_port(P["SLL"], gap=(0.1, 80)).moor(12)
    a3 = analyze(vessel(region="B", speed=5.0), tr3.pts, REF, RULES, now=NOW, coverage=lambda lon, lat: 0)
    g3 = [f for f in a3.flags if f.rule == "AIS gap"]
    assert len(g3) == 1 and g3[0].severity == "high"


def test_gfw_event_normalisation():
    e = normalise_event({"type": "encounter", "start": "2026-03-04T05:00:00Z", "end": "2026-03-04T11:30:00Z", "position": {"lat": 25.1, "lon": 56.4},
                         "encounter": {"vessel": {"name": "OTHER ONE", "flag": "PAN"}, "medianDistanceKilometers": 0.21, "medianSpeedKnots": 0.4}})
    assert e["label"].startswith("Encounter") and e["t1"] - e["t0"] == 6.5 * H and "OTHER ONE" in e["detail"] and "0.21 km" in e["detail"]
    g = normalise_event({"type": "gap", "start": "2026-03-04T05:00:00Z", "end": None, "gap": {"distanceKm": 120.4, "durationHours": 30, "intentionalDisabling": True}})
    assert g["label"] == "AIS off" and g["t1"] is None and "likely intentional" in g["detail"]
    assert normalise_event({})["label"] == "event"


def _pos(mmsi, sec, sog, cog, nav=0, base=None):
    """A PositionReport `sec` seconds after 2026-10-20 11:46:52Z with the given speed, course and nav status."""
    from datetime import datetime, timedelta, timezone
    base = base or datetime(2026, 10, 20, 11, 46, 52, tzinfo=timezone.utc)
    p = {**POS["Message"]["PositionReport"], "UserID": mmsi, "Sog": sog, "Cog": cog, "NavigationalStatus": nav}
    return {**POS, "MetaData": {**POS["MetaData"], "MMSI": mmsi, "time_utc": (base + timedelta(seconds=sec)).strftime("%Y-%m-%d %H:%M:%S") + " +0000 UTC"},
            "Message": {"PositionReport": p}}


def test_recorder_volume_policy():
    """Significance sampling: one fix per 10 min under way and per 30 min stopped, plus turns and starts/stops,
    never closer than 60 s; anchor swing does not flap; non-cargo types dropped once known; coverage counts all."""
    from app.engine.rules_config import Rules
    st = MemoryStore()
    rec = Recorder(st, rules=Rules({"live": {"keep_types": ["70-89"]}}))       # every other threshold from the defaults
    assert rec.keeps(None) and rec.keeps(80) and rec.keeps(70) and not rec.keeps(30) and not rec.keeps(60)
    m = 271044144
    for sec in range(0, 1801, 10):                       # 30 min under way on a steady course, a report every 10 s
        rec.handle(_pos(m, sec, 12.0, 90.0))
    assert rec.counts["received"] == 181 and rec.counts["stored"] == 4          # 0, 600, 1200, 1800 s
    rec.handle(_pos(m, 1830, 12.0, 130.0))               # 40° turn, but only 30 s after the last stored fix
    assert rec.counts["stored"] == 4
    rec.handle(_pos(m, 1860, 12.0, 130.0))               # 60 s after: the turn is stored
    assert rec.counts["stored"] == 5
    rec.handle(_pos(m, 1900, 0.2, 130.0, nav=1))         # dropped anchor: too soon (40 s)...
    rec.handle(_pos(m, 1920, 0.2, 130.0, nav=1))         # ...60 s after the turn: the stop is stored
    assert rec.counts["stored"] == 6
    for k, sec in enumerate(range(2100, 2100 + 3600, 180)):   # an hour at anchor, swinging 0.2–1.4 kn, every 3 min
        rec.handle(_pos(m, sec, 0.2 + 0.6 * (k % 3), (k * 47) % 360, nav=1))
    assert rec.counts["stored"] == 8                      # one per 30 min: 3720 and 5520 s; the swing never reads as a departure
    rec.handle(_pos(m, 5760, 9.0, 300.0, nav=0))          # heaves anchor and leaves: state change, stored at once
    assert rec.counts["stored"] == 9
    stored = rec.counts["stored"]
    # a ferry (type 60) announces itself: from now on its positions are filtered, coverage still counted
    ferry_static = {**STATIC, "MetaData": {**STATIC["MetaData"], "MMSI": 271000001}, "Message": {"ShipStaticData": {**STATIC["Message"]["ShipStaticData"], "UserID": 271000001, "ImoNumber": 9200002, "Type": 60}}}
    rec.handle(ferry_static)
    rec.handle(_pos(271000001, 600, 15.0, 10.0))
    assert rec.counts["filtered"] == 1 and rec.counts["stored"] == stored
    received = rec.counts["received"]
    rec.flush()
    assert st.live_stats()["positions"] == stored
    assert sum(st.live_coverage(days=36500).values()) == received
    # unknown message types are counted, never raise
    rec.handle({"MessageType": "BaseStationReport", "MetaData": {"MMSI": 2}, "Message": {}})
    assert rec.counts["unparsed"] == 1


def test_recorder_disk_guard():
    """Below min_free_gb free, positions pause (counted), coverage continues; storing resumes when space is back."""
    st = MemoryStore()
    rec = Recorder(st, rules=RULES)
    rec.min_free_gb = 1e9                                 # no disk is that big: guard trips
    assert rec.check_disk() is True
    rec.handle(_pos(271044144, 0, 12.0, 90.0))
    assert rec.counts["paused_disk"] == 1 and rec.counts["stored"] == 0 and not rec.buf
    rec.flush()
    assert sum(st.live_coverage(days=36500).values()) == 1
    rec.min_free_gb = 0.0
    assert rec.check_disk() is False
    rec.handle(_pos(271044144, 700, 12.0, 90.0))
    assert rec.counts["stored"] == 1


def test_live_prune_tiers():
    import time as _t
    st = MemoryStore()
    now = int(_t.time() * 1000)
    day, minute = 86_400_000, 60_000
    rows = []
    old_start = (now - 60 * day) // (15 * minute) * (15 * minute)   # aligned to a 15-min bucket so the count is deterministic
    for i in range(30):                                        # 60 days old: 30 fixes 2 min apart over 58 min → 4 buckets kept
        rows.append({"mmsi": 1, "t": old_start + i * 2 * minute, "lat": 41.0, "lon": 29.0, "sog": 10.0, "cog": 0.0, "heading": None, "nav": 0, "draught": None, "imo": None})
    for i in range(10):                                        # yesterday: full resolution kept
        rows.append({"mmsi": 1, "t": now - day + i * 2 * minute, "lat": 41.0, "lon": 29.0, "sog": 10.0, "cog": 0.0, "heading": None, "nav": 0, "draught": None, "imo": None})
    rows.append({"mmsi": 1, "t": now - 500 * day, "lat": 41.0, "lon": 29.0, "sog": 0.0, "cog": 0.0, "heading": None, "nav": 1, "draught": None, "imo": None})   # beyond retention
    st.live_put(rows)
    r = st.live_prune(full_res_days=30, thin_minutes=15, retention_months=14)
    assert r["deleted"] == 1 and r["thinned"] == 26
    kept = sorted(st.live[1])
    assert len(kept) == 14 and len([t for t in kept if t < now - 30 * day]) == 4


def test_live_region_is_one_query_and_local_tracks_are_not_recached():
    """A region can hold thousands of ships: the listing must come from one joined query (no per-ship lookups).
    Recorded tracks are read straight from the live table — never copied into the paid-data cache."""
    from app.service import Service, stats_json
    st = MemoryStore()
    rec = Recorder(st, rules=RULES)
    rec.handle(STATIC); rec.handle(POS); rec.flush()
    pv = OwnAISProvider(st)
    lookups = []
    original = st.mmsi_by_imo
    st.mmsi_by_imo = lambda imo: (lookups.append(imo), original(imo))[1]
    area = pv.get_vessels_in_area((28.0, 40.0, 30.0, 42.0))
    assert len(area) == 1 and lookups == []
    v, p = area[0]
    assert v.imo == 9100001 and v.type == "tanker" and v.flag == "Türkiye" and v.loa == 180 and v.speed == 0 and p.t == T_POS
    assert pv.area_static[9100001].destination == "NOVOROSSIYSK"
    st.mmsi_by_imo = original
    svc = Service(provider=pv, store=st, ref=REF, rules=RULES, now_ms=T_POS + 3_600_000)
    assert len(svc.track(9100001)) == 1 and st.latest_window_end(9100001) is None
    region = svc.region((28.0, 40.0, 30.0, 42.0))
    assert region[0]["destination"] == "NOVOROSSIYSK" and region[0]["flags"] is None and region[0]["vessel"]["imo"] == 9100001
    assert stats_json({"port_calls": 3, "raw": 1, "history_since": 5}) == {"portCalls": 3, "raw": 1, "historySince": 5}
