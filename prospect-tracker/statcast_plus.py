# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Statcast+ composite — pool-anchored index summarizing each prospect's
tracked Statcast / zone signals.

v29 — Promoted from a JS-only on-the-fly computation to a server-side
attached field. The Python version is canonical: it gets cached on
each player payload as `statcast_plus` and is consumed by:
  - breakout flag (storage._compute_breakout_flag) as an alternative
    stat-only perf gate when scout-published indices are missing
  - ETA (eta.estimate_eta) as a ±0.25y modifier inside the perf-adj
    family
  - spotlights (spotlights._classify_movement) as a riser-boost
    driver + ordering tiebreak
  - farm-grade rollup (storage org_summary loop) as a per-org
    `statcast_quality` aggregate under the tree.dev_* branches

Both sides use the same definition so the badge the user sees on the
expanded-density row matches the gate that fired on the server.

Definition (mirrors the original JS):
  Hitters blend contact quality (EV / HH% / Barrel%) + zone discipline
  (Z-Contact%, -Whiff%, -Chase%).
  Pitchers blend pitch quality (top-pitch avg velocity) + induced
  swing-and-miss (Whiff%, Chase%) + contact suppression (-HH%, -Barrel%
  allowed).
Each component is z-scored against the side-matched active pool,
averaged, then rescaled so 100 = pool mean and one population stddev
moves the index 10 points (a 100 + 10z index, matching the RPS+/DvM+/
Stf+ suite; this is z-score scaling, not the ratio wRC+/OPS+ family
where a point is ~1 percent).

RELIABILITY, added 2026-08-07 (docs/SC_PLUS_RECALIBRATION_GATE.md ship 1).
Every component is empirical-Bayes shrunk toward its pool mean by its own
sample size, and a component whose sample is below its floor is dropped
rather than shrunk. Before this the composite took a full-magnitude
exit-velocity z off a ONE batted-ball sample, which is how the site
maximum came to be a reliever with 87 pitches and no batted-ball data
at all.

SCALE, same date (ship 2). The divisor is the composite's standard
deviation WITHIN the player's own contributing-component class, not one
number for the side. Averaging k correlated unit-z legs shrinks the
spread as k rises, so a player missing his batted-ball legs used to sit
on a scale 22% wider than a full-coverage player and the top of the
board selected for MISSING DATA rather than for talent (measured
6.6 vs 5.4 points per sigma on the hitter side). Conditioning the
divisor is what makes "10 points per standard deviation" true for every
player instead of true on average. It does NOT reweight the composite:
the legs keep equal weight.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any, Iterable


# Anchoring constants — match the JS implementation exactly so a badge
# label and the gate it fired through never disagree. 100 is the pool
# mean. v-arkmetric-audit (finding 6): harmonized to 10 points per stddev to
# match every other backend "+" index (RPS+/DvM+/Stf+/$DvM+ all use 100 + 10·z);
# SC+ was the lone metric on a 15-pt scale, so a SC+ 115 and a DvM+ 115 meant
# different things. Now one σ-per-point convention across the suite.
_SC_PLUS_ANCHOR = 100
_SC_PLUS_PER_SIGMA = 10

# Tier breakpoints for display. These finally MEAN what they say: before the
# 2026-08-07 re-standardization ≥110 held 6.3% of the pool, not a quintile.
# They have no code consumers today (grep is clean) and exist as the published
# reading of the scale.
SC_PLUS_TOP_QUINTILE = 110     # ≥110 = +1σ → top ~16% of pool
SC_PLUS_BOTTOM_QUINTILE = 90   # ≤90 = -1σ → bottom ~16%

# Which raw sample size backs each component, and the EB constants per family.
# Recipe and constants are the reverted 2026-07-29 C1 build, recorded at
# docs/efv-2026-07-29/GATED_CANDIDATES.md:14-44; they are not re-derived here.
_VOLUME_FAMILY = {
    "avg_ev": "bbe", "hard_hit_pct": "bbe", "barrel_pct": "bbe",
    "hh_inv": "bbe", "barrel_inv": "bbe",
    "z_contact": "pitches", "whiff_inv": "pitches", "chase_inv": "pitches",
    "whiff": "pitches", "chase": "pitches",
    "top_velo": "velo_n",
}
_SAMPLE_FLOOR = {"bbe": 10, "pitches": 25, "velo_n": 10}
_SHRINK_K = {"bbe": 50, "pitches": 100, "velo_n": 50}

# A coverage class thinner than this borrows the side-wide divisor: a scale
# estimated on a handful of rows is noisier than the bias it would remove.
_MIN_COVERAGE_CELL = 50

# Reserved keys inside a side pool. Component names never start with "__".
_SCALE_KEY = "__coverage_scale__"
_SCALE_DEFAULT_KEY = "__scale_default__"


