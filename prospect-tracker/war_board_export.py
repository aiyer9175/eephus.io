# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - eWAR Leaderboards (data/war_leaderboards.json).

THE BOARD THE OTHER FIVE CANNOT DRAW. Every /mlbstats/ player board carries one
SIDE of a player's season: the reliever, starter and Leverage-starter boards his
pitching, the hitter, Defense and Leverage-batter boards his batting. That is
correct on each of those boards, because each column beside it divides by that
side's denominator, and it means no board can show a whole player:

  * a two-way player reads as half of himself on each board he is on;
  * a swingman who is on NEITHER pitcher board (more relief than
    sem_plus.MIN_START_SHARE, more starting than rem_plus.MAX_START_SHARE) is on
    no board at all.

This exporter writes the one artifact that sums the two sides BEFORE rounding,
so `war` is the whole player, plus a club rollup on the TWO bases the boards
disagree about (the roster today, and the club the eWAR was earned for).

WHAT IS NEW HERE AND WHAT IS NOT. The sides come from the same map the five
boards read (bullpen_export._side_war_by_season, lru-cached for the process), so
this board cannot disagree with them about a side. The SUM is stored ONLY in
this payload and is never stamped back onto a board row, because those rows must
keep reproducing WAR/PA+ and WAR/IP+ from one side and one denominator.

REFUSALS, the house pattern (fa_projection.py:191-201). There are three, and
they are three because a board can be wrong in three different ways:

  1. A DEGENERATE WAR READ is a board of blanks with a handful of numbers on
     it: fewer than bullpen_export.WAR_RATE_MIN_COVERAGE of the season's
     qualified StatsAPI lines carry a side cell.
  2. A DEAD SEASON FEED is worse, because it publishes a board that LOOKS full.
     load_season_pitching is a live StatsAPI call (the hitting side reads a disk
     cache and this one does not, bullpen_export.load_season_pitching), and when
     it comes back empty every arm loses his IP, so every arm reads as a
     swingman, both pitcher columns of every club read 0.0 and the arms drop out
     of the club rollup entirely for want of a team. The coverage test in (1)
     cannot see it: its denominator is built from the same feeds that failed. So
     each side is measured against the players who CARRY that side's eWAR cell,
     which is evidence from the other door.
  3. An EMPTY BLOCK: guard_nonempty_block protects `players` and `teams` the way
     it protects every other /mlbstats/ block.

A refusal keeps the previous file on disk and is filed RED. A season with no
qualified line AND no eWAR cell to miss is NOT a refusal: between the last out
and opening day there is nothing to publish, and a nightly red every night from
January is the false red that teaches a reader to skip the section. That case
logs a plain skip and keeps the file. A feed that goes dark while the eWAR
artifact DOES hold cells for the season is the outage, and it is red.

Run: `python war_board_export.py [season]`
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import rem_plus
import sem_plus
from bullpen_export import (WAR_RATE_DISPLAY_MIN_PA, WAR_RATE_DISPLAY_MIN_RP_IP,
                            WAR_RATE_MIN_COVERAGE, WAR_RATE_POOL_MIN_IP,
                            _ingest_red, _num, _side_war_by_season,
                            basis_rows_for, guard_nonempty_block, ip_to_float,
                            load_season_pitching, team_basis_meta)
from bullpen_export import served_war_basis as be_served_war_basis
from hitter_export import load_season_hitting
# This board is nothing BUT eWAR, so the stamp always ships with it.
from war_source import safe_ewar_vintage as _war_source_vintage

_log = logging.getLogger(__name__)
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "war_leaderboards.json"

#: The PER-SEASON substrate this board also writes, so a year range folds one
#: file instead of asking for one payload per selectable window (any start by
#: any end over sixteen seasons is 136 of them). Written in THIS process from
#: THIS board's own side map: see build_seasons.
SEASONS_FILENAME = "war_seasons.json"

#: The substrate's shape version. The page folds these rows positionally, so a
#: shape change it has not been taught has to be visible in the payload.
SEASONS_SCHEMA = 1

#: Where the per-season DENOMINATOR LINES are memoised, completed seasons only.
#: A finished season's stat line is frozen, which is the same argument the
#: window lab's panel memo makes - and it is what keeps this step's cost claim
#: true. scrapers._cache_ttl_for_key gives a prior-year key a 30-DAY TTL, so
#: without a memo the NIGHTLY eWAR refresh refetches about 30 season feeds
#: (roughly 1.1 MB and half a second of rate limit apiece) once a month inside a
#: step documented as opening no new door. Nothing in .cache/ ships.
SEASONS_LINES_CACHE = ROOT / ".cache" / "war_seasons_lines"
SEASONS_LINES_SCHEMA = 1


def seasons_out_path() -> Path:
    """Where the substrate is written, RESOLVED FROM OUT_PATH AT CALL TIME.

    Not a module constant, and the difference is not cosmetic: every test that
    drives this exporter redirects OUT_PATH to a tmp_path and nothing else, so a
    second module-level path would keep writing the synthetic substrate into the
    real, git-tracked data/ directory. Measured before this was a function: one
    stubbed test took data/war_seasons.json from 5,149 players to 24, and a full
    suite run left it at 20. That is the documented "pytest pollutes build
    artifacts" trap, and the fix is to have one door for both files."""
    return Path(OUT_PATH).parent / SEASONS_FILENAME

#: The qualified cut the board opens on, and the rule it publishes so a reader
#: never has to infer it. The two numbers are the DISPLAY floors the WAR-rate
#: columns already use (bullpen_export), not new thresholds: a player the rate
#: columns will show is a player this board calls qualified.
QUAL_MIN_PA = WAR_RATE_DISPLAY_MIN_PA        # 100
QUAL_MIN_IP = WAR_RATE_DISPLAY_MIN_RP_IP     # 30

#: The two-way FALLBACK, used only when the feed carries no position code at
#: all: both sides present with a real sample on each. The PA floor is the
#: qualified one; the IP floor is the POOL floor (20), because a two-way
#: player's pitching sample is by construction smaller than a full-time arm's
#: and the display floor would read him as a hitter who pitched.
TWP_FALLBACK_MIN_PA = WAR_RATE_DISPLAY_MIN_PA
TWP_FALLBACK_MIN_IP = WAR_RATE_POOL_MIN_IP

#: The PITCHING side of the club rollup, by the row's OWN role. A role is
#: assigned once, in _role, and the club columns read it rather than re-deriving
#: it from a row's innings: the second derivation is how a position player's
#: mop-up inning ended up in a column of pitchers. `TWP` sits in Starters by
#: decision (a two-way player's pitching is a rotation slot) and `H` in Swing,
#: because a position player pitching is on neither pitcher board either; the
#: count of those rows and what they are worth is disclosed in `team_rollup` so
#: the column is not silently mixed.
PIT_BUCKET = {"SP": "sp", "TWP": "sp", "RP": "rp", "SW": "sw", "H": "sw"}

#: The five player boards, for the `boards` field: which of them carries this
#: player today. It is what makes "on no board" a measured statement rather than
#: an assertion in a page's copy. Read from the served artifacts, never fetched.
BOARD_FILES = (
    ("bullpen", "bullpen_leaderboards.json", ("relievers",)),
    ("starters", "starter_leaderboards.json", ("starters",)),
    ("hitters", "hitter_leaderboards.json", ("hitters",)),
    ("defense", "defense_leaderboards.json", ("fielders",)),
    ("leverage", "leverage_leaderboards.json", ("batters", "starters")),
)


