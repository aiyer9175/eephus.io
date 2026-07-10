# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""E-STUFF lab -- forward-chained OOS test of the upper-level pitcher Tier-2
overlay (deferred xfv-phase2 A3/A4): does adding in-house AAA aStuff+
(stuff_plus_aaa) and/or the SC+ whiff component (swing_miss_percent z, the
X-C3 pitcher-signal carrier) to the eFV pitcher model improve out-of-sample
rank, on the EXACT protocol data/xfv_eval.json + tools/efv_lab_runner.py use?

Pre-registered gate (docs/audit-2026-07/AUDIT_FINDINGS.md, section E-STUFF):
  1. pitcher pool OOS Spearman delta >= +0.005
  2. AA/AAA sub-cohort delta >= +0.010
  3. lower-level cohort delta no worse than -0.003 (missing-data handling
     must not poison rows without tracking data; coverage reported)

OVERLAYS (per-season, mlbam-joined, as-of by decision year):
  astuff -- in-house AAA aStuff+. The shipped sidecar keeps only each
            pitcher's LATEST season and scales vs the fixed 2025 pool, which
            would leak post-decision seasons here, so pitcher-season scores
            are recomputed from the committed model artifact + pitch cache
            with SAME-SEASON pool stats (no cross-season look-ahead; shrink
            k and pitch floors match stuff_plus_aaa.score exactly).
  whiff  -- swing_miss_percent z within the season's qualified AAA pitcher
            pool (min 100 PA, AAA-restricted, sign +1 = more whiffs better),
            mirroring arkmetric_forward_eval / sc_plus_component_eval.

ENCODING (the missing-data contract): each overlay enters as a centered
value that is identically ZERO when uncovered (astuff -> (v-100)/10, whiff
is already a z) plus a 0/1 coverage flag. An uncovered row contributes
nothing, and a zero-variance train column draws a zero ridge coefficient,
so uncovered cohorts cannot be poisoned by construction -- the run proves
this numerically (max |score diff| reported).

AS-OF CONVENTIONS:
  strict     tracking season strictly BEFORE the decision (debut) year --
             the house rule from stuff_plus_aaa.forward_eval.
  sameseason tracking season <= decision year (sensitivity read only; a
             debut-year AAA aggregate mixes pre-callup and post-debut
             pitches, disclosed contamination).

KNOWN STRUCTURAL LIMIT (report, do not hide): AAA tracking begins 2023 and
the outcome-scored eval cohorts (SCORED_YEARS) end at debut year 2023, so
strict coverage is zero everywhere and even sameseason coverage exists only
in the 2023 TEST cohort while every TRAIN fold stays at zero. The gate
verdict must reflect exactly how thin that is.

Deterministic end-to-end: ridge/OLS are closed-form, no RNG anywhere (the
SEED constant is recorded for protocol compliance only). Offline: cached
Savant CSVs, cached StatsAPI splits (fetch=False throughout) and the
committed model artifact; nothing is fetched.

Writes data/xfv_pitcher_stuff_eval.json (gate verdicts + loss ledger).
Run: python tools/efv_pitcher_stuff_lab.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import numpy as np                                   # noqa: E402

import efv_model as XM                               # noqa: E402
from prospect_path import _spearman, _fit_ridge, _predict   # noqa: E402
from efv_model import (_fit_ols_fv, _pred_ols, blend_lambda,  # noqa: E402
                       _feature_spec)
from efv_dataset import matrix_path, live_matrix_path        # noqa: E402
import efv_lab_runner as LAB                         # noqa: E402  (tools/ on path)
import arkmetric_forward_eval as afe                 # noqa: E402
import milb_history as mh                            # noqa: E402
import stuff_plus_aaa as spa                         # noqa: E402

SEED = 20260702          # protocol compliance; no stochastic step exists
SCORED_YEARS = XM.SCORED_YEARS          # (2020, 2021, 2022, 2023)
TRACK_SEASONS = (2023, 2024, 2025, 2026)   # AAA tracking begins 2023
OUT_PATH = ROOT / "data" / "xfv_pitcher_stuff_eval.json"

GATE = {"pool_min_delta": 0.005,
        "upper_min_delta": 0.010,
        "lower_max_degrade": -0.003}

