# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The ABS challenge ledger (docs/eabs-2026-10-15/ABS_LEDGER.md).

Pinned: the ledger resolves the challenger's role through the
defense walk, reads the call on the field as the inverse of an overturned call,
reads the count and the bases before the pitch, and its invariant compares rows
with gameData.absChallenges per club."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import abs_ledger as al  # noqa: E402

LEDGER = ROOT / "data" / "_labs" / "abs_ledger"
FEEDS = ROOT / ".cache" / "game_feeds"


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
# The ledger
# --------------------------------------------------------------------------- #
def test_rows_roles_calls_counts_and_bases():
    rows, checks = al.challenge_rows(_feed())
    assert [(r["at_bat_index"], r["pitch_number"], r["source"], r["role"]) for r in rows] == [
        (0, 2, "event", "catcher"), (0, 4, "play", "batter"), (1, 1, "event", "pitcher")]
    c, b, p = rows
    assert (c["final_call"], c["original_call"], c["overturned"]) == ("C", "B", True)
    assert (c["balls_before"], c["strikes_before"], c["count_after_final"], c["count_after_original"]) == (1, 0, "1-1", "2-0")
    assert c["challenge_org"] == "KCR" and c["catcher_id"] == 20 and c["pitcher_id"] == 10
    assert (c["challenge_side"], c["role_by_side"]) == ("fielding", "pitcher_or_catcher")
    assert c["bases_before"] == "___"
    # The steal (playIndex 2) moved the runner before the last pitch.
    assert b["bases_before"] == "_2_" and (b["balls_before"], b["strikes_before"]) == (1, 2)
    assert (b["final_call"], b["original_call"], b["count_after_final"]) == ("C", "C", "K")
    assert (b["challenge_side"], b["role_by_side"]) == ("batting", "batter")
    # The substitution seated catcher 21 before the pitcher's challenge.
    assert p["catcher_id"] == 21 and p["outs_before"] == 1 and p["flags"] is None
    assert checks["pitcher_walk_mismatch"] == 0 and checks["side_role_mismatch"] == 0


def test_check_swing_is_its_own_kind():
    f = _feed()
    f["liveData"]["plays"]["allPlays"][1]["playEvents"][1]["reviewDetails"]["reviewType"] = "MZ"
    rows, _ = al.challenge_rows(f)
    assert [r["kind"] for r in rows] == ["zone", "zone", "check_swing"]
    assert al.original_call("check_swing", "B", True) == "S"
    assert al.original_call("zone", "B", True) == "C"
    assert al.original_call("zone", "X", True) is None


def test_the_invariant_matches_and_refuses():
    f = _feed()
    rows, _ = al.challenge_rows(f)
    assert al.check_feed(f, rows)["ok"]
    g = copy.deepcopy(f)
    g["gameData"]["absChallenges"]["home"]["usedFailed"] = 0
    assert not al.check_feed(g, rows)["ok"]
    assert not al.check_feed(f, rows[:1])["ok"]


def test_replay_reviews_are_not_rows():
    f = _feed()
    f["liveData"]["plays"]["allPlays"][0]["reviewDetails"] = _rev("MF", 118, True)
    rows, _ = al.challenge_rows(f)
    assert [r["review_type"] for r in rows] == ["MJ", "MJ"]


def test_count_after():
    assert al.count_after(3, 2, "B") == "BB" and al.count_after(1, 2, "C") == "K"
    assert al.count_after(0, 0, "S") == "0-1" and al.count_after(2, 1, "X") is None


def test_a_real_cached_feed_when_present():
    p = FEEDS / "824055.json"
    if not p.exists():
        pytest.skip("no cached feed")
    feed = json.loads(p.read_text(encoding="utf-8"))
    rows, checks = al.challenge_rows(feed)
    assert al.check_feed(feed, rows)["ok"] and checks["pitcher_walk_mismatch"] == 0
    (r,) = rows
    assert (r["at_bat_index"], r["pitch_number"], r["role"], r["overturned"]) == (34, 5, "batter", True)
    assert (r["original_call"], r["count_after_original"], r["count_after_final"]) == ("C", "K", "3-2")


def test_the_written_ledger_when_present():
    p = LEDGER / "mlb_2026.json"
    if not p.exists():
        pytest.skip("run python tools/build_abs_ledger.py")
    led = json.loads(p.read_text(encoding="utf-8"))
    assert led["fields"] == list(al.FIELDS)
    assert all(len(r) == len(al.FIELDS) for r in led["rows"])
    cov = json.loads((LEDGER / "coverage.json").read_text(encoding="utf-8"))
    mlb = cov["frames"]["mlb_2026"]
    assert mlb["invariant"]["feeds_mismatch"] == 0 and mlb["rows"] == len(led["rows"])
    i = led["fields"].index("kind")
    assert {r[i] for r in led["rows"]} == {"zone"}
    # The AAA seasons fetched for the stability frame: every feed matches its
    # absChallenges counts, and each season's row count is the AAA file's.
    aaa_frames = {k: v for k, v in cov["frames"].items() if k.startswith("level11_")}
    if aaa_frames and (LEDGER / "aaa.json").exists():
        aaa = json.loads((LEDGER / "aaa.json").read_text(encoding="utf-8"))
        s = aaa["fields"].index("season")
        for key, fr in aaa_frames.items():
            assert fr["invariant"]["feeds_mismatch"] == 0, key
            season = int(key.split("_")[1])
            assert fr["rows"] == sum(1 for r in aaa["rows"] if r[s] == season), key


def test_the_ledger_never_ships():
    """data/_labs/ ships in neither deploy consumer (test_publish_manifest pins
    that); the builder writes only there and under its own cache."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build_abs_ledger as b
    assert b.OUT_DIR == ROOT / "data" / "_labs" / "abs_ledger"
    assert b.TASK_CACHE == ROOT / ".cache" / "EWAR_T4_ABS_LEDGER"
    assert b.PROBE_DIR.parent == b.TASK_CACHE and b.AAA_DIR.parent == b.TASK_CACHE
