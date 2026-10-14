# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Synthetic fixtures for the eBR tests (test_ebr_core.py, test_ebr_substrate.py,
test_ebr_gate_look.py): play-by-play built with the runner record's own walk
(tools/build_runner_moves.walk_game) from hand-written payload plays, plus a
padding of plate-appearance rows that fills all 24 base-out cells of the fit
set. Nothing here reads a cache or the network.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_runner_moves as brm  # noqa: E402

A, B, C, D, E, F = 101, 102, 103, 104, 105, 106
PAD_RUNNERS = (991, 992, 993)
PAD_BATTER = 990
AWAY, HOME, VENUE = 10, 20, 30

#: A monotone RE24 table (a typical modern season), for event-level tests.
STD_RE = {
    "0|0": 0.50, "0|1": 0.27, "0|2": 0.10,
    "1|0": 0.88, "1|1": 0.52, "1|2": 0.22,
    "2|0": 1.12, "2|1": 0.68, "2|2": 0.32,
    "3|0": 1.47, "3|1": 0.90, "3|2": 0.43,
    "4|0": 1.34, "4|1": 0.94, "4|2": 0.36,
    "5|0": 1.75, "5|1": 1.15, "5|2": 0.49,
    "6|0": 1.96, "6|1": 1.36, "6|2": 0.57,
    "7|0": 2.25, "7|1": 1.53, "7|2": 0.75,
}


# ---------------------------------------------------------------------------
# payload builders (the winProbability play shape)
# ---------------------------------------------------------------------------
def pitch(idx, *, in_play=False, balls=0, strikes=0, hit=None):
    ev = {"index": idx, "isPitch": True, "type": "pitch",
          "details": {"isInPlay": in_play, "call": {"code": "X" if in_play else "S"}},
          "count": {"balls": balls, "strikes": strikes}}
    if hit is not None:
        ev["hitData"] = hit
        ev["defense"] = {"left": {"id": 7}, "center": {"id": 8}, "right": {"id": 9}}
    return ev


def action(idx, event_type):
    return {"index": idx, "isPitch": False, "type": "action", "details": {"eventType": event_type}}


def entry(rid, start, end, pi, *, reason=None, event_type=None, is_out=False, origin="same",
          out_base=None, credits=()):
    return {"movement": {"originBase": (start if origin == "same" else origin), "start": start,
                         "end": (None if is_out else end), "outBase": out_base,
                         "isOut": is_out, "outNumber": None},
            "details": {"runner": {"id": rid}, "playIndex": pi, "movementReason": reason,
                        "eventType": event_type, "isScoringEvent": end == "score" and not is_out},
            "credits": [{"player": {"id": pid}, "position": {"code": pos}, "credit": cr}
                        for pid, pos, cr in credits]}


def play(abi, batter, events, runners, *, outs, event_type, inning=1, half="top", pa=True,
         year=2024):
    return {"result": {"type": "atBat", "eventType": event_type, "awayScore": 0, "homeScore": 0},
            "about": {"atBatIndex": abi, "halfInning": half, "inning": inning,
                      "startTime": f"{year}-06-01T18:00:00Z"},
            "count": {"balls": 0, "strikes": 0, "outs": outs},
            "matchup": {"batter": {"id": batter}, "pitcher": {"id": 900}},
            "playEvents": events, "runners": runners,
            "credits": ([{"player": {"id": batter}, "credit": "b_pa"}] if pa else []),
            "atBatIndex": abi}


def hit(traj, loc, x=130.0, y=100.0):
    return {"trajectory": traj, "location": loc, "coordinates": {"coordX": x, "coordY": y}}


def single(abi, batter, *, outs=0, extra=(), loc="8", half="top", inning=1):
    return play(abi, batter, [pitch(0, in_play=True, hit=hit("line_drive", loc))],
                [entry(batter, None, "1B", 0, event_type="single", origin=None)] + list(extra),
                outs=outs, event_type="single", half=half, inning=inning)


