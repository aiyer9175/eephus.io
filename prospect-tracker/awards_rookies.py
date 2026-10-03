# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Rookie status for the Awards module (AWARDS_1_ROOKIE_STATUS; AWARDS_PLAN 4.2
'Rookie eligibility', LANE_DATA 2.3).

MLB's three rookie gates, measured through 31 December of S-1 (a player who crosses a
line during S stays eligible for S):

  at-bats   career MLB at-bats through S-1 <= 130, summed over every row of the cached
            StatsAPI season lines .cache/fa_statsapi_hitting_<y>.json (atBats), 2000 on;
  innings   career MLB innings through S-1 <= 50, outs / 3 over every row of
            .cache/fa_statsapi_pitching_<y>.json, 2000 on;
  days      active-roster days through S-1 <= 45, which the site cannot measure (no
            service-time engine until M10_SERVICE_TIME_ENGINE) and so ESTIMATES from the
            league-wide StatsAPI transaction log .cache/mlb_transactions/tx_<yyyy>_<mm>.json.gz
            (2008-01 on; il_table.json in that folder is a different file and is not read).

The days proxy. A segment opens on a transaction whose description says "selected the
contract", "purchased" (the contract), "recalled", "reinstated" or "activated" and whose
club is an MLB club; it closes on an injured or disabled list placement or transfer (the
two regexes below, which match StatsAPI's wording "placed RHP <name> on the 60-day injured
list" and "transferred <name> to the 60-day disabled list"; never stats._DEACTIVATING_DESCRIPTORS,
whose phrases match none of it, AWARDS_PLAN F8), or on "optioned", "sent ... outright",
"designated ... for assignment", "released", "traded", "claimed ... off waivers",
"reassigned ... minor league(s)", "elected free agency", "suspended" or "retired". A traded
player's segment closes on the trade and a new one opens only on a new selection, recall
or activation. Days count only inside [Opening Day, 1 September] of each year, both ends
inclusive (as stats._count_active_roster_days counts), 2020 from 2020-07-23. Opening Day is
the earliest regular-season game date on disk (the play corpus's game dates in
.cache/mgmt_game_dates.json, written by mgmt_decisions.game_dates) and, for a year with no
corpus, the typed table OPENING_DAY_TYPED, whose source is named beside it.

This module imports no fetcher (fa_sources fetches on a cache miss) and opens no socket; it
reads the cache files directly and refuses a season whose inputs are not on disk.

CLI:
  python awards_rookies.py --seasons 2011-2026 --write
      writes the tracked, unpublished data/_labs/awards/rookies.json; a season block, once
      written, is kept byte for byte on later runs;
  python awards_rookies.py --seasons 2024 --write --rebuild-season 2024 --reason "<why>"
      rewrites one block and records the reason in it.
Rookie status for S needs the transaction log through December of S-1 (2027 needs
tx_2026_12.json.gz); the CLI refuses and names tools/backfill_mlb_transactions.py.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache"
OUT_PATH = ROOT / "data" / "_labs" / "awards" / "rookies.json"
BACKFILL_TOOL = "tools/backfill_mlb_transactions.py"

SCHEMA = 1
PRODUCED_BY = "awards_rookies.py"

#: MLB's rookie lines (the at-bat and innings lines are "more than", so <= passes).
PRIOR_AB_MAX = 130
PRIOR_IP_MAX = 50.0
PROXY_DAYS_MAX = 45
#: Rows whose proxy days fall in this closed band carry the near_45_day_line token.
NEAR_45_BAND = (31, 60)

STATSAPI_FIRST_SEASON = 2000
TX_FIRST = (2008, 1)
#: The last day of a regular season that counts toward the 45-day line (month, day).
SEASON_CAP = (9, 1)
#: The 2020 season opened late; its window starts here instead of the table's date.
WINDOW_2020_OPEN = date(2020, 7, 23)
#: A corpus year with fewer dated games than this is not a regular season on disk.
MIN_CORPUS_GAMES = 1000

#: The 30 MLB clubs' StatsAPI team ids (GET /api/v1/teams?sportId=1; the same list the
#: transaction backfill keeps in .cache/mlb_transactions/mlb_teams.json). Stable since 2005.
MLB_TEAM_IDS = frozenset(range(108, 122)) | frozenset(range(133, 148)) | frozenset({158})

