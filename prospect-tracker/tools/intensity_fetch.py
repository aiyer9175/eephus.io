"""intensity_fetch: the game-intensity study's fetches, into .cache only, counts only.

Item H2 of the Part 8 intensity lane (intensity_index.md 3.0, 3.4, 3.5; section 5o of
docs/diamond-betting.md, "Game intensity: stakes, matchup quality and the postseason").
Three pulls, all public StatsAPI, no key and no Odds API credit:

1. REGULAR-SEASON FINALS for 2018, 2019 and 2021 to 2025 through
   betting_model.fetch_finals, one schedule request per season (the same pull 5k and
   7i register), stored as .cache/betting/regular_finals/<season>.json. Each season's
   count is reconciled against the B-CORPUS census and against the play corpus's own
   game_pk list (.cache/pbp_corpus plays, the game_pk column alone).
2. POSTSEASON GAME LISTS from the postseason.py cache (the F-SCORE plan's FS-1 ingest,
   .cache/statsapi_postseason_<season>.json, the tracked copy as fallback), cross-checked
   against mlb_leverage.season_game_pks with the postseason game types.
3. POSTSEASON winProbability FEEDS, one request per game, into .cache/win_prob_post/,
   a directory of its own: the 2018, 2019 and 2021 to 2025 postseasons as registered,
   and the 2000 to 2017 postseasons under owner answer INT-B1 (b), 2026-10-01.

WHY A DIRECTORY OF ITS OWN. tools/build_pbp_corpus.py globs every *.json directly in
.cache/win_prob (index_by_season and build()) and sorts a file into a season by its first
startTime year; a cached winProbability feed is a bare play list with no game type, so a
postseason feed written there would join a regular-season corpus on the next forced
rebuild, and the management module, eBR and the workload frame read those corpora. The
Baserunning runner builder reads .cache/win_prob/<pk>.json too. check_target() refuses
any path under .cache/win_prob/ and any path under data/. Each stored postseason feed is
wrapped as {game_pk, season, game_type, official_date, fetched_at, source_url, plays},
so even a reader pointed at it by mistake finds no bare play list. Only the intensity
lab reads .cache/win_prob_post/.

COUNTS ONLY (section 5o, 5c rule 1). Nothing here reads a score, a run, a winner or a
price beside a game: the receipt carries game_pk lists, game types, dates, fetch times,
play counts and drop counts. A run is not a look.

POLITENESS. Every request is spaced at least MIN_GAP_S apart and carries USER_AGENT.
Cached feeds are never fetched again without --force.

Usage (from prospect-tracker/):
  python tools/intensity_fetch.py --receipt <dir>/intensity_fetch_receipt.json
  python tools/intensity_fetch.py --dry-run          # lists and counts, no feed request
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: Regular seasons the study reads (2020 is excluded throughout; section 5o).
REGULAR_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
#: Postseasons as registered (intensity_index.md 3.5, about 270 games).
POSTSEASONS_REGISTERED = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
#: Postseasons added by owner answer INT-B1 (b), 2026-10-01 (about 600 more games).
POSTSEASONS_INT_B1 = tuple(range(2000, 2018))
POSTSEASONS = POSTSEASONS_INT_B1 + POSTSEASONS_REGISTERED
POSTSEASON_TYPES = ("F", "D", "L", "W")
FINAL_CODES = ("F", "O")

#: The B-CORPUS census of the 2026-09-05 plan, as section 5k quotes it, by season.
CENSUS = {2018: 2431, 2019: 2429, 2021: 2429, 2022: 2430, 2023: 2430, 2024: 2429, 2025: 2430}
CENSUS_LO, CENSUS_HI = 2429, 2431

CACHE = ROOT / ".cache"
FEED_DIR = CACHE / "win_prob_post"
FINALS_DIR = CACHE / "betting" / "regular_finals"
CORPUS_DIR = CACHE / "pbp_corpus"
RECEIPT_DEFAULT = CACHE / "intensity_fetch" / "receipt.json"
#: Never written by this tool: served artifacts, and the regular-season feed cache the
#: play corpus walks.
FORBIDDEN = (ROOT / "data", CACHE / "win_prob")

WP_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/winProbability"
MIN_GAP_S = 1.1
USER_AGENT = "eephus.io intensity_fetch/1 (game-intensity study; https://eephus.io/sources/)"
TIMEOUT_S = 30


class FetchRefused(Exception):
    """A write this tool may not make."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _forms(p: Path) -> list[Path]:
    """The absolute and the resolved form of a path (.cache may be a junction), case
    folded where the filesystem folds case."""
    a = Path(os.path.normcase(os.path.abspath(p)))
    r = Path(os.path.normcase(os.path.realpath(p)))
    return [a] if a == r else [a, r]