def strikeout(abi, batter, *, outs, extra=(), pi=2, half="top", inning=1):
    evs = [pitch(i) for i in range(pi + 1)]
    return play(abi, batter, evs,
                [entry(batter, None, None, pi, event_type="strikeout", is_out=True, origin=None)]
                + list(extra), outs=outs, event_type="strikeout", half=half, inning=inning)


# ---------------------------------------------------------------------------
# the scenario games
# ---------------------------------------------------------------------------
def scenario_games() -> dict:
    """{game_pk: (plays, info)}: every event family eBR prices or excludes."""
    g = {}
    # 1: a single moving the runner first to third (class H), then a steal of second on a strikeout
    g[1] = [single(0, A),
            single(1, B, extra=[entry(A, "1B", "3B", 0, reason="r_adv_play", event_type="single")]),
            strikeout(2, C, outs=1, extra=[entry(B, "1B", "2B", 2, reason="r_stolen_base_2b",
                                                  event_type="stolen_base_2b")])]
    # 2: a double steal (A on 2B, B on 1B), then a fly out
    g[2] = [single(0, A),
            single(1, B, extra=[entry(A, "1B", "2B", 0, reason="r_adv_force", event_type="single")]),
            play(2, C, [pitch(0), action(1, "stolen_base_3b"),
                        pitch(2, in_play=True, hit=hit("fly_ball", "9"))],
                 [entry(A, "2B", "3B", 1, reason="r_stolen_base_3b", event_type="stolen_base_3b"),
                  entry(B, "1B", "2B", 1, reason="r_stolen_base_2b", event_type="stolen_base_2b"),
                  entry(C, None, None, 2, event_type="field_out", is_out=True, origin=None)],
                 outs=1, event_type="field_out")]
    # 3: a caught stealing for the third out
    g[3] = [play(0, D, [pitch(0, in_play=True, hit=hit("ground_ball", "6"))],
                 [entry(D, None, None, 0, event_type="field_out", is_out=True, origin=None)],
                 outs=1, event_type="field_out"),
            play(1, E, [pitch(0, in_play=True, hit=hit("ground_ball", "4"))],
                 [entry(E, None, None, 0, event_type="field_out", is_out=True, origin=None)],
                 outs=2, event_type="field_out"),
            single(2, A, outs=2),
            play(3, C, [pitch(0), action(1, "caught_stealing_2b")],
                 [entry(A, "1B", None, 1, reason="r_caught_stealing_2b", is_out=True,
                        event_type="caught_stealing_2b", out_base="2B")],
                 outs=3, event_type="caught_stealing_2b", pa=False)]
    # 4: a pickoff of a runner not attempting
    g[4] = [single(0, B),
            play(1, C, [action(0, "pickoff_1b"), pitch(1)],
                 [entry(B, "1B", None, 0, reason="r_pickoff_1b", is_out=True,
                        event_type="pickoff_1b", out_base="1B")],
                 outs=1, event_type="pickoff_1b", pa=False)]
    # 5: a wild pitch, a passed ball and a balk move A home: never priced
    g[5] = [single(0, A),
            play(1, C, [pitch(0), action(1, "wild_pitch"), pitch(2), action(3, "passed_ball"),
                        pitch(4), action(5, "balk"), pitch(6)],
                 [entry(A, "1B", "2B", 1, reason="r_adv_play", event_type="wild_pitch"),
                  entry(A, "2B", "3B", 3, reason="r_adv_play", event_type="passed_ball"),
                  entry(A, "3B", "score", 5, reason="r_adv_play", event_type="balk"),
                  entry(C, None, None, 6, event_type="strikeout", is_out=True, origin=None)],
                 outs=1, event_type="strikeout")]
    # 6: a ground-ball double play
    g[6] = [single(0, A),
            play(1, B, [pitch(0, in_play=True, hit=hit("ground_ball", "6"))],
                 [entry(A, "1B", None, 0, reason="r_force_out", is_out=True,
                        event_type="grounded_into_double_play", out_base="2B"),
                  entry(B, None, None, 0, event_type="grounded_into_double_play", is_out=True,
                        origin=None, out_base="1B")],
                 outs=2, event_type="grounded_into_double_play")]
    # 7: an error carries the runner past second: the advance is truncated at the error
    g[7] = [single(0, A),
            single(1, B, extra=[entry(A, "1B", "2B", 0, reason="r_adv_force", event_type="single"),
                                entry(A, "2B", "3B", 0, reason="r_adv_throw", event_type="single",
                                      credits=[(8, "8", "f_throwing_error")])])]
    # 8: a fly ball out with a tag-up from first (class A)
    g[8] = [single(0, A),
            play(1, B, [pitch(0, in_play=True, hit=hit("fly_ball", "8", 125.0, 60.0))],
                 [entry(B, None, None, 0, event_type="field_out", is_out=True, origin=None),
                  entry(A, "1B", "2B", 0, reason="r_adv_tag", event_type="field_out")],
                 outs=1, event_type="field_out")]
    # 9: A bats for the home club (a second stint) and steals second
    g[9] = [single(0, A, half="bottom"),
            strikeout(1, D, outs=1, half="bottom",
                      extra=[entry(A, "1B", "2B", 2, reason="r_stolen_base_2b",
                                   event_type="stolen_base_2b")])]
    # 10: a single with two runners: B scores from second, A holds at second (class H, B)
    g[10] = [single(0, A), single(1, B, extra=[entry(A, "1B", "2B", 0, reason="r_adv_force",
                                                     event_type="single")]),
             single(2, C, loc="9", extra=[entry(A, "2B", "score", 0, reason="r_adv_play",
                                                event_type="single"),
                                          entry(B, "1B", "2B", 0, reason="r_adv_force",
                                                event_type="single")])]
    # 11: a ground-ball force at second that is not a double play (the eGDP cost's other arm)
    g[11] = [single(0, A),
             play(1, B, [pitch(0, in_play=True, hit=hit("ground_ball", "4"))],
                  [entry(B, None, "1B", 0, event_type="force_out", origin=None),
                   entry(A, "1B", None, 0, reason="r_force_out", is_out=True, event_type="force_out",
                         out_base="2B")],
                  outs=1, event_type="force_out")]
    # 12: a double, then an unforced runner on second holds on a ground-ball out (class G)
    g[12] = [play(0, A, [pitch(0, in_play=True, hit=hit("line_drive", "7", 90.0, 90.0))],
                  [entry(A, None, "2B", 0, event_type="double", origin=None)],
                  outs=0, event_type="double"),
             play(1, B, [pitch(0, in_play=True, hit=hit("ground_ball", "6"))],
                  [entry(B, None, None, 0, event_type="field_out", is_out=True, origin=None)],
                  outs=1, event_type="field_out")]
    return g


