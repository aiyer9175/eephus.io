#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_runner_moves - the runner record eBR reads (docs/ebr-2026-09-30/EBR_GATE.md part 2.2).

WHAT IT IS. A CLI that flattens the cached winProbability payloads of every FINAL
MLB regular-season game into two season-partitioned parquet tables under
``.cache/pbp_runners/`` (never ``.cache/pbp_corpus``, whose manifest is a
registered artifact with exactly three tables and whose rebuild moves the
/management/ vintage stamp):

  runners/<Y>/runners-<Y>.parquet   one row per ``runners[]`` entry: game_pk,
      season, at_bat_index, play_index, runner id, is_batter, origin base, start,
      end, out base, is_out, out number, ``details.movementReason``,
      ``details.eventType``, is_scoring, the error credit (any
      ``f_throwing_error`` or ``f_fielding_error`` on the entry), the credited
      fielder ids and positions, and the state of the entry's playIndex group
      before and after the group is applied.
  plays/<Y>/pa-<Y>.parquet          one row per play (plate appearance, or a play
      a caught stealing or a pickoff ended): the corpus ``plays`` column names
      (game_pk, season, half, inning, at_bat_index, batter_id, event_type,
      trajectory, outs_before, on_first, on_second, on_third,
      runs_scored_on_play), the batting and fielding club (from the schedule's
      clubs and the half), venue and scheduled innings (from the schedule), hit
      location, Gameday coordinates, exit velocity (stored, never used in the
      number), the in-play outfielder ids (the ``defense`` block), the count
      before the final pitch, the state at the final pitch, the state after the
      play, and the state at every playIndex (``states_json``).

THE GAMES are exactly ``mlb_leverage.season_game_pks(season, game_type="R")``,
frozen into ``schedule/<Y>.json`` with its sha256 in the manifest. A payload
carries no game type, so any other cached payload of that season (a postseason
game, a spring game) is counted and skipped: no postseason play enters a table.

THE HISTORY DIRECTORY (owner answer EBR-Q4 (b)). The seasons 2011 to 2017 and
2020 (``HIST_SEASONS``) are read from ``.cache/win_prob_hist/`` (the output of
tools/fetch_win_prob_hist.py) and from nowhere else; every other season reads
``.cache/win_prob``. The history directory is never read for a 2018-and-later
season, so the frozen seasons stay byte-identical when it fills, and nothing
here writes either source. The one-time re-fetch of a history season paces
its requests a second apart with the house User-Agent.

THE STATE WALK. The state at plate-appearance start is
``build_pbp_corpus.reconstruct_plays`` (imported with tools/ on sys.path, as
test_pbp_corpus.py does), so the repo keeps one walk. Inside the plate
appearance the PA's runner entries are applied NET per playIndex, in order
(each runner's last entry in the group is his destination; every mentioned
runner is lifted first, then the survivors are seated), and a pinch-runner
substitution that names a base swaps the id on that bag at its own index. The
reference is the eBR bundle's ebr_census.py.

STEALS are keyed on ``details.movementReason`` (r_stolen_base_*,
r_caught_stealing_*, r_pickoff_caught_stealing_*), never on
``details.eventType``: on the event type 17 to 41 entries a season score a
caught stealing where the runner was safe.

CODED STEALS (EBR_GATE.md amendment 11.9, owner decision EBR-Q4B-ID). In a
history season only, an entry the feed codes ``r_adv_play`` is read as
``r_stolen_base_<T>`` when its start is the base before T, the same play
carries a steal of T by that runner (an action event ``stolen_base_<T>`` whose
player is the runner, or the result description "<name> steals (n) <T>"), no
entry of his in the play already carries a steal-attempt reason, and it is his
first such entry there (``read_coded_steals``). The season's manifest block
lists every entry so read. A 2018-and-later season is never read this way.

RECEIPTS (EBR_GATE.md part 3), written into the manifest per season with the
sha256 of the cached StatsAPI season hitting lines they read
(``.cache/fa_statsapi_hitting_<Y>.json``, playerPool=All):
  I1  league SB and CS (pickoff caught stealing included) exact; league GIDP
      within 0.5 percent;
  I2  per player SB and CS exact for every player with any; GIDP exact for 97
      percent or more of players with any;
  I3  every final regular-season game of the schedule list is in the record.
I1 and I2 bind completed seasons (November 1 of the season onward, the eWAR
freeze rule); the live season's receipt is reported, never binding.

THE RE-FETCH RULE. An I1 or I2 miss on a completed season triggers ONE re-fetch
of that season's games of the mismatched players into
``.cache/pbp_runners/refetch/`` (never ``.cache/win_prob``) and one re-check;
a re-fetched copy is read in place of the cached payload from then on. The
manifest lists every re-fetched game.

INCREMENTAL AND FROZEN. A run adds only games not already in a season's tables.
A completed season is frozen with the sha256 of each of its files and is never
rewritten; a later run verifies the digests and refuses on a mismatch.

THE MINOR-LEAGUE COPY. ``.cache/game_feeds`` holds 2023 to 2026 minor-league
feeds that the monthly run starts deleting on 2027-07-22 (feed_cache, 400-day
mtime prune). ``--milb`` copies their regular-season games into
``milb/<level>/<season>/`` in the same layout, with counts and walk receipts
only: no minor-league value is computed here.

Run (outside any pipeline run; the MLB backfill takes several minutes):
    python tools/build_runner_moves.py [--seasons 2018,2019,2021-2026] [--milb]
                                       [--workers 8] [--no-refetch]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

_log = logging.getLogger("build_runner_moves")

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))         # mlb_leverage, feed_cache
import build_pbp_corpus as bpc  # noqa: E402  the one state walk

DEFAULT_SOURCE = REPO_ROOT / ".cache" / "win_prob"
DEFAULT_HIST_SOURCE = REPO_ROOT / ".cache" / "win_prob_hist"
DEFAULT_FEEDS = REPO_ROOT / ".cache" / "game_feeds"
DEFAULT_OUT = REPO_ROOT / ".cache" / "pbp_runners"
STATSAPI_LINES = REPO_ROOT / ".cache" / "fa_statsapi_hitting_{season}.json"

SCHEMA_VERSION = 1
DEFAULT_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
#: The seasons read from the history directory, and only these.
HIST_SEASONS = (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2020)
#: Seconds between requests of a history season's re-fetch (one a second).
HIST_FETCH_INTERVAL = 1.0
MILB_SEASONS = (2023, 2024, 2025, 2026)
#: sportId -> partition name of the minor-league copy.
MILB_LEVELS = {11: "aaa", 12: "aa", 13: "high_a", 14: "single_a", 16: "rookie"}
#: A completed season freezes on this (month, day) of its own year
#: (war_source.EWAR_FREEZE_MONTH_DAY, the eWAR rule EBR_GATE.md part 2.9 cites).
FREEZE_MONTH_DAY = (11, 1)
GIDP_LEAGUE_TOL = 0.005
GIDP_PLAYER_SHARE = 0.97

