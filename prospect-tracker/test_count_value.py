# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""RE288, the count-state run value table (count_value.py, tools/build_count_value.py).
docs/ewar-2026-10-15/RE288_COUNT_VALUE_GATE.md part 7: the edge cases on fixtures, the
estimand's refusals, and the invariants over the served artifact data/count_value.json.

The fixture games are winProbability-shaped plays run through the runner record's own walk
(tools/build_runner_moves.walk_game) and the corpus row builders
(tools/build_pbp_corpus.pitch_rows, event_rows), so the receipts compare against the same
producers the real build reads. Nothing here reads a cache or the network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import count_value as cv  # noqa: E402
import ebr  # noqa: E402
import build_count_value as bcv  # noqa: E402
import build_pbp_corpus as bpc  # noqa: E402
import build_runner_moves as brm  # noqa: E402

ARTIFACT = ROOT / "data" / "count_value.json"

STD_RE = {
    "0|0": 0.50, "0|1": 0.27, "0|2": 0.10, "1|0": 0.88, "1|1": 0.52, "1|2": 0.22,
    "2|0": 1.12, "2|1": 0.68, "2|2": 0.32, "3|0": 1.47, "3|1": 0.90, "3|2": 0.43,
    "4|0": 1.34, "4|1": 0.94, "4|2": 0.36, "5|0": 1.75, "5|1": 1.15, "5|2": 0.49,
    "6|0": 1.96, "6|1": 1.36, "6|2": 0.57, "7|0": 2.25, "7|1": 1.53, "7|2": 0.75,
}


def std_288(ball=0.03, strike=-0.05) -> dict:
    return {cv.cell(b, s, base, o): STD_RE[f"{base}|{o}"] + ball * b + strike * s
            for b, s in cv.COUNTS for base, o in cv.BASE_OUT}


# ---------------------------------------------------------------------------
# payload builders (the winProbability play shape)
# ---------------------------------------------------------------------------
def pev(i, n, code, b, s, o):
    return {"index": i, "pitchNumber": n, "isPitch": True, "type": "pitch",
            "details": {"call": {"code": code}, "isInPlay": code in ("X", "D", "E")},
            "count": {"balls": b, "strikes": s, "outs": o}}


def npev(i, desc, b, s, o):
    return {"index": i, "isPitch": False, "type": "no_pitch",
            "details": {"description": desc}, "count": {"balls": b, "strikes": s, "outs": o}}


def pko(i, base, b, s, o):
    return {"index": i, "isPitch": False, "type": "pickoff",
            "details": {"description": f"Pickoff Attempt {base}"},
            "count": {"balls": b, "strikes": s, "outs": o}}


def act(i, et, b, s, o):
    return {"index": i, "isPitch": False, "type": "action",
            "details": {"eventType": et, "description": et},
            "count": {"balls": b, "strikes": s, "outs": o}}


def ent(rid, start, end, pi, *, reason=None, et=None, out=False, batter=False, out_base=None):
    return {"movement": {"originBase": None if batter else start, "start": start,
                         "end": None if out else end, "outBase": out_base, "isOut": out,
                         "outNumber": None},
            "details": {"runner": {"id": rid}, "playIndex": pi, "movementReason": reason,
                        "eventType": et, "isScoringEvent": end == "score" and not out},
            "credits": []}


def play(abi, batter, events, runners, *, outs, et, half="top", inning=1, pa=True):
    return {"result": {"type": "atBat", "eventType": et, "event": et, "awayScore": 0,
                       "homeScore": 0},
            "about": {"atBatIndex": abi, "halfInning": half, "inning": inning,
                      "startTime": "2025-06-01T18:00:00Z"},
            "count": {"balls": 0, "strikes": 0, "outs": outs},
            "matchup": {"batter": {"id": batter}, "pitcher": {"id": 900}},
            "playEvents": events, "runners": runners,
            "credits": ([{"player": {"id": batter}, "credit": "b_pa"}] if pa else []),
            "atBatIndex": abi}


A, B, C, D, E, F, G = 101, 102, 103, 104, 105, 106, 107


