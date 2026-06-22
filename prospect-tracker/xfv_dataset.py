# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xFV Pass 1 -- leakage-clean as-of feature matrix + KM-censored labels (HITTERS).

This is the training SUBSTRATE for the xFV flagship model. It assembles one row per
resolved/censored prospect with features built strictly as-of a pre-outcome decision
point, attaches a first-6-MLB-season bWAR label with censoring handling, and reproduces
the consensus-FV-only baseline that the model must match or beat. NO MODEL IS FIT HERE.

Design (per docs/xfv-phase1-plan.md, owner sign-off 2026-06-21):
  COHORT     HITTERS only. Debuted (debuts.json) debut years 2017-2023 + the bust pool
             (inactive.json, never reached MLB). Busts are real 0-WAR outcomes, kept in
             to avoid survivorship bias (the prospect_path / source_backtest house rule).
  VINTAGE    consensus FV strictly pre-outcome: the LATEST points[] entry dated before
             the debut date (debuted) or the player's final prospect point (bust). Uses
             consensus_fv_raw / consensus_fv_pre_shrinkage -- never the shrunk grade,
             never fv_close/fv_high (whole-history candlesticks that peek forward).
  FEATURES   prior backbone (consensus FV, per-source FG/MLB-Pipeline FV, n_sources),
             the hit-tool + tool vector, scout disagreement (fv_stddev/spread -- kept
             though the Phase-1 sweep showed ~0 outcome signal), translated production
             from the StatsAPI ladder (milb_history, final pre-decision MiLB season --
             season-specific norms are contemporaneous by construction = leakage-safe):
             age-rel-level, level rank, staleness, league-relative k/bb/iso; plus draft
             pick/bonus and pre-decision IL history. NO Statcast (no historical depth;
             Tier-2 overlay is a later pass).
  TARGET     first-6-MLB-season summed bWAR (career_war seasons debut..debut+5).
  CENSORING  KM-from-the-start (owner call): 2017-2020 debuts resolve fully (window ends
             <= 2025); 2021-2023 debuts are right-censored -- carried with a rate
             projection of the unobserved tail + an observed-fraction weight. Busts = 0.
             We emit BOTH the resolved-only and the censored-included targets so the
             baseline's sensitivity to the censoring assumption is measurable.
  BASELINE   consensus_fv_raw rank vs realized WAR (Spearman) -- THE bar. Reported for
             debuted-only, full-pool resolved, and KM-censored full pool.

Artifacts: data/xfv_hitter_matrix.json (the matrix) + data/xfv_dataset_report.json.
Run: python xfv_dataset.py
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

import milb_history as mh
import storage
from prospect_path import _spearman   # reuse the house hand-rolled rank corr

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
MATRIX_PATH = DATA_DIR / "xfv_hitter_matrix.json"
REPORT_PATH = DATA_DIR / "xfv_dataset_report.json"

DEBUT_YEARS = tuple(range(2011, 2024))      # 2011-2023 (2011-2016 via the MLB Pipeline
#   backfill, now in debuts.json after the rebuild — captured directly, no augment needed)
RESOLVED_THROUGH = 2025                      # last fully-played season
TARGET_SEASONS = 6
CURRENT_SEASON = 2026
_LEVEL_RANK = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
# contemporaneous-ish typical age by level (leakage-free static prior for age-rel-level;
# the modeling pass refines this with frozen empirical level-season medians).
_TYPICAL_LEVEL_AGE = {"DSL": 18.0, "CPX": 19.0, "A": 20.0, "A+": 21.0,
                      "AA": 22.5, "AAA": 24.0}

_HIT_TOOLS = ("hit", "game_pwr", "raw_pwr", "speed", "field", "throw")
_PIT_TOOLS = ("fb", "sl", "cb", "ch", "cmd")


def matrix_path(side: str = "hit"):
    return DATA_DIR / ("xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json")


