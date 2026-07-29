# SCRATCH: anchor v2 -- paired (within-player) source-offset estimator, origin sweep,
# per-block cross-split, and the pairing-preserving placebo null.
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import _frontier_anchor as A

OUT = Path(__file__).resolve().parent / "_frontier_out"
OUT.mkdir(exist_ok=True)
_orig_apply = A.apply_anchor
_orig_fit = A.fit_anchor


# --------------------------------------------------------------- extra fits
def fit2(tr, y_override=None):
    P = _orig_fit(tr, y_override=y_override)
    fg, mp, w = tr["fg"], tr["mp"], tr["w"]
    both = np.isfinite(fg) & np.isfinite(mp)
    # PAIRED within-player offset: on players BOTH sources graded, the mean signed gap.
    # Isolates grading-scale bias from coverage/population differences.
    if both.sum() >= 25:
        d = mp[both] - fg[both]
        ww = w[both]
        gap = float((ww * d).sum() / ww.sum())
        # spread ratio on the same paired rows
        sfg = float(np.sqrt((ww * (fg[both] - np.average(fg[both], weights=ww)) ** 2).sum() / ww.sum()))
        smp = float(np.sqrt((ww * (mp[both] - np.average(mp[both], weights=ww)) ** 2).sum() / ww.sum()))
        P["pair_gap"] = gap
        P["pair_sfg"], P["pair_smp"] = max(sfg, 1e-6), max(smp, 1e-6)
        P["pair_n"] = int(both.sum())
        # paired per-source skill on the COMMON set (fair head-to-head)
        yv = tr["y"] if y_override is None else y_override
        P["c_rho_fg"] = A.spear(fg[both], yv[both])
        P["c_rho_mp"] = A.spear(mp[both], yv[both])
        # residual precision on the common set (inverse-variance vote weight)
        for k, arr in (("fg", fg), ("mp", mp)):
            o = A._wols(arr[both], yv[both], ww)
            P[f"c_ols_{k}"] = o
    else:
        P["pair_gap"] = 0.0
        P["pair_sfg"] = P["pair_smp"] = 1.0
        P["pair_n"] = 0
        P["c_rho_fg"] = P["c_rho_mp"] = np.nan
        P["c_ols_fg"] = P["c_ols_mp"] = None
    return P


def apply2(kind, P, te, weights=None):
    cons, fg, mp = te["cons"], te["fg"], te["mp"]
    n = len(cons)
    g = P.get("pair_gap", 0.0)

    if kind == "pair_shift":
        # de-bias each source onto the FanGraphs scale using the PAIRED gap, then
        # equal-weight average of whatever is available.
        return A._combine(cons - g / 2.0, [fg, mp - g], [1.0, 1.0])
    if kind == "pair_shift_half":               # half-strength (shrunk) correction
        return A._combine(cons - g / 4.0, [fg, mp - g / 2.0], [1.0, 1.0])
    if kind == "pair_shift_scale":              # paired shift + paired spread match
        mpn = (mp - g - np.nanmean([0.0])) if False else (mp - g)
        # rescale MP's spread onto FG's around the paired FG mean level
        r = P["pair_sfg"] / P["pair_smp"]
        mu = float(np.nanmean(fg)) if np.isfinite(fg).any() else 45.0
        mpn = mu + (mpn - mu) * r
        return A._combine(cons - g / 2.0, [fg, mpn], [1.0, 1.0])
    if kind == "pair_shift_prec":               # paired shift + common-set precision weights
        of, om = P.get("c_ols_fg"), P.get("c_ols_mp")
        if of is None or om is None:
            wf = wm = 1.0
        else:
            wf, wm = 1.0 / of[2], 1.0 / om[2]
            sw = (wf + wm) / 2.0
            wf, wm = float(np.clip(wf / sw, 0.6, 1.4)), float(np.clip(wm / sw, 0.6, 1.4))
        return A._combine(cons - g / 2.0, [fg, mp - g], [wf, wm])
    if kind == "pair_shift_rho":                # paired shift + common-set rho vote weights
        rf, rm = P.get("c_rho_fg"), P.get("c_rho_mp")
        if not (np.isfinite(rf) and np.isfinite(rm)):
            wf = wm = 1.0
        else:
            mean = (max(rf, 0.05) + max(rm, 0.05)) / 2.0
            wf = float(np.clip(max(rf, 0.05) / mean, 0.6, 1.4))
            wm = float(np.clip(max(rm, 0.05) / mean, 0.6, 1.4))
        return A._combine(cons - g / 2.0, [fg, mp - g], [wf, wm])
    if kind == "shift_only":
        zs = []
        for k, arr in (("fg", fg), ("mp", mp)):
            mo = P[f"mom_{k}"]
            zs.append(arr - mo[0] if mo else np.full(n, np.nan))
        cm = P["cons_mom"]
        return A._combine(cons - cm[0] if cm else cons, zs, [1.0, 1.0])
    return _orig_apply(kind, P, te, weights=weights)


