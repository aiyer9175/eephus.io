# SCRATCH part 3 of the POOLED-MODEL lane. Read-only wrt shipped modules.
#   (D) CROSS-FOLD: per (side, origin) delta over all available origins, mean/se/sign counts
#   (E) TRAIN-SIZE SWEEP: subsample the training pool 20/40/60/80/100% -- does pooling help
#       when the per-side fit is data-STARVED? (tests the lane's premise that n binds)
#   (F) ENDPOINT BOOTSTRAP on the clean continuum: p6 dev->0 (separate) vs dev->inf (pooled)
# Run: python tools/_frontier_pooled3.py     (FP3_MODE=def, FP3_B draws default 400)

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _frontier_pooled as fp                      # noqa: E402
from _frontier_pooled2 import score_pinned         # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"
ORIGINS_ALL = tuple(range(2016, 2025))


def fold_rhos(recs):
    """{(side, origin): spearman} plus n."""
    b = {}
    for s, y, p, t, fv in recs:
        b.setdefault((s, y), []).append((p, t))
    return {k: (fp.rho([x[0] for x in g], [x[1] for x in g]), len(g))
            for k, g in b.items() if len(g) >= 15}


def subsample_train(pool, frac, rng):
    """Thin the TRAIN pool only (test rows are debuted; keep them all)."""
    out = {"hit": [], "pit": []}
    for side in ("hit", "pit"):
        keep_test, rest = [], []
        for r in pool[side]:
            (keep_test if r["kind"] == "debuted" else rest).append(r)
        # thin busts AND the older debuted rows that act as train; test rows are selected
        # by decision_year later, so thin uniformly and keep every row that can be a test row
        # in the scored origins.
        idx = rng.random(len(rest)) < frac
        thin_rest = [r for r, k in zip(rest, idx) if k]
        td = [r for r in keep_test if r["decision_year"] in fp.ORIGINS_REC]
        old = [r for r in keep_test if r["decision_year"] not in fp.ORIGINS_REC]
        idx2 = rng.random(len(old)) < frac
        out[side] = thin_rest + td + [r for r, k in zip(old, idx2) if k]
    return out