def report_path(side: str = "hit"):
    return DATA_DIR / ("xfv_pitcher_dataset_report.json" if side == "pit"
                       else "xfv_dataset_report.json")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rec_is_pitcher(rec) -> bool:
    sl = rec.get("statline") or {}
    if sl.get("is_pitcher") is True:
        return True
    if sl.get("is_pitcher") is False:
        return False
    pos = (rec.get("position") or "").upper()
    return any(p in pos for p in ("RHP", "LHP", "SP", "RP")) or pos == "P"


def _side_match(rec, side: str) -> bool:
    return _rec_is_pitcher(rec) if side == "pit" else not _rec_is_pitcher(rec)


def _asof_point(rec, cutoff: str | None):
    """Latest points[] entry strictly before cutoff (debuted) or the final point
    (bust, cutoff=None). Returns the point dict or None."""
    pts = [p for p in (rec.get("points") or []) if p.get("snapshot_date")]
    if not pts:
        return None
    pts.sort(key=lambda p: p["snapshot_date"])
    if cutoff is None:
        return pts[-1]
    elig = [p for p in pts if p["snapshot_date"] < cutoff]
    return elig[-1] if elig else None


def _prior_features(rec, pt, side: str = "hit") -> dict:
    """Backbone prior + tools + disagreement, all as-of the decision point."""
    per = pt.get("per_source") or {}
    def src_fv(s):
        return _f((per.get(s) or {}).get("fv_published"))
    n_src = sum(1 for s, v in per.items()
                if s != "auto_detect" and _f(v.get("fv_published")) is not None)
    tools = pt.get("tools_consensus") or {}
    out = {
        "consensus_fv_raw": _f(pt.get("consensus_fv_raw")),
        "consensus_fv_pre_shrinkage": _f(pt.get("consensus_fv_pre_shrinkage")),
        "fv_fangraphs": src_fv("fangraphs"),
        "fv_mlb_pipeline": src_fv("mlb_pipeline"),
        "n_sources": float(n_src),
        "fv_stddev": _f(pt.get("fv_stddev")),
        "fv_spread": _f(pt.get("fv_spread")),
        "asof_date": pt.get("snapshot_date"),
    }
    for k in (_PIT_TOOLS if side == "pit" else _HIT_TOOLS):
        out[f"tool_{k}"] = _f(tools.get(k))
    return out


def _milb_features(mlbam, decision_year, birth_date, side: str = "hit"):
    """Translated production from the final MiLB season strictly before the decision
    year (StatsAPI ladder; season-specific norms = contemporaneous = leakage-safe).
    Mirrors prospect_path._features + a clean age-rel-level. Side-specific rates:
    hitters k/bb/iso vs level median; pitchers k/bb/era vs level median."""
    if not mlbam:
        return None
    group = "pitching" if side == "pit" else "hitting"
    for season in range(decision_year - 1, 2013, -1):
        rows = [r for r in (mh.player_index(season, group).get(int(mlbam)) or [])
                if r.get("level") != "MLB"]
        if not rows:
            continue
        level = mh.highest_level(rows)
        if level not in _LEVEL_RANK:
            continue
        row = mh.level_row(rows, level, group)
        norms = mh.league_norms(season, level, group, fetch=False) or {}
        age = _f(row.get("age"))
        if age is None and birth_date:
            try:
                b = date.fromisoformat(birth_date[:10])
                age = round((date(season, 6, 30) - b).days / 365.25, 1)
            except ValueError:
                age = None
        age_rel = (age - _TYPICAL_LEVEL_AGE[level]) if age is not None else None
        base = {
            "milb_season": season,
            "milb_level": level,
            "level_rank": float(_LEVEL_RANK[level]),
            "stale": float(decision_year - 1 - season),
            "age": age if age is not None else 23.0,
            "age_missing": 1.0 if age is None else 0.0,
            "age_rel_level": age_rel if age_rel is not None else 0.0,
        }
        if side == "pit":
            bf = _f(row.get("bf")) or 0.0
            so, bb = _f(row.get("so")), _f(row.get("bb"))
            era = _f(row.get("era"))
            base.update({
                "k_rel": ((so / bf) - (norms.get("k_pct") or 0.0)) if so is not None and bf else 0.0,
                "bb_rel": ((bb / bf) - (norms.get("bb_pct") or 0.0)) if bb is not None and bf else 0.0,
                "era_rel": (era - (norms.get("era") or 4.5)) if era is not None else 0.0,
                "rates_missing": 0.0 if bf else 1.0,
            })
        else:
            pa = _f(row.get("pa")) or 0.0
            so, bb = _f(row.get("so")), _f(row.get("bb"))
            slg, avg = _f(row.get("slg")), _f(row.get("avg"))
            iso = (slg - avg) if slg is not None and avg is not None else None
            base.update({
                "k_rel": ((so / pa) - (norms.get("k_pct") or 0.0)) if so is not None and pa else 0.0,
                "bb_rel": ((bb / pa) - (norms.get("bb_pct") or 0.0)) if bb is not None and pa else 0.0,
                "iso_rel": (iso - (norms.get("iso") or 0.0)) if iso is not None else 0.0,
                "rates_missing": 0.0 if pa else 1.0,
            })
        return base
    return None


