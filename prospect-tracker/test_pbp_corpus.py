# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for tools/build_pbp_corpus.py, above all the base-state reconstruction.

WHY THESE ARE HAND-BUILT. The corpus reads 19,132 cached winProbability
payloads, and the one derived thing in it that could be silently wrong is the
pre-play base state: the payload has no postOnFirst/Second/Third, so the state is
walked out of ``runners[].movement``. A cache-driven test cannot tell a correct
walk from a plausible one, so every case below is a synthetic play list where
the right answer is known by construction.

Four of these tests pin defects that were live in a draft of the walk and that
each cost measured accuracy against the payload's own ``playEvents[].offense``
block on a 240-game sample (2018 and 2023, 120 games each, 18,503 plays):

    test_multi_entry_runner_scores_once       lead-runner-first sort  94.80%
    test_bases_loaded_double_keeps_the_batter stepwise placement      99.63%
    test_midplay_pinch_runner_*               unaliased pinch runner  99.88%
    test_four_b_end_counts_as_a_run           "4B" read as a base     one lost run

Each of those four was re-introduced into a copy of the module and confirmed to
fail the test named beside it, so the tests are known to bite rather than merely
to pass. The half-inning reset and the automatic-runner seeding were checked the
same way.

With all four fixed the walk agrees with that independent block on 1.000000 of
18,041 comparable plays (399 excluded, see ``prepitch_baserunning``), leaves 5
invalid states in 18,503 plays (0.000270, all one payload defect class), and
reconciles outs and runs at 0 mismatches out of 18,503 each.

These are unit tests over PURE functions. Nothing here touches the network, the
real cache, or ``data/``.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import build_pbp_corpus as bpc  # noqa: E402


# ---------------------------------------------------------------------------
# synthetic payload builders
# ---------------------------------------------------------------------------
def _mv(start=None, end=None, is_out=False, out_base=None, out_number=None):
    """One ``runners[].movement`` block. ``start=None`` means the batter."""
    return {"originBase": start, "start": start, "end": end,
            "outBase": out_base, "isOut": is_out, "outNumber": out_number}


def _runner(rid, movement, play_index=5, event=None):
    return {"movement": movement,
            "details": {"runner": {"id": rid}, "playIndex": play_index,
                        "event": event}}


def _pitch(offense=None, ump=717, **pitch):
    """An ``isPitch`` playEvent. ``offense`` seeds the independent truth block."""
    ev = {
        "isPitch": True, "index": 0, "pitchNumber": 1, "playId": "pid-1",
        "type": "pitch",
        "details": {"call": {"code": pitch.pop("call", "S")},
                    "type": {"code": pitch.pop("ptype", "FF")},
                    "description": "Swinging Strike"},
        "pitchData": {"startSpeed": pitch.pop("speed", 94.1), "endSpeed": 86.0,
                      "zone": 5, "strikeZoneTop": 3.4, "strikeZoneBottom": 1.6,
                      "coordinates": {"pX": 0.11, "pZ": 2.4}},
        "officials": [{"official": {"id": ump}, "officialType": "Home Plate"},
                      {"official": {"id": 800}, "officialType": "First Base"}],
    }
    if offense is not None:
        ev["offense"] = offense
    return ev


def _action(event_type, description="", index=0, player_id=None,
            replaced_id=None, base=None, position=None, is_sub=False):
    ev = {"isPitch": False, "index": index, "type": "action",
          "details": {"eventType": event_type, "event": event_type,
                      "description": description}}
    if player_id is not None:
        ev["player"] = {"id": player_id}
    if replaced_id is not None:
        ev["replacedPlayer"] = {"id": replaced_id}
    if base is not None:
        ev["base"] = base
    if position is not None:
        ev["position"] = {"code": position}
    if is_sub:
        ev["isSubstitution"] = True
    return ev


