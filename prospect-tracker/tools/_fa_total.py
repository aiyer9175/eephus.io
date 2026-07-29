"""T1.3 scoring - the TOTAL, not the marginals.

PRE-REGISTERED PREDICTION (written before the run, see the report):
  total-interval coverage under sum-of-quantiles is ABOVE nominal (over-wide)
  while per-year SURVIVED coverage is far below it.
"survived" = the seasons the player actually appeared in, which is the slice a
reader looks at; the pooled Gate-1 coverage scores absences as WAR 0 and that
is what holds its marginal at nominal.

Usage: python tools/_fa_total.py [B]
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import _fa_rho as rho                                        # noqa: E402

HORIZONS = (3, 5)


def _mean(v):
    v = list(v)
    return math.fsum(float(x) for x in v) / len(v) if v else None


def rows_for(panel, h: int, min_war1: float = 0.0):
    out = []
    for r in panel:
        if not r.get("p10") or not r.get("p90"):
            continue
        act = r["act"][:h]
        if any(a is None for a in act) or len(act) < h:
            continue
        if (r.get("war1") or 0.0) < min_war1:
            continue
        out.append({"path": r["path"][:h], "p10": r["p10"][:h],
                    "p90": r["p90"][:h], "act": act, "anchor": r["anchor"],
                    "side": r["side"], "war1": r["war1"]})
    return out


def score(rows, h: int, draws: int = 4000, rho_v: float | None = None) -> dict:
    import fa_calibration as fc
    import fa_mc
    import numpy as np
    rv = fa_mc.RHO if rho_v is None else rho_v
    soq, mc = [], []
    per_year_all, per_year_surv = [], []
    for r in rows:
        y = float(sum(r["act"]))
        lo_s, hi_s = float(sum(r["p10"])), float(sum(r["p90"]))
        mid = float(sum(r["path"]))
        soq.append({"y": y, "q": {0.10: lo_s, 0.50: mid, 0.90: hi_s}})
        sims = fa_mc.simulate(r["path"], r["p10"], r["p90"], h,
                              draws=draws, rho=rv)
        tot = sims.sum(axis=1)
        # Round to the SERVED precision (paths are round(w, 2)). Without it
        # the MC and the sum-of-quantiles disagree only at the atom at 0: a
        # player who never plays again has y = 0 exactly and sum(p10) = 0.00
        # exactly, so SoQ scores him covered while an MC q10 of 0.0008 does
        # not. Verified: at rho = 1.0 the MC reproduces sum(p10)/sum(p90) on
        # 200 of 200 sampled rows to within 5%.
        mc.append({"y": y,
                   "q": {0.10: round(float(np.quantile(tot, 0.10)), 2),
                         0.50: round(float(np.quantile(tot, 0.50)), 2),
                         0.90: round(float(np.quantile(tot, 0.90)), 2)}})
        for t in range(h):
            row = {"y": r["act"][t],
                   "q": {0.10: r["p10"][t], 0.90: r["p90"][t]}}
            per_year_all.append(row)
            if r["act"][t] != 0.0:              # appeared
                per_year_surv.append(row)
    return {
        "h": h, "n": len(rows), "rho": rv,
        "soq": {"cov": fc.coverage(soq)["coverage"],
                "crps": _mean(fc.crps_from_quantiles(r["y"], r["q"]) for r in soq),
                "width": _mean(r["q"][0.90] - r["q"][0.10] for r in soq),
                "pin_avg": _mean(
                    (fc.pinball(r["y"], r["q"][0.10], 0.10)
                     + fc.pinball(r["y"], r["q"][0.90], 0.90)) / 2 for r in soq)},
        "mc": {"cov": fc.coverage(mc)["coverage"],
               "crps": _mean(fc.crps_from_quantiles(r["y"], r["q"]) for r in mc),
               "width": _mean(r["q"][0.90] - r["q"][0.10] for r in mc),
               "pin_avg": _mean(
                   (fc.pinball(r["y"], r["q"][0.10], 0.10)
                    + fc.pinball(r["y"], r["q"][0.90], 0.90)) / 2 for r in mc)},
        "per_year_all_cov": fc.coverage(per_year_all)["coverage"],
        "per_year_all_n": len(per_year_all),
        "per_year_survived_cov": fc.coverage(per_year_surv)["coverage"],
        "per_year_survived_n": len(per_year_surv),
    }


def _one_draw(args):
    seed, h, draws = args
    import random
    rng = random.Random(seed)
    panel = rho.load()
    rows = rows_for(panel, h)
    # stratified-by-anchor resample of the WHOLE panel
    from collections import defaultdict
    by = defaultdict(list)
    for r in rows:
        by[r["anchor"]].append(r)
    boot_rows = []
    for _a, rs in by.items():
        n = len(rs)
        boot_rows.extend(rs[rng.randrange(n)] for _ in range(n))
    s = score(boot_rows, h, draws=draws)
    return {k: s[k] for k in ("soq", "mc", "per_year_all_cov",
                              "per_year_survived_cov")}


def boot(h: int, B: int = 120, draws: int = 1500, workers: int = 6) -> dict:
    from concurrent.futures import ProcessPoolExecutor
    args = [(5000 + i, h, draws) for i in range(B)]
    out = []
    try:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_one_draw, args, chunksize=2):
                out.append(r)
    except Exception as exc:                                # noqa: BLE001
        print("pool failed (%s) -- serial" % exc, file=sys.stderr)
        out = [_one_draw(a) for a in args]
    res = {"B": len(out), "h": h}
    for k in ("cov", "crps", "width", "pin_avg"):
        d = sorted(x["mc"][k] - x["soq"][k] for x in out)
        n = len(d)
        res[k] = {"soq": _mean(x["soq"][k] for x in out),
                  "mc": _mean(x["mc"][k] for x in out),
                  "delta_mean": _mean(d), "delta_sd": statistics.pstdev(d),
                  "ci95": [d[int(0.025 * n)], d[min(n - 1, int(0.975 * n))]],
                  "mde95": 1.96 * statistics.pstdev(d),
                  "p_improves": sum(1 for v in d if v < 0) / n}
    res["per_year_all_cov"] = _mean(x["per_year_all_cov"] for x in out)
    res["per_year_survived_cov"] = _mean(x["per_year_survived_cov"] for x in out)
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "point"
    panel = rho.load()
    if cmd == "point":
        for h in HORIZONS:
            rows = rows_for(panel, h)
            print(json.dumps(score(rows, h), indent=1, default=float))
        print("-- FA-relevant slice (projected year-1 WAR >= 1.0)")
        for h in HORIZONS:
            print(json.dumps(score(rows_for(panel, h, 1.0), h), indent=1,
                             default=float))
        # rho sensitivity at h=5
        rows = rows_for(panel, 5)
        for rv in (0.0, 0.20, 0.357, 0.55, 0.80, 1.0):
            s = score(rows, 5, rho_v=rv)
            print(f"rho={rv:.3f} totalcov {s['mc']['cov']:.4f} "
                  f"crps {s['mc']['crps']:.4f} width {s['mc']['width']:.3f} "
                  f"pin {s['mc']['pin_avg']:.5f}")
    elif cmd == "boot":
        h = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        B = int(sys.argv[3]) if len(sys.argv) > 3 else 120
        print(json.dumps(boot(h, B), indent=1, default=float))
