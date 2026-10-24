"""Rule-engine tests on synthetic tracks. Each test plants one kind of event between real ports and
checks that the right rule fires with the right severity, and that nothing else does.
Runs under pytest, or `python -m tests.run` when pytest is not installed."""
from __future__ import annotations

from pathlib import Path

from app.engine import analyze, load_refdata, load_rules
from app.engine.rules_config import Rules
from app.engine.types import D, Vessel
from tests.synth import Track

CONFIG = Path(__file__).resolve().parents[2] / "config"
REF = load_refdata(CONFIG)
RULES = load_rules(CONFIG / "rules.yaml")
P = REF.by_id
T0 = 1_760_000_000_000                 # 9 Oct 2025, an arbitrary fixed epoch
NOW = T0 + 60 * D                      # tests evaluate "now" 60 days after T0


def vessel(**kw) -> Vessel:
    base = dict(imo=9100001, name="TEST VESSEL", flag="Malta", type="bulk", sub="Supramax bulk carrier", region="A", speed=12.0)
    base.update(kw)
    return Vessel(**base)


def run(track: Track, v: Vessel | None = None, **kw):
    return analyze(v or vessel(), track.pts, REF, RULES, now=NOW, **kw)


def rules_fired(a):
    return sorted({f.rule for f in a.flags})


# ---------------------------------------------------------------- clean
def test_clean_drops_duplicates_and_bad_fixes():
    tr = Track(T0, P["CND"].lat, P["CND"].lon).moor(12).sail_to_port(P["ODS"]).duplicate_last().bad_fix().moor(12)
    a = run(tr)
    assert a.stats["dup"] == 1 and a.stats["bad"] == 1
    assert a.stats["clean"] == a.stats["raw"] - 2
    assert all(abs(p.lat) <= 90 for p in a.track)


# ---------------------------------------------------------------- port calls & voyages
def test_port_call_detected_and_short_stop_ignored():
    tr = Track(T0, P["CND"].lat, P["CND"].lon).moor(20).sail_to_port(P["VAR"]).moor(2).sail_to_port(P["ODS"]).moor(30)
    a = run(tr)
    names = [pc.port.name for pc in a.port_calls]
    assert names == ["Constanța", "Odesa"], names          # the 2-hour stop at Varna is below min_hours
    assert a.voyages[-1].frm.port.name == "Constanța" and a.voyages[-1].to.port.name == "Odesa"
    assert not a.voyages[-1].current and a.status.state == "moored" and a.status.port.name == "Odesa"


def test_anchorage_then_berth_is_one_call():
    anch = P["CND"].anch
    tr = Track(T0, anch[1], anch[0]).moor(10, nav=1)        # waiting at the Constanța anchorage
    tr.speed = 6
    tr.sail_to_port(P["CND"]).moor(24)                       # then alongside
    a = run(tr)
    assert len(a.port_calls) == 1 and a.port_calls[0].port.name == "Constanța"
    assert a.port_calls[0].anchorage is False and a.port_calls[0].anch_hours >= 9


def test_current_voyage_is_open():
    tr = Track(T0, P["NVS"].lat, P["NVS"].lon).moor(24).sail_to(43.0, 33.0)
    a = run(tr)
    assert a.voyages[-1].current and a.voyages[-1].to is None
    assert a.status.state == "underway"


def test_voyage_distance_is_sane():
    tr = Track(T0, P["CND"].lat, P["CND"].lon).moor(12).sail_to_port(P["NVS"]).moor(12)
    a = run(tr)
    straight = __import__("app.engine.geo", fromlist=["nm_dist"]).nm_dist(P["CND"].lat, P["CND"].lon, P["NVS"].lat, P["NVS"].lon)
    assert abs(a.voyages[-1].nm - straight) < 25


