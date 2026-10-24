"""Every /api route, once. Framework-free: a request comes in as plain data, a Response goes out.

app.main (FastAPI, production) and app.devserver (standard library, local development and the
end-to-end tests) both hand their requests to `dispatch()`, so what is tested locally is exactly what
runs on the server.

Security rules applied here for every route:
  * auth level per route: public | user | admin (app.auth resolves a session cookie or an API token)
  * state-changing requests made with a session cookie must carry `X-MarineEdge: 1` (a header a
    cross-site form can't send) — together with SameSite=Lax cookies this blocks CSRF
  * errors never echo stack traces; provider keys are scrubbed from messages
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from typing import Any, Callable, Optional

from app import accounts as acc
from app import auth, push, settings_store
from app.mailer import Mailer
from app.providers.base import CreditsExhausted, ProviderError
from app.service import REGIONS, Service, analysis_json, regions_json, vessel_json

log = logging.getLogger("marineedge.api")
VERSION = "1.0.0"


# ---------------------------------------------------------------- request / response
@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]                 # lower-case names
    body: bytes = b""
    client_ip: str = ""
    _json: Any = None

    def json(self) -> dict:
        if self._json is None:
            if not self.body:
                self._json = {}
            else:
                try:
                    self._json = json.loads(self.body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    raise HTTPError(400, "The request body isn't valid JSON.")
            if not isinstance(self._json, dict):
                raise HTTPError(400, "Expected a JSON object.")
        return self._json

    @property
    def cookies(self) -> dict[str, str]:
        c = SimpleCookie()
        try:
            c.load(self.headers.get("cookie", ""))
        except Exception:  # noqa: BLE001
            return {}
        return {k: v.value for k, v in c.items()}

    @property
    def ip(self) -> str:
        fwd = self.headers.get("x-forwarded-for", "")
        return (fwd.split(",")[0].strip() if fwd else "") or self.client_ip

    @property
    def secure(self) -> bool:
        return self.headers.get("x-forwarded-proto", "").lower() == "https"

    @property
    def base_url(self) -> str:
        dom = os.environ.get("PUBLIC_URL") or (f"https://{os.environ['DOMAIN']}" if os.environ.get("DOMAIN") and os.environ.get("DOMAIN") != "localhost" else "")
        if dom:
            return dom.rstrip("/")
        host = self.headers.get("x-forwarded-host") or self.headers.get("host") or "localhost"
        return f"{'https' if self.secure else 'http'}://{host}"


@dataclass
class Response:
    body: Any = None
    status: int = 200
    content_type: str = "application/json"
    headers: list[tuple[str, str]] = field(default_factory=list)

    def encoded(self) -> bytes:
        if self.body is None:
            return b""
        if isinstance(self.body, bytes):
            return self.body
        if isinstance(self.body, str):
            return self.body.encode("utf-8")
        return json.dumps(self.body, separators=(",", ":"), default=str).encode("utf-8")


class HTTPError(Exception):
    def __init__(self, status: int, detail: str, code: str = "", field: Optional[str] = None):
        super().__init__(detail)
        self.status, self.detail, self.code, self.field = status, detail, code, field


def _cookie(name: str, value: str, max_age: int, secure: bool) -> tuple[str, str]:
    parts = [f"{name}={value}", "Path=/", f"Max-Age={max_age}", "HttpOnly", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    return ("Set-Cookie", "; ".join(parts))


# ---------------------------------------------------------------- app state
class App:
    def __init__(self, svc: Optional[Service] = None):
        self.svc = svc or Service()
        self.mailer = Mailer()
        self.accounts = acc.Accounts(self.svc.store, self.mailer)


_APP: Optional[App] = None


def app_state() -> App:
    global _APP
    if _APP is None:
        _APP = App()
    return _APP


def set_app(a: App) -> None:
    global _APP
    _APP = a


# ---------------------------------------------------------------- routing table
Handler = Callable[..., Any]
ROUTES: list[tuple[str, re.Pattern, Handler, str]] = []


def route(method: str, pattern: str, auth_level: str = "user"):
    rx = re.compile("^" + re.sub(r"\{(\w+)(?::int)?\}", lambda m: f"(?P<{m.group(1)}>[0-9]+)" if ":int" in m.group(0) else f"(?P<{m.group(1)}>[^/]+)", pattern) + "$")
    ints = set(re.findall(r"\{(\w+):int\}", pattern))

    def deco(fn: Handler) -> Handler:
        fn._ints = ints  # type: ignore[attr-defined]
        ROUTES.append((method, rx, fn, auth_level))
        return fn
    return deco


UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def dispatch(req: Request) -> Response:
    t0 = time.perf_counter()
    try:
        res = _dispatch(req)
    except HTTPError as e:
        res = Response({"detail": e.detail, "code": e.code or None, "field": e.field}, status=e.status)
    except acc.AccountError as e:
        res = Response({"detail": str(e), "code": e.code, "field": e.field}, status=e.status)
    except CreditsExhausted as e:
        res = Response({"detail": f"The provider's credits are used up: {e}", "code": "credits"}, status=402)
    except ProviderError as e:
        res = Response({"detail": _scrub(str(e)), "code": "provider"}, status=502)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error on %s %s", req.method, req.path)
        res = Response({"detail": "Something went wrong on the server. Try again in a moment.", "code": "server"}, status=500)
    ms = (time.perf_counter() - t0) * 1000
    if ms > 1500:
        log.info("slow %s %s %d in %.0f ms", req.method, req.path, res.status, ms)
    res.headers.append(("Cache-Control", "no-store"))
    return res


def _scrub(msg: str) -> str:
    for name in settings_store.KEY_ENV:
        k = settings_store.provider_key(name)
        if k and len(k) > 4:
            msg = msg.replace(k, "***")
    return msg[:400]


def _dispatch(req: Request) -> Response:
    path = req.path.rstrip("/") or "/"
    allowed = []
    for method, rx, fn, level in ROUTES:
        m = rx.match(path)
        if not m:
            continue
        if method != req.method:
            allowed.append(method)
            continue
        params = {k: (int(v) if k in fn._ints else v) for k, v in m.groupdict().items()}  # type: ignore[attr-defined]
        A = app_state()
        who = auth.resolve(req.headers, req.cookies, A.accounts)
        if req.method in UNSAFE and req.headers.get("x-marineedge") != "1" and not (who and who.kind in ("token", "bearer-session")):
            raise HTTPError(403, "Missing the app's request header. Reload the app and try again.", "csrf")
        if level != "public" and who is None:
            raise HTTPError(401, "Sign in to continue.", "signin")
        if level == "admin" and not who.is_admin:  # type: ignore[union-attr]
            raise HTTPError(403, "Only an admin can do that.", "admin")
        out = fn(req, who, **params)
        if isinstance(out, Response):
            return out
        if out is None:
            return Response(None, status=204)
        return Response(out)
    if allowed:
        raise HTTPError(405, "Method not allowed.")
    raise HTTPError(404, "Not found.")


def svc() -> Service:
    return app_state().svc


def _body_str(req: Request, key: str, max_len: int = 300) -> str:
    v = req.json().get(key)
    if v is None:
        return ""
    if not isinstance(v, (str, int, float)):
        raise HTTPError(400, f"{key} must be text.", field=key)
    return str(v)[:max_len]


def _session_response(req: Request, sess: acc.Session, extra: Optional[dict] = None) -> Response:
    body = {"user": acc.public_user(sess.user), **(extra or {})}
    r = Response(body)
    r.headers.append(_cookie(auth.COOKIE, sess.token, acc.SESSION_DAYS * 86_400, req.secure))
    return r


def _analysis(imo: int, refresh: bool = False):
    try:
        return svc().analysis(imo, refresh=refresh)
    except KeyError:
        raise HTTPError(404, "MarineEdge has no data for that IMO yet.", "unknown_imo")


# ================================================================ public
@route("GET", "/api/health", "public")
def health(req, who):
    s = svc()
    return {"ok": True, "version": VERSION, "provider": getattr(s.provider, "name", "?"), "auth": "accounts"}


@route("GET", "/api/auth/state", "public")
def auth_state(req, who):
    st = app_state().accounts.state()
    st["signedIn"] = who is not None
    return st


@route("POST", "/api/auth/signup", "public")
def auth_signup(req, who):
    b = req.json()
    sess = app_state().accounts.signup(_body_str(req, "name", 120), _body_str(req, "email", 320), str(b.get("password") or "")[:300],
                                       invite=_body_str(req, "invite", 200), setup_code=str(b.get("setupCode") or "")[:300],
                                       ua=req.headers.get("user-agent", ""), ip=req.ip)
    return _session_response(req, sess)


@route("POST", "/api/auth/login", "public")
def auth_login(req, who):
    b = req.json()
    sess = app_state().accounts.login(_body_str(req, "email", 320), str(b.get("password") or "")[:300], ua=req.headers.get("user-agent", ""), ip=req.ip)
    return _session_response(req, sess)


@route("POST", "/api/auth/logout", "public")
def auth_logout(req, who):
    if who and who.session_id:
        app_state().accounts.logout(who.session_id)
    r = Response(None, status=204)
    r.headers.append(_cookie(auth.COOKIE, "", 0, req.secure))
    return r


@route("POST", "/api/auth/forgot", "public")
def auth_forgot(req, who):
    return app_state().accounts.forgot(_body_str(req, "email", 320), req.base_url, ip=req.ip)


@route("POST", "/api/auth/reset", "public")
def auth_reset(req, who):
    b = req.json()
    sess = app_state().accounts.reset(str(b.get("password") or "")[:300], email=_body_str(req, "email", 320), code=_body_str(req, "code", 20),
                                      token=_body_str(req, "token", 200), ua=req.headers.get("user-agent", ""), ip=req.ip)
    return _session_response(req, sess)


@route("GET", "/api/auth/invite/{code}", "public")
def auth_invite(req, who, code):
    return app_state().accounts.invite_info(code)


@route("GET", "/api/auth/reset/{token}", "public")
def auth_reset_info(req, who, token):
    return app_state().accounts.reset_info(token)


# ================================================================ the signed-in person
def _me_json(who: auth.Principal) -> dict:
    s = svc()
    user = acc.public_user(who.user) if who.user else {"id": 0, "name": who.key, "email": who.key, "role": who.role, "initials": who.key[:2].upper(), "color": "#0A84FF", "prefs": {}}
    watch = s.store.get_watchlist(who.key)
    return {"user": user, "watchlist": watch, "push": {"configured": push.configured(), "publicKey": push.public_key()},
            "unread": _unread(who), "server": {"version": VERSION, "source": "demo" if s.is_mock else getattr(s.provider, "name", "?"),
                                               "liveKey": bool(settings_store.provider_key("aisstream")), "mock": s.is_mock,
                                               "recorder": (_recorder_status().get("state") if who.is_admin else None)}}


@route("GET", "/api/me")
def me(req, who):
    return _me_json(who)


@route("PATCH", "/api/me")
def me_update(req, who):
    if not who.user:
        raise HTTPError(400, "API tokens have no profile.")
    b = req.json()
    prefs = b.get("prefs") if isinstance(b.get("prefs"), dict) else None
    u = app_state().accounts.update_profile(who.user, name=b.get("name") if isinstance(b.get("name"), str) else None,
                                            email=b.get("email") if isinstance(b.get("email"), str) else None,
                                            current_password=str(b.get("currentPassword") or ""), prefs=prefs)
    return {"user": acc.public_user(u)}


@route("POST", "/api/me/password")
def me_password(req, who):
    if not who.user:
        raise HTTPError(400, "API tokens have no password.")
    b = req.json()
    app_state().accounts.change_password(who.user, str(b.get("current") or ""), str(b.get("password") or ""), who.session_id)
    return {"ok": True}


@route("GET", "/api/me/sessions")
def me_sessions(req, who):
    if not who.user:
        return []
    return app_state().accounts.sessions(who.user, who.session_id)


@route("DELETE", "/api/me/sessions/{sid:int}")
def me_session_delete(req, who, sid):
    if not who.user:
        raise HTTPError(400, "API tokens have no sessions.")
    app_state().accounts.revoke_session(who.user, sid)
    return None


@route("POST", "/api/me/sessions/revoke-others")
def me_sessions_others(req, who):
    if not who.user:
        raise HTTPError(400, "API tokens have no sessions.")
    return {"signedOut": app_state().accounts.revoke_other_sessions(who.user, who.session_id)}


@route("PUT", "/api/me/watchlist")
def put_watchlist(req, who):
    imos = req.json().get("imos")
    if not isinstance(imos, list) or not all(isinstance(i, int) and 1_000_000 <= i <= 9_999_999 for i in imos):
        raise HTTPError(400, "imos must be a list of 7-digit IMO numbers.")
    svc().store.set_watchlist(who.key, imos[:500])
    return {"watchlist": svc().store.get_watchlist(who.key)}


@route("GET", "/api/me/watching")
def me_watching(req, who):
    """The watchlist with each ship's name, verdict and last position (what Home shows under Watching)."""
    s = svc()
    imos = s.store.get_watchlist(who.key)
    risk = s.store.get_risk(imos)
    out = []
    src = s.live_source()
    for imo in imos:
        r = risk.get(imo) or {}
        last = None
        try:
            if hasattr(src, "store"):
                last = src.store.live_last(imo)
            elif s.is_mock:
                tr = s.provider.get_track(imo, s._now() - 86_400_000, s._now())
                last = {"t": tr[-1].t, "lat": tr[-1].lat, "lon": tr[-1].lon, "sog": tr[-1].sog} if tr else None
        except Exception:  # noqa: BLE001
            last = None
        name = r.get("name")
        if not name and (s.is_mock or getattr(s.provider, "local", False)):
            v = s.provider.get_vessel(imo)
            name = v.name if v else None
        out.append({"imo": imo, "name": name or f"IMO {imo}", "level": r.get("level"), "headline": r.get("headline"), "checked": r.get("analysed_at"),
                    "last": {"t": last["t"], "lat": last["lat"], "lon": last["lon"], "sog": last.get("sog")} if last else None})
    return out


