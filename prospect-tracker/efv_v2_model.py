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
    # "unavailable" means the cache floor left at most one readable season before V;
    # the frame records the floor it read at (milb_floor), so the cut slides with it
    # (2014 floor: V <= 2015, the rule as shipped; MILB_FLOOR_LV 2005: no vintage).
    floor = int(row.get("milb_floor") or F.D.MILB_FLOOR_DEFAULT)
    if m["milb"] is None and (int(row["vintage"]) <= floor + 1 or not row.get("mlbam_id")):
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
#: Sidecar drivers read off the row's record as of its read, each None when not observed
#: and imputed per fit at the mean of the TRAIN rows that observe it (no indicator ever
#: enters a skill head): pitcher BMI from the dated FanGraphs board archives, the PV-12
#: Pipeline-revision slot, and protection status from the league transaction feed on
#: outcome-blind ids (DS-09).
V2_OBSERVED_KEYS: tuple[str, ...] = ("bmi", "pl_rev", "on_40man", "nov_add")
#: Prefix of a SCREENING column (tools/efv_screen_lab.py): one column offered to one
#: head for one development read, carried on the row's `v2` view like a sidecar
#: driver and imputed per fit at the mean of the TRAIN rows that observe it
#: (has_block_means). No served candidate list names one; fit_v2(extra=...) is the
#: only way in, and a key without the prefix is refused there.
V2_SCREEN_PREFIX = "scr_"

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


def v2_row(feats: dict, extra: dict | None = None) -> dict:
    """The V2 view of one efv_model._vec feature dict. `has_block` is True for a row whose
    MiLB keys came off a real block; a no-block row carries None on every V2_MILB_KEYS
    entry (imputed later, per fit) and milb_absent 1.0. The contact term is the mean of
    the two strikeout rates, sign flipped so more contact reads higher. `acq_known` is
    True for a drafted row (a pick) or an international signing; otherwise every
    V2_ACQ_KEYS entry is None and imputed per fit. `extra` carries the sidecar drivers
    read off the row's own record as of its read (V2_OBSERVED_KEYS: BMI, protection
    status, the Pipeline-revision slot); a key it lacks, or holds as None, is None here
    and imputed per fit at the observed training mean."""
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
    ex = extra or {}
    for k in V2_OBSERVED_KEYS:
        v = ex.get(k)
        out[k] = (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool)
                  and math.isfinite(float(v)) else None)
    return out


def attach_v2(rows: list[dict]) -> list[dict]:
    """Each row (carrying `feats`, optionally `extra`) with its `v2` view attached, as
    new dicts."""
    return [dict(r, v2=v2_row(r["feats"], r.get("extra"))) for r in rows]


def has_block_means(train: list[dict]) -> dict[str, float]:
    """{key: mean} of every V2_MILB_KEYS entry over the TRAIN rows that have a block, of
    every V2_ACQ_KEYS entry over the TRAIN rows whose acquisition is known, and of every
    V2_OBSERVED_KEYS entry over the TRAIN rows that observe it. Unweighted, like
    efv_model._has_milb_impute_means. A key with no observed value falls back to 0.0."""
    out = {}
    for keys, flag in ((V2_MILB_KEYS, "has_block"), (V2_ACQ_KEYS, "acq_known")):
        for k in keys:
            vals = [r["v2"][k] for r in train
                    if r["v2"][flag] and r["v2"].get(k) is not None]
            out[k] = float(sum(vals) / len(vals)) if vals else 0.0
    for k in V2_OBSERVED_KEYS + screen_keys(train):
        vals = [r["v2"][k] for r in train if r["v2"].get(k) is not None]
        out[k] = float(sum(vals) / len(vals)) if vals else 0.0
    return out


def screen_keys(rows) -> tuple[str, ...]:
    """The screening columns the rows carry: the V2_SCREEN_PREFIX keys of the first
    row's v2 view (a screening column is attached to every row or to none). () on
    every served path."""
    if not rows:
        return ()
    return tuple(sorted(k for k in rows[0]["v2"] if str(k).startswith(V2_SCREEN_PREFIX)))


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
                  alphas: tuple[float, ...] = V2_ALPHAS,
                  no_inner: float = math.inf) -> float:
    """Nested forward-chained penalty choice over training years only (the H0 rule):
    each inner year is scored by a fit on the years before it. Skill: weighted squared
    error of the residual target on the inner year's has-block rows. Timing: log loss of
    REACHED. Ties go to the larger penalty; no inner year returns `no_inner` (the head
    off by default; only the DS-08 combiner rule passes a fixed finite penalty)."""
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
        return no_inner
    best = None
    for a in sorted(alphas, reverse=True):
        if best is None or loss[a] < loss[best]:
            best = a
    return best


def _force_keys(cands, keys, checks, force) -> tuple[tuple[str, ...], dict]:
    """Screening columns admitted WITHOUT the rule (the screening lab's floor
    derivation only): each must carry V2_SCREEN_PREFIX and sit in the candidate list;
    its check reads forced. Order follows the candidate list."""
    force = tuple(force or ())
    if not force:
        return tuple(keys), checks
    for k in force:
        if not str(k).startswith(V2_SCREEN_PREFIX) or k not in cands:
            raise ValueError(f"only a screening candidate may be forced, got {k!r}")
    checks = dict(checks)
    for k in force:
        checks[k] = {"admitted": True, "forced": True,
                     "reason": "forced: admission bypassed (screening floor derivation)",
                     "per_vintage_signs": {}, "mean_abs_t": None, "n_valid_vintages": 0}
    return tuple(k for k in cands if k in keys or k in force), checks