# ---------------------------------------------------------------- AIS gap
def test_ais_gap_medium_in_open_sea():
    # Samsun → Burgas stays more than 100 nm south of Crimea; a 9 h gap there is Medium
    tr = Track(T0, P["SAM"].lat, P["SAM"].lon).moor(12).sail_to_port(P["BOJ"], gap=(0.5, 9)).moor(12)
    a = run(tr)
    gaps = [f for f in a.flags if f.rule == "AIS gap"]
    assert len(gaps) == 1 and gaps[0].severity == "medium" and 8 <= gaps[0].hours <= 11
    assert gaps[0].voyage is a.voyages[-1] and a.voyages[-1].dark_h == gaps[0].hours


def test_ais_gap_high_when_long():
    # Jebel Ali → Salalah is ~5 days at 12 kn; a 30 h gap in the Arabian Sea is High on length alone
    tr = Track(T0, P["JEA"].lat, P["JEA"].lon).moor(12).sail_to(25.9, 56.5).sail_to(24.0, 59.5).sail_to_port(P["SLL"], gap=(0.2, 30)).moor(12)
    a = run(tr, vessel(region="B"))
    gaps = [f for f in a.flags if f.rule == "AIS gap"]
    assert len(gaps) == 1 and gaps[0].severity == "high" and gaps[0].hours > 24


def test_ais_gap_high_near_sensitive_zone():
    # Novorossiysk → Constanța passes within 100 nm of Crimea; a 9 h gap there is High
    tr = Track(T0, P["NVS"].lat, P["NVS"].lon).moor(12).sail_to_port(P["CND"], gap=(0.45, 9)).moor(12)
    a = run(tr)
    gaps = [f for f in a.flags if f.rule == "AIS gap"]
    assert len(gaps) == 1 and gaps[0].severity == "high", [(f.severity, f.lines) for f in gaps]


def test_ais_gap_ending_moored_in_a_sanctioned_port_is_high():
    # Poti → Feodosia: AIS off half-way across, first fix back on is already moored in Feodosia (Crimea).
    # The gap starts more than 100 nm from Crimea and is under 24 h, so only its end makes it High.
    from dataclasses import replace
    tr = Track(T0, P["POT"].lat, P["POT"].lon).moor(12).sail_to_port(P["FEO"], gap=(0.5, 100))
    tr.pts[-1] = replace(tr.pts[-1], sog=0.0, nav=5)
    tr.moor(24)
    a = run(tr)
    gaps = [f for f in a.flags if f.rule == "AIS gap"]
    assert len(gaps) == 1 and gaps[0].severity == "high" and gaps[0].hours < 24, [(f.severity, f.hours, f.lines) for f in gaps]
    assert "inside Crimea" in gaps[0].lines[2]


def test_no_gap_flag_while_in_port():
    tr = Track(T0, P["CND"].lat, P["CND"].lon).moor(48)      # fixes every 3 h: never a gap
    a = run(tr)
    assert "AIS gap" not in rules_fired(a)


# ---------------------------------------------------------------- draught
def rules_with(**groups):
    """The default rules with some values changed, as an admin would in the app."""
    r = Rules({k: (dict(v) if isinstance(v, dict) else v) for k, v in RULES.items()})
    for g, vals in groups.items():
        r[g] = {**r[g], **vals}
    return r


def draughts(a):
    return [f for f in a.flags if f.rule == "Draught change at sea"]


def test_draught_change_after_a_stop_at_sea_is_high():
    tr = Track(T0, P["RTA"].lat, P["RTA"].lon, draught=15.0)
    v = vessel(region="B", type="tanker")
    tr.moor(12).sail_to(26.4, 53.6).drift(4).set_draught(12.4).sail_to_port(P["FJR"]).moor(12)
    dr = draughts(run(tr, v))
    assert len(dr) == 1 and dr[0].severity == "high" and "-2.6" in dr[0].title and dr[0].meta["cause"] == "stop"
    assert any("stop at sea" in ln for ln in dr[0].lines) and any("indicator, not proof" in ln for ln in dr[0].lines)


