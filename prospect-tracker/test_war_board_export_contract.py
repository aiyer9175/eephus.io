# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR board's contract (war_board_export.py -> data/war_leaderboards.json).

WHAT THIS FILE IS ABOUT. data/war_leaderboards.json is the ONE artifact that
publishes a summed eWAR, and the reason the five player boards must not is the
same reason this one has to exist:

  * a board row's `war` is ONE SIDE, because the WAR-rate columns beside it
    divide by that side's denominator. Summing there would divide a two-way
    player's pitching by his plate appearances.
  * this payload's `war` is the WHOLE player, and it is summed from the
    UNROUNDED sides, because 0.44 + 0.44 is 0.9 and not the 0.8 two rounded
    cells would give.

Both halves are asserted here, the second one against the served board
artifacts, so the day someone stamps a sum onto a board row this goes red.

The rest is the failure behaviour the house pattern requires: a degenerate WAR
read REFUSES the write rather than publishing a board of blanks, an absent side
is a missing field and never a zero, and a club the stint frame cannot name gets
no Earned value at all.

Fixture-free except where a fixture is the point: the joins are exercised on
synthetic maps, and the served-artifact assertions skip when the board has not
been built on this machine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bullpen_export as be
import data_catalog
import rem_plus
import sem_plus
import war_board_export as wbe

ROOT = Path(__file__).parent
SERVED = ROOT / "data" / "war_leaderboards.json"
SEASON = 2026


# --------------------------------------------------------------------------- #
# a board with no feed behind it: every input is handed in
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _no_frame_leak():
    """_stint_frame memoises the war_daily frames FOR THE PROCESS (one download
    instead of four). A memo that outlived a test would hand the next one
    another test's stub, so it is emptied on both sides of every test."""
    wbe._FRAME_CACHE.clear()
    yield
    wbe._FRAME_CACHE.clear()


def _stub(monkeypatch, *, sides: dict, hitting: list, pitching: list,
          earned: dict | None = None, out: Path | None = None,
          seen: dict | None = None) -> list:
    """Run build()/export() against synthetic feeds. Nothing here touches the
    network, the eWAR artifact, the stint frames or data/.

    `seen` collects what the build ASKED the feeds for (the positions argument),
    because that argument is the only thing that puts a two-way player's innings
    on this board and nothing else would notice it going missing."""
    monkeypatch.setattr(wbe, "_side_war_by_season", lambda: sides)
    monkeypatch.setattr(wbe, "load_season_hitting", lambda s: list(hitting))

    def _pitching(s, positions=("P",)):
        if seen is not None:
            seen["positions"] = tuple(positions)
            seen["season"] = s
        return list(pitching)

    monkeypatch.setattr(wbe, "load_season_pitching", _pitching)
    monkeypatch.setattr(wbe, "_board_membership", lambda log=print: ({}, {"read": []}))
    monkeypatch.setattr(wbe, "_name_fallback", lambda season: {})
    monkeypatch.setattr(wbe, "_earned_by_club",
                        lambda season, dialect, log=print: (dict(earned or {}),
                                                            {"available": bool(earned)}))
    # the ingest ledger is a reporting path; a unit test must not file into it
    monkeypatch.setattr(be, "record_ingest", lambda *a, **k: None)
    filed: list = []
    monkeypatch.setattr(wbe, "_ingest_red", lambda source, msg: filed.append((source, msg)))
    if out is not None:
        monkeypatch.setattr(wbe, "OUT_PATH", out)
    return filed


def _league(n: int = 8, *, team: str = "BOS", start: int = 900):
    """A small but PLAUSIBLE season: n hitters and n arms, each with a side
    cell and a feed row. The feed guards measure a feed against the players who
    carry that side's eWAR cell, so a fixture that is one player wide would
    refuse for a reason the test is not about."""
    sides, hitting, pitching = {}, [], []
    for i in range(n):
        hid, pid = start + i, start + 100 + i
        sides[hid] = {SEASON: {"bat": 1.0}}
        sides[pid] = {SEASON: {"pit": 1.0}}
        hitting.append(_hit(hid, f"Bat {i}", team, 500))
        pitching.append(_pit(pid, f"Arm {i}", team, "60.0", 60, 0))
    return sides, hitting, pitching


def _hit(mlbam, name, team, pa, pos=None):
    row = {"mlbam": mlbam, "name": name, "team": team, "PA": pa}
    if pos:
        row["primary_pos"] = pos
    return row


