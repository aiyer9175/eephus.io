# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""HEM+ (Hitter Evaluation Metric +) - the model core.

HEM+ is the hitter analog of REM+/SEM+ (see rem_plus.py / sem_plus.py): a
ratio-to-league RATE index (100 = the average qualified hitter, 110 = 10% more
offense per plate appearance), the wRC+/wOBA family, NOT a z-score. The headline
number is PURE OFFENSIVE RATE SKILL: a sample-shrunk, hitter-pool-anchored wOBA
built from the events that carry a hitter's run creation (unintentional walks,
HBP, singles, doubles, triples, home runs) with the FanGraphs wOBA linear
weights, then re-normalized over hitters so 100 is the average hitter.

Volume (plate appearances), baserunning (SB/CS), and defense are real value but
they are NOT offensive-rate skill, so they ride SEPARATE context columns and
never move the HEM+ number - the same two-number discipline REM+ uses for
leverage and SEM+ for durability.

Each wOBA component is regressed toward the league pool by its own sample-
reliability constant (walks stabilize fast, extra-base hits slowly), so a small
sample does not blow up the number. HEM+ = 100 * shrunk_player_wOBA /
pool_mean_wOBA, with the pool anchor set so the sample-weighted pool average
scores exactly 100 by construction.

This module is PURE (no network, no I/O). It reuses the empirical-Bayes shrink
recipe from rem_plus. hitter_export.py assembles inputs (StatsAPI hitting
statlines) and writes the sidecar; tools/hem_plus_lab.py is the forward-chained
backtest (HEM+(Y) vs next-year wOBA, must beat raw wOBA / OPS / AVG). Every
threshold here is a module constant so the backtest can tune it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# Reuse the validated empirical-Bayes shrink recipe from the reliever model.
from rem_plus import _num, _safe_div, _shrink, _round

# ---- wOBA linear weights (FanGraphs family; mirror fa_config assembly.woba_weights) --
# Event run values relative to an out. Held as module constants so the model stays
# pure; hitter_export may override from fa_config for a season-specific set.
W_UBB = 0.69     # unintentional walk
W_HBP = 0.72     # hit by pitch
W_1B = 0.89      # single
W_2B = 1.27      # double
W_3B = 1.62      # triple
W_HR = 2.10      # home run

# ---- per-component sample-reliability constants (wOBA-denominator PAs) --------- #
# The number of wOBA-PA at which each rate is ~50% signal (Pizza-Cutter / Carleton
# stabilization points). Walks and HBP stabilize fast; extra-base hits very slowly,
# so 2B/3B are pulled hard toward the pool (they are near-noise in a partial season).
K_UBB = 120.0
K_HBP = 240.0
K_1B = 290.0
K_2B = 1000.0
K_3B = 1600.0
K_HR = 170.0

# ---- hitter population + qualification --------------------------------------- #
POOL_MIN_PA = 50.0        # minimum PA to CONTRIBUTE to the hitter anchor
QUALIFY_MIN_PA = 200.0    # leaderboard-qualified: a regular's sample

# ---- HEM+ tier bands (offensive-rate tiers by HEM+) -------------------------- #
TIER_ORDER = ["Elite", "Above-avg", "Average", "Below-avg"]
HEM_ELITE = 140.0
HEM_ABOVE = 110.0
HEM_AVG = 90.0


@dataclass
class Hitter:
    """One hitter-season. Counts are season totals; rates derived in
    derive_rates(). Singles are back-solved (H - 2B - 3B - HR)."""
    key: str
    name: str = ""
    team: str = ""
    mlbam: Optional[int] = None
    pa: float = 0.0
    ab: float = 0.0
    h: float = 0.0
    doub: float = 0.0
    trip: float = 0.0
    hr: float = 0.0
    bb: float = 0.0
    ibb: float = 0.0
    hbp: float = 0.0
    sf: float = 0.0
    so: float = 0.0
    sb: float = 0.0
    cs: float = 0.0
    rbi: float = 0.0
    r: float = 0.0
    # computed
    rates: dict = field(default_factory=dict)
    woba_skill: Optional[float] = None
    woba_raw: Optional[float] = None
    hem_plus: Optional[int] = None
    hem_plus_raw: Optional[float] = None
    tier: str = ""
    qualified: bool = False


