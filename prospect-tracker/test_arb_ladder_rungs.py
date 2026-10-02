# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The arbitration ladder prices the seasons that remain, and every one of them.

Two served-number defects from the 2026-10-01 reconciliation audit:

  RML01  Spotrac renders its OWN arbitration estimate for an unset season as a
         dollar pill with the class pill-estimate ("$10,500,000 ARB" for Jarren
         Duran's 2027). spotrac.py read it as signed salary, the 2027 ARB token
         was lost, and /arbitration/ never priced the rung: 16 of 30 clubs had
         no priced 2027 arbitration rung and the Club Ledger's arbitration
         block and Cost+ arbitration part read $0 for 14 of them.
  RVA01  A status token for a season already played (2026 PRE-ARB) became a
         ladder rung, so the Club Ledger's remaining arbitration figure carried
         a completed season's league minimum (LAD, CIN, MIN).

The served assertions are invariants, not dollars: the dollars move with every
nightly, the invariants do not.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import arb_export as X
import spotrac as S

ROOT = Path(__file__).parent


def _doc(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"data/{name} not built")
    return json.loads(p.read_text("utf-8"))


# ------------------------------------------------------------- the parser
ESTIMATE_FIXTURE = """
<table id="dataTable-active">
  <thead><tr><th>Player</th><th>Pos</th><th>2026</th><th>2027</th><th>2028</th></tr></thead>
  <tbody>
    <tr>
      <td data-export="Estimate Before Arb Three"><a href="/mlb/player/_/id/1/x">E</a></td>
      <td data-export="SP">SP</td>
      <td data-export="7775000"><a><div class='pill pill-normal pill-mlb text-center '><div class='pill-start'>$7,775,000</div><div class='pill-end'>3.2%</div></div></a></td>
      <td data-export="10500000"><a><div class='pill pill-normal pill-mlb text-center pill-estimate'><div class='pill-start'>$10,500,000</div><div class='pill-end'>ARB</div></div></a></td>
      <td data-export="0">ARB 3</td>
    </tr>
    <tr>
      <td data-export="Estimate Final Year"><a href="/mlb/player/_/id/2/y">F</a></td>
      <td data-export="RF">RF</td>
      <td data-export="1544125"><a><div class='pill pill-normal pill-mlb text-center'><div class='pill-start'>$1,544,125</div><div class='pill-end'>0.6%</div></div></a></td>
      <td data-export="5400000"><a><div class='pill pill-normal pill-mlb text-center pill-estimate'><div class='pill-start'>$5,400,000</div><div class='pill-end'>ARB</div></div></a></td>
      <td data-export=" ">UFA</td>
    </tr>
    <tr>
      <td data-export="Estimate Super Two"><a href="/mlb/player/_/id/3/z">G</a></td>
      <td data-export="SP">SP</td>
      <td data-export="900000"><a><div class='pill pill-normal pill-mlb text-center'><div class='pill-start'>$900,000</div></div></a></td>
      <td data-export="900000"><a><div class='pill pill-normal pill-mlb text-center pill-estimate'><div class='pill-start'>$900,000</div><div class='pill-end'>ARB</div></div></a></td>
      <td data-export="0">ARB 3 (S2)</td>
    </tr>
    <tr>
      <td data-export="Estimate Pre Arb"><a href="/mlb/player/_/id/4/w">H</a></td>
      <td data-export="C">C</td>
      <td data-export="696830"><a><div class='pill pill-normal pill-mlb text-center pill-estimate'><div class='pill-start'>$696,830</div><div class='pill-end'>0.3%</div></div></a></td>
      <td data-export="1000000"><a><div class='pill pill-normal pill-mlb text-center pill-estimate'><div class='pill-start'>$1,000,000</div><div class='pill-end'>PRE</div></div></a></td>
      <td data-export="0">PRE-ARB</td>
    </tr>
  </tbody>
</table>
"""


def _fixture_rows():
    table = BeautifulSoup(ESTIMATE_FIXTURE, "html.parser").find("table")
    return {r["player_name"]: r for r in S._parse_team_contract_table(table, "boston-red-sox")}


def test_an_arbitration_estimate_pill_is_a_status_and_never_a_salary():
    r = _fixture_rows()["Estimate Before Arb Three"]
    assert r["salary_by_year"] == {2026: 7775000}
    assert r["status_by_year"] == {2027: "ARB 2", 2028: "ARB 3"}
    assert r["signed_through"] == 2026 and r["years_remaining"] == 1
    assert r["control_years"] == [2027, 2028]


def test_a_final_year_estimate_stays_a_bare_arb_for_the_export_to_number():
    r = _fixture_rows()["Estimate Final Year"]
    assert r["salary_by_year"] == {2026: 1544125}
    assert r["status_by_year"] == {2027: "ARB", 2028: "UFA"}


def test_the_super_two_marker_travels_back_to_the_estimated_year():
    r = _fixture_rows()["Estimate Super Two"]
    assert r["salary_by_year"] == {2026: 900000}
    assert r["status_by_year"] == {2027: "ARB 2 (S2)", 2028: "ARB 3 (S2)"}


def test_a_pre_estimate_is_pre_arb_and_an_unlabelled_estimate_stays_money():
    r = _fixture_rows()["Estimate Pre Arb"]
    # the 2026 pill is an estimate too, but its end is a payroll share: it is
    # a prorated dollar figure for a season being paid, not a status
    assert r["salary_by_year"] == {2026: 696830}
    assert r["status_by_year"] == {2027: "PRE-ARB", 2028: "PRE-ARB"}


# -------------------------------------------------------- the export rules
def test_a_bare_arb_rung_takes_its_step_from_the_panel_label():
    base = {"season": 2026, "arb_year": 2, "super_two": False}
    assert X._number_bare_arb([(2027, "ARB"), (2028, "UFA")], base)[0] == (2027, "ARB 3")
    s2 = {"season": 2026, "arb_year": 3, "super_two": True}
    assert X._number_bare_arb([(2027, "ARB")], s2) == [(2027, "ARB 4 (S2)")]
    pre = {"season": 2026, "arb_year": None, "super_two": None}
    assert X._number_bare_arb([(2027, "ARB"), (2028, "ARB")], pre) == [
        (2027, "ARB 1"), (2028, "ARB 2")]
    # a numbered rung is never touched, and the step never passes 4
    assert X._number_bare_arb([(2027, "ARB 2")], base) == [(2027, "ARB 2")]
    late = {"season": 2026, "arb_year": 4, "super_two": None}
    assert X._number_bare_arb([(2027, "ARB")], late) == [(2027, "ARB 4")]


def test_a_played_season_never_becomes_a_rung(monkeypatch):
    import arb_dataset as A
    panel = [{"mlbam": 5, "season": 2026, "war": 0.1, "name": "R", "team": "LAD",
              "age": 28.0, "pa": 0, "ipouts": 30, "gs": 0, "salary": 780000.0}]
    panel.append(dict(panel[0], mlbam=6, name="S"))
    monkeypatch.setattr(A, "spotrac_status_by_mlbam", lambda: {
        5: {2026: "PRE-ARB"}, 6: {2026: "PRE-ARB", 2027: "PRE-ARB"}})
    monkeypatch.setattr(A, "league_min_by_year", lambda: {2026: 780000.0, 2027: 780000.0})
    monkeypatch.setattr(X, "_projected_war", lambda: {})
    out = X.build_board(panel, {}, {}, {}, season=2027, s1={"keys": []},
                        defl={2027: 1.0}, banded={})
    by = {r["m"]: r for r in out["rows"]}
    assert 5 not in by, "a ladder with no remaining season is not a board row"
    assert by[6]["l"] == [[2027, 780000, 780000, 780000, "PRE-ARB"]]
    assert by[6]["tot"] == 780000 and by[6]["yl"] == 1 and by[6]["c"] == 0


# ------------------------------------------------- the served artifacts
def test_the_served_board_prices_only_remaining_seasons_and_tot_is_its_ladder():
    board = _doc("arbitration.json")
    season = int(board["season"])
    early, bad_tot, bad_yl, bad_c = [], [], [], []
    for r in board.get("rows") or []:
        lad = r.get("l") or []
        assert lad, r.get("n")
        assert all(t[4] != "ARB" for t in lad), ("a bare ARB rung was served", r.get("n"))
        early += [(r.get("n"), t[0]) for t in lad if int(t[0]) < season]
        if (r.get("tot") or 0) != sum(t[1] or 0 for t in lad):
            bad_tot.append((r.get("n"), r.get("tot")))
        if r.get("yl") != len(lad):
            bad_yl.append((r.get("n"), r.get("yl"), len(lad)))
        if r.get("c") != X._token_step(lad[0][4])[0]:
            bad_c.append((r.get("n"), r.get("c"), lad[0][4]))
    assert not early, f"rungs before the board season {season}: {early[:5]}"
    assert not bad_tot, f"tot is not the sum of its rungs: {bad_tot[:5]}"
    assert not bad_yl, bad_yl[:5]
    assert not bad_c, bad_c[:5]


def test_a_null_rung_is_only_ever_a_player_with_no_salary_on_file():
    board = _doc("arbitration.json")
    bad = [(r.get("n"), t) for r in board.get("rows") or [] for t in r.get("l") or []
           if t[1] is None and not (int(r.get("e") or 0) & X.F_NO_SALARY)]
    assert not bad, bad[:5]


def test_every_club_ledger_remaining_figure_is_its_by_season_rows():
    led = _doc("ledger_board.json")
    board = _doc("arbitration.json")
    season = int(board["season"])
    assert int(led["class_year"]) == season
    for club, d in (led.get("clubs") or {}).items():
        a = d["arbitration"]
        rows = a.get("by_season") or []
        assert all(int(row[0]) >= season for row in rows), (club, rows)
        assert a["remaining_usd"] == sum(row[1] + row[3] for row in rows), club


def _cache_pages():
    pages = {}
    for code, slug in S._SPOTRAC_TEAM_SLUGS.items():
        p = S.CACHE_DIR / f"spotrac_team_{slug}.html"
        if not p.exists():
            return None
        pages[code] = p
    return pages


def test_every_cached_2027_arbitration_season_has_a_2027_rung():
    """Read straight off the cached Spotrac team pages (never the network).
    Every player whose 2027 cell is an ARB token, or a labelled Spotrac
    estimate, reaches the board with a 2027 rung, priced unless the row
    carries the no-salary flag."""
    pages = _cache_pages()
    if pages is None:
        pytest.skip("Spotrac team-page cache absent")
    board = _doc("arbitration.json")
    built = date.fromisoformat(board["generated_at"])
    newest = max(datetime.fromtimestamp(p.stat().st_mtime).date() for p in pages.values())
    if newest > built:
        pytest.skip(f"cache ({newest}) is newer than the board ({built}); rebuild first")
    links = json.loads((ROOT / "data" / "player_links.json").read_text("utf-8"))
    mlbam_of = {k: (v or {}).get("mlbam") for k, v in (links.get("byKey") or {}).items()}
    status = {}
    for code, p in pages.items():
        soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
        for tid in S.CONTRACT_TABLE_IDS + S.STATUS_TABLE_IDS:
            t = soup.find("table", id=tid)
            if t is None:
                continue
            for row in S._parse_team_contract_table(t, code):
                m = mlbam_of.get(row.get("player_key"))
                if m and row.get("status_by_year"):
                    status.setdefault(int(m), row["status_by_year"])
    arb = {m: s[2027] for m, s in status.items() if (s.get(2027) or "").startswith("ARB")}
    assert len(arb) > 200, len(arb)
    by = {int(r["m"]): r for r in board.get("rows") or []}
    missing, unpriced = [], []
    for m, tok in arb.items():
        r = by.get(m)
        rung = next((t for t in (r or {}).get("l") or [] if int(t[0]) == 2027), None)
        if rung is None:
            missing.append((m, tok))
        elif rung[1] is None and not (int(r.get("e") or 0) & X.F_NO_SALARY):
            unpriced.append((r.get("n"), rung))
    assert not missing, f"{len(missing)} cached 2027 ARB seasons reach no 2027 rung: {missing[:5]}"
    assert not unpriced, unpriced[:5]
