# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pitch economy: the arithmetic of the eWAR v3 candidate parts PE-P and PE-H. Pure.

Registered in docs/ebr-2026-09-30/EBR_GATE.md part 11.3 (owner decisions EW3-19 and
EW3-23) and docs/ewar/PITCH_ECONOMY_LAB.md, both committed before any number.

PE-P (pitchers, gate 11.3.2). Per role r in {SP, RP} the pitcher's pitches per out and
pitches per appearance are shrunk toward the season's pooled role values with the
starter-workload model's frozen priors (K_O 120 outs, K_B 2 appearances, taken by
reference from data/starter_workload_eval.json burn_in.priors), the efficiency-implied
outs X~ = n * min(27, b~ / ppo~) replace the outs he recorded (skill arm minus actual
arm), and the difference is priced per out against the league bullpen, with the
times-through-order decay T9 = 27 * pi * DELTA_TTO for starters. Re-centred to zero per
season and role, per out.

PE-H (hitters, gate 11.3.3). Two residuals against the league mean of each plate
appearance's terminal class: the count lift (the RE288 value a hitter gains on his
non-terminal pitches) and the pitches he makes the opposing starter throw, the second
priced as starter wear w = (F_RP - F_SP - T9) / (27 * L_ppo_SP) runs per pitch. Each is
shrunk by n / (n + K) with K_CL and K_P from a split-half fit on the 2018 and 2019
corpus seasons (lab part 7), and the sum is re-centred per PA over every hitting row.

Nothing here reads a file, a network or a next-season quantity. The frozen constants
below were fitted once by the lab (lab part 7) on the 2018 and 2019 corpus seasons; every
function that needs one takes it as an argument, so the lab ran before they were frozen.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping, Optional, Sequence

PITCH_ECONOMY_VERSION = "pitch_economy_v1"
GATE_DOC = "docs/ebr-2026-09-30/EBR_GATE.md"
LAB_DOC = "docs/ewar/PITCH_ECONOMY_LAB.md"

#: The starter-workload model's frozen priors (data/starter_workload_eval.json,
#: stage1.burn_in.priors k_o and k_b), by reference; gate 11.3.2.
K_O = 120.0
K_B = 2.0
OUTS_CAP = 27.0

#: S2's shrink constants (rem_plus K_STRIKEOUT, K_WALK, K_HBP, K_HOMERUN), by reference.
S2_K = {"k": 70.0, "bb": 170.0, "hbp": 170.0, "hr": 400.0}
FIP_W = {"hr": 13.0, "bbhbp": 3.0, "k": 2.0}

#: Role thresholds of the SEM+ and REM+ pools (sem_plus.MIN_START_SHARE,
#: rem_plus.MAX_START_SHARE) and their contribution floors.
SP_MIN_START_SHARE = 0.50
RP_MAX_START_SHARE = 0.10
SEM_POOL_MIN_IP = 20.0
REM_POOL_MIN_TBF = 50.0

#: Lab part 7: the split-half K clamp and the fit seasons.
K_CLAMP = (50.0, 20000.0)
FIT_SEASONS = (2018, 2019)

#: Frozen by the lab's corrected run of 2026-10-15 (lab part 7 and part 10; the log is
#: data/_labs/pitch_economy_constants.json). delta_TTO in runs per plate appearance
#: (384 starter-seasons, 47,079 plate appearances at the third and later pass); K_CL
#: in plate appearances (rho_half 0.484356 on 714 hitter-seasons, nbar 444.12); K_P in
#: plate appearances against starters (rho_half 0.561812 on 607, nbar 284.51). The
#: eWAR v3 skill look reads these and refits nothing (EBR_GATE.md 11.3.6).
DELTA_TTO: Optional[float] = 0.01847965
K_CL: Optional[float] = 236.41
K_P: Optional[float] = 110.95

#: Terminal classes of a plate appearance (gate 11.3.3).
CLASSES = ("walk", "hbp", "strikeout", "single", "double", "triple", "home_run",
           "out_in_play", "other")
_CLASS_OF = {
    "walk": "walk",
    "hit_by_pitch": "hbp",
    "strikeout": "strikeout", "strikeout_double_play": "strikeout",
    "single": "single", "double": "double", "triple": "triple", "home_run": "home_run",
    "field_out": "out_in_play", "force_out": "out_in_play",
    "grounded_into_double_play": "out_in_play", "double_play": "out_in_play",
    "triple_play": "out_in_play", "sac_fly": "out_in_play", "sac_bunt": "out_in_play",
    "sac_fly_double_play": "out_in_play", "sac_bunt_double_play": "out_in_play",
    "fielders_choice": "out_in_play", "fielders_choice_out": "out_in_play",
}


