# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV expert program X4: StatsAPI pitch-level probe below Triple-A
(EFV_X4_STATSAPI_PITCH_PROBE; owner 2026-10-15, decision EW3-12; registration
docs/efv-x4-pitch-probe/REGISTRATION.md, committed alone before this file existed).

WHAT IT DOES.
  --probe   fetch the registered coverage sample (two games per home team, level and
            season; sportIds 11 control, 12, 13, 14; seasons 2021 to 2026) as raw
            /feed/live JSON into .cache/efv_x4_pitch/feeds/, and count, per game, the
            share of pitch events carrying each tracked field (section 3).
  --full    for every sub-AAA (level, season) cell of 2021 to 2023 that the coverage rule
            marks VELO-COVERED, fetch every final regular-season game as a fields-filtered
            playByPlay payload into .cache/efv_x4_pitch/pbp/ (section 4).
  --read    build the per-player season aggregate and the descriptive read (sections 4 to
            7) and write data/_labs/efv_x4_pitch_probe.json.
  --md      write docs/efv-x4-pitch-probe/COVERAGE.md and RESULTS.md from the artifact.

DARK. No served module imports this file; the artifact lives under data/_labs/ (ships in
neither deploy consumer). GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus FV is
a continuous covariate and a comparator score only; nothing is grouped, counted or
averaged by consensus-FV level. RESERVED FRAMES: consensus vintages 2022 to 2024 only (R-LV
never built); rows whose short-label window reaches a 2025 or later debut cohort are
labelled spent. No look-ahead: every game feeding a row is asserted to fall inside season
S, before the row's as-of date V-01-01.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CACHE = ROOT / ".cache" / "efv_x4_pitch"
FEED_DIR = CACHE / "feeds"
PBP_DIR = CACHE / "pbp"
SCHED_DIR = CACHE / "schedule"
V4_SCHED_DIR = ROOT / ".cache" / "efv4_pbp" / "schedule"
OUT_PATH = ROOT / "data" / "_labs" / "efv_x4_pitch_probe.json"
DOC_DIR = ROOT / "docs" / "efv-x4-pitch-probe"
GATE_DOC = DOC_DIR / "REGISTRATION.md"
COVERAGE_DOC = DOC_DIR / "COVERAGE.md"
RESULTS_DOC = DOC_DIR / "RESULTS.md"
TOOL = "tools/efv_x4_pitch_probe.py"
ITEM = "EFV_X4_STATSAPI_PITCH_PROBE"
SCHEMA = 1

API = "https://statsapi.mlb.com/api"
USER_AGENT = ("BaseballR-prospect-tracker eFV X4 MiLB pitch-tracking coverage probe "
              "(one-off research fetch, 2 to 4 connections, resumable cache)")

# ----------------------------------------------------------------- declared (registration)
SPORTS: dict[int, str] = {11: "AAA", 12: "AA", 13: "A+", 14: "A"}
SUB_AAA = (12, 13, 14)
SEASONS: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025, 2026)
LABEL_SEASONS: tuple[int, ...] = (2021, 2022, 2023)
EARLY_MMDD, LATE_MMDD = "05-15", "08-01"
PROBE_WORKERS, FULL_WORKERS = 2, 4
REQUEST_PAUSE = 0.25
BLACKOUT_UTC_HOURS = range(6, 11)
GAME_TRACKED_SHARE = 0.80
CELL_COVERED_SHARE = 0.50
FIELDS: tuple[str, ...] = ("startSpeed", "spinRate", "ivb", "hbreak", "extension", "pxpz",
                           "zone", "ptype", "launchSpeed", "launchAngle", "xy")
#: "xy" (the Gameday stringer's pixel location, pitchData.coordinates.x and .y) is NOT a
#: registered field: it was added after the first sampled feed showed it, is reported as a
#: disclosed extra column, and enters no rule.
EXTRA_FIELDS = frozenset({"xy"})
BIP_FIELDS = frozenset({"launchSpeed", "launchAngle"})
FIELD_NAMES = {"startSpeed": "release speed", "spinRate": "spin rate",
               "ivb": "induced vertical break", "hbreak": "horizontal break",
               "extension": "extension", "pxpz": "plate location (pX, pZ)", "zone": "zone",
               "ptype": "pitch type", "launchSpeed": "launch speed", "launchAngle": "launch angle",
               "xy": "stringer pixel location (x, y; extra, unregistered)"}
FULL_SET = ("startSpeed", "spinRate", "ivb", "extension", "pxpz", "launchSpeed", "launchAngle")

FASTBALLS = frozenset({"FF", "SI", "FT", "FA"})
WHIFF = frozenset({"S", "W", "M", "Q"})
SWING = WHIFF | frozenset({"T", "F", "L", "O", "R", "X", "D", "E"})
PIT_MIN_PITCHES, HIT_MIN_PA = 100, 50
MIN_FB, MIN_BIP, MIN_SWINGS = 25, 15, 30
HARD_HIT_MPH = 95.0
ZONE_HALF_WIDTH_FT = 0.83

#: metric -> the coverage fields it needs (section 4, the candidate rule)
PIT_METRICS = {"fb_velo_p50": ("startSpeed", "ptype"), "fb_velo_p95": ("startSpeed", "ptype"),
               "fb_spin": ("spinRate", "ptype"), "fb_ivb": ("ivb", "ptype"),
               "whiff": ("startSpeed",), "chase": ("zone", "pxpz"),
               "ev_against_p50": ("launchSpeed",)}
HIT_METRICS = {"ev_p50": ("launchSpeed",), "ev_p90": ("launchSpeed",),
               "hard_hit": ("launchSpeed",), "whiff": ("startSpeed",), "chase": ("zone", "pxpz"),
               "zone_contact": ("zone", "pxpz")}
METRIC_NAMES = {"fb_velo_p50": "fastball velocity, median", "fb_velo_p95": "fastball velocity, 95th pct",
                "fb_spin": "fastball spin rate", "fb_ivb": "fastball induced vertical break",
                "whiff": "whiff rate", "chase": "chase rate", "ev_against_p50": "exit velocity against, median",
                "ev_p50": "exit velocity, median", "ev_p90": "exit velocity, 90th pct",
                "hard_hit": "hard-hit rate (95 mph or more)", "zone_contact": "zone contact rate"}
LEVEL_RANK = {"A": 0, "A+": 1, "AA": 2}
CONSENSUS_VINTAGES = tuple(s + 1 for s in LABEL_SEASONS)          # 2022, 2023, 2024
CLEAN_COHORTS = (2021,)
LAMBDA = 10.0
FOLDS = 5
SEED = 20261015
B_DEFAULT = 2000

NOTE = ("eFV X4 StatsAPI pitch probe, development read (EW3-12): descriptive only, ships "
        "nothing, no number by consensus-FV level, consensus FV a covariate and a comparator only")
SPENT_NOTE = ("spent: the short-label window reaches a 2025 or later debut cohort (R-VM); the "
              "EW3-13 waiver belongs to EFV_2026_HOLDOUT_READ alone, so these numbers are read "
              "once here and are never the sole claim")

