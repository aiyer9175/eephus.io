# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The aging v3 lab: ``dev``, ``mde``, ``look`` and ``health`` for
docs/AGING_V3_GATE.md (the gate governs every constant here; PLAN section 9.3
'Aging v3 (the one aging service)'; LANE_B.md sections 2 and 3).

    python tools/aging_v3_lab.py dev                 DEV selection (gate section 8), DEV rows only
    python tools/aging_v3_lab.py mde                 the power artifact (gate section 8), DEV rows only
    python tools/aging_v3_lab.py look --fixture      the whole look's reporting path on fixtures
    python tools/aging_v3_lab.py health --fixture    the health family's path on fixtures
    python tools/aging_v3_lab.py look --out DIR --i-am-the-look     THE LOOK (AG_7, once)
    python tools/aging_v3_lab.py health --out DIR --i-am-the-look   THE HEALTH LOOK (AG_13, once)

``dev`` and ``mde`` write ``data/aging_v3_mde.json`` (the DEV-only artifact);
both run under a FrameGuard that RAISES (``EarlyLookError``) if a label season
outside DEV reaches a scorer, so a GATE, TIER-2 or CONFIRM number cannot be
computed by them. ``look`` and ``health`` on the real corpus are the registered
looks: they refuse to run without ``--i-am-the-look`` and an ``--out`` directory,
check the calendar, tee stdout and stderr to that directory before anything
else runs, and never re-select a grid (the selections are read from the DEV
artifact). On ``--fixture`` every subcommand runs on synthetic corpora that
carry nulls (a player with no age, a bucket with no rows, a base with no
CONFIRM cells, an empty archetype) and writes under ``--out`` only.

The estimand (gate section 3): ``fa_market.contract_war_path(use_ml=False)``
with point-in-time ``fa_projection.fitted_models(corpus, B-1, use_cache=False)``
and the aging v3 service attached call-scoped under one configuration; cell
(B, h) scores label season L = B + h - 1 against the frozen fWAR label through
``fa_projection.war_actual_map`` (absent season = 0). The comparator (section
4) is the no-arm service with the PT cap computed call-scoped (``pt_cap``
True). Frames (section 6): the proj_eval universe per base, two-sided rows
excluded (path-shape L1: a row whose label player-season or whose history
player-seasons carry both a hit and a pit row), R-VM rows dropped
(efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR), label season 2020 masked.

Bans enforced here (section 15): no path-shape cache is read or written,
``.cache/fa_corpus.pkl`` is read only, every fit passes ``use_cache=False``,
no list vintage, FV, grade or prospect row is read, and the archetype window
never contains its start season (``check_out_of_window``).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import pickle
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aging_v3 as A                     # noqa: E402
import efv_vintage_frame as EVF          # noqa: E402
import fa_market as fm                   # noqa: E402
import fa_projection as fp               # noqa: E402
import value_framework as vf             # noqa: E402

# ---------------------------------------------------------------------------
# Registered constants (docs/AGING_V3_GATE.md; a change here is a test failure)
# ---------------------------------------------------------------------------

GATE_DOC = ROOT / "docs" / "AGING_V3_GATE.md"
MDE_PATH = ROOT / "data" / "aging_v3_mde.json"
EVAL_PATH = ROOT / "data" / "aging_v3_eval.json"
# sha256 of the gate document's bytes from the line beginning '## G-0.' up to
# (not including) the line beginning '## 18.', line endings normalized to LF
# (gate section 17); test_aging_v3_gate.py recomputes it.
PROTOCOL_HASH = "d42c0c37a4438b933d17ef4853ca5064253368550b3635614dd2e8c716300986"
PROTOCOL_START = "## G-0."
PROTOCOL_END = "## 18."

SEED = 20261124
B_BOOT = 2000
ALPHA = 0.0125                      # Bonferroni over the four ladder arms
HORIZONS = 5
MASKED_LABEL = 2020
FRAMES = {
    "DEV": (2008, 2009, 2010),
    "GATE": (2011, 2012, 2013),
    "TIER2": tuple(s for s in range(2014, 2026) if s != MASKED_LABEL),
    "CONFIRM": (2026,),
}
CONFIRM_MIN_N = 1000
ARMS = ("T", "S", "P", "R")
# age at target: 24 and under, 25-27, 28-30, 31-33, 34 and over
BANDS = (("24-", -1, 24), ("25-27", 25, 27), ("28-30", 28, 30), ("31-33", 31, 33), ("34+", 34, 999))
PLANTED_BANDS = ("24-", "31-33", "34+")       # the 24-and-under and 31-and-over cells
PLANT_WAR = 0.05
N_PLANTS = 200
UNDERPOWERED_MDE = 0.03
TIE = 0.002
POWER = 0.95
GRID_LAMBDA = (0.0, 0.5, 1.0)
GRID_SMOOTHER = (("ma3", 4), ("pen", 1), ("pen", 4), ("pen", 16))
GRID_KP = (50, 100, 200, 400)
GRID_KR = (100, 200, 400, 800)
INCUMBENT = {"lambda": 1.0, "smoother": "ma3", "penalty": 4}
G1_MAE = 0.003
G2_STAR = 0.05
G3_TAIL = 0.02
G4_BUCKET = 0.02
G4_MIN_N = 200
STAR_WAR = 4.0
TAIL_WAR = 3.0
# PS, the prospect shape gate (section 9)
PS_COHORTS = (2014, 2015, 2016, 2017, 2018)
NEVER_READ_COHORTS = (2020, 2021, 2025, 2026)
PS_MIN_SEASONS = 2
PS_MIN_PA = 150.0
PS_MIN_IP = 30.0
PS_WINDOW = 6                        # seasons d to d+6
PS_GUARD = 0.10
PS_MIN_N = 40
PS_BANDS = (("21-", -1, 21), ("22-23", 22, 23), ("24-25", 24, 25), ("26+", 26, 999))
PS_FIRST_DEBUT = 2001
# H, the health family (section 10)
H_FRAMES = {"DEV": (2011, 2012, 2013, 2014), "GATE": (2015, 2016, 2017, 2018), "CONFIRM": (2026,)}
H_HORIZONS = 3
H_FIRST_BASE = 2011
H_WAR_MAE = 0.003
H_DRIFT = 0.01
H_ALPHA = 0.05
IP_TO_BF = 4.3
# the registered floor list of other gates' look days (gate section 13)
FLOOR_LOOK_DAYS = (
    "2026-10-20", "2026-10-21", "2026-10-23", "2026-10-28", "2026-10-31", "2026-11-02",
    "2026-11-06", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-20",
    "2026-11-25", "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-08", "2026-12-10",
    "2027-02-15",
)
# The owner's waiver of every registered look day and date (DECISIONS_FOR_OWNER.md
# EW3-5, 2026-10-14). Carried only as the explicit switch --owner-waived-early-read,
# never by default: the artifact then names the read an owner-waived early read.
OWNER_WAIVER = ("EW3-5 (owner 2026-10-14): registered look days and dates waived; a look "
                "before its day is recorded as an owner-waived early read")


class EarlyLookError(RuntimeError):
    """A label season outside the frame a scorer was handed reached it."""


class FrameGuard:
    """The hard guard: every row a scorer sees must carry a label season in
    ``allowed``; anything else RAISES. ``dev`` and ``mde`` are built with the
    DEV guard, so a GATE, TIER-2 or CONFIRM number cannot be computed by them."""

    def __init__(self, name: str, allowed) -> None:
        self.name = name
        self.allowed = frozenset(int(s) for s in allowed)

    def check(self, label_season: int) -> None:
        if int(label_season) not in self.allowed:
            raise EarlyLookError(f"label season {label_season} reached the {self.name} scorer "
                                 f"(allowed {sorted(self.allowed)}): an early look is void")

    def check_rows(self, rows) -> None:
        for r in rows:
            self.check(r["L"])


DEV_GUARD = FrameGuard("DEV", FRAMES["DEV"])


def protocol_hash(doc: Path = GATE_DOC) -> str:
    """The gate's frozen sections hashed as section 17 states."""
    raw = doc.read_bytes().replace(b"\r\n", b"\n")
    lines = raw.split(b"\n")
    s = next(i for i, l in enumerate(lines) if l.startswith(PROTOCOL_START.encode()))
    e = next(i for i, l in enumerate(lines) if l.startswith(PROTOCOL_END.encode()))
    return hashlib.sha256(b"\n".join(lines[s:e]) + b"\n").hexdigest()


def assert_protocol(doc: Path = GATE_DOC) -> None:
    h = protocol_hash(doc)
    if h != PROTOCOL_HASH:
        raise RuntimeError(f"gate document protocol hash {h} != lab constant {PROTOCOL_HASH}: "
                           "sections G-0 to 17 were edited after registration")


def check_out_of_window(cfg: dict, start_season: int) -> list[int]:
    """The ARM R window of a pair starting at ``start_season`` must lie
    strictly before it (gate section 15); raises otherwise."""
    window = A.window_seasons(start_season, A.normalize_config(cfg))
    if any(s >= start_season for s in window):
        raise ValueError(f"archetype window {window} contains the start season {start_season}")
    return window


def assert_model_out_of_window(model: A.AgingModel) -> int:
    """Every archetype assignment a fitted model carries was read from a
    window strictly before its start season; raises on the first that was not."""
    n = 0
    for side in A.SIDES:
        for (_, t) in ((model.assign.get(side) or {}).get("archetype") or {}):
            check_out_of_window(model.cfg, int(t))
            n += 1
    return n


def calendar_blockers(today: _dt.date | None = None, docs_root: Path = ROOT / "docs") -> list[str]:
    """The days this lab must not run a look or a lab on (gate section 13; the
    writers' calendar rules U1a and U1c): the registered floor list, and any
    results row another gate document dates today."""
    today = today or _dt.date.today()
    iso = today.isoformat()
    out = []
    if iso in FLOOR_LOOK_DAYS:
        out.append(f"{iso} is a registered look day of another gate (the floor list)")
    pat = re.compile(r"^\|\s*" + re.escape(iso) + r"\s*\|")
    for p in sorted(docs_root.rglob("*GATE*.md")):
        if p.resolve() == GATE_DOC.resolve():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if pat.match(line) and re.search(r"look|verdict|PASS|FAIL|VOID|UNDERPOWERED", line):
                out.append(f"{p.relative_to(ROOT)} carries a look record dated {iso}")
                break
    return out


