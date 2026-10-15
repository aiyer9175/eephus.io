# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4 wave 2, plate-discipline and whiff columns from the MiLB pitch-event cache
(EFV4_PBP_DISCIPLINE_ARMS; owner 2026-10-08, decisions EW2-8 to EW2-12; research s2.1,
s3.1 and s3.2 of the eFV v4 lane).

WHY. The components of the strikeout rate (whiffs against called and foul strikes)
persist differently and no public source carried minor-league whiff or contact rates
before 2021, so the graders behind the development vintages saw the K rate, not its
parts. V2 pitchers are the consensus order on every vm fold and carry only k_rel on lv;
a pitcher skill column the graders could not read is the one pitcher-side lever before
tracked data arrives (DIAG W2-H6). The k_resid columns are stat-versus-stat
disagreement terms.

SOURCE. The per-game pitch rows of .cache/efv4_pbp (milb_pbp_fetch.py,
EFV4_PBP_FETCH), read only. A (level, season) pool contributes only when the census
(data/_labs/efv_w2/pbp_census.json, cache part) lists it as planned and complete; a
game contributes only when it is FULL (at least FULL_GAME_PPA pitches per PA, the
census rule), so a result-only game or pool gives no value. aggregate() reduces every
pool once to per-player counts under .cache/efv4_pbp_discipline (this task's own
folder; nothing else under .cache is written).

COUNTS per (player, level, season), full games only. Call codes: whiff S, W, T; contact
F, X, D, E; called strike C; ball B, *B; bunts (L, M, O), intentional balls (I) and
automatic calls (V, A, AB, AC) are not swing decisions and leave every pitch count. A
PA counts when its event is a batter outcome (PA_EVENTS); its first pitch is the pitch
thrown at 0-0.

    hitters   swstr_h               whiffs / pitches
              contact_h             contact / swings
              swing_h               swings / pitches
              two_strike_contact_h  contact / swings at two strikes
              fstrike_taken_h       first-pitch called strikes / PA
              k_resid_h             z(K / PA) - b x z(swstr_h)
    pitchers  swstr_p               whiffs / pitches
              cstr_p                called strikes / pitches
              csw_p                 (called strikes + whiffs) / pitches
              fstrike_p             first-pitch strikes (any strike or ball in play) / BF
              ball_rate_p           balls / pitches
              k_resid_p             z(K / BF) - b x z(swstr_p)

POPULATION Z. Inside each (level, season) pool, every player line with at least
NORM_MIN exposure (PA or BF in full games) whose rate is defined sets the pool's mean
and standard deviation (unweighted over lines); a pool with fewer than NORM_MIN_LINES
such lines gives no value. A line's z is (rate - mean) / sd. The k_resid slope b is the
least-squares slope of z(K rate) on z(swstr) over the same qualifying lines of the same
pool: every player at the (level, season), never a frame row, and no outcome.

THE COLUMN, read for an MLBAM id at year R as of a cutoff: the last two PLAYED seasons
ending before R-01-01 (efv_w2_milb.last_readable_season, the efv_dataset._milb_features
rule, then back over 2020, which had no MiLB season), every line of the id in those
seasons pooled with PA or BF weights, the pooled z shrunk by D / (D + K) on the total
exposure D, K the declared stabilization point of the nearest MLB rate (SHRINK_K,
declared 2026-10-09 before any read; no K was tuned on any frame). An id with no line in
a complete pool reads None; "pbp_absent" (no value) is read only by the DS-03 balance
probe and never enters any head.

ID. A list-vintage row reads its OUTCOME-BLIND `mlbam_id` (efv_identity through
efv_vintage_frame), never `record_mlbam_id`; a vintage-matched row reads the matrix id,
as base V2 reads it there (the efv_w2_milb convention).

ARMS (12, one wave-2 Holm family), each column offered to the SKILL head of its side
through the screening lab (efv_v2_model.fit_v2 extra=..., DS-06 admission inside every
fold, unchanged).

READS.
  lv_dev primary (the family): the pbp_absent probe proxies level (A ball had no pitch
  events before 2016), so each side's arms are read on its HAS-FULL-PBP rows per fold:
  the training rows, test rows and scored rows of every fold restricted to the slots
  where every column of the side has a value, the V2 assembly refit there as the base
  (every frame player of the fold still excluded from its training rows, GATE s4.5).
  Floors from N_NOISE noise columns per head and side on that frame (forced mode, the
  lab's default), the zero-information twin, an N_PERM-draw permutation null, Holm over
  the 12 arms, the lab's admission clauses and verdict strings. Disclosed in the
  artifact as `restriction`.
  lv_dev full frame (secondary): the lab's own Frame (served-V2 fold fits), the column
  None off the has-pbp rows and imputed at the fold's training mean, no floor; also
  scored on the has-pbp rows alone.
  vm_dev: frame version vm2, DS-16's rows, base parity asserted; scored on every row and
  on the has-pbp rows alone.
  spent (EW2-10): R-LV and R-VM through tools/efv_v3_backtest.build_reserved on the gate
  sha the 10-08 confirmation read used; every block carries SPENT_LABEL, chooses and
  tunes nothing and lands no progress-ledger row.

BANS. No served number moves; nothing served imports this module; no flag. Nothing here
groups, counts or averages anything by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md):
the only summaries are counts by side and year and the (level, season) population
norms. No column builder reads a label, a realized value or a debut. List vintages 2020
and 2021 and the 2025 cohort raise through efv_vintage_frame unless the committed gate
sha is handed in (spent_read only). The aggregate runs through season 2026: 2024 is the
last season a development or reserved read here sees, and 2025 and 2026 are the seasons
the live board reads (efv5_combined._fam_pbp at read year 2027; EFV_FIX_A_PBP_2026, owner
EW3-21, docs/efv-v2/EFV_PBP_2026_AGGREGATE.md), the same pools and construction. Selects
and adjudicates nothing beyond the development family's own verdicts (EW2-10: choice uses
the development frames only).

Run:  python efv_w2_pbp.py --aggregate          (fill .cache/efv4_pbp_discipline)
      python efv_w2_pbp.py --norms              (print the pool receipt)
      python efv_w2_pbp.py --dev-read           (the development reads; the artifact)
      python efv_w2_pbp.py --spent-read --gate-sha SHA
      python efv_w2_pbp.py --ledger --ledger-path PATH
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv_w2"
OUT_PATH = LAB_DIR / "efv_w2_pbp.json"
CENSUS_PATH = LAB_DIR / "pbp_census.json"
PBP_DIR = ROOT / ".cache" / "efv4_pbp"
AGG_DIR = ROOT / ".cache" / "efv4_pbp_discipline"
TOOL = "efv_w2_pbp.py"
MODULE = "efv_w2_pbp"
ITEM = "EFV4_PBP_DISCIPLINE_ARMS"
WAVE = 2
MODEL_PREFIX = "efv_v2_screen:wave2:"
SPENT_LABEL = "spent frame, read after the 10-08 confirmation"
NOTE = ("eFV v4 wave 2 (EFV4 pitch-event discipline), development read: the family's "
        "verdicts choose on the development frames only (EW2-10)")
NOTE_PRIMARY = (NOTE + "; lv_dev read on the has-full-pbp rows only, the V2 assembly refit "
                "on them as the base (pbp_absent proxies level)")