def fit_skill_head(train: list[dict], side: str, *, admit: bool = True,
                   alpha: float | None = None, candidates=None,
                   no_inner_alpha: float = math.inf, force=()) -> dict | None:
    """The skill head on one fold's training rows (each carrying `v2`): a ridge of the
    target percentile u_y on the consensus percentile u_c (free) and the admitted skill
    drivers (penalized), fit on has-block rows only. None when the
    side has no skill driver (pitchers by default), when no driver is admitted, or when
    the rows cannot support a fit; the caller then orders by consensus alone.
    `candidates` overrides the side's base list (skill_candidates() in the assembly);
    the absence flag is refused in any list. `force` names screening columns admitted
    without the rule (_force_keys; the screening lab's floor derivation only)."""
    _check_years({int(r["decision_year"]) for r in train})
    cands = skill_keys(side) if candidates is None else tuple(candidates)
    if V2_ABSENCE_KEY in cands:
        raise ValueError("the absence flag may not enter the skill head (DS-04)")
    if not cands:
        return None
    keys, checks = admitted_keys(train, cands) if admit else (cands, {})
    keys, checks = _force_keys(cands, keys, checks, force)
    if not keys:
        return None
    a = (_select_alpha(train, keys, "skill", no_inner=no_inner_alpha)
         if alpha is None else alpha)
    head = _skill_fit(train, keys, a)
    if head is None:
        return None
    head.update({"side": side, "admission": checks, "candidates": list(cands)})
    sc = _lin(head, _v2_x(skill_training_rows(train), keys, head["means"]))
    head["score_sd"] = float(sc.std()) if sc.size and sc.std() > 0 else 1.0
    return head


def fit_timing_head(train: list[dict], side: str, *, ids_outcome_blind: bool = False,
                    absence_admitted: bool = False, admit: bool = True,
                    alpha: float | None = None, candidates=None,
                    no_inner_alpha: float = math.inf, force=()) -> dict | None:
    """The REACHED/timing head on one fold's training rows: a penalized logistic of
    REACHED on u_c (free) and the admitted timing drivers (penalized).
    No-block rows take the has-block means; the absence flag joins only per
    timing_keys(); `candidates` overrides the list (timing_candidates() in the
    assembly), and an absence flag in it still needs outcome-blind admitted ids."""
    _check_years({int(r["decision_year"]) for r in train})
    cands = (timing_keys(side, ids_outcome_blind=ids_outcome_blind,
                         absence_admitted=absence_admitted)
             if candidates is None else tuple(candidates))
    if V2_ABSENCE_KEY in cands and not (ids_outcome_blind and absence_admitted):
        raise ValueError("the absence flag needs outcome-blind admitted ids (DS-04)")
    keys, checks = (admitted_keys(train, cands, target="reached", has_block_only=False)
                    if admit else (cands, {}))
    keys, checks = _force_keys(cands, keys, checks, force)
    a = (_select_alpha(train, keys, "timing", no_inner=no_inner_alpha)
         if alpha is None else alpha)
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


# ===========================================================================
# DRIVER SYSTEM V2 assembly (DS-07, DS-08, DS-09 wiring, DS-10, the BMI re-test,
# PV-12; docs/efv-v2/DRIVER_SYSTEM_V2.md s4.3)
# ===========================================================================
# TRAINING CODE ONLY, like the core above: nothing here is served and nothing here
# scores V2 against consensus or any source. The development read is DS-16's
# (tools/efv_v2_dev_read.py); the served grade moves only in DS_F_serve_v2.
#
# THE MODEL (s4.3), for one side s and one list year V (or debut year on F-VM):
#
#     u_c        within-(s, V) percentile of the consensus FV (the anchor, no fit)
#     e_skill    the skill head's driver part in CONSENSUS-PERCENTILE EQUIVALENTS: the
#                head's driver sum divided by its own (free) consensus slope, so +0.1
#                means "the head values this as much as 0.1 of consensus percentile"
#     e_time     the same for the REACHED/timing head (its logit driver sum over its
#                own logit consensus slope)
#     order_idx  u_c + w_skill * e_skill + w_time * e_time
#     eFV grade  the consensus FV value of (s, V) at order_idx's within-group rank,
#                ties averaged (DS-07, output_map)
#     eFV WAR    a continuous linear consensus-FV-to-WAR map fitted on the fold's
#                training rows, evaluated at the eFV grade (pricing only, never ranked)
#
# The spec writes order_idx = u_c + w_s * (z_skill + a * z_time) with "standardized"
# head scores. Standardizing by each head's own consensus slope (not its SD) is what lets
# ONE fixed weight mean the same thing on the list-vintage frame (consensus slope on the
# W3 percentile about 0.2) and the debut-year frame (about 0.4); in the spec's notation
# w_s = w_skill and a = w_time / w_skill.
#
# WEIGHTS (DS-08): w_skill and w_time per side are fixed by combiner_rule BEFORE any
# development read and written to data/efv_v2_assembly.json by
# tools/efv_v2_assemble.py. See combiner_rule for the rule and its three stated
# adaptations (the literal rule's rows hold no MiLB block).
#
# PITCHERS (owner answer DS-Q2, binding over s4.3's "timing only by default"): pitcher
# eFV is the consensus order in any fold where no pitcher SKILL driver passes the
# admission rule. The pitcher skill candidates are the DS-10 list-vintage K rate
# (k_rel off the as-of MiLB block), the pre-declared BMI re-test, and the PV-12 slot.
#
# GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group
# percentile and as the value multiset the grade is drawn from; the WAR map is a
# continuous line in the grade. Nothing groups, counts or averages rows by grade level.

