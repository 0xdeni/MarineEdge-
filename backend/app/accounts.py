"""People and sessions: sign up, sign in, forgot/reset password, profiles, team invites.

Pure business logic over the Store, so the same code runs under FastAPI (app.main), the stdlib dev
server and the tests. Nothing here knows about HTTP; app.routes turns these calls into responses.

Rules this module keeps:
  * passwords are hashed with scrypt (stdlib, memory-hard), never stored or logged in clear
  * session, invite and reset secrets are random 256-bit values; only their SHA-256 is stored
  * sign-in and reset answers never reveal whether an email has an account
  * accounts are by invitation; the very first account (empty server) needs the server's setup
    code — the admin password written to .env by deploy/install.sh (API_TOKENS ...:admin)
  * the last active admin can't be removed, disabled or demoted
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

SESSION_DAYS = 90
INVITE_DAYS = 7
RESET_MINUTES = 30
RESET_LINK_HOURS = 24
RESET_MAX_ATTEMPTS = 5
MIN_PASSWORD = 10
ROLES = ("admin", "analyst")
DAY_MS = 86_400_000

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
AVATAR_COLORS = ["#0A84FF", "#5E5CE6", "#BF5AF2", "#30B0C7", "#34C759", "#FF9F0A", "#FF375F", "#64D2FF"]


class AccountError(Exception):
    """A refusal the person should see. `code` lets the client react (e.g. focus a field)."""

    def __init__(self, message: str, code: str = "invalid", status: int = 400, field: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.field = field


# ---------------------------------------------------------------- secrets
def now_ms() -> int:
    return int(time.time() * 1000)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii").rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s + "=" * (-len(s) % 4))


SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        # spend the same time as a real check so a missing account can't be told apart by timing
        hashlib.scrypt(b"x", salt=b"0" * 16, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
        return False
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(_unb64(dk)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, _unb64(dk))


def check_password_rules(password: str, email: str = "", name: str = "") -> None:
    if len(password) < MIN_PASSWORD:
        raise AccountError(f"Use at least {MIN_PASSWORD} characters.", "weak_password", field="password")
    if len(password) > 256:
        raise AccountError("That password is too long.", "weak_password", field="password")
    low = password.lower()
    if len(set(low)) < 4:
        raise AccountError("Use a less repetitive password.", "weak_password", field="password")
    for bad in {email.lower(), email.split("@")[0].lower(), name.lower()} - {""}:
        if len(bad) >= 4 and bad in low:
            raise AccountError("Your password shouldn't contain your name or email.", "weak_password", field="password")
    if low in COMMON:
        raise AccountError("That password is too common.", "weak_password", field="password")


COMMON = {"password12", "password123", "1234567890", "qwertyuiop", "letmein123", "iloveyou12", "marineedge", "marineedge1",
          "administrator", "welcome123", "0987654321", "1q2w3e4r5t", "qwerty1234", "passw0rd12", "abc1234567"}


def normalize_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e):
        raise AccountError("Enter a valid email address.", "bad_email", field="email")
    return e


def clean_name(name: str) -> str:
    n = re.sub(r"\s+", " ", (name or "").strip())
    if not n:
        raise AccountError("Enter your name.", "bad_name", field="name")
    if len(n) > 80:
        raise AccountError("That name is too long.", "bad_name", field="name")
    return n


def initials(name: str, email: str = "") -> str:
    parts = [p for p in re.split(r"[\s\-]+", name or "") if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return (email[:2] or "?").upper()


def avatar_color(seed: str) -> str:
    return AVATAR_COLORS[int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(AVATAR_COLORS)]


def device_label(ua: str) -> str:
    ua = ua or ""
    dev = "iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Mac" if "Macintosh" in ua else "Android" if "Android" in ua else "Windows PC" if "Windows" in ua else "Linux" if "Linux" in ua else "Device"
    app = "Safari" if ("Safari" in ua and "Chrome" not in ua and "CriOS" not in ua) else "Chrome" if ("Chrome" in ua or "CriOS" in ua) else "Firefox" if "Firefox" in ua else "Edge" if "Edg/" in ua else ""
    if "python" in ua.lower() or "curl" in ua.lower():
        return "Script"
    return f"{dev} · {app}" if app else dev


def public_user(u: dict) -> dict[str, Any]:
    return {"id": u["id"], "name": u.get("name") or u["email"].split("@")[0], "email": u["email"], "role": u.get("role") or "analyst",
            "status": u.get("status") or "active", "created": u.get("created_at"), "lastSeen": u.get("last_seen_at"), "lastLogin": u.get("last_login_at"),
            "prefs": u.get("prefs") or {}, "initials": initials(u.get("name") or "", u["email"]), "color": avatar_color(u["email"])}


# ---------------------------------------------------------------- rate limits (per process)
class RateLimiter:
    def __init__(self) -> None:
        self.hits: dict[str, deque] = {}
        self.lock = threading.Lock()

    def check(self, key: str, limit: int, window_s: int) -> None:
        now = time.monotonic()
        with self.lock:
            q = self.hits.setdefault(key, deque())
            while q and q[0] < now - window_s:
                q.popleft()
            if len(q) >= limit:
                wait = int(window_s - (now - q[0])) + 1
                raise AccountError(f"Too many attempts. Try again in {max(1, round(wait / 60))} min.", "rate_limited", status=429)
            q.append(now)

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()


LIMITS = RateLimiter()


# ---------------------------------------------------------------- setup code (the server's admin password)
def admin_tokens() -> list[str]:
    """Admin entries of API_TOKENS (name:token:admin). The first account on a server proves ownership with one."""
    out = []
    for part in os.environ.get("API_TOKENS", "").split(","):
        bits = [b.strip() for b in part.strip().split(":")]
        if len(bits) >= 3 and bits[2].lower() == "admin" and bits[1]:
            out.append(bits[1])
    return out


def setup_code_ok(code: str) -> bool:
    toks = admin_tokens()
    if not toks:
        return True               # a dev machine with no tokens configured: the first person to sign up owns it
    return any(code and hmac.compare_digest(code.strip(), t) for t in toks)


def legacy_owner_name() -> Optional[str]:
    """The users row the old token sign-in wrote state under (watchlist, notes, push): the admin token's name."""
    for part in os.environ.get("API_TOKENS", "").split(","):
        bits = [b.strip() for b in part.strip().split(":")]
        if len(bits) >= 3 and bits[2].lower() == "admin" and bits[0]:
            return bits[0]
    return None


