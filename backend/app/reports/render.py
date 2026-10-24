"""Step 8: the vessel report. Jinja2 HTML with the same content as the app's ship page (verdict, what happened,
voyages, identity and sanctions, team notes), printed to PDF with Playwright's Chromium.
render_html() is pure; render_pdf() needs `playwright install chromium` (the API image has it)."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.engine.geo import fmt_dm
from app.engine.rules import fmt_dt, fmt_dur, fmt_dy
from app.engine.types import Analysis

TEMPLATES = Path(__file__).parent / "templates"
LAND = Path(__file__).resolve().parents[1] / "data" / "land.json"
OUT_DIR = Path(os.environ.get("VVT_REPORT_DIR", "/tmp/marineedge-reports"))
env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
env.filters["dt"] = fmt_dt
env.filters["dy"] = fmt_dy
env.filters["dur"] = fmt_dur
env.filters["dm"] = lambda p: fmt_dm(p.lat, p.lon)
env.filters["n"] = lambda x: f"{x:,}"

VOY = ["#1F6FD1", "#5B4FD6", "#A23FC9", "#0F8FA6", "#2F7CF0", "#138A80", "#7059E8", "#2C8FC9"]
SEV = {"high": "#D7261E", "medium": "#C46A00", "info": "#7A8794"}
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _day_range(t0: int, t1: Optional[int]) -> str:
    a = datetime.fromtimestamp(t0 / 1000, timezone.utc)
    if not t1 or abs(t1 - t0) < 12 * 3_600_000 and a.date() == datetime.fromtimestamp(t1 / 1000, timezone.utc).date():
        return f"{a.day} {MON[a.month - 1]} {a.year}"
    b = datetime.fromtimestamp(t1 / 1000, timezone.utc)
    if a.year == b.year and a.month == b.month:
        return f"{a.day} – {b.day} {MON[b.month - 1]} {b.year}"
    if a.year == b.year:
        return f"{a.day} {MON[a.month - 1]} – {b.day} {MON[b.month - 1]} {b.year}"
    return f"{a.day} {MON[a.month - 1]} {a.year} – {b.day} {MON[b.month - 1]} {b.year}"


env.filters["range"] = lambda f: _day_range(f.t0, f.t1)


@lru_cache(maxsize=1)
def _land() -> list[dict]:
    try:
        return json.loads(LAND.read_text(encoding="utf-8"))["rings"]
    except (OSError, ValueError, KeyError):
        return []


def _lists_text(lists: list[str]) -> str:
    order = ["OFAC SDN", "EU", "UK"]
    names = [x for x in order if x in lists] + [x for x in lists if x not in order]
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def svg_chart(a: Analysis, ref=None, w: int = 720, h: int = 400) -> str:
    """The year on a chart: Natural Earth coastlines, sensitive zones, one colour per voyage (the current one
    dashed), port calls, findings numbered as in the list below it, and the ship now."""
    pts = [p for p in a.track if not p.jump]
    if not pts:
        return ""
    my = lambda lat: math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))
    lons = [p.lon for p in pts] + [pc.port.lon for pc in a.port_calls]
    lats = [p.lat for p in pts] + [pc.port.lat for pc in a.port_calls]
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    padx, pady = max(0.6, (lon1 - lon0) * 0.08), max(0.4, (lat1 - lat0) * 0.1)
    lon0, lon1, lat0, lat1 = lon0 - padx, lon1 + padx, lat0 - pady, lat1 + pady
    y0, y1 = my(lat0), my(lat1)
    s = min(w / (lon1 - lon0), h / (y1 - y0))
    ox, oy = (w - (lon1 - lon0) * s) / 2, (h - (y1 - y0) * s) / 2
    P = lambda lon, lat: (round((lon - lon0) * s + ox, 1), round((y1 - my(max(-85, min(85, lat)))) * s + oy, 1))
    # what the frame really covers once centred
    vlon0, vlon1 = lon0 - ox / s, lon1 + ox / s
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="Helvetica, Arial, sans-serif">',
           '<defs><pattern id="hz" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="#D7261E" stroke-width="1.4" stroke-opacity="0.45"/></pattern>'
           f'<clipPath id="cp"><rect width="{w}" height="{h}" rx="10"/></clipPath></defs><g clip-path="url(#cp)">',
           f'<rect width="{w}" height="{h}" fill="#DCE8F1"/>']
    land = []
    for ring in _land():
        r = ring["r"]
        if max(x for x, _ in r) < vlon0 - 1 or min(x for x, _ in r) > vlon1 + 1 or max(y for _, y in r) < lat0 - 3 or min(y for _, y in r) > lat1 + 3:
            continue
        d = "M" + "L".join(f"{x},{y}" for x, y in (P(lo, la) for lo, la in r)) + "Z"
        land.append(f'<path d="{d}" fill="{"#DCE8F1" if ring.get("h") else "#F3F1EC"}" stroke="#AFBFCD" stroke-width="0.7"/>')
    out += land
    if ref is not None:
        for z in getattr(ref, "zones", []):
            if not z.enabled or not z.poly:
                continue
            d = "M" + "L".join(f"{x},{y}" for x, y in (P(lo, la) for lo, la in z.poly)) + "Z"
            out.append(f'<path d="{d}" fill="url(#hz)" stroke="#D7261E" stroke-opacity="0.6" stroke-width="1" stroke-dasharray="4 3"/>')
    for vg in a.voyages:
        seg = [P(p.lon, p.lat) for p in a.track[vg.i0:vg.i1 + 1] if not p.jump]
        if len(seg) < 2:
            continue
        dash = ' stroke-dasharray="7 5"' if vg.current else ""
        out.append(f'<polyline fill="none" stroke="{VOY[vg.color % 8]}" stroke-width="1.7" stroke-opacity="0.92" stroke-linejoin="round" stroke-linecap="round"{dash} '
                   f'points="{" ".join(f"{x},{y}" for x, y in seg)}"/>')
    seen: set[str] = set()
    calls: dict[str, int] = {}
    for pc in a.port_calls:
        calls[pc.port.id] = calls.get(pc.port.id, 0) + 1
    placed: list[tuple[float, float, float]] = []      # label boxes already drawn (x, y, width): busy ports first, no overlaps
    for pc in sorted(a.port_calls, key=lambda pc: (not pc.port.zone, -calls[pc.port.id])):
        if pc.port.id in seen or pc.port.pseudo:
            continue
        seen.add(pc.port.id)
        x, y = P(pc.port.lon, pc.port.lat)
        col = "#D7261E" if pc.port.zone else "#1B2733"
        out.append(f'<circle cx="{x}" cy="{y}" r="2.8" fill="#fff" stroke="{col}" stroke-width="1.4"/>')
        wl = 5.6 * len(pc.port.name)
        if any(abs(x - px) < max(wl, pw) * 0.9 and abs(y - py) < 12 for px, py, pw in placed):
            continue
        placed.append((x, y, wl))
        out.append(f'<text x="{x + 5}" y="{y - 4}" font-size="9.5" fill="#3E4C5A" paint-order="stroke" stroke="#F3F1EC" stroke-width="2.5">{_esc(pc.port.name)}</text>')
    for f in sorted([f for f in a.flags if f.severity != "info" and f.lat is not None and not f.vessel_level], key=lambda f: f.t0):
        x, y = P(f.lon, f.lat)
        out.append(f'<circle cx="{x}" cy="{y}" r="7.5" fill="{SEV[f.severity]}" stroke="#fff" stroke-width="1.6"/>'
                   f'<text x="{x}" y="{y + 3.2}" font-size="8.5" font-weight="700" fill="#fff" text-anchor="middle">{_flag_no(a, f)}</text>')
    x, y = P(pts[-1].lon, pts[-1].lat)
    out.append(f'<circle cx="{x}" cy="{y}" r="9" fill="#1F6FD1" fill-opacity="0.18"/><circle cx="{x}" cy="{y}" r="5" fill="#1F6FD1" stroke="#fff" stroke-width="2"/>')
    out.append(f'<text x="{w - 8}" y="{h - 8}" font-size="8" fill="#6B7A88" text-anchor="end">Coastlines: Natural Earth</text></g></svg>')
    return "".join(out)


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _flag_no(a: Analysis, f) -> int:
    """The number a finding has in the report's list (chronological, counted findings only)."""
    order = sorted([x for x in a.flags if x.severity != "info"], key=lambda x: x.t0)
    return next((i for i, x in enumerate(order, 1) if x is f), 0)