def game_one():
    """Top of the 1st, one run, three outs: two-strike fouls, a pickoff attempt and a
    steal between pitches, a pitch-clock automatic ball, an intentional walk of four
    automatic balls, a hit by pitch, an automatic strike and foul-bunt strike three, a
    bases-loaded walk and a ground out for the third out."""
    return [
        play(0, A, [pev(0, 1, "B", 1, 0, 0), pev(1, 2, "C", 1, 1, 0), pev(2, 3, "F", 1, 2, 0),
                    pev(3, 4, "F", 1, 2, 0), pev(4, 5, "X", 1, 2, 0)],
             [ent(A, None, "1B", 4, et="single", batter=True)], outs=0, et="single"),
        play(1, B, [pko(0, "1B", 0, 0, 0), pev(1, 1, "C", 0, 1, 0),
                    act(2, "stolen_base_2b", 0, 1, 0), pev(3, 2, "B", 1, 1, 0),
                    npev(4, "Automatic Ball - Pitcher Pitch Timer Violation", 2, 1, 0),
                    pev(5, 3, "T", 2, 2, 0), pev(6, 4, "S", 2, 3, 1)],
             [ent(A, "1B", "2B", 2, reason="r_stolen_base_2b", et="stolen_base_2b"),
              ent(B, None, None, 6, et="strikeout", out=True, batter=True)],
             outs=1, et="strikeout"),
        play(2, C, [npev(k, "Automatic Ball - Intentional", k + 1, 0, 1) for k in range(4)],
             [ent(C, None, "1B", 3, et="intent_walk", batter=True)], outs=1, et="intent_walk"),
        play(3, D, [pev(0, 1, "H", 0, 0, 1)],
             [ent(D, None, "1B", 0, et="hit_by_pitch", batter=True),
              ent(C, "1B", "2B", 0, reason="r_adv_force", et="hit_by_pitch"),
              ent(A, "2B", "3B", 0, reason="r_adv_force", et="hit_by_pitch")],
             outs=1, et="hit_by_pitch"),
        play(4, E, [pev(0, 1, "B", 1, 0, 1),
                    npev(1, "Automatic Strike - Batter Pitch Timer Violation", 1, 1, 1),
                    pev(2, 2, "L", 1, 2, 1), pev(3, 3, "L", 1, 3, 2)],
             [ent(E, None, None, 3, et="strikeout", out=True, batter=True)],
             outs=2, et="strikeout"),
        play(5, F, [pev(0, 1, "B", 1, 0, 2), pev(1, 2, "*B", 2, 0, 2), pev(2, 3, "B", 3, 0, 2),
                    pev(3, 4, "B", 4, 0, 2)],
             [ent(F, None, "1B", 3, et="walk", batter=True),
              ent(D, "1B", "2B", 3, reason="r_adv_force", et="walk"),
              ent(C, "2B", "3B", 3, reason="r_adv_force", et="walk"),
              ent(A, "3B", "score", 3, reason="r_adv_force", et="walk")],
             outs=2, et="walk"),
        play(6, G, [pev(0, 1, "X", 0, 0, 3)],
             [ent(G, None, None, 0, et="field_out", out=True, batter=True)],
             outs=3, et="field_out"),
    ]


def game_two():
    """Bottom of the 1st, no runs: a pickoff out between pitches, an automatic strike
    three on a timeout violation, a two-strike foul and a foul tip strike three."""
    h = "bottom"
    return [
        play(0, B, [pev(0, 1, "X", 0, 0, 0)],
             [ent(B, None, "1B", 0, et="single", batter=True)], outs=0, et="single", half=h),
        play(1, C, [pev(0, 1, "B", 1, 0, 0), pko(1, "1B", 1, 0, 0),
                    act(2, "pickoff_1b", 1, 0, 1), pev(3, 2, "C", 1, 1, 1),
                    pev(4, 3, "C", 1, 2, 1),
                    npev(5, "Automatic Strike - Batter Timeout Violation", 1, 3, 2)],
             [ent(B, "1B", None, 2, reason="r_pickoff_1b", et="pickoff_1b", out=True,
                  out_base="1B"),
              ent(C, None, None, 5, et="strikeout", out=True, batter=True)],
             outs=2, et="strikeout", half=h),
        play(2, D, [pev(0, 1, "S", 0, 1, 2), pev(1, 2, "S", 0, 2, 2), pev(2, 3, "F", 0, 2, 2),
                    pev(3, 4, "O", 0, 3, 3)],
             [ent(D, None, None, 3, et="strikeout", out=True, batter=True)],
             outs=3, et="strikeout", half=h),
    ]


