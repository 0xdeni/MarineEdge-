"""The recorder: keeps one websocket open to aisstream.io, subscribed to the configured region boxes,
and writes position reports and static data into the store. Runs as its own container
(`recorder` in docker-compose) and restarts itself on any error.

  python -m app.recorder            # needs an aisstream key: Profile › AIS provider in the app, or AISSTREAM_API_KEY

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
from app.providers.aisstream import REGION_BOXES, parse_message
from app.store import make_store

log = logging.getLogger("marineedge.recorder")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
WS_URL = "wss://stream.aisstream.io/v0/stream"
FLUSH_EVERY = 5.0          # seconds
STATS_EVERY = 300.0


def current_key() -> str:
    return settings_store.provider_key("aisstream") or os.environ.get("AISSTREAM_API_KEY", "")


class Recorder:
    def __init__(self, store, boxes=None):
        self.store = store
        self.boxes = boxes or REGION_BOXES
        self.static: dict[int, dict] = {}        # mmsi -> latest static row (imo, draught, …)
        self.buf: list[dict] = []
        self.counts = {"pos": 0, "static": 0, "written": 0, "dropped": 0}
        self.stop = False

    def warm(self) -> None:
        """Load the MMSI→static map so positions get their IMO and draught from the first message."""
        n = 0
        for r in self.store.mmsi_all():
            self.static[r["mmsi"]] = r
            n += 1
        log.info("warm: %d MMSIs known", n)

    def handle(self, obj: dict) -> None:
        parsed = parse_message(obj)
        if parsed is None:
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
        self.counts["pos"] += 1
        st = self.static.get(row["mmsi"], {})
        row["imo"] = st.get("imo")
        row["draught"] = st.get("draught")
        self.buf.append(row)

    def flush(self) -> None:
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

        self.warm()
        backoff = 2
        last_flush = last_stats = time.time()
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
                            log.exception("bad message")
                        now = time.time()
                        if now - last_flush >= FLUSH_EVERY:
                            self.flush()
                            last_flush = now
                        if now - last_stats >= STATS_EVERY:
                            log.info("stats %s", json.dumps(self.counts))
                            last_stats = now
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
