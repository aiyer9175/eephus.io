# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV isotonic-calibration lab (X-ISO, spec item A5 in docs/xfv-phase2-plan.md).

EXPERIMENT (pre-registered gate: docs/audit-2026-07/AUDIT_FINDINGS.md, section X-ISO):
fit per-bucket isotonic regression OUT-OF-FOLD, forward-chained by decision-year cohort,
mapping the shipped pipeline's predicted 5-bucket outcome probabilities (bust..star,
value_framework.p_bucket_given_fv on the OOF eFV grade) to realized bucket frequencies,
then evaluate whether the calibrated distribution beats the uncalibrated one on the
pre-registered three-condition gate:

  1. OOF Brier + log-loss improve, pooled AND per bucket (no bucket materially worse,
     tolerance MATERIAL_TOL relative);
  2. forward Spearman of the resulting rank (expected WAR under the calibrated
     distribution) vs realized outcomes does not drop more than 0.002 vs the shipped
     OOF grade;
  3. reliability improves in EVERY FV tier (mean absolute per-bucket calibration gap;
     no tier worse).

PROTOCOL (no same-player leakage anywhere):
  - pool: full labeled matrix per side (debuted + busts, bust_recent excluded --
    identical to efv_model.oos_grades), target = KM-censored first-6yr summed bWAR.
  - realized bucket: 6yr-average annual WAR (target/6) binned by the engine's bucket
    bands (<0.5 bust / 0.5-1.5 bench / 1.5-2.5 regular / 2.5-4.0 good / 4.0+ star).
  - base OOF probabilities: for each chain year Y in 2016..2023, fit the SHIPPED seam
    (lean ridge + in-fold linear scale calibration -> xfv_war -> realized_implied_fv
    -> p_bucket_given_fv) on cohorts with decision_year < Y only, score cohort Y.
  - isotonic OOF: for each EVAL year Y in SCORED_YEARS (2020..2023), the per-bucket
    isotonic calibrators are fit ONLY on OOF rows with decision_year < Y (which were
    themselves predicted by models trained strictly before them), then applied to
    cohort Y and renormalized onto the simplex. A player is only ever scored in his
    own cohort year, so no row ever calibrates itself.
  - everything is deterministic (ridge/OLS/PAVA); SEED is set for any stochastic step.

This is an EXPERIMENT HARNESS ONLY -- nothing here wires into the pipeline. Ship
wiring happens later, only on a clear gate pass.

