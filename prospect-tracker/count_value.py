# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""RE288: the count-state run value table, the pure core.
docs/ewar-2026-10-15/RE288_COUNT_VALUE_GATE.md (count_value_v1).

WHAT IT IS. The mean runs scored from a pitch to the end of its half-inning, by the
state before the pitch: balls (0 to 3), strikes (0 to 2), the 3-bit base code of
ebr.base_code (0 to 7) and outs (0 to 2), 288 cells per MLB season. A measurement
substrate for later registered work (eABS challenge values, pitch economy, framing,
swing decisions); it predicts nothing and values no player.

THE WALK (gate part 1). A play's events are its pitches (corpus pitches table, in
pitch_number order) and its non-pitch events (corpus events table, by index); the
pitches fill the playEvents indices the non-pitch events leave free. The count starts
at 0-0 and moves by the call code of each pitch and by the automatic balls and strikes
of no_pitch events; the base-out state moves by the runner record's states_json
groups, a group at index i applying after the event at i. One observation per live
pitch thrown with the count not ended and fewer than three outs.

THE TABLE (gate part 3 as amended by part 11.1). Each observation's count departure
y = (runs of the play from the pitch on) + RE24_s(the play's end state) - RE24_s(the
pitch's base-out state): the runs after the play are replaced by their expectation,
which keeps the estimand (mean runs to the end of the half-inning) and drops the
variance of later plate appearances. Raw departures on the eBR fit set (ebr.fit_mask)
are pooled over P with K by the ebr_v1 method of moments (eBR's frozen season lambdas as
the run level); the pool and K are computed once and frozen with COUNT_VALUE_VERSION.
Gate 11.2 (owner question RE288-Q1, default (a)): RE288_s = RE24_s + lambda_s x the
pooled departure, the K-to-infinity end of the shrink; each season's raw departure is
published beside its table. Every table is monotone in the count (balls up, strikes
down) or the build refuses.

THE LEDGER (gate part 4). A state at count 0-0, or whose count has ended, is valued on
the season's RE24 (eBR's table); any other state on RE288; three outs on 0. The run
value of an event is value(after) - value(before) + runs at its index, so the values of
a play telescope to its RE24 change.

Pure: no network, no writes. tools/build_count_value.py reads the stores and writes
data/count_value.json.
"""
from __future__ import annotations

import hashlib
import json
import math

COUNT_VALUE_VERSION = "count_value_v1"
GATE_DOC = "docs/ewar-2026-10-15/RE288_COUNT_VALUE_GATE.md"
POOL_SEASONS: tuple[int, ...] = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
K_CLIP = (500.0, 5000.0)
COUNTS: tuple[tuple[int, int], ...] = tuple((b, s) for b in range(4) for s in range(3))
CELLS: tuple[str, ...] = tuple(f"{b}-{s}|{base}|{o}" for b, s in COUNTS
                               for base in range(8) for o in (0, 1, 2))
BASE_OUT = tuple((base, o) for base in range(8) for o in (0, 1, 2))

#: Gate part 5 and part 6 tolerances (registered before any number).
ZERO_ZERO_MAX_ABS = 0.03
ZERO_ZERO_WMAD = 0.01
IDENTITY_TOL = 1e-6
IDENTITY_SHARE = 0.999
RECEIPT_SHARE = 0.999

#: The frozen pool of count_value_v1: K and the sha256 of the frozen pool document,
#: pinned after the one passing computation on P (2026-10-15, gate 11.2: W 0.452645,
#: tau^2 0.00037639, K_raw 1202.6, inside the clip). A build whose recomputed pool
#: differs refuses.
FROZEN_K: float | None = 1202.6
FROZEN_POOL_SHA256: str | None = "560b9f3c895c4f538df9a0022a9d6cc738936ebe9ffc21b8da2ad8d8d941ec24"

#: Gate part 1, the count walk.
BALL_CODES = frozenset({"B", "*B", "P", "I", "V"})
STRIKE_CODES = frozenset({"C", "S", "W", "M", "Q", "T", "O", "L"})
FOUL_CODES = frozenset({"F", "R"})
TERMINAL_CODES = frozenset({"X", "D", "E", "H"})


class CountValueRefusal(RuntimeError):
    """A build that must not write: the message names the season and the cause."""


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def cell(balls: int, strikes: int, base: int, outs: int) -> str:
    return f"{balls}-{strikes}|{base}|{outs}"


def bits_of(a, b, c) -> int:
    """The 3-bit code of occupied bases from three runner ids (None for empty)."""
    return (0 if a is None else 1) | (0 if b is None else 2) | (0 if c is None else 4)


# --------------------------------------------------------------------------
# the count walk
# --------------------------------------------------------------------------
def apply_call(balls: int, strikes: int, code) -> tuple[int, int, bool, str]:
    """(balls, strikes, ended, kind) after one pitch with this call code.

    kind: ball, strike, foul, foul_two_strike, terminal or unknown. Ball four and
    strike three end the count; an unknown code leaves it."""
    code = "" if code is None else str(code)
    if code in BALL_CODES:
        balls += 1
        return balls, strikes, balls >= 4, "ball"
    if code in STRIKE_CODES:
        strikes += 1
        return balls, strikes, strikes >= 3, "strike"
    if code in FOUL_CODES:
        if strikes >= 2:
            return balls, strikes, False, "foul_two_strike"
        return balls, 1 + strikes, False, "foul"
    if code in TERMINAL_CODES:
        return balls, strikes, True, "terminal"
    return balls, strikes, False, "unknown"


def automatic_call(description) -> str | None:
    """'ball', 'strike' or None for a no_pitch event's description."""
    d = "" if description is None else str(description)
    if d.startswith("Automatic Ball"):
        return "ball"
    if d.startswith("Automatic Strike"):
        return "strike"
    return None


