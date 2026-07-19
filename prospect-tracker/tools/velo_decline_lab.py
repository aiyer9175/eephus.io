# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Velo-decline adjustment lab (W3 T1-4, X-R8/X-S8) - tools-ready copy.

Candidate (pre-registered): index + g*min(0, velo_Y - velo_{Y-1}),
g in {1.5, 2.5, 3.5} pts/mph fixed upfront; g chosen forward-chained on
pre-2022 predictor-year folds, evaluated on 2022+. Velo is the PAL convention
(pal_export.load_velo: max of ff/si/fc avg speed from
pybaseball.statcast_pitcher_pitch_arsenal, one bulk call per season), read
from .cache/velo_arsenal_YYYY.json when present. A pair missing velo in
either year gets ZERO adjustment, so the pair sets stay byte-identical to the
incumbent REM+/SEM+ v2-lab pair sets (X-R1 / X-S1 loops).

GATE (seed 20260714, per side, convention v1 primary): paired bootstrap
lo95(rho gap candidate-incumbent) >= 0 POOLED OVER ALL PAIRS (zero-adjust
rows included); pass_under_v2 (within-outcome-season z target +
player-clustered season-stratified bootstrap) reported alongside.
Secondary diagnostics: >=1mph-loss subset effect + age-only counterfactual
(seasonal age from .cache/fa_statsapi_pitching_YYYY.json).

Run: python tools/velo_decline_lab.py [--no-write]
Writes data/rem_plus_velo_eval.json + data/sem_plus_velo_eval.json unless
--no-write. Never touches the shipped rem_plus_eval / sem_plus_eval.

RESULT (2026-07-15 rerun, seed 20260714, 2000 reps): NO SHIP on BOTH sides.
X-R8 REM: g=3.5, rho .2374 -> .2437, v1 gap CI [-0.0026, +0.0165] (FAIL,
directionally positive, not separable from zero); v2 also fails.
X-S8 SEM: g=2.5, rho .4167 -> .4107, v1 gap CI [-0.0137, +0.0018] (FAIL,
directionally NEGATIVE - velo decline HURTS the starter index). The incumbent
indexes stand; velo decline stays a display peripheral. This file is the
loss-ledger reproduction harness, not a shipped model.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import mlb_leverage                     # noqa: E402

# LEVERAGE STUB (load-bearing): rem_plus_lab.load_season calls
# mlb_leverage.fetch_season_leverage, which walks the StatsAPI winProbability
# feed game by game and re-fetches permanently-404 games on EVERY run. Nothing
# in this lab reads leverage: REM+ raw is FIP-based (leverage rides the
# separate RIV+ column, never touched here) and SEM+ never loads leverage.
# Stubbing keeps the pair sets byte-identical to the incumbents (verified:
# rem n=878 @ rho .2374, sem n=592 @ .4167 on the 2026-07-15 rerun) while
# removing thousands of live fetches. Remove the stub ONLY if a future
# variant actually needs gmLI/WPA.
mlb_leverage.fetch_season_leverage = lambda season, **k: ({}, {"stubbed": True})

import plus_lab_harness as plh          # noqa: E402
import rem_plus_lab as rl               # noqa: E402
import sem_plus_lab as sl               # noqa: E402
from rem_plus_backtest import _spearman  # noqa: E402

CACHE = ROOT / ".cache"
DATA = ROOT / "data"
SEED = 20260714
BOOT = 2000
G_GRID = [1.5, 2.5, 3.5]
SPLIT_PRED_YEAR = 2022
LOSS_SUBSET_MPH = -1.0


def _r4(v):
    return None if v is None else round(v, 4)


def _load_velo_year(y: int) -> dict:
    """Cached-first; falls back to the live PAL loader (bulk, one call)."""
    p = CACHE / f"velo_arsenal_{y}.json"
    if p.exists():
        return {int(k): float(v)
                for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
    try:
        import pal_export
        return dict(pal_export.load_velo(y))
    except Exception:  # noqa: BLE001
        return {}


def load_velo_all() -> dict:
    return {y: _load_velo_year(y) for y in range(2017, max(rl.SEASONS) + 1)}


def load_ages() -> dict:
    ages = {}
    for y in range(2017, max(rl.SEASONS) + 1):
        p = CACHE / f"fa_statsapi_pitching_{y}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for blk in d.get("stats", []) or []:
            for s in blk.get("splits", []) or []:
                pid = (s.get("player") or {}).get("id")
                age = (s.get("stat") or {}).get("age")
                if pid is not None and age is not None:
                    ages[(int(pid), y)] = int(age)
    return ages


def rem_pairs() -> list:
    by_season = {}
    for y in rl.SEASONS:
        s = rl.load_season(y)
        if s:
            by_season[y] = s
    rows = []
    for y in rl.SEASONS:
        ny = y + 1
        cur, nxt = by_season.get(y), by_season.get(ny)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["tbf"] or 0) < rl.MIN_TBF_Y or (b["tbf"] or 0) < rl.MIN_TBF_NEXT:
                continue
            if a["cand_rem_plus"] is None or a["raw_fip"] is None or b["ra9"] is None \
                    or a["era"] is None:
                continue
            if not plh.season_complete(ny):
                continue
            rows.append({"mid": mid, "py": y, "oy": ny,
                         "index": a["rem_plus_raw"], "tgt": -b["ra9"]})
    return rows


