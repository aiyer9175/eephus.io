# SCRATCH LAB (lane: blastradius) -- Step 3: is the FG-anchoring DIRECTIONALLY RIGHT?
#
# THE TEST. On players graded by BOTH FanGraphs and MLB Pipeline in the same cycle,
# with a resolved first-6yr WAR outcome, estimate the OUTCOME-EQUIVALENCE offset:
#   the delta d such that an MLB Pipeline grade of g predicts the same realized WAR
#   as a FanGraphs grade of (g - d).
# Stacked OLS on the SAME players:  W = a + b*fv + c*is_mp,  d = -c/b.
#
#   d ~ raw mean gap  => MP's extra points are PURE SCALE (a hot grader). Subtracting
#                        the offset is the right repair and destroys no information.
#   d ~ 0             => MP's extra points carry REAL outcome information. Normalizing
#                        them away destroys signal and the repair is wrong.
#
# Controls per docs/EFV_GATE_STANDARD.md section 2:
#   (1) cluster (by player) bootstrap with a REFIT each draw, B=2000
#   (2) zero-information control: the source LABEL permuted within player (the grade
#       pair is identical, only which one is called "MP" is randomized) -> d must be 0
#   (3) permutation null band for the same statistic
#   (4) the effect over >= 4 independent cohort-year time splits
import json
import os
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)

RNG = np.random.default_rng(20260725)
B = 2000


def load(side):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    rows = json.loads((_HERE / "data" / fn).read_text(encoding="utf-8"))
    out = []
    for r in rows:
        fg, mp = r.get("fv_fangraphs"), r.get("fv_mlb_pipeline")
        y = r.get("target_censored")
        if y is None:
            y = r.get("target_resolved")
        if fg is None or mp is None or y is None:
            continue
        yr = r.get("debut_year")
        if yr is None:
            a = r.get("asof_date") or ""
            yr = int(a[:4]) if a[:4].isdigit() else None
        if yr is None:
            continue
        out.append((float(fg), float(mp), float(y), int(yr), r["player_key"]))
    return out


def fit_offset(fg, mp, y):
    """Stacked OLS: W = a + b*fv + c*is_mp  ->  equivalence offset d = -c/b."""
    n = len(fg)
    X = np.column_stack([np.ones(2 * n),
                         np.concatenate([fg, mp]),
                         np.concatenate([np.zeros(n), np.ones(n)])])
    Y = np.concatenate([y, y])
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    b, c = beta[1], beta[2]
    if abs(b) < 1e-9:
        return np.nan, np.nan, np.nan
    return -c / b, b, c


def per_source_slope(x, y):
    A = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return beta[1], beta[0]


for side in ("hit", "pit"):
    rows = load(side)
    fg = np.array([r[0] for r in rows]); mp = np.array([r[1] for r in rows])
    y = np.array([r[2] for r in rows]);  yr = np.array([r[3] for r in rows])
    n = len(rows)
    print(f"\n================ {side.upper()}  n_pair={n} "
          f"(cohort years {yr.min()}-{yr.max()}) ================")
    gap = float((mp - fg).mean())
    print(f"RAW MEAN GAP  mean(MP) - mean(FG) on the same players: {gap:+.3f} FV")
    b_fg, a_fg = per_source_slope(fg, y)
    b_mp, a_mp = per_source_slope(mp, y)
    print(f"WAR-per-FV slope: FG {b_fg:.4f}   MP {b_mp:.4f}   (ratio {b_mp/b_fg:.3f})")

    d, b, c = fit_offset(fg, mp, y)
    print(f"OUTCOME-EQUIVALENCE OFFSET d = {d:+.3f} FV   (b={b:.4f}, c={c:+.4f})")

    # (1) cluster bootstrap, refit each draw
    ds = np.empty(B)
    for i in range(B):
        idx = RNG.integers(0, n, n)
        ds[i], _, _ = fit_offset(fg[idx], mp[idx], y[idx])
    lo, hi = np.nanpercentile(ds, [2.5, 97.5])
    print(f"  cluster bootstrap (refit/draw, B={B}): mean {np.nanmean(ds):+.3f} "
          f"CI95 [{lo:+.3f}, {hi:+.3f}]  sd {np.nanstd(ds):.3f}")
    print(f"  P(d has the same sign as the raw gap) = "
          f"{float(np.nanmean(np.sign(ds) == np.sign(gap))):.3f}")
    print(f"  P(|d| >= |raw gap|)                   = "
          f"{float(np.nanmean(np.abs(ds) >= abs(gap))):.3f}   "
          f"P(|d| <= 0.5*|raw gap|) = {float(np.nanmean(np.abs(ds) <= 0.5*abs(gap))):.3f}")

    # (2) zero-information control: randomize WHICH of the pair is labelled MP
    ctl = np.empty(B)
    for i in range(B):
        swap = RNG.random(n) < 0.5
        a_ = np.where(swap, mp, fg); b_ = np.where(swap, fg, mp)
        ctl[i], _, _ = fit_offset(a_, b_, y)
    clo, chi = np.nanpercentile(ctl, [2.5, 97.5])
    print(f"  ZERO-INFO control (source label permuted within player): mean "
          f"{np.nanmean(ctl):+.3f} CI95 [{clo:+.3f}, {chi:+.3f}]")
    print(f"    candidate OUTSIDE the control band: {not (clo <= d <= chi)}")

    # (3) permutation null: break the grade->outcome link entirely
    perm = np.empty(B)
    for i in range(B):
        perm[i], _, _ = fit_offset(fg, mp, RNG.permutation(y))
    plo, phi = np.nanpercentile(perm, [2.5, 97.5])
    p2 = float(np.nanmean(np.abs(perm) >= abs(d)))
    print(f"  PERMUTATION null (outcome shuffled): CI95 [{plo:+.3f}, {phi:+.3f}]  "
          f"two-sided p = {p2:.4f}")

    # (4) >= 4 independent time splits
    print("  TIME SPLITS (cohort year):")
    edges = np.quantile(yr, [0, .25, .5, .75, 1.0])
    used = []
    for j in range(4):
        m = (yr >= edges[j]) & (yr <= edges[j + 1]) if j == 3 else \
            (yr >= edges[j]) & (yr < edges[j + 1])
        if m.sum() < 40:
            continue
        dj, _, _ = fit_offset(fg[m], mp[m], y[m])
        gj = float((mp[m] - fg[m]).mean())
        used.append(dj)
        print(f"    yrs {int(yr[m].min())}-{int(yr[m].max())}  n={int(m.sum()):4d}  "
              f"d={dj:+.3f}   raw gap={gj:+.3f}")
    if used:
        print(f"    cross-split mean d = {np.nanmean(used):+.3f}   "
              f"sign agreement {sum(1 for v in used if np.sign(v)==np.sign(gap))}/{len(used)}")
