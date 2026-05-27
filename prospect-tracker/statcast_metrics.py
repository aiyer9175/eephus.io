"""MiLB Statcast-style pitch movement and contact-quality aggregates.

The MLB Stats API game feed exposes Statcast-like fields for some non-MLB
parks: pitch velocity/type, pitch movement, spin, extension, and batted-ball
launch data. Coverage is park/feed dependent, so this module treats the data
as opportunistic and only emits a player row when tracked fields are present.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


MLB_STATS_API = "https://statsapi.mlb.com/api/v1"
MLB_GAME_FEED_API = "https://statsapi.mlb.com/api/v1.1/game"
CACHE_DIR = Path(__file__).parent / ".cache" / "statcast_metrics"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SPORT_LEVELS = {
    1:  "MLB",
    11: "AAA",
    12: "AA",
    13: "A+",
    14: "A",
    16: "CPX",
    17: "DSL",
}
# v20 — MLB added so debuted prospects who played both AAA and the
# majors get level_splits for both. Statcast feed structure is the
# same; only the sport-ID lookup changes. Frontend already iterates
# level_splits with per-level labels, so the addition surfaces
# automatically once the pipeline re-runs.
TRACKED_LEVELS = {"MLB", "AAA", "AA", "A+", "A", "CPX"}
PITCH_PLOT_LIMIT = 900

SESSION = requests.Session()
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries, pool_connections=80, pool_maxsize=80)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)


@dataclass
class StatcastMetricRow:
    player_key: str
    player_name: str
    mlbam_id: int
    season: int
    level: str | None
    is_pitcher: bool
    source: str
    fetched_at: str
    coverage: dict = field(default_factory=dict)
    contact_quality: dict = field(default_factory=dict)
    pitch_movement: dict = field(default_factory=dict)
    pitch_plot: dict = field(default_factory=dict)
    level_splits: list[dict] = field(default_factory=list)
    # v30.7 — Top recent standout single-game performances. Populated
    # from the same /people/{id}/stats?type=gameLog feed the bulk
    # pipeline already consumes; surfaced in the UI under "Standout
    # performances" on the Spotlights page. Up to 5 entries newest-
    # first; each carries date, opponent, raw box-line, and score.
    standout_games: list[dict] = field(default_factory=list)
    # v30.8 — Most-recent N (default 15) game-by-game stat rows, raw
    # box-line shape. Powers the "Recent gameLogs" viz on the
    # prospect detail page. Newest-first; no quality filter applied
    # so the table can show the full chronology (cold games + hot).
    recent_games: list[dict] = field(default_factory=list)


def _get_json(url: str, params: dict | None = None, ttl_seconds: int = 7 * 86400) -> dict:
    key = requests.Request("GET", url, params=params).prepare().url or url
    safe = hashlib.md5(key.encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{safe}.json"
    if path.exists() and time.time() - path.stat().st_mtime <= ttl_seconds:
        return json.loads(path.read_text(encoding="utf-8"))
    time.sleep(0.04)
    resp = SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _safe_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _mean(vals: list[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _rounded_pct_parts(counts: dict[str, int]) -> dict[str, float]:
    """One-decimal percentages that sum to exactly 100.0 when possible."""
    total = sum(counts.values())
    if total <= 0:
        return {k: 0.0 for k in counts}
    raw = {k: counts[k] * 1000 / total for k in counts}
    floors = {k: int(raw[k]) for k in counts}
    remainder = 1000 - sum(floors.values())
    order = sorted(counts, key=lambda k: (raw[k] - floors[k], counts[k]), reverse=True)
    for key in order[:max(0, remainder)]:
        floors[key] += 1
    return {k: round(v / 10, 1) for k, v in floors.items()}


def _level_from_split(split: dict) -> str | None:
    league_name = ((split.get("league") or {}).get("name") or "").lower()
    sport = split.get("sport") or {}
    level = sport.get("abbreviation")
    if "dominican" in league_name:
        return "DSL"
    if "florida complex" in league_name or "arizona complex" in league_name:
        return "CPX"
    return level


def _game_logs(player_id: int, season: int, is_pitcher: bool) -> list[dict]:
    """Fetch per-player game logs using sportId hydrates.

    The plain `leagueListId=milb_full` stats path misses some rookie-ball
    rows, while the hydrate path used by tnestico/mlb_scraper returns CPX/DSL
    game logs when supplied sportId=16.
    """

    group = "pitching" if is_pitcher else "hitting"
    out: list[dict] = []
    seen: set[int] = set()
    for sport_id, level in SPORT_LEVELS.items():
        if level not in TRACKED_LEVELS and level != "DSL":
            continue
        data = _get_json(
            f"{MLB_STATS_API}/people/{player_id}",
            {
                "hydrate": (
                    f"stats(group={group},type=gameLog,season={season},"
                    f"sportId={sport_id},gameType=[R]),hydrations"
                )
            },
            ttl_seconds=86400,
        )
        people = data.get("people") or []
        stats = (people[0].get("stats") or []) if people else []
        for split in (stats[0].get("splits") if stats else []) or []:
            game_pk = (split.get("game") or {}).get("gamePk")
            if not game_pk or int(game_pk) in seen:
                continue
            seen.add(int(game_pk))
            split["_level"] = _level_from_split(split) or level
            out.append(split)
    return out


def _extract_standout_games(
    logs: list[dict],
    is_pitcher: bool,
    limit: int = 8,
    window_days: int = 14,
) -> list[dict]:
    """Pick the player's top standout single-game performances from the
    raw `_game_logs` output. Score each game on raw box-line achievement
    (hitters: hits + HR + XBH; pitchers: K + scoreless IP + low hits) and
    return the top `limit`, sorted newest-first. v30.7 — feeds the
    'Standout performances' widget on the Spotlights page.

    v31.10 — Trailing `window_days` filter (default 14d). Also widened
    inclusion floors per user calibration ("moderate loosening"):
      Hitters: 3+ XBH OR 4+ hits OR 6+ RBI OR multi-HR game
      Pitchers: 10+ K OR 7+ IP no-ER OR per-game FIP ≤ 2.50
        (FIP outing is approximated from the in-game line: see helper).
    Limit bumped to 8 (from 5) to push more per-player history into
    the FV-weighted ticker layer, which still de-dupes per player.
    """
    from datetime import date as _date, timedelta as _td
    cutoff = (_date.today() - _td(days=window_days)).isoformat()

    scored: list[tuple[float, dict]] = []
    for split in logs:
        st = split.get("stat") or {}
        game = split.get("game") or {}
        opp = split.get("opponent") or {}
        date = split.get("date") or (game.get("officialDate"))
        if not date:
            continue
        if date < cutoff:
            continue
        level = split.get("_level")
        score = 0.0
        # Hitter scoring — raw counting stats from gameLog. Higher is
        # better; floors below set inclusion.
        if not is_pitcher:
            h    = _safe_int(st.get("hits"))
            ab   = _safe_int(st.get("atBats"))
            hr   = _safe_int(st.get("homeRuns"))
            doub = _safe_int(st.get("doubles"))
            trip = _safe_int(st.get("triples"))
            rbi  = _safe_int(st.get("rbi"))
            bb   = _safe_int(st.get("baseOnBalls"))
            sb   = _safe_int(st.get("stolenBases"))
            so   = _safe_int(st.get("strikeOuts"))
            if h is None or ab is None or ab == 0:
                continue
            score = (
                (h or 0) * 1.0
                + (hr or 0) * 2.0
                + (trip or 0) * 1.0
                + (doub or 0) * 0.5
                + (rbi or 0) * 0.3
                + (bb or 0) * 0.4
                + (sb or 0) * 0.5
                - (so or 0) * 0.2
            )
            # v31.10 inclusion floor — any of:
            #   * 4+ hits (high-volume night)
            #   * 3+ XBH (doubles + triples + HR combined)
            #   * 6+ RBI (productive RBI night)
            #   * multi-HR game (2+)
            xbh = (doub or 0) + (trip or 0) + (hr or 0)
            qualifies = (
                (h or 0) >= 4
                or xbh >= 3
                or (rbi or 0) >= 6
                or (hr or 0) >= 2
            )
            if not qualifies:
                continue
            line_parts = []
            line_parts.append(f"{h}-for-{ab}")
            if hr:  line_parts.append(f"{hr} HR")
            if doub: line_parts.append(f"{doub} 2B")
            if trip: line_parts.append(f"{trip} 3B")
            if rbi:  line_parts.append(f"{rbi} RBI")
            if bb:   line_parts.append(f"{bb} BB")
            if sb:   line_parts.append(f"{sb} SB")
            line = " · ".join(line_parts)
        else:
            # Pitcher scoring — IP, K, scoreless game, low H, no BB.
            ip   = _safe_float(st.get("inningsPitched"))
            k    = _safe_int(st.get("strikeOuts"))
            er   = _safe_int(st.get("earnedRuns"))
            h    = _safe_int(st.get("hits"))
            bb   = _safe_int(st.get("baseOnBalls"))
            r    = _safe_int(st.get("runs"))
            hra  = _safe_int(st.get("homeRuns"))
            if ip is None or ip < 2.0:
                continue
            # v31.10 inclusion floor — any of:
            #   * 10+ K outing
            #   * 7+ IP with 0 ER (long scoreless start)
            #   * per-game FIP ≤ 2.50 (any of the rare clean lines that
            #     don't trip the K-threshold but are clearly dominant —
            #     e.g. 6 IP, 1 H, 0 ER, 1 BB, 5 K — that's a sub-2 FIP
            #     outing even without 10 K).
            # Per-game FIP approximation: (13*HR + 3*BB - 2*K) / IP + 3.10
            fip_outing = None
            if ip > 0:
                fip_outing = (
                    13.0 * (hra or 0) + 3.0 * (bb or 0) - 2.0 * (k or 0)
                ) / ip + 3.10
            qualifies = (
                (k is not None and k >= 10)
                or (ip >= 7.0 and (er or 0) == 0)
                or (fip_outing is not None and fip_outing <= 2.50 and ip >= 4.0)
            )
            if not qualifies:
                continue
            score = (
                ip * 1.5
                + (k or 0) * 0.8
                - (er or 0) * 1.0
                - (bb or 0) * 0.3
                - (h or 0) * 0.2
                - (hra or 0) * 1.0
            )
            line_parts = [f"{ip} IP", f"{k or 0} K"]
            if (h is not None):  line_parts.append(f"{h} H")
            if (er is not None): line_parts.append(f"{er} ER")
            if bb:               line_parts.append(f"{bb} BB")
            if hra:              line_parts.append(f"{hra} HR")
            line = " · ".join(line_parts)
        entry = {
            "date": date,
            "level": level,
            "opponent": opp.get("name") or opp.get("abbreviation") or "?",
            "is_home": bool((split.get("isHome") if isinstance(split.get("isHome"), bool)
                             else (split.get("game") or {}).get("isHome"))),
            "line": line,
            "score": round(score, 2),
            "is_pitcher": is_pitcher,
        }
        scored.append((score, entry))
    # Sort by score DESC to pick the top N, then resort by date DESC
    # so the rendered list reads newest-first.
    scored.sort(key=lambda x: -x[0])
    top = [e for _, e in scored[:limit]]
    top.sort(key=lambda e: e["date"], reverse=True)
    return top


def _extract_recent_games(
    logs: list[dict],
    is_pitcher: bool,
    limit: int = 15,
) -> list[dict]:
    """Most-recent N games for the player, with raw box-line stats.
    Sorted newest-first. Unlike _extract_standout_games this does NOT
    filter on game quality — every game with ≥1 PA / ≥0.1 IP shows up
    so the UI can render a chronological gamelog. v30.8 — feeds the
    'Last N games' viz on the prospect detail page.
    """
    rows: list[dict] = []
    for split in logs:
        st = split.get("stat") or {}
        game = split.get("game") or {}
        opp = split.get("opponent") or {}
        date = split.get("date") or (game.get("officialDate"))
        if not date:
            continue
        level = split.get("_level")
        if not is_pitcher:
            h    = _safe_int(st.get("hits"))
            ab   = _safe_int(st.get("atBats"))
            pa   = _safe_int(st.get("plateAppearances"))
            if (pa is None or pa < 1) and (ab is None or ab < 1):
                continue
            hr   = _safe_int(st.get("homeRuns")) or 0
            doub = _safe_int(st.get("doubles")) or 0
            trip = _safe_int(st.get("triples")) or 0
            rbi  = _safe_int(st.get("rbi")) or 0
            bb   = _safe_int(st.get("baseOnBalls")) or 0
            so   = _safe_int(st.get("strikeOuts")) or 0
            sb   = _safe_int(st.get("stolenBases")) or 0
            r    = _safe_int(st.get("runs")) or 0
            entry = {
                "date": date,
                "level": level,
                "opponent": opp.get("name") or opp.get("abbreviation") or "?",
                "is_home": bool(split.get("isHome") if isinstance(split.get("isHome"), bool)
                                 else (split.get("game") or {}).get("isHome")),
                "is_pitcher": False,
                "pa":  pa, "ab":  ab, "h":  h, "hr": hr, "doub": doub, "trip": trip,
                "rbi": rbi, "bb":  bb, "so":  so, "sb":  sb, "r":  r,
            }
        else:
            ip   = _safe_float(st.get("inningsPitched"))
            if ip is None or ip < 0.1:
                continue
            k    = _safe_int(st.get("strikeOuts")) or 0
            er   = _safe_int(st.get("earnedRuns")) or 0
            r    = _safe_int(st.get("runs")) or 0
            h    = _safe_int(st.get("hits")) or 0
            bb   = _safe_int(st.get("baseOnBalls")) or 0
            hra  = _safe_int(st.get("homeRuns")) or 0
            entry = {
                "date": date,
                "level": level,
                "opponent": opp.get("name") or opp.get("abbreviation") or "?",
                "is_home": bool(split.get("isHome") if isinstance(split.get("isHome"), bool)
                                 else (split.get("game") or {}).get("isHome")),
                "is_pitcher": True,
                "ip": ip, "k": k, "er": er, "r": r, "h": h, "bb": bb, "hr": hra,
            }
        rows.append(entry)
    # Newest first; take limit.
    rows.sort(key=lambda e: e["date"], reverse=True)
    return rows[:limit]


def _safe_int(v) -> int | None:
    if v is None:
        return None
    try:
        # gameLog returns hits/abs as int already; inningsPitched is str.
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


def _is_barrel(ev: float | None, la: float | None) -> bool:
    """Approximate MLB's barrel band from EV/LA.

    This follows the public rule shape: 98+ mph with a launch-angle window
    that expands as EV rises. It is intentionally conservative and used only
    for leaderboard context.
    """

    if ev is None or la is None or ev < 98:
        return False
    lower = 26 - max(0, ev - 98)
    upper = 30 + max(0, ev - 98)
    return lower <= la <= min(50, upper)


def _finalize_contact(rows: list[dict], is_pitcher: bool) -> dict:
    evs = [_safe_float(r.get("launch_speed")) for r in rows]
    las = [_safe_float(r.get("launch_angle")) for r in rows]
    paired = [(ev, la) for ev, la in zip(evs, las) if ev is not None]
    bbe = len(paired)
    if not bbe:
        return {}
    hard = sum(1 for ev, _la in paired if ev >= 95)
    barrels = sum(1 for ev, la in paired if _is_barrel(ev, la))
    return {
        "batted_balls": bbe,
        "avg_ev": _mean([ev for ev, _la in paired]),
        "max_ev": round(max(ev for ev, _la in paired), 1),
        "avg_la": _mean([la for _ev, la in paired if la is not None]),
        "hard_hit_pct": round(hard / bbe * 100, 1),
        "barrel_pct": round(barrels / bbe * 100, 1),
        "direction": "allowed" if is_pitcher else "hit",
    }


def _finalize_pitch(points: list[dict], outings: list[dict]) -> tuple[dict, dict]:
    tracked = [
        p for p in points
        if p.get("hb") is not None and p.get("ivb") is not None and p.get("pitch_type")
    ]
    if not tracked:
        return {}, {}
    by_type: dict[str, list[dict]] = {}
    totals_by_side: dict[str, int] = {}
    for p in tracked:
        by_type.setdefault(p["pitch_type"], []).append(p)
        side = p.get("batter_side") or "?"
        totals_by_side[side] = totals_by_side.get(side, 0) + 1
    pitch_counts = {code: len(rows) for code, rows in by_type.items()}
    usage_by_type = _rounded_pct_parts(pitch_counts)
    usage_by_side_pitch: dict[str, dict[str, float]] = {}
    for side in totals_by_side:
        side_denominator_counts = {
            pitch_code: sum(1 for r in pitch_rows if (r.get("batter_side") or "?") == side)
            for pitch_code, pitch_rows in by_type.items()
        }
        usage_by_side_pitch[side] = _rounded_pct_parts(side_denominator_counts)
    summary = []
    for code, rows in by_type.items():
        side_counts: dict[str, int] = {}
        for r in rows:
            side = r.get("batter_side") or "?"
            side_counts[side] = side_counts.get(side, 0) + 1
        side_usage = {
            side: {
                "count": count,
                "usage_pct": usage_by_side_pitch.get(side, {}).get(code),
            }
            for side, count in sorted(side_counts.items())
        }
        summary.append({
            "pitch_type": code,
            "pitch_name": rows[0].get("pitch_name") or code,
            "count": len(rows),
            "usage_pct": usage_by_type.get(code),
            "avg_velo": _mean([r.get("velo") for r in rows]),
            "max_velo": round(max([r.get("velo") for r in rows if r.get("velo") is not None], default=0), 1) or None,
            "avg_hb": _mean([r.get("hb") for r in rows]),
            "avg_ivb": _mean([r.get("ivb") for r in rows]),
            "avg_spin": _mean([r.get("spin") for r in rows]),
            "usage_by_batter_side": side_usage,
        })
    summary.sort(key=lambda r: -r["count"])
    plot_points = tracked[-PITCH_PLOT_LIMIT:]
    return (
        {
            "tracked_pitches": len(tracked),
            "pitch_summary": summary,
            "outings": outings,
        },
        {
            "x_axis": "Horizontal break",
            "y_axis": "Induced vertical break",
            "points": plot_points,
        },
    )


def _primary_level(logs: list[dict], level_hint: str | None) -> str | None:
    levels = [s.get("_level") for s in logs if s.get("_level") in TRACKED_LEVELS]
    if level_hint in levels:
        return level_hint
    if not levels:
        return level_hint if level_hint in TRACKED_LEVELS else None
    counts = {level: levels.count(level) for level in set(levels)}
    return sorted(counts, key=lambda level: (-counts[level], level))[0]


def _coverage_from_games(
    games_checked: int,
    games_with_pitch: int,
    games_with_contact: int,
    venues: dict[str, dict],
) -> dict:
    return {
        "games_checked": games_checked,
        "games_with_pitch_movement": games_with_pitch,
        "games_with_contact_quality": games_with_contact,
        "venues": sorted(venues.values(), key=lambda v: str(v.get("name") or "")),
    }


def fetch_statcast_metrics_for_player(
    player_key: str,
    player_name: str,
    mlbam_id: int | None,
    season: int,
    level_hint: str | None,
    is_pitcher: bool,
    feed_cache: dict[int, dict] | None = None,
) -> StatcastMetricRow | None:
    """Build the Statcast metric row for one player.

    v19 — Optional `feed_cache` arg: when provided, game-feed lookups
    come from the in-memory dict instead of firing fresh `_get_json`
    calls. The bulk entry point (`fetch_statcast_metrics_for_players`)
    pre-fetches every unique game_pk across the cohort exactly once and
    threads the cache in here, so each game feed is parsed at most
    once per run instead of once per (player × game). Cuts the
    Statcast step's wall time roughly in half on rosters with heavy
    same-game overlap (AAA/AA where every prospect plays the same
    handful of teams).
    """
    if not mlbam_id:
        return None
    logs = _game_logs(int(mlbam_id), season, is_pitcher=is_pitcher)
    logs = [s for s in logs if (s.get("_level") or level_hint) in TRACKED_LEVELS]
    if not logs:
        return None

    pitch_points: list[dict] = []
    contact_rows: list[dict] = []
    outings: list[dict] = []
    venues: dict[str, dict] = {}
    games_checked = games_with_pitch = games_with_contact = 0
    per_level: dict[str, dict] = {}
    primary_level = _primary_level(logs, level_hint)

    for split in logs:
        level = split.get("_level") or level_hint
        if level not in TRACKED_LEVELS:
            continue
        level_bucket = per_level.setdefault(level, {
            "pitch_points": [],
            "contact_rows": [],
            "outings": [],
            "venues": {},
            "games_checked": 0,
            "games_with_pitch": 0,
            "games_with_contact": 0,
        })
        game_pk = int((split.get("game") or {}).get("gamePk") or 0)
        if not game_pk:
            continue
        games_checked += 1
        level_bucket["games_checked"] += 1
        # v19 — Prefer in-memory cache when bulk caller pre-fetched.
        if feed_cache is not None and game_pk in feed_cache:
            data = feed_cache[game_pk]
        else:
            data = _get_json(f"{MLB_GAME_FEED_API}/{game_pk}/feed/live", ttl_seconds=86400)
        game_data = data.get("gameData") or {}
        venue = game_data.get("venue") or {}
        venue_key = str(venue.get("id") or venue.get("name") or "")
        if venue_key:
            venues[venue_key] = {"id": venue.get("id"), "name": venue.get("name")}
            level_bucket["venues"][venue_key] = {"id": venue.get("id"), "name": venue.get("name")}
        game_date = (game_data.get("datetime") or {}).get("officialDate") or split.get("date")
        pitch_count = tracked_pitch_count = contact_count = 0
        type_counts: dict[str, int] = {}

        for play in data.get("liveData", {}).get("plays", {}).get("allPlays", []):
            matchup = play.get("matchup") or {}
            batter = matchup.get("batter") or {}
            pitcher = matchup.get("pitcher") or {}
            player_match = int((pitcher if is_pitcher else batter).get("id") or 0) == int(mlbam_id)
            if not player_match:
                continue
            for event in play.get("playEvents", []):
                if not event.get("isPitch"):
                    continue
                pitch_data = event.get("pitchData") or {}
                details = event.get("details") or {}
                pitch_type = (details.get("type") or {}).get("code")
                pitch_name = (details.get("type") or {}).get("description") or pitch_type
                breaks = pitch_data.get("breaks") or {}
                if is_pitcher:
                    pitch_count += 1
                    if pitch_type:
                        type_counts[pitch_type] = type_counts.get(pitch_type, 0) + 1
                    point = {
                        "game_pk": game_pk,
                        "date": game_date,
                        "venue_id": venue.get("id"),
                        "venue_name": venue.get("name"),
                        "pitch_type": pitch_type,
                        "pitch_name": pitch_name,
                        "batter_side": (matchup.get("batSide") or {}).get("code"),
                        "velo": _safe_float(pitch_data.get("startSpeed")),
                        "hb": _safe_float(breaks.get("breakHorizontal")),
                        "ivb": _safe_float(breaks.get("breakVerticalInduced")),
                        "spin": _safe_float(breaks.get("spinRate")),
                        "extension": _safe_float(pitch_data.get("extension")),
                    }
                    if point["hb"] is not None and point["ivb"] is not None:
                        tracked_pitch_count += 1
                        pitch_points.append(point)
                        level_bucket["pitch_points"].append(point)
                hit_data = event.get("hitData") or {}
                launch_speed = _safe_float(hit_data.get("launchSpeed"))
                launch_angle = _safe_float(hit_data.get("launchAngle"))
                if launch_speed is not None:
                    contact_count += 1
                    contact_rows.append({
                        "game_pk": game_pk,
                        "date": game_date,
                        "launch_speed": launch_speed,
                        "launch_angle": launch_angle,
                    })
                    level_bucket["contact_rows"].append({
                        "game_pk": game_pk,
                        "date": game_date,
                        "launch_speed": launch_speed,
                        "launch_angle": launch_angle,
                    })
        if tracked_pitch_count:
            games_with_pitch += 1
            level_bucket["games_with_pitch"] += 1
        if contact_count:
            games_with_contact += 1
            level_bucket["games_with_contact"] += 1
        if is_pitcher and pitch_count:
            outing = {
                "game_pk": game_pk,
                "date": game_date,
                "venue_id": venue.get("id"),
                "venue_name": venue.get("name"),
                "pitches": pitch_count,
                "tracked_pitches": tracked_pitch_count,
                "pitch_types": type_counts,
            }
            outings.append(outing)
            level_bucket["outings"].append(outing)

    contact = _finalize_contact(contact_rows, is_pitcher=is_pitcher)
    pitch_movement, pitch_plot = _finalize_pitch(pitch_points, outings) if is_pitcher else ({}, {})
    if not contact and not pitch_movement:
        return None
    level_splits: list[dict] = []
    for level, bucket in sorted(per_level.items()):
        split_contact = _finalize_contact(bucket["contact_rows"], is_pitcher=is_pitcher)
        split_pitch_movement, split_pitch_plot = (
            _finalize_pitch(bucket["pitch_points"], bucket["outings"])
            if is_pitcher else ({}, {})
        )
        if not split_contact and not split_pitch_movement:
            continue
        level_splits.append({
            "player_key": player_key,
            "player_name": player_name,
            "mlbam_id": int(mlbam_id),
            "season": season,
            "level": level,
            "is_pitcher": is_pitcher,
            "source": "MLB Stats API game feed",
            "fetched_at": date.today().isoformat(),
            "coverage": _coverage_from_games(
                bucket["games_checked"],
                bucket["games_with_pitch"],
                bucket["games_with_contact"],
                bucket["venues"],
            ),
            "contact_quality": split_contact,
            "pitch_movement": split_pitch_movement,
            "pitch_plot": split_pitch_plot,
        })
    return StatcastMetricRow(
        player_key=player_key,
        player_name=player_name,
        mlbam_id=int(mlbam_id),
        season=season,
        level=primary_level,
        is_pitcher=is_pitcher,
        source="MLB Stats API game feed",
        fetched_at=date.today().isoformat(),
        coverage=_coverage_from_games(games_checked, games_with_pitch, games_with_contact, venues),
        contact_quality=contact,
        pitch_movement=pitch_movement,
        pitch_plot=pitch_plot,
        level_splits=level_splits,
        # v30.7 — Pull top 8 standout single-game performances off the
        # same `logs` we already walked above. Free piggyback — no
        # extra HTTP, just an extra pass over the per-game stat dicts.
        # v31.10 — limit bumped to 8 (was 5), trailing-14d window now
        # applied inside _extract_standout_games so the ticker leads
        # with the past two weeks of activity.
        standout_games=_extract_standout_games(logs, is_pitcher, limit=8),
        # v30.8 — Last 15 game rows for the prospect-detail "Recent
        # gameLogs" viz. Same `logs` we already walked above (free
        # piggyback, no extra HTTP).
        recent_games=_extract_recent_games(logs, is_pitcher, limit=15),
    )


def fetch_statcast_metrics_for_players(
    players: list[tuple[str, str, int | None, str | None, bool]],
    season: int,
    workers: int = 10,
) -> dict[str, StatcastMetricRow]:
    targets = [
        p for p in players
        if p[2] is not None and (p[3] in TRACKED_LEVELS or p[3] is None)
    ]
    out: dict[str, StatcastMetricRow] = {}
    if not targets:
        return out
    import logging, time as _time
    _log = logging.getLogger(__name__)
    max_workers = max(1, min(workers, len(targets)))
    # ============================================================
    # v19 — Three-pass bulk fetch with cross-player game-feed dedup.
    # Previous version made one /feed/live call per (player × game),
    # so two prospects in the same AAA game each fetched the same
    # 200 KB game feed. Now: pass 1 hydrates game logs (one /people
    # lookup per (player, sport_id), already cached); pass 2 collects
    # the UNIQUE set of game_pks across the whole cohort and fetches
    # each /feed/live exactly once into an in-memory dict; pass 3
    # processes each player using the cached feeds (CPU only, no HTTP).
    # ============================================================

    # ---- PASS 1: game logs per player (parallel, cached) ----
    logs_by_key: dict[str, list[dict]] = {}
    _p1_start = _time.monotonic()
    _log.info("statcast pass 1/3: fetching game logs for %d players (%d workers)",
              len(targets), max_workers)
    def _fetch_logs(item):
        key, _name, mlbam, _level, is_p = item
        try:
            return key, _game_logs(int(mlbam), season, is_pitcher=is_p)
        except Exception as e:
            _log.debug("statcast logs failed for %s: %s", key, e)
            return key, []
    _p1_done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for key, logs in ex.map(_fetch_logs, targets):
            logs_by_key[key] = logs
            _p1_done += 1
            if _p1_done % 250 == 0 or _p1_done == len(targets):
                _log.info("statcast pass 1/3: %d/%d game-log fetches done (%.0fs)",
                          _p1_done, len(targets), _time.monotonic() - _p1_start)

    # ---- PASS 2: unique game-feed fetch (parallel, cached) ----
    game_pks: set[int] = set()
    for logs in logs_by_key.values():
        for split in logs:
            gpk = int((split.get("game") or {}).get("gamePk") or 0)
            if gpk:
                game_pks.add(gpk)
    feed_cache: dict[int, dict] = {}
    if game_pks:
        _p2_start = _time.monotonic()
        _log.info("statcast pass 2/3: fetching %d unique game feeds (deduped from %d player×game lookups)",
                  len(game_pks), sum(len(v) for v in logs_by_key.values()))
        def _fetch_feed(gpk):
            try:
                return gpk, _get_json(f"{MLB_GAME_FEED_API}/{gpk}/feed/live", ttl_seconds=86400)
            except Exception as e:
                _log.debug("statcast feed failed for game %s: %s", gpk, e)
                return gpk, {}
        _p2_done = 0
        # Feeds are large; cap workers so we don't slam the API.
        feed_workers = max(1, min(max_workers, 12))
        with concurrent.futures.ThreadPoolExecutor(max_workers=feed_workers) as ex:
            for gpk, feed in ex.map(_fetch_feed, sorted(game_pks)):
                feed_cache[gpk] = feed
                _p2_done += 1
                if _p2_done % 500 == 0 or _p2_done == len(game_pks):
                    elapsed = _time.monotonic() - _p2_start
                    rate = _p2_done / max(elapsed, 0.001)
                    eta = (len(game_pks) - _p2_done) / rate if rate > 0 else 0
                    _log.info("statcast pass 2/3: %d/%d feeds (%.0fs elapsed · ~%.0fs left)",
                              _p2_done, len(game_pks), elapsed, eta)

    # ---- PASS 3: per-player processing using the cached feeds ----
    _p3_start = _time.monotonic()
    _log.info("statcast pass 3/3: processing %d players against cached feeds", len(targets))
    _p3_done = 0
    # Parallel because _finalize_pitch / contact has noticeable CPU work
    # for pitchers with many tracked pitches.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_key = {
            ex.submit(
                fetch_statcast_metrics_for_player,
                key, name, mlbam, season, level, is_pitcher,
                feed_cache,
            ): key
            for key, name, mlbam, level, is_pitcher in targets
        }
        for fut in concurrent.futures.as_completed(future_to_key):
            key = future_to_key[fut]
            try:
                row = fut.result()
            except Exception:
                row = None
            if row:
                out[key] = row
            _p3_done += 1
            if _p3_done % 500 == 0 or _p3_done == len(targets):
                _log.info("statcast pass 3/3: %d/%d processed (%d with data, %.0fs elapsed)",
                          _p3_done, len(targets), len(out), _time.monotonic() - _p3_start)
    return out