def _play(at_bat_index, inning, half, outs_after, runners=(), *,
          event="Single", event_type="single", batter=1001, pitcher=9001,
          away=0, home=0, rbi=0, balls=0, strikes=0, play_events=None,
          leverage_index=1.10, drop_leverage_index=False):
    play = {
        "atBatIndex": at_bat_index,
        "about": {"atBatIndex": at_bat_index, "inning": inning,
                  "halfInning": half, "isComplete": True,
                  "startTime": "2023-05-04T18:10:00.000Z"},
        "result": {"type": "atBat", "event": event, "eventType": event_type,
                   "rbi": rbi, "awayScore": away, "homeScore": home},
        "count": {"balls": balls, "strikes": strikes, "outs": outs_after},
        "matchup": {"batter": {"id": batter}, "batSide": {"code": "R"},
                    "pitcher": {"id": pitcher}, "pitchHand": {"code": "L"}},
        "runners": list(runners),
        "playEvents": list(play_events) if play_events is not None else [_pitch()],
        "dramaIndex": 12.0,
        "homeTeamWinProbability": 51.5,
        "awayTeamWinProbability": 48.5,
        "homeTeamWinProbabilityAdded": 1.5,
    }
    if not drop_leverage_index:
        play["leverageIndex"] = leverage_index
    return play


def _state(row):
    return (row["on_first"], row["on_second"], row["on_third"])


# ---------------------------------------------------------------------------
# the hand-built base-state cases
# ---------------------------------------------------------------------------
class TestBaseStateWalk:
    def test_leadoff_walk_then_double_puts_runner_on_third(self):
        plays = [
            _play(0, 1, "top", 0, [_runner(101, _mv(end="1B"))],
                  event="Walk", event_type="walk", batter=101),
            _play(1, 1, "top", 0,
                  [_runner(102, _mv(end="2B")), _runner(101, _mv("1B", "3B"))],
                  event="Double", event_type="double", batter=102),
            _play(2, 1, "top", 1, [_runner(103, _mv(is_out=True, out_base="1B", out_number=1))],
                  event="Strikeout", event_type="strikeout", batter=103),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[0]) == (None, None, None)
        # the double is hit with the walk on first
        assert _state(rows[1]) == (101, None, None)
        # and leaves the batter on second, the walk on third
        assert _state(rows[2]) == (None, 102, 101)
        assert [r["outs_before"] for r in rows] == [0, 0, 0]

    def test_fielders_choice_retires_lead_runner_and_seats_batter(self):
        plays = [
            _play(0, 3, "bottom", 0, [_runner(101, _mv(end="1B"))],
                  event="Walk", event_type="walk", batter=101),
            _play(1, 3, "bottom", 1,
                  [_runner(101, _mv("1B", is_out=True, out_base="2B", out_number=1)),
                   _runner(102, _mv(end="1B"))],
                  event="Fielders Choice Out", event_type="fielders_choice_out",
                  batter=102),
            _play(2, 3, "bottom", 1, [], event="Walk", event_type="walk", batter=103),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[1]) == (101, None, None)
        assert _state(rows[2]) == (102, None, None)
        assert rows[2]["outs_before"] == 1

    def test_caught_stealing_clears_the_runner(self):
        plays = [
            _play(0, 5, "top", 0, [_runner(101, _mv(end="1B"))],
                  event="Single", batter=101),
            _play(1, 5, "top", 2,
                  [_runner(101, _mv("1B", is_out=True, out_base="2B", out_number=1),
                           play_index=2, event="Caught Stealing 2B"),
                   _runner(102, _mv(is_out=True, out_base="1B", out_number=2),
                           play_index=5)],
                  event="Strikeout", event_type="strikeout", batter=102),
            _play(2, 5, "top", 2, [], event="Walk", event_type="walk", batter=103),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[1]) == (101, None, None)
        assert _state(rows[2]) == (None, None, None)
        assert rows[2]["outs_before"] == 2
        assert rows[1]["runs_scored_on_play"] == 0

    def test_home_run_with_two_on_scores_three_and_empties_the_bases(self):
        plays = [
            _play(0, 7, "bottom", 0, [_runner(101, _mv(end="1B"))],
                  event="Walk", event_type="walk", batter=101),
            _play(1, 7, "bottom", 0,
                  [_runner(102, _mv(end="1B")), _runner(101, _mv("1B", "2B"))],
                  event="Single", batter=102),
            _play(2, 7, "bottom", 0,
                  [_runner(103, _mv(end="score")),
                   _runner(101, _mv("2B", "score")),
                   _runner(102, _mv("1B", "score"))],
                  event="Home Run", event_type="home_run", batter=103, rbi=3, home=3),
            _play(3, 7, "bottom", 1,
                  [_runner(104, _mv(is_out=True, out_base="1B", out_number=1))],
                  event="Groundout", event_type="field_out", batter=104, home=3),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[2]) == (102, 101, None)
        assert rows[2]["runs_scored_on_play"] == 3
        assert _state(rows[3]) == (None, None, None)

    def test_double_play_records_two_outs_and_clears_both_men(self):
        plays = [
            _play(0, 2, "top", 0, [_runner(101, _mv(end="1B"))],
                  event="Single", batter=101),
            _play(1, 2, "top", 2,
                  [_runner(101, _mv("1B", is_out=True, out_base="2B", out_number=1)),
                   _runner(102, _mv(is_out=True, out_base="1B", out_number=2))],
                  event="Grounded Into DP", event_type="grounded_into_double_play",
                  batter=102),
            _play(2, 2, "top", 2, [], event="Walk", event_type="walk", batter=103),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[2]) == (None, None, None)
        assert rows[2]["outs_before"] == 2

    def test_half_inning_change_resets_bases_and_outs(self):
        plays = [
            _play(0, 4, "top", 0, [_runner(101, _mv(end="1B"))],
                  event="Single", batter=101),
            _play(1, 4, "top", 3,
                  [_runner(101, _mv("1B", is_out=True, out_base="2B", out_number=2)),
                   _runner(102, _mv(is_out=True, out_base="1B", out_number=3))],
                  event="Grounded Into DP", event_type="grounded_into_double_play",
                  batter=102),
            _play(2, 4, "bottom", 0, [], event="Walk", event_type="walk", batter=201),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[2]) == (None, None, None)
        assert rows[2]["outs_before"] == 0
        assert rows[1]["outs_after"] == 3

    def test_outs_never_decrease_inside_a_half_inning(self):
        plays = [
            _play(0, 1, "top", 1, [_runner(101, _mv(is_out=True, out_base="1B", out_number=1))],
                  event="Groundout", event_type="field_out", batter=101),
            _play(1, 1, "top", 2, [_runner(102, _mv(is_out=True, out_base="1B", out_number=2))],
                  event="Groundout", event_type="field_out", batter=102),
        ]
        diag: dict = {}
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023, diag=diag)
        assert [r["outs_before"] for r in rows] == [0, 1]
        assert diag.get("invalid_outs_decrease", 0) == 0
        assert diag.get("invalid_outs_gt3", 0) == 0
        assert diag.get("outs_walk_mismatch", 0) == 0