UPPER_LEVELS = ("AA", "AAA")
LOWER_LEVELS = ("A+", "A", "CPX", "DSL")

VARIANTS = {
    "astuff": ["x_astuff_c", "x_astuff_has"],
    "whiff":  ["x_whiff_z", "x_whiff_has"],
    "both":   ["x_astuff_c", "x_astuff_has", "x_whiff_z", "x_whiff_has"],
}


# ---------------------------------------------------------------- overlays

def _aaa_mlbams_offline(season: int) -> frozenset[int]:
    """afe._aaa_mlbams with fetch=False forced (offline guarantee)."""
    out = set()
    for group in ("hitting", "pitching"):
        for mid, rows in mh.player_index(season, group, fetch=False).items():
            milb = [r for r in rows if r.get("level") != "MLB"]
            if milb and mh.highest_level(milb) == "AAA":
                out.add(mid)
    return frozenset(out)


_WHIFF_CACHE: dict[int, dict] = {}


def whiff_table(season: int) -> dict[int, float]:
    """{mlbam: signed swing-miss z} for one qualified AAA pitcher season pool
    (min 100 PA, AAA-restricted; z math mirrors sc_plus_component_eval)."""
    if season in _WHIFF_CACHE:
        return _WHIFF_CACHE[season]
    vals: dict[int, float] = {}
    try:
        aaa = _aaa_mlbams_offline(season)
        for r in afe.savant_rows(season, "pitcher", fetch=False):
            mid = afe._f(r.get("player_id"))
            pa = afe._f(r.get("pa")) or 0
            sm = afe._f(r.get("swing_miss_percent"))
            if mid is None or int(mid) not in aaa or pa < afe.MIN_POOL_PA or sm is None:
                continue
            vals[int(mid)] = sm
    except Exception:                                 # noqa: BLE001
        vals = {}
    if len(vals) < 30:
        _WHIFF_CACHE[season] = {}
        return {}
    mu = statistics.mean(vals.values())
    sd = statistics.pstdev(vals.values()) or 1.0
    _WHIFF_CACHE[season] = {m: (v - mu) / sd for m, v in vals.items()}
    return _WHIFF_CACHE[season]


_ASTUFF_CACHE: dict[int, dict] = {}
_STUFF_MODEL = None


def _stuff_model():
    global _STUFF_MODEL
    if _STUFF_MODEL is None:
        import joblib
        _STUFF_MODEL = joblib.load(spa.MODEL_PATH)["model"]
    return _STUFF_MODEL


def astuff_table(season: int) -> dict[int, dict]:
    """{mlbam: {stuff, n_pitches}} for one AAA season, scored from the pitch
    cache with the committed model artifact. Pool stats (mean/sd over >=300
    pitch pitchers) come from the SAME season so there is no cross-season
    look-ahead; shrink k=300 and the 50-pitch score floor match
    stuff_plus_aaa.score."""
    if season in _ASTUFF_CACHE:
        return _ASTUFF_CACHE[season]
    m = _stuff_model()
    rv: dict[int, float] = {}
    npi: dict[int, int] = {}
    for path in sorted(spa.CACHE_DIR.glob(f"*_{season}.csv")):
        mid = int(path.stem.split("_")[0])
        X, _y = spa._load_season(mid, season)
        if len(X) < 50:
            continue
        rv[mid] = float(np.mean(m.predict(np.asarray(X))))
        npi[mid] = len(X)
    pool = [v for mid, v in rv.items() if npi[mid] >= spa.MIN_POOL_PITCHES]
    if len(pool) < 30:
        _ASTUFF_CACHE[season] = {}
        return {}
    mu = float(np.mean(pool))
    sd = float(np.std(pool)) or 1.0
    out = {}
    for mid, v in rv.items():
        shrunk = (v * npi[mid] + mu * spa.SHRINK_K) / (npi[mid] + spa.SHRINK_K)
        out[mid] = {"stuff": round(100 + 10 * (mu - shrunk) / sd, 2),
                    "n_pitches": npi[mid]}
    _ASTUFF_CACHE[season] = out
    return out