def _pit(mlbam, name, team, ip, g, gs, pos=None):
    row = {"mlbam": mlbam, "name": name, "team": team, "IP": ip, "G": g, "GS": gs}
    if pos:
        row["pos"] = pos
    return row


def test_the_two_sides_are_summed_before_rounding(monkeypatch):
    """0.44 + 0.44 is 0.9. Two rounded cells would publish 0.8.

    This is the whole reason the sum is stored here and computed here rather
    than added up by the page from the two columns beside it."""
    _stub(monkeypatch,
          sides={11: {SEASON: {"bat": 0.44, "pit": 0.44}}},
          hitting=[_hit(11, "Split Sider", "BOS", 300)],
          pitching=[_pit(11, "Split Sider", "BOS", "40.0", 20, 0)])
    built = wbe.build(SEASON, log=lambda *a: None)
    row = built["players"][0]
    assert row["war"] == 0.9, "the sum was taken from the ROUNDED sides"
    assert (row["war_bat"], row["war_pit"]) == (0.4, 0.4)


def test_a_two_way_player_carries_both_sides_and_the_feed_role(monkeypatch):
    """The board exists so Ohtani reads as one season instead of two halves.

    The PITCHING READ IS PINNED HERE TOO. A two-way player's innings, starts and
    position code reach this board only because the season pitching feed is
    asked for ("P", "TWP"); drop the "TWP" and he silently becomes a hitter with
    no IP and no GS whose pitching eWAR is still inside his total, which is a
    row that looks perfectly plausible."""
    seen: dict = {}
    _stub(monkeypatch,
          sides={660271: {SEASON: {"bat": 3.44, "pit": 2.75}}},
          hitting=[_hit(660271, "Shohei Ohtani", "LAD", 596, pos="TWP")],
          pitching=[_pit(660271, "Shohei Ohtani", "LAD", "85.2", 14, 14, pos="TWP")],
          seen=seen)
    row = wbe.build(SEASON, log=lambda *a: None)["players"][0]
    assert seen["positions"] == ("P", "TWP"), (
        "the season pitching feed was not asked for two-way players")
    assert row["role"] == "TWP" and row["pos"] == "TWP"
    assert row["war_bat"] == 3.4 and row["war_pit"] == 2.8
    assert row["war"] == round(3.44 + 2.75, 1) == 6.2
    assert row["pa"] == 596 and row["gs"] == 14


def test_a_swingman_is_on_this_board_with_role_sw(monkeypatch):
    """A 30-game arm with 8 starts is on NEITHER pitcher board: too many starts
    for rem_plus.MAX_START_SHARE, too few for sem_plus.MIN_START_SHARE. He is
    the reason the section was asked for."""
    _stub(monkeypatch,
          sides={22: {SEASON: {"pit": 1.6}}},
          hitting=[],
          pitching=[_pit(22, "Long Man", "PIT", "70.0", 30, 8)])
    row = wbe.build(SEASON, log=lambda *a: None)["players"][0]
    assert row["role"] == "SW"
    assert "war_bat" not in row, "a side the artifact does not carry must be absent"
    assert row["war"] == 1.6


def test_the_role_ladder_is_the_boards_own_thresholds():
    """Reuse, not re-derivation: a second copy of 0.50 / 0.10 is how a swingman
    double counts on two boards or vanishes from both."""
    assert wbe._pitching_role(100.0, 10, 10 * sem_plus.MIN_START_SHARE) == "SP"
    assert wbe._pitching_role(100.0, 10, 10 * rem_plus.MAX_START_SHARE) == "RP"
    assert wbe._pitching_role(100.0, 100, 30) == "SW"
    # A pitching cell with no season line we can see is a pitcher on neither
    # board, which is exactly what SW means here.
    assert wbe._pitching_role(0.0, 0, 0) == "SW"


def test_a_position_player_pitching_mop_up_is_still_a_hitter(monkeypatch):
    """He has a pitching side cell; he is not on the pitching feed.

    And his cameo does NOT become a pitcher's column on his club: the club
    rollup buckets by the row's own role, so an inning of mop-up sits in Swing
    with the count and the value disclosed, instead of quietly reading as a
    swingman's season."""
    sides, hitting, pitching = _league(team="SEA")
    sides[33] = {SEASON: {"bat": 2.0, "pit": -0.1}}
    hitting.append(_hit(33, "Mop Up", "SEA", 500, pos="1B"))
    _stub(monkeypatch, sides=sides, hitting=hitting, pitching=pitching)
    built = wbe.build(SEASON, log=lambda *a: None)
    row = [r for r in built["players"] if r["mlbam"] == 33][0]
    assert row["role"] == "H" and row["pos"] == "1B"
    assert row["war_pit"] == -0.1, "his cameo is part of his whole season"
    assert "ip" not in row and "gs" not in row, "he has no pitching line"
    roll = built["sources"]["team_rollup"]
    assert roll["n_position_player_pitching_rows"] == 1
    assert roll["war_pit_from_position_players"] == -0.1