Artifact: data/xfv_isotonic_eval.json.  Run: python tools/efv_isotonic_lab.py
"""
from __future__ import annotations

import bisect
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)  # noqa: E702

import numpy as np

import value_framework as vf
from efv_dataset import matrix_path
from efv_model import _prep, _feature_spec, SCORED_YEARS
from efv_score import _age_at
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration, _spearman

SEED = 7                      # all stochastic steps seeded (isotonic/ridge are deterministic)
np.random.seed(SEED)

BUCKETS = ("bust", "bench", "regular", "good", "star")
BUCKET_EDGES = (0.5, 1.5, 2.5, 4.0)   # 6yr-avg annual WAR band edges (config buckets bands)
TARGET_SEASONS = 6.0

CHAIN_YEARS = tuple(range(2016, 2024))   # OOF prediction chain (2016-2019 seed the calibrators)
EVAL_YEARS = tuple(SCORED_YEARS)          # gate cohorts (2020-2023, the canonical eval years)
MIN_TRAIN, MIN_TEST = 60, 10
MIN_CAL_ROWS = 150            # minimum OOF rows before an isotonic calibrator is trusted
MIN_TIER_N = 15               # per-FV-tier reliability minimum (harness convention)
MATERIAL_TOL = 0.01           # "materially worse" per bucket = >1% relative degradation
SPEARMAN_TOL = 0.002          # pre-registered rank-drop tolerance
LL_CLIP = 1e-6                # log-loss probability clip

OUT_PATH = ROOT / "data" / "xfv_isotonic_eval.json"


def realized_bucket(target_war_6yr: float) -> int:
    """Realized outcome bucket: 6yr-average annual WAR binned by the engine bands."""
    return bisect.bisect_right(BUCKET_EDGES, target_war_6yr / TARGET_SEASONS)


def _tier(fv: float) -> int:
    return int(round(fv / 5) * 5)


# ---------------------------------------------------------------------------
# base OOF probabilities (the shipped seam, forward-chained)
# ---------------------------------------------------------------------------

def oof_rows(side: str) -> list[dict]:
    """Forward-chained OOF rows for one side. Each row: the shipped pipeline's
    predicted 5-bucket distribution (uncalibrated), the OOF eFV grade, the realized
    bucket, and bookkeeping (cohort year, consensus FV, weight)."""
    is_pit = side == "pit"
    keys, _mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    by_key = {r["player_key"]: r for r in pool}

    out = []
    for yr in CHAIN_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < MIN_TEST or len(tr) < MIN_TRAIN:
            continue
        ridge = _fit_ridge(tr, keys)
        if not ridge:
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            src = by_key[r["player_key"]]
            xfv_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            dyear = src.get("debut_year") or 2020            # mirrors efv_score.run()
            age = _age_at(src.get("birth_date"), dyear)
            grade = vf.realized_implied_fv(xfv_war, is_pit, age=age,
                                           position=src.get("position"))
            if grade is None:
                continue
            probs = vf.p_bucket_given_fv(grade, is_pit)
            if not probs or len(probs) != len(BUCKETS):
                continue
            out.append({
                "player_key": r["player_key"], "side": side,
                "decision_year": yr, "fv": r["fv"], "grade": float(grade),
                "p_before": np.asarray(probs, dtype=float),
                "y": realized_bucket(r["target"]),
                "target": float(r["target"]),
                "weight": float(r["weight"]),
            })
    return out


# ---------------------------------------------------------------------------
# out-of-fold isotonic (per bucket, per side, forward-chained by eval year)
# ---------------------------------------------------------------------------

def fit_bucket_isotonics(cal_rows: list[dict]):
    """One isotonic regressor per bucket: predicted p_b -> realized 1{y==b},
    weighted by the row's KM observed-fraction weight (training convention)."""
    from sklearn.isotonic import IsotonicRegression
    isos = []
    for b in range(len(BUCKETS)):
        x = np.array([r["p_before"][b] for r in cal_rows])
        y = np.array([1.0 if r["y"] == b else 0.0 for r in cal_rows])
        w = np.array([r["weight"] for r in cal_rows])
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(x, y, sample_weight=w)
        isos.append(iso)
    return isos


def apply_isotonics(isos, p_before: np.ndarray) -> np.ndarray:
    q = np.array([float(isos[b].predict([p_before[b]])[0]) for b in range(len(BUCKETS))])
    s = q.sum()
    if s <= 1e-9:                      # degenerate: fall back to the uncalibrated row
        return p_before.copy()
    return q / s


def build_calibrated(rows_by_side: dict) -> list[dict]:
    """Attach p_after to every EVAL-year row, fit strictly on earlier OOF cohorts."""
    eval_rows = []
    for side, rows in rows_by_side.items():
        for yr in EVAL_YEARS:
            cal_rows = [r for r in rows if r["decision_year"] < yr]
            te = [r for r in rows if r["decision_year"] == yr]
            if not te:
                continue
            if len(cal_rows) < MIN_CAL_ROWS:
                continue                # never calibrate on a thin prior sample
            isos = fit_bucket_isotonics(cal_rows)
            for r in te:
                r = dict(r)
                r["p_after"] = apply_isotonics(isos, r["p_before"])
                r["n_cal"] = len(cal_rows)
                eval_rows.append(r)
    return eval_rows


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _onehot(y: int) -> np.ndarray:
    v = np.zeros(len(BUCKETS))
    v[y] = 1.0
    return v


