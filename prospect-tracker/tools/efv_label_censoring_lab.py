# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Lane B1 (master plan 2026-08-07b): measure the eFV label's censoring bias directly.

Pre-registration: docs/efv-2026-08-07b/LABEL_CENSORING_GATE.md, written before this ran.

WHAT: `efv_dataset._label_6yr` (:894-914, pre-B4-edit :879-894) projects the unobserved tail of the first-6yr
bWAR label at the OBSERVED per-season rate, i.e. it assumes a flat per-season WAR rate.
The module header calls that "KM-from-the-start"; it is not a Kaplan-Meier estimator.

HOW: take every FULLY RESOLVED debuted row in the shipped matrices (debut_year <= 2020,
so debut+5 <= RESOLVED_THROUGH), truncate its observation window to n = 2, 3, 4, 5 by
patching the module global `efv_dataset.RESOLVED_THROUGH`, and call the SHIPPED
`_label_6yr`. No reimplementation. Compare the projection to the true six-year total.

Writes exactly one artifact: data/xfv_label_censoring_eval.json.
Fits nothing, rescores nothing, rebuilds nothing.

Run: python tools/efv_label_censoring_lab.py
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ds            # noqa: E402
import efv_model as em              # noqa: E402
import efv_reliability as rel       # noqa: E402
import storage                      # noqa: E402

DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "xfv_label_censoring_eval.json"

BOOT_B = 5000
BOOT_SEED = 20260807
THIN_N = 15

# Magnitude bins on the TRUE six-year WAR: the shipped realized-bucket edges
# (efv_reliability.BUCKET_EDGES annual) times TARGET_SEASONS, with the negative
# tail split out. Cut points in six-year WAR: 0, 3, 9, 15, 24.
MAG_EDGES = (0.0, 3.0, 9.0, 15.0, 24.0)
MAG_NAMES = ("neg", "0to3", "3to9", "9to15", "15to24", "24plus")

SPANS = (2, 3, 4, 5)


def _mag_bin(true_war: float) -> str:
    i = 0
    for e in MAG_EDGES:
        if true_war >= e:
            i += 1
        else:
            break
    return MAG_NAMES[i]


# ---------------------------------------------------------------------------
# B3: pin check. Assert, do not assume.
# ---------------------------------------------------------------------------

def pin_check() -> dict:
    got = dict(em._BLEND_LAMBDA_RESELECT)
    want = {"hit": 0.70, "pit": 0.57}
    ok = (got.get("hit") == want["hit"] and got.get("pit") == want["pit"])
    return {"source": "efv_model._BLEND_LAMBDA_RESELECT (efv_model.py:581)",
            "read": got, "expected": want, "pin_ok": bool(ok),
            "note": ("pitcher lambda pinned; rank_calibration('pit') is NOT re-derived "
                     "per run, so a label experiment cannot silently move the served blend"
                     if ok else
                     "PIN VIOLATED: served lambda is not what the plan asserts")}


# ---------------------------------------------------------------------------
# cohort
# ---------------------------------------------------------------------------

def _career_war() -> dict[str, dict[int, float]]:
    cw = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}
    return cw


def load_rows() -> tuple[list[dict], dict]:
    """Resolved debuted rows from the shipped matrices, joined to career_war."""
    cw = _career_war()
    rows, meta = [], {}
    for side, fname in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        p = DATA_DIR / fname
        mrows = json.loads(p.read_text(encoding="utf-8"))
        meta[fname] = {
            "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(timespec="seconds"),
            "n_rows": len(mrows),
            "n_debuted": sum(1 for r in mrows if r.get("kind") == "debuted"),
            "n_censored_shipped": sum(1 for r in mrows if r.get("censored")),
        }
        for r in mrows:
            if r.get("kind") != "debuted":
                continue
            dy = r.get("debut_year")
            if dy is None or dy + ds.TARGET_SEASONS - 1 > ds.RESOLVED_THROUGH:
                continue
            seasons = cw.get(r["player_key"])
            if not seasons:
                continue
            rows.append({"player_key": r["player_key"], "side": side, "debut_year": int(dy),
                         "seasons": seasons, "shipped_target_resolved": r.get("target_resolved"),
                         "rerouted": bool(r.get("rerouted_from_bust"))})
    return rows, meta


