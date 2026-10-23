"""Sanctions lists → the `sanctions` table (or an in-memory dict), keyed on IMO.

Sources (official downloads, all free):
  OFAC SDN   https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV
             vessels carry 'Vessel Registration Identification IMO 1234567' in the remarks column.
  EU         https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList/content?token=dG9rZW4tMjAxNw
             semicolon CSV; vessel rows carry the IMO in the identification columns.
  UK         https://assets.publishing.service.gov.uk/media/.../UK_Sanctions_List.csv  (link changes; see
             https://www.gov.uk/government/publications/the-uk-sanctions-list). Rows carry "IMO number: 1234567".
  OpenSanctions maritime CSV (aggregated; CC BY-NC 4.0, commercial licence for business use):
             https://data.opensanctions.org/datasets/latest/maritime/  (file: maritime.csv)

All parsers return the same row shape:
  {"list": "OFAC SDN"|"EU"|"UK"|"OpenSanctions", "imo": int, "name": str, "programme": str, "raw": any}
Run daily: scripts/refresh_sanctions.py (cron inside the API container or on the host)."""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import date
from typing import Iterable, Optional

import requests

log = logging.getLogger("marineedge.sanctions")
IMO_RE = re.compile(r"\bIMO(?:\s*(?:number|no\.?|nr\.?))?\s*[:#]?\s*(\d{7})\b", re.I)

OFAC_SDN = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
EU_CSV = "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList/content?token=dG9rZW4tMjAxNw"
UK_PAGE = "https://www.gov.uk/government/publications/the-uk-sanctions-list"
OPENSANCTIONS_CSV = "https://data.opensanctions.org/datasets/latest/maritime/maritime.csv"


def _imo(text: str) -> Optional[int]:
    m = IMO_RE.search(text or "")
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- OFAC
def parse_ofac_sdn(text: str) -> list[dict]:
    """SDN.CSV columns: ent_num, SDN_Name, SDN_Type, Program, Title, Call_Sign, Vess_type, Tonnage, GRT, Vess_flag, Vess_owner, Remarks"""
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 12 or row[2].strip().lower() != "vessel":
            continue
        imo = _imo(row[11])
        if imo is None:
            continue
        out.append({"list": "OFAC SDN", "imo": imo, "name": row[1].strip(), "programme": row[3].strip(), "flag": row[9].strip(), "raw": row})
    return out


# ---------------------------------------------------------------- EU
def parse_eu_csv(text: str) -> list[dict]:
    """EU consolidated list, semicolon-separated 'full' CSV. One row per name alias / identification; a vessel
    appears with Entity_SubjectType 'vessel' (or 'V') and its IMO in an Identification_* column or the remark."""
    out, seen = [], set()
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        subject = (row.get("Entity_SubjectType") or row.get("Entity_SubjectType_ClassificationCode") or "").strip().lower()
        blob = " ".join(f"{k}: {v}" for k, v in row.items() if v)
        imo = _imo(blob)
        if imo is None or (subject and subject not in ("vessel", "v", "ship")) and "vessel" not in blob.lower():
            continue
        if imo in seen:
            continue
        seen.add(imo)
        name = (row.get("NameAlias_WholeName") or row.get("Naal_WholeName") or "").strip()
        prog = (row.get("Entity_Regulation_Programme") or row.get("Entity_Regulation_NumberTitle") or "").strip()
        out.append({"list": "EU", "imo": imo, "name": name, "programme": prog, "raw": row})
    return out


# ---------------------------------------------------------------- UK
def parse_uk_csv(text: str) -> list[dict]:
    """OFSI / FCDO UK Sanctions List CSV. Columns vary between releases; we read by header name where present
    and fall back to scanning the row for 'IMO number: 1234567'."""
    out, seen = [], set()
    lines = text.splitlines()
    # the published CSV sometimes starts with a 'Last Updated' line before the header
    start = next((i for i, l in enumerate(lines) if "Name 6" in l or "Name6" in l or "Regime" in l or "Entity Type" in l), 0)
    for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        blob = " ".join(f"{k}: {v}" for k, v in row.items() if v)
        etype = (row.get("Entity Type") or row.get("Group Type") or "").strip().lower()
        imo = _imo(blob)
        if imo is None or (etype and etype not in ("ship", "vessel")):
            continue
        if imo in seen:
            continue
        seen.add(imo)
        name = (row.get("Name 6") or row.get("Name6") or row.get("Name") or row.get("Primary Name") or "").strip()
        prog = (row.get("Regime") or row.get("Regime Name") or "").strip()
        out.append({"list": "UK", "imo": imo, "name": name, "programme": prog, "raw": row})
    return out