# ================================================================ regions, live map, search, ships
@route("GET", "/api/regions")
def regions(req, who):
    return regions_json()


@route("GET", "/api/regions/{rid}/overview")
def region_overview(req, who, rid):
    if rid not in REGIONS:
        raise HTTPError(404, "Unknown region.")
    return svc().overview(rid, who.key)


@route("GET", "/api/regions/{rid}/vessels")
def region_vessels(req, who, rid):
    if rid not in REGIONS:
        raise HTTPError(404, "Unknown region.")
    return svc().live_rows(REGIONS[rid]["bbox"])


@route("GET", "/api/vessels/search")
def search(req, who):
    q = (req.query.get("q") or "").strip()
    if len(q) < 2:
        return []
    return svc().search_json(q[:60])


@route("GET", "/api/vessels/{imo:int}")
def vessel(req, who, imo):
    v = svc().provider.get_vessel(imo)
    if v is None:
        raise HTTPError(404, "MarineEdge has no data for that IMO yet.", "unknown_imo")
    return vessel_json(v)


@route("GET", "/api/vessels/{imo:int}/analysis")
def analysis(req, who, imo):
    s = svc()
    a = _analysis(imo, refresh=req.query.get("refresh") == "1")
    out = analysis_json(a, include_track=req.query.get("track", "1") != "0", ref=s.ref)
    out["watching"] = imo in s.store.get_watchlist(who.key)
    out["history"] = s.history_status(imo)
    try:
        out["sanctionsChecked"] = (s.store.sanctions_status() or {}).get("refreshed") if not s.is_mock else s._now()
    except Exception:  # noqa: BLE001
        out["sanctionsChecked"] = None
    out["sanctionsLists"] = s.sanctions_lists()
    return out


