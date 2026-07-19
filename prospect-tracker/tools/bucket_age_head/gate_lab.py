# Bucket-head calibration gate (pre-registered, owner-approved 2026-07-15).
#
# Pit-only covariate bucket head BELOW the grade-monotone constraint:
#   p(bucket | grade_band, age_band), age bands <=22 / 23-24 / 25+,
#   grade bands = the existing 5-point FV tiers (round(fv/5)*5, the
#   tier_reliability convention), cells partially pooled toward the incumbent
#   p_bucket_given_fv row with weight n/(n+25).
#
# Fit population mirrors the incumbent bucket calibration's conventions
# (value_framework --fit: realized outcome shares by grade band; buckets =
# engine 6yr-avg annual WAR bands <0.5/1.5/2.5/4.0), instantiated on the
# repo's resolved labeled pitcher matrix: is_pitcher, debuted+busts,
# bust_recent excluded, censored == False, consensus_fv_raw + target present
# (the efv_model.oos_grades pool restricted to resolved labels).
#
# GATES (all must hold; pre-registered):
#  G1 pooled multiclass log-loss of the head <= incumbent on forward-chained
#     folds 2020-2023 (head fit strictly pre-fold; incumbent = the fixed
#     production p_bucket_given_fv at the same conditioning grade).
#  G2 E-ISO4 guard: pit BENCH and GOOD per-bucket (binary) log-loss
#     <= +1.0% relative vs incumbent.
#  G3 age-25+ subset pooled log-loss strictly improves.
#  G4 production head: valid distributions (sum 1, all >= 0) and
#     monotone-sane in grade within each age band (cumulative P(Y<=j)
#     non-increasing in grade, tolerance 1e-6) on a dense 20-80 grid.
#
# Bootstrap: 2000 reps, seed 20260715, row resampling of the pooled eval set.
# READ-ONLY against the repo. Run: python gate_lab.py
from __future__ import annotations

import bisect
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(r"C:/Users/noah/baseball-projects/BaseballR/prospect-tracker")
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

import value_framework as vf  # noqa: E402  (read-only import; production params)

SEED = 20260715
N_BOOT = 2000
BUCKETS = ("bust", "bench", "regular", "good", "star")
BUCKET_EDGES = (0.5, 1.5, 2.5, 4.0)   # engine bands on 6yr-avg annual WAR
TARGET_SEASONS = 6.0
AGE_BANDS = ("le22", "23_24", "25p")
SHRINK_N = 25.0                        # partial-pooling prior weight (pre-registered)
EVAL_YEARS = (2020, 2021, 2022, 2023)
MIN_TRAIN, MIN_TEST = 60, 10           # chain guards (efv_model convention)
LL_CLIP = 1e-6                         # lab log-loss clip (efv_isotonic_lab)
MATERIAL_TOL = 0.01                    # +1.0% relative (E-ISO4 / F-SIDE S3)
MONO_TOL = 1e-6                        # numerical tolerance for gate 4
GRID = np.arange(20.0, 80.0 + 1e-9, 0.25)

MATRIX = REPO / "data" / "xfv_pitcher_matrix.json"
OUT = HERE / "results.json"
EVAL_ROWS_CKPT = HERE / "eval_rows_ckpt.json"
HEAD_JSON = HERE / "patched" / "data" / "xfv_bucket_age_head.json"


# ---------------------------------------------------------------------------
# conventions (mirroring efv_model / efv_isotonic_lab / value_framework)
# ---------------------------------------------------------------------------

def tier(fv: float) -> int:
    """The existing grade-band convention (efv_isotonic_lab._tier)."""
    return int(round(fv / 5) * 5)


def age_band(age) -> str | None:
    if age is None:
        return None
    a = float(age)
    if a < 23.0:
        return "le22"
    if a < 25.0:
        return "23_24"
    return "25p"


