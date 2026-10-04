# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""StatsAPI club season lines (hitting, pitching, and the starter / reliever
pitching split), one season at a time, cached under .cache/team_stats/.

WHY THIS EXISTS (owner asks 13 and 15, 2026-09-30; Part 8 lane
league_team_stats, sections 2 and 8). The League Averages and Team Stats
sections of /mlbstats/ need what each club EARNED: its plate appearances and
pitches seen, its innings, batters faced and pitches thrown, and the same
pitching line split by role (innings actually thrown as a starter or as a
reliever). Nothing in the repo fetched StatsAPI's teams/stats endpoint before
this module. It reads three requests per season and nothing else:

  hit   teams/stats?season=Y&group=hitting&stats=season&sportIds=1&gameType=R
  pit   teams/stats?season=Y&group=pitching&stats=season&sportIds=1&gameType=R
  sprp  teams/stats?season=Y&group=pitching&stats=statSplits&sitCodes=sp,rp
        &sportIds=1&gameType=R&limit=100

THE LIMIT TRAP (measured 2026-09-30 on 2025). Without `limit` the statSplits
read returns 50 of its 60 rows (totalSplits 60), so ten club-role lines go
missing with no error. The sprp read therefore ALWAYS passes limit=100, and
every response is refused when it holds fewer rows than its own totalSplits or
fewer than 30 clubs per code.

NOT A SERVED INPUT. Nothing on the site reads this module in the patch that
added it. The readers are the League Averages and Team Stats exporters that
the lane builds next; promoting a column from here into a served number is a
separate, measured change.

SEASON-STAMPED, REFUSE ON SHAPE CHANGE (the fg_leaderboards.py pattern). Every
cached file is one (season, kind) and records the season, the request, the
fetch time and whether the season was complete when it was fetched. A season's
three responses are validated together BEFORE anything is written: a missing
block, a row from the wrong season, a page shorter than its totalSplits, a club
id that does not resolve, anything other than 30 clubs (30 per code on sprp),
or a broken identity (league PA against batters faced, pitches seen against
pitches thrown, and each club's sp + rp line against its whole pitching line;
exact on a complete season, within LIVE_TOLERANCE on the live one) raises
Refused and leaves the previous cache untouched.

CACHE POLICY (the TTL rule). A season is complete from November 1 of its year.
A file fetched while its season was complete never expires (force=True
refetches it); a live-season file expires after LIVE_TTL_S, so a daily run
reads it fresh and a same-day rerun reads the cache. Readers (team_lines,
expected_records) read disk only and raise NotCached when a season is absent.

xW-L. expected_records() reads MLB's published expected record from the
standings cache the pipeline already keeps (.cache/statsapi_standings_<Y>.json,
never fetched here): the `xWinLoss` entry only. `xWinLossSeason` projects the
full schedule and does not sum to games played, so it is never read. A club
whose xWinLoss wins plus losses differ from its games played is refused
(checked on all 27 cached seasons, 2000 to 2026: every club sums).

Every network read files one row into the ingest-health ledger through
bullpen_export.record_ingest under the source name `mlb_team_season`.

Usage:
    python mlb_team_season.py --seasons 2000 2026          # fetch what is missing or stale
    python mlb_team_season.py --seasons 2025 2025 --force
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "team_stats"
STANDINGS_DIR = ROOT / ".cache"

STATSAPI = "https://statsapi.mlb.com/api/v1"
SOURCE = "mlb_team_season"
SCHEMA = 1
FIRST_SEASON = 2000
N_CLUBS = 30
SPLIT_CODES = ("sp", "rp")
SPLIT_LIMIT = 100
LIVE_TTL_S = 24 * 3600
LIVE_TOLERANCE = 0.001
# The house request spacing (scrapers.RATE_LIMIT_SECONDS), across the process.
MIN_INTERVAL_S = 0.5

KINDS = ("hit", "pit", "sprp")

# Required on every row of a kind; a response missing one is a shape change.
REQUIRED_STATS = {
    "hit": ("gamesPlayed", "plateAppearances", "atBats", "runs"),
    "pit": ("gamesPlayed", "gamesStarted", "outs", "battersFaced", "runs"),
    "sprp": ("gamesStarted", "outs", "battersFaced", "runs"),
}

