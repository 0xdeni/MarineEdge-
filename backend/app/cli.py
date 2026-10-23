"""Command line for the pipeline. Works with any provider configured in .env.

  python -m app.cli search "hormuz"            step 1-2: candidates with IMO
  python -m app.cli pull 9000036               step 3-7: fetch (cached), analyse, print stats and flags
  python -m app.cli report 9000036 [--html]    step 8: PDF (or HTML) report to VVT_REPORT_DIR
  python -m app.cli region hormuz              live vessels in a region
  python -m app.cli fleet                      mock provider only: analyse the whole sample fleet
  python -m app.cli sanctions-refresh          OFAC + EU (+ UK with UK_SANCTIONS_CSV_URL, + OpenSanctions with --opensanctions)
  python -m app.cli first-pull 9000036 ...     the acceptance checklist from docs/PROVIDERS.md on real IMOs
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from app.service import Service, analysis_json

REGIONS = {"blacksea": (27.2, 40.6, 42.0, 47.4), "hormuz": (55.3, 25.3, 57.7, 27.5), "iran": (48.0, 24.4, 61.8, 31.0), "oman": (52.8, 16.0, 62.6, 26.9), "uae": (51.3, 23.6, 57.3, 26.6)}


def _svc() -> Service:
    return Service()


def cmd_search(a):
    for m in _svc().search(a.query):
        print(f"{m.imo}  {m.name:<24} {m.flag:<18} {m.sub or m.type:<28} {m.dwt:>8} dwt  built {m.built}")


def cmd_pull(a):
    svc = _svc()
    an = svc.analysis(a.imo, refresh=a.refresh)
    print(json.dumps(an.stats), json.dumps(an.sev))
    print(f"status: {an.status.state}  destination: {an.status.destination!r}")
    for vg in an.voyages[-a.voyages:]:
        print(f"  V{vg.n:<3} {vg.frm.port.name if vg.frm else 'history start':<22} → {vg.to.port.name if vg.to else '(underway)':<22} {vg.nm:>6} nm  draught {vg.draught_out}/{vg.draught_in}  dark {vg.dark_h:.0f} h  flags {len(vg.flags)}")
    for f in an.flags:
        print(f"  [{f.severity.upper():<6}] {f.title}" + (f"  (V{f.voyage.n})" if f.voyage else ""))
        for l in f.lines:
            print(f"           {l}")
    if a.json:
        out = f"analysis-{a.imo}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(analysis_json(an), fh)
        print("wrote", out)


def cmd_report(a):
    from app.reports.render import render_html, render_pdf
    svc = _svc()
    an = svc.analysis(a.imo)
    html = render_html(an)
    if a.html:
        out = f"report-{a.imo}.html"
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print("wrote", out)
    else:
        print("wrote", render_pdf(html, a.imo))


def cmd_region(a):
    svc = _svc()
    for row in svc.region(REGIONS[a.region]):
        v, p = row["vessel"], row["last"]
        print(f"{v['imo']}  {v['name']:<22} {p['sog']:>5} kn  {p['lat']:.3f},{p['lon']:.3f}")


def cmd_fleet(a):
    svc = _svc()
    if not hasattr(svc.provider, "fleet"):
        sys.exit("fleet is only available with VVT_PROVIDER=mock")
    svc.provider.generate_all()
    hi = 0
    for v in svc.provider.fleet:
        an = svc.analysis(v.imo)
        hi += 1 if an.sev["high"] else 0
        print(f"{v.imo}  {v.name:<20} voyages {len(an.voyages):>3}  flags {len(an.flags):>2}  high {an.sev['high']:>2}  {an.status.state}")
    print(f"{hi} of {len(svc.provider.fleet)} vessels with High flags")


def cmd_sanctions(a):
    from app.sanctions.loader import refresh_all
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("DATABASE_URL is required for sanctions refresh")
    print(json.dumps(refresh_all(dsn, uk_csv_url=os.environ.get("UK_SANCTIONS_CSV_URL"), include_opensanctions=a.opensanctions), indent=1))


def cmd_first_pull(a):
    """The acceptance checklist from docs/PROVIDERS.md, run on real IMOs the day a key arrives."""
    svc = _svc()
    print(f"provider: {getattr(svc.provider, 'name', '?')}")
    for imo in a.imos:
        try:
            an = svc.analysis(imo)
        except Exception as e:  # noqa: BLE001
            print(f"{imo}: FAILED {e}")
            continue
        s = an.stats
        checks = {
            "positions in the thousands (hourly fixes)": s["clean"] >= 1000,
            "draught populated": any(p.draught > 0 for p in an.track),
            "port calls found": s["port_calls"] >= 2,
            "voyages split": s["voyages"] >= 1,
            "cached (second read makes no provider call)": svc.store.covered(imo, svc._now() - int(svc.rules.history_months * 30.4 * 86_400_000), svc._now()),
        }
        print(f"{imo} {an.vessel.name}: {json.dumps(s)}")
        for k, ok in checks.items():
            print(f"   {'ok ' if ok else 'XX '} {k}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="marineedge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("pull"); s.add_argument("imo", type=int); s.add_argument("--refresh", action="store_true"); s.add_argument("--voyages", type=int, default=8); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_pull)
    s = sub.add_parser("report"); s.add_argument("imo", type=int); s.add_argument("--html", action="store_true"); s.set_defaults(fn=cmd_report)
    s = sub.add_parser("region"); s.add_argument("region", choices=list(REGIONS)); s.set_defaults(fn=cmd_region)
    s = sub.add_parser("fleet"); s.set_defaults(fn=cmd_fleet)
    s = sub.add_parser("sanctions-refresh"); s.add_argument("--opensanctions", action="store_true"); s.set_defaults(fn=cmd_sanctions)
    s = sub.add_parser("first-pull"); s.add_argument("imos", type=int, nargs="+"); s.set_defaults(fn=cmd_first_pull)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
