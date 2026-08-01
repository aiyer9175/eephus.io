# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
bayes_trade_value.py — Bayesian trade value engine.

Mathematical model
==================

For each player we compute:

    trade_value = (posterior_surplus × scarcity × dev_curve
                   + defensive_floor
                   + options_premium
                   + rule5_urgency)
                  × (1 − worriedness_discount)

All formulations are marked with § labels keyed to the config block:

  § PRIOR      FV-based surplus from value_framework.surplus_value_mm()
               Precision = base × pedigree × age_for_level_buffer × source_weight
  § LIKELIHOOD Rolling-weighted performance signal (recent / season windows)
               Observation noise ∝ base_noise / sqrt(sample / ref_sample)
  § KALMAN     Gaussian conjugate update (exact for Gaussian prior + likelihood):
                 K         = prior_prec / (prior_prec + obs_noise)
                 posterior  = prior_mean + K × (obs_signal − prior_mean)
               For debuted players, value_framework.debuted_player_value() runs
               the same update on career WAR vs. FV prior; we layer additional
               adjustments (rolling recency, scarcity, floor) on top.
  § SCARCITY   Positional scarcity multiplier on posterior surplus:
               C highest (1.22), DH baseline (0.95). Captures thin-supply
               premium above what WAR positional adjustments already encode.
  § FLOOR      Additive defensive-floor WAR → $M at premium positions.
               An elite defensive catcher contributes +2–3 WAR from defense
               alone; their distribution is left-truncated (non-Gaussian).
  § FLASH      Bimodal mixture for "all potential" players (fv_close_plus=True):
                 P(value) = p_click × N(μ_elite, σ) + (1−p_click) × N(μ_floor, σ)
               Peak-window performance events update p_click upward.
  § WORRY      Worriedness = P(skills_decay | trajectory):
               - approach_decay   (K%↑, BB%↓, chase%↑) — most concerning
               - contact_quality  (EV↓, barrel%↓, stable approach) — mechanical
               Age-for-level buffer discounts worriedness for young players.
  § AUTHENTIC  Skills-authenticity weight on small-sample observation:
               K%, BB%, xwOBA−wOBA gap, sample size gate.
  § ROLLING    Exponential-decay weighting: recent (last ~15 games) and season.
  § OPTIONS    Additive $M per remaining option (roster flexibility).
  § RULE5      Additive $M urgency premium within the pre-deadline window.
  § PEDIGREE   Signing bonus / draft slot → prior precision.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path
from typing import Any

import value_framework as vf
from value_framework import (
    surplus_value_mm,
    sv_credible_interval,
    debuted_player_value,
    is_pitcher_position,
    fv_to_6yr_avg_war,
    fv_to_prime_war,
    tiered_war_value_usd,
)
from age_level import score_age_vs_level


def _level_plus(row) -> float | None:
    """The level-anchored production chip, PHASE D2.

    Reads wrc_plus_level and falls back to ops_plus_level. The two are close but
    not the same number: measured over the 1,972 served hitter statlines the wRC+
    chip runs mean 99.2 sd 6.06 against OPS+ at 100.9 sd 6.97, i.e. it is centred
    about 1.7 points lower and is slightly tighter, because it fixes TWO things at
    once. The metric moves OPS to a linear-weight wOBA, and the baseline moves from
    an unweighted mean of TRACKED PROSPECTS over a two-season window to a
    PA-weighted single-season pool of the WHOLE league. The old prospect baseline
    ran 7-8% low at AA and A+ (.703 against a true .752, .708 against .767), so the
    old chip flattered every hitter at those levels.

    The FALLBACK matters for the gates below, which compare against fixed numbers:
    a null would silently read as 0.0 or 100.0 and flip a threshold for a reason
    that has nothing to do with the player. Coverage is 100% on the current board,
    so the fallback is a guard rather than a live path.
    """
    if not row:
        return None
    v = _safe_float(row.get("wrc_plus_level"), None)
    return v if v is not None else _safe_float(row.get("ops_plus_level"), None)

_log = logging.getLogger(__name__)
_HERE = Path(__file__).resolve().parent

# GRPO scores cache (loaded lazily from data/grpo_scores.json)
_grpo_scores_cache: dict | None = None
_MLB_DETAIL_CACHE: dict | None = None
_FA_PREV_AAV_CACHE: dict | None = None

def _grpo_scores() -> dict:
    """Load GRPO breakout scores, keyed by player_key."""
    global _grpo_scores_cache
    if _grpo_scores_cache is None:
        path = _HERE / "data" / "grpo_scores.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _grpo_scores_cache = data.get("all_scores") or {}
        except Exception:
            _grpo_scores_cache = {}
    return _grpo_scores_cache


def _name_key(name: str | None) -> str:
    s = (name or "").lower().replace(".", "").replace("'", "")
    parts = [p for p in s.replace("-", " ").split() if p not in {"jr", "sr", "ii", "iii", "iv"}]
    return "_".join(parts)


def _mlb_detail_players() -> dict:
    global _MLB_DETAIL_CACHE
    if _MLB_DETAIL_CACHE is None:
        try:
            data = json.loads((_HERE / "data" / "mlb_player_detail.json").read_text(encoding="utf-8"))
            players = data.get("players") or {}
            out = dict(players)
            for key, row in players.items():
                nk = _name_key((row or {}).get("name"))
                if nk:
                    out.setdefault(nk, row)
            _MLB_DETAIL_CACHE = out
        except Exception:
            _MLB_DETAIL_CACHE = {}
    return _MLB_DETAIL_CACHE


def _mlb_projection_entry(player: dict) -> dict | None:
    players = _mlb_detail_players()
    key = player.get("player_key")
    if key in players:
        return players[key]
    return players.get(_name_key(player.get("player_name")))


def _mlb_projection_surplus_mm(player: dict) -> float | None:
    entry = _mlb_projection_entry(player) or {}
    proj = entry.get("proj") or {}
    val = _safe_float(proj.get("surNpv"))
    return round(val / 1_000_000.0, 1) if val is not None else None


def _mlb_projection_is_twoway(player: dict) -> bool:
    entry = _mlb_projection_entry(player) or {}
    return bool(entry.get("twoWay") or str(entry.get("pos") or "").upper() == "TWP")


def _elite_young_slugger_projection_anchor(
    player: dict,
    position: str | None,
    age: float | None,
    career_pa: float,
    proj_surplus_mm: float | None,
) -> bool:
    """Let true elite cheap slugging 1B/DH types escape prospect sample caps."""
    if age is None or age > 25.0 or career_pa < 350.0:
        return False
    if proj_surplus_mm is None or proj_surplus_mm < 80.0:
        return False
    if _pos_primary(position) not in {"1B", "DH", "LF", "RF"}:
        return False

    statline = player.get("statline") or {}
    cq = ((player.get("statcast_metrics") or {}).get("contact_quality") or {})
    iso = _safe_float(statline.get("iso"))
    bb_pct = _safe_float(statline.get("bb_pct"))
    xwoba = _safe_float(cq.get("xwoba_est"))
    barrel = _safe_float(cq.get("barrel_pct"))
    avg_ev = _safe_float(cq.get("avg_ev"))
    if iso is None or iso < 0.240:
        return False
    if bb_pct is not None and bb_pct < 10.0:
        return False
    support = [
        xwoba is not None and xwoba >= 0.370,
        barrel is not None and barrel >= 14.0,
        avg_ev is not None and avg_ev >= 92.0,
    ]
    return sum(1 for ok in support if ok) >= 2


def _career_mlb_exposure(player: dict) -> tuple[float, float]:
    pa = 0.0
    ip = 0.0
    for row in player.get("career_stats") or []:
        if str(row.get("level") or "").upper() != "MLB":
            continue
        pa += _safe_float(row.get("pa") or row.get("PA") or row.get("ab") or row.get("AB"), 0.0) or 0.0
        ip += _safe_float(row.get("ip") or row.get("IP"), 0.0) or 0.0
    return pa, ip


def _projection_anchor_current_form_multiplier(player: dict, position: str | None, age: float | None) -> float:
    """Extra haircut when an MLB projection anchor is fighting a bad current year."""
    if is_pitcher_position(position):
        return 1.0

    statline = player.get("statline") or {}
    current_row = None
    for row in player.get("career_stats") or []:
        if str(row.get("level") or "").upper() == "MLB":
            current_row = row
            break
    row = statline or current_row or {}
    games = _safe_float(row.get("games"), 0.0) or 0.0
    pa = (_safe_float(row.get("pa"), None) or _safe_float(row.get("ab"), None) or 0.0)
    if games < 45.0 and pa < 175.0:
        return 1.0

    ops_plus = _level_plus(row)
    ops = _safe_float(row.get("ops"), None)
    obp = _safe_float(row.get("obp"), None)
    k_pct = _safe_float(row.get("k_pct"), None)
    bb_pct = _safe_float(row.get("bb_pct"), None)
    iso = _safe_float(row.get("iso"), None)
    cq = ((player.get("statcast_metrics") or {}).get("contact_quality") or {})
    avg_ev = _safe_float(cq.get("avg_ev"))
    barrel = _safe_float(cq.get("barrel_pct"))
    xwoba = _safe_float(cq.get("xwoba_est"))
    o_swing = _safe_float(((player.get("zone_metrics") or {}).get("o_swing_pct")
                           or (player.get("zone_metrics") or {}).get("actual_o_swing_pct")))
    elite_power_supported = (
        age is not None
        and age <= 25.0
        and _pos_primary(position) in {"1B", "DH", "LF", "RF"}
        and iso is not None
        and iso >= 0.240
        and (
            (ops_plus is not None and ops_plus >= 130.0)
            or (ops is not None and ops >= 0.850)
        )
        and (
            (xwoba is not None and xwoba >= 0.370)
            or (barrel is not None and barrel >= 14.0)
            or (avg_ev is not None and avg_ev >= 92.0)
        )
    )
    if elite_power_supported:
        return 1.0

    current_bad = (
        (ops_plus is not None and ops_plus < 100.0)
        or (ops is not None and ops < 0.700)
        or (obp is not None and obp < 0.300)
        or (k_pct is not None and k_pct >= 27.5)
    )
    severe_bad = (
        (ops_plus is not None and ops_plus < 95.0)
            or (ops is not None and ops < 0.660)
            or (obp is not None and obp < 0.285)
            or (k_pct is not None and k_pct >= 29.0)
    )

    pos = _pos_primary(position)
    max_mlb_sb = 0.0
    for row in player.get("career_stats") or []:
        if str(row.get("level") or "").upper() == "MLB":
            max_mlb_sb = max(max_mlb_sb, _safe_float(row.get("sb"), 0.0) or 0.0)
    cur_sb = _safe_float(row.get("sb"), 0.0) or 0.0
    speed_or_babip_profile = max_mlb_sb >= 20.0 or (cur_sb >= 8.0 and games <= 90.0)
    aging_speed_outfielder = (
        age is not None
        and age >= 29.0
        and pos in {"OF", "LF", "CF", "RF"}
        and speed_or_babip_profile
        and (iso is None or iso < 0.210)
    )
    low_power_contact_freefall = (
        age is not None
        and age >= 28.0
        and k_pct is not None
        and k_pct <= 15.0
        and iso is not None
        and iso < 0.090
        and (
            (ops is not None and ops < 0.650)
            or (ops_plus is not None and ops_plus < 90.0)
        )
        and (
            (avg_ev is not None and avg_ev < 86.0)
            or (barrel is not None and barrel < 2.0)
        )
    )
    low_power_infield_ceiling = False
    if age is not None and age >= 25.0 and pos in {"SS", "2B", "3B"}:
        meaningful_mlb_seasons = 0
        low_power_mlb_seasons = 0
        for season_row in player.get("career_stats") or []:
            if str(season_row.get("level") or "").upper() != "MLB":
                continue
            season_pa = (
                _safe_float(season_row.get("pa") or season_row.get("PA"), None)
                or _safe_float(season_row.get("ab") or season_row.get("AB"), None)
                or 0.0
            )
            season_iso = _safe_float(season_row.get("iso"), None)
            if season_pa >= 250.0:
                meaningful_mlb_seasons += 1
                if season_iso is not None and season_iso < 0.130:
                    low_power_mlb_seasons += 1
        low_power_infield_ceiling = (
            meaningful_mlb_seasons >= 3
            and low_power_mlb_seasons >= 2
            and low_power_mlb_seasons >= meaningful_mlb_seasons - 1
            and iso is not None
            and iso < 0.130
            and (
                (avg_ev is not None and avg_ev < 88.0)
                or (barrel is not None and barrel < 4.0)
            )
        )
    late_low_prior_free_swing_breakout = (
        age is not None
        and age >= 27.0
        and _safe_float(player.get("fv_close"), 99.0) <= 45.0
        and (
            (bb_pct is not None and bb_pct < 5.0)
            or (o_swing is not None and o_swing >= 36.0)
        )
        and (
            (xwoba is not None and xwoba < 0.310)
            or (barrel is not None and barrel < 7.0)
            or (iso is not None and iso < 0.170)
        )
    )

    if (
        not current_bad
        and not low_power_infield_ceiling
        and not late_low_prior_free_swing_breakout
        or (
            not severe_bad
            and not aging_speed_outfielder
            and not low_power_contact_freefall
            and not low_power_infield_ceiling
            and not late_low_prior_free_swing_breakout
        )
    ):
        return 1.0

    mult = 0.93
    if severe_bad:
        mult -= 0.05

    if aging_speed_outfielder:
        mult -= 0.18
        if severe_bad:
            mult -= 0.07
        if age >= 30.0:
            mult -= 0.02
    if low_power_contact_freefall:
        mult -= 0.22
    if low_power_infield_ceiling:
        mult -= 0.43
    if late_low_prior_free_swing_breakout:
        mult -= 0.31
        if age is not None and age >= 30.0:
            mult -= 0.08

    return max(0.50, round(mult, 3))


def _fa_prev_aav_mm(player: dict) -> float | None:
    global _FA_PREV_AAV_CACHE
    if _FA_PREV_AAV_CACHE is None:
        out = {}
        for path in (_HERE / "data").glob("fa_class*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for row in data.get("members") or []:
                val = _safe_float(row.get("prevAav"))
                if val is None:
                    continue
                keys = {row.get("key"), _name_key(row.get("name"))}
                for k in keys:
                    if k:
                        out.setdefault(k, val / 1_000_000.0)
        _FA_PREV_AAV_CACHE = out
    key = player.get("player_key")
    return _FA_PREV_AAV_CACHE.get(key) or _FA_PREV_AAV_CACHE.get(_name_key(player.get("player_name")))

# ---------------------------------------------------------------------------
# Config loader (mirrors value_framework.py pattern)
# ---------------------------------------------------------------------------
_cfg_cache: dict | None = None


def _cfg() -> dict:
    global _cfg_cache
    if _cfg_cache is None:
        import yaml  # type: ignore
        with open(_HERE / "value_framework_config.yaml", encoding="utf-8") as fh:
            _cfg_cache = yaml.safe_load(fh)
    return _cfg_cache.get("trade_value", {})


def _reset_cache() -> None:
    global _cfg_cache, _grpo_scores_cache
    _cfg_cache = None
    _grpo_scores_cache = None


# ---------------------------------------------------------------------------
# § SCARCITY: positional scarcity multiplier
# ---------------------------------------------------------------------------

def _pos_primary(position: str | None) -> str:
    """Normalize a position string to the canonical scarcity-lookup key.

    For multi-position tags (e.g. "3B/SS", "SS/2B/OF"):
    - Prefer premium defensive positions when present: C > SS > CF > 2B > 3B > corner
    - Henderson "3B/SS" → "SS" (SS scarcity applies, not 3B)
    - Turang "SS/2B/OF" → "2B" (his MLB role, but SS still in the tag)
    """
    if not position:
        return "DH"
    parts = [p.strip() for p in str(position).upper().strip().split("/")]
    # Premium position preference order for scarcity purposes
    _PREMIUM_ORDER = ["TWP", "C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH",
                      "SP", "RHP", "LHP", "P", "RP", "CL", "SIRP", "MIRP"]
    for pref in _PREMIUM_ORDER:
        if pref in parts:
            return pref
    return parts[0] if parts else "DH"


def scarcity_multiplier(position: str | None) -> float:
    """§ SCARCITY: return the trade-market positional scarcity premium.

    Applied multiplicatively to posterior surplus. Captures the thin-supply
    premium at C/SS/CF above what WAR positional adjustments already encode.
    """
    scarcity = _cfg().get("positional_scarcity", {})
    p = _pos_primary(position)
    return float(scarcity.get(p, scarcity.get("RF", 1.00)))


# ---------------------------------------------------------------------------
# § FLOOR: defensive floor value
# ---------------------------------------------------------------------------

def defensive_floor_mm(position: str | None, def_grade: float | None,
                       remaining_years: float | None = None) -> float:
    """§ FLOOR: additive defensive-floor value in $M.

    An elite defensive catcher contributes +2–3 WAR from defense alone,
    regardless of offensive performance. This makes the value distribution
    left-truncated (non-Gaussian) at premium defensive positions.

    Scale from 0 (average defense, grade ~50) to full floor (elite, ~65+),
    present-valued over floor_control_years at floor_discount_rate.

    If def_grade is None we assume average (50) and return 0 — we don't
    apply a floor bonus without evidence of above-average defense.
    """
    cfg = _cfg()
    p = _pos_primary(position)
    floor_war_map = cfg.get("defensive_floor_war", {})
    base_war = float(floor_war_map.get(p, floor_war_map.get(p.split("/")[0], 0.0)))
    if base_war <= 0.0:
        return 0.0

    above_avg_thr = float(cfg.get("def_grade_above_avg", 55.0))
    elite_thr     = float(cfg.get("def_grade_elite", 65.0))

    # grade_scale: 0 below above_avg, ramps from 0.25 at threshold to 1.0 at elite
    if def_grade is None or def_grade < above_avg_thr:
        return 0.0
    elif def_grade >= elite_thr:
        grade_scale = 1.0
    else:
        # § FLOOR: start at 0.25 at the above_avg threshold so a confirmed
        # above-average defender still registers a non-zero floor contribution.
        grade_scale = 0.25 + 0.75 * (def_grade - above_avg_thr) / (elite_thr - above_avg_thr)

    dpw  = float(cfg.get("floor_dollars_per_war_mm", 8.76))
    # Use caller-supplied remaining years (for debuted players with limited control),
    # otherwise fall back to config default.
    yrs  = int(min(remaining_years, cfg.get("floor_control_years", 5))
               if remaining_years is not None
               else cfg.get("floor_control_years", 5))
    rate = float(cfg.get("floor_discount_rate", 0.09))

    # NOTE (Phase 2 audit): this is a DELIBERATE flat defensive FLOOR, not a
    # price-the-mean of an uncertain outcome. An elite defender's glove is worth a
    # near-certain `base_war` every season regardless of the bat, so it is priced
    # at a single floor rate (`floor_dollars_per_war_mm`, the 1-2 WAR tier) and
    # discounted per season. It is additive on top of the mixture-priced posterior
    # and is intentionally EXEMPT from the convex per-season kernel (there is no
    # volatile WAR distribution to transform-first here). Left as-is by design.
    pv = sum(
        grade_scale * base_war * dpw / (1.0 + rate) ** yr
        for yr in range(1, yrs + 1)
    )
    return round(pv, 2)


def multiposition_bonus_mm(
    player_key: str | None,
    position: str | None,
    *,
    is_pitcher: bool = False,
    is_mlb_player: bool = False,
    remaining_years: float | None = None,
    posterior_surplus_mm: float | None = None,
) -> tuple[float, dict]:
    """Additive value for demonstrated MLB defensive flexibility.

    Evidence-gated by current-season fielding usage. DH is excluded because it
    is not defensive flexibility, and one-off emergency appearances do not
    qualify.
    """
    if is_pitcher or not is_mlb_player or not player_key:
        return 0.0, {"positions": {}, "meaningful_positions": []}
    try:
        from fielding import position_usage
        usage = position_usage(player_key)
    except Exception:
        usage = {}
    if not usage:
        return 0.0, {"positions": {}, "meaningful_positions": []}

    primary = _pos_primary(position)
    meaningful: list[str] = []
    clean_usage: dict[str, dict] = {}
    for raw_pos, row in usage.items():
        pos = str(raw_pos).upper()
        games = _safe_float((row or {}).get("games"), 0.0) or 0.0
        innings = _safe_float((row or {}).get("innings"), 0.0) or 0.0
        starts = _safe_float((row or {}).get("games_started"), 0.0) or 0.0
        clean_usage[pos] = {
            "games": games,
            "games_started": starts,
            "innings": innings,
        }
        if pos == "DH":
            continue
        if games >= 5.0 and innings >= 30.0:
            meaningful.append(pos)

    if len(meaningful) < 2:
        return 0.0, {"positions": clean_usage, "meaningful_positions": meaningful}

    meaningful.sort(
        key=lambda p: (p == primary, clean_usage.get(p, {}).get("innings", 0.0)),
        reverse=True,
    )
    secondary = [p for p in meaningful if p != primary] or meaningful[1:]
    pos_add = {
        "C": 1.5, "SS": 1.5, "CF": 1.5,
        "2B": 0.75, "3B": 0.75, "RF": 0.75, "LF": 0.75, "OF": 0.75,
        "1B": 0.25,
    }
    raw_bonus = sum(1.5 + float(pos_add.get(pos, 0.5)) for pos in secondary)
    control_scale = min(1.25, max(0.4, float(remaining_years or 0.0) / 5.0))
    impact_scale = min(1.0, max(0.25, float(posterior_surplus_mm or 0.0) / 35.0))
    bonus = min(7.5, raw_bonus * control_scale * impact_scale)
    return round(bonus, 1), {"positions": clean_usage, "meaningful_positions": meaningful}


# ---------------------------------------------------------------------------
# § PEDIGREE: signing bonus / draft slot → prior precision weight
# ---------------------------------------------------------------------------

def pedigree_precision(acquisition: dict | None) -> float:
    """§ PEDIGREE: convert signing bonus / draft slot to prior precision weight.

    High bonus → tighter prior (we trust the pre-draft evaluation more).
    Log-scale: each 10× in bonus adds one unit of precision weight above
    the $10k floor (the minimum IFA bonus).

    A prospect like Franklin Primera ($10k IFA bonus) gets ~0.0; a prospect
    like Josuar Gonzalez ($5M+ IFA bonus) gets near the maximum.
    """
    if not acquisition:
        return 0.0
    cfg_p = _cfg().get("prior", {}).get("pedigree", {})
    ifa_scale   = float(cfg_p.get("ifa_log_scale", 2.0))
    top10_bonus = float(cfg_p.get("draft_top10_bonus", 0.8))
    r1_bonus    = float(cfg_p.get("draft_round1_bonus", 0.4))
    r2_bonus    = float(cfg_p.get("draft_round2_bonus", 0.15))
    max_ped     = float(cfg_p.get("max_pedigree_precision", 3.0))

    bonus_usd    = acquisition.get("bonus_usd") or 0
    pick_overall = acquisition.get("pick_overall") or 0
    method       = str(acquisition.get("method") or "")
    round_label  = str(acquisition.get("round_label") or "")

    precision = 0.0

    if bonus_usd and bonus_usd > 0:
        if "international" in method.lower() or "ifa" in method.lower():
            # § PEDIGREE: IFA bonus log-scale (log10(bonus / 10000))
            # $10k → 0.0;  $100k → 1.0×ifa_scale;  $1M → 2.0×ifa_scale
            precision += ifa_scale * max(0.0, math.log10(bonus_usd / 10_000))
        else:
            # Draft: use pick position as signal
            if pick_overall and pick_overall <= 10:
                precision += top10_bonus
            elif (pick_overall and pick_overall <= 30) or "1" in round_label[:2]:
                precision += r1_bonus
            elif "2" in round_label[:2]:
                precision += r2_bonus
            # Also factor in bonus above slot as a signal of team conviction
            if bonus_usd > 500_000:
                precision += ifa_scale * max(0.0, math.log10(bonus_usd / 500_000)) * 0.5

    return round(min(precision, max_ped), 3)


# ---------------------------------------------------------------------------
# § PRIOR: age-for-level buffer
# ---------------------------------------------------------------------------

def age_for_level_buffer(age: float | None, level: str | None,
                         baselines: dict | None = None) -> float:
    """§ AGE_CURVE (prior precision): how much young-for-level protects the prior.

    A prospect who was young for every level has been tested against older,
    more developed competition. Their prior is tighter in the positive
    direction — it takes more negative evidence to move it downward.

    Returns an additive precision bonus (not a multiplier) so it stacks
    cleanly with pedigree and source-count precision components.
    """
    avl = score_age_vs_level(age, level, baselines)
    cfg_a = _cfg().get("prior", {}).get("age_for_level", {})
    buf_per_yr = float(cfg_a.get("buffer_per_year_young", 0.30))
    max_buf    = float(cfg_a.get("max_buffer", 1.5))

    if avl.diff is None:
        return 0.0
    # Negative diff means younger than baseline → positive buffer
    # Positive diff (old for level) → no buffer (doesn't penalize the prior)
    years_young = max(0.0, -avl.diff)
    return round(min(years_young * buf_per_yr, max_buf), 3)


# ---------------------------------------------------------------------------
# § AUTHENTIC: skills-authenticity weight
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float | None = None) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _eta_years_to_debut(eta) -> float | None:
    """Years from now to projected debut (bughunt F2, 2026-07-23). The
    timeseries payload carries `eta` as a DICT ({year, half, ...}) on every
    prospect row - _safe_float(dict) returned None, so _resolve_timing fell to
    default_eta_years=0.0 and every posterior priced debut-NOW (masked today by
    the eFV surplus overwrite on the trade board; latent-P0 on any coverage
    gap). Mirrors storage._eta_years_from: year - current year, late half adds
    0.5, floored at 0. A bare number passes through; None/unresolvable -> None
    (engine default), matching the consensus writer's behavior."""
    if eta is None:
        return None
    if isinstance(eta, dict):
        yr = _safe_float(eta.get("year"))
        if yr is None:
            return None
        yrs = yr - float(date.today().year)
        if str(eta.get("half") or "") == "late":
            yrs += 0.5
        return max(0.0, yrs)
    return _safe_float(eta)


