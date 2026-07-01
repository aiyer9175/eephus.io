# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pitcher Alchemy Lab - the role-conversion model core (pure, no network).

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
        "stuff_quality": stuff_quality_score(overall_est_woba(arm)),
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


def prospect_role_fit(tools: dict, position: Optional[str]) -> dict:
    """A SHAPE-ONLY role lean for a prospect pitcher from 20-80 scout tool grades
    (no MiLB tracking, so no stuff physics). Flags starter-labeled prospects who
    profile as relievers (thin arsenal / poor command) and reliever-labeled
    prospects who could start (deep arsenal + command)."""
    tools = tools or {}
    grades = [tools.get(k) for k in PROSPECT_TOOL_KEYS if tools.get(k) is not None]
    depth = sum(1 for g in grades if g is not None and g >= 55)   # above-average pitches
    cmd = tools.get("cmd")
    depth_s = {0: 5.0, 1: 15.0, 2: 45.0, 3: 80.0}.get(depth, 100.0)
    cmd_s = 50.0 if cmd is None else _clamp((cmd - 40.0) / (60.0 - 40.0) * 100.0)
    starter_shape = round(0.60 * depth_s + 0.40 * cmd_s, 1)
    pos = (position or "").upper()
    role = "SP" if "SP" in pos else ("RP" if ("RP" in pos or "IRP" in pos or "CL" in pos) else "SWING")
    lean = "SP" if starter_shape >= 60 else ("RP" if starter_shape < 40 else "SWING")
    return {
        "starter_shape": starter_shape, "arsenal_depth": depth, "cmd": cmd,
        "role": role, "lean": lean,
        "mismatch": (role in ("SP", "RP") and lean in ("SP", "RP") and role != lean),
    }


def starter_need_score(era: Optional[float]) -> float:
    """How much a STARTER needs to move to relief, from his rotation results. A
    dominant starter (low ERA) scores ~0 (no conversion case); a struggling one
    (high ERA) scores ~100. This is what keeps successful starters like a good
    young rotation arm OFF the SP->RP board no matter how nasty their stuff is."""
    if era is None:
        return 50.0
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
        "stuff_upside": stuff_quality_score(overall_est_woba(arm)),
        "putaway": putaway_score(best_whiff(arm)),
        "velo_leverage": _clamp(((arm.fb_velo or 93.0) - 90.0) / (101.0 - 90.0) * 100.0),
        "tto_leakage": _clamp(100.0 - 0.7 * arsenal_depth_score(npi)
                              - 0.3 * fb_reliance_inv(fb_pct(arm))),
    }
    upside = _blend(SP_RP_UPSIDE_WEIGHTS, upside_comps)
    need = starter_need_score(arm.era)
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


def detect_conversions(by_pid: dict) -> list:
    """by_pid: {mlbam: {season: row}} where row has G/GS/IP + name/team + rates.
    Returns conversion events (RP->SP / SP->RP) between consecutive qualified
    seasons, with the pre/post rows and a 'held' flag (did the new role stick the
    following season?)."""
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
            # held the new role the following season?
            held = None
            nxt = b + 1
            if nxt in byyr:
                rn = role_of(byyr[nxt].get("G"), byyr[nxt].get("GS"), byyr[nxt].get("IP"))
                held = (rn == rb) if rn else None
            events.append({
                "mlbam": pid, "name": byyr[b].get("name", ""), "team": byyr[b].get("team", ""),
                "direction": f"{ra}->{rb}", "year": b,
                "pre": _role_line(byyr[a]), "post": _role_line(byyr[b]),
                "held": held,
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


def recommend_pitch(arm: PalArm) -> Optional[dict]:
    """The pitch this arm most needs to add to survive a lineup as a starter,
    from its arsenal hole and platoon weakness. A rule model (the empty-slot x
    platoon-hole lookup), not a projection - returns None when the arsenal is
    already deep enough."""
    fams = _families(arm)
    npi = n_pitches(arm)
    # which hand does he struggle against, and how badly (OPS-against gap)?
    weak_hand, split = None, None
    if arm.ops_vl is not None and arm.ops_vr is not None:
        split = round(abs(arm.ops_vl - arm.ops_vr), 3)
        weak_hand = "RHB" if arm.ops_vr > arm.ops_vl else "LHB"
    big_split = split is not None and split >= 0.12

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
        want = "Changeup" if weak_hand == "RHB" else "Cutter"
        return {"add": want, "target": weak_hand,
                "reason": f"Deep arsenal, but a large platoon split leaves him exposed to {weak_hand}. "
                          f"A {want.lower()} would flatten the split a starter has to survive.",
                "priority": "medium"}
    return None
