"""The recorder: keeps one websocket open to aisstream.io, subscribed to the configured region boxes,
and writes position reports and static data into the store. Runs as its own container
(`recorder` in docker-compose) and restarts itself on any error.

  python -m app.recorder            # needs an aisstream key: Profile › AIS provider in the app, or AISSTREAM_API_KEY

Volume policy (config/rules.yaml → live:) — the raw feed for both regions is 10–25 M messages a day, far more
than a small server should keep, and far more than the engine needs (vendors sell hourly history):
  * one stored fix per ship per `min_interval_s` (default 120 s);
  * once a ship's static data says it is not a cargo ship or tanker (`keep_types`), its positions are dropped;
  * every received position still counts one fix in its 0.5° coverage cell, so the AIS-gap rule knows where
    receivers can hear even for ships we do not store;
  * `python -m app.jobs prune-live` (daily cron) thins rows older than `full_res_days` to one per
    `thin_minutes` and deletes rows older than `retention_months`.
Expected footprint after the policy: roughly 15 GB per year of PostGIS for both regions.

Rules from aisstream's docs honoured here: first subscription within 3 s of connecting, read the socket
continuously (we batch writes off the hot path), no browser connections, at most 3 connections per account."""
from __future__ import annotations

import asyncio
import json
import logging
import os
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
        self.min_interval_ms = int(live.get("min_interval_s", 120)) * 1000
        self.keep = parse_type_ranges(live.get("keep_types", ["70-89"]))
        self.static: dict[int, dict] = {}        # mmsi -> latest static row (imo, draught, type_code, …)
        self.last_t: dict[int, int] = {}         # mmsi -> timestamp of the last stored fix
        self.buf: list[dict] = []
        self.cov: dict[tuple[int, int, int], int] = {}
        self.counts = {"received": 0, "stored": 0, "sampled_out": 0, "filtered": 0, "static": 0, "written": 0, "dropped": 0, "unparsed": 0}
        self.stop = False

    def warm(self) -> None:
        """Load the MMSI→static map so positions get their IMO and draught from the first message."""
        n = 0
        for r in self.store.mmsi_all():
            self.static[r["mmsi"]] = r
            n += 1
        log.info("warm: %d MMSIs known · min interval %ds · keep types %s", n, self.min_interval_ms // 1000, self.keep or "all")

    def keeps(self, type_code) -> bool:
        if not self.keep or type_code is None:
            return True
        return any(a <= int(type_code) <= b for a, b in self.keep)

    def handle(self, obj: dict) -> None:
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
        last = self.last_t.get(row["mmsi"])
        if last is not None and row["t"] - last < self.min_interval_ms:
            self.counts["sampled_out"] += 1
            return
        self.last_t[row["mmsi"]] = row["t"]
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
        last_flush = last_stats = last_key = time.time()
        while not self.stop:
            key = current_key()
            if not key:
                log.warning("no aisstream key yet: paste it in the app (Profile › AIS provider › aisstream.io); retrying in 60 s")
                await asyncio.sleep(60)
                continue
            try:
                async with websockets.connect(WS_URL, max_size=2**20, ping_interval=20, ping_timeout=20, compression="deflate") as ws:
                    await ws.send(json.dumps({"APIKey": key, "BoundingBoxes": self.boxes, "FilterMessageTypes": ["PositionReport", "ShipStaticData", "StandardClassBPositionReport"]}))
                    log.info("subscribed to %d boxes", len(self.boxes))
                    backoff = 2
                    async for raw in ws:
                        try:
                            self.handle(json.loads(raw))
                        except Exception:  # noqa: BLE001
                            self.counts["unparsed"] += 1
                            log.exception("bad message")
                        now = time.time()
                        if now - last_flush >= FLUSH_EVERY:
                            self.flush()
                            last_flush = now
                        if now - last_stats >= STATS_EVERY:
                            log.info("stats %s", json.dumps(self.counts))
                            last_stats = now
                        if now - last_key >= KEY_CHECK_EVERY:
                            last_key = now
                            if key != current_key():
                                log.info("key changed; reconnecting")
                                break
            except Exception as e:  # noqa: BLE001  network errors, closed sockets, auth rejections
                log.warning("connection ended: %s; reconnecting in %d s", str(e)[:200], backoff)
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