@route("POST", "/api/vessels/{imo:int}/history", "admin")
def buy_history(req, who, imo):
    res = svc().buy_history(imo)
    a = _analysis(imo, refresh=True)
    return {**res, "verdict": a.verdict}


def _report(imo: int, fmt: str):
    from app.reports.render import render_html, render_pdf
    s = svc()
    a = _analysis(imo)
    notes = s.store.list_vessel_notes(imo)
    try:
        checked = (s.store.sanctions_status() or {}).get("refreshed") if not s.is_mock else s._now()
    except Exception:  # noqa: BLE001
        checked = None
    html = render_html(a, notes=notes, ref=s.ref, lists=s.sanctions_lists(), checked_at=checked, rules=dict(s.rules))
    if fmt == "html":
        return Response(html, content_type="text/html; charset=utf-8")
    path = render_pdf(html, imo)
    data = open(path, "rb").read()
    name = re.sub(r"[^A-Za-z0-9]+", "-", a.vessel.name).strip("-") or str(imo)
    return Response(data, content_type="application/pdf", headers=[("Content-Disposition", f'inline; filename="MarineEdge-{name}-{imo}.pdf"')])


@route("GET", "/api/vessels/{imo:int}/report.pdf")
def report_pdf(req, who, imo):
    return _report(imo, "pdf")