def scenario_frames(season=2024, games=None):
    """(pa, rn) DataFrames for the scenario games of one season."""
    games = scenario_games() if games is None else games
    pa_rows, rn_rows = [], []
    for k, plays in sorted(games.items()):
        pk = season * 1000 + k
        for p in plays:
            p["about"]["startTime"] = f"{season}-06-01T18:00:00Z"
        pa, rn = brm.walk_game(plays, game_pk=pk, season=season,
                               info={"away_id": AWAY, "home_id": HOME, "venue_id": VENUE,
                                     "scheduled_innings": 9}, diag={})
        pa_rows.extend(pa)
        rn_rows.extend(rn)
    pa_df = brm._frame(pa_rows, brm.PA_INT_COLS, ("game_pk", "at_bat_index"))
    rn_df = brm._frame(rn_rows, brm.RUNNER_INT_COLS, ("game_pk", "at_bat_index", "seq"))
    return pa_df, rn_df


def _pad_row(season, pk, inning, half, abi, outs_before, outs_after, b, runs):
    on = [PAD_RUNNERS[i] if b & (1 << i) else None for i in range(3)]
    return {
        "game_pk": pk, "season": season, "level": "mlb", "half": half, "inning": inning,
        "at_bat_index": abi, "batter_id": PAD_BATTER,
        "bat_team_id": AWAY if half == "top" else HOME,
        "fld_team_id": HOME if half == "top" else AWAY, "venue_id": VENUE,
        "scheduled_innings": 9, "event_type": "field_out", "event": "Flyout",
        "is_pa": False, "trajectory": None, "hit_location": None, "coord_x": None,
        "coord_y": None, "launch_speed": None, "of_left_id": None, "of_center_id": None,
        "of_right_id": None, "fp_balls": None, "fp_strikes": None,
        "final_pitch_index": None, "in_play_index": None, "outs_before": outs_before,
        "on_first": on[0], "on_second": on[1], "on_third": on[2],
        "fp_on_first": None, "fp_on_second": None, "fp_on_third": None, "fp_outs": None,
        "end_on_first": None, "end_on_second": None, "end_on_third": None,
        "end_outs": None, "outs_after": outs_after, "runs_scored_on_play": runs,
        "runs_fp": runs, "runner_placed": False, "states_json": "[]"}


