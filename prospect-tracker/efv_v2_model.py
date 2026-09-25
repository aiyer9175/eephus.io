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
