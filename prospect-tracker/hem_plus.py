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

PER-HAND HEM+, ESTIMATOR platoon_ratio_v1 (pre-registered 2026-10-01, before its
constant is fitted; docs/diamond-betting.md section 5e, "The per-hand estimator
platoon_ratio_v1"). Census finding M06-05: the per-hand number reused the season
shrink on the split's smaller denominator, so a thin split regressed toward 100
rather than toward the hitter's own level (two-hand mean minus season HEM+, slope
-0.15 on season - 100). The replacement, for a hitter with lines against both
hands (d_L, d_R their wOBA denominators, x_L, x_R their raw wOBA):
  q   = x_L / x_R - 1                         raw platoon ratio
  n   = d_L * d_R / (d_L + d_R)               its sample (0 when a hand is missing)
  q*  = (n * q + K_b * mu_b) / (n + K_b)      shrunk toward the league ratio for
                                              bat side b (L, R, S; unknown = all),
                                              mu_b this season's pooled ratio, the
                                              frozen 2016-2018 one when the side's
                                              pool is under 1,000 wOBA-PA a hand
  m_R = (d_L + d_R) / (d_L * (1 + q*) + d_R),  m_L = (1 + q*) * m_R
  per-hand wOBA = season shrunk wOBA * m_h, scored on the SEASON pool anchor.
So the d-weighted mean of the two hands IS the season number, and only the gap
between them is regressed. K_b is fitted ONCE on 2016-2018 by the DEM+ precedent
(positional_fit.fit_signal, year-over-year persistence of q, pairs with n >= 50
both years, r clamped to [0.05, 0.95], K = hm * (1 - r) / r rounded to 10, a side
under 30 pairs takes the all-hitter K) and frozen here; nothing after 2018 is read.
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

# ---- HEM+ display spread -----------------------------------------------------
# The bare ratio (100 * wOBA / league_wOBA) has a slope of ~100/0.323 ~= 310
# points per unit wOBA, about 2.28x FLATTER than the wRC+/OPS+ DEVIATION scale
# users mentally compare against - so every hitter (and every team Offense+) sat
# compressed near 100 and the league looked near-identical. HEM_SPREAD_GAIN
# rescales the deviation from 100 to the wRC+ convention. It is a MONOTONE
# transform of the score, so it preserves rank EXACTLY: the Spearman-rank
# validation (X-H1 gap-vs-raw-wOBA, X-H2 3yr) is unchanged (confirmed offline).
# 100 stays "league average"; only the spread around it widens.
HEM_SPREAD_GAIN = 2.28

# ---- HEM+ tier bands (offensive-rate tiers by HEM+, on the widened scale) ----- #
TIER_ORDER = ["Elite", "Above-avg", "Average", "Below-avg"]
HEM_ELITE = 135.0
HEM_ABOVE = 112.0
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
    bats: Optional[str] = None   # 'L' | 'R' | 'S' (batSide), for lineup construction
    # MLB's primary-position label off the season hitting row ('P', 'DH', 'C',
    # 'TWP', ...). Read for the bench only: it drops pitchers and names a DH,
    # which the fielding-innings feed cannot see. Never enters HEM+.
    primary_pos: Optional[str] = None
    # Pitches seen on the season line (StatsAPI numberOfPitches). Read only by
    # the board's P/PA columns (pitch_rates_boards); never enters HEM+.
    np: Optional[float] = None
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
    """100 + gain * (100 * shrunk_player_wOBA / pool_mean_wOBA - 100), rounded (the
    +stat convention on the wRC+-width scale). 100 = average; HEM_SPREAD_GAIN
    widens the deviation so the league reads with real separation. Monotone in the
    bare ratio, so ranks (and the validated Spearman gates) are unchanged."""
    w = woba_skill(hi, pool)
    if w is None or pool.mean_woba <= 0:
        return None
    raw = 100.0 + HEM_SPREAD_GAIN * (100.0 * w / pool.mean_woba - 100.0)
    hi.woba_skill = w
    hi.woba_raw = _raw_woba(hi)
    hi.hem_plus_raw = raw
    hi.hem_plus = int(round(raw))
    return hi.hem_plus


#: The split counting line this module accepts, StatsAPI statSplits field -> Hitter
#: field. Kept as module data so the caller that fetches (hitter_export) and the
#: scorer that consumes cannot drift about which events make the wOBA numerator.
SPLIT_COUNT_FIELDS = {
    "plateAppearances": "pa", "atBats": "ab", "hits": "h", "doubles": "doub",
    "triples": "trip", "homeRuns": "hr", "baseOnBalls": "bb",
    "intentionalWalks": "ibb", "hitByPitch": "hbp", "sacFlies": "sf",
    "strikeOuts": "so",
}