def skills_authenticity(statline: dict | None,
                        statcast: dict | None,
                        is_pitcher: bool,
                        level: str | None = None) -> float:
    """§ AUTHENTIC: [0, 1] weight on how skills-backed the surface results are.

    Small-sample observations are unreliable if the underlying metrics
    (approach, contact quality) don't support them. This weight scales the
    likelihood term so a fluky BABIP-driven .350 average moves the posterior
    less than a skills-backed .320.

    Returns 1.0 (full trust) when all indicators are healthy; lower when
    red flags appear or the sample is thin.
    """
    auth_cfg = _cfg().get("authenticity", {})
    if not statline:
        return 0.50  # no data → 50% trust

    score = 1.0
    cq = (statcast or {}).get("contact_quality") or {}

    if not is_pitcher:
        ha = auth_cfg.get("hitter", {})
        k_pct  = _safe_float(statline.get("k_pct"))
        bb_pct = _safe_float(statline.get("bb_pct"))
        woba   = _safe_float(statline.get("woba"))
        xwoba  = _safe_float(cq.get("xwoba_est") or statcast and _safe_float((statcast or {}).get("xwoba")))
        pa     = _safe_float(statline.get("pa") or statline.get("ab"), 0)

        max_k  = float(ha.get("max_k_pct", 27.0))
        min_bb = float(ha.get("min_bb_pct", 6.5))
        max_gap = float(ha.get("max_xwoba_woba_gap", 0.025))
        min_pa = float(ha.get("min_pa_for_full", 150))

        # K% penalty (§ AUTHENTIC)
        if k_pct is not None and k_pct > max_k:
            score -= min(0.30, (k_pct - max_k) / max_k * 0.5)
        # BB% penalty
        if bb_pct is not None and bb_pct < min_bb:
            score -= min(0.20, (min_bb - bb_pct) / min_bb * 0.4)
        # xwOBA vs wOBA gap (luck indicator)
        if xwoba is not None and woba is not None and woba - xwoba > max_gap:
            score -= min(0.20, (woba - xwoba - max_gap) / 0.03 * 0.15)
        # Small sample gate (§ AUTHENTIC)
        if pa is not None and pa < min_pa:
            cap = 0.5 + 0.5 * (pa / min_pa)
            score = min(score, cap)
    else:
        hp = auth_cfg.get("pitcher", {})
        k_pct  = _safe_float(statline.get("k_pct"))
        bb_pct = _safe_float(statline.get("bb_pct"))
        era    = _safe_float(statline.get("era"))
        fip    = _safe_float(statline.get("fip"))
        ip     = _safe_float(statline.get("ip"), 0)

        max_bb      = float(hp.get("max_bb_pct", 11.0))
        min_k       = float(hp.get("min_k_pct", 17.0))
        max_era_fip = float(hp.get("max_era_fip_gap", 0.60))
        min_ip      = float(hp.get("min_ip_for_full", 40.0))

        if bb_pct is not None and bb_pct > max_bb:
            score -= min(0.25, (bb_pct - max_bb) / max_bb * 0.4)
        if k_pct is not None and k_pct < min_k:
            score -= min(0.20, (min_k - k_pct) / min_k * 0.4)
        if era is not None and fip is not None and era - fip > max_era_fip:
            score -= min(0.20, (era - fip - max_era_fip) / 0.5 * 0.15)
        if ip is not None and ip < min_ip:
            cap = 0.5 + 0.5 * (ip / min_ip)
            score = min(score, cap)

    return round(max(0.10, min(1.0, score)), 3)


# ---------------------------------------------------------------------------
# § ROLLING + § LIKELIHOOD: performance signal computation
# ---------------------------------------------------------------------------

def _level_baseline(level: str | None, is_pitcher: bool, field: str,
                    level_norms: dict | None = None) -> float | None:
    """Return the league-average value for a given stat at a level.

    Prefers empirical level_norms from the pipeline; falls back to
    the static config table when not available.
    """
    lvl = (level or "A+").strip()

    # Try level_norms (empirical, from timeseries.json pipeline)
    if level_norms:
        norm = level_norms.get(lvl) or {}
        perf = norm.get("perf") or {}
        val = perf.get(field)
        if val is not None:
            return float(val)

    # Config fallback
    role = "pitcher" if is_pitcher else "hitter"
    baselines = _cfg().get("level_baselines", {}).get(role, {})
    lvl_map = baselines.get(lvl) or baselines.get("AA") or {}  # AA as middle fallback
    val = lvl_map.get(field)
    return float(val) if val is not None else None


def _perf_signal_from_statline(statline: dict | None,
                                statcast: dict | None,
                                is_pitcher: bool,
                                level: str | None,
                                level_norms: dict | None,
                                fv: float | None,
                                auth_weight: float,
                                o_swing_pct: float | None = None) -> float | None:
    """§ LIKELIHOOD: convert a statline + statcast block into a surplus $M signal.

    Normalizes each metric against the level average, weights the components,
    then maps the composite z-score to a surplus delta relative to the FV prior.

    Returns the signal in $M, or None if there is not enough data.
    """
    if not statline:
        return None

    cq = (statcast or {}).get("contact_quality") or {}
    z_scores: list[float] = []

    def _z(value: float | None, baseline: float | None,
           stdev_frac: float = 0.15, invert: bool = False) -> float | None:
        if value is None or baseline is None or baseline == 0:
            return None
        sd = max(1e-6, baseline * stdev_frac)
        z = (value - baseline) / sd
        return -z if invert else z

    if not is_pitcher:
        k_pct  = _safe_float(statline.get("k_pct"))
        bb_pct = _safe_float(statline.get("bb_pct"))
        woba   = _safe_float(statline.get("woba"))
        xwoba  = _safe_float(cq.get("xwoba_est"))
        avg_ev = _safe_float(cq.get("avg_ev"))
        brl    = _safe_float(cq.get("barrel_pct"))
        hh_pct = _safe_float(cq.get("hard_hit_pct"))

        bl_k    = _level_baseline(level, False, "k_pct", level_norms)
        bl_bb   = _level_baseline(level, False, "bb_pct", level_norms)
        bl_woba = _level_baseline(level, False, "xwoba" if xwoba else "woba", level_norms)
        bl_ev   = _level_baseline(level, False, "avg_ev", level_norms)
        bl_brl  = _level_baseline(level, False, "barrel_pct", level_norms)

        # § PROFILE: K% weight is profile-dependent.
        #
        # Low K% from a power bat (Wood/Murakami type: high EV + barrels) is
        # maximally valuable — bat-to-ball + power = complete offensive weapon.
        # Low K% from a contact-without-power bat (Hoerner type: modest EV, low
        # barrels) is still a positive signal but less predictive of run value
        # at scale.  These hitters often make contact on bad pitches (high chase)
        # which inflates K%/BB% without producing hard contact.
        #
        # Additionally: if o_swing_pct (chase rate) is available and the player
        # has a low K%, we check whether the K% comes from genuine discipline
        # (low chase → walks are real) or from making contact on bad pitches
        # (high chase + low K% = hitter who fouls off or puts weak balls in play
        # rather than taking walks, similar to many contact-first prospects).
        _MLB_CHASE_AVG = 29.5   # typical MLB O-Swing%
        _has_power     = (avg_ev is not None and avg_ev >= 90.0 and (brl or 0) >= 8.0) \
                         or (brl is not None and brl >= 12.0)
        _decent_power  = (avg_ev is not None and avg_ev >= 87.0) \
                         or (brl is not None and brl >= 5.0) \
                         or (xwoba is not None and xwoba >= 0.380) \
                         or (hh_pct is not None and hh_pct >= 45.0)
        if _has_power:
            _k_w, _brl_w = 0.22, 0.12   # full K% credit for genuine power bats
        elif _decent_power:
            _k_w, _brl_w = 0.16, 0.14   # partial K% credit; boost contact/power balance
        else:
            # Contact-without-power: K% is less meaningful, power metrics matter more
            _k_w, _brl_w = 0.08, 0.20

        # § CHASE ADJUSTMENT: for low-K% hitters, validate whether the K% comes
        # from genuine plate discipline (low o_swing) or from making weak contact
        # on bad pitches (high o_swing).
        _chase_adj = 0.0
        if o_swing_pct is not None and k_pct is not None and k_pct < 20:
            chase_delta = o_swing_pct - _MLB_CHASE_AVG
            _chase_adj = max(-0.12, min(0.08, -chase_delta / 35.0))

        # § BB%-xwOBA CONSISTENCY: a player walking a lot while posting mediocre
        # contact quality may have a favorable count environment rather than true
        # elite discipline.  Reynolds type: BB%=15.7% but xwoba=0.32 (average).
        # Soderstrom type: BB%=12.9% but xwoba=0.278 (well below average).
        # When BB% is above average but xwoba doesn't support it, down-weight BB%.
        _MLB_AVG_XWOBA = 0.318
        _bb_weight = 0.24
        if (bb_pct is not None and bb_pct > 9.5 and
                xwoba is not None and bl_woba is not None):
            # Scale the discount by how much xwoba falls below level average
            _xwoba_gap = max(0.0, (bl_woba + 0.005) - xwoba)  # gap below avg
            if _xwoba_gap > 0:
                _bb_excess   = min(1.0, (bb_pct - 9.5) / 7.0)   # 0 at 9.5%, 1 at 16.5%+
                _gap_scale   = min(1.0, _xwoba_gap / 0.040)      # 0 at avg, 1 at 0.04 below avg
                _bb_discount = min(0.55, _bb_excess * _gap_scale * 0.65)
                _bb_weight   = 0.24 * (1.0 - _bb_discount)

        # § POWER REGRESSION PENALTY: when ISO and barrel% are both scarily low,
        # the player has essentially no power projection. This caps upside regardless
        # of how disciplined they are at the plate. Perdomo type: iso=0.111, barrel=2.7%
        # at SS — plausibly a 8-10 HR hitter going forward, which limits WAR ceiling.
        # The penalty reduces the composite z-score to prevent elite K%/BB% from
        # over-projecting a player who can't drive the ball.
        _iso    = _safe_float(statline.get("iso")) if not is_pitcher else None
        _power_penalty = 0.0
        # Barrel threshold raised from 4.0 to 6.0: Volpe type (ISO=0.113, brl=4.5)
        # is a no-power profile that the old threshold let slip through. 6% barrel
        # is still well below the MLB average (~8%), representing genuine power scarcity.
        if _iso is not None and brl is not None and _iso < 0.120 and brl < 6.0:
            # How far below a "decent power" threshold?
            _iso_gap  = max(0.0, 0.120 - _iso) / 0.050   # 0 at .120, 1 at .070
            _brl_gap  = max(0.0, 6.0 - brl) / 6.0        # 0 at 6%, 1 at 0%
            _power_penalty = min(0.35, (_iso_gap + _brl_gap) / 2 * 0.40)

        # § HIGH-BARREL CONFIDENCE: when barrel% is elite (≥10%), the player is
        # demonstrably hitting the ball at the optimal EV/LA combination. This is
        # hard physical evidence that should reduce the weight of the xwOBA signal
        # (which can be noisy/low-sample) and boost confidence in the power metrics.
        # Chourio type: barrel%=13.0, avg_ev=92.3 → xwoba=0.286 seems inconsistent;
        # the barrels are real and the xwoba signal should be muted.
        _xwoba_w = 0.26   # default xwoba weight
        if brl is not None and brl >= 10.0:
            # High barrel% → trust power metrics more, xwoba less
            _barrel_confidence = min(1.0, (brl - 10.0) / 8.0)  # 0 at 10%, 1 at 18%+
            _xwoba_w = 0.26 * (1.0 - _barrel_confidence * 0.40)  # reduce up to 40%
            _brl_w   = _brl_w + 0.26 * _barrel_confidence * 0.40  # redistribute to barrel

        # § LIKELIHOOD weights: approach + contact quality + raw results
        components = [
            (_z(k_pct,  bl_k,  invert=True), _k_w),        # K% (profile-weighted)
            (_z(bb_pct, bl_bb, invert=False), _bb_weight),  # BB% (consistency-adjusted)
            (_z(xwoba or woba, bl_woba, stdev_frac=0.08), _xwoba_w),  # quality contact (barrel-adjusted)
            (_z(avg_ev, bl_ev, stdev_frac=0.05), 0.14),           # exit velocity
            (_z(brl,    bl_brl, stdev_frac=0.60), _brl_w),        # barrel % (profile-weighted)
        ]
        for z, _ in components:
            if z is not None:
                z_scores.append(z)
        weight_sum = sum(w for z, w in components if z is not None)
        if weight_sum == 0:
            return None
        composite_z = sum(z * w for z, w in components if z is not None) / weight_sum
        # Apply chase adjustment and power penalty on the composite
        composite_z += _chase_adj
        if _power_penalty > 0:
            composite_z = composite_z * (1.0 - _power_penalty) - _power_penalty * 0.3

    else:
        k_pct  = _safe_float(statline.get("k_pct"))
        bb_pct = _safe_float(statline.get("bb_pct"))
        era    = _safe_float(statline.get("era"))
        fip    = _safe_float(statline.get("fip"))

        bl_k   = _level_baseline(level, True, "k_pct", level_norms)
        bl_bb  = _level_baseline(level, True, "bb_pct", level_norms)
        bl_era = _level_baseline(level, True, "era", level_norms)
        bl_fip = _level_baseline(level, True, "fip", level_norms)

        # § STUFF+ CEILING: for pitchers whose primary-pitch Stuff+ is below average
        # (< 95), there's a hard ceiling on upside regardless of control/command.
        # Cameron type: 4-seam Stuff+=90, arsenal avg ~96 → can outperform on
        # control alone but cannot be a truly elite pitcher without better stuff.
        # Read from pitch_movement.pitch_summary if available.
        _stuff_penalty = 0.0
        _pm_data = (statcast or {}).get("pitch_movement") or {}
        _ps = _pm_data.get("pitch_summary") or []
        if _ps:
            # Primary pitch = highest usage
            _primary = max(_ps, key=lambda p: p.get("usage_pct") or 0, default=None)
            _primary_sp = float((_primary or {}).get("avg_stuff_plus") or 100)
            # Arsenal-weighted avg Stuff+
            _total_usage = sum(p.get("usage_pct") or 0 for p in _ps)
            _wsplus = sum((p.get("avg_stuff_plus") or 100) * (p.get("usage_pct") or 0)
                          for p in _ps) / max(1, _total_usage)
            # Penalty: scaled penalty when primary pitch Stuff+ < 95
            if _primary_sp < 95:
                _stuff_penalty = min(0.4, (95 - _primary_sp) / 25)  # 0 at 95, 0.4 at 85
            # Also cap composite_z for below-average arsenal
            _arsenal_below = max(0, 100 - _wsplus)  # 0 when at/above avg, positive when below

        components = [
            (_z(k_pct,  bl_k,  invert=False), 0.35),
            (_z(bb_pct, bl_bb, invert=True),  0.30),   # BB% → invert (lower = better)
            (_z(fip or era, bl_fip or bl_era, stdev_frac=0.15, invert=True), 0.35),
        ]
        weight_sum = sum(w for z, w in components if z is not None)
        if weight_sum == 0:
            return None
        composite_z = sum(z * w for z, w in components if z is not None) / weight_sum
        # Apply stuff ceiling: reduce signal for pitchers with below-average primary pitch.
        # A pitcher with Stuff+=90 (Cameron's 4-seam) and ERA > 4.0 is being carried
        # by command alone — the model should not project 3+ WAR talent for them.
        if _stuff_penalty > 0:
            composite_z = composite_z * (1.0 - _stuff_penalty)
            # Additional cap on the signal magnitude: below-avg stuff limits upside
            if era is not None:
                try:
                    era_val = float(era)
                    if era_val > 4.0 and _stuff_penalty >= 0.10:
                        # Heavy stuff penalty + bad ERA → cap the composite at slightly negative
                        composite_z = min(composite_z, -0.2)
                except (TypeError, ValueError):
                    pass

    if not z_scores and composite_z == 0:
        return None

    # § LIKELIHOOD: map composite z-score to a $M delta on the FV prior.
    # One σ of outperformance ≈ 3 FV points of upward revision ≈ some $M delta.
    # We proxy this via the marginal $M/FV-point at the player's current FV.
    fv_safe = float(fv or 50.0)
    sv_hi = surplus_value_mm(fv_safe + 3.0, is_pitcher) or 0.0
    sv_lo = surplus_value_mm(max(20.0, fv_safe - 3.0), is_pitcher) or 0.0
    mm_per_sigma = (sv_hi - sv_lo) / 2.0  # $M per standard deviation

    raw_signal_mm = composite_z * mm_per_sigma
    # § AUTHENTIC: scale by skills-authenticity weight
    return round(raw_signal_mm * auth_weight, 2)


def _rolling_signal(statline: dict | None,
                    statcast: dict | None,
                    recent_games: list[dict],
                    is_pitcher: bool,
                    level: str | None,
                    level_norms: dict | None,
                    fv: float | None,
                    career_stats: list | None = None) -> tuple[float | None, float, str]:
    """§ ROLLING: compute rolling-weighted performance signal.

    Blends:
      - recent window (last ~15 games, recent_games list)
      - season statline

    Returns (signal_mm, sample_size, window_label).
    """
    rcfg = _cfg().get("rolling", {})
    w_recent = float(rcfg.get("recent_weight", 0.35))
    w_season = float(rcfg.get("season_weight", 0.65))

    # Extract o_swing_pct stored in statcast by the caller (from zone_metrics)
    _o_swing_from_sc = _safe_float((statcast or {}).get("o_swing_pct"))

    auth = skills_authenticity(statline, statcast, is_pitcher, level)
    season_signal = _perf_signal_from_statline(
        statline, statcast, is_pitcher, level, level_norms, fv, auth,
        o_swing_pct=_o_swing_from_sc,
    )

    # § ROLLING: compute a quick statline from recent_games if available
    recent_signal: float | None = None
    if recent_games:
        rsl = _aggregate_recent_games(recent_games, is_pitcher)
        if rsl:
            r_auth = skills_authenticity(rsl, None, is_pitcher, level)
            recent_signal = _perf_signal_from_statline(
                rsl, None, is_pitcher, level, level_norms, fv, r_auth,
                o_swing_pct=_o_swing_from_sc,
            )

    # Sample size: prefer PA/IP from statline; fall back to career_stats[0]
    # when statline has only rates (common for MiLB prospects).
    cs0 = ((career_stats or [])[0]) if career_stats else {}
    if is_pitcher:
        sample = (_safe_float((statline or {}).get("ip")) or
                  _safe_float((cs0 or {}).get("ip") or (cs0 or {}).get("IP")) or 0.0)
    else:
        sample = (_safe_float((statline or {}).get("pa")) or
                  _safe_float((statline or {}).get("ab")) or
                  _safe_float((cs0 or {}).get("pa") or (cs0 or {}).get("PA")) or
                  _safe_float((cs0 or {}).get("ab") or (cs0 or {}).get("AB")) or
                  (_safe_float((cs0 or {}).get("g") or (cs0 or {}).get("G"), 0) or 0) * 4 or 0.0)
    # Conservative default when only rates are available: use 20 IP / 80 PA
    # so the signal comes through at a heavily discounted Kalman weight.
    if sample == 0 and ((statline or {}).get("k_pct") or (statline or {}).get("bb_pct")):
        sample = 20.0 if is_pitcher else 80.0

    # Blend signals
    if recent_signal is not None and season_signal is not None:
        blended = w_recent * recent_signal + w_season * season_signal
        label = "recent+season"
    elif season_signal is not None:
        blended = season_signal
        label = "season"
    elif recent_signal is not None:
        blended = recent_signal
        label = "recent"
    else:
        return None, float(sample), "none"

    return round(blended, 2), float(sample), label


def _aggregate_recent_games(games: list[dict], is_pitcher: bool) -> dict | None:
    """§ ROLLING: build a mini statline from recent_games dicts."""
    if not games:
        return None
    totals: dict[str, float] = {}
    for g in games:
        if not is_pitcher:
            for k in ("pa", "ab", "h", "hr", "doub", "trip", "bb", "so", "rbi"):
                totals[k] = totals.get(k, 0) + (g.get(k) or 0)
        else:
            for k in ("ip", "k", "er", "bb", "h_allowed"):
                totals[k] = totals.get(k, 0) + (g.get(k) or 0)

    if not is_pitcher:
        pa  = totals.get("pa") or totals.get("ab") or 0
        ab  = totals.get("ab") or 0
        h   = totals.get("h") or 0
        hr  = totals.get("hr") or 0
        bb  = totals.get("bb") or 0
        so  = totals.get("so") or 0
        if pa == 0:
            return None
        avg  = round(h / ab, 3) if ab else None
        obp  = round((h + bb) / pa, 3) if pa else None
        slg  = round((h + totals.get("doub", 0) + 2 * totals.get("trip", 0) + 3 * hr) / ab, 3) if ab else None
        iso  = round(slg - avg, 3) if slg and avg else None
        woba_approx = round((0.69 * bb + 0.888 * (h - hr) + 1.271 * totals.get("doub", 0) +
                             1.616 * totals.get("trip", 0) + 2.101 * hr) / pa, 3) if pa else None
        return {
            "pa": pa, "ab": ab, "bb_pct": round(100 * bb / pa, 1) if pa else None,
            "k_pct": round(100 * so / pa, 1) if pa else None,
            "woba": woba_approx, "iso": iso,
        }
    else:
        ip  = totals.get("ip") or 0
        k   = totals.get("k") or 0
        er  = totals.get("er") or 0
        bb  = totals.get("bb") or 0
        if ip == 0:
            return None
        era = round(9 * er / ip, 2) if ip else None
        # K% / BB% are per BATTER FACED, not per (K+ER+BB) -- the old denominator was
        # nonsense (an ER is not a plate appearance). Estimate BF = outs + baserunners
        # reached = 3*IP + H + BB (the standard TBF approximation; HBP omitted).
        h_a = totals.get("h_allowed") or 0
        bf  = 3 * ip + h_a + bb
        k_pct  = round(100 * k / max(1, bf), 1)
        bb_pct = round(100 * bb / max(1, bf), 1)
        return {"ip": ip, "era": era, "k_pct": k_pct, "bb_pct": bb_pct}


# ---------------------------------------------------------------------------
# § WORRY: worriedness score
# ---------------------------------------------------------------------------

