# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v2 model-class candidates: the arms of docs/efv-v2/MODEL_CLASS_SCREEN.md.

TRAINING CODE ONLY (EFV3_C02). Nothing here is served, nothing here reads a frame and
nothing here scores a row: the one screen that reads these arms is EFV3_C03
(tools/efv_v2_model_class_screen.py), one run on the frozen fWAR label, after the epoch.
The served eFV is Driver System V2 as assembled (efv_v2_model.fit_v2 at the weights in
data/efv_v2_assembly.json); every arm here WRAPS fit_v2 and predict_v2 and changes one
named thing. The arm definitions in MODEL_CLASS_SCREEN.md s2 are binding; the grid, the
pair weighting, the band boundary, the knot rule and the reliability rule are fixed here
and never re-shopped.

THE ARMS (model_id efv_v2_mc_<arm>; the rows are the rows fit_v2 consumes):

    MC-1  fit_mc1_pairwise   the skill head refit as a Bradley-Terry residual head:
                             pairs (i, j) inside one training (side, decision_year)
                             group with u_y_i > u_y_j, weighted |u_y_i - u_y_j| (ties at
                             W3 = 0 contribute nothing), loss log(1 + exp(-(s_i - s_j))),
                             s = b_uc * u_c + z(x) @ beta, b_uc free, beta L2-penalized
                             on V2_ALPHAS by the same nested forward-chained rule. The
                             listwise weighting is a SENSITIVITY (pair_weighting), never
                             the arm.
    MC-2  fit_mc2_anchor     u_c replaced by u_c*, the reliability-weighted mean of the
                             in-window sources' within-(side, V) percentiles; weights
                             from build_source_reliability (list vintages at most V - 3,
                             k 150 shrink toward equal, clamp (0.6, 1.5)); the served
                             single-source rule applied unchanged; a row missing a
                             source gets no indicator. Heads, admission and weights are
                             V2's, fitted on u_c*.
    MC-3  fit_mc3_twoband    V2's heads with w_skill and w_time by band: last level at
                             the read AA or above (upper) against below or no block
                             (lower); the band weights come from combiner_rule run per
                             band on rule years at most RULE_LAST_YEAR (band_weights),
                             clipped to [0, 1]. A no-block row takes the lower band.
    MC-4a fit_mc4a_signed    V2's heads with every admitted slope constrained to its
                             admitted sign by the active-set rule (fit, zero the wrong
                             signs, refit the rest, repeat). Deterministic.
    MC-4b fit_mc4b_spline    each admitted driver as a 3-piece monotone I-spline in the
                             admitted direction, pieces at the training terciles, the
                             basis coefficients sign-constrained as MC-4a; under
                             MC4B_MIN_HAS_BLOCK_ROWS has-block training rows the fold
                             falls back to MC-4a and says so.
    MC-5  fit_mc5_pricing    the pricing line (fit_war_map) with position-family dummies
                             and age at the read as continuous covariates; order_idx is
                             untouched (predict_mc5 keeps predict_v2's order bit for
                             bit). Outside the Holm family: an MAE row only.

DETERMINISM. Every fit is closed form or Newton from a zero start (efv_v2_model._wls,
_logistic and the weighted Newton here); no random step anywhere.

FRAMES. No frame is read here. guard_training_rows runs before any fit: a 2025+ decision
year raises through efv_v2_model._check_years and a reserved list vintage (R-LV, 2020 and
2021) through efv_vintage_frame.guard_score_request. This module imports efv_v2_model,
efv_vintage_frame and source_backtest only (test_efv_v2_candidates.py scans it): never a
label module, never a WAR column. The reliability table's target is the row's `target`
the caller joined (W3 on list vintages), read as ranks only.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-(side, year)
percentile, as the sources' within percentiles, and as the value multiset the grade is
drawn from (output_map). Nothing groups, counts or averages rows by grade level.
"""
from __future__ import annotations

import math

import numpy as np

import efv_v2_model as H
import efv_vintage_frame as F
import source_backtest as SB

#: model_id per arm. MC-5 is a pricing item, not an arm of the Holm family.
ARM_IDS: dict[str, str] = {"mc1": "efv_v2_mc_1", "mc2": "efv_v2_mc_2", "mc3": "efv_v2_mc_3",
                           "mc4a": "efv_v2_mc_4a", "mc4b": "efv_v2_mc_4b",
                           "mc5": "efv_v2_mc_5"}
#: The five arms of the family (Holm m 5).
FAMILY: tuple[str, ...] = ("mc1", "mc2", "mc3", "mc4a", "mc4b")
#: MC-4a's flag (MODEL_CLASS_SCREEN.md s2): off, and read by nothing served. fit_v2 does
#: not read it in this step; the screen and, later, the look runner read the constrained
#: fit in-process. It flips only after a registered look passes, through EV-15.
V2_SIGN_CONSTRAINED = False
#: MC-1 pair weightings: the arm is "distance"; "listwise" is the sensitivity.
PAIR_WEIGHTINGS: tuple[str, ...] = ("distance", "listwise")
#: MC-2: a reliability for list vintage V reads list vintages at most V - RELIABILITY_LAG
#: (the consensus_weight_eval vintage rule, "base years <= Y - 3 only").
RELIABILITY_LAG = 3
#: MC-2: the anchor travels on the row under this key once attach_anchor has run.
ANCHOR_KEY = "u_anchor"
#: MC-3: the band boundary, efv_dataset._LEVEL_RANK["AA"] (AAA is one above). A row at
#: or above it, with a block, is the upper band; every other row is the lower band.
MC3_BAND_AA_RANK = 4.0
MC3_BANDS: tuple[str, ...] = ("upper", "lower")
#: MC-3 twin control hook (EFV3_C03, MODEL_CLASS_SCREEN.md s5): a row carrying a band
#: label under this key is read as that band by band_of_row. The screen's
#: zero-information twin permutes the band labels within vintage by writing it; no
#: frame row, matrix row or served path carries the key.
MC3_BAND_KEY = "mc3_band"
#: MC-4b: folds with fewer has-block training rows fall back to MC-4a.
MC4B_MIN_HAS_BLOCK_ROWS = 300
#: MC-4b: the spline's interior breakpoints, the training terciles of the driver.
MC4B_KNOT_QUANTILES: tuple[float, float] = (1.0 / 3.0, 2.0 / 3.0)
MC4B_PIECES = 3
#: MC-5: position families per side, the first entry the reference level of the dummies.
MC5_FAMILIES: dict[str, tuple[str, ...]] = {"hit": ("corner", "middle", "other"),
                                            "pit": ("sp", "rp")}
#: MC-5: the listed position at the read (never the served current one) to a family.
#: C, SS and CF are "middle"; 1B, LF, RF and DH are "corner"; anything else is "other".
MC5_POSITIONS: dict[str, str] = {"C": "middle", "SS": "middle", "CF": "middle",
                                 "1B": "corner", "LF": "corner", "RF": "corner",
                                 "DH": "corner"}
MC5_RP_TOKENS: tuple[str, ...] = ("RP", "CL", "RELIEVER", "CLOSER")


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def guard_training_rows(train: list[dict], frame: str, *,
                        gate_sha: str | None = None) -> list[int]:
    """The years of the training rows, after the reserved-frame guards: a 2025+ year
    raises through efv_v2_model._check_years on either frame, and on the list-vintage
    frame a reserved list vintage raises through efv_vintage_frame.guard_score_request.
    Only the committed gate's sha (`gate_sha`, the reserved confirmation read of
    tools/efv_v3_backtest.py) opens either; the screen hands none in. Runs before any
    fit in this module."""
    if frame not in ("lv", "vm"):
        raise ValueError(f"frame must be lv or vm, got {frame!r}")
    years = sorted({int(r["decision_year"]) for r in train})
    H._check_years(years, gate_sha=gate_sha)
    if frame == "lv":
        for y in years:
            F.guard_score_request(y, gate_sha=gate_sha, purpose="candidate fit")
    return years


def _skill_cands(side: str) -> tuple[str, ...]:
    cands = H.skill_candidates(side)
    if H.V2_ABSENCE_KEY in cands:
        raise ValueError("the absence flag may not enter the skill head (DS-04)")
    return cands


# ---------------------------------------------------------------------------
# primitives shared by the arms
# ---------------------------------------------------------------------------

def _wlogistic(Z: np.ndarray, y: np.ndarray, w: np.ndarray,
               penalty: np.ndarray) -> np.ndarray:
    """efv_v2_model._logistic with a sample weight per row (no offset): maximize
    sum(w * (y * eta - log(1 + e^eta))) - 0.5 * sum(penalty * beta^2), eta = Z @ beta,
    by Newton from zero with the module's iteration count and tolerance."""
    beta = np.zeros(Z.shape[1])
    P = np.diag(penalty)
    for _ in range(H._NEWTON_MAX_IT):
        p = H._sigmoid(Z @ beta)
        g = Z.T @ (w * (y - p)) - penalty * beta
        Hm = (Z * (w * p * (1.0 - p))[:, None]).T @ Z + P
        step = np.linalg.solve(Hm, g)
        beta = beta + step
        if float(np.max(np.abs(step))) < H._NEWTON_TOL:
            break
    return beta


