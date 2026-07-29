# SCRATCH: (b) information-conditional shrinkage of the model leg toward the consensus
# anchor, and (d) tier/cohort-varying blend lambda. All schemes share ONE ridge fit per
# bootstrap replicate (they only change the blend), so pairing is exact.
# Run: python tools/_frontier_shrink_bd.py [B]
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontier_shrink import (ORIGINS, LAM, BASE_KEYS, OUT, load_pool, score_records,
                              blend, block_rho, block_auc, resample_pool, _tier)

SHIPPED_CFG = {"mode": "shipped"}


def schemes(prev):
    """prev = measured prevalence of each info flag on the scored records."""
    S = {"global": {"kind": "global"}}
    # ---------- (b) low-information rows shrink the MODEL leg toward consensus ----
    for flag in ("milb_missing", "single_source", "thin_milb", "no_tools"):
        for mult in (0.75, 0.5, 0.25, 0.0):
            S[f"lo_{flag}_x{mult:g}"] = {"kind": "info_flag", "flag": flag, "mult": mult}
        # PAIRING-PRESERVING PLACEBO: same prevalence, zero information
        for ui, uk in enumerate(("u", "u2", "u3")):
            S[f"PLACEBO_{flag}_x0.5_{uk}"] = {"kind": "rand_flag", "p": prev[flag],
                                              "mult": 0.5, "key": uk}
        # DIRECTION CONTROL: shrink the HIGH-information rows instead (should be worse)
        S[f"INV_{flag}_x0.5"] = {"kind": "info_flag_inv", "flag": flag, "mult": 0.5}
    # continuous information score
    S["lo_score_a"] = {"kind": "info_score", "floor": 0.5,
                       "terms": [("n_milb_seasons_s", 0.5), ("n_sources_s", 0.3),
                                 ("n_tools_s", 0.2)]}
    S["lo_score_b"] = {"kind": "info_score", "floor": 0.25,
                       "terms": [("n_milb_seasons_s", 0.5), ("n_sources_s", 0.3),
                                 ("n_tools_s", 0.2)]}
    S["PLACEBO_score_a"] = {"kind": "info_score", "floor": 0.5,
                            "terms": [("u", 0.5), ("u2", 0.3), ("u3", 0.2)]}
    # ---------- (d) tier-varying lambda ----------
    S["tier_hi_more"] = {"kind": "tier_mult", "map": {"lo": 0.75, "fringe": 0.9,
                                                      "mid": 1.0, "hi": 1.0}}
    S["tier_lo_more"] = {"kind": "tier_mult", "map": {"lo": 1.0, "fringe": 1.0,
                                                      "mid": 0.9, "hi": 0.75}}
    S["tier_free_A"] = {"kind": "tier", "map": {"lo": 0.5, "fringe": 0.7,
                                                "mid": 0.85, "hi": 0.9}}
    S["tier_free_B"] = {"kind": "tier", "map": {"lo": 0.9, "fringe": 0.85,
                                                "mid": 0.7, "hi": 0.5}}
    S["PLACEBO_tier_rand"] = {"kind": "rand_tier", "map": {"lo": 0.5, "fringe": 0.7,
                                                           "mid": 0.85, "hi": 0.9}}
    # global lambda grid (is the shipped pair near the optimum of THIS evaluator?)
    for lh in (0.5, 0.63, 0.7, 0.85, 1.0):
        for lp in (0.5, 0.63, 0.85, 1.0):
            S[f"lam_h{lh:g}_p{lp:g}"] = {"kind": "side_lam", "lam": {"hit": lh, "pit": lp}}
    return S


def _blend2(recs, sc):
    """Extension of _frontier_shrink.blend with the placebo kinds."""
    kind = sc["kind"]
    if kind in ("global", "info_flag", "info_flag_inv", "tier", "tier_mult", "side_lam"):
        return blend(recs, sc)
    out = np.empty(len(recs))
    for i, r in enumerate(recs):
        lam = LAM[r["side"]]
        if kind == "rand_flag":
            if r["info"][sc["key"]] < sc["p"]:
                lam *= sc["mult"]
        elif kind == "info_score":
            s = 0.0
            for k, wgt in sc["terms"]:
                s += wgt * _iscore(r["info"], k)
            lam = lam * (sc["floor"] + (1 - sc["floor"]) * max(0.0, min(1.0, s)))
        elif kind == "rand_tier":
            u = r["info"]["u"]
            t = "lo" if u < .25 else "fringe" if u < .5 else "mid" if u < .75 else "hi"
            lam = sc["map"][t]
        else:
            raise ValueError(kind)
        out[i] = (1 - lam) * r["cons"] + lam * r["mod"]
    return out


