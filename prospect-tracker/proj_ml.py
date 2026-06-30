# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""WAR-projection ML challenger (model-audit Phase 1, WS-1).

LightGBM quantile models, one per (side x horizon 1-5 x quantile
{.10,.25,.50,.75,.90}) — 50 heads total — challenging the Marcel + aging-
decay champion under "best model wins" (owner decision 2026-06-11).

DESIGN CONTRACTS:
  NO LOOKAHEAD   one training row per (player, base-season B) with
                 features computable STRICTLY from seasons <= B-1; the
                 label is bWAR in season B+h-1 (absent = 0, matching the
                 proj_eval convention). Forward-chaining is enforced by
                 the LABEL season: a model evaluated at base B trains
                 only on rows whose label season <= B-1.
  STACKED CHAMPION  the champion's own predictions (Marcel year-1 +
                 decay path medians per horizon) ride as features — the
                 trees start FROM the champion and learn its residuals,
                 so the challenger can't be much worse and the gain
                 isolates what trees add.
  NO ZERO FLOOR  the champion's decay path floors P10 at 0 WAR, which is
                 the measured root cause of the survived-only coverage
                 collapse (0.31-0.41 vs 0.80 — Phase-0 finding #1).
                 Quantile heads predict raw WAR, negatives included.
  DETERMINISM    fixed seed, deterministic=True, num_threads=1, feature
                 list versioned; saved bundles carry a training-data
                 hash, recorded in the model registry.
  QUANTILE SANITY  post-hoc monotone sort across quantiles per
                 prediction (quantile heads can cross; sorting restores
                 q10 <= q25 <= q50 <= q75 <= q90).

Training/eval drivers live in tools/train_proj_models.py. The live
integration point is fa_market.contract_war_path (model dispatch with
the champion decay as documented fallback; horizons 6+ extrapolate from
the h5 head along the champion's aging curves — a documented seam, since
nothing beyond h5 is validatable yet).
"""

from __future__ import annotations

import hashlib
import json
import logging
import warnings
from pathlib import Path

import numpy as np

import fa_market as fm
import fa_projection as fp

log = logging.getLogger(__name__)

# LightGBM's sklearn wrapper records feature names even when fit on a bare ndarray,
# then nags "X does not have valid feature names" on every ndarray predict. proj_ml
# predicts on ndarrays by design (deterministic positional schema, predict_path) -- so
# this fires once PER HEAD PER PLAYER (~32k times in a single proj_export, millions in a
# backtest), spamming logs (58MB seen) for zero signal. Filter the one message at import
# (scoped to the message + category, so real warnings still surface). Mirrors the
# context-managed suppressions already in efv_model / prospect_path / swing_plus_ingest.
warnings.filterwarnings("ignore", message="X does not have valid feature names",
                        category=UserWarning)

MODEL_DIR = Path(__file__).parent / "model" / "proj_lgbm"
MODEL_VERSION = "proj_lgbm_v1"
HORIZONS = 5
QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

# --- Defensive prior (HIT-ONLY), from the bWAR defensive split -------------
# Forward read of sustainable defensive value, separated from the noisy single-
# season defensive component embedded in the total-WAR lags. The total WAR lags
# (war_l1/l2/l3) already carry defense, but a REGRESSED, position-anchored read
# is more stable than one fluky dWAR season -- the hypothesis the audit flagged
# (wills-models-for-xfv-audit: defense is a real WAR component for MLB players,
# unlike the offense-dominated prospect WAR target, where it was rejected).
#
# SHIPPED 2026-06-29: pos_adj_prior ALONE -- the positional-adjustment prior
# ("where the org trusts them to play"), the report's thesis (position, not
# noisy fielding rates). Gated forward-chained (tools/def_feature_backtest.py ->
# data/proj_def_feature_eval.json): HOLDOUT pooled hit MAE -0.0027, star slice
# -0.0285; dev improves too; the gain concentrates in established regulars
# (base WAR >= 4) whose defensive value is real and persistent. Ablation:
# def_war_prior gains similarly (collinear -- DON'T stack, "+both" is worse);
# the def_missing flag is INERT (0.0000, redundant with the war_l*_missing
# flags) and is dropped. () = dormant. Candidate set: DEF_FEATURE_CANDIDATES.
DEF_FEATURE_CANDIDATES = ("def_war_prior", "pos_adj_prior", "def_missing")
DEF_FEATURE_KEYS: tuple = ("pos_adj_prior",)
_DEF_SHRINK_PA = 600.0
_DEF_HIST_PATH = Path(__file__).parent / "data" / "mlb_def_history.json"
_DEF_HIST_CACHE: dict | None = None


def _def_history() -> dict:
    """{ 'mlbam:season': {war_def, runs_position, pa} } from data/mlb_def_history.json
    (built by tools/build_def_history.py off the same bWAR pull as the corpus)."""
    global _DEF_HIST_CACHE
    if _DEF_HIST_CACHE is None:
        try:
            _DEF_HIST_CACHE = (json.loads(_DEF_HIST_PATH.read_text(encoding="utf-8"))
                               .get("rows", {}))
        except (OSError, ValueError):
            _DEF_HIST_CACHE = {}
    return _DEF_HIST_CACHE


def _def_prior(mlbam, base: int) -> dict:
    """Reliability-shrunk defensive prior from COMPLETED seasons base-1..3 ONLY
    (leakage-free -- the same window the war lags read). Position players only.

      def_war_prior  WAR_def per 650 PA, shrunk toward 0 (league-average) by the
                     window's PA exposure -- the full defensive-value read.
      pos_adj_prior  positional adjustment (runs) per 650 PA, shrunk -- the stable
                     "where the org trusts them to play" signal (the report's
                     thesis: position, not noisy fielding rates).
      def_missing    1.0 when the player has no MLB defensive history in the window
                     (rookies / pre-debut), so the tree can gate the read."""
    hist = _def_history()
    swd = spos = spa = 0.0
    if mlbam:
        for k in (1, 2, 3):
            r = hist.get(f"{int(mlbam)}:{base - k}")
            if r:
                swd += r["war_def"]
                spos += r["runs_position"]
                spa += r["pa"]
    if spa <= 0:
        return {"def_war_prior": 0.0, "pos_adj_prior": 0.0, "def_missing": 1.0}
    denom = spa + _DEF_SHRINK_PA
    return {"def_war_prior": round(swd * 650.0 / denom, 4),
            "pos_adj_prior": round(spos * 650.0 / denom, 4),
            "def_missing": 0.0}


SEED = 20260611

# Feature schema — versioned; order matters (LightGBM is positional).
HIT_COMPS = ("k_pct", "bb_pct", "iso", "babip", "hr_pa")
PIT_COMPS = ("k_pct", "bb_pct", "hr_bf")

LGBM_PARAMS = {
    "objective": "quantile",
    "n_estimators": 400,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 60,
    "subsample": 0.9, "subsample_freq": 1,
    "colsample_bytree": 0.9,
    "reg_lambda": 1.0,
    "deterministic": True,
    "force_row_wise": True,
    "n_jobs": 1,
    "random_state": SEED,
    "verbose": -1,
}
# Long horizons carry zero-inflated labels (most of the pool has washed
# out by h4-5) — the dev iteration showed the default capacity pulling
# star medians toward the zero mass (h5 star bias -0.88 vs champion
# -0.64). Deeper trees + smaller leaves at h>=4 let the star regime get
# its own structure instead of averaging into attrition.
LGBM_PARAMS_LONG_H = {**LGBM_PARAMS, "n_estimators": 600, "num_leaves": 63,
                      "min_child_samples": 30}


def _params_for(h: int) -> dict:
    return LGBM_PARAMS_LONG_H if h >= 4 else LGBM_PARAMS


def feature_names(side: str) -> list[str]:
    comps = HIT_COMPS if side == "hit" else PIT_COMPS
    names = ["age", "age_sq", "war_l1", "war_l2", "war_l3", "war_l1_missing",
             "war_l2_missing", "war_l3_missing", "age_x_war",
             "war_max3", "star_l1", "established",
             "expo_l1", "expo_l2", "expo_l3", "expo_trend",
             "season_idx", "role_flag", "profile_pwr", "profile_fin"]
    for c in comps:
        names += [f"m_{c}", f"rel_{c}"]          # Marcel-regressed + league-relative lag1
    if side == "hit":
        names += ["xiso_l1", "xiso_gap_l1", "xiso_missing"]
        names += list(DEF_FEATURE_KEYS)
    names += [f"champ_h{h}" for h in range(1, HORIZONS + 1)]
    return names


# Short hash of the FEATURE SCHEMA (both sides). Folded into every
# on-disk frame / point-in-time-bundle cache key so a feature change can
# never silently serve a stale-shaped vector — the cache filename simply
# misses and rebuilds.
_SCHEMA_TAG = hashlib.sha256(
    json.dumps({s: feature_names(s) for s in ("hit", "pit")},
               sort_keys=True).encode()).hexdigest()[:8]


def _league_mean(league: dict, season: int, side: str, comp: str):
    key = comp if side == "hit" else {"k_pct": "p_k_pct", "bb_pct": "p_bb_pct",
                                      "hr_bf": "p_hr_bf"}[comp]
    return fp._league_recent(league, season + 1, key)


def build_features(hist: list[dict], side: str, base: int, age: float | None,
                   curves: dict, war_map: dict, league: dict,
                   champ: dict | None = None,
                   in_progress: tuple[int, float] | None = None) -> list[float] | None:
    """One feature vector from history rows (seasons <= base-1) — the same
    inputs the champion sees, plus the champion's own path as stack
    features. Returns None when the champion itself can't project (no
    usable history), keeping challenger/champion populations identical.
    ``champ`` lets the live dispatch pass its already-computed CHAMPION
    path (and prevents recursion — the stack feature is always the
    champion, never the ML model feeding itself)."""
    if champ is None:
        champ = fm.contract_war_path(hist, side, base, HORIZONS, age,
                                     curves, war_map, league, use_ml=False)
    if champ is None or age is None:
        return None
    by_season = {h["season"]: h for h in hist}
    expo_key = "pa" if side == "hit" else "bf"

    def lag(season, key):
        r = by_season.get(season)
        return r.get(key) if r else None

    wl = [lag(base - k, "war") for k in (1, 2, 3)]
    el = [lag(base - k, expo_key) for k in (1, 2, 3)]
    # In-progress (LIVE) correction: the heads trained on COMPLETED seasons, so
    # at inference the most-recent lag (base-1) being a partial season is a
    # train/serve distribution shift - the trees read a 105-PA / 0.5-WAR
    # half-season as a bad FULL season and project a cliff (the Lindor case).
    # Lift the base-1 WAR and exposure lags to their full-season equivalent by
    # reliability-blending toward the prior completed season, weighted by the
    # unobserved fraction (1-frac): healthy regulars whose current pace matches
    # their track record are ~unchanged; only limited/injured veterans lift.
    # Training callers pass in_progress=None, so the fitted distribution is
    # untouched.
    if in_progress and (base - 1) == in_progress[0] and in_progress[1] > 0:
        rem = 1.0 - float(in_progress[1])
        est_war = lag(base - 2, "war") or 0.0
        est_exp = lag(base - 2, expo_key) or 0.0
        if wl[0] is not None:
            wl[0] = wl[0] + rem * est_war
        if el[0] is not None:
            el[0] = el[0] + rem * est_exp
    feats = [
        float(age), float(age) ** 2,
        wl[0] if wl[0] is not None else 0.0,
        wl[1] if wl[1] is not None else 0.0,
        wl[2] if wl[2] is not None else 0.0,
        1.0 if wl[0] is None else 0.0,
        1.0 if wl[1] is None else 0.0,
        1.0 if wl[2] is None else 0.0,
        float(age) * (wl[0] if wl[0] is not None else 0.0),
        # Star-regime markers: the zero-inflated long-horizon labels drown
        # the (rare) stars unless the trees can isolate the regime cheaply.
        max(v for v in (wl[0], wl[1], wl[2], 0.0) if v is not None),
        1.0 if (wl[0] or 0.0) >= 4.0 else 0.0,
        1.0 if all(v is not None and v >= 2.0 for v in wl[:2]) else 0.0,
        el[0] or 0.0, el[1] or 0.0, el[2] or 0.0,
        (el[0] or 0.0) - (el[1] or 0.0),
        float(base),
        1.0 if (side == "hit" and hist[0].get("role") == "C") or
               (side == "pit" and hist[0].get("role") == "SP") else 0.0,
    ]
    prof = fp.profile_role(hist, side, "X", league)
    feats += [1.0 if prof.endswith("|pwr") else 0.0,
              1.0 if prof.endswith("|fin") else 0.0]
    # Marcel-regressed components (the champion's own projection inputs) +
    # league-relative lag-1 raw rates.
    proj = fp.project_player(hist, side, base, curves, league, int(age))
    comps = HIT_COMPS if side == "hit" else PIT_COMPS
    for c in comps:
        m = (proj or {}).get(c)
        feats.append(m if m is not None else 0.0)
        raw = lag(base - 1, c)
        lgm = _league_mean(league, base - 1, side, c)
        feats.append((raw - lgm) if (raw is not None and lgm is not None) else 0.0)
    if side == "hit":
        mlbam = hist[0].get("mlbam")
        x = fp._xstats().get((mlbam, base - 1)) if mlbam else None
        iso1 = lag(base - 1, "iso")
        feats += [x if x is not None else 0.0,
                  (x - iso1) if (x is not None and iso1 is not None) else 0.0,
                  1.0 if x is None else 0.0]
        if DEF_FEATURE_KEYS:
            dvals = _def_prior(mlbam, base)
            feats += [dvals[k] for k in DEF_FEATURE_KEYS]
    feats += [champ["war_by_year"][h - 1] for h in range(1, HORIZONS + 1)]
    return feats


def build_training_frame(corpus: dict, first_base: int, max_label_season: int,
                         use_cache: bool = True) -> dict:
    """{side: {"X": ndarray, "y": {h: ndarray}, "label_season": {h: ndarray}}}
    over every (player, base) with base in [first_base, ...] such that ALL
    horizon labels respect label_season <= max_label_season... per-horizon:
    a row contributes to horizon h only when base+h-1 <= max_label_season
    (later horizons simply have fewer rows — no truncation bias from
    requiring all five). Disk-cached per (first_base, max_label_season,
    corpus span) since assembly walks the full corpus."""
    cache = (fp.CACHE_DIR /
             f"proj_ml_frame_{_SCHEMA_TAG}_{first_base}_{max_label_season}_{corpus['first']}_{corpus['last']}.pkl")
    if use_cache and cache.exists():
        import pickle
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    league = corpus["league"]
    by_player = {"hit": {}, "pit": {}}
    war_actual: dict[tuple, float] = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side].setdefault(r["mlbam"], {})[r["season"]] = r
                if r.get("war") is not None:
                    key = (r["mlbam"], r["season"])
                    war_actual[key] = war_actual.get(key, 0.0) + r["war"]
    out = {}
    for side in ("hit", "pit"):
        X, y, ls = [], {h: [] for h in range(1, HORIZONS + 1)}, {h: [] for h in range(1, HORIZONS + 1)}
        row_idx = {h: [] for h in range(1, HORIZONS + 1)}
        for base in range(first_base, max_label_season + 1):
            curves, war_map = fp.fitted_models(corpus, base - 1)
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (base - 1, base - 2, base - 3) if t in seasons]
                if not hist:
                    continue
                age_prev = next((h.get("age") for h in hist if h.get("age")), None)
                if age_prev is None:
                    continue
                age = age_prev + (base - hist[0]["season"])
                feats = build_features(hist, side, base, age, curves, war_map, league)
                if feats is None:
                    continue
                i = len(X)
                X.append(feats)
                for h in range(1, HORIZONS + 1):
                    target = base + h - 1
                    if target > max_label_season:
                        continue
                    y[h].append(war_actual.get((mlbam, target), 0.0))
                    ls[h].append(target)
                    row_idx[h].append(i)
        out[side] = {"X": np.asarray(X, dtype=float),
                     "y": {h: np.asarray(v, dtype=float) for h, v in y.items()},
                     "rows": {h: np.asarray(v, dtype=int) for h, v in row_idx.items()},
                     "label_season": {h: np.asarray(v, dtype=int) for h, v in ls.items()}}
    if use_cache:
        import pickle
        fp.CACHE_DIR.mkdir(exist_ok=True)
        with open(cache, "wb") as fh:
            pickle.dump(out, fh)
    return out


def train(corpus: dict, max_label_season: int, first_base: int = 2003,
          quantiles: tuple = QUANTILES) -> dict:
    """Train quantile heads on labels <= max_label_season. Returns
    {side: {h: {q: model}}} plus meta. ``quantiles`` lets point-in-time
    consumers (historical corpus enrichment) train the lean
    (q10/q50/q90) set instead of all five."""
    from lightgbm import LGBMRegressor
    frame = build_training_frame(corpus, first_base, max_label_season)
    models: dict = {"meta": {
        "version": MODEL_VERSION, "max_label_season": max_label_season,
        "first_base": first_base, "params": dict(LGBM_PARAMS),
        "quantiles": list(quantiles),
        "features": {s: feature_names(s) for s in ("hit", "pit")},
    }}
    for side in ("hit", "pit"):
        models[side] = {}
        f = frame[side]
        for h in range(1, HORIZONS + 1):
            rows = f["rows"][h]
            if len(rows) < 500:
                continue
            Xh, yh = f["X"][rows], f["y"][h]
            models[side][h] = {}
            for q in quantiles:
                m = LGBMRegressor(alpha=q, **_params_for(h))
                m.fit(Xh, yh)
                models[side][h][q] = m
        log.info("proj_ml %s: trained %d horizons on <=%d labels (n_h1=%d)",
                 side, len(models[side]), max_label_season,
                 len(f["rows"][1]))
    # training-data hash (shape + sums — cheap, deterministic)
    hsh = hashlib.sha256()
    for side in ("hit", "pit"):
        f = frame[side]
        hsh.update(str(f["X"].shape).encode())
        hsh.update(np.ascontiguousarray(f["X"].sum(axis=0)).tobytes())
    models["meta"]["train_hash"] = hsh.hexdigest()[:16]
    return models


# star_l1 flag position in the feature vector (feature_names index 10) -
# the ex-ante star-slice gate for the mean blend below.
_STAR_FLAG_IDX = 10


def _predict1(head, x) -> float:
    """Single-row predict via the raw LightGBM Booster -- ~7x faster than the
    LGBMRegressor sklearn wrapper (which re-validates the ndarray on every call),
    byte-identical output (verified max-abs-diff 0.0). predict_path scores ONE player
    at a time, so a single proj_export issues 38k+ single-row predicts where the wrapper
    overhead dominated (~25s -> ~3.5s). Falls back to the wrapper if booster_ is absent."""
    b = getattr(head, "booster_", None)
    return float((b.predict(x) if b is not None else head.predict(x))[0])


def _implied_mean(q10, q25, q50, q75, q90) -> float:
    """Distribution mean implied by the five quantile heads (trapezoid
    quadrature). The median ignores the right-tail mass; for the star
    regime (zero-inflated labels pulling q50 down) the implied mean is
    the principled recentering target."""
    return (q10 + 2 * q25 + 2 * q50 + 2 * q75 + q90) / 8.0


def predict_path(models: dict, feats: list[float], side: str) -> dict | None:
    """Quantile paths for one player: {war_by_year (q50), _p10, _p90 and,
    when trained, _p25/_p75}. Monotone-sorted across quantiles per
    horizon; NO zero floor.

    STAR MEAN BLEND (the Phase-1 disclosed-miss fix): when the bundle
    meta carries `star_blend` ({h: lambda}) and the row is in the
    EX-ANTE star slice (base-season WAR >= 4 - the star_l1 feature),
    the point prediction blends q50 toward the quantile-implied mean:
    q50' = q50 + lambda_h * (mean - q50). Bands untouched; non-star rows
    untouched. Lambdas are fitted forward-chained on the dev bases
    (tools/fit_star_blend.py) and committed in data/proj_star_blend.json."""
    if side not in models or not models[side]:
        return None
    # Schema guard: a bundle trained on a DIFFERENT feature vector than the
    # caller built (e.g. a live v1 bundle being served new-schema features
    # mid-upgrade) must fall back to the champion, never mis-predict on a
    # mismatched-width vector. Bundles carry their training schema in meta.
    meta_feats = (models.get("meta") or {}).get("features", {}).get(side)
    if meta_feats and len(feats) != len(meta_feats):
        log.warning("proj_ml %s: feature width %d != bundle schema %d — "
                    "falling back to champion", side, len(feats), len(meta_feats))
        return None
    qs = tuple(models["meta"].get("quantiles") or QUANTILES)
    x = np.asarray(feats, dtype=float).reshape(1, -1)
    by_q = {q: [] for q in qs}
    for h in range(1, HORIZONS + 1):
        heads = models[side].get(h)
        if not heads:
            return None
        preds = sorted(_predict1(heads[q], x) for q in qs)
        for q, v in zip(sorted(qs), preds):
            by_q[q].append(v)
    full_qs = all(q in by_q for q in QUANTILES)
    raw_q50 = list(by_q[0.50])  # pre-recenter medians, for the if-healthy display path
    # GLOBAL mean blend (the across-the-board recenter): the q50 head is
    # MAE-optimal but, for the right-skewed/zero-inflated WAR label, sits below
    # the expected value - so the displayed point projection reads systematically
    # LOW for every player (forward-chained + holdout bias ~ -0.15 WAR at all
    # horizons). Recenter q50 toward the quantile-implied mean for ALL rows:
    #   q50' = q50 + lambda_h * (implied_mean - q50)
    # Bands (q10/q90) untouched. Self-scaling: high-skew profiles (upside arms,
    # young bats) lift more than flat replacement-level rows. Lambdas fitted
    # forward-chained + holdout-confirmed (tools/fit_mean_blend.py),
    # data/proj_mean_blend.json.
    gblend = models["meta"].get("mean_blend") or {}
    if gblend and full_qs:
        for t in range(HORIZONS):
            lam = float(gblend.get(str(t + 1)) or gblend.get(t + 1) or 0.0)
            if lam <= 0:
                continue
            mean = _implied_mean(by_q[0.10][t], by_q[0.25][t], by_q[0.50][t],
                                 by_q[0.75][t], by_q[0.90][t])
            # LIFT-ONLY: recenter under-projected (right-skewed) rows UP toward
            # the expected value; never pull a projection DOWN. A symmetric
            # recenter trimmed ceiling stars (mean < median when the downside
            # tail dominates), which contradicts the "low across the board"
            # intent - the band (q90) already carries that downside.
            shift = lam * (mean - by_q[0.50][t])
            if shift > 0:
                by_q[0.50][t] = by_q[0.50][t] + shift
    # STAR top-up blend (additional, star rows only) - kept for any residual
    # star-slice miss the global recenter leaves; inert when its lambdas are 0.
    blend = models["meta"].get("star_blend") or {}
    if blend and full_qs and len(feats) > _STAR_FLAG_IDX and feats[_STAR_FLAG_IDX] >= 1.0:
        for t in range(HORIZONS):
            lam = float(blend.get(str(t + 1)) or blend.get(t + 1) or 0.0)
            if lam <= 0:
                continue
            mean = _implied_mean(by_q[0.10][t], by_q[0.25][t], by_q[0.50][t],
                                 by_q[0.75][t], by_q[0.90][t])
            by_q[0.50][t] = by_q[0.50][t] + lam * (mean - by_q[0.50][t])
    out = {"war_by_year": [round(v, 2) for v in by_q[0.50]],
           "war_by_year_p10": [round(v, 2) for v in by_q[0.10]],
           "war_by_year_p90": [round(v, 2) for v in by_q[0.90]]}
    if 0.25 in by_q:
        out["war_by_year_p25"] = [round(v, 2) for v in by_q[0.25]]
    if 0.75 in by_q:
        out["war_by_year_p75"] = [round(v, 2) for v in by_q[0.75]]
        # Playing-time-held (if-healthy) DISPLAY path: the 70th percentile of the
        # modelled outcome distribution (q70 = q50 + 0.8*(q75-q50)), floored at
        # the expected-value central. /projections/ shows this so a star's
        # out-years read at their healthy level instead of the attrition-
        # discounted mean; it is NEVER used for surplus / FA valuation, which
        # keep war_by_year (the expected value). Only present with full quantiles
        # (the live bundle), so the PIT/gate path is unaffected.
        out["war_by_year_pth"] = [
            round(max(by_q[0.50][t], raw_q50[t] + 0.8 * (by_q[0.75][t] - raw_q50[t])), 2)
            for t in range(len(by_q[0.50]))]
    return out


_PIT_CACHE: dict[int, dict] = {}
LEAN_QUANTILES = (0.10, 0.50, 0.90)


def train_cached(corpus: dict, max_label_season: int,
                 quantiles: tuple = LEAN_QUANTILES) -> dict:
    """Point-in-time bundle for HISTORICAL consumers (Gate 2's corpus
    enrichment): trained on labels <= max_label_season only, disk-cached —
    the no-lookahead twin of fp.fitted_models. The shipped live bundle
    (model/proj_lgbm) must NEVER enrich historical winters: it has seen
    their outcomes."""
    if max_label_season in _PIT_CACHE:
        return _PIT_CACHE[max_label_season]
    import joblib
    qtag = "".join(str(int(q * 100)) for q in quantiles)
    cache = fp.CACHE_DIR / f"proj_ml_pit_{MODEL_VERSION}_{_SCHEMA_TAG}_{max_label_season}_{qtag}.joblib"
    if cache.exists():
        _PIT_CACHE[max_label_season] = joblib.load(cache)
        return _PIT_CACHE[max_label_season]
    models = train(corpus, max_label_season, quantiles=quantiles)
    fp.CACHE_DIR.mkdir(exist_ok=True)
    joblib.dump(models, cache, compress=3)
    _PIT_CACHE[max_label_season] = models
    return models


def save(models: dict, path: Path | None = None) -> Path:
    import joblib
    path = path or MODEL_DIR
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(models, path / "models.joblib", compress=3)
    (path / "meta.json").write_text(json.dumps(models["meta"], indent=1),
                                    encoding="utf-8")
    return path


_LOADED: dict | None = None


def load(path: Path | None = None) -> dict | None:
    """Live loader (memoized). None when no bundle is shipped — consumers
    fall back to the champion decay."""
    global _LOADED
    if _LOADED is not None:
        return _LOADED or None
    import joblib
    p = (path or MODEL_DIR) / "models.joblib"
    if not p.exists():
        _LOADED = {}
        return None
    _LOADED = joblib.load(p)
    return _LOADED