def _uc(rows: list[dict]) -> np.ndarray:
    """The consensus percentile within decision year (efv_v2_model._percentiles), or
    the anchor u_c* when every row carries one (MC-2)."""
    if not rows:
        return np.zeros(0)
    n_anchor = sum(1 for r in rows if ANCHOR_KEY in r)
    if n_anchor == len(rows):
        return np.array([float(r[ANCHOR_KEY]) for r in rows], dtype=np.float64)
    if n_anchor:
        raise ValueError("every row or no row carries the anchor")
    return H._percentiles(rows)[0]


def _weights_of(rows: list[dict]) -> np.ndarray:
    return np.array([max(float(r.get("weight", 1.0) or 0.0), 1e-3) for r in rows])


# designs: a callable (rows, means) -> (X, column names, head metadata)

def _v2_design(keys):
    cols = tuple(keys)

    def design(rows, means):
        return H._v2_x(rows, cols, means), list(cols), {"design": {"kind": "v2"}}
    return design


def _ramp(x: np.ndarray, a: float, b: float) -> np.ndarray:
    """One non-decreasing piece: 0 at or below a, 1 at or above b, linear between; a
    zero-width piece is the step at a."""
    if b > a:
        return np.clip((x - a) / (b - a), 0.0, 1.0)
    return (x > a).astype(np.float64)


def ispline_knots(x) -> list[float]:
    """[lo, t1, t2, hi]: the training minimum, the terciles and the maximum."""
    xx = np.asarray(x, dtype=np.float64)
    q = np.quantile(xx, MC4B_KNOT_QUANTILES)
    return [float(xx.min()), float(q[0]), float(q[1]), float(xx.max())]


def ispline_basis(x, knots) -> np.ndarray:
    """The 3-piece monotone I-spline basis (order 2, integrated piecewise-constant
    M-splines): one ramp per piece, each non-decreasing from 0 to 1, so any
    non-negative combination is non-decreasing in x."""
    lo, t1, t2, hi = (float(k) for k in knots)
    xx = np.asarray(x, dtype=np.float64)
    return np.column_stack([_ramp(xx, lo, t1), _ramp(xx, t1, t2), _ramp(xx, t2, hi)])


def _ispline_design(drivers, signs: dict, knots: dict | None = None, columns=None):
    """The MC-4b design: each driver's I-spline basis in its admitted direction (the
    basis of sign * x, so the basis is non-decreasing in the admitted direction). Knots
    come from the rows the head is fitted on when `knots` is None (training rows only)
    and are reused as given otherwise. `columns` selects basis columns (the active set)."""
    drivers = tuple(drivers)

    def design(rows, means):
        X = H._v2_x(rows, drivers, means)
        kn = {} if knots is None else {k: list(v) for k, v in knots.items()}
        cols, parts = [], []
        for j, k in enumerate(drivers):
            s = float(signs.get(k) or 1)
            xs = s * X[:, j]
            if k not in kn:
                if xs.size == 0:
                    raise ValueError("knots need training rows")
                kn[k] = ispline_knots(xs)
            parts.append(ispline_basis(xs, kn[k]))
            cols += [f"{k}~i{p + 1}" for p in range(MC4B_PIECES)]
        Xb = np.column_stack(parts) if parts else np.zeros((len(rows), 0))
        if columns is not None:
            sel = [cols.index(c) for c in columns]
            Xb, cols = Xb[:, sel], list(columns)
        meta = {"design": {"kind": "ispline", "drivers": list(drivers),
                           "signs": {k: int(signs.get(k) or 1) for k in drivers},
                           "knots": kn, "pieces": MC4B_PIECES}}
        return Xb, cols, meta
    return design


def _head_x(head: dict, rows: list[dict]) -> np.ndarray:
    """The head's raw design on rows: V2's driver columns, or the I-spline basis."""
    d = head.get("design") or {"kind": "v2"}
    if d["kind"] == "ispline":
        X, _cols, _meta = _ispline_design(d["drivers"], d["signs"], d["knots"],
                                          head["keys"])(rows, head["means"])
        return X
    return H._v2_x(rows, head["keys"], head["means"])


def _e(head: dict | None, rows: list[dict]) -> np.ndarray:
    """The head's driver sum over its own consensus slope (efv_v2_model.e_skill /
    e_time, through the head's design); 0 when the head is unusable."""
    if not H.head_usable(head):
        return np.zeros(len(rows))
    return H._lin(head, _head_x(head, rows)) / head["b_uc"]


def _score_sd(head: dict, rows: list[dict]) -> float:
    sc = H._lin(head, _head_x(head, rows))
    return float(sc.std()) if sc.size and sc.std() > 0 else 1.0


