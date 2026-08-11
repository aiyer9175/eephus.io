# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE C2 (master plan 2026-08-07b): fit, gate and PREPARE the served eFV outcome
distribution recalibration. SHIPS NOTHING.

Pre-registration: docs/efv-2026-08-07b/DISTRIBUTION_RECALIBRATION_GATE.md sections 0-5,
written in full before this file existed. Artifact: data/xfv_dist_recalibration_eval.json.

Run:  python tools/efv_dist_recalibration_lab.py
      python tools/efv_dist_recalibration_lab.py --quick   (small B, smoke test only)
      python tools/efv_dist_recalibration_lab.py --idr     (LANE B-L5, see below)

Writes ONLY data/xfv_dist_recalibration_eval.json. Touches no served artifact, no config,
no test, and no module outside tools/.

-------------------------------------------------------------------------------
LANE B-L5 (2026-08-10) added the `--idr` entry point and the IDR / EasyUQ block.
It MERGES `lane_b_l5_idr_easyuq` into the same artifact and rewrites no other key.
Everything from the original C2 run is preserved byte-for-byte and is a RECORD of a
DIFFERENT frame vintage; see `lane_b_l5_idr_easyuq.frame` for the B-L5 basis.
-------------------------------------------------------------------------------
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Scratch. This used to be a hard-coded per-session agent scratchpad directory, which went
# stale the moment that session ended and silently pointed the cache at a directory nobody
# would ever look in again. Resolved from the environment with a stable temp fallback so it
# cannot rot: set EFV_LAB_SCRATCH to override. Nothing here is a repo path (rule 7).
SCRATCH = Path(os.environ.get("EFV_LAB_SCRATCH")
               or (Path(tempfile.gettempdir()) / "efv_dist_recal_lab"))
FRAME_CACHE = SCRATCH / "c2_frame.json"
OUT = ROOT / "data" / "xfv_dist_recalibration_eval.json"

SEED = 20260808
BUCKETS = ("bust", "bench", "regular", "good", "star")
EPS = 1e-6

# --- thresholds this gate ADDS (pre-registered in the doc, section 2.3 / 4.1) ---
MIN_RECAL_TRAIN = 150
CTRL_SHARE_BAR = 0.80
PERM_ALPHA = 0.05
BONF_K = 5
Z95 = 1.645
Z_BONF = 2.326
# diagnostic only (doc section 3)
WAR_REPS = np.array([0.25, 1.00, 2.00, 3.25, 5.00])


# =============================================================================
# 1. FRAME. Exact mirror of efv_reliability._oof_rows plus the provisional flag.
# =============================================================================
def build_frame(force: bool = False) -> list[dict]:
    if FRAME_CACHE.exists() and not force:
        return json.loads(FRAME_CACHE.read_text(encoding="utf-8"))
    import value_framework as vf
    import efv_odds_calibration as _odds_cal
    import efv_reliability as er
    from efv_dataset import matrix_path, TARGET_SEASONS
    from efv_model import _prep, _feature_spec
    from efv_score import _age_at, _grade_map_age
    from prospect_path import _fit_ridge, _predict, _fit_linear_calibration

    out: list[dict] = []
    for side in ("hit", "pit"):
        is_pit = side == "pit"
        keys, _mono = _feature_spec(side)
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
                and not (r["kind"] == "bust" and r.get("bust_recent"))]
        data = _prep(pool, "target_censored", side)
        by_key = {r["player_key"]: r for r in pool}
        for yr in er.CHAIN_YEARS:
            tr = [r for r in data if r["decision_year"] < yr]
            te = [r for r in data if r["decision_year"] == yr]
            if len(te) < er.MIN_TEST or len(tr) < er.MIN_TRAIN:
                continue
            ridge = _fit_ridge(tr, keys)
            if not ridge:
                continue
            cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"])
                                           for r in tr])
            a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            for r in te:
                src = by_key[r["player_key"]]
                xfv_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
                dyear = src.get("debut_year") or 2020
                age = _age_at(src.get("birth_date"), dyear)
                pos = src.get("position")
                _gm_age = _grade_map_age(age, 0.0)
                grade = vf.realized_implied_fv(xfv_war, is_pit, age=_gm_age, position=pos,
                                               exposure_seasons=TARGET_SEASONS)
                if grade is None:
                    continue
                probs = vf.p_bucket_given_fv(grade, is_pit)
                if not probs or len(probs) != 5:
                    continue
                provisional = not src.get("milb")
                after = _odds_cal.recalibrate_bucket(probs, is_pit, provisional=provisional)
                out.append({
                    "player_key": r["player_key"], "side": side, "decision_year": yr,
                    "fv": float(r["fv"]), "odds_grade": float(grade),
                    "provisional": bool(provisional),
                    "p_raw": [float(x) for x in probs],
                    "p_ship": [float(x) for x in after],
                    "y": int(er._realized_bucket(r["target"])),
                    "target": float(r["target"]),
                    "weight": float(r["weight"]),
                })
    SCRATCH.mkdir(parents=True, exist_ok=True)
    FRAME_CACHE.write_text(json.dumps(out), encoding="utf-8")
    return out


# =============================================================================
# 2. THE FAMILY. Cumulative-logit Platt, doc section 2.2.
# =============================================================================
def _logit(p):
    p = np.clip(p, EPS, 1.0 - EPS)
    return np.log(p / (1.0 - p))


def _sig(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40.0, 40.0)))


def _surv(P):
    """S[:,k-1] = P(Y >= k) for k = 1..4."""
    return np.cumsum(P[:, ::-1], axis=1)[:, ::-1][:, 1:]


def apply_map(P, A, B):
    S = _surv(np.asarray(P, dtype=float))
    S2 = _sig(np.asarray(A, dtype=float) + np.asarray(B, dtype=float) * _logit(S))
    S2 = np.minimum.accumulate(S2, axis=1)
    S2 = np.clip(S2, EPS, 1.0 - EPS)
    n = S2.shape[0]
    Q = np.empty((n, 5))
    Q[:, 0] = 1.0 - S2[:, 0]
    Q[:, 1] = S2[:, 0] - S2[:, 1]
    Q[:, 2] = S2[:, 1] - S2[:, 2]
    Q[:, 3] = S2[:, 2] - S2[:, 3]
    Q[:, 4] = S2[:, 3]
    Q = np.clip(Q, EPS, None)
    return Q / Q.sum(axis=1, keepdims=True)


def apply_prop(P, a, b):
    """ARM-5b, the INCUMBENT's actual family: Platt the bust mass and rescale the four
    non-bust buckets PROPORTIONALLY, i.e. S'_k = S_k * S'_1 / S_1 for k >= 2. This is what
    efv_odds_calibration.recalibrate_bucket does. See the section 6 disclosure: the gate
    doc described ARM-5 as 'thresholds 2 to 4 held at identity' AND as 'the incumbent's own
    family', and those are two different maps. ARM-5 is run exactly as registered; ARM-5b
    is the faithful one, added after the primary run."""
    P = np.asarray(P, dtype=float)
    S1 = np.clip(_surv(P)[:, 0], EPS, 1.0 - EPS)
    S1n = np.clip(_sig(a + b * _logit(S1)), EPS, 1.0 - EPS)
    Q = np.empty_like(P)
    Q[:, 0] = 1.0 - S1n
    Q[:, 1:] = P[:, 1:] * (S1n / S1)[:, None]
    Q = np.clip(Q, EPS, None)
    return Q / Q.sum(axis=1, keepdims=True)


_MODES = {
    # mode -> unpack(theta) -> (A, B)
    "shared":    lambda t: (np.repeat(t[0], 4), np.repeat(t[1], 4)),
    "perthr":    lambda t: (t[0::2].copy(), t[1::2].copy()),
    "level":     lambda t: (t.copy(), np.ones(4)),
    "bust_only": lambda t: (np.array([t[0], 0.0, 0.0, 0.0]),
                            np.array([t[1], 1.0, 1.0, 1.0])),
}
_INIT = {"shared": [0.0, 1.0], "perthr": [0.0, 1.0] * 4, "level": [0.0] * 4,
         "bust_only": [0.0, 1.0], "incumbent_prop": [0.0, 1.0]}
_BOUNDS = {"shared": [(-8, 8), (0.01, 5)], "perthr": [(-8, 8), (0.01, 5)] * 4,
           "level": [(-8, 8)] * 4, "bust_only": [(-8, 8), (0.01, 5)],
           "incumbent_prop": [(-8, 8), (0.01, 5)]}


def _apply(P, theta, mode: str):
    t = np.asarray(theta, dtype=float)
    if mode == "incumbent_prop":
        return apply_prop(P, float(t[0]), float(t[1]))
    A, B = _MODES[mode](t)
    return apply_map(P, A, B)


def fit_map(P, y, mode: str):
    """Maximum multinomial likelihood fit. Returns the free parameter vector."""
    from scipy.optimize import minimize
    P = np.asarray(P, dtype=float)
    y = np.asarray(y, dtype=int)

    def nll(theta):
        Q = _apply(P, theta, mode)
        return -float(np.mean(np.log(Q[np.arange(len(y)), y])))

    res = minimize(nll, np.array(_INIT[mode], dtype=float), method="L-BFGS-B",
                   bounds=_BOUNDS[mode])
    return np.asarray(res.x, dtype=float)


# =============================================================================
# 3. METRICS. Shipped functions where they exist.
# =============================================================================
def bust_ece(P, y, n_bins: int = 10) -> float:
    """Fast mirror of efv_reliability._reliability_bins ECE for the bust bucket."""
    p = np.asarray(P, dtype=float)[:, 0]
    yy = (np.asarray(y, dtype=int) == 0).astype(float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    N = len(p)
    ece = 0.0
    for i in range(n_bins):
        m = (p >= edges[i]) & ((p < edges[i + 1]) if i < n_bins - 1 else (p <= 1.0))
        c = int(m.sum())
        if c < 5:
            continue
        ece += (c / N) * abs(float(p[m].mean()) - float(yy[m].mean()))
    return float(ece)


def bucket_ece(P, y, b: int, n_bins: int = 10) -> float:
    p = np.asarray(P, dtype=float)[:, b]
    yy = (np.asarray(y, dtype=int) == b).astype(float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    N = len(p)
    ece = 0.0
    for i in range(n_bins):
        m = (p >= edges[i]) & ((p < edges[i + 1]) if i < n_bins - 1 else (p <= 1.0))
        c = int(m.sum())
        if c < 5:
            continue
        ece += (c / N) * abs(float(p[m].mean()) - float(yy[m].mean()))
    return float(ece)


def tier_table(P, y, fv, min_n: int = 15):
    P = np.asarray(P, dtype=float)
    y = np.asarray(y, dtype=int)
    t = np.rint(np.asarray(fv, dtype=float) / 5.0).astype(int) * 5
    out = {}
    for tk in sorted(set(t.tolist())):
        m = t == tk
        n = int(m.sum())
        if n < min_n:
            continue
        freq = np.zeros(5)
        for b in range(5):
            freq[b] = float((y[m] == b).mean())
        mb = P[m].mean(axis=0)
        out[int(tk)] = {"n": n, "gap": float(np.mean(np.abs(mb - freq))),
                        "realized_freq": {BUCKETS[b]: round(float(freq[b]), 4) for b in range(5)},
                        "mean_p": {BUCKETS[b]: round(float(mb[b]), 4) for b in range(5)}}
    return out


def tier_gap_weighted(P, y, fv, min_n: int = 15) -> float:
    tt = tier_table(P, y, fv, min_n)
    if not tt:
        return float("nan")
    num = sum(v["gap"] * v["n"] for v in tt.values())
    den = sum(v["n"] for v in tt.values())
    return float(num / den)


def _floor(vals, point):
    """Bootstrap floor on a delta. HOISTED to module level 2026-08-10 (it was nested inside
    main); body unchanged, it closed over nothing but module constants. Lane B-L5 calls it
    through _floor95 so both lanes share ONE floor implementation."""
    v = np.asarray([x for x in vals if np.isfinite(x)], dtype=float)
    sd = float(v.std(ddof=1))
    return {"B": int(len(v)), "sd": round(sd, 6),
            "mde95_onesided": round(Z95 * sd, 6),
            "mde_bonferroni_k5": round(Z_BONF * sd, 6),
            "point_delta": round(float(point), 6),
            "margin_over_floor": round(float(point) / (Z95 * sd), 4) if sd > 0 else None,
            "margin_over_bonferroni": round(float(point) / (Z_BONF * sd), 4) if sd > 0 else None,
            "clears": bool(float(point) > Z95 * sd),
            "clears_bonferroni": bool(float(point) > Z_BONF * sd),
            "boot_mean": round(float(v.mean()), 6),
            "ci95": [round(float(np.percentile(v, 2.5)), 6),
                     round(float(np.percentile(v, 97.5)), 6)]}


def logscore(P, y) -> float:
    P = np.asarray(P, dtype=float)
    y = np.asarray(y, dtype=int)
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-12, None))))


def brier(P, y) -> float:
    P = np.asarray(P, dtype=float)
    Y = np.zeros_like(P)
    Y[np.arange(len(y)), np.asarray(y, dtype=int)] = 1.0
    return float(np.mean(np.sum((P - Y) ** 2, axis=1)))


def war_mae(P, target) -> float:
    P = np.asarray(P, dtype=float)
    ev = P @ WAR_REPS
    return float(np.mean(np.abs(ev - np.asarray(target, dtype=float) / 6.0)))