def _woba_denom(hi: "Hitter") -> float:
    """The wOBA denominator: AB + BB - IBB + SF + HBP (the wOBA 'plate
    appearance', excluding IBB/sac bunts). Doubles as the shrink sample size."""
    return max(0.0, (hi.ab or 0.0) + (hi.bb or 0.0) - (hi.ibb or 0.0)
              + (hi.sf or 0.0) + (hi.hbp or 0.0))


def _singles(hi: "Hitter") -> float:
    return max(0.0, (hi.h or 0.0) - (hi.doub or 0.0) - (hi.trip or 0.0) - (hi.hr or 0.0))


def derive_rates(hi: "Hitter") -> None:
    d = _woba_denom(hi)
    ubb = max(0.0, (hi.bb or 0.0) - (hi.ibb or 0.0))
    s1 = _singles(hi)
    pa = hi.pa or 0.0
    ab = hi.ab or 0.0
    tb = s1 + 2.0 * (hi.doub or 0.0) + 3.0 * (hi.trip or 0.0) + 4.0 * (hi.hr or 0.0)
    obp_den = ab + (hi.bb or 0.0) + (hi.hbp or 0.0) + (hi.sf or 0.0)
    bip = ab - (hi.so or 0.0) - (hi.hr or 0.0) + (hi.sf or 0.0)   # BABIP denominator
    hi.rates = {
        # wOBA component rates (per wOBA-denominator PA) - the shrink targets
        "ubb_rate": _safe_div(ubb, d),
        "hbp_rate": _safe_div(hi.hbp, d),
        "s1_rate": _safe_div(s1, d),
        "s2_rate": _safe_div(hi.doub, d),
        "s3_rate": _safe_div(hi.trip, d),
        "hr_rate": _safe_div(hi.hr, d),
        # context rates (never enter the skill number)
        "avg": _safe_div(hi.h, ab),
        "obp": _safe_div((hi.h or 0.0) + (hi.bb or 0.0) + (hi.hbp or 0.0), obp_den),
        "slg": _safe_div(tb, ab),
        "iso": _safe_div(tb - (hi.h or 0.0), ab),
        "bb_pct": _safe_div(hi.bb, pa),
        "k_pct": _safe_div(hi.so, pa),
        "babip": _safe_div((hi.h or 0.0) - (hi.hr or 0.0), bip),
        "sb_net": (hi.sb or 0.0) - (hi.cs or 0.0),
        "woba_denom": d,
    }
    op = hi.rates["obp"]
    sl = hi.rates["slg"]
    hi.rates["ops"] = (op + sl) if (op is not None and sl is not None) else None


def _raw_woba(hi: "Hitter") -> Optional[float]:
    """Unshrunk wOBA from the actual event counts (for display + the backtest
    comparator)."""
    d = _woba_denom(hi)
    if d <= 0:
        return None
    num = (W_UBB * max(0.0, (hi.bb or 0.0) - (hi.ibb or 0.0)) + W_HBP * (hi.hbp or 0.0)
           + W_1B * _singles(hi) + W_2B * (hi.doub or 0.0) + W_3B * (hi.trip or 0.0)
           + W_HR * (hi.hr or 0.0))
    return num / d


@dataclass
class Pool:
    n: int = 0
    mean_ubb: float = 0.075
    mean_hbp: float = 0.010
    mean_1b: float = 0.150
    mean_2b: float = 0.045
    mean_3b: float = 0.004
    mean_hr: float = 0.033
    pool_woba: float = 0.315
    mean_woba: float = 0.315     # sample-weighted mean of the SHRUNK skill -> anchors 100