def _skill_fit_g(train: list[dict], keys, alpha: float, design) -> dict | None:
    """efv_v2_model._skill_fit on an arbitrary design and on _uc (the anchor when the
    rows carry one): weighted ridge of u_y on [1, u_c, z(design)] over the has-block
    rows, intercept and u_c slope free."""
    rows = H.skill_training_rows(train)
    if len(rows) < H.MIN_TEST_ROWS or not keys:
        return None
    u_c = _uc(train)
    _u, u_y = H._percentiles(train)
    pos = {id(r): i for i, r in enumerate(train)}
    ix = [pos[id(r)] for r in rows]
    means = H.has_block_means(train)
    X, cols, meta = design(rows, means)
    if H.V2_ABSENCE_KEY in cols or H.V2_ABSENCE_KEY in (
            meta.get("design") or {}).get("drivers", ()):
        raise ValueError("the absence flag may not enter the skill head (DS-04)")
    mu, sd, Xs = H._std_cols(X)
    w = _weights_of(rows)
    Z = np.column_stack([np.ones(len(rows)), u_c[ix], Xs])
    if math.isinf(alpha):
        coef = np.concatenate([H._wls(Z[:, :2], u_y[ix], w, np.zeros(2)),
                               np.zeros(len(cols))])
    else:
        pen = np.concatenate([[0.0, 0.0], np.full(len(cols), float(alpha))])
        coef = H._wls(Z, u_y[ix], w, pen)
    head = {"keys": list(cols), "means": means, "alpha": alpha, "mu": mu.tolist(),
            "sd": sd.tolist(), "b0": float(coef[0]), "b_uc": float(coef[1]),
            "beta": [float(b) for b in coef[2:]], "n_train": len(rows),
            "trained_on": "has_block"}
    head.update(meta)
    return head


def _timing_fit_g(train: list[dict], keys, alpha: float, design) -> dict | None:
    """efv_v2_model._timing_fit on an arbitrary design and on _uc: penalized logistic
    of REACHED on [1, u_c, z(design)] over every training row."""
    if len(train) < H.MIN_TRAIN_ROWS:
        return None
    u_c = _uc(train)
    y = np.array([r["reached"] for r in train], dtype=np.float64)
    if y.min() == y.max():
        return None
    means = H.has_block_means(train)
    X, cols, meta = design(train, means)
    mu, sd, Xs = H._std_cols(X)
    zero = np.zeros(len(train))
    if math.isinf(alpha) or not cols:
        coef = np.concatenate([
            H._logistic(np.column_stack([np.ones(len(train)), u_c]), y, zero,
                        np.full(2, H._OFFSET_EPS)), np.zeros(len(cols))])
    else:
        Z = np.column_stack([np.ones(len(train)), u_c, Xs])
        pen = np.concatenate([np.full(2, H._OFFSET_EPS), np.full(len(cols), float(alpha))])
        coef = H._logistic(Z, y, zero, pen)
    head = {"keys": list(cols), "means": means, "alpha": alpha, "mu": mu.tolist(),
            "sd": sd.tolist(), "b0": float(coef[0]), "b_uc": float(coef[1]),
            "beta": [float(b) for b in coef[2:]], "n_train": len(train),
            "trained_on": "all"}
    head.update(meta)
    return head


def _skill_loss(head: dict, te: list[dict]) -> float | None:
    te_hb = H.skill_training_rows(te)
    if not te_hb:
        return None
    u_c = _uc(te)
    _u, u_y = H._percentiles(te)
    pos = {id(r): i for i, r in enumerate(te)}
    ix = [pos[id(r)] for r in te_hb]
    pred = head["b0"] + head["b_uc"] * u_c[ix] + H._lin(head, _head_x(head, te_hb))
    return float(np.sum(_weights_of(te_hb) * (u_y[ix] - pred) ** 2))


def _timing_loss(head: dict, te: list[dict]) -> float | None:
    y = np.array([r["reached"] for r in te], dtype=np.float64)
    eta = head["b0"] + head["b_uc"] * _uc(te) + H._lin(head, _head_x(head, te))
    return float(np.sum(np.logaddexp(0.0, eta) - y * eta))


def _select_alpha_g(train: list[dict], fit, loss, *, alphas=H.V2_ALPHAS,
                    no_inner: float = math.inf) -> float:
    """efv_v2_model._select_alpha's rule on an arbitrary head: nested forward-chained
    over the training years only, each inner year scored by fits on the years before
    it; a year counts when every penalty fits and scores; ties go to the larger
    penalty; no inner year returns `no_inner` (the head off)."""
    tot = {a: 0.0 for a in alphas}
    used = 0
    for yr in H.inner_years(train):
        tr = [r for r in train if r["decision_year"] < yr]
        te = [r for r in train if r["decision_year"] == yr]
        fits = {a: fit(tr, a) for a in alphas}
        if any(h is None for h in fits.values()):
            continue
        ls = {a: loss(h, te) for a, h in fits.items()}
        if any(v is None for v in ls.values()):
            continue
        for a in alphas:
            tot[a] += ls[a]
        used += 1
    if not used:
        return no_inner
    best = None
    for a in sorted(alphas, reverse=True):
        if best is None or tot[a] < tot[best]:
            best = a
    return best


def _assemble(base: dict, arm: str, *, skill: dict | None, timing: dict | None,
              weights: dict[str, dict], side: str, **extra) -> dict:
    """fit_v2's assembly step on the arm's heads: owner DS-Q2 for pitchers, a weight
    only on a usable head, consensus-only when neither head carries one."""
    why = None
    if side == "pit" and not H.head_usable(skill):
        timing = None
        why = ("owner DS-Q2: no pitcher skill driver passed the admission rule in this "
               "fold, so pitchers take the consensus order")
    w = weights[side]
    w_s = float(w["w_skill"]) if H.head_usable(skill) else 0.0
    w_t = float(w["w_time"]) if H.head_usable(timing) else 0.0
    if why is None and w_s <= 0 and w_t <= 0:
        why = "no usable head carries a positive registered weight"
    out = dict(base)
    out.update({"model_id": ARM_IDS[arm], "arm": arm, "base_model_id": base["model_id"],
                "skill": skill, "timing": timing, "w_skill": w_s, "w_time": w_t,
                "consensus_only": w_s <= 0 and w_t <= 0, "consensus_only_reason": why})
    out.update(extra)
    return out


def _predict(model: dict, rows: list[dict], *, u_c=None, w_s=None, w_t=None) -> list[dict]:
    """predict_v2's output on an arm's model: u_c (or the anchor), e_skill and e_time
    through the heads' designs, the order index, the DS-07 grade on the rows' own
    consensus values and the pricing line. Per-row weights (MC-3) replace the scalars.
    On a V2 model with no override this is predict_v2 bit for bit."""
    if not rows:
        return []
    groups = [int(r["decision_year"]) for r in rows]
    fv = np.array([r["fv"] for r in rows], dtype=np.float64)
    u = H.within_pct(fv, groups) if u_c is None else np.asarray(u_c, dtype=np.float64)
    ws = (np.full(len(rows), float(model["w_skill"])) if w_s is None
          else np.asarray(w_s, dtype=np.float64))
    wt = (np.full(len(rows), float(model["w_time"])) if w_t is None
          else np.asarray(w_t, dtype=np.float64))
    es = _e(model["skill"], rows) if ws.max() > 0 else np.zeros(len(rows))
    et = _e(model["timing"], rows) if wt.max() > 0 else np.zeros(len(rows))
    order = u + ws * es + wt * et
    grade = H.output_map(order, groups, fv)
    war = H.war_at(model["war_map"], grade)
    return [{"player_key": r["player_key"], "u_c": float(u[i]),
             "e_skill": float(es[i]), "e_time": float(et[i]),
             "order_idx": float(order[i]), "efv_grade": float(grade[i]),
             "efv_war": float(war[i])} for i, r in enumerate(rows)]