def check_target(path, *, forbidden=None) -> Path:
    """`path` as an absolute Path, or FetchRefused when it lies under data/ or under
    .cache/win_prob/ (in either its absolute or its resolved form)."""
    path = Path(path)
    for f in (FORBIDDEN if forbidden is None else forbidden):
        for pf in _forms(path):
            for ff in _forms(Path(f)):
                if pf == ff or pf.is_relative_to(ff):
                    raise FetchRefused(f"refusing to write {path}: it lies under {f}")
    return Path(os.path.abspath(path))


def _write_json(path, doc, *, forbidden=None) -> Path:
    p = check_target(path, forbidden=forbidden)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(p)
    return p


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class Pacer:
    """At least `gap` seconds between the starts of two requests."""

    def __init__(self, gap: float = MIN_GAP_S, clock=time.monotonic, sleep=time.sleep):
        self.gap, self.clock, self.sleep = float(gap), clock, sleep
        self.last = None
        self.n = 0

    def wait(self) -> None:
        if self.last is not None:
            left = self.gap - (self.clock() - self.last)
            if left > 0:
                self.sleep(left)
        self.last = self.clock()
        self.n += 1


def _session():
    import feed_cache
    feed_cache.SESSION.headers["User-Agent"] = USER_AGENT   # this process only
    return feed_cache.SESSION


# ---------------------------------------------------------------------------
# 1. regular-season finals
# ---------------------------------------------------------------------------
def keep_regular_rows(rows: list, season: int) -> tuple[list, dict, dict]:
    """Rows of `season` only, one per game_pk (the first listed), regular season only,
    with drop counts and {game_pk: [official dates]} for every game_pk the schedule lists
    more than once: a suspended game is listed on each day it was played and keeps its
    original official date, and section 5k treats a game_pk listed on two schedule dates
    as resumed. Reads no score field."""
    kept, seen, drops = [], set(), Counter()
    dates: dict = {}
    for r in rows or []:
        if str(r.get("season")) != str(season):
            drops["season_not_requested"] += 1
            continue
        if r.get("game_type") not in (None, "R"):
            drops["not_regular_season"] += 1
            continue
        try:
            pk = int(r.get("game_pk"))
        except (TypeError, ValueError):
            drops["no_game_pk"] += 1
            continue
        dates.setdefault(pk, []).append(r.get("date"))
        if pk in seen:
            drops["duplicate_game_pk"] += 1
            continue
        seen.add(pk)
        kept.append(r)
    multi = {str(pk): v for pk, v in sorted(dates.items()) if len(v) > 1}
    return kept, dict(drops), multi


