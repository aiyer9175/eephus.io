# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Forward-chained gate for a DEDICATED MEAN HEAD on proj_lgbm.

The registry's disclosed open miss (war_cohort_diagnostic): established MLB stars are
UNDER-projected at the out-years. The shipped point projection lifts the MAE-optimal q50
toward the quantile-IMPLIED mean (trapezoid of q10..q90) -- but those quantile heads are
TAIL-LIGHT, so the implied mean under-states E[WAR] exactly where the right tail matters
(stars). A head trained with objective="regression" estimates E[WAR|x] DIRECTLY and is
not tail-light.

This harness swaps ONLY the recenter TARGET (implied-mean -> mean-head), holding the
shipped lift-only blend logic + lambdas fixed, and re-scores forward-chained on the
proj_eval corpus. Champion == the live predict_path blend (global mean-blend lift-only
+ star top-up). Variants:
  champion   q50 -> lift toward IMPLIED mean (mean-blend lam) + star top-up (star-blend lam)
  mh_same    q50 -> lift toward MEAN-HEAD   (same lambdas)
  mh_full    q50 -> lift toward MEAN-HEAD, lambda 1.0 lift-only every horizon (use it fully)

Metric per cohort/horizon: pooled MAE + bias, star slice (base-year WAR>=4) MAE + bias.
GATE (the owner's intent = "projections a bit low", esp. stars): a variant ships only if
it REDUCES star bias (toward 0) on the HOLDOUT without regressing pooled MAE. Loser is a
documented rejection. Hitters + pitchers (the miss is on both sides per the diagnostic).

VERDICT 2026-06-29 -- REJECTED (loss, not shipped). Holdout pooled: champion MAE 0.5069
(star bias -0.635); mean-head MAE 0.5429 (star bias -0.296). The mean head DOES cut the
star under-projection but REGRESSES pooled MAE by over-lifting non-stars -- the lift-only
implied-mean blend is the better Pareto point. Result recorded in
data/proj_horizon_eval.json -> challenger_blocks.mean_head_rejected. A star-slice-ONLY
mean head (all horizons) is the one unexplored variant.

Run: python tools/mean_head_backtest.py   (appends challenger_blocks.mean_head_rejected)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os
os.chdir(ROOT)

import fa_projection as fp          # noqa: E402
import proj_ml as PM                # noqa: E402
from lightgbm import LGBMRegressor  # noqa: E402

DEV_BASES = [2017, 2018, 2019, 2021]
HOLDOUT_BASES = [2022, 2023, 2024]
FRAME_MAX_LABEL = 2024
FIRST_BASE = 2003
QS = PM.QUANTILES                       # (.10,.25,.50,.75,.90)
MEAN_LAM = {1: 1.0, 2: 1.0, 3: 1.0, 4: 0.5, 5: 0.5}   # data/proj_mean_blend.json
STAR_LAM = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 1.0}   # data/proj_star_blend.json


def _implied(q):  # q = [q10,q25,q50,q75,q90]
    return (q[0] + 2 * q[1] + 2 * q[2] + 2 * q[3] + q[4]) / 8.0


def _point(q50, target, h, is_star):
    """Replicate predict_path's lift-only global blend + star top-up, with `target`
    as the recenter mean (implied-mean for champion, mean-head for the challenger)."""
    p = q50
    shift = MEAN_LAM[h] * (target - p)
    if shift > 0:
        p += shift
    if is_star and STAR_LAM[h] > 0:
        p += STAR_LAM[h] * (target - p)
    return p


def _point_full(q50, mh, h, is_star):
    """Lift-only toward the mean head, lambda 1.0 every horizon (use it fully)."""
    return q50 + max(0.0, mh - q50)