def test_absent_is_blank_and_a_real_zero_is_zero(monkeypatch):
    """The house rule, on every new field. A 0.0 SIDE CELL is a measurement and
    serves as 0.0; a side the artifact does not carry serves nothing.

    The third row is the trap: ip_to_float(None) returns 0.0, so a feed row with
    no IP would serve a measured zero innings unless the absence is checked
    BEFORE the conversion."""
    no_ip = {"mlbam": 66, "name": "No Innings Field", "team": "NYM",
             "G": 5, "GS": 0}
    _stub(monkeypatch,
          sides={44: {SEASON: {"bat": 0.0}}, 55: {SEASON: {"pit": 0.04}},
                 66: {SEASON: {"pit": 0.2}}},
          hitting=[_hit(44, "Exactly Replacement", "NYM", 250)],
          pitching=[_pit(55, "Rounds To Zero", "NYM", "31.0", 31, 0), no_ip])
    rows = {r["mlbam"]: r for r in wbe.build(SEASON, log=lambda *a: None)["players"]}
    assert rows[44]["war_bat"] == 0.0 and "war_pit" not in rows[44]
    # never -0.0: it renders as a different number from the 0.0 beside it
    assert str(rows[55]["war"]) == "0.0" and str(rows[55]["war_pit"]) == "0.0"
    assert "ip" not in rows[66], "an absent IP served as zero innings"
    assert rows[66]["g"] == 5 and rows[66]["gs"] == 0


def test_a_player_with_no_season_line_still_carries_his_ewar(monkeypatch):
    """Rows are every mlbam with a side cell, not every mlbam with a feed row:
    dropping him would silently shrink the league total. One such player in a
    healthy league is a released player, not a dead feed, so the guards below
    must not fire on him."""
    sides, hitting, pitching = _league(team="TB")
    sides[66] = {SEASON: {"bat": 1.1}}
    sides[77] = {SEASON: {"pit": 2.0}}
    pitching.append(_pit(77, "Qualified Arm", "TB", "80.0", 30, 0))
    _stub(monkeypatch, sides=sides, hitting=hitting, pitching=pitching)
    monkeypatch.setattr(wbe, "_name_fallback", lambda season: {66: "Released Guy"})
    rows = wbe.build(SEASON, log=lambda *a: None)["players"]
    got = [r for r in rows if r["mlbam"] == 66][0]
    assert got["name"] == "Released Guy" and got["war"] == 1.1
    assert "pa" not in got and got["team"] == ""


def test_the_qualified_rule_is_the_boards_display_floors(monkeypatch):
    """Published, not inferred, and the same two numbers the WAR-rate columns
    already gate on."""
    assert wbe.QUAL_MIN_PA == be.WAR_RATE_DISPLAY_MIN_PA
    assert wbe.QUAL_MIN_IP == be.WAR_RATE_DISPLAY_MIN_RP_IP
    _stub(monkeypatch,
          sides={1: {SEASON: {"bat": 1.0}}, 2: {SEASON: {"pit": 1.0}}},
          hitting=[_hit(1, "Part Timer", "COL", int(be.WAR_RATE_DISPLAY_MIN_PA) - 1)],
          pitching=[_pit(2, "Full Season", "COL", str(be.WAR_RATE_DISPLAY_MIN_RP_IP), 40, 0)])
    rows = {r["mlbam"]: r for r in wbe.build(SEASON, log=lambda *a: None)["players"]}
    assert rows[1]["qualified"] is False and rows[2]["qualified"] is True


