# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ROLE-CONDITIONED pitcher label instrument (candidate).

Shape: separate calibrated maps for starters / swingmen / relievers, keyed on the
early-window gs_ratio, with TWO layers of shrinkage:

  bucket shrinkage : a role map is mixed toward the pooled map by n_role/(n_role+K),
                     so a thin bucket cannot invent its own curve.
  player shrinkage : a player's role membership is soft (logistic in gs_ratio) and is
                     itself damped by how much evidence backs it (g/(g+G0)), so a guy
                     with 4 career appearances is labeled by the pooled map, and a
                     50/50 swingman is labeled by a blend rather than a coin flip.
                     That is the "role instability" handling.

Arms:
  R1_role_iso_hard  3 hard buckets, isotonic(war) inside each, shrunk to pooled.
  R2_role_iso_soft  continuous SP/RP membership, isotonic maps, double shrinkage.
  R3_role_resid     pooled isotonic(war) + role-conditioned ridge on the multivariate
                    window residual (workload / rate / role-trend features).
  R4_role_resid_q   R3's ORDER, magnitudes borrowed by quantile transport onto the
                    early-cohort TRUE marginal (per the transmission diagnostic: rank
                    is the channel, magnitude can be borrowed).
  R5_role_resid_km  R3's ORDER, magnitudes borrowed from the early-cohort KM marginal.
  R6_half_km        half R3 / half the KM label (re-anchor test).
  R7_resid_tailw    R3 with a tail-weighted residual fit (w = 1 + TAIL_C*max(0,true6)).
  R8_tailw_km       R7's order on the KM marginal.

MEASURED (2026-07-24, span=3, pit pool 530 / early 216 / mid 132 / test 180):
  KM bar blend 0.1164, oracle 0.2260 (headroom +0.1096).
  R1 0.1134 (-2.7%)  R2 0.1173 (+0.8%)  R3 0.1333 (+15.4%)  R4 0.1250 (+7.8%)
  R5 0.1308 (+13.1%) R6 0.1076 (-8.0%)  R7 0.1456 (+26.6%)  R8 0.1307 (+13.0%)
  span=4: KM 0.1947, R5 0.2071 (+39.6% of the 0.0313 span-4 headroom), R7 0.1851 (-30.7%).
  Pure role RE-CALIBRATION (R1/R2) is a null, confirming the prior role diagnostic. The
  gain lives in the role-conditioned RESIDUAL (R3/R5) and shows up as top-quartile label
  order: mid rho_topQ 0.383 (KM) -> 0.470, top-decile recall 0.54 -> 0.62, even though
  OVERALL label rho falls 0.804 -> 0.748. R7's span-3 +26.6% is NOT selected: it is worse
  than R3 on every early/mid selection metric and flips to -30.7% at span 4.

Circularity: every feature comes from harness window()/lines/war, i.e. post-debut
REALIZED outcomes. rec['row'] (scouting/draft) is never read.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_pitcher_label_harness as H  # noqa: E402

K_BUCKET = 60.0     # bucket-level shrinkage constant (games-of-role-evidence scale)
G0 = 10.0           # player-level role-confidence constant (appearances)
RIDGE_A = 8.0       # ridge penalty on standardized residual features
SOFT_T = 0.12       # logistic temperature on gs_ratio around 0.5
TAIL_C = 0.25       # tail emphasis in the weighted residual fit (w = 1 + c*max(0,true6))


# ---------------------------------------------------------------------------
# small numerics (no sklearn dependency, deterministic)
# ---------------------------------------------------------------------------

def _pava(xs, ys, ws=None):
    """Isotonic (non-decreasing) fit; returns (x_knots, y_knots) for interpolation."""
    pts = sorted(zip(xs, ys, ws or [1.0] * len(xs)))
    lvl = [[x, y, w] for x, y, w in pts]           # [x_last, mean, weight]
    out = []
    for x, y, w in lvl:
        blk = [x, y, w]
        while out and out[-1][1] > blk[1]:
            p = out.pop()
            tw = p[2] + blk[2]
            blk = [blk[0], (p[1] * p[2] + blk[1] * blk[2]) / tw, tw]
        out.append(blk)
    return [b[0] for b in out], [b[1] for b in out]