#: StatsAPI sport id -> level (milb_pbp_fetch.SPORTS).
SPORT_LEVEL: dict[int, str] = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A-", 16: "ROK"}
#: Seasons the aggregate holds: the first AAA season fetched through 2026, the season the
#: live board reads (read year 2027 reads 2026 and 2025; EFV_FIX_A_PBP_2026). Development
#: and reserved reads stop at 2024 by their own guards (the 2025 debut cohort reads 2024).
#: 2020 had no MiLB season.
AGG_SEASONS: tuple[int, ...] = tuple(y for y in range(2007, 2027) if y != 2020)
NO_SEASON = frozenset({2020})
AGG_VERSION = 1
FULL_GAME_PPA = 3.0

WHIFF = frozenset({"S", "W", "T"})
CONTACT = frozenset({"F", "X", "D", "E"})
CALLED = frozenset({"C"})
BALL = frozenset({"B", "*B"})
#: Not a swing decision: bunts, intentional balls, automatic calls.
NOT_COUNTED = frozenset({"L", "M", "O", "I", "V", "A", "AB", "AC", "VB", "VC"})
#: First-pitch strike (fstrike_p): any strike or a ball in play, bunts included.
FIRST_STRIKE = WHIFF | CONTACT | CALLED | frozenset({"L", "M", "O", "Q", "R"})
K_EVENTS = frozenset({"strikeout", "strikeout_double_play", "strikeout_triple_play"})
PA_EVENTS = frozenset({
    "single", "double", "triple", "home_run", "field_out", "strikeout",
    "strikeout_double_play", "strikeout_triple_play", "walk", "intent_walk",
    "hit_by_pitch", "force_out", "grounded_into_double_play", "grounded_into_triple_play",
    "double_play", "triple_play", "field_error", "fielders_choice", "fielders_choice_out",
    "sac_fly", "sac_bunt", "sac_fly_double_play", "sac_bunt_double_play",
    "catcher_interf", "batter_interference", "fan_interference"})

#: Count vectors (one list per player line, in this order).
HIT_COUNTS = ("pitches", "swings", "whiffs", "pa", "so", "fp_den", "fp_called",
              "two_swings", "two_whiffs")
PIT_COUNTS = ("pitches", "whiffs", "called", "balls", "bf", "so", "fp_den", "fp_strike")
COUNTS = {"hit": HIT_COUNTS, "pit": PIT_COUNTS}
EXPOSURE = {"hit": "pa", "pit": "bf"}

#: Column -> (side, numerator, denominator). k_resid is built from the "k" rate and
#: swstr (population slope), so it has no ratio of its own.
RATES: dict[str, tuple[str, str, str]] = {
    "swstr_h": ("hit", "whiffs", "pitches"),
    "contact_h": ("hit", "contact", "swings"),
    "swing_h": ("hit", "swings", "pitches"),
    "two_strike_contact_h": ("hit", "two_contact", "two_swings"),
    "fstrike_taken_h": ("hit", "fp_called", "fp_den"),
    "k_h": ("hit", "so", "pa"),
    "swstr_p": ("pit", "whiffs", "pitches"),
    "cstr_p": ("pit", "called", "pitches"),
    "csw_p": ("pit", "csw", "pitches"),
    "fstrike_p": ("pit", "fp_strike", "fp_den"),
    "ball_rate_p": ("pit", "balls", "pitches"),
    "k_p": ("pit", "so", "bf"),
}
RESID = {"k_resid_h": ("k_h", "swstr_h"), "k_resid_p": ("k_p", "swstr_p")}
#: The twelve columns, in arm order.
COLUMNS: dict[str, tuple[str, ...]] = {
    "hit": ("swstr_h", "contact_h", "k_resid_h", "swing_h", "two_strike_contact_h",
            "fstrike_taken_h"),
    "pit": ("swstr_p", "cstr_p", "csw_p", "k_resid_p", "fstrike_p", "ball_rate_p"),
}
#: Shrinkage K in the side's exposure unit (PA or BF), the published stabilization point
#: of the nearest MLB rate (Carleton 2012 and 2013): contact rate 100 PA, swing rate 50
#: PA, K rate 60 PA (hitters); K rate 70 BF, BB rate 170 BF (pitchers). Declared
#: 2026-10-09 before any read; no K was tuned on any frame.
SHRINK_K: dict[str, float] = {
    "swstr_h": 100.0, "contact_h": 100.0, "k_resid_h": 60.0, "swing_h": 50.0,
    "two_strike_contact_h": 100.0, "fstrike_taken_h": 50.0,
    "swstr_p": 70.0, "cstr_p": 70.0, "csw_p": 70.0, "k_resid_p": 70.0,
    "fstrike_p": 170.0, "ball_rate_p": 170.0,
}
SHRINK_K_NEAREST: dict[str, str] = {
    "swstr_h": "contact rate", "contact_h": "contact rate", "k_resid_h": "K rate",
    "swing_h": "swing rate", "two_strike_contact_h": "contact rate",
    "fstrike_taken_h": "swing rate", "swstr_p": "K rate", "cstr_p": "K rate",
    "csw_p": "K rate", "k_resid_p": "K rate", "fstrike_p": "BB rate",
    "ball_rate_p": "BB rate"}
NORM_MIN = {"hit": 100, "pit": 100}
NORM_MIN_LINES = 30
POOL_SEASONS = 2

ARMS: tuple[dict, ...] = tuple(
    {"name": f"w2p_{c}", "stat": c, "side": s, "head": "skill", "kind": "column",
     "retest": False,
     "column": {"source": "module", "module": MODULE, "attr": "screen_column", "arg": c}}
    for s in ("hit", "pit") for c in COLUMNS[s])
#: Lab constants of this family (tools/efv_screen_lab.py values).
N_NOISE = 3
N_PERM = 500
FLOOR_MODE = "forced"


# ---------------------------------------------------------------------------
# the aggregate: per-player counts per (level, season) pool, full games only
# ---------------------------------------------------------------------------

def _read_gz(path: Path):
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def game_counts(rec: dict) -> tuple[bool, dict, dict]:
    """(full, {batter: counts}, {pitcher: counts}) of one cached game record. A game
    below FULL_GAME_PPA pitches per PA is not full and gives empty counts."""
    pas = rec.get("pa") or []
    pitches = rec.get("pitches") or []
    full = bool(pas) and len(pitches) / len(pas) >= FULL_GAME_PPA
    hit: dict = {}
    pit: dict = {}
    if not full:
        return False, hit, pit
    pc = rec.get("pitch_cols") or []
    ix = {c: i for i, c in enumerate(pc)}
    i_ab, i_code, i_b0, i_s0 = ix["ab"], ix["code"], ix["b0"], ix["s0"]
    by_ab: dict = {}
    for p in pitches:
        by_ab.setdefault(p[i_ab], []).append(p)
    for row in pas:
        ab, batter, pitcher, event = row[0], row[1], row[2], row[3]
        if batter is None or pitcher is None:
            continue
        h = hit.setdefault(int(batter), [0] * len(HIT_COUNTS))
        q = pit.setdefault(int(pitcher), [0] * len(PIT_COUNTS))
        first = True
        for p in by_ab.get(ab, ()):
            code = p[i_code]
            if code is None or code in NOT_COUNTED:
                first = False
                continue
            two = p[i_s0] == 2
            h[0] += 1
            q[0] += 1
            if code in WHIFF:
                h[1] += 1
                h[2] += 1
                q[1] += 1
                if two:
                    h[7] += 1
                    h[8] += 1
            elif code in CONTACT:
                h[1] += 1
                if two:
                    h[7] += 1
            elif code in CALLED:
                q[2] += 1
            elif code in BALL:
                q[3] += 1
            if first and event in PA_EVENTS and p[i_b0] == 0 and p[i_s0] == 0:
                h[5] += 1
                q[6] += 1
                if code in CALLED:
                    h[6] += 1
                if code in FIRST_STRIKE:
                    q[7] += 1
            first = False
        if event in PA_EVENTS:
            h[3] += 1
            q[4] += 1
            if event in K_EVENTS:
                h[4] += 1
                q[5] += 1
    return True, hit, pit