# --------------------------------------------------------------------------- #
# the club rollup, on two bases
# --------------------------------------------------------------------------- #
def test_the_club_columns_sum_to_the_club_total(monkeypatch):
    """Hitters + Starters + Relievers + Swing is the club's eWAR. The pitching
    side goes to the column the row's own role names, so a two-way starter's
    pitching is in Starters and a swingman's is in Swing."""
    _stub(monkeypatch,
          sides={1: {SEASON: {"bat": 3.0}}, 2: {SEASON: {"pit": 2.0}},
                 3: {SEASON: {"pit": 1.0}}, 4: {SEASON: {"pit": 0.5}}},
          hitting=[_hit(1, "Bat", "CHC", 600)],
          pitching=[_pit(2, "Ace", "CHC", "180.0", 30, 30),
                    _pit(3, "Closer", "CHC", "60.0", 60, 0),
                    _pit(4, "Swing", "CHC", "70.0", 30, 8)])
    built = wbe.build(SEASON, log=lambda *a: None)
    t = built["teams"][0]
    assert (t["war_bat"], t["war_sp"], t["war_rp"], t["war_sw"]) == (3.0, 2.0, 1.0, 0.5)
    assert t["war"] == 6.5 and t["n_players"] == 4
    assert built["league"]["war"] == 6.5


def test_every_club_column_rounds_its_own_unrounded_sum(monkeypatch):
    """The module's thesis, one level up from the player row. A club column that
    added the SERVED tenths would carry one rounding error per player, and on a
    real club that is a fifth of a win.

    Every value here is deliberately off the tenth: two 0.44 hitters make 0.9
    and not the 0.8 two rounded cells give, three 0.04 relievers make 0.1 and
    not 0.0, two 0.26 starters make 0.5 and not 0.6. The league total is checked
    for the same reason (2.8, where the rounded rows give 2.7)."""
    _stub(monkeypatch,
          sides={1: {SEASON: {"bat": 0.44}}, 2: {SEASON: {"bat": 0.44}},
                 3: {SEASON: {"pit": 0.26}}, 4: {SEASON: {"pit": 0.26}},
                 5: {SEASON: {"pit": 0.04}}, 6: {SEASON: {"pit": 0.04}},
                 7: {SEASON: {"pit": 0.04}}, 8: {SEASON: {"pit": 1.26}}},
          hitting=[_hit(1, "Bat A", "CIN", 600), _hit(2, "Bat B", "CIN", 600)],
          pitching=[_pit(3, "SP A", "CIN", "180.0", 30, 30),
                    _pit(4, "SP B", "CIN", "170.0", 29, 29),
                    _pit(5, "RP A", "CIN", "60.0", 60, 0),
                    _pit(6, "RP B", "CIN", "55.0", 55, 0),
                    _pit(7, "RP C", "CIN", "50.0", 50, 0),
                    _pit(8, "Swing", "CIN", "70.0", 30, 8)])
    built = wbe.build(SEASON, log=lambda *a: None)
    t = built["teams"][0]
    assert t["war_bat"] == 0.9, "the Hitters column summed the ROUNDED rows"
    assert t["war_sp"] == 0.5, "the Starters column summed the ROUNDED rows"
    assert t["war_rp"] == 0.1, "the Relievers column summed the ROUNDED rows"
    assert t["war_sw"] == 1.3
    assert t["war"] == 2.8, "the club total summed the ROUNDED columns"
    assert built["league"]["war"] == 2.8, "the league total summed rounded rows"
    assert built["league"]["war_bat"] == 0.9
    assert built["league"]["war_pit"] == 1.9


def test_a_two_way_players_pitching_is_a_rotation_slot(monkeypatch):
    """PIT_BUCKET is read off the row's ROLE, and the role decides this one: a
    two-way player's pitching is a rotation slot (Starters), whatever his start
    share reads like in a season he opened in relief. Re-deriving the bucket
    from his innings here would file him under Relievers and disagree with the
    role his own row publishes."""
    _stub(monkeypatch,
          sides={1: {SEASON: {"bat": 2.0, "pit": 1.5}}},
          hitting=[_hit(1, "Two Way", "LAA", 500, pos="TWP")],
          pitching=[_pit(1, "Two Way", "LAA", "40.0", 40, 0, pos="TWP")])
    built = wbe.build(SEASON, log=lambda *a: None)
    assert built["players"][0]["role"] == "TWP"
    assert wbe._pitching_role(40.0, 40, 0) == "RP", "the fixture is not the case"
    t = built["teams"][0]
    assert (t["war_bat"], t["war_sp"], t["war_rp"]) == (2.0, 1.5, 0.0)