# ---------------------------------------------------------------------------
# the four defects the draft walk actually had
# ---------------------------------------------------------------------------
class TestReconstructionDefectsFixed:
    def test_multi_entry_runner_scores_once(self):
        """2B to 3B on the hit, then 3B to score on the throw, is ONE runner.

        A lead-runner-first sort applied the second step before the first and
        left him standing on third with the run still counted.
        """
        plays = [
            _play(0, 6, "top", 0, [_runner(101, _mv(end="2B"))],
                  event="Double", event_type="double", batter=101),
            _play(1, 6, "top", 0,
                  [_runner(102, _mv(end="2B"), play_index=4),
                   _runner(101, _mv("2B", "3B"), play_index=4),
                   _runner(101, _mv("3B", "score"), play_index=4)],
                  event="Double", event_type="double", batter=102, rbi=1, away=1),
            _play(2, 6, "top", 0, [], event="Walk", event_type="walk", batter=103,
                  away=1),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert rows[1]["on_second"] == 101 and rows[1]["on_third"] is None
        assert rows[1]["runs_scored_on_play"] == 1
        # he scored, so third is empty and only the new double is on base
        assert _state(rows[2]) == (None, 102, None)

    def test_bases_loaded_double_keeps_the_batter(self):
        """Stepwise placement LOSES the batter when paths are multi-hop.

        Shape taken from game_pk 529410 atBatIndex 56. Bases loaded, the batter
        doubles and the payload records him null-to-1B then 1B-to-2B, while the
        man who started on first is recorded 1B-to-2B then 2B-to-3B. Applied one
        step at a time: the batter is written to 1B (evicting the runner there),
        moves on to 2B, and then that runner's own 1B-to-2B step overwrites the
        batter at second. He vanishes. Net destinations cannot lose him.
        """
        loaded = [
            _play(0, 8, "bottom", 0, [_runner(201, _mv(end="1B"))], batter=201),
            _play(1, 8, "bottom", 0,
                  [_runner(202, _mv(end="1B")), _runner(201, _mv("1B", "2B"))],
                  batter=202),
            _play(2, 8, "bottom", 0,
                  [_runner(203, _mv(end="1B")), _runner(202, _mv("1B", "2B")),
                   _runner(201, _mv("2B", "3B"))],
                  batter=203),
            # bases loaded, batter doubles, two score, the trail runner to third
            _play(3, 8, "bottom", 0,
                  [_runner(204, _mv(end="1B"), play_index=6),
                   _runner(204, _mv("1B", "2B"), play_index=6),
                   _runner(201, _mv("3B", "score"), play_index=6),
                   _runner(202, _mv("2B", "3B"), play_index=6),
                   _runner(202, _mv("3B", "score"), play_index=6),
                   _runner(203, _mv("1B", "2B"), play_index=6),
                   _runner(203, _mv("2B", "3B"), play_index=6)],
                  event="Double", event_type="double", batter=204, rbi=2, home=2),
            _play(4, 8, "bottom", 0, [], event="Walk", event_type="walk",
                  batter=205, home=2),
        ]
        rows = bpc.reconstruct_plays(loaded, game_pk=529410, season=2023)
        assert _state(rows[3]) == (203, 202, 201)
        assert rows[3]["runs_scored_on_play"] == 2
        # the batter must still be on second, the trail runner on third
        assert _state(rows[4]) == (None, 204, 203)

    def test_midplay_pinch_runner_is_not_seated_pre_play(self):
        """A pinch runner who enters DURING the play was not on base when it
        began, so his ``movement.start`` is not pre-play evidence."""
        sub = _action("offensive_substitution",
                      "Offensive Substitution: Pinch-runner B replaces A.",
                      index=3, player_id=488721, replaced_id=435559, position="12",
                      is_sub=True)
        plays = [
            _play(0, 8, "bottom", 0, [_runner(435559, _mv(end="1B"))], batter=435559),
            _play(1, 8, "bottom", 0,
                  [_runner(435559, _mv("1B", "2B"), play_index=1),
                   _runner(435559, _mv("2B", "3B"), play_index=1),
                   _runner(605512, _mv(end="1B"), play_index=6),
                   _runner(488721, _mv("3B", "score"), play_index=6)],
                  batter=605512, rbi=1, home=1,
                  play_events=[_pitch(), sub]),
            _play(2, 8, "bottom", 1,
                  [_runner(621020, _mv(is_out=True, out_base="1B", out_number=1))],
                  event="Strikeout", event_type="strikeout", batter=621020, home=1),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        # pre-play: the ORIGINAL runner on first, the substitute nowhere
        assert _state(rows[1]) == (435559, None, None)
        assert rows[1]["runs_scored_on_play"] == 1

    def test_midplay_pinch_runner_leaves_no_phantom(self):
        """The relieved runner must not keep a bag for the rest of the inning."""
        sub = _action("offensive_substitution",
                      "Offensive Substitution: Pinch-runner B replaces A.",
                      index=3, player_id=488721, replaced_id=435559, position="12",
                      is_sub=True)
        plays = [
            _play(0, 8, "bottom", 0, [_runner(435559, _mv(end="1B"))], batter=435559),
            _play(1, 8, "bottom", 0,
                  [_runner(435559, _mv("1B", "2B"), play_index=1),
                   _runner(435559, _mv("2B", "3B"), play_index=1),
                   _runner(605512, _mv(end="1B"), play_index=6),
                   _runner(488721, _mv("3B", "score"), play_index=6)],
                  batter=605512, rbi=1, home=1,
                  play_events=[_pitch(), sub]),
            _play(2, 8, "bottom", 1,
                  [_runner(621020, _mv(is_out=True, out_base="1B", out_number=1))],
                  event="Strikeout", event_type="strikeout", batter=621020, home=1),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[2]) == (605512, None, None)

    def test_four_b_end_counts_as_a_run(self):
        """``end == '4B'`` means the runner reached home. Reading it as an
        unknown base loses the run (game_pk 716358, atBatIndex 34)."""
        plays = [
            _play(0, 5, "top", 0,
                  [_runner(663656, _mv(end="score"), play_index=2),
                   _runner(663656, _mv(end="4B"), play_index=2)],
                  event="Triple", event_type="triple", batter=663656, rbi=1, away=1),
            _play(1, 5, "top", 0, [], event="Walk", event_type="walk", batter=2,
                  away=1),
        ]
        diag: dict = {}
        rows = bpc.reconstruct_plays(plays, game_pk=716358, season=2023, diag=diag)
        assert rows[0]["runs_scored_on_play"] == 1
        assert diag.get("unknown_movement_end", 0) == 0
        assert diag.get("runs_mismatch", 0) == 0
        assert _state(rows[1]) == (None, None, None)


class TestActionsThatMoveRunnersWithoutMovements:
    def test_extra_innings_automatic_runner_is_seated_on_second(self):
        placed = _action("runner_placed", "Aaron Hicks starts inning at 2nd base.",
                         index=0, player_id=543305, base=2)
        plays = [
            _play(0, 10, "top", 1,
                  [_runner(602104, _mv(is_out=True, out_base="1B", out_number=1))],
                  event="Strikeout", event_type="strikeout", batter=602104,
                  play_events=[placed, _pitch()]),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[0]) == (None, 543305, None)

    def test_pinch_runner_announced_before_the_first_pitch_takes_the_bag(self):
        sub = _action("offensive_substitution",
                      "Offensive Substitution: Pinch-runner X replaces Y.",
                      index=0, player_id=606192, replaced_id=624512, base=2,
                      position="12", is_sub=True)
        plays = [
            _play(0, 8, "top", 0, [_runner(624512, _mv(end="2B"))],
                  event="Double", event_type="double", batter=624512),
            _play(1, 8, "top", 1,
                  [_runner(700, _mv(is_out=True, out_base="1B", out_number=1))],
                  event="Strikeout", event_type="strikeout", batter=700,
                  play_events=[sub, _pitch()]),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert _state(rows[1]) == (None, 606192, None)


# ---------------------------------------------------------------------------
# missing / odd payload fields
# ---------------------------------------------------------------------------
class TestMissingFields:
    def test_missing_leverage_index_does_not_crash(self):
        plays = [
            _play(0, 1, "top", 0, [_runner(101, _mv(end="1B"))], batter=101,
                  drop_leverage_index=True),
            _play(1, 1, "top", 1,
                  [_runner(102, _mv(is_out=True, out_base="1B", out_number=1))],
                  event="Strikeout", event_type="strikeout", batter=102),
        ]
        rows = bpc.reconstruct_plays(plays, game_pk=1, season=2023)
        assert rows[0]["leverage_index"] is None
        assert rows[1]["leverage_index"] == pytest.approx(1.10)
        assert _state(rows[1]) == (101, None, None)

    def test_empty_and_missing_blocks_are_survivable(self):
        rows = bpc.reconstruct_plays([{}], game_pk=1, season=2023)
        assert len(rows) == 1
        assert _state(rows[0]) == (None, None, None)
        assert rows[0]["outs_before"] == 0
        assert bpc.reconstruct_plays([], game_pk=1, season=2023) == []
        assert bpc.reconstruct_plays(None, game_pk=1, season=2023) == []

    def test_win_probability_before_is_after_minus_added(self):
        rows = bpc.reconstruct_plays([_play(0, 1, "top", 0)], game_pk=1, season=2023)
        assert rows[0]["wp_home_after"] == pytest.approx(51.5)
        assert rows[0]["wpa_home"] == pytest.approx(1.5)
        assert rows[0]["wp_home_before"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# the independent truth block and its comparability guard
# ---------------------------------------------------------------------------
class TestTruthBlock:
    def test_truth_reads_the_first_pitch_offense_block(self):
        play = _play(0, 1, "top", 0, play_events=[
            _pitch(offense={"batter": {"id": 5}, "first": {"id": 101},
                            "third": {"id": 103}})])
        assert bpc.truth_bases(play) == {"1B": 101, "2B": None, "3B": 103}

    def test_truth_is_none_when_the_play_has_no_pitch(self):
        play = _play(0, 1, "top", 0, play_events=[_action("game_advisory", "x")])
        assert bpc.truth_bases(play) is None

    def test_prepitch_baserunning_flags_a_pickoff_error(self):
        play = _play(0, 1, "top", 0, play_events=[
            {"isPitch": False, "index": 0, "type": "pickoff",
             "details": {"description": "Pickoff Attempt 1B"}},
            _action("pickoff_error_1b", "Throwing error on the pickoff.", index=1),
            _pitch(offense={"batter": {"id": 5}, "second": {"id": 101}})])
        assert bpc.prepitch_baserunning(play) is True

    def test_prepitch_baserunning_ignores_actions_after_the_first_pitch(self):
        play = _play(0, 1, "top", 0, play_events=[
            _pitch(), _action("stolen_base_2b", "steals 2nd", index=1)])
        assert bpc.prepitch_baserunning(play) is False

    def test_a_mound_visit_is_not_baserunning(self):
        play = _play(0, 1, "top", 0, play_events=[
            _action("mound_visit", "Mound Visit.", index=0), _pitch()])
        assert bpc.prepitch_baserunning(play) is False


# ---------------------------------------------------------------------------
# pitch and event flattening
# ---------------------------------------------------------------------------
class TestPitchAndEventRows:
    def test_pitch_row_carries_physics_and_the_home_plate_umpire(self):
        play = _play(7, 3, "top", 0, play_events=[_pitch(ump=623949)])
        rows = bpc.pitch_rows([play], game_pk=42, season=2023)
        assert len(rows) == 1
        r = rows[0]
        assert r["game_pk"] == 42 and r["season"] == 2023
        assert r["at_bat_index"] == 7 and r["pitch_number"] == 1
        assert r["call_code"] == "S" and r["pitch_type"] == "FF"
        assert r["start_speed"] == pytest.approx(94.1)
        assert r["plate_x"] == pytest.approx(0.11)
        assert r["sz_top"] == pytest.approx(3.4)
        assert r["home_plate_umpire_id"] == 623949
        assert r["is_pitch"] is True

    def test_pitch_rows_skip_non_pitch_events(self):
        play = _play(0, 1, "top", 0,
                     play_events=[_action("mound_visit", "Mound Visit."), _pitch()])
        assert len(bpc.pitch_rows([play], 1, 2023)) == 1

    def test_event_row_keeps_the_description_verbatim(self):
        text = "Offensive Substitution: Pinch-runner Teoscar Hernandez replaces Reese McGuire."
        sub = _action("offensive_substitution", text, index=2, player_id=606192,
                      replaced_id=624512, base=2, position="12", is_sub=True)
        rows = bpc.event_rows([_play(9, 4, "bottom", 0,
                                     play_events=[sub, _pitch()])], 42, 2023)
        assert len(rows) == 1
        r = rows[0]
        assert r["description"] == text
        assert r["is_substitution"] is True
        assert r["player_id"] == 606192 and r["replaced_player_id"] == 624512
        assert r["base"] == 2 and r["position_code"] == "12"
        assert r["at_bat_index"] == 9 and r["index"] == 2

    def test_event_rows_exclude_pitches(self):
        play = _play(0, 1, "top", 0, play_events=[_pitch(), _pitch()])
        assert bpc.event_rows([play], 1, 2023) == []


# ---------------------------------------------------------------------------
# season identification
# ---------------------------------------------------------------------------
class TestSeason:
    def test_season_from_parsed_payload(self):
        assert bpc.season_of_plays([_play(0, 1, "top", 0)]) == 2023
        assert bpc.season_of_plays([]) is None
        assert bpc.season_of_plays([{}]) is None

    def test_sniff_season_matches_the_full_parse(self, tmp_path):
        p = tmp_path / "716358.json"
        p.write_text(json.dumps([_play(0, 1, "top", 0)]), encoding="utf-8")
        assert bpc.sniff_season(p) == 2023
        assert bpc.sniff_season(p) == bpc.season_of_plays(json.loads(p.read_text()))

    def test_sniff_season_on_a_missing_file_is_none(self, tmp_path):
        assert bpc.sniff_season(tmp_path / "nope.json") is None


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------
class TestManifest:
    def test_new_manifest_is_well_formed(self):
        assert bpc.validate_manifest(bpc.new_manifest()) == []

    def test_season_block_needs_games_files_and_every_table(self):
        man = bpc.new_manifest()
        man["seasons"]["2023"] = {"games": 5, "files": [],
                                  "rows": {"plays": 1, "pitches": 2, "events": 3}}
        assert bpc.validate_manifest(man) == []

    def test_missing_table_row_count_is_reported(self):
        man = bpc.new_manifest()
        man["seasons"]["2023"] = {"games": 5, "files": [], "rows": {"plays": 1}}
        problems = bpc.validate_manifest(man)
        assert any("pitches" in p for p in problems)
        assert any("events" in p for p in problems)

    def test_non_year_season_key_is_reported(self):
        man = bpc.new_manifest()
        man["seasons"]["latest"] = {"games": 1, "files": [],
                                    "rows": {t: 0 for t in bpc.TABLES}}
        assert any("not a year" in p for p in bpc.validate_manifest(man))

    def test_missing_top_level_key_is_reported(self):
        man = bpc.new_manifest()
        del man["validation"]
        assert any("validation" in p for p in bpc.validate_manifest(man))

    def test_counters_aggregate_across_seasons(self):
        man = bpc.new_manifest()
        man["seasons"]["2018"] = {"counters": {"state_checked": 10, "runs_checked": 10,
                                               "runs_mismatch": 1}}
        man["seasons"]["2023"] = {"counters": {"state_checked": 30, "runs_checked": 30,
                                               "runs_mismatch": 0}}
        total = bpc.aggregate_counters(man)
        assert total["state_checked"] == 40
        assert bpc.rates(total)["runs_mismatch_rate"] == pytest.approx(0.025)

    def test_rates_are_divide_by_zero_safe(self):
        r = bpc.rates({})
        assert r["invalid_state_rate"] is None
        assert r["base_occupancy_agree_rate"] is None
        assert r["runs_mismatch_rate"] is None


# ---------------------------------------------------------------------------
# end to end over a synthetic cache
# ---------------------------------------------------------------------------
def _game(pk, season):
    year = f"{season}-05-04T18:10:00.000Z"
    plays = [
        _play(0, 1, "top", 0, [_runner(101, _mv(end="1B"))],
              event="Walk", event_type="walk", batter=101),
        _play(1, 1, "top", 0,
              [_runner(102, _mv(end="2B")), _runner(101, _mv("1B", "score"))],
              event="Double", event_type="double", batter=102, rbi=1, away=1),
        _play(2, 1, "top", 1,
              [_runner(103, _mv(is_out=True, out_base="1B", out_number=1))],
              event="Strikeout", event_type="strikeout", batter=103, away=1),
    ]
    for p in plays:
        p["about"]["startTime"] = year
    return plays


class TestBuildEndToEnd:
    def _cache(self, tmp_path):
        cache = tmp_path / "win_prob"
        cache.mkdir(parents=True)
        for pk, season in ((529406, 2018), (529407, 2018), (716358, 2023)):
            (cache / f"{pk}.json").write_text(json.dumps(_game(pk, season)),
                                              encoding="utf-8")
        return cache

    def test_build_writes_partitioned_tables_and_a_manifest(self, tmp_path):
        pytest.importorskip("pyarrow")
        cache = self._cache(tmp_path)
        out = tmp_path / "pbp_corpus"
        man = bpc.build(cache, out)

        assert sorted(man["seasons"]) == ["2018", "2023"]
        assert man["source_files_total"] == 3
        assert man["seasons"]["2018"]["games"] == 2
        assert man["seasons"]["2018"]["rows"]["plays"] == 6
        assert man["seasons"]["2023"]["rows"]["plays"] == 3
        assert bpc.validate_manifest(man) == []
        assert bpc.manifest_path(out).exists()
        for table in bpc.TABLES:
            assert bpc.table_path(out, table, 2018).exists()
            assert bpc.table_path(out, table, 2023).exists()

    def test_tables_read_back_whole_and_one_file_at_a_time(self, tmp_path):
        pq = pytest.importorskip("pyarrow.parquet")
        cache = self._cache(tmp_path)
        out = tmp_path / "pbp_corpus"
        bpc.build(cache, out)

        # the directory layout must NOT trip arrow's hive partition inference
        every = pq.read_table(out / "plays")
        assert every.num_rows == 9
        assert sorted(set(every.column("season").to_pylist())) == [2018, 2023]

        one = pq.read_table(bpc.table_path(out, "plays", 2023)).to_pydict()
        assert one["season"] == [2023, 2023, 2023]
        assert one["on_first"] == [None, 101, None]
        assert one["runs_scored_on_play"] == [0, 1, 0]

    def test_rebuild_skips_finished_seasons_unless_forced(self, tmp_path):
        pytest.importorskip("pyarrow")
        cache = self._cache(tmp_path)
        out = tmp_path / "pbp_corpus"
        bpc.build(cache, out)
        again = bpc.build(cache, out)
        # skipped, so this invocation records no new build time for the season
        assert again["seasons"]["2018"]["games"] == 2
        forced = bpc.build(cache, out, seasons={2018}, force=True)
        assert forced["seasons"]["2018"]["games"] == 2
        # forcing one season must not erase the other season's manifest row
        assert "2023" in forced["seasons"]

    def test_limit_caps_games_per_season(self, tmp_path):
        pytest.importorskip("pyarrow")
        cache = self._cache(tmp_path)
        out = tmp_path / "pbp_corpus"
        man = bpc.build(cache, out, limit=1)
        assert man["seasons"]["2018"]["games"] == 1
        assert man["seasons"]["2023"]["games"] == 1

    def test_a_capped_season_is_never_treated_as_complete(self, tmp_path):
        """Otherwise the next uncapped build skips it and ships a partial corpus."""
        pytest.importorskip("pyarrow")
        cache = self._cache(tmp_path)
        out = tmp_path / "pbp_corpus"
        capped = bpc.build(cache, out, limit=1)
        assert capped["seasons"]["2018"]["complete"] is False
        # the files exist, but an uncapped rebuild must still walk every game
        full = bpc.build(cache, out)
        assert full["seasons"]["2018"]["complete"] is True
        assert full["seasons"]["2018"]["games"] == 2
        assert full["seasons"]["2018"]["rows"]["plays"] == 6

    def test_dry_run_writes_nothing(self, tmp_path):
        cache = self._cache(tmp_path)
        out = tmp_path / "pbp_corpus"
        man = bpc.build(cache, out, dry_run=True)
        assert man["seasons"]["2018"]["rows"]["plays"] == 6
        assert not out.exists()

    def test_validation_block_is_clean_on_well_formed_input(self, tmp_path):
        cache = self._cache(tmp_path)
        out = tmp_path / "pbp_corpus"
        v = bpc.build(cache, out, dry_run=True)["validation"]
        assert v["invalid_state_plays"] == 0
        assert v["runs_mismatch"] == 0
        assert v["outs_walk_mismatch"] == 0
        assert v["plays_checked"] == 9

    def test_unreadable_payload_is_counted_not_fatal(self, tmp_path):
        cache = self._cache(tmp_path)
        (cache / "999999.json").write_text("{not json", encoding="utf-8")
        out = tmp_path / "pbp_corpus"
        man = bpc.build(cache, out, dry_run=True)
        # the bad file has no sniffable season, so it never enters a season bucket
        assert sorted(man["seasons"]) == ["2018", "2023"]
        assert man["seasons"]["2018"]["games"] == 2
