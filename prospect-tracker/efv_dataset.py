# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV Pass 1 -- leakage-clean as-of feature matrix + KM-censored labels (HITTERS).

This is the training SUBSTRATE for the eFV flagship model. It assembles one row per
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
Run: python efv_dataset.py
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

# --- E-STALE (2026-07-14): serve-time anchor-staleness decay -----------------
# ~7% of actively-scored players carry a consensus anchor (fv + tools) frozen at
# their LAST list appearance while stats/age move on. Training rows are built AT
# listing events (staleness 0 by construction), so the model cannot learn the
# discount - it must be applied at serving. Ground truth (tools/
# efv_stale_anchor_lab.py -> data/xfv_stale_anchor_eval.json, held-out-validated
# 2021-fit / 2022-validate): dropped-from-lists players bust ~91% vs ~55% for
# same-band re-listed controls and realize ~FV20-23 against FV35-45 anchors;
# the age gradient is flat, so time-since-listing alone drives the schedule.
# These constants MUST match the committed eval artifact (test-pinned, the
# overseas-factors pattern). Applied to the MODEL's fv input + the blend's
# consensus leg for ACTIVE rows only; the DISPLAYED consensus stays raw.
STALE_ANCHOR_RAMP_START_MO = 18     # inside normal annual list cadence: no decay
STALE_ANCHOR_RAMP_FULL_MO = 30      # fully "dropped" per the 18mo-relist study
STALE_ANCHOR_TERMINAL = {35: 10.0, 40: 10.0, 45: 10.0}   # FV points at full ramp


def _stale_anchor_discount(asof_iso, fv_raw, today=None):
    """FV-point decay of the model anchor for a live row. 0 inside the ramp
    start, linear to the band terminal at the ramp end. Bands without ground
    truth (outside 35-45) are never decayed."""
    if not asof_iso or fv_raw is None:
        return 0.0
    try:
        asof = date.fromisoformat(str(asof_iso)[:10])
    except ValueError:
        return 0.0
    months = ((today or date.today()) - asof).days / 30.44
    if months <= STALE_ANCHOR_RAMP_START_MO:
        return 0.0
    band = int(round(float(fv_raw) / 5.0) * 5)
    term = STALE_ANCHOR_TERMINAL.get(band)
    if not term:
        return 0.0
    frac = min(1.0, (months - STALE_ANCHOR_RAMP_START_MO)
               / (STALE_ANCHOR_RAMP_FULL_MO - STALE_ANCHOR_RAMP_START_MO))
    return term * frac

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


def live_matrix_path(side: str = "hit"):
    return DATA_DIR / ("xfv_live_pitcher_matrix.json" if side == "pit"
                       else "xfv_live_hitter_matrix.json")


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
    # As-of consensus-FV trajectory (momentum): net movement in consensus FV across
    # the player's snapshots up to AND INCLUDING the decision point. Leakage-free (only
    # points dated <= the decision date). A rising grade signals scouts catching up to
    # a breakout; orthogonal to the static FV level (the dominant feature).
    cutoff_date = pt.get("snapshot_date") or "9999"
    hist = sorted((p for p in (rec.get("points") or [])
                   if p.get("snapshot_date") and p["snapshot_date"] <= cutoff_date
                   and _f(p.get("consensus_fv_raw")) is not None),
                  key=lambda p: p["snapshot_date"])
    fv_trend = ((_f(hist[-1].get("consensus_fv_raw")) - _f(hist[0].get("consensus_fv_raw")))
                if len(hist) >= 2 else 0.0)
    out = {
        "consensus_fv_raw": _f(pt.get("consensus_fv_raw")),
        "consensus_fv_pre_shrinkage": _f(pt.get("consensus_fv_pre_shrinkage")),
        "fv_fangraphs": src_fv("fangraphs"),
        "fv_mlb_pipeline": src_fv("mlb_pipeline"),
        "n_sources": float(n_src),
        "fv_stddev": _f(pt.get("fv_stddev")),
        "fv_spread": _f(pt.get("fv_spread")),
        "fv_trend": fv_trend,
        "asof_date": pt.get("snapshot_date"),
    }
    for k in (_PIT_TOOLS if side == "pit" else _HIT_TOOLS):
        out[f"tool_{k}"] = _f(tools.get(k))
    return out