#: The per-hand estimator id. Stamped into the hitter artifact's platoon_splits
#: block and from there into the vintage basis, where the 5e / 5f dark clocks
#: read it (leaderboard_vintages.SPLIT_ESTIMATOR_ID, pinned equal by a test).
SPLIT_ESTIMATOR = "platoon_ratio_v1"

#: Platoon-ratio shrink constants by bat side, in units of the ratio's sample
#: n = d_L * d_R / (d_L + d_R). FROZEN from the pre-registered fit
#: (tools/hem_split_ratio_lab.py; StatsAPI statSplits 2016-2018, same-side
#: consecutive-season pairs with n >= 50 both years, the fit_signal rule; 727,
#: 734 and 722 hitter-seasons with both lines). Fit output, for the record:
#:   L    pairs 121  r_raw -0.0499  r 0.05 (clamp)  hm 104.2  K 1980
#:   R    pairs 266  r_raw  0.0477  r 0.05 (clamp)  hm  93.9  K 1780
#:   S    pairs  62  r_raw -0.0710  r 0.05 (clamp)  hm  99.3  K 1890
#:   ALL  pairs 449  r_raw  0.2159  r 0.2159        hm  97.4  K 350
#: Within a bat side the year-to-year persistence of the ratio is
#: indistinguishable from zero, so all three side constants sit on the clamp
#: floor and a season's own platoon gap carries about 5 percent weight at a
#: regular's sample (n near 100). ALL persists because it mixes the sides, whose
#: league gaps differ; it serves only a bat with no known side, toward the
#: all-hitter ratio, where that between-side spread is real signal.
K_PLATOON = {"L": 1980.0, "R": 1780.0, "S": 1890.0, "ALL": 350.0}
#: League platoon ratio (wOBA vs LHP over wOBA vs RHP, minus 1) by bat side,
#: pooled over 2016-2018 by the same fit. Used only when this season's pool for
#: a side holds under PLATOON_MU_MIN_D wOBA-PA against either hand.
MU_PLATOON_FROZEN = {"L": -0.1121, "R": 0.0512, "S": -0.0179, "ALL": -0.0087}
PLATOON_MU_MIN_D = 1000.0
PLATOON_SIDES = ("L", "R", "S")


def _line_hitter(counts: dict | None) -> Optional["Hitter"]:
    """One split counting line as a scratch Hitter, or None when unusable."""
    if not isinstance(counts, dict):
        return None
    tmp = Hitter(key="_split")
    for src, dst in SPLIT_COUNT_FIELDS.items():
        v = counts.get(src)
        if v is None:
            continue
        try:
            setattr(tmp, dst, float(v))
        except (TypeError, ValueError):
            continue
    return tmp if _woba_denom(tmp) > 0 else None


def _woba_parts(hi: Optional["Hitter"]) -> tuple[float, float]:
    """(raw wOBA numerator, wOBA denominator) of a line; (0, 0) when absent."""
    if hi is None:
        return 0.0, 0.0
    d = _woba_denom(hi)
    w = _raw_woba(hi)
    return ((w or 0.0) * d, d) if d > 0 else (0.0, 0.0)


def platoon_side(bats: Optional[str]) -> str:
    """The shrink group for a bat side: 'L', 'R', 'S', or 'ALL' when unknown."""
    b = (bats or "").upper()[:1]
    return b if b in PLATOON_SIDES else "ALL"


def platoon_ratio(line_l: Optional["Hitter"],
                  line_r: Optional["Hitter"]) -> tuple[Optional[float], float]:
    """(q, n): raw platoon ratio wOBA_vsL / wOBA_vsR - 1 and its sample
    d_L * d_R / (d_L + d_R). (None, 0.0) unless both lines carry a wOBA
    denominator and the vs-RHP wOBA is positive."""
    nl, dl = _woba_parts(line_l)
    nr, dr = _woba_parts(line_r)
    if dl <= 0 or dr <= 0 or nr <= 0:
        return None, 0.0
    return (nl / dl) / (nr / dr) - 1.0, dl * dr / (dl + dr)