def worriedness_score(player: dict, level_norms: dict | None = None) -> dict:
    """§ WORRY: estimate P(skills_decay | trajectory).

    Decomposes into two signal types:
      approach_decay    K%↑, BB%↓, chase%↑ — systematic hole, hardest to fix
      contact_quality   EV↓, barrel%↓, stable approach — often mechanical/injury

    The age-for-level buffer discounts worriedness for young-for-level players
    because their stronger prior takes more evidence to overcome.

    Returns a dict: {score, type, approach_signal, contact_signal, age_discount}.
    """
    wcfg = _cfg().get("worriedness", {})
    statline  = player.get("statline") or {}
    statcast  = player.get("statcast_metrics") or {}
    zone      = player.get("zone_metrics") or {}
    position  = player.get("position")
    # Mirror the main function: explicit flag OR position-based detection
    is_pitcher = bool(player.get("is_pitcher")) or is_pitcher_position(position)
    level     = player.get("current_level")
    age       = _safe_float(player.get("age"))

    cq = (statcast or {}).get("contact_quality") or {}

    # § WORRY: we need an actual prior-season baseline to detect *decay*.
    # Comparing only against a static level average fires on players who are
    # legitimately performing above average (e.g., Kyle Harrison pitching well
    # with a "high" K% relative to a bad level baseline). We require a prior
    # season to establish the delta; without one, only extreme absolute values
    # (e.g., K% > 33% or BB% > 15%) register approach concern.
    career = player.get("career_stats") or []
    prior_season = career[1] if len(career) > 1 else None  # index 0 = most recent

    # § WORRY: only compare within the SAME level. A player jumping from DSL→CPX
    # or A→A+ will naturally see K% rise — that's not decay, it's harder pitching.
    # When levels differ, discard the prior baseline and rely on absolute thresholds.
    current_cs_level = (career[0] if career else {}).get("level")
    prior_cs_level   = (prior_season or {}).get("level")
    if current_cs_level and prior_cs_level and current_cs_level != prior_cs_level:
        prior_season = None  # different level → no decay comparison
    has_prior_baseline = prior_season is not None

    approach_signal = 0.0
    contact_signal  = 0.0

    if not is_pitcher:
        k_thresh   = float(wcfg.get("approach_k_pct_threshold", 3.0))
        bb_thresh  = float(wcfg.get("approach_bb_pct_threshold", 2.0))
        ev_thresh  = float(wcfg.get("contact_ev_drop_threshold", 2.0))
        brl_thresh = float(wcfg.get("contact_barrel_drop_threshold", 2.5))

        k_cur   = _safe_float(statline.get("k_pct"))
        bb_cur  = _safe_float(statline.get("bb_pct"))
        ev_cur  = _safe_float(cq.get("avg_ev"))
        brl_cur = _safe_float(cq.get("barrel_pct"))

        if has_prior_baseline:
            # § WORRY: compare current vs prior season (true decay signal)
            k_base   = _safe_float((prior_season or {}).get("k_pct"))
            bb_base  = _safe_float((prior_season or {}).get("bb_pct"))
            ev_base  = _level_baseline(level, False, "avg_ev", level_norms)
            brl_base = _level_baseline(level, False, "barrel_pct", level_norms)

            if k_cur is not None and k_base is not None and k_cur - k_base > k_thresh:
                approach_signal += min(1.0, (k_cur - k_base - k_thresh) / k_thresh)
            if bb_cur is not None and bb_base is not None and bb_base - bb_cur > bb_thresh:
                approach_signal += min(1.0, (bb_base - bb_cur - bb_thresh) / bb_thresh) * 0.7
            if ev_cur is not None and ev_base is not None and ev_base - ev_cur > ev_thresh:
                contact_signal += min(1.0, (ev_base - ev_cur - ev_thresh) / ev_thresh) * 0.8
            if brl_cur is not None and brl_base is not None and brl_base - brl_cur > brl_thresh:
                contact_signal += min(1.0, (brl_base - brl_cur - brl_thresh) / brl_thresh) * 0.6
        else:
            # No prior season (or prior at different level): fire on extreme absolute
            # approach thresholds for K/BB, but still check barrel% and avgEV vs the
            # level baseline — those comparisons use the MLB/level average as reference,
            # not the prior season, so a level mismatch is irrelevant.
            # Volpe type: debuted from AAA, so career_stats[1] is AAA (level mismatch
            # kills has_prior_baseline) yet barrel%=4.5 vs MLB baseline 8.0 is a real
            # contact-quality signal that should fire regardless.
            if k_cur is not None and k_cur > 33.0:
                approach_signal += min(0.5, (k_cur - 33.0) / 10.0)
            if bb_cur is not None and bb_cur < 4.0:
                approach_signal += min(0.3, (4.0 - bb_cur) / 4.0) * 0.5
            ev_base_abs  = _level_baseline(level, False, "avg_ev", level_norms)
            brl_base_abs = _level_baseline(level, False, "barrel_pct", level_norms)
            if ev_cur is not None and ev_base_abs is not None and ev_base_abs - ev_cur > ev_thresh:
                contact_signal += min(1.0, (ev_base_abs - ev_cur - ev_thresh) / ev_thresh) * 0.8
            if brl_cur is not None and brl_base_abs is not None and brl_base_abs - brl_cur > brl_thresh:
                contact_signal += min(1.0, (brl_base_abs - brl_cur - brl_thresh) / brl_thresh) * 0.6

    else:
        # Pitcher worriedness: BB%↑ and K%↓ are the primary approach signals
        bb_cur  = _safe_float(statline.get("bb_pct"))
        k_cur   = _safe_float(statline.get("k_pct"))
        bb_base = _safe_float((prior_season or {}).get("bb_pct")) if has_prior_baseline else None
        k_base  = _safe_float((prior_season or {}).get("k_pct"))  if has_prior_baseline else None

        if has_prior_baseline:
            if bb_cur is not None and bb_base is not None and bb_cur - bb_base > 2.0:
                approach_signal += min(1.0, (bb_cur - bb_base - 2.0) / 2.0)
            if k_cur is not None and k_base is not None and k_base - k_cur > 3.0:
                approach_signal += min(1.0, (k_base - k_cur - 3.0) / 3.0) * 0.7
        else:
            # No prior: only fire on extreme absolute BB% (command collapse)
            if bb_cur is not None and bb_cur > 16.0:
                approach_signal += min(0.6, (bb_cur - 16.0) / 8.0)
            if k_cur is not None and k_cur < 10.0:
                approach_signal += min(0.4, (10.0 - k_cur) / 10.0) * 0.6

    # Cap signals at 1.0
    approach_signal = min(1.0, approach_signal)
    contact_signal  = min(1.0, contact_signal)

    # Blend into a composite worriedness score
    w_approach = float(wcfg.get("approach_weight", 0.65))
    w_contact  = float(wcfg.get("contact_weight", 0.35))
    raw_score  = w_approach * approach_signal + w_contact * contact_signal

    # § WORRY + § AGE_CURVE: age-for-level buffer reduces worriedness
    buf_discount = float(wcfg.get("age_buffer_discount", 0.25))
    avl_buf = age_for_level_buffer(age, level)
    age_discount = min(0.50, avl_buf * buf_discount)  # cap at 50% discount
    final_score = max(0.0, raw_score * (1.0 - age_discount))

    # Determine dominant type
    if approach_signal > 0.3 and contact_signal > 0.3:
        worry_type = "both"
    elif approach_signal > 0.2:
        worry_type = "approach"
    elif contact_signal > 0.2:
        worry_type = "contact_quality"
    else:
        worry_type = "none"

    return {
        "score":            round(final_score, 3),
        "type":             worry_type,
        "approach_signal":  round(approach_signal, 3),
        "contact_signal":   round(contact_signal, 3),
        "age_discount":     round(age_discount, 3),
    }


# ---------------------------------------------------------------------------
# § FLASH: bimodal mixture for "all potential" players
# ---------------------------------------------------------------------------

def flash_assessment(player: dict, level_norms: dict | None = None) -> dict:
    """§ FLASH: compute p_click and the bimodal value distribution arms.

    For players with fv_close_plus=True (the upside marker) we model:
        P(value) = p_click × V_elite + (1 − p_click) × V_floor

    p_click starts at p_click_base and is updated upward by:
      • Pedigree (high bonus → pre-existing selection filter)
      • Observed flash events (peak-window performance above flash threshold)

    This is the Bayesian update on the *ceiling accessibility* parameter,
    separate from the main Kalman update on the *expected* value.
    """
    fcfg = _cfg().get("flash", {})
    fv    = _safe_float(player.get("fv_close"))
    is_pitcher = bool(player.get("is_pitcher"))
    position   = player.get("position")
    age        = _safe_float(player.get("age"))
    fv_plus    = bool(player.get("fv_close_plus"))
    acq        = player.get("acquisition") or {}
    is_pitcher_pos = is_pitcher_position(position)

    # Only run the bimodal model for fv_plus players or high-pedigree prospects
    ped = pedigree_precision(acq)
    is_bimodal = fv_plus or ped >= 1.5

    if not is_bimodal or fv is None:
        return {"is_bimodal": False, "p_click": None, "ceiling_mm": None, "floor_mm": None}

    p_base   = float(fcfg.get("p_click_base", 0.20))
    p_ped    = float(fcfg.get("p_click_pedigree_bonus", 0.12))
    p_flash  = float(fcfg.get("p_click_flash_bonus", 0.22))
    p_max    = float(fcfg.get("p_click_max", 0.80))

    p_click = p_base
    if ped >= 1.5:
        p_click += p_ped

    # Detect flash events from recent statcast data
    statcast = player.get("statcast_metrics") or {}
    cq = (statcast or {}).get("contact_quality") or {}
    standout = (statcast or {}).get("standout_games") or []

    if not is_pitcher_pos:
        peak_xwoba = _safe_float(cq.get("xwoba_est"))
        xwoba_thr  = float(fcfg.get("hitter_peak_xwoba", 0.370))
        if peak_xwoba is not None and peak_xwoba >= xwoba_thr:
            p_click += p_flash
        # Standout game = additional flash signal
        if len(standout) >= 2:
            p_click += p_flash * 0.5
    else:
        statline  = player.get("statline") or {}
        era       = _safe_float(statline.get("era"))
        k_pct     = _safe_float(statline.get("k_pct"))
        era_thr   = float(fcfg.get("pitcher_peak_era", 2.80))
        k_thr     = float(fcfg.get("pitcher_peak_k_pct", 28.0))
        if era is not None and era <= era_thr:
            p_click += p_flash
        if k_pct is not None and k_pct >= k_thr:
            p_click += p_flash * 0.6

    p_click = round(min(p_click, p_max), 3)

    # Bimodal arms: elite = fv + bump, floor = fv - drop
    fv_bump = float(fcfg.get("elite_surplus_fv_bump", 10.0))
    fv_drop = float(fcfg.get("floor_surplus_fv_drop",  8.0))
    ceiling_mm = surplus_value_mm(min(80.0, fv + fv_bump), is_pitcher_pos, position,
                                  age=age) or 0.0
    floor_mm   = surplus_value_mm(max(20.0, fv - fv_drop), is_pitcher_pos, position,
                                  age=age) or 0.0

    return {
        "is_bimodal":  True,
        "p_click":     p_click,
        "ceiling_mm":  round(ceiling_mm, 1),
        "floor_mm":    round(floor_mm, 1),
        "blended_mm":  round(p_click * ceiling_mm + (1 - p_click) * floor_mm, 1),
    }


# ---------------------------------------------------------------------------
# Remaining team control years for debuted players
# ---------------------------------------------------------------------------

_MLB_SERVICE_DAYS_PER_YEAR = 172  # standard MLB service time calendar
_MLB_CONTROL_YEARS = 6            # pre-arb + arb window


def _remaining_control_years(player: dict) -> tuple[float, str]:
    """Compute remaining team-controlled seasons for a debuted player.

    Two components — take the MAX:
      service_control = max(0, debut_year + 6 - today_year)
          A player who debuted in 2025 hits free agency in 2031; regardless
          of whatever arb deal covers the next 3 years, the team controls
          him for 5 more seasons after 2026.
      contract_control = signed_through - today_year + 1
          Long-term extensions (Rafaela, Harris, Witt) extend control beyond
          the standard 6-year window; use the extension length when it's larger.

    The MAX correctly handles:
      Schlittler (debut 2025, arb through 2028): max(5, 3) = 5yr  ✓
      Rafaela (debut 2023, ext through 2032):   max(3, 7) = 7yr  ✓
      Rutschman (debut 2022, ext through 2027): max(2, 2) = 2yr  ✓
      Witt Jr. (debut 2022, ext through 2037):  max(2,12) =12yr  ✓
      Roman Anthony (debut 2025, ext thru 2034):max(5, 9) = 9yr  ✓
    """
    today_year = date.today().year
    contract   = player.get("current_contract") or {}
    roster     = player.get("roster_status")   or {}

    # Service control: debut year + 6 standard FA clock
    svc_ctrl = float(_MLB_CONTROL_YEARS)  # default: unknown debut → assume full
    debut = roster.get("mlb_debut_date") or ""
    if debut:
        try:
            svc_ctrl = max(0.0, float(int(debut[:4]) + _MLB_CONTROL_YEARS - today_year))
        except (TypeError, ValueError):
            pass

    # Contract control: long-term extension may go beyond service control
    contract_ctrl = 0.0
    signed_through = contract.get("signed_through")
    if signed_through:
        try:
            contract_ctrl = max(0.0, float(signed_through) - today_year + 1)
        except (TypeError, ValueError):
            pass

    remaining = max(svc_ctrl, contract_ctrl)
    source    = "contract_ext" if contract_ctrl > svc_ctrl else "debut+6"
    return (remaining, source)


def _aging_factor(age_now: float | None, yr_offset: int, is_pitcher: bool,
                  position: str | None = None) -> float:
    """Simple aging curve: slight growth before peak, decline after.

    Peak ages (empirical): pitchers ~25, hitters ~27.
    Catchers use a faster decline and lower floor — the physical toll of the
    position accelerates aging past the league-average curve.
    """
    if age_now is None:
        return 1.0

    aging_cfg = _cfg().get("aging_curve", {})
    is_catcher = (position is not None and _pos_primary(position) == "C")

    if is_catcher:
        peak          = float(aging_cfg.get("catcher_peak_age",       25.0))
        decline_rate  = float(aging_cfg.get("catcher_decline_per_yr",  0.09))
        min_mult      = float(aging_cfg.get("catcher_min_multiplier",  0.25))
    elif is_pitcher:
        peak          = float(aging_cfg.get("pitcher_peak_age",       25.0))
        decline_rate  = float(aging_cfg.get("pitcher_decline_per_yr",  0.07))
        min_mult      = float(aging_cfg.get("min_multiplier",          0.25))
    else:
        peak          = float(aging_cfg.get("hitter_peak_age",        27.0))
        decline_rate  = float(aging_cfg.get("hitter_decline_per_yr",   0.07))
        min_mult      = float(aging_cfg.get("min_multiplier",          0.25))

    age_at = age_now + yr_offset
    if age_at <= peak:
        return min(1.10, 1.0 + 0.025 * (peak - age_at))
    return max(min_mult, 1.0 - decline_rate * (age_at - peak))


def _estimate_salary_mm(player: dict, year: int, svc_ctrl: float,
                        market_value_mm: float) -> float:
    """Estimate salary for a controlled year when contract data is 0 or absent.

    Priority:
      1. Within a long-term extension window: use contract AAV (guaranteed money).
      2. Pre-arb years: league minimum ($0.78M).
      3. Arb years 1-3: 40/60/80% of market value.
    """
    contract     = player.get("current_contract") or {}
    aav_raw      = contract.get("aav_usd")
    signed_thru  = contract.get("signed_through")
    roster       = player.get("roster_status") or {}
    debut        = roster.get("mlb_debut_date") or ""
    debut_year   = int(debut[:4]) if debut else year - 1
    league_min   = 0.78  # $M

    # Only use AAV as the salary estimate for genuine long-term extensions
    # (AAV > $5M). Pre-arb/arb one-year deals often have salary_by_year=0 for
    # future option years and an AAV that averages in those $0 years — for
    # Volpe ($3.475M/1yr averaged to $1.16M/3 "yrs"), using $1.16M as the
    # 2027-2028 salary massively understates the real ~$12-20M arb cost.
    if signed_thru and aav_raw and float(aav_raw) > 5_000_000:
        if year <= int(signed_thru):
            return round(float(aav_raw) / 1e6, 2)

    # Service-time-based estimation
    svc_at_year = year - debut_year
    if svc_at_year <= 3:
        return league_min
    arb_year_idx = min(2, svc_at_year - 4)
    arb_frac     = [0.40, 0.60, 0.80][arb_year_idx]
    return round(market_value_mm * arb_frac, 2)


_CONTRACT_OPTIONS_CACHE: dict | None = None


def _contract_options() -> dict:
    """Load data/contract_options.json once; return player opt-out data by player_key."""
    global _CONTRACT_OPTIONS_CACHE
    if _CONTRACT_OPTIONS_CACHE is None:
        path = _HERE / "data" / "contract_options.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _CONTRACT_OPTIONS_CACHE = data.get("players") or {}
        except Exception:
            _CONTRACT_OPTIONS_CACHE = {}
    return _CONTRACT_OPTIONS_CACHE


def _p_player_opts_out(market_value_mm: float, salary_mm: float) -> float:
    """§ CONTRACT: probability a player exercises an opt-out at a given year.

    A player opts out when they can get more on the open market than their
    current salary. We model this as a logistic function of the
    surplus ratio (market_value / salary − 1):
      ratio < 0   → no advantage, P(opt) ≈ 0
      ratio = 0.5 → small advantage, P(opt) ≈ 0.30
      ratio = 1.0 → 2× market value, P(opt) ≈ 0.75
      ratio = 2.0 → 3× market value, P(opt) ≈ 0.95
    """
    if salary_mm <= 0 or market_value_mm <= 0:
        return 0.0
    ratio = market_value_mm / salary_mm - 1.0
    # Logistic: P = 1 / (1 + exp(-4 × (ratio - 0.4)))
    # Inflection at ratio ≈ 0.4 (player gets 40% more on market → ~50% chance of opt)
    return round(1.0 / (1.0 + math.exp(-4.0 * (ratio - 0.40))), 3)


def _trial_period_factor(player: dict, skills_auth: float) -> float:
    """Trial-period credibility weight τ ∈ [0.45, 1.0] on the offensive component.

    Early MLB samples are subject to two confounds:
      (A) Small-sample noise — partially handled by the Kalman gain cap.
      (B) Novelty effect — in a player's first season(s) MLB pitchers haven't
          accumulated tendencies data on them. Players who get "figured out"
          (Tyler Fitzgerald type) show inflated early numbers that don't survive
          the first full scouting cycle. Players with genuine underlying skills
          (Valenzuela type: elite approach + elite defense) survive the adjustment.

    τ is applied to the *offensive component* of true_talent_war only.
    The defensive floor is NOT discounted — defense is measurable and real
    from day one, independent of pitcher adjustment cycles.

    Math:
      base(seasons):  0 → 0.55, 1 → 0.75, 2 → 0.90, 3+ → 1.00
      quality:        high auth (xwOBA/BB% supports results) → up to +15%
                      low auth (BABIP-driven) → down to -20%
      floor_shield:   C/SS/CF with above-avg defense → 30% of remaining
                      discount absorbed by positional floor guarantee
    """
    cw          = player.get("career_war") or {}
    war_seasons = int(cw.get("war_seasons_count") or 0)
    position    = player.get("position") or ""
    tools       = player.get("tools") or {}

    if war_seasons >= 3:
        return 1.0  # past trial period

    # Base credibility by season count.
    # 0 seasons: heavy novelty effect — pitchers haven't seen the player.
    # 1 season:  book is partly out; adjustments partly made.
    # 2 seasons: most holes have been found; production is largely real.
    base = [0.45, 0.65, 0.83][war_seasons]

    # § PEDIGREE-AWARE TRIAL: players with strong prospect pedigree (large signing
    # bonus, top draft pick) have been evaluated by professionals before their MLB
    # debut — that prior evidence reduces the trial-period uncertainty.
    # Low-pedigree players (Brad Lord $125k, Valenzuela unknown) have zero
    # independent verification → trial should be stricter.
    acq = player.get("acquisition") or {}
    bonus = _safe_float(acq.get("bonus_usd"), 0) or 0
    # pedigree signal: 0 at <$100k (walk-on/undrafted), 1 at >$5M (elite prospect)
    ped_signal = min(1.0, math.log10(max(1, bonus) / 100_000) / 1.7)  # log scale
    # Pedigree modifier: no pedigree → base × 0.80 (20% steeper discount)
    #                    elite pedigree → base × 1.10 (10% lighter discount)
    ped_mod = 0.80 + 0.30 * ped_signal   # range [0.80, 1.10]
    base = base * ped_mod

    # Quality modifier: high-auth performance survives figuring-out; BABIP luck doesn't
    quality_mod = 1.0 + (skills_auth - 0.65) * 0.50
    quality_mod = max(0.75, min(1.18, quality_mod))

    tau = base * quality_mod

    # Position floor shield: premium defensive positions absorb some of the discount
    # because their defensive contribution is real and proven even in small samples.
    pos_primary = _pos_primary(position)
    def_grade_raw = tools.get("defense") or tools.get("DEF")
    def_grade = _safe_float(def_grade_raw) or (55.0 if pos_primary in ("C", "SS", "CF") else 45.0)

    if pos_primary in ("C", "SS", "CF") and def_grade >= 55.0:
        shield = 0.30 * (1.0 - tau)   # absorb 30% of the remaining discount
        tau = tau + shield

    return round(min(1.0, max(0.45, tau)), 3)


def _gross_war_pv(true_talent_war: float, remaining_years: float,
                  age: float | None, is_pitcher: bool,
                  position: str | None = None) -> float:
    """§ GROSS_FLOOR: PV of gross WAR production over remaining controlled years.

    Unlike _contract_surplus_mm, this does NOT subtract salary. It represents
    the market cost to acquire equivalent production — the floor below which
    trade value cannot fall for a productive player, even when their contract
    is above market rate.
    """
    if remaining_years <= 0 or not true_talent_war:
        return 0.0
    discount  = 0.09
    inflation = 0.05
    total = 0.0
    for yr_offset in range(1, int(remaining_years) + 1):
        af  = _aging_factor(age, yr_offset, is_pitcher, position)
        war = max(0.0, true_talent_war * af)
        raw_mv = tiered_war_value_usd(war) / 1e6
        mv     = raw_mv * (1.0 + inflation) ** yr_offset
        total += mv / (1.0 + discount) ** yr_offset
    return round(total, 1)


def _contract_surplus_mm(player: dict, true_talent_war: float,
                         remaining_years: float) -> float:
    """§ CONTRACT: compute surplus value over remaining controlled years.

    surplus = Σ_yr  max(0, market_value(war × aging) − salary) / (1+r)^yr
              × P(player still employed in yr)

    P(still employed) accounts for player opt-outs: if a player has an opt-out
    in year Y and their market value >> salary, there is a high probability they
    leave, so surplus in years Y+1, Y+2, … should be discounted accordingly.

    Club options work in the team's favor: the team exercises if market_value >
    option_price, so those years add to expected surplus.
    """
    if remaining_years <= 0 or true_talent_war is None:
        return 0.0

    contract     = player.get("current_contract") or {}
    salary_by_yr = contract.get("salary_by_year") or {}
    is_pitcher   = bool(player.get("is_pitcher")) or is_pitcher_position(player.get("position"))
    age_now      = _safe_float(player.get("age"))
    today_year   = date.today().year
    discount     = 0.09
    inflation    = 0.05

    roster      = player.get("roster_status") or {}
    debut       = roster.get("mlb_debut_date") or ""
    debut_year  = int(debut[:4]) if debut else today_year

    # Load opt-out data for this player (if any)
    opts_data   = _contract_options()
    player_key  = player.get("player_key") or ""
    player_name = (player.get("player_name") or "").lower().replace(" ", "_").replace(".", "")
    opt_entry   = opts_data.get(player_key) or opts_data.get(player_name) or {}
    player_opt_years = set(opt_entry.get("player_options") or [])
    club_opt_years   = {c["year"]: c.get("price_usd", 0)
                        for c in (opt_entry.get("club_options") or [])}

    # P(player still here in year Y) — cumulative probability not yet opted out
    p_still_here = 1.0

    total = 0.0
    for yr_offset in range(1, int(remaining_years) + 1):
        year = today_year + yr_offset

        # Projected WAR with aging curve
        af  = _aging_factor(age_now, yr_offset, is_pitcher, player.get("position"))
        war = max(0.0, true_talent_war * af)

        # Market value (with $/WAR inflation)
        raw_mv = tiered_war_value_usd(war) / 1e6
        mv     = raw_mv * (1.0 + inflation) ** yr_offset

        # Salary: known if non-zero in Spotrac data, else estimated
        sal_raw = salary_by_yr.get(str(year))
        if sal_raw and float(sal_raw) > 0:
            sal = float(sal_raw) / 1e6
        else:
            sal = _estimate_salary_mm(player, year, remaining_years, mv)

        # § CONTRACT: club options — team exercises if market_value > option price
        if year in club_opt_years:
            option_price_mm = club_opt_years[year] / 1e6
            if mv > option_price_mm:
                sal = option_price_mm  # team picks it up at the set price
            else:
                break  # team won't exercise → no more control

        # § SP DURABILITY PREMIUM: proven starters (150+ IP in a season) carry a
        # transaction premium because demonstrated workload capacity is scarce.
        # Kirby type: consistently eats innings even through a rough ERA patch.
        _RP_TAGS = {"RP", "CL", "SIRP", "MIRP"}
        _pos_str = _pos_primary(player.get("position"))
        _is_sp_type = is_pitcher and _pos_str not in _RP_TAGS
        _sp_dur_bonus = 0.0
        if _is_sp_type:
            _sp_cs = player.get("career_stats") or []
            _max_ip = max(
                (float(s.get("ip") or 0) for s in _sp_cs if (s.get("level") or "") == "MLB"),
                default=0.0
            )
            if _max_ip >= 150:
                _sp_dur_bonus = min(0.08, (_max_ip - 150) / 600)

        # § TRADABILITY DISCOUNT for back-end expensive years: in trade discussions
        # teams heavily discount years 4+ of a large extension because
        #   (a) health and production risk compound with age
        #   (b) NTC provisions become common for veterans → limits trade market
        #   (c) large salary obligations are hard to absorb as part of a trade
        # The discount is zero for years 1-3, then escalates by 5% per additional
        # year, scaled by how expensive the salary is relative to a baseline ($15M).
        # A $22M/yr back-end year (Hoerner 2031) gets ~25% tradability discount.
        if yr_offset >= 4 and sal > 8.0:
            # Scale: 0 at $8M (arb-level), 1 at $25M (veteran extension level)
            salary_scale  = min(1.0, (sal - 8.0) / 17.0)
            years_past_3  = yr_offset - 3
            # 7% per year past year 3, scaled by salary level; cap at 50%
            tradability_d = min(0.50, 0.07 * years_past_3 * salary_scale)
            mv = mv * (1.0 - tradability_d)                 # reduce effective market value

        # § CONTRACT: player opt-outs — if the player can get more on the open
        # market, they opt out. We model this probabilistically to get an expected
        # value, NOT a binary scenario. P(opts out in yr Y) depends on surplus ratio.
        if year in player_opt_years:
            p_opt = _p_player_opts_out(mv, sal)
            # Expected surplus THIS year: still happens (player is here pre-opt)
            annual_surplus = max(0.0, mv - sal)
            total += annual_surplus * p_still_here / (1.0 + discount) ** yr_offset
            # Update cumulative P(still here) for future years
            p_still_here *= (1.0 - p_opt)
            if p_still_here < 0.02:
                break  # negligible probability of being employed → stop
            continue

        # Allow negative surplus: when salary exceeds market value (player overpaid
        # vs. his production), that's a real cost to the acquiring team. The old
        # floor at $0 was artificially inflating long extensions with bad back-ends.
        annual_surplus = mv * (1.0 + _sp_dur_bonus) - sal
        total += annual_surplus * p_still_here / (1.0 + discount) ** yr_offset

    # Allow negative totals: underwater contracts are real trade liabilities.
    return round(total, 1)


