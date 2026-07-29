# SCRATCH: (c) ENSEMBLING and SERVED-NUMBER CHURN.
# Question: does averaging the ridge across alpha-holdout seeds / bootstrap resamples
# reduce the run-to-run movement of the SERVED eFV grade, and at what OOS cost?
# Churn is simulated by re-fitting the production stack on perturbed training pools
# (the analogue of a monthly rebuild whose labeled pool has shifted) and re-scoring
# the ACTUAL live board, then applying the shipped rank-preserving quantile map.
# Run: python tools/_frontier_shrink_c.py [R]
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontier_shrink import (LAM, BASE_KEYS, OUT, DATA, load_pool, train_rows,
                              fit_ridge_cfg, predict_many, _rank_np)
import efv_model as em
from prospect_path import _fit_linear_calibration

SH = {"mode": "shipped"}
F100 = {"mode": "fixed", "alpha": 100.0}
# arm -> (ridge cfg, lambda multiplier applied to the shipped per-side lambda)
ARMS = {
    "shipped":      (SH, 1.0),
    "fixed_10":     ({"mode": "fixed", "alpha": 10.0}, 1.0),
    "fixed_100":    (F100, 1.0),
    "fixed_300":    ({"mode": "fixed", "alpha": 300.0}, 1.0),
    "kfold5":       ({"mode": "kfold", "K": 5}, 1.0),
    "seedavg6":     ({"mode": "seedavg", "K": 6}, 1.0),
    "bag12":        ({"mode": "bag", "K": 12, "base": SH, "seed": 606}, 1.0),
    "bag48":        ({"mode": "bag", "K": 48, "base": F100, "seed": 606}, 1.0),
    "bag150":       ({"mode": "bag", "K": 150, "base": F100, "seed": 606}, 1.0),
    "lam_x0.82":    (SH, 0.8235),   # hit .85->.70
    "lam_x0.59":    (SH, 0.5882),   # hit .85->.50
    "lam_x0.41":    (SH, 0.4118),   # hit .85->.35
    "lam_x0.59_bag48": ({"mode": "bag", "K": 48, "base": F100, "seed": 606}, 0.5882),
}


def load_live():
    out = {}
    for side, fn in (("hit", "xfv_live_hitter_matrix.json"),
                     ("pit", "xfv_live_pitcher_matrix.json")):
        raw = json.loads((DATA / fn).read_text(encoding="utf-8"))
        rows = []
        for r in raw:
            if r.get("consensus_fv_raw") is None:
                continue
            rows.append({"player_key": r["player_key"], "feats": em._vec(r, side),
                         "fv": float(r["consensus_fv_raw"]), "side": side})
        out[side] = rows
    return out


def serve(train, live, side, cfg, lam_mult=1.0):
    """One production-analogue run -> {player_key: (rank_war, display_grade)}."""
    keys = BASE_KEYS[side]
    ridge = fit_ridge_cfg(train, keys, cfg)
    ols = em._fit_ols_fv(train)
    if not (ridge and ols):
        return None, None
    raw_tr = predict_many(ridge, train)
    c = _fit_linear_calibration(list(zip(raw_tr.tolist(), [r["target"] for r in train])))
    a, b = (c["a"], c["b"]) if c else (0.0, 1.0)
    raw = predict_many(ridge, live)
    lam = LAM[side] * lam_mult
    rw = np.array([(1 - lam) * max(0.0, em._pred_ols(ols, r["fv"]))
                   + lam * max(-2.0, a + b * float(p)) for r, p in zip(live, raw)])
    # shipped rank-preserving quantile map onto this pool's consensus FV distribution
    target = np.sort(np.array([r["fv"] for r in live], dtype=float))
    m = len(live)
    order = np.argsort(rw, kind="mergesort")
    disp = np.empty(m)
    for pos, i in enumerate(order):
        p = pos / (m - 1) if m > 1 else 0.0
        x = p * (m - 1)
        lo = int(x); hi = min(m - 1, lo + 1); frac = x - lo
        disp[i] = target[lo] * (1 - frac) + target[hi] * frac
    return rw, np.round(disp, 1), (ridge.get("alpha"))


def perturb(rows, rng, mode, frac=0.10):
    if mode == "drop":
        keep = [r for r in rows if rng.random() > frac]
        return keep
    if mode == "boot":
        return [rows[rng.randrange(len(rows))] for _ in rows]
    raise ValueError(mode)


