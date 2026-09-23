# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Forward-chained gate for a STAR-SLICE-ONLY mean-head top-up on proj_lgbm.

The global mean head (tools/mean_head_backtest.py) was rejected: applied to everyone it
over-lifts non-stars and regresses pooled MAE. But the diagnosed miss is STARS being
UNDER-projected (war_cohort: h1 -1.10, h5 -0.82), and at h1-h3 the shipped GLOBAL mean
blend already lifts stars to the quantile-IMPLIED mean -- which is TAIL-LIGHT, so it
under-lifts exactly the right tail. A dedicated objective=regression mean head is not
tail-light; applied ONLY to the ex-ante star slice (base-year WAR>=4) as an ADDITIONAL
lift on top of the live blend, it can cut the residual star under-projection while
leaving every non-star row (so pooled MAE) untouched.

Champion == the LIVE predict_path point: global lift-only mean blend (lam 1/1/1/.5/.5)
then the star top-up toward the implied mean (lam_5=1). Challenger adds, for star rows
only, q50' = q50 + lam_smh_h * max(0, mean_head - q50). lam_smh is FIT forward-chained on
the dev bases (minimize |star bias| subject to star MAE not degrading > MAE_GUARD), the
fit_star_blend protocol -- then APPLIED untouched to the holdout.

GATE: ship only if, on the HOLDOUT, star bias moves toward 0 AND star MAE does not degrade
beyond the guard AND pooled MAE does not regress (star-only => pooled barely moves). Loser
is a documented rejection. Hitters + pitchers (the miss is on both).

VERDICT 2026-06-29 -- REJECTED (loss, not shipped). The dev fit lands on ~zero lift
(h1-h4 lam=0, h5 lam=0.25) and the HOLDOUT shows NO change (star bias -0.635 unchanged,
star MAE 1.850 unchanged, pooled unchanged). The shipped global mean blend already lifts
stars to the implied mean; any further mean-head lift that stays within the star-MAE guard
buys no bias improvement -- the blend is already at the MAE-constrained optimum. So the
mean-head lever is exhausted; the remaining lever is a heads-level aging/tail refit.

Run: python tools/star_mean_head_backtest.py  (records challenger_blocks.star_mean_head)
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
QS = PM.QUANTILES
MEAN_LAM = {1: 1.0, 2: 1.0, 3: 1.0, 4: 0.5, 5: 0.5}   # data/proj_mean_blend.json (global, lift-only)
STAR_LAM = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 1.0}   # data/proj_star_blend.json (star top-up)
LAM_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
MAE_GUARD = 0.02


def _implied(q):
    return (q[0] + 2 * q[1] + 2 * q[2] + 2 * q[3] + q[4]) / 8.0


def _champion_point(qv, h, is_star):
    """Replicate the LIVE predict_path point: global lift-only mean blend, then the star
    top-up toward the (recomputed) implied mean. qv = sorted [q10,q25,q50,q75,q90]."""
    q10, q25, q50, q75, q90 = qv
    mean1 = _implied(qv)
    shift = MEAN_LAM[h] * (mean1 - q50)
    if shift > 0:
        q50 = q50 + shift
    if is_star and STAR_LAM[h] > 0:
        mean2 = _implied([q10, q25, q50, q75, q90])   # implied with the lifted q50
        q50 = q50 + STAR_LAM[h] * (mean2 - q50)
    return q50


