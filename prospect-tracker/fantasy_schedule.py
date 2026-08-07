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
TEAMS_API = "https://statsapi.mlb.com/api/v1/teams"
CACHE_DIR = Path(__file__).parent / ".cache" / "fantasy_schedule"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Probables update intraday; a short TTL keeps a nightly build fresh while making
# repeat calls within one run free. Always < 24h so any nightly cadence re-pulls.
SCHEDULE_TTL = 3 * 3600  # 3h
# Lineups move on a much shorter clock than probables: they post 2-4 hours before
# first pitch and change again when someone is scratched in batting practice. A
# 3h cache would routinely hand back a window in which nothing had posted yet.
LINEUP_TTL = 12 * 60     # 12 min
# The club-to-home-park map is static inside a season (a club does not move
# stadiums mid-year), so this one is cached for a day and the fetch is a
# once-a-build cost at worst.
TEAMS_TTL = 24 * 3600


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


def _cached_get(path: Path, url: str, params: dict, ttl: int, use_cache: bool = True) -> dict:
    """One hardened StatsAPI GET behind a TTL'd disk cache. Raises on a real
    failure; the callers decide what a failure degrades to."""
    if use_cache and path.exists() and time.time() - path.stat().st_mtime <= ttl:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # corrupt cache -> refetch
    time.sleep(0.04)
    resp = feed_cache.SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)  # atomic
    return data


def _cached_schedule(start_date: str, end_date: str, game_type: str, use_cache: bool) -> dict:
    """Raw `/schedule` JSON for the window, disk-cached (SCHEDULE_TTL) by span.

    The hydrate list is deliberately WITHOUT `lineups`. Lineups have a TTL an
    order of magnitude shorter than probables and every caller of this function
    wants a multi-day forward window, which is a window in which no lineup has
    posted; hydrating them here would either make the streamer board's cache
    churn every twelve minutes or serve lineups from a three-hour-old copy.
    `fetch_lineups` is the separate, single-day, short-TTL call."""
    return _cached_get(
        CACHE_DIR / f"{start_date}_{end_date}_{game_type}.json",
        SCHEDULE_API,
        {"sportId": 1, "startDate": start_date, "endDate": end_date,
         "gameType": game_type, "hydrate": "probablePitcher,linescore"},
        SCHEDULE_TTL, use_cache)


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


def fetch_lineups(day: str, *, game_type: str = "R", use_cache: bool = True) -> dict:
    """{game_pk: {"home": [mlbam, ...], "away": [...]}} for one day, batting order.

    A SIDE IS THE UNIT, NOT A GAME. Measured 2026-08-07: game 823428 had nine
    home players posted and zero away, which is the normal state for the hour
    or so between the two clubs filing their cards. An empty list therefore
    means "this club has not posted", never "this club has nobody", and there
    is deliberately no game-level `posted` flag for a caller to misread as
    covering both sides.

    CONFIRMED BATTING ORDER, AND NOTHING ELSE. The `lineups` hydration on
    /schedule returns `homePlayers`/`awayPlayers` IN BATTING ORDER once a club
    posts its card, and returns nothing at all before that. Both halves of that
    sentence are the feature: a posted lineup is a fact about tonight, and an
    unposted one has to stay absent rather than be filled in with whoever
    started yesterday. Verified 2026-08-07 against the boxscore `battingOrder`
    field for game 824804: the array order and the batting order agree exactly,
    which is the only reason a bare index is safe to publish as a lineup spot.

    Coverage is LOW by construction and that is not a bug. Measured on
    2026-08-07 at 14:40 ET: 1 of 15 games had a lineup posted for that night, 0
    of 15 for the next. A nightly build will usually see none, an afternoon
    rebuild will see some, and callers must treat the empty case as normal.

    Best-effort: any failure logs and returns {}, which reads downstream as "no
    lineup posted" and is exactly the right degradation."""
    try:
        data = _cached_get(CACHE_DIR / f"lineups_{day}_{game_type}.json", SCHEDULE_API,
                           {"sportId": 1, "date": day, "gameType": game_type,
                            "hydrate": "lineups"},
                           LINEUP_TTL, use_cache)
    except Exception:
        log.exception("fantasy_schedule: lineup fetch failed for %s - returning {}", day)
        return {}
    out: dict = {}
    for d in data.get("dates", []):
        for g in d.get("games", []):
            pk = g.get("gamePk")
            lu = g.get("lineups") or {}
            if not pk:
                continue
            side = {}
            for key, who in (("homePlayers", "home"), ("awayPlayers", "away")):
                ids = [p.get("id") for p in (lu.get(key) or []) if (p or {}).get("id")]
                if ids:
                    side[who] = ids
            if side:
                out[int(pk)] = {"home": side.get("home") or [], "away": side.get("away") or []}
    return out