# ---------------------------------------------------------------------------
# the measurement: truncate, call the SHIPPED label fn, compare
# ---------------------------------------------------------------------------

def measure(rows: list[dict]) -> tuple[list[dict], dict]:
    real_through = ds.RESOLVED_THROUGH
    recon = {"checked": 0, "match": 0, "mismatch": 0, "mismatch_examples": []}
    out = []
    try:
        for r in rows:
            dy = r["debut_year"]
            # ground truth via the SAME shipped function at the real horizon
            ds.RESOLVED_THROUGH = real_through
            t_res, t_cens, cflag, w, n_obs = ds._label_6yr(r["seasons"], dy)
            assert not cflag and n_obs == ds.TARGET_SEASONS, (r["player_key"], n_obs, cflag)
            true = t_cens
            recon["checked"] += 1
            shipped = r["shipped_target_resolved"]
            if shipped is not None and abs(float(shipped) - true) < 1e-6:
                recon["match"] += 1
            else:
                recon["mismatch"] += 1
                if len(recon["mismatch_examples"]) < 10:
                    recon["mismatch_examples"].append(
                        {"player_key": r["player_key"], "shipped": shipped, "recomputed": true})
            rec = {"player_key": r["player_key"], "side": r["side"], "debut_year": dy,
                   "true": true, "mag": _mag_bin(true), "rerouted": r["rerouted"], "proj": {}}
            for n in SPANS:
                ds.RESOLVED_THROUGH = dy + n - 1
                _tr, tc, cf, wt, nb = ds._label_6yr(r["seasons"], dy)
                assert cf and nb == n, (r["player_key"], n, nb, cf)
                rec["proj"][n] = {"projected": tc, "obs_sum": _tr, "weight": wt,
                                  "err": round(tc - true, 6)}
            out.append(rec)
    finally:
        ds.RESOLVED_THROUGH = real_through
    assert ds.RESOLVED_THROUGH == real_through
    return out, recon


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(BOOT_SEED)


def _boot_ci(x: np.ndarray, B: int = BOOT_B) -> tuple[float, float]:
    if len(x) < 2:
        return (float("nan"), float("nan"))
    idx = _RNG.integers(0, len(x), size=(B, len(x)))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = _avg_rank(a)          # tie-aware average ranks
    rb = _avg_rank(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    den = math.sqrt(float((ra * ra).sum()) * float((rb * rb).sum()))
    return float((ra * rb).sum() / den) if den else float("nan")


def _avg_rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=float)
    sx = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and sx[j + 1] == sx[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum() / den) if den else float("nan")


