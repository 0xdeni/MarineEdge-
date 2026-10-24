"""Scheduled jobs. Run from cron inside the api container (deploy/cron.d-marineedge):

  python -m app.jobs refresh      every 30 min: re-analyse every watched vessel (buys only the new
                                  tail of positions), turn new flags into alerts, push them
  python -m app.jobs sanctions    daily: refresh the sanctions lists (same as app.cli sanctions-refresh)
  python -m app.jobs region       optional: count ships in range per region
  python -m app.jobs sweep        every 20 min: check ships in range that are unchecked or stale (recorded data, free)
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
    from app import verdict as verdict_mod
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
            st = verdict_mod.story(f, a, svc.ref)
            title = f"{a.vessel.name}: {st['title']}"
            if svc.store.add_alert(imo, f.rule, f.t0, f.severity, title, st["text"]):
                new_alerts.append({"imo": imo, "rule": f.rule, "severity": f.severity, "title": title, "body": st["text"], "t0": f.t0, "key": f.key})
    pushed = notify(svc, new_alerts) if new_alerts else 0
    out = {"vessels": len(imos), "fetches": svc.fetches, "new_alerts": len(new_alerts), "pushed": pushed, "errors": errors}
    log.info("refresh %s", json.dumps(out))
    return out


def _min_severity(svc: Service, user: str, default: str) -> str:
    """A person's own choice (Profile › Notifications: High only, or High and Medium), else the server default."""
    try:
        u = svc.store.get_user_by_email(user)
    except Exception:  # noqa: BLE001
        u = None
    v = ((u or {}).get("prefs") or {}).get("pushMin")
    return v if v in ("high", "medium") else default


def notify(svc: Service, alerts: list[dict]) -> int:
    """Push each new alert to the subscriptions of the people who watch that vessel: High findings by default,
    High and Medium for people who chose that in the app (PUSH_MIN_SEVERITY sets the server default)."""
    default = os.environ.get("PUSH_MIN_SEVERITY", "high")
    rank = {"high": 2, "medium": 1, "info": 0}
    sent = 0
    subs = svc.store.list_push_subscriptions()
    if not subs:
        return 0
    watchers: dict[int, set[str]] = {}
    mins: dict[str, str] = {}
    for s in subs:
        if s["user"] not in mins:
            mins[s["user"]] = _min_severity(svc, s["user"], default)
            for imo in svc.store.get_watchlist(s["user"]):
                watchers.setdefault(imo, set()).add(s["user"])
    for al in alerts:
        for s in subs:
            if s["user"] not in watchers.get(al["imo"], set()):
                continue
            if rank.get(al["severity"], 0) < rank.get(mins.get(s["user"], default), 2):
                continue
            url = f"#/ship/{al['imo']}/finding/{al['key']}" if al.get("key") else f"#/ship/{al['imo']}"
            payload = {"title": al["title"], "body": al["body"], "url": url, "tag": f"{al['imo']}-{al.get('key') or al['rule']}"}
            try:
                if push.send(s["sub"], payload):
                    sent += 1
            except ValueError:            # subscription gone
                svc.store.remove_push_subscription(s["sub"]["endpoint"])
    return sent


def region(svc: Service | None = None) -> dict:
    svc = svc or Service()
    from app.service import REGIONS
    counts = {k: len(svc.live_rows(r["bbox"])) for k, r in REGIONS.items()}
    log.info("region %s", json.dumps(counts))
    return counts


def sweep(svc: Service | None = None, seconds: float = 240.0) -> dict:
    """Check ships in range that were never checked or were checked more than 6 hours ago (recorded data, free)."""
    svc = svc or Service()
    out = svc.sweep(budget_s=seconds)
    log.info("sweep %s", json.dumps(out))
    return out


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
    elif cmd == "sweep":
        print(json.dumps(sweep()))
    elif cmd == "prune-live":
        print(json.dumps(prune_live(full=("--all" in argv))))
    else:
        print(__doc__)
        return 2
    print(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