def _pitching_role(ip: float, g: float, gs: float) -> str:
    """SP / RP / SW from the SAME start-share ladder the two pitcher boards
    pool on: sem_plus.is_true_starter, then rem_plus.is_true_reliever, and
    anything left is the swingman this board exists to show.

    The two predicates are called rather than re-implemented, so the thresholds
    (sem_plus.MIN_START_SHARE 0.50, rem_plus.MAX_START_SHARE 0.10) live in one
    place. Re-deriving them here is how a swingman would double count on two
    boards or vanish from both. They read `ip`, `g` and `gs` off their record,
    which is all this shim carries.

    An arm with a pitching eWAR cell and no season line we can see lands in SW,
    which is exactly what he is: a pitcher on neither pitcher board."""
    line = SimpleNamespace(ip=float(ip or 0.0), g=float(g or 0.0), gs=float(gs or 0.0))
    if sem_plus.is_true_starter(line):
        return "SP"
    if rem_plus.is_true_reliever(line):
        return "RP"
    return "SW"


def _role(pos: Optional[str], *, is_pitcher: bool, has_bat: bool, has_pit: bool,
          pa: float, ip: float, g: float, gs: float) -> str:
    """H / SP / RP / SW / TWP for one player-season.

    TWP is the FEED'S call first (StatsAPI primary position code), because a
    club telling MLB a player is two-way is better evidence than any share of
    his innings. The fallback only runs when the feed carries no code for him:
    both sides present, with a qualified batting sample and a pool-sized
    pitching one.

    `is_pitcher` is membership of the season PITCHING feed (primary position P
    or TWP), not "has a pitching cell": a position player's mop-up inning gives
    him a pitching eWAR cell, and he is a hitter."""
    if (pos or "").upper() == "TWP":
        return "TWP"
    if not pos and has_bat and has_pit and pa >= TWP_FALLBACK_MIN_PA \
            and ip >= TWP_FALLBACK_MIN_IP:
        return "TWP"
    if is_pitcher or (has_pit and not has_bat):
        return _pitching_role(ip, g, gs)
    return "H"


def _board_membership(log=print) -> tuple[dict, dict]:
    """{mlbam: [board keys]} over the five served player boards, and a meta
    block naming which artifacts were readable.

    A MISSING FILE IS NOT AN EMPTY BOARD. When not one of the five can be read
    (a fresh checkout, a pruned data/) the map is returned empty and the caller
    OMITS the field rather than publishing `boards: []` on every row, which
    would read as "this player is on no board" for the whole league."""
    meta = {"read": [], "missing": [], "n_players": 0}
    out: dict[int, list] = {}
    for key, fname, blocks in BOARD_FILES:
        path = DATA_DIR / fname
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:     # noqa: BLE001 - an unbuilt board is not an error here
            meta["missing"].append(fname)
            continue
        meta["read"].append(fname)
        for block in blocks:
            for r in doc.get(block) or []:
                mid = r.get("mlbam")
                if mid is None:
                    continue
                try:
                    mid = int(mid)
                except (TypeError, ValueError):
                    continue
                seen = out.setdefault(mid, [])
                if key not in seen:
                    seen.append(key)
    meta["n_players"] = len(out)
    if meta["missing"]:
        log(f"  ewar board: {len(meta['missing'])} of {len(BOARD_FILES)} player "
            f"boards unreadable ({', '.join(meta['missing'])}); `boards` covers "
            f"the ones that are there")
    return out, meta


_FRAME_CACHE: dict = {}


def _stint_frame(side: str):
    """war_source.stint_frame(side), read ONCE per process.

    Two callers here want the same two frames (the Earned rollup and the name
    fallback), and neither war_source nor pybaseball memoises this read:
    `bwar_bat` goes through pybaseball's disk cache but `bwar_pitch` does not
    (war_source.stint_frame's own ASYMMETRY note), so an unshared read is a
    second live download of war_daily_pitch.txt. The exception is cached too, so
    a dead frame is not retried twice either."""
    if side not in _FRAME_CACHE:
        import war_source
        try:
            # DISPLAY DOOR (fWAR label epoch step D + U, 2026-10-03): the Earned board
            # shows the displayed eWAR, war_source.DISPLAY_PROVIDER (eWAR v3 once
            # EWAR_V3_LIVE is on, EBR_GATE.md 11.10.5), never the training label
            # war_source.DEFAULT_PROVIDER serves.
            _FRAME_CACHE[side] = (war_source.stint_frame(side, provider=war_source.DISPLAY_PROVIDER), None)
        except Exception as e:   # noqa: BLE001 - the caller decides what a failure means
            _FRAME_CACHE[side] = (None, e)
    df, err = _FRAME_CACHE[side]
    if err is not None:
        raise err
    return df


def _stale_frames() -> dict:
    """The sides war_source is serving off its last-good parquet, in fa_export's
    shape (fa_export.py:365). A frame that failed to download is served from
    disk with no exception raised, so the Earned basis can be built on a frame
    that is weeks old; war_source.served_stale's own docstring says a caller
    that publishes a board must look. This board does not refuse on it (the
    Earned column is additive and a last-good frame is still a measurement) but
    it will not serve it silently."""
    try:
        import war_source
        stale = war_source.served_stale()
    except Exception:    # noqa: BLE001 - a disclosure must not take a board down
        return {}
    return {side: {"age_days": (None if v.get("age_days") is None
                                else round(v["age_days"], 2)),
                   "rows": v.get("rows"), "error": v.get("error")}
            for side, v in (stale or {}).items()}


def _earned_by_club(season: int, dialect: dict, log=print) -> tuple[dict, dict]:
    """{club: eWAR EARNED for that club this season}, the other team basis.

    The board's own `war` is the roster today: every club total is the sum over
    the players it holds now, which is the basis Bullpen+, Rotation+ and
    Offense+ are on (bullpen_export.TEAM_BASIS). This is the other one, and the
    two differ by whole wins on a club that bought or sold in July.

    Built from war_source.stint_frame, which is one row per player-stint-season
    and therefore the only door that knows WHICH club a traded player's WAR was
    produced for. Both sides are summed UNROUNDED and rounded once, per club.

    THE DIALECT. The stint frame speaks Baseball-Reference ("TBR", "ARI",
    "CHW", "WSN") and this board speaks StatsAPI ("TB", "AZ", "CWS", "WSH"), so
    every club code is canonicalised through trades.canonical_org and then
    written back in THIS artifact's own spelling, the way
    bullpen_export.apply_current_team does it. A club that does not resolve
    gets NO field on its row (blank, never zero) and is counted here, because a
    zero would read as a club that produced nothing.

    A DEGRADED FRAME IS DISCLOSED, not hidden. war_source falls back to its
    last-good parquet when the war_daily download fails and records the side in
    served_stale(); `stale_frames` carries that verdict onto the artifact, so a
    reader of the Earned column can tell a fresh basis from one built on a frame
    that is days old.

    Never raises: a failed frame read returns an empty map and says why."""
    meta = {"available": False, "n_stint_rows": 0, "n_rows_unmapped": 0,
            "unmapped_codes": [], "n_clubs": 0}
    try:
        from trades import canonical_org
    except Exception as e:   # noqa: BLE001 - the earned basis is additive
        meta["refused"] = f"trades unavailable ({type(e).__name__}: {e})"
        return {}, meta
    totals: dict[str, float] = {}
    unmapped: dict[str, int] = {}
    for side in ("bat", "pit"):
        try:
            df = _stint_frame(side)
        except Exception as e:   # noqa: BLE001 - one failed side is not a board
            _log.warning("war_earned: the %s stint frame failed (%s); the "
                         "earned basis is served without it", side, e)
            meta["refused"] = f"{side} stint frame failed: {type(e).__name__}: {e}"
            meta["stale_frames"] = _stale_frames()
            return {}, meta
        try:
            sub = df[df["year_ID"] == int(season)]
            cols = list(zip(sub["team_ID"].tolist(), sub["WAR"].tolist()))
        except Exception as e:   # noqa: BLE001 - a frame shape change is not a crash
            _log.warning("war_earned: the %s stint frame has an unexpected "
                         "shape (%s)", side, e)
            meta["refused"] = f"{side} stint frame shape: {type(e).__name__}: {e}"
            meta["stale_frames"] = _stale_frames()
            return {}, meta
        for raw_team, raw_war in cols:
            w = _num(raw_war)
            if w is None:
                continue
            meta["n_stint_rows"] += 1
            code = canonical_org(str(raw_team).strip()) if raw_team is not None else None
            club = dialect.get(code or "")
            if not club:
                meta["n_rows_unmapped"] += 1
                unmapped[str(raw_team)] = unmapped.get(str(raw_team), 0) + 1
                continue
            totals[club] = totals.get(club, 0.0) + float(w)
    meta["unmapped_codes"] = sorted(unmapped)
    meta["n_clubs"] = len(totals)
    meta["available"] = bool(totals)
    # The frames this basis was actually built on: empty when both came off the
    # wire, otherwise the side, its age and the download error behind it.
    stale = _stale_frames()
    if stale:
        meta["stale_frames"] = stale
        meta["degraded_why"] = (
            "the war_daily download failed and a cached frame was served ("
            + ", ".join(f"{side}: {v.get('age_days')} days old, "
                        f"{v.get('rows')} rows, {v.get('error')}"
                        for side, v in sorted(stale.items()))
            + "). The Earned column describes that frame, not today's league.")
        log(f"  ewar board: the Earned basis was built on a LAST-GOOD frame "
            f"({', '.join(sorted(stale))}); it is disclosed on the artifact")
    if unmapped:
        log(f"  ewar board: {meta['n_rows_unmapped']} stint row(s) carry a club "
            f"this board cannot name ({', '.join(sorted(unmapped))}); those clubs "
            f"serve no Earned value")
    return totals, meta


