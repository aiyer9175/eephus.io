# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Alchemy Lab - the role-conversion model core (pure, no network).

Two transparent 0-100 candidate scores plus the conversion-history detection and
labeling. The design is deliberately a SCREEN, not a success-probability model:
the sabermetric literature (Clemens' swingman study, the BP/SABR times-through-
order work, Baumann on Helsley) is clear that the mechanism is the times-through-
order (TTO) penalty and the lever is ARSENAL COMPOSITION, while the observed
conversion sample is tiny and selection-biased (we only see arms teams chose to
convert). So:

  - RP->SP FIT: "can this reliever survive a lineup three times?" The role-
    STRUCTURAL signal is arsenal depth (a starter needs >=3 pitches); the rest
    (command, fastball reliance, platoon-neutrality, contact quality) are quality
    lanes. A hard arsenal-depth gate is the real differentiator, surfaced as a
    chip, not buried in the weighted blend.
  - SP->RP FIT: "would this starter's stuff play up in one-inning bursts?" The
    traits that hurt a starter (thin arsenal, fastball-heavy, big TTO leak) are
    exactly what make a good reliever, so TTO leakage is the complement of the
    RP->SP arsenal-depth score.

Weights are PRIORS from the literature; the small, selected conversion sample can
only sign-check them (pal_export runs the backtest as a directional gate over a
raw-quality residual, never as a weight-fitter). Velocity role-delta is the
rigorous +-1.0 mph (Clemens), scaled up for power/thin-arsenal arms; the REM+
relief projection is DISPLAY-ONLY so a hand-set relief assumption is never
laundered into a scored input.

This module is PURE. pal_export.py assembles the reachable Statcast/StatsAPI
features and calls these functions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rate_stabilization import NEED_ERA_SHRINK_IP

# ---- role detection (from season GS/G/IP) ---------------------------------- #
SP_GS_SHARE = 0.60
SP_IP_PER_G = 3.5
RP_GS_SHARE = 0.10
CONV_MIN_IP = 20.0        # min IP each side of a conversion to count (not a cameo)

# ---- velocity role delta (Clemens-rigorous central, shape-interacting) ------ #
BASE_VELO_DELTA = 1.0     # mph; RP->SP loses, SP->RP gains
MAX_VELO_DELTA = 2.2      # cap for pure power / thin-arsenal arms

# ---- default relief K% bump (overridden by the measured converter mean) ----- #
DEFAULT_RELIEF_K_BUMP = 0.025   # +2.5 K% moving to one-inning bursts (prior)

# ---- fit weights (priors) --------------------------------------------------- #
RP_SP_WEIGHTS = {
    "arsenal_depth": 0.35,   # the role-STRUCTURAL signal
    "command": 0.20,
    "fb_reliance_inv": 0.15,
    "stuff_quality": 0.10,
    "platoon_neutrality": 0.12,
    "survivability": 0.08,
}
# SP->RP is upside GATED BY NEED: a starter who is succeeding has no conversion
# case no matter how well his stuff would play up in relief (a good starter is
# worth more than a good reliever). The relief-upside blend is multiplied by a
# conversion-need factor from the starter's actual results.
SP_RP_UPSIDE_WEIGHTS = {
    "stuff_upside": 0.35,
    "putaway": 0.30,
    "velo_leverage": 0.20,
    "tto_leakage": 0.15,     # complement of arsenal depth (thin/FB-heavy leaks late)
}


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


# --------------------------------------------------------------------------- #
# feature container
# --------------------------------------------------------------------------- #
@dataclass
class PalArm:
    """One pitcher-season's conversion features (all reachable/bulk)."""
    mlbam: int
    name: str = ""
    team: str = ""
    season: int = 0
    role: str = ""           # SP | RP | SWING
    g: float = 0.0
    gs: float = 0.0
    ip: float = 0.0
    tbf: float = 0.0
    k_pct: Optional[float] = None
    bb_pct: Optional[float] = None
    era: Optional[float] = None      # current-role ERA (the "is he succeeding?" signal)
    # arsenal (from statcast_pitcher_arsenal_stats): per-pitch dicts
    #   {pitch, usage (0-1), whiff (0-1), est_woba, hard_hit (0-1)}
    arsenal: list = field(default_factory=list)
    fb_velo: Optional[float] = None     # top fastball avg velo (mph)
    # platoon (StatsAPI sitCodes vl/vr): OPS-against by batter hand
    ops_vl: Optional[float] = None
    ops_vr: Optional[float] = None
    platoon_tbf: Optional[float] = None  # min batters faced across hands (sample gate)
    p_throws: Optional[str] = None      # 'L' | 'R' (for reverse-split direction)
    rem_plus: Optional[int] = None      # current reliever REM+ (relievers only)
    was_starter: Optional[bool] = None  # started in a prior MLB season (re-conversion ease)
    prospx_role: Optional[str] = None   # PROSPX prospect-era role, when known (SP/RP/...)
    # W3 PAL-XRV (default None = incumbent path): per-pitch-type AAA aStuff+
    # rows {pitch_type: {stuff_plus, n_pitches}} from data/stuff_plus_aaa.json.
    # Attached by the assembly layer (pal_export) ONLY when EEPHUS_PAL_XRV is
    # set AND the pitcher clears the recent-AAA coverage gate; this module
    # stays pure (behavior is a function of the arm alone).
    aaa_by_type: Optional[dict] = None


# --------------------------------------------------------------------------- #
# derived arsenal features
# --------------------------------------------------------------------------- #
FASTBALLS = {"FF", "SI", "FC", "FT"}


