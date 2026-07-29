# SCRATCH: FINAL evidence run for the consensus-anchor lane.
#   Arms: shipped | pairgap (TARGET-FREE outlet-scale de-bias) | cov_era (fitted,
#         era-controlled coverage-pattern offsets) | cov_nonone (fitted, no era control)
#   Controls: rank-identical twin (affine), pattern-permutation placebo (>=300 draws),
#             shuffled-train-target null.
#   Uncertainty: paired refit bootstrap, resample WHOLE pool within (side, decision_year),
#             refit anchor + ridge + OLS + calibration every draw.
#   Splits: pooled 2020-2024 + 22 per-(side, origin) blocks 2014-2024.
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import _frontier_anchor_level2 as L

OUT = Path(__file__).resolve().parent / "_frontier_out"
OUT.mkdir(exist_ok=True)
ARMS = ["shipped", "pairgap", "cov_era", "cov_nonone"]
SEED = 20260724


def boot(sides, arms, B, rng, legs=("blend", "cons", "ridge"), origins=L.ORG, lams=None):
    if lams:
        L.LAM.update(lams)
    st = L.strata(sides)
    draws = []
    for _ in range(B):
        r = L.evaluate(L.resample(sides, st, rng), arms, origins=origins)
        if r is not None:
            draws.append(r)
    out = {}
    for k in arms:
        if k == "shipped":
            continue
        for leg in legs:
            d = np.array([x[f"{k}.{leg}"] - x[f"shipped.{leg}"] for x in draws])
            d = d[np.isfinite(d)]
            out[f"{k}.{leg}"] = {
                "mean": float(d.mean()), "sd": float(d.std(ddof=1)),
                "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
                "p_gt0": float((d > 0).mean()), "mde95": float(1.645 * d.std(ddof=1)),
                "B": int(len(d))}
    return out