def fetch_regular_season(season: int, *, pacer: Pacer, fetch=None, finals_dir=None,
                         force: bool = False, dry_run: bool = False) -> dict:
    """One season's finals into finals_dir/<season>.json; returns its counts."""
    finals_dir = Path(finals_dir or FINALS_DIR)
    path = finals_dir / f"{season}.json"
    check_target(path)
    doc = None if force else _read_json(path)
    cached = isinstance(doc, dict) and isinstance(doc.get("rows"), list)
    if not cached:
        if dry_run:
            return {"season": season, "status": "not_fetched_dry_run"}
        if fetch is None:
            import betting_model
            _session()
            fetch = betting_model.fetch_finals
        pacer.wait()
        rows = fetch(f"{season}-02-01", f"{season}-11-30")
        kept, drops, multi = keep_regular_rows(rows, season)
        doc = {"season": season, "fetched_at": _now(),
               "source": "betting_model.fetch_finals", "range": [f"{season}-02-01", f"{season}-11-30"],
               "n_returned": len(rows or []), "drops": drops,
               "listed_more_than_once": multi, "n_kept": len(kept), "rows": kept}
        _write_json(path, doc)
    return {"season": season, "status": "cached" if cached else "fetched",
            "fetched_at": doc.get("fetched_at"), "n_returned": doc.get("n_returned"),
            "n_kept": doc.get("n_kept"), "drops": doc.get("drops") or {},
            "listed_more_than_once": doc.get("listed_more_than_once"),
            "game_pks": sorted(int(r["game_pk"]) for r in doc["rows"])}


def corpus_game_pks(season: int, *, corpus_dir=None) -> set | None:
    """The play corpus's game_pk set for a season (the game_pk column alone), or None
    when the corpus file is absent."""
    p = Path(corpus_dir or CORPUS_DIR) / "plays" / str(season) / f"plays-{season}.parquet"
    if not p.exists():
        return None
    import pyarrow.parquet as pq
    col = pq.read_table(p, columns=["game_pk"]).column("game_pk").to_pylist()
    return {int(x) for x in col if x is not None}


def reconcile(season: int, finals_pks, corpus_pks) -> dict:
    """The census check on game_pk lists alone: the finals count against the census
    range and the census entry, and the two lists' differences."""
    fin = set(int(x) for x in finals_pks)
    out = {"season": season, "n_finals": len(fin), "census": CENSUS.get(season),
           "census_range": [CENSUS_LO, CENSUS_HI],
           "in_census_range": CENSUS_LO <= len(fin) <= CENSUS_HI,
           "equals_census": len(fin) == CENSUS.get(season)}
    if corpus_pks is None:
        out.update(n_corpus=None, only_in_finals=None, only_in_corpus=None)
    else:
        cor = set(corpus_pks)
        out.update(n_corpus=len(cor), only_in_finals=sorted(fin - cor),
                   only_in_corpus=sorted(cor - fin))
    return out


# ---------------------------------------------------------------------------
# 2. postseason game lists
# ---------------------------------------------------------------------------
def postseason_games_from_body(body: dict, season: int) -> tuple[list, dict]:
    """[{game_pk, season, game_type, official_date}] for every final game of type F, D,
    L or W in a postseason.py response body, one per game_pk, with drop counts. The
    final rule is postseason.py's (codedGameState F or O); no score is read."""
    out, seen, drops = [], set(), Counter()
    for s in (body or {}).get("series") or []:
        for g in s.get("games") or []:
            gt = g.get("gameType")
            if gt not in POSTSEASON_TYPES:
                drops[f"game_type_{gt}"] += 1
                continue
            if ((g.get("status") or {}).get("codedGameState") or "") not in FINAL_CODES:
                drops["not_final"] += 1
                continue
            pk = g.get("gamePk")
            if pk is None:
                drops["no_game_pk"] += 1
                continue
            if int(pk) in seen:
                drops["duplicate_game_pk"] += 1
                continue
            seen.add(int(pk))
            out.append({"game_pk": int(pk), "season": int(season), "game_type": gt,
                        "official_date": g.get("officialDate")})
    out.sort(key=lambda r: (r["official_date"] or "", r["game_pk"]))
    return out, dict(drops)