V2_ASSEMBLED_ID = "efv_v2_ds_assembled"
#: The pre-declared pitcher skill re-test beside the DS-10 K rate (owner question
#: 2026-09-25): BMI as of the read from the dated FanGraphs board archives.
V2_PIT_SKILL_EXTRA: tuple[str, ...] = ("bmi",)
#: PV-12: the Pipeline-revision candidate, both sides, Pipeline-anchored rows only.
V2_PL_REV_KEY = "pl_rev"
#: DS-09 protection status, timing head only, outcome-blind ids only.
V2_PROTECTION_KEYS: tuple[str, ...] = ("on_40man", "nov_add")
#: DS-08: the combiner rule reads decision years and list vintages up to this year.
RULE_LAST_YEAR = 2016
#: The penalty a combiner-rule head uses when its nested CV has no inner year (the
#: middle of V2_ALPHAS' finite grid, fixed before any read).
RULE_FALLBACK_ALPHA = 30.0
#: The largest combiner weight: a weight is a share of the head's own estimate.
W_MAX = 1.0
#: The development window V2 may be scored on, disjoint from the rule's years.
V2_FIRST_SCORED_YEAR = RULE_LAST_YEAR + 1
#: The registration artifact (weights, rule receipt, per-fold admission, coverage).
ASSEMBLY_PATH = DATA_DIR / "efv_v2_assembly.json"
IDENTITY_BALANCE_PATH = DATA_DIR / "efv_identity_balance.json"


def skill_candidates(side: str) -> tuple[str, ...]:
    """Every skill-head candidate the admission rule checks, per side. Hitters: the
    DS-05 list plus PV-12. Pitchers: the DS-10 K rate, the BMI re-test and PV-12."""
    if side == "hit":
        base = skill_keys("hit")
    elif side == "pit":
        base = tuple(V2_PIT_SKILL_CANDIDATES) + tuple(V2_PIT_SKILL_EXTRA)
    else:
        raise ValueError(f"side must be one of {F.SIDES}, got {side!r}")
    out = tuple(base) + (V2_PL_REV_KEY,)
    if V2_ABSENCE_KEY in out:
        raise ValueError("the absence flag may not enter the skill head (DS-04)")
    return out


def timing_candidates(side: str, *, ids_outcome_blind: bool = False,
                      absence_admitted: bool = False) -> tuple[str, ...]:
    """The timing head's candidates: age for level and level, the absence flag on
    outcome-blind admitted ids, and protection status on outcome-blind ids only (the
    matrix ids are a debut proxy, bug B4, so protection never enters a matrix fit)."""
    keys = timing_keys(side, ids_outcome_blind=ids_outcome_blind,
                       absence_admitted=absence_admitted)
    return keys + (V2_PROTECTION_KEYS if ids_outcome_blind else ())


def absence_admitted(side: str, path: Path | None = None) -> bool:
    """True when data/efv_identity_balance.json lists milb_absent as admissible to the
    side's timing head (label-balanced on outcome-blind ids, DS-03)."""
    p = IDENTITY_BALANCE_PATH if path is None else Path(path)
    if not p.exists():
        return False
    doc = json.loads(p.read_text(encoding="utf-8"))
    return V2_ABSENCE_KEY in ((doc.get("timing_head_admissible") or {}).get(side) or [])


# ---------------------------------------------------------------------------
# rows: the list-vintage frame (outcome-blind ids) and the v1 matrices
# ---------------------------------------------------------------------------

def _extra_from_frame_row(r: dict) -> dict:
    return {"bmi": r.get("bmi_at_read"), "pl_rev": r.get("pl_rev_at_read"),
            "on_40man": r.get("on_40man_at_v"), "nov_add": r.get("nov_add_v_minus_1")}


def lv_v2_rows(side: str, vintage: int, frame_rows: list[dict], *,
               gate_sha: str | None = None) -> list[dict]:
    """F-LV rows as V2 rows (no label): the V read's consensus as `fv`, the as-of MiLB
    block on the outcome-blind id (lv_model_row), and the sidecars efv_drivers attached
    (bmi_for_rows, protection_for_frame, pl_revision_for_rows). Rows without a
    consensus are dropped. Reserved vintages raise without the gate sha."""
    V = int(vintage)
    F.guard_score_request(V, gate_sha=gate_sha, purpose="V2 rows")
    out = []
    for r in frame_rows:
        if int(r["vintage"]) != V:
            raise ValueError(f"row {r.get('player_key')} is at {r['vintage']}, not {V}")
        c = (r.get("grades") or {}).get(SB.CONSENSUS_KEY)
        if c is None:
            continue
        feats = V1._vec(lv_model_row(r), side)
        extra = _extra_from_frame_row(r)
        out.append({"player_key": r["player_key"], "decision_year": V, "fv": float(c),
                    "feats": feats, "extra": extra, "v2": v2_row(feats, extra),
                    "frame": "lv", "ids_outcome_blind": True})
    return out


def lv_training_rows(side: str, frames: dict[int, tuple[list[dict], list[dict]]], *,
                     gate_sha: str | None = None) -> list[dict]:
    """Labelled F-LV rows for V2 fits: {V: (frame rows, efv_labels rows)} in, one row
    per (player, V) with target = W3 (the skill head's within-(s, V) percentile target),
    reached = R3 (debut inside the V window, the timing head's target) and weight 1.
    A row without a consensus, a W3 or an R3 is left out (a reserved_vm label is None
    and so never enters). The labels are joined by the caller; this module imports no
    label module."""
    out = []
    for V, (rows, labs) in sorted(frames.items()):
        if len(rows) != len(labs):
            raise ValueError(f"vintage {V}: {len(rows)} rows but {len(labs)} labels")
        v2rows = {r["player_key"]: r for r in lv_v2_rows(side, V, rows,
                                                         gate_sha=gate_sha)}
        for r, lab in zip(rows, labs):
            if lab.get("player_key") != r.get("player_key"):
                raise ValueError(f"label for {lab.get('player_key')} on row "
                                 f"{r.get('player_key')}")
            m = v2rows.get(r["player_key"])
            if m is None or lab.get("w3") is None or lab.get("r3") is None:
                continue
            out.append(dict(m, target=float(lab["w3"]), reached=float(lab["r3"]),
                            weight=1.0))
    _check_years({r["decision_year"] for r in out})
    return out


