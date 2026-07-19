# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

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
import math
import multiprocessing
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import feed_cache as feed_cache_mod  # aliased: a local `feed_cache` dict shadows it below


MLB_STATS_API = "https://statsapi.mlb.com/api/v1"
MLB_GAME_FEED_API = "https://statsapi.mlb.com/api/v1.1/game"
# v31.12 — Cache version is appended to the hash key, so bumping it
# auto-invalidates every cached response without manual cleanup. Bump
# when the upstream API response shape changes or when this module
# starts consuming additional fields that older cached payloads lack.
# Current bumps:
#   v1 — original
#   v2 — added gameLog standout/recent_games piggyback (v30.7/.8)
#   v3 — switched zone-metric aggregation to per-level splits (v20)
#   v4 — added hitter batted-ball coordinates, spray buckets, and
#        rolling estimated xwOBA from the same game feed.
#   v5 — added pitch acceleration / release-side fields for tjStuff+.
CACHE_VERSION = "v5"
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
    # Cache version goes INTO the hash so a bump invalidates everything.
    versioned_key = f"{CACHE_VERSION}|{key}"
    safe = hashlib.md5(versioned_key.encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{safe}.json"
    if path.exists() and time.time() - path.stat().st_mtime <= ttl_seconds:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # corrupt/half-written cache (e.g. process killed mid-write) — refetch
    time.sleep(0.04)
    resp = SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Writer-unique temp + atomic replace (shared with feed_cache): a killed
    # process never leaves a half-written file for the next run to choke on.
    feed_cache_mod.atomic_write_json(path, data)
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


def _mean_round(vals: list[float], digits: int = 1) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), digits) if vals else None


HOME_PLATE_Y_FT = 17 / 12


def _calculate_vaa_from_coords(coords: dict) -> float | None:
    """Vertical approach angle at the front of home plate, in degrees."""
    try:
        vy0 = float(coords["vY0"])
        vz0 = float(coords["vZ0"])
        ay = float(coords["aY"])
        az = float(coords["aZ"])
        y0 = float(coords.get("y0") or 50.0)
        if ay == 0:
            return None
        discriminant = vy0 * vy0 - (2 * ay * (y0 - HOME_PLATE_Y_FT))
        if discriminant < 0:
            return None
        vy_f = -math.sqrt(discriminant)
        t = (vy_f - vy0) / ay
        vz_f = vz0 + (az * t)
        if vy_f == 0:
            return None
        return round(-math.degrees(math.atan(vz_f / vy_f)), 2)
    except (KeyError, TypeError, ValueError):
        return None


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