def fixture_frames():
    import pandas as pd
    pa_rows, p_rows, e_rows = [], [], []
    for pk, plays in ((1, game_one()), (2, game_two())):
        pa, _ = brm.walk_game(plays, game_pk=pk, season=2025,
                              info={"away_id": 10, "home_id": 20, "venue_id": 30,
                                    "scheduled_innings": 9}, diag={})
        pa_rows += pa
        p_rows += bpc.pitch_rows(plays, game_pk=pk, season=2025)
        e_rows += bpc.event_rows(plays, game_pk=pk, season=2025)
    pa_df = brm._frame(pa_rows, brm.PA_INT_COLS, ("game_pk", "at_bat_index"))
    return {"pa": pa_df, "pitches": pd.DataFrame(p_rows), "events": pd.DataFrame(e_rows)}


@pytest.fixture(scope="module")
def frames():
    return fixture_frames()


@pytest.fixture(scope="module")
def walked(frames):
    return bcv.walk_season(2025, frames, ebr.RE(STD_RE))


def _nn(v):
    import pandas as pd
    return None if pd.isna(v) else v


def _walk(frames, pk, abi):
    pa = frames["pa"]
    row = pa[(pa.game_pk == pk) & (pa.at_bat_index == abi)].iloc[0]
    p = frames["pitches"]
    p = p[(p.game_pk == pk) & (p.at_bat_index == abi)].sort_values("pitch_number")
    e = frames["events"]
    e = e[(e.game_pk == pk) & (e.at_bat_index == abi)]
    bits = cv.bits_of(*(_nn(v) for v in (row.on_first, row.on_second, row.on_third)))
    return cv.walk_play(bits, int(row.outs_before), list(p.call_code),
                        [(int(r["index"]), r["type"], r["description"]) for _, r in e.iterrows()],
                        json.loads(row.states_json)), row


# ---------------------------------------------------------------------------
# the count walk
# ---------------------------------------------------------------------------
def test_a_two_strike_foul_leaves_the_count():
    assert cv.apply_call(1, 2, "F") == (1, 2, False, "foul_two_strike")
    assert cv.apply_call(1, 2, "R") == (1, 2, False, "foul_two_strike")
    assert cv.apply_call(1, 1, "F") == (1, 2, False, "foul")


def test_a_foul_tip_or_foul_bunt_with_two_strikes_is_a_strikeout():
    for code in ("T", "O", "L", "M"):
        assert cv.apply_call(0, 2, code) == (0, 3, True, "strike")


def test_ball_four_and_terminal_codes_end_the_count():
    assert cv.apply_call(3, 1, "*B") == (4, 1, True, "ball")
    assert cv.apply_call(2, 0, "P")[:3] == (3, 0, False)
    for code in ("X", "D", "E", "H"):
        assert cv.apply_call(1, 1, code) == (1, 1, True, "terminal")
    assert cv.apply_call(1, 1, "ZZ") == (1, 1, False, "unknown")
    assert cv.apply_call(1, 1, None) == (1, 1, False, "unknown")


def test_automatic_calls_read_the_description():
    assert cv.automatic_call("Automatic Ball - Pitcher Pitch Timer Violation") == "ball"
    assert cv.automatic_call("Automatic Ball - Intentional") == "ball"
    assert cv.automatic_call("Automatic Ball") == "ball"
    assert cv.automatic_call("Automatic Strike - Batter Timeout Violation") == "strike"
    assert cv.automatic_call(None) is None
    assert cv.automatic_call("Pickoff Attempt 1B") is None


def test_pitches_fill_the_indices_the_events_leave():
    assert cv.pitch_indices(4, [0, 2, 4]) == [1, 3, 5, 6]
    assert cv.pitch_indices(0, [0, 1, 2, 3]) == []
    assert cv.pitch_indices(3, []) == [0, 1, 2]