# ---------------------------------------------------------------------------
# MC-1: the pairwise (Bradley-Terry) residual skill head
# ---------------------------------------------------------------------------

def mc1_pairs(train: list[dict], side: str, *, weighting: str = "distance") -> dict:
    """The pair index over the has-block training rows: every (i, j) inside one
    (side, decision_year) group with u_y_i > u_y_j, u_y the target percentile within
    decision year over every row of the year. Weight "distance" is |u_y_i - u_y_j| (the
    arm); "listwise" divides it by the number of rows i beats in its group, so each
    winner contributes one unit over its list (the sensitivity). A row's side is its
    `side` field when it carries one, else `side`. Positions index the has-block list;
    `row_index` maps them back into `train`."""
    if weighting not in PAIR_WEIGHTINGS:
        raise ValueError(f"weighting must be one of {PAIR_WEIGHTINGS}, got {weighting!r}")
    rows = H.skill_training_rows(train)
    _u, u_y = H._percentiles(train)
    pos = {id(r): i for i, r in enumerate(train)}
    ix = np.array([pos[id(r)] for r in rows], dtype=np.int64)
    uy = u_y[ix] if ix.size else np.zeros(0)
    groups = [(str(r.get("side", side)), int(r["decision_year"])) for r in rows]
    by: dict = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    ii, jj, ww, gg = [], [], [], []
    n_by: dict[str, int] = {}
    for g in sorted(by):
        idx = np.asarray(by[g], dtype=np.int64)
        D = uy[idx][:, None] - uy[idx][None, :]
        a, b = np.nonzero(D > 0)
        w = D[a, b]
        if weighting == "listwise":
            wins = (D > 0).sum(axis=1)
            w = w / wins[a]
        ii.append(idx[a])
        jj.append(idx[b])
        ww.append(w)
        gg += [g] * int(a.size)
        n_by[f"{g[0]}:{g[1]}"] = int(a.size)
    cat = (lambda parts, dt: np.concatenate(parts).astype(dt) if parts
           else np.zeros(0, dtype=dt))
    i_arr, j_arr, w_arr = cat(ii, np.int64), cat(jj, np.int64), cat(ww, np.float64)
    return {"row_index": ix, "i": i_arr, "j": j_arr, "weight": w_arr, "group": gg,
            "n_rows": len(rows), "n_pairs": int(i_arr.size), "n_pairs_by_group": n_by,
            "weighting": weighting}


def _pairwise_fit(train: list[dict], keys, alpha: float, *, weighting: str,
                  side: str) -> dict | None:
    """The Bradley-Terry head on the pair index: a weighted logistic of 1 on the
    difference rows [u_c_i - u_c_j, z(x_i) - z(x_j)], b_uc free (a vanishing penalty, as
    _timing_fit gives its free terms), beta penalized by alpha; alpha infinite fits b_uc
    alone. The intercept cancels in a pair, so b0 is 0."""
    rows = H.skill_training_rows(train)
    if len(rows) < H.MIN_TEST_ROWS or not keys:
        return None
    pr = mc1_pairs(train, side, weighting=weighting)
    if pr["n_pairs"] == 0:
        return None
    u_c = _uc(train)[pr["row_index"]]
    means = H.has_block_means(train)
    mu, sd, Xs = H._std_cols(H._v2_x(rows, keys, means))
    S = np.column_stack([u_c, Xs])
    D = S[pr["i"]] - S[pr["j"]]
    w = pr["weight"]
    y = np.ones(D.shape[0])
    if math.isinf(alpha):
        coef = np.concatenate([_wlogistic(D[:, :1], y, w, np.array([H._OFFSET_EPS])),
                               np.zeros(len(keys))])
    else:
        pen = np.concatenate([[H._OFFSET_EPS], np.full(len(keys), float(alpha))])
        coef = _wlogistic(D, y, w, pen)
    return {"keys": list(keys), "means": means, "alpha": alpha, "mu": mu.tolist(),
            "sd": sd.tolist(), "b0": 0.0, "b_uc": float(coef[0]),
            "beta": [float(b) for b in coef[1:]], "n_train": len(rows),
            "n_pairs": pr["n_pairs"], "n_pairs_by_group": pr["n_pairs_by_group"],
            "pair_weighting": weighting, "loss": "bradley_terry",
            "trained_on": "has_block", "design": {"kind": "v2"}}


def _pair_loss(side: str, weighting: str):
    def loss(head: dict, te: list[dict]) -> float | None:
        pr = mc1_pairs(te, side, weighting=weighting)
        if pr["n_pairs"] == 0:
            return None
        te_hb = H.skill_training_rows(te)
        s = head["b_uc"] * _uc(te)[pr["row_index"]] + H._lin(head, _head_x(head, te_hb))
        d = s[pr["i"]] - s[pr["j"]]
        return float(np.sum(pr["weight"] * np.logaddexp(0.0, -d)))
    return loss


def fit_mc1_pairwise(train: list[dict], side: str, frame: str, weights: dict[str, dict],
                     *, pair_weighting: str = "distance", alpha: float | None = None,
                     alphas=H.V2_ALPHAS, absent_ok: bool | None = None) -> dict:
    """MC-1 on one fold's training rows: fit_v2, then its skill head refit as the
    pairwise head on the same admitted keys. With no admitted skill driver the arm is
    V2 itself. `alpha` fixes the penalty (tests); None selects it by the nested rule."""
    guard_training_rows(train, frame)
    if pair_weighting not in PAIR_WEIGHTINGS:
        raise ValueError(f"pair_weighting must be one of {PAIR_WEIGHTINGS}")
    base = H.fit_v2(train, side, frame=frame, weights=weights, absent_ok=absent_ok)
    v2_skill = base["skill"]
    if v2_skill is None:
        return _assemble(base, "mc1", skill=None, timing=base["timing"], weights=weights,
                         side=side, pair_weighting=pair_weighting,
                         note="no admitted skill driver in this fold: the arm is V2")
    keys = tuple(v2_skill["keys"])

    def fit(tr, a):
        return _pairwise_fit(tr, keys, a, weighting=pair_weighting, side=side)
    a = (_select_alpha_g(train, fit, _pair_loss(side, pair_weighting), alphas=alphas)
         if alpha is None else alpha)
    head = fit(train, a)
    if head is not None:
        head.update({"side": side, "admission": v2_skill["admission"],
                     "candidates": v2_skill["candidates"]})
        head["score_sd"] = _score_sd(head, H.skill_training_rows(train))
    return _assemble(base, "mc1", skill=head, timing=base["timing"], weights=weights,
                     side=side, pair_weighting=pair_weighting,
                     v2_skill_alpha=H._akey(v2_skill["alpha"]))


def predict_mc1(model: dict, rows: list[dict]) -> list[dict]:
    """The pairwise head is V2-shaped, so this is predict_v2."""
    return H.predict_v2(model, rows)


# ---------------------------------------------------------------------------
# MC-2: the reliability-weighted anchor
# ---------------------------------------------------------------------------

