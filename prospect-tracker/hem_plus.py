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


def split_hem_plus(counts: dict | None, pool: Pool) -> Optional[int]:
    """HEM+ for ONE hand, from that hand's own counting line, on the SAME pool.

    WHY THIS EXISTS (audit finding F08-02, 2026-09-10). `_platoon_adj` says so in
    its own docstring: it re-lenses the ORDER vs L / vs R and never the published
    number. So both hand-labelled orders carried each hitter's SEASON hem_plus,
    and a PA-weighted mean over a permutation of the same nine bats is
    permutation-invariant. Measured on the served board: the batSide lens was up
    (737 of 737 hitters stamped), the two orders were genuinely different
    permutations (0 of 30 teams identical), and `off_vs_lhp` and `off_vs_rhp`
    were still bit-identical on all 30 clubs, across all 480 captured rows. The
    pre-registered handedness gate would have measured its own twin.

    THE ANCHOR IS THE SEASON POOL, ON PURPOSE, AND IT IS THE WHOLE POINT. Scoring
    each hand against its own hand-specific pool would re-centre both to 100 and
    delete the league-wide platoon effect, which is the signal. Anchoring both to
    the one season pool makes a lefty's vs-LHP number read BELOW his season HEM+
    by the amount he actually loses, and makes the two hands comparable.

    Shrinkage needs no new constant: the split denominator is smaller, so the
    existing per-component reliability constants regress a thin split harder,
    which is the correct behaviour and is why this reuses `hem_plus` verbatim
    rather than re-deriving the arithmetic. Returns None on an unusable line,
    never a fabricated value."""
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
    if _woba_denom(tmp) <= 0:
        return None
    return hem_plus(tmp, pool)


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
#: Split PA floor, both players, against the hand. Below it the shrunk split is
#: mostly the pool anchor (the data weight at 30 wOBA-PA is 0.20 on walks and
#: 0.03 on doubles), and 100 PA is the page's existing thin-sample floor. The
#: card dims any per-hand number under this same floor.
PLATOON_OPTION_MIN_SPLIT_PA = 100
#: HEM+ points the bench split must clear the starter's by. The measured spread of
#: (vs-LHP minus vs-RHP HEM+) within a bat side and sample band is 13.5 to 22.3,
#: an upper bound on the noise in a difference of two splits; 15 is its low end.
PLATOON_OPTION_MARGIN = 15
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


def build_split_hem(platoon_counts: Optional[dict], pool: Pool) -> Optional[dict]:
    """{mlbam: {'L': hem_vs_lhp, 'R': hem_vs_rhp, 'pa': {...}}} from raw split
    lines, scored on the season `pool` (see split_hem_plus for why that anchor).

    `platoon_counts` is {'L': {mlbam: counts}, 'R': {mlbam: counts}} as
    hitter_export.load_platoon_splits returns it. None in, None out: an absent
    feed must stay distinguishable from a feed that resolved nobody, which is
    the load_bat_side posture and the reason that outage was caught at all."""
    if not platoon_counts:
        return None
    out: dict = {}
    for hand in ("L", "R"):
        for mid, counts in (platoon_counts.get(hand) or {}).items():
            v = split_hem_plus(counts, pool)
            if v is None:
                continue
            row = out.setdefault(int(mid), {"pa": {}})
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

    split_hem = build_split_hem(platoon_counts, pool)

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