def postseason_games(season: int, *, cache_dir=None, tracked_dir=None) -> tuple[list, dict, str]:
    """The season's final postseason games from the postseason.py cache (its full
    body carries officialDate), the tracked copy as fallback. postseason.load() is
    called first so the bracket identities are asserted before the list is used."""
    import postseason
    postseason.load(season, cache_dir=cache_dir, tracked_dir=tracked_dir)
    for src, p in (("cache", postseason.cache_path(season, cache_dir)),
                   ("tracked", postseason.tracked_path(season, tracked_dir))):
        doc = _read_json(p)
        if isinstance(doc, dict) and doc.get("complete") and isinstance(doc.get("body"), dict):
            games, drops = postseason_games_from_body(doc["body"], season)
            return games, drops, src
    raise FileNotFoundError(f"no complete postseason.py file for {season}")


def schedule_crosscheck(season: int, games: list, *, pacer: Pacer, lister=None) -> dict:
    """mlb_leverage.season_game_pks with the postseason game types, against the
    bracket list, on game_pk alone."""
    if lister is None:
        import mlb_leverage
        _session()
        lister = mlb_leverage.season_game_pks
    pacer.wait()
    sched = {int(pk) for pk, _ in lister(season, game_type=",".join(POSTSEASON_TYPES))}
    mine = {g["game_pk"] for g in games}
    return {"n_schedule": len(sched), "n_bracket": len(mine),
            "only_in_schedule": sorted(sched - mine), "only_in_bracket": sorted(mine - sched)}


# ---------------------------------------------------------------------------
# 3. postseason winProbability feeds
# ---------------------------------------------------------------------------
def _plays_status(plays) -> str:
    if not plays:
        return "empty"
    import mlb_leverage
    return "complete" if mlb_leverage.plays_end_the_game(plays) else "partial"


