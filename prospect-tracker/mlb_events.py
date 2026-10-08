# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB events: dated transaction history keyed by mlbam (wiring W01, part 1 of 3).

WHAT THIS BUILDS. One row per (person, date, type code) from four sources:

  StatsAPI   the league-wide transaction cache .cache/mlb_transactions/
             tx_YYYY_MM.json.gz (2008-01 on; the same files efv_drivers.py and
             tools/backfill_mlb_transactions.py read), MLB-club rows only (toTeam
             or fromTeam is one of the 30 clubs).
  IL         placements and activations parsed out of the StatsAPI SC rows with
             the rules tools/pt_risk_lab.py used to reconstruct il_table.json, so
             the per-player IL days here reconcile with that table's stints.
  arb        data/arb_history.json actual salaries of arbitration-eligible
             seasons (season-dated: the file carries no hearing or settlement date).
  FA         the fa_events ledger (signings with terms, option decisions, QOs),
             served rows only (quarantined rows never leave the database), joined
             to mlbam through data/player_links.json byKey.

The StatsAPI description string is copied verbatim into `desc` and never
re-voiced. No availability forecast rides on the IL history (the IL playing-time
adjustment failed on both sides, data/fa_pt_risk_eval.json w1b.verdict), and no
medical field is derived beyond the list named in the description.

TYPE CODES are the vocabulary of the site-pass plan section 3.2 (LANE_HOME 2.2):
callup (SE), recall (CU), optioned (OPT), dfa (DES), outright (OUT), claim (CLW),
release (REL), retire (RET), suspend (SU), rule5 (R5, R5M), trade (TR),
fa_sign (SFA without "minor league contract"; fa_events signing), minor_deal (SFA
"to a minor league contract"; an SGN of a player in no draft file), draft_sign
(SGN of a drafted player), il_place and il_return (SC), opt_declined,
opt_exercised and qo (fa_events). arb_salary (arb_history.json) is the one code
the plan does not list; it never reaches recent.json because it has no date.

DEDUPLICATION, in order. (1) A cache row repeated on the same (transaction id,
person) is dropped: one StatsAPI transaction id is ONE DEAL and carries one row
per person in it (a trade of three players is three rows on one id), so a drop
by transaction id alone would delete real players; the id is kept as the trade's
`deal`. (2) One row per (mlbam, date, type code): a second StatsAPI row on the
same key is folded into the first (`tx_more`, `desc_more`). (3) An fa_events
signing absorbs a StatsAPI fa_sign of the same player within 3 days.

