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
    across both war_daily tables (batting + pitching WAR summed).

    war_source.name_index is the facade route to this index; the raw frames
    below come through war_source.stint_frame (provider 'bwar')."""
    import pybaseball  # noqa: F401 - availability probe; frames come via war_source
    import war_source
    out: dict[str, dict[int, dict]] = {}
    for side, label in (("bat", "bwar_bat"), ("pit", "bwar_pitch")):
        try:
            df = war_source.stint_frame(side)
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
    idx = war_daily_index()
    key = normalize_key(name)
    cands = idx.get(key)
    # SUFFIX REPAIR 2026-07-25. The FA class spells players without a generational
    # suffix while Baseball-Reference's war_daily spells them with one, so an exact
    # key lookup silently missed them: "Jazz Chisholm" -> jazz_chisholm while the
    # index holds jazz_chisholm_jr. No id -> no WAR history -> no projection -> the
    # member renders as a blank row on /fa/ and the owner cannot see why. 44 index
    # keys carry _jr/_sr/_ii/_iii, so this is a class of bug, not one player.
    # Try the bare key first, then suffixed variants, then the reverse (a suffixed
    # class name against a bare index key).
    # MERGE the bare and suffixed candidate sets rather than stopping at the first
    # hit: "Lance McCullers" matches BOTH lance_mccullers (the father, last active
    # 1992) and lance_mccullers_jr (the son). Taking only the bare key returned a
    # man who is in no year of the window; merging lets the window filter below pick
    # the son unambiguously.
    merged = dict(cands or {})
    for suf in ("_jr", "_sr", "_ii", "_iii"):
        extra = idx.get(key + suf)
        if extra:
            merged.update(extra)
    cands = merged or None
    if not cands:
        for suf in ("_jr", "_sr", "_ii", "_iii"):
            if key.endswith(suf):
                cands = idx.get(key[: -len(suf)])
                break
    if not cands:
        return None
    window = set(active_window)
    plausible = [mid for mid, ent in cands.items() if ent["years"] & window]
    # WRONG-PLAYER FALLBACK REMOVED 2026-07-25. This used to read:
    #     if not plausible and len(cands) == 1: plausible = list(cands)
    # i.e. when exactly one candidate carried the name it was returned even though
    # it was active in NO year of the window. "Lance McCullers" resolved to 118617,
    # his father, who last pitched in 1992, because the son lives under
    # lance_mccullers_jr. Silently attaching another man's career to a free agent is
    # worse than returning None, so an out-of-window candidate is now refused.
    return plausible[0] if len(plausible) == 1 else None