def n_pitches(arm: PalArm, min_usage: float = 0.10) -> int:
    return sum(1 for p in arm.arsenal if (_num(p.get("usage")) or 0) >= min_usage)


def fb_pct(arm: PalArm) -> Optional[float]:
    if not arm.arsenal:
        return None
    return sum((_num(p.get("usage")) or 0) for p in arm.arsenal if p.get("pitch") in FASTBALLS)


def top_pitch_share(arm: PalArm) -> float:
    if not arm.arsenal:
        return 0.0
    return max((_num(p.get("usage")) or 0) for p in arm.arsenal)


def overall_est_woba(arm: PalArm) -> Optional[float]:
    """Usage-weighted xwOBA across the arsenal (lower = better)."""
    num = den = 0.0
    for p in arm.arsenal:
        u = _num(p.get("usage"))
        w = _num(p.get("est_woba"))
        if u and w is not None:
            num += u * w
            den += u
    return (num / den) if den else None


def best_whiff(arm: PalArm) -> Optional[float]:
    ws = [_num(p.get("whiff")) for p in arm.arsenal if _num(p.get("whiff")) is not None]
    return max(ws) if ws else None


def overall_hard_hit(arm: PalArm) -> Optional[float]:
    num = den = 0.0
    for p in arm.arsenal:
        u = _num(p.get("usage"))
        h = _num(p.get("hard_hit"))
        if u and h is not None:
            num += u * h
            den += u
    return (num / den) if den else None


# --------------------------------------------------------------------------- #
# component scorers (each 0-100)
# --------------------------------------------------------------------------- #
def arsenal_depth_score(n: int) -> float:
    return {0: 0.0, 1: 12.0, 2: 45.0, 3: 80.0}.get(n, 100.0)


def command_score(bb_pct: Optional[float]) -> float:
    if bb_pct is None:
        return 50.0
    return _clamp(100.0 * (0.12 - bb_pct) / (0.12 - 0.05))


def fb_reliance_inv(fb: Optional[float]) -> float:
    if fb is None:
        return 50.0
    return _clamp(100.0 * (1.0 - _clamp((fb - 0.50) / 0.35, 0.0, 1.0)))


def stuff_quality_score(woba: Optional[float]) -> float:
    if woba is None:
        return 50.0
    return _clamp(100.0 * (0.400 - woba) / (0.400 - 0.280))


def putaway_score(whiff: Optional[float]) -> float:
    if whiff is None:
        return 40.0
    return _clamp(100.0 * (whiff - 0.08) / (0.35 - 0.08))


def survivability_score(hard_hit: Optional[float]) -> float:
    if hard_hit is None:
        return 50.0
    return _clamp(100.0 * (0.45 - hard_hit) / (0.45 - 0.30))


def platoon_neutrality_score(ops_vl: Optional[float], ops_vr: Optional[float]) -> Optional[float]:
    if ops_vl is None or ops_vr is None:
        return None
    return _clamp(100.0 * (1.0 - _clamp(abs(ops_vl - ops_vr) / 0.25, 0.0, 1.0)))


# --------------------------------------------------------------------------- #
# W3 PAL-XRV (docs/wills-2026-07-23/GATES.md section W3): per-pitch-type AAA
# aStuff+ blended into the stuff reads. Registered constants - never retuned.
# --------------------------------------------------------------------------- #
PAL_XRV_MIN_PITCHES = 100   # recent-AAA pitch floor (current or prior season)
PAL_XRV_W = 0.5             # registered 50/50 blend (est_woba read vs aStuff+)


def astuff_composite(by_type: Optional[dict]) -> Optional[float]:
    """Usage-weighted per-pitch-type aStuff+ composite on the 100+10z scale.
    Weights are the pitcher's OWN per-type AAA pitch counts (his actual usage
    mix at AAA), not the MLB arsenal usage. None without coverage."""
    if not by_type:
        return None
    num = den = 0.0
    for row in by_type.values():
        sp = _num((row or {}).get("stuff_plus"))
        n = _num((row or {}).get("n_pitches")) or 0.0
        if sp is None or n <= 0:
            continue
        num += n * sp
        den += n
    return (num / den) if den else None


def astuff_to_quality(composite: float) -> float:
    """Map the aStuff+ 100+10z scale onto the 0-100 stuff-quality band that
    stuff_quality_score emits (est_woba 0.400 -> 0, 0.280 -> 100, linear).
    Mapping: aStuff+ 100 (pool mean) -> 50 (band midpoint), 2.5 band points
    per aStuff+ point, so +-2z spans the full band (80 -> 0, 120 -> 100).
    An a-priori convention mapping - never retuned after seeing gate data."""
    return _clamp(50.0 + 2.5 * (composite - 100.0))


def stuff_read(arm: "PalArm") -> float:
    """The stuff read shared by BOTH fit scores (stuff_quality in RP->SP FIT,
    stuff_upside in SP->RP FIT): the incumbent arsenal est_woba read, blended
    PAL_XRV_W/(1-PAL_XRV_W) with the usage-weighted per-type aStuff+ composite
    when (and only when) the assembly layer attached AAA coverage to the arm.
    Arms without coverage take the incumbent path byte-identically (clause P3)."""
    base = stuff_quality_score(overall_est_woba(arm))
    comp = astuff_composite(getattr(arm, "aaa_by_type", None))
    if comp is None:
        return base
    return PAL_XRV_W * base + (1.0 - PAL_XRV_W) * astuff_to_quality(comp)