def build_pool(hitters: Iterable["Hitter"]) -> Pool:
    """League-HITTER component means (over pool-contributing bats) + the shrunk-
    wOBA anchor. The anchor (mean_woba) is the wOBA-denominator-weighted mean of
    each hitter's SHRUNK wOBA, so the pool average scores exactly 100."""
    pool = [h for h in hitters if _woba_denom(h) >= POOL_MIN_PA]
    if not pool:
        return Pool()
    for h in pool:
        if not h.rates:
            derive_rates(h)
    dtot = sum(_woba_denom(h) for h in pool)
    if dtot <= 0:
        return Pool()

    def _wmean(key: str) -> float:
        num = sum((h.rates.get(key) or 0.0) * _woba_denom(h) for h in pool)
        return num / dtot

    p = Pool()
    p.n = len(pool)
    p.mean_ubb = _wmean("ubb_rate")
    p.mean_hbp = _wmean("hbp_rate")
    p.mean_1b = _wmean("s1_rate")
    p.mean_2b = _wmean("s2_rate")
    p.mean_3b = _wmean("s3_rate")
    p.mean_hr = _wmean("hr_rate")
    p.pool_woba = (W_UBB * p.mean_ubb + W_HBP * p.mean_hbp + W_1B * p.mean_1b
                   + W_2B * p.mean_2b + W_3B * p.mean_3b + W_HR * p.mean_hr)
    num = den = 0.0
    for h in pool:
        w = woba_skill(h, p)
        if w is not None:
            num += w * _woba_denom(h)
            den += _woba_denom(h)
    p.mean_woba = (num / den) if den else p.pool_woba
    return p


def woba_skill(hi: "Hitter", pool: Pool) -> Optional[float]:
    """Sample-shrunk wOBA (higher = better). Each component rate is regressed
    toward the hitter pool by its own reliability constant, then recombined with
    the wOBA linear weights. Extra-base hits (slow to stabilize) are pulled hard
    toward the pool in a partial season; walks/singles less so."""
    d = _woba_denom(hi)
    if d <= 0:
        return None
    if not hi.rates:
        derive_rates(hi)
    ubb = _shrink(hi.rates["ubb_rate"], d, K_UBB, pool.mean_ubb)
    hbp = _shrink(hi.rates["hbp_rate"], d, K_HBP, pool.mean_hbp)
    s1 = _shrink(hi.rates["s1_rate"], d, K_1B, pool.mean_1b)
    s2 = _shrink(hi.rates["s2_rate"], d, K_2B, pool.mean_2b)
    s3 = _shrink(hi.rates["s3_rate"], d, K_3B, pool.mean_3b)
    hr = _shrink(hi.rates["hr_rate"], d, K_HR, pool.mean_hr)
    return (W_UBB * ubb + W_HBP * hbp + W_1B * s1 + W_2B * s2 + W_3B * s3 + W_HR * hr)


def hem_plus(hi: "Hitter", pool: Pool) -> Optional[int]:
    """100 * shrunk_player_wOBA / pool_mean_wOBA, rounded (the +stat convention).
    Higher = more offense per PA than the average hitter."""
    w = woba_skill(hi, pool)
    if w is None or pool.mean_woba <= 0:
        return None
    raw = 100.0 * w / pool.mean_woba
    hi.woba_skill = w
    hi.woba_raw = _raw_woba(hi)
    hi.hem_plus_raw = raw
    hi.hem_plus = int(round(raw))
    return hi.hem_plus


def assign_tiers(hitters: list["Hitter"]) -> None:
    for h in hitters:
        v = h.hem_plus
        if v is None:
            h.tier = ""
        elif v >= HEM_ELITE:
            h.tier = "Elite"
        elif v >= HEM_ABOVE:
            h.tier = "Above-avg"
        elif v >= HEM_AVG:
            h.tier = "Average"
        else:
            h.tier = "Below-avg"