def _game_logs(
    player_id: int,
    season: int,
    is_pitcher: bool,
    ttl_seconds: int = 86400,
) -> list[dict]:
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
            ttl_seconds=ttl_seconds,
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
            # battersFaced lets a date-windowed leaderboard recompute K% / BB%
            # (strikeouts / walks per batter) off the raw box line. None when
            # the feed omits it; the consumer falls back to per-9 rates.
            bf   = _safe_int(st.get("battersFaced"))
            entry = {
                "date": date,
                "level": level,
                "opponent": opp.get("name") or opp.get("abbreviation") or "?",
                "is_home": bool(split.get("isHome") if isinstance(split.get("isHome"), bool)
                                 else (split.get("game") or {}).get("isHome")),
                "is_pitcher": True,
                "ip": ip, "k": k, "er": er, "r": r, "h": h, "bb": bb, "hr": hra,
                "bf": bf,
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


def _percentile(vals: list[float], pct: float) -> float | None:
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    rank = (len(vals) - 1) * pct
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (rank - lo)


_BIP_WOBA_WEIGHTS = {
    "out": 0.0,
    "single": 0.88,
    "double": 1.25,
    "triple": 1.58,
    "hr": 2.03,
}
_XWOBA_K = 61
_XWOBA_EPS = 0.75
_XWOBA_EV_SCALE = 4.0
_XWOBA_LA_SCALE = 8.0
_XWOBA_KNN_POINTS: list[tuple[float, float, float]] | None = None


def _add_xwoba_knn_point(points: list[tuple[float, float, float]], ev: float, la: float, outcome: str, reps: int = 1) -> None:
    val = _BIP_WOBA_WEIGHTS[outcome]
    for _ in range(reps):
        points.append((float(ev), float(la), val))


def _xwoba_knn_points() -> list[tuple[float, float, float]]:
    """Synthetic EV/LA outcome cloud used by the KNN contact model.

    The shape follows the TJStats article approach: predict total-base
    outcome probabilities from launch speed + launch angle, then convert
    those probabilities to an expected wOBA value. We do not ship MLB's
    historical Statcast training data in this repo, so this deterministic
    cloud encodes broad public baseball priors: soft/low/high contact is
    mostly out value, soft liners can be singles, hard low liners carry
    single/double value, and the 98+ mph / 20-35 degree band carries the
    highest extra-base/HR probability.
    """

    global _XWOBA_KNN_POINTS
    if _XWOBA_KNN_POINTS is not None:
        return _XWOBA_KNN_POINTS
    points: list[tuple[float, float, float]] = []
    for ev in range(50, 116, 5):
        for la in (-50, -35, -25, -15, 35, 45, 55, 65, 75):
            _add_xwoba_knn_point(points, ev, la, "out", reps=5)
    for ev in range(70, 106, 5):
        for la in (-8, -3, 0, 25, 30, 35):
            _add_xwoba_knn_point(points, ev, la, "out", reps=2)
    for ev in (88, 94, 100, 106):
        for la in (-7, -3, 1, 5):
            _add_xwoba_knn_point(points, ev, la, "single")
    for ev in (70, 76, 82, 88, 94):
        for la in (6, 10, 14, 18):
            _add_xwoba_knn_point(points, ev, la, "single", reps=3)
    for ev in (92, 97, 102, 107):
        for la in (14, 18, 22, 26, 30):
            _add_xwoba_knn_point(points, ev, la, "double")
    for ev in (96, 102):
        for la in (16, 22):
            _add_xwoba_knn_point(points, ev, la, "triple")
    for ev in (99, 103, 107, 111, 115):
        for la in (23, 28, 33):
            _add_xwoba_knn_point(points, ev, la, "hr")
    _XWOBA_KNN_POINTS = points
    return points


def _estimate_xwoba(ev: float | None, la: float | None) -> float | None:
    """KNN-style expected wOBA on contact from launch speed + angle."""

    if ev is None or la is None:
        return None
    neighbors: list[tuple[float, float]] = []
    for ref_ev, ref_la, value in _xwoba_knn_points():
        dist = ((ev - ref_ev) / _XWOBA_EV_SCALE) ** 2 + ((la - ref_la) / _XWOBA_LA_SCALE) ** 2
        neighbors.append((dist, value))
    neighbors.sort(key=lambda row: row[0])
    top = neighbors[:_XWOBA_K]
    denom = sum(1.0 / (dist + _XWOBA_EPS) for dist, _value in top)
    if denom <= 0:
        return None
    xwoba = sum(value / (dist + _XWOBA_EPS) for dist, value in top) / denom
    return round(max(0.02, min(1.60, xwoba)), 3)


def _spray_angle(coord_x: float | None, coord_y: float | None) -> float | None:
    if coord_x is None or coord_y is None:
        return None
    # MLB Gameday coordinates use a 250-ish px field canvas. Treat home as
    # bottom-center and center field as top-center, then compute horizontal
    # spray angle where negative is LF-side and positive is RF-side.
    dx = coord_x - 125.0
    dy = 200.0 - coord_y
    if dy <= 0:
        return None
    import math
    return round(math.degrees(math.atan2(dx, dy)), 1)


def _spray_bucket(angle: float | None, batter_side: str | None) -> str | None:
    if angle is None:
        return None
    if angle <= -15:
        field = "lf"
    elif angle >= 15:
        field = "rf"
    else:
        field = "cf"
    side = (batter_side or "").upper()
    if side == "R":
        return "pull" if field == "lf" else ("oppo" if field == "rf" else "center")
    if side == "L":
        return "pull" if field == "rf" else ("oppo" if field == "lf" else "center")
    return {"lf": "left", "cf": "center", "rf": "right"}[field]


def _is_air_ball(la: float | None) -> bool:
    return la is not None and la >= 10.0


def _is_pull_air_type(row: dict, la: float | None) -> bool:
    """Return True for FB/LD/popup batted-ball events.

    Pull-air% is defined as pull-side fly balls + line drives + popups
    divided by total batted-ball events. Prefer the tagged trajectory
    from the feed; launch angle is only a fallback for older rows that
    predate storing the trajectory label.
    """
    raw = (
        row.get("bb_type")
        or row.get("batted_ball_type")
        or row.get("trajectory")
        or row.get("hit_type")
        or ""
    )
    kind = re.sub(r"[^a-z]", "", str(raw).lower())
    if kind in {"flyball", "linedrive", "popup", "popupbunt"}:
        return True
    if kind in {"groundball", "groundout", "groundedintodoubleplay"}:
        return False
    return _is_air_ball(la)


def _xwobacon_profile_adjustment(
    xwobacon: float | None,
    avg_ev: float | None,
    p90_ev: float | None,
    hard_hit_pct: float | None,
    barrel_pct: float | None,
    _pull_air_pct: float | None,
    avg_la: float | None,
    bbe: int,
) -> float:
    if xwobacon is None or bbe < 25:
        return 0.0
    lift = 0.0
    # MLB's public xwOBA is deliberately context-neutral: EV/LA drive the
    # contact estimate, while spray/park/weather are excluded. Keep this
    # aggregate correction tied to EV/LA-derived contact quality only.
    if (
        barrel_pct is not None and barrel_pct >= 10.0
        and hard_hit_pct is not None and hard_hit_pct >= 45.0
    ):
        lift += max(0.0, barrel_pct - 8.0) * 0.005
        if p90_ev is not None:
            lift += max(0.0, p90_ev - 104.0) * 0.0025
        if avg_la is not None and avg_la >= 18.0:
            lift += min(0.018, (avg_la - 18.0) * 0.006)
    # Hard-contact grounder/liner profiles are not barrel monsters, but a
    # .340-ish contact estimate is too light when the player is sustaining
    # 50%+ hard-hit contact with a 90+ mph average EV.
    if (
        xwobacon < 0.365
        and hard_hit_pct is not None and hard_hit_pct >= 50.0
        and avg_ev is not None and avg_ev >= 90.0
        and avg_la is not None and avg_la <= 8.0
    ):
        lift += max(0.0, hard_hit_pct - 45.0) * 0.003
        lift += max(0.0, avg_ev - 90.0) * 0.006
    # The EV/LA surface can over-credit soft line-drive batches because
    # those batted balls often become singles in small samples. If the
    # aggregate profile has no real hard-contact support, pull the contact
    # estimate back down instead of letting batting-average contact masquerade
    # as power contact.
    if (
        avg_ev is not None and avg_ev < 86.0
        and p90_ev is not None and p90_ev < 100.0
        and hard_hit_pct is not None and hard_hit_pct < 30.0
        and (barrel_pct or 0.0) <= 2.0
        and xwobacon > 0.330
    ):
        soft_cap = 0.325 - max(0.0, 86.0 - avg_ev) * 0.008
        lift = min(lift, soft_cap - xwobacon)
    return round(max(-0.45, min(0.08, lift)), 3)


def _finalize_contact(rows: list[dict], is_pitcher: bool) -> dict:
    evs = [_safe_float(r.get("launch_speed")) for r in rows]
    las = [_safe_float(r.get("launch_angle")) for r in rows]
    paired = [(ev, la) for ev, la in zip(evs, las) if ev is not None]
    bbe = len(paired)
    if not bbe:
        return {}
    hard = sum(1 for ev, _la in paired if ev >= 95)
    barrels = sum(1 for ev, la in paired if _is_barrel(ev, la))
    avg_ev = _mean([ev for ev, _la in paired])
    p90_ev = round(_percentile([ev for ev, _la in paired], 0.90), 1)
    avg_la = _mean([la for _ev, la in paired if la is not None])
    hard_hit_pct = round(hard / bbe * 100, 1)
    barrel_pct = round(barrels / bbe * 100, 1)
    xwobas = [_estimate_xwoba(ev, la) for ev, la in paired]
    xwobas = [v for v in xwobas if v is not None]
    xwoba_base = round(sum(xwobas) / len(xwobas), 3) if xwobas else None

    spray_counts = {"pull": 0, "center": 0, "oppo": 0}
    air_pull = air_total = 0
    locs: list[dict] = []
    dated_for_roll: list[dict] = []
    for r in rows:
        ev = _safe_float(r.get("launch_speed"))
        la = _safe_float(r.get("launch_angle"))
        if ev is None:
            continue
        x = _safe_float(r.get("coord_x"))
        y = _safe_float(r.get("coord_y"))
        angle = _spray_angle(x, y)
        bucket = _spray_bucket(angle, r.get("batter_side"))
        if bucket not in spray_counts and r.get("spray") in spray_counts:
            bucket = r.get("spray")
        if bucket in spray_counts:
            spray_counts[bucket] += 1
        if _is_pull_air_type(r, la):
            air_total += 1
            if bucket == "pull":
                air_pull += 1
        xwoba = _estimate_xwoba(ev, la)
        if xwoba is not None:
            dated_for_roll.append({"date": r.get("date"), "xwoba": xwoba})
        if x is not None and y is not None:
            locs.append({
                "game_pk": r.get("game_pk"),
                "date": r.get("date"),
                "x": round(x, 1),
                "y": round(y, 1),
                "launch_speed": ev,
                "launch_angle": la,
                "distance_ft": _safe_float(r.get("total_distance")),
                "xwoba_est": xwoba,
                "hit_type": r.get("hit_type") or r.get("event") or "batted_ball",
                "bb_type": r.get("bb_type") or r.get("batted_ball_type") or r.get("trajectory"),
                "spray": bucket,
                "spray_angle": angle,
            })
    locs = locs[-450:]

    rolling: list[dict] = []
    dated_for_roll = [r for r in dated_for_roll if r.get("date")]
    dated_for_roll.sort(key=lambda r: r["date"])
    win = 25
    for i in range(len(dated_for_roll)):
        chunk = dated_for_roll[max(0, i - win + 1):i + 1]
        if len(chunk) < 5:
            continue
        rolling.append({
            "date": dated_for_roll[i]["date"],
            "bbe": len(chunk),
            "xwoba": round(sum(r["xwoba"] for r in chunk) / len(chunk), 3),
        })

    out = {
        "batted_balls": bbe,
        "avg_ev": avg_ev,
        "max_ev": round(max(ev for ev, _la in paired), 1),
        "p90_ev": p90_ev,
        "avg_la": avg_la,
        "hard_hit_pct": hard_hit_pct,
        "barrel_pct": barrel_pct,
        "xwoba_est": xwoba_base,
        "xwobacon_est": xwoba_base,
        "spray": {
            "pull_pct": round(spray_counts["pull"] / bbe * 100, 1) if bbe else None,
            "center_pct": round(spray_counts["center"] / bbe * 100, 1) if bbe else None,
            "oppo_pct": round(spray_counts["oppo"] / bbe * 100, 1) if bbe else None,
            "pull_air_pct": round(air_pull / bbe * 100, 1) if bbe else None,
            "pull_air_bbe": air_pull,
            "air_bbe": air_total,
        },
        "rolling_xwoba": rolling[-60:],
        "hit_locations": locs,
        "direction": "allowed" if is_pitcher else "hit",
    }
    adj = _xwobacon_profile_adjustment(
        xwoba_base,
        avg_ev,
        p90_ev,
        hard_hit_pct,
        barrel_pct,
        out["spray"]["pull_air_pct"],
        avg_la,
        bbe,
    )
    if adj and xwoba_base is not None:
        out["xwobacon_raw"] = xwoba_base
        out["xwobacon_adjustment"] = adj
        out["xwoba_est"] = round(max(0.02, min(1.60, xwoba_base + adj)), 3)
        out["xwobacon_est"] = out["xwoba_est"]
    return out


def _finalize_pitch(points: list[dict], outings: list[dict]) -> tuple[dict, dict]:
    tracked = [
        p for p in points
        if p.get("hb") is not None and p.get("ivb") is not None and p.get("pitch_type")
    ]
    if not tracked:
        return {}, {}
    try:
        from mlb_stuff_plus import score_pitch_points
        tracked = score_pitch_points(tracked)
    except Exception:
        tracked = [dict(p) for p in tracked]
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
            "avg_stuff_plus": _mean_round([r.get("tj_stuff_plus") for r in rows], 0),
            "avg_extension": _mean([r.get("extension") for r in rows]),
            "avg_release_height": _mean([r.get("release_height") for r in rows]),
            "avg_plate_height": _mean([r.get("plate_height") for r in rows]),
            "avg_vaa": _mean_round([r.get("vaa") for r in rows], 2),
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
    logs: list[dict] | None = None,
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
    logs = logs if logs is not None else _game_logs(int(mlbam_id), season, is_pitcher=is_pitcher)
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
            data = feed_cache_mod.get_game_feed(game_pk, game_date=split.get("date"))
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
                coords = pitch_data.get("coordinates") or {}
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
                        "pitcher_hand": (matchup.get("pitchHand") or {}).get("code"),
                        "velo": _safe_float(pitch_data.get("startSpeed")),
                        "hb": _safe_float(breaks.get("breakHorizontal")),
                        "ivb": _safe_float(breaks.get("breakVerticalInduced")),
                        "spin": _safe_float(breaks.get("spinRate")),
                        "extension": _safe_float(pitch_data.get("extension")),
                        "ax": _safe_float(coords.get("aX")),
                        "az": _safe_float(coords.get("aZ")),
                        "x0": _safe_float(coords.get("x0")),
                        "release_height": _safe_float(coords.get("z0")),
                        "plate_height": _safe_float(coords.get("pZ")),
                        "vaa": _calculate_vaa_from_coords(coords),
                    }
                    if point["hb"] is not None and point["ivb"] is not None:
                        tracked_pitch_count += 1
                        pitch_points.append(point)
                        level_bucket["pitch_points"].append(point)
                hit_data = event.get("hitData") or {}
                launch_speed = _safe_float(hit_data.get("launchSpeed"))
                launch_angle = _safe_float(hit_data.get("launchAngle"))
                if launch_speed is not None:
                    coords = hit_data.get("coordinates") or {}
                    coord_x = _safe_float(coords.get("coordX"))
                    coord_y = _safe_float(coords.get("coordY"))
                    batted_ball_type = (hit_data.get("trajectory") or "").title().replace("_", "")
                    hit_type = (
                        details.get("eventType")
                        or details.get("event")
                        or (play.get("result") or {}).get("eventType")
                        or (play.get("result") or {}).get("event")
                    )
                    batter_side = (matchup.get("batSide") or {}).get("code")
                    contact_count += 1
                    contact_row = {
                        "game_pk": game_pk,
                        "date": game_date,
                        "launch_speed": launch_speed,
                        "launch_angle": launch_angle,
                        "total_distance": _safe_float(hit_data.get("totalDistance")),
                        "coord_x": coord_x,
                        "coord_y": coord_y,
                        "hit_type": hit_type,
                        "bb_type": batted_ball_type,
                        "batter_side": batter_side,
                    }
                    contact_rows.append(contact_row)
                    level_bucket["contact_rows"].append(contact_row)
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
    logs_by_key: dict[str, list[dict]] | None = None,
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
    fetched_logs_by_key: dict[str, list[dict]] = {}
    _p1_start = _time.monotonic()
    if logs_by_key is not None:
        fetched_logs_by_key = {key: list(logs_by_key.get(key) or []) for key, *_ in targets}
        _log.info("statcast pass 1/3: using preloaded game logs for %d players",
                  len(targets))
    else:
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
                fetched_logs_by_key[key] = logs
                _p1_done += 1
                if _p1_done % 250 == 0 or _p1_done == len(targets):
                    _log.info("statcast pass 1/3: %d/%d game-log fetches done (%.0fs)",
                              _p1_done, len(targets), _time.monotonic() - _p1_start)

    # ---- PASS 2: unique game-feed fetch (parallel, cached) ----
    # Feeds go through the shared feed_cache (one on-disk dir keyed by
    # game_pk, deduped across statcast/zone/etc). game_date_by_pk lets the
    # cache give completed games a permanent TTL, so a monthly run only
    # re-fetches the trailing few days of games.
    game_pks: set[int] = set()
    game_date_by_pk: dict[int, str] = {}
    for logs in fetched_logs_by_key.values():
        for split in logs:
            gpk = int((split.get("game") or {}).get("gamePk") or 0)
            if gpk:
                game_pks.add(gpk)
                gd = split.get("date")
                if gd and gpk not in game_date_by_pk:
                    game_date_by_pk[gpk] = gd
    if game_pks:
        _p2_start = _time.monotonic()
        _log.info("statcast pass 2/3: fetching %d unique game feeds (deduped from %d player×game lookups)",
                  len(game_pks), sum(len(v) for v in fetched_logs_by_key.values()))
        def _fetch_feed(gpk):
            # v20 — Warm the on-disk feed cache only; do NOT retain the parsed
            # payload here. A full season's worth of feeds (thousands of full
            # play-by-play JSON blobs) held in one in-memory dict was enough to
            # OOM a modest box. Pass 3 re-reads each feed through
            # feed_cache_mod.get_game_feed(), which is a fast local disk-cache
            # hit by then (this pass just wrote it), so the wall-time win from
            # pass 2's parallel dedup is preserved without holding the whole
            # season resident in RAM at once.
            try:
                feed_cache_mod.get_game_feed(gpk, game_date=game_date_by_pk.get(gpk))
            except Exception as e:
                _log.debug("statcast feed failed for game %s: %s", gpk, e)
        _p2_done = 0
        # Shared cache retries 429 with backoff, so a higher cap is safe.
        feed_workers = max(1, min(max_workers, 20))
        with concurrent.futures.ThreadPoolExecutor(max_workers=feed_workers) as ex:
            for _ in ex.map(_fetch_feed, sorted(game_pks)):
                _p2_done += 1
                if _p2_done % 500 == 0 or _p2_done == len(game_pks):
                    elapsed = _time.monotonic() - _p2_start
                    rate = _p2_done / max(elapsed, 0.001)
                    eta = (len(game_pks) - _p2_done) / rate if rate > 0 else 0
                    _log.info("statcast pass 2/3: %d/%d feeds (%.0fs elapsed · ~%.0fs left)",
                              _p2_done, len(game_pks), elapsed, eta)

    # ---- PASS 3: per-player processing, reading feeds from the on-disk cache ----
    _p3_start = _time.monotonic()
    _log.info("statcast pass 3/3: processing %d players against cached feeds", len(targets))
    _p3_done = 0
    # v22 — Processes, not threads. _finalize_pitch/_finalize_contact do real
    # CPU work (JSON parse + per-pitch statistical aggregation), and CPython
    # threads don't get true parallelism for CPU-bound code (the GIL means
    # only one thread executes Python bytecode at a time regardless of
    # max_workers). A ProcessPoolExecutor gives each worker its own
    # interpreter/GIL, so this actually uses the box's cores. Capped at the
    # real core count (not max_workers, which was tuned high for pass 1/2's
    # I/O concurrency) since extra processes past that just add overhead for
    # CPU-bound work. fetch_statcast_metrics_for_player's args and its
    # StatcastMetricRow return value are plain picklable types.
    # SPAWN, not fork (v22 correction — an earlier version of this used
    # fork and OOM'd on a full run): by the time we reach this step, the
    # calling process (run_monthly.py's main()) has already accumulated a
    # large heap — the full player timeseries, statlines, ID maps, etc.
    # from every earlier step. fork() gives each worker a copy-on-write view
    # of that WHOLE heap, and CPython's per-object refcounting means merely
    # touching an inherited object (even incidentally, e.g. during a GC
    # sweep) dirties its page and forces a real copy — across several
    # workers that can multiply memory well past what the parent alone was
    # using, which is exactly what caused a second OOM here. spawn starts
    # each worker as a fresh interpreter that only receives the small,
    # explicitly-pickled task arguments, never the parent's heap, at the
    # cost of a negligible one-time interpreter-boot delay per worker.
    # Requires the importing script's entry point to be guarded by
    # `if __name__ == "__main__":` so a spawned child doesn't re-run it on
    # import — confirmed true for run_monthly.py (see bottom of that file).
    _p3_workers = min(max_workers, os.cpu_count() or 4)
    _p3_ctx = multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=_p3_workers, mp_context=_p3_ctx) as ex:
        future_to_key = {
            ex.submit(
                fetch_statcast_metrics_for_player,
                key, name, mlbam, season, level, is_pitcher,
                None,  # v20 — no in-memory feed_cache; falls back to the disk
                       # cache pass 2 just warmed (see _fetch_feed above).
                fetched_logs_by_key.get(key),
            ): key
            for key, name, mlbam, level, is_pitcher in targets
        }
        _p3_errors = 0
        for fut in concurrent.futures.as_completed(future_to_key):
            key = future_to_key[fut]
            try:
                row = fut.result()
            except Exception as _exc:
                # AUDIT 2026-07-18 (A8): under the spawn ProcessPoolExecutor a single
                # dead worker marks the pool broken and raises BrokenProcessPool on
                # EVERY pending future; swallowing them silently staled hundreds of
                # rows inside a run that still logged success. Log so a pool break or
                # a per-player fetch failure is visible at production log level.
                row = None
                _p3_errors += 1
                if _p3_errors <= 5 or _p3_errors % 200 == 0:
                    _log.warning("statcast pass 3/3: worker failed for %s (%d errors so far): %s",
                                 key, _p3_errors, _exc)
            if row:
                out[key] = row
            _p3_done += 1
            if _p3_done % 500 == 0 or _p3_done == len(targets):
                _log.info("statcast pass 3/3: %d/%d processed (%d with data, %.0fs elapsed)",
                          _p3_done, len(targets), len(out), _time.monotonic() - _p3_start)
        if _p3_errors:
            _log.warning("statcast pass 3/3: %d/%d workers failed (rows left stale this run)",
                         _p3_errors, len(targets))
    return out