def _voyage_name(vg) -> str:
    return f"{vg.frm.port.name if vg.frm else 'At sea'} → {vg.to.port.name if vg.to else 'at sea'}"


def _evidence(f) -> list[dict[str, Any]]:
    before, after = list(f.evidence_before or []), list(f.evidence_after or [])
    mark = set()
    if f.rule in ("AIS gap", "Draught change at sea"):
        if before:
            mark.add(len(before) - 1)
        if after:
            mark.add(len(before))
    elif f.rule == "Position jump" and after:
        mark.add(len(before))
    return [{"t": fmt_dt(p.t), "pos": fmt_dm(p.lat, p.lon), "sog": f"{p.sog:.1f} kn" if p.sog is not None else "—",
             "draught": f"{p.draught:.1f} m" if p.draught else "—", "mark": i in mark} for i, p in enumerate(before + after)]


def render_html(a: Analysis, notes: list[dict] | None = None, ref=None, lists: Optional[list[str]] = None, checked_at: Optional[int] = None,
                rules: Optional[dict] = None) -> str:
    from app import verdict as verdict_mod
    lists = list(lists) if lists is not None else ["OFAC SDN", "EU", "UK"]
    vd = a.verdict or verdict_mod.build(a, sanctions_checked=bool(lists), lists=lists)
    counted = sorted([f for f in a.flags if f.severity != "info"], key=lambda f: f.t0)
    info = sorted([f for f in a.flags if f.severity == "info"], key=lambda f: f.t0)

    def item(f, no):
        st = verdict_mod.story(f, a, ref)
        return {"no": no, "severity": f.severity, "color": SEV[f.severity], "rule": f.rule, "when": _day_range(f.t0, f.t1), "title": st["title"], "text": st["text"],
                "voyage": _voyage_name(f.voyage) if f.voyage else None, "lines": f.lines, "evidence": _evidence(f), "draught": f.rule == "Draught change at sea"}

    findings = [item(f, i) for i, f in enumerate(counted, 1)]
    quiet = [item(f, 0) for f in info]
    scope_name: dict[str, str] = {f"voyage:{vg.n}": f"On the voyage {_voyage_name(vg)}" for vg in a.voyages}
    scope_name.update({f"flag:{f.key}": f"On the finding “{verdict_mod.story(f, a, ref)['title']}”" for f in a.flags})
    note_rows = [{"author": n.get("author") or "Former member", "when": fmt_dy(n.get("updated_at") or n.get("created_at") or 0), "text": n.get("text", ""),
                  "ctx": scope_name.get(n.get("scope", ""), "") if n.get("scope") != "ship" else ""} for n in (notes or [])]
    voyages = [{"n": vg.n, "name": _voyage_name(vg), "color": VOY[vg.color % 8], "depart": fmt_dt(vg.depart), "arrive": fmt_dt(vg.arrive) if vg.arrive else "under way",
                "nm": f"{vg.nm:,}", "draught": f"{vg.draught_out:.1f} → {vg.draught_in:.1f}" if vg.draught_out else "—", "dark": f"{round(vg.dark_h)} h" if vg.dark_h else "—",
                "flags": sum(1 for x in vg.flags if x.severity != "info"), "current": vg.current} for vg in reversed(a.voyages)]
    v = a.vessel
    hist = sorted(v.history or [], key=lambda h: -h.get("t", 0))
    last = {fld: next((h for h in hist if h.get("field") == fld), None) for fld in ("name", "flag", "mmsi")}
    sanc = {"listed": [{"list": x["list"], "programme": x.get("programme", ""), "t": fmt_dy(x["t"]) if x.get("t") else ""} for x in (v.sanctions or [])],
            "lists": _lists_text(lists) if lists else "", "checked": fmt_dt(checked_at) + " UTC" if checked_at else None}
    days = vd.get("historyDays") or 0
    src = (a.stats or {}).get("source") or ""
    tpl = env.get_template("report.html")
    return tpl.render(a=a, v=v, vd=vd, findings=findings, quiet=quiet, notes=note_rows, voyages=voyages, chart=svg_chart(a, ref), last=last, sanc=sanc,
                      generated=datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC"), positions=f"{len(a.track):,}",
                      history_from=fmt_dy(a.track[0].t) if a.track else None, days=round(days), source=src,
                      recorded="aisstream" in src.lower(), history_since=fmt_dy(a.stats["history_since"]) if (a.stats or {}).get("history_since") else None,
                      R=_rules_view(rules))


