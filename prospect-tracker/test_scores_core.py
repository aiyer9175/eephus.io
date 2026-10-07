# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""scores_core (SCORES_1_CORE_RULES): the pure MLB Scores core on saved fixtures.

Hermetic: every payload comes from test_fixtures/scores/ (trimmed from the
Part 8 bundle's saved StatsAPI samples and the local win-probability cache);
no network, no clock, nothing under data/ or .cache/ is written. The worked
example of SCORES_PLAN 7.3 (NL Wild Card Game 1, PHI 3 at ATL 5, game 849845)
must reproduce exactly.
"""
from __future__ import annotations

import copy
import json
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

import scores_core as sc

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "scores"
GEN = "2026-10-02T12:00:00Z"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lg():
    return load("league_constants_2026.json")


@pytest.fixture(scope="module")
def g849845():
    sched = load("schedule_states.json")
    game = next(g for d in sched["dates"] for g in d["games"] if g["gamePk"] == 849845 and g["status"]["codedGameState"] == "F")
    return {"game": game, "wp": load("wp_849845_full.json"), "ext": load("wp_849845_ext.json"),
            "box": load("box_849845.json"), "feed": load("feed_849845.json")}


@pytest.fixture(scope="module")
def gf849845(g849845, lg):
    g = g849845
    return sc.build_game_file(g["game"], g["wp"], g["box"], lg, generated_at=GEN, feed=g["feed"])


@pytest.fixture(scope="module")
def gf824592(lg):
    return sc.build_game_file(load("game_824592.json"), load("wp_824592.json"), load("box_824592.json"), lg,
                              generated_at=GEN)


@pytest.fixture(scope="module")
def synth_loser(lg):
    d = load("synth_loser_top2.json")
    return d, sc.build_game_file(d["game"], d["wp"], d["box"], lg, generated_at=GEN)


@pytest.fixture(scope="module")
def synth_workhorse(lg):
    d = load("synth_workhorse.json")
    return d, sc.build_game_file(d["game"], d["wp"], d["box"], lg, generated_at=GEN)


# --------------------------------------------------------------------------- #
# Flags, literals, imports
# --------------------------------------------------------------------------- #
def test_module_flag_defaults_off():
    assert sc.SCORES_LIVE is False


def test_stars_v1_literals_pinned_to_the_plan():
    # SCORES_PLAN 7.1 "Frozen literals, pinned to this text by a test":
    # MIN_OUTS = 15, MIN_COVERAGE = 0.95, FIRST_STAR_WINNER = True, rounding to
    # 0.001, the order score, average LI, largest single-play credit, first
    # plate appearance, MLBAM id. From the first public serve any change is
    # stars_v2, dated.
    assert sc.STARS_RULE == "stars_v1"
    assert sc.MIN_OUTS == 15
    assert sc.MIN_COVERAGE == 0.95
    assert sc.FIRST_STAR_WINNER is True
    assert sc.SCORE_DECIMALS == 3
    assert sc.STAR_ORDER == ("score", "avg_li", "best_credit", "first_ab", "id")
    assert sc.MAX_STARS == 3
    # bp_v1 (plan 7.2): |a| >= 0.03, five rows
    assert sc.PLAYS_RULE == "bp_v1"
    assert sc.MIN_SWING == 30
    assert sc.N_BIG_PLAYS == 5
    assert sc.FIRST_STAR_NOTE_TEXT == "First star: top player on the winning team."


def test_league_constants_fixture_matches_the_served_block(lg):
    served = json.loads((ROOT / "data" / "league_constants.json").read_text(encoding="utf-8"))
    blk = served["seasons"]["2026"]
    assert lg["lg_ra9"] == blk["lg_ra9"] == 4.5492
    assert lg["rpw"] == blk["rpw"] == 9.8237


def test_import_pulls_in_no_pandas_numpy_or_requests():
    code = ("import sys, scores_core; mods = {m.split('.')[0] for m in sys.modules}; "
            "print(sorted(mods & {'pandas', 'numpy', 'requests', 'trades', 'feed_cache', 'mlb_leverage'}))")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_scores_core_is_a_dash_gate_target():
    sys.path.insert(0, str(ROOT / "tools"))
    import strip_emdashes
    assert "scores_core.py" in strip_emdashes.TARGETS
    text = (ROOT / "scores_core.py").read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text


# --------------------------------------------------------------------------- #
# Clubs
# --------------------------------------------------------------------------- #
def test_club_literal_matches_canonical_org_from_id_and_the_franchise_board():
    import trades
    board = json.loads((ROOT / "data" / "franchise_board.json").read_text(encoding="utf-8"))
    codes = {c["code"] for c in board["clubs"]}
    assert len(sc.CLUB_BY_ID) == 30 and len(codes) == 30
    assert set(sc.CLUB_BY_ID.values()) == codes
    for tid, code in sc.CLUB_BY_ID.items():
        assert trades.canonical_org_from_id(tid) == code, tid
    for c in board["clubs"]:
        assert sc.CLUB_BY_ID[c["mlbam_id"]] == c["code"]
    # placeholders and unknowns give None, never a name lookup
    assert sc.club_code(5528) is None
    assert sc.club_code(None) is None
    assert sc.club_code("145") == "CHW"


# --------------------------------------------------------------------------- #
# 1. The state rule
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status, want", [
    ({"abstractGameState": "Final", "codedGameState": "F", "detailedState": "Final"}, "final"),
    ({"abstractGameState": "Final", "codedGameState": "O", "detailedState": "Game Over"}, "final"),
    ({"abstractGameState": "Final", "codedGameState": "F", "detailedState": "Completed Early: Rain"}, "final"),
    ({"abstractGameState": "Final", "codedGameState": "D", "detailedState": "Postponed", "reason": "Rain"}, "postponed"),
    ({"abstractGameState": "Final", "codedGameState": "C", "detailedState": "Cancelled", "reason": "Rain"}, "cancelled"),
    ({"abstractGameState": "Live", "codedGameState": "U", "detailedState": "Suspended: Rain"}, "suspended"),
    ({"abstractGameState": "Final", "codedGameState": "F", "detailedState": "Suspended"}, "suspended"),
    ({"abstractGameState": "Live", "codedGameState": "P", "detailedState": "Warmup"}, "pregame"),
    ({"abstractGameState": "Live", "codedGameState": "I", "detailedState": "In Progress"}, "live"),
    ({"abstractGameState": "Live", "codedGameState": "M", "detailedState": "Manager challenge", "reason": "Close play at 1st"}, "live"),
    ({"abstractGameState": "Live", "codedGameState": "I", "detailedState": "Delayed: Rain", "reason": "Rain"}, "delayed"),
    ({"abstractGameState": "Preview", "codedGameState": "P", "detailedState": "Delayed Start: Rain", "reason": "Rain"}, "delayed"),
    ({"abstractGameState": "Preview", "codedGameState": "P", "detailedState": "Pre-Game"}, "pregame"),
    ({"abstractGameState": "Preview", "codedGameState": "S", "detailedState": "Scheduled"}, "scheduled"),
])
def test_state_rule(status, want):
    state, _reason = sc.game_state(status)
    assert state == want
    assert (state == "final") == sc.is_final(status)


def test_state_rule_on_the_schedule_fixture():
    sched = load("schedule_states.json")
    seen = {}
    for d in sched["dates"]:
        for g in d["games"]:
            card = sc.build_card(g, generated_at=GEN)
            seen.setdefault(card["state"], []).append(card)
    assert set(seen) == set(sc.STATES) - {"delayed"}
    canc = seen["cancelled"][0]
    assert canc["pk"] == 823490 and canc["reason"] == "Rain" and canc["of_record"] is None and canc["star"] is None
    post = seen["postponed"][0]
    assert post["makeup"] == "2026-10-01" and post["reason"] == "Rain"
    susp = seen["suspended"][0]
    assert susp["resume"] == "2026-10-01" and susp["sit"] is None
    tbd = next(c for c in seen["scheduled"] if c["tbd"])
    assert tbd["pk"] == 849830 and tbd["away"]["code"] is None and tbd["away"]["name"] == "SD/CHC" and tbd["home"]["code"] == "MIL"
    assert tbd["series"]["text"] == "NL Division Series, Game 1 of 5"
    dh = next(c for c in seen["scheduled"] if c["dh"]["kind"])
    assert dh["dh"] == {"kind": "split", "n": 2}
    live = seen["live"][0]
    assert live["pk"] == 849846 and live["sit"]["inning"] == 1 and live["sit"]["half"] == "bottom"
    assert live["sit"]["batter"]["id"] == 665161 and live["sit"]["pitcher"]["id"] == 680732
    assert live["sit"]["bases"] == [False, False, False]
    assert live["series"]["text"] == "AL Wild Card Series, Game 2 of 3, CHW leads 1-0"
    warm = next(c for c in seen["pregame"] if c["pk"] == 849841)
    assert warm["sit"] is None and warm["wp"] is None and warm["weather"]["condition"] == "Partly Cloudy"
    ifn = next(c for c in seen["scheduled"] if c["pk"] == 849844)
    assert ifn["series"]["if_necessary"] is True and ifn["away"]["probable"] is None
    tie = next(c for c in seen["final"] if c["pk"] == 900004)
    assert tie["away"]["r"] == tie["home"]["r"] == 3


# --------------------------------------------------------------------------- #
# 2. Win probability series
# --------------------------------------------------------------------------- #
def test_thousandths_survive_mlb_decimals_exactly():
    assert sc.thousandths(52.2) == 522
    assert sc.thousandths(2.200000000000003) == 22
    assert sc.thousandths(-0.8000000000000007) == -8
    assert sc.thousandths(16.900000000000002) == 169
    assert sc.thousandths(None) is None
    assert sc.pct_of_thousandths(293) == 29 and sc.pct_of_thousandths(934) == 93 and sc.pct_of_thousandths(905) == 91


def test_series_on_the_worked_example(g849845):
    ws = sc.wp_series(g849845["wp"])
    assert ws["pregame_home"] == 500
    assert ws["coverage"] == {"mlb": 70, "of": 70}
    assert ws["last"] == {"ab": 69, "wp_home": 1000}
    assert [r[0] for r in ws["series"]] == list(range(70))
    assert ws["series"][0] == [0, 1, "top", 522, 22]
    assert all(isinstance(r[3], int) and 0 <= r[3] <= 1000 for r in ws["series"])
    # the extended fields= form gives the same series
    assert sc.wp_series(g849845["ext"])["series"] == ws["series"]


def test_in_progress_element_is_never_a_point_and_never_credited():
    live = load("wp_849846_live.json")
    assert len(live) == 10 and live[-1]["about"]["isComplete"] is False
    assert sc.thousandths(live[-1]["homeTeamWinProbabilityAdded"]) == 8
    ws = sc.wp_series(live)
    assert len(ws["series"]) == 9 and ws["last"] == {"ab": 8, "wp_home": 161}
    assert ws["coverage"] == {"mlb": 9, "of": 9}
    assert [r["ab"] for r in sc.play_credits(live)] == list(range(9))
    one = load("wp_849841_live.json")
    assert len(one) == 1 and one[0]["about"]["isComplete"] is False
    ws1 = sc.wp_series(one)
    assert ws1["series"] == [] and ws1["pregame_home"] is None and ws1["last"] is None
    assert sc.player_wpa(one) == {}


def test_missing_value_stays_null(g849845):
    wp = copy.deepcopy(g849845["wp"])
    wp[10]["homeTeamWinProbability"] = None
    wp[10]["homeTeamWinProbabilityAdded"] = None
    ws = sc.wp_series(wp)
    assert ws["series"][10][3] is None and ws["series"][10][4] is None
    assert ws["coverage"] == {"mlb": 69, "of": 70}
    rows = sc.play_rows(wp, {"away": "PHI", "home": "ATL"})
    assert rows[10]["wp"] is None and rows[10]["swing"] is None and rows[10]["before"] is None
    # nobody is credited for the gap
    assert sc.play_credits(wp)[10]["credit"] is None


# --------------------------------------------------------------------------- #
# 3. Credit, WPA, pLI and parity with mlb_leverage
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["wp_849845_full.json", "wp_849845_ext.json", "wp_824592.json"])
def test_wpa_parity_with_mlb_leverage(name):
    import mlb_leverage as ml
    plays = sc.complete_elements(load(name))
    gp = ml._game_pitcher_dict(plays)
    bat_acc: dict = {}
    ml._fold_game_batters(bat_acc, plays)
    mine = sc.player_wpa(plays)
    pit_mine: dict = {}
    bat_mine: dict = {}
    for (pid, side), r in mine.items():
        pit_mine[pid] = pit_mine.get(pid, 0.0) + r["wpa_pit"]
        bat_mine[pid] = bat_mine.get(pid, 0.0) + r["wpa_bat"]
    for pid, d in gp.items():
        assert abs(pit_mine[pid] - d["wpa"]) < 1e-9, pid
    for bid, a in bat_acc.items():
        assert abs(bat_mine[bid] - a["wpa"]) < 1e-9, bid
        pli_mine = None
        for (pid, side), r in mine.items():
            if pid == bid and r["li_bat"]:
                pli_mine = sum(r["li_bat"]) / len(r["li_bat"])
        pli_theirs = (a["li_sum"] / a["li_n"]) if a["li_n"] else None
        assert (pli_mine is None and pli_theirs is None) or abs(pli_mine - pli_theirs) < 1e-9, bid


def test_identity_home_wpa_plus_unattributed_equals_final_minus_pregame(g849845):
    wp = g849845["wp"]
    acc = sc.player_wpa(wp)
    home = sum(r["wpa_bat"] + r["wpa_pit"] for (pid, side), r in acc.items() if side == "home")
    total = sum(r["wpa_bat"] + r["wpa_pit"] for r in acc.values())
    assert abs(home - 0.5) < 1e-9                       # ATL WPA 0.500 = 1.000 minus 0.500
    assert abs(total) < 1e-9                            # all players sum to 0
    un = sc.unattributed_home(wp)
    assert un == 0
    ws = sc.wp_series(wp)
    assert abs((sc.wins_to_thousandths(home) + un) - (ws["last"]["wp_home"] - ws["pregame_home"])) <= 2


def test_unattributed_absorbs_a_value_that_trails_the_score(g849845):
    wp = copy.deepcopy(g849845["wp"])
    # move 1.0 point of the Riley home run's added value out of attribution
    wp[65]["homeTeamWinProbabilityAdded"] = wp[65]["homeTeamWinProbabilityAdded"] - 1.0
    acc = sc.player_wpa(wp)
    home = sum(r["wpa_bat"] + r["wpa_pit"] for (pid, side), r in acc.items() if side == "home")
    un = sc.unattributed_home(wp)
    assert un == 10
    assert abs((sc.wins_to_thousandths(home) + un) - 500) <= 2


# --------------------------------------------------------------------------- #
# 5. stars_v1: the worked example
# --------------------------------------------------------------------------- #
def test_worked_example_reproduces_exactly(gf849845):
    stars = gf849845["stars"]
    assert [(s["name"], s["team"], s["score"], s["basis"]) for s in stars] == [
        ("Austin Riley", "ATL", 513, "wpa"), ("J.T. Realmuto", "PHI", 303, "wpa"), ("Ozzie Albies", "ATL", 273, "wpa")]
    assert [s["rank"] for s in stars] == [1, 2, 3]
    assert gf849845["first_star_note"] is False and gf849845["stars_reason"] is None
    assert stars[0]["why"] == "1-for-3, HR, 3 RBI. Go-ahead home run in the 8th, ATL 29% to 93%."
    assert gf849845["card"]["star"] == {"id": 663586, "name": "Austin Riley", "team": "ATL", "why": stars[0]["why"]}
    assert gf849845["wp"]["pregame_home"] == 500 and gf849845["wp"]["unattributed_home"] == 0
    assert gf849845["wp"]["series"][-1][3] == 1000


def test_worked_example_next_candidates(g849845, lg):
    cands = sc.star_candidates(g849845["wp"], g849845["box"], lg)
    nxt = [(c["name"], c["side"], c["score_m"], c["basis"], c["outs"]) for c in cands[3:5]]
    assert nxt[0][1:] == ("away", 176, "wpa", 15) and nxt[0][0].endswith("Luzardo")
    assert nxt[1] == ("Chris Sale", "home", 123, "wpa", 19)
    luz, sale = cands[3], cands[4]
    assert round(luz["runs_prevented"], 3) == 0.155 and luz["wpa_pit"] > luz["runs_prevented"]
    assert round(sale["runs_prevented"], 3) == 0.020


def test_worked_example_from_the_extended_fields_form(g849845, lg):
    g = g849845
    gf = sc.build_game_file(g["game"], g["ext"], g["box"], lg, generated_at=GEN, feed=g["feed"])
    assert [(s["id"], s["score"]) for s in gf["stars"]] == [(663586, 513), (592663, 303), (645277, 273)]
    assert [b["swing"] for b in gf["plays_big"]] == [637, 374, 215, -144, -129]


def test_shuffle_invariance(g849845, lg):
    g = g849845
    wp = copy.deepcopy(g["wp"])
    random.Random(20261002).shuffle(wp)
    gf = sc.build_game_file(g["game"], wp, g["box"], lg, generated_at=GEN, feed=g["feed"])
    ref = sc.build_game_file(g["game"], g["wp"], g["box"], lg, generated_at=GEN, feed=g["feed"])
    assert gf["stars"] == ref["stars"] and gf["plays_big"] == ref["plays_big"]
    assert gf["wp"] == ref["wp"] and gf["plays"] == ref["plays"] and gf["rev"] == ref["rev"]


def test_fuentes_shaped_reliever_is_not_rescued(g849845, lg, synth_workhorse):
    # the real Fuentes on 849845: WPA -0.199, 0 runs charged, never a candidate
    acc = sc.player_wpa(g849845["wp"])
    fuentes = next(r for (pid, side), r in acc.items() if r["name"] == "Didier Fuentes")
    assert round(fuentes["wpa_pit"], 3) == -0.199
    box_f = sc._box_entry(g849845["box"], "home", fuentes["id"])["stats"]["pitching"]
    assert box_f["runs"] == 0
    assert all(c["id"] != fuentes["id"] for c in sc.star_candidates(g849845["wp"], g849845["box"], lg))
    # the synthetic shape with 15 outs: the WPA guard keeps the runs term away
    d, gf = synth_workhorse
    acc = sc.player_wpa(d["wp"])
    one = acc[(1, "away")]
    assert round(one["wpa_pit"], 3) == -0.36
    assert d["box"]["teams"]["away"]["players"]["ID1"]["stats"]["pitching"]["outs"] == 15
    assert d["box"]["teams"]["away"]["players"]["ID1"]["stats"]["pitching"]["runs"] == 0
    assert sc.runs_prevented(15, 0, lg) > 0
    assert all(c["id"] != 1 for c in sc.star_candidates(d["wp"], d["box"], lg))


def test_workhorse_runs_term_changes_the_star_set(synth_workhorse, lg):
    d, gf = synth_workhorse
    acc = sc.player_wpa(d["wp"])
    pure = sorted(((r["wpa_bat"] + r["wpa_pit"], pid) for (pid, side), r in acc.items()), reverse=True)
    pure_top3 = {pid for _s, pid in pure[:3]}
    assert 3 not in pure_top3
    stars = gf["stars"]
    assert [s["id"] for s in stars] == [3, 201, 5]
    assert stars[0]["basis"] == "runs" and stars[0]["score"] == 258
    assert stars[0]["why"] == "7.0 IP, 1 R, 4 K on 60 pitches: 2.5 runs better than the league rate over his innings."
    assert round(acc[(3, "home")]["wpa_pit"], 3) == 0.04
    assert stars[2]["why"] == "2.0 IP in the 8th and 9th, 4 K; hold."
    assert gf["first_star_note"] is False


def test_stars_withheld_for_coverage_tie_and_non_final(g849845, lg):
    g = g849845
    wp = copy.deepcopy(g["wp"])
    for i in (5, 15, 25, 35, 45):
        wp[i]["homeTeamWinProbabilityAdded"] = None
    gf = sc.build_game_file(g["game"], wp, g["box"], lg, generated_at=GEN, feed=g["feed"])
    assert gf["wp"]["coverage"] == {"mlb": 65, "of": 70}
    assert gf["stars"] == [] and gf["stars_reason"] == sc.REASON_COVERAGE
    assert gf["plays_big"] == [] and gf["plays_big_reason"] == sc.PLAYS_REASON_COVERAGE
    assert gf["card"]["star"] is None and gf["card"]["top_play"] is None
    tie = copy.deepcopy(g["game"])
    tie["linescore"]["teams"]["home"]["runs"] = 3
    tie["teams"]["home"]["score"] = 3
    gf = sc.build_game_file(tie, g["wp"], g["box"], lg, generated_at=GEN)
    assert gf["stars"] == [] and gf["stars_reason"] == sc.REASON_TIE
    live = copy.deepcopy(g["game"])
    live["status"] = {"abstractGameState": "Live", "codedGameState": "I", "detailedState": "In Progress"}
    gf = sc.build_game_file(live, g["wp"], g["box"], lg, generated_at=GEN)
    assert gf["stars"] == [] and gf["stars_reason"] == sc.REASON_NOT_FINAL
    assert len(gf["plays_big"]) == 5 and gf["card"]["star"] is None


def test_824592_star_order_hudson_first_from_the_winner(gf824592):
    stars = gf824592["stars"]
    assert [(s["name"], s["team"], s["score"]) for s in stars] == [
        ("Bryan Hudson", "CHW", 195), ("Keider Montero", "DET", 395), ("Colson Montgomery", "CHW", 195)]
    assert gf824592["first_star_note"] is True
    assert gf824592["card"]["home"]["r"] == 2 and gf824592["card"]["away"]["r"] == 1
    assert stars[1]["why"] == "6.0 IP, 2 H, 0 R, 0 BB, 4 K on 65 pitches."
    assert stars[2]["why"] == "1-for-3, HR, RBI. Game-tying home run in the 7th, CHW 32% to 55%."


def test_loser_top_two_outscore_the_winner(synth_loser):
    d, gf = synth_loser
    stars = gf["stars"]
    assert [s["team"] for s in stars] == ["LAD", "CIN", "CIN"]
    assert [s["score"] for s in stars] == [210, 300, 250]
    assert gf["first_star_note"] is True
    assert stars[1]["score"] >= stars[2]["score"]


def test_tie_order_avg_li_then_best_credit_then_first_ab_then_id():
    def play(i, half, bid, pid, added, li):
        return {"about": {"atBatIndex": i, "halfInning": half, "inning": 1 + i // 6, "isComplete": True},
                "matchup": {"batter": {"id": bid, "fullName": f"B{bid}"}, "pitcher": {"id": pid, "fullName": f"P{pid}"}},
                "result": {"eventType": "single", "event": "Single", "awayScore": 0, "homeScore": 0},
                "count": {"outs": 0}, "homeTeamWinProbability": 50.0, "homeTeamWinProbabilityAdded": added,
                "leverageIndex": li, "atBatIndex": i}
    plays = [play(0, "bottom", 11, 1, 10.0, 2.0), play(1, "bottom", 12, 1, 10.0, 1.0),
             play(2, "bottom", 13, 1, 6.0, 1.0), play(3, "bottom", 13, 1, 4.0, 1.0),
             play(4, "bottom", 14, 1, 10.0, 1.0)]
    lg = {"lg_ra9": 4.5492, "rpw": 9.8237}
    cands = sc.star_candidates(plays, {}, lg)
    ids = [c["id"] for c in cands if c["side"] == "home"]
    # 11 (LI 2.0) before 12 and 14 (LI 1.0, tie on best credit 0.10, then first ab), then 13
    assert ids == [11, 12, 14, 13]


# --------------------------------------------------------------------------- #
# 6. Why sentences parsed back against their templates
# --------------------------------------------------------------------------- #
HITTER_RE = re.compile(r"^(\d+)-for-(\d+)((?:, (?:\d+ )?(?:2B|3B|HR|RBI|BB))*)\.(?: (Walk-off |Go-ahead |Game-tying |)(.+?) in the (\d+)(?:st|nd|rd|th), ([A-Z]{3}) (\d+)% to (\d+)%\.)?$")
STARTER_WPA_RE = re.compile(r"^(\d+)\.(\d) IP( in relief)?, (\d+) H, (\d+) R, (\d+) BB, (\d+) K on (\d+) pitches\.$")
STARTER_RUNS_RE = re.compile(r"^(\d+)\.(\d) IP, (\d+) R, (\d+) K on (\d+) pitches: (-?\d+\.\d) runs better than the league rate over his innings\.$")
RELIEVER_RE = re.compile(r"^(\d+)\.(\d) IP in the ([0-9a-z ]+), (\d+) K(; save|; hold|; win)?\.$")


def _counts(extras: str) -> dict:
    out = {}
    for part in [p for p in extras.split(", ") if p]:
        toks = part.split(" ")
        out[toks[-1]] = int(toks[0]) if len(toks) == 2 else 1
    return out


def test_why_sentences_parse_back(gf849845, gf824592, synth_workhorse, lg):
    for gf, box, wp in ((gf849845, load("box_849845.json"), load("wp_849845_full.json")),
                        (gf824592, load("box_824592.json"), load("wp_824592.json")),
                        (synth_workhorse[1], synth_workhorse[0]["box"], synth_workhorse[0]["wp"])):
        elements = sc.complete_elements(wp)
        for s in gf["stars"]:
            side = "home" if s["team"] == gf["card"]["home"]["code"] else "away"
            stats = box["teams"][side]["players"][f"ID{s['id']}"]["stats"]
            parts = s["why"].split(" On the mound: ")
            hitter = HITTER_RE.match(parts[0])
            if hitter:
                bat = stats["batting"]
                assert int(hitter.group(1)) == bat["hits"] and int(hitter.group(2)) == bat["atBats"]
                got = _counts(hitter.group(3))
                assert got.get("HR", 0) == bat.get("homeRuns", 0) and got.get("3B", 0) == bat.get("triples", 0)
                assert got.get("2B", 0) == bat.get("doubles", 0) and got.get("RBI", 0) == bat.get("rbi", 0)
                assert got.get("BB", 0) == bat.get("baseOnBalls", 0)
                if hitter.group(5):
                    assert hitter.group(7) == s["team"]
                    inning, before, after = int(hitter.group(6)), int(hitter.group(8)), int(hitter.group(9))
                    half = "bottom" if side == "home" else "top"
                    mine = [p for p in elements if p["matchup"]["batter"]["id"] == s["id"] and sc._half(p) == half
                            and p.get("homeTeamWinProbabilityAdded") is not None]
                    sign = 1 if side == "home" else -1
                    best = max(mine, key=lambda p: sign * p["homeTeamWinProbabilityAdded"])
                    assert best["about"]["inning"] == inning
                    wp_after = sc.thousandths(best["homeTeamWinProbability"])
                    added = sc.thousandths(best["homeTeamWinProbabilityAdded"])
                    after_bat = wp_after if side == "home" else 1000 - wp_after
                    before_bat = after_bat - sign * added
                    assert sc.pct_of_thousandths(before_bat) == before and sc.pct_of_thousandths(after_bat) == after
                pitch_text = parts[1] if len(parts) == 2 else None
            else:
                pitch_text = parts[0]
            if pitch_text is not None:
                pit = stats["pitching"]
                m = STARTER_WPA_RE.match(pitch_text) or STARTER_RUNS_RE.match(pitch_text) or RELIEVER_RE.match(pitch_text)
                assert m, pitch_text
                assert int(m.group(1)) == pit["outs"] // 3 and int(m.group(2)) == pit["outs"] % 3
                if m.re is STARTER_WPA_RE:
                    assert s["basis"] == "wpa"
                    assert (int(m.group(4)), int(m.group(5)), int(m.group(6)), int(m.group(7)), int(m.group(8))) == (
                        pit["hits"], pit["runs"], pit["baseOnBalls"], pit["strikeOuts"], pit["numberOfPitches"])
                elif m.re is STARTER_RUNS_RE:
                    assert s["basis"] == "runs"
                    assert (int(m.group(3)), int(m.group(4)), int(m.group(5))) == (pit["runs"], pit["strikeOuts"], pit["numberOfPitches"])
                    rs = pit["outs"] / 3 * lg["lg_ra9"] / 9 - pit["runs"]
                    assert float(m.group(6)) == float(sc._fmt1(rs))
                else:
                    assert int(m.group(4)) == pit["strikeOuts"]
                    deco = m.group(5) or ""
                    assert ("save" in deco) == (pit.get("saves", 0) > 0)


def test_hitter_sentence_qualifiers():
    bat = {"hits": 1, "atBats": 3, "homeRuns": 1, "rbi": 2}
    row = {"situation": {"lead": -1}, "half": "bottom", "home": 3, "away": 2, "inning": 9, "before": 300, "after": 1000,
           "event_phrase": "home run"}
    assert sc.hitter_sentence(bat, row, "ATL", True) == "1-for-3, HR, 2 RBI. Walk-off home run in the 9th, ATL 30% to 100%."
    assert sc.hitter_sentence(bat, row, "ATL", False) == "1-for-3, HR, 2 RBI. Go-ahead home run in the 9th, ATL 30% to 100%."
    row2 = dict(row, home=2, after=550, situation={"lead": -1})
    assert sc.hitter_sentence(bat, row2, "ATL", False).endswith("Game-tying home run in the 9th, ATL 30% to 55%.")
    row3 = dict(row, situation={"lead": 2}, home=5)
    assert sc.hitter_sentence(bat, row3, "ATL", False).endswith(". Home run in the 9th, ATL 30% to 100%.")
    assert sc.hitter_sentence({"hits": 0, "atBats": 0, "baseOnBalls": 2}, None, "ATL", False) == "0-for-0, 2 BB."
    assert sc._ip(19) == "6.1" and sc._ip(0) == "0.0"


# --------------------------------------------------------------------------- #
# 7. play_text
# --------------------------------------------------------------------------- #
def _play_for(et, event=None, rbi=0, scorers=()):
    return {"result": {"eventType": et, "event": event or et, "rbi": rbi},
            "matchup": {"batter": {"id": 1, "fullName": "Ronald Acuña Jr."}, "pitcher": {"id": 2, "fullName": "P"}},
            "runners": [{"movement": {"end": "score"}, "details": {"runner": {"id": 10 + i, "fullName": n}}}
                        for i, n in enumerate(scorers)],
            "playEvents": []}


def test_play_text_over_every_event_type():
    banned = re.compile(r"\b(edge|value|ev|kelly|pick|lean|bet)\b", re.IGNORECASE)
    assert len(sc.EVENT_PHRASES) >= 70
    for et, phrase in sc.EVENT_PHRASES.items():
        text = sc.play_text(_play_for(et))
        assert text.endswith(".") and chr(0x2014) not in text and chr(0x2013) not in text
        assert not banned.search(text), text
        assert phrase.split(" ")[0].lower() in text.lower(), (et, text)
        assert text[0].isupper()
    for label, phrase in sc.FIELD_OUT_LABELS.items():
        assert sc.play_text(_play_for("field_out", label)) == f"Acuña {phrase}."
    # unknown event types still print from fields
    assert sc.play_text(_play_for("some_new_type")) == "Acuña some new type."
    assert sc.play_text(_play_for("home_run", "Home Run", 3, ("Michael Harris II", "Ozzie Albies"))) == \
        "Acuña home run, 3 RBI. Harris and Albies scored."
    assert sc.play_text(_play_for("sac_fly", "Sac Fly", 1, ("Drake Baldwin",))) == "Acuña sacrifice fly, 1 RBI. Baldwin scored."
    assert sc.play_text(_play_for("grounded_into_double_play", "Grounded Into DP")) == "Acuña grounded into a double play."


def test_play_text_on_the_worked_example_uses_fields_not_descriptions(g849845, gf849845):
    names = sc.last_name_map(g849845["feed"], g849845["box"])
    wp = g849845["wp"]
    texts = {p["ab"]: p["text"] for p in gf849845["plays"]}
    assert texts[65] == "Riley home run, 3 RBI. Harris and Albies scored."
    assert texts[53] == "Realmuto triple, 2 RBI. De La Cruz and Stott scored."
    assert texts[66] == "Yastrzemski groundout."
    assert texts[0] == "Turner struck out swinging."
    assert texts[68].startswith("De La Cruz grounded into a double play.")
    assert texts[41] == "Schwarber single."
    assert sc.play_text(wp[65], names) == texts[65]
    # the extended fields= form (no pitch codes) still reads the call label
    ext = g849845["ext"]
    assert sc.play_text(ext[0], names) == "Turner struck out swinging."
    blob = sc.dumps(gf849845)
    for p in wp:
        desc = p["result"].get("description")
        if desc:
            assert desc not in blob, desc
    for key in ("headline", "blurb", "description", "title", "kicker", "summary"):
        assert f'"{key}"' not in blob


# --------------------------------------------------------------------------- #
# 4. bp_v1 and the situation before
# --------------------------------------------------------------------------- #
def test_biggest_plays_on_the_worked_example(gf849845):
    big = gf849845["plays_big"]
    assert [(b["rank"], b["inning"], b["half"], b["bat_team"], b["before"], b["after"], b["swing"], b["li"]) for b in big] == [
        (1, 8, "bottom", "ATL", 290, 927, 637, 4.97), (2, 7, "top", "PHI", 308, 682, 374, 3.69),
        (3, 6, "bottom", "ATL", 578, 793, 215, 1.81), (4, 9, "top", "PHI", 156, 12, -144, 3.07),
        (5, 7, "top", "PHI", 437, 308, -129, 3.6)]
    assert [sc.pct_of_thousandths(x) for x in (big[3]["before"], big[3]["after"])] == [16, 1]
    assert round((big[3]["after"] - big[3]["before"]) / 10) == -14
    assert big[0]["situation"] == {"outs": 2, "bases": [True, True, False], "lead": -1}
    assert big[0]["text"].startswith("Riley home run, 3 RBI.")
    assert all(b["clip"] is None and b["clip_state"] == "pending" for b in big)
    assert gf849845["card"]["top_play"] == {"ab": 65, "text": big[0]["text"], "bat_team": "ATL", "before": 290,
                                            "after": 927, "swing": 637, "clip_s": None}


def test_biggest_plays_floor_and_order():
    rows = [{"ab": i, "inning": 1, "half": "top", "text": "t", "bat_team": "PHI", "before": 500, "after": 500 + (s or 0),
             "swing": s, "li": li, "situation": {}} for i, (s, li) in enumerate([(29, 9.0), (30, 1.0), (-30, 2.0), (100, 0.5), (None, 1.0), (100, 0.7)])]
    big = sc.biggest_plays(rows)
    assert [b["ab"] for b in big] == [5, 3, 2, 1]


def test_situation_before_resets_each_half_with_the_automatic_runner():
    def play(i, inning, half, outs, on=(None, None, None), away=0, home=0):
        m = {"batter": {"id": 1}, "pitcher": {"id": 2}}
        for k, v in zip(("postOnFirst", "postOnSecond", "postOnThird"), on):
            if v:
                m[k] = {"id": v}
        return {"about": {"atBatIndex": i, "halfInning": half, "inning": inning, "isComplete": True},
                "count": {"outs": outs}, "matchup": m, "result": {"awayScore": away, "homeScore": home},
                "homeTeamWinProbability": 50.0, "homeTeamWinProbabilityAdded": 0.0, "atBatIndex": i}
    plays = [play(0, 9, "top", 1, (5, None, None), 1, 1), play(1, 9, "top", 3, (5, 6, None), 1, 1),
             play(2, 9, "bottom", 3, (None, None, None), 1, 1), play(3, 10, "top", 0, (7, None, None), 2, 1),
             play(4, 10, "bottom", 1)]
    reg = sc.situations(plays, season=2026, game_type="R")
    assert reg[0]["outs_before"] == 0 and reg[0]["bases_before"] == [False, False, False]
    assert reg[1]["outs_before"] == 1 and reg[1]["bases_before"] == [True, False, False]
    assert reg[2]["outs_before"] == 0 and reg[2]["bases_before"] == [False, False, False]
    assert reg[3]["bases_before"] == [False, True, False] and reg[3]["away_before"] == 1 and reg[3]["home_before"] == 1
    assert reg[4]["bases_before"] == [False, True, False] and reg[4]["away_before"] == 2
    post = sc.situations(plays, season=2026, game_type="F")
    assert post[3]["bases_before"] == [False, False, False] and post[4]["bases_before"] == [False, False, False]
    old = sc.situations(plays, season=2019, game_type="R")
    assert old[3]["bases_before"] == [False, False, False]
    assert sc.auto_runner(2020, "R") and not sc.auto_runner(2019, "R") and not sc.auto_runner(2026, "D")


def test_day_top_plays_across_games(gf849845, gf824592, synth_workhorse):
    cards = [gf849845["card"], gf824592["card"], synth_workhorse[1]["card"]]
    live_card = copy.deepcopy(gf824592["card"])
    live_card["state"] = "live"
    files = {gf849845["pk"]: gf849845, gf824592["pk"]: gf824592, synth_workhorse[1]["pk"]: synth_workhorse[1]}
    df = sc.build_date_file("2026-09-29", [cards[0], live_card, cards[2]], files, generated_at=GEN)
    top = df["day_top_plays"]
    assert len(top) == 5 and top[0] == {"pk": 849845, "ab": 65, "text": gf849845["plays_big"][0]["text"], "bat_team": "ATL",
                                        "before": 290, "after": 927, "swing": 637, "live": False}
    assert [abs(t["swing"]) for t in top] == sorted((abs(t["swing"]) for t in top), reverse=True)
    assert any(t["pk"] == 824592 and t["live"] for t in top)
    assert [c["pk"] for c in df["games"]] == sorted([c["pk"] for c in df["games"]], key=lambda pk: next(c["start"] for c in df["games"] if c["pk"] == pk))


# --------------------------------------------------------------------------- #
# Box, lineups, info, debuts
# --------------------------------------------------------------------------- #
def test_box_rows_carry_wpa_and_pli(gf849845):
    box = gf849845["box"]
    sale = next(r for r in box["home"]["pitching"] if r["name"] == "Chris Sale")
    assert sale["outs"] == 19 and sale["wpa"] == 123 and sale["started"] is True and sale["pli"] == 1.1
    fuentes = next(r for r in box["home"]["pitching"] if r["name"] == "Didier Fuentes")
    assert fuentes["wpa"] == -199 and fuentes["r"] == 0 and fuentes["dec"]["bs"] is True
    riley = next(r for r in box["home"]["batting"] if r["name"] == "Austin Riley")
    assert riley["wpa"] == 513 and riley["hr"] == 1 and riley["rbi"] == 3 and riley["ab"] == 3 and riley["order"] == 700
    assert [r["order"] for r in box["home"]["batting"] if r["order"] and r["order"] % 100 == 0] == [100, 200, 300, 400, 500, 600, 700, 800, 900]
    assert all(r["position_player"] is False for side in ("away", "home") for r in box[side]["pitching"])
    assert box["away"]["notes"] == []
    home_rows = box["home"]["batting"] + box["home"]["pitching"]
    home_sum = sum(r["wpa"] for r in home_rows if r["wpa"] is not None)
    assert abs(home_sum - 500) <= 3
    assert gf849845["lineups"]["home"][0]["id"] == 686948 and len(gf849845["lineups"]["away"]) == 9
    info = gf849845["info"]
    assert info["umpires"][0] == {"pos": "Home Plate", "id": 605670, "name": "Dan Merzel"}
    assert info["attendance"] == 30127 and info["duration_min"] == 146 and info["venue"]["roof"] == "Open"
    assert info["abs"] == {"PHI": {"won": 1, "lost": 0, "remaining": 2}, "ATL": {"won": 1, "lost": 1, "remaining": 1}}
    assert gf849845["scoring"] == [3, 15, 46, 53, 65]
    assert gf849845["links"] == {"gameday": "https://www.mlb.com/gameday/849845"}
    assert gf849845["card"]["of_record"]["sv"]["name"] == "Raisel Iglesias"
    assert gf849845["card"]["flags"] == {"no_hitter": False, "perfect_game": False, "debut": False, "extra_innings": False, "shortened": False}


def test_box_rows_carry_pitch_rates_that_reconcile(gf849845, g849845):
    """Owner ask 2026-10-07: pitches per plate appearance for batters, per
    inning for pitchers. A club's batters saw exactly the pitches the other
    club's pitchers threw (MLB's pitch events against its boxscore counts)."""
    box = gf849845["box"]
    for bat_side, pit_side in (("home", "away"), ("away", "home")):
        seen = sum(r["pit"] for r in box[bat_side]["batting"])
        thrown = sum(r["pc"] for r in box[pit_side]["pitching"])
        assert seen == thrown, (bat_side, seen, thrown)
    harper = next(r for r in box["away"]["batting"] if r["name"] == "Bryce Harper")
    assert harper["pit"] == 20 and harper["p_pa"] == 5.0
    sale = next(r for r in box["home"]["pitching"] if r["name"] == "Chris Sale")
    assert sale["pc"] == 95 and sale["outs"] == 19 and sale["p_ip"] == 15.0
    hicklen = next(r for r in box["home"]["batting"] if r["name"] == "Brewer Hicklen")
    assert hicklen["p_pa"] is None  # no plate appearance: no rate
    # a read without pitch events prints no count rather than a short one
    bare = [dict(e, playEvents=None) for e in g849845["wp"]]
    assert sc.pitches_seen(bare) is None
    assert all(r["pit"] is None and r["p_pa"] is None
               for r in sc.box_rows(g849845["box"], bare)["home"]["batting"])


def test_debuts_from_the_feed(g849845, lg):
    feed = copy.deepcopy(g849845["feed"])
    feed["gameData"]["players"]["ID663586"]["mlbDebutDate"] = "2026-09-29"
    gf = sc.build_game_file(g849845["game"], g849845["wp"], g849845["box"], lg, generated_at=GEN, feed=feed)
    assert gf["debuts"] == [663586] and gf["card"]["flags"]["debut"] is True
    riley = next(r for r in gf["box"]["home"]["batting"] if r["id"] == 663586)
    assert riley["debut"] is True
    assert sc.debut_ids(None, "2026-09-29") == set()


def test_info_only_on_finals_and_umpires_never_before(g849845, lg):
    live = copy.deepcopy(g849845["game"])
    live["status"] = {"abstractGameState": "Live", "codedGameState": "I", "detailedState": "In Progress"}
    gf = sc.build_game_file(live, g849845["wp"], g849845["box"], lg, generated_at=GEN, feed=g849845["feed"])
    assert gf["info"] is None and gf["card"]["sit"] is not None and gf["card"]["of_record"] is None


# --------------------------------------------------------------------------- #
# MLB strings: dash normalisation
# --------------------------------------------------------------------------- #
def test_mlb_string_with_en_dash_is_normalised_not_refused():
    sched = load("schedule_states.json")
    game = next(g for d in sched["dates"] for g in d["games"] if g["gamePk"] == 900005)
    assert chr(0x2013) in game["venue"]["name"] and chr(0x2014) in game["teams"]["home"]["team"]["name"]
    card = sc.build_card(game, generated_at=GEN)
    assert card["venue"]["name"] == "Truist Park - Lot A" and card["home"]["name"] == "Atlanta Braves - home"
    assert sc.find_dashes(card) == []
    df = sc.build_date_file("2026-09-30", [card], {}, generated_at=GEN)
    assert sc.validate_payload("date", df, name="2026-09-30.json")["ok"]
    raw = copy.deepcopy(df)
    raw["games"][0]["venue"]["name"] = game["venue"]["name"]
    res = sc.validate_payload("date", raw, name="2026-09-30.json")
    assert not res["ok"] and any(r[0] == "10" for r in res["refused"])


# --------------------------------------------------------------------------- #
# 8. The validator
# --------------------------------------------------------------------------- #
def test_validator_accepts_the_built_files(gf849845, gf824592, synth_loser, synth_workhorse):
    for gf in (gf849845, gf824592, synth_loser[1], synth_workhorse[1]):
        res = sc.validate_payload("game", gf, name=f"games/{gf['pk']}.json")
        assert res["ok"], res["refused"]
        assert res["bytes"] <= sc.FILE_KINDS["game"]["budget"]
    df = sc.build_date_file("2026-09-29", [gf849845["card"]], {849845: gf849845}, generated_at=GEN)
    res = sc.validate_payload("date", df, name="2026-09-29.json")
    assert res["ok"], res["refused"]


def test_rule_3_star_sets(gf824592, synth_loser):
    for gf in (gf824592, synth_loser[1]):
        assert gf["first_star_note"] is True
        assert sc.validate_payload("game", gf, name=f"games/{gf['pk']}.json")["ok"]
    bad = copy.deepcopy(gf824592)
    bad["stars"][1], bad["stars"][2] = bad["stars"][2], bad["stars"][1]       # 195 then 395: stars 2 and 3 increase
    res = sc.validate_payload("game", bad, name="games/824592.json")
    assert not res["ok"] and any("stars 2 and 3 increase" in m for r, m in res["refused"] if r == "3")
    bad = copy.deepcopy(gf824592)
    bad["first_star_note"] = False
    res = sc.validate_payload("game", bad, name="games/824592.json")
    assert any("first_star_note" in m for r, m in res["refused"] if r == "3")
    bad = copy.deepcopy(gf824592)
    bad["stars"][0], bad["stars"][1] = bad["stars"][1], bad["stars"][0]       # Montero (DET, the loser) first
    bad["first_star_note"] = False
    res = sc.validate_payload("game", bad, name="games/824592.json")
    assert any("the winner is CHW" in m for r, m in res["refused"] if r == "3")
    bad = copy.deepcopy(gf824592)
    bad["card"]["state"] = "live"
    bad["card"]["of_record"] = None
    res = sc.validate_payload("game", bad, name="games/824592.json")
    assert any("not final" in m for r, m in res["refused"] if r == "3")
    bad = copy.deepcopy(gf824592)
    bad["stars"][2]["score"] = 0
    res = sc.validate_payload("game", bad, name="games/824592.json")
    assert any("positive" in m for r, m in res["refused"] if r == "3")


def test_rule_2_values_and_the_final_value(gf849845):
    bad = copy.deepcopy(gf849845)
    bad["wp"]["series"][-1][3] = 0
    res = sc.validate_payload("game", bad, name="games/849845.json")
    assert any("does not match the winner" in m for r, m in res["refused"] if r == "2")
    bad = copy.deepcopy(gf849845)
    bad["plays"][3]["wp"] = 52.2
    res = sc.validate_payload("game", bad, name="games/849845.json")
    assert any("not an integer" in m for r, m in res["refused"] if r == "2")
    bad = copy.deepcopy(gf849845)
    bad["wp"]["series"][5][0] = 3
    res = sc.validate_payload("game", bad, name="games/849845.json")
    assert any("strictly increasing" in m for r, m in res["refused"] if r == "2")
    bad = copy.deepcopy(gf849845)
    bad["card"]["line"][0][1] = 7
    res = sc.validate_payload("game", bad, name="games/849845.json")
    assert any("innings sum" in m for r, m in res["refused"] if r == "2")
    noted = copy.deepcopy(gf849845)
    noted["wp"]["pregame_home"] = 520
    res = sc.validate_payload("game", noted, name="games/849845.json")
    assert res["ok"] and any("pregame point 520" in m for r, m in res["logged"] if r == "2")


def test_rule_1_names_and_enum(gf849845):
    assert not sc.validate_payload("game", gf849845, name="games/849846.json")["ok"]
    df = sc.build_date_file("2026-09-29", [gf849845["card"]], {}, generated_at=GEN)
    assert not sc.validate_payload("date", df, name="2026-09-30.json")["ok"]
    bad = copy.deepcopy(df)
    bad["games"][0]["state"] = "over"
    assert any(r == "1" for r, m in sc.validate_payload("date", bad, name="2026-09-29.json")["refused"])
    bad = copy.deepcopy(df)
    bad["schema"] = 2
    assert any(r == "1" for r, m in sc.validate_payload("date", bad, name="2026-09-29.json")["refused"])
    assert sc.kind_of_name("games/849845.json") == "game" and sc.kind_of_name("2026-09-29.json") == "date"
    assert sc.kind_of_name("index.json") == "index" and sc.kind_of_name("index-2026.json") == "season_index"
    assert sc.kind_of_name("latest.json") == "latest"
    # no scores kind captures a standings path; standings_core registers its
    # own kinds when it is imported in the same session (STANDINGS_1)
    assert sc.kind_of_name("standings/2026.json") not in ("latest", "index", "season_index", "date", "game", "clip")


def test_rule_4_copyright_exemption_and_urls(gf849845):
    box = load("box_849845.json")
    line = box["copyright"]
    assert sc.MLB_TERMS_URL in line and line.startswith("Copyright 2026 MLB Advanced Media, L.P.")
    index = {"schema": 1, "generated_at": GEN, "seasons": [{"season": 2026, "rev": "abc", "n_dates": 1}], "registry": [],
             "accuracy": {"mlb_wp": {}}, "rules": {"stars": sc.STARS_RULE, "plays": sc.PLAYS_RULE,
                                                   "video": {"embed": False}}, "copyright": line}
    assert sc.validate_payload("index", index, name="index.json")["ok"]
    bad = copy.deepcopy(index)
    bad["notice"] = line
    del bad["copyright"]
    res = sc.validate_payload("index", bad, name="index.json")
    assert not res["ok"] and any(r == "4" for r, m in res["refused"])
    bad = copy.deepcopy(index)
    bad["rules"]["terms"] = sc.MLB_TERMS_URL
    assert any(r == "4" for r, m in sc.validate_payload("index", bad, name="index.json")["refused"])
    season = {"schema": 1, "season": 2026, "dates": [{"d": "2026-09-29", "n": 1, "types": ["F"], "rev": "abc", "flags": []}],
              "bracket": None}
    assert sc.validate_payload("season_index", season, name="index-2026.json")["ok"]
    season["copyright"] = line
    res = sc.validate_payload("season_index", season, name="index-2026.json")
    assert not res["ok"] and any(r == "4" for r, m in res["refused"])
    # the game file's gameday link is the one URL outside clips; a URL anywhere
    # else, a bad host inside a clip, or a dangling clip reference refuses
    assert sc.validate_payload("game", gf849845, name="games/849845.json")["ok"]
    bad = copy.deepcopy(gf849845)
    bad["plays"][0]["text"] = "see https://www.mlb.com/video/x"
    assert any(r == "4" for r, m in sc.validate_payload("game", bad, name="games/849845.json")["refused"])
    bad = copy.deepcopy(gf849845)
    bad["clips"]["c1"] = {"id": "c1", "kind": "play", "embed": "https://evil.example.com/m/slug", "page": "https://www.mlb.com/video/a-b"}
    res = sc.validate_payload("game", bad, name="games/849845.json")
    assert any("fails its role allowlist" in m for r, m in res["refused"] if r == "4")
    good = copy.deepcopy(gf849845)
    good["clips"]["c1"] = {"id": "c1", "kind": "play", "embed": "https://streamable.com/m/jhoan-duran-x2885",
                           "page": "https://www.mlb.com/video/jhoan-duran-x2885",
                           "poster": {"w480": "https://img.mlbstatic.com/mlb-images/image/upload/w_480/a.jpg", "w960": None}}
    good["plays_big"][0]["clip"] = "c1"
    assert sc.validate_payload("game", good, name="games/849845.json")["ok"]
    good["plays_big"][1]["clip"] = "missing"
    assert any("does not resolve" in m for r, m in sc.validate_payload("game", good, name="games/849845.json")["refused"])
    df = sc.build_date_file("2026-09-29", [gf849845["card"]], {}, generated_at=GEN)
    assert df["games"][0] is not gf849845["card"]          # the builder never aliases its inputs
    df["games"][0]["venue"]["name"] = "mlb.com park"
    assert any(r == "4" for r, m in sc.validate_payload("date", df, name="2026-09-29.json")["refused"])
    assert sc.url_ok("https://streamable.com/m/abc-123", "embed")
    assert not sc.url_ok("http://streamable.com/m/abc-123", "embed")
    assert not sc.url_ok("https://streamable.com/m/abc?x=1", "embed")
    assert not sc.url_ok("https://www.mlb.com/video/" + "a" * 300, "page")


def test_rule_6_budget_logged_ceiling_refused(gf849845):
    big = copy.deepcopy(gf849845)
    big["pad"] = "x" * (sc.FILE_KINDS["game"]["budget"] + 10)
    res = sc.validate_payload("game", big, name="games/849845.json")
    assert res["ok"] and any("over_budget" in m for r, m in res["logged"] if r == "6")
    big["pad"] = "x" * (sc.FILE_KINDS["game"]["ceiling"] + 10)
    res = sc.validate_payload("game", big, name="games/849845.json")
    assert not res["ok"] and any(r == "6" for r, m in res["refused"])
    assert sc.FILE_KINDS["game"]["budget"] == 80 * 1024 and sc.FILE_KINDS["game"]["ceiling"] == 320 * 1024
    assert sc.FILE_KINDS["date"]["budget"] == 150 * 1024 and sc.FILE_KINDS["latest"]["budget"] == 16 * 1024
    assert sc.FILE_KINDS["index"]["budget"] == 16 * 1024 and sc.FILE_KINDS["season_index"]["budget"] == 40 * 1024


def test_rule_5_nan_refused(gf849845):
    bad = copy.deepcopy(gf849845)
    bad["plays"][0]["li"] = float("nan")
    res = sc.validate_payload("game", bad, name="games/849845.json")
    assert not res["ok"] and res["refused"][0][0] == "5"


def test_pitcher_with_no_outs_keeps_his_wpa_term():
    def play(i, bid, pid, added):
        return {"about": {"atBatIndex": i, "halfInning": "top", "inning": 9, "isComplete": True},
                "matchup": {"batter": {"id": bid, "fullName": f"B{bid}"}, "pitcher": {"id": pid, "fullName": f"P{pid}"}},
                "result": {"eventType": "single", "event": "Single", "awayScore": 0, "homeScore": 0},
                "count": {"outs": 0}, "homeTeamWinProbability": 50.0, "homeTeamWinProbabilityAdded": added,
                "atBatIndex": i}
    plays = [play(0, 11, 1, 20.0), play(1, 12, 2, -20.0)]
    cands = sc.star_candidates(plays, {}, {"lg_ra9": 4.5492, "rpw": 9.8237})
    assert [(c["id"], c["side"], c["score_m"], c["pitched"]) for c in cands] == [(1, "home", 200, True), (12, "away", 200, False)]


def test_rule_7_disk_age(gf849845):
    assert sc.validate_payload("game", gf849845, name="games/849845.json", disk_generated_at="2026-10-02T11:00:00Z")["ok"]
    res = sc.validate_payload("game", gf849845, name="games/849845.json", disk_generated_at="2026-10-02T13:00:00Z")
    assert any(r == "7" for r, m in res["refused"])


def test_rule_8_if_necessary_pair_passes_and_a_plain_disappearance_is_refused():
    before = load("schedule_2025_wc_before.json")
    after = load("schedule_2025_wc_after.json")
    games_a = [g for d in after["dates"] for g in d["games"]]
    day_b = [g for d in before["dates"] if d["date"] == "2025-10-02" for g in d["games"]]
    day_a = [g for d in after["dates"] if d["date"] == "2025-10-02" for g in d["games"]]
    assert len(day_b) == 4 and len(day_a) == 3
    g3 = next(g for g in day_b if g["gamePk"] == 813067)
    assert g3["ifNecessary"] == "Y" and g3["teams"]["away"]["team"]["id"] == 113 and g3["teams"]["home"]["team"]["id"] == 119
    prev = [sc.build_card(g, generated_at=GEN) for g in day_b]
    new = [sc.build_card(g, generated_at=GEN) for g in day_a]
    assert next(c for c in prev if c["pk"] == 813067)["series"]["if_necessary"] is True
    assert sc.series_over(813067, games_a + [g3])
    assert sc.check_shrink(prev, new, games_a) == []
    # the same drop without the flag is refused
    plain = copy.deepcopy(g3)
    plain["ifNecessary"] = "N"
    prev_plain = [sc.build_card(g, generated_at=GEN) for g in day_b if g["gamePk"] != 813067] + [sc.build_card(plain, generated_at=GEN)]
    res = sc.check_shrink(prev_plain, new, games_a)
    assert res and res[0][0] == "8" and "813067" in res[0][1]
    # a series still open does not allow the drop either
    open_games = [copy.deepcopy(g) for g in games_a]
    for g in open_games:
        if g["gamePk"] == 813068:
            g["teams"]["away"]["isWinner"], g["teams"]["home"]["isWinner"] = True, False
    assert not sc.series_over(813067, open_games + [g3])
    assert sc.check_shrink(prev, new, open_games)
    # a game the schedule marks postponed may leave the date
    moved = copy.deepcopy(plain)
    moved["status"] = {"abstractGameState": "Final", "codedGameState": "D", "detailedState": "Postponed", "reason": "Rain"}
    assert sc.check_shrink(prev_plain, new, games_a + [moved]) == []
    # isOver on the clinching game is enough on its own
    over = copy.deepcopy(games_a)
    for g in over:
        if g["gamePk"] == 813068:
            g["seriesStatus"] = {"isOver": True, "wins": 2, "losses": 0, "totalGames": 3, "description": "NL Wild Card Series"}
    assert sc.series_over(813067, over + [g3])


def test_rule_9_forbidden_keys():
    for key in ("edge", "ev", "kelly_frac", "pick_side", "slot", "record", "records", "price_usd", "odds", "decimal",
                "book", "implied_prob", "fair_odds", "clv", "stake", "units", "advance", "decision_at",
                "market", "headline", "blurb", "description", "title", "kicker", "summary"):
        assert sc.forbidden_key(key), key
    for key in ("wl", "of_record", "action", "wpa", "pli", "rev", "state", "series", "video", "clips", "li"):
        assert sc.forbidden_key(key) is None, key
    assert sc.forbidden_key("market_fair_prob", allow_market=True) is None
    assert sc.forbidden_key("market_x", allow_market=True)
    obj = {"schema": 1, "games": [{"pk": 1, "nested": {"edge": 1}}]}
    res = sc.validate_payload("latest", obj, name="latest.json")
    assert any(r == "9" and "edge" in m for r, m in res["refused"])


def test_second_payload_family_can_register_its_own_kind():
    line = load("box_849845.json")["copyright"]
    assert "standings" not in sc.FILE_KINDS
    sc.register_file_kind("standings_test", budget=10 * 1024, name_re=r"^standings/test-\d{4}\.json$", copyright_exempt=True)
    try:
        assert sc.kind_of_name("standings/test-2026.json") == "standings_test"
        obj = {"schema": 1, "season": 2026, "rows": [{"code": "ATL", "w": 90, "l": 72}], "copyright": line}
        res = sc.validate_files({"standings/test-2026.json": obj})["standings/test-2026.json"]
        assert res["ok"], res["refused"]
        obj["note"] = line
        assert not sc.validate_files({"standings/test-2026.json": obj})["standings/test-2026.json"]["ok"]
        assert sc.FILE_KINDS["standings_test"]["ceiling"] == 40 * 1024
        res = sc.validate_files({"standings/other.json": obj})["standings/other.json"]
        assert not res["ok"] and res["refused"][0][0] == "0"
    finally:
        del sc.FILE_KINDS["standings_test"]


def test_rev_is_stable_and_follows_content(gf849845):
    assert len(gf849845["rev"]) == 12 and gf849845["card"]["rev"] == gf849845["rev"]
    other = copy.deepcopy(gf849845)
    other["rev"] = None
    other["card"]["rev"] = None
    assert sc.rev_of(other) == gf849845["rev"]
    other["stars"][0]["score"] = 514
    assert sc.rev_of(other) != gf849845["rev"]
    assert sc.rev_of(sc.dumps(gf849845).encode("utf-8")) != gf849845["rev"]   # the on-disk hash includes rev itself
    with pytest.raises(ValueError):
        sc.dumps({"x": float("nan")})