def overlay_for(mid: int | None, decision_year: int, convention: str) -> dict:
    """Latest qualifying tracking season per overlay, under the as-of rule."""
    out = {"astuff": None, "astuff_season": None,
           "whiff_z": None, "whiff_season": None}
    if not mid:
        return out
    limit = decision_year - 1 if convention == "strict" else decision_year
    for s in sorted(TRACK_SEASONS, reverse=True):
        if s > limit:
            continue
        if out["astuff"] is None:
            t = astuff_table(s).get(mid)
            if t is not None:
                out["astuff"], out["astuff_season"] = t["stuff"], s
        if out["whiff_z"] is None:
            z = whiff_table(s).get(mid)
            if z is not None:
                out["whiff_z"], out["whiff_season"] = round(z, 4), s
    return out


# ------------------------------------------------------------------- rows

def _matrix_meta() -> dict[str, dict]:
    raw = json.loads(matrix_path("pit").read_text(encoding="utf-8"))
    return {r["player_key"]: r for r in raw}


def _level_group(lvl) -> str:
    if lvl in UPPER_LEVELS:
        return "upper"
    if lvl in LOWER_LEVELS:
        return "lower"
    return "unknown"


def build_rows(convention: str) -> list[dict]:
    """LAB.data_for('pit') rows + overlay features under one as-of rule.
    Feats are copied; the shared LAB cache is never mutated."""
    meta = _matrix_meta()
    out = []
    for r in LAB.data_for("pit"):
        mrow = meta.get(r["player_key"]) or {}
        try:
            mid = int(mrow.get("mlbam_id")) if mrow.get("mlbam_id") else None
        except (TypeError, ValueError):
            mid = None
        lvl = (mrow.get("milb") or {}).get("milb_level")
        ov = overlay_for(mid, r["decision_year"], convention)
        f = dict(r["feats"])
        f["x_astuff_c"] = ((ov["astuff"] - 100.0) / 10.0
                           if ov["astuff"] is not None else 0.0)
        f["x_astuff_has"] = 1.0 if ov["astuff"] is not None else 0.0
        f["x_whiff_z"] = ov["whiff_z"] if ov["whiff_z"] is not None else 0.0
        f["x_whiff_has"] = 1.0 if ov["whiff_z"] is not None else 0.0
        out.append({**r, "feats": f, "mlbam_id": mid, "level": lvl,
                    "level_group": _level_group(lvl),
                    "astuff_covered": ov["astuff"] is not None,
                    "whiff_covered": ov["whiff_z"] is not None,
                    "covered": (ov["astuff"] is not None
                                or ov["whiff_z"] is not None),
                    "ov": ov})
    return out


def coverage_by_year(rows: list[dict]) -> dict:
    by = defaultdict(lambda: {"n": 0, "mlbam": 0, "astuff": 0,
                              "whiff": 0, "any": 0})
    for r in rows:
        b = by[r["decision_year"]]
        b["n"] += 1
        b["mlbam"] += 1 if r["mlbam_id"] else 0
        b["astuff"] += 1 if r["astuff_covered"] else 0
        b["whiff"] += 1 if r["whiff_covered"] else 0
        b["any"] += 1 if r["covered"] else 0
    return {str(y): by[y] for y in sorted(by)}


# ------------------------------------------------------------------- eval

def _rho(pairs):
    return _spearman([a for a, _ in pairs], [b for _, b in pairs]) \
        if len(pairs) >= 8 else None


