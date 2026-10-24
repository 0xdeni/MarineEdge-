"""Outgoing email for password resets and invites. Plain SMTP from the standard library, configured by an
admin in the app (Profile › Email) and stored with the other runtime settings on the data volume.

Any provider that speaks SMTP works: Resend, Postmark, Amazon SES, Mailgun, SendGrid, Brevo, or a Gmail /
Google Workspace mailbox with an app password. Nothing is sent until an admin saves a host and a sender."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Optional

from app import settings_store

SECURITY = ("starttls", "ssl", "none")


def config() -> dict[str, Any]:
    return dict(settings_store.load().get("smtp") or {})


class Mailer:
    def __init__(self, cfg: Optional[dict] = None):
        self._cfg = cfg

    @property
    def cfg(self) -> dict[str, Any]:
        return self._cfg if self._cfg is not None else config()

    def configured(self) -> bool:
        c = self.cfg
        return bool(c.get("host") and c.get("from_email"))

    def send(self, to: str, subject: str, text: str, html: Optional[str] = None, timeout: float = 20.0) -> None:
        c = self.cfg
        if not self.configured():
            raise RuntimeError("Email delivery isn't set up")
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((c.get("from_name") or "MarineEdge", c["from_email"]))
        msg["To"] = to
        msg["Message-ID"] = make_msgid(domain=c["from_email"].split("@")[-1])
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        host, port = c["host"], int(c.get("port") or 587)
        sec = c.get("security") or "starttls"
        ctx = ssl.create_default_context()
        if sec == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
        try:
            server.ehlo()
            if sec == "starttls":
                server.starttls(context=ctx)
                server.ehlo()
            if c.get("username"):
                server.login(c["username"], c.get("password") or "")
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass


def public_view() -> dict[str, Any]:
    c = config()
    return {"configured": bool(c.get("host") and c.get("from_email")), "host": c.get("host") or "", "port": int(c.get("port") or 587),
            "security": c.get("security") or "starttls", "username": c.get("username") or "", "password": settings_store.masked(c.get("password") or ""),
            "fromEmail": c.get("from_email") or "", "fromName": c.get("from_name") or "MarineEdge"}


def save(body: dict[str, Any]) -> dict[str, Any]:
    """Store SMTP settings. An empty password field keeps the saved one; `clear: true` removes everything."""
    d = settings_store.load()
    if body.get("clear"):
        d.pop("smtp", None)
        settings_store.save(d)
        return public_view()
    cur = dict(d.get("smtp") or {})
    host = (body.get("host") or "").strip()
    sec = (body.get("security") or cur.get("security") or "starttls").lower()
    if sec not in SECURITY:
        raise ValueError("security must be starttls, ssl or none")
    try:
        port = int(body.get("port") or cur.get("port") or (465 if sec == "ssl" else 587))
    except (TypeError, ValueError):
        raise ValueError("port must be a number")
    if not (0 < port < 65536):
        raise ValueError("port must be between 1 and 65535")
    sender = (body.get("fromEmail") or "").strip()
    if host and ("@" not in sender or "." not in sender.split("@")[-1]):
        raise ValueError("enter the sender address mail should come from")
    cur.update({"host": host, "port": port, "security": sec, "username": (body.get("username") or "").strip(),
                "from_email": sender, "from_name": (body.get("fromName") or "MarineEdge").strip()[:60]})
    if body.get("password"):
        cur["password"] = body["password"]
    d["smtp"] = cur
    settings_store.save(d)
    return public_view()
