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
    11: "AAA",
    12: "AA",
    13: "A+",
    14: "A",
    16: "CPX",
    17: "DSL",
}
TRACKED_LEVELS = {"AAA", "AA", "A+", "A", "CPX"}
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
) -> StatcastMetricRow | None:
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
    max_workers = max(1, min(workers, len(targets)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_key = {
            ex.submit(fetch_statcast_metrics_for_player, key, name, mlbam, season, level, is_pitcher): key
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
    return out