def age_decision(r) -> float | None:
    """Age at the decision cutoff (the serve-time age_now analog).
    birth_date preferred (exact date arithmetic); fallback = milb.age (season
    age at the last pre-decision MiLB read) advanced by cutoff-vs-season
    staleness; None when neither exists (head falls back to the incumbent)."""
    bd, cut = r.get("birth_date"), r.get("cutoff")
    if bd and cut:
        try:
            b = date.fromisoformat(str(bd)[:10])
            c = date.fromisoformat(str(cut)[:10])
            return round((c - b).days / 365.25, 2)
        except ValueError:
            pass
    m = r.get("milb") or {}
    if m.get("age") is not None and not m.get("age_missing"):
        try:
            cy = int(str(cut)[:4])
            adj = max(0, cy - int(m.get("milb_season") or cy))
            return float(m["age"]) + adj
        except (TypeError, ValueError):
            return float(m["age"])
    return None


def decision_year(r) -> int:
    """efv_model._decision_year verbatim."""
    if r["kind"] == "debuted":
        return int(r["debut_year"])
    c = r.get("cutoff") or ""
    return (int(c[:4]) + 1) if c[:4].isdigit() else 2026


def realized_bucket(t: float) -> int:
    return bisect.bisect_right(BUCKET_EDGES, t / TARGET_SEASONS)


def incumbent(fv: float) -> np.ndarray:
    p = vf.p_bucket_given_fv(float(fv), True)
    return np.asarray(p, dtype=float)


# ---------------------------------------------------------------------------
# pool
# ---------------------------------------------------------------------------

def load_pool() -> list[dict]:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    pool = []
    for r in rows:
        if not r.get("is_pitcher"):
            continue
        if r["kind"] == "bust" and r.get("bust_recent"):
            continue
        if r.get("censored"):
            continue
        if r.get("consensus_fv_raw") is None or r.get("target_resolved") is None:
            continue
        fv = float(r["consensus_fv_raw"])
        age = age_decision(r)
        pool.append({
            "player_key": r["player_key"], "kind": r["kind"],
            "decision_year": decision_year(r),
            "fv": fv, "grade_band": tier(fv),
            "age": age, "age_band": age_band(age),
            "y": realized_bucket(float(r["target_resolved"])),
            "target": float(r["target_resolved"]),
        })
    return pool


# ---------------------------------------------------------------------------
# the head
# ---------------------------------------------------------------------------

def fit_head(train: list[dict]) -> dict:
    """Cell counts per (grade_band, age_band). Age-unknown rows cannot
    populate a cell (they are served by the incumbent fallback)."""
    cells: dict = defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in train:
        if r["age_band"] is None:
            continue
        cells[(r["grade_band"], r["age_band"])][r["y"]] += 1
    return {k: list(v) for k, v in cells.items()}


def head_prob(cells: dict, fv: float, age) -> np.ndarray:
    """p(bucket | grade, age): partial pooling of the cell empirical toward
    the incumbent row evaluated at the ACTUAL grade, weight n/(n+SHRINK_N).
    Missing age / missing cell -> the incumbent exactly (w=0)."""
    inc = incumbent(fv)
    ab = age_band(age)
    if ab is None:
        return inc
    cnt = cells.get((tier(fv), ab))
    if not cnt:
        return inc
    n = float(sum(cnt))
    if n <= 0:
        return inc
    w = n / (n + SHRINK_N)
    emp = np.asarray(cnt, dtype=float) / n
    p = w * emp + (1.0 - w) * inc
    s = p.sum()
    return p / s if s > 0 else inc


# ---------------------------------------------------------------------------
# metrics (efv_isotonic_lab conventions)
# ---------------------------------------------------------------------------

def _onehot(y: int) -> np.ndarray:
    v = np.zeros(len(BUCKETS))
    v[y] = 1.0
    return v


def ll_pooled(P: np.ndarray, Y: np.ndarray) -> float:
    """Multiclass log-loss: mean -log p_y (clip LL_CLIP)."""
    py = P[np.arange(len(Y)), Y]
    return float(np.mean(-np.log(np.clip(py, LL_CLIP, 1.0))))


def ll_bucket(P: np.ndarray, Y: np.ndarray, b: int) -> float:
    """Per-bucket binary cross-entropy (efv_isotonic_lab.logloss_per_bucket)."""
    p = np.clip(P[:, b], LL_CLIP, 1 - LL_CLIP)
    y = (Y == b).astype(float)
    return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))