def _blank_free(v: Optional[float]) -> Optional[float]:
    """1dp, and never -0.0 (a served -0.0 renders as '-0.0' and reads as a
    different number from the 0.0 beside it)."""
    if v is None:
        return None
    r = round(float(v), 1)
    return 0.0 if r == 0 else r


def _feed_health(war_by: dict, season: int, hit_by: dict, pit_by: dict,
                 *, n_hit_rows: int, n_pit_rows: int) -> dict:
    """Is each StatsAPI season feed actually there? Measured from the OTHER door.

    THE FAILURE THIS EXISTS FOR. `load_season_pitching` is a live StatsAPI call
    on every run. When it returns nothing, no row on this board carries IP, G or
    GS, so every arm falls through the role ladder into SW, both pitcher columns
    of all thirty clubs read 0.0, and the arms leave the club rollup entirely
    because their team came off that same feed. The board still has 1,456 rows
    and 30 clubs on it, so guard_nonempty_block passes and the ingest ledger
    goes green: a plausible board that is wrong by a third of the league.

    The eWAR coverage test cannot catch it, because the qualified lines it
    divides by come from the feeds that failed (a dead pitching feed leaves an
    all-hitter denominator that the hitting side covers at 100%).

    So each side is measured against the players who carry that side's eWAR
    CELL, which comes from the eWAR artifact and is independent of StatsAPI: of
    the players with a `pit` cell this season, how many does the pitching feed
    know? Today that is 799 of 855 (0.93) on the pitching side, because 56
    position players' mop-up innings give them a pitching cell and no pitching
    line, and 742 of 742 (1.00) on the hitting side; the floor is the boards'
    own WAR_RATE_MIN_COVERAGE (0.50), which a dead feed fails at 0.00.

    A side with no eWAR cells at all is not measured (nothing to be wrong
    about), and `refused` is None when both sides pass."""
    out = {"floor": WAR_RATE_MIN_COVERAGE, "refused": None,
           "n_hitting_rows": n_hit_rows, "n_pitching_rows": n_pit_rows}
    cells = {"bat": 0, "pit": 0}
    known = {"bat": 0, "pit": 0}
    feed = {"bat": hit_by, "pit": pit_by}
    for mid, by_season in war_by.items():
        cell = (by_season or {}).get(int(season))
        if not cell:
            continue
        for side in ("bat", "pit"):
            if _num(cell.get(side)) is None:
                continue
            cells[side] += 1
            if int(mid) in feed[side]:
                known[side] += 1
    for side, label in (("bat", "hitting"), ("pit", "pitching")):
        n = cells[side]
        out[f"n_{side}_cells"] = n
        if not n:
            continue
        share = known[side] / n
        out[f"n_{side}_cells_on_the_feed"] = known[side]
        out[f"{side}_feed_share"] = round(share, 4)
        if share < WAR_RATE_MIN_COVERAGE and out["refused"] is None:
            n_rows = n_hit_rows if side == "bat" else n_pit_rows
            out["refused"] = (
                f"the {season} {label} feed returned {n_rows} rows and names "
                f"{known[side]} of the {n} players carrying a {side} eWAR cell "
                f"({share:.0%}, floor {WAR_RATE_MIN_COVERAGE:.0%}); a board "
                f"built on it would read the whole {label} side as missing")
    return out


