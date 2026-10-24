"""The recorder: keeps one websocket open to aisstream.io, subscribed to the configured region boxes,
and writes position reports and static data into the store. Runs as its own container
(`recorder` in docker-compose) and restarts itself on any error.

  python -m app.recorder            # needs an aisstream key: the map screen or Profile › Data sources in the app, or AISSTREAM_API_KEY

Volume policy (config/rules.yaml → live:) — a ship under way reports every 2–10 s, at anchor every 3 min;
the engine needs far less (vendors sell hourly history), and small free servers have 30–40 GB disks:
  * significance sampling: one stored fix per ship per `moving_interval_s` (10 min) while under way and per
    `stationary_interval_s` (30 min) while stopped, plus a fix whenever the ship turns by `turn_deg` or
    starts/stops (with hysteresis, so an anchored ship swinging on its chain does not count), never closer
    than `min_interval_s` — about 4–5 stored fixes per ship-hour instead of hundreds received;
  * once a ship's static data says it is not a cargo ship or tanker (`keep_types`), its positions are dropped;
  * every received position still counts one fix in its 0.5° coverage cell, so the AIS-gap rule knows where
    receivers can hear even for ships we do not store;
  * disk guard: below `min_free_gb` free on the data disk, positions stop being stored (coverage and static
    data continue) until space is freed, so a full disk can never take the database down;
  * `python -m app.jobs prune-live` (daily cron) thins rows older than `full_res_days` to one per
    `thin_minutes` and deletes rows older than `retention_months`.
Footprint with migration 004's slim rows (~130 bytes per fix with indexes): roughly 1 GB a month at full
resolution and 0.5 GB a month once thinned for every 3,000 ships in receiver range — about 7–12 GB a year.

Rules from aisstream's docs honoured here: first subscription within 3 s of connecting, read the socket
continuously (we batch writes off the hot path), no browser connections, at most 3 connections per account."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import time

from app import settings_store
from app.engine import load_rules
from app.providers.aisstream import REGION_BOXES, cell_of, parse_message

log = logging.getLogger("marineedge.recorder")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
WS_URL = "wss://stream.aisstream.io/v0/stream"
FLUSH_EVERY = 5.0          # seconds
STATS_EVERY = 300.0
KEY_CHECK_EVERY = 30.0     # a key pasted in the app is picked up within this
DISK_CHECK_EVERY = 60.0
NAV_STATES = {0, 1, 5}     # under way using engine, at anchor, moored: a change between these is a state change


def angle_diff(a: float, b: float) -> float:
    d = abs((a - b) % 360.0)
    return 360.0 - d if d > 180.0 else d


STATUS_FILE = "recorder.json"


def write_status(**fields) -> None:
    """What the recorder is doing, for Profile › Data sources: no_key | connecting | connected | error."""
    import json as _json
    p = settings_store.DATA_DIR / STATUS_FILE
    try:
        cur = _json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        cur = {}
    if fields.get("state") and fields["state"] != cur.get("state"):
        cur["since"] = int(time.time() * 1000)
    cur.update(fields)
    cur["updated"] = int(time.time() * 1000)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(_json.dumps(cur))
        tmp.replace(p)
    except OSError:
        pass


def read_status() -> dict:
    """The recorder's last status; 'stopped' when it hasn't written for 10 minutes."""
    import json as _json
    p = settings_store.DATA_DIR / STATUS_FILE
    try:
        st = _json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        st = {}
    if st and time.time() * 1000 - (st.get("updated") or 0) > 10 * 60_000:
        st = {**st, "state": "stopped"}
    return st


def current_key() -> str:
    return settings_store.provider_key("aisstream") or os.environ.get("AISSTREAM_API_KEY", "")


def parse_type_ranges(spec) -> list[tuple[int, int]]:
    """["70-89", "60"] → [(70, 89), (60, 60)]; empty → keep everything."""
    out = []
    for item in spec or []:
        s = str(item).strip()
        if "-" in s:
            a, b = s.split("-", 1)
            out.append((int(a), int(b)))
        elif s:
            out.append((int(s), int(s)))
    return out


class Recorder:
    def __init__(self, store, boxes=None, rules=None):
        self.store = store
        self.boxes = boxes or REGION_BOXES
        self.rules = rules or load_rules()
        live = self.rules.get("live", {}) or {}
        self.min_interval_ms = int(live.get("min_interval_s", 60)) * 1000
        self.moving_ms = int(live.get("moving_interval_s", 600)) * 1000
        self.stationary_ms = int(live.get("stationary_interval_s", 1800)) * 1000
        self.stationary_kn = float(live.get("stationary_kn", 0.5))
        self.moving_kn = float(live.get("moving_kn", 2.0))
        self.turn_deg = float(live.get("turn_deg", 25))
        self.turn_min_kn = float(live.get("turn_min_kn", 3.0))
        self.keep = parse_type_ranges(live.get("keep_types", ["70-89"]))
        self.min_free_gb = float(live.get("min_free_gb", 3))
        self.disk_path = str(settings_store.DATA_DIR) if os.path.isdir(str(settings_store.DATA_DIR)) else "/"
        self.disk_low = False
        self.static: dict[int, dict] = {}        # mmsi -> latest static row (imo, draught, type_code, …)
        self.last: dict[int, dict] = {}          # mmsi -> {t, cog, moving, nav} of the last stored fix
        self.buf: list[dict] = []
        self.cov: dict[tuple[int, int, int], int] = {}
        self.counts = {"received": 0, "stored": 0, "sampled_out": 0, "filtered": 0, "static": 0, "written": 0, "dropped": 0,
                       "unparsed": 0, "paused_disk": 0}
        self.stop = False

    def warm(self) -> None:
        """Load the MMSI→static map so positions get their IMO and draught from the first message."""
        n = 0
        for r in self.store.mmsi_all():
            self.static[r["mmsi"]] = r
            n += 1
        log.info("warm: %d MMSIs known · one fix per %ds under way / %ds stopped · keep types %s", n, self.moving_ms // 1000,
                 self.stationary_ms // 1000, self.keep or "all")

    def should_store(self, row: dict) -> bool:
        """Significance sampling (see module doc). The state that matters is the one of the last STORED fix."""
        m, t = row["mmsi"], row["t"]
        sog, cog, nav = float(row.get("sog") or 0.0), float(row.get("cog") or 0.0), row.get("nav")
        last = self.last.get(m)
        if last is None:
            self.last[m] = {"t": t, "cog": cog, "moving": sog >= self.moving_kn, "nav": nav}
            return True
        dt = t - last["t"]
        if dt < self.min_interval_ms:
            return False
        moving = sog >= self.stationary_kn if last["moving"] else sog >= self.moving_kn     # hysteresis
        due = dt >= (self.moving_ms if moving else self.stationary_ms)
        state = moving != last["moving"] or (nav in NAV_STATES and last["nav"] in NAV_STATES and nav != last["nav"])
        turned = moving and last["moving"] and sog >= self.turn_min_kn and angle_diff(cog, last["cog"]) >= self.turn_deg
        if due or state or turned:
            self.last[m] = {"t": t, "cog": cog, "moving": moving, "nav": nav}
            return True
        return False

    def check_disk(self) -> bool:
        """True while the data disk has less than min_free_gb free; storing positions pauses meanwhile."""
        try:
            free_gb = shutil.disk_usage(self.disk_path).free / 1e9
        except OSError:
            return self.disk_low
        low = free_gb < self.min_free_gb
        if low and not self.disk_low:
            log.warning("disk nearly full (%.1f GB free < %.1f GB): positions paused, coverage and static data continue", free_gb, self.min_free_gb)
        elif self.disk_low and not low:
            log.info("disk space back (%.1f GB free): storing positions again", free_gb)
        self.disk_low = low
        return low

    def keeps(self, type_code) -> bool:
        if not self.keep or type_code is None:
            return True
        return any(a <= int(type_code) <= b for a, b in self.keep)

    def handle(self, obj: dict) -> None:
        if isinstance(obj, dict) and obj.get("error"):          # aisstream says why it refuses (bad key, bad subscription)
            self.last_error = str(obj["error"])[:200]
            write_status(state="error", error=self.last_error)
            log.warning("aisstream: %s", self.last_error)
            return
        parsed = parse_message(obj)
        if parsed is None:
            self.counts["unparsed"] += 1
            return
        kind, row = parsed
        if kind == "static":
            self.counts["static"] += 1
            prev = self.static.get(row["mmsi"], {})
            merged = {**prev, **{k: v for k, v in row.items() if v is not None}, "updated_at": row["t"]}
            self.static[row["mmsi"]] = merged
            self.store.mmsi_upsert(merged)
            if row.get("name") and row["name"] != prev.get("name"):
                try:          # a new or changed broadcast name: kept so former names stay searchable
                    self.store.name_seen(row["mmsi"], prev.get("name"), row["name"], row["t"])
                except Exception:  # noqa: BLE001  older database without migration 005
                    log.debug("name_seen failed", exc_info=True)
            if merged.get("imo"):
                self.store.live_backfill_imo(row["mmsi"], merged["imo"])
            return
        self.counts["received"] += 1
        cx, cy = cell_of(row["lon"], row["lat"])
        day = row["t"] // 86_400_000 * 86_400
        self.cov[(cx, cy, day)] = self.cov.get((cx, cy, day), 0) + 1
        st = self.static.get(row["mmsi"], {})
        if not self.keeps(st.get("type_code")):
            self.counts["filtered"] += 1
            return
        if not self.should_store(row):
            self.counts["sampled_out"] += 1
            return
        if self.disk_low:
            self.counts["paused_disk"] += 1
            return
        row["imo"] = st.get("imo")
        row["draught"] = st.get("draught")
        self.buf.append(row)
        self.counts["stored"] += 1

    def flush(self) -> None:
        if self.cov:
            cov, self.cov = self.cov, {}
            try:
                self.store.coverage_add([(cx, cy, day, n) for (cx, cy, day), n in cov.items()])
            except Exception:  # noqa: BLE001
                log.exception("coverage flush failed")
        if not self.buf:
            return
        batch, self.buf = self.buf, []
        try:
            self.store.live_put(batch)
            self.counts["written"] += len(batch)
        except Exception:  # noqa: BLE001
            log.exception("flush failed; %d rows dropped", len(batch))
            self.counts["dropped"] += len(batch)

    async def run(self) -> None:
        import websockets  # type: ignore

        try:
            self.warm()
        except Exception as e:  # noqa: BLE001  database not up yet at boot: start cold, the map fills from the feed
            log.warning("warm-up skipped (%s); static data will be learned from the feed", str(e)[:160])
        backoff = 2
        last_flush = last_stats = last_key = last_disk = time.time()
        self.check_disk()
        while not self.stop:
            key = current_key()
            if not key:
                write_status(state="no_key", error=None)
                log.warning("no aisstream key yet: paste it in the app (Profile › Data sources); retrying in 30 s")
                await asyncio.sleep(30)
                continue
            write_status(state="connecting")
            got_first = False
            try:
                async with websockets.connect(WS_URL, max_size=2**20, ping_interval=20, ping_timeout=20, compression="deflate") as ws:
                    await ws.send(json.dumps({"APIKey": key, "BoundingBoxes": self.boxes, "FilterMessageTypes": ["PositionReport", "ShipStaticData", "StandardClassBPositionReport"]}))
                    log.info("subscribed to %d boxes", len(self.boxes))
                    n0 = self.counts.get("received", 0) + self.counts.get("static", 0)
                    async for raw in ws:
                        try:
                            self.handle(json.loads(raw))
                        except Exception:  # noqa: BLE001
                            self.counts["unparsed"] += 1
                            log.exception("bad message")
                        now = time.time()
                        if not got_first and self.counts.get("received", 0) + self.counts.get("static", 0) > n0:
                            got_first = True
                            backoff = 2
                            self.last_error = None
                            write_status(state="connected", error=None)
                        if now - last_flush >= FLUSH_EVERY:
                            self.flush()
                            last_flush = now
                        if now - last_stats >= STATS_EVERY:
                            log.info("stats %s", json.dumps(self.counts))
                            last_stats = now
                            write_status(state="connected", counts=dict(self.counts))
                        if now - last_disk >= DISK_CHECK_EVERY:
                            last_disk = now
                            self.check_disk()
                        if now - last_key >= KEY_CHECK_EVERY:
                            last_key = now
                            if key != current_key():
                                log.info("key changed; reconnecting")
                                break
            except Exception as e:  # noqa: BLE001  network errors, closed sockets, auth rejections
                log.warning("connection ended: %s; reconnecting in %d s", str(e)[:200], backoff)
                write_status(state="error", error=getattr(self, "last_error", None) or str(e)[:200])
                self.flush()
                await asyncio.sleep(backoff)
                backoff = min(120, backoff * 2)
                continue
            if not got_first and not self.stop:           # closed by the server before any data (e.g. a refused key): don't hammer it
                write_status(state="error", error=getattr(self, "last_error", None) or "the feed closed the connection without sending data")
                self.flush()
                await asyncio.sleep(backoff)
                backoff = min(120, backoff * 2)
        self.flush()


def main() -> None:
    from app.store import make_store

    rec = Recorder(make_store())
    loop = asyncio.new_event_loop()

    def _stop(*_):
        rec.stop = True

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _stop)
        except NotImplementedError:
            pass
    loop.run_until_complete(rec.run())


if __name__ == "__main__":
    main()
