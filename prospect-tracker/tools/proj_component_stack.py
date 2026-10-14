# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""W2, the component stack twin of the serving WAR-path bundle (task
PJ_9_STACK_ARM_DARK; docs/PROJ_COMPONENTS_GATE.md section 6; LANE_A 2.5).

THE TWIN. `proj_lgbm_v1`'s feature vector (proj_ml.feature_names, the serving
schema) extended by the component stack: for hitters the projected BsR, Fld
and Pos runs per 600 PA from the frozen component heads (H3, H4, H5 at h1),
last season's sprint speed and its missing flag; for pitchers the projected
gmLI (P4) and the RA9 gap per 100 IP (P5). Every projection is point in time:
the heads read seasons B-3..B-1 through proj_components.lag_inputs, the
engine and the aging service are fitted at B - 1, the league constants are
B - 1's, and the head constants are the DEV-frozen model/proj_components/
params.json (which is why bases before 2022 are not point in time for the
veto read: section 6, round 4 leakage 9). The training call is proj_ml's:
the same label (fa_projection.war_actual_map, an absent season is 0), the
same rows (the twin's serving columns are checked equal to
proj_ml.build_training_frame's matrix), the same LightGBM hyperparameters
(proj_ml._params_for, checked against the serving bundle's meta) and the
same quantile heads. A stack column the heads cannot project is NaN, which
LightGBM treats as missing; sprint speed carries its own flag because the
gate names one.

NEVER SERVED. Nothing under fa_market, fa_projection, proj_export or
fa_export imports this module or opens model/proj_lgbm_components/;
`load_twin` is the only loader and only this module and its test call it
(test_proj_component_stack.py scans the served path and proves the loader
is never called). Caches live under .cache/proj_component_stack/, keyed by
the extended schema's hash, the component params hash and
max_label_season, beside proj_ml's own point-in-time caches.

THE VETO READ (once, recorded in data/proj_horizon_eval.json as
challenger_blocks.component_stack_tier2_veto, label READ). Bases 2022 to
2025, h1, forward-chained point-in-time twin and incumbent bundles (labels
<= B - 1, full quantiles, no blend lambdas, the raw monotone q50 as the
point, exactly proj_eval.run_rowmatch's basis), identical rows, the pooled
MAE delta (twin minus incumbent) with its one-sided 95% upper bound from
the player-clustered paired bootstrap (B 1000, seed 20261119, VIF 1.8 on
the sd). An upper bound at or above +0.0065 vetoes W2 whatever the 2027
look says; no number here is ever cited for a pass.

Usage:
    python tools/proj_component_stack.py --dry-run --out DIR   # fixtures only
    python tools/proj_component_stack.py --veto-read [--out DIR]
    python tools/proj_component_stack.py --final               # the twin bundle
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import pickle
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import proj_ml                        # noqa: E402

log = logging.getLogger("proj_component_stack")

BUNDLE_DIR = ROOT / "model" / "proj_lgbm_components"
CACHE_DIR = ROOT / ".cache" / "proj_component_stack"
ARTIFACT = ROOT / "data" / "proj_horizon_eval.json"
VETO_KEY = "component_stack_tier2_veto"
TWIN_VERSION = "proj_lgbm_components_v1"

#: The stack columns, appended after the serving schema in this order.
STACK_EXTRA = {
    "hit": ["bsr_rate_proj", "fld_rate_proj", "pos_rate_proj", "sprint_l1", "sprint_missing"],
    "pit": ["gmli_proj", "ra9_gap_proj"],
}

#: The veto read's registered constants (gate section 6, round 4).
VETO_BASES = (2022, 2023, 2024, 2025)
VETO_SEED = 20261119
VETO_B = 1000
VETO_VIF = 1.8
VETO_BAR = 0.0065
Z_ONE_SIDED_95 = 1.645

#: The DEV-frozen component params (gate section 9, 2026-10-09 row).
FROZEN_PARAMS_SHA256 = "da2d5114fe2c05a1cceed883a625ddb63060e45c8fc848c385860694b02cf9b6"


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def stack_feature_names(side: str) -> list[str]:
    """The serving schema (proj_ml.feature_names) followed by the stack
    columns; the serving columns keep their positions."""
    return list(proj_ml.feature_names(side)) + list(STACK_EXTRA[side])


def schema_tag() -> str:
    return hashlib.sha256(
        json.dumps({s: stack_feature_names(s) for s in ("hit", "pit")},
                   sort_keys=True).encode()).hexdigest()[:8]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def serving_meta(path: Path | None = None) -> dict:
    """The serving bundle's meta, checked: it must be on the fWAR corpus and
    on proj_ml's own schema and hyperparameters (a bundle from another
    trainer would need a training API this module does not have)."""
    meta = json.loads(((path or proj_ml.MODEL_DIR) / "meta.json").read_text(encoding="utf-8"))
    if meta.get("war_provider") != "fwar":
        raise RuntimeError(f"serving bundle war_provider {meta.get('war_provider')!r} is not fwar")
    feats = meta.get("features") or {}
    for side in ("hit", "pit"):
        if list(feats.get(side) or []) != list(proj_ml.feature_names(side)):
            raise RuntimeError(f"serving bundle {side} schema differs from proj_ml.feature_names; "
                               "W2 needs a proj_ml training API")
    if dict(meta.get("params") or {}) != dict(proj_ml.LGBM_PARAMS):
        raise RuntimeError("serving bundle hyperparameters differ from proj_ml.LGBM_PARAMS; "
                           "W2 needs a proj_ml training API")
    return meta


def load_corpus() -> dict:
    """The corpus pickle as the component tools read it (never rebuilt
    here), checked for the fWAR label and the repaired label shape."""
    import fa_projection as fp
    with open(fp.CORPUS_CACHE, "rb") as fh:
        corpus = pickle.load(fh)
    if corpus.get("war_provider") != "fwar":
        raise RuntimeError(f"corpus war_provider {corpus.get('war_provider')!r} is not fwar")
    if corpus.get("label_shape") != fp.LABEL_SHAPE:
        raise RuntimeError(f"corpus label_shape {corpus.get('label_shape')!r} != {fp.LABEL_SHAPE}")
    return corpus


def frozen_params() -> dict:
    import proj_components as PC
    return PC.check_params(PC.load_params(), FROZEN_PARAMS_SHA256)


# --------------------------------------------------------------------------
# The stack columns, point in time per base
# --------------------------------------------------------------------------

def _nan(v) -> float:
    return float("nan") if v is None else float(v)


def hitter_stack(line: dict | None, feat: dict) -> list[float]:
    """[bsr_rate_proj, fld_rate_proj, pos_rate_proj, sprint_l1, sprint_missing]
    from the h1 component line and the lag inputs; NaN where the heads
    project nothing."""
    bsr = fld = pos = None
    if line:
        pa = line.get("pa")
        bsr = line.get("bsr600")
        if pa and pa > 0:
            fld = None if line.get("fld") is None else float(line["fld"]) / float(pa) * 600.0
            pos = None if line.get("pos") is None else float(line["pos"]) / float(pa) * 600.0
    sprint = (feat or {}).get("sprint_speed_l1")
    return [_nan(bsr), _nan(fld), _nan(pos), _nan(sprint), 0.0 if sprint is not None else 1.0]


def pitcher_stack(line: dict | None, feat: dict) -> list[float]:
    """[gmli_proj, ra9_gap_proj] from the h1 component line."""
    if not line:
        return [float("nan"), float("nan")]
    return [_nan(line.get("gmli")), _nan(line.get("ra9gap_100ip"))]


class _StackContext:
    """Per-run memo of the point-in-time inputs the heads need."""

    def __init__(self, corpus: dict, params: dict):
        import aging_v3_sidecar
        import proj_components as PC
        self.corpus = corpus
        self.params = params
        self.params_hash = PC.params_hash(params)[:12]
        self.src = PC.make_sources()
        self.vintage_id = self.src.blob["vintage_id"]
        self.sidecar = aging_v3_sidecar.load(corpus, build_if_missing=False)
        self.league = corpus["league"]
        self._consts: dict[int, dict | None] = {}
        self._age_curves: dict[int, dict] = {}

    def consts(self, season: int):
        """season_constants(B - 1), or None when the league constants carry
        no solved block for that season (the stack is NaN there)."""
        import proj_components as PC
        if season not in self._consts:
            try:
                self._consts[season] = PC.season_constants(season, self.corpus, self.src.blob)
            except ValueError as e:
                log.info("stack: no league constants for %d (%s); stack columns NaN", season, e)
                self._consts[season] = None
        return self._consts[season]

    def age_curves(self, base: int) -> dict:
        import aging_v3
        import proj_components as PC
        if base not in self._age_curves:
            model = aging_v3.fitted(self.corpus, base - 1, None, sidecar=self.sidecar)
            self._age_curves[base] = PC.component_age_curves(model)
        return self._age_curves[base]


def _stack_cache_path(ctx: _StackContext, base: int) -> Path:
    return CACHE_DIR / f"stack_{schema_tag()}_{ctx.params_hash}_{ctx.vintage_id}_{base}.pkl"


def stack_rows(ctx: _StackContext, base: int, by_player: dict, curves: dict,
               use_cache: bool = True) -> dict:
    """{(side, mlbam): stack columns} for every veteran with history at
    `base`, from the frozen heads at h1; disk-cached per base."""
    import proj_components as PC
    path = _stack_cache_path(ctx, base)
    if use_cache and path.exists():
        with open(path, "rb") as fh:
            return pickle.load(fh)
    consts = ctx.consts(base - 1)
    age_curves = ctx.age_curves(base) if consts is not None else None
    out: dict = {}
    for side in ("hit", "pit"):
        for mlbam, seasons in by_player[side].items():
            hist = [seasons[t] for t in (base - 1, base - 2, base - 3) if t in seasons]
            if not hist:
                continue
            age = proj_ml.age_from_history(hist, base)
            if age is None:
                continue
            feat = PC.lag_inputs(ctx.src, side, mlbam, base)
            line = None
            if consts is not None:
                eng = PC.engine_projection(hist, side, base, age, curves, ctx.league)
                if eng is not None:
                    if side == "hit":
                        blk = PC.hitter_heads(eng, feat, ctx.params, consts, age_curves)
                    else:
                        blk = PC.pitcher_heads(eng, feat, ctx.params, consts)
                    line = (blk.get("lines") or {}).get(1)
            out[(side, mlbam)] = (hitter_stack(line, feat) if side == "hit"
                                  else pitcher_stack(line, feat))
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".pkl.tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(out, fh)
        tmp.replace(path)
    return out


def _by_player(corpus: dict) -> dict:
    by_player = {"hit": {}, "pit": {}}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side].setdefault(r["mlbam"], {})[r["season"]] = r
    return by_player


# --------------------------------------------------------------------------
# The training frame and the twin
# --------------------------------------------------------------------------

def _frame_cache_path(ctx: _StackContext, first_base: int, max_label_season: int) -> Path:
    c = ctx.corpus
    return (CACHE_DIR / f"frame_{schema_tag()}_{ctx.params_hash}_{first_base}_{max_label_season}_"
                        f"{c['first']}_{c['last']}{proj_ml._war_tag(c)}.pkl")


def build_stack_frame(ctx: _StackContext, first_base: int, max_label_season: int,
                      use_cache: bool = True) -> dict:
    """proj_ml.build_training_frame's walk with the stack columns appended
    and the row ids kept: {side: {X, y, rows, label_season, ids}}. The
    serving columns are checked equal to proj_ml's own cached frame, so the
    twin trains on exactly the incumbent's rows, labels and inputs."""
    import fa_projection as fp
    path = _frame_cache_path(ctx, first_base, max_label_season)
    if use_cache and path.exists():
        with open(path, "rb") as fh:
            return pickle.load(fh)
    corpus = ctx.corpus
    by_player = _by_player(corpus)
    war_actual = fp.war_actual_map(corpus)
    H = proj_ml.HORIZONS
    out = {}
    for side in ("hit", "pit"):
        X, ids = [], []
        y = {h: [] for h in range(1, H + 1)}
        ls = {h: [] for h in range(1, H + 1)}
        row_idx = {h: [] for h in range(1, H + 1)}
        for base in range(first_base, max_label_season + 1):
            curves, war_map = fp.fitted_models(corpus, base - 1, aging="v2")
            stack = stack_rows(ctx, base, by_player, curves)
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (base - 1, base - 2, base - 3) if t in seasons]
                if not hist:
                    continue
                age = proj_ml.age_from_history(hist, base)
                if age is None:
                    continue
                feats = proj_ml.build_features(hist, side, base, age, curves, war_map, ctx.league)
                if feats is None:
                    continue
                extra = stack.get((side, mlbam))
                if extra is None:
                    extra = [float("nan")] * len(STACK_EXTRA[side])
                    if side == "hit":
                        extra[-1] = 1.0
                i = len(X)
                X.append(list(feats) + list(extra))
                ids.append((mlbam, base))
                for h in range(1, H + 1):
                    target = base + h - 1
                    if target > max_label_season:
                        continue
                    y[h].append(war_actual.get((mlbam, target), 0.0))
                    ls[h].append(target)
                    row_idx[h].append(i)
        out[side] = {"X": np.asarray(X, dtype=float),
                     "y": {h: np.asarray(v, dtype=float) for h, v in y.items()},
                     "rows": {h: np.asarray(v, dtype=int) for h, v in row_idx.items()},
                     "label_season": {h: np.asarray(v, dtype=int) for h, v in ls.items()},
                     "ids": ids}
    check_against_serving_frame(out, corpus, first_base, max_label_season)
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".pkl.tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(out, fh)
        tmp.replace(path)
    return out


def check_against_serving_frame(frame: dict, corpus: dict, first_base: int,
                                max_label_season: int) -> None:
    """The twin's serving columns, labels and row index equal proj_ml's own
    frame exactly; anything else is a tool bug, never a model."""
    ref = proj_ml.build_training_frame(corpus, first_base, max_label_season)
    for side in ("hit", "pit"):
        n_serve = len(proj_ml.feature_names(side))
        Xs = frame[side]["X"][:, :n_serve]
        if Xs.shape != ref[side]["X"].shape or not np.array_equal(Xs, ref[side]["X"]):
            raise AssertionError(f"stack frame {side}: serving columns differ from proj_ml's frame")
        for h in ref[side]["y"]:
            if (not np.array_equal(frame[side]["y"][h], ref[side]["y"][h])
                    or not np.array_equal(frame[side]["rows"][h], ref[side]["rows"][h])):
                raise AssertionError(f"stack frame {side} h{h}: labels or rows differ from proj_ml's frame")


def train_twin(ctx: _StackContext, max_label_season: int, first_base: int = 2003,
               quantiles: tuple = proj_ml.QUANTILES, serving: dict | None = None) -> dict:
    """proj_ml.train's call on the extended frame: the same heads, the same
    hyperparameters per horizon (proj_ml._params_for), the same row floor."""
    from lightgbm import LGBMRegressor
    serving = serving or serving_meta()
    frame = build_stack_frame(ctx, first_base, max_label_season)
    models: dict = {"meta": {
        "version": TWIN_VERSION, "twin_of": serving.get("version"),
        "max_label_season": max_label_season, "first_base": first_base,
        "params": dict(proj_ml.LGBM_PARAMS),
        "params_long_h": dict(proj_ml.LGBM_PARAMS_LONG_H),
        "quantiles": list(quantiles),
        "features": {s: stack_feature_names(s) for s in ("hit", "pit")},
        "stack_extra": {s: list(STACK_EXTRA[s]) for s in ("hit", "pit")},
        "schema_tag": schema_tag(),
        "war_provider": ctx.corpus.get("war_provider"),
        "label_shape": ctx.corpus.get("label_shape"),
        "component_params_sha256": FROZEN_PARAMS_SHA256,
        "vintage_id": ctx.vintage_id,
        "serving_train_hash": serving.get("train_hash"),
        "never_served": True,
    }}
    for side in ("hit", "pit"):
        models[side] = {}
        f = frame[side]
        for h in range(1, proj_ml.HORIZONS + 1):
            rows = f["rows"][h]
            if len(rows) < 500:
                continue
            Xh, yh = f["X"][rows], f["y"][h]
            models[side][h] = {}
            for q in quantiles:
                m = LGBMRegressor(alpha=q, **proj_ml._params_for(h))
                m.fit(Xh, yh)
                models[side][h][q] = m
        log.info("twin %s: trained %d horizons on <=%d labels (n_h1=%d)",
                 side, len(models[side]), max_label_season, len(f["rows"][1]))
    hsh = hashlib.sha256()
    for side in ("hit", "pit"):
        f = frame[side]
        hsh.update(str(f["X"].shape).encode())
        hsh.update(np.ascontiguousarray(np.nansum(f["X"], axis=0)).tobytes())
    models["meta"]["train_hash"] = hsh.hexdigest()[:16]
    models["meta"]["n_rows"] = {s: {str(h): int(len(frame[s]["rows"][h]))
                                    for h in range(1, proj_ml.HORIZONS + 1)}
                                for s in ("hit", "pit")}
    return models


_PIT_CACHE: dict[int, dict] = {}


def _pit_cache_path(ctx: _StackContext, max_label_season: int, quantiles: tuple) -> Path:
    qtag = "".join(str(int(q * 100)) for q in quantiles)
    return (CACHE_DIR / f"pit_{TWIN_VERSION}_{schema_tag()}_{ctx.params_hash}_{max_label_season}_"
                        f"{qtag}{proj_ml._war_tag(ctx.corpus)}.joblib")


def train_cached_twin(ctx: _StackContext, max_label_season: int,
                      quantiles: tuple = proj_ml.QUANTILES, serving: dict | None = None) -> dict:
    """The point-in-time twin (labels <= max_label_season), disk-cached
    under .cache/proj_component_stack/ by schema hash, params hash and
    max_label_season (proj_ml.train_cached's rules)."""
    if max_label_season in _PIT_CACHE:
        return _PIT_CACHE[max_label_season]
    import joblib
    path = _pit_cache_path(ctx, max_label_season, quantiles)
    if path.exists():
        _PIT_CACHE[max_label_season] = joblib.load(path)
        return _PIT_CACHE[max_label_season]
    t0 = time.time()
    models = train_twin(ctx, max_label_season, quantiles=quantiles, serving=serving)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(models, path, compress=3)
    log.info("twin bundle <=%d trained and cached (%.0fs)", max_label_season, time.time() - t0)
    _PIT_CACHE[max_label_season] = models
    return models


def save_twin(models: dict, path: Path | None = None) -> Path:
    return proj_ml.save(models, path or BUNDLE_DIR)


def load_twin(path: Path | None = None) -> dict | None:
    """The twin's only loader. Nothing on the served path calls it."""
    import joblib
    p = (path or BUNDLE_DIR) / "models.joblib"
    if not p.exists():
        return None
    return joblib.load(p)


# --------------------------------------------------------------------------
# The veto read
# --------------------------------------------------------------------------

def paired_cluster_bootstrap(deltas_by_player: dict, B: int, seed: int) -> dict:
    """proj_eval's player-clustered paired bootstrap (the PJ-C scorer's)."""
    import proj_eval as pe
    return pe._paired_cluster_bootstrap(deltas_by_player, B, seed)


def score_pairs(pairs: list[dict], B: int = VETO_B, seed: int = VETO_SEED,
                vif: float = VETO_VIF) -> dict:
    """pairs: [{player, twin, incumbent, actual}] at one horizon. The pooled
    MAE delta (twin minus incumbent), the clustered sd times the VIF, the
    one-sided 95% upper bound and MDE95. A pair with a None or non-finite
    value is not scored."""
    by_player: dict = defaultdict(list)
    at = ai = 0.0
    n = 0
    for p in pairs:
        t, i, a = p.get("twin"), p.get("incumbent"), p.get("actual")
        if any(v is None or not math.isfinite(float(v)) for v in (t, i, a)):
            continue
        t, i, a = float(t), float(i), float(a)
        at += abs(t - a)
        ai += abs(i - a)
        n += 1
        by_player[p["player"]].append(abs(t - a) - abs(i - a))
    if n == 0:
        return {"n_rows": 0, "n_players": 0, "mae_twin": None, "mae_incumbent": None,
                "delta": None, "sd": None, "ub95": None, "mde95": None}
    bs = paired_cluster_bootstrap(by_player, B, seed)
    sd = bs["sd"]
    sd_vif = None if sd is None else float(sd) * float(vif)
    point = bs["point"]
    return {
        "n_rows": n, "n_players": bs["n_players"],
        "mae_twin": round(at / n, 4), "mae_incumbent": round(ai / n, 4),
        "delta": round(float(point), 4) if point is not None else None,
        "sd": round(sd_vif, 6) if sd_vif is not None else None,
        "ub95": (round(float(point) + Z_ONE_SIDED_95 * sd_vif, 4)
                 if point is not None and sd_vif is not None else None),
        "mde95": round(Z_ONE_SIDED_95 * sd_vif, 4) if sd_vif is not None else None,
    }


def veto_verdict(pooled: dict, bar: float = VETO_BAR) -> dict:
    """VETOED when the pooled upper bound is at or above the bar; a bound
    that cannot be computed is reported as NOT COMPUTABLE and vetoes
    nothing by itself. Never a pass."""
    ub = pooled.get("ub95")
    if ub is None:
        return {"vetoed": False, "verdict": "NOT COMPUTABLE (no upper bound)", "bar": bar}
    vetoed = float(ub) >= float(bar)
    return {"vetoed": vetoed, "bar": bar,
            "verdict": ("VETOED: the pooled one-sided 95% upper bound is at or above +0.0065"
                        if vetoed else
                        "not vetoed; no number here is cited for a pass (the 2027 look decides)")}


def collect_pairs(ctx: _StackContext, bases: tuple = VETO_BASES, serving: dict | None = None,
                  incumbent_fn=None, twin_fn=None) -> list[dict]:
    """The h1 pairs at each base: identical rows (a row enters only when the
    champion, the incumbent and the twin all produce a path), the raw
    monotone q50 of each bundle, the actual h1 WAR (absent season 0)."""
    import fa_projection as fp
    import proj_eval as pe
    corpus = ctx.corpus
    by_player = _by_player(corpus)
    war_actual = fp.war_actual_map(corpus)
    incumbent_fn = incumbent_fn or (lambda B: proj_ml.train_cached(corpus, B - 1, quantiles=proj_ml.QUANTILES))
    twin_fn = twin_fn or (lambda B: train_cached_twin(ctx, B - 1, serving=serving))
    pairs: list[dict] = []
    for B in bases:
        if B > corpus["last"] - 1:
            raise RuntimeError(f"base {B}: label season {B} is not complete in the corpus")
        curves, war_map = fp.fitted_models(corpus, B - 1, aging="v2")
        incumbent = incumbent_fn(B)
        twin = twin_fn(B)
        stack = stack_rows(ctx, B, by_player, curves)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                age = proj_ml.age_from_history(hist, B)
                if age is None:
                    continue
                champ = pe.default_predict_fn(hist, side, B, age, curves, war_map, ctx.league)
                if champ is None:
                    continue
                feats = proj_ml.build_features(hist, side, B, age, curves, war_map, ctx.league,
                                               champ=champ)
                if feats is None:
                    continue
                extra = stack.get((side, mlbam))
                if extra is None:
                    extra = [float("nan")] * len(STACK_EXTRA[side])
                    if side == "hit":
                        extra[-1] = 1.0
                pi = proj_ml.predict_path(incumbent, feats, side)
                pt = proj_ml.predict_path(twin, list(feats) + list(extra), side)
                if pi is None or pt is None:
                    continue
                base_actual = war_actual.get((mlbam, B - 1))
                pairs.append({
                    "player": mlbam, "side": side, "base": B,
                    "twin": pt["war_by_year"][0], "incumbent": pi["war_by_year"][0],
                    "actual": war_actual.get((mlbam, B), 0.0),
                    "survived": (mlbam, B) in war_actual,
                    "star": base_actual is not None and base_actual >= 4.0,
                })
        log.info("veto read base %d: %d pairs so far", B, len(pairs))
    return pairs


def veto_block(pairs: list[dict], bases=VETO_BASES, B: int = VETO_B, seed: int = VETO_SEED,
               vif: float = VETO_VIF, extra: dict | None = None) -> dict:
    """The recorded block: pooled primary, survived-only and star-slice
    secondaries, per-base and per-side descriptives, the verdict."""
    pooled = score_pairs(pairs, B, seed, vif)
    verdict = veto_verdict(pooled)
    block = {
        "label": "READ",
        "task": "PJ_9_STACK_ARM_DARK",
        "generated_at": _utc_stamp(),
        "gate": "docs/PROJ_COMPONENTS_GATE.md section 6, the W2 veto read (round 4, leakage 9)",
        "basis": ("forward-chained point-in-time twin and incumbent bundles (labels <= B - 1, "
                  "full quantiles, no blend lambdas, raw monotone q50), identical rows, h1, "
                  "absent season 0 WAR; twin minus incumbent MAE; veto only, never cited for a pass"),
        "candidate": TWIN_VERSION,
        "incumbent": "proj_lgbm_v1 point-in-time (proj_ml.train_cached)",
        "bases": list(bases), "horizon": 1,
        "bootstrap": {"B": int(B), "seed": int(seed), "vif": float(vif), "clustered_on": "player",
                      "upper_bound": "one-sided 95%, delta + 1.645 x sd x VIF"},
        "veto_bar": VETO_BAR,
        "pooled": pooled,
        "survived_only": score_pairs([p for p in pairs if p.get("survived")], B, seed, vif),
        "star_slice": score_pairs([p for p in pairs if p.get("star")], B, seed, vif),
        "per_base": {str(b): _descriptive([p for p in pairs if p.get("base") == b]) for b in bases},
        "per_side": {s: _descriptive([p for p in pairs if p.get("side") == s]) for s in ("hit", "pit")},
        "vetoed": verdict["vetoed"],
        "verdict": verdict["verdict"],
        "never_cited_for_a_pass": True,
    }
    if extra:
        block.update(extra)
    return block


def _descriptive(pairs: list[dict]) -> dict:
    n = at = ai = 0
    for p in pairs:
        t, i, a = p.get("twin"), p.get("incumbent"), p.get("actual")
        if any(v is None or not math.isfinite(float(v)) for v in (t, i, a)):
            continue
        at += abs(float(t) - float(a))
        ai += abs(float(i) - float(a))
        n += 1
    return {"n": n, "mae_twin": round(at / n, 4) if n else None,
            "mae_incumbent": round(ai / n, 4) if n else None,
            "delta": round((at - ai) / n, 4) if n else None}


def write_veto_block(block: dict, path: Path | None = None) -> Path:
    """Read-modify-write: every existing key of the artifact survives
    verbatim (challenger_blocks included); only this block's key is set.
    The file keeps its line endings."""
    path = path or ARTIFACT
    raw = path.read_bytes() if path.exists() else b"{}"
    crlf = b"\r\n" in raw
    try:
        doc = json.loads(raw.decode("utf-8"))
    except ValueError:
        doc = {}
    cb = doc.setdefault("challenger_blocks", {})
    cb[VETO_KEY] = block
    text = json.dumps(doc, indent=1)
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    return path


def recorded_veto(path: Path | None = None) -> dict | None:
    path = path or ARTIFACT
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return (doc.get("challenger_blocks") or {}).get(VETO_KEY)


def format_block(block: dict) -> str:
    def num(v):
        return "n/a" if v is None else f"{v:+.4f}" if isinstance(v, float) else str(v)
    lines = [f"W2 Tier-2 veto read ({block.get('label')}; bases {block.get('bases')}, h1; "
             f"B {block['bootstrap']['B']}, seed {block['bootstrap']['seed']}, VIF {block['bootstrap']['vif']})"]
    for name in ("pooled", "survived_only", "star_slice"):
        s = block.get(name) or {}
        lines.append(f"  {name:<14} n {s.get('n_rows')} players {s.get('n_players')} "
                     f"MAE twin {num(s.get('mae_twin'))} incumbent {num(s.get('mae_incumbent'))} "
                     f"delta {num(s.get('delta'))} ub95 {num(s.get('ub95'))} mde95 {num(s.get('mde95'))}")
    for b, s in (block.get("per_base") or {}).items():
        lines.append(f"  base {b}: n {s.get('n')} delta {num(s.get('delta'))}")
    for b, s in (block.get("per_side") or {}).items():
        lines.append(f"  side {b}: n {s.get('n')} delta {num(s.get('delta'))}")
    lines.append(f"  bar {block.get('veto_bar')}: {block.get('verdict')}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Fixtures (the dry run reads no real row)
# --------------------------------------------------------------------------

def fixture_pairs() -> list[dict]:
    """Pairs with None values and a non-finite value, enough players for a
    bootstrap, written so the dry run exercises every branch of the
    reporting path."""
    rng = np.random.default_rng(7)
    pairs = []
    for i in range(40):
        a = float(rng.normal(1.5, 1.5))
        inc = a + float(rng.normal(0.0, 0.6))
        tw = inc + float(rng.normal(0.01, 0.2))
        pairs.append({"player": 1000 + i, "side": "hit" if i % 2 else "pit",
                      "base": 2022 + (i % 4), "twin": tw, "incumbent": inc, "actual": a,
                      "survived": i % 5 != 0, "star": a >= 4.0})
    pairs.append({"player": 2001, "side": "hit", "base": 2022, "twin": None, "incumbent": 1.0,
                  "actual": 1.0, "survived": True, "star": False})
    pairs.append({"player": 2002, "side": "pit", "base": 2023, "twin": 1.0, "incumbent": None,
                  "actual": None, "survived": False, "star": False})
    pairs.append({"player": 2003, "side": "pit", "base": 2024, "twin": float("nan"),
                  "incumbent": 0.5, "actual": 0.0, "survived": False, "star": False})
    return pairs


def dry_run(out_dir: Path) -> dict:
    """The whole reporting path on fixtures: scoring with nulls, the block,
    its text, and the read-modify-write into a scratch artifact carrying
    foreign keys that must survive. Writes under out_dir only."""
    out_dir.mkdir(parents=True, exist_ok=True)
    block = veto_block(fixture_pairs(), B=50, extra={"dry_run": True})
    scratch = out_dir / "proj_horizon_eval.dryrun.json"
    scratch.write_bytes(json.dumps({"model": "fixture", "challenger_blocks": {"keep": {"x": 1}},
                                    "unrelated": "keep me"}, indent=1).replace("\n", "\r\n").encode())
    write_veto_block(block, scratch)
    back = json.loads(scratch.read_text(encoding="utf-8"))
    assert back["unrelated"] == "keep me" and back["challenger_blocks"]["keep"] == {"x": 1}
    assert back["challenger_blocks"][VETO_KEY]["dry_run"] is True
    assert b"\r\n" in scratch.read_bytes()
    (out_dir / "dry_run.txt").write_text(format_block(block) + "\n", encoding="utf-8")
    return block


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def run_veto_read(out_dir: Path | None, bases=VETO_BASES, B: int = VETO_B) -> dict:
    serving = serving_meta()
    corpus = load_corpus()
    ctx = _StackContext(corpus, frozen_params())
    t0 = time.time()
    pairs = collect_pairs(ctx, bases, serving=serving)
    block = veto_block(pairs, bases, B=B, extra={
        "schema": {s: stack_feature_names(s) for s in ("hit", "pit")},
        "schema_tag": schema_tag(),
        "component_params_sha256": FROZEN_PARAMS_SHA256,
        "vintage_id": ctx.vintage_id,
        "serving_bundle": {"version": serving.get("version"),
                           "train_hash": serving.get("train_hash"),
                           "max_label_season": serving.get("max_label_season"),
                           "war_provider": serving.get("war_provider")},
        "corpus": {"first": corpus.get("first"), "last": corpus.get("last"),
                   "war_provider": corpus.get("war_provider"),
                   "label_shape": corpus.get("label_shape")},
        "twin_bundles": {str(b): _pit_cache_path(ctx, b - 1, proj_ml.QUANTILES).name for b in bases},
        "wall_seconds": round(time.time() - t0, 1),
    })
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "veto_block.json").write_text(json.dumps(block, indent=1), encoding="utf-8")
        (out_dir / "veto_pairs.json").write_text(json.dumps(pairs), encoding="utf-8")
    return block


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="the reporting path on fixtures only")
    ap.add_argument("--veto-read", action="store_true", help="the Tier-2 veto read, recorded once")
    ap.add_argument("--final", action="store_true",
                    help="train the twin on the serving max_label_season into model/proj_lgbm_components/")
    ap.add_argument("--out", type=Path, default=None, help="output directory for receipts")
    ap.add_argument("--no-persist", action="store_true", help="veto read without writing the artifact")
    ap.add_argument("--B", type=int, default=VETO_B)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        out = args.out or (CACHE_DIR / "dryrun")
        block = dry_run(out)
        print(format_block(block))
        print(f"dry run written under {out}")
        return 0

    if args.veto_read:
        if recorded_veto() is not None and not args.no_persist:
            print(f"{ARTIFACT} already carries challenger_blocks.{VETO_KEY}: the veto read runs once; "
                  "refusing to rerun")
            return 2
        block = run_veto_read(args.out, B=args.B)
        print(format_block(block))
        if not args.no_persist:
            write_veto_block(block)
            print(f"wrote challenger_blocks.{VETO_KEY} into {ARTIFACT.relative_to(ROOT)}")
        return 0

    if args.final:
        rec = recorded_veto()
        if rec is None:
            print("no veto read recorded; run --veto-read first (the twin is not saved before its veto read)")
            return 2
        if rec.get("vetoed"):
            print("W2 is VETOED by its Tier-2 read; the twin is not saved for the Opening Day freeze")
            return 3
        serving = serving_meta()
        corpus = load_corpus()
        ctx = _StackContext(corpus, frozen_params())
        models = train_twin(ctx, int(serving["max_label_season"]),
                            first_base=int(serving.get("first_base") or 2003), serving=serving)
        models["meta"]["veto_read"] = {"ub95": (rec.get("pooled") or {}).get("ub95"),
                                       "delta": (rec.get("pooled") or {}).get("delta"),
                                       "vetoed": rec.get("vetoed")}
        path = save_twin(models)
        print(f"twin saved to {path} (train_hash {models['meta']['train_hash']})")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