def league_platoon_ratios(platoon_counts: Optional[dict],
                          bats_by_id: Optional[dict] = None,
                          min_d: float = PLATOON_MU_MIN_D) -> dict:
    """{side: mu} for 'L', 'R', 'S' and 'ALL': pooled wOBA against left-handers
    over pooled wOBA against right-handers, minus 1, over every hitter of that
    side with both lines. A side whose pool holds under `min_d` wOBA-PA on
    either hand takes MU_PLATOON_FROZEN."""
    acc = {s: [0.0, 0.0, 0.0, 0.0] for s in PLATOON_SIDES + ("ALL",)}
    pc = platoon_counts or {}
    left, right = pc.get("L") or {}, pc.get("R") or {}
    for mid in set(left) & set(right):
        nl, dl = _woba_parts(_line_hitter(left.get(mid)))
        nr, dr = _woba_parts(_line_hitter(right.get(mid)))
        if dl <= 0 or dr <= 0:
            continue
        side = platoon_side((bats_by_id or {}).get(int(mid)))
        for s in {side, "ALL"}:
            a = acc[s]
            a[0] += nl
            a[1] += dl
            a[2] += nr
            a[3] += dr
    out = {}
    for s, (nl, dl, nr, dr) in acc.items():
        if dl >= min_d and dr >= min_d and nr > 0:
            out[s] = (nl / dl) / (nr / dr) - 1.0
        else:
            out[s] = MU_PLATOON_FROZEN[s]
    return out


def shrink_platoon_ratio(q: Optional[float], n: float, side: str,
                         mu: dict) -> float:
    """q* = (n q + K mu) / (n + K) for the side's K and league ratio; the league
    ratio itself when there is no sample."""
    m = mu.get(side, MU_PLATOON_FROZEN.get(side, 0.0))
    k = K_PLATOON.get(side, K_PLATOON["ALL"])
    if q is None or n <= 0:
        return m
    if k <= 0:
        return q
    return (n * q + k * m) / (n + k)


def hand_multipliers(q_star: float, d_l: float, d_r: float) -> tuple[float, float]:
    """(m_L, m_R) with m_L / m_R = 1 + q* and d_L m_L + d_R m_R = d_L + d_R, so
    the d-weighted mean of the two hands is the season level exactly. A hitter
    with one line gets 1.0 on it."""
    tot = d_l + d_r
    den = d_l * (1.0 + q_star) + d_r
    if tot <= 0 or den <= 0:
        return 1.0, 1.0
    m_r = tot / den
    return (1.0 + q_star) * m_r, m_r


def _hem_from_woba(w: Optional[float], pool: Pool) -> Optional[int]:
    """The season HEM+ scale for a wOBA value: same anchor, same gain, nearest."""
    if w is None or pool.mean_woba <= 0:
        return None
    return int(round(100.0 + HEM_SPREAD_GAIN * (100.0 * w / pool.mean_woba - 100.0)))


def split_hem_pair(season: Optional["Hitter"], counts_l: Optional[dict],
                   counts_r: Optional[dict], pool: Pool,
                   mu: Optional[dict] = None) -> dict:
    """{'L': hem_vs_lhp, 'R': hem_vs_rhp} for one hitter, estimator
    platoon_ratio_v1 (module docstring; docs/diamond-betting.md 5e).

    WHY A PER-HAND NUMBER EXISTS (audit finding F08-02, 2026-09-10). Both
    hand-labelled orders used to carry the SEASON hem_plus, so `off_vs_lhp` and
    `off_vs_rhp` were a mean over a permutation of the same nine bats and came out
    bit-identical on all 30 clubs across all 480 captured rows.

    WHY THIS ESTIMATOR (census M06-05, owner answer 2026-09-25). The first
    per-hand number re-ran the season shrink on each hand's smaller line, which
    pulled a thin split toward 100 instead of toward the hitter's own level: a
    125+ hitter lost 4.7 points on the two-hand mean and a 95-or-below hitter
    gained 2.2. Here the LEVEL is the season shrunk wOBA, and only the GAP
    between the hands is regressed, toward the league gap for the bat side.

    THE ANCHOR IS STILL THE SEASON POOL. Scoring each hand against its own pool
    would re-centre both to 100 and delete the league platoon effect, which is
    the signal; a lefty's vs-LHP number reads below his season HEM+ by his
    regressed platoon gap.

    `season` is the scored season Hitter (woba_skill set by hem_plus). When it is
    absent the level is the shrunk wOBA of the two lines summed. A hand with no
    usable line is None, never a fabricated value."""
    line_l, line_r = _line_hitter(counts_l), _line_hitter(counts_r)
    out = {"L": None, "R": None}
    if line_l is None and line_r is None:
        return out
    level = season.woba_skill if season is not None else None
    if level is None:
        tot = Hitter(key="_both")
        for ln in (line_l, line_r):
            if ln is None:
                continue
            for f in SPLIT_COUNT_FIELDS.values():
                setattr(tot, f, getattr(tot, f) + getattr(ln, f))
        level = woba_skill(tot, pool)
    if level is None:
        return out
    side = platoon_side(season.bats if season is not None else None)
    q, n = platoon_ratio(line_l, line_r)
    q_star = shrink_platoon_ratio(q, n, side, mu or MU_PLATOON_FROZEN)
    m_l, m_r = hand_multipliers(q_star, _woba_denom(line_l) if line_l else 0.0,
                                _woba_denom(line_r) if line_r else 0.0)
    if line_l is not None:
        out["L"] = _hem_from_woba(level * m_l, pool)
    if line_r is not None:
        out["R"] = _hem_from_woba(level * m_r, pool)
    return out


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


