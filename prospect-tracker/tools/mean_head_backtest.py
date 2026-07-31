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

--------------------------------------------------------------------------------
W-STAR STAR-SLICE VARIANT (registered docs/efv-2026-07-24/GATES.md, one attempt,
marginal = FAIL; frozen here BEFORE the run):

  MECHANISM (zero new fitted parameters): star rows (the EX-ANTE star slice,
  base-year WAR >= 4 == the star_l1 feature proj_ml's star top-up gates on)
  take the SAME shipped recenter machinery (_point: lift-only global MEAN_LAM,
  then the STAR_LAM top-up) with the TARGET swapped implied-mean -> dedicated
  objective=regression mean head, at every horizon. Non-star rows are the
  champion path unchanged (so pooled can only move through the star rows).
  This is the mh_same treatment RESTRICTED to the star slice, i.e. the exact
  "star-slice-ONLY mean head (all horizons)" the 2026-06-29 ledger named
  unexplored. Live seam: proj_ml.predict_path behind EEPHUS_STAR_MEAN_HEAD
  (call-time read, default OFF, OFF path byte-identical).

  PRIOR-ART DISTINCTION: challenger_blocks.star_mean_head (2026-06-29,
  tools/star_mean_head_backtest.py) tested a DIFFERENT arm: an ADDITIONAL
  fitted-lambda lift on top of the fully-lifted champion point, under a
  star-MAE +0.02 guard; the dev fit pinned to ~zero lambda. It never tested
  the target swap, and it is not in the plan's closed-lane appendix; the plan
  Phase-6 table registers THIS arm ("mean_head_backtest", now).

  FROZEN GATE THRESHOLDS (GATES.md W-STAR bars, operationalized a priori):
    A. star bias improves on dev AND holdout: |star_bias_new| < |star_bias_champ|
       on the pooled star aggregate per cohort (strict; equality = marginal = FAIL).
    B. pooled MAE not worse than +0.005 on dev AND holdout:
       pooled_mae_new <= pooled_mae_champ + 0.005 per cohort.
  A-priori risk recorded from the 2026-06-29 ledger: dev champion star bias sat
  near zero (+0.065; the shipped lambdas were FIT on dev), so clause A's dev leg
  is expected to be the binding one. That is the gate doing its job, not a
  reason to amend it.

  REPORTED-ONLY (never gating): player-clustered bootstrap CIs (2000 reps, seed
  20260724) on the holdout star-bias delta and pooled-MAE delta. No other
  sampling exists in this harness; the LGBM heads keep the shipped
  deterministic seed via PM._params_for.

  Protocol otherwise IDENTICAL to run() above: forward-chained heads, dev
  bases 2017-2021, touch-once holdout 2022-2024, absent-season actual = 0,
  same-run champion baseline.

Run: python tools/mean_head_backtest.py --star-slice
     (merges challenger_blocks.star_slice_mean_head, preserving all blocks)
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
    print("\n=== HOLDOUT (pooled) - champion vs mean-head variants ===")
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


# ---------------------------------------------------------------------------
# W-STAR star-slice variant (frozen in the header above; one attempt).
SS_POOLED_MAE_TOL = 0.005      # clause B tolerance, per cohort
SS_BOOT_REPS = 2000            # reported-only bootstrap
SS_BOOT_SEED = 20260724        # gate default seed (sampling exists only here)
SS_BLOCK_KEY = "star_slice_mean_head"


def run_star_slice():
    corpus = fp.build_corpus()
    last_complete = corpus["last"] - 1
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

    # rows[cohort][h] = list of (mlbam, side, base, champ, new, act, is_star)
    rows = {c: {h: [] for h in range(1, PM.HORIZONS + 1)} for c in ("dev", "holdout")}

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
                    hq = {q: LGBMRegressor(alpha=q, **PM._params_for(h)).fit(X, y)
                          for q in QS}
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
                        act = war_actual.get((mlbam, target), 0.0)
                        champ = _point(q50, imp, h, is_star)
                        if is_star:
                            mh = float(hq["mean"].predict(x)[0])
                            new = _point(q50, mh, h, is_star)
                        else:
                            new = champ
                        rows[cohort][h].append((mlbam, side, B, champ, new, act, is_star))
            print(f"  done base {B}", flush=True)

    def _cohort_summary(c):
        allr = [r for h in range(1, PM.HORIZONS + 1) for r in rows[c][h]]
        n = len(allr)
        champ_mae = sum(abs(ch - a) for _, _, _, ch, nw, a, _ in allr) / n
        new_mae = sum(abs(nw - a) for _, _, _, ch, nw, a, _ in allr) / n
        st = [r for r in allr if r[6]]
        ns = len(st)
        s_champ_bias = sum(ch - a for _, _, _, ch, nw, a, _ in st) / ns
        s_new_bias = sum(nw - a for _, _, _, ch, nw, a, _ in st) / ns
        s_champ_mae = sum(abs(ch - a) for _, _, _, ch, nw, a, _ in st) / ns
        s_new_mae = sum(abs(nw - a) for _, _, _, ch, nw, a, _ in st) / ns
        per_h = {}
        for h in range(1, PM.HORIZONS + 1):
            sh = [r for r in rows[c][h] if r[6]]
            if not sh:
                continue
            per_h[str(h)] = {
                "n_star": len(sh),
                "champ_bias": round(sum(ch - a for _, _, _, ch, nw, a, _ in sh) / len(sh), 4),
                "new_bias": round(sum(nw - a for _, _, _, ch, nw, a, _ in sh) / len(sh), 4),
                "champ_mae": round(sum(abs(ch - a) for _, _, _, ch, nw, a, _ in sh) / len(sh), 4),
                "new_mae": round(sum(abs(nw - a) for _, _, _, ch, nw, a, _ in sh) / len(sh), 4)}
        return {
            "pooled": {"n": n, "champ_mae": round(champ_mae, 4),
                       "new_mae": round(new_mae, 4),
                       "mae_delta": round(new_mae - champ_mae, 4)},
            "star": {"n": ns, "champ_bias": round(s_champ_bias, 4),
                     "new_bias": round(s_new_bias, 4),
                     "champ_mae": round(s_champ_mae, 4),
                     "new_mae": round(s_new_mae, 4)},
            "star_per_h": per_h}

    summ = {c: _cohort_summary(c) for c in ("dev", "holdout")}

    # frozen clauses (header): A strict |bias| improvement, B pooled MAE tolerance
    clause_a = {c: abs(summ[c]["star"]["new_bias"]) < abs(summ[c]["star"]["champ_bias"])
                for c in ("dev", "holdout")}
    clause_b = {c: summ[c]["pooled"]["new_mae"]
                <= summ[c]["pooled"]["champ_mae"] + SS_POOLED_MAE_TOL
                for c in ("dev", "holdout")}
    passed = all(clause_a.values()) and all(clause_b.values())

    # reported-only player-clustered bootstrap (holdout): star-bias delta + pooled
    # MAE delta, resampling PLAYERS with replacement.
    rng = np.random.default_rng(SS_BOOT_SEED)
    hold = [r for h in range(1, PM.HORIZONS + 1) for r in rows["holdout"][h]]
    by_pl = {}
    for r in hold:
        by_pl.setdefault(r[0], []).append(r)
    players = sorted(by_pl)
    bias_d, mae_d = [], []
    for _ in range(SS_BOOT_REPS):
        pick = rng.choice(len(players), size=len(players), replace=True)
        sb = sn = ma = mn = 0.0
        cnt = 0
        for i in pick:
            for _, _, _, ch, nw, a, s in by_pl[players[i]]:
                ma += abs(ch - a); mn += abs(nw - a); cnt += 1
                if s:
                    sb += (ch - a); sn += (nw - a)
        stars = sum(1 for i in pick for r in by_pl[players[i]] if r[6])
        if stars and cnt:
            bias_d.append((sn / stars) - (sb / stars))
            mae_d.append((mn / cnt) - (ma / cnt))
    boot = {"reps": SS_BOOT_REPS, "seed": SS_BOOT_SEED,
            "star_bias_delta_ci95": [round(float(np.percentile(bias_d, 2.5)), 4),
                                     round(float(np.percentile(bias_d, 97.5)), 4)],
            "pooled_mae_delta_ci95": [round(float(np.percentile(mae_d, 2.5)), 4),
                                      round(float(np.percentile(mae_d, 97.5)), 4)]}

    # example holdout star rows, largest |new - champ|
    star_hold = [r for r in hold if r[6]]
    star_hold.sort(key=lambda r: -abs(r[4] - r[3]))
    examples = [{"mlbam": int(m), "side": sd, "base": b,
                 "champ": round(ch, 3), "new": round(nw, 3), "actual": round(a, 2)}
                for m, sd, b, ch, nw, a, _ in star_hold[:8]]

    verdict = (
        f"{'PASS' if passed else 'FAIL'} 2026-07-24 (W-STAR, one attempt, frozen "
        f"thresholds in tools/mean_head_backtest.py header): star-slice-only "
        f"mean-head recenter (target swap, shipped lambdas, all horizons; non-star "
        f"rows untouched). Clause A |star bias| improves: dev "
        f"{summ['dev']['star']['champ_bias']} -> {summ['dev']['star']['new_bias']} "
        f"({'ok' if clause_a['dev'] else 'FAIL'}), holdout "
        f"{summ['holdout']['star']['champ_bias']} -> {summ['holdout']['star']['new_bias']} "
        f"({'ok' if clause_a['holdout'] else 'FAIL'}). Clause B pooled MAE within "
        f"+{SS_POOLED_MAE_TOL}: dev {summ['dev']['pooled']['champ_mae']} -> "
        f"{summ['dev']['pooled']['new_mae']} ({'ok' if clause_b['dev'] else 'FAIL'}), "
        f"holdout {summ['holdout']['pooled']['champ_mae']} -> "
        f"{summ['holdout']['pooled']['new_mae']} "
        f"({'ok' if clause_b['holdout'] else 'FAIL'}). Prior art: distinct from "
        f"challenger_blocks.star_mean_head (additional fitted-lambda top-up, "
        f"2026-06-29); this arm is the target-swap variant that ledger named "
        f"unexplored. Live seam: proj_ml.predict_path EEPHUS_STAR_MEAN_HEAD "
        f"(default OFF, OFF path byte-identical, inert on quantile-only bundles).")

    out = {"registered": "docs/efv-2026-07-24/GATES.md W-STAR",
           "dev_bases": DEV_BASES, "holdout_bases": HOLDOUT_BASES,
           "mechanism": "star rows: _point target implied-mean -> mean head "
                        "(shipped MEAN_LAM + STAR_LAM, lift-only + top-up); "
                        "non-star rows: champion unchanged",
           "clauses": {"A_star_bias_improves": clause_a,
                       "B_pooled_mae_tol": {"tol": SS_POOLED_MAE_TOL, **clause_b}},
           "dev": summ["dev"], "holdout": summ["holdout"],
           "holdout_bootstrap_reported_only": boot,
           "examples_holdout_star": examples,
           "verdict": verdict}

    # read-modify-write MERGE (this artifact has key-collision history: never
    # rebuild the dict, never touch sibling blocks)
    art_p = ROOT / "data" / "proj_horizon_eval.json"
    art = json.loads(art_p.read_text(encoding="utf-8")) if art_p.exists() else {}
    pre_keys = set(art.get("challenger_blocks", {}))
    art.setdefault("challenger_blocks", {})[SS_BLOCK_KEY] = out
    assert pre_keys <= set(art["challenger_blocks"]), "sibling block lost"
    art_p.write_text(json.dumps(art, indent=1), encoding="utf-8")

    print("\n=== W-STAR star-slice mean head ===")
    for c in ("dev", "holdout"):
        s = summ[c]
        print(f"  {c:>7}: star bias {s['star']['champ_bias']:+.4f} -> "
              f"{s['star']['new_bias']:+.4f} | star MAE {s['star']['champ_mae']:.4f} -> "
              f"{s['star']['new_mae']:.4f} (n_star={s['star']['n']}) | pooled MAE "
              f"{s['pooled']['champ_mae']:.4f} -> {s['pooled']['new_mae']:.4f} "
              f"(n={s['pooled']['n']})")
    print(f"  bootstrap (holdout, reported-only): star-bias delta CI95 "
          f"{boot['star_bias_delta_ci95']}, pooled-MAE delta CI95 "
          f"{boot['pooled_mae_delta_ci95']}")
    print(f"  VERDICT: {'PASS' if passed else 'FAIL'}")
    print(f"wrote challenger_blocks.{SS_BLOCK_KEY} -> data/proj_horizon_eval.json")
    return out


if __name__ == "__main__":
    if "--star-slice" in sys.argv[1:]:
        run_star_slice()
    else:
        run()