def rel_slope(P, y, b: int = 0):
    """IRLS logistic fit of 1{y==b} on logit(p_b). Ideal (intercept 0, slope 1)."""
    x = _logit(np.asarray(P, dtype=float)[:, b])
    t = (np.asarray(y, dtype=int) == b).astype(float)
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(2)
    for _ in range(60):
        eta = X @ beta
        mu = _sig(eta)
        w = np.clip(mu * (1 - mu), 1e-9, None)
        z = eta + (t - mu) / w
        WX = X * w[:, None]
        try:
            new = np.linalg.solve(X.T @ WX, WX.T @ z)
        except np.linalg.LinAlgError:
            break
        if np.max(np.abs(new - beta)) < 1e-9:
            beta = new
            break
        beta = new
    return float(beta[0]), float(beta[1])


def bias_table(P, y, fv):
    P = np.asarray(P, dtype=float)
    y = np.asarray(y, dtype=int)
    fv = np.asarray(fv, dtype=float)
    t = np.rint(fv / 5.0).astype(int) * 5

    def _b(mask):
        if mask.sum() == 0:
            return None
        d = {}
        for b in range(5):
            d[BUCKETS[b]] = round(float(P[mask][:, b].mean() - (y[mask] == b).mean()), 5)
        gs = float(P[mask][:, 3:].sum(axis=1).mean() - np.isin(y[mask], (3, 4)).mean())
        d["good_plus_star"] = round(gs, 5)
        d["n"] = int(mask.sum())
        return d

    return {"pooled": _b(np.ones(len(y), dtype=bool)),
            "tier_le_45": _b(t <= 45), "tier_ge_50": _b(t >= 50)}


def m5t(P, y, fv) -> float:
    """M5T: good+star held-out bias in the tier >= 50 band (signed)."""
    P = np.asarray(P, dtype=float)
    y = np.asarray(y, dtype=int)
    t = np.rint(np.asarray(fv, dtype=float) / 5.0).astype(int) * 5
    m = t >= 50
    return float(P[m][:, 3:].sum(axis=1).mean() - np.isin(y[m], (3, 4)).mean())


# =============================================================================
# 4. FORWARD-CHAINED SCORING
# =============================================================================
def chain_score(frame, mode, *, perm_rng=None, marginal=False):
    """Forward-chained recalibration. Returns (idx, Q) for the evaluable rows.

    `mode` selects the family; `marginal=True` runs ARM-4 (train-fold pooled marginal);
    `perm_rng` runs the permuted-tier twin (predicted vectors shuffled within the train
    fold, per side, test rows untouched)."""
    P = np.array([r["p_raw"] for r in frame])
    y = np.array([r["y"] for r in frame])
    yr = np.array([r["decision_year"] for r in frame])
    sd = np.array([r["side"] for r in frame])
    pv = np.array([r["provisional"] for r in frame])
    idx_out, Q_out, folds = [], [], {}
    for side in ("hit", "pit"):
        s_mask = sd == side
        for t in sorted(set(yr[s_mask].tolist())):
            tr = np.where(s_mask & (yr < t) & ~pv)[0]
            te = np.where(s_mask & (yr == t))[0]
            if len(tr) < MIN_RECAL_TRAIN or len(te) == 0:
                continue
            folds.setdefault(side, []).append(int(t))
            Ptr = P[tr]
            ytr = y[tr]
            if perm_rng is not None:
                Ptr = Ptr[perm_rng.permutation(len(tr))]
            te_np = te[~pv[te]]
            te_pv = te[pv[te]]
            if marginal:
                marg = np.array([(ytr == b).mean() for b in range(5)])
                marg = np.clip(marg, EPS, None)
                marg = marg / marg.sum()
                Qn = np.tile(marg, (len(te_np), 1))
            else:
                Qn = _apply(P[te_np], fit_map(Ptr, ytr, mode), mode)
            if len(te_np):
                idx_out.append(te_np)
                Q_out.append(Qn)
            if len(te_pv):
                idx_out.append(te_pv)
                Q_out.append(P[te_pv])
    if not idx_out:
        return np.array([], dtype=int), np.zeros((0, 5)), folds
    idx = np.concatenate(idx_out)
    Q = np.vstack(Q_out)
    o = np.argsort(idx, kind="stable")
    return idx[o], Q[o], folds


REFIT_JSONL = SCRATCH / "c2_refit_draws.jsonl"


def _read_refit_draws() -> dict:
    out: dict = {}
    if not REFIT_JSONL.exists():
        return out
    for ln in REFIT_JSONL.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except json.JSONDecodeError:
            continue
        out[int(d["i"])] = d
    return out