def next_free_day(today: _dt.date | None = None) -> str:
    d = (today or _dt.date.today()) + _dt.timedelta(days=1)
    while calendar_blockers(d):
        d += _dt.timedelta(days=1)
    return d.isoformat()


# ---------------------------------------------------------------------------
# Configurations
# ---------------------------------------------------------------------------

def comparator_cfg() -> dict:
    """Section 4: the v2 curves with the PT cap computed call-scoped."""
    cfg = A.default_config()
    cfg["pt_cap"] = True
    return A.normalize_config(cfg)


def arm_cfg(arms: dict, lam: float = 1.0, smoother: str = "ma3", penalty: float = 4,
            k_p: float = 200, k_r: float = 400) -> dict:
    cfg = comparator_cfg()
    for a in ARMS:
        cfg["arms"][a] = bool(arms.get(a, False))
    # the grid values as registered (ints stay ints), so the no-arm composition
    # and comparator_cfg() share one cfg8
    cfg["S"] = {"lambda": float(lam), "smoother": smoother, "penalty": penalty}
    cfg["P"]["k"] = k_p
    cfg["R"]["k"] = k_r
    return A.normalize_config(cfg)


def composition_cfg(passed: list[str], sel: dict) -> dict:
    """The configuration of a composition of passed arms at the DEV selections."""
    return arm_cfg({a: (a in passed) for a in ARMS}, sel["lambda"], sel["smoother"],
                   sel["penalty"], sel["k_P"], sel["k_R"])


def smoother_rank(sm: str, pen: float) -> int:
    """Nearer the incumbent first (C5): ma3, then the larger penalty."""
    if sm == "ma3":
        return 0
    return {16: 1, 4: 2, 1: 3}.get(int(pen), 4)


# ---------------------------------------------------------------------------
# Corpus, universe, frames
# ---------------------------------------------------------------------------

def load_real(require_fwar: bool = True) -> tuple[dict, dict]:
    """``.cache/fa_corpus.pkl`` read-only and the sidecar (built if missing,
    never on a look day; its build never rewrites the corpus)."""
    with open(fp.CORPUS_CACHE, "rb") as fh:
        corpus = pickle.load(fh)
    probs = A.check_corpus(corpus)
    if probs and require_fwar:
        raise RuntimeError("; ".join(probs))
    import aging_v3_sidecar
    sidecar = aging_v3_sidecar.load(corpus)
    return corpus, sidecar


def two_sided_seasons(corpus: dict) -> set:
    hs = {(r["mlbam"], r["season"]) for r in corpus["hit"] if r.get("mlbam")}
    ps = {(r["mlbam"], r["season"]) for r in corpus["pit"] if r.get("mlbam")}
    return hs & ps


def first_exposure_season(corpus: dict) -> dict:
    """{mlbam: first corpus season with exposure} (the R-VM and PS debut rule)."""
    first: dict = {}
    for side in A.SIDES:
        ek = A.EXPO_KEY[side]
        for r in corpus[side]:
            if r.get("mlbam") and (r.get(ek) or 0) > 0:
                first[r["mlbam"]] = min(first.get(r["mlbam"], 9999), r["season"])
    return first


def is_rvm(mlbam, first: dict) -> bool:
    return first.get(mlbam, 9999) >= EVF.R_VM_FIRST_DEBUT_YEAR


def band_of(age: float, bands=BANDS) -> str:
    a = int(math.floor(float(age)))
    for name, lo, hi in bands:
        if lo <= a <= hi:
            return name
    return bands[-1][0]


def row_bucket(side: str, mlbam, season: int, role, sidecar: dict) -> str:
    """The G4 / report bucket of a row at season B-1: hitters from the sidecar
    position (two-way hitting side DH; IF, UT, TWP, X and missing pooled),
    pitchers by role."""
    if side == "pit":
        return A.base_role("pit", None, role)
    sc = (sidecar.get("rows") or {}).get((mlbam, season)) or {}
    b = A.bucket_from_position(sc.get("pos"), False, two_way_hitting=bool(sc.get("two_way")))
    return b or "pooled"


class Universe:
    """The corpus indexed for frames: players by side, the label map, the
    two-sided player-seasons, the first exposure season."""

    def __init__(self, corpus: dict, sidecar: dict) -> None:
        self.corpus = corpus
        self.sidecar = sidecar
        self.league = corpus["league"]
        self.by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
        for side in A.SIDES:
            for r in corpus[side]:
                if r.get("mlbam"):
                    self.by_player[side][r["mlbam"]][r["season"]] = r
        self.war_actual = fp.war_actual_map(corpus)
        self.two_sided = two_sided_seasons(corpus)
        self.first = first_exposure_season(corpus)
        self.last = int(corpus.get("last") or max(r["season"] for r in corpus["hit"]))


def frame_bases(label_seasons) -> list[int]:
    lo, hi = min(label_seasons), max(label_seasons)
    return list(range(lo - HORIZONS + 1, hi + 1))


def build_frame(U: Universe, name: str, label_seasons, guard: FrameGuard | None = None,
                bases: list[int] | None = None) -> dict:
    """Rows (side, mlbam, B, h, L, age at target, band, bucket, star, act) of
    the frame whose label seasons are ``label_seasons``; the universe is the
    proj_eval universe per base (a corpus season in B-1..B-3, an age-carrying
    row, a non-None champion path under the comparator), two-sided rows
    excluded, R-VM rows dropped, 2020 masked. Returns the frame dict with its
    rows, its bases and the exclusion census."""
    allowed = frozenset(int(s) for s in label_seasons)
    bases = bases or frame_bases(label_seasons)
    rows = []
    census = {"two_sided_rows": 0, "rvm_rows": 0, "no_age": 0, "masked_2020": 0, "no_path": 0}
    for B in bases:
        if B - 1 < int(U.corpus.get("first") or 2000) + 0:
            continue
        for side in A.SIDES:
            for mlbam, seasons in U.by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                age_row = next((h for h in hist if h.get("age")), None)
                if age_row is None:
                    census["no_age"] += 1
                    continue
                if is_rvm(mlbam, U.first):
                    census["rvm_rows"] += 1
                    continue
                if any((mlbam, h["season"]) in U.two_sided for h in hist):
                    census["two_sided_rows"] += 1
                    continue
                age = age_row["age"] + (B - age_row["season"])
                base_actual = U.war_actual.get((mlbam, B - 1))
                star = base_actual is not None and base_actual >= STAR_WAR
                bucket = row_bucket(side, mlbam, B - 1, hist[0].get("role"), U.sidecar)
                for h in range(1, HORIZONS + 1):
                    L = B + h - 1
                    if L not in allowed:
                        continue
                    if L == MASKED_LABEL:
                        census["masked_2020"] += 1
                        continue
                    if L > U.last:
                        continue
                    if (mlbam, L) in U.two_sided:
                        census["two_sided_rows"] += 1
                        continue
                    if guard is not None:
                        guard.check(L)
                    rows.append({"side": side, "mlbam": mlbam, "B": B, "h": h, "L": L,
                                 "age": age + h - 1, "band": band_of(age + h - 1),
                                 "bucket": bucket, "star": bool(star), "role": hist[0].get("role"),
                                 "act": float(U.war_actual.get((mlbam, L), 0.0)),
                                 "hist": hist, "age_B": age})
    return {"name": name, "label_seasons": sorted(allowed), "bases": bases, "rows": rows,
            "census": census}


# ---------------------------------------------------------------------------
# Predictions under one configuration
# ---------------------------------------------------------------------------

_V2_MEMO: dict = {}


def v2_models(corpus: dict, max_season: int) -> tuple[dict, dict]:
    """``fitted_models(corpus, max_season, use_cache=False)`` memoized in this
    process only (the fit is a pure function of the corpus and the season;
    the P-FITCACHE rule: nothing is read from or written to disk)."""
    key = (id(corpus), int(max_season))
    if key not in _V2_MEMO:
        _V2_MEMO[key] = fp.fitted_models(corpus, int(max_season), use_cache=False, aging="v2")
    return _V2_MEMO[key]


def attached(corpus: dict, sidecar: dict, max_season: int, cfg: dict) -> tuple[dict, dict, A.AgingModel]:
    curves, war_map = v2_models(corpus, max_season)
    c3 = A.attach(curves, corpus, int(max_season), use_cache=False, cfg=cfg, sidecar=sidecar)
    model = A.model_of(c3)
    if model.cfg["arms"]["R"]:
        assert_model_out_of_window(model)
    return c3, war_map, model


