# pwoba_xwoba_blend KEEP-ALIVE RE-GATE lab (run 2026-07-23)
#
# LEDGER POSITION (registry row `pwoba_xwoba_blend`, 2026-07-15 loss ledger):
#   NO SHIP - output blend (1-b)*woba_proj + b*est_woba(Y) beat the incumbent
#   fa_projection woba_proj by +0.0092 points (0.5274 vs 0.5182, n_gate 711)
#   but lo95 = -0.0014, refused as knife-edge per standing discipline.
#   The row's OWN registered keep-alive: "each new season adds ~650 pairs;
#   re-gate under this row's protocol at extended n."
#
# THIS RUN IS THAT RE-GATE, under the ORIGINAL protocol EXACTLY
# (tools/xwoba_projection_blend_lab.py, eval data/xwoba_projection_blend_eval.json):
#   * pair set: phem_marcel_lite_lab construction (MIN_PA 150/150, 3yr window
#     su>=2 & PA>=600 over the LOADED seasons only, complete-outcome seasons
#     only per plh.season_complete, age + point-in-time fa_projection woba_proj
#     required) + Savant est_woba present at PA >= 100
#   * frozen arm: output_blend with b = 0.2 (frozen on predictor years <= 2018
#     in the original run; NO refit here - the train grid is recomputed only as
#     a vintage-stability CHECK, never for selection)
#   * registered criterion: paired iid bootstrap lo95(output_blend minus
#     fa_projection) >= 0, v1 convention, seed 20260715, 2000 reps (the
#     original recorded seed convention; v2 companion reported alongside)
#   * extension: predictor year 2025 appended (outcome 2026); by_season loads
#     through 2026. Predictor years <= 2024 windows look backward only, so the
#     original 711-pair gate set is unchanged by the extension (up to upstream
#     cache drift, which this lab measures and reports).
#
# HONESTY NOTE ON THE EXTENSION (found at run time, recorded up front): the
# harness pair rule - registered, not optional - keeps a Y->Y+1 pair only when
# the OUTCOME season is complete (past Nov 15). On 2026-07-23 the 2026 season
# is mid-flight, so 2025->2026 pairs are dropped as partial_outcome under the
# registered protocol. This lab counts exactly how many pairs the extension
# actually adds TODAY, and previews (clearly labeled UNREGISTERED, and a
# protocol defect per the harness pair_rule) what the 2025->2026 cohort looks
# like with partial mid-2026 targets. The registered verdict comes ONLY from
# the frozen arm on the registered (complete-outcome) pair set.
#
# UNREGISTERED SENSITIVITY (reported, never verdict-bearing):
#   (a) small b grid on the registered gate set
#   (b) partial-2026 preview cohort + pooled preview
#
# Output: data/pwoba_blend_regate_eval.json. No production module is touched;
# if the registered criterion passes, the artifact carries the exact proposed
# production diff (hitter_export._join_pwoba) WITHOUT applying it.
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

SEED = 20260715               # original recorded convention (NOT re-rolled)
ALT_SEED_UNUSED = 20260723    # the fallback seed; unused because the original
                              # convention is recorded in the ledger artifact
BOOT = 2000
SEASONS_ORIG = [2016, 2017, 2018, 2021, 2022, 2023, 2024]
NEW_PRED_YEARS = [2025]       # the keep-alive extension (outcome 2026)
SEASONS = SEASONS_ORIG + NEW_PRED_YEARS
TRAIN_MAX_PRED_YEAR = 2018
MIN_PA_Y, MIN_PA_NEXT = 150.0, 150.0
TAG_MIN_SEASONS = 2
TAG_MIN_PA = 600.0
SAVANT_MIN_PA = 100.0

FROZEN_BETA = 0.2             # the registered winner arm, frozen 2026-07-15
FROZEN_GAMMA = 0.1            # gap_corrected context arm, frozen 2026-07-15
BETA_GRID_ORIG = [0.2, 0.3, 0.4, 0.5, 0.6]     # stability check only
GAMMA_GRID_ORIG = [0.1, 0.2, 0.3, 0.4, 0.5]    # stability check only
SENS_BETA_GRID = [0.1, 0.15, 0.2, 0.25, 0.3, 0.4]   # unregistered sensitivity

