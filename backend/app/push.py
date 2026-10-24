"""Web Push (VAPID). Keys in .env:
  VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY   generate once:  python -m app.push keygen
  VAPID_SUBJECT                          mailto:ops@yourcompany.com
Delivery uses pywebpush when installed; without it, send() logs and returns False so the rest of the
job still runs (alerts are stored either way and show in the app's Alerts tab)."""
from __future__ import annotations

import json
import logging
import os
import sys

log = logging.getLogger("marineedge.push")


def public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "")


def subject() -> str:
    """Who to contact about this sender. Apple's push service rejects placeholder addresses, so without
    VAPID_SUBJECT the server's own https address is used (DOMAIN or PUBLIC_URL from .env)."""
    v = (os.environ.get("VAPID_SUBJECT") or "").strip()
    if v and "yourcompany" not in v and "example.com" not in v:
        return v
    url = (os.environ.get("PUBLIC_URL") or "").strip().rstrip("/")
    if url.startswith("https://"):
        return url
    dom = (os.environ.get("DOMAIN") or "").strip()
    return f"https://{dom}" if dom and dom != "localhost" else "mailto:admin@localhost"


def configured() -> bool:
    return bool(os.environ.get("VAPID_PUBLIC_KEY") and os.environ.get("VAPID_PRIVATE_KEY"))


def send(sub: dict, payload: dict) -> bool:
    """Returns True when accepted by the push service; False on failure or when push is not configured.
    Raises Gone (410/404) as a ValueError so the caller can drop the subscription."""
    if not configured():
        log.info("push not configured; alert stored only: %s", payload.get("title"))
        return False
    try:
        from pywebpush import WebPushException, webpush  # type: ignore
    except ImportError:
        log.warning("pywebpush not installed (pip install pywebpush); alert stored only")
        return False
    try:
        webpush(subscription_info=sub, data=json.dumps(payload), vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub": subject()}, ttl=6 * 3600)
        return True
    except WebPushException as e:  # pragma: no cover - network
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            raise ValueError("gone") from e
        log.warning("push failed %s: %s", status, e)
        return False


def keygen() -> None:
    """Prints a VAPID key pair for .env (needs the `cryptography` package, pulled in by pywebpush)."""
    try:
        from cryptography.hazmat.primitives import serialization  # type: ignore
        from cryptography.hazmat.primitives.asymmetric import ec  # type: ignore
    except ImportError:
        sys.exit("pip install pywebpush  (brings cryptography)")
    import base64
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    print(f"VAPID_PUBLIC_KEY={b64(pub)}")
    print(f"VAPID_PRIVATE_KEY={b64(priv)}")
    print("VAPID_SUBJECT=mailto:ops@yourcompany.com")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "keygen":
        keygen()
    else:
        print(__doc__)
