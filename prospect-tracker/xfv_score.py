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
from xfv_model import _prep, _vec, _feature_spec, _fit_ols_fv, _pred_ols
from xfv_dataset import matrix_path, live_matrix_path, CURRENT_SEASON

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
_BUCKETS = ("bust", "bench", "regular", "good", "star")

# Guarded blend for the HEADLINE grade + board rank: rank_war = (1-lambda)*consensus_war
# + lambda*model_war. The lean model now BEATS consensus FV on OOS rank for both sides
# (data/xfv_eval.json), so lambda is high; the small consensus anchor is the owner-approved
# insurance against feature-selection optimism (guarantees xFV ranks ~>= consensus). The
# REALIZED grade + surplus + distribution stay on the pure model (the honest outcome view).
_BLEND_LAMBDA = {"hit": 0.85, "pit": 0.80}


def scored_path(side):
    return DATA_DIR / ("xfv_scored_pitcher.json" if side == "pit" else "xfv_scored.json")


def scored_live_path(side):
    return DATA_DIR / ("xfv_scored_live_pitcher.json" if side == "pit"
                       else "xfv_scored_live.json")


def score_report_path(side):
    return DATA_DIR / ("xfv_score_report_pitcher.json" if side == "pit" else "xfv_score_report.json")


def _age_at(birth_date, year):
    if not birth_date:
        return None
    try:
        b = date.fromisoformat(birth_date[:10])
        return round((date(int(year), 4, 1) - b).days / 365.25, 1)
    except (ValueError, TypeError):
        return None


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
    lam = _BLEND_LAMBDA[side]

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
            p = rank_pos / (m - 1) if m > 1 else 0.0
            disp = target[min(m - 1, int(round(p * (m - 1))))]
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
    lam = _BLEND_LAMBDA[side]
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
        xfv_war = max(-2.0, a + b * _predict(ridge, _vec(r, side)))
        cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else xfv_war
        rank_war = (1 - lam) * cons_war + lam * xfv_war   # guarded blend -> headline rank
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
            p = rank_pos / (m - 1) if m > 1 else 0.0
            disp = target[min(m - 1, int(round(p * (m - 1))))]
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
