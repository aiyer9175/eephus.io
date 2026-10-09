# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4, batted-ball trajectory, hardness and spray columns from the MiLB pitch-event
cache, plus a park correction of obp_rel behind a flag (EFV4_PBP_BATTED_BALL_BUNDLE;
owner decisions EW2-8 to EW2-12, 2026-10-08: new sources only, read on the development
frames, and once more on the spent reserved frames, labelled as such, choosing nothing).

WHY. hitData (trajectory, hardness, fielder location, field coordinates) rides on every
ball in play of every cached MiLB game, the result-only eras included, so line-drive,
popup and pull rates exist wherever the pitch-event fetch (milb_pbp_fetch.py,
.cache/efv4_pbp) holds games. The W2_1b lane recorded them as absent (efv_w2_milb.ABSENT)
because the season lines carry ground and air outs only. Prior is low: the air-out share
read -0.0075, and graders see batted balls.

THE COLUMNS (each offered to the V2 SKILL head of its side, one at a time, admitted or
refused inside every fold by V2's own DS-06 rule):

    hitters   ld_h          line drives / balls in play
              pu_h          popups / balls in play
              pull_h        balls in play on the pull side of the level-season centre
                            line / balls in play with coordinates and a known hand
              oppo_hard_h   opposite-side balls in play graded hard / opposite-side
                            balls in play
    pitchers  gb_p          ground balls / balls in play against
              ld_against_p  line drives / balls in play against
              pu_p          popups / balls in play against

A ball in play is a pitch row with call code X, D or E and a trajectory in
{ground_ball, line_drive, fly_ball, popup}; bunts (bunt_grounder, bunt_popup,
bunt_line_drive) and empty trajectories are left out of every numerator and
denominator (declared default).

SPRAY. The centre line of a (sport, season) is the median coordX of the balls in play
fielded by the centre fielder (location 8); coordX below it is the left-field side. A
right-handed batter pulls to the left-field side, a left-handed batter to the right; a
switch hitter bats from the side opposite the pitcher's hand. Hands come from the
StatsAPI people map already on disk for the MiLB populations
(.cache/milb_platoon/hand_map.json, read only), overlaid by this module's own people
cache (.cache/efv4_pbp_bb/people, fetch_people: the ids the map lacks, EW2-11 window, one
request at a time, resumable). The spec named the board snapshots as the hand source;
they hold board players only, so the level-season pools (every player at the level,
never the frame) could not be built from them (declared default, reported). A ball with
no hand known adds to no spray count.

NORMS AND THE VALUE. Per (sport, season) pool, every player with at least NORM_MIN of a
statistic's denominator gives one rate; the pool's mean and standard deviation turn a
line's rate into a z (a pool of fewer than NORM_MIN_PLAYERS players, or no spread, gives
no z). For a read at year V the walk goes from the last MiLB season that had ENDED by the
read (efv_w2_milb.last_readable_season, the efv_dataset._milb_features rule) down to the
row's MiLB floor, keeps every (sport) line with at least LINE_MIN balls in play, and stops
after MAX_SEASONS seasons that held one. The value is the denominator-weighted mean z,
shrunk by D / (D + K) on the total denominator D (K per statistic, declared before any
read). A row with no qualifying line is None and the fit imputes the observed training
mean (no absence flag enters any head); the lab's DS-03 balance probe reads the
missingness on lv_dev.

THE PARK CORRECTION (arm w2b_park_obp_hit, hitters). For each (sport, season) and club,
effect = on-base share of every plate appearance in the club's home games minus that in
its road games, shrunk by n / (n + K_PARK_PA) with n the smaller of the two counts. A
row's correction is the PA-weighted mean effect over the parks of its own plate
appearances at the season and level its obp_rel was read from (the MiLB block's
milb_season and milb_level), times the obp_rel reliability weight pa / (pa + 50); the
candidate replaces obp_rel by obp_rel minus that correction. It enters only through
adjust_rows, which is the identity while PARK_ADJUST_OBP_REL is False (the default):
nothing served imports this module, and the read asserts that the replacement arm with
no correction reproduces the V2 base order bit for bit before it reads anything.

LEAKAGE. Only seasons that ended before the read; ids are the play's MLBAM ids, joined to
the frame's OUTCOME-BLIND id (`mlbam_id` on a list-vintage row, never `record_mlbam_id`;
the matrix id on the vintage-matched frame, as every wave-2 column reads it there); pools
and park effects use every player and game at the (sport, season), never the frame; no
column builder reads a label, WAR series or debut. Development reads never read a season
after DEV_SEASON_CAP; only the spent read reaches the R-VM cohort's 2024 season.

THE READS. Development (EW2-10): lv_dev through the screening lab's own Frame and
measure_arm (DS-06 refit per fold, the zero-information twin, the DS-03 balance probe),
and vm_dev at vm2 through tools/efv_v3_backtest's Inputs (DS-16 base parity and v3 base
parity asserted there), each against the V2 base and PROSPX consensus with E_cond CI95.
Spent (EW2-10): R-LV and R-VM through efv_v3_backtest.build_reserved on the committed
gate sha the 10-08 confirmation used; every block is labelled SPENT_NOTE, chooses and
tunes nothing and lands no progress-ledger row.

BANS. No served number moves. Nothing here groups, counts or averages anything by
consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md); the only summaries are counts by
(side, year) and the (sport, season) pools.

Run:  python efv_w2_pbp_bb.py --aggregate     (reduce .cache/efv4_pbp into per-pool counts)
      python efv_w2_pbp_bb.py --fetch-people  (batter and pitcher hands; EW2-11 window)
      python efv_w2_pbp_bb.py --check         (coverage receipt only, no statistic)
      python efv_w2_pbp_bb.py --read          (development and spent reads; artifact)
      python efv_w2_pbp_bb.py --ledger        (this module's development ledger rows)
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PBP_DIR = ROOT / ".cache" / "efv4_pbp"
CACHE_DIR = ROOT / ".cache" / "efv4_pbp_bb"
AGG_DIR = CACHE_DIR / "agg"
PEOPLE_PATH = CACHE_DIR / "people" / "hands.json"
#: A StatsAPI people map (bats, throws by MLBAM id) already on disk for the MiLB
#: populations of sport ids 11 to 14 and 16; read only.
PLATOON_HANDS = ROOT / ".cache" / "milb_platoon" / "hand_map.json"
OUT_PATH = DATA_DIR / "_labs" / "efv_w2" / "efv_w2_pbp_bb.json"
CONFIRM_PATH = DATA_DIR / "_labs" / "efv_v3" / "efv_v3_confirm.json"
TOOL = "efv_w2_pbp_bb.py"
ITEM = "EFV4_PBP_BATTED_BALL_BUNDLE"
WAVE = 2
MODEL_PREFIX = "efv_v2_screen:wave2:"
FROZEN_PROVIDER = "fwar"
SPENT_NOTE = "spent frame, read after the 10-08 confirmation"
NOTE = ("eFV v4 (EFV4_PBP_BATTED_BALL_BUNDLE), development read only: selects and "
        "adjudicates nothing")

#: THE FLAG. The park-corrected obp_rel enters a fit only through adjust_rows, which is
#: the identity while this is False. Nothing served reads this module.
PARK_ADJUST_OBP_REL = False

API = "https://statsapi.mlb.com/api/v1"
USER_AGENT = ("BaseballR prospect-tracker eFV-v4 research fetch (MiLB batter and pitcher "
              "hands; cached, resumable, one request at a time)")
FETCH_DATES = frozenset({date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 10)})
BLACKOUT_UTC_HOURS = range(6, 11)
PEOPLE_CHUNK = 150
PAUSE_S = 0.25

#: StatsAPI sport id -> the level name the frames use (milb_history.SPORT_LEVEL; sport
#: 16 is complex or DSL by league and takes no park correction).
SPORT_LEVEL: dict[int, str] = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A", 16: "ROK"}
SPORTS: tuple[int, ...] = (11, 12, 13, 14, 15, 16)
FIRST_SEASON = 2006
#: Development reads read no season after this; the spent read may reach the season
#: before the R-VM cohort.
DEV_SEASON_CAP = F.R_VM_FIRST_DEBUT_YEAR - 2
SPENT_SEASON_CAP = F.R_VM_FIRST_DEBUT_YEAR - 1
AGG_VERSION = 1