def sem_pairs() -> list:
    by_season = {}
    for y in sl.SEASONS:
        s = sl.load_season(y)
        if s:
            by_season[y] = s
    rows = []
    for y in sl.SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["ip"] or 0) < sl.MIN_IP_Y or (b["ip"] or 0) < sl.MIN_IP_NEXT:
                continue
            if a["raw_fip"] is None or a["era"] is None or b["ra9"] is None \
                    or a["cand_sem"] is None:
                continue
            if not plh.season_complete(y + 1):
                continue
            rows.append({"mid": mid, "py": y, "oy": y + 1,
                         "index": a["sem_plus_raw"], "tgt": -b["ra9"]})
    return rows


def run_side(tag: str, rows: list, velo: dict, ages: dict) -> dict:
    n = len(rows)
    inc = [r["index"] for r in rows]
    tgt = [r["tgt"] for r in rows]
    mids = [r["mid"] for r in rows]
    pys = [r["py"] for r in rows]
    oys = [r["oy"] for r in rows]
    rho_inc = _spearman(inc, tgt)

    for r in rows:
        v1 = (velo.get(r["py"]) or {}).get(r["mid"])
        v0 = (velo.get(r["py"] - 1) or {}).get(r["mid"])
        r["dv"] = (v1 - v0) if (v1 is not None and v0 is not None) else None
        r["age"] = ages.get((r["mid"], r["py"]))

    n_dv = sum(1 for r in rows if r["dv"] is not None)
    coverage = {"n_pairs": n, "n_with_dv": n_dv,
                "n_dv_negative": sum(1 for r in rows
                                     if r["dv"] is not None and r["dv"] < 0),
                f"n_dv_le_{LOSS_SUBSET_MPH}": sum(1 for r in rows
                                                  if r["dv"] is not None
                                                  and r["dv"] <= LOSS_SUBSET_MPH),
                "n_zero_adjust_rows": n - n_dv,
                "n_with_age": sum(1 for r in rows if r["age"] is not None)}

    def cand_series(g):
        return [r["index"] + (g * min(0.0, r["dv"]) if r["dv"] is not None else 0.0)
                for r in rows]

    sel_idx = [i for i, r in enumerate(rows) if r["py"] < SPLIT_PRED_YEAR]
    ev_idx = [i for i, r in enumerate(rows) if r["py"] >= SPLIT_PRED_YEAR]
    grid = {}
    best_g, best_rho = None, None
    for g in G_GRID:
        cs = cand_series(g)
        r_sel = _spearman([cs[i] for i in sel_idx], [tgt[i] for i in sel_idx])
        r_ev = _spearman([cs[i] for i in ev_idx], [tgt[i] for i in ev_idx])
        grid[str(g)] = {"rho_pre2022_selection": _r4(r_sel),
                        "rho_2022plus_eval": _r4(r_ev),
                        "rho_all_pairs": _r4(_spearman(cs, tgt))}
        if r_sel is not None and (best_rho is None or r_sel > best_rho):
            best_g, best_rho = g, r_sel
    rho_inc_sel = _spearman([inc[i] for i in sel_idx], [tgt[i] for i in sel_idx])
    rho_inc_ev = _spearman([inc[i] for i in ev_idx], [tgt[i] for i in ev_idx])

    cand = cand_series(best_g)
    rho_cand = _spearman(cand, tgt)

    gap_v1 = plh.iid_boot_gaps(cand, {"vs_incumbent": inc}, tgt, BOOT, SEED)["vs_incumbent"]
    pass_v1 = bool(gap_v1 and gap_v1["lo95"] >= 0)
    tgt_z = plh.zscore_within(oys, tgt)
    gap_v2 = plh.cluster_boot_gaps(cand, {"vs_incumbent": inc}, tgt_z, mids, pys,
                                   BOOT, SEED)["vs_incumbent"]
    pass_v2 = bool(gap_v2 and gap_v2["lo95"] >= 0)
    ev_gap = plh.iid_boot_gaps([cand[i] for i in ev_idx],
                               {"vs_incumbent": [inc[i] for i in ev_idx]},
                               [tgt[i] for i in ev_idx], BOOT, SEED)["vs_incumbent"]

    li = [i for i, r in enumerate(rows)
          if r["dv"] is not None and r["dv"] <= LOSS_SUBSET_MPH]
    loss_diag = {"n": len(li)}
    if len(li) >= 20:
        lt = [tgt[i] for i in li]
        loss_diag.update({
            "rho_incumbent": _r4(_spearman([inc[i] for i in li], lt)),
            "rho_candidate": _r4(_spearman([cand[i] for i in li], lt)),
            "gap_ci_v1": plh.iid_boot_gaps([cand[i] for i in li],
                                           {"vs_incumbent": [inc[i] for i in li]},
                                           lt, BOOT, SEED)["vs_incumbent"],
            "mean_next_ra9_loss_subset": _r4(-sum(lt) / len(lt)),
            "mean_next_ra9_all": _r4(-sum(tgt) / n)})

    fit_pts = [(rows[i]["age"], rows[i]["dv"]) for i in sel_idx
               if rows[i]["age"] is not None and rows[i]["dv"] is not None]
    age_diag = {"n_fit_pre2022": len(fit_pts)}
    if len(fit_pts) >= 30:
        xs = [a for a, _ in fit_pts]
        ys = [d for _, d in fit_pts]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        var = sum((x - mx) ** 2 for x in xs)
        slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var) if var else 0.0
        icpt = my - slope * mx
        cand_age = [r["index"] + (best_g * min(0.0, icpt + slope * r["age"])
                                  if r["age"] is not None else 0.0)
                    for r in rows]
        age_diag.update({
            "fit": {"intercept": _r4(icpt), "slope_dv_per_age_year": _r4(slope)},
            "rho_age_counterfactual": _r4(_spearman(cand_age, tgt)),
            "gap_ci_age_minus_incumbent_v1":
                plh.iid_boot_gaps(cand_age, {"vs_incumbent": inc}, tgt, BOOT,
                                  SEED)["vs_incumbent"],
            "gap_ci_velo_minus_age_v1":
                plh.iid_boot_gaps(cand, {"vs_age_counterfactual": cand_age}, tgt,
                                  BOOT, SEED)["vs_age_counterfactual"]})

    return {
        "n_pairs": n, "velo_coverage": coverage, "g_grid": grid,
        "g_selected_on_pre2022_folds": best_g,
        "incumbent_rho": {"pre2022_selection": _r4(rho_inc_sel),
                          "eval_2022plus": _r4(rho_inc_ev),
                          "all_pairs": _r4(rho_inc)},
        "candidate_rho_all_pairs": _r4(rho_cand),
        "gate": {"bar": ("paired bootstrap lo95(rho gap cand-inc) >= 0 pooled over "
                         "ALL pairs (zero-adjust rows included), convention v1, "
                         f"seed {SEED}"),
                 "gap_ci_v1_all_pairs": gap_v1, "pass": pass_v1,
                 "gap_ci_v2_all_pairs": gap_v2, "pass_under_v2": pass_v2,
                 "cluster": plh.cluster_summary(mids, pys)},
        "eval_2022plus_holdout_v1": {"n": len(ev_idx),
                                     "rho_incumbent": _r4(rho_inc_ev),
                                     "rho_candidate": grid[str(best_g)]["rho_2022plus_eval"],
                                     "gap_ci_v1": ev_gap},
        "diag_velo_loss_subset": loss_diag,
        "diag_age_counterfactual": age_diag,
        "verdict": ("PASS: the velo-decline adjustment beats the incumbent index "
                    "forward under the pre-registered pooled v1 gate; ship per "
                    "the audit protocol." if pass_v1 else
                    "NO SHIP (loss ledger): the velo-decline adjustment does not "
                    "clear the pre-registered pooled v1 gate; the incumbent index "
                    "stands and velo decline stays a display peripheral only."),
    }