def fetch_home_venues(season: int, *, use_cache: bool = True) -> dict:
    """{venue_id: org} for the 30 clubs' own parks in `season`.

    THE REASON THIS EXISTS is that park factors are published per CLUB and a
    game is played at a VENUE, and those are the same thing until they are not.
    An org-keyed lookup silently prices a London Series or a Field of Dreams
    game at the nominal home club's park factor, which is the one game a year
    where the park term is most wrong. Resolving the venue id against this map
    and refusing the leg when it misses turns that into an absence a reader can
    see.

    Best-effort: any failure returns {}, and a caller with no map must fall
    back to NOT applying a park factor rather than to applying one it could not
    place."""
    try:
        data = _cached_get(CACHE_DIR / f"teams_{season}.json", TEAMS_API,
                           {"sportId": 1, "season": int(season)}, TEAMS_TTL, use_cache)
    except Exception:
        log.exception("fantasy_schedule: teams fetch failed for %s - returning {}", season)
        return {}
    out: dict = {}
    for t in data.get("teams") or []:
        vid = ((t or {}).get("venue") or {}).get("id")
        org = _org((t or {}).get("name"))
        if vid is not None and org:
            out[int(vid)] = org
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


def team_schedule(games: list[dict]) -> dict:
    """{team_org: [{date, opp_org, opp_team_id, is_home, venue}, ...]} from ALL
    games in the window — announced probables NOT required (that is the point:
    this is the raw slate a projected start can land on). Date-sorted, with
    doubleheader dates deduped to ONE entry per team per date (a projected
    second start needs the day, not the game count)."""
    by: dict = {}
    for g in games:
        d = g.get("date")
        if not d:
            continue
        for me, opp, is_home in (("home", "away", True), ("away", "home", False)):
            org = (g.get(me) or {}).get("org")
            if not org:
                continue
            by.setdefault(org, {}).setdefault(d, {
                "date": d,
                "opp_org": (g.get(opp) or {}).get("org"),
                "opp_team_id": (g.get(opp) or {}).get("team_id"),
                "is_home": is_home,
                "venue": (g.get("venue") or {}).get("name"),
            })
    return {org: [days[d] for d in sorted(days)] for org, days in by.items()}


def projected_two_start(starts: list[dict], team_sched: dict, window_end: str) -> dict:
    """{mlbam: [leg, leg]} two-start view that PROJECTS the unannounced second leg.

    Probables only post ~4-5 days out, so a 7-day window essentially never holds
    two ANNOUNCED starts for anyone and the announced-only two_start_pitchers()
    is empty by construction. For a pitcher with a single announced start on
    date D, the team's next game on D+4..D+6 (a normal rest cycle) inside the
    window becomes the projected second start, flagged ``projected: True`` and
    carrying that game's date/opponent/venue. Pitchers who DO have >=2 announced
    starts keep their announced legs untouched (no projection is added)."""
    out: dict = {}
    for mid, lst in starts_by_pitcher(starts).items():
        if len(lst) >= 2:
            out[mid] = lst          # already an announced two-start: leave as-is
            continue
        st = lst[0]
        team = st.get("team_org")
        try:
            d0 = date.fromisoformat(st.get("date") or "")
        except ValueError:
            continue
        if not team:
            continue
        lo, hi = d0 + timedelta(days=4), d0 + timedelta(days=6)
        for g in (team_sched.get(team) or []):
            gd = g.get("date")
            if not gd or gd > window_end:
                continue
            try:
                gdate = date.fromisoformat(gd)
            except ValueError:
                continue
            if lo <= gdate <= hi:
                out[mid] = [st, {
                    "mlbam": st.get("mlbam"),
                    "name": st.get("name"),
                    "date": gd,
                    "is_home": g.get("is_home"),
                    "team_org": team,
                    "opp_org": g.get("opp_org"),
                    "opp_team_id": g.get("opp_team_id"),
                    "venue": g.get("venue"),
                    "projected": True,
                }]
                break               # first slate day in the rest window wins
    return out


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
