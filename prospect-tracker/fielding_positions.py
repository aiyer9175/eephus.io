# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Game-data positional versatility ("versa").

Until now `versa` was a FanGraphs scout-reported multi-position string. This module
derives versa from ACTUAL GAME DATA: the MLB StatsAPI fielding group gives career
games + starts at each position. A prospect qualifies at a position once he has
>= VERSA_MIN_GAMES games OR >= VERSA_MIN_STARTS starts there (fantasy-standard; the
OR-starts clause lets a regular qualify mid-season while filtering one-off defensive
cameos). DH / PH / PR are excluded (not defensive positions).

Output: data/positions_played.json
    {"min_games": 10, "min_starts": 5, "generated_at": "...",
     "players": {player_key: {"by_pos": {POS: {"g": int, "gs": int}}, "versa": [POS, ...]}}}

The frontend loads this sidecar and surfaces the game-data versa (preferring it over
the FG-reported string). Built for ALL prospects (position players; pitchers skipped).

SECOND ARTIFACT: data/positions_played_seasons.json
    The census above is PRE-DEBUT ONLY and CAREER-TO-DATE, which makes it unusable as
    a model feature (see the "as-of-aware season census" section below the versa
    functions). The season census is the leakage-safe form: per-SEASON games/starts by
    position, keyed by MLBAM id, from the LEAGUE-WIDE StatsAPI fielding feed, with no
    debut filter and an explicit as-of truncation rule.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import time
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

VERSA_MIN_GAMES = 10   # games at a position to qualify (owner: "~10 games, calibrate")
VERSA_MIN_STARTS = 5   # OR starts — lets a regular qualify before 10 games accrue

# Not defensive positions — never count toward versatility.
_NON_FIELD = {"DH", "PH", "PR"}
_MLB_API = "https://statsapi.mlb.com/api/v1"

log = logging.getLogger(__name__)


# The career endpoint returns per-LEVEL splits ("A", "AA", "AAA", "ROK", "MLB",
# ...) AND a "Minors" ROLLUP split that re-states the sum of every non-MLB level.
# Summing all of them double-counts every minor-league game. Verified exactly on
# jesus_made, leo_de_vries, bobby_witt_jr, dawel_lugo and jose_ramirez across
# every level mix: rollup == sum of the non-MLB per-level rows, position by
# position. See docs/efv-2026-07-30/POSITION_CENSUS_ASOF.md section 7.
_MINORS_ROLLUP = "Minors"


def fetch_player_fielding(mlbam_id: int, timeout: float = 15.0) -> dict[str, dict]:
    """Career games + starts at each position for one player, MiLB+MLB.

    Returns {POS: {"g": games, "gs": gamesStarted}}. Empty on no fielding data.

    The "Minors" rollup split is DISCARDED when per-level minor-league rows are
    present, because it restates them; keeping both weighted every MiLB game
    twice against MLB's once, which biased the resolved position toward wherever
    a player logged his MINOR-league time. When a player carries ONLY the rollup
    and no per-level rows, the rollup is kept - dropping it would lose him."""
    url = (f"{_MLB_API}/people/{mlbam_id}/stats"
           f"?stats=career&group=fielding&leagueListId=mlb_milb")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        doc = json.load(r)
    splits = (doc.get("stats") or [{}])[0].get("splits") or []
    return aggregate_career_splits(splits)


def aggregate_career_splits(splits: list[dict]) -> dict[str, dict]:
    """{POS: {"g", "gs"}} from career-endpoint splits, rollup-deduplicated."""
    per_level: dict[str, dict] = {}
    rollup: dict[str, dict] = {}
    has_per_level_minors = False
    for s in splits:
        pos = ((s.get("position") or {}).get("abbreviation") or "").strip()
        if not pos:
            continue
        st = s.get("stat") or {}
        sport = ((s.get("sport") or {}).get("abbreviation") or "").strip()
        target = rollup if sport == _MINORS_ROLLUP else per_level
        if sport not in (_MINORS_ROLLUP, "MLB", ""):
            has_per_level_minors = True
        slot = target.setdefault(pos, {"g": 0, "gs": 0})
        try:
            slot["g"] += int(st.get("games") or 0)
            slot["gs"] += int(st.get("gamesStarted") or 0)
        except (TypeError, ValueError):
            continue
    if not has_per_level_minors:
        for pos, v in rollup.items():
            slot = per_level.setdefault(pos, {"g": 0, "gs": 0})
            slot["g"] += v["g"]
            slot["gs"] += v["gs"]
    return per_level


