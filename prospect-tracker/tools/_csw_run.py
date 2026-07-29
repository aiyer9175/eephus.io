# SCRATCH (cswpitch lane) runner. Stages:
#   desc  - coverage + collinearity of csw_rel/swstr_rel with the shipped k_rel block
#   point - point-estimate deltas for every arm, incl. the zero-information controls
#   perm  - permutation null band for the same delta (N independent permutations)
#   boot  - paired bootstrap (resamples TRAIN and TEST, refits every arm each draw)
#   sub   - the differentiated hypothesis: does the gain concentrate on THIN samples
#           and on the low levels?
#
# PRE-REGISTERED GATE (written before any real csw_rel value existed; the crawl was
# still running). Primary statistic = delta pooled Spearman on the 4-fold gate window
# 2020-2023 under the production fit config, arm `add_csw` minus `base`.
# SHIP requires ALL FIVE:
#   1. d_point >= +0.016   (docs/EFV_GATE_STANDARD.md pitcher incremental-feature MDE95)
#   2. paired-bootstrap CI95 lower bound > 0
#   3. d_point > the p95 of the within-matched permutation null band
#   4. >= 4 of the 6 forward-chained folds non-negative AND cross-fold mean > 0
#   5. the zero-information twin's delta < half the candidate's delta
# Anything short of all five is a NULL and is reported as a null. The subgroup cuts
# (thin exposure, low levels) are EXPLORATORY: they are reported with the same
# machinery but a subgroup result cannot ship on its own.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _csw_lab as L                                            # noqa: E402

OUT = L.OUT
G = L.GATE_ORIGINS
ALL = L.ORIGINS


