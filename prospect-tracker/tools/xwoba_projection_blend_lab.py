# P1 xwOBA-into-projection blend lab (pre-registered 2026-07-15)
#
# QUESTION (owner program: "wire our most predictive stats into MLB
# Projections"): does blending Savant xwOBA into the FA engine's projected
# wOBA improve the NEXT-season wOBA forecast that pWOBA ships and the WAR
# path consumes?
#
# LEDGER POSITION (why this is NOT a blind re-run):
#   * statcast-into-projections (2026-06-23, REJECTED) added rich Savant
#     expected-stat FEATURES to the proj_ml quantile stack -- no OOS lift.
#     Its memo left exactly one untested angle: a LEAN subset (gap-only).
#   * phem_marcel_lite (2026-07-15, VALIDATED) crowned fa_projection's
#     woba_proj the best next-season wOBA forecaster (rho 0.5189).
#   * X-H3 (VALIDATED): same-season xwOBA forward-beats actual wOBA
#     (0.454 vs 0.411) -- the signal this lab tries to graft ON TOP of
#     the validated projection, at the OUTPUT layer (the Marcel xISO
#     blend precedent), not as tree features.
#
# ARMS (hitters only -- the pitcher legs are ledgered losses:
#       xwOBA-allowed != FIP; phem pitcher leg failed):
#   1. fa_projection woba_proj                       [incumbent, validated]
#   2. est_woba(Y) alone                             [context, not a candidate]
#   3. output blend: (1-b)*woba_proj + b*est_woba(Y)     [candidate]
#   4. gap-corrected: woba_proj + g*(est_woba(Y)-woba(Y)) [candidate; the
#      rejection memo's "gap-only" lean angle]
#
# HYPERPARAMS: b, g grids fit on predictor years <= 2018 ONLY (train pairs
# 2016-2018 -> outcomes 2017-2019), frozen, gated on predictors 2021-2024
# (outcomes 2022-2025). Savant est_woba availability bounds SEASONS at 2016+.
#
# GATE (v1 convention, seed 20260715, 2000 reps): winner candidate (best gate
# rho among arms 3-4) vs the INCUMBENT arm 1: paired iid-bootstrap lo95 >= 0.
# pass_under_v2 reported alongside. Pair set replicates phem_marcel_lite_lab
# construction EXACTLY (MIN_PA 150/150, 3yr window su>=2 & PA>=600, complete
# outcome seasons only) plus: Savant est_woba present at PA_savant >= 100.
#
# Fully offline: .cache/savant_mlb/expected_batter_{Y}.csv (2016-2026,
# no 2020), .cache/fa_statsapi_hitting_*.json, fa_corpus.pkl, fa_fits pickles.
from __future__ import annotations

import csv
import json
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import plus_lab_harness as plh  # noqa: E402
from rem_plus_backtest import _spearman  # noqa: E402
from phem_marcel_lite_lab import (  # noqa: E402
    FaEngine, dual_gate, load_hit_season, _r4,
)

SEED = 20260715
BOOT = 2000
SEASONS = [2016, 2017, 2018, 2021, 2022, 2023, 2024]
TRAIN_MAX_PRED_YEAR = 2018
MIN_PA_Y, MIN_PA_NEXT = 150.0, 150.0
TAG_MIN_SEASONS = 2
TAG_MIN_PA = 600.0
SAVANT_MIN_PA = 100.0
BETA_GRID = [0.2, 0.3, 0.4, 0.5, 0.6]
GAMMA_GRID = [0.1, 0.2, 0.3, 0.4, 0.5]

SAVANT_DIR = ROOT / ".cache" / "savant_mlb"


