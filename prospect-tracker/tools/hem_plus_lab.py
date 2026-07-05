# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Hitter-metric lab: HEM+ forward validation (the offensive analog of the SEM+
lab). One pre-registered experiment:

  X-H1  HEM+ skill validation. HEM+ = hitter-pool EB-shrunk wOBA. GATE (ship):
        forward Spearman vs wOBA(Y+1) BEATS the naive AVG baseline (bootstrap gap
        lo95 > 0) AND is NOT WORSE than its raw-wOBA parent (gap lo95 >= -0.01).
        The shrinkage earns its place if it holds even/ahead of raw wOBA while
        beating the simpler rate stats. -> data/hem_plus_eval.json

Uses the CACHED StatsAPI hitting statlines (fa_sources), so it runs offline. All
stochastic steps seeded.
Run: python tools/hem_plus_lab.py [--no-write] [--seasons 2015,2016,...]
"""
from __future__ import annotations

import json
import random
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import hem_plus  # noqa: E402
import hitter_export as he  # noqa: E402
from rem_plus_backtest import _spearman, _ci  # noqa: E402

DATA = ROOT / "data"
HEM_EVAL = DATA / "hem_plus_eval.json"

# Predictor seasons (cached hitting 2000-2026). Recent, ex-2020 (COVID 60-game).
SEASONS = [2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
MIN_PA_Y = 150.0                   # a usable predictor-year sample
MIN_PA_NEXT = 150.0                # a real outcome-year sample
BOOT = 2000
SEED = 20260705


def _r4(v):
    return None if v is None else round(v, 4)


def load_season(y: int) -> dict:
    """MLBAM -> per-hitter record for season Y, carrying HEM+, raw wOBA, OPS, AVG
    (predictors) and PA. The next-year wOBA is joined at pair time."""
    rows = he.load_season_hitting(y)
    if not rows:
        return {}
    scored = hem_plus.score_pool(he.build_hitters(rows))
    out = {}
    for h in scored["hitters"]:
        if h.get("hem_plus") is None or h.get("woba_raw") is None:
            continue
        out[h["mlbam"]] = {
            "name": h.get("name"), "hem_plus": h["hem_plus"], "woba_raw": h["woba_raw"],
            "ops": h.get("ops"), "avg": h.get("avg"), "pa": h.get("pa"),
        }
    print(f"  {y}: {len(out)} hitters scored")
    return out


def _boot_gap_ci(a_pred, b_pred, tgt, seed=SEED):
    """Seeded bootstrap CI on rho(a,tgt) - rho(b,tgt)."""
    n = len(tgt)
    rng = random.Random(seed)
    gaps = []
    for _ in range(BOOT):
        samp = [rng.randrange(n) for _ in range(n)]
        ra = _spearman([a_pred[i] for i in samp], [tgt[i] for i in samp])
        rb = _spearman([b_pred[i] for i in samp], [tgt[i] for i in samp])
        if ra is not None and rb is not None:
            gaps.append(ra - rb)
    return _ci(gaps)


def run(write: bool = True) -> dict:
    t0 = time.time()
    by_season = {}
    for y in SEASONS + [max(SEASONS) + 1]:
        s = load_season(y)
        if s:
            by_season[y] = s
    print(f"  loaded {len(by_season)} seasons in {round(time.time()-t0,1)}s")

    hem, woba, ops, avg, tgt = [], [], [], [], []
    for y in SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT:
                continue
            if a["ops"] is None or a["avg"] is None or b["woba_raw"] is None:
                continue
            hem.append(a["hem_plus"]); woba.append(a["woba_raw"])
            ops.append(a["ops"]); avg.append(a["avg"]); tgt.append(b["woba_raw"])
    n = len(hem)
    rho_hem = _spearman(hem, tgt)
    rho_woba = _spearman(woba, tgt)
    rho_ops = _spearman(ops, tgt)
    rho_avg = _spearman(avg, tgt)
    gap_vs_avg = _boot_gap_ci(hem, avg, tgt)
    gap_vs_ops = _boot_gap_ci(hem, ops, tgt)
    gap_vs_woba = _boot_gap_ci(hem, woba, tgt)
    passed = bool(rho_hem is not None and gap_vs_avg and gap_vs_avg["lo95"] > 0
                  and gap_vs_woba and gap_vs_woba["lo95"] >= -0.01)

    dur = round(time.time() - t0, 1)
    payload = {
        "generated_at": date.today().isoformat(), "seasons": SEASONS, "seed": SEED,
        "experiment": "X-H1", "model": "hem_plus",
        "conventions": {"predictor_year": f"year Y (PA>={int(MIN_PA_Y)})",
                        "target": f"wOBA in year Y+1 (PA>={int(MIN_PA_NEXT)})",
                        "excluded": "2020 (60-game COVID season)"},
        "n_forward_pairs": n,
        "forward_spearman_vs_wOBA_next": {
            "hem_plus": _r4(rho_hem), "raw_woba": _r4(rho_woba),
            "ops": _r4(rho_ops), "avg": _r4(rho_avg)},
        "gap_ci_vs_avg": gap_vs_avg, "gap_ci_vs_ops": gap_vs_ops,
        "gap_ci_vs_raw_woba": gap_vs_woba,
        "gate": {"bar": "beats AVG forward (gap lo95 > 0) AND not worse than raw wOBA (lo95 >= -0.01)",
                 "pass": passed},
        "runtime_seconds": dur,
        "verdict": {"status": "validated" if passed else "provisional",
                    "summary": (
                        f"Forward-chained OOS over {len(SEASONS)} seasons ({n} Y->Y+1 pairs): "
                        f"HEM+ predicts next-year wOBA at rho {_r4(rho_hem)} vs raw wOBA "
                        f"{_r4(rho_woba)}, OPS {_r4(rho_ops)}, AVG {_r4(rho_avg)}. CI on the rho "
                        f"gap vs AVG {gap_vs_avg}, vs raw wOBA {gap_vs_woba}. "
                        + ("Shipped VALIDATED: HEM+ beats the naive rate baselines and holds "
                           "even-or-ahead of its raw-wOBA parent out of sample, so the "
                           "component empirical-Bayes shrinkage + hitter-pool anchoring earn "
                           "their place. Volume/baserunning ride separate context columns."
                           if passed else
                           "Shipped provisional with the r published."))}}

    print(json.dumps({"X-H1": {"n": n, "hem": _r4(rho_hem), "woba": _r4(rho_woba),
                               "ops": _r4(rho_ops), "avg": _r4(rho_avg),
                               "vs_avg": gap_vs_avg, "vs_woba": gap_vs_woba,
                               "pass": passed}}, indent=1))
    if write:
        tmp = HEM_EVAL.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(HEM_EVAL)
        print(f"wrote {HEM_EVAL.relative_to(ROOT)}")
    return {HEM_EVAL: payload}


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--seasons" in argv:
        i = argv.index("--seasons")
        SEASONS = [int(x) for x in argv[i + 1].split(",")]
    run(write="--no-write" not in argv)
