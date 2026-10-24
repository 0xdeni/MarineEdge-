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
KEY_ENV = {"datalastic": "DATALASTIC_API_KEY", "kpler": "KPLER_API_KEY", "aisstream": "AISSTREAM_API_KEY", "gfw": "GFW_API_TOKEN"}


def version() -> int:
    """Changes whenever the file is written; lets every API worker notice an admin change."""
    try:
        return FILE.stat().st_mtime_ns
    except OSError:
        return 0


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


def mock_allowed() -> bool:
    """The generated demo fleet is for tests and local development only. A server never serves it unless
    VVT_ALLOW_MOCK=1 is set on purpose, so the live app can't show invented ships."""
    return os.environ.get("VVT_ALLOW_MOCK", "") == "1"


def provider_name() -> str:
    name = (load().get("provider") or os.environ.get("VVT_PROVIDER") or "aisstream").lower()
    if name == "mock" and not mock_allowed():
        return "aisstream"
    return name


def rule_overrides() -> dict[str, Any]:
    """Thresholds changed in the app (Profile › Rules & thresholds), merged over config/rules.yaml."""
    return dict(load().get("rules") or {})


def set_rule_overrides(over: dict[str, Any]) -> None:
    import time
    d = load()
    if over:
        d["rules"] = over
    else:
        d.pop("rules", None)
    d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save(d)


def zones_off() -> list[str]:
    return list(load().get("zones_off") or [])


def zones_on() -> list[str]:
    """Zones an admin switched on although config/zones.geojson ships them off (Syria since Oct 2026)."""
    return list(load().get("zones_on") or [])


def set_zone_enabled(zone_id: str, enabled: bool) -> list[str]:
    d = load()
    off = set(d.get("zones_off") or [])
    on = set(d.get("zones_on") or [])
    if enabled:
        off.discard(zone_id)
        on.add(zone_id)
    else:
        off.add(zone_id)
        on.discard(zone_id)
    d["zones_off"] = sorted(off)
    d["zones_on"] = sorted(on)
    save(d)
    return d["zones_off"]


def provider_key(name: str) -> str:
    keys = load().get("keys", {})
    return keys.get(name) or os.environ.get(KEY_ENV.get(name, ""), "")


def set_provider(name: str, api_key: str | None) -> None:
    import time
    d = load()
    d["provider"] = name
    d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if api_key:
        d.setdefault("keys", {})[name] = api_key.strip()
    save(d)


def set_key(name: str, api_key: str | None) -> None:
    """Store (or clear) one key without switching the active provider — used for the GFW cross-check token."""
    import time
    d = load()
    keys = d.setdefault("keys", {})
    if api_key and api_key.strip():
        keys[name] = api_key.strip()
    else:
        keys.pop(name, None)
    d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save(d)


def masked(key: str) -> str:
    return "" if not key else (key[:3] + "…" + key[-3:] if len(key) > 8 else "set")


def public_view() -> dict[str, Any]:
    d = load()
    return {"provider": provider_name(), "keys": {k: masked(provider_key(k)) for k in KEY_ENV}, "updated": d.get("updated"),
            "mockAllowed": mock_allowed()}


def update_state() -> dict[str, Any] | None:
    """Verdict of the last auto-update: deploy/autoupdate.sh writes state/update.json on the host, mounted
    read-only at /state in the api container. None until the first update has run."""
    p = Path(os.environ.get("VVT_STATE_DIR", "/state")) / "update.json"
    if not p.exists():
        p = Path(__file__).resolve().parents[2] / "state" / "update.json"
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def disk_view() -> dict[str, Any] | None:
    """Free and total space on the data disk (the same disk as the database on a one-server install)."""
    import shutil
    try:
        du = shutil.disk_usage(str(DATA_DIR) if Path(DATA_DIR).is_dir() else "/")
    except OSError:
        return None
    return {"free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1)}
