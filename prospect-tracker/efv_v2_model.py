# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v2 champion H0: the consensus-offset hurdle with ridge heads (EV-09).

docs/efv-v2/PROGRAM.md s3.1 and s3.4. CODE ONLY IN THIS STEP: nothing here is served.
The board grade, the Source Comparison score and every price still read eFV v1
(efv_model / efv_score); H0 is adjudicated only on the reserved frames after
docs/efv-v2/EFV_V2_GATE.md commits.

THE MODEL.

    score_v2          = P(REACHED | x) * E[WAR | REACHED, x]
    logit P(REACHED)  = f_R(consensus_fv) + ridge_R(x)
    E[WAR | REACHED]  = f_W(consensus_fv) + ridge_W(x)

    f_R, f_W   within-fold maps on the consensus FV, fitted on the fold's training rows
               only and then FIXED as offsets: f_R a two-parameter logistic regression of
               REACHED on consensus FV, f_W a two-parameter weighted least-squares line of
               the six-season WAR target on consensus FV over the reached rows. Both are
               continuous in the grade and neither is ever tabulated by grade level.
    ridge_R    a penalized logistic head on the standardized v1 feature vector (the
               consensus FV itself left out), fitted WITH the f_R offset, so it can only
               learn what the consensus does not already explain.
    ridge_W    the same for the WAR residual (target minus f_W), weighted least squares
               with the v1 censoring weights.
    penalties  one per head, chosen by NESTED FORWARD-CHAINED CV inside the fold's
               training years: every training year y with enough rows on both sides of
               it is an inner test year, scored by a fit on training years before y
               (offsets refitted there too). The grid ends at an infinite penalty, which
               switches the head off, so "consensus alone" is always a candidate and v1's
               pinned blend weight (0.70 / 0.57) has no counterpart here: it disappears
               into the penalty. Ties go to the larger penalty.
    no clip    v1 floors the consensus leg at 0 WAR and the model leg at -2 WAR. H0 has
               no floor anywhere: a negative expected WAR stays negative, so the 131-row
               tie the clip made on the vintage-matched frame ([E1] b_p5) cannot recur.

LIVENESS DOMAIN. With both heads removed the score is sigma(f_R(fv)) * f_W(fv), which is
increasing in fv wherever f_W(fv) > -f_W' / ((1 - P) * f_R'), and only there. With no
clip, f_W is negative at the bottom of the grade range (about -1 WAR at a 35 on the hitter
folds), so the composite can turn below the observed range; offset_curve_is_monotone
reports it instead of assuming it, and the development read records it for every fold
over the grades that fold scores. On every real fold today it holds.

TRAINING DATA. The v1 matrices (efv_dataset.matrix_path) with v1's own pool rule
(recent never-MLB busts excluded, the CENSORED-NEVER rows of BUST2) and v1's target
(target_censored, the six-season label with v1's censoring rule, weighted by v1's
observed-fraction weight). REACHED is the matrix's own split: a debuted row reached, a
bust row did not. The heads read exactly v1's feature columns (efv_model._feature_spec)
minus the consensus FV, so H0 holds v1's information set: it is a coherence repair
registered as NON-INFERIOR to v1, not a source of lift (PROGRAM.md s3.1).

ONE OUTPUT. score_v2 is the only number the model emits per player. served_views()
derives the board order, the Source Comparison score and the pricing grade from it and
from nothing else, so the three orderings cannot disagree (PROGRAM.md s3.1; v1 has
three: the board sorts on the model leg, the comparison scores the blend).

DETERMINISM. Every fit is closed form or a fixed Newton iteration from a zero start;
nothing is random. The only random step anywhere on this path is the development read's
bootstrap, which takes an explicit seed. The same inputs and seed reproduce every
number bit for bit (test_efv_v2_model.py).

RESERVED FRAMES. oos_scores refuses any year at or after
efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR, and lv_scores refuses any list vintage in
RESERVED_LV without the committed gate's sha (efv_vintage_frame.guard_score_request).

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the consensus FV enters only as a
continuous regressor inside a map. Nothing here groups, counts or averages rows by
consensus-FV level; test_efv_v2_model.py scans the source for it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import efv_model as V1
import efv_vintage_frame as F
import source_backtest as SB

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
#: The development read's artifact (tools/efv_v2_dev_read.py writes it).
DEV_EVAL_PATH = DATA_DIR / "efv_v2_dev_eval.json"

MODEL_ID = "efv_v2_h0"
#: Ridge penalty grid for both heads, on standardized columns. The last entry switches
#: the head off (consensus offset alone).
ALPHAS: tuple[float, ...] = (0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0,
                             3000.0, math.inf)
#: v1's fold gates (efv_model.oos_grades): a scored year needs this many test rows and
#: this many training rows. The inner CV uses the same pair.
MIN_TEST_ROWS = 15
MIN_TRAIN_ROWS = 60
#: The default seed of the development read's bootstrap: the claim instruments' own
#: seed, so a v1 leg on the vintage-matched frame reproduces the served interval. The
#: model itself draws nothing.
SEED = SB._CLAIM_SEED
#: Newton iterations for the logistic fits (a fixed count from a zero start keeps the
#: result bit-reproducible; the tolerance only ends it early).
_NEWTON_MAX_IT = 100
_NEWTON_TOL = 1e-12
#: A vanishing penalty on the two offset parameters so a separable training fold still
#: has a finite MLE. Changes no fit that has one.
_OFFSET_EPS = 1e-8


# ---------------------------------------------------------------------------
# columns and data
# ---------------------------------------------------------------------------

def head_keys(side: str) -> list[str]:
    """v1's feature columns for the side, minus the consensus FV (the offset holds it)."""
    keys, _mono = V1._feature_spec(side)
    return [k for k in keys if k != "fv"]


def training_rows(side: str) -> list[dict]:
    """v1's labeled pool for the side, prepared as efv_model._prep does, plus `reached`
    (1.0 debuted, 0.0 never-MLB bust). Recent busts are left out exactly as v1 leaves
    them out: they may still reach, so they are neither REACHED nor resolved never."""
    rows = json.loads(_matrix_path(side).read_text(encoding="utf-8"))
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = V1._prep(full, "target_censored", side)
    for d in data:
        d["reached"] = 1.0 if d["kind"] == "debuted" else 0.0
    return data


def _matrix_path(side: str) -> Path:
    from efv_dataset import matrix_path
    return matrix_path(side)


def _xmat(rows: list[dict], keys: list[str]) -> np.ndarray:
    if not rows:
        return np.zeros((0, len(keys)))
    return np.array([[float(r["feats"].get(k, 0.0)) for k in keys] for r in rows],
                    dtype=np.float64)