def _blend(weights: dict, comps: dict) -> float:
    """Weighted mean over the components that are present (renormalized)."""
    num = den = 0.0
    for k, w in weights.items():
        v = comps.get(k)
        if v is not None:
            num += w * v
            den += w
    return round(num / den, 1) if den else 0.0


# --------------------------------------------------------------------------- #
# velocity role projection (shape-interacting)
# --------------------------------------------------------------------------- #
def velo_delta(arm: PalArm, to_role: str) -> float:
    """Signed mph delta. Power / thin-arsenal arms move more (they gain most in
    relief, lose most stretching out); depth/command arms move near the base."""
    fb = fb_pct(arm) or 0.5
    npi = n_pitches(arm)
    shape = _clamp((fb - 0.5) / 0.4, 0.0, 1.0) * 0.6 + _clamp((3 - npi) / 3.0, 0.0, 1.0) * 0.4
    mag = min(MAX_VELO_DELTA, BASE_VELO_DELTA + shape * (MAX_VELO_DELTA - BASE_VELO_DELTA))
    return round(mag if to_role == "RP" else -mag, 1)


def project_velo(arm: PalArm, to_role: str) -> Optional[float]:
    if arm.fb_velo is None:
        return None
    return round(arm.fb_velo + velo_delta(arm, to_role), 1)


# --------------------------------------------------------------------------- #
# the two fit scores
# --------------------------------------------------------------------------- #
def _flags_rp_sp(arm: PalArm, npi: int, fb: Optional[float], plat: Optional[float]) -> list:
    flags = []
    if top_pitch_share(arm) >= 0.80:
        flags.append({"key": "relief_only", "label": "relief-only profile"})
    if npi < 3:
        flags.append({"key": "needs_third", "label": "needs a third pitch"})
    if fb is not None and fb >= 0.85:
        flags.append({"key": "fb_heavy", "label": "fastball-heavy"})
    if plat is not None and plat < 40:
        flags.append({"key": "platoon_risk", "label": "platoon risk"})
    return flags


PEDIGREE_NUDGE = 3.0   # "started before" = re-conversion ease (Baumann), capped + small


def rp_sp_fit(arm: PalArm) -> dict:
    npi = n_pitches(arm)
    fb = fb_pct(arm)
    plat = platoon_neutrality_score(arm.ops_vl, arm.ops_vr)
    comps = {
        "arsenal_depth": arsenal_depth_score(npi),
        "command": command_score(arm.bb_pct),
        "fb_reliance_inv": fb_reliance_inv(fb),
        "stuff_quality": stuff_read(arm),      # W3: aStuff+ blend when covered
        "platoon_neutrality": plat,
        "survivability": survivability_score(overall_hard_hit(arm)),
    }
    fit = _blend(RP_SP_WEIGHTS, comps)
    # starter pedigree: a reliever who has started before (in MLB or as a
    # prospect) re-converts more easily - a small, capped nudge + a chip.
    flags = _flags_rp_sp(arm, npi, fb, plat)
    if arm.was_starter:
        fit = min(100.0, fit + PEDIGREE_NUDGE)
        flags.append({"key": "started_before", "label": "started before"})
    elif arm.prospx_role == "SP":
        fit = min(100.0, fit + PEDIGREE_NUDGE)
        flags.append({"key": "prospect_sp", "label": "starter as a prospect"})
    return {
        "fit": round(fit, 1),
        "components": {k: (round(v, 1) if v is not None else None) for k, v in comps.items()},
        "n_pitches": npi,
        "fb_pct": None if fb is None else round(fb, 3),
        "proj_velo": project_velo(arm, "SP"),
        "reverse_platoon": reverse_platoon(arm),
        "flags": flags,
    }


# --------------------------------------------------------------------------- #
# T1-13 Lane B candidate: relief-usage stamina lane (game-log features)
# --------------------------------------------------------------------------- #
# A reliever whose org already uses him for multi-inning stints (>=4-out
# appearances) is structurally closer to a starter's workload than a max-effort
# back-to-back one-inning arm. multi_inning_share is the primary signal;
# b2b_rate (pitched the day after a previous appearance) is the negative
# complement. CANDIDATE weight 0.10 - gated in the T1-13 lab, NOT shipped.
RP_SP_WEIGHTS_V2 = {**RP_SP_WEIGHTS, "stamina_usage": 0.10}
STAMINA_MI_FULL = 0.50       # multi-inning share that saturates the lane
STAMINA_B2B_FULL = 0.40      # b2b rate that zeroes the (0.3-weight) sub-lane


def stamina_usage_score(multi_inning_share: Optional[float],
                        b2b_rate: Optional[float]) -> Optional[float]:
    """0-100 usage-stamina lane from the two game-log features. None (drops
    from the renormalized blend) when the relief sample was too thin to read."""
    if multi_inning_share is None:
        return None
    s_mi = _clamp(100.0 * multi_inning_share / STAMINA_MI_FULL)
    s_b2b = 50.0 if b2b_rate is None else _clamp(100.0 * (1.0 - b2b_rate / STAMINA_B2B_FULL))
    return 0.7 * s_mi + 0.3 * s_b2b