def versa_positions(by_pos: dict[str, dict],
                    min_games: int = VERSA_MIN_GAMES,
                    min_starts: int = VERSA_MIN_STARTS) -> list[str]:
    """Positions the prospect QUALIFIES at (>= min_games games OR >= min_starts
    starts), most-played first. DH / PH / PR excluded.

    TIE-BREAK (2026-08-04): ties used to fall through to dict-insertion order,
    i.e. whatever order the StatsAPI happened to return, which made the FIRST
    chip on the versa list a property of the FEED rather than of the player. It
    also made the artifact non-reproducible across sources: on the 2026-08-04
    board, 40+ of the 68 players whose versa list differed between the
    per-player career feed and the league-wide season census differed ONLY in
    the order of two positions with identical game counts (devin_fitzgerald
    2B/SS both 48 G, rj_schreck LF/RF both 98 G). Ties now break on
    (games, starts, defensive spectrum, name) - the SAME deterministic rule
    `observed_position_detail` already used, so the two resolvers agree and no
    new tunable enters the system. `_SPECTRUM_RANK` is defined just below;
    module-level names resolve at call time."""
    qual = [(pos, v) for pos, v in by_pos.items()
            if pos not in _NON_FIELD
            and ((v.get("g") or 0) >= min_games or (v.get("gs") or 0) >= min_starts)]
    qual.sort(key=lambda kv: (-(kv[1].get("g") or 0), -(kv[1].get("gs") or 0),
                              _SPECTRUM_RANK.get(kv[0], len(_SPECTRUM)), kv[0]))
    return [pos for pos, _ in qual]


# Defensive spectrum, hardest first. Used ONLY as the last tie-break in
# observed_position: when two positions are level on games AND on starts,
# the harder one is the meaningful assignment (industry convention, and the
# one the scarcity model prices). Stating the order makes the resolver
# deterministic; the shipped versa sort breaks its ties on dict-insertion
# order, which is whatever the StatsAPI happened to return.
_SPECTRUM = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "OF", "IF", "P"]
_SPECTRUM_RANK = {pos: i for i, pos in enumerate(_SPECTRUM)}


def observed_position_detail(by_pos: dict[str, dict],
                             min_games: int = VERSA_MIN_GAMES,
                             min_starts: int = VERSA_MIN_STARTS) -> dict | None:
    """Most-played NON-DH position from a game-data `by_pos` map, with detail.

    The owner ask ("hitter position should be based on what position they've
    played the most in the minors") answered from the fielding census rather
    than from a scouting projection. Returns
    ``{"pos", "g", "gs", "share", "tie", "qualified"}`` where `share` is the
    position's fraction of the player's non-DH fielding games, `tie` flags that
    the top position was decided by a tie-break rather than won outright on
    games, and `qualified` records that the top position cleared the exposure
    floor.

    Rules, all pre-registered in docs/efv-2026-07-30/POSITION_ROLE_GATE.md:

    * DH / PH / PR are never eligible (`_NON_FIELD`, same set versa uses). A
      player whose largest bucket is DH resolves to his largest FIELDING
      bucket; a player with nothing but DH/PH/PR resolves to None.
    * Exposure floor: the winner must clear `>= min_games` games OR
      `>= min_starts` starts - the SAME thresholds versa already qualifies on,
      so no new tunable enters the system. Below that this returns None rather
      than naming a position off three cameo games.
    * Ties break deterministically on (games, starts, defensive spectrum,
      name), never on dict order.

    Returns None for an empty / all-DH / below-floor map. Never raises on
    malformed counts (non-numeric entries read as 0).
    """
    if not by_pos:
        return None

    def _n(v) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    cands = [(pos, _n(v.get("g")), _n(v.get("gs")))
             for pos, v in by_pos.items()
             if pos and pos not in _NON_FIELD]
    cands = [c for c in cands if c[1] > 0 or c[2] > 0]
    if not cands:
        return None
    total_g = sum(c[1] for c in cands)
    cands.sort(key=lambda c: (-c[1], -c[2],
                              _SPECTRUM_RANK.get(c[0], len(_SPECTRUM)), c[0]))
    pos, g, gs = cands[0]
    tie = len(cands) > 1 and cands[1][1] == g
    qualified = g >= min_games or gs >= min_starts
    if not qualified:
        return None
    return {"pos": pos, "g": g, "gs": gs,
            "share": round(g / total_g, 4) if total_g else 0.0,
            "tie": bool(tie), "qualified": True}


def observed_position(by_pos: dict[str, dict],
                      min_games: int = VERSA_MIN_GAMES,
                      min_starts: int = VERSA_MIN_STARTS) -> str | None:
    """Most-played non-DH position, or None. Thin wrapper on
    observed_position_detail - see that docstring for every rule."""
    d = observed_position_detail(by_pos, min_games, min_starts)
    return d["pos"] if d else None


def load_observed_positions(path: str | Path = "data/positions_played.json",
                            min_games: int = VERSA_MIN_GAMES,
                            min_starts: int = VERSA_MIN_STARTS) -> dict[str, str]:
    """{player_key: observed_position} over the whole sidecar.

    Players whose census is empty, all-DH, or below the exposure floor are
    OMITTED (not mapped to None), so a caller's `.get(key)` returns None for
    "no observation" whichever way the player got there. Missing or malformed
    file yields an empty map: this must never be able to break an export.
    """
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for pk, rec in (doc.get("players") or {}).items():
        pos = observed_position((rec or {}).get("by_pos") or {},
                                min_games, min_starts)
        if pos:
            out[pk] = pos
    return out