def test_war_earned_is_absent_for_a_club_that_cannot_be_named(monkeypatch):
    """Blank, never zero: a zero would read as a club that produced nothing."""
    _stub(monkeypatch,
          sides={1: {SEASON: {"bat": 3.0}}, 2: {SEASON: {"bat": 1.0}}},
          hitting=[_hit(1, "A", "CHC", 600), _hit(2, "B", "STL", 600)],
          pitching=[], earned={"CHC": 2.5})
    teams = {t["team"]: t for t in wbe.build(SEASON, log=lambda *a: None)["teams"]}
    assert teams["CHC"]["war_earned"] == 2.5
    assert "war_earned" not in teams["STL"]


def test_the_earned_basis_reads_stints_and_speaks_this_boards_dialect(monkeypatch):
    """The stint frame speaks Baseball-Reference (TBR, CHW) and this board
    speaks StatsAPI (TB, CWS). A club that resolves to neither is counted and
    dropped rather than silently folded into another club's total."""
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({
        "year_ID": [SEASON, SEASON, SEASON, SEASON - 1],
        "team_ID": ["TBR", "CHW", "XXX", "TBR"],
        "WAR": [1.25, 2.0, 9.0, 50.0],
        "mlb_ID": [1, 2, 3, 4],
        "name_common": ["A", "B", "C", "D"],
    })

    class _WarSourceStub:
        @staticmethod
        def stint_frame(side, **kw):
            return frame if side == "bat" else frame.iloc[0:0]

    monkeypatch.setitem(__import__("sys").modules, "war_source", _WarSourceStub)
    totals, meta = wbe._earned_by_club(SEASON, {"TBR": "TB", "CHW": "CWS"},
                                       log=lambda *a: None)
    assert totals == {"TB": 1.25, "CWS": 2.0}, "the season or the dialect leaked"
    assert meta["n_rows_unmapped"] == 1 and meta["unmapped_codes"] == ["XXX"]
    assert meta["available"] is True


def test_a_last_good_stint_frame_is_disclosed_on_the_earned_basis(monkeypatch):
    """war_source serves its cached parquet when the war_daily download fails
    and raises NOTHING: it records the side in served_stale() and expects a
    publisher to look (war_source.served_stale's own docstring). The Earned
    column is additive, so a cached frame is still served, but never silently:
    the age, the row count and the download error ride on the artifact the way
    fa_export carries stale_frames.

    Also pins the read count: both callers here share one frame per side,
    because pybaseball's bwar_pitch is NOT disk-cached and an unshared read is a
    second live download of war_daily_pitch.txt."""
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"year_ID": [SEASON], "team_ID": ["TBR"], "WAR": [1.25],
                          "mlb_ID": [1], "name_common": ["A"]})
    reads: list = []

    class _WarSourceStub:
        @staticmethod
        def stint_frame(side, **kw):
            reads.append(side)
            return frame

        @staticmethod
        def served_stale():
            return {"pit": {"age_days": 4.1234, "rows": 123,
                            "error": "HTTPError: 503"}}

    monkeypatch.setitem(__import__("sys").modules, "war_source", _WarSourceStub)
    totals, meta = wbe._earned_by_club(SEASON, {"TBR": "TB"}, log=lambda *a: None)
    assert totals == {"TB": 2.5}, "both sides are read"
    assert meta["stale_frames"] == {"pit": {"age_days": 4.12, "rows": 123,
                                           "error": "HTTPError: 503"}}
    assert "war_daily" in meta["degraded_why"]
    wbe._name_fallback(SEASON)
    assert reads == ["bat", "pit"], (
        f"the stint frames were read more than once per side: {reads}")


# --------------------------------------------------------------------------- #
# refusals and the payload the page reads
# --------------------------------------------------------------------------- #
def test_a_degenerate_war_read_refuses_the_write(monkeypatch, tmp_path):
    """The fa_projection.py:191-201 pattern. Below the coverage floor the
    previous data/war_leaderboards.json stays on disk and the run files RED:
    a board with four numbers on it and nine hundred blanks is the failure
    this guard exists for, not a thin board."""
    out = tmp_path / "war_leaderboards.json"
    out.write_text(json.dumps({"players": [{"mlbam": 1}], "teams": [{"team": "BOS"}]}),
                   encoding="utf-8")
    before = out.read_text(encoding="utf-8")
    filed = _stub(monkeypatch,
                  sides={1: {SEASON: {"bat": 1.0}}},
                  hitting=[_hit(i, f"H{i}", "BOS", 500) for i in range(1, 11)],
                  pitching=[], out=out)
    assert wbe.export(SEASON, log=lambda *a: None) == 0
    assert out.read_text(encoding="utf-8") == before, "the refusal overwrote the board"
    assert filed and filed[0][0] == "war_leaderboards"
    assert "war_leaderboards" in str(filed[0][1]) or "covered" in str(filed[0][1])