def terminal_class(event_type) -> Optional[str]:
    """The class of a plate appearance's terminal event; None for an intentional walk
    (excluded from PE-H) and 'other' for anything else that ends a plate appearance
    (a reach on error, catcher's interference)."""
    e = "" if event_type is None else str(event_type)
    if e == "intent_walk":
        return None
    return _CLASS_OF.get(e, "other")


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def _f(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def fip9(hr: float, bb: float, hbp: float, k: float, ip: float, cfip: float) -> Optional[float]:
    """FIP per nine on the season constant: (13 HR + 3 (BB + HBP) - 2 K) / IP + cFIP."""
    if not ip or ip <= 0:
        return None
    return (FIP_W["hr"] * hr + FIP_W["bbhbp"] * (bb + hbp) - FIP_W["k"] * k) / ip + cfip


def shrink(count: float, n: float, k: float, mean: float) -> float:
    """(count + k * mean) / (n + k): a rate shrunk toward mean with k pseudo-units."""
    return (float(count) + k * float(mean)) / (float(n) + k)


def recentre(values: Mapping, exposure: Mapping, groups: Mapping | None = None) -> dict:
    """value_i - exposure_i * (sum of values) / (sum of exposure), within each group.

    The zero-sum rule of gate part 9.4 rule 3 (and 11.3.2, 11.3.3): a group whose
    exposure sums to 0 is returned unchanged (nothing to spread over)."""
    groups = groups or {k: 0 for k in values}
    tot_v: dict = {}
    tot_e: dict = {}
    for key, v in values.items():
        g = groups[key]
        tot_v[g] = tot_v.get(g, 0.0) + float(v)
        tot_e[g] = tot_e.get(g, 0.0) + float(exposure.get(key, 0.0) or 0.0)
    out = {}
    for key, v in values.items():
        g = groups[key]
        e = float(exposure.get(key, 0.0) or 0.0)
        out[key] = float(v) - (e * tot_v[g] / tot_e[g] if tot_e[g] else 0.0)
    return out


# --------------------------------------------------------------------------
# PE-P
# --------------------------------------------------------------------------
def implied_outs(n: float, pitches: float, outs: float, l_ppo: float, l_pa: float,
                 k_o: float = K_O, k_b: float = K_B) -> float:
    """X~ = n * min(27, b~ / ppo~): the efficiency-implied outs of one role line."""
    if not n or n <= 0:
        return 0.0
    ppo = shrink(pitches, outs, k_o, l_ppo)
    b = shrink(pitches, n, k_b, l_pa)
    if ppo <= 0:
        return 0.0
    return float(n) * min(OUTS_CAP, b / ppo)


def t9(pi: float, delta_tto: float) -> float:
    """The times-through-order decay in runs per nine: 27 * pi * delta_TTO."""
    return 27.0 * float(pi) * float(delta_tto)


def price_per_out(role: str, f_rp: float, f_skill: float, t9_s: float) -> float:
    """c: runs per out of the pitcher covering an out instead of the league bullpen."""
    if role == "SP":
        return (float(f_rp) - float(f_skill) - float(t9_s)) / 27.0
    return (float(f_rp) - float(f_skill)) / 27.0


def pe_p_raw(lines: Mapping[str, Mapping], f_skill: float, f_rp: float, t9_s: float,
             league: Mapping[str, Mapping]) -> dict:
    """{role: g} for one pitcher-season, with each role's X~, G and c.

    lines: {role: {"n", "pitches", "outs"}}; league: {role: {"l_ppo", "l_pa"}}."""
    out = {}
    for role, ln in lines.items():
        n, p, o = (float(ln.get(k) or 0.0) for k in ("n", "pitches", "outs"))
        lg = league[role]
        x = implied_outs(n, p, o, lg["l_ppo"], lg["l_pa"])
        gap = x - o if n > 0 else 0.0
        c = price_per_out(role, f_rp, f_skill, t9_s)
        out[role] = {"x": x, "outs": o, "gap_outs": gap, "c": c, "g": gap * c}
    return out


def pe_p_delta(raw: Mapping[object, Mapping[str, Mapping]]) -> dict:
    """{pitcher: Delta_PE} from {pitcher: pe_p_raw(...)}: zero-sum per role, per out."""
    vals, expo, grp = {}, {}, {}
    for pid, roles in raw.items():
        for role, blk in roles.items():
            key = (pid, role)
            vals[key] = blk["g"]
            expo[key] = blk["outs"]
            grp[key] = role
    rc = recentre(vals, expo, grp)
    out: dict = {}
    for (pid, _role), v in rc.items():
        out[pid] = out.get(pid, 0.0) + v
    return out


# --------------------------------------------------------------------------
# PE-H
# --------------------------------------------------------------------------
def wear_price(f_rp: float, f_sp: float, t9_s: float, l_ppo_sp: float) -> float:
    """w: starter-wear runs per pitch to the batting side."""
    return (float(f_rp) - float(f_sp) - float(t9_s)) / (27.0 * float(l_ppo_sp))


def reliability(n: float, k: Optional[float]) -> float:
    """n / (n + K); a K of None or infinity gives 0 (the term carries nothing)."""
    if k is None or not math.isfinite(k) or n <= 0:
        return 0.0
    return float(n) / (float(n) + float(k))


def pe_h_raw(cl_res: float, n: float, p_res: float, m: float, w: float,
             k_cl: Optional[float], k_p: Optional[float]) -> float:
    """g_PEH = CLres * n / (n + K_CL) + w * Pres * m / (m + K_P)."""
    return float(cl_res) * reliability(n, k_cl) + float(w) * float(p_res) * reliability(m, k_p)


def split_half_k(rho_half: Optional[float], nbar: float,
                 clamp: Sequence[float] = K_CLAMP) -> float:
    """K from a split-half correlation (lab part 7): Spearman-Brown to the full season,
    then K = nbar * (1 - rho) / rho, clamped; rho_half at or below 0 gives infinity."""
    if rho_half is None or rho_half <= 0:
        return math.inf
    rho = 2.0 * rho_half / (1.0 + rho_half)
    k = float(nbar) * (1.0 - rho) / rho
    return min(max(k, float(clamp[0])), float(clamp[1]))


# --------------------------------------------------------------------------
# S2's skill FIP (part 9.4), before the park term
# --------------------------------------------------------------------------
def s2_targets(pool_sp: Mapping[str, float], pool_rp: Mapping[str, float], sigma: float) -> dict:
    """nu_j,c = sigma * nu_SP,c + (1 - sigma) * nu_RP,c, per component."""
    s = min(max(float(sigma), 0.0), 1.0)
    return {c: s * pool_sp[c] + (1.0 - s) * pool_rp[c] for c in ("k", "bb", "hbp", "hr")}


def s2_skill_fip(m: Mapping[str, float], tbf: float, ip: float, nu: Mapping[str, float],
                 cfip: float, shrink_hr: bool = True) -> Optional[float]:
    """F~: the FIP per nine of the shrunk counts m~ = TBF * (m + K nu) / (TBF + K)."""
    if not ip or ip <= 0 or not tbf or tbf <= 0:
        return None
    mt = {}
    for c in ("k", "bb", "hbp", "hr"):
        if c == "hr" and not shrink_hr:
            mt[c] = float(m[c])
        else:
            mt[c] = float(tbf) * shrink(m[c], tbf, S2_K[c], nu[c])
    return fip9(mt["hr"], mt["bb"], mt["hbp"], mt["k"], ip, cfip)


def pooled_rates(lines: Iterable[Mapping[str, float]]) -> Optional[dict]:
    """Sum m / sum TBF per component over a pool of season lines."""
    tot = {"k": 0.0, "bb": 0.0, "hbp": 0.0, "hr": 0.0, "tbf": 0.0}
    for ln in lines:
        for c in tot:
            tot[c] += float(ln.get(c) or 0.0)
    if tot["tbf"] <= 0:
        return None
    return {c: tot[c] / tot["tbf"] for c in ("k", "bb", "hbp", "hr")}


# --------------------------------------------------------------------------
# delta_TTO (lab part 7)
# --------------------------------------------------------------------------
def delta_tto(starter_seasons: Iterable[Mapping], min_late: int = 30) -> Optional[dict]:
    """Weighted mean of (mean run value at pass 3 and later - mean over every pass).

    starter_seasons: {"late_n", "late_sum", "all_n", "all_sum"} per starter-season."""
    num = den = 0.0
    used = 0
    for s in starter_seasons:
        ln, an = int(s["late_n"]), int(s["all_n"])
        if ln < min_late or an <= 0:
            continue
        d = s["late_sum"] / ln - s["all_sum"] / an
        num += d * ln
        den += ln
        used += 1
    if den <= 0:
        return None
    return {"delta_tto": num / den, "starter_seasons": used, "late_pa": int(den)}