A.fit_anchor = fit2
A.apply_anchor = apply2

KINDS = ["shipped", "plain_mean", "shift_only", "zmap", "warcal",
         "pair_shift", "pair_shift_half", "pair_shift_scale",
         "pair_shift_prec", "pair_shift_rho"]


def sides_arrays(cut="debuted_km"):
    return {s: A.to_arrays(A.load_rows(s, cut)) for s in ("hit", "pit")}


def run(sides, kinds, origins, **kw):
    r = A.fwd_anchor(kinds, sides, origins, **kw)
    if r is None:
        return None, None, None
    preds, tgt, blk = r
    return {k: A.spear(preds[k], tgt) for k in kinds}, preds, (tgt, blk)


def main():
    t0 = time.time()
    sides = sides_arrays()
    res = {}
    print("=== ORIGIN-WINDOW SWEEP (pooled block-percentile Spearman) ===")
    windows = {"2020-2024": tuple(range(2020, 2025)),
               "2018-2024": tuple(range(2018, 2025)),
               "2016-2024": tuple(range(2016, 2025)),
               "2014-2024": tuple(range(2014, 2025))}
    for name, org in windows.items():
        pt, _pr, (tgt, _b) = run(sides, KINDS, org)
        res.setdefault("windows", {})[name] = {"n": int(len(tgt)),
                                               **{k: pt[k] for k in KINDS}}
        print(f"  [{name}] n={len(tgt)}")
        for k in KINDS:
            print(f"     {k:17s} rho {pt[k]:.4f}  delta {pt[k]-pt['shipped']:+.4f}")

    # ---- per-block (side x origin) deltas: the cross-split check
    print("\n=== PER-BLOCK DELTAS (side x origin, 2014-2024) ===")
    org = windows["2014-2024"]
    perblk = {}
    for s in ("hit", "pit"):
        for Y in org:
            pt2, _p, (tg, _b) = run({s: sides[s]}, KINDS, (Y,))
            if pt2 is None:
                continue
            perblk[f"{s}{Y}"] = {"n": int(len(tg)), **{k: pt2[k] for k in KINDS}}
    res["per_block"] = perblk
    for k in KINDS:
        if k == "shipped":
            continue
        d = np.array([v[k] - v["shipped"] for v in perblk.values()])
        d = d[np.isfinite(d)]
        print(f"  {k:17s} mean {d.mean():+.4f} se {d.std(ddof=1)/np.sqrt(len(d)):.4f} "
              f"t {d.mean()/(d.std(ddof=1)/np.sqrt(len(d))):+.2f}  signs {int((d>0).sum())}+/{int((d<0).sum())}-  (nblk={len(d)})")
        res.setdefault("per_block_summary", {})[k] = {
            "mean": float(d.mean()), "se": float(d.std(ddof=1) / np.sqrt(len(d))),
            "pos": int((d > 0).sum()), "neg": int((d < 0).sum())}

    # ---- fitted paired gap per side / per origin (the mechanism, for the record)
    print("\n=== FITTED PAIRED SOURCE GAP (MLB Pipeline minus FanGraphs, FV pts) ===")
    for s in ("hit", "pit"):
        a = sides[s]
        for Y in (2020, 2022, 2024):
            tri = np.flatnonzero(a["dy"] < Y)
            tr = {k: v[tri] for k, v in a.items() if isinstance(v, np.ndarray)}
            P = A.fit_anchor(tr)
            print(f"  {s} train<{Y}: gap {P['pair_gap']:+.3f} on n_pair={P['pair_n']} "
                  f"| marginal gap {P['mom_mp'][0]-P['mom_fg'][0]:+.3f} "
                  f"| common-set rho FG {P['c_rho_fg']:.4f} MP {P['c_rho_mp']:.4f}")
            res.setdefault("gaps", {})[f"{s}_{Y}"] = {
                "pair_gap": P["pair_gap"], "pair_n": P["pair_n"],
                "marginal_gap": P["mom_mp"][0] - P["mom_fg"][0],
                "c_rho_fg": P["c_rho_fg"], "c_rho_mp": P["c_rho_mp"]}

    json.dump(res, open(OUT / "_anchor_v2.json", "w"), indent=1, default=float)
    print("\nelapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
