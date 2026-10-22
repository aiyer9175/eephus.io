# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV driver weight integrity (EFV_WEIGHT_INTEGRITY, owner decision EW3-49, 2026-10-22).

docs/efv-v2/EFV_WEIGHT_INTEGRITY.md, registered alone before this module existed. On the
served eFV v5 COMBINED heads (the re-fit's variant RT) and the re-fit's development frames,
once:

  A  how sure the served weights are: cluster-bootstrap intervals of every served slope and
     head weight (player and club clusters), leave-one-cohort-out signs, effective degrees
     of freedom, planted recovery (descriptive, adopts nothing);
  B  simpler heads in every fold: B1 unit weights on sign-stable keys with one fitted scale,
     B2 ridge on an extended penalty grid, B3 sparse top-k stable keys;
  C  the live board against the training rows per driver (SMD, KS, drop-one classifier
     AUC) and, for drivers that carry the shift, a level x season re-standardization;
  D  the skill head refitted with a within-year pairwise logistic rank loss;

each candidate read against the served heads (S), consensus alone (K) and a planted signal
through the same pipeline (P), with Holm across the adoption tests. The read never serves:
EFV_WEIGHT_INTEGRITY_ON stays False.

RESERVED FRAMES. Only the re-fit's cached development frames are read (lv_dev list vintages
2017 to 2019, vm_dev debut cohorts 2017 to 2023); the cache's builders raised on the reserved
vintages and stopped before the 2025 cohort.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group percentile;
the groups are side, frame, year, fold, level band, read season and club. Nothing here groups,
counts or averages rows by consensus-FV level; test_efv_weight_integrity.py scans this source.

    python efv_weight_integrity.py --run --cache <re-fit cache> --work <scratch dir>
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
import zlib
from pathlib import Path

import numpy as np

import efv5_combined as V5C
import efv5_refit as RF
import efv_v2_candidates as C
import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "efv_weight_integrity.json"
WEIGHTS_PATH = DATA_DIR / "efv_weight_integrity_weights.json"
DOC = "docs/efv-v2/EFV_WEIGHT_INTEGRITY.md"
RESULTS_DOC = "docs/efv-v2/EFV_WEIGHT_INTEGRITY_RESULTS.md"
TOOL = "efv_weight_integrity.py"
ITEM = "EFV_WEIGHT_INTEGRITY"

#: Section 9: an adopted head serves only when the owner flips this (False: byte identical).
EFV_WEIGHT_INTEGRITY_ON = False

#: Registered constants (sections 2 to 8).
SEED = 20261022
B = 4000
MARGIN = 0.005
HOLM_ALPHA = 0.05
CONFIG = "RT"
LIVE_DAY = "2026-10-16"
CARRY_DROP = 0.01
CARRY_SMD = 0.25
MIN_GROUP_VALUES = 20
CV_FOLDS = 5
SHIFT_PEN = 1.0
GRID_B2: tuple[float, ...] = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0,
                              30000.0, 100000.0, math.inf)
K_GRID: tuple = (1, 2, 3, 5, 8, None)
TOPK_PEN = 1.0
GRID_D: tuple[float, ...] = (0.0001, 0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, math.inf)
ARMS: tuple[str, ...] = ("B1", "B2", "B3", "C", "D")
#: Section 8.5: the order in which an adopting arm takes a side.
ADOPT_ORDER: tuple[str, ...] = ("B1", "B3", "B2", "C", "D")
STRUCTURAL_ZERO_PREFIXES: tuple[str, ...] = ("scr_g5_", "scr_t5_")
SIDES = F.SIDES

_LOG = print


def _tools():
    return RF._tools()


def _rnd(v, n: int = 5):
    if v is None:
        return None
    try:
        if not math.isfinite(float(v)):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(v), n)


# ---------------------------------------------------------------------------
# the cache and the fold contexts (section 1)
# ---------------------------------------------------------------------------

def load_cache(cache_dir: Path) -> tuple[dict, list[dict], dict]:
    """(build1, RT fold packs, phase0) of the re-fit's run."""
    cache_dir = Path(cache_dir)
    _tools()
    with (cache_dir / "build1.pkl").open("rb") as fh:
        b1 = pickle.load(fh)
    with (cache_dir / "packs_RT.pkl").open("rb") as fh:
        packs, _rec = pickle.load(fh)
    with (cache_dir / "phase0.pkl").open("rb") as fh:
        p0 = pickle.load(fh)
    return b1, packs, p0


def contexts(b1: dict, packs: list[dict]) -> list[dict]:
    """Every development fold of both sides with its rows as RT built them: the skill
    training rows (vm_dev: twins of earlier decision years added), the test rows, both RT
    rank-transformed, the cached fold model and pack."""
    BT, _B4 = _tools()
    inp = b1["inp"]
    by_id = {p["fold_id"]: p for p in packs}
    out = []
    for fid in BT.FRAMES_DEV:
        kind = BT.FRAME_KIND[fid]
        for side in SIDES:
            cols = (inp.cols.get(fid) or {}).get(side) or {}
            for fold, blk in inp.frames[fid]["by_side"][side].items():
                Y = int(fold)
                fold_id = f"{fid}|{side}|{Y}"
                p = by_id[fold_id]
                te = V5C.attach(blk["test"], side, cols, "test")
                if [r["player_key"] for r in te] != list(p["keys"]):
                    raise RuntimeError(f"{fold_id}: the test rows differ from the cached pack")
                tr = V5C.attach(blk["train"], side, cols, "train")
                if fid == "vm_dev":
                    tr = tr + [t for t in b1["twins"][side] if int(t["decision_year"]) < Y]
                out.append({"fold_id": fold_id, "fid": fid, "side": side, "fold": Y,
                            "kind": kind, "tr": tr, "te": te,
                            "tr_x": RF.rank_transform(tr, side),
                            "te_x": RF.rank_transform(te, side),
                            "scored": blk["scored"], "model": p["model"], "pack": p})
    return out


def production_context(b1: dict, side: str) -> dict:
    tr = list(b1["prod"][side]) + list(b1["twins"][side])
    return {"fold_id": f"production|{side}", "fid": "production", "side": side, "fold": None,
            "kind": "vm", "tr": tr, "tr_x": RF.rank_transform(tr, side)}


def served_models() -> dict:
    """The stored served production fit (RT) of both sides."""
    doc = json.loads(RF.WEIGHTS_PATH.read_text(encoding="utf-8"))
    return {s: RF.model_in(m) for s, m in doc["models_by_candidate"][CONFIG].items()}


def cand_names(side: str) -> list[str]:
    """RT's skill candidate columns of the side (the dark list dropped)."""
    return RF.refit_candidates(side, "skill", dark=True)


def key_to_name(side: str) -> dict:
    cands = V5C.candidates()
    return {cands[n]["key"]: n for n in V5C.side_candidates(side)}


def key_sign(key: str, side: str) -> int:
    n = key_to_name(side).get(key)
    return 0 if n is None else int(V5C.candidates()[n]["sign"])


# ---------------------------------------------------------------------------
# designs and the ridge solver (multiplicity weights for the bootstrap)
# ---------------------------------------------------------------------------

def design_of(train_x: list[dict], keys: list[str]) -> dict | None:
    """joint_skill's design on the has-block rows: Z = [1, u_c, z(keys)], u_y, w."""
    rows = H.skill_training_rows(train_x)
    if len(rows) < H.MIN_TEST_ROWS or not keys:
        return None
    means = H.has_block_means(train_x)
    X = H._v2_x(rows, list(keys), means)
    mu, sd, Xs = H._std_cols(X)
    u_c = C._uc(train_x)
    _u, u_y = H._percentiles(train_x)
    pos = {id(r): i for i, r in enumerate(train_x)}
    ix = np.asarray([pos[id(r)] for r in rows], dtype=int)
    w = C._weights_of(rows)
    Z = np.column_stack([np.ones(len(rows)), u_c[ix], Xs])
    return {"keys": list(keys), "means": means, "mu": mu, "sd": sd, "Z": Z, "u_y": u_y[ix],
            "u_c": u_c[ix], "w": w, "rows": rows, "ix": ix, "X": X}


def solve(Z: np.ndarray, y: np.ndarray, w: np.ndarray, pen: np.ndarray, lb: np.ndarray,
          ub: np.ndarray) -> np.ndarray:
    """The ridge WLS: H._wls when nothing is bounded (V2's own solver), else the bounded
    solver of efv5_combined."""
    if np.all(np.isneginf(lb)) and np.all(np.isposinf(ub)):
        return H._wls(Z, y, w, pen)
    return V5C.bounded_wls(Z, y, w, pen, lb, ub)


def head_from(Dz: dict, coef: np.ndarray, **meta) -> dict:
    h = {"keys": list(Dz["keys"]), "means": Dz["means"], "mu": [float(v) for v in Dz["mu"]],
         "sd": [float(v) for v in Dz["sd"]], "b0": float(coef[0]), "b_uc": float(coef[1]),
         "beta": [float(b) for b in coef[2:]], "n_train": int(len(Dz["rows"])),
         "trained_on": "has_block", "design": {"kind": "v2"}}
    h.update(meta)
    return h