# The original ledger numbers this re-gate extends (data/xwoba_projection_blend_eval.json)
ORIGINAL = {
    "generated_at": "2026-07-15",
    "n_gate": 711,
    "gate_pred_years": [2022, 2023, 2024],
    "rho_fa_projection": 0.5182,
    "rho_output_blend": 0.5274,
    "point_delta": 0.0092,
    "gap_ci_v1": {"mean": 0.0095, "lo95": -0.0014, "hi95": 0.0201},
    "gap_ci_v2": {"mean": 0.0099, "lo95": -0.0001, "hi95": 0.0196},
    "frozen_beta": 0.2,
    "frozen_gamma": 0.1,
    "seed": 20260715,
    "boot": 2000,
    "verdict": "NO SHIP (knife-edge refused)",
    "keep_alive": ("each new season adds ~650 pairs; re-gate under this row's "
                   "protocol at extended n"),
}

SAVANT_DIR = ROOT / ".cache" / "savant_mlb"


def load_xwoba(year: int) -> dict[int, dict]:
    """{mlbam: {est_woba, woba, pa}} from the cached Savant expected CSV.
    (Copy of the original lab's loader, unchanged.)"""
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
    """X-H2 window tag (su, PA) - copy of the original lab's helper."""
    su = 0
    pa = 0.0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if rec and rec.get("hem_plus_raw") is not None and rec.get("pa"):
            su += 1
            pa += rec["pa"]
    return su, pa


def build_pairs(by_season, xw, eng, years, allow_partial_years=frozenset()):
    """The ORIGINAL pair construction, gate order preserved EXACTLY
    (MIN_PA -> target present -> season_complete -> window -> age -> fa_proj
    -> savant). `allow_partial_years` bypasses ONLY the season_complete gate
    for the listed predictor years (the unregistered preview); the registered
    call passes the empty set. Drops are counted per gate and per predictor
    year so the new-pair accounting is exact."""
    pairs = []
    drops = {"partial_outcome": 0, "window": 0, "age_missing": 0,
             "fa_proj_missing": 0, "savant_missing": 0}
    drops_by_year: dict[int, dict] = {}
    for y in years:
        dy = drops_by_year.setdefault(y, dict.fromkeys(drops, 0))
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT:
                continue
            if b["woba_raw"] is None:
                continue
            if not plh.season_complete(y + 1) and y not in allow_partial_years:
                drops["partial_outcome"] += 1
                dy["partial_outcome"] += 1
                continue
            su, wpa = _hem3_window(by_season, mid, y)
            if su < TAG_MIN_SEASONS or wpa < TAG_MIN_PA:
                drops["window"] += 1
                dy["window"] += 1
                continue
            age = a.get("age")
            if age is None:
                drops["age_missing"] += 1
                dy["age_missing"] += 1
                continue
            pr = eng.proj("hit", int(mid), y, age + 1)
            fa_val = pr.get("woba_proj") if pr else None
            if fa_val is None:
                drops["fa_proj_missing"] += 1
                dy["fa_proj_missing"] += 1
                continue
            sv = xw.get(y, {}).get(int(mid))
            if not sv or sv["pa"] < SAVANT_MIN_PA:
                drops["savant_missing"] += 1
                dy["savant_missing"] += 1
                continue
            pairs.append({
                "mid": mid, "y": y, "oy": y + 1, "tgt": b["woba_raw"],
                "fa": fa_val, "xw": sv["est_woba"],
                "gap": sv["est_woba"] - sv["woba"],
            })
    return pairs, drops, drops_by_year


def frozen_arms(subset):
    """The four original arms with the FROZEN hyperparameters (no refit)."""
    return {
        "fa_projection": [p["fa"] for p in subset],
        "xwoba_alone": [p["xw"] for p in subset],
        "output_blend": [(1 - FROZEN_BETA) * p["fa"] + FROZEN_BETA * p["xw"]
                         for p in subset],
        "gap_corrected": [p["fa"] + FROZEN_GAMMA * p["gap"] for p in subset],
    }


