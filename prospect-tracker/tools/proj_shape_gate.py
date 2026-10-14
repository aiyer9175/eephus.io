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
    key = str(work)
    if key not in _FRAME:
        with open(Path(work) / "frame.pkl", "rb") as fh:
            _FRAME[key] = pickle.load(fh)
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
                mdl = LGBMRegressor(alpha=q, **proj_ml._params_for(h))
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
            mdl = LGBMRegressor(objective=make_objective(q, lam, prv, nxt), **JOINT_PARAMS)
            mdl.fit(Xl, yl)
            out["heads"][side][q] = mdl.booster_.model_to_string()
    return out


_BOOSTERS: dict = {}


def _booster(s: str):
    import lightgbm as lgb
    k = id(s)
    b = _BOOSTERS.get(k)
    if b is None or b[0] is not s:
        b = (s, lgb.Booster(model_str=s))
        _BOOSTERS[k] = b
    return b[1]


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
    heads = bundle["heads"].get(side) or {}
    for h in range(1, HORIZONS + 1):
        sel = np.flatnonzero(f["base"][idx] + h - 1 <= ceiling)
        if not len(sel):
            continue
        rows = idx[sel]
        if bundle["arm"] == "S":
            hh = heads.get(h)
            if not hh:
                continue
            Xh = f["X"][rows]
            for k, q in enumerate(QUANTILES):
                out[sel, h - 1, k] = _booster(hh[q]).predict(Xh)
        else:
            if not heads:
                continue
            Xl = _long(f, rows, np.full(len(rows), h))
            for k, q in enumerate(QUANTILES):
                out[sel, h - 1, k] = _booster(heads[q]).predict(Xl)
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
def scored(F: dict, arm_preds: dict, frame: str, ceiling: int) -> dict:
    """Flatten the cells of `frame` scored by every arm in `arm_preds`
    ({arm: {B: {side: (idx, composed)}}}): arrays aligned across arms, row-matched
    by construction (S7). Raises if any arm lacks a prediction on a cell."""
    cols = defaultdict(list)
    arms = list(arm_preds)
    for side in ("hit", "pit"):
        f = F[side]
        cm = cell_mask(f, frame) & (label_seasons(f) <= ceiling)
        for B in sorted({int(b) for b in f["base"][cm.any(axis=1)]}):
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
            heads = bundle["heads"].get(side) or {}
            for h in range(1, HORIZONS + 1):
                if bundle["arm"] == "S":
                    hh = heads.get(h)
                    if not hh:
                        break
                    for k, q in enumerate(QUANTILES):
                        Q[0, h - 1, k] = _booster(hh[q]).predict(x)[0]
                else:
                    xl = np.hstack([x, [[float(h), float(feats[0]) + h - 1]]])
                    for k, q in enumerate(QUANTILES):
                        Q[0, h - 1, k] = _booster(heads[q]).predict(xl)[0]
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


# ---------------------------------------------------------------- artifact io
def load_artifact() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {}


def write_artifact(art: dict) -> None:
    OUT.write_text(json.dumps(art, indent=1, default=_jsonable) + "\n", encoding="utf-8")


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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["frame"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    if a.stage == "frame":
        setup(Path(a.work), Path(ROOT / ".cache" / "fa_corpus.pkl"))
        F = build_frame(Path(a.work), a.procs)
        print(json.dumps(F["meta"], indent=1, default=_jsonable))
        for s in ("hit", "pit"):
            print(s, F[s]["X"].shape)
