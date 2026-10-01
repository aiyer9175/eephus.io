# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fantasy_scoring.py — canonical fantasy scoring engines for the /fantasy/ module.

Single source of truth for how a projected/observed counting-stat line becomes a
fantasy value, across four Ottoneu systems (https://ottoneu.fangraphs.com/scoringoptions):

  Points (per-player total = Σ stat·weight):
    * FanGraphs Points (FGP)  — the DEFAULT
    * SABR Points             — FIP-flavored (no hit penalty; different IP/HR)
  Categories (league-relative z-score valuation; no absolute per-player total):
    * Old School 5x5          — AVG HR RBI SB R  /  W SV ERA WHIP K
    * Ottoneu Classic 4x4     — OBP SLG HR R      /  ERA WHIP HR9 K

The POINTS weight tables are exported verbatim to the client (via
`points_weight_tables()` baked into data/fantasy.json) so the in-browser scoring
selector recomputes the SAME numbers on the fly — this module is the authority
and the JS is a mirror. Hitting weights are identical across FGP and SABR; only
pitching differs. Values cross-checked against the official scoring page, two
FanGraphs how-scoring articles, and the Ottoneu community forum
(single = +4.6, HR = +14.0 net; FGP pitcher IP = +7.4, SABR IP = +5.0).

Stat-key contract (per-player dict, counting totals unless noted):
  Hitters: ab, h (TOTAL hits incl. XBH), double, triple, hr, bb, hbp, sb, cs;
           rate/PT fields for roto: pa, avg, obp, slg
  Pitchers: ip (TRUE innings = outs/3, NOT 6.1-notation), k, h, bb, hbp, hr,
           sv, hld; rate/PT fields for roto: era, whip, hr9, w, sv, k
Missing keys score 0 (e.g. projections without SV/HLD simply omit those terms).
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping

# ---------------------------------------------------------------------------
# POINTS systems
# ---------------------------------------------------------------------------
# Hitting is IDENTICAL in FGP and SABR. Ottoneu's native table is base-H plus
# INCREMENTAL bonuses for extra-base hits, so `h` is total hits and double/
# triple/hr stack on top of it. A single therefore nets h - ab = 5.6 - 1.0 = 4.6.
_HITTER_POINTS: dict[str, float] = {
    "ab": -1.0,      # charged on every at-bat (not on BB/HBP)
    "h": 5.6,        # every hit (base)
    "double": 2.9,   # additional, on top of H
    "triple": 5.7,   # additional, on top of H
    "hr": 9.4,       # additional, on top of H
    "bb": 3.0,
    "hbp": 3.0,
    "sb": 1.9,
    "cs": -2.8,
}

# Pitching DIFFERS between the two systems (IP, H, HR). SABR is FIP-flavored:
# it does not score hits at all.
_PITCHER_POINTS_FGP: dict[str, float] = {
    "ip": 7.4,       # per TRUE inning (accrued per out: outs/3 · 7.4)
    "k": 2.0,
    "h": -2.6,
    "bb": -3.0,
    "hbp": -3.0,
    "hr": -12.3,
    "sv": 5.0,
    "hld": 4.0,
}
_PITCHER_POINTS_SABR: dict[str, float] = {
    "ip": 5.0,
    "k": 2.0,
    # no "h" term — SABR is FIP-based
    "bb": -3.0,
    "hbp": -3.0,
    "hr": -13.0,
    "sv": 5.0,
    "hld": 4.0,
}

POINTS_SYSTEMS = ("fgp", "sabr")


def points_weight_tables() -> dict:
    """Serializable weight tables for the client (baked into data/fantasy.json).

    The in-browser selector applies these exact weights so its per-player totals
    match this module. Hitting is shared; only pitching swaps per system."""
    return {
        "hitter": dict(_HITTER_POINTS),          # shared by fgp + sabr
        "pitcher": {
            "fgp": dict(_PITCHER_POINTS_FGP),
            "sabr": dict(_PITCHER_POINTS_SABR),
        },
    }


def score_points(stats: Mapping[str, float], system: str = "fgp", side: str = "hit") -> float:
    """Projected/observed fantasy points for one player.

    system ∈ {"fgp","sabr"}; side ∈ {"hit","pit"}. Missing stat keys score 0.
    `ip` must be TRUE innings (outs/3); use `ip_from_outs` if you hold outs."""
    system = (system or "fgp").lower()
    if system not in POINTS_SYSTEMS:
        raise ValueError(f"unknown points system {system!r}; expected one of {POINTS_SYSTEMS}")
    if side in ("hit", "hitter", "h"):
        weights = _HITTER_POINTS
    elif side in ("pit", "pitcher", "p"):
        weights = _PITCHER_POINTS_FGP if system == "fgp" else _PITCHER_POINTS_SABR
    else:
        raise ValueError(f"unknown side {side!r}; expected 'hit' or 'pit'")
    return round(sum(float(stats.get(k, 0) or 0) * w for k, w in weights.items()), 2)


def ip_from_outs(outs: float) -> float:
    """True innings from an out count (Ottoneu scores IP per out)."""
    return (float(outs) or 0.0) / 3.0


def ip_from_decimal_thirds(ip_notation: float) -> float:
    """Convert 6.1/6.2-notation (6⅓ / 6⅔) to true innings (6.333/6.667)."""
    whole = int(ip_notation)
    frac = round(ip_notation - whole, 1)
    thirds = {0.0: 0.0, 0.1: 1 / 3, 0.2: 2 / 3}.get(frac)
    if thirds is None:  # already a true-innings decimal — pass through
        return float(ip_notation)
    return whole + thirds


# ---------------------------------------------------------------------------
# CATEGORY (rotisserie) systems — league-relative z-score valuation
# ---------------------------------------------------------------------------
# Roto has no absolute per-player "points"; value is how much a player moves the
# standings in each category relative to the player pool. We rank by summed
# per-category z-scores. Counting cats use the raw projected total; RATE cats use
# a mass-weighted deviation (rate − pool_rate)·PT so a small-sample rate can't
# dominate, with the sign flipped for lower-is-better cats (ERA/WHIP/HR9).
ROTO_CATS: dict[str, dict[str, tuple[str, ...]]] = {
    "5x5": {"hit": ("avg", "hr", "rbi", "sb", "r"), "pit": ("w", "sv", "era", "whip", "k")},
    "4x4": {"hit": ("obp", "slg", "hr", "r"),       "pit": ("era", "whip", "hr9", "k")},
}
_RATE_CATS = {"avg", "obp", "slg", "era", "whip", "hr9"}
_LOWER_BETTER = {"era", "whip", "hr9"}
_PT_KEY = {"hit": "pa", "pit": "ip"}


def _cat_raw(player: Mapping[str, float], cat: str, side: str,
             pool_mean_rate: float) -> float:
    """One player's raw contribution in `cat` (higher = better, sign-corrected)."""
    if cat in _RATE_CATS:
        pt = float(player.get(_PT_KEY[side], 0) or 0)
        dev = float(player.get(cat, 0) or 0) - pool_mean_rate
        if cat in _LOWER_BETTER:
            dev = -dev                     # low ERA/WHIP/HR9 = good
        return dev * pt                    # mass-weighted so PT matters
    return float(player.get(cat, 0) or 0)  # counting cat: raw total


def roto_params(pool: Iterable[Mapping], fmt: str = "5x5", side: str = "hit") -> dict | None:
    """The pool constants one side of a roto format is z-scored against:
    {"fmt", "side", "cats", "rate_means", "mu", "sd"}. None for an empty pool.

    Split out of roto_valuations (2026-10-01) so a line that is NOT in the pool
    (a prospect's projected season, on the /fantasy/ Fantasy Rank) can be
    valued on the same scale as the pool without joining it."""
    fmt = (fmt or "5x5").lower()
    if fmt not in ROTO_CATS:
        raise ValueError(f"unknown roto format {fmt!r}; expected one of {tuple(ROTO_CATS)}")
    side = "hit" if side in ("hit", "hitter", "h") else "pit"
    cats = ROTO_CATS[fmt][side]
    players = [p for p in pool]
    if not players:
        return None

    # Pool mean of each RATE cat (PT-weighted so it's the real league rate).
    pt_key = _PT_KEY[side]
    rate_means: dict[str, float] = {}
    for cat in cats:
        if cat in _RATE_CATS:
            num = sum(float(p.get(cat, 0) or 0) * float(p.get(pt_key, 0) or 0) for p in players)
            den = sum(float(p.get(pt_key, 0) or 0) for p in players)
            rate_means[cat] = (num / den) if den else 0.0

    mu: dict[str, float] = {}
    sd: dict[str, float] = {}
    for cat in cats:
        xs = [_cat_raw(p, cat, side, rate_means.get(cat, 0.0)) for p in players]
        m = sum(xs) / len(xs)
        mu[cat] = m
        sd[cat] = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
    return {"fmt": fmt, "side": side, "cats": list(cats), "rate_means": rate_means,
            "mu": mu, "sd": sd}


def roto_value(player: Mapping, params: Mapping) -> tuple[float, dict]:
    """(summed z, {cat: z}) for one line against roto_params' pool constants.
    Unrounded; roto_valuations rounds for its own output."""
    side = params["side"]
    per = {}
    for cat in params["cats"]:
        x = _cat_raw(player, cat, side, (params.get("rate_means") or {}).get(cat, 0.0))
        s = params["sd"][cat]
        per[cat] = ((x - params["mu"][cat]) / s) if s else 0.0
    return sum(per.values()), per


def roto_valuations(pool: Iterable[Mapping], fmt: str = "5x5", side: str = "hit") -> dict:
    """League-relative valuation for one side of a roto format.

    Returns {player_id: {"value": total_z, "cats": {cat: z}}} — higher value is
    better. `pool` items must carry an "id" plus the stat/PT keys the format's
    cats need. Value is only comparable WITHIN one side+pool (hitters vs hitters).
    """
    players = [p for p in pool]
    params = roto_params(players, fmt, side)
    if params is None:
        return {}
    out: dict = {}
    for p in players:
        _v, z = roto_value(p, params)
        per_cat = {cat: round(z[cat], 3) for cat in params["cats"]}
        out[p["id"]] = {"value": round(sum(per_cat.values()), 3), "cats": per_cat}
    return out


# Human-facing catalog for the client selector (default first).
SCORING_CATALOG = [
    {"id": "fgp",  "kind": "points", "label": "FanGraphs Points", "default": True},
    {"id": "sabr", "kind": "points", "label": "SABR Points"},
    {"id": "5x5",  "kind": "roto",   "label": "Old School (5x5)"},
    {"id": "4x4",  "kind": "roto",   "label": "Ottoneu Classic (4x4)"},
]