def predict(frame: dict, U: Universe, cfg: dict, guard: FrameGuard | None = None,
            with_pt: bool = False) -> np.ndarray:
    """The champion WAR prediction of every frame row under ``cfg``; with
    ``with_pt`` also the year-1 exposure and the role the walk used (for the
    health family). Raises if a configuration returns no path for a row the
    comparator priced, or if a label season outside the guard reaches here."""
    cfg = A.normalize_config(cfg)
    rows = frame["rows"]
    if guard is not None:
        guard.check_rows(rows)
    for r in rows:
        if is_rvm(r["mlbam"], U.first):
            raise EarlyLookError(f"an R-VM row ({r['mlbam']}) reached a scorer")
    preds = np.full(len(rows), np.nan)
    pts = np.full(len(rows), np.nan)
    by_base: dict[int, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_base[r["B"]].append(i)
    for B, idx in sorted(by_base.items()):
        c3, war_map, _ = attached(U.corpus, U.sidecar, B - 1, cfg)
        paths: dict = {}
        for i in idx:
            r = rows[i]
            key = (r["side"], r["mlbam"])
            if key not in paths:
                paths[key] = fm.contract_war_path(r["hist"], r["side"], B, HORIZONS, r["age_B"],
                                                  c3, war_map, U.league, use_ml=False, aging="v3")
            p = paths[key]
            if p is None:
                raise RuntimeError(f"no champion path for {key} at base {B} under cfg8 "
                                   f"{A.config_hash(cfg)} (the comparator priced it)")
            preds[i] = float(p["war_by_year_champ"][r["h"] - 1])
            pts[i] = float(p.get("pt_y1") or 0.0)
    if np.isnan(preds).any():
        raise RuntimeError("a frame row received no prediction")
    return (preds, pts) if with_pt else preds


# ---------------------------------------------------------------------------
# ACAL, MAE, the player-cluster bootstrap, the guards
# ---------------------------------------------------------------------------

def cell_index(frame: dict) -> tuple[np.ndarray, list[str]]:
    names = [f"{side}:{b[0]}" for side in A.SIDES for b in BANDS]
    pos = {n: i for i, n in enumerate(names)}
    return np.array([pos[f"{r['side']}:{r['band']}"] for r in frame["rows"]], dtype=int), names


def player_index(frame: dict) -> tuple[np.ndarray, int]:
    keys = sorted({r["mlbam"] for r in frame["rows"]}, key=str)
    pos = {k: i for i, k in enumerate(keys)}
    return np.array([pos[r["mlbam"]] for r in frame["rows"]], dtype=int), len(keys)


def acal(resid: np.ndarray, cells: np.ndarray, n_cells: int) -> float:
    """sum_c n_c |mean_c(resid)| / sum_c n_c = sum_c |S_c| / N."""
    if resid.size == 0:
        return float("nan")
    s = np.bincount(cells, weights=resid, minlength=n_cells)
    return float(np.abs(s).sum() / resid.size)


def _cluster_sums(frame: dict, cols: dict[str, np.ndarray], cells: np.ndarray, n_cells: int,
                  pidx: np.ndarray, n_players: int) -> dict:
    """Per-player sums: for each named residual column its per-cell sums
    (n_players x n_cells) and its |.| sum, plus the row count per player."""
    out = {"count": np.bincount(pidx, minlength=n_players).astype(float)}
    for name, v in cols.items():
        m = np.zeros((n_players, n_cells))
        np.add.at(m, (pidx, cells), v)
        out[name] = m
        out[name + "_abs"] = np.bincount(pidx, weights=np.abs(v), minlength=n_players)
    return out


def _draws(n_players: int, B: int, seed: int, probs: np.ndarray | None = None) -> np.ndarray:
    """B player-cluster resamples as count vectors (B x n_players): players
    drawn with replacement, n_players at a time, as multinomial counts
    (uniform, or from ``probs`` for a plant's resampled population)."""
    rng = np.random.default_rng(seed)
    p = np.full(n_players, 1.0 / n_players) if probs is None else np.asarray(probs, dtype=float)
    return rng.multinomial(n_players, p, size=B).astype(float)


def bootstrap_pair(frame: dict, pred_a: np.ndarray, pred_b: np.ndarray, *, B: int = B_BOOT,
                   seed: int = SEED, probs: np.ndarray | None = None) -> dict:
    """D = ACAL(a) - ACAL(b) and MAE(b) - MAE(a) with their player-cluster
    bootstrap (players resampled with all their rows). ``a`` is the
    predecessor, ``b`` the arm. One-sided p for D > 0 is
    (1 + #{D* <= 0}) / (B + 1); the reversal p is (1 + #{D* >= 0}) / (B + 1)."""
    act = np.array([r["act"] for r in frame["rows"]])
    cells, names = cell_index(frame)
    pidx, n_players = player_index(frame)
    ea, eb = pred_a - act, pred_b - act
    n_cells = len(names)
    out = {"n_rows": int(len(act)), "n_players": int(n_players), "B": int(B), "seed": int(seed),
           "acal_pred": acal(ea, cells, n_cells), "acal_arm": acal(eb, cells, n_cells),
           "mae_pred": float(np.abs(ea).mean()) if len(act) else None,
           "mae_arm": float(np.abs(eb).mean()) if len(act) else None}
    out["D"] = out["acal_pred"] - out["acal_arm"] if len(act) else None
    out["mae_diff"] = (out["mae_arm"] - out["mae_pred"]) if len(act) else None
    if len(act) == 0 or n_players < 2:
        out.update({"sd": None, "p": None, "p_reversal": None, "mae_diff_hi95": None, "draws": 0})
        return out
    sums = _cluster_sums(frame, {"a": ea, "b": eb}, cells, n_cells, pidx, n_players)
    W = _draws(n_players, B, seed, probs)
    N = W @ sums["count"]
    Sa = np.abs(W @ sums["a"]).sum(axis=1)
    Sb = np.abs(W @ sums["b"]).sum(axis=1)
    D = (Sa - Sb) / N
    M = ((W @ sums["b_abs"]) - (W @ sums["a_abs"])) / N
    out["sd"] = float(D.std(ddof=1))
    out["p"] = float((1 + int((D <= 0).sum())) / (B + 1))
    out["p_reversal"] = float((1 + int((D >= 0).sum())) / (B + 1))
    out["mae_diff_hi95"] = float(np.percentile(M, 95))
    out["draws"] = int(B)
    return out


def guards(frame: dict, pred_a: np.ndarray, pred_b: np.ndarray, boot: dict) -> dict:
    """G1 to G4 of gate section 7 for arm ``b`` against predecessor ``a``."""
    rows = frame["rows"]
    act = np.array([r["act"] for r in rows])
    ea, eb = pred_a - act, pred_b - act
    g = {}
    g["G1"] = {"mae_diff_hi95": boot.get("mae_diff_hi95"), "limit": G1_MAE,
               "pass": (boot.get("mae_diff_hi95") is None) or (boot["mae_diff_hi95"] <= G1_MAE)}
    star = np.array([r["star"] for r in rows], dtype=bool)
    if star.any():
        ba, bb = float(ea[star].mean()), float(eb[star].mean())
        g["G2"] = {"n": int(star.sum()), "bias_pred": ba, "bias_arm": bb, "limit": G2_STAR,
                   "pass": abs(bb) - abs(ba) <= G2_STAR}
    else:
        g["G2"] = {"n": 0, "bias_pred": None, "bias_arm": None, "limit": G2_STAR, "pass": True}
    h5 = np.array([r["h"] == HORIZONS for r in rows], dtype=bool)
    n_act = int((act[h5] >= TAIL_WAR).sum()) if h5.any() else 0
    if n_act > 0:
        ra = float((pred_a[h5] >= TAIL_WAR).sum() / n_act)
        rb = float((pred_b[h5] >= TAIL_WAR).sum() / n_act)
        g["G3"] = {"n_act_ge3": n_act, "ratio_pred": ra, "ratio_arm": rb, "limit": G3_TAIL,
                   "pass": rb >= ra - G3_TAIL}
    else:
        g["G3"] = {"n_act_ge3": 0, "ratio_pred": None, "ratio_arm": None, "limit": G3_TAIL, "pass": True}
    by_bucket: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_bucket[f"{r['side']}:{r['bucket']}"].append(i)
    g4 = {}
    ok = True
    for b, idx in sorted(by_bucket.items()):
        if len(idx) < G4_MIN_N:
            continue
        ii = np.array(idx)
        ma, mb = float(np.abs(ea[ii]).mean()), float(np.abs(eb[ii]).mean())
        g4[b] = {"n": len(idx), "mae_pred": ma, "mae_arm": mb, "pass": mb - ma <= G4_BUCKET}
        ok = ok and g4[b]["pass"]
    g["G4"] = {"buckets": g4, "limit": G4_BUCKET, "min_n": G4_MIN_N, "pass": ok}
    g["all_pass"] = all(g[k]["pass"] for k in ("G1", "G2", "G3", "G4"))
    return g


def report_cells(frame: dict, pred: np.ndarray, archetypes: list[str] | None = None) -> dict:
    """Reported, never adjudicated: ACAL and MAE by age band x bucket and by
    age band x archetype."""
    rows = frame["rows"]
    act = np.array([r["act"] for r in rows])
    e = pred - act
    out = {"band_x_bucket": {}, "band_x_archetype": {}}
    groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[f"{r['side']}:{r['band']}:{r['bucket']}"].append(i)
    for k, idx in sorted(groups.items()):
        ii = np.array(idx)
        out["band_x_bucket"][k] = {"n": len(idx), "bias": float(e[ii].mean()),
                                   "mae": float(np.abs(e[ii]).mean())}
    if archetypes is not None:
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            groups[f"{r['side']}:{r['band']}:{archetypes[i]}"].append(i)
        for k, idx in sorted(groups.items()):
            ii = np.array(idx)
            out["band_x_archetype"][k] = {"n": len(idx), "bias": float(e[ii].mean()),
                                          "mae": float(np.abs(e[ii]).mean())}
    return out


def row_archetypes(frame: dict, U: Universe, cfg: dict) -> list[str]:
    """The out-of-window archetype of every row's pair start (season B,
    window B-3..B-1), for the reports; NEUTRAL where thin."""
    cfg = A.normalize_config(cfg)
    ztabs: dict[int, dict] = {}
    out = []
    sc_rows = (U.sidecar.get("rows") or {})
    for r in frame["rows"]:
        B = r["B"]
        if B - 1 not in ztabs:
            ztabs[B - 1] = A._season_z_tables(U.corpus, cfg, B - 1)
        check_out_of_window(cfg, B)
        seasons = U.by_player[r["side"]][r["mlbam"]]
        arch, _ = A.assign_archetype(r["side"], B, seasons, sc_rows, ztabs[B - 1], cfg, U.league)
        out.append(arch)
    return out


def level_summary(model: A.AgingModel) -> dict:
    """Per cell: the peak age and the mean annual slope of level() before and
    after the peak (reported, never adjudicated)."""
    out = {}
    for side in A.SIDES:
        for cell in sorted(model.cells.get(side) or {}):
            bucket, arch = cell, None
            if "|" in cell:
                head, tail = cell.rsplit("|", 1)
                if tail in A.ARCHETYPES[side]:
                    bucket, arch = head, tail
            if bucket in (A.PARENT[side],):
                bucket = None
            role = bucket if (side == "pit" and bucket in A.PIT_BUCKETS) else None
            try:
                curve = model._level_curve(side, bucket if bucket in A.BUCKETS[side] else None, arch, role)
            except Exception:   # noqa: BLE001 - a cell the API cannot address is reported as such
                curve = {}
            if not curve:
                out[f"{side}:{cell}"] = None
                continue
            ages = sorted(curve)
            peak = max(ages, key=lambda a: curve[a])
            before = [curve[b] - curve[a] for a, b in zip(ages, ages[1:]) if b <= peak]
            after = [curve[b] - curve[a] for a, b in zip(ages, ages[1:]) if a >= peak]
            out[f"{side}:{cell}"] = {"peak_age": int(peak),
                                     "slope_before": (sum(before) / len(before)) if before else None,
                                     "slope_after": (sum(after) / len(after)) if after else None,
                                     "support": [int(ages[0]), int(ages[-1])]}
    return out


def cell_counts(model: A.AgingModel) -> dict:
    """n and w (the shrinkage weight) for every bucket x age and archetype x
    age cell of a fitted model (war_rate)."""
    out = {"bucket_x_age": {}, "archetype_x_age": {}}
    for side in A.SIDES:
        for cell, comps in sorted((model.cells.get(side) or {}).items()):
            curve = comps.get("war_rate") or {}
            tail = cell.rsplit("|", 1)[1] if "|" in cell else ""
            key = "archetype_x_age" if tail in A.ARCHETYPES[side] else "bucket_x_age"
            if key == "bucket_x_age" and tail and tail not in A.ARCHETYPES[side]:
                continue                            # a v2 profile cohort, not a registered cell
            out[key][f"{side}:{cell}"] = {str(a): {"n": int(v.get("n", 0)),
                                                   "w": v.get("w_shrink", 1.0 if cell in A.PARENT.values() else None)}
                                          for a, v in sorted(curve.items())}
    return out


# ---------------------------------------------------------------------------
# dev: the DEV selection (gate section 8)
# ---------------------------------------------------------------------------

def select(cands: list[tuple[tuple, float]], nearer_key) -> tuple:
    """The DEV ACAL minimum; a value within TIE of the minimum that is nearer
    the incumbent (smaller ``nearer_key``) wins the tie."""
    best = min(v for _, v in cands)
    tied = [k for k, v in cands if v <= best + TIE]
    return min(tied, key=nearer_key)


def run_dev(U: Universe, out_path: Path | None, log=print, frame: dict | None = None) -> dict:
    """ARM T on, then the S grid with T, the P grid with T and S, the R grid
    with T, S and P (completion C4), each selected by the DEV ACAL rule;
    returns the artifact dict (DEV rows only; the DEV guard raises on any
    other label season)."""
    t0 = time.time()
    frame = frame or build_frame(U, "DEV", FRAMES["DEV"], DEV_GUARD)
    DEV_GUARD.check_rows(frame["rows"])
    log(f"DEV frame: {len(frame['rows'])} rows, bases {frame['bases'][0]}-{frame['bases'][-1]}, "
        f"label seasons {frame['label_seasons']}, census {frame['census']}")
    preds: dict[str, np.ndarray] = {}

    def P(cfg):
        h = A.config_hash(cfg)
        if h not in preds:
            preds[h] = predict(frame, U, cfg, DEV_GUARD)
        return preds[h]

    cells, names = cell_index(frame)
    act = np.array([r["act"] for r in frame["rows"]])

    def ACAL(cfg):
        return acal(P(cfg) - act, cells, len(names))

    comp = comparator_cfg()
    art = {"comparator": {"cfg8": A.config_hash(comp), "acal_dev": ACAL(comp)}, "arms": {}}
    sel = dict(INCUMBENT, k_P=200, k_R=400)
    # ARM T, no grid
    cfg_t = arm_cfg({"T": True})
    art["arms"]["T"] = {"grid": None, "acal_dev": ACAL(cfg_t), "cfg8": A.config_hash(cfg_t)}
    log(f"  T: DEV ACAL {art['arms']['T']['acal_dev']:.5f} (comparator {art['comparator']['acal_dev']:.5f})")
    # ARM S with T
    grid = []
    for lam in GRID_LAMBDA:
        for sm, pen in GRID_SMOOTHER:
            cfg = arm_cfg({"T": True, "S": True}, lam, sm, pen)
            v = ACAL(cfg)
            grid.append(((lam, sm, pen), v))
            log(f"  S: lambda {lam} smoother {sm} penalty {pen}: DEV ACAL {v:.5f}")
    lam, sm, pen = select(grid, lambda k: (abs(k[0] - INCUMBENT["lambda"]), smoother_rank(k[1], k[2])))
    sel.update(**{"lambda": lam, "smoother": sm, "penalty": pen})
    art["arms"]["S"] = {"grid": [{"lambda": k[0], "smoother": k[1], "penalty": k[2], "acal_dev": v}
                                 for k, v in grid],
                        "selected": {"lambda": lam, "smoother": sm, "penalty": pen},
                        "acal_dev": dict(grid)[(lam, sm, pen)],
                        "cfg8": A.config_hash(arm_cfg({"T": True, "S": True}, lam, sm, pen))}
    log(f"  S selected: lambda {lam} smoother {sm} penalty {pen}")
    # ARM P with T and S
    grid = []
    for kp in GRID_KP:
        cfg = arm_cfg({"T": True, "S": True, "P": True}, lam, sm, pen, kp)
        v = ACAL(cfg)
        grid.append(((kp,), v))
        log(f"  P: k_P {kp}: DEV ACAL {v:.5f}")
    (kp,) = select(grid, lambda k: -k[0])
    sel["k_P"] = kp
    art["arms"]["P"] = {"grid": [{"k_P": k[0], "acal_dev": v} for k, v in grid],
                        "selected": {"k_P": kp}, "acal_dev": dict(grid)[(kp,)],
                        "cfg8": A.config_hash(arm_cfg({"T": True, "S": True, "P": True}, lam, sm, pen, kp))}
    log(f"  P selected: k_P {kp}")
    # ARM R with T, S and P
    grid = []
    for kr in GRID_KR:
        cfg = arm_cfg({"T": True, "S": True, "P": True, "R": True}, lam, sm, pen, kp, kr)
        v = ACAL(cfg)
        grid.append(((kr,), v))
        log(f"  R: k_R {kr}: DEV ACAL {v:.5f}")
    (kr,) = select(grid, lambda k: -k[0])
    sel["k_R"] = kr
    art["arms"]["R"] = {"grid": [{"k_R": k[0], "acal_dev": v} for k, v in grid],
                        "selected": {"k_R": kr}, "acal_dev": dict(grid)[(kr,)],
                        "cfg8": A.config_hash(composition_cfg(list(ARMS), sel))}
    log(f"  R selected: k_R {kr}")
    art["selected"] = sel
    # n and w per cell from the fit through the last DEV base's season (2009 on
    # the real corpus): the bucket cells under T, S, P and the archetype cells
    # under T, S, P, R, at the selections
    last_fit = max(frame["bases"]) - 1
    _, _, m_p = attached(U.corpus, U.sidecar, last_fit, composition_cfg(["T", "S", "P"], sel))
    _, _, m_r = attached(U.corpus, U.sidecar, last_fit, composition_cfg(list(ARMS), sel))
    cc_p, cc_r = cell_counts(m_p), cell_counts(m_r)
    art["cells"] = {"fit_through_season": last_fit,
                    "bucket_x_age": cc_p["bucket_x_age"], "archetype_x_age": cc_r["archetype_x_age"],
                    "level": level_summary(m_r), "caps": m_r.caps}
    art["frame"] = {"name": "DEV", "label_seasons": frame["label_seasons"], "bases": frame["bases"],
                    "n_rows": len(frame["rows"]), "n_players": int(player_index(frame)[1]),
                    "census": frame["census"],
                    "rows_by_label_season": {str(s): int(sum(1 for r in frame["rows"] if r["L"] == s))
                                             for s in frame["label_seasons"]}}
    art["preds"] = preds
    art["wall_s"] = round(time.time() - t0, 1)
    return art


# ---------------------------------------------------------------------------
# mde: the power artifact (gate section 8)
# ---------------------------------------------------------------------------

def z(p: float) -> float:
    return statistics.NormalDist().inv_cdf(p)


MDE_FACTOR = z(1.0 - ALPHA) + z(POWER)      # the D at which a p < ALPHA test has POWER


def plant(frame: dict, pred_a: np.ndarray, pred_b: np.ndarray) -> np.ndarray:
    """The simulated arm of one plant: the predecessor's predictions carrying
    the arm's own row-level dispersion around the predecessor (centred within
    each cell, so no cell bias moves by itself), with a correction of
    PLANT_WAR toward zero bias in every planted cell (24 and under, 31 and
    over), the correction never larger than the cell's own bias."""
    act = np.array([r["act"] for r in frame["rows"]])
    cells, names = cell_index(frame)
    ea = pred_a - act
    d = pred_b - pred_a
    sim = pred_a.copy()
    for c, name in enumerate(names):
        ii = np.where(cells == c)[0]
        if ii.size == 0:
            continue
        sim[ii] += d[ii] - d[ii].mean()
        band = name.split(":", 1)[1]
        if band in PLANTED_BANDS:
            bias = float(ea[ii].mean())
            sim[ii] -= math.copysign(min(PLANT_WAR, abs(bias)), bias)
    return sim


def run_mde(U: Universe, art: dict, log=print, n_plants: int = N_PLANTS, B: int = B_BOOT,
            frame: dict | None = None) -> dict:
    """Per arm at its selection against its predecessor on DEV: D, its
    player-cluster bootstrap sd, MDE95 = (z_{1-ALPHA} + z_{POWER}) x sd, and the
    detection rate of a PLANT_WAR correction over ``n_plants`` simulated
    plants (each a player-cluster resample of the DEV frame carrying the
    plant, tested by the registered bootstrap); UNDERPOWERED iff MDE95 > 0.03."""
    t0 = time.time()
    frame = frame or build_frame(U, "DEV", FRAMES["DEV"], DEV_GUARD)
    DEV_GUARD.check_rows(frame["rows"])
    sel = art["selected"]
    preds = art.get("preds") or {}

    def P(cfg):
        h = A.config_hash(cfg)
        if h not in preds:
            preds[h] = predict(frame, U, cfg, DEV_GUARD)
        return preds[h]

    comps = {"comparator": comparator_cfg()}
    passed: list[str] = []
    for a in ARMS:
        passed.append(a)
        comps[a] = composition_cfg(list(passed), sel)
    _, n_players = player_index(frame)
    power = {}
    prev = "comparator"
    for a in ARMS:
        pa, pb = P(comps[prev]), P(comps[a])
        boot = bootstrap_pair(frame, pa, pb, B=B, seed=SEED)
        sd = boot.get("sd")
        mde95 = (MDE_FACTOR * sd) if sd is not None else None
        sim = plant(frame, pa, pb)
        detected = 0
        d_hats, sds = [], []
        for j in range(n_plants):
            rng = np.random.default_rng(SEED + 1 + j)
            counts = np.bincount(rng.integers(0, n_players, size=n_players), minlength=n_players)
            bj = bootstrap_pair(frame, pa, sim, B=B, seed=SEED, probs=counts / counts.sum())
            if bj.get("p") is not None and bj["p"] < ALPHA:
                detected += 1
            if bj.get("D") is not None:
                d_hats.append(bj["D"])
            if bj.get("sd") is not None:
                sds.append(bj["sd"])
        full = bootstrap_pair(frame, pa, sim, B=B, seed=SEED)
        power[a] = {
            "predecessor": prev, "cfg8": A.config_hash(comps[a]), "predecessor_cfg8": A.config_hash(comps[prev]),
            "n_rows": boot["n_rows"], "n_players": boot["n_players"],
            "D_dev": boot["D"], "sd_D": sd, "mde95": mde95, "mde_factor": MDE_FACTOR,
            "mde95_onesided_1645": (1.6449 * sd) if sd is not None else None,
            "underpowered": (mde95 is None) or (mde95 > UNDERPOWERED_MDE),
            "plant": {"war": PLANT_WAR, "bands": list(PLANTED_BANDS), "n_plants": n_plants,
                      "D_planted_full_frame": full["D"], "sd_planted_full_frame": full.get("sd"),
                      "detected": detected, "detection_rate": detected / n_plants if n_plants else None,
                      "D_hat_mean": (sum(d_hats) / len(d_hats)) if d_hats else None,
                      "sd_median": (statistics.median(sds) if sds else None),
                      "alpha": ALPHA, "B": B, "seed": SEED, "plant_seeds": [SEED + 1, SEED + n_plants]},
        }
        log(f"  {a} vs {prev}: D_dev {boot['D']:+.5f} sd {sd if sd is None else round(sd, 5)} "
            f"MDE95 {mde95 if mde95 is None else round(mde95, 5)} "
            f"{'UNDERPOWERED' if power[a]['underpowered'] else 'powered'}; plant {PLANT_WAR} WAR "
            f"detected {detected}/{n_plants}")
        prev = a
    art["power"] = power
    art["power_wall_s"] = round(time.time() - t0, 1)
    return art


def write_mde(art: dict, path: Path, U: Universe, source: str) -> dict:
    """The DEV-only artifact. Carries no GATE, TIER-2 or CONFIRM row (the
    frame block names DEV's label seasons only; a test pins it)."""
    doc = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task": "AG_6_AGING_V3_DEV_AND_POWER", "gate": "docs/AGING_V3_GATE.md section 8",
        "protocol_hash": PROTOCOL_HASH, "aging_v3_version": A.AGING_V3_VERSION,
        "source": source,
        "corpus": {"provider": U.corpus.get("war_provider"), "sig": fp._corpus_sig(U.corpus),
                   "first": U.corpus.get("first"), "last": U.corpus.get("last")},
        "sidecar_sig": ((U.sidecar.get("meta") or {}).get("sig")),
        "frame": art["frame"],
        "rule": {"selection": "the DEV ACAL minimum; a value within 0.002 of the minimum nearer the "
                              "incumbent wins the tie (lambda nearer 1.0; ma3 before a penalized fit, "
                              "then the larger penalty; the larger k_P; the larger k_R); the S grid's tie "
                              "order is lexicographic in that order (lambda first, then the smoother)",
                 "order": "T on; S selected with T; P with T and S; R with T, S and P (C4); never re-selected",
                 "tie": TIE, "grid": {"lambda": list(GRID_LAMBDA),
                                      "smoother": [f"{s}:{p}" for s, p in GRID_SMOOTHER],
                                      "k_P": list(GRID_KP), "k_R": list(GRID_KR)},
                 "power": "D = ACAL(predecessor) - ACAL(arm) on DEV; player-cluster bootstrap B 2000 seed "
                          "20261124; MDE95 = (z_{1-0.0125} + z_{0.95}) x sd(D); a 0.05 WAR correction "
                          "planted in the 24-and-under and 31-and-over cells over 200 plants, each a "
                          "player-cluster resample tested at p < 0.0125; UNDERPOWERED iff MDE95 > 0.03"},
        "comparator": art["comparator"], "arms": art["arms"], "selected": art["selected"],
        "power": art["power"], "cells": art["cells"],
        "wall_s": {"dev": art.get("wall_s"), "mde": art.get("power_wall_s")},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def artifact_label_seasons(doc: dict) -> set[int]:
    """Every label season the artifact names (the VOID check: only DEV may appear)."""
    return {int(s) for s in doc.get("frame", {}).get("label_seasons", [])} | \
        {int(s) for s in (doc.get("frame", {}).get("rows_by_label_season") or {})}


# ---------------------------------------------------------------------------
# look: the ladder on GATE, PS, the TIER-2 veto, CONFIRM (gate sections 7, 9)
# ---------------------------------------------------------------------------

def run_ladder(U: Universe, frame: dict, sel: dict, underpowered: dict, log=print,
               B: int = B_BOOT) -> dict:
    """Each arm in the order T, S, P, R against the composition of the arms
    already passed (the comparator for T): PASS iff p < ALPHA and every guard
    holds; a failed or UNDERPOWERED arm is skipped."""
    cells, names = cell_index(frame)
    preds: dict[str, np.ndarray] = {}

    def P(cfg):
        h = A.config_hash(cfg)
        if h not in preds:
            preds[h] = predict(frame, U, cfg)
        return preds[h]

    comp = comparator_cfg()
    passed: list[str] = []
    out = {"frame": frame["name"], "n_rows": len(frame["rows"]), "arms": {}, "order": list(ARMS)}
    pred_cfg = comp
    for a in ARMS:
        cand = composition_cfg(passed + [a], sel)
        entry = {"predecessor": list(passed), "cfg8": A.config_hash(cand),
                 "predecessor_cfg8": A.config_hash(pred_cfg)}
        if underpowered.get(a):
            entry["verdict"] = "UNDERPOWERED"
            entry["note"] = "skipped: the DEV power artifact marks the arm UNDERPOWERED"
            out["arms"][a] = entry
            log(f"  {a}: UNDERPOWERED (skipped)")
            continue
        pa, pb = P(pred_cfg), P(cand)
        boot = bootstrap_pair(frame, pa, pb, B=B, seed=SEED)
        g = guards(frame, pa, pb, boot)
        ok = (boot.get("p") is not None) and boot["p"] < ALPHA and g["all_pass"]
        entry.update({"bootstrap": boot, "guards": g, "verdict": "PASS" if ok else "FAIL",
                      "report": report_cells(frame, pb, row_archetypes(frame, U, cand))})
        out["arms"][a] = entry
        log(f"  {a}: D {boot['D'] if boot['D'] is None else round(boot['D'], 5)} p {boot.get('p')} "
            f"guards {'ok' if g['all_pass'] else 'FAILED'} -> {entry['verdict']}")
        if ok:
            passed.append(a)
            pred_cfg = cand
    out["passed"] = passed
    out["composition_cfg8"] = A.config_hash(pred_cfg)
    return out


def run_veto(U: Universe, frame: dict, ladder: dict, sel: dict, log=print, B: int = B_BOOT) -> dict:
    """Each passed arm read on ``frame`` against the same predecessor it was
    adjudicated against; VETOED if D is significantly reversed; a veto
    withdraws every later arm adjudicated against a composition that contained
    it (C6)."""
    out = {"frame": frame["name"], "n_rows": len(frame["rows"]), "arms": {}}
    if not frame["rows"]:
        out["note"] = "no rows: nothing read"
        return out
    withdrawn = False
    kept: list[str] = []
    for a in ladder["passed"]:
        pred = ladder["arms"][a]["predecessor"]
        if withdrawn:
            out["arms"][a] = {"verdict": "WITHDRAWN", "note": "a vetoed arm was in its predecessor composition"}
            continue
        pa = predict(frame, U, composition_cfg(pred, sel))
        pb = predict(frame, U, composition_cfg(pred + [a], sel))
        boot = bootstrap_pair(frame, pa, pb, B=B, seed=SEED)
        vetoed = boot.get("p_reversal") is not None and boot["p_reversal"] < ALPHA
        out["arms"][a] = {"bootstrap": boot, "verdict": "VETOED" if vetoed else "KEPT",
                          "report": report_cells(frame, pb)}
        log(f"  {frame['name']} {a}: D {boot['D'] if boot['D'] is None else round(boot['D'], 5)} "
            f"p_reversal {boot.get('p_reversal')} -> {out['arms'][a]['verdict']}")
        if vetoed:
            withdrawn = True
        else:
            kept.append(a)
    out["kept"] = kept
    return out


def ps_population(U: Universe) -> list[dict]:
    """Section 9: MLB debutants from the corpus itself (first corpus season
    with exposure, PS_FIRST_DEBUT or later), cohorts PS_COHORTS, at least
    PS_MIN_SEASONS seasons of 150 PA / 30 IP in d..d+6; two-sided players and
    players with no debut age excluded; cohorts 2020, 2021, 2025 and 2026
    never read. No FV, grade, list vintage or prospect row is read."""
    pop = []
    two_sided_players = {m for m, _ in U.two_sided}
    for mlbam, d in U.first.items():
        if d not in PS_COHORTS or d in NEVER_READ_COHORTS or d < PS_FIRST_DEBUT:
            continue
        if mlbam in two_sided_players or is_rvm(mlbam, U.first):
            continue
        side = "hit" if mlbam in U.by_player["hit"] else "pit"
        seasons = U.by_player[side].get(mlbam) or {}
        if not seasons or min(seasons) != d:
            continue
        row0 = seasons[d]
        if not row0.get("age"):
            continue
        qual = 0
        for s in range(d, d + PS_WINDOW + 1):
            r = seasons.get(s)
            if r is None:
                continue
            if side == "hit" and (r.get("pa") or 0) >= PS_MIN_PA:
                qual += 1
            if side == "pit" and (r.get("ip") or 0) >= PS_MIN_IP:
                qual += 1
        if qual < PS_MIN_SEASONS:
            continue
        window = [s for s in range(d, min(d + PS_WINDOW, U.last) + 1) if s != MASKED_LABEL]
        if len(window) < 2:
            continue
        sc = (U.sidecar.get("rows") or {}).get((mlbam, d)) or {}
        if side == "hit":
            bucket = A.bucket_from_position(sc.get("pos"), False, two_way_hitting=bool(sc.get("two_way")))
        else:
            bucket = A.base_role("pit", None, row0.get("role"))
        pop.append({"mlbam": mlbam, "side": side, "d": d, "debut_age": float(row0["age"]),
                    "band": band_of(row0["age"], PS_BANDS), "bucket": bucket or "pooled",
                    "reliever": bucket == "RP", "window": window,
                    "y": [float(U.war_actual.get((mlbam, s), 0.0)) for s in window]})
    return pop


def tent_shape(side: str, debut_age: float, offsets: list[int]) -> list[float]:
    """The incumbent tent (value_framework._trajectory_shape's aging branch)
    over an arbitrary window, renormalized to mean 1.0."""
    cfg = vf._config().get("aging", {})
    peak = float(cfg["pitcher_peak_age" if side == "pit" else "hitter_peak_age"])
    raw = [vf._aging_multiplier(debut_age + k, peak, cfg) for k in offsets]
    mean = (sum(raw) / len(raw)) or 1.0
    return [r / mean for r in raw]


def _renorm(vals: list[float]) -> list[float]:
    mean = (sum(vals) / len(vals)) or 1.0
    return [v / mean for v in vals]


def sse_levelfree(y: list[float], s: list[float]) -> float:
    ss = sum(v * v for v in s)
    L = (sum(a * b for a, b in zip(y, s)) / ss) if ss > 0 else 0.0
    return sum((a - L * b) ** 2 for a, b in zip(y, s)) / len(y)


def run_ps(U: Universe, cfg_accepted: dict, log=print, B: int = B_BOOT) -> dict:
    """The prospect shape gate: the incumbent tent against the v3 shape()
    under the accepted composition, both fit point-in-time through d-1."""
    pop = ps_population(U)
    out = {"n": len(pop), "cohorts": list(PS_COHORTS), "composition_cfg8": A.config_hash(cfg_accepted)}
    if not pop:
        out.update({"verdict": "NO_POPULATION", "primary": None})
        log("  PS: no population")
        return out
    models: dict[int, A.AgingModel] = {}
    diffs, rows = [], []
    for p in pop:
        d = p["d"]
        if d not in models:
            models[d] = attached(U.corpus, U.sidecar, d - 1, cfg_accepted)[2]
        offsets = [s - d for s in p["window"]]
        inc = tent_shape(p["side"], p["debut_age"], offsets)
        full = models[d].shape(p["side"], p["debut_age"], PS_WINDOW + 1,
                               p["bucket"] if p["bucket"] != "pooled" else None, p["reliever"])
        v3 = _renorm([full[k] for k in offsets])
        s_inc, s_v3 = sse_levelfree(p["y"], inc), sse_levelfree(p["y"], v3)
        diffs.append(s_inc - s_v3)
        rows.append({**p, "sse_inc": s_inc, "sse_v3": s_v3})
    diffs_a = np.array(diffs)
    n = len(diffs_a)
    rng = np.random.default_rng(SEED)
    draws = np.array([diffs_a[rng.integers(0, n, size=n)].mean() for _ in range(B)]) if n >= 2 else np.array([])
    lo95 = float(np.percentile(draws, 5)) if draws.size else None
    primary = {"mean_paired_sse_diff": float(diffs_a.mean()), "lo95": lo95, "B": B, "seed": SEED,
               "pass": (lo95 is not None) and lo95 > 0}
    gd = {}
    ok = True
    for key in ("band", "bucket"):
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            groups[str(r[key])].append(r)
        for g, rs in sorted(groups.items()):
            if len(rs) < PS_MIN_N:
                continue
            mi = sum(r["sse_inc"] for r in rs) / len(rs)
            mv = sum(r["sse_v3"] for r in rs) / len(rs)
            gd[f"{key}:{g}"] = {"n": len(rs), "sse_inc": mi, "sse_v3": mv,
                                "pass": mv <= mi * (1.0 + PS_GUARD)}
            ok = ok and gd[f"{key}:{g}"]["pass"]
    out.update({"primary": primary, "guards": gd, "guards_pass": ok,
                "verdict": "PASS" if (primary["pass"] and ok) else "FAIL",
                "strata": {"debut_age_bands": [b[0] for b in PS_BANDS]}})
    log(f"  PS: n {n} mean paired SSE diff {primary['mean_paired_sse_diff']:+.5f} lo95 {lo95} "
        f"guards {'ok' if ok else 'FAILED'} -> {out['verdict']}")
    return out


def run_look(U: Universe, mde_doc: dict, out_dir: Path, log=print, B: int = B_BOOT,
             write_eval: Path | None = None, source: str = "real",
             waiver: dict | None = None) -> dict:
    """The whole look: the ladder on GATE, PS, the TIER-2 veto, CONFIRM.
    ``waiver`` (from ``_stop_if_blocked`` under --owner-waived-early-read) is
    recorded in the artifact as ``owner_waived_early_read``; None otherwise."""
    t0 = time.time()
    assert_protocol()
    if mde_doc.get("protocol_hash") != PROTOCOL_HASH:
        raise RuntimeError("the DEV artifact was written under another protocol hash")
    bad = artifact_label_seasons(mde_doc) - set(FRAMES["DEV"])
    if bad:
        raise EarlyLookError(f"the DEV artifact names non-DEV label seasons {sorted(bad)}: VOID")
    sel = mde_doc["selected"]
    underpowered = {a: bool(v.get("underpowered")) for a, v in (mde_doc.get("power") or {}).items()}
    log(f"selections (never re-selected): {sel}; underpowered {underpowered}")
    gate = build_frame(U, "GATE", FRAMES["GATE"], FrameGuard("GATE", FRAMES["GATE"]))
    log(f"GATE frame: {len(gate['rows'])} rows, census {gate['census']}")
    ladder = run_ladder(U, gate, sel, underpowered, log=log, B=B)
    accepted = composition_cfg(ladder["passed"], sel)
    log(f"ladder: passed {ladder['passed']} composition cfg8 {A.config_hash(accepted)}")
    ps = run_ps(U, accepted, log=log, B=B)
    tier2 = build_frame(U, "TIER2", FRAMES["TIER2"], FrameGuard("TIER2", FRAMES["TIER2"]))
    log(f"TIER-2 frame: {len(tier2['rows'])} rows, census {tier2['census']}")
    veto2 = run_veto(U, tier2, ladder, sel, log=log, B=B)
    confirm = build_frame(U, "CONFIRM", FRAMES["CONFIRM"], FrameGuard("CONFIRM", FRAMES["CONFIRM"]))
    n_conf = len({r["mlbam"] for r in confirm["rows"]})
    log(f"CONFIRM frame: {len(confirm['rows'])} rows, {n_conf} players, census {confirm['census']}")
    if len(confirm["rows"]) >= CONFIRM_MIN_N:
        ladder2 = dict(ladder, passed=veto2.get("kept", ladder["passed"]))
        vetoc = run_veto(U, confirm, ladder2, sel, log=log, B=B)
        vetoc["opened"] = True
    else:
        vetoc = {"frame": "CONFIRM", "opened": False, "n_rows": len(confirm["rows"]),
                 "note": f"not opened: row-matched n {len(confirm['rows'])} < {CONFIRM_MIN_N}", "arms": {},
                 "kept": veto2.get("kept", ladder["passed"])}
        log(f"  CONFIRM not opened (n {len(confirm['rows'])} < {CONFIRM_MIN_N})")
    final = vetoc.get("kept", veto2.get("kept", ladder["passed"]))
    composition_changed = list(final) != list(ladder["passed"])
    if composition_changed and ps.get("verdict") == "PASS":
        ps["verdict"] = "composition withdrawn"
    doc = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task": "AG_7_AGING_V3_LOOK", "gate": "docs/AGING_V3_GATE.md sections 7 and 9",
        "protocol_hash": PROTOCOL_HASH, "aging_v3_version": A.AGING_V3_VERSION, "source": source,
        "corpus": {"provider": U.corpus.get("war_provider"), "sig": fp._corpus_sig(U.corpus),
                   "first": U.corpus.get("first"), "last": U.corpus.get("last")},
        "dev_artifact_generated_at": mde_doc.get("generated_at"), "selected": sel,
        "frames": {k: {"label_seasons": f["label_seasons"], "bases": f["bases"], "n_rows": len(f["rows"]),
                       "census": f["census"]} for k, f in (("GATE", gate), ("TIER2", tier2), ("CONFIRM", confirm))},
        "ladder": ladder, "ps": ps, "tier2_veto": veto2, "confirm": vetoc,
        "final_composition": final, "final_cfg8": A.config_hash(composition_cfg(final, sel)),
        "owner_waived_early_read": waiver,
        "wall_s": round(time.time() - t0, 1),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "aging_v3_look.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
    if write_eval is not None:
        write_eval.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"record row: | {doc['generated_at'][:10]} | ladder+PS | passed {ladder['passed']} final {final}; "
        f"PS {ps.get('verdict')} | {hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12]} | "
        f"wall {doc['wall_s']}s{' | owner-waived early read' if waiver else ''} |")
    return doc