# ---- sabermetric batting-order construction ---------------------------------
# Slot (1-indexed) for the k-th best bat: best -> #2 and #4 (The Book: your two
# best hitters bat 2nd and 4th, not leadoff), then #1, #3, #5, then 6-9 by
# quality. A tunable constant so a future eval can refit it.
SLOT_PRIORITY = [2, 4, 1, 3, 5, 6, 7, 8, 9]
PLATOON_ADV = 4.0        # HEM+ pts a platoon-advantaged bat gains vs the given hand
PLATOON_S = 2.0          # switch hitters: small universal edge (never disadvantaged)
STAGGER_MAX_COST = 8.0   # only swap for handedness when two bats' Q are within this band


def _platoon_adj(bats: Optional[str], opp_hand: str) -> float:
    """Heuristic platoon term for lineup construction (Phase 1, no split HEM+ yet):
    a lefty gains vs RHP, a righty gains vs LHP, a switch hitter always holds a
    small edge. Used only to re-lens the order vs L / vs R, not the published
    HEM+ number."""
    b = (bats or "").upper()[:1]
    if b == "S":
        return PLATOON_S
    if b not in ("L", "R"):
        return 0.0
    adv = (opp_hand == "R" and b == "L") or (opp_hand == "L" and b == "R")
    return PLATOON_ADV if adv else -PLATOON_ADV


def build_batting_order(hitters: list["Hitter"], opp_hand: str,
                        split_hem: Optional[dict] = None) -> Optional[list[dict]]:
    """A sabermetric 9-man batting order vs the given pitcher hand ('R' or 'L').
    Not just HEM+ descending: the two best bats hit 2nd and 4th, then a handedness
    stagger breaks up same-handed runs (managers alternate L/R so a reliever can't
    match up). Everyday nine = the top 9 by PA. Returns None if fewer than 9.

    `split_hem` is {mlbam: {'L': hem_vs_lhp, 'R': hem_vs_rhp}} from real platoon
    lines (hitter_export.load_platoon_splits). When a slot resolves, it is stamped
    as `hem_plus_split` ALONGSIDE the untouched season `hem_plus`, never instead
    of it: the served per-slot display and Offense+ keep reading `hem_plus`, so
    this adds a column and moves no served number. The ORDER is still built on the
    season number plus the `_platoon_adj` heuristic; re-ordering on the real split
    is a served-display change and belongs to its own epoch (audit F08-02)."""
    pool = [h for h in hitters if h.hem_plus is not None and (h.pa or 0) > 0]
    pool = sorted(pool, key=lambda h: -(h.pa or 0))[:9]
    if len(pool) < 9:
        return None

    def Q(h):   # context quality vs this hand
        return (h.hem_plus or 0) + _platoon_adj(h.bats, opp_hand)

    ranked = sorted(pool, key=lambda h: -Q(h))
    slots: list = [None] * 9
    for k, h in enumerate(ranked):
        slots[SLOT_PRIORITY[k] - 1] = h

    def _hand(h):
        return (h.bats or "").upper()[:1]

    def _same(a, b):
        ha, hb = _hand(a), _hand(b)
        return bool(ha) and bool(hb) and ha != "S" and hb != "S" and ha == hb

    # Handedness stagger: greedily swap a same-handed neighbor with a later,
    # different-handed bat of near-equal quality. Deterministic, bounded passes.
    improved, passes = True, 0
    while improved and passes < 4:
        improved, passes = False, passes + 1
        for i in range(8):
            if _same(slots[i], slots[i + 1]):
                for j in range(i + 2, 9):
                    if (not _same(slots[i], slots[j])
                            and abs(Q(slots[i + 1]) - Q(slots[j])) <= STAGGER_MAX_COST):
                        slots[i + 1], slots[j] = slots[j], slots[i + 1]
                        improved = True
                        break
    order = []
    for idx, h in enumerate(slots):
        row = {"slot": idx + 1, "key": h.key, "name": h.name,
               "bats": h.bats, "hem_plus": h.hem_plus, "pa": int(h.pa),
               "platoon_adv": _platoon_adj(h.bats, opp_hand) > 0}
        if split_hem and h.mlbam is not None:
            sp = split_hem.get(int(h.mlbam))
            if isinstance(sp, dict):
                v = sp.get(opp_hand)
                if v is not None:
                    row["hem_plus_split"] = v
                    row["split_pa"] = (sp.get("pa") or {}).get(opp_hand)
        order.append(row)
    return order