def _interp(knots, vals, x):
    if not knots:
        return 0.0
    if x <= knots[0]:
        return vals[0]
    if x >= knots[-1]:
        return vals[-1]
    lo, hi = 0, len(knots) - 1
    while hi - lo > 1:
        m = (lo + hi) // 2
        if knots[m] <= x:
            lo = m
        else:
            hi = m
    if knots[hi] == knots[lo]:
        return vals[hi]
    f = (x - knots[lo]) / (knots[hi] - knots[lo])
    return vals[lo] + f * (vals[hi] - vals[lo])


def _solve(A, b):
    n = len(b)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            continue
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        for r in range(n):
            if r == c:
                continue
            f = M[r][c] / pv
            if f:
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


def _fit_ridge_std(X, y, alpha=None, w=None):
    """Standardized (optionally weighted) ridge with intercept. Returns dict state."""
    alpha = RIDGE_A if alpha is None else alpha
    n, p = len(X), len(X[0])
    w = [1.0] * n if w is None else list(w)
    sw = sum(w) or 1.0
    mu = [sum(w[i] * X[i][j] for i in range(n)) / sw for j in range(p)]
    sd = []
    for j in range(p):
        v = sum(w[i] * (X[i][j] - mu[j]) ** 2 for i in range(n)) / sw
        sd.append(math.sqrt(v) if v > 1e-12 else 1.0)
    Z = [[(r[j] - mu[j]) / sd[j] for j in range(p)] for r in X]
    ym = sum(w[i] * y[i] for i in range(n)) / sw
    yc = [t - ym for t in y]
    scale = sw / n                      # keep alpha on the same footing as unweighted
    A = [[sum(w[i] * Z[i][a] * Z[i][b] for i in range(n)) / scale
          + (alpha if a == b else 0.0) for b in range(p)] for a in range(p)]
    rhs = [sum(w[i] * Z[i][a] * yc[i] for i in range(n)) / scale for a in range(p)]
    coef = _solve(A, rhs)
    return {"mu": mu, "sd": sd, "coef": coef, "y0": ym, "n": n}


def _pred_ridge(st, x):
    return st["y0"] + sum(c * ((v - m) / s) for c, v, m, s
                          in zip(st["coef"], x, st["mu"], st["sd"]))


def _quantile_map(src_sorted, dst_sorted, x):
    """Rank-preserving transport: position of x in src -> same position in dst."""
    n = len(src_sorted)
    if n == 0:
        return x
    lo, hi = 0, n
    while lo < hi:
        m = (lo + hi) // 2
        if src_sorted[m] < x:
            lo = m + 1
        else:
            hi = m
    r = lo
    hi2 = r
    while hi2 < n and src_sorted[hi2] == x:
        hi2 += 1
    pos = (r + hi2 - 1) / 2.0 if hi2 > r else r - 0.5
    pos = max(0.0, min(n - 1.0, pos))
    f = pos / max(1.0, n - 1.0)
    m = len(dst_sorted)
    g = f * (m - 1)
    i0 = int(math.floor(g))
    i1 = min(m - 1, i0 + 1)
    return dst_sorted[i0] + (g - i0) * (dst_sorted[i1] - dst_sorted[i0])


# ---------------------------------------------------------------------------
# features (post-debut realized only)
# ---------------------------------------------------------------------------

def _season_shapes(rec, span):
    out = []
    for i in range(span):
        ln = rec["lines"].get(i)
        if not ln:
            continue
        g = H._f(ln.get("g"))
        out.append({"i": i, "g": g, "gs": H._f(ln.get("gs")),
                    "ip": H._f(ln.get("ip")),
                    "gsr": (H._f(ln.get("gs")) / g) if g else 0.0})
    return out


def feats(rec, span):
    w = H.window(rec, span)
    ss = _season_shapes(rec, span)
    gsr_trend = (ss[-1]["gsr"] - ss[0]["gsr"]) if len(ss) >= 2 else 0.0
    ip_slope = ((ss[-1]["ip"] - ss[0]["ip"]) / 100.0) if len(ss) >= 2 else 0.0
    ip_last = (ss[-1]["ip"] / 100.0) if ss else 0.0
    has = 1.0 if w["seasons_pitched"] > 0 else 0.0
    era = min(w["era"], 9.0) if w["ip"] > 0 else 4.5
    return {
        "war": w["war"],
        "war_per_season": w["war_per_season"],
        "ip_per_season": w["ip_per_season"] / 100.0,
        "ip_last": ip_last,
        "ip_slope": ip_slope,
        "seasons_frac": w["seasons_pitched"] / max(1.0, float(span)),
        "gs_ratio": w["gs_ratio"],
        "gsr_trend": gsr_trend,
        "k_pct": w["k_pct"] if has else 0.20,
        "bb_pct": w["bb_pct"] if has else 0.09,
        "kbb": w["kbb"] if has else 0.11,
        "era": era,
        "war_per_ip": w["war_per_ip"] * 100.0,
        "tj_in_window": w["tj_in_window"],
        "no_lines": 1.0 - has,
        "g": w["g"],
    }