def _served_board(tmp_path):
    """A previous board on disk, to prove a refusal leaves it there."""
    out = tmp_path / "war_leaderboards.json"
    out.write_text(json.dumps({"players": [{"mlbam": 1}], "teams": [{"team": "BOS"}]}),
                   encoding="utf-8")
    return out, out.read_text(encoding="utf-8")


@pytest.mark.parametrize("dead", ["pitching", "hitting", "both"])
def test_a_dead_season_feed_refuses_rather_than_publishing_a_full_board(
        monkeypatch, tmp_path, dead):
    """THE FAILURE THE COVERAGE GUARD CANNOT SEE. load_season_pitching is a live
    StatsAPI call on every run. When a feed comes back empty the board still has
    a row for every player (the sides come from the eWAR artifact, which is
    fine), so it looks full: what is gone is the half of the league that feed
    named. Every arm loses his IP and falls through the role ladder into SW,
    both pitcher columns of all thirty clubs read 0.0, and the arms leave the
    club rollup entirely because their team came off that same feed.

    The eWAR coverage test divides by qualified lines FROM THE FEEDS, so a dead
    pitching feed leaves an all-hitter denominator that reads 100% covered. This
    guard measures each feed against the players who carry that side's eWAR
    cell, which is evidence from the other door."""
    out, before = _served_board(tmp_path)
    sides, hitting, pitching = _league(n=12)
    if dead in ("pitching", "both"):
        pitching = []
    if dead in ("hitting", "both"):
        hitting = []
    filed = _stub(monkeypatch, sides=sides, hitting=hitting, pitching=pitching,
                  out=out)
    assert wbe.export(SEASON, log=lambda *a: None) == 0
    assert out.read_text(encoding="utf-8") == before, (
        "a dead feed overwrote a good board")
    assert filed and filed[0][0] == "war_leaderboards"
    # "both" is red as well: with eWAR cells on hand for the season, a feed
    # that returns nothing is an outage whether one went or two. The quiet
    # skip below is the OTHER case, a season with no cells to miss.
    assert ("hitting" if dead == "both" else dead) in str(filed[0][1]), filed


def test_a_healthy_feed_pair_publishes(monkeypatch, tmp_path):
    """The other half of the guard above: the fixture it refuses is the SAME
    fixture with one feed removed, so the refusal is about the feed and not
    about the shape of the test."""
    out, _ = _served_board(tmp_path)
    sides, hitting, pitching = _league(n=12)
    filed = _stub(monkeypatch, sides=sides, hitting=hitting, pitching=pitching,
                  out=out)
    assert wbe.export(SEASON, log=lambda *a: None) == 24
    assert filed == [], "a healthy run filed a red"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["sources"]["feeds"]["refused"] is None
    assert doc["sources"]["feeds"]["pit_feed_share"] == 1.0
    assert doc["sources"]["feeds"]["bat_feed_share"] == 1.0
    assert {r["role"] for r in doc["players"]} == {"H", "RP"}


def test_a_season_with_no_line_yet_is_a_quiet_skip_not_a_red(monkeypatch, tmp_path):
    """January is not a failure. With no qualified line anywhere there is
    nothing to publish: the previous board stays and the run says so in the log.
    Filing this red would put an INGEST RED on the deploy shell every night
    from the last out to opening day, which is the nightly false red the
    SCHEDULED_EXPORTS comment warns teaches a reader to skip the section."""
    out, before = _served_board(tmp_path)
    filed = _stub(monkeypatch, sides={}, hitting=[], pitching=[], out=out)
    assert wbe.export(SEASON, log=lambda *a: None) == 0
    assert out.read_text(encoding="utf-8") == before
    assert filed == [], "an empty season filed a red"
    # a side map that holds cells for ANOTHER season is the same empty season
    filed.clear()
    _stub(monkeypatch, sides={1: {SEASON - 1: {"bat": 3.0}}}, hitting=[],
          pitching=[], out=out)
    assert wbe.export(SEASON, log=lambda *a: None) == 0
    assert filed == [], "last season's cells filed this season a red"
    built = wbe.build(SEASON, log=lambda *a: None)
    assert built["skipped"] and not built.get("refused")