# ---------------------------------------------------------------------------
# health: the H family (gate section 10)
# ---------------------------------------------------------------------------

def h_bases(label_seasons) -> list[int]:
    lo, hi = min(label_seasons), max(label_seasons)
    return [b for b in range(lo - H_HORIZONS + 1, hi + 1) if b >= H_FIRST_BASE]


def health_rows(U: Universe, frame: dict, model_by_base: dict) -> list[dict]:
    """Frame rows with h <= 3 whose feature window t-2..t lies inside the
    transactions coverage (C8), each carrying its z-features."""
    tj = U.sidecar.get("tj") or {}
    sc_rows = U.sidecar.get("rows") or {}
    out = []
    for r in frame["rows"]:
        if r["h"] > H_HORIZONS or r["B"] < H_FIRST_BASE:
            continue
        m = model_by_base[r["B"]]
        feats = m.health_features(r["side"], r["age_B"] - 1, sc_rows, tj, r["mlbam"], r["B"] - 1)
        zz = m.health_z(r["B"] - 1, feats)
        if zz is None:
            continue
        out.append(dict(r, z=zz))
    return out


def realized_exposure(U: Universe, side: str, mlbam, season: int) -> float:
    r = (U.by_player[side].get(mlbam) or {}).get(season)
    if r is None:
        return 0.0
    if side == "hit":
        return float(r.get("pa") or 0.0)
    return float(r.get("ip") or 0.0) * IP_TO_BF