RESID_KEYS = ["war_per_season", "ip_per_season", "ip_last", "ip_slope", "seasons_frac",
              "gs_ratio", "gsr_trend", "k_pct", "bb_pct", "kbb", "era", "war_per_ip",
              "tj_in_window", "no_lines"]


def _x(f):
    return [f[k] for k in RESID_KEYS]


def role_weights(f):
    """Soft SP membership, damped by how much evidence backs the role read."""
    if f["no_lines"] or f["g"] <= 0:
        return {"SP": 0.0, "RP": 0.0, "conf": 0.0}
    z = (f["gs_ratio"] - 0.5) / SOFT_T
    z = max(-30.0, min(30.0, z))
    p_sp = 1.0 / (1.0 + math.exp(-z))
    conf = f["g"] / (f["g"] + G0)
    return {"SP": p_sp, "RP": 1.0 - p_sp, "conf": conf}


def hard_role(f):
    if f["no_lines"] or f["g"] <= 0:
        return None
    r = f["gs_ratio"]
    return "SP" if r >= 0.7 else ("RP" if r < 0.2 else "SW")


# ---------------------------------------------------------------------------
# fit / predict
# ---------------------------------------------------------------------------

def fit(train_rows, spans=(1, 2, 3, 4, 5)):
    """State is fit PER SPAN (the instrument must transfer down to span 1-2 cohorts)."""
    state = {"spans": {}}
    for span in spans:
        rows = []
        for r in train_rows:
            f = feats(r, span)
            rows.append({"f": f, "y": r["true6"], "w": H.window(r, span),
                         "km": H.km_label(r, span)})
        st = {}

        # --- pooled isotonic on window WAR --------------------------------
        kx, ky = _pava([d["f"]["war"] for d in rows], [d["y"] for d in rows])
        st["pool_iso"] = (kx, ky)

        # --- hard-bucket isotonics (R1) -----------------------------------
        st["hard_iso"] = {}
        for b in ("SP", "SW", "RP"):
            sub = [d for d in rows if hard_role(d["f"]) == b]
            if len(sub) >= 12:
                bx, by = _pava([d["f"]["war"] for d in sub], [d["y"] for d in sub])
                st["hard_iso"][b] = (bx, by, float(len(sub)))

        # --- soft SP/RP isotonics, weighted by membership (R2) ------------
        st["soft_iso"] = {}
        for b in ("SP", "RP"):
            xs, ys, ws = [], [], []
            for d in rows:
                rw = role_weights(d["f"])
                m = rw[b] * rw["conf"]
                if m > 0.02:
                    xs.append(d["f"]["war"]); ys.append(d["y"]); ws.append(m)
            if sum(ws) >= 12:
                bx, by = _pava(xs, ys, ws)
                st["soft_iso"][b] = (bx, by, sum(ws))

        # --- residual ridge: pooled + per-role, shrunk (R3) ---------------
        base = [_interp(kx, ky, d["f"]["war"]) for d in rows]
        res = [d["y"] - b for d, b in zip(rows, base)]
        X = [_x(d["f"]) for d in rows]
        tw = [1.0 + TAIL_C * max(0.0, d["y"]) for d in rows]
        st["res_pool"] = _fit_ridge_std(X, res)
        st["res_pool_t"] = _fit_ridge_std(X, res, w=tw)
        st["res_role"], st["res_role_t"] = {}, {}
        for b in ("SP", "RP"):
            idx = [i for i, d in enumerate(rows)
                   if role_weights(d["f"])[b] >= 0.5 and not d["f"]["no_lines"]]
            if len(idx) >= 40:
                st["res_role"][b] = _fit_ridge_std([X[i] for i in idx],
                                                   [res[i] for i in idx])
                st["res_role_t"][b] = _fit_ridge_std([X[i] for i in idx],
                                                     [res[i] for i in idx],
                                                     w=[tw[i] for i in idx])

        state["spans"][span] = st

        # --- marginals for the quantile-transport arms --------------------
        scores = [_score_r3(st, d["f"]) for d in rows]
        st["src_sorted"] = sorted(scores)
        st["src_sorted_t"] = sorted(_score_r3(st, d["f"], tail=True) for d in rows)
        st["dst_true"] = sorted(d["y"] for d in rows)
        st["dst_km"] = sorted(d["km"] for d in rows)
    return state