def _injury_discount(player: dict) -> float:
    """§ INJURY: structural discount for players with significant IL history.

    Goes beyond worriedness (which tracks performance decay) to capture
    players who miss substantial time recurrently — the Alvarez type.
    Returns a discount in [0, 0.25].
    """
    roster  = player.get("roster_status") or {}
    il_hist = roster.get("injury_history") or []

    # Weight recent injuries more (last 2 seasons)
    today_year = date.today().year
    weighted_days = 0.0
    for il in il_hist:
        days = il.get("days") or 0
        if il.get("active") and not days:
            typ = str(il.get("type") or "").lower()
            days = 100 if "60" in typ else 45 if "15" in typ or "10" in typ else 30
        since = str(il.get("since") or "")
        try:
            il_year = int(since[:4])
            recency_weight = 2.0 if today_year - il_year <= 1 else 1.0
        except (TypeError, ValueError):
            recency_weight = 1.0
        weighted_days += days * recency_weight

    # Thresholds: < 30 days → no discount; 30-80 → small; 80-150 → medium; 150+ → large
    if weighted_days < 30:
        return 0.0
    elif weighted_days < 80:
        return round(0.04 * (weighted_days - 30) / 50, 3)
    elif weighted_days < 150:
        return round(0.04 + 0.10 * (weighted_days - 80) / 70, 3)
    else:
        return 0.20  # severe recurrent injury history


def _has_active_injury(player: dict) -> bool:
    roster = player.get("roster_status") or {}
    return any(bool(il.get("active")) for il in (roster.get("injury_history") or []))


def _has_top100_pedigree(player: dict) -> bool:
    # v47 - the export bakes `top100_pedigree: true` on the player payload
    # (omitted when False), computed with EXACTLY this label walk at export
    # time, because tools.history is no longer shipped in the artifact.
    # Prefer the baked flag; the walk below stays as the fallback for
    # pre-v47 artifacts (where it must OR across BOTH tools.history and
    # tools.source_history - a history-only walk under-fires).
    if player.get("top100_pedigree"):
        return True
    tools = player.get("tools") or {}
    labels: list[str] = []
    for row in tools.get("history") or []:
        labels.append(str(row.get("interval_label") or ""))
    for rows in (tools.get("source_history") or {}).values():
        for row in rows or []:
            labels.append(str(row.get("interval_label") or ""))
    return any("top 100" in label.lower() or "top100" in label.lower() for label in labels)


def _current_mlb_statline_row(player: dict) -> dict:
    statline = player.get("statline") or {}
    if (
        str(statline.get("level") or "").upper() == "MLB"
        and not bool(statline.get("is_prior_season"))
    ):
        return statline
    current_year = date.today().year
    for row in player.get("career_stats") or []:
        if str(row.get("level") or "").upper() != "MLB":
            continue
        if int(_safe_float(row.get("season"), 0.0) or 0.0) == current_year:
            return row
    return {}


def _current_pitcher_bad_trial(player: dict) -> bool:
    row = _current_mlb_statline_row(player)
    if not row:
        return False
    ip = _safe_float(row.get("ip"), 0.0) or 0.0
    if ip < 8.0:
        return False
    k_pct = _safe_float(row.get("k_pct"), 0.0) or 0.0
    bb_pct = _safe_float(row.get("bb_pct"), 0.0) or 0.0
    era_minus = _safe_float(row.get("era_minus_level"), 100.0) or 100.0
    level_plus = _safe_float(row.get("level_plus_pct"), 0.0) or 0.0
    stf_plus = _safe_float(row.get("stf_plus_periph"), 100.0) or 100.0
    whip = _safe_float(row.get("whip"), 0.0) or 0.0
    return (
        (k_pct <= 18.0 and bb_pct >= 14.0)
        or stf_plus <= 85.0
        or era_minus >= 160.0
        or level_plus <= -60.0
        or whip >= 1.80
    )


# ---------------------------------------------------------------------------
# § ARCHETYPE_POLICY: centralized group-level trade-value policy
# ---------------------------------------------------------------------------

def _mlb_playing_time(player: dict, is_pitcher: bool) -> dict:
    """Return MLB playing-time signals from career_stats.

    The trade-value policy needs rough trial-period gates (PA/IP), not precise
    service accounting. We therefore use the fields already available in the
    export and degrade gracefully when a row lacks PA/IP.
    """
    rows = player.get("career_stats") or []
    total_pa = 0.0
    total_ip = 0.0
    max_ip = 0.0
    max_games = 0.0
    for r in rows:
        if (r.get("level") or "") != "MLB":
            continue
        ip = _safe_float(r.get("ip") or r.get("IP"), 0.0) or 0.0
        pa = (_safe_float(r.get("pa") or r.get("PA"), None) or
              _safe_float(r.get("ab") or r.get("AB"), None) or 0.0)
        games = _safe_float(r.get("games") or r.get("g") or r.get("G"), 0.0) or 0.0
        if not is_pitcher and pa <= 0 and games > 0:
            pa = games * 4.0
        total_pa += pa
        total_ip += ip
        max_ip = max(max_ip, ip)
        max_games = max(max_games, games)
    if is_pitcher:
        stat_ip = _safe_float((player.get("statline") or {}).get("ip"), 0.0) or 0.0
        total_ip = max(total_ip, stat_ip)
        max_ip = max(max_ip, stat_ip)
    else:
        stat_pa = (_safe_float((player.get("statline") or {}).get("pa"), None) or
                   _safe_float((player.get("statline") or {}).get("ab"), None) or 0.0)
        total_pa = max(total_pa, stat_pa)
    return {
        "total_pa": round(total_pa, 1),
        "total_ip": round(total_ip, 1),
        "max_ip": round(max_ip, 1),
        "max_games": round(max_games, 1),
    }


def _mlb_exposure_by_season(player: dict, is_pitcher: bool) -> dict[int, float]:
    """Return MLB PA/IP exposure by season for WAR-rate weighting."""
    out: dict[int, float] = {}
    for r in player.get("career_stats") or []:
        if (r.get("level") or "") != "MLB":
            continue
        try:
            season = int(r.get("season"))
        except (TypeError, ValueError):
            continue
        if is_pitcher:
            exposure = _safe_float(r.get("ip") or r.get("IP"), 0.0) or 0.0
        else:
            exposure = (
                _safe_float(r.get("pa") or r.get("PA"), None)
                or _safe_float(r.get("ab") or r.get("AB"), None)
                or 0.0
            )
            games = _safe_float(r.get("games") or r.get("g") or r.get("G"), 0.0) or 0.0
            if exposure <= 0 and games > 0:
                exposure = games * 4.0
        out[season] = out.get(season, 0.0) + exposure
    return out


def _full_season_exposure(player: dict, is_pitcher: bool, position: str | None) -> float:
    """Return role-specific full-season PA/IP denominator for WAR rates."""
    pos = _pos_primary(position)
    if is_pitcher:
        return 45.0 if pos in {"RP", "CL", "SIRP", "MIRP"} else 150.0
    return 380.0 if pos == "C" else 600.0


def _exposure_weighted_career_war(
    player: dict,
    is_pitcher: bool,
    position: str | None = None,
) -> tuple[float | None, float, dict[int, float]]:
    """Downweight cup-of-coffee WAR seasons in the career baseline.

    `career_war.war_per_yr` counts every MLB season equally, so a 16-IP cameo can
    drag a two-season player as much as a real current-season run. This returns a
    season-exposure weighted WAR rate plus the fractional season weights used.
    """
    cwar = player.get("career_war") or {}
    seasons = cwar.get("seasons") or {}
    if not seasons:
        return None, 0.0, {}

    exposure_by_season = _mlb_exposure_by_season(player, is_pitcher)
    full_ref = _full_season_exposure(player, is_pitcher, position)
    weights: dict[int, float] = {}
    total_war = 0.0
    total_weight = 0.0
    for year_raw, war_raw in seasons.items():
        try:
            year = int(year_raw)
            war = float(war_raw)
        except (TypeError, ValueError):
            continue
        exposure = exposure_by_season.get(year)
        if exposure is None:
            weight = 1.0
        else:
            weight = max(0.05, min(1.0, exposure / full_ref))
        weights[year] = weight
        total_war += war
        total_weight += weight

    if total_weight <= 0:
        return None, 0.0, weights
    return total_war / total_weight, total_weight, weights


def _stuff_or_league_avg(pitch: dict) -> float:
    """tjStuff+ for one pitch row, defaulting to the 100 league anchor ONLY when
    the value is genuinely absent.

    `is None`, not `or`: tjStuff+ is an indexed metric whose scale reaches 0, and
    a pitch graded 0.0 is the WORST possible offering, not a missing reading. The
    prior `(pitch.get("avg_stuff_plus") or 100.0)` promoted that pitch to exactly
    league average, which is the largest possible error the guard could make.
    """
    v = (pitch or {}).get("avg_stuff_plus")
    if v is None:
        return 100.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 100.0


def _pitcher_stuff_summary(player: dict) -> dict:
    """Summarize pitch-level Stuff+ where available."""
    pm = ((player.get("statcast_metrics") or {}).get("pitch_movement") or {})
    pitches = pm.get("pitch_summary") or []
    if not pitches:
        return {"has_data": False, "primary_stuff_plus": None, "weighted_stuff_plus": None}
    primary = max(pitches, key=lambda p: p.get("usage_pct") or 0, default={})
    total_usage = sum(p.get("usage_pct") or 0 for p in pitches) or 1.0
    weighted = sum(_stuff_or_league_avg(p) * (p.get("usage_pct") or 0)
                   for p in pitches) / total_usage
    return {
        "has_data": True,
        "primary_stuff_plus": round(_stuff_or_league_avg(primary), 1),
        "weighted_stuff_plus": round(float(weighted), 1),
    }


def _pitcher_starter_workload(player: dict, playing_time: dict | None = None) -> bool:
    """Infer starter role for generic pitcher labels from MLB workload shape."""
    if playing_time is None:
        playing_time = _mlb_playing_time(player, True)
    age = _safe_float(player.get("age"), None)
    statline = player.get("statline") or {}
    if str(statline.get("level") or "").upper() == "MLB":
        cur_ip = _safe_float(statline.get("ip"), 0.0) or 0.0
        cur_games = _safe_float(statline.get("games"), 0.0) or 0.0
        if cur_games >= 8.0 and cur_ip >= 8.0 and (cur_ip / cur_games) < 2.7:
            return False
        if cur_games >= 15.0 and cur_ip >= 15.0 and (cur_ip / cur_games) < 3.0:
            return False
        if age is not None and age <= 25.5 and cur_games >= 3.0 and cur_ip >= 12.0 and (cur_ip / cur_games) >= 4.0:
            return True
    if (playing_time.get("max_ip") or 0.0) >= 80.0:
        return True

    rows = list(player.get("career_stats") or [])
    if statline:
        rows.append({"level": "MLB", **statline})

    for r in rows:
        if (r.get("level") or "MLB") != "MLB":
            continue
        ip = _safe_float(r.get("ip") or r.get("IP"), 0.0) or 0.0
        games = _safe_float(r.get("games") or r.get("g") or r.get("G"), 0.0) or 0.0
        if games >= 8.0 and ip >= 40.0 and (ip / games) >= 4.0:
            return True
        if games >= 10.0 and ip >= 50.0 and (ip / games) >= 3.2:
            return True

    return (
        (playing_time.get("total_ip") or 0.0) >= 120.0
        and (playing_time.get("max_ip") or 0.0) >= 50.0
    )


def _hitter_offense_supported(player: dict, cfg: dict) -> bool:
    """True when current offensive underlyings support a breakout floor."""
    statline = player.get("statline") or {}
    cq = ((player.get("statcast_metrics") or {}).get("contact_quality") or {})
    xwoba = _safe_float(cq.get("xwoba_est"))
    iso = _safe_float(statline.get("iso"))
    barrel = _safe_float(cq.get("barrel_pct"))

    checks = []
    min_xwoba = cfg.get("min_xwoba_est")
    min_iso = cfg.get("min_iso")
    min_barrel = cfg.get("min_barrel_pct")
    if min_xwoba is not None and xwoba is not None:
        checks.append(xwoba >= float(min_xwoba))
    if min_iso is not None and iso is not None:
        checks.append(iso >= float(min_iso))
    if min_barrel is not None and barrel is not None:
        checks.append(barrel >= float(min_barrel))

    # If there is no current batted-ball support, do not award a breakout floor.
    if not checks:
        return False
    min_supported = int(cfg.get("min_supported_metrics", 1))
    return sum(1 for ok in checks if ok) >= min_supported


def _hitter_current_offense_bad(player: dict, cfg: dict) -> bool:
    """True when current MLB batted-ball quality is actively undermining the prior."""
    statline = player.get("statline") or {}
    cq = ((player.get("statcast_metrics") or {}).get("contact_quality") or {})
    xwoba = _safe_float(cq.get("xwoba_est"))
    iso = _safe_float(statline.get("iso"))
    barrel = _safe_float(cq.get("barrel_pct"))
    if xwoba is None or iso is None or barrel is None:
        return False
    return (
        xwoba <= float(cfg.get("max_xwoba_est", 0.300))
        and iso <= float(cfg.get("max_iso", 0.130))
        and barrel <= float(cfg.get("max_barrel_pct", 5.5))
    )


def _current_salary_mm(player: dict) -> float:
    contract = player.get("current_contract") or {}
    salary = _safe_float(contract.get("salary_usd"), None)
    if salary is None:
        salary_by_year = contract.get("salary_by_year") or {}
        salary = _safe_float(salary_by_year.get(str(date.today().year)), None)
    if salary is None:
        aav = _safe_float(contract.get("aav_usd"), None)
        if aav is not None and aav > 0:
            salary = aav
    if salary is None:
        prev_aav = _fa_prev_aav_mm(player)
        if prev_aav is not None:
            return prev_aav
    return (salary or 0.0) / 1_000_000.0


def _has_active_arm_injury(player: dict) -> bool:
    roster = player.get("roster_status") or {}
    for il in roster.get("injury_history") or []:
        if not il.get("active"):
            continue
        txt = f"{il.get('reason') or ''} {il.get('description') or ''}".lower()
        if any(term in txt for term in ("ucl", "elbow", "forearm", "shoulder", "arm")):
            return True
    return False


