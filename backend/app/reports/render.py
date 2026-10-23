"""Step 8: the vessel report. Jinja2 HTML (same content as the PWA's report screen) printed to PDF
with Playwright's Chromium. render_html() is pure; render_pdf() needs `playwright install chromium`."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.engine.geo import fmt_dm
from app.engine.rules import fmt_dt, fmt_dur, fmt_dy
from app.engine.types import Analysis

TEMPLATES = Path(__file__).parent / "templates"
OUT_DIR = Path(os.environ.get("VVT_REPORT_DIR", "/tmp/marineedge-reports"))
env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
env.filters["dt"] = fmt_dt
env.filters["dy"] = fmt_dy
env.filters["dur"] = fmt_dur
env.filters["dm"] = lambda p: fmt_dm(p.lat, p.lon)
env.filters["n"] = lambda x: f"{x:,}"


def svg_chart(a: Analysis, w: int = 720, h: int = 440) -> str:
    """Minimal chart: voyages as polylines in a Mercator box, flags as dots. The production report
    swaps this for a MapLibre static render; this keeps the PDF self-contained."""
    import math
    pts = [p for p in a.track if not p.jump]
    if not pts:
        return ""
    my = lambda lat: math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))
    lon0, lon1 = min(p.lon for p in pts) - 0.3, max(p.lon for p in pts) + 0.3
    y0, y1 = my(min(p.lat for p in pts) - 0.2), my(max(p.lat for p in pts) + 0.2)
    s = min(w / (lon1 - lon0), h / (y1 - y0))
    P = lambda lon, lat: (round((lon - lon0) * s + (w - (lon1 - lon0) * s) / 2, 1), round((y1 - my(lat)) * s + (h - (y1 - y0) * s) / 2, 1))
    cols = ["#2A68C9", "#C2399A", "#1E9A8B", "#7B4FD1", "#BE7410", "#3C9638", "#D04A66", "#4F6B8A"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}"><rect width="{w}" height="{h}" fill="#D8E6ED"/>']
    for vg in a.voyages:
        seg = [P(p.lon, p.lat) for p in a.track[vg.i0:vg.i1 + 1] if not p.jump]
        if len(seg) < 2:
            continue
        dash = ' stroke-dasharray="8 6"' if vg.current else ""
        out.append(f'<polyline fill="none" stroke="{cols[vg.color]}" stroke-width="2"{dash} points="{" ".join(f"{x},{y}" for x, y in seg)}"/>')
    for f in a.flags:
        if f.vessel_level or f.lat is None:
            continue
        x, y = P(f.lon, f.lat)
        col = {"high": "#C62828", "medium": "#B86E00", "info": "#2C6CB0"}[f.severity]
        out.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{col}" stroke="#fff" stroke-width="1.5"/>')
    seen = set()
    for pc in a.port_calls:
        if pc.port.id in seen:
            continue
        seen.add(pc.port.id)
        x, y = P(pc.port.lon, pc.port.lat)
        out.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#18222E"/><text x="{x + 6}" y="{y - 3}" font-size="10" font-family="sans-serif" fill="#4A5D6D">{pc.port.name}</text>')
    x, y = P(pts[-1].lon, pts[-1].lat)
    out.append(f'<circle cx="{x}" cy="{y}" r="7" fill="#0B5FA5" stroke="#fff" stroke-width="2"/></svg>')
    return "".join(out)


def render_html(a: Analysis, notes: list[dict] | None = None) -> str:
    tpl = env.get_template("report.html")
    return tpl.render(a=a, v=a.vessel, generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), chart=svg_chart(a), notes=notes or [])


def render_pdf(html: str, imo: int) -> Path:
    from playwright.sync_api import sync_playwright  # type: ignore
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"vvt-{imo}-{int(datetime.now().timestamp())}.pdf"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(html, wait_until="load")
        pg.pdf(path=str(path), format="A4", print_background=True, margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
        b.close()
    return path