@route("GET", "/api/vessels/{imo:int}/report.html")
def report_html(req, who, imo):
    return _report(imo, "html")


@route("GET", "/api/vessels/{imo:int}/crosscheck")
def crosscheck(req, who, imo):
    from app.engine.types import YEAR
    from app.providers.gfw import GFWClient
    token = settings_store.provider_key("gfw")
    if not token:
        return {"ok": False, "imo": imo, "source": "Global Fishing Watch", "configured": False,
                "error": "No Global Fishing Watch token yet. An admin adds it in Profile › Data sources."}
    now = svc()._now()
    return GFWClient(token).crosscheck(imo, now - YEAR, now)


# ---- team notes
SCOPE_RX = re.compile(r"^(ship|voyage:\d{1,4}|flag:[a-z0-9]{1,12}-\d{9,14})$")


def _note_json(n: dict, who: auth.Principal) -> dict:
    mine = bool(who.user and n.get("user_id") == who.user["id"]) or (not who.user and n.get("author_email") == who.key)
    return {"id": n["id"], "imo": n["imo"], "scope": n["scope"], "text": n["text"], "created": n["created_at"], "updated": n["updated_at"],
            "author": n.get("author") or "Former member", "mine": mine, "canEdit": mine, "canDelete": mine or who.is_admin}