def test_an_unreadable_side_map_refuses_rather_than_publishing_zeros(monkeypatch):
    def _boom():
        raise RuntimeError("pybaseball is down")

    monkeypatch.setattr(wbe, "_side_war_by_season", _boom)
    built = wbe.build(SEASON, log=lambda *a: None)
    assert built["refused"] and built["players"] == []


def test_the_payload_carries_the_build_stamp_and_both_disclosures(monkeypatch, tmp_path):
    """The eWAR build stamp rides every eWAR column on this page; this board is
    nothing but eWAR, so it always ships one. The team basis ships because the
    board has a team column and a club rollup."""
    out = tmp_path / "war_leaderboards.json"
    _stub(monkeypatch,
          sides={i: {SEASON: {"bat": 1.0}} for i in range(1, 21)},
          hitting=[_hit(i, f"H{i}", "BOS", 500) for i in range(1, 21)],
          pitching=[], earned={"BOS": 19.5}, out=out)
    monkeypatch.setattr(wbe, "_war_source_vintage",
                        lambda as_of=None: {"artifact_generated_at": "2026-09-16T09:47:15",
                                            "stale": False, "as_of": as_of})
    n = wbe.export(SEASON, log=lambda *a: None)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert n == 20 and len(doc["players"]) == 20
    assert list(doc)[:6] == ["generated_at", "season", "as_of", "ewar_vintage",
                             "team_basis", "qualified_rule"]
    assert doc["ewar_vintage"]["stale"] is False
    assert doc["team_basis"]["note"] and doc["team_basis"]["n_rows"] == 20
    assert doc["qualified_rule"] == {"min_pa": 100, "min_ip": 30}
    assert doc["qualified_rule"] == {"min_pa": wbe.QUAL_MIN_PA,
                                     "min_ip": wbe.QUAL_MIN_IP}
    # the page prints this rule; "PA >= 100.0" is not how a rule reads
    assert all(isinstance(v, int) for v in doc["qualified_rule"].values())
    assert doc["league"]["war"] == 20.0
    assert doc["teams"][0]["war_earned"] == 19.5
    assert doc["block_guard"]["players"]["n"] == 20


def test_boards_is_omitted_when_no_board_artifact_can_be_read(monkeypatch, tmp_path):
    """A missing file is not an empty board: `boards: []` on every row would
    read as a league nobody is on a leaderboard in."""
    real_membership = wbe._board_membership
    _stub(monkeypatch, sides={1: {SEASON: {"bat": 1.0}}},
          hitting=[_hit(1, "A", "BOS", 500)], pitching=[])
    # the real reader, pointed at an empty directory
    monkeypatch.setattr(wbe, "DATA_DIR", tmp_path)
    monkeypatch.setattr(wbe, "_board_membership", real_membership)
    built = wbe.build(SEASON, log=lambda *a: None)
    assert "boards" not in built["players"][0]
    assert len(built["sources"]["boards"]["missing"]) == len(wbe.BOARD_FILES)


# --------------------------------------------------------------------------- #
# the served artifact, and the boards it must never contaminate
# --------------------------------------------------------------------------- #
def _served():
    if not SERVED.exists():
        pytest.skip("data/war_leaderboards.json is not built on this machine")
    return json.loads(SERVED.read_text(encoding="utf-8"))


def test_the_served_board_is_whole_players_sorted_by_ewar():
    doc = _served()
    players = doc["players"]
    assert players and doc["teams"] and doc["league"]
    wars = [r["war"] for r in players]
    assert wars == sorted(wars, reverse=True), "the board does not open on eWAR"
    for r in players[:200]:
        sides = (r.get("war_bat") or 0.0) + (r.get("war_pit") or 0.0)
        assert abs(r["war"] - sides) <= 0.1, (r["name"], r["war"], sides)
        assert "war_bat" in r or "war_pit" in r
    assert {"war", "war_bat", "war_pit"} <= set(doc["league"])
    # the feed census the dead-feed guard is measured on rides with the board
    feeds = doc["sources"]["feeds"]
    assert feeds["refused"] is None
    assert feeds["pit_feed_share"] >= feeds["floor"]
    assert feeds["bat_feed_share"] >= feeds["floor"]
    for t in doc["teams"]:
        assert {"team", "war", "war_bat", "war_sp", "war_rp", "war_sw",
                "n_players"} <= set(t)
        # Each column rounds its OWN unrounded sum, so the four can miss the
        # served total by up to a quarter of a win (4 x 0.05, plus the total's
        # own 0.05). Anything past that is a column summing something else.
        parts = t["war_bat"] + t["war_sp"] + t["war_rp"] + t["war_sw"]
        assert abs(parts - t["war"]) <= 0.25, (t["team"], parts, t["war"])


