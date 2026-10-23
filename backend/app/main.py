"""FastAPI app. Run: uvicorn app.main:app --reload  (from backend/)
Routes mirror the eight steps; the frontend consumes the same JSON shapes it uses in offline mode."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.auth import enabled as auth_enabled, require_token
from app.providers.base import CreditsExhausted, ProviderError
from app.service import Service, analysis_json, vessel_json

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
app = FastAPI(title="MarineEdge API", version="0.3.0", dependencies=[Depends(require_token)])
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
svc = Service()

REGIONS = {
    "blacksea": (27.2, 40.6, 42.0, 47.4), "hormuz": (55.3, 25.3, 57.7, 27.5), "iran": (48.0, 24.4, 61.8, 31.0),
    "oman": (52.8, 16.0, 62.6, 26.9), "uae": (51.3, 23.6, 57.3, 26.6), "all": (-180, -90, 180, 90),
}


@app.exception_handler(CreditsExhausted)
async def _credits(_, exc):
    return JSONResponse(status_code=402, content={"error": "provider credits exhausted", "detail": str(exc)})


@app.exception_handler(ProviderError)
async def _provider(_, exc):
    return JSONResponse(status_code=502, content={"error": "provider error", "detail": str(exc)})


@app.get("/api/health")
def health():
    return {"ok": True, "provider": getattr(svc.provider, "name", "?"), "auth": "token" if auth_enabled() else "open", "rules": dict(svc.rules), "zones": [{"id": z.id, "name": z.name, "enabled": z.enabled} for z in svc.ref.zones]}


@app.get("/api/vessels/search")
def search(q: str = Query(min_length=2)):
    return [vessel_json(m) if hasattr(m, "history") else m.__dict__ for m in svc.search(q)]


@app.get("/api/vessels/{imo}")
def vessel(imo: int):
    v = svc.provider.get_vessel(imo)
    if v is None:
        raise HTTPException(404, "unknown IMO")
    return vessel_json(v)


@app.get("/api/vessels/{imo}/analysis")
def analysis(imo: int, refresh: bool = False, track: bool = True):
    try:
        return analysis_json(svc.analysis(imo, refresh=refresh), include_track=track)
    except KeyError:
        raise HTTPException(404, "unknown IMO")


@app.get("/api/regions/{region}/vessels")
def region(region: str):
    if region not in REGIONS:
        raise HTTPException(404, "unknown region")
    return svc.region(REGIONS[region])


@app.get("/api/rules")
def rules():
    return dict(svc.rules)


@app.post("/api/rules/reload")
def rules_reload():
    return dict(svc.reload_rules())


class ZoneToggle(BaseModel):
    enabled: bool


@app.post("/api/zones/{zone_id}")
def zone_toggle(zone_id: str, body: ZoneToggle):
    if zone_id not in svc.ref.zone_by_id:
        raise HTTPException(404, "unknown zone")
    svc.set_zone(zone_id, body.enabled)
    return {"id": zone_id, "enabled": body.enabled}


@app.post("/api/vessels/{imo}/report")
def report(imo: int, fmt: str = "pdf"):
    from app.reports.render import render_html, render_pdf
    try:
        a = svc.analysis(imo)
    except KeyError:
        raise HTTPException(404, "unknown IMO")
    html = render_html(a)
    if fmt == "html":
        from fastapi.responses import HTMLResponse
        return HTMLResponse(html)
    path = render_pdf(html, imo)
    return FileResponse(path, media_type="application/pdf", filename=f"vvt-{imo}.pdf")


@app.get("/api/fleet")
def fleet():
    """Mock mode only: the whole sample fleet, analysed. Lets the PWA fill its lists in one call."""
    if not hasattr(svc.provider, "fleet"):
        raise HTTPException(404, "fleet listing is only available with the mock provider")
    svc.provider.generate_all()
    return [analysis_json(svc.analysis(v.imo), include_track=False) for v in svc.provider.fleet]