def main(R=40):
    t0 = time.time()
    pool = load_pool()
    live = load_live()
    tr = {s: train_rows(pool[s]) for s in ("hit", "pit")}
    print("train pool", {s: len(v) for s, v in tr.items()},
          "live board", {s: len(v) for s, v in live.items()}, flush=True)

    # reference run (unperturbed) per arm
    ref = {}
    for nm, (cfg, lm) in ARMS.items():
        ref[nm] = {}
        for s in ("hit", "pit"):
            rw, dg, al = serve(tr[s], live[s], s, cfg, lm)
            ref[nm][s] = (rw, dg, al)
        print(f"  ref {nm:14s} alpha hit={ref[nm]['hit'][2]} pit={ref[nm]['pit'][2]} "
              f"mean_disp hit={ref[nm]['hit'][1].mean():.2f}", flush=True)

    results = {}
    for pmode in ("drop", "boot"):
        runs = {nm: {s: [] for s in ("hit", "pit")} for nm in ARMS}
        alphas = {nm: {s: [] for s in ("hit", "pit")} for nm in ARMS}
        rng = random.Random(777)
        for i in range(R):
            pert = {s: perturb(tr[s], rng, pmode) for s in ("hit", "pit")}
            for nm, (cfg, lm) in ARMS.items():
                for s in ("hit", "pit"):
                    rw, dg, al = serve(pert[s], live[s], s, cfg, lm)
                    runs[nm][s].append(dg)
                    alphas[nm][s].append(al)
            if (i + 1) % 10 == 0:
                print(f"[{time.time()-t0:.0f}s] {pmode} run {i+1}/{R}", flush=True)

        print(f"\n== CHURN in the SERVED display grade, perturbation={pmode} "
              f"({'drop 10% of labeled pool' if pmode=='drop' else 'bootstrap the labeled pool'}), "
              f"R={R} runs ==")
        print(f"{'arm':14s} {'sd_grade':>9s} {'mad_pair':>9s} {'p|d|>0.5':>9s} "
              f"{'p|d|>1.0':>9s} {'max_sd':>8s} {'sd_vs_ref':>10s} {'alpha_flips':>12s}")
        res = {}
        for nm in ARMS:
            per_side = {}
            for s in ("hit", "pit"):
                M = np.vstack(runs[nm][s])                 # R x n_live
                sd = M.std(axis=0, ddof=1)
                # pairwise consecutive-run movement (what a user sees between rebuilds)
                dpair = np.abs(np.diff(M, axis=0))
                per_side[s] = {
                    "sd_grade": float(sd.mean()),
                    "max_sd": float(sd.max()),
                    "mad_pair": float(dpair.mean()),
                    "p_gt_05": float((dpair >= 0.5).mean()),
                    "p_gt_10": float((dpair >= 1.0).mean()),
                    "sd_vs_ref": float(np.abs(M - ref[nm][s][1]).mean()),
                    "n_live": int(M.shape[1]),
                }
            w = {s: per_side[s]["n_live"] for s in per_side}
            tot = sum(w.values())
            agg = {k: sum(per_side[s][k] * w[s] for s in per_side) / tot
                   for k in ("sd_grade", "mad_pair", "p_gt_05", "p_gt_10", "sd_vs_ref")}
            agg["max_sd"] = max(per_side[s]["max_sd"] for s in per_side)
            av = [a for s in ("hit", "pit") for a in alphas[nm][s] if a is not None]
            nflip = (len(set(av)) if av else 0)
            res[nm] = {"both": agg, "hit": per_side["hit"], "pit": per_side["pit"],
                       "distinct_alphas": nflip,
                       "alpha_values": sorted(set(round(float(a), 3) for a in av)) if av else []}
            print(f"{nm:14s} {agg['sd_grade']:>9.4f} {agg['mad_pair']:>9.4f} "
                  f"{agg['p_gt_05']:>9.4f} {agg['p_gt_10']:>9.4f} {agg['max_sd']:>8.3f} "
                  f"{agg['sd_vs_ref']:>10.4f} {str(res[nm]['alpha_values']):>12s}")
        results[pmode] = res

    out = {"R": R, "arms": {k: str(v) for k, v in ARMS.items()},
           "live_n": {s: len(v) for s, v in live.items()},
           "train_n": {s: len(v) for s, v in tr.items()},
           "churn": results}
    (OUT / "_scratch_shrink_c.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote", OUT / "_scratch_shrink_c.json", f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(R=int(sys.argv[1]) if len(sys.argv) > 1 else 40)