def brier_pooled(P: np.ndarray, Y: np.ndarray) -> float:
    O = np.zeros_like(P)
    O[np.arange(len(Y)), Y] = 1.0
    return float(np.mean(np.sum((P - O) ** 2, axis=1)))


def _rel_worse(after: float, before: float) -> float:
    if before <= 0:
        return 0.0 if after <= before else float("inf")
    return (after - before) / before


# ---------------------------------------------------------------------------
# forward-chained eval
# ---------------------------------------------------------------------------

def build_eval_rows(pool: list[dict]) -> tuple[list[dict], dict]:
    eval_rows, fold_diag = [], {}
    for yr in EVAL_YEARS:
        tr = [r for r in pool if r["decision_year"] < yr]
        te = [r for r in pool if r["decision_year"] == yr]
        if len(te) < MIN_TEST or len(tr) < MIN_TRAIN:
            fold_diag[str(yr)] = {"skipped": True, "n_train": len(tr), "n_test": len(te)}
            continue
        cells = fit_head(tr)
        for r in te:
            rr = dict(r)
            rr["p_head"] = head_prob(cells, r["fv"], r["age"]).tolist()
            rr["p_inc"] = incumbent(r["fv"]).tolist()
            eval_rows.append(rr)
        n_cells = len(cells)
        fold_diag[str(yr)] = {
            "skipped": False, "n_train": len(tr), "n_test": len(te),
            "n_train_age_known": sum(1 for r in tr if r["age_band"] is not None),
            "n_test_age_known": sum(1 for r in te if r["age_band"] is not None),
            "n_test_25p": sum(1 for r in te if r["age_band"] == "25p"),
            "test_kinds": dict(Counter(r["kind"] for r in te)),
            "n_head_cells": n_cells,
        }
    return eval_rows, fold_diag


def metric_block(rows: list[dict]) -> dict:
    P_h = np.array([r["p_head"] for r in rows])
    P_i = np.array([r["p_inc"] for r in rows])
    Y = np.array([r["y"] for r in rows])
    out = {
        "n": len(rows),
        "log_loss": {"incumbent": round(ll_pooled(P_i, Y), 5),
                     "head": round(ll_pooled(P_h, Y), 5)},
        "brier": {"incumbent": round(brier_pooled(P_i, Y), 5),
                  "head": round(brier_pooled(P_h, Y), 5)},
        "per_bucket_log_loss": {},
    }
    out["log_loss"]["delta"] = round(out["log_loss"]["head"] - out["log_loss"]["incumbent"], 5)
    out["brier"]["delta"] = round(out["brier"]["head"] - out["brier"]["incumbent"], 5)
    for b, name in enumerate(BUCKETS):
        li, lh = ll_bucket(P_i, Y, b), ll_bucket(P_h, Y, b)
        out["per_bucket_log_loss"][name] = {
            "incumbent": round(li, 5), "head": round(lh, 5),
            "delta": round(lh - li, 5),
            "rel_delta": round(_rel_worse(lh, li), 5) if np.isfinite(_rel_worse(lh, li)) else None,
        }
    return out


# ---------------------------------------------------------------------------
# gate 4: production-head validity + grade monotone-sanity
# ---------------------------------------------------------------------------