def _two_sided(doc):
    """The served rows where one side and the sum are TELLABLE APART, which is
    the only place either invariant below can be tested."""
    return {r["mlbam"]: r for r in doc["players"]
            if r.get("war_bat") is not None and r.get("war_pit") is not None
            and abs(r["war"] - (r["war_bat"] or 0)) > 0.15
            and abs(r["war"] - (r["war_pit"] or 0)) > 0.15}


def test_no_rate_board_row_carries_a_summed_ewar():
    """THE INVARIANT THE RATE BOARDS LIVE BY. On Bullpen, Starters and Hitters
    the `war` beside WAR/IP+ and WAR/PA+ is ONE SIDE, because those columns
    divide by that side's denominator. If one of those rows ever starts carrying
    this payload's sum, the rate column beside it becomes arithmetic nonsense
    for every two-way player.

    DEFENSE IS DELIBERATELY NOT IN THIS LIST. Its row is the WHOLE player by
    owner decision O4 (defense_export._stamp_war sums the two sides unrounded
    and rounds once), because that board carries no WAR rate to contradict and
    its frame note exists to disclose the difference. The next test pins that
    side of it, so the two decisions cannot quietly swap places."""
    doc = _served()
    both = _two_sided(doc)
    if not both:
        pytest.skip("no two-sided player on the served board to test with")
    checked = 0
    for fname, key in (("bullpen_leaderboards.json", "relievers"),
                       ("starter_leaderboards.json", "starters"),
                       ("hitter_leaderboards.json", "hitters")):
        path = ROOT / "data" / fname
        if not path.exists():
            continue
        board = json.loads(path.read_text(encoding="utf-8"))
        for row in board.get(key) or []:
            mine = both.get(row.get("mlbam"))
            if mine is None or row.get("war") is None:
                continue
            checked += 1
            assert abs(row["war"] - mine["war"]) > 0.05, (
                f"{fname} row {row.get('name')} carries the SUMMED eWAR "
                f"({row['war']}); a rate board row must carry one side")
    if not checked:
        pytest.skip("no two-sided player is on a served rate board")


def test_the_defense_board_row_is_the_whole_player_and_agrees_with_this_one():
    """The other half of O4, and the reason the two boards can be read side by
    side: the Defense row's `war` is this payload's `war` for the same player.
    A serving Defense board that started carrying one side would disagree with
    the eWAR section by a two-way player's whole other half."""
    doc = _served()
    both = _two_sided(doc)
    path = ROOT / "data" / "defense_leaderboards.json"
    if not both or not path.exists():
        pytest.skip("no two-sided player on a served Defense board")
    board = json.loads(path.read_text(encoding="utf-8"))
    checked = 0
    for row in board.get("fielders") or []:
        mine = both.get(row.get("mlbam"))
        if mine is None or row.get("war") is None:
            continue
        checked += 1
        assert abs(row["war"] - mine["war"]) <= 0.05, (
            f"defense_leaderboards.json row {row.get('name')} carries "
            f"{row['war']} where the whole player is {mine['war']}")
    if not checked:
        pytest.skip("the served Defense board carries no two-sided `war` yet")


def test_the_board_is_catalogued_and_shipped():
    """data/war_leaderboards.json is fetched by /mlbstats/, so it must be in the
    catalog and must not be on the deploy's withhold list."""
    row = next((a for a in data_catalog.ARTIFACTS
                if a["file"] == "war_leaderboards.json"), None)
    assert row is not None, "the eWAR board is not in data_catalog.ARTIFACTS"
    assert row["group"] == "mlb" and row["stability"] in (data_catalog.STABLE,
                                                          data_catalog.EXPERIMENTAL)
    assert "war_leaderboards.json" not in data_catalog.excluded_files()


def test_the_pipeline_writes_it_on_both_paths():
    """A served artifact nothing rebuilds is a frozen board. Monthly 6b4j and
    the nightly 9e-pre0c both run it, and the ledger watches the name it files
    its refusals under."""
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    assert "6b4j" in src and "9e-pre0c" in src
    assert src.count("from war_board_export import export") == 2
    assert '"war_leaderboards",' in src, (
        "the refusal files under a name run_monthly does not watch, so it "
        "never reaches the deploy shell's INGEST RED")