def rp_sp_fit_v2(arm: PalArm, usage: Optional[dict] = None) -> dict:
    """rp_sp_fit + the 0.10-weight stamina_usage lane (T1-13 Lane B candidate).
    `usage` is pal_gamelogs.relief_usage_features output (or None). With
    usage=None the lane drops from the renormalized blend, which is NOT the
    identity - use rp_sp_fit for the incumbent score."""
    npi = n_pitches(arm)
    fb = fb_pct(arm)
    plat = platoon_neutrality_score(arm.ops_vl, arm.ops_vr)
    usage = usage or {}
    comps = {
        "arsenal_depth": arsenal_depth_score(npi),
        "command": command_score(arm.bb_pct),
        "fb_reliance_inv": fb_reliance_inv(fb),
        "stuff_quality": stuff_read(arm),      # W3: aStuff+ blend when covered
        "platoon_neutrality": plat,
        "survivability": survivability_score(overall_hard_hit(arm)),
        "stamina_usage": stamina_usage_score(usage.get("multi_inning_share"),
                                             usage.get("b2b_rate")),
    }
    fit = _blend(RP_SP_WEIGHTS_V2, comps)
    flags = _flags_rp_sp(arm, npi, fb, plat)
    if arm.was_starter:
        fit = min(100.0, fit + PEDIGREE_NUDGE)
        flags.append({"key": "started_before", "label": "started before"})
    elif arm.prospx_role == "SP":
        fit = min(100.0, fit + PEDIGREE_NUDGE)
        flags.append({"key": "prospect_sp", "label": "starter as a prospect"})
    return {
        "fit": round(fit, 1),
        "components": {k: (round(v, 1) if v is not None else None) for k, v in comps.items()},
        "n_pitches": npi,
        "fb_pct": None if fb is None else round(fb, 3),
        "proj_velo": project_velo(arm, "SP"),
        "reverse_platoon": reverse_platoon(arm),
        "flags": flags,
    }


def reverse_platoon(arm: PalArm) -> Optional[dict]:
    """Platoon split WITH direction. Conventionally a pitcher is tougher on
    same-handed hitters; a REVERSE split (tougher on the opposite hand) is a rare
    hidden strength that supports facing a full lineup, and an extreme normal
    split is a conversion blocker. Needs the throwing hand + vs-L/R OPS."""
    if arm.ops_vl is None or arm.ops_vr is None or not arm.p_throws:
        return None
    if arm.p_throws == "R":
        own, opp = arm.ops_vr, arm.ops_vl        # RHP own-side = RHB
    else:
        own, opp = arm.ops_vl, arm.ops_vr        # LHP own-side = LHB
    idx = round(own - opp, 3)                     # > 0 => reverse (own-side is tougher)
    split = round(abs(arm.ops_vl - arm.ops_vr), 3)
    return {
        "p_throws": arm.p_throws, "own_ops": round(own, 3), "opp_ops": round(opp, 3),
        "reverse_index": idx, "reverse": idx > 0.030, "split": split,
        "extreme": split >= 0.150,
        "weak_hand": "RHB" if arm.ops_vr > arm.ops_vl else "LHB",
    }


# --------------------------------------------------------------------------- #
# prospect conversion watch (shape-only; no Statcast physics at the minors)
# --------------------------------------------------------------------------- #
PROSPECT_TOOL_KEYS = ("fb", "sl", "cb", "ch", "ct")

# The SWING band on starter_shape: at or above SHAPE_SP_MIN the shape reads as a
# starter, below SHAPE_RP_MAX as a reliever, and between them as a swing. Named
# (they were inline literals) because the /pal/ watch now stages on the DISTANCE
# past these boundaries, so the band width is load-bearing rather than cosmetic.
SHAPE_SP_MIN = 60.0
SHAPE_RP_MAX = 40.0
SHAPE_SWING_BAND = SHAPE_SP_MIN - SHAPE_RP_MAX      # 20.0


def prospect_role_fit(tools: dict, position: Optional[str]) -> dict:
    """A SHAPE-ONLY role lean for a prospect pitcher from 20-80 scout tool grades
    (no MiLB tracking, so no stuff physics). Flags starter-labeled prospects who
    profile as relievers (thin arsenal / poor command) and reliever-labeled
    prospects who could start (deep arsenal + command).

    `mismatch` stays a plain BOOL (three test files and the prospx chip read it by
    identity / truthiness). The new `mismatch_margin` carries the SEVERITY: how far
    past its lean boundary the shape sits, in shape points, or None when there is no
    mismatch. It is the only continuous quantity this shape-only read produces, so it
    is what the /pal/ watch ranks and stages on. Note it is heavily QUANTIZED: the
    arsenal-depth term is a four-value step table, so the whole pool carries only
    about two dozen distinct shapes and a threshold moves rows in clumps.
    """
    tools = tools or {}
    grades = [tools.get(k) for k in PROSPECT_TOOL_KEYS if tools.get(k) is not None]
    depth = sum(1 for g in grades if g is not None and g >= 55)   # above-average pitches
    cmd = tools.get("cmd")
    depth_s = {0: 5.0, 1: 15.0, 2: 45.0, 3: 80.0}.get(depth, 100.0)
    cmd_s = 50.0 if cmd is None else _clamp((cmd - 40.0) / (60.0 - 40.0) * 100.0)
    starter_shape = round(0.60 * depth_s + 0.40 * cmd_s, 1)
    pos = (position or "").upper()
    # "NO ROLE STATED" IS NOT "SWINGMAN". A position of RHP, LHP or P states
    # HANDEDNESS and no role at all, and it covers 691 of the 1,875 pool
    # pitchers (36.9%). Those rows used to be filed as SWING beside genuine
    # swingmen, which made a missing input look like a scouting read.
    #
    # Both still fail the `mismatch` predicate below and both always did, so no
    # served row moves: with no stated role there is nothing for the shape to
    # DISAGREE with, and excluding them from a mismatch list is correct. What
    # was wrong was calling the exclusion a role. It is counted and disclosed
    # instead, in pal_export.prospect_watch_rule.
    if "SP" in pos:
        role = "SP"
    elif "RP" in pos or "CL" in pos:
        role = "RP"
    elif "SWING" in pos or "SWG" in pos:
        role = "SWING"
    else:
        role = "UNSTATED"
    lean = ("SP" if starter_shape >= SHAPE_SP_MIN
            else ("RP" if starter_shape < SHAPE_RP_MAX else "SWING"))
    mismatch = role in ("SP", "RP") and lean in ("SP", "RP") and role != lean
    if not mismatch:
        margin = None
    elif lean == "RP":
        margin = round(SHAPE_RP_MAX - starter_shape, 1)
    else:
        margin = round(starter_shape - SHAPE_SP_MIN, 1)
    return {
        "starter_shape": starter_shape, "arsenal_depth": depth, "cmd": cmd,
        "role": role, "lean": lean,
        "mismatch": mismatch,
        "mismatch_margin": margin,
    }