# Reliability shrink: a level-relative rate is shrunk toward 0 (league average) by its
# sample size, w = exposure / (exposure + K). A small-sample cup-of-coffee (e.g. a 3-PA
# AAA cameo with a fluky .98 OBP) collapses to ~0 instead of reading as elite; a full
# season is barely touched. Without this, cameos produced absurd grades (a 37-FV org bat
# read 53 eFV off a few AAA PA). K is roughly a quarter-season of exposure.
_K_REL_PA = 100.0
_K_REL_BF = 80.0

# Static per-group level-median-ish priors, used ONLY when neither the
# contemporaneous nor the prior-season same-level norm exists (e.g. a brand-new
# season's DSL pitching norms have not been computed yet). Without a fallback,
# _season_rates subtracts 0, so a RAW rate masquerades as a level-relative edge --
# the exact bug that spiked new-season DSL arms (a 45% DSL K% read as a +45% edge).
_NORM_PRIOR = {
    "pitching": {"k_pct": 0.22, "bb_pct": 0.095, "era": 4.30},
    "hitting":  {"k_pct": 0.22, "bb_pct": 0.085, "iso": 0.135, "obp": 0.330, "ops": 0.715},
}


def _resolved_norms(season, level, group):
    """Contemporaneous same-level norms, falling back to the prior season's
    same-level norms, then to a static per-group prior -- NEVER an empty dict. A
    missing norm made _season_rates treat a raw rate as a level-relative edge,
    which is why un-normed DSL/complex arms spiked to the grade ceiling."""
    n = mh.league_norms(season, level, group, fetch=False) or {}
    if not n.get("k_pct"):
        n = mh.league_norms(season - 1, level, group, fetch=False) or {}
    if not n.get("k_pct"):
        n = dict(_NORM_PRIOR.get(group, {}))
    return n


def _season_rates(row, norms, side: str):
    """Level-relative rate block + exposure (pa/bf) for one MiLB season, SAMPLE-SHRUNK.
    Side-specific: hitters k/bb/obp/iso vs level median; pitchers k/bb/era vs level median.
    Norms are season-and-level-specific (contemporaneous) so this is leakage-safe."""
    if side == "pit":
        bf = _f(row.get("bf")) or 0.0
        so, bb, era = _f(row.get("so")), _f(row.get("bb")), _f(row.get("era"))
        w = bf / (bf + _K_REL_BF) if bf else 0.0
        return {
            "k_rel": w * (((so / bf) - (norms.get("k_pct") or 0.0)) if so is not None and bf else 0.0),
            "bb_rel": w * (((bb / bf) - (norms.get("bb_pct") or 0.0)) if bb is not None and bf else 0.0),
            "era_rel": w * ((era - (norms.get("era") or 4.5)) if era is not None else 0.0),
            "exposure": bf, "rates_missing": 0.0 if bf else 1.0,
        }
    pa = _f(row.get("pa")) or 0.0
    so, bb = _f(row.get("so")), _f(row.get("bb"))
    slg, avg, obp, ops = _f(row.get("slg")), _f(row.get("avg")), _f(row.get("obp")), _f(row.get("ops"))
    iso = (slg - avg) if slg is not None and avg is not None else None
    w = pa / (pa + _K_REL_PA) if pa else 0.0
    return {
        "k_rel": w * (((so / pa) - (norms.get("k_pct") or 0.0)) if so is not None and pa else 0.0),
        "bb_rel": w * (((bb / pa) - (norms.get("bb_pct") or 0.0)) if bb is not None and pa else 0.0),
        "iso_rel": w * ((iso - (norms.get("iso") or 0.0)) if iso is not None else 0.0),
        # Phase-1 sweep: peak-MiLB OBP is the strongest hitter edge BEYOND FV (+0.16
        # partial), under-priced by scouts. Not derivable from k/bb/iso (hits-on-base).
        "obp_rel": w * ((obp - (norms.get("obp") or 0.0)) if obp is not None and norms.get("obp") else 0.0),
        # RPS+ family: full OPS vs the level mean (the site's level-relative production
        # metric). Adds the batting-average / contact-quality component beyond OBP + ISO.
        "ops_rel": w * ((ops - (norms.get("ops") or 0.0)) if ops is not None and norms.get("ops") else 0.0),
        "exposure": pa, "rates_missing": 0.0 if pa else 1.0,
    }