def _pearson(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _spear(a, b):
    return L.rho(np.asarray(a, float), np.asarray(b, float))


def desc(D):
    m = D["matched"]
    hm = D["has_milb"]
    print(f"rows={D['n']}  has_milb={int(hm.sum())}  csw_matched={int(m.sum())} "
          f"({m.sum()/max(int(hm.sum()),1):.1%} of milb rows)")
    ix = D["idx"]
    k = D["X"][:, ix["k_rel"]]
    pk = D["X"][:, ix["peak_k_rel"]]
    er = D["X"][:, ix["era_rel"]] if "era_rel" in ix else None
    out = {"n_rows": int(D["n"]), "n_has_milb": int(hm.sum()),
           "n_csw_matched": int(m.sum())}
    print("\n-- collinearity on the MATCHED pool (n=%d) --" % int(m.sum()))
    for nm, col in (("csw_rel", D["csw"]), ("swstr_rel", D["swstr"])):
        for on, oc in (("k_rel", k), ("peak_k_rel", pk)):
            p = _pearson(col[m], oc[m]); s = _spear(col[m], oc[m])
            out[f"{nm}_vs_{on}_pearson"] = round(p, 4)
            out[f"{nm}_vs_{on}_spearman"] = round(s, 4) if s == s else None
            print(f"   {nm:10s} vs {on:12s} pearson {p:+.3f}   spearman {s:+.3f}")
    p = _pearson(D["csw"][m], D["swstr"][m])
    out["csw_vs_swstr_pearson"] = round(p, 4)
    print(f"   csw_rel    vs swstr_rel   pearson {p:+.3f}")
    # residual information: what is left of csw_rel after projecting out the shipped
    # K-rate block? If this is tiny there is nothing new to add, by construction.
    A = np.column_stack([np.ones(int(m.sum())), k[m], pk[m]])
    for nm, col in (("csw_rel", D["csw"]), ("swstr_rel", D["swstr"])):
        coef, *_ = np.linalg.lstsq(A, col[m], rcond=None)
        resid = col[m] - A @ coef
        r2 = 1.0 - resid.var() / col[m].var() if col[m].var() > 0 else float("nan")
        out[f"{nm}_r2_on_krel_block"] = round(float(r2), 4)
        print(f"   R^2({nm} ~ k_rel + peak_k_rel) = {r2:.3f} "
              f"-> residual sd {resid.std():.4f} of total {col[m].std():.4f}")
    # exposure
    pit = D["pitches"][m]
    out["pitches_median"] = float(np.median(pit))
    out["pitches_q10"] = float(np.quantile(pit, 0.10))
    out["pitches_q90"] = float(np.quantile(pit, 0.90))
    print(f"\n   pitches per matched row: p10 {out['pitches_q10']:.0f}  "
          f"median {out['pitches_median']:.0f}  p90 {out['pitches_q90']:.0f}")
    from collections import Counter
    print("   matched by level:", Counter(D["level"][m].tolist()).most_common())
    out["matched_by_level"] = dict(Counter(D["level"][m].tolist()))
    return out


_MAIN = ("base", "add_csw", "add_swstr", "add_both", "swap_krel_csw",
         "swap_krel_swstr", "drop_krel")


def point(D, A):
    res = {}
    for nm in _MAIN:
        r = L.score(D, A[nm])
        rf = L.score(D, A[nm], full_test=True)
        res[nm] = {"rho6": L.pooled_rho(r), "rho4": L.pooled_rho(r, G),
                   "block4": L.block_rho(r, G), "auc4": L.auc(rf, G),
                   "per_fold": L.per_fold_rho(r)}
    ctrl = {}
    for kind in ("perm_csw", "perm_swstr", "permin_csw", "permin_swstr", "noise"):
        vals = []
        t = 0
        while f"ctrl_{kind}_{t}" in A:
            r = L.score(D, A[f"ctrl_{kind}_{t}"])
            vals.append((L.pooled_rho(r, G), L.block_rho(r, G)))
            t += 1
        ctrl[kind] = {"n": len(vals),
                      "rho4_mean": float(np.mean([v[0] for v in vals])),
                      "rho4_sd": float(np.std([v[0] for v in vals])),
                      "block4_mean": float(np.mean([v[1] for v in vals]))}
    b = res["base"]
    print("\n%-18s %8s %8s %8s %8s" % ("arm", "rho4", "d_rho4", "block4", "auc4"))
    for nm in _MAIN:
        r = res[nm]
        print("%-18s %8.4f %+8.4f %8.4f %8.4f"
              % (nm, r["rho4"], r["rho4"] - b["rho4"], r["block4"], r["auc4"]))
    for kind, c in ctrl.items():
        print("%-18s %8.4f %+8.4f %8.4f   (zero-info control, mean of %d, sd %.4f)"
              % ("ctrl_" + kind, c["rho4_mean"], c["rho4_mean"] - b["rho4"],
                 c["block4_mean"], c["n"], c["rho4_sd"]))
    print("\nper-fold rho (6 forward-chained splits):")
    for nm in _MAIN:
        pf = res[nm]["per_fold"]
        d = {y: round(pf[y] - res["base"]["per_fold"][y], 4)
             for y in pf if y in res["base"]["per_fold"]}
        print("   %-18s %s" % (nm, d if nm != "base" else
                               {y: round(v, 4) for y, v in pf.items()}))
    return {"arms": res, "controls": ctrl}


def perm_null(D, A, n=400):
    """Permutation null band: the delta you get from adding a column with the SAME
    marginal distribution as csw_rel but NO information, over n fresh permutations."""
    ix = D["idx"]
    base_cols = np.array([ix[k] for k in D["keys"]])
    r0 = L.score(D, base_cols)
    b4 = L.pooled_rho(r0, G)
    rng = np.random.default_rng(L.SEED + 99)
    out = {}
    for nm, col in (("csw_rel", D["csw"]), ("swstr_rel", D["swstr"])):
        d = []
        X0 = D["X"]
        slot = ix[nm]
        saved = X0[:, slot].copy()
        mi = np.flatnonzero(D["matched"])
        for _ in range(n):
            c = saved.copy()
            c[mi] = saved[rng.permutation(mi)]
            X0[:, slot] = c
            r = L.score(D, np.append(base_cols, slot))
            d.append(L.pooled_rho(r, G) - b4)
        X0[:, slot] = saved
        d = np.array(d)
        out[nm] = {"n": n, "mean": float(d.mean()), "sd": float(d.std()),
                   "p05": float(np.quantile(d, 0.05)),
                   "p95": float(np.quantile(d, 0.95)),
                   "p99": float(np.quantile(d, 0.99)),
                   "max": float(d.max())}
        print("perm-null %-10s delta mean %+.4f sd %.4f  p95 %+.4f  p99 %+.4f  max %+.4f"
              % (nm, d.mean(), d.std(), out[nm]["p95"], out[nm]["p99"], d.max()))
    return out


def boot(D, A, B=1500):
    """Paired bootstrap: resample rows (stratified by decision_year) over the WHOLE
    pool - train and test together - and refit every arm on the same replicate."""
    dy = D["dy"]
    strata = [np.flatnonzero(dy == v) for v in np.unique(dy)]
    arms = list(_MAIN) + ["ctrl_perm_csw_0", "ctrl_permin_csw_0", "ctrl_noise_0"]
    store = {a: [] for a in arms}
    rng = np.random.default_rng(L.SEED + 7)
    t0 = time.time()
    for b in range(B + 1):
        sel = (np.arange(D["n"]) if b == 0 else
               np.concatenate([rng.choice(ixs, size=len(ixs), replace=True)
                               for ixs in strata]))
        for a in arms:
            r = L.score(D, A[a], sel=sel)
            store[a].append(L.pooled_rho(r, G))
        if b % 100 == 0:
            print("  boot %d/%d  %.0fs" % (b, B, time.time() - t0), flush=True)
    out = {}
    base = np.array(store["base"][1:])
    for a in arms:
        v = np.array(store[a][1:])
        d = v - base
        d = d[~np.isnan(d)]
        out[a] = {"point": store[a][0], "d_point": store[a][0] - store["base"][0],
                  "d_mean": float(d.mean()), "d_sd": float(d.std()),
                  "ci95": [float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))],
                  "p_gt0": float((d > 0).mean()), "B": len(d)}
        print("%-18s d_point %+.4f  d_mean %+.4f  sd %.4f  CI95 [%+.4f, %+.4f]  P(>0)=%.3f"
              % (a, out[a]["d_point"], out[a]["d_mean"], out[a]["d_sd"],
                 out[a]["ci95"][0], out[a]["ci95"][1], out[a]["p_gt0"]))
    return out