def gate4_check(cells: dict) -> dict:
    rep_age = {"le22": 21.0, "23_24": 23.5, "25p": 27.0}
    worst_sum, worst_neg = 0.0, 0.0
    violations = []
    for ab in AGE_BANDS:
        prev_cum = None
        prev_fv = None
        for fv in GRID:
            p = head_prob(cells, float(fv), rep_age[ab])
            worst_sum = max(worst_sum, abs(float(p.sum()) - 1.0))
            worst_neg = min(worst_neg, float(p.min()))
            cum = np.cumsum(p)[:4]
            if prev_cum is not None:
                jump = cum - prev_cum          # must be <= 0 (non-increasing in grade)
                mv = float(jump.max())
                if mv > MONO_TOL:
                    j = int(np.argmax(jump))
                    violations.append({
                        "age_band": ab, "fv_from": round(float(prev_fv), 2),
                        "fv_to": round(float(fv), 2),
                        "threshold": f"P(Y<={BUCKETS[j]})",
                        "increase": round(mv, 5),
                    })
            prev_cum, prev_fv = cum, fv
    # compact: keep the worst violation per (age_band, boundary fv_to)
    seen = {}
    for v in violations:
        k = (v["age_band"], v["fv_to"])
        if k not in seen or v["increase"] > seen[k]["increase"]:
            seen[k] = v
    compact = sorted(seen.values(), key=lambda v: -v["increase"])
    return {
        "valid_distributions": bool(worst_sum < 1e-9 and worst_neg >= 0.0),
        "max_abs_sum_minus_1": float(worst_sum),
        "min_prob": float(worst_neg),
        "monotone_sane": not compact,
        "monotone_tolerance": MONO_TOL,
        "n_violation_boundaries": len(compact),
        "max_violation": compact[0]["increase"] if compact else 0.0,
        "violations": compact[:20],
        "grid": [float(GRID[0]), float(GRID[-1]), 0.25],
    }


# ---------------------------------------------------------------------------
# bootstrap (2000 reps, seed 20260715)
# ---------------------------------------------------------------------------

