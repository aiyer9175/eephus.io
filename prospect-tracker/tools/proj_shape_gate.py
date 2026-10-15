# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The gate tool of docs/PROJ_PATH_SHAPE_GATE.md: ARM A (the joint smoothness
refit) and ARM B (the three bias levers), scored exactly as the document
registers them, writing data/proj_shape_gate.json.

This module is the battery's ONE engine. tools/proj_shape_mde_lab.py (section 3)
imports it and is confined to the DEV frame by the `ceiling` argument every
prediction call carries; tools/proj_shape_blast_lab.py (section 0a) fits nothing
and does not import it.

WHAT IS HELD FIXED (4.6d, read under amendment A-2 23.2 (b)): one pinned copy of
the `fwar` corpus (`.cache/fa_corpus.pkl` copied into the run's private work
directory and hashed), `first_base = 2003`, point-in-time `fp.fitted_models(corpus,
B - 1)` for every row (the frame is built once and every point-in-time training set
is a filter of it: a row at base B carries features fitted on seasons <= B - 1 and
enters a bundle evaluated at base B' only with labels <= B' - 1), the champion
`champ_h1..h5` from the `use_ml=False` path, the L1 two-sided exclusion on every
arm, one blend convention, SEED 20260611 with deterministic, single-threaded,
row-wise LightGBM, the five quantiles and the cross-quantile monotone sort.

LEAK CONTROLS (4.7). (1) every bundle is fitted inside this module on labels
<= B - 1 and `assert_point_in_time` raises otherwise; the live bundle is never
scored at a historical base. (2) the frame is built with the fitted-model and frame
caches pointed at the private work directory (`fp.CACHE_DIR` is repointed before
anything is fitted), so nothing reads or writes the production `.cache`. (3) and
(4) no `proj_ml.train_cached` call, no `_PIT_CACHE`: bundles are files under the
work directory keyed by arm and base. (10) blend lambdas are refit per arm per base
on out-of-fold predictions whose labels are <= B - 1; the shipped lambdas are never
read.

DEFAULTS this tool takes where the document is silent, each recorded in the
artifact's `defaults` block:
  D1  L1 exclusion: a frame row is two-sided when its base season (B - 1) is a
      player-season with corpus rows on both sides; a cell (row, h) is two-sided
      when its label season (B + h - 1) is. Both are excluded from every fit and
      every scored cell, for every arm and for S.
  D2  the point-in-time blend refit pools every earlier base from 2004 on whose
      cells carry labels <= B - 1 (the published procedures name a pool of dev
      bases; the forward-chained analogue is every base before B).
  D3  the mean blend: per horizon, lift-only, the lambda on the grid 0.0 to 1.0
      in steps of 0.1 with the smallest absolute bias among those whose MAE stays
      strictly below the champion's on the same cells (the published rule, "the
      MAX that still beats the prior champion", with |bias| as its tie-break);
      0.0 when none qualifies or the pool is empty.
  D4  the star blend: tools/fit_star_blend.py's rule (grid 0, 0.2 .. 1.0; minimise
      |star bias| with star MAE at most +0.02 over lambda 0; sides pooled), applied
      on top of the mean-blended q50 because that is the order
      proj_ml.predict_path applies them in; horizon 2 is served at 0 for both arms
      (the incumbent's h2 failed its confirmation, 4.2) and the fitted value is
      published.
  D5  the joint heads read the frame's features plus `horizon` and
      `age_at_target = age + h - 1`, appended last.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

GATE_DOC = "docs/PROJ_PATH_SHAPE_GATE.md"
OUT = ROOT / "data" / "proj_shape_gate.json"

# ---------------------------------------------------------------- registered
HORIZONS = 5
QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
FIRST_BASE = 2003
EVAL_FIRST_BASE = 2008
DEV_LABELS = (2008, 2009, 2010, 2011)
GATE_LABELS = (2012, 2013, 2014)
CONFIRM_LABELS = (2026,)
TIER2_LABELS = tuple(range(2015, 2026))
LAST_COMPLETE = 2025                       # corpus["last"] - 1, proj_eval's complete-seasons convention
LAMBDA_GRID = (0.0, 0.05, 0.10, 0.20, 0.40, 0.80)
M = 0.0065
S1B = 0.0130
ASHAPE_RS2 = 0.2617
ASHAPE_UAF = 0.1192
S3_BIAS = 0.0200
S4_DELTA = 0.0200
S4_BAND = (0.75, 0.87)
S5_PINBALL = 0.0050
S6_STAR_MAE = 0.0500
A0_MAE_TOL = 0.0050
A0_BIAS_TOL = 0.0100
B3_POOLED = 0.0100
B4_DEEPEN = 0.0500
B2_RATIO = 0.5
B2_FLOOR = 0.01
TWIN_SHARE = 0.75
CONFIRM_MIN_N = 1000
VIF_REGISTERED = 1.8
TRIPWIRE2_POINTS = 10.0
HOLM_K = 3
HOLM_ALPHA = 0.05
SEED_FIT = 20260611
SEED_BOOT = 20260918
B_TEST = 1000
B_FULL = 200
PERM_DRAWS = 200
CAL_DRAWS = 300                            # the published map's 300-draw cluster bootstrap
CAL_SEED = 20260724                        # tools/proj_calibration_lab.py's seed
Z95_ONE = 1.6448536269514722
B0_COMPARE_BASES = (2014, 2015, 2016, 2017, 2018, 2019, 2021)
LEVERS = ("B-AGE", "B-C", "B-STAR")        # the fixed Holm order (5.5)
AGE_CELLS = ("age:<=24:hit", "age:34+:hit", "age:<=24:pit", "age:34+:pit")
# 3.3: the nearer-zero end of each lever cell's published CI (data/proj_calibration_eval.json)
PLANTED = {"age:<=24:hit": -0.0155, "age:34+:hit": 0.0960, "age:<=24:pit": 0.0887,
           "age:34+:pit": -0.0024, "role:C": 0.1862, "star": -0.1489}
DENIED_STAR_H = (2,)
MEAN_GRID = tuple(round(0.1 * i, 1) for i in range(11))
STAR_GRID = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
STAR_GUARD = 0.02
VERDICTS = ("PASS", "NULL", "NULL_HOLM", "NULL_NO_ADMISSIBLE_LAMBDA", "NO_EFFECT",
            "ABSORBED", "DEAD_ON_ARRIVAL", "UNDERPOWERED", "UNDERPOWERED_NO_MARGIN",
            "NOT_ADJUDICATED_NO_HOLM", "NOT_ADJUDICATED_NO_FLOOR", "NOT_AVAILABLE",
            "PASS_BY_CONSTRUCTION", "VOID", "VOID_CLOSED")

UNCONDITIONAL_BASIS = (
    "Every criterion in this battery is scored on `war_provider = fwar`. The "
    "champion-versus-challenger numbers in `data/proj_horizon_eval.json` (2026-08-19) "
    "and every cell of `data/proj_calibration_eval.json` (2026-07-25) predate the fWAR "
    "label epoch (docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md) and are priors, not "
    "comparators. Label seasons 2015 through 2025 were already scored on the shipped "
    "challenger by `challenger_blocks.gate1_targets` and carry no confirming verdict here.")
UNCONDITIONAL_ROUGHNESS = (
    "An absent season is scored as 0.0 WAR, so the expected path of a population whose "
    "survival probability decays is genuinely not smooth in age. Part of the roughness "
    "removed here is attrition signal, and the accuracy column is what prices that. RS2 "
    "falls by construction under a second-difference penalty and no verdict here turns "
    "on it in the passing direction.")
UNCONDITIONAL_TWO_WAY = (
    "The served two-way population is one player. Each side's model estimates the "
    "player's TOTAL WAR given that side's line, so the two sides are two estimates of "
    "one quantity, and no claim about two-way accuracy is supported by this battery in "
    "either direction. The served two-way `war` sum carries no workload discount and no "
    "clause here adjudicates that.")
UNCONDITIONAL_TRANSPORT = (
    "The verdict-bearing frame is label seasons 2012-2014, and the served population is "
    "2027. Transport across that gap is disclosed, not demonstrated.")
L1_DISCLOSURE = (
    "The LIVE served bundle carries no two-sided exclusion, so this gate measures a "
    "contrast between two consistently built arms and does not measure the served "
    "bundle's absolute level.")
EARLY_READ = ("OWNER-WAIVED EARLY READ (owner EW3-5, 2026-10-14, verbatim: 'Fuck the "
              "registered look days and waiting, we don't have to wait for anything. "
              "Let's do everything today')")

JOINT_PARAMS = {
    "n_estimators": 400, "learning_rate": 0.05, "num_leaves": 31,
    "min_child_samples": 60, "subsample": 0.9, "subsample_freq": 1,
    "colsample_bytree": 0.9, "reg_lambda": 1.0, "deterministic": True,
    "force_row_wise": True, "n_jobs": 1, "random_state": SEED_FIT, "verbose": -1,
}

# DRY-RUN MODE, the reporting path rehearsed on a fixture before a look (the Part 8
# LOOKS rule). With PROJ_SHAPE_GATE_FIXTURE=1 every head is fitted with 12 trees so
# the whole path runs in minutes on a fixture frame whose labels are synthetic. It is
# never set for a registered run: every stage and the artifact record the mode, and
# test_proj_shape_gate.py pins that the committed artifacts were not written in it.
FIXTURE = os.environ.get("PROJ_SHAPE_GATE_FIXTURE") == "1"


def _fx(params: dict) -> dict:
    return {**params, "n_estimators": 12} if FIXTURE else params


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def frame_of_label(label: int) -> str | None:
    if label in DEV_LABELS:
        return "DEV"
    if label in GATE_LABELS:
        return "GATE"
    if label in CONFIRM_LABELS:
        return "CONFIRM"
    if label in TIER2_LABELS:
        return "TIER2"
    return None


FRAME_LABELS = {"DEV": DEV_LABELS, "GATE": GATE_LABELS, "CONFIRM": CONFIRM_LABELS,
                "TIER2": TIER2_LABELS}


# ---------------------------------------------------------------- environment
_ENV: dict = {}


def setup(work: Path, corpus_path: Path | None = None) -> dict:
    """Repoint every cache this battery could write at the private work directory,
    then load the pinned corpus. Called once per process."""
    if _ENV.get("work") == str(work):
        return _ENV["corpus"]
    import fa_projection as fp
    work = Path(work)
    (work / "cache").mkdir(parents=True, exist_ok=True)
    pinned = work / "fa_corpus.pkl"
    if not pinned.exists():
        if corpus_path is None:
            raise SystemExit("no pinned corpus in the work directory")
        shutil.copyfile(corpus_path, pinned)
    xs = work / "cache" / "xstats.pkl"
    if not xs.exists():
        src = fp.CACHE_DIR / "xstats.pkl"
        if src.exists():
            shutil.copyfile(src, xs)
    fp.CACHE_DIR = work / "cache"
    fp._XSTATS_CACHE = xs
    with open(pinned, "rb") as fh:
        corpus = pickle.load(fh)
    if corpus.get("war_provider") != "fwar":
        raise SystemExit("corpus war_provider %r, A-2 requires fwar" % corpus.get("war_provider"))
    if corpus.get("label_shape") != fp.LABEL_SHAPE:
        raise SystemExit("corpus label_shape %r" % corpus.get("label_shape"))
    _ENV.update(work=str(work), corpus=corpus)
    return corpus


def corpus_stamp(work: Path) -> dict:
    corpus = _ENV["corpus"]
    return {"path": "work/fa_corpus.pkl (copied from .cache/fa_corpus.pkl)",
            "sha256": sha256_file(Path(work) / "fa_corpus.pkl"),
            "first": corpus["first"], "last": corpus["last"],
            "war_provider": corpus.get("war_provider"),
            "label_shape": corpus.get("label_shape"),
            "n_hit_rows": len(corpus["hit"]), "n_pit_rows": len(corpus["pit"])}


def two_sided_set(corpus: dict) -> set:
    hit = {(r["mlbam"], r["season"]) for r in corpus["hit"] if r.get("mlbam")}
    pit = {(r["mlbam"], r["season"]) for r in corpus["pit"] if r.get("mlbam")}
    return hit & pit


# ---------------------------------------------------------------- the frame
def _frame_chunk(args) -> dict:
    """Rows for the given bases, built exactly as proj_ml.build_training_frame
    builds them, plus the identity and class columns the scorer needs."""
    work, bases = args
    corpus = setup(Path(work))
    import fa_projection as fp
    import proj_ml
    league = corpus["league"]
    by_player = {"hit": {}, "pit": {}}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side].setdefault(r["mlbam"], {})[r["season"]] = r
    out = {s: {"X": [], "mlbam": [], "base": [], "role": [], "pt": []}
           for s in ("hit", "pit")}
    for side in ("hit", "pit"):
        o = out[side]
        for base in bases:
            curves, war_map = fp.fitted_models(corpus, base - 1, aging="v2")
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (base - 1, base - 2, base - 3) if t in seasons]
                if not hist:
                    continue
                age = proj_ml.age_from_history(hist, base)
                if age is None:
                    continue
                feats = proj_ml.build_features(hist, side, base, age, curves, war_map, league)
                if feats is None:
                    continue
                proj = fp.project_player(hist, side, base, curves, league, age) or {}
                o["X"].append(feats)
                o["mlbam"].append(mlbam)
                o["base"].append(base)
                o["role"].append(proj.get("role") or "?")
                o["pt"].append(float(proj.get("pt_proj") or 0.0))
    return out