def matrix_training_rows(side: str, *, bio_panel: dict | None = None) -> list[dict]:
    """The v1 matrix pool (training_rows) as V2 rows. The only sidecar is BMI as of the
    row's own read date (the pitcher re-test); protection is left None because matrix
    ids are not outcome-blind (B4), and PV-12 has no row before list vintage 2022."""
    import efv_drivers as DRV
    panel = DRV.load_bio_panel() if bio_panel is None else bio_panel
    raw = json.loads(_matrix_path(side).read_text(encoding="utf-8"))
    asof = {r["player_key"]: r.get("asof_date") for r in raw}
    out = []
    for d in training_rows(side):
        extra = {"bmi": DRV.bmi_asof(d["player_key"], asof.get(d["player_key"]), panel)}
        out.append(dict(d, extra=extra, v2=v2_row(d["feats"], extra), frame="vm",
                        ids_outcome_blind=False))
    return out


# ---------------------------------------------------------------------------
# DS-07: the output map
# ---------------------------------------------------------------------------

def output_map(order_idx, groups, values) -> np.ndarray:
    """Inside each group, the row at order rank k takes the k-th smallest of the group's
    own consensus values; rows tied on order_idx share the mean of the values their
    ranks draw. So within a group the grade orders rows exactly as order_idx does, and
    with no ties the group's grade multiset IS its consensus multiset: consensus sets
    the level, the model only reorders (principle 1, bug B5)."""
    o = np.asarray(order_idx, dtype=np.float64)
    v = np.asarray(values, dtype=np.float64)
    if o.shape != v.shape:
        raise ValueError("order_idx and values differ in length")
    out = np.zeros(o.size)
    by: dict = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    for idx in by.values():
        ix = np.asarray(idx)
        oo = o[ix]
        perm = np.argsort(oo, kind="mergesort")
        g = np.empty(ix.size)
        g[perm] = np.sort(v[ix])
        for u in np.unique(oo):
            m = oo == u
            if m.sum() > 1:
                g[m] = g[m].mean()
        out[ix] = g
    return out


def fit_war_map(train: list[dict]) -> dict | None:
    """The continuous consensus-FV-to-WAR line for pricing: weighted least squares of the
    training target on [1, consensus FV]. A line, so it is monotone and never a table by
    grade. None when the rows cannot support it."""
    if len(train) < MIN_TEST_ROWS:
        return None
    fv = np.array([r["fv"] for r in train], dtype=np.float64)
    if float(fv.std()) <= 0:
        return None
    y = np.array([r["target"] for r in train], dtype=np.float64)
    w = np.array([max(float(r.get("weight", 1.0) or 0.0), 1e-3) for r in train])
    b = _wls(np.column_stack([np.ones(fv.size), fv]), y, w, np.zeros(2))
    return {"a": float(b[0]), "b": float(b[1]), "n": int(fv.size)}


def war_at(war_map: dict | None, grade) -> np.ndarray:
    g = np.asarray(grade, dtype=np.float64)
    if war_map is None:
        return np.full(g.shape, np.nan)
    return war_map["a"] + war_map["b"] * g


# ---------------------------------------------------------------------------
# the heads in consensus-percentile equivalents
# ---------------------------------------------------------------------------

def head_usable(head: dict | None) -> bool:
    """A head moves the order only when it carries a nonzero driver slope and a positive
    consensus slope to express it against."""
    return bool(head is not None and head.get("b_uc", 0.0) > 0
                and any(abs(b) > 0 for b in head.get("beta") or ()))


def e_skill(head: dict | None, rows: list[dict]) -> np.ndarray:
    """The skill head's driver sum over its own consensus slope (0 when unusable)."""
    if not head_usable(head):
        return np.zeros(len(rows))
    return _lin(head, skill_design(rows, head)) / head["b_uc"]


def e_time(head: dict | None, rows: list[dict]) -> np.ndarray:
    """The timing head's logit driver sum over its own logit consensus slope."""
    if not head_usable(head):
        return np.zeros(len(rows))
    return _lin(head, _v2_x(rows, head["keys"], head["means"])) / head["b_uc"]


# ---------------------------------------------------------------------------
# DS-08: the combiner rule (fixed weights, fixed before any development read)
# ---------------------------------------------------------------------------

def _rule_heads(train: list[dict], side: str, *, ids_outcome_blind: bool,
                absent_ok: bool) -> tuple[dict | None, dict | None]:
    """The side's FULL candidate heads on rule-fold training rows: admission is not
    applied (no rule fold has two earlier vintages that give a t, the rule's own
    precondition failing, recorded in the receipt), and a head whose nested CV has no
    inner year takes RULE_FALLBACK_ALPHA instead of switching off."""
    skill = fit_skill_head(train, side, admit=False, candidates=skill_candidates(side),
                           no_inner_alpha=RULE_FALLBACK_ALPHA)
    timing = fit_timing_head(train, side, admit=False, ids_outcome_blind=ids_outcome_blind,
                             absence_admitted=absent_ok,
                             candidates=timing_candidates(
                                 side, ids_outcome_blind=ids_outcome_blind,
                                 absence_admitted=absent_ok),
                             no_inner_alpha=RULE_FALLBACK_ALPHA)
    return skill, timing


