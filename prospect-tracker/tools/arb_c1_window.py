# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE C2 clause C1': the served chain against the arbitration ladders.

docs/ARBITRATION_GATE.md section 11d registers C1' as "re-run the 2026-08-19 C1
protocol on the current pool". The 2026-08-19 lab lived in a scratchpad and is
not in this tree, but its PROTOCOL is registered in full in section 9b, and
this file implements that text and nothing else:

  * the GATE B pool: players with an observed arbitration window (two or more
    scored seasons with a salary and a step), tools/arb_gate_b._pool's rule;
  * the SERVED per-player configuration, chained so each rung's prediction is
    the next rung's prior: the arb-1 champion at ARB 1, the banded step
    multiplier at ARB 2 and later, floored at the league minimum, which is
    arb_export.build_board's estimator selection;
  * the fitted ladder and clemens_2026, through tools/arb_gate_b's own window
    pricing;
  * MAE of the discounted window total in NOMINAL dollars, discount 0.07;
  * every fitted estimator (deflator, stage 1, banded multipliers, fitted
    ladder) fit in-sample on the pool, as GATE B fit its ladder;
  * a player the served chain cannot price at every step is dropped from ALL
    arms and counted;
  * the floor: a paired bootstrap clustered on PLAYER refitting every fitted
    arm each draw, one-sided MDE95, with section 11c's seed and B.

PASS needs the served chain to beat BOTH ladders by more than the floor of
each contrast.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

DISCOUNT = 0.07


def load_pool(frame: str):
    """(pool, metrics). Each player carries his unframed steps (the ladders
    price the season's own WAR, as GATE B does) and the framed copies the
    served chain reads."""
    import arb_dataset as A
    import arb_metrics as M
    import arb_model as Mod
    rows = A.build_panel(log=None)["rows"]
    sc = A.scored_rows(rows)
    fr = {(int(r["mlbam"]), int(r["season"])): r
          for r in Mod.attach_frame(sc, rows, frame)}
    by: dict[int, dict[int, dict]] = {}
    for r in sc:
        by.setdefault(int(r["mlbam"]), {})[int(r["arb_year"])] = r
    pool = []
    for mlbam, steps in by.items():
        if len(steps) < 2:
            continue
        pool.append({"mlbam": mlbam, "steps": steps,
                     "framed": {k: fr[(mlbam, int(r["season"]))]
                                for k, r in steps.items()}})
    return pool, M.metric_panel(2018, 2026)


def fit(pool, metrics):
    """Every fitted arm, in-sample on the pool."""
    import arb_gate_b as GB
    import arb_model as Mod
    rows = [r for p in pool for r in p["framed"].values()]
    seasons = sorted({int(r["season"]) for r in rows})
    defl = Mod.fit_deflator(rows, base_year=seasons[0])
    return {"defl": defl,
            "s1": Mod.fit_stage1(rows, metrics, defl),
            "banded": Mod.fit_banded_multipliers(rows, defl),
            "fitted": GB._fit_ladder(pool)[0]}


def served_window(p, metrics, arms) -> float | None:
    """Discounted nominal total of the served chain over the player's observed
    window, or None when a step cannot be priced."""
    import arb_model as Mod
    defl, s1, banded = arms["defl"], arms["s1"], arms["banded"]
    tot, prev = 0.0, None
    for i, (step, _row) in enumerate(sorted(p["steps"].items())):
        r = dict(p["framed"][step])
        if prev is not None:
            r["prior_salary"] = prev
        if step == 1:
            d = Mod.predict(r, metrics, defl, s1, None) if s1 else None
        else:
            d = Mod.banded_predict(r, banded, defl)
        if not d:
            return None
        lvl = defl.get(int(r["season"])) or defl[max(defl)]
        pred = d * lvl
        lm = float(r.get("league_min") or 0.0)
        pred = max(pred, lm)
        tot += pred / ((1 + DISCOUNT) ** i)
        prev = pred
    return tot


def maes(pool, metrics, arms):
    """(paired n, dropped, {arm: MAE}) on the players the chain prices fully."""
    import arb_gate_b as GB
    served, clem, fitd = [], [], []
    dropped = 0
    for p in pool:
        s = served_window(p, metrics, arms)
        if s is None:
            dropped += 1
            continue
        a = GB._actual_window(p["steps"])
        served.append(abs(s - a))
        clem.append(abs(GB._predict_window(p["steps"], GB.CLEMENS) - a))
        fitd.append(abs(GB._predict_window(p["steps"], arms["fitted"]) - a))
    if not served:
        return 0, dropped, None
    return len(served), dropped, {"served": float(np.mean(served)),
                                  "clemens_2026": float(np.mean(clem)),
                                  "fitted": float(np.mean(fitd))}


def score(frame: str, *, seed: int, B: int) -> dict:
    pool, metrics = load_pool(frame)
    arms = fit(pool, metrics)
    n, dropped, m = maes(pool, metrics, arms)
    rng = np.random.default_rng(seed)
    gc, gf = [], []
    for _ in range(B):
        idx = rng.integers(0, len(pool), len(pool))
        draw = [pool[i] for i in idx]
        try:
            a = fit(draw, metrics)
            _n, _d, mm = maes(draw, metrics, a)
        except Exception:                            # a degenerate draw
            continue
        if mm:
            gc.append(mm["clemens_2026"] - mm["served"])
            gf.append(mm["fitted"] - mm["served"])
    out = {"frame": frame, "pool_players": len(pool), "n_paired": n,
           "dropped": dropped, "fitted_ladder": arms["fitted"],
           "mae_usd": m, "seed": seed, "B": B,
           "B_successful": {"clemens_2026": len(gc), "fitted": len(gf)}}
    for name, g in (("clemens_2026", gc), ("fitted", gf)):
        gain = m[name] - m["served"]
        floor = 1.645 * float(np.std(g, ddof=1)) if len(g) > 1 else None
        out["vs_" + name] = {
            "gain_usd": gain, "mde95_onesided_usd": floor,
            "gain_over_floor": (gain / floor) if floor else None,
            "resolvable": bool(floor is not None and gain > floor)}
    out["verdict"] = ("PASS" if out["vs_clemens_2026"]["resolvable"]
                      and out["vs_fitted"]["resolvable"] else "FAIL")
    return out