# ---- bench, positions and the platoon-option marker (display only) ----------
# Everything below serves SIBLING keys of `orders` (bench per-hand fields,
# slot_meta, platoon_options, regulars_out). None of it may reorder the nine,
# add a key to a slot, or move Offense+: `orders` feeds the leaderboard
# vintages' off_vs_lhp / off_vs_rhp and betting_export prices order[:5].
#
# A marker fires for opposing hand h, starter S and bench bat B only when ALL of:
#   1. S lacks the platoon edge vs h (bats h, not a switch hitter);
#   2. B holds it (bats opposite h, or switch);
#   3. B has played S's primary position (DH is open to every non-pitcher);
#   4. both carry a real per-hand HEM+ vs h (a season fallback never counts);
#   5. both have PLATOON_OPTION_MIN_SPLIT_PA or more split PA vs h;
#   6. B's split minus S's split is PLATOON_OPTION_MARGIN or more.
# The reader-facing statement of the rule is the platoon_option glossary entry.
#: Split PA floor, both players, against the hand: the page's existing
#: thin-sample floor. Under platoon_ratio_v1 a hand's number below it is mostly
#: the season level times the league gap for the bat side (the hitter's own gap
#: carries n / (n + K_PLATOON) of the weight). The card dims any per-hand number
#: under this same floor. Unchanged by the 2026-10-01 estimator switch.
PLATOON_OPTION_MIN_SPLIT_PA = 100
#: HEM+ points the bench split must clear the starter's by. Re-derived on
#: platoon_ratio_v1 (owner answer M17HEM-1 (b), 2026-10-01) by the recipe that
#: set the first value (tools/plt_margin_lab.py): the population SD of (vs-LHP
#: minus vs-RHP HEM+) within a bat side and vs-LHP PA band, over cells of 8+
#: hitters with both hands, its low end rounded up to a multiple of 5.
#:   first construction, 2026-09-11 board: 13.5 to 22.3, 635 hitters -> 15
#:   first construction, final 2026 lines: 13.23 to 22.70, 644 hitters -> 15
#:   platoon_ratio_v1, final 2026 lines:   1.24 to 3.59, 644 hitters -> 5
#: The spread collapsed because a hitter's own gap now carries about 5 percent
#: of the weight, so his two hand numbers differ mostly by his bat side's league
#: gap scaled by his level. The cells are frozen below; a test pins the margin
#: to them and, when the lab's cached feeds exist, the cells to a rerun.
PLATOON_OPTION_MARGIN = 5
PLATOON_OPTION_MARGIN_DERIVATION = {
    "estimator": "platoon_ratio_v1",
    "season": 2026,
    "n_hitters_both_hands": 644,
    "min_cell_n": 8,
    "bands": [[20, 60], [60, 100], [100, 150], [150, 250], [250, 900]],
    "round_to": 5,
    "cells": [
        {"bats": "L", "vs_lhp_pa": [20, 60], "n": 51, "mean": -21.12, "sd": 1.96},
        {"bats": "L", "vs_lhp_pa": [60, 100], "n": 35, "mean": -21.46, "sd": 1.93},
        {"bats": "L", "vs_lhp_pa": [100, 150], "n": 28, "mean": -21.82, "sd": 1.85},
        {"bats": "L", "vs_lhp_pa": [150, 250], "n": 48, "mean": -23.08, "sd": 3.59},
        {"bats": "R", "vs_lhp_pa": [20, 60], "n": 93, "mean": 11.71, "sd": 1.24},
        {"bats": "R", "vs_lhp_pa": [60, 100], "n": 56, "mean": 11.66, "sd": 1.65},
        {"bats": "R", "vs_lhp_pa": [100, 150], "n": 69, "mean": 12.41, "sd": 1.86},
        {"bats": "R", "vs_lhp_pa": [150, 250], "n": 72, "mean": 12.92, "sd": 2.76},
        {"bats": "S", "vs_lhp_pa": [20, 60], "n": 23, "mean": -7.04, "sd": 1.71},
        {"bats": "S", "vs_lhp_pa": [100, 150], "n": 8, "mean": -8.62, "sd": 1.58},
        {"bats": "S", "vs_lhp_pa": [150, 250], "n": 19, "mean": -6.42, "sd": 3.13},
    ],
    "spread_low": 1.24,
    "spread_high": 3.59,
    "previous": {"margin": 15, "spread_low": 13.5, "spread_high": 22.3,
                 "n_hitters_both_hands": 635, "board": "2026-09-11",
                 "construction": "per-hand season shrink (before platoon_ratio_v1)"},
}
#: Defensive innings at a position that make a bat eligible there (rule 3). The
#: fielding-innings feed carries innings only; 30 innings reproduces the
#: fielding_positions 10-games-or-5-starts rule on 646 of 647 eligible
#: (bat, position) pairs of the 2026-09-11 nine and bench, with 25 extra.
PLATOON_OPTION_MIN_POS_INN = 30.0
#: The fielding positions a bat can be eligible at; DH is handled by rule.
FIELD_POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
BENCH_MAX = 6