def exposure_paths(rows: list[dict], U: Universe, cfg: dict, model_by_base: dict) -> tuple[np.ndarray, np.ndarray]:
    """Projected exposure and WAR at each row's horizon under ``cfg``: the
    year-1 exposure of the champion path walked with the service's pt_next."""
    sub = {"name": "H", "rows": rows}
    preds, pt1 = predict(sub, U, cfg, with_pt=True)
    expo = np.zeros(len(rows))
    for i, r in enumerate(rows):
        m = model_by_base[r["B"]]
        bucket = m.bucket_of(r["mlbam"], r["B"] - 1, r["side"], r["role"])
        e = pt1[i]
        a = r["age_B"]
        for _ in range(1, r["h"]):
            a += 1
            e = m.pt_next(r["side"], r["role"], e, a, bucket=bucket)
        expo[i] = e
    return expo, preds


def recentred_multipliers(rows: list[dict], expo: np.ndarray, gamma: list[float], clip) -> np.ndarray:
    """exp(gamma . z) clipped, recentred within each base season and side."""
    lo, hi = clip
    raw = np.array([min(hi, max(lo, math.exp(sum(g * v for g, v in zip(gamma, r["z"]))))) for r in rows])
    out = raw.copy()
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r["B"], r["side"])].append(i)
    for idx in groups.values():
        ii = np.array(idx)
        m = A.recentre_health(list(expo[ii]), list(raw[ii]))
        out[ii] = m
    return out