@route("GET", "/api/vessels/{imo:int}/notes")
def notes_list(req, who, imo):
    return [_note_json(n, who) for n in svc().store.list_vessel_notes(imo)]


@route("POST", "/api/vessels/{imo:int}/notes")
def notes_add(req, who, imo):
    scope = _body_str(req, "scope", 40) or "ship"
    text = (req.json().get("text") or "")
    if not isinstance(text, str) or not text.strip():
        raise HTTPError(400, "Write something first.", field="text")
    if not SCOPE_RX.match(scope):
        raise HTTPError(400, "Unknown note scope.", field="scope")
    nid = svc().store.add_vessel_note(imo, scope, who.key, text.strip()[:4000])
    return _note_json(svc().store.get_vessel_note(nid), who)


def _own_note(who: auth.Principal, nid: int, delete: bool = False) -> dict:
    n = svc().store.get_vessel_note(nid)
    if not n:
        raise HTTPError(404, "That note was deleted.")
    j = _note_json(n, who)
    if not (j["canDelete"] if delete else j["canEdit"]):
        raise HTTPError(403, "Only the author can change this note.")
    return n


@route("PATCH", "/api/notes/{nid:int}")
def notes_edit(req, who, nid):
    _own_note(who, nid)
    text = req.json().get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPError(400, "Write something first.", field="text")
    svc().store.update_vessel_note(nid, text.strip()[:4000])
    return _note_json(svc().store.get_vessel_note(nid), who)


