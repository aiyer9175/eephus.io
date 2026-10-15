# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV expert program step X2: team revealed-preference columns (EFV_X2_REVEALED_PREFERENCE;
owner EW3-12, 2026-10-15; method fixed before any number in
docs/efv-v2/EFV_X2_REVEALED_PREFERENCE.md).

WHAT THIS BUILDS. Clubs hold private information and their decisions leak it. Fifteen
pre-declared per-player columns (COLUMNS), each read as of the row's own read date and
from nothing dated on or after it:

    promotion   x2_promos_per_season, x2_promo_age_rel, x2_midseason_jumps,
                x2_skipped_levels (MiLB season lines, milb_history, seasons before the
                read's year)
    40-man      x2_add_before_elig, x2_r5_protect, x2_r5_exposed_n, x2_r5_selected,
                x2_r5m_selected (league transaction feed, .cache/mlb_transactions,
                announced strictly before the read; Rule 5 draft days found in the feed)
    decisions   x2_options, x2_release_events, x2_trades, x2_trade_principal_mlb
    spring      x2_nri_springs (non-roster invitee lists, .cache/efv4_nri dated by the
                efv_w2_nri rule, extended to 2026 in .cache/efv_x2_revealed/nri)
    market      x2_bonus_vs_slot (data/draft_bonus_slot.json, 2017 drafts onward)

THE READ. Development frames only: lv_dev (list vintages 2017 to 2019, W3) and vm_dev
(vm2, debut cohorts 2017 to 2023) from tools/efv_v2_model_class_screen.build_inputs, the
builder every eFV development read uses, on the frozen fWAR label. Per fold, OLS of the
training target's percentile on the consensus percentile and the standardized column
(fitted on training rows with a resolved id), then the within (side, vintage) Spearman of
that score minus consensus's (efv_v2_stat.paired_delta, E_cond, player-clustered, B 2000,
seed 20261019), both sides and each side. DESCRIPTIVE inputs for EFV_X3_POOLED_MODEL: the
reading (CARRY, LEAN, NULL) routes columns and ships nothing.

KEYS AND DATES. lv rows read the OUTCOME-BLIND id (efv_identity via the frame row's
mlbam_id, never record_mlbam_id) at the frame row's asof_date; vm rows read the matrix id
(a partial debut proxy, bug B4) at the matrix asof_date (training) or the pinned
preseason read (test). Every value carries the latest date it read; the builder asserts
that date is strictly before the read.

RESERVED FRAMES. Nothing here reads list vintages 2020 and 2021 or the 2025 and later
debut cohorts: check_dev_folds raises on any such fold or row, and the builder's own
guards (efv_vintage_frame) raise first. The 2026 season belongs to EFV_2026_HOLDOUT_READ.

BANS. No served number moves: nothing served imports this module and no flag exists.
Nothing here groups, counts or averages anything by consensus-FV level
(docs/PROSPECT_ANCHOR_GATE.md); the only groups are side and year. No column builder reads
a label, a WAR series or a debut.

Run:  python efv_x2_revealed.py --fetch    (teams and the 2026 NRI lists, cached once)
      python efv_x2_revealed.py --check    (source receipts and coverage, no statistic)
      python efv_x2_revealed.py --read     (the development read; writes the artifact)
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "efv_x2_revealed"
TX_DIR = ROOT / ".cache" / "mlb_transactions"
DRAFT_DIR = ROOT / ".cache" / "draft_history"
BONUS_PATH = DATA_DIR / "draft_bonus_slot.json"
OUT_PATH = DATA_DIR / "_labs" / "efv_x2" / "efv_x2_revealed.json"
TOOL = "efv_x2_revealed.py"
ITEM = "EFV_X2_REVEALED_PREFERENCE"
DOC = "docs/efv-v2/EFV_X2_REVEALED_PREFERENCE.md"
RESULTS_DOC = "docs/efv-v2/EFV_X2_REVEALED_PREFERENCE_RESULTS.md"
NOTE = ("eFV X2 team revealed-preference columns, development read only: descriptive "
        "inputs for EFV_X3, selects and adjudicates nothing")

API = "https://statsapi.mlb.com/api/v1"
#: Registered estimator constants (DOC s4).
B_DEFAULT = 2000
SEED = 20261019
#: Development folds (DOC s2).
LV_DEV_FOLDS: tuple[int, ...] = (2017, 2018, 2019)
FRAMES_DEV: tuple[str, ...] = ("lv_dev", "vm_dev")
SCOPES: tuple[str, ...] = ("both", "hit", "pit")
#: A MiLB level counts in a season with at least this many PA (hitter) or batters faced.
MIN_LINE_VOLUME = 20
#: Level ranks (milb_history._LEVEL_RANK without MLB); A is the first full-season rung.
LEVEL_RANK = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
FULL_SEASON_FIRST = 2
#: Rounds 11 and later: the bonus a club may pay without charge to its pool.
LATE_ROUND_ALLOWANCE = 125000.0
#: The first draft year whose bonus and slot the endpoint carries (draft_bonus).
FIRST_MONEY_YEAR = 2017
#: Rule 5 eligibility: drafts after signing, by age at signing (18 or younger: 5th).
R5_YOUNG_AGE = 18
#: Seasons whose team lists are cached (parent org and level of every club id).
TEAM_SEASONS: tuple[int, ...] = tuple(range(2009, 2027))
TEAM_SPORTS = "1,11,12,13,14,15,16"
#: The NRI seasons this task adds to the efv_w2_nri cache (2009 to 2025 there).
NRI_EXTEND: tuple[int, ...] = (2026,)
PAUSE_S = 0.5
#: A fold fits the column slope only with at least this many training rows with an id.
MIN_FIT_ROWS = 30
#: A December day is the Rule 5 draft day only with at least this many CLW, R5 and R5M
#: transactions; otherwise (the 2023 draft is absent from the feed) the year's draft day
#: is R5_FALLBACK_MMDD, and its selections are read from R5 and R5M codes only.
R5_MIN_EVENTS = 20
R5_FALLBACK_MMDD = "-12-08"