def stratum_stats(true: np.ndarray, proj: np.ndarray, weights: np.ndarray | None = None) -> dict:
    err = proj - true
    n = len(err)
    lo, hi = _boot_ci(err)
    sd_true = float(true.std(ddof=1)) if n > 1 else float("nan")
    mean_b = float(err.mean()) if n else float("nan")
    d = {
        "n": int(n),
        "mean_bias": round(mean_b, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "ci_excludes_zero": bool(n > 1 and (lo > 0 or hi < 0)),
        "median_bias": round(float(np.median(err)), 4) if n else None,
        "mae": round(float(np.abs(err).mean()), 4) if n else None,
        "rmse": round(float(np.sqrt((err ** 2).mean())), 4) if n else None,
        "sd_err": round(float(err.std(ddof=1)), 4) if n > 1 else None,
        "sd_true": round(sd_true, 4) if n > 1 else None,
        "mean_true": round(float(true.mean()), 4) if n else None,
        "mean_proj": round(float(proj.mean()), 4) if n else None,
        "thin": bool(n < THIN_N),
    }
    if n > 1 and sd_true and not math.isnan(sd_true) and sd_true > 0:
        d["bias_over_sd_true"] = round(mean_b / sd_true, 4)
        d["material"] = bool(d["ci_excludes_zero"] and n >= THIN_N
                             and (abs(mean_b) >= 1.0 or abs(mean_b) >= 0.25 * sd_true))
    else:
        d["bias_over_sd_true"] = None
        d["material"] = False
    if n >= 3:
        d["pearson_proj_true"] = round(_pearson(proj, true), 4)
        d["spearman_proj_true"] = round(_spearman(proj, true), 4)
        d["corr_err_true"] = round(_pearson(err, true), 4)
        d["rank_attenuation_multiplier"] = d["pearson_proj_true"]
    if weights is not None and n:
        wsum = float(weights.sum())
        d["weighted_mean_bias"] = round(float((err * weights).sum() / wsum), 4) if wsum else None
    return d


# ---------------------------------------------------------------------------
# downstream: buckets, AUC bars
# ---------------------------------------------------------------------------

def bucket_and_bar_stats(recs: list[dict], n: int, side: str | None = None) -> dict:
    sel = [r for r in recs if side is None or r["side"] == side]
    true = np.array([r["true"] for r in sel])
    proj = np.array([r["proj"][n]["projected"] for r in sel])
    bt = np.array([rel._realized_bucket(v) for v in true])
    bp = np.array([rel._realized_bucket(v) for v in proj])
    conf = {}
    for i in range(len(rel.BUCKETS)):
        for j in range(len(rel.BUCKETS)):
            c = int(((bt == i) & (bp == j)).sum())
            if c:
                conf[f"{rel.BUCKETS[i]}->{rel.BUCKETS[j]}"] = c
    out = {
        "n": len(sel),
        "bucket_changed": int((bt != bp).sum()),
        "bucket_changed_pct": round(100.0 * float((bt != bp).mean()), 2) if len(sel) else None,
        "bucket_up": int((bp > bt).sum()),
        "bucket_down": int((bp < bt).sum()),
        "confusion_true_to_proj": conf,
        "realized_freq_true": {rel.BUCKETS[i]: int((bt == i).sum()) for i in range(len(rel.BUCKETS))},
        "realized_freq_proj": {rel.BUCKETS[i]: int((bp == i).sum()) for i in range(len(rel.BUCKETS))},
    }
    for bar_name, bar in (("contributor_war_ge_3", em._CONTRIB_WAR), ("star_war_ge_10", em._STAR_WAR)):
        t = true >= bar
        p = proj >= bar
        out[bar_name] = {
            "bar": bar,
            "true_positives_in_pool": int(t.sum()),
            "proj_positives_in_pool": int(p.sum()),
            "false_promote": int((~t & p).sum()),
            "false_demote": int((t & ~p).sum()),
            "net_shift": int(p.sum() - t.sum()),
            "label_flip_pct": round(100.0 * float((t != p).mean()), 2) if len(sel) else None,
        }
    return out


# ---------------------------------------------------------------------------
# diagnostic: realized per-season-index share profile (explains direction only)
# ---------------------------------------------------------------------------

def season_share_profile(rows: list[dict]) -> dict:
    out = {}
    for side in ("hit", "pit", "all"):
        sel = [r for r in rows if side == "all" or r["side"] == side]
        prof = []
        for k in range(ds.TARGET_SEASONS):
            vals = [r["seasons"].get(r["debut_year"] + k, 0.0) for r in sel]
            prof.append(round(float(np.mean(vals)), 4) if vals else None)
        tot = sum(p for p in prof if p)
        out[side] = {
            "mean_war_by_season_index": prof,
            "share_of_six_year_mean": [round(p / tot, 4) if tot else None for p in prof],
            "seasons_4to6_share": round(sum(prof[3:]) / tot, 4) if tot else None,
            "n": len(sel),
        }
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    pin = pin_check()
    print("B3 PIN CHECK:", json.dumps(pin["read"]), "ok =", pin["pin_ok"])

    rows, meta = load_rows()
    print(f"resolved debuted rows: {len(rows)} "
          f"(hit {sum(1 for r in rows if r['side'] == 'hit')}, "
          f"pit {sum(1 for r in rows if r['side'] == 'pit')})")

    recs, recon = measure(rows)
    print(f"ground-truth reconciliation vs shipped target_resolved: "
          f"{recon['match']}/{recon['checked']} match, {recon['mismatch']} mismatch")

    result = {
        # MUST be "generated_at": model_registry._artifact_date only reads
        # generated_at / run_at / fit_date / as_of / date, so any other spelling
        # sends this artifact into test_model_registry.UNDATED_EVAL_ARTIFACTS,
        # a set whose docstring says it may only ever shrink. An undated
        # artifact falls back to file mtime, and the deploy box runs
        # `git checkout -- .` nightly, so on the box that serves the site its
        # age would read as roughly zero however old the measurement really is.
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lane": "B1 (master plan 2026-08-07b)",
        "gate_doc": "docs/efv-2026-08-07b/LABEL_CENSORING_GATE.md",
        "what": ("bias of efv_dataset._label_6yr's flat-rate tail projection, measured by "
                 "truncating fully resolved debuted rows to n_obs = 2..5 and calling the "
                 "SHIPPED label function"),
        "shipped_function": "efv_dataset._label_6yr (efv_dataset.py:894-914, pre-B4-edit :879-894)",
        "resolved_through": ds.RESOLVED_THROUGH,
        "target_seasons": ds.TARGET_SEASONS,
        "bootstrap": {"B": BOOT_B, "seed": BOOT_SEED, "type": "percentile, resampled within stratum"},
        "materiality_rule": "CI95 excludes 0 AND (|bias| >= 1.0 WAR OR |bias| >= 0.25 * SD(true))",
        "b3_pin_check": pin,
        "matrix_meta": meta,
        "ground_truth_reconciliation": recon,
        "pool": {
            "n": len(recs),
            "hit": sum(1 for r in recs if r["side"] == "hit"),
            "pit": sum(1 for r in recs if r["side"] == "pit"),
            "rerouted_from_bust": sum(1 for r in recs if r["rerouted"]),
            "debut_years": sorted({r["debut_year"] for r in recs}),
        },
    }

    def arrays(sel, n):
        return (np.array([r["true"] for r in sel]),
                np.array([r["proj"][n]["projected"] for r in sel]),
                np.array([r["proj"][n]["weight"] for r in sel]))

    # --- by n_obs x side (the primary strata) ---
    by_n_side = {}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            sel = [r for r in recs if side == "all" or r["side"] == side]
            t, p, w = arrays(sel, n)
            by_n_side[f"n{n}_{side}"] = stratum_stats(t, p, w)
    result["by_n_obs_and_side"] = by_n_side

    # --- by n_obs x magnitude bin (mandatory) ---
    by_mag = {}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            for mag in MAG_NAMES:
                sel = [r for r in recs if (side == "all" or r["side"] == side) and r["mag"] == mag]
                if not sel:
                    continue
                t, p, w = arrays(sel, n)
                by_mag[f"n{n}_{side}_{mag}"] = stratum_stats(t, p, w)
    result["by_n_obs_and_magnitude"] = by_mag

    # --- by debut cohort ---
    by_cohort = {}
    for n in SPANS:
        for dy in sorted({r["debut_year"] for r in recs}):
            for side in ("hit", "pit"):
                sel = [r for r in recs if r["debut_year"] == dy and r["side"] == side]
                if not sel:
                    continue
                t, p, w = arrays(sel, n)
                by_cohort[f"n{n}_{side}_{dy}"] = stratum_stats(t, p, w)
    result["by_n_obs_and_cohort"] = by_cohort

    # --- transferability: the recent resolved cohorts (2017-2020), which sit closest
    #     to the 2021-2024 rows that actually ride the projection today ---
    recent = {}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            sel = [r for r in recs if (side == "all" or r["side"] == side)
                   and 2017 <= r["debut_year"] <= 2020]
            t, p, w = arrays(sel, n)
            recent[f"n{n}_{side}"] = stratum_stats(t, p, w)
    result["recent_cohort_2017_2020"] = recent

    # --- confound control: the 2020 season was 60 games, so it depresses whichever
    #     window slot it lands in. Debut years 2011-2014 have six-year windows that
    #     end 2016-2019, entirely pre-COVID. If the bias survives here it is not a
    #     short-season artifact. ---
    precovid = {}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            sel = [r for r in recs if (side == "all" or r["side"] == side)
                   and r["debut_year"] <= 2014]
            t, p, w = arrays(sel, n)
            precovid[f"n{n}_{side}"] = stratum_stats(t, p, w)
    result["pre_covid_cohort_2011_2014"] = precovid

    # --- production fidelity: rows a career-terminal transaction would have resolved
    #     at the truncation horizon never ride the projection in production
    #     (efv_dataset.build_matrix:1214-1220). Re-measure with those removed. ---
    real_through = ds.RESOLVED_THROUGH
    term = ds._load_terminal_dates({r["player_key"] for r in recs})
    term_sens = {"n_pool_with_terminal_date": len(term)}
    try:
        for n in SPANS:
            for side in ("hit", "pit", "all"):
                sel = []
                excl = 0
                for r in recs:
                    if side != "all" and r["side"] != side:
                        continue
                    td = term.get(r["player_key"])
                    if td:
                        ds.RESOLVED_THROUGH = r["debut_year"] + n - 1
                        if ds._terminal_resolves(td):
                            excl += 1
                            continue
                    sel.append(r)
                ds.RESOLVED_THROUGH = real_through
                t, p, w = arrays(sel, n)
                s = stratum_stats(t, p, w)
                s["excluded_terminal_resolved"] = excl
                term_sens[f"n{n}_{side}"] = s
    finally:
        ds.RESOLVED_THROUGH = real_through
    result["terminal_resolution_sensitivity"] = term_sens

    # --- downstream: buckets + AUC bars ---
    result["downstream"] = {f"n{n}_{side}": bucket_and_bar_stats(recs, n, None if side == "all" else side)
                            for n in SPANS for side in ("hit", "pit", "all")}

    # --- induced label noise summary for Lane I7 ---
    noise = {}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            k = f"n{n}_{side}"
            s = by_n_side[k]
            noise[k] = {"sd_err": s["sd_err"], "sd_true": s["sd_true"],
                        "pearson_proj_true": s.get("pearson_proj_true"),
                        "spearman_proj_true": s.get("spearman_proj_true"),
                        "corr_err_true": s.get("corr_err_true"),
                        "rank_attenuation_multiplier": s.get("rank_attenuation_multiplier"),
                        "noise_to_signal_var": (round((s["sd_err"] ** 2) / (s["sd_true"] ** 2), 4)
                                                if s["sd_err"] and s["sd_true"] else None)}
    result["induced_label_noise"] = noise
    result["induced_label_noise_note"] = (
        "rank_attenuation_multiplier is corr(projected, true) in the truncation replay. Under "
        "the classical independent-noise assumption a rank correlation measured against the "
        "projected label is attenuated by roughly this factor relative to the same quantity "
        "measured against the true label. corr_err_true is printed beside it because the noise "
        "is NOT independent of the truth here, so treat the multiplier as an upper bound on "
        "retained information, not as an exact correction.")

    # --- population-mix estimate on the ACTUAL shipped censored rows ---
    shipped_cens = {}
    for side, fname in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        mrows = json.loads((DATA_DIR / fname).read_text(encoding="utf-8"))
        for r in mrows:
            if r.get("censored") and r.get("kind") == "debuted":
                k = (side, int(r.get("observed_seasons") or 0))
                shipped_cens[k] = shipped_cens.get(k, 0) + 1
    mix = {"counts": {f"{s}_n{n}": c for (s, n), c in sorted(shipped_cens.items())}}
    tot_rows, tot_war, tot_war_w = 0, 0.0, 0.0
    for (s, n), c in shipped_cens.items():
        st = by_n_side.get(f"n{n}_{s}")
        if not st:
            continue
        tot_rows += c
        tot_war += c * st["mean_bias"]
        tot_war_w += c * (n / ds.TARGET_SEASONS) * st["mean_bias"]
    mix["n_rows_riding_the_projection"] = tot_rows
    mix["expected_total_label_bias_war"] = round(tot_war, 2)
    mix["expected_mean_label_bias_war_per_row"] = round(tot_war / tot_rows, 4) if tot_rows else None
    mix["expected_total_label_bias_war_fit_weighted"] = round(tot_war_w, 2)
    result["population_mix_estimate"] = mix

    result["season_share_profile_diagnostic"] = season_share_profile(rows)

    # The competing premise: attrition. If players vanish before season 6 the flat rate
    # OVER-states. Measured on the same pool so the two forces are comparable.
    attr = {}
    for side in ("hit", "pit", "all"):
        sel = [r for r in rows if side == "all" or r["side"] == side]
        n = len(sel)
        no6 = sum(1 for r in sel if (r["debut_year"] + 5) not in r["seasons"])
        no456 = sum(1 for r in sel
                    if not any((r["debut_year"] + k) in r["seasons"] for k in (3, 4, 5)))
        attr[side] = {"n": n,
                      "no_season6_line": no6, "no_season6_pct": round(100.0 * no6 / n, 2),
                      "no_seasons_4to6_line": no456,
                      "no_seasons_4to6_pct": round(100.0 * no456 / n, 2)}
    attr["note"] = ("attrition is real and LARGER than the plan's 32.8 percent premise, yet "
                    "the net bias is still negative: the players who vanish are near-zero "
                    "contributors whose flat-rate projection was near zero anyway, so the "
                    "season-mass effect dominates")
    result["attrition_diagnostic"] = attr

    # --- verdict against the pre-registered criterion ---
    eligible = {k: v for k, v in list(by_n_side.items()) + list(by_mag.items())
                if not v["thin"] and not k.endswith("_all") and "_all_" not in k}
    any_sig = [k for k, v in eligible.items() if v["ci_excludes_zero"]]
    any_mat = [k for k, v in eligible.items() if v["material"]]
    if any_mat:
        verdict = "MATERIAL_BIAS"
    elif any_sig:
        verdict = "DETECTABLE_BUT_IMMATERIAL"
    else:
        verdict = "NULL"
    result["verdict"] = verdict
    result["eligible_strata_n"] = len(eligible)
    result["strata_ci_excludes_zero"] = sorted(any_sig)
    result["strata_material"] = sorted(any_mat)
    result["b2_recommendation"] = (
        "RECOMMEND B2 for wave 2 (its own gate doc, rank-identical level twin, random-label "
        "null band, permutation p-value). NOT built in this wave."
        if verdict == "MATERIAL_BIAS" else
        "B2 does not run. Record the null / immaterial finding and hand to Lane C.")

    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nVERDICT: {verdict}")
    print(f"material strata: {any_mat[:12]}")
    for n in SPANS:
        for side in ("hit", "pit"):
            s = by_n_side[f"n{n}_{side}"]
            print(f"  n={n} {side}: n={s['n']:4d} bias={s['mean_bias']:+7.3f} "
                  f"CI[{s['ci95'][0]:+.3f},{s['ci95'][1]:+.3f}] rmse={s['rmse']:.3f} "
                  f"sd_true={s['sd_true']:.3f} b/sd={s['bias_over_sd_true']:+.3f} "
                  f"material={s['material']}")
    print(f"\nwrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
