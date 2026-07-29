"""Full gate run for the biometric lane: per-fold stability, paired bootstrap
(resample train AND test, refit every draw), row-permuted zero-information twin,
and a permutation null band. Writes tools/_arch_bio_result.json."""
import sys, json, time
import numpy as np
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools")
import _arch_bio_gate as G

B_BOOT = int(sys.argv[1]) if len(sys.argv) > 1 else 600
B_PERM = int(sys.argv[2]) if len(sys.argv) > 2 else 200
KINDS = ("bmi", "linear", "frame", "arch_inter", "arch_strat")
MDE = {"hit": 0.017, "pit": 0.016}

out = {"protocol": {
    "pool": "efv_lab_runner.data_for(side) debuted rows; forward-chained folds "
            + str(G.FOLDS_EXT),
    "bio_source": "dated FanGraphs board archives, vintage STRICTLY <= row cutoff",
    "n_boot": B_BOOT, "n_perm": B_PERM,
    "mde95_pooled_rho": MDE,
    "encoding": "train-fold z-score, missing -> train mean + explicit missing "
                "indicator (never encoded as an extreme value)"}, "sides": {}}

for side in ("hit", "pit"):
    rows = G.load(side)
    nb = sum(1 for r in rows if r["bio"]["bmi"] is not None)
    nf = sum(1 for r in rows if r["bio"]["frame"] is not None)
    S = {"pool_n": len(rows), "bmi_cov": round(nb / len(rows), 4),
         "frame_cov": round(nf / len(rows), 4), "variants": {}}
    base = G.evaluate(rows, "none", side, per_fold=True)
    S["baseline"] = base
    print("== %s base rho=%.4f n=%d  (bmi cov %.1f%%, frame cov %.1f%%)"
          % (side, base["rho"], base["n"], 100 * nb / len(rows), 100 * nf / len(rows)))

    years = sorted({r["decision_year"] for r in rows})
    by_year = {y: [r for r in rows if r["decision_year"] == y] for y in years}

    for kind in KINDS:
        t0 = time.time()
        cand = G.evaluate(rows, kind, side, per_fold=True)
        d_rho = cand["rho"] - base["rho"]
        d_t45 = cand["t45"] - base["t45"]

        # per-fold sign stability
        pf = {y: round(cand["per_fold"][y][0] - base["per_fold"][y][0], 4)
              for y in cand["per_fold"] if y in base["per_fold"]}
        n_pos = sum(1 for v in pf.values() if v > 0)

        # ---- zero-information twin (single draw, matched marginals) ----
        rng = np.random.default_rng(12345)
        perm_deltas = []
        for _ in range(B_PERM):
            pr = G.permute_bio(rows, rng)
            c = G.evaluate(pr, kind, side)
            if c:
                perm_deltas.append(c["rho"] - base["rho"])
        perm_deltas = np.array(perm_deltas)
        p_perm = float((perm_deltas >= d_rho).mean()) if len(perm_deltas) else float("nan")

        # ---- paired bootstrap: resample the POOL (train and test), refit both arms ----
        rng2 = np.random.default_rng(777)
        boot = []
        for _ in range(B_BOOT):
            res = []
            for y in years:                       # stratified by decision year
                g = by_year[y]
                idx = rng2.integers(0, len(g), len(g))
                res.extend(g[i] for i in idx)
            b0 = G.evaluate(res, "none", side)
            b1 = G.evaluate(res, kind, side)
            if b0 and b1:
                boot.append(b1["rho"] - b0["rho"])
        boot = np.array(boot)
        lo, hi = (float(np.quantile(boot, .025)), float(np.quantile(boot, .975))) \
            if len(boot) else (float("nan"),) * 2
        p_improve = float((boot > 0).mean()) if len(boot) else float("nan")

        v = {"rho": round(cand["rho"], 4), "d_rho": round(d_rho, 4),
             "d_t45": round(d_t45, 4),
             "within_tier_wm": round(cand["within_tier_wm"], 4),
             "per_fold_d": pf, "folds_positive": "%d/%d" % (n_pos, len(pf)),
             "boot_ci95": [round(lo, 4), round(hi, 4)],
             "boot_p_improve": round(p_improve, 3),
             "perm_null_p95": round(float(np.quantile(perm_deltas, .95)), 4),
             "perm_null_mean": round(float(perm_deltas.mean()), 4),
             "p_vs_perm_null": round(p_perm, 3),
             "mde95": MDE[side],
             "verdict": ("NULL (below MDE95)" if abs(d_rho) < MDE[side]
                         else ("candidate" if d_rho > 0 else "regression"))}
        S["variants"][kind] = v
        print("  %-11s d_rho=%+.4f  CI95[%+.4f,%+.4f] P(imp)=%.3f  permP95=%+.4f "
              "p_perm=%.3f  folds+=%s  %s  (%.0fs)"
              % (kind, d_rho, lo, hi, p_improve, v["perm_null_p95"], p_perm,
                 v["folds_positive"], v["verdict"], time.time() - t0))
    out["sides"][side] = S

json.dump(out, open("tools/_arch_bio_result.json", "w"), indent=1)
print("wrote tools/_arch_bio_result.json")
