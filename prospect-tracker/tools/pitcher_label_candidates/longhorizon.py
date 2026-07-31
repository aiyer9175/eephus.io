# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SPAN-ADAPTIVE LONG-HORIZON pitcher label instrument.

One instrument, four calibrations. A pitcher censored after 2 MLB seasons and one
censored after 5 are NOT the same estimation problem: at span 2 only ~22% of the
6-year WAR mass is observed, at span 5 ~85%. So the instrument fits a SEPARATE map per
span (2,3,4,5), each on the same early cohort but on that span's own window, and at
predict time uses the map for the longest horizon actually available for the row.

Three pieces per span:
  1. SCORE   ridge on standardized post-debut window features (cumulative WAR + the
     trajectory/workload/role/rate fields the diagnostics said WAR-sum does not carry:
     last-season WAR and IP, WAR/IP slope, gs_ratio level and drift, kbb/k_pct gated on
     real exposure, appear_frac, age at debut). Target is the NORMAL SCORE of true6, not
     true6 - the transmission diagnostic showed the label->model channel is ~pure rank.
  2. TRANSPORT  the score's percentile (against the fitted cohort's out-of-fold score
     distribution) is mapped onto the early-cohort TRUE 6yr WAR marginal. Order comes
     from the model, magnitude is borrowed - exactly the D-arm construction that carried
     97.7% of the oracle headroom in the transmission diagnostic.
  3. SHRINK  toward the cohort mean by a per-span reliability weight estimated
     out-of-fold on the fitting cohort (OLS slope of true6 on the transported value,
     clipped to [0,1]). Short spans are noisy and get pulled to the mean; span 5 is
     nearly unshrunk. Rank is untouched; only level moves.