def refit_chunk(frame, indices) -> None:
    """One restricted-E_refit draw per index, appended to REFIT_JSONL. Draw i is seeded
    from SEED*1000 + i so chunking is equivalent to a single pass."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    n = len(frame)
    with REFIT_JSONL.open("a", encoding="utf-8") as fh:
        for i in indices:
            r = np.random.default_rng(SEED * 1000 + int(i))
            boot = [frame[j] for j in r.integers(0, n, n)]
            try:
                ib, Qb, _ = chain_score(boot, "perthr")
            except Exception:                                   # noqa: BLE001
                continue
            if len(ib) == 0:
                continue
            yb = np.array([boot[j]["y"] for j in ib])
            fvb = np.array([boot[j]["fv"] for j in ib])
            Qa = np.array([boot[j]["p_ship"] for j in ib])
            fh.write(json.dumps({
                "i": int(i),
                "M1": bust_ece(Qa, yb) - bust_ece(Qb, yb),
                "M2": tier_gap_weighted(Qa, yb, fvb) - tier_gap_weighted(Qb, yb, fvb),
                "M5T": abs(m5t(Qa, yb, fvb)) - abs(m5t(Qb, yb, fvb))}) + "\n")
            fh.flush()


def fit_full(frame, mode):
    """Production fit: the whole out-of-fold frame, non-provisional rows, per side."""
    out = {}
    for side in ("hit", "pit"):
        rows = [r for r in frame if r["side"] == side and not r["provisional"]]
        P = np.array([r["p_raw"] for r in rows])
        y = np.array([r["y"] for r in rows])
        theta = fit_map(P, y, mode)
        rec = {"theta": [round(float(v), 6) for v in theta], "n_fit": len(rows)}
        if mode != "incumbent_prop":
            A, B = _MODES[mode](theta)
            rec["A"] = [round(float(a), 6) for a in A]
            rec["B"] = [round(float(b), 6) for b in B]
        out[side] = rec
    return out


# =============================================================================
# 5. MAIN
# =============================================================================
def main(quick: bool = False):
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    frame = build_frame()
    P_raw = np.array([r["p_raw"] for r in frame])
    P_ship = np.array([r["p_ship"] for r in frame])
    y_all = np.array([r["y"] for r in frame])
    fv_all = np.array([r["fv"] for r in frame])
    tgt_all = np.array([r["target"] for r in frame])

    rep = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_dist_recalibration_lab.py",
        "registration": ("docs/efv-2026-08-07b/DISTRIBUTION_RECALIBRATION_GATE.md "
                         "sections 0-5, written in full BEFORE this lab existed; "
                         "section 6 is a placeholder filled after the run"),
        "lane": "C2 (master plan 2026-08-07b)",
        "scope_note": ("FITS and GATES a recalibration and PREPARES a re-anchor. "
                       "Ships nothing. Writes no config, no test, no served artifact."),
        "seed": SEED,
        "self_added_thresholds": {
            "MIN_RECAL_TRAIN": MIN_RECAL_TRAIN,
            "ctrl_share_bar": CTRL_SHARE_BAR,
            "perm_alpha": PERM_ALPHA,
            "bonferroni_k": BONF_K,
            "z95_onesided": Z95,
            "war_representatives": WAR_REPS.tolist(),
            "note": ("the master plan names no numeric bar for this lane; every value "
                     "here was fixed in the gate doc before the lab existed"),
        },
    }

    # --- 4.0 stop condition: frame reproduces the shipped monitor -------------
    ship = json.loads((ROOT / "data" / "xfv_reliability.json").read_text(encoding="utf-8"))
    mirror_ece = bust_ece(P_ship, y_all)
    rep["stop_conditions"] = {"mirror_reproduces_shipped": {
        "shipped_bust_ece": ship["tripwire"]["bust_ece"],
        "shipped_pooled_n": ship["pooled_n"],
        "mirror_bust_ece": round(mirror_ece, 5),
        "mirror_n": len(frame),
        "abs_delta": round(abs(mirror_ece - ship["tripwire"]["bust_ece"]), 5),
        "pass": abs(mirror_ece - ship["tripwire"]["bust_ece"]) <= 0.005}}

    # metric-implementation cross-check against the SHIPPED functions
    import efv_reliability as er
    shipped_rows = [{"p": P_ship[i], "y": int(y_all[i]), "fv": float(fv_all[i])}
                    for i in range(len(frame))]
    shipped_bins = er._reliability_bins(shipped_rows, key="p")
    shipped_tiers = er._tier_reliability(shipped_rows, key="p")
    sgap = (sum(v["gap"] * v["n"] for v in shipped_tiers.values())
            / sum(v["n"] for v in shipped_tiers.values()))
    rep["stop_conditions"]["metric_impl_matches_shipped_fn"] = {
        "shipped_fn_bust_ece": shipped_bins["bust"]["ece"],
        "lab_bust_ece": round(mirror_ece, 5),
        "shipped_fn_tier_gap_weighted": round(float(sgap), 5),
        "lab_tier_gap_weighted": round(tier_gap_weighted(P_ship, y_all, fv_all), 5),
        "pass": (abs(shipped_bins["bust"]["ece"] - mirror_ece) < 1e-4
                 and abs(sgap - tier_gap_weighted(P_ship, y_all, fv_all)) < 1e-4)}

    rep["frame"] = {
        "n_rows": len(frame),
        "n_by_side": {s: sum(1 for r in frame if r["side"] == s) for s in ("hit", "pit")},
        "n_provisional": int(sum(1 for r in frame if r["provisional"])),
        "chain_years": sorted({r["decision_year"] for r in frame}),
        "note": ("exact mirror of efv_reliability._oof_rows plus the provisional flag; "
                 "provisional rows receive NO map from ANY arm, matching "
                 "recalibrate_bucket's hard no-op"),
    }

    # --- run the arms --------------------------------------------------------
    arms = {}
    idx2, Q2, folds2 = chain_score(frame, "perthr")
    arms["arm2_perthr"] = (idx2, Q2)
    common = idx2
    rep["frame"]["evaluable_n"] = int(len(common))
    rep["frame"]["evaluable_folds"] = {k: v for k, v in folds2.items()}
    rep["frame"]["evaluable_years"] = sorted({int(frame[i]["decision_year"]) for i in common})
    rep["frame"]["evaluable_provisional"] = int(sum(1 for i in common if frame[i]["provisional"]))

    for name, mode in (("arm1_shared", "shared"), ("arm3_level", "level"),
                       ("arm5_bust_only_refit", "bust_only"),
                       ("arm5b_incumbent_family_refit_POSTHOC", "incumbent_prop")):
        i_, q_, _ = chain_score(frame, mode)
        assert np.array_equal(i_, common), f"{name} frame mismatch"
        arms[name] = (i_, q_)
    i4, q4, _ = chain_score(frame, "perthr", marginal=True)
    assert np.array_equal(i4, common)
    arms["arm4_marginal_constant"] = (i4, q4)
    arms["arm0_shipped"] = (common, P_ship[common])
    arms["raw_no_map"] = (common, P_raw[common])

    y = y_all[common]
    fv = fv_all[common]
    tgt = tgt_all[common]
    prov_mask = np.array([frame[i]["provisional"] for i in common])

    # --- 4.0 validity stop conditions ---------------------------------------
    valid = {"pass": True, "detail": {}}
    for name, (_, Q) in arms.items():
        sums = Q.sum(axis=1)
        neg = int((Q < -1e-12).sum())
        S = _surv(Q)
        mono = float(np.max(np.diff(S, axis=1)))
        prov_ok = bool(np.allclose(Q[prov_mask], P_raw[common][prov_mask], atol=1e-12))
        ok = (abs(sums - 1.0).max() < 1e-9) and neg == 0 and mono <= 1e-9 and prov_ok
        valid["detail"][name] = {"max_abs_sum_err": round(float(abs(sums - 1.0).max()), 12),
                                 "n_negative": neg,
                                 "max_survivor_increase": round(mono, 12),
                                 "provisional_untouched": prov_ok, "pass": bool(ok)}
        valid["pass"] = valid["pass"] and ok
    rep["stop_conditions"]["arms_valid"] = valid

    # --- metrics per arm -----------------------------------------------------
    def metrics(Q):
        i0, s0 = rel_slope(Q, y, 0)
        return {
            "M1_bust_ece": round(bust_ece(Q, y), 5),
            "M2_tier_gap_weighted": round(tier_gap_weighted(Q, y, fv), 5),
            "M2_tier_gap_unweighted": round(float(np.mean([v["gap"] for v in
                                                           tier_table(Q, y, fv).values()])), 5),
            "M3_ece_by_bucket": {BUCKETS[b]: round(bucket_ece(Q, y, b), 5) for b in range(5)},
            "M3_ece_mean5": round(float(np.mean([bucket_ece(Q, y, b) for b in range(5)])), 5),
            "M4_bust_reliability_intercept": round(i0, 5),
            "M4_bust_reliability_slope": round(s0, 5),
            "M5_bias": bias_table(Q, y, fv),
            "M5T_good_star_bias_tier_ge_50": round(m5t(Q, y, fv), 5),
            "logscore": round(logscore(Q, y), 5),
            "brier": round(brier(Q, y), 5),
            "war_mae_diagnostic": round(war_mae(Q, tgt), 5),
            "per_tier": {str(k): v for k, v in tier_table(Q, y, fv).items()},
        }

    rep["arms"] = {name: metrics(Q) for name, (_, Q) in arms.items()}

    A0, Q0 = arms["arm0_shipped"][1], arms["arm2_perthr"][1]
    d_M1 = rep["arms"]["arm0_shipped"]["M1_bust_ece"] - rep["arms"]["arm2_perthr"]["M1_bust_ece"]
    d_M2 = (rep["arms"]["arm0_shipped"]["M2_tier_gap_weighted"]
            - rep["arms"]["arm2_perthr"]["M2_tier_gap_weighted"])
    d_M5T = abs(rep["arms"]["arm0_shipped"]["M5T_good_star_bias_tier_ge_50"]) - \
        abs(rep["arms"]["arm2_perthr"]["M5T_good_star_bias_tier_ge_50"])
    d_LS = rep["arms"]["arm0_shipped"]["logscore"] - rep["arms"]["arm2_perthr"]["logscore"]

    # --- the production fit (what would ship) --------------------------------
    rep["production_fit_perthr"] = fit_full(frame, "perthr")
    rep["production_fit_shared"] = fit_full(frame, "shared")
    rep["production_fit_level"] = fit_full(frame, "level")
    rep["production_fit_bust_only"] = fit_full(frame, "bust_only")
    rep["production_fit_incumbent_prop"] = fit_full(frame, "incumbent_prop")
    import efv_odds_calibration as _oc
    rep["incumbent_platt"] = {k: list(v) for k, v in _oc._PLATT.items()}

    # =========================================================================
    # 3.1 FLOORS. Derived on THIS statistic on THESE rows, both instruments.
    # =========================================================================
    B_cond, B_refit, B_perm = (200, 40, 30) if quick else (2000, 400, 200)
    for a in sys.argv[1:]:
        if a.startswith("--bcond="):
            B_cond = int(a.split("=")[1])
        elif a.startswith("--brefit="):
            B_refit = int(a.split("=")[1])
        elif a.startswith("--bperm="):
            B_perm = int(a.split("=")[1])
    print(f"B_cond={B_cond} B_refit={B_refit} B_perm={B_perm}", flush=True)

    # E_cond: fits held fixed, scored rows resampled i.i.d.
    n = len(common)
    dc = {"M1": [], "M2": [], "M5T": [], "LS": [],
          **{f"ece_{b}": [] for b in range(5)}}
    for _bi in range(B_cond):
        if _bi % 200 == 0:
            print(f"  E_cond {_bi}/{B_cond}", flush=True)
        s = rng.integers(0, n, n)
        Qa, Qb = A0[s], Q0[s]
        ys, fvs = y[s], fv[s]
        dc["M1"].append(bust_ece(Qa, ys) - bust_ece(Qb, ys))
        dc["M2"].append(tier_gap_weighted(Qa, ys, fvs) - tier_gap_weighted(Qb, ys, fvs))
        dc["M5T"].append(abs(m5t(Qa, ys, fvs)) - abs(m5t(Qb, ys, fvs)))
        dc["LS"].append(logscore(Qa, ys) - logscore(Qb, ys))
        for b in range(5):
            dc[f"ece_{b}"].append(bucket_ece(Qa, ys, b) - bucket_ece(Qb, ys, b))

    rep["floors_E_cond"] = {
        "instrument": "E_cond (registered primary, data/xfv_power_eval.json): per-fold "
                      "recalibration fits held FIXED, scored rows resampled i.i.d.",
        "M1_bust_ece": _floor(dc["M1"], d_M1),
        "M2_tier_gap_weighted": _floor(dc["M2"], d_M2),
        "M5T_abs_good_star_bias_ge_50": _floor(dc["M5T"], d_M5T),
        "logscore": _floor(dc["LS"], d_LS),
        "per_bucket_ece": {BUCKETS[b]: _floor(
            dc[f"ece_{b}"],
            rep["arms"]["arm0_shipped"]["M3_ece_by_bucket"][BUCKETS[b]]
            - rep["arms"]["arm2_perthr"]["M3_ece_by_bucket"][BUCKETS[b]]) for b in range(5)},
    }

    # E_refit (RESTRICTED): resample the pooled frame, refit the forward chain per draw.
    # Draw i is seeded from SEED*1000 + i, so the set of draws is identical whether it is
    # produced in one process or in resumable chunks (see --refit-chunk). This machine
    # segfaults inside L-BFGS-B on long runs; chunking is a durability measure and changes
    # no draw.
    have = _read_refit_draws()
    missing = [i for i in range(B_refit) if i not in have]
    if missing:
        print(f"  E_refit computing {len(missing)} draws inline", flush=True)
        refit_chunk(frame, missing)
        have = _read_refit_draws()
    dr = {"M1": [], "M2": [], "M5T": []}
    for i in range(B_refit):
        if i in have:
            for k in dr:
                dr[k].append(have[i][k])
    rep["floors_E_refit_restricted"] = {
        "instrument": "E_refit RESTRICTED: pooled frame resampled with replacement and the "
                      "forward-chained RECALIBRATION refit per draw. The underlying ridge "
                      "and its output calibration are INPUTS to this lane and are held "
                      "fixed, so this is a LOWER BOUND on full refit variance. Disclosed "
                      "in the gate doc section 3.1 before the run.",
        "M1_bust_ece": _floor(dr["M1"], d_M1),
        "M2_tier_gap_weighted": _floor(dr["M2"], d_M2),
        "M5T_abs_good_star_bias_ge_50": _floor(dr["M5T"], d_M5T),
    }

    # --- P6 permuted-tier twin ----------------------------------------------
    perm = {"M1": [], "M2": []}
    perm_alt = {"arm1_shared": {"M1": [], "M2": []}, "arm3_level": {"M1": [], "M2": []}}
    prng = np.random.default_rng(SEED + 1)
    for _bi in range(B_perm):
        if _bi % 20 == 0:
            print(f"  perm {_bi}/{B_perm}", flush=True)
        ip, Qp, _ = chain_score(frame, "perthr", perm_rng=prng)
        if not np.array_equal(ip, common):
            continue
        perm["M1"].append(bust_ece(A0, y) - bust_ece(Qp, y))
        perm["M2"].append(tier_gap_weighted(A0, y, fv) - tier_gap_weighted(Qp, y, fv))
        for nm, md in (("arm1_shared", "shared"), ("arm3_level", "level")):
            ia, Qa, _ = chain_score(frame, md, perm_rng=prng)
            if not np.array_equal(ia, common):
                continue
            perm_alt[nm]["M1"].append(bust_ece(A0, y) - bust_ece(Qa, y))
            perm_alt[nm]["M2"].append(tier_gap_weighted(A0, y, fv)
                                      - tier_gap_weighted(Qa, y, fv))
    pm1 = np.asarray(perm["M1"], dtype=float)
    pm2 = np.asarray(perm["M2"], dtype=float)
    rep["ctrl_permuted_tier_twin"] = {
        "what": ("predicted probability vectors shuffled among TRAIN rows within each fold "
                 "and side, destroying the tier-to-outcome correspondence; ARM-2 refit on "
                 "the permuted train fold and applied to the REAL test rows"),
        "B": int(len(pm1)), "seed": SEED + 1,
        "actual_M1_improvement": round(float(d_M1), 6),
        "perm_M1_mean": round(float(pm1.mean()), 6),
        "perm_M1_p95": round(float(np.percentile(pm1, 95)), 6),
        "perm_M1_p05": round(float(np.percentile(pm1, 5)), 6),
        "perm_p_onesided_M1": round(float((pm1 >= d_M1).mean()), 5),
        "actual_M2_improvement": round(float(d_M2), 6),
        "perm_M2_mean": round(float(pm2.mean()), 6),
        "perm_M2_p95": round(float(np.percentile(pm2, 95)), 6),
        "perm_p_onesided_M2": round(float((pm2 >= d_M2).mean()), 5),
        "pass_M1": bool(float((pm1 >= d_M1).mean()) < PERM_ALPHA),
    }

    # --- P8 held-out folds ---------------------------------------------------
    folds = {}
    for t in sorted({int(frame[i]["decision_year"]) for i in common}):
        m = np.array([frame[i]["decision_year"] == t for i in common])
        if m.sum() < 20:
            folds[str(t)] = {"n": int(m.sum()), "skipped_lt_20": True}
            continue
        folds[str(t)] = {
            "n": int(m.sum()),
            "arm0_bust_ece": round(bust_ece(A0[m], y[m]), 5),
            "arm2_bust_ece": round(bust_ece(Q0[m], y[m]), 5),
            "delta": round(bust_ece(A0[m], y[m]) - bust_ece(Q0[m], y[m]), 5),
            "arm0_logscore": round(logscore(A0[m], y[m]), 5),
            "arm2_logscore": round(logscore(Q0[m], y[m]), 5),
        }
    scored = [v for v in folds.values() if "delta" in v]
    rep["held_out_folds"] = {
        "by_year": folds,
        "n_folds_scored": len(scored),
        "n_folds_improved": sum(1 for v in scored if v["delta"] > 0),
        "n_folds_logscore_improved": sum(1 for v in scored
                                         if v["arm0_logscore"] > v["arm2_logscore"]),
        "note": "reported for honesty; the gate doc builds no clause on a fold split this small",
    }

    # --- control shares (P5, P7) --------------------------------------------
    d_M1_arm4 = (rep["arms"]["arm0_shipped"]["M1_bust_ece"]
                 - rep["arms"]["arm4_marginal_constant"]["M1_bust_ece"])
    d_M1_arm5 = (rep["arms"]["arm0_shipped"]["M1_bust_ece"]
                 - rep["arms"]["arm5_bust_only_refit"]["M1_bust_ece"])
    rep["ctrl_zero_information"] = {
        "arm4_marginal_constant_M1": rep["arms"]["arm4_marginal_constant"]["M1_bust_ece"],
        "arm4_improvement_over_arm0": round(float(d_M1_arm4), 6),
        "arm2_improvement_over_arm0": round(float(d_M1), 6),
        "share_of_arm2_M1_gain": round(float(d_M1_arm4 / d_M1), 4) if d_M1 else None,
        "bar": CTRL_SHARE_BAR,
        "arm2_beats_arm4_on_M1": bool(rep["arms"]["arm2_perthr"]["M1_bust_ece"]
                                      < rep["arms"]["arm4_marginal_constant"]["M1_bust_ece"]),
        "arm2_beats_arm4_on_logscore": bool(rep["arms"]["arm2_perthr"]["logscore"]
                                            < rep["arms"]["arm4_marginal_constant"]["logscore"]),
    }
    rep["ctrl_incumbent_family_refit"] = {
        "arm5_M1": rep["arms"]["arm5_bust_only_refit"]["M1_bust_ece"],
        "arm5_improvement_over_arm0": round(float(d_M1_arm5), 6),
        "share_of_arm2_M1_gain": round(float(d_M1_arm5 / d_M1), 4) if d_M1 else None,
        "bar": CTRL_SHARE_BAR,
        "arm5_M5T": rep["arms"]["arm5_bust_only_refit"]["M5T_good_star_bias_tier_ge_50"],
        "arm2_M5T": rep["arms"]["arm2_perthr"]["M5T_good_star_bias_tier_ge_50"],
        "note": ("ARM-5 is the incumbent's OWN two-parameter family refit per fold. It is "
                 "here because substituting a production calibration for a per-fold one has "
                 "flipped the sign of a headline in this program."),
    }

    # =========================================================================
    # POST-HOC DIAGNOSTICS. ADDED AFTER THE PRIMARY RUN. THESE DO NOT ENTER THE
    # VERDICT AND NO PRE-REGISTERED CLAUSE WAS EDITED. Same discipline C1 used
    # for its CTRL-6 / CTRL-7.
    # =========================================================================
    def _bust_decomp(Q, yy, n_bins=10):
        """Murphy decomposition of the bust-bucket Brier score over the SAME 10 bins
        _reliability_bins uses. RESOLUTION is what a constant predictor cannot have."""
        p = np.asarray(Q, dtype=float)[:, 0]
        t = (np.asarray(yy, dtype=int) == 0).astype(float)
        edges = np.linspace(0.0, 1.0, n_bins + 1)
        N = len(p)
        base = float(t.mean())
        rel = res = 0.0
        occupied = 0
        for i in range(n_bins):
            m = (p >= edges[i]) & ((p < edges[i + 1]) if i < n_bins - 1 else (p <= 1.0))
            c = int(m.sum())
            if c < 5:
                continue
            occupied += 1
            mp, fr = float(p[m].mean()), float(t[m].mean())
            rel += (c / N) * (mp - fr) ** 2
            res += (c / N) * (fr - base) ** 2
        return {"reliability": round(rel, 6), "resolution": round(res, 6),
                "uncertainty": round(base * (1 - base), 6),
                "occupied_bins_ge5": occupied, "base_rate": round(base, 5)}

    t_arr = np.rint(fv / 5.0).astype(int) * 5
    rep["posthoc_added_after_primary_run"] = {
        "disclosure": ("Everything in this block was written after the primary numbers "
                       "were known. It changes no clause, no threshold and no verdict. It "
                       "exists because the pre-registered PRIMARY metric turned out to be "
                       "degenerate and that is worth measuring rather than hiding."),
        "arm5_misspecification": {
            "what": ("The gate doc registers ARM-5 as '(A_1, B_1) free, thresholds 2 to 4 "
                     "held at identity' AND calls it 'the incumbent's own family'. Those "
                     "are two DIFFERENT maps. recalibrate_bucket rescales the non-bust "
                     "buckets PROPORTIONALLY (S'_k = S_k * S'_1 / S_1), it does not hold "
                     "the upper cumulative logits fixed."),
            "consequence": ("ARM-5 as registered leaves the good+star mass literally "
                            "unchanged from raw whenever S'_1 >= S_2, which is why its M5T "
                            "equals the raw curve's exactly. ARM-5 is reported as "
                            "registered; ARM-5b is the faithful incumbent-family refit and "
                            "is the one the P7 question should have been asked of."),
            "arm5_as_registered_M1": rep["arms"]["arm5_bust_only_refit"]["M1_bust_ece"],
            "arm5b_faithful_M1":
                rep["arms"]["arm5b_incumbent_family_refit_POSTHOC"]["M1_bust_ece"],
            "arm5b_share_of_arm2_M1_gain": round(
                float((rep["arms"]["arm0_shipped"]["M1_bust_ece"]
                       - rep["arms"]["arm5b_incumbent_family_refit_POSTHOC"]["M1_bust_ece"])
                      / d_M1), 4) if d_M1 else None,
        },
        "M1_is_degenerate": {
            "what": ("Pooled bust ECE over equal-width bins measures LEVEL, not "
                     "discrimination. A predictor that emits one constant occupies one bin "
                     "and its ECE collapses to |mean_p - base_rate|, which can be near "
                     "zero. That is why ARM-4 and the permuted twin BEAT ARM-2 on M1 while "
                     "losing badly on log score, Brier and the tier gap."),
            "murphy_decomposition_bust": {
                name: _bust_decomp(Q, y) for name, (_, Q) in arms.items()},
            "reading": ("compare `resolution`: ARM-4 and any permuted-collapse map have "
                        "near-zero resolution by construction. M1 does not penalise that; "
                        "log score and Brier do."),
        },
        "permuted_twin_other_arms": {
            nm: {"B": len(v["M1"]),
                 "actual_M1_improvement": round(float(
                     rep["arms"]["arm0_shipped"]["M1_bust_ece"]
                     - rep["arms"][nm]["M1_bust_ece"]), 6),
                 "perm_M1_mean": round(float(np.mean(v["M1"])), 6) if v["M1"] else None,
                 "perm_p_onesided_M1": round(float(np.mean(
                     np.asarray(v["M1"]) >= (rep["arms"]["arm0_shipped"]["M1_bust_ece"]
                                             - rep["arms"][nm]["M1_bust_ece"]))), 5)
                 if v["M1"] else None,
                 "actual_M2_improvement": round(float(
                     rep["arms"]["arm0_shipped"]["M2_tier_gap_weighted"]
                     - rep["arms"][nm]["M2_tier_gap_weighted"]), 6),
                 "perm_p_onesided_M2": round(float(np.mean(
                     np.asarray(v["M2"]) >= (rep["arms"]["arm0_shipped"]["M2_tier_gap_weighted"]
                                             - rep["arms"][nm]["M2_tier_gap_weighted"]))), 5)
                 if v["M2"] else None}
            for nm, v in perm_alt.items()},
        "arm4_share_on_M2": round(float(
            (rep["arms"]["arm0_shipped"]["M2_tier_gap_weighted"]
             - rep["arms"]["arm4_marginal_constant"]["M2_tier_gap_weighted"]) / d_M2), 4)
        if d_M2 else None,
        "tier_band_counts_in_evaluable_frame": {
            "tier_le_45": int((t_arr <= 45).sum()), "tier_ge_50": int((t_arr >= 50).sum()),
            "by_tier": {str(int(k)): int((t_arr == k).sum())
                        for k in sorted(set(t_arr.tolist()))},
            "note": ("this is why the M5T floor is wide: the top-of-board band the defect "
                     "lives in is a small minority of the frame"),
        },
        "min_recal_train_sensitivity": _min_recal_sensitivity(frame, y_all, fv_all, P_ship),
        "arm_ranking_note": ("ARM-2 was named PRIMARY in the gate doc before any number "
                            "existed. Reading the arm table and then promoting whichever "
                            "arm won is selection on outcome; this lane does NOT do that "
                            "and hands the observation to a fresh pre-registration."),
    }

    # =========================================================================
    # 6. SERVE-PATH INTEGRITY + DOLLAR IMPACT
    # =========================================================================
    rep["serve_path"] = serve_path_checks()
    rep["dollar_impact"] = dollar_impact({
        "arm2_perthr_REGISTERED_PRIMARY": rep["production_fit_perthr"],
        "arm1_shared_POSTHOC": rep["production_fit_shared"],
        "arm3_level_POSTHOC": rep["production_fit_level"]})

    # =========================================================================
    # 7. VERDICT
    # =========================================================================
    fc = rep["floors_E_cond"]
    fr = rep["floors_E_refit_restricted"]
    worst_bucket = None
    for b in range(5):
        f = fc["per_bucket_ece"][BUCKETS[b]]
        if f["point_delta"] < -f["mde95_onesided"]:
            worst_bucket = BUCKETS[b]
    clauses = {
        "P1_M1_both_instruments": {
            "e_cond": fc["M1_bust_ece"]["clears"],
            "e_refit_restricted": fr["M1_bust_ece"]["clears"],
            "pass": bool(fc["M1_bust_ece"]["clears"] and fr["M1_bust_ece"]["clears"]),
            "instruments_agree": bool(fc["M1_bust_ece"]["clears"] == fr["M1_bust_ece"]["clears"]),
        },
        "P2_M2_tier_gap": {"pass": bool(fc["M2_tier_gap_weighted"]["clears"]),
                           "e_refit_restricted": fr["M2_tier_gap_weighted"]["clears"]},
        "P3_top_of_board_M5T": {
            "pass": bool(abs(rep["arms"]["arm2_perthr"]["M5T_good_star_bias_tier_ge_50"])
                         < abs(rep["arms"]["arm0_shipped"]["M5T_good_star_bias_tier_ge_50"])
                         and fc["M5T_abs_good_star_bias_ge_50"]["clears"])},
        "P4_do_no_harm": {"pass": worst_bucket is None, "worst_bucket": worst_bucket},
        "P5_zero_information": {
            "pass": bool(rep["ctrl_zero_information"]["arm2_beats_arm4_on_M1"]
                         and rep["ctrl_zero_information"]["arm2_beats_arm4_on_logscore"]),
            "level_effect_only": bool((rep["ctrl_zero_information"]["share_of_arm2_M1_gain"]
                                       or 0) >= CTRL_SHARE_BAR)},
        "P6_permuted_tier_twin": {"pass": rep["ctrl_permuted_tier_twin"]["pass_M1"]},
        "P7_incumbent_refit_redirect": {
            "trips": bool((rep["ctrl_incumbent_family_refit"]["share_of_arm2_M1_gain"] or 0)
                          >= CTRL_SHARE_BAR)},
        "P8_folds": {"improved": rep["held_out_folds"]["n_folds_improved"],
                     "of": rep["held_out_folds"]["n_folds_scored"]},
    }
    stop_logscore = bool(d_LS < -fc["logscore"]["mde95_onesided"])
    clauses["STOP_logscore_worse"] = {"tripped": stop_logscore,
                                      "delta_arm0_minus_arm2": round(float(d_LS), 6)}
    stops_ok = (rep["stop_conditions"]["mirror_reproduces_shipped"]["pass"]
                and rep["stop_conditions"]["arms_valid"]["pass"]
                and not stop_logscore)
    if not stops_ok or not clauses["P1_M1_both_instruments"]["pass"] \
            or not clauses["P6_permuted_tier_twin"]["pass"]:
        verdict = "NO_SHIP"
    elif clauses["P7_incumbent_refit_redirect"]["trips"]:
        verdict = "REDIRECT"
    elif all(clauses[k]["pass"] for k in ("P2_M2_tier_gap", "P3_top_of_board_M5T",
                                          "P4_do_no_harm", "P5_zero_information")):
        verdict = "GATED_READY"
    else:
        verdict = "PARTIAL"
    rep["clauses"] = clauses
    rep["verdict"] = verdict
    rep["elapsed_s"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"verdict={verdict}  n={len(common)}  dM1={d_M1:+.5f}  dM2={d_M2:+.5f}  "
          f"dM5T={d_M5T:+.5f}  elapsed={rep['elapsed_s']}s")
    return rep


# =============================================================================
# SERVE-PATH INTEGRITY
# =============================================================================
def _min_recal_sensitivity(frame, y_all, fv_all, P_ship) -> dict:
    """POST-HOC. MIN_RECAL_TRAIN = 150 is a threshold this gate added and it sets the
    evaluable frame. Does the failing comparison depend on it? Re-run the arms at 100 and
    250 and report the two clauses that actually failed."""
    global MIN_RECAL_TRAIN
    keep = MIN_RECAL_TRAIN
    out = {}
    try:
        for mr in (100, 150, 250, 400):
            MIN_RECAL_TRAIN = mr
            i2, Q2, _ = chain_score(frame, "perthr")
            i1, Q1, _ = chain_score(frame, "shared")
            i4, Q4, _ = chain_score(frame, "perthr", marginal=True)
            if len(i2) == 0 or not np.array_equal(i2, i4) or not np.array_equal(i2, i1):
                out[str(mr)] = {"n": int(len(i2)), "frames_disagree": True}
                continue
            yy, ff, A0 = y_all[i2], fv_all[i2], P_ship[i2]
            out[str(mr)] = {
                "n": int(len(i2)),
                "arm0_M1": round(bust_ece(A0, yy), 5),
                "arm2_M1": round(bust_ece(Q2, yy), 5),
                "arm1_M1": round(bust_ece(Q1, yy), 5),
                "arm4_M1": round(bust_ece(Q4, yy), 5),
                "P5_arm2_beats_arm4_on_M1": bool(bust_ece(Q2, yy) < bust_ece(Q4, yy)),
                "arm0_M2": round(tier_gap_weighted(A0, yy, ff), 5),
                "arm2_M2": round(tier_gap_weighted(Q2, yy, ff), 5),
                "arm1_M2": round(tier_gap_weighted(Q1, yy, ff), 5),
                "arm4_M2": round(tier_gap_weighted(Q4, yy, ff), 5),
                "arm0_M5T": round(m5t(A0, yy, ff), 5),
                "arm2_M5T": round(m5t(Q2, yy, ff), 5),
                "arm1_M5T": round(m5t(Q1, yy, ff), 5),
                "arm0_logscore": round(logscore(A0, yy), 5),
                "arm2_logscore": round(logscore(Q2, yy), 5),
                "arm1_logscore": round(logscore(Q1, yy), 5),
                "arm4_logscore": round(logscore(Q4, yy), 5),
            }
    finally:
        MIN_RECAL_TRAIN = keep
    return out


def serve_path_checks() -> dict:
    """Verify, before and after, the three invariants the lane brief names."""
    import inspect
    import value_framework as vf
    import efv_score as es

    src = (ROOT / "efv_score.py").read_text(encoding="utf-8").splitlines()
    seams = [i + 1 for i, ln in enumerate(src) if "_odds_cal.recalibrate_bucket(" in ln]
    # what the recalibrated vector is consumed by, in the 60 lines after each seam
    consumers = {}
    for s in seams:
        uses = []
        for i in range(s, min(len(src), s + 60)):
            ln = src[i]
            if "probs" in ln and "recalibrate_bucket" not in ln:
                uses.append((i + 1, ln.strip()[:110]))
        consumers[str(s)] = uses[:8]

    sig = inspect.signature(vf.expected_surplus_usd)
    cal_sites = [i + 1 for i, ln in enumerate(src) if "vf.apply_calibration(" in ln]
    reprice_src = inspect.getsource(es._reprice_surplus_on_display)
    return {
        "recalibrate_bucket_seams": seams,
        "expected_n_seams": 3,
        "seams_ok": len(seams) == 3,
        "recalibrated_vector_consumers": consumers,
        "expected_surplus_usd_signature": str(sig),
        "dollars_can_see_the_map": ("probs" in sig.parameters
                                    or "p_bucket" in str(sig)),
        "dollar_path": ("vf.expected_surplus_usd -> _pipeline_surplus_from_svs "
                        "(value_framework.py:1371-1376) calls p_bucket_given_fv ITSELF, at "
                        "the DISPLAY grade. It takes no probability argument, so no odds-seam "
                        "map can reach it."),
        "apply_calibration_call_sites_in_efv_score": cal_sites,
        "apply_calibration_applied_once": {
            "seam": "efv_score._cal_mm (:1097-1111), called from _reprice_surplus_on_display (:1583-1585)",
            "reprice_recomputes_from_engine": ("vf.expected_surplus_usd" in reprice_src
                                               and "vf.sv_distribution" in reprice_src),
            "reprice_reads_back_a_calibrated_field": any(
                tok in reprice_src for tok in ('_cq(s["surplus_mm"]', '_cq(s.get("surplus_mm")')),
            "note": ("_reprice_surplus_on_display overwrites surplus_mm / band_p10_mm / "
                     "band_p90_mm / dist with values recomputed FRESH from the engine at the "
                     "display grade, so the earlier _cx calibration at :1516-1520 is "
                     "discarded rather than compounded. Applied exactly once."),
        },
        "odds_and_dollars_split": {
            "odds_grade_field": "vf.realized_implied_fv (efv_score :1480, :1488)",
            "dollar_grade_field": "xfv_grade_display (efv_score :1558, :1160-1168)",
            "unified_by_this_lane": False,
            "note": "plan item D6, an owner decision. Not touched.",
        },
    }


# =============================================================================
# DOLLAR IMPACT ON THE LIVE BOARD
# =============================================================================
def dollar_impact(fits: dict) -> dict:
    """`fits` maps a candidate label -> {"hit": {...}, "pit": {...}} production fit.

    THE ODDS GRADE IS NOT EXPORTED. efv_export.py:44-45 sets both `xfv_grade` and
    `xfv_grade_realized` to the scored dict's `xfv_grade`, which efv_score.py:1473 builds
    from vf.outcome_implied_fv, while p_bucket / p_bust are keyed on `_odds_grade` =
    vf.realized_implied_fv (efv_score.py:1480, :1488). So the board cannot be reconstructed
    from any exported grade. This function RECOVERS the odds grade by inverting the served
    vector against the p_bucket_given_fv curve, which also identifies the provisional rows
    (their vector sits on the RAW curve, not the Platt-mapped one)."""
    import value_framework as vf
    import efv_odds_calibration as _oc

    board = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    da, ee = vf._round_timing(*vf._resolve_timing(None, 1.0))
    bridge_to = float(vf._config()["lowtier_anchor"]["bridge_to_fv"])

    grid = np.round(np.arange(20.0, 80.0001, 0.01), 2)
    tab_raw, tab_platt = {}, {}
    for side, ip in (("hit", False), ("pit", True)):
        R = np.array([vf.p_bucket_given_fv(float(g), ip) for g in grid], dtype=float)
        tab_raw[side] = R
        tab_platt[side] = np.array([_oc.recalibrate_bucket(list(r), ip, provisional=False)
                                    for r in R], dtype=float)

    sv_cache: dict = {}

    def svs(grade, is_pit):
        k = (round(grade * 2) / 2, is_pit)
        if k not in sv_cache:
            role = "pitcher" if is_pit else "hitter"
            sv_cache[k] = np.asarray(vf._effective_bucket_sv(
                is_pit, None, da, ee, vf._war_scale_for(grade, role)), dtype=float)
        return sv_cache[k]

    bands = [("<=40", -1e9, 41.0), ("42.5-45", 41.0, 46.0), ("47.5-50", 46.0, 51.0),
             ("52.5-55", 51.0, 56.0), (">=57.5", 56.0, 1e9)]
    labs = ["EXISTING_odds_vs_dollars_gap"] + list(fits)
    agg = {lab: {b[0]: {"n": 0, "sum_d": 0.0, "sum_abs_d": 0.0, "max_abs_d": 0.0,
                        "sum_served_surplus_mm": 0.0, "sum_dp_bust": 0.0,
                        "sum_dp_good_star": 0.0} for b in bands} for lab in labs}
    n_prov = n_used = n_skip = n_below_bridge = 0
    resid, gdiff = [], []
    surplus_check = []
    for pk, row in board.items():
        cfv = row.get("consensus_fv")
        gd = row.get("xfv_grade_quantile")
        if cfv is None or gd is None or not row.get("p_bucket"):
            n_skip += 1
            continue
        is_pit = row.get("side") == "P"
        side = "pit" if is_pit else "hit"
        v = np.asarray([row["p_bucket"][b] for b in BUCKETS], dtype=float)
        i_raw = int(np.argmin(np.abs(tab_raw[side] - v).max(axis=1)))
        i_plt = int(np.argmin(np.abs(tab_platt[side] - v).max(axis=1)))
        d_raw = float(np.abs(tab_raw[side][i_raw] - v).max())
        d_plt = float(np.abs(tab_platt[side][i_plt] - v).max())
        provisional = d_raw < d_plt
        j = i_raw if provisional else i_plt
        resid.append(min(d_raw, d_plt))
        g_odds = float(grid[j])
        if row.get("xfv_grade_realized") is not None:
            gdiff.append(g_odds - float(row["xfv_grade_realized"]))
        p_raw = tab_raw[side][j]
        p_inc = tab_raw[side][j] if provisional else tab_platt[side][j]
        if provisional:
            n_prov += 1
        band = next((nm for nm, lo, hi in bands if lo <= float(cfv) < hi), None)
        if band is None:
            n_skip += 1
            continue
        gd = float(gd)
        if gd < bridge_to:
            # below the bridge, expected_surplus_usd uses the flat low-tier ANCHOR and
            # reads no bucket probability at all, so a distribution recalibration has
            # exactly zero price meaning on these rows.
            n_below_bridge += 1
            continue
        sv = svs(gd, is_pit)
        cur = float(np.asarray(vf.p_bucket_given_fv(gd, is_pit), dtype=float) @ sv) / 1e6
        c_cur = vf.apply_calibration(cur, gd, is_pit)
        c_inc = vf.apply_calibration(float(p_inc @ sv) / 1e6, gd, is_pit)
        if row.get("surplus_mm") is not None:
            surplus_check.append(abs(c_cur - float(row["surplus_mm"])))

        def _put(lab, d, dpb, dpg):
            a = agg[lab][band]
            a["n"] += 1
            a["sum_d"] += d
            a["sum_abs_d"] += abs(d)
            a["max_abs_d"] = max(a["max_abs_d"], abs(d))
            a["sum_served_surplus_mm"] += float(row.get("surplus_mm") or 0.0)
            a["sum_dp_bust"] += dpb
            a["sum_dp_good_star"] += dpg
        p_cur = np.asarray(vf.p_bucket_given_fv(gd, is_pit), dtype=float)
        _put("EXISTING_odds_vs_dollars_gap", float(c_inc - c_cur),
             float(p_inc[0] - p_cur[0]), float(p_inc[3:].sum() - p_cur[3:].sum()))
        for lab, pf in fits.items():
            if provisional:
                p_c = p_raw
            else:
                p_c = apply_map(p_raw.reshape(1, 5),
                                np.asarray(pf[side]["A"], dtype=float),
                                np.asarray(pf[side]["B"], dtype=float))[0]
            c_new = vf.apply_calibration(float(p_c @ sv) / 1e6, gd, is_pit)
            _put(lab, float(c_new - c_inc), float(p_c[0] - p_inc[0]),
                 float(p_c[3:].sum() - p_inc[3:].sum()))
        n_used += 1
    for lab in agg:
        for name in agg[lab]:
            a = agg[lab][name]
            if a["n"]:
                a["mean_delta_mm"] = round(a["sum_d"] / a["n"], 4)
                a["mean_abs_delta_mm"] = round(a["sum_abs_d"] / a["n"], 4)
                a["mean_dp_bust"] = round(a["sum_dp_bust"] / a["n"], 5)
                a["mean_dp_good_star"] = round(a["sum_dp_good_star"] / a["n"], 5)
                a["mean_served_surplus_mm"] = round(a["sum_served_surplus_mm"] / a["n"], 3)
            for k in ("sum_d", "sum_abs_d", "max_abs_d", "sum_dp_bust",
                      "sum_dp_good_star", "sum_served_surplus_mm"):
                a[k] = round(a[k], 4)
    rd = np.asarray(resid, dtype=float)
    gdf = np.asarray(gdiff, dtype=float)
    sc = np.asarray(surplus_check, dtype=float)
    return {
        "served_surplus_mm_delta": 0.0,
        "served_surplus_mm_delta_basis": (
            "EXACT, structural, not estimated. vf.expected_surplus_usd takes no probability "
            "argument and re-derives p_bucket_given_fv itself at the DISPLAY grade "
            "(_pipeline_surplus_from_svs, value_framework.py:1371-1376). A map applied at the "
            "efv_score odds seam therefore cannot reach surplus_mm, band_p10_mm, band_p90_mm "
            "or dist. PATH A moves NO dollar on the board."),
        "counterfactual_note": (
            "Every delta below is a COUNTERFACTUAL: what would happen IF the served odds "
            "were also the pricing distribution, i.e. if the p_bucket vector inside "
            "_pipeline_surplus_from_svs were replaced by the served odds vector. "
            "EXISTING_odds_vs_dollars_gap is the size of that swap TODAY, with no "
            "recalibration at all; each arm's row is the ADDITIONAL move its map would "
            "cause on top of it. PATH A causes none of this."),
        "odds_grade_not_exported": {
            "what": ("efv_export.py:44-45 sets xfv_grade AND xfv_grade_realized to the "
                     "scored dict's xfv_grade = vf.outcome_implied_fv (efv_score.py:1473). "
                     "p_bucket / p_bust are keyed on _odds_grade = vf.realized_implied_fv "
                     "(efv_score.py:1480, :1488). The export comment at efv_export.py:41-42 "
                     "says xfv_grade_realized IS realized_implied_fv and 'still drives "
                     "p_bucket / p_bust'. It is not and it does not."),
            "recovered_minus_exported_grade": {
                "n": int(len(gdf)), "median": round(float(np.median(gdf)), 3),
                "p05": round(float(np.percentile(gdf, 5)), 3),
                "p95": round(float(np.percentile(gdf, 95)), 3),
                "share_within_0.1": round(float((np.abs(gdf) <= 0.1).mean()), 4)},
            "inversion_residual_max_abs_prob": {
                "median": round(float(np.median(rd)), 6),
                "p95": round(float(np.percentile(rd, 95)), 6),
                "max": round(float(rd.max()), 6),
                "note": "p_bucket is exported at 3 dp, so ~5e-4 is the floor"},
        },
        "pricing_basis": {
            "sv_grade": "xfv_grade_quantile (the DISPLAY grade, which is what prices dollars)",
            "position": None, "debut_age": da, "eta_years": ee,
            "engine_reproduction_abs_err_mm": {
                "n": int(len(sc)), "median": round(float(np.median(sc)), 4),
                "p95": round(float(np.percentile(sc, 95)), 4)} if len(sc) else None,
            "limitation": ("per-row position and age are not carried in data/xfv.json, so "
                           "the per-bucket SVs use the engine's generic curve and default "
                           "timing. The reproduction error above bounds that. Band-level "
                           "magnitude, not a per-player restatement."),
        },
        "rows_total": len(board), "rows_priced": n_used,
        "rows_provisional_no_map": n_prov, "rows_skipped": n_skip,
        "rows_below_bridge_no_price_meaning": n_below_bridge,
        "bridge_to_fv": bridge_to,
        "by_consensus_fv_band": agg,
    }


# #############################################################################
# ############################## LANE B-L5 ####################################
# IDR / EasyUQ recalibration cut at the four business thresholds.
#
# PRE-REGISTRATION. Everything from here to `run_idr` - the family, the four arms,
# the metric, the decomposition, the estimators, the multiplicity correction and the
# eight ship clauses - was written BEFORE any B-L5 number existed, in this file, in one
# commit. The only things written after the run are inside `run_idr`'s
# `posthoc_added_after_primary_run` block, which changes no clause.
#
# WHY THIS IS NOT THE TWO ATTEMPTS THAT ALREADY FAILED.
#   tools/efv_dist_recalibration_lab.py (C2, above) fitted PARAMETRIC cumulative-logit
#   Platt families. NO_SHIP. tools/efv_isotonic_lab.py (X-ISO) fitted isotonic PER BUCKET
#   on p_b against 1{y == b} and RENORMALIZED onto the simplex; that is not IDR, the
#   renormalization is not order preserving, and it failed on calibrated rank, dropping
#   Spearman -0.0165 against a -0.002 tolerance.
#   IDR cut at the four thresholds is FOUR PAVA FITS on score -> 1{y >= k}. The four
#   response vectors are POINTWISE ORDERED (1{y>=1} >= 1{y>=2} >= 1{y>=3} >= 1{y>=4} for
#   every single row), and PAVA is monotone in its response, so the four fitted curves
#   CANNOT CROSS. Ordinality is therefore STRUCTURAL and no renormalization onto the
#   simplex is needed. `IDR_ORDINALITY_STRUCTURAL` below records this as a claim that the
#   run must CONFIRM, not assume: if the raw fits cross, the fit is wrong.
#
# THE BINDING DESIGN CONSTRAINT. PAVA makes blocks, blocks make ties, ties destroy rank.
# The candidate lives strictly DOWNSTREAM of `rank_war` and must never feed back into it.
# `rank_feedback_audit()` is the executable proof, run every time, and its failure is a
# hard stop.
#
# HAZARDS, named before the run.
#   H1  IDR is in-sample optimal BY CONSTRUCTION. Every candidate number here is produced
#       by a forward-chained fit on strictly earlier cohorts (`idr_folds`), and the
#       train/test index disjointness is ASSERTED per fold, not assumed.
#   H2  IDR cannot extrapolate above the training maximum; `out_of_bounds="clip"` would
#       flatten the published fan at the top of the board, which is exactly where the
#       business cares. `_idr_extend` handles it: above x_max the candidate carries the
#       PAVA level at x_max and adds the INCUMBENT curve's own log-odds increment from
#       x_max to x. That is monotone in x because the incumbent is, it is exact at x_max
#       by construction, and the number of rows it touches is reported.
#   H3  The FV60 star cell is thin. It is reported as a VENN-ABERS interval (Vovk's IVAP:
#       refit the isotonic twice per test point, with its label forced to 0 and to 1), and
#       never as a point.
#
# THE GATE. Mean RPS primary, decomposed CORP-style into MCB / DSC / UNC. A
# zero-information constant fails BY CONSTRUCTION: its PAVA recalibration is the marginal,
# so DSC = 0 exactly and skill = -MCB/UNC <= 0. This is the structural fix for the ECE
# regime above, in which a constant reached 152.68 percent of the candidate's gain.
# #############################################################################

IDR_THRESHOLDS = (1, 2, 3, 4)            # y >= k, k = bench+ / regular+ / good+ / star
IDR_MIN_TRAIN = 150                      # same bar the C2 chain used
IDR_MIN_TIER_TRAIN = 25                  # tier climatology falls back to global below this
IDR_TIER_EDGES = (38.0, 43.0, 48.0, 53.0)   # consensus-FV climatology bins, fixed a priori
IDR_HOLM_ALPHA = 0.05
IDR_SEED = 20260810
IDR_STAR_TIER = 60                       # the business cell H3 names
IDR_ORDINALITY_STRUCTURAL = True         # claim the run must CONFIRM
IDR_ARMS = ("incumbent", "candidate_idr", "clim_global", "clim_tier")


def _q_from_surv(S):
    """5-bucket vector from survivors S[:, k-1] = P(Y >= k). Ordinality projection is a
    NO-OP on a structurally ordered S; it is here so a broken arm cannot emit a negative
    probability and quietly score well."""
    S = np.minimum.accumulate(np.clip(np.asarray(S, dtype=float), EPS, 1.0 - EPS), axis=1)
    n = S.shape[0]
    Q = np.empty((n, 5))
    Q[:, 0] = 1.0 - S[:, 0]
    Q[:, 1] = S[:, 0] - S[:, 1]
    Q[:, 2] = S[:, 1] - S[:, 2]
    Q[:, 3] = S[:, 2] - S[:, 3]
    Q[:, 4] = S[:, 3]
    Q = np.clip(Q, EPS, None)
    return Q / Q.sum(axis=1, keepdims=True)


_INC_CACHE: dict = {}


def _incumbent_surv(side: str, xs):
    """Survivors of the SHIPPED served distribution at odds grade x: p_bucket_given_fv
    then recalibrate_bucket. Cached on 2dp of x."""
    import value_framework as vf
    import efv_odds_calibration as _oc
    is_pit = side == "pit"
    out = np.empty((len(xs), 4))
    for i, x in enumerate(xs):
        k = (side, round(float(x), 2))
        v = _INC_CACHE.get(k)
        if v is None:
            p = vf.p_bucket_given_fv(k[1], is_pit)
            p = _oc.recalibrate_bucket(list(p), is_pit, provisional=False)
            v = _surv(np.asarray(p, dtype=float).reshape(1, 5))[0]
            _INC_CACHE[k] = v
        out[i] = v
    return out


def fit_idr(x, y):
    """FOUR PAVA fits, one per business threshold, on the SAME covariate. Unweighted: the
    evaluation is unweighted, so the fit is matched to the measure it is scored on."""
    from sklearn.isotonic import IsotonicRegression
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=int)
    isos = []
    for k in IDR_THRESHOLDS:
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True,
                                 out_of_bounds="clip")
        iso.fit(x, (y >= k).astype(float))
        isos.append(iso)
    return {"iso": isos, "xmin": float(x.min()), "xmax": float(x.max()), "n": int(len(x))}


def _idr_extend(fit, x, S, side):
    """H2. Above the training maximum the raw PAVA value is a flat clip. Carry the PAVA
    level at x_max and add the INCUMBENT's log-odds increment from x_max to x. Exact at
    x_max, monotone in x, and it does not invent a shape the lab has no data for."""
    above = np.asarray(x, dtype=float) > fit["xmax"] + 1e-12
    n_above = int(above.sum())
    if n_above:
        Sx = _incumbent_surv(side, np.asarray(x, dtype=float)[above])
        Sm = _incumbent_surv(side, np.array([fit["xmax"]]))[0]
        shift = _logit(np.clip(Sx, EPS, 1 - EPS)) - _logit(np.clip(Sm, EPS, 1 - EPS))[None, :]
        S = S.copy()
        S[above] = _sig(_logit(np.clip(S[above], EPS, 1 - EPS)) + shift)
    return S, above, n_above


def predict_idr(fit, x, side):
    """Returns (S, diag). `diag.raw_max_survivor_increase` is the STRUCTURAL ordinality
    check on the interpolation region, taken BEFORE any projection: it must be <= 0."""
    x = np.asarray(x, dtype=float)
    S = np.column_stack([fit["iso"][j].predict(x) for j in range(len(IDR_THRESHOLDS))])
    S_ext, above, n_above = _idr_extend(fit, x, S, side)
    interior = ~above
    raw_inc = float(np.max(np.diff(S[interior], axis=1))) if int(interior.sum()) else 0.0
    ext_inc = float(np.max(np.diff(S_ext[above], axis=1))) if n_above else 0.0
    return S_ext, {"raw_max_survivor_increase": raw_inc,
                   "extended_max_survivor_increase": ext_inc,
                   "n_above_train_max": n_above, "n_interior": int(interior.sum()),
                   "train_xmax": round(fit["xmax"], 4)}


def _tier_bin(fv):
    return np.digitize(np.asarray(fv, dtype=float), np.asarray(IDR_TIER_EDGES))


def idr_folds(frame):
    """Forward chain, per side. Train = NON-PROVISIONAL rows in strictly earlier decision
    years. Test = NON-PROVISIONAL rows in the year. Provisional rows are dropped from the
    primary frame entirely: `recalibrate_bucket` is a hard no-op on them, so every arm
    would emit the identical vector and their only effect is to dilute every delta by the
    same factor and inflate every arm's apparent skill together."""
    yr = np.array([r["decision_year"] for r in frame])
    sd = np.array([r["side"] for r in frame], dtype=object)
    pv = np.array([bool(r["provisional"]) for r in frame])
    out = []
    for side in ("hit", "pit"):
        sm = sd == side
        for t in sorted({int(v) for v in yr[sm].tolist()}):
            tr = np.where(sm & (yr < t) & ~pv)[0]
            te = np.where(sm & (yr == t) & ~pv)[0]
            if len(tr) < IDR_MIN_TRAIN or len(te) == 0:
                continue
            assert not (set(tr.tolist()) & set(te.tolist())), "H1: train/test overlap"
            out.append((side, int(t), tr, te))
    return out


