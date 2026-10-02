# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Self-computed reliever leverage + win-probability, from MLB's own feed.

FanGraphs is blocked for autonomous pulls here (HTTP 403), so gmLI / WPA /
WPA-LI / Shutdowns / Meltdowns are computed IN-HOUSE from the MLB StatsAPI
winProbability resource:

    GET https://statsapi.mlb.com/api/v1/game/{game_pk}/winProbability

which returns one object per plate appearance carrying `leverageIndex`,
`homeTeamWinProbability`, and `homeTeamWinProbabilityAdded` (verified present on
~99% of plays back to 2015; the leadoff PA is the only common gap). For the
pitcher on the mound each play:

  - the fielding (pitcher's) team is HOME in the top half, AWAY in the bottom;
  - WPA_play  = homeTeamWinProbabilityAdded/100, sign-flipped when the pitcher
    is the away team (win units, pitcher's perspective);
  - WPA/LI_play = WPA_play / leverageIndex (context-neutral);
  - gmLI       = mean leverageIndex at the play where the reliever ENTERS a game;
  - a Shutdown / Meltdown is an APPEARANCE whose summed WPA is >= +0.06 / <= -0.06
    (the FanGraphs definitions).

The result keys by MLBAM id, so it joins cleanly to the season pitching statline
(rem_plus.Reliever). The per-game `winProbability` feed is cached on disk by
game_pk (final games are immutable), reusing feed_cache's hardened, 429-retrying
session. ALL NETWORK IS BEHIND EXPLICIT CALLS - nothing fetches at import - so
tests drive the pure accumulate()/_finalize() path with synthetic plays and
never touch the wire.
"""
from __future__ import annotations

import json
import logging
import statistics
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

import feed_cache  # reuse the hardened session + immutable-final TTL logic

_log = logging.getLogger(__name__)

WP_API = "https://statsapi.mlb.com/api/v1/game"
SCHEDULE_API = "https://statsapi.mlb.com/api/v1/schedule"

CACHE_DIR = Path(__file__).parent / ".cache" / "win_prob"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# FanGraphs Shutdown/Meltdown thresholds (win-probability added per appearance).
SD_MD_THRESHOLD = 0.06


# --------------------------------------------------------------------------- #
# Network layer (explicit calls only)
# --------------------------------------------------------------------------- #
def get_win_probability(game_pk: int, *, game_date: str | None = None) -> list:
    """The `/winProbability` play list for one game, cached on disk by game_pk.

    Mirrors feed_cache.get_game_feed's caching (final games are immutable, so the
    TTL is chosen from the game date), but hits the winProbability resource,
    which is the ONLY endpoint carrying leverageIndex + WPA (the `/feed/live`
    payload has neither)."""
    game_pk = int(game_pk)
    path = CACHE_DIR / f"{game_pk}.json"
    ttl = feed_cache._ttl_for_date(game_date)
    if path.exists() and time.time() - path.stat().st_mtime <= ttl:
        try:
            cached = _plays_of(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            cached = None  # corrupt/partial cache - re-fetch
        # The date-derived FINAL_TTL is trusted only for a play list that ends
        # the game, the same gate feed_cache.get_game_feed puts on its feeds
        # (_looks_final). Game 823062 (2026-07-07, MIL at STL) was cached an
        # hour after first pitch holding one pre-game advisory, and the date
        # TTL served that partial list as final for three months, so the play
        # corpus carried the game with no plate appearance in it.
        if cached is not None and (ttl < feed_cache.FINAL_TTL
                                   or plays_end_the_game(cached)):
            return cached
    time.sleep(0.04)
    resp = feed_cache.SESSION.get(f"{WP_API}/{game_pk}/winProbability", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)  # atomic
    return _plays_of(data)


def plays_end_the_game(plays) -> bool:
    """Does this play list end the game? True when its last play leaves the home
    win probability at 0 or 100, which is how every finished game in the corpus
    ends (a rain-shortened game included: its last row is the delay advisory at
    0 or 100). A list cut off before the end reads False, so it is re-fetched."""
    if not plays:
        return False
    wp = (plays[-1] or {}).get("homeTeamWinProbability")
    try:
        return round(float(wp), 6) in (0.0, 100.0)
    except (TypeError, ValueError):
        return False


def season_game_pks(season: int, *, game_type: str = "R") -> list[tuple[int, str]]:
    """(game_pk, official_date) for every FINAL MLB game of a season."""
    resp = feed_cache.SESSION.get(
        SCHEDULE_API,
        params={"sportId": 1, "season": int(season), "gameType": game_type},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    out: list[tuple[int, str]] = []
    seen: set[int] = set()
    for d in data.get("dates", []):
        for g in d.get("games", []):
            state = ((g.get("status") or {}).get("abstractGameState"))
            if state != "Final":
                continue
            pk = g.get("gamePk")
            if not pk or int(pk) in seen:
                continue
            seen.add(int(pk))
            out.append((int(pk), g.get("officialDate") or d.get("date")))
    return out


def fetch_season_leverage(season: int, *, limit: Optional[int] = None,
                          game_type: str = "R",
                          progress: Optional[Callable[[int, int], None]] = None
                          ) -> tuple[dict, dict]:
    """Walk a season's FINAL games, accumulate per-pitcher leverage, and return
    ({mlbam: metrics}, coverage). Best-effort + resumable: a game whose feed
    fails is logged and skipped (never aborts), and cached games are free, so
    re-runs only fetch the trailing new games. `limit` caps the game count (for
    a fast partial refresh)."""
    pks = season_game_pks(season, game_type=game_type)
    if limit is not None:
        pks = pks[:limit]
    acc: dict = {}
    used = 0
    total = len(pks)
    for i, (pk, gd) in enumerate(pks):
        try:
            plays = get_win_probability(pk, game_date=gd)
        except Exception as e:  # network / parse - skip this game
            _log.warning("winProbability fetch failed for game %s: %s", pk, e)
            continue
        _fold_game(acc, plays)
        used += 1
        if progress and (i % 100 == 0 or i == total - 1):
            progress(i + 1, total)
    return _finalize(acc), {"games": used, "games_total": total}


# --------------------------------------------------------------------------- #
# Pure accumulation (no network - unit-tested with synthetic plays)
# --------------------------------------------------------------------------- #
def _plays_of(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("winProbability") or []
    return []


def _is_home_pitcher(play: dict) -> bool:
    """The pitcher's team fields; the fielding team is HOME in the top half."""
    ab = play.get("about") or {}
    half = ab.get("halfInning")
    if half:
        return half == "top"
    return bool(ab.get("isTopInning"))


def _game_pitcher_dict(plays: Iterable[dict]) -> dict:
    """One game's per-pitcher within-game accumulator (wpa, wpa_li, entry_li,
    entry_inning, name), keyed by pitcher id. Shared by the reliever + starter
    folds so both read one pass over the play stream. Pure."""
    gp: dict = {}
    for play in plays:
        matchup = play.get("matchup") or {}
        p = matchup.get("pitcher") or {}
        pid = p.get("id")
        if not pid:
            continue
        home = _is_home_pitcher(play)
        added = play.get("homeTeamWinProbabilityAdded")
        li = play.get("leverageIndex")
        inning = (play.get("about") or {}).get("inning")
        d = gp.get(pid)
        if d is None:
            d = {"wpa": 0.0, "wpa_li": 0.0, "entry_li": li,
                 "entry_inning": inning, "name": p.get("fullName", "")}
            gp[pid] = d
        elif d["entry_li"] is None and li is not None:
            # first play lacked LI (leadoff PA); take the next available
            d["entry_li"] = li
            if d["entry_inning"] is None:
                d["entry_inning"] = inning
        if added is not None:
            wp = (added if home else -added) / 100.0
            d["wpa"] += wp
            if li and li > 0:
                d["wpa_li"] += wp / li
    return gp


def _merge_reliever(acc: dict, gp: dict) -> None:
    """Merge one game's per-pitcher dict into the RELIEVER accumulator, dropping
    start-games (entry_inning==1). Byte-identical to the original _fold_game merge
    (test_mlb_leverage.py locks the reliever numbers)."""
    for pid, d in gp.items():
        # A pitcher whose first appearance in a game is in the 1st inning
        # started or opened that game. Folding a whole start into relief gmLI /
        # SD-MD / WPA / appearances contaminates the leverage profile of
        # spot-starting swingmen (who are admitted to the reliever pool at
        # GS/G <= 0.10). Drop start-games from the fold; true 1st-inning relief
        # entries are rare and genuine openers are excluded downstream anyway.
        if d.get("entry_inning") == 1:
            continue
        a = acc.get(pid)
        if a is None:
            a = {"wpa": 0.0, "wpa_li": 0.0, "gmli_sum": 0.0, "gmli_n": 0,
                 "sd": 0, "md": 0, "appearances": 0, "entry_innings": [], "name": d["name"]}
            acc[pid] = a
        a["wpa"] += d["wpa"]
        a["wpa_li"] += d["wpa_li"]
        a["appearances"] += 1
        if d["entry_li"] is not None:
            a["gmli_sum"] += d["entry_li"]
            a["gmli_n"] += 1
        if d["entry_inning"] is not None:
            a["entry_innings"].append(d["entry_inning"])
        if d["wpa"] >= SD_MD_THRESHOLD:
            a["sd"] += 1
        elif d["wpa"] <= -SD_MD_THRESHOLD:
            a["md"] += 1
        if d["name"]:
            a["name"] = d["name"]


def _fold_game(acc: dict, plays: Iterable[dict]) -> None:
    """Fold one game's plays into the running per-RELIEVER accumulator. Kept as a
    thin composition of the two extracted helpers so the reliever output is
    unchanged."""
    _merge_reliever(acc, _game_pitcher_dict(plays))


# ---- batter + starter folds (S-1; the reliever fold above is untouched) ----- #
def _fold_game_batters(acc: dict, plays: Iterable[dict]) -> None:
    """Per-BATTER accumulation, per plate appearance. WPA_batter = -WPA_pitcher
    (the batting team is the pitcher's opponent), pLI = mean leverageIndex faced.
    The winProbability feed carries one object per PA, so one play == one PA."""
    for play in plays:
        matchup = play.get("matchup") or {}
        b = matchup.get("batter") or {}
        bid = b.get("id")
        if not bid:
            continue
        home_bat = not _is_home_pitcher(play)          # batter bats in the other half
        added = play.get("homeTeamWinProbabilityAdded")
        li = play.get("leverageIndex")
        a = acc.get(bid)
        if a is None:
            a = {"pa": 0, "wpa": 0.0, "wpa_li": 0.0, "li_sum": 0.0, "li_n": 0,
                 "name": b.get("fullName", "")}
            acc[bid] = a
        a["pa"] += 1
        if added is not None:
            wp = (added if home_bat else -added) / 100.0
            a["wpa"] += wp
            if li and li > 0:
                a["wpa_li"] += wp / li
        if li is not None:
            a["li_sum"] += li
            a["li_n"] += 1
        if b.get("fullName"):
            a["name"] = b["fullName"]


def _finalize_batters(acc: dict) -> dict:
    out: dict = {}
    for bid, a in acc.items():
        pli = (a["li_sum"] / a["li_n"]) if a["li_n"] else None
        # FanGraphs Clutch = WPA/pLI - WPA/LI (context-timing above a rate-neutral base).
        clutch = round(a["wpa"] / pli - a["wpa_li"], 3) if pli else None
        out[int(bid)] = {
            "mlbam": int(bid), "name": a["name"], "pa": a["pa"],
            "wpa": round(a["wpa"], 3), "wpa_li": round(a["wpa_li"], 3),
            "pli": round(pli, 2) if pli is not None else None,
            "clutch": clutch,
        }
    return out


def _merge_starter(acc: dict, gp: dict) -> None:
    """Merge one game's per-pitcher dict into the STARTER accumulator, KEEPING only
    the entry_inning==1 games (starts/openers) that the reliever fold drops."""
    for pid, d in gp.items():
        if d.get("entry_inning") != 1:
            continue
        a = acc.get(pid)
        if a is None:
            a = {"starts": 0, "wpa": 0.0, "wpa_li": 0.0, "name": d["name"]}
            acc[pid] = a
        a["starts"] += 1
        a["wpa"] += d["wpa"]
        a["wpa_li"] += d["wpa_li"]
        if d["name"]:
            a["name"] = d["name"]


def _finalize_starters(acc: dict) -> dict:
    out: dict = {}
    for pid, a in acc.items():
        starts = a["starts"]
        out[int(pid)] = {
            "mlbam": int(pid), "name": a["name"], "starts": starts,
            "wpa": round(a["wpa"], 3),
            "wpa_per_start": round(a["wpa"] / starts, 3) if starts else None,
            "wpa_li": round(a["wpa_li"], 3),
        }
    return out


def _finalize(acc: dict) -> dict:
    out: dict = {}
    for pid, a in acc.items():
        gmli = (a["gmli_sum"] / a["gmli_n"]) if a["gmli_n"] else None
        out[int(pid)] = {
            "mlbam": int(pid),
            "name": a["name"],
            "gmli": round(gmli, 3) if gmli is not None else None,
            "wpa": round(a["wpa"], 3),
            "wpa_li": round(a["wpa_li"], 3),
            "sd": a["sd"],
            "md": a["md"],
            "appearances": a["appearances"],
            "entry_inning": (round(statistics.median(a["entry_innings"]), 1)
                             if a["entry_innings"] else None),
        }
    return out


def accumulate(games: Iterable[tuple[int, list]]) -> dict:
    """Pure: fold an iterable of (game_pk, plays) into finalized per-pitcher
    leverage metrics keyed by MLBAM id. The network path shares this fold."""
    acc: dict = {}
    for _pk, plays in games:
        _fold_game(acc, plays)
    return _finalize(acc)


def accumulate_batters(games: Iterable[tuple[int, list]]) -> dict:
    """Pure batter fold over (game_pk, plays) -> finalized per-batter metrics."""
    acc: dict = {}
    for _pk, plays in games:
        _fold_game_batters(acc, plays)
    return _finalize_batters(acc)


def accumulate_starters(games: Iterable[tuple[int, list]]) -> dict:
    """Pure starter fold over (game_pk, plays) -> finalized per-starter metrics."""
    acc: dict = {}
    for _pk, plays in games:
        _merge_starter(acc, _game_pitcher_dict(plays))
    return _finalize_starters(acc)


def fetch_season_all_leverage(season: int, *, limit: Optional[int] = None,
                              game_type: str = "R",
                              progress: Optional[Callable[[int, int], None]] = None):
    """Single-pass season walk that folds RELIEVER + BATTER + STARTER accumulators
    from the same cached winProbability feed (the cache makes the re-walk free, so
    one pass beats three). Returns (relievers, batters, starters, coverage). The
    per-game pitcher dict is built once and shared by the reliever + starter merges
    so the reliever output stays identical to fetch_season_leverage."""
    pks = season_game_pks(season, game_type=game_type)
    if limit is not None:
        pks = pks[:limit]
    rel_acc: dict = {}
    bat_acc: dict = {}
    strt_acc: dict = {}
    used = 0
    total = len(pks)
    for i, (pk, gd) in enumerate(pks):
        try:
            plays = get_win_probability(pk, game_date=gd)
        except Exception as e:  # network / parse - skip this game
            _log.warning("winProbability fetch failed for game %s: %s", pk, e)
            continue
        gp = _game_pitcher_dict(plays)
        _merge_reliever(rel_acc, gp)
        _merge_starter(strt_acc, gp)
        _fold_game_batters(bat_acc, plays)
        used += 1
        if progress and (i % 100 == 0 or i == total - 1):
            progress(i + 1, total)
    return (_finalize(rel_acc), _finalize_batters(bat_acc), _finalize_starters(strt_acc),
            {"games": used, "games_total": total})