def run():
    corpus = fp.build_corpus()
    last_complete = corpus["last"] - 1
    PM.DEF_FEATURE_KEYS = PM.DEF_FEATURE_KEYS  # use the shipped schema (incl. pos_adj_prior)
    frame = PM.build_training_frame(corpus, FIRST_BASE, FRAME_MAX_LABEL)

    by_player = {"hit": {}, "pit": {}}
    war_actual = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side].setdefault(r["mlbam"], {})[r["season"]] = r
                if r.get("war") is not None:
                    k = (r["mlbam"], r["season"])
                    war_actual[k] = war_actual.get(k, 0.0) + r["war"]

    # accumulators: variant -> cohort -> horizon -> list[(pred, actual, is_star)]
    variants = ("champion", "mh_same", "mh_full")
    agg = {v: {c: {h: [] for h in range(1, PM.HORIZONS + 1)}
               for c in ("dev", "holdout")} for v in variants}

    for cohort, bases in (("dev", DEV_BASES), ("holdout", HOLDOUT_BASES)):
        for B in bases:
            curves, war_map = fp.fitted_models(corpus, B - 1)
            # forward-chained heads per side/horizon: q-heads + a mean head
            heads = {"hit": {}, "pit": {}}
            for side in ("hit", "pit"):
                f = frame[side]
                for h in range(1, PM.HORIZONS + 1):
                    ls = f["label_season"][h]
                    sel = ls <= (B - 1)
                    if sel.sum() < 500:
                        continue
                    ridx = f["rows"][h][sel]
                    X, y = f["X"][ridx], f["y"][h][sel]
                    hq = {}
                    for q in QS:
                        m = LGBMRegressor(alpha=q, **PM._params_for(h))
                        m.fit(X, y)
                        hq[q] = m
                    mp = dict(PM._params_for(h)); mp["objective"] = "regression"
                    mh = LGBMRegressor(**mp); mh.fit(X, y)
                    hq["mean"] = mh
                    heads[side][h] = hq
            # eval rows
            for side in ("hit", "pit"):
                fr = frame[side]
                for mlbam, seasons in by_player[side].items():
                    hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                    if not hist:
                        continue
                    age_prev = next((hh.get("age") for hh in hist if hh.get("age")), None)
                    if age_prev is None:
                        continue
                    age = age_prev + (B - hist[0]["season"])
                    feats = PM.build_features(hist, side, B, age, curves, war_map,
                                              corpus["league"])
                    if feats is None:
                        continue
                    x = np.asarray(feats, dtype=float).reshape(1, -1)
                    base_war = war_actual.get((mlbam, B - 1))
                    is_star = base_war is not None and base_war >= 4.0
                    for h in range(1, PM.HORIZONS + 1):
                        target = B + h - 1
                        if target > last_complete or h not in heads[side]:
                            continue
                        hq = heads[side][h]
                        qv = sorted(float(hq[q].predict(x)[0]) for q in QS)
                        q50 = qv[2]
                        imp = _implied(qv)
                        mh = float(hq["mean"].predict(x)[0])
                        act = war_actual.get((mlbam, target), 0.0)
                        agg["champion"][cohort][h].append((_point(q50, imp, h, is_star), act, is_star))
                        agg["mh_same"][cohort][h].append((_point(q50, mh, h, is_star), act, is_star))
                        agg["mh_full"][cohort][h].append((_point_full(q50, mh, h, is_star), act, is_star))
            print(f"  done base {B}")

    # summarize
    def _summ(pairs):
        if not pairs:
            return None
        mae = sum(abs(p - a) for p, a, _ in pairs) / len(pairs)
        bias = sum(p - a for p, a, _ in pairs) / len(pairs)
        sp = [(p, a) for p, a, s in pairs if s]
        smae = (sum(abs(p - a) for p, a in sp) / len(sp)) if sp else None
        sbias = (sum(p - a for p, a in sp) / len(sp)) if sp else None
        return {"n": len(pairs), "mae": round(mae, 4), "bias": round(bias, 4),
                "n_star": len(sp), "star_mae": round(smae, 4) if smae is not None else None,
                "star_bias": round(sbias, 4) if sbias is not None else None}

    out = {"dev_bases": DEV_BASES, "holdout_bases": HOLDOUT_BASES, "variants": {}}
    for v in variants:
        out["variants"][v] = {}
        for cohort in ("dev", "holdout"):
            allp = [p for h in range(1, PM.HORIZONS + 1) for p in agg[v][cohort][h]]
            per_h = {h: _summ(agg[v][cohort][h]) for h in range(1, PM.HORIZONS + 1)
                     if agg[v][cohort][h]}
            out["variants"][v][cohort] = {"pooled": _summ(allp), "per_h": per_h}

    # Record into the REGISTERED eval artifact (challenger_blocks), matching the
    # statcast-rejection convention -- no separate unregistered *_eval.json file
    # (test_model_registry enforces every data/*_eval.json belongs to a model).
    art_p = ROOT / "data" / "proj_horizon_eval.json"
    art = json.loads(art_p.read_text(encoding="utf-8")) if art_p.exists() else {}
    art.setdefault("challenger_blocks", {})["mean_head_rejected"] = out
    art_p.write_text(json.dumps(art, indent=1), encoding="utf-8")
    # print the headline
    print("\n=== HOLDOUT (pooled) — champion vs mean-head variants ===")
    for v in variants:
        s = out["variants"][v]["holdout"]["pooled"]
        print(f"  {v:>9}: MAE {s['mae']:.4f}  bias {s['bias']:+.4f} | "
              f"star MAE {s['star_mae']:.4f}  star bias {s['star_bias']:+.4f} (n_star={s['n_star']})")
    print("=== DEV (pooled) ===")
    for v in variants:
        s = out["variants"][v]["dev"]["pooled"]
        print(f"  {v:>9}: MAE {s['mae']:.4f}  bias {s['bias']:+.4f} | "
              f"star MAE {s['star_mae']:.4f}  star bias {s['star_bias']:+.4f}")
    print("\nwrote data/proj_mean_head_eval.json")
    return out


if __name__ == "__main__":
    run()