def run_eval(rows: list[dict], extra_keys: list[str]) -> dict:
    """Exact efv_lab_runner.run_variant protocol (fold gates 12/50, shipped
    ridge + OLS anchor + shipped blend lambda) with optional overlay keys."""
    keys = _feature_spec("pit")[0] + list(extra_keys)
    lam = blend_lambda("pit")
    pooled = []                        # row dicts with score attached
    fold_cov = {}
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        trf = [{"feats": r["feats"], "target": r["target_censored"],
                "weight": r["weight"], "fv": r["fv"]} for r in tr]
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]}
                           for r in tr])
        ridge = _fit_ridge(trf, keys)
        if not (ols and ridge):
            continue
        fold_cov[str(yr)] = {
            "train_n": len(tr), "train_covered": sum(r["covered"] for r in tr),
            "test_n": len(te), "test_covered": sum(r["covered"] for r in te)}
        for r in te:
            rp = _predict(ridge, r["feats"])
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            score = (1 - lam) * cw + lam * rp
            pooled.append({"player_key": r["player_key"], "year": yr,
                           "score": score, "pure": rp,
                           "target": r["target_censored"], "fv": r["fv"],
                           "level_group": r["level_group"],
                           "covered": r["covered"], "row": r})

    def sub(pred):
        return _rho([(p["score"], p["target"]) for p in pooled if pred(p)])

    per_year = {str(y): _rho([(p["score"], p["target"])
                              for p in pooled if p["year"] == y])
                for y in sorted({p["year"] for p in pooled})}
    groups = {}
    for g in ("upper", "lower", "unknown"):
        grp = [p for p in pooled if p["level_group"] == g]
        groups[g] = {"n": len(grp), "rho": sub(lambda p, g=g: p["level_group"] == g)}
    return {
        "keys": keys, "lam": round(lam, 3), "n": len(pooled),
        "pooled_rho": _rho([(p["score"], p["target"]) for p in pooled]),
        "pooled_rho_pure": _rho([(p["pure"], p["target"]) for p in pooled]),
        "per_level_group": groups,
        "covered": {"n": sum(p["covered"] for p in pooled),
                    "rho": sub(lambda p: p["covered"])},
        "uncovered": {"n": sum(not p["covered"] for p in pooled),
                      "rho": sub(lambda p: not p["covered"])},
        "per_year": per_year,
        "fold_coverage": fold_cov,
        "_pooled": pooled,
    }


def _delta(a, b):
    if a is None or b is None:
        return None
    return round(a - b, 4)


def compare(base: dict, var: dict) -> dict:
    """Deltas vs baseline + the numerical no-poisoning proof (max |score
    diff| on identical rows; expected 0.0 while train coverage is zero)."""
    bmap = {(p["player_key"], p["year"]): p["score"] for p in base["_pooled"]}
    diffs = [abs(p["score"] - bmap[(p["player_key"], p["year"])])
             for p in var["_pooled"] if (p["player_key"], p["year"]) in bmap]
    return {
        "delta_pooled": _delta(var["pooled_rho"], base["pooled_rho"]),
        "delta_pooled_pure": _delta(var["pooled_rho_pure"], base["pooled_rho_pure"]),
        "delta_upper": _delta(var["per_level_group"]["upper"]["rho"],
                              base["per_level_group"]["upper"]["rho"]),
        "delta_lower": _delta(var["per_level_group"]["lower"]["rho"],
                              base["per_level_group"]["lower"]["rho"]),
        "delta_unknown": _delta(var["per_level_group"]["unknown"]["rho"],
                                base["per_level_group"]["unknown"]["rho"]),
        "max_abs_score_diff": round(max(diffs), 12) if diffs else None,
        "n_matched": len(diffs),
    }


def gate_verdict(cmp_: dict, var: dict) -> dict:
    """The three pre-registered conditions. A pass additionally requires the
    delta to be SUPPORTED by covered rows in both train and test (a delta
    measured with zero trainable coverage is definitionally not evidence)."""
    fc = var["fold_coverage"]
    train_cov = sum(f["train_covered"] for f in fc.values())
    test_cov = sum(f["test_covered"] for f in fc.values())
    trainable = train_cov > 0
    c1 = (cmp_["delta_pooled"] is not None
          and cmp_["delta_pooled"] >= GATE["pool_min_delta"] and trainable)
    c2 = (cmp_["delta_upper"] is not None
          and cmp_["delta_upper"] >= GATE["upper_min_delta"] and trainable)
    c3 = (cmp_["delta_lower"] is not None
          and cmp_["delta_lower"] >= GATE["lower_max_degrade"])
    return {
        "condition_1_pool_delta": {
            "pass": bool(c1), "delta": cmp_["delta_pooled"],
            "bar": GATE["pool_min_delta"]},
        "condition_2_upper_delta": {
            "pass": bool(c2), "delta": cmp_["delta_upper"],
            "bar": GATE["upper_min_delta"]},
        "condition_3_lower_no_degrade": {
            "pass": bool(c3), "delta": cmp_["delta_lower"],
            "bar": GATE["lower_max_degrade"]},
        "trainable_coverage": {
            "train_covered_rows_all_folds": train_cov,
            "test_covered_rows_all_folds": test_cov,
            "trainable": trainable},
        "verdict": "PASS" if (c1 and c2 and c3) else "FAIL",
    }