def _label_6yr(seasons: dict, debut_year: int):
    """(target_resolved, target_censored, censored_flag, weight, observed_seasons).
    seasons: {int year: war}."""
    window = [debut_year + i for i in range(TARGET_SEASONS)]
    observed = [y for y in window if y <= RESOLVED_THROUGH]
    obs_sum = round(sum(seasons.get(y, 0.0) for y in observed), 3)
    n_obs = len(observed)
    full_resolved = (debut_year + TARGET_SEASONS - 1) <= RESOLVED_THROUGH
    if full_resolved:
        return obs_sum, obs_sum, False, 1.0, n_obs
    # right-censored: project the unobserved tail at the observed per-season rate
    rate = obs_sum / n_obs if n_obs else 0.0
    n_missing = TARGET_SEASONS - n_obs
    censored_target = round(obs_sum + n_missing * rate, 3)
    weight = round(n_obs / TARGET_SEASONS, 3)
    return obs_sum, censored_target, True, weight, n_obs


# ---------------------------------------------------------------------------
# join sidecars (draft / bonus / injury) from the DB
# ---------------------------------------------------------------------------

def _load_sidecars(player_keys: set[str]):
    acq, il = {}, {}
    with storage.connect() as con:
        ph = ",".join("?" for _ in player_keys)
        pk = tuple(player_keys)
        for r in con.execute(
                f"SELECT player_key, method, pick_overall, bonus_usd FROM acquisitions "
                f"WHERE player_key IN ({ph})", pk):
            acq[r["player_key"]] = {"pick_overall": r["pick_overall"],
                                    "bonus_usd": r["bonus_usd"], "method": r["method"]}
        for r in con.execute(
                f"SELECT player_key, since FROM il_history WHERE player_key IN ({ph})", pk):
            il.setdefault(r["player_key"], []).append(r["since"])
    return acq, il


def _injury_features(il_dates, cutoff: str | None):
    """IL stints recorded strictly before the decision date."""
    if not il_dates:
        return {"il_stints_pre": 0.0, "il_any_pre": 0.0}
    pre = [d for d in il_dates if d and (cutoff is None or d < cutoff)]
    return {"il_stints_pre": float(len(pre)), "il_any_pre": 1.0 if pre else 0.0}


# ---------------------------------------------------------------------------
# cohort
# ---------------------------------------------------------------------------

