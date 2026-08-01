# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""eFV Pass 6 -- consolidate the per-side scores + tool eFVs into one artifact the
site can consume (data/xfv.json): per player the headline grade (re-anchored to the
20-80 scale), the realized 6yr-WAR projection, the 5-bucket distribution, surplus $,
the uncertainty band, the consensus FV for side-by-side comparison, and tool eFVs.

Run: python efv_export.py   (after efv_score for both sides + xfv_tools)
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from efv_score import scored_path, scored_live_path

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv.json"
# eFV valuation curve (glossary Methodology surface): per-FV-tier worth of a
# grade under the production valuation set -- the published FanGraphs 2026
# anchor vs the value_framework model vs the live board's medians. Written by
# _valuation_curve(), fetched by assets/glossary.js (_methValuationCurveHTML),
# pinned by test_valuation_curve_surface.py. Diagnostic only.
VALUATION_CURVE_PATH = DATA_DIR / "xfv_valuation_curve.json"


def _entry(s, side, kind):
    e = {
        "side": "P" if side == "pit" else "H",
        "kind": kind,                    # "active" | "resolved" | backgrade kinds ("debuted"/"bust")
        # COMMENT CORRECTED 2026-07-14 (audit; the flip shipped 2026-07-06):
        # xfv_grade_quantile IS the displayed headline site-wide (prospx,
        # build_site, proj_export, fa_fit all read it first) and surplus_mm is
        # priced on it -- see meta.grade_scale. xfv_grade / xfv_grade_realized
        # is the honest pure-model reference (realized_implied_fv(E[6yr WAR]),
        # deflated), which still drives p_bucket / p_bust (validated odds).
        # The artifact shape (xfv_grade == realized alias) is test-pinned.
        "xfv_grade": s.get("xfv_grade"),                 # realized (pure model) reference
        "xfv_grade_realized": s.get("xfv_grade"),        # alias (identical; kept for back-compat reads)
        "xfv_grade_quantile": s.get("xfv_grade_display"),# the DISPLAYED headline (20-80 quantile map)
        "consensus_fv": s.get("consensus_fv"),
        # COMMENT CORRECTED 2026-07-23 (bughunt doc-drift): the realized delta
        # does NOT track the displayed quantile headline - the headline's delta
        # is xfv_minus_consensus_quantile below.
        "xfv_minus_consensus": s.get("xfv_minus_consensus"),          # realized - consensus (pure-model delta)
        "xfv_minus_consensus_quantile": s.get("xfv_minus_consensus_display"),  # displayed headline - consensus
        "xfv_war_6yr": s.get("xfv_war_6yr"),
        "p_bucket": s.get("p_bucket"),
        "surplus_mm": s.get("surplus_mm"),
        "band_p10_mm": s.get("band_p10_mm"),
        "band_p90_mm": s.get("band_p90_mm"),
        "p_bust": s.get("p_bust"),
    }
    if s.get("dist") is not None:                        # live: full surplus fan + comparison
        e["dist"] = s["dist"]
    if s.get("consensus_surplus_mm") is not None:
        e["consensus_surplus_mm"] = s["consensus_surplus_mm"]
    if s.get("injury_factor") is not None:               # live injury penalty (<1.0 = hurt)
        e["injury_factor"] = s["injury_factor"]
    if s.get("xfv_grade_healthy") is not None:           # same basis as xfv_grade, injury removed
        e["xfv_grade_healthy"] = s["xfv_grade_healthy"]
    if s.get("statcast_factor") is not None:             # live Statcast+ tilt (!=1.0)
        e["statcast_factor"] = s["statcast_factor"]
    if s.get("krp_plus") is not None:                    # KRP+ (K-backed Run Prevention), pitchers
        e["krp_plus"] = s["krp_plus"]
    if s.get("factors"):                                 # per-prospect eFV explainer
        e["factors"] = s["factors"]
    if s.get("xline_note"):                              # S-XLINE measurement note (annotation only,
        e["xline_note"] = s["xline_note"]                # live covered players; never a ranked factor)
    if s.get("xfv_provisional"):                          # prior-anchored (no pro track record)
        e["xfv_provisional"] = True
    if s.get("realized_war") is not None:                # backgraded graduate's actual career WAR
        e["realized_war"] = s["realized_war"]
    return e