def pitch_indices(n_pitches: int, event_indices) -> list[int]:
    """The playEvents indices of a play's pitches: the indices of 0 to
    (pitches + events - 1) that no non-pitch event holds, in order."""
    taken = {int(i) for i in event_indices}
    n = int(n_pitches) + len(taken)
    return [i for i in range(n) if i not in taken][: int(n_pitches)]


def walk_play(start_bits: int, start_outs: int, pitch_codes, events=(), states=()) -> dict:
    """Walk one play. Pure.

    pitch_codes: call codes in pitch_number order.
    events: (index, type, description) of the play's non-pitch events.
    states: the runner record's states_json entries
            [index, b1, b2, b3, outs_before, a1, a2, a3, outs_after, runs].

    Returns obs [(balls, strikes, bits, outs, runs_before)], steps
    [(before, after, runs)] with a state (balls, strikes, bits, outs, ended),
    the reconstructed index of the last pitch, the count before it, the end state,
    the total runs and counters."""
    events = [(int(i), t, d) for i, t, d in events]
    p_idx = pitch_indices(len(pitch_codes), [e[0] for e in events])
    items: dict = {}
    for i, code in zip(p_idx, pitch_codes):
        items.setdefault(i, {})["pitch"] = code
    for i, t, d in events:
        items.setdefault(i, {})["event"] = (t, d)
    for st in states or ():
        i = -1 if st[0] is None else int(st[0])
        items.setdefault(i, {}).setdefault("groups", []).append(st)
    balls = strikes = 0
    bits, outs, ended = int(start_bits), int(start_outs), False
    runs = 0
    obs, steps = [], []
    c = {"automatic_ball": 0, "automatic_strike": 0, "intent_automatic_ball": 0,
         "two_strike_foul": 0, "pickoff_attempt": 0, "unknown_code": 0,
         "pitch_after_end": 0, "state_chain_break": 0, "walk": 0, "strikeout": 0,
         "in_play": 0, "hit_by_pitch": 0, "play_end_without_terminal": 0}
    last_pitch = p_idx[-1] if p_idx else None
    count_before_last = (None, None)
    for i in sorted(items):
        it = items[i]
        before = (balls, strikes, bits, outs, ended)
        if "pitch" in it:
            code = it["pitch"]
            if i == last_pitch:
                count_before_last = (balls, strikes)
            if ended or outs >= 3:
                c["pitch_after_end"] += 1
            else:
                obs.append((balls, strikes, bits, outs, runs))
                balls, strikes, ended, kind = apply_call(balls, strikes, code)
                if kind == "unknown":
                    c["unknown_code"] += 1
                elif kind == "foul_two_strike":
                    c["two_strike_foul"] += 1
                if ended:
                    if kind == "terminal":
                        c["hit_by_pitch" if code == "H" else "in_play"] += 1
                    elif balls >= 4:
                        c["walk"] += 1
                    else:
                        c["strikeout"] += 1
        if "event" in it:
            t, d = it["event"]
            if t == "no_pitch":
                a = automatic_call(d)
                if a is not None:
                    c["automatic_" + a] += 1
                    if a == "ball" and "Intentional" in str(d):
                        c["intent_automatic_ball"] += 1
                    if not ended and outs < 3:
                        if a == "ball":
                            balls += 1
                            ended = balls >= 4
                            if ended:
                                c["walk"] += 1
                        else:
                            strikes += 1
                            ended = strikes >= 3
                            if ended:
                                c["strikeout"] += 1
            elif t == "pickoff":
                c["pickoff_attempt"] += 1
        run_i = 0
        for st in it.get("groups", ()):
            b_before = bits_of(st[1], st[2], st[3])
            if b_before != bits or int(st[4]) != outs:
                c["state_chain_break"] += 1
            bits = bits_of(st[5], st[6], st[7])
            outs = int(st[8])
            run_i += int(st[9] or 0)
        runs += run_i
        steps.append((before, (balls, strikes, bits, outs, ended), run_i))
    if steps and not steps[-1][1][4]:
        # The play's end is the end of its count (the next play starts at 0-0): a plate
        # appearance that ends without ball four, strike three or a terminal code
        # (catcher's interference) still closes on RE24 (gate part 4).
        b_, a_, r_ = steps[-1]
        c["play_end_without_terminal"] = int(a_[3] < 3)
        steps[-1] = (b_, (a_[0], a_[1], a_[2], a_[3], True), r_)
    return {"obs": obs, "steps": steps, "last_pitch_index": last_pitch,
            "count_before_last": count_before_last, "end": (bits, outs), "runs": runs,
            "counters": c}


