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
moves the index 15 points (wRC+/OPS+ family scaling).
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any, Iterable


# Anchoring constants — match the JS implementation exactly so a badge
# label and the gate it fired through never disagree. 100 is the pool
# mean; 15 points per stddev mirrors wRC+ / OPS+ display ergonomics.
_SC_PLUS_ANCHOR = 100
_SC_PLUS_PER_SIGMA = 15

# Tier breakpoints used by downstream gates / display.
SC_PLUS_TOP_QUINTILE = 115     # ≥115 ≈ +1σ → top quintile of pool
SC_PLUS_BOTTOM_QUINTILE = 85   # ≤85 ≈ -1σ → bottom quintile


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
        # rolls the same direction as the other components.
        "z_contact":    z.get("z_contact_pct"),
        "whiff_inv":    -z["whiff_pct"] if z.get("whiff_pct") is not None else None,
        "chase_inv":    -z["chase_pct"] if z.get("chase_pct") is not None else None,
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
        "chase":      z.get("chase_pct"),
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


def _column_stat(values: Iterable[float | None]) -> dict:
    """Population mean + stddev for one component column. Returns
    {mean, sd} with sd defaulting to 1 when the sample is too thin
    (so callers can divide without guarding for ZeroDivisionError)."""
    nums = [float(v) for v in values
            if v is not None and isinstance(v, (int, float))]
    if not nums:
        return {"mean": None, "sd": 1.0}
    m = mean(nums)
    sd = pstdev(nums) if len(nums) > 1 else 0.0
    return {"mean": m, "sd": sd if sd > 0 else 1.0}


def build_pool(players: Iterable[dict]) -> dict:
    """Compute per-side, per-component pool statistics for Statcast+.

    Returns a dict of shape:
      {"hit": {component: {mean, sd}, ...},
       "pit": {component: {mean, sd}, ...}}

    Callers should build the pool ONCE per export run from the active
    player set and reuse it for every per-player Statcast+ call. The
    returned dict is JSON-serializable and safe to cache.
    """
    hit_rows: list[dict] = []
    pit_rows: list[dict] = []
    for p in players:
        if _is_pitcher(p):
            pit_rows.append(_extract_pitcher(p))
        else:
            hit_rows.append(_extract_hitter(p))

    def _stats_for(rows: list[dict]) -> dict:
        if not rows:
            return {}
        keys = rows[0].keys()
        return {k: _column_stat(r.get(k) for r in rows) for k in keys}

    return {"hit": _stats_for(hit_rows), "pit": _stats_for(pit_rows)}


def compute_statcast_plus(player: dict, pool: dict) -> int | None:
    """Return the Statcast+ index for `player` against the prebuilt
    `pool` (from build_pool). None when the player has no usable
    Statcast / zone data on any component.
    """
    is_pit = _is_pitcher(player)
    row = _extract_pitcher(player) if is_pit else _extract_hitter(player)
    side_pool = (pool or {}).get("pit" if is_pit else "hit") or {}

    zs: list[float] = []
    for key, raw in row.items():
        if raw is None or not isinstance(raw, (int, float)):
            continue
        ps = side_pool.get(key)
        if not ps or ps.get("mean") is None:
            continue
        sd = ps.get("sd") or 1.0
        if sd == 0:
            continue
        zs.append((float(raw) - float(ps["mean"])) / float(sd))

    if not zs:
        return None
    avg_z = sum(zs) / len(zs)
    return int(round(_SC_PLUS_ANCHOR + avg_z * _SC_PLUS_PER_SIGMA))