def is_pitcher(hi: "Hitter") -> bool:
    """MLB labels the player a pitcher. A two-way player carries 'TWP' and stays."""
    return (hi.primary_pos or "").upper() == "P"


def player_positions(hi: "Hitter", positions: Optional[dict]) -> Optional[list]:
    """Eligible 2026 MLB positions, primary first, or None when the fielding lens
    is down (`positions` None). `positions` is {mlbam: {pos: innings}}.

    Fielding positions with PLATOON_OPTION_MIN_POS_INN or more innings, most
    innings first. A bat MLB labels DH leads with DH, because DH has no innings
    and so is invisible to the fielding feed; a non-pitcher with no eligible
    fielding position is a DH by elimination. A pitcher is ['P']."""
    if positions is None:
        return None
    if is_pitcher(hi):
        return ["P"]
    inn = positions.get(int(hi.mlbam)) if hi.mlbam is not None else None
    inn = inn if isinstance(inn, dict) else {}
    field = sorted((p for p in FIELD_POSITIONS
                    if (_num(inn.get(p)) or 0.0) >= PLATOON_OPTION_MIN_POS_INN),
                   key=lambda p: (-(_num(inn.get(p)) or 0.0), FIELD_POSITIONS.index(p)))
    out = (["DH"] if (hi.primary_pos or "").upper() == "DH" else []) + field
    return out or ["DH"]


def bench_row(hi: "Hitter", split_hem: Optional[dict],
              positions: Optional[dict]) -> dict:
    """One served bench row: the five legacy fields plus the per-hand HEM+ and
    split PA from the SAME split map the slots read (null per hand when the feed
    has no line), and the eligible positions."""
    sp = (split_hem or {}).get(int(hi.mlbam)) if hi.mlbam is not None else None
    sp = sp if isinstance(sp, dict) else {}
    spa = sp.get("pa") or {}
    return {"key": hi.key, "name": hi.name, "bats": hi.bats,
            "hem_plus": hi.hem_plus, "pa": int(hi.pa), "mlbam": hi.mlbam,
            "pos": player_positions(hi, positions),
            "hem_plus_split": {"L": sp.get("L"), "R": sp.get("R")},
            "split_pa": {"L": spa.get("L"), "R": spa.get("R")}}


def platoon_options(order: Optional[list], bench: list, slot_meta: dict,
                    hand: str) -> tuple[list, int]:
    """(options, n_withheld_by_floor) for one opposing hand, from SERVED rows only
    (slot `bats` / `hem_plus_split` / `split_pa`, slot_meta `pos`, bench `bats` /
    `pos` / per-hand dicts), so a test can recompute the set off the artifact.

    n_withheld_by_floor counts pairs that pass every rule except the split-PA
    floor (rule 5). Options sort by delta, best first."""
    out: list = []
    withheld = 0
    for s in order or []:
        if _platoon_adj(s.get("bats"), hand) >= 0:                      # rule 1
            continue
        spos = ((slot_meta.get(s.get("key")) or {}).get("pos") or [None])[0]
        sv, spa = s.get("hem_plus_split"), s.get("split_pa")
        if spos is None or spos == "P" or sv is None:                   # rules 3, 4
            continue
        for b in bench:
            if _platoon_adj(b.get("bats"), hand) <= 0:                  # rule 2
                continue
            bpos = b.get("pos") or []
            if "P" in bpos or (spos != "DH" and spos not in bpos):      # rule 3
                continue
            bv = (b.get("hem_plus_split") or {}).get(hand)
            bpa = (b.get("split_pa") or {}).get(hand)
            if bv is None:                                              # rule 4
                continue
            delta = bv - sv
            if delta < PLATOON_OPTION_MARGIN:                           # rule 6
                continue
            if ((spa or 0) < PLATOON_OPTION_MIN_SPLIT_PA
                    or (bpa or 0) < PLATOON_OPTION_MIN_SPLIT_PA):       # rule 5
                withheld += 1
                continue
            out.append({"starter_key": s.get("key"), "bench_key": b.get("key"),
                        "pos": spos,
                        "starter_split": sv, "starter_split_pa": spa,
                        "starter_bats": s.get("bats"),
                        "bench_split": bv, "bench_split_pa": bpa,
                        "bench_bats": b.get("bats"), "delta": delta})
    out.sort(key=lambda o: (-o["delta"], str(o["starter_key"]), str(o["bench_key"])))
    return out, withheld