#: Opening Day where no regular-season corpus is on disk: the first scheduled
#: regular-season game of each year from MLB's published schedules (the international
#: openers count: Tokyo 2008, 2012, 2019 and 2025, Sydney 2014, Seoul 2024). The
#: corpus's own earliest game date wins where a year is on disk (opening_day()).
OPENING_DAY_TYPED = {
    2008: date(2008, 3, 25), 2009: date(2009, 4, 5), 2010: date(2010, 4, 4),
    2011: date(2011, 3, 31), 2012: date(2012, 3, 28), 2013: date(2013, 3, 31),
    2014: date(2014, 3, 22), 2015: date(2015, 4, 5), 2016: date(2016, 4, 3),
    2017: date(2017, 4, 2), 2018: date(2018, 3, 29), 2019: date(2019, 3, 20),
    2020: date(2020, 7, 23), 2021: date(2021, 4, 1), 2022: date(2022, 4, 7),
    2023: date(2023, 3, 30), 2024: date(2024, 3, 20), 2025: date(2025, 3, 18),
    2026: date(2026, 3, 25),
}
OPENING_DAY_TYPED_SOURCE = "MLB regular-season schedules, first scheduled game of the year"
OPENING_DAY_CORPUS_SOURCE = ".cache/mgmt_game_dates.json (play corpus game dates, earliest of the year)"

# --- the descriptors ------------------------------------------------------------------
#: Injured or disabled list placements and transfers, in StatsAPI's wording.
IL_PLACED_RE = re.compile(r"placed .* on the .*(injured|disabled) list")
IL_TRANSFER_RE = re.compile(r"transferred .* to the .*(injured|disabled) list")
#: Opens a segment when the club is an MLB club.
OPEN_RE = re.compile(
    r"selected the contract|\bpurchased\b|\brecalled\b|\breinstated\b|\bactivated\b")
#: Closes a segment (any club: an option names the minor league club it goes to).
CLOSE_RE = re.compile(
    r"\boptioned\b|\bsent\b.*\boutright\b|\bdesignated\b.*\bfor assignment\b|\breleased\b"
    r"|\btraded\b|\bclaimed\b.*\boff waivers\b|\breassigned\b.*\bminor league"
    r"|elected free agency|\bsuspended\b|\bretired\b")

COLUMNS = ["mlbam", "prior_ab", "prior_ip", "proxy_days", "eligible", "reason"]
NEAR_TOKEN = "near_45_day_line"
POOL_RULE = ("every player with an MLB season line in S whose prior at-bats and innings "
             "through S-1 are at or under the lines; a player over either line is not a "
             "rookie and is counted in n_over_lines, not listed")


# --- classification and the day count -----------------------------------------------
def classify(description: str, club_is_mlb: bool) -> str | None:
    """'open', 'close' or None for one transaction description. The injured-list
    regexes are read first; an opener counts only at an MLB club; the other closers
    count at any club."""
    d = (description or "").lower()
    if IL_PLACED_RE.search(d) or IL_TRANSFER_RE.search(d):
        return "close"
    if OPEN_RE.search(d):
        return "open" if club_is_mlb else None
    if CLOSE_RE.search(d):
        return "close"
    return None


def transaction_club(tx: dict) -> int | None:
    """The club a transaction moves the player to, else the one it moves him from."""
    for key in ("toTeam", "fromTeam"):
        t = tx.get(key) or {}
        if t.get("id") is not None:
            try:
                return int(t["id"])
            except (TypeError, ValueError):
                return None
    return None


def transaction_date(tx: dict) -> date | None:
    for key in ("date", "effectiveDate"):
        s = (tx.get(key) or "")[:10]
        if s:
            try:
                return date.fromisoformat(s)
            except ValueError:
                continue
    return None


def events_from_transactions(transactions, mlb_ids=MLB_TEAM_IDS) -> dict:
    """mlbam -> sorted [(date, tx_id, kind)] over one iterable of StatsAPI rows."""
    ev: dict = defaultdict(list)
    for tx in transactions:
        pid = (tx.get("person") or {}).get("id")
        if pid is None:
            continue
        d = transaction_date(tx)
        if d is None:
            continue
        kind = classify(tx.get("description") or "", transaction_club(tx) in mlb_ids)
        if kind is None:
            continue
        ev[int(pid)].append((d, int(tx.get("id") or 0), kind))
    for rows in ev.values():
        rows.sort()
    return ev