BASES = ("1B", "2B", "3B")
_BASE_NUM = {"1B": 1, "2B": 2, "3B": 3}
_SCORE_ENDS = ("score", "4B")
_ERROR_CREDITS = ("f_throwing_error", "f_fielding_error")
_ATTEMPT_PREFIXES = ("r_stolen_base", "r_caught_stealing", "r_pickoff_caught_stealing")
_CS_PREFIXES = ("r_caught_stealing", "r_pickoff_caught_stealing")
#: Play-ending events that are not a plate appearance (the batter bats again).
_NON_PA_EVENTS = ("caught_stealing", "pickoff", "stolen_base", "wild_pitch", "passed_ball",
                  "balk", "other_out", "other_advance", "runner_double_play", "game_advisory",
                  "defensive_indiff", "batter_timeout", "mound_visit", "injury", "ejection")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def season_complete(season: int, today: _dt.date | None = None) -> bool:
    """True from November 1 of the season's own year (the eWAR freeze rule)."""
    t = today or _dt.date.today()
    m, d = FREEZE_MONTH_DAY
    return t >= _dt.date(int(season), m, d)


def source_for_season(season: int, source: Path = DEFAULT_SOURCE,
                      hist_source: Path = DEFAULT_HIST_SOURCE) -> Path:
    """The payload directory of one season: the history directory for
    HIST_SEASONS, ``source`` (the live winProbability cache) for every other."""
    return Path(hist_source) if int(season) in HIST_SEASONS else Path(source)


def _rid(r: dict):
    return ((r.get("details") or {}).get("runner") or {}).get("id")


def _bits(st: dict) -> int:
    return ((1 if st["1B"] is not None else 0) | (2 if st["2B"] is not None else 0)
            | (4 if st["3B"] is not None else 0))


def _error_credit(r: dict) -> bool:
    return any((c.get("credit") in _ERROR_CREDITS) for c in (r.get("credits") or ()))


def _fielders(r: dict) -> tuple[str, str]:
    ids, pos = [], []
    for c in r.get("credits") or ():
        pid = (c.get("player") or {}).get("id")
        if pid is None:
            continue
        ids.append(str(pid))
        pos.append(str((c.get("position") or {}).get("code") or ""))
    return ",".join(ids), ",".join(pos)


def _is_pa(play: dict) -> bool:
    """A completed plate appearance: the play carries the batter's b_pa credit
    (a probe of 300 games: every batting event carries it, and no caught
    stealing, pickoff, wild pitch or other out that ended a play does). A
    payload with no play-level credits (the minor-league /feed/live plays) falls
    back to the event type: every play whose event is not one of the
    non-plate-appearance events below, which are exactly the events the MLB
    record shows without b_pa in 2018, 2024 and 2026."""
    if "credits" in play:
        return any(c.get("credit") == "b_pa" for c in play.get("credits") or ())
    et = str(((play.get("result") or {}).get("eventType")) or "")
    return bool(et) and not et.startswith(_NON_PA_EVENTS)


def is_steal_attempt(reason) -> bool:
    return bool(reason) and str(reason).startswith(_ATTEMPT_PREFIXES)


def is_caught_stealing(reason) -> bool:
    return bool(reason) and str(reason).startswith(_CS_PREFIXES)


def is_stolen_base(reason) -> bool:
    return bool(reason) and str(reason).startswith("r_stolen_base")


#: Steal target -> the base the runner starts from (EBR_GATE.md amendment 11.9).
_STEAL_FROM = {"2b": "1B", "3b": "2B", "home": "3B"}
_STEAL_WORDS = {"2nd base": "2b", "3rd base": "3b", "home": "home"}


def read_coded_steals(play: dict, ents=None) -> dict:
    """{id(entry): (reason as read, mark)} for the entries of ``play`` that
    amendment 11.9 reads as a steal: ``r_adv_play``, starting on the base
    before the target, under the same runner's stolen-base mark in the play
    (``mark`` is "action" or "description"), with no steal-attempt entry of
    his own in the play; the first such entry of each runner only."""
    ents = list(ents if ents is not None else (play.get("runners") or ()))
    marks: dict = defaultdict(list)
    for ev in play.get("playEvents") or ():
        et = str(((ev.get("details") or {}).get("eventType")) or "")
        pid = (ev.get("player") or {}).get("id")
        if ev.get("type") == "action" and et.startswith("stolen_base_") and pid is not None:
            t = et[len("stolen_base_"):]
            if t in _STEAL_FROM:
                marks[pid].append((t, "action"))
    desc = str((play.get("result") or {}).get("description") or "")
    attempted = {_rid(r) for r in ents
                 if is_steal_attempt((r.get("details") or {}).get("movementReason"))}
    out: dict = {}
    done: set = set()
    for r in ents:
        det = r.get("details") or {}
        x = _rid(r)
        if det.get("movementReason") != "r_adv_play" or x is None or x in attempted or x in done:
            continue
        cands = list(marks.get(x, ()))
        name = (det.get("runner") or {}).get("fullName")
        if name:
            pat = re.escape(str(name)) + r" steals \(\d+\) (2nd base|3rd base|home)"
            cands += [(_STEAL_WORDS[m.group(1)], "description") for m in re.finditer(pat, desc)]
        start = (r.get("movement") or {}).get("start")
        for t, mark in cands:
            if _STEAL_FROM[t] == start:
                out[id(r)] = ("r_stolen_base_" + t, mark)
                done.add(x)
                break
    return out


# --------------------------------------------------------------------------
# the walk inside a plate appearance (pure)
# --------------------------------------------------------------------------
def _apply_group(st: dict, group: list, diag: dict) -> tuple[int, int]:
    """NET application of one playIndex group to the state ``st`` (mutated).

    Each runner's LAST entry in the group is his destination; every mentioned
    runner is lifted first, then the survivors are seated. Returns (outs, runs)."""
    final: dict = {}
    for r in group:
        x = _rid(r)
        if x is None:
            continue
        final[x] = r.get("movement") or {}
    before = dict(st)
    for x in final:
        for b in BASES:
            if st[b] == x:
                st[b] = None
    outs = runs = 0
    for x, mv in final.items():
        end = mv.get("end")
        if mv.get("isOut"):
            outs += 1
        elif end in _SCORE_ENDS:
            runs += 1
        elif end in BASES:
            if st[end] is not None and st[end] != x:
                diag["group_collisions"] = diag.get("group_collisions", 0) + 1
            st[end] = x
        elif end is None:
            for b in BASES:
                if before[b] == x:
                    st[b] = x
    return outs, runs