# ---------------------------------------------------------------- OpenSanctions (aggregator)
def parse_opensanctions_csv(text: str) -> list[dict]:
    """maritime.csv column names are not fixed in their docs, so pick columns by name fragments:
    an 'imo' column, a name/caption column, a datasets/topics column and a sanction programme column if any."""
    out, seen = [], set()
    rd = csv.DictReader(io.StringIO(text))
    cols = rd.fieldnames or []
    col_imo = next((c for c in cols if "imo" in c.lower()), None)
    col_name = next((c for c in cols if c.lower() in ("caption", "name")), next((c for c in cols if "name" in c.lower()), None))
    col_ds = next((c for c in cols if "dataset" in c.lower()), None)
    col_topic = next((c for c in cols if "topic" in c.lower()), None)
    col_prog = next((c for c in cols if "program" in c.lower() or "authority" in c.lower()), None)
    for row in rd:
        raw_imo = (row.get(col_imo) or "") if col_imo else ""
        imo = None
        for part in re.split(r"[;,\s]+", raw_imo):
            if part.isdigit() and len(part) == 7:
                imo = int(part)
                break
        if imo is None:
            imo = _imo(" ".join(v for v in row.values() if v))
        if imo is None or imo in seen:
            continue
        topics = (row.get(col_topic) or "") if col_topic else ""
        if col_topic and topics and "sanction" not in topics.lower():
            continue   # vessels in the file for other reasons (e.g. port-state-control) are not sanctions hits
        seen.add(imo)
        out.append({"list": "OpenSanctions", "imo": imo, "name": (row.get(col_name) or "").strip() if col_name else "",
                    "programme": ((row.get(col_prog) or "") if col_prog else "") or ((row.get(col_ds) or "") if col_ds else ""), "raw": row})
    return out


# ---------------------------------------------------------------- fetchers
def fetch_ofac(session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(OFAC_SDN, timeout=120)
    r.raise_for_status()
    rows = parse_ofac_sdn(r.text)
    log.info("OFAC SDN: %d vessels with IMO", len(rows))
    return rows


def fetch_eu(session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(EU_CSV, timeout=120)
    r.raise_for_status()
    rows = parse_eu_csv(r.content.decode("utf-8-sig", errors="replace"))
    log.info("EU: %d vessels with IMO", len(rows))
    return rows


def fetch_uk(csv_url: str, session: requests.Session | None = None) -> list[dict]:
    """The UK CSV link changes with every publication; pass the current one (UK_SANCTIONS_CSV_URL in .env)."""
    s = session or requests.Session()
    r = s.get(csv_url, timeout=120)
    r.raise_for_status()
    rows = parse_uk_csv(r.content.decode("utf-8-sig", errors="replace"))
    log.info("UK: %d vessels with IMO", len(rows))
    return rows


def fetch_opensanctions(session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(OPENSANCTIONS_CSV, timeout=300, headers={"User-Agent": "MarineEdge/0.3 (sanctions refresh)"})
    r.raise_for_status()
    rows = parse_opensanctions_csv(r.content.decode("utf-8-sig", errors="replace"))
    log.info("OpenSanctions maritime: %d sanctioned vessels with IMO", len(rows))
    return rows


# ---------------------------------------------------------------- storage
def upsert(conn, rows: Iterable[dict], today: date | None = None) -> int:
    """Write into the sanctions table; entries missing from today's list get delisted_at set."""
    today = today or date.today()
    n = 0
    seen: dict[str, set[int]] = {}
    with conn.cursor() as cur:
        for r in rows:
            seen.setdefault(r["list"], set()).add(r["imo"])
            cur.execute("""INSERT INTO sanctions (list_name, imo, vessel_name, programme, listed_at, raw, refreshed_at)
                           VALUES (%s,%s,%s,%s,%s,%s, now())
                           ON CONFLICT (list_name, imo) DO UPDATE SET vessel_name=EXCLUDED.vessel_name, programme=EXCLUDED.programme, delisted_at=NULL, refreshed_at=now()""",
                        (r["list"], r["imo"], r.get("name"), r.get("programme"), today, json.dumps(r.get("raw"), default=str)))
            n += 1
        for lst, imos in seen.items():
            cur.execute("UPDATE sanctions SET delisted_at=%s WHERE list_name=%s AND delisted_at IS NULL AND NOT (imo = ANY(%s))", (today, lst, list(imos)))
    conn.commit()
    return n


def refresh_all(dsn: str, uk_csv_url: str | None = None, include_opensanctions: bool = False) -> dict:
    import psycopg  # type: ignore
    rows: list[dict] = []
    counts = {}
    for name, fn in [("OFAC SDN", fetch_ofac), ("EU", fetch_eu)]:
        try:
            got = fn()
            rows += got
            counts[name] = len(got)
        except Exception as e:  # one list failing must not block the others
            log.exception("%s refresh failed", name)
            counts[name] = f"failed: {e}"
    if uk_csv_url:
        try:
            got = fetch_uk(uk_csv_url)
            rows += got
            counts["UK"] = len(got)
        except Exception as e:
            log.exception("UK refresh failed")
            counts["UK"] = f"failed: {e}"
    if include_opensanctions:
        try:
            got = fetch_opensanctions()
            rows += got
            counts["OpenSanctions"] = len(got)
        except Exception as e:
            log.exception("OpenSanctions refresh failed")
            counts["OpenSanctions"] = f"failed: {e}"
    with psycopg.connect(dsn) as conn:
        n = upsert(conn, rows)
    counts["rows_written"] = n
    return counts
