# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""xFV Pass 3 -- the production seam: turn the hitter model's WAR prediction into
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

Artifacts: data/xfv_scored.json (per-player) + report block. Run: python xfv_score.py
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

import value_framework as vf
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration, _spearman
from xfv_model import _prep, _vec, _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda
from xfv_dataset import matrix_path, live_matrix_path, CURRENT_SEASON

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
_BUCKETS = ("bust", "bench", "regular", "good", "star")

# Guarded blend for the HEADLINE grade + board rank: rank_war = (1-lambda)*consensus_war
# + lambda*model_war. xFV still PREDICTS WAR; lambda is the WAG-CALIBRATED trust in its
# adjustment (how much realized WAR-Above-Grade supports xFV's where-consensus-missed edge,
# forward-chained -- see xfv_model.wag_calibration). Hitters ~0.8, pitchers shrink harder.
# REALIZED grade + surplus + distribution stay on the pure model (the honest outcome view).


def scored_path(side):
    return DATA_DIR / ("xfv_scored_pitcher.json" if side == "pit" else "xfv_scored.json")


def scored_live_path(side):
    return DATA_DIR / ("xfv_scored_live_pitcher.json" if side == "pit"
                       else "xfv_scored_live.json")


def score_report_path(side):
    return DATA_DIR / ("xfv_score_report_pitcher.json" if side == "pit" else "xfv_score_report.json")


# Human labels for the per-prospect xFV explainer (which signals moved the grade off
# the consensus-FV prior). Keys match the model feature names.
_FACTOR_LABELS = {
    "obp_rel": "On-base vs level", "k_rel": "Contact (K%) vs level",
    "bb_rel": "Walk rate vs level", "iso_rel": "Power (ISO) vs level",
    "age_rel_level": "Age for level", "level_rank": "Level reached",
    "tool_hit": "Hit tool", "tool_speed": "Speed tool", "tool_game_pwr": "Power tool",
    "tool_field": "Field tool", "peak_k_rel": "Peak K rate", "peak_bb_rel": "Peak walk rate",
    "tool_fb": "Fastball", "tool_cmd": "Command", "tool_sl": "Slider",
    "tool_ch": "Changeup", "tool_cb": "Curveball", "era_rel": "ERA vs level",
    "n_sources": "Source coverage", "pick_overall": "Draft pedigree",
    "bonus_log": "Signing bonus", "milb_missing": "Thin track record",
    "fv_stddev": "Source disagreement", "il_stints_pre": "Injury history",
}


def _factors(ridge, feats, top: int = 4) -> list:
    """Per-prospect explainer: the non-FV ridge contributions (weight * standardized
    feature, in WAR units) that moved xFV off the consensus-FV prior, largest first.
    Sum of these ~= the xFV-minus-consensus adjustment, so it literally explains the
    delta. Returns [{label, dir, mag}]."""
    contribs = []
    for k, m, s, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"]):
        if k == "fv":
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