# ---------------------------------------------------------------- the service
@dataclass
class Session:
    user: dict
    session_id: int
    token: str


class Accounts:
    def __init__(self, store, mailer=None):
        self.store = store
        self.mailer = mailer

    # ---- state for the sign-in screens
    def state(self) -> dict[str, Any]:
        return {"setup": self.store.count_users() == 0, "inviteOnly": True, "email": bool(self.mailer and self.mailer.configured()),
                "minPassword": MIN_PASSWORD}

    # ---- sessions
    def _start_session(self, user: dict, ua: str, ip: str) -> Session:
        token = new_secret()
        sid = self.store.create_session(user["id"], sha256(token), (ua or "")[:300], (ip or "")[:64], now_ms() + SESSION_DAYS * DAY_MS)
        self.store.update_user(user["id"], last_login_at=now_ms(), last_seen_at=now_ms())
        return Session(user=self.store.get_user(user["id"]), session_id=sid, token=token)

    def session_user(self, token: str) -> Optional[tuple[dict, int]]:
        """Resolve a session cookie. Slides the expiry forward; writes at most every 10 minutes."""
        if not token or len(token) > 200:
            return None
        s = self.store.get_session(sha256(token))
        if not s:
            return None
        t = now_ms()
        if s["expires_at"] < t:
            self.store.delete_session(s["id"])
            return None
        u = self.store.get_user(s["user_id"])
        if not u or u.get("status") != "active":
            return None
        if t - (s.get("last_seen_at") or 0) > 10 * 60_000:
            self.store.touch_session(s["id"], t, t + SESSION_DAYS * DAY_MS)
            self.store.update_user(u["id"], last_seen_at=t)
        return u, s["id"]

    def logout(self, session_id: int) -> None:
        self.store.delete_session(session_id)

    def sessions(self, user: dict, current_id: Optional[int]) -> list[dict]:
        out = []
        for s in self.store.list_sessions(user["id"]):
            out.append({"id": s["id"], "device": device_label(s.get("user_agent") or ""), "created": s["created_at"], "lastSeen": s["last_seen_at"],
                        "current": s["id"] == current_id})
        return sorted(out, key=lambda s: (not s["current"], -(s["lastSeen"] or 0)))

    def revoke_session(self, user: dict, session_id: int) -> None:
        if not any(s["id"] == session_id for s in self.store.list_sessions(user["id"])):
            raise AccountError("That device is already signed out.", "not_found", status=404)
        self.store.delete_session(session_id)

    def revoke_other_sessions(self, user: dict, current_id: Optional[int]) -> int:
        return self.store.delete_user_sessions(user["id"], except_id=current_id)

    # ---- sign up / sign in
    def signup(self, name: str, email: str, password: str, invite: str = "", setup_code: str = "", ua: str = "", ip: str = "") -> Session:
        LIMITS.check(f"signup:{ip}", 10, 3600)
        name, email = clean_name(name), normalize_email(email)
        check_password_rules(password, email, name)
        if self.store.count_users() == 0:
            if not setup_code_ok(setup_code):
                raise AccountError("That setup code isn't right. It's the admin password from the server setup.", "bad_setup_code", status=403, field="setupCode")
            uid = self._create_owner(name, email, password)
            return self._start_session(self.store.get_user(uid), ua, ip)
        inv = self.store.get_invite(sha256(invite.strip())) if invite.strip() else None
        if not inv or inv.get("used_at") or inv["expires_at"] < now_ms():
            raise AccountError("This invite has expired or was already used. Ask your admin for a new one." if inv else
                               "MarineEdge accounts are by invitation. Paste the invite link or code you received.", "bad_invite", status=403, field="invite")
        if inv.get("email") and inv["email"] != email:
            raise AccountError(f"This invite is for {inv['email']}.", "invite_email", status=403, field="email")
        if self.store.get_user_by_email(email):
            raise AccountError("There's already an account with this email. Sign in instead.", "exists", status=409, field="email")
        uid = self.store.create_user(email, name, inv.get("role") or "analyst", hash_password(password))
        self.store.use_invite(inv["id"], uid)
        return self._start_session(self.store.get_user(uid), ua, ip)

    def _create_owner(self, name: str, email: str, password: str) -> int:
        """First account on the server. If the old token sign-in left state under the admin token's name,
        that row becomes the owner so the watchlist, notes and push subscriptions carry over."""
        legacy = legacy_owner_name()
        if legacy:
            uid = self.store.adopt_user(legacy, email, name, "admin", hash_password(password))
            if uid:
                return uid
        return self.store.create_user(email, name, "admin", hash_password(password))

    def login(self, email: str, password: str, ua: str = "", ip: str = "") -> Session:
        e = (email or "").strip().lower()
        LIMITS.check(f"login-ip:{ip}", 30, 900)
        LIMITS.check(f"login:{e}", 10, 900)
        u = self.store.get_user_by_email(e) if e else None
        if u is None and self.store.count_users() == 0 and password and admin_tokens() and setup_code_ok(password):
            # The server was updated from token sign-in: signing in the old way (any email + admin password)
            # creates the owner account with that email, so nobody is locked out by the update.
            email_ok = normalize_email(e)
            uid = self._create_owner(email_ok.split("@")[0].replace(".", " ").title(), email_ok, password)
            return self._start_session(self.store.get_user(uid), ua, ip)
        if not verify_password(password or "", u.get("password_hash") if u else None):
            raise AccountError("Email or password is incorrect.", "bad_credentials", status=401)
        if u.get("status") != "active":
            raise AccountError("This account is turned off. Ask your admin.", "disabled", status=403)
        return self._start_session(u, ua, ip)

    # ---- forgot / reset
    def forgot(self, email: str, base_url: str, ip: str = "") -> dict[str, Any]:
        LIMITS.check(f"forgot-ip:{ip}", 10, 3600)
        mail_ok = bool(self.mailer and self.mailer.configured())
        try:
            e = normalize_email(email)
        except AccountError:
            raise
        LIMITS.check(f"forgot:{e}", 5, 3600)
        u = self.store.get_user_by_email(e)
        if u and u.get("status") == "active" and mail_ok:
            code = f"{secrets.randbelow(1_000_000):06d}"
            token = new_secret()
            self.store.create_reset(u["id"], sha256(f"{u['id']}:{code}"), sha256(token), now_ms() + RESET_MINUTES * 60_000, None)
            link = f"{base_url.rstrip('/')}/#/reset/{token}"
            try:
                self.mailer.send(e, "Your MarineEdge reset code",
                                 f"Hi {u.get('name') or ''},\n\nYour code to reset your MarineEdge password is {code}.\n"
                                 f"It works for {RESET_MINUTES} minutes. You can also open this link on your phone:\n{link}\n\n"
                                 "If you didn't ask for this, you can ignore this email; your password stays the same.",
                                 html=reset_email_html(u.get("name") or "", code, link))
            except Exception:  # noqa: BLE001  the answer must not reveal anything; the admin sees mail errors in the test screen
                pass
        return {"ok": True, "email": mail_ok}

    def reset_info(self, token: str) -> dict[str, Any]:
        r = self.store.get_reset_by_token(sha256(token or "")) if token else None
        if not r or r.get("used_at") or r["expires_at"] < now_ms():
            return {"valid": False}
        u = self.store.get_user(r["user_id"])
        return {"valid": bool(u), "email": u["email"] if u else None, "name": (u or {}).get("name")}

    def reset(self, password: str, email: str = "", code: str = "", token: str = "", ua: str = "", ip: str = "") -> Session:
        LIMITS.check(f"reset-ip:{ip}", 20, 3600)
        r = None
        if token:
            r = self.store.get_reset_by_token(sha256(token))
            if not r or r.get("used_at") or r["expires_at"] < now_ms():
                raise AccountError("This reset link has expired. Ask for a new one.", "bad_reset", status=400)
            u = self.store.get_user(r["user_id"])
        else:
            e = normalize_email(email)
            LIMITS.check(f"reset:{e}", 10, 3600)
            u = self.store.get_user_by_email(e)
            r = self.store.get_active_reset(u["id"]) if u else None
            if not u or not r or r.get("used_at") or r["expires_at"] < now_ms() or r.get("attempts", 0) >= RESET_MAX_ATTEMPTS:
                raise AccountError("That code has expired. Ask for a new one.", "bad_reset", status=400, field="code")
            if not r.get("code_hash") or not hmac.compare_digest(r["code_hash"], sha256(f"{u['id']}:{(code or '').strip()}")):
                self.store.bump_reset_attempts(r["id"])
                left = RESET_MAX_ATTEMPTS - r.get("attempts", 0) - 1
                raise AccountError("That code isn't right." + (f" {left} tries left." if left > 0 else " Ask for a new one."), "bad_code", status=400, field="code")
        if not u or u.get("status") != "active":
            raise AccountError("This account is turned off. Ask your admin.", "disabled", status=403)
        check_password_rules(password, u["email"], u.get("name") or "")
        self.store.update_user(u["id"], password_hash=hash_password(password))
        self.store.mark_reset_used(r["id"])
        self.store.delete_user_sessions(u["id"])
        return self._start_session(self.store.get_user(u["id"]), ua, ip)

    # ---- profile
    def update_profile(self, user: dict, name: Optional[str] = None, email: Optional[str] = None, current_password: str = "", prefs: Optional[dict] = None) -> dict:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = clean_name(name)
        if email is not None and email.strip().lower() != user["email"]:
            e = normalize_email(email)
            if not verify_password(current_password or "", user.get("password_hash")):
                raise AccountError("Enter your current password to change your email.", "bad_password", status=403, field="currentPassword")
            if self.store.get_user_by_email(e):
                raise AccountError("Another account uses that email.", "exists", status=409, field="email")
            fields["email"] = e
        if prefs is not None:
            merged = {**(user.get("prefs") or {}), **{k: v for k, v in prefs.items() if k in PREF_KEYS}}
            fields["prefs"] = merged
        if fields:
            self.store.update_user(user["id"], **fields)
        return self.store.get_user(user["id"])

    def change_password(self, user: dict, current: str, new: str, session_id: Optional[int]) -> None:
        LIMITS.check(f"pw:{user['id']}", 10, 3600)
        if not verify_password(current or "", user.get("password_hash")):
            raise AccountError("Your current password isn't right.", "bad_password", status=403, field="current")
        check_password_rules(new, user["email"], user.get("name") or "")
        self.store.update_user(user["id"], password_hash=hash_password(new))
        self.store.delete_user_sessions(user["id"], except_id=session_id)

    # ---- team (admin)
    def team(self) -> dict[str, Any]:
        users = [public_user(u) for u in self.store.list_users() if u.get("password_hash")]
        t = now_ms()
        invites = [{"id": i["id"], "email": i.get("email"), "role": i.get("role"), "created": i["created_at"], "expires": i["expires_at"],
                    "by": i.get("created_by")} for i in self.store.list_invites() if not i.get("used_at") and i["expires_at"] > t]
        return {"users": sorted(users, key=lambda u: (u["role"] != "admin", u["name"].lower())), "invites": invites}

    def create_invite(self, admin: dict, email: str = "", role: str = "analyst", base_url: str = "") -> dict[str, Any]:
        if role not in ROLES:
            raise AccountError("Role must be admin or analyst.", "bad_role")
        e = normalize_email(email) if (email or "").strip() else None
        if e and self.store.get_user_by_email(e):
            raise AccountError("That person already has an account.", "exists", status=409, field="email")
        code = new_secret()
        iid = self.store.create_invite(sha256(code), e, role, admin["id"], now_ms() + INVITE_DAYS * DAY_MS)
        link = f"{base_url.rstrip('/')}/#/invite/{code}"
        emailed = False
        if e and self.mailer and self.mailer.configured():
            try:
                self.mailer.send(e, f"{admin.get('name') or 'Your team'} invited you to MarineEdge",
                                 f"You've been invited to MarineEdge, the ship-checking tool your team uses.\n\nOpen this link on your phone to create your account (it works for {INVITE_DAYS} days):\n{link}\n",
                                 html=invite_email_html(admin.get("name") or "", link))
                emailed = True
            except Exception:  # noqa: BLE001
                emailed = False
        return {"id": iid, "code": code, "link": link, "email": e, "role": role, "expires": now_ms() + INVITE_DAYS * DAY_MS, "emailed": emailed}

    def invite_info(self, code: str) -> dict[str, Any]:
        inv = self.store.get_invite(sha256(code or "")) if code else None
        if not inv or inv.get("used_at") or inv["expires_at"] < now_ms():
            return {"valid": False}
        by = self.store.get_user(inv["created_by"]) if inv.get("created_by") else None
        return {"valid": True, "email": inv.get("email"), "role": inv.get("role"), "expires": inv["expires_at"], "invitedBy": (by or {}).get("name")}

    def revoke_invite(self, invite_id: int) -> None:
        self.store.delete_invite(invite_id)

    def _active_admins(self) -> list[dict]:
        return [u for u in self.store.list_users() if u.get("role") == "admin" and u.get("status") == "active" and u.get("password_hash")]

    def set_member(self, admin: dict, user_id: int, role: Optional[str] = None, status: Optional[str] = None) -> dict:
        u = self.store.get_user(user_id)
        if not u or not u.get("password_hash"):
            raise AccountError("No such person.", "not_found", status=404)
        if role is not None and role not in ROLES:
            raise AccountError("Role must be admin or analyst.", "bad_role")
        if status is not None and status not in ("active", "disabled"):
            raise AccountError("Status must be active or disabled.", "bad_status")
        losing_admin = u.get("role") == "admin" and u.get("status") == "active" and ((role and role != "admin") or status == "disabled")
        if losing_admin and len(self._active_admins()) <= 1:
            raise AccountError("Someone else has to be an admin first.", "last_admin", status=409)
        fields = {k: v for k, v in (("role", role), ("status", status)) if v is not None}
        if fields:
            self.store.update_user(user_id, **fields)
            if status == "disabled":
                self.store.delete_user_sessions(user_id)
        return public_user(self.store.get_user(user_id))

    def remove_member(self, admin: dict, user_id: int) -> None:
        u = self.store.get_user(user_id)
        if not u or not u.get("password_hash"):
            raise AccountError("No such person.", "not_found", status=404)
        if u.get("role") == "admin" and len(self._active_admins()) <= 1:
            raise AccountError("Someone else has to be an admin first.", "last_admin", status=409)
        self.store.delete_user(user_id)

    def admin_reset_link(self, admin: dict, user_id: int, base_url: str) -> dict[str, Any]:
        u = self.store.get_user(user_id)
        if not u or not u.get("password_hash"):
            raise AccountError("No such person.", "not_found", status=404)
        token = new_secret()
        exp = now_ms() + RESET_LINK_HOURS * 3_600_000
        self.store.create_reset(u["id"], None, sha256(token), exp, admin["id"])
        return {"link": f"{base_url.rstrip('/')}/#/reset/{token}", "expires": exp, "email": u["email"], "name": u.get("name")}


