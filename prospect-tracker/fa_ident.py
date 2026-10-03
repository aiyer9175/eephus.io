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
    below come through war_source.stint_frame on the DISPLAYED series, eWAR v2,
    named explicitly (an identity helper that uses WAR only as a tiebreak; fWAR
    label epoch step D + U, 2026-10-03, owner answer EPOCH-Q4)."""
    import pybaseball  # noqa: F401 - availability probe; frames come via war_source
    import war_source
    out: dict[str, dict[int, dict]] = {}
    missing: list[str] = []
    for side, label in (("bat", "bwar_bat"), ("pit", "bwar_pitch")):
        try:
            df = war_source.stint_frame(side, provider="ewar_v2")
        except Exception as e:                                # noqa: BLE001
            # HALF AN INDEX IS WORSE THAN NO INDEX (2026-08-05). This used to
            # `continue` and return whatever it had, which looks safe and is the
            # single most expensive bug of the session: a failed PITCHING frame
            # yields a BATTING-ONLY index that is structurally valid and passes
            # every downstream check, so every pitcher silently fails to resolve
            # while every hitter resolves fine. On 2026-08-04 that blanked 79 of
            # 228 free agents (and 2028: 181 -> 111, 2029: 133 -> 83) with no
            # error anywhere. Proven by reproduction: rebuilding from the batting
            # frame alone reproduces the served blank set with SET EQUALITY.
            #
            # It is ALWAYS the pitching side, and it is not luck: pybaseball
            # decorates bwar_bat with @cache.df_cache() and bwar_pitch with
            # NOTHING, so batting serves from a 7-day parquet cache while
            # pitching is a live download on every process that builds this.
            #
            # The failure is now RECORDED rather than swallowed, and the caller
            # is told which side is missing so a degraded index can be refused
            # instead of published. See fa_export's identity_health block, which
            # holds the write when this fires.
            log.error("%s unavailable: %s. The identity index will be MISSING "
                      "the %s side entirely, so every %s-only player will fail "
                      "to resolve.", label, e, side, side)
            missing.append(side)
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
    # Recorded on the MODULE, not inside the returned dict. Every caller treats
    # this index as {name: ...} and several iterate it, so a sentinel key would
    # be a new silent defect in the middle of fixing one. war_daily_index is
    # lru_cache(maxsize=1), so this tracks the one live build.
    global _SIDES_MISSING
    _SIDES_MISSING = tuple(missing)
    return out


# Which WAR sides were missing from the LAST war_daily_index build. Empty means
# the index is whole. Read it through index_sides_missing().
_SIDES_MISSING: tuple[str, ...] = ()


def index_sides_missing() -> tuple[str, ...]:
    """Which WAR sides ('bat', 'pit') failed to load in the live index.

    () means whole. Anything else means resolution is SILENTLY partial for that
    side, and a caller publishing a board off it is about to serve blanks that
    look like real absences: see the comment in war_daily_index. Builds the
    index if it has not been built, so the answer always describes a real one."""
    war_daily_index()
    return _SIDES_MISSING


#: READ-TIME SPELLING BRIDGE, our normalized key -> Baseball-Reference's.
#:
#: Identity fixes are alias maps, never DB remaps: the DB key is what every
#: other surface, override file and stored event references, so re-keying a
#: player to match one upstream source silently breaks the rest.
#:
#: Entries are earned one at a time, each with the B-Ref spelling and the id it
#: resolves to, because a wrong alias attaches another man's career to a free
#: agent. Only add a row after checking the war_daily frame itself.
#:
#: jake_junis: B-Ref's war_daily spells him "Jakob Junis" (mlb_ID 596001,
#: active 2017-2026). Neither spelling appeared anywhere else in this repo, so
#: the miss was invisible: he shipped on the 2027 board with no price and a
#: reason code that reads as "has not pitched in the majors in four years",
#: for a pitcher who threw 40 innings this season.
NAME_ALIASES: dict[str, str] = {
    "jake_junis": "jakob_junis",
}


def _candidates(idx: dict, key: str) -> dict | None:
    """war_daily candidates for one normalized key, with the suffix repair."""
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
    return cands or None


#: Why a name did not resolve. These are the THREE different failures a bare
#: None used to flatten into one, and they are not equally interesting: a KBO
#: entrant with no MLB career is a correct null forever, while a spelling miss
#: is a bug with a fix. A caller that reports "unresolved" for all three tells
#: its reader to go looking for a defect that is not there.
NO_MLB_RECORD = "no_mlb_record"                  # absent from war_daily entirely
NO_RECORD_IN_WINDOW = "no_record_in_window"      # played, but not in the window
IDENTITY_AMBIGUOUS = "identity_ambiguous"        # two men fit; we refuse to guess
RESOLVED = "resolved"


def resolve_with_reason(name: str, active_window: range) -> tuple[int | None, str]:
    """(mlbam_id, reason) where reason is RESOLVED or one of the three misses
    above. resolve() is this function with the reason dropped, so the two can
    never disagree about who resolved."""
    idx = war_daily_index()
    key = normalize_key(name)
    cands = _candidates(idx, key)
    if not cands:
        # The alias is a FALLBACK, not a rewrite: a real match under our own
        # spelling always wins, so adding a row can only turn a miss into a
        # hit and can never move a player who already resolved.
        alias = NAME_ALIASES.get(key)
        if alias:
            cands = _candidates(idx, alias)
            if cands:
                log.info("identity alias: %s resolved through the B-Ref "
                         "spelling %r", key, alias)
    if not cands:
        return None, NO_MLB_RECORD
    window = set(active_window)
    plausible = [mid for mid, ent in cands.items() if ent["years"] & window]
    # WRONG-PLAYER FALLBACK REMOVED 2026-07-25. This used to read:
    #     if not plausible and len(cands) == 1: plausible = list(cands)
    # i.e. when exactly one candidate carried the name it was returned even though
    # it was active in NO year of the window. "Lance McCullers" resolved to 118617,
    # his father, who last pitched in 1992, because the son lives under
    # lance_mccullers_jr. Silently attaching another man's career to a free agent is
    # worse than returning None, so an out-of-window candidate is now refused.
    if len(plausible) == 1:
        return plausible[0], RESOLVED
    return None, (IDENTITY_AMBIGUOUS if plausible else NO_RECORD_IN_WINDOW)


def resolve(name: str, active_window: range) -> int | None:
    """MLBAM id for ``name`` if exactly one war_daily candidate was active
    inside ``active_window``; None on no-match or ambiguity."""
    return resolve_with_reason(name, active_window)[0]