def combiner_rule(side: str, sources: dict[str, list[dict]], *,
                  last_year: int = RULE_LAST_YEAR, absent_ok: bool | None = None) -> dict:
    """DS-08. The weights, by one rule that reads only rows at or before `last_year`.

    THE RULE AS SPECIFIED (s4.3): the pooled forward-chained OLS coefficient on (model leg
    minus consensus) over decision years up to 2016, the timing share at the ratio of the
    two heads' coefficients, and w at or below 0 means that side orders by consensus.

    AS IMPLEMENTED, per source (the v1 matrices, decision years <= last_year; the F-LV
    frame, list vintages <= last_year), for every rule year y with MIN_TEST_ROWS rows
    and MIN_TRAIN_ROWS earlier rows: fit the side's skill and timing heads on the
    earlier rows (F-LV: every player in year y left out of them) and express each on
    year y's rows in consensus-percentile equivalents (e_skill, e_time). A year counts
    when either head moves some row. Pool the counted years of every source and fit
    OLS u_y ~ 1 + u_c + e_skill + e_time (u_c, u_y within year). Then
        w_skill = clip(c_skill / c_uc, 0, W_MAX),  w_time = clip(c_time / c_uc, 0, W_MAX),
    both 0 when c_uc <= 0, and a column that is zero on every pooled row gets weight 0.
    A weight is a SHARE of the head's own estimate (1 = the head as fitted, 0 =
    consensus alone), so it is bounded by W_MAX = 1: a ratio above 1 would extrapolate
    past the head, and the rule's fixed fallback penalty (adaptation 3) over-shrinks the
    rule-fold head, which inflates the ratio. DISCLOSED: the bound was added after the
    first dry run of the rule read 1.29 for pitchers; the unbounded ratios stay in the
    receipt (w_skill_ratio, w_time_ratio).

    THREE STATED ADAPTATIONS, each because the literal rule cannot run:
      1. the matrices at decision years <= 2016 carry 3 rows with a MiLB block per side
         (the era rule marks the rest milb_unavailable), so no skill head fits there; the
         list-vintage frame at vintages <= 2016 is added. V2 is then scored only from
         V2_FIRST_SCORED_YEAR, so no rule row is ever a scored row.
      2. admission is off inside rule folds: it needs two earlier vintages that give a
         t, and no rule year has them.
      3. a head whose nested CV has no inner year takes RULE_FALLBACK_ALPHA.
    Reads no row after last_year; the receipt carries every (source, year) read."""
    _check_years({int(r["decision_year"]) for rows in sources.values() for r in rows})
    ab = absence_admitted(side) if absent_ok is None else bool(absent_ok)
    pooled = {"u_c": [], "u_y": [], "e_s": [], "e_t": []}
    receipt: dict = {}
    for name, rows in sources.items():
        rule_rows = [r for r in rows if int(r["decision_year"]) <= int(last_year)]
        ob = all(bool(r.get("ids_outcome_blind")) for r in rule_rows) and bool(rule_rows)
        rec = {"n_rows": len(rule_rows), "ids_outcome_blind": ob,
               "years": sorted({int(r["decision_year"]) for r in rule_rows}),
               "folds": {}}
        for y in inner_years(rule_rows):
            te = [r for r in rule_rows if r["decision_year"] == y]
            te_keys = {r["player_key"] for r in te}
            tr = [r for r in rule_rows if r["decision_year"] < y
                  and not (ob and r["player_key"] in te_keys)]
            skill, timing = _rule_heads(tr, side, ids_outcome_blind=ob,
                                        absent_ok=ob and ab)
            es, et = e_skill(skill, te), e_time(timing, te)
            moved = bool(np.any(es != 0) or np.any(et != 0))
            rec["folds"][str(y)] = {
                "n_train": len(tr), "n_test": len(te), "counted": moved,
                "skill_keys": (skill or {}).get("keys"),
                "skill_alpha": _akey((skill or {}).get("alpha", math.inf)),
                "skill_n_train": (skill or {}).get("n_train"),
                "timing_keys": (timing or {}).get("keys"),
                "timing_alpha": _akey((timing or {}).get("alpha", math.inf))}
            if not moved:
                continue
            u_c, u_y = _percentiles(te)
            pooled["u_c"] += u_c.tolist()
            pooled["u_y"] += u_y.tolist()
            pooled["e_s"] += es.tolist()
            pooled["e_t"] += et.tolist()
        receipt[name] = rec
    n = len(pooled["u_y"])
    out = {"side": side, "last_year": int(last_year), "n_pooled": n, "sources": receipt,
           "absence_admitted": ab, "coef": None, "se": None,
           "w_skill": 0.0, "w_time": 0.0, "a": None}
    if n < MIN_TRAIN_ROWS:
        out["status"] = "not_estimable"
        out["reason"] = f"{n} pooled rows, fewer than {MIN_TRAIN_ROWS}"
        return out
    cols = {"u_c": pooled["u_c"], "e_skill": pooled["e_s"], "e_time": pooled["e_t"]}
    live = [k for k, v in cols.items() if k == "u_c" or np.any(np.asarray(v) != 0)]
    X = np.column_stack([np.ones(n)] + [np.asarray(cols[k]) for k in live])
    y = np.asarray(pooled["u_y"], dtype=np.float64)
    XtX = X.T @ X
    b = np.linalg.solve(XtX, X.T @ y)
    resid = y - X @ b
    s2 = float(resid @ resid) / (n - X.shape[1])         # n >= MIN_TRAIN_ROWS
    se = np.sqrt(np.abs(np.diag(np.linalg.inv(XtX))) * s2)
    coef = {"intercept": float(b[0]), **{k: float(b[i + 1]) for i, k in enumerate(live)}}
    ses = {"intercept": float(se[0]), **{k: float(se[i + 1]) for i, k in enumerate(live)}}
    c_uc = coef["u_c"]
    c_s, c_t = coef.get("e_skill"), coef.get("e_time")
    r_s = c_s / c_uc if (c_uc > 0 and c_s is not None) else None
    r_t = c_t / c_uc if (c_uc > 0 and c_t is not None) else None
    w_s, w_t = _share(r_s), _share(r_t)
    out.update(status="ok", coef=coef, se=ses, live_columns=live,
               w_skill_ratio=None if r_s is None else round(r_s, 6),
               w_time_ratio=None if r_t is None else round(r_t, 6),
               w_skill=round(w_s, 6), w_time=round(w_t, 6),
               a=(round(w_t / w_s, 6) if w_s > 0 else None))
    return out


