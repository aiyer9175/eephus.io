"""T1.2 (dollars side) - grade the player-specific GUARANTEE band against the
single unconditional residual band, on the Gate-2 forward chain.

Same discipline as tools/_fa_bandlab.py: paired bootstrap resampling the whole
corpus with a refit per draw, a permuted zero-information control on the same
draws, and 9 independent forward-chained winters.

Usage:
    python tools/_fa_guarband.py point
    python tools/_fa_guarband.py boot [B]
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import _fa_lab as lab                                       # noqa: E402

TEST_YEARS = lab.TEST_YEARS


def _mean(v):
    v = list(v)
    return math.fsum(float(x) for x in v) / len(v) if v else None


def chain(pool, arm: dict) -> dict:
    """Forward-chained band scoring. Metrics are on the LOG-guarantee scale
    (the scale the band is estimated on) plus dollar coverage."""
    import fa_market as fm
    import fa_calibration as fc
    lab.apply_arm(arm)
    for k, v in arm.items():
        if k in ("BAND_SCALE_GUAR", "BAND_PERMUTE_SEED", "BAND_RIDGE_GUAR"):
            setattr(fm, k, v)
    rows = []
    for W in TEST_YEARS:
        train = [s for s in pool if s["class_year"] < W]
        test = [s for s in pool if s["class_year"] == W]
        if len(train) < 100 or not test:
            continue
        dpw = fm.dollars_per_war_by_winter(train)
        model = fm.MarketModel(train, dpw)
        model.supply_by_year[W] = fm._supply(test, W)
        for s in test:
            p = model.predict(s)
            lo, hi = p.get("proj_guarantee_p10_usd"), p.get("proj_guarantee_p90_usd")
            if not lo or not hi or hi <= lo:
                continue
            act = fm._npv_of(s)
            rows.append({
                "y": math.log(act),
                "q": {0.10: math.log(lo), 0.90: math.log(hi)},
                "ratio": hi / lo,
                "act": act, "pred": p["proj_guarantee_usd"],
                "pos": fm._pos_group(s.get("position")),
                "age": s["_age"], "winter": W,
                "mega": 1 if act >= 100e6 else 0,
            })
    if not rows:
        return {}
    out = {
        "n": len(rows),
        "cov": fc.coverage(rows, 0.10, 0.90)["coverage"],
        "pin10": _mean(fc.pinball(r["y"], r["q"][0.10], 0.10) for r in rows),
        "pin90": _mean(fc.pinball(r["y"], r["q"][0.90], 0.90) for r in rows),
        "ratio_mean": _mean(r["ratio"] for r in rows),
        "ratio_sd": statistics.pstdev([r["ratio"] for r in rows]),
        "ratio_min": min(r["ratio"] for r in rows),
        "ratio_max": max(r["ratio"] for r in rows),
    }
    out["pin_avg"] = (out["pin10"] + out["pin90"]) / 2.0
    cond = {
        "pred_decile": fc.conditional_coverage(rows, lambda r: r["pred"], n_bins=10),
        "pos": fc.conditional_coverage(rows, "pos"),
        "age": fc.conditional_coverage(
            rows, lambda r: ("<28" if r["age"] < 28 else "28-31"
                             if r["age"] < 32 else "32+")),
        "mega": fc.conditional_coverage(rows, lambda r: "mega" if r["mega"] else "rest"),
    }
    devs = [c["coverage"] - 0.80 for t in cond.values() for c in t
            if c.get("coverage") is not None and c["n"] >= 25]
    out["cond_rmse"] = math.sqrt(_mean(d * d for d in devs)) if devs else None
    out["cond_maxabs"] = max((abs(d) for d in devs), default=None)
    out["cond"] = cond
    return out


ARMS = {
    "flat": {"BAND_SCALE_GUAR": False},
    "scale": {"BAND_SCALE_GUAR": True, "BAND_RIDGE_GUAR": 3.0},
    "perm": {"BAND_SCALE_GUAR": True, "BAND_RIDGE_GUAR": 3.0, "BAND_PERMUTE_SEED": 7},
}
for _r in (0.0, 0.3, 1.0, 3.0, 10.0, 30.0):
    ARMS[f"ridge{_r}"] = {"BAND_SCALE_GUAR": True, "BAND_RIDGE_GUAR": _r}
KEYS = ("pin_avg", "cov", "cond_rmse", "cond_maxabs", "ratio_sd")
BOOT_ARMS = ("flat", "scale", "perm")


def _one_draw(args):
    seed, = args
    import random
    rng = random.Random(seed)
    draw = lab._resample(lab.load(), rng)
    out = {}
    for name in BOOT_ARMS:
        arm = ARMS[name]
        if name == "perm":
            arm = {**arm, "BAND_PERMUTE_SEED": seed}
        r = chain(draw, arm)
        out[name] = {k: r.get(k) for k in KEYS}
    return out


def boot(B: int = 200, workers: int = 6) -> dict:
    from concurrent.futures import ProcessPoolExecutor
    args = [(3000 + i,) for i in range(B)]
    draws = []
    try:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_one_draw, args, chunksize=2):
                draws.append(r)
    except Exception as exc:                                # noqa: BLE001
        print("pool failed (%s) -- serial" % exc, file=sys.stderr)
        draws = [_one_draw(a) for a in args]
    res = {"B": len(draws)}
    for k in KEYS:
        d = sorted(x["scale"][k] - x["flat"][k] for x in draws
                   if x["scale"][k] is not None and x["flat"][k] is not None)
        dp = sorted(x["perm"][k] - x["flat"][k] for x in draws
                    if x["perm"][k] is not None and x["flat"][k] is not None)
        n = len(d)
        res[k] = {
            "flat_mean": _mean(x["flat"][k] for x in draws if x["flat"][k] is not None),
            "scale_mean": _mean(x["scale"][k] for x in draws if x["scale"][k] is not None),
            "delta_mean": _mean(d), "delta_sd": statistics.pstdev(d),
            "ci95": [d[int(0.025 * n)], d[min(n - 1, int(0.975 * n))]],
            "p_improves": sum(1 for v in d if v < 0) / n,
            "mde95": 1.96 * statistics.pstdev(d),
            "perm_delta_mean": _mean(dp),
            "perm_null_band95": [dp[int(0.025 * len(dp))],
                                 dp[min(len(dp) - 1, int(0.975 * len(dp)))]],
        }
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "point"
    if cmd == "point":
        pool = lab.load()
        for name, arm in ARMS.items():
            r = chain(pool, arm)
            print(name, json.dumps({k: (round(v, 5) if isinstance(v, float) else v)
                                    for k, v in r.items() if k != "cond"},
                                   default=float))
        r = chain(pool, ARMS["scale"])
        for name, tab in r["cond"].items():
            print("--", name)
            for c in tab:
                print("  ", c["bin"], "n", c["n"], "cov", c["coverage"], "z", c.get("z"))
    elif cmd == "boot":
        B = int(sys.argv[2]) if len(sys.argv) > 2 else 200
        print(json.dumps(boot(B), indent=1, default=float))
