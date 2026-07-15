# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""eFV Pass 3 -- the production seam: turn the hitter model's WAR prediction into
the flagship outputs (grade + 5-bucket distribution + surplus $ + uncertainty),
reusing the existing value_framework engine end to end.

Pipeline per player:
  features -> ridge E[6yr summed bWAR] -> linear calibration (scale) = xfv_war
          -> vf.realized_implied_fv(xfv_war)            = xfv_grade (20-80)
          -> vf.p_bucket_given_fv(xfv_grade)            = 5-bucket distribution
          -> vf.expected_surplus_usd(xfv_grade, ...)    = surplus $ (engine-calibrated)
          -> vf.sv_distribution(xfv_grade, ...)         = uncertainty band

xfv_grade is monotone in xfv_war (realized_implied_fv is monotone), which is monotone
in the model prediction -> xfv_grade inherits the model's rank edge over consensus FV
(see data/xfv_eval.json). The surplus reuses the engine's own isotonic calibration; we
do NOT re-calibrate on top (no double-correction).

Artifacts: data/xfv_scored.json (per-player) + report block. Run: python efv_score.py
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

import value_framework as vf
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration, _spearman
from efv_model import _prep, _vec, _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda
from efv_dataset import matrix_path, live_matrix_path, CURRENT_SEASON, TARGET_SEASONS

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
_BUCKETS = ("bust", "bench", "regular", "good", "star")

# Guarded blend for the HEADLINE grade + board rank: rank_war = (1-lambda)*consensus_war
# + lambda*model_war. eFV still PREDICTS WAR; lambda is the WAG-CALIBRATED trust in its
# adjustment (how much realized WAR-Above-Grade supports eFV's where-consensus-missed edge,
# forward-chained -- see efv_model.wag_calibration). Hitters ~0.8, pitchers shrink harder.
# REALIZED grade + surplus + distribution stay on the pure model (the honest outcome view).


def scored_path(side):
    return DATA_DIR / ("xfv_scored_pitcher.json" if side == "pit" else "xfv_scored.json")


def scored_live_path(side):
    return DATA_DIR / ("xfv_scored_live_pitcher.json" if side == "pit"
                       else "xfv_scored_live.json")


def score_report_path(side):
    return DATA_DIR / ("xfv_score_report_pitcher.json" if side == "pit" else "xfv_score_report.json")


# Human labels for the per-prospect eFV explainer (which signals moved the grade off
# the consensus-FV prior). Keys match the model feature names.
_FACTOR_LABELS = {
    "obp_rel": "On-base vs level", "k_rel": "Contact (K%) vs level",
    "bb_rel": "Walk rate vs level", "iso_rel": "Power (ISO) vs level",
    "age_rel_level": "Age for level", "level_rank": "Level reached",
    "tool_hit": "Hit tool", "tool_speed": "Speed tool", "tool_game_pwr": "Power tool",
    "tool_field": "Field tool", "peak_k_rel": "Peak K rate", "peak_bb_rel": "Peak walk rate",
    "tool_fb": "Fastball", "tool_cmd": "Command", "tool_sl": "Slider",
    "tool_ch": "Changeup", "tool_cb": "Curveball", "era_rel": "ERA vs level",
    "x_era_k": "K-backed run prevention",                 # KRP+: (-era_rel)*k_rel
    "n_sources": "Source coverage", "pick_overall": "Draft pedigree",
    "bonus_log": "Signing bonus", "n_milb_seasons": "Track-record depth",
    "fv_stddev": "Source disagreement", "il_stints_pre": "Injury history",
    # ops_rel shipped into the hitter lean set 2026-07-07 without a label, so
    # the raw feature key leaked into the user-facing factors panel.
    "ops_rel": "Production (OPS) vs level",
    "peak_ops_rel": "Peak production (OPS)", "peak_obp_rel": "Peak on-base",
    "peak_iso_rel": "Peak power (ISO)",
}

# Features excluded from the per-prospect explainer: model-internal recentering,
# not interpretable per-prospect "reasons" a reader can act on.
#   fv                  - the consensus prior itself (the baseline deltas are FROM).
#   milb_missing        - the imputed-production INDICATOR. eFV only grades players
#                         WITH a pro track record, so every live-scored prospect has
#                         milb_missing=0; it is a near-constant offset (~+0.7 on ~all
#                         of them) whose "Thin track record" label reads BACKWARDS (a
#                         real track record scores UP because the weight is negative
#                         and the training mean > 0). Carries no per-player signal.
#   is_ifa / is_college - acquisition-cohort intercept dummies (a per-cohort baseline
#                         shift), not a scouting/production signal.
_EXPLAINER_SKIP = {"fv", "milb_missing", "is_ifa", "is_college"}


def _factors(ridge, feats, top: int = 4) -> list:
    """Per-prospect explainer: the non-FV ridge contributions (weight * standardized
    feature, in raw ridge units) that moved eFV off the consensus-FV prior, largest
    first. DOCSTRING CORRECTED 2026-07-14 (audit): the mags are DIRECTIONAL raw-model
    contributions, NOT an exact decomposition of the headline delta - the headline
    passes through the linear calibration (a + b*pred), the -2 floor, the blend
    lambda, and the live overlays, so these do not sum to xfv_minus_consensus.
    Returns [{label, dir, mag}]."""
    contribs = []
    for k, m, s, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"]):
        if k in _EXPLAINER_SKIP:
            continue
        c = w * ((feats.get(k, 0.0) - m) / (s or 1.0))
        if abs(c) >= 0.05:
            contribs.append((k, c))
    contribs.sort(key=lambda kc: -abs(kc[1]))
    return [{"label": _FACTOR_LABELS.get(k, k), "dir": "up" if c > 0 else "down",
             "mag": round(abs(c), 2)} for k, c in contribs[:top]]


def _age_at(birth_date, year):
    if not birth_date:
        return None
    try:
        b = date.fromisoformat(birth_date[:10])
        return round((date(int(year), 4, 1) - b).days / 365.25, 1)
    except (ValueError, TypeError):
        return None