def _share(ratio: float | None) -> float:
    """A combiner ratio as a weight: 0 when absent or not positive, W_MAX above it.
    It bounds a weight on a head, never a prediction."""
    if ratio is None or not ratio > 0:
        return 0.0
    return W_MAX if ratio > W_MAX else float(ratio)


def load_weights(path: Path | None = None) -> dict[str, dict]:
    """{side: {"w_skill", "w_time"}} from the registration artifact."""
    p = ASSEMBLY_PATH if path is None else Path(path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {s: {"w_skill": float(doc["weights"][s]["w_skill"]),
                "w_time": float(doc["weights"][s]["w_time"])} for s in F.SIDES}


# ---------------------------------------------------------------------------
# the assembled model: fit, order, grade
# ---------------------------------------------------------------------------

def fit_v2(train: list[dict], side: str, *, frame: str, weights: dict[str, dict],
           absent_ok: bool | None = None, extra: dict | None = None) -> dict:
    """V2 on one fold's training rows. frame "lv" (outcome-blind ids: protection and the
    absence flag may enter the timing head) or "vm" (the v1 matrices: they may not).
    Admission runs inside both head fits on the fold's own training vintages.
    `extra` ({"skill": keys, "timing": keys}, the screening lab only) offers screening
    columns (V2_SCREEN_PREFIX) to a head beside the side's own candidates, under the
    same admission rule; with "force": True they are admitted without it (the lab's
    floor derivation only). None leaves every served path as it is."""
    if frame not in ("lv", "vm"):
        raise ValueError(f"frame must be lv or vm, got {frame!r}")
    _check_years({int(r["decision_year"]) for r in train})
    ex = {h: tuple((extra or {}).get(h) or ()) for h in ("skill", "timing")}
    for ks in ex.values():
        for k in ks:
            if not str(k).startswith(V2_SCREEN_PREFIX):
                raise ValueError(f"a screening column must carry the prefix "
                                 f"{V2_SCREEN_PREFIX!r}, got {k!r}")
    ob = frame == "lv"
    ab = ob and (absence_admitted(side) if absent_ok is None else bool(absent_ok))
    forced = bool((extra or {}).get("force"))
    skill = fit_skill_head(train, side,
                           candidates=skill_candidates(side) + ex["skill"],
                           force=ex["skill"] if forced else ())
    timing = None
    why = None
    if side == "pit" and not head_usable(skill):
        why = ("owner DS-Q2: no pitcher skill driver passed the admission rule in this "
               "fold, so pitchers take the consensus order")
    else:
        timing = fit_timing_head(train, side, ids_outcome_blind=ob, absence_admitted=ab,
                                 candidates=timing_candidates(
                                     side, ids_outcome_blind=ob, absence_admitted=ab)
                                 + ex["timing"],
                                 force=ex["timing"] if forced else ())
    w = weights[side]
    w_s = float(w["w_skill"]) if head_usable(skill) else 0.0
    w_t = float(w["w_time"]) if head_usable(timing) else 0.0
    if why is None and w_s <= 0 and w_t <= 0:
        why = "no usable head carries a positive registered weight"
    out = {"model_id": V2_ASSEMBLED_ID, "side": side, "frame": frame,
           "skill": skill, "timing": timing, "w_skill": w_s, "w_time": w_t,
           "consensus_only": w_s <= 0 and w_t <= 0, "consensus_only_reason": why,
           "war_map": fit_war_map(train), "n_train": len(train),
           "train_years": sorted({int(r["decision_year"]) for r in train})}
    if extra:
        out["extra"] = dict(ex, force=forced)
    return out


def predict_v2(model: dict, rows: list[dict]) -> list[dict]:
    """Per row: u_c, e_skill, e_time, order_idx, the eFV grade (DS-07) and the eFV WAR
    (pricing). Groups are the rows' own (side, decision year or list vintage)."""
    if not rows:
        return []
    groups = [int(r["decision_year"]) for r in rows]
    fv = np.array([r["fv"] for r in rows], dtype=np.float64)
    u_c = within_pct(fv, groups)
    es = e_skill(model["skill"], rows) if model["w_skill"] > 0 else np.zeros(len(rows))
    et = e_time(model["timing"], rows) if model["w_time"] > 0 else np.zeros(len(rows))
    order = u_c + model["w_skill"] * es + model["w_time"] * et
    grade = output_map(order, groups, fv)
    war = war_at(model["war_map"], grade)
    return [{"player_key": r["player_key"], "u_c": float(u_c[i]),
             "e_skill": float(es[i]), "e_time": float(et[i]),
             "order_idx": float(order[i]), "efv_grade": float(grade[i]),
             "efv_war": float(war[i])} for i, r in enumerate(rows)]


def _check_scored_year(y: int) -> None:
    if int(y) <= RULE_LAST_YEAR:
        raise ValueError(f"year {y} is a combiner-rule year (<= {RULE_LAST_YEAR}); V2 is "
                         f"scored only from {V2_FIRST_SCORED_YEAR}")


def v2_lv_scores(side: str, vintage: int, frame_rows: list[dict],
                 train_rows: list[dict], *, weights: dict[str, dict],
                 gate_sha: str | None = None) -> dict:
    """V2 on one F-LV (side, V) frame, fitted on labelled F-LV rows at vintages before V
    with every player in the V frame left out of training. Reserved vintages raise
    without the committed gate sha; rule years raise."""
    V = int(vintage)
    F.guard_score_request(V, gate_sha=gate_sha, purpose="V2 score")
    _check_scored_year(V)
    test = lv_v2_rows(side, V, frame_rows, gate_sha=gate_sha)
    in_frame = {r["player_key"] for r in frame_rows}
    tr = [r for r in train_rows if r["decision_year"] < V
          and r["player_key"] not in in_frame]
    model = fit_v2(tr, side, frame="lv", weights=weights)
    return {"side": side, "vintage": V, "n_train": len(tr), "n_scored": len(test),
            "model": model, "rows": predict_v2(model, test)}


def v2_vm_scores(side: str, *, weights: dict[str, dict], years=None,
                 timing_pin: bool = False, data: list[dict] | None = None,
                 receipts: dict | None = None) -> dict[int, dict]:
    """V2 on the vintage-matched frame, forward-chained like oos_scores: each decision
    year scored by a fit on earlier matrix rows. timing_pin=True scores only the debuted
    rows with an in-window preseason read, with that read (and BMI as of it) as input."""
    years = [y for y in (V1.SCORED_YEARS if years is None else years)]
    _check_years(years)
    for y in years:
        _check_scored_year(y)
    data = matrix_training_rows(side) if data is None else data
    mine: dict = {}
    pinned = pinned_inputs(side, data, mine) if timing_pin else {}
    if timing_pin:
        import efv_drivers as DRV
        panel = DRV.load_bio_panel()
    out = {}
    for yr in years:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < MIN_TEST_ROWS or len(tr) < MIN_TRAIN_ROWS:
            continue
        if timing_pin:
            te2 = []
            for r in te:
                pin = pinned.get(r["player_key"])
                if pin is None:
                    continue
                extra = {"bmi": DRV.bmi_asof(r["player_key"],
                                             mine[r["player_key"]].get("asof_date"),
                                             panel)}
                te2.append(dict(r, feats=pin["feats"], fv=pin["fv"], extra=extra,
                                v2=v2_row(pin["feats"], extra)))
            te = te2
        model = fit_v2(tr, side, frame="vm", weights=weights)
        out[yr] = {"model": model, "rows": predict_v2(model, te)}
    if timing_pin and receipts is not None:
        receipts.update(mine)
    return out


# ===========================================================================
# DS-17: the P(bust) chip (docs/efv-v2/DRIVER_SYSTEM_V2.md s3 idea 10, s4.2 ADD, s5)
# ===========================================================================
# A PROBABILITY, NOT AN ORDER. P(bust) is one minus the probability of reaching the
# majors inside the frame's window (R3 on the list-vintage frame: a debut inside
# V..V+3; on the v1 matrices: the matrix's own debuted-versus-never split). It comes
# from the SAME REACHED/timing head that feeds V2's order index (fit_timing_head, same
# candidates, same admission rule), plus one calibration term: the FG-vs-Pipeline
# spread, the absolute difference of the two sources' within-(side, year) percentiles
# (lane I4: two graders who disagree mark a riskier prospect; every conversion of the
# spread into a RANK shift lost, so it enters here and nowhere else).
#
#     logit P(REACHED) = b0 + b_uc * u_c + timing drivers + c_s * z(spread)
#     P(bust)          = 1 - P(REACHED)
#
# The spread enters only if it passes the DS-06 admission rule with the REACHED target
# inside the fold (per training vintage, on the rows that OBSERVE both sources); c_s is
# then fitted with the head's linear predictor as a fixed offset. A row without both
# sources reads the head alone (never an imputed spread), so the spread's presence can
# carry no signal. FG grades exist from list vintage 2017, so the spread can be admitted
# only in folds with two earlier vintages that observe it.
#
# RESERVED FRAMES: the spread may not be credited on R-LV (bug B9a, one prior exposure of
# R-LV-overlapping rows); nothing here reads a reserved row (_check_years).
# GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-year
# percentile only; calibration is reported by side and by equal-count ranges of the
# PREDICTED probability, never by grade level.

PBUST_MODEL_ID = "efv_v2_pbust"
PBUST_SPREAD_KEY = "spread"


def spread_values(pairs, groups) -> list[float | None]:
    """|within-group percentile of Pipeline - within-group percentile of FanGraphs| per
    row, over the rows of each group that carry BOTH grades; None where either is
    missing. `pairs` is [(fangraphs, pipeline) or None], `groups` the rows' (side, year)
    labels."""
    out: list[float | None] = [None] * len(pairs)
    by: dict = {}
    for i, (p, g) in enumerate(zip(pairs, groups)):
        if p is None or p[0] is None or p[1] is None:
            continue
        by.setdefault(g, []).append(i)
    for idx in by.values():
        fg = within_pct([float(pairs[i][0]) for i in idx], [0] * len(idx))
        pl = within_pct([float(pairs[i][1]) for i in idx], [0] * len(idx))
        for j, i in enumerate(idx):
            out[i] = float(abs(pl[j] - fg[j]))
    return out


def _spread_arr(rows: list[dict]) -> np.ndarray:
    return np.array([np.nan if r.get(PBUST_SPREAD_KEY) is None
                     else float(r[PBUST_SPREAD_KEY]) for r in rows], dtype=np.float64)


def _u_c(rows: list[dict]) -> np.ndarray:
    """The consensus percentile within each row's own year (no label read)."""
    return within_pct([r["fv"] for r in rows], [int(r["decision_year"]) for r in rows])


def spread_admission(train: list[dict], *, min_rows: int = ADMIT_MIN_ROWS) -> dict:
    """The DS-06 rule for the spread against REACHED: per training vintage, the t of
    z(spread) in OLS reached ~ 1 + u_c + z(spread) on the rows that observe the spread
    (u_c within the vintage over all its rows)."""
    _check_years({int(r["decision_year"]) for r in train})
    u_c = _u_c(train)
    s = _spread_arr(train)
    y = np.array([r["reached"] for r in train], dtype=np.float64)
    t_by = {}
    for yr in sorted({int(r["decision_year"]) for r in train}):
        ix = [i for i, r in enumerate(train)
              if int(r["decision_year"]) == yr and not np.isnan(s[i])]
        t_by[yr] = (admission_t(u_c[ix], y[ix], s[ix], min_rows=min_rows)
                    if len(ix) >= min_rows else None)
    return admission_check(t_by)


def _head_eta(head: dict, rows: list[dict]) -> np.ndarray:
    """The REACHED head's full linear predictor on rows (u_c within the rows' years)."""
    return (head["b0"] + head["b_uc"] * _u_c(rows)
            + _lin(head, _v2_x(rows, head["keys"], head["means"])))


def consensus_only_head(train: list[dict], side: str) -> dict | None:
    """The reference REACHED head: a logistic on the consensus percentile alone."""
    head = _timing_fit(train, (), math.inf)
    if head is not None:
        head.update({"side": side, "admission": {}, "candidates": []})
    return head


def fit_pbust(train: list[dict], side: str, *, frame: str, timing: dict | None = None,
              spread: str = "admit", absent_ok: bool | None = None,
              consensus_only: bool = False) -> dict:
    """The P(bust) chip on one fold's training rows (each carrying `v2`, `fv`,
    `reached`, `decision_year` and optionally `spread`).

    timing  the REACHED head (fit_timing_head with V2's candidates for the frame and the
            admission rule) unless one is handed in; with no usable head, the consensus
            percentile alone (a logistic on u_c).
    spread  "admit" (the chip: the DS-06 rule decides), "force" (a diagnostic: always
            fitted when enough rows observe it) or "off".
    consensus_only  the reference arm (consensus_only_head, no spread): what the served
            chip uses while the DS-17 read says the chip does not beat it
            (pbust_serving_arm)."""
    if frame not in ("lv", "vm"):
        raise ValueError(f"frame must be lv or vm, got {frame!r}")
    if spread not in ("admit", "force", "off"):
        raise ValueError(f"spread must be admit, force or off, got {spread!r}")
    _check_years({int(r["decision_year"]) for r in train})
    ob = frame == "lv"
    ab = ob and (absence_admitted(side) if absent_ok is None else bool(absent_ok))
    if consensus_only:
        timing, spread = consensus_only_head(train, side), "off"
    head = timing
    if head is None:
        head = fit_timing_head(train, side, ids_outcome_blind=ob, absence_admitted=ab,
                               candidates=timing_candidates(side, ids_outcome_blind=ob,
                                                            absence_admitted=ab))
    if head is None:
        head = consensus_only_head(train, side)
    out = {"model_id": PBUST_MODEL_ID, "consensus_only": bool(consensus_only), "side": side, "frame": frame, "timing": head,
           "spread_mode": spread, "spread_admission": None, "spread_used": False,
           "c_spread": 0.0, "spread_mu": None, "spread_sd": None,
           "n_train": len(train), "n_spread_train": 0,
           "train_years": sorted({int(r["decision_year"]) for r in train})}
    if head is None or spread == "off":
        return out
    s = _spread_arr(train)
    obs = ~np.isnan(s)
    out["n_spread_train"] = int(obs.sum())
    chk = spread_admission(train)
    out["spread_admission"] = chk
    use = chk["admitted"] if spread == "admit" else True
    if not use or obs.sum() < MIN_TRAIN_ROWS or float(np.nanstd(s)) <= 0:
        return out
    mu, sd = float(np.nanmean(s)), float(np.nanstd(s))
    z = (s[obs] - mu) / sd
    y = np.array([r["reached"] for r in train], dtype=np.float64)
    eta = _head_eta(head, train)
    c = _logistic(z[:, None], y[obs], eta[obs], np.array([_OFFSET_EPS]))
    out.update(spread_used=True, c_spread=float(c[0]), spread_mu=mu, spread_sd=sd)
    return out


def predict_pbust(model: dict, rows: list[dict]) -> list[dict]:
    """Per row: p_reach and p_bust = 1 - p_reach, from the head's linear predictor plus
    the spread term on rows that observe it (u_c within the rows' own years)."""
    if not rows:
        return []
    head = model["timing"]
    if head is None:
        raise ValueError("the P(bust) model has no REACHED head")
    eta = _head_eta(head, rows)
    if model.get("spread_used"):
        s = _spread_arr(rows)
        obs = ~np.isnan(s)
        zs = np.where(obs, (np.nan_to_num(s) - model["spread_mu"]) / model["spread_sd"], 0.0)
        eta = eta + model["c_spread"] * zs
    p = _sigmoid(eta)
    return [{"player_key": r["player_key"], "decision_year": int(r["decision_year"]),
             "p_reach": float(p[i]), "p_bust": float(1.0 - p[i]),
             "spread_used": bool(model.get("spread_used")
                                 and r.get(PBUST_SPREAD_KEY) is not None)}
            for i, r in enumerate(rows)]


PBUST_EVAL_PATH = DATA_DIR / "efv_v2_pbust_eval.json"


def pbust_serving_arm(path: Path | None = None) -> str:
    """The P(bust) arm the served chip may use, from the committed DS-17 read
    (tools/efv_pbust_read.py SERVING_RULE): "chip" or "consensus". With no read on disk
    the answer is "consensus" (the chip has not been shown to beat it)."""
    p = PBUST_EVAL_PATH if path is None else Path(path)
    if not p.exists():
        return "consensus"
    doc = json.loads(p.read_text(encoding="utf-8"))
    arm = (doc.get("serving") or {}).get("arm")
    return arm if arm in ("chip", "consensus") else "consensus"