#: Transaction status codes (efv_drivers, the same replay as protection_asof).
ADD = frozenset({"SE", "R5", "CLW"})
IMPLIED = frozenset({"OPT", "CU"})
REMOVE = frozenset({"OUT", "REL", "DES", "DFA", "RET", "RTN", "R5M"})
SIGNINGS = frozenset({"SGN", "SFA"})
MLB_CONTRACT = "major league contract"
RELEASE_CODES = frozenset({"REL", "DES", "OUT"})
R5_DAY_CODES = frozenset({"CLW", "R5", "R5M"})

COLUMNS: dict[str, dict] = {
    "x2_promos_per_season": {"family": "promotion", "text": (
        "arrivals at a level above every level reached before, per season with a line")},
    "x2_promo_age_rel": {"family": "promotion", "text": (
        "mean over arrivals of season age minus the median age at that level and season")},
    "x2_midseason_jumps": {"family": "promotion", "text": (
        "levels beyond the first inside a season, per season with a line")},
    "x2_skipped_levels": {"family": "promotion", "text": (
        "full-season levels jumped over at an arrival from a full-season level")},
    "x2_add_before_elig": {"family": "forty_man", "text": (
        "1 when the first 40-man add came before the first eligible Rule 5 draft day")},
    "x2_r5_protect": {"family": "forty_man", "text": (
        "+1 on the 40-man, -1 exposed, at the latest eligible Rule 5 draft day; 0 none yet")},
    "x2_r5_exposed_n": {"family": "forty_man", "text": (
        "eligible Rule 5 draft days at which he was exposed")},
    "x2_r5_selected": {"family": "forty_man", "text": (
        "1 when taken in the major league phase of a Rule 5 draft")},
    "x2_r5m_selected": {"family": "forty_man", "text": (
        "1 when taken in the minor league phase of a Rule 5 draft")},
    "x2_options": {"family": "decisions", "text": "option transactions"},
    "x2_release_events": {"family": "decisions", "text": (
        "releases, designations for assignment and outrights")},
    "x2_trades": {"family": "decisions", "text": "trades naming him"},
    "x2_trade_principal_mlb": {"family": "decisions", "text": (
        "1 when one of at most two players his club sent for a return holding a "
        "major leaguer")},
    "x2_nri_springs": {"family": "spring", "text": (
        "distinct springs on a big-league non-roster invitee list")},
    "x2_bonus_vs_slot": {"family": "market", "text": (
        "log of signing bonus over slot (rounds 11 and later: over 125,000 dollars)")},
}
JOINT = "x2_all"


# ---------------------------------------------------------------------------
# fetch (teams and the 2026 non-roster invitee lists), polite and cached once
# ---------------------------------------------------------------------------

def fetch_window_open(now: datetime | None = None) -> bool:
    """False between 06:00 and 11:00 UTC (the nightly fetch window)."""
    import efv_w2_nri as NRI
    return NRI.fetch_window_open(now)


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(path)


def teams_path(season: int) -> Path:
    return CACHE_DIR / "teams" / f"teams_{int(season)}.json"


def nri_path(season: int, club: int) -> Path:
    return CACHE_DIR / "nri" / f"nri_{int(season)}_{int(club)}.json"


