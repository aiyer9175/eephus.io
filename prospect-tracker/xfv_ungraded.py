# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xFV for UNGRADED prospects -- a production-only leading indicator for the players the
scouting sources have NOT graded yet (the DSL/CPX/A breakout bats + arms the prospect
cycle is behind on, plus the org-depth fillers).

THE PROBLEM the flagship xFV model can't touch: it is anchored on consensus FV (the
dominant feature) and ABSTAINS on players with no source grade. But ~6,300 players on
40-man org rosters have real MiLB production and zero source FV -- and among them are
the genuine sleepers (a 18-yo posting an elite line in the DSL) that xFV could flag a
cycle ahead of the sources.

THE MODEL (deliberately separate, NOT the flagship): a dedicated NO-FV ridge -- the same
production substrate (level-relative k/bb/obp/iso vs contemporaneous norms, age-for-level,
multi-season peaks, track record) the flagship uses, but WITHOUT the consensus-FV anchor,
re-fit so the production features carry the full WAR signal instead of a partial effect.
Imputing a constant FV into the shipped model was tested and FAILS (the FV weight is so
dominant that production-only predictions floor at the -2 WAR clamp; degenerate). The
no-FV fit is the fix.

  VALIDATION (forward-chained on the labeled matrix, low-minors DSL/CPX/A cohort -- the
  target population; data/xfv_ungraded_eval.json):
    HITTERS  keep level_rank: low-minors age<=21 Spearman vs realized WAR ~0.22, all-levels
             ~0.31 -- nearly matching the 0.26 consensus FV gets on graded low-minors bats,
             for players who have NO consensus at all. A real coverage + discovery win.
    PITCHERS drop level_rank (it HURTS the low-minors read -- it rewards quad-A org arms
             reaching AAA): low-minors Spearman jumps 0.09 -> 0.24. The K-rate signal (a DSL
             arm missing bats) is the genuine lead; conservative by design (weak signal).

  GRADE MAP: a conventional, CAPPED, ABSOLUTE linear map war_pred -> FV (NOT a cohort
  quantile map -- a weak year must not inflate the top). Calibrated so the cohort matches
  both the owner's spec and conventional FV semantics: MOST land 20-30 (org filler), only
  genuine production breakouts reach 35-43, and a hard cap (43 hit / 40 pit) keeps any
  un-scouted player from masquerading as a real prospect (a true 45+ would have been
  graded). Heavy reliability shrinkage (inherited from _season_rates) keeps small-sample
  DSL lines from spiking.

These grades are PROVISIONAL and explicitly flagged (xfv_ungraded + xfv_provisional) so
every surface can show them as the production-only leading indicator they are, distinct
from the source-anchored flagship grade.

