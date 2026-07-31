# SCRATCH part 2 (frontier: higher-power eFV evaluator).
# Two variance components the resampling bootstrap does not isolate:
#   A. RIDGE-SEED noise  - _fit_ridge picks alpha on a seeded holdout permutation; a candidate
#      and the baseline can land on different alphas for reasons unrelated to the candidate.
#   B. BETWEEN-COHORT noise - how much of the delta sd is cross-year (block) vs within-year.
#   C. Does averaging the evaluator over K ridge seeds actually shrink the delta sd by ~sqrt(K)?
# Read-only; monkeypatches the seed at RUNTIME only (no shipped file is edited).

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prospect_path as pp                      # noqa: E402
import _frontier_evalpower as fp                # noqa: E402

EV_FOCUS = ["EV0_current_gate", "EV1_hit_9origin", "EV5_both_9origin_blockrho",
            "EV7_both_9origin_cauc", "EV10_prodfit_testdeb", "EV11_prodfit_testfull"]


def eval_arms(pool, arms):
    return {a: fp.eval_all(fp.all_records(pool, fp.ARMS[a])) for a in arms}


def main():
    t0 = time.time()
    pool = fp.load_pool()
    arms = ("base", "noise", "prod_trend", "drop_peakk")
    base_seed = pp._RIDGE_HOLDOUT_SEED

    # ---------- A: ridge-seed noise (36 seeds) ----------
    NSEEDS = 36
    per_seed = []
    for i in range(NSEEDS):
        pp._RIDGE_HOLDOUT_SEED = 1000 + i
        per_seed.append(eval_arms(pool, arms))
        if (i + 1) % 6 == 0:
            print(f"[{time.time()-t0:.0f}s] seed {i+1}/{NSEEDS}", flush=True)
    pp._RIDGE_HOLDOUT_SEED = base_seed

    print("\n== A. RIDGE-SEED noise: sd of the point delta across 36 alpha-holdout seeds ==")
    print(f"{'evaluator':30s} {'cand':>11s} {'mean_d':>9s} {'sd_seed':>9s} {'sd_seed/K=8':>11s}")
    out = {"A_seed_noise": {}}
    for k in EV_FOCUS:
        for a in ("noise", "prod_trend", "drop_peakk"):
            d = np.array([s[a][k] - s["base"][k] for s in per_seed
                          if s[a][k] is not None and s["base"][k] is not None])
            sd = float(d.std(ddof=1))
            print(f"{k:30s} {a:>11s} {d.mean():>9.5f} {sd:>9.5f} {sd/np.sqrt(8):>11.5f}")
            out["A_seed_noise"].setdefault(k, {})[a] = {
                "mean": round(float(d.mean()), 5), "sd": round(sd, 5),
                "sd_if_averaged_over_8_seeds": round(sd / np.sqrt(8), 5)}

    # ---------- C: does seed-averaging shrink the delta sd? (6 groups of 6 seeds) ----------
    print("\n== C. seed-AVERAGED evaluator: sd of the K=6-averaged delta over 6 disjoint groups ==")
    print(f"{'evaluator':30s} {'cand':>11s} {'sd_1seed':>9s} {'sd_K6avg':>9s} {'shrink_x':>9s}")
    out["C_seed_averaging"] = {}
    for k in EV_FOCUS:
        for a in ("noise", "prod_trend"):
            d = np.array([s[a][k] - s["base"][k] for s in per_seed])
            g = d[:36].reshape(6, 6).mean(axis=1)
            sd1, sdk = float(d.std(ddof=1)), float(g.std(ddof=1))
            print(f"{k:30s} {a:>11s} {sd1:>9.5f} {sdk:>9.5f} "
                  f"{(sd1/sdk if sdk else float('nan')):>9.2f}")
            out["C_seed_averaging"].setdefault(k, {})[a] = {
                "sd_single_seed": round(sd1, 5), "sd_6seed_avg": round(sdk, 5),
                "shrink_x": round(sd1 / sdk, 2) if sdk else None}

    # ---------- B: between-cohort (block) bootstrap on the fixed production fits ----------
    print("\n== B. BLOCK (side,year) cluster bootstrap on fixed fits: between-cohort variance ==")
    recmaps = {a: fp.all_records(pool, fp.ARMS[a]) for a in arms}
    point = {a: fp.eval_all(recmaps[a]) for a in arms}
    rng = random.Random(11)
    B = 2000
    boot = {a: {k: [] for k in point["base"]} for a in arms}
    # pre-split every frame/side record list into (year -> rows)
    split = {a: {key: fp._blocks(recs) for key, recs in recmaps[a].items()} for a in arms}
    blockkeys = sorted({bk for key in split["base"] for bk in split["base"][key]})
    for _ in range(B):
        draw = [blockkeys[rng.randrange(len(blockkeys))] for _ in blockkeys]
        for a in arms:
            rm = {}
            for key, bl in split[a].items():
                rows = []
                for bk in draw:
                    if bk in bl:
                        rows.extend((bk[0], bk[1], x[0], x[1], x[2]) for x in bl[bk])
                rm[key] = rows
            r = fp.eval_all(rm)
            for k in r:
                boot[a][k].append(r[k])
    print(f"{'evaluator':30s} {'cand':>11s} {'delta':>9s} {'sd_block':>9s} {'p_gt0':>7s}")
    out["B_block_bootstrap"] = {}
    for k in EV_FOCUS:
        for a in ("noise", "prod_trend", "drop_peakk"):
            d = np.array([c - b for c, b in zip(boot[a][k], boot["base"][k])
                          if c is not None and b is not None])
            print(f"{k:30s} {a:>11s} {point[a][k]-point['base'][k]:>9.5f} "
                  f"{d.std(ddof=1):>9.5f} {(d>0).mean():>7.3f}")
            out["B_block_bootstrap"].setdefault(k, {})[a] = {
                "delta": round(point[a][k] - point["base"][k], 5),
                "sd": round(float(d.std(ddof=1)), 5),
                "p_gt0": round(float((d > 0).mean()), 3)}

    (ROOT / "tools" / "_frontier_out" / "_scratch_evalpower2.json").write_text(json.dumps(out, indent=1),
                                                            encoding="utf-8")
    print(f"\ndone [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()