def build(season: int, *, log=print) -> dict:
    """The payload's blocks: players, teams, league and the meta that dates and
    qualifies them. Separated from export() so a test can build a board without
    writing one."""
    try:
        war_by = _side_war_by_season()
    except Exception as e:   # noqa: BLE001 - a refusal is a result, not a crash
        _log.warning("eWAR board: the side map is unreadable (%s)", e)
        return {"refused": f"WAR fetch failed: {type(e).__name__}: {e}",
                "players": [], "teams": [], "league": {}, "sources": {}}

    log(f"  ewar board: loading {season} season lines...")
    hit_rows = load_season_hitting(season)
    # TWP as well as P: the two-way player's pitching line is the half of him
    # the hitter board cannot see, and it is the row his GS comes from.
    pit_rows = load_season_pitching(season, positions=("P", "TWP"))
    hit_by = {int(r["mlbam"]): r for r in hit_rows if r.get("mlbam") is not None}
    pit_by = {int(r["mlbam"]): r for r in pit_rows if r.get("mlbam") is not None}
    feeds = _feed_health(war_by, season, hit_by, pit_by,
                         n_hit_rows=len(hit_rows), n_pit_rows=len(pit_rows))
    sources_stub = {"n_hitting_rows": len(hit_rows),
                    "n_pitching_rows": len(pit_rows), "feeds": feeds}

    # THE COVERAGE TEST, run on the SEASON'S QUALIFIED LINES rather than on the
    # rows this board is about to build: the rows come from the side map, so
    # asking them about coverage would ask the map about itself and a
    # degenerate map would pass at 100%.
    qual_ids = {mid for mid, r in hit_by.items()
                if (_num(r.get("PA")) or 0.0) >= QUAL_MIN_PA}
    qual_ids |= {mid for mid, r in pit_by.items()
                 if ip_to_float(r.get("IP")) >= QUAL_MIN_IP}
    covered = {mid for mid in qual_ids if (war_by.get(mid) or {}).get(int(season))}
    coverage = {"n_qualified_lines": len(qual_ids), "n_with_a_side_cell": len(covered),
                "floor": WAR_RATE_MIN_COVERAGE,
                "rule": (f"PA >= {QUAL_MIN_PA:g} or IP >= {QUAL_MIN_IP:g} on the "
                         f"StatsAPI season line")}
    sources_stub["coverage"] = coverage

    # A DEAD FEED, caught from the other door. Measured against the players who
    # carry that side's eWAR cell, which is evidence the feeds cannot fake.
    # THIS IS TESTED BEFORE THE SKIP BELOW on purpose: a feed that fails while
    # the eWAR artifact holds cells for the season is an outage, and it stays an
    # outage whether one feed went or both.
    if feeds["refused"]:
        _log.warning("eWAR board REFUSED: %s", feeds["refused"])
        return {"refused": feeds["refused"], "players": [], "teams": [],
                "league": {}, "coverage": coverage, "sources": sources_stub}

    # NOTHING TO PUBLISH IS NOT A FAILURE. No qualified line AND no eWAR cell to
    # miss means the season has not been played yet: the file stands and the run
    # says so quietly, the way bullpen_export skips a season with no pitching
    # data. Filing this red would put an INGEST RED on the deploy shell every
    # night from the last out to opening day.
    if not qual_ids:
        _log.info("eWAR board: no qualified %s line yet (%d hitting rows, %d "
                  "pitching rows); keeping the previous board", season,
                  len(hit_rows), len(pit_rows))
        return {"skipped": (f"no qualified {season} season line yet "
                            f"({len(hit_rows)} hitting rows, {len(pit_rows)} "
                            f"pitching rows)"),
                "players": [], "teams": [], "league": {}, "coverage": coverage,
                "sources": sources_stub}

    if len(covered) < WAR_RATE_MIN_COVERAGE * len(qual_ids):
        _log.warning("eWAR board REFUSED: eWAR covers %d of %d qualified %s lines",
                     len(covered), len(qual_ids), season)
        return {"refused": (f"eWAR covered {len(covered)} of {len(qual_ids)} "
                            f"qualified season lines "
                            f"(floor {WAR_RATE_MIN_COVERAGE:.0%})"),
                "players": [], "teams": [], "league": {}, "coverage": coverage,
                "sources": sources_stub}

    boards_by, boards_meta = _board_membership(log=log)
    # The season ids the two feeds cannot name at all. The stint frames are
    # only read for names when there IS one, because that read is two large
    # frames and a board of named players must not pay for it.
    unnamed = {int(m) for m, by in war_by.items()
               if (by or {}).get(int(season)) and int(m) not in hit_by
               and int(m) not in pit_by}
    name_fallback = _name_fallback(season) if unnamed else {}

    players, basis_rows = [], []
    roles: dict[str, int] = {}
    n_no_line = 0
    for mid, by_season in war_by.items():
        cell = (by_season or {}).get(int(season))
        if not cell:
            continue
        bat, pit = _num(cell.get("bat")), _num(cell.get("pit"))
        if bat is None and pit is None:
            continue
        h, p = hit_by.get(int(mid)), pit_by.get(int(mid))
        src = h or p
        # THE CLUB comes from the pitching line whenever there is one. A
        # pitcher's hitting line is the club he last BATTED for, which for a
        # reliever traded after an interleague at-bat is his old club: Luke
        # Weaver served NYM here while the bullpen board, the pitching line and
        # /projections/ all said PIT (audit X03-02). Position players who
        # pitched mop-up have no pitching line (the P/TWP filter), so they keep
        # the hitting line's club.
        club_src = p if p is not None else h
        if src is None:
            n_no_line += 1
        pa = _num((h or {}).get("PA"))
        # ip_to_float(None) is 0.0, so the None check comes BEFORE the
        # conversion: a pitching row with no IP has no innings we can name, and
        # the house rule says absent is blank rather than zero.
        raw_ip = (p or {}).get("IP") if p else None
        ip = ip_to_float(raw_ip) if raw_ip is not None else None
        g = _num((p or {}).get("G"))
        gs = _num((p or {}).get("GS"))
        # The FEED'S code, kept apart from what the column prints: `pos_code`
        # absent is what the two-way fallback keys on, and printing "P" for a
        # pitcher the feed gave no code for would hide that absence.
        pos_code = (p or {}).get("pos") or (h or {}).get("primary_pos") or None
        pos = pos_code or ("P" if p is not None else "")
        role = _role(pos_code, is_pitcher=p is not None,
                     has_bat=bat is not None, has_pit=pit is not None,
                     pa=pa or 0.0, ip=ip or 0.0, g=g or 0.0, gs=gs or 0.0)
        roles[role] = roles.get(role, 0) + 1
        total = (bat or 0.0) + (pit or 0.0)
        row = {
            "mlbam": int(mid),
            "name": (src or {}).get("name") or name_fallback.get(int(mid)) or "",
            "team": (club_src or {}).get("team") or "",
            "role": role,
            "pos": pos,
            "qualified": bool((pa or 0.0) >= QUAL_MIN_PA or (ip or 0.0) >= QUAL_MIN_IP),
            # THE WHOLE PLAYER: the two sides summed UNROUNDED, rounded once.
            # A side the artifact does not carry is left out of the sum and out
            # of the row (absent, never zero).
            "war": _blank_free(total),
        }
        if bat is not None:
            row["war_bat"] = _blank_free(bat)
        if pit is not None:
            row["war_pit"] = _blank_free(pit)
        if pa is not None:
            row["pa"] = int(pa)
        if ip is not None:
            row["ip"] = round(ip, 1)
        if g is not None:
            row["g"] = int(g)
        if gs is not None:
            row["gs"] = int(gs)
        if boards_by:
            row["boards"] = list(boards_by.get(int(mid)) or [])
        # The UNROUNDED sides ride beside the row for the club rollup below and
        # are dropped before the payload is written: a club total that summed
        # the served 1dp cells would carry one rounding error per player.
        row["_bat"], row["_pit"] = bat, pit
        players.append(row)
        if club_src is not None:
            basis_rows.append(club_src)
    players.sort(key=lambda r: (-(r["war"] if r["war"] is not None else -99),
                                r["name"]))

    teams, team_meta = _team_rows(players, season, log=log)
    league = {
        "war": _blank_free(sum((r["_bat"] or 0.0) + (r["_pit"] or 0.0) for r in players)),
        "war_bat": _blank_free(sum(r["_bat"] or 0.0 for r in players)),
        "war_pit": _blank_free(sum(r["_pit"] or 0.0 for r in players)),
        "n_players": len(players),
    }
    for r in players:
        r.pop("_bat", None)
        r.pop("_pit", None)
    sources = {
        "n_hitting_rows": len(hit_rows), "n_pitching_rows": len(pit_rows),
        "feeds": feeds,
        "n_side_map_players": len(war_by),
        "n_players_without_a_season_line": n_no_line,
        "n_roles": dict(sorted(roles.items())),
        "coverage": coverage,
        "boards": boards_meta,
        "team_rollup": team_meta,
    }
    log(f"  ewar board: {len(players)} players "
        f"({sum(1 for r in players if r['qualified'])} qualified), "
        f"{len(teams)} clubs")
    return {"players": players, "teams": teams, "league": league,
            "sources": sources, "basis_rows": basis_rows,
            # The two season maps this board's rows were built from. The
            # per-season substrate takes the LIVE season's denominators from
            # here rather than reading the feeds again, so a one-season window
            # and the Current view cannot differ by a plate appearance.
            "season_lines": {"hit": hit_by, "pit": pit_by}}



# --------------------------------------------------------------------------- #
# the PER-SEASON SUBSTRATE (data/war_seasons.json)
# --------------------------------------------------------------------------- #
def _ewar_doc() -> dict:
    """The eWAR artifact, through ewar.load (memoised there, so this read is
    free once the side map above has been built).

    Read for CONTEXT ONLY: the season range, and each player-season's PA, IP and
    clubs of production. Every eWAR VALUE in the substrate comes from the same
    `_side_war_by_season()` map the board rows are built from, because the two
    must not be able to disagree (see build_seasons)."""
    import ewar
    return ewar.load()


#: The pitching feed's own pool, copied from the call build() makes, so a
#: position player's mop-up inning is outside this substrate's IP and GS on
#: EVERY season exactly as it is outside the board's on the live one.
FEED_PITCHING_POS = ("P", "TWP")