Artifact: data/xfv_ungraded.json (by_player + by_mlbam). Run: python xfv_ungraded.py
"""
from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path

import value_framework as vf
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration, _spearman
from xfv_model import _vec
from xfv_dataset import matrix_path, _milb_features, _f, CURRENT_SEASON

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv_ungraded.json"
EVAL_PATH = DATA_DIR / "xfv_ungraded_eval.json"
_BUCKETS = ("bust", "bench", "regular", "good", "star")

# No-FV production feature sets (see module docstring + data/xfv_ungraded_eval.json).
# Hitters KEEP level_rank (reaching a high level is predictive); pitchers DROP it (it
# rewards quad-A org arms and HURTS the low-minors discovery the model exists for).
_NOFV_HIT = ["obp_rel", "ops_rel", "k_rel", "peak_k_rel", "peak_obp_rel",
             "iso_rel", "age_rel_level", "level_rank", "n_milb_seasons"]
_NOFV_PIT = ["k_rel", "peak_k_rel", "bb_rel", "era_rel", "x_era_k",
             "age_rel_level", "n_milb_seasons"]

# Conventional grade map with a SOFT ceiling: grade = BASE + SLOPE*war_pred, floored at
# FLOOR, then compressed above KNEE toward CEIL: g' = KNEE + (CEIL-KNEE)*(1-exp(-(g-KNEE)/SOFT)).
# Spec-calibrated (owner: "low, 20-30 for most, breakouts higher") + validated to match
# conventional FV semantics on the real roster cohort (hitters median ~23 / 77% <=30;
# pitchers median ~24 / 87% <=30). WHY SOFT, not a HARD CAP (cap test, 2026-06-23):
#   HITTERS  uncapped grade carries REAL forward-chained signal above 43 (realized 6yr WAR
#            bins: [43,48) mean 3.43, [48+) mean 6.10; Spearman 0.29 among grade>=40), so a
#            hard cap at 43 DISCARDS signal -- the genuine young-for-level breakouts (an 18-yo
#            holding AA) deserve mid-to-high-40s. KNEE 43 / CEIL 49 lets them through while
#            bounding the extreme (an un-scouted player still can't claim top-prospect status
#            without scout corroboration; ungraded-selection risk caps the magnitude).
#   PITCHERS signal above 40 is NOISE (Spearman 0.077; bins flat) -- the top uncapped arms are
#            small-sample high-K complex-ball spikes. KNEE 38 / CEIL 42 compresses hard.
# Soft (not hard) so ORDER is preserved above the knee -- it matters now that these grades fold
# into the flagship board rank + farm composite.
_GRADE_MAP = {
    "hit": {"BASE": 27.0, "SLOPE": 3.8, "FLOOR": 20.0, "KNEE": 43.0, "CEIL": 49.0, "SOFT": 4.0},
    "pit": {"BASE": 25.0, "SLOPE": 4.5, "FLOOR": 20.0, "KNEE": 38.0, "CEIL": 42.0, "SOFT": 2.5},
}

# Default ETA (years to MLB) by level, for the surplus seam -- ungraded low-minors players
# are years away. Surplus at FV 20-35 is near $0 regardless; this only shapes the band.
_LEVEL_ETA = {"DSL": 6.0, "CPX": 5.0, "A": 4.5, "A+": 3.5, "AA": 2.5, "AAA": 1.5}

_FACTOR_LABELS = {
    "obp_rel": "On-base vs level", "ops_rel": "OPS vs level", "k_rel": "Contact (K%) vs level",
    "bb_rel": "Walk rate vs level", "iso_rel": "Power (ISO) vs level", "era_rel": "ERA vs level",
    "age_rel_level": "Age for level", "level_rank": "Level reached", "x_era_k": "Run prevention x K",
    "peak_k_rel": "Peak K rate", "peak_obp_rel": "Peak on-base", "n_milb_seasons": "Track record",
}

_PIT_POS = ("P", "RHP", "LHP", "SP", "RP", "SIRP", "MIRP")


def _is_pitcher_pos(pos) -> bool:
    return (pos or "").upper() in _PIT_POS


def _prep(rows, side: str):
    """Labeled rows -> {feats, target} for the no-FV fit (reuses the flagship _vec, which
    already emits every production feature; we just train on a subset of keys)."""
    out = []
    for r in rows:
        t = r.get("target_censored")
        if t is None:
            continue
        out.append({
            "player_key": r["player_key"], "feats": _vec(r, side), "target": float(t),
            "weight": float(r.get("weight", 1.0)),
            "decision_year": (int(r["debut_year"]) if r["kind"] == "debuted"
                              else (int((r.get("cutoff") or "2026")[:4]) + 1
                                    if (r.get("cutoff") or "")[:4].isdigit() else 2026)),
            "milb": r.get("milb") or {},
        })
    return out


def _keys(side: str):
    return _NOFV_PIT if side == "pit" else _NOFV_HIT


def fit_nofv(side: str):
    """Fit the no-FV production ridge + linear scale calibration on the full labeled matrix.
    Returns (ridge, a, b) where war = max(-2, a + b*ridge(feats))."""
    is_pit = side == "pit"
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = _prep([r for r in rows if bool(r.get("is_pitcher")) == is_pit], side)
    ridge = _fit_ridge(data, _keys(side))
    raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    return ridge, a, b


def _war(ridge, a, b, feats) -> float:
    return max(-2.0, a + b * _predict(ridge, feats))


def _grade(war: float, side: str) -> float:
    """war_pred -> provisional FV: linear below the KNEE, soft-compressed toward CEIL above it
    (order-preserving, so breakouts stay ranked while the magnitude is bounded)."""
    import math
    m = _GRADE_MAP[side]
    g = max(m["FLOOR"], m["BASE"] + m["SLOPE"] * war)
    knee, ceil, soft = m["KNEE"], m["CEIL"], m["SOFT"]
    if g > knee:
        g = knee + (ceil - knee) * (1.0 - math.exp(-(g - knee) / soft))
    return round(g, 1)


def _display_statline(mlbam, milb_block, side: str, org: str | None):
    """A frontend-shaped statline (the final pre-decision MiLB season line that drove the
    grade) so a provisional player's board row + detail page can show the production behind
    the grade. Best-effort: reads the warm milb_history cache (no network)."""
    import milb_history as mh
    season = milb_block.get("milb_season")
    level = milb_block.get("milb_level")
    if not (season and level and mlbam):
        return None
    group = "pitching" if side == "pit" else "hitting"
    try:
        rows = mh.player_index(int(season), group, fetch=False).get(int(mlbam)) or []
        row = mh.level_row(rows, level, group)
    except Exception:
        return None
    if not row:
        return None
    def fl(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    out = {"mlbam_id": mlbam, "level": level, "level_label": row.get("league"),
           "season": int(season), "is_prior_season": int(season) < CURRENT_SEASON, "org": org}
    if side == "pit":
        bf, ip, so, bb = fl(row.get("bf")), fl(row.get("ip")), fl(row.get("so")), fl(row.get("bb"))
        out.update({
            "is_pitcher": True, "ip": row.get("ip"), "era": row.get("era"), "games": row.get("g"),
            "tbf": int(bf) if bf else None,
            "k_pct": round(so / bf * 100, 1) if (so is not None and bf) else None,
            "bb_pct": round(bb / bf * 100, 1) if (bb is not None and bf) else None,
            "k_per_9": round(so / ip * 9, 2) if (so is not None and ip) else None,
            "bb_per_9": round(bb / ip * 9, 2) if (bb is not None and ip) else None,
        })
    else:
        pa, so, bb = fl(row.get("pa")), fl(row.get("so")), fl(row.get("bb"))
        slg, avg = fl(row.get("slg")), fl(row.get("avg"))
        out.update({
            "is_pitcher": False, "ab": row.get("ab"), "avg": row.get("avg"), "obp": row.get("obp"),
            "slg": row.get("slg"), "ops": row.get("ops"), "hr": row.get("hr"),
            "pa": int(pa) if pa else None,
            "k_pct": round(so / pa * 100, 1) if (so is not None and pa) else None,
            "bb_pct": round(bb / pa * 100, 1) if (bb is not None and pa) else None,
            "iso": round(slg - avg, 3) if (slg is not None and avg is not None) else None,
        })
    return out


def _career_row(r, side: str, org: str | None):
    """One season-and-level MiLB stat row in the site's career_stats shape (the detail-page
    stats table reads career_stats)."""
    def fl(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    base = {"season": r.get("season"), "level": r.get("level"), "level_label": r.get("league"),
            "org": org, "is_pitcher": side == "pit"}
    if side == "pit":
        bf, ip, so, bb = fl(r.get("bf")), fl(r.get("ip")), fl(r.get("so")), fl(r.get("bb"))
        base.update({
            "games": r.get("g"), "era": r.get("era"), "ip": r.get("ip"),
            "tbf": int(bf) if bf else None,
            "k_per_9": round(so / ip * 9, 2) if (so is not None and ip) else None,
            "bb_per_9": round(bb / ip * 9, 2) if (bb is not None and ip) else None,
            "k_pct": round(so / bf * 100, 1) if (so is not None and bf) else None,
            "bb_pct": round(bb / bf * 100, 1) if (bb is not None and bf) else None,
        })
    else:
        pa, so, bb = fl(r.get("pa")), fl(r.get("so")), fl(r.get("bb"))
        slg, avg = fl(r.get("slg")), fl(r.get("avg"))
        base.update({
            "games": None, "ab": r.get("ab"), "avg": r.get("avg"), "obp": r.get("obp"),
            "slg": r.get("slg"), "ops": r.get("ops"), "hr": r.get("hr"),
            "iso": round(slg - avg, 3) if (slg is not None and avg is not None) else None,
            "k_pct": round(so / pa * 100, 1) if (so is not None and pa) else None,
            "bb_pct": round(bb / pa * 100, 1) if (bb is not None and pa) else None,
        })
    return base


def _career_stats(mlbam, side: str, org: str | None, max_seasons: int = 5):
    """Multi-season MiLB stat rows (one per season-and-level) for the provisional player's
    detail-page stats table -- the production behind the grade. Best-effort, warm cache only."""
    import milb_history as mh
    group = "pitching" if side == "pit" else "hitting"
    out = []
    for season in range(CURRENT_SEASON, CURRENT_SEASON - max_seasons, -1):
        try:
            rows = mh.player_index(int(season), group, fetch=False).get(int(mlbam)) or []
        except Exception:
            continue
        for r in rows:
            lvl = r.get("level")
            if not lvl or lvl == "MLB":
                continue
            out.append(_career_row(r, side, org))
    # newest first, higher level first within a season (matches the site's ordering)
    _ord = {"AAA": 5, "AA": 4, "A+": 3, "A": 2, "CPX": 1, "DSL": 0}
    out.sort(key=lambda x: (-(x.get("season") or 0), -_ord.get(x.get("level"), -1)))
    return out


def _factors(ridge, feats, top: int = 3) -> list:
    """The largest standardized production contributions (WAR units), for the explainer."""
    contribs = []
    for k, mu, sd, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"]):
        c = w * ((feats.get(k, 0.0) - mu) / (sd or 1.0))
        if abs(c) >= 0.05:
            contribs.append((k, c))
    contribs.sort(key=lambda kc: -abs(kc[1]))
    return [{"label": _FACTOR_LABELS.get(k, k), "dir": "up" if c > 0 else "down",
             "mag": round(abs(c), 2)} for k, c in contribs[:top]]


def evaluate(persist: bool = True) -> dict:
    """Forward-chained rank validation vs realized WAR on the low-minors target cohort
    (the governance artifact -- proves the no-FV production model carries OOS signal where
    there is no consensus FV). Mirrors the flagship eval protocol."""
    out = {"generated_at": __import__("datetime").date.today().isoformat(),
           "model": "xFV ungraded (no-FV production ridge)", "by_side": {}}
    for side in ("hit", "pit"):
        is_pit = side == "pit"
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        data = _prep([r for r in rows if bool(r.get("is_pitcher")) == is_pit], side)
        keys = _keys(side)
        res = {}
        for label, levels, max_age in (("low_minors_age_le21", {"DSL", "CPX", "A"}, 21),
                                       ("all_levels", None, None)):
            P, T = [], []
            for yr in (2019, 2020, 2021, 2022, 2023):
                tr = [r for r in data if r["decision_year"] < yr]
                te = [r for r in data if r["decision_year"] == yr]
                if len(tr) < 60 or len(te) < 15:
                    continue
                rg = _fit_ridge(tr, keys)
                cal = _fit_linear_calibration([(_predict(rg, r["feats"]), r["target"]) for r in tr])
                a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
                for r in te:
                    m = r["milb"]
                    lvl = m.get("milb_level")
                    age = m.get("age")
                    if (levels is None or lvl in levels) and (max_age is None or age is None or age <= max_age):
                        P.append(_war(rg, a, b, r["feats"]))
                        T.append(r["target"])
            res[label] = {"n": len(P), "spearman_vs_realized_war": _spearman(P, T) if len(P) >= 8 else None}
        out["by_side"][side] = {"features": keys, "cohorts": res}
    out["note"] = ("Production-only (no consensus FV) ranks realized WAR among un-graded-analog "
                   "low-minors players; this is the signal the provisional ungraded grade rests on. "
                   "Hitters ~0.22 low-minors / ~0.31 all-levels; pitchers ~0.24 low-minors (level_rank "
                   "dropped). These are PROVISIONAL leading-indicator grades, not the flagship.")
    if persist:
        EVAL_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", EVAL_PATH)
    return out


def build(persist: bool = True) -> dict:
    """Score every UNGRADED roster player (data/rosters_by_org.json: fv_raw is None) that has
    real MiLB production, on the no-FV production model + capped grade map. Writes
    data/xfv_ungraded.json = {by_player, by_mlbam, meta}. Run AFTER the site export
    (rosters_by_org.json must exist)."""
    rost_path = DATA_DIR / "rosters_by_org.json"
    if not rost_path.exists():
        log.warning("rosters_by_org.json absent -- run the site export first; ungraded xFV empty")
        return {"players": 0}
    rosters = json.loads(rost_path.read_text(encoding="utf-8"))
    fits = {s: fit_nofv(s) for s in ("hit", "pit")}

    by_player, by_mlbam = {}, {}
    counts = {"hit": 0, "pit": 0, "no_production": 0, "no_mlbam": 0}
    for org, levels in rosters.items():
        for level, players in (levels or {}).items():
            if level == "MLB" or not isinstance(players, list):
                continue
            for p in players:
                if p.get("fv_raw") is not None:           # already source-graded -> flagship owns it
                    continue
                mid = p.get("mlbam_id")
                if not mid:
                    counts["no_mlbam"] += 1
                    continue
                side = "pit" if _is_pitcher_pos(p.get("position")) else "hit"
                m = _milb_features(mid, CURRENT_SEASON + 1, None, side)
                if not m or m.get("k_rel") is None:        # no usable MiLB production
                    counts["no_production"] += 1
                    continue
                ridge, a, b = fits[side]
                feats = _vec({"consensus_fv_raw": _GRADE_MAP[side]["BASE"],
                              "position": p.get("position"), "milb": m}, side)
                war = _war(ridge, a, b, feats)
                grade = _grade(war, side)
                pos = p.get("position")
                age = _f(p.get("age"))
                eta = _LEVEL_ETA.get(level, 4.0)
                is_pit = side == "pit"
                surplus = vf.expected_surplus_usd(grade, is_pit, pos, age=age, eta_years=eta)
                dist = vf.sv_distribution(grade, is_pit, pos, age=age, eta_years=eta) or {}
                pcts = dist.get("percentiles") or {}
                probs = vf.p_bucket_given_fv(grade, is_pit) or []
                pk = p.get("player_key") or f"mlbam_{mid}"
                statline = _display_statline(mid, m, side, p.get("team_name"))
                career_stats = _career_stats(mid, side, p.get("team_name"))
                def _mm(v):
                    return round(float(v), 1) if v is not None else None
                entry = {
                    "player_key": pk, "mlbam_id": mid, "name": p.get("fullName"),
                    "player_name": p.get("fullName"),
                    "side": "P" if is_pit else "H", "org": org, "level": level,
                    "position": pos, "age": age,
                    "statline": statline,
                    "career_stats": career_stats or None,
                    "xfv_grade": grade, "xfv_war_6yr": round(war, 2),
                    "consensus_fv": None,                     # ungraded -> no source FV
                    "surplus_mm": round(surplus / 1e6, 1) if surplus else None,
                    "p_bucket": {k: round(pv, 3) for k, pv in zip(_BUCKETS, probs)} if probs else None,
                    "dist": {"p10_mm": _mm(pcts.get("p10")), "p25_mm": _mm(pcts.get("p25")),
                             "p50_mm": _mm(pcts.get("p50")), "p75_mm": _mm(pcts.get("p75")),
                             "p90_mm": _mm(pcts.get("p90")), "mean_mm": _mm(dist.get("mean")),
                             "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None},
                    "band_p10_mm": _mm(pcts.get("p10")),
                    "band_p90_mm": _mm(pcts.get("p90")),
                    "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None,
                    "factors": _factors(ridge, feats),
                    "xfv_ungraded": True, "xfv_provisional": True,
                }
                by_player[pk] = entry
                by_mlbam[str(mid)] = grade
                counts[side] += 1

    grades = [e["xfv_grade"] for e in by_player.values()]
    grades.sort()
    def q(pp):
        return grades[min(len(grades) - 1, int(pp * (len(grades) - 1)))] if grades else None
    meta = {
        "generated_at": __import__("datetime").date.today().isoformat(),
        "n_players": len(by_player), "counts": counts,
        "grade_dist": {"median": round(statistics.median(grades), 1) if grades else None,
                       "p75": q(0.75), "p90": q(0.90), "p99": q(0.99), "max": max(grades) if grades else None,
                       "share_le_30": round(sum(1 for g in grades if g <= 30) / len(grades), 3) if grades else None,
                       "n_breakout_ge35": sum(1 for g in grades if g >= 35)},
        "grade_map": _GRADE_MAP, "eval": "data/xfv_ungraded_eval.json", "status": "provisional",
        "note": ("Production-only leading indicator for source-UNGRADED roster players. "
                 "Conventional capped FV map; most 20-30, breakouts to the cap. NOT the flagship xFV."),
    }
    out = {"meta": meta, "by_player": by_player, "by_mlbam": by_mlbam}
    if persist:
        OUT_PATH.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
        log.info("wrote %s (%d ungraded players: %d hit / %d pit)",
                 OUT_PATH, len(by_player), counts["hit"], counts["pit"])
    return meta


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--eval" in sys.argv:
        rep = evaluate()
        for side, blk in rep["by_side"].items():
            print(f"\n=== {side} (no-FV production model) ===")
            for c, v in blk["cohorts"].items():
                print(f"  {c:22s} n={v['n']:5d} Spearman vs realized WAR = {v['spearman_vs_realized_war']}")
    else:
        meta = build()
        print("ungraded xFV:", meta["n_players"], "players", json.dumps(meta["counts"]))
        print("grade dist:", json.dumps(meta["grade_dist"]))