def fetch_feed(game: dict, *, pacer: Pacer, get=None, feed_dir=None, force=False,
               dry_run=False) -> dict:
    """One postseason feed into feed_dir/<game_pk>.json, wrapped with its game type.
    Returns {game_pk, season, game_type, status, fetched_at, n_plays, cached}; status is
    complete, partial, empty, error or not_fetched_dry_run."""
    feed_dir = Path(feed_dir or FEED_DIR)
    pk = int(game["game_pk"])
    path = check_target(feed_dir / f"{pk}.json")
    base = {"game_pk": pk, "season": game["season"], "game_type": game["game_type"]}
    doc = None if force else _read_json(path)
    if isinstance(doc, dict) and isinstance(doc.get("plays"), list):
        return {**base, "status": _plays_status(doc["plays"]), "fetched_at": doc.get("fetched_at"),
                "n_plays": len(doc["plays"]), "cached": True}
    if dry_run:
        return {**base, "status": "not_fetched_dry_run", "fetched_at": None, "n_plays": None,
                "cached": False}
    if get is None:
        get = _session().get
    url = WP_URL.format(pk=pk)
    pacer.wait()
    fetched_at = _now()
    try:
        resp = get(url, timeout=TIMEOUT_S)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:   # one failed game is a counted error, never an abort
        return {**base, "status": "error", "fetched_at": fetched_at, "n_plays": None,
                "cached": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    import mlb_leverage
    plays = mlb_leverage._plays_of(payload)
    _write_json(path, {**base, "official_date": game.get("official_date"),
                       "fetched_at": fetched_at, "source_url": url, "plays": plays})
    return {**base, "status": _plays_status(plays), "fetched_at": fetched_at,
            "n_plays": len(plays), "cached": False}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
def run(*, regular_seasons=REGULAR_SEASONS, postseasons=POSTSEASONS, force=False,
        dry_run=False, receipt=None, log=print) -> dict:
    pacer = Pacer()
    rec = {"tool": "tools/intensity_fetch.py", "started_at": _now(), "user_agent": USER_AGENT,
           "min_gap_s": MIN_GAP_S, "dry_run": bool(dry_run),
           "feed_dir": str(FEED_DIR), "finals_dir": str(FINALS_DIR),
           "note": "counts only: no score, run, winner, stake or price is read or printed",
           "regular": {}, "postseason": {}, "games": []}

    for season in regular_seasons:
        r = fetch_regular_season(season, pacer=pacer, force=force, dry_run=dry_run)
        pks = r.pop("game_pks", None)
        if pks is not None:
            r["census"] = reconcile(season, pks, corpus_game_pks(season))
        rec["regular"][str(season)] = r
        c = r.get("census") or {}
        log(f"regular {season}: {r['status']}, kept {r.get('n_kept')}, drops {r.get('drops')}, "
            f"census {c.get('census')}, corpus {c.get('n_corpus')}, "
            f"only_in_finals {len(c.get('only_in_finals') or [])}, "
            f"only_in_corpus {len(c.get('only_in_corpus') or [])}")

    for season in postseasons:
        games, drops, src = postseason_games(season)
        row = {"source": src, "n_games": len(games),
               "by_type": dict(Counter(g["game_type"] for g in games)), "list_drops": drops}
        if not dry_run:
            row["schedule_crosscheck"] = schedule_crosscheck(season, games, pacer=pacer)
        feeds = []
        for g in games:
            f = fetch_feed(g, pacer=pacer, force=force, dry_run=dry_run)
            f["official_date"] = g.get("official_date")
            feeds.append(f)
        row["feeds"] = dict(Counter(f["status"] for f in feeds))
        row["feeds_fetched_this_run"] = sum(1 for f in feeds if not f["cached"]
                                            and f["status"] not in ("error", "not_fetched_dry_run"))
        row["feeds_cached_before"] = sum(1 for f in feeds if f["cached"])
        rec["postseason"][str(season)] = row
        rec["games"].extend(feeds)
        x = row.get("schedule_crosscheck") or {}
        log(f"postseason {season}: {len(games)} games {row['by_type']}, list drops {drops}, "
            f"feeds {row['feeds']}, schedule only {len(x.get('only_in_schedule') or [])}, "
            f"bracket only {len(x.get('only_in_bracket') or [])}")
        if receipt:
            _write_json(receipt, rec)

    tot = Counter()
    for row in rec["postseason"].values():
        tot.update(row["feeds"])
    rec["totals"] = {
        "regular_games": sum((r.get("n_kept") or 0) for r in rec["regular"].values()),
        "postseason_games": sum(r["n_games"] for r in rec["postseason"].values()),
        "postseason_games_registered": sum(rec["postseason"][str(s)]["n_games"]
                                           for s in postseasons if s in POSTSEASONS_REGISTERED),
        "postseason_games_int_b1": sum(rec["postseason"][str(s)]["n_games"]
                                       for s in postseasons if s in POSTSEASONS_INT_B1),
        "feeds": dict(tot), "requests": pacer.n}
    rec["finished_at"] = _now()
    if receipt:
        _write_json(receipt, rec)
    log(f"totals: {rec['totals']}")
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--receipt", default=str(RECEIPT_DEFAULT), help="receipt JSON path")
    ap.add_argument("--regular", default=",".join(map(str, REGULAR_SEASONS)),
                    help="regular seasons, comma separated ('' for none)")
    ap.add_argument("--postseasons", default=",".join(map(str, POSTSEASONS)),
                    help="postseasons, comma separated ('' for none)")
    ap.add_argument("--force", action="store_true", help="refetch what is cached")
    ap.add_argument("--dry-run", action="store_true", help="lists and counts, no feed request")
    a = ap.parse_args(argv)

    def seasons(s):
        out = tuple(int(x) for x in s.split(",") if x.strip())
        if 2020 in out:
            raise SystemExit("2020 is excluded from the intensity study (section 5o)")
        return out

    run(regular_seasons=seasons(a.regular), postseasons=seasons(a.postseasons),
        force=a.force, dry_run=a.dry_run, receipt=a.receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