def _row_sources(by_v: dict, sources) -> list[str]:
    if sources is not None:
        return [s for s in sources if s != SB.CONSENSUS_KEY]
    seen: set[str] = set()
    for rows in by_v.values():
        for r in rows:
            seen |= set((r.get("grades") or {}).keys())
    seen.discard(SB.CONSENSUS_KEY)
    return sorted(seen)


def build_source_reliability(rows_by_side_vintage: dict[str, dict[int, list[dict]]], *,
                             single_source: dict, sources=None,
                             min_group_rows: int = H.MIN_TEST_ROWS,
                             target_vintages=None, gate_sha: str | None = None,
                             frame: str = "lv") -> dict:
    """The MC-2 reliability table keyed (source, side, V).

    `frame` names what the years are (guard_training_rows' distinction): on "lv" they
    are list vintages, so a reserved one (R-LV) raises through
    efv_vintage_frame.guard_score_request; on "vm" they are debut years of the
    vintage-matched frame (the screen's MC-2 design rule: career WAR on the debut
    frame), which the R-LV guard does not name, and the one guard is
    efv_v2_model._check_years (no year at or after the first reserved debut cohort).

    Rows are {side: {V: rows}}, each row carrying `grades` ({source: FV at the V
    read}) and `target` (the W3 the caller joined; read as ranks only). For every
    target V the table reads list vintages at most V - RELIABILITY_LAG and nothing
    later: per source, the size-weighted mean over those (side, V') groups of at least
    `min_group_rows` rows carrying the source of the Spearman of the source's own
    grade against the target, floored at source_backtest.SPEARMAN_FLOOR, divided by
    the mean over the sources with history, shrunk toward 1 with
    source_backtest.WEIGHT_SHRINK_K pseudo rows and clamped to
    source_backtest.WEIGHT_CLAMP (the shipped learned-weight rule). A source with no
    history at V keeps weight 1.0 (never punished for being new). `single_source` is
    {"k", "prior"}, consensus.SINGLE_SOURCE_K and SINGLE_SOURCE_PRIOR handed in by the
    runner (this module may not import consensus). The rule is fixed and not tuned."""
    if frame not in ("lv", "vm"):
        raise ValueError(f"frame must be lv or vm, got {frame!r}")
    k_ss = float(single_source["k"])
    prior = float(single_source["prior"])
    table: dict = {}
    reads: dict = {}
    stats_doc: dict = {}
    srcs_doc: dict = {}
    for side, by_v in rows_by_side_vintage.items():
        vintages = sorted(int(v) for v in by_v)
        H._check_years(vintages, gate_sha=gate_sha)
        for v in vintages:
            if frame == "lv":
                F.guard_score_request(v, gate_sha=gate_sha, purpose="reliability table")
        srcs = _row_sources(by_v, sources)
        srcs_doc[side] = srcs
        targets = (vintages if target_vintages is None
                   else sorted(int(v) for v in target_vintages))
        H._check_years(targets, gate_sha=gate_sha)
        table[side], reads[side], stats_doc[side] = {}, {}, {}
        for V in targets:
            if frame == "lv":
                F.guard_score_request(V, gate_sha=gate_sha, purpose="reliability table")
            hist = [v for v in vintages if v <= V - RELIABILITY_LAG]
            reads[side][str(V)] = hist
            stats = {}
            for s in srcs:
                tot, n, g = 0.0, 0, 0
                for v in hist:
                    rr = [r for r in by_v[v] if (r.get("grades") or {}).get(s) is not None
                          and r.get("target") is not None]
                    if len(rr) < int(min_group_rows):
                        continue
                    rho = SB._spearman([float(r["grades"][s]) for r in rr],
                                       [float(r["target"]) for r in rr])
                    if rho is None:
                        continue
                    tot += rho * len(rr)
                    n += len(rr)
                    g += 1
                stats[s] = {"rho": (tot / n) if n else None, "n": n, "groups": g}
            with_hist = [s for s in srcs if stats[s]["rho"] is not None]
            weights = {s: 1.0 for s in srcs}
            if with_hist:
                floored = {s: max(SB.SPEARMAN_FLOOR, stats[s]["rho"]) for s in with_hist}
                mean_rho = sum(floored.values()) / len(floored)
                for s in with_hist:
                    raw = floored[s] / mean_rho
                    n = stats[s]["n"]
                    shrunk = (n * raw + SB.WEIGHT_SHRINK_K * 1.0) / (n + SB.WEIGHT_SHRINK_K)
                    weights[s] = round(min(SB.WEIGHT_CLAMP[1],
                                           max(SB.WEIGHT_CLAMP[0], shrunk)), 4)
            table[side][str(V)] = weights
            stats_doc[side][str(V)] = stats
    return {"rule": ("per (source, side, V): within-(side, V') Spearman of the source's "
                     "own grade against the target over list vintages V' at most "
                     f"V - {RELIABILITY_LAG}, relative to the mean over sources with "
                     "history, shrunk toward equal and clamped; the single-source "
                     "rule unchanged; no indicator for a missing source"),
            "frame": frame,
            "lag": RELIABILITY_LAG, "shrink_k": SB.WEIGHT_SHRINK_K,
            "clamp": list(SB.WEIGHT_CLAMP), "rho_floor": SB.SPEARMAN_FLOOR,
            "min_group_rows": int(min_group_rows),
            "single_source": {"k": k_ss, "prior": prior,
                              "weight_on_source": 1.0 / (1.0 + k_ss)},
            "sources": srcs_doc, "table": table, "reads": reads, "stats": stats_doc,
            "indicator_columns": []}


def reliability_weight(reliability: dict, source: str, side: str, vintage: int) -> float:
    """The table's weight for (source, side, V); 1.0 for a source it does not list."""
    return float(reliability["table"][side][str(int(vintage))].get(source, 1.0))


def anchor_values(rows: list[dict], reliability: dict, side: str) -> tuple[np.ndarray, int]:
    """(u_c* per row, rows with no listed source). Inside each row's own (side, V):
    every source's grades over the rows that carry it are placed on their within
    percentile (efv_v2_model.within_pct), a one-source row's grade first shrunk toward
    the prior exactly as consensus.compute_consensus_point shrinks it (weight
    1 / (1 + k) on the source); u_c* is the reliability-weighted mean of the row's
    present sources' percentiles. A missing source contributes no weight and no column.
    A row with no listed source takes the consensus percentile (counted)."""
    table = reliability["table"][side]
    srcs = reliability["sources"][side]
    ss = reliability["single_source"]
    w_src = 1.0 / (1.0 + float(ss["k"]))
    prior = float(ss["prior"])
    years = [int(r["decision_year"]) for r in rows]
    num = np.zeros(len(rows))
    den = np.zeros(len(rows))
    by: dict = {}
    for i, y in enumerate(years):
        by.setdefault(y, []).append(i)
    for V, idx in by.items():
        w_V = table.get(str(V))
        if w_V is None:
            raise ValueError(f"no reliability weights for list vintage {V}")
        n_src = {i: sum(1 for s in srcs if (rows[i].get("grades") or {}).get(s) is not None)
                 for i in idx}
        for s in srcs:
            have = [i for i in idx if (rows[i].get("grades") or {}).get(s) is not None]
            if not have:
                continue
            vals = []
            for i in have:
                g = float(rows[i]["grades"][s])
                vals.append(w_src * g + (1.0 - w_src) * prior if n_src[i] == 1 else g)
            pct = H.within_pct(vals, [0] * len(have))
            w = float(w_V.get(s, 1.0))
            for j, i in enumerate(have):
                num[i] += w * pct[j]
                den[i] += w
    u_cons = H.within_pct([r["fv"] for r in rows], years)
    safe = np.where(den > 0, den, 1.0)
    return np.where(den > 0, num / safe, u_cons), int((den == 0).sum())


