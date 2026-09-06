#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_pbp_corpus - flatten ``.cache/win_prob/*.json`` into a play/pitch corpus.

WHAT IT IS. A no-network CLI that walks the 19,132 cached
``/api/v1/game/{pk}/winProbability`` payloads (19 GB of JSON, one file per game,
each file a LIST of plays) and writes three season-partitioned parquet tables
under ``.cache/pbp_corpus/``:

  plays    one row per plate appearance. Identity, count, score, Leverage Index,
           win probability, and the RECONSTRUCTED pre-play state (outs_before,
           on_first/on_second/on_third runner ids, runs_scored_on_play).
  pitches  one row per ``playEvents`` entry with ``isPitch``. Call code, pitch
           type, velocity, zone, plate coordinates, strike-zone edges, and the
           home-plate umpire id off the event's own ``officials`` block.
  events   one row per NON-pitch ``playEvents`` entry (substitutions, steals,
           pickoffs, mound visits, advisories) carrying ``details.description``
           VERBATIM, because the substitution lineage parser downstream reads
           the raw sentence and nothing else reproduces it.

WHAT IT IS NOT. Not a fetcher: it opens no socket and refetches nothing, so a
game absent from the cache is absent from the corpus, full stop. Not a metric,
not a model, not a rate table: every column is either copied from the payload or
derived by the base-state walk below. Nothing here is park-, era-, or
opponent-adjusted, and no row is dropped for quality.