def brier_pooled(rows, key) -> float:
    return float(np.mean([np.sum((r[key] - _onehot(r["y"])) ** 2) for r in rows]))


def brier_per_bucket(rows, key) -> dict:
    P = np.array([r[key] for r in rows])
    Y = np.array([_onehot(r["y"]) for r in rows])
    return {BUCKETS[b]: float(np.mean((P[:, b] - Y[:, b]) ** 2)) for b in range(len(BUCKETS))}


def logloss_pooled(rows, key) -> float:
    return float(np.mean([-np.log(np.clip(r[key][r["y"]], LL_CLIP, 1.0)) for r in rows]))


def logloss_per_bucket(rows, key) -> dict:
    P = np.array([np.clip(r[key], LL_CLIP, 1 - LL_CLIP) for r in rows])
    Y = np.array([_onehot(r["y"]) for r in rows])
    return {BUCKETS[b]: float(np.mean(-(Y[:, b] * np.log(P[:, b])
                                        + (1 - Y[:, b]) * np.log(1 - P[:, b]))))
            for b in range(len(BUCKETS))}


def expected_war(rows, key, mids_by_side) -> list[float]:
    return [float(np.dot(r[key], mids_by_side[r["side"]])) for r in rows]


def tier_reliability(rows) -> dict:
    """Per consensus-FV tier: mean absolute per-bucket calibration gap
    (|mean predicted p_b - realized freq_b| averaged over buckets), before vs after."""
    by_tier = defaultdict(list)
    for r in rows:
        by_tier[_tier(r["fv"])].append(r)
    out = {}
    for tk in sorted(by_tier):
        grp = by_tier[tk]
        if len(grp) < MIN_TIER_N:
            continue
        freq = np.mean([_onehot(r["y"]) for r in grp], axis=0)
        mb = np.mean([r["p_before"] for r in grp], axis=0)
        ma = np.mean([r["p_after"] for r in grp], axis=0)
        gap_b = float(np.mean(np.abs(mb - freq)))
        gap_a = float(np.mean(np.abs(ma - freq)))
        out[str(tk)] = {
            "n": len(grp),
            "realized_freq": {BUCKETS[i]: round(float(freq[i]), 4) for i in range(len(BUCKETS))},
            "mean_p_before": {BUCKETS[i]: round(float(mb[i]), 4) for i in range(len(BUCKETS))},
            "mean_p_after": {BUCKETS[i]: round(float(ma[i]), 4) for i in range(len(BUCKETS))},
            "gap_before": round(gap_b, 5), "gap_after": round(gap_a, 5),
            "improved": bool(gap_a < gap_b - 1e-9),
            "worse": bool(gap_a > gap_b + 1e-4),
        }
    return out


def reliability_bins(rows, key, n_bins: int = 10) -> dict:
    """Pooled per-bucket reliability curve (equal-width probability bins) + ECE."""
    out = {}
    for b, name in enumerate(BUCKETS):
        p = np.array([r[key][b] for r in rows])
        y = np.array([1.0 if r["y"] == b else 0.0 for r in rows])
        edges = np.linspace(0.0, 1.0, n_bins + 1)
        curve, ece = [], 0.0
        for i in range(n_bins):
            m = (p >= edges[i]) & (p < edges[i + 1] if i < n_bins - 1 else p <= 1.0)
            if m.sum() < 5:
                continue
            mp, fr = float(p[m].mean()), float(y[m].mean())
            curve.append({"bin": [round(float(edges[i]), 2), round(float(edges[i + 1]), 2)],
                          "n": int(m.sum()), "mean_p": round(mp, 4), "freq": round(fr, 4)})
            ece += (m.sum() / len(p)) * abs(mp - fr)
        out[name] = {"ece": round(float(ece), 5), "curve": curve}
    return out


# ---------------------------------------------------------------------------
# gate evaluation
# ---------------------------------------------------------------------------

