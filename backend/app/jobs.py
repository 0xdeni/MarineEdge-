"""Scheduled jobs. Run from cron inside the api container (deploy/cron.d-marineedge):

  python -m app.jobs refresh      every 30 min: re-analyse every watched vessel (buys only the new
                                  tail of positions), turn new flags into alerts, push them
  python -m app.jobs sanctions    daily: refresh the sanctions lists (same as app.cli sanctions-refresh)
  python -m app.jobs region       optional: warm the live region views (costs one area query per region)
  python -m app.jobs prune-live   daily: tiered retention for the recorded free feed (rules.live); --all for a full pass

Everything goes through Service, so the cache rule and the provider adapter apply as in the API."""
from __future__ import annotations

import json
import logging
import os
import sys
import time

from app import push
from app.service import Service

log = logging.getLogger("marineedge.jobs")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


def refresh(svc: Service | None = None, imos: list[int] | None = None) -> dict:
    svc = svc or Service()
    imos = imos if imos is not None else svc.store.all_watched()
    new_alerts: list[dict] = []
    errors = 0
    for imo in imos:
        try:
            a = svc.analysis(imo, refresh=True)
        except Exception:  # noqa: BLE001  one bad vessel must not stop the run
            log.exception("refresh failed for %s", imo)
            errors += 1
            continue
        for f in a.flags:
            if svc.store.add_alert(imo, f.rule, f.t0, f.severity, f"{a.vessel.name}: {f.title}", " · ".join(f.lines[:2])):
                new_alerts.append({"imo": imo, "rule": f.rule, "severity": f.severity, "title": f"{a.vessel.name}: {f.title}", "body": f.lines[0] if f.lines else "", "t0": f.t0})
    pushed = notify(svc, new_alerts) if new_alerts else 0
    out = {"vessels": len(imos), "fetches": svc.fetches, "new_alerts": len(new_alerts), "pushed": pushed, "errors": errors}
    log.info("refresh %s", json.dumps(out))
    return out


def notify(svc: Service, alerts: list[dict]) -> int:
    """Push each new alert to the subscriptions of users who watch that vessel. High flags only by
    default; set PUSH_MIN_SEVERITY=medium to include Medium."""
    min_sev = os.environ.get("PUSH_MIN_SEVERITY", "high")
    rank = {"high": 2, "medium": 1, "info": 0}
    sent = 0
    subs = svc.store.list_push_subscriptions()
    if not subs:
        return 0
    watchers: dict[int, set[str]] = {}
    for s in subs:
        for imo in svc.store.get_watchlist(s["user"]):
            watchers.setdefault(imo, set()).add(s["user"])
    for al in alerts:
        if rank.get(al["severity"], 0) < rank.get(min_sev, 2):
            continue
        for s in subs:
            if s["user"] not in watchers.get(al["imo"], set()):
                continue
            payload = {"title": al["title"], "body": al["body"], "url": f"#imo{al['imo']}", "tag": f"{al['imo']}-{al['rule']}"}
            try:
                if push.send(s["sub"], payload):
                    sent += 1
            except ValueError:            # subscription gone
                svc.store.remove_push_subscription(s["sub"]["endpoint"])
    return sent


def region(svc: Service | None = None) -> dict:
    svc = svc or Service()
    from app.main import REGIONS
    counts = {}
    for k, bbox in REGIONS.items():
        if k == "all":
            continue
        counts[k] = len(svc.region(bbox))
    log.info("region %s", json.dumps(counts))
    return counts


def prune_live(full: bool = False) -> dict:
    """Tiered retention for the recorded free feed; thresholds from rules.live. `full` thins the whole old table."""
    from app.engine import load_rules
    from app.store import make_store
    live = load_rules().get("live", {}) or {}
    store = make_store()
    return store.live_prune(int(live.get("full_res_days", 30)), int(live.get("thin_minutes", 30)), int(live.get("retention_months", 14)), window_days=None if full else 3)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "refresh"
    t0 = time.time()
    if cmd == "refresh":
        print(json.dumps(refresh()))
    elif cmd == "sanctions":
        from app.sanctions.loader import refresh_all
        print(json.dumps(refresh_all(os.environ["DATABASE_URL"], uk_csv_url=os.environ.get("UK_SANCTIONS_CSV_URL"), include_opensanctions=os.environ.get("OPENSANCTIONS", "") == "1")))
    elif cmd == "region":
        print(json.dumps(region()))
    elif cmd == "prune-live":
        print(json.dumps(prune_live(full=("--all" in argv))))
    else:
        print(__doc__)
        return 2
    print(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