def build_frame(work: Path, procs: int = 8) -> dict:
    from multiprocessing import Pool
    corpus = setup(work)
    bases = list(range(FIRST_BASE, LAST_COMPLETE + 1))
    jobs = [(str(work), [b]) for b in bases]
    t0 = time.time()
    with Pool(procs) as pool:
        chunks = pool.map(_frame_chunk, jobs)
    import fa_projection as fp
    war_actual = fp.war_actual_map(corpus)
    ts = two_sided_set(corpus)
    F = {"meta": {"built_at": utc_now(), "wall_s": round(time.time() - t0, 1),
                  "bases": bases, "corpus": corpus_stamp(work)}}
    import proj_ml
    for side in ("hit", "pit"):
        X, mb, bs, role, pt = [], [], [], [], []
        for c in chunks:
            X += c[side]["X"]; mb += c[side]["mlbam"]; bs += c[side]["base"]
            role += c[side]["role"]; pt += c[side]["pt"]
        X = np.asarray(X, dtype=float)
        bs = np.asarray(bs, dtype=int)
        n = len(bs)
        Y = np.full((n, HORIZONS), np.nan)
        surv = np.zeros((n, HORIZONS), dtype=bool)
        excl_cell = np.zeros((n, HORIZONS), dtype=bool)
        excl_row = np.zeros(n, dtype=bool)
        star = np.zeros(n, dtype=bool)
        for i in range(n):
            m, B = mb[i], int(bs[i])
            ba = war_actual.get((m, B - 1))
            star[i] = ba is not None and ba >= 4.0
            excl_row[i] = (m, B - 1) in ts
            for h in range(1, HORIZONS + 1):
                t = B + h - 1
                excl_cell[i, h - 1] = (m, t) in ts
                if t <= LAST_COMPLETE:
                    Y[i, h - 1] = war_actual.get((m, t), 0.0)
                    surv[i, h - 1] = (m, t) in war_actual
        F[side] = {"X": X, "mlbam": np.asarray(mb, dtype=np.int64), "base": bs,
                   "role": np.asarray(role), "pt": np.asarray(pt, dtype=float),
                   "Y": Y, "survived": surv, "star": star,
                   "excl_row": excl_row, "excl_cell": excl_cell,
                   "features": proj_ml.feature_names(side)}
    with open(Path(work) / "frame.pkl", "wb") as fh:
        pickle.dump(F, fh, protocol=4)
    return F


_FRAME: dict = {}


def load_frame(work: Path) -> dict:
    """The frame, loaded once per process. With PROJ_SHAPE_LABEL_CEILING set (the
    power lab sets it to 2011 before any process starts, 3.1), every label and
    survival flag whose label season lies above the ceiling is blanked on load, so a
    GATE, CONFIRM or Tier-2 label is not present in that process at all."""
    key = str(work)
    if key not in _FRAME:
        with open(Path(work) / "frame.pkl", "rb") as fh:
            F = pickle.load(fh)
        cap = os.environ.get("PROJ_SHAPE_LABEL_CEILING")
        if cap:
            cap = int(cap)
            for side in ("hit", "pit"):
                f = F[side]
                over = label_seasons(f) > cap
                f["Y"] = np.where(over, np.nan, f["Y"])
                f["survived"] = f["survived"] & ~over
            F["meta"]["label_ceiling"] = cap
        _FRAME[key] = F
    return _FRAME[key]


def valid_cells(f: dict) -> np.ndarray:
    """(n, 5) bool: label known (<= LAST_COMPLETE) and not two-sided (D1)."""
    return (~np.isnan(f["Y"])) & (~f["excl_cell"]) & (~f["excl_row"][:, None])


def label_seasons(f: dict) -> np.ndarray:
    return f["base"][:, None] + np.arange(HORIZONS)[None, :]


def cell_mask(f: dict, frame: str) -> np.ndarray:
    """(n, 5) bool cells of a named frame (4.6): evaluation bases from 2008, label
    season in the frame's set, valid."""
    ls = label_seasons(f)
    inset = np.isin(ls, FRAME_LABELS[frame])
    return inset & (f["base"][:, None] >= EVAL_FIRST_BASE) & valid_cells(f)


# ---------------------------------------------------------------- fitting
def assert_point_in_time(train_label_max: int, B: int) -> None:
    if train_label_max > B - 1:
        raise AssertionError("leak 1: a bundle scored at base %d trained on label %d"
                             % (B, train_label_max))


def _train_cells(f: dict, B: int, rows_weight: np.ndarray | None = None) -> np.ndarray:
    ls = label_seasons(f)
    return valid_cells(f) & (ls <= B - 1)


def fit_s(F: dict, B: int, weights: dict | None = None,
          horizons: tuple = tuple(range(1, HORIZONS + 1))) -> dict:
    """S: proj_lgbm_v1's fifty heads at labels <= B - 1 (train()'s recipe: one model
    per side, horizon and quantile, _params_for(h), a horizon skipped below 500
    rows), under the L1 exclusion. `weights` (bootstrap row multiplicities per side)
    duplicates rows, which is the resampling the full-refit draw needs."""
    import proj_ml
    from lightgbm import LGBMRegressor
    out = {"arm": "S", "B": B, "heads": {}}
    for side in ("hit", "pit"):
        f = F[side]
        tc = _train_cells(f, B)
        out["heads"][side] = {}
        for h in horizons:
            idx = np.flatnonzero(tc[:, h - 1])
            if weights is not None:
                idx = np.repeat(idx, weights[side][idx])
            if len(idx) < 500:
                continue
            assert_point_in_time(int(f["base"][idx].max() + h - 1), B)
            Xh, yh = f["X"][idx], f["Y"][idx, h - 1]
            out["heads"][side][h] = {}
            for q in QUANTILES:
                mdl = LGBMRegressor(alpha=q, **_fx(proj_ml._params_for(h)))
                mdl.fit(Xh, yh)
                out["heads"][side][h][q] = mdl.booster_.model_to_string()
    return out


def _long(f: dict, idx: np.ndarray, hs: np.ndarray) -> np.ndarray:
    X = f["X"][idx]
    age = f["X"][idx, 0]
    return np.hstack([X, hs[:, None].astype(float), (age + hs - 1)[:, None]])


def make_objective(q: float, lam: float, prv: np.ndarray, nxt: np.ndarray):
    """pinball_q + lam * sum of squared second differences over every triple of
    consecutive horizons present in a player-base group (4.1 item 3). Pinball's
    pseudo-Hessian is 1.0; the penalty's Hessian is exact and diagonal: 2 * lam per
    triple at each endpoint and 8 * lam at its centre, which is lam * [2, 10, 12,
    10, 2] on a complete five-horizon group."""
    n = len(prv)
    c = np.flatnonzero((prv >= 0) & (nxt >= 0))
    a, b = prv[c], nxt[c]
    hess = np.ones(n)
    if lam > 0 and len(c):
        np.add.at(hess, c, 8.0 * lam)
        np.add.at(hess, a, 2.0 * lam)
        np.add.at(hess, b, 2.0 * lam)

    def obj(y_true, y_pred):
        g = np.where(y_pred > y_true, 1.0 - q, -q)
        if lam > 0 and len(c):
            d = y_pred[b] - 2.0 * y_pred[c] + y_pred[a]
            gp = np.zeros(n)
            np.add.at(gp, c, -4.0 * lam * d)
            np.add.at(gp, a, 2.0 * lam * d)
            np.add.at(gp, b, 2.0 * lam * d)
            g = g + gp
        return g, hess
    return obj


def penalty_census(prv: np.ndarray, nxt: np.ndarray, grp: np.ndarray) -> dict:
    groups = len(np.unique(grp))
    centres = int(((prv >= 0) & (nxt >= 0)).sum())
    has_triple = len(np.unique(grp[(prv >= 0) & (nxt >= 0)]))
    return {"groups": groups, "groups_with_a_triple": has_triple,
            "groups_without_a_triple_kept_full_pinball": groups - has_triple,
            "triples": centres}


def fit_joint(F: dict, B: int, lam: float, weights: dict | None = None) -> dict:
    """ARM A's joint shape at one lambda: ten heads (side x quantile) on the long
    frame, the custom objective of 4.1 item 3, the 4.1a hyperparameters exactly.
    lam = 0 is A0. Short groups are kept (L8)."""
    from lightgbm import LGBMRegressor
    out = {"arm": "J%.2f" % lam, "lam": lam, "B": B, "heads": {}, "census": {}}
    for side in ("hit", "pit"):
        f = F[side]
        tc = _train_cells(f, B)
        rows, hs = np.nonzero(tc)
        hs = hs + 1
        if weights is not None:
            rep = weights[side][rows]
            # a resampled player keeps his groups intact: each copy is its own group
            grp_src = np.repeat(np.arange(len(rows)), rep)
            rows, hs = rows[grp_src], hs[grp_src]
            copy_id = np.concatenate([np.arange(k) for k in rep]) if len(rep) else np.zeros(0, int)
        else:
            copy_id = np.zeros(len(rows), dtype=int)
        if len(rows) == 0:
            out["heads"][side] = {}
            continue
        assert_point_in_time(int((f["base"][rows] + hs - 1).max()), B)
        # group key (row, copy): order by group then horizon
        order = np.lexsort((hs, copy_id, rows))
        rows, hs, copy_id = rows[order], hs[order], copy_id[order]
        gkey = rows.astype(np.int64) * 1000 + copy_id
        prv = np.full(len(rows), -1)
        nxt = np.full(len(rows), -1)
        same = (gkey[1:] == gkey[:-1]) & (hs[1:] == hs[:-1] + 1)
        j = np.flatnonzero(same)
        nxt[j] = j + 1
        prv[j + 1] = j
        Xl = _long(f, rows, hs)
        yl = f["Y"][rows, hs - 1]
        out["census"][side] = penalty_census(prv, nxt, gkey)
        out["census"][side]["long_rows"] = int(len(rows))
        out["heads"][side] = {}
        for q in QUANTILES:
            mdl = LGBMRegressor(objective=make_objective(q, lam, prv, nxt), **_fx(JOINT_PARAMS))
            mdl.fit(Xl, yl)
            out["heads"][side][q] = mdl.booster_.model_to_string()
    return out


def _boosters(bundle: dict) -> dict:
    """The bundle's LightGBM Boosters, parsed once per loaded bundle and released
    with it: {(side, h, q): Booster} for S, {(side, None, q): Booster} for a joint
    bundle. (A module-level cache keyed on the model strings kept every bundle of a
    run alive at once, several GB for the S series alone.)"""
    import lightgbm as lgb
    bs = bundle.get("_boosters")
    if bs is None:
        bs = {}
        for side, heads in (bundle.get("heads") or {}).items():
            for k, v in heads.items():
                if isinstance(v, dict):
                    for q, s in v.items():
                        bs[(side, k, q)] = lgb.Booster(model_str=s)
                else:
                    bs[(side, None, k)] = lgb.Booster(model_str=v)
        bundle["_boosters"] = bs
    return bs


def q_matrix(bundle: dict, side: str, X: np.ndarray, h: int) -> np.ndarray | None:
    """(n, 5) raw head outputs at horizon h for the base-feature matrix X, unsorted;
    None when the bundle has no head there (S skips a horizon below 500 rows)."""
    bs = _boosters(bundle)
    out = np.empty((len(X), len(QUANTILES)))
    if bundle["arm"] == "S":
        if (side, h, QUANTILES[0]) not in bs:
            return None
        for k, q in enumerate(QUANTILES):
            out[:, k] = bs[(side, h, q)].predict(X)
        return out
    if (side, None, QUANTILES[0]) not in bs:
        return None
    Xl = np.hstack([X, np.full((len(X), 1), float(h)), (X[:, 0] + h - 1)[:, None]])
    for k, q in enumerate(QUANTILES):
        out[:, k] = bs[(side, None, q)].predict(Xl)
    return out


