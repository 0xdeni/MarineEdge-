#!/usr/bin/env python3
"""Builds one self-contained HTML file of the PWA in mock mode (no server, no service worker, no manifest):
the shareable demo and the claude.ai artifact. Usage: python3 scripts/build_single.py [out.html]"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "frontend" / "public"
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "marineedge-demo.html"
html = (PUB / "index.html").read_text()
html = re.sub(r'<link rel="manifest"[^>]*>\n?', "", html)
html = re.sub(r'<link rel="apple-touch-icon"[^>]*>\n?', "", html)
html = html.replace('<link rel="stylesheet" href="./styles.css">', "<style>\n" + (PUB / "styles.css").read_text() + "\n</style>")
for name in ("geo.js", "base.js", "core.js", "api.js", "app.js"):
    js = (PUB / name).read_text().replace("</script", "<\\/script")
    html = html.replace(f'<script src="./{name}"></script>', f"<script>\n{js}\n</script>")
html = re.sub(r'<script>\s*if \("serviceWorker" in navigator\).*?</script>', "", html, flags=re.S)
html = html.replace('new URLSearchParams(location.search).get("source") || "mock"', '"mock"')
assert 'src="./' not in html, "unresolved local script"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html)
print(out, len(html.encode()), "bytes")
