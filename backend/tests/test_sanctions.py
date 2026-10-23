"""Parser tests on small fixtures shaped like the real downloads (no network)."""
from __future__ import annotations

from app.sanctions.loader import parse_eu_csv, parse_ofac_sdn, parse_opensanctions_csv, parse_uk_csv

OFAC = (
    '1,"EXAMPLE SHIP","vessel","IRAN-EO13902","-0-","3FAB","Crude Oil Tanker","-0-","12345","Panama","Example Co","Vessel Registration Identification IMO 9000036; Former Vessel Flag Gabon."\n'
    '2,"SOME PERSON","individual","SDGT","-0-","-0-","-0-","-0-","-0-","-0-","-0-","DOB 01 Jan 1970"\n'
    '3,"NO IMO SHIP","vessel","RUSSIA-EO14024","-0-","UBXY","Bulk Carrier","-0-","-0-","Russia","-0-","Linked To: SOMEONE."\n'
)

EU = (
    "FileGenerationDate;Entity_LogicalId;Entity_SubjectType;Entity_Regulation_Programme;NameAlias_WholeName;Identification_Number;Identification_TypeCode;Identification_Remark\n"
    "21/10/2026;100;vessel;UKR;SILVER REACH;9000019;IMO;Vessel IMO 9000019\n"
    "21/10/2026;100;vessel;UKR;SILVER REACH;;;Former name ORION LEGEND\n"
    "21/10/2026;101;person;SYR;JOHN DOE;;;passport 1234567\n"
    "21/10/2026;102;enterprise;IRN;SOME SHIPPING CO;;;IMO 5555555 company number\n"
)

UK = (
    "Last Updated,21/10/2026\n"
    "Name 6,Name 1,Regime,Entity Type,Other Information,Unique ID\n"
    "LEVANT STAR,,Syria,Ship,\"Type of ship: Product tanker. IMO number: 9000027. Flag: Cameroon\",SYR0001\n"
    "SOME PERSON,,Russia,Individual,DOB 1970,RUS0001\n"
    "KHALIJ MOON,,Iran,Ship,\"IMO number 9000046. Former flag Gabon\",IRN0002\n"
)

OS_CSV = (
    "id,schema,caption,imo_number,mmsi,flag,topics,datasets,first_seen,last_seen\n"
    "os-1,Vessel,HORMUZ QUEEN,9000036,626489894,ga,sanction,us_ofac_sdn;gb_hmt_sanctions,2026-02-11,2026-10-21\n"
    "os-2,Vessel,CLEAN SHIP,9000001,,mt,poi,ext_tokyo_mou,2025-01-01,2026-10-21\n"
    "os-3,Vessel,DOUBLE IMO,9000013;9000014,,pa,sanction.linked,eu_fsf,2026-03-01,2026-10-21\n"
)


def test_ofac_vessels_with_imo_only():
    rows = parse_ofac_sdn(OFAC)
    assert [r["imo"] for r in rows] == [9000036]
    assert rows[0]["list"] == "OFAC SDN" and rows[0]["programme"] == "IRAN-EO13902" and rows[0]["name"] == "EXAMPLE SHIP"


def test_eu_vessel_rows_deduplicated_and_non_vessels_skipped():
    rows = parse_eu_csv(EU)
    assert [(r["imo"], r["name"], r["programme"]) for r in rows] == [(9000019, "SILVER REACH", "UKR")]


def test_uk_ships_parsed_from_free_text():
    rows = parse_uk_csv(UK)
    assert sorted(r["imo"] for r in rows) == [9000027, 9000046]
    assert {r["imo"]: r["programme"] for r in rows} == {9000027: "Syria", 9000046: "Iran"}


def test_opensanctions_sanction_topic_only():
    rows = parse_opensanctions_csv(OS_CSV)
    assert sorted(r["imo"] for r in rows) == [9000013, 9000036]       # first IMO of a double entry; the port-state-control row is skipped
    hq = next(r for r in rows if r["imo"] == 9000036)
    assert hq["list"] == "OpenSanctions" and hq["name"] == "HORMUZ QUEEN" and "ofac" in hq["programme"]