def test_steal_and_pickoff_attempt_between_pitches(frames):
    w, _ = _walk(frames, 1, 1)
    assert [o[:4] for o in w["obs"]] == [(0, 0, 1, 0), (0, 1, 2, 0), (2, 1, 2, 0), (2, 2, 2, 0)]
    assert w["counters"]["pickoff_attempt"] == 1
    assert w["counters"]["automatic_ball"] == 1
    assert w["counters"]["strikeout"] == 1
    assert w["end"] == (2, 1)


def test_two_strike_fouls_are_observed_at_the_same_count(frames):
    w, _ = _walk(frames, 1, 0)
    assert [o[:4] for o in w["obs"]] == [(0, 0, 0, 0), (1, 0, 0, 0), (1, 1, 0, 0),
                                         (1, 2, 0, 0), (1, 2, 0, 0)]
    assert w["counters"]["two_strike_foul"] == 1
    assert w["counters"]["in_play"] == 1


def test_an_intentional_walk_adds_no_observation(frames):
    w, _ = _walk(frames, 1, 2)
    assert w["obs"] == []
    assert w["counters"]["intent_automatic_ball"] == 4
    assert w["counters"]["walk"] == 1
    assert w["end"] == (3, 1)
    assert w["last_pitch_index"] is None


def test_an_automatic_strike_moves_the_count_without_an_observation(frames):
    w, _ = _walk(frames, 1, 4)
    assert [o[:4] for o in w["obs"]] == [(0, 0, 7, 1), (1, 1, 7, 1), (1, 2, 7, 1)]
    assert w["counters"]["automatic_strike"] == 1
    assert w["count_before_last"] == (1, 2)


def test_an_automatic_strike_three_ends_the_plate_appearance(frames):
    w, _ = _walk(frames, 2, 1)
    assert [o[:4] for o in w["obs"]] == [(0, 0, 1, 0), (1, 0, 0, 1), (1, 1, 0, 1)]
    assert w["counters"]["strikeout"] == 1
    assert w["end"] == (0, 2)
    assert w["steps"][-1][1][4] is True


def test_catchers_interference_closes_the_play_on_re24():
    # a foul-coded pitch with the catcher's interference: the batter takes first and the
    # count never ends by its own rule, so the play's end closes it
    w = cv.walk_play(0, 1, ["B", "F"], [], [[1, None, None, None, 1, 555, None, None, 1, 0]])
    assert w["steps"][-1][1] == (1, 1, 1, 1, True)
    assert w["counters"]["play_end_without_terminal"] == 1
    t288, re24 = cv.Table(std_288()), ebr.RE(STD_RE)
    assert sum(cv.event_values(w, t288, re24)) == pytest.approx(
        cv.re24_change(0, 1, 1, 1, 0, re24), abs=1e-12)
    # an inning-ending caught stealing is not counted as a plate appearance without an end
    w = cv.walk_play(1, 2, ["B"], [(1, "action", "caught_stealing_2b")],
                     [[1, 9, None, None, 2, None, None, None, 3, 0]])
    assert w["counters"]["play_end_without_terminal"] == 0
    assert sum(cv.event_values(w, t288, re24)) == pytest.approx(-STD_RE["1|2"], abs=1e-12)


def test_ball_four_with_the_bases_loaded_scores_inside_the_walk(frames):
    w, _ = _walk(frames, 1, 5)
    assert [o[:4] for o in w["obs"]] == [(0, 0, 7, 2), (1, 0, 7, 2), (2, 0, 7, 2), (3, 0, 7, 2)]
    assert all(o[4] == 0 for o in w["obs"])
    assert w["runs"] == 1 and w["end"] == (7, 2)


def test_the_receipts_agree_with_the_record_on_fixtures(walked):
    rc = walked["receipts"]
    assert rc["r1_ok"] == rc["r1_n"] == 9          # every play with a pitch (not the IBB)
    assert rc["r2_ok"] == rc["r2_n"] == 9
    assert rc["r3_ok"] == rc["r3_n"] == 10
    assert rc["end_ok"] == rc["end_n"] == 10
    assert rc["fit_plays"] == 10
    assert walked["counters"]["state_chain_break"] == 0
    assert walked["counters"]["unknown_code"] == 0
    assert walked["counters"]["pitch_after_end"] == 0