def padding_frame(season=2024, halves=400, seed=7, start_pk=None):
    """Complete fit-set half-innings of three rows (outs 0, 1, 2) with random
    occupancy by the padding runners and random runs: exercises the runs-to-end
    recipe inside a half-inning. Its cell means are noise, not a run environment."""
    rng = random.Random(seed * 100003 + season)
    rows = []
    pk0 = start_pk if start_pk is not None else season * 1000 + 500
    for h in range(halves):
        pk, inning, half = pk0 + h // 16, 1 + (h % 16) // 2, ("top" if h % 2 == 0 else "bottom")
        for o in range(3):
            rows.append(_pad_row(season, pk, inning, half, (h % 16) * 3 + o, o, o + 1,
                                 rng.randrange(8), rng.choice((0, 0, 0, 1, 1, 2))))
    return brm._frame(rows, brm.PA_INT_COLS, ("game_pk", "at_bat_index"))


def environment_frame(season=2024, per_cell=60, level=1.0, start_pk=None):
    """One-row fit-set half-innings (the third out on the play), ``per_cell`` in
    every base-out cell, whose runs-to-end average exactly ``level`` times STD_RE
    over each cell (a Bresenham sequence of whole runs): a monotone run
    environment for builds on fixtures."""
    rows = []
    pk0 = start_pk if start_pk is not None else season * 1000 + 500
    h = 0
    for c in sorted(STD_RE):
        b, o = (int(x) for x in c.split("|"))
        m = STD_RE[c] * level
        for i in range(per_cell):
            runs = math.floor((i + 1) * m) - math.floor(i * m)
            pk, inning, half = pk0 + h // 16, 1 + (h % 16) // 2, ("top" if h % 2 == 0 else "bottom")
            rows.append(_pad_row(season, pk, inning, half, h % 16, o, 3, b, runs))
            h += 1
    return brm._frame(rows, brm.PA_INT_COLS, ("game_pk", "at_bat_index"))


def season_frames(season=2024, *, per_cell=60, games=None):
    """A fixture season: the scenario games plus a monotone run environment whose
    level moves a little by season."""
    pa, rn = scenario_frames(season, games)
    pad = environment_frame(season, per_cell=per_cell, level=1.0 + 0.01 * (season % 7))
    pa = concat([pa, pad])
    pa = pa.sort_values(["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
    return pa, rn


def concat(frames):
    """Row-stack fixture frames in (game_pk, at_bat_index) order."""
    import warnings

    import pandas as pd
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        out = pd.concat(list(frames), ignore_index=True)
    return out.sort_values(["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