def attach_anchor(rows: list[dict], reliability: dict, side: str) -> tuple[list[dict], int]:
    """Rows as new dicts carrying u_c* under ANCHOR_KEY."""
    u, n_missing = anchor_values(rows, reliability, side)
    return [dict(r, **{ANCHOR_KEY: float(u[i])}) for i, r in enumerate(rows)], n_missing


def _admission_for_key_a(train: list[dict], key: str, *, target: str,
                         has_block_only: bool, min_rows: int = H.ADMIT_MIN_ROWS) -> dict:
    """efv_v2_model.admission_for_key with u_c read through _uc (the anchor)."""
    H._check_years({int(r["decision_year"]) for r in train})
    u_c = _uc(train)
    _u, u_y = H._percentiles(train)
    means = H.has_block_means(train)
    t_by = {}
    for yr in sorted({int(r["decision_year"]) for r in train}):
        ix = [i for i, r in enumerate(train) if int(r["decision_year"]) == yr
              and (r["v2"]["has_block"] or not has_block_only)]
        if not ix or sum(1 for i in ix if train[i]["v2"].get(key) is not None) < min_rows:
            t_by[yr] = None
            continue
        x = [H.v2_vector(train[i]["v2"], (key,), means)[0] for i in ix]
        y = (u_y[ix] if target == "u_y"
             else np.array([train[i]["reached"] for i in ix], dtype=np.float64))
        t_by[yr] = H.admission_t(u_c[ix], y, x, min_rows=min_rows)
    return H.admission_check(t_by)


def _admitted_keys_a(train, keys, *, target, has_block_only):
    checks = {k: _admission_for_key_a(train, k, target=target, has_block_only=has_block_only)
              for k in keys}
    return tuple(k for k in keys if checks[k]["admitted"]), checks


def fit_mc2_anchor(train: list[dict], side: str, frame: str, weights: dict[str, dict],
                   source_reliability: dict, *, alpha: float | None = None,
                   alphas=H.V2_ALPHAS, absent_ok: bool | None = None) -> dict:
    """MC-2 on one fold's training rows (each carrying `grades`): V2's heads, admission
    rule and weights, fitted with u_c* in place of u_c. fit_v2 is the base (its pricing
    line and fold receipt are kept); the comparator stays served consensus."""
    guard_training_rows(train, frame)
    rows, n_missing = attach_anchor(train, source_reliability, side)
    base = H.fit_v2(train, side, frame=frame, weights=weights, absent_ok=absent_ok)
    ob = frame == "lv"
    ab = ob and (H.absence_admitted(side) if absent_ok is None else bool(absent_ok))
    cands = _skill_cands(side)
    skill = None
    keys, checks = _admitted_keys_a(rows, cands, target="u_y", has_block_only=True)
    if keys:
        def fit_s(tr, a):
            return _skill_fit_g(tr, keys, a, _v2_design(keys))
        a_s = _select_alpha_g(rows, fit_s, _skill_loss, alphas=alphas) if alpha is None else alpha
        skill = fit_s(rows, a_s)
        if skill is not None:
            skill.update({"side": side, "admission": checks, "candidates": list(cands),
                          "anchor": True})
            skill["score_sd"] = _score_sd(skill, H.skill_training_rows(rows))
    timing = None
    if not (side == "pit" and not H.head_usable(skill)):
        tcands = H.timing_candidates(side, ids_outcome_blind=ob, absence_admitted=ab)
        tkeys, tchecks = _admitted_keys_a(rows, tcands, target="reached",
                                          has_block_only=False)

        def fit_t(tr, a):
            return _timing_fit_g(tr, tkeys, a, _v2_design(tkeys))
        a_t = (_select_alpha_g(rows, fit_t, _timing_loss, alphas=alphas)
               if alpha is None else alpha)
        timing = fit_t(rows, a_t)
        if timing is not None:
            timing.update({"side": side, "admission": tchecks, "candidates": list(tcands),
                           "ids_outcome_blind": bool(ob), "anchor": True})
            timing["score_sd"] = _score_sd(timing, rows)
    anchor = {"side": side, "lag": source_reliability["lag"],
              "sources": list(source_reliability["sources"][side]),
              "single_source": dict(source_reliability["single_source"]),
              "n_train_rows_without_source": n_missing,
              "indicator_columns": [],
              "comparator": "served consensus (u_c), unchanged",
              "reliability": source_reliability}
    return _assemble(base, "mc2", skill=skill, timing=timing, weights=weights, side=side,
                     anchor=anchor)


def predict_mc2(model: dict, rows: list[dict]) -> list[dict]:
    """predict_v2 with u_c* (from the rows' own grades and the model's table) as the
    anchor; the grade still comes from the rows' consensus values."""
    u, _n = anchor_values(rows, model["anchor"]["reliability"], model["anchor"]["side"])
    return _predict(model, rows, u_c=u)


# ---------------------------------------------------------------------------
# MC-3: the two-band weight
# ---------------------------------------------------------------------------

def band_of_row(r: dict) -> str:
    """"upper" for a row whose as-of MiLB block puts its last level at AA or above;
    "lower" for every other row, a no-block row included (never a third value). A
    label written under MC3_BAND_KEY (the screen's twin control) is read as given."""
    ov = r.get(MC3_BAND_KEY)
    if ov is not None:
        if ov not in MC3_BANDS:
            raise ValueError(f"{MC3_BAND_KEY} must be one of {MC3_BANDS}, got {ov!r}")
        return str(ov)
    v2 = r["v2"]
    lr = v2.get("level_rank")
    if v2.get("has_block") and lr is not None and float(lr) >= MC3_BAND_AA_RANK:
        return "upper"
    return "lower"


def _clip_share(x) -> float:
    x = float(x or 0.0)
    return 0.0 if x <= 0 else (H.W_MAX if x > H.W_MAX else x)


def band_weights(side: str, sources: dict[str, list[dict]], *,
                 last_year: int = H.RULE_LAST_YEAR, absent_ok: bool | None = None) -> dict:
    """The DS-08 combiner rule run per band on rule years at most RULE_LAST_YEAR: the
    sources' rows split by band_of_row, each band's rule as efv_v2_model.combiner_rule
    writes it, the weights clipped to [0, W_MAX]. `years_read` lists every year any
    band's rule read."""
    if int(last_year) > H.RULE_LAST_YEAR:
        raise ValueError(f"the rule reads no year after {H.RULE_LAST_YEAR}")
    out = {"side": side, "last_year": int(last_year), "boundary": MC3_BAND_AA_RANK,
           "bands": {}, "weights": {}, "n_rows": {}, "years_read": []}
    years: set[int] = set()
    for band in MC3_BANDS:
        src = {name: [r for r in rows if band_of_row(r) == band]
               for name, rows in sources.items()}
        rule = H.combiner_rule(side, src, last_year=last_year, absent_ok=absent_ok)
        out["bands"][band] = rule
        out["weights"][band] = {side: {"w_skill": _clip_share(rule["w_skill"]),
                                       "w_time": _clip_share(rule["w_time"])}}
        out["n_rows"][band] = {name: len(rows) for name, rows in src.items()}
        for rec in rule["sources"].values():
            years |= {int(y) for y in rec["years"]}
    out["years_read"] = sorted(years)
    return out


