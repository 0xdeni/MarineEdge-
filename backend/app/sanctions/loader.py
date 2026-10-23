"""Sanctions lists → the `sanctions` table (or an in-memory dict), keyed on IMO.

Sources (all official downloads, all free):
  OFAC SDN   https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV
             + ADD.CSV; vessels carry 'Vessel Registration Identification IMO 1234567' in the remarks.
  EU         https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList/content?token=dG9rZW4tMjAxNw
             (CSV, 'Identification' rows with IMO numbers for vessels)
  UK         https://assets.publishing.service.gov.uk/.../UK_Sanctions_List.ods (or the OFSI consolidated CSV)
  OpenSanctions (aggregated, Vessel schema keyed on IMO): https://data.opensanctions.org/datasets/latest/maritime/
             – free for non-commercial use, commercial licence otherwise.

Run daily (scripts/refresh_sanctions.sh or a cron inside the API container)."""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date
from typing import Iterable

import requests

log = logging.getLogger("vvt.sanctions")
IMO_RE = re.compile(r"IMO\s*:?\s*(\d{7})", re.I)

OFAC_SDN = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
OFAC_ADD = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADD.CSV"


def parse_ofac_sdn(text: str) -> list[dict]:
    """Rows: ent_num, SDN_Name, SDN_Type, Program, Title, Call_Sign, Vess_type, Tonnage, GRT, Vess_flag, Vess_owner, Remarks"""
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 12 or row[2].strip().lower() != "vessel":
            continue
        m = IMO_RE.search(row[11] or "")
        if not m:
            continue
        out.append({"list": "OFAC SDN", "imo": int(m.group(1)), "name": row[1].strip(), "programme": row[3].strip(), "flag": row[9].strip(), "raw": row})
    return out


def fetch_ofac(session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(OFAC_SDN, timeout=120)
    r.raise_for_status()
    rows = parse_ofac_sdn(r.text)
    log.info("OFAC SDN: %d vessels with IMO", len(rows))
    return rows


def parse_eu_csv(text: str) -> list[dict]:
    """EU consolidated list CSV (semicolon separated). Vessel entries expose the IMO in the identification columns."""
    out = []
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        blob = " ".join(v or "" for v in row.values())
        m = IMO_RE.search(blob)
        if not m:
            continue
        out.append({"list": "EU", "imo": int(m.group(1)), "name": row.get("NameAlias_WholeName", "").strip(), "programme": row.get("Entity_Regulation_Programme", "").strip(), "raw": row})
    return out


def parse_uk_csv(text: str) -> list[dict]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        blob = " ".join(v or "" for v in row.values())
        m = IMO_RE.search(blob)
        if not m:
            continue
        out.append({"list": "UK", "imo": int(m.group(1)), "name": (row.get("Name 6") or row.get("Name") or "").strip(), "programme": (row.get("Regime") or "").strip(), "raw": row})
    return out


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
                        (r["list"], r["imo"], r.get("name"), r.get("programme"), today, __import__("json").dumps(r.get("raw"), default=str)))
            n += 1
        for lst, imos in seen.items():
            cur.execute("UPDATE sanctions SET delisted_at=%s WHERE list_name=%s AND delisted_at IS NULL AND NOT (imo = ANY(%s))", (today, lst, list(imos)))
    conn.commit()
    return n


def refresh_all(dsn: str) -> dict:
    import psycopg  # type: ignore
    rows = []
    rows += fetch_ofac()
    # EU and UK: add the download once the URLs are confirmed for your jurisdiction (see docs/PROVIDERS.md)
    with psycopg.connect(dsn) as conn:
        n = upsert(conn, rows)
    return {"rows": n}