def window_days(start: date, end: date, opening) -> int:
    """Days of [start, end] (both ends inclusive) that fall inside [Opening Day,
    1 September] of each year; `opening` maps a year to its Opening Day."""
    if end < start:
        return 0
    total = 0
    for year in range(start.year, end.year + 1):
        lo = max(start, opening(year))
        hi = min(end, date(year, *SEASON_CAP))
        if hi >= lo:
            total += (hi - lo).days + 1
    return total


def proxy_days(events, end: date, opening) -> int:
    """Active-roster days estimated from a player's sorted (date, id, kind) events
    through `end`: a segment opens on the first 'open' and closes on the next 'close';
    an open segment at `end` counts through `end`."""
    total = 0
    since: date | None = None
    for d, _tx_id, kind in events:
        if d > end:
            break
        if kind == "open":
            if since is None:
                since = d
        elif since is not None:
            total += window_days(since, d, opening)
            since = None
    if since is not None:
        total += window_days(since, end, opening)
    return total


def eligibility(prior_ab: int, prior_ip: float, days: int) -> tuple[bool, str]:
    """(eligible, reason). The reason lists each line crossed; an eligible row reads
    'eligible'; rows with proxy days in NEAR_45_BAND carry the near_45_day_line token."""
    reasons = []
    if prior_ab > PRIOR_AB_MAX:
        reasons.append(f"prior at-bats {prior_ab} over {PRIOR_AB_MAX}")
    if prior_ip > PRIOR_IP_MAX:
        reasons.append(f"prior innings {prior_ip:.1f} over {PRIOR_IP_MAX:g}")
    if days > PROXY_DAYS_MAX:
        reasons.append(f"roster days {days} over {PROXY_DAYS_MAX} (estimate)")
    ok = not reasons
    text = "eligible" if ok else "; ".join(reasons)
    if near_45_day_line(days):
        text += "; " + NEAR_TOKEN
    return ok, text


def near_45_day_line(days: int) -> bool:
    lo, hi = NEAR_45_BAND
    return lo <= int(days) <= hi


# --- readers (cache files only; nothing here fetches) ----------------------------------
def statsapi_path(cache_dir: Path, group: str, season: int) -> Path:
    return Path(cache_dir) / f"fa_statsapi_{group}_{season}.json"


def tx_path(cache_dir: Path, year: int, month: int) -> Path:
    return Path(cache_dir) / "mlb_transactions" / f"tx_{year}_{month:02d}.json.gz"


def _load_json(path: Path):
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _splits(doc) -> list:
    try:
        return list((doc.get("stats") or [{}])[0].get("splits") or [])
    except (AttributeError, IndexError):
        return []


def prior_counts(cache_dir: Path, through: int, first: int = STATSAPI_FIRST_SEASON):
    """(at_bats, outs) per mlbam summed over every season line from `first` to
    `through`; a missing file raises FileNotFoundError. `first` is a test seam (a
    fixture world starts later than 2000); the CLI always reads from 2000."""
    ab: dict = defaultdict(int)
    outs: dict = defaultdict(int)
    for y in range(first, through + 1):
        for sp in _splits(_load_json(statsapi_path(cache_dir, "hitting", y))):
            ab[int(sp["player"]["id"])] += int((sp.get("stat") or {}).get("atBats") or 0)
        for sp in _splits(_load_json(statsapi_path(cache_dir, "pitching", y))):
            outs[int(sp["player"]["id"])] += int((sp.get("stat") or {}).get("outs") or 0)
    return ab, outs


def season_players(cache_dir: Path, season: int) -> set:
    """Every mlbam with a hitting or pitching season line in `season`."""
    ids = set()
    for group in ("hitting", "pitching"):
        for sp in _splits(_load_json(statsapi_path(cache_dir, group, season))):
            ids.add(int(sp["player"]["id"]))
    return ids


def tx_months(first=TX_FIRST, last=None):
    y, m = first
    while (y, m) <= tuple(last):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def missing_tx_months(cache_dir: Path, last, first=TX_FIRST) -> list:
    return [(y, m) for y, m in tx_months(first, last) if not tx_path(cache_dir, y, m).exists()]


def load_events(cache_dir: Path, last, first=TX_FIRST) -> dict:
    """Events per mlbam over every month from `first` (TX_FIRST; a test seam) to
    `last` (inclusive)."""
    def rows():
        for y, m in tx_months(first, last):
            doc = _load_json(tx_path(cache_dir, y, m))
            for tx in (doc.get("transactions") or []):
                yield tx
    return events_from_transactions(rows())