def complete_pools(census: dict | None = None) -> list[tuple[int, int]]:
    """(sport, season) pools the census lists as planned and complete, inside
    AGG_SEASONS. Every other pool (the probe's six sample games of an unplanned
    season, a result-only season) gives no value."""
    if census is None:
        census = json.loads(CENSUS_PATH.read_text(encoding="utf-8"))
    out = []
    for c in census["cache"]["cells"]:
        sp, y = int(c["sportId"]), int(c["season"])
        if c.get("fetch_planned") and c.get("complete") and y in AGG_SEASONS:
            out.append((sp, y))
    return sorted(out)


def _agg_path(sport: int, season: int) -> Path:
    return AGG_DIR / f"{int(sport)}_{int(season)}.v{AGG_VERSION}.json.gz"


def aggregate_pool(sport: int, season: int) -> dict:
    """Reduce one pool's cached games to {"hit": {id: counts}, "pit": {id: counts}}
    plus game counts; cached (a past season is final)."""
    path = _agg_path(sport, season)
    if path.exists():
        return _read_gz(path)
    files = sorted((PBP_DIR / str(int(sport)) / str(int(season))).glob("*.json.gz"))
    hit: dict = {}
    pit: dict = {}
    games = full = 0
    for f in files:
        rec = _read_gz(f)
        games += 1
        ok, gh, gp = game_counts(rec)
        if not ok:
            continue
        full += 1
        for side_acc, g in ((hit, gh), (pit, gp)):
            for pid, v in g.items():
                acc = side_acc.get(pid)
                if acc is None:
                    side_acc[pid] = list(v)
                else:
                    for i, x in enumerate(v):
                        acc[i] += x
    doc = {"v": AGG_VERSION, "sport": int(sport), "level": SPORT_LEVEL[int(sport)],
           "season": int(season), "games": games, "games_full": full,
           "hit_cols": list(HIT_COUNTS), "pit_cols": list(PIT_COUNTS),
           "hit": {str(k): v for k, v in hit.items()},
           "pit": {str(k): v for k, v in pit.items()}}
    AGG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with open(tmp, "wb") as fh:
        fh.write(gzip.compress(json.dumps(doc, separators=(",", ":")).encode("utf-8"), 6))
    os.replace(tmp, path)
    return doc


def _agg_job(job):
    sp, y = job
    t0 = time.time()
    d = aggregate_pool(sp, y)
    return sp, y, d["games"], d["games_full"], len(d["hit"]), len(d["pit"]), time.time() - t0


def aggregate(*, workers: int = 8, log=print) -> dict:
    """Fill AGG_DIR for every complete pool (resumable: a written pool is kept)."""
    jobs = complete_pools()
    out = {"pools": len(jobs), "rows": []}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for sp, y, g, fg, nh, npit, dt in ex.map(_agg_job, jobs):
            out["rows"].append([SPORT_LEVEL[sp], y, g, fg, nh, npit])
            log(f"  {SPORT_LEVEL[sp]:>3} {y}: games {g} full {fg} batters {nh} "
                f"pitchers {npit} ({dt:.0f} s)")
    return out


# ---------------------------------------------------------------------------
# lines, population norms, the k_resid slope
# ---------------------------------------------------------------------------

def _derived(c: dict, side: str) -> dict:
    out = dict(c)
    if side == "hit":
        out["contact"] = c["swings"] - c["whiffs"]
        out["two_contact"] = c["two_swings"] - c["two_whiffs"]
    else:
        out["csw"] = c["called"] + c["whiffs"]
    return out


@lru_cache(maxsize=None)
def pool_lines(sport: int, season: int, side: str) -> dict:
    """{id: counts dict} of one complete pool and side ({} for any other pool)."""
    if (int(sport), int(season)) not in set(_complete()):
        return {}
    d = aggregate_pool(int(sport), int(season))
    cols = d[f"{side}_cols"]
    return {int(k): _derived(dict(zip(cols, v)), side) for k, v in d[side].items()}


@lru_cache(maxsize=1)
def _complete() -> tuple:
    return tuple(complete_pools())


def rate_of(c: dict, col: str) -> float | None:
    _side, num, den = RATES[col]
    d = c.get(den) or 0
    return (float(c.get(num) or 0) / float(d)) if d > 0 else None