def _sub_swaps(play: dict, first_pitch_index) -> dict:
    """{event index: (base, new id, replaced id)} for pinch-runner substitutions
    made after the first pitch of the plate appearance (the pre-pitch ones are
    already in reconstruct_plays' start state)."""
    out = {}
    for ev in play.get("playEvents") or ():
        idx = ev.get("index")
        if idx is None or first_pitch_index is None or idx < first_pitch_index:
            continue
        if ev.get("isPitch") or not ev.get("isSubstitution"):
            continue
        if (ev.get("details") or {}).get("eventType") != "offensive_substitution":
            continue
        base = {1: "1B", 2: "2B", 3: "3B"}.get(ev.get("base"))
        new = (ev.get("player") or {}).get("id")
        old = (ev.get("replacedPlayer") or {}).get("id")
        if base is None or new is None:
            continue
        out[idx] = (base, new, old)
    return out


def _pitch_indices(play: dict):
    first = final = in_play = None
    for ev in play.get("playEvents") or ():
        if not ev.get("isPitch"):
            continue
        idx = ev.get("index")
        if first is None:
            first = idx
        final = idx
        if (ev.get("details") or {}).get("isInPlay"):
            in_play = idx
    return first, final, in_play


def _count_before(play: dict, final_idx):
    """(balls, strikes) as the final pitch is thrown: the count after the last
    event before it (an automatic ball or strike included), else 0-0."""
    balls = strikes = 0
    if final_idx is None:
        return None, None
    for ev in play.get("playEvents") or ():
        idx = ev.get("index")
        if idx is None or idx >= final_idx:
            continue
        c = ev.get("count") or {}
        if c.get("balls") is not None:
            balls, strikes = c.get("balls"), c.get("strikes")
    return balls, strikes


def _in_play_event(play: dict, in_play_idx):
    if in_play_idx is None:
        return None
    for ev in play.get("playEvents") or ():
        if ev.get("index") == in_play_idx and ev.get("isPitch"):
            return ev
    return None


def walk_game(plays, *, game_pk: int, season: int, info: dict | None = None,
              level: str = "mlb", diag: dict | None = None,
              count_coded_steals: bool = False) -> tuple[list, list]:
    """(pa_rows, runner_rows) for one game. Pure.

    ``info``: {"away_id", "home_id", "venue_id", "scheduled_innings"} from the
    schedule (MLB) or the feed's gameData (minor leagues). ``count_coded_steals``
    (history seasons only) applies amendment 11.9 (``read_coded_steals``) and
    lists each entry it reads in ``diag["coded_steal_entries"]``."""
    if diag is None:
        diag = {}
    info = info or {}
    away, home = info.get("away_id"), info.get("home_id")
    pa_rows, runner_rows = [], []
    starts = bpc.reconstruct_plays(plays, game_pk=game_pk, season=season, diag=diag)
    for play, srow in zip(plays or (), starts):
        about = play.get("about") or {}
        result = play.get("result") or {}
        half = about.get("halfInning")
        top = str(half or "").startswith("top")
        st = {"1B": srow["on_first"], "2B": srow["on_second"], "3B": srow["on_third"]}
        outs = int(srow["outs_before"] or 0)
        first_idx, final_idx, in_play_idx = _pitch_indices(play)
        subs = _sub_swaps(play, first_idx)
        ents = bpc._sorted_runners(play)
        coded = read_coded_steals(play, ents) if count_coded_steals else {}
        groups: dict = defaultdict(list)
        order: list = []
        for r in ents:
            pi = (r.get("details") or {}).get("playIndex")
            pi = -1 if pi is None else pi
            if pi not in groups:
                order.append(pi)
            groups[pi].append(r)
        indices = sorted(set(order) | set(subs))
        fp_state = None
        runs_fp = 0
        states = []
        seq = 0
        for idx in indices:
            if fp_state is None and final_idx is not None and idx >= final_idx:
                fp_state = (st["1B"], st["2B"], st["3B"], outs)
            if idx in subs:
                base, new, old = subs[idx]
                for b in BASES:
                    if st[b] in (new, old):
                        st[b] = None
                st[base] = new
            grp = groups.get(idx)
            if not grp:
                continue
            b_before, o_before = _bits(st), outs
            ids_before = (st["1B"], st["2B"], st["3B"])
            n_out, n_run = _apply_group(st, grp, diag)
            outs += n_out
            if final_idx is not None and idx >= final_idx:
                runs_fp += n_run
            b_after = _bits(st)
            states.append([idx, ids_before[0], ids_before[1], ids_before[2], o_before,
                           st["1B"], st["2B"], st["3B"], outs, n_run])
            for r in grp:
                mv = r.get("movement") or {}
                det = r.get("details") or {}
                fid, fpos = _fielders(r)
                x = _rid(r)
                reason = det.get("movementReason")
                if id(r) in coded:
                    reason, mark = coded[id(r)]
                    diag["coded_steals"] = diag.get("coded_steals", 0) + 1
                    diag.setdefault("coded_steal_entries", []).append(
                        [int(game_pk), play.get("atBatIndex"), idx, x, mv.get("start"),
                         det.get("movementReason"), reason, mark])
                runner_rows.append({
                    "game_pk": game_pk, "season": season, "level": level,
                    "at_bat_index": play.get("atBatIndex"), "play_index": idx,
                    "seq": seq, "runner_id": x,
                    "is_batter": bool(mv.get("originBase") is None
                                      and x == ((play.get("matchup") or {}).get("batter") or {}).get("id")),
                    "batter_id": ((play.get("matchup") or {}).get("batter") or {}).get("id"),
                    "half": half, "inning": about.get("inning"),
                    "bat_team_id": away if top else home,
                    "origin_base": mv.get("originBase"), "start": mv.get("start"),
                    "end": mv.get("end"), "out_base": mv.get("outBase"),
                    "is_out": bool(mv.get("isOut")), "out_number": mv.get("outNumber"),
                    "movement_reason": reason,
                    "event_type": det.get("eventType"),
                    "is_scoring": bool(det.get("isScoringEvent")),
                    "error_credit": _error_credit(r),
                    "fielder_ids": fid, "fielder_positions": fpos,
                    "base_before_group": b_before, "outs_before_group": o_before,
                    "base_after_group": b_after, "outs_after_group": outs,
                    "runs_group": n_run, "is_final_pitch_group": bool(
                        final_idx is not None and idx >= final_idx),
                })
                seq += 1
        if fp_state is None:
            fp_state = (st["1B"], st["2B"], st["3B"], outs)
        co = (play.get("count") or {}).get("outs")
        if co is not None and co != outs:
            diag["pa_outs_walk_mismatch"] = diag.get("pa_outs_walk_mismatch", 0) + 1
        ip = _in_play_event(play, in_play_idx)
        hd = (ip or {}).get("hitData") or {}
        coords = hd.get("coordinates") or {}
        dfn = (ip or {}).get("defense") or {}
        balls, strikes = _count_before(play, final_idx)
        pa_rows.append({
            "game_pk": game_pk, "season": season, "level": level,
            "half": half, "inning": about.get("inning"),
            "at_bat_index": play.get("atBatIndex"),
            "batter_id": srow["batter_id"],
            "bat_team_id": away if top else home, "fld_team_id": home if top else away,
            "venue_id": info.get("venue_id"),
            "scheduled_innings": info.get("scheduled_innings"),
            "event_type": result.get("eventType"), "event": result.get("event"),
            "is_pa": _is_pa(play),
            "trajectory": hd.get("trajectory") if ip is not None else srow["trajectory"],
            "hit_location": (str(hd.get("location")) if hd.get("location") is not None else None),
            "coord_x": coords.get("coordX"), "coord_y": coords.get("coordY"),
            "launch_speed": hd.get("launchSpeed"),
            "of_left_id": (dfn.get("left") or {}).get("id"),
            "of_center_id": (dfn.get("center") or {}).get("id"),
            "of_right_id": (dfn.get("right") or {}).get("id"),
            "fp_balls": balls, "fp_strikes": strikes,
            "final_pitch_index": final_idx, "in_play_index": in_play_idx,
            "outs_before": srow["outs_before"],
            "on_first": srow["on_first"], "on_second": srow["on_second"],
            "on_third": srow["on_third"],
            "fp_on_first": fp_state[0], "fp_on_second": fp_state[1],
            "fp_on_third": fp_state[2], "fp_outs": fp_state[3],
            "end_on_first": st["1B"], "end_on_second": st["2B"], "end_on_third": st["3B"],
            "end_outs": outs, "outs_after": srow["outs_after"],
            "runs_scored_on_play": srow["runs_scored_on_play"], "runs_fp": runs_fp,
            "runner_placed": any(((ev.get("details") or {}).get("eventType") == "runner_placed")
                                 for ev in play.get("playEvents") or ()),
            "states_json": json.dumps(states, separators=(",", ":")),
        })
    return pa_rows, runner_rows


