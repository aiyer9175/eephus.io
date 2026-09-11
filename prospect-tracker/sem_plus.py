# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SEM+ (Starter Evaluation Metric +) - the model core.

SEM+ is the starter analog of REM+ (see rem_plus.py): a ratio-to-league rate
index (100 = the average true starter in the calibration population, 110 = 10% better run prevention),
the ERA+/wRC+ family, NOT a z-score. The headline number is PURE SKILL: a
sample-shrunk, STARTER-pool-anchored FIP built from the components that carry a
pitcher's run-prevention talent (K%, BB%, HBP, a heavily regressed HR rate),
re-normalized over STARTERS so 100 is the average starter, not the average
pitcher.

Durability (innings, games started, average start length) is real starter value
but it is WORKLOAD, not run-prevention rate, so it rides SEPARATE context columns
and never moves the SEM+ talent number - the same two-number discipline REM+ uses
for leverage. Quality starts and times-through-order need game logs the pipeline
does not have, so SEM+ v1 uses average start length (IP/GS) as the displayed
durability read.

This module is PURE (no network, no I/O). It reuses the validated FIP machinery
from rem_plus (the empirical-Bayes shrink recipe + FIP linear weights); only the
pool (starters), the anchor (100 = average starter), the qualification, and the
role taxonomy differ. starter_export.py assembles inputs and writes the sidecar;
tools/sem_plus_lab.py is the forward-chained backtest. Every threshold here is a
module constant so the backtest can tune it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# Reuse the validated FIP machinery + shrink recipe from the reliever model.
from rem_plus import (
    _num, _safe_div, _shrink, _round,
    FIP_HR, FIP_BBHBP, FIP_K,
    K_STRIKEOUT, K_WALK, K_HBP, K_HOMERUN,
)

# ---- starter population + qualification ------------------------------------ #
POOL_MIN_IP = 20.0        # minimum IP to CONTRIBUTE to the starter anchor
MIN_START_SHARE = 0.50    # GS/G at or above this counts as a starter
QUALIFY_MIN_GS = 10       # leaderboard-qualified: a rotation regular
QUALIFY_MIN_IP = 50.0     # ... or a real innings sample

# ---- SEM+ role bands (rotation slots by SEM+) ------------------------------ #
ROLE_ORDER = ["Ace", "Mid-rotation", "Back-end", "Spot"]
SEM_ACE = 115.0
SEM_MID = 100.0
SEM_BACK = 88.0


@dataclass
class Starter:
    """One starter-season. Counts are season totals; rates derived in
    derive_rates(). go/ao are ground/air outs (a batted-ball signal for the
    optional GB-adjusted skill core the backtest evaluates)."""
    key: str
    name: str = ""
    team: str = ""
    mlbam: Optional[int] = None
    g: float = 0.0
    gs: float = 0.0
    ip: float = 0.0
    tbf: float = 0.0
    so: float = 0.0
    bb: float = 0.0
    hbp: float = 0.0
    hr: float = 0.0
    er: float = 0.0
    r: float = 0.0
    pit: float = 0.0
    strikes: float = 0.0
    cg: float = 0.0
    go: float = 0.0          # ground outs
    ao: float = 0.0          # air outs
    # computed
    rates: dict = field(default_factory=dict)
    fip_skill: Optional[float] = None
    sem_plus: Optional[int] = None
    sem_plus_raw: Optional[float] = None
    role: str = ""
    qualified: bool = False


def is_true_starter(s: Starter) -> bool:
    """Primarily a starter: most appearances are starts and real innings."""
    if s.ip <= 0 or s.g <= 0 or s.gs <= 0:
        return False
    return (s.gs / s.g) >= MIN_START_SHARE


def derive_rates(s: Starter) -> None:
    s.rates = {
        "k_pct": _safe_div(s.so, s.tbf),
        "bb_pct": _safe_div(s.bb, s.tbf),
        "hbp_pct": _safe_div(s.hbp, s.tbf),
        "hr_rate": _safe_div(s.hr, s.tbf),
        "k_bb_pct": (None if _safe_div(s.so, s.tbf) is None or _safe_div(s.bb, s.tbf) is None
                     else _safe_div(s.so, s.tbf) - _safe_div(s.bb, s.tbf)),
        "gb_pct": _safe_div(s.go, (s.go + s.ao)),   # ground-ball share of balls in play outs
        "ip_per_gs": _safe_div(s.ip, s.gs),          # average start length
        "strike_pct": _safe_div(s.strikes, s.pit),
        "era": _safe_div((s.er or 0.0) * 9.0, s.ip),
        "ra9": _safe_div((s.r or 0.0) * 9.0, s.ip),
    }


@dataclass
class Pool:
    n: int = 0
    mean_k_pct: float = 0.21
    mean_bb_pct: float = 0.075
    mean_hbp_pct: float = 0.010
    mean_hr_rate: float = 0.030
    mean_gb_pct: float = 0.44
    pool_era: float = 4.10
    cfip: float = 3.10
    mean_fip: float = 4.10


