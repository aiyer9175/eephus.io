# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""In-house MiLB fielding runs (MFR), to docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md
(task MILB_FIELDING_RUNS, owner decision EW3-33). The gate is the spec; every constant
below is the gate's, by its part number.

Modes:
    fetch [--sport N --season Y] [--max-minutes M]   part 1: StatsAPI playByPlay fielder
                                                     credits, reduced, resumable
    census                                           part 2: coverage per (level, season)
                                                     -> data/milb_fielding_runs_census.json
    build                                            part 3: the measure's season tables
                                                     -> .cache/milb_fielding/tables/
    read [--gate-sha SHA]                            parts 4 and 5, ONCE
                                                     -> data/milb_fielding_runs_eval.json
    read --dry-run                                   the reporting path on fixtures carrying
                                                     None values; reads no real row

The fetch reads no WAR, debut, grade or label column; the census reads coverage only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import sys
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GATE_DOC = "docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md"
CACHE = ROOT / ".cache" / "milb_fielding"
PBP_DIR = CACHE / "pbp"
TABLES = CACHE / "tables"
SCHEDULE_DIR = ROOT / ".cache" / "efv4_pbp" / "schedule"
FEED_CACHE_DIR = ROOT / ".cache" / "game_feeds"
CENSUS_OUT = ROOT / "data" / "milb_fielding_runs_census.json"
EVAL_OUT = ROOT / "data" / "milb_fielding_runs_eval.json"

API = "https://statsapi.mlb.com/api/v1"
USER_AGENT = ("BaseballR-prospect-tracker MiLB fielding-runs research fetch "
              "(one-off, 4 connections max, resumable cache)")

# --- part 1 -----------------------------------------------------------------
SPORTS = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "ROK"}
LEVEL_ORDER = (11, 12, 13, 14, 16)
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
CELL_IN_SHARE = 0.80
MAX_WORKERS = 4
BLACKOUT_UTC_HOURS = range(6, 11)
_REQUEST_SLEEP = 0.05
EXCLUDED_LEAGUES = frozenset({125})
PBP_FIELDS = ",".join((
    "allPlays", "result", "eventType", "about", "atBatIndex", "inning", "isTopInning",
    "count", "outs", "balls", "strikes", "matchup", "batSide", "code", "runners", "movement",
    "originBase", "start", "end", "isOut", "details", "credits", "player", "id", "position",
    "credit", "playEvents", "isPitch", "type", "call", "hitData", "trajectory", "hardness",
    "location", "coordinates", "coordX", "coordY", "pitchData", "pX", "pZ", "strikeZoneTop",
    "strikeZoneBottom", "index",
))
ROW_VERSION = 1
PLAY_COLS = ("ab", "inning", "top", "event", "outs", "bat_side", "last_code", "traj", "hard",
             "loc", "x", "y", "last_idx")
RUNNER_COLS = ("ab", "pidx", "runner", "origin", "start", "end", "is_out", "revent")
CREDIT_COLS = ("ab", "pidx", "revent", "pid", "pos", "credit")
SUB_COLS = ("ab", "eidx", "pid", "pos", "event")
TAKEN_COLS = ("ab", "code", "b", "s", "px", "pz", "top", "bot")
TAKEN_CODES = frozenset({"B", "*B", "C"})
SUB_EVENTS = frozenset({"defensive_substitution", "defensive_switch", "position_switch"})


class FetchWindowClosed(RuntimeError):
    """A network read was attempted inside the 06:00 to 11:00 UTC blackout."""


def _guard() -> None:
    h = datetime.now(timezone.utc).hour
    if h in BLACKOUT_UTC_HOURS:
        raise FetchWindowClosed(f"UTC hour {h:02d} is inside the 06:00 to 11:00 UTC blackout")


_session_lock = threading.Lock()
_session = None


def session():
    global _session
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    with _session_lock:
        if _session is None:
            s = requests.Session()
            retry = Retry(total=6, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504],
                          allowed_methods=frozenset({"GET"}), respect_retry_after_header=True)
            ad = HTTPAdapter(max_retries=retry, pool_connections=MAX_WORKERS,
                             pool_maxsize=MAX_WORKERS)
            s.mount("https://", ad)
            s.headers["User-Agent"] = USER_AGENT
            _session = s
        return _session


def _get_json(url: str, params: dict) -> dict:
    _guard()
    time.sleep(_REQUEST_SLEEP)
    r = session().get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def _atomic_write_gz(path: Path, obj) -> None:
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


def game_path(sport: int, season: int, game_pk: int, base: Path | None = None) -> Path:
    return (base or PBP_DIR) / str(int(sport)) / str(int(season)) / f"{int(game_pk)}.json.gz"


def schedule(sport: int, season: int) -> list[dict]:
    """The cached final regular-season schedule (milb_pbp_fetch's list), Mexican League out."""
    path = SCHEDULE_DIR / f"{int(sport)}_{int(season)}.v2.json.gz"
    if not path.exists():
        return []
    return [g for g in read_gz(path) if g.get("league") not in EXCLUDED_LEAGUES]


def _r2(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 2) if math.isfinite(f) else None


def _pos(c) -> str | None:
    p = (c or {}).get("position") or {}
    return str(p.get("code")) if p.get("code") is not None else None


def reduce_plays(all_plays: list[dict]) -> dict:
    """Compact rows from a playByPlay `allPlays` list (gate part 1, reduced rows)."""
    plays, runners, credits, subs, taken = [], [], [], [], []
    for i, play in enumerate(all_plays or []):
        about = play.get("about") or {}
        ab = play.get("atBatIndex", about.get("atBatIndex", i))
        res = play.get("result") or {}
        evs = play.get("playEvents") or []
        last = None
        last_idx = None
        b0 = s0 = 0
        for j, ev in enumerate(evs):
            cnt = ev.get("count") or {}
            idx = ev.get("index", j)
            if ev.get("isPitch"):
                det = ev.get("details") or {}
                code = (det.get("call") or {}).get("code") or det.get("code")
                last, last_idx = (ev, code), idx
                if code in TAKEN_CODES:
                    pd_ = ev.get("pitchData") or {}
                    co = pd_.get("coordinates") or {}
                    taken.append([ab, code, b0, s0, _r2(co.get("pX")), _r2(co.get("pZ")),
                                  _r2(pd_.get("strikeZoneTop")), _r2(pd_.get("strikeZoneBottom"))])
            elif ev.get("type") == "action":
                det = ev.get("details") or {}
                et = det.get("eventType")
                pl = (ev.get("player") or {}).get("id")
                pos = _pos(ev)
                if et in SUB_EVENTS and pl is not None and pos is not None:
                    subs.append([ab, idx, pl, pos, et])
            b0 = cnt.get("balls", b0)
            s0 = cnt.get("strikes", s0)
        hd = {}
        last_code = None
        if last is not None:
            hd = last[0].get("hitData") or {}
            last_code = last[1]
        co = hd.get("coordinates") or {}
        plays.append([ab, about.get("inning"), 1 if about.get("isTopInning") else 0,
                      res.get("eventType"), (play.get("count") or {}).get("outs"),
                      ((play.get("matchup") or {}).get("batSide") or {}).get("code"),
                      last_code, hd.get("trajectory"), hd.get("hardness"), hd.get("location"),
                      _r2(co.get("coordX")), _r2(co.get("coordY")), last_idx])
        for rn in play.get("runners") or []:
            mv = rn.get("movement") or {}
            det = rn.get("details") or {}
            pidx = det.get("playIndex")
            rev = det.get("eventType")
            runners.append([ab, pidx, (det.get("runner") or {}).get("id"), mv.get("originBase"),
                            mv.get("start"), mv.get("end"), 1 if mv.get("isOut") else 0, rev])
            for c in rn.get("credits") or []:
                pid = (c.get("player") or {}).get("id")
                if pid is None:
                    continue
                credits.append([ab, pidx, rev, pid, _pos(c), c.get("credit")])
    return {"plays": plays, "runners": runners, "credits": credits, "subs": subs,
            "taken": taken}


def game_record(g: dict, sport: int, season: int, all_plays: list[dict], source: str) -> dict:
    rec = {"v": ROW_VERSION, "gamePk": int(g["gamePk"]), "date": g.get("date"),
           "sportId": int(sport), "level": SPORTS.get(int(sport)), "season": int(season),
           "league": g.get("league"), "home": g.get("home"), "away": g.get("away"),
           "source": source, "play_cols": list(PLAY_COLS), "runner_cols": list(RUNNER_COLS),
           "credit_cols": list(CREDIT_COLS), "sub_cols": list(SUB_COLS),
           "taken_cols": list(TAKEN_COLS)}
    rec.update(reduce_plays(all_plays))
    return rec


def _plays_from_feed_cache(game_pk: int) -> list[dict] | None:
    path = FEED_CACHE_DIR / f"{int(game_pk)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    st = (data.get("gameData") or {}).get("status") or {}
    if st.get("abstractGameState") != "Final":
        return None
    plays = ((data.get("liveData") or {}).get("plays") or {}).get("allPlays")
    return plays if plays else None


def fetch_game(sport: int, season: int, g: dict) -> str:
    path = game_path(sport, season, g["gamePk"])
    if path.exists():
        return "cached"
    plays = _plays_from_feed_cache(int(g["gamePk"]))
    source = "feed_cache"
    if plays is None:
        data = _get_json(f"{API}/game/{int(g['gamePk'])}/playByPlay", {"fields": PBP_FIELDS})
        plays = data.get("allPlays") or []
        source = "playByPlay"
    _atomic_write_gz(path, game_record(g, sport, season, plays, source))
    return source