# --------------------------------------------------------------------------
# tables (pandas only inside these functions, so the walk stays import-light)
# --------------------------------------------------------------------------
PA_INT_COLS = ("game_pk", "season", "inning", "at_bat_index", "batter_id", "bat_team_id",
               "fld_team_id", "venue_id", "scheduled_innings", "of_left_id", "of_center_id",
               "of_right_id", "fp_balls", "fp_strikes", "final_pitch_index", "in_play_index",
               "outs_before", "on_first", "on_second", "on_third", "fp_on_first",
               "fp_on_second", "fp_on_third", "fp_outs", "end_on_first", "end_on_second",
               "end_on_third", "end_outs", "outs_after", "runs_scored_on_play", "runs_fp")
RUNNER_INT_COLS = ("game_pk", "season", "at_bat_index", "play_index", "seq", "runner_id",
                   "batter_id", "inning", "bat_team_id", "out_number", "base_before_group",
                   "outs_before_group", "base_after_group", "outs_after_group", "runs_group")


def _frame(rows: list, int_cols, sort_cols):
    import pandas as pd
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.array([None if v is None or v != v else int(v) for v in df[c]],
                             dtype="Int64")
    df = df.sort_values(list(sort_cols), kind="mergesort").reset_index(drop=True)
    return df