def _lines_memo_path(season: int) -> Path:
    return (SEASONS_LINES_CACHE /
            f"lines_{int(season)}_v{SEASONS_LINES_SCHEMA}.json")


def _read_lines_memo(season: int) -> Optional[dict]:
    """The memoised denominator lines for a COMPLETED season, or None."""
    try:
        doc = json.loads(_lines_memo_path(season).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = doc.get("lines")
    if not isinstance(rows, dict) or not rows:
        return None
    return {int(k): v for k, v in rows.items()}


def _write_lines_memo(season: int, lines: dict) -> None:
    """Memoise a COMPLETE read of a COMPLETED season. A partial read is never
    written: a hole memoised once is a hole forever, which is the defect
    arb_metrics.season_metrics records having shipped."""
    path = _lines_memo_path(season)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"season": int(season),
                                   "schema": SEASONS_LINES_SCHEMA,
                                   "built_at": date.today().isoformat(),
                                   "lines": {str(k): v for k, v in lines.items()}},
                                  separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
    except OSError:     # pragma: no cover - a memo we cannot write is a refetch
        pass


def _feed_lines(season: int, *, hit_by: Optional[dict] = None,
                pit_by: Optional[dict] = None,
                live: bool = False) -> tuple:
    """({mlbam: {"pa", "ip", "age", "pos", "g", "gs"}}, [dead groups], origin)
    for one season: every denominator the substrate publishes, from the door the
    BOARD reads.

    THE HOLE IS PER GROUP, SO THE REPORT IS TOO. A season does not usually fail;
    ONE of its two feeds does. A 2019 pitching read that 500s leaves every 2019
    pitcher-season without `ip` or `gs` while the hitting rows sail through, and
    a caller told only "the season is fine" would print a three-season IP total
    silently missing one season. So the dead groups come back by name and
    build_seasons publishes them.

    ONE DOOR PER NUMBER. The eWAR artifact also carries a `pa` and an `ip` per
    player-season, and taking them from there was measured against the board on
    2026-09-17: 155 rows disagreed on PA and 86 on IP, by four or five apiece,
    because the artifact's denominators come off the war_daily frame and the
    board's come off the StatsAPI season line. Two doors, one column name, a
    disagreement nobody would see. So the artifact supplies the eWAR and the
    clubs of production, and the season feed supplies every denominator.

    THE LIVE SEASON IS THE BOARD'S OWN READ, handed in as `hit_by` / `pit_by`
    (the maps build() just built its rows from), so PA, IP and GS on a
    one-season window are the board's numbers rather than numbers like them.
    Past seasons come off the DISK CACHE both loaders read
    (fa_sources.fetch_statsapi_season_stats, 2000-2026 on disk): the pitching
    loader is a LIVE call, and a sixteen-season sweep through it would be
    sixteen live calls in a step that has to stay offline.

    Age and hitting G come from the cached split either way, because neither
    loader carries them.

    G IS A MAX, NOT A SUM. A two-way player's hitting G and his pitching G are
    the same games, so the two feeds combine with max() and are never added.

    Best effort by design: a season whose feed is cold contributes no
    denominator at all, and its rows still carry their eWAR sides."""
    out: dict = {}
    missing: list = []
    if not live:
        memo = _read_lines_memo(season)
        if memo is not None:
            return memo, [], "memo"
    try:
        import fa_sources
    except Exception:    # noqa: BLE001 - a substrate is not worth a failed board
        return out, ["hitting", "pitching"], "unavailable"
    for group in ("hitting", "pitching"):
        try:
            splits = fa_sources.fetch_statsapi_season_stats(int(season), group)
        except Exception:   # noqa: BLE001 - a cold season is a thinner row
            missing.append(group)
            continue
        if not splits:
            missing.append(group)
            continue
        for s in splits or []:
            pid = (s.get("player") or {}).get("id")
            if not pid:
                continue
            st = s.get("stat") or {}
            pos = (s.get("position") or {}).get("abbreviation")
            if group == "pitching" and pos and pos not in FEED_PITCHING_POS:
                continue
            r = out.setdefault(int(pid), {})
            age = _num(st.get("age"))
            if age is not None and r.get("age") is None:
                r["age"] = int(age)
            if group == "pitching":
                # The pitching feed's code wins: a two-way player reads TWP
                # there and a fielding abbreviation on the hitting side.
                if pos:
                    r["pos"] = pos
                r.setdefault("pos", "P")
                gs = _num(st.get("gamesStarted"))
                if gs is not None:
                    r["gs"] = int(gs)
                ip = st.get("inningsPitched")
                if ip is not None:
                    r["ip"] = ip_to_float(ip)
                g = _num(st.get("gamesPitched"))
            else:
                if pos and not r.get("pos"):
                    r["pos"] = pos
                pa = _num(st.get("plateAppearances"))
                if pa is not None:
                    r["pa"] = int(pa)
                g = _num(st.get("gamesPlayed"))
            if g is not None:
                r["g"] = max(int(g), int(r.get("g") or 0))
    # The live season, from the board's own maps. Same fields, same rules; only
    # the door changes, and only for the season the board itself published.
    for mid, h in (hit_by or {}).items():
        pa = _num(h.get("PA"))
        if pa is not None:
            out.setdefault(int(mid), {})["pa"] = int(pa)
        code = h.get("primary_pos")
        if code:
            out.setdefault(int(mid), {}).setdefault("pos", code)
    for mid, p in (pit_by or {}).items():
        r = out.setdefault(int(mid), {})
        raw_ip = p.get("IP")
        # ip_to_float(None) is 0.0, so the None test comes first: an arm with no
        # innings we can name has no innings, not zero of them.
        if raw_ip is not None:
            r["ip"] = ip_to_float(raw_ip)
        gs = _num(p.get("GS"))
        if gs is not None:
            r["gs"] = int(gs)
        g = _num(p.get("G"))
        if g is not None:
            r["g"] = max(int(g), int(r.get("g") or 0))
        r["pos"] = p.get("pos") or r.get("pos") or "P"
    if not live and not missing and out:
        _write_lines_memo(season, out)
    return out, missing, "feed"


def _club_dialect(players: list) -> dict:
    """{canonical org: this board's own spelling}, learned from the clubs on the
    board exactly as _earned_by_club learns it. The eWAR artifact's per-season
    `tm` speaks Baseball-Reference ("SFG", "TBR", "CHW") and this board speaks
    StatsAPI ("SF", "TB", "CWS"), so a club is canonicalised once and written
    back in the artifact's own spelling."""
    out: dict = {}
    try:
        from trades import canonical_org
    except Exception:   # noqa: BLE001 - a dialect is a courtesy, not a board
        return out
    for r in players:
        club = r.get("team")
        if club:
            out.setdefault(canonical_org(club) or club, club)
    return out


def _season_share(league_war: dict, seasons: list) -> dict:
    """{season: that season's league eWAR over the mean of the last three
    COMPLETE seasons}, so a page can say "2020 produced 37% of a normal season"
    and "2026 has produced 94% of one so far" from a published number instead of
    two literals typed into the JS.

    Complete is war_source.ewar_season_complete, the same predicate the eWAR
    cadence uses, so the live season is never inside its own baseline."""
    try:
        import war_source as _ws
        complete = [y for y in seasons if _ws.ewar_season_complete(int(y))]
    except Exception:   # noqa: BLE001 - a disclosure must not take a board down
        complete = [y for y in seasons if int(y) < date.today().year]
    base = [league_war.get(int(y)) or 0.0 for y in complete[-3:]]
    base = [b for b in base if b > 0]
    if not base:
        return {}
    mean = sum(base) / len(base)
    return {str(int(y)): round((league_war.get(int(y)) or 0.0) / mean, 4)
            for y in seasons if league_war.get(int(y))}