PREF_KEYS = {"theme", "region", "timeLocal", "pushMin", "introSeen"}


# ---------------------------------------------------------------- email bodies (plain + simple HTML)
def _email_frame(title: str, body_html: str) -> str:
    return ("<!doctype html><html><body style=\"margin:0;padding:24px;background:#F2F2F7;font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif;color:#1C1C1E\">"
            "<div style=\"max-width:440px;margin:0 auto;background:#FFFFFF;border-radius:18px;padding:28px\">"
            "<div style=\"font-size:15px;font-weight:600;letter-spacing:-0.2px;color:#0B1A2E\">MarineEdge</div>"
            f"<h1 style=\"font-size:22px;line-height:28px;margin:18px 0 10px\">{title}</h1>{body_html}"
            "<p style=\"font-size:13px;line-height:18px;color:#6E6E73;margin:22px 0 0\">If you didn't expect this email, you can ignore it.</p></div></body></html>")


def reset_email_html(name: str, code: str, link: str) -> str:
    from html import escape
    return _email_frame("Reset your password",
                        f"<p style=\"font-size:15px;line-height:21px;margin:0\">Hi {escape(name)}, here is your code. It works for {RESET_MINUTES} minutes.</p>"
                        f"<p style=\"font-size:34px;font-weight:700;letter-spacing:6px;margin:18px 0;font-variant-numeric:tabular-nums\">{escape(code)}</p>"
                        f"<p style=\"margin:0\"><a href=\"{escape(link)}\" style=\"display:inline-block;background:#0A6FE0;color:#FFFFFF;text-decoration:none;font-weight:600;padding:12px 20px;border-radius:22px\">Choose a new password</a></p>")


def invite_email_html(inviter: str, link: str) -> str:
    from html import escape
    who = escape(inviter) if inviter else "Your team"
    return _email_frame(f"{who} invited you",
                        "<p style=\"font-size:15px;line-height:21px;margin:0 0 18px\">MarineEdge checks ships before you fix them: twelve months of voyages, every red flag with its evidence.</p>"
                        f"<p style=\"margin:0\"><a href=\"{escape(link)}\" style=\"display:inline-block;background:#0A6FE0;color:#FFFFFF;text-decoration:none;font-weight:600;padding:12px 20px;border-radius:22px\">Create your account</a></p>"
                        f"<p style=\"font-size:13px;line-height:18px;color:#6E6E73;margin:14px 0 0\">The link works for {INVITE_DAYS} days.</p>")
