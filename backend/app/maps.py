"""Detailed base map, hosted on this server: an extract of the Protomaps OpenStreetMap basemap for the regions
MarineEdge records (Black Sea to the Eastern Mediterranean; the Gulf, Hormuz, Oman and the Arabian Sea).

An admin starts the download in the app (Profile › Maps). It runs once, in the background:
  1. fetch the `pmtiles` command-line tool (go-pmtiles, pinned version, SHA-256 checked) for this CPU
  2. find the newest daily build at build.protomaps.com
  3. `pmtiles extract` only the two regions, up to the chosen zoom, into the data volume
The web server then serves /tiles/basemap.pmtiles with HTTP range requests; the app reads it with a
small PMTiles reader (frontend/public/js/pmtiles.js). Until then, and offline, the app draws the
Natural Earth layers that ship with it. Map data © OpenStreetMap contributors (ODbL)."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import platform
import subprocess
import tarfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from app import settings_store

log = logging.getLogger("marineedge.maps")

PMTILES_VERSION = "1.31.2"
PMTILES_SHA256 = {   # go-pmtiles release tarballs, checked before anything is unpacked
    "x86_64": "3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f",
    "arm64": "f8bd47e7ea866863489cad588fbaf2f31f42e5821f7a03f009b3769f05801cb1",
}
BUILDS_URL = "https://build-metadata.protomaps.dev/builds.json"
BUILD_BASE = "https://build.protomaps.com/"
REGION = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"name": "Black Sea · Aegean · Eastern Mediterranean"},
     "geometry": {"type": "Polygon", "coordinates": [[[22.0, 29.5], [43.5, 29.5], [43.5, 48.5], [22.0, 48.5], [22.0, 29.5]]]}},
    {"type": "Feature", "properties": {"name": "Gulf · Hormuz · Oman · Arabian Sea"},
     "geometry": {"type": "Polygon", "coordinates": [[[43.5, 15.0], [65.0, 15.0], [65.0, 32.0], [43.5, 32.0], [43.5, 15.0]]]}},
]}
ZOOMS = (11, 12, 13, 14)
DEFAULT_ZOOM = 13

_lock = threading.Lock()


def _dir() -> Path:
    d = Path(settings_store.DATA_DIR) / "maps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_path() -> Path:
    return _dir() / "basemap.pmtiles"


def _status_path() -> Path:
    return _dir() / "status.json"


def _write(st: dict) -> None:
    p = _status_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st), encoding="utf-8")
    tmp.replace(p)


def _read() -> dict:
    try:
        return json.loads(_status_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def status() -> dict[str, Any]:
    st = _read()
    f = file_path()
    installed = f.exists() and f.stat().st_size > 1000
    state = st.get("state") or ("done" if installed else "idle")
    if state == "downloading" and time.time() - (st.get("heartbeat") or 0) > 180:
        state = "failed"
        st["error"] = st.get("error") or "the download stopped (server restarted?)"
    tmp = _dir() / "basemap.tmp.pmtiles"
    return {"installed": installed, "bytes": f.stat().st_size if installed else 0, "build": st.get("build"), "maxzoom": st.get("maxzoom"),
            "state": state, "error": st.get("error"), "started": st.get("started"), "finished": st.get("finished"),
            "progressBytes": tmp.stat().st_size if (state == "downloading" and tmp.exists()) else None, "url": "/tiles/basemap.pmtiles" if installed else None,
            "zooms": list(ZOOMS), "defaultZoom": DEFAULT_ZOOM, "attribution": "© OpenStreetMap contributors · Protomaps"}


def _arch() -> Optional[str]:
    m = platform.machine().lower()
    return "arm64" if m in ("aarch64", "arm64") else "x86_64" if m in ("x86_64", "amd64") else None


def _fetch(url: str, timeout: float = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "MarineEdge maps"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310  fixed https URLs only
        return r.read()


def ensure_tool() -> Path:
    bin_dir = Path(settings_store.DATA_DIR) / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / f"pmtiles-{PMTILES_VERSION}"
    if exe.exists():
        return exe
    arch = _arch()
    if arch is None:
        raise RuntimeError(f"no pmtiles build for this processor ({platform.machine()})")
    name = f"go-pmtiles_{PMTILES_VERSION}_Linux_{arch}.tar.gz"
    blob = _fetch(f"https://github.com/protomaps/go-pmtiles/releases/download/v{PMTILES_VERSION}/{name}", timeout=120)
    got = hashlib.sha256(blob).hexdigest()
    if got != PMTILES_SHA256[arch]:
        raise RuntimeError(f"pmtiles download failed its checksum ({got[:12]}…)")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        member = next((m for m in tf.getmembers() if m.name.rsplit("/", 1)[-1] == "pmtiles" and m.isfile()), None)
        if member is None:
            raise RuntimeError("pmtiles binary missing from the release archive")
        data = tf.extractfile(member).read()          # type: ignore[union-attr]
    tmp = exe.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o755)
    tmp.replace(exe)
    return exe


def latest_build() -> str:
    builds = json.loads(_fetch(BUILDS_URL, timeout=30))
    keys = sorted((b.get("key") for b in builds if str(b.get("key", "")).endswith(".pmtiles")), reverse=True)
    if not keys:
        raise RuntimeError("no basemap builds listed")
    return keys[0]


def start(maxzoom: int = DEFAULT_ZOOM) -> dict[str, Any]:
    if maxzoom not in ZOOMS:
        raise ValueError(f"zoom must be one of {ZOOMS}")
    with _lock:
        cur = status()
        if cur["state"] == "downloading":
            return cur
        _write({"state": "downloading", "started": int(time.time() * 1000), "heartbeat": time.time(), "maxzoom": maxzoom, "build": _read().get("build")})
    threading.Thread(target=_run, args=(maxzoom,), daemon=True).start()
    return status()


def _run(maxzoom: int) -> None:
    started = _read().get("started")
    tmp = _dir() / "basemap.tmp.pmtiles"
    try:
        exe = ensure_tool()
        key = latest_build()
        region = _dir() / "region.geojson"
        region.write_text(json.dumps(REGION), encoding="utf-8")
        if tmp.exists():
            tmp.unlink()
        cmd = [str(exe), "extract", BUILD_BASE + key, str(tmp), f"--region={region}", f"--maxzoom={maxzoom}", "--download-threads=4"]
        log.info("maps: %s", " ".join(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        stop = threading.Event()

        def beat() -> None:          # the status file says "alive" every 20 s while the tool runs
            while not stop.is_set():
                _write({"state": "downloading", "started": started, "heartbeat": time.time(), "maxzoom": maxzoom, "build": key})
                stop.wait(20)
        hb = threading.Thread(target=beat, daemon=True)
        hb.start()
        tail: list[str] = []
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                tail = (tail + [line.strip()])[-8:]
            code = proc.wait()
        finally:
            stop.set()
            hb.join(timeout=5)
        if code != 0 or not tmp.exists():
            raise RuntimeError(" / ".join(t for t in tail if t)[-400:] or f"pmtiles exited with {code}")
        tmp.replace(file_path())
        _write({"state": "done", "started": started, "finished": int(time.time() * 1000), "maxzoom": maxzoom, "build": key})
        log.info("maps: installed %s (%d MB)", key, file_path().stat().st_size // 1_000_000)
    except Exception as e:  # noqa: BLE001
        log.exception("maps download failed")
        _write({"state": "failed", "started": started, "finished": int(time.time() * 1000), "maxzoom": maxzoom, "error": str(e)[:400]})
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def remove() -> dict[str, Any]:
    with _lock:
        for p in (file_path(), _dir() / "basemap.tmp.pmtiles", _status_path()):
            try:
                p.unlink()
            except OSError:
                pass
    return status()