def archetype_policy_adjustment(
    player: dict,
    *,
    is_mlb_player: bool,
    is_pitcher: bool,
    position: str | None,
    age: float | None,
    fv: float | None,
    prior_surplus_mm: float,
    posterior_surplus_mm: float,
    true_talent_war: float | None,
    remaining_control_years: float | None,
    authenticity: float,
    worriedness: dict,
) -> dict:
    """Centralized archetype policy for trade-value calibration.

    This layer deliberately returns small, auditable operations:
      * posterior_floor_mm: do not let noisy early MLB evidence erase a group
        whose prior should remain informative.
      * posterior_multiplier: group-level boost/discount for scarcity/risk that
        is not captured by raw WAR surplus.
      * tags: emitted to JSON so future backtests can score policy by group.
    """
    out = {
        "tags": [],
        "posterior_floor_mm": 0.0,
        "posterior_multiplier": 1.0,
        "features": {},
    }
    cfg = _cfg().get("archetype_policy", {})
    if not cfg.get("enabled", False) or not is_mlb_player:
        return out

    pos = _pos_primary(position)
    age_v = float(age) if age is not None else 99.0
    fv_v = float(fv) if fv is not None else 0.0
    tt_war = float(true_talent_war or 0.0)
    ctrl = float(remaining_control_years or 0.0)
    worry_score = float((worriedness or {}).get("score") or 0.0)
    playing_time = _mlb_playing_time(player, is_pitcher)
    statline = player.get("statline") or {}
    current_salary_mm = _current_salary_mm(player)
    active_injury = _has_active_injury(player)
    active_arm_injury = _has_active_arm_injury(player)
    current_mlb_row = _current_mlb_statline_row(player)
    current_mlb_statline = bool(current_mlb_row)
    starter_workload = is_pitcher and (pos == "SP" or _pitcher_starter_workload(player, playing_time))
    stale_prior_cfg = cfg.get("stale_mlb_prior", {})
    stale_mlb_prior = (
        not is_pitcher
        and age_v >= float(stale_prior_cfg.get("min_age", 28.0))
        and playing_time["total_pa"] >= float(stale_prior_cfg.get("min_pa", 1500.0))
    )
    stuff = _pitcher_stuff_summary(player) if is_pitcher else {
        "has_data": False,
        "primary_stuff_plus": None,
        "weighted_stuff_plus": None,
    }
    tools = player.get("tools") or {}
    composite_stuff_plus = _safe_float(tools.get("composite_stuff_plus"))

    out["features"] = {
        "primary_position": pos,
        "mlb_pa": playing_time["total_pa"],
        "mlb_ip": playing_time["total_ip"],
        "validated_ip": max(playing_time["total_ip"], playing_time["max_ip"]),
        "stale_mlb_prior": stale_mlb_prior,
        "current_salary_mm": round(current_salary_mm, 2),
        "active_injury": active_injury,
        "active_arm_injury": active_arm_injury,
        "current_mlb_statline": current_mlb_statline,
        "starter_workload": starter_workload,
        "primary_stuff_plus": stuff["primary_stuff_plus"],
        "weighted_stuff_plus": stuff["weighted_stuff_plus"],
        "composite_stuff_plus": composite_stuff_plus,
    }

    def _tag(name: str) -> None:
        if name not in out["tags"]:
            out["tags"].append(name)

    if stale_mlb_prior:
        _tag("stale_mlb_prior")

    def _floor_from_prior(name: str, pct: float) -> None:
        if stale_mlb_prior:
            _tag("stale_mlb_prior")
            return
        _tag(name)
        out["posterior_floor_mm"] = max(
            float(out["posterior_floor_mm"]),
            prior_surplus_mm * float(pct),
        )

    def _floor_from_fv(name: str, fv_anchor: float) -> None:
        """A floor anchored to a GRADE, priced through the live valuation engine.

        Replaces four hardcoded dollar floors (65/62/58/65) on 2026-07-31, owner
        decision, docs/efv-2026-07-30/TRADE_ARCHETYPE_FLOOR_GATE.md.

        WHY NOT A PERCENTAGE OF THE PRIOR, which was the obvious candidate: the
        measured floor/prior ratios on the rows these tag are 0.76 to 4.77 and, in
        one case, 92.86. They are not a disguised percentage, and a percentage would
        destroy the only thing they are for. Mason Miller is the proof: his FV prior
        prices at $0.7M, so ANY multiple of it is still nothing, and the floor
        exists precisely because that prior has failed. A floor whose job is to
        override a broken prior cannot be defined in terms of that prior.

        WHY NOT KEEP DOLLARS: they were calibrated against the v5 price scale and
        did not move when surplus became an expected value, so they quietly lost
        strictness while every number around them rose. An absolute dollar guardrail
        silently loosens every time the currency it guards is re-scaled.

        A GRADE is the stable meaning. "This archetype is worth at least a FV-58
        pitcher" survives a re-price by construction, because the engine re-prices
        FV-58 too. The anchors below are the exact FV each old dollar figure
        represented on the v5 pitcher table, so this is a re-expression and not a
        re-calibration: 65.0 -> FV 58.73, 62.0 -> 58.28, 58.0 -> 57.69.
        """
        _tag(name)
        try:
            val = float(surplus_value_mm(float(fv_anchor), True) or 0.0)
        except Exception:
            return
        out["posterior_floor_mm"] = max(float(out["posterior_floor_mm"]), val)

    def _mult(name: str, mult: float) -> None:
        _tag(name)
        out["posterior_multiplier"] *= float(mult)

    yp = cfg.get("young_premium_confirming", {})
    if (age_v <= float(yp.get("max_age", 22.5))
            and fv_v >= float(yp.get("min_fv", 55.0))
            and ctrl >= float(yp.get("min_control_years", 6.0))
            and pos in set(yp.get("premium_positions", ["C", "SS", "CF"]))):
        _floor_from_prior("young_premium_confirming",
                          float(yp.get("posterior_floor_prior_pct", 0.82)))

    ypp = cfg.get("young_peak_plateau", {})
    if (age_v <= float(ypp.get("max_age", 24.5))
            and fv_v >= float(ypp.get("min_fv", 58.0))
            and ctrl >= float(ypp.get("min_control_years", 6.0))
            and tt_war <= float(ypp.get("max_true_talent_war", 2.0))):
        _floor_from_prior("young_peak_plateau",
                          float(ypp.get("posterior_floor_prior_pct", 0.55)))

    opb = cfg.get("older_pedigree_breakout", {})
    if (not is_pitcher
            and age_v >= float(opb.get("min_age", 25.0))
            and age_v <= float(opb.get("max_age", 29.5))
            and fv_v >= float(opb.get("min_fv", 50.0))
            and tt_war >= float(opb.get("min_true_talent_war", 1.5))
            and authenticity >= float(opb.get("min_authenticity", 0.75))
            and _hitter_offense_supported(player, opb)):
        _floor_from_prior("older_pedigree_breakout",
                          float(opb.get("posterior_floor_prior_pct", 0.50)))

    yrh = cfg.get("young_rookie_hitter_confirming", {})
    if (not is_pitcher
            and age_v <= float(yrh.get("max_age", 24.5))
            and fv_v >= float(yrh.get("min_fv", 52.0))
            and playing_time["total_pa"] >= float(yrh.get("min_pa", 150.0))
            and playing_time["total_pa"] <= float(yrh.get("max_pa", 500.0))
            and (_safe_float(statline.get("k_pct"), 99.0) or 99.0) <= float(yrh.get("max_k_pct", 25.0))
            and (_safe_float(statline.get("bb_pct"), 0.0) or 0.0) >= float(yrh.get("min_bb_pct", 6.0))
            and (
                (_safe_float(statline.get("iso"), 0.0) or 0.0) >= float(yrh.get("min_iso", 0.120))
                or _hitter_offense_supported(player, yrh)
            )):
        _floor_from_prior("young_rookie_hitter_confirming",
                          float(yrh.get("posterior_floor_prior_pct", 0.65)))

    ccb = cfg.get("cheap_control_breakout_hitter", {})
    if (not is_pitcher
            and not stale_mlb_prior
            and age_v <= float(ccb.get("max_age", 28.0))
            and ctrl >= float(ccb.get("min_control_years", 2.0))
            and current_salary_mm <= float(ccb.get("max_current_salary_mm", 5.0))
            and tt_war >= float(ccb.get("min_true_talent_war", 1.5))
            and _hitter_offense_supported(player, ccb)):
        _mult("cheap_control_breakout_hitter",
              float(ccb.get("posterior_multiplier", 1.15)))

    olp = cfg.get("older_low_prior_breakout", {})
    if (not is_pitcher
            and age_v >= float(olp.get("min_age", 22.5))
            and fv_v <= float(olp.get("max_fv", 47.5))):
        has_full_trial = playing_time["total_pa"] >= float(olp.get("min_pa", 500.0))
        ratio = posterior_surplus_mm / max(1e-6, prior_surplus_mm)
        if (not has_full_trial
                and ratio >= float(olp.get("max_posterior_prior_pct_before_discount", 1.75))):
            small_sample_mult = float(olp.get("posterior_multiplier", 0.88))
            if age_v >= 27.0 and playing_time["total_pa"] < 500.0:
                small_sample_mult = min(small_sample_mult, 0.55)
            _mult("older_low_prior_breakout_trial", small_sample_mult)

    ppb = cfg.get("premium_position_breakout", {})
    if (not is_pitcher
            and age_v <= float(ppb.get("max_age", 29.5))
            and pos in set(ppb.get("positions", ["C", "SS", "CF"]))
            and tt_war >= float(ppb.get("min_true_talent_war", 2.2))
            and _hitter_offense_supported(player, ppb)):
        _floor_from_prior("premium_position_breakout",
                          float(ppb.get("posterior_floor_prior_pct", 0.55)))

    hpua = cfg.get("high_prior_mlb_underachiever", {})
    high_prior_underachiever = (
        not is_pitcher
        and fv_v >= float(hpua.get("min_fv", 55.0))
        and playing_time["total_pa"] >= float(hpua.get("min_pa", 1500.0))
        and tt_war <= float(hpua.get("max_true_talent_war", 2.5))
        and _hitter_current_offense_bad(player, hpua)
    )
    if high_prior_underachiever:
        _mult("high_prior_mlb_underachiever",
              float(hpua.get("posterior_multiplier", 0.45)))

    conp = cfg.get("current_offense_not_supporting_prior", {})
    if (not high_prior_underachiever
            and not is_pitcher
            and fv_v >= float(conp.get("min_fv", 55.0))
            and playing_time["total_pa"] >= float(conp.get("min_pa", 300.0))
            and _hitter_current_offense_bad(player, conp)):
        _mult("current_offense_not_supporting_prior",
              float(conp.get("posterior_multiplier", 0.72)))

    if (not is_pitcher
            and pos in {"LF", "RF", "OF", "1B", "DH"}
            and age_v >= 26.0
            and fv_v <= 50.0
            and playing_time["total_pa"] >= 900.0):
        cq = ((player.get("statcast_metrics") or {}).get("contact_quality") or {})
        xwoba = _safe_float(cq.get("xwoba_est"), 0.0) or 0.0
        iso = _safe_float(statline.get("iso"), 0.0) or 0.0
        ops_plus = _level_plus(statline) or 0.0
        if xwoba < 0.360 and iso < 0.220 and ops_plus < 125.0:
            _mult("low_prior_corner_bat_not_elite",
                  0.72)

    if (not is_pitcher
            and pos not in {"C", "SS", "CF"}
            and age_v >= 25.0
            and fv_v <= 45.0
            and playing_time["total_pa"] >= 500.0
            and tt_war <= 2.2):
        cq = ((player.get("statcast_metrics") or {}).get("contact_quality") or {})
        xwoba = _safe_float(cq.get("xwoba_est"), 0.0) or 0.0
        barrel = _safe_float(cq.get("barrel_pct"), 0.0) or 0.0
        iso = _safe_float(statline.get("iso"), 0.0) or 0.0
        ops_plus = _level_plus(statline) or 0.0
        if (
            ops_plus <= 105.0
            and iso <= 0.170
            and (
                xwoba <= 0.300
                or barrel <= 5.0
            )
        ):
            _mult("low_prior_mlb_bat_not_impact", 0.62)
            out["features"]["suppress_additive_floors"] = True

    pvs = cfg.get("productive_veteran_slugger", {})
    if (not is_pitcher
            and age_v >= float(pvs.get("min_age", 29.0))
            and pos in set(pvs.get("positions", ["1B", "LF", "RF", "OF", "DH"]))
            and tt_war >= float(pvs.get("min_true_talent_war", 3.0))
            and worry_score <= float(pvs.get("max_worriedness", 0.20))):
        _mult("productive_veteran_slugger",
              float(pvs.get("posterior_multiplier", 1.08)))

    cps = cfg.get("command_pitcher_small_sample", {})
    validated_ip = max(playing_time["total_ip"], playing_time["max_ip"])
    if (is_pitcher
            and starter_workload
            and age_v >= float(cps.get("min_age", 26.0))
            and validated_ip < float(cps.get("max_validated_ip", 160.0))
            and fv_v <= float(cps.get("max_fv", 47.5))
            and (
                (stuff["has_data"]
                 and (stuff["primary_stuff_plus"] or 100.0) < float(cps.get("low_primary_stuff_plus", 95.0)))
                or (stuff["has_data"]
                    and (stuff["weighted_stuff_plus"] or 100.0) <= float(cps.get("max_weighted_stuff_plus", 100.0))
                    and composite_stuff_plus is not None
                    and composite_stuff_plus <= float(cps.get("max_composite_stuff_plus", 90.0)))
            )):
        _mult("command_pitcher_small_sample",
              float(cps.get("posterior_multiplier", 0.82)))

    ssp = cfg.get("stuff_supported_pitcher", {})
    stat_k = _safe_float(statline.get("k_pct"), 0.0) or 0.0
    stat_bb = _safe_float(statline.get("bb_pct"), 99.0) or 99.0
    if (is_pitcher
            and age_v <= float(ssp.get("max_age", 28.5))
            and fv_v >= float(ssp.get("min_fv", 50.0))
            and (stuff["primary_stuff_plus"] or 0.0) >= float(ssp.get("min_primary_stuff_plus", 105.0))
            and (stuff["weighted_stuff_plus"] or 0.0) >= float(ssp.get("min_weighted_stuff_plus", 104.0))
            and stat_k >= float(ssp.get("min_k_pct", 25.0))
            and stat_bb <= float(ssp.get("max_bb_pct", 8.0))):
        _floor_from_prior("stuff_supported_pitcher",
                          float(ssp.get("posterior_floor_prior_pct", 1.05)))

    ilsp = cfg.get("injured_low_stuff_pitcher", {})
    low_composite = (
        composite_stuff_plus is not None
        and composite_stuff_plus <= float(ilsp.get("max_composite_stuff_plus", 95.0))
    )
    low_primary = (
        stuff["primary_stuff_plus"] is not None
        and stuff["primary_stuff_plus"] <= float(ilsp.get("max_primary_stuff_plus", 100.0))
    )
    if (is_pitcher
            and active_arm_injury
            and fv_v <= float(ilsp.get("max_fv", 50.0))
            and (low_composite or low_primary)):
        _mult("injured_low_stuff_pitcher",
              float(ilsp.get("posterior_multiplier", 0.65)))

    elite_young_injury_exception = (
        age_v <= 24.5
        and fv_v >= 60.0
        and (
            (stuff["weighted_stuff_plus"] or 0.0) >= 108.0
            or (composite_stuff_plus or 0.0) >= 120.0
        )
    )
    if (is_pitcher
            and starter_workload
            and active_injury
            and not current_mlb_statline
            and not elite_young_injury_exception):
        _mult("active_injured_starter_no_current_season",
              0.72)

    if (is_pitcher
            and starter_workload
            and age_v <= 24.5
            and fv_v >= 52.0
            and (stuff["weighted_stuff_plus"] or 0.0) >= 104.0
            and stat_bb <= 8.0):
        _floor_from_prior("young_stuff_command_starter", 1.25)

    if (is_pitcher
            and starter_workload
            and ctrl >= 2.0
            and age_v <= 30.5
            and fv_v >= 50.0
            and tt_war >= 1.8
            and not active_injury
            and not active_arm_injury
            and worry_score <= 0.45
            and (stuff["weighted_stuff_plus"] or composite_stuff_plus or 100.0) >= 102.0):
        # was a hardcoded 65.0; FV 58.73 is exactly what that meant on the v5 table
        _floor_from_fv("controlled_rotation_asset", 58.73)

    if (is_pitcher
            and starter_workload
            and ctrl >= 3.0
            and age_v <= 25.5
            and fv_v >= 50.0
            and not active_injury
            and current_mlb_statline
            and stat_k >= 23.0
            and stat_bb <= 9.0
            and (stuff["weighted_stuff_plus"] or composite_stuff_plus or 100.0) >= 103.0):
        _floor_from_prior("young_controlled_stuff_starter", 1.65)

    current_ip = _safe_float(statline.get("ip"), 0.0) or 0.0
    current_games = _safe_float(statline.get("games"), 0.0) or 0.0
    ip_per_game = current_ip / current_games if current_games > 0.0 else 0.0
    if (is_pitcher
            and starter_workload
            and current_mlb_statline
            and not active_injury
            and ctrl >= 1.0
            and age_v <= 29.0
            and current_ip >= 55.0
            and ip_per_game >= 4.0
            and stat_k >= 25.0
            and stat_bb <= 8.5
            and (
                (stuff["weighted_stuff_plus"] or 0.0) >= 102.0
                or (composite_stuff_plus or 0.0) >= 102.0
                or (_safe_float(statline.get("stf_plus_periph"), 0.0) or 0.0) >= 105.0
            )):
        # was a hardcoded 62.0
        _floor_from_fv("healthy_breakout_starter", 58.28)

    current_pitcher_ip = _safe_float(current_mlb_row.get("ip"), 0.0) or 0.0
    current_pitcher_games = _safe_float(current_mlb_row.get("games"), 0.0) or 0.0
    current_pitcher_k = _safe_float(current_mlb_row.get("k_pct"), 0.0) or 0.0
    current_pitcher_bb = _safe_float(current_mlb_row.get("bb_pct"), 99.0) or 99.0
    current_pitcher_era = _safe_float(current_mlb_row.get("era"), 99.0) or 99.0
    current_pitcher_whip = _safe_float(current_mlb_row.get("whip"), 99.0) or 99.0
    current_pitcher_stf = _safe_float(current_mlb_row.get("stf_plus_periph"), 100.0) or 100.0
    if (is_pitcher
            and starter_workload
            and current_mlb_statline
            and not active_injury
            and age_v <= 33.0
            and current_pitcher_games >= 10.0
            and current_pitcher_ip >= 55.0
            and current_pitcher_era <= 3.30
            and current_pitcher_whip <= 1.25
            and current_pitcher_k >= 20.0
            and current_pitcher_bb <= 9.5
            and (
                current_pitcher_stf >= 102.0
                or (stuff["weighted_stuff_plus"] or 0.0) >= 102.0
            )):
        # was a hardcoded 58.0
        _floor_from_fv("productive_established_starter", 57.69)

    if (is_pitcher
            and starter_workload
            and age_v <= 25.0
            and fv_v <= 55.0
            and _current_pitcher_bad_trial(player)):
        _mult("failed_current_mlb_pitcher_trial", 0.52)
        out["features"]["suppress_additive_floors"] = True

    if (not is_pitcher
            and pos == "C"
            and ctrl >= 2.0
            and age_v <= 29.0
            and _hitter_offense_supported(player, {"min_iso": 0.180, "min_xwoba_est": 0.310, "min_barrel_pct": 8.0})):
        _mult("controlled_catcher_asset", 1.12)

    if (is_pitcher
            and pos in {"RP", "CL", "SIRP", "MIRP"}
            and ctrl >= 2.0
            and age_v <= 29.0
            and tt_war >= 2.0
            and (stuff["weighted_stuff_plus"] or composite_stuff_plus or 0.0) >= 115.0
            and current_salary_mm <= 8.0):
        # was a hardcoded 65.0
        _floor_from_fv("elite_controlled_reliever", 58.73)

    yesp = cfg.get("young_elite_stuff_pitcher", {})
    has_elite_pitch_data = (
        stuff["has_data"]
        and (stuff["primary_stuff_plus"] or 0.0) >= float(yesp.get("min_primary_stuff_plus", 105.0))
    )
    has_elite_tool_data = (
        composite_stuff_plus is not None
        and composite_stuff_plus >= float(yesp.get("min_composite_stuff_plus", 115.0))
    )
    if (is_pitcher
            and starter_workload
            and age_v <= float(yesp.get("max_age", 24.5))
            and fv_v >= float(yesp.get("min_fv", 55.0))
            and (has_elite_pitch_data or has_elite_tool_data)):
        if stale_mlb_prior:
            _tag("stale_mlb_prior")
        else:
            _tag("young_elite_stuff_pitcher")
            pct = float(yesp.get("posterior_floor_prior_pct", 0.65))
            starter_prior = surplus_value_mm(fv_v, True, "SP", age=age_v, eta_years=0.0) or prior_surplus_mm
            out["posterior_floor_mm"] = max(
                float(out["posterior_floor_mm"]),
                float(starter_prior) * pct,
            )

    vlp = cfg.get("validated_late_pitcher", {})
    has_validated_stuff = (
        not stuff["has_data"]
        or (stuff["primary_stuff_plus"] or 100.0) >= float(vlp.get("min_primary_stuff_plus", 95.0))
    )
    if (is_pitcher
            and starter_workload
            and age_v >= float(vlp.get("min_age", 25.0))
            and validated_ip >= float(vlp.get("min_validated_ip", 160.0))
            and tt_war >= float(vlp.get("min_true_talent_war", 2.0))
            and has_validated_stuff):
        _mult("validated_late_pitcher",
              float(vlp.get("posterior_multiplier", 1.05)))

    env = cfg.get("expensive_nonstar_veteran", {})
    if (not is_pitcher
            and stale_mlb_prior
            and current_salary_mm >= float(env.get("min_current_salary_mm", 30.0))
            and tt_war <= float(env.get("max_true_talent_war", 3.0))):
        _mult("expensive_nonstar_veteran",
              float(env.get("posterior_multiplier", 0.65)))

    ppmi = cfg.get("post_peak_expensive_middle_infielder", {})
    if (not is_pitcher
            and stale_mlb_prior
            and age_v >= float(ppmi.get("min_age", 30.0))
            and pos in set(ppmi.get("positions", ["SS", "2B"]))
            and ctrl >= float(ppmi.get("min_control_years", 4.0))
            and current_salary_mm >= float(ppmi.get("min_current_salary_mm", 20.0))
            and tt_war <= float(ppmi.get("max_true_talent_war", 3.3))):
        _mult("post_peak_expensive_middle_infielder",
              float(ppmi.get("posterior_multiplier", 0.20)))
        if ppmi.get("suppress_additive_floors", False):
            out["features"]["suppress_additive_floors"] = True

    out["posterior_floor_mm"] = round(float(out["posterior_floor_mm"]), 1)
    out["posterior_multiplier"] = round(float(out["posterior_multiplier"]), 3)
    return out


# ---------------------------------------------------------------------------
# § OPTIONS: roster flexibility premium
# ---------------------------------------------------------------------------

def options_premium_mm(player: dict) -> float:
    """§ OPTIONS: additive $M premium per remaining option.

    Options allow a team to shuttle a player between MLB and AAA without
    waivers, which is genuine roster flexibility with real competitive value.
    More options → higher premium (especially for contenders).
    """
    ocfg    = _cfg().get("options", {})
    per_opt = float(ocfg.get("premium_per_option_mm", 0.9))
    max_opt = int(ocfg.get("max_options_in_system", 3))

    roster = player.get("roster_status") or {}
    used   = int(roster.get("options_used") or 0)
    # Standard MLB players start with 3 options; clamp to valid range
    remaining = max(0, min(max_opt, max_opt - used))

    # Prospects (no MLB debut) still have all 3 options
    if player.get("status") == "active":
        remaining = max_opt

    return round(remaining * per_opt, 2)


# ---------------------------------------------------------------------------
# § RULE5: Rule 5 draft urgency premium
# ---------------------------------------------------------------------------

def rule5_urgency_mm(player: dict) -> float:
    """§ RULE5: additive $M urgency premium when a player is Rule 5 exposed.

    If a player must be added to the 40-man by November or risk being drafted
    for $100k, their trade value spikes in the months before the deadline
    because the alternative to trading is losing them for near-free.

    The premium scales with months remaining before the deadline window.
    """
    rcfg     = _cfg().get("rule5", {})
    premium  = float(rcfg.get("urgency_premium_mm", 1.8))
    window   = int(rcfg.get("urgency_window_months", 4))
    deadline = int(rcfg.get("deadline_month", 11))
    exp_yrs  = int(rcfg.get("exposure_years_default", 3))

    roster   = player.get("roster_status") or {}
    on_40man = bool(roster.get("on_40_man"))
    if on_40man:
        return 0.0  # already protected

    acq = player.get("acquisition") or {}
    signed_year = acq.get("year")

    today = date.today()
    if signed_year:
        years_in = today.year - int(signed_year)
        if years_in < exp_yrs:
            return 0.0  # not yet exposed

    # Months until the November deadline (0 = the deadline IS this month = MAX urgency).
    months_to_deadline = (deadline - today.month) % 12
    if months_to_deadline > window:
        return 0.0

    # Linear ramp: full premium in the deadline month and the month before, tapering to
    # premium/window at the window edge. (The old code remapped 0 -> 12 and then zeroed
    # the premium DURING the deadline month, the single highest-urgency month.)
    ramp = 1.0 - max(0, months_to_deadline - 1) / window
    return round(premium * ramp, 2)


# ---------------------------------------------------------------------------
# § KALMAN: core Bayesian update for prospects
# ---------------------------------------------------------------------------

def _prior_precision(player: dict, n_sources: int) -> float:
    """§ PRIOR: compute total prior precision for a prospect.

    prior_prec = base × (1 + pedigree + age_buf + source_weight)

    Higher precision → observation moves the posterior less, and
    the prior is more trusted. Young-for-level + high-bonus players
    need more negative evidence before the posterior moves downward.
    """
    cfg_p = _cfg().get("prior", {})
    base  = float(cfg_p.get("base_precision", 1.0))
    ns    = _cfg().get("prior", {}).get("n_sources", {})
    src_w = float(ns.get("per_source_weight", 0.15))
    max_sw = float(ns.get("max_source_weight", 0.60))

    ped = pedigree_precision(player.get("acquisition"))
    avl = age_for_level_buffer(
        _safe_float(player.get("age")),
        player.get("current_level"),
    )
    src = min(max_sw, src_w * max(0, n_sources - 1))

    return base * (1.0 + ped + avl + src)


def _obs_noise(sample: float, is_pitcher: bool) -> float:
    """§ LIKELIHOOD: observation noise as a function of sample size.

    obs_noise = base_noise / sqrt(sample / ref_sample)

    Smaller sample → higher noise → K (Kalman gain) is smaller →
    the observation moves the posterior less. This is the formal
    Bayesian analog of "not trusting a one-month sample."
    """
    ncfg     = _cfg().get("obs_noise", {})
    ref      = float(ncfg.get("pitcher_ref_ip" if is_pitcher else "hitter_ref_pa", 300.0))
    base_n   = float(ncfg.get("base_noise", 2.5))
    min_n    = float(ncfg.get("min_noise_floor", 0.6))
    sample   = max(1.0, sample)
    noise    = base_n / math.sqrt(sample / ref)
    return max(min_n, noise)


# ---------------------------------------------------------------------------
# Main entry point: bayesian_trade_value(player)
# ---------------------------------------------------------------------------