def team_offense(team: str, hitters: list["Hitter"],
                 active_ids: Optional[frozenset] = None,
                 split_hem: Optional[dict] = None,
                 positions: Optional[dict] = None) -> dict:
    """Team offense aggregates. Offense+ is PA-weighted HEM+ (the offensive
    quality of the plate appearances the lineup takes). Also emits constructed
    batting orders vs RHP / LHP and a bench list (regulars beyond the nine).

    `active_ids` is the set of MLBAM ids on a current ACTIVE roster. When given,
    the CONSTRUCTED objects (orders, lineup, bench) are built only from players
    who can actually play today; the AGGREGATES are not touched.

    THAT SPLIT IS THE WHOLE DESIGN. A constructed batting order is a claim about
    tonight, so an injured player in it is simply wrong: Nick Kurtz was batting
    second for the Athletics on 434 plate appearances while out for the season,
    and 37 of 270 constructed slots league-wide were held by players not on an
    active roster. Offense+ is a claim about the season as played, where those
    434 plate appearances are real and belong. It also feeds betting_model and
    the leaderboard vintages the 600-game clock is accruing against, so
    re-basing it would be a model change wearing a display fix's clothes.

    None means the roster feed failed, and then NOTHING is filtered: an
    unreachable feed must leave the charts intact rather than empty them. A
    player with no readable mlbam is KEPT, never over-filtered.

    `positions` ({mlbam: {pos: innings}}, None when the fielding lens is down)
    only feeds the display siblings: bench `pos`, `slot_meta` and
    `platoon_options`. `orders`, `lineup` and every aggregate are built before
    it is read and never see it.
    """
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
    # THE CONSTRUCTED NINE IS TODAY'S QUESTION, so it runs on the active roster.
    # Everything above this line stays on the full pool: those aggregates describe
    # the season as played.
    avail = scored if active_ids is None else [
        h for h in scored
        if h.mlbam is None or int(h.mlbam) in active_ids]      # unreadable id -> keep
    out["n_off_roster_dropped"] = len(scored) - len(avail)
    if not avail:
        # every bat filtered out (a club mid-teardown, or a feed that returned a
        # partial roster). An empty nine is worse than an unfiltered one.
        avail = scored
        out["n_off_roster_dropped"] = 0
        out["roster_filter_skipped"] = "no active-roster bat matched; left unfiltered"
    ladder = sorted(avail, key=lambda h: (-(h.hem_plus or 0), -h.pa))
    out["lineup"] = [{"tier": h.tier, "key": h.key, "name": h.name, "bats": h.bats,
                      "hem_plus": h.hem_plus, "pa": int(h.pa)} for h in ladder]
    # Constructed orders vs each pitcher hand (falls back to overall HEM+ when the
    # bat side is unknown; the toggle still re-lenses platoon advantage + stagger).
    orders = {"vr": build_batting_order(avail, "R", split_hem),
              "vl": build_batting_order(avail, "L", split_hem)}
    out["orders"] = {k: v for k, v in orders.items() if v}
    # Bench bats: the regulars who did NOT make the everyday nine (by PA), the
    # next hitters by playing time, so the chart can show them clearly separated.
    # A pitcher is never a bench bat (MLB's own position label, not a guess).
    everyday = {r["key"] for r in (orders.get("vr") or [])}
    bench = [h for h in sorted(avail, key=lambda h: -(h.pa or 0))
             if h.key not in everyday and not is_pitcher(h)][:BENCH_MAX]
    out["bench"] = [bench_row(h, split_hem, positions) for h in bench]
    # Display siblings of `orders`. Nothing below writes into a slot.
    by_key = {h.key: h for h in avail}
    slot_keys = {r["key"] for side in out["orders"].values() for r in side}
    out["slot_meta"] = {k: {"mlbam": by_key[k].mlbam,
                            "pos": player_positions(by_key[k], positions)}
                        for k in sorted(slot_keys) if k in by_key}
    opts: dict = {"vl": [], "vr": [], "n_withheld": {"vl": 0, "vr": 0}}
    if positions is not None:
        for side, hand in (("vl", "L"), ("vr", "R")):
            opts[side], opts["n_withheld"][side] = platoon_options(
                out["orders"].get(side), out["bench"], out["slot_meta"], hand)
    out["platoon_options"] = opts
    # Would-be regulars the active filter dropped: the club's top nine by season
    # PA over the UNFILTERED pool (the rule that picks the everyday nine) who are
    # not in `avail`. Status labels are stamped by the exporter, which holds the
    # roster caches; this module does no I/O.
    avail_keys = {h.key for h in avail}
    regulars = sorted([h for h in scored if not is_pitcher(h)], key=lambda h: -(h.pa or 0))[:9]
    out["regulars_out"] = [{"key": h.key, "mlbam": h.mlbam, "name": h.name,
                            "bats": h.bats, "hem_plus": h.hem_plus, "pa": int(h.pa)}
                           for h in regulars if h.key not in avail_keys]
    return out


