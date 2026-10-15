# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Scores plays tab reads every review (docs/eabs-2026-10-15/ABS_LEDGER.md
section 7).

Pinned: a pitch-level ABS challenge (MJ) is read as its own review and never
merged with a replay challenge (MF) on the same play; a play-level MJ belongs to
the plate appearance's last pitch; the job's winProbability fields filter asks
for the review fields; the plays tab names an ABS challenge in words."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import scores_core as sc  # noqa: E402


def _pitch(i, n, code, balls, strikes, outs, review=None):
    e = {"index": i, "pitchNumber": n, "isPitch": True, "type": "pitch",
         "details": {"call": {"code": code}}, "count": {"balls": balls, "strikes": strikes, "outs": outs},
         "pitchData": {"coordinates": {"pX": 0.8, "pZ": 1.7}, "strikeZoneTop": 3.3, "strikeZoneBottom": 1.6}}
    if review:
        e["reviewDetails"] = review
    return e


def _rev(kind, team, over, pid=None, extra=None):
    r = {"isOverturned": over, "inProgress": False, "reviewType": kind, "challengeTeamId": team}
    if pid is not None:
        r["player"] = {"id": pid, "fullName": f"Player {pid}"}
    if extra:
        r["additionalReviews"] = extra
    return r


def _player(pid, order, pos):
    return {"person": {"id": pid}, "battingOrder": order, "allPositions": [{"code": pos}]}


def _feed():
    """Away 147 bats in the top; home 118 fields with pitcher 10 and catcher 20.
    PA 0: the catcher's challenge on pitch 2 is overturned (ball to strike); a
    steal before pitch 3; the batter's challenge of strike three stands on the
    play. PA 1: a new catcher (21) comes in, then the pitcher challenges."""
    pa0 = {"atBatIndex": 0, "about": {"atBatIndex": 0, "inning": 1, "halfInning": "top", "isComplete": True},
           "matchup": {"batter": {"id": 1}, "pitcher": {"id": 10}, "postOnFirst": None},
           "count": {"balls": 1, "strikes": 3, "outs": 1}, "result": {"awayScore": 0, "homeScore": 0},
           "runners": [{"movement": {"start": "1B", "end": "2B", "isOut": False},
                        "details": {"playIndex": 2, "runner": {"id": 5}}}],
           "playEvents": [_pitch(0, 1, "B", 1, 0, 0),
                          _pitch(1, 2, "C", 1, 1, 0, _rev("MJ", 118, True, 20)),
                          {"index": 2, "type": "action", "isPitch": False, "details": {"eventType": "stolen_base_2b"},
                           "count": {"balls": 1, "strikes": 1, "outs": 0}},
                          _pitch(3, 3, "C", 1, 2, 0),
                          _pitch(4, 4, "C", 1, 3, 1)],
           "reviewDetails": _rev("MJ", 147, False, 1, extra=[_rev("MF", 118, True)])}
    pa0["matchup"]["postOnSecond"] = {"id": 5}
    pa1 = {"atBatIndex": 1, "about": {"atBatIndex": 1, "inning": 1, "halfInning": "top", "isComplete": True},
           "matchup": {"batter": {"id": 2}, "pitcher": {"id": 10}},
           "count": {"balls": 0, "strikes": 0, "outs": 2}, "result": {"awayScore": 0, "homeScore": 0},
           "runners": [],
           "playEvents": [{"index": 0, "type": "action", "isPitch": False, "isSubstitution": True,
                           "player": {"id": 21}, "position": {"code": "2"}, "details": {},
                           "count": {"balls": 0, "strikes": 0, "outs": 1}},
                          _pitch(1, 1, "B", 1, 0, 1, _rev("MJ", 118, False, 10)),
                          _pitch(2, 2, "X", 1, 0, 2)]}
    box = {"teams": {
        "away": {"pitchers": [30], "players": {"ID1": _player(1, "100", "8"), "ID2": _player(2, "200", "6"),
                                               "ID5": _player(5, "300", "3"), "ID30": _player(30, None, "1")}},
        "home": {"pitchers": [10], "players": {"ID20": _player(20, "200", "2"), "ID21": _player(21, "201", "2"),
                                               "ID10": _player(10, None, "1")}}}}
    return {"gamePk": 999, "gameData": {
                "game": {"pk": 999, "type": "R", "season": "2026"}, "datetime": {"officialDate": "2026-05-01"},
                "teams": {"away": {"id": 147, "sport": {"id": 1}}, "home": {"id": 118, "sport": {"id": 1}}},
                "absChallenges": {"hasChallenges": True, "away": {"usedSuccessful": 0, "usedFailed": 1},
                                  "home": {"usedSuccessful": 1, "usedFailed": 1}}},
            "liveData": {"plays": {"allPlays": [pa0, pa1]}, "boxscore": box,
                         "linescore": {"scheduledInnings": 9}}}


# --------------------------------------------------------------------------- #
# The Scores reader
# --------------------------------------------------------------------------- #
def test_pitch_level_abs_challenges_are_read_and_never_merged_with_replay_challenges():
    pa = _feed()["liveData"]["plays"]["allPlays"][0]
    revs = sc.play_reviews(pa, {20: "Catcher", 1: "Batter"})
    assert [(r["kind"], r["by"], r["overturned"], r["pitch"]) for r in revs] == [
        ("MJ", "KCR", True, 2),    # the pitch-level challenge the old reader dropped
        ("MJ", "NYY", False, 4),   # play-level: the plate appearance's last pitch
        ("MF", "KCR", True, None),  # a replay challenge in additionalReviews keeps its own kind
    ]
    assert revs[0]["player"] == "Catcher" and revs[2]["player"] is None


def test_the_plays_tab_rows_carry_every_review():
    rows = sc.play_rows(_feed()["liveData"]["plays"]["allPlays"], {"away": "NYY", "home": "KCR"}, season=2026)
    assert [len(r["reviews"]) for r in rows] == [3, 1]
    assert rows[1]["reviews"][0] == {"by": "KCR", "overturned": False, "kind": "MJ", "pitch": 1, "player": "10"}


def test_the_job_fields_filter_requests_the_review_fields():
    src = (ROOT / "tools" / "scores_job.py").read_text(encoding="utf-8")
    m = re.search(r"WP_FIELDS = \((.*?)\)\n", src.replace("\r\n", "\n"), re.S)
    fields = set("".join(re.findall(r'"([^"]*)"', m.group(1))).split(","))
    for f in ("reviewDetails", "isOverturned", "reviewType", "challengeTeamId", "additionalReviews",
              "pitchNumber", "player"):
        assert f in fields, f


def test_the_plays_tab_names_an_abs_challenge():
    js = (ROOT / "assets" / "scores.js").read_text(encoding="utf-8")
    assert '"ABS challenge"' in js and '"check-swing challenge"' in js and '"replay review"' in js
