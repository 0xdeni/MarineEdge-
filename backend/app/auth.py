"""API access control. Two modes, chosen by environment:

  API_TOKENS unset   → open (local dev only; the frontend's demo login is cosmetic)
  API_TOKENS set     → every /api/* route except /api/health needs `Authorization: Bearer <token>`
                       or `X-API-Key: <token>`. Comma-separated `name:token` pairs, e.g.
                       API_TOKENS="deni:9f3a...,analyst2:77c1..."; the name is logged, never the token.

SSO (Google Workspace / Microsoft Entra) goes in front of this on deploy: Caddy or oauth2-proxy
authenticates the browser and forwards an identity header; see docs/DEPLOY.md. Tokens stay for the
CLI, scheduled jobs and the PWA on a phone."""
from __future__ import annotations

import hmac
import logging
import os
from typing import Optional

from fastapi import HTTPException, Request

log = logging.getLogger("marineedge.auth")


def _tokens() -> dict[str, str]:
    raw = os.environ.get("API_TOKENS", "").strip()
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, tok = part.partition(":")
        if tok:
            out[tok.strip()] = name.strip()
        else:
            out[name] = "token"
    return out


def enabled() -> bool:
    return bool(_tokens())


def identify(request: Request) -> Optional[str]:
    """Returns the caller's name, or None when no valid token is presented."""
    toks = _tokens()
    if not toks:
        return "open"
    cand = ""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        cand = auth[7:].strip()
    cand = cand or request.headers.get("x-api-key", "").strip()
    for tok, name in toks.items():
        if cand and hmac.compare_digest(cand, tok):
            return name
    return None


async def require_token(request: Request) -> str:
    """FastAPI dependency. Health stays open so load balancers and uptime checks work."""
    if request.url.path.rstrip("/") == "/api/health":
        return "health"
    who = identify(request)
    if who is None:
        raise HTTPException(status_code=401, detail="missing or invalid API token", headers={"WWW-Authenticate": "Bearer"})
    request.state.user = who
    return who