@route("DELETE", "/api/notes/{nid:int}")
def notes_delete(req, who, nid):
    _own_note(who, nid, delete=True)
    svc().store.delete_vessel_note(nid)
    return None


# ---- alerts
def _alerts_for(who: auth.Principal, days: int) -> list[dict]:
    s = svc()
    watch = set(s.store.get_watchlist(who.key))
    items = s.store.list_alerts(s._now() - days * 86_400_000)
    return [a for a in items if a["imo"] in watch]


def _unread(who: auth.Principal) -> int:
    try:
        seen = svc().store.get_alerts_seen(who.key)
        return sum(1 for a in _alerts_for(who, 30) if a["created_at"] > seen)
    except Exception:  # noqa: BLE001
        return 0


@route("GET", "/api/alerts")
def alerts(req, who):
    try:
        days = max(1, min(90, int(req.query.get("days", "30"))))
    except ValueError:
        days = 30
    seen = svc().store.get_alerts_seen(who.key)
    return {"items": [{**a, "unread": a["created_at"] > seen} for a in _alerts_for(who, days)], "seen": seen, "watching": len(svc().store.get_watchlist(who.key))}


@route("POST", "/api/alerts/seen")
def alerts_seen(req, who):
    svc().store.set_alerts_seen(who.key, svc()._now())
    return {"ok": True}


# ---- push
@route("POST", "/api/push/subscribe")
def push_subscribe(req, who):
    b = req.json()
    if not isinstance(b.get("endpoint"), str) or not isinstance(b.get("keys"), dict):
        raise HTTPError(400, "Bad subscription.")
    svc().store.add_push_subscription(who.key, {"endpoint": b["endpoint"][:1000], "keys": b["keys"]}, req.headers.get("user-agent", "")[:200])
    return {"ok": True, "configured": push.configured()}


@route("DELETE", "/api/push/subscribe")
def push_unsubscribe(req, who):
    ep = req.json().get("endpoint")
    if isinstance(ep, str):
        svc().store.remove_push_subscription(ep)
    return {"ok": True}


@route("POST", "/api/push/test")
def push_test(req, who):
    if not push.configured():
        raise HTTPError(400, "Push isn't set up on this server (no VAPID keys).", "push_off")
    subs = svc().store.list_push_subscriptions([who.key])
    if not subs:
        raise HTTPError(400, "This device isn't subscribed yet.", "no_sub")
    sent = 0
    for s in subs:
        try:
            if push.send(s["sub"], {"title": "MarineEdge", "body": "Notifications work on this device.", "url": "#/alerts", "tag": "test"}):
                sent += 1
        except ValueError:
            svc().store.remove_push_subscription(s["sub"]["endpoint"])
    return {"sent": sent}


# ---- reference data for the map
@route("GET", "/api/geo/zones")
def geo_zones(req, who):
    feats = [{"type": "Feature", "properties": {"id": z.id, "name": z.name, "short": z.short or z.name, "basis": z.basis, "enabled": z.enabled},
              "geometry": {"type": "Polygon", "coordinates": [z.poly]}} for z in svc().ref.zones]
    return {"type": "FeatureCollection", "features": feats}


@route("GET", "/api/geo/ports")
def geo_ports(req, who):
    return [{"id": p.id, "name": p.name, "country": p.country, "lon": p.lon, "lat": p.lat, "zone": p.zone, "major": p.major}
            for p in svc().ref.ports if not p.pseudo]


@route("GET", "/api/rules")
def rules(req, who):
    return {"rules": dict(svc().rules), "overrides": settings_store.rule_overrides()}