def _shrunk_iso(st, key, bucket, war):
    px, py = st["pool_iso"]
    pooled = _interp(px, py, war)
    ent = st[key].get(bucket)
    if not ent:
        return pooled
    bx, by, n = ent
    w = n / (n + K_BUCKET)
    return w * _interp(bx, by, war) + (1 - w) * pooled


def _score_r1(st, f):
    b = hard_role(f)
    if b is None:
        px, py = st["pool_iso"]
        return _interp(px, py, f["war"])
    return _shrunk_iso(st, "hard_iso", b, f["war"])


def _score_r2(st, f):
    px, py = st["pool_iso"]
    pooled = _interp(px, py, f["war"])
    rw = role_weights(f)
    if rw["conf"] <= 0:
        return pooled
    role_val = 0.0
    tot = 0.0
    for b in ("SP", "RP"):
        ent = st["soft_iso"].get(b)
        if not ent or rw[b] <= 0:
            continue
        bx, by, n = ent
        sh = n / (n + K_BUCKET)
        role_val += rw[b] * (sh * _interp(bx, by, f["war"]) + (1 - sh) * pooled)
        tot += rw[b]
    if tot <= 0:
        return pooled
    role_val /= tot
    a = rw["conf"]
    return a * role_val + (1 - a) * pooled


def _score_r3(st, f, tail=False):
    px, py = st["pool_iso"]
    base = _interp(px, py, f["war"])
    x = _x(f)
    pk, rk = ("res_pool_t", "res_role_t") if tail else ("res_pool", "res_role")
    r_pool = _pred_ridge(st[pk], x)
    rw = role_weights(f)
    if rw["conf"] <= 0 or not st[rk]:
        return base + r_pool
    r_role, tot = 0.0, 0.0
    for b in ("SP", "RP"):
        sub = st[rk].get(b)
        if not sub or rw[b] <= 0:
            continue
        sh = sub["n"] / (sub["n"] + K_BUCKET)
        r_role += rw[b] * (sh * _pred_ridge(sub, x) + (1 - sh) * r_pool)
        tot += rw[b]
    if tot <= 0:
        return base + r_pool
    r_role /= tot
    a = rw["conf"]
    return base + a * r_role + (1 - a) * r_pool


def _st(state, span):
    sp = state["spans"]
    if span in sp:
        return sp[span]
    return sp[min(sp, key=lambda k: abs(k - span))]


def predict(state, rec, span, arm="R3"):
    st = _st(state, span)
    f = feats(rec, span)
    if arm == "R1":
        return _score_r1(st, f)
    if arm == "R2":
        return _score_r2(st, f)
    s = _score_r3(st, f)
    if arm == "R3":
        return s
    if arm == "R4":
        return _quantile_map(st["src_sorted"], st["dst_true"], s)
    if arm == "R5":
        return _quantile_map(st["src_sorted"], st["dst_km"], s)
    if arm == "R6":                       # re-anchor half the score on the KM label
        return 0.5 * s + 0.5 * H.km_label(rec, span)
    if arm == "R7":                       # tail-weighted residual fit (top-quartile focus)
        return _score_r3(st, f, tail=True)
    if arm == "R8":                       # R7 order, KM marginal magnitudes
        return _quantile_map(st["src_sorted_t"], st["dst_km"], _score_r3(st, f, tail=True))
    raise ValueError(arm)


def _arm(name):
    return (fit, lambda state, rec, span, n=name: predict(state, rec, span, n))


CANDIDATES = {
    "R1_role_iso_hard": _arm("R1"),
    "R2_role_iso_soft": _arm("R2"),
    "R3_role_resid": _arm("R3"),
    "R4_role_resid_q": _arm("R4"),
    "R5_role_resid_km": _arm("R5"),
    "R6_half_km": _arm("R6"),
    "R7_resid_tailw": _arm("R7"),
    "R8_tailw_km": _arm("R8"),
}


if __name__ == "__main__":
    spans = [int(a) for a in sys.argv[1:]] or [3]
    for sp in spans:
        print("=" * 78)
        print(f"ROLE-CONDITIONED INSTRUMENT GATE  span={sp}")
        print("=" * 78)
        H.run_gate(CANDIDATES, span=sp, side="pit")
        print()