def _display_is_ewar() -> bool:
    """True when the displayed WAR is eWAR (provider ewar_v3), the series whose
    history reaches 2000 (docs/ewar/EWAR_HISTORY_GATE.md part 5)."""
    try:
        import war_source
        return war_source.DISPLAY_PROVIDER == "ewar_v3"
    except Exception:   # noqa: BLE001 - no provider, no history window
        return False


def _history_clubs_names(seasons: list, blocks: dict, *, log=print) -> tuple[dict, dict]:
    """({(mlbam, season): [team_IDs in stint order]}, {mlbam: name}) from the
    war_daily stint frames (_stint_frame, the frames the Earned rollup reads), for
    the seasons the eWAR v2 artifact has no block for, and a name for every player.

    The clubs follow the artifact's own rule (ewar.export_payload: batting stints,
    then pitching stints, each club once, ewar._fold_team), so a season before 2011
    names its clubs the way a season after it does. The name is the frame's
    name_common on the player's latest row; the board's own name wins where the
    player is on it. Best effort, and it never opens a frame itself: it reads
    only the frames this process already holds (the Earned rollup reads both in
    build(), before the substrate), so a run whose frames were not read, or
    failed, ships those rows with no club and no name, as before, and says so."""
    try:
        from ewar import _fold_team
    except Exception:   # noqa: BLE001
        def _fold_team(t):
            return str(t or "").strip().upper()
    first = int(min(seasons)) if seasons else None
    tm: dict = {}
    names: dict = {}
    latest: dict = {}
    for side in ("bat", "pit"):
        df, err = _FRAME_CACHE.get(side) or (None, None)
        if df is None:
            log(f"  ewar seasons: the {side} stint frame was not read in this run"
                + (f" ({type(err).__name__})" if err is not None else "")
                + "; seasons the eWAR v2 artifact does not cover ship without its clubs, "
                "and players off the board without its names")
            continue
        cols = [c for c in ("mlb_ID", "year_ID", "team_ID", "name_common") if c in df.columns]
        if "mlb_ID" not in cols or "year_ID" not in cols:
            continue
        sub = df[df["mlb_ID"].notna()][cols]
        for r in sub.itertuples(index=False):
            try:
                mid, yr = int(r.mlb_ID), int(r.year_ID)
            except (TypeError, ValueError):
                continue
            if first is not None and yr < first:
                continue
            nm = getattr(r, "name_common", None)
            if isinstance(nm, str) and nm and yr >= latest.get(mid, -1):
                latest[mid] = yr
                names[mid] = nm
            if (blocks.get(str(mid)) or {}).get(str(yr)):
                continue            # the artifact names this season's clubs
            team = getattr(r, "team_ID", None)
            if not isinstance(team, str) or not team:
                continue
            lst = tm.setdefault((mid, yr), [])
            club = _fold_team(team)
            if club not in lst:
                lst.append(club)
    return tm, names


def _components_block(groups: list) -> dict:
    """The season groups the page states (docs/ewar/EWAR_HISTORY_GATE.md part 2),
    or {} when the displayed WAR is not eWAR."""
    if not groups:
        return {}
    import ewar_history
    out = {"source": "ewar_history.season_groups (data/ewar_history.json)",
           "first_season": groups[0]["first"],
           "why_it_stops": ewar_history.WHY_IT_STOPS,
           "groups": [{"first": g["first"], "last": g["last"], "text": g["text_headline"],
                       "missing": [m for m in g["missing"] if m != "r2"],
                       "short": g["short_headline"]} for g in groups]}
    # The xHEM+ part (EBR_GATE.md 11.11, owner EW3-51): its one sentence, stated once
    # for a window that reaches a season carrying it; absent while no season does.
    xs = [g["first"] for g in groups if "xhem" in (g.get("headline") or [])]
    if xs:
        import ewar_v3
        out["xhem"] = {"first_season": min(xs), "copy": ewar_v3.xhem_copy()}
    return out


