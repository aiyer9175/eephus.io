"""SPOTRAC_POS_CODES_2026_10: Spotrac's numeric 'Pos' ids map to abbreviations,
and a FORMAT SENTINEL fails the contracts ingest loudly on a wrong-type cell.

From the refetch of 2026-10-03 the team contract pages serve a number in the
'Pos' column on some rows ("Jhoan Duran | 33 | 29"). The parser passed it
through, 242 veterans served pos '33', '32' and so on, and 128 pitcher cards
turned into hitter cards with nothing in the run saying so. The parser now
reads the ids through spotrac.SPOTRAC_POS_CODES (measured one to one on the 30
cached pages, see the table's comment) and reads anything else as None, and
run_monthly files the `spotrac_contracts_format` ingest row from
spotrac.contract_format_report.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import mlb_player_export
import proj_export
import run_monthly
import spotrac

ROOT = Path(__file__).resolve().parent

# The layout before 2026-10-03: abbreviations, a 2026 column.
OLD_LAYOUT = """
<table id="dataTable-active">
  <thead><tr><th>Player (3)</th><th>Pos</th><th>Age</th><th>2026</th><th>2027</th><th>2028</th></tr></thead>
  <tbody>
    <tr>
      <td data-export="Old Starter"><a href="https://www.spotrac.com/mlb/player/_/id/101/old-starter">Old Starter</a></td>
      <td data-export="SP">SP</td>
      <td data-export="31">31</td>
      <td data-export="20000000"><a>$20,000,000</a></td>
      <td data-export="20000000"><a>$20,000,000</a></td>
      <td data-export=" ">UFA</td>
    </tr>
    <tr>
      <td data-export="Old Reliever"><a href="https://www.spotrac.com/mlb/player/_/id/102/old-reliever">Old Reliever</a></td>
      <td data-export="RP">RP</td>
      <td data-export="28">28</td>
      <td data-export="1500000"><a>$1,500,000</a></td>
      <td data-export="0">ARB 2</td>
      <td data-export="0">ARB 3</td>
    </tr>
    <tr>
      <td data-export="Old Shortstop"><a href="https://www.spotrac.com/mlb/player/_/id/103/old-shortstop">Old Shortstop</a></td>
      <td data-export="SS">SS</td>
      <td data-export="26">26</td>
      <td data-export="800000"><a>$800,000</a></td>
      <td data-export="0">PRE-ARB</td>
      <td data-export=" "></td>
    </tr>
  </tbody>
</table>
"""

# The layout of 2026-10-03: numeric ids beside abbreviations, the 2026 column gone.
NEW_LAYOUT = """
<table id="dataTable-active">
  <thead><tr><th>Player (6)</th><th>Pos</th><th>Age</th><th>2027</th><th>2028</th><th>2029</th></tr></thead>
  <tbody>
    <tr>
      <td data-export="New Reliever"><a href="https://www.spotrac.com/mlb/player/_/id/201/new-reliever">New Reliever</a></td>
      <td class="text-center details-sm" data-export="33">33</td>
      <td class="text-center details-sm" data-export="29">29</td>
      <td data-export="0"><div class="pill pill-arbitration"><div class="pill-start">ARB 3</div></div></td>
      <td data-export=" "><div class="pill pill-ufa"><div class="pill-start">UFA</div></div></td>
      <td data-export=" "></td>
    </tr>
    <tr>
      <td data-export="New Starter"><a href="https://www.spotrac.com/mlb/player/_/id/202/new-starter">New Starter</a></td>
      <td data-export="32">32</td>
      <td data-export="30">30</td>
      <td data-export="15000000"><a>$15,000,000</a></td>
      <td data-export="15000000"><a>$15,000,000</a></td>
      <td data-export=" ">UFA</td>
    </tr>
    <tr>
      <td data-export="New Catcher"><a href="https://www.spotrac.com/mlb/player/_/id/203/new-catcher">New Catcher</a></td>
      <td data-export="34">34</td>
      <td data-export="27">27</td>
      <td data-export="900000"><a>$900,000</a></td>
      <td data-export=" "></td>
      <td data-export=" "></td>
    </tr>
    <tr>
      <td data-export="New Outfielder"><a href="https://www.spotrac.com/mlb/player/_/id/204/new-outfielder">New Outfielder</a></td>
      <td data-export="62">62</td>
      <td data-export="25">25</td>
      <td data-export="780000"><a>$780,000</a></td>
      <td data-export=" "></td>
      <td data-export=" "></td>
    </tr>
    <tr>
      <td data-export="Still Lettered"><a href="https://www.spotrac.com/mlb/player/_/id/205/still-lettered">Still Lettered</a></td>
      <td data-export="SP">SP</td>
      <td data-export="37">37</td>
      <td data-export="42000000"><a>$42,000,000</a></td>
      <td data-export=" ">UFA</td>
      <td data-export=" "></td>
    </tr>
    <tr>
      <td data-export="New Pitcher"><a href="https://www.spotrac.com/mlb/player/_/id/206/new-pitcher">New Pitcher</a></td>
      <td data-export="63">63</td>
      <td data-export="25">25</td>
      <td data-export="760000"><a>$760,000</a></td>
      <td data-export=" "></td>
      <td data-export=" "></td>
    </tr>
  </tbody>
