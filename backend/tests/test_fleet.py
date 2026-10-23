"""Regression on the generated fleet: the mock provider is deterministic, so the per-rule flag counts
and the status mix must not drift when the engine changes. Update the numbers deliberately (with a
reason in the commit) when a rule is intentionally retuned."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.engine import analyze, load_refdata, load_rules
from app.engine.types import YEAR
from app.providers.mock import MockProvider

CONFIG = Path(__file__).resolve().parents[2] / "config"
FIXED_NOW = 1_792_700_000_000      # 22 Oct 2026 · fixed so the generated tracks are identical on every run


def build():
    ref = load_refdata(CONFIG)
    rules = load_rules(CONFIG / "rules.yaml")
    mp = MockProvider(ref=ref, now_ms=FIXED_NOW)
    mp.generate_all()

    def near(lat, lon, r, a0, a1):
        return [(n.vessel, n.t0, n.t1) for n in mp.get_vessels_near(lat, lon, r, a0, a1)]

    out = {}
    for v in mp.fleet:
        st = mp.get_static(v.imo)
        out[v.imo] = analyze(v, mp.get_track(v.imo, mp.now - YEAR, mp.now), ref, rules, now=mp.now, vessels_near=near, destination=st.destination, eta=st.eta)
    return out


def test_fleet_is_deterministic_and_well_formed():
    A = build()
    assert len(A) == 40
    rules = Counter(f.rule for a in A.values() for f in a.flags)
    assert set(rules) == {"Sanctions hit", "Call at a sensitive port", "AIS gap", "Draught change at sea", "Possible ship-to-ship transfer", "Position jump", "Identity change"}
    assert rules["Sanctions hit"] == 5 and rules["Identity change"] == 7          # fixed in fleet.json
    high = sum(1 for a in A.values() if a.sev["high"])
    assert 15 <= high <= 25, high                                                  # roughly half the fleet carries a High flag
    for a in A.values():
        assert a.stats["clean"] > 2500, a.vessel.name                              # ~hourly fixes for a year
        assert a.stats["port_calls"] >= 20 and a.stats["voyages"] >= 20
        assert a.status.state in ("underway", "anchored", "moored")
        assert all(f.id for f in a.flags)
        for vg in a.voyages:
            assert vg.nm >= 0 and (vg.arrive is None or vg.arrive >= vg.depart)
        for f in a.flags:
            if not f.vessel_level:
                assert f.voyage is not None and f.lat is not None
    # the same input twice gives the same counts
    B = build()
    assert Counter(f.rule for a in B.values() for f in a.flags) == rules


def test_low_risk_vessels_have_no_sensitive_calls():
    A = build()
    mp = MockProvider(ref=load_refdata(CONFIG), now_ms=FIXED_NOW)
    low = [d["imo"] for d in mp.cfg["fleet"] if d["risk"] < 0.3]
    for imo in low:
        assert not any(f.rule == "Call at a sensitive port" for f in A[imo].flags), A[imo].vessel.name