BIP_CODES = frozenset({"X", "D", "E"})
TRAJ = ("ground_ball", "line_drive", "fly_ball", "popup")
ON_BASE = frozenset({"single", "double", "triple", "home_run", "walk", "intent_walk",
                     "hit_by_pitch"})
#: Event prefixes that are not a completed plate appearance (baserunning ends, sacrifice
#: bunts, interference) and so leave the on-base denominator.
NOT_PA_PREFIXES: tuple[str, ...] = (
    "caught_stealing", "pickoff", "stolen_base", "wild_pitch", "passed_ball", "balk",
    "other_advancement", "runner_double_play", "defensive_indiff", "sac_bunt",
    "catcher_interf", "other_out", "game_advisory", "ejection", "injury",
    "batter_timeout", "os_ruling_pending", "field_out_runner", "error")

#: Columns of the per-pool counts.
BAT_COLS = ("pa", "ob", "bip", "gb", "ld", "fb", "pu", "hard", "spray", "pull", "oppo",
            "oppo_hard")
PIT_COLS = ("bf", "bip", "gb", "ld", "fb", "pu")
PARK_COLS = ("home_pa", "home_ob", "road_pa", "road_ob")

NORM_MIN = 50.0
NORM_MIN_PLAYERS = 30
LINE_MIN = 20.0
MAX_SEASONS = 2
K_PARK_PA = 2000.0
K_OBP_PA = 50.0

#: Statistic -> (side, numerator, denominator, shrink K in denominator units). K is the
#: published stabilization point of the nearest MLB rate where one exists (line-drive
#: rate about 600 balls in play, ground-ball rate about 70 to 80), else a declared
#: value; declared 2026-10-09 before any read, never tuned on a frame.
STATS: dict[str, dict] = {
    "ld_h": {"side": "hit", "num": "ld", "den": "bip", "k": 600.0,
             "what": "line drives / balls in play"},
    "pu_h": {"side": "hit", "num": "pu", "den": "bip", "k": 400.0,
             "what": "popups / balls in play"},
    "pull_h": {"side": "hit", "num": "pull", "den": "spray", "k": 200.0,
               "what": "pull-side balls in play / balls in play with a side"},
    "oppo_hard_h": {"side": "hit", "num": "oppo_hard", "den": "oppo", "k": 400.0,
                    "what": "opposite-side balls in play graded hard / opposite-side "
                            "balls in play"},
    "gb_p": {"side": "pit", "num": "gb", "den": "bip", "k": 70.0,
             "what": "ground balls / balls in play against"},
    "ld_against_p": {"side": "pit", "num": "ld", "den": "bip", "k": 650.0,
                     "what": "line drives / balls in play against"},
    "pu_p": {"side": "pit", "num": "pu", "den": "bip", "k": 400.0,
             "what": "popups / balls in play against"},
}
#: The column arms: each statistic offered to the skill head of its side.
ARMS: tuple[dict, ...] = tuple(
    {"name": f"w2b_{s}", "stat": s, "side": spec["side"], "head": "skill",
     "kind": "column", "retest": False,
     "column": {"source": "module", "module": "efv_w2_pbp_bb", "attr": "screen_column",
                "arg": s}}
    for s, spec in STATS.items())
#: The replacement arm: obp_rel park-corrected, hitters (not a column, so not in ARMS
#: and not in the screening lab's wave 2 list).
PARK_ARM: dict = {"name": "w2b_park_obp_hit", "stat": "park_obp_rel", "side": "hit",
                  "head": "skill", "kind": "replace", "replaces": "obp_rel",
                  "retest": False}


# ---------------------------------------------------------------------------
# reading the pitch-event cache
# ---------------------------------------------------------------------------

def _read_gz(path: Path):
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def is_pa(event) -> bool:
    if not event:
        return False
    return not str(event).startswith(NOT_PA_PREFIXES)


def is_bip(code, traj) -> bool:
    return code in BIP_CODES and traj in TRAJ


def bat_side(bats: str | None, throws: str | None) -> str | None:
    """The side a batter hits from: his own hand, or for a switch hitter the side
    opposite the pitcher's hand. None when it cannot be told."""
    if bats in ("R", "L"):
        return bats
    if bats == "S":
        return {"R": "L", "L": "R"}.get(throws or "")
    return None


def pull_of(side: str | None, x, x0) -> int | None:
    """1 pull, 0 opposite, None (no side, no coordinate, no centre line, or on it)."""
    if side is None or x is None or x0 is None or float(x) == float(x0):
        return None
    left = float(x) < float(x0)
    return int(left) if side == "R" else int(not left)


def _games(sport: int, season: int, pbp_dir: Path | None = None):
    d = (pbp_dir or PBP_DIR) / str(int(sport)) / str(int(season))
    if not d.exists():
        return
    for p in sorted(d.glob("*.json.gz")):
        yield _read_gz(p)


def aggregate_pool(sport: int, season: int, *, hands: dict | None = None,
                   games=None) -> dict:
    """Per-pool counts of one (sport, season): per batter BAT_COLS, per pitcher
    PIT_COLS, per club PARK_COLS, per batter plate appearances by park (home club), the
    centre line and a census. `games` replaces the cache read (tests)."""
    games = _games(sport, season) if games is None else games
    bat: dict = {}
    pit: dict = {}
    park: dict = {}
    batpark: dict = {}
    census = {"games": 0, "pa": 0, "bip": 0, "bip_coords": 0, "traj": {}, "hard": {},
              "traj_not_in_play": 0, "bunts": 0}
    held: list = []          # (batter, pitcher, x, hard) of every ball in play
    cf_x: list = []
    for g in games:
        census["games"] += 1
        home, away = g.get("home"), g.get("away")
        pa_by_ab = {}
        for ab, batter, pitcher, event, _inn, _top in g.get("pa") or []:
            pa_by_ab[ab] = (batter, pitcher)
            if not is_pa(event) or batter is None:
                continue
            ob = 1 if event in ON_BASE else 0
            census["pa"] += 1
            b = bat.setdefault(batter, [0] * len(BAT_COLS))
            b[0] += 1
            b[1] += ob
            if pitcher is not None:
                pit.setdefault(pitcher, [0] * len(PIT_COLS))[0] += 1
            if home is not None:
                ph = park.setdefault(home, [0] * len(PARK_COLS))
                ph[0] += 1
                ph[1] += ob
                bp = batpark.setdefault(batter, {})
                bp[home] = bp.get(home, 0) + 1
            if away is not None:
                pa_ = park.setdefault(away, [0] * len(PARK_COLS))
                pa_[2] += 1
                pa_[3] += ob
        for ab, _n, code, _b0, _s0, _b1, _s1, traj, hard, loc, x, _y in g.get("pitches") or []:
            if traj and code not in BIP_CODES:
                census["traj_not_in_play"] += 1
            if traj and str(traj).startswith("bunt"):
                census["bunts"] += 1
            if not is_bip(code, traj):
                continue
            batter, pitcher = pa_by_ab.get(ab, (None, None))
            census["bip"] += 1
            census["traj"][traj] = census["traj"].get(traj, 0) + 1
            census["hard"][str(hard)] = census["hard"].get(str(hard), 0) + 1
            col = {"ground_ball": 3, "line_drive": 4, "fly_ball": 5, "popup": 6}[traj]
            if batter is not None:
                b = bat.setdefault(batter, [0] * len(BAT_COLS))
                b[2] += 1
                b[col] += 1
                b[7] += int(hard == "hard")
            if pitcher is not None:
                p = pit.setdefault(pitcher, [0] * len(PIT_COLS))
                p[1] += 1
                p[col - 1] += 1
            if x is not None:
                census["bip_coords"] += 1
                held.append((batter, pitcher, float(x), hard))
                if str(loc) == "8":
                    cf_x.append(float(x))
    x0 = float(np.median(cf_x)) if len(cf_x) >= 100 else None
    hand_known = 0
    if hands is not None and x0 is not None:
        for batter, pitcher, x, hard in held:
            if batter is None:
                continue
            bh = (hands.get(str(batter)) or {}).get("bats")
            th = (hands.get(str(pitcher)) or {}).get("throws") if pitcher is not None else None
            pull = pull_of(bat_side(bh, th), x, x0)
            if pull is None:
                continue
            hand_known += 1
            b = bat[batter]
            b[8] += 1
            b[9] += pull
            if not pull:
                b[10] += 1
                b[11] += int(hard == "hard")
    census["bip_with_side"] = hand_known
    return {"v": AGG_VERSION, "sport": int(sport), "season": int(season),
            "hands": hands is not None, "x0": x0, "x0_n": len(cf_x),
            "bat": {str(k): v for k, v in bat.items()},
            "pit": {str(k): v for k, v in pit.items()},
            "park": {str(k): v for k, v in park.items()},
            "batpark": {str(k): {str(t): n for t, n in v.items()} for k, v in batpark.items()},
            "census": census}