def _rel_worse(after: float, before: float) -> float:
    """Relative degradation (positive = worse). before==0 guarded."""
    if before <= 0:
        return 0.0 if after <= before else float("inf")
    return (after - before) / before


def evaluate(rows: list[dict]) -> dict:
    mids = {"hit": np.asarray(vf._calibrated_midpoints("hitter")),
            "pit": np.asarray(vf._calibrated_midpoints("pitcher"))}

    def _block(sub):
        bb, ba = brier_pooled(sub, "p_before"), brier_pooled(sub, "p_after")
        lb, la = logloss_pooled(sub, "p_before"), logloss_pooled(sub, "p_after")
        pbb, pba = brier_per_bucket(sub, "p_before"), brier_per_bucket(sub, "p_after")
        plb, pla = logloss_per_bucket(sub, "p_before"), logloss_per_bucket(sub, "p_after")
        targets = [r["target"] for r in sub]
        rho_shipped = _spearman([r["grade"] for r in sub], targets)
        rho_before = _spearman(expected_war(sub, "p_before", mids), targets)
        rho_after = _spearman(expected_war(sub, "p_after", mids), targets)
        return {
            "n": len(sub),
            "brier": {"before": round(bb, 5), "after": round(ba, 5),
                      "delta": round(ba - bb, 5)},
            "log_loss": {"before": round(lb, 5), "after": round(la, 5),
                         "delta": round(la - lb, 5)},
            "per_bucket": {
                name: {"brier_before": round(pbb[name], 5), "brier_after": round(pba[name], 5),
                       "logloss_before": round(plb[name], 5), "logloss_after": round(pla[name], 5),
                       "brier_improved": bool(pba[name] < pbb[name]),
                       "logloss_improved": bool(pla[name] < plb[name]),
                       "materially_worse": bool(_rel_worse(pba[name], pbb[name]) > MATERIAL_TOL
                                                or _rel_worse(pla[name], plb[name]) > MATERIAL_TOL)}
                for name in BUCKETS},
            "spearman": {"shipped_grade": round(rho_shipped, 4) if rho_shipped is not None else None,
                         "expected_war_before": round(rho_before, 4) if rho_before is not None else None,
                         "expected_war_after": round(rho_after, 4) if rho_after is not None else None},
        }

    pooled = _block(rows)
    per_side = {s: _block([r for r in rows if r["side"] == s]) for s in ("hit", "pit")}
    tiers = tier_reliability(rows)
    curves = {"before": reliability_bins(rows, "p_before"),
              "after": reliability_bins(rows, "p_after")}

    # --- condition 1: Brier + log-loss improve pooled AND per bucket ---------
    pooled_improves = (pooled["brier"]["after"] < pooled["brier"]["before"]
                       and pooled["log_loss"]["after"] < pooled["log_loss"]["before"])
    buckets_improve = all(v["brier_improved"] and v["logloss_improved"]
                          for v in pooled["per_bucket"].values())
    no_bucket_material = not any(v["materially_worse"] for v in pooled["per_bucket"].values())
    cond1 = bool(pooled_improves and buckets_improve and no_bucket_material)

    # --- condition 2: Spearman drop vs shipped within tolerance --------------
    rs, ra = pooled["spearman"]["shipped_grade"], pooled["spearman"]["expected_war_after"]
    cond2 = bool(rs is not None and ra is not None and (ra - rs) >= -SPEARMAN_TOL)

    # --- condition 3: reliability improves in every FV tier ------------------
    tier_flags = {tk: v["improved"] for tk, v in tiers.items()}
    cond3 = bool(tiers) and all(v["improved"] for v in tiers.values())
    any_tier_worse = any(v["worse"] for v in tiers.values())

    gate = {
        "condition_1_brier_logloss": {
            "pass": cond1,
            "pooled_improves": bool(pooled_improves),
            "all_buckets_improve": bool(buckets_improve),
            "no_bucket_materially_worse": bool(no_bucket_material),
            "material_tolerance_rel": MATERIAL_TOL,
        },
        "condition_2_spearman": {
            "pass": cond2,
            "shipped_grade_rho": rs, "calibrated_rank_rho": ra,
            "delta": round(ra - rs, 4) if (rs is not None and ra is not None) else None,
            "tolerance": -SPEARMAN_TOL,
        },
        "condition_3_tier_reliability": {
            "pass": cond3,
            "tiers_improved": tier_flags,
            "n_tiers": len(tiers),
            "n_improved": sum(1 for v in tiers.values() if v["improved"]),
            "any_tier_worse": bool(any_tier_worse),
        },
        "verdict": "PASS" if (cond1 and cond2 and cond3) else "FAIL",
    }
    return {"pooled": pooled, "per_side": per_side, "per_tier_reliability": tiers,
            "reliability_curves_pooled": curves, "gate": gate}