# --------------------------------------------------------------------------
# the ledger
# --------------------------------------------------------------------------
class Table:
    """A season's RE288 lookup (dict cell -> value)."""

    def __init__(self, table: dict):
        self.t = table

    def __call__(self, balls: int, strikes: int, base: int, outs: int) -> float:
        return self.t[cell(balls, strikes, base, outs)]


def state_value(t288, re24, state) -> float:
    """Gate part 4: three outs 0; count 0-0 or ended RE24; otherwise RE288."""
    balls, strikes, bits, outs, ended = state
    if outs >= 3:
        return 0.0
    if ended or (balls == 0 and strikes == 0):
        return re24(bits, outs)
    return t288(balls, strikes, bits, outs)


def event_values(walk: dict, t288, re24) -> list[float]:
    """The run value of every step of a walked play."""
    return [state_value(t288, re24, a) - state_value(t288, re24, b) + r
            for b, a, r in walk["steps"]]


def re24_change(start_bits: int, start_outs: int, end_bits: int, end_outs: int, runs, re24) -> float:
    def v(b, o):
        return 0.0 if o >= 3 else re24(b, o)
    return float(runs) + v(end_bits, end_outs) - v(start_bits, start_outs)


def forced_walk(bits: int) -> tuple[int, int]:
    """(new bits, runs) after a walk or hit by pitch: the batter takes first and
    only forced runners advance."""
    on1, on2, on3 = bool(bits & 1), bool(bits & 2), bool(bits & 4)
    runs = 0
    if on1:
        if on2:
            if on3:
                runs = 1
            on3 = True
        on2 = True
    on1 = True
    return (1 if on1 else 0) | (2 if on2 else 0) | (4 if on3 else 0), runs


