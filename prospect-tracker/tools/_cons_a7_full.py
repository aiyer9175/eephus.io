# A7 -- final gate. Adds the only OUT-OF-SAMPLE-IDENTIFIABLE vintage forms, a
# repeated zero-information control distribution, and the shrinkage sweeps.
from __future__ import annotations

import json
import sys
import time

import numpy as np

from _cons_a6_boot import (FG, MP, CONS, TGT, WT, DY, SIDE, PULL, DEBUT, TOP,
                           IFA, COL, BOTH, FOLDS, MIN_TRAIN, MIN_TEST, SHIPPED,
                           rho, resid_var, _R)
from _cons_data import OUT

N = len(FG)


def fit(idx):
    p = {}
    pb = idx[BOTH[idx]]
    for s in (0, 1):
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

    def _w(sub):
        if len(sub) < 120:
            return {"fg": 1.0, "mp": 1.0}
        v1, v2 = resid_var(FG[sub], TGT[sub], WT[sub]), resid_var(MP[sub], TGT[sub], WT[sub])
        if v1 <= 0 or v2 <= 0:
            return {"fg": 1.0, "mp": 1.0}
        s1, s2 = 1 / v1, 1 / v2
        return {"fg": 2 * s1 / (s1 + s2), "mp": 2 * s2 / (s1 + s2)}
    p["w"] = _w(pb)
    p["w_top"], p["w_fringe"] = _w(pb[TOP[pb]]), _w(pb[~TOP[pb]])
    p["w_ifa"], p["w_col"] = _w(pb[IFA[pb]]), _w(pb[COL[pb]])
    p["w_hs"] = _w(pb[~IFA[pb] & ~COL[pb]])
    # per-train-year offsets (used by the recency + trend vintage forms)
    yrs, offs, ns = [], [], []
    for y in np.unique(DY[pb]):
        s = pb[DY[pb] == y]
        if len(s) >= 40:
            yrs.append(int(y))
            offs.append(float(MP[s].mean() - FG[s].mean()))
            ns.append(len(s))
    p["yr_off"] = (np.array(yrs, float), np.array(offs, float), np.array(ns, float))
    return p


def vintage_offset(p, Y, mode):
    yrs, offs, ns = p["yr_off"]
    if len(yrs) == 0:
        return None
    if mode == "recent3":
        m = yrs >= (Y - 3)
        if m.sum() == 0:
            return None
        return float((offs[m] * ns[m]).sum() / ns[m].sum())
    if mode == "trend":
        if len(yrs) < 4:
            return None
        w = ns
        W = w.sum()
        mx, my = (w * yrs).sum() / W, (w * offs).sum() / W
        den = (w * (yrs - mx) ** 2).sum()
        if den <= 0:
            return None
        b = (w * (yrs - mx) * (offs - my)).sum() / den
        return float(my + b * (Y - mx))
    return None


def make(idx, p, kind, Y=None, sdr_override=None, pull=(0.5, 35.0)):
    f, m = FG[idx], MP[idx]
    sh = np.array([p[s]["shift"] for s in SIDE[idx]])
    mfg = np.array([p[s]["mfg"] for s in SIDE[idx]])
    mmp = np.array([p[s]["mmp"] for s in SIDE[idx]])
    sdr = np.array([p[s]["sdr"] for s in SIDE[idx]]) if sdr_override is None \
        else np.full(len(idx), sdr_override)
    wf, wm = np.ones(len(idx)), np.ones(len(idx))
    if kind == "raw":
        madj = m
    elif kind in ("recent3", "trend"):
        v = vintage_offset(p, Y, kind)
        madj = m - (sh if v is None else v)
    elif kind == "sd":
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
        wf = np.where(IFA[idx], p["w_ifa"]["fg"], np.where(COL[idx], p["w_col"]["fg"], p["w_hs"]["fg"]))
        wm = np.where(IFA[idx], p["w_ifa"]["mp"], np.where(COL[idx], p["w_col"]["mp"], p["w_hs"]["mp"]))
    hf, hm = ~np.isnan(f), ~np.isnan(m)
    num = np.where(hf, wf * np.nan_to_num(f), 0.0) + np.where(hm, wm * np.nan_to_num(madj), 0.0)
    den = np.where(hf, wf, 0.0) + np.where(hm, wm, 0.0)
    out = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    if pull is not None:
        K, prior = pull
        w = 1.0 / (1.0 + K)
        out = np.where(PULL[idx], w * out + (1 - w) * prior, out)
    return out


VAR = ["raw", "shift", "recent3", "trend", "shipped", "ivw", "tier", "cohort", "sd"]


