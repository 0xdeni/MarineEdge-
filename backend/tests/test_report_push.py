"""The PDF report's content, the 30-minute job's notifications (per-person severity, links to the finding),
sanctions wording that names only the lists the server holds, and the recorder's status file."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app import jobs, push, settings_store, verdict
from app.reports.render import render_html, svg_chart
from tests.test_service import make_service


def test_report_has_verdict_story_notes_and_server_rules():
    svc = make_service()
    a = svc.analysis(9000013)
    svc.store.add_vessel_note(9000013, "ship", "deni@example.com", "Owner confirmed the cargo was grain.")
    f = next(x for x in a.flags if x.severity == "high")
    svc.store.add_vessel_note(9000013, f"flag:{f.key}", "deni@example.com", "Asked the charterer about this one.")
    rules = dict(svc.rules)
    rules["ais_gap"] = {**rules["ais_gap"], "min_hours": 9}
    html = render_html(a, notes=svc.store.list_vessel_notes(9000013), ref=svc.ref, lists=["OFAC SDN", "EU"], rules=rules)
    assert a.verdict["sentence"] in html
    assert verdict.story(f, a, svc.ref)["title"] in html                       # findings read as in the app
    assert "Owner confirmed the cargo was grain." in html
    assert "On the finding" in html                                           # a note on a finding says which
    assert "an AIS gap is over 9 h at sea" in html                            # thresholds come from the server, not the template
    assert "OFAC SDN and EU" in html and "OFAC SDN, EU and UK" not in html    # only the lists really checked
    assert "indicators, not proof" in html


def test_report_chart_has_coastlines_and_numbered_findings():
    svc = make_service()
    a = svc.analysis(9000013)
    svg = svg_chart(a, svc.ref)
    assert svg.startswith("<svg") and svg.count("<path") > 10                # Natural Earth land drawn
    assert ">1</text>" in svg                                                # findings numbered like the list


def test_verdict_names_only_loaded_lists():
    svc = make_service()
    a = svc.analysis(9000013)
    a.flags = []
    a.sev = {"high": 0, "medium": 0, "info": 0}
    a.track = a.track[:30]
    v = verdict.build(a, sanctions_checked=True, lists=["OFAC SDN", "EU"])
    assert v["level"] == "insufficient"
    assert "OFAC or EU sanctions lists" in v["detail"] and "UK" not in v["detail"]
    v = verdict.build(a, sanctions_checked=False, lists=[])
    assert "haven't been downloaded" in v["detail"]


def test_notify_links_to_the_finding_and_respects_each_persons_choice():
    svc = make_service()
    st = svc.store
    for email, pref in (("high@example.com", None), ("medium@example.com", "medium")):
        uid = st.create_user(email, email.split("@")[0], "analyst", "x")
        if pref:
            st.update_user(uid, prefs={"pushMin": pref})
        st.set_watchlist(email, [9000013])
        st.add_push_subscription(email, {"endpoint": f"https://push.example/{email}", "keys": {"p256dh": "k", "auth": "a"}}, "test")
    sent = []
    orig_send, orig_conf = push.send, push.configured
    push.send = lambda sub, payload: sent.append((sub["endpoint"], payload)) or True
    try:
        n = jobs.notify(svc, [{"imo": 9000013, "rule": "AIS gap", "severity": "high", "title": "AZOV CRESCENT: AIS off for 44 hours", "body": "x", "key": "aisgap-1761401335754"},
                              {"imo": 9000013, "rule": "Draught change at sea", "severity": "medium", "title": "AZOV CRESCENT: Draught fell", "body": "y", "key": "draughtchang-1"}])
    finally:
        push.send, push.configured = orig_send, orig_conf
    assert n == 3                                                             # high → both people; medium → only the one who asked
    assert {e for e, p in sent if p["tag"].endswith("draughtchang-1")} == {"https://push.example/medium@example.com"}
    assert all(p["url"].startswith("#/ship/9000013/finding/") for _, p in sent)


def test_vapid_subject_never_a_placeholder():
    keep = {k: os.environ.get(k) for k in ("VAPID_SUBJECT", "DOMAIN", "PUBLIC_URL")}
    try:
        os.environ["VAPID_SUBJECT"] = "mailto:ops@yourcompany.com"
        os.environ["DOMAIN"] = "44-197-249-76.sslip.io"
        os.environ.pop("PUBLIC_URL", None)
        assert push.subject() == "https://44-197-249-76.sslip.io"
        os.environ["VAPID_SUBJECT"] = "mailto:deni@company.com"
        assert push.subject() == "mailto:deni@company.com"
    finally:
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_recorder_status_file_round_trip():
    from app import recorder
    d = Path(tempfile.mkdtemp(prefix="me-rec-"))
    keep = settings_store.DATA_DIR
    settings_store.DATA_DIR = d
    try:
        assert recorder.read_status() == {}
        recorder.write_status(state="error", error="Api Key Is Not Valid")
        st = recorder.read_status()
        assert st["state"] == "error" and st["error"] == "Api Key Is Not Valid" and st["since"]
        recorder.write_status(state="connected", error=None)
        assert recorder.read_status()["state"] == "connected"
    finally:
        settings_store.DATA_DIR = keep