def write_table(df, path: Path) -> str:
    """Deterministic parquet write; returns the file's sha256."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy", write_statistics=False)
    data = buf.getvalue()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return sha256_bytes(data)


def read_table(path: Path):
    import pandas as pd
    return pd.read_parquet(path)


# --------------------------------------------------------------------------
# schedule (the only network the MLB build needs)
# --------------------------------------------------------------------------
def fetch_schedule_meta(season: int) -> dict:
    """{game_pk: {away_id, home_id, venue_id, scheduled_innings, coded_state}} for
    the FINAL regular-season games of a season (the schedule call and the Final
    rule of mlb_leverage.season_game_pks). A game listed on several dates (a
    postponement made up later) takes the occurrence the schedule codes "F"
    (played to a final), else its first Final occurrence."""
    import feed_cache
    import mlb_leverage
    resp = feed_cache.SESSION.get(mlb_leverage.SCHEDULE_API,
                                  params={"sportId": 1, "season": int(season), "gameType": "R"},
                                  timeout=30)
    resp.raise_for_status()
    out: dict = {}
    for d in resp.json().get("dates", []):
        for g in d.get("games", []):
            stt = g.get("status") or {}
            if stt.get("abstractGameState") != "Final":
                continue
            pk = g.get("gamePk")
            if not pk:
                continue
            pk = int(pk)
            coded = stt.get("codedGameState")
            if pk in out and not (coded == "F" and out[pk]["coded_state"] != "F"):
                continue
            t = g.get("teams") or {}
            out[pk] = {"away_id": ((t.get("away") or {}).get("team") or {}).get("id"),
                       "home_id": ((t.get("home") or {}).get("team") or {}).get("id"),
                       "venue_id": (g.get("venue") or {}).get("id"),
                       "scheduled_innings": g.get("scheduledInnings"),
                       "coded_state": coded}
    return out


def live_schedule(season: int) -> list:
    """[[game_pk, date, away, home, venue, scheduled_innings, coded_state], ...]: the
    games are EXACTLY mlb_leverage.season_game_pks(season, game_type="R"). A game
    the schedule codes "C" (cancelled) or "D" (postponed, never made up) is still
    "Final" to the schedule, so the list carries it, and it has no play-by-play:
    the endpoint answers 404 "Game data couldn't be found" (2019's 567304, DET at
    CWS on 2019-09-27; 2024's 746577, HOU at CLE on 2024-09-29; both rained out)."""
    import mlb_leverage
    games = mlb_leverage.season_game_pks(int(season), game_type="R")
    meta = fetch_schedule_meta(season)
    out = []
    for pk, date in games:
        m = meta.get(int(pk)) or {}
        out.append([int(pk), date, m.get("away_id"), m.get("home_id"), m.get("venue_id"),
                    m.get("scheduled_innings"), m.get("coded_state")])
    out.sort(key=lambda r: r[0])
    return out


# --------------------------------------------------------------------------
# one game from disk (worker)
# --------------------------------------------------------------------------
def _load_payload(pk: int, source: Path, refetch: Path):
    import orjson
    for d in (refetch, source):
        p = Path(d) / f"{pk}.json"
        if p.exists():
            try:
                data = orjson.loads(p.read_bytes())
            except Exception:  # noqa: BLE001 - an unreadable payload is a missing game
                return None, "unreadable"
            # mlb_leverage._plays_of: a bare list, or {"winProbability": [...]}
            plays = data if isinstance(data, list) else ((data or {}).get("winProbability") or [])
            if not isinstance(plays, list) or not plays:
                return None, "empty"
            return plays, ("refetch" if d == refetch else "cache")
    return None, "missing"


def _int_counters(diag: dict) -> dict:
    """The integer tallies of a walk's diag (runs_worst is a detail, not a count)."""
    return {k: v for k, v in diag.items() if isinstance(v, int) and not isinstance(v, bool)}


def _game_job(args):
    pk, season, info, source, refetch = args
    plays, how = _load_payload(pk, Path(source), Path(refetch))
    if plays is None:
        return pk, how, [], [], {}
    diag: dict = {}
    pa, rn = walk_game(plays, game_pk=pk, season=season, info=info, diag=diag,
                       count_coded_steals=int(season) in HIST_SEASONS)
    counters = _int_counters(diag)
    if diag.get("coded_steal_entries"):
        counters["coded_steal_entries"] = diag["coded_steal_entries"]
    return pk, how, pa, rn, counters


def _milb_job(path):
    import orjson
    try:
        d = orjson.loads(Path(path).read_bytes())
    except Exception:  # noqa: BLE001
        return None
    gd = d.get("gameData") or {}
    g = gd.get("game") or {}
    if g.get("type") != "R":
        return ("skip", "not_regular")
    if ((gd.get("status") or {}).get("abstractGameState")) != "Final":
        return ("skip", "not_final")
    sport = (((gd.get("teams") or {}).get("home") or {}).get("sport") or {}).get("id")
    level = MILB_LEVELS.get(sport)
    if level is None:
        return ("skip", f"sport_{sport}")
    try:
        season = int(g.get("season"))
    except (TypeError, ValueError):
        return ("skip", "no_season")
    plays = ((d.get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    if not plays:
        return ("skip", "no_plays")
    teams = gd.get("teams") or {}
    info = {"away_id": (teams.get("away") or {}).get("id"),
            "home_id": (teams.get("home") or {}).get("id"),
            "venue_id": (gd.get("venue") or {}).get("id"),
            "scheduled_innings": ((d.get("liveData") or {}).get("linescore") or {}).get("scheduledInnings")}
    pk = int(g.get("pk"))
    diag: dict = {}
    pa, rn = walk_game(plays, game_pk=pk, season=season, info=info, level=level, diag=diag)
    return ("ok", level, season, pk, pa, rn, _int_counters(diag))


# --------------------------------------------------------------------------
# receipts I1 to I3
# --------------------------------------------------------------------------
def official_lines(season: int, path: Path | None = None):
    """({mlbam: Counter(sb, cs, gidp, pa)}, sha256, path) from the cached StatsAPI
    season hitting lines (summed over a player's club splits), or (None, None, p)."""
    p = Path(path) if path else Path(str(STATSAPI_LINES).format(season=int(season)))
    if not p.exists():
        return None, None, p
    raw_bytes = p.read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    body = raw.get("body", raw) if isinstance(raw, dict) else raw
    if isinstance(body, str):
        body = json.loads(body)
    out: dict = {}
    for x in ((body.get("stats") or [{}])[0].get("splits") or []):
        pid = (x.get("player") or {}).get("id")
        if pid is None:
            continue
        stt = x.get("stat") or {}
        c = out.setdefault(int(pid), Counter())
        c["sb"] += int(stt.get("stolenBases") or 0)
        c["cs"] += int(stt.get("caughtStealing") or 0)
        c["gidp"] += int(stt.get("groundIntoDoublePlay") or 0)
        c["pa"] += int(stt.get("plateAppearances") or 0)
    return out, sha256_bytes(raw_bytes), p


def record_counts(pa_df, rn_df) -> dict:
    """{mlbam: Counter(sb, cs, gidp, pa)} from the record."""
    out: dict = defaultdict(Counter)
    if rn_df is not None and len(rn_df):
        reasons = rn_df["movement_reason"].fillna("")
        for pid, rs in zip(rn_df["runner_id"], reasons):
            if pid is None or pid != pid:
                continue
            if rs.startswith("r_stolen_base"):
                out[int(pid)]["sb"] += 1
            elif rs.startswith(_CS_PREFIXES):
                out[int(pid)]["cs"] += 1
    if pa_df is not None and len(pa_df):
        for pid, et, ispa in zip(pa_df["batter_id"], pa_df["event_type"], pa_df["is_pa"]):
            if pid is None or pid != pid:
                continue
            if et == "grounded_into_double_play":
                out[int(pid)]["gidp"] += 1
            if bool(ispa):
                out[int(pid)]["pa"] += 1
    return out


NO_PLAY_CODES = ("C", "D")


def cancelled_games(scheduled: list) -> list:
    """Listed games the schedule codes cancelled ("C") or postponed and never made
    up ("D"): final to the schedule, never played."""
    return sorted(int(r[0]) for r in scheduled if len(r) > 6 and r[6] in NO_PLAY_CODES)


def identity_receipts(season: int, pa_df, rn_df, scheduled: list, present: set,
                      official=None, official_sha=None, official_path=None) -> dict:
    """The I1 to I3 receipt block of one season. I3 counts a listed game the
    schedule codes cancelled or postponed (never played) as complete with no play
    when the record holds no payload for it."""
    mine = record_counts(pa_df, rn_df)
    blk: dict = {"season": int(season)}
    sched_pks = [int(r[0]) for r in scheduled]
    cancelled = [pk for pk in cancelled_games(scheduled) if pk not in set(present)]
    missing = sorted(set(sched_pks) - set(present) - set(cancelled))
    blk["I3"] = {"games_scheduled": len(sched_pks), "games_present": len(set(sched_pks) & set(present)),
                 "cancelled_no_play": cancelled, "missing": missing[:200],
                 "n_missing": len(missing), "pass": not missing}
    if official is None:
        blk["I1"] = blk["I2"] = {"pass": None, "note": "no cached StatsAPI season hitting lines"}
        blk["statsapi_lines"] = {"path": str(official_path) if official_path else None, "sha256": None}
        return blk
    blk["statsapi_lines"] = {"path": Path(official_path).name if official_path else None,
                             "sha256": official_sha}
    lg_mine = Counter()
    lg_off = Counter()
    for c in mine.values():
        lg_mine.update(c)
    for c in official.values():
        lg_off.update(c)
    gd = lg_mine["gidp"] - lg_off["gidp"]
    gtol = abs(gd) <= GIDP_LEAGUE_TOL * max(1, lg_off["gidp"])
    blk["I1"] = {"sb": [lg_mine["sb"], lg_off["sb"]], "cs": [lg_mine["cs"], lg_off["cs"]],
                 "gidp": [lg_mine["gidp"], lg_off["gidp"]],
                 "pa": [lg_mine["pa"], lg_off["pa"]],
                 "pass": bool(lg_mine["sb"] == lg_off["sb"] and lg_mine["cs"] == lg_off["cs"] and gtol)}
    ids = set(mine) | set(official)
    res = {}
    mism: dict = {}
    for stat in ("sb", "cs", "gidp"):
        anyone = [i for i in ids if official.get(i, {}).get(stat, 0) > 0 or mine.get(i, {}).get(stat, 0) > 0]
        bad = sorted(i for i in anyone if official.get(i, {}).get(stat, 0) != mine.get(i, {}).get(stat, 0))
        res[stat] = {"players_with_any": len(anyone), "exact": len(anyone) - len(bad),
                     "exact_share": (round((len(anyone) - len(bad)) / len(anyone), 6) if anyone else None)}
        mism[stat] = bad
    i2_pass = (not mism["sb"] and not mism["cs"]
               and (res["gidp"]["exact_share"] is None or res["gidp"]["exact_share"] >= GIDP_PLAYER_SHARE))
    blk["I2"] = dict(res, n_mismatch={k: len(v) for k, v in mism.items()}, pass_=None)
    blk["I2"].pop("pass_")
    blk["I2"]["pass"] = bool(i2_pass)
    blk["_mismatched_players"] = sorted(set(mism["sb"]) | set(mism["cs"])
                                        | (set(mism["gidp"]) if not i2_pass else set()))
    return blk


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------
def manifest_path(out_dir: Path) -> Path:
    return Path(out_dir) / "manifest.json"


def load_manifest(out_dir: Path) -> dict:
    p = manifest_path(out_dir)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"schema_version": SCHEMA_VERSION, "built_at": None, "generated_at": None,
            "source_cache": None, "seasons": {}, "milb": {}, "refetched": {}}


def write_manifest(out_dir: Path, man: dict) -> None:
    p = manifest_path(out_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def season_paths(out_dir: Path, season: int, level: str | None = None) -> tuple[Path, Path]:
    base = Path(out_dir) if level is None else Path(out_dir) / "milb" / level
    return (base / "plays" / str(season) / f"pa-{season}.parquet",
            base / "runners" / str(season) / f"runners-{season}.parquet")


class FrozenSeasonChanged(RuntimeError):
    pass


def _verify_frozen(out_dir: Path, blk: dict, season: int, level: str | None = None) -> None:
    pa_p, rn_p = season_paths(out_dir, season, level)
    for p, key in ((pa_p, "pa_sha256"), (rn_p, "runners_sha256")):
        if not p.exists() or sha256_file(p) != blk.get(key):
            raise FrozenSeasonChanged(f"frozen season {level or 'mlb'} {season}: {p.name} "
                                      f"does not match its manifest digest")


def _run_games(jobs: list, workers: int):
    if workers <= 1 or len(jobs) < 50:
        return [_game_job(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_game_job, jobs, chunksize=25))


def _count_skipped(source: Path, season: int, listed: set) -> int:
    n = 0
    for p in Path(source).glob("*.json"):
        try:
            pk = int(p.stem)
        except ValueError:
            continue
        if pk in listed:
            continue
        if bpc.sniff_season(p) == int(season):
            n += 1
    return n


def refetch_games(pks, refetch_dir: Path, fetcher=None, *, interval: float = 0.25) -> list:
    """One re-fetch of each game into refetch_dir (never .cache/win_prob), the
    requests ``interval`` seconds apart with the house User-Agent."""
    refetch_dir = Path(refetch_dir)
    refetch_dir.mkdir(parents=True, exist_ok=True)
    got = []
    if fetcher is None:
        import feed_cache
        import mlb_leverage
        from fetch_win_prob_hist import house_user_agent
        headers = {"User-Agent": house_user_agent()}

        def fetcher(pk):
            time.sleep(interval)
            r = feed_cache.SESSION.get(f"{mlb_leverage.WP_API}/{int(pk)}/winProbability",
                                      headers=headers, timeout=30)
            r.raise_for_status()
            return r.content
    for pk in sorted(set(int(p) for p in pks)):
        try:
            body = fetcher(pk)
        except Exception as e:  # noqa: BLE001 - one failed re-fetch leaves the cached copy
            _log.warning("re-fetch %s failed: %s", pk, e)
            continue
        tmp = refetch_dir / f"{pk}.json.tmp"
        tmp.write_bytes(body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))
        tmp.replace(refetch_dir / f"{pk}.json")
        got.append(pk)
    return got


def build_season(season: int, *, out_dir: Path = DEFAULT_OUT, source: Path = DEFAULT_SOURCE,
                 schedule=None, workers: int = 8, today: _dt.date | None = None,
                 official_path: Path | None = None, allow_refetch: bool = True,
                 fetcher=None, man: dict | None = None,
                 hist_source: Path = DEFAULT_HIST_SOURCE) -> dict:
    """Build (or extend) one MLB season. Returns its manifest block. A history
    season (HIST_SEASONS) reads ``hist_source``; every other reads ``source``."""
    out_dir = Path(out_dir)
    source = source_for_season(season, source, hist_source)
    interval = HIST_FETCH_INTERVAL if int(season) in HIST_SEASONS else 0.25
    refetch_dir = out_dir / "refetch"
    own_man = man is None
    man = man if man is not None else load_manifest(out_dir)
    sblk = (man.get("seasons") or {}).get(str(season))
    if sblk and sblk.get("frozen"):
        _verify_frozen(out_dir, sblk, season)
        return sblk
    t0 = time.time()
    sched_path = out_dir / "schedule" / f"{season}.json"
    if schedule is None:
        schedule = live_schedule(season)
    sched_bytes = json.dumps(schedule, separators=(",", ":")).encode("utf-8")
    sched_path.parent.mkdir(parents=True, exist_ok=True)
    sched_path.write_bytes(sched_bytes)
    info_of = {int(r[0]): {"away_id": r[2], "home_id": r[3], "venue_id": r[4],
                           "scheduled_innings": r[5]} for r in schedule}
    pa_p, rn_p = season_paths(out_dir, season)
    import pandas as pd
    old_pa = read_table(pa_p) if pa_p.exists() else None
    old_rn = read_table(rn_p) if rn_p.exists() else None
    have = set(int(x) for x in old_pa["game_pk"].unique()) if old_pa is not None and len(old_pa) else set()
    cancelled = set(cancelled_games(schedule))
    todo = [pk for pk in sorted(info_of) if pk not in have
            and not (pk in cancelled and not (Path(source) / f"{pk}.json").exists()
                     and not (refetch_dir / f"{pk}.json").exists())]
    # A listed game with no payload in either directory is fetched ONCE into
    # refetch/ (never .cache/win_prob), so I3 can close without the cache.
    absent = [pk for pk in todo if not (Path(source) / f"{pk}.json").exists()
              and not (refetch_dir / f"{pk}.json").exists()]
    filled = []
    if absent and allow_refetch:
        filled = refetch_games(absent, refetch_dir, fetcher, interval=interval)
        man.setdefault("filled", {})[str(season)] = sorted(
            set((man.get("filled") or {}).get(str(season), [])) | set(filled))
    jobs = [(pk, int(season), info_of[pk], str(source), str(refetch_dir)) for pk in todo]
    results = _run_games(jobs, workers)
    diag: Counter = Counter((sblk or {}).get("counters") or {})
    coded: dict = defaultdict(list)          # game_pk -> amendment 11.9 entries
    for e in (sblk or {}).get("coded_steals") or ():
        if int(e[0]) in have:
            coded[int(e[0])].append(e)
    how_n: Counter = Counter()
    new_pa, new_rn = [], []
    for pk, how, pa, rn, dg in results:
        coded[int(pk)] = list(dg.pop("coded_steal_entries", None) or ())
        how_n[how] += 1
        new_pa.extend(pa)
        new_rn.extend(rn)
        diag.update(dg)
    pa_df = _frame(new_pa, PA_INT_COLS, ("game_pk", "at_bat_index"))
    rn_df = _frame(new_rn, RUNNER_INT_COLS, ("game_pk", "at_bat_index", "seq"))
    if old_pa is not None and len(old_pa):
        pa_df = pd.concat([old_pa, pa_df], ignore_index=True) if len(pa_df) else old_pa
        pa_df = pa_df.sort_values(["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
    if old_rn is not None and len(old_rn):
        rn_df = pd.concat([old_rn, rn_df], ignore_index=True) if len(rn_df) else old_rn
        rn_df = rn_df.sort_values(["game_pk", "at_bat_index", "seq"], kind="mergesort").reset_index(drop=True)
    present = set(int(x) for x in pa_df["game_pk"].unique()) if len(pa_df) else set()
    official, off_sha, off_path = official_lines(season, official_path)
    rec = identity_receipts(season, pa_df, rn_df, schedule, present, official, off_sha, off_path)
    complete = season_complete(season, today)
    refetched = []
    if (complete and allow_refetch and official is not None
            and not (rec["I1"]["pass"] and rec["I2"]["pass"])
            and not (man.get("refetched") or {}).get(str(season))):
        bad = set(rec.get("_mismatched_players") or ())
        if len(pa_df):
            g1 = set(int(x) for x in pa_df.loc[pa_df["batter_id"].isin(list(bad)), "game_pk"].unique())
        else:
            g1 = set()
        if len(rn_df):
            g2 = set(int(x) for x in rn_df.loc[rn_df["runner_id"].isin(list(bad)), "game_pk"].unique())
        else:
            g2 = set()
        games = sorted((g1 | g2) & set(info_of))
        refetched = refetch_games(games, refetch_dir, fetcher, interval=interval)
        man.setdefault("refetched", {})[str(season)] = refetched
        if refetched:
            jobs = [(pk, int(season), info_of[pk], str(source), str(refetch_dir)) for pk in refetched]
            redo = _run_games(jobs, workers)
            keep_pa = pa_df[~pa_df["game_pk"].isin(refetched)]
            keep_rn = rn_df[~rn_df["game_pk"].isin(refetched)]
            r_pa, r_rn = [], []
            for pk, how, pa, rn, dg in redo:
                coded[int(pk)] = list(dg.pop("coded_steal_entries", None) or ())
                r_pa.extend(pa)
                r_rn.extend(rn)
            pa_df = pd.concat([keep_pa, _frame(r_pa, PA_INT_COLS, ("game_pk", "at_bat_index"))],
                              ignore_index=True).sort_values(["game_pk", "at_bat_index"],
                                                             kind="mergesort").reset_index(drop=True)
            rn_df = pd.concat([keep_rn, _frame(r_rn, RUNNER_INT_COLS, ("game_pk", "at_bat_index", "seq"))],
                              ignore_index=True).sort_values(["game_pk", "at_bat_index", "seq"],
                                                             kind="mergesort").reset_index(drop=True)
            present = set(int(x) for x in pa_df["game_pk"].unique())
            rec = identity_receipts(season, pa_df, rn_df, schedule, present, official, off_sha, off_path)
    rec.pop("_mismatched_players", None)
    if (not results and not refetched and pa_p.exists() and rn_p.exists()
            and sblk and sblk.get("pa_sha256") == sha256_file(pa_p)
            and sblk.get("runners_sha256") == sha256_file(rn_p)):
        pa_sha, rn_sha = sblk["pa_sha256"], sblk["runners_sha256"]   # nothing new: no rewrite
    else:
        pa_sha = write_table(pa_df, pa_p)
        rn_sha = write_table(rn_df, rn_p)
    skipped = _count_skipped(source, season, set(info_of)) if Path(source).exists() else None
    blk = {
        "season": int(season), "source": Path(source).name,
        "games_scheduled": len(info_of), "games_present": len(present),
        "games_added_this_run": int(sum(v for k, v in how_n.items() if k in ("cache", "refetch"))),
        "payloads_missing": int(how_n.get("missing", 0) + how_n.get("empty", 0)
                                + how_n.get("unreadable", 0)),
        "other_cached_payloads_skipped": skipped,
        "rows": {"pa": int(len(pa_df)), "runners": int(len(rn_df))},
        "files": {"pa": str(pa_p.relative_to(out_dir)).replace("\\", "/"),
                  "runners": str(rn_p.relative_to(out_dir)).replace("\\", "/")},
        "pa_sha256": pa_sha, "runners_sha256": rn_sha,
        "schedule_sha256": sha256_bytes(sched_bytes),
        "counters": dict(sorted(diag.items())),
        "receipts": rec,
        "refetched_games": refetched or (man.get("refetched") or {}).get(str(season), []),
        "filled_games": (man.get("filled") or {}).get(str(season), []),
        **({"coded_steals": [e for pk in sorted(coded) for e in coded[pk]]}
           if int(season) in HIST_SEASONS else {}),
        "complete": bool(complete),
        "frozen": bool(complete and rec["I3"]["pass"] and rec["I1"].get("pass") is True
                         and rec["I2"].get("pass") is True),
        "build_seconds": round(time.time() - t0, 2),
    }
    man.setdefault("seasons", {})[str(season)] = blk
    if own_man:
        now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
        man["built_at"] = man["generated_at"] = now
        man["source_cache"] = str(Path(source))
        write_manifest(out_dir, man)
    return blk


def build_milb(*, out_dir: Path = DEFAULT_OUT, feeds: Path = DEFAULT_FEEDS, workers: int = 8,
               today: _dt.date | None = None, man: dict | None = None,
               seasons=MILB_SEASONS) -> dict:
    """The minor-league copy: regular-season games of .cache/game_feeds, counts
    and walk receipts only. Incremental by game_pk; a completed level-season is
    frozen and never rewritten (its source feeds get pruned)."""
    import pandas as pd
    out_dir = Path(out_dir)
    own_man = man is None
    man = man if man is not None else load_manifest(out_dir)
    mblk = man.setdefault("milb", {})
    files = sorted(Path(feeds).glob("*.json")) if Path(feeds).exists() else []
    skips: Counter = Counter()
    by: dict = defaultdict(lambda: {"pa": [], "rn": [], "diag": Counter(), "pks": set()})
    paths = [str(p) for p in files]
    if workers > 1 and len(paths) > 50:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            res_iter = list(ex.map(_milb_job, paths, chunksize=40))
    else:
        res_iter = [_milb_job(p) for p in paths]
    for res in res_iter:
        if res is None:
            skips["unreadable"] += 1
            continue
        if res[0] == "skip":
            skips[res[1]] += 1
            continue
        _, level, season, pk, pa, rn, dg = res
        if season not in seasons:
            skips["season_out_of_scope"] += 1
            continue
        key = (level, season)
        by[key]["pa"].extend(pa)
        by[key]["rn"].extend(rn)
        by[key]["diag"].update(dg)
        by[key]["pks"].add(pk)
    for (level, season), acc in sorted(by.items()):
        name = f"{level}|{season}"
        blk = mblk.get(name)
        if blk and blk.get("frozen"):
            _verify_frozen(out_dir, blk, season, level)
            continue
        pa_p, rn_p = season_paths(out_dir, season, level)
        old_pa = read_table(pa_p) if pa_p.exists() else None
        old_rn = read_table(rn_p) if rn_p.exists() else None
        have = set(int(x) for x in old_pa["game_pk"].unique()) if old_pa is not None and len(old_pa) else set()
        pa_new = [r for r in acc["pa"] if r["game_pk"] not in have]
        rn_new = [r for r in acc["rn"] if r["game_pk"] not in have]
        pa_df = _frame(pa_new, PA_INT_COLS, ("game_pk", "at_bat_index"))
        rn_df = _frame(rn_new, RUNNER_INT_COLS, ("game_pk", "at_bat_index", "seq"))
        if old_pa is not None and len(old_pa):
            pa_df = (pd.concat([old_pa, pa_df], ignore_index=True) if len(pa_df) else old_pa)
            pa_df = pa_df.sort_values(["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
        if old_rn is not None and len(old_rn):
            rn_df = (pd.concat([old_rn, rn_df], ignore_index=True) if len(rn_df) else old_rn)
            rn_df = rn_df.sort_values(["game_pk", "at_bat_index", "seq"], kind="mergesort").reset_index(drop=True)
        counts = record_counts(pa_df, rn_df)
        lg = Counter()
        for c in counts.values():
            lg.update(c)
        dg = Counter((blk or {}).get("counters") or {})
        dg.update(acc["diag"])
        complete = season_complete(season, today)
        mblk[name] = {
            "level": level, "season": int(season),
            "games": int(pa_df["game_pk"].nunique()) if len(pa_df) else 0,
            "rows": {"pa": int(len(pa_df)), "runners": int(len(rn_df))},
            "counts": {"sb": lg["sb"], "cs": lg["cs"], "gidp": lg["gidp"], "pa": lg["pa"]},
            "games_with_venue": int(pa_df.drop_duplicates("game_pk")["venue_id"].notna().sum()) if len(pa_df) else 0,
            "receipts": {
                "outs_walk_mismatch": int(dg.get("outs_walk_mismatch", 0)),
                "runs_mismatch": int(dg.get("runs_mismatch", 0)),
                "truth_plays": int(dg.get("truth_plays", 0)),
                "truth_occupancy_ok": int(dg.get("truth_occupancy_ok", 0)),
                "note": ("walk receipts only; the official minor-league SB, CS and GIDP lines "
                         "are not cached, so I1 and I2 are not computed for this copy"),
            },
            "counters": dict(sorted(dg.items())),
            "files": {"pa": str(pa_p.relative_to(out_dir)).replace("\\", "/"),
                      "runners": str(rn_p.relative_to(out_dir)).replace("\\", "/")},
            "pa_sha256": write_table(pa_df, pa_p), "runners_sha256": write_table(rn_df, rn_p),
            "complete": bool(complete), "frozen": bool(complete),
        }
    man["milb_skipped"] = dict(sorted(skips.items()))
    if own_man:
        now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
        man["built_at"] = man["generated_at"] = now
        write_manifest(out_dir, man)
    return mblk


def build(seasons=DEFAULT_SEASONS, *, out_dir: Path = DEFAULT_OUT, source: Path = DEFAULT_SOURCE,
          workers: int = 8, milb: bool = False, feeds: Path = DEFAULT_FEEDS,
          allow_refetch: bool = True, today: _dt.date | None = None,
          schedules: dict | None = None, official_paths: dict | None = None,
          fetcher=None, hist_source: Path = DEFAULT_HIST_SOURCE) -> dict:
    out_dir = Path(out_dir)
    man = load_manifest(out_dir)
    for s in seasons:
        sch = (schedules or {}).get(int(s)) if schedules is not None else None
        if schedules is not None and sch is None:
            continue
        blk = build_season(int(s), out_dir=out_dir, source=source, schedule=sch, workers=workers,
                           today=today, official_path=(official_paths or {}).get(int(s)),
                           allow_refetch=allow_refetch, fetcher=fetcher, man=man,
                           hist_source=hist_source)
        rc = blk.get("receipts") or {}
        print(f"  {s}: games {blk.get('games_present')}/{blk.get('games_scheduled')}  "
              f"I1 {rc.get('I1', {}).get('pass')}  I2 {rc.get('I2', {}).get('pass')}  "
              f"I3 {rc.get('I3', {}).get('pass')}  frozen {blk.get('frozen')}", flush=True)
    if milb:
        build_milb(out_dir=out_dir, feeds=feeds, workers=workers, today=today, man=man)
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    man["schema_version"] = SCHEMA_VERSION
    man["built_at"] = man["generated_at"] = now
    man["source_cache"] = str(Path(source))
    man["hist_source_cache"] = str(Path(hist_source))
    man["hist_seasons"] = list(HIST_SEASONS)
    write_manifest(out_dir, man)
    return man


def _parse_seasons(s: str) -> list:
    """A range skips 2020 (the 60-game season); the explicit token 2020 keeps it."""
    out = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(x for x in range(int(a), int(b) + 1) if x != 2020)
        elif part:
            out.append(int(part))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2018,2019,2021-2026")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--milb", action="store_true")
    ap.add_argument("--milb-only", action="store_true")
    ap.add_argument("--no-refetch", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()
    seasons = [] if a.milb_only else _parse_seasons(a.seasons)
    build(seasons, workers=a.workers, milb=(a.milb or a.milb_only),
          allow_refetch=not a.no_refetch)
    print(f"done in {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