def _standardize(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = X.mean(axis=0) if X.shape[0] else np.zeros(X.shape[1])
    sd = X.std(axis=0) if X.shape[0] else np.ones(X.shape[1])
    sd = np.where(sd > 0, sd, 1.0)
    return mu, sd


def _sigmoid(z):
    """Numerically stable logistic, exp(-log(1 + exp(-z)))."""
    return np.exp(-np.logaddexp(0.0, -np.asarray(z, dtype=np.float64)))


# ---------------------------------------------------------------------------
# the two primitive fits
# ---------------------------------------------------------------------------

def _logistic(Z: np.ndarray, y: np.ndarray, offset: np.ndarray,
              penalty: np.ndarray) -> np.ndarray:
    """Penalized logistic regression with an offset, by Newton from zero:
    maximize sum(y*eta - log(1 + e^eta)) - 0.5 * sum(penalty * beta^2),
    eta = offset + Z @ beta. `penalty` is per column (0 leaves a column free)."""
    beta = np.zeros(Z.shape[1])
    P = np.diag(penalty)
    for _ in range(_NEWTON_MAX_IT):
        eta = offset + Z @ beta
        p = _sigmoid(eta)
        g = Z.T @ (y - p) - penalty * beta
        H = (Z * (p * (1.0 - p))[:, None]).T @ Z + P
        step = np.linalg.solve(H, g)
        beta = beta + step
        if float(np.max(np.abs(step))) < _NEWTON_TOL:
            break
    return beta


def _wls(Z: np.ndarray, y: np.ndarray, w: np.ndarray, penalty: np.ndarray) -> np.ndarray:
    """Weighted least squares with a per-column ridge penalty (0 leaves a column free)."""
    WZ = Z * w[:, None]
    return np.linalg.solve(WZ.T @ Z + np.diag(penalty), WZ.T @ y)


# ---------------------------------------------------------------------------
# offsets and heads
# ---------------------------------------------------------------------------

def fit_offsets(train: list[dict]) -> dict | None:
    """f_R and f_W on the training rows. None when the rows cannot support them
    (fewer than two reached and two never rows, or a constant consensus)."""
    reached = [r for r in train if r["reached"] == 1.0]
    never = [r for r in train if r["reached"] == 0.0]
    if len(reached) < 2 or len(never) < 2:
        return None
    fv = np.array([r["fv"] for r in train], dtype=np.float64)
    if float(fv.std()) <= 0:
        return None
    Z = np.column_stack([np.ones(fv.size), fv])
    y = np.array([r["reached"] for r in train], dtype=np.float64)
    r_ab = _logistic(Z, y, np.zeros(fv.size), np.full(2, _OFFSET_EPS))
    fvw = np.array([r["fv"] for r in reached], dtype=np.float64)
    if float(fvw.std()) <= 0:
        return None
    Zw = np.column_stack([np.ones(fvw.size), fvw])
    tw = np.array([r["target"] for r in reached], dtype=np.float64)
    ww = np.array([max(float(r.get("weight", 1.0) or 0.0), 1e-3) for r in reached])
    w_cd = _wls(Zw, tw, ww, np.zeros(2))
    return {"r": [float(r_ab[0]), float(r_ab[1])], "w": [float(w_cd[0]), float(w_cd[1])]}


def _off_r(off: dict, fv) -> np.ndarray:
    return off["r"][0] + off["r"][1] * np.asarray(fv, dtype=np.float64)


def _off_w(off: dict, fv) -> np.ndarray:
    return off["w"][0] + off["w"][1] * np.asarray(fv, dtype=np.float64)


def _fit_head_w(rows: list[dict], keys: list[str], off: dict, alpha: float) -> dict:
    """ridge_W on the reached rows: the WAR residual after f_W, intercept free."""
    reached = [r for r in rows if r["reached"] == 1.0]
    X = _xmat(reached, keys)
    mu, sd = _standardize(X)
    resid = (np.array([r["target"] for r in reached], dtype=np.float64)
             - _off_w(off, [r["fv"] for r in reached]))
    w = np.array([max(float(r.get("weight", 1.0) or 0.0), 1e-3) for r in reached])
    if math.isinf(alpha) or not keys:
        b0 = float(np.average(resid, weights=w)) if resid.size else 0.0
        beta = np.zeros(len(keys))
    else:
        Z = np.column_stack([np.ones(len(reached)), (X - mu) / sd])
        pen = np.concatenate([[0.0], np.full(len(keys), float(alpha))])
        coef = _wls(Z, resid, w, pen)
        b0, beta = float(coef[0]), coef[1:]
    return {"alpha": alpha, "mu": mu.tolist(), "sd": sd.tolist(), "b0": b0,
            "beta": [float(b) for b in beta]}


def _fit_head_r(rows: list[dict], keys: list[str], off: dict, alpha: float) -> dict:
    """ridge_R on every row: REACHED with the f_R offset, intercept free."""
    X = _xmat(rows, keys)
    mu, sd = _standardize(X)
    y = np.array([r["reached"] for r in rows], dtype=np.float64)
    o = _off_r(off, [r["fv"] for r in rows])
    if math.isinf(alpha) or not keys:
        coef = _logistic(np.ones((len(rows), 1)), y, o, np.zeros(1))
        b0, beta = float(coef[0]), np.zeros(len(keys))
    else:
        Z = np.column_stack([np.ones(len(rows)), (X - mu) / sd])
        pen = np.concatenate([[0.0], np.full(len(keys), float(alpha))])
        coef = _logistic(Z, y, o, pen)
        b0, beta = float(coef[0]), coef[1:]
    return {"alpha": alpha, "mu": mu.tolist(), "sd": sd.tolist(), "b0": b0,
            "beta": [float(b) for b in beta]}


def _head_value(head: dict | None, X: np.ndarray) -> np.ndarray:
    if head is None:
        return np.zeros(X.shape[0])
    mu, sd = np.asarray(head["mu"]), np.asarray(head["sd"])
    beta = np.asarray(head["beta"], dtype=np.float64)
    if beta.size == 0:
        return np.full(X.shape[0], float(head["b0"]))
    return head["b0"] + ((X - mu) / sd) @ beta


# ---------------------------------------------------------------------------
# nested forward-chained penalty selection
# ---------------------------------------------------------------------------

def inner_years(train: list[dict]) -> list[int]:
    """Training years that can serve as an inner test year: at least MIN_TEST_ROWS rows
    in the year and MIN_TRAIN_ROWS rows in the years before it."""
    ys = sorted({int(r["decision_year"]) for r in train})
    out = []
    for y in ys:
        n_te = sum(1 for r in train if r["decision_year"] == y)
        n_tr = sum(1 for r in train if r["decision_year"] < y)
        if n_te >= MIN_TEST_ROWS and n_tr >= MIN_TRAIN_ROWS:
            out.append(y)
    return out


def select_alphas(train: list[dict], keys: list[str],
                  alphas: tuple[float, ...] = ALPHAS) -> dict:
    """Penalty per head by nested forward-chained CV over the training years only.

    Inner loss: ridge_W, the weighted squared error of the WAR residual on the inner
    test year's reached rows; ridge_R, the mean log loss of REACHED on all its rows.
    Losses are summed over inner years. The argmin wins; a tie goes to the larger
    penalty (the grid is walked from the top). No inner year: both heads off."""
    loss_w = {a: 0.0 for a in alphas}
    loss_r = {a: 0.0 for a in alphas}
    used_w, used_r = [], []
    for y in inner_years(train):
        tr = [r for r in train if r["decision_year"] < y]
        te = [r for r in train if r["decision_year"] == y]
        off = fit_offsets(tr)
        if off is None:
            continue
        te_reached = [r for r in te if r["reached"] == 1.0]
        Xr_te = _xmat(te, keys)
        yr_te = np.array([r["reached"] for r in te], dtype=np.float64)
        or_te = _off_r(off, [r["fv"] for r in te])
        Xw_te = _xmat(te_reached, keys)
        tw_te = np.array([r["target"] for r in te_reached], dtype=np.float64)
        ow_te = _off_w(off, [r["fv"] for r in te_reached])
        ww_te = np.array([max(float(r.get("weight", 1.0) or 0.0), 1e-3)
                          for r in te_reached])
        do_w = bool(te_reached) and sum(1 for r in tr if r["reached"] == 1.0) >= 2
        for a in alphas:
            hr = _fit_head_r(tr, keys, off, a)
            eta = or_te + _head_value(hr, Xr_te)
            loss_r[a] += float(np.sum(np.logaddexp(0.0, eta) - yr_te * eta))
            if do_w:
                hw = _fit_head_w(tr, keys, off, a)
                pred = ow_te + _head_value(hw, Xw_te)
                loss_w[a] += float(np.sum(ww_te * (tw_te - pred) ** 2))
        used_r.append(y)
        if do_w:
            used_w.append(y)

    def _argmin(loss, used):
        if not used:
            return math.inf
        best = None
        for a in sorted(alphas, reverse=True):
            if best is None or loss[a] < loss[best]:
                best = a
        return best

    return {"alpha_w": _argmin(loss_w, used_w), "alpha_r": _argmin(loss_r, used_r),
            "inner_years_w": used_w, "inner_years_r": used_r,
            "loss_w": {_akey(a): loss_w[a] for a in alphas},
            "loss_r": {_akey(a): loss_r[a] for a in alphas}}


def _akey(a: float) -> str:
    return "off" if math.isinf(a) else repr(float(a))


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------

def fit(train: list[dict], side: str, *, keys: list[str] | None = None,
        alphas: tuple[float, ...] = ALPHAS) -> dict | None:
    """H0 on one fold's training rows. None when the offsets cannot be fitted."""
    keys = list(head_keys(side) if keys is None else keys)
    off = fit_offsets(train)
    if off is None:
        return None
    sel = select_alphas(train, keys, alphas)
    return {"model_id": MODEL_ID, "side": side, "keys": keys, "offset": off,
            "head_r": _fit_head_r(train, keys, off, sel["alpha_r"]),
            "head_w": _fit_head_w(train, keys, off, sel["alpha_w"]),
            "selection": sel, "n_train": len(train),
            "n_reached": sum(1 for r in train if r["reached"] == 1.0),
            "train_years": sorted({int(r["decision_year"]) for r in train})}


def offset_only(model: dict) -> dict:
    """The same model with both heads removed: score = f(consensus FV) alone."""
    out = dict(model)
    out["head_r"] = None
    out["head_w"] = None
    return out


def predict(model: dict, rows: list[dict]) -> list[dict]:
    """[{p_reached, e_war_reached, score}] per row (rows carry `feats` and `fv`).
    No floor on any term."""
    if not rows:
        return []
    X = _xmat(rows, model["keys"])
    fv = np.array([r["fv"] for r in rows], dtype=np.float64)
    p = _sigmoid(_off_r(model["offset"], fv) + _head_value(model["head_r"], X))
    e = _off_w(model["offset"], fv) + _head_value(model["head_w"], X)
    s = p * e
    return [{"p_reached": float(p[i]), "e_war_reached": float(e[i]), "score": float(s[i])}
            for i in range(len(rows))]


def offset_curve_is_monotone(model: dict, fv_lo: float, fv_hi: float,
                             n: int = 2001) -> bool:
    """True when the offset-only score is strictly increasing in the consensus FV on
    [fv_lo, fv_hi]; the condition under which heads-off H0 orders rows exactly as the
    consensus does. Checked on a fine grid (a liveness receipt, not a fit)."""
    if fv_hi <= fv_lo:
        return True
    g = np.linspace(float(fv_lo), float(fv_hi), int(n))
    s = _sigmoid(_off_r(model["offset"], g)) * _off_w(model["offset"], g)
    return bool(np.all(np.diff(s) > 0))


# ---------------------------------------------------------------------------
# one output: board, comparison score and price all come from score_v2
# ---------------------------------------------------------------------------

def served_views(scores: dict[str, float], consensus: dict[str, float]) -> dict:
    """The three consumers of a grade, derived from score_v2 and nothing else.

    board_order     player keys by score descending (key ascending on an exact tie)
    comparison      the score itself (what the Source Comparison ranks)
    price_grade     the score carried onto the consensus grade scale by rank: the
                    player at score percentile q takes the consensus value at
                    percentile q of the same pool (source_backtest's display
                    convention), so the pricing input orders players exactly as
                    the score does, ties aside. Never read by a served price in
                    this step."""
    keys = sorted(scores, key=lambda k: (-scores[k], k))
    pool = [k for k in keys if consensus.get(k) is not None]
    cons_sorted = sorted(float(consensus[k]) for k in pool)
    m = len(pool)
    price = {}
    for pos, k in enumerate(reversed(pool)):
        pp = pos / (m - 1) if m > 1 else 0.0
        price[k] = cons_sorted[min(m - 1, int(round(pp * (m - 1))))]
    return {"board_order": keys, "comparison": {k: scores[k] for k in keys},
            "price_grade": price}


# ---------------------------------------------------------------------------
# forward-chained out-of-sample scores on the v1 matrices (the vintage-matched frame)
# ---------------------------------------------------------------------------

def _check_years(years) -> list[int]:
    ys = [int(y) for y in years]
    bad = [y for y in ys if y >= F.R_VM_FIRST_DEBUT_YEAR]
    if bad:
        raise F.ReservedFrameError(
            f"years {bad} reach the reserved R-VM cohorts (first "
            f"{F.R_VM_FIRST_DEBUT_YEAR}); see docs/efv-v2/PROGRAM.md s2.4")
    return ys


def pinned_inputs(side: str, data: list[dict], receipts: dict | None = None) -> dict:
    """EV-01 timing pin, the same rule efv_model.oos_grades(timing_pin=True) applies:
    each debuted row's prior block read at the raters' preseason point of its decision
    year. {player_key: {"feats", "fv"}}; rows with no in-window consensus are absent."""
    import efv_dataset as _ed
    recs = _ed.asof_records()
    raw_rows = json.loads(_matrix_path(side).read_text(encoding="utf-8"))
    raw_by_key = {r["player_key"]: r for r in raw_rows
                  if not (r["kind"] == "bust" and r.get("bust_recent"))}
    out = {}
    for d in data:
        if d["kind"] != "debuted":
            continue
        raw = raw_by_key.get(d["player_key"])
        pre = _ed.preseason_consensus_asof(recs.get(d["player_key"]),
                                           d["decision_year"], side)
        if raw is None or pre is None:
            continue
        row = dict(raw)
        row.update(pre)
        row.pop("fv_effective", None)
        out[d["player_key"]] = {"feats": V1._vec(row, side),
                                "fv": float(pre["consensus_fv_raw"])}
        if receipts is not None:
            receipts[d["player_key"]] = {
                "asof_date": pre.get("asof_date"),
                "window_year": d["decision_year"],
                "consensus_fv_raw": float(pre["consensus_fv_raw"])}
    return out


def fold_models(side: str, *, years=V1.SCORED_YEARS, data: list[dict] | None = None,
                alphas: tuple[float, ...] = ALPHAS) -> dict[int, dict]:
    """{year: H0 fit on decision years before it}, with v1's fold gates."""
    years = _check_years(years)
    data = training_rows(side) if data is None else data
    out = {}
    for yr in years:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < MIN_TEST_ROWS or len(tr) < MIN_TRAIN_ROWS:
            continue
        m = fit(tr, side, alphas=alphas)
        if m is not None:
            out[yr] = m
    return out


def oos_scores(side: str, *, timing_pin: bool = False, receipts: dict | None = None,
               heads: bool = True, years=V1.SCORED_YEARS, data: list[dict] | None = None,
               models: dict[int, dict] | None = None) -> dict[str, float]:
    """{player_key: out-of-sample score_v2}, forward-chained exactly as
    efv_model.oos_grades is: each decision year scored by a fit on earlier years.
    timing_pin=True scores only the debuted rows that carry an in-window preseason read,
    with that read as the input (frame version vm2). heads=False is the offset-only
    model (the liveness instrument)."""
    years = _check_years(years)
    data = training_rows(side) if data is None else data
    models = fold_models(side, years=years, data=data) if models is None else models
    mine: dict = {}
    pinned = pinned_inputs(side, data, mine) if timing_pin else {}
    out = {}
    for yr in years:
        m = models.get(yr)
        if m is None:
            continue
        if not heads:
            m = offset_only(m)
        te = [r for r in data if r["decision_year"] == yr]
        if timing_pin:
            te = [dict(r, **pinned[r["player_key"]]) for r in te
                  if r["player_key"] in pinned]
        for r, pr in zip(te, predict(m, te)):
            out[r["player_key"]] = pr["score"]
    if timing_pin and receipts is not None:
        receipts.update({k: v for k, v in mine.items() if k in out})
    return out


# ---------------------------------------------------------------------------
# v1 on the same folds (the comparator the development read needs on F-LV)
# ---------------------------------------------------------------------------

def v1_fold_scorer(train: list[dict], side: str):
    """efv_model.oos_grades' per-fold scorer, rebuilt on the rows given: the consensus
    OLS leg floored at 0, the calibrated ridge leg floored at -2, blended at v1's pinned
    lambda. Those floors are v1's, reproduced so v1 is scored as it is served; H0 has
    none. Returns f(rows) -> [score] or None when the fold cannot fit."""
    keys, _m = V1._feature_spec(side)
    lam = V1.blend_lambda(side)
    ols = V1._fit_ols_fv(train)
    ridge = V1._fit_ridge(train, keys)
    if not (ols and ridge):
        return None
    cal = V1._fit_linear_calibration([(V1._predict(ridge, r["feats"]), r["target"])
                                      for r in train])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)

    def score(rows):
        out = []
        for r in rows:
            cons_war = max(0.0, V1._pred_ols(ols, r["fv"]))
            model_war = max(-2.0, a + b * V1._predict(ridge, r["feats"]))
            out.append((1 - lam) * cons_war + lam * model_war)
        return out
    return score