def team_offense(team: str, hitters: list["Hitter"]) -> dict:
    """Team offense aggregates. Offense+ is PA-weighted HEM+ (the offensive
    quality of the plate appearances the lineup takes)."""
    scored = [h for h in hitters if h.hem_plus is not None and h.pa > 0]
    out = {"team": team, "n_hitters": len(scored)}
    if not scored:
        return out
    num = den = 0.0
    for h in scored:
        num += h.hem_plus * h.pa
        den += h.pa
    off = (num / den) if den else None
    out["offense_plus"] = None if off is None else int(round(off))
    out["offense_plus_raw"] = off
    out["team_pa"] = int(sum(h.pa for h in scored))
    out["n_above_avg"] = sum(1 for h in scored if h.hem_plus >= 100)
    # heart of the order: top-3 by HEM+ among the regulars
    front = sorted([h for h in scored if h.pa >= QUALIFY_MIN_PA],
                   key=lambda h: h.hem_plus, reverse=True)[:3]
    out["heart_hem"] = int(round(sum(h.hem_plus for h in front) / len(front))) if front else None
    ladder = sorted(scored, key=lambda h: (-(h.hem_plus or 0), -h.pa))
    out["lineup"] = [{"tier": h.tier, "key": h.key, "name": h.name,
                      "hem_plus": h.hem_plus, "pa": int(h.pa)} for h in ladder]
    return out


def score_pool(hitters: list["Hitter"]) -> dict:
    """End to end: derive rates, build the pool, score HEM+, assign tiers, roll up
    team offenses. Returns 'hitters', 'teams', 'pool'. Pure - callers supply the
    data."""
    pool_input = [h for h in hitters if _woba_denom(h) > 0]
    for h in pool_input:
        derive_rates(h)
    pool = build_pool(pool_input)
    for h in pool_input:
        hem_plus(h, pool)
        h.qualified = _woba_denom(h) >= QUALIFY_MIN_PA
    assign_tiers(pool_input)

    by_team: dict[str, list["Hitter"]] = {}
    for h in pool_input:
        by_team.setdefault(h.team or "", []).append(h)
    teams = []
    for team, hs in by_team.items():
        if team:
            teams.append(team_offense(team, hs))
    teams.sort(key=lambda t: (t.get("offense_plus") or -999), reverse=True)

    scored = [h for h in pool_input if h.hem_plus is not None]
    scored.sort(key=lambda h: (h.hem_plus, h.hem_plus_raw or 0), reverse=True)
    return {
        "hitters": [hitter_row(h) for h in scored],
        "teams": teams,
        "pool": {"n": pool.n, "pool_woba": round(pool.pool_woba, 3),
                 "mean_woba": round(pool.mean_woba, 3),
                 "n_qualified": sum(1 for h in scored if h.qualified),
                 "n_provisional": sum(1 for h in scored if not h.qualified)},
    }


def hitter_row(h: "Hitter") -> dict:
    """The per-hitter record the frontend/export consumes. HEM+ is the skill; the
    rate + volume + baserunning columns ride as separate context."""
    return {
        "key": h.key, "mlbam": h.mlbam, "name": h.name, "team": h.team,
        "hem_plus": h.hem_plus, "hem_plus_raw": _round(h.hem_plus_raw, 1),
        "qualified": h.qualified, "tier": h.tier,
        "pa": int(h.pa), "ab": int(h.ab), "hr": int(h.hr), "bb": int(h.bb),
        "sb": int(h.sb),
        "woba": _round(h.woba_skill, 3),
        "woba_raw": _round(h.woba_raw, 3),
        "avg": _round(h.rates.get("avg"), 3),
        "obp": _round(h.rates.get("obp"), 3),
        "slg": _round(h.rates.get("slg"), 3),
        "ops": _round(h.rates.get("ops"), 3),
        "iso": _round(h.rates.get("iso"), 3),
        "bb_pct": _round(h.rates.get("bb_pct"), 4),
        "k_pct": _round(h.rates.get("k_pct"), 4),
        "babip": _round(h.rates.get("babip"), 3),
    }