def _paired_mae_boot(rows: list[dict], a: np.ndarray, b: np.ndarray, B: int, seed: int) -> dict:
    """Player-cluster bootstrap of mean(|b|) - mean(|a|) over rows (negative
    means b, the H arm, is closer); returns the point, lo95 and hi95 of the
    reduction mean(|a|) - mean(|b|)."""
    keys = sorted({r["mlbam"] for r in rows}, key=str)
    pos = {k: i for i, k in enumerate(keys)}
    pidx = np.array([pos[r["mlbam"]] for r in rows])
    n = len(keys)
    red = np.abs(a) - np.abs(b)
    num = np.bincount(pidx, weights=red, minlength=n)
    cnt = np.bincount(pidx, minlength=n).astype(float)
    out = {"n_rows": len(rows), "n_players": n, "point": float(red.mean()) if len(rows) else None}
    if n < 2:
        out.update({"lo95": None, "hi95": None})
        return out
    W = _draws(n, B, seed)
    stats = (W @ num) / (W @ cnt)
    out["lo95"] = float(np.percentile(stats, 5))
    out["hi95"] = float(np.percentile(stats, 95))
    return out


def run_health(U: Universe, cfg_accepted: dict, out_dir: Path, log=print, B: int = B_BOOT,
               source: str = "real", write_eval: Path | None = None) -> dict:
    """gamma by ridge on the H DEV frame (h1 rows, log exposure ratios);
    PRIMARY on GATE: the paired exposure MAE reduction over h1-h3 (lo95 > 0);
    guards: WAR MAE upper bound, league exposure drift, CONFIRM not reversed."""
    t0 = time.time()
    cfg_h = A.normalize_config(dict(cfg_accepted, health=True))
    cfg_0 = A.normalize_config(dict(cfg_accepted, health=False))
    doc = {"generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "task": "AG_13_HEALTH_LOOK", "gate": "docs/AGING_V3_GATE.md section 10",
           "protocol_hash": PROTOCOL_HASH, "aging_v3_version": A.AGING_V3_VERSION, "source": source,
           "composition_cfg8": A.config_hash(cfg_accepted), "frames": {}}
    frames = {}
    models: dict[int, A.AgingModel] = {}
    for name, labels in H_FRAMES.items():
        bases = h_bases(labels)
        fr = build_frame(U, f"H-{name}", labels, FrameGuard(f"H-{name}", labels), bases=bases)
        for Bse in bases:
            if Bse not in models:
                models[Bse] = attached(U.corpus, U.sidecar, Bse - 1, cfg_h)[2]
        rows = health_rows(U, fr, models)
        frames[name] = rows
        doc["frames"][name] = {"label_seasons": sorted(labels), "bases": bases, "n_rows": len(rows),
                               "census": fr["census"]}
        log(f"H-{name}: {len(rows)} rows with features (of {len(fr['rows'])})")
    # gamma on DEV h1 rows
    dev = [r for r in frames["DEV"] if r["h"] == 1]
    gamma = None
    if dev:
        expo0, _ = exposure_paths(dev, U, cfg_0, models)
        Z = [r["z"] for r in dev]
        y = [math.log(max(realized_exposure(U, r["side"], r["mlbam"], r["L"]), 1.0) / max(expo0[i], 1.0))
             for i, r in enumerate(dev)]
        gamma = models[dev[0]["B"]].fit_health_gamma(Z, y)
    doc["gamma"] = gamma
    doc["gamma_features"] = list(A.HEALTH_FEATURES)
    log(f"gamma {gamma}")
    for name in ("GATE", "CONFIRM"):
        rows = frames[name]
        if not rows or gamma is None:
            doc[name] = {"n_rows": len(rows), "note": "no rows or no gamma", "verdict": "NOT_READ"}
            continue
        expo0, war0 = exposure_paths(rows, U, cfg_0, models)
        mult = recentred_multipliers(rows, expo0, gamma, cfg_h["H"]["clip"])
        expo_h, war_h = expo0 * mult, war0 * mult
        real = np.array([realized_exposure(U, r["side"], r["mlbam"], r["L"]) for r in rows])
        act = np.array([r["act"] for r in rows])
        prim = _paired_mae_boot(rows, real - expo0, real - expo_h, B, SEED)
        war = _paired_mae_boot(rows, act - war0, act - war_h, B, SEED)
        drift = {}
        for (Bse, side), idx in _group(rows).items():
            ii = np.array(idx)
            s0 = float(expo0[ii].sum())
            drift[f"{Bse}:{side}"] = abs(float(expo_h[ii].sum()) - s0) / s0 if s0 > 0 else 0.0
        entry = {"n_rows": len(rows), "primary": prim,
                 "war_mae_increase_hi95": (-war["lo95"]) if war["lo95"] is not None else None,
                 "drift": drift, "guards": {}}
        entry["guards"]["war_mae"] = (entry["war_mae_increase_hi95"] is None) or \
            (entry["war_mae_increase_hi95"] <= H_WAR_MAE)
        entry["guards"]["drift"] = all(v < H_DRIFT for v in drift.values())
        if name == "GATE":
            entry["verdict"] = "PASS" if (prim["lo95"] is not None and prim["lo95"] > 0
                                          and all(entry["guards"].values())) else "FAIL"
        else:
            entry["opened"] = len(rows) >= CONFIRM_MIN_N
            entry["verdict"] = ("REVERSED" if (entry["opened"] and prim["hi95"] is not None and prim["hi95"] < 0)
                                else ("NOT_REVERSED" if entry["opened"] else "NOT_OPENED"))
        doc[name] = entry
        log(f"H-{name}: exposure MAE reduction {prim['point']} lo95 {prim['lo95']} -> {entry['verdict']}")
    doc["wall_s"] = round(time.time() - t0, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "aging_v3_health.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                                                  encoding="utf-8")
    if write_eval is not None:
        write_eval.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def _group(rows: list[dict]) -> dict:
    g: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        g[(r["B"], r["side"])].append(i)
    return g


# ---------------------------------------------------------------------------
# Fixtures carrying nulls (gate section 14)
# ---------------------------------------------------------------------------

def _league(season: int) -> dict:
    return {"season": season, "_total_pa": 180000.0, "woba": 0.315, "r_pa": 0.115,
            "k_pct": 0.22, "bb_pct": 0.085, "iso": 0.16, "babip": 0.295, "hr_pa": 0.032,
            "fip_constant": 3.15, "era": 4.1, "p_k_pct": 0.22, "p_bb_pct": 0.085,
            "p_hr_bf": 0.032, "lg_fip": 4.1}


def fixture_corpus(seed: int = 7, n_hit: int = 320, n_pit: int = 300, first: int = 2000,
                   last: int = 2026, nulls: bool = True) -> dict:
    """A synthetic fWAR-shaped corpus, 2000 to 2026. With ``nulls``: one
    hitter whose rows carry no age; no DH position anywhere (a bucket with no
    rows); no pitcher row carries a K% or BB% (an empty archetype: POWER and
    COMMAND never assigned); no row at all in seasons 2021 to 2023 (so base
    2024 has no CONFIRM cells, and TIER-2 carries holes)."""
    rng = random.Random(seed)
    hit, pit = [], []
    positions = ["C", "SS", "2B", "3B", "CF", "LF", "RF", "1B", "X"] + ([] if nulls else ["DH"])
    gap = {2021, 2022, 2023} if nulls else set()
    mlbam = 100000
    for side, n in (("hit", n_hit), ("pit", n_pit)):
        for k_player in range(n):
            mlbam += 1
            debut = rng.randint(first, last - 2)
            age0 = rng.randint(20, 28)
            years = rng.randint(3, 13)
            talent = rng.gauss(2.0, 1.4)
            pos = rng.choice(positions) if side == "hit" else None
            role = ("C" if pos == "C" else "H") if side == "hit" else rng.choice(["SP", "SP", "RP"])
            expo = rng.uniform(250, 650) if side == "hit" else (rng.uniform(400, 900) if role == "SP" else rng.uniform(150, 320))
            no_age = nulls and side == "hit" and k_player == 3
            for k in range(years):
                s, a = debut + k, age0 + k
                if s > last or s in gap:
                    continue
                peak = 27 if side == "hit" else 26
                shape = 1.0 - 0.035 * abs(a - peak) + rng.gauss(0, 0.25)
                expo = max(60.0, expo * rng.uniform(0.85, 1.15) * (1.03 if a < peak else 0.97))
                age = None if no_age else a
                if side == "hit":
                    war = (talent * shape) * expo / 600.0
                    hit.append({"mlbam": mlbam, "season": s, "age": age, "role": role, "pa": round(expo, 0),
                                "k_pct": max(0.05, rng.gauss(0.22, 0.05)), "bb_pct": max(0.02, rng.gauss(0.085, 0.025)),
                                "iso": max(0.03, rng.gauss(0.16, 0.05)), "babip": rng.gauss(0.295, 0.03),
                                "hr_pa": max(0.0, rng.gauss(0.032, 0.012)), "war": round(war, 2),
                                "war_total": round(war, 2), "_pos": pos})
                else:
                    war = (talent * shape) * expo / 250.0 * 0.6
                    # the empty archetype: a pitcher row with no K% or BB% at all
                    # (a constant rate would give z-scores from a degenerate sd)
                    kp = None if nulls else max(0.05, rng.gauss(0.22, 0.06))
                    bp = None if nulls else max(0.02, rng.gauss(0.085, 0.025))
                    pit.append({"mlbam": mlbam, "season": s, "age": age, "role": role, "bf": round(expo, 0),
                                "ip": round(expo / 4.3, 1), "k_pct": kp, "bb_pct": bp,
                                "hr_bf": max(0.0, rng.gauss(0.032, 0.01)),
                                "war": round(war, 2), "war_total": round(war, 2), "fip": rng.gauss(4.1, 0.8)})
    league = {s: _league(s) for s in range(first, last + 1)}
    return {"hit": hit, "pit": pit, "league": league, "first": first, "last": last,
            "war_provider": "fwar", "label_shape": fp.LABEL_SHAPE}


def fixture_sidecar(corpus: dict, seed: int = 11) -> dict:
    rng = random.Random(seed)
    rows = {}
    for r in corpus["hit"]:
        rows[(r["mlbam"], r["season"])] = {
            "pos": r.get("_pos"), "two_way": False, "pa": r["pa"], "sb": 0.0, "cs": 0.0,
            "go": 0.0, "ao": 0.0, "bat": rng.gauss(0, 10), "bsr": rng.gauss(0, 3),
            "fld": rng.gauss(0, 6), "inn": r["pa"] * 1.4,
            "il_days": float(rng.choice([0, 0, 0, 12, 30, 65])) if r["season"] >= 2008 else None,
            "il_stints": rng.choice([0, 0, 1, 2]) if r["season"] >= 2008 else None,
            "il60": rng.choice([0, 0, 0, 1]) if r["season"] >= 2008 else None}
    for r in corpus["pit"]:
        rows[(r["mlbam"], r["season"])] = {
            "pos": "P", "two_way": False, "gs": 20.0 if r["role"] == "SP" else 0.0, "g": 30.0,
            "ip": r["ip"], "bf": r["bf"], "bat": None, "bsr": None, "fld": None, "inn": None,
            "il_days": float(rng.choice([0, 0, 15, 45, 120])) if r["season"] >= 2008 else None,
            "il_stints": rng.choice([0, 0, 1, 1, 2]) if r["season"] >= 2008 else None,
            "il60": rng.choice([0, 0, 0, 1]) if r["season"] >= 2008 else None}
    tj = {r["mlbam"]: [r["season"] - 1] for r in corpus["pit"][::37]}
    return {"rows": rows, "tj": tj, "meta": {"sig": "fixture", "il_coverage": list(range(2008, 2027))}}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class _Tee:
    def __init__(self, stream, path: Path):
        self.stream = stream
        self.f = open(path, "a", encoding="utf-8")

    def write(self, s):
        self.stream.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.stream.flush()
        self.f.flush()


def _tee(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = _Tee(sys.stdout, out_dir / "stdout.txt")
    sys.stderr = _Tee(sys.stderr, out_dir / "stderr.txt")


def _universe(args) -> tuple[Universe, str]:
    if args.fixture:
        corpus = fixture_corpus(nulls=True)
        return Universe(corpus, fixture_sidecar(corpus)), "fixture"
    corpus, sidecar = load_real()
    return Universe(corpus, sidecar), "real"


def _stop_if_blocked(args, today: _dt.date | None = None) -> dict | None:
    """The calendar check (gate section 13). Without --owner-waived-early-read
    a blocked day is a SystemExit naming the next free day. With the switch
    (the owner's EW3-5 waiver, explicit, never the default) the blockers are
    recorded and returned, with --rule-day as the writer computed it, so the
    artifact names the read an owner-waived early read. The fixture path
    checks nothing and returns None."""
    if args.fixture:
        return None
    blockers = calendar_blockers(today)
    waived = bool(getattr(args, "owner_waived", False))
    if blockers and not waived:
        raise SystemExit("BLOCKER: date " + next_free_day(today) + " (" + "; ".join(blockers) + ")")
    if not waived:
        return None
    today = today or _dt.date.today()
    return {"owner_waived": True, "waiver": OWNER_WAIVER, "today": today.isoformat(),
            "rule_day": getattr(args, "rule_day", None), "blockers_waived": blockers}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=("dev", "mde", "look", "health", "hash"))
    ap.add_argument("--fixture", action="store_true", help="synthetic corpora with nulls; writes under --out only")
    ap.add_argument("--out", type=Path, default=None, help="output directory (tee, artifacts)")
    ap.add_argument("--plants", type=int, default=N_PLANTS)
    ap.add_argument("--B", type=int, default=B_BOOT)
    ap.add_argument("--i-am-the-look", action="store_true", dest="look",
                    help="look / health on the real corpus: the registered look, once (AG_7 / AG_13)")
    ap.add_argument("--owner-waived-early-read", action="store_true", dest="owner_waived",
                    help="the owner's EW3-5 waiver of the look day: the calendar blockers are recorded, "
                         "not refused, and the artifact names the read an owner-waived early read")
    ap.add_argument("--rule-day", default=None,
                    help="the day the gate's section 13 rule gives, as the writer computed it (recorded)")
    return ap


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "hash":
        print(protocol_hash())
        return 0
    assert_protocol()
    if args.out is not None:
        _tee(args.out)
    waiver = _stop_if_blocked(args)
    if waiver:
        print(f"OWNER-WAIVED EARLY READ: {waiver['waiver']}; today {waiver['today']}; rule day "
              f"{waiver['rule_day']}; blockers waived: {waiver['blockers_waived'] or 'none'}")
    print(f"aging_v3_lab {args.command} {'FIXTURE' if args.fixture else 'real'} protocol {PROTOCOL_HASH[:12]} "
          f"version {A.AGING_V3_VERSION} {_dt.datetime.now().isoformat(timespec='seconds')}")
    U, source = _universe(args)
    if args.command in ("dev", "mde"):
        path = (args.out / "aging_v3_mde.json") if args.fixture else MDE_PATH
        if args.fixture and args.out is None:
            raise SystemExit("--fixture needs --out")
        if args.command == "dev":
            art = run_dev(U, path)
            art["power"] = {}
            if path.exists():
                old = json.loads(path.read_text(encoding="utf-8"))
                if old.get("selected") == art["selected"]:
                    art["power"] = old.get("power") or {}
        else:
            if not path.exists():
                raise SystemExit(f"{path} is absent: run dev first")
            old = json.loads(path.read_text(encoding="utf-8"))
            art = run_dev(U, path)
            if old.get("selected") != art["selected"]:
                raise SystemExit("the DEV selection changed since the artifact was written: "
                                 f"{old.get('selected')} != {art['selected']}")
            art = run_mde(U, art, n_plants=args.plants, B=args.B)
        write_mde(art, path, U, source)
        print(f"written {path} (DEV only; selections {art['selected']})")
        return 0
    if args.command in ("look", "health"):
        if not args.fixture and not args.look:
            raise SystemExit("the look on the real corpus is the registered look (AG_7 / AG_13): pass "
                             "--i-am-the-look and --out DIR, on the day gate section 13 defines")
        if args.out is None:
            raise SystemExit("--out DIR is required (the tee and the artifacts)")
        if args.fixture:
            # the whole chain on fixtures: dev, mde, then the look, under --out only
            path = args.out / "aging_v3_mde.json"
            art = run_dev(U, path)
            art = run_mde(U, art, n_plants=min(args.plants, 20), B=min(args.B, 200))
            mde_doc = write_mde(art, path, U, source)
        else:
            if not MDE_PATH.exists():
                raise SystemExit(f"{MDE_PATH} is absent: AG_6 has not landed")
            mde_doc = json.loads(MDE_PATH.read_text(encoding="utf-8"))
        if args.command == "look":
            run_look(U, mde_doc, args.out, B=args.B if not args.fixture else min(args.B, 200),
                     write_eval=None if args.fixture else EVAL_PATH, source=source, waiver=waiver)
        else:
            look_doc = None
            if not args.fixture:
                if not EVAL_PATH.exists():
                    raise SystemExit(f"{EVAL_PATH} is absent: the ladder's record must exist first")
                look_doc = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
                accepted = composition_cfg(look_doc["final_composition"], mde_doc["selected"])
            else:
                accepted = composition_cfg(["T"], mde_doc["selected"])
            run_health(U, accepted, args.out, B=args.B if not args.fixture else min(args.B, 200),
                       source=source, write_eval=None if args.fixture else (args.out / "aging_v3_health_eval.json"))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