# ---------------------------------------------------------------------------
# the list-vintage frame (F-LV): rows, and H0 / v1 scores per vintage
# ---------------------------------------------------------------------------

def lv_model_row(row: dict) -> dict:
    """An efv_vintage_frame row as a matrix-shaped row efv_model._vec can read: the
    prior block at the V read, the MiLB block through V - 1, and the sidecars the frame
    attached (acquisition fields only when known before V)."""
    m = dict(row.get("prior") or {})
    m.update({"player_key": row.get("player_key"), "kind": "lv",
              "mlbam_id": row.get("mlbam_id"), "birth_date": row.get("birth_date"),
              "position": row.get("position"), "cutoff": row["window"][0],
              "milb": row.get("milb"),
              "pick_overall": row.get("pick_overall"), "bonus_usd": row.get("bonus_usd"),
              "is_ifa": row.get("is_ifa"), "is_college": row.get("is_college"),
              "il_stints_pre": row.get("il_stints_pre"),
              "il_any_pre": row.get("il_any_pre")})
    if m["milb"] is None and (int(row["vintage"]) <= 2015 or not row.get("mlbam_id")):
        m["milb_unavailable"] = True
    return m


def lv_scores(side: str, vintage: int, frame_rows: list[dict], *,
              data: list[dict] | None = None, gate_sha: str | None = None) -> dict:
    """H0 and v1 scores for one F-LV (side, V) frame, both fitted on matrix rows with
    decision year before V and excluding every player in the frame.

    Returns {"status", "n_train", "h0": {key: score}, "v1": {key: score}, "model"}.
    Reserved vintages raise without the committed gate sha."""
    V = int(vintage)
    F.guard_score_request(V, gate_sha=gate_sha, purpose="score")
    data = training_rows(side) if data is None else data
    in_frame = {r["player_key"] for r in frame_rows}
    tr = [r for r in data if r["decision_year"] < V and r["player_key"] not in in_frame]
    n_overlap = sum(1 for r in data if r["decision_year"] < V
                    and r["player_key"] in in_frame)
    res = {"vintage": V, "side": side, "n_train": len(tr),
           "n_train_excluded_in_frame": n_overlap, "h0": {}, "v1": {}, "model": None}
    scored = []
    for r in frame_rows:
        mr = lv_model_row(r)
        if mr.get("consensus_fv_raw") is None:
            continue
        scored.append({"player_key": r["player_key"], "feats": V1._vec(mr, side),
                       "fv": float(mr["consensus_fv_raw"])})
    if len(tr) < MIN_TRAIN_ROWS or len(scored) < MIN_TEST_ROWS:
        res["status"] = "fold_gate"
        return res
    m = fit(tr, side)
    v1 = v1_fold_scorer(tr, side)
    if m is None or v1 is None:
        res["status"] = "no_fit"
        return res
    res["h0"] = {r["player_key"]: p["score"] for r, p in zip(scored, predict(m, scored))}
    res["v1"] = dict(zip([r["player_key"] for r in scored], v1(scored)))
    res["model"] = m
    fvs = [r["fv"] for r in scored]
    res["offset_monotone_on_frame"] = offset_curve_is_monotone(m, min(fvs), max(fvs))
    res["status"] = "ok"
    return res