def _iscore(info, k):
    if k == "n_milb_seasons_s":
        return min(1.0, info["n_milb_seasons"] / 3.0)
    if k == "n_sources_s":
        return min(1.0, info["n_sources"] / 2.0)
    if k == "n_tools_s":
        return min(1.0, info["n_tools"] / 2.0)
    return info[k]


def main(B=400):
    t0 = time.time()
    pool = load_pool()
    recs, _ = score_records(pool, BASE_KEYS, SHIPPED_CFG)
    prev = {f: float(np.mean([r["info"][f] for r in recs]))
            for f in ("milb_missing", "single_source", "thin_milb", "no_tools")}
    print(f"n={len(recs)}  flag prevalence on scored rows: "
          + "  ".join(f"{k}={v:.3f}" for k, v in prev.items()), flush=True)
    print("tier counts:", {t: sum(1 for r in recs if _tier(r["fv"]) == t)
                           for t in ("lo", "fringe", "mid", "hi")})
    S = schemes(prev)

    point = {nm: block_rho(recs, _blend2(recs, sc)) for nm, sc in S.items()}
    pauc = {nm: block_auc(recs, _blend2(recs, sc)) for nm, sc in S.items()}
    print("\n== point block_rho by blend scheme ==")
    for nm in S:
        print(f"  {nm:28s} {point[nm]:.5f}  d={point[nm]-point['global']:+.5f}"
              f"   auc={pauc[nm]:.4f} d={pauc[nm]-pauc['global']:+.4f}")
    print(f"[{time.time()-t0:.0f}s]", flush=True)

    # ---------- paired refit bootstrap ----------
    boots = {nm: [] for nm in S}
    rng = random.Random(4242)
    for b in range(B):
        rp = resample_pool(pool, rng)
        rr, _ = score_records(rp, BASE_KEYS, SHIPPED_CFG)
        prev_b = {f: float(np.mean([r["info"][f] for r in rr])) for f in prev}
        Sb = schemes(prev_b)
        for nm, sc in Sb.items():
            boots[nm].append(block_rho(rr, _blend2(rr, sc)))
        if (b + 1) % 50 == 0:
            print(f"[{time.time()-t0:.0f}s] boot {b+1}/{B}", flush=True)

    base = np.array(boots["global"], dtype=float)
    print(f"\n== paired refit bootstrap (B={B}) ==")
    print(f"{'scheme':28s} {'delta':>9s} {'bmean':>9s} {'sd':>8s} {'CI95lo':>9s} "
          f"{'CI95hi':>9s} {'P(d>0)':>7s}")
    res = {}
    for nm in S:
        c = np.array(boots[nm], dtype=float)
        d = c - base
        sd = float(d.std(ddof=1))
        res[nm] = {"delta": round(point[nm] - point["global"], 5),
                   "bmean": round(float(d.mean()), 5), "sd": round(sd, 5),
                   "ci95": [round(float(np.percentile(d, 2.5)), 5),
                            round(float(np.percentile(d, 97.5)), 5)],
                   "p_gt0": round(float((d > 0).mean()), 3),
                   "mde95_80": round(2.49 * sd, 5),
                   "auc_delta": round(pauc[nm] - pauc["global"], 5)}
        r = res[nm]
        print(f"{nm:28s} {r['delta']:>9.5f} {r['bmean']:>9.5f} {r['sd']:>8.5f} "
              f"{r['ci95'][0]:>9.5f} {r['ci95'][1]:>9.5f} {r['p_gt0']:>7.3f}")

    plac = [nm for nm in S if nm.startswith("PLACEBO")]
    pv = np.array([res[nm]["delta"] for nm in plac])
    print(f"\nPLACEBO band (n={len(plac)}): mean {pv.mean():+.5f} sd {pv.std(ddof=1):.5f} "
          f"max|d| {np.abs(pv).max():.5f}")

    out = {"n": len(recs), "B": B, "prevalence": prev, "lam": LAM,
           "point": {k: round(v, 5) for k, v in point.items()},
           "auc": {k: round(v, 5) for k, v in pauc.items()},
           "bootstrap": res,
           "placebo_band": {"n": len(plac), "mean": round(float(pv.mean()), 5),
                            "sd": round(float(pv.std(ddof=1)), 5),
                            "max_abs": round(float(np.abs(pv).max()), 5)}}
    (OUT / "_scratch_shrink_bd.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote", OUT / "_scratch_shrink_bd.json", f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(B=int(sys.argv[1]) if len(sys.argv) > 1 else 400)
