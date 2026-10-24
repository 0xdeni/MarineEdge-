"""Service-level tests with the mock provider and the in-memory store: the cache rule (fetch once,
then only the tail), watchlist/notes state, and alert de-duplication."""
from __future__ import annotations

from app.engine import load_refdata, load_rules
from app.engine.types import D, H
from app.providers.mock import MockProvider
from app.service import Service
from app.store import MemoryStore, _chain_covers

CONFIG = __import__("pathlib").Path(__file__).resolve().parents[2] / "config"


def make_service(now_ms: int | None = None) -> Service:
    ref = load_refdata(CONFIG)
    prov = MockProvider(ref=ref, now_ms=now_ms)
    svc = Service(provider=prov, store=MemoryStore(), ref=ref, rules=load_rules(CONFIG / "rules.yaml"), now_ms=prov.now)
    return svc


def test_track_fetched_once_then_only_the_tail():
    svc = make_service()
    calls = []
    orig = svc.provider.get_track
    svc.provider.get_track = lambda imo, a, b: (calls.append((a, b)), orig(imo, a, b))[1]
    first = svc.track(9000036)
    assert len(calls) == 1 and len(first) > 1000
    year = svc.rules.history_months * 30.4 * D
    assert abs((calls[0][1] - calls[0][0]) - year) < D
    svc.track(9000036)                                          # same instant: fully covered, no call
    assert len(calls) == 1
    svc.now += 2 * D                                            # two days later: buy the tail only
    svc.provider.now += 2 * D
    svc.track(9000036)
    assert len(calls) == 2
    a, b = calls[1]
    assert (b - a) <= 2 * D + 2 * H and (b - a) >= 2 * D - H
    svc.now += 10 * 60_000                                      # ten minutes later: nothing worth buying
    svc.track(9000036)
    assert len(calls) == 2


def test_chain_coverage():
    s, e = 0, 100 * H
    assert _chain_covers([(0, 100 * H)], s, e)
    assert _chain_covers([(0, 60 * H), (59 * H, 100 * H)], s, e)          # overlapping chain
    assert not _chain_covers([(0, 60 * H), (70 * H, 100 * H)], s, e)      # hole of 10 h
    assert _chain_covers([(0, 95 * H)], s, e)                             # within 6 h slack
    assert not _chain_covers([(10 * H, 100 * H)], s, e)                   # starts late


def test_watchlist_and_notes_state():
    st = MemoryStore()
    st.set_watchlist("deni", [9000036, 9000014, 9000036])
    assert st.get_watchlist("deni") == [9000014, 9000036]
    st.set_watchlist("ana", [9000019])
    assert st.all_watched() == [9000014, 9000019, 9000036]
    st.set_note("deni", 9000036, 4, "Check the STS partner")
    st.set_note("deni", 9000036, 5, "   ")
    assert st.get_notes("deni", 9000036) == {"4": "Check the STS partner"}
    assert st.get_notes("ana", 9000036) == {}


def test_alert_dedup_by_hour():
    st = MemoryStore()
    assert st.add_alert(9000036, "AIS gap", 1_000_000_800_000, "high", "AIS gap of 30 hours", "")
    assert not st.add_alert(9000036, "AIS gap", 1_000_000_800_000 + 20 * 60_000, "high", "AIS gap of 30 hours", "")   # same hour
    assert st.add_alert(9000036, "AIS gap", 1_000_000_800_000 + 2 * H, "high", "AIS gap of 31 hours", "")
    assert len(st.list_alerts(0)) == 2


def test_zone_switches_override_the_shipped_defaults():
    """config/zones.geojson ships Syria off and the rest on; an admin's switch in the app wins either way."""
    import tempfile
    from pathlib import Path

    from app import settings_store
    d = Path(tempfile.mkdtemp(prefix="me-test-"))
    settings_store.DATA_DIR, settings_store.FILE = d, d / "settings.json"
    svc = make_service()
    z = svc.ref.zone_by_id
    svc._apply_zone_settings()
    assert not z["syria"].enabled and z["crimea"].enabled
    settings_store.set_zone_enabled("syria", True)
    settings_store.set_zone_enabled("crimea", False)
    svc._apply_zone_settings()
    assert z["syria"].enabled and not z["crimea"].enabled
    settings_store.set_zone_enabled("syria", False)
    svc._apply_zone_settings()
    assert not z["syria"].enabled and settings_store.zones_on() == [] and "syria" in settings_store.zones_off()


def test_verdicts_from_older_rules_count_as_not_checked():
    """After a rule fix, stored verdicts from the old rules must not keep ships on the High-risk list: they read as
    not checked until the background sweep (or opening the ship) checks them again."""
    from app.engine import ENGINE_VERSION
    svc = make_service()
    svc.store.save_risk(9000013, {"name": "OLD", "level": "high", "high": 3, "engine": "2026-01-01:0"})
    svc.store.save_risk(9000036, {"name": "OLDER", "level": "high", "high": 1})          # written before versions existed
    assert svc.fresh_risk([9000013, 9000036]) == {}
    svc.analysis(9000013, refresh=True)
    fresh = svc.fresh_risk([9000013, 9000036])
    assert list(fresh) == [9000013] and fresh[9000013]["engine"].startswith(ENGINE_VERSION + ":")
    # switching a zone (or changing a threshold) in the app re-checks every ship too
    svc.set_zone("crimea", False)
    assert svc.fresh_risk([9000013]) == {}
    svc.set_zone("crimea", True)
    assert list(svc.fresh_risk([9000013])) == [9000013]
