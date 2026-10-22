# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-12 (docs/efv-v2/DRIVER_SYSTEM_V2.md, bug B7): no scored row reads a
placeholder debut day.

THE DEFECT. With no PlayerIndex mlbDebutDate, stats.derive_roster_status fell back
to the first contract selection; for a November Rule 5 protection add that is not a
game date, and storage rolled it forward to a synthesized {first MLB season}-07-01.
The eFV training matrix read that day as the debut: 131 debuted rows took their
consensus input and MiLB cutoff at July 1 whatever the real day was (69 real debuts
were earlier, so post-debut reads leaked in; 61 were later).

THE FIX, pinned here:
  * derive_roster_status records the date's source; run_monthly asks /people/{id}
    for an offseason selection date before storage can roll it forward;
  * storage publishes debut_date_basis and debut_date_is_placeholder on graduates;
  * tools/redate_placeholder_debuts.py writes data/debut_redates.json from the
    StatsAPI people record, accepted only inside the first MLB season on file;
  * efv_dataset reads the real day where one exists and moves a day that is still
    a placeholder back to the season start, so the debut year (and the label)
    never moves.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import efv_dataset as E
import storage
from stats import derive_roster_status
from tools import redate_placeholder_debuts as R

ROOT = Path(__file__).parent
REDATES = ROOT / "data" / "debut_redates.json"


@pytest.fixture
def redates(monkeypatch):
    table = {"late_real": ("2022-07-01", "2022-08-19"),
             "early_real": ("2021-07-01", "2021-04-12"),
             "unresolved": ("2020-07-01", None),
             "wrong_year": ("2019-07-01", "2017-05-19")}
    monkeypatch.setattr(E, "_REDATES", table)
    return table


def test_a_placeholder_day_is_replaced_by_the_real_day(redates):
    assert E.resolved_debut_date({"player_key": "early_real",
                                  "debut_date": "2021-07-01"}) == ("2021-04-12", False,
                                                                   "2021-07-01")
    assert E.resolved_debut_date({"player_key": "late_real",
                                  "debut_date": "2022-07-01"})[0] == "2022-08-19"


def test_the_year_never_moves(redates):
    """A people date in another season is not applied: the label is keyed on the
    year and a different year means a different man or a data hole."""
    dd, ph, frm = E.resolved_debut_date({"player_key": "wrong_year",
                                         "debut_date": "2019-07-01"})
    assert dd == "2019-07-01" and ph is True and frm is None


def test_a_fixed_export_is_left_alone(redates):
    """Once debuts.json carries the real day, the map is a no-op."""
    assert E.resolved_debut_date({"player_key": "early_real",
                                  "debut_date": "2021-04-12"}) == ("2021-04-12", False, None)


def test_a_still_placeholder_day_reads_the_season_start(redates):
    assert E.debut_day_for_cutoff({"player_key": "unresolved",
                                   "debut_date": "2020-07-01"}) == ("2020-04-01", True, None)
    # the storage flag works without the map
    rec = {"player_key": "x", "debut_date": "2016-04-01",
           "debut_date_is_placeholder": True}
    assert E.debut_day_for_cutoff(rec) == ("2016-04-01", True, None)
    assert E.debut_day_for_cutoff({"player_key": "y", "debut_date": "2016-06-02"}) == (
        "2016-06-02", False, None)


def test_storage_names_the_placeholder_bases():
    assert storage.PLACEHOLDER_DEBUT_BASES == {"rule5_rollforward_placeholder",
                                               "opening_day_placeholder"}
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert 'payload["debut_date_is_placeholder"]' in src
    assert '"rule5_rollforward_placeholder")' in src


def test_roster_status_records_where_the_date_came_from():
    sel = [{"date": "2024-09-01", "type_code": "SE",
            "description": "Selected the contract of Player"}]
    career = [{"season": 2024, "level": "MLB", "is_pitcher": False, "ab": 50, "games": 18}]
    assert derive_roster_status(sel, career)["mlb_debut_date_source"] == "selection"
    assert derive_roster_status(sel, career, api_debut_date="2024-09-03")[
        "mlb_debut_date_source"] == "api"
    assert derive_roster_status(sel, [])["mlb_debut_date_source"] is None