def _mean_sd(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / n
    return m, math.sqrt(v)


@lru_cache(maxsize=None)
def pool_norm(sport: int, season: int, side: str) -> dict | None:
    """The pool's mean and sd per rate over lines with at least NORM_MIN exposure, and
    the k_resid slope; None when the pool has fewer than NORM_MIN_LINES such lines."""
    lines = pool_lines(int(sport), int(season), side)
    exp = EXPOSURE[side]
    q = [c for c in lines.values() if (c.get(exp) or 0) >= NORM_MIN[side]]
    if len(q) < NORM_MIN_LINES:
        return None
    out: dict = {"n_lines": len(q), "rates": {}}
    for col, (s, _n, _d) in RATES.items():
        if s != side:
            continue
        xs = [r for r in (rate_of(c, col) for c in q) if r is not None]
        if len(xs) < NORM_MIN_LINES:
            continue
        m, sd = _mean_sd(xs)
        if sd > 0:
            out["rates"][col] = {"mean": m, "sd": sd, "n": len(xs)}
    for rcol, (kcol, wcol) in RESID.items():
        if RATES[kcol][0] != side:
            continue
        nk, nw = out["rates"].get(kcol), out["rates"].get(wcol)
        if not nk or not nw:
            continue
        pts = []
        for c in q:
            rk, rw = rate_of(c, kcol), rate_of(c, wcol)
            if rk is None or rw is None:
                continue
            pts.append(((rw - nw["mean"]) / nw["sd"], (rk - nk["mean"]) / nk["sd"]))
        if len(pts) < NORM_MIN_LINES:
            continue
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        sxx = sum((p[0] - mx) ** 2 for p in pts)
        b = (sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx) if sxx > 0 else 0.0
        out["rates"][rcol] = {"slope": b, "n": len(pts)}
    return out


def line_z(c: dict, sport: int, season: int, side: str) -> dict:
    """{column: z} of one player line against its own pool (absent where undefined)."""
    nm = pool_norm(int(sport), int(season), side)
    out: dict = {}
    if nm is None:
        return out
    zs: dict = {}
    for col, (s, _n, _d) in RATES.items():
        if s != side or col not in nm["rates"]:
            continue
        r = rate_of(c, col)
        if r is None:
            continue
        zs[col] = (r - nm["rates"][col]["mean"]) / nm["rates"][col]["sd"]
    for col in COLUMNS[side]:
        if col in RESID:
            kcol, wcol = RESID[col]
            if col in nm["rates"] and kcol in zs and wcol in zs:
                out[col] = zs[kcol] - nm["rates"][col]["slope"] * zs[wcol]
        elif col in zs:
            out[col] = zs[col]
    return out


# ---------------------------------------------------------------------------
# the as-of column
# ---------------------------------------------------------------------------

def last_readable_season(read_year: int, cutoff: str | None) -> int:
    """efv_dataset._milb_features' as-of rule (efv_w2_milb.last_readable_season,
    identical): read_year - 1, lowered when the cutoff falls before 1 October of a
    season (that season had not ended)."""
    first = int(read_year) - 1
    if cutoff:
        try:
            cy, cm = int(str(cutoff)[:4]), int(str(cutoff)[5:7])
            first = min(first, cy if cm >= 10 else cy - 1)
        except (ValueError, IndexError):
            pass
    return first


def read_seasons(read_year: int, cutoff: str | None) -> list[int]:
    """The last POOL_SEASONS played seasons ending before the read (2020 skipped)."""
    out, y = [], last_readable_season(read_year, cutoff)
    while len(out) < POOL_SEASONS and y >= min(AGG_SEASONS):
        if y not in NO_SEASON:
            out.append(y)
        y -= 1
    return out


def profile(mlbam, read_year: int, cutoff: str | None, side: str) -> dict:
    """{column: value | None} for one id read at `read_year` as of `cutoff`, plus
    "_exposure" (PA or BF in full games read) and "_seasons". Only the seasons
    read_seasons names are touched."""
    cols = COLUMNS[side]
    out: dict = {c: None for c in cols}
    out["_exposure"] = 0.0
    out["_seasons"] = []
    if not mlbam:
        return out
    pid = int(mlbam)
    exp = EXPOSURE[side]
    acc = {c: [0.0, 0.0] for c in cols}
    for season in read_seasons(read_year, cutoff):
        if season > max(AGG_SEASONS):
            continue
        for sp in SPORT_LEVEL:
            c = pool_lines(sp, season, side).get(pid)
            if not c:
                continue
            d = float(c.get(exp) or 0)
            if d <= 0:
                continue
            z = line_z(c, sp, season, side)
            if not z:
                continue
            out["_exposure"] += d
            if season not in out["_seasons"]:
                out["_seasons"].append(season)
            for col, v in z.items():
                acc[col][0] += v * d
                acc[col][1] += d
    for col in cols:
        num, den = acc[col]
        if den > 0:
            out[col] = (num / den) * (den / (den + SHRINK_K[col]))
    return out


def lv_values(side: str, frames: dict, *, gate_sha: str | None = None) -> dict:
    """{(V, player_key): profile} on the list-vintage frame rows of the side, each read
    on its outcome-blind id at its own window start. A reserved vintage raises unless
    the committed gate sha is handed in (spent_read only)."""
    out = {}
    for V in sorted((frames.get(side) or {})):
        F.guard_score_request(int(V), gate_sha=gate_sha, purpose="w2 pbp column")
        for r in frames[side][V][0]:
            out[(int(V), r["player_key"])] = profile(
                r.get("mlbam_id"), int(V), (r.get("window") or [None])[0], side)
    return out


_LV_MEMO: dict = {}


def screen_column(stat: str, side: str, frames: dict) -> dict:
    """The screening lab's builder hook (column source "module", arg = column):
    {(V, player_key): value | None} on the side's list-vintage frame rows."""
    if stat not in COLUMNS.get(side, ()):
        raise ValueError(f"{stat} is not a {side} pitch-event column")
    key = (side, id(frames))
    if key not in _LV_MEMO:
        _LV_MEMO.clear()
        _LV_MEMO[key] = lv_values(side, frames)
    return {slot: p.get(stat) for slot, p in _LV_MEMO[key].items()}


def vm_values(side: str, data: list[dict], raw_by_key: dict, *,
              allow_reserved: bool = False) -> dict:
    """{player_key: profile} on the vintage-matched matrix rows, read on the matrix id
    at the row's decision year as of its matrix cutoff. A 2025 or later decision year is
    skipped unless allow_reserved (spent_read, after the gate sha opened the cohort)."""
    out = {}
    for d in data:
        y = int(d["decision_year"])
        if y >= F.R_VM_FIRST_DEBUT_YEAR and not allow_reserved:
            continue
        raw = raw_by_key.get(d["player_key"]) or {}
        out[d["player_key"]] = profile(raw.get("mlbam_id"), y, raw.get("cutoff"), side)
    return out


def has_all(p: dict, side: str) -> bool:
    return all(p.get(c) is not None for c in COLUMNS[side])


def coverage(values: dict, side: str) -> dict:
    """{str(year): {"rows", "with_value", "with_all"}} of {(year, key): profile}."""
    out: dict = {}
    for (y, _k), p in values.items():
        c = out.setdefault(str(y), {"rows": 0, "with_value": 0, "with_all": 0})
        c["rows"] += 1
        c["with_value"] += int(any(p.get(x) is not None for x in COLUMNS[side]))
        c["with_all"] += int(has_all(p, side))
    return dict(sorted(out.items()))


def norms_receipt() -> dict:
    """Per side and pool: lines, qualifying lines, the k_resid slope (no player value)."""
    out: dict = {}
    for side in ("hit", "pit"):
        rows = []
        for sp, y in _complete():
            nm = pool_norm(sp, y, side)
            agg = aggregate_pool(sp, y)
            rows.append({"level": SPORT_LEVEL[sp], "season": y, "games": agg["games"],
                         "games_full": agg["games_full"],
                         "lines": len(pool_lines(sp, y, side)),
                         "qualifying_lines": nm["n_lines"] if nm else 0,
                         "k_resid_slope": (round(nm["rates"][f"k_resid_{side[0]}"]["slope"], 4)
                                           if nm and f"k_resid_{side[0]}" in nm["rates"]
                                           else None),
                         "means": ({c: round(v["mean"], 4) for c, v in nm["rates"].items()
                                    if "mean" in v} if nm else None)})
        out[side] = rows
    return out


def construction() -> dict:
    return {"columns": {s: list(c) for s, c in COLUMNS.items()},
            "rates": {c: {"side": s, "num": n, "den": d} for c, (s, n, d) in RATES.items()},
            "k_resid": {c: f"z({k}) - b x z({w}), b the pool's least-squares slope"
                        for c, (k, w) in RESID.items()},
            "codes": {"whiff": sorted(WHIFF), "contact": sorted(CONTACT),
                      "called": sorted(CALLED), "ball": sorted(BALL),
                      "not_counted": sorted(NOT_COUNTED),
                      "first_strike": sorted(FIRST_STRIKE)},
            "pa_events": sorted(PA_EVENTS), "k_events": sorted(K_EVENTS),
            "full_game_ppa": FULL_GAME_PPA, "norm_min": NORM_MIN,
            "norm_min_lines": NORM_MIN_LINES, "pool_seasons": POOL_SEASONS,
            "shrink_k": SHRINK_K, "shrink_k_nearest_mlb_rate": SHRINK_K_NEAREST,
            "z": ("inside each (level, season) pool: unweighted mean and sd over lines "
                  "with at least norm_min exposure; every player at the pool, never a "
                  "frame row"),
            "as_of": ("the last two played seasons ending before the read "
                      "(efv_dataset._milb_features rule; 2020 skipped)"),
            "id": ("list vintage: the outcome-blind mlbam_id (efv_identity), never "
                   "record_mlbam_id; matrix row: the matrix id, as base V2 reads it"),
            "missing": ("no line in a complete pool: None (imputed at the fold's training "
                        "mean on a full frame); pbp_absent is a DS-03 balance probe only")}


def source_receipt() -> dict:
    pools = _complete()
    return {"dir": ".cache/efv4_pbp (read only)", "aggregate_dir": ".cache/efv4_pbp_discipline",
            "census": "data/_labs/efv_w2/pbp_census.json", "census_sha256": _sha(CENSUS_PATH),
            "pools": [[SPORT_LEVEL[sp], y] for sp, y in pools], "n_pools": len(pools)}


# ---------------------------------------------------------------------------
# the restricted frame (has-full-pbp rows per fold)
# ---------------------------------------------------------------------------

def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


def restricted_frame(full, keep: dict):
    """A screening-lab Frame holding only the slots of `keep` ({side: {(V, key)}}):
    training rows, test rows and scored rows of every fold. A fold's training rows
    still exclude EVERY player of the full fold frame (GATE s4.5), not only the kept
    ones, and the base is the V2 assembly refit on the kept training rows."""
    _tools()
    import efv_screen_lab as LAB

    class _Sub(LAB.Frame):
        def fold_train(self, side, V):
            k = (side, int(V))
            if k not in self._fold_train:
                in_frame = {r["player_key"] for r in full.tests[k]}
                self._fold_train[k] = [r for r in self.train[side]
                                       if int(r["decision_year"]) < int(V)
                                       and r["player_key"] not in in_frame]
            return self._fold_train[k]

    def kept(side, r_key):
        return r_key in keep.get(side, ())
    train = {s: [r for r in full.train[s] if kept(s, (int(r["decision_year"]), r["player_key"]))]
             for s in full.train}
    tests = {(s, V): [r for r in rows if kept(s, (int(V), r["player_key"]))]
             for (s, V), rows in full.tests.items()}
    scored = {(s, V): [c for c in rows if kept(s, (int(V), c["key"]))]
              for (s, V), rows in full.scored.items()}
    counts = {}
    for s in full.train:
        counts[s] = {"train_rows": len(train[s]), "train_rows_full": len(full.train[s])}
        for V in full.folds:
            counts[s][str(V)] = {"test_rows": len(tests[(s, V)]),
                                 "test_rows_full": len(full.tests[(s, V)]),
                                 "scored": len(scored[(s, V)]),
                                 "scored_full": len(full.scored[(s, V)])}
    return _Sub(train, tests, scored, weights=full.weights, folds=full.folds,
                absent_ok=full.absent_ok, label=full.label, counts=counts,
                w_star=full.w_star)


def _subset_delta(LAB, frame, side: str, order: dict, keep: set, *, B: int) -> dict:
    """Candidate vs base and vs consensus on the scored rows of `keep` only (the full
    frame's fits, scored on the has-pbp rows)."""
    keys, groups, y, pos, a, b, cons, gr = [], [], [], [], [], [], [], []
    for V in frame.folds:
        bo = frame.base(side, V)["order"]
        for c in frame.scored[(side, V)]:
            if (V, c["key"]) not in keep:
                continue
            ca, cb = order.get((V, c["key"])), bo.get(c["key"])
            if ca is None or cb is None:
                continue
            keys.append(c["key"])
            groups.append(c["group"])
            y.append(c["w3"])
            pos.append(bool(c["contributor"]))
            a.append(float(ca))
            b.append(float(cb))
            cons.append(c["cons"])
            gr.append(c["grades"])
    cols = (keys, groups, y, pos, a, b, cons, gr)
    cc = (keys, groups, y, pos, a, list(cons), cons, gr)
    bc = (keys, groups, y, pos, b, list(cons), cons, gr)
    return {"n": len(keys),
            "candidate_vs_efv_v2_base": LAB._delta(cols, "within", B=B, seed=LAB.SEED),
            "candidate_vs_prospx_consensus": LAB._delta(cc, "within", B=B, seed=LAB.SEED),
            "efv_v2_base_vs_prospx_consensus": LAB._delta(bc, "within", B=B, seed=LAB.SEED)}


# ---------------------------------------------------------------------------
# the development reads
# ---------------------------------------------------------------------------

def _cand(arm: dict) -> dict:
    out = {k: arm[k] for k in ("name", "side", "head", "kind", "retest", "column")}
    out["what"] = f"{arm['stat']}: MiLB pitch-event rate, population z, shrunk ({MODULE})"
    return out


def _tag(arm: dict) -> str:
    return f"SCREEN-W{WAVE}:{arm['side']}.{arm['head']}.{arm['name']}"


def _base_vs_cons(LAB, frame, *, B: int) -> dict:
    out = {}
    for s in F.SIDES:
        order = {}
        for V in frame.folds:
            for pk, idx in frame.base(s, V)["order"].items():
                order[(V, pk)] = idx
        out[s] = LAB._vs_consensus(frame, (s,), order, B=B)
    return out


def lv_read(arms, *, B: int, n_perm: int = N_PERM, log=print) -> dict:
    """lv_dev: the pbp_absent probes, the primary family on the has-full-pbp frame
    (floors, arms with twin and permutation null, Holm, verdicts) and the full-frame
    secondary read."""
    _tools()
    import efv_screen_lab as LAB
    t0 = time.time()
    full, frames = LAB.real_frame()
    log(f"lv_dev frame built in {time.time() - t0:.0f} s")
    vals = {s: lv_values(s, frames) for s in F.SIDES}
    keep = {s: {k for k, p in vals[s].items() if has_all(p, s)} for s in F.SIDES}
    out = {"frame": {"id": "lv_dev", "folds": list(full.folds), "counts": full.counts,
                     "w_star_dev": full.w_star, "label": full.label},
           "coverage": {s: coverage(vals[s], s) for s in F.SIDES},
           "pbp_absent_probe": {}}
    for s in F.SIDES:
        ind = {slot: (0.0 if slot in keep[s] else 1.0) for slot in full.slots(s)}
        out["pbp_absent_probe"][s] = LAB.balance_probe(full, s, ind,
                                                       seed=LAB._seed_for(f"pbp_absent:{s}"))
        pr = out["pbp_absent_probe"][s]
        log(f"  pbp_absent {s}: {pr.get('verdict')} {pr.get('partial')} {pr.get('ci95')}")
    # --- primary: the has-full-pbp frame -------------------------------------------
    sub = restricted_frame(full, keep)
    t1 = time.time()
    floors = LAB.derive_floors(sub, B=B, sides=F.SIDES, heads=("skill",), n_noise=N_NOISE,
                               mode=FLOOR_MODE)
    log("  floors (has-pbp frame): "
        + ", ".join(f"{s} {floors['skill'][s]['within']}" for s in F.SIDES)
        + f" ({time.time() - t1:.0f} s)")
    bvc_sub = _base_vs_cons(LAB, sub, B=B)
    arms_out = []
    for arm in arms:
        t1 = time.time()
        v = {k: p.get(arm["stat"]) for k, p in vals[arm["side"]].items()
             if k in keep[arm["side"]]}
        a = LAB.measure_arm(sub, _cand(arm), v, floors, B=B, n_perm=n_perm,
                            base_vs_cons=bvc_sub)
        a.pop("_order", None)
        a["tag"] = _tag(arm)
        a["model_id"] = f"{MODEL_PREFIX}{arm['name']}:{arm['side']}"
        a["stat"] = arm["stat"]
        a["frame"]["frame_version"] = "lv1_v2 has-full-pbp"
        arms_out.append(a)
        w = a["within"]
        log(f"  lv primary {arm['name']}: admitted {a['admitted_folds']}/{a['n_folds']}, "
            f"vs V2 {w.get('delta')} {w.get('ci95')} p {a['permutation_null'].get('p')} "
            f"({time.time() - t1:.0f} s)")
    holm = LAB.apply_verdicts(arms_out, m=len(arms), exploratory=False)
    for a in arms_out:
        a["screening"]["wave"] = WAVE
        a["screening"]["frame_restriction"] = "has-full-pbp rows"
        a["frame"]["note"] = NOTE_PRIMARY
    out["primary"] = {
        "restriction": {
            "rule": ("each side's arms are read on its has-full-pbp slots only: every "
                     "column of the side has a value; training, test and scored rows of "
                     "every fold restricted; the V2 assembly refit on the kept training "
                     "rows is the base; every frame player of the fold is still "
                     "excluded from its training rows"),
            "why": ("pbp_absent proxies level (A ball had no pitch events before 2016) "
                    "and never enters a skill head; the restriction removes it from the "
                    "comparison instead of imputing over it"),
            "counts": sub.counts},
        "floors": floors, "base_vs_consensus": bvc_sub,
        "holm": holm, "arms": {a["name"]: a for a in arms_out}}
    # --- secondary: the full frame ---------------------------------------------------
    bvc = _base_vs_cons(LAB, full, B=B)
    out["full_frame"] = {"arms": {}}
    for arm in arms:
        t1 = time.time()
        v = {k: p.get(arm["stat"]) if k in keep[arm["side"]] else None
             for k, p in vals[arm["side"]].items()}
        a = LAB.measure_arm(full, _cand(arm), v, {}, B=B, n_perm=0, base_vs_cons=bvc)
        order = a.pop("_order", None) or {}
        a.pop("permutation_null", None)
        a["tag"] = _tag(arm)
        a["model_id"] = f"{MODEL_PREFIX}{arm['name']}:{arm['side']}"
        a["frame"]["note"] = NOTE
        a["has_pbp_rows"] = _subset_delta(LAB, full, arm["side"], order, keep[arm["side"]],
                                          B=B)
        out["full_frame"]["arms"][arm["name"]] = a
        w = a["within"]
        vc = a["frame"]["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
        log(f"  lv full {arm['name']}: admitted {a['admitted_folds']}/{a['n_folds']}, vs V2 "
            f"{w.get('delta')} {w.get('ci95')}, vs consensus {vc.get('delta')} "
            f"{vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out


def vm_orders(side: str, data: list[dict], weights: dict, years, *,
              key: str | None = None, values: dict | None = None) -> tuple[dict, dict]:
    """V2 on the vintage-matched frame exactly as efv_v2_model.v2_vm_scores(timing_pin=
    True) scores it (efv_w2_il_backfill.vm_orders), with one column attached to every
    row and offered to the skill head when `key` is given."""
    import efv_w2_il_backfill as W2I
    return W2I.vm_orders(side, data, weights, years, head="skill" if key else None,
                         key=key, values=values)


def vm_read(arms, *, B: int, log=print) -> dict:
    """vm_dev at vm2: DS-16's rows and base order, then per arm the forward-chained V2
    with the column offered to the skill head; scored on every row and on the has-pbp
    rows. The recomputed base must equal DS-16's on every row."""
    import efv_v2_model as H
    import efv_w2_milb as W2M
    _tools()
    import efv_v2_dev_read as DR
    t0 = time.time()
    weights = H.load_weights()
    rows, meta = DR.v2_vm_dev(DATA_DIR, weights)
    years = meta["fold_years"]
    if any(int(y) >= F.R_VM_FIRST_DEBUT_YEAR for y in years):
        raise F.ReservedFrameError(f"vm years reach R-VM: {years}")
    log(f"vm_dev rows built in {time.time() - t0:.0f} s ({len(rows)} rows)")
    out = {"frame": {"id": "vm_dev", "frame_version": "vm2", "window": meta["window"],
                     "fold_years": years, "dropped": meta["dropped"],
                     "population_rows": meta["population_rows"],
                     "id_join": "matrix mlbam_id, as the base V2 reads it on this frame"},
           "coverage": {}, "parity": {}, "arms": {}}
    key = f"{H.V2_SCREEN_PREFIX}cand"
    for s in F.SIDES:
        data = H.matrix_training_rows(s)
        raw = json.loads(H._matrix_path(s).read_text(encoding="utf-8"))
        raw_by_key = {r["player_key"]: r for r in raw}
        prof = vm_values(s, data, raw_by_key)
        side_rows = [c for c in rows if c["side"] == s]
        base, _f0 = vm_orders(s, data, weights, years)
        mism = sum(1 for c in side_rows
                   if base.get(c["key"]) is None
                   or abs(base[c["key"]] - float(c["grades"][DR.V2_KEY])) > 1e-9)
        out["parity"][s] = {"rows": len(side_rows), "mismatched_base_order": mism}
        if mism:
            raise RuntimeError(f"vm base parity failed on {s}: {mism} rows")
        scored = {c["key"] for c in side_rows}
        dy = {d["player_key"]: int(d["decision_year"]) for d in data
              if int(d["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR}
        keep = {k for k, p in prof.items() if has_all(p, s)}
        out["coverage"][s] = {
            "train_rows": coverage({(dy[k], k): p for k, p in prof.items()}, s),
            "scored_rows": coverage({(dy[k], k): p for k, p in prof.items() if k in scored}, s)}
        for arm in [a for a in arms if a["side"] == s]:
            t1 = time.time()
            vals = {k: (p.get(arm["stat"]) if k in keep else None) for k, p in prof.items()}
            cand, folds = vm_orders(s, data, weights, years, key=key, values=vals)
            blk = W2M._vm_block(side_rows, cand, B=B)
            blk["note"] = NOTE
            sub = W2M._vm_block(side_rows, {k: v for k, v in cand.items() if k in keep}, B=B)
            out["arms"][arm["name"]] = {
                "name": arm["name"], "side": s, "head": "skill", "folds": folds,
                "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
                "n_folds": len(folds), "frame": blk,
                "has_pbp_rows": {"n": sub["n"], "deltas": {
                    k: d["spearman"] for k, d in sub["deltas"].items()}}}
            w = blk["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            vc = blk["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
            log(f"  vm {arm['name']}: admitted "
                f"{out['arms'][arm['name']]['admitted_folds']}/{len(folds)}, vs V2 "
                f"{w.get('delta')} {w.get('ci95')}, vs consensus {vc.get('delta')} "
                f"{vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out


def _git(*args) -> str | None:
    import subprocess
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


def _write(doc: dict, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if chr(0x2014) in text or chr(0x2013) in text:
        raise ValueError("an em or en dash reached the artifact")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)


def dev_read(*, B: int | None = None, n_perm: int = N_PERM, out: Path = OUT_PATH,
             log=print) -> dict:
    """The development reads on lv_dev and vm_dev; writes the artifact (a spent block
    already there is kept)."""
    import efv_labels as L
    import efv_v2_model as H
    import efv_v2_stat as S
    _tools()
    import efv_screen_lab as LAB
    B = S.B_DEFAULT if B is None else int(B)
    LAB.guards()
    t0 = time.time()
    prev = json.loads(Path(out).read_text(encoding="utf-8")) if Path(out).exists() else {}
    doc = {"schema": 1, "item": ITEM,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "produced_by": TOOL, "wave": WAVE, "role": "development",
           "adjudicates": False, "selects": False, "exploratory": False, "note": NOTE,
           "owner_decision": ("EW2-8 to EW2-12 (2026-10-08): new sources only; choose on "
                              "development frames only; the reserved frames are spent"),
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "id": LAB.label_id()},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"), "tool": TOOL,
                    "module_sha256": _sha(Path(__file__)),
                    "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                    "lab_sha256": _sha(ROOT / "tools" / "efv_screen_lab.py")},
           "assembly_sha256": _sha(H.ASSEMBLY_PATH),
           "estimator": {"name": "E_cond", "B": B, "seed": S.SEED_DEFAULT,
                         "clusters": "player", "statistic": S.STAT_LABEL[S.PRIMARY]},
           "family": {"m": len(ARMS), "n_noise_per_head_side": N_NOISE, "n_perm": int(n_perm),
                      "floor_mode": FLOOR_MODE, "alpha": LAB.ALPHA,
                      "admission_rule": LAB.ADMISSION_RULE,
                      "frame": "lv_dev has-full-pbp (primary)"},
           "construction": construction(), "source": source_receipt(),
           "norms": norms_receipt(),
           "arms_declared": [{k: a[k] for k in ("name", "stat", "side", "head")}
                             for a in ARMS],
           "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                      "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                      "lv_folds": list(LAB.FOLDS), "anchor_gate_grouping": False,
                      "aggregate_last_season": max(AGG_SEASONS)}}
    doc["lv_dev"] = lv_read(ARMS, B=B, n_perm=n_perm, log=log)
    doc["vm_dev"] = vm_read(ARMS, B=B, log=log)
    if prev.get("spent"):
        doc["spent"] = prev["spent"]
    doc["summary"] = summary(doc)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    _write(doc, out)
    log(f"wrote {out} in {doc['elapsed_s']} s")
    return doc


# ---------------------------------------------------------------------------
# the spent read: R-LV and R-VM, read once on 2026-10-08 under the owner's waiver
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def registered_v3_columns():
    """This family's arms as efv_v3.W2_COLUMNS entries for the life of the block (the
    v3 machinery's own "add" path), removed afterwards; efv_v3.py is not edited."""
    import efv_v2_model as H
    import efv_v3 as V3
    added = []
    try:
        for a in ARMS:
            if a["name"] in V3.W2_COLUMNS:
                raise RuntimeError(f"{a['name']} already in efv_v3.W2_COLUMNS")
            V3.W2_COLUMNS[a["name"]] = {"side": a["side"], "head": a["head"],
                                        "module": MODULE, "arg": a["stat"],
                                        "key": f"{H.V2_SCREEN_PREFIX}{a['name']}"}
            added.append(a["name"])
        yield V3.W2_COLUMNS
    finally:
        for n in added:
            V3.W2_COLUMNS.pop(n, None)


def spent_values(inp, got: dict, *, gate_sha: str) -> tuple[dict, dict, dict]:
    """({fid: {side: {arm name: {(year, key, kind): value}}}}, coverage, has-pbp keys
    {fid: {side: {(year, key)}}}) on the reserved frames' training and test rows. A
    value off the has-pbp rows is None (imputed by the fit), as on the development
    full frame."""
    import efv_v2_model as H
    cols: dict = {"lv_res": {s: {} for s in F.SIDES}, "vm_pros": {s: {} for s in F.SIDES}}
    cov: dict = {"lv_res": {}, "vm_pros": {}}
    keep: dict = {"lv_res": {}, "vm_pros": {}}
    for s in F.SIDES:
        frames_lv = {V: (rows, None) for V, (rows, _l) in (got["dev"] or {}).get(s, {}).items()}
        for (side, V), rows in got["res"].items():
            if side == s:
                frames_lv[int(V)] = (rows, None)
        reads = lv_values(s, {s: frames_lv}, gate_sha=gate_sha)
        cov["lv_res"][s] = coverage({k: p for k, p in reads.items()
                                     if k[0] in F.RESERVED_LV}, s)
        keep["lv_res"][s] = {k for k, p in reads.items() if has_all(p, s)}
        raw = json.loads(H._matrix_path(s).read_text(encoding="utf-8"))
        vm_r = vm_values(s, H.matrix_training_rows(s), {r["player_key"]: r for r in raw},
                         allow_reserved=True)
        Y = F.R_VM_FIRST_DEBUT_YEAR
        te_keys = {c["key"] for c in inp.frames["vm_pros"]["by_side"][s][Y]["scored"]}
        cov["vm_pros"][s] = coverage({(Y, k): vm_r[k] for k in te_keys if k in vm_r}, s)
        vm_keep = {k for k, p in vm_r.items() if has_all(p, s)}
        keep["vm_pros"][s] = set()
        for a in [x for x in ARMS if x["side"] == s]:
            st = a["stat"]
            lv_v, vm_v = {}, {}
            for V, blk in inp.frames["lv_res"]["by_side"][s].items():
                for kind in ("train", "test"):
                    for r in blk[kind]:
                        y = int(r["decision_year"])
                        k = (y, r["player_key"])
                        lv_v[(y, r["player_key"], kind)] = (
                            (reads.get(k) or {}).get(st) if k in keep["lv_res"][s] else None)
            for _y, blk in inp.frames["vm_pros"]["by_side"][s].items():
                for kind in ("train", "test"):
                    for r in blk[kind]:
                        y = int(r["decision_year"])
                        pk = r["player_key"]
                        vm_v[(y, pk, kind)] = ((vm_r.get(pk) or {}).get(st)
                                               if pk in vm_keep else None)
                        if pk in vm_keep:
                            keep["vm_pros"][s].add((y, pk))
            cols["lv_res"][s][a["name"]] = lv_v
            cols["vm_pros"][s][a["name"]] = vm_v
    return cols, cov, keep


def spent_read(gate_sha: str, *, B: int | None = None, out: Path = OUT_PATH,
               log=print) -> dict:
    """Every arm on R-LV and R-VM against the V2 base and PROSPX consensus (E_cond
    CI95), on every scored row and on the has-pbp scored rows, labelled SPENT_LABEL.
    Written into the artifact's `spent` block only; never a progress-ledger row; nothing
    is chosen on it."""
    import efv_v2_stat as S
    import efv_v3 as V3
    import efv_w2_il_backfill as W2I
    _tools()
    import efv_v3_backtest as BT
    B = S.B_DEFAULT if B is None else int(B)
    if not F.gate_sha_committed(gate_sha):
        raise F.ReservedFrameError(f"{gate_sha!r} is not the committed registration")
    t0 = time.time()
    inp, got = W2I.build_reserved_capturing(gate_sha, log=log)
    parity = BT.assert_v3_base_parity(inp, BT.FRAMES_RES)
    log(f"reserved frames built, V2 base parity {parity} ({time.time() - t0:.0f} s)")
    blk_out = {"label": SPENT_LABEL, "role": "spent", "selects": False,
               "adjudicates": False, "chooses_nothing": True,
               "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "gate": {"doc": F.GATE_DOC, "sha": gate_sha, "guards": inp.guards},
               "label_id": inp.label, "base_parity": parity,
               "estimator": {"name": "E_cond", "B": B, "seed": BT.SEED,
                             "clusters": "player"},
               "frames": {}, "arms": {}}

    def legs_on(rows):
        out = {}
        for name, b_key in (("candidate_vs_efv_v2_base", BT.V2_KEY),
                            ("candidate_vs_prospx_consensus", BT.CONS)):
            out[name] = {("spearman" if st == "within" else st):
                         BT.paired(rows, BT.V3_KEY, b_key, st, B=B)
                         for st in ("within", "pooled", "auc")}
        return out

    with registered_v3_columns():
        cols, cov, keep = spent_values(inp, got, gate_sha=gate_sha)
        inp.cols = cols
        base_rows = {fid: inp.rows_with(fid, inp.orders(fid, V3.base_config())[0])
                     for fid in BT.FRAMES_RES}
        for fid in BT.FRAMES_RES:
            blk_out["frames"][fid] = {
                "n_by_side": BT._n_side(base_rows[fid]), "coverage": cov[fid],
                "efv_v2_base_vs_prospx_consensus": {
                    s: BT.paired([c for c in base_rows[fid] if c["side"] == s],
                                 BT.V2_KEY, BT.CONS, "within", B=B)
                    for s in F.SIDES}}
        for a in ARMS:
            t1 = time.time()
            cfg = V3.base_config()
            cfg["add"][a["side"]][a["head"]].append(a["name"])
            V3.validate_config(cfg)
            key = V3.W2_COLUMNS[a["name"]]["key"]
            arm_out = {"name": a["name"], "side": a["side"], "head": a["head"],
                       "label": SPENT_LABEL, "frames": {}}
            for fid in BT.FRAMES_RES:
                orders, rec = inp.orders(fid, cfg, sides=(a["side"],))
                rows = inp.rows_with(fid, orders, sides=(a["side"],))
                kp = keep[fid][a["side"]]
                sub = [c for c in rows if (int(c["year"]), c["key"]) in kp]
                folds = {f: {"admitted": key in (r.get("skill_keys") or []),
                             "head_keys": r.get("skill_keys"),
                             "consensus_only": r["consensus_only"]}
                         for f, r in rec.items()}
                legs = legs_on(rows)
                arm_out["frames"][fid] = {
                    "n": len(rows), "folds": folds,
                    "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
                    "n_folds": len(folds), "deltas": legs, "label": SPENT_LABEL,
                    "has_pbp_rows": {"n": len(sub), "deltas": {
                        k: v["spearman"] for k, v in legs_on(sub).items()} if sub else None}}
                w = legs["candidate_vs_efv_v2_base"]["spearman"]
                vc = legs["candidate_vs_prospx_consensus"]["spearman"]
                log(f"  {fid} {a['name']}: admitted {arm_out['frames'][fid]['admitted_folds']}"
                    f"/{len(folds)}, vs V2 {w.get('delta')} {w.get('ci95')}, vs consensus "
                    f"{vc.get('delta')} {vc.get('ci95')} ({time.time() - t1:.0f} s)")
            blk_out["arms"][a["name"]] = arm_out
    blk_out["elapsed_s"] = round(time.time() - t0, 1)
    doc = json.loads(Path(out).read_text(encoding="utf-8")) if Path(out).exists() else {}
    doc["spent"] = blk_out
    doc["summary"] = summary(doc)
    _write(doc, out)
    log(f"wrote the spent block into {out} in {blk_out['elapsed_s']} s")
    return doc


# ---------------------------------------------------------------------------
# summary and the progress ledger (development rows only)
# ---------------------------------------------------------------------------

def _pair(leg: dict | None) -> list:
    leg = leg or {}
    return [leg.get("delta"), leg.get("ci95")]


def summary(doc: dict) -> list[dict]:
    """One line per arm: per frame rows, admitted folds, within delta vs V2 and vs
    consensus with CI95 (spent frames carry SPENT_LABEL). Copies only."""
    out = []
    for arm in doc.get("arms_declared") or [{k: a[k] for k in ("name", "stat", "side", "head")}
                                            for a in ARMS]:
        n = arm["name"]
        row = {"arm": n, "side": arm["side"], "head": arm["head"], "stat": arm["stat"]}
        lv = doc.get("lv_dev") or {}
        p = ((lv.get("primary") or {}).get("arms") or {}).get(n)
        if p:
            d = p["frame"]["deltas"]
            row["lv_dev_has_pbp"] = {
                "n": p["frame"]["n"], "verdict": p.get("verdict"),
                "admitted_folds": f"{p['admitted_folds']}/{p['n_folds']}",
                "vs_v2_refit": _pair(d["candidate_vs_efv_v2_base"]["spearman"]),
                "vs_consensus": _pair(d["candidate_vs_prospx_consensus"]["spearman"]),
                "floor": p["within"].get("floor"), "p_perm": p["within"].get("p_perm"),
                "holm_p": p["within"].get("holm_p")}
        a = ((lv.get("full_frame") or {}).get("arms") or {}).get(n)
        if a:
            d = a["frame"]["deltas"]
            row["lv_dev"] = {"n": a["frame"]["n"],
                             "admitted_folds": f"{a['admitted_folds']}/{a['n_folds']}",
                             "vs_v2": _pair(d["candidate_vs_efv_v2_base"]["spearman"]),
                             "vs_consensus": _pair(d["candidate_vs_prospx_consensus"]["spearman"]),
                             "has_pbp_rows_vs_v2": _pair(
                                 a["has_pbp_rows"]["candidate_vs_efv_v2_base"])}
        a = (((doc.get("vm_dev") or {}).get("arms")) or {}).get(n)
        if a:
            d = a["frame"]["deltas"]
            row["vm_dev"] = {"n": a["frame"]["n"],
                             "admitted_folds": f"{a['admitted_folds']}/{a['n_folds']}",
                             "vs_v2": _pair(d["candidate_vs_efv_v2_base"]["spearman"]),
                             "vs_consensus": _pair(d["candidate_vs_prospx_consensus"]["spearman"]),
                             "has_pbp_rows_vs_v2": _pair(
                                 a["has_pbp_rows"]["deltas"].get("candidate_vs_efv_v2_base"))}
        sp = (((doc.get("spent") or {}).get("arms") or {}).get(n) or {}).get("frames") or {}
        for fid, f in sp.items():
            v2 = f["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            vc = f["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
            hp = (f.get("has_pbp_rows") or {}).get("deltas") or {}
            row[fid] = {"n": f["n"], "label": SPENT_LABEL,
                        "admitted_folds": f"{f['admitted_folds']}/{f['n_folds']}",
                        "vs_v2": _pair(v2), "vs_consensus": _pair(vc),
                        "has_pbp_rows_vs_v2": _pair(hp.get("candidate_vs_efv_v2_base"))}
        out.append(row)
    return out


def ledger_docs(doc: dict) -> list[dict]:
    """One development document per (arm, development frame) in the shape
    efv_progress.build_dev_rows reads: on lv_dev the FAMILY's block (the has-full-pbp
    rows, with its floor, Holm p and verdict; the restriction named in the frame note
    and the screening block), on vm_dev the vm2 block. The lv_dev full-frame read and
    the spent block never become a row."""
    out = []
    for arm in doc.get("arms_declared") or []:
        prim = ((doc.get("lv_dev") or {}).get("primary") or {}).get("arms") or {}
        vm = (doc.get("vm_dev") or {}).get("arms") or {}
        for fid, a in (("lv_dev", prim.get(arm["name"])), ("vm_dev", vm.get(arm["name"]))):
            if not a:
                continue
            scr = {"wave": f"{WAVE} ({fid})", "exploratory": False,
                   "development_only": True, "adjudicates": False, "selects": False,
                   "head": arm["head"], "statistic_column": arm["stat"],
                   "admitted_folds": a["admitted_folds"], "n_folds": a["n_folds"]}
            if fid == "lv_dev":
                scr.update({"frame_restriction": "has-full-pbp rows",
                            "twin_inside_floor": (a.get("twin") or {}).get("inside_floor")})
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--aggregate", action="store_true", help="fill the per-pool counts")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--norms", action="store_true", help="print the pool receipt")
    ap.add_argument("--dev-read", action="store_true", help="the development reads")
    ap.add_argument("--n-perm", type=int, default=N_PERM)
    ap.add_argument("--spent-read", action="store_true", help="the spent-frame read")
    ap.add_argument("--gate-sha", default="", help="the committed gate sha (spent read)")
    ap.add_argument("--ledger", action="store_true",
                    help="append this module's development rows from the artifact")
    ap.add_argument("--ledger-path", default=None,
                    help="durable ledger path (default: efv_progress's own)")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args()
    if a.aggregate:
        t0 = time.time()
        res = aggregate(workers=a.workers)
        print(f"{res['pools']} pools in {time.time() - t0:.1f} s")
    if a.norms:
        print(json.dumps(norms_receipt(), indent=1))
    if a.dev_read:
        print(json.dumps(dev_read(B=a.B, n_perm=a.n_perm, out=Path(a.out))["summary"],
                         indent=1))
    if a.spent_read:
        if not a.gate_sha:
            ap.error("--spent-read needs --gate-sha")
        print(json.dumps(spent_read(a.gate_sha, B=a.B, out=Path(a.out))["summary"], indent=1))
    if a.ledger:
        print(json.dumps(update_ledger(path=Path(a.out), ledger_path=a.ledger_path),
                         indent=1))