def idr_arms(frame, folds, *, collect_diag=False):
    """All four arms on ONE index set. Returns (idx, {arm: Q}, diag)."""
    x = np.array([r["odds_grade"] for r in frame], dtype=float)
    y = np.array([r["y"] for r in frame], dtype=int)
    fvv = np.array([r["fv"] for r in frame], dtype=float)
    P_ship = np.array([r["p_ship"] for r in frame], dtype=float)
    tb = _tier_bin(fvv)
    idx_parts, parts = [], {a: [] for a in IDR_ARMS}
    diag = {"folds": [], "raw_max_survivor_increase": -np.inf,
            "extended_max_survivor_increase": -np.inf, "n_above_train_max": 0,
            "n_scored": 0, "tier_fallbacks": 0}
    for side, t, tr, te in folds:
        fit = fit_idr(x[tr], y[tr])
        S_cand, d = predict_idr(fit, x[te], side)
        # global climatology: the train-fold marginal, one constant vector for the fold
        g = np.array([float((y[tr] >= k).mean()) for k in IDR_THRESHOLDS])
        S_g = np.tile(g, (len(te), 1))
        # tier-marginal climatology: the train-fold marginal WITHIN the row's FV bin
        S_t = np.empty((len(te), len(IDR_THRESHOLDS)))
        for i, ti in enumerate(tb[te]):
            m = tb[tr] == ti
            if int(m.sum()) < IDR_MIN_TIER_TRAIN:
                S_t[i] = g
                diag["tier_fallbacks"] += 1
            else:
                S_t[i] = [float((y[tr][m] >= k).mean()) for k in IDR_THRESHOLDS]
        idx_parts.append(te)
        parts["candidate_idr"].append(_q_from_surv(S_cand))
        parts["clim_global"].append(_q_from_surv(S_g))
        parts["clim_tier"].append(_q_from_surv(S_t))
        parts["incumbent"].append(P_ship[te])
        diag["raw_max_survivor_increase"] = max(diag["raw_max_survivor_increase"],
                                                d["raw_max_survivor_increase"])
        diag["extended_max_survivor_increase"] = max(diag["extended_max_survivor_increase"],
                                                     d["extended_max_survivor_increase"])
        diag["n_above_train_max"] += d["n_above_train_max"]
        diag["n_scored"] += len(te)
        if collect_diag:
            diag["folds"].append({"side": side, "year": t, "n_train": int(len(tr)),
                                  "n_test": int(len(te)), **d,
                                  "train_marginal": [round(float(v), 5) for v in g]})
    if not idx_parts:
        return np.array([], dtype=int), {a: np.zeros((0, 5)) for a in IDR_ARMS}, diag
    idx = np.concatenate(idx_parts)
    o = np.argsort(idx, kind="stable")
    return idx[o], {a: np.vstack(parts[a])[o] for a in IDR_ARMS}, diag


