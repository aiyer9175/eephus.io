"""CROSSMODEL LANE: emit the durable cross-model map + ranked defect list.

Everything in `defects` was MEASURED in-session by the tools next to this file
(_am_crossmodel_lab.py, _am_lambda_stability.py, _am_dupscan.py) or by direct
import of the shipped modules. No number here is estimated.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "_am_crossmodel_map.json"


def classify(surface: str) -> str:
    s = (surface or "").lower()
    if "rendered nowhere" in s or s.startswith("model-dev") or s.startswith("n/a") or s.startswith("none"):
        return "model-dev/loss-ledger"
    if "gated off" in s or "not wired" in s or "implemented but off" in s:
        return "gated-off"
    return "served"


def surface_family(surface: str) -> str:
    s = (surface or "").lower()
    for key, fam in (("/fa/", "fa"), ("/projections/", "projections"), ("prospx", "prospx"),
                     ("/mlbstats/", "mlbstats"), ("/pal/", "pal"), ("/trademachine/", "trademachine"),
                     ("collegesavant", "collegesavant"), ("/glossary/", "glossary"),
                     ("farm", "prospx"), ("efv", "prospx"), ("draft", "prospx")):
        if key in s:
            return fam
    return "other"


def build():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    models = reg["models"]
    rows = []
    for m in models:
        ea = m.get("eval_artifact") or ""
        rows.append({
            "model_id": m["model_id"],
            "surface": m.get("surface") or "",
            "surface_family": surface_family(m.get("surface") or ""),
            "role": classify(m.get("surface") or ""),
            "verdict": m.get("verdict"),
            "eval_artifact": ea or None,
            "artifact_exists": bool(ea and (ROOT / ea).exists()),
        })
    counts = Counter((r["role"], r["verdict"]) for r in rows)
    fam = Counter(r["surface_family"] for r in rows if r["role"] == "served")

    doc = {
        "artifact": "cross-model redundancy + coherence map",
        "lane": "crossmodel",
        "generated_at": "2026-07-25",
        "standard": "docs/EFV_GATE_STANDARD.md",
        "scope_note": (
            "Registry census + duplicate-computation census + measured divergences. "
            "The registry census is exact (155 rows read from data/model_registry.json). "
            "The duplicate census is a grep-driven sweep of constant tables across "
            "*.py / *.js / *.html / *.yaml, so it is a LOWER BOUND, not a proof of "
            "completeness."),
        "census": {
            "n_registry_rows": len(rows),
            "by_role_and_verdict": {"%s|%s" % k: v for k, v in sorted(counts.items())},
            "served_rows": sum(1 for r in rows if r["role"] == "served"),
            "non_served_rows": sum(1 for r in rows if r["role"] != "served"),
            "non_served_deprecated_orphans": sorted(
                r["model_id"] for r in rows if r["role"] != "served" and r["verdict"] == "deprecated"),
            "served_by_family": dict(fam),
            "rows_with_no_eval_artifact": sorted(
                r["model_id"] for r in rows if not r["eval_artifact"]),
        },
        "rows": rows,
        "duplicate_computations": DUPLICATES,
        "basis_seams": BASIS,
        "cycles_checked_clean": CLEAN,
        "defects_ranked": DEFECTS,
        "measured_nulls": NULLS,
    }
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print("wrote", OUT)
    print("registry rows", len(rows), "served", doc["census"]["served_rows"],
          "orphan-deprecated", len(doc["census"]["non_served_deprecated_orphans"]))


DUPLICATES = [
    {
        "id": "D1-typical-age-at-level",
        "quantity": "typical (population-median) age at each MiLB level",
        "copies": {
            "efv_dataset._TYPICAL_LEVEL_AGE": {"DSL": 18.0, "CPX": 19.0, "A": 20.0,
                                               "A+": 21.0, "AA": 22.5, "AAA": 24.0},
            "level_norms.FALLBACK_AGE_BASELINE": {"DSL": 18.0, "CPX": 18.5, "A": 21.0,
                                                  "A+": 22.0, "AA": 23.0, "AAA": 24.0,
                                                  "MLB": 27.5},
            "age_level.LEVEL_BASELINES": {"A": 21.0, "A+": 22.0, "AA": 23.0, "AAA": 24.0},
            "eta.EXPECTED_AGES": {"A": 21.0, "A+": 22.0, "AA": 23.0, "AAA": 24.0,
                                  "CPX": 18.5, "DSL": 18.0},
            "spotlights._SPOTLIGHT_AGE_BASELINES": {"A": 21.0, "A+": 22.0, "AA": 23.0,
                                                    "AAA": 24.0, "MLB": 26.0},
        },
        "equal": False,
        "divergence_years_efv_minus_others": {"CPX": +0.5, "A": -1.0, "A+": -1.0,
                                              "AA": -0.5, "DSL": 0.0, "AAA": 0.0},
        "note": ("Four of the five copies agree exactly. efv_dataset is the outlier and it "
                 "is NOT a fallback: efv_dataset.py:412 uses it unconditionally to build "
                 "age_rel_level, a SHIPPED eFV feature on both sides. A 21.5yo at High-A is "
                 "'young for level' (-0.5) on every display surface and 'old for level' "
                 "(+0.5) inside the model that ranks him."),
        "accuracy_of_unifying": "measured NULL - see measured_nulls.N1",
    },
    {
        "id": "D2-level-to-mlb-eta",
        "quantity": "expected years from a MiLB level to an MLB debut",
        "copies": {
            "eta.BASE_YEARS (SHIPPED eta model, KM-fitted v39)": {
                "MLB": 0.0, "AAA": 0.75, "AA": 1.5, "A+": 3.0, "A": 3.75,
                "CPX": 4.25, "DSL": 7.5},
            "efv_ungraded._LEVEL_ETA (LIVE provisional surplus seam)": {
                "DSL": 6.0, "CPX": 5.0, "A": 4.5, "A+": 3.5, "AA": 2.5, "AAA": 1.5},
            "surplus_backtest_real._LEVEL_ETA (the GATE that validates prospect_surplus)": {
                "AAA": 1.0, "AA": 2.0, "A+": 2.5, "A": 3.0, "A-": 3.5, "CPX": 4.0,
                "ROK": 4.0, "DSL": 4.0, "FRk": 4.0, "Rk": 4.0},
            "eta_backtest.V38_BASE_YEARS (frozen legacy comparator - INTENTIONAL, not a defect)": {
                "MLB": 0.0, "AAA": 0.5, "AA": 2.0, "A+": 3.5, "A": 5.0, "CPX": 6.5, "DSL": 7.5},
        },
        "equal": False,
        "max_divergence_years_among_live_copies": {"DSL": 3.5, "A": 1.5, "AAA": 0.75,
                                                   "A+": 1.0, "AA": 1.0, "CPX": 1.0},
        "pv_consequence_at_7pct_discount": {
            "AAA_efv_ungraded_vs_eta": "1.07^0.75 = 5.2% under-pricing of AAA provisional surplus",
            "DSL_surplus_gate_vs_eta": "1.07^3.5 = 27.2% over-pricing inside the surplus GATE",
        },
        "cycle_safety": "eta.py imports NO project module, so any consumer may import it.",
    },
    {
        "id": "D3-positional-ladder",
        "quantity": "positional run adjustment (runs per 650 PA)",
        "copies": {
            "prospect_def_value.POS_ADJ (canonical, adopted 2026-07-25, DH = games x 8.5)": {
                "C": 10.91, "SS": 8.76, "2B": 4.51, "CF": 3.53, "3B": 3.36,
                "LF": -6.47, "RF": -6.41, "1B": -8.53, "DH": -14.04},
            "data/positional_fit.json fit.ladder.values (SERVED to /pal/ via positional_fit_ui.json; residual-DH spec, REFIT EVERY RUN)": {
                "C": 10.56, "SS": 8.89, "2B": 4.65, "CF": 3.63, "3B": 3.28,
                "LF": -6.47, "RF": -6.45, "1B": -8.60, "DH": -13.76},
            "positional_fit.py folklore_ladder (retired copy, emitted into the artifact)": {
                "C": 12.5, "SS": 7.5, "CF": 2.5, "2B": 2.5, "3B": 2.5,
                "RF": -7.5, "LF": -7.5, "1B": -12.5, "DH": -17.5},
            "tools/_recon_defense.POS_ADJ_STD (retired copy)": "same folklore numbers",
        },
        "equal": False,
        "divergence_runs_canonical_minus_served": {"C": 0.35, "SS": -0.13, "2B": -0.14,
                                                   "CF": -0.10, "3B": 0.08, "LF": 0.00,
                                                   "RF": 0.04, "1B": 0.07, "DH": -0.28},
        "note": ("The canonical ladder's own bootstrap CI95 half-width is ~0.05 runs. The C "
                 "rung disagrees by 0.35 runs = 7x that CI. Both are LIVE: POS_ADJ prices "
                 "data/prospect_def_value.json, the positional_fit ladder prices the /pal/ "
                 "positional-fit UI, so two surfaces answer 'what is a catcher worth' "
                 "differently. positional_fit refits on every run, so the gap is not even "
                 "stable."),
    },
    {
        "id": "D4-consensus-fv-to-6yr-war",
        "quantity": "expected first-6-season summed WAR given a consensus FV",
        "copies": {
            "efv_model._fit_ols_fv (per-side, refit per fold; the eFV blend's consensus anchor AND the eval baseline)":
                "hit a=-18.2718 b=0.4830 (n=1882); pit a=-10.1314 b=0.2753 (n=1989)",
            "value_framework.fv_to_6yr_avg_war(fv)*6 (ROLE-BLIND; prices prospect_surplus, farm_grades, fa_market, bayes_trade_value, the glossary walk-through, and efv_score:1003 cons_implied)":
                {"35": 1.14, "40": 1.14, "45": 1.86, "50": 4.02, "55": 5.88,
                 "60": 8.64, "65": 12.00, "70": 15.12},
        },
        "equal": False,
        "divergence_war_ols_minus_vf": {
            "hit": {"35": -1.140, "40": -0.091, "45": 1.604, "50": 1.859, "55": 2.414,
                    "60": 2.069, "65": 1.124, "70": 0.419},
            "pit": {"35": -1.140, "40": -0.258, "45": 0.398, "50": -0.385, "55": -0.869,
                    "60": -2.252, "65": -4.235, "70": -5.979},
        },
        "note": ("Worst case FV65 pitchers: 7.77 WAR (eFV's own anchor) vs 12.00 WAR "
                 "(the map that prices him) = -35%. One map is role-specific and one is "
                 "role-blind, and the role-blind one is the one that turns into dollars."),
    },
    {
        "id": "D5-js-level-ladders",
        "quantity": "MiLB level ordinal, inside one file (prospx/index.html)",
        "copies": {
            "LEVEL_RANK @12338": "DSL0 FCL1 CPX1 Rk1 R1 ROK1 A2 A+3 AA4 AAA5 MLB6 (ascending, WITH legacy aliases)",
            "_lvlRank @14145": "DSL1 CPX2 A3 A+4 AA5 AAA6 MLB7 (ascending, +1 origin, NO aliases)",
            "LEVEL_ORDER @15768": "MLB0 AAA1 AA2 A+3 A4 CPX5 DSL6 (descending)",
            "LEVEL_RANK @29625": "MLB0 AAA1 AA2 A+3 A4 CPX5 DSL6 (descending) - SAME IDENTIFIER as @12338, INVERSE POLARITY",
            "LEVEL_ORD @49089": "DSL0 CPX1 A2 A+3 AA4 AAA5 MLB6 (ascending)",
        },
        "equal": False,
        "live_impact": ("LATENT, not live. _lvlRank@14145 falls back to 0 for Rk/ROK/FCL/A-, "
                        "which would sort a rookie-league line BELOW DSL and defeat the alias "
                        "guarantee LEVEL_RANK@12338 documents. VERIFIED HARMLESS TODAY: the "
                        "served payload data/timeseries.json contains only "
                        "{A, CPX, A+, AA, DSL, AAA} (49,077 level tokens, 0 aliases). The "
                        "defect is the two same-named inverse-polarity constants, which is a "
                        "sign-error waiting to happen on the next edit."),
    },
    {
        "id": "D6-forked-value-framework",
        "quantity": "the whole surplus engine",
        "copies": {
            "value_framework.py": "202 KB, production",
            "tools/bucket_age_head/patched/value_framework.py": "197 KB fork, 188 diff lines",
            "tools/bucket_age_head/patched/efv_score.py": "53 KB fork",
        },
        "equal": False,
        "note": ("A full fork of the surplus engine + scorer for a lane whose registry verdict "
                 "is 'deprecated' (xfv_bucket_age_head, clean fail). Nothing in production "
                 "imports it. It will silently rot away from production and any future reader "
                 "who greps a constant will find two answers."),
    },
    {
        "id": "D7-plus-metric-formula",
        "quantity": "the 100 + 10z 'plus' rescale",
        "copies": {
            "storage._index_plus": "clamp [0, 250], returns None on stdev<=0 -- the documented shared helper",
            "prospx _clampPlus": "clamp [0, 250] -- agrees",
            "collegesavant/app.js + pitcher_app.js": "clamp [40, 160] -- DIVERGES",
            "stuff_plus_aaa.py / aaa_physics_export.py / advancement_pace_export.py / arkmetric_forward_eval.py / efv_score.krp_plus": "NO clamp",
        },
        "equal": False,
        "note": ("Not a served-number bug at current dispersion, but four different clamp "
                 "conventions for one platform-wide scale. storage._index_plus documents "
                 "itself as 'Generic X+ normalization shared by RPS+, DvM+, Stuff+, Cmd+' "
                 "and is in fact shared by none of the eight modules listed above."),
    },
    {
        "id": "D8-rate-shrinkage-constants",
        "quantity": "OPS / ERA stabilization pseudo-counts",
        "copies": {"rate_stabilization.{K_AB=170, K_IP=50, NEED_ERA_SHRINK_IP=45}":
                   "single definition, imported by storage.py and pal_conversion.py"},
        "equal": True,
        "note": ("CHECKED CLEAN. Already unified (registry: era_shrink_unification) and "
                 "guarded by test_stabilization_constants.py, which asserts the literals are "
                 "ABSENT from the consumers. This is the pattern the other seven should follow."),
    },
]

BASIS = [
    {
        "id": "B1-fwar-named-bwar-fed",
        "seam": "stats.fetch_career_war_bulk -> storage._build_debuted_payload -> value_framework.realized_consumed_seasons / _realized_consumed_usd / backtest.RealizedSeason",
        "declared": "value_framework docstrings say 'ACTUAL recorded fWAR', 'a {year: fWAR} mapping'; backtest.RealizedSeason.fwar",
        "actual": "bWAR. stats.py: 'bWAR is the ONE WAR source site-wide'; the feed is pybaseball.bwar_bat / bwar_pitch (B-Ref war_daily).",
        "numeric_divergence_today": "none - the field is only misnamed, not mis-fed",
        "severity": "medium (latent). bWAR and fWAR disagree most for pitchers (RA9 vs FIP); the next maintainer who honours the docstring wires the wrong feed.",
    },
    {
        "id": "B2-dollars-per-war-two-levels",
        "seam": "prospect_surplus / trade_machine vs fa_market / mlb_projections",
        "declared": "config/valuation_sets/prospx_current.yaml meta.win_cost_basis: 'FA-signings-implied $/WAR (data/fa_dpw_series.json, trailing 3-winter mean)'; params.win_cost.disable_fa_implied: false with the comment 'production leaves the FA-implied rescale ON'.",
        "actual": ("Production runs valuation_sets.DEFAULT_SET = clemens_2026, whose "
                   "params.win_cost.disable_fa_implied is TRUE. Live "
                   "value_framework._config()['dollars_per_war'] = flat 11.74M, "
                   "fa_implied {'enabled': False}. So the FA-implied rescale is OFF."),
        "numeric_divergence_today": (
            "prospect surplus and /trademachine/ vet surplus price a win at $11.7400M flat "
            "(value_framework.tiered_war_value_usd, unrescaled - verified in "
            "mlb_trade_lookup._compute_surplus). /projections/ RESCALES the identical "
            "value_framework tiered value by (winter_dpw / base_flat): "
            "proj_export._season_value_usd:128. Measured live: winter_dpw(2026) = "
            "$14,701,738 vs base_flat $11,740,000, ratio 1.2523. THE SAME 3.0-WAR SEASON IS "
            "WORTH $51.21M ON /projections/ AND $40.89M ON /trademachine/, a +25.2% gap "
            "(+20.8% for the 2027 winter). /fa/ prices on the same FA-implied series. "
            "Both models are registered 'validated'. Separately, the trailing-3-winter mean "
            "of data/fa_dpw_series.json is $13.0252M (+10.95% over base_flat) and the 2026 "
            "realized winter is $13.5826M (+15.70%)."),
        "severity": ("high - post-ETA prospects are served on BOTH /projections/ and "
                     "/trademachine/ (registry: mlb_projections_prospects, "
                     "trade_machine_surplus), so one player carries two dollar values 25% "
                     "apart, and the yaml comment asserts the opposite of production."),
    },
    {
        "id": "B3-role-split-applied-twice",
        "seam": "efv_score.realized_implied_fv -> efv_board_scale.board_value -> value_framework.surplus_value_mm",
        "declared": ("efv_board_side_scale shipped 2026-07-25 on the owner directive 'by the "
                     "Clemens framework, hitter/pitcher FVs translate to different outcomes'; "
                     "it raises pitcher grades (top-25 pitcher share 0.04 -> 0.12)."),
        "actual": ("value_framework.realized_implied_fv ACCEPTS is_pitcher and IGNORES it "
                   "(measured: identical FV for hit and pit at 2/4/6/9/12/16/20 WAR, max "
                   "delta 0.02 = rounding). So xfv_grade is a pure WAR-implied quantity: two "
                   "players at the same grade have, by construction, the same E[6yr WAR]. "
                   "value_framework.surplus_value_mm then prices the pitcher at 0.500x "
                   "(FV40) to 0.862x (FV70) of the hitter at the SAME grade. In "
                   "config/valuation_sets/prospx_current.yaml the ctrl_war column is "
                   "BYTE-IDENTICAL for hitter and pitcher at every tier (1.14 ... 15.12) "
                   "while surplus_musd is not (FV60: 78.6 vs 63.8)."),
        "numeric_divergence_today": ("same grade, same modelled control WAR, 19.0% less money "
                                     "at FV60 and 50.0% less at FV40, purely for being a pitcher."),
        "severity": ("high (coherence, not necessarily accuracy). The pitcher haircut may be a "
                     "correct risk/durability price, but it is applied at the DOLLAR layer to a "
                     "grade whose WAR content is already role-equalised, while a same-day ship "
                     "moves the grade the OTHER way. Nothing in either model's notes reconciles "
                     "the two. Needs one owner and one written basis."),
    },
    {
        "id": "B4-def-value-units",
        "seam": "prospect_def_value.POS_ADJ -> def_value -> data/prospect_def_value.json",
        "declared": "POS_ADJ_PROVENANCE.units = 'runs per 650 PA'",
        "actual": "def_value docstring: 'expected positional run value (per 162)'",
        "numeric_divergence_today": "none for a 650-PA regular; grows with playing-time shortfall",
        "severity": "low - documentation only; def_value is not an eFV input (swap REJECTED).",
    },
    {
        "id": "B5-fa-config-stale-economics",
        "seam": "fa_config.yaml header",
        "declared": "'the shared economics (discount rate 0.09, $/WAR tiers, 5% escalation) are READ from value_framework at runtime'",
        "actual": ("live discount_rate = 0.07 and dollars_per_war_inflation = 0.0 under "
                   "clemens_2026. fa_market.py's own docstrings already say 0.07."),
        "numeric_divergence_today": "the comment is wrong by 2pp on the discount rate and 5pp on escalation; the CODE is correct (it reads value_framework).",
        "severity": "low - stale comment. Note the ledger's documented 5%/yr backcast is a no-op at inflation 0.0, but it never fires in practice because data/fa_dpw_series.json covers 2015-2026.",
    },
]

CLEAN = [
    "No cycle from eFV back into its own inputs: consensus.py and grade_normalization.py contain zero references to xfv_* / efv_*; empirical_anchors groups the resolved cohort by CONSENSUS fv, never by xfv_grade. consensus -> eFV -> xfv_grade -> surplus is a DAG.",
    "One ridge implementation: prospect_path._fit_ridge is imported by efv_model, efv_score and efv_ungraded. Alpha is selected inside the training folds, so there is no selection leak.",
    "rate_stabilization K_AB / K_IP / NEED_ERA_SHRINK_IP are single-defined and test-guarded (test_stabilization_constants.py asserts the literals are absent from consumers).",
    "MLB park factors (fa_fit, Savant) and MiLB park factors (efv_park_line, in-house StatsAPI) are DIFFERENT populations, not a duplicate. efv_park_line is gated off anyway.",
    "advancement_pace_export.AP_LEVEL_RANK is a deliberate, documented second ladder (ap_-prefixed, sportId 16 grain) with an explicit name-collision warning. Not a defect.",
    "eta_backtest.V38_BASE_YEARS is a deliberately frozen legacy comparator with its rationale in-comment. Not a defect.",
]

DEFECTS = [
    {"rank": 1, "id": "B3", "severity": "high",
     "title": "pitcher role adjustment priced twice, in opposite directions",
     "where": "value_framework.realized_implied_fv / surplus_value_mm vs efv_board_scale",
     "action": "OWNER DECISION. Write down which layer owns the role split, then remove it from the other."},
    {"rank": 2, "id": "D4", "severity": "high",
     "title": "two live consensus-FV -> 6yr-WAR maps disagreeing by up to 5.98 WAR",
     "where": "efv_model._fit_ols_fv vs value_framework.fv_to_6yr_avg_war",
     "action": "Make fv_to_6yr_avg_war role-aware, or state in the registry that the dollar layer is deliberately role-blind and the ranker is not."},
    {"rank": 3, "id": "B2", "severity": "high",
     "title": "the same 3.0-WAR season is $51.21M on /projections/ and $40.89M on /trademachine/ (+25.2%)",
     "where": "proj_export._season_value_usd:128 rescales by winter_dpw/base_flat; mlb_trade_lookup._compute_surplus does not",
     "action": "Pick one basis for served dollars, or label the basis on screen. Also fix config/valuation_sets/prospx_current.yaml, which comments 'production leaves the FA-implied rescale ON' while production (clemens_2026) turns it OFF."},
    {"rank": 4, "id": "D2", "severity": "high",
     "title": "the gate that validates prospect_surplus discounts on an ETA table the shipped ETA model does not use (up to 3.5y at DSL, 27.2% PV at 7%)",
     "where": "surplus_backtest_real._LEVEL_ETA + efv_ungraded._LEVEL_ETA vs eta.BASE_YEARS",
     "action": "import eta; use eta.BASE_YEARS. eta.py has no project imports, so this cannot cycle."},
    {"rank": 5, "id": "L1", "severity": "medium-high",
     "title": "pitcher blend-lambda is an unpinned argmax over a curve flatter than its own detection limit, and it has already drifted",
     "where": "efv_model._BLEND_LAMBDA_RESELECT['pit'] is None",
     "action": "Pin pit as hit is already pinned. Measured: see measured_nulls.N2."},
    {"rank": 6, "id": "D3", "severity": "medium-high",
     "title": "two live positional ladders, 0.35 runs apart at C (7x the CI), one refit every run",
     "where": "prospect_def_value.POS_ADJ vs data/positional_fit.json",
     "action": "positional_fit should IMPORT prospect_def_value.POS_ADJ, or the eval must gate the residual-DH spec as the canonical one."},
    {"rank": 7, "id": "D1", "severity": "medium",
     "title": "eFV's age_rel_level is built on a typical-age table 1.0 year off the four other live copies",
     "where": "efv_dataset._TYPICAL_LEVEL_AGE:120 used unconditionally at :412",
     "action": "Unify onto the four-way-agreeing table. Measured accuracy cost is a NULL (measured_nulls.N1), so this is free."},
    {"rank": 8, "id": "B1", "severity": "medium",
     "title": "the surplus engine calls its WAR field fwar and is fed bWAR everywhere",
     "where": "value_framework, backtest.RealizedSeason",
     "action": "Rename to war_bref / bwar, or add an explicit basis note at the seam."},
    {"rank": 9, "id": "R1", "severity": "medium",
     "title": "51 of 155 registry rows (33%) are non-served deprecated loss ledgers",
     "where": "data/model_registry.json",
     "action": "Split into MODEL registry (86 served rows) and LOSS LEDGER. Do NOT delete: the ledgers are what stop dead lanes being re-attempted."},
    {"rank": 10, "id": "D6", "severity": "medium",
     "title": "a 250 KB fork of value_framework + efv_score for a deprecated lane",
     "where": "tools/bucket_age_head/patched/",
     "action": "Archive or delete; nothing imports it."},
    {"rank": 11, "id": "D7", "severity": "low-medium",
     "title": "the 100+10z plus scale has three clamp conventions across eight modules",
     "where": "storage._index_plus [0,250] vs collegesavant [40,160] vs five unclamped",
     "action": "Promote _index_plus out of storage.py into a shared module and import it."},
    {"rank": 12, "id": "D5", "severity": "low",
     "title": "two same-named inverse-polarity LEVEL_RANK constants in prospx/index.html plus three more ladders",
     "where": "prospx/index.html:12338, 14145, 15768, 29625, 49089",
     "action": "One exported ladder + one accessor. Latent today (no alias levels in the served payload)."},
    {"rank": 13, "id": "B5", "severity": "low",
     "title": "fa_config.yaml header states discount 0.09 / escalation 5%; live values are 0.07 / 0.0",
     "where": "fa_config.yaml:4, :24",
     "action": "Comment fix."},
    {"rank": 14, "id": "B4", "severity": "low",
     "title": "def_value documented per-162, ladder fitted per-650-PA",
     "where": "prospect_def_value.py:28 / :242",
     "action": "Docstring fix."},
]

NULLS = [
    {
        "id": "N1",
        "claim": "unifying efv_dataset._TYPICAL_LEVEL_AGE onto the four-way-agreeing site table",
        "protocol": ("forward-chained SCORED_YEARS (2020-2023), shipped blend leg at the live "
                     "lambdas (hit 0.70, pit 0.54); paired bootstrap B=300 resampling the WHOLE "
                     "pool with a ridge + consensus-OLS refit per draw; zero-information control "
                     "= the SAME age_rel_level column, row-permuted; plus a constant-zero arm."),
        "n": {"hit_pairs": 795, "pit_pairs": 837,
              "rows_actually_affected": "45% (1002 of 2065 hit rows and 1123 of 2065 pit rows carry milb_level = null)"},
        "point": {"base": {"hit": 0.28560, "pit": 0.25620, "block": 0.27787},
                  "site_table": {"hit": 0.28670, "pit": 0.25400, "block": 0.27565},
                  "row_permuted_control": {"hit": 0.28670, "pit": 0.26080, "block": 0.27926},
                  "constant_zero": {"hit": 0.28460, "pit": 0.25860, "block": 0.27675}},
        "paired_bootstrap_delta_vs_base": {
            "site_table": {"hit": {"mean": 0.00051, "ci95": [-0.0047, 0.0055]},
                           "pit": {"mean": -0.00285, "ci95": [-0.0153, 0.0094]},
                           "block": {"mean": -0.00122, "ci95": [-0.00903, 0.00606]}},
            "row_permuted_control": {"hit": {"mean": -0.00050, "ci95": [-0.0124, 0.0088]},
                                     "pit": {"mean": 0.00346, "ci95": [-0.0105, 0.0204]},
                                     "block": {"mean": 0.00149, "ci95": [-0.00685, 0.0117]}}},
        "floors": {"feature-class pooled rho": "0.017 hit / 0.016 pit", "block-rho": "0.0149"},
        "verdict": ("NULL on every arm, and the candidate is the same size as its own "
                    "zero-information control. Unification is accuracy-neutral at this "
                    "resolution, so the coherence fix is free. SECONDARY NULL, reported "
                    "because it bounds the problem: age_rel_level as currently specified is "
                    "not distinguishable from its row-permuted twin OR from a constant zero "
                    "in the shipped forward-chained blend. Per EFV_GATE_STANDARD section 6 "
                    "that is NOT grounds to remove it - it means the eval cannot adjudicate "
                    "this table, so the tie must be broken on coherence."),
        "artifact": "data/_am_crossmodel_agelevel_eval.json",
        "lab": "tools/_am_crossmodel_lab.py",
    },
    {
        "id": "N2",
        "claim": "the pitcher blend-lambda selector picks a resolvable optimum",
        "protocol": ("forward-chained SCORED_YEARS on the debuted pool (the pool the live "
                     "selector uses, n=438 scored pairs); ridge + consensus-OLS fit ONCE per "
                     "(draw, fold) and every lambda in 0.50-0.70 scored off the same legs; "
                     "bootstrap B=200 over the whole pool."),
        "measured": {
            "point_curve_spread_over_the_whole_search_band": 0.00190,
            "registered_MDE95_for_a_pit_lambda_shift": "0.005-0.008",
            "point_argmax": 0.55,
            "bootstrap_argmax_CI95": [0.50, 0.70],
            "bootstrap_argmax_mass_at_the_band_edges": "28.5% at 0.50, 9.5% at 0.70",
            "cost_of_pinning_at_0.54": {"mean": -0.00243, "p05": -0.0066},
            "cost_of_pinning_at_0.59": {"mean": -0.00294, "p05": -0.0072},
            "cost_of_pinning_at_0.70": {"mean": -0.00504, "p05": -0.0144}},
        "registry_drift": ("data/xfv_eval_pitcher.json (stamped 2026-07-24) records "
                           "shipped_lambda 0.59 with 'matches_shipped_lambda': true. Live "
                           "efv_model.blend_lambda('pit') returns 0.54 with no code change. "
                           "The registered self-consistency assertion is now FALSE."),
        "verdict": ("NULL - the entire 0.50-0.70 band is inside its own detection limit "
                    "(spread 0.0019 vs MDE95 0.005-0.008) and the bootstrap argmax spans the "
                    "whole band. Pinning costs nothing measurable. RECOMMEND PINNING pit the "
                    "way hit is already pinned, on the same stability argument the hit pin "
                    "was taken on. This is not an accuracy claim in either direction."),
        "artifact": "data/_am_lambda_stability_pit_deb.json",
        "lab": "tools/_am_lambda_stability.py",
    },
    {
        "id": "N3",
        "claim": "reproduction of registered eFV numbers",
        "measured": ("full_pool_km n reproduces EXACTLY (hit 795, pit 837 scored pairs). "
                     "Pooled blend rho does NOT reproduce byte-for-byte: I measure hit "
                     "0.28560 / pit 0.25620 against registered hit 0.2729 / pit 0.2519. The "
                     "pitcher gap is explained by the lambda drift in N2 (0.59 registered vs "
                     "0.54 live). The hitter gap (+0.0127) at an identical lambda and "
                     "identical n is NOT explained and is larger than the block-rho MDE95 of "
                     "0.0149... marginally under it, so it is formally unresolvable, but it "
                     "should be re-derived by the eFV lane rather than assumed benign."),
        "verdict": "PARTIAL reproduction. Flagged, not resolved - out of this lane's scope.",
    },
    {
        "id": "N4",
        "claim": "positional_ladder eval's duplicate_ladders_found claim",
        "measured": ("REPRODUCED exactly. data/positional_ladder_eval.json predicts the "
                     "residual-DH spec yields C 10.56, SS 8.89, 2B 4.65, CF 3.63, 3B 3.28, "
                     "LF -6.47, RF -6.45, 1B -8.60, DH -13.76. data/positional_fit.json "
                     "fit.ladder.values is byte-identical to that list. The 0.35-run C "
                     "divergence the eval warned about is live and served."),
        "verdict": "REPRODUCED.",
    },
]

if __name__ == "__main__":
    build()