def test_observations_carry_runs_to_the_end_of_the_half(walked):
    obs = walked["obs"]
    top = obs[:len(obs) - 8]                        # game two has eight observations, last
    # one run scores on ball four of play 5: every top observation before it carries it,
    # the ground out after it carries none
    assert list(top[:-1, 4]) == [1.0] * (len(top) - 1)
    assert top[-1, 4] == 0.0
    assert list(obs[-8:, 4]) == [0.0] * 8


# ---------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------
def test_terminal_states_map_to_re24_and_the_third_out_to_zero():
    t288, re24 = cv.Table(std_288()), ebr.RE(STD_RE)
    assert cv.state_value(t288, re24, (0, 0, 3, 1, False)) == STD_RE["3|1"]
    assert cv.state_value(t288, re24, (1, 2, 3, 1, False)) == pytest.approx(STD_RE["3|1"] + 0.03 - 0.10)
    assert cv.state_value(t288, re24, (1, 3, 3, 2, True)) == STD_RE["3|2"]
    assert cv.state_value(t288, re24, (4, 0, 7, 1, True)) == STD_RE["7|1"]
    assert cv.state_value(t288, re24, (2, 2, 7, 3, False)) == 0.0


def test_per_event_values_sum_to_each_plays_re24_change(frames):
    t288, re24 = cv.Table(std_288()), ebr.RE(STD_RE)
    for pk, abi in ((1, k) for k in range(7)):
        w, row = _walk(frames, pk, abi)
        start = cv.bits_of(*(_nn(v) for v in (row.on_first, row.on_second, row.on_third)))
        end = cv.bits_of(*(_nn(v) for v in (row.end_on_first, row.end_on_second, row.end_on_third)))
        ch = cv.re24_change(start, int(row.outs_before), end, int(row.end_outs),
                            int(row.runs_scored_on_play), re24)
        assert sum(cv.event_values(w, t288, re24)) == pytest.approx(ch, abs=1e-12)


def test_the_vectorized_ledger_matches_the_pure_one(walked):
    out = bcv.ledger_identity(walked, std_288(), STD_RE)
    assert out["plays"] == 10 and out["exact"] == 10 and out["share"] == 1.0
    assert out["delta_sum"] == pytest.approx(out["change_sum"], abs=1e-9)


def test_a_broken_walk_breaks_the_identity(walked):
    bad = dict(walked)
    steps = walked["steps"].copy()
    steps[0, 10] += 1                               # a run that never scored
    bad["steps"] = steps
    out = bcv.ledger_identity(bad, std_288(), STD_RE)
    assert out["exact"] == out["plays"] - 1


def test_forced_walk_moves_only_forced_runners():
    assert cv.forced_walk(0) == (1, 0)
    assert cv.forced_walk(1) == (3, 0)
    assert cv.forced_walk(2) == (3, 0)
    assert cv.forced_walk(4) == (5, 0)
    assert cv.forced_walk(5) == (7, 0)
    assert cv.forced_walk(6) == (7, 0)
    assert cv.forced_walk(3) == (7, 0)
    assert cv.forced_walk(7) == (7, 1)


def test_called_pitch_value_at_full_count():
    t288, re24 = cv.Table(std_288()), ebr.RE(STD_RE)
    assert cv.called_pitch_value(t288, re24, 3, 2, 7, 2) == pytest.approx(1 + STD_RE["7|2"])
    assert cv.called_pitch_value(t288, re24, 3, 2, 0, 0) == pytest.approx(
        STD_RE["1|0"] - STD_RE["0|1"])
    v = cv.called_pitch_value(t288, re24, 1, 1, 0, 0)
    assert v == pytest.approx((STD_RE["0|0"] + 0.06 - 0.05) - (STD_RE["0|0"] + 0.03 - 0.10))
    assert v > 0


# ---------------------------------------------------------------------------
# the estimand and its refusals
# ---------------------------------------------------------------------------
def _raw_from(table, n=100):
    return {c: {"n": n, "mean": v, "var": 1.0} for c, v in table.items()}


def test_raw_cells_counts_and_means():
    r = cv.raw_cells([0, 0, 3], [0, 0, 2], [7, 7, 0], [2, 2, 0], [1.0, 3.0, 0.5])
    assert r["0-0|7|2"] == {"n": 2, "mean": 2.0, "var": 2.0}
    assert r["3-2|0|0"]["n"] == 1 and r["3-2|0|0"]["var"] == 0.0
    assert len(r) == 2