def _injury_factor(r) -> float:
    """Owner-directed live injury penalty: a multiplicative haircut on the xFV WAR
    projection (so it flows to the grade, the rank, AND surplus) for prospects who are
    currently hurt or recently fragile. Injuries cost cumulative WAR (durability) and
    carry re-injury risk that scout FV under-prices; xFV penalizes them harder. Applied
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


def _statcast_factor(r) -> float:
    """Live Statcast+ overlay tilt: nudge the xFV WAR projection by batted-ball quality /
    Stuff+ (100 = average), which the user flagged as under-used. Current-state, upper-level
    only -> a provisional tilt (no historical Statcast to OOS-validate), bounded +/-18%.
    Players without a Statcast+ (lower levels) are untouched (factor 1.0)."""
    sc = r.get("statcast_plus")
    if sc is None:
        return 1.0
    try:
        sc = float(sc)
    except (TypeError, ValueError):
        return 1.0
    return round(min(1.18, max(0.82, 1.0 + (sc - 100.0) * 0.008)), 3)


def run(persist: bool = True, side: str = "hit") -> dict:
    keys, _mono = _feature_spec(side)
    is_pit = side == "pit"
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit]
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
    for r in data:
        pk = r["player_key"]
        src = by_key[pk]
        xfv_war = max(-2.0, a + b * raw[pk])              # model E[6yr WAR] (honest)
        pos = src.get("position")
        dyear = src.get("debut_year") or 2020
        age = _age_at(src.get("birth_date"), dyear)
        xfv_grade = vf.realized_implied_fv(xfv_war, is_pit, age=age, position=pos)
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
    # pool: the ordering is xFV's outcome-grounded ranking (the value-add, now
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
            "reading": "positive => xFV up/down-adjustments point toward where consensus "
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
    historical xFV grades land on the SAME 20-80 scale as the current board grade."""
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
    """Backfill an xFV value at EACH historical board snapshot so the FV-history chart can
    plot xFV over time (not just consensus). For every points[] entry we re-score the as-of
    features (that snapshot's per-source FV + tools + production as-of that year) with the
    shipped model and map onto the live grade scale. Honest caveat: this is today's model
    scoring old snapshots (a retrospective), not the grade we would have shown then. Writes
    data/xfv_history.json = {by_player: {key: [{d, x, c}]}}. Run after run_live (reuses its
    scored pool for the grade scale)."""
    from xfv_dataset import (_prior_features, _milb_features, _load_sidecars,
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
            row.update(_prior_features(rec, pt, side))
            row["milb"] = _milb_features(rec.get("mlbam_id"), min(yr, CURRENT_SEASON) + 1,
                                         rec.get("birth_date"), side)
            model_war = max(-2.0, a + b * _predict(ridge, _vec(row, side)))
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
    is_pit = side == "pit"
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit]
    data = _prep(pool, "target_censored", side)
    ridge = _fit_ridge(data, keys)
    raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    ols = _fit_ols_fv(data)
    return ridge, a, b, ols, keys