def fit_mc3_twoband(train: list[dict], side: str, frame: str,
                    weights_by_band: dict[str, dict[str, dict]], *,
                    absent_ok: bool | None = None) -> dict:
    """MC-3 on one fold's training rows: V2's heads (fit_v2), the combiner weights per
    band. `weights_by_band` is {band: fit_v2-shaped weights} from band_weights."""
    guard_training_rows(train, frame)
    for band in MC3_BANDS:
        if band not in weights_by_band:
            raise ValueError(f"weights_by_band lacks the {band} band")
    base = H.fit_v2(train, side, frame=frame, weights=weights_by_band["lower"],
                    absent_ok=absent_ok)
    model = _assemble(base, "mc3", skill=base["skill"], timing=base["timing"],
                      weights=weights_by_band["lower"], side=side)
    bw = {}
    for band in MC3_BANDS:
        w = weights_by_band[band][side]
        bw[band] = {"w_skill": _clip_share(w["w_skill"]) if H.head_usable(model["skill"]) else 0.0,
                    "w_time": _clip_share(w["w_time"]) if H.head_usable(model["timing"]) else 0.0}
    w_s = max(b["w_skill"] for b in bw.values())
    w_t = max(b["w_time"] for b in bw.values())
    model.update({"band_weights": bw, "band_boundary": MC3_BAND_AA_RANK,
                  "band_rule": ("last level at the read AA or above, with a block, is the "
                                "upper band; below, or no block, is the lower band"),
                  "n_train_by_band": {b: sum(1 for r in train if band_of_row(r) == b)
                                      for b in MC3_BANDS},
                  "w_skill": w_s, "w_time": w_t, "consensus_only": w_s <= 0 and w_t <= 0})
    if model["consensus_only"] and model["consensus_only_reason"] is None:
        model["consensus_only_reason"] = "no band carries a positive weight on a usable head"
    return model


def predict_mc3(model: dict, rows: list[dict]) -> list[dict]:
    bw = model["band_weights"]
    bands = [band_of_row(r) for r in rows]
    return _predict(model, rows, w_s=[bw[b]["w_skill"] for b in bands],
                    w_t=[bw[b]["w_time"] for b in bands])


# ---------------------------------------------------------------------------
# MC-4a: the sign-constrained ridge (active set)
# ---------------------------------------------------------------------------

def admitted_signs(head: dict | None) -> dict[str, int]:
    """{key: admitted sign} from the head's admission checks (the sign the DS-06 rule
    returned on the fold's training vintages); a key without one is absent."""
    out: dict[str, int] = {}
    if head is None:
        return out
    for k in head.get("keys", []):
        chk = (head.get("admission") or {}).get(k) or {}
        s = int(chk.get("sign") or 0)
        if s:
            out[k] = s
    return out


def _active_set(head: dict | None, refit, signs: dict[str, int]) -> tuple[dict | None, dict]:
    """Fit, zero every slope opposing its sign, refit on the rest, repeat. `refit(keys)`
    returns the head on those keys at the same penalty (None when none remain and the
    head cannot fit). Returns (head, {zeroed key: its sign and unconstrained slope})."""
    zeroed: dict = {}
    cur = head
    while cur is not None:
        bad = [(k, b) for k, b in zip(cur["keys"], cur["beta"]) if signs.get(k, 0) * b < 0]
        if not bad:
            break
        for k, b in bad:
            zeroed[k] = {"sign": signs[k], "slope_unconstrained": float(b)}
        keep = [k for k in cur["keys"] if k not in dict(bad)]
        cur = refit(keep)
    return cur, zeroed


def _constrain_v2_head(train: list[dict], head: dict | None, kind: str) -> tuple[dict | None, dict]:
    """MC-4a on one V2 head: the refits use efv_v2_model's own fits at the head's
    penalty, so a head with no opposing slope is returned unchanged."""
    if head is None:
        return None, {}
    signs = admitted_signs(head)
    alpha = head["alpha"]

    def refit(keys):
        new = (H._skill_fit(train, tuple(keys), alpha) if kind == "skill"
               else H._timing_fit(train, tuple(keys), alpha))
        if new is None:
            return None
        new.update({k: head[k] for k in ("side", "admission", "candidates",
                                         "ids_outcome_blind") if k in head})
        rows = H.skill_training_rows(train) if kind == "skill" else train
        new["score_sd"] = _score_sd(new, rows)
        return new
    out, zeroed = _active_set(head, refit, signs)
    if out is not None:
        out = dict(out, signs=signs, constrained_zero=zeroed)
    return out, zeroed


def fit_mc4a_signed(train: list[dict], side: str, frame: str, weights: dict[str, dict],
                    *, absent_ok: bool | None = None) -> dict:
    """MC-4a on one fold's training rows: fit_v2, then each head's admitted slopes
    constrained to their admitted signs by the active-set rule. On the vm frame the
    sign is the one admission_check returns at fit time (the assembly stores none)."""
    guard_training_rows(train, frame)
    base = H.fit_v2(train, side, frame=frame, weights=weights, absent_ok=absent_ok)
    skill, zs = _constrain_v2_head(train, base["skill"], "skill")
    timing, zt = _constrain_v2_head(train, base["timing"], "timing")
    return _assemble(base, "mc4a", skill=skill, timing=timing, weights=weights, side=side,
                     constrained_zero={"skill": zs, "timing": zt},
                     sign_source=("admission_check on the fold's training vintages, "
                                  "at fit time"))


def predict_mc4a(model: dict, rows: list[dict]) -> list[dict]:
    """The constrained heads are V2-shaped, so this is predict_v2."""
    return H.predict_v2(model, rows)


# ---------------------------------------------------------------------------
# MC-4b: the monotone I-spline residual
# ---------------------------------------------------------------------------

def _spline_head(train: list[dict], v2_head: dict | None, kind: str, *,
                 alpha: float | None, alphas) -> tuple[dict | None, dict]:
    """One head of MC-4b: the V2 head's admitted drivers through the I-spline design
    in their admitted directions, the penalty by the nested rule, the basis
    coefficients constrained non-negative by the active-set rule."""
    if v2_head is None or not v2_head["keys"]:
        return v2_head, {}
    drivers = tuple(v2_head["keys"])
    signs = admitted_signs(v2_head)
    fit_g = _skill_fit_g if kind == "skill" else _timing_fit_g
    loss = _skill_loss if kind == "skill" else _timing_loss
    rows = H.skill_training_rows(train) if kind == "skill" else train

    def fit(tr, a):
        return fit_g(tr, drivers, a, _ispline_design(drivers, signs))
    a = _select_alpha_g(train, fit, loss, alphas=alphas) if alpha is None else alpha
    head = fit(train, a)
    if head is None:
        return None, {}
    knots = head["design"]["knots"]

    def refit(cols):
        if not cols and kind == "skill":
            return None
        return fit_g(train, drivers, a, _ispline_design(drivers, signs, knots, cols))
    head, zeroed = _active_set(head, refit, {c: 1 for c in head["keys"]})
    if head is None:
        return None, zeroed
    head.update({k: v2_head[k] for k in ("side", "admission", "candidates",
                                         "ids_outcome_blind") if k in v2_head})
    head.update({"drivers": list(drivers), "signs": signs, "constrained_zero": zeroed,
                 "score_sd": _score_sd(head, rows)})
    return head, zeroed