def fetch(*, log=print) -> dict:
    """Fill .cache/efv_x2_revealed: one teams list per season (every affiliated sport) and
    the NRI_EXTEND non-roster invitee lists of the 30 clubs. A cached file is final."""
    import efv_w2_nri as NRI
    out = {"calls": 0, "cached": 0}
    for season in TEAM_SEASONS:
        p = teams_path(season)
        if p.exists():
            out["cached"] += 1
            continue
        url = f"{API}/teams?sportIds={TEAM_SPORTS}&season={int(season)}"
        doc = NRI._get(url)
        doc["_url"] = url
        doc["_fetched_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write(p, doc)
        out["calls"] += 1
        time.sleep(PAUSE_S)
    log(f"  teams {TEAM_SEASONS[0]} to {TEAM_SEASONS[-1]}: cached")
    for season in NRI_EXTEND:
        for club in sorted(mlb_club_ids(season)):
            p = nri_path(season, club)
            if p.exists():
                out["cached"] += 1
                continue
            url = (f"{API}/teams/{club}/roster?rosterType=nonRosterInvitees"
                   f"&season={int(season)}&date={int(season)}-03-01")
            doc = NRI._get(url)
            doc["_url"] = url
            doc["_fetched_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _write(p, doc)
            out["calls"] += 1
            time.sleep(PAUSE_S)
        log(f"  nri {season}: cached")
    return out


# ---------------------------------------------------------------------------
# source books (read-only)
# ---------------------------------------------------------------------------

_TEAMS: dict[int, dict[int, tuple[int, int]]] | None = None


def load_teams() -> dict[int, dict[int, tuple[int, int]]]:
    """{season: {team id: (sport id, parent org id)}} from the cached team lists."""
    global _TEAMS
    if _TEAMS is None:
        out: dict[int, dict[int, tuple[int, int]]] = {}
        for season in TEAM_SEASONS:
            p = teams_path(season)
            if not p.exists():
                continue
            m = {}
            for t in json.loads(p.read_text(encoding="utf-8")).get("teams") or []:
                sport = int((t.get("sport") or {}).get("id") or 0)
                org = int(t.get("parentOrgId") or t["id"]) if sport != 1 else int(t["id"])
                m[int(t["id"])] = (sport, org)
            out[season] = m
        _TEAMS = out
    return _TEAMS


def team_info(team_id, season: int, teams: dict | None = None) -> tuple[int, int] | None:
    """(sport id, parent org id) of a club id in a season, else the nearest season that
    lists it, else None."""
    if team_id is None:
        return None
    tm = load_teams() if teams is None else teams
    tid = int(team_id)
    if tid in (tm.get(int(season)) or {}):
        return tm[int(season)][tid]
    for s in sorted(tm, key=lambda s: abs(int(s) - int(season))):
        if tid in tm[s]:
            return tm[s][tid]
    return None


def mlb_club_ids(season: int) -> frozenset[int]:
    """The major league club ids of a season (teams cache, else the NRI teams file)."""
    tm = load_teams().get(int(season))
    if tm:
        return frozenset(t for t, (sport, _org) in tm.items() if sport == 1)
    import efv_w2_nri as NRI
    return frozenset(NRI.clubs(season, fetch=True))


def tx_path(year: int, month: int) -> Path:
    return TX_DIR / f"tx_{int(year)}_{int(month):02d}.json.gz"


class TxBook:
    """The league transaction feed as read here: per person, oldest first,
    (announced day, code, description, from team, to team, transaction id); the trades
    by transaction id; the Rule 5 draft day of each year."""

    def __init__(self, events: dict[int, list[tuple]], trades: dict[int, list[tuple]],
                 r5_days: dict[int, str], months: list[str]):
        self.events = events
        self.trades = trades
        self.r5_days = r5_days
        self.months = months

    @classmethod
    def load(cls, last_year: int, tx_dir: Path = TX_DIR) -> "TxBook":
        events: dict[int, list[tuple]] = {}
        trades: dict[int, list[tuple]] = {}
        dec: dict[int, dict[str, int]] = {}
        months = []
        for y in range(2008, int(last_year) + 1):
            for m in range(1, 13):
                p = Path(tx_dir) / f"tx_{y}_{m:02d}.json.gz"
                if not p.exists():
                    continue
                months.append(f"{y}-{m:02d}")
                with gzip.open(p, "rt", encoding="utf-8") as fh:
                    doc = json.load(fh)
                for t in doc.get("transactions") or []:
                    day = str(t.get("date") or t.get("effectiveDate") or "")[:10]
                    code = str(t.get("typeCode") or "")
                    if len(day) < 10:
                        continue
                    if code in R5_DAY_CODES and day[5:7] == "12":
                        c = dec.setdefault(int(day[:4]), {})
                        c[day] = c.get(day, 0) + 1
                    pid = (t.get("person") or {}).get("id")
                    if not pid:
                        continue
                    ev = (day, code, str(t.get("description") or "").lower(),
                          (t.get("fromTeam") or {}).get("id"),
                          (t.get("toTeam") or {}).get("id"), t.get("id"))
                    events.setdefault(int(pid), []).append(ev)
                    if code == "TR" and t.get("id") is not None:
                        trades.setdefault(int(t["id"]), []).append((int(pid),) + ev)
        for evs in events.values():
            evs.sort(key=lambda e: (e[0], e[5] or 0))
        r5, detected = {}, {}
        for y in range(2009, int(last_year) + 1):
            best = max((c := dec.get(y, {})).items(), key=lambda kv: (kv[1], kv[0]),
                       default=(None, 0))
            if best[0] is not None and best[1] >= R5_MIN_EVENTS:
                r5[y], detected[y] = best[0], True
            else:
                r5[y], detected[y] = f"{y}{R5_FALLBACK_MMDD}", False
        book = cls(events, trades, r5, months)
        book.r5_detected = detected
        return book


def forty_man_on(evs, day: str) -> bool:
    """On the 40-man at the start of `day`: the latest status-bearing event announced
    strictly before it decides (efv_drivers.protection_asof's replay)."""
    on = False
    for e in evs:
        if e[0] >= day:
            break
        code, desc = e[1], e[2]
        if code in ADD or code in IMPLIED or (code in SIGNINGS and MLB_CONTRACT in desc):
            on = True
        elif code in REMOVE:
            on = False
    return on


def first_add_day(evs, before: str) -> str | None:
    for e in evs:
        if e[0] >= before:
            return None
        if e[1] in ADD or e[1] in IMPLIED or (e[1] in SIGNINGS and MLB_CONTRACT in e[2]):
            return e[0]
    return None


class MilbBook:
    """MiLB season lines per side: {person: {season: [(level rank, age, volume)]}} and
    the median season age of every counted line per (season, level)."""

    def __init__(self, lines: dict[str, dict], medians: dict[tuple, float],
                 first_season: dict[int, int], first_age: dict[int, float]):
        self.lines = lines
        self.medians = medians
        self.first_season = first_season
        self.first_age = first_age

    @classmethod
    def load(cls, seasons) -> "MilbBook":
        import milb_history as mh
        lines: dict[str, dict] = {"hit": {}, "pit": {}}
        ages: dict[tuple, list[float]] = {}
        first: dict[int, int] = {}
        first_age: dict[int, float] = {}
        for side, group, vol in (("hit", "hitting", "pa"), ("pit", "pitching", "bf")):
            for season in seasons:
                for sport in mh.MINOR_SPORTS:
                    for r in mh.season_splits(sport, int(season), group, fetch=False):
                        lvl = LEVEL_RANK.get(str(r.get("level")))
                        pid = r.get("mlbam")
                        if lvl is None or not pid:
                            continue
                        pid = int(pid)
                        age = r.get("age")
                        age = float(age) if age not in (None, "") else None
                        v = int(r.get(vol) or 0)
                        if pid not in first or int(season) < first[pid]:
                            first[pid] = int(season)
                            first_age[pid] = age
                        if v < MIN_LINE_VOLUME:
                            continue
                        lines[side].setdefault(pid, {}).setdefault(int(season), []).append(
                            (lvl, age, v))
                        if age is not None:
                            ages.setdefault((side, int(season), lvl), []).append(age)
        med = {k: float(statistics.median(v)) for k, v in ages.items() if v}
        return cls(lines, med, first, first_age)


def promotion_values(seasons: dict[int, list[tuple]], medians: dict[tuple, float],
                     side: str, before_year: int) -> tuple[dict, str | None]:
    """The four promotion columns from one person's counted lines in seasons before
    `before_year`, and the latest input date (31 December of the last season read)."""
    out = {k: None for k in ("x2_promos_per_season", "x2_promo_age_rel",
                             "x2_midseason_jumps", "x2_skipped_levels")}
    used = sorted(s for s in (seasons or {}) if s < int(before_year))
    if not used:
        return out, None
    top = None
    arrivals: list[float | None] = []
    jumps = skipped = 0
    for s in used:
        by_lvl: dict[int, float | None] = {}
        for lvl, age, _v in seasons[s]:
            by_lvl.setdefault(lvl, age)
        lv = sorted(by_lvl)
        jumps += len(lv) - 1
        for L in lv:
            if top is None:
                top = L
                continue
            if L > top:
                med = medians.get((side, s, L))
                age = by_lvl[L]
                arrivals.append(None if (med is None or age is None) else age - med)
                if top >= FULL_SEASON_FIRST:
                    skipped += max(0, L - top - 1)
                top = L
    n = len(used)
    rel = [a for a in arrivals if a is not None]
    out.update(x2_promos_per_season=len(arrivals) / n,
               x2_promo_age_rel=(sum(rel) / len(rel)) if rel else None,
               x2_midseason_jumps=jumps / n, x2_skipped_levels=float(skipped))
    return out, f"{used[-1]}-12-31"


def load_draft_years(draft_dir: Path = DRAFT_DIR) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for p in sorted(Path(draft_dir).glob("*.json")):
        try:
            y = int(p.stem)
        except ValueError:
            continue
        for r in json.loads(p.read_text(encoding="utf-8")) or []:
            if r.get("mlbam"):
                out.setdefault(int(r["mlbam"]), []).append(y)
    for v in out.values():
        v.sort()
    return out


def load_bonus(path: Path = BONUS_PATH) -> dict[int, tuple[int, float]]:
    """{person: (draft year, log bonus over slot)} for signed picks with money."""
    out: dict[int, tuple[int, float]] = {}
    if not Path(path).exists():
        return out
    for k, v in json.loads(Path(path).read_text(encoding="utf-8")).items():
        if not isinstance(v, dict):
            continue
        try:
            pid = int(k)
        except (TypeError, ValueError):
            continue
        b, s, y = v.get("bonus_usd"), v.get("slot_usd"), v.get("year")
        if y is None or int(y) < FIRST_MONEY_YEAR or not b or float(b) <= 0:
            continue
        slot = float(s) if s and float(s) > 0 else LATE_ROUND_ALLOWANCE
        out[pid] = (int(y), math.log(float(b) / slot))
    return out


def _age_on(birth: str | None, day: str) -> float | None:
    try:
        b = datetime.strptime(str(birth)[:10], "%Y-%m-%d")
        d = datetime.strptime(day, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    return d.year - b.year - ((d.month, d.day) < (b.month, b.day))


def rule5_first_year(pid: int, birth: str | None, milb: MilbBook,
                     drafts: dict[int, list[int]], before_year: int | None = None
                     ) -> tuple[int | None, str]:
    """(December year of the first eligible Rule 5 draft, how). None without a MiLB
    season on record before `before_year` (DOC s3): a first season in the read's year
    or later is not known at the read."""
    fs = milb.first_season.get(pid)
    if fs is None or (before_year is not None and fs >= int(before_year)):
        return None, "no_milb_season"
    fa = milb.first_age.get(pid)
    dys = [y for y in drafts.get(pid, ()) if y <= fs]
    if dys:
        S = dys[-1]
        how = "draft"
        age = _age_on(birth, f"{S}-06-05")
    else:
        S = fs - 1 if (fa is not None and fa <= 17) else fs
        how = "ifa"
        age = _age_on(birth, f"{S}-07-02")
    if age is None:
        age = (fa - (fs - S)) if fa is not None else None
    if age is None:
        return None, "no_age"
    return (S + 4 if age <= R5_YOUNG_AGE else S + 3), how


def _season_mlb(season: int) -> frozenset[int]:
    return F._mlb_ids(int(season))


def trade_principal(pid: int, ev: tuple, book: TxBook, season_mlb=_season_mlb,
                    before_year: int | None = None) -> bool:
    """One of at most two players his club sent in the trade `ev`, for a return that held
    a player with a major league line in the trade season or the season before. A season
    in the read's year (`before_year`) or later is not known at the read and is not read."""
    day, _code, _desc, frm, to, tid = ev
    if tid is None:
        return False
    yr = int(day[:4])
    me = team_info(frm, yr)
    them = team_info(to, yr)
    if me is None or them is None:
        return False
    sent, ret = set(), set()
    for p, d, _c, _ds, f2, _t2, _id in book.trades.get(int(tid), ()):
        o = team_info(f2, yr)
        if o is None:
            continue
        if o[1] == me[1]:
            sent.add(p)
        elif o[1] == them[1]:
            ret.add(p)
    if not ret or len(sent | {pid}) > 2:
        return False
    seasons = [s for s in (yr, yr - 1) if before_year is None or s < int(before_year)]
    mlb = frozenset().union(*(season_mlb(s) for s in seasons)) if seasons else frozenset()
    return any(p in mlb for p in ret)


class Books:
    """Every source book a column reads, loaded once."""

    def __init__(self, tx: TxBook, milb: MilbBook, drafts: dict, bonus: dict, nri: dict,
                 *, date_cap: str):
        self.tx = tx
        self.milb = milb
        self.drafts = drafts
        self.bonus = bonus
        self.nri = nri
        self.date_cap = date_cap

    @classmethod
    def load(cls, *, last_year: int, date_cap: str, log=print) -> "Books":
        t0 = time.time()
        tx = TxBook.load(last_year)
        log(f"  transactions through {last_year}: {len(tx.months)} months, "
            f"{len(tx.events)} persons ({round(time.time() - t0, 1)} s)")
        milb = MilbBook.load(range(2005, int(last_year) + 1))
        log(f"  milb lines 2005 to {last_year} ({round(time.time() - t0, 1)} s)")
        nri = nri_entries(season_cap=last_year, date_cap=date_cap)
        return cls(tx, milb, load_draft_years(), load_bonus(), nri, date_cap=date_cap)


def nri_entries(*, season_cap: int, date_cap: str) -> dict[int, list[tuple[str, int]]]:
    """{person: [(known date, season)]} from the efv_w2_nri cache plus this task's NRI
    extension, dated by efv_w2_nri's rule, entries known on or after date_cap dropped."""
    import efv_drivers as DRV
    import efv_w2_nri as NRI
    rosters = NRI.load_rosters(min(int(season_cap), NRI.SEASONS[-1]))
    tx = DRV.load_league_transactions(int(season_cap))
    for season in NRI_EXTEND:
        if season > int(season_cap):
            continue
        for p in sorted((CACHE_DIR / "nri").glob(f"nri_{season}_*.json")):
            club = int(p.stem.split("_")[2])
            for e in json.loads(p.read_text(encoding="utf-8")).get("roster") or []:
                pid = (e.get("person") or {}).get("id")
                if pid:
                    rosters.setdefault(season, {}).setdefault(int(pid), []).append(club)
        if not rosters.get(season):
            # the endpoint returns an empty list for the current season (probed
            # 2026-10-15), so the season's list is the people with a dated invitation
            # in the league feed (the dating rule's own transactions)
            rosters[season] = feed_invitees(season, tx)
    idx = NRI.NriIndex.build(season_cap=int(season_cap), date_cap=date_cap, rosters=rosters,
                             tx=tx)
    return {pid: [(k, s) for k, s, _d in v] for pid, v in idx.entries.items()}


def feed_invitees(season: int, tx: dict) -> dict[int, list[int]]:
    """{person: []} for every person with a spring-training invitation announced in the
    efv_w2_nri dating range of `season` (1 September of S - 1 to 30 September of S)."""
    import efv_w2_nri as NRI
    lo = f"{int(season) - 1}{NRI.DATING_OPEN_MMDD}"
    hi = f"{int(season)}{NRI.DATING_CLOSE_MMDD}"
    return {int(pid): [] for pid, evs in tx.items()
            if any(NRI.INVITE_TEXT in str(desc).lower() and lo <= day <= hi
                   for day, _code, desc in evs)}


# ---------------------------------------------------------------------------
# the columns of one person at one read
# ---------------------------------------------------------------------------

def column_values(person_id, asof, birth: str | None, side: str, books: Books
                  ) -> tuple[dict, dict]:
    """({column: value | None}, {column: latest input date | None}) for one person read
    at `asof`. Every input is dated strictly before `asof`; None everywhere without an
    id or a read date, or for a read on or after the books' date cap."""
    vals = {c: None for c in COLUMNS}
    dates = {c: None for c in COLUMNS}
    try:
        pid = int(person_id) if person_id is not None else None
    except (TypeError, ValueError):
        pid = None
    d = str(asof or "")[:10]
    if pid is None or len(d) < 10 or d >= books.date_cap:
        return vals, dates
    year = int(d[:4])
    # promotion
    pv, pdate = promotion_values(books.milb.lines[side].get(pid), books.milb.medians, side,
                                 year)
    for k, v in pv.items():
        vals[k] = v
        dates[k] = pdate if v is not None else None
    # transactions strictly before the read
    evs = [e for e in books.tx.events.get(pid, ()) if e[0] < d]
    last_tx = evs[-1][0] if evs else None
    tx_cols = ("x2_options", "x2_release_events", "x2_trades", "x2_trade_principal_mlb",
               "x2_r5_selected", "x2_r5m_selected")
    vals["x2_options"] = float(sum(1 for e in evs if e[1] == "OPT"))
    vals["x2_release_events"] = float(sum(1 for e in evs if e[1] in RELEASE_CODES))
    trades = {}
    for e in evs:
        if e[1] == "TR":
            trades.setdefault(e[5], e)
    vals["x2_trades"] = float(len(trades))
    vals["x2_trade_principal_mlb"] = 1.0 if any(
        trade_principal(pid, e, books.tx, before_year=year) for e in trades.values()) else 0.0
    r5_days = {y: day for y, day in books.tx.r5_days.items() if day < d}
    sel_mlb = sel_min = False
    for e in evs:
        if e[1] == "R5":
            sel_mlb = True
        elif e[1] == "R5M":
            sel_min = True
        elif (e[1] == "CLW" and r5_days.get(int(e[0][:4])) == e[0]
              and books.tx.r5_detected.get(int(e[0][:4]))):
            info = team_info(e[4], int(e[0][:4]))
            if info is not None and info[0] == 1:
                sel_mlb = True
            elif info is not None:
                sel_min = True
    vals["x2_r5_selected"] = 1.0 if sel_mlb else 0.0
    vals["x2_r5m_selected"] = 1.0 if sel_min else 0.0
    for k in tx_cols:
        dates[k] = last_tx
    # Rule 5 eligibility and protection
    first, _how = rule5_first_year(pid, birth, books.milb, books.drafts, before_year=year)
    if first is not None:
        elig = sorted(day for y, day in r5_days.items() if y >= first)
        add = first_add_day(evs, d)
        first_day = books.tx.r5_days.get(first) or f"{first}-12-01"
        vals["x2_add_before_elig"] = 1.0 if (add is not None and add < first_day) else 0.0
        exposed = [day for day in elig if not forty_man_on(evs, day)]
        vals["x2_r5_exposed_n"] = float(len(exposed))
        if elig:
            vals["x2_r5_protect"] = -1.0 if elig[-1] in exposed else 1.0
        else:
            vals["x2_r5_protect"] = 0.0
        for k in ("x2_add_before_elig", "x2_r5_exposed_n", "x2_r5_protect"):
            dates[k] = max([x for x in (last_tx, elig[-1] if elig else None) if x],
                           default=None)
    # spring invitations known strictly before the read
    springs = {s for k, s in books.nri.get(pid, ()) if k < d}
    vals["x2_nri_springs"] = float(len(springs))
    known = [k for k, s in books.nri.get(pid, ()) if k < d]
    dates["x2_nri_springs"] = max(known) if known else None
    # market price
    b = books.bonus.get(pid)
    if b is not None and b[0] < year:
        vals["x2_bonus_vs_slot"] = b[1]
        dates["x2_bonus_vs_slot"] = f"{b[0]}-12-31"
    for k, dd in dates.items():
        if dd is not None and not dd < d:
            raise AssertionError(f"look-ahead: {k} read {dd} for a read at {d}")
    return vals, dates


# ---------------------------------------------------------------------------
# the development frames
# ---------------------------------------------------------------------------

def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


def check_dev_folds(frames: dict) -> None:
    """Raise unless every fold and row is a development fold (DOC s2)."""
    for fid, fr in frames.items():
        if fid not in FRAMES_DEV:
            raise F.ReservedFrameError(f"frame {fid} is not a development frame")
        for side, blks in fr["by_side"].items():
            for fold, blk in blks.items():
                fold = int(fold)
                if fid == "lv_dev" and fold not in LV_DEV_FOLDS:
                    raise F.ReservedFrameError(f"lv fold {fold} is not a development fold")
                if fid == "vm_dev" and fold >= F.R_VM_FIRST_DEBUT_YEAR:
                    raise F.ReservedFrameError(f"vm fold {fold} is a reserved cohort")
                for part in ("train", "test"):
                    for r in blk[part]:
                        y = int(r["decision_year"])
                        if fid == "lv_dev" and (y in F.RESERVED_LV or y > max(LV_DEV_FOLDS)):
                            raise F.ReservedFrameError(f"lv row at reserved vintage {y}")
                        if y >= F.R_VM_FIRST_DEBUT_YEAR:
                            raise F.ReservedFrameError(f"row at reserved year {y}")


def build_inputs(*, log=print) -> tuple[dict, dict]:
    """(the C03 development inputs, the list-vintage frames they were built from)."""
    _tools()
    import efv_v2_assemble as ASM
    import efv_v2_model_class_screen as MCS
    t0 = time.time()
    frames_lv = ASM.build_frames()
    log(f"lv frames built ({round(time.time() - t0, 1)} s)")
    orig = ASM.build_frames
    ASM.build_frames = lambda *a, **k: frames_lv
    try:
        inputs = MCS.build_inputs(log=lambda m: None)
    finally:
        ASM.build_frames = orig
    log(f"development inputs built ({round(time.time() - t0, 1)} s)")
    check_dev_folds(inputs["frames"])
    return inputs, frames_lv


def row_reads(inputs: dict, frames_lv: dict) -> dict:
    """{(fid, side, year, player_key, part): (person id, read date, birth date)}: lv rows
    on the frame row's outcome-blind id at its asof_date; vm training rows on the matrix
    id at the matrix asof_date, vm test rows at the pinned preseason read."""
    import efv_v2_model as H
    out = {}
    for side in F.SIDES:
        lv = {(int(V), r["player_key"]): r for V, (rows, _l) in frames_lv[side].items()
              for r in rows}
        raw = {r["player_key"]: r for r in json.loads(
            H._matrix_path(side).read_text(encoding="utf-8"))}
        mine: dict = {}
        H.pinned_inputs(side, H.matrix_training_rows(side), mine)
        pinned = {pk: rec.get("asof_date") for pk, rec in mine.items()}
        for fid in FRAMES_DEV:
            for fold, blk in inputs["frames"][fid]["by_side"][side].items():
                for part in ("train", "test"):
                    for r in blk[part]:
                        y, pk = int(r["decision_year"]), r["player_key"]
                        if fid == "lv_dev":
                            fr = lv.get((y, pk))
                            if fr is None:
                                raise KeyError(f"lv {side} {y} {pk}: no frame row")
                            out[(fid, side, y, pk, part)] = (
                                fr.get("mlbam_id"), fr.get("asof_date"), fr.get("birth_date"))
                        else:
                            rw = raw.get(pk) or {}
                            asof = rw.get("asof_date") if part == "train" else pinned.get(pk)
                            out[(fid, side, y, pk, part)] = (
                                rw.get("mlbam_id"), asof, rw.get("birth_date"))
    return out


def attach_columns(reads: dict, books: Books, *, log=print) -> tuple[dict, dict]:
    """({read key: {column: value}}, receipts). Each (person, read date, side) is
    computed once."""
    memo: dict = {}
    out = {}
    latest = None
    for key, (pid, asof, birth) in reads.items():
        side = key[1]
        mk = (pid, str(asof or "")[:10], side, birth)
        if mk not in memo:
            vals, dates = column_values(pid, asof, birth, side, books)
            memo[mk] = vals
            ds = [x for x in dates.values() if x]
            if ds and (latest is None or max(ds) > latest[0]):
                latest = (max(ds), str(asof)[:10])
        out[key] = memo[mk]
    log(f"  columns on {len(out)} row reads ({len(memo)} distinct reads)")
    return out, {"distinct_reads": len(memo), "row_reads": len(out),
                 "latest_input_date_read": latest}


# ---------------------------------------------------------------------------
# the fit and the statistic
# ---------------------------------------------------------------------------

def _pct(values: list[float]) -> np.ndarray:
    from scipy.stats import rankdata
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0:
        return v
    return (rankdata(v) - 0.5) / v.size


def _pct_by(values: list[float], years: list[int]) -> np.ndarray:
    out = np.zeros(len(values))
    ys = np.asarray(years)
    vv = np.asarray(values, dtype=np.float64)
    for y in sorted(set(years)):
        m = ys == y
        out[m] = _pct(list(vv[m]))
    return out


def fit_fold(train: list[dict], test: list[dict], names: list[str]) -> dict:
    """OLS of the training target's percentile on [1, consensus percentile, standardized
    columns], fitted on training rows with a resolved id; the test score b_u u + b z.
    train rows: {"fv", "target", "year", "has_id", "x": {name: v}}; test rows: {"u",
    "x"}. A missing value takes the training mean (z = 0)."""
    tr = [r for r in train if r["fv"] is not None and r["target"] is not None]
    u_tr = _pct_by([r["fv"] for r in tr], [r["year"] for r in tr])
    t_tr = _pct_by([r["target"] for r in tr], [r["year"] for r in tr])
    fit_rows = np.asarray([bool(r["has_id"]) for r in tr])
    mu, sd = {}, {}
    for n in names:
        obs = [r["x"].get(n) for r, ok in zip(tr, fit_rows) if ok and r["x"].get(n) is not None]
        mu[n] = float(np.mean(obs)) if obs else 0.0
        s = float(np.std(obs)) if len(obs) > 1 else 0.0
        sd[n] = s if s > 1e-12 else 0.0

    def z(rows):
        Z = np.zeros((len(rows), len(names)))
        for j, n in enumerate(names):
            if sd[n] == 0.0:
                continue
            for i, r in enumerate(rows):
                v = r["x"].get(n)
                Z[i, j] = 0.0 if v is None else (float(v) - mu[n]) / sd[n]
        return Z
    if int(fit_rows.sum()) < MIN_FIT_ROWS:
        # too few training rows with an id: the score is consensus's own order
        b_u, b_z = 1.0, [0.0] * len(names)
    else:
        Ztr = z(tr)[fit_rows]
        X = np.column_stack([np.ones(int(fit_rows.sum())), u_tr[fit_rows], Ztr])
        beta, *_ = np.linalg.lstsq(X, t_tr[fit_rows], rcond=None)
        b_u = float(beta[1])
        b_z = [float(b) for b in beta[2:]]
    u_te = np.asarray([r["u"] for r in test], dtype=np.float64)
    score = b_u * u_te + (z(test) @ np.asarray(b_z) if names else 0.0)
    return {"score": score, "b_u": round(b_u, 6), "b_z": dict(zip(names, [round(b, 6)
                                                                         for b in b_z])),
            "n_fit": int(fit_rows.sum()), "n_train": len(tr),
            "mean": {n: round(mu[n], 6) for n in names},
            "sd": {n: round(sd[n], 6) for n in names}}


def frame_rows(inputs: dict, fid: str, cols: dict) -> dict:
    """{(side, fold): (train rows, scored rows)} in fit_fold's shape. A scored row keeps
    the base keys of efv_v2_stat (key, group, outcome, consensus)."""
    import source_backtest as SB
    cons_key = SB.CONSENSUS_KEY
    out = {}
    for side in F.SIDES:
        for fold, blk in inputs["frames"][fid]["by_side"][side].items():
            tr = []
            for r in blk["train"]:
                k = (fid, side, int(r["decision_year"]), r["player_key"], "train")
                x = cols[k]
                tr.append({"fv": r.get("fv"), "target": r.get("target"),
                           "year": int(r["decision_year"]), "x": x,
                           "has_id": _has_id(x)})
            sc = blk["scored"]
            u = _pct([c["grades"][cons_key] for c in sc])
            te = []
            for c, ui in zip(sc, u):
                k = (fid, side, int(c["year"]), c["key"], "test")
                te.append({"key": c["key"], "group": c["group"], "side": side,
                           "year": int(c["year"]), "u": float(ui), "x": cols[k],
                           "cons": float(c["grades"][cons_key]),
                           "war": float(c["outcome"]["war"]),
                           "contributor": bool(c["outcome"]["contributor"])})
            out[(side, int(fold))] = (tr, te)
    return out


_ID_MARK = "_has_id"


def _has_id(x: dict) -> bool:
    return bool(x.get(_ID_MARK))


def arm_scores(rows_by_fold: dict, names: list[str]) -> tuple[list[dict], dict]:
    """The scored rows with the arm's score under "a", and the per-fold slopes."""
    rows, slopes = [], {}
    for (side, fold), (tr, te) in sorted(rows_by_fold.items()):
        if not te:
            continue
        f = fit_fold(tr, te, names)
        for r, s in zip(te, f["score"]):
            rows.append(dict(r, a=float(s)))
        slopes[f"{side}|{fold}"] = {"b_u": f["b_u"], "b_z": f["b_z"], "n_fit": f["n_fit"],
                                    "n_train": f["n_train"]}
    return rows, slopes


def paired_within(rows: list[dict], *, B: int, seed: int) -> dict:
    import efv_v2_stat as S
    d = S.paired_delta([r["key"] for r in rows], [r["group"] for r in rows],
                       [r["war"] for r in rows], [r["contributor"] for r in rows],
                       [r["a"] for r in rows], [r["cons"] for r in rows],
                       [r["cons"] for r in rows], statistic="within", B=B, seed=seed)
    keep = ("a", "b", "delta", "ci95", "sd", "mde95", "p_gt_0", "n", "n_clusters",
            "rows_in_kept_groups", "B", "B_used", "seed", "status")
    return {k: d.get(k) for k in keep}


def coverage(rows: list[dict], name: str) -> dict:
    """{str(year) and "all": {"rows", "with_value", "nonzero"}} on scored rows."""
    out: dict = {}
    for r in rows:
        for key in (f"{r['side']}|{r['year']}", "all"):
            c = out.setdefault(key, {"rows": 0, "with_value": 0, "nonzero": 0})
            v = r["x"].get(name)
            c["rows"] += 1
            c["with_value"] += int(v is not None)
            c["nonzero"] += int(v not in (None, 0.0))
    return dict(sorted(out.items()))


def reading(lv: dict, vm: dict) -> str:
    """CARRY, LEAN or NULL (DOC s5), from the both-sides blocks of the two frames."""
    dl, dv = lv.get("delta"), vm.get("delta")
    if dl is None or dv is None or not (dl > 0 and dv > 0):
        return "NULL"
    ci = lv.get("ci95")
    if isinstance(ci, list) and len(ci) == 2 and ci[0] > 0:
        return "CARRY"
    return "LEAN"


def read_frame(inputs: dict, fid: str, cols: dict, *, B: int, seed: int, log=print) -> dict:
    by_fold = frame_rows(inputs, fid, cols)
    arms = {}
    for name in list(COLUMNS) + [JOINT]:
        names = list(COLUMNS) if name == JOINT else [name]
        t0 = time.time()
        rows, slopes = arm_scores(by_fold, names)
        blk = {"slopes": slopes}
        for scope in SCOPES:
            sel = rows if scope == "both" else [r for r in rows if r["side"] == scope]
            blk[scope] = paired_within(sel, B=B, seed=seed)
        if name != JOINT:
            blk["coverage"] = coverage(rows, name)
        arms[name] = blk
        b = blk["both"]
        log(f"  {fid} {name}: delta {b['delta']} {b['ci95']} ({round(time.time() - t0, 1)} s)")
    rows0, _s = arm_scores(by_fold, [])
    base = {scope: paired_within(rows0 if scope == "both"
                                 else [r for r in rows0 if r["side"] == scope], B=50, seed=seed)
            for scope in SCOPES}
    n_side = {s: sum(1 for r in rows0 if r["side"] == s) for s in F.SIDES}
    return {"n": len(rows0), "n_by_side": n_side,
            "n_players": len({r["key"] for r in rows0}),
            "folds": sorted({f for (_side, f) in by_fold}),
            "consensus_within": {s: base[s]["b"] for s in SCOPES},
            "liveness_no_column": {s: base[s]["delta"] for s in SCOPES},
            "arms": arms}


# ---------------------------------------------------------------------------
# receipts, artifact
# ---------------------------------------------------------------------------

def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def source_receipt(books: Books) -> dict:
    nri_files = sorted((CACHE_DIR / "nri").glob("nri_*.json")) if CACHE_DIR.exists() else []
    teams = load_teams()
    return {
        "transactions": {"dir": ".cache/mlb_transactions", "months": len(books.tx.months),
                         "first": books.tx.months[0] if books.tx.months else None,
                         "last": books.tx.months[-1] if books.tx.months else None,
                         "persons": len(books.tx.events)},
        "rule5_draft_days": {str(y): d for y, d in sorted(books.tx.r5_days.items())},
        "rule5_day_detected": {str(y): v for y, v in sorted(books.tx.r5_detected.items())},
        "teams": {"dir": ".cache/efv_x2_revealed/teams", "seasons": sorted(teams)},
        "nri": {"dirs": [".cache/efv4_nri", ".cache/efv_x2_revealed/nri"],
                "extension_files": len(nri_files), "extension_seasons": list(NRI_EXTEND),
                "persons_dated_before_cap": len(books.nri)},
        "draft_history": {"dir": ".cache/draft_history", "persons": len(books.drafts)},
        "bonus": {"path": "data/draft_bonus_slot.json", "persons": len(books.bonus),
                  "first_year": FIRST_MONEY_YEAR, "sha256": _sha(BONUS_PATH)},
        "milb": {"source": "milb_history.season_splits (cached)",
                 "persons_hit": len(books.milb.lines["hit"]),
                 "persons_pit": len(books.milb.lines["pit"]),
                 "min_line_volume": MIN_LINE_VOLUME},
    }


def _assert_no_dash(text: str) -> None:
    if chr(0x2014) in text or chr(0x2013) in text:
        raise ValueError("dash in artifact text")


def read(*, B: int = B_DEFAULT, seed: int = SEED, out: Path = OUT_PATH, log=print) -> dict:
    t0 = time.time()
    inputs, frames_lv = build_inputs(log=log)
    reads = row_reads(inputs, frames_lv)
    # development reads: no season after 2024, nothing known on or after 2025-01-01
    books = Books.load(last_year=F.R_VM_FIRST_DEBUT_YEAR - 1,
                       date_cap=f"{F.R_VM_FIRST_DEBUT_YEAR}-01-01", log=log)
    cols, rec = attach_columns(reads, books, log=log)
    for k, (pid, _asof, _b) in reads.items():
        cols[k] = dict(cols[k], **{_ID_MARK: pid is not None})
    _tools()
    import efv_v3_backtest as BT
    frames = {}
    for fid in FRAMES_DEV:
        frames[fid] = read_frame(inputs, fid, cols, B=B, seed=seed, log=log)
        frames[fid]["role"] = "development"
        frames[fid]["note"] = "development frame, spent, not a claim"
    summary = []
    for name in list(COLUMNS) + [JOINT]:
        lv, vm = frames["lv_dev"]["arms"][name]["both"], frames["vm_dev"]["arms"][name]["both"]
        summary.append({"column": name,
                        "family": COLUMNS.get(name, {}).get("family", "joint"),
                        "lv_dev": {"delta": lv["delta"], "ci95": lv["ci95"]},
                        "vm_dev": {"delta": vm["delta"], "ci95": vm["ci95"]},
                        "reading": reading(lv, vm)})
    doc = {
        "schema": 1, "item": ITEM,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "produced_by": TOOL, "registration": DOC, "role": "development",
        "adjudicates": False, "selects": False, "ships": False, "note": NOTE,
        "owner_decision": "EW3-12 (2026-10-15)",
        "label": BT._label(),
        "code": {"commit": _git("rev-parse", "HEAD"),
                 "module_sha256": _sha(Path(__file__)),
                 "registration_commit": _git("log", "-1", "--format=%H", "--", DOC)},
        "estimator": {"statistic": "within (side, vintage) Spearman, size-weighted, arm "
                                   "minus PROSPX consensus (efv_v2_stat.paired_delta)",
                      "interval": "E_cond, paired, player-clustered", "B": int(B),
                      "seed": int(seed),
                      "fit": "OLS of the training target percentile on [1, consensus "
                             "percentile, standardized columns], rows with a resolved id; "
                             "missing value takes the training mean"},
        "columns": {k: dict(v) for k, v in COLUMNS.items()},
        "joint_arm": JOINT,
        "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                   "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                   "lv_folds": list(LV_DEV_FOLDS), "date_cap": books.date_cap,
                   "season_cap": F.R_VM_FIRST_DEBUT_YEAR - 1},
        "sources": source_receipt(books),
        "column_receipts": rec,
        "frames": frames,
        "summary": summary,
        "elapsed_s": round(time.time() - t0, 1),
    }
    text = json.dumps(doc, indent=1, default=str)
    _assert_no_dash(text)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(out)
    log(f"wrote {out} ({doc['elapsed_s']} s)")
    return doc


def check(*, log=print) -> dict:
    """Source receipts only: no frame, no label, no statistic."""
    books = Books.load(last_year=F.R_VM_FIRST_DEBUT_YEAR - 1,
                       date_cap=f"{F.R_VM_FIRST_DEBUT_YEAR}-01-01", log=log)
    rec = source_receipt(books)
    log(json.dumps(rec, indent=1, default=str))
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--B", type=int, default=B_DEFAULT)
    a = ap.parse_args(argv)
    if a.fetch:
        if not fetch_window_open():
            print("fetch window closed (06:00 to 11:00 UTC)")
            return 2
        print(json.dumps(fetch()))
    if a.check:
        check()
    if a.read:
        read(B=a.B)
    return 0


if __name__ == "__main__":
    sys.exit(main())