def test_draught_typed_in_under_way_after_a_port_call_is_info():
    """Cargo can't move while a ship is under way: a change typed in mid-passage is the last port's cargo entered late."""
    tr = Track(T0, P["RTA"].lat, P["RTA"].lon, draught=15.0)
    v = vessel(region="B", type="tanker")
    tr.moor(12).sail_to(26.4, 53.6).set_draught(12.4).sail_to_port(P["FJR"]).moor(12)
    a = run(tr, v)
    dr = draughts(a)
    assert len(dr) == 1 and dr[0].severity == "info" and dr[0].meta["cause"] == "underway" and dr[0].meta["port"] == "Ras Tanura"
    assert a.sev["high"] == 0
    # with the switch off (Profile › Red-flag rules) every change at sea counts, as in the brief
    strict_off = analyze(v, tr.pts, REF, rules_with(draught_change={"after_stop_or_dark_only": False}), now=NOW)
    assert [f.severity for f in draughts(strict_off)] == ["high"]


def test_draught_after_going_dark_is_high_unless_out_of_receiver_range():
    def track():
        return Track(T0, P["RTA"].lat, P["RTA"].lon, draught=15.0).moor(12).sail_to(26.4, 53.6, gap=(0.3, 10)).set_draught(12.4).sail_to_port(P["FJR"]).moor(12)
    v = vessel(region="B", type="tanker")
    dark = draughts(run(track(), v, coverage=lambda lon, lat: 500))
    assert len(dark) == 1 and dark[0].severity == "high" and dark[0].meta["cause"] == "dark"
    unheard = draughts(run(track(), v, coverage=lambda lon, lat: 0))
    assert len(unheard) == 1 and unheard[0].severity == "info" and unheard[0].meta["cause"] == "unheard"


def test_unknown_draught_is_not_a_change():
    """AIS sends draught in a separate message: positions heard before it carry 0, meaning "not known"."""
    tr = Track(T0, 43.2, 30.5, draught=0.0).sail_to(43.6, 31.4).set_draught(12.0).sail_to(44.0, 32.4)
    assert draughts(run(tr)) == []
    tr = Track(T0, 43.2, 30.5, draught=6.0).sail_to(43.4, 30.9).set_draught(0.0).sail_to(43.6, 31.4).drift(4).set_draught(12.0).sail_to(44.0, 32.4)
    dr = draughts(run(tr))
    assert len(dr) == 1 and dr[0].meta["from"] == 6.0 and dr[0].meta["to"] == 12.0 and dr[0].severity == "high"


def test_draught_change_in_port_is_not_flagged():
    tr = Track(T0, P["CND"].lat, P["CND"].lon, draught=8.0).moor(12).set_draught(13.5).moor(12).sail_to_port(P["ODS"]).moor(12)
    a = run(tr)
    assert "Draught change at sea" not in rules_fired(a)


# ---------------------------------------------------------------- STS
def test_sts_detected_with_partner():
    partner = vessel(imo=9100002, name="PARTNER ONE", type="tanker", region="B", sub="Aframax crude tanker")
    tr = Track(T0, P["FJR"].lat, P["FJR"].lon, draught=8.0)
    v = vessel(region="B", type="tanker")
    tr.moor(12).sail_to(25.0, 56.95).drift(4).sail_to_port(P["SOH"]).moor(12)
    drift_pts = [p for p in tr.pts if p.sog < 1 and p.nav == 0]
    t0, t1 = drift_pts[0].t, drift_pts[-1].t

    def near(lat, lon, radius_m, a0, a1):
        return [(partner, max(t0, a0), min(t1, a1))] if a0 < t1 and a1 > t0 else []

    a = run(tr, v, vessels_near=near)
    sts = [f for f in a.flags if f.rule == "Possible ship-to-ship transfer"]
    assert len(sts) == 1 and sts[0].partner_imo == 9100002 and sts[0].severity == "high"


def _anchored_off_fujairah():
    return Track(T0, P["FJR"].lat, P["FJR"].lon, draught=8.0).moor(12).sail_to(25.0, 56.95).moor(6, nav=1).sail_to_port(P["SOH"]).moor(12)