def bayesian_trade_value(
    player: dict,
    level_norms: dict | None = None,
    n_sources: int = 3,
) -> dict:
    """Compute the Bayesian trade value for a player.

    Works for both active prospects (FV-based prior) and debuted MLB players
    (WAR-updated prior via debuted_player_value).

    Returns a dict with:
      trade_value_mm       — headline $M trade value
      trade_value_lo       — conservative (10th pct) estimate
      trade_value_hi       — optimistic (90th pct) estimate
      prior_surplus_mm     — FV-based prior before performance update
      posterior_surplus_mm — after § KALMAN update
      kalman_gain          — how much the observation moved the posterior
      scarcity_mult        — § SCARCITY multiplier applied
      defensive_floor_mm   — § FLOOR additive guarantee
      worriedness          — § WORRY decomposed score
      flash                — § FLASH bimodal assessment
      options_premium_mm   — § OPTIONS additive
      rule5_urgency_mm     — § RULE5 additive
      rolling_label        — which data windows were used
      authenticity         — § AUTHENTIC weight on the observation
      inputs_available     — list of data fields successfully used
    """
    player_key  = player.get("player_key", "?")
    _db_position = player.get("position")
    _is_mlb_status_for_pos = (player.get("status") or "active") in ("debuted", "graduated")
    _pos_source = "db"
    # Resolve actual current position from fielding data / overrides
    try:
        from fielding import resolve_position as _rp
        _mlbam = None
        from storage import connect as _conn
        with _conn() as _c:
            _row = _c.execute("SELECT mlbam_id FROM player_photos WHERE player_key=?", (player_key,)).fetchone()
            if _row: _mlbam = _row[0]
        position, _pos_source = _rp(player_key, _mlbam, _db_position, _is_mlb_status_for_pos)
        if position != _db_position and _pos_source != "db":
            _log.debug("fielding override: %s %s→%s (%s)", player_key, _db_position, position, _pos_source)
    except Exception:
        position = _db_position
    is_pitcher  = bool(player.get("is_pitcher")) or is_pitcher_position(position)

    # § ROLE DETECTION: for debuted pitchers tagged "RHP"/"LHP" (generic tags),
    # determine if they're a starter or reliever based on career IP workload.
    # Config now has RHP/LHP at 0.92 (RP rate) by default; confirmed starters
    # need to be re-tagged "SP" (1.13) and relievers tagged "RP" (0.92).
    # Threshold: max single-season MLB IP ≥ 80 = starter workload.
    _pos_tag = _pos_primary(position)
    if is_pitcher and _pos_tag in ("P", "RHP", "LHP") and _is_mlb_status_for_pos:
        _cs_ip = player.get("career_stats") or []
        _max_ip = max(
            (float(s.get("ip") or 0) for s in _cs_ip if (s.get("level") or "") == "MLB"),
            default=0.0
        )
        if _pitcher_starter_workload(player):
            # Confirmed starter workload → SP scarcity (1.13)
            position = "SP"
        elif _max_ip > 0:
            # Reliever workload → RP scarcity (0.92)
            position = "RP"
        # If max_ip == 0 (no MLB data yet), keep generic tag → 0.92 (RP default)
    status      = player.get("status", "active")
    fv          = _safe_float(player.get("fv_close"))
    age         = _safe_float(player.get("age"))
    # bughunt F2: eta arrives as the timeseries ETA DICT - derive years-to-debut
    # from it (see _eta_years_to_debut) instead of _safe_float(dict) -> None -> 0.0.
    eta         = _eta_years_to_debut(player.get("eta"))
    statline    = player.get("statline") or {}
    statcast    = player.get("statcast_metrics") or {}
    recent_games = (statcast or {}).get("recent_games") or []
    # Prefer the level-split matching the player's current level for contact quality,
    # falling back to the top-level contact_quality.
    _ls = (statcast or {}).get("level_splits") or []
    _level_for_cq = (player.get("current_level") or "").upper()
    _level_split_cq = next(
        (s.get("contact_quality") or {} for s in _ls if (s.get("level") or "").upper() == _level_for_cq),
        (statcast or {}).get("contact_quality") or {}
    ) if _ls else ((statcast or {}).get("contact_quality") or {})
    # Merge level-split contact quality into a shallow copy of statcast for signal use
    if _level_split_cq:
        statcast = dict(statcast or {})
        statcast["contact_quality"] = _level_split_cq
    # Pull o_swing_pct from zone_metrics and attach to statcast for signal computation
    _zm = player.get("zone_metrics") or {}
    _o_swing = _safe_float(_zm.get("o_swing_pct") or _zm.get("actual_o_swing_pct"))
    if _o_swing is not None:
        statcast = dict(statcast or {})
        statcast["o_swing_pct"] = _o_swing
    _is_mlb_status = status in ("debuted", "graduated")
    # Graduated players have no current MiLB level — default to MLB for baselines.
    level = player.get("current_level") or ("MLB" if _is_mlb_status else None)
    acq         = player.get("acquisition") or {}

    inputs_available: list[str] = []
    if _pos_source != "db":
        inputs_available.append(f"position_source_{_pos_source}")

    # ── § PRIOR: FV-based prior surplus ──────────────────────────────────────
    if fv is None:
        return {
            "player_key": player_key,
            "error": "no_fv",
            "trade_value_mm": None,
        }

    is_mlb_player = status in ("debuted", "graduated")
    remaining_ctrl: float = float(_MLB_CONTROL_YEARS)
    ctrl_source: str = "prospect"
    grpo_fv_adj: float = 0.0
    grpo_score: float | None = None
    fv_effective: float | None = fv
    gross_floor_mm: float = 0.0
    fv50_trade_rarity_final_floor_mm: float = 0.0

    if is_mlb_player:
        # § CONTRACT + § KALMAN for MLB players.
        #
        # Step 1: derive remaining control years from debut+6 vs. extension,
        #         whichever is larger.
        remaining_ctrl, ctrl_source = _remaining_control_years(player)

        # Step 2: establish true-talent WAR via Kalman blend of career WAR (prior)
        #         and current-season performance signal (likelihood).
        cwar        = player.get("career_war") or {}
        _raw_career_war_yr = _safe_float(cwar.get("war_per_yr"), 0.0) or 0.0
        _weighted_career_war_yr, _effective_war_seasons, _war_season_weights = (
            _exposure_weighted_career_war(player, is_pitcher, position)
        )
        _full_season_sample = _full_season_exposure(player, is_pitcher, position)
        career_war_yr = (
            _weighted_career_war_yr
            if _weighted_career_war_yr is not None
            else _raw_career_war_yr
        )
        prior_surplus_mm = surplus_value_mm(fv, is_pitcher, position, age=age) or 0.0

        signal_mm, sample, roll_label = _rolling_signal(
            statline, statcast, recent_games, is_pitcher, level, level_norms, fv,
            career_stats=player.get("career_stats"),
        )
        auth = skills_authenticity(statline, statcast, is_pitcher, level)

        # § KALMAN on WAR: blend career rate with current-season signal.
        war_seasons = int((cwar.get("war_seasons_count") or 0))
        ref_sample  = 60.0 if is_pitcher else 200.0

        # § TRAJECTORY: penalize sustained or recent decline.
        # When the most recent completed season's WAR is well below the career
        # average (and we have enough history to judge), regress toward the
        # recent result. Volpe / Alvarez type: long career average looks good
        # but recent reality is worse.
        seasons_dict = cwar.get("seasons") or {}
        recent_season_war: float | None = None
        if seasons_dict and war_seasons >= 2:
            try:
                today_year = date.today().year
                sorted_years = sorted(int(y) for y in seasons_dict if seasons_dict.get(y) is not None)
                # § TRAJECTORY FIX: use the most recent COMPLETED season, not the
                # current in-progress year.  Reynolds's 2025 (1.26 WAR, terrible)
                # was being ignored because 2026 (partial, 2.95) was the latest key.
                # A 240-AB hot streak shouldn't erase a full year of poor production.
                completed = [y for y in sorted_years if y < today_year]
                ref_year  = completed[-1] if completed else (sorted_years[-1] if sorted_years else None)
                if ref_year is not None:
                    recent_weight = _war_season_weights.get(ref_year, 1.0)
                    if recent_weight >= 0.45:
                        recent_season_war = float(seasons_dict[str(ref_year)] or 0)
            except (TypeError, ValueError):
                pass

        base_war = career_war_yr

        # § PARTIAL-SEASON REGRESSION: career_war.war_per_yr for players in their
        # first year is the TOTAL accumulated WAR for that partial season, not an
        # annualized rate.  McGonigle at 3.37 WAR in 65 games = 8.4 WAR/yr pace —
        # treating that as a full-season baseline massively overstates true talent.
        # When war_seasons == 1, regress toward a league-average rate weighted by
        # how much of a season the player has actually played.
        # § PARTIAL-SEASON REGRESSION ANCHOR: what we regress toward for war_seasons=1
        # players depends heavily on age and existing track record.
        # Young prospects (21-23): regress toward 1.8 — wide uncertainty, real upside.
        # Old debutants (26+, Banfield type): already past peak, minor league history
        #   is essentially known to be poor → regress toward near-zero, not 1.8.
        # Additionally: if the player ALREADY showed negative MLB WAR in their only
        #   season, don't regress upward — that's evidence, not noise.
        _age_val = age or 25.0
        if _age_val >= 27:
            _LEAGUE_AVG_WAR = 0.4   # late debuters, almost no development runway
        elif _age_val >= 26:
            _LEAGUE_AVG_WAR = 0.6
        elif _age_val >= 25:
            _LEAGUE_AVG_WAR = 1.0
        elif _age_val >= 24:
            _LEAGUE_AVG_WAR = 1.4
        else:
            _LEAGUE_AVG_WAR = 1.8   # young prospect — genuine uncertainty

        # If they've already shown negative WAR in their only MLB season, the anchor
        # is capped at 0.5 regardless of age (evidence beats prior).
        if career_war_yr < 0 and war_seasons >= 1:
            _LEAGUE_AVG_WAR = min(_LEAGUE_AVG_WAR, 0.5)

        if war_seasons == 1:
            _cs_list    = player.get("career_stats") or []
            _first_cs   = _cs_list[0] if _cs_list else {}
            if is_pitcher:
                _exposure = _safe_float(_first_cs.get("ip") or _first_cs.get("IP"), 0.0) or 0.0
            else:
                _exposure = (
                    _safe_float(_first_cs.get("pa") or _first_cs.get("PA"), None)
                    or _safe_float(_first_cs.get("ab") or _first_cs.get("AB"), None)
                    or 0.0
                )
                if _exposure <= 0:
                    _games = float(_first_cs.get("games") or 162)
                    _exposure = _games * 4.0
            _season_frac = min(1.0, _exposure / _full_season_sample)
            base_war     = _season_frac * career_war_yr + (1.0 - _season_frac) * _LEAGUE_AVG_WAR

        # § CURRENT BREAKOUT / INJURY RECOVERY: when the current in-progress year
        # is dramatically better than the recent completed year AND above the career
        # average, partially incorporate it into the trajectory anchor.
        # — For 2-season players (Misiorowski): 35% weight on current year.
        # — For veterans (8+ seasons, Alvarez type): 20% weight. A career-long track
        #   record anchors the prior but an injury-driven down year shouldn't persist
        #   when current metrics clearly show recovery (xwOBA 0.41, barrel 17%).
        # Conditions are stricter for veterans: current must exceed career avg (not
        # just the injury year) to avoid noise from hot starts.
        if recent_season_war is not None and war_seasons >= 2 and seasons_dict:
            try:
                _today_yr = date.today().year
                _curr_war = seasons_dict.get(str(_today_yr))
                if _curr_war is not None:
                    _cs2  = player.get("career_stats") or []
                    _g2   = float((_cs2[0].get("games") or 50) if _cs2 else 50)
                    _ip2  = float((_cs2[0].get("ip") or 50) if _cs2 else 50)
                    _g_eff = _ip2 if is_pitcher else _g2
                    _frac = min(0.85, _g_eff / _full_season_sample)
                    if _frac > 0.08:
                        _ann = float(_curr_war) / _frac
                        # Blend weight: smaller for veterans (more prior history)
                        _breakout_blend = 0.35 if war_seasons == 2 else 0.20
                        # Veterans need a stricter threshold: current must be above
                        # career avg (not just 1.75x the injury year floor).
                        _min_improvement = 1.75 if war_seasons == 2 else 2.0
                        if _ann > recent_season_war * _min_improvement and _ann > career_war_yr:
                            _capped = min(_ann, career_war_yr * 2.5)
                            recent_season_war = (
                                (1.0 - _breakout_blend) * recent_season_war
                                + _breakout_blend * _capped
                            )
            except (TypeError, ValueError, ZeroDivisionError):
                pass

        if recent_season_war is not None and career_war_yr > 0.5:
            # § TRAJECTORY BLEND
            # § MONSTER SEASON REGRESSION: when the most recent completed year is
            # an outlier (>1.5× career avg), cap it.  Cameron type: career 2.12,
            # 2025=3.78 — the old formula used max(×1.5, +2.0) = 4.12, so 3.78
            # never triggered. Simpler and tighter: cap at 1.5× career avg only.
            _rsw_cap = career_war_yr * 1.5
            recent_season_war_adj = min(recent_season_war, _rsw_cap)
            if war_seasons == 2:
                blend_recent = 0.25
            else:
                blend_recent = 0.40
            base_war = (1.0 - blend_recent) * base_war + blend_recent * recent_season_war_adj
            if recent_season_war_adj < base_war * 0.40 and war_seasons >= 3:
                base_war = 0.45 * base_war + 0.55 * recent_season_war_adj

        if signal_mm is not None and sample > 0:
            sample_frac = min(1.0, sample / ref_sample)
            seasons_basis = _effective_war_seasons if _effective_war_seasons > 0 else float(war_seasons)
            seasons_frac    = min(1.0, seasons_basis / 3.0)
            recency_weight  = 0.25 + 0.47 * sample_frac * (0.55 + 0.45 * seasons_frac)
            # § VETERAN ANCHOR: for established players (5+ MLB seasons), the career
            # track record is far more reliable than any partial-season signal.
            # Henderson (5 seasons, 4.49 WAR/yr) should not have a bad month
            # drag his true_talent down by 1.44 WAR at K=0.72.
            if war_seasons >= 5:
                veteran_cap = max(0.30, 0.55 - 0.04 * (war_seasons - 4))  # 0.51 at 5, 0.35 at 9+
                recency_weight = min(recency_weight, veteran_cap)
            recency_weight  = round(min(0.75, recency_weight), 3)

            dpw_mm           = 11.74
            raw_war_delta    = signal_mm / dpw_mm

            # § SIGNAL CAP: cap the WAR boost from a single season's signal.
            # Approach metrics (K%/BB%) can generate large z-scores even in small
            # samples; contact quality (xwOBA/EV) is a stronger stabilizing anchor.
            # With both → cap at 2.0; approach-only → tighter 1.2 cap.
            MAX_WAR_DELTA = 2.0
            cq = (statcast or {}).get("contact_quality") or {}
            has_contact_data = bool(cq.get("xwoba_est") or cq.get("avg_ev"))
            effective_cap = MAX_WAR_DELTA if has_contact_data else 1.2
            war_signal_delta = max(-MAX_WAR_DELTA, min(effective_cap, raw_war_delta))

            true_talent_war  = max(0.0, base_war + recency_weight * war_signal_delta)
            kalman_gain      = recency_weight
            inputs_available.extend(["career_war", "current_season_statline"])
            if recent_games:
                inputs_available.append("recent_games")
        else:
            true_talent_war = max(0.0, base_war)
            kalman_gain     = 0.0
            inputs_available.append("career_war")

        # § POWER-PROFILE WAR CEILING: when ISO is scarily low (<0.120) AND barrel%
        # is near zero (<3%), the player has essentially no power projection. Regardless
        # of how disciplined they are at the plate, extra bases are required for WAR
        # to exceed ~2.5 in the modern game.  Perdomo type: iso=0.111, barrel%=2.7,
        # 15.1% walks — the elite discipline is real but the power ceiling is hard.
        if not is_pitcher:
            _sl_iso2 = _safe_float(statline.get("iso"))
            _cq2 = (statcast or {}).get("contact_quality") or {}
            _brl2 = _safe_float(_cq2.get("barrel_pct"))
            if _sl_iso2 is not None and _brl2 is not None:
                if _sl_iso2 < 0.120 and _brl2 < 3.0:
                    # Hard ceiling: contact-only players can't exceed ~2.5 WAR
                    _power_ceiling = 2.5 - max(0.0, (0.110 - _sl_iso2) / 0.015) * 0.3
                    true_talent_war = min(true_talent_war, max(0.5, _power_ceiling))

        # § STUFF-FLOOR FOR SP (starting pitchers only, NOT relievers):
        # SP with above-average Stuff+ and multi-year control carry a WAR floor
        # because ERA variance dwarfs stuff variance. Kirby type.
        # EXCLUDED for relievers: RP are MORE volatile, not less. A reliever
        # with average stuff (Molina avg_stuff+=101) who has -0.28 career WAR
        # should absolutely NOT get a 2.0 WAR floor — that stuff level doesn't
        # overcome their track record in the bullpen.
        _RP_ROLE_TAGS = {"RP", "CL", "SIRP", "MIRP"}
        _is_true_sp = (is_pitcher and is_mlb_player and
                       _pos_primary(position) not in _RP_ROLE_TAGS)
        if _is_true_sp:
            # Also require meaningful SP workload (80+ IP season) to confirm starter role
            _cs_sp = player.get("career_stats") or []
            _max_sp_ip = max(
                (float(s.get("ip") or 0) for s in _cs_sp if (s.get("level") or "") == "MLB"),
                default=0.0
            )
            if _max_sp_ip >= 80:
                _pm2     = (statcast or {}).get("pitch_movement") or {}
                _ps2     = _pm2.get("pitch_summary") or []
                _wsplus2 = 0.0   # default: no Stuff+ data → no floor
                if _ps2:
                    _tu2 = sum(p2.get("usage_pct") or 0 for p2 in _ps2) or 1
                    _wsplus2 = sum((p2.get("avg_stuff_plus") or 100) * (p2.get("usage_pct") or 0)
                                   for p2 in _ps2) / _tu2
                # Threshold 105: "mid stuff" (Burrows 101.8) doesn't get a floor.
                # Only genuinely above-average arsenals (Kirby 103.5, Miller 117.5).
                if _wsplus2 >= 105.0 and remaining_ctrl >= 3:
                    _stuff_floor = 2.0 + max(0.0, _wsplus2 - 105) / 50 * 0.5
                    true_talent_war = max(true_talent_war, _stuff_floor)

                # § STUFF-CEILING FOR SP: mirror of the floor. Low-stuff SPs
                # (primary pitch stuff+ < 95) rely entirely on command; when
                # their ERA is elevated (> 4.20) in the current season, that
                # command-reliant model is failing. Cap base true_talent_war so
                # the career average doesn't float the value above what their
                # arsenal can sustain. Only applied for war_seasons <= 4 (early
                # career, where one great season can inflate the average) when
                # pitch data is available.
                _pm_primary = max(_ps2, key=lambda p2: p2.get("usage_pct") or 0,
                                  default={})
                _primary_sp = float((_pm_primary or {}).get("avg_stuff_plus") or 100)
                _cs_era = player.get("career_stats") or []
                _curr_era = _safe_float((_cs_era[0] if _cs_era else {}).get("era"), 0.0) or 0.0
                if (_ps2 and _primary_sp < 95 and war_seasons <= 4
                        and _curr_era >= 4.00):
                    # Ceiling scales with arsenal: stuff+=90 → 2.3 WAR max;
                    # stuff+=94 → 2.7 WAR max. Above 95, ceiling is lifted.
                    _stuff_ceiling = 2.3 + max(0.0, _primary_sp - 90) / 5 * 0.4
                    true_talent_war = min(true_talent_war, _stuff_ceiling)

        # § RELIEVER VOLATILITY DISCOUNT: RP are the most volatile asset in baseball.
        # A quarter-season of good ERA from a reliever with mediocre stuff (Garcia,
        # Lord) or a career of failure (Molina, Klein) should be heavily discounted.
        # Unlike SP where control dominates, RP value evaporates overnight with
        # a role change, injury, or one pitching coach's decision.
        _is_rp_role = is_pitcher and _pos_primary(position) in _RP_ROLE_TAGS
        if _is_rp_role and is_mlb_player:
            # Scale discount by career track record (negative WAR → max discount)
            _rp_career = career_war_yr or 0.0
            if _rp_career < 0.5:
                # Bad or unproven RP: heavy discount regardless of current ERA
                _rp_discount = min(0.45, 0.25 + max(0, 0.5 - _rp_career) * 0.4)
            else:
                # Proven RP (Miller type): smaller discount based on stuff quality
                _pm2 = (statcast or {}).get("pitch_movement") or {}
                _ps2 = _pm2.get("pitch_summary") or []
                _rp_stuff = 100.0
                if _ps2:
                    _tu2 = sum(p2.get("usage_pct") or 0 for p2 in _ps2) or 1
                    _rp_stuff = sum((p2.get("avg_stuff_plus") or 100) * (p2.get("usage_pct") or 0)
                                    for p2 in _ps2) / _tu2
                # Elite stuff (110+): small discount. Average stuff (100): larger.
                _rp_discount = max(0.05, min(0.30, (110 - _rp_stuff) / 40))
            true_talent_war = true_talent_war * (1.0 - _rp_discount)

        # § CONTACT-PROFILE AGING PENALTY: "Hoerner/Arraez type" — low power, soft
        # contact, elite bat-to-ball — doesn't age well past 28-29 because:
        #   (a) speed/BABIP erodes, the main source of their value
        #   (b) pitchers learn to pound the zone since they can't be punished with power
        #   (c) they can't compensate with extra bases when legs go
        # Apply when: soft contact (avg_ev<87, barrel%<5) + elite contact (K%<15)
        # AND player is past age 28. Scale with age beyond 28.
        if not is_pitcher and age is not None and age > 28:
            _cq_stat = (statcast or {}).get("contact_quality") or {}
            _avg_ev  = _safe_float(_cq_stat.get("avg_ev"))
            _brl     = _safe_float(_cq_stat.get("barrel_pct"), 10.0)
            _sl_k    = _safe_float(statline.get("k_pct"), 25.0)
            if _avg_ev is not None and _avg_ev < 87.0 and _brl < 5.0 and _sl_k < 15.0:
                _contact_penalty = min(0.18, (age - 28) * 0.05)
                true_talent_war  = true_talent_war * (1.0 - _contact_penalty)
                inputs_available.append(f"contact_aging_penalty_{_contact_penalty:.2f}")

        # § PARTIAL-SAMPLE ANNUALIZATION GUARDRAIL:
        # Full-season denominators are correct for rates, but trade value should
        # not treat a low/moderate-prior player with a fraction of a season as a
        # fully established 4-6 WAR talent. Use FV prime WAR as the anchor and
        # allow only bounded overperformance until MLB exposure is real.
        _fv_anchor_war = fv_to_prime_war(fv) or _LEAGUE_AVG_WAR
        _eff_seasons = _effective_war_seasons if _effective_war_seasons > 0 else float(war_seasons)
        _suppress_no_power_infield_floors = False
        if _eff_seasons < 1.5:
            _bonus = (0.7 if (fv or 0.0) >= 60.0 else 0.4) + 0.8 * _eff_seasons
            _sample_cap = _fv_anchor_war + _bonus
            if true_talent_war > _sample_cap:
                true_talent_war = _sample_cap
                inputs_available.append("partial_sample_annualization_cap")

        _curr_mlb_row = None
        for _row in player.get("career_stats") or []:
            if (_row.get("level") or "") == "MLB":
                _curr_mlb_row = _row
                break
        _skill_row = _curr_mlb_row or statline or {}
        if not is_pitcher and _skill_row:
            _mlb_iso = _safe_float(_skill_row.get("iso"))
            _mlb_k = _safe_float(_skill_row.get("k_pct"))
            _mlb_ops_plus = _level_plus(_skill_row)
            _unsupported_hit = (
                (_mlb_iso is not None and _mlb_iso < 0.130)
                or (_mlb_k is not None and _mlb_k >= 28.0)
                or (_mlb_ops_plus is not None and _mlb_ops_plus < 100.0)
            )
            _no_power_infield = (
                _pos_primary(position) in {"INF", "MI", "SS", "2B", "3B"}
                and (fv or 0.0) < 55.0
                and (
                    (_mlb_iso is not None and _mlb_iso < 0.145)
                    or (_mlb_k is not None and _mlb_k >= 27.0)
                )
            )
            if _unsupported_hit:
                _hit_cap = _fv_anchor_war + (0.35 if (fv or 0.0) >= 60.0 else 0.20)
                if (fv or 0.0) < 55.0:
                    _hit_cap = min(_hit_cap, 2.25)
                if _no_power_infield:
                    _hit_cap = min(_hit_cap, max(0.8, _fv_anchor_war + 0.05))
                    _suppress_no_power_infield_floors = True
                if true_talent_war > _hit_cap:
                    true_talent_war = _hit_cap
                    inputs_available.append("current_mlb_offense_cap")

        if is_pitcher and _skill_row:
            _mlb_k = _safe_float(_skill_row.get("k_pct"))
            _mlb_bb = _safe_float(_skill_row.get("bb_pct"))
            _mlb_era = _safe_float(_skill_row.get("era"))
            _kbb = (_mlb_k - _mlb_bb) if _mlb_k is not None and _mlb_bb is not None else None
            _pm_guard = (statcast or {}).get("pitch_movement") or {}
            _ps_guard = _pm_guard.get("pitch_summary") or []
            _weighted_stuff = None
            if _ps_guard:
                _usage = sum(p2.get("usage_pct") or 0 for p2 in _ps_guard) or 1.0
                _weighted_stuff = sum((p2.get("avg_stuff_plus") or 100.0) * (p2.get("usage_pct") or 0)
                                      for p2 in _ps_guard) / _usage
            _unsupported_pitch = (
                (_kbb is not None and _kbb < 10.0)
                or (_weighted_stuff is not None and _weighted_stuff < 100.0 and (_mlb_era or 0.0) >= 4.0)
            )
            if _unsupported_pitch:
                _pitch_cap = _fv_anchor_war + (0.35 if (fv or 0.0) >= 55.0 else 0.15)
                if (fv or 0.0) < 55.0:
                    _pitch_cap = min(_pitch_cap, 2.45)
                if true_talent_war > _pitch_cap:
                    true_talent_war = _pitch_cap
                    inputs_available.append("current_mlb_pitching_cap")

        # Step 3: § TRIAL PERIOD — apply credibility weight to the offensive
        # component before pricing the contract. The defensive floor is added
        # separately and is NOT discounted (defense is measurable and real
        # from day one, independent of pitcher adjustment cycles).
        auth = skills_authenticity(statline, statcast, is_pitcher, level)
        tau  = _trial_period_factor(player, auth)
        true_talent_war_adj = true_talent_war * tau
        if tau < 1.0:
            inputs_available.append(f"trial_discount_{tau:.2f}")

        # Step 4: § CONTRACT surplus = season-by-season (market value - salary),
        #         discounted, over remaining controlled years.
        contract_surplus = _contract_surplus_mm(player, true_talent_war_adj, remaining_ctrl)

        # § FV ANCHOR for very early debutants: a player 30 games into their debut
        # (Colt Emerson type) should still be anchored mostly to their prospect FV,
        # not to contract surplus computed from 30 games of noisy WAR.  We blend
        # linearly: at 0 games the value is pure FV; at 80 games it's pure contract.
        # This prevents a good FV-60 prospect from ranking below a FV-52 prospect
        # just because they debuted recently and have bad early stats.
        _cs_list_d  = player.get("career_stats") or []
        _first_d    = (_cs_list_d[0] if _cs_list_d else {}) or {}
        _games_d    = float(_first_d.get("games") or 0) if war_seasons <= 1 else 80
        BLEND_GAMES = 80.0   # fully on contract surplus after 80 MLB games in first season
        if war_seasons == 1 and _games_d < BLEND_GAMES and fv is not None:
            _fv_surplus   = surplus_value_mm(fv, is_pitcher, position, age=age, eta_years=eta) or 0.0
            _blend_weight = _games_d / BLEND_GAMES          # 0 = pure FV; 1 = pure contract
            posterior_surplus_mm = (1.0 - _blend_weight) * _fv_surplus + _blend_weight * contract_surplus
        else:
            posterior_surplus_mm = contract_surplus
        if (
            war_seasons == 1
            and _games_d < BLEND_GAMES
            and age is not None
            and age <= 23.5
            and fv is not None
            and fv >= 52.0
            and _has_top100_pedigree(player)
        ):
            _fv_surplus = surplus_value_mm(fv, is_pitcher, position, age=age, eta_years=eta) or posterior_surplus_mm
            if fv >= 65.0:
                _early_debut_floor = max(_fv_surplus * 1.05, 140.0)
            elif fv >= 62.0:
                _early_debut_floor = max(_fv_surplus * 1.25, 120.0)
            elif fv >= 60.0:
                _early_debut_floor = max(_fv_surplus * 1.65, 105.0)
            elif fv >= 54.0:
                _early_debut_floor = max(_fv_surplus * 1.55, 55.0)
            else:
                _early_debut_floor = max(_fv_surplus * 1.45, 48.0)
            if posterior_surplus_mm < _early_debut_floor:
                posterior_surplus_mm = round(_early_debut_floor, 1)
                inputs_available.append("early_debut_top100_prospect_floor")

        # § GROSS_FLOOR: prevent productive veterans with expensive contracts from
        # collapsing to $0 surplus. When salary > surplus (contract is above-market),
        # the player still commands real trade value because their gross WAR production
        # is scarce — teams compare "cost to acquire X WAR" not just surplus delta.
        # Applied only when true_talent_war_adj passes the minimum WAR gate.
        # Worry is pre-computed here so the floor can discount declining players'
        # future WAR before computing the PV; the assembly section reuses this value.
        worry = worriedness_score(player, level_norms)
        _gf_cfg = _cfg().get("gross_production_floor", {})
        _gf_enabled = bool(_gf_cfg.get("enabled", True))
        _gf_min_war = float(_gf_cfg.get("min_true_talent_war", 0.5))
        _gf_frac    = float(_gf_cfg.get("fraction", 0.22))
        # § GROSS_FLOOR + WORRY: a declining player's future production should be
        # discounted in the floor itself — not just in the final trade_value output.
        # Without this, a player with worriedness=0.65 still gets a floor anchored
        # on their full (inflated) true_talent_war × control years. Devers: 8yr ctrl
        # looks valuable in gross terms but most of it is post-peak negative-surplus
        # years that the worriedness correctly signals he won't survive at full value.
        # Scale: worry=0 → no reduction; worry=0.65 → WAR reduced by ~0.65×worry_war_scale.
        _gf_worry_scale = float(_gf_cfg.get("worry_war_scale", 0.40))
        _gf_effective_war = max(
            0.0,
            true_talent_war_adj * (1.0 - worry["score"] * _gf_worry_scale),
        )
        gross_floor_mm = 0.0
        if _gf_enabled and _gf_effective_war >= _gf_min_war:
            gross_floor_mm = round(
                _gross_war_pv(_gf_effective_war, remaining_ctrl, age, is_pitcher, position) * _gf_frac,
                1,
            )
            if gross_floor_mm > posterior_surplus_mm:
                posterior_surplus_mm = gross_floor_mm

        if (("current_mlb_offense_cap" in inputs_available
             or "current_mlb_pitching_cap" in inputs_available)
                and _eff_seasons < 1.5):
            _surplus_mult = 1.35 if (fv or 0.0) >= 60.0 else (1.25 if (fv or 0.0) >= 50.0 else 1.10)
            if _suppress_no_power_infield_floors:
                _surplus_mult = 0.75
            _surplus_cap = prior_surplus_mm * _surplus_mult
            if posterior_surplus_mm > _surplus_cap:
                posterior_surplus_mm = round(_surplus_cap, 1)
                gross_floor_mm = min(gross_floor_mm, posterior_surplus_mm)
                inputs_available.append("unsupported_partial_surplus_cap")

        _proj_surplus_mm = _mlb_projection_surplus_mm(player)
        _career_pa, _career_ip = _career_mlb_exposure(player)
        _elite_young_slugger_anchor = _elite_young_slugger_projection_anchor(
            player,
            position,
            age,
            _career_pa,
            _proj_surplus_mm,
        )
        _projection_anchor = (
            _proj_surplus_mm is not None
            and (
                _career_pa >= 1000.0
                or (not is_pitcher and _career_pa >= 500.0)
                or _career_ip >= 300.0
                or _mlb_projection_is_twoway(player)
                or _elite_young_slugger_anchor
            )
        )
        if _projection_anchor:
            posterior_surplus_mm = _proj_surplus_mm
            gross_floor_mm = max(gross_floor_mm, _proj_surplus_mm)
            inputs_available.append("mlb_projection_surplus_anchor")
            if _elite_young_slugger_anchor:
                inputs_available.append("elite_young_slugger_projection_anchor")
            _current_form_mult = _projection_anchor_current_form_multiplier(player, position, age)
            if _current_form_mult < 1.0:
                posterior_surplus_mm = round(posterior_surplus_mm * _current_form_mult, 1)
                gross_floor_mm = min(gross_floor_mm, posterior_surplus_mm)
                inputs_available.append(f"projection_anchor_current_form_{_current_form_mult:.2f}")

        base_trade_value_mm = posterior_surplus_mm

    else:  # active prospect
        # § GRPO: adjust FV prior from the group-relative breakout model.
        # For unranked / low-FV players (provisional FV=35 from mlbam_ingest),
        # this is where elite raw tools (Frias's 117mph EV) can lift the prior
        # even before scouting sources publish a grade.
        # The adjustment is capped at ±10 FV points and scaled by model confidence:
        # low confidence → small adjustment; high confidence → full adjustment.
        grpo_s = _grpo_scores().get(player_key) or {}
        grpo_fv_adj = 0.0
        grpo_score  = None
        if grpo_s:
            raw_adj = _safe_float(grpo_s.get("fv_adj"), 0.0) or 0.0
            conf    = grpo_s.get("confidence") or "low"
            conf_scale = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(conf, 0.3)
            grpo_fv_adj = max(-10.0, min(10.0, raw_adj * conf_scale))
            grpo_score  = grpo_s.get("breakout_score")
        fv_effective = round((fv or 35.0) + grpo_fv_adj, 1)

        # § PRIOR: prospect FV-based surplus (with GRPO-adjusted effective FV)
        prior_surplus_mm = surplus_value_mm(fv_effective, is_pitcher, position, age=age, eta_years=eta) or 0.0
        inputs_available.append("fv")

        # § PRIOR PRECISION: scale by pedigree + age-for-level + source count
        prior_prec = _prior_precision(player, n_sources)

        # § LIKELIHOOD: rolling performance signal
        signal_mm, sample, roll_label = _rolling_signal(
            statline, statcast, recent_games, is_pitcher, level, level_norms, fv,
            career_stats=player.get("career_stats"),
        )
        auth = skills_authenticity(statline, statcast, is_pitcher, level)

        if signal_mm is not None and sample > 10:
            # § KALMAN: Gaussian conjugate update in PRECISION-consistent form.
            # K = prior_var / (prior_var + obs_var) = 1 / (1 + prior_prec * obs_var).
            # The old prior_prec / (prior_prec + obs_n) INVERTED the prior's role: a
            # TIGHTER prior (higher pedigree / age-for-level / source precision) moved
            # MORE on a noisy sample, the exact opposite of _prior_precision's contract
            # ("higher precision -> observation moves the posterior less"). Now a higher
            # prior precision correctly SHRINKS the gain, so a young high-bonus prospect's
            # FV prior is protected from a small noisy sample. obs_n is the observation
            # variance proxy (same magnitude the old denominator used).
            obs_n = _obs_noise(sample, is_pitcher)
            K     = 1.0 / (1.0 + max(1e-6, prior_prec) * obs_n)
            # § PROSPECT GAIN CAP: the FV is an informed consensus that should
            # dominate the prior. A single season of outlier rate stats
            # (BB%=26%, K%=6%) shouldn't override FV ordering.
            # Cap K at 0.22 and signal at ±60% of prior surplus so extreme
            # individual metrics can't completely override the FV hierarchy.
            K         = min(K, 0.22)
            max_sig   = prior_surplus_mm * 0.60
            signal_mm = max(-max_sig, min(max_sig, signal_mm))
            posterior_surplus_mm = round(prior_surplus_mm + K * signal_mm, 1)
            kalman_gain = round(K, 3)
            inputs_available.append("performance_signal")
            if recent_games:
                inputs_available.append("recent_games")
        else:
            posterior_surplus_mm = prior_surplus_mm
            kalman_gain          = 0.0
            roll_label           = "prior_only"

        if age is not None and (fv or 0.0) >= 50.0 and age <= 24.0:
            raw_prior = surplus_value_mm(fv, is_pitcher, position, age=age, eta_years=eta) or prior_surplus_mm
            floor_mult = 1.30 if (fv or 0.0) < 55.0 else 1.12
            prospect_floor = round(raw_prior * floor_mult, 1)
            if posterior_surplus_mm < prospect_floor:
                posterior_surplus_mm = prospect_floor
                inputs_available.append("young_top_prospect_prior_floor")

        if (
            age is not None
            and age <= 23.5
            and (fv or 0.0) >= 52.0
            and _has_top100_pedigree(player)
        ):
            raw_prior = surplus_value_mm(fv, is_pitcher, position, age=age, eta_years=eta) or prior_surplus_mm
            top100_floor = max(raw_prior * 1.65, 55.0 if (fv or 0.0) >= 54.0 else 48.0)
            if posterior_surplus_mm < top100_floor:
                posterior_surplus_mm = round(top100_floor, 1)
                inputs_available.append("recent_top100_prospect_floor")

        older_nonimpact_suppressed = False
        if (
            not is_pitcher
            and age is not None
            and age >= 23.0
            and (fv or 0.0) <= 50.0
            and str(level or "").upper() in {"AA", "AAA"}
        ):
            prospect_iso = _safe_float((statline or {}).get("iso"), 0.0) or 0.0
            prospect_ops_plus = _level_plus(statline) or 100.0
            prospect_k = _safe_float((statline or {}).get("k_pct"), 0.0) or 0.0
            if prospect_iso < 0.100 and prospect_ops_plus <= 100.0 and prospect_k >= 24.0:
                posterior_surplus_mm = round(posterior_surplus_mm * 0.42, 1)
                older_nonimpact_suppressed = True
                inputs_available.append("older_nonimpact_prospect_suppression")

        if (
            age is not None
            and (age <= 25.5 or (is_pitcher and age <= 26.0))
            and (fv or 0.0) >= 50.0
            and not older_nonimpact_suppressed
        ):
            raw_prior = surplus_value_mm(fv, is_pitcher, position, age=age, eta_years=eta) or prior_surplus_mm
            fv_v = float(fv or 0.0)
            if fv_v >= 55.0:
                rarity_floor = max(raw_prior * 1.35, 60.0)
            elif fv_v >= 54.0:
                rarity_floor = max(raw_prior * 1.50, 48.0)
            elif fv_v >= 52.0:
                rarity_floor = max(raw_prior * 1.55, 38.0)
            else:
                rarity_floor = max(raw_prior * 1.45, 30.0)
            fv50_trade_rarity_final_floor_mm = round(rarity_floor, 1)
            if posterior_surplus_mm < rarity_floor:
                posterior_surplus_mm = round(rarity_floor, 1)
                inputs_available.append("fv50_trade_rarity_floor")

    # ── § SCARCITY: positional scarcity multiplier ────────────────────────────
    scar = scarcity_multiplier(position)

    # ── § FLOOR: defensive floor guarantee ───────────────────────────────────
    # Proxy defensive grade from tool grades if available; default to 55 (above avg)
    # if position is C or SS and no explicit grade exists (conservative floor).
    tools       = player.get("tools") or {}
    def_grade_raw = (tools.get("defense") or tools.get("DEF") or
                     tools.get("arm") or tools.get("ARM"))
    def_grade   = _safe_float(def_grade_raw)
    pos_primary = _pos_primary(position)
    # For debuted/graduated players at premium defensive positions without an
    # explicit tool grade, assume above-average (55) — they've proven they can
    # hold the position at the MLB level.
    # For active PROSPECTS, do NOT apply this fallback: the FV already incorporates
    # positional scarcity, so assuming a 55 defensive grade would double-count it
    # (giving every SS prospect an extra ~$12M on top of their FV).
    # C and SS: holding those positions at all in MLB implies defensive viability —
    # BUT only when the player has demonstrated they can contribute offensively.
    # A catcher with career WAR ≤ 0 (Banfield -0.15, Ford -0.02) hasn't shown
    # they belong; the defensive floor would inflate them purely on position label.
    # Gate: career_war_yr > 0.5 required to receive the floor assumption.
    _career_waryr_for_floor = _safe_float((player.get("career_war") or {}).get("war_per_yr"), 0.0) or 0.0
    if def_grade is None and pos_primary in ("C", "SS") and is_mlb_player and _career_waryr_for_floor > 0.5:
        def_grade = 55.0
    # For debuted players, cap the floor window at remaining control years.
    floor_remaining = remaining_ctrl if is_mlb_player else None
    floor_mm = defensive_floor_mm(position, def_grade, remaining_years=floor_remaining)
    if is_mlb_player and locals().get("_suppress_no_power_infield_floors"):
        floor_mm = 0.0
        gross_floor_mm = 0.0
        inputs_available.append("no_power_infield_floor_suppression")
    if def_grade is not None:
        inputs_available.append("defensive_grade")

    # ── § AGE_CURVE (catcher dev bonus) ──────────────────────────────────────
    catcher_cfg = _cfg().get("catcher_dev", {})
    catcher_bonus = 0.0
    if pos_primary == "C" and age is not None:
        age_thr = float(catcher_cfg.get("age_threshold", 24))
        if age <= age_thr:
            catcher_bonus = float(catcher_cfg.get("late_peak_bonus", 0.08))

    # ── § FLASH: bimodal ceiling assessment ──────────────────────────────────
    flash = flash_assessment(player, level_norms)
    if flash["is_bimodal"]:
        inputs_available.append("flash_model")

    # ── § WORRY: worriedness score ────────────────────────────────────────────
    worry = worriedness_score(player, level_norms)
    if worry["score"] > 0.1:
        inputs_available.append("worriedness_signal")

    # ── § INJURY: structural discount for recurrent IL history ───────────────
    inj_discount = _injury_discount(player) if is_mlb_player else 0.0
    if inj_discount > 0.02:
        inputs_available.append("injury_history")

    # ── § OPTIONS: roster flexibility premium ────────────────────────────────
    opt_mm = options_premium_mm(player)

    # ── § RULE5: deadline urgency ─────────────────────────────────────────────
    r5_mm = rule5_urgency_mm(player)

    # ── § ARCHETYPE_POLICY: centralized group adjustment ─────────────────────
    archetype_policy = archetype_policy_adjustment(
        player,
        is_mlb_player=is_mlb_player,
        is_pitcher=is_pitcher,
        position=position,
        age=age,
        fv=fv,
        prior_surplus_mm=float(prior_surplus_mm),
        posterior_surplus_mm=float(posterior_surplus_mm),
        true_talent_war=float(true_talent_war) if is_mlb_player and "true_talent_war" in locals() else None,
        remaining_control_years=remaining_ctrl if is_mlb_player else None,
        authenticity=auth,
        worriedness=worry,
    )
    # THE MEASURED MLB PROJECTION OUTRANKS THE ARCHETYPE FLOOR (owner decision
    # 2026-07-31, docs/efv-2026-07-30/TRADE_ARCHETYPE_FLOOR_GATE.md).
    #
    # Until now this floor silently overrode the projection anchor set a few hundred
    # lines above, while the record kept emitting mlb_projection_surplus_anchor. So
    # the output announced an input that never reached the price: on the FV60 RF
    # fixture, anchoring at $35.0M and not anchoring at all produced the identical
    # $51.6M. Measured on the live board, the anchor applied to 276 of 6,414 rows
    # and this floor overrode it on 77 of them, carrying $1,365M (Alvarez, Yamamoto,
    # Fried, Suarez, Rasmussen).
    #
    # The floor's own docstring scopes it to "noisy early MLB evidence". The anchor
    # gate requires 500+ MLB PA for hitters, 1000+ overall, or 300+ IP, which is the
    # substantial-sample regime and the opposite of what the floor was written for.
    # So on the floor's stated purpose it does not apply here at all, and yielding is
    # the honest reading rather than the cautious one.
    #
    # Gated on the FLAG rather than on _projection_anchor because that local lives
    # inside the is_mlb_player block and is not in scope here for every player.
    _anchored = "mlb_projection_surplus_anchor" in inputs_available
    _floor_mm = archetype_policy["posterior_floor_mm"]
    if _floor_mm > posterior_surplus_mm and not _anchored:
        posterior_surplus_mm = _floor_mm
        inputs_available.append("archetype_posterior_floor")
    elif _floor_mm > posterior_surplus_mm and _floor_mm > 0.0:
        # Record that a REAL floor wanted to fire and was outranked, so the
        # suppression is auditable instead of invisible. Gated on > 0 because the
        # default floor is 0.0 and every negative-surplus player would otherwise
        # collect this tag for a floor that does not exist: measured, that was
        # firing on rows like Austin Riley whose archetype policy computed no floor
        # at all and only tagged stale_mlb_prior.
        inputs_available.append("archetype_floor_yielded_to_projection")
    if archetype_policy["posterior_multiplier"] != 1.0:
        posterior_surplus_mm = round(
            posterior_surplus_mm * archetype_policy["posterior_multiplier"],
            1,
        )
        inputs_available.append("archetype_posterior_multiplier")
    if (archetype_policy.get("features") or {}).get("suppress_additive_floors"):
        floor_mm = 0.0
        opt_mm = 0.0
        gross_floor_mm = 0.0
        inputs_available.append("archetype_suppress_additive_floors")

    multi_pos_mm, multi_pos_usage = multiposition_bonus_mm(
        player_key,
        position,
        is_pitcher=is_pitcher,
        is_mlb_player=is_mlb_player,
        remaining_years=remaining_ctrl if is_mlb_player else None,
        posterior_surplus_mm=float(posterior_surplus_mm),
    )
    if multi_pos_mm > 0:
        inputs_available.append("multiposition_bonus")

    # ── Assemble final trade value ────────────────────────────────────────────
    # trade_value = (posterior_surplus × scarcity × (1 + catcher_dev_bonus)
    #               + defensive_floor + multiposition + options + rule5)
    #               × (1 − injury_discount) × (1 − worriedness_discount)
    worry_discount = min(0.20, worry["score"] * 0.20)
    if "mlb_projection_surplus_anchor" in inputs_available:
        # The MLB projection surplus already bakes in recent performance and
        # playing-time risk, so keep board-level penalties from double-counting
        # the same current-season regression.
        current_form_flag = any(str(x).startswith("projection_anchor_current_form_") for x in inputs_available)
        max_injury_discount = 0.20 if _has_active_injury(player) else (0.12 if current_form_flag else 0.08)
        max_worry_discount = 0.08 if current_form_flag else 0.04
        capped_inj_discount = min(inj_discount, max_injury_discount)
        capped_worry_discount = min(worry_discount, max_worry_discount)
        if capped_inj_discount != inj_discount or capped_worry_discount != worry_discount:
            inputs_available.append("projection_anchor_discount_cap")
        inj_discount = capped_inj_discount
        worry_discount = capped_worry_discount

    core_mm = (posterior_surplus_mm * scar * (1.0 + catcher_bonus)
               + floor_mm + multi_pos_mm + opt_mm + r5_mm)
    trade_value_mm = round(core_mm * (1.0 - inj_discount) * (1.0 - worry_discount), 1)
    if fv50_trade_rarity_final_floor_mm > 0.0 and trade_value_mm < fv50_trade_rarity_final_floor_mm:
        trade_value_mm = fv50_trade_rarity_final_floor_mm
        inputs_available.append("fv50_trade_rarity_trade_floor")

    # Uncertainty bounds: always bracket the point estimate.
    # lo = the pessimistic (floor-only) scenario: worriedness at max discount,
    #      no Kalman update, scarcity applied to prior only.
    # hi = the optimistic scenario: no worriedness, full flash ceiling if bimodal,
    #      scarcity + floor + options.
    # We anchor off the point estimate to guarantee lo ≤ tv ≤ hi.
    lo_scale = 0.55 + 0.20 * (1.0 - worry["score"])   # [0.55, 0.75] depending on worry
    hi_scale  = 1.25 + 0.25 * kalman_gain             # [1.25, 1.50] depending on evidence weight
    if flash["is_bimodal"] and flash.get("p_click", 0) > 0.4:
        hi_scale += 0.15  # bimodal players with good p_click have fatter upside

    trade_value_lo = round(max(floor_mm, trade_value_mm * lo_scale), 1)
    trade_value_hi = round(trade_value_mm * hi_scale, 1)

    # Tier label
    if trade_value_mm is None:
        tier = "unknown"
    elif trade_value_mm >= 40:
        tier = "elite"
    elif trade_value_mm >= 20:
        tier = "high"
    elif trade_value_mm >= 8:
        tier = "mid"
    elif trade_value_mm >= 2:
        tier = "low"
    else:
        tier = "minimal"

    # ── Contract metadata for display ────────────────────────────────────────
    # Exposes service time, phase, current salary, and FA year so the frontend
    # can show a richer "contract spec" column rather than just "Xyr ctrl".
    _contract_meta: dict = {}
    if is_mlb_player:
        _cc  = player.get("current_contract") or {}
        _rs2 = player.get("roster_status") or {}
        _debut_str = _rs2.get("mlb_debut_date") or ""
        _debut_yr  = int(_debut_str[:4]) if _debut_str else None
        _today_yr  = date.today().year
        _fa_year   = (_debut_yr + _MLB_CONTROL_YEARS) if _debut_yr else None
        # Effective FA year = max(service-based, extension end)
        _ext_end   = _cc.get("signed_through")
        if _ext_end and _fa_year:
            _fa_year = max(_fa_year, int(_ext_end) + 1)
        elif _ext_end:
            _fa_year = int(_ext_end) + 1
        # Service years from debut (approximate)
        _svc_yrs = round((_today_yr - _debut_yr) if _debut_yr else 0, 1)
        # Contract phase — detect genuine long-term extensions first.
        # Players like Witt Jr. ($26.25M/yr through 2037) have service_phase='arb_eligible'
        # in the DB but are NOT on an arb deal; the extension supersedes the service clock.
        _aav         = float(_cc.get("aav_usd") or 0)
        _ext_end_yr  = _cc.get("signed_through")
        _svc_fa_yr   = (_debut_yr + _MLB_CONTROL_YEARS) if _debut_yr else None  # service-clock FA
        _is_ext      = bool(_ext_end_yr and _aav > 5_000_000 and
                           _ext_end_yr > (_svc_fa_yr or 0))
        _phase = _rs2.get("service_phase") or ""
        if _today_yr >= (_fa_year or 9999):
            _phase_label = "Free Agent"
        elif _is_ext:
            _phase_label = f"Ext. thru {_ext_end_yr}"
        elif _phase == "pre_arb":
            _phase_label = "Pre-Arb"
        elif _phase == "arb_eligible":
            # We intentionally omit the arb year number (Arb 1 / Arb 2 / Arb 3)
            # because computing it accurately requires official MLB service time
            # (accounting for 60-day IL exclusions, option year deductions, Super Two
            # cutoffs, etc.) which is not exposed by the MLB Stats API.  The current
            # salary already encodes which arb tier the player is in far more reliably
            # than any heuristic we can build from games-played or debut-date math.
            _phase_label = "Arb"
        else:
            _phase_label = "Team Control"
        # Current salary (this year's).
        # salary_by_year[2026] is the actual salary; fall back to league minimum for
        # pre-arb players whose contract data only shows $0 for future years.
        # Never use the AAV directly as the displayed salary — for pre-arb one-year
        # deals, AAV = salary/years_listed is misleadingly low ($267k for Cameron).
        _sal_this_yr = _cc.get("salary_by_year") or {}
        _sal_from_data = _sal_this_yr.get(str(_today_yr)) or 0
        _LEAGUE_MIN_USD = 780_000  # 2026 MLB league minimum
        _prev_aav_mm = _fa_prev_aav_mm(player)
        if _sal_from_data:
            _current_sal = max(_sal_from_data, _LEAGUE_MIN_USD)
        elif _aav > 0:
            _current_sal = _aav
        elif _prev_aav_mm is not None:
            _current_sal = _prev_aav_mm * 1_000_000
        else:
            _current_sal = _LEAGUE_MIN_USD
        # MiLB option years remaining (roster flexibility — distinct from contract options)
        _milb_opts_used = int(_rs2.get("options_used") or 0)
        _milb_opts_rem  = max(0, 3 - _milb_opts_used)

        # Contract player opt-outs and club options from contract_options.json
        _opt_entry      = _contract_options().get(player_key) or \
                          _contract_options().get((player.get("player_name") or "").lower().replace(" ", "_").replace(".", "")) or {}
        _player_opt_yrs = sorted(_opt_entry.get("player_options") or [])
        _club_opt_yrs   = sorted((c["year"] for c in (_opt_entry.get("club_options") or [])))

        _contract_meta = {
            "phase":              _phase_label,
            "current_salary_mm":  round(float(_current_sal) / 1e6, 2) if _current_sal else None,
            "signed_through":     _ext_end_yr,
            "service_years":      _svc_yrs,
            "aav_mm":             round(_aav / 1e6, 2) or None,
            "milb_options_remaining": _milb_opts_rem,
            # Contract structural options (player opt-outs and club options)
            "player_opt_years":   _player_opt_yrs,
            "club_opt_years":     _club_opt_yrs,
        }

    # § CRUNCH: roster-crunch exposure (Rule 5 urgency / 40-man status / option
    # years / service phase). All already computed above but never exported; a
    # compact sub-dict that SURVIVES board_slim (not in _BOARD_DROP) so the trade
    # board can flag protect-or-lose players and roll a per-org Crunch score. A
    # descriptive/deterministic lookup (no outcome to validate). Most meaningful for
    # the 40-man-eligible / MLB cohort (minor leaguers read on_40_man False / 3
    # options); the surface discloses that scope.
    _cr_roster = player.get("roster_status") or {}
    _cr_on40   = bool(_cr_roster.get("on_40_man"))
    _cr_used   = int(_cr_roster.get("options_used") or 0)
    _cr_left   = (int(_cr_roster["options_remaining"]) if _cr_roster.get("options_remaining") is not None
                  else max(0, 3 - _cr_used))
    _cr_signed_yr = (player.get("acquisition") or {}).get("year")
    _cr_years_in  = (date.today().year - int(_cr_signed_yr)) if _cr_signed_yr else None
    _cr_exp_yrs   = int(_cfg().get("rule5", {}).get("exposure_years_default", 3))
    _cr_r5_exp    = (not _cr_on40) and (_cr_years_in is not None and _cr_years_in >= _cr_exp_yrs)
    _cr_score = 0.0
    if _cr_r5_exp or r5_mm > 0:      _cr_score += 55.0   # must-protect by Nov or lose for ~$100k
    if _cr_on40 and _cr_left == 0:   _cr_score += 30.0   # out of options -> waiver-exposed to move
    elif _cr_on40 and _cr_left == 1: _cr_score += 12.0
    if _cr_on40:                     _cr_score += 10.0   # occupies a scarce 40-man slot
    crunch = {
        "on_40_man":        _cr_on40,
        "options_used":     _cr_used,
        "options_left":     _cr_left,
        "rule5_exposed":    _cr_r5_exp,
        "rule5_urgency_mm": round(r5_mm, 2),
        "service_phase":    _cr_roster.get("service_phase") or "none",
        "service_years":    (round(_svc_yrs, 1) if is_mlb_player else None),
        "score":            round(min(100.0, _cr_score), 1),
    }

    return {
        "player_key":            player_key,
        "player_name":           player.get("player_name"),
        "position":              position,
        "org":                   player.get("org"),
        "status":                status,
        "fv":                    fv,
        "age":                   age,

        # § GRPO
        "grpo_breakout_score":   grpo_score if not is_mlb_player else None,
        "grpo_fv_adj":           round(grpo_fv_adj, 1) if not is_mlb_player else None,
        "fv_effective":          fv_effective if not is_mlb_player else fv,

        # § PRIOR
        "prior_surplus_mm":      round(float(prior_surplus_mm), 1),

        # § KALMAN
        "kalman_gain":           round(float(kalman_gain if 'kalman_gain' in dir() else 0.0), 3),
        "posterior_surplus_mm":  round(float(posterior_surplus_mm), 1),

        # § AUTHENTIC
        "authenticity":          skills_authenticity(statline, statcast, is_pitcher, level),

        # § SCARCITY + § FLOOR
        "scarcity_mult":         round(scar, 3),
        "defensive_floor_mm":    round(floor_mm, 2),
        "catcher_dev_bonus":     round(catcher_bonus, 3),
        "multiposition_bonus_mm": round(multi_pos_mm, 2),
        "position_usage":         multi_pos_usage,

        # § FLASH
        "flash":                 flash,

        # § WORRY + § INJURY
        "worriedness":           worry,
        "injury_discount":       round(inj_discount, 3),
        "archetype_policy":      archetype_policy,

        # § OPTIONS + § RULE5
        "options_premium_mm":    round(opt_mm, 2),
        "rule5_urgency_mm":      round(r5_mm, 2),

        # § CRUNCH (roster-decision exposure; survives board_slim for the board chip + per-org score)
        "crunch":                crunch,

        # Final values
        "trade_value_mm":        trade_value_mm,
        "trade_value_lo":        trade_value_lo,
        "trade_value_hi":        trade_value_hi,
        "trade_value_tier":      tier,
        # Active rarity floor (None when the FV50+ young-prospect floor didn't apply).
        # Policy invariant: trade_value_mm never sits below this when set.
        "fv50_trade_rarity_final_floor_mm": (
            fv50_trade_rarity_final_floor_mm if fv50_trade_rarity_final_floor_mm > 0.0 else None
        ),

        # Metadata
        "rolling_label":         roll_label if 'roll_label' in dir() else "none",
        "inputs_available":      inputs_available,
        "computed_at":           date.today().isoformat(),

        # Service / contract context (debuted players only)
        "remaining_control_years": round(remaining_ctrl, 1) if is_mlb_player else None,
        "control_years_source":    ctrl_source if is_mlb_player else None,
        "contract":                _contract_meta if is_mlb_player else {},
        # Trial period
        "trial_factor":            round(tau, 3) if is_mlb_player else None,
        "true_talent_war":         round(true_talent_war, 2) if is_mlb_player else None,
        "gross_floor_mm":          round(gross_floor_mm, 1) if is_mlb_player else None,
    }