def build_matrix(side: str = "hit"):
    is_pit = side == "pit"
    debuts = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    inact = json.loads((DATA_DIR / "inactive.json").read_text(encoding="utf-8"))

    with storage.connect() as con:
        cw = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}

    acct = {"debuted_seen": 0, "debuted_hitter": 0, "debuted_no_pre_fv": 0,
            "debuted_no_war": 0, "debuted_kept": 0,
            "bust_seen": 0, "bust_hitter": 0, "bust_no_fv": 0, "bust_kept": 0,
            "bust_recent_flagged": 0}
    rows = []

    # --- debuted ---
    for rec in debuts:
        acct["debuted_seen"] += 1
        pk, dd, mlbam = rec.get("player_key"), rec.get("debut_date"), rec.get("mlbam_id")
        if not (pk and dd):
            continue
        dy = int(dd[:4])
        if dy not in DEBUT_YEARS or not _side_match(rec, side):
            continue
        acct["debuted_hitter"] += 1
        pt = _asof_point(rec, dd)
        if pt is None or _f(pt.get("consensus_fv_raw")) is None:
            acct["debuted_no_pre_fv"] += 1
            continue
        seasons = cw.get(pk)
        if not seasons:
            acct["debuted_no_war"] += 1
            continue
        t_res, t_cens, cflag, w, n_obs = _label_6yr(seasons, dy)
        row = {"player_key": pk, "kind": "debuted", "debut_year": dy,
               "is_pitcher": is_pit, "cutoff": dd,
               "target_resolved": t_res, "target_censored": t_cens,
               "censored": cflag, "weight": w, "observed_seasons": n_obs,
               "mlbam_id": mlbam, "birth_date": rec.get("birth_date"),
               "position": rec.get("position")}
        row.update(_prior_features(rec, pt, side))
        row["milb"] = _milb_features(mlbam, dy, rec.get("birth_date"), side)
        acct["debuted_kept"] += 1
        rows.append(row)

    # --- busts (never reached MLB) ---
    for rec in inact:
        acct["bust_seen"] += 1
        pk = rec.get("player_key")
        if not pk or rec.get("debut_date"):     # debut_date set => not a never-MLB bust
            continue
        if not _side_match(rec, side):
            continue
        acct["bust_hitter"] += 1
        pt = _asof_point(rec, None)
        if pt is None or _f(pt.get("consensus_fv_raw")) is None:
            acct["bust_no_fv"] += 1
            continue
        last_date = pt.get("snapshot_date") or ""
        recent = last_date[:4] >= "2024"     # may still be developing
        if recent:
            acct["bust_recent_flagged"] += 1
        cutoff = (last_date or None)
        row = {"player_key": pk, "kind": "bust", "debut_year": None,
               "is_pitcher": is_pit, "cutoff": cutoff,
               "target_resolved": 0.0, "target_censored": 0.0,
               "censored": False, "weight": 0.5 if recent else 1.0,
               "observed_seasons": TARGET_SEASONS, "bust_recent": recent,
               "mlbam_id": rec.get("mlbam_id"), "birth_date": rec.get("birth_date"),
               "position": rec.get("position")}
        row.update(_prior_features(rec, pt, side))
        dec_year = (int(last_date[:4]) + 1) if last_date[:4].isdigit() else CURRENT_SEASON
        row["milb"] = _milb_features(rec.get("mlbam_id"), dec_year, rec.get("birth_date"), side)
        acct["bust_kept"] += 1
        rows.append(row)

    # sidecars
    acq, il = _load_sidecars({r["player_key"] for r in rows})
    for r in rows:
        a = acq.get(r["player_key"]) or {}
        r["pick_overall"] = a.get("pick_overall")
        r["bonus_usd"] = a.get("bonus_usd")
        r.update(_injury_features(il.get(r["player_key"]), r["cutoff"]))

    return rows, acct


# ---------------------------------------------------------------------------
# coverage + baseline
# ---------------------------------------------------------------------------

def _coverage(rows, field, sub=None):
    n = 0
    for r in rows:
        v = (r.get(sub) or {}).get(field) if sub else r.get(field)
        if v is not None:
            n += 1
    return n


def _baseline(rows, target_key, fv_key="consensus_fv_raw"):
    xs, ys = [], []
    for r in rows:
        fv, t = r.get(fv_key), r.get(target_key)
        if fv is not None and t is not None:
            xs.append(fv); ys.append(t)
    return {"n": len(xs), "spearman": _spearman(xs, ys) if len(xs) >= 8 else None}