LG_SP_ERA = 4.20            # league-ish starter ERA: the need-gate shrink target
# ERA regresses toward LG_SP_ERA with NEED_ERA_SHRINK_IP pseudo-count of IP
# (imported from rate_stabilization, which holds the provenance).


def starter_need_score(era: Optional[float], ip: Optional[float] = None) -> float:
    """How much a STARTER needs to move to relief, from his rotation results. A
    dominant starter (low ERA) scores ~0 (no conversion case); a struggling one
    (high ERA) scores ~100. This is what keeps successful starters OFF the SP->RP
    board no matter how nasty their stuff is.

    Raw ERA is the slowest-stabilizing pitching stat, so it is shrunk toward a
    league-average starter ERA by innings (empirical Bayes). Without this a small
    sample unlucky ace (e.g. 30-40 rocky innings on a high BABIP) scored ~100 need
    and surfaced near the top of the demotion board - the exact noise the gate is
    meant to reject. A full-season struggler still scores high; a 30-IP blip does
    not."""
    if era is None:
        return 50.0
    if ip and ip > 0:
        era = (ip * era + NEED_ERA_SHRINK_IP * LG_SP_ERA) / (ip + NEED_ERA_SHRINK_IP)
    return _clamp(100.0 * (era - 3.20) / (5.50 - 3.20))


def _flags_sp_rp(arm: PalArm, npi: int, need: float) -> list:
    flags = []
    bw = best_whiff(arm)
    if bw is not None and bw >= 0.30:
        flags.append({"key": "putaway", "label": "late-inning weapon"})
    if need < 30:
        flags.append({"key": "succeeding_sp", "label": "succeeding as a starter"})
    elif need >= 70:
        flags.append({"key": "struggling_sp", "label": "struggling as a starter"})
    if npi >= 4 and command_score(arm.bb_pct) >= 70:
        flags.append({"key": "keep_starting", "label": "deep arsenal, keep starting"})
    return flags


def sp_rp_fit(arm: PalArm) -> dict:
    """Relief upside GATED by conversion need. A starter only belongs on this
    board if his stuff would play up in relief AND he is not locking down a
    rotation spot - so a great starter scores low even with elite stuff."""
    npi = n_pitches(arm)
    upside_comps = {
        "stuff_upside": stuff_read(arm),       # W3: aStuff+ blend when covered
        "putaway": putaway_score(best_whiff(arm)),
        "velo_leverage": _clamp(((arm.fb_velo or 93.0) - 90.0) / (101.0 - 90.0) * 100.0),
        "tto_leakage": _clamp(100.0 - 0.7 * arsenal_depth_score(npi)
                              - 0.3 * fb_reliance_inv(fb_pct(arm))),
    }
    upside = _blend(SP_RP_UPSIDE_WEIGHTS, upside_comps)
    need = starter_need_score(arm.era, arm.ip)
    factor = 0.30 + 0.70 * (need / 100.0)   # dominant SP -> 0.30x, struggling SP -> 1.0x
    comps = {k: round(v, 1) for k, v in upside_comps.items()}
    comps["conversion_need"] = round(need, 1)
    return {
        "fit": round(upside * factor, 1),
        "relief_upside": round(upside, 1),
        "starter_era": None if arm.era is None else round(arm.era, 2),
        "components": comps,
        "n_pitches": npi,
        "proj_velo": project_velo(arm, "RP"),
        "best_whiff": None if best_whiff(arm) is None else round(best_whiff(arm), 3),
        "flags": _flags_sp_rp(arm, npi, need),
    }


# --------------------------------------------------------------------------- #
# REM+ relief projection (DISPLAY ONLY - never a scored input)
# --------------------------------------------------------------------------- #
def project_relief_rem_plus(arm: PalArm, pool, k_bump: float = DEFAULT_RELIEF_K_BUMP):
    """If this starter's rates held up (plus the measured relief K% bump) in a
    one-inning role, roughly what REM+ would he post? Scored against the REAL
    reliever pool by calling rem_plus directly (bypassing score_pool's reliever
    filter). Uses the pitcher's ACTUAL TBF (no relief-TBF fiction). Display only,
    with the assumption shown - it launders nothing into the fit score."""
    import rem_plus
    if arm.tbf <= 0 or arm.ip <= 0 or arm.k_pct is None:
        return None
    k = min(0.60, (arm.k_pct or 0) + k_bump)
    bb = max(0.0, (arm.bb_pct or 0) - 0.005)   # tiny command gain in short stints
    conv = rem_plus.Reliever(
        key=str(arm.mlbam), gs=0, ip=arm.ip, tbf=arm.tbf,
        so=k * arm.tbf, bb=bb * arm.tbf,
        hbp=0.01 * arm.tbf, hr=_hr_from_arm(arm), er=0.0, r=0.0)
    rem_plus.derive_rates(conv)
    return rem_plus.rem_plus(conv, pool)