def _age_factor(r) -> float:
    """Owner-directed live prospect-age penalty (2026-07-14, the Andrew Moore
    directive: a 26.9yo AA reliever must not rank top-100). A multiplicative
    haircut on the eFV WAR projection for OLD active prospects, mirroring the
    injury-penalty overlay: LIVE board only, never the resolved eval.

    Why an overlay and not a bigger model coefficient: the trained age
    coefficient is honest but small because the debuted-only training pool is
    survivorship-censored - the 26yo org arms who never got a shot are not in
    it, so the data cannot support the penalty the owner (correctly) wants
    priced. Ramp: 1.0 through age 25, -0.10/yr after, floored at 0.75
    (age 27.5+). Transparent via the "Prospect age penalty" factor chip."""
    age = r.get("age_now")
    if age is None:
        age = (r.get("milb") or {}).get("age")
    if age is None or float(age) <= 25.0:
        return 1.0
    return round(max(0.75, 1.0 - 0.10 * (float(age) - 25.0)), 3)


def _injury_factor(r) -> float:
    """Owner-directed live injury penalty: a multiplicative haircut on the eFV WAR
    projection (so it flows to the grade, the rank, AND surplus) for prospects who are
    currently hurt or recently fragile. Injuries cost cumulative WAR (durability) and
    carry re-injury risk that scout FV under-prices; eFV penalizes them harder. Applied
    only to the LIVE board (resolved players' outcomes already embed their injuries)."""
    f = 1.0
    if r.get("il_on"):
        t = str(r.get("il_type") or "").lower()
        f *= 0.70 if "60" in t else (0.82 if ("15" in t or "10" in t) else 0.90)
    days = float(r.get("il_days_12mo") or 0.0)
    if days >= 120:
        f *= 0.82
    elif days >= 60:
        f *= 0.90
    if float(r.get("il_stints_12mo") or 0.0) >= 3:
        f *= 0.92
    if r.get("is_post_tj"):
        f *= 0.85
    return round(max(0.5, f), 3)


# Statcast+ live-tilt slope, CALIBRATED from the measured forward-r (data/statcast_plus_eval.json)
# rather than a hand-set constant. SC+ is a 100+10z index, so a PERFECTLY-predictive SC+ would
# justify 0.01 / point (= 10% per 1σ); the actual, weak forward-r (~0.12 pit / ~0.15 hit) scales
# that down so the tilt is evidence-sized, not a WAG. Per side; the +/-18% clamp stays (it now
# rarely binds, because the calibrated slope is far gentler than the old 0.008).
_SC_TILT_PER_PT_AT_R1 = 0.01


def _sc_forward_r() -> dict:
    try:
        e = json.loads((DATA_DIR / "statcast_plus_eval.json").read_text(encoding="utf-8"))
        return {"hit": float(e["hitters"]["r_sc_vs_mlb_ops"]),
                "pit": float(e["pitchers"]["r_sc_vs_mlb_era_inv"])}
    except Exception:
        return {"hit": 0.15, "pit": 0.12}


_SC_FWD_R = _sc_forward_r()


def _statcast_factor(r, side: str = "hit") -> float:
    """Live Statcast+ overlay tilt: nudge the eFV WAR projection by batted-ball quality / Stuff+
    (100 = average). Current-state, upper-level only -> a provisional tilt (no historical Statcast
    to OOS-validate), bounded +/-18%. The slope is the per-side forward-r times the
    perfect-predictor slope (_SC_TILT_PER_PT_AT_R1), so a weak signal gets a small tilt. Players
    without a Statcast+ (lower levels) are untouched (factor 1.0)."""
    sc = r.get("statcast_plus")
    if sc is None:
        return 1.0
    try:
        sc = float(sc)
    except (TypeError, ValueError):
        return 1.0
    slope = max(0.0, _SC_FWD_R.get(side, 0.13)) * _SC_TILT_PER_PT_AT_R1
    return round(min(1.18, max(0.82, 1.0 + (sc - 100.0) * slope)), 3)


def _apply_war_tilt(war: float, factor: float) -> float:
    """Apply a multiplicative injury/Statcast tilt to a (possibly NEGATIVE) WAR
    projection in the INTENDED direction: a penalty (factor<1) always LOWERS the
    projection, a boost (factor>1) always RAISES it. For war>=0 that is war*factor;
    for war<0, war*factor INVERTS (a penalty on a negative war moves it toward zero =
    UP, so an injured fringe arm leapfrogs his healthy peers and the factors chip
    reads backwards), so divide instead -- symmetric and monotone across the sign
    boundary. Floored at the model floor -2.0."""
    if factor == 1.0 or war is None:
        return war
    adj = war * factor if war >= 0 else war / factor
    return max(-2.0, adj)


def _reprice_surplus_on_display(s: dict, is_pit: bool, pos, age=None, eta=None) -> None:
    """Re-price the surplus DOLLARS (surplus_mm + band + the surplus fan) off the DISPLAYED
    20-80 grade (xfv_grade_display) instead of the honestly-deflated realized grade, so the
    dollars a prospect shows match the eFV grade the site displays and the /projections/
    surface (owner: eFV surplus must be consistent site-wide). The OUTCOME ODDS (p_bucket and
    p_bust -- the validated star/bust odds) STAY on the realized grade: they are probabilities,
    not a dollar value, and were ground-truthed on that basis. No-op when the display grade or
    a priced surplus is unavailable (e.g. a provisional cohort)."""
    gq = s.get("xfv_grade_display")
    if gq is None:
        return
    kw = {}
    if age is not None:
        kw["age"] = age
    if eta is not None:
        kw["eta_years"] = eta
    sq = vf.expected_surplus_usd(gq, is_pit, pos, **kw)
    dq = vf.sv_distribution(gq, is_pit, pos, **kw) or {}
    pq = dq.get("percentiles") or {}
    _r1 = lambda v: round(float(v), 1) if v is not None else None
    s["surplus_mm"] = _r1(sq / 1e6) if sq else None
    s["band_p10_mm"] = _r1(pq.get("p10"))
    s["band_p90_mm"] = _r1(pq.get("p90"))
    if s.get("dist") is not None:
        # Surplus fan follows the displayed grade; keep the realized p_bust already on the row.
        s["dist"] = {"p10_mm": _r1(pq.get("p10")), "p25_mm": _r1(pq.get("p25")),
                     "p50_mm": _r1(pq.get("p50")), "p75_mm": _r1(pq.get("p75")),
                     "p90_mm": _r1(pq.get("p90")), "mean_mm": _r1(dq.get("mean")),
                     "p_bust": s.get("p_bust")}