def main():
    t0 = time.time()
    mode = os.environ.get("FP3_MODE", "def")
    pool = fp.load_pool()
    res = {}

    # ------------------------------------------------------------- (D) cross-fold
    if "d" in mode:
        print("=== (D) CROSS-FOLD deltas, all origins %s, per (side, origin) Spearman ===" % (ORIGINS_ALL,))
        base = fold_rhos(fp.score(pool, "sep", origins=ORIGINS_ALL))
        D = {}
        for arm, kw in (("p1", {}), ("p4", {}), ("p6_sep(dev0.001)", {"dev": 0.001}),
                        ("p6_pooled(dev1e4)", {"dev": 1e4})):
            if "dev" in kw:
                recs = score_pinned(pool, "p6", 100.0, dev_mult=kw["dev"])
            else:
                recs = fp.score(pool, arm, origins=ORIGINS_ALL)
            fr = fold_rhos(recs)
            rows = []
            for k in sorted(set(base) & set(fr)):
                rows.append((k, fr[k][0] - base[k][0], base[k][1]))
            d = np.array([r[1] for r in rows])
            pos = int((d > 0).sum())
            print(" %-20s folds=%d mean %+0.4f se %0.4f t=%+0.2f signs %d+/%d-"
                  % (arm, len(d), d.mean(), d.std(ddof=1) / np.sqrt(len(d)),
                     d.mean() / (d.std(ddof=1) / np.sqrt(len(d))), pos, len(d) - pos))
            for k, dv, n in rows:
                print("      %s %d  n=%3d  d_rho %+0.4f" % (k[0], k[1], n, dv))
            D[arm] = {"folds": [[list(k), float(dv), int(n)] for k, dv, n in rows]}
        res["crossfold"] = D
        print("   (%.0fs)" % (time.time() - t0), flush=True)

    # ------------------------------------------------------------- (E) train-size sweep
    if "e" in mode:
        R = int(os.environ.get("FP3_R", "24"))
        print("\n=== (E) TRAIN-SIZE SWEEP: is pooling a data-starvation remedy? "
              "(%d reps per fraction, paired within rep) ===" % R)
        print("frac  n_train  d(p1-sep) block_rho   d(p6pool-p6sep) block_rho   "
              "d(p1-sep) rho_hit   d(p1-sep) rho_pit")
        E = {}
        for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
            rng = np.random.default_rng(fp.SEED + 31)
            acc = {"p1": [], "p6": [], "hit": [], "pit": [], "n": []}
            reps = 1 if frac >= 1.0 else R
            for _ in range(reps):
                sp = subsample_train(pool, frac, rng) if frac < 1.0 else pool
                ms = fp.metrics(fp.score(sp, "sep"))
                mp = fp.metrics(fp.score(sp, "p1"))
                a = fp.metrics(score_pinned(sp, "p6", 100.0, dev_mult=0.001))
                b = fp.metrics(score_pinned(sp, "p6", 100.0, dev_mult=1e4))
                acc["p1"].append(mp["block_rho"] - ms["block_rho"])
                acc["p6"].append(b["block_rho"] - a["block_rho"])
                acc["hit"].append(mp["rho_hit"] - ms["rho_hit"])
                acc["pit"].append(mp["rho_pit"] - ms["rho_pit"])
                acc["n"].append(len([r for r in sp["hit"] + sp["pit"]
                                     if r["decision_year"] < 2024
                                     and not (r["kind"] == "bust" and r["bust_recent"])]))
            E["%g" % frac] = {k: [float(x) for x in v] for k, v in acc.items()}
            print("%-5g %7d  %+0.4f (sd %0.4f)   %+0.4f (sd %0.4f)   %+0.4f   %+0.4f"
                  % (frac, int(np.mean(acc["n"])), np.mean(acc["p1"]),
                     np.std(acc["p1"], ddof=1) if reps > 1 else 0.0,
                     np.mean(acc["p6"]), np.std(acc["p6"], ddof=1) if reps > 1 else 0.0,
                     np.mean(acc["hit"]), np.mean(acc["pit"])))
        res["trainsize"] = E
        print("   (%.0fs)" % (time.time() - t0), flush=True)

    # ------------------------------------------------------------- (F) endpoint bootstrap
    if "f" in mode:
        B = int(os.environ.get("FP3_B", "400"))
        print("\n=== (F) ENDPOINT PAIRED BOOTSTRAP on the clean continuum (B=%d) ===" % B)
        print("    arms: p6 dev=0.001 (two separate coefficient sets) vs p6 dev=1e4 (fully shared)")
        print("    plus sep (shipped two-model config) as the reference")
        rng = np.random.default_rng(fp.SEED + 99)
        MK = ["rho_hit", "rho_pit", "mae_hit", "mae_pit", "block_rho", "cauc", "t45_hit", "t45_pit"]
        acc = {a: {k: [] for k in MK} for a in ("sep", "p6sep", "p6pool", "p1")}

        def run(p):
            return {"sep": fp.metrics(fp.score(p, "sep")),
                    "p1": fp.metrics(fp.score(p, "p1")),
                    "p6sep": fp.metrics(score_pinned(p, "p6", 100.0, dev_mult=0.001)),
                    "p6pool": fp.metrics(score_pinned(p, "p6", 100.0, dev_mult=1e4))}

        pt = run(pool)
        for bi in range(B):
            m = run(fp.resample(pool, rng))
            for a in acc:
                for k in MK:
                    acc[a][k].append(m[a].get(k, float("nan")))
            if (bi + 1) % 50 == 0:
                print("  boot %d/%d %.0fs" % (bi + 1, B, time.time() - t0), flush=True)
        F = {}
        for lbl, a, b in (("p6pool - p6sep", "p6pool", "p6sep"),
                          ("p1 - sep", "p1", "sep"),
                          ("p6sep - sep", "p6sep", "sep")):
            print("-- %s" % lbl)
            F[lbl] = {}
            for k in MK:
                s = fp.summ(np.array(acc[a][k]) - np.array(acc[b][k]))
                if not s:
                    continue
                F[lbl][k] = s
                print("   %-9s point %+0.4f | mean %+0.4f sd %0.5f CI95 [%+0.4f,%+0.4f] "
                      "P(>0)=%.3f MDE95 %0.4f"
                      % (k, pt[a].get(k, float("nan")) - pt[b].get(k, float("nan")),
                         s["mean"], s["sd"], s["lo"], s["hi"], s["p_gt0"], 1.645 * s["sd"]))
        print("\n arm-level sd:")
        for a in acc:
            print("   %-7s block_rho sd %0.5f  rho_hit sd %0.5f  rho_pit sd %0.5f"
                  % (a, fp.summ(acc[a]["block_rho"])["sd"], fp.summ(acc[a]["rho_hit"])["sd"],
                     fp.summ(acc[a]["rho_pit"])["sd"]))
        res["endpoint"] = {"point": pt, "boot": F, "B": B,
                           "armsd": {a: {k: fp.summ(acc[a][k]) for k in MK} for a in acc}}

    json.dump(res, open(OUT / "_scratch_pooled3.json", "w"), indent=1, default=float)
    print("\ntotal %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