def _partner_at(dist_m, partner):
    """A provider that sees `partner` dist_m away for the whole stop: returned only when the search reaches it."""
    def near(lat, lon, radius_m, a0, a1):
        return [(partner, a0, a1)] if radius_m >= dist_m else []
    return near


def test_sts_at_anchor_needs_the_other_ship_alongside():
    """In an anchorage, ships 300-500 m apart are neighbours on their own anchors, not a transfer."""
    partner = vessel(imo=9100002, name="PARTNER ONE", type="tanker", region="B", sub="Aframax crude tanker")
    v = vessel(region="B", type="tanker")
    sts = lambda a: [f for f in a.flags if f.rule == "Possible ship-to-ship transfer"]   # noqa: E731
    assert sts(run(_anchored_off_fujairah(), v, vessels_near=_partner_at(400, partner))) == []
    hit = sts(run(_anchored_off_fujairah(), v, vessels_near=_partner_at(60, partner)))
    assert len(hit) == 1 and hit[0].meta["alongside"] is True and "within 150 m" in hit[0].lines[0]
    # drifting (not anchored), the wider 500 m search applies
    drifting = Track(T0, P["FJR"].lat, P["FJR"].lon, draught=8.0).moor(12).sail_to(25.0, 56.95).drift(6).sail_to_port(P["SOH"]).moor(12)
    assert len(sts(run(drifting, v, vessels_near=_partner_at(400, partner)))) == 1


def test_sts_ignores_partners_without_an_imo_number():
    """Tugs, pilot boats and harbour craft broadcast no IMO number."""
    craft = vessel(imo=0, name="MMSI 273123456", type="other", region="B", sub="Tug")
    v = vessel(region="B", type="tanker")
    sts = lambda a: [f for f in a.flags if f.rule == "Possible ship-to-ship transfer"]   # noqa: E731
    assert sts(run(_anchored_off_fujairah(), v, vessels_near=_partner_at(60, craft))) == []
    loose = analyze(v, _anchored_off_fujairah().pts, REF, rules_with(sts={"partner_needs_imo": False}), now=NOW, vessels_near=_partner_at(60, craft))
    assert len(sts(loose)) == 1


def test_slow_drift_without_partner_is_not_sts():
    tr = Track(T0, P["FJR"].lat, P["FJR"].lon).moor(12).sail_to(25.0, 56.95).drift(4).sail_to_port(P["SOH"]).moor(12)
    a = run(tr, vessel(region="B"), vessels_near=lambda *a: [])
    assert "Possible ship-to-ship transfer" not in rules_fired(a)


# ---------------------------------------------------------------- position jump
def test_position_jump_is_medium_and_excluded_from_distance():
    tr = Track(T0, P["CND"].lat, P["CND"].lon).moor(12).sail_to(43.2, 30.5).jump(80).sail_to_port(P["NVS"]).moor(12)
    a = run(tr)
    j = [f for f in a.flags if f.rule == "Position jump"]
    assert len(j) == 1 and j[0].severity == "medium" and "jamming" in j[0].lines[1].lower()
    assert "Draught change at sea" not in rules_fired(a)
    straight = __import__("app.engine.geo", fromlist=["nm_dist"]).nm_dist(P["CND"].lat, P["CND"].lon, P["NVS"].lat, P["NVS"].lon)
    assert a.voyages[-1].nm < straight + 60     # the 80 nm hop is not counted twice


# ---------------------------------------------------------------- sensitive port
def test_call_at_sensitive_port_is_high():
    tr = Track(T0, P["NVS"].lat, P["NVS"].lon).moor(12).sail_to_port(P["SEV"]).moor(30).sail_to_port(P["CND"]).moor(12)
    a = run(tr)
    sp = [f for f in a.flags if f.rule == "Call at a sensitive port"]
    assert len(sp) == 1 and sp[0].severity == "high" and "Sevastopol" in sp[0].title and "Crimea" in sp[0].lines[0]