def build_seasons(war_by: dict, players: list, *, live_season: int,
                  season_lines: Optional[dict] = None, log=print) -> dict:
    """The per-season substrate a year range folds: one row per player-season
    over the eWAR artifact's whole window, with the two sides kept apart.

    THE SAME-PROCESS RULE, and why it is not optional. `war_by` is the map
    build() built this board's rows from, handed in rather than read again. The
    served board and this file are then the same numbers by construction. They
    were not before: measured 2026-09-17, the served board's
    `ewar_vintage.artifact_generated_at` was 2026-09-16T09:47:15 while
    data/ewar.json carried `live_built_at` 2026-09-17T14:45:01, and the two
    disagreed on 173 of the top 400 rows. A year range whose one-season view
    disagreed with the Current view on the same page would be that defect made
    visible, so the fold source is built from the board's own read or not at
    all.

    THE UNIVERSE IS EVERY PLAYER-SEASON. The qualified rule filters the rows a
    page RENDERS and never the fold: a rate pooled over the seasons in which a
    player happened to qualify is a rate on a basis it was not computed on.
    `qualified_rule_window` ships beside it so the page reports the rule rather
    than typing it.

    SIDES AT FULL PRECISION, ROUNDED ONCE AT THE END. The board rounds each side
    to a tenth to print it; a window that summed served tenths would carry one
    rounding error per season. So the sides ship as the map holds them and the
    fold sums them unrounded and rounds once, which is the board's own rule over
    one season. There is deliberately no per-season `war` field: a second copy
    of bat + pit is a second number that could disagree with the first.

    ABSENT IS NOT ZERO. A side, a denominator or a feed field the artifact does
    not carry is null in the row, never 0."""
    try:
        doc = _ewar_doc()
    except Exception as e:   # noqa: BLE001 - the substrate is additive
        log(f"  ewar seasons: the eWAR artifact is unreadable "
            f"({type(e).__name__}); the per-season substrate was not built")
        return {"refused": f"eWAR artifact unreadable: {type(e).__name__}: {e}",
                "players": {}}
    rng = (doc.get("seasons") or [])[:2]
    if len(rng) != 2:
        return {"refused": "the eWAR artifact publishes no season range",
                "players": {}}
    seasons = list(range(int(rng[0]), int(rng[1]) + 1))
    blocks = doc.get("players") or {}
    # THE HISTORY WINDOW (docs/ewar/EWAR_HISTORY_GATE.md part 5, owner EW3-17). On
    # eWAR (provider ewar_v3) the substrate reaches back to the first season of the
    # frozen fWAR vintage, 2000, every season of it the displayed eWAR already
    # serves through the same side map. The eWAR v2 artifact above starts in 2011,
    # so the clubs and names of an earlier season come from the war_daily stint
    # frame the Earned rollup reads (_history_clubs_names). eWAR v2 keeps its own
    # window.
    groups = []
    if _display_is_ewar():
        import ewar_history
        hist = ewar_history.seasons()
        if hist:
            seasons = list(range(min(hist[0], seasons[0]), seasons[-1] + 1))
        groups = ewar_history.season_groups()
    frame_tm, frame_names = _history_clubs_names(seasons, blocks, log=log)

    dialect = _club_dialect(players)
    try:
        from trades import canonical_org
    except Exception:   # noqa: BLE001 - a club code we cannot canonicalise ships raw
        canonical_org = None

    lines_now = season_lines or {}
    feeds, cold, group_cold = {}, [], {}
    n_memo = n_fetch = 0
    t_feed = time.time()
    for y in seasons:
        live = int(y) == int(live_season)
        lines, missing, origin = _feed_lines(
            y, hit_by=lines_now.get("hit") if live else None,
            pit_by=lines_now.get("pit") if live else None, live=live)
        n_memo += 1 if origin == "memo" else 0
        n_fetch += 1 if origin == "feed" else 0
        if not lines:
            cold.append(y)
        elif missing:
            # HALF A SEASON, NAMED. The rows still ship and the side that failed
            # is absent rather than zero, which is right; what would be wrong is
            # a payload reporting full coverage over a season with no innings in
            # it.
            group_cold[str(y)] = missing
        feeds[y] = lines
    feed_seconds = round(time.time() - t_feed, 2)

    tm_dict, tm_idx, pos_dict, pos_idx = [], {}, [], {}

    def _dict_key(value, table, index):
        if not value:
            return None
        i = index.get(value)
        if i is None:
            i = len(table)
            table.append(value)
            index[value] = i
        return i

    names = {int(r["mlbam"]): (r.get("name") or "")
             for r in players if r.get("mlbam") is not None}
    out_players, league = {}, {}
    n_rows = n_unresolved = 0
    for mid, by_season in war_by.items():
        rows = []
        for y in seasons:
            cell = (by_season or {}).get(int(y))
            if not cell:
                continue
            bat, pit = _num(cell.get("bat")), _num(cell.get("pit"))
            if bat is None and pit is None:
                continue
            blk = (blocks.get(str(int(mid))) or {}).get(str(y)) or {}
            feed = (feeds.get(y) or {}).get(int(mid)) or {}
            pa, ip = _num(feed.get("pa")), _num(feed.get("ip"))
            named = []
            for c in (blk.get("tm") or frame_tm.get((int(mid), int(y))) or []):
                if not c:
                    continue
                canon = canonical_org(str(c)) if canonical_org else None
                if not canon:
                    n_unresolved += 1
                club = dialect.get(canon or "") or canon or str(c)
                if club not in named:
                    named.append(club)
            rows.append([
                int(y),
                None if bat is None else round(bat, 4),
                None if pit is None else round(pit, 4),
                None if pa is None else int(pa),
                None if ip is None else round(ip, 1),
                feed.get("age"),
                _dict_key(feed.get("pos"), pos_dict, pos_idx),
                feed.get("g"),
                feed.get("gs"),
                _dict_key("/".join(named), tm_dict, tm_idx),
            ])
            league[int(y)] = league.get(int(y), 0.0) + (bat or 0.0) + (pit or 0.0)
            n_rows += 1
        if rows:
            out_players[str(int(mid))] = [names.get(int(mid)) or frame_names.get(int(mid)) or "",
                                          rows]
    league_r = {str(y): round(v, 1) for y, v in sorted(league.items())}
    log(f"  ewar seasons: {len(out_players)} players, {n_rows} player-seasons, "
        f"{seasons[0]}-{seasons[-1]}")
    return {
        "schema": SEASONS_SCHEMA,
        "seasons": seasons,
        "fields": ["season", "war_bat", "war_pit", "pa", "ip", "age", "pos",
                   "g", "gs", "tm"],
        "tm": tm_dict, "pos": pos_dict,
        "league_war": league_r,
        "season_share": _season_share({int(k): v for k, v in league_r.items()},
                                      seasons),
        # What each season's eWAR carries, measured (ewar_history.season_groups,
        # docs/ewar/EWAR_HISTORY_GATE.md part 2): the page states a window's groups.
        "components": _components_block(groups),
        "qualified_rule_window": {"min_pa": int(QUAL_MIN_PA),
                                  "min_ip": int(QUAL_MIN_IP)},
        "players": out_players,
        "sources": {"n_players": len(out_players), "n_player_seasons": n_rows,
                    "n_seasons_without_a_feed": len(cold),
                    "seasons_without_a_feed": cold,
                    # {season: [feed groups that failed]}. A season here has its
                    # eWAR sides and NO denominator for the named side, so a
                    # window folding it sums fewer seasons of PA or IP than of
                    # eWAR. The page states it; it is not inferable from the
                    # rows.
                    "groups_without_a_feed": group_cold,
                    "feed_reads": {"from_memo": n_memo, "fetched": n_fetch,
                                   "seconds": feed_seconds,
                                   "memo": str(SEASONS_LINES_CACHE.name)},
                    "n_club_codes_unresolved": n_unresolved},
        "field_notes": {
            "g": ("games PLAYED: the MAX of the hitting and pitching feed G, "
                  "never their sum, because a two-way player's hitting games "
                  "and pitching games are the same games. The eWAR BOARD's own "
                  "`g` is the pitching feed's G alone, so a hitter reads blank "
                  "there and a real number here. Two different questions, "
                  "pinned apart by test_mlbstats_windows."),
            "war_bat": ("the batting side at full precision. The board prints "
                        "it rounded to a tenth; a window sums these and rounds "
                        "once."),
        },
        "note": ("One row per player-season, positional by `fields`. A window is "
                 "the fold of these rows: counts add, the two eWAR sides sum "
                 "UNROUNDED and round once. The board's Current view is this "
                 "file folded at the live season, from the same read, in the "
                 "same process. A season named in `groups_without_a_feed` "
                 "carries its eWAR and no denominator for that side, so a "
                 "window over it is short of one season's PA or IP and says "
                 "so."),
    }


def _write_seasons(payload: dict, *, today: str, log=print) -> int:
    """Write data/war_seasons.json, guarded the way every /mlbstats/ block is.

    guard_nonempty_block keeps the previous file and files the refusal under a
    name run_monthly watches, so a degenerate substrate reaches INGEST RED
    instead of shipping a year range with nothing in it. The file is written
    COMPACT (no indent): it is folded by a machine, and indent=1 costs about a
    third of the payload for whitespace no reader sees."""
    out_path = seasons_out_path()
    if payload.get("refused"):
        log(f"  ewar seasons: REFUSED ({payload['refused']}); leaving "
            f"{out_path.name} as it is")
        _ingest_red("war_seasons", f"{payload['refused']}. The per-season "
                                   f"substrate was not rewritten; the previous "
                                   f"file stands.")
        return 0
    rows = [[mid, v] for mid, v in (payload.get("players") or {}).items()]
    kept, guard = guard_nonempty_block(
        rows, out_path, key="players", source="war_seasons",
        label="ewar seasons", log=log)
    if not kept:
        return 0
    if len(kept) != len(rows):
        # The guard served the previous file's block. A substrate that cannot be
        # rebuilt keeps the one on disk rather than half of a new one.
        log("  ewar seasons: the empty-block guard served the previous players "
            "block; the substrate was not rewritten")
        return 0
    out = {"generated_at": today, "as_of": today,
           "war_provider": None, "ewar_generated_at": None}
    try:
        basis = be_served_war_basis()
        out["war_provider"] = basis.get("war_provider")
        out["ewar_generated_at"] = basis.get("ewar_generated_at")
    except Exception:   # noqa: BLE001 - a stamp we cannot read is stated absent
        pass
    out["ewar_vintage"] = _war_source_vintage(as_of=today)
    out.update(payload)
    out["block_guard"] = {"players": guard}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out_path)
    log(f"  ewar seasons: wrote {out_path.name} "
        f"({payload['sources']['n_player_seasons']} player-seasons, "
        f"{payload['sources']['feed_reads']['from_memo']} seasons from the "
        f"line memo)")
    return payload["sources"]["n_player_seasons"]


def _name_fallback(season: int) -> dict:
    """{mlbam: name} from the stint frames, for a player the season feeds do
    not carry at all (released, or playing abroad, with a covered part-season).
    Best effort: a board must never fail over a missing name. The frames come
    through _stint_frame, so this read and the Earned rollup's share one copy
    per process rather than downloading war_daily twice."""
    out: dict[int, str] = {}
    for side in ("bat", "pit"):
        try:
            df = _stint_frame(side)
            sub = df[df["year_ID"] == int(season)]
            for mid, nm in zip(sub["mlb_ID"].tolist(), sub["name_common"].tolist()):
                if mid is None or not nm:
                    continue
                try:
                    out.setdefault(int(mid), str(nm))
                except (TypeError, ValueError):
                    continue
        except Exception:   # noqa: BLE001 - a name is not worth a failed board
            continue
    return out