# --- metric: mean RPS, and its CORP decomposition ----------------------------
def rps(Q, y) -> float:
    """Mean ranked probability score, sum of squared CDF errors over the four business
    thresholds. Lower is better."""
    S = _surv(np.asarray(Q, dtype=float))
    y = np.asarray(y, dtype=int)
    Z = np.column_stack([(y >= k).astype(float) for k in IDR_THRESHOLDS])
    return float(np.mean(np.sum((S - Z) ** 2, axis=1)))


def corp(Q, y) -> dict:
    """CORP decomposition. Per threshold the RPS term is a Brier score, and Brier =
    MCB - DSC + UNC with the reference forecasts produced by an IN-SAMPLE PAVA
    recalibration on the evaluation set (that is what makes it CORP: consistent,
    optimally binned, reproducible). Summed over thresholds this decomposes mean RPS.

    A CONSTANT arm gets DSC = 0 EXACTLY, because PAVA on a constant covariate returns the
    marginal, so its recalibrated score equals the climatological score."""
    from sklearn.isotonic import IsotonicRegression
    S = _surv(np.asarray(Q, dtype=float))
    y = np.asarray(y, dtype=int)
    per, tot = {}, {"score": 0.0, "MCB": 0.0, "DSC": 0.0, "UNC": 0.0}
    for j, k in enumerate(IDR_THRESHOLDS):
        z = (y >= k).astype(float)
        s = S[:, j]
        sbar = float(np.mean((s - z) ** 2))
        rc = IsotonicRegression(y_min=0.0, y_max=1.0,
                                out_of_bounds="clip").fit_transform(s, z)
        s_rc = float(np.mean((rc - z) ** 2))
        zb = float(z.mean())
        s_mg = float(zb * (1.0 - zb))
        per[f"y_ge_{k}"] = {
            "n_events": int(z.sum()), "base_rate": round(zb, 6),
            "brier": round(sbar, 6), "MCB": round(sbar - s_rc, 6),
            "DSC": round(s_mg - s_rc, 6), "UNC": round(s_mg, 6),
            "skill": round((s_mg - sbar) / s_mg, 6) if s_mg > 0 else None}
        tot["score"] += sbar
        tot["MCB"] += sbar - s_rc
        tot["DSC"] += s_mg - s_rc
        tot["UNC"] += s_mg
    res = tot["score"] - (tot["MCB"] - tot["DSC"] + tot["UNC"])
    return {"per_threshold": per,
            "total": {"mean_rps": round(tot["score"], 6), "MCB": round(tot["MCB"], 6),
                      "DSC": round(tot["DSC"], 6), "UNC": round(tot["UNC"], 6),
                      "skill_score": round((tot["DSC"] - tot["MCB"]) / tot["UNC"], 6)
                      if tot["UNC"] > 0 else None,
                      "identity_residual": round(res, 12)}}