def run():
    corpus = fp.build_corpus()
    last_complete = corpus["last"] - 1
    frame = PM.build_training_frame(corpus, FIRST_BASE, FRAME_MAX_LABEL)

    by_player = {"hit": {}, "pit": {}}
    war_actual = fp.war_actual_map(corpus)  # the ONE label (809902c6); never sum r['war'] across sides
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side].setdefault(r["mlbam"], {})[r["season"]] = r

    # per cohort/horizon: star rows carry (champ_point, mean_head, actual);
    # all rows carry (champ_point, actual, is_star) for pooled.
    star = {c: {h: [] for h in range(1, PM.HORIZONS + 1)} for c in ("dev", "holdout")}
    pooled = {c: {h: [] for h in range(1, PM.HORIZONS + 1)} for c in ("dev", "holdout")}

    for cohort, bases in (("dev", DEV_BASES), ("holdout", HOLDOUT_BASES)):
        for B in bases:
            curves, war_map = fp.fitted_models(corpus, B - 1)
            heads = {"hit": {}, "pit": {}}
            for side in ("hit", "pit"):
                f = frame[side]
                for h in range(1, PM.HORIZONS + 1):
                    sel = f["label_season"][h] <= (B - 1)
                    if sel.sum() < 500:
                        continue
                    ridx = f["rows"][h][sel]
                    X, y = f["X"][ridx], f["y"][h][sel]
                    hq = {q: LGBMRegressor(alpha=q, **PM._params_for(h)).fit(X, y) for q in QS}
                    mp = dict(PM._params_for(h)); mp["objective"] = "regression"
                    hq["mean"] = LGBMRegressor(**mp).fit(X, y)
                    heads[side][h] = hq
            for side in ("hit", "pit"):
                for mlbam, seasons in by_player[side].items():
                    hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                    if not hist:
                        continue
                    age_prev = next((hh.get("age") for hh in hist if hh.get("age")), None)
                    if age_prev is None:
                        continue
                    age = age_prev + (B - hist[0]["season"])
                    feats = PM.build_features(hist, side, B, age, curves, war_map, corpus["league"])
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
                        cp = _champion_point(qv, h, is_star)
                        act = war_actual.get((mlbam, target), 0.0)
                        pooled[cohort][h].append((cp, act, is_star))
                        if is_star:
                            mh = float(hq["mean"].predict(x)[0])
                            star[cohort][h].append((cp, mh, act))
            print(f"  done base {B}")

    # fit lam_smh per horizon on DEV: minimize |star bias| s.t. star MAE <= champ + guard
    lam_fit = {}
    dev_table = {}
    for h in range(1, PM.HORIZONS + 1):
        rows = star["dev"][h]
        if not rows:
            lam_fit[h] = 0.0
            continue
        champ_bias = sum(cp - a for cp, mh, a in rows) / len(rows)
        champ_mae = sum(abs(cp - a) for cp, mh, a in rows) / len(rows)
        best = (0.0, champ_bias, champ_mae)
        for lam in LAM_GRID[1:]:
            preds = [cp + lam * max(0.0, mh - cp) for cp, mh, a in rows]
            bias = sum(p - a for p, (cp, mh, a) in zip(preds, rows)) / len(rows)
            mae = sum(abs(p - a) for p, (cp, mh, a) in zip(preds, rows)) / len(rows)
            if mae <= champ_mae + MAE_GUARD and abs(bias) < abs(best[1]):
                best = (lam, bias, mae)
        lam_fit[h] = best[0]
        dev_table[h] = {"n_star": len(rows), "lam": best[0],
                        "champ_bias": round(champ_bias, 4), "fit_bias": round(best[1], 4),
                        "champ_mae": round(champ_mae, 4), "fit_mae": round(best[2], 4)}

    # apply lam_fit on HOLDOUT; report star bias/MAE + pooled MAE (champion vs challenger)
    def _star_metrics(rows, lam_by_h, h):
        if not rows:
            return None
        lam = lam_by_h.get(h, 0.0)
        ch_bias = sum(cp - a for cp, mh, a in rows) / len(rows)
        ch_mae = sum(abs(cp - a) for cp, mh, a in rows) / len(rows)
        preds = [cp + lam * max(0.0, mh - cp) for cp, mh, a in rows]
        new_bias = sum(p - a for p, (cp, mh, a) in zip(preds, rows)) / len(rows)
        new_mae = sum(abs(p - a) for p, (cp, mh, a) in zip(preds, rows)) / len(rows)
        return {"n": len(rows), "lam": lam,
                "champ_bias": round(ch_bias, 4), "new_bias": round(new_bias, 4),
                "champ_mae": round(ch_mae, 4), "new_mae": round(new_mae, 4)}

    out = {"dev_bases": DEV_BASES, "holdout_bases": HOLDOUT_BASES,
           "lam_smh_fit": {str(h): lam_fit[h] for h in lam_fit},
           "dev_fit_table": {str(h): dev_table.get(h) for h in dev_table},
           "holdout_star": {}, "holdout_pooled": {}}

    # holdout star per-horizon
    for h in range(1, PM.HORIZONS + 1):
        m = _star_metrics(star["holdout"][h], lam_fit, h)
        if m:
            out["holdout_star"][str(h)] = m

    # pooled MAE (champion vs challenger) -- star rows lifted by their horizon lam,
    # every non-star row untouched (so the challenger can only move pooled via stars).
    for cohort in ("dev", "holdout"):
        ch_abs = new_abs = n = 0
        for h in range(1, PM.HORIZONS + 1):
            lam = lam_fit.get(h, 0.0)
            srows = star[cohort][h]
            # build a lookup of lifted value per star row by position
            lift_vals = [cp + lam * max(0.0, mh - cp) for cp, mh, a in srows]
            si = 0
            for cp, a, is_star in pooled[cohort][h]:
                ch_abs += abs(cp - a); n += 1
                if is_star:
                    new_abs += abs(lift_vals[si] - a); si += 1
                else:
                    new_abs += abs(cp - a)
        out["holdout_pooled" if cohort == "holdout" else "dev_pooled"] = {
            "n": n, "champ_mae": round(ch_abs / n, 4), "new_mae": round(new_abs / n, 4)}

    # star aggregate (holdout) with per-horizon lam
    sb_ch = sb_new = sm_ch = sm_new = sn = 0
    for h in range(1, PM.HORIZONS + 1):
        lam = lam_fit.get(h, 0.0)
        for cp, mh, a in star["holdout"][h]:
            p = cp + lam * max(0.0, mh - cp)
            sb_ch += (cp - a); sb_new += (p - a)
            sm_ch += abs(cp - a); sm_new += abs(p - a); sn += 1
    if sn:
        out["holdout_star_agg"] = {"n": sn,
            "champ_bias": round(sb_ch / sn, 4), "new_bias": round(sb_new / sn, 4),
            "champ_mae": round(sm_ch / sn, 4), "new_mae": round(sm_new / sn, 4)}

    art_p = ROOT / "data" / "proj_horizon_eval.json"
    art = json.loads(art_p.read_text(encoding="utf-8")) if art_p.exists() else {}
    art.setdefault("challenger_blocks", {})["star_mean_head"] = out
    art_p.write_text(json.dumps(art, indent=1), encoding="utf-8")

    print("\n=== lam_smh fit (dev):", out["lam_smh_fit"])
    sa = out.get("holdout_star_agg", {})
    print(f"HOLDOUT star: bias {sa.get('champ_bias')} -> {sa.get('new_bias')} | "
          f"MAE {sa.get('champ_mae')} -> {sa.get('new_mae')} (n={sa.get('n')})")
    hp = out["holdout_pooled"]
    print(f"HOLDOUT pooled MAE {hp['champ_mae']} -> {hp['new_mae']} (n={hp['n']})")
    print("wrote challenger_blocks.star_mean_head -> data/proj_horizon_eval.json")
    return out


if __name__ == "__main__":
    run()
