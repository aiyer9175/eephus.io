# SCRATCH LAB (lane: blastradius) -- Step 3, ROUND 2.
#
# ROUND 1 (tools/_gn_outcome_equiv.py) IS RETRACTED AS DEGENERATE. Its stacked-OLS
# offset returns the raw mean gap ALGEBRAICALLY: with the same players on both sides
# the outcome column has identical half-means, so the source dummy must absorb
# b*(mean(mp)-mean(fg)) and d = -c/b = the raw gap regardless of the outcome. The
# permutation null proved it (CI95 collapsed to a single point = the gap, p=0.64).
# Any mean-matching estimator on the SAME players with a LINEAR outcome model is
# degenerate this way. Reported as a null result of the method, not of the world.
#
# The offset is a CONSTANT for a player graded by both outlets, so it cannot change
# their relative order. It only bites where COVERAGE differs -- an MP-only prospect
# vs an FG-only prospect. That is the operative question and it IS testable:
#
#  TEST A (cross-coverage equivalence). On DISTINCT players, fit
#     W = a + b*fv + c*is_mp_only    over (FG-only) union (MP-only)
#  d = -c/b is the shift that puts MP-only grades on FG-only's outcome footing.
#  Not degenerate: the two groups are different players with different outcomes.
#
#  TEST B (is a pure SHIFT the right functional form?). H0: slope_MP == slope_FG on
#  the paired players. A shift is only right if the WAR-per-FV slopes agree.
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
        y = r.get("target_censored")
        if y is None:
            y = r.get("target_resolved")
        if y is None:
            continue
        a = r.get("asof_date") or ""
        yr = r.get("debut_year") or (int(a[:4]) if a[:4].isdigit() else None)
        if yr is None:
            continue
        out.append({"fg": r.get("fv_fangraphs"), "mp": r.get("fv_mlb_pipeline"),
                    "y": float(y), "yr": int(yr), "k": r["player_key"]})
    return out


def ols(X, Y):
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    return beta


def offset_cross(fv, y, ismp):
    X = np.column_stack([np.ones(len(fv)), fv, ismp])
    b = ols(X, y)
    return (np.nan if abs(b[1]) < 1e-9 else -b[2] / b[1]), b[1], b[2]


