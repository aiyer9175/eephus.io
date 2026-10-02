# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A CollegeSavant line attaches to the draft record it belongs to (census M03-06).

college_translation._draft_keys took the first draft_players row by name, so
75 of 505 PROSPX bridge keys sat on a prep-year record (Caglianone's 2021
record instead of his 2024 college one), 14 Draft Prospects rows lost the link
to their own tracked page and 9 hitter pages lost the college box panel. The
resolver now takes the earliest record of draft year >= the college season,
never a record typed or named as a high school.

The unit tests drive resolve_draft_keys and _draft_index on fixtures; the
artifact tests read the SERVED data/collegesavant_* files.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import college_translation as ct

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def _js(name: str) -> dict:
    text = (DATA / name).read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):text.rstrip().rstrip(";").rindex("}") + 1])


def _bridge() -> dict:
    return json.loads((DATA / "collegesavant_milb_equiv.json").read_text(encoding="utf-8"))["by_player_key"]


def _key_year(pk: str) -> int:
    return int(re.match(r"draft_(\d{4})_", pk).group(1))


def _index(rows):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE draft_players (player_key TEXT, player_name TEXT, "
                "draft_year INTEGER, school TEXT, player_type TEXT)")
    con.executemany("INSERT INTO draft_players VALUES (?,?,?,?,?)", rows)
    return ct._draft_index(con)


def test_caglianone_resolves_to_his_college_record():
    idx = _index([
        ("draft_2021_jac_caglianone", "Jac Caglianone", 2021, "Florida", "COLh"),
        ("draft_2024_jac_caglianone", "Jac Caglianone", 2024, "Florida", "COLh"),
    ])
    assert ct.resolve_draft_keys(idx, "jac caglianone", 2024) == ["draft_2024_jac_caglianone"]


def test_redrafted_player_at_the_same_school_carries_both_keys():
    idx = _index([
        ("draft_2025_tre_phelps", "Tre Phelps", 2025, "Georgia", "COLh"),
        ("draft_2026_tre_phelps", "Tre Phelps", 2026, "Georgia", "COLh"),
    ])
    assert ct.resolve_draft_keys(idx, "tre phelps", 2025) == [
        "draft_2025_tre_phelps", "draft_2026_tre_phelps"]


def test_high_school_records_never_resolve():
    idx = _index([
        ("draft_2028_alex_rodriguez", "Alex Rodriguez", 2028, "Plant City (Fla.) HS", "HSh"),
        ("draft_2026_logan_schmidt", "Logan Schmidt", 2026, "Ganesha HS (CA)", "COLp"),
    ])
    assert ct.resolve_draft_keys(idx, "alex rodriguez", 2024) == []
    assert ct.resolve_draft_keys(idx, "logan schmidt", 2025) == []


def test_same_class_namesakes_break_on_the_team_school():
    idx = _index([
        ("draft_2025_jared_jones", "Jared Jones", 2025, "LSU", "COLh"),
        ("draft_2025_jared_jones_2", "Jared Jones", 2025, "Texas Tech", "COLh"),
    ])
    assert ct.resolve_draft_keys(idx, "jared jones", 2025, "Texas Tech")[0] == "draft_2025_jared_jones_2"
    assert ct.resolve_draft_keys(idx, "jared jones", 2025, "LSU")[0] == "draft_2025_jared_jones"


def test_served_bridge_never_sits_on_an_earlier_or_prep_record():
    br = _bridge()
    assert br
    # The CollegeSavant season each name's line comes from.
    years: dict[str, int] = {}
    for v in list(ct.load_cs_hitters().values()) + list(ct.load_cs_pitchers().values()):
        k = ct.norm_name(v["name"])
        years[k] = min(years.get(k, 9999), int(v["year"]))
    ts = {}
    for c in json.loads((DATA / "draft_timeseries.json").read_text(encoding="utf-8"))["classes"]:
        for p in c.get("prospects", []):
            ts[p["player_key"]] = p
    early = [k for k, e in br.items() if _key_year(k) < years.get(ct.norm_name(e["name"]), 0)]
    assert not early, early[:5]
    # Served player_type only: the served draft_timeseries still prints a prep
    # school on two college records the store has since corrected (O'Ferrall,
    # Virginia; Neville, Oregon), so its school string is not the referee here.
    prep = [k for k in br if (ts.get(k, {}).get("player_type") or "").startswith("HS")]
    assert not prep, prep[:5]
    assert "draft_2024_jac_caglianone" in br and "draft_2021_jac_caglianone" not in br
    assert "draft_2026_roch_cholowsky" in br and "draft_2023_roch_cholowsky" not in br


def test_served_tracked_pages_get_their_box_and_board_link():
    T = _js("collegesavant_translation.js")["translations"]
    assert T["cholowsky-roch"].get("box")
    P = _js("collegesavant_draft_prospects.js")
    row = next(x for x in P["hitters"] if x["name"] == "Roch Cholowsky" and x["year"] == 2026)
    assert row.get("cs", {}).get("slug") == "cholowsky-roch"