def run(persist: bool = True, side: str = "hit") -> dict:
    keys, _mono = _feature_spec(side)
    is_pit = side == "pit"
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    # Match the GOVERNANCE eval pool (efv_model.run): drop never-MLB recent-bust rows
    # so the shipped model is fit on the same population the eval measures. Rank-neutral
    # (those rows are outside every forward-chain fold), just removes fringe fit noise.
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    by_key = {r["player_key"]: r for r in pool}

    # Final model: ridge on the full matrix + linear scale calibration (full-window) +
    # the consensus-FV OLS anchor for the guarded blend.
    ridge = _fit_ridge(data, keys)
    raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    ols = _fit_ols_fv(data)
    lam = blend_lambda(side)

    scored = []
    _price_ctx = {}                                       # pk -> age, for the post-rank surplus re-price
    for r in data:
        pk = r["player_key"]
        src = by_key[pk]
        xfv_war = max(-2.0, a + b * raw[pk])              # model E[6yr WAR] (honest)
        pos = src.get("position")
        dyear = src.get("debut_year") or 2020
        age = _age_at(src.get("birth_date"), dyear)
        _price_ctx[pk] = age
        # Invert the WAR->grade map on the model's OWN window (6 seasons, the model
        # target), NOT the global clemens control_years=7. A control_years flip for
        # valuation had silently re-pointed this denominator to 7 seasons, deflating
        # top-end grades (an elite prospect's 6yr-WAR prediction was priced against a
        # 7yr FV curve). Monotone -> rank-preserving, so the OOS eval is unchanged.
        xfv_grade = vf.realized_implied_fv(xfv_war, is_pit, age=age, position=pos,
                                           exposure_seasons=TARGET_SEASONS)
        cons_fv = src.get("consensus_fv_raw")
        if xfv_grade is None or cons_fv is None:
            continue
        cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else xfv_war
        rank_war = (1 - lam) * cons_war + lam * xfv_war   # guarded blend -> headline rank
        probs = vf.p_bucket_given_fv(xfv_grade, is_pit) or []
        xfv_surplus = vf.expected_surplus_usd(xfv_grade, is_pit, pos, age=age, eta_years=1.0)
        cons_surplus = vf.expected_surplus_usd(cons_fv, is_pit, pos, age=age, eta_years=1.0)
        dist = vf.sv_distribution(xfv_grade, is_pit, pos) or {}
        pcts = dist.get("percentiles") or {}
        scored.append({
            "player_key": pk, "kind": src["kind"], "position": pos,
            "consensus_fv": round(cons_fv, 1),
            "xfv_grade": round(xfv_grade, 1),
            "xfv_minus_consensus": round(xfv_grade - cons_fv, 1),
            "xfv_war_6yr": round(xfv_war, 2),
            "rank_war": round(rank_war, 3),
            "p_bucket": {b_: round(p, 3) for b_, p in zip(_BUCKETS, probs)},
            "surplus_mm": round(xfv_surplus / 1e6, 1) if xfv_surplus else None,
            "consensus_surplus_mm": round(cons_surplus / 1e6, 1) if cons_surplus else None,
            "band_p10_mm": round(pcts.get("p10", 0) , 1) if pcts else None,
            "band_p90_mm": round(pcts.get("p90", 0), 1) if pcts else None,
            "p_bust": round(dist.get("p_bust"), 3) if dist.get("p_bust") is not None else None,
            "realized_war_6yr": round(r["target"], 2),
            "censored": src.get("censored", False),
        })

    # --- re-anchor the HEADLINE grade onto the familiar 20-80 scale -------
    # The realized_implied_fv grade is honestly deflated (consensus FV is
    # optimistic) but floors at 20 and reads as jarringly low next to consensus.
    # The headline xfv_grade_display is a RANK-PRESERVING quantile map of the
    # GUARDED-BLEND ranking (rank_war) onto the consensus FV distribution of this
    # pool: the ordering is eFV's outcome-grounded ranking (the value-add, now
    # beating consensus OOS), the units match consensus (usable). Surplus/
    # distribution stay on the honest realized grade.
    if scored:
        target = sorted(s["consensus_fv"] for s in scored)
        order = sorted(range(len(scored)), key=lambda i: scored[i]["rank_war"])
        m = len(scored)
        for rank_pos, i in enumerate(order):
            p = (rank_pos / (m - 1)) if m > 1 else 0.0
            pos = p * (m - 1)                     # smooth (interpolated) quantile map so
            lo = int(pos); hi = min(m - 1, lo + 1); frac = pos - lo   # small WAR/tilt moves
            disp = target[lo] * (1 - frac) + target[hi] * frac        # show in the grade
            scored[i]["xfv_grade_display"] = round(disp, 1)
            scored[i]["xfv_minus_consensus_display"] = round(disp - scored[i]["consensus_fv"], 1)

    # --- re-price SURPLUS DOLLARS on the DISPLAYED (quantile) grade --------
    # Owner: eFV surplus must reflect the 20-80 grade the site shows (consensus-tier
    # market value), consistent with /projections/. Runs AFTER the quantile map since
    # xfv_grade_display is pool-relative. Star/bust odds stay on the realized grade.
    for s in scored:
        _reprice_surplus_on_display(s, is_pit, s.get("position"),
                                    age=_price_ctx.get(s["player_key"]), eta=1.0)

    # --- validation -------------------------------------------------------
    res = [s for s in scored if s["kind"] == "debuted" and not s["censored"]]
    # adjustment direction: does (xfv - consensus) point the same way as
    # (realized - consensus-implied WAR)? in-sample/illustrative.
    adj, miss = [], []
    for s in res:
        cons_implied = (vf.fv_to_6yr_avg_war(s["consensus_fv"]) or 0) * 6
        adj.append(s["xfv_minus_consensus"])
        miss.append(s["realized_war_6yr"] - cons_implied)
    dir_rho = _spearman(adj, miss) if len(adj) >= 8 else None

    ups = sorted(res, key=lambda s: -s["xfv_minus_consensus"])[:6]
    downs = sorted(res, key=lambda s: s["xfv_minus_consensus"])[:6]
    def _ex(s):
        return {"player_key": s["player_key"], "consensus_fv": s["consensus_fv"],
                "xfv_grade": s["xfv_grade"], "delta": s["xfv_minus_consensus"],
                "realized_war_6yr": s["realized_war_6yr"]}

    report = {
        "generated_at": date.today().isoformat(),
        "scope": "PITCHERS" if is_pit else "HITTERS", "n_scored": len(scored),
        "calibration_scale": {"a": round(a, 3), "b": round(b, 3)},
        "headline_grade_divergence_vs_consensus": {
            "scale": "rank-preserving quantile map onto consensus FV distribution",
            "mean_abs_delta": round(statistics.mean(abs(s["xfv_minus_consensus_display"]) for s in scored), 2),
            "max_up": round(max(s["xfv_minus_consensus_display"] for s in scored), 1),
            "max_down": round(min(s["xfv_minus_consensus_display"] for s in scored), 1),
            "share_within_2_grades": round(sum(1 for s in scored if abs(s["xfv_minus_consensus_display"]) <= 2) / len(scored), 3),
        },
        "realized_grade_divergence_vs_consensus": {
            "scale": "realized_implied_fv (honestly deflated; drives surplus + distribution)",
            "mean_abs_delta": round(statistics.mean(abs(s["xfv_minus_consensus"]) for s in scored), 2),
            "max_up": round(max(s["xfv_minus_consensus"] for s in scored), 1),
            "max_down": round(min(s["xfv_minus_consensus"] for s in scored), 1),
        },
        "adjustment_direction_check": {
            "spearman_adj_vs_consensus_miss": dir_rho,
            "n": len(adj),
            "reading": "positive => eFV up/down-adjustments point toward where consensus "
                       "FV under/over-shot realized WAR (illustrative, in-sample).",
        },
        "surplus_totals_mm": {
            "xfv": round(sum(s["surplus_mm"] or 0 for s in scored), 1),
            "consensus": round(sum(s["consensus_surplus_mm"] or 0 for s in scored), 1),
        },
        "example_up_adjustments": [_ex(s) for s in ups],
        "example_down_adjustments": [_ex(s) for s in downs],
        "note": ("xfv_grade is monotone in the model prediction, so it inherits the OOS "
                 "rank edge over consensus FV in data/xfv_eval.json. Surplus reuses the "
                 "engine's isotonic calibration (no double-correction)."),
    }
    if persist:
        sp, rp = scored_path(side), score_report_path(side)
        sp.write_text(json.dumps(scored, indent=0), encoding="utf-8")
        rp.write_text(json.dumps(report, indent=1), encoding="utf-8")
        log.info("wrote %s (%d players) + %s", sp, len(scored), rp)
    return report