# ---------------------------------------------------------------------------
# Batch computation and JSON export
# ---------------------------------------------------------------------------

def _latest_affiliated_season(player: dict) -> int | None:
    seasons: list[int] = []
    rows = list(player.get("career_stats") or [])
    statline = player.get("statline")
    if isinstance(statline, dict):
        rows.append(statline)
    for row in rows:
        level = str(row.get("level") or "").upper()
        if level not in {"MLB", "AAA", "AA", "A+", "A", "CPX", "DSL"}:
            continue
        try:
            seasons.append(int(row.get("season")))
        except (TypeError, ValueError):
            continue
    return max(seasons) if seasons else None


def _trade_value_export_eligible(player: dict) -> bool:
    org = str(player.get("org") or "").strip().lower()
    if org == "office of the commissioner":
        return False

    status = player.get("status")
    if status == "active":
        return True

    roster = player.get("roster_status") or {}
    if roster.get("on_40_man"):
        return True

    contract = player.get("current_contract") or {}
    if contract.get("salary_usd") or contract.get("total_usd") or contract.get("signed_through"):
        return True

    latest = _latest_affiliated_season(player)
    if latest is None:
        return False
    return latest >= date.today().year - 1


def compute_all_trade_values(
    players: list[dict],
    level_norms: dict | None = None,
) -> list[dict]:
    """Compute Bayesian trade values for all players.

    Players without an FV are skipped. Errors per player are caught
    individually so one bad record doesn't abort the whole batch.

    Deduplication: when the same player_key appears in multiple source
    files (e.g. both debuts.json and graduates.json), keep the record
    with the most complete status. Priority: graduated > debuted > active.
    Roman Anthony / Schlittler appear in both debuts and graduates;
    without dedup they render twice on the Trade Board.
    """
    # graduated and debuted are both "MLB player" status — treat as equal
    # priority so the data-freshness tiebreak below picks the more current record.
    _STATUS_PRIORITY = {"graduated": 1, "debuted": 1, "active": 0}

    # Deduplicate input by player_key, keeping the highest-priority status
    seen: dict[str, dict] = {}
    for p in players:
        if not _trade_value_export_eligible(p):
            continue
        key = p.get("player_key")
        if not key:
            continue
        if key not in seen:
            seen[key] = p
        else:
            existing_pri = _STATUS_PRIORITY.get(seen[key].get("status", ""), 0)
            new_pri      = _STATUS_PRIORITY.get(p.get("status", ""), 0)
            if new_pri > existing_pri:
                seen[key] = p
            elif new_pri == existing_pri:
                # Same status priority: prefer the record with more current-season data
                # (graduates.json can be stale vs debuts.json for the same player)
                def _cs_games(rec):
                    cs = (rec.get("career_stats") or [{}])
                    row = cs[0] if cs else {}
                    return float(row.get("ip") or row.get("ab") or row.get("games") or 0)
                if _cs_games(p) > _cs_games(seen[key]):
                    seen[key] = p

    results: list[dict] = []
    for p in seen.values():
        try:
            n_sources = int(p.get("fv_total_instances") or 3)
            tv = bayesian_trade_value(p, level_norms=level_norms, n_sources=n_sources)
            if tv.get("trade_value_mm") is not None:
                results.append(tv)
        except Exception:
            _log.exception("bayes_trade_value: error processing %s", p.get("player_key", "?"))
    return results


