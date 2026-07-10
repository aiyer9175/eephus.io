# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Shared veteran-identity resolution against B-Ref war_daily — one name
index serving the FA pipeline (signings), the fit engine (contracted
rosters), and any future consumer. Disambiguation by activity window;
ambiguity is reported, never guessed."""

from __future__ import annotations

import logging
from functools import lru_cache

from scrapers import normalize_key

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def war_daily_index() -> dict[str, dict[int, dict]]:
    """{normalized_name: {mlb_ID: {"years": set[int], "war": {year: WAR}}}}
    across both war_daily tables (batting + pitching WAR summed)."""
    import pybaseball as pyb
    out: dict[str, dict[int, dict]] = {}
    for fn, label in ((pyb.bwar_bat, "bwar_bat"), (pyb.bwar_pitch, "bwar_pitch")):
        try:
            df = fn(return_all=True)
        except Exception as e:                                # noqa: BLE001
            log.warning("%s unavailable: %s", label, e)
            continue
        sub = df[df["WAR"].notna() & df["mlb_ID"].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid = int(row.mlb_ID)
                yr = int(row.year_ID)
                war = float(row.WAR)
                nm = normalize_key(str(row.name_common))
            except (TypeError, ValueError):
                continue
            ent = out.setdefault(nm, {}).setdefault(mid, {"years": set(), "war": {}})
            ent["years"].add(yr)
            ent["war"][yr] = ent["war"].get(yr, 0.0) + war
    return out


def resolve(name: str, active_window: range) -> int | None:
    """MLBAM id for ``name`` if exactly one war_daily candidate was active
    inside ``active_window``; None on no-match or ambiguity."""
    cands = war_daily_index().get(normalize_key(name))
    if not cands:
        return None
    window = set(active_window)
    plausible = [mid for mid, ent in cands.items() if ent["years"] & window]
    if not plausible and len(cands) == 1:
        plausible = list(cands)
    return plausible[0] if len(plausible) == 1 else None