def fit_mc4b_spline(train: list[dict], side: str, frame: str, weights: dict[str, dict],
                    *, alpha: float | None = None, alphas=H.V2_ALPHAS,
                    absent_ok: bool | None = None) -> dict:
    """MC-4b on one fold's training rows, or MC-4a (flagged `fell_back`) when the fold
    has fewer than MC4B_MIN_HAS_BLOCK_ROWS has-block training rows."""
    guard_training_rows(train, frame)
    n_hb = len(H.skill_training_rows(train))
    if n_hb < MC4B_MIN_HAS_BLOCK_ROWS:
        m = fit_mc4a_signed(train, side, frame, weights, absent_ok=absent_ok)
        m.update({"model_id": ARM_IDS["mc4b"], "arm": "mc4b", "fell_back": True,
                  "fallback": "mc4a",
                  "fallback_reason": (f"{n_hb} has-block training rows, under "
                                      f"{MC4B_MIN_HAS_BLOCK_ROWS}")})
        return m
    base = H.fit_v2(train, side, frame=frame, weights=weights, absent_ok=absent_ok)
    skill, zs = _spline_head(train, base["skill"], "skill", alpha=alpha, alphas=alphas)
    timing, zt = _spline_head(train, base["timing"], "timing", alpha=alpha, alphas=alphas)
    return _assemble(base, "mc4b", skill=skill, timing=timing, weights=weights, side=side,
                     fell_back=False, constrained_zero={"skill": zs, "timing": zt},
                     n_has_block_train=n_hb)


def predict_mc4b(model: dict, rows: list[dict]) -> list[dict]:
    return _predict(model, rows)


# ---------------------------------------------------------------------------
# MC-5: the pricing line with position family and age (outside the family)
# ---------------------------------------------------------------------------

def position_family(position, side: str) -> str:
    """The MC-5 family of a listed position at the read. Pitchers: "rp" for a relief
    role, else "sp"."""
    p = str(position or "").strip().upper()
    if side == "pit":
        return "rp" if any(tok in p for tok in MC5_RP_TOKENS) else "sp"
    return MC5_POSITIONS.get(p, "other")


def fit_mc5_pricing(train: list[dict], position_family, age_at_read, *,
                    side: str | None = None) -> dict | None:
    """fit_war_map's line with continuous covariates: weighted least squares of the
    training target on [1, consensus FV, family dummies, age at read]. Families are the
    per-row labels given (None reads as the reference family); the reference is the
    side's first family when present, else the first label in sorted order; a dummy
    constant on the rows is left out. Age is imputed at the observed training mean
    with no indicator and left out when unobserved or constant. A line in the grade
    with additive shifts, never a table by grade. None when the rows cannot support it."""
    H._check_years({int(r["decision_year"]) for r in train})
    fams_in = list(position_family)
    ages_in = list(age_at_read)
    if len(fams_in) != len(train) or len(ages_in) != len(train):
        raise ValueError("position_family and age_at_read must align with train")
    if len(train) < H.MIN_TEST_ROWS:
        return None
    fv = np.array([r["fv"] for r in train], dtype=np.float64)
    if float(fv.std()) <= 0:
        return None
    labels = sorted({str(f) for f in fams_in if f is not None})
    pref = MC5_FAMILIES.get(side or "", ())
    ref = pref[0] if pref and pref[0] in labels else (labels[0] if labels else "other")
    fams = [ref if f is None else str(f) for f in fams_in]
    labels = sorted(set(fams))
    y = np.array([r["target"] for r in train], dtype=np.float64)
    w = _weights_of(train)
    cols, names = [np.ones(fv.size), fv], ["intercept", "fv"]
    for f in labels:
        if f == ref:
            continue
        d = np.array([1.0 if g == f else 0.0 for g in fams])
        if float(d.std()) > 0:
            cols.append(d)
            names.append(f"family:{f}")
    ages = np.array([np.nan if a is None else float(a) for a in ages_in], dtype=np.float64)
    obs = ~np.isnan(ages)
    age_mean = float(ages[obs].mean()) if obs.any() else None
    age_used = False
    if age_mean is not None:
        a_imp = np.where(obs, ages, age_mean)
        if float(a_imp.std()) > 0:
            cols.append(a_imp)
            names.append("age_at_read")
            age_used = True
    Z = np.column_stack(cols)
    b = H._wls(Z, y, w, np.zeros(len(names)))
    coef = {n: float(v) for n, v in zip(names, b)}
    return {"model_id": ARM_IDS["mc5"], "a": coef["intercept"], "b": coef["fv"],
            "family": {n.split(":", 1)[1]: v for n, v in coef.items()
                       if n.startswith("family:")},
            "reference_family": ref, "families": labels,
            "age": coef.get("age_at_read", 0.0), "age_used": age_used,
            "age_mean": age_mean, "age_observed": int(obs.sum()),
            "n": int(fv.size), "columns": names, "role": "pricing, no rank claim"}


def attach_mc5(model: dict, pricing: dict | None) -> dict:
    """The V2 (or arm) model with the MC-5 line beside its own war_map. The order index
    is untouched: only predict_mc5 reads the line."""
    return dict(model, pricing_mc5=pricing)


def mc5_war(pricing: dict | None, grade, position_family, age_at_read) -> np.ndarray:
    g = np.asarray(grade, dtype=np.float64)
    if pricing is None:
        return np.full(g.shape, np.nan)
    fams = [pricing["reference_family"] if f is None else str(f) for f in position_family]
    shift = np.array([pricing["family"].get(f, 0.0) for f in fams], dtype=np.float64)
    war = pricing["a"] + pricing["b"] * g + shift
    if pricing["age_used"]:
        ages = np.array([np.nan if a is None else float(a) for a in age_at_read],
                        dtype=np.float64)
        ages = np.where(np.isnan(ages), pricing["age_mean"], ages)
        war = war + pricing["age"] * ages
    return war


def predict_mc5(model: dict, rows: list[dict], position_family, age_at_read) -> list[dict]:
    """predict_v2's rows with efv_war from the MC-5 line at the same grade; u_c,
    e_skill, e_time, order_idx and efv_grade are predict_v2's own values, and the V2
    price is kept as efv_war_v2."""
    out = H.predict_v2(model, rows)
    if not out:
        return out
    fams, ages = list(position_family), list(age_at_read)
    if len(fams) != len(rows) or len(ages) != len(rows):
        raise ValueError("position_family and age_at_read must align with rows")
    war = mc5_war(model.get("pricing_mc5"), [o["efv_grade"] for o in out], fams, ages)
    return [dict(o, efv_war_v2=o["efv_war"], efv_war=float(war[i]))
            for i, o in enumerate(out)]
