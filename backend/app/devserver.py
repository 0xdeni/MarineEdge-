"""Dependency-free dev server: serves the PWA and the same /api routes as app.main using only the
standard library, so `python -m app.devserver` works on a laptop with nothing installed but PyYAML.
Not for production (single-threaded, no auth). Use uvicorn app.main:app for the real API.

  cd backend && VVT_PROVIDER=mock python -m app.devserver            # http://127.0.0.1:8080/?source=server
"""
from __future__ import annotations

import json
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.service import Service, analysis_json, vessel_json

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "frontend" / "public"
REGIONS = {"blacksea": (27.2, 40.6, 42.0, 47.4), "hormuz": (55.3, 25.3, 57.7, 27.5), "iran": (48.0, 24.4, 61.8, 31.0), "oman": (52.8, 16.0, 62.6, 26.9), "uae": (51.3, 23.6, 57.3, 26.6), "all": (-180, -90, 180, 90)}
svc = Service()
USER = "dev"


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, fmt, *args):  # quieter
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        q = parse_qs(u.query)
        try:
            if p == "/api/health":
                return self._json({"ok": True, "provider": getattr(svc.provider, "name", "?"), "auth": "open", "dev": True})
            if p == "/api/vessels/search":
                return self._json([m.__dict__ for m in svc.search(q.get("q", [""])[0])])
            if p == "/api/fleet":
                svc.provider.generate_all()
                return self._json([analysis_json(svc.analysis(v.imo), include_track=False) for v in svc.provider.fleet])
            if p.startswith("/api/vessels/") and p.endswith("/crosscheck"):
                from app import settings_store
                from app.engine.types import YEAR
                from app.providers.gfw import GFWClient
                tok = settings_store.provider_key("gfw")
                if not tok:
                    return self._json({"ok": False, "source": "Global Fishing Watch", "error": "no Global Fishing Watch token yet — Profile › AIS provider › Cross-check token"})
                now = svc._now()
                return self._json(GFWClient(tok).crosscheck(int(p.split("/")[3]), now - YEAR, now))
            if p.startswith("/api/vessels/") and p.endswith("/analysis"):
                imo = int(p.split("/")[3])
                return self._json(analysis_json(svc.analysis(imo), include_track=q.get("track", ["1"])[0] != "0"))
            if p.startswith("/api/vessels/"):
                v = svc.provider.get_vessel(int(p.split("/")[3]))
                return self._json(vessel_json(v)) if v else self._json({"error": "unknown IMO"}, 404)
            if p.startswith("/api/regions/"):
                return self._json(svc.region(REGIONS[p.split("/")[3]]))
            if p == "/api/rules":
                return self._json(dict(svc.rules))
            if p == "/api/me":
                return self._json({"user": USER, "role": "admin", "watchlist": svc.store.get_watchlist(USER), "push": {"configured": False, "publicKey": ""}, "provider": getattr(svc.provider, "name", "?")})
            if p == "/api/admin/config":
                from app import settings_store
                return self._json({**settings_store.public_view(), "active": getattr(svc.provider, "name", "?"), "credits_used": getattr(svc.provider, "credits_used", 0), "fetches_this_run": svc.fetches, "live": svc.store.live_stats(), "update": settings_store.update_state(), "disk": settings_store.disk_view(), "db_gb": None, "database": False, "push": False, "auth": "open"})
            if p.startswith("/api/me/notes/"):
                return self._json(svc.store.get_notes(USER, int(p.split("/")[4])))
            if p == "/api/alerts":
                return self._json(svc.store.list_alerts(svc._now() - int(q.get("days", ["14"])[0]) * 86_400_000))
            if p.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
        except KeyError:
            return self._json({"error": "unknown"}, 404)
        if p == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_PUT(self):
        p = urlparse(self.path).path
        body = self._body()
        if p == "/api/me/watchlist":
            svc.store.set_watchlist(USER, body.get("imos", []))
            return self._json({"watchlist": svc.store.get_watchlist(USER)})
        if p.startswith("/api/me/notes/"):
            _, _, _, _, imo, n = p.split("/")
            svc.store.set_note(USER, int(imo), int(n), body.get("text", ""))
            return self._json(svc.store.get_notes(USER, int(imo)))
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        body = self._body()
        if p.startswith("/api/vessels/") and p.endswith("/report"):
            from app.reports.render import render_html
            html = render_html(svc.analysis(int(p.split("/")[3]))).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            return self.wfile.write(html)
        if p == "/api/push/subscribe":
            svc.store.add_push_subscription(USER, body, self.headers.get("User-Agent", ""))
            return self._json({"ok": True, "configured": False})
        if p == "/api/jobs/refresh":
            from app.jobs import refresh
            return self._json(refresh(svc))
        if p == "/api/admin/provider":
            try:
                return self._json(svc.set_provider(body.get("provider", "mock"), body.get("api_key")))
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)[:300]}, 400)
        if p == "/api/admin/test":
            try:
                return self._json(svc.test_provider())
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": str(e)[:300]})
        if p == "/api/admin/key":
            from app import settings_store
            if body.get("name") not in settings_store.KEY_ENV:
                return self._json({"error": "unknown key name"}, 400)
            settings_store.set_key(body["name"], body.get("api_key"))
            return self._json(settings_store.public_view())
        if p == "/api/admin/first-pull":
            return self._json(svc.first_pull([int(i) for i in body.get("imos", [])][:10]))
        if p == "/api/jobs/sanctions":
            return self._json({"error": "sanctions refresh needs DATABASE_URL (PostGIS)"}, 400)
        if p == "/api/rules/reload":
            return self._json(dict(svc.reload_rules()))
        return self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        p = urlparse(self.path).path
        body = self._body()
        if p == "/api/push/subscribe":
            svc.store.remove_push_subscription(body.get("endpoint", ""))
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()


def main():
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8080))
    print(f"MarineEdge dev server on http://127.0.0.1:{port}/?source=server  (provider: {getattr(svc.provider, 'name', '?')})")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
