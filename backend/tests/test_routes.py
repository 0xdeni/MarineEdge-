"""The HTTP layer (app/routes.py) without a server: auth levels, the CSRF header, notes permissions,
input checks, the verdict wording, and that a server never serves the demo fleet."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app import accounts as acc
from app import routes, settings_store, verdict
from tests.test_service import make_service

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1"


def _client():
    os.environ["API_TOKENS"] = "admin:owner-setup-code-1:admin"
    acc.LIMITS.reset()
    d = Path(tempfile.mkdtemp(prefix="me-test-"))            # settings written by these tests stay out of the real data dir
    settings_store.DATA_DIR, settings_store.FILE = d, d / "settings.json"
    routes.set_app(routes.App(make_service()))

    def call(method, path, body=None, cookie=None, query=None, csrf=True, headers=None):
        h = {"user-agent": UA}
        if csrf:
            h["x-marineedge"] = "1"
        if cookie:
            h["cookie"] = cookie
        h.update(headers or {})
        r = routes.dispatch(routes.Request(method=method, path=path, query=query or {}, headers=h,
                                           body=json.dumps(body).encode() if body is not None else b"", client_ip="10.0.0.1"))
        raw = r.encoded()
        try:
            data = json.loads(raw) if raw and r.content_type.startswith("application/json") else raw
        except ValueError:
            data = raw
        cookies = [v.split(";")[0] for k, v in r.headers if k == "Set-Cookie"]
        return r.status, data, cookies
    return call


def _owner(call):
    s, b, ck = call("POST", "/api/auth/signup", {"name": "Deni Dudaev", "email": "deni@example.com", "password": "a-long-pass-phrase", "setupCode": "owner-setup-code-1"})
    assert s == 200, b
    return ck[0]


def test_auth_levels_and_csrf():
    call = _client()
    assert call("GET", "/api/health")[0] == 200
    assert call("GET", "/api/auth/state")[1]["setup"] is True
    assert call("GET", "/api/me")[0] == 401
    assert call("POST", "/api/auth/login", {"email": "a@b.co", "password": "x"}, csrf=False)[0] == 403
    owner = _owner(call)
    assert call("GET", "/api/me", cookie=owner)[1]["user"]["role"] == "admin"
    assert call("PUT", "/api/me/watchlist", {"imos": [9000013]}, cookie=owner, csrf=False)[0] == 403
    assert call("PUT", "/api/me/watchlist", {"imos": [9000013]}, cookie=owner)[0] == 200
    assert call("PUT", "/api/me/watchlist", {"imos": ["x"]}, cookie=owner)[0] == 400
    # an API token (scripts) needs no CSRF header
    s, b, _ = call("GET", "/api/admin/config", headers={"authorization": "Bearer owner-setup-code-1"}, csrf=False)
    assert s == 200 and b["mock"] is True
    s, b, _ = call("POST", "/api/admin/invites", {"role": "analyst"}, cookie=owner)
    s, b, ck = call("POST", "/api/auth/signup", {"name": "Ana", "email": "ana@example.com", "password": "another-long-pass", "invite": b["code"]})
    ana = ck[0]
    assert call("GET", "/api/admin/config", cookie=ana)[0] == 403
    assert call("GET", "/api/regions", cookie=ana)[0] == 200
    s, _, ck = call("POST", "/api/auth/logout", cookie=ana)
    assert s == 204 and ck == ["me_session="]
    assert call("GET", "/api/me", cookie=ana)[0] == 401


def test_notes_belong_to_their_author():
    call = _client()
    owner = _owner(call)
    s, b, _ = call("POST", "/api/admin/invites", {"role": "analyst"}, cookie=owner)
    ana = call("POST", "/api/auth/signup", {"name": "Ana", "email": "ana@example.com", "password": "another-long-pass", "invite": b["code"]})[2][0]
    assert call("POST", "/api/vessels/9000013/notes", {"scope": "voyage:x", "text": "hi"}, cookie=ana)[0] == 400
    assert call("POST", "/api/vessels/9000013/notes", {"scope": "ship", "text": "   "}, cookie=ana)[0] == 400
    s, n, _ = call("POST", "/api/vessels/9000013/notes", {"scope": "flag:aisgap-1761582413062", "text": "Gap matches the Kerch closure"}, cookie=ana)
    assert s == 200 and n["mine"] and n["author"] == "Ana"
    notes = call("GET", "/api/vessels/9000013/notes", cookie=owner)[1]
    assert notes[0]["mine"] is False and notes[0]["canDelete"] is True            # admins may delete, not edit
    assert call("PATCH", f"/api/notes/{n['id']}", {"text": "edited"}, cookie=owner)[0] == 403
    assert call("PATCH", f"/api/notes/{n['id']}", {"text": "edited"}, cookie=ana)[1]["text"] == "edited"
    assert call("DELETE", f"/api/notes/{n['id']}", cookie=owner)[0] == 204
    assert call("GET", "/api/vessels/9000013/notes", cookie=ana)[1] == []


def test_ship_page_data_and_overview():
    call = _client()
    owner = _owner(call)
    s, a, _ = call("GET", "/api/vessels/9000013/analysis", cookie=owner)
    assert s == 200 and a["verdict"]["level"] == "high" and a["verdict"]["sentence"].startswith("Called at three ports in Crimea")
    assert all(f["key"] and isinstance(f["meta"], dict) for f in a["flags"]) and a["watching"] is False
    assert call("GET", "/api/vessels/1234567/analysis", cookie=owner)[0] == 404
    s, res, _ = call("GET", "/api/vessels/search", cookie=owner, query={"q": "silver dune"})
    assert res[0]["name"] == "AZOV CRESCENT" and res[0]["matchedFormer"] == "SILVER DUNE" and res[0]["verdict"]["level"] == "high"
    s, ov, _ = call("GET", "/api/regions/blacksea/overview", cookie=owner)
    assert s == 200 and ov["counts"]["inRange"] > 0 and ov["source"] == "demo"
    assert call("GET", "/api/regions/atlantis/overview", cookie=owner)[0] == 404
    s, html, _ = call("GET", "/api/vessels/9000013/report.html", cookie=owner)
    assert s == 200 and b"AZOV CRESCENT" in html


def test_rules_overrides_are_checked_and_persisted():
    call = _client()
    owner = _owner(call)
    assert call("PUT", "/api/admin/rules", {"overrides": {"ais_gap": {"min_hours": "8"}}}, cookie=owner)[0] == 400
    assert call("PUT", "/api/admin/rules", {"overrides": {"nope": {"x": 1}}}, cookie=owner)[0] == 400
    assert call("PUT", "/api/admin/rules", {"overrides": {"sanctions": {"lists": 1}}}, cookie=owner)[0] == 400
    assert call("PUT", "/api/admin/rules", {"overrides": {"sts": {"partner_needs_imo": 1}}}, cookie=owner)[0] == 400   # a switch takes on/off
    assert call("PUT", "/api/admin/rules", {"overrides": {"sts": {"min_hours": True}}}, cookie=owner)[0] == 400        # a number takes a number
    s, r, _ = call("PUT", "/api/admin/rules", {"overrides": {"ais_gap": {"min_hours": 8}, "sts": {"partner_needs_imo": False}}}, cookie=owner)
    assert s == 200 and r["rules"]["ais_gap"]["min_hours"] == 8 and r["rules"]["sts"]["partner_needs_imo"] is False
    assert settings_store.rule_overrides() == {"ais_gap": {"min_hours": 8}, "sts": {"partner_needs_imo": False}}
    s, r, _ = call("DELETE", "/api/admin/rules", cookie=owner)
    assert r["overrides"] == {} and settings_store.rule_overrides() == {}


def test_a_server_never_serves_the_demo_fleet():
    old = {k: os.environ.get(k) for k in ("VVT_PROVIDER", "VVT_ALLOW_MOCK")}
    try:
        os.environ["VVT_PROVIDER"] = "mock"
        os.environ.pop("VVT_ALLOW_MOCK", None)
        assert settings_store.provider_name() == "aisstream"
        os.environ["VVT_ALLOW_MOCK"] = "1"
        assert settings_store.provider_name() == "mock"
        os.environ.pop("VVT_PROVIDER", None)
        assert settings_store.provider_name() in ("aisstream", settings_store.load().get("provider"))
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_verdict_levels_read_plainly():
    svc = make_service()
    a = svc.analysis(9000011)                     # a clean ship in the demo fleet
    v = verdict.build(a)
    assert v["level"] == "clear" and v["sentence"].startswith("Nothing found in 12 months") and v["label"] == "No red flags"
    a.track = a.track[-30:]                       # pretend we only heard it for a few hours
    a.flags = []
    a.sev = {"high": 0, "medium": 0, "info": 0}
    v = verdict.build(a, sanctions_checked=False)
    assert v["level"] == "insufficient" and "haven't been downloaded" in v["detail"]
    hi = verdict.build(svc.analysis(9000014))
    assert hi["level"] == "high" and hi["sentence"] == "On the OFAC SDN and EU sanctions lists." and hi["detail"].startswith("It also ")
    assert len(hi["tiles"]) == 3 and hi["tiles"][0]["risk"]