def subgroups(D, A, B=800):
    """The differentiated hypothesis: CSW% stabilizes faster than K%, so any gain
    should CONCENTRATE on thin-exposure rows and on the low levels. Deltas are
    computed on TEST-ROW SUBSETS of the same forward-chained fits, with the same
    paired bootstrap, so the subgroup claim carries its own interval."""
    ix = D["idx"]
    m = D["matched"]
    pit = D["pitches"]
    thin_cut = float(np.quantile(pit[m], 0.33)) if m.sum() else 0.0
    cuts = {
        "all": np.ones(D["n"], dtype=bool),
        "matched": m,
        "thin_matched": m & (pit <= thin_cut),
        "thick_matched": m & (pit > thin_cut),
        "low_levels_A_Aplus": m & np.isin(D["level"].astype(str), ("A", "A+")),
        "high_levels_AA_AAA": m & np.isin(D["level"].astype(str), ("AA", "AAA")),
    }
    print("\nsubgroup sizes (matched pool, thin cut = %.0f pitches):" % thin_cut)
    for k, v in cuts.items():
        print("   %-22s %d" % (k, int(v.sum())))
    dy = D["dy"]
    strata = [np.flatnonzero(dy == v) for v in np.unique(dy)]
    rng = np.random.default_rng(L.SEED + 21)
    arms = ["base", "add_csw", "ctrl_permin_csw_0"]
    store = {c: {a: [] for a in arms} for c in cuts}
    t0 = time.time()
    for b in range(B + 1):
        sel = (np.arange(D["n"]) if b == 0 else
               np.concatenate([rng.choice(ixs, size=len(ixs), replace=True)
                               for ixs in strata]))
        rs = {a: L.score(D, A[a], sel=sel) for a in arms}
        for c, mask in cuts.items():
            for a in arms:
                store[c][a].append(L.pooled_rho(rs[a], G, mask=mask))
        if b % 100 == 0:
            print("  sub %d/%d  %.0fs" % (b, B, time.time() - t0), flush=True)
    out = {}
    for c in cuts:
        base = np.array(store[c]["base"][1:])
        o = {"n_rows_in_cut": int(cuts[c].sum())}
        for a in ("add_csw", "ctrl_permin_csw_0"):
            v = np.array(store[c][a][1:])
            d = v - base
            d = d[~np.isnan(d)]
            if len(d) < 50:
                o[a] = None
                continue
            o[a] = {"d_point": store[c][a][0] - store[c]["base"][0],
                    "d_mean": float(d.mean()), "d_sd": float(d.std()),
                    "ci95": [float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))],
                    "p_gt0": float((d > 0).mean())}
        out[c] = o
        a = o.get("add_csw")
        if a:
            ctl = o.get("ctrl_permin_csw_0") or {}
            print("%-22s add_csw d %+.4f (CI [%+.4f,%+.4f], P>0 %.3f)   "
                  "zero-info twin d %+.4f"
                  % (c, a["d_mean"], a["ci95"][0], a["ci95"][1], a["p_gt0"],
                     ctl.get("d_mean", float("nan"))))
    return out


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "desc"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else None
    D = L.load()
    A = L.arms(D)
    res = {}
    if stage in ("desc", "all"):
        res["desc"] = desc(D)
    if stage in ("point", "all"):
        res["point"] = point(D, A)
    if stage in ("perm", "all"):
        res["perm_null"] = perm_null(D, A, n=n or 400)
    if stage in ("boot", "all"):
        res["boot"] = boot(D, A, B=n or 1500)
    if stage in ("sub", "all"):
        res["subgroups"] = subgroups(D, A, B=n or 800)
    (OUT / f"_csw_{stage}.json").write_text(json.dumps(res, indent=1, default=float),
                                            encoding="utf-8")
    print("\nwrote", OUT / f"_csw_{stage}.json")
