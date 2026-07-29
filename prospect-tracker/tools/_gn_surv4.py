# C3 follow-up: the claimed w_fg magnitudes (0.189 truncated vs 0.511 least-truncated)
# are NOT reproducible as a Spearman share, so test the only estimator class that could
# produce them -- a STACKING weight (the convex blend weight the outcome prefers) -- and
# then ask the survivorship question OF THAT ESTIMATOR: does restoring the dropped
# never-debut pool move it? Plus a zero-information control to calibrate the scale.
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
OUT = HERE / "_gn_out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))
from _gn_surv3 import load, rows_for, ci   # noqa: E402

GRID = np.linspace(0.0, 1.0, 51)


def _rho(x, wr):
    rx = rankdata(x)
    rx = rx - rx.mean()
    d = np.sqrt((rx * rx).sum())
    return float((rx * wr).sum() / d) if d > 0 else 0.0


def w_stack_rho(fg, mp, war):
    wr = rankdata(war)
    wr = wr - wr.mean()
    n = np.sqrt((wr * wr).sum())
    if n == 0:
        return 0.5, 0.0
    wr = wr / n
    best, bw = -2.0, 0.5
    for w in GRID:
        r = _rho(w * fg + (1 - w) * mp, wr)
        if r > best:
            best, bw = r, float(w)
    return bw, best


def w_stack_ols(fg, mp, war):
    X = np.column_stack([fg, mp, np.ones(len(fg))])
    try:
        b = np.linalg.lstsq(X, war, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    a, c = max(0.0, b[0]), max(0.0, b[1])
    return float(a / (a + c)) if (a + c) > 0 else 0.5


def arrays(rws):
    return (np.array([r[2] for r in rws], float),
            np.array([r[3] for r in rws], float),
            np.array([r[4] for r in rws], float))


def line(label, rws, B=600, seed=17):
    fg, mp, war = arrays(rws)
    wr, _ = w_stack_rho(fg, mp, war)
    wo = w_stack_ols(fg, mp, war)
    rng = random.Random(seed)
    keys = np.array([r[0] for r in rws])
    uniq, inv = np.unique(keys, return_inverse=True)
    by = [np.where(inv == i)[0] for i in range(len(uniq))]
    n = len(uniq)
    br, bo = [], []
    for _ in range(B):
        idx = np.concatenate([by[rng.randrange(n)] for _ in range(n)])
        br.append(w_stack_rho(fg[idx], mp[idx], war[idx])[0])
        v = w_stack_ols(fg[idx], mp[idx], war[idx])
        if v is not None:
            bo.append(v)
    rl, rh = ci(br)
    ol, oh = ci(bo)
    dr = sum(1 for r in rws if r[5]) / len(rws)
    print(f"{label:>28}: n={len(rws):>5} debut={dr:.3f} "
          f"w_fg[rho-stack]={wr:.3f} CI[{rl:.3f},{rh:.3f}]  "
          f"w_fg[OLS-stack]={wo:.3f} CI[{ol:.3f},{oh:.3f}]", flush=True)
    return {"n": len(rws), "debut_rate": dr, "w_rho": wr, "w_rho_ci": [rl, rh],
            "w_ols": wo, "w_ols_ci": [ol, oh]}


if __name__ == "__main__":
    TS, DEB, INA = load("timeseries.json"), load("debuts.json"), load("inactive.json")
    SHIP, REP = TS + DEB, TS + DEB + INA
    TRUNC, LEAST = (2017, 2018, 2019, 2020), (2021, 2022, 2023)
    res = {}
    print("=== stacking weight: truncation gradient, SHIPPED universe ===", flush=True)
    res["ship_trunc"] = line("SHIPPED 2017-2020", rows_for(SHIP, TRUNC))
    res["ship_least"] = line("SHIPPED 2021-2023", rows_for(SHIP, LEAST))
    print("\n=== same cuts, dropped never-debut pool PUT BACK ===", flush=True)
    res["rep_trunc"] = line("REPAIRED 2017-2020", rows_for(REP, TRUNC))
    res["rep_least"] = line("REPAIRED 2021-2023", rows_for(REP, LEAST))
    res["ship_all"] = line("SHIPPED 2017-2023", rows_for(SHIP, TRUNC + LEAST))
    res["rep_all"] = line("REPAIRED 2017-2023", rows_for(REP, TRUNC + LEAST))

    print("\n=== zero-information control (FanGraphs column row-permuted) ===", flush=True)
    rws = rows_for(SHIP, TRUNC + LEAST)
    rng = random.Random(101)
    perm = list(range(len(rws)))
    rng.shuffle(perm)
    ctl = [(r[0], r[1], rws[perm[i]][2], r[3], r[4], r[5], r[6]) for i, r in enumerate(rws)]
    res["control"] = line("CONTROL fg-permuted", ctl, B=300)

    (OUT / "surv_c3_stack.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