def run(persist: bool = True) -> dict:
    from efv_model import blend_lambda   # local: avoids a module-level cycle
    by_player = {}
    counts = {"resolved": 0, "active": 0}
    # resolved (backtest cohort -- known outcomes; powers the Debuted views) FIRST, then
    # the live board OVERWRITES any overlap so a current prospect shows its live grade.
    for side in ("hit", "pit"):
        for s in json.loads(scored_path(side).read_text(encoding="utf-8")):
            by_player[s["player_key"]] = _entry(s, side, "resolved")
            counts["resolved"] += 1
    # Backgrade: every other graded prospect (graduates + lingering/no-track-record actives),
    # scored on the live grade scale. Overwrites the resolved-scale entry so the WHOLE site
    # reads on one scale; the live board (next) wins for current prospects.
    from efv_score import backgrade_path
    bp = backgrade_path()
    if bp.exists():
        for s in json.loads(bp.read_text(encoding="utf-8")).get("scored", []):
            by_player[s["player_key"]] = _entry(s, s.get("side") == "pit" and "pit" or "hit",
                                                s.get("kind", "backgrade"))
            counts["backgrade"] = counts.get("backgrade", 0) + 1
    for side in ("hit", "pit"):
        lp = scored_live_path(side)
        if not lp.exists():
            continue
        for s in json.loads(lp.read_text(encoding="utf-8")):
            by_player[s["player_key"]] = _entry(s, side, "active")
            counts["active"] += 1

    # tool eFVs: resolved first, then live overlays (live wins for board players).
    for fn in ("xfv_tools.json", "xfv_tools_live.json"):
        fp = DATA_DIR / fn
        if not fp.exists():
            continue
        for pk, tv in json.loads(fp.read_text(encoding="utf-8")).get("by_player", {}).items():
            if pk in by_player:
                by_player[pk]["tool_xfv"] = tv

    out = {
        "meta": {
            "generated_at": date.today().isoformat(),
            "n_players": len(by_player),
            # bughunt SCORE d (2026-07-23): count kind=="active" rows in the
            # MERGED artifact - the backgrade contributes prior-anchored
            # kind=="active" rows (264 at fix time, all xfv_provisional) on top
            # of the live-board count, so counts["active"] undercounted the
            # artifact's own active universe.
            "n_active": sum(1 for e in by_player.values() if e.get("kind") == "active"),
            # AUDIT FIX 2026-07-14: the LIVE blend lambda, stamped on every
            # regen - the governance eval artifacts (xfv_eval*.json) record
            # their own lambda at eval time and had silently desynced from
            # the live value twice; this stamp is the always-current truth
            # to compare them against.
            "live_lambda": {"hit": round(blend_lambda("hit"), 4),
                            "pit": round(blend_lambda("pit"), 4)},
            # RESTAMPED 2026-07-30. This string was stale on BOTH of its claims: it still
            # called xfv_grade_quantile the site-wide displayed grade (retired 2026-07-25,
            # when storage.BOARD_GRADE_FIELD moved to raw xfv_grade), and it described
            # xfv_grade through realized_implied_fv (retired 2026-07-30 by the pooled
            # outcome refit). A grade that changes meaning without its documentation
            # following is the exact drift this program spent the session correcting.
            "grade_scale": "xfv_grade is THE board number: the displayed grade, the sort key "
                           "and the basis of overall_rank (storage.BOARD_GRADE_FIELD). Since "
                           "2026-07-30 it is value_framework.outcome_implied_fv(E[6yr WAR]) -- "
                           "the inverse of the POOLED empirical outcome curve fitted on resolved "
                           "cohorts (data/fv_outcome_curves_pooled.json), so a grade states the "
                           "FV whose measured first-six-year bWAR matches this prediction. It is "
                           "a pure function of predicted WAR: unlike the retired map it takes no "
                           "age or position, so two rows with equal predictions grade equally. "
                           "Below about FV45 the curve is flat and the sub-floor knots are a "
                           "shape-preserving re-spread, so a sub-45 grade is NOT outcome-"
                           "calibrated and must not be read as one. xfv_grade_quantile is the "
                           "RETIRED per-side quantile map onto the consensus distribution; it is "
                           "no longer displayed but surplus_mm is still priced through it, which "
                           "is why the refit moved zero dollars. p_bucket / p_bust stay on the "
                           "retired realized_implied_fv map on purpose (they were ground-truthed "
                           "on it and a re-key has not been measured). Live board players carry "
                           "kind=active + a surplus dist; they require a pro track record (eFV "
                           "abstains on players with no MiLB production).",
            "eval": {"hitter": "data/xfv_eval.json", "pitcher": "data/xfv_eval_pitcher.json",
                     "tools": "data/xfv_tools.json"},
            "status": "provisional",
        },
        "by_player": by_player,
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=0), encoding="utf-8")
        log.info("wrote %s (%d players)", OUT_PATH, len(by_player))
    return out