def corpus_opening_days(path: Path) -> dict:
    """year -> earliest game date among a year's corpus games, for years with at
    least MIN_CORPUS_GAMES dated games."""
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    by: dict = defaultdict(list)
    for d in got.values():
        s = str(d or "")[:10]
        try:
            by[int(s[:4])].append(date.fromisoformat(s))
        except ValueError:
            continue
    return {y: min(v) for y, v in by.items() if len(v) >= MIN_CORPUS_GAMES}


def opening_day_table(cache_dir: Path, years) -> dict:
    """year -> {'date': iso, 'source': 'corpus'|'typed'}; the corpus wins where it holds
    the year; 2020 opens on WINDOW_2020_OPEN whatever the table says."""
    corpus = corpus_opening_days(Path(cache_dir) / "mgmt_game_dates.json")
    out = {}
    for y in years:
        if y == 2020:
            out[y] = {"date": WINDOW_2020_OPEN.isoformat(), "source": "typed"}
        elif y in corpus:
            out[y] = {"date": corpus[y].isoformat(), "source": "corpus"}
        elif y in OPENING_DAY_TYPED:
            out[y] = {"date": OPENING_DAY_TYPED[y].isoformat(), "source": "typed"}
        else:
            raise KeyError(f"no Opening Day on disk or in OPENING_DAY_TYPED for {y}")
    return out


def opening_from_table(table: dict):
    def _open(year: int) -> date:
        row = table.get(year) or table.get(str(year))
        if row is None:
            raise KeyError(f"no Opening Day for {year}")
        return date.fromisoformat(row["date"])
    return _open


# --- the season block --------------------------------------------------------------------
def _sha1_12(parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()[:12]


_SHA1_MEMO: dict = {}


def _file_sha1(path: Path) -> str:
    """sha1 of a file's bytes, memoised per (path, size, mtime) within one process."""
    st = Path(path).stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key in _SHA1_MEMO:
        return _SHA1_MEMO[key]
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    _SHA1_MEMO[key] = h.hexdigest()
    return _SHA1_MEMO[key]


def input_hashes(cache_dir: Path, season: int, opening_table: dict, *,
                 statsapi_first: int = STATSAPI_FIRST_SEASON, tx_first=TX_FIRST) -> dict:
    """One sha1_12 per input family, each over the sorted (file name, file sha1) list."""
    through = season - 1
    hit = [(statsapi_path(cache_dir, "hitting", y).name,
            _file_sha1(statsapi_path(cache_dir, "hitting", y)))
           for y in range(statsapi_first, through + 1)]
    pit = [(statsapi_path(cache_dir, "pitching", y).name,
            _file_sha1(statsapi_path(cache_dir, "pitching", y)))
           for y in range(statsapi_first, through + 1)]
    txs = [(tx_path(cache_dir, y, m).name, _file_sha1(tx_path(cache_dir, y, m)))
           for y, m in tx_months(tx_first, (through, 12))]
    od = sorted((str(y), v["date"], v["source"]) for y, v in opening_table.items())
    return {
        "statsapi_hitting": _sha1_12(f"{n} {s}" for n, s in hit),
        "statsapi_pitching": _sha1_12(f"{n} {s}" for n, s in pit),
        "transactions": _sha1_12(f"{n} {s}" for n, s in txs),
        "opening_day": _sha1_12(" ".join(r) for r in od),
    }


def check_inputs(cache_dir: Path, season: int, *, statsapi_first: int = STATSAPI_FIRST_SEASON,
                 tx_first=TX_FIRST) -> list[str]:
    """Human-readable refusals for a season whose inputs are not on disk."""
    problems = []
    through = season - 1
    gap = missing_tx_months(cache_dir, (through, 12), tx_first)
    if gap:
        y, m = gap[0]
        problems.append(
            f"season {season} needs the transaction log through {through}-12 and "
            f"{len(gap)} month(s) are missing from {cache_dir / 'mlb_transactions'} "
            f"(first {y}-{m:02d}); run {BACKFILL_TOOL} for those months first. "
            "This module never fetches.")
    for y in range(statsapi_first, season + 1):
        for group in ("hitting", "pitching"):
            p = statsapi_path(cache_dir, group, y)
            if not p.exists():
                problems.append(f"season {season} needs {p.name} (the FA StatsAPI season "
                                "line cache, fa_sources); this module never fetches.")
    return problems


def build_season(season: int, cache_dir: Path = CACHE_DIR, *, events: dict | None = None,
                 opening_table: dict | None = None, built_at: str | None = None,
                 statsapi_first: int = STATSAPI_FIRST_SEASON, tx_first=TX_FIRST) -> dict:
    """One season block. `events` (from load_events) and `opening_table` may be passed
    to share them across seasons; both are rebuilt from the cache otherwise.
    `statsapi_first` and `tx_first` are test seams for a fixture world; the CLI keeps
    the module constants (2000 and 2008-01)."""
    cache_dir = Path(cache_dir)
    through = season - 1
    problems = check_inputs(cache_dir, season, statsapi_first=statsapi_first, tx_first=tx_first)
    if problems:
        raise FileNotFoundError("; ".join(problems))
    if events is None:
        events = load_events(cache_dir, (through, 12), tx_first)
    years = range(tx_first[0], through + 1)
    if opening_table is None:
        opening_table = opening_day_table(cache_dir, years)
    table = {int(k): v for k, v in opening_table.items() if int(k) in years}
    opening = opening_from_table(table)
    end = date(through, 12, 31)
    ab, outs = prior_counts(cache_dir, through, statsapi_first)
    players = season_players(cache_dir, season)
    rows = []
    n_over = 0
    n_days_only = 0
    for pid in sorted(players):
        prior_ab = int(ab.get(pid, 0))
        prior_ip = round(int(outs.get(pid, 0)) / 3.0, 1)
        if prior_ab > PRIOR_AB_MAX or prior_ip > PRIOR_IP_MAX:
            n_over += 1
            continue
        days = proxy_days(events.get(pid, ()), end, opening)
        ok, reason = eligibility(prior_ab, prior_ip, days)
        if not ok:
            n_days_only += 1
        rows.append([pid, prior_ab, prior_ip, days, ok, reason])
    return {
        "season": season,
        "built_at": built_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "statsapi_seasons": f"{statsapi_first}-{through}",
            "transactions_from": f"{tx_first[0]}-{tx_first[1]:02d}",
            "transactions_to": f"{through}-12",
            "through": end.isoformat(),
            "opening_day": {str(y): table[y] for y in sorted(table)},
            "sha1_12": input_hashes(cache_dir, season, table, statsapi_first=statsapi_first,
                                    tx_first=tx_first),
        },
        "pool_rule": POOL_RULE,
        "n_players_with_line": len(players),
        "n_over_lines": n_over,
        "n_pool": len(rows),
        "n_eligible": sum(1 for r in rows if r[4]),
        "n_days_only": n_days_only,
        "columns": list(COLUMNS),
        "rows": rows,
    }