def called_pitch_value(t288, re24, balls: int, strikes: int, bits: int, outs: int) -> float:
    """Value after a ball minus value after a strike at this state (gate part 3):
    ball four is a forced walk on RE24, strike three a strikeout on RE24 (0 at three
    outs); otherwise the next count on the ledger's state value."""
    if balls >= 3:
        nb, r = forced_walk(bits)
        v_ball = r + re24(nb, outs)
    else:
        v_ball = state_value(t288, re24, (1 + balls, strikes, bits, outs, False))
    if strikes >= 2:
        v_strike = 0.0 if 1 + outs >= 3 else re24(bits, 1 + outs)
    else:
        v_strike = state_value(t288, re24, (balls, 1 + strikes, bits, outs, False))
    return v_ball - v_strike


# --------------------------------------------------------------------------
# the estimand
# --------------------------------------------------------------------------
def raw_cells(balls, strikes, bits, outs, ros) -> dict:
    """{cell: {n, mean, var}} from parallel arrays of fit-set observations."""
    import numpy as np
    b = np.asarray(balls, dtype=np.int64)
    s = np.asarray(strikes, dtype=np.int64)
    base = np.asarray(bits, dtype=np.int64)
    o = np.asarray(outs, dtype=np.int64)
    y = np.asarray(ros, dtype=float)
    key = ((b * 3 + s) * 8 + base) * 3 + o
    n = np.bincount(key, minlength=288)
    sm = np.bincount(key, weights=y, minlength=288)
    sq = np.bincount(key, weights=y * y, minlength=288)
    out = {}
    for k, c in enumerate(CELLS):
        nk = int(n[k])
        if nk == 0:
            continue
        mean = float(sm[k] / nk)
        var = float((sq[k] - nk * mean * mean) / (nk - 1)) if nk > 1 else 0.0
        out[c] = {"n": nk, "mean": mean, "var": max(var, 0.0)}
    return out


def pool_table(raw_by_season: dict) -> dict:
    pool = {}
    for c in CELLS:
        n = sum(raw_by_season[s][c]["n"] for s in raw_by_season if c in raw_by_season[s])
        if n == 0:
            raise CountValueRefusal(f"pool cell {c} is empty")
        pool[c] = sum(raw_by_season[s][c]["n"] * raw_by_season[s][c]["mean"]
                      for s in raw_by_season if c in raw_by_season[s]) / n
    return pool


def season_lambda(raw: dict, pool: dict) -> float:
    num = sum(raw[c]["n"] * raw[c]["mean"] for c in CELLS if c in raw)
    den = sum(raw[c]["n"] * pool[c] for c in CELLS if c in raw)
    return num / den


def shrink_constant(raw_by_season: dict, pool: dict, lambdas: dict | None = None) -> dict:
    """K = W / tau^2, ebr.shrink_constant's method of moments over the cells present
    with n >= 2 in every season; clipped to K_CLIP. ``lambdas`` ({season: run level})
    replaces the season lambda of the cells themselves (gate 11.1: eBR's frozen
    lambdas scale the count departures)."""
    import numpy as np
    seasons = sorted(raw_by_season)
    lam = ({s: float(lambdas[s]) for s in seasons} if lambdas is not None
           else {s: season_lambda(raw_by_season[s], pool) for s in seasons})
    used = [c for c in CELLS if all(c in raw_by_season[s] and raw_by_season[s][c]["n"] >= 2
                                    for s in seasons)]
    if not used:
        raise CountValueRefusal("no cell is present in every pool season")
    within, tau = [], []
    for c in used:
        ms = np.array([raw_by_season[s][c]["mean"] / lam[s] for s in seasons])
        ns = np.array([raw_by_season[s][c]["n"] for s in seasons], dtype=float)
        vs = np.array([raw_by_season[s][c]["var"] / lam[s] ** 2 for s in seasons])
        between = float(np.var(ms, ddof=1)) if len(seasons) > 1 else 0.0
        samp = float(np.mean(vs / ns))
        tau.append(max(between - samp, 0.0))
        within.append(float(np.average(vs, weights=ns)))
    w = float(np.mean(within))
    t2 = float(np.mean(tau))
    k_raw = (w / t2) if t2 > 0 else float("inf")
    k = min(max(k_raw, K_CLIP[0]), K_CLIP[1])
    return {"K": round(k, 1), "K_raw": (round(k_raw, 1) if math.isfinite(k_raw) else None),
            "W": round(w, 6), "tau2": round(t2, 8), "cells_used": len(used)}