def history_path():
    return DATA_DIR / "xfv_history.json"


def _build_grade_map(side: str):
    """Monotone rank_war -> display-grade lookup from the current live scored pool, so the
    historical eFV grades land on the SAME 20-80 scale as the current board grade."""
    try:
        scored = json.loads(scored_live_path(side).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted((s["rank_war"], s["xfv_grade_display"]) for s in scored
                  if s.get("rank_war") is not None and s.get("xfv_grade_display") is not None)


def _map_grade(grade_map, rank_war):
    if not grade_map:
        return None
    import bisect
    xs = [g[0] for g in grade_map]
    i = bisect.bisect_left(xs, rank_war)
    if i <= 0:
        return grade_map[0][1]
    if i >= len(grade_map):
        return grade_map[-1][1]
    (x0, y0), (x1, y1) = grade_map[i - 1], grade_map[i]
    return y0 if x1 == x0 else y0 + (y1 - y0) * (rank_war - x0) / (x1 - x0)


def score_history(persist: bool = True) -> dict:
    """Backfill an eFV value at EACH historical board snapshot so the FV-history chart can
    plot eFV over time (not just consensus). For every points[] entry we re-score the as-of
    features (that snapshot's per-source FV + tools + production as-of that year) with the
    shipped model and map onto the live grade scale. Honest caveat: this is today's model
    scoring old snapshots (a retrospective), not the grade we would have shown then. Writes
    data/xfv_history.json = {by_player: {key: [{d, x, c}]}}. Run after run_live (reuses its
    scored pool for the grade scale)."""
    from efv_dataset import (_prior_features, _milb_features, _load_sidecars, _cohort_flags,
                             _injury_features, _side_match, _f, CURRENT_SEASON)
    ts_path = DATA_DIR / "timeseries.json"
    if not ts_path.exists():
        return {"players": 0}
    players = (json.loads(ts_path.read_text(encoding="utf-8")).get("players")) or []
    fit = {s: _fit_production(s) for s in ("hit", "pit")}
    lam = {s: blend_lambda(s) for s in ("hit", "pit")}
    gmap = {s: _build_grade_map(s) for s in ("hit", "pit")}
    acq, il = _load_sidecars({p.get("player_key") for p in players if p.get("player_key")})

    out = {}
    for rec in players:
        pk = rec.get("player_key")
        if not pk:
            continue
        side = "pit" if _side_match(rec, "pit") else "hit"
        ridge, a, b, ols, _keys = fit[side]
        pts = sorted((pt for pt in (rec.get("points") or [])
                      if pt.get("snapshot_date") and _f(pt.get("consensus_fv_raw")) is not None),
                     key=lambda pt: pt["snapshot_date"])
        if len(pts) < 2:
            continue
        a_sc = acq.get(pk) or {}
        ilf = _injury_features(il.get(pk), None)
        series = []
        for pt in pts:
            cons_fv = _f(pt.get("consensus_fv_raw"))
            if cons_fv is None:
                continue
            yr = int(pt["snapshot_date"][:4])
            row = {"consensus_fv_raw": cons_fv, "pick_overall": a_sc.get("pick_overall"),
                   "bonus_usd": a_sc.get("bonus_usd"), **ilf}
            row["is_ifa"], row["is_college"] = _cohort_flags(a_sc.get("method"), a_sc.get("year"), rec.get("birth_date"))
            row.update(_prior_features(rec, pt, side))
            row["milb"] = _milb_features(rec.get("mlbam_id"), min(yr, CURRENT_SEASON) + 1,
                                         rec.get("birth_date"), side)
            model_war = max(-2.0, a + b * _predict(ridge, _vec(row, side)))
            # DISPLAYED (20-80 quantile-scale) grade at this snapshot: guarded blend ->
            # live grade map, the same transform behind the headline since the 2026-07-06
            # quantile flip -- so the eFV-history chart is on ONE scale with the badge (no
            # scale discontinuity at the live point; the pre-flip realized line sat ~5-9
            # grades below the displayed number).
            cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else model_war
            rank_war = (1 - lam[side]) * cons_war + lam[side] * model_war
            grade = _map_grade(gmap[side], rank_war)
            if grade is None:
                continue
            series.append({"d": pt["snapshot_date"], "x": round(grade, 1), "c": round(cons_fv, 1)})
        if len(series) >= 2:
            out[pk] = series

    if persist:
        history_path().write_text(json.dumps({"by_player": out}, separators=(",", ":")),
                                  encoding="utf-8")
        log.info("wrote %s (%d players)", history_path(), len(out))
    return {"players": len(out)}


def _fit_production(side: str):
    """Fit the shipped model (ridge + linear scale calibration + consensus-FV OLS anchor)
    on the FULL labeled matrix -- the same fit run() uses -- returning (ridge, a, b, ols, keys)."""
    keys, _mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    # ONE shared fit with the lambda selector (efv_model.fit_production_stack):
    # full labeled pool minus never-MLB recent-bust rows, ridge + output
    # calibration + consensus OLS. The selector sizing blend_lambda now measures
    # exactly this stack (E-LAMBDA parity repair 2026-07-15).
    from efv_model import fit_production_stack
    stack = fit_production_stack(rows, side, keys)
    if not stack:
        raise RuntimeError(f"production stack unfittable for side={side}")
    return stack["ridge"], stack["a"], stack["b"], stack["ols"], keys


def run_live(persist: bool = True, side: str = "hit") -> dict:
    """Score the CURRENT active prospect board (efv_dataset.build_live_matrix) with the
    model fit on the full labeled matrix. Same production seam as run() -- grade +
    5-bucket distribution + surplus + uncertainty band via value_framework -- but these
    players have no outcome label yet, so there is no validation block; they ARE the
    grades the site shows next to consensus FV. Surplus/distribution use each player's
    real timing (current age + ETA) so eFV prices on the same basis as the site's
    consensus surplus. Run after build_live + the site export (timeseries.json)."""
    is_pit = side == "pit"
    ridge, a, b, ols, _keys = _fit_production(side)
    lam = blend_lambda(side)
    live = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))

    scored, skipped_no_track = [], 0
    krp_raw = {}                                          # KRP+ pool: player_key -> x_era_k (pitchers w/ exposure)
    _price_ctx = {}                                       # pk -> (age, eta), for the post-rank surplus re-price
    for r in live:
        try:
            cons_fv = float(r.get("consensus_fv_raw"))
        except (TypeError, ValueError):
            continue
        # eFV is outcome/production-grounded: it ABSTAINS on players with no pro
        # track record. In training, milb_missing tagged untracked busts (large
        # negative weight); applying that to a current draftee/IFA who simply hasn't
        # played a pro season yet would wrongly crush them. Gate on MiLB production.
        if not r.get("milb"):
            skipped_no_track += 1
            continue
        feats = _vec(r, side)
        xfv_war = max(-2.0, a + b * _predict(ridge, feats))
        # E-STALE: the blend's consensus leg prices the DECAYED anchor
        # (fv_effective, efv_dataset._stale_anchor_discount) - the ground-truth
        # study shows a long-unlisted FV45 carries ~FV35 of credible consensus
        # information, and blending toward the raw anchor would hand back what
        # the decayed model feature just took away. Display consensus (cons_fv)
        # stays raw everywhere.
        _fv_eff = r.get("fv_effective")
        _cons_anchor = float(_fv_eff) if _fv_eff is not None else cons_fv
        cons_war = max(0.0, _pred_ols(ols, _cons_anchor)) if ols else xfv_war
        rank_war = (1 - lam) * cons_war + lam * xfv_war   # guarded blend -> headline rank
        factors = _factors(ridge, feats)                  # explainer: why eFV != consensus
        _stale_disc = float(r.get("anchor_stale_discount") or 0.0)
        if _stale_disc > 0:
            # surfaced like the other live overlays so the card explains WHY the
            # grade sits under a stale consensus (the Hickey complaint).
            factors.insert(0, {"label": "Stale list coverage", "dir": "down",
                               "mag": round(_stale_disc / 2.0, 2)})
        inj = _injury_factor(r)                           # owner-directed live injury penalty
        agef = _age_factor(r)                              # owner-directed live prospect-age penalty
        sc = _statcast_factor(r, side)                     # live Statcast+ quality tilt (per-side r-calibrated)
        if sc != 1.0:
            factors.insert(0, {"label": "Statcast+ quality", "dir": "up" if sc > 1 else "down",
                               "mag": round(abs(sc - 1) * 6, 2)})
        if inj < 1.0:
            factors.insert(0, {"label": "Injury penalty", "dir": "down",
                               "mag": round((1 - inj) * 6, 2)})
        if agef < 1.0:
            factors.insert(0, {"label": "Prospect age penalty", "dir": "down",
                               "mag": round((1 - agef) * 6, 2)})
        adj_factor = inj * sc * agef
        if adj_factor != 1.0:                              # adjust grade, rank, AND surplus
            xfv_war = _apply_war_tilt(xfv_war, adj_factor)  # sign-aware (negative-war safe)
            # Tilt the MODEL term only, then rebuild the blend, so the consensus
            # anchor cons_war is not also haircut. (rank_war *= adj_factor scaled
            # the whole blend, double-penalizing an injured/low-Statcast player.)
            rank_war = (1 - lam) * cons_war + lam * xfv_war
        pos = r.get("position")
        age = r.get("age_now")
        if age is None:
            age = _age_at(r.get("birth_date"), CURRENT_SEASON)
        eta = r.get("eta_years")
        eta = float(eta) if eta is not None else 1.0
        _price_ctx[r["player_key"]] = (age, eta)
        # Invert the WAR->grade map on the model's OWN window (6 seasons, the model
        # target), NOT the global clemens control_years=7. A control_years flip for
        # valuation had silently re-pointed this denominator to 7 seasons, deflating
        # top-end grades (an elite prospect's 6yr-WAR prediction was priced against a
        # 7yr FV curve). Monotone -> rank-preserving, so the OOS eval is unchanged.
        xfv_grade = vf.realized_implied_fv(xfv_war, is_pit, age=age, position=pos,
                                           exposure_seasons=TARGET_SEASONS)
        if xfv_grade is None:
            continue
        probs = vf.p_bucket_given_fv(xfv_grade, is_pit) or []
        xfv_surplus = vf.expected_surplus_usd(xfv_grade, is_pit, pos, age=age, eta_years=eta)
        dist = vf.sv_distribution(xfv_grade, is_pit, pos, age=age, eta_years=eta) or {}
        pcts = dist.get("percentiles") or {}
        def _mm(v):
            return round(float(v), 1) if v is not None else None
        # AUDIT FIX 2026-07-14: gate KRP+ on actual exposure, not the product's
        # truthiness - x_era_k == 0.0 also happens when era_rel is exactly 0.0
        # (or in the zeroed double-bad quadrant), and those arms DO have IP.
        if is_pit and (r.get("milb") or {}).get("era_rel") is not None \
                and float(feats.get("rates_missing", 1.0) or 0.0) == 0.0:
            krp_raw[r["player_key"]] = feats["x_era_k"]
        scored.append({
            "player_key": r["player_key"], "kind": "active", "position": pos,
            "consensus_fv": round(cons_fv, 1),
            "xfv_grade": round(xfv_grade, 1),                 # realized-implied (deflated)
            "xfv_minus_consensus": round(xfv_grade - cons_fv, 1),
            "xfv_war_6yr": round(xfv_war, 2),
            "rank_war": round(rank_war, 3),
            "p_bucket": {k: round(p, 3) for k, p in zip(_BUCKETS, probs)},
            "surplus_mm": _mm(xfv_surplus / 1e6) if xfv_surplus else None,
            "consensus_surplus_mm": r.get("consensus_surplus_mm"),
            "dist": {"p10_mm": _mm(pcts.get("p10")), "p25_mm": _mm(pcts.get("p25")),
                     "p50_mm": _mm(pcts.get("p50")), "p75_mm": _mm(pcts.get("p75")),
                     "p90_mm": _mm(pcts.get("p90")), "mean_mm": _mm(dist.get("mean")),
                     "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None},
            "band_p10_mm": _mm(pcts.get("p10")),
            "band_p90_mm": _mm(pcts.get("p90")),
            "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None,
            "injury_factor": inj if inj < 1.0 else None,
            "statcast_factor": sc if sc != 1.0 else None,
            "factors": factors,
        })

    # headline grade -- rank-preserving quantile map of the GUARDED-BLEND ranking
    # (rank_war) onto the LIVE pool's consensus FV distribution (units match consensus;
    # order is eFV's outcome-grounded ranking, which beats consensus OOS). Mirrors run();
    # surplus/distribution stay on the honest realized grade.
    if scored:
        target = sorted(s["consensus_fv"] for s in scored)
        order = sorted(range(len(scored)), key=lambda i: scored[i]["rank_war"])
        m = len(scored)
        for rank_pos, i in enumerate(order):
            p = (rank_pos / (m - 1)) if m > 1 else 0.0
            pos = p * (m - 1)                     # smooth (interpolated) quantile map so
            lo = int(pos); hi = min(m - 1, lo + 1); frac = pos - lo   # small WAR/tilt moves
            disp = target[lo] * (1 - frac) + target[hi] * frac        # show in the grade
            scored[i]["xfv_grade_display"] = round(disp, 1)
            scored[i]["xfv_minus_consensus_display"] = round(disp - scored[i]["consensus_fv"], 1)

    # Re-price SURPLUS DOLLARS on the DISPLAYED (quantile) grade (see run()): eFV surplus
    # reflects the 20-80 grade shown, consistent site-wide + with /projections/. Star/bust
    # odds stay on the realized grade.
    for s in scored:
        _age, _eta = _price_ctx.get(s["player_key"], (None, 1.0))
        _reprice_surplus_on_display(s, is_pit, s.get("position"), age=_age, eta=_eta)

    # KRP+ (K-backed Run Prevention): standardize the model's x_era_k = (-era_rel)*k_rel
    # interaction over the live pitcher pool onto the harmonized "+" scale (100 + 10*z,
    # population sigma, clamped 40-160). High = a below-level ERA that missing bats support.
    if is_pit and len(krp_raw) >= 2:
        vals = list(krp_raw.values())
        mu = statistics.mean(vals)
        sd = statistics.pstdev(vals)
        if sd > 0:
            for s in scored:
                x = krp_raw.get(s["player_key"])
                if x is not None:
                    s["krp_plus"] = round(min(160.0, max(40.0, 100 + 10 * (x - mu) / sd)), 1)

    xfv_tot = round(sum(s["surplus_mm"] or 0 for s in scored), 1)
    cons_tot = round(sum(s["consensus_surplus_mm"] or 0 for s in scored), 1)
    report = {
        "generated_at": date.today().isoformat(),
        "scope": f"LIVE {'PITCHERS' if is_pit else 'HITTERS'} (active board)",
        "n_scored": len(scored),
        "skipped_no_pro_track_record": skipped_no_track,
        "calibration_scale": {"a": round(a, 3), "b": round(b, 3)},
        "realized_grade_divergence_vs_consensus": {
            "mean_abs_delta": round(statistics.mean(abs(s["xfv_minus_consensus"]) for s in scored), 2) if scored else None,
            "mean_signed_delta": round(statistics.mean(s["xfv_minus_consensus"] for s in scored), 2) if scored else None,
        },
        "surplus_totals_mm": {"xfv": xfv_tot, "consensus": cons_tot,
                              "xfv_share_of_consensus": round(xfv_tot / cons_tot, 3) if cons_tot else None},
    }
    if persist:
        scored_live_path(side).write_text(json.dumps(scored, indent=0), encoding="utf-8")
        log.info("wrote %s (%d players)", scored_live_path(side), len(scored))
    return report


def backgrade_path():
    return DATA_DIR / "xfv_backgrade.json"


def run_backgrade(persist: bool = True) -> dict:
    """Backgrade EVERY graded prospect so the WHOLE site carries an eFV, not just the active
    board (run_live) + the labeled-outcome matrix (run). For each universe player -- timeseries
    actives + debuts.json graduates -- score the as-of features with the shipped model and map
    onto the SAME live grade scale the board uses, so a graduate's eFV is directly comparable
    to a current prospect's. Graduates are scored at their final pre-debut snapshot (the grade
    eFV carried into the majors) and keep realized_war for the did-we-nail-it read. Players with
    no pro track record are graded prior-anchored and flagged xfv_provisional. Fills the gap
    run_live (active w/ track record) + run (matrix cohort) leave behind. Run AFTER run_live
    (reuses its scored pool for the grade scale). Writes data/xfv_backgrade.json."""
    from efv_dataset import (_prior_features, _milb_features, _load_sidecars, _cohort_flags,
                             _injury_features, _side_match, _f, CURRENT_SEASON)
    fit = {s: _fit_production(s) for s in ("hit", "pit")}
    lam = {s: blend_lambda(s) for s in ("hit", "pit")}
    gmap = {s: _build_grade_map(s) for s in ("hit", "pit")}
    # Active-board players already have a richer live entry -- don't re-grade them here.
    have_live = set()
    for s in ("hit", "pit"):
        lp = scored_live_path(s)
        if lp.exists():
            have_live |= {r["player_key"] for r in json.loads(lp.read_text(encoding="utf-8"))}

    ts_path, deb_path = DATA_DIR / "timeseries.json", DATA_DIR / "debuts.json"
    actives = ((json.loads(ts_path.read_text(encoding="utf-8")).get("players") or [])
               if ts_path.exists() else [])
    debuted = json.loads(deb_path.read_text(encoding="utf-8")) if deb_path.exists() else []
    if isinstance(debuted, dict):
        debuted = debuted.get("players") or []
    # AUDIT FIX 2026-07-14: bust-kind players (inactive.json, ~2,200) used to
    # keep the RESOLVED pool's quantile scale in xfv.json because this queue
    # only covered graduates + actives - a quarter of the artifact read on a
    # different grade scale than the site. Score them here (anchored at their
    # final snapshot, same as the resolved builder) so the whole site reads
    # on the live scale.
    inact_path = DATA_DIR / "inactive.json"
    inact = json.loads(inact_path.read_text(encoding="utf-8")) if inact_path.exists() else []
    if isinstance(inact, dict):
        inact = inact.get("players") or []
    # Debuted first so a recently-graduated player who lingers in timeseries is tagged debuted.
    queue = ([(rec, "debuted") for rec in debuted]
             + [(rec, "active") for rec in actives]
             + [(rec, "bust") for rec in inact])
    acq, il = _load_sidecars({rec.get("player_key") for rec, _ in queue if rec.get("player_key")})

    def _mm(v):
        return round(float(v), 1) if v is not None else None

    scored, seen = [], set()
    for rec, kind in queue:
        pk = rec.get("player_key")
        if not pk or pk in seen or pk in have_live:
            continue
        pts = sorted((pt for pt in (rec.get("points") or [])
                      if pt.get("snapshot_date") and _f(pt.get("consensus_fv_raw")) is not None),
                     key=lambda pt: pt["snapshot_date"])
        if not pts:
            continue
        side = "pit" if _side_match(rec, "pit") else "hit"
        is_pit = side == "pit"
        ridge, a, b, ols, _keys = fit[side]
        debut_date = rec.get("debut_date") if kind == "debuted" else None
        # as-of point: graduate -> last snapshot before debut; active -> latest snapshot
        cand = [pt for pt in pts if (not debut_date or pt["snapshot_date"] < debut_date)] or pts
        pt = cand[-1]
        # AUDIT FIX 2026-07-14: when EVERY snapshot is post-debut the `or pts`
        # fallback anchors on a post-debut grade (187 graduates) - tag it so
        # realized-vs-grade readouts can exclude these from "the grade eFV
        # carried into the majors".
        postdebut_anchor = bool(debut_date and pt["snapshot_date"] >= debut_date)
        cons_fv = _f(pt.get("consensus_fv_raw"))
        if cons_fv is None:
            continue
        yr = int(pt["snapshot_date"][:4])
        milb_yr = (int(debut_date[:4]) if (kind == "debuted" and debut_date and debut_date[:4].isdigit())
                   else min(yr, CURRENT_SEASON) + 1)
        a_sc = acq.get(pk) or {}
        ilf = _injury_features(il.get(pk), None) if kind == "active" else {}
        row = {"consensus_fv_raw": cons_fv, "pick_overall": a_sc.get("pick_overall"),
               "bonus_usd": a_sc.get("bonus_usd"), **ilf}
        if kind == "active":
            # AUDIT FIX 2026-07-14: _injury_factor reads the LIVE il fields
            # (il_on/il_type/il_days_12mo/is_post_tj), which this row never
            # carried (_injury_features emits the PRE-cutoff training features)
            # - the backgrade injury penalty was dead code. Populate them the
            # same way build_live_matrix does.
            _il_st = rec.get("il_status") or {}
            _hp = rec.get("health_profile") or {}
            row.update({"il_on": 1 if _il_st.get("is_on_il") else 0,
                        "il_type": _il_st.get("type"),
                        "il_days_12mo": _f(_hp.get("il_days_12mo")) or 0.0,
                        "il_stints_12mo": _f(_hp.get("il_stints_12mo")) or 0.0,
                        "is_post_tj": bool(_hp.get("is_post_tj"))})
        row["is_ifa"], row["is_college"] = _cohort_flags(a_sc.get("method"), a_sc.get("year"), rec.get("birth_date"))
        row.update(_prior_features(rec, pt, side))
        row["milb"] = _milb_features(rec.get("mlbam_id"), milb_yr, rec.get("birth_date"), side)
        feats = _vec(row, side)
        cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else 0.0
        if row.get("milb"):
            xfv_war = max(-2.0, a + b * _predict(ridge, feats))
            factors = _factors(ridge, feats)
        else:
            # AUDIT FIX 2026-07-14: honor the docstring's prior-anchored
            # contract - a no-track-record row scored through the ridge eats
            # the trained milb_missing untracked-BUST penalty, which is wrong
            # for a merely data-less graduate. Grade on the consensus prior.
            xfv_war = cons_war
            factors = []
        rank_war = (1 - lam[side]) * cons_war + lam[side] * xfv_war
        inj = _injury_factor(row) if kind == "active" else 1.0   # graduate prospect-era IL is moot
        if inj < 1.0:
            factors.insert(0, {"label": "Injury penalty", "dir": "down", "mag": round((1 - inj) * 6, 2)})
            xfv_war = _apply_war_tilt(xfv_war, inj)         # sign-aware (negative-war safe)
            # Tilt the model term only, then rebuild the blend (see the live path
            # above): the consensus anchor must not also be haircut.
            rank_war = (1 - lam[side]) * cons_war + lam[side] * xfv_war
        disp = _map_grade(gmap[side], rank_war)
        if disp is None:
            continue
        if kind == "debuted":
            age, eta = _age_at(rec.get("birth_date"), milb_yr), 0.5
        else:
            age = rec.get("age_now") or _age_at(rec.get("birth_date"), CURRENT_SEASON)
            eta = float(rec.get("eta_years")) if rec.get("eta_years") is not None else 1.0
        pos = rec.get("position")
        # Invert the WAR->grade map on the model's OWN window (6 seasons, the model
        # target), NOT the global clemens control_years=7. A control_years flip for
        # valuation had silently re-pointed this denominator to 7 seasons, deflating
        # top-end grades (an elite prospect's 6yr-WAR prediction was priced against a
        # 7yr FV curve). Monotone -> rank-preserving, so the OOS eval is unchanged.
        xfv_grade = vf.realized_implied_fv(xfv_war, is_pit, age=age, position=pos,
                                           exposure_seasons=TARGET_SEASONS)
        if xfv_grade is None:
            continue
        probs = vf.p_bucket_given_fv(xfv_grade, is_pit) or []
        surplus = vf.expected_surplus_usd(xfv_grade, is_pit, pos, age=age, eta_years=eta)
        dist = vf.sv_distribution(xfv_grade, is_pit, pos, age=age, eta_years=eta) or {}
        pcts = dist.get("percentiles") or {}
        entry = {
            "player_key": pk, "side": side, "kind": kind, "position": pos,
            **({"xfv_postdebut_anchor": True} if postdebut_anchor else {}),
            "consensus_fv": round(cons_fv, 1),
            "xfv_grade": round(xfv_grade, 1),
            "xfv_grade_display": round(disp, 1),
            "xfv_minus_consensus_display": round(disp - cons_fv, 1),
            "xfv_minus_consensus": round(xfv_grade - cons_fv, 1),
            "xfv_war_6yr": round(xfv_war, 2),
            "rank_war": round(rank_war, 3),
            "p_bucket": {k: round(p, 3) for k, p in zip(_BUCKETS, probs)},
            "surplus_mm": _mm(surplus / 1e6) if surplus else None,
            "dist": {"p10_mm": _mm(pcts.get("p10")), "p25_mm": _mm(pcts.get("p25")),
                     "p50_mm": _mm(pcts.get("p50")), "p75_mm": _mm(pcts.get("p75")),
                     "p90_mm": _mm(pcts.get("p90")), "mean_mm": _mm(dist.get("mean")),
                     "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None},
            "band_p10_mm": _mm(pcts.get("p10")), "band_p90_mm": _mm(pcts.get("p90")),
            "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None,
            "factors": factors,
        }
        # Surplus dollars on the DISPLAYED (quantile) grade, consistent with the live board.
        _reprice_surplus_on_display(entry, is_pit, pos, age=age, eta=eta)
        if not row.get("milb"):
            entry["xfv_provisional"] = True          # prior-anchored (no pro track record)
        if inj < 1.0:
            entry["injury_factor"] = inj
        if kind == "debuted":
            cw = (rec.get("career_war") or {}).get("career_war")
            if cw is not None:
                entry["realized_war"] = round(float(cw), 1)
        scored.append(entry)
        seen.add(pk)

    if persist:
        backgrade_path().write_text(json.dumps({"scored": scored}, separators=(",", ":")),
                                    encoding="utf-8")
        log.info("wrote %s (%d players)", backgrade_path(), len(scored))
    return {"players": len(scored),
            "provisional": sum(1 for s in scored if s.get("xfv_provisional")),
            "debuted": sum(1 for s in scored if s["kind"] == "debuted")}


if __name__ == "__main__":
    import sys as _sys
    if "--live" in _sys.argv:
        for _s in ("hit", "pit"):
            logging.basicConfig(level=logging.INFO, format="%(message)s")
            _rep = run_live(side=_s)
            print(f"\n=== LIVE {_s} ===")
            print("n scored:", _rep["n_scored"], "| skipped (no pro track record):",
                  _rep["skipped_no_pro_track_record"], "| calibration:", _rep["calibration_scale"])
            print("realized divergence vs consensus:", json.dumps(_rep["realized_grade_divergence_vs_consensus"]))
            print("surplus totals ($M):", json.dumps(_rep["surplus_totals_mm"]))
        _sys.exit(0)
    _SIDE = "pit" if "--pit" in _sys.argv else "hit"
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run(side=_SIDE)
    print("n scored:", rep["n_scored"], "| calibration:", rep["calibration_scale"])
    print("headline divergence:", json.dumps(rep["headline_grade_divergence_vs_consensus"]))
    print("realized divergence:", json.dumps(rep["realized_grade_divergence_vs_consensus"]))
    print("adjustment direction check:", json.dumps(rep["adjustment_direction_check"]))
    print("surplus totals ($M):", json.dumps(rep["surplus_totals_mm"]))
    print("\nexample UP adjustments (eFV > consensus):")
    for e in rep["example_up_adjustments"]:
        print(f"  {e['player_key'][:24]:24s} cons={e['consensus_fv']:4} -> xfv={e['xfv_grade']:4} (+{e['delta']}) | realized 6yr WAR={e['realized_war_6yr']}")
    print("example DOWN adjustments (eFV < consensus):")
    for e in rep["example_down_adjustments"]:
        print(f"  {e['player_key'][:24]:24s} cons={e['consensus_fv']:4} -> xfv={e['xfv_grade']:4} ({e['delta']}) | realized 6yr WAR={e['realized_war_6yr']}")
