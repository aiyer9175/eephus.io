# A6 -- vectorized forward-chained gate with the four mandatory controls.
#   (1) paired cluster bootstrap resampling the WHOLE pool, REFITTING every
#       calibration parameter on each draw
#   (2) zero-information / directional controls
#   (3) permutation null band
#   (4) >= 4 independent time splits (7 here), reported per fold
from __future__ import annotations

import json
import sys
import time

import numpy as np

from _cons_data import OUT, load_matrix_rows, ci

FOLDS = np.array([2018, 2019, 2020, 2021, 2022, 2023, 2024])
MIN_TRAIN, MIN_TEST = 200, 25
SHIPPED = {"fg": 0.9363, "mp": 1.0637}

_R = load_matrix_rows()
for r in _R:
    r["pulled"] = (r["pre"] is not None and abs(r["cons"] - r["pre"]) > 1e-9)

FG = np.array([r["fg"] if r["fg"] is not None else np.nan for r in _R])
MP = np.array([r["mp"] if r["mp"] is not None else np.nan for r in _R])
CONS = np.array([r["cons"] for r in _R], float)
TGT = np.array([r["target"] for r in _R], float)
WT = np.array([r["weight"] for r in _R], float)
DY = np.array([r["decision_year"] for r in _R], int)
SIDE = np.array([0 if r["side"] == "hit" else 1 for r in _R], int)
PULL = np.array([r["pulled"] for r in _R], bool)
DEBUT = np.array([r["kind"] == "debuted" for r in _R], bool)
TOP = CONS >= 50
IFA = np.array([r["is_ifa"] for r in _R], bool)
COL = np.array([r["is_college"] for r in _R], bool)
HASF, HASM = ~np.isnan(FG), ~np.isnan(MP)
BOTH = HASF & HASM


def rankdata(a):
    order = a.argsort(kind="mergesort")
    ranks = np.empty(len(a), float)
    ranks[order] = np.arange(len(a), dtype=float)
    sa = a[order]
    i = 0
    n = len(sa)
    while i < n:
        j = i
        while j + 1 < n and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return ranks


def rho(x, y):
    if len(x) < 8:
        return np.nan
    rx, ry = rankdata(x), rankdata(y)
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def resid_var(x, t, w):
    X = np.column_stack([np.ones_like(x), x])
    b = np.linalg.lstsq(X * w[:, None], t * w, rcond=None)[0]
    e = t - X @ b
    return float((w * e ** 2).sum() / w.sum())


def fit(idx):
    """Calibration parameters from TRAIN indices only."""
    p = {}
    pb = idx[BOTH[idx]]
    for s, nm in ((0, "hit"), (1, "pit")):
        sub = pb[SIDE[pb] == s]
        if len(sub) < 60:
            sub = pb
        if len(sub) < 60:
            p[s] = {"shift": 0.0, "mfg": 40.0, "mmp": 40.0, "sdr": 1.0}
            continue
        f, m = FG[sub], MP[sub]
        sdr = m.std(ddof=1) / f.std(ddof=1) if f.std(ddof=1) > 0 else 1.0
        p[s] = {"shift": float(m.mean() - f.mean()), "mfg": float(f.mean()),
                "mmp": float(m.mean()), "sdr": float(sdr) if 0.5 < sdr < 2.0 else 1.0}
    # inverse-residual-variance weights (predicted-WAR space)
    def _w(sub):
        if len(sub) < 120:
            return {"fg": 1.0, "mp": 1.0}
        v1 = resid_var(FG[sub], TGT[sub], WT[sub])
        v2 = resid_var(MP[sub], TGT[sub], WT[sub])
        if v1 <= 0 or v2 <= 0:
            return {"fg": 1.0, "mp": 1.0}
        s1, s2 = 1 / v1, 1 / v2
        return {"fg": 2 * s1 / (s1 + s2), "mp": 2 * s2 / (s1 + s2)}
    p["w"] = _w(pb)
    p["w_top"] = _w(pb[TOP[pb]])
    p["w_fringe"] = _w(pb[~TOP[pb]])
    p["w_ifa"] = _w(pb[IFA[pb]])
    p["w_col"] = _w(pb[COL[pb]])
    p["w_hs"] = _w(pb[~IFA[pb] & ~COL[pb]])
    p["shift_yr"] = {}
    for y in np.unique(DY[pb]):
        s = pb[DY[pb] == y]
        if len(s) >= 60:
            p["shift_yr"][int(y)] = float(MP[s].mean() - FG[s].mean())
    return p