DARK AND SERVED PATHS. While MLB_EVENTS_LIVE is False (this module holds the one
definition) everything is written under .cache/mlb_events/preview/ and nothing
under data/. The flip (task Q9_22c) sets the flag and the same writer fills
data/mlb_events/ (gitignored; shipped by the /data/mlb_events/*** include in
deploy/nightly-build.sh and the CI staging step).

Files: <mlbam>.json per MLB player page (the players of mlb_player_detail.json),
index.json (counts, window, per-season MLB IL placements) and recent.json (every
MLB-club row of the last RECENT_DAYS days, all players, for the homepage rail).

Run:  python mlb_events.py              (build from the cache on disk)
      python mlb_events.py --refresh    (refresh the open months first, then build)
"""
from __future__ import annotations

import argparse
import calendar
import gzip
import json
import os
import re
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TX_DIR = ROOT / ".cache" / "mlb_transactions"
DRAFT_DIR = ROOT / ".cache" / "draft_history"

#: THE flag. False: write only under PREVIEW_DIR. Flipped by Q9_22c in one commit.
MLB_EVENTS_LIVE = False
PREVIEW_DIR = ROOT / ".cache" / "mlb_events" / "preview"
SERVED_DIR = DATA / "mlb_events"

SCHEMA = 1
PRODUCED_BY = "mlb_events.py"
TX_FIRST = (2008, 1)
RECENT_DAYS = 35
#: fa_events signing absorbs a StatsAPI fa_sign within this many days.
FA_ABSORB_DAYS = 3
#: Nightly refresh: the previous and current month every night (2 calls); a
#: missing month, or one fetched while it was still open, inside the look-back is
#: refetched too, newest first, up to the cap (the first night after a gap only).
REFRESH_LOOKBACK_MONTHS = 12
REFRESH_MAX_CALLS = 6
URL = ("https://statsapi.mlb.com/api/v1/transactions"
       "?startDate={y}-{m:02d}-01&endDate={y}-{m:02d}-{d:02d}")

#: The 30 MLB clubs' StatsAPI team ids, the fallback when
#: .cache/mlb_transactions/mlb_teams.json is absent (awards_rookies.MLB_TEAM_IDS).
MLB_TEAM_IDS = frozenset(range(108, 122)) | frozenset(range(133, 148)) | frozenset({158})

#: StatsAPI typeCode to type code (codes not listed here, and SC, SFA and SGN,
#: are classified in classify()).
CODE_TYPES = {
    "SE": "callup", "CU": "recall", "OPT": "optioned", "DES": "dfa",
    "OUT": "outright", "CLW": "claim", "REL": "release", "RET": "retire",
    "SU": "suspend", "R5": "rule5", "R5M": "rule5", "TR": "trade",
}
FA_EVENT_TYPES = {"signing": "fa_sign", "option_declined": "opt_declined",
                  "option_exercised": "opt_exercised", "qo_offered": "qo"}
TYPE_CODES = frozenset(CODE_TYPES.values()) | frozenset(FA_EVENT_TYPES.values()) | {
    "fa_sign", "minor_deal", "draft_sign", "il_place", "il_return", "arb_salary"}

# IL parse rules, tools/pt_risk_lab.py header note 3 (the il_table.json rules).
IL_WORDS = ("injured list", "disabled list")
ACT_WORDS = ("activated", "reinstated", "returned")
_IL_LIST = re.compile(r"(\d+)[- ]day (injured|disabled) list")


def _season_window(year: int) -> tuple[date, date]:
    """The IL day-count window of tools/pt_risk_lab.py (header note 4)."""
    if year == 2020:
        return date(2020, 7, 23), date(2020, 9, 28)
    return date(year, 4, 1), date(year, 10, 1)


def il_list(desc: str) -> str:
    """The list a StatsAPI IL row names, as printed in its description."""
    low = desc.lower()
    m = _IL_LIST.search(low)
    if m:
        return f"{m.group(1)}-day {'IL' if m.group(2) == 'injured' else 'DL'}"
    if "covid" in low:
        return "COVID-19 IL"
    return "IL" if "injured list" in low else "DL"


def output_dir() -> Path:
    """Where the builder writes: data/mlb_events/ only when the flag is on."""
    return SERVED_DIR if MLB_EVENTS_LIVE else PREVIEW_DIR


# ---------------------------------------------------------------------------
# the cache
# ---------------------------------------------------------------------------

def tx_path(y: int, m: int, tx_dir: Path = TX_DIR) -> Path:
    return Path(tx_dir) / f"tx_{int(y)}_{int(m):02d}.json.gz"


def _months(first: tuple[int, int], last: tuple[int, int]):
    y, m = first
    while (y, m) <= last:
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def _shift(ym: tuple[int, int], k: int) -> tuple[int, int]:
    i = ym[0] * 12 + (ym[1] - 1) + k
    return i // 12, i % 12 + 1


def cache_months(tx_dir: Path = TX_DIR) -> list[tuple[int, int]]:
    out = []
    for p in Path(tx_dir).glob("tx_*_*.json.gz"):
        m = re.fullmatch(r"tx_(\d{4})_(\d{2})\.json\.gz", p.name)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return sorted(out)


def mlb_team_ids(tx_dir: Path = TX_DIR) -> frozenset:
    p = Path(tx_dir) / "mlb_teams.json"
    try:
        ids = frozenset(int(i) for i in json.loads(p.read_text(encoding="utf-8")))
        return ids or MLB_TEAM_IDS
    except (OSError, ValueError, TypeError):
        return MLB_TEAM_IDS


def months_to_refresh(as_of: date, tx_dir: Path = TX_DIR,
                      cap: int = REFRESH_MAX_CALLS) -> list[tuple[int, int]]:
    """Previous and current month always; inside the look-back, a missing month or
    one whose file was written on or before its own last day (fetched while open).
    Months before the first one on disk are never fetched here (that is the
    backfill tools' job). Newest first, at most `cap`."""
    cur = (as_of.year, as_of.month)
    want = [cur, _shift(cur, -1)]
    on_disk = cache_months(tx_dir)
    first = max(TX_FIRST, on_disk[0]) if on_disk else cur
    for k in range(2, REFRESH_LOOKBACK_MONTHS + 1):
        y, m = _shift(cur, -k)
        if (y, m) < first:
            break
        p = tx_path(y, m, tx_dir)
        if not p.exists():
            want.append((y, m))
            continue
        written = datetime.fromtimestamp(p.stat().st_mtime).date()
        if written <= date(y, m, calendar.monthrange(y, m)[1]):
            want.append((y, m))
    return want[:max(0, int(cap))]


def _get_json(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eephus-mlb-events"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2.0 * (i + 1))
    return None


def refresh(as_of: date | None = None, *, tx_dir: Path = TX_DIR, fetch=None,
            cap: int = REFRESH_MAX_CALLS, log_fn=print) -> dict:
    """Refetch the open months into the cache. A month is replaced atomically and
    only when the new payload carries a transactions list at least as long as the
    file on disk (a short read never shrinks a month). Zero credits: StatsAPI is
    keyless."""
    as_of = as_of or date.today()
    fetch = fetch or _get_json
    tx_dir = Path(tx_dir)
    tx_dir.mkdir(parents=True, exist_ok=True)
    out = {"calls": 0, "written": [], "kept": [], "failed": [], "rows": 0}
    for y, m in months_to_refresh(as_of, tx_dir, cap):
        if (y, m) > (as_of.year, as_of.month):
            continue
        last = calendar.monthrange(y, m)[1]
        url = URL.format(y=y, m=m, d=last)
        out["calls"] += 1
        try:
            doc = fetch(url)
        except Exception as e:  # noqa: BLE001
            out["failed"].append(f"{y}-{m:02d}: {e}"[:160])
            continue
        rows = (doc or {}).get("transactions") if isinstance(doc, dict) else None
        if not isinstance(rows, list):
            out["failed"].append(f"{y}-{m:02d}: no transactions list")
            continue
        p = tx_path(y, m, tx_dir)
        if p.exists():
            try:
                with gzip.open(p, "rt", encoding="utf-8") as fh:
                    old = len(json.load(fh).get("transactions") or [])
            except (OSError, ValueError):
                old = 0
            if len(rows) < old:
                out["kept"].append(f"{y}-{m:02d}: {len(rows)} < {old} on disk")
                continue
        tmp = p.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(doc, fh)
        tmp.replace(p)
        out["written"].append(f"{y}-{m:02d}")
        out["rows"] += len(rows)
        log_fn(f"mlb_events refresh {y}-{m:02d}: {len(rows)} transactions")
    return out


# ---------------------------------------------------------------------------
# sources other than the cache
# ---------------------------------------------------------------------------

def _read_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_draft(draft_dir: Path = DRAFT_DIR) -> dict[int, frozenset]:
    """{draft year: mlbam ids picked} from .cache/draft_history/<year>.json."""
    out = {}
    for p in Path(draft_dir).glob("*.json"):
        if not re.fullmatch(r"\d{4}", p.stem):
            continue
        rows = _read_json(p) or []
        out[int(p.stem)] = frozenset(int(r["mlbam"]) for r in rows
                                     if isinstance(r, dict) and r.get("mlbam"))
    return out


def load_players(path: Path = DATA / "mlb_player_detail.json") -> dict[int, dict]:
    """{mlbam: {key, name}} for every MLB player page."""
    doc = _read_json(path) or {}
    out = {}
    for key, p in (doc.get("players") or {}).items():
        if isinstance(p, dict) and p.get("mlbam"):
            out[int(p["mlbam"])] = {"key": p.get("key") or key, "name": p.get("name")}
    return out


def load_links(path: Path = DATA / "player_links.json") -> dict[str, int]:
    doc = _read_json(path) or {}
    return {k: int(v["mlbam"]) for k, v in (doc.get("byKey") or {}).items()
            if isinstance(v, dict) and v.get("mlbam")}


def load_arb(path: Path = DATA / "arb_history.json") -> list[list]:
    return list((_read_json(path) or {}).get("rows") or [])


def load_fa_events() -> list[dict]:
    """The served fa_events rows (fa_pipeline.served_fa_events: invalidated rows
    stay in the database and never leave it)."""
    try:
        import storage
        return [e for e in storage.load_fa_events() if not e.get("invalidated")]
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def _club(t: dict, side: str):
    return (t.get(side) or {}).get("id")


def il_kind(low: str) -> str | None:
    """il_place or il_return from a lower-case description, by the il_table.json
    rule (tools/pt_risk_lab.py header note 3), whatever the row's typeCode: a
    recall can carry "Placed on the 60-day injured list" in its text."""
    if not any(w in low for w in IL_WORDS):
        return None
    if "placed" in low:
        return "il_place"
    if any(w in low for w in ACT_WORDS):
        return "il_return"
    return None


def classify(t: dict, mlb_ids=MLB_TEAM_IDS, draft: dict | None = None) -> str | None:
    """Type code of one StatsAPI row, or None (not an MLB-club row, or a code the
    vocabulary does not carry: ASG, NUM, DFA, RTN, PUR, SC without an IL list...)."""
    if not ({_club(t, "toTeam"), _club(t, "fromTeam")} & set(mlb_ids)):
        return None
    code = str(t.get("typeCode") or "")
    low = str(t.get("description") or "").lower()
    if code == "SC":
        return il_kind(low)
    if code == "SFA":
        return "minor_deal" if "minor league contract" in low else "fa_sign"
    if code == "SGN":
        day = str(t.get("date") or t.get("effectiveDate") or "")[:10]
        pid = (t.get("person") or {}).get("id")
        if draft is None or not day[:4].isdigit():
            return "draft_sign"
        y = int(day[:4])
        if y not in draft:
            return "draft_sign"
        drafted = any(pid in draft.get(yy, ()) for yy in (y, y - 1))
        return "draft_sign" if drafted else "minor_deal"
    return CODE_TYPES.get(code)


# ---------------------------------------------------------------------------
# the builder
# ---------------------------------------------------------------------------

def _scan_cache(tx_dir: Path, mlb_ids, draft, window_last: date):
    """StatsAPI rows mapped to type codes plus the IL event list, one pass."""
    seen_pair = set()
    il_seen_ids, il_seen_sig = set(), set()
    rows = []
    il_events = defaultdict(list)       # pid -> [(date, kind)] kind P or A
    counts = Counter()
    for y, m in cache_months(tx_dir):
        if (y, m) < TX_FIRST:
            continue
        with gzip.open(tx_path(y, m, tx_dir), "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        for t in doc.get("transactions") or []:
            counts["cache_rows"] += 1
            typ = classify(t, mlb_ids, draft)
            mlb_row = bool({_club(t, "toTeam"), _club(t, "fromTeam")} & set(mlb_ids))
            il_typ = il_kind(str(t.get("description") or "").lower()) if mlb_row else None
            if typ is None and il_typ is None:
                if mlb_row:
                    counts["unmapped:" + str(t.get("typeCode") or "")] += 1
                continue
            person = t.get("person") or {}
            pid = person.get("id")
            if not pid:
                counts["no_person"] += 1
                continue
            day = str(t.get("date") or t.get("effectiveDate") or "")[:10]
            try:
                dt = date.fromisoformat(day)
            except ValueError:
                counts["no_date"] += 1
                continue
            if dt > window_last or dt < date(*TX_FIRST, 1):
                counts["outside_window"] += 1
                continue
            tid = t.get("id")
            desc = str(t.get("description") or "")
            if il_typ is not None:
                # The il_table.json event list: dedupe on transaction id, then on
                # (person, date, first 80 characters), across the whole cache.
                sig = (pid, t.get("date"), desc.lower()[:80])
                if not ((tid is not None and tid in il_seen_ids) or sig in il_seen_sig):
                    if tid is not None:
                        il_seen_ids.add(tid)
                    il_seen_sig.add(sig)
                    il_events[int(pid)].append((dt, "P" if il_typ == "il_place" else "A"))
            pair = (tid, pid)
            if tid is not None and pair in seen_pair:
                counts["dupe_tx_person"] += 1
                continue
            seen_pair.add(pair)
            types = [x for x in (typ, il_typ) if x is not None]
            if len(types) == 2 and types[0] == types[1]:
                types = types[:1]
            elif len(types) == 2:
                counts["il_in_other_code"] += 1
            for x in types:
                r = {"date": day, "type": x, "src": "statsapi", "desc": desc,
                     "tx": tid, "from": _club(t, "fromTeam"), "to": _club(t, "toTeam")}
                if x == "trade":
                    r["deal"] = tid
                if x in ("il_place", "il_return"):
                    r["il"] = il_list(desc)
                rows.append((int(pid), person.get("fullName"), r))
    return rows, il_events, counts


def _stints(il_events: dict, cap: date | None = None) -> tuple[dict, dict, dict]:
    """tools/pt_risk_lab.build_stints on the same event list: {pid: {year:
    [days, stints]}}, per-year placement counts, and each placement's (days, close
    date or None). `cap` (the feed's last day) stops an open stint there, so a
    count made inside a season never includes days not yet played; None keeps the
    il_table.json rule exactly (a stint with no closer runs to its window's end)."""
    il = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    per_year = Counter()
    by_place = {}
    for pid, evs in il_events.items():
        evs.sort()
        for i, (dt, kind) in enumerate(evs):
            if kind != "P":
                continue
            w_lo, w_hi = _season_window(dt.year)
            if cap is not None:
                w_hi = min(w_hi, cap + timedelta(days=1))
            close = w_hi
            closer = None
            for dt2, _k2 in evs[i + 1:]:
                if dt2 > dt:
                    close = min(close, dt2)
                    closer = dt2
                    break
            start = max(dt, w_lo)
            days = max(0, (min(close, w_hi) - start).days) if start <= w_hi else 0
            il[pid][dt.year][0] += days
            il[pid][dt.year][1] += 1
            per_year[dt.year] += 1
            prev = by_place.get((pid, dt))
            by_place[(pid, dt)] = ((prev[0] if prev else 0) + days, closer)
    return ({p: {y: list(v) for y, v in yrs.items()} for p, yrs in il.items()},
            dict(per_year), by_place)


def _fa_rows(fa_events, links):
    out, unjoined = [], 0
    for e in fa_events or []:
        typ = FA_EVENT_TYPES.get(e.get("event_type"))
        mlbam = links.get(e.get("player_key"))
        day = str(e.get("event_date") or "")[:10]
        if not typ or not day:
            continue
        if mlbam is None:
            unjoined += 1
            continue
        r = {"date": day, "type": typ, "src": "fa_class", "key": e.get("player_key")}
        for k in ("from_team", "to_team", "years", "guarantee_usd", "aav_usd",
                  "option_price_usd", "mlb_deal"):
            if e.get(k) is not None:
                r[k] = e[k]
        out.append((mlbam, e.get("player_name"), r))
    return out, unjoined


def _arb_rows(arb):
    out = []
    for row in arb or []:
        try:
            season, mlbam, name, team, arb_year, actual = row[:6]
        except (TypeError, ValueError):
            continue
        if not mlbam or not actual:
            continue
        out.append((int(mlbam), name, {"date": None, "season": int(season),
                                       "type": "arb_salary", "src": "arb",
                                       "club": team, "arb_year": int(arb_year),
                                       "salary_usd": int(actual)}))
    return out


def _sort_key(r: dict):
    return (r.get("date") or f"{r.get('season', 0)}-00-00", r["type"], str(r.get("tx") or ""))


#: How many seasons the /fa/ "IL days, last three seasons" column sums.
IL_RECENT_SEASONS = 3


def il_recent_seasons(as_of: date, n: int = IL_RECENT_SEASONS) -> list[int]:
    """The last `n` seasons that have started by `as_of` (a season starts on
    its IL window's first day, Apr 1; 2020 on Jul 23), oldest first."""
    last = as_of.year if as_of >= _season_window(as_of.year)[0] else as_of.year - 1
    return list(range(last - n + 1, last + 1))


def il_recent(il_events: dict, as_of: date, window_last: date | None) -> dict:
    """{"seasons": [y-2, y-1, y], "days": {mlbam: [d, d, d]}}: in-season IL days
    per season by the il_table.json rule, with an open stint stopped at the
    feed's last day (never a day not yet played). Players with no IL day in the
    three seasons are left out: every MLB-club IL move is in the cache, so a
    player missing here had none."""
    seasons = il_recent_seasons(as_of)
    cap = min(window_last, as_of) if window_last is not None else as_of
    table, _per_year, _by = _stints({p: list(e) for p, e in il_events.items()}, cap=cap)
    days = {}
    for pid, yrs in table.items():
        row = [int((yrs.get(y) or [0, 0])[0]) for y in seasons]
        if any(row):
            days[str(pid)] = row
    return {"seasons": seasons, "rule": "in-season days inside Apr 1 to Oct 1 "
            "(2020: Jul 23 to Sep 28), ended by the next IL move; an open stint "
            "stops at the feed's last day", "days": dict(sorted(days.items(), key=lambda kv: int(kv[0])))}


#: The /history/ MLB rows: trades and major-league free-agent signings.
ON_THIS_DAY_TYPES = ("trade", "fa_sign")


def on_this_day(month: int, day: int, *, before_year: int, tx_dir: Path = TX_DIR,
                mlb_ids=None, types=ON_THIS_DAY_TYPES) -> list[dict]:
    """MLB-club rows of `types` dated `month`-`day` in seasons before
    `before_year`, read from the month files of the cache only (one file per
    season). Same vocabulary and dedupe as build(): a repeated (transaction id,
    person) is dropped and one row is kept per (person, date, type). Newest
    first. Each row: date, type, mlbam, name, from, to, desc (verbatim), tx."""
    tx_dir = Path(tx_dir)
    mlb_ids = frozenset(mlb_ids) if mlb_ids is not None else mlb_team_ids(tx_dir)
    want = set(types)
    out, seen_pair, seen_key = [], set(), set()
    for y, m in cache_months(tx_dir):
        if m != month or y >= before_year or (y, m) < TX_FIRST:
            continue
        try:
            with gzip.open(tx_path(y, m, tx_dir), "rt", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        for t in doc.get("transactions") or []:
            d = str(t.get("date") or t.get("effectiveDate") or "")[:10]
            if len(d) < 10 or int(d[5:7]) != month or int(d[8:10]) != day:
                continue
            typ = classify(t, mlb_ids, None)
            if typ not in want:
                continue
            person = t.get("person") or {}
            pid = person.get("id")
            if not pid:
                continue
            tid = t.get("id")
            if tid is not None:
                if (tid, pid) in seen_pair:
                    continue
                seen_pair.add((tid, pid))
            k = (int(pid), d, typ)
            if k in seen_key:
                continue
            seen_key.add(k)
            out.append({"date": d, "type": typ, "mlbam": int(pid), "name": person.get("fullName"),
                        "from": _club(t, "fromTeam"), "to": _club(t, "toTeam"),
                        "desc": str(t.get("description") or ""), "tx": tid})
    out.sort(key=lambda r: (r["date"], str(r["tx"] or "")), reverse=True)
    return out


def build(*, tx_dir: Path = TX_DIR, as_of: date | None = None, players=None,
          links=None, fa_events=None, arb=None, draft=None, mlb_ids=None) -> dict:
    """Everything the writer needs, in memory. Inputs default to the files on disk."""
    as_of = as_of or date.today()
    tx_dir = Path(tx_dir)
    months = [ym for ym in cache_months(tx_dir) if ym >= TX_FIRST]
    if months:
        ly, lm = months[-1]
        window_last = min(date(ly, lm, calendar.monthrange(ly, lm)[1]), as_of)
        window_first = date(*months[0], 1)
    else:
        window_last = window_first = None
    mlb_ids = frozenset(mlb_ids) if mlb_ids is not None else mlb_team_ids(tx_dir)
    draft = load_draft() if draft is None else draft
    players = load_players() if players is None else players
    links = load_links() if links is None else links
    fa_events = load_fa_events() if fa_events is None else fa_events
    arb = load_arb() if arb is None else arb

    if window_last is not None:
        st_rows, il_events, counts = _scan_cache(tx_dir, mlb_ids, draft, window_last)
    else:
        st_rows, il_events, counts = [], {}, Counter()
    il_table, per_year, by_place = _stints(il_events)
    through = max((r["date"] for _p, _n, r in st_rows), default=None)

    # One row per (mlbam, date, type code).
    keyed: dict[tuple, dict] = {}
    names: dict[int, str] = {}
    for pid, name, r in st_rows:
        if name:
            names.setdefault(pid, name)
        if r["type"] == "il_place":
            days, closer = by_place.get((pid, date.fromisoformat(r["date"])), (0, None))
            r["il_days"] = days
            r["il_end"] = closer.isoformat() if closer else None
        k = (pid, r["date"], r["type"])
        hit = keyed.get(k)
        if hit is None:
            keyed[k] = r
            continue
        counts["folded_same_key"] += 1
        hit.setdefault("tx_more", []).append(r["tx"])
        if r["desc"] != hit["desc"]:
            hit.setdefault("desc_more", []).append(r["desc"])

    fa, unjoined = _fa_rows(fa_events, links)
    counts["fa_unjoined"] = unjoined
    for pid, name, r in fa:
        if name:
            names.setdefault(pid, name)
        if r["type"] == "fa_sign":
            d0 = date.fromisoformat(r["date"])
            for dd in range(-FA_ABSORB_DAYS, FA_ABSORB_DAYS + 1):
                k = (pid, (d0 + timedelta(days=dd)).isoformat(), "fa_sign")
                old = keyed.get(k)
                if old is not None and old.get("src") == "statsapi":
                    r["desc"], r["tx"] = old["desc"], old["tx"]
                    del keyed[k]
                    counts["fa_absorbed_statsapi"] += 1
                    break
        k = (pid, r["date"], r["type"])
        if k in keyed:
            counts["folded_same_key"] += 1
            continue
        keyed[k] = r
    for pid, name, r in _arb_rows(arb):
        if name:
            names.setdefault(pid, name)
        k = (pid, f"season:{r['season']}", r["type"])
        if k not in keyed:
            keyed[k] = r

    by_pid = defaultdict(list)
    for (pid, _d, _t), r in keyed.items():
        by_pid[pid].append(r)

    per_player = {}
    for pid, meta in sorted(players.items()):
        rows = sorted(by_pid.get(pid, []), key=_sort_key)
        il_p = il_table.get(pid) or {}
        per_player[pid] = {
            "schema": SCHEMA, "mlbam": pid, "key": meta.get("key"),
            "name": meta.get("name") or names.get(pid),
            "through": through,
            "il_seasons": {str(y): il_p[y] for y in sorted(il_p)},
            "rows": rows,
        }

    lo = as_of - timedelta(days=RECENT_DAYS - 1)
    recent_rows = []
    for (pid, d, _t), r in keyed.items():
        if not r.get("date") or not (lo.isoformat() <= r["date"] <= as_of.isoformat()):
            continue
        rr = {"mlbam": pid, "name": names.get(pid), "date": r["date"], "type": r["type"],
              "clubs": [c for c in (r.get("from"), r.get("to")) if c is not None],
              "desc": r.get("desc"), "tx": r.get("tx")}
        if (players.get(pid) or {}).get("key"):
            rr["key"] = players[pid]["key"]
        if r.get("from") is not None:
            rr["from"] = r["from"]
        if r.get("to") is not None:
            rr["to"] = r["to"]
        if r["type"] == "trade":
            rr["deal"] = r.get("deal")
        if r.get("il"):
            rr["il"] = r["il"]
        if r.get("src") == "fa_class":
            rr["src"] = "fa_class"
            for k in ("from_team", "to_team", "years", "guarantee_usd", "aav_usd",
                      "option_price_usd"):
                if r.get(k) is not None:
                    rr[k] = r[k]
        recent_rows.append(rr)
    recent_rows.sort(key=lambda x: (x["date"], x["type"], x["tx"] or 0, x["mlbam"]),
                     reverse=True)

    by_type = Counter(r["type"] for r in keyed.values())
    window = {"first": window_first.isoformat() if window_first else None,
              "last": window_last.isoformat() if window_last else None,
              "through": through, "months_on_disk": len(months)}
    index = {
        "schema": SCHEMA, "produced_by": PRODUCED_BY, "live": MLB_EVENTS_LIVE,
        "as_of": as_of.isoformat(), "window": window,
        "n_players": len(per_player),
        "n_player_rows": sum(len(p["rows"]) for p in per_player.values()),
        "n_rows_all": len(keyed),
        "by_type": dict(sorted(by_type.items())),
        "il_placements_by_season": {str(y): per_year[y] for y in sorted(per_year)},
        "il_recent": il_recent(il_events, as_of, window_last),
        "counts": dict(sorted(counts.items())),
        "il_days_rule": ("days of each placement inside its season's Apr 1 to Oct 1 "
                         "window (2020: Jul 23 to Sep 28), closed by the player's next "
                         "IL placement or activation; the il_table.json rule"),
        "players": {str(pid): [len(p["rows"]),
                               max((r["date"] for r in p["rows"] if r.get("date")),
                                   default=None)]
                    for pid, p in per_player.items()},
    }
    recent = {"schema": SCHEMA, "produced_by": PRODUCED_BY, "live": MLB_EVENTS_LIVE,
              "as_of": as_of.isoformat(), "days": RECENT_DAYS, "from": lo.isoformat(),
              "through": through, "n_rows": len(recent_rows), "rows": recent_rows}
    return {"players": per_player, "index": index, "recent": recent,
            "il_table": il_table, "il_per_year": per_year}


# ---------------------------------------------------------------------------
# the writer
# ---------------------------------------------------------------------------

def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _atomic(p: Path, data: bytes) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


def write(result: dict, out_dir: Path | None = None) -> dict:
    """Write <mlbam>.json, index.json and recent.json; remove a stale <mlbam>.json.
    Refuses any directory under data/ while MLB_EVENTS_LIVE is False."""
    out = Path(out_dir) if out_dir is not None else output_dir()
    if not MLB_EVENTS_LIVE:
        try:
            Path(out).resolve().relative_to(DATA.resolve())
        except ValueError:
            pass
        else:
            raise RuntimeError(f"mlb_events: MLB_EVENTS_LIVE is False; refusing to write {out}")
    out.mkdir(parents=True, exist_ok=True)
    keep = set()
    for pid, payload in result["players"].items():
        name = f"{pid}.json"
        keep.add(name)
        _atomic(out / name, _dump(payload))
    removed = 0
    for p in out.glob("*.json"):
        if re.fullmatch(r"\d+\.json", p.name) and p.name not in keep:
            p.unlink()
            removed += 1
    _atomic(out / "index.json", _dump(result["index"]))
    _atomic(out / "recent.json", _dump(result["recent"]))
    return {"dir": str(out), "players": len(keep), "removed": removed,
            "recent_rows": result["recent"]["n_rows"]}


def nightly(*, as_of: date | None = None, tx_dir: Path = TX_DIR, fetch=None,
            out_dir: Path | None = None, log_fn=print, **inputs) -> dict:
    """run_daily step 9e-pre0g: refresh the open months, then build and write.
    A failed refresh still builds from the cache on disk and reports ok False.
    `inputs` pass through to build() (players, links, fa_events, arb, draft)."""
    as_of = as_of or date.today()
    ref = refresh(as_of, tx_dir=tx_dir, fetch=fetch, log_fn=log_fn)
    res = build(tx_dir=tx_dir, as_of=as_of, **inputs)
    wrote = write(res, out_dir)
    idx = res["index"]
    ok = not ref["failed"]
    msg = (f"{'live' if MLB_EVENTS_LIVE else 'preview'}: {ref['calls']} call(s), "
           f"months {','.join(ref['written']) or 'none'} written"
           f"{'; failed ' + '; '.join(ref['failed']) if ref['failed'] else ''}; "
           f"through {idx['window']['through']}; {idx['n_players']} players, "
           f"{idx['n_player_rows']} rows, recent {res['recent']['n_rows']}")
    log_fn("mlb_events: " + msg)
    return {"ok": ok, "message": msg[:200], "n_rows": idx["n_player_rows"],
            "refresh": ref, "write": wrote}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true",
                    help="refresh the open months of the cache before building")
    ap.add_argument("--as-of", default=None, help="build date (YYYY-MM-DD)")
    ap.add_argument("--tx-dir", default=None,
                    help="read (and with --refresh, fill) this copy of the transaction cache")
    a = ap.parse_args(argv)
    as_of = date.fromisoformat(a.as_of) if a.as_of else date.today()
    tx_dir = Path(a.tx_dir) if a.tx_dir else TX_DIR
    if a.refresh:
        print(nightly(as_of=as_of, tx_dir=tx_dir)["message"])
        return 0
    res = build(as_of=as_of, tx_dir=tx_dir)
    print(write(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