# Per-player detail fields that the COMPUTE produces (and the policy tests inspect in
# memory) but NO frontend code reads off the written file -- ~2.4MB of dead weight that
# made the Trade Machine view fetch+parse a 7.6MB JSON before painting. Dropped from the
# WRITTEN file only; the in-memory compute result is untouched (tests use it directly).
_BOARD_DROP = (
    # heavy detail blocks (~2.4MB)
    "archetype_policy", "worriedness", "inputs_available", "position_usage",
    # per-player breakdown scalars the compute emits but NO frontend file reads (verified
    # by grep across assets/*.js + prospx + build_site): the model internals, not display.
    "kalman_gain", "authenticity", "trial_factor", "true_talent_war", "scarcity_mult",
    "gross_floor_mm", "prior_surplus_mm", "catcher_dev_bonus", "defensive_floor_mm",
    "multiposition_bonus_mm", "options_premium_mm", "rule5_urgency_mm",
    "control_years_source", "rolling_label", "computed_at", "fv_effective",
    "fv50_trade_rarity_final_floor_mm",
)  # posterior_surplus_mm is KEPT (the evaluator's prospect-pool currency)
_FLASH_KEEP = ("is_bimodal", "p_click")                       # board ceiling flag + tooltip
_CONTRACT_KEEP = ("phase", "current_salary_mm", "signed_through", "fa_year", "aav_mm",
                  "player_opt_years", "club_opt_years")        # _tbCtrlBadge consumes these


def board_slim(r: dict) -> dict:
    """Slim one trade-value record for the board/evaluator payload: drop the unconsumed
    detail fields and trim flash/contract to the sub-fields the frontend reads. Returns a
    NEW dict (never mutates the compute result)."""
    out = {k: v for k, v in r.items() if k not in _BOARD_DROP}
    fl = r.get("flash")
    if isinstance(fl, dict):
        out["flash"] = {k: fl[k] for k in _FLASH_KEEP if k in fl}
    cc = r.get("contract")
    if isinstance(cc, dict):
        out["contract"] = {k: cc[k] for k in _CONTRACT_KEEP if k in cc}
    return out


def _platform_tier(mm: float | None) -> str:
    """Tier label from a surplus $M, matching the board filter thresholds
    (Elite $40M+ / High $20-40M / Mid $8-20M)."""
    if mm is None:
        return "low"
    if mm >= 40:
        return "elite"
    if mm >= 20:
        return "high"
    if mm >= 8:
        return "mid"
    if mm >= 0:
        return "low"
    return "minimal"


# Trade Value Grade thresholds ($M of contract-adjusted surplus -> letter). The
# surplus already nets salary out of projected production over the control window,
# so the grade reads "how valuable is this player to ACQUIRE in trade." A finer-
# grained, on-brand companion to the farm letter grades; the board/evaluator JS
# mirror these exact cutoffs in `_tbGrade` so server and client agree.
_TRADE_GRADE_CUTS = (
    (100.0, "A+"),   # franchise cornerstone
    (60.0,  "A"),
    (40.0,  "A-"),   # = Elite tier floor
    (25.0,  "B+"),
    (15.0,  "B"),
    (8.0,   "B-"),   # = Mid tier floor
    (3.0,   "C"),
    (0.0,   "D"),
    (float("-inf"), "F"),   # negative surplus = contract liability
)


def _trade_value_grade(mm: float | None) -> str | None:
    """Letter grade (A+ .. F) for a contract-adjusted surplus $M. None passes
    through (no grade for players with no computed value)."""
    if mm is None:
        return None
    v = float(mm)
    for thr, g in _TRADE_GRADE_CUTS:
        if v >= thr:
            return g
    return "F"


def _roster_seasons_index(data_dir: Path) -> dict:
    """player_key -> (last_mlb_season, n_mlb_seasons) from debuts.json's
    roster_status.mlb_seasons. Used to (a) drop players who have not appeared in
    MLB for 2+ seasons (no longer active assets - e.g. restricted-list / retired
    players) and (b) date how established a debuted player is so the prospect-era
    backgrade can be tempered toward his realized MLB performance."""
    out: dict = {}
    try:
        d = json.loads((Path(data_dir) / "debuts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    players = d.get("players") if isinstance(d, dict) else d
    if isinstance(players, dict):
        players = list(players.values())
    for p in (players or []):
        pk = p.get("player_key")
        seasons = ((p.get("roster_status") or {}).get("mlb_seasons")) or []
        if pk and seasons:
            out[pk] = (max(seasons), len(seasons))
    return out


def _backgrade_realized_factor(age, realized_war, proj_war_6yr, n_seasons) -> float:
    """Discount-only factor in [0,1] that tempers a DEBUTED player's prospect-era
    backgrade surplus toward his realized MLB performance. The backgrade prices
    `xfv_war_6yr` (the projection from his PROSPECT profile), so a former top
    prospect who busted (Hiura: proj 10.3 WAR, realized 0.8) is otherwise valued
    like the prospect he never became. Trust realized more the more established
    the player is (by MLB seasons OR age); never inflates (cap at 1.0)."""
    if proj_war_6yr is None or realized_war is None or n_seasons is None:
        return 1.0
    proj_rate = float(proj_war_6yr) / 6.0
    if proj_rate <= 0:
        return 1.0
    n = max(1, int(n_seasons))
    f_seasons = min(1.0, n / 4.0)                                  # ~4 MLB seasons -> realized dominates
    f_age = 0.0 if age is None else max(0.0, min(1.0, (float(age) - 24.0) / 5.0))
    f = max(f_seasons, f_age)                                      # most-established signal wins
    realized_rate = max(0.0, float(realized_war) / n)             # floored at replacement
    eff_rate = (1.0 - f) * proj_rate + f * realized_rate
    return max(0.0, min(1.0, eff_rate / proj_rate))


def _sortino_fields(dist: dict | None, scale: float) -> dict | None:
    """Downside-risk stats from the persisted 5-point eFV surplus fan. A prospect
    is an option on future WAR, so upside variance is not risk; only the shortfall
    below the mean is. Semi-deviation DD = sqrt(sum w_i * min(q_i - mean, 0)^2)
    over the p10..p90 quadrature. Returns display fields scaled to the board's
    shown value ($ fields scale; the ratio is scale-invariant). risk_mm applies a
    LOCAL half-lambda and does NOT touch the global risk_aversion_lambda (which
    stays 0 and feeds the separate prospx risk_adjusted_mm)."""
    if not dist:
        return None
    mean = dist.get("mean_mm")
    pts = [dist.get(k) for k in ("p10_mm", "p25_mm", "p50_mm", "p75_mm", "p90_mm")]
    if mean is None or any(p is None for p in pts):
        return None
    w = (0.15, 0.25, 0.25, 0.25, 0.10)
    dd = sum(wi * min(float(p) - float(mean), 0.0) ** 2 for wi, p in zip(w, pts)) ** 0.5
    sortino = (float(mean) - float(pts[0])) / max(dd, 0.1)   # upside cushion per unit downside
    return {
        "p_bust": dist.get("p_bust"),
        "downside_mm": round(dd * scale, 1),
        "risk_mm": round((float(mean) - 0.5 * dd) * scale, 1),
        "sortino": round(min(99.0, max(0.0, sortino)), 2),
    }


def apply_platform_surplus(records: list[dict], data_dir: Path | str) -> dict:
    """Re-point each Trade Machine record's surplus to the PLATFORM-STANDARD value the rest
    of the site shows, so the board/evaluator stop using bayes' own (floored/scarcity-scaled)
    number that the owner flagged as out of line:

      active prospects -> PROSPX eFV surplus      (data/xfv.json by_player[key].surplus_mm)
      MLB (modeled)    -> MLB Projections surNpv  (data/mlb_projections.json vets/prospects)
      MLB (unmodeled)  -> eFV backgrade surplus   (universal fallback; ~99.5% MLB coverage)

    Also backfills null ages from the projection artifacts (player_key join). All sources are
    value_framework-priced, so this makes Trade Machine == PROSPX/Projections. Defensive: if an
    artifact is missing/stale, the record keeps its existing bayes value. Mutates in place;
    returns a small stats dict. GRPO breakout (grpo_breakout_score) is left as a DISPLAY signal
    only -- it no longer drives the shown value (that was a source of the misalignment)."""
    dd = Path(data_dir)

    def _load(name):
        try:
            return json.loads((dd / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    xfv = (_load("xfv.json") or {}).get("by_player", {}) or {}
    mp = _load("mlb_projections.json") or {}
    det = (_load("mlb_player_detail.json") or {}).get("players", {}) or {}

    proj_sur, ages = {}, {}
    for grp in ("vets", "prospects"):
        for r in (mp.get(grp) or []):
            k = r.get("key")
            if not k:
                continue
            if r.get("surNpv") is not None:
                proj_sur[k] = r["surNpv"] / 1e6        # surNpv is raw $; board surplus is $M
            if r.get("age") is not None:
                ages.setdefault(k, r["age"])
    for k, v in det.items():
        if v.get("age") is not None:
            ages.setdefault(k, v["age"])

    roster = _roster_seasons_index(dd)                       # pk -> (last_mlb_season, n_seasons)
    current_season = max((ls for ls, _ in roster.values()), default=None)

    stats = {"xfv": 0, "projection": 0, "xfv_backgrade": 0, "unchanged": 0,
             "age_backfilled": 0, "inactive_dropped": 0, "backgrade_tempered": 0}
    for r in records:
        pk = r.get("player_key")
        is_pros = r.get("status") == "active"
        # Resolve age up front (backfilled from the projection artifacts) - the
        # backgrade temper below reads it.
        age = r.get("age")
        if age is None and pk in ages:
            age = ages[pk]
            r["age"] = age
            stats["age_backfilled"] += 1

        # Drop debuted players who have not appeared in MLB for 2+ seasons: they
        # are no longer active trade assets (restricted-list / retired / released
        # - e.g. Wander Franco, last MLB season 2023). Active prospects are never
        # dropped, and neither are players the projection system still models (an
        # injured star with a forward projection stays). trade_value_mm=None ->
        # the board's null filter omits them.
        if not is_pros and pk not in proj_sur and pk in roster and current_season is not None \
                and roster[pk][0] <= current_season - 2:
            r["trade_value_mm"] = None
            r["posterior_surplus_mm"] = None
            r["trade_value_grade"] = None
            r["trade_value_tier"] = None
            r["surplus_source"] = "inactive_dropped"
            stats["inactive_dropped"] += 1
            continue

        xe = xfv.get(pk) or {}
        x_sur = xe.get("surplus_mm")
        # Carry the raw eFV grade through to the board: the convex-$/WAR + $0-floor
        # surplus transform compresses within-tier ordering (the backtest shows the
        # grade orders realized WAR better than the $-transform; surplus itself is
        # priced on the displayed quantile grade since 2026-07-06), so the board
        # uses xfv_grade as the within-tier tie-break for the bunched
        # low/floored block. Display value stays trade_value_mm.
        if xe.get("xfv_grade") is not None:
            r["xfv_grade"] = xe.get("xfv_grade")
        # Also carry the continuous 6yr WAR projection through as a FINER within-
        # tier tie-break: at the $-floor a large block (~1/3) compresses to one
        # surplus value AND the same displayed grade, where xfv_grade can no
        # longer separate them. xfv_war_6yr is the continuous quantity behind the
        # grade, so it breaks those ties by projected value. Display value stays
        # trade_value_mm; this only orders otherwise-tied rows.
        if xe.get("xfv_war_6yr") is not None:
            r["xfv_war_6yr"] = xe.get("xfv_war_6yr")
        new, src = None, None
        if is_pros:
            if x_sur is not None:
                new, src = x_sur, "xfv"
        else:
            if pk in proj_sur:
                new, src = proj_sur[pk], "projection"
            elif x_sur is not None:
                # Temper the prospect-era backgrade toward realized MLB outcomes
                # for established debuted players (a busted former top prospect
                # otherwise carries the value of the prospect he never became).
                rs = roster.get(pk)
                factor = _backgrade_realized_factor(
                    age, xe.get("realized_war"), xe.get("xfv_war_6yr"),
                    rs[1] if rs else None)
                new, src = x_sur * factor, "xfv_backgrade"
                if factor < 0.999:
                    stats["backgrade_tempered"] += 1
        if new is not None:
            mm = round(float(new), 1)
            r["trade_value_mm"] = mm
            r["posterior_surplus_mm"] = mm
            r["trade_value_tier"] = _platform_tier(mm)
            r["surplus_source"] = src
            # eFV credible-interval bands + Sortino apply ONLY when the shown value came
            # from the eFV entry (xfv / xfv_backgrade). A "projection"-sourced MLB row's
            # value is the projection surNpv, NOT the eFV surplus, so attaching xe's
            # prospect-era band_p10/p90 + dist to it was a basis mismatch -> leave null.
            if src in ("xfv", "xfv_backgrade"):
                lo, hi = xe.get("band_p10_mm"), xe.get("band_p90_mm")
                # Scale the bands with a tempered backgrade so they stay consistent.
                scale = (mm / float(x_sur)) if (src == "xfv_backgrade" and x_sur) else 1.0
                r["trade_value_lo"] = round(float(lo) * scale, 1) if lo is not None else None
                r["trade_value_hi"] = round(float(hi) * scale, 1) if hi is not None else None
                # Risk-adjusted surplus (Sortino): downside-only risk from the eFV fan.
                rf = _sortino_fields(xe.get("dist"), scale)
                if rf:
                    r["p_bust"] = rf["p_bust"]
                    r["downside_mm"] = rf["downside_mm"]
                    r["risk_mm"] = rf["risk_mm"]
                    r["sortino"] = rf["sortino"]
            else:
                # src == "projection": the bayes compute's lo/hi bracketed the
                # DISCARDED bayes value, so the re-pointed surNpv could sit
                # outside its own band. No band exists on this basis -> null
                # (the frontends null-guard the range tooltip).
                r["trade_value_lo"] = None
                r["trade_value_hi"] = None
            stats[src] += 1
        else:
            stats["unchanged"] += 1
        # Trade Value Grade off the FINAL value (re-pointed or bayes fallback) so
        # every board row carries a letter; survives board_slim automatically.
        r["trade_value_grade"] = _trade_value_grade(r.get("trade_value_mm"))

    # ------------------------------------------------------------------ #
    # MLB veterans the projection system prices but the board never saw
    # ------------------------------------------------------------------ #
    # The board population is assembled from timeseries.json + debuts.json +
    # graduates.json, ALL THREE of which are prospect-derived: a player is only
    # in them if this platform once tracked him as a prospect. An established
    # veteran who was never in our ranking coverage - because he debuted before
    # it, came from NPB/KBO, or was simply never ranked - therefore never
    # reached the trade board, no matter how thoroughly /projections/ modelled
    # him.
    #
    # Measured 2026-08-01: 325 of 1,319 projected vets (24.6%) were absent,
    # including AARON JUDGE ($24.6M surplus through 2031), garrett_crochet and
    # matt_chapman. The loop above could never fix it - it re-prices records
    # that exist and has no path to ADD one.
    #
    # These rows are priced on EXACTLY the basis an MLB row already on the board
    # gets (src="projection", value = surNpv), so the board stays one currency.
    # No FV is invented: the prospect Bayesian model is not run on them, because
    # fabricating a grade to get a player onto a board is the defect class this
    # codebase has removed twice (the BA-statcast FV-40 and the
    # performance_ingest FV-35).
    added = _append_projection_only_rows(records, proj_sur, ages, det, dd)
    stats["projection_only_added"] = added
    return stats


def _append_projection_only_rows(records: list, proj_sur: dict, ages: dict,
                                 det: dict, data_dir) -> int:
    """Append board rows for priced vets missing from the prospect-derived pool.

    Only vets carrying a surNpv are added - that IS the priced value, and a row
    without one has no value on any basis the board serves (see the coverage
    test for what the remainder is and why it is deliberately not invented)."""
    present = {r.get("player_key") for r in records if r.get("player_key")}
    try:
        proj = json.loads((Path(data_dir) / "mlb_projections.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    n = 0
    for v in (proj.get("vets") or []):
        pk = v.get("key")
        if not pk or pk in present or pk not in proj_sur:
            continue
        mm = round(float(proj_sur[pk]), 1)
        row = {
            "player_key": pk,
            "player_name": v.get("name"),
            "position": v.get("pos"),
            "org": v.get("team"),
            "status": "debuted",              # an MLB veteran, never a tracked prospect
            "age": v.get("age") if v.get("age") is not None else ages.get(pk),
            "trade_value_mm": mm,
            "posterior_surplus_mm": mm,
            "trade_value_tier": _platform_tier(mm),
            "trade_value_grade": _trade_value_grade(mm),
            "surplus_source": "projection",
            # Same deliberate null as the projection branch above: the eFV
            # credible band is a prospect-era basis and does not describe a
            # contract-surplus NPV.
            "trade_value_lo": None,
            "trade_value_hi": None,
            # Why this row exists at all, so the board can say so rather than
            # leaving a reader to wonder why a star appeared from nowhere.
            "board_entry": "projection_only",
        }
        thru, aav = v.get("thru"), v.get("aav")
        if thru is not None or aav is not None:
            row["contract"] = _clean_contract({
                "signed_through": thru,
                "aav_mm": round(aav / 1e6, 1) if aav is not None else None,
                "fa_year": (thru + 1) if thru is not None else None,
            })
        records.append(row)
        n += 1
    return n


def _clean_contract(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _unpriced_vets(data_dir, on_board: set | None = None) -> list[dict]:
    """Projected vets priced NOWHERE, and why.

    `on_board` is the set of keys already carrying a value. It matters: a vet can
    have no CONTRACT surplus (expiring deal) and still be on the board through the
    eFV path, because he was once a tracked prospect - tarik_skubal is exactly
    that. Publishing him as "not tradeable" would be false, and would render a
    dimmed row in search for a player who IS tradeable. "Unpriced" has to mean
    unpriced on EVERY basis, not just the contract one.

    Two honest reasons, neither of which is a missing row:
      expiring     - the contract ends before the projection horizon opens, so
                     there is no team-controlled season left. A pending free
                     agent is not a trade asset; the FA module prices him.
      no_contract  - nothing on file (pre-arb / optioned players Spotrac does
                     not list), so there is no salary to subtract from value.

    Deliberately NOT given a fabricated value. `no_contract` is the larger and
    more interesting group - those players have real team control and would
    carry substantial surplus at the league minimum - and pricing them is a
    modelling decision, registered rather than smuggled in here."""
    try:
        proj = json.loads((Path(data_dir) / "mlb_projections.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    first = proj.get("first_season") or 0
    out = []
    for v in (proj.get("vets") or []):
        if not v.get("key") or v.get("surNpv") is not None:
            continue
        if on_board and v["key"] in on_board:
            continue                    # priced by another basis (eFV backgrade)
        thru = v.get("thru")
        out.append({
            "key": v["key"], "name": v.get("name"), "org": v.get("team"),
            "pos": v.get("pos"), "thru": thru,
            "war5": v.get("warTotal"),
            "reason": "expiring" if (thru is not None and thru < first) else "no_contract",
        })
    out.sort(key=lambda r: -(r.get("war5") or 0))
    return out


def _projection_coverage(records: list, data_dir) -> dict:
    """Is every vet the projection system PRICES also on the trade board?

    The invariant that would have caught Aaron Judge's absence. Stamped into the
    artifact so a population regression is visible in the data, not just in a log
    line - the board silently lost a quarter of the projected veteran universe and
    nothing anywhere reported it.

    `unpriceable` is NOT a failure. It counts vets the projection system models
    but cannot price, and there are exactly two kinds, both correct:
      - contract expires this season (no team-controlled season inside the
        2027-2031 horizon, so there is no future surplus to trade) - this is why
        aj_minter is absent, and he is a pending free agent, not a lost row;
      - no contract on file at all (pre-arb / optioned players Spotrac does not
        list), so there is no salary to subtract from projected value.
    Neither is invented a value here. The second group is the larger open
    question and is registered in the coverage doc, not papered over."""
    on_board = {r.get("player_key") for r in records
                if r.get("player_key") and r.get("trade_value_mm") is not None}
    try:
        proj = json.loads((Path(data_dir) / "mlb_projections.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"available": False}
    vets = [v for v in (proj.get("vets") or []) if v.get("key")]
    priced = [v for v in vets if v.get("surNpv") is not None]
    missing = [v for v in priced if v["key"] not in on_board]
    unpriceable = [v for v in vets if v.get("surNpv") is None]
    expiring = sum(1 for v in unpriceable
                   if v.get("thru") is not None and v.get("thru") < (proj.get("first_season") or 0))
    return {
        "available": True,
        "vets": len(vets),
        "priced_vets": len(priced),
        "priced_on_board": len(priced) - len(missing),
        "missing": len(missing),
        "examples": [v["key"] for v in sorted(
            missing, key=lambda x: -(x.get("warTotal") or 0))[:5]],
        "unpriceable": len(unpriceable),
        "unpriceable_expiring": expiring,
        "unpriceable_no_contract": len(unpriceable) - expiring,
    }


def export_trade_values_json(
    players: list[dict],
    out_path: Path | str,
    level_norms: dict | None = None,
) -> int:
    """Compute and write data/trade_values.json (board-slim payload).

    Returns the number of players exported.
    """
    out_path = Path(out_path)
    results  = compute_all_trade_values(players, level_norms=level_norms)

    # Re-point surplus to the platform-standard value (PROSPX eFV / MLB Projections) + backfill
    # ages, then sort by the ALIGNED value.
    st = apply_platform_surplus(results, out_path.parent)
    _log.info("trade_values platform-surplus: %s", st)
    # Drop players apply_platform_surplus flagged inactive (no MLB appearance in
    # 2+ seasons - restricted-list / retired / released); they are not tradeable
    # assets and shouldn't appear on the board.
    results = [r for r in results if r.get("surplus_source") != "inactive_dropped"]
    results.sort(key=lambda r: r.get("trade_value_mm") if r.get("trade_value_mm") is not None else -1e9, reverse=True)

    cov = _projection_coverage(results, out_path.parent)
    if cov.get("missing"):
        _log.warning("trade_values COVERAGE: %d priced vets are NOT on the board "
                     "(e.g. %s) - the board population regressed",
                     cov["missing"], ", ".join(cov.get("examples") or []))
    else:
        _log.info("trade_values coverage: every priced vet is on the board "
                  "(%d of %d projected vets; %d unpriceable, see 'unpriceable')",
                  cov.get("priced_on_board", 0), cov.get("vets", 0),
                  cov.get("unpriceable", 0))

    payload = {
        "generated_at": date.today().isoformat(),
        # Which dollar calibration produced these numbers. Four served artifacts
        # silently disagreed on 2026-07-31 because none of them said.
        "calibration":   vf.calibration_stamp(),
        # Board-vs-projection coverage, stamped so a regression is visible in the
        # artifact itself rather than only in a log line nobody reads.
        "coverage":      cov,
        # Vets the projection system models but CANNOT price, with the reason.
        # They are kept OUT of `players` so they never pollute a value ranking,
        # and shipped here so the search can answer "why isn't he here?" instead
        # of returning nothing - which is what sent someone looking for
        # A.J. Minter into the code.
        "unpriced":      _unpriced_vets(
            out_path.parent,
            {r.get("player_key") for r in results
             if r.get("trade_value_mm") is not None}),
        "count":         len(results),
        "players":       [board_slim(r) for r in results],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )
    _log.info("trade_values export: %d players → %s", len(results), out_path)
    return len(results)
