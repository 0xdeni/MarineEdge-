"""Who is calling. Two kinds of caller:

  * people, signed in with an account (app/accounts.py): an HttpOnly session cookie `me_session`
    (or the same value as a Bearer token from a script)
  * scripts and scheduled jobs, with an API token from .env:
      API_TOKENS="admin:9f3a…:admin,etl:77c1…"   → `Authorization: Bearer <token>` or `X-API-Key: <token>`
    The name is logged, never the token. The admin token is also the setup code for the first account.

There is no anonymous mode: every /api route except health and the sign-in endpoints needs one of the two."""
from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("marineedge.auth")

COOKIE = "me_session"
ROLES: dict[str, str] = {}   # token name -> role, filled by _tokens()


def _tokens() -> dict[str, str]:
    """API_TOKENS="deni:9f3a…:admin,ana:77c1…"  → {token: name}; role per name in ROLES (analyst by default)."""
    raw = os.environ.get("API_TOKENS", "").strip()
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        if len(bits) >= 2:
            name, tok = bits[0].strip(), bits[1].strip()
            ROLES[name] = bits[2].strip().lower() if len(bits) > 2 and bits[2].strip() else "analyst"
            if tok:
                out[tok] = name
        else:
            out[bits[0]] = "token"
            ROLES["token"] = "analyst"
    return out


def tokens_configured() -> bool:
    return bool(_tokens())


def token_name(candidate: str) -> Optional[str]:
    for tok, name in _tokens().items():
        if candidate and hmac.compare_digest(candidate, tok):
            return name
    return None


@dataclass
class Principal:
    kind: str                       # "session" (a person) | "token" (a script)
    key: str                        # key for per-user state: the account email, or the token name
    role: str                       # admin | analyst
    user: Optional[dict] = None     # the account row for people
    session_id: Optional[int] = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def bearer(headers: dict[str, str]) -> str:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-api-key", "").strip()


def resolve(headers: dict[str, str], cookies: dict[str, str], accounts) -> Optional[Principal]:
    b = bearer(headers)
    if b:
        name = token_name(b)
        if name:
            return Principal(kind="token", key=name, role=ROLES.get(name, "analyst"))
        hit = accounts.session_user(b)
        if hit:
            u, sid = hit
            return Principal(kind="bearer-session", key=u["email"], role=u.get("role") or "analyst", user=u, session_id=sid)
        return None
    c = cookies.get(COOKIE)
    if c:
        hit = accounts.session_user(c)
        if hit:
            u, sid = hit
            return Principal(kind="session", key=u["email"], role=u.get("role") or "analyst", user=u, session_id=sid)
    return None