def predict_raw(bundle: dict, F: dict, side: str, idx: np.ndarray,
                ceiling: int) -> np.ndarray:
    """(len(idx), 5 horizons, 5 quantiles) raw head outputs, sorted across
    quantiles per cell (the monotone sort, no zero floor); NaN where the cell's label
    season exceeds `ceiling` or the head was not trained. `ceiling` is how the MDE
    lab is kept off every frame but DEV."""
    f = F[side]
    out = np.full((len(idx), HORIZONS, len(QUANTILES)), np.nan)
    if not len(idx):
        return out
    for h in range(1, HORIZONS + 1):
        sel = np.flatnonzero(f["base"][idx] + h - 1 <= ceiling)
        if not len(sel):
            continue
        Qh = q_matrix(bundle, side, f["X"][idx[sel]], h)
        if Qh is not None:
            out[sel, h - 1, :] = Qh
    out.sort(axis=2)
    return out


# ---------------------------------------------------------------- blends
def implied_mean(Q: np.ndarray, q50: np.ndarray | None = None) -> np.ndarray:
    q50 = Q[..., 2] if q50 is None else q50
    return (Q[..., 0] + 2 * Q[..., 1] + 2 * q50 + 2 * Q[..., 3] + Q[..., 4]) / 8.0


def compose(Q: np.ndarray, star_flag: np.ndarray, lam_m: dict, lam_s: dict) -> dict:
    """proj_ml.predict_path's composition on raw sorted quantiles: the lift-only
    global mean blend, then the star top-up on star_l1 rows (its implied mean reads
    the mean-blended q50, as predict_path's does), rounded to 0.01 as served."""
    q50 = Q[..., 2].copy()
    for t in range(HORIZONS):
        lm = float(lam_m.get(t + 1, 0.0))
        if lm > 0:
            shift = lm * (implied_mean(Q[:, t, :]) - q50[:, t])
            q50[:, t] = np.where(shift > 0, q50[:, t] + shift, q50[:, t])
    for t in range(HORIZONS):
        ls = float(lam_s.get(t + 1, 0.0))
        if ls > 0:
            mean1 = implied_mean(Q[:, t, :], q50[:, t])
            q50[:, t] = np.where(star_flag, q50[:, t] + ls * (mean1 - q50[:, t]), q50[:, t])
    return {"c": np.round(q50, 2), "p10": np.round(Q[..., 0], 2),
            "p90": np.round(Q[..., 4], 2)}


def star_flag(f: dict, idx: np.ndarray) -> np.ndarray:
    import proj_ml
    return f["X"][idx, proj_ml._STAR_FLAG_IDX] >= 1.0


def champ_central(f: dict, idx: np.ndarray) -> np.ndarray:
    return f["X"][idx][:, -HORIZONS:]


def fit_blends(F: dict, oof: dict, B: int, weights: dict | None = None) -> dict:
    """D2 to D4: point-in-time mean and star lambdas for an arm scored at base B,
    from that arm's out-of-fold predictions at every earlier base whose cells carry
    labels <= B - 1. `oof` is {base: {side: (idx, Q)}}."""
    lam_m, lam_s, lam_s_fit, table = {}, {}, {}, {}
    pools = {h: {"Q": [], "y": [], "ch": [], "st": []} for h in range(1, HORIZONS + 1)}
    for Bp, sides in oof.items():
        if Bp >= B:
            continue
        for side, (idx, Q) in sides.items():
            f = F[side]
            ok = valid_cells(f)[idx]
            for h in range(1, HORIZONS + 1):
                if Bp + h - 1 > B - 1:
                    continue
                s = ok[:, h - 1] & ~np.isnan(Q[:, h - 1, 2])
                if not s.any():
                    continue
                r = idx[s]
                rep = None if weights is None else weights[side][r]
                take = (lambda a: a) if rep is None else (lambda a: np.repeat(a, rep, axis=0))
                pools[h]["Q"].append(take(Q[s, h - 1, :]))
                pools[h]["y"].append(take(f["Y"][r, h - 1]))
                pools[h]["ch"].append(take(champ_central(f, r)[:, h - 1]))
                pools[h]["st"].append(take(star_flag(f, r)))
    for h in range(1, HORIZONS + 1):
        p = pools[h]
        if p["Q"] and not sum(len(a) for a in p["y"]):
            p["Q"] = []
        if not p["Q"]:
            lam_m[h], lam_s[h], lam_s_fit[h] = 0.0, 0.0, 0.0
            table[h] = {"n": 0}
            continue
        Q = np.vstack(p["Q"]); y = np.concatenate(p["y"])
        ch = np.concatenate(p["ch"]); st = np.concatenate(p["st"])
        champ_mae = float(np.mean(np.abs(ch - y)))
        mean0 = implied_mean(Q)
        best = None
        for lam in MEAN_GRID:
            shift = lam * (mean0 - Q[:, 2])
            c = np.where(shift > 0, Q[:, 2] + shift, Q[:, 2])
            mae = float(np.mean(np.abs(c - y)))
            bias = float(np.mean(c - y))
            if mae < champ_mae and (best is None or abs(bias) < abs(best[1]) - 1e-12
                                    or (abs(abs(bias) - abs(best[1])) <= 1e-12 and lam > best[0])):
                best = (lam, bias, mae)
        lm = best[0] if best else 0.0
        shift = lm * (mean0 - Q[:, 2])
        q50m = np.where(shift > 0, Q[:, 2] + shift, Q[:, 2])
        ls_fit = 0.0
        if st.any():
            Qs, ys, q50s = Q[st], y[st], q50m[st]
            mean1 = implied_mean(Qs, q50s)
            base_bias = float(np.mean(q50s - ys)); base_mae = float(np.mean(np.abs(q50s - ys)))
            bb = (0.0, base_bias, base_mae)
            for lam in STAR_GRID[1:]:
                pp = q50s + lam * (mean1 - q50s)
                bias = float(np.mean(pp - ys)); mae = float(np.mean(np.abs(pp - ys)))
                if mae <= base_mae + STAR_GUARD and abs(bias) < abs(bb[1]):
                    bb = (lam, bias, mae)
            ls_fit = bb[0]
        lam_m[h] = lm
        lam_s_fit[h] = ls_fit
        lam_s[h] = 0.0 if h in DENIED_STAR_H else ls_fit
        table[h] = {"n": int(len(y)), "n_star": int(st.sum()),
                    "champion_mae": round(champ_mae, 4)}
    return {"mean": lam_m, "star": lam_s, "star_fitted": lam_s_fit, "pool": table}


# ---------------------------------------------------------------- bundles on disk
def bundle_path(work: Path, arm: str, B: int, tag: str = "") -> Path:
    return Path(work) / "bundles" / (arm + tag) / ("%d.pkl" % B)


def arm_name(lam: float | None) -> str:
    return "S" if lam is None else "J%.2f" % lam


def get_bundle(work: Path, F: dict, arm: str, B: int) -> dict:
    p = bundle_path(work, arm, B)
    if p.exists():
        with open(p, "rb") as fh:
            return pickle.load(fh)
    t0 = time.time()
    if arm == "S":
        b = fit_s(F, B)
    else:
        b = fit_joint(F, B, float(arm[1:]))
    b["fit_wall_s"] = round(time.time() - t0, 1)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(b, fh, protocol=4)
    os.replace(tmp, p)
    return b


def _bundle_job(args):
    work, arm, B = args
    setup(Path(work))
    F = load_frame(Path(work))
    b = get_bundle(Path(work), F, arm, B)
    return arm, B, b.get("fit_wall_s")


def ensure_bundles(work: Path, jobs: list, procs: int = 8) -> list:
    """Fit every (arm, B) not yet on disk, in parallel processes (each fit is
    single-threaded and deterministic, so the parallelism changes no number)."""
    todo = [(str(work), a, B) for a, B in jobs if not bundle_path(work, a, B).exists()]
    if not todo:
        return []
    from multiprocessing import Pool
    # largest fits first
    todo.sort(key=lambda j: (-j[2], j[1]))
    with Pool(min(procs, len(todo))) as pool:
        return list(pool.imap_unordered(_bundle_job, todo))


def oof_for(work: Path, F: dict, arm: str, bases, ceiling: int) -> dict:
    """{B: {side: (idx, Q)}}: each base's own rows predicted by the bundle fitted at
    that base (labels <= B - 1), cells above `ceiling` left NaN."""
    out = {}
    for B in bases:
        b = get_bundle(work, F, arm, B)
        out[B] = {}
        for side in ("hit", "pit"):
            idx = np.flatnonzero(F[side]["base"] == B)
            out[B][side] = (idx, predict_raw(b, F, side, idx, ceiling))
    return out


# ---------------------------------------------------------------- scoring
def scored(F: dict, arm_preds: dict, frame: str, ceiling: int, bases=None) -> dict:
    """Flatten the cells of `frame` scored by every arm in `arm_preds`
    ({arm: {B: {side: (idx, composed)}}}): arrays aligned across arms, row-matched
    by construction (S7). Raises if any arm lacks a prediction on a cell."""
    cols = defaultdict(list)
    arms = list(arm_preds)
    for side in ("hit", "pit"):
        f = F[side]
        cm = cell_mask(f, frame) & (label_seasons(f) <= ceiling)
        for B in sorted({int(b) for b in f["base"][cm.any(axis=1)]}):
            if bases is not None and B not in bases:
                continue
            idx = np.flatnonzero((f["base"] == B) & cm.any(axis=1))
            if not len(idx):
                continue
            for h in range(1, HORIZONS + 1):
                s = cm[idx, h - 1]
                if not s.any():
                    continue
                r = idx[s]
                cols["side"] += [side] * len(r)
                cols["mlbam"].append(f["mlbam"][r])
                cols["base"].append(np.full(len(r), B))
                cols["h"].append(np.full(len(r), h))
                cols["y"].append(f["Y"][r, h - 1])
                cols["star"].append(f["star"][r])
                cols["champ"].append(champ_central(f, r)[:, h - 1])
                cols["age_t"].append(f["X"][r, 0] + h - 1)
                cols["role"].append(f["role"][r])
                cols["pt"].append(f["pt"][r])
                cols["survived"].append(f["survived"][r, h - 1])
                cols["row"].append(r)
                for a in arms:
                    pidx, comp = arm_preds[a][B][side]
                    pos = np.searchsorted(pidx, r)
                    if not (np.all(pos < len(pidx)) and np.all(pidx[pos] == r)):
                        raise AssertionError("S7: arm %s lacks rows at base %d" % (a, B))
                    for k in ("c", "p10", "p90"):
                        v = comp[k][pos, h - 1]
                        if np.isnan(v).any():
                            raise AssertionError("S7: arm %s has no %s at base %d h%d"
                                                 % (a, k, B, h))
                        cols["%s:%s" % (a, k)].append(v)
    out = {}
    for k, v in cols.items():
        out[k] = np.asarray(v) if k == "side" else (np.concatenate(v) if v else np.zeros(0))
    return out


def stats_block(S: dict, arm: str, sel: np.ndarray | None = None) -> dict:
    """Per horizon and pooled: n, MAE, signed bias, P10-P90 coverage, pinball q10/q90,
    star-slice (ex-ante base WAR >= 4) MAE and bias."""
    sel = np.ones(len(S["y"]), dtype=bool) if sel is None else sel
    c, p10, p90 = S[arm + ":c"], S[arm + ":p10"], S[arm + ":p90"]
    y = S["y"]

    def blk(m):
        if not m.any():
            return {"n": 0}
        e = c[m] - y[m]
        d10 = y[m] - p10[m]
        d90 = y[m] - p90[m]
        st = m & S["star"]
        es = c[st] - y[st]
        return {"n": int(m.sum()), "mae": round(float(np.mean(np.abs(e))), 4),
                "bias": round(float(np.mean(e)), 4),
                "coverage": round(float(np.mean((p10[m] <= y[m]) & (y[m] <= p90[m]))), 4),
                "pinball_q10": round(float(np.mean(np.where(d10 >= 0, 0.1 * d10, -0.9 * d10))), 4),
                "pinball_q90": round(float(np.mean(np.where(d90 >= 0, 0.9 * d90, -0.1 * d90))), 4),
                "n_star": int(st.sum()),
                "mae_star": round(float(np.mean(np.abs(es))), 4) if st.any() else None,
                "bias_star": round(float(np.mean(es)), 4) if st.any() else None}
    out = {"pooled": blk(sel), "by_h": {}}
    for h in range(1, HORIZONS + 1):
        out["by_h"][str(h)] = blk(sel & (S["h"] == h))
    return out


def player_index(S: dict) -> tuple[np.ndarray, int]:
    u, inv = np.unique(S["mlbam"], return_inverse=True)
    return inv, len(u)