def _zone_row(player: dict) -> dict | None:
    """Pick the freshest tracked zone-metrics split for a player.

    `zone_metrics` may live as either a single dict or as a row with a
    `.level_splits` array. The freshest split wins (largest pitch
    sample); current-level matches don't get any priority here since
    the breakout / ETA gates care about cumulative signal, not the
    current-level subset.
    """
    z = player.get("zone_metrics")
    if not z:
        return None
    splits = z.get("level_splits") if isinstance(z, dict) else None
    if splits:
        return max(splits, key=lambda s: (s.get("pitches") or 0)) if splits else None
    return z if isinstance(z, dict) and z else None


def _extract_hitter(player: dict) -> dict:
    sc = player.get("statcast_metrics") or {}
    cq = sc.get("contact_quality") or {}
    z = _zone_row(player) or {}
    return {
        "avg_ev":       cq.get("avg_ev"),
        "hard_hit_pct": cq.get("hard_hit_pct"),
        "barrel_pct":   cq.get("barrel_pct"),
        # Zone discipline — whiff/chase are inverted so "less is better"
        # rolls the same direction as the other components. The chase rate is
        # serialized as o_swing_pct on ZoneMetricRow (chase_pct never existed on
        # production rows, which silently killed this component); keep chase_pct
        # as a defensive fallback for any alternate payload shape.
        "z_contact":    z.get("z_contact_pct"),
        "whiff_inv":    -z["whiff_pct"] if z.get("whiff_pct") is not None else None,
        "chase_inv":    (-z["o_swing_pct"] if z.get("o_swing_pct") is not None
                         else (-z["chase_pct"] if z.get("chase_pct") is not None else None)),
    }


def _extract_pitcher(player: dict) -> dict:
    sc = player.get("statcast_metrics") or {}
    cq = sc.get("contact_quality") or {}
    pm = sc.get("pitch_movement") or {}
    summary = pm.get("pitch_summary") or []
    top = summary[0] if summary else {}
    z = _zone_row(player) or {}
    return {
        "top_velo":   top.get("avg_velo"),
        "whiff":      z.get("whiff_pct"),
        # o_swing_pct = the serialized chase rate (see _extract_hitter note).
        "chase":      (z.get("o_swing_pct") if z.get("o_swing_pct") is not None
                       else z.get("chase_pct")),
        # Contact-suppression components — both inverted so higher is
        # better, matching the rest of the pitcher mix.
        "hh_inv":     -cq["hard_hit_pct"] if cq.get("hard_hit_pct") is not None else None,
        "barrel_inv": -cq["barrel_pct"]   if cq.get("barrel_pct")   is not None else None,
    }


def _is_pitcher(player: dict) -> bool:
    """Side resolution mirrors the JS path: prefer statline.is_pitcher,
    fall back to sabermetrics.is_pitcher. Both fields are set by the
    earlier enrichment pass in storage.py."""
    sl = player.get("statline") or {}
    if "is_pitcher" in sl and sl["is_pitcher"] is not None:
        return bool(sl["is_pitcher"])
    sm = player.get("sabermetrics") or {}
    return bool(sm.get("is_pitcher"))


def _component_volumes(player: dict) -> dict:
    """Sample size behind each component family. Production rows carry all
    three on 100% of the rows that carry the component itself (measured
    2026-08-07: 0 missing of 1,717 contact / 3,582 zone / 876 velo), so a
    missing volume means a malformed or synthetic row, and such a component
    is dropped rather than trusted at full weight."""
    sc = player.get("statcast_metrics") or {}
    cq = sc.get("contact_quality") or {}
    z = _zone_row(player) or {}
    pm = sc.get("pitch_movement") or {}
    summary = pm.get("pitch_summary") or []
    top = summary[0] if summary else {}
    return {"bbe": cq.get("batted_balls"),
            "pitches": z.get("pitches"),
            "velo_n": top.get("count")}


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _shrunk(key: str, raw, vols: dict, prior) -> float | None:
    """EB-shrink one component toward the pool prior by its own sample size.
    None means the component does not enter the composite at all."""
    raw = _num(raw)
    if raw is None:
        return None
    fam = _VOLUME_FAMILY.get(key)
    if fam is None or prior is None:
        return raw
    n = _num(vols.get(fam))
    if n is None or n < _SAMPLE_FLOOR[fam]:
        return None
    k = _SHRINK_K[fam]
    return (n * raw + k * float(prior)) / (n + k)


