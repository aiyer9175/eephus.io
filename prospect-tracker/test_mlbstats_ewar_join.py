# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR on the Leverage, Defense and team boards (MLB Stats overhaul, wave 4).

Three joins ship here and each one has a way of going quietly wrong:

  * E3, LEVERAGE. A batter row carries his BATTING side and a starter row his
    PITCHING side. Summing the two onto one number would hand a two-way player
    his pitching value on the batter board, which is the error
    fa_projection._war_age_maps makes on purpose for a different denominator.
  * E4, DEFENSE. The column is WHOLE-PLAYER eWAR, batting plus pitching, summed
    UNROUNDED and rounded once; rounding each side first drifts by up to a full
    display step. The fielding frame inside eWAR is not the frame behind Fld and
    DEM+, so the payload carries the sentence that says so, read from the
    artifact (the page types no frame: eWAR v3 moves that answer with no page
    change).
  * E5, TEAM eWAR. A club total is the sum over EVERY board row that names the
    club, qualified or not and above or below the WAR-rate display floor,
    summed unrounded. A club with no covered row carries NO value: a blank
    reads as "not computed", a 0.0 reads as a replacement-level roster.

The absent-never-zero rule is the thread through all three, and it is asserted
on each side rather than assumed from one.

No network and no artifact: the side map is injected, so these run anywhere.
"""
from __future__ import annotations

import json

import pytest

import bullpen_export as be
import defense_export as de
import leverage_export as le


@pytest.fixture(autouse=True)
def _no_ingest_writes(monkeypatch):
    """The ingest-health ledger is a served artifact; a unit test never books to
    it (the same posture as conftest's odds-ledger isolation)."""
    monkeypatch.setattr(be, "record_ingest", lambda *a, **k: None)


def _map(season=2026, **sides):
    """{mlbam: {season: {"bat": x, "pit": y}}}, the side_war_by_season shape."""
    out: dict = {}
    for side, by_id in sides.items():
        for mid, v in by_id.items():
            out.setdefault(int(mid), {}).setdefault(int(season), {})[side] = v
    return out


def _patch_map(monkeypatch, war_map):
    monkeypatch.setattr(be, "_side_war_by_season", lambda: war_map)


# --------------------------------------------------------------- E3 leverage

def test_each_leverage_board_carries_its_own_side_of_ewar(monkeypatch):
    """A two-way player is 3.5 on the batter board and 2.7 on the starter board,
    never 6.2 on either: the side is the board's side."""
    _patch_map(monkeypatch, _map(bat={9: 3.5, 1: 2.0}, pit={9: 2.7, 2: 1.8}))
    batters = [{"mlbam": 9, "pa": 500}, {"mlbam": 1, "pa": 400}]
    starters = [{"mlbam": 9, "starts": 14}, {"mlbam": 2, "starts": 30}]
    meta = le._stamp_war(batters, starters, 2026)
    assert [r["war"] for r in batters] == [3.5, 2.0]
    assert [r["war"] for r in starters] == [2.7, 1.8]
    assert meta["n_batters"] == 2 and meta["n_starters"] == 2


def test_a_leverage_row_is_blank_iff_the_artifact_does_not_cover_it(monkeypatch):
    """Absent iff no cell, which is E3's whole rule. The leverage fold's `pa`
    and `starts` come from the winProbability walk rather than the season line,
    so a null there is a feed shape and must not blank a covered player's eWAR
    beside a GS of 30: this board does not divide by a denominator, so it does
    not gate on one (the WAR-rate columns do both)."""
    _patch_map(monkeypatch, _map(bat={1: 1.1, 3: 0.0}, pit={2: 0.9, 4: 0.0}))
    batters = [{"mlbam": 1, "pa": 0}, {"mlbam": 5, "pa": 300},
               {"mlbam": 3, "pa": 120}, {"pa": 200}]
    starters = [{"mlbam": 2, "starts": None}, {"mlbam": 6, "starts": 20},
                {"mlbam": 4, "starts": 9}]
    le._stamp_war(batters, starters, 2026)
    # covered, whatever the fold's own denominator says
    assert batters[0]["war"] == 1.1 and starters[0]["war"] == 0.9
    # uncovered, and the row with no id at all
    assert "war" not in batters[1] and "war" not in batters[3]
    assert "war" not in starters[1]
    # a real zero is a real value and prints; it is never a negative zero
    assert batters[2]["war"] == 0.0 and str(batters[2]["war"]) == "0.0"
    assert starters[2]["war"] == 0.0


def test_a_failed_war_read_leaves_the_leverage_boards_blank_and_says_so(
        monkeypatch):
    """The refusal has to be legible in the served block, or "joined for 0/659"
    reads as a coverage fact about the season instead of an outage."""
    def _boom():
        raise RuntimeError("pybaseball down")
    monkeypatch.setattr(be, "_side_war_by_season", _boom)
    batters = [{"mlbam": 1, "pa": 500}]
    starters = [{"mlbam": 2, "starts": 30}]
    meta = le._stamp_war(batters, starters, 2026)
    assert "war" not in batters[0] and "war" not in starters[0]
    assert meta["refused"] and not meta.get("available")


def test_a_degenerate_war_map_refuses_the_leverage_board_it_barely_covers(
        monkeypatch):
    """Three covered arms out of sixty is the degenerate fetch score_war_rate
    refuses on, and this refuses with it: a handful of numbers beside the blanks
    would read as real. The healthy side still ships, and the refusal names its
    own board."""
    covered_bat = {i: 1.0 for i in range(1, 61)}
    _patch_map(monkeypatch, _map(bat=covered_bat, pit={101: 2.0, 102: 2.0}))
    batters = [{"mlbam": i, "pa": 400} for i in range(1, 61)]
    starters = [{"mlbam": 100 + i, "starts": 20} for i in range(1, 61)]
    meta = le._stamp_war(batters, starters, 2026)
    assert meta["n_batters"] == 60 and batters[0]["war"] == 1.0
    assert meta["n_starters"] == 0
    assert all("war" not in r for r in starters)
    assert "floor 50%" in meta["starters_refused"]
    assert "batters_refused" not in meta


def test_a_leverage_row_of_another_season_is_not_borrowed(monkeypatch):
    _patch_map(monkeypatch, _map(season=2025, bat={1: 4.4}))
    batters = [{"mlbam": 1, "pa": 600}]
    le._stamp_war(batters, [], 2026)
    assert "war" not in batters[0]


def _lev_export(tmp_path, monkeypatch, batters, starters):
    monkeypatch.setattr(le, "OUT_PATH", tmp_path / "leverage_leaderboards.json")
    monkeypatch.setattr(le, "_season_boards",
                        lambda season, leverage_limit=None, log=print: (
                            batters, starters, {"games": 1, "games_total": 1},
                            {"ewar_join": {"n_batters": len(batters)}}, []))
    monkeypatch.setattr(le, "_war_source_vintage",
                        lambda as_of=None: {"artifact_generated_at": "2026-09-16",
                                            "as_of": as_of, "stale": False})
    le.export(2026, write=True, log=lambda *a, **k: None, today="2026-09-16")
    return json.loads(le.OUT_PATH.read_text(encoding="utf-8"))


def test_the_leverage_payload_dates_the_ewar_column_it_serves(tmp_path, monkeypatch):
    """The build stamp ships with the column, on this board as on the others: a
    reader who sees an eWAR number can always ask which build it came from."""
    doc = _lev_export(tmp_path, monkeypatch,
                      [{"mlbam": 1, "name": "A", "team": "NYY", "pa": 500,
                        "wpa": 3.0, "war": 4.1, "qualified": True}],
                      [{"mlbam": 2, "name": "B", "team": "LAD", "starts": 30,
                        "wpa": 2.0, "gs": 30, "war": 5.2, "qualified": True}])
    assert doc["ewar_vintage"]["as_of"] == "2026-09-16"
    assert doc["batters"][0]["war"] == 4.1 and doc["starters"][0]["war"] == 5.2


def test_a_refused_leverage_join_ships_no_build_stamp(tmp_path, monkeypatch):
    """The stamp dates a column. With no column on any row it dates nothing, so
    it does not ship (the iff the defense contract test holds, on this board
    too); the refusal stays readable in sources.ewar_join."""
    doc = _lev_export(tmp_path, monkeypatch,
                      [{"mlbam": 1, "name": "A", "team": "NYY", "pa": 500,
                        "wpa": 3.0, "qualified": True}],
                      [{"mlbam": 2, "name": "B", "team": "LAD", "starts": 30,
                        "wpa": 2.0, "gs": 30, "qualified": True}])
    assert "ewar_vintage" not in doc
    assert "war" not in doc["batters"][0] and "war" not in doc["starters"][0]
    assert "ewar_join" in doc["sources"]


def test_the_leverage_history_seasons_carry_the_same_join(tmp_path, monkeypatch):
    """History is the same rule per season, not a second one."""
    _patch_map(monkeypatch, _map(season=2025, bat={1: 4.4}, pit={2: 3.3}))
    monkeypatch.setattr(le, "_war_source_vintage",
                        lambda as_of=None: {"artifact_generated_at": "2026-09-16"})

    def _boards(season, leverage_limit=None, log=print):
        batters = [{"mlbam": 1, "name": "A", "team": "NYY", "pa": 600, "wpa": 3.0,
                    "qualified": True}]
        starters = [{"mlbam": 2, "name": "B", "team": "LAD", "starts": 30,
                     "wpa": 2.0, "qualified": True}]
        le._stamp_war(batters, starters, season)
        return batters, starters, {"games": 1}, {}, []

    monkeypatch.setattr(le, "_season_boards", _boards)
    out = tmp_path / "leverage_history.json"
    doc = le.export_history([2025], out_path=out, write=True, log=lambda *a, **k: None)
    yr = doc["history"]["2025"]
    assert yr["batters"][0]["war"] == 4.4 and yr["starters"][0]["war"] == 3.3
    assert "ewar_vintage" in doc


def test_the_season_boards_stamp_both_sides_for_live_and_history(monkeypatch):
    """The join lives in _season_boards, which is the ONE path both the live
    export and every history season go through."""
    _patch_map(monkeypatch, _map(bat={1: 4.4}, pit={2: 3.3}))
    monkeypatch.setattr(le, "load_season_hitting", lambda season: [])
    monkeypatch.setattr(le, "load_season_pitching", lambda season: [])
    import mlb_leverage
    monkeypatch.setattr(mlb_leverage, "fetch_season_all_leverage",
                        lambda season, limit=None: (
                            {}, {1: {"name": "A", "pa": 600, "wpa": 3.0}},
                            {2: {"name": "B", "starts": 30, "wpa": 2.0}},
                            {"games": 1, "games_total": 1}))
    batters, starters, _cov, sources, _src = le._season_boards(
        2026, log=lambda *a, **k: None)
    assert batters[0]["war"] == 4.4 and starters[0]["war"] == 3.3
    assert sources["ewar_join"]["n_batters"] == 1


# ---------------------------------------------------------------- E4 defense

def test_defense_ewar_is_both_sides_summed_before_rounding(monkeypatch):
    """1.44 + 1.44 is 2.9, not the 2.8 two rounded sides would give. The
    column is whole-player, so a fielder who pitched carries both."""
    _patch_map(monkeypatch, _map(bat={9: 1.44, 1: 3.51}, pit={9: 1.44}))
    rows = [{"mlbam": 9, "inn": 400.0}, {"mlbam": 1, "inn": 900.0}]
    meta = de._stamp_war(rows, 2026)
    assert rows[0]["war"] == 2.9
    assert rows[0]["war"] != round(round(1.44, 1) + round(1.44, 1), 1)
    assert rows[1]["war"] == 3.5          # one side is the whole player here
    assert meta["n_stamped"] == 2 and meta["n_two_sided"] == 1


def test_a_fielder_the_artifact_does_not_cover_stays_blank(monkeypatch):
    _patch_map(monkeypatch, _map(bat={1: 2.0}))
    rows = [{"mlbam": 7, "inn": 500.0}, {"inn": 500.0}, {"mlbam": 1, "inn": 10.0}]
    de._stamp_war(rows, 2026)
    assert "war" not in rows[0] and "war" not in rows[1]
    assert rows[2]["war"] == 2.0          # innings are exposure, not a gate


def test_a_degenerate_war_map_refuses_the_defense_board(monkeypatch):
    """Twelve covered fielders out of a hundred is the degenerate fetch, and a
    board of twelve numbers beside 88 blanks is exactly what the WAR-rate floor
    exists to stop; the same floor governs here."""
    _patch_map(monkeypatch, _map(bat={i: 1.0 for i in range(1, 13)}))
    rows = [{"mlbam": i, "inn": 900.0} for i in range(1, 101)]
    meta = de._stamp_war(rows, 2026)
    assert meta["n_stamped"] == 0 and not meta.get("available")
    assert all("war" not in r for r in rows)
    assert "12 of 100" in meta["refused"] and "floor 50%" in meta["refused"]


def test_a_failed_war_read_leaves_the_defense_board_blank_and_says_so(monkeypatch):
    def _boom():
        raise RuntimeError("pybaseball down")
    monkeypatch.setattr(be, "_side_war_by_season", _boom)
    rows = [{"mlbam": 1, "inn": 500.0}]
    meta = de._stamp_war(rows, 2026)
    assert "war" not in rows[0]
    assert meta["refused"] and not meta.get("available")


def _patch_ewar_meta(monkeypatch, meta):
    import ewar
    monkeypatch.setattr(ewar, "load", lambda path=None: {"meta": meta})


def test_the_defense_frame_sentence_is_read_from_the_artifact(monkeypatch):
    """The page types no frame. v2 states its configuration; a v3 build that
    writes meta.fielding_source is quoted verbatim, with no code change here."""
    _patch_ewar_meta(monkeypatch, {"fielding_blend_w": 0.0})
    assert de._ewar_fielding_note() == (
        "Its fielding is Baseball-Reference's (fielding_blend_w 0.0), a "
        "different frame from Fld and DEM+.")
    _patch_ewar_meta(monkeypatch, {"fielding_blend_w": 0.0,
                                   "fielding_source": "Its fielding is the fWAR frame."})
    assert de._ewar_fielding_note() == "Its fielding is the fWAR frame."
    _patch_ewar_meta(monkeypatch, {"fielding_blend_w": 0.6})
    assert "0.6" in de._ewar_fielding_note()


def test_a_bare_fielding_source_token_is_set_in_a_sentence(monkeypatch):
    """data/ewar.json writes its per-block fielding source as "bref", a token.
    If a v3 build lifts that vocabulary to meta level the title must not read
    "Whole-player eWAR this season. bref", and the page cannot fix it because it
    types no frame. The wrapper names the source and claims nothing else: a v3
    whose fielding IS the published frame would make "a different frame" false."""
    _patch_ewar_meta(monkeypatch, {"fielding_source": "bref"})
    assert de._ewar_fielding_note() == "Its fielding comes from bref."
    _patch_ewar_meta(monkeypatch, {"fielding_source": "fangraphs"})
    note = de._ewar_fielding_note()
    assert note == "Its fielding comes from fangraphs."
    assert "different frame" not in note
    # a non-string (the artifact's meta.fielding is a dict today) is not a frame
    _patch_ewar_meta(monkeypatch, {"fielding_source": {"by_season": {}},
                                   "fielding_blend_w": 0.0})
    assert de._ewar_fielding_note().startswith("Its fielding is Baseball-Reference")


def test_an_unreadable_artifact_states_the_absence_instead_of_a_frame(monkeypatch):
    import ewar

    def _boom(path=None):
        raise OSError("no artifact")

    monkeypatch.setattr(ewar, "load", _boom)
    note = de._ewar_fielding_note()
    assert "could not be read" in note
    assert "Baseball-Reference" not in note   # never guess a frame


def test_the_defense_frame_block_carries_the_note_and_not_the_old_line(monkeypatch):
    _patch_ewar_meta(monkeypatch, {"fielding_blend_w": 0.0})
    frame = de._frame_meta()
    assert frame["ewar_note"].startswith("Its fielding is")
    assert "not_ewar" not in frame


def _def_export(tmp_path, monkeypatch, fielders, teams):
    monkeypatch.setattr(de, "_active_mlbam_ids", lambda season: None)
    monkeypatch.setattr(de, "HITTER_BOARD", tmp_path / "missing_hitters.json")
    monkeypatch.setattr(de, "MULTIYR_PATH", tmp_path / "missing_multiyr.json")
    monkeypatch.setattr(de, "EVAL_PATH", tmp_path / "missing_eval.json")
    monkeypatch.setattr(de, "_war_source_vintage",
                        lambda as_of=None: {"artifact_generated_at": "2026-09-16",
                                            "as_of": as_of, "stale": False})
    monkeypatch.setattr(de, "score_season",
                        lambda season, active_ids=None, log=print, file_red=True: {
                            "scored": {"fielders": fielders, "teams": teams,
                                       "pool": {"n_qualified": len(fielders)}},
                            "basis_rows": [],
                            "framing": {"framing_available": True,
                                        "n_catchers_c200": 0,
                                        "n_catchers_with_framing": 0},
                            "src": {"published": {}, "innings": {}, "ladder": {}},
                            "fielders": fielders})
    out = tmp_path / "defense_leaderboards.json"
    de.export(2026, out_path=out, write=True, log=lambda *a, **k: None,
              today="2026-09-16")
    return json.loads(out.read_text(encoding="utf-8"))


def test_the_defense_payload_ships_the_column_the_stamp_and_the_note(
        tmp_path, monkeypatch):
    """The served contract: a war column, the build stamp that dates it, and the
    frame sentence the title reads (test_defense_export_contract holds the iff)."""
    _patch_map(monkeypatch, _map(bat={1: 2.04}, pit={1: 0.02}))
    _patch_ewar_meta(monkeypatch, {"fielding_blend_w": 0.0})
    doc = _def_export(tmp_path, monkeypatch,
                      [{"mlbam": 1, "name": "A", "team": "NYY", "inn": 900.0}],
                      [{"team": "NYY", "team_dem_plus": 101}])
    assert doc["fielders"][0]["war"] == 2.1
    assert doc["ewar_vintage"]["as_of"] == "2026-09-16"
    assert doc["frame"]["ewar_note"] and "not_ewar" not in doc["frame"]
    assert doc["ewar_join"]["n_stamped"] == 1
    # a fielding board keeps whole-player eWAR off the CLUB row (it would repeat
    # the lineup total on another frame)
    assert "team_war" not in doc["teams"][0]


def test_a_refused_defense_join_ships_neither_column_nor_stamp(
        tmp_path, monkeypatch):
    """The contract test is an iff and this is its other direction: with the WAR
    read down the board serves no war column, so it must serve no build stamp
    dating one. Without this the renamed contract test goes red on the served
    file in a real failure mode."""
    def _boom():
        raise RuntimeError("pybaseball down")
    monkeypatch.setattr(be, "_side_war_by_season", _boom)
    _patch_ewar_meta(monkeypatch, {"fielding_blend_w": 0.0})
    doc = _def_export(tmp_path, monkeypatch,
                      [{"mlbam": 1, "name": "A", "team": "NYY", "inn": 900.0}],
                      [{"team": "NYY", "team_dem_plus": 101}])
    has_war = any(k.startswith(("war", "ewar"))
                  for r in doc["fielders"] for k in r)
    assert not has_war
    assert ("ewar_vintage" in doc) == has_war
    assert doc["ewar_join"]["refused"]


# --------------------------------------------------------------- E5 team eWAR

def test_team_war_sums_every_row_of_the_club_unrounded(monkeypatch):
    """Four 0.44-win arms are 1.8, not the 1.6 four rounded rows would give, and
    the sub-floor arm counts: a pen is its arms, not its qualified arms."""
    _patch_map(monkeypatch, _map(pit={1: 0.44, 2: 0.44, 3: 0.44, 4: 0.44}))
    rows = [{"mlbam": 1, "team": "NYY", "ip": 60.0},
            {"mlbam": 2, "team": "NYY", "ip": 55.0},
            {"mlbam": 3, "team": "NYY", "ip": 40.0},
            {"mlbam": 4, "team": "NYY", "ip": 12.0}]     # under the display gate
    teams = [{"team": "NYY"}]
    meta = be.stamp_team_war(teams, rows, 2026, side="pit")
    assert teams[0]["team_war"] == 1.8
    assert teams[0]["team_war_n"] == 4
    assert abs(teams[0]["team_war"] - sum(0.44 for _ in rows)) <= 0.05 * len(rows)
    assert meta["n_rows_summed"] == 4 and meta["n_rows_without_war"] == 0
    assert meta["basis"] == be.TEAM_BASIS and meta["side"] == "pit"


def test_a_club_with_no_covered_row_carries_no_team_war(monkeypatch):
    """Absent, never zero. A stale rollup row stamped on an earlier run must not
    keep a value the rows no longer support."""
    _patch_map(monkeypatch, _map(bat={1: 3.0}))
    rows = [{"mlbam": 1, "team": "NYY", "pa": 500},
            {"mlbam": 2, "team": "LAD", "pa": 400},
            {"mlbam": 3, "team": None, "pa": 300}]
    teams = [{"team": "NYY"}, {"team": "LAD", "team_war": 9.9, "team_war_n": 3},
             {"team": "SEA"}]
    meta = be.stamp_team_war(teams, rows, 2026, side="bat")
    assert teams[0]["team_war"] == 3.0 and teams[0]["team_war_n"] == 1
    assert "team_war" not in teams[1] and "team_war_n" not in teams[1]
    assert "team_war" not in teams[2]
    # the LAD row is the uncovered one; the teamless row is in no club at all
    assert meta["n_rows_without_war"] == 1
    assert meta["n_teams_stamped"] == 1


def test_the_three_counts_reconcile_to_every_row(monkeypatch):
    """A row dropped for having no club is counted too, so summed + without_war
    + without_team is the whole board. A failed _team_abbrev_map blanks every
    team code, and that outage must not report as a clean partial."""
    _patch_map(monkeypatch, _map(pit={1: 1.0, 2: 2.0}))
    rows = [{"mlbam": 1, "team": "NYY", "ip": 60.0},
            {"mlbam": 2, "team": "NYY", "ip": 60.0},
            {"mlbam": 3, "team": "NYY", "ip": 60.0},
            {"mlbam": 4, "team": None, "ip": 60.0},
            {"mlbam": 5, "ip": 60.0}]
    meta = be.stamp_team_war([{"team": "NYY"}], rows, 2026, side="pit")
    assert meta["n_rows_summed"] == 2
    assert meta["n_rows_without_war"] == 1
    assert meta["n_rows_without_team"] == 2
    assert (meta["n_rows_summed"] + meta["n_rows_without_war"]
            + meta["n_rows_without_team"]) == len(rows)


def test_a_degenerate_war_map_stamps_no_club_and_clears_a_stale_one(monkeypatch):
    """Two covered arms out of twenty would print "NYY 0.9" beside twenty blank
    player rows. The club rollup refuses on the same floor the player columns
    do, and it CLEARS the field, because guard_nonempty_block can serve last
    run's rollup and a stale total must not ride beside this run's blanks."""
    _patch_map(monkeypatch, _map(pit={1: 0.45, 2: 0.45}))
    rows = [{"mlbam": i, "team": "NYY", "ip": 50.0} for i in range(1, 21)]
    teams = [{"team": "NYY", "team_war": 9.9, "team_war_n": 20}]
    meta = be.stamp_team_war(teams, rows, 2026, side="pit")
    assert "team_war" not in teams[0] and "team_war_n" not in teams[0]
    assert meta["n_teams_stamped"] == 0 and not meta.get("available")
    assert "2 of 20" in meta["refused"] and "floor 50%" in meta["refused"]


def test_a_failed_war_read_also_clears_a_stale_team_war(monkeypatch):
    def _boom():
        raise RuntimeError("pybaseball down")
    monkeypatch.setattr(be, "_side_war_by_season", _boom)
    teams = [{"team": "NYY", "team_war": 9.9, "team_war_n": 20}]
    be.stamp_team_war(teams, [{"mlbam": 1, "team": "NYY"}], 2026, side="pit")
    assert "team_war" not in teams[0] and "team_war_n" not in teams[0]


def test_team_war_reads_the_side_the_board_is_on(monkeypatch):
    """The lineup rollup sums the BATTING side and a pen the PITCHING side: a
    two-way player never contributes his pitching wins to Team Lineups."""
    _patch_map(monkeypatch, _map(bat={9: 3.5}, pit={9: 2.7}))
    rows = [{"mlbam": 9, "team": "LAD", "pa": 500}]
    hit_teams, pit_teams = [{"team": "LAD"}], [{"team": "LAD"}]
    be.stamp_team_war(hit_teams, rows, 2026, side="bat")
    be.stamp_team_war(pit_teams, rows, 2026, side="pit")
    assert hit_teams[0]["team_war"] == 3.5 and pit_teams[0]["team_war"] == 2.7


def test_a_failed_war_read_stamps_no_club_at_all(monkeypatch):
    def _boom():
        raise RuntimeError("pybaseball down")
    monkeypatch.setattr(be, "_side_war_by_season", _boom)
    teams = [{"team": "NYY"}]
    meta = be.stamp_team_war(teams, [{"mlbam": 1, "team": "NYY"}], 2026, side="pit")
    assert "team_war" not in teams[0]
    assert meta["refused"] and not meta.get("available")


def test_the_three_team_boards_all_wire_the_rollup_on_their_own_side():
    """The owner's ask is team eWAR on Bullpens, Rotations and Lineups, so the
    call site is pinned on each: a board that loses it would show up only as a
    blank column on the page.

    THE SIDE IS PINNED WITH IT. Team Lineups on side="pit" would serve pitching
    eWAR beside Offense+, near blank for all 30 clubs, and the helper cannot
    object because it honours the argument it is handed."""
    import hitter_export
    import starter_export
    for mod, side, rows in ((be, "pit", 'scored["relievers"]'),
                            (starter_export, "pit", 'scored["starters"]'),
                            (hitter_export, "bat", 'scored["hitters"]')):
        src = open(mod.__file__, encoding="utf-8").read()
        call = (f'rollup_meta["team_war"] = stamp_team_war(\n'
                f'        teams, {rows}, season, side="{side}")')
        assert call in src, f"{mod.__name__}: {call}"


def test_each_board_sums_its_own_side_for_a_two_way_player(monkeypatch):
    """The end of that wiring, exercised rather than grepped: the same two-way
    player is 3.5 in the club's lineup total and 2.7 in its rotation total, and
    neither total is 6.2."""
    _patch_map(monkeypatch, _map(bat={9: 3.5, 8: 1.0}, pit={9: 2.7, 7: 1.5}))
    hit_rows = [{"mlbam": 9, "team": "LAD", "pa": 500},
                {"mlbam": 8, "team": "LAD", "pa": 400}]
    pit_rows = [{"mlbam": 9, "team": "LAD", "ip": 90.0},
                {"mlbam": 7, "team": "LAD", "ip": 150.0}]
    lineups, rotations = [{"team": "LAD"}], [{"team": "LAD"}]
    be.stamp_team_war(lineups, hit_rows, 2026, side="bat")
    be.stamp_team_war(rotations, pit_rows, 2026, side="pit")
    assert lineups[0]["team_war"] == 4.5      # 3.5 + 1.0, batting only
    assert rotations[0]["team_war"] == 4.2    # 2.7 + 1.5, pitching only