PBP_FIELDS = ",".join((
    "allPlays", "result", "eventType", "about", "atBatIndex", "isTopInning", "matchup",
    "batter", "pitcher", "id", "playEvents", "isPitch", "pitchNumber", "details", "call",
    "code", "type", "isInPlay", "pitchData", "startSpeed", "extension", "zone",
    "strikeZoneTop", "strikeZoneBottom", "coordinates", "pX", "pZ", "breaks", "spinRate",
    "breakVerticalInduced", "breakHorizontal", "hitData", "launchSpeed", "launchAngle",
))
SCHEDULE_FIELDS = ",".join((
    "dates", "date", "games", "gamePk", "gameType", "officialDate", "status",
    "abstractGameState", "detailedState", "codedGameState", "teams", "home", "away",
    "team", "id", "league",
))
EXCLUDED_LEAGUES = {125}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# ------------------------------------------------------------------------------ network

class FetchWindowClosed(RuntimeError):
    pass


_session = None
_lock = threading.Lock()
NET = {"calls": 0, "seconds": 0.0, "errors": 0}


def _session_get():
    global _session
    with _lock:
        if _session is None:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            s = requests.Session()
            retry = Retry(total=6, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504],
                          allowed_methods=frozenset({"GET"}), respect_retry_after_header=True)
            ad = HTTPAdapter(max_retries=retry, pool_connections=FULL_WORKERS, pool_maxsize=FULL_WORKERS)
            s.mount("https://", ad)
            s.headers["User-Agent"] = USER_AGENT
            _session = s
        return _session


def _guard() -> None:
    h = datetime.now(timezone.utc).hour
    if h in BLACKOUT_UTC_HOURS:
        raise FetchWindowClosed(f"UTC hour {h:02d} is inside the 06:00 to 11:00 UTC nightly window")


def get_json(url: str, params: dict | None = None) -> dict:
    _guard()
    time.sleep(REQUEST_PAUSE)
    t0 = time.time()
    r = _session_get().get(url, params=params or {}, timeout=90)
    with _lock:
        NET["calls"] += 1
        NET["seconds"] += time.time() - t0
    r.raise_for_status()
    return r.json()


def write_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(gzip.compress(json.dumps(obj, separators=(",", ":")).encode("utf-8"), 6))
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        if not path.exists():
            raise


def read_gz(path: Path):
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


# ----------------------------------------------------------------------------- schedule

def schedule(sport: int, season: int) -> list[dict]:
    """Final regular-season games [{gamePk, date, league, home, away}] by the rule of
    milb_pbp_fetch.schedule; 2021 to 2025 read from the eFV v4 cache, else fetched here."""
    v4 = V4_SCHED_DIR / f"{int(sport)}_{int(season)}.v2.json.gz"
    if v4.exists():
        return read_gz(v4)
    path = SCHED_DIR / f"{int(sport)}_{int(season)}.v2.json.gz"
    if path.exists():
        return read_gz(path)
    data = get_json(f"{API}/v1/schedule", {
        "sportId": int(sport), "startDate": f"{int(season)}-02-15",
        "endDate": f"{int(season)}-11-30", "gameType": "R", "hydrate": "team(league)",
        "fields": SCHEDULE_FIELDS})
    games: dict[int, dict] = {}
    for d in data.get("dates") or []:
        for g in d.get("games") or []:
            st = g.get("status") or {}
            final = (st.get("abstractGameState") == "Final"
                     and st.get("detailedState") not in {"Postponed", "Cancelled", "Suspended"}
                     and st.get("codedGameState") not in {"D", "C", "U", "T"})
            if g.get("gameType") != "R" or not final:
                continue
            teams = g.get("teams") or {}
            home = (teams.get("home") or {}).get("team") or {}
            away = (teams.get("away") or {}).get("team") or {}
            league = (home.get("league") or {}).get("id")
            if league in EXCLUDED_LEAGUES or (away.get("league") or {}).get("id") in EXCLUDED_LEAGUES:
                continue
            pk = int(g["gamePk"])
            games[pk] = {"gamePk": pk, "date": g.get("officialDate") or d.get("date"),
                         "league": league, "home": home.get("id"), "away": away.get("id")}
    out = sorted(games.values(), key=lambda r: (r["date"] or "", r["gamePk"]))
    write_gz(path, out)
    return out


def sample_games(sched: list[dict], season: int) -> list[dict]:
    """The registered sample: per home team the first home game on or after May 15 (EARLY)
    and on or after Aug 1 (LATE); a half without one takes the nearest earlier home game;
    a repeated pick counts once."""
    by_home: dict = {}
    for g in sched:
        if g.get("home") is not None:
            by_home.setdefault(g["home"], []).append(g)
    out = []
    for home in sorted(by_home):
        gs = sorted(by_home[home], key=lambda r: (r["date"] or "", r["gamePk"]))
        picks = {}
        for half, mmdd in (("early", EARLY_MMDD), ("late", LATE_MMDD)):
            cut = f"{int(season)}-{mmdd}"
            after = [g for g in gs if (g["date"] or "") >= cut]
            pick = after[0] if after else gs[-1]
            if pick["gamePk"] not in picks:
                picks[pick["gamePk"]] = dict(pick, half=half)
        out.extend(picks.values())
    return out


def feed_path(sport: int, season: int, pk: int) -> Path:
    return FEED_DIR / str(int(sport)) / str(int(season)) / f"{int(pk)}.json.gz"


def pbp_path(sport: int, season: int, pk: int) -> Path:
    return PBP_DIR / str(int(sport)) / str(int(season)) / f"{int(pk)}.json.gz"


def fetch_feed(sport: int, season: int, pk: int) -> str:
    p = feed_path(sport, season, pk)
    if p.exists():
        return "cached"
    data = get_json(f"{API}/v1.1/game/{int(pk)}/feed/live")
    write_gz(p, data)
    return "fetched"


def fetch_pbp(sport: int, season: int, pk: int) -> str:
    p = pbp_path(sport, season, pk)
    if p.exists():
        return "cached"
    data = get_json(f"{API}/v1/game/{int(pk)}/playByPlay", {"fields": PBP_FIELDS})
    write_gz(p, data)
    return "fetched"


def _run_pool(jobs: list[tuple], fn, workers: int, log=print, label="") -> dict:
    stats = {"fetched": 0, "cached": 0, "failed": 0, "failures": []}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, *j): j for j in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                stats[fut.result()] += 1
            except FetchWindowClosed:
                raise
            except Exception as e:                      # noqa: BLE001  (recorded, never hidden)
                stats["failed"] += 1
                stats["failures"].append([*futs[fut], f"{type(e).__name__}: {e}"[:200]])
            if i % 200 == 0:
                log(f"  {label} {i}/{len(jobs)} ({time.time() - t0:.0f} s, {NET['calls']} calls)")
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


# --------------------------------------------------------------------------- parsing

def _present(v) -> bool:
    return v is not None