def pooled_departure(pool: dict, lam: float) -> dict:
    """lambda_s D_pool(c): the season departure of gate 11.2 (RE288-Q1 default (a))."""
    return {c: lam * pool[c] for c in CELLS}


def shrunk_departure(raw: dict, pool: dict, k: float, lam: float) -> dict:
    """D^_s(c) = [n D_s + K lambda_s D_pool] / [n + K]: the per-season shrink of gate
    11.1, which refused (10.2); kept for RE288-Q1 options (b) and (c). n 0 gives
    lambda pool."""
    t = {}
    for c in CELLS:
        r = raw.get(c)
        n = r["n"] if r else 0
        m = r["mean"] if r else 0.0
        t[c] = (n * m + k * lam * pool[c]) / (n + k)
    return t


def assemble(re24_table: dict, departure: dict) -> dict:
    """RE288(c) = RE24(base, outs) + the count departure of c (gate 11.1)."""
    return {c: re24_table[c.split("|", 1)[1]] + departure[c] for c in CELLS}


def count_monotone_violations(table: dict) -> list[str]:
    """Gate invariant 2: at fixed base-out, a ball never lowers the value and a
    strike never raises it."""
    v = []
    for base, o in BASE_OUT:
        for b in range(3):
            for s in range(3):
                if table[cell(b + 1, s, base, o)] < table[cell(b, s, base, o)]:
                    v.append(f"{b}-{s}->{b + 1}-{s}@{base}|{o}")
        for b in range(4):
            for s in range(2):
                if table[cell(b, 1 + s, base, o)] > table[cell(b, s, base, o)]:
                    v.append(f"{b}-{s}->{b}-{1 + s}@{base}|{o}")
    return v


ADD_RUNNER = {1: (0,), 2: (0,), 3: (1, 2), 4: (0,), 5: (1, 4), 6: (2, 4), 7: (3, 5, 6)}


def base_out_violations(table: dict) -> list[str]:
    """Reported, never refusing: at a fixed count, adding a runner lowers the value
    or adding an out raises it."""
    v = []
    for b, s in COUNTS:
        for o in (0, 1, 2):
            for hi, lows in ADD_RUNNER.items():
                for lo in lows:
                    if table[cell(b, s, hi, o)] < table[cell(b, s, lo, o)]:
                        v.append(f"{b}-{s}@{lo}->{hi}|{o}")
        for base in range(8):
            for o in (0, 1):
                if table[cell(b, s, base, o + 1)] > table[cell(b, s, base, o)]:
                    v.append(f"{b}-{s}@{base}|{o}->{o + 1}")
    return v


def zero_zero_check(table: dict, re24_table: dict, raw: dict) -> dict:
    """Gate invariant 1: the 0-0 row against RE24, per base-out cell; the weights
    are the season's 0-0 observation counts."""
    diffs, ws = {}, {}
    for base, o in BASE_OUT:
        d = table[cell(0, 0, base, o)] - re24_table[f"{base}|{o}"]
        diffs[f"{base}|{o}"] = d
        ws[f"{base}|{o}"] = (raw.get(cell(0, 0, base, o)) or {}).get("n", 0)
    tw = sum(ws.values())
    wmad = (sum(abs(diffs[k]) * ws[k] for k in diffs) / tw) if tw else float("nan")
    worst = max(diffs, key=lambda k: abs(diffs[k]))
    max_abs = abs(diffs[worst])
    return {"max_abs": max_abs, "worst_cell": worst, "wmad": wmad,
            "pass": bool(max_abs <= ZERO_ZERO_MAX_ABS and wmad <= ZERO_ZERO_WMAD),
            "diffs": diffs}