def test_run_monthly_asks_people_for_an_offseason_selection():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    assert '_offseason_selection = (rs.get("mlb_debut_date_source") == "selection"' in src
    assert 'rs["mlb_debut_date_source"] = "api_people"' in src


def test_the_tool_accepts_only_a_people_date_in_the_first_season():
    rs = {"a": {"mlb_debut_date": "2019-11-20", "mlb_seasons": [2021, 2022]},
          "b": {"mlb_debut_date": "2019-11-20", "mlb_seasons": [2021]},
          "c": {"mlb_debut_date": "2020-11-20", "mlb_seasons": [2022]},
          "in_season": {"mlb_debut_date": "2019-06-02", "mlb_seasons": [2019]},
          "same_year": {"mlb_debut_date": "2019-11-20", "mlb_seasons": [2019]}}
    debuts = [{"player_key": "a", "mlbam_id": 1}, {"player_key": "b", "mlbam_id": 2}]
    cands = R.candidates(rs, debuts, {})
    assert [c["player_key"] for c in cands] == ["a", "b", "c"]
    assert cands[0]["placeholder_date"] == "2021-07-01"
    rows = R.resolve(cands, {1: {"mlbDebutDate": "2021-05-02", "fullName": "A"},
                             2: {"mlbDebutDate": "2018-05-02", "fullName": "B"}})
    assert rows["a"]["status"] == "redated" and rows["a"]["debut_date"] == "2021-05-02"
    assert rows["b"]["status"].startswith("unresolved") and rows["b"]["debut_date"] is None
    assert rows["c"]["status"] == "unresolved: no mlbam id"


def test_the_redate_map_holds_no_cross_season_date():
    if not REDATES.exists():
        pytest.skip("data/debut_redates.json not built")
    doc = json.loads(REDATES.read_text(encoding="utf-8"))
    assert doc["n_redated"] + doc["n_unresolved"] == doc["n_candidates"] == len(doc["rows"])
    for pk, r in doc["rows"].items():
        if r["status"] == "redated":
            assert r["debut_date"][:4] == str(r["first_mlb_season"]) == r["placeholder_date"][:4], pk
        else:
            assert r["debut_date"] is None, pk


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_no_matrix_row_reads_a_placeholder_day(side):
    """The served training matrix: every debuted row whose published day is a known
    placeholder carries the real day, and a row still flagged reads no later than
    the season start."""
    p = E.matrix_path(side)
    if not p.exists() or not REDATES.exists():
        pytest.skip("matrix or re-date map not built")
    rows = json.loads(p.read_text(encoding="utf-8"))
    red = json.loads(REDATES.read_text(encoding="utf-8"))["rows"]
    n_redated = 0
    for r in rows:
        if r.get("kind") != "debuted":
            continue
        assert "debut_date_is_placeholder" in r, "matrix predates DS-12: rebuild it"
        m = red.get(r["player_key"])
        if r.get("debut_date_redated_from"):
            n_redated += 1
            assert m and m["status"] == "redated"
            assert r["cutoff"] == m["debut_date"] and r["debut_date_redated_from"] == m["placeholder_date"]
        if m and m["status"] == "redated":
            # the real day, whether the map re-dated the row or the source already
            # carried it (the debut ledger has carried the real day since the MLB
            # events flip, so the map has no row left to move; PORT_RED_TESTS_TRIAGE)
            assert r["cutoff"] == m["debut_date"], (r["player_key"], r["cutoff"], m)
            n_redated += 1
        if r["debut_date_is_placeholder"]:
            assert r["cutoff"] <= f"{r['debut_year']}{E.SEASON_START_MMDD}"
    assert n_redated > 0, "no redated key is in the matrix; the map or the matrix is stale"
