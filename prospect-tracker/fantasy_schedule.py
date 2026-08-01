# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fantasy_schedule.py — forward-looking MLB probable-pitcher / schedule feed.

The rest of the pipeline only ever pulls FINAL games (leverage, statcast, WP).
The Fantasy module's Daily SP Streamers and Two-Start SP sections need the
OPPOSITE: who is scheduled to pitch, and against whom, over the next few days.

One hardened call to the StatsAPI `/schedule` endpoint hydrated with
`probablePitcher` gives, per game: date, venue, both teams, and each team's
announced probable starter (mlbam id + name). We reuse `feed_cache.SESSION`
(429-retrying) and canonicalize team names to the site's 3-letter org codes via
`trades.canonical_org`, so downstream joins line up with the skill leaderboards
(`starter_leaderboards.json`, the `teams` block of `hitter_/bullpen_leaderboards`)
and Savant park factors.

Probables move through the day (lineups get announced), so the on-disk cache uses
a SHORT ttl — a nightly build always pulls fresh, but repeated calls inside one
run are free. Best-effort: a network hiccup returns [] and the caller degrades
(the section renders "probables not yet posted"), never aborts the build.

CLI:
    python fantasy_schedule.py            # today..+2 coverage summary
    python fantasy_schedule.py --days 7   # a full scoring week
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import feed_cache  # hardened session (retries 429) + TTL helpers

log = logging.getLogger("fantasy_schedule")

SCHEDULE_API = "https://statsapi.mlb.com/api/v1/schedule"
CACHE_DIR = Path(__file__).parent / ".cache" / "fantasy_schedule"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Probables update intraday; a short TTL keeps a nightly build fresh while making
# repeat calls within one run free. Always < 24h so any nightly cadence re-pulls.
SCHEDULE_TTL = 3 * 3600  # 3h


def _org(name: str | None) -> str | None:
    """MLB team name -> the site's 3-letter org code (lazy import: trades.py is heavy)."""
    if not name:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name)
    except Exception:
        return None


def date_window(n_days: int = 3, from_date: date | None = None) -> tuple[str, str]:
    """(start, end) ISO strings for `from_date`..`from_date + n_days-1` (default today)."""
    start = from_date or date.today()
    end = start + timedelta(days=max(0, n_days - 1))
    return start.isoformat(), end.isoformat()