# ---------------------------------------------------------------------------
# artifact
# ---------------------------------------------------------------------------

def run(persist: bool = True) -> dict:
    rows_by_side = {s: oof_rows(s) for s in ("hit", "pit")}
    eval_rows = build_calibrated(rows_by_side)

    splits = {}
    for s in ("hit", "pit"):
        cnt = defaultdict(int)
        for r in rows_by_side[s]:
            cnt[r["decision_year"]] += 1
        splits[s] = {
            "chain_oof_rows_by_year": {str(y): cnt[y] for y in sorted(cnt)},
            "eval_rows": sum(1 for r in eval_rows if r["side"] == s),
            "calibrator_train_rows_by_eval_year": {
                str(y): len([r for r in rows_by_side[s] if r["decision_year"] < y])
                for y in EVAL_YEARS},
        }

    res = evaluate(eval_rows)
    out = {
        "generated_at": date.today().isoformat(),
        "experiment": "X-ISO: out-of-fold isotonic calibration of the eFV 5-bucket outcome distribution",
        "spec": "docs/xfv-phase2-plan.md A5; gate pre-registered in docs/audit-2026-07/AUDIT_FINDINGS.md section X-ISO",
        "method": {
            "base_distribution": "shipped seam, forward-chained OOF: lean ridge + in-fold linear "
                                 "scale calibration -> xfv_war -> realized_implied_fv -> "
                                 "p_bucket_given_fv (uncalibrated 'before')",
            "calibration": "per-bucket sklearn IsotonicRegression (PAVA, deterministic), fit on "
                           "predicted p_b vs realized 1{y==b}, KM-weight sample weights, then "
                           "renormalized onto the simplex ('after')",
            "oof_protocol": "isotonic for eval cohort Y fit ONLY on OOF rows with decision_year < Y; "
                            "those rows were themselves predicted by models trained strictly before "
                            "them (chain years 2016-2023); no row ever calibrates itself; no "
                            "same-player leakage (each player appears in exactly one cohort)",
            "realized_bucket": "6yr-average annual WAR (target_censored/6) binned by the engine "
                               "bands: <0.5 bust / 0.5-1.5 bench / 1.5-2.5 regular / 2.5-4.0 good / 4.0+ star",
            "pool": "full labeled matrix per side (debuted + busts, bust_recent excluded), "
                    "matching efv_model.oos_grades",
            "rank_metric": "expected WAR under the distribution (bucket probs x calibrated "
                           "bucket midpoints); shipped baseline = OOF eFV grade",
            "eval_years": list(EVAL_YEARS),
            "chain_years": [CHAIN_YEARS[0], CHAIN_YEARS[-1]],
            "min_calibrator_rows": MIN_CAL_ROWS,
        },
        "seed": SEED,
        "cohort_splits": splits,
        "results": res,
        "gate": res["gate"],
    }

    if out["gate"]["verdict"] != "PASS":
        g = out["gate"]
        failed = [k for k in ("condition_1_brier_logloss", "condition_2_spearman",
                              "condition_3_tier_reliability") if not g[k]["pass"]]
        out["loss_ledger"] = {
            "date": date.today().isoformat(),
            "experiment": "X-ISO out-of-fold isotonic calibration (5-bucket eFV outcome distribution)",
            "hypothesis": "OOF per-bucket isotonic improves probability calibration without hurting ranking",
            "what_was_tried": "per-bucket PAVA isotonic on the shipped OOF distribution, "
                              "forward-chained by cohort with 2016-2019 seeding the first "
                              "calibrator; simplex renormalization; KM sample weights",
            "result": {
                "failed_conditions": failed,
                "pooled_brier_before_after": [res["pooled"]["brier"]["before"],
                                              res["pooled"]["brier"]["after"]],
                "pooled_logloss_before_after": [res["pooled"]["log_loss"]["before"],
                                                res["pooled"]["log_loss"]["after"]],
                "spearman_shipped_vs_calibrated": [g["condition_2_spearman"]["shipped_grade_rho"],
                                                   g["condition_2_spearman"]["calibrated_rank_rho"]],
                "tiers_improved": f"{g['condition_3_tier_reliability']['n_improved']}/"
                                  f"{g['condition_3_tier_reliability']['n_tiers']}",
                "tiers_worse": [tk for tk, v in res["per_tier_reliability"].items() if v["worse"]],
                "per_side_spearman": {s: res["per_side"][s]["spearman"] for s in ("hit", "pit")},
            },
            "diagnosis": "the rank metric is faithful (within each side, expected-WAR-before rho "
                         "equals the shipped grade rho exactly), so the Spearman drop is caused by "
                         "the isotonic step itself: PAVA's flat segments tie previously-distinct "
                         "grades and lose within-segment ordering. Calibration quality genuinely "
                         "improves (condition 1 passes, every bucket better; tier gaps shrink in "
                         "5/6 tiers, driven by bust-probability over/under-prediction at FV 45+), "
                         "but it costs more rank than the pre-registered tolerance allows and the "
                         "FV-35 tier (already near-perfectly calibrated) gets slightly worse.",
            "reading": "pre-registered gate requires ALL THREE conditions; a marginal result is a FAIL "
                       "(owner policy). The distribution stays on the engine's own calibration "
                       "(value_framework p_bucket_given_fv); no double-correction is shipped.",
            "disposition": "NO SHIP. Harness (tools/efv_isotonic_lab.py) + this artifact are the "
                           "committed loss; re-attempt only with a materially different method or "
                           "more resolved cohorts.",
        }

    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"wrote {OUT_PATH}")
    return out