# ===========================================================================
# DRIVER SYSTEM V2 core (DS-04, DS-05, DS-06; docs/efv-v2/DRIVER_SYSTEM_V2.md s4)
# ===========================================================================
# TRAINING CODE ONLY. Nothing below is served and nothing below reads a frame: the
# board, the Source Comparison score and every price still read eFV v1 (efv_model /
# efv_score) until DS-02 serves V2. v1's own feature lists (efv_model._FEATURES_HIT /
# _FEATURES_PIT) are untouched for that reason: editing them would move the served
# grade on the next nightly. The V2 lists below are what the V2 training path reads.
#
# THE THREE DEFECTS THIS SECTION REMOVES, each measured (DRIVER_SYSTEM_V2.md s2):
#   B3  a row with no MiLB block took raw 0.0 on every rate and level key, and for
#       the milb_unavailable rows no indicator carried it, so the pitcher block
#       learned "has a MiLB record" (pitchers with a block debuted 70.1% of the
#       time, without one 10.7%). V2 imputes a no-block row at the has-block TRAIN
#       mean, fits every skill slope on has-block rows only, and lets the absence
#       flag reach the REACHED/timing head alone, and only on outcome-blind ids.
#   DS-05 the SCRAP list (s4.2): the whole pitcher block (owner answer DS-Q2:
#       pitcher eFV is the consensus order until pitch-quality or K-rate data
#       passes the admission rule), hitter age, milb_missing, n_milb_seasons,
#       ops_rel, is_ifa as a slope; hitter k_rel and peak_k_rel become one
#       contact term.
#   DS-06 the admission rule: a driver enters a head only if its single-feature
#       coefficient given the consensus percentile held one sign in every prior
#       training vintage with a mean |t| of at least 1 (lane I1). The per-vintage
#       signs travel with the fitted head and into data/xfv_driver_admission.json.
#
# GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters only as a
# within-(side, year) percentile, a continuous offset. Nothing groups rows by grade.