# Counting convention of the versa artifact. Bump whenever a change makes the
# stored by_pos counts non-comparable with the previous vintage, because the
# monotone floor below is only meaningful WITHIN a convention. Measured case:
# the 2026-07-28 artifact predates the "Minors" rollup dedupe and its career
# totals are almost exactly DOUBLE the current ones (miguel_hiraldo 984 vs
# 492), so using it as a floor would have forced 2,143 of 2,216 players
# (96.7%) into the per-player fallback - safe, but it would have thrown away
# the whole win silently. A stamp mismatch drops the floor instead.
#   1 = pre-2026-07-30 (rollup double-count)
#   2 = rollup-deduped career splits + deterministic versa tie-break
VERSA_CONVENTION = 2


def _prior_career_games(out_path: str | Path,
                        convention: int = VERSA_CONVENTION) -> dict[str, int]:
    """{player_key: total by_pos games} from the PREVIOUS versa artifact.

    Career games at a position are monotone non-decreasing, so the last
    artifact is a valid FLOOR for the next one. The census route below uses it
    as its correctness guard: any player the league-wide census scores BELOW
    his own previous total is missing something (a league outside
    CENSUS_SPORTS, a season the feed dropped, a stale open-season page) and is
    re-derived from the authoritative per-player career endpoint instead.
    Missing/corrupt artifact, or one written under a DIFFERENT counting
    convention -> empty floor, which degrades to "trust the census", the same
    fail-open posture the rest of this module takes."""
    try:
        doc = json.loads(Path(out_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if int(doc.get("convention") or 0) != int(convention):
        return {}
    out: dict[str, int] = {}
    for pk, rec in (doc.get("players") or {}).items():
        try:
            out[pk] = sum(int((v or {}).get("g") or 0)
                          for v in ((rec or {}).get("by_pos") or {}).values())
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def _census_career_by_pos(mlbam_ids, *, sports: "tuple[int, ...]" = None,
                          seasons: "range | list[int] | None" = None,
                          fetch: bool = True,
                          log_: logging.Logger | None = None) -> dict[int, dict[str, dict]]:
    """Career-to-date `{mlbam: {POS: {'g','gs'}}}` from the LEAGUE-WIDE census.

    One cached request per (sportId, season) - ~154 files for 2005-2026 across
    the seven affiliated sportIds - instead of one request per player. Reading
    the whole cached census and folding it down to a board-sized id allowlist
    measured 0.79s on 2026-08-04 (154 files, 38,402 kept rows). Rows for ids
    outside `mlbam_ids` are dropped as they stream, so peak memory is the
    allowlist's slice, not the league's."""
    lg = log_ or log
    if sports is None:
        sports = CENSUS_SPORTS
    if seasons is None:
        seasons = range(CENSUS_FIRST_SEASON, date.today().year + 1)
    keep = {int(m) for m in mlbam_ids if m}
    out: dict[int, dict[str, dict]] = {}
    n_seasons = 0
    for sport_id in sports:
        for season in seasons:
            rows = fetch_season_fielding(sport_id, season, fetch=fetch, log_=lg)
            if rows:
                n_seasons += 1
            for r in rows:
                mid = r.get("mlbam")
                if mid not in keep:
                    continue
                slot = out.setdefault(mid, {}).setdefault(r["pos"], {"g": 0, "gs": 0})
                try:
                    slot["g"] += int(r.get("g") or 0)
                    slot["gs"] += int(r.get("gs") or 0)
                except (TypeError, ValueError):
                    continue
    lg.info("versa census: %d league-seasons covered %d of %d target players",
            n_seasons, len(out), len(keep))
    return out


def build_positions_played(players: list[dict],
                           out_path: str | Path = "data/positions_played.json",
                           throttle: float = 0.05,
                           log_: logging.Logger | None = None,
                           *,
                           use_census: bool | None = None,
                           census_fetch: bool = True,
                           workers: int = 16) -> dict:
    """Build the versa sidecar for every POSITION-PLAYER prospect with an
    mlbam_id. Pitchers are skipped (no versa). Per-player errors are swallowed
    so one bad id can't sink the batch.

    ROUTE (2026-08-04 runtime lane). This step was the single slowest in the
    pipeline at a measured 437s, because it fired ONE StatsAPI request per
    player, serially, with a 50ms sleep between them. It now derives the same
    career `by_pos` from the LEAGUE-WIDE season census that already exists in
    this module (`fetch_season_fielding`): ~154 cached (sportId, season) files
    covering 2005-2026, folded down to the board's id allowlist in ~1s of CPU
    plus a refresh of the seven OPEN-season files.

    Two guards keep the route swap from becoming a silent data regression -
    the failure class that produced the 2026-08-03 standout/recent-games
    defect:

      1. COVERAGE FALLBACK. Any player the census does not carry at all falls
         back to `fetch_player_fielding`, the authoritative per-player career
         endpoint. Measured 2026-08-04 on the 2,216-player board: 193 (8.7%),
         mostly players with no fielding record anywhere yet.
      2. MONOTONE FLOOR. Career games only ever increase, so any player the
         census scores BELOW his own previous artifact total also falls back.
         That catches leagues outside CENSUS_SPORTS, seasons the feed dropped
         (measured: 8 of 2,010 comparable players short by 6+ games, worst
         -53) and any open-season cache that went stale despite the TTL. With
         a deliberately 5-day-stale census the floor pushed 1,610 of 2,216
         into the fallback - the guard doing its job, and still pooled rather
         than serial.

    Both fallbacks run through a thread pool with NO sleep; the serial 50ms
    throttle is kept only for the `workers <= 1` legacy path. Set
    ``use_census=False`` (or ``EEPHUS_VERSA_PER_PLAYER=1``) to force the old
    per-player route for the whole board - still pooled, so even the escape
    hatch is not the 437s original.
    """
    lg = log_ or log
    if use_census is None:
        use_census = os.environ.get("EEPHUS_VERSA_PER_PLAYER") != "1"

    targets: list[tuple[str, int]] = []
    skipped = 0
    for p in players:
        mid = p.get("mlbam_id")
        pk = p.get("player_key")
        if not mid or not pk or (p.get("statline") or {}).get("is_pitcher"):
            skipped += 1
            continue
        try:
            targets.append((pk, int(mid)))
        except (TypeError, ValueError):
            skipped += 1

    out: dict[str, dict] = {}
    err = 0
    n_census = 0
    fallback: list[tuple[str, int]] = []
    # Census value for a player who was ROUTED to the fallback, kept so a
    # failed or empty per-player fetch degrades to the census rather than to
    # nothing. Losing a player entirely is strictly worse than serving a
    # census read the floor merely flagged as incomplete.
    census_backup: dict[str, dict] = {}

    if use_census:
        floor = _prior_career_games(out_path)
        census = _census_career_by_pos((m for _pk, m in targets),
                                       fetch=census_fetch, log_=lg)
        n_missing = n_regressed = 0
        for pk, mid in targets:
            by_pos = census.get(mid)
            if not by_pos:
                n_missing += 1
                fallback.append((pk, mid))
                continue
            if sum(int(v.get("g") or 0) for v in by_pos.values()) < floor.get(pk, 0):
                n_regressed += 1
                census_backup[pk] = by_pos
                fallback.append((pk, mid))
                continue
            out[pk] = {"by_pos": by_pos, "versa": versa_positions(by_pos)}
            n_census += 1
        lg.info("positions_played: %d players from the season census; "
                "%d per-player fallbacks (%d absent from the census, "
                "%d below their previous career total)",
                n_census, len(fallback), n_missing, n_regressed)
    else:
        lg.info("positions_played: census route DISABLED - per-player fetch "
                "for all %d targets", len(targets))
        fallback = list(targets)

    if fallback:
        n_workers = max(1, min(int(workers or 1), len(fallback)))

        def _one(item: tuple[str, int]):
            pk, mid = item
            try:
                return pk, fetch_player_fielding(mid)
            except Exception:                                        # noqa: BLE001
                return pk, None

        if n_workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
                results = list(ex.map(_one, fallback))
        else:
            results = []
            for item in fallback:
                results.append(_one(item))
                if throttle:
                    time.sleep(throttle)
        n_backed_off = 0
        for pk, by_pos in results:
            if not by_pos:
                # None = the per-player fetch raised; {} = it returned no
                # fielding data. Either way, if the census had something for
                # this player, keep it: he was routed here because the census
                # looked INCOMPLETE, which is still better than absent.
                if by_pos is None:
                    err += 1
                backup = census_backup.get(pk)
                if backup:
                    out[pk] = {"by_pos": backup, "versa": versa_positions(backup)}
                    n_backed_off += 1
                continue
            out[pk] = {"by_pos": by_pos, "versa": versa_positions(by_pos)}
        if n_backed_off:
            lg.info("positions_played: %d fallback fetches came back empty or "
                    "failed; kept the census value for those players",
                    n_backed_off)

    payload = {
        "generated_at": date.today().isoformat(),
        "min_games": VERSA_MIN_GAMES,
        "min_starts": VERSA_MIN_STARTS,
        "convention": VERSA_CONVENTION,
        "source": "season_census" if use_census else "per_player",
        "n_from_census": n_census,
        "n_from_per_player": len(fallback) - err,
        "players": out,
    }
    Path(out_path).write_text(json.dumps(payload, separators=(",", ":")),
                              encoding="utf-8")
    lg.info("positions_played: wrote %d players (%d errors, %d skipped) -> %s",
            len(out), err, skipped, out_path)
    return payload


# ══════════════════════════════════════════════════════════════════════════════
# AS-OF-AWARE SEASON CENSUS  (data/positions_played_seasons.json)
# ══════════════════════════════════════════════════════════════════════════════
#
# WHY THIS EXISTS - the defect in the artifact above, stated exactly.
#
# `build_positions_played` has TWO properties that make it unusable as a model
# feature, and neither is a leakage guard:
#
#   (a) PER-PLAYER, PRE-DEBUT scope. Its `__main__` filters on `debut_date` and
#       the production caller (run_monthly step 3a-ii) filters on
#       `p.status != "debuted"`. Both are SCOPE filters inherited from the
#       artifact's original job - a "versa" chip on the prospect board, shipped
#       in c78a5a1 for "all active position prospects" - compounded by COST: the
#       builder fires one StatsAPI request PER PLAYER and run_monthly's own
#       comment measures it at 437s, "the single slowest step in the pipeline",
#       which is why it also sits behind a whole-artifact freshness gate. Nothing
#       in the module, the commit, or the pipeline ever claimed a temporal bound.
#
#   (b) CAREER-TO-DATE values. `fetch_player_fielding` asks for `stats=career`,
#       so every entry is summed to the BUILD DATE with no as-of truncation at
#       all. The pre-debut filter does not date the data; it only decides whose
#       career total gets fetched.
#
# Together those produce a coverage split that is ALIGNED WITH THE LABEL: on the
# eFV hitter matrix, 52.7% of bust rows carry an observation against 5.1% of
# debuted rows, because busts stay "active prospects" forever and debuted players
# are dropped on the next rebuild. A feature whose DEFINITION correlates with the
# target is a leak, which is why efv_model.POS_PREMIUM_USES_OBSERVED and
# prospect_def_value.DEF_VALUE_USES_OBSERVED are both gated default-off.
#
# WHAT THIS BUILDER DOES DIFFERENTLY - three changes, all of them load-bearing:
#
#   1. LEAGUE-WIDE, not per-player. One request per (sportId, season) returns
#       every player-position split in that league-season, the same shape
#       milb_history.season_splits and fielding_innings already use. That removes
#       the cost bound that forced the scope bound: the whole 2005-2026 census
#       across MLB + the six affiliated MiLB sportIds is a few hundred requests
#       instead of one per player, and it covers RETIRED players, whom a
#       board-driven per-player loop can never reach.
#   2. PER-SEASON, not career-to-date. Rows are kept split by season, so any
#       consumer can ask what was known at a date instead of what is known now.
#       `career_by_pos` reproduces the old career-to-date read exactly; the extra
#       resolution is additive.
#   3. NO DEBUT FILTER. Debuted, retired and never-debuted players are all
#       ingested on the same terms, so coverage stops carrying information about
#       the outcome.
#
# THE AS-OF RULE, pre-registered here rather than left to each caller:
#
#   A season counts at an as-of date only if that season was COMPLETE before the
#   date. `season_visible_through(as_of)` returns the last such season using a
#   fixed Oct 1 season boundary (SEASON_END_MONTH / SEASON_END_DAY). A 2024-01-22
#   scouting snapshot therefore sees 2023 and earlier; a 2024-08-15 snapshot ALSO
#   sees only 2023, because the 2024 season had not finished.
#
#   Dropping the partial current season is deliberate and conservative. The
#   season endpoint returns a season TOTAL, so crediting 2024 at an August 2024
#   decision would import games played after it. Game-level truncation is the
#   only way to recover that partial year and this feed cannot give it, so the
#   honest bound is whole completed seasons. It costs recency and buys the
#   property prospect_def_value's ladder eval actually needs: nothing in the
#   vector postdates the decision it is scored against.
#
# WHAT THIS DOES NOT DO: it does not flip any consumer. `positions_played.json`,
# its versa chip and `_up_mid_share_map`'s present-day quality multiplier are all
# untouched.

SEASON_CENSUS_PATH = "data/positions_played_seasons.json"

# One request per (sport, season), cached forever for closed seasons.
_SEASON_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "statsapi_field_season"
# sportId 1 is ALREADY on disk: fielding_innings.py caches the identical
# league-wide MLB fielding doc per season, 2000-2026. Reused rather than refetched.
_MLB_FIELD_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "statsapi_field"

MLB_SPORT = 1
MINOR_SPORTS = (11, 12, 13, 14, 15, 16)   # AAA, AA, A+, A, short-season A, complex/DSL
CENSUS_SPORTS = (MLB_SPORT,) + MINOR_SPORTS
# 2005 is the first season .cache/milb_stats carries and comfortably predates the
# earliest eFV decision year (2011) by a full development cycle.
CENSUS_FIRST_SEASON = 2005

SEASON_END_MONTH, SEASON_END_DAY = 10, 1

_STATS_BASE = "https://statsapi.mlb.com/api/v1/stats"
_UA = {"User-Agent": "Mozilla/5.0"}
_PAGE = 2000
_MIN_INTERVAL = 1.05
_last_request = [0.0]


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def _get_json(url: str, timeout: float = 60.0) -> dict:
    _throttle()
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _lean(splits: list[dict], season: int, sport_id: int) -> list[dict]:
    """StatsAPI fielding splits -> the only fields this census keeps.

    `name` and `age` are kept deliberately: the league-wide feed is the widest
    identity surface we have for players who never reached MLB, and
    `resolve_census_ids` joins on the name and guards the join with the birth
    year that (season - age) implies."""
    out = []
    for s in splits:
        try:
            mid = int((s.get("player") or {})["id"])
            pos = ((s.get("position") or {}).get("abbreviation") or "").strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not pos:
            continue
        st = s.get("stat") or {}
        try:
            g = int(st.get("games") or st.get("gamesPlayed") or 0)
            gs = int(st.get("gamesStarted") or 0)
        except (TypeError, ValueError):
            continue
        if g <= 0 and gs <= 0:
            continue
        try:
            age = int(st.get("age")) if st.get("age") is not None else None
        except (TypeError, ValueError):
            age = None
        out.append({"mlbam": mid, "name": (s.get("player") or {}).get("fullName") or "",
                    "pos": pos, "g": g, "gs": gs, "season": season, "sport": sport_id,
                    "age": age})
    return out


def _mlb_season_from_innings_cache(season: int) -> list[dict] | None:
    """sportId 1 for `season` out of fielding_innings.py's cache, or None.

    Same endpoint, same league-wide shape, already on disk for 2000-2026. Free."""
    path = _MLB_FIELD_CACHE_DIR / f"fld_{season}.json"
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    blocks = doc.get("stats") or []
    if not blocks:
        return None
    splits = []
    for b in blocks:
        splits.extend(b.get("splits") or [])
    return _lean(splits, season, MLB_SPORT) if splits else None


# A CLOSED league-season is immutable, so its cache file is permanent. The
# season IN PROGRESS is not, and this cache had no TTL at all: measured
# 2026-08-04, the on-disk 2026 files were written 2026-07-30 and the census
# therefore undercounted career games for 1,418 of 2,010 board players by a
# median of 2 (never over - a frozen census is a strict time prefix). That is
# harmless for the as-of census, which drops the partial current season by
# construction, and NOT harmless for the versa route, which reads career
# totals. Refresh the open season on this TTL; leave closed seasons alone.
SEASON_OPEN_TTL_SECONDS = 6 * 3600


def _season_is_open(season: int) -> bool:
    """True while `season` can still accrue games (calendar-year test)."""
    try:
        return int(season) >= date.today().year
    except (TypeError, ValueError):
        return False


def fetch_season_fielding(sport_id: int, season: int, fetch: bool = True,
                          log_: logging.Logger | None = None,
                          open_ttl_seconds: float | None = SEASON_OPEN_TTL_SECONDS
                          ) -> list[dict]:
    """Every (player, position) fielding split for one league-season, cached.

    Returns lean rows (see `_lean`). `fetch=False` keeps a caller strictly
    offline: an uncached league-season reads as [] rather than firing a request.
    A failed fetch falls back to whatever is cached and never raises.

    Closed seasons are cached forever. The OPEN season is refreshed once its
    file is older than `open_ttl_seconds` (pass None to restore the old
    permanent-cache behaviour). The refresh is strictly non-destructive: a
    failed or SHORTER re-fetch keeps the cached copy, because a league-season
    can only gain rows and a short page-set is a feed hiccup, never a
    shrinking season."""
    lg = log_ or log
    _SEASON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # v2 keeps `age` (the birth-year guard in resolve_census_ids needs it). The
    # filename is versioned so a v1 cache is refetched rather than silently
    # read back missing the field.
    path = _SEASON_CACHE_DIR / f"fld_v2_{sport_id}_{season}.json"
    cached: list[dict] | None = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
        if cached is not None:
            stale = False
            if fetch and open_ttl_seconds is not None and _season_is_open(season):
                try:
                    stale = (time.time() - path.stat().st_mtime) > open_ttl_seconds
                except OSError:
                    stale = False
            if not stale:
                return cached
    if sport_id == MLB_SPORT and cached is None:
        reused = _mlb_season_from_innings_cache(season)
        if reused is not None:
            path.write_text(json.dumps(reused, separators=(",", ":")), encoding="utf-8")
            return reused
    if not fetch:
        return cached if cached is not None else []
    rows: list[dict] = []
    offset = 0
    while True:
        url = (f"{_STATS_BASE}?stats=season&group=fielding&season={season}"
               f"&sportIds={sport_id}&playerPool=ALL&limit={_PAGE}&offset={offset}")
        try:
            doc = _get_json(url)
        except Exception as exc:                                     # noqa: BLE001
            lg.warning("season fielding fetch failed sport=%s season=%s: %s",
                       sport_id, season, exc)
            return cached if cached is not None else rows
        block = (doc.get("stats") or [{}])[0]
        page = block.get("splits") or []
        rows.extend(_lean(page, season, sport_id))
        total = block.get("totalSplits") or 0
        offset += len(page)
        if not page or offset >= total:
            break
    if cached is not None and len(rows) < len(cached):
        lg.warning("season fielding refresh sport=%s season=%s returned %d rows "
                   "vs %d cached - keeping the cache (a season cannot shrink)",
                   sport_id, season, len(rows), len(cached))
        return cached
    path.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    return rows


def build_positions_played_seasons(
        seasons: "range | list[int] | None" = None,
        sports: "tuple[int, ...]" = CENSUS_SPORTS,
        out_path: str | Path = SEASON_CENSUS_PATH,
        keep_mlbam: "set[int] | None" = None,
        fetch: bool = True,
        log_: logging.Logger | None = None) -> dict:
    """Build the as-of-aware season census.

    Shape::

        {"generated_at": "...", "seasons": [first, last], "sports": [...],
         "season_end": "10-01",
         "players": {mlbam(str): {season(str): {POS: [g, gs]}}}}

    `keep_mlbam` restricts the WRITTEN ARTIFACT to an id allowlist. The full
    league-wide pull always lands in `.cache/statsapi_field_season/`; the
    allowlist only bounds what goes into `data/`, which is a deployed directory.
    Pass None to write everyone.

    Positions are stored as a two-element `[g, gs]` list rather than a dict: the
    census is a few hundred thousand cells and the key names would be most of the
    file. `_pos_map` normalises either form on read.
    """
    lg = log_ or log
    if seasons is None:
        seasons = range(CENSUS_FIRST_SEASON, date.today().year + 1)
    seasons = list(seasons)
    players: dict[str, dict[str, dict[str, list[int]]]] = {}
    n_rows = n_fetched = 0
    for sport_id in sports:
        for season in seasons:
            rows = fetch_season_fielding(sport_id, season, fetch=fetch, log_=lg)
            if rows:
                n_fetched += 1
            for r in rows:
                mid = r["mlbam"]
                if keep_mlbam is not None and mid not in keep_mlbam:
                    continue
                cell = (players.setdefault(str(mid), {})
                                .setdefault(str(r["season"]), {})
                                .setdefault(r["pos"], [0, 0]))
                cell[0] += int(r.get("g") or 0)
                cell[1] += int(r.get("gs") or 0)
                n_rows += 1
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [min(seasons), max(seasons)] if seasons else [],
        "sports": list(sports),
        "season_end": f"{SEASON_END_MONTH:02d}-{SEASON_END_DAY:02d}",
        "min_games": VERSA_MIN_GAMES,
        "min_starts": VERSA_MIN_STARTS,
        "players": players,
    }
    Path(out_path).write_text(json.dumps(payload, separators=(",", ":")),
                              encoding="utf-8")
    lg.info("positions_played_seasons: %d players, %d cells, %d league-seasons -> %s",
            len(players), n_rows, n_fetched, out_path)
    return payload


def season_visible_through(as_of, season_end_month: int = SEASON_END_MONTH,
                           season_end_day: int = SEASON_END_DAY) -> int | None:
    """Last season COMPLETE at `as_of` (a date, or a 'YYYY-MM-DD' string).

    The whole as-of rule lives here. A season Y is complete once
    `date(Y, season_end_month, season_end_day)` has passed, so a January 2024
    decision sees 2023 and an August 2024 decision also sees only 2023.
    Returns None for an unparseable input, which callers read as "no as-of
    truncation is possible" and MUST treat as no observation rather than
    silently falling through to the career total."""
    d = as_of
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return None
    if not isinstance(d, date):
        return None
    y = d.year
    return y if (d.month, d.day) >= (season_end_month, season_end_day) else y - 1


def _pos_map(cell) -> dict[str, int]:
    """`[g, gs]` (stored form) or `{'g':..,'gs':..}` (versa form) -> a dict."""
    if isinstance(cell, dict):
        return {"g": int(cell.get("g") or 0), "gs": int(cell.get("gs") or 0)}
    try:
        return {"g": int(cell[0] or 0), "gs": int(cell[1] or 0)}
    except (TypeError, ValueError, IndexError):
        return {"g": 0, "gs": 0}


def _sum_seasons(seasons_map: dict, through: int | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for season, by_pos in (seasons_map or {}).items():
        try:
            yr = int(season)
        except (TypeError, ValueError):
            continue
        if through is not None and yr > through:
            continue
        for pos, cell in (by_pos or {}).items():
            v = _pos_map(cell)
            slot = out.setdefault(pos, {"g": 0, "gs": 0})
            slot["g"] += v["g"]
            slot["gs"] += v["gs"]
    return out


def career_by_pos(seasons_map: dict) -> dict[str, dict]:
    """Career-to-date `by_pos`, identical in shape to the versa census. Use for
    present-day reads (the versa chip, `_up_mid_share_map`) where "now" is the
    correct question."""
    return _sum_seasons(seasons_map, None)


def as_of_by_pos(seasons_map: dict, as_of) -> dict[str, dict]:
    """`by_pos` restricted to seasons complete at `as_of`.

    Returns {} when `as_of` is unusable, so a caller cannot accidentally get a
    career total where it asked for a dated one."""
    through = season_visible_through(as_of)
    if through is None:
        return {}
    return _sum_seasons(seasons_map, through)


def load_season_census(path: str | Path = SEASON_CENSUS_PATH) -> dict:
    """{mlbam(str): {season(str): {POS: [g, gs]}}}. Empty on any failure - a
    missing census must degrade to "no observation", never raise."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc.get("players") or {}


def observed_position_as_of(seasons_map: dict, as_of,
                            min_games: int = VERSA_MIN_GAMES,
                            min_starts: int = VERSA_MIN_STARTS) -> str | None:
    """Most-played non-DH position among seasons complete at `as_of`.

    Every rule (DH exclusion, exposure floor, deterministic tie-break) is
    `observed_position`'s - this only changes WHICH seasons are summed."""
    return observed_position(as_of_by_pos(seasons_map, as_of), min_games, min_starts)


def observed_positions_as_of(census: dict, as_of_by_key: dict,
                             mlbam_by_key: dict,
                             min_games: int = VERSA_MIN_GAMES,
                             min_starts: int = VERSA_MIN_STARTS) -> dict[str, str]:
    """{player_key: observed position at that key's own as-of date}.

    Keys with no id, no census entry, no usable as-of date or nothing clearing
    the exposure floor are OMITTED, exactly as `load_observed_positions` omits
    them, so `.get(key)` is None for "no observation" whichever way it happened.
    """
    out: dict[str, str] = {}
    for key, as_of in (as_of_by_key or {}).items():
        mid = (mlbam_by_key or {}).get(key)
        if not mid:
            continue
        entry = census.get(str(mid))
        if not entry:
            continue
        pos = observed_position_as_of(entry, as_of, min_games, min_starts)
        if pos:
            out[key] = pos
    return out


# ── Identity resolution for the census ────────────────────────────────────────
# The census is keyed by MLBAM id, so coverage is capped by how many of OUR
# player_keys can be bound to one. That cap is itself label-correlated and it is
# the real binding constraint - see docs/efv-2026-07-30/POSITION_CENSUS_ASOF.md.

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def normalize_name(s) -> str:
    """Accent-folded, punctuation-stripped, suffix-stripped lowercase name. The
    join key for `resolve_census_ids`."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]", " ", s.lower())
    s = _SUFFIX_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


BIRTH_YEAR_TOLERANCE = 1   # StatsAPI age is as-of a season cutoff, so +-1 year


def census_name_index(census_rows: "list[dict]") -> dict:
    """{normalized name: {mlbam: {"seasons": {...}, "birth_years": {...}}}}.

    `birth_years` is the set of (season - age) values the feed implies for that
    id; StatsAPI reports age as of a fixed season cutoff, so a real player
    yields one or two adjacent values."""
    idx: dict[str, dict[int, dict]] = {}
    for r in census_rows:
        nm = normalize_name(r.get("name"))
        if not nm:
            continue
        try:
            mid = int(r["mlbam"])
        except (KeyError, TypeError, ValueError):
            continue
        slot = idx.setdefault(nm, {}).setdefault(mid, {"seasons": set(), "birth_years": set()})
        season, age = r.get("season"), r.get("age")
        if season:
            slot["seasons"].add(int(season))
            if age is not None:
                slot["birth_years"].add(int(season) - int(age))
    return idx


def resolve_census_ids(rows: "list[dict]", name_index: dict,
                       known: dict | None = None) -> tuple[dict, dict]:
    """Bind player_keys to MLBAM ids for census lookup. -> (ids, provenance).

    `rows` are dicts carrying `player_key`, `name`, `birth_year` and `by_year`
    (the latest season a candidate may first appear in). `known` is any
    already-trusted binding and always wins.

    A name match is accepted ONLY when it is UNIQUE after two guards:

      * VINTAGE - the candidate must already be playing by `by_year`. An id
        whose first census season postdates the decision is a different player.
      * BIRTH YEAR - the candidate's implied birth year (census season minus
        StatsAPI age) must be within `BIRTH_YEAR_TOLERANCE` of ours. This is
        what separates two same-named players a decade apart, and it is why
        `_lean` keeps `age`.

    A guard is SKIPPED, not failed, when our side has nothing to compare (no
    birth date on the row, no age in the feed): a missing input must not
    manufacture a rejection. Ambiguous names are DROPPED, never guessed.

    This is a census-scoped binding for coverage measurement; it deliberately
    does not write to `.cache/mlbam_ids.json` or
    `data/sources/mlbam_id_overrides.json`, which the identity pipeline owns.
    """
    ids: dict[str, int] = {}
    prov: dict[str, str] = {}
    for r in rows:
        key = r.get("player_key")
        if not key:
            continue
        pre = (known or {}).get(key)
        if pre:
            ids[key] = int(pre)
            prov[key] = "known"
            continue
        cands = name_index.get(normalize_name(r.get("name"))) or {}
        by_year = r.get("by_year")
        birth_year = r.get("birth_year")
        ok = []
        for mid, seen in cands.items():
            seasons = seen.get("seasons") or set()
            if not seasons or (by_year and min(seasons) > by_year):
                continue
            bys = seen.get("birth_years") or set()
            if birth_year and bys and \
                    min(abs(b - birth_year) for b in bys) > BIRTH_YEAR_TOLERANCE:
                continue
            ok.append(mid)
        if len(ok) == 1:
            ids[key] = int(ok[0])
            prov[key] = "name"
        elif len(ok) > 1:
            prov[key] = "ambiguous"
        else:
            prov[key] = "unresolved"
    return ids, prov


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ts = json.loads(Path("data/timeseries.json").read_text(encoding="utf-8"))
    players = [p for p in (ts.get("players") or [])
               if not p.get("debut_date")]
    build_positions_played(players)
