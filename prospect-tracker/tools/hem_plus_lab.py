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
MULTI_EVAL = DATA / "hem_plus_multiyear_eval.json"

# Predictor seasons (cached hitting 2000-2026). Recent, ex-2020 (COVID 60-game).
SEASONS = [2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
MIN_PA_Y = 150.0                   # a usable predictor-year sample
MIN_PA_NEXT = 150.0                # a real outcome-year sample
BOOT = 2000
SEED = 20260705
TAG_MIN_SEASONS = 2                # 3yr "established" bar
TAG_MIN_PA = 600.0                 # ... and total PA over the window


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


def _hem3(by_season, mid, y):
    """PA-weighted trailing-3-season HEM+ (y-2..y) for a player, seasons used, PA."""
    num = den = 0.0
    su = 0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if rec and rec.get("hem_plus") is not None and rec.get("pa"):
            num += rec["hem_plus"] * rec["pa"]; den += rec["pa"]; su += 1
    return (num / den if den else None), su, den


def _multiyear_proposed(by_season: dict, cur_season: int) -> dict:
    """3yr HEM+ for the CURRENT qualified pool -> proposed_values joined into
    hitter_leaderboards.json by MLBAM (like sem_plus_3yr)."""
    cur = by_season.get(cur_season) or {}
    players, vals = {}, []
    for mid, row in cur.items():
        if row.get("hem_plus") is None or (row.get("pa") or 0) < 200:
            continue
        h3, su, pa3 = _hem3(by_season, mid, cur_season)
        if h3 is None:
            continue
        tag = ("established" if su >= TAG_MIN_SEASONS and pa3 >= TAG_MIN_PA else "provisional")
        players[str(mid)] = {"name": row.get("name"), "hem_plus_now": row.get("hem_plus"),
                             "hem_plus_3yr": int(round(h3)), "seasons_used": su,
                             "pa_total": int(pa3), "tag": tag}
        vals.append((str(mid), h3))
    n = len(vals)
    svals = sorted(v for _, v in vals)
    for mid, v in vals:
        lo = sum(1 for s in svals if s < v)
        eq = sum(1 for s in svals if s == v)
        players[mid]["pct"] = int(round(100.0 * (lo + (eq + 1) / 2.0 - 0.5) / n)) if n else None
    return {"season": cur_season, "window": [cur_season - 2, cur_season - 1, cur_season],
            "metric": "hem_plus_3yr", "display_name": "HEM+ (3yr)",
            "definition": (f"PA-weighted mean HEM+ over the trailing 3 seasons. A steadier "
                           f"offense read than one season. tag is 'established' with "
                           f"{TAG_MIN_SEASONS}+ seasons and {int(TAG_MIN_PA)}+ PA."),
            "n_with_value": len(players), "players": players}


def run(write: bool = True) -> dict:
    t0 = time.time()
    by_season = {}
    # Backtest pairs run over SEASONS (all complete Y->Y+1). Load two extra seasons
    # beyond the last predictor (the last complete target + the CURRENT season) so
    # the proposed-values 3yr window matches the live board's season, not a year
    # behind. The current (incomplete) season is NOT used as a backtest target.
    for y in SEASONS + [max(SEASONS) + 1, max(SEASONS) + 2]:
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

    # ---- X-H2: 3yr HEM+ forward pairs (3yr vs 1yr on the SAME set) ---- #
    one3, three3, tgt3 = [], [], []
    for y in SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT or b["woba_raw"] is None:
                continue
            h3, su, pa3 = _hem3(by_season, mid, y)
            if h3 is None or su < TAG_MIN_SEASONS or pa3 < TAG_MIN_PA:
                continue
            one3.append(a["hem_plus"]); three3.append(h3); tgt3.append(b["woba_raw"])
    n3 = len(one3)
    rho_1yr = _spearman(one3, tgt3)
    rho_3yr = _spearman(three3, tgt3)
    gap3 = _boot_gap_ci(three3, one3, tgt3) if n3 >= 30 else None
    passed3 = bool(rho_3yr is not None and rho_1yr is not None
                   and rho_3yr > rho_1yr and gap3 and gap3["lo95"] >= 0)

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

    cur_season = max(by_season)
    multi_payload = {
        "generated_at": date.today().isoformat(), "seasons": SEASONS, "seed": SEED,
        "experiment": "X-H2", "model": "hem_plus_3yr", "n_forward_pairs": n3,
        "conventions": {"predictor_year": f"trailing 3yr through Y (PA>={int(MIN_PA_Y)} in Y)",
                        "target": f"wOBA in year Y+1 (PA>={int(MIN_PA_NEXT)})", "excluded": "2020"},
        "hem_1yr_forward_rho_on_3yr_set": _r4(rho_1yr),
        "hem_3yr_forward_rho": _r4(rho_3yr), "gap_ci_3yr_minus_1yr": gap3,
        "gate": {"bar": "3yr rho > 1yr rho on the same set AND bootstrap gap lo95 >= 0",
                 "pass": passed3},
        "verdict": ("PASS: 3-year HEM+ forward-predicts next-year offense better than one "
                    "season; ship hem_plus_3yr as a companion column."
                    if passed3 else
                    "MARGINAL: 3-year HEM+ does not clear the strict same-set gate; ship "
                    "provisional with the r published (more sample is a steadier read)."),
        "proposed_values": _multiyear_proposed(by_season, cur_season)}

    print(json.dumps({"X-H1": {"n": n, "hem": _r4(rho_hem), "woba": _r4(rho_woba),
                               "ops": _r4(rho_ops), "avg": _r4(rho_avg),
                               "vs_avg": gap_vs_avg, "vs_woba": gap_vs_woba, "pass": passed},
                      "X-H2": {"n": n3, "one": _r4(rho_1yr), "three": _r4(rho_3yr),
                               "gap": gap3, "pass": passed3}}, indent=1))
    if write:
        for path, pl in ((HEM_EVAL, payload), (MULTI_EVAL, multi_payload)):
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(pl, indent=1) + "\n", encoding="utf-8")
            tmp.replace(path)
            print(f"wrote {path.relative_to(ROOT)}")
    return {HEM_EVAL: payload, MULTI_EVAL: multi_payload}


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--seasons" in argv:
        i = argv.index("--seasons")
        SEASONS = [int(x) for x in argv[i + 1].split(",")]
    run(write="--no-write" not in argv)