def _legs(row: dict, vols: dict, side_pool: dict) -> tuple[list[float], str] | None:
    """Contributing z's plus the coverage key naming which legs contributed."""
    zs: list[float] = []
    keys: list[str] = []
    for key, raw in row.items():
        ps = side_pool.get(key)
        if not ps or ps.get("mean") is None:
            continue
        val = _shrunk(key, raw, vols, ps.get("prior"))
        if val is None:
            continue
        zs.append((val - float(ps["mean"])) / float(ps["sd"]))
        keys.append(key)
    if not zs:
        return None
    return zs, "|".join(sorted(keys))


def build_pool(players: Iterable[dict]) -> dict:
    """Compute per-side, per-component pool statistics for Statcast+.

    Returns a dict of shape:
      {"hit": {component: {mean, sd, prior}, ...,
               "__coverage_scale__": {coverage_key: sd},
               "__scale_default__": sd},
       "pit": {...}}

    Callers should build the pool ONCE per export run from the active
    player set and reuse it for every per-player Statcast+ call. The
    returned dict is JSON-serializable and safe to cache.

    Two passes are required, not one. The raw column mean is the EB prior;
    the mean and sd that standardize the column are then recomputed on the
    SHRUNK values. Taking the divisor from the unshrunk pool while the
    numerator is shrunk is the measured aStuff+ defect (7.16 points per
    sigma against an advertised 10, docs/efv-2026-07-29/GATED_CANDIDATES.md
    C3); it is the same bug in the same shape.
    """
    rows: list[tuple[str, dict, dict]] = []
    for p in players:
        is_pit = _is_pitcher(p)
        rows.append(("pit" if is_pit else "hit",
                     _extract_pitcher(p) if is_pit else _extract_hitter(p),
                     _component_volumes(p)))

    out: dict[str, dict] = {}
    for side in ("hit", "pit"):
        side_rows = [(r, v) for s, r, v in rows if s == side]
        if not side_rows:
            out[side] = {}
            continue
        # Union, not rows[0].keys(): a first row missing a component used to
        # drop that component for the whole pool.
        keys = sorted({k for r, _ in side_rows for k in r})
        stats: dict[str, Any] = {}
        for k in keys:
            raw = [x for x in (_num(r.get(k)) for r, _ in side_rows) if x is not None]
            prior = mean(raw) if raw else None
            vals = [x for x in (_shrunk(k, r.get(k), v, prior) for r, v in side_rows)
                    if x is not None]
            if not vals:
                stats[k] = {"mean": None, "sd": 1.0, "prior": prior}
                continue
            m = mean(vals)
            sd = pstdev(vals) if len(vals) > 1 else 0.0
            # Relative near-zero guard. `sd > 0` passed a degenerate column
            # through and handed one row an unbounded z.
            if not (sd > 1e-12 and sd > abs(m) * 1e-9):
                sd = 1.0
            stats[k] = {"mean": m, "sd": sd, "prior": prior}

        composites: list[float] = []
        cells: dict[str, list[float]] = {}
        for r, v in side_rows:
            got = _legs(r, v, stats)
            if got is None:
                continue
            avg = sum(got[0]) / len(got[0])
            composites.append(avg)
            cells.setdefault(got[1], []).append(avg)
        default = pstdev(composites) if len(composites) > 1 else 1.0
        stats[_SCALE_DEFAULT_KEY] = default if default > 1e-9 else 1.0
        stats[_SCALE_KEY] = {c: pstdev(v) for c, v in cells.items()
                             if len(v) >= _MIN_COVERAGE_CELL and pstdev(v) > 1e-9}
        out[side] = stats

    return out


def compute_statcast_plus(player: dict, pool: dict) -> int | None:
    """Return the Statcast+ index for `player` against the prebuilt
    `pool` (from build_pool). None when the player has no usable
    Statcast / zone data on any component.
    """
    is_pit = _is_pitcher(player)
    row = _extract_pitcher(player) if is_pit else _extract_hitter(player)
    side_pool = (pool or {}).get("pit" if is_pit else "hit") or {}

    got = _legs(row, _component_volumes(player), side_pool)
    if got is None:
        return None
    zs, coverage = got

    if _SCALE_DEFAULT_KEY not in side_pool:
        # A pool without scales would silently serve the OLD compressed
        # index at the NEW thresholds, which reads as a site-wide collapse
        # rather than as an error. Fail loudly instead.
        raise ValueError(
            "statcast_plus: pool has component stats but no coverage scale; "
            "rebuild it with build_pool() rather than reusing a stale cache")
    sd = (side_pool.get(_SCALE_KEY) or {}).get(coverage) \
        or side_pool.get(_SCALE_DEFAULT_KEY) or 1.0

    avg_z = (sum(zs) / len(zs)) / float(sd)
    return int(round(_SC_PLUS_ANCHOR + avg_z * _SC_PLUS_PER_SIGMA))