def evaluate(pool, variants=VAR, perm_rng=None, sdr_mode=None, rng=None, pulls=None):
    specs = [(v, None) for v in variants] + [(f"pull_K{k}_P{pp}", (k, pp))
                                             for (k, pp) in (pulls or [])]
    acc = {nm: ([], []) for nm, _ in specs}
    acc["served"] = ([], [])
    pf = {nm: {} for nm in acc}
    for Y in FOLDS:
        tr = pool[DY[pool] < Y]
        te = pool[DY[pool] == Y]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        p = fit(tr)
        t = TGT[te]
        if perm_rng is not None:
            t = perm_rng.permutation(t)
        for nm, pl in specs:
            if pl is None:
                ov = None
                if nm == "sd" and sdr_mode == "random":
                    ov = 1.0 + abs(p[0]["sdr"] - 1.0) * (1 if rng.random() < 0.5 else -1)
                elif nm == "sd" and sdr_mode == "invert":
                    ov = 2.0 - p[0]["sdr"]
                x = make(te, p, nm, Y=Y, sdr_override=ov)
            else:
                x = make(te, p, "shift", Y=Y, pull=(pl if pl[0] >= 0 else None))
            ok = ~np.isnan(x)
            if ok.sum() < 15:
                continue
            acc[nm][0].append(x[ok])
            acc[nm][1].append(t[ok])
            pf[nm][int(Y)] = rho(x[ok], t[ok])
        acc["served"][0].append(CONS[te])
        acc["served"][1].append(t)
        pf["served"][int(Y)] = rho(CONS[te], t)
    out = {}
    for nm in acc:
        if not acc[nm][0]:
            continue
        x, y = np.concatenate(acc[nm][0]), np.concatenate(acc[nm][1])
        vals = [q for q in pf[nm].values() if np.isfinite(q)]
        out[nm] = {"pooled": rho(x, y), "mean_fold": float(np.mean(vals)),
                   "per_fold": pf[nm], "n": len(x)}
    return out


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    PULLS = [(-1, 0)] + [(k, pr) for k in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)
                         for pr in (30.0, 35.0, 40.0)]
    summary = {}
    for cohort, mask in (("full", np.ones(N, bool)), ("debuted", DEBUT)):
        pool = np.where(mask)[0]
        base = evaluate(pool, pulls=PULLS)
        ref = base["shift"]
        print(f"\n{'='*78}\n=== A7 cohort={cohort}  n={ref['n']}  "
              f"reference = 'shift' (the LIVE design: outlet offset + equal votes "
              f"+ single-source pull K=0.5 -> FV35) ===")
        print(f"{'variant':>12} {'pooled':>8} {'d':>9} {'meanfold':>9} {'d':>9} {'folds up':>9}")
        for v in VAR + ["served"]:
            b = base[v]
            up = sum(1 for y in ref["per_fold"] if b["per_fold"].get(y, -9) > ref["per_fold"][y])
            print(f"{v:>12} {b['pooled']:>8.4f} {b['pooled']-ref['pooled']:>+9.4f} "
                  f"{b['mean_fold']:>9.4f} {b['mean_fold']-ref['mean_fold']:>+9.4f} "
                  f"{up:>4}/{len(ref['per_fold'])}")
        print("\n  single-source pull-down sweep (K, prior); 'none' = pull removed:")
        print(f"{'setting':>16} {'pooled':>8} {'d':>9} {'meanfold':>9} {'d':>9}")
        for nm in [k for k in base if k.startswith("pull_")]:
            b = base[nm]
            lbl = "none" if nm.startswith("pull_K-1") else nm[5:]
            print(f"{lbl:>16} {b['pooled']:>8.4f} {b['pooled']-ref['pooled']:>+9.4f} "
                  f"{b['mean_fold']:>9.4f} {b['mean_fold']-ref['mean_fold']:>+9.4f}")

        # paired bootstrap with refit
        rng = np.random.default_rng(101)
        t0 = time.time()
        names = [v for v in VAR if v != "shift"] + [k for k in base if k.startswith("pull_")]
        d = {v: {"p": [], "m": []} for v in names}
        for _ in range(B):
            bidx = pool[rng.integers(0, len(pool), len(pool))]
            r = evaluate(bidx, pulls=PULLS)
            if "shift" not in r:
                continue
            for v in names:
                if v in r:
                    d[v]["p"].append(r[v]["pooled"] - r["shift"]["pooled"])
                    d[v]["m"].append(r[v]["mean_fold"] - r["shift"]["mean_fold"])
        print(f"\n  paired bootstrap B={B} ({time.time()-t0:.0f}s) -- delta vs the live design")
        print(f"{'variant':>16} {'d pooled':>9} {'CI95 pooled':>21} {'MDE95':>7} | "
              f"{'d meanfold':>10} {'CI95':>21} {'MDE95':>7}")
        boot = {}
        for v in names:
            a, m = np.array(d[v]["p"]), np.array(d[v]["m"])
            lo, hi = np.percentile(a, [2.5, 97.5])
            lo2, hi2 = np.percentile(m, [2.5, 97.5])
            lbl = ("pull=none" if v.startswith("pull_K-1") else (v[5:] if v.startswith("pull_") else v))
            print(f"{lbl:>16} {base[v]['pooled']-ref['pooled']:>+9.4f} [{lo:+.4f},{hi:+.4f}] "
                  f"{2*1.96*a.std(ddof=1):>7.4f} | {base[v]['mean_fold']-ref['mean_fold']:>+10.4f} "
                  f"[{lo2:+.4f},{hi2:+.4f}] {2*1.96*m.std(ddof=1):>7.4f}")
            boot[lbl] = {"d_pooled": base[v]['pooled'] - ref['pooled'],
                         "ci_pooled": [float(lo), float(hi)],
                         "mde95_pooled": float(2 * 1.96 * a.std(ddof=1)),
                         "d_mean": base[v]['mean_fold'] - ref['mean_fold'],
                         "ci_mean": [float(lo2), float(hi2)],
                         "mde95_mean": float(2 * 1.96 * m.std(ddof=1))}

        # repeated zero-information control for the sd map
        rngc = np.random.default_rng(53)
        ctrl_p, ctrl_m = [], []
        for _ in range(200):
            r = evaluate(pool, variants=["shift", "sd"], sdr_mode="random", rng=rngc)
            ctrl_p.append(r["sd"]["pooled"] - r["shift"]["pooled"])
            ctrl_m.append(r["sd"]["mean_fold"] - r["shift"]["mean_fold"])
        cp, cm = np.array(ctrl_p), np.array(ctrl_m)
        obs_p = base["sd"]["pooled"] - ref["pooled"]
        obs_m = base["sd"]["mean_fold"] - ref["mean_fold"]
        print(f"\n  ZERO-INFORMATION CONTROL for the sd(distribution) map "
              f"(same |sdr-1| magnitude, random sign, 200 draws):")
        print(f"    control d pooled   mean {cp.mean():+.4f}  p95 {np.percentile(cp,95):+.4f}  "
              f"| observed {obs_p:+.4f} -> "
              f"{'BEATS control p95' if obs_p>np.percentile(cp,95) else 'DOES NOT beat the control'}")
        print(f"    control d meanfold mean {cm.mean():+.4f}  p95 {np.percentile(cm,95):+.4f}  "
              f"| observed {obs_m:+.4f} -> "
              f"{'BEATS control p95' if obs_m>np.percentile(cm,95) else 'DOES NOT beat the control'}")

        # permutation null band
        rngp = np.random.default_rng(77)
        nulls = {v: [] for v in names}
        for _ in range(250):
            r = evaluate(pool, perm_rng=rngp, pulls=PULLS)
            for v in names:
                if v in r:
                    nulls[v].append(r[v]["pooled"] - r["shift"]["pooled"])
        print("\n  permutation null band (target shuffled within fold), |delta pooled| p95:")
        for v in names:
            a = np.abs(np.array(nulls[v]))
            lbl = ("pull=none" if v.startswith("pull_K-1") else (v[5:] if v.startswith("pull_") else v))
            obs = abs(base[v]['pooled'] - ref['pooled'])
            print(f"    {lbl:>16} null|d|p95 = {np.percentile(a,95):.4f}   observed |d| = {obs:.4f}  "
                  f"-> {'OUTSIDE' if obs > np.percentile(a,95) else 'INSIDE (null)'}")
        summary[cohort] = {"point": {v: {"pooled": base[v]["pooled"],
                                         "mean_fold": base[v]["mean_fold"],
                                         "per_fold": base[v]["per_fold"]} for v in base},
                           "bootstrap": boot,
                           "sd_control": {"ctrl_mean_pooled": float(cp.mean()),
                                          "ctrl_p95_pooled": float(np.percentile(cp, 95)),
                                          "obs_pooled": float(obs_p),
                                          "ctrl_p95_mean": float(np.percentile(cm, 95)),
                                          "obs_mean": float(obs_m)}}
    json.dump(summary, open(OUT / "a7_gate.json", "w"), indent=1)
    print("\nwrote", OUT / "a7_gate.json")


if __name__ == "__main__":
    main()