# Tier axis for the valuation curve: the published FV tiers and the numeric
# grade each one prices at (the "+" half-grades sit at the midpoint). Matches
# valuation_sets._TIER_AXIS; duplicated as a literal so the artifact shape is
# stable even if the sets module reorders.
_VC_TIER_FV = {"35+": 37.5, "40": 40.0, "40+": 42.5, "45": 45.0, "45+": 47.5,
               "50": 50.0, "55": 55.0, "60": 60.0, "65": 65.0, "70": 70.0}
_VC_SET = "clemens_2026"
_VC_MIN_LIVE_N = 5     # thin-tier honesty: below this, ship n but no medians


def _valuation_curve(by_player=None) -> dict:
    """Bake data/xfv_valuation_curve.json: what an eFV grade is worth, per FV
    tier and role, three ways --

      published: the FanGraphs 2026 anchor table the valuation set commits to
                 (valuation_sets.tier_table: surplus $M, 7yr-control WAR,
                 star odds under the published 2-seasons-of-4+-WAR definition);
      model:     the same three quantities as the value_framework engine prices
                 them under the production set (surplus_value_mm, expected_war
                 mean at 7 service years, star_odds -- SAME star definition as
                 published, so the two columns are directly comparable);
      live:      medians over the current active board (data/xfv.json,
                 kind == "active") snapped to the nearest tier midpoint of the
                 displayed grade. NOTE p_star_median is the eFV 5-bucket "star"
                 outcome probability, a DIFFERENT quantity from the published
                 2x4 star odds -- both are kept, under clearly separate keys.

    Diagnostic only: measures the served numbers, changes none of them.
    Standalone: python -c "import efv_export; efv_export._valuation_curve()".
    """
    from statistics import median
    import valuation_sets                      # leaf import (no engine cycle)
    import value_framework

    if by_player is None:
        by_player = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("by_player", {})

    # --- live board medians, bucketed by nearest tier midpoint ---------------
    live = {role: {t: {"surplus": [], "war6": [], "pstar": []}
                   for t in _VC_TIER_FV} for role in ("hitter", "pitcher")}
    for e in by_player.values():
        if e.get("kind") != "active":
            continue
        q = e.get("xfv_grade_quantile")
        if q is None:
            continue
        role = "pitcher" if e.get("side") == "P" else "hitter"
        tier = min(_VC_TIER_FV, key=lambda t: (abs(float(q) - _VC_TIER_FV[t]),
                                               _VC_TIER_FV[t]))
        b = live[role][tier]
        b["surplus"].append(e.get("surplus_mm"))
        b["war6"].append(e.get("xfv_war_6yr"))
        b["pstar"].append((e.get("p_bucket") or {}).get("star"))

    def _live_block(role, tier):
        b = live[role][tier]
        n = len(b["surplus"])                  # players snapped to the tier
        out = {"n": n}
        if n >= _VC_MIN_LIVE_N:
            for key, vals, dp in (("surplus_mm_median", b["surplus"], 1),
                                  ("war6_median", b["war6"], 2),
                                  ("p_star_median", b["pstar"], 4)):
                got = [float(v) for v in vals if v is not None]
                if got:
                    out[key] = round(median(got), dp)
        return out

    # --- published anchor + engine model, per role/tier ----------------------
    tiers = {}
    with value_framework.valuation_set(_VC_SET):
        for role in ("hitter", "pitcher"):
            pub_table = valuation_sets.tier_table(_VC_SET, role)
            is_pit = role == "pitcher"
            rt = {}
            for tier, fv in _VC_TIER_FV.items():
                pub = pub_table.get(tier) or {}
                ew = value_framework.expected_war(fv, is_pit, service_years=7)
                sv = value_framework.surplus_value_mm(fv, is_pit)
                # bughunt F4 (2026-07-23): a like-for-like RAW column. The
                # monitor used to conflate bases (model = calibrated engine $,
                # live = the then-RAW served surplus_mm) and could not see the
                # drift it exists to measure (hitter FV45 read +51% when the
                # like-for-like gap was -23%). Served surplus_mm is CALIBRATED
                # now (efv_score seam, same 2026-07-23 ship), so live medians
                # compare like-for-like against model.surplus_mm; surplus_mm_raw
                # keeps the pre-calibration engine dollars visible so drift in
                # the calibration layer itself is also measurable.
                sv_raw = value_framework.expected_surplus_usd(fv, is_pit)
                so = value_framework.star_odds(fv, is_pit)
                rt[tier] = {
                    "fv": fv,
                    "published": {"surplus_mm": pub.get("surplus_musd"),
                                  "ctrl_war": pub.get("ctrl_war"),
                                  "star_odds": pub.get("star_odds")},
                    "model": {"surplus_mm": None if sv is None else round(sv, 1),
                              "surplus_mm_raw": None if sv_raw is None else round(sv_raw / 1e6, 1),
                              "expected_war": None if not ew else round(ew["mean"], 2),
                              "star_odds": None if so is None else round(so, 4)},
                    "live": _live_block(role, tier),
                }
            tiers[role] = rt

    star_def = (valuation_sets.engine_params(_VC_SET).get("star_definition")
                or {"min_seasons": 2, "war_threshold": 4.0})
    out = {
        "generated_at": date.today().isoformat(),
        "valuation_set": _VC_SET,
        "war_window": "7yr control window (published ctrl_war basis)",
        "star_def": {"min_seasons": star_def.get("min_seasons", 2),
                     "war_threshold": star_def.get("war_threshold", 4.0)},
        "surplus_basis": ("model.surplus_mm and live.surplus_mm_median are both "
                          "CALIBRATED engine dollars (served surplus_mm prices "
                          "through apply_calibration since 2026-07-23); "
                          "model.surplus_mm_raw is the raw pre-calibration engine "
                          "figure. live is timing-aware (age+ETA), model is "
                          "timing-naive - the remaining basis gap is timing only."),
        "tiers": tiers,
    }
    VALUATION_CURVE_PATH.write_text(json.dumps(out, indent=0), encoding="utf-8")
    log.info("wrote %s", VALUATION_CURVE_PATH)
    return out