def run(write: bool = True) -> dict:
    t0 = time.time()
    velo = load_velo_all()
    ages = load_ages()
    res_rem = run_side("rem", rem_pairs(), velo, ages)
    res_sem = run_side("sem", sem_pairs(), velo, ages)
    common = {
        "experiment": "X-R8/X-S8 velo-decline adjustment",
        "generated_at": date.today().isoformat(), "seed": SEED, "boot": BOOT,
        "g_grid": G_GRID,
        "candidate": "index + g*min(0, velo_Y - velo_{Y-1}); missing velo => zero adjust",
        "velo_convention": ("max(ff,si,fc) avg speed per pal_export.load_velo; "
                            ".cache/velo_arsenal_YYYY.json"),
        "selection": f"g forward-chained on predictor-year < {SPLIT_PRED_YEAR} folds",
        "harness": plh.convention_meta("-RA9 in year Y+1 (raw, pooled)",
                                       "-RA9 in year Y+1"),
        "runtime_seconds": round(time.time() - t0, 1),
    }
    payloads = {}
    for name, side in (("rem_plus_velo_eval.json", res_rem),
                       ("sem_plus_velo_eval.json", res_sem)):
        pl = dict(common)
        pl.update(side)
        payloads[DATA / name] = pl
    print(json.dumps({"X-R8": {"gate": res_rem["gate"]["gap_ci_v1_all_pairs"],
                               "pass": res_rem["gate"]["pass"]},
                      "X-S8": {"gate": res_sem["gate"]["gap_ci_v1_all_pairs"],
                               "pass": res_sem["gate"]["pass"]}}, indent=1))
    if write:
        for path, pl in payloads.items():
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(pl, indent=1) + "\n", encoding="utf-8")
            tmp.replace(path)
            print(f"wrote {path.relative_to(ROOT)}")
    return payloads


if __name__ == "__main__":
    run(write="--no-write" not in sys.argv[1:])