def fetch_cell(sport: int, season: int, *, deadline: float | None = None, log=print) -> dict:
    games = schedule(sport, season)
    todo = [g for g in games if not game_path(sport, season, g["gamePk"]).exists()]
    st = {"sport": sport, "season": season, "scheduled": len(games), "todo": len(todo),
          "playByPlay": 0, "feed_cache": 0, "failed": 0, "stopped": None}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        it = iter(todo)
        futs = {}

        def _submit() -> bool:
            g = next(it, None)
            if g is None:
                return False
            futs[ex.submit(fetch_game, sport, season, g)] = g
            return True

        for _ in range(MAX_WORKERS * 2):
            if not _submit():
                break
        while futs:
            done = next(as_completed(list(futs)))
            g = futs.pop(done)
            try:
                src = done.result()
                if src in st:
                    st[src] += 1
                n = st["playByPlay"] + st["feed_cache"]
                if n and n % 500 == 0:
                    log(f"  {SPORTS[sport]} {season}: {n}/{len(todo)} "
                        f"{n / max(time.time() - t0, 1e-6):.1f} games/s")
            except FetchWindowClosed as e:
                st["stopped"] = str(e)
            except Exception as e:  # noqa: BLE001 - a failed game is retried on the next run
                st["failed"] += 1
                if st["failed"] <= 5:
                    log(f"  fail {sport}/{season}/{g['gamePk']}: {type(e).__name__}: {e}")
            if st["stopped"] or (deadline and time.time() > deadline):
                st["stopped"] = st["stopped"] or "deadline"
                continue
            _submit()
    st["seconds"] = round(time.time() - t0, 1)
    return st


def cmd_fetch(a) -> int:
    deadline = time.time() + 60 * a.max_minutes if a.max_minutes else None
    cells = [(s, y) for s in LEVEL_ORDER for y in sorted(SEASONS, reverse=True)
             if (a.sport is None or s == a.sport) and (a.season is None or y == a.season)]
    for s, y in cells:
        st = fetch_cell(s, y, deadline=deadline)
        print(json.dumps(st), flush=True)
        if st["stopped"]:
            print(f"STOPPED: {st['stopped']}", flush=True)
            return 2
    return 0


# --- part 3: parse (pass 1) ---------------------------------------------------
POS_RATED = ("2", "3", "4", "5", "6", "7", "8", "9")
POS_NAME = {"2": "C", "3": "1B", "4": "2B", "5": "3B", "6": "SS", "7": "LF", "8": "CF", "9": "RF"}
LEVEL_RANK = {16: 0, 14: 1, 13: 2, 12: 3, 11: 4}          # ROK < A < A+ < AA < AAA
TRAJ = {"ground_ball": 1, "line_drive": 2, "fly_ball": 3, "popup": 4}
HARD = {"soft": 1, "medium": 2, "hard": 3}
OUT_EVENTS = frozenset({"field_out", "force_out", "grounded_into_double_play", "double_play",
                        "triple_play", "fielders_choice_out", "sac_fly", "sac_fly_double_play"})
RV = {"out": -0.27, "single": 0.47, "double": 0.77, "triple": 1.04, "field_error": 0.47,
      "fielders_choice": 0.47}
NONOUT_EVENTS = frozenset({"single", "double", "triple", "field_error", "fielders_choice"})
IN_PLAY_CODES = frozenset({"X", "D", "E"})
HOME_X, HOME_Y, FT_PER_UNIT = 125.42, 198.27, 2.5
ANGLE_CLAMP, ANGLE_BIN, DIST_BIN, DIST_BINS = 50.0, 5.0, 30.0, 17
DP_RUNS, KILL_RV, XB_RV, FRAME_RUNS, CS_RUNS = 0.40, -0.65, 0.25, 0.13, 0.65
STEAL_EVENTS = {"stolen_base_2b": (0, 2), "stolen_base_3b": (0, 3),
                "caught_stealing_2b": (1, 2), "caught_stealing_3b": (1, 3)}
X_LO, X_STEP, X_BINS = -2.0, 2.0 / 12.0, 24
Z_LO, Z_STEP, Z_BINS = -1.0, 0.1, 30
SPARSE_N = 30
SPARSE_FRAME_N = 20
INN_FLOOR = 200.0
LINK_INN = 100.0
MIN_LINK = 15
F_CLAMP = (0.25, 2.0)
K_CAP = 5000.0
MLB_INN_FLOOR = 300.0
DEBUT_YEARS = (2022, 2023, 2024)
B = 2000
SEED = 20261016
SEED_SHUFFLE = 20261017
SEED_PERMUTE = 20261018
SEED_PLANT_A = 20261019
SEED_PLANT_B = 20261020
PLANT_SD = 0.02
PLANT_B_RHO = 0.25
ALPHA = 0.05


class _Cols:
    """Append-only columnar table on array.array columns (keeps millions of rows compact)."""

    def __init__(self, spec):
        from array import array
        self.names = [n for n, _ in spec]
        self.cols = [array(t) for _, t in spec]

    def append(self, row) -> None:
        for c, v in zip(self.cols, row):
            c.append(v)

    def __len__(self) -> int:
        return len(self.cols[0])

    def frame(self):
        import numpy as np
        import pandas as pd
        return pd.DataFrame({n: np.frombuffer(c, dtype=c.typecode) if len(c) else
                             np.array([], dtype=c.typecode) for n, c in zip(self.names, self.cols)})


_I8, _I16, _I32, _F32 = "b", "h", "i", "f"


class Tables:
    """Pass-1 tables, columnar."""

    def __init__(self):
        self.games = []
        base = [("sport", _I8), ("season", _I16), ("gidx", _I32)]
        self.bip = _Cols(base + [("team", _I32), ("traj", _I8), ("hard", _I8), ("abin", _I8),
                                 ("dbin", _I8), ("located", _I8), ("out", _I8), ("init", _I8),
                                 ("rv", _F32)] + [(f"h{k}", _I32) for k in POS_RATED])
        self.dp = _Cols(base + [("pos", _I8), ("pid", _I32), ("turned", _I8)])
        self.arm = _Cols(base + [("pos", _I8), ("pid", _I32), ("ev", _I8), ("start", _I8),
                                 ("oc", _I8)])
        self.taken = _Cols(base + [("pid", _I32), ("xb", _I8), ("zb", _I8), ("cg", _I8),
                                   ("strike", _I8)])
        self.steal = _Cols(base + [("pid", _I32), ("cs", _I8), ("base", _I8)])
        self.inn = _Cols(base + [("pid", _I32), ("pos", _I8), ("outs", _I16)])
        self.census = defaultdict(lambda: defaultdict(int))


def _timelines(plays_top: dict, credits, subs) -> dict:
    tl = defaultdict(list)
    for ab, pidx, _rev, pid, pos, cr in credits:
        if pos in POS_RATED or pos == "1":
            if cr == "c_catcher_interf" or pidx is None or ab not in plays_top:
                continue
            tl[(plays_top[ab], pos)].append(((ab, pidx), pid))
    for ab, eidx, pid, pos, _ev in subs:
        if (pos in POS_RATED or pos == "1") and ab in plays_top and eidx is not None:
            tl[(plays_top[ab], pos)].append(((ab, eidx), pid))
    out = {}
    for k, v in tl.items():
        v.sort(key=lambda t: t[0])
        out[k] = ([t[0] for t in v], [t[1] for t in v])
    return out


def _holder(tl: dict, top: int, pos: str, key) -> int:
    ent = tl.get((top, pos))
    if not ent:
        return 0
    import bisect
    keys, pids = ent
    i = bisect.bisect_right(keys, key)
    return int(pids[i - 1] if i > 0 else pids[0])


def angle_dist(x, y):
    dx, dy = x - HOME_X, HOME_Y - y
    a = math.degrees(math.atan2(dx, dy))
    a = max(-ANGLE_CLAMP, min(ANGLE_CLAMP, a))
    return a, FT_PER_UNIT * math.hypot(dx, dy)