# --- the file ------------------------------------------------------------------------------
def _empty_payload() -> dict:
    return {
        "schema": SCHEMA,
        "produced_by": PRODUCED_BY,
        "lines": {"prior_ab_max": PRIOR_AB_MAX, "prior_ip_max": PRIOR_IP_MAX,
                  "proxy_days_max": PROXY_DAYS_MAX, "near_45_day_line": list(NEAR_45_BAND),
                  "window": "Opening Day to 1 September of each year, both ends inclusive; "
                            "2020 from " + WINDOW_2020_OPEN.isoformat()},
        "opening_day_sources": {"corpus": OPENING_DAY_CORPUS_SOURCE,
                                "typed": OPENING_DAY_TYPED_SOURCE},
        "columns": list(COLUMNS),
        "seasons": [],
    }


def load_payload(path: Path = OUT_PATH) -> dict:
    p = Path(path)
    if not p.exists():
        return _empty_payload()
    return json.loads(p.read_text(encoding="utf-8"))


def dumps_payload(payload: dict) -> str:
    """Readable JSON with one compact row per line."""
    blocks = []
    for blk in payload.get("seasons", []):
        head = {k: v for k, v in blk.items() if k != "rows"}
        text = json.dumps(head, indent=1, ensure_ascii=True)
        rows = ",\n".join("   " + json.dumps(r, separators=(",", ":"), ensure_ascii=True)
                          for r in blk.get("rows", []))
        text = text[:-2] + ",\n  \"rows\": [\n" + rows + "\n  ]\n }"
        blocks.append(text)
    top = {k: v for k, v in payload.items() if k != "seasons"}
    out = json.dumps(top, indent=1, ensure_ascii=True)
    body = ",\n".join(blocks)
    return out[:-2] + ",\n \"seasons\": [\n" + body + "\n ]\n}\n"


def write_payload(payload: dict, path: Path = OUT_PATH) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps_payload(payload), encoding="utf-8")
    return p