</table>
"""


def _parse(html: str, audit: dict | None = None) -> dict:
    table = BeautifulSoup(html, "html.parser").find("table")
    rows = spotrac._parse_team_contract_table(table, "test-club", audit)
    return {r["player_name"]: r for r in rows}


def _with_cell(html: str, old: str, new: str) -> str:
    assert html.count(old) == 1, old
    return html.replace(old, new)


# ------------------------------------------------------------ the two layouts
def test_old_layout_parses_and_passes_the_sentinel():
    audit = spotrac._new_audit()
    rows = _parse(OLD_LAYOUT, audit)
    assert {n: r["position"] for n, r in rows.items()} == {
        "Old Starter": "SP", "Old Reliever": "RP", "Old Shortstop": "SS"}
    assert rows["Old Starter"]["salary_by_year"] == {2026: 20000000, 2027: 20000000}
    assert rows["Old Starter"]["signed_through"] == 2027
    assert rows["Old Reliever"]["status_by_year"] == {2027: "ARB 2", 2028: "ARB 3"}
    assert rows["Old Shortstop"]["salary_usd"] == 800000
    assert audit == {"rows": 3, "issues": [], "coded": []}


def test_new_layout_maps_the_numeric_ids_and_passes_the_sentinel():
    audit = spotrac._new_audit()
    rows = _parse(NEW_LAYOUT, audit)
    assert {n: r["position"] for n, r in rows.items()} == {
        "New Reliever": "RP", "New Starter": "SP", "New Catcher": "C",
        "New Outfielder": "OF", "Still Lettered": "SP", "New Pitcher": "P"}
    assert rows["New Reliever"]["status_by_year"] == {2027: "ARB 3", 2028: "UFA"}
    assert rows["New Starter"]["salary_by_year"] == {2027: 15000000, 2028: 15000000}
    assert rows["New Starter"]["current_year"] == 2027
    assert audit["issues"] == []
    assert audit["rows"] == 6
    assert [c[1] for c in audit["coded"]] == ["33", "32", "34", "62", "63"]


def test_every_mapped_abbreviation_is_a_position_every_consumer_reads():
    for code, abbr in spotrac.SPOTRAC_POS_CODES.items():
        assert code.isdigit()
        assert abbr in spotrac.SPOTRAC_POS_VOCAB
        assert proj_export._valid_pos(abbr), abbr
        pitcher = abbr in ("SP", "RP", "P")
        assert mlb_player_export._is_pitcher_pos(abbr) is pitcher, abbr
        assert proj_export._row_sides({"pos": abbr}) == (["pit"] if pitcher else ["hit"])


def test_resolve_position_kinds():
    assert spotrac._resolve_position("33") == ("RP", "code")
    assert spotrac._resolve_position(" 41 ") == ("RF", "code")
    assert spotrac._resolve_position("SP/DH") == ("SP/DH", "abbr")
    assert spotrac._resolve_position("ss") == ("ss", "abbr")
    assert spotrac._resolve_position("") == (None, "blank")
    assert spotrac._resolve_position(None) == (None, "blank")
    assert spotrac._resolve_position("77") == (None, "bad")
    assert spotrac._resolve_position("Pitcher") == (None, "bad")


# --------------------------------------------------------------- the sentinel
def test_sentinel_fires_on_an_unmapped_numeric_position():
    html = _with_cell(NEW_LAYOUT, '<td data-export="34">34</td>', '<td data-export="77">77</td>')
    audit = spotrac._new_audit()
    rows = _parse(html, audit)
    assert rows["New Catcher"]["position"] is None
    assert [(i["kind"], i["player"], i["value"]) for i in audit["issues"]] == [
        ("position", "New Catcher", "77")]
    rep = spotrac.contract_format_report(people=[], audits={"test-club": audit})
    assert rep["ok"] is False
    assert rep["by_kind"] == {"position": 1}


def test_sentinel_fires_on_a_wrong_type_age_and_money_cell():
    html = _with_cell(OLD_LAYOUT, '<td data-export="28">28</td>', '<td data-export="RP">RP</td>')
    html = _with_cell(html, '<td data-export="800000"><a>$800,000</a></td>',
                      '<td data-export="$800,000"><a>$800,000</a></td>')
    # digits under a cell that shows no dollar figure: a placeholder, not pay
    html = _with_cell(html, '<td data-export="1500000"><a>$1,500,000</a></td>',
                      '<td data-export="1500000">N/A</td>')
    audit = spotrac._new_audit()
    rows = _parse(html, audit)
    kinds = sorted((i["kind"], i["player"]) for i in audit["issues"])
    assert kinds == [("age", "Old Reliever"), ("money", "Old Reliever"),
                     ("money", "Old Shortstop")]
    assert 2026 not in rows["Old Shortstop"]["salary_by_year"]


def test_sentinel_fires_on_a_shifted_header():
    html = _with_cell(OLD_LAYOUT, "<th>Pos</th><th>Age</th>", "<th>Age</th><th>Pos</th>")
    audit = spotrac._new_audit()
    _parse(html, audit)
    assert {i["kind"] for i in audit["issues"]} >= {"header"}
    no_years = OLD_LAYOUT.replace("<th>2026</th><th>2027</th><th>2028</th>",
                                  "<th>Y1</th><th>Y2</th><th>Y3</th>")
    audit = spotrac._new_audit()
    assert _parse(no_years, audit) == {}
    assert [i["value"] for i in audit["issues"]] == ["no year columns"]


def test_side_check_catches_a_renumbered_code():
    audit = spotrac._new_audit()
    _parse(NEW_LAYOUT, audit)
    people_ok = [{"fullName": "New Reliever", "position": "P"},
                 {"fullName": "New Catcher", "position": "C"}]
    side = spotrac._code_side_check(audit["coded"], people_ok)
    assert (side["matched"], side["agree"], side["bad"]) == (2, 2, False)
    # 33 reused for shortstops: every coded "RP" meets a StatsAPI SS.
    coded = [(f"Player {i}", "33", "RP") for i in range(25)]
    people = [{"fullName": f"Player {i}", "position": "SS"} for i in range(25)]
    rep = spotrac.contract_format_report(
        people=people, audits={"c": {"rows": 25, "issues": [], "coded": coded}})
    assert rep["ok"] is False
    assert rep["by_kind"] == {"code_drift": 1}
    assert rep["side_check"]["share"] == 0.0


def test_report_is_red_when_no_page_was_parsed():
    assert spotrac.contract_format_report(people=[], audits={})["ok"] is False


def test_run_monthly_files_a_red_ingest_row(tmp_path, monkeypatch):
    bad = spotrac._new_audit()
    _parse(_with_cell(NEW_LAYOUT, '<td data-export="34">34</td>',
                      '<td data-export="77">77</td>'), bad)
    monkeypatch.setattr(spotrac, "_FORMAT_AUDIT", {"test-club": bad})
    monkeypatch.setattr(run_monthly, "_INGEST_HEALTH", [])
    monkeypatch.setattr(run_monthly, "_SPOTRAC_FORMAT_RED", False)
    rep = run_monthly._spotrac_format_sentinel(logging.getLogger("t"), "test")
    assert rep["ok"] is False
    assert run_monthly._SPOTRAC_FORMAT_RED is True
    assert "spotrac_contracts_format" in run_monthly.SCHEDULED_EXPORTS
    payload = run_monthly.write_ingest_health(tmp_path, "test", log=None)
    assert "spotrac_contracts_format" in payload["red"]
    row = [r for r in payload["sources"] if r["source"] == "spotrac_contracts_format"][0]
    assert row["kind"] == "export" and row["ok"] is False
    assert "position" in row["message"]


def test_run_monthly_files_a_green_row_on_clean_pages(tmp_path, monkeypatch):
    good = spotrac._new_audit()
    _parse(NEW_LAYOUT, good)
    monkeypatch.setattr(spotrac, "_FORMAT_AUDIT", {"test-club": good})
    monkeypatch.setattr(run_monthly, "_INGEST_HEALTH", [])
    monkeypatch.setattr(run_monthly, "_SPOTRAC_FORMAT_RED", False)
    import storage
    monkeypatch.setattr(storage, "record_source_check", lambda *a, **k: None)
    monkeypatch.setattr(spotrac, "CACHE_DIR", tmp_path)
    rep = run_monthly._spotrac_format_sentinel(logging.getLogger("t"), "test")
    assert rep["ok"] is True
    assert run_monthly._SPOTRAC_FORMAT_RED is False
    payload = run_monthly.write_ingest_health(tmp_path, "test", log=None)
    assert "spotrac_contracts_format" not in payload["red"]


# ---------------------------------------------------- the club-option cell
def test_tbd_club_option_year_is_a_status_not_a_zero_dollar_year():
    """2026-10-03 layout: an option year reads "TBD" over "CO" with
    data-export="0". Priced as money it was a $0 contract year (Ozzie Albies
    served aav $0); it is a status, and the sentinel stays quiet on it."""
    html = _with_cell(
        NEW_LAYOUT,
        '<td data-export="15000000"><a>$15,000,000</a></td>\n      <td data-export=" ">UFA</td>',
        '<td data-export="15000000"><a>$15,000,000</a></td>\n'
        '      <td data-export="0"><div class="pill pill-normal pill-mlb text-center pill-club">'
        '<div class="pill-start float-start text-center text-white">TBD</div>'
        '<div class="pill-end">CO</div></div></td>')
    audit = spotrac._new_audit()
    row = _parse(html, audit)["New Starter"]
    assert row["salary_by_year"] == {2027: 15000000, 2028: 15000000}
    assert row["status_by_year"] == {2029: "TBD CO"}
    assert row["signed_through"] == 2028
    assert row["aav_usd"] == 15000000
    assert audit["issues"] == []
    assert spotrac._year_cell_status("TBDCO") == "TBD CO"
    assert spotrac._year_cell_status("TBD") == "TBD"
    assert spotrac._year_cell_status("$0") is None


# ---------------------------------------------------------- the served pages
def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} not built")
    return json.loads(path.read_text(encoding="utf-8"))


def test_served_projections_carry_no_numeric_position():
    vets = _load(ROOT / "data" / "mlb_projections.json").get("vets") or []
    numeric = [(v.get("key"), v.get("pos")) for v in vets
               if str(v.get("pos") or "").strip().isdigit()]
    assert not numeric, f"{len(numeric)} vets serve a numeric pos: {numeric[:10]}"


def test_no_statsapi_pitcher_card_on_the_hitter_side():
    players = _load(ROOT / "data" / "mlb_player_detail.json").get("players") or {}
    index = _load(ROOT / ".cache" / "player_index.json").get("players") or []
    primary = {int(p["id"]): p.get("position") for p in index if p.get("id")}
    wrong = [(k, p.get("pos")) for k, p in players.items()
             if p.get("mlbam") and primary.get(int(p["mlbam"])) == "P"
             and not p.get("twoWay") and not p.get("isPit")]
    assert not wrong, f"{len(wrong)} StatsAPI pitchers on the hitter side: {wrong[:10]}"