def make(idx, p, kind, sdr_override=None):
    """Vectorized consensus for rows `idx`."""
    f, m = FG[idx].copy(), MP[idx].copy()
    sh = np.array([p[s]["shift"] for s in SIDE[idx]])
    mfg = np.array([p[s]["mfg"] for s in SIDE[idx]])
    mmp = np.array([p[s]["mmp"] for s in SIDE[idx]])
    sdr = np.array([p[s]["sdr"] for s in SIDE[idx]])
    if sdr_override is not None:
        sdr = np.full(len(idx), sdr_override)
    wf = np.ones(len(idx))
    wm = np.ones(len(idx))
    if kind == "raw":
        madj = m
    elif kind == "vintage":
        shy = np.array([p["shift_yr"].get(int(y), p[s]["shift"])
                        for y, s in zip(DY[idx], SIDE[idx])])
        madj = m - shy
    elif kind in ("sd", "sd_inv", "sd_rand"):
        madj = mfg + (m - mmp) / sdr
    else:
        madj = m - sh
    if kind == "shipped":
        wf[:], wm[:] = SHIPPED["fg"], SHIPPED["mp"]
    elif kind == "ivw":
        wf[:], wm[:] = p["w"]["fg"], p["w"]["mp"]
    elif kind == "tier":
        t = TOP[idx]
        wf = np.where(t, p["w_top"]["fg"], p["w_fringe"]["fg"])
        wm = np.where(t, p["w_top"]["mp"], p["w_fringe"]["mp"])
    elif kind == "cohort":
        wf = np.where(IFA[idx], p["w_ifa"]["fg"],
                      np.where(COL[idx], p["w_col"]["fg"], p["w_hs"]["fg"]))
        wm = np.where(IFA[idx], p["w_ifa"]["mp"],
                      np.where(COL[idx], p["w_col"]["mp"], p["w_hs"]["mp"]))
    hf, hm = ~np.isnan(f), ~np.isnan(m)
    num = np.where(hf, wf * np.nan_to_num(f), 0.0) + np.where(hm, wm * np.nan_to_num(madj), 0.0)
    den = np.where(hf, wf, 0.0) + np.where(hm, wm, 0.0)
    out = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    pl = PULL[idx]
    out = np.where(pl, (2.0 / 3.0) * out + (1.0 / 3.0) * 35.0, out)
    return out


VARIANTS = ["raw", "shift", "vintage", "shipped", "ivw", "tier", "cohort", "sd"]