V2_MODEL_ID = "efv_v2_ds"

#: The skill head's candidate drivers (s4.3). Hitters: on-base skill, the merged
#: contact term, two tools, the college cohort and the rewritten level. Pitchers: none
#: (owner DS-Q2); the list-vintage K-rate residual enters only through DS-10, and only
#: when V2_PIT_SKILL_CANDIDATES passes the admission rule inside the fold.
V2_SKILL_KEYS: dict[str, tuple[str, ...]] = {
    "hit": ("obp_rel", "contact", "tool_hit", "tool_speed", "is_college", "level_rank"),
    "pit": (),
}
#: Pitcher skill candidates held for DS-10 (list-vintage K rate). Never in a default fit.
V2_PIT_SKILL_CANDIDATES: tuple[str, ...] = ("k_rel",)
#: The REACHED/timing head's drivers (principle 4: timing is not talent). Age for level
#: moved here from the hitter skill set; protection status joins in DS-09.
V2_TIMING_KEYS: dict[str, tuple[str, ...]] = {
    "hit": ("age_rel_level", "level_rank"),
    "pit": ("age_rel_level", "level_rank"),
}
#: The block-absence flag. Only ever in the timing head, and only on outcome-blind ids.
V2_ABSENCE_KEY = "milb_absent"
#: Keys that come off the MiLB block. A row without a block takes each at the
#: has-block training mean (DS-04), so absence reads as average, not as raw zero.
V2_MILB_KEYS: tuple[str, ...] = ("obp_rel", "contact", "level_rank", "age_rel_level",
                                 "k_rel")
#: Keys that come off the acquisition record. A row whose acquisition is not known
#: (no draft pick and not an international signing) takes each at the acquisition-known
#: training mean: efv_model._vec writes 0.0 there, which reads "not college", and
#: acquisition-record presence is itself imbalanced on the label (hitters: partial
#: -0.126, CI95 -0.174 to -0.084, data/efv_identity_balance.json), so a raw 0.0 would
#: hand the college slope a debut proxy.
V2_ACQ_KEYS: tuple[str, ...] = ("is_college",)
#: Keys that come off neither block (tools are already mean-imputed in efv_model._vec).
V2_OTHER_KEYS: tuple[str, ...] = ("tool_hit", "tool_speed")

#: DS-05 SCRAP list (DRIVER_SYSTEM_V2.md s4.2), per side: key -> measured reason. None of
#: these may appear in a V2 SKILL design matrix. Pitcher age_rel_level is scrapped as a
#: skill slope only; age for level is a timing input on both sides.
V2_SCRAPPED: dict[str, dict[str, str]] = {
    "pit": {
        "peak_k_rel": "pitcher block, owner DS-Q2; its slope learned block presence (B3)",
        "k_rel": ("pitcher block, owner DS-Q2; returns only as the DS-10 list-vintage "
                  "residual if admitted"),
        "bb_rel": "pitcher block, owner DS-Q2",
        "age_rel_level": ("pitcher block as a skill slope, owner DS-Q2; kept as a "
                          "timing input"),
        "x_era_k": "pitcher block, owner DS-Q2",
        "tool_fb": "pitcher block, owner DS-Q2",
        "age": "pitcher block, owner DS-Q2; opposite signs on reach and WAR given reach",
        "seasons_at_level": "pitcher block, owner DS-Q2",
    },
    "hit": {
        "age": ("opposite signs on reach and WAR given reach, positive in 5 of 11 folds; "
                "dropping it helped on vm1, vm2 and lv_dev (A1)"),
        "milb_missing": "missingness is a debut proxy (B3); weight 0.0001",
        "n_milb_seasons": "drop helps on vm1 and lv (A1); a declared suppressor",
        "ops_rel": "collinear with obp_rel; drop helps on vm1 and lv (A1)",
        "is_ifa": "no slope: drop helps on vm1 and lv (A1)",
        "k_rel": "merged into the contact term",
        "peak_k_rel": "merged into the contact term",
    },
}