def _cached_schedule(start_date: str, end_date: str, game_type: str, use_cache: bool) -> dict:
    """Raw `/schedule` JSON for the window, disk-cached (SCHEDULE_TTL) by span."""
    path = CACHE_DIR / f"{start_date}_{end_date}_{game_type}.json"
    if use_cache and path.exists() and time.time() - path.stat().st_mtime <= SCHEDULE_TTL:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # corrupt cache -> refetch
    time.sleep(0.04)
    resp = feed_cache.SESSION.get(
        SCHEDULE_API,
        params={
            "sportId": 1,
            "startDate": start_date,
            "endDate": end_date,
            "gameType": game_type,
            "hydrate": "probablePitcher,linescore",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)  # atomic
    return data


def _side(side_obj: dict) -> dict:
    """Normalize one game side (home/away) -> {team_id, team, org, probable, record}."""
    team = side_obj.get("team") or {}
    pp = side_obj.get("probablePitcher") or {}
    rec = side_obj.get("leagueRecord") or {}
    name = team.get("name")
    return {
        "team_id": team.get("id"),
        "team": name,
        "org": _org(name),
        "probable": ({"mlbam": pp.get("id"), "name": pp.get("fullName")} if pp.get("id") else None),
        "record": {"w": rec.get("wins"), "l": rec.get("losses")} if rec else None,
    }


def fetch_probables(start_date: str, end_date: str, *, game_type: str = "R",
                    use_cache: bool = True) -> list[dict]:
    """Scheduled games in [start_date, end_date] with probable pitchers.

    Returns one dict per game: game_pk, date, datetime (UTC ISO), status, venue
    {id,name}, and home/away sides (each: team_id, team, org, probable{mlbam,name}
    or None, record). Doubleheaders yield two games. Best-effort: any failure logs
    and returns []."""
    try:
        data = _cached_schedule(start_date, end_date, game_type, use_cache)
    except Exception:
        log.exception("fantasy_schedule: /schedule fetch failed %s..%s — returning []",
                      start_date, end_date)
        return []
    out: list[dict] = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            pk = g.get("gamePk")
            if not pk:
                continue
            teams = g.get("teams") or {}
            venue = g.get("venue") or {}
            out.append({
                "game_pk": int(pk),
                "date": g.get("officialDate") or d.get("date"),
                "datetime": g.get("gameDate"),
                "status": ((g.get("status") or {}).get("abstractGameState")),
                "double_header": g.get("doubleHeader") not in (None, "N"),
                "venue": {"id": venue.get("id"), "name": venue.get("name")},
                "home": _side(teams.get("home") or {}),
                "away": _side(teams.get("away") or {}),
            })
    return out


def starts_index(games: list[dict]) -> list[dict]:
    """Flatten games -> one row per announced probable START (skips unannounced).

    Each start row is the pitcher's-eye view a streamer ranking needs: who they
    are, when, at home/away, the opponent org (for Offense+/Bullpen+ join) and the
    venue (for park factors)."""
    rows: list[dict] = []
    for g in games:
        for me, opp, is_home in (("home", "away", True), ("away", "home", False)):
            side = g[me]
            pp = side.get("probable")
            if not pp or not pp.get("mlbam"):
                continue
            rows.append({
                "mlbam": pp["mlbam"],
                "name": pp.get("name"),
                "game_pk": g["game_pk"],
                "date": g["date"],
                "datetime": g["datetime"],
                "is_home": is_home,
                "team_org": side.get("org"),
                "opp_org": g[opp].get("org"),
                "opp_team_id": g[opp].get("team_id"),
                "opp_team": g[opp].get("team"),
                "venue_id": g["venue"].get("id"),
                "venue": g["venue"].get("name"),
                "status": g["status"],
            })
    return rows


def starts_by_pitcher(starts: list[dict]) -> dict:
    """{mlbam: [start, ...]} in date order — the per-pitcher schedule view."""
    by: dict = {}
    for s in starts:
        by.setdefault(s["mlbam"], []).append(s)
    for lst in by.values():
        lst.sort(key=lambda s: (s.get("date") or "", s.get("datetime") or ""))
    return by


def two_start_pitchers(starts: list[dict]) -> dict:
    """{mlbam: [start, start, ...]} for pitchers with >=2 starts in the window
    (the Two-Start SP section — sort key: number of starts, then quality upstream)."""
    return {mid: lst for mid, lst in starts_by_pitcher(starts).items() if len(lst) >= 2}


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MLB probable-pitcher / schedule poller (forward-looking).")
    ap.add_argument("--days", type=int, default=3, help="window length from today (default 3)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    s, e = date_window(args.days)
    games = fetch_probables(s, e, use_cache=not args.no_cache)
    starts = starts_index(games)
    two = two_start_pitchers(starts)
    announced = sum(1 for g in games for k in ("home", "away") if g[k].get("probable"))
    print(f"\n=== PROBABLES {s}..{e} ({args.days}d) ===")
    print(f"  games: {len(games)}   announced probables: {announced}/{2*len(games)}   two-start SP: {len(two)}")
    from collections import Counter
    by_day = Counter(g["date"] for g in games)
    for day in sorted(by_day):
        day_games = [g for g in games if g["date"] == day]
        ann = sum(1 for g in day_games for k in ("home", "away") if g[k].get("probable"))
        print(f"  {day}: {len(day_games)} games, {ann} probables announced")
    # Show a couple of sample matchups
    for g in games[:4]:
        hp = (g["home"]["probable"] or {}).get("name", "TBD")
        ap_ = (g["away"]["probable"] or {}).get("name", "TBD")
        print(f"    {g['date']} {g['away']['org']}({ap_}) @ {g['home']['org']}({hp}) — {g['venue']['name']}")