# ================================================================ admin
@route("GET", "/api/admin/config", "admin")
def admin_config(req, who):
    from app import maps, mailer
    s = svc()
    live = db_bytes = sanc = None
    try:
        live = s.store.live_stats()
    except Exception:  # noqa: BLE001  table missing until migration 003 runs
        live = None
    try:
        db_bytes = s.store.db_size()
    except Exception:  # noqa: BLE001
        db_bytes = None
    try:
        sanc = s.store.sanctions_status()
    except Exception:  # noqa: BLE001
        sanc = None
    hp = s.history_provider()
    return {**settings_store.public_view(), "active": getattr(s.provider, "name", "?"), "credits_used": getattr(s.provider, "credits_used", 0), "live": live,
            "update": settings_store.update_state(), "disk": settings_store.disk_view(), "db_gb": round(db_bytes / 1e9, 2) if db_bytes else None,
            "fetches_this_run": s.fetches, "zones": [{"id": z.id, "name": z.name, "basis": z.basis, "enabled": z.enabled} for z in s.ref.zones],
            "database": bool(os.environ.get("DATABASE_URL")), "push": push.configured(), "email": mailer.public_view(), "maps": maps.status(),
            "sanctions": sanc, "history": {"available": hp is not None, "provider": getattr(hp, "name", None) if hp else None},
            "users": app_state().accounts.store.count_users(), "version": VERSION, "mock": s.is_mock, "sweep": dict(s._sweep_state),
            "recorder": _recorder_status()}


def _recorder_status() -> dict:
    try:
        from app.recorder import read_status
        return read_status()
    except Exception:  # noqa: BLE001
        return {}


@route("POST", "/api/admin/provider", "admin")
def admin_provider(req, who):
    b = req.json()
    name = str(b.get("provider") or "")
    allowed = ("aisstream", "datalastic", "kpler") + (("mock",) if settings_store.mock_allowed() else ())
    if name not in allowed:
        raise HTTPError(400, f"Provider must be one of: {', '.join(allowed)}.")
    try:
        return svc().set_provider(name, b.get("api_key") or None)
    except ProviderError as e:
        raise HTTPError(400, str(e))


@route("POST", "/api/admin/test", "admin")
def admin_test(req, who):
    return svc().test_provider()


@route("POST", "/api/admin/key", "admin")
def admin_key(req, who):
    b = req.json()
    name = str(b.get("name") or "")
    if name not in settings_store.KEY_ENV:
        raise HTTPError(400, f"Unknown key name {name!r}.")
    settings_store.set_key(name, b.get("api_key") or None)
    return settings_store.public_view()


@route("POST", "/api/admin/first-pull", "admin")
def admin_first_pull(req, who):
    imos = req.json().get("imos")
    if not isinstance(imos, list):
        raise HTTPError(400, "imos must be a list.")
    return svc().first_pull([int(i) for i in imos if str(i).isdigit()][:10])


# ---- team
@route("GET", "/api/admin/team", "admin")
def admin_team(req, who):
    return app_state().accounts.team()


@route("POST", "/api/admin/invites", "admin")
def admin_invite(req, who):
    if not who.user:
        raise HTTPError(400, "Invite people from a signed-in account.")
    return app_state().accounts.create_invite(who.user, email=_body_str(req, "email", 320), role=_body_str(req, "role", 20) or "analyst", base_url=req.base_url)


@route("DELETE", "/api/admin/invites/{iid:int}", "admin")
def admin_invite_delete(req, who, iid):
    app_state().accounts.revoke_invite(iid)
    return None


@route("PATCH", "/api/admin/users/{uid:int}", "admin")
def admin_user_update(req, who, uid):
    b = req.json()
    return app_state().accounts.set_member(who.user or {}, uid, role=b.get("role"), status=b.get("status"))


@route("DELETE", "/api/admin/users/{uid:int}", "admin")
def admin_user_delete(req, who, uid):
    if who.user and who.user["id"] == uid:
        raise HTTPError(400, "You can't remove yourself. Ask another admin.")
    app_state().accounts.remove_member(who.user or {}, uid)
    return None


@route("POST", "/api/admin/users/{uid:int}/reset-link", "admin")
def admin_reset_link(req, who, uid):
    return app_state().accounts.admin_reset_link(who.user or {"id": None}, uid, req.base_url)


# ---- email
@route("GET", "/api/admin/email", "admin")
def admin_email(req, who):
    from app import mailer
    return mailer.public_view()