def build_split_hem(platoon_counts: Optional[dict], pool: Pool,
                    hitters: Optional[Iterable["Hitter"]] = None) -> Optional[dict]:
    """{mlbam: {'L': hem_vs_lhp, 'R': hem_vs_rhp, 'pa': {...}}} from raw split
    lines, estimator platoon_ratio_v1 on the season `pool` (see split_hem_pair).

    `platoon_counts` is {'L': {mlbam: counts}, 'R': {mlbam: counts}} as
    hitter_export.load_platoon_splits returns it; `hitters` are the scored season
    Hitters, which carry the level (woba_skill) and the bat side. None in, None
    out: an absent feed must stay distinguishable from a feed that resolved
    nobody, which is the load_bat_side posture and the reason that outage was
    caught at all."""
    if not platoon_counts:
        return None
    by_id = {int(h.mlbam): h for h in (hitters or []) if h.mlbam is not None}
    mu = league_platoon_ratios(platoon_counts,
                               {m: h.bats for m, h in by_id.items() if h.bats})
    left, right = platoon_counts.get("L") or {}, platoon_counts.get("R") or {}
    out: dict = {}
    for mid in sorted({int(m) for m in left} | {int(m) for m in right}):
        cl = left.get(mid, left.get(str(mid)))
        cr = right.get(mid, right.get(str(mid)))
        vals = split_hem_pair(by_id.get(mid), cl, cr, pool, mu)
        for hand, counts in (("L", cl), ("R", cr)):
            v = vals.get(hand)
            if v is None:
                continue
            row = out.setdefault(mid, {"pa": {}})
            row[hand] = v
            try:
                row["pa"][hand] = int(float(counts.get("plateAppearances") or 0))
            except (TypeError, ValueError):
                pass
    return out or None


def score_pool(hitters: list["Hitter"],
               active_ids: Optional[frozenset] = None,
               platoon_counts: Optional[dict] = None,
               positions: Optional[dict] = None) -> dict:
    """End to end: derive rates, build the pool, score HEM+, assign tiers, roll up
    team offenses. Returns 'hitters', 'teams', 'pool'. Pure - callers supply the
    data.

    `platoon_counts` (optional) carries each hitter's per-hand counting line; the
    per-hand HEM+ is scored HERE because it must use this run's pool anchor, and
    the pool does not exist until this function builds it.

    `positions` (optional, {mlbam: {pos: innings}}) feeds only the lineup-card
    display siblings (see team_offense)."""
    pool_input = [h for h in hitters if _woba_denom(h) > 0]
    for h in pool_input:
        derive_rates(h)
    pool = build_pool(pool_input)
    for h in pool_input:
        hem_plus(h, pool)
        h.qualified = _woba_denom(h) >= QUALIFY_MIN_PA
    assign_tiers(pool_input)

    split_hem = build_split_hem(platoon_counts, pool, pool_input)

    by_team: dict[str, list["Hitter"]] = {}
    for h in pool_input:
        by_team.setdefault(h.team or "", []).append(h)
    teams = []
    for team, hs in by_team.items():
        if team:
            teams.append(team_offense(team, hs, active_ids, split_hem, positions))
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
        "bats": h.bats,
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