def test_the_departure_is_shrunk_by_the_ebr_recipe_and_added_to_re24():
    pool = {c: 0.03 * int(c[0]) - 0.05 * int(c[2]) for c in cv.CELLS}
    raw = {c: {"n": 500, "mean": v * 2.0, "var": 1.0} for c, v in pool.items() if c != "3-0|7|0"}
    d = cv.shrunk_departure(raw, pool, 1000.0, 1.1)
    c = "1-1|3|1"
    assert d[c] == pytest.approx((500 * pool[c] * 2.0 + 1000 * 1.1 * pool[c]) / 1500)
    assert d["3-0|7|0"] == pytest.approx(1.1 * pool["3-0|7|0"])
    t = cv.assemble(STD_RE, d)
    pdep = cv.pooled_departure(pool, 0.9)
    assert pdep[c] == pytest.approx(0.9 * pool[c])
    assert t[c] == pytest.approx(STD_RE["3|1"] + d[c])
    assert t["0-0|4|2"] == pytest.approx(STD_RE["4|2"])


def test_the_departure_replaces_later_runs_by_re24_of_the_end_state(walked):
    obs = walked["obs"]
    # play 0 of game one: a single from the empty bases, no run: y = RE24(1|0) - RE24(0|0)
    assert list(obs[:5, 5]) == pytest.approx([STD_RE["1|0"] - STD_RE["0|0"]] * 5)
    # ball four with the bases loaded and two out: one run, the state unchanged: y = 1
    assert list(obs[13:17, 5]) == pytest.approx([1.0] * 4)
    # the ground out for the third out: y = 0 - RE24(7|2)
    assert obs[17, 5] == pytest.approx(-STD_RE["7|2"])


def test_the_pool_refuses_an_empty_cell():
    raw = _raw_from(std_288())
    del raw["3-0|7|0"]
    with pytest.raises(cv.CountValueRefusal):
        cv.pool_table({2025: raw})


def test_k_is_clipped():
    seasons = {s: _raw_from(std_288(), n=1000) for s in (2024, 2025)}
    pool = cv.pool_table(seasons)
    k = cv.shrink_constant(seasons, pool)
    assert k["K"] == cv.K_CLIP[1] and k["K_raw"] is None
    k = cv.shrink_constant(seasons, pool, {2024: 1.0, 2025: 1.0})
    assert k["K"] == cv.K_CLIP[1]
    noisy = {2024: _raw_from(std_288(), n=1000),
             2025: {c: {"n": 1000, "mean": v + (0.5 if i % 2 else -0.5), "var": 1.0}
                    for i, (c, v) in enumerate(std_288().items())}}
    k = cv.shrink_constant(noisy, cv.pool_table(noisy), {2024: 1.0, 2025: 1.0})
    assert k["K"] == cv.K_CLIP[0]


def test_the_count_monotone_check_refuses_a_reversal():
    t = std_288()
    assert cv.count_monotone_violations(t) == []
    t["2-1|3|1"] = t["1-1|3|1"] - 0.001
    v = cv.count_monotone_violations(t)
    assert "1-1->2-1@3|1" in v
    t = std_288()
    t["1-2|0|0"] = t["1-1|0|0"] + 0.001
    assert "1-1->1-2@0|0" in cv.count_monotone_violations(t)


def test_base_out_violations_are_reported():
    t = std_288()
    assert cv.base_out_violations(t) == []
    t["0-0|4|0"] = t["0-0|0|0"] - 0.01
    assert "0-0@0->4|0" in cv.base_out_violations(t)


def test_the_zero_zero_check_fires():
    t = std_288()
    raw = _raw_from(t)
    ok = cv.zero_zero_check(t, STD_RE, raw)
    assert ok["pass"] and ok["max_abs"] == pytest.approx(0.0)
    t["0-0|4|0"] = STD_RE["4|0"] + 0.031
    bad = cv.zero_zero_check(t, STD_RE, raw)
    assert not bad["pass"] and bad["worst_cell"] == "4|0"
    t = {c: (v + 0.011 if c.startswith("0-0|") else v) for c, v in std_288().items()}
    bad = cv.zero_zero_check(t, STD_RE, raw)
    assert bad["max_abs"] < cv.ZERO_ZERO_MAX_ABS and not bad["pass"]