def bootstrap(rows: list[dict]) -> dict:
    rng = np.random.default_rng(SEED)
    P_h = np.array([r["p_head"] for r in rows])
    P_i = np.array([r["p_inc"] for r in rows])
    Y = np.array([r["y"] for r in rows])
    is25 = np.array([r["age_band"] == "25p" for r in rows])
    n = len(rows)
    deltas = {"pooled_ll": [], "bench_ll": [], "good_ll": [], "ll_25p": []}
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, n)
        ph, pi, y, m25 = P_h[idx], P_i[idx], Y[idx], is25[idx]
        deltas["pooled_ll"].append(ll_pooled(ph, y) - ll_pooled(pi, y))
        deltas["bench_ll"].append(ll_bucket(ph, y, 1) - ll_bucket(pi, y, 1))
        deltas["good_ll"].append(ll_bucket(ph, y, 3) - ll_bucket(pi, y, 3))
        if m25.sum() >= 5:
            deltas["ll_25p"].append(ll_pooled(ph[m25], y[m25]) - ll_pooled(pi[m25], y[m25]))
    out = {"n_reps": N_BOOT, "seed": SEED}
    for k, v in deltas.items():
        a = np.array(v)
        out[k] = {
            "n_effective_reps": len(a),
            "mean_delta": round(float(a.mean()), 5),
            "ci90": [round(float(np.percentile(a, 5)), 5),
                     round(float(np.percentile(a, 95)), 5)],
            "p_delta_le_0": round(float((a <= 0).mean()), 4),
        }
    return out


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def main():
    pool = load_pool()
    eval_rows, fold_diag = build_eval_rows(pool)
    EVAL_ROWS_CKPT.write_text(json.dumps(eval_rows, indent=0), encoding="utf-8")
    print(f"checkpoint: {len(eval_rows)} eval rows -> {EVAL_ROWS_CKPT.name}")

    pooled = metric_block(eval_rows)
    sub25 = metric_block([r for r in eval_rows if r["age_band"] == "25p"])
    sub_age_known = metric_block([r for r in eval_rows if r["age_band"] is not None])
    per_fold = {str(y): metric_block([r for r in eval_rows if r["decision_year"] == y])
                for y in EVAL_YEARS
                if any(r["decision_year"] == y for r in eval_rows)}
    per_band = {ab: metric_block([r for r in eval_rows if r["age_band"] == ab])
                for ab in AGE_BANDS
                if any(r["age_band"] == ab for r in eval_rows)}

    # production head: full resolved pool (every decision year)
    prod_cells = fit_head(pool)
    g4 = gate4_check(prod_cells)

    boot = bootstrap(eval_rows)

    # gates -------------------------------------------------------------
    g1_pass = pooled["log_loss"]["head"] <= pooled["log_loss"]["incumbent"]
    bench = pooled["per_bucket_log_loss"]["bench"]
    good = pooled["per_bucket_log_loss"]["good"]
    g2_bench_ok = _rel_worse(bench["head"], bench["incumbent"]) <= MATERIAL_TOL
    g2_good_ok = _rel_worse(good["head"], good["incumbent"]) <= MATERIAL_TOL
    g2_pass = bool(g2_bench_ok and g2_good_ok)
    g3_pass = sub25["log_loss"]["head"] < sub25["log_loss"]["incumbent"]
    g4_pass = bool(g4["valid_distributions"] and g4["monotone_sane"])
    verdict = "PASS" if (g1_pass and g2_pass and g3_pass and g4_pass) else "FAIL"

    # Moore -------------------------------------------------------------
    moore = {}
    for label, g in (("xfv_grade_live_45.8", 45.8), ("band_rep_45.0", 45.0),
                     ("registered_motivation_grade_48.0", 48.0)):
        ph = head_prob(prod_cells, g, 26.9)
        pi = incumbent(g)
        moore[label] = {"grade": g, "age": 26.9,
                        "incumbent_p_bust": round(float(pi[0]), 3),
                        "head_p_bust": round(float(ph[0]), 3),
                        "head_p_bucket": {b: round(float(p), 3)
                                          for b, p in zip(BUCKETS, ph)}}
    cell = prod_cells.get((45, "25p"), [0] * 5)
    n_cell = sum(cell)
    moore["cell_fv45_25p"] = {
        "n": n_cell,
        "empirical_p_bust": round(cell[0] / n_cell, 3) if n_cell else None,
        "empirical_counts": cell,
        "shrink_weight_n_over_n_plus_25": round(n_cell / (n_cell + SHRINK_N), 3),
        "registered_band_empirical_claim": 0.81,
        "note": ("under THIS lab's conventions (resolved pool, consensus-FV grade "
                 "bands, age at decision cutoff) the fv45/25+ cell is n=8 with "
                 "empirical p_bust 0.750, and mean realized WAR6 RISES with age "
                 "inside the fv45 band (0.51 le22 / 1.70 23-24 / 2.51 25+): the "
                 "registered 0.81 band-empirical figure is not reproduced here"),
    }

    prod_cells_out = {f"{gb}|{ab}": {"n": int(sum(c)), "counts": [int(x) for x in c],
                                     "weight": round(sum(c) / (sum(c) + SHRINK_N), 4)}
                      for (gb, ab), c in sorted(prod_cells.items())}

    results = {
        "generated_at": date.today().isoformat(),
        "experiment": "BUCKET-AGE-HEAD: pit-only covariate bucket head p(bucket | grade_band, "
                      "age_band) below the grade-monotone constraint (grade-monotone "
                      "calibration line is CLOSED: X-ISO/E-ISO2/3/4 all rejected)",
        "seed": SEED,
        "bootstrap_reps": N_BOOT,
        "design": {
            "head": "p(bucket | grade_band, age_band), pit only; age bands <=22 / 23-24 / 25+ "
                    "(le22: age<23; 23_24: 23<=age<25; 25p: age>=25); grade bands = the existing "
                    "5-point FV tiers (round(fv/5)*5, efv_isotonic_lab._tier); cell empirical "
                    "partially pooled toward the incumbent p_bucket_given_fv row at the ACTUAL "
                    "grade with weight n/(n+25); missing age or missing cell -> incumbent exactly",
            "population": "resolved labeled pitcher matrix (data/xfv_pitcher_matrix.json): "
                          "is_pitcher, debuted+busts, bust_recent excluded, censored==False, "
                          "consensus_fv_raw + target_resolved present (n=1569, all weight 1.0); "
                          "mirrors efv_model.oos_grades pool restricted to resolved labels",
            "conditioning_grade": "consensus_fv_raw (the pre-outcome list grade), mirroring the "
                                  "incumbent table's own population convention (published-FV rows); "
                                  "served on xfv_grade exactly as the incumbent already is",
            "age_at": "decision cutoff (birth_date exact; fallback milb.age advanced by "
                      "cutoff-vs-season staleness; None -> incumbent fallback)",
            "realized_bucket": "6yr-avg annual WAR (target_resolved/6) binned <0.5/1.5/2.5/4.0 "
                               "(engine bands, efv_isotonic_lab convention)",
            "folds": "forward-chained decision-year folds 2020-2023, head fit strictly on "
                     "decision_year < Y; incumbent is the fixed production curve",
            "metrics": "log-loss clip 1e-6; per-bucket = binary cross-entropy "
                       "(efv_isotonic_lab.logloss_per_bucket); unweighted means (all rows w=1)",
            "incumbent_method": (vf._fitted().get("method") or {}).get("pitcher"),
        },
        "pool": {
            "n": len(pool),
            "kinds": dict(Counter(r["kind"] for r in pool)),
            "age_known": sum(1 for r in pool if r["age_band"] is not None),
            "age_bands": dict(Counter(r["age_band"] or "missing" for r in pool)),
            "grade_bands": {str(k): v for k, v in
                            sorted(Counter(r["grade_band"] for r in pool).items())},
        },
        "folds": fold_diag,
        "results": {
            "pooled": pooled,
            "age_25p_subset": sub25,
            "age_known_subset": sub_age_known,
            "per_fold": per_fold,
            "per_age_band": per_band,
        },
        "bootstrap": boot,
        "gate": {
            "g1_pooled_logloss_le_incumbent": {
                "pass": bool(g1_pass),
                "head": pooled["log_loss"]["head"],
                "incumbent": pooled["log_loss"]["incumbent"],
                "delta": pooled["log_loss"]["delta"],
            },
            "g2_eiso4_guard_bench_good_le_1pct_rel": {
                "pass": g2_pass,
                "bench": {"pass": bool(g2_bench_ok), **bench},
                "good": {"pass": bool(g2_good_ok), **good},
                "tolerance_rel": MATERIAL_TOL,
            },
            "g3_age25p_subset_improves": {
                "pass": bool(g3_pass),
                "n": sub25["n"],
                "head": sub25["log_loss"]["head"],
                "incumbent": sub25["log_loss"]["incumbent"],
                "delta": sub25["log_loss"]["delta"],
            },
            "g4_validity_and_grade_monotone": {"pass": g4_pass, **g4},
            "verdict": verdict,
        },
        "moore": moore,
        "production_head_cells": prod_cells_out,
        "rerun_marker": {
            "pattern": "F-SIDE S5 tripwire",
            "trigger": "the FIRST pipeline run where the 2024 decision fold becomes trainable "
                       "in the DEBUTED frame (debuted rows with decision_year==2024 carrying "
                       "resolved censored==False labels; the full-pool 2024 cell is bust-only "
                       "today and does NOT count)",
            "action": "MANDATORY named re-run of BUCKET-AGE-HEAD (this lab, identical "
                      "pre-registered gates) before the head may ship or any baseline resets; "
                      "the Moore-class RP-role cohort resolves only then (improvement-program "
                      "2026-07-15: role blindness not gateable until 2024+ cohorts resolve)",
            "registered": date.today().isoformat(),
        },
    }
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")

    print(f"\nVERDICT: {verdict}")
    print(f" G1 pooled LL   : {'PASS' if g1_pass else 'FAIL'}  inc {pooled['log_loss']['incumbent']} -> head {pooled['log_loss']['head']} (delta {pooled['log_loss']['delta']})")
    print(f" G2 bench/good  : {'PASS' if g2_pass else 'FAIL'}  bench rel {bench['rel_delta']} | good rel {good['rel_delta']}")
    print(f" G3 25+ subset  : {'PASS' if g3_pass else 'FAIL'}  n={sub25['n']} inc {sub25['log_loss']['incumbent']} -> head {sub25['log_loss']['head']}")
    print(f" G4 valid+mono  : {'PASS' if g4_pass else 'FAIL'}  valid={g4['valid_distributions']} mono={g4['monotone_sane']} worst={g4['max_violation']}")
    print(f" Moore: head p_bust @(45.8, 26.9) = {moore['xfv_grade_live_45.8']['head_p_bust']} "
          f"(incumbent {moore['xfv_grade_live_45.8']['incumbent_p_bust']}; registered published 0.388; "
          f"claimed band-empirical 0.81; this-lab cell empirical "
          f"{moore['cell_fv45_25p']['empirical_p_bust']})")
    return results


if __name__ == "__main__":
    main()