def pen_bounds(keys: list[str], side: str, *, v2_pen, cand_pen, signs: dict | None = None
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Penalties and bounds over [1, u_c, keys]: a V2 key at v2_pen (fixed at 0 when it is
    None or infinite), a candidate at cand_pen bounded by its atlas sign; `signs`
    ({key: +1 or -1}) bounds every key at that sign instead."""
    k2n = key_to_name(side)
    pen, lb, ub = [0.0, 0.0], [-np.inf, -np.inf], [np.inf, np.inf]
    for k in keys:
        if signs is not None:
            s = int(signs[k])
            pen.append(float(cand_pen))
            lb.append(0.0 if s > 0 else -np.inf)
            ub.append(0.0 if s < 0 else np.inf)
        elif k in k2n:
            s = int(V5C.candidates()[k2n[k]]["sign"])
            pen.append(float(cand_pen))
            lb.append(0.0 if s > 0 else -np.inf)
            ub.append(0.0 if s < 0 else np.inf)
        else:
            fixed = v2_pen is None or math.isinf(float(v2_pen))
            pen.append(0.0 if fixed else float(v2_pen))
            lb.append(0.0 if fixed else -np.inf)
            ub.append(0.0 if fixed else np.inf)
    return np.asarray(pen), np.asarray(lb), np.asarray(ub)


def served_pens(head: dict, side: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lam = head.get("lam")
    lam = math.inf if lam is None else float(lam)
    return pen_bounds(head["keys"], side, v2_pen=head.get("alpha"),
                      cand_pen=(0.0 if math.isinf(lam) else lam))


def edf(Z: np.ndarray, w: np.ndarray, pen: np.ndarray, lb: np.ndarray, ub: np.ndarray,
        coef: np.ndarray) -> dict:
    """Section 4 A4: the ridge hat-matrix trace over the free coefficients (not fixed and
    not held at a bound), and that minus the intercept and the consensus slope."""
    free = ~((lb == 0) & (ub == 0))
    at_bound = ((coef == 0.0) & ((lb == 0) | (ub == 0)))
    free &= ~at_bound
    free[:2] = True
    Zf = Z[:, free]
    A = (Zf * w[:, None]).T @ Zf
    tr = float(np.trace(np.linalg.solve(A + np.diag(pen[free]), A)))
    return {"edf": round(tr, 3), "edf_drivers": round(tr - 2.0, 3),
            "free_slopes": int(free.sum() - 2), "slopes": int(Z.shape[1] - 2)}


# ---------------------------------------------------------------------------
# the served skill procedure (efv5_refit.fit_heads' skill branch) and its pieces
# ---------------------------------------------------------------------------

def v2_admitted(train_x: list[dict], side: str, kind: str) -> tuple[list[str], float | None]:
    """The V2 keys the served procedure admits on these rows and their alpha."""
    import efv_v3 as V3
    cfg = V3.base_config()
    ob = kind == "lv"
    ab = ob and H.absence_admitted(side)
    s_cands = V3.head_candidates(cfg, side, "skill", ids_outcome_blind=ob, absence_admitted=ab)
    if not s_cands:
        return [], None
    keys, _checks = C._admitted_keys_a(train_x, s_cands, target="u_y", has_block_only=True)
    if not keys:
        return [], None

    def fit_s(tr, a):
        return C._skill_fit_g(tr, keys, a, C._v2_design(keys))
    return list(keys), C._select_alpha_g(train_x, fit_s, C._skill_loss)


def served_skill(train_x: list[dict], side: str, kind: str) -> dict | None:
    """The served skill head on these (RT-transformed) rows: V2 admission and alpha, the
    candidate lambda by nested CV, the joint ridge."""
    names = cand_names(side)
    v2_keys, alpha = v2_admitted(train_x, side, kind)
    lam = V5C.select_lambda(train_x, "skill", v2_keys, alpha, names)
    head = V5C.joint_skill(train_x, v2_keys, alpha, names, lam)
    if head is not None:
        head["v2_keys"] = list(v2_keys)
    return head


def fold_penalties(model: dict) -> tuple[list[str], float | None, float]:
    """(V2 keys, alpha, lambda) of a cached fold model's skill head."""
    head = (model or {}).get("skill") or {}
    lam = ((model or {}).get("config") or {}).get("lam", {}).get("skill")
    lam = head.get("lam", lam)
    lam = math.inf if lam is None else float(lam)
    return list(head.get("v2_keys") or []), head.get("alpha"), lam


def slopes_of(head: dict | None) -> dict:
    if not head:
        return {}
    return {k: float(b) for k, b in zip(head.get("keys") or [], head.get("beta") or [])}


def loco_slopes(train_x: list[dict], side: str, v2_keys, alpha, lam) -> dict:
    """{decision year: {key: slope}}: the joint head refitted at fixed penalties with each
    decision year of the rows left out (twins carry their row's year)."""
    names = cand_names(side)
    out = {}
    for y in sorted({int(r["decision_year"]) for r in H.skill_training_rows(train_x)}):
        sub = [r for r in train_x if int(r["decision_year"]) != y]
        h = V5C.joint_skill(sub, v2_keys, alpha, names, lam)
        out[y] = slopes_of(h)
    return out


def stability(loco: dict, universe: list[str]) -> dict:
    """{key: {"stable", "sign", "score", "slopes"}} from left-out-year slopes."""
    out = {}
    for k in universe:
        s = np.asarray([float(v.get(k, 0.0)) for v in loco.values()], dtype=np.float64)
        stable = bool(s.size >= 2 and np.all(s != 0.0) and (np.all(s > 0) or np.all(s < 0)))
        sd = float(s.std(ddof=1)) if s.size >= 2 else 0.0
        score = abs(float(s.mean())) / sd if (stable and sd > 0) else (math.inf if stable else 0.0)
        out[k] = {"stable": stable, "sign": (1 if s.mean() > 0 else -1) if stable else 0,
                  "score": score, "n": int(s.size)}
    return out


def universe_of(side: str, v2_keys) -> list[str]:
    cands = V5C.candidates()
    return list(v2_keys) + [cands[n]["key"] for n in cand_names(side)]


def ranked(stab: dict) -> list[str]:
    st = [k for k, v in stab.items() if v["stable"]]
    return sorted(st, key=lambda k: (-stab[k]["score"], k))


# ---------------------------------------------------------------------------
# arm B: the simpler heads
# ---------------------------------------------------------------------------

def unit_head(train_x: list[dict], keys: list[str], signs: dict) -> dict | None:
    """B1: U = sum sign_k z_k over the keys, one scale c >= 0 by WLS u_y ~ 1 + u_c + c U."""
    if not keys:
        return None
    Dz = design_of(train_x, keys)
    if Dz is None:
        return None
    sv = np.asarray([float(signs[k]) for k in keys])
    U = Dz["Z"][:, 2:] @ sv
    Z1 = np.column_stack([Dz["Z"][:, :2], U])
    coef = V5C.bounded_wls(Z1, Dz["u_y"], Dz["w"], np.zeros(3), np.asarray([-np.inf, -np.inf, 0.0]),
                           np.asarray([np.inf, np.inf, np.inf]))
    full = np.concatenate([coef[:2], coef[2] * sv])
    return head_from(Dz, full, kind="unit", scale=float(coef[2]), signs={k: int(signs[k]) for k in keys})


def topk_head(train_x: list[dict], keys: list[str], signs: dict) -> dict | None:
    """B3's head on the given keys: each bounded at its stable sign, penalty TOPK_PEN."""
    if not keys:
        return None
    Dz = design_of(train_x, keys)
    if Dz is None:
        return None
    pen = np.concatenate([[0.0, 0.0], np.full(len(keys), TOPK_PEN)])
    lb = np.asarray([-np.inf, -np.inf] + [0.0 if signs[k] > 0 else -np.inf for k in keys])
    ub = np.asarray([np.inf, np.inf] + [0.0 if signs[k] < 0 else np.inf for k in keys])
    coef = V5C.bounded_wls(Dz["Z"], Dz["u_y"], Dz["w"], pen, lb, ub)
    return head_from(Dz, coef, kind="topk", signs={k: int(signs[k]) for k in keys})


def _k_keys(rank: list[str], k) -> list[str]:
    return list(rank) if k is None else list(rank[:int(k)])


def select_k(train_x: list[dict], side: str, v2_keys, alpha, lam) -> tuple:
    """B3's k by nested forward-chained CV over the rows' inner years, the ranking re-derived
    on each inner training set; ties go to the smaller k. Returns (k, losses)."""
    uni = universe_of(side, v2_keys)
    tot = {str(k): 0.0 for k in K_GRID}
    used = 0
    for yr in H.inner_years(train_x):
        tr = [r for r in train_x if int(r["decision_year"]) < yr]
        te = [r for r in train_x if int(r["decision_year"]) == yr]
        stab = stability(loco_slopes(tr, side, v2_keys, alpha, lam), uni)
        rank = ranked(stab)
        ls = {}
        for k in K_GRID:
            keys = _k_keys(rank, k)
            h = topk_head(tr, keys, {q: stab[q]["sign"] for q in keys}) if keys else None
            if h is None:
                h = consensus_head(tr)
            if h is None:
                ls = None
                break
            v = C._skill_loss(h, te)
            if v is None:
                ls = None
                break
            ls[str(k)] = v
        if ls is None:
            continue
        for k in ls:
            tot[k] += ls[k]
        used += 1
    if not used:
        return None, {"inner_years_used": 0}
    best = None
    for k in K_GRID:
        if best is None or tot[str(k)] < tot[str(best)] - 1e-15:
            best = k
    return best, {"inner_years_used": used, "loss": {k: _rnd(v, 6) for k, v in tot.items()}}


def consensus_head(train_x: list[dict]) -> dict | None:
    """u_y ~ 1 + u_c on the has-block rows, no driver (unusable: e_skill 0)."""
    rows = H.skill_training_rows(train_x)
    if len(rows) < H.MIN_TEST_ROWS:
        return None
    u_c = C._uc(train_x)
    _u, u_y = H._percentiles(train_x)
    pos = {id(r): i for i, r in enumerate(train_x)}
    ix = [pos[id(r)] for r in rows]
    c2 = H._wls(np.column_stack([np.ones(len(rows)), u_c[ix]]), u_y[ix], C._weights_of(rows),
                np.zeros(2))
    return {"keys": [], "means": H.has_block_means(train_x), "mu": [], "sd": [], "b0": float(c2[0]),
            "b_uc": float(c2[1]), "beta": [], "n_train": len(rows), "trained_on": "has_block",
            "design": {"kind": "v2"}}


def ridge_head(train_x: list[dict], side: str, v2_keys) -> tuple[dict | None, float]:
    """B2: one common penalty on every slope by nested CV on GRID_B2."""
    names = cand_names(side)

    def fit(tr, a):
        return V5C.joint_skill(tr, v2_keys, a, names, a)
    lam = C._select_alpha_g(train_x, fit, C._skill_loss, alphas=GRID_B2)
    return fit(train_x, lam), lam


# ---------------------------------------------------------------------------
# arm D: the within-year pairwise logistic rank loss
# ---------------------------------------------------------------------------

def _sigmoid(x):
    return 0.5 * (1.0 + np.tanh(0.5 * x))


def pair_index(y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(hi, lo): every within-group pair with unequal labels, oriented high to low."""
    hi_all, lo_all = [], []
    for g in np.unique(groups):
        ix = np.flatnonzero(groups == g)
        if ix.size < 2:
            continue
        a, b = np.triu_indices(ix.size, 1)
        i, j = ix[a], ix[b]
        d = y[i] - y[j]
        keep = d != 0
        i, j, d = i[keep], j[keep], d[keep]
        hi_all.append(np.where(d > 0, i, j))
        lo_all.append(np.where(d > 0, j, i))
    if not hi_all:
        return np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    return np.concatenate(hi_all), np.concatenate(lo_all)


def pair_matrix(Fm: np.ndarray, y: np.ndarray, w: np.ndarray, groups: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(D, pair weights, hi, lo): every within-group pair with unequal labels, oriented
    high minus low, weights w_i w_j normalized to sum 1."""
    hi, lo = pair_index(y, groups)
    if not hi.size:
        return np.zeros((0, Fm.shape[1])), np.zeros(0), hi, lo
    pw = w[hi] * w[lo]
    t = pw.sum()
    return Fm[hi] - Fm[lo], (pw / t if t > 0 else pw), hi, lo


def pair_data(train_x: list[dict], keys: list[str], *, head: dict | None = None) -> dict | None:
    """The pairwise design on the has-block rows: F = [u_c, z(keys)] at the rows' own
    standardization (or a fitted head's, for scoring)."""
    rows = H.skill_training_rows(train_x)
    if len(rows) < H.MIN_TEST_ROWS:
        return None
    means = head["means"] if head else H.has_block_means(train_x)
    X = H._v2_x(rows, list(keys), means)
    if head:
        mu, sd = np.asarray(head["mu"]), np.asarray(head["sd"])
        Xs = (X - mu) / sd if X.shape[1] else X
    else:
        mu, sd, Xs = H._std_cols(X)
    u_c = C._uc(train_x)
    pos = {id(r): i for i, r in enumerate(train_x)}
    ix = np.asarray([pos[id(r)] for r in rows], dtype=int)
    y = np.asarray([float(r["target"]) for r in rows])
    w = C._weights_of(rows)
    g = np.asarray([int(r["decision_year"]) for r in rows])
    Fm = np.column_stack([u_c[ix], Xs]) if X.shape[1] else u_c[ix][:, None]
    D, pw, hi, lo = pair_matrix(Fm, y, w, g)
    return {"keys": list(keys), "means": means, "mu": mu, "sd": sd, "D": D, "pw": pw,
            "hi": hi, "lo": lo, "w": w, "rows": rows,
            "n_rows": len(rows), "n_pairs": int(pw.size)}


def pair_fit(D: np.ndarray, pw: np.ndarray, pen: np.ndarray, lb: np.ndarray, ub: np.ndarray,
             x0: np.ndarray | None = None) -> np.ndarray:
    """argmin sum pw log(1 + exp(-D b)) + 0.5 sum pen b^2 within the bounds (L-BFGS-B)."""
    from scipy.optimize import minimize

    def fg(b):
        m = D @ b
        loss = float(pw @ np.logaddexp(0.0, -m) + 0.5 * np.sum(pen * b * b))
        g = -(D.T @ (pw * _sigmoid(-m))) + pen * b
        return loss, g
    if x0 is None:
        x0 = np.zeros(D.shape[1])
        x0[0] = 1.0
    x0 = np.clip(np.asarray(x0, dtype=np.float64), lb, ub)
    res = minimize(fg, x0, jac=True, method="L-BFGS-B", bounds=list(zip(lb, ub)),
                   options={"ftol": 1e-12, "gtol": 1e-9, "maxiter": 5000, "maxfun": 20000})
    return res.x


def pair_loss(D: np.ndarray, pw: np.ndarray, b: np.ndarray) -> float:
    return float(pw @ np.logaddexp(0.0, -(D @ b))) if pw.size else 0.0


def pair_head(train_x: list[dict], side: str, keys: list[str], lam: float) -> dict | None:
    pd_ = pair_data(train_x, keys)
    if pd_ is None or pd_["n_pairs"] == 0:
        return None
    p = len(keys)
    if math.isinf(lam) or p == 0:
        pen = np.zeros(1)
        D = pd_["D"][:, :1]
        lb, ub = np.asarray([-np.inf]), np.asarray([np.inf])
        b = pair_fit(D, pd_["pw"], pen, lb, ub)
        beta = np.zeros(p)
        b_uc = float(b[0])
    else:
        pen0, lb0, ub0 = pen_bounds(keys, side, v2_pen=lam, cand_pen=lam)
        pen = np.concatenate([[0.0], pen0[2:]])
        lb = np.concatenate([[-np.inf], lb0[2:]])
        ub = np.concatenate([[np.inf], ub0[2:]])
        b = pair_fit(pd_["D"], pd_["pw"], pen, lb, ub)
        b_uc, beta = float(b[0]), b[1:]
    return {"keys": list(keys), "means": pd_["means"], "mu": [float(v) for v in pd_["mu"]],
            "sd": [float(v) for v in pd_["sd"]], "b0": 0.0, "b_uc": b_uc,
            "beta": [float(v) for v in beta], "lam": lam, "alpha": lam,
            "n_train": pd_["n_rows"], "n_pairs": pd_["n_pairs"], "trained_on": "has_block",
            "design": {"kind": "v2"}, "loss": "pairwise_logistic"}


def pair_head_loss(head: dict, te: list[dict]) -> float | None:
    pd_ = pair_data(te, head["keys"], head=head)
    if pd_ is None or pd_["n_pairs"] == 0:
        return None
    b = np.concatenate([[head["b_uc"]], np.asarray(head["beta"], dtype=np.float64)])
    return pair_loss(pd_["D"], pd_["pw"], b)


def rank_head(train_x: list[dict], side: str, v2_keys) -> tuple[dict | None, float, dict]:
    """D: lambda by nested forward-chained CV on the held-out mean pairwise log loss."""
    keys = universe_of(side, v2_keys)
    tot = {lam: 0.0 for lam in GRID_D}
    used = 0
    for yr in H.inner_years(train_x):
        tr = [r for r in train_x if int(r["decision_year"]) < yr]
        te = [r for r in train_x if int(r["decision_year"]) == yr]
        ls = {}
        for lam in GRID_D:
            h = pair_head(tr, side, keys, lam)
            v = None if h is None else pair_head_loss(h, te)
            if v is None:
                ls = None
                break
            ls[lam] = v
        if ls is None:
            continue
        for lam in GRID_D:
            tot[lam] += ls[lam]
        used += 1
    best = math.inf
    if used:
        best = None
        for lam in sorted(GRID_D, reverse=True):
            if best is None or tot[lam] < tot[best]:
                best = lam
    head = pair_head(train_x, side, keys, best)
    return head, best, {"inner_years_used": used,
                        "loss": {str(k): _rnd(v, 6) for k, v in tot.items()} if used else None}


# ---------------------------------------------------------------------------
# arm C: re-standardization within level x season
# ---------------------------------------------------------------------------

def structural_zero(key: str) -> bool:
    return any(key.startswith(p) for p in STRUCTURAL_ZERO_PREFIXES)


def level_of(r: dict):
    v = (r.get("v2") or {}).get("level_rank")
    return "nb" if v is None else int(v)


def make_season_of(raw_by_key: dict, live_season: int):
    """The read season of a row (the document, section 6)."""
    def season_of(r: dict) -> int:
        if r.get("twin"):
            return int(r["twin_read_season"])
        fr = r.get("frame")
        dy = int(r["decision_year"])
        if fr == "live":
            return int(live_season)
        if fr == "lv":
            return dy - 1
        m = ((raw_by_key.get(r["player_key"]) or {}).get("milb") or {})
        s = m.get("milb_season")
        return int(s) if s is not None else dy - 1
    return season_of


def _vals(rows: list[dict], key: str) -> list[tuple[int, float]]:
    sz = structural_zero(key)
    out = []
    for i, r in enumerate(rows):
        v = r["v2"].get(key)
        if v is None or (sz and float(v) == 0.0):
            continue
        out.append((i, float(v)))
    return out


def _moments(v: np.ndarray) -> tuple[float, float] | None:
    if v.size < MIN_GROUP_VALUES:
        return None
    s = float(v.std(ddof=1))
    return (float(v.mean()), s) if s > 0 else None


def restd_reference(train: list[dict], keys: list[str]) -> dict:
    """{key: {level: (mean, sd)}, "_all": (mean, sd)} over the fit's training rows."""
    out = {}
    for k in keys:
        got = _vals(train, k)
        by: dict = {}
        for i, v in got:
            by.setdefault(level_of(train[i]), []).append(v)
        ref = {lv: _moments(np.asarray(vs)) for lv, vs in by.items()}
        ref["_all"] = _moments(np.asarray([v for _i, v in got]))
        out[k] = ref
    return out


def restandardize(rows: list[dict], keys: list[str], ref: dict, season_of) -> tuple[list[dict], dict]:
    """Copies of rows with each key re-read within (level band, read season) onto the
    reference moments of its level band (section 6); receipt of the groups used."""
    new = [dict(r, v2=dict(r["v2"])) for r in rows]
    rec = {}
    for k in keys:
        got = _vals(rows, k)
        if not got:
            rec[k] = {"values": 0}
            continue
        by_ls: dict = {}
        by_s: dict = {}
        for i, v in got:
            r = rows[i]
            by_ls.setdefault((level_of(r), season_of(r)), []).append((i, v))
            by_s.setdefault(season_of(r), []).append((i, v))
        mom_ls = {g: _moments(np.asarray([v for _i, v in vs])) for g, vs in by_ls.items()}
        mom_s = {g: _moments(np.asarray([v for _i, v in vs])) for g, vs in by_s.items()}
        n_ls = n_s = n_none = 0
        for (lv, s), vs in by_ls.items():
            m = mom_ls[(lv, s)]
            how = "ls"
            if m is None:
                m = mom_s.get(s)
                how = "s"
            r_ref = (ref.get(k) or {}).get(lv) or (ref.get(k) or {}).get("_all")
            if m is None or r_ref is None:
                n_none += len(vs)
                continue
            for i, v in vs:
                new[i]["v2"][k] = r_ref[0] + (v - m[0]) * r_ref[1] / m[1]
            if how == "ls":
                n_ls += len(vs)
            else:
                n_s += len(vs)
        rec[k] = {"values": len(got), "level_season": n_ls, "season_only": n_s, "unchanged": n_none}
    return new, rec


def clip_to(rows: list[dict], keys: list[str], train: list[dict]) -> tuple[list[dict], int]:
    """Values clipped into the transformed training range of each key."""
    n = 0
    out = [dict(r, v2=dict(r["v2"])) for r in rows]
    for k in keys:
        tv = [float(r["v2"][k]) for r in train if r["v2"].get(k) is not None]
        if not tv:
            continue
        lo, hi = min(tv), max(tv)
        for r in out:
            v = r["v2"].get(k)
            if v is None:
                continue
            if v < lo:
                r["v2"][k] = lo
                n += 1
            elif v > hi:
                r["v2"][k] = hi
                n += 1
    return out, n


def restd_fit_rows(tr_x: list[dict], te_x: list[dict] | None, keys: list[str], season_of
                   ) -> tuple[list[dict], list[dict] | None, dict]:
    ref = restd_reference(tr_x, keys)
    tr2, rec_tr = restandardize(tr_x, keys, ref, season_of)
    te2, rec_te = (restandardize(te_x, keys, ref, season_of) if te_x is not None else (None, None))
    return tr2, te2, {"train": rec_tr, "test": rec_te, "ref": ref}


def restd_live(prod_tr_x: list[dict], live_rows: list[dict], keys: list[str], season_of
               ) -> tuple[list[dict], list[dict], dict]:
    """(transformed production training rows, transformed and clipped live rows, receipt)."""
    tr2, _none, rec = restd_fit_rows(prod_tr_x, None, keys, season_of)
    lv2, rec_l = restandardize(live_rows, keys, rec["ref"], season_of)
    lv2, n_clip = clip_to(lv2, keys, tr2)
    return tr2, lv2, {"train": rec["train"], "live": rec_l, "clipped": n_clip}


# ---------------------------------------------------------------------------
# the shift classifier (section 6)
# ---------------------------------------------------------------------------

def _logit_fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    Z = np.column_stack([np.ones(len(y)), X])
    pen = np.concatenate([[1e-8], np.full(X.shape[1], SHIFT_PEN)])
    return H._logistic(Z, y, np.zeros(len(y)), pen)


def _logit_pred(b: np.ndarray, X: np.ndarray) -> np.ndarray:
    return _sigmoid(np.column_stack([np.ones(X.shape[0]), X]) @ b)


def _auc(score: np.ndarray, pos: np.ndarray) -> float | None:
    import source_backtest as SB
    return SB._auc_np(np, np.asarray(score, dtype=np.float64), np.asarray(pos, dtype=bool))


def cv_auc(X: np.ndarray, y: np.ndarray, *, seed: int = SEED) -> float | None:
    """Stratified CV_FOLDS-fold cross-validated AUC of the ridge logistic."""
    if X.shape[1] == 0:
        return 0.5
    rng = np.random.default_rng(seed)
    fold = np.empty(len(y), dtype=int)
    for cls in (0, 1):
        ix = np.flatnonzero(y == cls)
        ix = ix[rng.permutation(ix.size)]
        fold[ix] = np.arange(ix.size) % CV_FOLDS
    p = np.zeros(len(y))
    for f in range(CV_FOLDS):
        te = fold == f
        b = _logit_fit(X[~te], y[~te])
        p[te] = _logit_pred(b, X[te])
    return _auc(p, y == 1)


def shift_read(train_rows: list[dict], live_rows: list[dict], head: dict, side: str,
               extra_keys: list[str]) -> dict:
    """Section 6 per side: SMD, KS, the classifier and the drop-one AUC."""
    from scipy.stats import ks_2samp
    T = H.skill_training_rows(train_rows)
    L = [r for r in live_rows if r["v2"].get("has_block")]
    keys = list(head["keys"])
    mu, sd = np.asarray(head["mu"]), np.asarray(head["sd"])
    XT = (H._v2_x(T, keys, head["means"]) - mu) / sd
    XL = (H._v2_x(L, keys, head["means"]) - mu) / sd
    X = np.vstack([XT, XL])
    y = np.concatenate([np.zeros(len(T)), np.ones(len(L))])
    full = cv_auc(X, y)
    b = _logit_fit(X, y)
    ins = _auc(_logit_pred(b, X), y == 1)
    per = {}
    for j, k in enumerate(keys):
        keep = [i for i in range(len(keys)) if i != j]
        drop = cv_auc(X[:, keep], y) if keep else 0.5
        per[k] = dict(_describe(T, L, k, head["means"].get(k, 0.0), ks_2samp),
                      cv_auc_without=_rnd(drop, 4),
                      drop=_rnd(None if (full is None or drop is None) else full - drop, 4))
        per[k]["carries"] = bool((per[k]["drop"] is not None and per[k]["drop"] >= CARRY_DROP)
                                 or (per[k]["smd_design"] is not None
                                     and abs(per[k]["smd_design"]) >= CARRY_SMD))
    desc = {}
    for k in extra_keys:
        if k in per:
            continue
        m = H.has_block_means(train_rows).get(k, 0.0)
        desc[k] = _describe(T, L, k, m, ks_2samp)
    return {"n_train": len(T), "n_live": len(L), "cv_auc": _rnd(full, 4),
            "in_sample_auc": _rnd(ins, 4), "keys": per, "descriptive": desc,
            "carrying": sorted(k for k, v in per.items() if v["carries"])}


def _describe(T, L, k, mean_fill, ks) -> dict:
    t_obs = np.asarray([float(r["v2"][k]) for r in T if r["v2"].get(k) is not None])
    l_obs = np.asarray([float(r["v2"][k]) for r in L if r["v2"].get(k) is not None])
    t_des = np.asarray([float(r["v2"][k]) if r["v2"].get(k) is not None else float(mean_fill) for r in T])
    l_des = np.asarray([float(r["v2"][k]) if r["v2"].get(k) is not None else float(mean_fill) for r in L])

    def smd(a, b):
        if a.size < 2 or b.size < 1 or float(a.std(ddof=1)) <= 0:
            return None
        return (float(b.mean()) - float(a.mean())) / float(a.std(ddof=1))
    out = {"smd_design": _rnd(smd(t_des, l_des), 4), "smd_observed": _rnd(smd(t_obs, l_obs), 4),
           "n_obs_train": int(t_obs.size), "n_obs_live": int(l_obs.size),
           "train_mean": _rnd(t_obs.mean() if t_obs.size else None, 4),
           "live_mean": _rnd(l_obs.mean() if l_obs.size else None, 4)}
    if t_obs.size >= 5 and l_obs.size >= 5:
        r = ks(t_obs, l_obs)
        out.update(ks=_rnd(r.statistic, 4), ks_p=float(f"{r.pvalue:.3g}"))
    else:
        out.update(ks=None, ks_p=None)
    return out


# ---------------------------------------------------------------------------
# clubs and the six-season label (section 2, section 7)
# ---------------------------------------------------------------------------

def club_of(rec: dict | None, season: int, pk: str) -> str:
    """The developing club in the read season: the line of that season with the most
    games (minor league lines first), else the nearest earlier season's, else the signing
    organization, else the record's organization; else the row is its own cluster."""
    if rec:
        lines = [s for s in (rec.get("career_stats") or []) if s.get("org")
                 and s.get("season") is not None and int(s["season"]) <= int(season)]
        for pool in ([s for s in lines if s.get("level") != "MLB"], lines):
            if not pool:
                continue
            last = max(int(s["season"]) for s in pool)
            best = max((s for s in pool if int(s["season"]) == last),
                       key=lambda s: (float(s.get("games") or s.get("g") or 0), str(s.get("org"))))
            return str(best["org"])
        dc = (rec.get("dev_credit") or {}).get("signing_org")
        if dc:
            return str(dc)
        if rec.get("org"):
            return str(rec["org"])
    return f"solo:{pk}"


def l6_lv(scored: list[dict]) -> dict:
    """{(side, V, key): six-season label} of the lv_dev scored rows (efv_labels L6; its
    censored projection where not resolved)."""
    import efv_labels as L
    uni = F.load_universe()
    war = L.war_seasons_table()
    out = {}
    for c in scored:
        V = int(c["year"])
        rec = uni.get(c["key"])
        if rec is None:
            continue
        lab = L.labels_for(rec, V, war.get(c["key"]))
        v = lab.get("l6")
        if v is None:
            v = lab.get("l6_censored_target")
        if v is not None:
            out[(c["side"], V, c["key"])] = float(v)
    return out


# ---------------------------------------------------------------------------
# packs, weights and orders
# ---------------------------------------------------------------------------

def make_packs(ctxs: list[dict], heads: dict) -> list[dict]:
    """RF.pack per fold from {fold id: head or None} (e_skill on the test rows; e_time 0)."""
    out = []
    for c in ctxs:
        h = heads.get(c["fold_id"])
        te_x = c.get("te_fit", c["te_x"])
        es = H.e_skill(h, te_x) if h is not None else np.zeros(len(c["te"]))
        out.append(RF.pack(c["fold_id"], c["fid"], c["side"], c["fold"], c["te"], c["scored"], es,
                           np.zeros(len(c["te"])), model={"skill": h}))
    return out


def weights_cf(packs: list[dict]) -> dict:
    return {s: RF.cross_fitted([p for p in packs if p["side"] == s]) for s in SIDES}


def weights_all(packs: list[dict]) -> dict:
    return {s: RF.weights_from([p for p in packs if p["side"] == s]) for s in SIDES}


class Scored:
    """One side's scored rows of both frames, the arrays every statistic reads."""

    def __init__(self, b1: dict, side: str, clubs: dict, l6: dict):
        BT, _B4 = _tools()
        inp = b1["inp"]
        rows = []
        for fid in BT.FRAMES_DEV:
            for c in inp.scored(fid):
                if c["side"] == side:
                    rows.append((fid, c))
        self.side = side
        self.keys = [(fid, int(c["year"]), c["key"]) for fid, c in rows]
        self.pos = {k: i for i, k in enumerate(self.keys)}
        self.frame = np.asarray([fid for fid, _c in rows])
        self.codes = np.asarray([f"{fid}|{c['group']}" for fid, c in rows])
        self.y = np.asarray([float(c["outcome"]["war"]) for _f, c in rows])
        self.contrib = np.asarray([bool(c["outcome"]["contributor"]) for _f, c in rows])
        self.cons = np.asarray([float(c["grades"][BT.CONS]) for _f, c in rows])
        self.player = np.asarray([c["key"] for _f, c in rows])
        self.club = np.asarray([clubs.get((fid, side, int(c["year"]), c["key"]), f"solo:{c['key']}")
                                for fid, c in rows])
        self.l6 = np.asarray([l6.get((fid, side, int(c["year"]), c["key"]), np.nan)
                              for fid, c in rows])
        self.rows = [c for _f, c in rows]
        self.n = len(rows)

    def order(self, packs: list[dict], wcf: dict | None, *, const: float | None = None) -> np.ndarray:
        """The order on the scored rows: u_c + w e_skill (+ w_time e_time) with the fold's
        cross-fitted weights, or one constant weight."""
        out = np.full(self.n, np.nan)
        for p in packs:
            if p["side"] != self.side:
                continue
            if const is None:
                w = wcf[self.side][p["fold_id"]]
                ws, wt = float(w["w_skill"]), float(w["w_time"])
            else:
                ws, wt = float(const), 0.0
            o = p["u_c"] + ws * p["e_s"] + wt * p["e_t"]
            for k, v in zip(p["keys"], o):
                i = self.pos.get((p["fid"], int(p["fold"]), k))
                if i is not None:
                    out[i] = float(v)
        if np.isnan(out).any():
            raise RuntimeError(f"{self.side}: {int(np.isnan(out).sum())} scored rows without an order")
        return out

    def consensus(self, packs: list[dict]) -> np.ndarray:
        out = np.full(self.n, np.nan)
        for p in packs:
            if p["side"] != self.side:
                continue
            for k, v in zip(p["keys"], p["u_c"]):
                i = self.pos.get((p["fid"], int(p["fold"]), k))
                if i is not None:
                    out[i] = float(v)
        return out


# ---------------------------------------------------------------------------
# the statistic and the paired cluster bootstrap (section 2)
# ---------------------------------------------------------------------------

def _groups(codes: np.ndarray, frame: np.ndarray, mask: np.ndarray | None = None) -> dict:
    import efv_v2_stat as S
    sel = np.arange(codes.size) if mask is None else np.flatnonzero(mask)
    out = {}
    for f in ("lv_dev", "vm_dev"):
        ix = sel[frame[sel] == f]
        out[f] = [str(u) for u in S.kept_groups(codes[ix])]
    return out


def pooled_stat(orders: dict, y: np.ndarray, codes: np.ndarray, frame: np.ndarray,
                kept: dict, idx: np.ndarray) -> dict:
    """{name: (pooled, {frame: within})} on the rows idx (a group counts with 3 or more
    rows in the draw; within size weighted; pooled over the frames by rows used)."""
    import source_backtest as SB
    names = list(orders)
    out_w = {n: {} for n in names}
    rows_f = {}
    for f in ("lv_dev", "vm_dev"):
        ixf = idx[frame[idx] == f]
        gc = codes[ixf]
        tot = {n: 0.0 for n in names}
        m_tot = 0
        for u in kept[f]:
            m = ixf[gc == u]
            if m.size < 3:
                continue
            yr = SB._ranks_np(np, y[m])
            rs = {}
            ok = True
            for n in names:
                r = SB._corr_np(np, SB._ranks_np(np, orders[n][m]), yr)
                if r is None:
                    ok = False
                    break
                rs[n] = r
            if not ok:
                continue
            for n in names:
                tot[n] += rs[n] * m.size
            m_tot += m.size
        rows_f[f] = m_tot
        for n in names:
            out_w[n][f] = tot[n] / m_tot if m_tot else None
    res = {}
    n_all = sum(rows_f.values())
    for n in names:
        if not n_all:
            res[n] = (None, out_w[n])
            continue
        res[n] = (sum(rows_f[f] * out_w[n][f] for f in rows_f if out_w[n][f] is not None) / n_all,
                  out_w[n])
    return res


def boot(orders: dict, y: np.ndarray, codes: np.ndarray, frame: np.ndarray, clusters: np.ndarray,
         *, B: int = B, seed: int = SEED, mask: np.ndarray | None = None) -> dict:
    """The point and B paired cluster draws of every order's pooled within (one shared draw
    per replicate, so differences are paired)."""
    import source_backtest as SB
    sel = np.arange(y.size) if mask is None else np.flatnonzero(mask)
    kept = _groups(codes, frame, mask)
    point = pooled_stat(orders, y, codes, frame, kept, sel)
    order, starts, lens = SB._cluster_layout(np, clusters[sel])
    rng = np.random.default_rng(int(seed))
    names = list(orders)
    draws = np.full((int(B), len(names)), np.nan)
    for b in range(int(B)):
        ix = sel[SB._cluster_draw(np, rng, order, starts, lens)]
        st = pooled_stat(orders, y, codes, frame, kept, ix)
        draws[b] = [np.nan if st[n][0] is None else st[n][0] for n in names]
    return {"names": names, "point": point, "draws": draws, "kept": kept,
            "n_clusters": int(starts.size), "n": int(sel.size)}


def diff(bt: dict, a: str, b: str) -> dict:
    """a minus b: point, CI90, CI95, one-sided 95 percent lower bound, the non-inferiority
    p value at MARGIN and the per-frame points."""
    ia, ib = bt["names"].index(a), bt["names"].index(b)
    d = bt["draws"][:, ia] - bt["draws"][:, ib]
    d = d[np.isfinite(d)]
    pa, pb = bt["point"][a], bt["point"][b]
    pt = None if (pa[0] is None or pb[0] is None) else pa[0] - pb[0]
    frames = {f: (None if (pa[1].get(f) is None or pb[1].get(f) is None)
                  else _rnd(pa[1][f] - pb[1][f], 5)) for f in ("lv_dev", "vm_dev")}
    if d.size < 50:
        return {"delta": _rnd(pt), "frames": frames, "status": "too few draws"}
    q = np.quantile(d, [0.025, 0.05, 0.95, 0.975])
    return {"delta": _rnd(pt), "frames": frames, "ci90": [_rnd(q[1], 4), _rnd(q[2], 4)],
            "ci95": [_rnd(q[0], 4), _rnd(q[3], 4)], "lower95_one_sided": _rnd(q[1], 5),
            "p_noninferior": _rnd((int(np.sum(d <= -MARGIN)) + 1) / (d.size + 1), 5),
            "B_used": int(d.size)}


def holm(pvals: dict, alpha: float = HOLM_ALPHA) -> dict:
    """{test: {"p", "threshold", "rejects"}} by Holm's step-down at family alpha."""
    items = sorted(pvals.items(), key=lambda t: (t[1], t[0]))
    m = len(items)
    out = {}
    stop = False
    for i, (k, p) in enumerate(items):
        thr = alpha / (m - i)
        rej = (not stop) and p <= thr
        if not rej:
            stop = True
        out[k] = {"p": p, "threshold": _rnd(thr, 6), "rejects": bool(rej), "rank": i + 1}
    return out


# ---------------------------------------------------------------------------
# arm A: the production bootstrap
# ---------------------------------------------------------------------------

def mult_draws(cluster_ids: np.ndarray, B_: int, seed: int) -> np.ndarray:
    """(B, n) multiplicity weights: clusters drawn with replacement, every row of a drawn
    cluster weighted by its draw count."""
    u, inv = np.unique(cluster_ids, return_inverse=True)
    rng = np.random.default_rng(int(seed))
    out = np.empty((int(B_), cluster_ids.size))
    for b in range(int(B_)):
        cnt = np.bincount(rng.integers(0, u.size, u.size), minlength=u.size)
        out[b] = cnt[inv]
    return out


def boot_coefs(Z, y, w, pen, lb, ub, mults: np.ndarray) -> np.ndarray:
    out = np.empty((mults.shape[0], Z.shape[1]))
    for b in range(mults.shape[0]):
        out[b] = solve(Z, y, w * mults[b], pen, lb, ub)
    return out


def slope_table(coefs: np.ndarray, keys: list[str], point: np.ndarray, w_skill: float) -> dict:
    """Per key: beta / b_uc (and times w_skill) with CI90, CI95, the share at the
    production sign and at exactly 0."""
    out = {}
    buc = coefs[:, 1]
    ok = buc > 0
    for j, k in enumerate(keys):
        s = coefs[ok, 2 + j] / buc[ok]
        p = point[2 + j] / point[1]
        q = np.quantile(s, [0.025, 0.05, 0.95, 0.975]) if s.size else [np.nan] * 4
        sg = np.sign(p)
        out[k] = {"per_sd": _rnd(p, 5), "order_weight": _rnd(w_skill * p, 5),
                  "ci90": [_rnd(q[1], 5), _rnd(q[2], 5)], "ci95": [_rnd(q[0], 5), _rnd(q[3], 5)],
                  "share_at_sign": _rnd(float(np.mean(np.sign(s) == sg)) if (s.size and sg != 0) else None, 4),
                  "share_zero": _rnd(float(np.mean(s == 0.0)) if s.size else None, 4),
                  "ci95_includes_zero": bool(q[0] <= 0.0 <= q[3]),
                  "ci90_includes_zero": bool(q[1] <= 0.0 <= q[2])}
    return out


def ratio_boot(packs_side: list[dict], cl: np.ndarray, B_: int, seed: int) -> dict:
    """A2: DS-08 as served (u_y ~ 1 + u_c + e_skill + e_time) under cluster draws."""
    u_c, u_y, e_s, e_t = RF._pool(packs_side)
    pt = RF.ols_ratios(u_c, u_y, e_s, e_t)
    mults = mult_draws(cl, B_, seed)
    got = {"w_skill_ratio": [], "w_time_ratio": [], "w_skill": [], "w_time": []}
    cols = {"u_c": u_c, "e_skill": e_s, "e_time": e_t}
    live = [k for k, v in cols.items() if k == "u_c" or np.any(v != 0)]
    X = np.column_stack([np.ones(u_y.size)] + [cols[k] for k in live])
    for b in range(mults.shape[0]):
        wv = mults[b]
        A = (X * wv[:, None]).T @ X
        try:
            coef = np.linalg.solve(A, (X * wv[:, None]).T @ u_y)
        except np.linalg.LinAlgError:
            continue
        c = dict(zip(["intercept"] + live, coef))
        cu = c["u_c"]
        for nm, key in (("w_skill", "e_skill"), ("w_time", "e_time")):
            r = c[key] / cu if (cu > 0 and key in c) else None
            if r is not None:
                got[nm + "_ratio"].append(r)
                got[nm].append(min(max(r, 0.0), 1.0))
    out = {"point": {k: _rnd(pt.get(k), 5) for k in ("w_skill", "w_time", "w_skill_ratio", "w_time_ratio")}}
    for k, v in got.items():
        a = np.asarray(v)
        out[k] = ({"ci90": [_rnd(np.quantile(a, 0.05), 4), _rnd(np.quantile(a, 0.95), 4)],
                   "ci95": [_rnd(np.quantile(a, 0.025), 4), _rnd(np.quantile(a, 0.975), 4)],
                   "B_used": int(a.size)} if a.size > 1 else None)
    return out


# ---------------------------------------------------------------------------
# the run (kept in parts that resume from the work directory)
# ---------------------------------------------------------------------------

class Run:
    def __init__(self, cache_dir: Path, work: Path, *, log=print):
        self.cache = Path(cache_dir)
        self.work = Path(work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.t0 = time.time()
        self.b1, self.packs, self.p0 = load_cache(self.cache)
        self.ctx = contexts(self.b1, self.packs)
        self.served = served_models()
        self.prod = {s: production_context(self.b1, s) for s in SIDES}

    def _load(self, name):
        p = self.work / f"{name}.pkl"
        if p.exists():
            with p.open("rb") as fh:
                self.log(f"  work hit {name}")
                return pickle.load(fh)
        return None

    def _save(self, name, obj):
        with (self.work / f"{name}.pkl").open("wb") as fh:
            pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)

    def cached(self, name, fn):
        got = self._load(name)
        if got is None:
            t = time.time()
            got = fn()
            self._save(name, got)
            self.log(f"  built {name} ({round(time.time() - t, 1)} s)")
        return got

    # -- parity (section 1) ---------------------------------------------------------
    def parity(self) -> dict:
        out = {}
        for s in SIDES:
            head = self.served[s]["skill"]
            Dz = design_of(self.prod[s]["tr_x"], head["keys"])
            pen, lb, ub = served_pens(head, s)
            coef = solve(Dz["Z"], Dz["u_y"], Dz["w"], pen, lb, ub)
            stored = np.concatenate([[head["b0"], head["b_uc"]], head["beta"]])
            d = float(np.max(np.abs(coef - stored)))
            if d > 1e-9:
                raise RuntimeError(f"{s}: the production skill head is not reproduced ({d})")
            out[s] = {"production_max_abs_diff": d, "keys": len(head["keys"])}
        worst = 0.0
        for c in self.ctx:
            es = H.e_skill(c["model"].get("skill"), c["te_x"])
            worst = max(worst, float(np.max(np.abs(es - c["pack"]["e_s"]))) if es.size else 0.0)
        if worst > 1e-9:
            raise RuntimeError(f"the cached fold models do not reproduce the cached e_skill ({worst})")
        out["fold_e_skill_max_abs_diff"] = worst
        return out

    def parity_procedure(self) -> dict:
        """served_skill on each fold's rows reproduces the cached fold skill head."""
        worst, n = 0.0, 0
        for c in self.ctx:
            h = served_skill(c["tr_x"], c["side"], c["kind"])
            a = slopes_of(h)
            b = slopes_of(c["model"].get("skill"))
            ks = set(a) | set(b)
            d = max([abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in ks] or [0.0])
            worst = max(worst, d)
            n += 1
        if worst > 1e-8:
            raise RuntimeError(f"the served skill procedure is not reproduced ({worst})")
        return {"folds": n, "max_abs_slope_diff": worst}

    # -- clubs, L6, scored arrays ---------------------------------------------------
    def clubs(self) -> dict:
        BT, _B4 = _tools()
        uni = F.load_universe()
        inp = self.b1["inp"]
        raw = {s: V5C._raw_by_side()[s] for s in SIDES}
        out = {}
        for fid in BT.FRAMES_DEV:
            for c in inp.scored(fid):
                Y = int(c["year"])
                if fid == "lv_dev":
                    R = Y - 1
                else:
                    m = ((raw[c["side"]].get(c["key"]) or {}).get("milb") or {})
                    R = int(m["milb_season"]) if m.get("milb_season") is not None else Y - 1
                out[(fid, c["side"], Y, c["key"])] = club_of(uni.get(c["key"]), R, c["key"])
        prod = {}
        for s in SIDES:
            so = make_season_of(raw[s], 2026)
            for r in self.prod[s]["tr"]:
                prod[(s, int(r["decision_year"]), r["player_key"], bool(r.get("twin")))] = \
                    club_of(uni.get(r["player_key"]), so(r), r["player_key"])
        return {"scored": out, "prod": prod}

    def l6(self) -> dict:
        import efv_labels as L
        BT, _B4 = _tools()
        if L.provider() != BT.FROZEN_PROVIDER:
            raise RuntimeError(f"label provider is {L.provider()!r}, not {BT.FROZEN_PROVIDER!r}")
        inp = self.b1["inp"]
        lv = l6_lv(inp.scored("lv_dev"))
        out = {("lv_dev",) + k: v for k, v in lv.items()}
        for c in self.ctx:
            if c["fid"] != "vm_dev":
                continue
            tgt = {r["player_key"]: r.get("target") for r in c["te"]}
            for sc in c["scored"]:
                v = tgt.get(sc["key"])
                if v is not None:
                    out[("vm_dev", c["side"], c["fold"], sc["key"])] = float(v)
        return out

    # -- the live board (section 6) -------------------------------------------------
    def live(self) -> dict:
        import efv_dataset as D
        import efv_v2_serve as S
        RF.clear_flag_caches()
        out = {}
        for s in SIDES:
            live = json.loads(D.live_matrix_path(s).read_text(encoding="utf-8"))
            rows = S.live_rows(s, live, today=LIVE_DAY)
            rows = S._with_live_candidates(s, rows, live, self.served[s], LIVE_DAY)
            got = RF.score_board(s, self.served[s], today=LIVE_DAY)
            eff = RF.board_effect({s: got})[s]
            if eff["moved_1_or_more"] or (eff["max_move"] or 0) > 1e-9:
                raise RuntimeError(f"{s}: the served models do not reproduce data/xfv.json on the "
                                   f"live board of {LIVE_DAY}")
            out[s] = {"rows": rows, "n": len(rows), "parity": {"rows": eff["n"], "max_move": eff["max_move"]}}
        return out

    # -- arm A ----------------------------------------------------------------------
    def arm_a(self, clubs: dict) -> dict:
        out = {}
        for s in SIDES:
            m = self.served[s]
            head = m["skill"]
            Dz = design_of(self.prod[s]["tr_x"], head["keys"])
            pen, lb, ub = served_pens(head, s)
            pt = solve(Dz["Z"], Dz["u_y"], Dz["w"], pen, lb, ub)
            rows = Dz["rows"]
            pl = np.asarray([r["player_key"] for r in rows])
            cb = np.asarray([clubs["prod"].get((s, int(r["decision_year"]), r["player_key"],
                                                bool(r.get("twin"))), f"solo:{r['player_key']}")
                             for r in rows])
            blk = {"n_rows": len(rows), "n_players": int(np.unique(pl).size),
                   "n_clubs": int(np.unique(cb).size), "w_skill": m["w_skill"],
                   "lam": _rnd(head.get("lam")), "alpha": _rnd(head.get("alpha"))}
            for nm, cl, sd in (("player", pl, SEED), ("club", cb, SEED + 1)):
                mults = mult_draws(cl, B, sd)
                co = boot_coefs(Dz["Z"], Dz["u_y"], Dz["w"], pen, lb, ub, mults)
                blk[nm] = slope_table(co, head["keys"], pt, float(m["w_skill"]))
                if nm == "player":
                    self._save(f"a1_player_coefs_{s}", (mults, co))
            # A5: planted recovery
            fitted = Dz["Z"] @ pt
            resid_sd = float(np.std(Dz["u_y"] - fitted, ddof=1))
            eps = np.random.default_rng(SEED + 7).normal(0.0, resid_sd, len(rows))
            c0 = H._wls(Dz["Z"][:, :2], Dz["u_y"], Dz["w"], np.zeros(2))
            mults = mult_draws(pl, B, SEED + 2)
            planted = {}
            for nm, y in (("fitted", fitted + eps), ("zero", Dz["Z"][:, :2] @ c0 + eps)):
                co = boot_coefs(Dz["Z"], y, Dz["w"], pen, lb, ub, mults)
                truth = (pt[2:] / pt[1]) if nm == "fitted" else np.zeros(len(head["keys"]))
                tab = slope_table(co, head["keys"], np.concatenate([[1.0, 1.0], truth]), 1.0)
                cover = [tab[k]["ci95"][0] <= t <= tab[k]["ci95"][1] for k, t in zip(head["keys"], truth)]
                nz = [k for k, t in zip(head["keys"], truth) if t != 0.0]
                planted[nm] = {"truth_per_sd": {k: _rnd(t, 5) for k, t in zip(head["keys"], truth)},
                               "share_ci95_covers_truth": _rnd(float(np.mean(cover)), 4),
                               "share_nonzero_truth_excluding_zero": (
                                   _rnd(float(np.mean([not tab[k]["ci95_includes_zero"] for k in nz])), 4)
                                   if nz else None),
                               "share_excluding_zero": _rnd(float(np.mean(
                                   [not tab[k]["ci95_includes_zero"] for k in head["keys"]])), 4),
                               "table": tab}
            blk["planted"] = dict(planted, resid_sd=_rnd(resid_sd, 5), seed=SEED + 7)
            blk["edf"] = edf(Dz["Z"], Dz["w"], pen, lb, ub, pt)
            # A2
            mine = [p for p in self.packs if p["side"] == s]
            pkeys = [k for p in mine for k in p["ols"]["keys"]]
            pfold = [(p["fid"], p["fold"]) for p in mine for _k in p["ols"]["keys"]]
            cl_p = np.asarray(pkeys)
            cl_c = np.asarray([clubs["scored"].get((f, s, Y, k), f"solo:{k}") for (f, Y), k in zip(pfold, pkeys)])
            blk["head_weights"] = {"player": ratio_boot(mine, cl_p, B, SEED + 3),
                                   "club": ratio_boot(mine, cl_c, B, SEED + 4)}
            # A3
            blk["loco"] = self.loco(s, head)
            for k, v in blk["player"].items():
                lc = blk["loco"]["keys"].get(k) or {}
                if not (v["ci95_includes_zero"] or blk["club"][k]["ci95_includes_zero"]) and not lc.get("flips"):
                    v["reading"] = "real"
                elif v["ci90_includes_zero"] or blk["club"][k]["ci90_includes_zero"]:
                    v["reading"] = "noise"
                else:
                    v["reading"] = "weak"
                v["flagged"] = bool(v["ci95_includes_zero"] or blk["club"][k]["ci95_includes_zero"])
            # the timing head (weight 0): descriptive slopes only
            th = m.get("timing") or {}
            blk["timing_head"] = {"w_time": m["w_time"], "keys": list(th.get("keys") or []),
                                  "per_sd": {k: _rnd(b / th["b_uc"], 5) for k, b in
                                             zip(th.get("keys") or [], th.get("beta") or [])}
                                  if th.get("b_uc") else None,
                                  "note": "weight 0: moves no order"}
            out[s] = blk
            self.log(f"  arm A {s}: done ({round(time.time() - self.t0, 1)} s)")
        return out

    def loco(self, side: str, head: dict) -> dict:
        tr = self.prod[side]["tr"]
        years = sorted({int(r["decision_year"]) for r in tr})
        fits = {}
        for y in years:
            sub = [r for r in tr if int(r["decision_year"]) != y]
            h = served_skill(RF.rank_transform(sub, side), side, "vm")
            fits[y] = {"lam": _rnd(None if h is None else h.get("lam")),
                       "per_sd": ({k: b / h["b_uc"] for k, b in slopes_of(h).items()}
                                  if h and h.get("b_uc") else {})}
        keys = {}
        for k in head["keys"]:
            vals = [fits[y]["per_sd"].get(k, 0.0) for y in years]
            pos = sum(1 for v in vals if v > 0)
            neg = sum(1 for v in vals if v < 0)
            keys[k] = {"per_sd": {str(y): _rnd(v, 5) for y, v in zip(years, vals)},
                       "n_plus": pos, "n_minus": neg, "n_zero": len(vals) - pos - neg,
                       "flips": bool(pos and neg)}
        return {"years": years, "lam": {str(y): fits[y]["lam"] for y in years}, "keys": keys}

    # -- configurations -------------------------------------------------------------
    def fit_config(self, name: str, ctxs: list[dict], *, carry: dict | None = None,
                   season_of=None) -> dict:
        """{fold id: {"head", "rec"}} of one configuration on the contexts given (fold or
        production contexts; rows possibly planted)."""
        out = {}
        for c in ctxs:
            t = time.time()
            side = c["side"]
            m = c.get("model")
            v2_keys, alpha, lam = fold_penalties(m) if m is not None else (None, None, None)
            if m is None:                                   # production: the served fit's own
                head0 = self.served[side]["skill"]
                v2_keys = list(head0.get("v2_keys") or [])
                alpha = head0.get("alpha")
                lam = math.inf if head0.get("lam") is None else float(head0["lam"])
            tr_x = c["tr_x"]
            rec: dict = {}
            if name == "S":
                head = served_skill(tr_x, side, c["kind"]) if c.get("refit") else (m or {}).get("skill")
            elif name in ("B1", "B3"):
                uni = universe_of(side, v2_keys)
                stab = stability(loco_slopes(tr_x, side, v2_keys, alpha, lam), uni)
                rank = ranked(stab)
                rec["stable"] = {k: stab[k]["sign"] for k in rank}
                if name == "B1":
                    head = unit_head(tr_x, rank, {k: stab[k]["sign"] for k in rank})
                else:
                    k, krec = select_k(tr_x, side, v2_keys, alpha, lam)
                    rec.update(k="all" if k is None and krec.get("inner_years_used") else k, cv=krec)
                    keys = _k_keys(rank, k) if krec.get("inner_years_used") else []
                    head = topk_head(tr_x, keys, {q: stab[q]["sign"] for q in keys}) if keys else None
            elif name == "B2":
                head, lam2 = ridge_head(tr_x, side, v2_keys)
                rec["lam"] = _rnd(lam2)
            elif name == "D":
                head, lamd, drec = rank_head(tr_x, side, v2_keys)
                rec.update(lam=_rnd(lamd), cv=drec)
            elif name == "C":
                keys = (carry or {}).get(side) or []
                tr2, te2, rrec = restd_fit_rows(tr_x, c.get("te_x"), keys, season_of)
                head = served_skill(tr2, side, c["kind"])
                rec["restd"] = rrec
                c = dict(c, te_fit=te2)
                out[c["fold_id"]] = {"head": head, "rec": rec, "te_fit": te2}
                rec["seconds"] = round(time.time() - t, 1)
                continue
            else:
                raise ValueError(name)
            rec["seconds"] = round(time.time() - t, 1)
            rec["nonzero"] = [k for k, b in slopes_of(head).items() if b != 0.0]
            out[c["fold_id"]] = {"head": head, "rec": rec}
        return out

    def packs_of(self, fits: dict, ctxs: list[dict]) -> list[dict]:
        heads = {k: v["head"] for k, v in fits.items()}
        cc = [dict(c, te_fit=fits[c["fold_id"]]["te_fit"]) if fits[c["fold_id"]].get("te_fit")
              is not None else c for c in ctxs]
        return make_packs(cc, heads)


def planted_contexts(run: Run, side: str) -> tuple[list[dict], dict, dict]:
    """The side's fold contexts with every training label and scored outcome replaced by
    truth + noise (section 3, P). Returns (contexts, {scored key: planted outcome}, receipt)."""
    head = run.served[side]["skill"]
    prod = run.prod[side]["tr"]
    pool = run.b1["pool"][side]
    table: dict = {}

    def add(rows, frame):
        rx = RF.rank_transform(rows, side)
        u_c = C._uc(rows)
        e = H.e_skill(head, rx)
        for r, u, ev in zip(rows, u_c, e):
            table[(frame, int(r["decision_year"]), r["player_key"], bool(r.get("twin")))] = float(u + ev)
    add(prod, "vm")
    add(pool, "lv")
    Dz = design_of(run.prod[side]["tr_x"], head["keys"])
    pen, lb, ub = served_pens(head, side)
    pt = solve(Dz["Z"], Dz["u_y"], Dz["w"], pen, lb, ub)
    sd = float(np.std(Dz["u_y"] - Dz["Z"] @ pt, ddof=1))
    ids = sorted(table)
    eps = np.random.default_rng(SEED + 11).normal(0.0, sd, len(ids))
    noise = dict(zip(ids, eps))
    miss = {"n": 0}

    def val(r, frame):
        k = (frame, int(r["decision_year"]), r["player_key"], bool(r.get("twin")))
        if k in table:
            return table[k] + noise[k]
        miss["n"] += 1
        h = zlib.crc32(repr(k).encode()) & 0xFFFFFFFF
        return float(np.random.default_rng(h).normal(0.0, sd))

    out = []
    planted_y = {}
    for c in run.ctx:
        if c["side"] != side:
            continue
        frame = "lv" if c["fid"] == "lv_dev" else "vm"
        tr = [dict(r, target=val(r, r.get("frame") or frame)) for r in c["tr"]]
        sc = []
        for s_ in c["scored"]:
            ident = (frame, int(c["fold"]), s_["key"], False)
            yv = (table[ident] + noise[ident]) if ident in table else val({"decision_year": c["fold"],
                                                                         "player_key": s_["key"]}, frame)
            planted_y[(c["fid"], int(c["fold"]), s_["key"])] = yv
            sc.append(dict(s_, outcome=dict(s_["outcome"], war=float(yv))))
        out.append(dict(c, tr=tr, tr_x=RF.rank_transform(tr, side), scored=sc, refit=True,
                        model=c["model"]))
    return out, planted_y, {"noise_sd": _rnd(sd, 5), "rows_in_table": len(table),
                            "rows_outside_table": miss["n"], "seed": SEED + 11}


def _head_system(nm: str, head: dict, tr_x: list[dict], side: str):
    """The WLS system of a production head: design, penalties and bounds."""
    Dz = design_of(tr_x, head["keys"])
    if Dz is None:
        return None
    if nm == "B1":
        sv = np.asarray([float(head["signs"][k]) for k in head["keys"]])
        Z = np.column_stack([Dz["Z"][:, :2], Dz["Z"][:, 2:] @ sv])
        return {"Dz": Dz, "Z": Z, "pen": np.zeros(3), "lb": np.asarray([-np.inf, -np.inf, 0.0]),
                "ub": np.asarray([np.inf, np.inf, np.inf]), "signs": sv}
    if nm == "B3":
        sg = head["signs"]
        pen = np.concatenate([[0.0, 0.0], np.full(len(head["keys"]), TOPK_PEN)])
        lb = np.asarray([-np.inf, -np.inf] + [0.0 if sg[k] > 0 else -np.inf for k in head["keys"]])
        ub = np.asarray([np.inf, np.inf] + [0.0 if sg[k] < 0 else np.inf for k in head["keys"]])
        return {"Dz": Dz, "Z": Dz["Z"], "pen": pen, "lb": lb, "ub": ub}
    if nm == "B2":
        lam = head.get("lam")
        lam = math.inf if lam is None else float(lam)
        pen, lb, ub = pen_bounds(head["keys"], side, v2_pen=lam,
                                 cand_pen=(0.0 if math.isinf(lam) else lam))
        return {"Dz": Dz, "Z": Dz["Z"], "pen": pen, "lb": lb, "ub": ub}
    pen, lb, ub = served_pens(head, side)
    return {"Dz": Dz, "Z": Dz["Z"], "pen": pen, "lb": lb, "ub": ub}


def _pair_system(head: dict, side: str):
    lam = float(head["lam"])
    pen0, lb0, ub0 = pen_bounds(head["keys"], side, v2_pen=lam, cand_pen=lam)
    return (np.concatenate([[0.0], pen0[2:]]), np.concatenate([[-np.inf], lb0[2:]]),
            np.concatenate([[np.inf], ub0[2:]]))


def pair_edf(head: dict, tr_x: list[dict], side: str) -> dict:
    """A4 for the rank-loss head: the trace of (Hessian + P)^-1 Hessian over the free
    coefficients, minus the consensus slope."""
    pd_ = pair_data(tr_x, head["keys"])
    if pd_ is None or not head.get("keys") or not H.head_usable(head):
        return {"edf_drivers": 0.0, "free_slopes": 0, "slopes": len(head.get("keys") or [])}
    b = np.concatenate([[head["b_uc"]], np.asarray(head["beta"])])
    pen, lb, ub = _pair_system(head, side)
    free = ~((b == 0.0) & ((lb == 0) | (ub == 0)))
    free[0] = True
    pr = _sigmoid(pd_["D"] @ b)
    Df = pd_["D"][:, free]
    Hm = (Df * (pd_["pw"] * pr * (1 - pr))[:, None]).T @ Df
    tr = float(np.trace(np.linalg.solve(Hm + np.diag(pen[free]), Hm)))
    return {"edf": round(tr, 3), "edf_drivers": round(tr - 1.0, 3), "free_slopes": int(free.sum() - 1),
            "slopes": len(head["keys"])}


def live_variance(nm: str, head: dict | None, w_skill: float, tr_x: list[dict], live_rows: list[dict],
                  side: str, mults: np.ndarray) -> dict:
    """Section 5: the mean over live rows of the bootstrap variance of 100 w e_skill, the
    head refitted at its fixed structure on each multiplicity draw of the production rows."""
    if head is None or not H.head_usable(head) or w_skill <= 0:
        return {"mean_var_pp2": 0.0, "rows": len(live_rows), "note": "no usable head or weight 0"}
    keys = head["keys"]
    Xl = (H._v2_x(live_rows, keys, head["means"]) - np.asarray(head["mu"])) / np.asarray(head["sd"])
    E = np.zeros((mults.shape[0], len(live_rows)))
    if nm == "D":
        pd_ = pair_data(tr_x, keys)
        pen, lb, ub = _pair_system(head, side)
        b0 = np.concatenate([[head["b_uc"]], np.asarray(head["beta"])])
        base = pd_["w"][pd_["hi"]] * pd_["w"][pd_["lo"]]
        for b in range(mults.shape[0]):
            mm = mults[b]
            pw = base * mm[pd_["hi"]] * mm[pd_["lo"]]
            t = pw.sum()
            co = pair_fit(pd_["D"], pw / t if t > 0 else pw, pen, lb, ub, x0=b0)
            if co[0] > 0:
                E[b] = (Xl @ co[1:]) / co[0]
    else:
        sysm = _head_system(nm, head, tr_x, side)
        Z, y, w = sysm["Z"], sysm["Dz"]["u_y"], sysm["Dz"]["w"]
        Xuse = Xl @ sysm["signs"] if nm == "B1" else Xl
        for b in range(mults.shape[0]):
            co = solve(Z, y, w * mults[b], sysm["pen"], sysm["lb"], sysm["ub"])
            if co[1] > 0:
                E[b] = (Xuse * co[2] if nm == "B1" else Xuse @ co[2:]) / co[1]
    v = np.var(100.0 * float(w_skill) * E, axis=0, ddof=1)
    return {"mean_var_pp2": _rnd(float(v.mean()), 4), "median_var_pp2": _rnd(float(np.median(v)), 4),
            "rows": len(live_rows), "B": int(mults.shape[0])}


def board_for(R, side: str, head: dict | None, w_skill: float, rows: list[dict]) -> dict:
    """The live board under a production head at its weight against data/xfv.json."""
    import efv_v2_serve as S
    model = dict(R.served[side], skill=head, w_skill=float(w_skill), w_time=0.0,
                 w_skill_unscaled=float(w_skill), w_time_unscaled=0.0,
                 consensus_only=float(w_skill) <= 0 or not H.head_usable(head))
    preds = H.predict_v2(model, rows)
    parts = S._chip_parts(model, rows)
    order = sorted(range(len(preds)), key=lambda i: (-preds[i]["order_idx"], preds[i]["player_key"]))
    rank = {i: k + 1 for k, i in enumerate(order)}
    got = {r["player_key"]: {"grade": float(p["efv_grade"]), "order_idx": float(p["order_idx"]),
                             "fv": float(r["fv"]), "rank": rank[i], "chips": S.driver_chips(parts[i])[:6]}
           for i, (r, p) in enumerate(zip(rows, preds))}
    eff = RF.board_effect({side: got})[side]
    eff["top_movers"] = eff["top_movers"][:25]
    return eff


def production_reads(R, prod: dict, wall: dict, live: dict, carry: dict) -> dict:
    """A4 for every production head, the section 5 variance on the live board and the board
    effect of every configuration."""
    out = {}
    for key, pf in prod.items():
        nm, s = key.split("|")
        head = pf["head"]
        tr_x = pf.get("tr_x") or R.prod[s]["tr_x"]
        rows_live = pf.get("live") or live[s]["rows"]
        w = float(wall[nm][s]["w_skill"]) if nm != "S" else float(R.served[s]["w_skill"])
        blk = {"w_skill": _rnd(w, 5), "keys": list((head or {}).get("keys") or []),
               "nonzero": [k for k, b in slopes_of(head).items() if b != 0.0],
               "per_sd": ({k: _rnd(b / head["b_uc"], 5) for k, b in slopes_of(head).items()}
                          if head and head.get("b_uc") else {}),
               "lam": _rnd((head or {}).get("lam")), "rec": pf.get("rec")}
        if head is None or not head.get("keys"):
            blk["edf"] = {"edf_drivers": 0.0, "free_slopes": 0, "slopes": 0}
        elif nm == "D":
            blk["edf"] = pair_edf(head, tr_x, s)
        else:
            sysm = _head_system(nm, head, tr_x, s)
            co = np.concatenate([[head["b0"], head["b_uc"]],
                                 [head["scale"]] if nm == "B1" else head["beta"]])
            blk["edf"] = edf(sysm["Z"], sysm["Dz"]["w"], sysm["pen"], sysm["lb"], sysm["ub"], co)
        Dz = design_of(tr_x, (head or {}).get("keys") or R.served[s]["skill"]["keys"])
        pl = np.asarray([r["player_key"] for r in Dz["rows"]])
        mults = mult_draws(pl, B, SEED)
        blk["variance"] = live_variance(nm, head, w, tr_x, rows_live, s, mults)
        blk["board"] = board_for(R, s, head, w, rows_live) if nm != "S" else None
        out[key] = blk
        R.log(f"  production {key}: edf {blk['edf'].get('edf_drivers')}, "
              f"var {blk['variance'].get('mean_var_pp2')}")
    for s in SIDES:
        base = (out.get(f"S|{s}") or {}).get("variance", {}).get("mean_var_pp2")
        for key, blk in out.items():
            if key.endswith(f"|{s}") and base:
                blk["variance"]["ratio_to_S"] = _rnd((blk["variance"].get("mean_var_pp2") or 0.0) / base, 4)
    return out


def config_names() -> tuple[str, ...]:
    return ("S", "B1", "B2", "B3", "D")


def summarize(bt: dict) -> dict:
    return {n: {"pooled": _rnd(v[0], 5), "lv_dev": _rnd(v[1].get("lv_dev"), 5),
                "vm_dev": _rnd(v[1].get("vm_dev"), 5)} for n, v in bt["point"].items()}


def run_all(cache_dir: Path, work: Path, *, log=print) -> dict:
    BT, _B4 = _tools()
    t0 = time.time()
    R = Run(cache_dir, work, log=log)
    log("parity")
    par = R.cached("parity", R.parity)
    par_proc = R.cached("parity_procedure", R.parity_procedure)
    log(f"  {par} {par_proc}")
    clubs = R.cached("clubs", R.clubs)
    l6 = R.cached("l6", R.l6)
    live = R.cached("live", R.live)
    log("arm A")
    arm_a = R.cached("arm_a", lambda: R.arm_a(clubs))

    # the fold fits of every configuration on the real rows
    fits = {"S": {c["fold_id"]: {"head": c["model"].get("skill"), "rec": {"cached": True}}
                  for c in R.ctx}}
    for nm in ("B1", "B2", "B3", "D"):
        log(f"configuration {nm}")
        fits[nm] = R.cached(f"fits_{nm}", lambda nm=nm: R.fit_config(nm, R.ctx))

    # arm C: the shift, then the carrying keys' re-standardized configuration
    raw = {s: V5C._raw_by_side()[s] for s in SIDES}
    season_of = {s: make_season_of(raw[s], int(V5C.live_read(LIVE_DAY)["season"])) for s in SIDES}
    shift = {}
    for s in SIDES:
        extra = universe_of(s, list(R.served[s]["skill"].get("v2_keys") or [])) + \
            [k for k in ("tool_hit",) if s == "hit"]
        shift[s] = shift_read(R.prod[s]["tr_x"], live[s]["rows"], R.served[s]["skill"], s,
                              sorted(set(extra)))
    carry = {s: shift[s]["carrying"] for s in SIDES}
    log(f"  carrying keys: {carry}")
    if any(carry.values()):
        def fit_c():
            out = {}
            for s in SIDES:
                if not carry[s]:
                    continue
                out.update(R.fit_config("C", [c for c in R.ctx if c["side"] == s], carry=carry,
                                        season_of=season_of[s]))
            return out
        fits["C"] = R.cached("fits_C", fit_c)

    # orders, weights and the read
    packs = {nm: R.packs_of(f, [c for c in R.ctx if c["fold_id"] in f]) for nm, f in fits.items()}
    scored = {s: Scored(R.b1, s, clubs["scored"], l6) for s in SIDES}
    wcf = {nm: weights_cf(pk) for nm, pk in packs.items()}
    wall = {nm: weights_all(pk) for nm, pk in packs.items()}
    reads, served_const = {}, {}
    for s in SIDES:
        sc = scored[s]
        orders = {"K": sc.consensus(packs["S"])}
        for nm, pk in packs.items():
            if any(p["side"] == s for p in pk):
                orders[nm] = sc.order(pk, wcf[nm])
        const = {nm: sc.order(pk, None, const=float(R.served[s]["w_skill"]))
                 for nm, pk in packs.items() if any(p["side"] == s for p in pk)}
        log(f"  bootstrap {s} ({len(orders)} orders)")
        bt = {nm: boot(orders, sc.y, sc.codes, sc.frame, cl, B=B, seed=sd)
              for nm, cl, sd in (("player", sc.player, SEED), ("club", sc.club, SEED + 1))}
        reads[s] = {"orders": orders, "bt": bt}
        btc = boot(const, sc.y, sc.codes, sc.frame, sc.player, B=B, seed=SEED)
        served_const[s] = {"points": summarize(btc),
                           "deltas": {nm: diff(btc, nm, "S") for nm in const if nm != "S"}}

    # the planted check (section 3)
    planted = {}
    for s in SIDES:
        log(f"planted {s}")

        def plant(s=s):
            pctx, py, prec = planted_contexts(R, s)
            pf = {"S": R.fit_config("S", pctx)}
            pctx = [dict(c, model={"skill": pf["S"][c["fold_id"]]["head"],
                                   "config": {"lam": {"skill": (pf["S"][c["fold_id"]]["head"] or {}).get("lam")}}})
                    for c in pctx]
            for nm in tuple(n for n in fits if n != "S"):
                if nm == "C":
                    if not carry[s]:
                        continue
                    pf[nm] = R.fit_config("C", pctx, carry=carry, season_of=season_of[s])
                else:
                    pf[nm] = R.fit_config(nm, pctx)
            return pctx, py, prec, pf
        pctx, py, prec, pf = R.cached(f"planted_{s}", plant)
        sc = scored[s]
        yp = np.asarray([py[k] for k in sc.keys])
        ppk = {nm: R.packs_of(f, [c for c in pctx if c["fold_id"] in f]) for nm, f in pf.items()}
        pw = {nm: weights_cf(pk) for nm, pk in ppk.items()}
        po = {"K": sc.consensus(ppk["S"])}
        for nm, pk in ppk.items():
            po[nm] = sc.order(pk, pw[nm])
        bt = boot(po, yp, sc.codes, sc.frame, sc.player, B=B, seed=SEED + 5)
        sk = diff(bt, "S", "K")
        planted[s] = {"receipt": prec, "points": summarize(bt), "S_vs_K": sk,
                      "recovers": bool(sk.get("lower95_one_sided") is not None
                                       and sk["lower95_one_sided"] > 0),
                      "arms": {nm: {"vs_S": diff(bt, nm, "S"), "vs_K": diff(bt, nm, "K")}
                               for nm in po if nm not in ("S", "K")}}

    # the six-season WAR secondary (arm D) and the re-fit's own secondaries
    secondary = {}
    for s in SIDES:
        sc = scored[s]
        mask = np.isfinite(sc.l6)
        o = {k: v for k, v in reads[s]["orders"].items() if k in ("S", "D", "K")}
        bt6 = boot(o, np.where(mask, sc.l6, 0.0), sc.codes, sc.frame, sc.player, B=B, seed=SEED + 6,
                   mask=mask)
        sec = {"l6": {"n": int(mask.sum()), "points": summarize(bt6),
                      "D_vs_S": diff(bt6, "D", "S") if "D" in o else None,
                      "S_vs_K": diff(bt6, "S", "K")}}
        sec["map"] = {}
        for nm in reads[s]["orders"]:
            if nm in ("S", "K"):
                continue
            rows = [dict(c, group=str(code), grades=dict(c["grades"], _a=float(reads[s]["orders"][nm][i]),
                                                       _s=float(reads[s]["orders"]["S"][i])))
                    for i, (c, code) in enumerate(zip(sc.rows, sc.codes))]
            sec["map"][nm] = {f: {st: RF._keep(BT.paired([r for r, fr in zip(rows, sc.frame) if fr == f],
                                                         "_a", "_s", st, B=B, seed=SEED))
                                  for st in ("pooled", "auc")} for f in ("lv_dev", "vm_dev")}
        secondary[s] = sec

    # production fits of every configuration (A4, section 5 variance, C shift after, board)
    def prod_fits():
        out = {}
        for nm in fits:
            for s in SIDES:
                if nm == "C" and not carry[s]:
                    continue
                if nm == "S":
                    out[f"{nm}|{s}"] = {"head": R.served[s]["skill"], "rec": {"stored": True}}
                    continue
                pc = R.prod[s]
                if nm == "C":
                    tr2, lv2, rrec = restd_live(pc["tr_x"], live[s]["rows"], carry[s], season_of[s])
                    out[f"{nm}|{s}"] = {"head": served_skill(tr2, s, "vm"), "rec": {"restd": rrec},
                                        "tr_x": tr2, "live": lv2}
                else:
                    out[f"{nm}|{s}"] = R.fit_config(nm, [pc])[pc["fold_id"]]
        return out
    prod = R.cached("production_fits", prod_fits)
    shift_after = {}
    for s in SIDES:
        pf = prod.get(f"C|{s}")
        if pf and pf["head"] is not None and pf["head"].get("keys"):
            sa = shift_read(pf["tr_x"], pf["live"], pf["head"], s, [])
            shift_after[s] = {"cv_auc_before": shift[s]["cv_auc"], "cv_auc_after": sa["cv_auc"],
                              "in_sample_auc_before": shift[s]["in_sample_auc"],
                              "in_sample_auc_after": sa["in_sample_auc"], "keys": sa["keys"]}
    production = R.cached("production_reads", lambda: production_reads(R, prod, wall, live, carry))

    # adoption (section 8)
    tests = {}
    verdict = {}
    for s in SIDES:
        bt = reads[s]["bt"]
        verdict[s] = {}
        for nm in ARMS:
            if nm not in reads[s]["orders"]:
                verdict[s][nm] = {"read": False, "why": "no configuration (no key carries the shift)"
                                  if nm == "C" else "not read"}
                continue
            dp, dc = diff(bt["player"], nm, "S"), diff(bt["club"], nm, "S")
            kk = diff(bt["player"], nm, "K")
            p = max(dp.get("p_noninferior") or 1.0, dc.get("p_noninferior") or 1.0)
            tests[f"{s}|{nm}"] = p
            lbp, lbc = dp.get("lower95_one_sided"), dc.get("lower95_one_sided")
            verdict[s][nm] = {"read": True, "vs_S_player": dp, "vs_S_club": dc, "vs_K": kk, "p": p,
                              "lower_bounds_clear": bool(lbp is not None and lbc is not None
                                                         and lbp > -MARGIN and lbc > -MARGIN)}
    hm = holm(tests)
    adopted = {}
    for s in SIDES:
        rec = planted[s]["recovers"]
        for nm, v in verdict[s].items():
            if not v.get("read"):
                continue
            h = hm[f"{s}|{nm}"]
            pts = reads[s]["bt"]["player"]["point"]
            not_below_k = bool(pts[nm][0] is not None and pts["K"][0] is not None
                               and pts[nm][0] >= pts["K"][0])
            why = []
            extra = True
            if nm == "C":
                sa = shift_after.get(s) or {}
                extra = bool(sa.get("cv_auc_after") is not None and sa.get("cv_auc_before") is not None
                             and sa["cv_auc_after"] < sa["cv_auc_before"])
                v["shift_falls"] = extra
                if not extra:
                    why.append("the shift does not fall")
            if nm == "D":
                d6 = (secondary[s]["l6"].get("D_vs_S") or {})
                hi6 = (d6.get("ci95") or [None, None])[1]
                extra = bool(d6.get("delta") is not None and d6["delta"] >= -MARGIN
                             and hi6 is not None and hi6 >= 0)
                v["six_season_holds"] = extra
                if not extra:
                    why.append("loses on the six-season WAR secondary")
            v.update(holm=h, not_below_consensus=not_below_k, planted_recovers=rec)
            v["passes"] = bool(h["rejects"] and v["lower_bounds_clear"] and not_below_k and rec and extra)
            if not h["rejects"]:
                why.insert(0, "non-inferiority not established after Holm")
            if not v["lower_bounds_clear"]:
                why.append("a one-sided lower bound at or below -0.005")
            if not not_below_k:
                why.append("trails consensus-only")
            if not rec:
                why.append("the planted check does not recover on this side")
            v["why_not"] = why
        passing = [nm for nm in ADOPT_ORDER if verdict[s].get(nm, {}).get("passes")]
        adopted[s] = passing[0] if passing else None
        verdict[s]["passing"] = passing
    doc = {"schema": 1, "item": ITEM, "produced_by": TOOL, "role": "development", "adjudicates": False,
           "doc": DOC, "owner_decision": "EW3-49 (2026-10-22)", "label": R.p0.get("label"),
           "B": B, "seed": SEED, "margin": MARGIN, "holm_alpha": HOLM_ALPHA,
           "parity": {"stored_heads": par, "procedure": par_proc},
           "live_board": {s: {"n": live[s]["n"], "parity": live[s]["parity"], "day": LIVE_DAY} for s in SIDES},
           "clubs": {"scored_rows": len(clubs["scored"]),
                     "scored_solo": sum(1 for v in clubs["scored"].values() if v.startswith("solo:")),
                     "production_rows": len(clubs["prod"]),
                     "production_solo": sum(1 for v in clubs["prod"].values() if v.startswith("solo:"))},
           "arm_a": arm_a, "shift": shift, "carrying": carry,
           "fits": {nm: {fid: v["rec"] for fid, v in f.items()} for nm, f in fits.items() if nm != "S"},
           "weights_cross_fitted": {nm: {s: {fid: {k: _rnd(w.get(k), 5) for k in ("w_skill", "w_skill_ratio")}
                                             for fid, w in v.items()} for s, v in wc.items()}
                                    for nm, wc in wcf.items()},
           "weights_pooled": {nm: {s: {k: _rnd(w.get(k), 5) for k in ("w_skill", "w_skill_ratio", "n")}
                                   for s, w in wa.items()} for nm, wa in wall.items()},
           "reads": {s: {"points": summarize(reads[s]["bt"]["player"]),
                         "clusters": {nm: reads[s]["bt"][nm]["n_clusters"] for nm in ("player", "club")},
                         "S_vs_K": {nm: diff(reads[s]["bt"][nm], "S", "K") for nm in ("player", "club")},
                         "n": scored[s].n} for s in SIDES},
           "served_constant_weights": served_const, "planted": planted, "secondary": secondary,
           "shift_after": shift_after, "production": production,
           "verdict": verdict, "holm": hm, "adopted": adopted, "elapsed_s": round(time.time() - t0, 1)}
    R._save("doc_core", (doc, packs, fits, wall, prod))
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--cache", default=None, help="the re-fit's cache (build1, packs_RT, phase0)")
    ap.add_argument("--work", default=None, help="a scratch directory for resumable parts")
    a = ap.parse_args(argv)
    BT, _B4 = _tools()

    def log(msg):
        print(msg, flush=True)
    if a.run:
        if OUT_PATH.exists():
            log(f"refused: {OUT_PATH} exists; the registered read runs once")
            return 2
        if not (a.cache and a.work):
            log("refused: --cache and --work are needed")
            return 2
        doc = run_all(Path(a.cache), Path(a.work), log=log)
        doc["code"] = {"commit": BT._commit(), "tool": TOOL, "tool_sha256": BT._sha(ROOT / TOOL),
                       "doc": DOC, "doc_sha256": BT._sha(ROOT / DOC)}
        doc["generated_at"] = BT._now()
        BT.write_doc(doc, OUT_PATH)
        log(f"wrote {OUT_PATH}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