#: DS-06 admission rule (lane I1, p4): per training vintage, the t of the driver's
#: coefficient in an OLS of the target percentile on [1, consensus percentile, z(x)].
ADMIT_MIN_ROWS = MIN_TRAIN_ROWS  # a vintage with fewer rows gives no t (I1's floor)
ADMIT_MIN_VINTAGES = 2          # at least two vintages must give a t
ADMIT_MIN_MEAN_ABS_T = 1.0      # mean |t| over those vintages
#: Ridge penalty grid for the V2 heads, standardized columns; the last entry switches a
#: head off. Chosen by nested forward-chained CV on training years only, as H0 does.
V2_ALPHAS: tuple[float, ...] = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, math.inf)


def v2_row(feats: dict) -> dict:
    """The V2 view of one efv_model._vec feature dict. `has_block` is True for a row whose
    MiLB keys came off a real block; a no-block row carries None on every V2_MILB_KEYS
    entry (imputed later, per fit) and milb_absent 1.0. The contact term is the mean of
    the two strikeout rates, sign flipped so more contact reads higher. `acq_known` is
    True for a drafted row (a pick) or an international signing; otherwise every
    V2_ACQ_KEYS entry is None and imputed per fit."""
    has = bool(V1._has_milb_block(feats))
    acq = bool(float(feats.get("is_ifa") or 0.0) == 1.0
               or float(feats.get("pick_missing", 1.0)) == 0.0)
    out: dict = {"has_block": has, "acq_known": acq, V2_ABSENCE_KEY: 0.0 if has else 1.0}
    for k in ("obp_rel", "level_rank", "age_rel_level", "k_rel"):
        v = feats.get(k)
        out[k] = float(v) if (has and v is not None) else None
    kr, pk = feats.get("k_rel"), feats.get("peak_k_rel")
    out["contact"] = (-0.5 * (float(kr) + float(pk))
                      if (has and kr is not None and pk is not None) else None)
    for k in V2_ACQ_KEYS:
        v = feats.get(k)
        out[k] = float(v) if (acq and v is not None) else None
    for k in V2_OTHER_KEYS:
        v = feats.get(k)
        out[k] = float(v) if v is not None else 0.0
    return out


def attach_v2(rows: list[dict]) -> list[dict]:
    """Each row (carrying `feats`) with its `v2` view attached, as new dicts."""
    return [dict(r, v2=v2_row(r["feats"])) for r in rows]


def has_block_means(train: list[dict]) -> dict[str, float]:
    """{key: mean} of every V2_MILB_KEYS entry over the TRAIN rows that have a block, and
    of every V2_ACQ_KEYS entry over the TRAIN rows whose acquisition is known. Unweighted,
    like efv_model._has_milb_impute_means. A key with no observed value falls back to
    0.0."""
    out = {}
    for keys, flag in ((V2_MILB_KEYS, "has_block"), (V2_ACQ_KEYS, "acq_known")):
        for k in keys:
            vals = [r["v2"][k] for r in train
                    if r["v2"][flag] and r["v2"].get(k) is not None]
            out[k] = float(sum(vals) / len(vals)) if vals else 0.0
    return out


def v2_vector(v2: dict, keys, means: dict[str, float]) -> list[float]:
    """The design row for `keys`: a missing block key takes the has-block mean."""
    out = []
    for k in keys:
        v = v2.get(k)
        out.append(float(means.get(k, 0.0)) if v is None else float(v))
    return out


def _v2_x(rows: list[dict], keys, means) -> np.ndarray:
    if not rows or not keys:
        return np.zeros((len(rows), len(keys)))
    return np.array([v2_vector(r["v2"], keys, means) for r in rows], dtype=np.float64)


def within_pct(values, groups) -> np.ndarray:
    """Within-group percentile (average rank / group size), for u_c and u_y."""
    vals = np.asarray(values, dtype=np.float64)
    out = np.zeros(vals.size)
    by: dict = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    for idx in by.values():
        ix = np.asarray(idx)
        v = vals[ix]
        order = np.argsort(v, kind="mergesort")
        ranks = np.empty(v.size)
        ranks[order] = np.arange(1, v.size + 1, dtype=np.float64)
        for u in np.unique(v):                      # ties take their average rank
            m = v == u
            if m.sum() > 1:
                ranks[m] = ranks[m].mean()
        out[ix] = ranks / v.size
    return out