def _hr_from_arm(arm: PalArm) -> float:
    # rough HR count from a league-ish HR rate on TBF (rate cancels in shrinkage anchor)
    return 0.028 * arm.tbf


# --------------------------------------------------------------------------- #
# conversion detection + labeling (from season rows)
# --------------------------------------------------------------------------- #
def role_of(g, gs, ip) -> Optional[str]:
    g = _num(g) or 0
    gs = _num(gs) or 0
    ip = _num(ip) or 0
    if g <= 0 or ip <= 0:
        return None
    share = gs / g
    if share >= SP_GS_SHARE and (ip / g) >= SP_IP_PER_G:
        return "SP"
    if share <= RP_GS_SHARE:
        return "RP"
    return "SWING"


def detect_conversions(by_pid: dict, last_closed_season: Optional[int] = None) -> list:
    """by_pid: {mlbam: {season: row}} where row has G/GS/IP + name/team + rates.
    Returns conversion events (RP->SP / SP->RP) between consecutive qualified
    seasons, with the pre/post rows and a 'held' flag (did the new role stick the
    following season?).

    Label hygiene (T1-6 backtest repair):
      - `last_closed_season`: when given, a held label is only read from a
        COMPLETED b+1 season (an in-progress season's cumulative GS-share is
        not a settled role read, so e.g. 2025 events stay held=None until 2026
        closes). None keeps the legacy behavior for callers without a clock.
      - IP gate: a b+1 season under CONV_MIN_IP cannot certify "held the new
        role a full season" -> held stays None (too thin to judge, and a
        1-appearance cameo is not evidence either way)."""
    events = []
    for pid, byyr in by_pid.items():
        yrs = sorted(byyr)
        for i in range(len(yrs) - 1):
            a, b = yrs[i], yrs[i + 1]
            if b - a > 2:
                continue
            ra = role_of(byyr[a].get("G"), byyr[a].get("GS"), byyr[a].get("IP"))
            rb = role_of(byyr[b].get("G"), byyr[b].get("GS"), byyr[b].get("IP"))
            if not ra or not rb or ra == rb:
                continue
            if ra == "SWING" or rb == "SWING":
                continue
            import bullpen_export as be
            ipa = be.ip_to_float(byyr[a].get("IP"))
            ipb = be.ip_to_float(byyr[b].get("IP"))
            if ipa < CONV_MIN_IP or ipb < CONV_MIN_IP:
                continue
            # held the new role the following season? (closed seasons with a
            # real sample only - see the docstring)
            held = None
            nxt = b + 1
            if (nxt in byyr
                    and (last_closed_season is None or nxt <= last_closed_season)
                    and be.ip_to_float(byyr[nxt].get("IP")) >= CONV_MIN_IP):
                rn = role_of(byyr[nxt].get("G"), byyr[nxt].get("GS"), byyr[nxt].get("IP"))
                held = (rn == rb) if rn else None
            events.append({
                "mlbam": pid, "name": byyr[b].get("name", ""), "team": byyr[b].get("team", ""),
                "direction": f"{ra}->{rb}", "year": b,
                "pre": _role_line(byyr[a]), "post": _role_line(byyr[b]),
                "held": held,
            })
    return events


# In-progress (current-season) conversion detection thresholds. A mid-year switch
# dilutes the season's cumulative GS-share / IP-per-G, so role_of reads SWING and
# detect_conversions drops the pair (both sides must be a clean SP/RP). These
# gates surface the switch anyway, as an always-PENDING event.
IN_PROGRESS_MIN_GS = 5          # current-season starts to call an RP->SP in progress
IN_PROGRESS_MIN_IP_PER_G = 2.5  # innings per APPEARANCE gate: openers/multi-inning RPs sit <= ~1.2 IP/G, genuine RP->SP converts >= ~3.0
IN_PROGRESS_MIN_RELIEF = 0.50   # current-season relief-appearance share for SP->RP