def _team_rows(players: list[dict], season: int, *, log=print) -> tuple[list, dict]:
    """The club rollup on BOTH bases, and the meta that names them.

    `war` is the roster today: the sum over the players the club holds now, the
    same basis (bullpen_export.TEAM_BASIS) every other team board on this page
    is on, so the eWAR section can be read beside them. `war_earned` is the club
    the eWAR was produced for, by stint.

    THE FOUR COMPONENT COLUMNS SUM TO `war` before rounding. `war_bat` is the
    batting side of EVERY player on the club, a two-way player's batting
    included; the pitching side goes to the column the ROW'S OWN role names
    (PIT_BUCKET), so a two-way starter's pitching is in Starters and a
    swingman's is in Swing. Each column rounds its own UNROUNDED sum, which is
    the same reason the player rows do: adding up thirty served tenths carries
    thirty rounding errors. The price is that the four served columns can differ
    from the served total by up to a quarter of a win (four columns at half a
    tenth each, plus the total's own), and that is the right trade: each column
    is then the club's best 1dp answer to its own question.

    ONE ROLE, READ TWICE, IS TWO ROLES. The bucket is not re-derived from the
    row's innings here: a position player pitching mop-up has no pitching line,
    so a second derivation reads him as a swingman and files his cameo in a
    column of pitchers. He goes to Swing because he is on neither pitcher board,
    and how many such rows there are and what they are worth is disclosed in
    `n_position_player_pitching_rows` / `war_pit_from_position_players`.

    A club with no covered player gets no row. A club the stint frame cannot
    name gets no `war_earned` (blank, never zero)."""
    acc: dict[str, dict] = {}
    n_no_team = 0
    n_pos_pit, war_pos_pit = 0, 0.0
    for r in players:
        club = r.get("team")
        if not club:
            n_no_team += 1
            continue
        a = acc.setdefault(club, {"bat": 0.0, "sp": 0.0, "rp": 0.0, "sw": 0.0,
                                  "n": 0})
        a["n"] += 1
        if r.get("_bat") is not None:
            a["bat"] += float(r["_bat"])
        if r.get("_pit") is not None:
            a[PIT_BUCKET.get(r.get("role") or "", "sw")] += float(r["_pit"])
            if r.get("role") == "H":
                n_pos_pit += 1
                war_pos_pit += float(r["_pit"])
    dialect = {}
    try:
        from trades import canonical_org
        for club in acc:
            dialect.setdefault(canonical_org(club) or club, club)
    except Exception as e:   # noqa: BLE001 - the earned basis is additive
        _log.warning("war_earned: trades.canonical_org unavailable (%s)", e)
    earned, earned_meta = _earned_by_club(season, dialect, log=log) if dialect \
        else ({}, {"available": False, "refused": "no club dialect to map onto"})
    teams = []
    for club, a in acc.items():
        row = {"team": club,
               "war": _blank_free(a["bat"] + a["sp"] + a["rp"] + a["sw"])}
        if club in earned:
            row["war_earned"] = _blank_free(earned[club])
        row["war_bat"] = _blank_free(a["bat"])
        row["war_sp"] = _blank_free(a["sp"])
        row["war_rp"] = _blank_free(a["rp"])
        row["war_sw"] = _blank_free(a["sw"])
        row["n_players"] = a["n"]
        teams.append(row)
    teams.sort(key=lambda r: -(r["war"] if r["war"] is not None else -99))
    meta = {
        "basis": "current_roster", "n_teams": len(teams),
        "n_players_without_a_club": n_no_team,
        "n_teams_without_earned": sum(1 for t in teams if "war_earned" not in t),
        "n_position_player_pitching_rows": n_pos_pit,
        "war_pit_from_position_players": _blank_free(war_pos_pit),
        "earned": earned_meta,
        "note": ("`war` is the eWAR of the players the club holds today, the "
                 "basis every team board on this page is on; `war_earned` is "
                 "the eWAR produced for the club this season, by stint. Hitters "
                 "is the batting side of every player on the club; Starters, "
                 "Relievers and Swing hold the pitching side by the player's "
                 "role, the same start share the two pitcher boards pool on, "
                 "and Swing also holds the mop-up inning of a position player, "
                 "who is on neither pitcher board either. Each column rounds "
                 "its own unrounded sum."),
    }
    return teams, meta


def export(season: Optional[int] = None, *, write: bool = True, log=print,
           today: Optional[str] = None) -> int:
    """Build data/war_leaderboards.json and return the player-row count."""
    season = int(season or date.today().year)
    today = today or date.today().isoformat()

    built = build(season, log=log)
    # NOTHING TO PUBLISH, which is not a failure and must not read as one. The
    # ledger is left alone: a red here would fire every night of the offseason
    # and teach a reader to scroll past the section.
    if built.get("skipped"):
        log(f"  ewar board: SKIP ({built['skipped']}); leaving "
            f"{OUT_PATH.name} as it is")
        return 0
    if built.get("refused"):
        log(f"  ewar board: REFUSED ({built['refused']}); leaving "
            f"{OUT_PATH.name} as it is")
        _ingest_red("war_leaderboards",
                    (f"{season}: {built['refused']}. The eWAR board was not "
                     f"rewritten; the previous file stands."))
        return 0

    players, players_guard = guard_nonempty_block(
        built["players"], OUT_PATH, key="players", source="war_leaderboards",
        label="ewar board", log=log)
    teams, teams_guard = guard_nonempty_block(
        built["teams"], OUT_PATH, key="teams", source="war_leaderboards",
        label="ewar board", log=log)

    payload = {
        "generated_at": today, "season": season, "as_of": today,
        # WHICH BUILD every number on this board comes from, and whether it has
        # fallen behind the frame under it (audit F10-02 / F11-01). This board
        # is nothing but eWAR, so the stamp is not conditional here.
        "ewar_vintage": _war_source_vintage(as_of=today),
        # The club a player is counted under, disclosed the same way the five
        # boards disclose it. Counted over the rows behind THIS board.
        "team_basis": team_basis_meta(
            basis_rows_for(players, built.get("basis_rows") or []),
            label="ewar board"),
        # The cut the board opens on, published rather than inferred, and
        # published as the page prints it: the two floors are floats
        # in bullpen_export and "PA >= 100.0" is not how a rule reads.
        "qualified_rule": {"min_pa": int(QUAL_MIN_PA), "min_ip": int(QUAL_MIN_IP)},
        # What each input delivered this run, the coverage the refusal is
        # measured against, and the empty-block guard's verdict per block.
        "sources": built["sources"],
        "block_guard": {"players": players_guard, "teams": teams_guard},
        "note": ("Batting plus pitching eWAR, summed before rounding, so a "
                 "two-way player reads as a whole season and a swingman on "
                 "neither pitcher board still appears. The sides are the ones "
                 "the five player boards serve; the sum is stored only here."),
        "players": players, "teams": teams, "league": built["league"],
    }
    if write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(OUT_PATH)
        log(f"  ewar board: wrote {OUT_PATH.name}")

    # THE PER-SEASON SUBSTRATE, from the SAME side map this board was built
    # from, in the same process (build_seasons says why). It is additive: a
    # substrate that cannot be built leaves the board alone and files its own
    # refusal. _side_war_by_season is lru-cached for the process, so this is the
    # identical object build() read, not a second look at the artifact.
    if write:
        try:
            _write_seasons(build_seasons(_side_war_by_season(), players,
                                         live_season=season,
                                         season_lines=built.get("season_lines"),
                                         log=log),
                           today=today, log=log)
        except Exception:   # noqa: BLE001 - the board ships with or without it
            _log.exception("the per-season substrate failed; the board stands")
    return len(players)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _season = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    export(_season, log=print)