def _agg_path(sport: int, season: int) -> Path:
    return AGG_DIR / f"{int(sport)}_{int(season)}.v{AGG_VERSION}.json.gz"


def cached_pools(pbp_dir: Path | None = None) -> list[tuple[int, int]]:
    """(sport, season) pools the pitch-event cache holds games for."""
    base = pbp_dir or PBP_DIR
    out = []
    for sp in SPORTS:
        d = base / str(sp)
        if not d.exists():
            continue
        for s in sorted(d.iterdir()):
            if s.is_dir() and s.name.isdigit() and any(s.glob("*.json.gz")):
                out.append((sp, int(s.name)))
    return out


def aggregate_all(*, force: bool = False, log=print) -> dict:
    """Reduce every cached pool (with the hands when fetched); a pool already reduced
    with the same hands state is kept."""
    hands = load_hands()
    have_hands = bool(hands)
    out = {"pools": 0, "reduced": 0, "kept": 0, "hands": have_hands}
    AGG_DIR.mkdir(parents=True, exist_ok=True)
    for sp, se in cached_pools():
        out["pools"] += 1
        p = _agg_path(sp, se)
        if p.exists() and not force:
            try:
                if _read_gz(p).get("hands") == have_hands:
                    out["kept"] += 1
                    continue
            except (OSError, ValueError):
                pass
        t0 = time.time()
        doc = aggregate_pool(sp, se, hands=hands if have_hands else None)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(gzip.compress(json.dumps(doc, separators=(",", ":")).encode("utf-8"), 6))
        tmp.replace(p)
        out["reduced"] += 1
        log(f"  {SPORT_LEVEL[sp]:>3} {se}: {doc['census']['games']} games, "
            f"{doc['census']['bip']} balls in play, x0 {doc['x0']}, with side "
            f"{doc['census']['bip_with_side']} ({time.time() - t0:.1f} s)")
    _POOLS.clear()
    _norm.cache_clear()
    _effects.cache_clear()
    return out


_POOLS: dict = {}


def pools() -> dict:
    """{(sport, season): reduced pool} of every reduced file on disk (read once)."""
    if not _POOLS:
        if AGG_DIR.exists():
            for p in sorted(AGG_DIR.glob(f"*.v{AGG_VERSION}.json.gz")):
                d = _read_gz(p)
                _POOLS[(int(d["sport"]), int(d["season"]))] = d
        _POOLS["_loaded"] = True
    return {k: v for k, v in _POOLS.items() if k != "_loaded"}


def set_pools(docs) -> None:
    """Install reduced pools directly (tests)."""
    _POOLS.clear()
    for d in docs:
        _POOLS[(int(d["sport"]), int(d["season"]))] = d
    _POOLS["_loaded"] = True
    _norm.cache_clear()
    _effects.cache_clear()


# ---------------------------------------------------------------------------
# hands: the StatsAPI people endpoint (EW2-11 window)
# ---------------------------------------------------------------------------