# The team-line parser's field maps: house key -> StatsAPI stat key.
HIT_FIELDS = {
    "g": "gamesPlayed", "pa": "plateAppearances", "ab": "atBats", "r": "runs",
    "h": "hits", "d": "doubles", "t": "triples", "hr": "homeRuns",
    "bb": "baseOnBalls", "ibb": "intentionalWalks", "hbp": "hitByPitch",
    "sf": "sacFlies", "sh": "sacBunts", "so": "strikeOuts", "sb": "stolenBases",
    "cs": "caughtStealing", "gidp": "groundIntoDoublePlay", "lob": "leftOnBase",
    "go": "groundOuts", "ao": "airOuts", "pitches": "numberOfPitches",
}
PIT_FIELDS = {
    "g": "gamesPlayed", "gs": "gamesStarted", "gp": "gamesPitched",
    "outs": "outs", "bf": "battersFaced", "r": "runs", "er": "earnedRuns",
    "h": "hits", "d": "doubles", "t": "triples", "hr": "homeRuns",
    "bb": "baseOnBalls", "ibb": "intentionalWalks", "hbp": "hitBatsmen",
    "so": "strikeOuts", "pitches": "numberOfPitches", "strikes": "strikes",
    "w": "wins", "l": "losses", "sv": "saves", "svo": "saveOpportunities",
    "hld": "holds", "bs": "blownSaves", "cg": "completeGames", "sho": "shutouts",
    "go": "groundOuts", "ao": "airOuts", "wp": "wildPitches", "bk": "balks",
    "ir": "inheritedRunners", "irs": "inheritedRunnersScored",
}


class Refused(RuntimeError):
    """A response (or a season's set of responses) failed validation. The cache
    is left as it was."""


class NotCached(LookupError):
    """The cache has no file for this (season, kind). Readers never fetch."""


# --------------------------------------------------------------------------
# Calendar and TTL
# --------------------------------------------------------------------------

def season_complete(season: int, today: Optional[date] = None) -> bool:
    """A season is complete from November 1 of its year: the regular season and
    the postseason are over and StatsAPI's season lines have settled (the rule
    fg_leaderboards.season_complete uses for its own cache)."""
    today = today or date.today()
    return (int(season), 11, 1) <= (today.year, today.month, today.day)