def gate_block(subset, label):
    """Frozen-arm dual-convention gate on a pair subset (v1 = registered)."""
    arms = frozen_arms(subset)
    tgt = [p["tgt"] for p in subset]
    mids = [p["mid"] for p in subset]
    pys = [p["y"] for p in subset]
    oys = [p["oy"] for p in subset]
    res = dual_gate("output_blend", arms, tgt, mids, pys, oys)
    gap_v1 = res["v1"]["gap_ci_primary_minus"].get("fa_projection")
    gap_v2 = res["v2"]["gap_ci_primary_minus"].get("fa_projection")
    return {
        "label": label,
        "n": len(subset),
        "pred_years": sorted({p["y"] for p in subset}),
        "outcome_years": sorted({p["oy"] for p in subset}),
        "rhos_v1": {k: _r4(_spearman(v, tgt)) for k, v in arms.items()},
        "results": res,
        "gap_ci_blend_minus_incumbent_v1": gap_v1,
        "gap_ci_blend_minus_incumbent_v2": gap_v2,
        "pass_v1": bool(gap_v1 and gap_v1["lo95"] >= 0),
        "pass_under_v2": bool(gap_v2 and gap_v2["lo95"] >= 0),
    }


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

    # ---- registered pair set (complete outcomes only) ----------------------- #
    pairs, drops, drops_by_year = build_pairs(by_season, xw, eng, SEASONS)
    train = [p for p in pairs if p["y"] <= TRAIN_MAX_PRED_YEAR]
    gate = [p for p in pairs if p["y"] > TRAIN_MAX_PRED_YEAR]
    new_resolved = [p for p in gate if p["y"] in NEW_PRED_YEARS]
    print(f"pairs={len(pairs)} train={len(train)} gate={len(gate)} "
          f"new_resolved={len(new_resolved)} drops={drops}")

    # ---- vintage-stability check: recompute the ORIGINAL train grids -------- #
    # (report only - the arm stays frozen at b=0.2 / g=0.1 regardless)
    def _rho_blend(subset, beta):
        vals = [(1 - beta) * p["fa"] + beta * p["xw"] for p in subset]
        return _spearman(vals, [p["tgt"] for p in subset])

    def _rho_gap(subset, gamma):
        vals = [p["fa"] + gamma * p["gap"] for p in subset]
        return _spearman(vals, [p["tgt"] for p in subset])

    beta_report = {str(b): _r4(_rho_blend(train, b)) for b in BETA_GRID_ORIG}
    gamma_report = {str(g): _r4(_rho_gap(train, g)) for g in GAMMA_GRID_ORIG}
    beta_argmax = max(BETA_GRID_ORIG, key=lambda b: beta_report[str(b)] or -9)
    gamma_argmax = max(GAMMA_GRID_ORIG, key=lambda g: gamma_report[str(g)] or -9)
    train_check = {
        "train_n": len(train),
        "beta_grid_train_rho": beta_report,
        "gamma_grid_train_rho": gamma_report,
        "beta_argmax": beta_argmax,
        "gamma_argmax": gamma_argmax,
        "frozen_beta_used": FROZEN_BETA,
        "frozen_gamma_used": FROZEN_GAMMA,
        "argmax_matches_frozen": bool(beta_argmax == FROZEN_BETA
                                      and gamma_argmax == FROZEN_GAMMA),
        "note": ("check only; the arm is frozen at the 2026-07-15 values and "
                 "is NOT re-selected here"),
    }
    print(f"train check: beta_argmax={beta_argmax} gamma_argmax={gamma_argmax} "
          f"(frozen {FROZEN_BETA}/{FROZEN_GAMMA})")

    # ---- REGISTERED RE-GATE: frozen arm on the registered pair set ---------- #
    registered = gate_block(gate, "registered (complete outcomes only)")
    print(json.dumps({"registered": {
        "n": registered["n"], "rhos": registered["rhos_v1"],
        "gap_v1": registered["gap_ci_blend_minus_incumbent_v1"],
        "pass": registered["pass_v1"]}}, indent=1))

    # reproduction accounting vs the original artifact
    reproduction = {
        "original_n_gate": ORIGINAL["n_gate"],
        "n_gate_now": registered["n"],
        "original_rhos": {"fa_projection": ORIGINAL["rho_fa_projection"],
                          "output_blend": ORIGINAL["rho_output_blend"]},
        "rhos_now": {k: registered["rhos_v1"][k]
                     for k in ("fa_projection", "output_blend")},
        "original_gap_ci_v1": ORIGINAL["gap_ci_v1"],
        "gap_ci_v1_now": registered["gap_ci_blend_minus_incumbent_v1"],
        "reproduces_original": bool(
            registered["n"] == ORIGINAL["n_gate"]
            and registered["rhos_v1"]["fa_projection"] == ORIGINAL["rho_fa_projection"]
            and registered["rhos_v1"]["output_blend"] == ORIGINAL["rho_output_blend"]),
    }

    # ---- new-pair accounting ------------------------------------------------ #
    y_new = NEW_PRED_YEARS[0]
    accounting = {
        "new_pred_years_added": NEW_PRED_YEARS,
        "new_resolved_pairs_entering_gate": len(new_resolved),
        "partial_outcome_drops_by_new_year": {
            str(y): drops_by_year.get(y, {}).get("partial_outcome", 0)
            for y in NEW_PRED_YEARS},
        "season_complete_2026": plh.season_complete(2026),
        "harness_pair_rule": plh.convention_meta("", "")["pair_rule"],
        "explanation": (
            "The keep-alive's ~650 pairs/season arrive as predictor-2025 -> "
            "outcome-2026 pairs. The registered pair rule keeps a pair only "
            "when the OUTCOME season is complete (past Nov 15). On "
            f"{date.today().isoformat()} the 2026 season is in progress, so "
            "every 2025->2026 pair is dropped as partial_outcome under the "
            "registered protocol. The registered gate set therefore extends "
            f"by {len(new_resolved)} pairs at this vintage."),
    }

    # ---- UNREGISTERED sensitivity (a): small b grid on the registered set --- #
    tgt_g = [p["tgt"] for p in gate]
    fa_g = [p["fa"] for p in gate]
    beta_sens = {}
    for b in SENS_BETA_GRID:
        vals = [(1 - b) * p["fa"] + b * p["xw"] for p in gate]
        ci = plh.iid_boot_gaps(vals, {"fa_projection": fa_g}, tgt_g, BOOT, SEED)
        beta_sens[str(b)] = {"rho": _r4(_spearman(vals, tgt_g)),
                             "gap_ci_v1_vs_incumbent": ci["fa_projection"]}

    # ---- UNREGISTERED sensitivity (b): partial-2026 preview cohort ---------- #
    preview_pairs, p_drops, _ = build_pairs(
        by_season, xw, eng, NEW_PRED_YEARS, allow_partial_years={y_new})
    print(f"preview 2025->partial-2026 pairs={len(preview_pairs)} drops={p_drops}")
    preview = None
    pooled = None
    if len(preview_pairs) >= 30:
        preview = gate_block(preview_pairs,
                             "UNREGISTERED preview: 2025 -> partial 2026")
        pooled = gate_block(gate + preview_pairs,
                            "UNREGISTERED pooled: registered + partial-2026")
    sensitivity = {
        "status": ("UNREGISTERED - reported for information only; the verdict "
                   "comes from the frozen arm on the registered pair set"),
        "beta_grid_on_registered_gate_set": {
            "note": ("frozen arm is b=0.2; other b values are sensitivity "
                     "only, never verdict-bearing"),
            "grid": beta_sens},
        "partial_2026_preview": {
            "defect_warning": (
                "harness pair_rule calls partial-year targets a DEFECT; this "
                "block exists only to preview the November 2026 re-gate. "
                "Mid-2026 wOBA targets are PA-truncated and era-shifted; "
                "preview n is also a LOWER bound on the November cohort "
                "(players below 150 PA today can still cross the floor by "
                "season end)."),
            "n_preview_pairs": len(preview_pairs),
            "preview_drops": p_drops,
            "preview_gate": preview,
            "pooled_gate": pooled,
        },
    }

    # ---- verdict under the registered criterion ----------------------------- #
    pass_v1 = registered["pass_v1"]
    n_new = len(new_resolved)
    if pass_v1:
        status = "PASS"
        reason = ("frozen arm clears the registered criterion "
                  "(v1 lo95 >= 0) on the registered pair set")
    elif n_new == 0:
        status = "FAIL"
        reason = (
            "no new resolved pairs at this vintage: the 2025->2026 cohort is "
            "excluded by the registered complete-outcome pair rule until "
            "2026-11-15, so the gate set is the original one and the "
            "knife-edge refusal stands (lo95 < 0). The keep-alive re-gate "
            "becomes decidable after Nov 15, 2026.")
    else:
        status = "FAIL"
        reason = ("extended-n re-run of the frozen arm still has lo95 < 0 "
                  "under the registered criterion")
    verdict = {
        "status": status,
        "criterion": ("output_blend (frozen b=0.2) minus fa_projection, "
                      "paired iid bootstrap lo95 >= 0, v1 convention, "
                      f"seed {SEED}, {BOOT} reps (original recorded convention)"),
        "reason": reason,
        "next_regate": ("re-run this lab after 2026-11-15: season_complete(2026) "
                        "flips true and the 2025->2026 cohort (preview n "
                        f"{len(preview_pairs)}+, keep-alive estimate ~650) "
                        "enters the registered gate set"),
    }

    # ---- proposed production diff (only materialized on PASS) --------------- #
    proposed_diff = None
    if pass_v1:
        proposed_diff = {
            "file": "hitter_export.py",
            "function": "_join_pwoba",
            "anchor_lines": "291-294 (at HEAD 2026-07-23)",
            "change": (
                "after `w = (proj or {}).get(\"woba_proj\")` and the None "
                "guard, blend the current-season Savant est_woba at the "
                "frozen weight before stamping: load est_woba(season) from "
                ".cache/savant_mlb/expected_batter_{season}.csv via "
                "fa_sources/savant fetcher with PA >= 100; when present, "
                "w = 0.8 * w + 0.2 * est_woba; else keep w unchanged. "
                "pwoba_pctile recomputes over the blended pool unchanged."),
            "not_applied": True,
        }

    payload = {
        "experiment": ("pwoba_xwoba_blend keep-alive RE-GATE "
                       "(frozen arm b=0.2, original protocol, extended vintage)"),
        "generated_at": date.today().isoformat(),
        "seed": SEED, "boot": BOOT,
        "seed_note": ("original recorded convention reused (seed 20260715, "
                      "2000 reps, v1 iid paired bootstrap); the fallback seed "
                      f"{ALT_SEED_UNUSED} was not needed"),
        "harness": plh.convention_meta("wOBA(Y+1) raw pooled", "wOBA(Y+1)"),
        "ledger_reference": {
            "registry_row": "pwoba_xwoba_blend",
            "original_lab": "tools/xwoba_projection_blend_lab.py",
            "original_eval": "data/xwoba_projection_blend_eval.json",
            "original": ORIGINAL,
        },
        "protocol": {
            "replicates": ("original pair construction, arms, and gate rule "
                           "EXACTLY; hyperparameters FROZEN (b=0.2, g=0.1), "
                           "no re-tuning"),
            "extension": (f"predictor years {NEW_PRED_YEARS} appended "
                          "(outcome 2026); by_season loads through 2026"),
            "gate_rule": ("frozen output_blend vs incumbent fa_projection: "
                          "iid paired bootstrap lo95 >= 0 (v1)"),
            "pair_set": ("phem_marcel_lite_lab construction (MIN_PA 150/150, "
                         "3yr window su>=2 & PA>=600, complete outcomes) + "
                         f"Savant est_woba present at PA >= {SAVANT_MIN_PA}"),
        },
        "n_pairs": len(pairs), "n_train": len(train), "n_gate": len(gate),
        "drops": drops,
        "drops_by_pred_year": {str(y): d for y, d in drops_by_year.items()},
        "train_stability_check": train_check,
        "vintage_reproduction": reproduction,
        "new_pair_accounting": accounting,
        "registered_regate": registered,
        "unregistered_sensitivity": sensitivity,
        "verdict": verdict,
        "proposed_production_diff": proposed_diff,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = ROOT / "data" / "pwoba_blend_regate_eval.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps({
        "verdict": verdict["status"],
        "reason": verdict["reason"],
        "n_gate": registered["n"],
        "new_resolved_pairs": n_new,
        "gap_v1": registered["gap_ci_blend_minus_incumbent_v1"],
        "preview_n": len(preview_pairs),
        "preview_gap_v1": (preview or {}).get("gap_ci_blend_minus_incumbent_v1"),
        "pooled_gap_v1": (pooled or {}).get("gap_ci_blend_minus_incumbent_v1"),
    }, indent=1))


if __name__ == "__main__":
    main()