def pitch_fields(ev: dict) -> dict:
    """Presence of every registered field on one pitch event."""
    pd = ev.get("pitchData") or {}
    br = pd.get("breaks") or {}
    co = pd.get("coordinates") or {}
    det = ev.get("details") or {}
    hd = ev.get("hitData") or {}
    return {"startSpeed": _present(pd.get("startSpeed")), "spinRate": _present(br.get("spinRate")),
            "ivb": _present(br.get("breakVerticalInduced")), "hbreak": _present(br.get("breakHorizontal")),
            "extension": _present(pd.get("extension")),
            "pxpz": _present(co.get("pX")) and _present(co.get("pZ")),
            "zone": _present(pd.get("zone")), "ptype": _present((det.get("type") or {}).get("code")),
            "launchSpeed": _present(hd.get("launchSpeed")), "launchAngle": _present(hd.get("launchAngle")),
            "xy": _present(co.get("x")) and _present(co.get("y")),
            "_bip": bool(det.get("isInPlay"))}


def game_coverage(feed: dict) -> dict:
    gd = feed.get("gameData") or {}
    plays = ((feed.get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    n = nb = 0
    cnt = {f: 0 for f in FIELDS}
    for play in plays:
        for ev in play.get("playEvents") or []:
            if not ev.get("isPitch"):
                continue
            pf = pitch_fields(ev)
            n += 1
            nb += int(pf["_bip"])
            for f in FIELDS:
                if f in BIP_FIELDS:
                    cnt[f] += int(pf["_bip"] and pf[f])
                else:
                    cnt[f] += int(pf[f])
    share = {}
    for f in FIELDS:
        den = nb if f in BIP_FIELDS else n
        share[f] = round(cnt[f] / den, 4) if den else None
    venue = gd.get("venue") or {}
    home = (gd.get("teams") or {}).get("home") or {}
    league = home.get("league") or {}
    return {"pitches": n, "bip": nb, "share": share,
            "league_id": league.get("id"), "league": league.get("name"),
            "tracked": {f: (share[f] is not None and share[f] >= GAME_TRACKED_SHARE) for f in FIELDS},
            "venue_id": venue.get("id"), "venue": venue.get("name"),
            "home_id": home.get("id"), "home": home.get("name"),
            "date": (gd.get("datetime") or {}).get("officialDate")}


# ----------------------------------------------------------------------------- probe

def probe(*, log=print, fetch: bool = True) -> dict:
    jobs, plan = [], []
    for sport in SPORTS:
        for season in SEASONS:
            sched = schedule(sport, season) if fetch else (
                read_gz(V4_SCHED_DIR / f"{sport}_{season}.v2.json.gz")
                if (V4_SCHED_DIR / f"{sport}_{season}.v2.json.gz").exists()
                else read_gz(SCHED_DIR / f"{sport}_{season}.v2.json.gz"))
            picks = sample_games(sched, season)
            plan.append({"sport": sport, "season": season, "schedule_games": len(sched),
                         "home_teams": len({g["home"] for g in sched}), "sampled": len(picks)})
            for g in picks:
                jobs.append((sport, season, g["gamePk"]))
                g["sport"], g["season"] = sport, season
                plan[-1].setdefault("_games", []).append(g)
    log(f"probe sample: {len(jobs)} games over {len(plan)} (level, season) cells")
    fetch_stats = _run_pool(jobs, fetch_feed, PROBE_WORKERS, log=log, label="probe") if fetch else None
    games = []
    for cell in plan:
        for g in cell.pop("_games", []):
            p = feed_path(g["sport"], g["season"], g["gamePk"])
            if not p.exists():
                continue
            cov = game_coverage(read_gz(p))
            games.append({"gamePk": g["gamePk"], "sport": g["sport"], "level": SPORTS[g["sport"]],
                          "season": g["season"], "half": g["half"], "sched_date": g["date"], **cov})
    return {"plan": plan, "fetch": fetch_stats, "games": games}


_LV_ORDER_C = {"AAA": 0, "AA": 1, "A+": 2, "A": 3}


def coverage_tables(games: list[dict]) -> dict:
    cells, venues = {}, {}
    for g in games:
        key = (g["level"], g["season"])
        c = cells.setdefault(key, {"level": g["level"], "sport": g["sport"], "season": g["season"],
                                   "games": 0, "games_with_pitches": 0, "pitches": 0,
                                   "tracked_games": {f: 0 for f in FIELDS}, "venues": set(),
                                   "venues_velo": set()})
        c["games"] += 1
        c["games_with_pitches"] += int(g["pitches"] > 0)
        c["pitches"] += g["pitches"]
        c["venues"].add(g["venue"])
        for f in FIELDS:
            c["tracked_games"][f] += int(bool(g["tracked"][f]))
        if g["tracked"]["startSpeed"]:
            c["venues_velo"].add(g["venue"])
        v = venues.setdefault((g["level"], g["season"], g["venue"]),
                              {"level": g["level"], "season": g["season"], "venue": g["venue"],
                               "home": g["home"], "games": 0, "velo_games": 0, "spin_games": 0,
                               "ev_games": 0})
        v["games"] += 1
        v["velo_games"] += int(bool(g["tracked"]["startSpeed"]))
        v["spin_games"] += int(bool(g["tracked"]["spinRate"]))
        v["ev_games"] += int(bool(g["tracked"]["launchSpeed"]))
    out_cells = []
    for key in sorted(cells, key=lambda k: (-{"AAA": 3, "AA": 2, "A+": 1, "A": 0}[k[0]], k[1])):
        c = cells[key]
        n = c["games"]
        share = {f: round(c["tracked_games"][f] / n, 4) if n else None for f in FIELDS}
        velo = share["startSpeed"] is not None and share["startSpeed"] >= CELL_COVERED_SHARE
        full = all(share[f] is not None and share[f] >= CELL_COVERED_SHARE for f in FULL_SET)
        out_cells.append({"level": c["level"], "sport": c["sport"], "season": c["season"], "games": n,
                          "games_with_pitches": c["games_with_pitches"], "pitches": c["pitches"],
                          "tracked_game_share": share, "venues": len(c["venues"]),
                          "venues_with_velo": len(c["venues_velo"]),
                          "velo_covered": velo, "full_covered": full})
    out_venues = sorted(venues.values(), key=lambda v: (v["level"], v["season"], str(v["venue"])))
    real = any(c["velo_covered"] for c in out_cells
               if c["sport"] in SUB_AAA and c["season"] in LABEL_SEASONS)
    leagues: dict = {}
    for g in games:
        if g["sport"] not in SUB_AAA:
            continue
        lg = leagues.setdefault((g["level"], g.get("league")),
                                {"level": g["level"], "league": g.get("league"), "games": 0,
                                 "velo_games": 0, "seasons": set(), "seasons_with_velo": set()})
        lg["games"] += 1
        lg["seasons"].add(g["season"])
        if g["tracked"]["startSpeed"]:
            lg["velo_games"] += 1
            lg["seasons_with_velo"].add(g["season"])
    by_league = [dict(v, seasons=sorted(v["seasons"]), seasons_with_velo=sorted(v["seasons_with_velo"]))
                 for _, v in sorted(leagues.items(), key=lambda kv: (_LV_ORDER_C[kv[0][0]], str(kv[0][1])))]
    partial = [g for g in games if g["sport"] in SUB_AAA and not g["tracked"]["startSpeed"]]
    max_untracked = max((((g.get("share") or {}).get("startSpeed") or 0.0) for g in partial), default=None)
    return {"cells": out_cells, "venues": out_venues, "coverage_real": real,
            "by_league_sub_aaa": by_league,
            "sub_aaa_untracked_games": len(partial),
            "sub_aaa_untracked_max_velo_share": max_untracked,
            "rule": {"game_tracked_share": GAME_TRACKED_SHARE, "cell_covered_share": CELL_COVERED_SHARE,
                     "full_set": list(FULL_SET)}}


def covered_cells(cov: dict) -> list[tuple[int, int]]:
    return [(c["sport"], c["season"]) for c in cov["cells"]
            if c["sport"] in SUB_AAA and c["season"] in LABEL_SEASONS and c["velo_covered"]]


# ------------------------------------------------------------------------- full fetch

def full_fetch(cells: list[tuple[int, int]], *, log=print) -> dict:
    jobs = []
    for sport, season in cells:
        for g in schedule(sport, season):
            jobs.append((sport, season, g["gamePk"]))
    log(f"full fetch: {len(jobs)} games over {len(cells)} cells")
    return _run_pool(jobs, fetch_pbp, FULL_WORKERS, log=log, label="full")


# -------------------------------------------------------------------------- aggregate

def _q(vals, q):
    return float(np.quantile(np.asarray(vals, dtype=np.float64), q)) if vals else None


def _in_zone(pd: dict) -> bool | None:
    z = pd.get("zone")
    if z is not None:
        try:
            z = int(z)
        except (TypeError, ValueError):
            z = None
        if z is not None:
            if 1 <= z <= 9:
                return True
            if 11 <= z <= 14:
                return False
    co = pd.get("coordinates") or {}
    px, pz = co.get("pX"), co.get("pZ")
    top, bot = pd.get("strikeZoneTop"), pd.get("strikeZoneBottom")
    if None in (px, pz, top, bot):
        return None
    return abs(float(px)) <= ZONE_HALF_WIDTH_FT and float(bot) <= float(pz) <= float(top)


class _Acc:
    __slots__ = ("pitches", "fb_v", "fb_spin", "fb_ivb", "swings", "whiffs", "out_n", "out_sw",
                 "z_sw", "z_con", "ev", "pa_tracked", "max_date", "min_date")

    def __init__(self):
        self.pitches = 0
        self.fb_v, self.fb_spin, self.fb_ivb, self.ev = [], [], [], []
        self.swings = self.whiffs = self.out_n = self.out_sw = self.z_sw = self.z_con = 0
        self.pa_tracked = 0
        self.max_date = self.min_date = None


def aggregate(cells: list[tuple[int, int]], *, sched: dict | None = None, log=print) -> dict:
    """{side: {(pid, season, level): {metric: value, "_n": exposure, "_max_date": d}}}"""
    acc = {"pit": {}, "hit": {}}
    t0 = time.time()
    n_games = 0
    for sport, season in cells:
        level = SPORTS[sport]
        games = sched[(sport, season)] if sched else schedule(sport, season)
        for g in games:
            p = pbp_path(sport, season, g["gamePk"])
            if not p.exists():
                continue
            d = g["date"]
            assert d and d[:4] == str(season), f"game {g['gamePk']} date {d} outside season {season}"
            n_games += 1
            for play in read_gz(p).get("allPlays") or []:
                mu = play.get("matchup") or {}
                bid = (mu.get("batter") or {}).get("id")
                pid = (mu.get("pitcher") or {}).get("id")
                evs = [e for e in play.get("playEvents") or [] if e.get("isPitch")]
                if not evs:
                    continue
                pa_all_tracked = all((e.get("pitchData") or {}).get("startSpeed") is not None for e in evs)
                ka, kb = (int(pid), season, level) if pid else None, (int(bid), season, level) if bid else None
                ap = acc["pit"].setdefault(ka, _Acc()) if ka else None
                ah = acc["hit"].setdefault(kb, _Acc()) if kb else None
                for a in (ap, ah):
                    if a is not None:
                        a.max_date = d if a.max_date is None or d > a.max_date else a.max_date
                        a.min_date = d if a.min_date is None or d < a.min_date else a.min_date
                if ah is not None and pa_all_tracked and (play.get("result") or {}).get("eventType"):
                    ah.pa_tracked += 1
                for e in evs:
                    pd = e.get("pitchData") or {}
                    if pd.get("startSpeed") is None:
                        continue
                    det = e.get("details") or {}
                    code = (det.get("call") or {}).get("code") or det.get("code")
                    ptype = (det.get("type") or {}).get("code")
                    swing = code in SWING
                    whiff = code in WHIFF
                    zone = _in_zone(pd)
                    hd = e.get("hitData") or {}
                    ls = hd.get("launchSpeed") if det.get("isInPlay") else None
                    for a in (ap, ah):
                        if a is None:
                            continue
                        a.pitches += 1
                        a.swings += int(swing)
                        a.whiffs += int(whiff)
                        if zone is False:
                            a.out_n += 1
                            a.out_sw += int(swing)
                        elif zone is True and swing:
                            a.z_sw += 1
                            a.z_con += int(not whiff)
                        if ls is not None:
                            a.ev.append(float(ls))
                    if ap is not None and ptype in FASTBALLS:
                        ap.fb_v.append(float(pd["startSpeed"]))
                        br = pd.get("breaks") or {}
                        if br.get("spinRate") is not None:
                            ap.fb_spin.append(float(br["spinRate"]))
                        if br.get("breakVerticalInduced") is not None:
                            ap.fb_ivb.append(float(br["breakVerticalInduced"]))
        log(f"  aggregate {level} {season}: {n_games} games read ({time.time() - t0:.0f} s)")
    out = {"pit": {}, "hit": {}}
    for key, a in acc["pit"].items():
        if a.pitches < PIT_MIN_PITCHES:
            continue
        out["pit"][key] = {
            "fb_velo_p50": _q(a.fb_v, 0.5) if len(a.fb_v) >= MIN_FB else None,
            "fb_velo_p95": _q(a.fb_v, 0.95) if len(a.fb_v) >= MIN_FB else None,
            "fb_spin": float(np.mean(a.fb_spin)) if len(a.fb_spin) >= MIN_FB else None,
            "fb_ivb": float(np.mean(a.fb_ivb)) if len(a.fb_ivb) >= MIN_FB else None,
            "whiff": a.whiffs / a.swings if a.swings >= MIN_SWINGS else None,
            "chase": a.out_sw / a.out_n if a.out_n >= MIN_SWINGS else None,
            "ev_against_p50": _q(a.ev, 0.5) if len(a.ev) >= MIN_BIP else None,
            "_n": a.pitches, "_max_date": a.max_date, "_min_date": a.min_date}
    for key, a in acc["hit"].items():
        if a.pa_tracked < HIT_MIN_PA:
            continue
        out["hit"][key] = {
            "ev_p50": _q(a.ev, 0.5) if len(a.ev) >= MIN_BIP else None,
            "ev_p90": _q(a.ev, 0.9) if len(a.ev) >= MIN_BIP else None,
            "hard_hit": (sum(1 for x in a.ev if x >= HARD_HIT_MPH) / len(a.ev)) if len(a.ev) >= MIN_BIP else None,
            "whiff": a.whiffs / a.swings if a.swings >= MIN_SWINGS else None,
            "chase": a.out_sw / a.out_n if a.out_n >= MIN_SWINGS else None,
            "zone_contact": a.z_con / a.z_sw if a.z_sw >= MIN_SWINGS else None,
            "_n": a.pa_tracked, "_max_date": a.max_date, "_min_date": a.min_date}
    return out


def candidate_metrics(cov: dict, cells: list[tuple[int, int]]) -> dict:
    """Section 4: a metric enters when each source field is tracked in at least half the
    sampled games of every contributing cell."""
    share = {(c["sport"], c["season"]): c["tracked_game_share"] for c in cov["cells"]}
    out = {}
    for side, metrics in (("pit", PIT_METRICS), ("hit", HIT_METRICS)):
        keep, drop = [], {}
        for m, fields in metrics.items():
            bad = [f"{SPORTS[s]} {y} {f}" for (s, y) in cells for f in fields
                   if (share.get((s, y)) or {}).get(f) is None or share[(s, y)][f] < CELL_COVERED_SHARE]
            if bad:
                drop[m] = bad
            else:
                keep.append(m)
        out[side] = {"metrics": keep, "dropped": drop}
    return out


# ------------------------------------------------------------------------------- read

def build_rows(side: str, agg: dict, metrics: list[str], *, mlb: dict, war: dict, cons: dict) -> list[dict]:
    import efv5_tracking_head as TH
    picked: dict = {}
    for (pid, season, level), vals in agg[side].items():
        if season not in LABEL_SEASONS:
            continue
        m = {k: vals.get(k) for k in metrics}
        if any(v is None for v in m.values()):
            continue
        cur = picked.get((pid, season))
        if cur is None or LEVEL_RANK[level] > LEVEL_RANK[cur[0]]:
            picked[(pid, season)] = (level, m, vals["_max_date"])
    rows = []
    for (pid, season), (level, m, max_date) in sorted(picked.items()):
        cr = cons.get((pid, season))
        if cr is None:
            continue
        y = TH.labels3(pid, season, mlb, war)
        if y is None:
            continue
        as_of = f"{season + 1}-01-01"
        assert max_date is not None and max_date < as_of, (pid, season, max_date)
        rows.append({"pid": pid, "season": season, "level": level, "player_key": cr["player_key"],
                     "fv": float(cr["fv"]), "m": m, "reach3": y["reach3"], "rate3": y["rate3"],
                     "spent": TH.spent(season), "as_of": as_of, "max_input_date": max_date})
    return rows


def _mu_sd(vals):
    v = np.asarray(vals, dtype=np.float64)
    if v.size == 0:
        return 0.0, 1.0
    sd = float(v.std())
    return float(v.mean()), (sd if sd > 1e-12 else 1.0)


def design(rows: list[dict], metrics: list[str], mom: dict) -> np.ndarray:
    cols = [np.ones(len(rows)), np.array([float(LEVEL_RANK[r["level"]]) for r in rows])]
    mu, sd = mom["fv"]
    cols.append((np.array([r["fv"] for r in rows]) - mu) / sd)
    for k in metrics:
        mu, sd = mom[k]
        cols.append((np.array([r["m"][k] for r in rows]) - mu) / sd)
    return np.column_stack(cols)


def moments(rows, metrics):
    out = {"fv": _mu_sd([r["fv"] for r in rows])}
    for k in metrics:
        out[k] = _mu_sd([r["m"][k] for r in rows])
    return out


def fit(rows, metrics, lam):
    import efv5_tracking_head as TH
    mom = moments(rows, metrics)
    X = design(rows, metrics, mom)
    y_r = np.array([r["reach3"] for r in rows])
    y_w = np.array([r["rate3"] for r in rows])
    w_r = TH.fit_logistic(X, y_r, lam)
    reached = y_r > 0
    w_w = TH.fit_ridge(X[reached], y_w[reached], lam)
    return {"mom": mom, "w_r": w_r, "w_w": w_w}


def oof(rows, metrics, folds, lam) -> np.ndarray:
    import efv5_tracking_head as TH
    out = np.full(len(rows), np.nan)
    for f in np.unique(folds):
        te, tr = folds == f, folds != f
        tr_rows = [r for r, t in zip(rows, tr) if t]
        te_rows = [r for r, t in zip(rows, te) if t]
        ft = fit(tr_rows, metrics, lam)
        out[te] = TH.order_head(ft["w_r"], ft["w_w"], design(te_rows, metrics, ft["mom"]))
    return out


def read_frame(rows: list[dict], metrics: list[str], *, B: int, seed: int) -> dict:
    import efv5_atlas as A
    import efv5_tracking_head as TH
    ok, why = TH.readable(rows)
    if not rows:
        return {"n": 0, "readable": False, "unreadable_reason": why}
    folds = A.player_folds(np.array([r["pid"] for r in rows]), FOLDS, seed)
    scores = {"head": oof(rows, metrics, folds, LAMBDA), "base": oof(rows, metrics, folds, math.inf),
              "consensus": np.array([r["fv"] for r in rows])}
    rep = TH.compare(rows, scores, B=B, seed=seed)
    rep["readable"], rep["unreadable_reason"] = ok, why
    d = rep["deltas"].get("head_minus_base") or {}
    a, r = d.get("auc_reach3") or {}, d.get("rho_rate3") or {}
    lo = (a.get("ci95") or [None, None])[0]
    rep["incremental_signal"] = bool(ok and a.get("point") is not None and r.get("point") is not None
                                     and a["point"] > 0 and r["point"] > 0 and lo is not None and lo > 0)
    rep["level_counts"] = {lv: sum(1 for x in rows if x["level"] == lv) for lv in LEVEL_RANK}
    return rep


def coefficients(rows, metrics) -> dict:
    if len(rows) < 10:
        return {}
    ft = fit(rows, metrics, LAMBDA)
    return {"reach": {k: round(float(ft["w_r"][3 + i]), 4) for i, k in enumerate(metrics)},
            "rate": {k: round(float(ft["w_w"][3 + i]), 4) for i, k in enumerate(metrics)},
            "consensus_reach": round(float(ft["w_r"][2]), 4), "consensus_rate": round(float(ft["w_w"][2]), 4)}


def run_read(doc: dict, *, B: int, seed: int, log=print) -> dict:
    import efv5_atlas as A
    import efv_vintage_frame as F
    cov = doc["coverage"]
    cells = covered_cells(cov)
    doc["covered_cells"] = [{"sport": s, "level": SPORTS[s], "season": y} for s, y in cells]
    if not cov["coverage_real"]:
        doc["read"] = {"status": "not run: coverage below AAA is not REAL by the section 3 rule"}
        return doc
    cand = candidate_metrics(cov, cells)
    doc["candidates"] = cand
    for V in CONSENSUS_VINTAGES:
        assert V not in F.RESERVED_LV
    t0 = time.time()
    agg = aggregate(cells, log=log)
    doc["aggregate"] = {side: {"lines": len(agg[side]),
                               "by_cell": [{"level": SPORTS[s], "season": y,
                                            "lines": sum(1 for k in agg[side] if k[1] == y and k[2] == SPORTS[s])}
                                           for s, y in cells]} for side in agg}
    mlb = A.mlb_seasons()
    war, vintage_id = A.fwar_totals()
    listings = A.load_listings()
    universe = F.load_universe()
    doc["inputs"] = {"fwar_vintage_id": vintage_id, "aggregate_seconds": round(time.time() - t0, 1)}
    doc["read"] = {}
    for side in ("hit", "pit"):
        metrics = cand[side]["metrics"]
        cons = A.consensus_reads(side, listings, vintages=CONSENSUS_VINTAGES, universe=universe, log=log)
        rows = build_rows(side, agg, metrics, mlb=mlb, war=war, cons=cons)
        clean = [r for r in rows if r["season"] in CLEAN_COHORTS]
        frame = {}
        for y in LABEL_SEASONS:
            for lv in LEVEL_RANK:
                sub = [r for r in rows if r["season"] == y and r["level"] == lv]
                if sub:
                    frame.setdefault(str(y), {})[lv] = {"rows": len(sub),
                                                        "reached": int(sum(r["reach3"] for r in sub)),
                                                        "spent": bool(sub[0]["spent"])}
        out = {"metrics": metrics, "rows": len(rows), "frame": frame,
               "max_input_date_by_cohort": {str(y): max((r["max_input_date"] for r in rows if r["season"] == y), default=None)
                                            for y in LABEL_SEASONS},
               "clean": read_frame(clean, metrics, B=B, seed=seed) if metrics else {"readable": False, "unreadable_reason": "no candidate metric"},
               "pooled": read_frame(rows, metrics, B=B, seed=seed + 1) if metrics else {"readable": False, "unreadable_reason": "no candidate metric"},
               "coefficients_clean": coefficients(clean, metrics) if metrics else {}}
        out["pooled"]["spent"] = True
        out["pooled"]["note"] = SPENT_NOTE
        doc["read"][side] = out
        log(f"  {side}: {len(rows)} rows ({len(clean)} clean)")
    return doc


# --------------------------------------------------------------------------- artifact

#: The network pass that filled the sample cache (2026-10-15, from its run log); a later
#: rerun reads the cache and carries this receipt forward.
FIRST_FETCH = {"date": "2026-10-15", "fetched": 1439, "cached": 1, "failed": 0, "seconds": 529.6,
               "requests": 1443, "note": "1,439 sampled feeds plus 4 schedule reads (2026); one feed was "
                                         "cached by the producer's smoke test"}

GAME_KEEP = ("gamePk", "sport", "level", "season", "half", "date", "venue_id", "venue", "home",
             "league", "pitches", "bip", "share")


def _write(doc: dict, path: Path = OUT_PATH) -> None:
    """indent 1, with each sampled game on one line (the list is long)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dflt = lambda o: sorted(o) if isinstance(o, set) else str(o)  # noqa: E731
    games = (doc.get("probe") or {}).get("games")
    if games is None:
        txt = json.dumps(doc, indent=1, default=dflt)
    else:
        mark = "__X4_GAMES__"
        shell = dict(doc, probe=dict(doc["probe"], games=mark))
        body = ",\n".join("   " + json.dumps(g, separators=(",", ":"), default=dflt) for g in games)
        txt = json.dumps(shell, indent=1, default=dflt).replace(json.dumps(mark), "[\n" + body + "\n  ]")
    path.write_text(txt + "\n", encoding="utf-8", newline="\n")


def base_doc() -> dict:
    return {"schema": SCHEMA, "generated_at": _now(), "tool": TOOL, "item": ITEM, "note": NOTE,
            "role": "development", "served": False, "ships": False, "spent_note": SPENT_NOTE,
            "registration": {"doc": "docs/efv-x4-pitch-probe/REGISTRATION.md", "sha256": _sha(GATE_DOC),
                             "git_head_at_run": _git_head(),
                             "early_read": "owner-waived early read (EW3-5): the read runs on the registration's own day"},
            "declared": {"sports": SPORTS, "seasons": SEASONS, "label_seasons": LABEL_SEASONS,
                         "early_cut": EARLY_MMDD, "late_cut": LATE_MMDD,
                         "game_tracked_share": GAME_TRACKED_SHARE, "cell_covered_share": CELL_COVERED_SHARE,
                         "full_set": FULL_SET, "lambda": LAMBDA, "folds": FOLDS, "seed": SEED,
                         "pit_min_pitches": PIT_MIN_PITCHES, "hit_min_pa": HIT_MIN_PA,
                         "min_fb": MIN_FB, "min_bip": MIN_BIP, "min_swings": MIN_SWINGS}}


# ------------------------------------------------------------------------- documents

_LV_ORDER = {"AAA": 0, "AA": 1, "A+": 2, "A": 3}


def _pct(v) -> str:
    return "" if v is None else f"{100.0 * v:.0f}%"


def _f4(v) -> str:
    return "" if v is None else f"{v:+.4f}"


def _ci(d: dict) -> str:
    ci = d.get("ci95")
    return "" if not ci or None in ci else f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def _write_crlf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").replace("\n", "\r\n"), encoding="utf-8", newline="")


def coverage_md(doc: dict) -> str:
    cov = doc["coverage"]
    pr = doc["probe"]
    fs = pr.get("first_fetch") or pr.get("fetch") or {}
    L = ["# StatsAPI pitch tracking below Triple-A: coverage tables", "",
         f"Generated {doc.get('generated_at')} by `{TOOL}` from `data/_labs/efv_x4_pitch_probe.json`. "
         "Registration: `docs/efv-x4-pitch-probe/REGISTRATION.md` (sha256 "
         f"{(doc['registration'].get('sha256') or '')[:12]}). Development probe; ships nothing.", "",
         f"Sample: {len(pr['games'])} games read ({fs.get('fetched', 0)} fetched, {fs.get('cached', 0)} "
         f"already cached, {fs.get('failed', 0)} failed, in the first network pass), two per home team, level and season "
         "(the first home game on or after May 15 and on or after Aug 1), each the raw "
         "`/api/v1.1/game/{gamePk}/feed/live` JSON cached under `.cache/efv_x4_pitch/feeds/`. A game is "
         f"tracked for a field when the field is present on at least {int(GAME_TRACKED_SHARE * 100)} percent "
         "of its pitches (of its balls in play for launch speed and angle). A cell is VELO-COVERED when "
         "release speed is tracked in at least half its sampled games, FULL-COVERED when release speed, "
         "spin, induced vertical break, extension, plate location, launch speed and launch angle each are.",
         "", "## 1. Share of sampled games tracked, by level and season", ""]
    cols = list(FIELDS)
    L.append("| level | season | games | venues | " + " | ".join(FIELD_NAMES[f] for f in cols)
             + " | VELO-COVERED | FULL-COVERED |")
    L.append("|---|---|---|---|" + "---|" * len(cols) + "---|---|")
    for c in sorted(cov["cells"], key=lambda c: (_LV_ORDER[c["level"]], c["season"])):
        sh = c["tracked_game_share"]
        L.append(f"| {c['level']} | {c['season']} | {c['games']} | {c['venues']} | "
                 + " | ".join(_pct(sh.get(f)) for f in cols)
                 + f" | {'yes' if c['velo_covered'] else 'no'} | {'yes' if c['full_covered'] else 'no'} |")
    L += ["", "The last field column, the stringer's pixel location, is an extra the registration did "
          "not name (it was seen on the first sampled feed) and enters no rule: it is the Gameday "
          "operator's click on a drawn zone, not a measured location.", "",
          "## 2. Release speed by park", "",
          "Games with release speed tracked over games sampled, per venue and season (the venue as the "
          "feed names it).", ""]
    by: dict = {}
    for v in cov["venues"]:
        by.setdefault((v["level"], v["venue"]), {})[v["season"]] = v
    L.append("| level | venue | " + " | ".join(str(y) for y in SEASONS) + " |")
    L.append("|---|---|" + "---|" * len(SEASONS))
    for (lv, venue) in sorted(by, key=lambda k: (_LV_ORDER[k[0]], str(k[1]))):
        row = by[(lv, venue)]
        cells = ["" if row.get(y) is None else f"{row[y]['velo_games']}/{row[y]['games']}" for y in SEASONS]
        L.append(f"| {lv} | {venue} | " + " | ".join(cells) + " |")
    sub = [c for c in cov["cells"] if c["sport"] in SUB_AAA]
    velo = [f"{c['level']} {c['season']}" for c in sub if c["velo_covered"]]
    aaa = [f"{c['season']} {_pct(c['tracked_game_share'].get('startSpeed'))}"
           for c in sorted(cov["cells"], key=lambda c: c["season"]) if c["sport"] == 11]
    L += ["", "## 3. Release speed by league below Triple-A", "",
          "| level | league (as the feed names it) | seasons sampled | games sampled | games tracked |",
          "|---|---|---|---|---|"]
    for x in cov.get("by_league_sub_aaa") or []:
        ss = x["seasons"]
        span = f"{ss[0]}" if len(ss) == 1 else f"{ss[0]} to {ss[-1]}"
        L.append(f"| {x['level']} | {x['league']} | {span} | {x['games']} | {x['velo_games']} |")
    L += ["", "## 4. Verdict by the registered rule", "",
          "- Coverage below Triple-A REAL (a sub-AAA cell of 2021 to 2023 VELO-COVERED): "
          f"**{'yes' if cov['coverage_real'] else 'no'}**.",
          f"- Sub-AAA cells VELO-COVERED, any season: {', '.join(velo) if velo else 'none'}.",
          f"- Control, Triple-A release speed share of sampled games by season: {', '.join(aaa)}."]
    for line in doc.get("coverage_notes") or []:
        L.append(f"- {line}")
    return "\n".join(L) + "\n"


def results_md(doc: dict) -> str:
    cov = doc["coverage"]
    L = ["# StatsAPI pitch tracking below Triple-A: results in plain language", "",
         f"Generated {doc.get('generated_at')} by `{TOOL}`. Registration "
         "`docs/efv-x4-pitch-probe/REGISTRATION.md`, read the same day as an owner-waived early read "
         "(EW3-5). Tables: `docs/efv-x4-pitch-probe/COVERAGE.md`. Nothing served moves.", "",
         "## What was asked", "",
         "Savant's public minor-league data covers only Triple-A (from 2022) and the Florida State "
         "League (from 2021). The question was whether MLB's free game feeds (StatsAPI) carry pitch "
         "tracking (velocity, spin, movement, extension, location, exit velocity and launch angle) for "
         "Double-A, High-A and Single-A games, in which seasons and parks, and if so whether that data "
         "tells us anything about prospects that consensus does not.", "",
         "## What we found", ""]
    sub = [c for c in cov["cells"] if c["sport"] in SUB_AAA]
    for lv in ("AA", "A+", "A"):
        cs = sorted((c for c in sub if c["level"] == lv), key=lambda c: c["season"])
        L.append(f"- {lv}: share of sampled games with release speed on 80 percent or more of pitches: "
                 + ", ".join(f"{c['season']} {_pct(c['tracked_game_share'].get('startSpeed'))}" for c in cs) + ".")
    aaa = sorted((c for c in cov["cells"] if c["sport"] == 11), key=lambda c: c["season"])
    L.append("- Triple-A (the control): " + ", ".join(
        f"{c['season']} {_pct(c['tracked_game_share'].get('startSpeed'))}" for c in aaa) + ".")
    for line in doc.get("plain_findings") or []:
        L.append(f"- {line}")
    L += ["", "## The descriptive signal read", ""]
    rd = doc.get("read") or {}
    if "status" in rd:
        L.append(f"{rd['status'][:1].upper()}{rd['status'][1:]}. The registration stops the probe here: no aggregate is built "
                 "and no outcome is read, because the data does not exist below Triple-A on this source.")
    else:
        L.append("head = consensus FV plus level plus the tracked metrics; base = consensus FV plus level; "
                 "both out of fold. AUC against reaching MLB within 3 seasons, Spearman against fWAR per "
                 "MLB season over those seasons. Signal = head beats base on both and the AUC gain's CI95 "
                 "sits above zero (descriptive; ships nothing).")
        L.append("")
        for side in ("hit", "pit"):
            r = rd.get(side) or {}
            L += [f"### {'Hitters' if side == 'hit' else 'Pitchers'}", "",
                  f"Metrics: {', '.join(METRIC_NAMES[m] for m in r.get('metrics', [])) or 'none'}; rows {r.get('rows')}.", "",
                  "| frame | rows (reached) | head AUC / rho | base AUC / rho | consensus AUC / rho | "
                  "head minus base AUC (CI95) | head minus base rho (CI95) | signal |",
                  "|---|---|---|---|---|---|---|---|"]
            for fr in ("clean", "pooled"):
                x = r.get(fr) or {}
                sc = x.get("scores") or {}
                d = (x.get("deltas") or {}).get("head_minus_base") or {}
                da, dr = d.get("auc_reach3") or {}, d.get("rho_rate3") or {}

                def ar(k, sc=sc):
                    s = sc.get(k) or {}
                    return f"{_f4(s.get('auc_reach3'))} / {_f4(s.get('rho_rate3'))}"
                lab = "clean (S 2021)" if fr == "clean" else "pooled (S 2021 to 2023, spent)"
                sig = "yes" if x.get("incremental_signal") else ("no" if x.get("readable") else "unreadable")
                L.append(f"| {lab} | {x.get('n', 0)} ({x.get('reach3_pos', '')}) | {ar('head')} | {ar('base')} | "
                         f"{ar('consensus')} | {_f4(da.get('point'))} {_ci(da)} | {_f4(dr.get('point'))} {_ci(dr)} | {sig} |")
            L.append("")
    L += ["", "## What happens next", ""]
    for line in doc.get("next_steps") or []:
        L.append(f"- {line}")
    return "\n".join(L) + "\n"


SAVANT_CENSUS = ROOT / "data" / "_labs" / "efv5" / "tracking_coverage.json"
FSL_NAME = "Florida State League"
#: The Florida State League played 2021 as "Low-A Southeast" (the one-season league names).
FSL_NAMES = frozenset({FSL_NAME, "Low-A Southeast"})


def derive_findings(doc: dict) -> dict:
    """The plain-language findings, every one computed from the coverage tables (no
    hand-typed number)."""
    cov = doc["coverage"]
    lg = cov.get("by_league_sub_aaa") or []
    tracked_lg = [x for x in lg if x["velo_games"] > 0]
    untracked_lg = [x for x in lg if x["velo_games"] == 0]
    sub = [c for c in cov["cells"] if c["sport"] in SUB_AAA]
    aa_hi = [c for c in sub if c["level"] in ("AA", "A+")]
    aa_hi_zero = all((c["tracked_game_share"].get("startSpeed") or 0.0) == 0.0 for c in aa_hi)
    a_tracked_names = sorted({x["league"] for x in tracked_lg if x["level"] == "A"})
    fsl_rows = [x for x in lg if x["level"] == "A" and x["league"] in FSL_NAMES]
    fsl = ({"games": sum(x["games"] for x in fsl_rows), "velo_games": sum(x["velo_games"] for x in fsl_rows)}
           if fsl_rows else None)
    fsl_only = bool(a_tracked_names) and set(a_tracked_names) <= FSL_NAMES
    fsl_dark = sorted({str(g.get("venue")) for g in (doc.get("probe") or {}).get("games", [])
                       if g["sport"] == 14 and g.get("league") in FSL_NAMES
                       and ((g.get("share") or {}).get("startSpeed") or 0.0) < GAME_TRACKED_SHARE})
    aaa = {c["season"]: c for c in cov["cells"] if c["sport"] == 11}
    findings = []
    findings.append(
        f"Double-A and High-A: {'no' if aa_hi_zero else 'some'} sampled game in any season 2021 to 2026 "
        "carries release speed, spin, movement, extension, plate location or exit velocity "
        f"({sum(c['games'] for c in aa_hi)} games, {sum(c['venues'] for c in aa_hi)} venue-seasons). "
        "The feeds hold only the pitch call, the count, the batted-ball type and the stringer's pixel click.")
    if fsl is not None:
        findings.append(
            f"Single-A: the tracked games are {'all' if fsl_only else 'not only'} in the {FSL_NAME} (named "
            f"Low-A Southeast in 2021; {fsl['velo_games']} of its {fsl['games']} sampled games tracked); the other Single-A leagues "
            f"({', '.join(x['league'] for x in untracked_lg if x['level'] == 'A' and x['league'] not in FSL_NAMES) or 'none'}) "
            "carry none. So Single-A cells sit near the Florida State League's share of Single-A games and never "
            "reach the 50 percent bar.")
        if fsl_dark:
            findings.append("Florida State League venues with an untracked sampled game: " + ", ".join(fsl_dark) + ".")
    findings.append(
        f"Of the {cov.get('sub_aaa_untracked_games')} untracked sub-AAA games, the largest share of pitches with "
        f"a release speed is {_pct(cov.get('sub_aaa_untracked_max_velo_share'))}: tracking is all or nothing by park.")
    sav_2022 = None
    try:
        probes = json.loads(SAVANT_CENSUS.read_text(encoding="utf-8"))["verified_coverage"]["probes"]
        sav_2022 = next((p for p in probes if p.get("season") == 2022), None)
    except (OSError, KeyError, ValueError):
        pass
    if 2022 in aaa and 2023 in aaa:
        later = [aaa[y] for y in sorted(aaa) if y >= 2023]
        all_later = all(c["venues_with_velo"] == c["venues"] for c in later)
        line = (f"The Triple-A control: tracking in {aaa[2021]['venues_with_velo'] if 2021 in aaa else 0} parks "
                f"in 2021, {aaa[2022]['venues_with_velo']} of {aaa[2022]['venues']} sampled parks in 2022, and "
                f"{'every' if all_later else 'not every'} sampled park from 2023.")
        if sav_2022:
            line += (f" Savant's one probe day of 2022 ({sav_2022['day']}) served {len(sav_2022['home_parks'])} home "
                     "parks across Triple-A and the Florida State League, so in 2022 StatsAPI is, if anything, "
                     "thinner than Savant, not richer.")
        findings.append(line)
    sav = None
    try:
        sav = json.loads(SAVANT_CENSUS.read_text(encoding="utf-8"))["verified_coverage"]["summary"]
    except (OSError, KeyError, ValueError):
        pass
    if sav:
        findings.append(f"Savant's census of 2026-10-14 reads: \"{sav}\". StatsAPI tracks the same levels and the same "
                        "Single-A league, so it adds no tracked level or league over Savant's public minors data "
                        "(the tracking-era head already reads the Florida State League and Triple-A from Savant).")
    tl = ", ".join("%s %s (%d/%d)" % (x["level"], x["league"], x["velo_games"], x["games"]) for x in tracked_lg)
    notes = [f"Sub-AAA leagues with a tracked sampled game (tracked/sampled): {tl or 'none'}."]
    nxt = ["Nothing ships and nothing served moves. The registration's rule stops the probe at the coverage "
           "tables: no aggregate is built and no outcome is read, because the data does not exist below "
           "Triple-A outside the Florida State League, which the tracking-era head already reads from Savant.",
           "EFV_X3_POOLED_MODEL should take Double-A and High-A as box-score and pitch-call levels only "
           "(chase and zone contact need a measured location, which does not exist there; whiff, called-strike "
           "and contact rates need only the pitch call, and the eFV v4 playByPlay cache already holds the "
           "calls of the 2021 to 2025 games).",
           "A new tracked level would show up in this same sample at no cost: rerun "
           "`python tools/efv_x4_pitch_probe.py --probe` after a future season (the cache keeps every sampled "
           "feed), and a level that turns VELO-COVERED re-registers before any read."]
    return {"plain_findings": findings, "coverage_notes": notes, "next_steps": nxt}


def write_docs(doc: dict) -> None:
    _write_crlf(COVERAGE_DOC, coverage_md(doc))
    _write_crlf(RESULTS_DOC, results_md(doc))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--b", type=int, default=B_DEFAULT)
    args = ap.parse_args(argv)
    if args.probe:
        doc = base_doc()
        prior = None
        try:
            prior = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("probe") or {}
        except (OSError, ValueError):
            pass
        pr = probe()
        doc["probe"] = {"plan": pr["plan"], "fetch": pr["fetch"], "net": dict(NET),
                        "games": [{k: g.get(k) for k in GAME_KEEP} for g in pr["games"]]}
        cur = pr["fetch"] or {}
        doc["probe"]["first_fetch"] = ((prior or {}).get("first_fetch")
                                       or (dict(cur, net=dict(NET)) if cur.get("fetched") else FIRST_FETCH))
        doc["coverage"] = coverage_tables(pr["games"])
        doc["status"] = "probe complete"
        _write(doc)
        print(f"coverage_real {doc['coverage']['coverage_real']}; covered cells {covered_cells(doc['coverage'])}")
    if args.full:
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        cells = covered_cells(doc["coverage"])
        doc["full_fetch"] = full_fetch(cells) if cells else {"status": "no covered cell"}
        doc["full_fetch"]["net"] = dict(NET)
        _write(doc)
    if args.read:
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        doc["generated_at"] = _now()
        doc = run_read(doc, B=args.b, seed=SEED)
        doc.update(derive_findings(doc))
        doc["status"] = "complete"
        _write(doc)
    if args.md:
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        write_docs(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