def fetch_window_open(now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    day = now.astimezone().date()
    if day not in FETCH_DATES:
        return False, f"local date {day} is not a fetch date"
    h = now.astimezone(timezone.utc).hour
    if h in BLACKOUT_UTC_HOURS:
        return False, f"UTC hour {h:02d} is inside the 06:00 to 11:00 UTC blackout"
    return True, "open"


def _get(url: str, *, tries: int = 6) -> dict:
    for attempt in range(tries):
        ok, why = fetch_window_open()
        if not ok:
            raise RuntimeError(f"fetch window closed: {why}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and exc.code < 500:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(5 * (2 ** attempt))
    raise RuntimeError(f"no answer after {tries} tries: {url[:120]}")


def _read_hand_file(path: Path, key: str | None) -> dict:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc = (doc.get(key) or {}) if key else doc
    return {str(k): {"bats": (v or {}).get("bats"), "throws": (v or {}).get("throws")}
            for k, v in doc.items() if str(k).isdigit()}


def load_hands() -> dict:
    """{str(id): {"bats": code | None, "throws": code | None}}: the StatsAPI people
    map already on disk (PLATOON_HANDS, read only, never written), overlaid by this
    module's own people cache (PEOPLE_PATH) where that holds the id."""
    out = _read_hand_file(PLATOON_HANDS, None)
    out.update(_read_hand_file(PEOPLE_PATH, "hands"))
    return out


def pool_ids() -> list[int]:
    ids: set = set()
    for d in pools().values():
        ids |= {int(k) for k in d["bat"]}
        ids |= {int(k) for k in d["pit"]}
    return sorted(ids)


def fetch_people(*, log=print) -> dict:
    """Fill PEOPLE_PATH with the hands of every id in the reduced pools; ids already
    asked for are never asked again (resumable)."""
    doc = (json.loads(PEOPLE_PATH.read_text(encoding="utf-8")) if PEOPLE_PATH.exists()
           else {"hands": {}, "asked": []})
    asked = set(int(i) for i in doc.get("asked") or [])
    have = set(load_hands())
    todo = [i for i in pool_ids() if i not in asked and str(i) not in have]
    out = {"ids": len(asked) + len(todo), "todo": len(todo), "calls": 0}
    PEOPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(todo), PEOPLE_CHUNK):
        chunk = todo[i:i + PEOPLE_CHUNK]
        url = (f"{API}/people?personIds={','.join(str(x) for x in chunk)}"
               f"&fields=people,id,batSide,code,pitchHand")
        data = _get(url)
        out["calls"] += 1
        for p in data.get("people") or []:
            doc["hands"][str(p["id"])] = {"bats": (p.get("batSide") or {}).get("code"),
                                          "throws": (p.get("pitchHand") or {}).get("code")}
        asked |= set(chunk)
        doc["asked"] = sorted(asked)
        doc["fetched_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        doc["source"] = f"{API}/people?personIds=... fields batSide, pitchHand"
        tmp = PEOPLE_PATH.with_name(PEOPLE_PATH.name + ".tmp")
        tmp.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        tmp.replace(PEOPLE_PATH)
        if out["calls"] % 50 == 0:
            log(f"  people: {out['calls']} calls, {len(asked)} ids asked")
        time.sleep(PAUSE_S)
    out["with_hand"] = len(doc["hands"])
    return out


# ---------------------------------------------------------------------------
# norms, lines, the as-of value
# ---------------------------------------------------------------------------

def _counts(pool: dict, side: str, pid) -> dict | None:
    row = (pool["bat"] if side == "hit" else pool["pit"]).get(str(pid))
    if row is None:
        return None
    return dict(zip(BAT_COLS if side == "hit" else PIT_COLS, row))


def rate(counts: dict | None, stat: str) -> tuple[float | None, float]:
    spec = STATS[stat]
    if not counts:
        return None, 0.0
    den = float(counts.get(spec["den"]) or 0.0)
    if den <= 0:
        return None, 0.0
    return float(counts.get(spec["num"]) or 0.0) / den, den


@lru_cache(maxsize=None)
def _norm(sport: int, season: int, stat: str) -> tuple | None:
    """(mean, sd, n) of the rate over every player in the pool with at least NORM_MIN
    of its denominator; None when the pool is thin or has no spread."""
    pool = pools().get((int(sport), int(season)))
    if pool is None:
        return None
    side = STATS[stat]["side"]
    vals = []
    for row in (pool["bat"] if side == "hit" else pool["pit"]).values():
        r, den = rate(dict(zip(BAT_COLS if side == "hit" else PIT_COLS, row)), stat)
        if r is not None and den >= NORM_MIN:
            vals.append(r)
    if len(vals) < NORM_MIN_PLAYERS:
        return None
    a = np.asarray(vals, dtype=np.float64)
    sd = float(a.std())
    if not math.isfinite(sd) or sd <= 1e-9:
        return None
    return float(a.mean()), sd, len(vals)


def last_readable_season(read_year: int, cutoff: str | None) -> int:
    """efv_dataset._milb_features' as-of rule (efv_w2_milb.last_readable_season):
    read_year - 1, lowered when the cutoff falls before 1 October of a season."""
    first = int(read_year) - 1
    if cutoff:
        try:
            cy, cm = int(str(cutoff)[:4]), int(str(cutoff)[5:7])
            first = min(first, cy if cm >= 10 else cy - 1)
        except (ValueError, IndexError):
            pass
    return first


def profile(mlbam, read_year: int, cutoff: str | None, side: str, floor: int, *,
            season_cap: int, stats=None) -> dict:
    """{stat: value | None} for one person read at `read_year` (as of `cutoff`), plus
    "_seasons", the seasons read. Only seasons from the floor up to the last readable
    one (and never past season_cap) are walked."""
    stats = [s for s in (stats or STATS) if STATS[s]["side"] == side]
    out: dict = {s: None for s in stats}
    out["_seasons"] = []
    try:
        pid = int(mlbam) if mlbam is not None else None
    except (TypeError, ValueError):
        pid = None
    if pid is None:
        return out
    top = min(last_readable_season(read_year, cutoff), int(season_cap))
    acc = {s: [0.0, 0.0] for s in stats}
    used = 0
    allp = pools()
    for season in range(top, max(int(floor), FIRST_SEASON) - 1, -1):
        lines = []
        for sp in SPORTS:
            pool = allp.get((sp, season))
            c = _counts(pool, side, pid) if pool else None
            if c and float(c.get("bip") or 0.0) >= LINE_MIN:
                lines.append((sp, c))
        if not lines:
            continue
        used += 1
        out["_seasons"].append(season)
        for sp, c in lines:
            for s in stats:
                r, den = rate(c, s)
                nm = _norm(sp, season, s)
                if r is None or nm is None or den <= 0:
                    continue
                acc[s][0] += (r - nm[0]) / nm[1] * den
                acc[s][1] += den
        if used >= MAX_SEASONS:
            break
    for s in stats:
        num, den = acc[s]
        if den > 0:
            out[s] = (num / den) * (den / (den + STATS[s]["k"]))
    return out


# ---------------------------------------------------------------------------
# the park correction
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _effects(sport: int, season: int) -> dict:
    """{club: shrunk home-minus-road on-base share} of one pool."""
    pool = pools().get((int(sport), int(season)))
    out = {}
    if pool is None:
        return out
    for club, (hp, hob, rp, rob) in pool["park"].items():
        if hp <= 0 or rp <= 0:
            out[club] = 0.0
            continue
        n = float(min(hp, rp))
        out[club] = (hob / hp - rob / rp) * (n / (n + K_PARK_PA))
    return out


def park_correction(mlbam, season, level, *, season_cap: int) -> float | None:
    """The obp_rel correction of one MiLB block (its milb_season and milb_level): the
    PA-weighted mean park effect of the player's own plate appearances there, times
    pa / (pa + 50). None when the block's season or level is not in the cache."""
    try:
        pid, season = int(mlbam), int(season)
    except (TypeError, ValueError):
        return None
    if season > int(season_cap) or level not in ("AAA", "AA", "A+", "A"):
        return None
    tot, num = 0, 0.0
    seen = False
    for sp, lv in SPORT_LEVEL.items():
        if lv != level:
            continue
        pool = pools().get((sp, season))
        if pool is None:
            continue
        seen = True
        eff = _effects(sp, season)
        for club, n in (pool["batpark"].get(str(pid)) or {}).items():
            tot += n
            num += n * eff.get(club, 0.0)
    if not seen or tot <= 0:
        return None
    return (num / tot) * (tot / (tot + K_OBP_PA))


def adjust_rows(rows: list[dict], corr: dict, kind: str, *, on: bool | None = None
                ) -> list[dict]:
    """Rows (copies) whose v2 obp_rel is replaced by obp_rel minus the row's correction
    (corr {(year, player_key, kind): value}). THE IDENTITY (the same list, untouched)
    unless `on`, or PARK_ADJUST_OBP_REL when `on` is None, is True."""
    if not (PARK_ADJUST_OBP_REL if on is None else on):
        return rows
    out = []
    for r in rows:
        c = corr.get((int(r["decision_year"]), r["player_key"], kind))
        v = r["v2"].get("obp_rel")
        if c is None or v is None:
            out.append(r)
            continue
        out.append(dict(r, v2=dict(r["v2"], obp_rel=float(v) - float(c))))
    return out


# ---------------------------------------------------------------------------
# the list-vintage column (the screening lab's hook)
# ---------------------------------------------------------------------------

def lv_profiles(side: str, frames: dict, *, season_cap: int = DEV_SEASON_CAP) -> dict:
    """{(V, player_key): profile} on the side's list-vintage frame rows, each read on
    its outcome-blind id at its own window start and MiLB floor."""
    import efv_dataset as D
    out = {}
    for V in sorted((frames.get(side) or {})):
        F.guard_score_request(int(V), purpose="w2 pbp batted-ball column")
        for r in frames[side][V][0]:
            out[(int(V), r["player_key"])] = profile(
                r.get("mlbam_id"), int(V), (r.get("window") or [None])[0], side,
                int(r.get("milb_floor") or D.MILB_FLOOR_DEFAULT), season_cap=season_cap)
    return out


_LV_MEMO: dict = {}


def screen_column(stat: str, side: str, frames: dict) -> dict:
    """The screening lab's builder hook (column source "module", arg = statistic):
    {(V, player_key): value | None} on the side's list-vintage frame rows."""
    if stat not in STATS:
        raise ValueError(f"unknown statistic {stat!r}")
    if STATS[stat]["side"] != side:
        raise ValueError(f"{stat} is a {STATS[stat]['side']} column, not {side}")
    key = (side, id(frames))
    if key not in _LV_MEMO:
        _LV_MEMO.clear()
        _LV_MEMO[key] = lv_profiles(side, frames)
    return {slot: p.get(stat) for slot, p in _LV_MEMO[key].items()}


def coverage(values: dict, stat: str) -> dict:
    """{str(year): {"rows", "with_value"}} of {(year, ...): {stat: v}}."""
    out: dict = {}
    for k, v in values.items():
        c = out.setdefault(str(k[0]), {"rows": 0, "with_value": 0})
        c["rows"] += 1
        c["with_value"] += int((v or {}).get(stat) is not None)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# helpers shared by the reads
# ---------------------------------------------------------------------------

def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


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


def _key(arm: dict) -> str:
    import efv_v2_model as H
    return f"{H.V2_SCREEN_PREFIX}{arm['name']}"


@contextmanager
def registered_columns():
    """The column arms as efv_v3 W2_COLUMNS entries for the duration of one read (the
    Inputs path validates an added column against that table); removed afterwards, so
    the v3 selection menu is never widened."""
    import efv_v3 as V3
    added = []
    for arm in ARMS:
        if arm["name"] in V3.W2_COLUMNS:
            continue
        V3.W2_COLUMNS[arm["name"]] = {"side": arm["side"], "head": "skill",
                                      "module": "efv_w2_pbp_bb", "arg": arm["stat"],
                                      "key": _key(arm)}
        added.append(arm["name"])
    try:
        yield
    finally:
        for n in added:
            V3.W2_COLUMNS.pop(n, None)


@contextmanager
def _frames_fixed(frames_lv: dict | None):
    """efv_v2_assemble.build_frames answers `frames_lv` (built once per run)."""
    _tools()
    import efv_v2_assemble as ASM
    orig = ASM.build_frames
    if frames_lv is not None:
        ASM.build_frames = lambda *a, **k: frames_lv
    try:
        yield
    finally:
        ASM.build_frames = orig


def _cand(arm: dict) -> dict:
    out = {k: arm[k] for k in ("name", "side", "head", "kind", "retest", "column")}
    out["what"] = f"{arm['stat']}: {STATS[arm['stat']]['what']} (efv_w2_pbp_bb, skill head)"
    return out


# ---------------------------------------------------------------------------
# lv_dev: the screening lab's own Frame and measure_arm
# ---------------------------------------------------------------------------

def has_value_read(LAB, frame, side: str, order: dict, values: dict, *, B: int) -> dict:
    """The arm read again on the scored rows that carry a value only (the restriction
    the DS-03 probe asks for when the missingness is IMBALANCED, disclosed beside the
    full read): within delta against the V2 base and against consensus."""
    kept = {k: v for k, v in order.items() if values.get(k) is not None}
    cols = LAB._columns(frame, (side,), kept)
    keys, groups, y, pos, a, _b, cons, g = cols
    if not keys:
        return {"n": 0}
    vs_cons = (keys, groups, y, pos, a, list(cons), cons, g)
    return {"n": len(keys),
            "rule": "scored rows whose column value is not None (no imputed row)",
            "within_vs_v2": LAB._delta(cols, "within", B=B, seed=LAB.SEED),
            "within_vs_consensus": LAB._delta(vs_cons, "within", B=B, seed=LAB.SEED)}


def lv_read(arms, *, B: int, log=print) -> tuple[dict, dict]:
    """Every column arm on lv_dev (list vintages 2017 to 2019) through the lab's Frame
    and measure_arm: DS-06 refit inside every fold with the column offered to the skill
    head, the zero-information twin, the DS-03 balance probe on the column's
    missingness, and the consensus leg. No floor and no permutation null: a development
    read forms no verdict. Returns (block, the frames it built)."""
    _tools()
    import efv_screen_lab as LAB
    t0 = time.time()
    frame, frames = LAB.real_frame()
    log(f"lv_dev frame built in {time.time() - t0:.0f} s")
    base_vs_cons = {}
    for s in F.SIDES:
        order = {}
        for V in frame.folds:
            for pk, idx in frame.base(s, V)["order"].items():
                order[(V, pk)] = idx
        base_vs_cons[s] = LAB._vs_consensus(frame, (s,), order, B=B)
    out = {"frame": {"id": "lv_dev", "folds": list(frame.folds), "counts": frame.counts,
                     "w_star_dev": frame.w_star, "label": frame.label},
           "coverage": {}, "arms": {}}
    for s in F.SIDES:
        prof = lv_profiles(s, frames)
        out["coverage"][s] = {st: coverage(prof, st) for st in STATS
                              if STATS[st]["side"] == s}
    for arm in arms:
        t1 = time.time()
        values = screen_column(arm["stat"], arm["side"], frames)
        a = LAB.measure_arm(frame, _cand(arm), values, {}, B=B, n_perm=0,
                            base_vs_cons=base_vs_cons)
        a["has_value_rows"] = has_value_read(LAB, frame, arm["side"], a.pop("_order", None)
                                             or {}, values, B=B)
        a.pop("permutation_null", None)
        a["tag"] = f"SCREEN-W{WAVE}:{arm['side']}.skill.{arm['name']}"
        a["model_id"] = f"{MODEL_PREFIX}{arm['name']}:{arm['side']}"
        a["frame"]["note"] = NOTE
        out["arms"][arm["name"]] = a
        w = a["within"]
        vc = a["frame"]["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
        log(f"  lv_dev {arm['name']}: admitted {a['admitted_folds']}/{a['n_folds']}, within "
            f"vs V2 {w.get('delta')} {w.get('ci95')}, vs consensus {vc.get('delta')} "
            f"{vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out, frames


# ---------------------------------------------------------------------------
# the Inputs path (vm_dev, the park arm on every frame, the spent R-LV and R-VM)
# ---------------------------------------------------------------------------

COMPARISONS = (("candidate_vs_efv_v2_base", "efv_v3", "efv_v2"),
               ("candidate_vs_prospx_consensus", "efv_v3", "prospx_consensus"),
               ("efv_v2_base_vs_prospx_consensus", "efv_v2", "prospx_consensus"))
_RATER_NAMES = {"efv_v3": "efv_v2_candidate", "efv_v2": "efv_v2_base"}


def frame_block(rows: list[dict], *, B: int, frame_version: str, note: str) -> dict:
    """Raters and the within / pooled / AUC deltas of the candidate against the V2 base
    and against consensus, paired on identical rows (E_cond, player-clustered), in the
    screening ledger's shape."""
    _tools()
    import efv_v2_stat as S
    import efv_v3_backtest as BT
    blk = BT.frame_block(rows, B=B, stats=("within", "pooled", "auc"),
                         comparisons=COMPARISONS, scopes=("both",))
    raters = {_RATER_NAMES.get(k, k): v for k, v in blk["raters"].items()}
    years = sorted({int(str(g).split("|")[1]) for g in blk["groups"]})
    deltas = blk["deltas"]
    return {"frame_version": frame_version,
            "window": [min(years), max(years)] if years else None,
            "n": blk["n"], "n_by_side": blk["n_by_side"], "n_players": blk["n_players"],
            "groups": blk["groups"], "statistic": S.STAT_LABEL[S.PRIMARY],
            "raters": raters, "deltas": deltas,
            "secondary": {"statistic": S.STAT_LABEL["pooled"],
                          "raters": {n: r.get("pooled") for n, r in raters.items()},
                          "deltas": {n: {"delta": (d.get("pooled") or {}).get("delta"),
                                         "ci95": (d.get("pooled") or {}).get("ci95"),
                                         "mde95": (d.get("pooled") or {}).get("mde95"),
                                         "reading": (d.get("pooled") or {}).get("reading")}
                                     for n, d in deltas.items()}},
            "verdict": None, "note": note}


def _matrix_raw(side: str) -> dict:
    import efv_v2_model as H
    return {r["player_key"]: r for r in json.loads(
        H._matrix_path(side).read_text(encoding="utf-8"))}


def _slot_reads(inp, fid: str, kind: str, side: str, *, lv_rows: dict | None,
                raw: dict | None):
    """Yield ((year, player_key, part), id, read year, cutoff, floor, milb block) for
    every train and test row of one side of one Inputs frame. lv: the frame row's
    outcome-blind id at its window start and floor; vm: the matrix id at the decision
    year and the matrix cutoff, from the served default floor (efv_w2_milb.vm_profiles'
    convention)."""
    import efv_dataset as D
    for _fold, blk in inp.frames[fid]["by_side"][side].items():
        for part in ("train", "test"):
            for r in blk[part]:
                y, pk = int(r["decision_year"]), r["player_key"]
                if kind == "lv":
                    fr = (lv_rows or {}).get((side, y, pk))
                    if fr is None:
                        raise KeyError(f"{fid} {side} {y} {pk}: no frame row")
                    yield ((y, pk, part), fr.get("mlbam_id"), y,
                           (fr.get("window") or [None])[0],
                           int(fr.get("milb_floor") or D.MILB_FLOOR_DEFAULT), fr.get("milb"))
                else:
                    rw = (raw or {}).get(pk) or {}
                    yield ((y, pk, part), rw.get("mlbam_id"), y, rw.get("cutoff"),
                           D.MILB_FLOOR_DEFAULT, rw.get("milb"))


def inputs_columns(inp, fid: str, kind: str, *, season_cap: int,
                   lv_rows: dict | None = None) -> tuple[dict, dict, dict]:
    """({side: {arm name: {(year, player_key, part): value}}}, coverage, park
    corrections {(year, player_key, part): value | None} of the hitter rows) on one
    Inputs frame."""
    cols: dict = {s: {} for s in F.SIDES}
    cov: dict = {s: {} for s in F.SIDES}
    corr: dict = {}
    for side in F.SIDES:
        raw = _matrix_raw(side) if kind == "vm" else None
        vals: dict = {}
        for slot, pid, ry, cut, floor, milb in _slot_reads(inp, fid, kind, side,
                                                            lv_rows=lv_rows, raw=raw):
            vals[slot] = profile(pid, ry, cut, side, floor, season_cap=season_cap)
            if side == "hit":
                m = milb or {}
                corr[slot] = (park_correction(pid, m.get("milb_season"), m.get("milb_level"),
                                              season_cap=season_cap)
                              if pid is not None and m.get("milb_season") is not None
                              else None)
        for arm in ARMS:
            if arm["side"] == side:
                cols[side][arm["name"]] = {k: v[arm["stat"]] for k, v in vals.items()}
        cov[side] = {st: coverage(vals, st) for st in STATS if STATS[st]["side"] == side}
    cov["hit"]["park_obp_rel"] = coverage({k: {"park_obp_rel": v} for k, v in corr.items()},
                                          "park_obp_rel")
    return cols, cov, corr


def read_inputs_arm(inp, fid: str, arm: dict, *, B: int, frame_version: str,
                    note: str) -> dict:
    """One column arm on one Inputs frame: the V2 base with the column offered to the
    side's skill head under DS-06 in every fold, scored on the frame's rows."""
    import efv_v3 as V3
    cfg = V3.base_config()
    cfg["add"][arm["side"]]["skill"].append(arm["name"])
    V3.validate_config(cfg)
    orders, _rec = inp.orders(fid, cfg, sides=(arm["side"],))
    rows = inp.rows_with(fid, orders, sides=(arm["side"],))
    key = _key(arm)
    folds = {}
    for fold in inp.frames[fid]["by_side"][arm["side"]]:
        m = inp.fold_fit(fid, arm["side"], fold, cfg)["model"]
        sk = m.get("skill") or {}
        adm = (sk.get("admission") or {}).get(key) or {}
        beta = None
        if key in (sk.get("keys") or []):
            beta = round(float(sk["beta"][list(sk["keys"]).index(key)]), 5)
        folds[str(fold)] = {"admitted": key in (sk.get("keys") or []),
                            "reason": adm.get("reason") or m.get("consensus_only_reason"),
                            "per_vintage_signs": adm.get("per_vintage_signs"),
                            "mean_abs_t": adm.get("mean_abs_t"), "beta_std": beta,
                            "w_skill": m.get("w_skill"),
                            "skill_keys": list(sk.get("keys") or [])}
    return {"name": arm["name"], "side": arm["side"], "head": "skill", "folds": folds,
            "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
            "n_folds": len(folds),
            "frame": frame_block(rows, B=B, frame_version=frame_version, note=note)}


def park_orders(inp, fid: str, corr: dict, *, on: bool) -> tuple[dict, dict]:
    """({(side, fold, key): order_idx} of the hitter scored rows, fold receipts) with
    every training and test row's obp_rel replaced through adjust_rows(on=on), each
    fold refit (the cached base fits are not touched)."""
    import efv_v3 as V3
    cfg = V3.base_config()
    out, rec = {}, {}
    side = "hit"
    for fold, blk in inp.frames[fid]["by_side"][side].items():
        tr = adjust_rows(blk["train"], corr, "train", on=on)
        te = adjust_rows(blk["test"], corr, "test", on=on)
        f = inp.fold_fit(fid, side, fold, cfg, train=tr, test=te, cache=False)
        order = V3.order_index(f["parts"], f["w_skill0"], f["w_time0"])
        for c in blk["scored"]:
            out[(side, int(fold), c["key"])] = float(order[f["index"][c["key"]]])
        sk = f["model"].get("skill") or {}
        moved = sum(1 for r in tr if corr.get((int(r["decision_year"]), r["player_key"],
                                               "train")) not in (None, 0.0)
                    and r["v2"].get("obp_rel") is not None)
        rec[str(fold)] = {"obp_rel_in_skill": "obp_rel" in (sk.get("keys") or []),
                          "skill_keys": list(sk.get("keys") or []),
                          "train_rows_corrected": moved if on else 0,
                          "n_train": len(tr), "n_test": len(te)}
    return out, rec


def permuted_corrections(corr: dict, seed: int) -> dict:
    """The corrections permuted within (year, part) over the slots that carry one (the
    zero-information twin of the park arm)."""
    rng = np.random.default_rng(seed)
    by: dict = {}
    for k, v in corr.items():
        if v is not None:
            by.setdefault((k[0], k[2]), []).append(k)
    out = dict(corr)
    for grp in sorted(by):
        ks = sorted(by[grp], key=lambda k: k[1])
        vals = [corr[k] for k in ks]
        perm = rng.permutation(len(vals))
        for k, j in zip(ks, perm):
            out[k] = vals[int(j)]
    return out


def read_park_arm(inp, fid: str, corr: dict, *, B: int, frame_version: str,
                  note: str) -> dict:
    """The park arm on one Inputs frame: parity first (the replacement with no
    correction must reproduce V2's order on every hitter scored row, bit for bit), then
    the corrected candidate and its twin against the V2 base and consensus."""
    off, _r0 = park_orders(inp, fid, corr, on=False)
    bad = sum(1 for c in inp.scored(fid, sides=("hit",))
              if off[("hit", int(c["year"]), c["key"])] != float(c["grades"]["efv_v2"]))
    if bad:
        raise RuntimeError(f"{fid}: the park arm with no correction differs from V2 on "
                           f"{bad} rows; nothing read")
    on, rec = park_orders(inp, fid, corr, on=True)
    rows = inp.rows_with(fid, on, sides=("hit",))
    twin_corr = permuted_corrections(corr, seed=_seed(f"twin:{PARK_ARM['name']}:{fid}"))
    tw, _rt = park_orders(inp, fid, twin_corr, on=True)
    tw_rows = inp.rows_with(fid, tw, sides=("hit",))
    tw_blk = frame_block(tw_rows, B=B, frame_version=frame_version, note=note)
    vals = [v for v in corr.values() if v is not None]
    return {"name": PARK_ARM["name"], "side": "hit", "head": "skill", "kind": "replace",
            "replaces": "obp_rel", "folds": rec,
            "parity_off": {"rows": len(inp.scored(fid, sides=("hit",))), "differ": bad,
                           "reproduces": True},
            "correction": {"slots": len(corr), "with_value": len(vals),
                           "mean": round(float(np.mean(vals)), 6) if vals else None,
                           "sd": round(float(np.std(vals)), 6) if vals else None,
                           "abs_p95": (round(float(np.quantile(np.abs(vals), 0.95)), 6)
                                       if vals else None)},
            "twin": {"within": tw_blk["deltas"]["candidate_vs_efv_v2_base"]["spearman"]},
            "frame": frame_block(rows, B=B, frame_version=frame_version, note=note)}


def _seed(name: str) -> int:
    import efv_v2_stat as S
    h = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)
    return int((S.SEED_DEFAULT + h) % (2 ** 31 - 1))


def _log_arm(log, label: str, name: str, a: dict, t1: float) -> None:
    d = a["frame"]["deltas"]
    w, vc = d["candidate_vs_efv_v2_base"]["spearman"], \
        d["candidate_vs_prospx_consensus"]["spearman"]
    adm = (f"admitted {a['admitted_folds']}/{a['n_folds']}, " if "admitted_folds" in a
           else "")
    log(f"  {label} {name}: {adm}within vs V2 {w.get('delta')} {w.get('ci95')}, vs "
        f"consensus {vc.get('delta')} {vc.get('ci95')} ({time.time() - t1:.0f} s)")


def _lv_rows_dev(frames_lv: dict) -> dict:
    out = {}
    for side in F.SIDES:
        for V, (rows, _labs) in frames_lv[side].items():
            for r in rows:
                out[(side, int(V), r["player_key"])] = r
    return out


def dev_inputs_read(arms, frames_lv: dict, *, B: int, log=print) -> tuple[dict, dict]:
    """vm_dev for every column arm, and the park arm on lv_dev and vm_dev, through
    efv_v3_backtest's development Inputs (base parity with DS-16 and v3-at-base parity
    are asserted there before any arm is read). The v3 menu's own wave-2 columns are
    not built. Returns (vm_dev block, park block)."""
    _tools()
    import efv_v3_backtest as BT
    t0 = time.time()
    orig = BT.w2_values_dev
    BT.w2_values_dev = lambda inputs, fl, log=print: {fid: {s: {} for s in F.SIDES}
                                                       for fid in BT.FRAMES_DEV}
    try:
        with _frames_fixed(frames_lv):
            inp = BT.build_dev(log=log)
    finally:
        BT.w2_values_dev = orig
    years = sorted(int(y) for y in inp.frames["vm_dev"]["by_side"]["hit"])
    if any(y >= F.R_VM_FIRST_DEBUT_YEAR for y in years):
        raise F.ReservedFrameError(f"vm years reach R-VM: {years}")
    log(f"development inputs built in {time.time() - t0:.0f} s")
    cols_vm, cov_vm, corr_vm = inputs_columns(inp, "vm_dev", "vm",
                                              season_cap=DEV_SEASON_CAP)
    _c, cov_lv, corr_lv = inputs_columns(inp, "lv_dev", "lv", season_cap=DEV_SEASON_CAP,
                                         lv_rows=_lv_rows_dev(frames_lv))
    inp.cols = {"vm_dev": cols_vm}
    vm = {"frame": {"id": "vm_dev", "frame_version": "vm2", "fold_years": years,
                    "n_scored": len(inp.scored("vm_dev")),
                    "base_parity": inp.meta.get("base_parity", {}).get("reproduces"),
                    "v3_base_parity": inp.meta.get("v3_base_parity")},
          "coverage": cov_vm, "arms": {},
          "id_note": ("matrix ids, partly a debut proxy (B4); a row without one is None "
                      "and imputed at the fold's observed training mean")}
    with registered_columns():
        for arm in arms:
            t1 = time.time()
            a = read_inputs_arm(inp, "vm_dev", arm, B=B, frame_version="vm2", note=NOTE)
            vm["arms"][arm["name"]] = a
            _log_arm(log, "vm_dev", arm["name"], a, t1)
    park = {"arm": {k: PARK_ARM[k] for k in ("name", "side", "head", "kind", "replaces")},
            "flag": "efv_w2_pbp_bb.PARK_ADJUST_OBP_REL", "flag_default": PARK_ADJUST_OBP_REL,
            "frames": {}}
    for fid, fv, corr, cov in (("lv_dev", "lv1_v2", corr_lv, cov_lv["hit"]["park_obp_rel"]),
                               ("vm_dev", "vm2", corr_vm, cov_vm["hit"]["park_obp_rel"])):
        t1 = time.time()
        a = read_park_arm(inp, fid, corr, B=B, frame_version=fv, note=NOTE)
        a["coverage"] = cov
        park["frames"][fid] = a
        _log_arm(log, f"{fid} (park)", PARK_ARM["name"], a, t1)
    return vm, park


def gate_sha_from_confirm(path: Path = CONFIRM_PATH) -> str:
    """The committed gate sha the 10-08 confirmation read opened the reserved frames on,
    copied from its artifact and checked again here."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    sha = ((doc.get("gate") or {}).get("sha"))
    if not F.gate_sha_committed(sha):
        raise F.ReservedFrameError(f"the confirmation artifact's gate sha {sha!r} is not "
                                   "the committed registration")
    return sha


def spent_read(arms, frames_lv: dict, *, B: int, log=print) -> dict:
    """Every arm (the park arm included) on the SPENT reserved frames, R-LV (list
    vintages 2020 and 2021, W3) and R-VM (the 2025 debut cohort, vm2 rule), through
    efv_v3_backtest.build_reserved on the confirmation's gate sha; v3-at-base parity
    with the V2 base is asserted first. Every block is labelled SPENT_NOTE. It chooses
    and tunes nothing."""
    _tools()
    import efv_v3 as V3
    import efv_v3_backtest as BT
    gate_sha = gate_sha_from_confirm()
    t0 = time.time()
    with _frames_fixed(frames_lv):
        inp = BT.build_reserved(V3.base_config(), gate_sha=gate_sha, log=log)
    parity = BT.assert_v3_base_parity(inp, BT.FRAMES_RES)
    log(f"spent inputs built in {time.time() - t0:.0f} s; v3 base parity {parity}")
    lv_rows = _lv_rows_dev(frames_lv)
    for side in F.SIDES:
        for V, blk in inp.frames["lv_res"]["by_side"][side].items():
            for pk, r in blk["frame_rows"].items():
                lv_rows[(side, int(V), pk)] = r
    cols_lv, cov_lv, corr_lv = inputs_columns(inp, "lv_res", "lv",
                                              season_cap=SPENT_SEASON_CAP, lv_rows=lv_rows)
    cols_vm, cov_vm, corr_vm = inputs_columns(inp, "vm_pros", "vm",
                                              season_cap=SPENT_SEASON_CAP)
    inp.cols = {"lv_res": cols_lv, "vm_pros": cols_vm}
    out = {"note": SPENT_NOTE, "gate_sha": gate_sha, "v3_base_parity": parity,
           "guards": inp.guards, "frames": {}}
    names = {"lv_res": ("R-LV", "lv1_v2", cov_lv, corr_lv),
             "vm_pros": ("R-VM", "vm2", cov_vm, corr_vm)}
    with registered_columns():
        for fid, (label, fv, cov, corr) in names.items():
            blk = {"frame": {"id": fid, "label": label, "frame_version": fv,
                             "folds": sorted(int(y) for y in
                                             inp.frames[fid]["by_side"]["hit"]),
                             "n_scored": len(inp.scored(fid)), "note": SPENT_NOTE},
                   "coverage": cov, "arms": {}}
            for arm in arms:
                t1 = time.time()
                a = read_inputs_arm(inp, fid, arm, B=B, frame_version=fv, note=SPENT_NOTE)
                blk["arms"][arm["name"]] = a
                _log_arm(log, f"{label} (spent)", arm["name"], a, t1)
            t1 = time.time()
            a = read_park_arm(inp, fid, corr, B=B, frame_version=fv, note=SPENT_NOTE)
            blk["arms"][PARK_ARM["name"]] = a
            _log_arm(log, f"{label} (spent, park)", PARK_ARM["name"], a, t1)
            out["frames"][fid] = blk
    return out


# ---------------------------------------------------------------------------
# receipts, the artifact, the summary and the ledger rows
# ---------------------------------------------------------------------------

def pool_receipt() -> dict:
    """Per (sport, season): games, balls in play, trajectory and hardness shares, the
    centre line and the share of balls in play with a known side. Counts only."""
    out = {}
    for (sp, se), d in sorted(pools().items()):
        c = d["census"]
        bip = max(c["bip"], 1)
        out[f"{SPORT_LEVEL[sp]}|{sp}|{se}"] = {
            "games": c["games"], "pa": c["pa"], "bip": c["bip"],
            "traj_share": {k: round(v / bip, 4) for k, v in sorted(c["traj"].items())},
            "hard_share": {k: round(v / bip, 4) for k, v in sorted(c["hard"].items())},
            "bip_coords_share": round(c["bip_coords"] / bip, 4),
            "bip_with_side_share": round(c.get("bip_with_side", 0) / bip, 4),
            "x0": d["x0"], "x0_n": d["x0_n"], "hands": d["hands"],
            "traj_not_in_play": c["traj_not_in_play"]}
    return out


def norms_receipt() -> dict:
    """Pools each statistic could norm (no rate value)."""
    out = {}
    for s in STATS:
        have = sum(1 for (sp, se) in pools() if _norm(sp, se, s))
        out[s] = {"pools_normed": have, "pools": len(pools())}
    return out


def hands_receipt() -> dict:
    """Ids with a hand, by source, and the share of the pool ids covered. Counts only."""
    h = load_hands()
    bats: dict = {}
    for v in h.values():
        bats[str(v.get("bats"))] = bats.get(str(v.get("bats")), 0) + 1
    ids = pool_ids() if pools() else []
    return {"sources": {".cache/milb_platoon/hand_map.json (read only)":
                        len(_read_hand_file(PLATOON_HANDS, None)),
                        ".cache/efv4_pbp_bb/people/hands.json":
                        len(_read_hand_file(PEOPLE_PATH, "hands"))},
            "ids": len(h), "bats": bats,
            "pool_ids": len(ids),
            "pool_ids_with_hand": sum(1 for i in ids if str(i) in h),
            "source": "statsapi.mlb.com/api/v1/people batSide, pitchHand"}


def _leg(blk: dict, comp: str) -> list:
    d = ((blk.get("deltas") or {}).get(comp) or {}).get("spearman") or {}
    return [d.get("delta"), d.get("ci95")]


def _all_arms() -> list[dict]:
    return [{k: a[k] for k in ("name", "stat", "side", "head")} for a in ARMS] + [
        {k: PARK_ARM[k] for k in ("name", "stat", "side", "head")}]


def summary(doc: dict) -> list[dict]:
    """One line per arm: rows, admitted folds, within delta vs V2 and vs consensus with
    CI95 on every frame read. Copies only."""
    out = []
    for arm in doc.get("arms_declared") or []:
        n = arm["name"]
        row = {"arm": n, "side": arm["side"], "stat": arm["stat"]}
        blocks = [("lv_dev", (doc.get("lv_dev") or {}).get("arms")),
                  ("vm_dev", (doc.get("vm_dev") or {}).get("arms"))]
        for fid, b in ((doc.get("park") or {}).get("frames") or {}).items():
            blocks.append((fid, {PARK_ARM["name"]: b}))
        for fid, b in ((doc.get("spent") or {}).get("frames") or {}).items():
            blocks.append((fid, b.get("arms")))
        for fid, arms in blocks:
            a = (arms or {}).get(n)
            if not a:
                continue
            row[fid] = {"n": a["frame"]["n"],
                        "vs_v2": _leg(a["frame"], "candidate_vs_efv_v2_base"),
                        "vs_consensus": _leg(a["frame"], "candidate_vs_prospx_consensus")}
            if "admitted_folds" in a:
                row[fid]["admitted_folds"] = f"{a['admitted_folds']}/{a['n_folds']}"
            hv = a.get("has_value_rows") or {}
            if hv.get("n"):
                row[fid]["has_value_rows"] = {
                    "n": hv["n"],
                    "vs_v2": [hv["within_vs_v2"].get("delta"), hv["within_vs_v2"].get("ci95")],
                    "vs_consensus": [hv["within_vs_consensus"].get("delta"),
                                     hv["within_vs_consensus"].get("ci95")]}
            if fid in ("lv_res", "vm_pros"):
                row[fid]["note"] = SPENT_NOTE
        out.append(row)
    return out


def ledger_docs(doc: dict) -> list[dict]:
    """One development document per (arm, development frame) in the shape
    efv_progress.build_dev_rows reads. The spent frames land no row. Copies only."""
    out = []
    park = (doc.get("park") or {}).get("frames") or {}
    for arm in doc.get("arms_declared") or []:
        for fid in ("lv_dev", "vm_dev"):
            if arm["name"] == PARK_ARM["name"]:
                a = park.get(fid)
            else:
                a = ((doc.get(fid) or {}).get("arms") or {}).get(arm["name"])
            if not a:
                continue
            scr = {"wave": f"{WAVE} ({fid})", "exploratory": False,
                   "development_only": True, "adjudicates": False, "selects": False,
                   "head": "skill", "statistic_column": arm["stat"]}
            if "admitted_folds" in a:
                scr.update(admitted_folds=a["admitted_folds"], n_folds=a["n_folds"])
            else:
                scr.update(replaces="obp_rel", flag="PARK_ADJUST_OBP_REL")
            out.append({"role": "development",
                        "model_id": f"{MODEL_PREFIX}{arm['name']}:{arm['side']}",
                        "generated_at": doc.get("generated_at"),
                        "label": doc.get("label") or {}, "code": doc.get("code") or {},
                        "screening": scr, "frames": {fid: a["frame"]}})
    return out


def update_ledger(doc: dict | None = None, *, path: Path = OUT_PATH, ledger_path=None,
                  out_path=None, trigger: str = "efv_change") -> dict:
    """Append this module's development rows (and only them) to data/efv_progress.json
    through efv_progress.build_dev_rows and commit_rows. Idempotent."""
    import efv_progress as P
    doc = doc if doc is not None else json.loads(Path(path).read_text(encoding="utf-8"))
    now_dt = datetime.now(timezone.utc)
    now_iso = P._now_iso(now_dt)
    src = [{"path": P._rel(Path(path)), "generated_at": doc.get("generated_at"),
            "sha256": _sha(path)}]
    cands = []
    for d in ledger_docs(doc):
        cands += P.build_dev_rows(d, sources=src, date=now_dt.date().isoformat(),
                                  trigger=trigger, now_iso=now_iso,
                                  frames=tuple(d["frames"]), raters=P.SCREEN_RATERS,
                                  deltas=P.SCREEN_DELTAS, statistic_fields=True)
    if not cands:
        return {"appended": [], "status": "no development rows"}
    res = P.commit_rows(cands, out_path=out_path, ledger_path=ledger_path,
                        sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)
    res["status"] = "ok"
    return res


def check(*, log=print) -> dict:
    """The coverage receipt alone (pools, norms, hands), no frame and no statistic."""
    return {"pools": pool_receipt(), "norms": norms_receipt(), "hands": hands_receipt()}


def read(*, B: int | None = None, out: Path = OUT_PATH, spent: bool = True,
         log=print) -> dict:
    """The development read of every arm on lv_dev and vm_dev, then the spent read on
    R-LV and R-VM; writes the artifact."""
    import efv_labels as L
    import efv_v2_model as H
    import efv_v2_stat as S
    _tools()
    import efv_screen_lab as LAB
    if L.provider() != FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not the frozen "
                           f"{FROZEN_PROVIDER!r}")
    if not pools():
        raise RuntimeError("no reduced pools: run --aggregate first")
    B = S.B_DEFAULT if B is None else int(B)
    LAB.guards()
    t0 = time.time()
    doc = {"schema": 1, "item": ITEM,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "produced_by": TOOL, "wave": WAVE, "role": "development",
           "adjudicates": False, "selects": False, "exploratory": False, "note": NOTE,
           "owner_decision": ("EW2-8 to EW2-12 (2026-10-08): new sources only; choose on "
                              "the development frames; the reserved frames are spent"),
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "id": LAB.label_id()},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"), "tool": TOOL,
                    "module_sha256": _sha(Path(__file__)),
                    "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py")},
           "assembly_sha256": _sha(H.ASSEMBLY_PATH),
           "estimator": {"name": "E_cond", "B": B, "seed": S.SEED_DEFAULT,
                         "clusters": "player", "statistic": S.STAT_LABEL[S.PRIMARY]},
           "construction": {
               "stats": STATS, "head": "skill", "ball_in_play": (
                   "call code X, D or E with a trajectory in ground_ball, line_drive, "
                   "fly_ball, popup; bunts left out"),
               "spray": ("centre line = median coordX of the balls fielded by the centre "
                         "fielder in the (sport, season); a switch hitter bats opposite "
                         "the pitcher's hand"),
               "norm": ("z inside the (sport, season) pool of every player with at least "
                        f"{NORM_MIN:g} of the denominator (at least {NORM_MIN_PLAYERS} "
                        "players)"),
               "line_min_bip": LINE_MIN, "max_seasons": MAX_SEASONS,
               "shrink": "D / (D + K) on the total denominator",
               "as_of": "efv_dataset._milb_features rule (season Y readable from 1 "
                        "October of Y)",
               "dev_season_cap": DEV_SEASON_CAP, "spent_season_cap": SPENT_SEASON_CAP,
               "park": {"effect": ("on-base share of plate appearances in the club's home "
                                   "games minus its road games, shrunk n / (n + "
                                   f"{K_PARK_PA:g}) with n the smaller count"),
                        "correction": ("PA-weighted mean effect over the parks of the "
                                       "player's own plate appearances at the MiLB block's "
                                       "season and level, times pa / (pa + 50)"),
                        "on_base_events": sorted(ON_BASE),
                        "not_a_pa": list(NOT_PA_PREFIXES),
                        "levels": ["AAA", "AA", "A+", "A"]}},
           "source": {"pitch_events": ".cache/efv4_pbp (milb_pbp_fetch.py)",
                      "reduced": ".cache/efv4_pbp_bb/agg", "hands": hands_receipt()},
           "pools": pool_receipt(), "norms": norms_receipt(),
           "arms_declared": _all_arms(),
           "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                      "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                      "lv_folds": list(LAB.FOLDS), "anchor_gate_grouping": False}}
    arms = list(ARMS)
    if not load_hands():
        arms = [a for a in ARMS if STATS[a["stat"]]["den"] not in ("spray", "oppo")]
        doc["withheld"] = {a["name"]: "no hands fetched: the spray columns are not built"
                           for a in ARMS if a not in arms}
    doc["lv_dev"], frames_lv = lv_read(arms, B=B, log=log)
    doc["vm_dev"], doc["park"] = dev_inputs_read(arms, frames_lv, B=B, log=log)
    if spent:
        doc["spent"] = spent_read(arms, frames_lv, B=B, log=log)
    doc["summary"] = summary(doc)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(out)
    log(f"wrote {out} in {doc['elapsed_s']} s")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--aggregate", action="store_true", help="reduce .cache/efv4_pbp")
    ap.add_argument("--force", action="store_true", help="re-reduce every pool")
    ap.add_argument("--fetch-people", action="store_true",
                    help="fetch batter and pitcher hands (EW2-11 window)")
    ap.add_argument("--check", action="store_true", help="coverage receipt only")
    ap.add_argument("--read", action="store_true",
                    help="the development and spent reads; writes the artifact")
    ap.add_argument("--no-spent", action="store_true", help="skip the spent read")
    ap.add_argument("--ledger", action="store_true",
                    help="append this module's development rows from the artifact")
    ap.add_argument("--ledger-path", default=None,
                    help="durable ledger path (default: efv_progress's own)")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)
    if a.aggregate:
        log(json.dumps(aggregate_all(force=a.force, log=log), indent=1))
    if a.fetch_people:
        log(json.dumps(fetch_people(log=log), indent=1))
    if a.check:
        log(json.dumps(check(log=log), indent=1))
    if a.read:
        res = read(B=a.B, out=Path(a.out), spent=not a.no_spent, log=log)
        log(json.dumps(res["summary"], indent=1))
    if a.ledger:
        log(json.dumps(update_ledger(path=Path(a.out), ledger_path=a.ledger_path),
                       indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
