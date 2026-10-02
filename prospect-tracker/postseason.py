"""Postseason series results from MLB StatsAPI, 2000 to the live season.

The one postseason results source for the site (F-SCORE plan FS-1, Part 8
8.E, the postseason row). One public call per season,
/api/v1/schedule/postseason/series?sportId=1&season=Y (no key), returns every
series with its games; this module caches each response, parses it into
series rows and per-club rounds, and asserts the bracket's identities before
anything reads a completed season.

STORAGE. fetch() writes .cache/statsapi_postseason_{Y}.json as
{season, fetched_at, complete, body}. A season whose World Series has a winner
is FROZEN: it is never fetched again without force=True. The live season is
fetched at most once a day, never before its regular season ends (the
regularSeasonEndDate of the cached /seasons payload; no date on disk means no
fetch), and, once a response is cached, not again until its first postseason
game has been played. Completed seasons 2000 to 2025 also live in a TRACKED,
UNPUBLISHED copy under data/_labs/postseason/ (trimmed to the fields load()
reads), so a box that rebuilds from its own checkout has them without a
fetch; load() reads that copy first and the cache second. Not through
scrapers._fetch: its 30-day prior-year TTL would refetch frozen seasons.

RULES (orchestrator ruling X11).
- A game is final only when status.codedGameState is F or O, the scores_core
  rule. abstractGameState is never read: seven postponed probe games carry
  abstractGameState Final with codedGameState D. Postponed and suspended
  games count nothing until a final record exists; a gamePk counts once.
- A series is won at gamesInSeries // 2 + 1 final wins.
- A team id that is not one of the 30 clubs is a bracket placeholder and is
  dropped (5528 HOU/CWS, 5513 AL Higher Seed, 2710 Higher Seed League
  Champion in the live 2026 bracket). Names are never read, so a placeholder
  cannot resolve to a club through its name.
- bye is True only for a club in a division series with no first-round
  series, in a season whose schedule holds at least one first-round (gameType
  F) series: 2000 to 2011 and 2020 carry no byes.
- round_reached: 0 missed, 1 first round, 2 division series or bye, 3 LCS,
  4 World Series, 5 champion. In 2000 to 2011 the division series is the
  first round, so its clubs reach 2 and count at round 1 or more.
- in_progress (live season only): the club is in the bracket and has lost no
  completed series.

IDENTITIES, asserted on every complete season before load() returns: one
champion; two pennant winners; the round-1 participants, read from the
postseason schedule's own series and games and never from the standings'
clinched flags (2012 has 10 round-1 clubs and 8 clinched rows), number the
format's berths; each club in at most one series per round; no placeholder;
and the round counts of the format (clubs at round 1 or more through round 5).
A disagreement with the standings' clinched count is a feed note
(feed_notes()), logged and never raised.

division_champions(season) loads the standings cache and returns
franchise_export.division_champions: one rule, one implementation.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"
TRACKED = ROOT / "data" / "_labs" / "postseason"
URL = "https://statsapi.mlb.com/api/v1/schedule/postseason/series?sportId=1&season={season}"
FIRST_SEASON = 2000
TIMEOUT_S = 30

ROUND_OF = {"F": 1, "D": 2, "L": 3, "W": 4}
CHAMPION = 5
FINAL_CODES = ("F", "O")
#: Series the endpoint lists that are not postseason rounds: the regular-season
#: tiebreaker games (gameType R, seriesDescription "Regular Season"; 2007 COL,
#: 2008 CHW, 2009 MIN, 2013 TBR and 2018 CHC and LAD hosted one). The standings
#: already count them; they take no part in a round.
SKIPPED_TYPES = ("R",)


class PostseasonError(Exception):
    """A response or a cached file that may not be read as a bracket."""


class PostseasonIdentityError(PostseasonError):
    """A complete season whose bracket breaks one of the identities."""


def format_for(season: int) -> dict:
    """The postseason format of a season: berths and the round counts
    (clubs at round 1 or more, 2 or more, ... 5) it must show when complete."""
    s = int(season)
    if s < FIRST_SEASON:
        raise PostseasonError(f"no postseason format registered before {FIRST_SEASON}: {s}")
    if s <= 2011:
        return {"berths": 8, "round_counts": (8, 8, 4, 2, 1), "first_round": False}
    if s == 2020:
        return {"berths": 16, "round_counts": (16, 8, 4, 2, 1), "first_round": True}
    if s <= 2021:
        return {"berths": 10, "round_counts": (10, 8, 4, 2, 1), "first_round": True}
    return {"berths": 12, "round_counts": (12, 8, 4, 2, 1), "first_round": True}


def _clubs_by_id() -> dict:
    """{StatsAPI team id: club code} for the 30 clubs, by id only."""
    from trades import _org_by_id
    return dict(_org_by_id())


def cache_path(season: int, cache_dir: Path | None = None) -> Path:
    return Path(cache_dir or CACHE) / f"statsapi_postseason_{int(season)}.json"


def rejected_path(season: int, cache_dir: Path | None = None) -> Path:
    """Where fetch() keeps a response it refused to cache, so a parser repair
    can be checked against it without spending another call."""
    return Path(cache_dir or CACHE) / f"statsapi_postseason_{int(season)}.rejected.json"


def tracked_path(season: int, tracked_dir: Path | None = None) -> Path:
    return Path(tracked_dir or TRACKED) / f"statsapi_postseason_{int(season)}.json"


def _read_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
def _is_final(game: dict) -> bool:
    return ((game.get("status") or {}).get("codedGameState") or "") in FINAL_CODES


def _pair(game: dict, ids: dict):
    """The two clubs of a game as a sorted tuple, or None when a side is not
    one of the 30 clubs (a placeholder) or missing."""
    out = []
    for side in ("home", "away"):
        tid = (((game.get("teams") or {}).get(side) or {}).get("team") or {}).get("id")
        code = ids.get(int(tid)) if tid is not None else None
        if code is None:
            return None
        out.append(code)
    return tuple(sorted(out))


def _series_groups(entries: list, season: int, ids: dict) -> list:
    """[(series id, round, games)], one per series actually played.

    The feed's series entry is the unit, with two repairs keyed on the clubs
    a game names, never on names or dates: an entry whose games name two or
    more distinct club pairs is split by pair (its id gains .1, .2 in the
    order the pairs first appear; a placeholder game joins the one pair that
    holds its club), and two entries of one round naming the same club pair
    are one series (games de-duplicated by gamePk downstream)."""
    groups: list = []
    for s in entries:
        meta = s.get("series") or {}
        games = s.get("games") or []
        gtype = meta.get("gameType") or (games[0].get("gameType") if games else None)
        if gtype in SKIPPED_TYPES:
            continue
        rnd = ROUND_OF.get(gtype)
        if rnd is None:
            raise PostseasonError(f"{season}: series {meta.get('id')} has game type {gtype!r}")
        pairs: list = []
        for g in games:
            pr = _pair(g, ids)
            if pr and pr not in pairs:
                pairs.append(pr)
        if len(pairs) <= 1:
            groups.append([meta.get("id"), rnd, list(games), pairs[0] if pairs else None])
            continue
        split = {pr: [] for pr in pairs}
        for g in games:
            pr = _pair(g, ids)
            if pr is None:
                clubs = set()
                for side in ("home", "away"):
                    tid = (((g.get("teams") or {}).get(side) or {}).get("team") or {}).get("id")
                    if tid is not None and ids.get(int(tid)):
                        clubs.add(ids[int(tid)])
                hits = [p for p in pairs if clubs & set(p)]
                pr = hits[0] if len(hits) == 1 else None
            if pr is not None:
                split[pr].append(g)
        for k, pr in enumerate(pairs, start=1):
            groups.append([f"{meta.get('id')}.{k}", rnd, split[pr], pr])
    merged: list = []
    for gid, rnd, games, pr in groups:
        twin = next((m for m in merged if pr is not None and m[1] == rnd and m[3] == pr), None)
        if twin is not None:
            twin[2].extend(games)
        else:
            merged.append([gid, rnd, games, pr])
    return [(gid, rnd, games) for gid, rnd, games, _ in merged]


def parse(body: dict, season: int, *, clubs_by_id: dict | None = None) -> dict:
    """The bracket of one response body: series rows and per-club rounds.

    Rows are [series_id, round, best_of, club_a, club_b, wins_a, wins_b,
    winner, complete]; club_a hosts the series' first listed game. A side
    that is a placeholder is None. Raises PostseasonError on a body without
    a series list."""
    if not isinstance(body, dict) or not isinstance(body.get("series"), list):
        raise PostseasonError(f"{season}: response lacks 'series'")
    ids = clubs_by_id if clubs_by_id is not None else _clubs_by_id()
    rows: list = []
    placeholders: set = set()
    per_round: dict = defaultdict(Counter)
    for gid, rnd, games in _series_groups(body["series"], season, ids):
        best_of = max((int(g.get("gamesInSeries") or 0) for g in games), default=0)
        order: list = []
        wins: Counter = Counter()
        counted: set = set()
        for g in games:
            sides = (g.get("teams") or {})
            for side in ("home", "away"):
                tid = ((sides.get(side) or {}).get("team") or {}).get("id")
                if tid is None:
                    continue
                code = ids.get(int(tid))
                if code is None:
                    placeholders.add(int(tid))
                elif code not in order:
                    order.append(code)
            pk = g.get("gamePk")
            if not _is_final(g) or pk in counted:
                continue
            counted.add(pk)
            for side in ("home", "away"):
                t = sides.get(side) or {}
                tid = (t.get("team") or {}).get("id")
                code = ids.get(int(tid)) if tid is not None else None
                if code is not None and t.get("isWinner") is True:
                    wins[code] += 1
        if len(order) > 2:
            raise PostseasonIdentityError(f"{season}: series {gid} lists clubs {order}")
        club_a = order[0] if order else None
        club_b = order[1] if len(order) > 1 else None
        need = best_of // 2 + 1 if best_of else None
        winner = None
        if need:
            won = [c for c in (club_a, club_b) if c and wins[c] >= need]
            if len(won) > 1:
                raise PostseasonIdentityError(f"{season}: series {gid} has two winners")
            winner = won[0] if won else None
        for c in (club_a, club_b):
            if c:
                per_round[rnd][c] += 1
        rows.append([gid, rnd, best_of, club_a, club_b,
                     wins[club_a] if club_a else 0, wins[club_b] if club_b else 0,
                     winner, winner is not None])
    rows.sort(key=lambda r: (r[1], str(r[0])))
    ws = [r for r in rows if r[1] == ROUND_OF["W"]]
    complete = len(ws) == 1 and ws[0][7] is not None
    has_first = any(r[1] == ROUND_OF["F"] for r in rows)

    clubs = {code: {"round_reached": 0, "series_won": 0, "bye": False, "in_progress": False}
             for code in sorted(set(ids.values()))}
    first_round_clubs = set(per_round.get(ROUND_OF["F"], {}))
    eliminated: set = set()
    for r in rows:
        rnd, a, b, winner = r[1], r[3], r[4], r[7]
        for c in (a, b):
            if c:
                clubs[c]["round_reached"] = max(clubs[c]["round_reached"], rnd)
        if winner:
            clubs[winner]["series_won"] += 1
            loser = b if winner == a else a
            if loser:
                eliminated.add(loser)
            if rnd == ROUND_OF["W"]:
                clubs[winner]["round_reached"] = CHAMPION
    for c in per_round.get(ROUND_OF["D"], {}):
        if has_first and c not in first_round_clubs:
            clubs[c]["bye"] = True
    if not complete:
        for c, v in clubs.items():
            v["in_progress"] = v["round_reached"] > 0 and c not in eliminated
    return {"season": int(season), "complete": complete, "series": rows, "clubs": clubs,
            "placeholders": sorted(placeholders), "has_first_round": has_first,
            "per_round": {k: dict(v) for k, v in per_round.items()}}


def identity_failures(parsed: dict) -> list:
    """Every identity a complete season breaks, as sentences; [] when it holds."""
    season = parsed["season"]
    fmt = format_for(season)
    clubs = parsed["clubs"]
    reached = [v["round_reached"] for v in clubs.values()]
    out: list = []
    counts = tuple(sum(1 for r in reached if r >= k) for k in range(1, 6))
    if counts[4] != 1:
        out.append(f"{season}: {counts[4]} champions, expected 1")
    if counts[3] != 2:
        out.append(f"{season}: {counts[3]} pennant winners, expected 2")
    if counts[0] != fmt["berths"]:
        out.append(f"{season}: {counts[0]} round-1 participants, expected {fmt['berths']}")
    if counts != fmt["round_counts"]:
        out.append(f"{season}: round counts {counts}, expected {fmt['round_counts']}")
    for rnd, per in parsed["per_round"].items():
        doubles = sorted(c for c, n in per.items() if n > 1)
        if doubles:
            out.append(f"{season}: clubs in two series of round {rnd}: {doubles}")
    if parsed["placeholders"]:
        out.append(f"{season}: placeholder ids {parsed['placeholders']}")
    if any(r[3] is None or r[4] is None or not r[8] for r in parsed["series"]):
        out.append(f"{season}: a series without two clubs or a winner")
    if fmt["first_round"] != parsed["has_first_round"]:
        out.append(f"{season}: first round present {parsed['has_first_round']}, "
                   f"expected {fmt['first_round']}")
    return out


def assert_identities(parsed: dict) -> None:
    bad = identity_failures(parsed)
    if bad:
        raise PostseasonIdentityError("; ".join(bad))


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------
def load(season: int, *, cache_dir: Path | None = None, tracked_dir: Path | None = None,
         clubs_by_id: dict | None = None) -> dict | None:
    """The parsed bracket of one season, or None when nothing is on disk.

    A completed season is read from the tracked copy first, then the cache;
    the live season from the cache. The identities are asserted on every
    complete season before this returns."""
    doc, source = None, None
    tp = tracked_path(season, tracked_dir)
    if tp.exists():
        doc, source = _read_json(tp), "tracked"
    if not (isinstance(doc, dict) and doc.get("complete")):
        cached = _read_json(cache_path(season, cache_dir))
        if isinstance(cached, dict):
            doc, source = cached, "cache"
    if not isinstance(doc, dict):
        return None
    parsed = parse(doc.get("body"), season, clubs_by_id=clubs_by_id)
    if parsed["complete"]:
        assert_identities(parsed)
    parsed["source"] = source
    parsed["fetched_at"] = doc.get("fetched_at")
    return parsed


def division_champions(season: int, *, cache_dir: Path | None = None) -> dict:
    """{division id: club code or None} for one season, from the standings
    cache, through franchise_export.division_champions (one rule)."""
    import franchise_export
    raw = _read_json(Path(cache_dir or CACHE) / f"statsapi_standings_{int(season)}.json") or {}
    return franchise_export.division_champions(
        raw.get("records") or [], live=(int(season) == int(franchise_export.SEASON_NOW)))


def feed_notes(parsed: dict, *, cache_dir: Path | None = None) -> list:
    """Where the standings' clinched count differs from the round-1
    participants read from the schedule. A note for the ingest log, never an
    error: the identities never read the standings (2012 is one)."""
    if not parsed or not parsed.get("complete"):
        return []
    season = parsed["season"]
    raw = _read_json(Path(cache_dir or CACHE) / f"statsapi_standings_{int(season)}.json")
    if not isinstance(raw, dict):
        return []
    clinched = sum(1 for rec in raw.get("records") or []
                   for tr in rec.get("teamRecords") or [] if tr.get("clinched"))
    n1 = sum(1 for v in parsed["clubs"].values() if v["round_reached"] >= 1)
    if clinched != n1:
        return [f"feed note {season}: the postseason schedule has {n1} round-1 clubs, "
                f"the standings {clinched} clinched rows"]
    return []


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------
def _first_game_date(body) -> str | None:
    dates = [g.get("officialDate") for s in (body or {}).get("series") or []
             for g in s.get("games") or [] if g.get("officialDate")]
    return min(dates) if dates else None


def fetch_decision(season: int, cached: dict | None, today: date,
                   regular_season_end: str | None) -> tuple:
    """(fetch?, reason) without force: the freeze, the once-a-day rule and
    the regular-season gate, decided from disk alone."""
    s = int(season)
    if isinstance(cached, dict) and cached.get("complete"):
        return False, "frozen"
    if s > today.year:
        return False, "future season"
    if s == today.year:
        if not regular_season_end:
            return False, "no regular-season end date on disk"
        if today.isoformat() <= str(regular_season_end):
            return False, "regular season not over"
    if isinstance(cached, dict):
        if str(cached.get("fetched_at") or "")[:10] == today.isoformat():
            return False, "fetched today"
        first = _first_game_date(cached.get("body"))
        if first and today.isoformat() < first:
            return False, "first postseason game not yet played"
    return True, "due"


def _http_get(url: str) -> dict:
    import requests
    resp = requests.get(url, timeout=TIMEOUT_S, headers={"User-Agent": "eephus-postseason"})
    resp.raise_for_status()
    return resp.json()


def _write_atomic(p: Path, doc: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, p)


def fetch(season: int, force: bool = False, *, today: date | None = None,
          cache_dir: Path | None = None, http_get=None, regular_season_end: str | None = None,
          clubs_by_id: dict | None = None) -> dict:
    """Fetch one season into the cache when the rules allow it.

    Returns {season, action ('fetched' or 'skipped'), reason, complete, path}.
    A body is validated before it is written: no 'series' list raises, and a
    complete season that breaks an identity raises, so a failure leaves the
    previous file in place."""
    s = int(season)
    today = today or date.today()
    p = cache_path(s, cache_dir)
    cached = _read_json(p)
    if not force:
        if regular_season_end is None and s == today.year:
            try:
                from mgmt_decisions import regular_season_end_on_disk
                regular_season_end = regular_season_end_on_disk(s)
            except Exception:                                   # noqa: BLE001
                regular_season_end = None
        go, reason = fetch_decision(s, cached, today, regular_season_end)
        if not go:
            return {"season": s, "action": "skipped", "reason": reason,
                    "complete": bool((cached or {}).get("complete")), "path": str(p)}
    body = (http_get or _http_get)(URL.format(season=s))
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        parsed = parse(body, s, clubs_by_id=clubs_by_id)
        if parsed["complete"]:
            assert_identities(parsed)
    except PostseasonError:
        _write_atomic(rejected_path(s, cache_dir),
                      {"season": s, "fetched_at": fetched_at, "complete": False, "body": body})
        raise
    doc = {"season": s, "fetched_at": fetched_at, "complete": parsed["complete"], "body": body}
    _write_atomic(p, doc)
    return {"season": s, "action": "fetched", "reason": "forced" if force else "due",
            "complete": parsed["complete"], "path": str(p), "n_series": len(parsed["series"])}


def promote_rejected(season: int, *, cache_dir: Path | None = None,
                     clubs_by_id: dict | None = None) -> dict:
    """Re-validate a refused response under the current parser and, when it
    now passes, cache it with its original fetched_at. No network."""
    rp = rejected_path(season, cache_dir)
    doc = _read_json(rp)
    if not isinstance(doc, dict):
        raise PostseasonError(f"{season}: no refused response on disk")
    parsed = parse(doc.get("body"), season, clubs_by_id=clubs_by_id)
    if parsed["complete"]:
        assert_identities(parsed)
    out = {"season": int(season), "fetched_at": doc.get("fetched_at"),
           "complete": parsed["complete"], "body": doc.get("body")}
    _write_atomic(cache_path(season, cache_dir), out)
    rp.unlink()
    return {"season": int(season), "action": "promoted", "reason": "refused response re-validated",
            "complete": parsed["complete"], "path": str(cache_path(season, cache_dir)),
            "n_series": len(parsed["series"])}


# ---------------------------------------------------------------------------
# the tracked copy
# ---------------------------------------------------------------------------
def trim_body(body: dict) -> dict:
    """The fields load() reads: series ids and game type, and per game its
    id, gameType, gamesInSeries, seriesDescription, codedGameState and the
    two team ids with isWinner."""
    out = []
    for s in (body or {}).get("series") or []:
        meta = s.get("series") or {}
        games = []
        for g in s.get("games") or []:
            teams = {}
            for side in ("away", "home"):
                t = (g.get("teams") or {}).get(side) or {}
                row = {"team": {"id": (t.get("team") or {}).get("id")}}
                if "isWinner" in t:
                    row["isWinner"] = t.get("isWinner")
                teams[side] = row
            games.append({"gamePk": g.get("gamePk"), "gameType": g.get("gameType"),
                          "gamesInSeries": g.get("gamesInSeries"),
                          "seriesDescription": g.get("seriesDescription"),
                          "status": {"codedGameState": (g.get("status") or {}).get("codedGameState")},
                          "teams": teams})
        out.append({"series": {"id": meta.get("id"), "gameType": meta.get("gameType")},
                    "games": games})
    return {"series": out}


def write_tracked(season: int, *, cache_dir: Path | None = None,
                  tracked_dir: Path | None = None, clubs_by_id: dict | None = None) -> dict:
    """Write the trimmed copy of a COMPLETE cached season under data/_labs/postseason/.
    The trimmed body must parse to the same bracket as the full one."""
    cached = _read_json(cache_path(season, cache_dir))
    if not (isinstance(cached, dict) and cached.get("complete")):
        raise PostseasonError(f"{season}: no complete season in the cache")
    full = parse(cached["body"], season, clubs_by_id=clubs_by_id)
    assert_identities(full)
    trimmed = trim_body(cached["body"])
    again = parse(trimmed, season, clubs_by_id=clubs_by_id)
    if (again["series"], again["clubs"]) != (full["series"], full["clubs"]):
        raise PostseasonError(f"{season}: the trimmed copy parses differently")
    doc = {"season": int(season), "fetched_at": cached.get("fetched_at"),
           "complete": True, "body": trimmed}
    p = tracked_path(season, tracked_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return {"season": int(season), "path": str(p), "bytes": p.stat().st_size}


# ---------------------------------------------------------------------------
# the nightly step (run_daily d8p)
# ---------------------------------------------------------------------------
def nightly(*, today: date | None = None, cache_dir: Path | None = None, log=None) -> dict:
    """Refresh the live season when the rules allow; read it back.

    Returns {season, action, reason, complete, n_series, notes, message}.
    Raises on a failed fetch or a broken complete bracket, so the caller files
    a red; nothing on disk changes in that case."""
    today = today or date.today()
    season = today.year
    got = fetch(season, today=today, cache_dir=cache_dir)
    parsed = load(season, cache_dir=cache_dir)
    notes = feed_notes(parsed, cache_dir=cache_dir) if parsed else []
    n_series = len(parsed["series"]) if parsed else 0
    msg = (f"{season}: {got['action']} ({got['reason']}); "
           f"{'complete' if parsed and parsed['complete'] else 'in progress' if parsed else 'no bracket on disk'}"
           + (f"; {'; '.join(notes)}" if notes else ""))
    if log:
        log.info("postseason cache: %s", msg)
    return {"season": season, "action": got["action"], "reason": got["reason"],
            "complete": bool(parsed and parsed["complete"]), "n_series": n_series,
            "notes": notes, "message": msg}
