"""FastAPI shell for production. Run: uvicorn app.main:app  (from backend/)

Every /api route lives once in app/routes.py, shared with the standard-library dev server, so the
code tested locally (end-to-end, through app.devserver) is the code that serves the app here. This
file only adapts FastAPI's request and response objects."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response as StarletteResponse

from app import routes

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
app = FastAPI(title="MarineEdge API", version=routes.VERSION, docs_url=None, redoc_url=None, openapi_url=None)
_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip() and o.strip() != "*"]
if _origins:   # same-origin by default (the app and the API share a domain); list other origins only if a separate client needs them
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "Authorization", "X-MarineEdge"])


def to_request(request: Request, path: str, body: bytes) -> routes.Request:
    return routes.Request(method=request.method.upper(), path="/api/" + path, query=dict(request.query_params),
                          headers={k.lower(): v for k, v in request.headers.items()}, body=body,
                          client_ip=request.client.host if request.client else "")


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def api(path: str, request: Request):
    body = await request.body()
    res = await run_in_threadpool(routes.dispatch, to_request(request, path, body))
    out = StarletteResponse(content=res.encoded() if res.status != 204 else b"", status_code=res.status,
                            media_type=None if res.status == 204 else res.content_type)
    for k, v in res.headers:
        out.headers.append(k, v)
    return out