def run_live(persist: bool = True, side: str = "hit") -> dict:
    """Score the CURRENT active prospect board (xfv_dataset.build_live_matrix) with the
    model fit on the full labeled matrix. Same production seam as run() -- grade +
    5-bucket distribution + surplus + uncertainty band via value_framework -- but these
    players have no outcome label yet, so there is no validation block; they ARE the
    grades the site shows next to consensus FV. Surplus/distribution use each player's
    real timing (current age + ETA) so xFV prices on the same basis as the site's
    consensus surplus. Run after build_live + the site export (timeseries.json)."""
    is_pit = side == "pit"
    ridge, a, b, ols, _keys = _fit_production(side)
    lam = blend_lambda(side)
    live = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))

    scored, skipped_no_track = [], 0
    for r in live:
        try:
            cons_fv = float(r.get("consensus_fv_raw"))
        except (TypeError, ValueError):
            continue
        # xFV is outcome/production-grounded: it ABSTAINS on players with no pro
        # track record. In training, milb_missing tagged untracked busts (large
        # negative weight); applying that to a current draftee/IFA who simply hasn't
        # played a pro season yet would wrongly crush them. Gate on MiLB production.
        if not r.get("milb"):
            skipped_no_track += 1
            continue
        feats = _vec(r, side)
        xfv_war = max(-2.0, a + b * _predict(ridge, feats))
        cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else xfv_war
        rank_war = (1 - lam) * cons_war + lam * xfv_war   # guarded blend -> headline rank
        factors = _factors(ridge, feats)                  # explainer: why xFV != consensus
        inj = _injury_factor(r)                           # owner-directed live injury penalty
        sc = _statcast_factor(r)                           # live Statcast+ quality tilt
        if sc != 1.0:
            factors.insert(0, {"label": "Statcast+ quality", "dir": "up" if sc > 1 else "down",
                               "mag": round(abs(sc - 1) * 6, 2)})
        if inj < 1.0:
            factors.insert(0, {"label": "Injury penalty", "dir": "down",
                               "mag": round((1 - inj) * 6, 2)})
        adj_factor = inj * sc
        if adj_factor != 1.0:                              # adjust grade, rank, AND surplus
            xfv_war = max(-2.0, xfv_war * adj_factor)
            rank_war *= adj_factor
        pos = r.get("position")
        age = r.get("age_now")
        if age is None:
            age = _age_at(r.get("birth_date"), CURRENT_SEASON)
        eta = r.get("eta_years")
        eta = float(eta) if eta is not None else 1.0
        xfv_grade = vf.realized_implied_fv(xfv_war, is_pit, age=age, position=pos)
        if xfv_grade is None:
            continue
        probs = vf.p_bucket_given_fv(xfv_grade, is_pit) or []
        xfv_surplus = vf.expected_surplus_usd(xfv_grade, is_pit, pos, age=age, eta_years=eta)
        dist = vf.sv_distribution(xfv_grade, is_pit, pos, age=age, eta_years=eta) or {}
        pcts = dist.get("percentiles") or {}
        def _mm(v):
            return round(float(v), 1) if v is not None else None
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
    # order is xFV's outcome-grounded ranking, which beats consensus OOS). Mirrors run();
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
    """Backgrade EVERY graded prospect so the WHOLE site carries an xFV, not just the active
    board (run_live) + the labeled-outcome matrix (run). For each universe player -- timeseries
    actives + debuts.json graduates -- score the as-of features with the shipped model and map
    onto the SAME live grade scale the board uses, so a graduate's xFV is directly comparable
    to a current prospect's. Graduates are scored at their final pre-debut snapshot (the grade
    xFV carried into the majors) and keep realized_war for the did-we-nail-it read. Players with
    no pro track record are graded prior-anchored and flagged xfv_provisional. Fills the gap
    run_live (active w/ track record) + run (matrix cohort) leave behind. Run AFTER run_live
    (reuses its scored pool for the grade scale). Writes data/xfv_backgrade.json."""
    from xfv_dataset import (_prior_features, _milb_features, _load_sidecars,
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
    # Debuted first so a recently-graduated player who lingers in timeseries is tagged debuted.
    queue = [(rec, "debuted") for rec in debuted] + [(rec, "active") for rec in actives]
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
        row.update(_prior_features(rec, pt, side))
        row["milb"] = _milb_features(rec.get("mlbam_id"), milb_yr, rec.get("birth_date"), side)
        feats = _vec(row, side)
        xfv_war = max(-2.0, a + b * _predict(ridge, feats))
        cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else xfv_war
        rank_war = (1 - lam[side]) * cons_war + lam[side] * xfv_war
        factors = _factors(ridge, feats)
        inj = _injury_factor(row) if kind == "active" else 1.0   # graduate prospect-era IL is moot
        if inj < 1.0:
            factors.insert(0, {"label": "Injury penalty", "dir": "down", "mag": round((1 - inj) * 6, 2)})
            xfv_war = max(-2.0, xfv_war * inj)
            rank_war *= inj
        disp = _map_grade(gmap[side], rank_war)
        if disp is None:
            continue
        if kind == "debuted":
            age, eta = _age_at(rec.get("birth_date"), milb_yr), 0.5
        else:
            age = rec.get("age_now") or _age_at(rec.get("birth_date"), CURRENT_SEASON)
            eta = float(rec.get("eta_years")) if rec.get("eta_years") is not None else 1.0
        pos = rec.get("position")
        xfv_grade = vf.realized_implied_fv(xfv_war, is_pit, age=age, position=pos)
        if xfv_grade is None:
            continue
        probs = vf.p_bucket_given_fv(xfv_grade, is_pit) or []
        surplus = vf.expected_surplus_usd(xfv_grade, is_pit, pos, age=age, eta_years=eta)
        dist = vf.sv_distribution(xfv_grade, is_pit, pos, age=age, eta_years=eta) or {}
        pcts = dist.get("percentiles") or {}
        entry = {
            "player_key": pk, "side": side, "kind": kind, "position": pos,
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
    print("\nexample UP adjustments (xFV > consensus):")
    for e in rep["example_up_adjustments"]:
        print(f"  {e['player_key'][:24]:24s} cons={e['consensus_fv']:4} -> xfv={e['xfv_grade']:4} (+{e['delta']}) | realized 6yr WAR={e['realized_war_6yr']}")
    print("example DOWN adjustments (xFV < consensus):")
    for e in rep["example_down_adjustments"]:
        print(f"  {e['player_key'][:24]:24s} cons={e['consensus_fv']:4} -> xfv={e['xfv_grade']:4} ({e['delta']}) | realized 6yr WAR={e['realized_war_6yr']}")