def thr_brier(Q, y, j) -> float:
    S = _surv(np.asarray(Q, dtype=float))
    z = (np.asarray(y, dtype=int) >= IDR_THRESHOLDS[j]).astype(float)
    return float(np.mean((S[:, j] - z) ** 2))


def holm(pvals: dict) -> dict:
    """Holm-Bonferroni step-down. Returns {name: {"p", "p_holm", "reject"}}."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (name, p) in enumerate(items):
        adj = min(1.0, max(running, (m - i) * float(p)))
        running = adj
        out[name] = {"p_onesided": round(float(p), 6), "p_holm": round(adj, 6),
                     "reject_at_0.05": bool(adj < IDR_HOLM_ALPHA)}
    return out


def venn_abers(x_tr, z_tr, x_te):
    """Vovk IVAP. For each test point, refit the isotonic twice with the test label forced
    to 0 and to 1. [p0, p1] is the multiprobability interval; p0 <= p1 always."""
    from sklearn.isotonic import IsotonicRegression
    x_tr = np.asarray(x_tr, dtype=float)
    z_tr = np.asarray(z_tr, dtype=float)
    p0, p1 = [], []
    for xv in np.asarray(x_te, dtype=float):
        for lab, acc in ((0.0, p0), (1.0, p1)):
            iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            iso.fit(np.append(x_tr, xv), np.append(z_tr, lab))
            acc.append(float(iso.predict([xv])[0]))
    return np.asarray(p0), np.asarray(p1)


# --- the rank-invariance proof ----------------------------------------------
def rank_feedback_audit() -> dict:
    """POSITIVE EVIDENCE that a recalibration at the odds seam cannot reach `rank_war`.

    Not a grep. For every function in efv_score.py that assigns `rank_war`, the assignment
    graph is walked in source order and the TRANSITIVE dependency closure of `rank_war` is
    computed; `probs` (the recalibrated vector) must not be in it. The FORWARD closure of
    `probs` is computed too, and must not intersect the rank/grade names. Both directions,
    because one-directional reasoning is how the -0.0165 got shipped last time."""
    import ast
    src_text = (ROOT / "efv_score.py").read_text(encoding="utf-8")
    tree = ast.parse(src_text)
    rank_names = {"rank_war", "_rank_exact"}
    grade_names = {"xfv_grade", "xfv_war", "cons_war", "cons_fv", "_odds_grade", "lam"}
    seam_name = "probs"
    fns = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = list(ast.walk(node))
        if not any(isinstance(s, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in rank_names for t in s.targets)
                for s in body):
            continue
        deps: dict = {}
        fwd: dict = {}
        rank_line = seam_line = None
        for s in body:
            if not isinstance(s, ast.Assign):
                continue
            rhs = {n.id for n in ast.walk(s.value) if isinstance(n, ast.Name)}
            closure = set(rhs)
            for r in rhs:
                closure |= deps.get(r, set())
            for tgt in s.targets:
                for nm in (n.id for n in ast.walk(tgt) if isinstance(n, ast.Name)):
                    deps[nm] = set(closure)
                    fwd[nm] = set(closure)
                    if nm in rank_names and rank_line is None:
                        rank_line = s.lineno
            if "recalibrate_bucket" in ast.dump(s.value) and seam_line is None:
                seam_line = s.lineno
        rank_dep = set()
        for nm in rank_names:
            rank_dep |= deps.get(nm, set())
        seam_reach = {nm for nm, c in fwd.items() if seam_name in c}
        fns.append({
            "function": node.name, "lineno": node.lineno,
            "rank_assign_line": rank_line, "recalibrate_bucket_line": seam_line,
            "seam_name_in_rank_dependency_closure": bool(seam_name in rank_dep),
            "rank_assigned_before_seam": bool(seam_line is None or rank_line is None
                                              or rank_line < seam_line),
            "names_downstream_of_seam": sorted(seam_reach)[:24],
            "downstream_of_seam_intersects_rank_or_grade":
                sorted(seam_reach & (rank_names | grade_names)),
            "rank_dependency_closure_size": len(rank_dep),
        })
    clean = all(not f["seam_name_in_rank_dependency_closure"]
                and f["rank_assigned_before_seam"]
                and not f["downstream_of_seam_intersects_rank_or_grade"] for f in fns)
    return {
        "method": ("AST assignment-graph closure over efv_score.py, both directions, on "
                   "every function that assigns rank_war"),
        "functions_examined": fns,
        "n_functions": len(fns),
        "seam_cannot_reach_rank": bool(clean),
        "structural_argument": (
            "PATH A lands on `probs` at efv_score's three odds seams. `rank_war` is "
            "assigned from (1 - lam) * cons_war + lam * xfv_war on the line BEFORE the "
            "first seam, and the display grade is a quantile map of the sorted rank_war "
            "pool. docs/EFV_GATE_STANDARD.md section 4 records that served eFV surplus is "
            "a function of rank ONLY with respect to rank_war, so a downstream-only "
            "recalibration is rank-invariant BY CONSTRUCTION."),
        "dollar_argument": (
            "vf.expected_surplus_usd prices through _pipeline_surplus_from_svs "
            "(value_framework.py:1371-1376), which calls p_bucket_given_fv ITSELF at the "
            "DISPLAY grade and takes no probability argument. No map applied at the odds "
            "seam can reach surplus_mm, band_p10_mm, band_p90_mm or dist."),
        "consumers_of_the_recalibrated_vector": [
            "data/xfv.json p_bucket (efv_score.py:1514) and p_bust (:1521)",
            "efv_export.py:87,91 pass-through, and the :301 p_star_median tier display",
            "efv_reliability.py, the calibration monitor",
            "assets/trademachine.js:779,983 read p_bust for DISPLAY only",
        ],
    }


# --- the B-L5 run ------------------------------------------------------------
def _boot_p(deltas) -> float:
    """One-sided bootstrap p for `candidate is better`, i.e. P(delta <= 0) where delta is
    other_arm_score - candidate_score and lower score is better."""
    v = np.asarray([d for d in deltas if np.isfinite(d)], dtype=float)
    return float((v <= 0.0).mean()) if len(v) else 1.0


def _floor95(vals, point) -> dict:
    """The C2 floor helper above, REUSED verbatim, with its two Bonferroni-k5 fields
    dropped: this lane corrects for multiplicity with Holm over a 3-contrast family, and
    leaving a k=5 Bonferroni column beside a Holm p is an invitation to quote the wrong
    one."""
    out = _floor(list(vals), point)
    out.pop("mde_bonferroni_k5", None)
    out.pop("margin_over_bonferroni", None)
    out.pop("clears_bonferroni", None)
    return out


def run_idr(quick: bool = False, persist: bool = True) -> dict:
    t0 = time.time()
    rng = np.random.default_rng(IDR_SEED)
    frame = build_frame()
    folds = idr_folds(frame)
    idx, Q, diag = idr_arms(frame, folds, collect_diag=True)
    y = np.array([frame[i]["y"] for i in idx], dtype=int)
    fvv = np.array([frame[i]["fv"] for i in idx], dtype=float)
    xg = np.array([frame[i]["odds_grade"] for i in idx], dtype=float)
    tiers = np.rint(fvv / 5.0).astype(int) * 5

    rep: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lane": "B-L5 (2026-08-10)",
        "produced_by": "tools/efv_dist_recalibration_lab.py --idr",
        "family": ("IDR / EasyUQ: four PAVA fits on odds_grade -> 1{y >= k}, k = 1..4. "
                   "Ordinality is STRUCTURAL because the four response vectors are "
                   "pointwise ordered and PAVA is monotone in its response."),
        "scope_note": ("FITS and GATES. Ships nothing. Writes only this artifact. "
                       "PATH A (the efv_score odds seam), strictly downstream of rank_war."),
        "seed": IDR_SEED,
        "differs_from_prior_attempts": {
            "C2_above": "parametric cumulative-logit Platt families only. NO_SHIP.",
            "X_ISO_efv_isotonic_lab": ("isotonic PER BUCKET on p_b vs 1{y == b} WITH "
                                       "simplex renormalization, which is not IDR and is "
                                       "not order preserving. FAIL on calibrated rank, "
                                       "Spearman -0.0165 against a -0.002 tolerance."),
            "this_lane": ("four PAVA fits on the THRESHOLD indicators, no renormalization "
                          "needed, and the map is confined downstream of rank_war so a "
                          "rank tolerance is not even the binding object."),
        },
        "prereg": {
            "min_train": IDR_MIN_TRAIN, "min_tier_train": IDR_MIN_TIER_TRAIN,
            "tier_edges": list(IDR_TIER_EDGES), "holm_alpha": IDR_HOLM_ALPHA,
            "arms": list(IDR_ARMS), "thresholds": list(IDR_THRESHOLDS),
            "primary_metric": "mean RPS, sum of squared CDF errors over the 4 thresholds",
            "decomposition": "CORP: score = MCB - DSC + UNC, per threshold and summed",
            "estimators": ["E_cond (fits fixed, rows resampled)",
                           "E_refit restricted (frame resampled, IDR chain refit; the "
                           "upstream ridge is held fixed, so it is a LOWER BOUND)"],
            "ship_clauses": [
                "V0 validity: every arm sums to 1, no negatives, raw PAVA fits ordinal",
                "V1 H1: train/test index disjointness asserted per fold",
                "G1 mean RPS candidate < incumbent, Holm p < 0.05 under BOTH estimators",
                "G2 candidate beats BOTH climatologies, Holm p < 0.05 under E_cond and "
                "point-better under E_refit",
                "G3 DSC_candidate > DSC_incumbent AND MCB_candidate < MCB_incumbent",
                "G4 do no harm: no threshold's Brier degrades past its own E_cond floor",
                "G5 rank_feedback_audit clean",
                "STOP log score materially worse than incumbent -> NO_SHIP regardless",
            ],
        },
        "frame": {
            "n_frame_rows": len(frame),
            "n_primary_scored": int(len(idx)),
            "provisional_dropped_from_primary": int(sum(1 for r in frame if r["provisional"])),
            "folds": diag["folds"],
            "n_folds": len(folds),
            "events_by_threshold": {f"y_ge_{k}": int((y >= k).sum()) for k in IDR_THRESHOLDS},
            "rows_by_tier": {str(int(t)): int((tiers == t).sum())
                             for t in sorted(set(tiers.tolist()))},
            "note": ("PRIMARY is the NON-PROVISIONAL evaluable frame. recalibrate_bucket "
                     "is a hard no-op on provisional rows, so every arm would emit an "
                     "identical vector there and their only effect is to dilute all four "
                     "arms by the same factor."),
            "matrix_mtimes": {s: time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(_matrix_mtime(s))) for s in ("hit", "pit")},
        },
        "ordinality": {
            "claim": ("STRUCTURAL. The four PAVA fits cannot cross because the response "
                      "vectors are pointwise ordered."),
            "raw_max_survivor_increase": round(diag["raw_max_survivor_increase"], 12),
            "held_structurally": bool(diag["raw_max_survivor_increase"] <= 0.0),
            "extension_max_survivor_increase": round(diag["extended_max_survivor_increase"], 12)
            if diag["n_above_train_max"] else None,
            "extension_held": bool(diag["n_above_train_max"] == 0
                                   or diag["extended_max_survivor_increase"] <= 0.0),
            "reading": ("a POSITIVE value means two fitted curves crossed, which under "
                        "pointwise-ordered responses can only mean the fit is wrong"),
        },
        "H2_extrapolation": {
            "n_rows_above_train_max": diag["n_above_train_max"],
            "share_above_train_max": round(diag["n_above_train_max"] / max(1, len(idx)), 5),
            "how_smoothed": ("carry the PAVA level at x_max, add the INCUMBENT curve's own "
                             "log-odds increment from x_max to x. Exact at x_max, monotone "
                             "in x, invents no shape the data cannot support."),
        },
        "H1_out_of_fold": {
            "asserted": True,
            "how": ("idr_folds asserts set(train) & set(test) is empty for every fold, and "
                    "train is restricted to decision_year strictly less than the test year, "
                    "so no row can calibrate itself and no cohort can calibrate itself"),
        },
        "tier_climatology_fallbacks": diag["tier_fallbacks"],
    }

    # --- validity ------------------------------------------------------------
    val = {"pass": True, "detail": {}}
    for a in IDR_ARMS:
        Qa = Q[a]
        S = _surv(Qa)
        ok = (abs(Qa.sum(axis=1) - 1.0).max() < 1e-9 and int((Qa < -1e-12).sum()) == 0
              and float(np.max(np.diff(S, axis=1))) <= 1e-9)
        val["detail"][a] = {
            "max_abs_sum_err": round(float(abs(Qa.sum(axis=1) - 1.0).max()), 12),
            "n_negative": int((Qa < -1e-12).sum()),
            "max_survivor_increase": round(float(np.max(np.diff(S, axis=1))), 12),
            "pass": bool(ok)}
        val["pass"] = val["pass"] and ok
    rep["validity"] = val

    # --- the four-arm table --------------------------------------------------
    table = {}
    for a in IDR_ARMS:
        c = corp(Q[a], y)
        table[a] = {
            "mean_rps": c["total"]["mean_rps"], "MCB": c["total"]["MCB"],
            "DSC": c["total"]["DSC"], "UNC": c["total"]["UNC"],
            "skill_score": c["total"]["skill_score"],
            "corp_identity_residual": c["total"]["identity_residual"],
            "logscore": round(logscore(Q[a], y), 6),
            "brier5": round(brier(Q[a], y), 6),
            "per_threshold": c["per_threshold"],
            "mean_p": {BUCKETS[b]: round(float(Q[a][:, b].mean()), 5) for b in range(5)},
        }
    rep["four_arm_table"] = table
    rep["four_arm_table_note"] = (
        "ONE table, every time. A zero-information constant scores UNC exactly and gets "
        "skill 0 by construction; that is the structural fix for the ECE regime in which "
        "a constant reached 152.68 percent of the candidate gain.")

    d_point = {o: table[o]["mean_rps"] - table["candidate_idr"]["mean_rps"]
               for o in ("incumbent", "clim_global", "clim_tier")}
    rep["point_deltas_rps_other_minus_candidate"] = {k: round(v, 6) for k, v in d_point.items()}

    # --- E_cond --------------------------------------------------------------
    B_cond, B_refit = (200, 40) if quick else (2000, 400)
    n = len(idx)
    dc = {o: [] for o in d_point}
    dls, dthr = [], {j: [] for j in range(4)}
    for bi in range(B_cond):
        if bi % 250 == 0:
            print(f"  IDR E_cond {bi}/{B_cond}", flush=True)
        s = rng.integers(0, n, n)
        ys = y[s]
        rc = rps(Q["candidate_idr"][s], ys)
        for o in d_point:
            dc[o].append(rps(Q[o][s], ys) - rc)
        dls.append(logscore(Q["incumbent"][s], ys) - logscore(Q["candidate_idr"][s], ys))
        for j in range(4):
            dthr[j].append(thr_brier(Q["incumbent"][s], ys, j)
                           - thr_brier(Q["candidate_idr"][s], ys, j))
    rep["E_cond"] = {
        "instrument": "fits held FIXED, scored rows resampled i.i.d., B = %d" % B_cond,
        "vs": {o: dict(_floor95(dc[o], d_point[o]),
                       p_onesided=round(_boot_p(dc[o]), 6)) for o in d_point},
        "logscore_incumbent_minus_candidate": _floor95(
            dls, table["incumbent"]["logscore"] - table["candidate_idr"]["logscore"]),
        "per_threshold_brier_incumbent_minus_candidate": {
            f"y_ge_{IDR_THRESHOLDS[j]}": _floor95(
                dthr[j], thr_brier(Q["incumbent"], y, j) - thr_brier(Q["candidate_idr"], y, j))
            for j in range(4)},
    }
    rep["E_cond"]["holm"] = holm({o: rep["E_cond"]["vs"][o]["p_onesided"] for o in d_point})

    # --- E_refit (restricted) ------------------------------------------------
    dr = {o: [] for o in d_point}
    nfr = len(frame)
    for bi in range(B_refit):
        if bi % 50 == 0:
            print(f"  IDR E_refit {bi}/{B_refit}", flush=True)
        r = np.random.default_rng(IDR_SEED * 1000 + bi)
        boot = [frame[j] for j in r.integers(0, nfr, nfr)]
        try:
            ib, Qb, _ = idr_arms(boot, idr_folds(boot))
        except Exception:                                       # noqa: BLE001
            continue
        if len(ib) == 0:
            continue
        yb = np.array([boot[j]["y"] for j in ib], dtype=int)
        rc = rps(Qb["candidate_idr"], yb)
        for o in d_point:
            dr[o].append(rps(Qb[o], yb) - rc)
    rep["E_refit_restricted"] = {
        "instrument": ("frame resampled with replacement and the IDR chain REFIT per draw; "
                       "the upstream ridge and its output calibration are INPUTS to this "
                       "lane and are held fixed, so this is a LOWER BOUND on refit "
                       "variance. B = %d" % B_refit),
        "vs": {o: dict(_floor95(dr[o], d_point[o]),
                       p_onesided=round(_boot_p(dr[o]), 6)) for o in d_point},
    }
    rep["E_refit_restricted"]["holm"] = holm(
        {o: rep["E_refit_restricted"]["vs"][o]["p_onesided"] for o in d_point})

    # --- H3 Venn-Abers at the FV60 star cell ---------------------------------
    rep["H3_venn_abers_star_cell"] = _venn_abers_cells(frame, folds, idx, y, tiers, Q)

    # --- G5 rank invariance --------------------------------------------------
    rep["G5_rank_feedback_audit"] = rank_feedback_audit()

    # --- verdict -------------------------------------------------------------
    ec, er = rep["E_cond"], rep["E_refit_restricted"]
    g1 = bool(d_point["incumbent"] > 0
              and ec["holm"]["incumbent"]["reject_at_0.05"]
              and er["holm"]["incumbent"]["reject_at_0.05"])
    g2 = bool(all(d_point[o] > 0 and ec["holm"][o]["reject_at_0.05"]
                  for o in ("clim_global", "clim_tier"))
              and all(d_point[o] > 0 for o in ("clim_global", "clim_tier")))
    g3 = bool(table["candidate_idr"]["DSC"] > table["incumbent"]["DSC"]
              and table["candidate_idr"]["MCB"] < table["incumbent"]["MCB"])
    harmed = [k for k, v in ec["per_threshold_brier_incumbent_minus_candidate"].items()
              if v["point_delta"] < -v["mde95_onesided"]]
    g4 = not harmed
    g5 = bool(rep["G5_rank_feedback_audit"]["seam_cannot_reach_rank"])
    stop_ls = bool(ec["logscore_incumbent_minus_candidate"]["point_delta"]
                   < -ec["logscore_incumbent_minus_candidate"]["mde95_onesided"])
    ord_ok = bool(rep["ordinality"]["held_structurally"] and rep["ordinality"]["extension_held"])
    clauses = {
        "V0_validity_and_ordinality": {"pass": bool(val["pass"] and ord_ok),
                                       "arms_valid": val["pass"], "ordinal": ord_ok},
        "V1_out_of_fold_asserted": {"pass": True},
        "G1_beats_incumbent_both_estimators": {
            "pass": g1, "point_delta_rps": round(d_point["incumbent"], 6),
            "e_cond_holm_p": ec["holm"]["incumbent"]["p_holm"],
            "e_refit_holm_p": er["holm"]["incumbent"]["p_holm"]},
        "G2_beats_both_climatologies": {
            "pass": g2,
            "vs_clim_global": round(d_point["clim_global"], 6),
            "vs_clim_tier": round(d_point["clim_tier"], 6),
            "e_cond_holm_p": {o: ec["holm"][o]["p_holm"]
                              for o in ("clim_global", "clim_tier")},
            "e_refit_point_better": {o: bool(d_point[o] > 0)
                                     for o in ("clim_global", "clim_tier")}},
        "G3_discrimination_and_calibration": {
            "pass": g3,
            "DSC_candidate": table["candidate_idr"]["DSC"],
            "DSC_incumbent": table["incumbent"]["DSC"],
            "MCB_candidate": table["candidate_idr"]["MCB"],
            "MCB_incumbent": table["incumbent"]["MCB"]},
        "G4_do_no_harm_per_threshold": {"pass": g4, "harmed": harmed},
        "G5_rank_invariance": {"pass": g5},
        "STOP_logscore_worse": {"tripped": stop_ls,
                                "delta": ec["logscore_incumbent_minus_candidate"]["point_delta"]},
    }
    if not clauses["V0_validity_and_ordinality"]["pass"] or not g5 or stop_ls or not g1:
        verdict = "NO_SHIP"
    elif g2 and g3 and g4:
        verdict = "SHIP_READY"
    else:
        verdict = "PARTIAL"
    rep["clauses"] = clauses
    rep["verdict"] = verdict

    # =========================================================================
    # POST-HOC. WRITTEN AFTER THE PRIMARY NUMBERS WERE KNOWN, PLACED AFTER THE
    # VERDICT IS ALREADY COMPUTED, AND CHANGING NO CLAUSE AND NO THRESHOLD. It
    # exists because a pre-registered clause failed and the reason is measurable.
    # =========================================================================
    d_mcb, d_dsc = [], []
    for bi in range(B_cond):
        s = rng.integers(0, n, n)
        ys = y[s]
        ci = corp(Q["incumbent"][s], ys)["total"]
        cc = corp(Q["candidate_idr"][s], ys)["total"]
        d_mcb.append(ci["MCB"] - cc["MCB"])
        d_dsc.append(ci["DSC"] - cc["DSC"])
    from sklearn.isotonic import IsotonicRegression                      # noqa: F401
    blocks = []
    for side, t, tr, te in folds:
        fit = fit_idr(np.array([frame[i]["odds_grade"] for i in tr], dtype=float),
                      np.array([frame[i]["y"] for i in tr], dtype=int))
        blocks.append({"side": side, "year": t, "n_train": int(len(tr)),
                       "distinct_fitted_levels": [
                           int(len(np.unique(np.round(fit["iso"][j].y_thresholds_, 9))))
                           for j in range(4)]})
    mids = None
    try:
        import value_framework as vf
        from prospect_path import _spearman
        mids = {"hit": np.asarray(vf._calibrated_midpoints("hitter"), dtype=float),
                "pit": np.asarray(vf._calibrated_midpoints("pitcher"), dtype=float)}
        tgt = [float(frame[i]["target"]) for i in idx]
        sides = [frame[i]["side"] for i in idx]
        rho = {}
        for a in IDR_ARMS:
            ev = [float(np.dot(Q[a][i], mids[sides[i]])) for i in range(len(idx))]
            rho[a] = round(float(_spearman(ev, tgt)), 5)
        rho["odds_grade_itself"] = round(float(_spearman(xg.tolist(), tgt)), 5)
    except Exception as exc:                                             # noqa: BLE001
        rho = {"error": str(exc)}
    rep["posthoc_added_after_primary_run"] = {
        "disclosure": ("Written after the primary numbers were known and placed after the "
                       "verdict. Changes no clause, no threshold, no verdict."),
        "why_G3_failed_arithmetically": {
            "delta_rps": round(d_point["incumbent"], 6),
            "delta_MCB_incumbent_minus_candidate": round(
                table["incumbent"]["MCB"] - table["candidate_idr"]["MCB"], 6),
            "delta_DSC_incumbent_minus_candidate": round(
                table["incumbent"]["DSC"] - table["candidate_idr"]["DSC"], 6),
            "identity": "delta_rps = delta_MCB - delta_DSC",
            "reading": ("the entire RPS gain, and MORE than all of it, is bought by "
                        "removing miscalibration; the candidate PAYS discrimination for it. "
                        "That is PAVA blocking: blocks are ties and ties are lost "
                        "resolution. It is the same mechanism that killed X-ISO on rank, "
                        "showing up here as a DSC debit rather than a Spearman debit."),
            "E_cond_floor_delta_MCB": _floor95(
                d_mcb, table["incumbent"]["MCB"] - table["candidate_idr"]["MCB"]),
            "E_cond_floor_delta_DSC": _floor95(
                d_dsc, table["incumbent"]["DSC"] - table["candidate_idr"]["DSC"]),
        },
        "pava_resolution_cost": {
            "distinct_fitted_levels_per_fold": blocks,
            "reading": ("one level per threshold means the fold's PAVA collapsed to a "
                        "constant and contributed no discrimination at all"),
        },
        "forbidden_wiring_counterfactual": {
            "what": ("Spearman of E[WAR] under each arm against the realized target. This "
                     "is NOT wired and MUST NOT be: it is the measurement of what the "
                     "banned feedback would cost, and it is here so the next reader can "
                     "see the size of the trap rather than rediscover it."),
            "spearman": rho,
        },
        "top_of_board_bound": (
            "the FV55+ cell is the first instrument in this program to BOUND the "
            "top-of-board over-prediction rather than point-estimate it; see "
            "H3_venn_abers_star_cell"),
    }
    rep["if_it_ships"] = {
        "this_lane_does_neither": True,
        "owed_1": ("epoch bump: the served p_bucket / p_bust vectors change on "
                   "non-provisional rows, so the artifact epoch that stamps xfv.json must "
                   "be incremented by whoever wires it"),
        "owed_2": ("config/valuation_sets/prospx_current.yaml re-capture, because the "
                   "capture records the served odds surface"),
        "owed_3": "regen tripwires in docs/EFV_REGEN_TRIPWIRES_2026-08-07.md re-stamped",
        "note_on_prices": ("MEASURED, not assumed: PATH A moves NO price. "
                           "vf.expected_surplus_usd re-derives p_bucket_given_fv itself at "
                           "the DISPLAY grade, so surplus_mm / band_p10_mm / band_p90_mm / "
                           "dist are byte-identical under any odds-seam map. The lane brief "
                           "premise 'if it ships it moves prices' is FALSE for PATH A."),
    }
    rep["elapsed_s"] = round(time.time() - t0, 1)

    if persist:
        cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        cur["lane_b_l5_idr_easyuq"] = rep
        cur["multi_lane_note"] = (
            "Two lanes write this artifact. The top-level keys are LANE C2 (2026-08-08), "
            "parametric cumulative-logit Platt, verdict NO_SHIP, on the frame of that day. "
            "`lane_b_l5_idr_easyuq` is LANE B-L5 (2026-08-10), IDR / EasyUQ at the four "
            "business thresholds, on a REBUILT frame. The two frames are different "
            "vintages and their absolute numbers are NOT comparable across blocks; each "
            "block carries its own incumbent arm.")
        OUT.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    print(f"IDR verdict={verdict} n={len(idx)} dRPS_vs_inc={d_point['incumbent']:+.6f} "
          f"elapsed={rep['elapsed_s']}s")
    return rep


def _matrix_mtime(side: str) -> float:
    from efv_dataset import matrix_path
    return matrix_path(side).stat().st_mtime


def _venn_abers_cells(frame, folds, idx, y, tiers, Q) -> dict:
    """H3. The FV60 star cell as an INTERVAL. Per test row, IVAP against its own fold's
    train set on the star indicator; the cell is summarised by the mean of p0 and the mean
    of p1, which is the interval a cell-level rate must be read inside."""
    x = np.array([r["odds_grade"] for r in frame], dtype=float)
    yf = np.array([r["y"] for r in frame], dtype=int)
    pos = {int(v): i for i, v in enumerate(idx)}
    out = {}
    for tier_label, sel in (("FV60", lambda t: t == IDR_STAR_TIER),
                            ("FV55", lambda t: t == 55),
                            ("FV60_plus", lambda t: t >= IDR_STAR_TIER),
                            ("FV55_plus", lambda t: t >= 55)):
        p0s, p1s, cand, inc, rows, ev = [], [], [], [], 0, 0
        for side, t, tr, te in folds:
            keep = [i for i in te if i in pos and sel(int(round(frame[i]["fv"] / 5.0) * 5))]
            if not keep:
                continue
            a0, a1 = venn_abers(x[tr], (yf[tr] >= 4).astype(float), x[keep])
            p0s.extend(a0.tolist())
            p1s.extend(a1.tolist())
            for i in keep:
                cand.append(float(Q["candidate_idr"][pos[i], 4]))
                inc.append(float(Q["incumbent"][pos[i], 4]))
                ev += int(yf[i] >= 4)
                rows += 1
        if not rows:
            out[tier_label] = {"n_rows": 0}
            continue
        out[tier_label] = {
            "n_rows": rows, "n_star_events": ev,
            "realized_rate": round(ev / rows, 5),
            "venn_abers_interval_mean": [round(float(np.mean(p0s)), 5),
                                         round(float(np.mean(p1s)), 5)],
            "venn_abers_interval_widest_row": [round(float(np.min(p0s)), 5),
                                               round(float(np.max(p1s)), 5)],
            "candidate_mean_p_star": round(float(np.mean(cand)), 5),
            "incumbent_mean_p_star": round(float(np.mean(inc)), 5),
            "incumbent_inside_interval": bool(np.mean(p0s) <= np.mean(inc) <= np.mean(p1s)),
            "candidate_inside_interval": bool(np.mean(p0s) <= np.mean(cand) <= np.mean(p1s)),
        }
    out["reading"] = ("Vovk IVAP. p0 is the isotonic prediction with the test label forced "
                      "to 0 and p1 with it forced to 1; the true probability is not a "
                      "point and this interval is its honest width at this sample size.")
    return out


if __name__ == "__main__":
    _chunk = next((a for a in sys.argv[1:] if a.startswith("--refit-chunk=")), None)
    if _chunk:
        a, b = _chunk.split("=")[1].split(":")
        fr = build_frame()
        todo = [i for i in range(int(a), int(a) + int(b)) if i not in _read_refit_draws()]
        print(f"refit chunk {a}:{b} -> {len(todo)} draws to compute", flush=True)
        refit_chunk(fr, todo)
        print(f"have {len(_read_refit_draws())} draws", flush=True)
    elif "--idr" in sys.argv:
        run_idr(quick="--quick" in sys.argv, persist="--dry" not in sys.argv)
    else:
        main(quick="--quick" in sys.argv)