def load_xwoba(year: int) -> dict[int, dict]:
    """{mlbam: {est_woba, woba, pa}} from the cached Savant expected CSV."""
    path = SAVANT_DIR / f"expected_batter_{year}.csv"
    if not path.exists():
        return {}
    out: dict[int, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                mid = int(r["player_id"])
                out[mid] = {"est_woba": float(r["est_woba"]),
                            "woba": float(r["woba"]),
                            "pa": float(r["pa"])}
            except (KeyError, TypeError, ValueError):
                continue
    return out


def _hem3_window(by_season, mid, y):
    """X-H2 window tag (su, PA) — mirrors phem lab's _hem3 gate use."""
    su = 0
    pa = 0.0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if rec and rec.get("hem_plus_raw") is not None and rec.get("pa"):
            su += 1
            pa += rec["pa"]
    return su, pa


def main():
    t0 = time.time()
    eng = FaEngine()
    print(f"fa corpus: hit={len(eng.hist_hit)} players")

    by_season = {}
    for y in sorted(set(SEASONS + [max(SEASONS) + 1])):
        s, _ = load_hit_season(y)
        if s:
            by_season[y] = s
        print(f"  hit {y}: {len(s)} scored")
    xw = {y: load_xwoba(y) for y in SEASONS}
    print("  savant expected loaded:", {y: len(v) for y, v in xw.items()})

    pairs = []
    drops = {"partial_outcome": 0, "window": 0, "age_missing": 0,
             "fa_proj_missing": 0, "savant_missing": 0}
    for y in SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT:
                continue
            if b["woba_raw"] is None:
                continue
            if not plh.season_complete(y + 1):
                drops["partial_outcome"] += 1
                continue
            su, wpa = _hem3_window(by_season, mid, y)
            if su < TAG_MIN_SEASONS or wpa < TAG_MIN_PA:
                drops["window"] += 1
                continue
            age = a.get("age")
            if age is None:
                drops["age_missing"] += 1
                continue
            pr = eng.proj("hit", int(mid), y, age + 1)
            fa_val = pr.get("woba_proj") if pr else None
            if fa_val is None:
                drops["fa_proj_missing"] += 1
                continue
            sv = xw.get(y, {}).get(int(mid))
            if not sv or sv["pa"] < SAVANT_MIN_PA:
                drops["savant_missing"] += 1
                continue
            pairs.append({
                "mid": mid, "y": y, "oy": y + 1, "tgt": b["woba_raw"],
                "fa": fa_val, "xw": sv["est_woba"],
                "gap": sv["est_woba"] - sv["woba"],
            })
    train = [p for p in pairs if p["y"] <= TRAIN_MAX_PRED_YEAR]
    gate = [p for p in pairs if p["y"] > TRAIN_MAX_PRED_YEAR]
    print(f"pairs={len(pairs)} train={len(train)} gate={len(gate)} drops={drops}")

    # -- hyperparameter fit (TRAIN only, frozen) ------------------------------
    def _rho_blend(subset, beta):
        vals = [(1 - beta) * p["fa"] + beta * p["xw"] for p in subset]
        return _spearman(vals, [p["tgt"] for p in subset])

    def _rho_gap(subset, gamma):
        vals = [p["fa"] + gamma * p["gap"] for p in subset]
        return _spearman(vals, [p["tgt"] for p in subset])

    beta_report = {b: _r4(_rho_blend(train, b)) for b in BETA_GRID}
    gamma_report = {g: _r4(_rho_gap(train, g)) for g in GAMMA_GRID}
    beta_star = max(BETA_GRID, key=lambda b: beta_report[b] or -9)
    gamma_star = max(GAMMA_GRID, key=lambda g: gamma_report[g] or -9)
    frozen = {"beta": beta_star, "gamma": gamma_star,
              "train_pred_years": f"<= {TRAIN_MAX_PRED_YEAR}",
              "train_n": len(train),
              "beta_grid_train_rho": {str(k): v for k, v in beta_report.items()},
              "gamma_grid_train_rho": {str(k): v for k, v in gamma_report.items()}}
    print(f"frozen: beta={beta_star} gamma={gamma_star}")

    # -- gate -----------------------------------------------------------------
    arms = {
        "fa_projection": [p["fa"] for p in gate],
        "xwoba_alone": [p["xw"] for p in gate],
        "output_blend": [(1 - beta_star) * p["fa"] + beta_star * p["xw"] for p in gate],
        "gap_corrected": [p["fa"] + gamma_star * p["gap"] for p in gate],
    }
    tgt = [p["tgt"] for p in gate]
    mids = [p["mid"] for p in gate]
    pys = [p["y"] for p in gate]
    oys = [p["oy"] for p in gate]

    rhos = {k: _spearman(v, tgt) for k, v in arms.items()}
    candidates = ("output_blend", "gap_corrected")
    winner = max(candidates, key=lambda k: rhos[k] if rhos[k] is not None else -9)
    res = dual_gate(winner, arms, tgt, mids, pys, oys)
    gap_v1 = res["v1"]["gap_ci_primary_minus"].get("fa_projection")
    gap_v2 = res["v2"]["gap_ci_primary_minus"].get("fa_projection")
    pass_v1 = bool(gap_v1 and gap_v1["lo95"] >= 0)
    pass_v2 = bool(gap_v2 and gap_v2["lo95"] >= 0)

    payload = {
        "experiment": "P1 xwOBA-into-projection output blend (hitters)",
        "generated_at": date.today().isoformat(), "seed": SEED, "boot": BOOT,
        "harness": plh.convention_meta("wOBA(Y+1) raw pooled", "wOBA(Y+1)"),
        "protocol": {
            "arms": list(arms.keys()),
            "candidates": list(candidates),
            "incumbent": "fa_projection (validated pWOBA, phem_marcel_lite)",
            "hyperparams_fit": f"predictor years <= {TRAIN_MAX_PRED_YEAR} ONLY, frozen",
            "gate_rule": ("winner candidate vs incumbent fa_projection: "
                          "iid paired bootstrap lo95 >= 0 (v1)"),
            "pair_set": ("phem_marcel_lite_lab construction (MIN_PA 150/150, "
                         "3yr window su>=2 & PA>=600, complete outcomes) + "
                         f"Savant est_woba present at PA >= {SAVANT_MIN_PA}"),
            "ledger_position": ("NOT the rejected proj_ml feature bundle; this is "
                                "the output-layer blend / gap-only lean angle"),
        },
        "n_pairs": len(pairs), "n_train": len(train), "n_gate": len(gate),
        "drops": drops,
        "gate_pred_years": sorted({p["y"] for p in gate}),
        "gate_outcome_years": sorted({p["oy"] for p in gate}),
        "frozen_hyperparams": frozen,
        "gate_rhos_v1": {k: _r4(v) for k, v in rhos.items()},
        "winner_candidate": winner,
        "results": res,
        "gate": {
            "bar": ("winner candidate paired-bootstrap lo95(winner - fa_projection)"
                    " >= 0; v1 convention, seed 20260715, 2000 reps"),
            "gap_ci_winner_minus_incumbent_v1": gap_v1,
            "gap_ci_winner_minus_incumbent_v2": gap_v2,
            "pass": pass_v1, "pass_under_v2": pass_v2,
        },
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = ROOT / "data" / "xwoba_projection_blend_eval.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps({"rhos": payload["gate_rhos_v1"], "winner": winner,
                      "gap_v1": gap_v1, "pass": pass_v1, "pass_v2": pass_v2},
                     indent=1))


if __name__ == "__main__":
    main()
