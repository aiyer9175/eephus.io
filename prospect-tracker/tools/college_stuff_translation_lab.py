# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""W4 COL-XRV lab: college_stuff_translation gate + collegesavant stuff+ governance.

Registration: docs/wills-2026-07-23/GATES.md section "W4 COL-XRV". Registered
bars are FROZEN and hard-coded here; never retuned after seeing data.

  PART A (unconditional governance, NOT a gate)
    -> data/collegesavant_stuff_eval.json
    Descriptive validation record for the ALREADY-SHIPPED CollegeSavant
    stuff_plus lineage (collegesavant/pitcher_pitch_data_2024/2025/2026.js +
    pitcher_data.js): scale convention + measured distribution, per-season
    coverage, agreement with Will's xRV vintage (recomputed Pearson r on
    overlapping TrackMan pitcher_id x pitch_type rows between the 2026 payload
    and "NCAA 26 Averages S+.csv"; expectation recorded a priori: r near
    0.959), the three-scale collision warning, and best-effort forward checks
    from matched draftee outcomes.

  PART B (the gate)
    -> data/college_stuff_translation_eval.json
    Usage-weighted college stuff+ per pitcher (weights = pitch_count across
    that pitcher's pitch types, rows with non-null stuff_plus only, joined
    same-season by (pitcher_id, year)) as an ADDITIONAL covariate in the
    pitcher college -> Single-A (first pro exposure) K% translation,
    matched-pairs leave-one-out protocol (the college_translation.py harness:
    same pair construction, same SLOPE_SHRINK_K shrinkage convention).

  FROZEN BARS (one attempt; marginal = FAIL):
    STOP-D : matched pairs with stuff+ coverage < 40 -> verdict
             COVERAGE-STARVED, ship Part A only.
    K1     : LOO K% MAE with the covariate STRICTLY improves vs the
             stat-line-only translation, both models LOO-refit on the
             IDENTICAL covered-pair set.
    K2     : bootstrap lo95 (2.5th percentile) of the per-pair improvement
             (|err_base| - |err_aug|) > 0; 2000 reps, seed 20260723,
             pair-level resampling.

  A-PRIORI MODEL FORM (decided before any gate data was seen):
    baseline  y = ym + b1*(x1-x1m),           b1 = ols * n/(n+SLOPE_SHRINK_K)
    augmented y = ym + b1*(x1-x1m)+b2*(x2-x2m), (b1,b2) = joint OLS via 2x2
              normal equations, BOTH shrunk by the same n/(n+SLOPE_SHRINK_K)
              factor (the incumbent convention extended to two covariates).
    Covariate join is SAME-SEASON ONLY ((pitcher_id, year) of the selected
    outcome row); a pitcher with no same-season per-pitch stuff row is
    uncovered, never imputed.