def detect_in_progress_conversions(by_pid: dict, current_season: int) -> list:
    """Surface a CURRENT-SEASON role conversion that season-cumulative role_of
    misses because a mid-year switch dilutes the year's GS-share and IP-per-G
    (e.g. a reliever who becomes a starter in June reads as SWING for the whole
    year, so detect_conversions never emits the flip). These events are always
    PENDING (held=None): the following season is unobserved. Kept SEPARATE from
    detect_conversions so the historical backtest set stays byte-identical.

    Griffin Jax (2025 RP, 2026 G23/GS12/IP60 -> SWING) is the motivating case."""
    import bullpen_export as be
    events = []
    for pid, byyr in by_pid.items():
        cur = byyr.get(current_season)
        if not cur:
            continue
        ip_cur = be.ip_to_float(cur.get("IP"))
        if ip_cur < CONV_MIN_IP:
            continue
        # Only ambiguous (SWING) current seasons are interesting - a clean current
        # SP/RP is already handled by detect_conversions.
        if role_of(cur.get("G"), cur.get("GS"), cur.get("IP")) != "SWING":
            continue
        g_cur = _num(cur.get("G")) or 0
        gs_cur = _num(cur.get("GS")) or 0
        # Most recent prior season (within 2 years) with a real sample + clear role.
        prior_role = prior_year = None
        for py in sorted((y for y in byyr if y < current_season), reverse=True):
            if current_season - py > 2:
                break
            if be.ip_to_float(byyr[py].get("IP")) < CONV_MIN_IP:
                continue
            r = role_of(byyr[py].get("G"), byyr[py].get("GS"), byyr[py].get("IP"))
            if r in ("SP", "RP"):
                prior_role, prior_year = r, py
                break
        if prior_role is None:
            continue
        relief_share = (g_cur - gs_cur) / g_cur if g_cur else 0.0
        direction = None
        if (prior_role == "RP" and gs_cur >= IN_PROGRESS_MIN_GS
                and g_cur > 0 and (ip_cur / g_cur) >= IN_PROGRESS_MIN_IP_PER_G):
            direction = "RP->SP"
        elif prior_role == "SP" and gs_cur < g_cur and relief_share >= IN_PROGRESS_MIN_RELIEF:
            direction = "SP->RP"
        if not direction:
            continue
        events.append({
            "mlbam": pid, "name": cur.get("name", ""), "team": cur.get("team", ""),
            "direction": direction, "year": current_season,
            "pre": _role_line(byyr[prior_year]), "post": _role_line(cur),
            "held": None, "in_progress": True,
        })
    return events


def _role_line(row: dict) -> dict:
    import bullpen_export as be
    ip = be.ip_to_float(row.get("IP"))
    tbf = _num(row.get("BF")) or 0
    so = _num(row.get("SO")) or 0
    bb = _num(row.get("BB")) or 0
    er = _num(row.get("ER")) or 0
    return {
        "season": row.get("season"),
        "g": int(_num(row.get("G")) or 0), "gs": int(_num(row.get("GS")) or 0),
        "ip": round(ip, 1),
        "k_pct": round(so / tbf, 4) if tbf else None,
        "bb_pct": round(bb / tbf, 4) if tbf else None,
        "era": round(er * 9.0 / ip, 2) if ip else None,
    }


def role_success(arm: PalArm) -> Optional[bool]:
    """Is this pitcher SUCCEEDING in his CURRENT role, from a real sample of his
    own results (ERA + K-BB)? Used only to TIER conversion candidates for display:
    a successful reliever who profiles as a starter is the premium RP->SP case (a
    starter is worth more than a reliever), while the SP->RP board is already
    gated on conversion NEED. None when the sample is too thin to judge."""
    if arm.ip is None or arm.ip < CONV_MIN_IP or arm.era is None:
        return None
    kbb = (arm.k_pct - arm.bb_pct) if (arm.k_pct is not None and arm.bb_pct is not None) else None
    if arm.role == "RP":
        return arm.era <= 3.50 and (kbb is None or kbb >= 0.12)
    if arm.role == "SP":
        return arm.era <= 3.90 and (kbb is None or kbb >= 0.10)
    return None


def label_success(ev: dict) -> Optional[bool]:
    """Primary label = held the new role >=1 full season (objective, not a
    tunable role-adjusted tax). A revert within a year is a soft-fail. None when
    the following season is not yet observed."""
    return ev.get("held")


# --------------------------------------------------------------------------- #
# pitch-add recommender: what weapon should this arm add to start?
# --------------------------------------------------------------------------- #
BREAKING = {"SL", "CU", "ST", "SV", "KC", "SC", "CS"}
OFFSPEED = {"CH", "FS", "FO"}


def _families(arm: PalArm, min_usage: float = 0.05) -> set:
    fams = set()
    for p in arm.arsenal:
        if (_num(p.get("usage")) or 0) < min_usage:
            continue
        t = p.get("pitch")
        if t in FASTBALLS:
            fams.add("FB")
        elif t in BREAKING:
            fams.add("BR")
        elif t in OFFSPEED:
            fams.add("OFF")
    return fams


# W3 ARM-2 (display upgrade): rank the family-hole adds by LEAGUE-MEAN per-type
# xRV (meta.league_xrv_by_type in data/stuff_plus_aaa.json; mean predicted
# delta_run_exp, LOWER = better for the pitcher) instead of the fixed
# BR-before-OFF rule order. Candidate types per family are an a-priori list of
# learnable pitches; a league mean is only trusted at >= XRV_MIN_LEAGUE_N
# pitches. Output shape/keys are UNCHANGED (same {add, target, reason,
# priority} objects, better ordering); league_xrv=None reproduces the
# incumbent rule order byte-identically (the default-OFF path).
XRV_PITCH_NAMES = {"SL": "Slider", "ST": "Sweeper", "CU": "Curveball",
                   "KC": "Knuckle-curve", "CH": "Changeup", "FS": "Splitter"}
XRV_FAMILY_CANDIDATES = {"BR": ("SL", "ST", "CU", "KC"), "OFF": ("CH", "FS")}
XRV_MIN_LEAGUE_N = 500


def _best_xrv_type(fam: str, league_xrv: dict):
    """(pitch_type, mean_pred_rv) of the family's best league-mean type, or
    None when no candidate type has a trusted league mean."""
    best = None
    for pt in XRV_FAMILY_CANDIDATES.get(fam, ()):
        row = league_xrv.get(pt) or {}
        rv = _num(row.get("mean_pred_rv"))
        if rv is None or (_num(row.get("n_pitches")) or 0) < XRV_MIN_LEAGUE_N:
            continue
        if best is None or rv < best[1]:          # lower RV = better pitch
            best = (pt, rv)
    return best