def _milb_features(mlbam, decision_year, birth_date, side: str = "hit"):
    """Translated production from the MiLB ladder strictly before the decision year
    (StatsAPI; season-and-level norms are contemporaneous = leakage-safe). Returns the
    FINAL pre-decision season's rates (the current-state read) PLUS multi-season PEAK
    production + season count (a fuller read than one snapshot -- a player who posted an
    elite K-BB% two levels ago carries that signal). Mirrors prospect_path._features +
    a clean age-rel-level."""
    if not mlbam:
        return None
    group = "pitching" if side == "pit" else "hitting"
    minpa = 60 if side == "pit" else 50
    seasons = []
    for season in range(decision_year - 1, 2013, -1):
        rows = [r for r in (mh.player_index(season, group).get(int(mlbam)) or [])
                if r.get("level") != "MLB"]
        if not rows:
            continue
        # PRIMARY level = the highest level where the player got meaningful exposure that
        # season (not a cup-of-coffee). Sets level_rank + age_rel_level so a cameo can't
        # make a 19-yo look like an established AAA bat. Rates come from this level too,
        # and are sample-shrunk on top.
        present = sorted({r.get("level") for r in rows if r.get("level") in _LEVEL_RANK},
                         key=lambda lv: -_LEVEL_RANK[lv])
        if not present:
            continue
        level, row = None, None
        for lv in present:
            lr = mh.level_row(rows, lv, group)
            exp = (_f(lr.get("bf")) if side == "pit" else _f(lr.get("pa"))) or 0.0
            if exp >= minpa:
                level, row = lv, lr
                break
        if level is None:
            # No level cleared the exposure threshold -> use the MOST-EXPOSED level (the
            # player's real home), NOT the highest. A cup-of-coffee at a high level (e.g. an
            # 18-yo's 3-PA AA cameo) must not set level_rank / age_rel_level as if he were
            # established there: those level features are NOT exposure-shrunk the way the rate
            # features are, so a cameo at a high level otherwise manufactures a huge
            # young-for-level + level-reached boost off zero real playing time.
            def _lv_exp(lv):
                lr = mh.level_row(rows, lv, group)
                return (_f(lr.get("bf")) if side == "pit" else _f(lr.get("pa"))) or 0.0
            level = max(present, key=_lv_exp)
            row = mh.level_row(rows, level, group)
        norms = _resolved_norms(season, level, group)
        rates = _season_rates(row, norms, side)
        # Age-for-level uses the integer StatsAPI "baseball age" (age at the season's July 1).
        # Decimal precision from birth_date was tested for the model and slightly HURT OOS rank
        # (debuted 0.3308 -> 0.3291): the standard baseball age is the cleaner basis here. The
        # user-facing CURRENT age is shown as a decimal site-wide (a separate, display concern).
        age = _f(row.get("age"))
        if age is None and birth_date:
            try:
                b = date.fromisoformat(birth_date[:10])
                age = round((date(season, 6, 30) - b).days / 365.25, 1)
            except ValueError:
                age = None
        rates.update({"season": season, "level": level,
                      "level_rank": float(_LEVEL_RANK[level]), "age": age})
        seasons.append(rates)
    if not seasons:
        return None

    final = seasons[0]                 # most recent (descending loop)
    level, age = final["level"], final["age"]
    # age-relative-to-level, CAPPED to +/-3.5: the model term is linear, so an extreme
    # (a 19-yo cup-of-coffee in AAA -> -5) would over-extrapolate the young-for-level boost.
    age_rel = (age - _TYPICAL_LEVEL_AGE[level]) if age is not None else None
    if age_rel is not None:
        age_rel = max(-3.5, min(3.5, age_rel))
    base = {
        "milb_season": final["season"], "milb_level": level,
        "level_rank": final["level_rank"],
        "stale": float(decision_year - 1 - final["season"]),
        "age": age if age is not None else 23.0,
        "age_missing": 1.0 if age is None else 0.0,
        "age_rel_level": age_rel if age_rel is not None else 0.0,
        "n_milb_seasons": float(len(seasons)),
    }
    keep = ("k_rel", "bb_rel", "era_rel", "rates_missing") if side == "pit" \
        else ("k_rel", "bb_rel", "iso_rel", "obp_rel", "ops_rel", "rates_missing")
    base.update({k: final[k] for k in keep})

    # Multi-season PEAK across exposure-qualified seasons (best sustained production,
    # not just the latest line). Direction = the productive extreme of each rate.
    minpa = 60 if side == "pit" else 50
    qual = [s for s in seasons if (s.get("exposure") or 0) >= minpa] or seasons
    if side == "pit":
        base["peak_k_rel"] = max(s["k_rel"] for s in qual)
        base["peak_bb_rel"] = min(s["bb_rel"] for s in qual)   # fewer walks = better
    else:
        base["peak_obp_rel"] = max(s["obp_rel"] for s in qual)
        base["peak_k_rel"] = min(s["k_rel"] for s in qual)     # fewer Ks = better
        base["peak_iso_rel"] = max(s["iso_rel"] for s in qual)
        base["peak_ops_rel"] = max(s["ops_rel"] for s in qual)
    # A2: production TRAJECTORY -- latest vs earliest level-relative production (the primary
    # rate per side). Positive = improving toward the decision point. Leakage-safe (all
    # pre-decision). 0 when only one season is on record.
    metric = "k_rel" if side == "pit" else "ops_rel"
    base["prod_trend"] = (final[metric] - seasons[-1][metric]) if len(seasons) >= 2 else 0.0
    return base


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
                f"SELECT player_key, method, pick_overall, bonus_usd, year FROM acquisitions "
                f"WHERE player_key IN ({ph})", pk):
            acq[r["player_key"]] = {"pick_overall": r["pick_overall"],
                                    "bonus_usd": r["bonus_usd"], "method": r["method"],
                                    "year": r["year"]}
        for r in con.execute(
                f"SELECT player_key, since FROM il_history WHERE player_key IN ({ph})", pk):
            il.setdefault(r["player_key"], []).append(r["since"])
    return acq, il