def count_marginal(table: dict, raw: dict, t288=None, re24=None, raw_ros: dict | None = None) -> dict:
    """The 12-cell count marginal: n, the raw mean of runs to the end of the half at
    the count (from ``raw_ros`` when given, else ``raw``), rv_vs_00
    (occupancy-weighted RE288(count) - RE288(0-0), the weights the observation counts
    of ``raw``) and, when the ledger lookups are given, the called-pitch value (value
    after a ball minus after a strike)."""
    src = raw if raw_ros is None else raw_ros
    out = {}
    for b, s in COUNTS:
        n = sum((raw.get(cell(b, s, base, o)) or {}).get("n", 0) for base, o in BASE_OUT)
        if n == 0:
            out[f"{b}-{s}"] = {"n": 0, "re_mean": None, "rv_vs_00": None, "called_value": None}
            continue
        mean = sum((src.get(cell(b, s, base, o)) or {}).get("n", 0)
                   * (src.get(cell(b, s, base, o)) or {}).get("mean", 0.0)
                   for base, o in BASE_OUT) / n
        rv = sum((raw.get(cell(b, s, base, o)) or {}).get("n", 0)
                 * (table[cell(b, s, base, o)] - table[cell(0, 0, base, o)])
                 for base, o in BASE_OUT) / n
        cv = None
        if t288 is not None and re24 is not None:
            cv = sum((raw.get(cell(b, s, base, o)) or {}).get("n", 0)
                     * called_pitch_value(t288, re24, b, s, base, o)
                     for base, o in BASE_OUT) / n
        out[f"{b}-{s}"] = {"n": int(n), "re_mean": mean, "rv_vs_00": rv, "called_value": cv}
    return out


def table_sha(table: dict) -> str:
    return _sha({c: round(table[c], 6) for c in CELLS})


def pool_doc_sha(doc: dict) -> str:
    return _sha({k: v for k, v in doc.items() if k != "sha256"})


def frozen_pool_document(raw_by_season: dict, lambdas: dict) -> dict:
    """The count_value_v1 pool, computed ONCE over P: the pooled count departures with
    their n, K with its method-of-moments inputs and the season lambdas it used
    (eBR's frozen ones, gate 11.1)."""
    missing = [s for s in POOL_SEASONS if s not in raw_by_season or s not in lambdas]
    if missing:
        raise CountValueRefusal(f"the frozen pool needs every season of P; missing {missing}")
    raw = {s: raw_by_season[s] for s in POOL_SEASONS}
    pool = pool_table(raw)
    k = shrink_constant(raw, pool, {s: lambdas[s] for s in POOL_SEASONS})
    doc = {"count_value_version": COUNT_VALUE_VERSION, "pool_seasons": list(POOL_SEASONS),
           "estimator": "count departure against RE24 of the play's end state (gate 11.1)",
           "k_clip": list(K_CLIP), "d_pool": {c: round(pool[c], 9) for c in CELLS},
           "n_pool": {c: int(sum(raw[s][c]["n"] for s in raw if c in raw[s])) for c in CELLS},
           "K": k["K"], "K_raw": k["K_raw"], "W": k["W"], "tau2": k["tau2"],
           "cells_used": k["cells_used"],
           "fit_set_observations": {str(s): int(sum(v["n"] for v in raw[s].values()))
                                    for s in POOL_SEASONS},
           "lambda": {str(s): float(lambdas[s]) for s in POOL_SEASONS}}
    doc["sha256"] = pool_doc_sha(doc)
    return doc


def check_frozen_pool(doc: dict) -> None:
    """Refuse a pool document that is not the one frozen with COUNT_VALUE_VERSION."""
    if doc.get("count_value_version") != COUNT_VALUE_VERSION \
            or tuple(doc.get("pool_seasons") or ()) != POOL_SEASONS:
        raise CountValueRefusal(f"the pool document is not {COUNT_VALUE_VERSION}'s")
    if doc.get("sha256") != pool_doc_sha(doc):
        raise CountValueRefusal("the pool document's sha256 does not match its content")
    if FROZEN_POOL_SHA256 is not None and doc["sha256"] != FROZEN_POOL_SHA256:
        raise CountValueRefusal(f"the pool differs from the one frozen with {COUNT_VALUE_VERSION} "
                                f"({doc['sha256'][:12]} against {FROZEN_POOL_SHA256[:12]})")
    if FROZEN_K is not None and float(doc["K"]) != float(FROZEN_K):
        raise CountValueRefusal(f"K {doc['K']} differs from the frozen {FROZEN_K}")
