# Step 4 / C3: is "MLB Pipeline is a more precise grader than FanGraphs" a survivorship
# artifact? Two independent probes:
#   (P1) the TRUNCATION GRADIENT the claim rests on (truncated 2017-2020 vs least-truncated
#        2021-2023, on the SHIPPED universe);
#   (P2) the direct REPAIR -- put the dropped never-debut pool (inactive.json) back and
#        re-measure the same quantity on the same players.
# Cluster bootstrap over PLAYERS (a player recurs across base years) + a paired-swap
# permutation null. ANALYSIS ONLY.
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
OUT = HERE / "_gn_out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))
import source_backtest as sb   # noqa: E402

SRC = ("fangraphs", "mlb_pipeline")
FLOOR = sb.SPEARMAN_FLOOR


def load(name):
    d = json.loads((DATA / name).read_text(encoding="utf-8"))
    return d["players"] if isinstance(d, dict) else d


def rows_for(universe, years):
    out = []
    for p in universe:
        o = sb._outcome(p)
        for y in years:
            g = sb._rater_grades_for_year(p, y)
            if g and all(s in g for s in SRC):
                out.append((p.get("player_key"), y, g["fangraphs"], g["mlb_pipeline"],
                            o["war"], o["debuted"], o["contributor"]))
    return out


def _rank(a):
    a = np.asarray(a, float)
    order = a.argsort(kind="mergesort")
    r = np.empty(len(a), float)
    r[order] = np.arange(len(a), dtype=float)
    sa = a[order]
    i = 0
    while i < len(sa):
        j = i
        while j + 1 < len(sa) and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def rho(x, y):
    if len(x) < 6:
        return None
    rx, ry = _rank(x), _rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def stats(rws, idx=None):
    a = np.asarray(rws, dtype=object)
    if idx is not None:
        a = a[idx]
    fg = np.array([r[2] for r in a], float)
    mp = np.array([r[3] for r in a], float)
    war = np.array([r[4] for r in a], float)
    rf, rm = rho(fg, war), rho(mp, war)
    if rf is None or rm is None:
        return None
    ff, fm = max(FLOOR, rf), max(FLOOR, rm)
    return {"rho_fg": rf, "rho_mp": rm, "d_rho": rf - rm,
            "w_fg": ff / (ff + fm)}


def cluster_boot(rws, B=2000, seed=17):
    rng = random.Random(seed)
    keys = np.array([r[0] for r in rws])
    uniq, inv = np.unique(keys, return_inverse=True)
    by = [np.where(inv == i)[0] for i in range(len(uniq))]
    n = len(uniq)
    acc = {"rho_fg": [], "rho_mp": [], "d_rho": [], "w_fg": []}
    for _ in range(B):
        idx = np.concatenate([by[rng.randrange(n)] for _ in range(n)])
        s = stats(rws, idx)
        if s:
            for k in acc:
                acc[k].append(s[k])
    return acc


def perm_null(rws, B=2000, seed=23):
    """Exchangeability null for 'the two graders are equally precise': independently
    swap the (fg, mp) pair within each row. Preserves both marginals and the pairing."""
    rng = random.Random(seed)
    base = [list(r) for r in rws]
    out = []
    for _ in range(B):
        sw = []
        for r in base:
            if rng.random() < 0.5:
                sw.append((r[0], r[1], r[3], r[2], r[4], r[5], r[6]))
            else:
                sw.append(tuple(r))
        s = stats(sw)
        if s:
            out.append(s["d_rho"])
    return out


def ci(v, lo=2.5, hi=97.5):
    return (float(np.percentile(v, lo)), float(np.percentile(v, hi))) if v else (None, None)


def report(label, rws, B=2000):
    s = stats(rws)
    if s is None:
        print(f"{label:>34}: UNAVAILABLE (n={len(rws)})")
        return None
    bo = cluster_boot(rws, B)
    nk = len(set(r[0] for r in rws))
    dl, dh = ci(bo["d_rho"])
    wl, wh = ci(bo["w_fg"])
    dr = sum(1 for r in rws if r[5]) / len(rws)
    print(f"{label:>34}: n={len(rws):>5} players={nk:>5} debut_rate={dr:.3f} "
          f"rho_fg={s['rho_fg']:+.4f} rho_mp={s['rho_mp']:+.4f} "
          f"d_rho={s['d_rho']:+.4f} CI[{dl:+.4f},{dh:+.4f}] "
          f"w_fg={s['w_fg']:.3f} CI[{wl:.3f},{wh:.3f}]")
    return {"label": label, "n": len(rws), "players": nk, "debut_rate": dr, **s,
            "d_rho_ci": [dl, dh], "w_fg_ci": [wl, wh]}


if __name__ == "__main__":
    TS, DEB, INA = load("timeseries.json"), load("debuts.json"), load("inactive.json")
    SHIP, REP = TS + DEB, TS + DEB + INA
    TRUNC = (2017, 2018, 2019, 2020)
    LEAST = (2021, 2022, 2023)
    res = {}

    print("=== P1. TRUNCATION GRADIENT on the SHIPPED universe (ts + debuts) ===")
    res["ship_trunc"] = report("SHIPPED 2017-2020 (truncated)", rows_for(SHIP, TRUNC))
    res["ship_least"] = report("SHIPPED 2021-2023 (least trunc)", rows_for(SHIP, LEAST))

    print("\n=== P2. SAME CUTS on the REPAIRED universe (+ inactive.json) ===")
    res["rep_trunc"] = report("REPAIRED 2017-2020", rows_for(REP, TRUNC))
    res["rep_least"] = report("REPAIRED 2021-2023", rows_for(REP, LEAST))
    res["rep_all"] = report("REPAIRED 2017-2023 pooled", rows_for(REP, TRUNC + LEAST))
    res["ship_all"] = report("SHIPPED 2017-2023 pooled", rows_for(SHIP, TRUNC + LEAST))

    print("\n=== per-year splits (>=4 required by the gate standard) ===")
    for y in range(2017, 2024):
        res[f"ship_{y}"] = report(f"SHIPPED {y}", rows_for(SHIP, (y,)), B=800)
    print()
    for y in range(2017, 2024):
        res[f"rep_{y}"] = report(f"REPAIRED {y}", rows_for(REP, (y,)), B=800)

    print("\n=== permutation null for d_rho (paired grader swap) ===")
    for lab, u, yy in (("SHIPPED 2017-2023", SHIP, TRUNC + LEAST),
                       ("REPAIRED 2017-2023", REP, TRUNC + LEAST)):
        rws = rows_for(u, yy)
        pn = perm_null(rws, 1500)
        lo, hi = ci(pn)
        obs = stats(rws)["d_rho"]
        p = float(np.mean([abs(v) >= abs(obs) for v in pn]))
        print(f"  {lab:>22}: obs d_rho={obs:+.4f}  null CI95[{lo:+.4f},{hi:+.4f}]  "
              f"two-sided p={p:.4f}")
        res[f"perm_{lab.split()[0].lower()}"] = {"obs": obs, "null_ci": [lo, hi], "p": p}

    (OUT / "surv_c3.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
