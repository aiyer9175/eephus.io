"""Single source of truth for FV <-> WAR <-> $ conversions.

Anchors:
  * FV -> WAR ranges per the 2026 FanGraphs scouting primer
    (https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/).
    Hitter and pitcher ranges differ; we honor the split everywhere.
  * $/WAR per FanGraphs "What Are Teams Paying for a Win in Free Agency"
    (2026 edition). We use the article's NON-LINEAR 3-tier model
    (0-1 WAR / 1-2 WAR / 2+ WAR) rather than a flat rate, because the
    article's headline finding is that the star premium has roughly
    doubled from 2020-2023 to 2024-2026 -- a flat rate misprices both
    ends. Tier rates are a rolling 3-year average (2024-2026) to balance
    recency against single-year noise.
  * 6yr cost-controlled surplus = expected_war_6yr * $/WAR_tier - cost_basis
    where expected_war_6yr accounts for ramp-up (sub-peak debut/sophomore
    years) AND bust probability (per-FV success rate from industry
    research). Cost basis = 3yr pre-arb + 3yr arb (40/60/80 of FA value).

All downstream consumers (storage.py surplus calcs, mlb_trade_lookup.py
contract surplus, index.html trade audits + player cards + org tree
financial leaves) read FROM this module. To recompute the JSON+JS
snapshots after editing constants, run:

    python value_framework.py --emit-snapshots
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable

# =============================================================================
# CITATIONS
# =============================================================================
# Pinned so the snapshot files always carry provenance.
SOURCE_PRIMER_URL = "https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/"
SOURCE_DPW_URL    = "https://blogs.fangraphs.com/what-are-teams-paying-for-a-win-in-free-agency-2026-edition/"
FRAMEWORK_VERSION = "v1.0"          # bump when the formula or anchors change

# =============================================================================
# $/WAR -- non-linear 3-tier (rolling 3yr average 2024-2026)
# =============================================================================
# Raw per-year tier values reported in the 2026 edition + prior editions.
# We expose all 7 years so a different rolling window or anchor year can
# be computed at runtime via dollars_per_war_for_window().
_DPW_BY_YEAR: dict[int, dict[str, float]] = {
    # year -> {tier_label: $M/WAR}
    2020: {"0-1": 10.93, "1-2": 8.52, "2+": 11.99, "overall": 10.85},
    2021: {"0-1":  4.09, "1-2": 6.31, "2+":  7.22, "overall":  6.70},
    2022: {"0-1":  9.46, "1-2": 8.77, "2+": 12.15, "overall": 11.24},
    2023: {"0-1":  6.87, "1-2": 9.77, "2+": 10.81, "overall": 10.34},
    2024: {"0-1":  8.22, "1-2": 8.83, "2+": 14.13, "overall": 12.08},
    2025: {"0-1":  5.96, "1-2": 8.95, "2+": 13.91, "overall": 11.92},
    2026: {"0-1":  6.74, "1-2": 8.51, "2+": 12.84, "overall": 11.23},
}

# Default rolling window -- 3yr (2024-2026) per user spec. Smoother than
# single-year, more responsive than 7-yr. Override via the `window` arg
# on dollars_per_war_for_window().
DEFAULT_WINDOW_YEARS = (2024, 2025, 2026)


def dollars_per_war_for_window(
    window: tuple[int, ...] = DEFAULT_WINDOW_YEARS,
) -> dict[str, float]:
    """Average the per-year tier rates across `window`. Returns a dict
    with keys '0-1', '1-2', '2+', 'overall' all in $M/WAR."""
    if not window:
        raise ValueError("dollars_per_war_for_window: window must be non-empty")
    rows = [_DPW_BY_YEAR[y] for y in window if y in _DPW_BY_YEAR]
    if not rows:
        raise ValueError(f"dollars_per_war_for_window: no data for window {window}")
    out: dict[str, float] = {}
    for key in ("0-1", "1-2", "2+", "overall"):
        out[key] = round(sum(r[key] for r in rows) / len(rows), 3)
    return out


# Cache the default-window tiers for quick lookups.
_TIERS_DEFAULT = dollars_per_war_for_window()


def dollars_per_war(projected_war: float | None,
                    window: tuple[int, ...] = DEFAULT_WINDOW_YEARS,
                    ) -> float:
    """Look up the $M/WAR tier rate for a projected first-year WAR.

    Tier boundaries match the article: <1.0 -> low tier, 1.0-2.0 ->
    mid tier, >=2.0 -> star tier. None / negative WAR is treated as
    fringe (0-1 tier). Returns $M/WAR."""
    if projected_war is None:
        return _TIERS_DEFAULT["0-1"]
    war = float(projected_war)
    tiers = (_TIERS_DEFAULT if window == DEFAULT_WINDOW_YEARS
             else dollars_per_war_for_window(window))
    if war < 1.0:
        return tiers["0-1"]
    if war < 2.0:
        return tiers["1-2"]
    return tiers["2+"]


def dollars_per_war_flat(window: tuple[int, ...] = DEFAULT_WINDOW_YEARS) -> float:
    """Single overall $M/WAR for cases where tier-dispatching doesn't fit
    (portfolio aggregates, simple career-WAR x rate displays, etc)."""
    tiers = (_TIERS_DEFAULT if window == DEFAULT_WINDOW_YEARS
             else dollars_per_war_for_window(window))
    return tiers["overall"]


# =============================================================================
# FV -> WAR (from the FanGraphs scouting primer)
# =============================================================================
# Primer publishes (low, high) WAR ranges per FV grade, split by role.
# For valuation purposes we use the MIDPOINT as the peak-year projection.
# Grades the primer omits (20/25/35/65/75) are interpolated; 30 is the
# primer's "up & down" marker and gets a small negative value.
FV_GRADES = (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80)

_PRIMER_RANGE_HITTER = {
    # grade -> (low, high) peak WAR/yr, from the primer's hitter table
    40: (0.0, 0.7),
    45: (0.8, 1.5),
    50: (1.6, 2.4),
    55: (2.5, 3.3),
    60: (3.4, 4.9),
    70: (5.0, 7.0),
    80: (7.0, 9.0),   # primer says ">7.0", we cap at 9 for the midpoint
}

_PRIMER_RANGE_PITCHER = {
    40: (0.0, 0.9),
    45: (1.0, 1.7),
    50: (1.8, 2.5),
    55: (2.6, 3.4),
    60: (3.5, 4.9),
    70: (5.0, 7.0),
    80: (7.0, 9.0),
}


def _midpoint(lo: float, hi: float) -> float:
    return round((lo + hi) / 2.0, 2)


def _build_fv_to_war(primer_ranges: dict[int, tuple[float, float]]) -> dict[int, float]:
    """Build a complete FV -> peak-WAR table from the primer ranges by
    interpolating the missing grades (25/35/65/75) and tail-anchoring
    20/30 below the primer floor."""
    out: dict[int, float] = {}
    out[20] = 0.0
    out[25] = 0.0
    out[30] = -0.1
    out[35] = 0.0
    for g in (40, 45, 50, 55, 60, 70, 80):
        lo, hi = primer_ranges[g]
        out[g] = _midpoint(lo, hi)
    # Interpolated half-grades the primer skips:
    out[65] = round((out[60] + out[70]) / 2.0, 2)
    out[75] = round((out[70] + out[80]) / 2.0, 2)
    return out


FV_TO_WAR_HITTER  = _build_fv_to_war(_PRIMER_RANGE_HITTER)
FV_TO_WAR_PITCHER = _build_fv_to_war(_PRIMER_RANGE_PITCHER)


def fv_to_war_peak(fv: float | None, is_pitcher: bool) -> float | None:
    """FV grade -> projected peak WAR/yr. Linear-interpolated between
    5-pt anchors so half-grades (e.g. FV 47.5) get sane values.

    Returns None on missing FV. Negative WAR clamped at -0.5 for very
    low grades."""
    if fv is None:
        return None
    try:
        f = float(fv)
    except (TypeError, ValueError):
        return None
    table = FV_TO_WAR_PITCHER if is_pitcher else FV_TO_WAR_HITTER
    if f >= 80:
        return table[80]
    if f <= 20:
        return max(-0.5, table[20])
    lo = int(f // 5) * 5
    hi = lo + 5
    t = (f - lo) / 5.0
    return round(table[lo] * (1 - t) + table[hi] * t, 2)


# =============================================================================
# Bust probability -- P(MLB regular | FV at draft/sign time)
# =============================================================================
# Industry-standard prospect-success rates, anchored to Sickels (2002-2012),
# McDaniel/Longenhagen (2014-2020) and recent BA primer commentary. Defines
# "MLB regular" as accumulating >=2 career WAR. Pitchers run ~5-10pp lower
# at each grade due to TJ + role-conversion risk. These are exposed as a
# constant dict so future calibration from our own grad data can override
# individual cells without rewriting the framework.
BUST_PROB_HITTER = {
    20: 0.01, 25: 0.02, 30: 0.03, 35: 0.05, 40: 0.10,
    45: 0.20, 50: 0.32, 55: 0.45, 60: 0.62, 65: 0.72,
    70: 0.80, 75: 0.87, 80: 0.92,
}
BUST_PROB_PITCHER = {
    20: 0.01, 25: 0.02, 30: 0.03, 35: 0.04, 40: 0.08,
    45: 0.15, 50: 0.25, 55: 0.36, 60: 0.50, 65: 0.60,
    70: 0.70, 75: 0.78, 80: 0.85,
}


def success_prob(fv: float | None, is_pitcher: bool) -> float:
    """P(MLB regular) for a prospect at a given FV grade. Linear-interp
    between 5-pt anchors. Floor 0.005, cap 0.95."""
    if fv is None:
        return 0.0
    try:
        f = float(fv)
    except (TypeError, ValueError):
        return 0.0
    table = BUST_PROB_PITCHER if is_pitcher else BUST_PROB_HITTER
    if f >= 80:
        return table[80]
    if f <= 20:
        return table[20]
    lo = int(f // 5) * 5
    hi = lo + 5
    t = (f - lo) / 5.0
    return round(max(0.005, min(0.95, table[lo] * (1 - t) + table[hi] * t)), 3)


# =============================================================================
# Surplus ramp + cost-basis factors
# =============================================================================
# Avg WAR / peak WAR over the 6yr cost-controlled window. Hitters typically
# reach peak in year 3-4 and decline modestly by year 6; pitchers face
# more in-window injury attrition. Tuned so a top prospect's expected
# 6yr WAR roughly matches the primer's "5-7 WAR/yr at peak" framing.
RAMP_FACTOR_HITTER  = 0.78
RAMP_FACTOR_PITCHER = 0.72

# Pre-arb fixed cost = 3yr * MLB minimum (~$0.78M per CBA, rounded).
PRE_ARB_TOTAL_MM = 2.4

# Avg arb-year payout as a % of equivalent FA value. Arb1 ~40%, arb2 ~60%,
# arb3 ~80%; we use 0.6 as a single avg across the 3yr arb window.
ARB_PCT_OF_FA = 0.60


# =============================================================================
# Position multipliers
# =============================================================================
# Calibrated from cached Spotrac team-contract data via
# tools/calibrate_position_mults.py. The script computes per-position
# median AAV across all current MLB contracts (n=443 with AAV >=$1M)
# and normalizes against the overall median ($7.25M). Calibration output
# is written to data/position_multipliers_calibration_raw.json as a
# RESEARCH artifact -- not auto-loaded -- because the raw values are
# confounded by star concentration (a position with 1-3 superstars on
# huge deals reads as a "scarcity premium" when it's really a star
# bias). The defaults below were curated from that calibration:
#
#   * VALIDATED by calibration (used as-is):
#     - RP        0.552 (calibrated)  -- matches the "fungibility" prior
#     - CF        1.052 (calibrated)  -- modest up-the-middle premium
#     - OF        0.621 (calibrated)  -- generic OF = bench/reserve
#   * RAISED from calibration (calibration was star-driven):
#     - C        was 0.828 raw; used 0.95 (catchers genuinely underpaid
#                but small sample skews low; partial pull toward prior)
#     - 1B       was 0.552 raw; used 0.70 (1B is clearly discounted but
#                low-AAV sample skews toward replacement-level)
#     - 2B       was 0.762 raw; used 0.88
#   * REJECTED from calibration (star-driven, not scarcity):
#     - 3B, RF, LF, DH all read 1.7-2.1 in calibration due to
#       Devers/Bregman/Soto/Judge/Ohtani; we use defensible scarcity
#       priors instead.
#   * UNCHANGED from prior:
#     - SS        1.18 (up-the-middle premium; calibration also high)
#     - SP/RHP    1.00 (anchor; we already differentiate SP/RP via the
#                  WAR-tier $/WAR rate, no need to double-count)
#
# To promote raw calibration values into production wholesale, write a
# data/position_multipliers.json file with a `{"multipliers": {...}}`
# shape. Anything in that file overrides these defaults.
_POSITION_MULT_DEFAULTS: dict[str, float] = {
    "C":    0.95,
    "SS":   1.18,
    "2B":   0.88,
    "3B":   0.95,
    "1B":   0.70,
    "CF":   1.05,
    "LF":   0.93,
    "RF":   0.95,
    "OF":   0.65,
    "DH":   0.78,
    # Pitchers
    "SP":   1.00,
    "RHP":  1.00,
    "LHP":  1.04,
    "RP":   0.55,
    "MIRP": 0.75,
    "SIRP": 0.65,
    # Two-way
    "TWP":  1.18,
}

_PITCHER_POS_RE = re.compile(r"^(RHP|LHP|SP|RP|MIRP|SIRP|P)$")


def _load_position_mult_overrides() -> dict[str, float]:
    """Read the calibrated multipliers from data/position_multipliers.json
    if present. Returns {} when the file is missing or malformed."""
    here = Path(__file__).resolve().parent
    fp = here / "data" / "position_multipliers.json"
    if not fp.exists():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    mults = data.get("multipliers") if isinstance(data, dict) else None
    return {k: float(v) for k, v in mults.items()} if isinstance(mults, dict) else {}


def position_multiplier(position: str | None) -> float:
    """Position scarcity multiplier. Reads calibrated overrides if a
    data/position_multipliers.json was generated, else falls back to
    v1 reasoned defaults. Unknown positions return 1.0."""
    if not position:
        return 1.0
    overrides = _load_position_mult_overrides()
    table = {**_POSITION_MULT_DEFAULTS, **overrides}
    primary = str(position).split("/")[0].strip().upper()
    return table.get(primary, 1.0)


def is_pitcher_position(position: str | None) -> bool:
    """Pure-name dispatch -- 'RHP' / 'LHP' / 'SP' / 'RP' / 'MIRP' / 'SIRP'
    plus the bare 'P' all read as pitcher. Hyphenated multi-positions
    (e.g. 'SS/2B') use the primary."""
    if not position:
        return False
    primary = str(position).split("/")[0].strip().upper()
    return bool(_PITCHER_POS_RE.match(primary))


# =============================================================================
# Core valuation: surplus_value_mm
# =============================================================================
def surplus_value_mm(
    fv: float | None,
    is_pitcher: bool,
    position: str | None = None,
    *,
    window: tuple[int, ...] = DEFAULT_WINDOW_YEARS,
    apply_position_mult: bool = True,
) -> float | None:
    """6yr cost-controlled surplus value ($M) for a prospect at FV.

    Decomposition (every factor exposed via a named constant above):
        expected_war_6yr = WAR_peak * 6 * ramp * p_success
        gross_value      = expected_war_6yr * $/WAR_tier(WAR_peak)
        arb_cost         = 3 * WAR_peak * $/WAR_tier * ARB_PCT * ramp * p_success
        cost_basis       = PRE_ARB_TOTAL_MM + arb_cost
        surplus          = (gross_value - cost_basis) * position_mult

    Returns None when FV is missing or unparseable. Negative-surplus
    prospects (where arb cost exceeds expected output -- typical for
    FV 40 with low p_success * low WAR) are clamped to a $0.3M floor
    since even an org-filler 40 carries some optionality / trade value.
    """
    war_peak = fv_to_war_peak(fv, is_pitcher)
    if war_peak is None:
        return None
    if war_peak <= 0:
        # FV 20-30 -- no cost-controlled MLB value to model.
        return 0.3
    p = success_prob(fv, is_pitcher)
    ramp = RAMP_FACTOR_PITCHER if is_pitcher else RAMP_FACTOR_HITTER
    rate = dollars_per_war(war_peak, window=window)

    expected_war_6yr = war_peak * 6.0 * ramp * p
    gross = expected_war_6yr * rate
    arb_cost = 3.0 * war_peak * rate * ARB_PCT_OF_FA * ramp * p
    cost_basis = PRE_ARB_TOTAL_MM + arb_cost

    surplus = gross - cost_basis
    if apply_position_mult:
        surplus *= position_multiplier(position)

    return round(max(0.3, surplus), 1)


def dollars_per_fv(
    fv: float | None,
    is_pitcher: bool,
    position: str | None = None,
    *,
    window: tuple[int, ...] = DEFAULT_WINDOW_YEARS,
) -> float | None:
    """$M of cost-controlled surplus per FV-point. Useful for portfolio
    efficiency metrics (draft pool $/FV, org-tree value-per-FV leaf).

    Computed as surplus_value_mm(fv) / fv. Returns None for FV <= 0 or
    missing FV."""
    if fv is None:
        return None
    try:
        f = float(fv)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    sv = surplus_value_mm(fv, is_pitcher, position, window=window)
    if sv is None:
        return None
    return round(sv / f, 3)


# =============================================================================
# Career-WAR -> $M (for MLB veterans valued via realized career WAR)
# =============================================================================
def career_war_value_mm(career_war: float | None,
                        window: tuple[int, ...] = DEFAULT_WINDOW_YEARS,
                        ) -> float | None:
    """Convert realized career WAR to $M using the overall $/WAR rate
    (NOT the tiered one -- career WAR is an aggregate across many
    seasons at varying tiers, so the overall mean is the right blend).

    Returns None for missing / negative career WAR."""
    if career_war is None:
        return None
    try:
        cw = float(career_war)
    except (TypeError, ValueError):
        return None
    if cw <= 0:
        return None
    return round(cw * dollars_per_war_flat(window=window), 2)


# =============================================================================
# Snapshot emitters (consumed by frontend)
# =============================================================================
def build_snapshot(window: tuple[int, ...] = DEFAULT_WINDOW_YEARS) -> dict:
    """Build the full JSON snapshot for frontend consumption. Includes
    everything index.html needs to do its own surplus/dollar calcs
    without re-implementing the formula."""
    tiers = dollars_per_war_for_window(window)
    # Precompute surplus tables (one row per FV grade, hitter + pitcher,
    # at the default DH/CF/SP positions so the frontend can grab a base
    # and apply its own position multiplier).
    surplus_table_hitter: dict[str, float] = {}
    surplus_table_pitcher: dict[str, float] = {}
    for g in FV_GRADES:
        sh = surplus_value_mm(g, is_pitcher=False, position=None,
                              window=window, apply_position_mult=False)
        sp = surplus_value_mm(g, is_pitcher=True, position=None,
                              window=window, apply_position_mult=False)
        if sh is not None:
            surplus_table_hitter[str(g)] = sh
        if sp is not None:
            surplus_table_pitcher[str(g)] = sp
    return {
        "version":        FRAMEWORK_VERSION,
        "window":         list(window),
        "sources": {
            "primer":         SOURCE_PRIMER_URL,
            "dollars_per_war": SOURCE_DPW_URL,
        },
        "dollars_per_war": {
            "tiers":   tiers,         # {"0-1", "1-2", "2+", "overall"}
            # JSON has no int keys, so stringify upfront for parity.
            "by_year": {str(k): v for k, v in _DPW_BY_YEAR.items()},
        },
        "fv_to_war_peak": {
            "hitter":  {str(k): v for k, v in FV_TO_WAR_HITTER.items()},
            "pitcher": {str(k): v for k, v in FV_TO_WAR_PITCHER.items()},
        },
        "bust_prob": {
            "hitter":  {str(k): v for k, v in BUST_PROB_HITTER.items()},
            "pitcher": {str(k): v for k, v in BUST_PROB_PITCHER.items()},
        },
        "surplus_value_mm": {
            "hitter":  surplus_table_hitter,
            "pitcher": surplus_table_pitcher,
        },
        "position_multipliers": {
            **_POSITION_MULT_DEFAULTS,
            **_load_position_mult_overrides(),
        },
        "ramp_factor": {
            "hitter":  RAMP_FACTOR_HITTER,
            "pitcher": RAMP_FACTOR_PITCHER,
        },
        "cost_basis": {
            "pre_arb_total_mm": PRE_ARB_TOTAL_MM,
            "arb_pct_of_fa":    ARB_PCT_OF_FA,
        },
    }


def emit_snapshots(out_dir: Path | None = None) -> tuple[Path, Path]:
    """Write the JSON snapshot + a JS sidecar to data/. The JS file
    assigns the snapshot to window.VALUE_FRAMEWORK so a plain <script>
    tag in index.html exposes it synchronously with no fetch."""
    out_dir = out_dir or (Path(__file__).resolve().parent / "data")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = build_snapshot()
    json_path = out_dir / "value_framework.json"
    json_path.write_text(json.dumps(snap, indent=2, sort_keys=True),
                         encoding="utf-8")
    js_payload = ("// AUTO-GENERATED by value_framework.py -- do not edit.\n"
                  "// Regenerate via: python value_framework.py --emit-snapshots\n"
                  f"window.VALUE_FRAMEWORK = {json.dumps(snap, indent=2, sort_keys=True)};\n")
    js_path = out_dir / "value_framework.js"
    js_path.write_text(js_payload, encoding="utf-8")
    return (json_path, js_path)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit-snapshots", action="store_true",
                    help="Write data/value_framework.{json,js}")
    ap.add_argument("--print-table", action="store_true",
                    help="Print the surplus table to stdout")
    args = ap.parse_args()
    if args.emit_snapshots:
        jp, jsp = emit_snapshots()
        print(f"wrote {jp}")
        print(f"wrote {jsp}")
    if args.print_table:
        print(f"\n$/WAR tiers (window {DEFAULT_WINDOW_YEARS}):")
        for k, v in dollars_per_war_for_window().items():
            print(f"  {k:>8}: ${v:>5.2f}M")
        print(f"\nFV -> 6yr surplus ($M), pre-position multiplier:")
        print(f"  {'FV':>4} {'hit_WAR':>8} {'hit_p':>6} {'hit_surp':>10} "
              f"{'pit_WAR':>8} {'pit_p':>6} {'pit_surp':>10}")
        for g in FV_GRADES:
            hw = fv_to_war_peak(g, False)
            pw = fv_to_war_peak(g, True)
            hp = success_prob(g, False)
            pp = success_prob(g, True)
            hs = surplus_value_mm(g, False, None, apply_position_mult=False)
            ps = surplus_value_mm(g, True, None, apply_position_mult=False)
            print(f"  {g:>4} {hw:>8.2f} {hp:>6.2f} ${hs:>8.1f}M "
                  f"{pw:>8.2f} {pp:>6.2f} ${ps:>8.1f}M")