def is_fresh(doc: dict, now: Optional[float] = None,
             ttl_s: float = LIVE_TTL_S) -> bool:
    """A file fetched while its season was complete never expires; a live one
    expires after `ttl_s` (daily)."""
    if doc.get("complete"):
        return True
    try:
        t = datetime.fromisoformat(doc["fetched_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return False
    return ((now if now is not None else time.time()) - t) < ttl_s


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
_LAST = [0.0]


def _throttle() -> None:
    with _LOCK:
        wait = MIN_INTERVAL_S - (time.monotonic() - _LAST[0])
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.monotonic()


def statsapi_get(path: str, params: dict) -> dict:
    """One StatsAPI GET through the shared retrying session, at the house
    spacing. The default `http_get` of both ingest modules."""
    import feed_cache                    # noqa: PLC0415 - network only when fetching
    _throttle()
    resp = feed_cache.SESSION.get(f"{STATSAPI}/{path}", params=params, timeout=45)
    resp.raise_for_status()
    return resp.json()


def request_url(path: str, params: dict) -> str:
    return f"{STATSAPI}/{path}?{urlencode(params)}"


def _default_record(source: str, *, ok: bool, n_rows: int = 0, message: str = "",
                    import_fallback: bool = True) -> None:
    import bullpen_export                # noqa: PLC0415 - reporting path only
    bullpen_export.record_ingest(source, ok=ok, n_rows=n_rows, message=message,
                                 import_fallback=import_fallback)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Requests and validation
# --------------------------------------------------------------------------

def request_for(kind: str, season: int) -> tuple[str, dict]:
    """(path, params) for one kind. The sprp read always carries limit=100."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; use one of {KINDS}")
    base = {"season": int(season), "sportIds": 1, "gameType": "R"}
    if kind == "hit":
        return "teams/stats", {**base, "group": "hitting", "stats": "season"}
    if kind == "pit":
        return "teams/stats", {**base, "group": "pitching", "stats": "season"}
    return "teams/stats", {**base, "group": "pitching", "stats": "statSplits",
                           "sitCodes": ",".join(SPLIT_CODES), "limit": SPLIT_LIMIT}


def cache_path(season: int, kind: str, cache_dir: Optional[Path] = None) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; use one of {KINDS}")
    return Path(cache_dir if cache_dir is not None else CACHE_DIR) / f"{int(season)}_{kind}.json"


def _club(team: dict) -> Optional[str]:
    from trades import canonical_org_from_id    # noqa: PLC0415 - heavy import
    return canonical_org_from_id((team or {}).get("id"), (team or {}).get("name"))


def parse_response(blob: dict, kind: str, season: int,
                   club_of: Optional[Callable[[dict], Optional[str]]] = None) -> list[dict]:
    """Validated rows of one teams/stats response:
    [{team_id, club, name, code (sprp only), stat}], `stat` verbatim.

    Raises Refused on a missing block, a wrong group or stat type, a page
    shorter than its totalSplits, a row from another season, an unresolved
    club, a missing required stat, or anything other than 30 clubs (30 per
    code on sprp)."""
    club_of = club_of or _club
    season = int(season)
    blocks = (blob or {}).get("stats") or []
    if not blocks:
        raise Refused(f"{season} {kind}: response has no stats block")
    block = blocks[0]
    want_group = "hitting" if kind == "hit" else "pitching"
    want_type = "statSplits" if kind == "sprp" else "season"
    group = ((block.get("group") or {}).get("displayName") or "")
    typ = ((block.get("type") or {}).get("displayName") or "")
    if group != want_group or typ != want_type:
        raise Refused(f"{season} {kind}: block is {group}/{typ}, "
                      f"expected {want_group}/{want_type}")
    splits = block.get("splits") or []
    total = block.get("totalSplits")
    if isinstance(total, int) and len(splits) < total:
        raise Refused(f"{season} {kind}: the page holds {len(splits)} of its "
                      f"{total} rows (totalSplits); the read needs limit={SPLIT_LIMIT}")
    rows: list[dict] = []
    seen: dict = {}
    for sp in splits:
        s_season = sp.get("season")
        if s_season is not None and str(s_season) != str(season):
            raise Refused(f"{season} {kind}: a row carries season {s_season}")
        team = sp.get("team") or {}
        tid = team.get("id")
        club = club_of(team)
        if tid is None or not club:
            raise Refused(f"{season} {kind}: club {team!r} does not resolve")
        stat = sp.get("stat") or {}
        missing = [k for k in REQUIRED_STATS[kind] if stat.get(k) is None]
        if missing:
            raise Refused(f"{season} {kind}: {club} is missing {missing}")
        code = None
        if kind == "sprp":
            code = ((sp.get("split") or {}).get("code") or "")
            if code not in SPLIT_CODES:
                raise Refused(f"{season} {kind}: unexpected sitCode {code!r}")
        key = (code, int(tid))
        if key in seen:
            raise Refused(f"{season} {kind}: club {club} appears twice"
                          + (f" under {code}" if code else ""))
        seen[key] = club
        row = {"team_id": int(tid), "club": club, "name": team.get("name")}
        if code:
            row["code"] = code
        row["stat"] = dict(stat)
        rows.append(row)
    codes = SPLIT_CODES if kind == "sprp" else (None,)
    for code in codes:
        n = sum(1 for (c, _t) in seen if c == code)
        if n != N_CLUBS:
            label = f" for code {code}" if code else ""
            raise Refused(f"{season} {kind}: {n} clubs{label}, expected {N_CLUBS}")
        clubs = [v for (c, _t), v in seen.items() if c == code]
        if len(set(clubs)) != N_CLUBS:
            raise Refused(f"{season} {kind}: two team ids resolve to one club{(' for code ' + code) if code else ''}")
    return rows


def _int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


def parse_team_line(stat: dict, side: str) -> dict:
    """One club line in house keys. side 'hit' reads HIT_FIELDS; 'pit' (the
    whole staff, or one sp / rp line) reads PIT_FIELDS and adds `ip` as outs / 3.
    Counts only: a rate is derived by its exporter from these counts, never
    copied from StatsAPI's rounded strings. A field the feed lacks is None."""
    stat = stat or {}
    if side == "hit":
        return {k: _int(stat.get(src)) for k, src in HIT_FIELDS.items()}
    if side != "pit":
        raise ValueError(f"side must be 'hit' or 'pit', not {side!r}")
    out = {k: _int(stat.get(src)) for k, src in PIT_FIELDS.items()}
    if out["hbp"] is None:
        out["hbp"] = _int(stat.get("hitByPitch"))
    out["ip"] = None if out["outs"] is None else out["outs"] / 3.0
    return out


def _close(a: float, b: float, complete: bool) -> bool:
    if complete:
        return a == b
    return abs(a - b) <= LIVE_TOLERANCE * max(abs(a), abs(b), 1.0)


def check_identities(rows: dict, complete: bool) -> list[str]:
    """Problems with a season's three row sets taken together, [] when they
    agree. League PA equals league batters faced; pitches seen equal pitches
    thrown (when every club carries a count); each club's sp + rp outs,
    batters faced and pitches equal its whole pitching line. Exact on a
    complete season, within LIVE_TOLERANCE on the live one (the three reads
    are seconds apart while the day's late games settle)."""
    out: list[str] = []
    hit, pit, sprp = rows["hit"], rows["pit"], rows["sprp"]
    pa = sum(_int(r["stat"].get("plateAppearances")) or 0 for r in hit)
    bf = sum(_int(r["stat"].get("battersFaced")) or 0 for r in pit)
    if not _close(pa, bf, complete):
        out.append(f"league PA {pa} != batters faced {bf}")
    seen = [_int(r["stat"].get("numberOfPitches")) for r in hit]
    thrown = [_int(r["stat"].get("numberOfPitches")) for r in pit]
    if None not in seen and None not in thrown and not _close(sum(seen), sum(thrown), complete):
        out.append(f"league pitches seen {sum(seen)} != thrown {sum(thrown)}")
    whole = {r["team_id"]: r for r in pit}
    parts: dict = {}
    for r in sprp:
        parts.setdefault(r["team_id"], []).append(r)
    for tid, prs in sorted(parts.items()):
        w = whole.get(tid)
        if w is None:
            out.append(f"club {prs[0]['club']} has sp/rp lines and no pitching line")
            continue
        for key in ("outs", "battersFaced", "numberOfPitches"):
            vals = [_int(p["stat"].get(key)) for p in prs]
            tot = _int(w["stat"].get(key))
            if None in vals or tot is None:
                continue
            if not _close(sum(vals), tot, complete):
                out.append(f"{w['club']} sp + rp {key} {sum(vals)} != whole {tot}")
    return out


# --------------------------------------------------------------------------
# Load (cache, else network)
# --------------------------------------------------------------------------

def _read_doc(season: int, kind: str, cache_dir: Optional[Path]) -> Optional[dict]:
    p = cache_path(season, kind, cache_dir)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if doc.get("schema") != SCHEMA or doc.get("season") != int(season) or doc.get("kind") != kind:
        return None
    return doc


def load(season: int, *, force: bool = False, cache_dir: Optional[Path] = None,
         today: Optional[date] = None, now: Optional[float] = None,
         http_get: Optional[Callable[[str, dict], dict]] = None,
         record: Optional[Callable[..., None]] = None) -> dict:
    """{"hit": doc, "pit": doc, "sprp": doc} for one season.

    Reads each kind from the cache while it is fresh (is_fresh), fetches the
    rest, validates every response and the season's identities together, and
    only then writes the fetched files. Refused leaves the cache as it was and
    files a red ingest row; a fetch that succeeds files an ok row. A season
    served wholly from the cache files nothing."""
    season = int(season)
    if season < FIRST_SEASON:
        raise ValueError(f"season {season} precedes FIRST_SEASON {FIRST_SEASON}")
    record = record or _default_record
    complete = season_complete(season, today)
    docs: dict = {}
    todo: list[str] = []
    for kind in KINDS:
        doc = None if force else _read_doc(season, kind, cache_dir)
        if doc is not None and is_fresh(doc, now):
            docs[kind] = doc
        else:
            todo.append(kind)
    if not todo:
        return docs
    stamp = datetime.fromtimestamp(now if now is not None else time.time(),
                                   tz=timezone.utc).isoformat(timespec="seconds")
    get = http_get or statsapi_get
    try:
        for kind in todo:
            path, params = request_for(kind, season)
            try:
                blob = get(path, params)
            except Exception as exc:     # noqa: BLE001 - any transport failure is a refusal
                raise Refused(f"{season} {kind}: fetch failed ({exc})") from exc
            rows = parse_response(blob, kind, season)
            docs[kind] = {
                "schema": SCHEMA, "kind": kind, "season": season,
                "fetched_at": stamp, "complete": complete,
                "url": request_url(path, params), "n_rows": len(rows),
                "rows": rows,
            }
        problems = check_identities({k: docs[k]["rows"] for k in KINDS}, complete)
        if problems:
            raise Refused(f"{season}: identities broken: " + "; ".join(problems[:5])
                          + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""))
    except Refused as exc:
        record(SOURCE, ok=False, n_rows=0, message=str(exc))
        raise
    for kind in todo:
        _write_atomic(cache_path(season, kind, cache_dir),
                      json.dumps(docs[kind], separators=(",", ":")) + "\n")
    n = sum(docs[k]["n_rows"] for k in todo)
    record(SOURCE, ok=True, n_rows=n,
           message=f"{season} {'+'.join(todo)} fetched ({'complete' if complete else 'live'})",
           import_fallback=False)
    return docs


# --------------------------------------------------------------------------
# Readers (cache only)
# --------------------------------------------------------------------------

def cached(season: int, kind: str, cache_dir: Optional[Path] = None) -> dict:
    """The cached document, never the network. NotCached when absent."""
    doc = _read_doc(season, kind, cache_dir)
    if doc is None:
        raise NotCached(f"no cached team_stats {kind} for {season} at "
                        f"{cache_path(season, kind, cache_dir)}")
    return doc


def team_lines(season: int, cache_dir: Optional[Path] = None) -> dict:
    """{"hit": {club: line}, "pit": {club: line}, "sp": {club: line},
    "rp": {club: line}} from the cache, each line parse_team_line's dict plus
    team_id. NotCached when a kind is absent."""
    out: dict = {"hit": {}, "pit": {}, "sp": {}, "rp": {}}
    for kind in KINDS:
        for r in cached(season, kind, cache_dir)["rows"]:
            side = "hit" if kind == "hit" else "pit"
            bucket = r["code"] if kind == "sprp" else kind
            out[bucket][r["club"]] = {"team_id": r["team_id"], **parse_team_line(r["stat"], side)}
    return out


def parse_expected_records(raw: dict,
                           club_of: Optional[Callable[[dict], Optional[str]]] = None) -> dict:
    """{club: {team_id, g, w, l, xw, xl}} from a StatsAPI standings payload,
    reading the `xWinLoss` expected record only (never `xWinLossSeason`).

    Raises Refused when a club has no xWinLoss entry, when its xWinLoss wins
    plus losses differ from its games played, or when the payload does not
    hold 30 clubs. W + L is not checked against games played: a tie game
    counts in games played (2000, 2001, 2002, 2003, 2005 and 2016 carry one)."""
    club_of = club_of or _club
    out: dict = {}
    for rec in (raw or {}).get("records") or []:
        for tr in rec.get("teamRecords") or []:
            team = tr.get("team") or {}
            club = club_of(team)
            if not club or team.get("id") is None:
                raise Refused(f"standings club {team!r} does not resolve")
            exp = ((tr.get("records") or {}).get("expectedRecords") or [])
            x = [e for e in exp if e.get("type") == "xWinLoss"]
            if not x:
                raise Refused(f"{club}: no xWinLoss expected record")
            xw, xl = _int(x[0].get("wins")), _int(x[0].get("losses"))
            g = _int(tr.get("gamesPlayed"))
            if xw is None or xl is None or g is None or xw + xl != g:
                raise Refused(f"{club}: xWinLoss {xw}-{xl} does not sum to "
                              f"games played {g}")
            if club in out:
                raise Refused(f"standings club {club} appears twice")
            out[club] = {"team_id": int(team["id"]), "g": g,
                         "w": _int(tr.get("wins")), "l": _int(tr.get("losses")),
                         "xw": xw, "xl": xl}
    if len(out) != N_CLUBS:
        raise Refused(f"standings hold {len(out)} clubs, expected {N_CLUBS}")
    return out


def expected_records(season: int, standings_dir: Optional[Path] = None) -> dict:
    """parse_expected_records over .cache/statsapi_standings_<Y>.json, the file
    the pipeline already keeps. Disk only; NotCached when absent."""
    p = Path(standings_dir if standings_dir is not None else STANDINGS_DIR) \
        / f"statsapi_standings_{int(season)}.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise NotCached(f"no cached standings for {season} at {p}") from None
    return parse_expected_records(raw)


# --------------------------------------------------------------------------
# CLI (the one-time backfill and manual refreshes)
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seasons", nargs=2, type=int, metavar=("FIRST", "LAST"),
                    required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--cache-dir", type=Path, default=None)
    args = ap.parse_args(argv)
    bad = 0
    for y in range(args.seasons[0], args.seasons[1] + 1):
        try:
            docs = load(y, force=args.force, cache_dir=args.cache_dir)
        except Refused as exc:
            bad += 1
            print(f"{y} REFUSED {exc}")
            continue
        lines = team_lines(y, args.cache_dir)
        pa = sum(v["pa"] or 0 for v in lines["hit"].values())
        bf = sum(v["bf"] or 0 for v in lines["pit"].values())
        seen = sum(v["pitches"] or 0 for v in lines["hit"].values())
        thrown = sum(v["pitches"] or 0 for v in lines["pit"].values())
        print(f"{y} ok complete={docs['hit']['complete']} rows="
              f"{'/'.join(str(docs[k]['n_rows']) for k in KINDS)} "
              f"PA={pa} BF={bf} seen={seen} thrown={thrown} "
              f"fetched_at={min(docs[k]['fetched_at'] for k in KINDS)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
