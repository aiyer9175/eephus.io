# C3 adjudication, paired. Two deltas on ONE bootstrap of the repaired universe so the
# comparisons are paired (the shipped sample is a SUBSET of the repaired one):
#   D_surv  = w_fg(repaired) - w_fg(shipped)      <- the survivorship effect itself
#   D_grad  = w_fg(2021-2023) - w_fg(2017-2020)   <- the gradient the claim rests on,
#                                                    measured on BOTH universes
# Plus per-year splits (7 time splits) and a permutation null for the gradient.
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "_gn_out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))
from _gn_surv3 import load, rows_for, ci   # noqa: E402
from _gn_surv4 import w_stack_ols, arrays   # noqa: E402

TRUNC, LEAST = (2017, 2018, 2019, 2020), (2021, 2022, 2023)


def w_of(rws):
    if len(rws) < 40:
        return None
    fg, mp, war = arrays(rws)
    return w_stack_ols(fg, mp, war)


def paired_boot(rep_rows, ship_keys, B=2000, seed=31):
    """Resample PLAYERS from the repaired universe; per draw compute w_fg on the
    repaired rows and on the shipped-subset rows of the SAME draw."""
    rng = random.Random(seed)
    keys = np.array([r[0] for r in rep_rows])
    uniq, inv = np.unique(keys, return_inverse=True)
    by = [np.where(inv == i)[0] for i in range(len(uniq))]
    n = len(uniq)
    arr = np.array(rep_rows, dtype=object)
    in_ship = np.array([r[0] in ship_keys for r in rep_rows])
    out = {"rep": [], "ship": [], "d": []}
    for _ in range(B):
        idx = np.concatenate([by[rng.randrange(n)] for _ in range(n)])
        rr = list(arr[idx])
        ss = list(arr[idx[in_ship[idx]]])
        a, b = w_of(rr), w_of(ss)
        if a is None or b is None:
            continue
        out["rep"].append(a); out["ship"].append(b); out["d"].append(a - b)
    return out


def grad_boot(rows_t, rows_l, B=2000, seed=41):
    """Independent cluster bootstrap of each cut -> CI on the gradient."""
    rng = random.Random(seed)
    def draw(rws):
        keys = np.array([r[0] for r in rws])
        uniq, inv = np.unique(keys, return_inverse=True)
        by = [np.where(inv == i)[0] for i in range(len(uniq))]
        arr = np.array(rws, dtype=object)
        n = len(uniq)
        return arr, by, n
    at, bt, nt = draw(rows_t)
    al, bl, nl = draw(rows_l)
    d = []
    for _ in range(B):
        it = np.concatenate([bt[rng.randrange(nt)] for _ in range(nt)])
        il = np.concatenate([bl[rng.randrange(nl)] for _ in range(nl)])
        wt, wl = w_of(list(at[it])), w_of(list(al[il]))
        if wt is not None and wl is not None:
            d.append(wl - wt)
    return d


if __name__ == "__main__":
    TS, DEB, INA = load("timeseries.json"), load("debuts.json"), load("inactive.json")
    SHIP, REP = TS + DEB, TS + DEB + INA
    ship_keys = {p["player_key"] for p in SHIP}
    res = {}

    print("=== D_surv: does restoring the dropped pool move w_fg? (paired) ===")
    for lab, yy in (("2017-2020 truncated", TRUNC), ("2021-2023 least trunc", LEAST),
                    ("2017-2023 pooled", TRUNC + LEAST)):
        rep = rows_for(REP, yy)
        bo = paired_boot(rep, ship_keys, B=1200)
        lo, hi = ci(bo["d"])
        print(f"  {lab:>22}: w_ship={np.mean(bo['ship']):.3f} w_rep={np.mean(bo['rep']):.3f} "
              f"D_surv={np.mean(bo['d']):+.3f} CI95[{lo:+.3f},{hi:+.3f}]")
        res[f"dsurv_{yy[0]}"] = {"w_ship": float(np.mean(bo["ship"])),
                                 "w_rep": float(np.mean(bo["rep"])),
                                 "d": float(np.mean(bo["d"])), "ci": [lo, hi]}

    print("\n=== D_grad: the truncation gradient, on each universe ===")
    for lab, uni in (("SHIPPED", SHIP), ("REPAIRED", REP)):
        rt, rl = rows_for(uni, TRUNC), rows_for(uni, LEAST)
        wt, wl = w_of(rt), w_of(rl)
        d = grad_boot(rt, rl, B=1200)
        lo, hi = ci(d)
        print(f"  {lab:>9}: w_trunc={wt:.3f} w_least={wl:.3f} "
              f"D_grad={wl-wt:+.3f} boot CI95[{lo:+.3f},{hi:+.3f}]")
        res[f"dgrad_{lab.lower()}"] = {"w_trunc": wt, "w_least": wl,
                                       "d": wl - wt, "ci": [lo, hi]}

    print("\n=== per-year w_fg (7 time splits) ===")
    print(f"{'year':>5} {'debut_ship':>11} {'w_ship':>7} {'debut_rep':>10} {'w_rep':>7}")
    for y in range(2017, 2024):
        rs, rr = rows_for(SHIP, (y,)), rows_for(REP, (y,))
        ws, wrp = w_of(rs), w_of(rr)
        ds = sum(1 for r in rs if r[5]) / len(rs)
        dr = sum(1 for r in rr if r[5]) / len(rr)
        print(f"{y:>5} {ds:>11.3f} {ws:>7.3f} {dr:>10.3f} {wrp:>7.3f}")
        res[f"year_{y}"] = {"debut_ship": ds, "w_ship": ws, "debut_rep": dr, "w_rep": wrp}

    (OUT / "surv_c3_paired.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