Sparsity handling (the horizon diagnostic's #5/#6): nominal span overstates observed
data (the 2023 production cohort averages 2.40 actual MLB seasons in a 3-season window,
and ~10% of the 2021 cohort has no resolvable mlbam id at all). Every feature is
per-season normalized, appear_frac / has_lines enter explicitly, and a WAR-ONLY map is
fitted per span and used verbatim for rows with no MLB lines, so an id-resolution
failure cannot be read as a zero-appearance bust.

CIRCULARITY: every input is post-debut REALIZED outcome data (career WAR by season, MLB
pitching lines, TJ years, age off the MLB line). rec['row'] - consensus FV, tool grades,
draft pick/bonus - is NEVER read.

MEASURED (2026-07-24, `python tools/pitcher_label_candidates/longhorizon.py 2 3 4 5`,
pool 530 pit / early 216 / mid 132 / test 180, oracle blend rho 0.2260 at every span):

  span | KM blend | LH_span_adaptive | LH_order_only | %headroom (adaptive / order)
    2  |  0.0806  |     0.1537       |    0.1561     |  50.3% / 51.9%
    3  |  0.1164  |     0.1190       |    0.1193     |   2.4% /  2.6%
    4  |  0.1947  |     0.1968       |    0.2151     |   6.7% / 65.2%
    5  |  0.1936  |     0.1964       |    0.2025     |   8.6% / 27.5%

  Paired bootstrap vs KM (B=1000): span2 order_only +0.0763 sd 0.0256 P(>0)=1.000;
  span4 order_only +0.0205 sd 0.0111 CI95 [+0.0003,+0.0437] P=0.975; span3 +0.0013
  sd 0.0256 P=0.526 (a null). Against the FREE fallback of dropping the censored block
  (blend 0.1542): span4 +0.0604 P=0.902, span2 +0.0031 P=0.527, span3 -0.0366 P=0.266.

  HONEST NOTE ON THE TWO ARMS. The mass-share blend (LH_span_adaptive) was chosen a
  priori from mid-cohort label fidelity, where the additive arm looks better at long
  spans (mid label rho 0.8827 vs 0.8558 at span 4). On the held-out test the ORDERING
  arm wins by a wide margin at span 4 - i.e. the arm with the WORSE label rho produces
  the BETTER model, exactly as the transmission diagnostic predicted (rank is the
  channel; fidelity is not the objective). Mid label fidelity is therefore a MISLEADING
  selection criterion here; treat the order-only preference as theory-consistent but
  test-observed, not independently validated.

Usage:  python tools/pitcher_label_candidates/longhorizon.py [span ...]
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np                              # noqa: E402
import efv_pitcher_label_harness as H           # noqa: E402
from prospect_path import _spearman             # noqa: E402

TARGET_SEASONS = 6
SPANS = (1, 2, 3, 4, 5)
AGE_FILL = 24.5


# ---------------------------------------------------------------------------
# features - post-debut realized outcome data only
# ---------------------------------------------------------------------------

def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _age_debut(rec):
    for i in range(TARGET_SEASONS):
        ln = rec["lines"].get(i)
        if ln and ln.get("age") not in (None, ""):
            try:
                return float(ln["age"]) - i
            except (TypeError, ValueError):
                return None
    return None


def feats(rec: dict, span: int) -> dict:
    """H.window() plus per-season trajectory + sparsity fields, all span-normalized."""
    w = dict(H.window(rec, span))
    span_f = float(max(1, span))
    war_by = [_f(rec["war"].get(i)) for i in range(span)]
    ips, gsr, app = [], [], []
    for i in range(span):
        ln = rec["lines"].get(i)
        if not ln:
            ips.append(0.0), gsr.append(0.0), app.append(0.0)
            continue
        ip_i, g_i = _f(ln.get("ip")), _f(ln.get("g"))
        ips.append(ip_i)
        gsr.append((_f(ln.get("gs")) / g_i) if g_i else 0.0)
        app.append(1.0 if ip_i > 0 else 0.0)
    last = span - 1
    seen = w["seasons_pitched"]
    age = _age_debut(rec)
    exposure = min(1.0, w["ip"] / 80.0)          # rate stats only mean something with IP

    w.update({
        "has_lines": 1.0 if seen > 0 else 0.0,
        "appear_frac": seen / span_f,
        "log_ip_ps": math.log1p(max(0.0, w["ip"]) / span_f),
        "log_ip_last": math.log1p(max(0.0, ips[last] if ips else 0.0)),
        "ip_last": ips[last] if ips else 0.0,
        "ip_max": max(ips) if ips else 0.0,
        "ip_slope": ((ips[last] - ips[0]) / max(1, span - 1)) if span > 1 else 0.0,
        "war_last": war_by[last] if war_by else 0.0,
        "war_max": max(war_by) if war_by else 0.0,
        "war_slope": ((war_by[last] - war_by[0]) / max(1, span - 1)) if span > 1 else 0.0,
        "gs_ratio_last": gsr[last] if gsr else 0.0,
        "gs_ratio_delta": (gsr[last] - gsr[0]) if span > 1 else 0.0,
        "kbb_x": w["kbb"] * exposure,
        "k_pct_x": w["k_pct"] * exposure,
        "bb_pct_x": w["bb_pct"] * exposure,
        "era_x": (w["era"] if w["ip"] > 0 else 4.30) * exposure,
        "war_per_ip_c": w["war"] / max(40.0, w["ip"]),
        "age_debut": age if age is not None else AGE_FILL,
        "age_missing": 0.0 if age is not None else 1.0,
        "span_f": span_f,
    })
    return w


# the multivariate score keys (WAR-sum PLUS what WAR-sum does not carry)
KEYS = ["war", "war_per_season", "war_last", "war_max", "war_slope", "war_per_ip_c",
        "log_ip_ps", "log_ip_last", "ip_max", "ip_slope",
        "gs_ratio", "gs_ratio_last", "gs_ratio_delta",
        "kbb_x", "k_pct_x", "era_x", "appear_frac", "has_lines",
        "age_debut", "age_missing"]

# fallback for rows with no MLB lines (id-resolution failures): WAR only
KEYS_WAR = ["war", "war_per_season", "war_last", "war_max", "war_slope"]


# ---------------------------------------------------------------------------
# tiny standardized ridge
# ---------------------------------------------------------------------------

def _design(rows, span, keys):
    return np.array([[_f(feats(r, span).get(k)) for k in keys] for r in rows], dtype=float)


def _ridge(X, y, alpha):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    Z1 = np.hstack([Z, np.ones((len(Z), 1))])
    A = Z1.T @ Z1 + alpha * np.eye(Z1.shape[1])
    A[-1, -1] -= alpha                                    # do not penalize intercept
    coef = np.linalg.solve(A, Z1.T @ y)
    return {"mu": mu, "sd": sd, "coef": coef}


def _apply(m, X):
    Z = (X - m["mu"]) / m["sd"]
    return np.hstack([Z, np.ones((len(Z), 1))]) @ m["coef"]


def _nscore(v):
    """normal scores of a vector (rank -> gaussian quantile), ties broken by order"""
    v = np.asarray(v, dtype=float)
    n = len(v)
    r = np.empty(n)
    r[np.argsort(v, kind="mergesort")] = np.arange(n)
    p = (r + 0.5) / n
    return np.sqrt(2.0) * _erfinv(2.0 * p - 1.0)


def _erfinv(y):
    return np.vectorize(_erfinv_scalar)(y)


def _erfinv_scalar(y):
    # Winitzki approximation + 2 Newton steps (avoids a scipy dependency)
    a = 0.147
    ln = math.log(max(1e-12, 1.0 - y * y))
    t1 = 2.0 / (math.pi * a) + ln / 2.0
    x = math.copysign(math.sqrt(max(0.0, math.sqrt(t1 * t1 - ln / a) - t1)), y)
    for _ in range(2):
        err = math.erf(x) - y
        x -= err / (2.0 / math.sqrt(math.pi) * math.exp(-x * x))
    return x


# ---------------------------------------------------------------------------
# per-span fit
# ---------------------------------------------------------------------------

def _obs_war(rec, span):
    return sum(rec["war"].get(i, 0.0) for i in range(span))


def _oof(X, y, alpha, kfold, seed):
    n = len(y)
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    folds = [idx[i::kfold] for i in range(kfold)]
    out = np.zeros(n)
    for f in folds:
        tr = [i for i in idx if i not in set(f)]
        out[f] = _apply(_ridge(X[tr], y[tr], alpha), X[f])
    return out


def _fit_one_span(rows, span, alpha, kfold, seed, rank_target=True):
    """Two arms per span:
       SCORE  ridge on the normal score of true6      (pure ordering, rank-targeted)
       REST   ridge on true6 - observed WAR, then label = observed + rest_hat
              (structural: the observed part is KNOWN exactly, only the tail is modelled)
    Each arm is fitted twice - on the full feature set and on WAR-only (used verbatim when
    the row has no MLB lines). The two arms are combined in percentile space with a weight
    equal to the share of 6-year WAR mass this span actually observes: at span 2 almost
    nothing is known and ordering rules; at span 5 the observed sum is nearly the answer."""
    y6 = np.array([r["true6"] for r in rows], dtype=float)
    obs = np.array([_obs_war(r, span) for r in rows], dtype=float)
    rest = y6 - obs
    tgt_score = _nscore(y6) if rank_target else y6
    out = {"arms": {}}
    for arm, tgt in (("score", tgt_score), ("rest", rest)):
        out["arms"][arm] = {}
        for tag, keys in (("full", KEYS), ("war", KEYS_WAR)):
            X = _design(rows, span, keys)
            oo = _oof(X, tgt, alpha, kfold, seed + span)
            out["arms"][arm][tag] = {"model": _ridge(X, tgt, alpha), "keys": keys,
                                     "oof_raw": oo}
    # percentile reference distributions for the COMBINED per-arm predictor
    has = np.array([1.0 if feats(r, span)["has_lines"] > 0 else 0.0 for r in rows])
    ref = {}
    for arm in ("score", "rest"):
        v = np.where(has > 0, out["arms"][arm]["full"]["oof_raw"],
                     out["arms"][arm]["war"]["oof_raw"])
        if arm == "rest":
            v = obs + v                       # the additive label
        ref[arm] = {"sorted": np.sort(v), "raw": v}
    out["ref"] = ref
    out["marginal"] = np.sort(y6)
    out["mean"] = float(y6.mean())
    # observed share of the 6yr WAR mass at this span -> weight on the additive arm
    tot = float(np.abs(y6).sum())
    out["obs_share"] = float(min(1.0, max(0.0, np.abs(obs).sum() / tot))) if tot else 0.5
    return out


def _pct(sorted_ref, s):
    """percentile of s inside a sorted reference distribution, linearly interpolated"""
    n = len(sorted_ref)
    i = int(np.searchsorted(sorted_ref, s))
    if i <= 0:
        return 0.5 / n
    if i >= n:
        return 1.0 - 0.5 / n
    lo, hi = sorted_ref[i - 1], sorted_ref[i]
    frac = 0.0 if hi <= lo else (s - lo) / (hi - lo)
    return (i - 1 + 0.5 + frac) / n


def _quant(sorted_vals, p):
    n = len(sorted_vals)
    x = p * n - 0.5
    lo = int(math.floor(x))
    hi = min(n - 1, max(0, lo + 1))
    lo = min(n - 1, max(0, lo))
    frac = x - math.floor(x)
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def _arm_value(blk, rec, span, arm):
    """raw predictor for one arm on one row (WAR-only fallback when lines are missing)"""
    fr = feats(rec, span)
    tag = "full" if fr["has_lines"] > 0 else "war"
    sub = blk["arms"][arm][tag]
    x = np.array([[_f(fr.get(k)) for k in sub["keys"]]], dtype=float)
    v = float(_apply(sub["model"], x)[0])
    return v + _obs_war(rec, span) if arm == "rest" else v


def _blend_pct(blk, rec, span, w_add=None):
    """percentile of the row, blending the ordering arm and the additive arm with a
    weight equal to the share of 6yr WAR mass this span observes."""
    w = blk["obs_share"] if w_add is None else w_add
    p_s = _pct(blk["ref"]["score"]["sorted"], _arm_value(blk, rec, span, "score"))
    p_a = _pct(blk["ref"]["rest"]["sorted"], _arm_value(blk, rec, span, "rest"))
    return min(1 - 1e-9, max(1e-9, (1.0 - w) * p_s + w * p_a))


def _shrink_weight(st, span, rows, w_add=None):
    """OLS slope of true6 on the OUT-OF-FOLD transported label, clipped to [0,1].
    Short spans are noisy -> slope < 1 -> the label is pulled toward the cohort mean."""
    blk = st["spans"][span]
    y = np.array([r["true6"] for r in rows], dtype=float)
    w = blk["obs_share"] if w_add is None else w_add
    ps = np.array([_pct(blk["ref"]["score"]["sorted"], v)
                   for v in blk["ref"]["score"]["raw"]])
    pa = np.array([_pct(blk["ref"]["rest"]["sorted"], v)
                   for v in blk["ref"]["rest"]["raw"]])
    p = (1.0 - w) * ps + w * pa
    v = np.array([_quant(blk["marginal"], min(1 - 1e-9, max(1e-9, pp))) for pp in p])
    vc = v - v.mean()
    den = float((vc * vc).sum())
    if den <= 0 or len(rows) < 10:
        return 1.0
    slope = float((vc * (y - y.mean())).sum() / den)
    return max(0.0, min(1.0, slope))


def fit(train_rows, alpha=12.0, kfold=5, seed=17, rank_target=True, shrink=True,
        w_add=None):
    st = {"spans": {}, "shrink": {}, "w_add": w_add,
          "cfg": {"alpha": alpha, "rank_target": rank_target}}
    for sp in SPANS:
        st["spans"][sp] = _fit_one_span(train_rows, sp, alpha, kfold, seed, rank_target)
    for sp in SPANS:
        st["shrink"][sp] = _shrink_weight(st, sp, train_rows, w_add) if shrink else 1.0
    return st


def predict(state, rec, span):
    """Label = shrunk, quantile-transported blend of the two arms for THIS span."""
    sp = min(max(1, int(span)), max(SPANS))
    blk = state["spans"][sp]
    v = _quant(blk["marginal"], _blend_pct(blk, rec, sp, state.get("w_add")))
    mu, w = blk["mean"], state["shrink"].get(sp, 1.0)
    return mu + w * (v - mu)


# ---------------------------------------------------------------------------
# arms
# ---------------------------------------------------------------------------

def _fit_noshrink(rows):
    """same ordering, no pull toward the cohort mean (level control)"""
    return fit(rows, shrink=False)


def _fit_order_only(rows):
    """ordering arm only (w_add=0): pure multivariate rank, transported"""
    return fit(rows, w_add=0.0)


def _fit_additive_only(rows):
    """additive arm only (w_add=1): observed WAR + modelled remainder"""
    return fit(rows, w_add=1.0)


def _fit_raw(rows):
    """no transport, no shrink: observed WAR + modelled remainder in WAR units"""
    st = fit(rows, shrink=False, w_add=1.0)
    st["raw"] = True
    return st


def _pred_raw(state, rec, span):
    sp = min(max(1, int(span)), max(SPANS))
    return _arm_value(state["spans"][sp], rec, sp, "rest")


CANDIDATES = {
    "LH_span_adaptive": (fit, predict),
    "LH_no_shrink": (_fit_noshrink, predict),
    "LH_order_only": (_fit_order_only, predict),
    "LH_additive_only": (_fit_additive_only, predict),
    "LH_raw_magnitude": (_fit_raw, _pred_raw),
}


# ---------------------------------------------------------------------------
# paired bootstrap (per the transmission diagnostic: single-arm rho is uninformative)
# ---------------------------------------------------------------------------

def _blend_preds(train_pairs, test_recs, side="pit"):
    from efv_model import _vec, _fit_ols_fv, _pred_ols, _feature_spec
    from prospect_path import _fit_ridge as _fr, _predict as _pr
    keys, _m = _feature_spec(side)
    data = [{"feats": _vec(r["row"], side), "target": float(t),
             "fv": float(r["row"]["consensus_fv_raw"]), "player_key": r["pk"]}
            for r, t in train_pairs if t is not None]
    ridge, ols = _fr(data, keys), _fit_ols_fv(data)
    if not ridge or not ols:
        return None
    lam = H.LAM_PIT
    return [(1 - lam) * max(0.0, _pred_ols(ols, float(r["row"]["consensus_fv_raw"])))
            + lam * _pr(ridge, _vec(r["row"], side)) for r in test_recs]


def paired_bootstrap(span=3, side="pit", B=1000, seed=7):
    pool = H.build_pool(side)
    early = [r for r in pool if H.EARLY[0] <= r["dy"] <= H.EARLY[1]]
    mid = [r for r in pool if H.MID[0] <= r["dy"] <= H.MID[1]]
    test = [r for r in pool if H.TEST[0] <= r["dy"] <= H.TEST[1]]
    base = [(r, r["true6"]) for r in early]
    arms = {
        "A_KM": _blend_preds(base + [(r, H.km_label(r, span)) for r in mid], test, side),
        "C_oracle": _blend_preds(base + [(r, r["true6"]) for r in mid], test, side),
        "Z_drop_mid": _blend_preds(base, test, side),
    }
    for nm, (fn_fit, fn_pred) in CANDIDATES.items():
        st = fn_fit(early)
        arms[nm] = _blend_preds(base + [(r, fn_pred(st, r, span)) for r in mid], test, side)
    truth = [r["true6"] for r in test]
    n = len(truth)
    rng = random.Random(seed)
    idxs = [[rng.randrange(n) for _ in range(n)] for _ in range(B)]
    print(f"\n  PAIRED BOOTSTRAP vs A_KM (span={span}, B={B}, n_test={n})")
    print(f"    {'arm':22} {'rho':>7} {'delta':>8} {'sd':>7} {'ci_lo':>8} {'ci_hi':>8} {'P(>0)':>7}")
    a = arms["A_KM"]
    for nm, pr in arms.items():
        if pr is None:
            print(f"    {nm:22} {'FAILED':>7}")
            continue
        rho = _spearman(pr, truth) or 0.0
        if nm == "A_KM":
            print(f"    {nm:22} {rho:7.4f} {'-':>8}")
            continue
        ds = []
        for ix in idxs:
            t = [truth[i] for i in ix]
            ds.append((_spearman([pr[i] for i in ix], t) or 0.0)
                      - (_spearman([a[i] for i in ix], t) or 0.0))
        ds.sort()
        mean = sum(ds) / len(ds)
        sd = (sum((d - mean) ** 2 for d in ds) / len(ds)) ** 0.5
        pgt = sum(1 for d in ds if d > 0) / len(ds)
        print(f"    {nm:22} {rho:7.4f} {mean:+8.4f} {sd:7.4f} {ds[int(.025 * B)]:+8.4f} "
              f"{ds[int(.975 * B)]:+8.4f} {pgt:7.3f}")


if __name__ == "__main__":
    spans = [int(a) for a in sys.argv[1:]] or [3, 4, 5]
    for sp in spans:
        print("=" * 78)
        print(f"SPAN-ADAPTIVE LONG-HORIZON pitcher label instrument - span={sp}")
        print("=" * 78)
        H.run_gate(CANDIDATES, span=sp, side="pit")
    for sp in spans:
        paired_bootstrap(span=sp, B=1000)