@route("PUT", "/api/admin/email", "admin")
def admin_email_save(req, who):
    from app import mailer
    try:
        return mailer.save(req.json())
    except ValueError as e:
        raise HTTPError(400, str(e)[:1].upper() + str(e)[1:] + ".")


@route("POST", "/api/admin/email/test", "admin")
def admin_email_test(req, who):
    to = _body_str(req, "to", 320) or (who.user or {}).get("email")
    if not to:
        raise HTTPError(400, "Who should the test go to?", field="to")
    try:
        app_state().mailer.send(acc.normalize_email(to), "MarineEdge test email",
                                "Email delivery works. Password reset codes and invites will arrive like this one.")
    except acc.AccountError:
        raise
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        pw = (settings_store.load().get("smtp") or {}).get("password")
        if pw:
            msg = msg.replace(pw, "***")
        return {"ok": False, "error": msg[:300]}
    return {"ok": True, "to": to}


# ---- rules & zones
@route("PUT", "/api/admin/rules", "admin")
def admin_rules(req, who):
    over = req.json().get("overrides")
    if not isinstance(over, dict):
        raise HTTPError(400, "overrides must be an object.")
    base = svc().rules
    clean: dict[str, Any] = {}
    for grp, vals in over.items():
        if grp not in base or not isinstance(vals, dict) or not isinstance(base[grp], dict):
            raise HTTPError(400, f"Unknown rule group {grp!r}.")
        for k, v in vals.items():
            if k not in base[grp] or isinstance(base[grp][k], (list, dict)) or isinstance(v, bool) or not isinstance(v, (int, float)):
                raise HTTPError(400, f"{grp}.{k} can't be changed here.")
            if v < 0 or v > 100_000:
                raise HTTPError(400, f"{grp}.{k} is out of range.")
            clean.setdefault(grp, {})[k] = v
    r = svc().set_rule_overrides(clean)
    return {"rules": dict(r), "overrides": settings_store.rule_overrides()}


@route("DELETE", "/api/admin/rules", "admin")
def admin_rules_reset(req, who):
    r = svc().set_rule_overrides({})
    return {"rules": dict(r), "overrides": {}}


@route("POST", "/api/admin/zones/{zid}", "admin")
def admin_zone(req, who, zid):
    if zid not in svc().ref.zone_by_id:
        raise HTTPError(404, "Unknown zone.")
    en = req.json().get("enabled")
    if not isinstance(en, bool):
        raise HTTPError(400, "enabled must be true or false.")
    svc().set_zone(zid, en)
    return {"id": zid, "enabled": en}


# ---- maps
@route("GET", "/api/maps", "user")
def maps_status(req, who):
    from app import maps
    st = maps.status()
    return {"installed": st["installed"], "url": st["url"], "attribution": st["attribution"]}


@route("GET", "/api/admin/maps", "admin")
def admin_maps(req, who):
    from app import maps
    return maps.status()


@route("POST", "/api/admin/maps/download", "admin")
def admin_maps_download(req, who):
    from app import maps
    try:
        z = int(req.json().get("maxzoom") or maps.DEFAULT_ZOOM)
        return maps.start(z)
    except ValueError as e:
        raise HTTPError(400, str(e))


@route("DELETE", "/api/admin/maps", "admin")
def admin_maps_delete(req, who):
    from app import maps
    return maps.remove()


# ---- jobs
@route("POST", "/api/jobs/sanctions", "admin")
def jobs_sanctions(req, who):
    if not os.environ.get("DATABASE_URL"):
        raise HTTPError(400, "Sanctions lists need the server's database.")
    from app.sanctions.loader import refresh_all
    return refresh_all(os.environ["DATABASE_URL"], uk_csv_url=os.environ.get("UK_SANCTIONS_CSV_URL"), include_opensanctions=os.environ.get("OPENSANCTIONS", "") == "1")


@route("POST", "/api/jobs/refresh", "admin")
def jobs_refresh(req, who):
    from app.jobs import refresh
    return refresh(svc())


@route("POST", "/api/jobs/sweep", "admin")
def jobs_sweep(req, who):
    return svc().sweep(budget_s=float(req.json().get("seconds") or 30))
