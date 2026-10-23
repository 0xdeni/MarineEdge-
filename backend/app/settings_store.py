"""Runtime settings that an admin changes from the app (phone) instead of editing .env on a server:
the AIS provider and its API key. Kept in a JSON file on the data volume with 0600 permissions.
Environment variables are the defaults; the file overrides them. Keys are never returned in full."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("VVT_DATA_DIR", "/data" if Path("/data").is_dir() else Path.home() / ".marineedge"))
FILE = DATA_DIR / "settings.json"
KEY_ENV = {"datalastic": "DATALASTIC_API_KEY", "kpler": "KPLER_API_KEY"}


def load() -> dict[str, Any]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(d: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(FILE)


def provider_name() -> str:
    return load().get("provider") or os.environ.get("VVT_PROVIDER", "mock")


def provider_key(name: str) -> str:
    keys = load().get("keys", {})
    return keys.get(name) or os.environ.get(KEY_ENV.get(name, ""), "")


def set_provider(name: str, api_key: str | None) -> None:
    d = load()
    d["provider"] = name
    if api_key:
        d.setdefault("keys", {})[name] = api_key.strip()
    save(d)


def masked(key: str) -> str:
    return "" if not key else (key[:3] + "…" + key[-3:] if len(key) > 8 else "set")


def public_view() -> dict[str, Any]:
    d = load()
    return {"provider": provider_name(), "keys": {k: masked(provider_key(k)) for k in KEY_ENV}, "file": str(FILE), "updated": d.get("updated")}