def _rules_view(rules: Optional[dict]) -> dict:
    """The thresholds the footer quotes: the server's own (rules.yaml plus admin changes), never hard-coded."""
    if rules is None:
        from app.engine import load_rules
        rules = load_rules()
    g = lambda grp, k: (rules.get(grp) or {}).get(k) if isinstance(rules, dict) else getattr(getattr(rules, grp), k)
    fmt = lambda x: f"{x:g}" if isinstance(x, (int, float)) else str(x)
    return {"pc_h": fmt(g("port_call", "min_hours")), "pc_kn": fmt(g("port_call", "max_speed_kn")), "gap_h": fmt(g("ais_gap", "min_hours")),
            "gap_high": fmt(g("ais_gap", "high_hours")), "gap_nm": fmt(g("ais_gap", "near_sensitive_nm")), "dr_m": fmt(g("draught_change", "min_meters")),
            "sts_h": fmt(g("sts", "min_hours")), "sts_m": fmt(g("sts", "max_dist_m")), "sts_kn": fmt(g("sts", "max_speed_kn")), "jump_kn": fmt(g("position_jump", "max_implied_kn"))}


def render_pdf(html: str, imo: int) -> Path:
    from playwright.sync_api import sync_playwright  # type: ignore
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"vvt-{imo}-{int(datetime.now().timestamp())}.pdf"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(html, wait_until="load")
        pg.pdf(path=str(path), format="A4", print_background=True, margin={"top": "14mm", "bottom": "16mm", "left": "13mm", "right": "13mm"},
               display_header_footer=True, header_template="<span></span>",
               footer_template='<div style="font:7pt Helvetica,Arial,sans-serif;color:#7A8794;width:100%;padding:0 13mm;display:flex;justify-content:space-between">'
                               '<span>MarineEdge vessel report</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
        b.close()
    return path