THE LOAD-BEARING PART: PRE-PITCH BASE STATE IS NOT A FIRST-CLASS FIELD on the
play. ``matchup`` has no postOnFirst/Second/Third in this payload, so the state
is reconstructed by walking ``runners[].movement`` within a (game, inning,
half) in atBatIndex order. Three inputs feed the carried base map, in order:

  1. the map carried from the previous play of the same half inning (reset to
     empty at every half-inning change);
  2. index-ordered non-pitch actions that change occupancy without a movement
     record: ``runner_placed`` (the extra-innings automatic runner, which
     otherwise makes the 10th inning look empty) and a pinch-runner
     ``offensive_substitution`` carrying a ``base`` field (which otherwise
     leaves the relieved runner's id parked on the bag);
  3. healing from this play's own ``movement.start`` values, which name the base
     each mover began on and therefore correct any drift the first two missed.

Movements are then applied as a NET destination per runner, not step by step:
each runner's LAST entry names where he finished, every mentioned runner is
lifted off the bases, and the survivors are seated. Two ordering traps and one
identity trap forced this, and each cost real accuracy before it was found.

WHAT EACH GUARD IS WORTH, re-measured 2026-09-06 by switching one guard OFF at a
time on the acceptance sample below and re-scoring the walk against the payload's
own offense block. The shipped walk scores 100.0000% base occupancy agreement on
41,220 comparable plays; each figure below is that same rate with the one named
guard removed. The sort variant is a REBUILD of the ordering described, not the
original draft's code, so read it as the cost of that ordering rather than as an
artifact of a specific old commit:

  * ONE RUNNER CAN CARRY SEVERAL ENTRIES on one play (2B to 3B on the hit, then
    3B to score on the throw). Sorting lead-runner-first inside a playIndex
    reverses those pairs and strands runners who had scored: 93.2945%. Sorting
    on playIndex alone, ties in payload order, is what the shipped walk does.
  * Stepwise placement clobbers. On a bases-loaded single the batter is written
    to 1B and then to 2B before the man who started on 1B vacates it, so seating
    that man at 2B overwrites the batter and loses him: 99.7210%, and the
    occupied-base collision counter goes from 19 to 2,824.
  * A pinch runner entering MID plate appearance splits one baserunner across two
    ids. Without ``_pinch_runner_alias`` a phantom runner holds a bag for the
    rest of the inning: 99.9951%. It is the smallest of the three and it is the
    only one that leaves a wrong RUNNER on a right bag.

``movement.end is None`` and ``movement.isOut`` are perfectly coincident in this
payload (measured: 2,194 entries end-None-and-out, 2,172 entries end-set-and-safe,
ZERO mixed, over 40 games), so the out test is unambiguous. ``end`` also takes an
undocumented ``4B`` meaning the runner reached home; see ``_SCORE_ENDS``.

MEASURED ACCURACY, NOT ASSERTED. ``playEvents[].offense`` carries ``first`` /
``second`` / ``third`` when those bases are occupied. That block is an
INDEPENDENT ground truth for the reconstruction, and every build scores the walk
against it. The corpus does NOT read that block into its output columns: the
reconstruction is scored by it, never seeded from it, so the figure stays honest.
Acceptance sample: 70 random games from EVERY season the cache holds (2018,
2019, 2021 through 2026: there is no 2017 and no 2020), 560 games, 42,269 plays.

    base occupancy agreement   1.000000  on 41,220 comparable plays
    base identity agreement    0.999903  4 misses, all right bag wrong man
    plays not comparable         933     (see ``prepitch_baserunning``)
    invalid reconstructed state   19      0.000450 of 42,269
    outs walk vs count.outs        0      0.000000 of 42,269
    runs walk vs score delta       0      0.000000 of 42,269

A second, independent end-to-end check on the written parquet: summing
``runs_scored_on_play`` over a game equals that game's final
``away_score + home_score`` in 150 of 150 games, and ``leverage_index`` is null
on exactly 150 rows in 150 games, one per game. The base-state distribution the
corpus produces is 56.93% bases empty and 2.340% bases loaded, which is where
major-league base-out frequencies actually sit.

WHAT THE RECONSTRUCTION REFUSES TO CLAIM.
  * IT DOES NOT REPAIR THE FORCE-OUT-AT-THIRD DEFECT. All 19 invalid states on
    the acceptance sample are the same class, and every one is an occupied-base
    collision (the outs checks flag zero): re-measured 2026-09-06, 19 of 19 are
    ``force_out`` plays, 18 described "out at 3rd" and 1 "out at home". On those
    the payload records the lead runner's out and the batter reaching first, but
    OMITS the trailing runner's 1B-to-2B advance. The walk then seats the batter
    on an occupied first base, counts the collision, and loses the trailing
    runner for one play. No advance is inferred: the omission
    belongs to the source. The healing pass restores the runner the next time he
    appears in ``runners[]``, which is why the collisions leave no residue in the
    agreement score.
  * It does not claim the runner IDS are right on a play where a pinch runner
    entered and then nobody moved: occupancy is carried, but a substitution
    without a ``base`` field and without a Pinch Runner position cannot be
    attributed to a bag until the new runner next appears in ``runners[]``.
    Measured cost: 4 plays in 41,220, every one of them the right base holding
    the relieved man's id rather than the substitute's. Occupancy is unaffected,
    so a base-out state model is clean and only a per-runner join is exposed.
  * It does not reconcile a payload that contradicts itself. Where the walked
    outs disagree with ``count.outs``, or the runs counted off ``movement.end``
    disagree with the ``result.awayScore``/``homeScore`` delta, the row keeps the
    walked value and the disagreement is counted into the manifest rather than
    smoothed away.
  * ``leverage_index`` is absent on exactly 1.00 play per game (measured: 60
    missing over 60 games / 4,593 plays, 1.31%), always the game's leadoff plate
    appearance. That is a null in the column, not a zero.
  * ``wp_home_after`` is the payload's ``homeTeamWinProbability``, which is the
    POST-play number (measured: the final play of a game the home team lost
    reads 0.0). ``wp_home_before`` is derived as after minus added; chaining one
    play's after into the next play's before agrees to within 0.06 points on
    97.02% of 1,880 consecutive pairs, so treat the before column as
    within-play consistent, not as a continuous game-level series.

Run:
    python tools/build_pbp_corpus.py [--seasons 2018,2019] [--limit N]
                                     [--sample N] [--force] [--validate]
                                     [--dry-run]

``--limit`` caps games PER SEASON and ``--sample`` takes N random games per
season; both mark the season INCOMPLETE in the manifest so a later uncapped run
rebuilds it instead of shipping a partial corpus. An uncapped season already on
disk is skipped unless ``--force``, so the full build is resumable one season at
a time and safe to interrupt.

Cost of the full build, extrapolated from 560 games across all 8 seasons:
12.5 ms per game to flatten, so about 4.0 minutes for all 19,132 games, plus
roughly 85 s for the one-time season index. Output about 336 MB (17.13 KB per
game) holding an estimated 1.44M plays, 5.63M pitches and 0.73M events, against
the 19 GB of JSON it is read from.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_log = logging.getLogger("build_pbp_corpus")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = REPO_ROOT / ".cache" / "win_prob"
DEFAULT_OUT = REPO_ROOT / ".cache" / "pbp_corpus"

TABLES = ("plays", "pitches", "events")
BASES = ("1B", "2B", "3B")
# "score" is the ordinary end value for a run. "4B" is an undocumented synonym
# for reaching home that the payload emits on an inside-the-park home run scored
# as a triple-plus-score (game_pk 716358, atBatIndex 34, Kyle Tucker). It is very
# rare: ZERO occurrences in 600 random games, one in the 240-game build sample.
# Treated as a run, because reading it as an unknown base loses the run outright.
_SCORE_ENDS = ("score", "4B")
_BASE_OF_NUM = {1: "1B", 2: "2B", 3: "3B"}
# about.startTime is the first "startTime" in the file (result precedes about,
# and playEvents[].startTime comes later), so a head read names the season.
_SEASON_RE = re.compile(rb'"startTime"\s*:\s*"(\d{4})-')
_SNIFF_BYTES = 4096


# --------------------------------------------------------------------------
# season identification
# --------------------------------------------------------------------------
def sniff_season(path: Path) -> int | None:
    """Season of a cached game from a head read, no full parse.

    Reads the first 4 KB and takes the first ``startTime`` year. Verified 300/300
    on the oldest 300 cache files; the full parse re-derives it and any
    disagreement is counted into the manifest, never silently preferred.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(_SNIFF_BYTES)
    except OSError:
        return None
    m = _SEASON_RE.search(head)
    return int(m.group(1)) if m else None


def season_of_plays(plays) -> int | None:
    """Season from the parsed payload (first play's ``about.startTime`` year)."""
    for pl in plays or ():
        st = (pl.get("about") or {}).get("startTime")
        if st and len(st) >= 4 and st[:4].isdigit():
            return int(st[:4])
    return None


# --------------------------------------------------------------------------
# base-state reconstruction (pure)
# --------------------------------------------------------------------------
def _runner_id(r: dict):
    return ((r.get("details") or {}).get("runner") or {}).get("id")


def _sorted_runners(play: dict) -> list:
    """Runner entries in application order: ``details.playIndex``, ties in payload order.

    ONE RUNNER CAN CARRY SEVERAL ENTRIES on a single play (2B to 3B on the hit,
    then 3B to score on the throw), and those entries are a SEQUENCE: applying
    them out of order strands a runner who actually scored. The sort is
    therefore stable on playIndex alone. An earlier draft sorted lead-runner-first
    inside a playIndex to stop a batter taking 1B from evicting the runner
    standing there; that ordering reverses the two-step sequences and costs 6.71
    points of base occupancy agreement (re-measured 2026-09-06 on the acceptance
    sample: 93.2945% with that ordering, 100.0000% shipped). It is not
    needed: every place is preceded by dropping the mover from his old bag, so
    the evicted runner is restored by his own entry a step later.
    """
    out = []
    for i, r in enumerate(play.get("runners") or ()):
        pi = (r.get("details") or {}).get("playIndex")
        out.append(((pi if pi is not None else -1), i, r))
    out.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in out]


def _first_entry_per_runner(runners: list) -> list:
    """The earliest entry for each runner, for the pre-play healing pass.

    A runner with a 2B-to-3B entry and a 3B-to-score entry began the play on 2B,
    not on 3B, so only his FIRST entry may inform the pre-play state.
    """
    seen = set()
    out = []
    for r in runners:
        rid = _runner_id(r)
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out


def _drop(bases: dict, rid) -> None:
    """Remove a runner id from whatever bag it currently sits on."""
    if rid is None:
        return
    for b in BASES:
        if bases[b] == rid:
            bases[b] = None


def _apply_pre_pitch_actions(bases: dict, play: dict) -> None:
    """Occupancy changes that carry no ``runners[]`` movement record.

    ``runner_placed`` seats the extra-innings automatic runner; a pinch-runner
    ``offensive_substitution`` with a ``base`` field swaps the id on that bag.
    Both are actions ahead of the first pitch of the plate appearance, so the
    scan stops at the first pitch event.
    """
    for ev in play.get("playEvents") or ():
        if ev.get("isPitch"):
            break
        det = ev.get("details") or {}
        et = det.get("eventType")
        base = _BASE_OF_NUM.get(ev.get("base"))
        if base is None:
            continue
        pid = (ev.get("player") or {}).get("id")
        if pid is None:
            continue
        if et == "runner_placed":
            _drop(bases, pid)
            bases[base] = pid
        elif et == "offensive_substitution":
            # pinch runner: the relieved man leaves the bag, the new man takes it
            _drop(bases, (ev.get("replacedPlayer") or {}).get("id"))
            _drop(bases, pid)
            bases[base] = pid


def _bump(diag: dict, key: str, n: int = 1) -> None:
    diag[key] = diag.get(key, 0) + n


def _pinch_runner_alias(play: dict) -> dict:
    """{relieved runner id: incoming pinch runner id} for this play.

    A pinch runner can enter in the MIDDLE of a plate appearance, and the payload
    then splits one baserunner across two ids: game_pk 529416 atBatIndex 67 has
    Suzuki going 1B to 2B to 3B on a passed ball and Bourjos, who replaced him at
    third, scoring from 3B on the single. Without this alias the walk seats
    Bourjos at 3B in the PRE-play state (he was not in the game yet) and then
    leaves Suzuki stranded at 3B for the rest of the inning, a phantom runner.
    Restricted to Pinch Runner (position code 12) and to substitutions naming a
    ``base``, so a pinch HITTER never merges identities with a man on base.
    """
    alias: dict = {}
    for ev in play.get("playEvents") or ():
        if ev.get("isPitch") or not ev.get("isSubstitution"):
            continue
        if (ev.get("details") or {}).get("eventType") != "offensive_substitution":
            continue
        code = (ev.get("position") or {}).get("code")
        if code != "12" and ev.get("base") is None:
            continue
        new = (ev.get("player") or {}).get("id")
        old = (ev.get("replacedPlayer") or {}).get("id")
        if new is not None and old is not None:
            alias[old] = new
    return alias


_BASERUNNING_ACTIONS = frozenset({
    "stolen_base_1b", "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
    "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
    "pickoff_1b", "pickoff_2b", "pickoff_3b",
    "pickoff_error_1b", "pickoff_error_2b", "pickoff_error_3b",
    "pickoff_caught_stealing_2b", "pickoff_caught_stealing_3b",
    "pickoff_caught_stealing_home", "balk", "wild_pitch", "passed_ball",
    "defensive_indiff", "other_advance", "error", "runner_placed",
})


def prepitch_baserunning(play: dict) -> bool:
    """True when a runner could have moved BEFORE this play's first pitch.

    A pickoff error, a balk or a steal recorded ahead of pitch one moves runners
    inside the plate appearance. The reconstruction reports the state at the
    START of the play; the offense truth block reports the state AT the first
    pitch. On these plays the two measure different instants, so the play is left
    out of the agreement score rather than counted as a miss. This predicate is
    the only thing that voids a truth block once ``truth_bases`` found one, so
    the excluded set IS this class by construction rather than by measurement.

    HOW BIG THE EXCLUSION IS, AND WHAT IT BUYS. Re-measured 2026-09-06 on the
    acceptance sample (``--sample 70``, seed 17, all eight cached seasons, 560
    games, 42,269 plays): 42,153 of those plays carry a truth block and 933 of
    them are excluded here, 2.21%. The exclusion is quantified, not trusted:
    scoring all 933 against the truth block ANYWAY, 904 agree and 29 disagree,
    so dropping the exclusion moves base occupancy agreement from 1.000000 to
    0.999312 (42,124 of 42,153). It is hiding 29 plays, not a broken walk. A
    240-game re-draw (2018 and 2023, 120 games each, seed 17, 18,074 plays)
    excludes 396 of 18,023, the same rate.
    """
    for ev in play.get("playEvents") or ():
        if ev.get("isPitch"):
            return False
        if ev.get("type") in ("pickoff", "stepoff"):
            return True
        if ev.get("isBaseRunningPlay"):
            return True
        if (ev.get("details") or {}).get("eventType") in _BASERUNNING_ACTIONS:
            return True
    return False


def truth_bases(play: dict) -> dict | None:
    """Independent pre-play base state from the first PITCH event's offense block.

    The offense block on an ACTION event is the pre-action state (a pinch-runner
    substitution still shows the relieved man there), so only an ``isPitch``
    event is taken. A plate appearance with no pitch yields None and is left out
    of the score entirely rather than counted as agreement.
    """
    for ev in play.get("playEvents") or ():
        if not ev.get("isPitch"):
            continue
        off = ev.get("offense")
        if not off:
            return None
        return {"1B": (off.get("first") or {}).get("id"),
                "2B": (off.get("second") or {}).get("id"),
                "3B": (off.get("third") or {}).get("id")}
    return None


def reconstruct_plays(plays, game_pk=None, season=None,
                      diag: dict | None = None) -> list[dict]:
    """Walk one game's play list into play rows carrying the pre-play state.

    Pure: takes the payload list, returns rows. ``diag`` (a dict of counters,
    created if omitted) accumulates the validation tallies described in the
    module docstring. Half-inning changes reset the base map and the out count.
    """
    if diag is None:
        diag = {}

    rows: list[dict] = []
    bases = {b: None for b in BASES}
    cur_half = None
    prev_outs = 0
    prev_total_score = None

    for play in plays or ():
        about = play.get("about") or {}
        result = play.get("result") or {}
        count = play.get("count") or {}
        matchup = play.get("matchup") or {}

        half_key = (about.get("inning"), about.get("halfInning"))
        if half_key != cur_half:
            cur_half = half_key
            bases = {b: None for b in BASES}
            prev_outs = 0

        _apply_pre_pitch_actions(bases, play)

        runners = _sorted_runners(play)
        alias = _pinch_runner_alias(play)
        entrants = set(alias.values())

        # heal: movement.start names the bag the runner actually began on.
        # Only the FIRST entry per runner speaks to the pre-play state, and a
        # pinch runner who entered during this play was not on base when it
        # began, so his start base is not pre-play evidence.
        for r in _first_entry_per_runner(runners):
            start = (r.get("movement") or {}).get("start")
            rid = _runner_id(r)
            if rid in entrants:
                continue
            if start in BASES and rid is not None:
                if bases[start] is not None and bases[start] != rid:
                    _bump(diag, "heal_evictions")
                _drop(bases, rid)
                bases[start] = rid

        pre = dict(bases)
        outs_before = prev_outs

        # ---- score the walk against the play's own offense block -------------
        truth = truth_bases(play)
        if truth is not None and prepitch_baserunning(play):
            truth = None
            _bump(diag, "truth_skipped_prepitch")
        if truth is not None:
            _bump(diag, "truth_plays")
            if all((pre[b] is None) == (truth[b] is None) for b in BASES):
                _bump(diag, "truth_occupancy_ok")
            if all(pre[b] == truth[b] for b in BASES):
                _bump(diag, "truth_identity_ok")

        # ---- apply movements, NET not STEPWISE -------------------------------
        # Each runner's LAST entry is his destination. Applying the steps one at
        # a time is what an earlier draft did, and it clobbers: on a
        # bases-loaded single the batter is written to 1B and then to 2B before
        # the runner who started on 1B vacates it, so seating that runner at 2B
        # overwrote the batter and lost him. Removing every mentioned runner
        # first and then seating each at his final base is order-independent.
        # Re-measured 2026-09-06 on the acceptance sample: applying the entries
        # stepwise instead scores 99.7210% base occupancy where this scores
        # 100.0000%, and raises invalid_occupied_base from 19 to 2,824.
        final: dict = {}
        for r in runners:
            rid = _runner_id(r)
            if rid is not None:
                final[alias.get(rid, rid)] = r.get("movement") or {}
        for rid in final:
            _drop(bases, rid)
        for old_id, new_id in alias.items():
            if new_id in final:
                _drop(bases, old_id)

        runs = set()
        outs_ids = set()
        for rid, m in final.items():
            end = m.get("end")
            if m.get("isOut"):
                outs_ids.add(rid)
            elif end in _SCORE_ENDS:
                runs.add(rid)
            elif end in BASES:
                occ = bases[end]
                if occ is not None and occ != rid:
                    _bump(diag, "invalid_occupied_base")
                bases[end] = rid
            elif end is None:
                # safe with no destination: he never left the bag he started on
                _bump(diag, "end_none_not_out")
                for b in BASES:
                    if pre[b] == rid:
                        bases[b] = rid
            else:
                _bump(diag, "unknown_movement_end")

        outs_on_play = len(outs_ids)
        runs_scored = len(runs)
        outs_after = count.get("outs")
        if outs_after is None:
            outs_after = outs_before + outs_on_play

        # ---- invalid-state tallies -------------------------------------------
        _bump(diag, "state_checked")
        if outs_after > 3:
            _bump(diag, "invalid_outs_gt3")
        if outs_after < outs_before:
            _bump(diag, "invalid_outs_decrease")
        if outs_before + outs_on_play != outs_after:
            _bump(diag, "outs_walk_mismatch")

        away, home = result.get("awayScore"), result.get("homeScore")
        total = None if (away is None or home is None) else (away + home)
        if total is not None:
            delta = total - (prev_total_score if prev_total_score is not None else 0)
            _bump(diag, "runs_checked")
            if delta != runs_scored:
                _bump(diag, "runs_mismatch")
                worst = diag.get("runs_worst") or (0, None)
                if abs(delta - runs_scored) > worst[0]:
                    diag["runs_worst"] = (
                        abs(delta - runs_scored),
                        {"game_pk": game_pk, "at_bat_index": play.get("atBatIndex"),
                         "inning": about.get("inning"),
                         "half": about.get("halfInning"),
                         "event": result.get("event"), "score_delta": delta,
                         "walked_runs": runs_scored},
                    )
            prev_total_score = total

        wpa = play.get("homeTeamWinProbabilityAdded")
        wp_after = play.get("homeTeamWinProbability")
        wp_before = None if (wp_after is None or wpa is None) else round(wp_after - wpa, 6)

        rows.append({
            "game_pk": game_pk,
            "season": season,
            "half": about.get("halfInning"),
            "inning": about.get("inning"),
            "at_bat_index": play.get("atBatIndex"),
            "batter_id": (matchup.get("batter") or {}).get("id"),
            "bat_side": (matchup.get("batSide") or {}).get("code"),
            "pitcher_id": (matchup.get("pitcher") or {}).get("id"),
            "pitch_hand": (matchup.get("pitchHand") or {}).get("code"),
            "event_type": result.get("eventType"),
            "event": result.get("event"),
            "rbi": result.get("rbi"),
            "away_score": away,
            "home_score": home,
            "outs_after": outs_after,
            "balls": count.get("balls"),
            "strikes": count.get("strikes"),
            "leverage_index": play.get("leverageIndex"),
            "drama_index": play.get("dramaIndex"),
            "wp_home_before": wp_before,
            "wp_home_after": wp_after,
            "wpa_home": wpa,
            "outs_before": outs_before,
            "on_first": pre["1B"],
            "on_second": pre["2B"],
            "on_third": pre["3B"],
            "runs_scored_on_play": runs_scored,
        })
        prev_outs = outs_after

    return rows


# --------------------------------------------------------------------------
# pitch + event flattening (pure)
# --------------------------------------------------------------------------
def _hp_umpire(ev: dict):
    """Home-plate umpire id off the event's own officials block, when present."""
    for o in ev.get("officials") or ():
        if o.get("officialType") == "Home Plate":
            return (o.get("official") or {}).get("id")
    return None


def pitch_rows(plays, game_pk=None, season=None) -> list[dict]:
    """One row per ``isPitch`` playEvent."""
    out = []
    for play in plays or ():
        abi = play.get("atBatIndex")
        for ev in play.get("playEvents") or ():
            if not ev.get("isPitch"):
                continue
            det = ev.get("details") or {}
            pdata = ev.get("pitchData") or {}
            coord = pdata.get("coordinates") or {}
            out.append({
                "game_pk": game_pk,
                "season": season,
                "at_bat_index": abi,
                "pitch_number": ev.get("pitchNumber"),
                "play_id": ev.get("playId"),
                "call_code": (det.get("call") or {}).get("code"),
                "pitch_type": (det.get("type") or {}).get("code"),
                "start_speed": pdata.get("startSpeed"),
                "end_speed": pdata.get("endSpeed"),
                "zone": pdata.get("zone"),
                "plate_x": coord.get("pX"),
                "plate_z": coord.get("pZ"),
                "sz_top": pdata.get("strikeZoneTop"),
                "sz_bot": pdata.get("strikeZoneBottom"),
                "is_pitch": True,
                "home_plate_umpire_id": _hp_umpire(ev),
            })
    return out


def event_rows(plays, game_pk=None, season=None) -> list[dict]:
    """One row per NON-pitch playEvent, description kept verbatim."""
    out = []
    for play in plays or ():
        abi = play.get("atBatIndex")
        for ev in play.get("playEvents") or ():
            if ev.get("isPitch"):
                continue
            det = ev.get("details") or {}
            out.append({
                "game_pk": game_pk,
                "season": season,
                "at_bat_index": abi,
                "index": ev.get("index"),
                "type": ev.get("type"),
                "event_type": det.get("eventType"),
                "event": det.get("event"),
                "description": det.get("description"),
                "player_id": (ev.get("player") or {}).get("id"),
                "replaced_player_id": (ev.get("replacedPlayer") or {}).get("id"),
                "position_code": (ev.get("position") or {}).get("code"),
                "batting_order": ev.get("battingOrder"),
                "base": ev.get("base"),
                "is_substitution": bool(ev.get("isSubstitution")),
            })
    return out


def game_tables(plays, game_pk=None, season=None, diag: dict | None = None):
    """(play_rows, pitch_rows, event_rows) for one cached game."""
    return (reconstruct_plays(plays, game_pk, season, diag),
            pitch_rows(plays, game_pk, season),
            event_rows(plays, game_pk, season))


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------
def manifest_path(out_dir: Path) -> Path:
    return Path(out_dir) / "manifest.json"


def new_manifest() -> dict:
    # `generated_at` duplicates `built_at` on purpose. `built_at` is this file's
    # own vocabulary and reads naturally beside `build_seconds`; `generated_at`
    # is the key the model registry's freshness layer knows how to age, and this
    # manifest is a registered eval artifact (pbp_corpus_base_state). Without it
    # the registry falls back to the file's mtime, and the deploy box rewrites
    # every mtime on its nightly `git checkout -- .`, so the age it would report
    # there is the checkout rather than the build. One key, written twice, buys
    # an honest age on the only machine where the age matters.
    return {"schema_version": 1, "built_at": None, "generated_at": None,
            "source_cache": None, "source_files_total": 0,
            "seasons": {}, "validation": {}}


def load_manifest(out_dir: Path) -> dict:
    p = manifest_path(out_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _log.warning("manifest unreadable, starting a fresh one: %s", p)
    return new_manifest()


def validate_manifest(man: dict) -> list[str]:
    """Shape problems in a manifest; an empty list means it is well formed."""
    bad = []
    for k in ("schema_version", "built_at", "generated_at", "seasons",
              "validation", "source_files_total", "source_cache"):
        if k not in man:
            bad.append(f"missing top-level key: {k}")
    for season, blk in (man.get("seasons") or {}).items():
        if not str(season).isdigit():
            bad.append(f"season key not a year: {season!r}")
        for k in ("games", "files", "rows"):
            if k not in blk:
                bad.append(f"season {season} missing {k}")
        for t in TABLES:
            if t not in (blk.get("rows") or {}):
                bad.append(f"season {season} rows missing table {t}")
    return bad


def aggregate_counters(man: dict) -> dict:
    """Sum the per-season raw counters recorded in the manifest.

    The corpus is built one season at a time and often across several
    invocations, so the top-level validation block has to be re-derived from
    every season on disk rather than from whatever this process happened to
    walk. Seasons written before ``counters`` existed contribute nothing and are
    skipped rather than guessed at.
    """
    total: dict = {}
    for blk in (man.get("seasons") or {}).values():
        for k, v in (blk.get("counters") or {}).items():
            if isinstance(v, (int, float)):
                total[k] = total.get(k, 0) + v
        worst = (blk.get("validation") or {}).get("runs_worst_example")
        if worst and not total.get("runs_worst"):
            total["runs_worst"] = (1, worst)
    return total


def rates(diag: dict) -> dict:
    """Validation rates from the accumulated counters. Divide-by-zero safe."""
    def rate(num, den):
        d = diag.get(den, 0)
        return None if not d else round(diag.get(num, 0) / d, 6)

    checked = diag.get("state_checked", 0)
    invalid = (diag.get("invalid_occupied_base", 0)
               + diag.get("invalid_outs_gt3", 0)
               + diag.get("invalid_outs_decrease", 0))
    truth_n = diag.get("truth_plays", 0)
    return {
        "plays_checked": checked,
        "invalid_state_plays": invalid,
        "invalid_state_rate": None if not checked else round(invalid / checked, 6),
        "invalid_occupied_base": diag.get("invalid_occupied_base", 0),
        "invalid_outs_gt3": diag.get("invalid_outs_gt3", 0),
        "invalid_outs_decrease": diag.get("invalid_outs_decrease", 0),
        "outs_walk_mismatch": diag.get("outs_walk_mismatch", 0),
        "outs_walk_mismatch_rate": rate("outs_walk_mismatch", "state_checked"),
        "runs_checked": diag.get("runs_checked", 0),
        "runs_mismatch": diag.get("runs_mismatch", 0),
        "runs_mismatch_rate": rate("runs_mismatch", "runs_checked"),
        "runs_worst_example": (diag.get("runs_worst") or (0, None))[1],
        "base_truth_plays": truth_n,
        "base_truth_skipped_prepitch": diag.get("truth_skipped_prepitch", 0),
        "base_occupancy_agree_rate": None if not truth_n else round(
            diag.get("truth_occupancy_ok", 0) / truth_n, 6),
        "base_identity_agree_rate": None if not truth_n else round(
            diag.get("truth_identity_ok", 0) / truth_n, 6),
        "heal_evictions": diag.get("heal_evictions", 0),
        "unknown_movement_end": diag.get("unknown_movement_end", 0),
        "end_none_not_out": diag.get("end_none_not_out", 0),
        "season_sniff_disagreements": diag.get("season_sniff_disagree", 0),
        "unreadable_files": diag.get("unreadable", 0),
        "empty_files": diag.get("empty", 0),
    }


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------
def _schemas():
    """Explicit arrow schemas, one per table.

    Explicit rather than inferred for two reasons. Arrow ints are natively
    nullable, so a missing runner id stays NULL instead of turning into a NaN
    float the way a pandas int column would. And the build streams row groups
    (see :class:`_TableWriter`), so an inferred schema could differ between the
    first chunk and a later one, for instance a column that is all-null in the
    first 400 games and populated after that.
    """
    import pyarrow as pa

    i8, i16, i64, f8 = pa.int8(), pa.int16(), pa.int64(), pa.float64()
    s, b = pa.string(), pa.bool_()
    return {
        "plays": pa.schema([
            ("game_pk", i64), ("season", i16), ("half", s), ("inning", i8),
            ("at_bat_index", i16), ("batter_id", i64), ("bat_side", s),
            ("pitcher_id", i64), ("pitch_hand", s), ("event_type", s),
            ("event", s), ("rbi", i8), ("away_score", i16), ("home_score", i16),
            ("outs_after", i8), ("balls", i8), ("strikes", i8),
            ("leverage_index", f8), ("drama_index", f8),
            ("wp_home_before", f8), ("wp_home_after", f8), ("wpa_home", f8),
            ("outs_before", i8), ("on_first", i64), ("on_second", i64),
            ("on_third", i64), ("runs_scored_on_play", i8),
        ]),
        "pitches": pa.schema([
            ("game_pk", i64), ("season", i16), ("at_bat_index", i16),
            ("pitch_number", i16), ("play_id", s), ("call_code", s),
            ("pitch_type", s), ("start_speed", f8), ("end_speed", f8),
            ("zone", i8), ("plate_x", f8), ("plate_z", f8), ("sz_top", f8),
            ("sz_bot", f8), ("is_pitch", b), ("home_plate_umpire_id", i64),
        ]),
        "events": pa.schema([
            ("game_pk", i64), ("season", i16), ("at_bat_index", i16),
            ("index", i16), ("type", s), ("event_type", s), ("event", s),
            ("description", s), ("player_id", i64), ("replaced_player_id", i64),
            ("position_code", s), ("batting_order", s), ("base", i8),
            ("is_substitution", b),
        ]),
    }


class _TableWriter:
    """Streaming parquet writer: one row group per flush, bounded memory.

    A whole season held in Python dicts before a single write is the failure
    mode this avoids. One season runs about 2,400 games, roughly 187,000 plays
    and 715,000 pitch rows, and a list of dicts that size costs on the order of
    a gigabyte of interpreter overhead. Flushing every few hundred games keeps
    the live set small and the file identical.
    """

    def __init__(self, path: Path, schema):
        import pyarrow.parquet as pq

        self.path = Path(path)
        self.schema = schema
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._w = pq.ParquetWriter(self.path, schema, compression="zstd")
        self.rows = 0

    def write(self, rows: list) -> None:
        import pyarrow as pa

        if not rows:
            return
        table = pa.Table.from_pylist(rows, schema=self.schema)
        self._w.write_table(table)
        self.rows += table.num_rows

    def close(self) -> None:
        self._w.close()


def table_path(out_dir: Path, table: str, season: int) -> Path:
    """``<out>/<table>/<season>/<table>-<season>.parquet``.

    Deliberately NOT the hive ``season=2018`` directory name. Every file also
    carries ``season`` as a real column so a single file read is self-describing,
    and pyarrow refuses to merge the two: reading the tree with a hive directory
    present raises "Field season has incompatible types: int16 vs
    dictionary<values=int32>". A plain year directory keeps both
    ``pq.read_table(out/'plays')`` over every season and a direct read of one
    file working, which is what the consumers of this corpus actually do.
    """
    return Path(out_dir) / table / str(season) / f"{table}-{season}.parquet"


def index_by_season(cache_dir: Path, seasons=None, limit=None) -> dict:
    """{season: [path, ...]} from the head-read sniff, capped at ``limit`` per season.

    The sniff costs about 4.4 ms per file, so a full index of the 19,132-file
    cache runs roughly 85 s. With an explicit ``seasons`` set AND a ``limit`` the
    scan stops as soon as every requested season is full, which is what keeps a
    ``--limit`` test run to seconds instead of a minute and a half.
    """
    out: dict = {}
    for p in sorted(Path(cache_dir).glob("*.json")):
        if (seasons and limit is not None
                and len(out) == len(seasons)
                and all(len(v) >= limit for v in out.values())):
            break
        s = sniff_season(p)
        if s is None:
            continue
        if seasons and s not in seasons:
            continue
        bucket = out.setdefault(s, [])
        if limit is not None and len(bucket) >= limit:
            continue
        bucket.append(p)
    return out


def build(cache_dir: Path, out_dir: Path, *, seasons=None, limit=None,
          force=False, dry_run=False, sample=None, seed=17,
          flush_games: int = 400) -> dict:
    """Build (or resume) the corpus. Returns the manifest dict."""
    t0 = time.time()
    cache_dir, out_dir = Path(cache_dir), Path(out_dir)
    if not cache_dir.is_dir():
        raise SystemExit(f"cache dir not found: {cache_dir}")

    all_json = sorted(cache_dir.glob("*.json"))
    _log.info("cache: %d files under %s", len(all_json), cache_dir)

    by_season = index_by_season(cache_dir, seasons=seasons,
                                limit=None if sample else limit)
    if sample:
        rng = random.Random(seed)
        for s, paths in list(by_season.items()):
            if len(paths) > sample:
                by_season[s] = sorted(rng.sample(paths, sample))
    _log.info("seasons selected: %s",
              {s: len(v) for s, v in sorted(by_season.items())})

    # Always load: --force rebuilds the SELECTED seasons, it must not erase the
    # manifest rows of seasons this invocation was never asked to touch.
    man = load_manifest(out_dir)
    man["source_cache"] = str(cache_dir)
    man["source_files_total"] = len(all_json)

    # A capped run (--limit / --sample) writes a season from a SUBSET of its
    # games. Marking that season "done" would make the next uncapped build skip
    # it and quietly ship a partial corpus, so only an uncapped season counts as
    # complete and a capped one is always rebuilt.
    complete = (limit is None and sample is None)
    for season in sorted(by_season):
        paths = by_season[season]
        prior = (man.get("seasons") or {}).get(str(season)) or {}
        on_disk = all(table_path(out_dir, t, season).exists() for t in TABLES)
        if on_disk and prior.get("complete") and not force:
            _log.info("season %d already built, skipping (use --force to rebuild)",
                      season)
            continue
        if on_disk and not prior.get("complete"):
            _log.info("season %d on disk but written from a capped run, rebuilding",
                      season)

        t1 = time.time()
        buf: dict = {t: [] for t in TABLES}
        counts = {t: 0 for t in TABLES}
        diag: dict = {}
        games = 0
        writers = {}
        if not dry_run:
            schemas = _schemas()
            writers = {t: _TableWriter(table_path(out_dir, t, season), schemas[t])
                       for t in TABLES}

        def flush():
            for t in TABLES:
                if dry_run:
                    counts[t] += len(buf[t])
                else:
                    writers[t].write(buf[t])
                buf[t] = []

        try:
            for path in paths:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    _log.warning("unreadable payload %s: %s", path.name, exc)
                    _bump(diag, "unreadable")
                    continue
                if not isinstance(payload, list) or not payload:
                    _bump(diag, "empty")
                    continue
                try:
                    game_pk = int(path.stem)
                except ValueError:
                    game_pk = None
                parsed_season = season_of_plays(payload)
                if parsed_season is not None and parsed_season != season:
                    _bump(diag, "season_sniff_disagree")
                use_season = parsed_season or season
                a, b, c = game_tables(payload, game_pk, use_season, diag)
                buf["plays"].extend(a)
                buf["pitches"].extend(b)
                buf["events"].extend(c)
                games += 1
                if games % flush_games == 0:
                    flush()
            flush()
        finally:
            for w in writers.values():
                w.close()
        if not dry_run:
            counts = {t: writers[t].rows for t in TABLES}

        elapsed = round(time.time() - t1, 2)
        man["seasons"][str(season)] = {
            "games": games,
            "complete": bool(complete),
            "limit": limit,
            "sample": sample,
            "files": [] if dry_run else [
                f"{t}/{season}/{t}-{season}.parquet" for t in TABLES],
            "bytes": 0 if dry_run else sum(
                table_path(out_dir, t, season).stat().st_size
                for t in TABLES if table_path(out_dir, t, season).exists()),
            "rows": counts,
            "build_seconds": elapsed,
            # raw counters kept so the top-level validation can be re-aggregated
            # across seasons built in SEPARATE invocations, which is the normal
            # way a 19,132-game build gets finished.
            "counters": {k: v for k, v in diag.items() if k != "runs_worst"},
            "validation": rates(diag),
        }
        _log.info("season %d: %d games, %d plays, %d pitches, %d events in %.1fs",
                  season, games, counts["plays"], counts["pitches"],
                  counts["events"], elapsed)

    man["validation"] = rates(aggregate_counters(man))
    man["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    man["generated_at"] = man["built_at"]
    man["build_seconds"] = round(time.time() - t0, 2)
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path(out_dir).write_text(
            json.dumps(man, indent=1, sort_keys=True), encoding="utf-8")
    return man


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Flatten .cache/win_prob into a season-partitioned play/pitch corpus.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=str(DEFAULT_CACHE), help="win_prob cache dir")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="corpus output dir")
    ap.add_argument("--seasons", default=None,
                    help="comma-separated seasons to build (default: all found)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap games PER SEASON (testing)")
    ap.add_argument("--sample", type=int, default=None,
                    help="random games per season instead of the first N (testing)")
    ap.add_argument("--seed", type=int, default=17, help="sample seed")
    ap.add_argument("--flush-games", type=int, default=400,
                    help="games buffered before a parquet row group is written")
    ap.add_argument("--force", action="store_true",
                    help="rebuild seasons whose parquet already exists")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and validate, write nothing")
    ap.add_argument("--validate", action="store_true",
                    help="print the validation block when the build finishes")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    seasons = None
    if args.seasons:
        seasons = {int(s) for s in args.seasons.replace(" ", "").split(",") if s}

    man = build(Path(args.cache), Path(args.out), seasons=seasons,
                limit=args.limit, force=args.force, dry_run=args.dry_run,
                sample=args.sample, seed=args.seed,
                flush_games=args.flush_games)
    if args.validate:
        print(json.dumps(man["validation"], indent=1, sort_keys=True))
    bad = validate_manifest(man)
    if bad:
        for b in bad:
            _log.warning("manifest: %s", b)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