def build_pool(starters: Iterable[Starter], *, gb_adjust: bool = False) -> Pool:
    """League-STARTER means (over pool-contributing arms) + the FIP constant.
    When gb_adjust is set, the pool mean FIP anchor is computed from the
    GB-adjusted skill core (the X-S3 candidate)."""
    pool = [s for s in starters if s.ip >= POOL_MIN_IP and s.ip > 0]
    if not pool:
        return Pool()
    tbf = sum(s.tbf for s in pool)
    ip = sum(s.ip for s in pool)
    er = sum((s.er or 0.0) for s in pool)
    so = sum(s.so for s in pool)
    bb = sum(s.bb for s in pool)
    hbp = sum(s.hbp for s in pool)
    hr = sum(s.hr for s in pool)
    go = sum(s.go for s in pool)
    ao = sum(s.ao for s in pool)

    p = Pool()
    p.n = len(pool)
    p.mean_k_pct = so / tbf
    p.mean_bb_pct = bb / tbf
    p.mean_hbp_pct = hbp / tbf
    p.mean_hr_rate = hr / tbf
    p.mean_gb_pct = (go / (go + ao)) if (go + ao) else 0.44
    p.pool_era = er * 9.0 / ip
    raw_fip = (FIP_HR * hr + FIP_BBHBP * (bb + hbp) - FIP_K * so) / ip
    p.cfip = p.pool_era - raw_fip
    num = den = 0.0
    for s in pool:
        f = fip_skill(s, p, gb_adjust=gb_adjust)
        if f is not None:
            num += f * s.ip
            den += s.ip
    p.mean_fip = (num / den) if den else p.pool_era
    return p


def fip_skill(s: Starter, pool: Pool, *, gb_adjust: bool = False) -> Optional[float]:
    """Sample-shrunk FIP (ERA scale, lower = better). Component rates are
    regressed toward the starter pool by sample size, then converted back to
    expected counts over the pitcher's actual innings. When gb_adjust is set,
    the HR shrink TARGET is a ground-ball-implied expectation (grounders leave
    the park less), the X-S3 "more than FIP" candidate."""
    if s.ip <= 0 or s.tbf <= 0:
        return None
    if not s.rates:
        derive_rates(s)
    k = _shrink(s.rates["k_pct"], s.tbf, K_STRIKEOUT, pool.mean_k_pct)
    bb = _shrink(s.rates["bb_pct"], s.tbf, K_WALK, pool.mean_bb_pct)
    hbp = _shrink(s.rates["hbp_pct"], s.tbf, K_HBP, pool.mean_hbp_pct)
    hr_target = pool.mean_hr_rate
    if gb_adjust:
        gb = s.rates.get("gb_pct")
        if gb is not None and pool.mean_gb_pct:
            # scale the pool HR target by how much this arm beats the pool GB
            # rate (more grounders -> lower HR expectation); clamped to a band.
            factor = max(0.6, min(1.4, 1.0 - 0.8 * (gb - pool.mean_gb_pct)))
            hr_target = pool.mean_hr_rate * factor
    hr = _shrink(s.rates["hr_rate"], s.tbf, K_HOMERUN, hr_target)
    k_c, bb_c, hbp_c, hr_c = k * s.tbf, bb * s.tbf, hbp * s.tbf, hr * s.tbf
    fip = (FIP_HR * hr_c + FIP_BBHBP * (bb_c + hbp_c) - FIP_K * k_c) / s.ip + pool.cfip
    return max(fip, 1.0)


def sem_plus(s: Starter, pool: Pool, *, gb_adjust: bool = False) -> Optional[int]:
    """100 * pool_mean_FIP / player_FIP, rounded to nearest int (the +stat
    convention). Higher = better run prevention than the average starter."""
    f = fip_skill(s, pool, gb_adjust=gb_adjust)
    if f is None or f <= 0:
        return None
    raw = 100.0 * pool.mean_fip / f
    s.fip_skill = f
    s.sem_plus_raw = raw
    s.sem_plus = int(round(raw))
    return s.sem_plus


def assign_roles(starters: list[Starter]) -> None:
    """Rotation slot by SEM+ tier (Ace / Mid-rotation / Back-end / Spot)."""
    for s in starters:
        v = s.sem_plus
        if v is None:
            s.role = ""
        elif v >= SEM_ACE:
            s.role = "Ace"
        elif v >= SEM_MID:
            s.role = "Mid-rotation"
        elif v >= SEM_BACK:
            s.role = "Back-end"
        else:
            s.role = "Spot"


def _role_rank(role: str) -> int:
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return len(ROLE_ORDER)


