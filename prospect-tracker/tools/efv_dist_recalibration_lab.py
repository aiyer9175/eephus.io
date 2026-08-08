# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE C2 (master plan 2026-08-07b): fit, gate and PREPARE the served eFV outcome
distribution recalibration. SHIPS NOTHING.

Pre-registration: docs/efv-2026-08-07b/DISTRIBUTION_RECALIBRATION_GATE.md sections 0-5,
written in full before this file existed. Artifact: data/xfv_dist_recalibration_eval.json.

Run:  python tools/efv_dist_recalibration_lab.py
      python tools/efv_dist_recalibration_lab.py --quick   (small B, smoke test only)

Writes ONLY data/xfv_dist_recalibration_eval.json. Touches no served artifact, no config,
no test, and no module outside tools/.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRATCH = Path(r"C:\Users\noah\AppData\Local\Temp\claude"
               r"\c--Users-noah-baseball-projects-BaseballR"
               r"\51d4716c-ebca-464e-b136-f45585e28ab6\scratchpad")
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

    def _floor(vals, point):
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


if __name__ == "__main__":
    _chunk = next((a for a in sys.argv[1:] if a.startswith("--refit-chunk=")), None)
    if _chunk:
        a, b = _chunk.split("=")[1].split(":")
        fr = build_frame()
        todo = [i for i in range(int(a), int(a) + int(b)) if i not in _read_refit_draws()]
        print(f"refit chunk {a}:{b} -> {len(todo)} draws to compute", flush=True)
        refit_chunk(fr, todo)
        print(f"have {len(_read_refit_draws())} draws", flush=True)
    else:
        main(quick="--quick" in sys.argv)