def _hole_rec(fam: str, pitch_name: str, weak_hand, big_split: bool) -> dict:
    """The family-hole recommendation object (same shape as the fixed rules)."""
    low = pitch_name.lower()
    if fam == "BR":
        return {"add": pitch_name, "target": weak_hand,
                "reason": f"No reliable breaking ball. A {low} is the swing-and-miss weapon he needs to "
                          "turn a lineup over a second and third time.", "priority": "high"}
    tail = (f" and neutralize {weak_hand}" if big_split else "")
    return {"add": pitch_name, "target": weak_hand,
            "reason": f"No offspeed pitch. A {low} would give him a third look{tail} - the classic "
                      "weapon against opposite-handed hitters over multiple times through.",
            "priority": "high" if big_split else "medium"}


# Candidates for the deep-arsenal platoon branch, in preference order, paired with
# the Statcast pitch code that means "he already throws this". The first entry of
# each pair is the incumbent recommendation, so a pitcher who throws neither is
# advised exactly as before; the second is the same-family alternative for one who
# already throws the first. USAGE FLOOR matches _families, so "already throws it"
# means the same thing here as it does everywhere else in this module.
PITCH_ADD_MIN_USAGE = 0.05
PLATOON_ADD_CANDIDATES = {
    "RHB": (("Changeup", "CH"), ("Splitter", "FS")),
    "LHB": (("Cutter", "FC"), ("Slider", "SL")),
}


def recommend_pitch(arm: PalArm, league_xrv: Optional[dict] = None) -> Optional[dict]:
    """The pitch this arm most needs to add to survive a lineup as a starter,
    from its arsenal hole and platoon weakness. A rule model (the empty-slot x
    platoon-hole lookup), not a projection - returns None when the arsenal is
    already deep enough. With `league_xrv` (W3 ARM-2, meta.league_xrv_by_type
    from the AAA aStuff+ sidecar) the family holes are ranked by league-mean
    per-type xRV instead of the fixed BR-then-OFF order; without it the
    incumbent rule order runs unchanged."""
    fams = _families(arm)
    npi = n_pitches(arm)
    # which hand does he struggle against, and how badly (OPS-against gap)?
    weak_hand, split = None, None
    if arm.ops_vl is not None and arm.ops_vr is not None:
        split = round(abs(arm.ops_vl - arm.ops_vr), 3)
        weak_hand = "RHB" if arm.ops_vr > arm.ops_vl else "LHB"
    big_split = split is not None and split >= 0.12

    holes = [f for f in ("BR", "OFF") if f not in fams]
    if holes and league_xrv:
        ranked = []
        for fam in holes:
            best = _best_xrv_type(fam, league_xrv)
            if best is not None:
                ranked.append((best[1], fam, XRV_PITCH_NAMES[best[0]]))
        if ranked:
            ranked.sort()                         # lowest mean RV first = best add
            _rv, fam, name = ranked[0]
            return _hole_rec(fam, name, weak_hand, big_split)
        # no trusted league mean for any hole -> fall through to the rule order
    if "BR" not in fams:
        return {"add": "Slider", "target": weak_hand,
                "reason": "No reliable breaking ball. A slider is the swing-and-miss weapon he needs to "
                          "turn a lineup over a second and third time.", "priority": "high"}
    if "OFF" not in fams:
        tail = (f" and neutralize {weak_hand}" if big_split else "")
        return {"add": "Changeup", "target": weak_hand,
                "reason": f"No offspeed pitch. A changeup would give him a third look{tail} - the classic "
                          "weapon against opposite-handed hitters over multiple times through.",
                "priority": "high" if big_split else "medium"}
    if npi < 3:
        return {"add": "A genuine third pitch", "target": None,
                "reason": "Only two pitches used 10 percent or more. He has the pitch types but needs to "
                          "trust a third often enough to keep hitters honest across a full lineup.",
                "priority": "medium"}
    if big_split:
        # DO NOT TELL HIM TO ADD A PITCH HE ALREADY THROWS. Every branch above
        # this one fires on a family HOLE, so what it names is necessarily
        # absent. This branch is reached precisely when the arsenal is DEEP
        # (both families present) and it used to pick from the weak hand alone,
        # without ever consulting the arsenal. Measured on the live payload: 22
        # of 236 pitch_add rows recommended a pitch the arm was already throwing
        # at 5% usage or more, including Brooks Raley, told to add a changeup he
        # throws 10% of the time.
        #
        # The second candidate is the same family as the first, so the advice
        # keeps its shape: an offspeed pitch to blunt opposite-handed contact, or
        # a glove-side pitch to hold the other corner. If he throws both, this
        # rule model has nothing left to point at and says so by returning None,
        # which is what the docstring already promises for a deep arsenal.
        have = {p.get("pitch") for p in arm.arsenal
                if (_num(p.get("usage")) or 0) >= PITCH_ADD_MIN_USAGE}
        for want, code in (PLATOON_ADD_CANDIDATES.get(weak_hand) or ()):
            if code not in have:
                return {"add": want, "target": weak_hand,
                        "reason": f"Deep arsenal, but a large platoon split leaves him exposed to {weak_hand}. "
                                  f"A {want.lower()} would flatten the split a starter has to survive.",
                        "priority": "medium"}
    return None