def main():
    t0 = time.time()
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    BN = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    sides = {s: L.load(s) for s in ("hit", "pit")}
    res = {"config": {"B_boot": B, "B_null": BN, "origins": list(L.ORG), "lam": dict(L.LAM),
                      "seed": SEED}}

    # ---------------- 1. POINT, pooled + per side
    print("=" * 78)
    print("1. POINT ESTIMATES -- recommended evaluator (both sides, (side x origin)")
    print("   percentile blocks, train = production pool, test = debuted, origins 2020-2024)")
    pt = L.evaluate(sides, ARMS)
    res["point_pooled"] = {k: float(v) for k, v in pt.items()}
    print(f"   pooled n={pt['n']}")
    for k in ARMS:
        print(f"     {k:11s} blend {pt[k+'.blend']:.4f} (d {pt[k+'.blend']-pt['shipped.blend']:+.4f})"
              f"  cons {pt[k+'.cons']:.4f} (d {pt[k+'.cons']-pt['shipped.cons']:+.4f})"
              f"  ridge {pt[k+'.ridge']:.4f} (d {pt[k+'.ridge']-pt['shipped.ridge']:+.4f})")
    for s in ("hit", "pit"):
        r = L.evaluate({s: sides[s]}, ARMS)
        res[f"point_{s}"] = {k: float(v) for k, v in r.items()}
        print(f"   {s} only n={r['n']}: " + " | ".join(
            f"{k} {r[k+'.blend']:.4f} (d {r[k+'.blend']-r['shipped.blend']:+.4f})" for k in ARMS))

    # ---------------- 2. rank-identical twin control
    print("\n2. RANK-IDENTICAL TWIN CONTROL (anchor -> 3.7*anchor - 111, must read 0.0000)")
    save = L.anchor

    def twin(kind, a, tri, tei, **kw):
        atr, ate = save("shipped", a, tri, tei, **kw)
        return 3.7 * atr - 111.0, 3.7 * ate - 111.0
    L.anchor = lambda kind, a, tri, tei, **kw: (twin(kind, a, tri, tei, **kw)
                                                if kind == "twin" else save(kind, a, tri, tei, **kw))
    rt = L.evaluate(sides, ["shipped", "twin"])
    print(f"     twin blend delta {rt['twin.blend']-rt['shipped.blend']:+.6f}  "
          f"cons {rt['twin.cons']-rt['shipped.cons']:+.6f}  "
          f"ridge {rt['twin.ridge']-rt['shipped.ridge']:+.6f}")
    res["twin_delta"] = {leg: float(rt[f"twin.{leg}"] - rt[f"shipped.{leg}"])
                         for leg in ("blend", "cons", "ridge")}
    L.anchor = save

    # ---------------- 3. paired refit bootstrap
    print(f"\n3. PAIRED REFIT BOOTSTRAP (resample pool within (side,decision_year), refit"
          f" anchor+ridge+OLS each draw), B={B}")
    rng = np.random.default_rng(SEED)
    bp = boot(sides, ARMS, B, rng)
    res["boot_pooled"] = bp
    for k in ARMS:
        if k == "shipped":
            continue
        for leg in ("blend", "cons", "ridge"):
            e = bp[f"{k}.{leg}"]
            print(f"     {k:11s} {leg:6s} point {pt[f'{k}.{leg}']-pt[f'shipped.{leg}']:+.4f} "
                  f"mean {e['mean']:+.4f} sd {e['sd']:.4f} CI95 [{e['lo']:+.4f},{e['hi']:+.4f}] "
                  f"P(>0) {e['p_gt0']:.3f} MDE95 {e['mde95']:.4f}")
    for s in ("hit", "pit"):
        rng2 = np.random.default_rng(SEED + 11)
        bs = boot({s: sides[s]}, ARMS, max(400, B // 4), rng2, legs=("blend",))
        res[f"boot_{s}"] = bs
        print(f"     [{s} only] " + " | ".join(
            f"{k} {bs[k+'.blend']['mean']:+.4f} sd {bs[k+'.blend']['sd']:.4f} "
            f"P {bs[k+'.blend']['p_gt0']:.3f}" for k in ARMS if k != "shipped"))

    # ---------------- 4. null bands
    print(f"\n4a. NULL BAND -- coverage-pattern labels PERMUTED (identical group sizes and")
    print(f"    identical offset magnitudes, zero information about WHICH rows), B={BN}")
    rngN = np.random.default_rng(SEED + 5)
    nb = {k: [] for k in ARMS if k != "shipped"}
    for _ in range(BN):
        r = L.evaluate(sides, ARMS, pat_perm_rng=rngN)
        for k in nb:
            nb[k].append(r[f"{k}.blend"] - r["shipped.blend"])
    for k, v in nb.items():
        v = np.array(v)
        real = pt[f"{k}.blend"] - pt["shipped.blend"]
        res.setdefault("null_pattern_perm", {})[k] = {
            "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
            "p95": float(np.percentile(v, 95)), "max": float(v.max()),
            "max_abs": float(np.abs(v).max()), "real": float(real),
            "p_ge_real": float((v >= real).mean()), "B": int(len(v))}
        e = res["null_pattern_perm"][k]
        print(f"     {k:11s} null mean {e['mean']:+.5f} sd {e['sd']:.5f} p95 {e['p95']:+.5f} "
              f"max {e['max']:+.5f} | REAL {real:+.4f} -> p(null>=real) {e['p_ge_real']:.4f}")

    print(f"\n4b. NULL BAND -- TRAIN-FOLD target shuffled (every fitted parameter becomes")
    print(f"    noise; the SCORED target stays real, so the pairing is preserved), B={BN}")
    rngS = np.random.default_rng(SEED + 6)
    nb2 = {k: [] for k in ARMS if k != "shipped"}
    for _ in range(BN):
        r = L.evaluate(sides, ARMS, y_shuf_rng=rngS)
        for k in nb2:
            nb2[k].append(r[f"{k}.blend"] - r["shipped.blend"])
    for k, v in nb2.items():
        v = np.array(v)
        real = pt[f"{k}.blend"] - pt["shipped.blend"]
        res.setdefault("null_target_shuffle", {})[k] = {
            "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
            "p95": float(np.percentile(v, 95)), "real": float(real),
            "p_ge_real": float((v >= real).mean()), "B": int(len(v))}
        e = res["null_target_shuffle"][k]
        print(f"     {k:11s} null mean {e['mean']:+.5f} sd {e['sd']:.5f} p95 {e['p95']:+.5f} "
              f"| REAL {real:+.4f} -> p(null>=real) {e['p_ge_real']:.4f}")

    # ---------------- 5. cross-split
    print("\n5. CROSS-SPLIT: per-(side x origin) blend deltas, 22 blocks 2014-2024")
    pb = {}
    for s in ("hit", "pit"):
        for Y in range(2014, 2025):
            r = L.evaluate({s: sides[s]}, ARMS, origins=(Y,))
            if r is not None:
                pb[f"{s}{Y}"] = {k: float(r[f"{k}.blend"]) for k in ARMS}
    res["per_block"] = pb
    for k in ARMS:
        if k == "shipped":
            continue
        d = np.array([v[k] - v["shipped"] for v in pb.values()])
        d = d[np.isfinite(d)]
        se = d.std(ddof=1) / np.sqrt(len(d))
        res.setdefault("per_block_summary", {})[k] = {
            "mean": float(d.mean()), "se": float(se), "t": float(d.mean() / se),
            "pos": int((d > 0).sum()), "neg": int((d < 0).sum()), "n": int(len(d))}
        print(f"     {k:11s} mean {d.mean():+.4f} se {se:.4f} t {d.mean()/se:+.2f} "
              f"signs {int((d>0).sum())}+/{int((d<0).sum())}- nblk={len(d)}")

    # ---------------- 6. lambda sensitivity
    print("\n6. LAMBDA SENSITIVITY (pit live lam 0.54 instead of the pinned 0.63)")
    orig = dict(L.LAM)
    for lam_pit in (0.54, 0.63, 0.70):
        L.LAM["pit"] = lam_pit
        r = L.evaluate(sides, ARMS)
        print(f"     lam_pit={lam_pit}: " + " | ".join(
            f"{k} d {r[k+'.blend']-r['shipped.blend']:+.4f}" for k in ARMS if k != "shipped"))
        res.setdefault("lam_sens", {})[str(lam_pit)] = {
            k: float(r[f"{k}.blend"] - r["shipped.blend"]) for k in ARMS if k != "shipped"}
    L.LAM.update(orig)

    # ---------------- 7. origin-window sensitivity
    print("\n7. ORIGIN-WINDOW SENSITIVITY")
    for name, org in (("2020-2023 (SCORED_YEARS)", tuple(range(2020, 2024))),
                      ("2020-2024 (recommended)", tuple(range(2020, 2025))),
                      ("2018-2024", tuple(range(2018, 2025)))):
        r = L.evaluate(sides, ARMS, origins=org)
        print(f"     {name:26s} n={r['n']:4d} " + " | ".join(
            f"{k} d {r[k+'.blend']-r['shipped.blend']:+.4f}" for k in ARMS if k != "shipped"))
        res.setdefault("origin_sens", {})[name] = {
            "n": int(r["n"]),
            **{k: float(r[f"{k}.blend"] - r["shipped.blend"]) for k in ARMS if k != "shipped"}}

    json.dump(res, open(OUT / "_anchor_final.json", "w"), indent=1, default=float)
    print("\nelapsed", round(time.time() - t0, 1), "s")


def _eval_shuffled(sides, sh, arms):
    """Evaluate with anchor parameters fit against a within-year SHUFFLED train target
    while the scored target stays real."""
    real_y = {}
    for s in sides:
        real_y[s] = sides[s]["y"]
        sides[s] = dict(sides[s])
        sides[s]["y"] = sh[s]["y_shuf"]
    try:
        # anchors get the shuffled y; but ridge/OLS must see the shuffled y too for a
        # consistent null (this is the "all fitted structure is noise" band).
        r = L.evaluate(sides, arms)
    finally:
        for s in sides:
            sides[s]["y"] = real_y[s]
    return r


if __name__ == "__main__":
    main()