def angle_bin(a: float) -> int:
    return min(int((a + ANGLE_CLAMP) // ANGLE_BIN), int(2 * ANGLE_CLAMP / ANGLE_BIN) - 1)


def parse_game(rec: dict, gidx: int, T: Tables) -> None:
    sport, season = int(rec["sportId"]), int(rec["season"])
    cen = T.census[(sport, season)]
    plays = rec.get("plays") or []
    cen["games_reduced"] += 1 if plays else 0
    if not plays:
        return
    T.games.append((gidx, int(rec["gamePk"]), sport, season, rec.get("date"),
                    rec.get("home"), rec.get("away")))
    top_of = {p[0]: int(p[2]) for p in plays}
    side_of = {p[0]: p[5] for p in plays}
    tl = _timelines(top_of, rec.get("credits") or [], rec.get("subs") or [])
    by_ab_r = defaultdict(list)
    for r in rec.get("runners") or []:
        by_ab_r[r[0]].append(r)
    by_ab_c = defaultdict(list)
    for c in rec.get("credits") or []:
        by_ab_c[c[0]].append(c)
    team = {1: rec.get("home"), 0: rec.get("away")}
    inn_acc = defaultdict(int)
    prev_outs = {}
    for p in plays:
        ab, inning, top, event, outs_after, bat_side, last_code, traj, hard, loc, x, y, last_idx = p
        cen["plays"] += 1
        half = (inning, top)
        o_before = prev_outs.get(half, 0)
        o_after = outs_after if isinstance(outs_after, int) else o_before
        n_outs = max(0, o_after - o_before)
        prev_outs[half] = o_after
        key = (ab, last_idx if last_idx is not None else 10 ** 6)
        holders = {k: _holder(tl, top, k, key) for k in POS_RATED}
        for k, pid in holders.items():
            if pid and n_outs:
                inn_acc[(pid, k)] += n_outs
        # steals (gate part 3, catcher throwing)
        for r in by_ab_r.get(ab, ()):
            st = STEAL_EVENTS.get(r[7])
            if st is not None:
                c_pid = _holder(tl, top, "2", (ab, r[1] if r[1] is not None else 0))
                if c_pid:
                    T.steal.append((sport, season, gidx, c_pid, st[0], st[1]))
        if last_code not in IN_PLAY_CODES:
            continue
        cen["bip_all"] += 1
        if event not in OUT_EVENTS and event not in NONOUT_EVENTS:
            continue
        if traj not in TRAJ:
            continue
        cen["bip"] += 1
        is_out = event in OUT_EVENTS
        bip_cr = [c for c in by_ab_c.get(ab, ()) if c[1] == last_idx and c[5] != "c_catcher_interf"]
        init = bip_cr[0][4] if bip_cr else None
        if is_out and init is None:
            cen["bip_out_no_credit"] += 1
        if bip_cr:
            cen["bip_credited"] += 1
        located = x is not None and y is not None
        cen["bip_located"] += 1 if located else 0
        if located:
            a, d = angle_dist(x, y)
            abin = angle_bin(a)
            dbin = -1 if traj == "ground_ball" else min(int(d // DIST_BIN), DIST_BINS - 1)
        else:
            abin, dbin = -1, -1
        rv = RV["out"] if is_out else RV[event]
        init_code = int(init) if (init and init.isdigit()) else 0
        T.bip.append((sport, season, gidx, int(team[top] or 0), TRAJ[traj], HARD.get(hard, 0),
                      abin, dbin,
                      1 if located else 0, 1 if is_out else 0, init_code, rv,
                      *[holders[k] for k in POS_RATED]))
        bip_runners = [r for r in by_ab_r.get(ab, ()) if r[1] == last_idx]
        n_out_bip = sum(r[6] for r in bip_runners)
        # double plays (gate part 3)
        if (is_out and traj == "ground_ball" and init in ("3", "4", "5", "6")
                and any(r[4] == "1B" for r in bip_runners) and (o_after - n_out_bip) < 2):
            T.dp.append((sport, season, gidx, init_code, int(bip_cr[0][3]),
                         1 if n_out_bip >= 2 else 0))
        # outfield arm (gate part 3)
        if event in ("single", "double"):
            fb = [c for c in bip_cr if c[5] == "f_fielded_ball" and c[4] in ("7", "8", "9")]
            if fb:
                of_pos, of_pid = fb[0][4], int(fb[0][3])
                of_assist = any((c[5] == "f_assist_of") or (c[5] == "f_assist" and c[4] in ("7", "8", "9"))
                                for c in bip_cr)
                per = defaultdict(list)
                for r in bip_runners:
                    if r[2] is not None:
                        per[r[2]].append(r)
                for rows in per.values():
                    starts = [r[4] for r in rows if r[4]]
                    if not starts or starts[0] not in ("1B", "2B"):
                        continue
                    start = starts[0]
                    end = rows[-1][5]
                    out = any(r[6] for r in rows)
                    if out and of_assist:
                        oc = 2
                    elif ((event == "single" and start == "1B" and end in ("3B", "score"))
                          or (event == "single" and start == "2B" and end == "score")
                          or (event == "double" and start == "1B" and end == "score")):
                        oc = 1
                    else:
                        oc = 0
                    T.arm.append((sport, season, gidx, int(of_pos), of_pid,
                                  1 if event == "single" else 2, 1 if start == "1B" else 2, oc))
    # framing (gate part 3): the catcher at the start of the plate appearance
    for t in rec.get("taken") or []:
        ab, code, b, s, px, pz, ztop, zbot = t
        cen["taken"] += 1
        if px is None or pz is None or ztop is None or zbot is None or ztop <= zbot or ab not in top_of:
            continue
        cen["taken_located"] += 1
        top = top_of[ab]
        c_pid = _holder(tl, top, "2", (ab, -1))
        if not c_pid:
            continue
        xs = px if side_of.get(ab) != "L" else -px
        z = (pz - zbot) / (ztop - zbot)
        xb = min(max(int((xs - X_LO) // X_STEP), 0), X_BINS - 1)
        zb = min(max(int((z - Z_LO) // Z_STEP), 0), Z_BINS - 1)
        cg = 0 if s > b else (1 if s == b else 2)
        T.taken.append((sport, season, gidx, c_pid, xb, zb, cg, 1 if code == "C" else 0))
    for (pid, k), outs in inn_acc.items():
        T.inn.append((sport, season, gidx, int(pid), int(k), min(outs, 32000)))


def iter_game_files(base: Path | None = None, sports=LEVEL_ORDER, seasons=SEASONS):
    base = base or PBP_DIR
    for s in sports:
        for y in seasons:
            d = base / str(s) / str(y)
            if d.exists():
                for p in sorted(d.glob("*.json.gz")):
                    yield s, y, p


def pass1(base: Path | None = None, sports=LEVEL_ORDER, seasons=SEASONS,
          schedule_fn=schedule, log=print) -> Tables:
    T = Tables()
    for s in sports:
        for y in seasons:
            T.census[(s, y)]["scheduled"] = len(schedule_fn(s, y))
    gidx = 0
    t0 = time.time()
    for s, y, p in iter_game_files(base, sports, seasons):
        try:
            rec = read_gz(p)
        except (OSError, ValueError, EOFError):
            T.census[(s, y)]["unreadable"] += 1
            continue
        T.census[(s, y)]["files"] += 1
        parse_game(rec, gidx, T)
        gidx += 1
        if gidx % 5000 == 0:
            log(f"  pass1 {gidx} games {time.time() - t0:.0f}s")
    return T


def census_rows(T: Tables) -> list[dict]:
    rows = []
    for (s, y), c in sorted(T.census.items()):
        sched = c.get("scheduled", 0)
        red = c.get("games_reduced", 0)
        bip = c.get("bip", 0)
        rows.append({
            "sportId": s, "level": SPORTS[s], "season": y, "scheduled_final": sched,
            "files": c.get("files", 0), "games_reduced": red,
            "reduced_share": round(red / sched, 4) if sched else None,
            "cell_in": bool(sched and red / sched >= CELL_IN_SHARE),
            "plays": c.get("plays", 0), "balls_in_play_all": c.get("bip_all", 0),
            "balls_in_play_rated": bip,
            "located_share": round(c.get("bip_located", 0) / bip, 4) if bip else None,
            "credited_share": round(c.get("bip_credited", 0) / bip, 4) if bip else None,
            "outs_without_credit": c.get("bip_out_no_credit", 0),
            "taken_pitches": c.get("taken", 0),
            "taken_located_share": (round(c.get("taken_located", 0) / c["taken"], 4)
                                    if c.get("taken") else None),
        })
    return rows


# --- part 3: the measure (vectorized) ------------------------------------------
BIP_COLS = ["sport", "season", "gidx", "team", "traj", "hard", "abin", "dbin", "located", "out",
            "init", "rv"] + [f"h{k}" for k in POS_RATED]


def to_frames(T: Tables) -> dict:
    import pandas as pd
    return {
        "games": pd.DataFrame(T.games, columns=["gidx", "gamePk", "sport", "season", "date",
                                                "home", "away"]),
        "bip": T.bip.frame(), "dp": T.dp.frame(), "arm": T.arm.frame(),
        "taken": T.taken.frame(), "steal": T.steal.frame(), "inn": T.inn.frame(),
    }


def fit_cells(bip):
    """Per level: p_c, w_ck (k = 1..9) and delta_c for each located ball in play, with the
    sparse-cell fallback (part 10 note N1): (traj, hard, abin, dbin) -> (traj, abin, dbin)
    -> (traj, abin) -> (traj), the first with SPARSE_N or more balls in play."""
    import numpy as np
    import pandas as pd
    loc = bip[bip.located == 1]
    n = len(bip)
    p = np.full(n, np.nan)
    w = np.zeros((n, 10))
    delta = np.full(n, np.nan)
    keysets = (["traj", "hard", "abin", "dbin"], ["traj", "abin", "dbin"], ["traj", "abin"],
               ["traj"])
    pos = bip.index.to_numpy()
    idx_of = pd.Series(np.arange(n), index=pos)
    for sport, g in loc.groupby("sport"):
        level_delta = float(g.loc[g.out == 0, "rv"].mean() - RV["out"]) if (g.out == 0).any() else 0.8
        todo = g.index
        for ks in keysets:
            if len(todo) == 0:
                break
            cols = ks
            stats = g.groupby(cols).agg(n=("out", "size"), outs=("out", "sum"))
            nonout = g[g.out == 0].groupby(cols).rv.mean().rename("rv_non")
            stats = stats.join(nonout)
            shares = (g[g.out == 1].groupby(cols + ["init"]).size().unstack("init", fill_value=0))
            sub = g.loc[todo]
            keyed = sub[cols].merge(stats, left_on=cols, right_index=True, how="left")
            keyed.index = sub.index
            last = ks == keysets[-1]
            ok = keyed.n >= (1 if last else SPARSE_N)
            take = keyed[ok]
            if len(take):
                ii = idx_of.loc[take.index].to_numpy()
                p[ii] = (take.outs / take.n).to_numpy()
                d = (take.rv_non - RV["out"]).to_numpy()
                delta[ii] = np.where(np.isfinite(d), d, level_delta)
                sh = sub.loc[take.index, cols].merge(shares, left_on=cols, right_index=True,
                                                     how="left")
                tot = None
                for k in range(1, 10):
                    col = sh[k].to_numpy(float) if k in sh.columns else np.zeros(len(sh))
                    col = np.nan_to_num(col)
                    w[ii, k] = col
                    tot = col if tot is None else tot + col
                tot = np.where(tot > 0, tot, 1.0)
                w[ii, 1:] = w[ii, 1:] / tot[:, None]
            todo = keyed.index[~ok]
    return p, w, delta


def range_runs(bip, p, w, delta):
    """Per ball in play, runs and chances for positions 2..9 (located and range-factor)."""
    import numpy as np
    n = len(bip)
    runs = np.zeros((n, 10))
    chances = np.zeros((n, 10))
    init = bip.init.to_numpy()
    outs = bip.out.to_numpy()
    loc = bip.located.to_numpy() == 1
    for k in range(1, 10):
        made = ((init == k) & (outs == 1)).astype(float)
        runs[loc, k] = (made[loc] - p[loc] * w[loc, k]) * delta[loc]
        chances[loc, k] = p[loc] * w[loc, k]
    # range-factor construction for unlocated balls in play
    unl = ~loc
    if unl.any():
        sports = bip.sport.to_numpy()
        for s in np.unique(sports[unl]):
            m = unl & (sports == s)
            ml = loc & (sports == s)
            d_l = float(np.nanmean(delta[ml])) if ml.any() else 0.8
            for k in range(1, 10):
                made = ((init[m] == k) & (outs[m] == 1)).astype(float)
                q = float(made.mean())
                runs[m, k] = (made - q) * d_l
                chances[m, k] = q
    return runs, chances


def game_rows(F: dict, bip_runs=None):
    """(sport, season, gidx, pid, pos) rows: outs and component runs before level norms."""
    import numpy as np
    import pandas as pd
    bip = F["bip"]
    parts = []
    if len(bip):
        p, w, delta = fit_cells(bip)
        runs, chances = bip_runs if bip_runs is not None else range_runs(bip, p, w, delta)
        for k in POS_RATED:
            kk = int(k)
            part = pd.DataFrame({
                "sport": bip.sport.to_numpy(), "season": bip.season.to_numpy(),
                "gidx": bip.gidx.to_numpy(), "pid": bip[f"h{k}"].to_numpy(),
                "range_runs": runs[:, kk], "range_chances": chances[:, kk]})
            part = part.groupby(["sport", "season", "gidx", "pid"], as_index=False).sum()
            part["pos"] = kk
            parts.append(part)
    dp = F["dp"]
    if len(dp):
        r = dp.groupby(["sport", "pos"]).turned.transform("mean")
        parts.append(pd.DataFrame({"sport": dp.sport, "season": dp.season, "gidx": dp.gidx,
                                   "pid": dp.pid, "pos": dp.pos,
                                   "dp_runs": (dp.turned - r) * DP_RUNS, "dp_opps": 1.0}))
    arm = F["arm"]
    if len(arm):
        g = arm.groupby(["sport", "pos", "ev", "start"]).oc
        pk = g.transform(lambda s: (s == 2).mean())
        px = g.transform(lambda s: (s == 1).mean())
        ev_ = KILL_RV * pk + XB_RV * px
        obs = np.where(arm.oc == 2, KILL_RV, np.where(arm.oc == 1, XB_RV, 0.0))
        parts.append(pd.DataFrame({"sport": arm.sport, "season": arm.season, "gidx": arm.gidx,
                                   "pid": arm.pid, "pos": arm.pos,
                                   "arm_runs": ev_ - obs, "arm_opps": 1.0}))
    tk = F["taken"]
    if len(tk):
        pf = frame_prob(tk)
        part = pd.DataFrame({"sport": tk.sport, "season": tk.season, "gidx": tk.gidx,
                             "pid": tk.pid, "frame_runs": (tk.strike - pf) * FRAME_RUNS,
                             "frame_n": 1.0})
        part = part.groupby(["sport", "season", "gidx", "pid"], as_index=False).sum()
        part["pos"] = 2
        parts.append(part)
    stl = F["steal"]
    if len(stl):
        sL = stl.groupby("sport").cs.transform("mean")
        parts.append(pd.DataFrame({"sport": stl.sport, "season": stl.season, "gidx": stl.gidx,
                                   "pid": stl.pid, "pos": 2,
                                   "throw_runs": (stl.cs - sL) * CS_RUNS, "throw_n": 1.0}))
    inn = F["inn"]
    parts.append(pd.DataFrame({"sport": inn.sport, "season": inn.season, "gidx": inn.gidx,
                               "pid": inn.pid, "pos": inn.pos, "outs": inn.outs}))
    allp = pd.concat(parts, ignore_index=True)
    allp = allp[allp.pid > 0]
    comp = ["outs", "range_runs", "range_chances", "dp_runs", "dp_opps", "arm_runs", "arm_opps",
            "frame_runs", "frame_n", "throw_runs", "throw_n"]
    for c in comp:
        if c not in allp.columns:
            allp[c] = 0.0
    gr = allp.groupby(["sport", "season", "gidx", "pid", "pos"], as_index=False)[comp].sum()
    gr["inn"] = gr.outs / 3.0
    return gr


def frame_prob(tk):
    """Called-strike probability per taken pitch with the sparse fallback (part 10 note N1):
    (level, cg, xb, zb) -> (level, cg, xb//2, zb//2) -> (level, xb//2, zb//2) -> level."""
    import numpy as np
    tk = tk.assign(xb2=tk.xb // 2, zb2=tk.zb // 2)
    out = np.full(len(tk), np.nan)
    for keys in (["sport", "cg", "xb", "zb"], ["sport", "cg", "xb2", "zb2"],
                 ["sport", "xb2", "zb2"], ["sport"]):
        g = tk.groupby(keys).strike
        n = g.transform("size").to_numpy()
        m = g.transform("mean").to_numpy()
        fill = np.isnan(out) & ((n >= SPARSE_FRAME_N) | (keys == ["sport"]))
        out[fill] = m[fill]
    return out


COMPONENTS = ("range_runs", "dp_runs", "arm_runs", "frame_runs", "throw_runs")


def level_norms(gr):
    """Centre every component to an innings-weighted mean of zero within (level, season,
    position); total = the sum of the centred components."""
    import numpy as np
    gr = gr.copy()
    keys = ["sport", "season", "pos"]
    tot_inn = gr.groupby(keys).inn.transform("sum")
    for c in COMPONENTS:
        rate = gr.groupby(keys)[c].transform("sum") / tot_inn.replace(0, np.nan)
        gr[c] = gr[c] - gr.inn * rate.fillna(0.0)
    gr["runs"] = gr[list(COMPONENTS)].sum(axis=1)
    return gr


def season_table(gr):
    comp = ["inn", "runs", *COMPONENTS, "range_chances", "dp_opps", "arm_opps", "frame_n",
            "throw_n"]
    st = gr.groupby(["pid", "season", "sport", "pos"], as_index=False)[comp].sum()
    st["games"] = gr.groupby(["pid", "season", "sport", "pos"]).gidx.nunique().to_numpy()
    return st


def shrink_k(gr, games) -> dict:
    """Per position: split-half reliability on player-season-level rows with INN_FLOOR+
    innings, halves by alternate games in date order, Spearman-Brown, k = n_bar (1 - r) / r
    (part 10 note N1: Pearson correlation of the half rates)."""
    import numpy as np
    order = games.set_index("gidx")[["date", "gamePk"]]
    g = gr.merge(order, left_on="gidx", right_index=True, how="left")
    g = g.sort_values(["pid", "season", "sport", "pos", "date", "gamePk"])
    g["half"] = g.groupby(["pid", "season", "sport", "pos"]).cumcount() % 2
    h = g.groupby(["pid", "season", "sport", "pos", "half"])[["runs", "inn"]].sum().unstack("half")
    h = h.dropna()
    out = {}
    for pos in POS_RATED:
        kk = int(pos)
        hh = h[h.index.get_level_values("pos") == kk]
        tot = hh["inn"].sum(axis=1)
        hh = hh[(tot >= INN_FLOOR) & (hh["inn"].min(axis=1) > 0)]
        if len(hh) < 10:
            out[pos] = {"k": K_CAP, "r_half": None, "r": None, "n_rows": int(len(hh)),
                        "n_bar": None}
            continue
        a = (hh["runs"][0] / hh["inn"][0]).to_numpy()
        b = (hh["runs"][1] / hh["inn"][1]).to_numpy()
        rh = float(np.corrcoef(a, b)[0, 1])
        r = 2 * rh / (1 + rh) if rh > -1 else -1.0
        nbar = float(hh["inn"].sum(axis=1).mean())
        k = K_CAP if r <= 0 else min(nbar * (1 - r) / r, K_CAP)
        out[pos] = {"k": round(k, 3), "r_half": round(rh, 4), "r": round(r, 4),
                    "n_rows": int(len(hh)), "n_bar": round(nbar, 2)}
    return out


def level_factors(st, kpos: dict) -> dict:
    """Chained same-player translation (gate part 3): f(lo -> hi) on same-season, same-position
    rows with LINK_INN+ innings at both levels; F_L chained to AAA."""
    import numpy as np
    chain = [16, 14, 13, 12, 11]
    f = {}
    for lo, hi in zip(chain, chain[1:]):
        a = st[(st.sport == lo) & (st.inn >= LINK_INN)]
        b = st[(st.sport == hi) & (st.inn >= LINK_INN)]
        m = a.merge(b, on=["pid", "season", "pos"], suffixes=("_lo", "_hi"))
        if len(m) < MIN_LINK:
            f[(lo, hi)] = {"f": 1.0, "links": int(len(m)), "identified": False}
            continue
        k = m.pos.map(lambda p: kpos[str(p)]["k"]).to_numpy(float)
        s_lo = (m.runs_lo / (m.inn_lo + k)).to_numpy()
        r_hi = (m.runs_hi / m.inn_hi).to_numpy()
        w = np.minimum(m.inn_lo, m.inn_hi).to_numpy()
        den = float((w * s_lo ** 2).sum())
        val = float((w * r_hi * s_lo).sum() / den) if den > 0 else 1.0
        val = min(max(val, F_CLAMP[0]), F_CLAMP[1])
        f[(lo, hi)] = {"f": round(val, 4), "links": int(len(m)), "identified": True}
    F = {11: 1.0}
    for lo, hi in reversed(list(zip(chain, chain[1:]))):
        F[lo] = F[hi] * f[(lo, hi)]["f"]
    return {"pairs": {f"{SPORTS[lo]}->{SPORTS[hi]}": v for (lo, hi), v in f.items()},
            "F": {SPORTS[s]: round(v, 4) for s, v in F.items()}, "_F": F}


def mfr(st, kpos: dict, F: dict, keys=("pid", "pos")):
    """MFR per key group: sum F_L runs_L / (sum innings + k_pos), per 1,000 innings."""
    import numpy as np
    s = st.copy()
    s["fr"] = s.runs * s.sport.map(F).astype(float)
    g = s.groupby(list(keys), as_index=False).agg(fr=("fr", "sum"), inn=("inn", "sum"))
    k = g.pos.map(lambda p: kpos[str(p)]["k"]).astype(float)
    g["mfr"] = 1000.0 * g.fr / (g.inn + k)
    g["reliability"] = g.inn / (g.inn + k)
    g["mfr"] = g.mfr.where(np.isfinite(g.mfr))
    return g


def build(base: Path | None = None, *, write: bool = True, out_dir: Path | None = None,
          sports=LEVEL_ORDER, seasons=SEASONS, schedule_fn=schedule, log=print) -> dict:
    T = pass1(base, sports, seasons, schedule_fn, log)
    cen = census_rows(T)
    F = to_frames(T)
    in_cells = {(r["sportId"], r["season"]) for r in cen if r["cell_in"]}
    for name in ("bip", "dp", "arm", "taken", "steal", "inn"):
        df = F[name]
        if len(df):
            keep = [(s, y) in in_cells for s, y in zip(df.sport, df.season)]
            F[name] = df[keep].reset_index(drop=True)
    gr = level_norms(game_rows(F))
    kpos = shrink_k(gr, F["games"])
    st = season_table(gr)
    lf = level_factors(st, kpos)
    res = {"census": cen, "in_cells": sorted(in_cells), "F": F, "gr": gr, "st": st, "k": kpos,
           "levels": lf}
    if write:
        d = out_dir or TABLES
        d.mkdir(parents=True, exist_ok=True)
        st.to_parquet(d / "season_table.parquet", index=False)
        gr.to_parquet(d / "game_rows.parquet", index=False)
        for name in ("games", "bip"):
            F[name].to_parquet(d / f"{name}.parquet", index=False)
        meta = {"k": kpos, "levels": {k: v for k, v in lf.items() if k != "_F"},
                "in_cells": sorted(in_cells), "built_at": _now()}
        (d / "build_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return res


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_build(a) -> int:
    res = build()
    cen = {"generated_at": _now(), "gate": GATE_DOC, "part": "2 (coverage census)",
           "cell_in_rule": f"reduced games >= {CELL_IN_SHARE:.0%} of scheduled final games",
           "rows": res["census"],
           "note": "Coverage only; no estimand of the gate is computed by the census."}
    CENSUS_OUT.write_text(json.dumps(cen, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"k": res["k"], "levels": {k: v for k, v in res["levels"].items()
                                                if k != "_F"}}, indent=1))
    return 0


# --- parts 4 and 5: statistics ---------------------------------------------------

def _rank(a):
    import pandas as pd
    return pd.Series(a).rank(method="average").to_numpy()


def spearman(x, y):
    import numpy as np
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return None
    rx, ry = _rank(x[ok]), _rank(y[ok])
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def partial_rank(x, y, g):
    """Rank partial correlation of x and y given g (part 4 (c))."""
    import numpy as np
    x, y, g = (np.asarray(v, float) for v in (x, y, g))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(g)
    if ok.sum() < 5:
        return None
    rx, ry, rg = _rank(x[ok]), _rank(y[ok]), _rank(g[ok])
    if min(rx.std(), ry.std(), rg.std()) == 0:
        return None
    A = np.column_stack([np.ones_like(rg), rg])
    ex = rx - A @ np.linalg.lstsq(A, rx, rcond=None)[0]
    ey = ry - A @ np.linalg.lstsq(A, ry, rcond=None)[0]
    if ex.std() == 0 or ey.std() == 0:
        return None
    return float(np.corrcoef(ex, ey)[0, 1])


def _r(v, k=4):
    import numpy as np
    return None if v is None or not np.isfinite(v) else round(float(v), k)


def boot(stat_fn, groups, b: int, seed: int):
    """Cluster bootstrap (resample `groups`, every row of a drawn group together)."""
    import numpy as np
    groups = np.asarray(groups)
    out = np.full(b, np.nan)
    if not len(groups):
        return out
    uniq, inv = np.unique(groups, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    bounds = np.searchsorted(inv[order], np.arange(len(uniq) + 1))
    members = [order[bounds[i]:bounds[i + 1]] for i in range(len(uniq))]
    rng = np.random.default_rng(seed)
    n = len(members)
    for i in range(b):
        pick = rng.integers(0, n, n)
        idx = np.concatenate([members[k] for k in pick])
        v = stat_fn(idx)
        out[i] = np.nan if v is None else v
    return out


def summarize(point, draws) -> dict:
    import numpy as np
    d = draws[np.isfinite(draws)]
    if point is None or len(d) == 0:
        return {"point": _r(point), "lb95": None, "ub95": None, "p_one_sided": None,
                "draws": int(len(d))}
    return {"point": _r(point), "lb95": _r(float(np.percentile(d, 2.5))),
            "ub95": _r(float(np.percentile(d, 97.5))),
            "p_one_sided": _r(float(((d <= 0).sum() + 1) / (len(d) + 1)), 5), "draws": int(len(d))}


def holm(ps: dict, alpha: float = ALPHA) -> dict:
    items = sorted((v, k) for k, v in ps.items() if v is not None)
    m = len(items)
    out, stop = {}, False
    for i, (p, k) in enumerate(items):
        thr = alpha / (m - i)
        ok = (not stop) and p <= thr
        out[k] = {"p": p, "threshold": round(thr, 5), "rejects": bool(ok)}
        stop = stop or not ok
    for k, v in ps.items():
        if v is None:
            out[k] = {"p": None, "threshold": None, "rejects": False}
    return out


def _centre(df, col, by):
    return df[col] - df.groupby(by)[col].transform("mean")


def season_mfr(st, kpos, F):
    """(pid, season, pos) MiLB rows pooled across levels: MFR and innings."""
    return mfr(st, kpos, F, keys=("pid", "season", "pos"))


def persistence_pairs(sm):
    a = sm[sm.inn >= INN_FLOOR]
    b = a.assign(season=a.season - 1)
    m = a.merge(b, on=["pid", "season", "pos"], suffixes=("_y", "_y1"))
    m = m[m.season.between(2021, 2025)].copy()
    m["x"] = _centre(m, "mfr_y", ["pos", "season"])
    m["y"] = _centre(m, "mfr_y1", ["pos", "season"])
    return m


def read_a(st, kpos, F, b: int, seed: int) -> dict:
    import numpy as np
    m = persistence_pairs(season_mfr(st, kpos, F))
    x, y, g = m.x.to_numpy(float), m.y.to_numpy(float), m.pid.to_numpy()
    rho = spearman(x, y)
    draws = boot(lambda i: spearman(x[i], y[i]), g, b, seed)
    cells = {}
    for pos, mm in m.groupby("pos"):
        xx, yy, gg = mm.x.to_numpy(float), mm.y.to_numpy(float), mm.pid.to_numpy()
        cells[POS_NAME[str(pos)]] = {"pairs": int(len(mm)), **summarize(
            spearman(xx, yy), boot(lambda i: spearman(xx[i], yy[i]), gg, b, seed))}
    return {"pairs": int(len(m)), "players": int(len(np.unique(g))),
            **summarize(rho, draws), "per_position": cells}


def shuffle_stints(st, seed: int):
    """N-a: within each (level, season, position) permute the stints' player ids."""
    import numpy as np
    rng = np.random.default_rng(seed)
    s = st.sort_values(["sport", "season", "pos", "pid"]).reset_index(drop=True)
    pid = s.pid.to_numpy().copy()
    for _, idx in s.groupby(["sport", "season", "pos"]).indices.items():
        pid[idx] = pid[idx][rng.permutation(len(idx))]
    s["pid"] = pid
    return s.groupby(["pid", "season", "sport", "pos"], as_index=False)[["inn", "runs"]].sum()


def planted_a(res: dict, b: int, seed: int) -> dict:
    """P-a: located balls in play re-drawn with a planted per-player out probability s_p ~
    N(0, PLANT_SD) held across seasons; the range component recomputed with the fitted
    cells; its persistence must clear LB95 > 0."""
    import numpy as np
    import pandas as pd
    Fr = res["F"]
    bip = Fr["bip"][Fr["bip"].located == 1].reset_index(drop=True)
    if not len(bip):
        return {"verdict": "NOT COMPUTABLE"}
    p, w, delta = fit_cells(bip)
    rng = np.random.default_rng(seed)
    H = np.column_stack([np.zeros(len(bip), dtype=np.int64)]
                        + [bip[f"h{k}"].to_numpy().astype(np.int64) for k in POS_RATED])
    uniq = np.unique(H[:, 1:])
    sk = rng.normal(0.0, PLANT_SD, len(uniq))
    S = np.zeros(H.shape)
    pos_idx = np.searchsorted(uniq, H[:, 1:])
    S[:, 1:] = sk[pos_idx]
    S[:, 1:][H[:, 1:] == 0] = 0.0
    skill = dict(zip(uniq.tolist(), sk.tolist()))
    W = w[:, 1:10]
    Sfull = np.zeros((len(bip), 9))
    Sfull[:, 1:] = S[:, 1:]                    # pitcher (k = 1) carries no planted skill
    p2 = np.clip(p + (W * Sfull).sum(1), 0.001, 0.999)
    out = rng.random(len(bip)) < p2
    wt = np.clip(W * (p[:, None] + Sfull), 0.0, None)
    tot = wt.sum(1)
    wt = np.where(tot[:, None] > 0, wt / np.where(tot > 0, tot, 1.0)[:, None], 1.0 / 9)
    cum = wt.cumsum(1)
    u = rng.random(len(bip))[:, None]
    init = np.minimum(1 + (u > cum).sum(1), 9)
    syn = bip.copy()
    syn["out"] = out.astype(np.int8)
    syn["init"] = np.where(out, init, 0).astype(np.int8)
    runs, _ = range_runs(syn, p, w, delta)
    parts = []
    for k in POS_RATED:
        kk = int(k)
        part = pd.DataFrame({"sport": syn.sport, "season": syn.season, "gidx": syn.gidx,
                             "pid": syn[f"h{k}"], "range_runs": runs[:, kk]})
        part = part.groupby(["sport", "season", "gidx", "pid"], as_index=False).sum()
        part["pos"] = kk
        parts.append(part)
    gr = pd.concat(parts, ignore_index=True)
    inn = res["gr"][["sport", "season", "gidx", "pid", "pos", "inn"]]
    gr = inn.merge(gr, on=["sport", "season", "gidx", "pid", "pos"], how="left")
    gr["range_runs"] = gr.range_runs.fillna(0.0)
    gr = gr[gr.pid > 0]
    keys = ["sport", "season", "pos"]
    rate = gr.groupby(keys).range_runs.transform("sum") / gr.groupby(keys).inn.transform("sum")
    gr["runs"] = gr.range_runs - gr.inn * rate.fillna(0.0)
    st = gr.groupby(["pid", "season", "sport", "pos"], as_index=False)[["inn", "runs"]].sum()
    pa = read_a(st, res["k"], res["levels"]["_F"], b, seed)
    sm = mfr(st, res["k"], res["levels"]["_F"], keys=("pid", "pos"))
    sm = sm[sm.inn >= INN_FLOOR]
    rec = spearman(sm.mfr.to_numpy(float), sm.pid.map(skill).to_numpy(float))
    ok = pa["lb95"] is not None and pa["lb95"] > 0
    return {"planted_sd": PLANT_SD, "persistence": {k: pa[k] for k in
                                                    ("pairs", "point", "lb95", "ub95")},
            "spearman_with_planted": _r(rec), "verdict": "PASS" if ok else "FAIL"}


# --- MLB side ---------------------------------------------------------------------
FG_RAW = ROOT / ".cache" / "sdr" / "home" / "defense_plus" / "data" / "raw"
WAR_DAILY = ROOT / ".cache" / "war_daily" / "bat.parquet"
STATSAPI_FIELD = ROOT / ".cache" / "statsapi_field"
GRADE_ROWS = ROOT / "data" / "_labs" / "tool_tables_rederived" / "grade_rows_frozen.json"
FG_POS = {"C": 2, "1B": 3, "2B": 4, "3B": 5, "SS": 6, "LF": 7, "CF": 8, "RF": 9}
OAA_POS = (3, 4, 5, 6, 7, 8, 9)
LAST_MLB = 2026
UZR_LAST = 2024


def _sha(p: Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fg_ip(x) -> float:
    x = float(x)
    whole = int(x)
    return whole + round((x - whole) * 10) / 3.0


def load_mlb() -> dict:
    import pandas as pd
    fgs, meta = [], {"fg_files": {}}
    for s in range(2016, LAST_MLB + 1):
        p = FG_RAW / f"fg_field_full_{s}.csv"
        if not p.exists():
            continue
        meta["fg_files"][s] = _sha(p)
        f = pd.read_csv(p)
        f = f[f.Pos.isin(list(FG_POS))].copy()
        f["pid"] = pd.to_numeric(f.xMLBAMID, errors="coerce")
        f = f[f.pid.notna()].copy()
        f["pid"] = f.pid.astype(int)
        f["season"] = s
        f["pos"] = f.Pos.map(FG_POS)
        f["inn"] = f.Inn.map(fg_ip)
        for c in ("OAA", "UZR", "DRS", "FRP"):
            f[c] = pd.to_numeric(f[c], errors="coerce") if c in f.columns else float("nan")
        fgs.append(f[["pid", "season", "pos", "inn", "OAA", "UZR", "DRS", "FRP"]])
    fg = pd.concat(fgs, ignore_index=True)
    wd = pd.read_parquet(WAR_DAILY)
    wd["pid"] = pd.to_numeric(wd.mlb_ID, errors="coerce")
    wd["season"] = pd.to_numeric(wd.year_ID, errors="coerce")
    for c in ("runs_field", "Inn"):
        wd[c] = pd.to_numeric(wd[c], errors="coerce")
    wd = wd.dropna(subset=["pid", "season"])
    rf = wd.groupby(["pid", "season"], as_index=False).agg(
        runs_field=("runs_field", lambda x: x.sum(min_count=1)), inn=("Inn", "sum"))
    rf = rf.astype({"pid": int, "season": int})
    meta["war_daily"] = {"sha256": _sha(WAR_DAILY), "modified": datetime.fromtimestamp(
        WAR_DAILY.stat().st_mtime, timezone.utc).isoformat()}
    first = {}
    for s in range(2000, LAST_MLB + 1):
        p = STATSAPI_FIELD / f"fld_{s}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for blk in d.get("stats") or []:
            for sp in blk.get("splits") or []:
                pid = (sp.get("player") or {}).get("id")
                if pid is not None and int(pid) not in first:
                    first[int(pid)] = s
    meta["statsapi_field_seasons"] = [2000, LAST_MLB]
    return {"fg": fg, "rf": rf, "debut": first, "meta": meta}


def load_grades() -> dict:
    d = json.loads(GRADE_ROWS.read_text(encoding="utf-8"))
    out = {}
    for r in d.get("rows") or []:
        g = (r.get("tools_consensus") or {}).get("field")
        if g is not None and r.get("side") == "hit":
            out[int(r["mlbam"])] = float(g)
    return {"field": out, "meta": {"path": str(GRADE_ROWS.relative_to(ROOT)).replace("\\", "/"),
                                   "sha256": _sha(GRADE_ROWS), "n_rows": d.get("n_rows"),
                                   "field_rows_hit": len(out)}}


B_COLS = ["pid", "debut", "pos", "pred", "pred_inn", "pred_milb_primary", "T1", "T2", "FRP",
          "UZR", "DRS", "mlb_inn_t1", "mlb_inn_t2"]


def b_frame(st, kpos, F, mlb: dict):
    """(b) rows: one per player with debut D in DEBUT_YEARS (R-VM guarded)."""
    import numpy as np
    import pandas as pd
    from efv_vintage_frame import guard_vm_request
    guard_vm_request(DEBUT_YEARS, purpose="MILB_FIELDING_RUNS (b)")
    fg, rf, debut = mlb["fg"], mlb["rf"], mlb["debut"]
    rows = []
    milb_pids = set(st.pid.unique().tolist())
    fg_by = dict(tuple(fg.groupby("pid")))
    rf_by = dict(tuple(rf.groupby("pid")))
    st_by = dict(tuple(st.groupby("pid")))
    for pid, D in debut.items():
        if D not in DEBUT_YEARS or pid not in milb_pids or pid not in fg_by:
            continue
        f = fg_by[pid]
        f = f[f.season >= D]
        if f.empty:
            continue
        k = int(f.groupby("pos").inn.sum().idxmax())
        r = rf_by.get(pid)
        t1, t1_inn = np.nan, 0.0
        if r is not None:
            r = r[r.season >= D]
            t1_inn = float(r.inn.sum())
            if t1_inn >= MLB_INN_FLOOR and r.runs_field.notna().any():
                t1 = 1000.0 * float(r.runs_field.sum()) / t1_inn
        fo = f[f.pos.isin(OAA_POS) & f.OAA.notna()]
        t2_inn = float(fo.inn.sum())
        t2 = 1000.0 * float(fo.OAA.sum()) / t2_inn if t2_inn >= MLB_INN_FLOOR else np.nan
        fk = f[f.pos == k]

        def _at(col, last=LAST_MLB):
            ff = fk[(fk.season <= last) & fk[col].notna()]
            ii = float(ff.inn.sum())
            return 1000.0 * float(ff[col].sum()) / ii if ii >= MLB_INN_FLOOR else np.nan
        pre = st_by[pid]
        pre = pre[(pre.season < D) & (pre.season >= 2021)]
        pk = pre[pre.pos == k]
        pred, pred_inn = np.nan, float(pk.inn.sum())
        if pred_inn >= INN_FLOOR:
            pred = float(mfr(pk, kpos, F, keys=("pid", "pos")).mfr.iloc[0])
        alt = np.nan
        if len(pre):
            kp = int(pre.groupby("pos").inn.sum().idxmax())
            pa = pre[pre.pos == kp]
            if float(pa.inn.sum()) >= INN_FLOOR:
                alt = float(mfr(pa, kpos, F, keys=("pid", "pos")).mfr.iloc[0])
        rows.append({"pid": pid, "debut": D, "pos": k, "pred": pred, "pred_inn": pred_inn,
                     "pred_milb_primary": alt, "T1": t1, "T2": t2, "FRP": _at("FRP"),
                     "UZR": _at("UZR", UZR_LAST), "DRS": _at("DRS"), "mlb_inn_t1": t1_inn,
                     "mlb_inn_t2": t2_inn})
    return pd.DataFrame(rows, columns=B_COLS)


def _fin(s):
    import numpy as np
    return np.isfinite(s.to_numpy(dtype=float))


def _cell(df, xcol, ycol, b, seed, fn=spearman):
    import numpy as np
    d = df[_fin(df[xcol]) & _fin(df[ycol])].copy()
    if len(d) < 3:
        return {"n": int(len(d)), **summarize(None, np.array([]))}
    d["xc"] = _centre(d, xcol, "pos")
    d["yc"] = _centre(d, ycol, "pos")
    x, y = d.xc.to_numpy(float), d.yc.to_numpy(float)
    pt = fn(x, y)
    return {"n": int(len(d)), **summarize(pt, boot(lambda i: fn(x[i], y[i]), d.pid.to_numpy(),
                                                   b, seed))}


def _rule(cells: dict) -> dict:
    ps = {k: (v["p_one_sided"] if v.get("lb95") is not None else None) for k, v in cells.items()}
    h = holm(ps)
    clears = {k: bool(h[k]["rejects"] and cells[k]["lb95"] is not None and cells[k]["lb95"] > 0)
              for k in cells}
    return {"holm": h, "clears": clears, "any": any(clears.values())}


def _permute_within_pos(df, col, seed):
    import numpy as np
    rng = np.random.default_rng(seed)
    d = df.sort_values(["pos", "pid"]).reset_index(drop=True)
    v = d[col].to_numpy(float).copy()
    for _, idx in d.groupby("pos").indices.items():
        v[idx] = v[idx][rng.permutation(len(idx))]
    d[col] = v
    return d


def _verdict(rule, null_rule, planted_rule) -> str:
    if null_rule["any"]:
        return "VOID"
    if not planted_rule["any"]:
        return "UNDERPOWERED"
    return "PASS" if rule["any"] else "FAIL"


def read_b(bf, b: int, seed: int) -> dict:
    import numpy as np
    cells = {t: _cell(bf, "pred", t, b, seed) for t in ("T1", "T2")}
    rule = _rule(cells)
    nb = _permute_within_pos(bf, "pred", SEED_PERMUTE)
    null_cells = {t: _cell(nb, "pred", t, b, seed) for t in ("T1", "T2")}
    null_rule = _rule(null_cells)
    rng2 = np.random.default_rng(SEED_PLANT_B)
    pb = bf.copy()
    for t in ("T1", "T2"):
        ok = _fin(pb.pred) & _fin(pb[t])
        z = np.full(len(pb), np.nan)
        if ok.sum() >= 3:
            r = _rank(pb.pred.to_numpy(float)[ok])
            zr = (r - r.mean()) / (r.std() or 1.0)
            z[ok] = PLANT_B_RHO * zr + math.sqrt(1 - PLANT_B_RHO ** 2) * rng2.normal(
                0, 1, int(ok.sum()))
        pb[t] = z
    planted_cells = {t: _cell(pb, "pred", t, b, seed) for t in ("T1", "T2")}
    planted_rule = _rule(planted_cells)
    reported = {t: _cell(bf, "pred", t, b, seed) for t in ("FRP", "UZR", "DRS")}
    alt = {t: _cell(bf, "pred_milb_primary", t, b, seed) for t in ("T1", "T2")}
    per_pos = {}
    for pos, d in bf.groupby("pos"):
        per_pos[POS_NAME[str(pos)]] = {t: _cell(d, "pred", t, b, seed)
                                       for t in ("T1", "T2", "FRP")}
    has = _fin(bf.pred)
    return {"rows": int(len(bf)), "rows_with_predictor": int(has.sum()),
            "by_debut": {int(k): int(v) for k, v in bf[has].debut.value_counts().sort_index().items()},
            "primary": cells, "rule": rule, "null_N_b": {"cells": null_cells, "rule": null_rule},
            "planted_P_b": {"rho": PLANT_B_RHO, "cells": planted_cells, "rule": planted_rule},
            "reported": reported, "predictor_at_milb_primary": alt, "per_position": per_pos,
            "verdict": _verdict(rule, null_rule, planted_rule)}


def read_c(bf, grades: dict, b: int, seed: int) -> dict:
    import numpy as np
    cf = bf.copy()
    cf["grade"] = cf.pid.map(grades).astype(float)
    cf = cf[_fin(cf.grade)]

    def pc(df, xcol, t):
        d = df[_fin(df[xcol]) & _fin(df[t])].copy()
        if len(d) < 5:
            return {"n": int(len(d)), **summarize(None, np.array([]))}
        d["xc"] = _centre(d, xcol, "pos")
        d["yc"] = _centre(d, t, "pos")
        x, y, g = d.xc.to_numpy(float), d.yc.to_numpy(float), d.grade.to_numpy(float)
        return {"n": int(len(d)), **summarize(partial_rank(x, y, g), boot(
            lambda i: partial_rank(x[i], y[i], g[i]), d.pid.to_numpy(), b, seed))}
    cells = {t: pc(cf, "pred", t) for t in ("T1", "T2")}
    rule = _rule(cells)
    grade_alone = {t: _cell(cf.assign(g=cf.grade), "g", t, b, seed) for t in ("T1", "T2")}
    pred_alone = {t: _cell(cf, "pred", t, b, seed) for t in ("T1", "T2")}
    nc = _permute_within_pos(cf, "pred", SEED_PERMUTE)
    null_cells = {t: pc(nc, "pred", t) for t in ("T1", "T2")}
    null_rule = _rule(null_cells)
    rng2 = np.random.default_rng(SEED_PLANT_B + 1)
    pcf = cf.copy()
    for t in ("T1", "T2"):
        ok = _fin(pcf.pred) & _fin(pcf[t])
        z = np.full(len(pcf), np.nan)
        if ok.sum() >= 5:
            zg = _rank(pcf.grade.to_numpy(float)[ok])
            zp = _rank(pcf.pred.to_numpy(float)[ok])
            zg = (zg - zg.mean()) / (zg.std() or 1.0)
            zp = (zp - zp.mean()) / (zp.std() or 1.0)
            sig = 0.5 * zg + 0.2 * zp
            z[ok] = sig + math.sqrt(max(1.0 - float(sig.var()), 0.05)) * rng2.normal(
                0, 1, int(ok.sum()))
        pcf[t] = z
    planted_cells = {t: pc(pcf, "pred", t) for t in ("T1", "T2")}
    planted_rule = _rule(planted_cells)
    return {"rows_with_grade": int(len(cf)), "primary": cells, "rule": rule,
            "grade_alone_spearman": grade_alone, "predictor_alone_spearman_same_rows": pred_alone,
            "null_N_c": {"cells": null_cells, "rule": null_rule},
            "planted_P_c": {"cells": planted_cells, "rule": planted_rule},
            "verdict": _verdict(rule, null_rule, planted_rule)}


def evaluate(res: dict, mlb: dict, grades: dict, b: int = B, seed: int = SEED, log=print) -> dict:
    st, kpos, F = res["st"], res["k"], res["levels"]["_F"]
    log("  (a) persistence")
    a = read_a(st, kpos, F, b, seed)
    log("  (a) null N-a")
    a_null = read_a(shuffle_stints(st, SEED_SHUFFLE), kpos, F, b, seed)
    log("  (a) planted P-a")
    a_plant = planted_a(res, b, SEED_PLANT_A)
    if a_null["lb95"] is not None and a_null["lb95"] > 0:
        va = "VOID"
    elif a_plant.get("verdict") != "PASS":
        va = "UNDERPOWERED"
    else:
        va = "PASS" if (a["lb95"] is not None and a["lb95"] > 0 and a_null["ub95"] is not None
                        and a["lb95"] > a_null["ub95"]) else "FAIL"
    log("  (b)")
    bf = b_frame(st, kpos, F, mlb)
    rb = read_b(bf, b, seed)
    log("  (c)")
    rc = read_c(bf, grades["field"], b, seed)
    return {"a_persistence": {**a, "null_N_a": {k: a_null[k] for k in
                                                ("pairs", "point", "lb95", "ub95")},
                              "planted_P_a": a_plant, "verdict": va},
            "b_mlb": rb, "c_incremental": rc, "_bf": bf}


# --- the fixture (dry run and tests) --------------------------------------------------

def fixture_records(seed: int = 7, games_per_cell: int = 60) -> list[dict]:
    """Synthetic reduced game records for two levels and three seasons, with players who
    move up a level in the same season, located and unlocated balls in play, double plays,
    outfield arm opportunities, steals and taken pitches (some without location)."""
    import random
    rnd = random.Random(seed)
    recs = []
    pid0 = 600000
    teams = {11: [1, 2, 3, 4], 12: [5, 6, 7, 8]}
    roster = {}
    for s in teams:
        for t in teams[s]:
            for k in POS_RATED + ("1",):
                roster[(t, k)] = pid0
                pid0 += 1
    gpk = 900000
    trajs = list(TRAJ)
    for season in (2021, 2022, 2023):
        for sport in (12, 11):
            for gi in range(games_per_cell):
                if sport == 11 and gi == games_per_cell // 2:
                    for k in POS_RATED:          # promotions: links between levels
                        roster[(1, k)] = roster[(5, k)]
                home, away = rnd.sample(teams[sport], 2)
                plays, runners, credits, subs, taken = [], [], [], [], []
                ab = 0
                for inning in range(1, 10):
                    for top in (1, 0):
                        dteam = home if top else away
                        outs = 0
                        while outs < 3:
                            traj = rnd.choice(trajs)
                            x = rnd.uniform(40, 210) if rnd.random() > 0.05 else None
                            y = rnd.uniform(40, 190) if x is not None else None
                            k = rnd.choice(POS_RATED[1:])
                            fielder = roster[(dteam, k)]
                            is_out = rnd.random() < 0.7
                            ev = (rnd.choice(["field_out", "grounded_into_double_play"]) if is_out
                                  else rnd.choice(["single", "double", "field_error"]))
                            n_out = (2 if (ev == "grounded_into_double_play" and outs == 0)
                                     else (1 if is_out else 0))
                            if ev == "grounded_into_double_play" and n_out == 1:
                                ev = "field_out"
                            outs = min(3, outs + n_out)
                            plays.append([ab, inning, top, ev, outs, rnd.choice("LR"), "X", traj,
                                          rnd.choice(["soft", "medium", "hard", None]),
                                          k, x, y, 3])
                            for _ in range(3):
                                px = rnd.uniform(-1.5, 1.5) if rnd.random() > 0.1 else None
                                taken.append([ab, rnd.choice(["B", "C", "*B"]), rnd.randint(0, 3),
                                              rnd.randint(0, 2), px, rnd.uniform(1, 4), 3.4, 1.6])
                            runners.append([ab, 3, 1000 + ab, None, None, None if is_out else "1B",
                                            1 if is_out else 0, ev])
                            if rnd.random() < 0.3:
                                runners.append([ab, 3, 2000 + ab, "1B", "1B",
                                                rnd.choice(["2B", "3B", "score", None]),
                                                1 if n_out == 2 else 0, ev])
                            cr = "f_assist" if is_out else "f_fielded_ball"
                            credits.append([ab, 3, ev, fielder, k, cr])
                            if is_out:
                                credits.append([ab, 3, ev, roster[(dteam, "3")], "3", "f_putout"])
                            credits.append([ab, 1, "strikeout", roster[(dteam, "2")], "2",
                                            "f_putout"])
                            if rnd.random() < 0.1:
                                sev = rnd.choice(list(STEAL_EVENTS))
                                runners.append([ab, 1, 3000 + ab, "1B", "1B", "2B",
                                                1 if "caught" in sev else 0, sev])
                            ab += 1
                recs.append({"v": ROW_VERSION, "gamePk": gpk,
                             "date": f"{season}-06-{1 + gi % 28:02d}",
                             "sportId": sport, "level": SPORTS[sport], "season": season,
                             "league": 1, "home": home, "away": away, "source": "fixture",
                             "plays": plays, "runners": runners, "credits": credits, "subs": subs,
                             "taken": taken})
                gpk += 1
    return recs


def fixture_mlb(st) -> dict:
    """MLB fixture: debuts in DEBUT_YEARS for some fixture players, targets with None/NaN."""
    import numpy as np
    import pandas as pd
    pids = sorted(st.pid.unique().tolist())
    rng = np.random.default_rng(3)
    debut = {p: int(rng.choice(DEBUT_YEARS)) for p in pids[: len(pids) // 2]}
    fg_rows, rf_rows = [], []
    for p, D in debut.items():
        pos = int(st[st.pid == p].groupby("pos").inn.sum().idxmax())
        for s in range(D, LAST_MLB + 1):
            fg_rows.append({"pid": p, "season": s, "pos": pos, "inn": 400.0,
                            "OAA": None if rng.random() < 0.2 else float(rng.normal()),
                            "UZR": None if s > UZR_LAST else float(rng.normal()),
                            "DRS": float(rng.normal()), "FRP": None})
            rf_rows.append({"pid": p, "season": s, "runs_field": None if rng.random() < 0.1 else
                            float(rng.normal()), "inn": 400.0})
    fg = pd.DataFrame(fg_rows)
    for c in ("OAA", "UZR", "DRS", "FRP"):
        fg[c] = pd.to_numeric(fg[c], errors="coerce")
    rf = pd.DataFrame(rf_rows)
    rf["runs_field"] = pd.to_numeric(rf.runs_field, errors="coerce")
    grades = {p: (None if rng.random() < 0.3 else float(rng.choice([40, 45, 50, 55, 60])))
              for p in debut}
    return {"fg": fg, "rf": rf, "debut": debut, "meta": {"fixture": True},
            "grades": {k: v for k, v in grades.items() if v is not None}}


def dry_run(out_path: Path | None = None, b: int = 40, log=print) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="mfr_dry_"))
    recs = fixture_records()
    for r in recs:
        _atomic_write_gz(game_path(r["sportId"], r["season"], r["gamePk"], tmp), r)
    sched = defaultdict(list)
    for r in recs:
        sched[(r["sportId"], r["season"])].append({"gamePk": r["gamePk"]})
    res = build(tmp, write=False, sports=(11, 12), seasons=(2021, 2022, 2023),
                schedule_fn=lambda s, y: sched.get((s, y), []), log=log)
    mlb = fixture_mlb(res["st"])
    ev = evaluate(res, mlb, {"field": mlb["grades"]}, b=b, log=log)
    art = artifact(res, ev, {"fixture": True}, {"fixture": True}, gate_sha=None, dry=True)
    if out_path is not None:
        out_path.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")
    return art


# --- the artifact and the one read --------------------------------------------------

def artifact(res, ev, mlb_meta, grade_meta, *, gate_sha, dry: bool) -> dict:
    ver = {"a": ev["a_persistence"]["verdict"], "b": ev["b_mlb"]["verdict"],
           "c": ev["c_incremental"]["verdict"]}
    return {
        "generated_at": _now(), "gate": GATE_DOC, "gate_sha": gate_sha, "dry_run": dry,
        "read": "OWNER-WAIVED EARLY READ (EW3-5); read once",
        "question": ("Does an in-house MiLB fielding-runs measure (MFR) persist within the minors, "
                     "predict MLB fielding runs after debut, and add to the consensus field grade?"),
        "verdicts": ver,
        "serves": ver["b"] == "PASS",
        "construction": {"k_innings": res["k"],
                         "levels": {k: v for k, v in res["levels"].items() if k != "_F"},
                         "in_cells": [list(c) for c in res["in_cells"]],
                         "constants": {"inn_floor": INN_FLOOR, "mlb_inn_floor": MLB_INN_FLOOR,
                                       "debut_years": list(DEBUT_YEARS), "B": B, "seed": SEED,
                                       "planted_sd": PLANT_SD, "planted_b_rho": PLANT_B_RHO,
                                       "dp_runs": DP_RUNS, "kill_rv": KILL_RV, "xb_rv": XB_RV,
                                       "frame_runs": FRAME_RUNS, "cs_runs": CS_RUNS, "rv": RV}},
        "inputs": {"mlb": mlb_meta, "grades": grade_meta},
        "a_persistence": ev["a_persistence"], "b_mlb": ev["b_mlb"],
        "c_incremental": ev["c_incremental"],
        "survivorship": ("(b) and (c) are among debuts only: players who reached the majors in "
                         "2022 to 2024 with 300+ MLB innings."),
    }


def cmd_read(a) -> int:
    if a.dry_run:
        art = dry_run(Path(tempfile.gettempdir()) / "milb_fielding_runs_dry.json")
        print(json.dumps(art["verdicts"]))
        print("dry run complete")
        return 0
    if EVAL_OUT.exists():
        prev = json.loads(EVAL_OUT.read_text(encoding="utf-8"))
        if not prev.get("dry_run"):
            print(f"REFUSED: the read is spent ({EVAL_OUT.name} exists)")
            return 3
    if not a.gate_sha:
        print("REFUSED: --gate-sha names the commit carrying the gate")
        return 3
    print(f"gate {GATE_DOC} at {a.gate_sha}", flush=True)
    mlb = load_mlb()
    grades = load_grades()
    print("inputs:", json.dumps({"war_daily": mlb["meta"]["war_daily"],
                                 "grades": grades["meta"]}), flush=True)
    print("building the measure", flush=True)
    res = build()
    print("scoring", flush=True)
    ev = evaluate(res, mlb, grades)
    art = artifact(res, ev, mlb["meta"], grades["meta"], gate_sha=a.gate_sha, dry=False)
    EVAL_OUT.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")
    ev["_bf"].to_parquet(TABLES / "b_rows.parquet", index=False)
    print(json.dumps(art["verdicts"]), flush=True)
    return 0


# --- entry -------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--sport", type=int)
    f.add_argument("--season", type=int)
    f.add_argument("--max-minutes", type=float)
    sub.add_parser("build")
    r = sub.add_parser("read")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--gate-sha")
    a = ap.parse_args(argv)
    if a.mode == "fetch":
        return cmd_fetch(a)
    if a.mode == "build":
        return cmd_build(a)
    if a.mode == "read":
        return cmd_read(a)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
