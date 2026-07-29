# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
#
# ============================================================================
# DESCRIPTIVE COMPS. DISPLAY ONLY.
#
# Nothing in this file may become a model input, a grade, a rank, a sort key,
# or a projection. It imports no efv_*, proj_*, fa_* or valuation module and
# touches no served number. It is a pure reshape of a frozen research artifact
# into a payload a lazy-loaded card panel can read.
# ============================================================================
"""Archetype comps sidecar: data/archetype_comps.json.

Reshapes tools/_comb_out/archetype_descriptive_hit.json (3,957 hitter strata
from the 2026-07-25 combinatorial-archetype sweep, never surfaced until now)
into a compact token-encoded table, and attaches the pre-registered cut points
from tools/_comb_out/prereg_hit.json so a panel can bucket a live player into
the same strata the sweep enumerated.

TWO THINGS THE READER MUST KNOW, both verified in this module's own audit
block (run `python archetype_comps_export.py --audit`):

1. THE SOURCE ARTIFACT'S health_warning IS FACTUALLY FALSE, AND IS NOT
   PROPAGATED. It claims: "Every one of these strata has an out-of-fold
   residual against the shipped eFV model that is statistically zero." That
   is not true of the numbers sitting in the same file. Of the 3,957 strata,
   477 (12.05 percent) carry |t| >= 2, 124 (3.13 percent) carry |t| >= 3, and
   the maximum is 4.91. Under a true global null those counts would be about
   180 and 11. After Benjamini-Hochberg control at q = 0.05 across all 3,957
   strata, 77 survive (all at |t| >= 3.30), so the excess is not a
   multiplicity artifact either. The artifact even contradicts itself: its
   own per-row already_priced flag is exactly (|t| <= 2.0) and is False on
   474 rows, i.e. the file simultaneously ships a field asserting that 474
   strata are NOT priced by the model and a prose warning asserting that all
   3,957 are. This export drops that prose and ships a per-stratum
   reliability tier derived from the actual t-statistic instead, so the
   frontend can mark the comps where the stratum and the grade disagree.

2. THE SWEEP THAT PRODUCED THIS RETURNED NO SHIP AS A MODEL, AND THE PRODUCER
   SCRIPT DOES NOT EXIST. Nested cross-validation found no out-of-sample
   value: on the hitter side every arm's rank-correlation delta is inside or
   below its own null band (d_rho -0.0106 to +0.0082, no CI clean of zero),
   and the inner-fold selected effect collapses out of fold (hitter real arms
   shrink from 0.86-1.85 WAR to -0.60..+0.50, i.e. 45 to 141 percent of the
   in-fold effect is selection bias; the negative-control arms invert
   outright). See tools/_comb_out/nested_hit_*.json and nested_pit_*.json.
   And tools/_comb_sweep_desc.py, the script that emitted the descriptive
   table, IS NOT IN THE TREE and nothing else in the repo writes that file,
   so the mean_war / median_war / bust_rate / oof_resid_* columns cannot be
   regenerated or independently audited. They are carried forward as a frozen
   quote of a 2026-07-25 measurement, not as a reproducible statistic.

   What IS reproducible, and is checked on every run: stratum membership. All
   3,957 ids and all 3,957 resolved-row counts match the pre-registered,
   outcome-blind enumeration in prereg_hit.json (sha fa70f4244573730b) exactly
   and byte-for-byte on the counts. The strata are honest; only the outcome
   statistics attached to them are unauditable.

CONTRACT for whatever renders this: it is a comp shelf. "Hitters who looked
like this went on to X" is a statement about 25 to 220 resolved players in a
2016-2020 decision window, not a forecast, not a correction to eFV, and never
an input to one.

Run: python archetype_comps_export.py [--audit]
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SRC_PATH = ROOT / "tools" / "_comb_out" / "archetype_descriptive_hit.json"
PREREG_PATH = ROOT / "tools" / "_comb_out" / "prereg_hit.json"
OUT_PATH = DATA / "archetype_comps.json"

SCHEMA = 1

# Reliability tiers, derived from the stratum's own out-of-fold residual t.
# The t tests "does the shipped eFV model already price this stratum", so a
# LARGE |t| does not mean the comp is wrong, it means the comp and the grade
# disagree and the panel must not present them as one voice.
T_NOMINAL = 1.645          # 90 percent two-sided, the "nominally non-zero" line
FDR_Q = 0.05               # Benjamini-Hochberg level across all strata
THIN_N = 40                # n_complete below this is a thin comp shelf
REL_CODES = ("priced", "watch", "off_model")

# Cut points below are transcribed from tools/_comb_axes.build_axes(), which
# is the code that actually assigned the buckets. Where AXIS_META prose and
# the code disagree (the scouting bands are 45 / 57.5, not 45 / 55 / 60), the
# CODE is quoted, because the code is what produced these strata.
TERCILE = {"T1": "Bottom third", "T2": "Middle third", "T3": "Top third"}

FACETS = {
    "age": {
        "label": "Age at decision", "cut": "fixed", "tier": "CORE",
        "note": "20 / 22 / 23.5, the HS-signing, college-draft and "
                "old-for-the-upper-minors conventions",
        "levels": {"U20": "Under 20", "20-21": "20 to 21.9",
                   "22-23": "22 to 23.4", "23.5+": "23.5 and up"},
        "edges": [20.0, 22.0, 23.5],
    },
    "age_rel_level": {
        "label": "Age vs level", "cut": "fixed", "tier": "CORE",
        "note": "years above or below the level's typical age",
        "levels": {"VYNG": "Very young for level (2+ years young)",
                   "YNG": "Young for level", "ONTIME": "On time for level",
                   "OLD": "Old for level (1+ year old)"},
        "edges": [-2.0, -0.5, 1.0],
    },
    "level": {
        "label": "Level at decision", "cut": "fixed", "tier": "CORE",
        "note": "the level ladder; DSL is folded into CPX for sample size",
        "levels": {"CPX": "Complex / DSL", "A": "Single-A", "A+": "High-A",
                   "AA": "Double-A", "AAA": "Triple-A"},
    },
    "n_milb_seasons": {
        "label": "MiLB seasons on record", "cut": "fixed", "tier": "CORE",
        "levels": {"S1": "1 season", "S2-3": "2 to 3 seasons",
                   "S4+": "4 or more seasons"},
        "edges": [2, 4],
    },
    "ops_rel": {
        "label": "Level-relative OPS", "cut": "tercile", "tier": "CORE",
        "levels": dict(TERCILE), "higher_is_better": True,
    },
    "k_rel": {
        "label": "Level-relative strikeout rate", "cut": "tercile",
        "tier": "CORE", "levels": dict(TERCILE), "higher_is_better": False,
    },
    "iso_rel": {
        "label": "Level-relative ISO", "cut": "tercile", "tier": "CORE",
        "levels": dict(TERCILE), "higher_is_better": True,
    },
    "prod_trend": {
        "label": "Production trend", "cut": "tercile", "tier": "CORE",
        "levels": dict(TERCILE), "higher_is_better": True,
    },
    "pos_group": {
        "label": "Position group", "cut": "fixed", "tier": "CORE",
        "levels": {"C": "Catcher", "MIF": "Middle infield",
                   "CIF": "Corner infield", "OF": "Outfield",
                   "UTIL": "Utility"},
    },
    "tool_hit": {
        "label": "Hit tool", "cut": "fixed", "tier": "CORE",
        "levels": {"BLW": "Below average (under 45)",
                   "AVG": "Average (45 to 57.5)", "PLUS": "Plus (57.5+)"},
        "edges": [45.0, 57.5],
    },
    "tool_game_pwr": {
        "label": "Game power", "cut": "fixed", "tier": "CORE",
        "levels": {"BLW": "Below average (under 45)",
                   "AVG": "Average (45 to 57.5)", "PLUS": "Plus (57.5+)"},
        "edges": [45.0, 57.5],
    },
    "tool_speed": {
        "label": "Speed", "cut": "fixed", "tier": "CORE",
        "levels": {"BLW": "Below average (under 45)",
                   "AVG": "Average (45 to 57.5)", "PLUS": "Plus (57.5 to 67.5)",
                   "BURNER": "Burner (67.5+)"},
        "edges": [45.0, 57.5, 67.5],
    },
    "acq": {
        "label": "Acquisition route", "cut": "fixed", "tier": "CORE",
        "levels": {"IFA": "International amateur", "COL": "College draft",
                   "HS": "High school draft"},
    },
    "fv": {
        "label": "Consensus FV tier", "cut": "fixed", "tier": "CORE",
        "levels": {"FV35-": "FV 35 or lower", "FV40": "FV 40",
                   "FV45": "FV 45", "FV50+": "FV 50 or higher"},
        "edges": [37.5, 42.5, 47.5],
    },
    "ops_sign": {
        "label": "OPS vs level median", "cut": "fixed", "tier": "EXT",
        "levels": {"ABOVE": "Above level median", "BELOW": "Below level median"},
    },
    "obp_rel": {
        "label": "Level-relative OBP", "cut": "tercile", "tier": "EXT",
        "levels": dict(TERCILE), "higher_is_better": True,
    },
    "bb_rel": {
        "label": "Level-relative walk rate", "cut": "tercile", "tier": "EXT",
        "levels": dict(TERCILE), "higher_is_better": True,
    },
    "peak_ops_rel": {
        "label": "Best-season OPS vs level", "cut": "tercile", "tier": "EXT",
        "levels": dict(TERCILE), "higher_is_better": True,
    },
    "peak_k_rel": {
        "label": "Best-season strikeout rate vs level", "cut": "tercile",
        "tier": "EXT", "levels": dict(TERCILE), "higher_is_better": False,
    },
    "pos_fine": {
        "label": "Primary position", "cut": "fixed", "tier": "EXT",
        "levels": {"C": "Catcher", "SS": "Shortstop", "2B": "Second base",
                   "3B": "Third base", "1B/DH": "First base / DH",
                   "CF": "Center field", "COF": "Corner outfield",
                   "OF": "Outfield (unspecified)", "UTIL": "Utility"},
    },
    "tool_raw_pwr": {
        "label": "Raw power", "cut": "fixed", "tier": "EXT",
        "levels": {"BLW": "Below average (under 45)",
                   "AVG": "Average (45 to 57.5)", "PLUS": "Plus (57.5+)"},
        "edges": [45.0, 57.5],
    },
    "tool_field": {
        "label": "Fielding", "cut": "fixed", "tier": "EXT",
        "levels": {"BLW": "Below average (under 45)",
                   "AVG": "Average (45 to 57.5)", "PLUS": "Plus (57.5+)"},
        "edges": [45.0, 57.5],
    },
    "tool_throw": {
        "label": "Arm", "cut": "fixed", "tier": "EXT",
        "levels": {"BLW": "Below average (under 45)",
                   "AVG": "Average (45 to 57.5)", "PLUS": "Plus (57.5+)"},
        "edges": [45.0, 57.5],
    },
    "pick": {
        "label": "Draft slot", "cut": "fixed", "tier": "EXT",
        "levels": {"TOP10": "Top 10 overall", "R1": "Rest of round 1 plus comp",
                   "R2-3": "Rounds 2 to 3", "DAY2+": "Day 2 or later"},
        "edges": [11, 41, 101],
    },
    "bonus": {
        "label": "Signing bonus", "cut": "tercile", "tier": "EXT",
        "note": "terciles among rows that report a bonus",
        "levels": dict(TERCILE), "higher_is_better": True,
    },
    "n_sources": {
        "label": "Ranking outlets on the consensus", "cut": "fixed",
        "tier": "EXT",
        "levels": {"SRC1": "1 outlet", "SRC2": "2 outlets",
                   "SRC3+": "3 or more outlets"},
        "edges": [2, 3],
    },
    "fv_trend": {
        "label": "Grade momentum", "cut": "tercile", "tier": "EXT",
        "levels": dict(TERCILE), "higher_is_better": True,
    },
    "il_any_pre": {
        "label": "Pre-decision injured list", "cut": "fixed", "tier": "EXT",
        "levels": {"NOIL": "No pre-decision IL stint",
                   "IL": "Any pre-decision IL stint"},
    },
}

COLS = ("f", "n_resolved", "n_complete", "mean_war", "war_lo95", "war_hi95",
        "median_war", "bust_rate", "resid", "resid_t", "rel", "thin",
        "zero_var")

COLS_NOTE = {
    "f": "indices into tokens; length is the way of the stratum (1 to 3)",
    "n_resolved": "rows in the stratum carrying an out-of-fold residual",
    "n_complete": "subset whose WAR window has closed; EVERY war and bust "
                  "number below is computed on this subset only",
    "mean_war": "mean realized WAR of the n_complete members",
    "war_lo95": "normal-approximation lower bound on mean_war",
    "war_hi95": "upper bound; see reliability.zero_var_note when they are "
                "equal",
    "median_war": "median realized WAR; far below mean_war in most strata "
                  "because the distribution is a mass at zero plus a tail",
    "bust_rate": "share of n_complete at or below 0.5 career WAR",
    "resid": "mean out-of-fold residual, realized minus the shipped eFV "
             "blend prediction, on the sweep's calibrated WAR scale (arm "
             "R_cal). Negative means the model graded the stratum above what "
             "it realized. Diagnostic for the reliability flag only; it is "
             "NOT an offset anyone may apply to a grade.",
    "resid_t": "Welch t of resid against the stratum's complement",
    "rel": "index into reliability.codes",
    "thin": f"1 when n_complete < {THIN_N}",
    "zero_var": "1 when war_lo95 == war_hi95; see reliability.zero_var_note",
}


def _p_two_sided(t: float) -> float:
    """Two-sided normal p for a Welch t. The sweep's own strata carry n in the
    tens to low hundreds, so the normal tail is a mild approximation; it is
    used only to order the strata for the FDR step, which is rank-based."""
    return math.erfc(abs(float(t)) / math.sqrt(2.0))


def _bh_reject(ps: list[float], q: float) -> list[bool]:
    """Benjamini-Hochberg step-up. Returns a per-input rejection mask."""
    n = len(ps)
    order = sorted(range(n), key=lambda i: ps[i])
    kmax = 0
    for rank, i in enumerate(order, start=1):
        if ps[i] <= q * rank / n:
            kmax = rank
    out = [False] * n
    for rank, i in enumerate(order, start=1):
        if rank <= kmax:
            out[i] = True
    return out


def _reliability(t: float, rejected: bool) -> int:
    """0 priced, 1 watch, 2 off_model. See REL_LEGEND for what each means."""
    if rejected:
        return 2
    return 1 if abs(float(t)) >= T_NOMINAL else 0


REL_LEGEND = {
    "priced": "Out-of-fold residual against the shipped eFV model is "
              "indistinguishable from zero (|t| under 1.645). The comp shelf "
              "and the grade tell the same story; show the comps plainly.",
    "watch": "|t| at or above 1.645 but not surviving Benjamini-Hochberg at "
             "q = 0.05 across all 3,957 strata. Nominally off-model, well "
             "inside what 3,957 overlapping tests throw off by chance. Treat "
             "as unverified, not as a finding.",
    "off_model": "Survives Benjamini-Hochberg at q = 0.05 across all 3,957 "
                 "strata (|t| at or above 3.30 here). The stratum's members "
                 "were systematically mis-graded out of fold, so the comp "
                 "shelf and the eFV grade DISAGREE. Neither is authoritative: "
                 "the sweep that found these returned NO SHIP under nested "
                 "CV, so this is a flag on the display, not a correction to "
                 "the grade. Mark it in the UI. Read audit.off_model_shape "
                 "before reading any of these as a model defect: the tier is "
                 "almost entirely the floored corner of the outcome scale.",
}

ZERO_VAR_NOTE = (
    "war_lo95 == war_hi95 == mean_war. Every complete-window member of the "
    "stratum realized the same WAR, in practice 0.0 because none of them "
    "reached the majors. The interval is degenerate, not precise: it carries "
    "no information about how a future player in the stratum will do. Never "
    "render it as a tight confidence band.")


def _audit(src: dict, prereg: dict) -> dict:
    """Everything this module asserts about the source, recomputed from the
    source. Fails loudly rather than shipping a claim it cannot back."""
    rows = src["archetypes"]
    n = len(rows)
    ts = [abs(float(r["oof_resid_t"])) for r in rows]
    counts = {f"ge_{thr}": sum(1 for t in ts if t >= thr)
              for thr in (1.0, 1.645, 2.0, 2.576, 3.0, 4.0)}
    ps = [_p_two_sided(r["oof_resid_t"]) for r in rows]
    rej = _bh_reject(ps, FDR_Q)
    n_rej = sum(rej)
    min_rej_t = min((ts[i] for i, x in enumerate(rej) if x), default=None)

    pre = {s["id"]: int(s["n"])
           for s in prereg["populations"]["TRACK"]["strata"]}
    unknown = [r["id"] for r in rows if r["id"] not in pre]
    n_mismatch = [r["id"] for r in rows
                  if r["id"] in pre and pre[r["id"]] != int(r["n_resolved"])]

    # the artifact's own already_priced field vs its own prose warning
    ap_false = sum(1 for r in rows if not r.get("already_priced"))
    ap_is_t_le_2 = sum(1 for r in rows
                       if (abs(float(r["oof_resid_t"])) <= 2.0)
                       == bool(r.get("already_priced")))

    # What the surviving off-model tier actually IS. It is not 77 scattered
    # model defects; it is one corner of the outcome scale.
    off = [r for i, r in enumerate(rows) if rej[i]]
    off_neg = sum(1 for r in off if float(r["oof_resid_t"]) < 0)
    off_bust1 = sum(1 for r in off if float(r["bust_rate_le_0p5"]) >= 1.0)
    off_zero = sum(1 for r in off
                   if float(r["war_ci95"][0]) == float(r["war_ci95"][1]))
    zero_var_all = sum(1 for r in rows
                       if float(r["war_ci95"][0]) == float(r["war_ci95"][1]))

    return {
        "n_strata": n,
        "abs_t_counts": counts,
        "abs_t_pct": {k: round(100.0 * v / n, 2) for k, v in counts.items()},
        "abs_t_max": round(max(ts), 2),
        "expected_under_global_null": {"ge_2.0": round(0.0455 * n, 1),
                                       "ge_3.0": round(0.0027 * n, 1)},
        "bh_q": FDR_Q,
        "bh_rejected": n_rej,
        "bh_min_rejected_abs_t": None if min_rej_t is None else round(min_rej_t, 2),
        "prereg_ids_unknown": len(unknown),
        "prereg_n_mismatch": len(n_mismatch),
        "prereg_sha256_16": prereg.get("prereg_sha256_16"),
        "already_priced_false": ap_false,
        "already_priced_equals_abs_t_le_2_rows": ap_is_t_le_2,
        "zero_variance_strata": zero_var_all,
        "off_model_shape": {
            "n": n_rej,
            "negative_residual": off_neg,
            "bust_rate_1p0": off_bust1,
            "zero_variance_ci": off_zero,
            "reading": (
                f"{off_neg} of {n_rej} surviving strata carry a NEGATIVE "
                "residual, i.e. the model graded them above what they "
                f"realized, and {off_bust1} busted at a 100 percent rate with "
                f"{off_zero} of them showing a zero-width WAR interval. The "
                "tier is dominated by the floor of the outcome scale: WAR "
                "cannot go below roughly zero for a player who never debuts, "
                "so any model that assigns a positive expectation to a young "
                "low-FV group is guaranteed a one-sided residual there. Treat "
                "off_model as 'the comp shelf bottoms out where the grade "
                "does not', not as evidence of a correctable eFV defect. It "
                "is a display caveat only, and the nested-CV NO SHIP verdict "
                "stands over all of it."),
        },
        "health_warning_verdict": (
            "FALSE. The source health_warning claims every stratum's "
            f"out-of-fold residual is statistically zero; {counts['ge_2.0']} "
            f"of {n} strata sit at |t| >= 2 (expected about "
            f"{round(0.0455 * n)} under a true global null), {n_rej} survive "
            "Benjamini-Hochberg at q = 0.05, and the artifact's own "
            f"already_priced flag is False on {ap_false} rows. Not "
            "propagated."),
    }


def build(src: dict, prereg: dict) -> dict:
    rows = src["archetypes"]
    audit = _audit(src, prereg)
    if audit["prereg_ids_unknown"] or audit["prereg_n_mismatch"]:
        raise SystemExit(
            "REFUSING TO SHIP: the descriptive table no longer matches the "
            "pre-registered stratum enumeration "
            f"({audit['prereg_ids_unknown']} unknown ids, "
            f"{audit['prereg_n_mismatch']} count mismatches). The membership "
            "check is the only reproducible property this artifact has.")

    ps = [_p_two_sided(r["oof_resid_t"]) for r in rows]
    rej = _bh_reject(ps, FDR_Q)

    tokens: list[str] = []
    tok_idx: dict[str, int] = {}
    out_rows = []
    for i, r in enumerate(rows):
        f = []
        for part in r["id"].split("|"):
            j = tok_idx.get(part)
            if j is None:
                j = tok_idx[part] = len(tokens)
                tokens.append(part)
            f.append(j)
        lo, hi = r["war_ci95"]
        out_rows.append([
            f,
            int(r["n_resolved"]),
            int(r["n_complete"]),
            round(float(r["mean_war"]), 2),
            round(float(lo), 2),
            round(float(hi), 2),
            round(float(r["median_war"]), 2),
            round(float(r["bust_rate_le_0p5"]), 3),
            round(float(r["oof_resid_cal"]), 2),
            round(float(r["oof_resid_t"]), 2),
            _reliability(r["oof_resid_t"], rej[i]),
            1 if int(r["n_complete"]) < THIN_N else 0,
            1 if float(lo) == float(hi) else 0,
        ])

    rel_counts = {REL_CODES[k]: sum(1 for x in out_rows if x[10] == k)
                  for k in range(3)}

    return {
        "schema": SCHEMA,
        "generated_at": date.today().isoformat(),
        "side": "hit",
        "contract": (
            "DESCRIPTIVE COMPS, DISPLAY ONLY. These are historical strata, "
            "not a projection and not a correction to any grade. Never a "
            "model input, a rank, or a sort key. The sweep that produced "
            "them returned NO SHIP under nested cross-validation."),
        "source": {
            "artifact": "tools/_comb_out/archetype_descriptive_hit.json",
            "sweep": "combinatorial-archetype sweep, 2026-07-25",
            "prereg": "tools/_comb_out/prereg_hit.json",
            "prereg_sha256_16": prereg.get("prereg_sha256_16"),
            "producer_script": "tools/_comb_sweep_desc.py",
            "producer_status": (
                "ABSENT from the tree. Nothing in the repo writes "
                "archetype_descriptive_hit.json, so mean_war, median_war, "
                "bust_rate and the oof_resid_* columns cannot be regenerated "
                "or independently audited. They are a frozen quote of a "
                "2026-07-25 measurement."),
            "reproduced": (
                "Stratum MEMBERSHIP is reproducible and is re-checked on "
                "every run: all 3,957 ids and all 3,957 resolved-row counts "
                "match the pre-registered outcome-blind enumeration exactly."),
            "model_verdict": (
                "NO SHIP. Nested CV found no out-of-sample value: hitter-side "
                "rank-correlation deltas run -0.0106 to +0.0082 with no CI "
                "clean of zero, and 45 to 141 percent of the in-fold selected "
                "effect is selection bias (inner 0.86 to 1.85 WAR collapsing "
                "to -0.60 to +0.50 out of fold). Negative-control arms invert. "
                "Evidence: tools/_comb_out/nested_hit_*.json."),
            "dropped_field": (
                "The source health_warning is not propagated. It is false; "
                "see audit.health_warning_verdict."),
        },
        "population": {
            "description": src.get("population"),
            "n_population": src.get("n_population"),
            "n_complete_window": src.get("n_complete_window"),
            "decision_years": [2016, 2024],
            "complete_window_years": [2016, 2020],
            "reporting_floor": src.get("reporting_floor"),
            "resolved_floor": "n_resolved >= 40 (the sweep's pre-registered "
                              "stratum size floor)",
            "note": "n_resolved counts rows carrying an out-of-fold residual; "
                    "n_complete counts the subset whose 6-year WAR window has "
                    "actually closed. Every WAR and bust number below is "
                    "computed on n_complete only.",
        },
        "base": {
            "mean_war": src.get("base_mean_war"),
            "bust_rate": src.get("base_bust_rate_le_0p5"),
            "bust_definition": "career WAR at or below 0.5 in the complete "
                               "window",
            "note": "population baseline; a stratum is only interesting "
                    "against this, and its own CI has to clear it",
        },
        "reliability": {
            "basis": "oof_resid_t, the Welch t of the stratum's mean "
                     "out-of-fold eFV residual against its complement",
            "t_nominal": T_NOMINAL,
            "fdr_q": FDR_Q,
            "thin_n_complete": THIN_N,
            "codes": list(REL_CODES),
            "legend": REL_LEGEND,
            "counts": rel_counts,
            "thin_rows": sum(x[11] for x in out_rows),
            "zero_var_rows": sum(x[12] for x in out_rows),
            "zero_var_note": ZERO_VAR_NOTE,
            "ui_rule": "rel == 2 must be visibly marked (the comp shelf and "
                       "the grade disagree). thin == 1 should carry the "
                       "sample size next to the number. zero_var == 1 must "
                       "suppress the interval entirely rather than draw a "
                       "zero-width band.",
        },
        "audit": audit,
        "facets": FACETS,
        "tercile_edges": prereg.get("tercile_edges"),
        "tercile_edges_note": (
            "frozen, outcome-blind cut points from the pre-registration; a "
            "panel must bucket a live player with THESE numbers to land in "
            "the same strata. Values are level-relative rate differences on "
            "the eFV matrix scale, not percentages."),
        "tokens": tokens,
        "cols": list(COLS),
        "cols_note": COLS_NOTE,
        "rows": out_rows,
        "row_note": "A player matches a row when every token in f is in the "
                    "player's own facet set. Bucket the player with "
                    "facets[].edges and tercile_edges, which are the frozen "
                    "cut points the sweep itself used.",
    }


def run(persist: bool = True) -> dict:
    src = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    out = build(src, prereg)
    if persist:
        text = json.dumps(out, separators=(",", ":"), sort_keys=False) + "\n"
        if not OUT_PATH.exists() or OUT_PATH.read_text(encoding="utf-8") != text:
            OUT_PATH.write_text(text, encoding="utf-8")
            log.info("wrote %s (%d strata)", OUT_PATH, len(out["rows"]))
    return out


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    audit_only = "--audit" in sys.argv
    src = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if audit_only:
        print(json.dumps(_audit(src, prereg), indent=1))
    else:
        out = run(persist=True)
        print(f"strata      {len(out['rows'])}")
        print(f"tokens      {len(out['tokens'])}")
        print(f"reliability {out['reliability']['counts']}")
        print(f"thin        {out['reliability']['thin_rows']}")
        print(f"bytes       {OUT_PATH.stat().st_size}")