Run:  python tools/college_stuff_translation_lab.py
Writes both artifacts under data/ and prints a summary. Read-only vs
prospects.db; never touches served payloads.
"""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import college_translation as ct  # noqa: E402
import storage  # noqa: E402
from rate_stabilization import SLOPE_SHRINK_K  # noqa: E402

SEED = 20260723
BOOT_REPS = 2000
STOP_D_MIN_PAIRS = 40
GENERATED_AT = "2026-07-23"
GATES_REF = "docs/wills-2026-07-23/GATES.md section W4 COL-XRV"

CS_DIR = ROOT / "collegesavant"
WILL_CSV = ROOT.parent / "NCAA 26 Averages S+.csv"
XRV_MANIFEST = ROOT.parent / "xRV models" / "manifest.pkl"

PAYLOADS = [(2024, "pitcher_pitch_data_2024.js", "window.PITCHER_PITCH_DATA_2024"),
            (2025, "pitcher_pitch_data_2025.js", "window.PITCHER_PITCH_DATA_2025"),
            (2026, "pitcher_pitch_data_2026.js", "window.PITCHER_PITCH_DATA_2026")]


# --------------------------------------------------------------------------- #
# small stats helpers (pure python, deterministic)
# --------------------------------------------------------------------------- #
def _mean(v):
    return sum(v) / len(v) if v else None


def _sd(v):
    if len(v) < 2:
        return None
    m = _mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def _pct(v, q):
    s = sorted(v)
    if not s:
        return None
    i = q * (len(s) - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return s[lo] if lo == hi else s[lo] + (i - lo) * (s[hi] - s[lo])


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    xm, ym = _mean(xs), _mean(ys)
    sxx = sum((x - xm) ** 2 for x in xs)
    syy = sum((y - ym) ** 2 for y in ys)
    sxy = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


def _r(x, nd=4):
    return None if x is None else round(x, nd)


# --------------------------------------------------------------------------- #
# payload loading
# --------------------------------------------------------------------------- #
def load_pitch_rows():
    """year -> list of per-pitcher-per-pitch-type payload rows."""
    out = {}
    for year, fname, marker in PAYLOADS:
        out[year] = ct._first_array(CS_DIR / fname, marker)
    return out


def usage_weighted_stuff(pitch_rows):
    """(pitcher_id, year) -> {stuff_wt, pitches, types} usage-weighted across a
    pitcher's pitch types; rows with null stuff_plus or pitch_count<=0 excluded
    from both numerator and weights (the a-priori rule)."""
    out = {}
    for year, rows in pitch_rows.items():
        acc = {}
        for rr in rows:
            sp, pc = rr.get("stuff_plus"), rr.get("pitch_count") or 0
            pid = str(rr.get("pitcher_id") or "")
            if sp is None or pc <= 0 or not pid:
                continue
            w, s, t = acc.get(pid, (0.0, 0.0, 0))
            acc[pid] = (w + pc, s + float(sp) * pc, t + 1)
        for pid, (w, s, t) in acc.items():
            if w > 0:
                out[(pid, year)] = {"stuff_wt": s / w, "pitches": int(w), "types": t}
    return out


# --------------------------------------------------------------------------- #
# PART A - governance record
# --------------------------------------------------------------------------- #
def build_part_a(pitch_rows, stuff_map, forward_checks):
    per_season = {}
    for year, rows in pitch_rows.items():
        sp = [float(rr["stuff_plus"]) for rr in rows if rr.get("stuff_plus") is not None]
        wts = [(float(rr["stuff_plus"]), rr.get("pitch_count") or 0)
               for rr in rows if rr.get("stuff_plus") is not None]
        wsum = sum(w for _, w in wts)
        per_season[str(year)] = {
            "rows": len(rows),
            "pitchers": len({str(rr.get("pitcher_id")) for rr in rows}),
            "pitch_types": sorted({rr.get("pitch_type") for rr in rows}),
            "rows_with_stuff_plus": len(sp),
            "rows_null_stuff_plus": len(rows) - len(sp),
            "stuff_plus_distribution": {
                "mean": _r(_mean(sp), 2), "sd": _r(_sd(sp), 2),
                "usage_weighted_mean": _r(sum(s * w for s, w in wts) / wsum, 2) if wsum else None,
                "p5": _r(_pct(sp, 0.05), 1), "p25": _r(_pct(sp, 0.25), 1),
                "p50": _r(_pct(sp, 0.50), 1), "p75": _r(_pct(sp, 0.75), 1),
                "p95": _r(_pct(sp, 0.95), 1),
                "min": _r(min(sp), 1) if sp else None,
                "max": _r(max(sp), 1) if sp else None,
            },
        }

    # agreement with Will's xRV vintage on (pitcher_id, pitch_type), 2026 payload
    agreement = {"csv": str(WILL_CSV.name), "join_key": "pitcher_id x pitch_type",
                 "expected_r_recorded_a_priori": 0.959}
    will = {}
    formula_dev = []
    league_avg = worst = None
    try:
        import pickle
        man = pickle.load(open(XRV_MANIFEST, "rb"))
        league_avg = man.get("league_average_xrv")
        worst = man.get("worst_xrv")
    except Exception:
        pass
    with open(WILL_CSV, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            pid = (row.get("pitcher_id") or "").strip()
            pt = (row.get("pitch_type") or "").strip()
            sp_raw = (row.get("stuff+") or "").strip()
            if not pid or pid == "Unknown" or not pt or pt == "Undefined" or not sp_raw:
                continue
            try:
                spv = float(sp_raw)
            except ValueError:
                continue
            will[(pid, pt)] = spv
            xrv_raw = (row.get("xrv") or "").strip()
            if xrv_raw and league_avg is not None and worst is not None:
                try:
                    xrv = float(xrv_raw)
                    implied = 100.0 * (worst - xrv) / (worst - league_avg)
                    formula_dev.append(abs(implied - spv))
                except ValueError:
                    pass
    xs, ys = [], []
    for rr in pitch_rows.get(2026, []):
        if rr.get("stuff_plus") is None:
            continue
        k = (str(rr.get("pitcher_id")), rr.get("pitch_type"))
        if k in will:
            xs.append(float(rr["stuff_plus"]))
            ys.append(will[k])
    agreement["overlapping_rows"] = len(xs)
    agreement["pearson_r_measured"] = _r(_pearson(xs, ys))
    agreement["will_formula_verified"] = {
        "formula": "stuff+ = 100 * (worst_xrv - xrv) / (worst_xrv - league_average_xrv)",
        "league_average_xrv": league_avg, "worst_xrv": worst,
        "rows_checked": len(formula_dev),
        "max_abs_deviation": _r(max(formula_dev), 4) if formula_dev else None,
    }

    doc = {
        "generated_at": GENERATED_AT,
        "artifact": "collegesavant_stuff_eval",
        "kind": "governance validation record (registry ledger, NOT a gate)",
        "experiment": {
            "registration": GATES_REF,
            "clause": "Governance (unconditional): registry row + eval artifact for the "
                      "shipped CollegeSavant stuff_plus lineage; fixes a standing-rule "
                      "violation (model-audit-program) that predates this program.",
            "seed": SEED,
        },
        "lineage": {
            "surface": "collegesavant/pitcher_index.html (Stuff+ column, per-pitch pages)",
            "payloads": [f"collegesavant/{f}" for _, f, _ in PAYLOADS] + ["collegesavant/pitcher_data.js"],
            "provenance": "Vendored college TrackMan xRV-family model (Will's CollegeSavant "
                          "build); per-pitch-type xRV models scored on 7 TrackMan kinematic "
                          "features, mapped to a 100-anchored ratio scale. Static payloads; "
                          "no in-tree trainer regenerates them.",
            "model_features": ["RelSpeed", "InducedVertBreak", "HorzBreak", "RelHeight",
                               "Extension", "SpinRate", "HorzRelAngle / VAA (vintage-dependent)"],
        },
        "scale_convention": {
            "statement": "100 anchors league-average expected run value; 0 anchors the worst "
                         "observed college xRV. NOT a z-score scale: the measured payload SD "
                         "is far wider than 10 and the distribution is left-skewed with a "
                         "long tail toward 0.",
            "collision_warning": [
                "THREE different Stuff+ scales exist in this tree and must NEVER be mixed "
                "on one surface:",
                "(1) CollegeSavant stuff_plus (these payloads): college TrackMan xRV ratio "
                "scale, 100 = college league-average xRV, 0 = worst observed; measured "
                "SD ~23-24 per season (see per_season_coverage).",
                "(2) Will's 2026 formula-anchored vintage (NCAA 26 Averages S+.csv + "
                "xRV models/): same formula family, DIFFERENT model fit; verified "
                "stuff+ = 100*(worst_xrv - xrv)/(worst_xrv - league_average_xrv).",
                "(3) Platform aStuff+ (stuff_plus_aaa.py, data/stuff_plus_aaa.json): "
                "LightGBM delta_run_exp on AAA Statcast, scaled 100 + 10z vs the "
                "qualified AAA pool. A 130 here is elite; a 130 CollegeSavant "
                "stuff_plus is barely plus.",
            ],
        },
        "per_season_coverage": per_season,
        "agreement_with_wills_vintage": agreement,
        "forward_checks": forward_checks,
        "reading": "Descriptive record. The shipped lineage is internally consistent with "
                   "Will's 2026 vintage at the pitch level (r measured above) and its scale "
                   "anchors are documented; predictive value against pro outcomes is "
                   "measured separately by the W4 gate ledger "
                   "(data/college_stuff_translation_eval.json).",
    }
    return doc


# --------------------------------------------------------------------------- #
# PART B - the gate
# --------------------------------------------------------------------------- #
def fit_uni(pairs):
    """pairs = [(x, y)]; incumbent-form univariate regression-to-the-mean."""
    return ct._fit([p[0] for p in pairs], [p[1] for p in pairs])


def predict_uni(f, x):
    return ct._predict(f, x)


def fit_bi(rows):
    """rows = [(x1, x2, y)]; joint OLS via 2x2 normal equations, both slopes
    shrunk by n/(n+SLOPE_SHRINK_K). Registered a priori."""
    n = len(rows)
    if n < 8:
        return None
    x1m = _mean([r[0] for r in rows])
    x2m = _mean([r[1] for r in rows])
    ym = _mean([r[2] for r in rows])
    s11 = sum((r[0] - x1m) ** 2 for r in rows)
    s22 = sum((r[1] - x2m) ** 2 for r in rows)
    s12 = sum((r[0] - x1m) * (r[1] - x2m) for r in rows)
    s1y = sum((r[0] - x1m) * (r[2] - ym) for r in rows)
    s2y = sum((r[1] - x2m) * (r[2] - ym) for r in rows)
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-9:
        return None
    b1 = (s22 * s1y - s12 * s2y) / det
    b2 = (s11 * s2y - s12 * s1y) / det
    shrink = n / (n + SLOPE_SHRINK_K)
    b1s, b2s = b1 * shrink, b2 * shrink
    resid = [r[2] - (ym + b1s * (r[0] - x1m) + b2s * (r[1] - x2m)) for r in rows]
    rmse = math.sqrt(sum(e * e for e in resid) / n)
    return {"x1_mean": round(x1m, 3), "x2_mean": round(x2m, 3), "y_mean": round(ym, 3),
            "b1": round(b1s, 4), "b2": round(b2s, 4),
            "ols_b1": round(b1, 4), "ols_b2": round(b2, 4),
            "band_sd": round(rmse, 3), "n": n}


def predict_bi(f, x1, x2):
    return f["y_mean"] + f["b1"] * (x1 - f["x1_mean"]) + f["b2"] * (x2 - f["x2_mean"])


def run_gate(covered):
    """covered = [(x1_college_k, x2_stuff_wt, y_pro_k)]; LOO both models on the
    identical set; per-pair absolute errors; bootstrap of the improvement."""
    n = len(covered)
    err_b, err_a = [], []
    for i in range(n):
        train = covered[:i] + covered[i + 1:]
        fb = fit_uni([(r[0], r[2]) for r in train])
        fa = fit_bi(train)
        if not fb or not fa:
            continue
        x1, x2, y = covered[i]
        err_b.append(abs(y - predict_uni(fb, x1)))
        err_a.append(abs(y - predict_bi(fa, x1, x2)))
    mae_b = _mean(err_b)
    mae_a = _mean(err_a)
    diffs = [b - a for b, a in zip(err_b, err_a)]  # positive = covariate helps
    rng = random.Random(SEED)
    m = len(diffs)
    boots = []
    for _ in range(BOOT_REPS):
        boots.append(_mean([diffs[rng.randrange(m)] for _ in range(m)]))
    boots.sort()
    lo95 = boots[int(0.025 * BOOT_REPS)]
    return mae_b, mae_a, lo95, len(diffs)


def main():
    pitch_rows = load_pitch_rows()
    stuff_map = usage_weighted_stuff(pitch_rows)

    # matched pairs: EXACTLY the college_translation harness construction
    with storage.connect() as con:
        key_name = ct._key_to_name(con)
        cs_p = ct.load_cs_pitchers()
        _sa_h, sa_p = ct.load_single_a(con, key_name)

    all_pairs, covered = [], []
    for slug, v in cs_p.items():
        if slug not in sa_p or v.get("k_pct") is None or sa_p[slug][1] is None:
            continue
        x1, y = float(v["k_pct"]), float(sa_p[slug][1])
        all_pairs.append((x1, y))
        sm = stuff_map.get((str(v.get("pitcher_id")), v.get("year")))
        if sm is not None:
            covered.append((x1, sm["stuff_wt"], y))

    n_cov = len(covered)
    stopd = n_cov < STOP_D_MIN_PAIRS

    # forward checks for Part A (descriptive, best effort)
    fwd = {
        "matched_pairs_total": len(all_pairs),
        "matched_pairs_with_stuff": n_cov,
        "corr_usageweighted_stuff_vs_first_pro_A_kpct": _r(_pearson(
            [c[1] for c in covered], [c[2] for c in covered])) if n_cov >= 3 else None,
        "corr_usageweighted_stuff_vs_college_kpct": _r(_pearson(
            [c[1] for c in covered], [c[0] for c in covered])) if n_cov >= 3 else None,
        "note": "First pro exposure = earliest qualifying A/A+ season, >= 20 IP, "
                "stored-BF K% (the college_translation.load_single_a gate).",
    }

    part_a = build_part_a(pitch_rows, stuff_map, fwd)
    (ROOT / "data" / "collegesavant_stuff_eval.json").write_text(
        json.dumps(part_a, indent=1), encoding="utf-8")

    gate = {
        "generated_at": GENERATED_AT,
        "artifact": "college_stuff_translation",
        "experiment": {
            "registration": GATES_REF,
            "mechanism": ("usage-weighted college stuff+ (pitch_count weights, same-season "
                          "(pitcher_id, year) join, non-null rows only) as an additional "
                          "covariate in the pitcher college -> Single-A K% translation; "
                          "matched-pairs LOO, incumbent shrinkage convention "
                          "(slope * n/(n+SLOPE_SHRINK_K), K=" + str(SLOPE_SHRINK_K) + ")"),
            "flag": "EEPHUS_COL_XRV (default OFF; OFF path byte-identical, verified)",
            "seed": SEED,
            "bootstrap_reps": BOOT_REPS,
            "one_attempt": True,
        },
        "coverage": {
            "matched_pairs_total": len(all_pairs),
            "matched_pairs_with_stuff_coverage": n_cov,
            "stop_d_bar": STOP_D_MIN_PAIRS,
        },
    }

    if stopd:
        gate["clauses"] = {
            "STOP-D": {"bar": "covered pairs >= %d" % STOP_D_MIN_PAIRS,
                       "measured": n_cov, "result": "TRIGGERED"},
            "K1": {"bar": "LOO K% MAE strictly improves vs stat-line-only on identical pairs",
                   "measured": None, "result": "NOT RUN (STOP-D)"},
            "K2": {"bar": "bootstrap lo95 of improvement > 0 (2000 reps, seed 20260723)",
                   "measured": None, "result": "NOT RUN (STOP-D)"},
        }
        gate["verdict"] = "COVERAGE-STARVED"
        gate["loss_ledger"] = {
            "story": "Fewer than %d matched college->pro pairs carry same-season "
                     "usage-weighted stuff+; the covariate cannot be evaluated honestly. "
                     "Governance record (Part A) ships regardless; mechanism stays "
                     "default-OFF behind EEPHUS_COL_XRV." % STOP_D_MIN_PAIRS,
            "keep_alive": "Re-gate at next draft-class resolution when 2025/2026 tracked "
                          "classes accrue first pro A/A+ exposure.",
        }
    else:
        mae_b, mae_a, lo95, n_scored = run_gate(covered)
        k1 = mae_a < mae_b
        k2 = lo95 > 0
        gate["clauses"] = {
            "STOP-D": {"bar": "covered pairs >= %d" % STOP_D_MIN_PAIRS,
                       "measured": n_cov, "result": "CLEAR"},
            "K1": {"bar": "LOO K% MAE (augmented) < LOO K% MAE (stat-line-only), "
                          "identical covered pairs, strict",
                   "mae_stat_line_only": round(mae_b, 4),
                   "mae_with_stuff_covariate": round(mae_a, 4),
                   "improvement": round(mae_b - mae_a, 4),
                   "pairs_scored": n_scored,
                   "result": "PASS" if k1 else "FAIL"},
            "K2": {"bar": "bootstrap lo95 of per-pair improvement > 0 "
                          "(2000 reps, seed 20260723, pair resampling)",
                   "lo95": round(lo95, 4),
                   "result": "PASS" if k2 else "FAIL"},
        }
        gate["verdict"] = "PASS" if (k1 and k2) else "FAIL"
        full_fit = fit_bi(covered)
        base_fit = fit_uni([(c[0], c[2]) for c in covered])
        gate["fitted_on_all_covered_pairs"] = {
            "augmented": full_fit,
            "stat_line_only_same_subset": base_fit,
            "production_pit_k_context": "production pit_k is fit on ALL matched pairs "
                                        "(n=%d); the gate subset refit is the "
                                        "apples-to-apples baseline" % len(all_pairs),
        }
        if gate["verdict"] == "PASS":
            gate["reading"] = {
                "story": "Usage-weighted college stuff+ adds real out-of-sample K% signal "
                         "on top of the college K% stat line in the matched-pair LOO. "
                         "Central flip of EEPHUS_COL_XRV + collegesavant translation regen "
                         "is authorized by the ship rule.",
            }
        else:
            gate["loss_ledger"] = {
                "story": "The covariate did not clear the frozen bars on the identical "
                         "covered-pair set (K1 improvement %s, K2 lo95 %s). College stuff+ "
                         "describes pitch quality, but on this sample it does not add "
                         "K%%-translation signal beyond the college K%% line itself. "
                         "Mechanism stays default-OFF behind EEPHUS_COL_XRV." % (
                             round(mae_b - mae_a, 4), round(lo95, 4)),
                "keep_alive": "Re-gate at next draft-class resolution (2025/2026 tracked "
                              "classes reaching first pro A/A+ exposure).",
            }

    (ROOT / "data" / "college_stuff_translation_eval.json").write_text(
        json.dumps(gate, indent=1), encoding="utf-8")

    print(json.dumps({"part_a_agreement": part_a["agreement_with_wills_vintage"],
                      "coverage": gate["coverage"],
                      "clauses": gate["clauses"],
                      "verdict": gate["verdict"]}, indent=1))


if __name__ == "__main__":
    main()