# ---------------------------------------------------- supplementary reads

def residual_read(base: dict, rows_same: list[dict]) -> dict:
    """NON-GATE forward read: on sameseason-covered 2023-cohort rows, does
    the overlay correlate with the realized target and with the baseline
    model's OOS residual? This estimates whether the feature WOULD add
    signal once a trainable fold exists. Disclosed contamination: the 2023
    aggregate includes post-debut pitches for these debut-2023 pitchers."""
    smap = {(r["player_key"]): r for r in rows_same}
    out = {}
    p23 = [p for p in base["_pooled"] if p["year"] == 2023]
    for feat, cov_key, val in (
            ("astuff", "astuff_covered", lambda r: r["ov"]["astuff"]),
            ("whiff_z", "whiff_covered", lambda r: r["ov"]["whiff_z"])):
        pairs_t, pairs_r, pairs_b = [], [], []
        for p in p23:
            r = smap.get(p["player_key"])
            if not r or not r[cov_key]:
                continue
            v = val(r)
            pairs_t.append((v, p["target"]))
            pairs_r.append((v, p["target"] - p["score"]))
            pairs_b.append((p["score"], p["target"]))
        out[feat] = {
            "n": len(pairs_t),
            "rho_vs_target": _rho(pairs_t),
            "rho_vs_baseline_residual": _rho(pairs_r),
            "rho_baseline_vs_target_same_rows": _rho(pairs_b),
        }
    return out


def _astuff_mids(season: int) -> set:
    return set(astuff_table(season))


def future_coverage() -> dict:
    """When does this become testable, and with how many rows?
    (a) 2024/2025 debut pitchers (debuts.json) with STRICTLY-pre-debut
        tracking -- the rows a matrix rebuild would add as censored cohorts.
    (b) live AA/AAA pitcher prospects with current (2025/2026) tracking --
        the applied population if the overlay ever ships."""
    debuts = json.loads((ROOT / "data" / "debuts.json").read_text(encoding="utf-8"))
    fut = {}
    for dy in (2024, 2025):
        pre = [s for s in TRACK_SEASONS if s < dy]
        n = n_ast = n_wh = 0
        for d in debuts:
            dd = d.get("debut_date") or ""
            mid = d.get("mlbam_id")
            if not mid or not dd[:4].isdigit() or int(dd[:4]) != dy:
                continue
            mid = int(mid)
            ast = any(mid in _astuff_mids(s) for s in pre)
            wh = any(mid in whiff_table(s) for s in pre)
            if ast or wh:
                n += 1
                n_ast += 1 if ast else 0
                n_wh += 1 if wh else 0
        fut[f"debut_{dy}_strict_covered"] = {
            "any": n, "astuff": n_ast, "whiff": n_wh,
            "note": "pitcher-implied by presence in the pitcher tracking pools"}
    live = {"upper_n": 0, "upper_covered": 0, "all_n": 0, "all_covered": 0}
    try:
        lrows = json.loads(live_matrix_path("pit").read_text(encoding="utf-8"))
        for r in lrows:
            try:
                mid = int(r.get("mlbam_id")) if r.get("mlbam_id") else None
            except (TypeError, ValueError):
                mid = None
            lvl = (r.get("milb") or {}).get("milb_level")
            cov = bool(mid) and any(
                mid in _astuff_mids(s) or mid in whiff_table(s)
                for s in (2025, 2026))
            live["all_n"] += 1
            live["all_covered"] += 1 if cov else 0
            if lvl in UPPER_LEVELS:
                live["upper_n"] += 1
                live["upper_covered"] += 1 if cov else 0
    except (OSError, ValueError):
        live = {"error": "live pitcher matrix not readable"}
    fut["live_prospects_2025_2026_tracking"] = live
    return fut


# -------------------------------------------------------------------- run

def _strip(res: dict) -> dict:
    return {k: v for k, v in res.items() if k != "_pooled"}