for side in ("hit", "pit"):
    rows = load(side)
    fgo = [r for r in rows if r["fg"] is not None and r["mp"] is None]
    mpo = [r for r in rows if r["mp"] is not None and r["fg"] is None]
    both = [r for r in rows if r["mp"] is not None and r["fg"] is not None]
    print(f"\n================ {side.upper()} ================")
    print(f"coverage: FG-only {len(fgo)}   MP-only {len(mpo)}   both {len(both)}")

    # ---------------- TEST A ----------------
    if len(fgo) >= 40 and len(mpo) >= 40:
        fv = np.array([r["fg"] for r in fgo] + [r["mp"] for r in mpo], float)
        y = np.array([r["y"] for r in fgo] + [r["y"] for r in mpo], float)
        ismp = np.array([0.0] * len(fgo) + [1.0] * len(mpo))
        yr = np.array([r["yr"] for r in fgo] + [r["yr"] for r in mpo])
        n = len(fv)
        d, b, c = offset_cross(fv, y, ismp)
        gap_paired = float(np.mean([r["mp"] - r["fg"] for r in both])) if both else np.nan
        print(f"TEST A cross-coverage offset d = {d:+.3f} FV   (b={b:.4f}, c={c:+.4f})")
        print(f"  reference: paired raw mean gap = {gap_paired:+.3f} FV "
              f"(what the shipped repair subtracts)")
        print(f"  raw mean grade: FG-only {fv[ismp==0].mean():.2f}  "
              f"MP-only {fv[ismp==1].mean():.2f};  mean WAR: "
              f"FG-only {y[ismp==0].mean():.2f}  MP-only {y[ismp==1].mean():.2f}")

        ds = np.empty(B)
        for i in range(B):
            idx = RNG.integers(0, n, n)
            ds[i], _, _ = offset_cross(fv[idx], y[idx], ismp[idx])
        lo, hi = np.nanpercentile(ds, [2.5, 97.5])
        print(f"  bootstrap (refit/draw, B={B}): mean {np.nanmean(ds):+.3f} "
              f"CI95 [{lo:+.3f}, {hi:+.3f}]  sd {np.nanstd(ds):.3f}")
        print(f"  P(d > 0) = {float(np.nanmean(ds > 0)):.3f}   "
              f"P(d >= paired gap) = {float(np.nanmean(ds >= gap_paired)):.3f}")

        ctl = np.empty(B)
        for i in range(B):
            ctl[i], _, _ = offset_cross(fv, y, RNG.permutation(ismp))
        clo, chi = np.nanpercentile(ctl, [2.5, 97.5])
        print(f"  ZERO-INFO control (coverage label permuted): mean {np.nanmean(ctl):+.3f} "
              f"CI95 [{clo:+.3f}, {chi:+.3f}]  -> candidate outside band: "
              f"{not (clo <= d <= chi)}")
        perm = np.empty(B)
        for i in range(B):
            perm[i], _, _ = offset_cross(fv, RNG.permutation(y), ismp)
        plo, phi = np.nanpercentile(perm, [2.5, 97.5])
        print(f"  PERMUTATION null (outcome shuffled): CI95 [{plo:+.3f}, {phi:+.3f}]  "
              f"two-sided p = {float(np.nanmean(np.abs(perm) >= abs(d))):.4f}")
        edges = np.quantile(yr, [0, .25, .5, .75, 1.0])
        vals = []
        print("  TIME SPLITS:")
        for j in range(4):
            m = ((yr >= edges[j]) & (yr <= edges[j+1])) if j == 3 else \
                ((yr >= edges[j]) & (yr < edges[j+1]))
            if m.sum() < 40 or ismp[m].sum() < 10 or (1 - ismp[m]).sum() < 10:
                print(f"    split {j}: too thin (n={int(m.sum())}, "
                      f"mp={int(ismp[m].sum())}) - SKIPPED")
                continue
            dj, _, _ = offset_cross(fv[m], y[m], ismp[m])
            vals.append(dj)
            print(f"    yrs {int(yr[m].min())}-{int(yr[m].max())}  n={int(m.sum()):4d}  "
                  f"(mp-only {int(ismp[m].sum()):3d})  d={dj:+.3f}")
        if vals:
            print(f"    cross-split mean {np.nanmean(vals):+.3f}  sign agreement "
                  f"{sum(1 for v in vals if v > 0)}/{len(vals)} positive")
    else:
        print("TEST A: UNAVAILABLE - a coverage arm is thinner than 40 rows")

    # ---------------- TEST B ----------------
    if len(both) >= 60:
        fgv = np.array([r["fg"] for r in both], float)
        mpv = np.array([r["mp"] for r in both], float)
        yv = np.array([r["y"] for r in both], float)
        n = len(both)

        def slopes(i):
            bf = ols(np.column_stack([np.ones(len(i)), fgv[i]]), yv[i])[1]
            bm = ols(np.column_stack([np.ones(len(i)), mpv[i]]), yv[i])[1]
            return bf, bm
        bf, bm = slopes(np.arange(n))
        diffs = np.empty(B)
        for i in range(B):
            idx = RNG.integers(0, n, n)
            a_, b_ = slopes(idx)
            diffs[i] = b_ - a_
        lo, hi = np.nanpercentile(diffs, [2.5, 97.5])
        print(f"TEST B slope equality on the paired players (n={n}):")
        print(f"  WAR-per-FV  FG {bf:.4f}   MP {bm:.4f}   diff {bm-bf:+.4f}")
        print(f"  paired bootstrap CI95 [{lo:+.4f}, {hi:+.4f}]  "
              f"-> slopes differ: {not (lo <= 0 <= hi)}")
        print(f"  P(MP slope steeper) = {float(np.nanmean(diffs > 0)):.3f}")
    else:
        print("TEST B: UNAVAILABLE - fewer than 60 paired rows")