def evaluate(idx_pool, variants=VARIANTS, perm_seed=None, sdr_mode=None, rng=None):
    """Forward-chained pooled rho + per-fold rho for each variant on `idx_pool`."""
    pairs = {v: ([], []) for v in variants}
    pairs["served"] = ([], [])
    pf = {v: {} for v in list(variants) + ["served"]}
    for Y in FOLDS:
        tr = idx_pool[DY[idx_pool] < Y]
        te = idx_pool[DY[idx_pool] == Y]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        p = fit(tr)
        t = TGT[te]
        if perm_seed is not None:
            t = rng.permutation(t)
        for v in variants:
            ov = None
            if v == "sd" and sdr_mode == "invert":
                ov = 2.0 - p[0]["sdr"]      # same magnitude, wrong direction
            elif v == "sd" and sdr_mode == "random":
                mag = abs(p[0]["sdr"] - 1.0)
                ov = 1.0 + mag * (1 if rng.random() < 0.5 else -1)
            x = make(te, p, v, sdr_override=ov)
            ok = ~np.isnan(x)
            if ok.sum() < 15:
                continue
            pairs[v][0].append(x[ok])
            pairs[v][1].append(t[ok])
            pf[v][int(Y)] = rho(x[ok], t[ok])
        pairs["served"][0].append(CONS[te])
        pairs["served"][1].append(t)
        pf["served"][int(Y)] = rho(CONS[te], t)
    out = {}
    for v in pairs:
        if not pairs[v][0]:
            continue
        x = np.concatenate(pairs[v][0])
        y = np.concatenate(pairs[v][1])
        vals = [q for q in pf[v].values() if np.isfinite(q)]
        out[v] = {"pooled": rho(x, y), "mean_fold": float(np.mean(vals)) if vals else np.nan,
                  "per_fold": pf[v], "n": len(x)}
    return out


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    for cohort, mask in (("full", np.ones(len(_R), bool)), ("debuted", DEBUT)):
        pool = np.where(mask)[0]
        base = evaluate(pool)
        print(f"\n=== A6 point estimates, cohort={cohort} (n={base['shift']['n']}) ===")
        print(f"{'variant':>10} {'pooled':>8} {'d(shift)':>9} {'meanfold':>9} {'d':>9}")
        for v in list(VARIANTS) + ["served"]:
            b = base["shift"]
            print(f"{v:>10} {base[v]['pooled']:>8.4f} {base[v]['pooled']-b['pooled']:>+9.4f} "
                  f"{base[v]['mean_fold']:>9.4f} {base[v]['mean_fold']-b['mean_fold']:>+9.4f}")

        # ---- paired bootstrap: resample the WHOLE pool, refit each draw ----
        rng = np.random.default_rng(11)
        t0 = time.time()
        deltas = {v: {"pooled": [], "mean": []} for v in VARIANTS if v != "shift"}
        for _ in range(B):
            bidx = pool[rng.integers(0, len(pool), len(pool))]
            r = evaluate(bidx)
            if "shift" not in r:
                continue
            for v in deltas:
                if v in r:
                    deltas[v]["pooled"].append(r[v]["pooled"] - r["shift"]["pooled"])
                    deltas[v]["mean"].append(r[v]["mean_fold"] - r["shift"]["mean_fold"])
        print(f"  [bootstrap B={B} in {time.time()-t0:.0f}s]")
        print(f"\n  paired bootstrap (train+test resampled, refit each draw), "
              f"delta vs 'shift' (= the LIVE design):")
        print(f"{'variant':>10} {'d pooled':>9} {'CI95':>22} {'P(>0)':>7} | "
              f"{'d meanfold':>10} {'CI95':>22} {'P(>0)':>7}")
        res_out = {}
        for v, d in deltas.items():
            a = np.array(d["pooled"])
            m = np.array(d["mean"])
            lo, hi = np.percentile(a, [2.5, 97.5])
            lo2, hi2 = np.percentile(m, [2.5, 97.5])
            print(f"{v:>10} {base[v]['pooled']-base['shift']['pooled']:>+9.4f} "
                  f"[{lo:+.4f},{hi:+.4f}]".rjust(0) +
                  f"   {np.mean(a>0):>6.3f} | "
                  f"{base[v]['mean_fold']-base['shift']['mean_fold']:>+10.4f} "
                  f"[{lo2:+.4f},{hi2:+.4f}]   {np.mean(m>0):>6.3f}")
            res_out[v] = {"d_pooled": base[v]['pooled'] - base['shift']['pooled'],
                          "ci_pooled": [float(lo), float(hi)], "p_pooled": float(np.mean(a > 0)),
                          "d_mean": base[v]['mean_fold'] - base['shift']['mean_fold'],
                          "ci_mean": [float(lo2), float(hi2)], "p_mean": float(np.mean(m > 0)),
                          "sd_pooled": float(a.std(ddof=1)), "sd_mean": float(m.std(ddof=1))}
        print("\n  MDE95 (2*1.96*sd of the paired bootstrap delta):")
        for v, o in res_out.items():
            print(f"    {v:>10} pooled MDE95 = {2*1.96*o['sd_pooled']:.4f}   "
                  f"mean-fold MDE95 = {2*1.96*o['sd_mean']:.4f}")

        # ---- permutation null band ----
        rngp = np.random.default_rng(23)
        nulls = {v: [] for v in VARIANTS if v != "shift"}
        for _ in range(300):
            r = evaluate(pool, perm_seed=1, rng=rngp)
            for v in nulls:
                nulls[v].append(r[v]["pooled"] - r["shift"]["pooled"])
        print("\n  permutation null band (target permuted within fold), delta pooled:")
        for v, a in nulls.items():
            a = np.array(a)
            print(f"    {v:>10} null p2.5={np.percentile(a,2.5):+.4f} "
                  f"p97.5={np.percentile(a,97.5):+.4f}  |observed| "
                  f"{'OUTSIDE' if abs(res_out[v]['d_pooled'])>np.percentile(np.abs(a),95) else 'INSIDE'} the null p95")

        # ---- directional / zero-information controls for the sd map ----
        rngc = np.random.default_rng(31)
        for mode in ("invert", "random"):
            r = evaluate(pool, sdr_mode=mode, rng=rngc)
            print(f"  control sd map [{mode:>6}] : d pooled "
                  f"{r['sd']['pooled']-r['shift']['pooled']:+.4f}   d meanfold "
                  f"{r['sd']['mean_fold']-r['shift']['mean_fold']:+.4f}")
        json.dump(res_out, open(OUT / f"a6_{cohort}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