def run(persist: bool = True, side: str = "hit") -> dict:
    rows, acct = build_matrix(side)
    debuted = [r for r in rows if r["kind"] == "debuted"]
    busts = [r for r in rows if r["kind"] == "bust"]
    resolved_debuted = [r for r in debuted if not r["censored"]]
    full_resolved = resolved_debuted + [b for b in busts if not b.get("bust_recent")]
    full_censored = debuted + [b for b in busts if not b.get("bust_recent")]

    feat_cov = {k: f"{_coverage(rows, k)}/{len(rows)}"
                for k in ("consensus_fv_raw", "fv_fangraphs", "fv_mlb_pipeline",
                          "fv_stddev", "tool_hit", "tool_game_pwr", "pick_overall",
                          "bonus_usd")}
    milb_cov = {k: f"{_coverage(rows, k, sub='milb')}/{len(rows)}"
                for k in ("level_rank", "age_rel_level", "k_rel",
                          "era_rel" if side == "pit" else "iso_rel")}

    baselines = {
        "debuted_only_resolved": _baseline(resolved_debuted, "target_resolved"),
        "full_pool_resolved": _baseline(full_resolved, "target_resolved"),
        "full_pool_km_censored": _baseline(full_censored, "target_censored"),
        "debuted_km_censored": _baseline(debuted, "target_censored"),
    }
    # WAR distribution sanity
    res_t = sorted(r["target_resolved"] for r in resolved_debuted)
    def pct(v, p):
        return round(v[int(p * (len(v) - 1))], 2) if v else None

    report = {
        "generated_at": date.today().isoformat(),
        "scope": f"{'PITCHERS' if side == 'pit' else 'HITTERS'}; debut 2017-2023 + never-MLB bust pool",
        "target": f"first-{TARGET_SEASONS}-season summed bWAR; resolved<= {RESOLVED_THROUGH}",
        "no_model": True,
        "accounting": acct,
        "counts": {
            "rows_total": len(rows), "debuted": len(debuted), "busts": len(busts),
            "resolved_debuted": len(resolved_debuted),
            "censored_debuted": len(debuted) - len(resolved_debuted),
            "bust_recent_excluded_from_label": acct["bust_recent_flagged"],
        },
        "feature_coverage": feat_cov,
        "milb_feature_coverage": milb_cov,
        "war_distribution_resolved_debuted": {
            "n": len(res_t), "p10": pct(res_t, .10), "p50": pct(res_t, .50),
            "p90": pct(res_t, .90), "mean": round(statistics.mean(res_t), 2) if res_t else None,
            "max": round(max(res_t), 2) if res_t else None,
            "pct_under_0.5": round(sum(1 for v in res_t if v < 0.5) / len(res_t), 3) if res_t else None,
        },
        "baseline_consensus_fv_spearman": baselines,
        "baseline_note": ("THE bar. consensus_fv_raw rank vs realized first-6yr bWAR. "
                          "debuted-only ~ the 0.38 Phase-1 sweep figure; full-pool dilutes "
                          "with busts. Sensitivity = resolved vs KM-censored."),
    }
    if persist:
        mp, rp = matrix_path(side), report_path(side)
        mp.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        rp.write_text(json.dumps(report, indent=1), encoding="utf-8")
        log.info("wrote %s (%d rows) + %s", mp, len(rows), rp)
    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _side = "pit" if "--pit" in sys.argv else "hit"
    rep = run(side=_side)
    print("accounting:", json.dumps(rep["accounting"]))
    print("counts:", json.dumps(rep["counts"]))
    print("feature coverage:", json.dumps(rep["feature_coverage"]))
    print("milb coverage:", json.dumps(rep["milb_feature_coverage"]))
    print("WAR dist (resolved debuted):", json.dumps(rep["war_distribution_resolved_debuted"]))
    print("BASELINE consensus-FV Spearman:")
    for k, v in rep["baseline_consensus_fv_spearman"].items():
        print(f"  {k:28s} n={v['n']:5d}  spearman={v['spearman']}")