def season_block(payload: dict, season: int) -> dict | None:
    for blk in payload.get("seasons", []):
        if int(blk.get("season", -1)) == int(season):
            return blk
    return None


def status(payload: dict, season: int, mlbam: int) -> dict | None:
    """The downstream lookup: {'eligible', 'reason', 'prior_ab', 'prior_ip',
    'proxy_days', 'near_45_day_line'} for one player-season; a player over the at-bat or
    innings line is not in the pool and comes back ineligible with that reason; None when
    the season block is missing."""
    blk = season_block(payload, season)
    if blk is None:
        return None
    for r in blk.get("rows", []):
        if int(r[0]) == int(mlbam):
            return {"eligible": bool(r[4]), "reason": r[5], "prior_ab": r[1],
                    "prior_ip": r[2], "proxy_days": r[3],
                    "near_45_day_line": near_45_day_line(r[3])}
    return {"eligible": False,
            "reason": f"prior at-bats over {PRIOR_AB_MAX} or prior innings over "
                      f"{PRIOR_IP_MAX:g} through {season - 1} (not in the pool)",
            "prior_ab": None, "prior_ip": None, "proxy_days": None,
            "near_45_day_line": False}


def parse_seasons(text: str) -> list[int]:
    out = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seasons", default="2011-2026", help="e.g. 2011-2026 or 2024,2026")
    ap.add_argument("--write", action="store_true", help="write the labs file")
    ap.add_argument("--rebuild-season", type=int, default=None,
                    help="rewrite this one season block (needs --reason)")
    ap.add_argument("--reason", default=None, help="why the block is rebuilt; lands in it")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    ap.add_argument("--statsapi-first", type=int, default=STATSAPI_FIRST_SEASON,
                    help="test seam: first StatsAPI season line read (the real build: 2000)")
    ap.add_argument("--tx-first", default=f"{TX_FIRST[0]}-{TX_FIRST[1]:02d}",
                    help="test seam: first transaction month read, YYYY-MM (the real build: 2008-01)")
    args = ap.parse_args(argv)

    cache_dir = Path(args.cache_dir)
    statsapi_first = int(args.statsapi_first)
    tx_first = (int(args.tx_first[:4]), int(args.tx_first[5:7]))
    seasons = parse_seasons(args.seasons)
    if args.rebuild_season is not None:
        if not args.reason:
            print("--rebuild-season needs --reason", file=sys.stderr)
            return 2
        if args.rebuild_season not in seasons:
            seasons = sorted(set(seasons) | {args.rebuild_season})
    refusals = []
    for s in seasons:
        refusals.extend(check_inputs(cache_dir, s, statsapi_first=statsapi_first,
                                     tx_first=tx_first))
    if refusals:
        for r in refusals:
            print("REFUSED: " + r, file=sys.stderr)
        return 2

    payload = load_payload(Path(args.out))
    todo = [s for s in seasons
            if season_block(payload, s) is None or s == args.rebuild_season]
    kept = [s for s in seasons if s not in todo]
    if kept:
        print(f"kept as written: {', '.join(str(s) for s in kept)}")
    if todo:
        last = (max(todo) - 1, 12)
        print(f"loading transactions {tx_first[0]}-{tx_first[1]:02d}..{last[0]}-{last[1]:02d}",
              flush=True)
        events = load_events(cache_dir, last, tx_first)
        table = opening_day_table(cache_dir, range(tx_first[0], max(todo)))
        for s in todo:
            blk = build_season(s, cache_dir, events=events, opening_table=table,
                               statsapi_first=statsapi_first, tx_first=tx_first)
            if s == args.rebuild_season and season_block(payload, s) is not None:
                old = season_block(payload, s)
                blk["rebuilt"] = {"at": blk["built_at"], "reason": args.reason,
                                  "previous_built_at": old.get("built_at")}
            payload["seasons"] = [b for b in payload["seasons"] if int(b["season"]) != s] + [blk]
            payload["seasons"].sort(key=lambda b: int(b["season"]))
            print(f"{s}: line {blk['n_players_with_line']}, over lines {blk['n_over_lines']}, "
                  f"pool {blk['n_pool']}, eligible {blk['n_eligible']}, "
                  f"days only {blk['n_days_only']}")
    if args.write:
        p = write_payload(payload, Path(args.out))
        print(f"wrote {p} ({p.stat().st_size} bytes, {len(payload['seasons'])} seasons)")
    elif todo:
        print("dry run; pass --write to write the file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