def test_disabled_zone_does_not_fire():
    REF.zone_by_id["crimea"].enabled = False
    try:
        tr = Track(T0, P["NVS"].lat, P["NVS"].lon).moor(12).sail_to_port(P["SEV"]).moor(30).sail_to_port(P["CND"]).moor(12)
        a = run(tr)
        assert "Call at a sensitive port" not in rules_fired(a)
    finally:
        REF.zone_by_id["crimea"].enabled = True


def test_syria_is_off_by_default():
    """Most US, EU and UK sanctions on Syria were lifted in 2025: the zone ships switched off (an admin can turn it on)."""
    syria = REF.zone_by_id["syria"]
    assert syria.default_on is False and syria.enabled is False and REF.zone_by_id["crimea"].default_on is True
    tr = Track(T0, P["MER"].lat, P["MER"].lon).moor(12).sail_to_port(P["TAR"]).moor(30).sail_to_port(P["MER"]).moor(12)
    assert "Call at a sensitive port" not in rules_fired(run(tr))
    syria.enabled = True
    try:
        assert "Call at a sensitive port" in rules_fired(run(tr))
    finally:
        syria.enabled = False


# ---------------------------------------------------------------- identity & sanctions
def test_identity_change_severity():
    one = vessel(history=[{"field": "flag", "from": "Panama", "to": "Gabon", "t": NOW - 30 * D}])
    two = vessel(history=[{"field": "flag", "from": "Panama", "to": "Gabon", "t": NOW - 30 * D}, {"field": "mmsi", "from": "352123456", "to": "626123456", "t": NOW - 28 * D}])
    old = vessel(history=[{"field": "name", "from": "OLD NAME", "to": "TEST VESSEL", "t": NOW - 400 * D}])
    tr = Track(T0, P["CND"].lat, P["CND"].lon).moor(24)
    assert [f.severity for f in run(tr, one).flags if f.rule == "Identity change"] == ["info"]
    assert [f.severity for f in run(tr, two).flags if f.rule == "Identity change"] == ["medium"]
    assert "Identity change" not in rules_fired(run(tr, old))


def test_sanctions_hit_for_every_listing_in_force_however_old():
    # The lists hold only listings in force, so the listing date never ages a hit out: a ship first seen on the
    # EU list 400 days ago and still there is as sanctioned as one listed last month.
    recent = vessel(sanctions=[{"list": "OFAC SDN", "programme": "RUSSIA-EO14024", "t": NOW - 100 * D}])
    old = vessel(sanctions=[{"list": "EU", "programme": "Reg. 833/2014", "t": NOW - 400 * D}])
    future = vessel(sanctions=[{"list": "UK", "programme": "", "t": NOW + 3 * D}])
    tr = Track(T0, P["CND"].lat, P["CND"].lon).moor(24)
    hit = [f for f in run(tr, recent).flags if f.rule == "Sanctions hit"]
    assert len(hit) == 1 and hit[0].severity == "high" and hit[0].vessel_level
    old_hit = [f for f in run(tr, old).flags if f.rule == "Sanctions hit"]
    assert len(old_hit) == 1 and old_hit[0].severity == "high", old_hit
    assert old_hit[0].lines[0].startswith("EU · Reg. 833/2014 · on the list since at least "), old_hit[0].lines
    assert "Sanctions hit" not in rules_fired(run(tr, future))


# ---------------------------------------------------------------- clean voyage
def test_clean_voyage_raises_nothing():
    tr = Track(T0, P["JEA"].lat, P["JEA"].lon).moor(20)
    tr.speed = 14
    v = vessel(region="B", type="container", sub="Container ship · 5,000 TEU")
    tr.sail_to(25.3, 55.6).sail_to(26.1, 56.2).sail_to(26.45, 56.75).sail_to(25.7, 57.2).sail_to_port(P["SOH"]).moor(20)
    a = run(tr, v)
    assert a.flags == [], [(f.rule, f.lines) for f in a.flags]
    assert len(a.voyages) == 1 and a.voyages[0].frm.port.name == "Jebel Ali" and a.voyages[0].to.port.name == "Sohar"