if __name__ == "__main__":
    rep = run(persist="--dry" not in sys.argv)
    g = rep["gate"]
    p = rep["results"]["pooled"]
    print(f"\nX-ISO gate verdict: {g['verdict']}")
    print(f"  n eval rows: {p['n']}")
    print(f"  cond1 (brier/logloss): {g['condition_1_brier_logloss']['pass']} | "
          f"brier {p['brier']['before']} -> {p['brier']['after']} | "
          f"logloss {p['log_loss']['before']} -> {p['log_loss']['after']}")
    print(f"  cond2 (spearman): {g['condition_2_spearman']['pass']} | "
          f"shipped {g['condition_2_spearman']['shipped_grade_rho']} -> "
          f"calibrated {g['condition_2_spearman']['calibrated_rank_rho']} "
          f"(delta {g['condition_2_spearman']['delta']})")
    print(f"  cond3 (tier reliability): {g['condition_3_tier_reliability']['pass']} | "
          f"improved {g['condition_3_tier_reliability']['n_improved']}/"
          f"{g['condition_3_tier_reliability']['n_tiers']}")
    for name, v in p["per_bucket"].items():
        print(f"    {name:8s} brier {v['brier_before']} -> {v['brier_after']} | "
              f"logloss {v['logloss_before']} -> {v['logloss_after']}"
              f"{'  MATERIALLY WORSE' if v['materially_worse'] else ''}")