def _percentiles(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """(u_c, u_y) within decision year: the consensus and target percentiles."""
    yrs = [int(r["decision_year"]) for r in rows]
    return (within_pct([r["fv"] for r in rows], yrs),
            within_pct([r["target"] for r in rows], yrs))


def skill_training_rows(rows: list[dict]) -> list[dict]:
    """The rows a skill slope may be fit on: has-block rows only (DS-04)."""
    return [r for r in rows if r["v2"]["has_block"]]


def skill_keys(side: str) -> tuple[str, ...]:
    """The skill head's candidate drivers. Never contains the absence flag."""
    keys = tuple(V2_SKILL_KEYS[side])
    if V2_ABSENCE_KEY in keys:
        raise ValueError("the absence flag may not enter the skill head (DS-04)")
    return keys


def timing_keys(side: str, *, ids_outcome_blind: bool = False,
                absence_admitted: bool = False) -> tuple[str, ...]:
    """The timing head's drivers. The absence flag joins ONLY when the rows' ids came
    from the outcome-blind resolver (efv_identity) AND the label-balance report admits it
    (data/efv_identity_balance.json); on the v1 training matrices neither holds."""
    keys = tuple(V2_TIMING_KEYS[side])
    if ids_outcome_blind and absence_admitted:
        keys = keys + (V2_ABSENCE_KEY,)
    return keys


# ---------------------------------------------------------------------------
# DS-06: the admission rule
# ---------------------------------------------------------------------------

def admission_t(u_c, y, x, *, min_rows: int = ADMIT_MIN_ROWS) -> float | None:
    """t of x's coefficient in the OLS y ~ 1 + u_c + z(x) on one vintage's rows, or None
    when the vintage has fewer than min_rows rows or x is constant."""
    u_c, y, x = (np.asarray(a, dtype=np.float64) for a in (u_c, y, x))
    n = x.size
    if n < int(min_rows) or n <= 3 or float(x.std()) <= 0:
        return None
    z = (x - x.mean()) / x.std()
    X = np.column_stack([np.ones(n), u_c, z])
    XtX = X.T @ X
    if abs(float(np.linalg.det(XtX))) < 1e-12:
        return None
    b = np.linalg.solve(XtX, X.T @ y)
    r = y - X @ b
    var = float(r @ r) / (n - 3) * float(np.linalg.inv(XtX)[2, 2])
    if not var > 0:
        return None
    return float(b[2] / math.sqrt(var))


def admission_check(t_by_vintage: dict[int, float | None]) -> dict:
    """The rule on a driver's per-vintage t values. Admitted only when at least
    ADMIT_MIN_VINTAGES vintages give a t, every one has the same sign, and their mean
    |t| is at least ADMIT_MIN_MEAN_ABS_T. One flipped sign refuses the driver."""
    valid = {int(v): float(t) for v, t in sorted(t_by_vintage.items()) if t is not None}
    signs = {v: (1 if t > 0 else -1 if t < 0 else 0) for v, t in valid.items()}
    mean_abs = (sum(abs(t) for t in valid.values()) / len(valid)) if valid else None
    one_sign = bool(valid) and (all(s > 0 for s in signs.values())
                                or all(s < 0 for s in signs.values()))
    if len(valid) < ADMIT_MIN_VINTAGES:
        reason = f"fewer than {ADMIT_MIN_VINTAGES} vintages give a t"
    elif not one_sign:
        reason = "sign flipped between training vintages"
    elif mean_abs < ADMIT_MIN_MEAN_ABS_T:
        reason = f"mean |t| {mean_abs:.3f} below {ADMIT_MIN_MEAN_ABS_T}"
    else:
        reason = "sign held in every training vintage and mean |t| cleared"
    admitted = (len(valid) >= ADMIT_MIN_VINTAGES and one_sign
                and mean_abs is not None and mean_abs >= ADMIT_MIN_MEAN_ABS_T)
    return {"t_by_vintage": {str(v): round(t, 4) for v, t in valid.items()},
            "per_vintage_signs": {str(v): s for v, s in signs.items()},
            "vintages_without_t": sorted(int(v) for v, t in t_by_vintage.items()
                                         if t is None),
            "n_valid_vintages": len(valid),
            "sign": (next(iter(signs.values())) if one_sign else 0),
            "mean_abs_t": None if mean_abs is None else round(mean_abs, 4),
            "admitted": bool(admitted), "reason": reason}


def admission_for_key(train: list[dict], key: str, *, target: str = "u_y",
                      has_block_only: bool = True,
                      min_rows: int = ADMIT_MIN_ROWS) -> dict:
    """The rule for one driver on training rows (each carrying `v2`, `fv`, `target`,
    `reached`, `decision_year`). Percentiles are taken within decision year over every
    row of that year; the t is read on the has-block rows when has_block_only (the
    skill head's rows) and on every row, imputed, otherwise (the timing head's)."""
    _check_years({int(r["decision_year"]) for r in train})
    u_c, u_y = _percentiles(train)
    means = has_block_means(train)
    t_by = {}
    for yr in sorted({int(r["decision_year"]) for r in train}):
        ix = [i for i, r in enumerate(train) if int(r["decision_year"]) == yr
              and (r["v2"]["has_block"] or not has_block_only)]
        if not ix:
            t_by[yr] = None
            continue
        # an imputed value says nothing about the driver: a vintage gives a t only when
        # at least min_rows of its rows OBSERVE the driver (the degenerate pre-2016
        # vintages, where nearly every block key is imputed, give none)
        if sum(1 for i in ix if train[i]["v2"].get(key) is not None) < min_rows:
            t_by[yr] = None
            continue
        x = [v2_vector(train[i]["v2"], (key,), means)[0] for i in ix]
        y = (u_y[ix] if target == "u_y"
             else np.array([train[i]["reached"] for i in ix], dtype=np.float64))
        t_by[yr] = admission_t(u_c[ix], y, x, min_rows=min_rows)
    return admission_check(t_by)


def admitted_keys(train: list[dict], keys, *, target: str = "u_y",
                  has_block_only: bool = True) -> tuple[tuple[str, ...], dict]:
    """(the keys that pass the rule on these training rows, {key: check})."""
    checks = {k: admission_for_key(train, k, target=target, has_block_only=has_block_only)
              for k in keys}
    return tuple(k for k in keys if checks[k]["admitted"]), checks


# ---------------------------------------------------------------------------
# the two heads (s4.3): a skill ridge and a REACHED/timing logistic, both residual
# to the consensus percentile u_c
# ---------------------------------------------------------------------------

def _std_cols(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu, sd = _standardize(X)
    return mu, sd, ((X - mu) / sd if X.shape[1] else X)


def _lin(head: dict, X: np.ndarray) -> np.ndarray:
    """The head's DRIVER part only: sum of slope times standardized driver. The
    consensus column and the intercept are not in it, so the score is what the head
    adds beyond consensus."""
    beta = np.asarray(head["beta"], dtype=np.float64)
    if beta.size == 0:
        return np.zeros(X.shape[0])
    return ((X - np.asarray(head["mu"])) / np.asarray(head["sd"])) @ beta


def _skill_fit(train: list[dict], keys, alpha: float) -> dict | None:
    """Weighted ridge of u_y on [1, u_c, z(drivers)] over the has-block rows, with the
    intercept and the u_c slope unpenalized. Consensus is a free control, never a
    feature with a shrunk slope; the drivers are read conditional on it, the same way
    the admission rule reads them."""
    rows = skill_training_rows(train)
    if len(rows) < MIN_TEST_ROWS or not keys:
        return None
    u_c, u_y = _percentiles(train)
    pos = {id(r): i for i, r in enumerate(train)}
    ix = [pos[id(r)] for r in rows]
    means = has_block_means(train)
    mu, sd, Xs = _std_cols(_v2_x(rows, keys, means))
    w = np.array([max(float(r.get("weight", 1.0) or 0.0), 1e-3) for r in rows])
    Z = np.column_stack([np.ones(len(rows)), u_c[ix], Xs])
    off = math.inf if math.isinf(alpha) else float(alpha)
    if math.isinf(off):
        coef = np.concatenate([_wls(Z[:, :2], u_y[ix], w, np.zeros(2)),
                               np.zeros(len(keys))])
    else:
        pen = np.concatenate([[0.0, 0.0], np.full(len(keys), off)])
        coef = _wls(Z, u_y[ix], w, pen)
    return {"keys": list(keys), "means": means, "alpha": alpha, "mu": mu.tolist(),
            "sd": sd.tolist(), "b0": float(coef[0]), "b_uc": float(coef[1]),
            "beta": [float(b) for b in coef[2:]], "n_train": len(rows),
            "trained_on": "has_block"}


def _timing_fit(train: list[dict], keys, alpha: float) -> dict | None:
    """Penalized logistic of REACHED on [1, u_c, z(drivers)] over every training row
    (no-block rows at the has-block means), intercept and u_c slope unpenalized."""
    if len(train) < MIN_TRAIN_ROWS:
        return None
    u_c, _u_y = _percentiles(train)
    y = np.array([r["reached"] for r in train], dtype=np.float64)
    if y.min() == y.max():
        return None
    means = has_block_means(train)
    mu, sd, Xs = _std_cols(_v2_x(train, keys, means))
    zero = np.zeros(len(train))
    if math.isinf(alpha) or not keys:
        coef = np.concatenate([
            _logistic(np.column_stack([np.ones(len(train)), u_c]), y, zero,
                      np.full(2, _OFFSET_EPS)), np.zeros(len(keys))])
    else:
        Z = np.column_stack([np.ones(len(train)), u_c, Xs])
        pen = np.concatenate([np.full(2, _OFFSET_EPS), np.full(len(keys), float(alpha))])
        coef = _logistic(Z, y, zero, pen)
    return {"keys": list(keys), "means": means, "alpha": alpha, "mu": mu.tolist(),
            "sd": sd.tolist(), "b0": float(coef[0]), "b_uc": float(coef[1]),
            "beta": [float(b) for b in coef[2:]], "n_train": len(train),
            "trained_on": "all"}


def _select_alpha(train: list[dict], keys, head: str,
                  alphas: tuple[float, ...] = V2_ALPHAS) -> float:
    """Nested forward-chained penalty choice over training years only (the H0 rule):
    each inner year is scored by a fit on the years before it. Skill: weighted squared
    error of the residual target on the inner year's has-block rows. Timing: log loss of
    REACHED. Ties go to the larger penalty; no inner year switches the head off."""
    loss = {a: 0.0 for a in alphas}
    used = 0
    for yr in inner_years(train):
        tr = [r for r in train if r["decision_year"] < yr]
        te = [r for r in train if r["decision_year"] == yr]
        ok = False
        if head == "skill":
            te_hb = skill_training_rows(te)
            if not te_hb:
                continue
            u_c, u_y = _percentiles(te)
            pos = {id(r): i for i, r in enumerate(te)}
            ix = [pos[id(r)] for r in te_hb]
            w = np.array([max(float(r.get("weight", 1.0) or 0.0), 1e-3) for r in te_hb])
            fits = {a: _skill_fit(tr, keys, a) for a in alphas}
            if any(h is None for h in fits.values()):
                continue
            for a, h in fits.items():
                pred = (h["b0"] + h["b_uc"] * u_c[ix]
                        + _lin(h, _v2_x(te_hb, keys, h["means"])))
                loss[a] += float(np.sum(w * (u_y[ix] - pred) ** 2))
            ok = True
        else:
            u_c, _ = _percentiles(te)
            y = np.array([r["reached"] for r in te], dtype=np.float64)
            fits = {a: _timing_fit(tr, keys, a) for a in alphas}
            if any(h is None for h in fits.values()):
                continue
            for a, h in fits.items():
                eta = (h["b0"] + h["b_uc"] * u_c
                       + _lin(h, _v2_x(te, keys, h["means"])))
                loss[a] += float(np.sum(np.logaddexp(0.0, eta) - y * eta))
            ok = True
        used += ok
    if not used:
        return math.inf
    best = None
    for a in sorted(alphas, reverse=True):
        if best is None or loss[a] < loss[best]:
            best = a
    return best


def fit_skill_head(train: list[dict], side: str, *, admit: bool = True,
                   alpha: float | None = None) -> dict | None:
    """The skill head on one fold's training rows (each carrying `v2`): a ridge of the
    target percentile u_y on the consensus percentile u_c (free) and the admitted skill
    drivers (penalized), fit on has-block rows only. None when the
    side has no skill driver (pitchers by default), when no driver is admitted, or when
    the rows cannot support a fit; the caller then orders by consensus alone."""
    _check_years({int(r["decision_year"]) for r in train})
    cands = skill_keys(side)
    if not cands:
        return None
    keys, checks = admitted_keys(train, cands) if admit else (cands, {})
    if not keys:
        return None
    a = _select_alpha(train, keys, "skill") if alpha is None else alpha
    head = _skill_fit(train, keys, a)
    if head is None:
        return None
    head.update({"side": side, "admission": checks, "candidates": list(cands)})
    sc = _lin(head, _v2_x(skill_training_rows(train), keys, head["means"]))
    head["score_sd"] = float(sc.std()) if sc.size and sc.std() > 0 else 1.0
    return head


def fit_timing_head(train: list[dict], side: str, *, ids_outcome_blind: bool = False,
                    absence_admitted: bool = False, admit: bool = True,
                    alpha: float | None = None) -> dict | None:
    """The REACHED/timing head on one fold's training rows: a penalized logistic of
    REACHED on u_c (free) and the admitted timing drivers (penalized).
    No-block rows take the has-block means; the absence flag joins only per
    timing_keys()."""
    _check_years({int(r["decision_year"]) for r in train})
    cands = timing_keys(side, ids_outcome_blind=ids_outcome_blind,
                        absence_admitted=absence_admitted)
    keys, checks = (admitted_keys(train, cands, target="reached", has_block_only=False)
                    if admit else (cands, {}))
    a = _select_alpha(train, keys, "timing") if alpha is None else alpha
    head = _timing_fit(train, keys, a)
    if head is None:
        return None
    head.update({"side": side, "admission": checks, "candidates": list(cands),
                 "ids_outcome_blind": bool(ids_outcome_blind)})
    sc = _lin(head, _v2_x(train, keys, head["means"]))
    head["score_sd"] = float(sc.std()) if sc.size and sc.std() > 0 else 1.0
    return head


def skill_design(rows: list[dict], head: dict) -> np.ndarray:
    """The skill head's design matrix for rows: its keys only (never the absence flag),
    no-block rows at the head's has-block training means."""
    if V2_ABSENCE_KEY in head["keys"]:
        raise ValueError("the absence flag may not enter the skill head (DS-04)")
    return _v2_x(rows, head["keys"], head["means"])


def z_skill(head: dict | None, rows: list[dict]) -> np.ndarray:
    """Standardized skill residual score: the driver part of the head over its
    training sd (0 for every row when the head is None)."""
    if head is None:
        return np.zeros(len(rows))
    return _lin(head, skill_design(rows, head)) / head["score_sd"]


def z_time(head: dict | None, rows: list[dict]) -> np.ndarray:
    """Standardized timing residual score (0 for every row when the head is None)."""
    if head is None:
        return np.zeros(len(rows))
    return _lin(head, _v2_x(rows, head["keys"], head["means"])) / head["score_sd"]
