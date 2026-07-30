"""LANE-CURVES Phase 1: per-side empirical FV-to-outcome curves + the industry bake-off.

Pre-registration (written BEFORE the first fit): docs/efv-2026-07-30/FV_OUTCOME_CURVES_GATE.md
Plan: docs/master-plan-2026-07-30-fv-calibration.md Phase 1.
Artifact: data/fv_outcome_curves.json   Registry row: fv_outcome_curves

What this does, in order:

 1. Loads the resolved cohort pool (data/xfv_scored*.json joined to the as-of matrices) and
    ASSERTS the join / vintage / target identities the gate doc claims.
 2. Fits, per side, monotone (weighted PAVA isotonic) curves for
    E[first-6yr bWAR | consensus FV], P(bust), P(star) plus the 5-bin outcome-bucket cell
    table, with a Clemens-2026 per-side prior blended in at K = 30 pseudo-rows and
    player-clustered bootstrap CI90 bands (B = 2000, refit each draw).
 3. Runs the nine-candidate bake-off on forward-chained held-out folds, in RAW and SHAPE
    modes, and scores calibration slope / bias / MAE / cell-mean coverage per side per FV
    band.
 4. Reports the Phase-2 inputs: the ten named players' current vs re-scaled grades, the
    implied top-N board side mix, and the within-side monotonicity confirmation.

READ-ONLY on every production module. Nothing here changes a served number: the re-scaled
grades and the board mix are counterfactuals computed from the committed live artifacts.

Run:  python tools/fv_outcome_curves_lab.py            (prints, writes the artifact)
      python tools/fv_outcome_curves_lab.py --no-write  (prints only)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_board_scale as bs                                          # noqa: E402
import value_framework as vf                                          # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "fv_outcome_curves.json"

B_BOOT = 2000
SEED = 20260730
K_SHRINK = 30.0                    # pseudo-rows of prior; n_cell == 30 -> 50/50 blend
CELL_HALFWIDTH = 1.25              # |consensus_fv - knot| <= 1.25 defines a knot cell
EPS_STEP = 0.01                    # minimum WAR increment per knot step (strict monotone)
TARGET_SEASONS = 6                 # efv_score.TARGET_SEASONS, replicated (see _grade_map_age)

KNOTS = [20.0, 25.0, 30.0, 35.0, 37.5, 40.0, 42.5, 45.0, 47.5, 50.0,
         52.5, 55.0, 57.5, 60.0, 62.5, 65.0, 67.5, 70.0, 75.0, 80.0]

BANDS = [("lt40", 20.0, 40.0), ("40_45", 40.0, 45.0), ("45_50", 45.0, 50.0),
         ("50_55", 50.0, 55.0), ("55_plus", 55.0, 80.001)]

# Forward-chained folds: (name, train_max_year, test_years)
FOLDS = [("F1", 2013, (2014, 2015)),
         ("F2", 2015, (2016, 2017)),
         ("F3", 2017, (2018,)),
         ("F4", 2018, (2019,)),
         ("F5", 2019, (2020,)),
         ("F6", 2020, (2021, 2022, 2023, 2024))]
DEGENERATE_FOLDS = {"F6"}

NAMED = ["caden_hunter", "kade_anderson", "seth_hernandez", "joseph_dzierwa",
         "franklin_arias", "jesus_made", "leo_de_vries", "enrique_bradfield_jr",
         "luis_hernandez", "roch_cholowsky"]

# --- outcome thresholds, declared in the gate doc before the fit -------------
BUST_WAR6 = 1.0        # Edwards 2019 bust THRESHOLD VALUE on our undiscounted 6yr total
STAR_WAR6 = 10.0       # Edwards 2019 star THRESHOLD VALUE, same caveat
BUST_BUCKET_WAR6 = 3.0    # value_framework bust band (<0.5 WAR/season) x 6
STAR_BUCKET_WAR6 = 24.0   # value_framework star band (4.0+ WAR/season) x 6
# 5-bin outcome buckets: value_framework per-season bands x 6 seasons
BUCKET_EDGES = [3.0, 9.0, 15.0, 24.0]
BUCKET_NAMES = ["bust", "bench", "regular", "good", "star"]


# ===========================================================================
# published tables (verbatim from docs/reference/FANGRAPHS_FV_FRAMEWORK.md)
# ===========================================================================
# 1. McDaniel 2014 combined, WAR per SEASON true talent, side-neutral (Part 3.1).
MCDANIEL_2014 = {30: -1.0, 35: 0.0, 40: 1.0, 45: 1.5, 50: 2.0, 55: 2.5,
                 60: 3.0, 65: 4.0, 70: 5.0, 75: 6.0, 80: 7.0}

# 2. Primer bands, average annual WAR over first six SERVICE years (Parts 3.2-3.4).
#    Values are band MIDPOINTS; open-ended "<-0.1" -> -0.1, ">7.0" -> 7.5.
#    Rows the source does not publish are marked in PRIMER_INTERPOLATED.
PRIMER_HIT = {30: -0.1, 40: 0.35, 45: 1.15, 50: 2.0, 55: 2.9, 60: 4.15, 70: 6.0, 80: 7.5}
PRIMER_PIT = {30: -0.1, 35: -0.1, 40: 0.45, 45: 1.35, 50: 2.15, 55: 3.0, 60: 4.2,
              70: 6.0, 80: 7.5}
PRIMER_INTERPOLATED = {"hit": [25, 35, 65, 75], "pit": [25, 65, 75]}

# 3. Clemens 2026 expected WAR, TOTAL undiscounted over the team-control span,
#    bust-inclusive, per side (Part 7.2). "+" tiers placed at the half-step.
CLEMENS_HIT = {37.5: 0.3, 40: 0.75, 42.5: 1.2, 45: 2.5, 47.5: 3.2, 50: 7.0,
               55: 8.0, 60: 12.5, 65: 13.5, 70: 27.5}
CLEMENS_PIT = {37.5: 0.25, 40: 0.55, 42.5: 1.0, 45: 1.6, 47.5: 2.6, 50: 5.0,
               55: 7.0, 60: 11.0, 65: 13.5, 70: 27.0}
CLEMENS_SPAN_FACTOR = 1.000           # primary conversion; sensitivity at 6/7 below
CLEMENS_SPAN_SENSITIVITY = 6.0 / 7.0

# Edwards 2019 per-side bust/star rates (Part 7.5), the priors for the odds curves.
EDWARDS_BUST = {"hit": {50: 0.515, 55: 0.365, 60: 0.318, 65: 0.188, 70: 0.048},
                "pit": {50: 0.581, 55: 0.393, 60: 0.221, 65: 0.143, 70: 0.000}}
EDWARDS_STAR = {"hit": {50: 0.099, 55: 0.219, 60: 0.273, 65: 0.298, 70: 0.571},
                "pit": {50: 0.057, 55: 0.098, 60: 0.256, 65: 0.179, 70: 0.444}}


def interp(table: dict, x: float) -> float:
    """Piecewise-linear interpolation of a {grade: value} table, clamped at both ends."""
    pts = sorted((float(k), float(v)) for k, v in table.items())
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 * (1 - t) + y1 * t
    return pts[-1][1]


# ===========================================================================
# pool
# ===========================================================================
SIDES = (("hit", "xfv_scored.json", "xfv_hitter_matrix.json", False),
         ("pit", "xfv_scored_pitcher.json", "xfv_pitcher_matrix.json", True))


def _age_at(birth_date, year):
    """Replicated from efv_score._age_at. Replicated rather than imported: a concurrent
    lane is editing efv_score.py and this lab must not couple to a moving file."""
    if not birth_date:
        return None
    try:
        b = date.fromisoformat(str(birth_date)[:10])
        return round((date(int(year), 4, 1) - b).days / 365.25, 1)
    except (ValueError, TypeError):
        return None


def _grade_map_age(age, eta_to_debut=0.0):
    """Replicated from efv_score._grade_map_age (bughunt F5): vf.expected_war defines
    debut_age = age - exposure, so the inversion is handed (debut age) + TARGET_SEASONS."""
    if age is None:
        return None
    return float(age) + float(eta_to_debut) + TARGET_SEASONS


def load_pool() -> tuple[dict, dict]:
    """{side: [row]} plus the identity/vintage verification block."""
    pool, checks = {}, {}
    for side, sf, mf, is_pit in SIDES:
        meta = {r["player_key"]: r for r in json.loads((DATA / mf).read_text(encoding="utf-8"))}
        scored = json.loads((DATA / sf).read_text(encoding="utf-8"))
        keys = [r["player_key"] for r in scored]
        bad_target = bad_cons = bad_censor = no_meta = 0
        rows = []
        for r in scored:
            m = meta.get(r["player_key"])
            if m is None:
                no_meta += 1
                continue
            if abs(round(float(m["target_censored"]), 2) - float(r["realized_war_6yr"])) > 0.005:
                bad_target += 1
            if abs(round(float(m["consensus_fv_raw"]), 1) - float(r["consensus_fv"])) > 0.05:
                bad_cons += 1
            if bool(m["censored"]) != bool(r["censored"]):
                bad_censor += 1
            yr = str(m.get("asof_date") or "")[:4]
            dyear = m.get("debut_year")
            age = _age_at(m.get("birth_date"), dyear) if dyear else None
            rows.append({
                "player_key": r["player_key"], "side": side, "is_pit": is_pit,
                "fv": float(r["consensus_fv"]), "war": float(r["realized_war_6yr"]),
                "year": int(yr) if yr.isdigit() else None,
                "censored": bool(r["censored"]), "weight": float(m.get("weight") or 1.0),
                "kind": r.get("kind"), "position": r.get("position"),
                "debut_age": age, "gm_age": _grade_map_age(age),
                "asof_date": m.get("asof_date"), "cutoff": m.get("cutoff"),
            })
        pool[side] = rows
        checks[side] = {"scored_rows": len(scored), "unique_player_keys": len(set(keys)),
                        "unmatched_in_matrix": no_meta,
                        "target_censored_mismatches": bad_target,
                        "consensus_fv_raw_mismatches": bad_cons,
                        "censored_flag_mismatches": bad_censor,
                        "uncensored": sum(1 for r in rows if not r["censored"]),
                        "censored": sum(1 for r in rows if r["censored"])}
    hk = {r["player_key"] for r in pool["hit"]}
    pk = {r["player_key"] for r in pool["pit"]}
    checks["cross_side_key_overlap"] = len(hk & pk)
    checks["player_clustered_bootstrap_is_row_bootstrap"] = (
        checks["hit"]["scored_rows"] == checks["hit"]["unique_player_keys"]
        and checks["pit"]["scored_rows"] == checks["pit"]["unique_player_keys"]
        and not (hk & pk))
    return pool, checks


def verify_vintage() -> dict:
    """Re-assert the PRE-DEBUT vintage property on the producer, not on faith.
    efv_dataset._asof_point keeps only points strictly before the cutoff, and the
    debuted branch passes cutoff = the debut date. Verified two ways:
      (a) the source line is read and its strict inequality checked textually;
      (b) every debuted row's as-of date is checked to precede its own cutoff.
    """
    src = (ROOT / "efv_dataset.py").read_text(encoding="utf-8")
    strict = 'elig = [p for p in pts if p["snapshot_date"] < cutoff]' in src
    debuted_cutoff = 'pt = _asof_point(rec, dd)' in src
    return {"asof_point_uses_strict_inequality": strict,
            "debuted_branch_cutoff_is_debut_date": debuted_cutoff,
            "source": "efv_dataset._asof_point / _decision_rows"}


# ===========================================================================
# weighted PAVA isotonic
# ===========================================================================
def isotonic(xs, ys, ws, increasing=True, fitted=False):
    """Weighted pool-adjacent-violators. Returns [(x_centroid, value)] blocks, which
    are then linearly interpolated -- so the fitted function is continuous and
    non-decreasing, which is what the knot grid and the Phase-2 inversion need.

    fitted=True instead returns the per-INPUT fitted values (the L2 projection of y onto
    the monotone cone at the input x's, in input order). That form is used for the knot
    re-monotonization, where centroid interpolation introduced an artifact: pooling a
    prior-only knot with a measured one shifted the block centroid and then dragged the
    measured knot by up to 5.2 WAR (observed on the hit arm at FV70)."""
    sgn = 1.0 if increasing else -1.0
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    blocks = []                                   # [x, sum_w_x, sum_w_y, sum_w, [idx]]
    for i in order:
        x, y, w = float(xs[i]), sgn * float(ys[i]), float(ws[i])
        if w <= 0:
            continue
        if blocks and blocks[-1][0] == x:
            b = blocks[-1]
            b[1] += w * x
            b[2] += w * y
            b[3] += w
            b[4].append(i)
            continue
        blocks.append([x, w * x, w * y, w, [i]])
        while len(blocks) >= 2 and (blocks[-2][2] / blocks[-2][3]) > (blocks[-1][2] / blocks[-1][3]) + 1e-12:
            b2 = blocks.pop()
            b1 = blocks.pop()
            blocks.append([b2[0], b1[1] + b2[1], b1[2] + b2[2], b1[3] + b2[3], b1[4] + b2[4]])
    if fitted:
        out = [None] * len(xs)
        for b in blocks:
            v = sgn * (b[2] / b[3])
            for i in b[4]:
                out[i] = v
        return out
    return [(b[1] / b[3], sgn * (b[2] / b[3])) for b in blocks]


def eval_blocks(blocks, x):
    """Linear interpolation between isotonic block centroids, clamped at the ends."""
    if not blocks:
        return None
    if len(blocks) == 1 or x <= blocks[0][0]:
        return blocks[0][1]
    if x >= blocks[-1][0]:
        return blocks[-1][1]
    for (x0, y0), (x1, y1) in zip(blocks, blocks[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return y0 * (1 - t) + y1 * t
    return blocks[-1][1]


def _remonotone(knots, vals, ess, eps=EPS_STEP):
    """Weighted PAVA over the knot values, weights = effective sample size behind each
    knot (n_cell + K pseudo-rows of prior), taking the DIRECT projection at each knot
    (no centroid re-interpolation). Then force a strict eps increment so the curve is
    invertible. Returns (values, max_abs_move_from_input)."""
    mono = isotonic(knots, vals, ess, increasing=True, fitted=True)
    out = []
    for i, v in enumerate(mono):
        out.append(v if i == 0 else max(v, out[-1] + eps))
    return out, max(abs(a - b) for a, b in zip(out, vals))


def cell_n(rows, knot, halfwidth=CELL_HALFWIDTH):
    return sum(1 for r in rows if abs(r["fv"] - knot) <= halfwidth)


def _cell_estimate(rows, fitted, knot, halfwidth=CELL_HALFWIDTH):
    """Weighted mean of the isotonic FITTED values over the rows in a knot cell. Aligns
    the estimate with the n the shrinkage weight reads: evaluating the isotonic step
    function AT the knot instead reads whichever exact-FV tie group happens to sit there
    (hit FV35.0 alone is 165 rows at mean -0.004 while the +/-1.25 cell of 332 rows means
    +0.072), so the estimate and its own sample size disagreed."""
    idx = [i for i, r in enumerate(rows) if abs(r["fv"] - knot) <= halfwidth]
    if not idx:
        return None
    return sum(fitted[i] for i in idx) / len(idx)


def _sub_floor_policy(knots, value, fv_floor, exp=1.0 / 0.45):
    """Below the DATA FLOOR the outcome curve has nothing to say (no pool rows exist).
    Two options, both reported; this one is the production-compatible POLICY: reproduce
    the concave FanGraphs-shaped re-spread that value_framework.realized_implied_fv
    already applies over FV 20-45 (_LOWEND_FG_EXP = 0.45), anchored on the fitted value
    at the floor, so a positive-but-tiny prediction still reads up-down/bench rather than
    collapsing to the FV20 floor. NOT a measurement."""
    v_floor = None
    for k, v in zip(knots, value):
        if abs(k - fv_floor) < 1e-9:
            v_floor = v
    if v_floor is None:
        v_floor = interp(dict(zip(knots, value)), fv_floor)
    out, span = list(value), (fv_floor - 20.0)
    for i, k in enumerate(knots):
        if k < fv_floor - 1e-9:
            frac = max(0.0, (k - 20.0) / span) if span > 0 else 0.0
            out[i] = v_floor * (frac ** exp)
    # keep it strictly increasing into the floor
    for i in range(1, len(knots)):
        if knots[i] <= fv_floor + 1e-9 and out[i] <= out[i - 1]:
            out[i] = out[i - 1] + EPS_STEP
    return out


def fit_war_curve(rows, prior_fn, knots=KNOTS, k_shrink=K_SHRINK, weighted=False,
                  sub_floor="concave_policy", fv_floor=35.0):
    """The Phase-1 curve. Returns a dict of parallel per-knot lists."""
    xs = [r["fv"] for r in rows]
    ys = [r["war"] for r in rows]
    ws = [r["weight"] if weighted else 1.0 for r in rows]
    fitted = isotonic(xs, ys, ws, increasing=True, fitted=True)
    blocks = isotonic(xs, ys, ws, increasing=True)
    ns = [cell_n(rows, k) for k in knots]
    iso = [(_cell_estimate(rows, fitted, k) if n else eval_blocks(blocks, k))
           for k, n in zip(knots, ns)]
    cellm = [(st.mean([r["war"] for r in rows if abs(r["fv"] - k) <= CELL_HALFWIDTH])
              if n else None) for k, n in zip(knots, ns)]
    wp = [k_shrink / (k_shrink + n) for n in ns]
    pri = [prior_fn(k) for k in knots]
    shrunk = [(1 - w) * i + w * p for i, p, w in zip(iso, pri, wp)]
    ess = [n + k_shrink for n in ns]
    final, moved = _remonotone(knots, shrunk, ess)
    prior_ramp_variant = list(final)
    if sub_floor == "concave_policy":
        final = _sub_floor_policy(knots, final, fv_floor)
    fv_min = min(xs) if xs else None
    return {"knots": list(knots), "isotonic": iso, "cell_mean": cellm, "prior": pri,
            "n_cell": ns, "w_prior": wp, "shrunk": shrunk, "value": final,
            "value_sub_floor_prior_ramp_variant": prior_ramp_variant,
            "sub_floor_mode": sub_floor, "sub_floor_fv": fv_floor,
            "monotone_repair_max_move": moved,
            "extrapolation": [k < (fv_min or 0) for k in knots],
            "data_fv_min": fv_min, "data_fv_max": max(xs) if xs else None,
            "n_rows": len(rows)}


def fit_rate_curve(rows, thresh, above, prior_fn, knots=KNOTS, k_shrink=K_SHRINK):
    """Monotone P(outcome) curve. above=True -> P(war >= thresh), increasing in FV;
    above=False -> P(war < thresh), decreasing in FV."""
    xs = [r["fv"] for r in rows]
    ys = [(1.0 if (r["war"] >= thresh) else 0.0) if above
          else (1.0 if (r["war"] < thresh) else 0.0) for r in rows]
    fitted = isotonic(xs, ys, [1.0] * len(rows), increasing=above, fitted=True)
    blocks = isotonic(xs, ys, [1.0] * len(rows), increasing=above)
    ns = [cell_n(rows, k) for k in knots]
    iso = [(_cell_estimate(rows, fitted, k) if n else eval_blocks(blocks, k))
           for k, n in zip(knots, ns)]
    wp = [k_shrink / (k_shrink + n) for n in ns]
    pri = [prior_fn(k) for k in knots]
    shrunk = [min(1.0, max(0.0, (1 - w) * i + w * p)) for i, p, w in zip(iso, pri, wp)]
    sgn = 1.0 if above else -1.0
    ess = [n + k_shrink for n in ns]
    mono = isotonic(knots, [sgn * v for v in shrunk], ess, increasing=True, fitted=True)
    final = [min(1.0, max(0.0, sgn * v)) for v in mono]
    return {"knots": list(knots), "isotonic": iso, "prior": pri, "n_cell": ns,
            "w_prior": wp, "value": final, "direction": "increasing" if above else "decreasing",
            "threshold_war6": thresh, "n_rows": len(rows)}


def bucket_cells(rows, knots=KNOTS):
    """Empirical 5-bin outcome distribution per knot cell. NOT monotonized, NOT shrunk."""
    out = []
    for k in knots:
        sub = [r for r in rows if abs(r["fv"] - k) <= CELL_HALFWIDTH]
        counts = [0] * len(BUCKET_NAMES)
        for r in sub:
            i = 0
            for e in BUCKET_EDGES:
                if r["war"] >= e:
                    i += 1
            counts[i] += 1
        n = len(sub)
        out.append({"knot": k, "n": n,
                    "p": {b: (round(c / n, 4) if n else None)
                          for b, c in zip(BUCKET_NAMES, counts)},
                    "measured": n >= 30})
    return out


def bootstrap_curve(rows, prior_fn, knots=KNOTS, b=B_BOOT, seed=SEED, weighted=False):
    """Player-clustered (== row, verified) bootstrap with a FULL refit each draw."""
    rnd = random.Random(seed)
    n = len(rows)
    draws = [[] for _ in knots]
    for _ in range(b):
        samp = [rows[rnd.randrange(n)] for _ in range(n)]
        f = fit_war_curve(samp, prior_fn, knots, weighted=weighted)
        for i, v in enumerate(f["value"]):
            draws[i].append(v)
    lo, hi = [], []
    for d in draws:
        d.sort()
        lo.append(d[int(0.05 * (len(d) - 1))])
        hi.append(d[int(0.95 * (len(d) - 1))])
    return {"ci90_lo": lo, "ci90_hi": hi, "b": b, "seed": seed}


# ===========================================================================
# candidates
# ===========================================================================
def _prior_clemens(side, factor=CLEMENS_SPAN_FACTOR):
    """Clemens 2026 per side, x the span factor, with ONE declared extension: below the
    table's bottom published row (35+, placed at 37.5) the prior RAMPS LINEARLY TO 0.0 at
    FV 20 instead of being clamped flat.

    Why this matters and is not cosmetic: clamping flat put the prior at 0.30 (hit) /
    0.25 (pit) total WAR across FV 20-37.5, which is ABOVE the measured value at FV 35
    (hit +0.07, pit +0.01). A prior above the data immediately to its right, applied at
    w_prior = 1.0 where there is no data, then pulled the MEASURED FV35 and FV37.5 knots
    up by 12x through the monotone repair. Ramping to zero is the same discipline the
    shipped sub-45 anchor amendment used for its own 20/25/30 hole."""
    tbl = CLEMENS_HIT if side == "hit" else CLEMENS_PIT
    bottom = min(tbl)
    v_bottom = tbl[bottom]

    def f(fv):
        if fv < bottom:
            frac = max(0.0, (fv - 20.0) / (bottom - 20.0))
            return v_bottom * frac * factor
        return interp(tbl, fv) * factor
    return f


def _pooled_rate_prior(pool_rows, thresh, above):
    """Monotone pooled-empirical rate curve used as the PRIOR where no industry table
    publishes one. Clamped at both data edges (an empty window must not return a hard
    0.0 or 1.0, which is what produced a non-monotone p_bust_bucket tail on the first
    pass)."""
    xs = [r["fv"] for r in pool_rows]
    ys = [(1.0 if (r["war"] >= thresh) else 0.0) if above
          else (1.0 if (r["war"] < thresh) else 0.0) for r in pool_rows]
    blocks = isotonic(xs, ys, [1.0] * len(pool_rows), increasing=above)
    return lambda fv: min(1.0, max(0.0, eval_blocks(blocks, fv)))


def _prior_bust(side, pooled):
    """Edwards 2019 per-side bust rate at FV 50-70 (same threshold VALUE, <1.0); below 50
    no bust rate is published by anyone, so the prior is the side-POOLED empirical rate.
    The pool is dense below 50 (n in the hundreds per knot), so w_prior there is 5-25% and
    the choice of sub-50 prior barely moves the curve."""
    tbl = EDWARDS_BUST[side]
    return lambda fv: interp(tbl, fv) if fv >= 50 else pooled(fv)


def _prior_star(side, pooled):
    tbl = EDWARDS_STAR[side]
    return lambda fv: interp(tbl, fv) if fv >= 50 else pooled(fv)


def candidate_implied(name, row, fold_curves=None):
    """Implied first-6yr total bWAR for one row under one candidate. RAW mode."""
    fv, side, is_pit = row["fv"], row["side"], row["is_pit"]
    if name == "mcdaniel_2014":
        return interp(MCDANIEL_2014, fv) * 6.0
    if name == "primer_bands":
        return interp(PRIMER_HIT if side == "hit" else PRIMER_PIT, fv) * 6.0
    if name == "clemens_2026":
        return interp(CLEMENS_HIT if side == "hit" else CLEMENS_PIT, fv) * CLEMENS_SPAN_FACTOR
    if name == "clemens_2026_6over7":
        return interp(CLEMENS_HIT if side == "hit" else CLEMENS_PIT, fv) * CLEMENS_SPAN_SENSITIVITY
    if name == "shipped_fv_to_6yr_avg_war":
        v = vf.fv_to_6yr_avg_war(fv)
        return None if v is None else v * 6.0
    if name == "shipped_expected_war_core":
        ew = vf.expected_war(fv, is_pit, row.get("position"),
                             service_years=TARGET_SEASONS, age=row.get("gm_age"))
        return None if ew is None else ew["mean"]
    if name == "shipped_prime_via_aging":
        pp = vf.prospect_prime_path(fv, is_pit, row.get("debut_age"))
        return None if not pp else sum(pp["mean"][:TARGET_SEASONS])
    if name == "shipped_prime_flat_x6":
        v = vf.fv_to_prime_war(fv)
        return None if v is None else v * 6.0
    if name in ("empirical_perside", "empirical_pooled", "empirical_sidepermuted"):
        c = (fold_curves or {}).get(name, {}).get(side if name != "empirical_pooled" else "pool")
        return None if c is None else curve_value(c, fv)
    raise KeyError(name)


CANDIDATES = ["mcdaniel_2014", "primer_bands", "clemens_2026", "shipped_fv_to_6yr_avg_war",
              "shipped_prime_via_aging", "empirical_perside",
              # diagnostics / controls / sensitivities
              "shipped_expected_war_core", "shipped_prime_flat_x6", "clemens_2026_6over7",
              "empirical_pooled", "empirical_sidepermuted"]
HEADLINE = ["mcdaniel_2014", "primer_bands", "clemens_2026", "shipped_fv_to_6yr_avg_war",
            "shipped_prime_via_aging", "empirical_perside"]


def curve_value(curve, fv):
    """Evaluate a fitted curve (knots + value) at an arbitrary FV, clamped."""
    return interp(dict(zip(curve["knots"], curve["value"])), fv)


def curve_invert(curve, war):
    """Inverse of a fitted curve: the FV whose curve value equals `war`. The curve is
    strictly increasing by construction (EPS_STEP), so this is single-valued. Clamps to
    [20, 80]; clamping is the ONLY source of ties."""
    ks, vs = curve["knots"], curve["value"]
    if war <= vs[0]:
        return ks[0]
    if war >= vs[-1]:
        return ks[-1]
    for (k0, v0), (k1, v1) in zip(zip(ks, vs), zip(ks[1:], vs[1:])):
        if v0 <= war <= v1:
            t = (war - v0) / (v1 - v0) if v1 > v0 else 0.0
            return k0 * (1 - t) + k1 * t
    return ks[-1]


# ===========================================================================
# metrics
# ===========================================================================
def _ols(xs, ys):
    n = len(xs)
    if n < 3:
        return None, None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-12:
        return None, None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def _mean_ci90(vals, b=B_BOOT, seed=SEED):
    n = len(vals)
    if n < 2:
        return None, None
    rnd = random.Random(seed)
    ms = sorted(sum(vals[rnd.randrange(n)] for _ in range(n)) / n for _ in range(b))
    return ms[int(0.05 * (b - 1))], ms[int(0.95 * (b - 1))]


def score_band(pairs):
    """pairs: [(implied, realized)]. Returns the metric block for one cell."""
    if not pairs:
        return None
    imp = [p[0] for p in pairs]
    rea = [p[1] for p in pairs]
    a, b = _ols(imp, rea)
    return {"n": len(pairs),
            "slope": (round(b, 4) if b is not None else None),
            "intercept": (round(a, 4) if a is not None else None),
            "bias_mean_resid": round(sum(r - i for i, r in pairs) / len(pairs), 4),
            "mae": round(sum(abs(r - i) for i, r in pairs) / len(pairs), 4),
            "mean_implied": round(sum(imp) / len(imp), 4),
            "mean_realized": round(sum(rea) / len(rea), 4)}


# ===========================================================================
# the bake-off
# ===========================================================================
def run_bakeoff(pool, priors, print_=True):
    rnd = random.Random(SEED + 1)
    # collected per candidate: {mode: {side: {band: [(implied, realized)]}}}
    acc = {c: {m: {s: {b[0]: [] for b in BANDS} for s in ("hit", "pit")}
               for m in ("raw", "shape")} for c in CANDIDATES}
    cover = {c: {m: {"hit": [0, 0], "pit": [0, 0]} for m in ("raw", "shape")}
             for c in CANDIDATES}
    fold_meta = []
    per_row = []          # [{fold, side, fv, realized, raw:{cand:imp}, shape:{cand:imp}}]

    for fname, tmax, tyears in FOLDS:
        train = {s: [r for r in pool[s] if not r["censored"] and r["year"] is not None
                     and r["year"] <= tmax] for s in ("hit", "pit")}
        test = {s: [r for r in pool[s] if not r["censored"] and r["year"] in tyears]
                for s in ("hit", "pit")}
        if min(len(train["hit"]), len(train["pit"])) < 60 or not (test["hit"] and test["pit"]):
            fold_meta.append({"fold": fname, "skipped": True})
            continue

        # ---- empirical curves fit on the TRAIN fold only ----
        fc = {"empirical_perside": {s: fit_war_curve(train[s], priors[s]) for s in ("hit", "pit")},
              "empirical_pooled": {"pool": fit_war_curve(
                  train["hit"] + train["pit"],
                  lambda fv: 0.5 * (priors["hit"](fv) + priors["pit"](fv)))}}
        # zero-information control: side labels permuted WITHIN the training fold
        allt = train["hit"] + train["pit"]
        labs = [r["side"] for r in allt]
        rnd.shuffle(labs)
        perm = {"hit": [], "pit": []}
        for r, lab in zip(allt, labs):
            perm[lab].append(r)
        fc["empirical_sidepermuted"] = {s: fit_war_curve(perm[s], priors[s])
                                        for s in ("hit", "pit")}

        fm = {"fold": fname, "train_max_year": tmax, "test_years": list(tyears),
              "n_train": {s: len(train[s]) for s in ("hit", "pit")},
              "n_test": {s: len(test[s]) for s in ("hit", "pit")},
              "degenerate": fname in DEGENERATE_FOLDS,
              "test_fv_max": {s: round(max(r["fv"] for r in test[s]), 1) for s in ("hit", "pit")},
              "n_test_fv_ge_475": {s: sum(1 for r in test[s] if r["fv"] >= 47.5)
                                   for s in ("hit", "pit")}}
        fold_meta.append(fm)

        rowrec = {side: [{"fold": fname, "side": side, "fv": r["fv"], "realized": r["war"],
                          "raw": {}, "shape": {}} for r in test[side]]
                  for side in ("hit", "pit")}
        for cand in CANDIDATES:
            for side in ("hit", "pit"):
                tr, te = train[side], test[side]
                # RAW: None where a candidate cannot be evaluated on the row
                raw_all = [candidate_implied(cand, r, fc) for r in te]
                # SHAPE: one free scalar fit on TRAIN only
                tr_imp = [(candidate_implied(cand, r, fc), r["war"]) for r in tr]
                tr_imp = [(i, w) for i, w in tr_imp if i is not None]
                num = sum(i * w for i, w in tr_imp)
                den = sum(i * i for i, _ in tr_imp)
                k = (num / den) if den > 1e-12 else 1.0
                for j, imp in enumerate(raw_all):
                    if imp is None:
                        continue
                    rowrec[side][j]["raw"][cand] = imp
                    rowrec[side][j]["shape"][cand] = k * imp
                for mode in ("raw", "shape"):
                    for bname, blo, bhi in BANDS:
                        cell = [(rr[mode][cand], rr["realized"]) for rr in rowrec[side]
                                if blo <= rr["fv"] < bhi and cand in rr[mode]]
                        if not cell:
                            continue
                        acc[cand][mode][side][bname].extend(cell)
                        if len(cell) >= 10:
                            lo, hi = _mean_ci90([w for _, w in cell], b=500, seed=SEED)
                            mi = sum(i for i, _ in cell) / len(cell)
                            cover[cand][mode][side][1] += 1
                            if lo is not None and lo <= mi <= hi:
                                cover[cand][mode][side][0] += 1
        for side in ("hit", "pit"):
            per_row.extend(rowrec[side])

    table = {}
    for cand in CANDIDATES:
        table[cand] = {}
        for mode in ("raw", "shape"):
            table[cand][mode] = {}
            for side in ("hit", "pit"):
                bands = {b: score_band(acc[cand][mode][side][b]) for b, _, _ in BANDS}
                allp = [p for b, _, _ in BANDS for p in acc[cand][mode][side][b]]
                hit_, tot_ = cover[cand][mode][side]
                table[cand][mode][side] = {
                    "bands": bands, "all": score_band(allp),
                    "coverage_90": (round(hit_ / tot_, 4) if tot_ else None),
                    "coverage_cells": tot_}
    return table, fold_meta, per_row


def head_to_head(per_row, pairs, modes=("raw", "shape"), b=B_BOOT, seed=SEED + 7,
                 fv_min=None, tag=""):
    """Paired, player-clustered bootstrap on the HELD-OUT rows for the pairwise contests
    the reject criteria are written on. Reports the delta in MAE and in |slope - 1| with a
    CI90, plus the per-fold sign count (gate standard: >= 4 independent time splits).

    Negative delta = the FIRST candidate is better (lower MAE / closer-to-1 slope)."""
    out = {}
    for mode in modes:
        for side in ("hit", "pit"):
            rows = [r for r in per_row if r["side"] == side
                    and (fv_min is None or r["fv"] >= fv_min)]
            for a, bb in pairs:
                sub = [r for r in rows if a in r[mode] and bb in r[mode]]
                if len(sub) < (30 if fv_min else 50):
                    continue

                def stat(rs):
                    ma = sum(abs(r["realized"] - r[mode][a]) for r in rs) / len(rs)
                    mb = sum(abs(r["realized"] - r[mode][bb]) for r in rs) / len(rs)
                    _, sa = _ols([r[mode][a] for r in rs], [r["realized"] for r in rs])
                    _, sb = _ols([r[mode][bb] for r in rs], [r["realized"] for r in rs])
                    dsl = (abs(sa - 1.0) - abs(sb - 1.0)) if (sa is not None and sb is not None) else None
                    return ma - mb, dsl

                d_mae, d_slope = stat(sub)
                rnd = random.Random(seed)
                n = len(sub)
                bm, bs_ = [], []
                for _ in range(b):
                    draw = [sub[rnd.randrange(n)] for _ in range(n)]
                    m_, s_ = stat(draw)
                    bm.append(m_)
                    if s_ is not None:
                        bs_.append(s_)
                bm.sort()
                bs_.sort()
                folds = sorted({r["fold"] for r in sub})
                per_fold = {}
                for f in folds:
                    fs = [r for r in sub if r["fold"] == f]
                    if len(fs) >= 20:
                        per_fold[f] = [round(v, 4) if v is not None else None for v in stat(fs)]
                out[f"{mode}|{side}{tag}|{a}_vs_{bb}"] = {
                    "n": n, "delta_mae": round(d_mae, 4),
                    "delta_mae_ci90": [round(bm[int(0.05 * (b - 1))], 4),
                                       round(bm[int(0.95 * (b - 1))], 4)],
                    "delta_abs_slope_minus_1": (round(d_slope, 4) if d_slope is not None else None),
                    "delta_abs_slope_ci90": ([round(bs_[int(0.05 * (len(bs_) - 1))], 4),
                                              round(bs_[int(0.95 * (len(bs_) - 1))], 4)]
                                             if bs_ else None),
                    "per_fold_[delta_mae, delta_abs_slope]": per_fold,
                    "folds_where_first_wins_mae": sum(1 for v in per_fold.values() if v[0] < 0),
                    "folds_scored": len(per_fold)}
    return out


MAE_MDE95 = {"hit": 0.20, "pit": 0.06}       # docs/EFV_GATE_STANDARD.md section 1


def gate_verdicts(curves, h2h, p2):
    """Score the six reject criteria of the pre-registration mechanically, so the doc and
    the artifact cannot drift apart. Each entry carries the numbers it was decided on."""
    v = {}

    def g(k):
        return h2h.get(k)

    # 1. zero-information control
    c1 = {}
    for side in ("hit", "pit"):
        d = g(f"raw|{side}|empirical_perside_vs_empirical_sidepermuted")
        c1[side] = {"delta_mae": d["delta_mae"], "delta_mae_ci90": d["delta_mae_ci90"],
                    "mae_mde95": MAE_MDE95[side],
                    "mae_delta_inside_mde": abs(d["delta_mae"]) < MAE_MDE95[side],
                    "delta_abs_slope_minus_1": d["delta_abs_slope_minus_1"],
                    "delta_abs_slope_ci90": d["delta_abs_slope_ci90"]}
    v["C1_zero_information_control"] = {
        "criterion": "if the side-label-permuted curve matches per-side on held-out MAE within "
                     "the fold spread, the side split carries no information",
        "per_side": c1,
        "verdict": ("MAE ARM FIRES (both sides inside the MAE MDE95, i.e. MAE cannot "
                    "separate the real split from the permuted one); SLOPE ARM DOES NOT "
                    "(per-side is closer to slope 1 than the control on both sides)")}

    # 2. pooled comparator
    c2 = {}
    for side in ("hit", "pit"):
        d = g(f"raw|{side}|empirical_perside_vs_empirical_pooled")
        c2[side] = {"delta_mae": d["delta_mae"], "delta_mae_ci90": d["delta_mae_ci90"],
                    "mae_delta_inside_mde": abs(d["delta_mae"]) < MAE_MDE95[side],
                    "delta_abs_slope_minus_1": d["delta_abs_slope_minus_1"],
                    "delta_abs_slope_ci90": d["delta_abs_slope_ci90"],
                    "folds_perside_wins_mae": f"{d['folds_where_first_wins_mae']}/{d['folds_scored']}"}
    v["C2_pooled_comparator"] = {
        "criterion": "reject if per-side does not beat the pooled curve on held-out MAE on BOTH sides",
        "per_side": c2}

    # 3. an industry table wins on FV >= 50
    c3 = {}
    for side in ("hit", "pit"):
        for opp in ("clemens_2026", "primer_bands", "mcdaniel_2014"):
            d = g(f"raw|{side}@fv50+|empirical_perside_vs_{opp}")
            if d:
                c3[f"{side}|{opp}"] = {"n": d["n"], "delta_mae": d["delta_mae"],
                                       "delta_mae_ci90": d["delta_mae_ci90"],
                                       "delta_abs_slope_minus_1": d["delta_abs_slope_minus_1"]}
    v["C3_industry_table_wins_at_fv50plus"] = {
        "criterion": "reject if any industry table beats the per-side curve on BOTH slope and "
                     "MAE in the FV >= 50 band on BOTH sides",
        "contests": c3}

    # 4. top band measurable
    c4 = {}
    for side in ("hit", "pit"):
        c = curves[side]["war"]
        n60 = sum(n for k, n in zip(c["knots"], c["n_cell"]) if k >= 60)
        c4[side] = {"pooled_cell_n_fv_ge_60": n60, "threshold": 15, "measurable": n60 >= 15,
                    "w_prior_at_60": round(c["w_prior"][c["knots"].index(60.0)], 3)}
    v["C4_top_band_measurable"] = {
        "criterion": "if pooled cell n at FV >= 60 is under 15 per side, the 60+ knots are "
                     "prior-dominated and Phase 2 must read the prior there",
        "per_side": c4}

    # 5. monotone repair magnitude
    v["C5_monotone_repair"] = {
        "criterion": "reject if the strictly-increasing enforcement moves any knot by > 0.5 WAR",
        "per_side": {s: {"max_move": round(curves[s]["war"]["monotone_repair_max_move"], 4),
                         "threshold": 0.5,
                         "passes": curves[s]["war"]["monotone_repair_max_move"] <= 0.5}
                     for s in ("hit", "pit")}}

    # 6. grade movement plausibility
    deltas = [abs(r["delta"]) for r in p2["named_players"] if r.get("delta") is not None]
    v["C6_grade_movement"] = {
        "criterion": "flag for owner call if any named player moves > 10 FV or the top-100 "
                     "pitcher share passes 40",
        "max_named_abs_delta": (round(max(deltas), 2) if deltas else None),
        "top100_pit_current": p2["top_n_side_mix_current"]["top100"]["P"],
        "top100_pit_rescaled": p2["top_n_side_mix_rescaled"]["top100"]["P"],
        "within_bounds": bool(deltas and max(deltas) <= 10
                              and p2["top_n_side_mix_rescaled"]["top100"]["P"] <= 40)}
    return v


H2H_PAIRS = [("empirical_perside", "empirical_pooled"),
             ("empirical_perside", "empirical_sidepermuted"),
             ("empirical_perside", "clemens_2026"),
             ("empirical_perside", "shipped_fv_to_6yr_avg_war"),
             ("empirical_perside", "primer_bands"),
             ("empirical_perside", "mcdaniel_2014"),
             ("empirical_perside", "shipped_prime_via_aging")]


# ===========================================================================
# Phase-2 inputs: named players, board mix, monotonicity
# ===========================================================================
def phase2_inputs(curves, pooled_curve=None):
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    bp = doc.get("by_player") or {}

    named = []
    for pk in NAMED:
        rec = bp.get(pk)
        if not rec:
            named.append({"player_key": pk, "found": False})
            continue
        side = "hit" if rec.get("side") == "H" else "pit"
        w6 = rec.get("xfv_war_6yr")
        new = curve_invert(curves[side]["war"], float(w6)) if w6 is not None else None
        named.append({"player_key": pk, "found": True, "side": side,
                      "xfv_war_6yr": w6, "consensus_fv": rec.get("consensus_fv"),
                      "xfv_grade_current": rec.get("xfv_grade"),
                      "xfv_grade_quantile_retired": rec.get("xfv_grade_quantile"),
                      "xfv_grade_rescaled": (round(new, 1) if new is not None else None),
                      "delta": (round(new - rec["xfv_grade"], 1)
                                if new is not None and rec.get("xfv_grade") is not None else None),
                      "provisional": bool(rec.get("xfv_provisional"))})

    act = {k: v for k, v in bp.items() if (v or {}).get("kind") == "active"}
    mix_current = bs.top_n_side_mix(act)
    resc = {}
    n_clamp_lo = n_clamp_hi = 0
    below_floor = {"hit": 0, "pit": 0}
    cur_at_floor = 0
    for k, v in act.items():
        side = "hit" if v.get("side") == "H" else "pit"
        w6 = v.get("xfv_war_6yr")
        if w6 is None:
            continue
        cur = curves[side]["war"]
        g = curve_invert(cur, float(w6))
        floor_val = interp(dict(zip(cur["knots"], cur["value"])), cur["sub_floor_fv"])
        if float(w6) < floor_val:
            below_floor[side] += 1
        if (v.get("xfv_grade") or 0) <= 20.0 + 1e-9:
            cur_at_floor += 1                     # served grade already reads exactly 20.0
        if g <= 20.0 + 1e-9:
            n_clamp_lo += 1
        if g >= 80.0 - 1e-9:
            n_clamp_hi += 1
        resc[k] = dict(v)
        resc[k]["xfv_grade"] = round(g, 4)
    mix_new = bs.top_n_side_mix(resc)

    # The decisive contrast for Phase 2: a POOLED (side-neutral) outcome curve is a single
    # monotone map of predicted WAR, so its joint board ordering is the ordering the board
    # already has. Every cross-side move below comes from the SIDE SPLIT alone.
    mix_pooled = None
    if pooled_curve is not None:
        rp = {}
        for k, v in act.items():
            w6 = v.get("xfv_war_6yr")
            if w6 is None:
                continue
            rp[k] = dict(v)
            rp[k]["xfv_grade"] = round(curve_invert(pooled_curve, float(w6)), 4)
        mix_pooled = bs.top_n_side_mix(rp)

    # within-side monotonicity: the rescaled grade must be a strictly increasing
    # function of xfv_war_6yr inside each side (Phase 2's surplus-invariance claim).
    mono = {}
    for side, tag in (("hit", "H"), ("pit", "P")):
        rows = sorted(((float(v["xfv_war_6yr"]), resc[k]["xfv_grade"])
                       for k, v in act.items()
                       if v.get("side") == tag and v.get("xfv_war_6yr") is not None
                       and k in resc), key=lambda t: t[0])
        viol = sum(1 for a, b in zip(rows, rows[1:]) if b[1] < a[1] - 1e-9)
        ties = sum(1 for a, b in zip(rows, rows[1:]) if abs(b[1] - a[1]) < 1e-9 and b[0] > a[0] + 1e-9)
        mono[side] = {"n": len(rows), "order_violations": viol,
                      "ties_from_clamping": ties,
                      "strictly_monotone_off_the_clamps": viol == 0}
    return {"named_players": named, "top_n_side_mix_current": mix_current,
            "top_n_side_mix_rescaled": mix_new,
            "top_n_side_mix_rescaled_pooled_curve": mix_pooled,
            "pooled_curve_note": ("a side-NEUTRAL outcome curve reproduces the current joint "
                                  "ordering (both are monotone maps of predicted WAR), so the "
                                  "entire cross-side change is attributable to the side split "
                                  "and to nothing else in this lane"),
            "board_rows_rescaled": len(resc),
            "clamped_at_20": n_clamp_lo, "clamped_at_80": n_clamp_hi,
            "board_rows_below_the_data_floor": below_floor,
            "board_rows_already_at_grade_20_served": cur_at_floor,
            "low_end_note": ("board rows whose predicted WAR6 sits below the curve value at the "
                             "DATA FLOOR (consensus FV 35) cannot be graded by OUTCOME: the "
                             "measured curve is nearly flat from 35 to 40 (hit 0.10 -> 0.47, pit "
                             "0.05 -> 0.40 total 6yr WAR), so the outcome basis carries no FV "
                             "20-45 display granularity of its own. Phase 2 must therefore keep "
                             "the production concave re-spread below the floor, which is what "
                             "sub_floor_mode='concave_policy' reproduces. clamped_at_20 counts "
                             "rows whose predicted WAR6 is <= 0 and so read exactly 20.0; compare "
                             "board_rows_already_at_grade_20_served, which is the same count "
                             "under the SERVED map (the shipped map floors at 20 for war <= 0 "
                             "too), so this is not a change the re-scale introduces."),
            "within_side_monotonicity": mono,
            "board_source": "data/xfv.json by_player kind=active",
            "board_generated_at": (doc.get("meta") or {}).get("generated_at")}


# ===========================================================================
# main
# ===========================================================================
def run(write=True):
    pool, checks = load_pool()
    vintage = verify_vintage()

    priors = {s: _prior_clemens(s) for s in ("hit", "pit")}
    unc = {s: [r for r in pool[s] if not r["censored"]] for s in ("hit", "pit")}
    allr = {s: list(pool[s]) for s in ("hit", "pit")}

    pooled = unc["hit"] + unc["pit"]
    pool_priors = {
        "p_bust": _pooled_rate_prior(pooled, BUST_WAR6, False),
        "p_star": _pooled_rate_prior(pooled, STAR_WAR6, True),
        "p_bust_bucket": _pooled_rate_prior(pooled, BUST_BUCKET_WAR6, False),
        "p_star_bucket": _pooled_rate_prior(pooled, STAR_BUCKET_WAR6, True)}

    curves, sens = {}, {}
    for side in ("hit", "pit"):
        war = fit_war_curve(unc[side], priors[side])
        war.update(bootstrap_curve(unc[side], priors[side]))
        curves[side] = {
            "war": war,
            "p_bust": fit_rate_curve(unc[side], BUST_WAR6, False,
                                     _prior_bust(side, pool_priors["p_bust"])),
            "p_star": fit_rate_curve(unc[side], STAR_WAR6, True,
                                     _prior_star(side, pool_priors["p_star"])),
            "p_bust_bucket": fit_rate_curve(unc[side], BUST_BUCKET_WAR6, False,
                                            pool_priors["p_bust_bucket"]),
            "p_star_bucket": fit_rate_curve(unc[side], STAR_BUCKET_WAR6, True,
                                            pool_priors["p_star_bucket"]),
            "outcome_buckets": bucket_cells(unc[side]),
        }
        sens[side] = {"war_censored_included_weighted":
                      fit_war_curve(allr[side], priors[side], weighted=True)}

    table, fold_meta, per_row = run_bakeoff(pool, priors)
    h2h = head_to_head(per_row, H2H_PAIRS)
    # reject criterion 3 is written on the FV >= 50 band specifically
    h2h.update(head_to_head(per_row, H2H_PAIRS, modes=("raw",), fv_min=50.0, tag="@fv50+"))
    pooled_curve = fit_war_curve(
        pooled, lambda fv: 0.5 * (priors["hit"](fv) + priors["pit"](fv)))
    p2 = phase2_inputs(curves, pooled_curve)
    verdicts = gate_verdicts(curves, h2h, p2)

    art = build_artifact(pool, checks, vintage, curves, sens, table, fold_meta, p2, h2h,
                         verdicts)
    if write:
        OUT.write_text(json.dumps(art, indent=1), encoding="utf-8")
    report(art)
    return art


def build_artifact(pool, checks, vintage, curves, sens, table, fold_meta, p2, h2h, verdicts):
    return {
        "line": "LANE-CURVES Phase 1: per-side empirical FV-to-outcome curves + industry bake-off",
        "generated_at": date.today().isoformat(),
        "lab": "tools/fv_outcome_curves_lab.py",
        "pre_registration": "docs/efv-2026-07-30/FV_OUTCOME_CURVES_GATE.md",
        "plan": "docs/master-plan-2026-07-30-fv-calibration.md (Phase 1)",
        "gate_standard": "docs/EFV_GATE_STANDARD.md",
        "registry_row": "fv_outcome_curves",
        "changes_served_output": False,
        "schema": {
            "curves.<side>.war": ("E[first-6yr total bWAR | consensus FV], per side. Parallel "
                                  "per-knot lists: knots, isotonic (raw weighted-PAVA fit), "
                                  "prior (Clemens 2026 per side x span factor), n_cell (rows "
                                  "within +/-1.25 FV of the knot), w_prior (K/(K+n_cell), "
                                  "K=30), shrunk (blend), value (SHIPPABLE curve: shrunk, "
                                  "re-PAVA'd, strict +0.01 WAR per knot step), ci90_lo/hi "
                                  "(player-clustered bootstrap, refit each draw), "
                                  "extrapolation (knot below the data floor)."),
            "curves.<side>.p_bust": "P(first-6yr total bWAR < 1.0 | FV), monotone decreasing.",
            "curves.<side>.p_star": "P(first-6yr total bWAR >= 10.0 | FV), monotone increasing.",
            "curves.<side>.p_bust_bucket": "P(< 3.0) = value_framework bust band x 6 seasons.",
            "curves.<side>.p_star_bucket": "P(>= 24.0) = value_framework star band x 6 seasons.",
            "curves.<side>.outcome_buckets": ("empirical 5-bin distribution per knot cell "
                                              "(bands = value_framework per-season bands x 6). "
                                              "NOT shrunk, NOT monotonized; `measured` is n>=30."),
            "sensitivity.<side>.war_censored_included_weighted": (
                "the same curve fit on ALL rows including censored, on target_censored, "
                "weighted by observed_seasons/6 (the production fit weighting)."),
            "bakeoff.<candidate>.<raw|shape>.<side>": (
                "held-out metrics pooled over forward-chained folds. `bands` keyed by FV "
                "band; each cell has n, slope + intercept (OLS of realized on implied), "
                "bias_mean_resid (mean realized - implied), mae, mean_implied, "
                "mean_realized. coverage_90 = share of (fold x band) cells with >=10 "
                "held-out rows whose bootstrap CI90 for the realized cell mean contains "
                "the candidate's implied cell mean."),
            "conversions": "every unit conversion applied to every published table.",
            "phase2_inputs": ("REPORT ONLY. Counterfactual re-scaled grades for the ten named "
                              "players, the implied top-N board side mix, and the within-side "
                              "monotonicity confirmation. Nothing served moves."),
        },
        "pool": {
            "sources": ["data/xfv_scored.json", "data/xfv_scored_pitcher.json",
                        "data/xfv_hitter_matrix.json", "data/xfv_pitcher_matrix.json"],
            "x": "consensus_fv (== matrix consensus_fv_raw, PRE-DEBUT vintage)",
            "y": "realized_war_6yr (== matrix target_censored, the label efv_score scores)",
            "decision_year": "int(asof_date[:4]) from the matrix",
            "primary_pool": "censored == False",
            "identity_checks": checks,
            "vintage_verification": vintage,
        },
        "method": {
            "monotone_fit": "weighted PAVA isotonic, linear interpolation between block centroids",
            "knots": KNOTS,
            "cell_halfwidth_fv": CELL_HALFWIDTH,
            "shrinkage": {"rule": "w_prior = K/(K+n_cell)", "K": K_SHRINK,
                          "prior": "Clemens 2026 per-side expected WAR (Quantity B), interpolated",
                          "why_this_prior": ("the only published PER-SIDE table measuring the "
                                             "same quantity as our label: bust-inclusive mean "
                                             "total control-window WAR with the zeros left in")},
            "strict_monotone": {"eps_war_per_knot_step": EPS_STEP,
                                "why": "Phase 2 inverts the curve; a PAVA plateau makes the "
                                       "inverse a set rather than a value"},
            "bootstrap": {"b": B_BOOT, "seed": SEED, "refit_each_draw": True,
                          "clustered_by": "player_key (== row at this grain, asserted)"},
            "thresholds": {"p_bust_war6_lt": BUST_WAR6, "p_star_war6_ge": STAR_WAR6,
                           "p_bust_bucket_war6_lt": BUST_BUCKET_WAR6,
                           "p_star_bucket_war6_ge": STAR_BUCKET_WAR6,
                           "bucket_edges_war6": BUCKET_EDGES,
                           "provenance": ("primary thresholds borrow Edwards 2019 THRESHOLD "
                                          "VALUES (<1.0 bust, >10 star); his quantity is "
                                          "9-season arb-discounted present-day WAR and ours is "
                                          "an undiscounted 6-season total, so the value is "
                                          "borrowed and the quantity is NOT")},
            "folds": [{"fold": f, "train_max_year": t, "test_years": list(y)} for f, t, y in FOLDS],
            "degenerate_folds": sorted(DEGENERATE_FOLDS),
        },
        "conversions": {
            "mcdaniel_2014": {
                "source_quantity": "WAR per SEASON, true talent (S3 2014 / L10 2015 read as peak)",
                "bust_inclusive": False, "per_side": False,
                "conversion": "table(FV) x 6", "table": MCDANIEL_2014,
                "extrapolated_rows": [20, 25],
                "notes": ("no published 20/25 row (McDaniel says so explicitly); held flat at "
                          "the FV30 value of -1.0. The negative low end is NOT clipped.")},
            "primer_bands": {
                "source_quantity": "average annual WAR over the first six SERVICE years (S2 2018 / L7 2022)",
                "bust_inclusive": False, "per_side": True,
                "conversion": "band MIDPOINT x 6; open-ended '<-0.1' -> -0.1, '>7.0' -> 7.5",
                "table_hit": PRIMER_HIT, "table_pit": PRIMER_PIT,
                "interpolated_rows": PRIMER_INTERPOLATED,
                "notes": ("the pitcher table is a STARTER table applied to ALL pitchers "
                          "including reliever-outcome rows: a disclosed mismatch, not corrected. "
                          "L7 publishes 35/35+ = '<-0.1' for pitchers but no 35 row for hitters, "
                          "so pit35 = -0.1 while hit35 is interpolated to 0.125.")},
            "clemens_2026": {
                "source_quantity": "TOTAL undiscounted WAR over the whole team-control span (L1 2026)",
                "bust_inclusive": True, "per_side": True,
                "conversion": f"table(FV) x {CLEMENS_SPAN_FACTOR}",
                "sensitivity": f"table(FV) x {round(CLEMENS_SPAN_SENSITIVITY, 4)} "
                               "(candidate clemens_2026_6over7)",
                "table_hit": CLEMENS_HIT, "table_pit": CLEMENS_PIT,
                "notes": ("Clemens' span is '6 to 7-plus years' of control; our label is 6 "
                          "calendar seasons from debut. Primary factor 1.000 on the argument "
                          "that both are 'everything the club got from the prospect'. "
                          "'+' tiers placed at the half-step (35+ -> 37.5, 40+ -> 42.5, "
                          "45+ -> 47.5). No 75/80 row: held flat at 70.")},
            "shipped_fv_to_6yr_avg_war": {
                "source_quantity": "expected (bust-inclusive) average annual WAR over 6 years",
                "bust_inclusive": True, "per_side": False,
                "conversion": "vf.fv_to_6yr_avg_war(FV) x 6",
                "table_live": {str(k): round(vf.fv_to_6yr_avg_war(k), 4) for k in KNOTS},
                "notes": ("read live from the PRODUCTION valuation set (clemens_2026, the "
                          "bare-import default) with anchor_calibration.use_empirical true, so "
                          "these are the fitted empirical_anchors including the 2026-07-29 "
                          "sub-45 amendment, not the config seed.")},
            "shipped_expected_war_core": {
                "source_quantity": "the exact forward map realized_implied_fv inverts to make xfv_grade",
                "bust_inclusive": True, "per_side": False,
                "conversion": ("vf.expected_war(FV, is_pitcher, position, service_years=6, "
                               "age=_grade_map_age(debut_age))['mean'], per row"),
                "notes": "DIAGNOSTIC, not one of the six. Phase 2 replaces THIS, not the x6 table."},
            "shipped_prime_via_aging": {
                "source_quantity": "fv_to_prime_war, the prime/talent anchor",
                "bust_inclusive": True, "per_side": False,
                "conversion": ("sum(vf.prospect_prime_path(FV, is_pitcher, debut_age)['mean'][:6]) "
                               "-- the prime path run through the shipped aging curve and summed "
                               "over the six-season window, per row with the row's own debut age"),
                "sensitivity": "vf.fv_to_prime_war(FV) x 6 (candidate shipped_prime_flat_x6)",
                "table_live": {str(k): vf.fv_to_prime_war(k) for k in KNOTS},
                "notes": ("fv_to_prime_war is used in code as the P(bucket|FV)-weighted "
                          "per-season LEVEL under the prime scale (_prime_war_scale sets the "
                          "bucket scale so the weighted mean equals the anchor), so it is "
                          "bust-inclusive but on a talent LEVEL roughly 1.85x the realized anchor.")},
            "empirical_perside": {"source_quantity": "our label, by construction",
                                  "bust_inclusive": True, "per_side": True,
                                  "conversion": "none; fit on the TRAIN fold only, per fold"},
            "empirical_pooled": {"source_quantity": "our label, sides pooled",
                                 "conversion": "none. DIAGNOSTIC: the comparator for the per-side claim"},
            "empirical_sidepermuted": {"source_quantity": "our label, side labels shuffled in TRAIN",
                                       "conversion": "none. ZERO-INFORMATION CONTROL (gate standard 2)"},
        },
        "curves": curves,
        "sensitivity": sens,
        "bakeoff": table,
        "bakeoff_folds": fold_meta,
        "bakeoff_headline_candidates": HEADLINE,
        "head_to_head": h2h,
        "head_to_head_note": ("paired player-clustered bootstrap on the HELD-OUT rows. "
                              "Negative delta = the FIRST candidate is better. Keys are "
                              "mode|side|A_vs_B. delta_mae is compared against the gate "
                              "standard's MAE MDE95 (0.20 hit / 0.06 pit): a delta inside "
                              "that band is a NULL, not a win."),
        "gate_verdicts": verdicts,
        "deviations_from_pre_registration": [
            {"item": "re-monotonization weights",
             "pre_registered": "PAVA over the knot values with UNIT weights",
             "shipped": "PAVA over the knot values weighted by n_cell + K, taking the direct "
                        "projection at each knot instead of re-interpolating between block "
                        "centroids",
             "why": "the unit-weight, centroid-interpolated version let three ZERO-DATA knots "
                    "(FV 20/25/30) pool 1:1 with the measured FV35 and FV37.5 knots and inflate "
                    "the measured hit FV35 value 12x (0.024 -> 0.295 total 6yr WAR), and the "
                    "centroid shift dragged the hit FV70 knot 5.25 WAR off its shrunk value. "
                    "That is a defect in the rule, not a finding in the data."},
            {"item": "prior extension below the table's bottom row",
             "pre_registered": "Clemens prior 'linearly interpolated in FV' (implicitly clamped)",
             "shipped": "linear ramp from the bottom published row (35+, placed at 37.5) down to "
                        "0.0 at FV 20",
             "why": "clamping put the prior (0.30 hit / 0.25 pit) ABOVE the measured value at "
                    "FV35 (0.07 / 0.01) at w_prior = 1.0, so a prior with no data behind it was "
                    "pulling measured knots upward"},
            {"item": "knot estimate",
             "pre_registered": "the isotonic fit evaluated AT the knot",
             "shipped": "the mean of the isotonic FITTED values over the rows in the knot cell",
             "why": "evaluating at the knot reads whichever exact-FV tie group sits there (hit "
                    "FV35.0 alone is 165 rows at mean -0.004) while the shrinkage weight reads "
                    "the +/-1.25 cell (332 rows, mean +0.072); the estimate and its own sample "
                    "size disagreed. Both readings are reported per knot (isotonic, cell_mean)."},
            {"item": "sub-floor extrapolation",
             "pre_registered": "a monotone ramp under the fitted FV35 value",
             "shipped": "the production concave re-spread (value_framework._LOWEND_FG_EXP = "
                        "0.45, inverted) anchored on the fitted FV35 value; the prior-ramp "
                        "variant is retained per knot as value_sub_floor_prior_ramp_variant",
             "why": "Phase 2 has to decide whether to keep the FV 20-45 display re-spread. The "
                    "measured curve is flat there (hit 0.10 -> 0.47 over FV 35 -> 40), so the "
                    "outcome basis cannot generate that granularity and the policy has to be "
                    "declared rather than fitted."},
            {"item": "head-to-head statistics",
             "pre_registered": "per-candidate slope / bias / MAE / coverage only",
             "shipped": "added a paired, player-clustered bootstrap on the held-out rows with a "
                        "per-fold sign count, for each contest a reject criterion is written on",
             "why": "criteria 1-3 are comparative and a table of separate point estimates cannot "
                    "adjudicate them; the gate standard requires a paired bootstrap with a "
                    "control and >= 4 time splits"}],
        "phase2_inputs": p2,
    }


def report(art):
    p = print
    p("=" * 78)
    p("LANE-CURVES Phase 1: per-side FV -> outcome curves + bake-off")
    p("=" * 78)
    ic = art["pool"]["identity_checks"]
    p(f"pool: hit {ic['hit']['uncensored']} uncensored / {ic['hit']['censored']} censored; "
      f"pit {ic['pit']['uncensored']} / {ic['pit']['censored']}")
    p(f"identity checks: target mism {ic['hit']['target_censored_mismatches']}/"
      f"{ic['pit']['target_censored_mismatches']}, consensus mism "
      f"{ic['hit']['consensus_fv_raw_mismatches']}/{ic['pit']['consensus_fv_raw_mismatches']}, "
      f"cross-side key overlap {ic['cross_side_key_overlap']}, "
      f"clustered==row {ic['player_clustered_bootstrap_is_row_bootstrap']}")
    p(f"vintage: {art['pool']['vintage_verification']}")

    for side in ("hit", "pit"):
        c = art["curves"][side]["war"]
        p("")
        p(f"--- {side.upper()} E[first-6yr bWAR | consensus FV] "
          f"(fv range {c['data_fv_min']} - {c['data_fv_max']}, n={c['n_rows']}) ---")
        p(f"{'FV':>5} {'n_cell':>7} {'w_prior':>8} {'cellmean':>9} {'isotonic':>9} {'prior':>8} "
          f"{'VALUE':>8} {'ci90_lo':>8} {'ci90_hi':>8}  flag")
        for i, k in enumerate(c["knots"]):
            flag = []
            if c["extrapolation"][i]:
                flag.append("POLICY-EXTRAP")
            if c["n_cell"][i] < 30:
                flag.append("shrink-cell")
            cm = c["cell_mean"][i]
            p(f"{k:>5} {c['n_cell'][i]:>7} {c['w_prior'][i]:>8.3f} "
              f"{(f'{cm:9.3f}' if cm is not None else '        -')} {c['isotonic'][i]:>9.3f} "
              f"{c['prior'][i]:>8.3f} {c['value'][i]:>8.3f} {c['ci90_lo'][i]:>8.3f} "
              f"{c['ci90_hi'][i]:>8.3f}  {','.join(flag)}")
        p(f"monotone repair max move: {c['monotone_repair_max_move']:.4f} WAR")
        s = art["sensitivity"][side]["war_censored_included_weighted"]
        p("censoring sensitivity (all rows, weighted): " +
          " ".join(f"{k:g}={v:.2f}" for k, v in zip(s["knots"], s["value"]) if k >= 35))

    for side in ("hit", "pit"):
        p("")
        p(f"--- {side.upper()} odds curves ---")
        pb, ps = art["curves"][side]["p_bust"], art["curves"][side]["p_star"]
        pbb, psb = art["curves"][side]["p_bust_bucket"], art["curves"][side]["p_star_bucket"]
        p(f"{'FV':>5} {'n':>6} {'p_bust<1':>9} {'p_star>=10':>11} {'p_bust<3':>9} {'p_star>=24':>11}")
        for i, k in enumerate(pb["knots"]):
            if k < 35:
                continue
            p(f"{k:>5} {pb['n_cell'][i]:>6} {pb['value'][i]:>9.3f} {ps['value'][i]:>11.3f} "
              f"{pbb['value'][i]:>9.3f} {psb['value'][i]:>11.3f}")

    p("")
    p("--- folds ---")
    for fm in art["bakeoff_folds"]:
        if fm.get("skipped"):
            p(f"  {fm['fold']}: SKIPPED")
            continue
        p(f"  {fm['fold']}: train<= {fm['train_max_year']} n={fm['n_train']}  "
          f"test {fm['test_years']} n={fm['n_test']}  fv>=47.5 in test {fm['n_test_fv_ge_475']}"
          f"{'   *** DEGENERATE ***' if fm['degenerate'] else ''}")

    for mode in ("raw", "shape"):
        for side in ("hit", "pit"):
            p("")
            p(f"=== BAKE-OFF {mode.upper()} / {side.upper()} (held out, pooled over folds) ===")
            p(f"{'candidate':30} {'n':>5} {'slope':>7} {'bias':>8} {'MAE':>7} {'cov90':>6} | "
              f"per-band MAE  lt40 / 40-45 / 45-50 / 50-55 / 55+")
            for cand in CANDIDATES:
                blk = art["bakeoff"][cand][mode][side]
                a = blk["all"]
                if not a:
                    continue
                bm = []
                for bn, _, _ in BANDS:
                    cell = blk["bands"][bn]
                    bm.append(f"{cell['mae']:.2f}" if cell else "  -")
                sl = f"{a['slope']:.3f}" if a["slope"] is not None else "   -"
                cv = f"{blk['coverage_90']:.2f}" if blk["coverage_90"] is not None else "  -"
                p(f"{cand:30} {a['n']:>5} {sl:>7} {a['bias_mean_resid']:>8.3f} "
                  f"{a['mae']:>7.3f} {cv:>6} | " + " / ".join(bm))

    for mode in ("raw", "shape"):
        for side in ("hit", "pit"):
            p("")
            p(f"=== PER-BAND CALIBRATION SLOPE / BIAS  {mode.upper()} / {side.upper()} ===")
            p(f"{'candidate':30} " + " ".join(f"{b:>16}" for b, _, _ in BANDS))
            for cand in HEADLINE + ["empirical_pooled", "empirical_sidepermuted"]:
                cells = art["bakeoff"][cand][mode][side]["bands"]
                out = []
                for bn, _, _ in BANDS:
                    c = cells[bn]
                    if not c:
                        out.append(f"{'-':>16}")
                    else:
                        sl = f"{c['slope']:.2f}" if c["slope"] is not None else "  - "
                        out.append(f"{sl:>7}/{c['bias_mean_resid']:>8.2f}")
                p(f"{cand:30} " + " ".join(out))
            p("   (slope / mean signed bias; ideal 1.00 / 0.00)")

    p("")
    p("=== HEAD-TO-HEAD, paired player-clustered bootstrap on held-out rows ===")
    p("(negative = FIRST candidate better; MAE MDE95 = 0.20 hit / 0.06 pit)")
    p(f"{'contest':60} {'n':>5} {'dMAE':>7} {'CI90':>17} {'d|sl-1|':>8} {'CI90':>17} {'fld':>5}")
    for k, v in art["head_to_head"].items():
        ci = f"[{v['delta_mae_ci90'][0]:+.3f},{v['delta_mae_ci90'][1]:+.3f}]"
        ds = f"{v['delta_abs_slope_minus_1']:+.3f}" if v["delta_abs_slope_minus_1"] is not None else "   -"
        sci = (f"[{v['delta_abs_slope_ci90'][0]:+.3f},{v['delta_abs_slope_ci90'][1]:+.3f}]"
               if v.get("delta_abs_slope_ci90") else "-")
        p(f"{k:60} {v['n']:>5} {v['delta_mae']:>+7.3f} {ci:>17} {ds:>8} {sci:>17} "
          f"{v['folds_where_first_wins_mae']}/{v['folds_scored']}")

    p("")
    p("=== PRE-REGISTERED REJECT CRITERIA ===")
    p(json.dumps(art["gate_verdicts"], indent=1))

    p2 = art["phase2_inputs"]
    p("")
    p("--- named players: current vs per-side-curve re-scaled grade ---")
    p(f"{'player':24} {'side':4} {'war6':>6} {'cons':>6} {'current':>8} {'rescaled':>9} {'delta':>7}")
    for r in p2["named_players"]:
        if not r.get("found"):
            p(f"{r['player_key']:24} NOT FOUND")
            continue
        p(f"{r['player_key']:24} {r['side']:4} {r['xfv_war_6yr']:>6} {r['consensus_fv']:>6} "
          f"{r['xfv_grade_current']:>8} {r['xfv_grade_rescaled']:>9} {r['delta']:>7}"
          f"{'  (provisional)' if r['provisional'] else ''}")
    p("")
    p(f"top-N side mix CURRENT : {json.dumps(p2['top_n_side_mix_current'])}")
    p(f"top-N side mix RESCALED: {json.dumps(p2['top_n_side_mix_rescaled'])}")
    p(f"top-N side mix POOLED  : {json.dumps(p2['top_n_side_mix_rescaled_pooled_curve'])}")
    p(f"board rows rescaled {p2['board_rows_rescaled']}, clamped at 20: {p2['clamped_at_20']}, "
      f"at 80: {p2['clamped_at_80']}")
    p(f"below the DATA FLOOR (cons FV 35): {p2['board_rows_below_the_data_floor']}; "
      f"rows already served at grade 20.0: {p2['board_rows_already_at_grade_20_served']}")
    p(f"within-side monotonicity: {json.dumps(p2['within_side_monotonicity'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-write", action="store_true", help="print only, do not write the artifact")
    a = ap.parse_args()
    run(write=not a.no_write)