def test_the_count_marginal_is_zero_at_zero_zero():
    t = std_288()
    m = cv.count_marginal(t, _raw_from(t), cv.Table(t), ebr.RE(STD_RE))
    assert m["0-0"]["rv_vs_00"] == pytest.approx(0.0)
    assert m["3-0"]["rv_vs_00"] == pytest.approx(0.09)
    assert m["0-2"]["rv_vs_00"] == pytest.approx(-0.10)
    assert set(m) == {f"{b}-{s}" for b, s in cv.COUNTS}


def test_the_frozen_pool_refuses_a_changed_document():
    seasons = {s: _raw_from(std_288(), n=1000 + s % 7) for s in cv.POOL_SEASONS}
    lams = {s: 1.0 for s in cv.POOL_SEASONS}
    doc = cv.frozen_pool_document(seasons, lams)
    if cv.FROZEN_POOL_SHA256 is None:
        cv.check_frozen_pool(doc)
    tampered = dict(doc)
    tampered["K"] = 1.0
    with pytest.raises(cv.CountValueRefusal):
        cv.check_frozen_pool(tampered)
    with pytest.raises(cv.CountValueRefusal):
        cv.frozen_pool_document({2025: seasons[2025]}, lams)


def test_the_core_opens_no_socket_and_writes_nothing():
    src = (ROOT / "count_value.py").read_text(encoding="utf-8")
    for bad in ("import requests", "urllib", "socket", "open(", "write_text", "write_bytes"):
        assert bad not in src, bad


# ---------------------------------------------------------------------------
# the served artifact
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def artifact():
    if not ARTIFACT.exists():
        pytest.skip("data/count_value.json is not built")
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_the_artifact_is_dated_versioned_and_pinned(artifact):
    assert artifact["count_value_version"] == cv.COUNT_VALUE_VERSION
    assert artifact["generated_at"]
    assert artifact["gate_doc"] == cv.GATE_DOC
    assert artifact["pool_sha256"] == cv.FROZEN_POOL_SHA256
    assert float(artifact["K"]) == float(cv.FROZEN_K)
    assert cv.K_CLIP[0] <= artifact["K"] <= cv.K_CLIP[1]
    assert artifact["pool_seasons"] == list(cv.POOL_SEASONS)


def test_every_served_season_holds_its_invariants(artifact):
    assert set(artifact["by_season"]) == {str(s) for s in cv.POOL_SEASONS}
    for s, blk in artifact["by_season"].items():
        t = blk["re288"]
        assert set(t) == set(cv.CELLS), s
        assert cv.count_monotone_violations(t) == [], s
        inv = blk["invariants"]
        assert inv["zero_zero"]["pass"], s
        assert inv["zero_zero"]["max_abs"] <= cv.ZERO_ZERO_MAX_ABS
        assert inv["zero_zero"]["wmad"] <= cv.ZERO_ZERO_WMAD
        assert inv["ledger_identity"]["share"] >= cv.IDENTITY_SHARE, s
        assert inv["count_monotone_violations"] == 0
        for k in ("r1_index", "r2_count", "r3_runs"):
            assert blk["receipts"][k]["share"] >= cv.RECEIPT_SHARE, (s, k)
        for c in cv.CELLS:
            d = blk["re288"][c] - blk["re24"][c.split("|", 1)[1]]
            assert d == pytest.approx(blk["lambda"] * artifact["pool"]["d"][c], abs=2e-4), (s, c)
        for c, v in blk["re24"].items():
            assert abs(t[cv.cell(0, 0, *map(int, c.split("|")))] - v) <= cv.ZERO_ZERO_MAX_ABS + 1e-4
        assert blk["count_marginal"]["0-0"]["rv_vs_00"] == 0.0
        assert blk["count_marginal"]["3-0"]["rv_vs_00"] > 0 > blk["count_marginal"]["0-2"]["rv_vs_00"]


def test_the_served_pool_is_monotone_in_the_count(artifact):
    assert cv.count_monotone_violations(artifact["pool"]["re288"]) == []
    assert all(n > 0 for n in artifact["pool"]["n"].values())
