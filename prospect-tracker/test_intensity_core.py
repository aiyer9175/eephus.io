# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The game-intensity construction core (`intensity_core.py`, plan Part 8 item IX-H1).

Fixtures and synthetic leagues only. No test here reads a game, a final, a standings
file or a price: every club, record and schedule below is made up in this file. The
section "Game intensity: stakes, matchup quality and the postseason" of
docs/diamond-betting.md binds the module; this file pins it to that text and checks:

- a World Series game 7 between equal clubs gives S = 1;
- two eliminated clubs give 0;
- the two forced runs under common random numbers are identical except the forced
  game, and the one-pass stakes equal the two literal forced runs count for count;
- the frozen literals equal the registration text (and the registration test's one
  copy of them);
- the exact series recursion reproduces the lane's table (`intensity_work/
  series_stakes.py` in the Part 8 bundle, equal clubs, p = 0.5 a game);
- the copies stay copies: the bracket equals proj_current's line for line, the Elo walk
  equals tools/betting_elo.py, and the module imports no served code (X4).
"""
from __future__ import annotations

import ast
import importlib.util
import math
import random
import re
from pathlib import Path

import pytest

import intensity_core as ic
import test_betting_intensity_registration as reg

ROOT = Path(__file__).resolve().parent

DIVISIONS = {
    "AL_C": ["CHW", "CLE", "DET", "KCR", "MIN"],
    "AL_E": ["BAL", "BOS", "NYY", "TBR", "TOR"],
    "AL_W": ["ATH", "HOU", "LAA", "SEA", "TEX"],
    "NL_C": ["CHC", "CIN", "MIL", "PIT", "STL"],
    "NL_E": ["ATL", "MIA", "NYM", "PHI", "WSN"],
    "NL_W": ["ARI", "COL", "LAD", "SDP", "SFG"],
}
ORGS = sorted(o for d in DIVISIONS.values() for o in d)
LEAGUE = {o: d.split("_")[0] for d, m in DIVISIONS.items() for o in m}
DIV = {o: d for d, m in DIVISIONS.items() for o in m}

# The lane's table, printed by intensity_work/series_stakes.py (Part 8 bundle,
# 2026-09-30): G = dWS_home + dWS_away for equal clubs at p = 0.5 a game, by round and
# series state, with P(win the World Series | win this round) = 1/8, 1/4, 1/2 and 1.
LANE_TABLE = {
    "WC 0-0": 0.125, "WC 0-1": 0.125, "WC 1-0": 0.125, "WC 1-1": 0.25,
    "DS 0-0": 0.1875, "DS 0-1": 0.1875, "DS 0-2": 0.125, "DS 1-0": 0.1875,
    "DS 1-1": 0.25, "DS 1-2": 0.25, "DS 2-0": 0.125, "DS 2-1": 0.25, "DS 2-2": 0.5,
    "CS 0-0": 0.3125, "CS 0-1": 0.3125, "CS 0-2": 0.25, "CS 0-3": 0.125,
    "CS 1-0": 0.3125, "CS 1-1": 0.375, "CS 1-2": 0.375, "CS 1-3": 0.25,
    "CS 2-0": 0.25, "CS 2-1": 0.375, "CS 2-2": 0.5, "CS 2-3": 0.5,
    "CS 3-0": 0.125, "CS 3-1": 0.25, "CS 3-2": 0.5, "CS 3-3": 1.0,
    "WS 0-0": 0.625, "WS 0-1": 0.625, "WS 0-2": 0.5, "WS 0-3": 0.25,
    "WS 1-0": 0.625, "WS 1-1": 0.75, "WS 1-2": 0.75, "WS 1-3": 0.5,
    "WS 2-0": 0.5, "WS 2-1": 0.75, "WS 2-2": 1.0, "WS 2-3": 1.0,
    "WS 3-0": 0.25, "WS 3-1": 0.5, "WS 3-2": 1.0, "WS 3-3": 2.0,
}
LANE_FINAL_DAY_WC3 = 0.125   # "RS final day, winner-take-all for WC3"

# The lane's S column (section 2.3): G -> S at the draft G_REF. Its Opening Day row
# is G = G_REF exactly (L = 1), so that key is the draft value itself.
LANE_S = {ic.G_REF_DRAFT: 0.134, 0.0344: 0.268, 0.125: 0.479, 0.25: 0.605, 0.1875: 0.552,
          0.5: 0.735, 0.3125: 0.647, 1.0: 0.867, 0.625: 0.777, 2.0: 1.000}

# The lane's worked index values (section 2.3): (S, Q, A, D) -> (II, band).
LANE_II = [((0.000, 0.10, 0.30, 0), (6, "routine")),
           ((0.134, 0.50, 0.50, 0), (23, "routine")),
           ((0.134, 0.50, 0.50, 1), (33, "raised")),
           ((0.479, 0.67, 0.50, 1), (56, "high")),
           ((0.605, 0.80, 0.80, 1), (70, "peak")),
           ((1.000, 0.95, 0.95, 0), (89, "peak"))]


# ---------------------------------------------------------------------------
# synthetic fields
# ---------------------------------------------------------------------------
def _teams(wins: dict | None = None, p: dict | None = None) -> dict:
    return {o: {"wins": (wins or {}).get(o, 80), "p": (p or {}).get(o, 0.5),
                "league": LEAGUE[o], "div": DIV[o]} for o in ORGS}


def _final_day_field():
    """The last day of a made-up season. Every club has played 161 games except
    SEA and TEX (AL West, 160 each), who meet in the one remaining game tied at 85
    wins for the last wild card; every other record is distinct and settled. Equal
    clubs, no home edge."""
    wins = {}
    al = {"NYY": 100, "CLE": 99, "HOU": 98, "BOS": 92, "DET": 90, "SEA": 85, "TEX": 85,
          "TOR": 84, "MIN": 83, "BAL": 82, "KCR": 81, "LAA": 79, "TBR": 78, "CHW": 70,
          "ATH": 66}
    nl = {"LAD": 101, "PHI": 97, "MIL": 96, "SDP": 93, "NYM": 91, "CHC": 89, "ATL": 87,
          "ARI": 86, "CIN": 80, "SFG": 77, "STL": 76, "PIT": 75, "MIA": 72, "WSN": 68,
          "COL": 60}
    wins.update(al)
    wins.update(nl)
    return _teams(wins), [("SEA", "TEX")]


def _eliminated_field():
    """Five days left. KCR and CHW (AL Central) sit 30 games behind the last wild card
    and play each other twice; the contenders still play each other."""
    wins = {o: 70 for o in ORGS}
    wins.update({"NYY": 95, "BOS": 94, "TOR": 93, "CLE": 92, "DET": 91, "HOU": 96,
                 "SEA": 90, "LAD": 95, "PHI": 94, "ATL": 93, "MIL": 92, "CHC": 91,
                 "SDP": 90, "KCR": 60, "CHW": 59})
    pairs = [("KCR", "CHW"), ("NYY", "BOS"), ("TOR", "SEA"), ("CLE", "DET"),
             ("CHW", "KCR"), ("HOU", "SEA"), ("BOS", "TOR"), ("LAD", "SDP"),
             ("PHI", "ATL"), ("MIL", "CHC")]
    return _teams(wins), pairs


def _contested_field(seed: int = 7, n_games: int = 60):
    """A spread of talents and records with a few weeks left, so ties and races
    happen in the simulations."""
    rnd = random.Random(seed)
    wins = {o: rnd.randint(70, 84) for o in ORGS}
    p = {o: min(0.62, max(0.38, rnd.gauss(0.5, 0.04))) for o in ORGS}
    pairs = []
    for _ in range(n_games):
        h, a = rnd.sample(ORGS, 2)
        pairs.append((h, a))
    return _teams(wins, p), pairs


AL6 = ("NYY", "CLE", "HOU", "BOS", "DET", "SEA")
NL6 = ("LAD", "PHI", "MIL", "SDP", "NYM", "CHC")


def _equal_bracket(fmt: str = "six"):
    n = 6 if fmt == "six" else 5
    seeds = {"AL": AL6[:n], "NL": NL6[:n]}
    clubs = AL6[:n] + NL6[:n]
    return seeds, {c: 90 for c in clubs}, {c: 0.5 for c in clubs}


def _decide(state: dict, winner: str, loser: str, need: int) -> None:
    state[frozenset((winner, loser))] = {winner: need, loser: 0}


# ---------------------------------------------------------------------------
# the four pins the spec names
# ---------------------------------------------------------------------------
def test_world_series_game_7_between_equal_clubs_gives_s_1():
    seeds, wins, talent = _equal_bracket()
    st: dict = {}
    for lg, (s1, s2, s3, s4, s5, s6) in (("AL", AL6), ("NL", NL6)):
        _decide(st, s3, s6, 2)
        _decide(st, s4, s5, 2)
        _decide(st, s1, s4, 3)
        _decide(st, s2, s3, 3)
        _decide(st, s1, s2, 4)
    st[frozenset(("NYY", "LAD"))] = {"NYY": 3, "LAD": 3}
    for edge in (0.0, ic.HOME_EDGE):
        r = ic.postseason_stakes(seeds, wins, talent, "NYY", "LAD", series_state=st,
                                 home_edge=edge)
        assert r["game_type"] == "W" and r["game_number"] == 7
        assert r["d_series"] == 1.0 and r["dws_h"] == 1.0 and r["dws_a"] == 1.0
        assert r["G"] == 2.0 and r["G_se"] == 0.0
        assert ic.stakes_score(r["G"], ic.G_REF_DRAFT) == pytest.approx(1.0, abs=1e-15)
        for ref in (0.005, 0.02):
            assert ic.stakes_score(r["G"], ref) == pytest.approx(1.0, abs=1e-15)


def test_two_eliminated_clubs_give_zero():
    teams, pairs = _eliminated_field()
    out = ic.regular_season_stakes(teams, pairs, [0, 4], n_sims=1500, seed=ic.SEED)
    for g in out["games"]:
        assert {g["home"], g["away"]} == {"KCR", "CHW"}
        assert g["dws_h"] == 0.0 and g["dws_a"] == 0.0
        assert g["dpo_h"] == 0.0 and g["dpo_a"] == 0.0
        assert g["G"] == 0.0 and g["G_se"] == 0.0
        assert ic.stakes_multiple(g["G"], ic.G_REF_DRAFT) == 0.0
        assert ic.stakes_score(g["G"], ic.G_REF_DRAFT) == 0.0
    # a contender's game in the same field is not zero: SEA chases the last wild card
    live = ic.regular_season_stakes(teams, pairs, [5], n_sims=1500, seed=ic.SEED)
    assert live["games"][0]["away"] == "SEA"
    assert live["games"][0]["dpo_a"] > 0 and live["games"][0]["G"] > 0


def test_forced_crn_runs_are_identical_except_the_forced_game():
    teams, pairs = _contested_field()
    k = 17
    runs = {side: ic.simulate_forced(teams, pairs, forced=(k, side), n_sims=400,
                                     seed=ic.SEED, trace=True)
            for side in ("home", "away")}
    th, ta = runs["home"]["trace"], runs["away"]["trace"]
    assert len(th) == len(ta) == 400
    for i, (x, y) in enumerate(zip(th, ta)):
        assert x[k] == 1 and y[k] == 0, i
        assert x[:k] == y[:k] and x[k + 1:] == y[k + 1:], (
            f"simulation {i}: a game other than the forced one differs")
    # the forced game's draw is consumed: the unforced run lines up too
    free = ic.simulate_forced(teams, pairs, forced=None, n_sims=400, seed=ic.SEED,
                              trace=True)["trace"]
    for x, z in zip(th, free):
        assert x[:k] == z[:k] and x[k + 1:] == z[k + 1:]


def test_one_pass_stakes_equal_two_literal_forced_runs():
    teams, pairs = _contested_field()
    ks = [3, 17, 40]
    n = 300
    one = ic.regular_season_stakes(teams, pairs, ks, n_sims=n, seed=99)
    for g in one["games"]:
        k, h, a = g["index"], g["home"], g["away"]
        fh = ic.simulate_forced(teams, pairs, forced=(k, "home"), n_sims=n, seed=99)
        fa = ic.simulate_forced(teams, pairs, forced=(k, "away"), n_sims=n, seed=99)
        assert g["counts"]["ws"] == {"hH": fh["ws"][h], "hA": fa["ws"][h],
                                     "aH": fh["ws"][a], "aA": fa["ws"][a]}
        assert g["counts"]["po"] == {"hH": fh["playoff"][h], "hA": fa["playoff"][h],
                                     "aH": fh["playoff"][a], "aA": fa["playoff"][a]}
        assert g["dws_h"] == (fh["ws"][h] - fa["ws"][h]) / n
        assert g["dpo_a"] == (fa["playoff"][a] - fh["playoff"][a]) / n
    free = ic.simulate_forced(teams, pairs, forced=None, n_sims=n, seed=99)
    for o in ORGS:
        assert one["proj_wins"][o] == free["win_sum"][o] / n


def test_the_literals_equal_the_registration_text():
    L = reg.LITERALS
    assert ic.CONSTRUCTION == reg.CONSTRUCTION == "ix_v1"
    assert ic.G_REF_DRAFT == L["g_ref_draft"]
    assert ic.G_REF_SEED == L["g_ref_seed"]
    assert ic.G_REF_SIMS == L["g_ref_sims"]
    assert ic.G_REF_CLUBS == L["g_ref_clubs"]
    assert (ic.W_STAKES, ic.W_QUALITY, ic.W_STARTERS, ic.W_DIVISION, ic.W_RIVALRY) == (
        L["w_stakes"], L["w_quality"], L["w_starters"], L["w_division"], L["w_rivalry"])
    assert ic.BANDS == L["bands"]
    assert (ic.ELO_BASE, ic.ELO_K, ic.ELO_HOME_POINTS) == (
        L["elo_base"], L["elo_k"], L["elo_home_points"])
    assert ic.HOME_EDGE == L["home_edge"]
    assert (ic.SIMS, ic.SEED) == (L["sims"], L["seed"])
    assert ic.FOCUS_THRESHOLD == L["focus_threshold"]
    # and against the text itself, not only the other test's copy
    sec = reg._norm(reg._section())
    formula = (f"II = round(100 x ({ic.W_STAKES:.2f} S + {ic.W_QUALITY:.2f} Q + "
               f"{ic.W_STARTERS:.2f} A + {ic.W_DIVISION:.2f} D))")
    assert formula in sec
    assert f"draft value {ic.G_REF_DRAFT}" in sec
    assert f"{ic.G_REF_SIMS:,} simulations at seed {ic.G_REF_SEED}" in sec
    sched = ic.G_REF_SCHEDULE
    assert (f"{ic.G_REF_CLUBS} equal clubs at 0-0 on a 162-game schedule of "
            f"{sched['division']} division, {sched['league']} league and "
            f"{sched['interleague']} interleague games") in sec
    assert sum(sched.values()) == 162
    assert (f"({ic.ELO_BASE:.0f}, K {ic.ELO_K:.0f}, {ic.ELO_HOME_POINTS:.0f} points of "
            "home field, flat start each season)") in sec
    assert f"home edge of {ic.HOME_EDGE}" in sec
    assert f"{ic.SIMS:,} simulations at seed {ic.SEED}" in sec
    assert f"`|ds| >= {ic.FOCUS_THRESHOLD}`" in sec
    lo, mid, hi = ic.BANDS
    names = ic.BAND_NAMES
    assert (f"under {lo} {names[0]}, {lo} to {mid - 1} {names[1]}, {mid} to {hi - 1} "
            f"{names[2]}, {hi} and over {names[3]}") in sec
    assert "`S = ln(1 + L) / ln(1 + 2 / G_REF)`" in sec
    assert "`L = G / G_REF`" in sec and "`G = dWS_h + dWS_a`" in sec


def test_g_ref_is_not_frozen_before_the_gate_tool():
    """G_REF stays None until the gate tool's commit records it by a dated amendment;
    until then S needs an explicit reference and nothing defaults to the draft."""
    sec = reg._norm(reg._section())
    if ic.G_REF is None:
        with pytest.raises(ValueError):
            ic.stakes_score(0.01)
    else:
        assert f"{ic.G_REF}" in sec and "G_REF" in sec


def test_the_series_recursion_reproduces_the_lane_table():
    seeds, wins, talent = _equal_bracket()
    s1, s2, s3, s4, s5, s6 = AL6
    for key, want in LANE_TABLE.items():
        rnd, score = key.split()
        wa, wb = (int(x) for x in score.split("-"))
        st: dict = {}
        if rnd == "WC":
            x, y = s3, s6
        elif rnd == "DS":
            _decide(st, s4, s5, 2)
            x, y = s1, s4
        elif rnd == "CS":
            _decide(st, s4, s5, 2)
            _decide(st, s3, s6, 2)
            _decide(st, s1, s4, 3)
            _decide(st, s2, s3, 3)
            x, y = s1, s2
        else:
            for lg6 in (AL6, NL6):
                a1, a2, a3, a4, a5, a6 = lg6
                _decide(st, a4, a5, 2)
                _decide(st, a3, a6, 2)
                _decide(st, a1, a4, 3)
                _decide(st, a2, a3, 3)
                _decide(st, a1, a2, 4)
            x, y = s1, NL6[0]
        st[frozenset((x, y))] = {x: wa, y: wb}
        r = ic.postseason_stakes(seeds, wins, talent, x, y, series_state=st,
                                 home_edge=0.0)
        assert r["G"] == pytest.approx(want, abs=5e-5), key
        assert r["dws_h"] == pytest.approx(r["dws_a"], abs=1e-15), key
        # the same swing with the two clubs named the other way round
        r2 = ic.postseason_stakes(seeds, wins, talent, y, x, series_state=st,
                                  home_edge=0.0)
        assert r2["G"] == pytest.approx(r["G"], abs=1e-15), key


def test_the_final_day_wild_card_game_matches_the_lane_value():
    """Winner takes the last wild card: each club's playoff swing is exactly 1 and its
    World Series swing is P(WS | the 6 seed) = 1/16 for equal clubs, so G = 0.125.
    Under common random numbers the mirror-image clubs get exactly equal swings."""
    teams, pairs = _final_day_field()
    out = ic.regular_season_stakes(teams, pairs, [0], n_sims=20_000, seed=ic.SEED,
                                   home_edge=0.0)
    g = out["games"][0]
    assert g["dpo_h"] == 1.0 and g["dpo_a"] == 1.0
    assert g["dpo_h_se"] == 0.0 and g["dpo_a_se"] == 0.0
    assert g["dws_h"] == g["dws_a"]
    assert g["G_se"] > 0
    assert abs(g["G"] - LANE_FINAL_DAY_WC3) < 4 * g["G_se"]


# ---------------------------------------------------------------------------
# formats and the bracket
# ---------------------------------------------------------------------------
def test_format_for_season():
    for s in (2018, 2019, 2021):
        assert ic.format_for_season(s) == "five"
    for s in (2022, 2023, 2024, 2025, 2026, 2027):
        assert ic.format_for_season(s) == "six"
    for s in (2020, 2017, 1999):
        with pytest.raises(ValueError):
            ic.format_for_season(s)
    with pytest.raises(ValueError):
        ic.bracket_tree({"AL": AL6[:5], "NL": NL6[:5]}, "seven")


def test_five_club_format_equal_clubs():
    seeds, wins, talent = _equal_bracket("five")
    ws = ic.world_series_probs(seeds, wins, talent, fmt="five", home_edge=0.0)
    for lg in (AL6, NL6):
        s1, s2, s3, s4, s5 = lg[:5]
        assert ws[s1] == pytest.approx(1 / 8) and ws[s2] == pytest.approx(1 / 8)
        assert ws[s3] == pytest.approx(1 / 8)
        assert ws[s4] == pytest.approx(1 / 16) and ws[s5] == pytest.approx(1 / 16)
    assert sum(ws.values()) == pytest.approx(1.0, abs=1e-12)
    # the one-game wild card: the swing on the series is 1, and the winner then
    # needs three series at one half each
    r = ic.postseason_stakes(seeds, wins, talent, "BOS", "DET", fmt="five", home_edge=0.0)
    assert r["best_of"] == 1 and r["d_series"] == 1.0
    assert r["G"] == pytest.approx(2 * 1 / 8)
    # seed 1 meets the wild-card winner, seed 2 meets seed 3
    tree = ic.bracket_tree(seeds, "five")
    al = tree["left"]
    assert al["left"]["left"] == "NYY" and al["left"]["right"]["left"] == "BOS"
    assert (al["right"]["left"], al["right"]["right"]) == ("CLE", "HOU")


def test_six_club_format_equal_clubs():
    seeds, wins, talent = _equal_bracket("six")
    ws = ic.world_series_probs(seeds, wins, talent, fmt="six", home_edge=0.0)
    for lg in (AL6, NL6):
        assert ws[lg[0]] == pytest.approx(1 / 8) and ws[lg[1]] == pytest.approx(1 / 8)
        for s in lg[2:]:
            assert ws[s] == pytest.approx(1 / 16)


def test_bracket_is_proj_current_line_for_line():
    """The six-club sampled bracket is a copy of proj_current's `_bracket_once`: the
    same seeds, records, probabilities and generator give the same postseason. If
    proj_current's bracket changes, this fails on purpose: `ix_v1` is frozen, so the
    divergence is recorded in the section the same day (X9) and this test is pinned
    to the frozen copy instead."""
    import proj_current as pc
    rnd = random.Random(2026)
    for trial in range(200):
        al = rnd.sample(DIVISIONS["AL_E"] + DIVISIONS["AL_C"] + DIVISIONS["AL_W"], 6)
        nl = rnd.sample(DIVISIONS["NL_E"] + DIVISIONS["NL_C"] + DIVISIONS["NL_W"], 6)
        seeds = {103: tuple(al), 104: tuple(nl)}
        wins = {o: rnd.randint(84, 100) for o in al + nl}
        ph = {(x, y): rnd.uniform(0.35, 0.65) for x in al + nl for y in al + nl if x != y}
        mine = ic.bracket_once(seeds, wins, ph, random.Random(trial), "six")
        theirs = pc._bracket_once(seeds, wins, ph, random.Random(trial))
        assert mine == theirs, trial
    assert (ic.WC_PATTERN, ic.LDS_PATTERN, ic.L7_PATTERN) == (
        pc.WC_PATTERN, pc.LDS_PATTERN, pc.L7_PATTERN)
    assert ic.POSTSEASON_SEED_OFFSET == pc.POSTSEASON_SEED_OFFSET
    for pa, pb in ((0.5, 0.5), (0.6, 0.45), (0.3, 0.7), (1e-9, 0.5)):
        assert ic.log5(pa, pb) == pc.log5(pa, pb)


@pytest.mark.parametrize("fmt", ["five", "six"])
def test_the_exact_bracket_agrees_with_the_sampled_bracket(fmt):
    """Unequal clubs and the registered home edge: the exact evaluator and the sampled
    bracket give the same title odds to within the sampling error."""
    n_seeds = 5 if fmt == "five" else 6
    rnd = random.Random(11)
    seeds = {"AL": AL6[:n_seeds], "NL": NL6[:n_seeds]}
    clubs = AL6[:n_seeds] + NL6[:n_seeds]
    wins = {c: 100 - i for i, c in enumerate(clubs)}
    talent = {c: rnd.uniform(0.45, 0.6) for c in clubs}
    exact = ic.world_series_probs(seeds, wins, talent, fmt=fmt)
    ph = {(a, b): ic.p_home_game(talent[a], talent[b]) for a in clubs for b in clubs
          if a != b}
    n = 40_000
    post = random.Random(5)
    counts = {c: 0 for c in clubs}
    for _ in range(n):
        counts[ic.bracket_once(seeds, wins, ph, post, fmt)["ws"]] += 1
    for c in clubs:
        se = math.sqrt(exact[c] * (1 - exact[c]) / n)
        assert abs(counts[c] / n - exact[c]) < 4.5 * se + 1e-9, c


def test_unforced_odds_agree_with_proj_current():
    """The rest-of-season loop is proj_current's: on the same field the unforced run's
    playoff and title odds agree with simulate_playoffs to within sampling error (the
    streams differ only in where ties draw, so the agreement is statistical)."""
    import proj_current as pc
    teams, pairs = _contested_field(seed=3, n_games=80)
    n = 4000
    mine = ic.simulate_forced(teams, pairs, forced=None, n_sims=n, seed=1)
    theirs = pc.simulate_playoffs(teams, pairs, n_sims=n, seed=1, home_edge=ic.HOME_EDGE)
    for o in ORGS:
        assert abs(mine["playoff"][o] / n - theirs[o]["playoffPct"]) < 0.04, o
        assert abs(mine["ws"][o] / n - theirs[o]["wsPct"]) < 0.025, o
        assert abs(mine["win_sum"][o] / n - theirs[o]["projWinsMean"]) < 0.15, o


def test_a_decided_series_or_an_unreached_club_is_refused():
    seeds, wins, talent = _equal_bracket()
    st: dict = {}
    _decide(st, "BOS", "DET", 2)
    with pytest.raises(ValueError):
        ic.postseason_stakes(seeds, wins, talent, "BOS", "DET", series_state=st)
    with pytest.raises(ValueError):          # DET lost; it cannot meet NYY
        ic.postseason_stakes(seeds, wins, talent, "NYY", "DET", series_state=st)
    with pytest.raises(ValueError):          # BOS has not played its wild card yet
        ic.postseason_stakes(seeds, wins, talent, "NYY", "BOS", series_state={})
    with pytest.raises(ValueError):          # not a postseason club
        ic.postseason_stakes(seeds, wins, talent, "NYY", "KCR")


def test_the_field_must_be_complete():
    teams, pairs = _contested_field()
    short = dict(teams)
    short.pop("COL")
    with pytest.raises(ValueError):
        ic.simulate_forced(short, [p for p in pairs if "COL" not in p], n_sims=10)
    with pytest.raises(ValueError):
        ic.simulate_forced(teams, pairs + [("NYY", "XXX")], n_sims=10)
    with pytest.raises(ValueError):
        ic.regular_season_stakes(teams, pairs, [len(pairs)], n_sims=10)


# ---------------------------------------------------------------------------
# Elo
# ---------------------------------------------------------------------------
def _games(seed: int = 4, n: int = 300, season: str = "2023") -> list[dict]:
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        h, a = rnd.sample(ORGS, 2)
        out.append({"game_pk": int(season) * 10_000 + i,
                    "date": f"{season}-{4 + i // 60:02d}-{1 + (i % 60) // 3:02d}",
                    "home_org": h, "away_org": a,
                    "home_runs": rnd.randint(0, 9), "away_runs": rnd.randint(0, 9)})
    return [g for g in out if g["home_runs"] != g["away_runs"]]


def _betting_elo():
    spec = importlib.util.spec_from_file_location("betting_elo_copy_check",
                                                  ROOT / "tools" / "betting_elo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_elo_constants_and_walk_are_copies_of_betting_elo():
    be = _betting_elo()
    assert (ic.ELO_K, ic.ELO_HOME_POINTS, ic.ELO_BASE) == (
        be.LITERATURE_K, be.LITERATURE_HOME_ADV_ELO, be.BASE_RATING)
    games = _games()
    walk = {r["game_pk"]: r["p_home"] for r in ic.elo_walk(games)}
    theirs = be.elo_probabilities(games)
    assert walk.keys() == theirs.keys()
    for pk, p in theirs.items():
        assert walk[pk] == p
    assert ic.elo_ratings_before(games, "2023-12-31") == be.final_ratings(games)
    # 24 Elo points at a coin flip is the registered home edge, to four places
    assert round(ic.elo_win_prob(1500, 1500) - 0.5, 4) == ic.HOME_EDGE


def test_elo_starts_flat_each_season_and_reads_strictly_before_the_date():
    g23, g24 = _games(1, 200, "2023"), _games(2, 200, "2024")
    walk = ic.elo_walk(g23 + g24)
    first24 = [r for r in walk if r["date"].startswith("2024")]
    seen = set()
    for r in first24:
        for side, club in (("r_home", r["home_org"]), ("r_away", r["away_org"])):
            if club not in seen:
                assert r[side] == ic.ELO_BASE
                seen.add(club)
    day = sorted({g["date"] for g in g24})[5]
    before = ic.elo_ratings_before(g23 + g24, day)
    expect = ic.elo_ratings_before([g for g in g24 if g["date"] < day], day)
    assert before == expect
    later = [g for g in g24 if g["date"] >= day]
    assert before == ic.elo_ratings_before(
        [g for g in g23 + g24 if g not in later] + [dict(g, home_runs=g["away_runs"],
                                                       away_runs=g["home_runs"])
                                                  for g in later], day)
    t = ic.talent_from_ratings({"NYY": 1600.0}, ["NYY", "BOS"])
    assert t["BOS"] == 0.5 and t["NYY"] == pytest.approx(1 / (1 + 10 ** -0.25))


# ---------------------------------------------------------------------------
# S, Q, A, D, the index, the bands and the standard error
# ---------------------------------------------------------------------------
def test_stakes_score_matches_the_lane_column():
    for G, s in LANE_S.items():
        assert round(ic.stakes_score(G, ic.G_REF_DRAFT), 3) == s, G
    assert ic.stakes_score(0.0, ic.G_REF_DRAFT) == 0.0
    assert ic.stakes_score(-0.001, ic.G_REF_DRAFT) == 0.0      # noise below zero clamps
    assert ic.stakes_score(2.5, ic.G_REF_DRAFT) == pytest.approx(1.0)
    assert ic.stakes_multiple(ic.G_REF_DRAFT, ic.G_REF_DRAFT) == pytest.approx(1.0)
    assert math.log1p(2 / ic.G_REF_DRAFT) == pytest.approx(5.168, abs=1e-3)
    xs = [i / 100 for i in range(201)]
    ss = [ic.stakes_score(x, ic.G_REF_DRAFT) for x in xs]
    assert all(b > a for a, b in zip(ss, ss[1:]))


def test_index_values_and_bands_match_the_lane_table():
    for (S, Q, A, D), (ii, band) in LANE_II:
        assert ic.index_value(S, Q, A, D) == ii, (S, Q, A, D)
        assert ic.band_of(ii) == band
    assert ic.index_value(0.5, 0.5, None, 1) is None
    assert ic.band_of(None) is None
    for v, b in ((0, "routine"), (29, "routine"), (30, "raised"), (49, "raised"),
                 (50, "high"), (69, "high"), (70, "peak"), (100, "peak")):
        assert ic.band_of(v) == b
    assert ic.index_value(1.0, 1.0, 1.0, 1) == 100
    assert ic.index_value(0.0, 0.0, 0.0, 0) == 0


def test_percentile_ranks_q_and_a():
    vals = {"a": 90, "b": 80, "c": 80, "d": 70, "e": 100}
    q = ic.percentile_ranks(vals)
    assert q == {"e": 1.0, "a": 0.75, "b": 0.375, "c": 0.375, "d": 0.0}
    assert ic.percentile_ranks({"x": 3}) == {"x": 0.5}
    assert ic.percentile_ranks({"x": 3, "y": 3}) == {"x": 0.5, "y": 0.5}
    assert ic.matchup_quality(vals, "a", "d") == 0.0
    assert ic.matchup_quality(vals, "a", "e") == 0.75
    board = {101: 120.0, 102: 96.0, 103: 105.0, 104: 80.0}
    assert ic.starter_percentile(101, board) == 1.0
    assert ic.starters_score(101, 103, board) == pytest.approx(2 / 3)
    assert ic.starters_score(101, None, board) is None        # unannounced
    assert ic.starters_score(101, 999, board) is None         # not on the board
    assert ic.division_flag("AL_E", "AL_E") == 1
    assert ic.division_flag("AL_E", "AL_C") == 0
    assert ic.division_flag(None, None) == 0


def test_paired_standard_error():
    d = [0, 2, 0, 2]
    se = ic.paired_standard_error(sum(d), sum(x * x for x in d), len(d))
    assert se == pytest.approx(math.sqrt((4 / 3) / 4))
    assert ic.paired_standard_error(0, 0, 1) is None
    assert ic.paired_standard_error(0, 0, 50) == 0.0


def test_projected_wins_are_current_wins_plus_expected_remaining():
    teams, pairs = _contested_field(seed=9, n_games=40)
    out = ic.regular_season_stakes(teams, pairs, [0], n_sims=3000, seed=4)
    for o in ORGS:
        exp = teams[o]["wins"] + sum(
            ic.p_home_game(teams[h]["p"], teams[a]["p"]) if o == h else
            1 - ic.p_home_game(teams[h]["p"], teams[a]["p"])
            for h, a in pairs if o in (h, a))
        assert abs(out["proj_wins"][o] - exp) < 0.12, o


# ---------------------------------------------------------------------------
# what the module may not be
# ---------------------------------------------------------------------------
def test_the_module_imports_no_served_code_and_touches_no_file():
    src = (ROOT / "intensity_core.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "math", "random"}, imported
    calls = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not calls & {"open", "exec", "eval", "__import__"}
    for word in ("read_text", "write_text", "Path(", "urlopen", "requests", "json."):
        assert word not in src, word


def test_the_module_names_no_column_and_no_serving_flag():
    assert "intensity_core.py" not in reg._ix_offenders()
    src = (ROOT / "intensity_core.py").read_text(encoding="utf-8")
    for flag in reg.FLAGS:
        assert flag not in src
    assert reg.EM_DASH not in src and reg.EN_DASH not in src
    assert not re.search(r"SHOW_INTENSITY_CHIP", src)