def cluster_boot(S: dict, num: np.ndarray, den: np.ndarray, draws: int, seed: int,
                 sel: np.ndarray | None = None) -> np.ndarray:
    """Cluster (player) bootstrap of sum(num)/sum(den) over the selected cells."""
    sel = np.ones(len(num), dtype=bool) if sel is None else sel
    inv, P = player_index(S)
    pn = np.bincount(inv[sel], weights=num[sel], minlength=P)
    pd = np.bincount(inv[sel], weights=den[sel], minlength=P)
    have = np.flatnonzero(pd > 0)
    pn, pd = pn[have], pd[have]
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    k = len(have)
    for i in range(draws):
        w = np.bincount(rng.integers(0, k, k), minlength=k)
        dsum = float(w @ pd)
        out[i] = float(w @ pn) / dsum if dsum else np.nan
    return out


def n_players(S: dict, sel: np.ndarray | None = None) -> int:
    sel = np.ones(len(S["y"]), dtype=bool) if sel is None else sel
    return int(len(np.unique(S["mlbam"][sel])))


def paired_delta(S: dict, a: str, b: str, kind: str = "mae", h: int | None = None,
                 star: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Per-cell numerator for delta = stat(a) - stat(b), and its denominator."""
    sel = np.ones(len(S["y"]), dtype=bool)
    if h is not None:
        sel &= S["h"] == h
    if star:
        sel &= S["star"]
    y = S["y"]
    if kind == "mae":
        v = np.abs(S[a + ":c"] - y) - np.abs(S[b + ":c"] - y)
    elif kind == "bias":
        v = (S[a + ":c"] - y) - (S[b + ":c"] - y)
    elif kind == "coverage":
        v = (((S[a + ":p10"] <= y) & (y <= S[a + ":p90"])).astype(float)
             - ((S[b + ":p10"] <= y) & (y <= S[b + ":p90"])).astype(float))
    elif kind in ("pinball_q10", "pinball_q90"):
        q, k = (0.1, "p10") if kind == "pinball_q10" else (0.9, "p90")

        def pb(x):
            d = y - x
            return np.where(d >= 0, q * d, (q - 1) * d)
        v = pb(S[a + ":" + k]) - pb(S[b + ":" + k])
    else:
        raise ValueError(kind)
    return np.where(sel, v, 0.0), sel.astype(float)


def boot_sd(S: dict, num: np.ndarray, den: np.ndarray, draws: int = B_TEST,
            seed: int = SEED_BOOT) -> float:
    d = cluster_boot(S, num, den, draws, seed)
    return float(np.nanstd(d, ddof=1))


# ---------------------------------------------------------------- roughness (4.5)
def rs2_uaf(paths: list[list[float]]) -> dict:
    """RS2 (per-path RMS second difference over h1..h5, mean and median), UAF (the
    up-after-a-fall step rate) and RAF (the rise-after-a-fall path count)."""
    rs, ups, steps, raf = [], 0, 0, 0
    for w in paths:
        d2 = [(w[t + 1] - 2 * w[t] + w[t - 1]) ** 2 for t in range(1, 4)]
        rs.append(math.sqrt(sum(d2) / 3.0))
        fallen, rose_after = False, False
        for t in range(4):
            if fallen:
                steps += 1
                if w[t + 1] > w[t]:
                    ups += 1
                    rose_after = True
            else:
                steps += 1
            if w[t + 1] < w[t]:
                fallen = True
        raf += rose_after
    rs_sorted = sorted(rs)
    n = len(rs)
    med = (rs_sorted[n // 2] if n % 2 else 0.5 * (rs_sorted[n // 2 - 1] + rs_sorted[n // 2])) if n else None
    return {"pool": n, "rs2_mean": round(sum(rs) / n, 4) if n else None,
            "rs2_median": round(med, 4) if n else None,
            "uaf_up": ups, "uaf_steps": steps,
            "uaf": round(ups / steps, 4) if steps else None, "raf": raf}


def served_pool(rows: list[dict], key: str) -> list[list[float]]:
    out = []
    for m in rows:
        w = m.get(key)
        if not w or len(w) < HORIZONS or any(x is None for x in w[:HORIZONS]):
            continue
        w = [float(x) for x in w[:HORIZONS]]
        if w[0] >= 1.0:
            out.append(w)
    return out


# ---------------------------------------------------------------- the serving replica
def serving_inputs(served_rows: list[dict]) -> dict:
    """The served veteran population at FIRST_SEASON, rebuilt from the pinned corpus
    exactly as proj_export._veteran_rows builds each side's path inputs: history
    seasons FIRST_SEASON-1..-3, the MIN_PA / MIN_IP filter, fitted_models at
    FIRST_SEASON - 1, the in-progress tuple. Returns per (mlbam, side): hist, age,
    the champion path and the stack features."""
    import fa_market as fm
    import fa_projection as fp
    import proj_export as pe
    import proj_ml
    corpus = _ENV["corpus"]
    league = corpus["league"]
    FS = pe.FIRST_SEASON
    curves, war_map = fp.fitted_models(corpus, FS - 1)
    frac = fp.season_fraction(league, FS - 1)
    in_prog = (FS - 1, frac)
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            if row.get("mlbam") and row["season"] >= FS - 3:
                by_player[side][row["mlbam"]][row["season"]] = row
    out = {}
    for m in served_rows:
        mlbam = m.get("mlbam")
        sides = {}
        for side in ("hit", "pit"):
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (FS - 1, FS - 2, FS - 3) if t in seasons]
            if not hist:
                continue
            if side == "hit":
                if max(h.get("pa") or 0 for h in hist) < pe.MIN_PA:
                    continue
            elif max(h.get("ip") or 0 for h in hist) < pe.MIN_IP:
                continue
            age_row = next((h for h in hist if h.get("age")), None)
            if age_row is None:
                continue
            age = age_row["age"] + (FS - age_row["season"])
            champ = fm.contract_war_path(hist, side, FS, pe.HORIZON, age, curves,
                                         war_map, league, in_progress=in_prog,
                                         use_ml=False)
            if champ is None:
                continue
            feats = proj_ml.build_features(hist, side, FS, age, curves, war_map,
                                           league, champ=champ, in_progress=in_prog)
            sides[side] = {"hist": hist, "age": age, "champ": champ, "feats": feats}
        if sides:
            out[mlbam] = sides
    return {"rows": out, "first_season": FS, "season_fraction": frac}


def serve_live_war(inp: dict) -> dict:
    """{mlbam: five-season `war`} through the LIVE bundle (proj_ml.predict_path on the
    shipped model), summed across sides as proj_export sums a two-way row."""
    import proj_ml
    live = proj_ml.load()
    res = {}
    for mlbam, sides in inp["rows"].items():
        arr = []
        for side, d in sides.items():
            ml = proj_ml.predict_path(live, d["feats"], side) if d["feats"] else None
            arr.append(ml["war_by_year"][:HORIZONS] if ml else d["champ"]["war_by_year"][:HORIZONS])
        res[mlbam] = [round(sum(a[t] for a in arr), 2) for t in range(HORIZONS)]
    return res


def serve_bundle_war(inp: dict, bundle: dict, blends: dict) -> dict:
    """{mlbam: five-season `war`} through a gate bundle (S or joint) and its blends,
    on the same inputs, both sides summed."""
    res = {}
    for mlbam, sides in inp["rows"].items():
        arr = []
        for side, d in sides.items():
            feats = d["feats"]
            if feats is None:
                arr.append(d["champ"]["war_by_year"][:HORIZONS])
                continue
            x = np.asarray(feats, dtype=float)[None, :]
            Q = np.full((1, HORIZONS, len(QUANTILES)), np.nan)
            for h in range(1, HORIZONS + 1):
                Qh = q_matrix(bundle, side, x, h)
                if Qh is None:
                    break
                Q[0, h - 1, :] = Qh[0]
            if np.isnan(Q).any():
                arr.append(d["champ"]["war_by_year"][:HORIZONS])
                continue
            Q.sort(axis=2)
            import proj_ml
            sf = np.array([feats[proj_ml._STAR_FLAG_IDX] >= 1.0])
            comp = compose(Q, sf, blends["mean"], blends["star"])
            arr.append([float(v) for v in comp["c"][0]])
        res[mlbam] = [round(sum(a[t] for a in arr), 2) for t in range(HORIZONS)]
    return res


def stack_share(bundle: dict, blends: dict, inp: dict, seed: int = SEED_FIT) -> dict:
    """Tripwire 2 (4.5): the share of an arm's central-path prediction variance
    attributable to champ_h1..champ_h5, by permutation importance over those five
    columns permuted together across rows (seed SEED_FIT, the fits' seed), on the
    served veteran inputs, h1..h5 and both sides pooled:
    share = mean((c - c_perm)^2) / (2 * var(c)). Twice the variance is the expected
    squared change when the prediction is fully determined by the permuted columns,
    so the share runs from 0 (they carry nothing) to about 1. Default named in the
    artifact (D10)."""
    import proj_ml
    rng = np.random.default_rng(seed)
    cs, cps = [], []
    for side in ("hit", "pit"):
        feats = [d["feats"] for sides in inp["rows"].values()
                 for s, d in sides.items() if s == side and d["feats"]]
        if not feats:
            continue
        X = np.asarray(feats, dtype=float)
        Xp = X.copy()
        Xp[:, -HORIZONS:] = X[rng.permutation(len(X))][:, -HORIZONS:]
        for XX, sink in ((X, cs), (Xp, cps)):
            Q = np.full((len(XX), HORIZONS, len(QUANTILES)), np.nan)
            for h in range(1, HORIZONS + 1):
                Qh = q_matrix(bundle, side, XX, h)
                if Qh is not None:
                    Q[:, h - 1, :] = Qh
            Q.sort(axis=2)
            sf = XX[:, proj_ml._STAR_FLAG_IDX] >= 1.0
            sink.append(compose(Q, sf, blends["mean"], blends["star"])["c"].ravel())
    c, cp = np.concatenate(cs), np.concatenate(cps)
    ok = ~(np.isnan(c) | np.isnan(cp))
    v = float(np.var(c[ok]))
    share = float(np.mean((c[ok] - cp[ok]) ** 2) / (2.0 * v)) if v > 0 else None
    return {"share": None if share is None else round(share, 4), "n_cells": int(ok.sum()),
            "seed": seed}


# ---------------------------------------------------------------- criteria, verbatim
CRITERIA_IDS = ("S1 PRIMARY", "S1b", "S1c", "S2", "S3", "S4", "S5", "S6", "S7", "S8",
                "A-SHAPE")


def criteria_verbatim() -> dict:
    """Each 4.8 row exactly as the document prints it, read from the document so
    the artifact cannot carry a paraphrase."""
    out = {}
    for line in (ROOT / GATE_DOC).read_text(encoding="utf-8").splitlines():
        for cid in CRITERIA_IDS:
            plain = "| %s |" % cid
            bold = "| **%s** |" % cid
            if (line.startswith(plain) or line.startswith(bold)) and cid not in out:
                out[cid] = line.strip()
    missing = [c for c in CRITERIA_IDS if c not in out]
    if missing:
        raise SystemExit("criteria rows not found in the gate document: %s" % missing)
    return out


# ---------------------------------------------------------------- composed series
def series(work: Path, F: dict, arm: str, bases, ceiling: int) -> tuple[dict, dict]:
    """({B: {side: (idx, composed)}}, {B: blends}) for an arm at scoring bases
    `bases`, each blended with lambdas refit point in time from the arm's own
    out-of-fold predictions at every earlier base (D2)."""
    need = sorted(set(range(FIRST_BASE + 1, max(bases) + 1)))
    oof = oof_for(work, F, arm, need, ceiling)
    preds, lams = {}, {}
    for B in bases:
        bl = fit_blends(F, oof, B)
        lams[B] = bl
        preds[B] = {}
        for side in ("hit", "pit"):
            idx, Q = oof[B][side]
            preds[B][side] = (idx, compose(Q, star_flag(F[side], idx), bl["mean"], bl["star"]))
    return preds, lams


def lam_vectors(lams: dict) -> dict:
    return {str(B): {"mean": {str(h): v for h, v in bl["mean"].items()},
                     "star_served": {str(h): v for h, v in bl["star"].items()},
                     "star_fitted": {str(h): v for h, v in bl["star_fitted"].items()}}
            for B, bl in sorted(lams.items())}


def full_depth(work: Path, F: dict, arm: str) -> tuple[dict, dict]:
    """The arm at serving depth (labels <= 2025, the bundle a flip would serve) and
    its blends refit on every base's out-of-fold predictions."""
    B = LAST_COMPLETE + 1
    b = get_bundle(work, F, arm, B)
    oof = oof_for(work, F, arm, range(FIRST_BASE + 1, LAST_COMPLETE + 1), LAST_COMPLETE)
    return b, fit_blends(F, oof, B)


def champion_arm(F: dict, bases) -> dict:
    """The champion as an arm: its central path is the stack feature champ_h1..h5;
    bands are not used by any clause it enters (S2 reads MAE only)."""
    out = {}
    for B in bases:
        out[B] = {}
        for side in ("hit", "pit"):
            idx = np.flatnonzero(F[side]["base"] == B)
            c = champ_central(F[side], idx)
            out[B][side] = (idx, {"c": c, "p10": c, "p90": c})
    return out


def per_h_mae(S: dict, arm: str) -> dict:
    out = {}
    for h in range(1, HORIZONS + 1):
        m = S["h"] == h
        if m.any():
            out[h] = float(np.mean(np.abs(S[arm + ":c"][m] - S["y"][m])))
    return out


def upper_bound(S: dict, a: str, b: str, vif: float, sel: np.ndarray | None = None) -> dict:
    num, den = paired_delta(S, a, b, "mae")
    if sel is not None:
        num, den = np.where(sel, num, 0.0), np.where(sel, den, 0.0)
    point = float(num.sum() / den.sum())
    boots = cluster_boot(S, num, den, B_TEST, SEED_BOOT)
    sd = float(np.nanstd(boots, ddof=1))
    return {"point": round(point, 5), "sd_raw": round(sd, 6), "vif": round(vif, 4),
            "sd": round(sd * vif, 6), "upper95": round(point + Z95_ONE * sd * vif, 5),
            "n": int(den.sum()), "n_players": n_players(S, den > 0)}


# ---------------------------------------------------------------- the calibration map (B0)
def _band(a):
    return np.where(a <= 24, "<=24", np.where(a <= 27, "25-27", np.where(
        a <= 30, "28-30", np.where(a <= 33, "31-33", "34+"))))


def _pt_tier(side, pt):
    return np.where(side == "hit",
                    np.where(pt >= 500, "hi", np.where(pt >= 250, "mid", "lo")),
                    np.where(pt >= 600, "hi", np.where(pt >= 300, "mid", "lo")))


def calibration_cells(S: dict) -> dict:
    """tools/proj_calibration_lab.py's cell set, as boolean masks over a scored dict."""
    band = _band(S["age_t"])
    tier = _pt_tier(S["side"], S["pt"])
    cells = {}
    for h in range(1, HORIZONS + 1):
        cells["h%d" % h] = S["h"] == h
        for side in ("hit", "pit"):
            cells["h%d:%s" % (h, side)] = (S["h"] == h) & (S["side"] == side)
    for ab in ("<=24", "25-27", "28-30", "31-33", "34+"):
        cells["age:" + ab] = band == ab
        for side in ("hit", "pit"):
            cells["age:%s:%s" % (ab, side)] = (band == ab) & (S["side"] == side)
    for t in ("lo", "mid", "hi"):
        cells["pt:" + t] = tier == t
        for side in ("hit", "pit"):
            cells["pt:%s:%s" % (t, side)] = (tier == t) & (S["side"] == side)
    for role in ("C", "H", "SP", "RP"):
        cells["role:" + role] = S["role"] == role
    cells["star"] = S["star"].astype(bool)
    cells["nonstar"] = ~S["star"].astype(bool)
    cells["survived"] = S["survived"].astype(bool)
    cells["absent"] = ~S["survived"].astype(bool)
    for side in ("hit", "pit"):
        cells["side:" + side] = S["side"] == side
    cells["all"] = np.ones(len(S["y"]), dtype=bool)
    for ab in ("<=24", "25-27", "28-30", "31-33", "34+"):
        for h in (1, 3, 5):
            cells["ageh:%s:h%d" % (ab, h)] = (band == ab) & (S["h"] == h)
    return cells


def calibration_map(S: dict, arm: str, pred: np.ndarray | None = None) -> dict:
    """Each cell: n, bias, MAE, pred, act, the 300-draw cluster bootstrap over
    players (seed 20260724) and `resolvable = |bias| > 1.96 sd`, refused below 20
    players: the published map's own convention (L6)."""
    pred = S[arm + ":c"] if pred is None else pred
    e = pred - S["y"]
    out = {}
    for name, m in calibration_cells(S).items():
        if not m.any():
            continue
        c = {"n": int(m.sum()), "bias": round(float(e[m].mean()), 4),
             "mae": round(float(np.abs(e[m]).mean()), 4),
             "pred": round(float(pred[m].mean()), 4), "act": round(float(S["y"][m].mean()), 4),
             "n_players": n_players(S, m)}
        if c["n_players"] >= 20:
            boots = cluster_boot(S, np.where(m, e, 0.0), m.astype(float), CAL_DRAWS, CAL_SEED)
            boots = np.sort(boots)
            sd = float(np.std(boots, ddof=1))
            k = len(boots)
            c["ci95"] = [round(float(boots[int(0.025 * (k - 1))]), 4),
                         round(float(boots[int(0.975 * (k - 1))]), 4)]
            c["sd"] = round(sd, 4)
            c["resolvable"] = bool(abs(c["bias"]) > 1.96 * sd)
        else:
            c["resolvable"] = False
            c["refused"] = "fewer than 20 players"
        out[name] = c
    return out


# ---------------------------------------------------------------- stage: pre-flight + B0-COMPARE
def stage_preflight(work: Path, procs: int) -> dict:
    t0 = time.time()
    F = load_frame(work)
    ensure_bundles(work, [("S", B) for B in range(FIRST_BASE + 1, LAST_COMPLETE + 1)], procs)
    bases = list(range(EVAL_FIRST_BASE, LAST_COMPLETE + 1))
    sp, slams = series(work, F, "S", bases, LAST_COMPLETE)
    ch = champion_arm(F, bases)
    pre = {}
    for frame in ("DEV", "GATE"):
        S = scored(F, {"S": sp, "C": ch}, frame, LAST_COMPLETE)
        ms, mc = per_h_mae(S, "S"), per_h_mae(S, "C")
        beats = {h: ms[h] < mc[h] for h in ms}
        pre[frame] = {
            "label_seasons": list(FRAME_LABELS[frame]), "n": int(len(S["y"])),
            "n_players": n_players(S),
            "mae_S": {str(h): round(v, 4) for h, v in ms.items()},
            "mae_champion": {str(h): round(v, 4) for h, v in mc.items()},
            "S_minus_champion": {str(h): round(ms[h] - mc[h], 4) for h in ms},
            "S_beats_champion": {str(h): bool(v) for h, v in beats.items()},
            "form": "Form 1" if all(beats.values()) else "Form 2",
        }
    # B0-COMPARE: the published map's bases, every label season <= 2025
    cmp_cells = {}
    S = _scored_bases(F, {"S": sp}, B0_COMPARE_BASES)
    cmap = calibration_map(S, "S")
    prior = json.loads((ROOT / "data" / "proj_calibration_eval.json").read_text(encoding="utf-8"))
    for c in ("star", "role:C") + AGE_CELLS:
        cmp_cells[c] = {"champion_bwar_prior": prior["cells"].get(c), "b0_compare": cmap.get(c)}
    return {
        "preflight": {"what": "S alone (blended point in time, row-matched, L1 exclusion) "
                              "against the champion per horizon (4.4a); scores the "
                              "incumbent and burns nothing", "frames": pre,
                      "lambda_rule_form": pre["DEV"]["form"], "s2_form": pre["GATE"]["form"]},
        "b0_compare": {"bases": list(B0_COMPARE_BASES), "engine": "S, the serving composition "
                       "(proj_lgbm_v1 heads, the mean and star blends refit point in time)",
                       "n_rows": int(len(S["y"])), "n_players": n_players(S),
                       "lever_cells": cmp_cells, "cells": cmap,
                       "note": "Tier-2 label seasons, a measurement of the INCUMBENT; it "
                               "burns nothing and carries no adjudication (5.1)"},
        "S_lambdas": lam_vectors(slams),
        "wall_s": round(time.time() - t0, 1),
    }


def _scored_bases(F: dict, arm_preds: dict, bases) -> dict:
    """Every valid cell at the given bases with label <= LAST_COMPLETE (B0-COMPARE
    reads the published map's bases, not a 4.6 frame)."""
    FRAME_LABELS["ANY_TO_2025"] = tuple(range(FIRST_BASE, LAST_COMPLETE + 1))
    return scored(F, arm_preds, "ANY_TO_2025", LAST_COMPLETE, bases=set(bases))


# ---------------------------------------------------------------- stage: ARM A
def stage_arm_a(work: Path, procs: int, mde: dict, pre: dict) -> dict:
    t0 = time.time()
    F = load_frame(work)
    corpus = _ENV["corpus"]
    vif = float(mde["bootstrap"]["vif_applied"])
    arms = ["S"] + [arm_name(l) for l in LAMBDA_GRID]
    # (1) the DEV frontier and the lambda rule (4.4): DEV cells only, ceiling 2011
    dev_bases = list(range(EVAL_FIRST_BASE, max(DEV_LABELS) + 1))
    ensure_bundles(work, [(a, B) for a in arms for B in range(FIRST_BASE + 1, max(DEV_LABELS) + 1)], procs)
    dev = {}
    for a in arms:
        dev[a], _ = series(work, F, a, dev_bases, max(DEV_LABELS))
    dev["C"] = champion_arm(F, dev_bases)
    SD = scored(F, dev, "DEV", max(DEV_LABELS))
    ms, mc = per_h_mae(SD, "S"), per_h_mae(SD, "C")
    form = pre["preflight"]["lambda_rule_form"]
    frontier, admissible = [], []
    for lam in LAMBDA_GRID:
        a = arm_name(lam)
        mh = per_h_mae(SD, a)
        if form == "Form 1":
            ok = all(mh[h] < mc[h] for h in mh)
        else:
            ok = all(mh[h] - mc[h] <= ms[h] - mc[h] + M for h in mh)
        st = stats_block(SD, a)
        frontier.append({"lambda": lam, "pooled_mae": st["pooled"]["mae"],
                         "per_h_mae": {str(h): round(v, 4) for h, v in mh.items()},
                         "pooled_bias": st["pooled"]["bias"],
                         "coverage": st["pooled"]["coverage"], "admissible": ok})
        if ok:
            admissible.append(lam)
    chosen = max(admissible) if admissible else None
    if FIXTURE and os.environ.get("PROJ_SHAPE_GATE_FIXTURE_LAMBDA"):
        # dry run only: force a candidate so the GATE reporting path is rehearsed
        chosen = float(os.environ["PROJ_SHAPE_GATE_FIXTURE_LAMBDA"])
    # A0's reproduction tolerance on DEV (4.3, S8)
    def h1_mae(a):
        m = SD["h"] == 1
        return float(np.mean(np.abs(SD[a + ":c"][m] - SD["y"][m])))
    a0 = arm_name(0.0)
    a0_dmae = h1_mae(a0) - h1_mae("S")
    a0_dbias = float(np.mean(SD[a0 + ":c"] - SD["y"]) - np.mean(SD["S:c"] - SD["y"]))
    a0_within = abs(a0_dmae) <= A0_MAE_TOL and abs(a0_dbias) <= A0_BIAS_TOL
    out = {"lambda_rule_form": form, "dev_frontier": frontier,
           "dev_champion_mae": {str(h): round(v, 4) for h, v in mc.items()},
           "dev_S_mae": {str(h): round(v, 4) for h, v in ms.items()},
           "lambda_selected": chosen,
           "a0_reproduction_dev": {"delta_h1_mae": round(a0_dmae, 5),
                                   "delta_pooled_bias": round(a0_dbias, 5),
                                   "tolerance": [A0_MAE_TOL, A0_BIAS_TOL],
                                   "within": bool(a0_within)}}
    # serving-depth recount for every grid point (frontier RS2 / UAF, descriptive)
    P = json.loads((ROOT / "data" / "mlb_projections.json").read_text(encoding="utf-8"))
    inp = serving_inputs(P["vets"])
    ensure_bundles(work, [(a, B) for a in arms for B in range(FIRST_BASE + 1, LAST_COMPLETE + 2)], procs)
    fd = {}
    for a in arms:
        b, bl = full_depth(work, F, a)
        war = serve_bundle_war(inp, b, bl)
        fd[a] = {"rough": rs2_uaf([w for w in war.values() if w[0] >= 1.0]), "blends": bl,
                 "war": war}
    for row in frontier:
        r = fd[arm_name(row["lambda"])]["rough"]
        row.update(rs2_mean=r["rs2_mean"], uaf=r["uaf"], rs2_pool=r["pool"])
    out["frontier_S_full_depth_rough"] = fd["S"]["rough"]
    if chosen is None:
        out.update(verdict="NULL_NO_ADMISSIBLE_LAMBDA", failed=["A-F9"],
                   sentence=None, wall_s=round(time.time() - t0, 1))
        return out
    cand = arm_name(chosen)
    # (2) the GATE frame, opened once: S, A0, the candidate, the champion
    gate_bases = list(range(EVAL_FIRST_BASE, max(GATE_LABELS) + 1))
    g = {a: series(work, F, a, gate_bases, LAST_COMPLETE) for a in ("S", a0, cand)}
    gp = {a: v[0] for a, v in g.items()}
    gp["C"] = champion_arm(F, gate_bases)
    SG = scored(F, gp, "GATE", LAST_COMPLETE)
    stS, stX, stA0 = stats_block(SG, "S"), stats_block(SG, cand), stats_block(SG, a0)
    hs = [str(h) for h in range(1, HORIZONS + 1)]
    crit = {}
    s1 = upper_bound(SG, cand, "S", vif)
    s1_a0 = upper_bound(SG, cand, a0, vif)
    s1_pass = s1["upper95"] < M
    s1_both = s1_pass and s1_a0["upper95"] < M
    s8_branch = "A0 within tolerance: S1 against S alone" if a0_within else \
        "A0 outside tolerance: S1 must clear against BOTH S and A0"
    s1_verdict = s1_pass if a0_within else s1_both
    crit["S1 PRIMARY"] = {"vs_S": s1, "vs_A0": s1_a0, "branch": s8_branch,
                          "pass": bool(s1_verdict)}
    d_h = {h: round(stX["by_h"][h]["mae"] - stS["by_h"][h]["mae"], 4) for h in hs}
    crit["S1b"] = {"point_delta_by_h": d_h, "pass": all(v < S1B for v in d_h.values())}
    # S1c: Tier-2 point in time (4.6a) and CONFIRM (4.6b)
    t2_bases = list(range(min(TIER2_LABELS) - HORIZONS + 1, LAST_COMPLETE + 1))
    t2 = {a: series(work, F, a, t2_bases, LAST_COMPLETE)[0] for a in ("S", cand)}
    ST = scored(F, t2, "TIER2", LAST_COMPLETE)
    s1c_t2 = upper_bound(ST, cand, "S", vif)
    confirm = {"status": "NOT_AVAILABLE",
               "check": "corpus['last'] >= 2027 under the complete-seasons convention",
               "corpus_last": corpus["last"],
               "census_2026_rows": {s: int(sum(1 for r in corpus[s] if r["season"] == 2026))
                                    for s in ("hit", "pit")},
               "season_fraction_2026": round(float(__import__("fa_projection").season_fraction(
                   corpus["league"], 2026)), 3),
               "reading": "NOT_AVAILABLE is not a pass and is not a failure; the ARM A "
                          "verdict rests on the GATE frame alone"}
    crit["S1c"] = {"tier2": s1c_t2, "confirm": confirm,
                   "pass": bool(s1c_t2["upper95"] < M),
                   "supports_pass": False}
    # S2 in the GATE frame's form
    mxs, mss, mcs = per_h_mae(SG, cand), per_h_mae(SG, "S"), per_h_mae(SG, "C")
    s2form = pre["preflight"]["s2_form"]
    if s2form == "Form 1":
        s2ok = {h: mxs[h] < mcs[h] for h in mxs}
    else:
        s2ok = {h: mxs[h] - mcs[h] <= mss[h] - mcs[h] + M for h in mxs}
    crit["S2"] = {"form": s2form, "mae_candidate": {str(h): round(v, 4) for h, v in mxs.items()},
                  "mae_S": {str(h): round(v, 4) for h, v in mss.items()},
                  "mae_champion": {str(h): round(v, 4) for h, v in mcs.items()},
                  "by_h": {str(h): bool(v) for h, v in s2ok.items()}, "pass": all(s2ok.values())}
    s3 = {h: round(abs(stX["by_h"][h]["bias"]) - abs(stS["by_h"][h]["bias"]), 4) for h in hs}
    crit["S3"] = {"abs_bias_growth_by_h": s3, "pass": all(v <= S3_BIAS for v in s3.values())}
    s4d = {h: round(stX["by_h"][h]["coverage"] - stS["by_h"][h]["coverage"], 4) for h in hs}
    s4a = {h: stX["by_h"][h]["coverage"] for h in hs}
    crit["S4"] = {"coverage_delta_by_h": s4d, "coverage_candidate_by_h": s4a,
                  "coverage_S_by_h": {h: stS["by_h"][h]["coverage"] for h in hs},
                  "pass": all(abs(v) <= S4_DELTA for v in s4d.values())
                  and all(S4_BAND[0] <= v <= S4_BAND[1] for v in s4a.values())}
    s5 = {h: {"q10": round(stX["by_h"][h]["pinball_q10"] - stS["by_h"][h]["pinball_q10"], 4),
              "q90": round(stX["by_h"][h]["pinball_q90"] - stS["by_h"][h]["pinball_q90"], 4)}
          for h in hs}
    crit["S5"] = {"pinball_delta_by_h": s5,
                  "pass": all(v["q10"] <= S5_PINBALL and v["q90"] <= S5_PINBALL for v in s5.values())}
    s6 = {}
    s6ok = True
    for h in hs:
        a, b = stX["by_h"][h], stS["by_h"][h]
        if not a.get("n_star"):
            continue
        dm = round(a["mae_star"] - b["mae_star"], 4)
        deeper = abs(a["bias_star"]) > abs(b["bias_star"])
        s6[h] = {"star_mae_delta": dm, "bias_star_candidate": a["bias_star"],
                 "bias_star_S": b["bias_star"], "deeper": bool(deeper), "n_star": a["n_star"]}
        s6ok &= dm <= S6_STAR_MAE and not deeper
    crit["S6"] = {"by_h": s6, "pass": bool(s6ok)}
    crit["S7"] = {"rows_per_cell": "identical by construction; scored() raises on a mismatch",
                  "n": int(len(SG["y"])), "pass": True}
    crit["S8"] = {"a0_within_dev_tolerance": bool(a0_within), "s1_cleared_vs_both": bool(s1_both),
                  "pass": bool(a0_within or s1_both)}
    # A-SHAPE on the served `war` recount at the chosen lambda (4.5)
    rough = fd[cand]["rough"]
    crit["A-SHAPE"] = {"recount": rough, "rs2_bar": ASHAPE_RS2, "uaf_bar": ASHAPE_UAF,
                       "pass": bool(rough["pool"] and rough["rs2_mean"] <= ASHAPE_RS2
                                    and rough["uaf"] <= ASHAPE_UAF),
                       "pool_rule": "served veteran rows with a complete five-season path and "
                                    "year-1 at or above 1.0 WAR, on the candidate's own path"}
    champ_rough = rs2_uaf(served_pool(P["vets"], "warChamp"))
    trip = {"fires": bool(rough["pool"] and rough["rs2_mean"] <= champ_rough["rs2_mean"]),
            "candidate_rs2_mean": rough["rs2_mean"],
            "champion_rs2_mean": champ_rough["rs2_mean"], "abandons": False}
    if trip["fires"] or FIXTURE:
        pre_sh = stack_share(get_bundle(work, F, "S", LAST_COMPLETE + 1), fd["S"]["blends"], inp)
        post_sh = stack_share(get_bundle(work, F, cand, LAST_COMPLETE + 1),
                              fd[cand]["blends"], inp)
        rise = (None if pre_sh["share"] is None or post_sh["share"] is None
                else round(100.0 * (post_sh["share"] - pre_sh["share"]), 2))
        trip.update(share_pre_S=pre_sh, share_post_candidate=post_sh, rise_points=rise,
                    abandons=bool(trip["fires"] and rise is not None
                                  and rise > TRIPWIRE2_POINTS))
    # 4.6c the full-depth transport check, veto-only, READ
    fdp = {}
    t2_rows = list(range(min(TIER2_LABELS) - HORIZONS + 1, LAST_COMPLETE + 1))
    for a in ("S", cand):
        b, bl = get_bundle(work, F, a, LAST_COMPLETE + 1), fd[a]["blends"]
        fdp[a] = {}
        for B in t2_rows:
            fdp[a][B] = {}
            for side in ("hit", "pit"):
                idx = np.flatnonzero(F[side]["base"] == B)
                Q = predict_raw(b, F, side, idx, LAST_COMPLETE)
                fdp[a][B][side] = (idx, compose(Q, star_flag(F[side], idx), bl["mean"], bl["star"]))
    SFD = scored(F, fdp, "TIER2", LAST_COMPLETE)
    transport = upper_bound(SFD, cand, "S", vif)
    transport["vetoes"] = bool(transport["upper95"] >= M)
    transport["label"] = "READ: in-sample at serving depth; veto-only (4.6a, 4.6c)"
    # A-F8
    mde_l = mde["mde95_pooled_mae_by_lambda"]["%.2f" % chosen]
    underpowered = mde_l >= M
    failed = []
    if underpowered:
        failed.append("A-F8")
    for cid, fid in (("S1 PRIMARY", "A-F1"), ("S1b", "A-F1b"), ("S1c", "A-F1c"), ("S2", "A-F2")):
        if not crit[cid]["pass"]:
            failed.append(fid)
    if transport["vetoes"]:
        failed.append("A-F1c (4.6c)")
    if not crit["S8"]["pass"]:
        failed.append("A-F3")
    if not crit["S4"]["pass"]:
        failed.append("A-F4")
    if not crit["S6"]["pass"]:
        failed.append("A-F5")
    if not crit["A-SHAPE"]["pass"]:
        failed.append("A-F6")
    if not crit["S3"]["pass"] or not crit["S5"]["pass"]:
        failed.append("S3/S5")
    if trip["abandons"]:
        failed.append("A-F7")
    if not failed:
        verdict = "PASS"
    elif "A-F8" in failed:
        verdict = "UNDERPOWERED_NO_MARGIN"
    elif failed == ["A-F6"]:
        verdict = "NO_EFFECT"
    else:
        verdict = "NULL"
    out.update({
        "fixture": FIXTURE,
        "candidate": cand, "gate_bases": gate_bases,
        "mde95_pooled_mae_at_lambda": mde_l,
        "criteria_verbatim": criteria_verbatim(),
        "criteria": crit, "stats": {"S": stS, "candidate": stX, "A0": stA0},
        "tripwire2": trip, "transport_check_4_6c": transport,
        "per_base_lambdas": {"S": lam_vectors(g["S"][1]), "A0": lam_vectors(g[a0][1]),
                             "candidate": lam_vectors(g[cand][1])},
        "full_depth_lambdas": {a: lam_vectors({LAST_COMPLETE + 1: fd[a]["blends"]})
                               for a in ("S", a0, cand)},
        "failed": failed, "verdict": verdict, "wall_s": round(time.time() - t0, 1),
        "two_way_disclosure": {
            "ohtani_mlbam": 660271,
            "war_5y_live_vs_candidate": [round(sum(serve_live_war(
                {"rows": {660271: inp["rows"][660271]}})[660271]), 2),
                round(sum(fd[cand]["war"][660271]), 2)] if 660271 in inp["rows"] else None,
            "sentence": UNCONDITIONAL_TWO_WAY},
    })
    return out


# ---------------------------------------------------------------- stage: B0-GATE + ARM B
def _age_cell_masks(S: dict) -> dict:
    band = _band(S["age_t"])
    out = {}
    for c in AGE_CELLS:
        _, ab, side = c.split(":")
        out[c] = (band == ab) & (S["side"] == side)
    return out


def _lever_cell_mask(S: dict, lever: str) -> np.ndarray:
    if lever == "B-C":
        return S["role"] == "C"
    if lever == "B-STAR":
        return S["star"].astype(bool)
    m = np.zeros(len(S["y"]), dtype=bool)
    for v in _age_cell_masks(S).values():
        m |= v
    return m


def lever_stat(S: dict, lever: str, pred: np.ndarray) -> float:
    """The signed-toward-zero statistic of 5.5b is delta = |bias_pre| - |bias_post| on
    the lever's own cell. For B-AGE, a unit over four cells, the cell bias is the
    n-weighted mean over the four registered age cells of |bias| (default named in
    the artifact)."""
    e = pred - S["y"]
    if lever == "B-AGE":
        tot = n = 0.0
        for m in _age_cell_masks(S).values():
            if m.any():
                tot += m.sum() * abs(float(e[m].mean()))
                n += m.sum()
        return tot / n
    m = _lever_cell_mask(S, lever)
    return abs(float(e[m].mean()))


def fit_lever(SD: dict, lever: str, form: str, key: np.ndarray | None = None) -> dict:
    """Fit on the DEV frame's cells (forward-chained: every DEV label is earlier than
    every GATE label). `key` overrides the keying column for the permuted twin."""
    e = SD["S:c"] - SD["y"]
    if lever == "B-AGE":
        age = SD["age_t"] if key is None else key
        out = {}
        for side in ("hit", "pit"):
            m = SD["side"] == side
            x = age[m] - age[m].mean()
            b = float((x * e[m]).sum() / (x * x).sum())
            out[side] = {"slope": b, "centre": float(age[m].mean())}
        return {"lever": lever, "form": "side-keyed linear slope in age-at-target", "fit": out}
    m = (SD["role"] == "C") if key is None else key.astype(bool)
    if lever == "B-C":
        if form == "primary":
            k = float(SD["y"][m].sum() / SD["S:c"][m].sum())
            return {"lever": lever, "form": "projected PT x rate scale on catcher rows "
                    "(a multiplicative factor on the catcher central path)", "k": k}
        a = -float(e[m].mean())
        return {"lever": lever, "form": "output-side level on catcher rows (twin)", "a": a}
    raise ValueError(lever)


def apply_lever(S: dict, fit: dict, key: np.ndarray | None = None) -> np.ndarray:
    pred = S["S:c"].copy()
    if fit["lever"] == "B-AGE":
        age = S["age_t"] if key is None else key
        for side, v in fit["fit"].items():
            m = S["side"] == side
            pred[m] = pred[m] - v["slope"] * (age[m] - v["centre"])
        return pred
    m = (S["role"] == "C") if key is None else key.astype(bool)
    if "k" in fit:
        pred[m] = pred[m] * fit["k"]
    else:
        pred[m] = pred[m] + fit["a"]
    return pred


def _permute_within(S: dict, col: np.ndarray, rng) -> np.ndarray:
    """The keying column permuted across players within (label season x horizon)."""
    out = col.copy()
    ls = S["base"] + S["h"] - 1
    for key in set(zip(ls.tolist(), S["h"].tolist())):
        m = np.flatnonzero((ls == key[0]) & (S["h"] == key[1]))
        out[m] = col[m][rng.permutation(len(m))]
    return out


def stage_arm_b(work: Path, mde: dict, arm_a: dict) -> dict:
    t0 = time.time()
    F = load_frame(work)
    vif = float(mde["bootstrap"]["vif_applied"])
    engine = "S"           # 5.2: the engine serving after ARM A's verdict (see artifact)
    dev_bases = list(range(EVAL_FIRST_BASE, max(DEV_LABELS) + 1))
    gate_bases = list(range(EVAL_FIRST_BASE, max(GATE_LABELS) + 1))
    dp, _ = series(work, F, engine, dev_bases, max(DEV_LABELS))
    gp, _ = series(work, F, engine, gate_bases, LAST_COMPLETE)
    SD = scored(F, {"S": dp}, "DEV", max(DEV_LABELS))
    SG = scored(F, {"S": gp}, "GATE", LAST_COMPLETE)
    b0 = calibration_map(SG, "S")
    b0_lever = {c: b0.get(c) for c in ("star", "role:C") + AGE_CELLS}
    resolvable_cells = sorted(c for c, v in b0.items() if v.get("resolvable"))
    arm_a_pass = arm_a.get("verdict") == "PASS"
    # 8.2: a flip is the owner's call even on a PASS, and this battery flips nothing,
    # so the engine B0-GATE reads is the incumbent whatever ARM A's verdict (D12)
    arm_a_ships = False
    levers = {}
    for lever in LEVERS:
        L = {"lever": lever}
        cells = list(AGE_CELLS) if lever == "B-AGE" else (["role:C"] if lever == "B-C" else ["star"])
        L["b0_gate_cells"] = {c: b0.get(c) for c in cells}
        resolvable = any((b0.get(c) or {}).get("resolvable") for c in cells)
        mde_l = mde["arm_b"]["levers"][lever]
        L["floor"] = {"mde95_holm_k3": mde_l["mde95_holm_k3"], "sd": mde_l["sd"],
                      "detected_planted": mde_l["detected"]}
        if lever == "B-STAR" and not arm_a_pass:
            L.update(status="not run", verdict="NULL",
                     reason="B-F7: ARM A was not shipped, so the only admissible form of this "
                            "lever is one of the three banned mean-head arms")
            levers[lever] = L
            continue
        if lever == "B-STAR":
            L.update(status="not run", verdict="NOT_AVAILABLE",
                     reason="D12: ARM A passed but SERVE_SHAPE_REFIT is the owner's call (8.2) "
                            "and was not flipped; this lever's only admissible form "
                            "recalibrates the refit heads, which do not serve")
            levers[lever] = L
            continue
        if not resolvable:
            L.update(status="not fitted", verdict="DEAD_ON_ARRIVAL",
                     reason="B-F1: its B0-GATE cell is not resolvable on the serving engine "
                            "(|bias| at or below 1.96 sd, or fewer than 20 players)")
            if arm_a_ships:
                L["absorbed_sentence"] = "the refit absorbed it"
            levers[lever] = L
            continue
        # fitted on DEV, adjudicated on GATE (out of fold)
        fit = fit_lever(SD, lever, "primary")
        post = apply_lever(SG, fit)
        pre_stat, post_stat = lever_stat(SG, lever, SG["S:c"]), lever_stat(SG, lever, post)
        delta = pre_stat - post_stat
        # paired bootstrap of delta, clustered on player
        inv, P = player_index(SG)
        rng = np.random.default_rng(SEED_BOOT)
        draws = []
        for _ in range(B_TEST):
            pick = rng.integers(0, P, P)
            w = np.bincount(pick, minlength=P)[inv].astype(float)
            draws.append(_weighted_lever_delta(SG, lever, post, w))
        sd = float(np.nanstd(draws, ddof=1)) * vif
        mae_pre = float(np.mean(np.abs(SG["S:c"] - SG["y"])))
        mae_post = float(np.mean(np.abs(post - SG["y"])))
        cm = _lever_cell_mask(SG, lever)
        slice_pre = float(np.mean(np.abs(SG["S:c"][cm] - SG["y"][cm])))
        slice_post = float(np.mean(np.abs(post[cm] - SG["y"][cm])))
        # B2: the permuted twin
        key = SG["age_t"] if lever == "B-AGE" else (SG["role"] == "C").astype(float)
        keyd = SD["age_t"] if lever == "B-AGE" else (SD["role"] == "C").astype(float)
        prng = np.random.default_rng(SEED_BOOT)
        ratios, reds = [], []
        for _ in range(PERM_DRAWS):
            kd = _permute_within(SD, keyd, prng)
            kg = _permute_within(SG, key, prng)
            pf = fit_lever(SD, lever, "primary", key=kd)
            pp = apply_lever(SG, pf, key=kg)
            red = pre_stat - lever_stat(SG, lever, pp)
            rise = float(np.mean(np.abs(pp - SG["y"]))) - mae_pre
            reds.append(red)
            ratios.append(rise / red if red > B2_FLOOR else np.nan)
        rise_real = mae_post - mae_pre
        real_ratio = rise_real / delta if delta > B2_FLOOR else None
        med_red = float(np.median(reds))
        if delta <= B2_FLOOR:
            b2 = "NULL"
        elif med_red <= B2_FLOOR:
            b2 = "PASS_BY_CONSTRUCTION"
        else:
            med_ratio = float(np.nanmedian(ratios))
            b2 = "PASS" if real_ratio < B2_RATIO * med_ratio else "NULL"
        # B4: no other resolvable cell deepens by more than 0.05
        b0_post = calibration_map(SG, "S", pred=post)
        deepened = {c: round(abs(b0_post[c]["bias"]) - abs(b0[c]["bias"]), 4)
                    for c in resolvable_cells if c in b0_post and c not in cells
                    and abs(b0_post[c]["bias"]) - abs(b0[c]["bias"]) > B4_DEEPEN}
        L.update(status="fitted", fit=fit,
                 b1={"delta": round(delta, 5), "pre": round(pre_stat, 5),
                     "post": round(post_stat, 5), "sd_vif": round(sd, 6),
                     "sign_positive": bool(delta > 0)},
                 b2={"verdict": b2, "real_reduction": round(delta, 5),
                     "real_cost_ratio": None if real_ratio is None else round(real_ratio, 4),
                     "permuted_reduction_median": round(med_red, 5),
                     "permuted_cost_ratio_median": (None if np.all(np.isnan(ratios))
                                                    else round(float(np.nanmedian(ratios)), 4)),
                     "permuted_cost_ratio_iqr": (None if np.all(np.isnan(ratios)) else
                                                 [round(float(np.nanpercentile(ratios, 25)), 4),
                                                  round(float(np.nanpercentile(ratios, 75)), 4)]),
                     "draws": PERM_DRAWS, "seed": SEED_BOOT},
                 b3={"pooled_mae_rise": round(mae_post - mae_pre, 5),
                     "slice_mae_rise": round(slice_post - slice_pre, 5),
                     "pass": bool(mae_post - mae_pre <= B3_POOLED and slice_post - slice_pre <= 0)},
                 b4={"deepened_beyond_0.05": deepened, "pass": not deepened})
        levers[lever] = L
    # the Holm family, always k = 3 in the fixed order (5.5a, 5.5b)
    from efv_power_lab import holm_family
    fam = []
    for lever in LEVERS:
        L = levers[lever]
        b1 = L.get("b1")
        enters_real = (b1 is not None and b1["sign_positive"]
                       and L["floor"]["detected_planted"])
        if enters_real:
            fam.append({"key": lever, "delta": b1["delta"], "sd": b1["sd_vif"]})
        else:
            fam.append({"key": lever, "delta": 0.0, "sd": L["floor"]["sd"]})
            L["holm_substitution"] = "5.5a: delta 0.0 with its registered floor sd"
    holm = holm_family(fam, HOLM_ALPHA)
    for c in holm["cells"]:
        L = levers[c["key"]]
        L["holm"] = c
        if L.get("status") != "fitted":
            continue
        if not L["b1"]["sign_positive"]:
            L["verdict"] = "NULL"
            L["reason"] = "5.5b: delta <= 0, NULL whatever its abs_t"
        elif not L["floor"]["detected_planted"]:
            L["verdict"] = "UNDERPOWERED"
            L["reason"] = ("B-F8: the detection check cannot see a planted effect the size "
                           "of the nearer-zero end of its published prior CI")
        elif not c["reject_holm"]:
            L["verdict"] = "NULL_HOLM"
        elif L["b2"]["verdict"] == "NULL":
            L["verdict"] = "NULL"
            L["reason"] = "B-F3: the permuted twin"
        elif not L["b3"]["pass"]:
            L["verdict"] = "NULL"
            L["reason"] = "B-F4: MAE budget"
        elif not L["b4"]["pass"]:
            L["verdict"] = "NULL"
            L["reason"] = "B-F5: another resolvable cell deepens"
        else:
            L["verdict"] = "PASS"
    # 5.4a: B-C's twin is evaluated only after its primary PASSED every clause
    Lc = levers.get("B-C") or {}
    if Lc.get("verdict") == "PASS" or (FIXTURE and Lc.get("status") == "fitted"):
        twin = fit_lever(SD, "B-C", "twin")
        tpost = apply_lever(SG, twin)
        pre_c = lever_stat(SG, "B-C", SG["S:c"])
        prim_c = lever_stat(SG, "B-C", apply_lever(SG, Lc["fit"]))
        twin_c = lever_stat(SG, "B-C", tpost)
        den = pre_c - prim_c
        share = (pre_c - twin_c) / den if den > 0 else None
        Lc["twin"] = {"fit": twin, "abs_bias_pre": round(pre_c, 5),
                      "abs_bias_post_primary": round(prim_c, 5),
                      "abs_bias_post_twin": round(twin_c, 5),
                      "share": None if share is None else round(share, 4),
                      "threshold": TWIN_SHARE,
                      "ships_in_place_of_primary": bool(share is not None and share >= TWIN_SHARE),
                      "b_f6_sentence": ("the miss is in projected catcher PT and rate and this "
                                        "term repairs the number and not the cause")}
    return {"engine": engine, "fixture": FIXTURE,
            "engine_note": ("proj_lgbm_v1 as served: ARM A did not ship (a flip is the owner's "
                            "call even on a PASS, 8.2), so B0-GATE re-runs on the incumbent"),
            "b0_gate": {"frame": "GATE", "label_seasons": list(GATE_LABELS),
                        "n_rows": int(len(SG["y"])), "n_players": n_players(SG),
                        "lever_cells": b0_lever, "resolvable_cells": resolvable_cells,
                        "cells": b0},
            "levers": levers,
            "holm": {"k": holm["k"], "alpha": holm["alpha"], "order": list(LEVERS),
                     "procedure": holm["procedure"], "cells": holm["cells"]},
            "wall_s": round(time.time() - t0, 1)}


def _weighted_lever_delta(S: dict, lever: str, post: np.ndarray, w: np.ndarray) -> float:
    def wstat(pred):
        e = pred - S["y"]
        if lever == "B-AGE":
            tot = n = 0.0
            for m in _age_cell_masks(S).values():
                ww = w * m
                if ww.sum() > 0:
                    tot += ww.sum() * abs(float((ww * e).sum() / ww.sum()))
                    n += ww.sum()
            return tot / n if n else np.nan
        m = _lever_cell_mask(S, lever)
        ww = w * m
        return abs(float((ww * e).sum() / ww.sum())) if ww.sum() > 0 else np.nan
    return wstat(S["S:c"]) - wstat(post)


# ---------------------------------------------------------------- the artifact
SENTENCES = {
    "A-F1": ("The joint refit with an age-smoothness penalty is NOT non-inferior to the "
             "shipped `proj_lgbm_v1` composition. It buys a smoother path at an accuracy cost "
             "larger than the margin registered before the run, and it does not ship. The "
             "served paths remain non-monotone in age and that defect is published with its "
             "size rather than repaired."),
    "A-F1c": ("The GATE frame did not fail this arm, and the read frame did. A read frame "
              "cannot pass an arm and it can fail one, and it failed this one. The refit does "
              "not ship."),
    "A-F3": ("The measured difference is the change of objective plus the penalty, and "
             "nothing in this battery separates them. The result is a NULL and the quantity "
             "measured is a re-implementation of the estimator, not a smoothness effect."),
    "A-F6": ("The penalty did not smooth the served paths by the minimum registered before "
             "the run. The recount at the chosen lambda leaves the board too close to the "
             "shipped engine for this to be the repair the owner reported. This is a failed "
             "implementation, not a finding about smoothness, and the arm is abandoned rather "
             "than re-tuned."),
    "A-F8": ("This battery cannot resolve a degradation as small as the margin it was allowed "
             "to spend. The verdict is UNDERPOWERED_NO_MARGIN. It is not a pass, and no number "
             "from this run may be cited as evidence that accuracy was preserved."),
    "B-F7": ("The mean-head lever is exhausted; three arms (`mean_head_rejected`, "
             "`star_mean_head`, `star_slice_mean_head`) have already failed, and without the "
             "heads refit no admissible form of this lever remains. Not run."),
}
LEVER_WORDS = {"B-AGE": "age-by-side slope", "B-C": "catcher correction",
               "B-STAR": "star-slice recalibration"}


def l8_census(F: dict) -> dict:
    """Per base: the share of base rows in the point-in-time training frame (labels
    <= B - 1) that carry all five horizons, per side (L8)."""
    out = {}
    for B in range(EVAL_FIRST_BASE, LAST_COMPLETE + 2):
        out[str(B)] = {}
        for side in ("hit", "pit"):
            f = F[side]
            tc = _train_cells(f, B)
            rows = tc.any(axis=1)
            out[str(B)][side] = round(float(tc[rows].all(axis=1).mean()), 4) if rows.any() else None
    return out


def l1_census(F: dict) -> dict:
    corpus = _ENV["corpus"]
    ts = two_sided_set(corpus)
    out = {"two_sided_player_seasons": len(ts),
           "player_seasons": len({(r["mlbam"], r["season"]) for s in ("hit", "pit")
                                  for r in corpus[s] if r.get("mlbam")}),
           "excluded_cells_by_frame": {}, "two_sided_cells_scored": 0}
    for frame in ("DEV", "GATE", "TIER2"):
        n_ex = n_all = 0
        for side in ("hit", "pit"):
            f = F[side]
            ls = label_seasons(f)
            inset = np.isin(ls, FRAME_LABELS[frame]) & (f["base"][:, None] >= EVAL_FIRST_BASE) \
                & ~np.isnan(f["Y"])
            ex = inset & (f["excl_cell"] | f["excl_row"][:, None])
            n_ex += int(ex.sum())
            n_all += int(inset.sum())
            # the scorer reads valid_cells(), which carries no two-sided cell
            assert not (cell_mask(f, frame) & (f["excl_cell"] | f["excl_row"][:, None])).any()
        out["excluded_cells_by_frame"][frame] = {"excluded": n_ex, "of": n_all,
                                                 "share": round(n_ex / n_all, 4) if n_all else None}
    out["disclosure"] = L1_DISCLOSURE
    return out


MDE_OUT = ROOT / "data" / "proj_shape_mde.json"


def assemble(work: Path, mde_path: Path = MDE_OUT) -> dict:
    F = load_frame(work)
    mde = json.loads(Path(mde_path).read_text(encoding="utf-8"))
    pre = _read_stage(work, "preflight")
    aa = _read_stage(work, "arm_a")
    ab = _read_stage(work, "arm_b")
    b = mde["bootstrap"]
    art = {
        "generated_at": utc_now(),
        "gate": GATE_DOC + " (sections 4 and 5, under amendment A-2: war_provider = fwar)",
        "read": EARLY_READ + "; recorded in section 24 of the gate document",
        "producer": "tools/proj_shape_gate.py (stages preflight, arm-a, arm-b, assemble)",
        "war_provider": "fwar",
        "fixture": FIXTURE,
        "corpus": corpus_stamp(work),
        "sentences": {"basis": UNCONDITIONAL_BASIS, "roughness": UNCONDITIONAL_ROUGHNESS,
                      "two_way": UNCONDITIONAL_TWO_WAY, "transport": UNCONDITIONAL_TRANSPORT},
        "defaults": [
            "D1 L1 exclusion: a frame row whose base season (B - 1) is two-sided and a cell "
            "whose label season (B + h - 1) is two-sided are excluded from every fit and "
            "every scored cell, for every arm and for S",
            "D2 point-in-time blends pool every earlier base from 2004 whose cells carry "
            "labels <= B - 1",
            "D3 mean blend: lift-only, grid 0.0 to 1.0 by 0.1, the smallest |bias| among the "
            "lambdas whose MAE stays strictly below the champion's on the same cells",
            "D4 star blend: tools/fit_star_blend.py's rule on top of the mean-blended q50 "
            "(predict_path's order); h2 served at 0 for both arms (the incumbent's h2 failed "
            "its confirmation), the fitted value published",
            "D5 the joint heads read the frame's features plus horizon and age_at_target",
            "D6 the power lab's calibration candidate is lambda 0.20; the measured ratio "
            "applies to every lambda",
            "D7 B-AGE's cell statistic is the n-weighted mean |bias| over the four registered "
            "age cells; its floor is the bootstrap sd of their prior-signed mean bias",
            "D8 B-C's primary form is a multiplicative factor on the catcher central path "
            "(projected PT times rate scaled together); its twin is an additive level",
            "D9 the A-SHAPE recount is the battery's serving replica (it reproduces the "
            "served `war` on 1,400 of 1,400 rows through the live bundle) run through the "
            "candidate's serving-depth bundle and blends",
            "D10 Tripwire 2's champion-stack share is the permutation importance of "
            "champ_h1..h5 permuted together on the served veteran inputs: "
            "mean((c - c_perm)^2) / (2 var(c)), h1..h5 and both sides pooled, seed 20260611",
            "D11 an UNDERPOWERED lever (B-F8) enters the Holm family under the 5.5a "
            "substitution, the conservative direction for the other two",
            "D12 this battery flips no flag (8.2), so B0-GATE and every lever read the "
            "incumbent whatever ARM A's verdict; on an ARM A PASS, B-STAR reads NOT_AVAILABLE "
            "until the owner flips SERVE_SHAPE_REFIT, and enters the Holm family under 5.5a",
        ],
        "bootstrap": {"B": b["B"], "refits_per_draw": b["refits_per_draw"],
                      "train_resampled": b["train_resampled"], "seed": b["seed"],
                      "vif_registered": b["vif_registered"], "vif_measured": b["vif_measured"],
                      "vif_applied": b["vif_applied"], "calibration": b["calibration"],
                      "source": "data/proj_shape_mde.json"},
        "l1": l1_census(F),
        "l8_share_all_five_by_base": l8_census(F),
        "flags": {"SERVE_SHAPE_REFIT": False, "SERVE_BIAS_LEVERS": [],
                  "MODEL_VERSION": "proj_lgbm_v1",
                  "note": "a flip is the owner's call even on a PASS (8.2); nothing flipped"},
        "tier2_or_confirm_supports_pass": False,
    }
    if pre:
        art["preflight"] = pre["preflight"]
        art["b0_compare"] = pre["b0_compare"]
    holm_a = "NOT_APPLICABLE_NON_INFERIORITY"
    if aa:
        A = dict(aa)
        A["frame"] = {"GATE": list(GATE_LABELS), "DEV": list(DEV_LABELS),
                      "TIER2": list(TIER2_LABELS), "CONFIRM": list(CONFIRM_LABELS)}
        A["comparators"] = {"S": "proj_lgbm_v1 heads retrained point in time per base with full "
                                 "quantiles, the L1 exclusion and point-in-time blends",
                            "A0": "the joint shape at lambda 0", "C": "marcel_decay_v2"}
        A["sentences"] = []
        fl = A.get("failed") or []
        if any(f in fl for f in ("A-F1", "A-F1b", "A-F2")):
            A["sentences"].append(SENTENCES["A-F1"])
        if any(f.startswith("A-F1c") for f in fl):
            A["sentences"].append(SENTENCES["A-F1c"])
        if "A-F3" in fl:
            A["sentences"].append(SENTENCES["A-F3"])
        if "A-F6" in fl:
            A["sentences"].append(SENTENCES["A-F6"])
        if "A-F8" in fl:
            A["sentences"].append(SENTENCES["A-F8"])
        A["roughness_sentence"] = UNCONDITIONAL_ROUGHNESS
        A["transport_sentence"] = UNCONDITIONAL_TRANSPORT
        art["arm_a"] = A
    holm_b = None
    if ab:
        B_ = dict(ab)
        for lever, L in B_["levers"].items():
            if L.get("verdict") in ("NULL", "NULL_HOLM") and lever != "B-STAR":
                L["sentence"] = ("The %s is a NULL on the serving engine under a Holm family "
                                 "of three. The cell `proj_calibration_map` published on the "
                                 "champion decay path does not reproduce as a fixable bias on "
                                 "the engine that actually serves." % LEVER_WORDS[lever])
            if L.get("reason", "").startswith("B-F7"):
                L["sentence"] = SENTENCES["B-F7"]
        holm_b = dict(B_["holm"])
        for c in holm_b["cells"]:
            c.setdefault("mde95_holm_k3", c.get("mde95_holm_k3"))
        art["arm_b"] = B_
    art["holm"] = {"arm_a": holm_a, "arm_b": holm_b}
    return art


# ---------------------------------------------------------------- artifact io
def load_artifact() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {}


def write_artifact(art: dict, out: Path = OUT) -> None:
    Path(out).write_text(json.dumps(art, indent=1, default=_jsonable) + "\n", encoding="utf-8")


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(type(o))


def _stage_file(work: Path, name: str) -> Path:
    return Path(work) / ("stage_%s.json" % name)


def _save_stage(work: Path, name: str, obj: dict) -> None:
    _stage_file(work, name).write_text(json.dumps(obj, indent=1, default=_jsonable),
                                       encoding="utf-8")


def _read_stage(work: Path, name: str) -> dict | None:
    p = _stage_file(work, name)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["frame", "preflight", "arm-a", "arm-b", "assemble"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--mde", default=str(MDE_OUT))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    work = Path(a.work)
    setup(work, Path(ROOT / ".cache" / "fa_corpus.pkl"))
    if a.stage == "frame":
        F = build_frame(work, a.procs)
        print(json.dumps(F["meta"], indent=1, default=_jsonable))
    elif a.stage == "preflight":
        r = stage_preflight(work, a.procs)
        _save_stage(work, "preflight", r)
        print(json.dumps(r["preflight"], indent=1, default=_jsonable))
    elif a.stage == "arm-a":
        mde = json.loads(Path(a.mde).read_text(encoding="utf-8"))
        r = stage_arm_a(work, a.procs, mde, _read_stage(work, "preflight"))
        _save_stage(work, "arm_a", r)
        print(json.dumps({k: r.get(k) for k in ("lambda_selected", "candidate", "failed",
                                                "verdict")}, indent=1, default=_jsonable))
    elif a.stage == "arm-b":
        mde = json.loads(Path(a.mde).read_text(encoding="utf-8"))
        r = stage_arm_b(work, mde, _read_stage(work, "arm_a"))
        _save_stage(work, "arm_b", r)
        print(json.dumps({k: v.get("verdict") for k, v in r["levers"].items()}, indent=1))
    elif a.stage == "assemble":
        write_artifact(assemble(work, Path(a.mde)), Path(a.out))