def regen_all(persist: bool = True, include_eval: bool = False) -> dict:
    """Run the whole eFV pipeline in dependency order and consolidate data/xfv.json:
    training matrix -> live matrix -> resolved scores -> live scores -> tool eFVs ->
    export. The forward-chained backtest eval (efv_model, the governance artifact) is
    heavy and stable, so it is OPT-IN (include_eval). Requires data/timeseries.json
    (run after the site export). One call for what was five manual module runs."""
    import efv_dataset
    import efv_score
    import efv_tools
    for side in ("hit", "pit"):
        efv_dataset.run(persist, side)          # labeled training matrix + baseline
        efv_dataset.build_live(persist, side)   # current active-board feature matrix
    if include_eval:
        import efv_model
        for side in ("hit", "pit"):
            efv_model.run(persist, side)         # forward-chained eval (registry artifact)
    for side in ("hit", "pit"):
        efv_score.run(persist, side)             # resolved cohort scores
        efv_score.run_live(persist, side)        # live board scores (gated on track record)
    efv_score.run_backgrade(persist)              # backgrade the rest of the site (graduates etc.)
    efv_score.score_history(persist)              # eFV-over-time per snapshot (FV history chart)
    efv_tools.run(persist)                        # resolved tool eFVs
    efv_tools.run_live(persist)                   # live tool eFVs
    # UNGRADED prospects -- production-only leading indicator for the source-ungraded roster
    # players (DSL/CPX breakouts etc.). Separate model + artifact (data/xfv_ungraded.json);
    # NOT folded into the flagship xfv.json or the farm-rank composite. Needs rosters_by_org.json
    # (written by the site export) + the labeled matrix (built above). Best-effort.
    try:
        import efv_ungraded
        efv_ungraded.build(persist)
    except Exception:
        log.exception("efv_ungraded.build failed -- continuing without ungraded grades")
    # C1: refresh the shipped-distribution reliability curves + drift tripwire.
    # Diagnostic only (no served number depends on them); regen_all previously
    # omitted it, leaving data/xfv_reliability.json stale. Best-effort.
    try:
        import efv_reliability
        efv_reliability.build(persist)
    except Exception:
        log.exception("efv_reliability.build failed -- continuing without reliability regen")
    out = run(persist)
    # Valuation curve (glossary Methodology surface): what a grade is worth per
    # tier -- published anchor vs engine model vs live-board medians. Best-effort
    # like the reliability block above, fed the freshly consolidated by_player
    # so its live medians can never lag the export they describe. Skipped when
    # not persisting (a dry run must not touch committed data/ artifacts).
    if persist:
        try:
            _valuation_curve(out.get("by_player"))
        except Exception:
            log.exception("_valuation_curve failed -- continuing without valuation-curve regen")
        # S-XLINE-4 overlay signal bake (data/statcast_alevel_signals.json):
        # refresh the A/CPX whiff/velo z legs from the stored zone/statcast
        # payloads for the NEXT scoring pass (frozen coefficients re-emitted
        # verbatim, never refit). Best-effort like the blocks above; offline.
        try:
            import statcast_alevel_export
            statcast_alevel_export.run()
        except Exception:
            log.exception("statcast_alevel_export failed -- continuing with the prior signal bake")
    return out


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--all" in sys.argv:
        rep = regen_all(include_eval="--eval" in sys.argv)
    else:
        rep = run()
    print("eFV consolidated export:", rep["meta"]["n_players"], "players",
          f"({rep['meta']['n_active']} active) ->", OUT_PATH)
