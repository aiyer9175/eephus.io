# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB service time from the transaction history (M10_SERVICE_TIME_ENGINE).

WHY. roster_status.service_years_decimal was read by the debuted-value engine
(storage._build_debuted_payload -> value_framework.debuted_player_value) but no
code ever wrote it, so every graduate was priced as if he had consumed no
control at all. roster_status.active_roster_days is NOT service time (it skips
injured-list days, which DO accrue service, and stops each season on 1
September). This module counts service the way the Basic Agreement does and
validates the count against published service time before anything prices on it.

THE COUNT. A day of the regular season accrues service when the player is on an
MLB club's active roster, on its injured list (any length, 60-day included), on
the paternity, bereavement or family medical emergency list, or designated for
assignment off the active roster. It does not accrue on optional assignment, on
the restricted, suspended or ineligible lists, or off the 40-man. Days count
from Opening Day through the last regular-season day; a season credits at most
172 days (one service year). Two CBA adjustments:
  20-day rule   a player optioned for fewer than 20 days in aggregate in a season
                is credited those days;
  2020          the 67-day season is prorated (each day credits 186/67 days).
Service years decimal = total days / 172, so 5.045 (5 years, 45 days) reads
5 + 45/172 = 5.262.

THE STATE MACHINE. Each player's transactions (the league-wide StatsAPI feed in
.cache/mlb_transactions/tx_<yyyy>_<mm>.json.gz, 2008-01 on, merged by transaction
id with the per-player store in prospects.db player_transactions, which is
fresher for board players) are walked in (date, id) order. A transaction applies
from its own date: the day of a recall counts, the day of an option does not.
  on (counting)  selected / purchased the contract, recalled, activated,
                 reinstated, claimed off waivers, Rule 5 (major league phase),
                 a plain free-agent signing by a player with prior MLB service,
                 all at an MLB club;
  injured list   'placed .* on the .*(injured|disabled) list' and
                 'transferred .* to the .*(injured|disabled) list' at an MLB club
                 (never stats._DEACTIVATING_DESCRIPTORS, which match none of
                 StatsAPI's wording);
  optioned       'optioned' by an MLB club;
  no service     restricted, suspended, ineligible or military list; suspended;
  off            sent outright, released, elected free agency, retired, returned
                 (Rule 5), traded while off the roster;
  unchanged      traded (status carries to the new club), assigned, number
                 changes, paternity and bereavement lists.
Between seasons a player on optional assignment returns to his club's reserve
list (the option ends with the season), so he counts from Opening Day unless the
club options him again in spring.

LIMITS, stated. The feed starts 2008-01, so a player on a roster before then is
flagged window_censored and his total is a floor. The count is as of the last
transaction on disk for that player (service_as_of); a season still in progress
or a feed gap after that date is not counted.

VALIDATION. evaluate() compares the count at the end of each platform season with
the service time MLB Trade Rumors published in its arbitration posts
(data/_labs/arb_ledger.json, class years 2022-2026: service through the end of
season class_year - 1). The tolerance below was written BEFORE the first read and
is applied to the holdout classes only; the development classes were used to
check the state machine. Registry row: service_time.

CLI:
  python service_time.py --eval --write   writes data/service_time_eval.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TX_DIR = ROOT / ".cache" / "mlb_transactions"
GAME_DATES = ROOT / ".cache" / "mgmt_game_dates.json"
WAR_DAILY = ROOT / ".cache" / "war_daily"
ARB_LEDGER = ROOT / "data" / "_labs" / "arb_ledger.json"
EVAL_PATH = ROOT / "data" / "service_time_eval.json"

DAYS_PER_YEAR = 172
OPTION_CREDIT_DAYS = 20
FEED_FIRST = date(2008, 1, 1)
SOURCE = "service_time.py transaction engine"

#: The 30 MLB clubs' StatsAPI team ids (the list awards_rookies.MLB_TEAM_IDS keeps).
MLB_TEAM_IDS = frozenset(range(108, 122)) | frozenset(range(133, 148)) | frozenset({158})

# --- the pre-registered validation design (written before the first read) ----------
#: Classes used while building the state machine (development) and the classes the
#: tolerance is read on (holdout). A class year C carries service through season C-1.
DEV_CLASSES = (2022, 2023, 2024)
HOLDOUT_CLASSES = (2025, 2026)
#: The engine is fit for pricing when, on the holdout, BOTH hold:
TOL_MAE_DAYS = 20.0
TOL_ROUNDED_YEAR_AGREEMENT = 0.90
#: The pricing reads int(round(service_years_decimal)) as consumed control years
#: (value_framework.debuted_player_value), so the second clause is the one that moves
#: a dollar; the first bounds the day count itself.

# --- season calendar -------------------------------------------------------------------
#: Opening Day (the first date with five or more regular-season games: the domestic
#: opener, not an international or single-game opener) and the last regular-season day
#: (tiebreaker games included) from MLB's published schedules, for the years the play
#: corpus does not hold. The corpus (.cache/mgmt_game_dates.json) wins where a year is
#: on disk.
SEASON_TYPED = {
    2008: (date(2008, 3, 31), date(2008, 9, 30)),
    2009: (date(2009, 4, 6), date(2009, 10, 6)),
    2010: (date(2010, 4, 5), date(2010, 10, 3)),
    2011: (date(2011, 3, 31), date(2011, 9, 28)),
    2012: (date(2012, 4, 5), date(2012, 10, 3)),
    2013: (date(2013, 4, 1), date(2013, 9, 30)),
    2014: (date(2014, 3, 31), date(2014, 9, 28)),
    2015: (date(2015, 4, 6), date(2015, 10, 4)),
    2016: (date(2016, 4, 4), date(2016, 10, 2)),
    2017: (date(2017, 4, 3), date(2017, 10, 1)),
    2018: (date(2018, 3, 29), date(2018, 10, 1)),
    2019: (date(2019, 3, 28), date(2019, 9, 29)),
    2020: (date(2020, 7, 23), date(2020, 9, 27)),
    2021: (date(2021, 4, 1), date(2021, 10, 3)),
    2022: (date(2022, 4, 7), date(2022, 10, 5)),
    2023: (date(2023, 3, 30), date(2023, 10, 1)),
    2024: (date(2024, 3, 28), date(2024, 9, 30)),
    2025: (date(2025, 3, 27), date(2025, 9, 28)),
    2026: (date(2026, 3, 26), date(2026, 9, 27)),
}
SEASON_TYPED_SOURCE = "MLB regular-season schedules (domestic Opening Day, last regular-season day)"
#: 2020: each day of the 67-day season credits 186/67 days (the full 186-day schedule
#: prorated), capped at 172 like any season.
SEASON_2020_SCALE = 186.0 / 67.0
MIN_GAMES_OPENING_DAY = 5


@lru_cache(maxsize=1)
def season_calendar() -> dict[int, tuple[date, date]]:
    """{year: (opening_day, last_day)}: the typed table, overridden by the play corpus
    where the corpus holds a full season (2020 always keeps the typed 67-day window)."""
    cal = dict(SEASON_TYPED)
    try:
        raw = json.loads(GAME_DATES.read_text("utf-8"))
    except (OSError, ValueError):
        raw = {}
    by_year: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for iso in raw.values():
        try:
            by_year[int(iso[:4])][iso[:10]] += 1
        except (TypeError, ValueError):
            continue
    for y, counts in by_year.items():
        if y == 2020 or sum(counts.values()) < 2000:
            continue
        opens = sorted(d for d, n in counts.items() if n >= MIN_GAMES_OPENING_DAY)
        if not opens:
            continue
        cal[y] = (date.fromisoformat(opens[0]), date.fromisoformat(max(counts)))
    return cal


# --- transactions ------------------------------------------------------------------------
IL_PLACED_RE = re.compile(r"placed .* on the .*(injured|disabled) list")
IL_TRANSFER_RE = re.compile(r"transferred .* to the .*(injured|disabled) list")
NOSVC_LIST_RE = re.compile(r"placed .* on the .*(restricted|suspended|ineligible|military) list")
ADD_RE = re.compile(r"(selected|purchased) (the )?contract")
MINOR_PHASE_RE = re.compile(r"(aaa|minor league) phase")
ON_RE = re.compile(r"\brecalled\b|\bactivated\b|\breinstated\b")
DFA_RE = re.compile(r"designated .* for assignment")
OFF_RE = re.compile(r"\bsent\b.*\boutright\b|\boutrighted\b|\breleased\b|elected free agency"
                    r"|\bretired\b|\breturned\b.* from ")
CLAIM_RE = re.compile(r"claimed .* off waivers")

COUNTING = frozenset({"active", "il", "dfa_active"})
OPTIONAL = frozenset({"optioned", "dfa_opt"})
ON_40 = COUNTING | OPTIONAL | frozenset({"nosvc"})


def _iso(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _norm_feed(t: dict) -> tuple | None:
    d = _iso(t.get("date"))
    if d is None:
        return None
    return (d, int(t.get("id") or 0), t.get("typeCode") or "",
            (t.get("description") or "").lower(),
            (t.get("fromTeam") or {}).get("id"), (t.get("toTeam") or {}).get("id"))


def _norm_store(t: dict) -> tuple | None:
    d = _iso(t.get("date"))
    if d is None:
        return None
    return (d, int(t.get("id") or 0), t.get("type_code") or "",
            (t.get("description") or "").lower(),
            t.get("from_team_id"), t.get("to_team_id"))


@lru_cache(maxsize=1)
def league_feed() -> tuple[dict[int, list[tuple]], date | None]:
    """({mlbam: [normalized transaction]}, last transaction date on disk)."""
    out: dict[int, list[tuple]] = defaultdict(list)
    last = None
    for f in sorted(TX_DIR.glob("tx_*.json.gz")):
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                rows = json.load(fh).get("transactions") or []
        except (OSError, ValueError):
            continue
        for t in rows:
            pid = (t.get("person") or {}).get("id")
            n = _norm_feed(t)
            if pid is None or n is None:
                continue
            out[int(pid)].append(n)
            if last is None or n[0] > last:
                last = n[0]
    return dict(out), last


def store_from_rows(tx_by_key: dict[str, list[dict]] | None,
                    fetched_by_key: dict[str, str] | None = None
                    ) -> dict[str, tuple[list[tuple], date | None]]:
    """{player_key: ([normalized transaction], fetch date)} from the per-player store
    (storage.load_player_transactions and load_player_transactions_meta)."""
    out: dict[str, tuple[list[tuple], date | None]] = {}
    fetched_by_key = fetched_by_key or {}
    for key, rows in (tx_by_key or {}).items():
        txs = [n for n in (_norm_store(t) for t in rows or [] if isinstance(t, dict)) if n]
        out[key] = (txs, _iso(fetched_by_key.get(key)))
    return out


def _club(tx: tuple) -> int | None:
    """The club acting: the destination where the row has one, else the origin."""
    return tx[5] if tx[5] is not None else tx[4]


def _is_mlb(team_id) -> bool:
    try:
        return int(team_id) in MLB_TEAM_IDS
    except (TypeError, ValueError):
        return False


def step(state: str, tx: tuple, *, had_service: bool) -> str:
    """One transaction -> the player's next state (see the module docstring)."""
    _d, _id, code, desc, frm, to = tx
    club_mlb = _is_mlb(_club(tx))
    from_mlb = _is_mlb(frm)
    if IL_PLACED_RE.search(desc) or IL_TRANSFER_RE.search(desc):
        return "il" if club_mlb else state
    if NOSVC_LIST_RE.search(desc):
        return "nosvc" if club_mlb else state
    if code == "SU" or (desc.endswith("suspended.") and state in COUNTING):
        return "nosvc" if state in ON_40 else state
    if ADD_RE.search(desc):
        if MINOR_PHASE_RE.search(desc) or code == "R5M":
            return state
        return "active" if club_mlb else state
    if code == "OPT" or " optioned " in f" {desc} ":
        return "optioned" if (from_mlb or club_mlb) and not _is_minor_to_minor(tx) else state
    if DFA_RE.search(desc):
        if not club_mlb:
            return state
        return "dfa_opt" if state in OPTIONAL else "dfa_active"
    if CLAIM_RE.search(desc):
        return "active" if _is_mlb(to) or club_mlb else state
    if OFF_RE.search(desc):
        return "none"
    if code == "TR" or " traded " in f" {desc} ":
        if state == "dfa_active":
            return "active"
        if state == "dfa_opt":
            return "optioned"
        return state if _is_mlb(to) or state == "none" else "none"
    if ON_RE.search(desc):
        return "active" if club_mlb else state
    # A plain signing by a player with prior service is a major league contract,
    # except the generic-position duplicate StatsAPI writes beside a minor league
    # deal ("signed free agent p <name>."), which is not.
    if (code == "SFA" and club_mlb and "minor league" not in desc and had_service
            and "free agent p " not in desc):
        return "active"
    return state


def _is_minor_to_minor(tx: tuple) -> bool:
    return tx[4] is not None and not _is_mlb(tx[4]) and tx[5] is not None and not _is_mlb(tx[5])


def count(events: list[tuple], as_of: date) -> dict:
    """Walk one player's merged transactions through `as_of` (inclusive).

    Returns {total_days, by_season {year: credited days}, years, days, decimal,
    as_of, window_censored}."""
    cal = season_calendar()
    seen: set = set()
    evs = []
    for e in sorted(events, key=lambda e: (e[0], e[1])):
        k = e[1] or (e[0], e[3])
        if k in seen:
            continue
        seen.add(k)
        if e[0] <= as_of:
            evs.append(e)
    counted: dict[int, int] = defaultdict(int)
    optioned: dict[int, int] = defaultdict(int)
    state = "none"
    censored = False
    first_member = None

    def accrue(st: str, start: date, end_excl: date) -> None:
        if end_excl <= start or not (st in COUNTING or st in OPTIONAL):
            return
        for y in range(start.year, end_excl.year + 1):
            b = cal.get(y)
            if not b:
                continue
            lo = max(start, b[0])
            hi = min(end_excl, b[1] + timedelta(days=1))
            n = (hi - lo).days
            if n <= 0:
                continue
            if st in COUNTING:
                counted[y] += n
            else:
                optioned[y] += n

    cursor = None
    for e in evs:
        if cursor is not None:
            # Season rollover: an option ends with the season, so a player still on
            # optional assignment on 1 January is back on his club's reserve list.
            while cursor.year < e[0].year:
                jan1 = date(cursor.year + 1, 1, 1)
                accrue(state, cursor, jan1)
                cursor = jan1
                if state in OPTIONAL:
                    state = "active"
            accrue(state, cursor, e[0])
        had = bool(counted) or state in ON_40
        nxt = step(state, e, had_service=had)
        if first_member is None and nxt in ON_40 and state not in ON_40:
            first_member = e
            # Joined by a move that presumes he was already on a 40-man (an option,
            # an injured list placement, an activation or a DFA) at the start of the
            # feed: his earlier service is not on disk.
            if e[0] < date(2009, 1, 1) and not ADD_RE.search(e[3]):
                censored = True
        state = nxt
        cursor = e[0]
    if cursor is not None:
        end = as_of + timedelta(days=1)
        while cursor.year < end.year:
            jan1 = date(cursor.year + 1, 1, 1)
            accrue(state, cursor, min(jan1, end))
            cursor = jan1
            if state in OPTIONAL:
                state = "active"
        if cursor < end:
            accrue(state, cursor, end)
    by_season: dict[int, int] = {}
    for y in sorted(set(counted) | set(optioned)):
        days = counted.get(y, 0)
        opt = optioned.get(y, 0)
        if 0 < opt < OPTION_CREDIT_DAYS:
            days += opt
        if y == 2020:
            days = round(days * SEASON_2020_SCALE)
        days = min(DAYS_PER_YEAR, days)
        if days > 0:
            by_season[y] = days
    total = sum(by_season.values())
    yrs, rem = divmod(total, DAYS_PER_YEAR)
    return {
        "total_days": total,
        "by_season": by_season,
        "years": yrs,
        "days": rem,
        "decimal": round(total / DAYS_PER_YEAR, 3),
        "as_of": as_of.isoformat(),
        "window_censored": censored,
        "on_40_man": state in ON_40,
    }


def token(total_days: int) -> str:
    """5 years 45 days -> '5.045' (the published notation; days are not a fraction)."""
    y, d = divmod(int(total_days), DAYS_PER_YEAR)
    return f"{y}.{d:03d}"


# --- serving --------------------------------------------------------------------------------
def roster_fields(mlbam: int | None, store_events: list[tuple] | None = None,
                  store_fetched: date | None = None) -> dict | None:
    """The roster_status fields for one player: the league feed for this id merged with
    his per-player store rows, counted through the later of the feed's last day and
    the store's fetch date. None without an id or without any MLB service history."""
    if not mlbam:
        return None
    feed, feed_last = league_feed()
    evs = list(feed.get(int(mlbam)) or []) + list(store_events or [])
    if not evs:
        return None
    ends = [d for d in (feed_last, store_fetched) if d is not None]
    as_of = max(ends) if ends else max(e[0] for e in evs)
    c = count(evs, as_of)
    if not c["by_season"] and not c["on_40_man"]:
        return None
    return {
        "service_days": c["total_days"],
        "service_years_decimal": c["decimal"],
        "service_time": token(c["total_days"]),
        "service_by_season": {str(k): v for k, v in c["by_season"].items()},
        "service_as_of": c["as_of"],
        "service_window_censored": c["window_censored"],
        "service_source": SOURCE,
    }


def overlay_roster_status(roster_status: dict[str, dict], ids_by_key: dict[str, int],
                          store: dict | None = None) -> tuple[dict[str, dict], dict]:
    """A copy of {player_key: roster_status} with the service fields written for every
    key that has an mlbam id and a service history (`store` from store_from_rows).
    Returns (copy, receipt)."""
    store = store or {}
    out = dict(roster_status or {})
    n = 0
    for key, mid in (ids_by_key or {}).items():
        evs, fetched = store.get(key, ([], None))
        f = roster_fields(mid, evs, fetched)
        if not f:
            continue
        rec = dict(out.get(key) or {})
        rec.update(f)
        out[key] = rec
        n += 1
    return out, {"keys_with_ids": len(ids_by_key or {}), "service_written": n}


# --- validation -------------------------------------------------------------------------------
def _bbref_to_mlbam() -> dict[str, int]:
    import pandas as pd
    out: dict[str, int] = {}
    for side in ("bat", "pit"):
        p = WAR_DAILY / f"{side}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p, columns=["mlb_ID", "player_ID"]).dropna().drop_duplicates()
        for mid, bid in zip(df["mlb_ID"], df["player_ID"]):
            try:
                out.setdefault(str(bid), int(mid))
            except (TypeError, ValueError):
                continue
    return out


def published_rows() -> tuple[list[dict], dict]:
    """One row per (mlbam, class_year) with MLBTR's published service time."""
    doc = json.loads(ARB_LEDGER.read_text("utf-8"))
    b2m = _bbref_to_mlbam()
    by: dict[tuple[int, int], dict] = {}
    conflicts = unresolved = 0
    for e in doc.get("entries") or []:
        if e.get("service_years") is None:
            continue
        mid = e.get("mlbam") or b2m.get(str(e.get("bbref_id") or ""))
        if not mid:
            unresolved += 1
            continue
        k = (int(mid), int(e["class_year"]))
        tot = int(e["service_years"]) * DAYS_PER_YEAR + int(e.get("service_days") or 0)
        if k in by:
            if by[k]["published_days"] != tot:
                conflicts += 1
                by[k]["conflict"] = True
            continue
        by[k] = {"mlbam": k[0], "class_year": k[1], "name": e.get("player_name"),
                 "published": e.get("service_time"), "published_days": tot,
                 "conflict": False}
    rows = [r for r in by.values() if not r["conflict"]]
    return rows, {"entries": len(doc.get("entries") or []), "unresolved_id": unresolved,
                  "player_class_rows": len(by), "conflicting_dropped": conflicts}


def _metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    err = [r["engine_days"] - r["published_days"] for r in rows]
    ae = [abs(x) for x in err]
    rnd = [int(round(r["engine_days"] / DAYS_PER_YEAR)) == int(round(r["published_days"] / DAYS_PER_YEAR))
           for r in rows]
    yrs = [r["engine_days"] // DAYS_PER_YEAR == r["published_days"] // DAYS_PER_YEAR for r in rows]
    n = len(rows)
    return {
        "n": n,
        "mae_days": round(sum(ae) / n, 2),
        "median_abs_err_days": statistics.median(ae),
        "bias_days": round(sum(err) / n, 2),
        "exact_agreement": round(sum(1 for x in ae if x == 0) / n, 4),
        "within_5_days": round(sum(1 for x in ae if x <= 5) / n, 4),
        "within_10_days": round(sum(1 for x in ae if x <= 10) / n, 4),
        "within_20_days": round(sum(1 for x in ae if x <= 20) / n, 4),
        "same_whole_years": round(sum(yrs) / n, 4),
        "rounded_year_agreement": round(sum(rnd) / n, 4),
        "over_172_days_off": sum(1 for x in ae if x >= DAYS_PER_YEAR),
    }


def evaluate(classes=None) -> dict:
    cal = season_calendar()
    feed, feed_last = league_feed()
    rows, census = published_rows()
    classes = tuple(classes or (DEV_CLASSES + HOLDOUT_CLASSES))
    scored = []
    no_tx = 0
    for r in rows:
        if r["class_year"] not in classes:
            continue
        evs = feed.get(r["mlbam"])
        if not evs:
            no_tx += 1
            continue
        end = cal[r["class_year"] - 1][1]
        c = count(evs, end)
        scored.append({**r, "engine_days": c["total_days"], "engine": token(c["total_days"]),
                       "window_censored": c["window_censored"]})
    dev = [s for s in scored if s["class_year"] in DEV_CLASSES]
    hold = [s for s in scored if s["class_year"] in HOLDOUT_CLASSES]
    mh = _metrics(hold)
    passed = (mh.get("n", 0) > 0 and mh["mae_days"] <= TOL_MAE_DAYS
              and mh["rounded_year_agreement"] >= TOL_ROUNDED_YEAR_AGREEMENT)
    worst = sorted(scored, key=lambda s: -abs(s["engine_days"] - s["published_days"]))[:25]
    return {
        "model_id": "service_time",
        "generated_at": date.today().isoformat(),
        "produced_by": "python service_time.py --eval --write",
        "comparator": ("MLB Trade Rumors published service time (arbitration projection posts "
                       "and trackers, data/_labs/arb_ledger.json), service through the end of "
                       "season class_year - 1"),
        "tolerance": {
            "registered": "written in service_time.py before the first read",
            "applied_to": "holdout classes " + ", ".join(map(str, HOLDOUT_CLASSES)),
            "mae_days_max": TOL_MAE_DAYS,
            "rounded_year_agreement_min": TOL_ROUNDED_YEAR_AGREEMENT,
            "why_rounded_year": ("value_framework.debuted_player_value reads "
                                 "int(round(service years)) as consumed control years"),
        },
        "passed": passed,
        "verdict": "provisional",
        "holdout": mh,
        "development": _metrics(dev),
        "all": _metrics(scored),
        "by_class": {str(c): _metrics([s for s in scored if s["class_year"] == c])
                     for c in classes},
        "census": {**census, "scored": len(scored), "no_transactions_on_disk": no_tx,
                   "window_censored_scored": sum(1 for s in scored if s["window_censored"])},
        "feed": {"first": FEED_FIRST.isoformat(),
                 "last_transaction": feed_last.isoformat() if feed_last else None},
        "calendar_source": {"typed": SEASON_TYPED_SOURCE,
                            "corpus": ".cache/mgmt_game_dates.json where a full season is on disk"},
        # Ids and day errors only: the published figures stay in the off-webroot lab
        # ledger (owner answer M23-3), so this served artifact republishes none of them.
        "largest_misses": [{"mlbam": s["mlbam"], "class_year": s["class_year"],
                            "error_days": s["engine_days"] - s["published_days"]}
                           for s in worst],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    if a.eval:
        doc = evaluate()
        print(json.dumps({k: doc[k] for k in ("passed", "holdout", "development", "census")},
                         indent=1))
        if a.write:
            EVAL_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
            print("wrote", EVAL_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
