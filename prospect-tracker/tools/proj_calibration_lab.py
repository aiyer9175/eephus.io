# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Level calibration of the CHAMPION projection engine, by horizon and by
player class (projections-lane priority 3, 2026-07-24).

Forward-chained exactly like proj_eval: for base B the aging curves and WAR
map are fit on seasons <= B-1 and the path is scored against actual bWAR
(absent season = 0). Cells: side x horizon x {age band, projected-PT tier,
role, ex-ante star slice}. Reports bias (pred - actual), MAE and n, plus a
paired cluster bootstrap over players for the cells that a fix would key
on, so no cell is read as real below its own sampling noise.

Run: python tools/proj_calibration_lab.py --bases 2014,...,2021
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_market as fm            # noqa: E402
import fa_projection as fp        # noqa: E402

H = 5


def age_band(a):
    if a is None:
        return "?"
    if a <= 24:
        return "<=24"
    if a <= 27:
        return "25-27"
    if a <= 30:
        return "28-30"
    if a <= 33:
        return "31-33"
    return "34+"


def pt_tier(side, pt):
    if side == "hit":
        return "hi" if pt >= 500 else ("mid" if pt >= 250 else "lo")
    return "hi" if pt >= 600 else ("mid" if pt >= 300 else "lo")


def collect(corpus, bases):
    league = corpus["league"]
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    war_actual: dict[tuple, float] = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
                if r.get("war") is not None:
                    k = (r["mlbam"], r["season"])
                    war_actual[k] = war_actual.get(k, 0.0) + r["war"]
    rows = []
    for B in bases:
        curves, war_map = fp.fitted_models(corpus, B - 1)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                ar = next((h for h in hist if h.get("age")), None)
                if ar is None:
                    continue
                age = ar["age"] + (B - ar["season"])
                proj = fp.project_player(hist, side, B, curves, league, age)
                if proj is None:
                    continue
                war1 = fp.war_from_projection(proj, side, war_map, league, B)
                role = fp.profile_role(hist, side, proj["role"], league)
                path = fm._decay_path(war1, proj["pt_proj"], side, role, age, curves)
                base_act = war_actual.get((mlbam, B - 1))
                star = base_act is not None and base_act >= 4.0
                for h in range(1, H + 1):
                    tgt = B + h - 1
                    if tgt > corpus["last"] - 1:
                        continue
                    rows.append({
                        "B": B, "side": side, "m": mlbam, "h": h,
                        "pred": path[h - 1], "act": war_actual.get((mlbam, tgt), 0.0),
                        "survived": (mlbam, tgt) in war_actual,
                        "age": age + h - 1, "aband": age_band(age + h - 1),
                        "pt": pt_tier(side, proj["pt_proj"]),
                        "role": proj["role"], "star": star})
    return rows


def cell(rows, sel):
    idx = [i for i in sel]
    if not idx:
        return None
    n = len(idx)
    return {"n": n,
            "bias": round(sum(rows[i]["pred"] - rows[i]["act"] for i in idx) / n, 4),
            "mae": round(sum(abs(rows[i]["pred"] - rows[i]["act"]) for i in idx) / n, 4),
            "pred": round(sum(rows[i]["pred"] for i in idx) / n, 4),
            "act": round(sum(rows[i]["act"] for i in idx) / n, 4)}


def boot_bias(rows, sel, draws, seed):
    """Cluster bootstrap over players for one cell's bias."""
    by_pl = defaultdict(list)
    for i in sel:
        by_pl[rows[i]["m"]].append(i)
    pls = sorted(by_pl)
    if len(pls) < 20:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        pick = [pls[rng.randrange(len(pls))] for _ in range(len(pls))]
        idx = [i for p in pick for i in by_pl[p]]
        vals.append(sum(rows[i]["pred"] - rows[i]["act"] for i in idx) / len(idx))
    vals.sort()
    n = len(vals)
    return {"ci95": [round(vals[int(0.025 * (n - 1))], 4),
                     round(vals[int(0.975 * (n - 1))], 4)],
            "sd": round((sum((v - sum(vals) / n) ** 2 for v in vals) / (n - 1)) ** 0.5, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bases", default="2014,2015,2016,2017,2018,2019,2021")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260724)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    bases = [int(b) for b in args.bases.split(",")]
    if args.corpus:
        import pickle
        corpus = pickle.load(open(args.corpus, "rb"))
    else:
        corpus = fp.build_corpus()
    rows = collect(corpus, bases)
    print("rows", len(rows))
    res = {"bases": bases, "n_rows": len(rows), "cells": {}}

    def add(name, pred):
        sel = [i for i, r in enumerate(rows) if pred(r)]
        c = cell(rows, sel)
        if c is None:
            return
        b = boot_bias(rows, sel, args.draws, args.seed)
        if b:
            c.update(b)
            c["resolvable"] = abs(c["bias"]) > 1.96 * b["sd"]
        res["cells"][name] = c

    for h in range(1, H + 1):
        add(f"h{h}", lambda r, h=h: r["h"] == h)
        for side in ("hit", "pit"):
            add(f"h{h}:{side}", lambda r, h=h, s=side: r["h"] == h and r["side"] == s)
    for ab in ("<=24", "25-27", "28-30", "31-33", "34+"):
        add(f"age:{ab}", lambda r, a=ab: r["aband"] == a)
        for side in ("hit", "pit"):
            add(f"age:{ab}:{side}", lambda r, a=ab, s=side: r["aband"] == a and r["side"] == s)
    for t in ("lo", "mid", "hi"):
        add(f"pt:{t}", lambda r, t=t: r["pt"] == t)
        for side in ("hit", "pit"):
            add(f"pt:{t}:{side}", lambda r, t=t, s=side: r["pt"] == t and r["side"] == s)
    for role in ("C", "H", "SP", "RP"):
        add(f"role:{role}", lambda r, x=role: r["role"] == x)
    add("star", lambda r: r["star"])
    add("nonstar", lambda r: not r["star"])
    add("survived", lambda r: r["survived"])
    add("absent", lambda r: not r["survived"])
    for side in ("hit", "pit"):
        add(f"side:{side}", lambda r, s=side: r["side"] == s)
    add("all", lambda r: True)

    # age x horizon interaction (the ask: is the bias a level or a slope?)
    for ab in ("<=24", "25-27", "28-30", "31-33", "34+"):
        for h in (1, 3, 5):
            add(f"ageh:{ab}:h{h}", lambda r, a=ab, h=h: r["aband"] == a and r["h"] == h)

    out = json.dumps(res, indent=1)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    for k, v in res["cells"].items():
        flag = "" if not v.get("sd") else (" *" if v.get("resolvable") else "  ")
        ci = v.get("ci95")
        print(f"{k:<22} n={v['n']:>6} bias={v['bias']:+.4f}{flag} "
              f"ci={ci} mae={v['mae']:.4f} pred={v['pred']:.3f} act={v['act']:.3f}")


if __name__ == "__main__":
    main()