def team_rotation(team: str, starters: list[Starter],
                  active_ids=None) -> dict:
    """Team rotation aggregates. Rotation+ is starter-IP-weighted SEM+ (the
    talent of the innings started).

    `active_ids` is the set of MLBAM ids on a current ACTIVE roster. When given,
    the CONSTRUCTED `rotation` ladder is built only from arms that can pitch
    today; Rotation+ and the other aggregates are not touched.

    THE SPLIT MATTERS AND IS THE SAME ONE hem_plus.team_offense MAKES. A rotation
    chart is a claim about who starts this week, so a Tommy John case in it is
    wrong: 78 of 226 rotation slots, 34.5%, were held by arms off an active
    roster. Rotation+ is a claim about the innings already thrown, and it feeds
    betting_model and the leaderboard vintages, so it stays on the full pool.

    None means the roster feed failed and NOTHING is filtered; an arm whose
    mlbam cannot be read is kept.
    """
    scored = [s for s in starters if s.sem_plus is not None and s.ip > 0]
    out = {"team": team, "n_starters": len(scored)}
    if not scored:
        return out
    num = den = 0.0
    for s in scored:
        num += s.sem_plus * s.ip
        den += s.ip
    rot = (num / den) if den else None
    out["rotation_plus"] = None if rot is None else int(round(rot))
    out["rotation_plus_raw"] = rot
    out["starter_ip"] = round(sum(s.ip for s in scored), 1)
    out["n_above_avg"] = sum(1 for s in scored if s.sem_plus >= 100)
    out["total_gs"] = int(sum(s.gs for s in scored))
    # top-3 by SEM+ = the rotation front
    front = sorted(scored, key=lambda s: s.sem_plus, reverse=True)[:3]
    out["front_sem"] = int(round(sum(s.sem_plus for s in front) / len(front))) if front else None
    avail = scored if active_ids is None else [
        s for s in scored
        if getattr(s, "mlbam", None) is None or int(s.mlbam) in active_ids]
    out["n_off_roster_dropped"] = len(scored) - len(avail)
    if not avail:
        avail = scored
        out["n_off_roster_dropped"] = 0
        out["roster_filter_skipped"] = "no active-roster arm matched; left unfiltered"
    ladder = sorted(avail, key=lambda s: (-(s.sem_plus or 0), -s.ip))
    out["rotation"] = [{"role": s.role, "key": s.key, "name": s.name,
                        "sem_plus": s.sem_plus, "ip": round(s.ip, 1),
                        "gs": int(s.gs)} for s in ladder]
    return out


def score_pool(starters: list[Starter], *, gb_adjust: bool = False,
               active_ids=None) -> dict:
    """End to end: filter to true starters, derive rates, build the pool, score
    SEM+, assign roles, roll up team rotations. Returns 'starters', 'teams',
    'pool'. Pure - callers supply the data."""
    pool_input = [s for s in starters if is_true_starter(s)]
    for s in pool_input:
        derive_rates(s)
    pool = build_pool(pool_input, gb_adjust=gb_adjust)
    for s in pool_input:
        sem_plus(s, pool, gb_adjust=gb_adjust)
        s.qualified = (s.gs >= QUALIFY_MIN_GS) or (s.ip >= QUALIFY_MIN_IP)
    assign_roles(pool_input)

    by_team: dict[str, list[Starter]] = {}
    for s in pool_input:
        by_team.setdefault(s.team or "", []).append(s)
    teams = []
    for team, ts in by_team.items():
        if team:
            teams.append(team_rotation(team, ts, active_ids))
    teams.sort(key=lambda t: (t.get("rotation_plus") or -999), reverse=True)

    scored = [s for s in pool_input if s.sem_plus is not None]
    scored.sort(key=lambda s: (s.sem_plus, s.sem_plus_raw or 0), reverse=True)
    return {
        "starters": [starter_row(s) for s in scored],
        "teams": teams,
        "pool": {"n": pool.n, "pool_era": round(pool.pool_era, 2),
                 "mean_fip": round(pool.mean_fip, 2),
                 "n_qualified": sum(1 for s in scored if s.qualified),
                 "n_provisional": sum(1 for s in scored if not s.qualified)},
    }


def starter_row(s: Starter) -> dict:
    """The per-starter record the frontend/export consumes."""
    return {
        "key": s.key, "mlbam": s.mlbam, "name": s.name, "team": s.team,
        "sem_plus": s.sem_plus, "sem_plus_raw": _round(s.sem_plus_raw, 1),
        "qualified": s.qualified, "role": s.role,
        "ip": round(s.ip, 1), "g": int(s.g), "gs": int(s.gs), "tbf": int(s.tbf),
        "cg": int(s.cg),
        "k_pct": _round(s.rates.get("k_pct"), 4),
        "bb_pct": _round(s.rates.get("bb_pct"), 4),
        "k_bb_pct": _round(s.rates.get("k_bb_pct"), 4),
        "gb_pct": _round(s.rates.get("gb_pct"), 4),
        "ip_per_gs": _round(s.rates.get("ip_per_gs"), 2),
        # NOT the standard FIP (audit F05-02): the sample-shrunk, starter-pool
        # skill FIP SEM+ is a ratio of. Key kept for compatibility; the board
        # labels it "Skill FIP" (see rem_plus.reliever_row).
        "fip": _round(s.fip_skill, 2),
        "era": _round(s.rates.get("era"), 2),
        "hr9": _round(_safe_div((s.hr or 0.0) * 9.0, s.ip), 2),
        "strike_pct": _round(s.rates.get("strike_pct"), 4),
    }