def _cohort_flags(method, year, birth_date) -> tuple[float, float]:
    """Acquisition-cohort indicators used as model features. is_ifa = signed as an
    international free agent; is_college = drafted out of college (age>=21 in the draft
    year, the leakage-free split the eFV sweep validated). HS draftees / unknown are (0,0).
    The ridge re-centers each cohort's intercept -> sharper CROSS-tier ordering (OOS gain:
    hit +0.024, pit cohort-interactions +0.011)."""
    is_ifa = 1.0 if method == "international_fa" else 0.0
    is_college = 0.0
    if method == "draft" and year and birth_date:
        try:
            if int(year) - int(str(birth_date)[:4]) >= 21:
                is_college = 1.0
        except (ValueError, TypeError):
            pass
    return is_ifa, is_college


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
        r["is_ifa"], r["is_college"] = _cohort_flags(a.get("method"), a.get("year"), r.get("birth_date"))
        r.update(_injury_features(il.get(r["player_key"]), r["cutoff"]))

    return rows, acct


# ---------------------------------------------------------------------------
# live cohort -- the CURRENT active prospect board (no labels; for scoring)
# ---------------------------------------------------------------------------

def build_live_matrix(side: str = "hit"):
    """Feature rows for the CURRENT active prospect board so the trained model can
    score the players the site actually shows. Same as-of feature construction as
    build_matrix (the SAME _prior_features / _milb_features / sidecar helpers) but
    sourced from the live board (data/timeseries.json `players[]`), with the
    decision point = the latest snapshot (cutoff=None) and NO outcome label.

    Reads timeseries.json (the export output) so the eFV grades line up exactly with
    the consensus FV the site displays. Captures age + eta_years + the engine's
    consensus surplus so the scorer can price eFV vs consensus on identical timing.
    Run AFTER the site export (run_monthly / build_site) has written timeseries.json.
    """
    is_pit = side == "pit"
    ts_path = DATA_DIR / "timeseries.json"
    if not ts_path.exists():
        log.warning("timeseries.json absent -- run the site export first; live matrix empty")
        return [], {"live_seen": 0, "live_side": 0, "live_kept": 0, "live_no_fv": 0}

    payload = json.loads(ts_path.read_text(encoding="utf-8"))
    players = payload.get("players") or []
    acct = {"live_seen": 0, "live_side": 0, "live_kept": 0, "live_no_fv": 0}
    rows = []
    for rec in players:
        acct["live_seen"] += 1
        pk = rec.get("player_key")
        if not pk or not _side_match(rec, side):
            continue
        acct["live_side"] += 1
        pt = _asof_point(rec, None)        # latest snapshot = current grade
        if pt is None or _f(pt.get("consensus_fv_raw")) is None:
            acct["live_no_fv"] += 1
            continue
        surplus = rec.get("surplus") or {}
        il = rec.get("il_status") or {}
        hp = rec.get("health_profile") or {}
        row = {"player_key": pk, "kind": "active", "debut_year": None,
               "is_pitcher": is_pit, "cutoff": None,
               "mlbam_id": rec.get("mlbam_id"), "birth_date": rec.get("birth_date"),
               "position": rec.get("position"),
               "age_now": _f(rec.get("age")),
               "eta_years": _f(surplus.get("eta_years")),
               "consensus_surplus_mm": _f(surplus.get("value_mm")),
               # current injury signals (for the live injury penalty)
               "il_on": 1 if il.get("is_on_il") else 0,
               "il_type": il.get("type"),
               "il_days_12mo": _f(hp.get("il_days_12mo")) or 0.0,
               "il_stints_12mo": _f(hp.get("il_stints_12mo")) or 0.0,
               "is_post_tj": bool(hp.get("is_post_tj")),
               # Statcast+ (batted-ball quality / Stuff+) -- current-state only, upper-level;
               # a live overlay tilt (no historical depth to train on). 100 = average.
               "statcast_plus": _f(rec.get("statcast_plus"))}
        row.update(_prior_features(rec, pt, side))
        # E-STALE: decay the MODEL anchor for long-unlisted players (the Nathan
        # Hickey class: FV frozen at a 2024 list while stats/age are current).
        # fv_effective feeds _vec's fv feature + the scorer's consensus blend
        # leg; consensus_fv_raw is untouched so every DISPLAY of consensus
        # stays the true consensus.
        _disc = _stale_anchor_discount(row.get("asof_date"), row.get("consensus_fv_raw"))
        row["anchor_stale_discount"] = round(_disc, 2)
        row["fv_effective"] = round(row["consensus_fv_raw"] - _disc, 2) if _disc else row["consensus_fv_raw"]
        # LIVE scoring includes the CURRENT season (no leakage -- current production IS the
        # signal). decision_year = CURRENT_SEASON+1 so _milb_features' range starts at the
        # current year. (Training stays strictly pre-outcome.) Without this, a 2026 breakout
        # like Arias's .990 OPS was ignored and stale 2025 stats drove the grade.
        row["milb"] = _milb_features(rec.get("mlbam_id"), CURRENT_SEASON + 1,
                                     rec.get("birth_date"), side)
        rows.append(row)
        acct["live_kept"] += 1

    acq, il = _load_sidecars({r["player_key"] for r in rows})
    for r in rows:
        a = acq.get(r["player_key"]) or {}
        r["pick_overall"] = a.get("pick_overall")
        r["bonus_usd"] = a.get("bonus_usd")
        r["is_ifa"], r["is_college"] = _cohort_flags(a.get("method"), a.get("year"), r.get("birth_date"))
        r.update(_injury_features(il.get(r["player_key"]), None))
    return rows, acct


def build_live(persist: bool = True, side: str = "hit") -> dict:
    rows, acct = build_live_matrix(side)
    rep = {"generated_at": date.today().isoformat(),
           "scope": f"LIVE {'PITCHERS' if side == 'pit' else 'HITTERS'} (active board)",
           "accounting": acct, "n_rows": len(rows),
           "milb_coverage": _coverage(rows, "level_rank", sub="milb"),
           "mlbam_coverage": _coverage(rows, "mlbam_id")}
    if persist:
        live_matrix_path(side).write_text(json.dumps(rows, indent=0), encoding="utf-8")
        log.info("wrote %s (%d rows)", live_matrix_path(side), len(rows))
    return rep


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
        "scope": (f"{'PITCHERS' if side == 'pit' else 'HITTERS'}; debut "
                  f"{DEBUT_YEARS[0]}-{DEBUT_YEARS[-1]} + never-MLB bust pool"),
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