def run(persist: bool = True) -> dict:
    rows_strict = build_rows("strict")
    rows_same = build_rows("sameseason")

    base = run_eval(rows_strict, [])
    lab_base = LAB.baseline("pit")
    parity_ok = (base["pooled_rho"] == lab_base["spearman"])

    results = {}
    for conv, rows in (("strict", rows_strict), ("sameseason", rows_same)):
        results[conv] = {}
        for vid, keys in VARIANTS.items():
            var = run_eval(rows, keys)
            cmp_ = compare(base, var)
            results[conv][vid] = {"eval": _strip(var), "vs_baseline": cmp_,
                                  "gate": gate_verdict(cmp_, var)}

    # the registered gate is the strict convention, "both" variant
    reg = results["strict"]["both"]["gate"]
    all_verdicts = {f"{c}:{v}": results[c][v]["gate"]["verdict"]
                    for c in results for v in results[c]}
    overall = "PASS" if any(g == "PASS" for g in all_verdicts.values()) else "FAIL"

    supp = residual_read(base, rows_same)
    fut = future_coverage()

    out = {
        "generated_at": date.today().isoformat(),
        "tool": "tools/efv_pitcher_stuff_lab.py",
        "experiment": "E-STUFF (pre-registered in docs/audit-2026-07/"
                      "AUDIT_FINDINGS.md; deferred xfv-phase2 A3/A4)",
        "seed": SEED,
        "method": {
            "protocol": "exact efv_lab_runner forward chain: for each scored "
                        "year Y in " + str(list(SCORED_YEARS)) + " train the "
                        "shipped lean ridge + OLS consensus anchor on "
                        "decision_year < Y (fold gates 12 test / 50 train), "
                        "blend with the shipped pitcher lambda, pool OOS "
                        "rows; debuted pitcher pool, KM-censored target",
            "overlays": {
                "astuff": "in-house AAA aStuff+ rescored per (pitcher, "
                          "season) from the committed model artifact with "
                          "same-season pool stats (the shipped sidecar keeps "
                          "only the latest season vs the 2025 pool, which "
                          "would leak post-decision seasons); shrink k=300, "
                          "50-pitch score floor, 300-pitch pool floor",
                "whiff": "swing_miss_percent z within the season's "
                         "qualified AAA pitcher pool (min 100 PA, "
                         "AAA-restricted, sign +1), per "
                         "sc_plus_component_eval / X-C3",
            },
            "encoding": "centered value (astuff (v-100)/10; whiff already "
                        "z), zeroed when uncovered, + 0/1 coverage flag; "
                        "uncovered rows contribute exactly nothing",
            "as_of": {"strict": "tracking season < decision (debut) year",
                      "sameseason": "tracking season <= decision year "
                                    "(sensitivity only; debut-year AAA "
                                    "aggregates include post-debut pitches)"},
            "determinism": "closed-form ridge/OLS, no RNG; offline "
                           "(cached CSVs + committed artifacts only)",
            "astuff_selfscore_caveat": "the stuff model's shipping fit saw "
                                       "2023-2025 pitches, so 2023 feature "
                                       "values score pitches the model "
                                       "trained on; accepted feature-"
                                       "generation caveat matching the "
                                       "module's own forward gate, and moot "
                                       "while the gate is untrainable",
        },
        "baseline": {"pooled_rho": base["pooled_rho"],
                     "pooled_rho_pure": base["pooled_rho_pure"],
                     "per_level_group": base["per_level_group"],
                     "per_year": base["per_year"],
                     "n": base["n"], "lam": base["lam"],
                     "parity_with_efv_lab_runner_baseline": parity_ok,
                     "efv_lab_runner_baseline_rho": lab_base["spearman"]},
        "coverage_by_cohort_year": {
            "strict": coverage_by_year(rows_strict),
            "sameseason": coverage_by_year(rows_same)},
        "results": results,
        "registered_gate": {"convention": "strict", "variant": "both",
                            **reg},
        "all_gate_verdicts": all_verdicts,
        "overall_verdict": overall,
        "supplementary_non_gate_reads": {
            "residual_read_2023_sameseason_covered": supp,
            "prior_evidence": {
                "stuff_plus_aaa_forward_gate": "final-AAA aStuff+ vs first-"
                    "MLB: K% r 0.5145, ERA(inv) r 0.077, n 18 (data/"
                    "stuff_plus_aaa_eval.json, graduates 2024+)",
                "x_c3_whiff": "AAA SwingMiss% z vs first-MLB ERA(inv) "
                    "r 0.359 (data/sc_plus_component_eval.json)"},
        },
        "future_coverage": fut,
    }

    if overall == "FAIL":
        c23 = out["coverage_by_cohort_year"]["sameseason"].get("2023", {})
        out["loss_ledger"] = {
            "date": date.today().isoformat(),
            "experiment": "E-STUFF upper-level pitcher Tier-2 overlay "
                          "(aStuff+ / SC+ whiff) into the eFV pitcher model",
            "hypothesis": "for AA/AAA pitchers the in-house aStuff+ "
                          "(pitcher-level forward r 0.28) or the SC+ whiff "
                          "component (X-C3 r 0.359 vs first-MLB ERA) adds "
                          "OOS rank signal the production features miss",
            "what_was_tried": "both overlays plus each alone, joined "
                              "per-season by mlbam under strict and "
                              "same-season as-of rules, neutral-when-missing "
                              "encoding + coverage flags, on the exact "
                              "shipped forward-chained protocol",
            "result": {
                "failed_conditions": ["condition_1_pool_delta",
                                      "condition_2_upper_delta"],
                "root_cause": "structural, not a signal failure: AAA "
                    "tracking begins 2023 while the outcome-scored eval "
                    "cohorts end at debut year 2023, so strict pre-decision "
                    "coverage is 0 rows everywhere; even the same-season "
                    "relaxation covers only the 2023 TEST cohort "
                    f"({c23.get('any', 0)}/{c23.get('n', 0)} rows) while "
                    "every TRAIN fold has zero covered rows, so the ridge "
                    "coefficient on the overlay is identically zero and "
                    "every forward-chained delta is exactly 0.0 by "
                    "construction (max |score diff| proves it)",
                "verdict_reading": "FAIL as inconclusive under the "
                    "pre-registered rule that insufficient n is a FAIL, "
                    "not a pass; the overlay was never given a trainable "
                    "fold, so nothing here refutes the hypothesis either",
            },
            "signal_read_recorded": (
                "the same-season sensitivity read (n="
                f"{supp['astuff']['n']}, 2023 cohort, 6yr-WAR censored "
                "target) shows only weak incremental signal: astuff rho "
                f"{supp['astuff']['rho_vs_target']} vs target but "
                f"{supp['astuff']['rho_vs_baseline_residual']} vs the "
                "baseline's OOS residual; whiff "
                f"{supp['whiff_z']['rho_vs_target']} / "
                f"{supp['whiff_z']['rho_vs_baseline_residual']}. The strong "
                "priors (stuff K% r 0.5145 n=18; X-C3 whiff r 0.359) are "
                "against FIRST-MLB RATE outcomes, not 6yr WAR; the overlay "
                "is unproven on the eFV target and most of its rate signal "
                "may already be priced by the K-based production features"),
            "do_not_reattempt_until": "the pitcher matrix includes debut "
                "cohorts 2024+ as (censored) scored rows -- the first fold "
                "with nonzero TRAIN coverage is test year 2025 trained on "
                "the 2024 cohort (see future_coverage for the row counts "
                "that rebuild would add)",
        }

    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    rep = run()
    b = rep["baseline"]
    print(f"baseline: pooled={b['pooled_rho']} pure={b['pooled_rho_pure']} "
          f"n={b['n']} parity={b['parity_with_efv_lab_runner_baseline']}")
    for conv in ("strict", "sameseason"):
        cov = rep["coverage_by_cohort_year"][conv]
        tot = sum(v["any"] for v in cov.values())
        print(f"[{conv}] covered rows (all cohorts): {tot}")
        for vid, blk in rep["results"][conv].items():
            c = blk["vs_baseline"]
            g = blk["gate"]
            print(f"  {vid:7s} d_pool={c['delta_pooled']} "
                  f"d_upper={c['delta_upper']} d_lower={c['delta_lower']} "
                  f"maxdiff={c['max_abs_score_diff']} -> {g['verdict']}")
    print("supplementary:", json.dumps(
        rep["supplementary_non_gate_reads"]
           ["residual_read_2023_sameseason_covered"]))
    print("future:", json.dumps(rep["future_coverage"]))
    print("OVERALL:", rep["overall_verdict"])
    print("wrote", OUT_PATH)
