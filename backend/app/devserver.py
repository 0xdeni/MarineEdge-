"""Local development server, standard library only: serves the app (frontend/public), the map tiles file
(/tiles/, with HTTP range requests) and every /api route through app.routes — the same handlers the
production FastAPI app uses. Single machine, no TLS; not for production.

  cd backend && python -m app.devserver            # http://127.0.0.1:8080
  VVT_PROVIDER=aisstream python -m app.devserver   # the recorded-feed path instead of the demo fleet

Without VVT_PROVIDER the dev server uses the generated demo fleet so the screens have ships to show;
a real server never does (settings_store.mock_allowed)."""
from __future__ import annotations

import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

if not os.environ.get("VVT_PROVIDER"):
    os.environ["VVT_PROVIDER"] = "mock"
if os.environ["VVT_PROVIDER"] == "mock":
    os.environ.setdefault("VVT_ALLOW_MOCK", "1")

from app import routes  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "frontend" / "public"


def tiles_dir() -> Path:
    from app import settings_store
    return Path(os.environ.get("VVT_TILES_DIR") or (Path(settings_store.DATA_DIR) / "maps"))


class H(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, fmt, *args):  # quieter: API calls only
        if args and "/api/" in str(args[0]):
            super().log_message(fmt, *args)

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _api(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        req = routes.Request(method=self.command, path=u.path, query=dict(parse_qsl(u.query)),
                             headers={k.lower(): v for k, v in self.headers.items()}, body=body, client_ip=self.client_address[0])
        res = routes.dispatch(req)
        data = res.encoded() if res.status != 204 else b""
        self.send_response(res.status)
        if res.status != 204:
            self.send_header("Content-Type", res.content_type)
        self.send_header("Content-Length", str(len(data)))
        for k, v in res.headers:
            self.send_header(k, v)
        self.end_headers()
        if data and self.command != "HEAD":
            self.wfile.write(data)

    def _tiles(self):
        name = urlparse(self.path).path.split("/tiles/", 1)[1]
        f = tiles_dir() / Path(name).name
        if not f.is_file():
            self.send_error(404)
            return
        size = f.stat().st_size
        rng = self.headers.get("Range", "")
        start, end = 0, size - 1
        status = 200
        if rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b))
            end = min(size - 1, int(b)) if (a and b) else size - 1
            if start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        with open(f, "rb") as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api()
        if self.path.startswith("/tiles/"):
            return self._tiles()
        if urlparse(self.path).path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        return self._api()

    def do_PUT(self):
        return self._api()

    def do_PATCH(self):
        return self._api()

    def do_DELETE(self):
        return self._api()


def main():
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8080))
    s = routes.app_state().svc
    print(f"MarineEdge dev server on http://127.0.0.1:{port}  (data: {getattr(s.provider, 'name', '?')}{', DEMO FLEET' if s.is_mock else ''})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
