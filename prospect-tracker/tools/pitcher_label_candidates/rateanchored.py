# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""RATE-ANCHORED pitcher label instrument.

IDEA. A pitcher's WAR over a 2-4 season window is a product of two things the label
needs to separate: HOW MUCH he pitched (bulk innings, which early-career opportunity
hands out almost arbitrarily) and HOW WELL he pitched per inning (rate quality, which
stabilises far faster than WAR does). The shipped KM label multiplies the *sum* of both
by 6/span, so it ranks an early innings-eater (fulmer, keller, flaherty) above a
slow-burn ace who debuted in relief or on an innings cap (burnes, r.suarez, urias,
giolito). This instrument instead builds the 6yr total as

    label = WAR already realised in the window
          + E[remaining innings | workload, role, durability]
            x E[WAR per inning   | SHRUNK RATE QUALITY, role]

so the projected part of the label is anchored on rates (K%, BB%, K-BB%, ERA - each
regressed to the cohort mean by batters faced / innings) rather than on early WAR
magnitude. Both arms are calibrated on the EARLY cohort only.

The score is then QUANTILE-TRANSPORTED onto the early cohort's TRUE first-6yr-WAR
marginal, using out-of-fold scores to build the map. Per the transmission diagnostic
(a label with TRUE ranks and KM's wrong magnitudes captures 97.7% of the oracle
headroom, while KM ranks with TRUE magnitudes captures 10.1%), the ORDER is what the
model consumes; the magnitude is borrowed so the label sits on the same scale as the
true-labelled early block it is mixed with.

CIRCULARITY: every input is post-debut REALISED outcome data (MLB season lines, career
WAR, TJ years). rec['row'] - which holds consensus FV, tool grades, draft slot - is
never read.

Run:  python tools/pitcher_label_candidates/rateanchored.py            # the gate, spans 2/3/4
      python tools/pitcher_label_candidates/rateanchored.py --replicate # shifted-split check

MEASURED RESULT (2026-07-24) - read the replication block before believing the gate.
  OFFICIAL gate (early 2011-15 / mid 2016-18 / test 2019-20, n_test=180), R1:
    span2  KM 0.0806 -> R1 0.1446  (+0.0640, 44.0% of that span's headroom, P(>0)=0.991)
    span3  KM 0.1164 -> R1 0.1312  (+0.0148, 13.5%, P(>0)=0.62 - inside noise)
    span4  KM 0.1947 -> R1 0.2601  (+0.0654, 208.9%, P(>0)=0.999 - above the ORACLE)
  Channel decomposition on the official split confirms the transmission diagnostic:
  R1's ORDER carried on KM magnitudes scores 0.2739 at span4 / 0.1429 at span3, while
  KM's order carried on R1 magnitudes scores 0.2030 / 0.1154 (~= the KM bar). Pure
  magnitude controls (KM quantile-transported, KM affine-rescaled to the early TRUE
  marginal) move nothing: 0.1988 / 0.2033 at span4.
  REPLICATION on shifted cohort splits is where it falls down. span4's +0.0654 becomes
  +0.0055 / -0.0065 / -0.0093 on ALT-A/B/C, and span3 is negative on all three
  (-0.031 / -0.003 / -0.062). Only span2 keeps its sign in 3 of 4 splits
  (+0.064 / -0.047 / +0.032 / +0.087). Treat span4 as split-specific, span3 as a null,
  and span2 - where KM is at its worst and production coverage is 100% - as the only
  lane with any cross-split support.
  ABLATION: replacing the rate features with role/IP-only features costs 0.2601 -> 0.2488
  at span4 and GAINS 0.1312 -> 0.1457 at span3, so the rate anchor itself is not what
  carries the number; the two-part (realised WAR + projected IP x projected WAR/IP)
  structure and the quantile transport are. Reported as a partial negative on the
  "rates beat short-sample WAR" hypothesis.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import efv_pitcher_label_harness as H   # noqa: E402

TARGET_SEASONS = 6
KBF = 350.0        # batters-faced prior weight for K% / BB% shrinkage
KIP = 70.0         # innings prior weight for ERA shrinkage
KBF_SEASON = 200.0  # lighter prior for the per-season rate series
KIP_SEASON = 40.0
SPANS = (1, 2, 3, 4, 5)
RIDGE_LAM = 5.0
MIN_REM_IP = 20.0  # rows with less than this remaining IP do not identify a rate->WAR slope
IP_CAP = 500.0

# workload / durability / role arm -> projects REMAINING innings
WORK_FEATS = ("log_ip", "log_ipps", "log_g", "log_gs", "gsr", "last_gsr", "gsr_slope",
              "log_last_ip", "log_max_ip", "seen", "no_lines", "ip_slope",
              "tj_in", "kbb_s", "era_s")
# rate arm -> projects WAR PER REMAINING INNING (this is the rate anchor)
RATE_FEATS = ("k_s", "bb_s", "kbb_s", "era_s", "kbb_peak", "kbb_last", "kbb_rec",
              "era_last", "gsr", "last_gsr", "log_ipps", "seen")
# used only by the secondary GBM arm
ALL_FEATS = WORK_FEATS + RATE_FEATS + ("war", "war_ps", "wpi", "war_last", "war_peak")


# ---------------------------------------------------------------------------
# realized-window feature construction (outcome data only)
# ---------------------------------------------------------------------------

def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _agg(rec, span):
    ip = g = gs = so = bb = bf = er = 0.0
    seasons = []
    for i in range(span):
        ln = rec["lines"].get(i)
        if not ln:
            continue
        _ip = _f(ln.get("ip"))
        ip += _ip
        g += _f(ln.get("g"))
        gs += _f(ln.get("gs"))
        so += _f(ln.get("so"))
        bb += _f(ln.get("bb"))
        bf += _f(ln.get("bf"))
        er += _f(ln.get("era")) * _ip / 9.0
        seasons.append({"ip": _ip, "g": _f(ln.get("g")), "gs": _f(ln.get("gs")),
                        "so": _f(ln.get("so")), "bb": _f(ln.get("bb")),
                        "bf": _f(ln.get("bf")), "era": _f(ln.get("era")),
                        "war": _f(rec["war"].get(i, 0.0))})
    war = sum(_f(rec["war"].get(i, 0.0)) for i in range(span))
    return dict(ip=ip, g=g, gs=gs, so=so, bb=bb, bf=bf, er=er, war=war, seasons=seasons)


def _priors(rows, span):
    so = bb = bf = ip = er = 0.0
    for r in rows:
        a = _agg(r, span)
        so += a["so"]; bb += a["bb"]; bf += a["bf"]; ip += a["ip"]; er += a["er"]
    return {"k": (so / bf) if bf else 0.20, "bb": (bb / bf) if bf else 0.085,
            "era": (9 * er / ip) if ip else 4.10}


def _feats(rec, span, P):
    a = _agg(rec, span)
    bf, ip = a["bf"], a["ip"]
    k_s = (a["so"] + P["k"] * KBF) / (bf + KBF)
    bb_s = (a["bb"] + P["bb"] * KBF) / (bf + KBF)
    era_s = (9 * a["er"] + P["era"] * KIP) / (ip + KIP)
    ss = a["seasons"]
    if ss:
        kb = [((s["so"] + P["k"] * KBF_SEASON) / (s["bf"] + KBF_SEASON)
               - (s["bb"] + P["bb"] * KBF_SEASON) / (s["bf"] + KBF_SEASON)) for s in ss]
        wts = sum(j + 1 for j in range(len(ss)))
        ips = [s["ip"] for s in ss]
        gsr_s = [(s["gs"] / s["g"]) if s["g"] else 0.0 for s in ss]
        last = ss[-1]
        x = {
            "kbb_peak": max(kb), "kbb_last": kb[-1],
            "kbb_rec": sum((j + 1) * v for j, v in enumerate(kb)) / wts,
            "era_last": (last["era"] * last["ip"] + P["era"] * KIP_SEASON) / (last["ip"] + KIP_SEASON),
            "war_last": last["war"], "war_peak": max(s["war"] for s in ss),
            "last_gsr": gsr_s[-1], "gsr_slope": (gsr_s[-1] - gsr_s[0]) if len(gsr_s) > 1 else 0.0,
            "log_last_ip": math.log1p(ips[-1]), "log_max_ip": math.log1p(max(ips)),
            "ip_slope": (ips[-1] - ips[0]) if len(ips) > 1 else 0.0,
        }
    else:
        x = {"kbb_peak": P["k"] - P["bb"], "kbb_last": P["k"] - P["bb"],
             "kbb_rec": P["k"] - P["bb"], "era_last": P["era"], "war_last": 0.0,
             "war_peak": 0.0, "last_gsr": 0.0, "gsr_slope": 0.0, "log_last_ip": 0.0,
             "log_max_ip": 0.0, "ip_slope": 0.0}
    x.update({
        "log_ip": math.log1p(ip), "log_ipps": math.log1p(ip / max(1, span)),
        "log_g": math.log1p(a["g"]), "log_gs": math.log1p(a["gs"]),
        "gsr": (a["gs"] / a["g"]) if a["g"] else 0.0,
        "seen": float(len(ss)), "no_lines": 1.0 if not ss else 0.0,
        "k_s": k_s, "bb_s": bb_s, "kbb_s": k_s - bb_s, "era_s": era_s,
        "war": a["war"], "war_ps": a["war"] / max(1, span),
        "wpi": (a["war"] / ip) if ip > 0 else 0.0,
        "tj_in": float(sum(1 for y in rec["tj_years"] if rec["dy"] <= y < rec["dy"] + span)),
        "_bf": bf, "_ip": ip,
    })
    return x


def _rem_ip(rec, span):
    t = 0.0
    for i in range(span, TARGET_SEASONS):
        ln = rec["lines"].get(i)
        if ln:
            t += _f(ln.get("ip"))
    return t


# ---------------------------------------------------------------------------
# plain numpy ridge (standardised, intercept unpenalised)
# ---------------------------------------------------------------------------

def _ridge(X, y, lam=None, w=None):
    lam = RIDGE_LAM if lam is None else lam
    X = np.asarray(X, float); y = np.asarray(y, float)
    mu = X.mean(0); sd = X.std(0); sd[sd == 0] = 1.0
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    w = np.ones(len(y)) if w is None else np.asarray(w, float)
    A = Z.T @ (Z * w[:, None]) + lam * np.eye(Z.shape[1])
    A[0, 0] -= lam
    coef = np.linalg.solve(A, Z.T @ (y * w))
    return {"coef": coef, "mu": mu, "sd": sd}


def _rpred(m, X):
    X = np.asarray(X, float)
    Z = np.hstack([np.ones((len(X), 1)), (X - m["mu"]) / m["sd"]])
    return Z @ m["coef"]


# ---------------------------------------------------------------------------
# the instrument
# ---------------------------------------------------------------------------

def _mat(F, names):
    return np.array([[x[k] for k in names] for x in F], float)


def _fit_span(rows, span, use_gbm=False):
    P = _priors(rows, span)
    F = [_feats(r, span, P) for r in rows]
    y = np.array([r["true6"] for r in rows], float)
    war = np.array([x["war"] for x in F], float)
    rem_ip = np.array([_rem_ip(r, span) for r in rows], float)
    rem_war = y - war
    Xw = _mat(F, WORK_FEATS)
    Xr = _mat(F, RATE_FEATS)
    ok = rem_ip >= MIN_REM_IP
    st = {"P": P, "span": span,
          "m_ip": _ridge(Xw, np.log1p(rem_ip)),
          "m_wpi": _ridge(Xr[ok], rem_war[ok] / rem_ip[ok], w=np.minimum(rem_ip[ok], IP_CAP))}
    if use_gbm:
        from sklearn.ensemble import GradientBoostingRegressor
        st["gbm"] = GradientBoostingRegressor(n_estimators=300, max_depth=2, learning_rate=0.04,
                                              subsample=0.8, random_state=0
                                              ).fit(_mat(F, ALL_FEATS), rem_war)
    return st


def _raw_score(st, rec, span, use_gbm=False):
    x = _feats(rec, span, st["P"])
    if x["_bf"] <= 0:                      # no MLB lines resolvable -> fall back to KM
        return H.km_label(rec, span)
    war = x["war"]
    if use_gbm and "gbm" in st:
        return war + float(_gbm_pred(st["gbm"], x))
    ip_hat = max(0.0, math.expm1(float(_rpred(st["m_ip"], _mat([x], WORK_FEATS))[0])))
    wpi_hat = float(_rpred(st["m_wpi"], _mat([x], RATE_FEATS))[0])
    return war + ip_hat * wpi_hat


def _gbm_pred(g, x):
    return g.predict(_mat([x], ALL_FEATS))[0]


def _quantile_map(src, dst):
    """Monotone transport: percentile of a score in `src` -> same percentile of `dst`."""
    return {"src": np.sort(np.asarray(src, float)), "dst": np.sort(np.asarray(dst, float))}


def _apply_map(m, v):
    src, dst = m["src"], m["dst"]
    n = len(src)
    if n < 5:
        return float(v)
    pos = float(np.searchsorted(src, v, side="left"))
    if v <= src[0]:
        pos = 0.0
    elif v >= src[-1]:
        pos = n - 1.0
    else:
        j = int(np.searchsorted(src, v, side="left"))
        lo, hi = src[j - 1], src[j]
        pos = (j - 1) + ((v - lo) / (hi - lo) if hi > lo else 0.0)
    q = pos / max(1.0, n - 1.0)
    idx = q * (len(dst) - 1)
    lo_i = int(math.floor(idx)); hi_i = min(len(dst) - 1, lo_i + 1)
    frac = idx - lo_i
    out = dst[lo_i] * (1 - frac) + dst[hi_i] * frac
    # linear extrapolation past the observed score range keeps the tail from flattening
    if v > src[-1] and src[-1] > src[0]:
        out += (v - src[-1]) * ((dst[-1] - dst[0]) / (src[-1] - src[0]))
    elif v < src[0] and src[-1] > src[0]:
        out -= (src[0] - v) * ((dst[-1] - dst[0]) / (src[-1] - src[0]))
    return float(out)


def _fit(train_rows, use_gbm=False, transport=True, folds=5):
    state = {"spans": {}, "maps": {}, "use_gbm": use_gbm, "transport": transport}
    rows = list(train_rows)
    for span in SPANS:
        state["spans"][span] = _fit_span(rows, span, use_gbm)
        if not transport:
            continue
        # out-of-fold raw scores -> the transport map (in-sample scores are over-spread)
        oof = np.zeros(len(rows))
        idx = np.arange(len(rows))
        for k in range(folds):
            te = idx[idx % folds == k]
            tr = idx[idx % folds != k]
            if len(tr) < 30 or not len(te):
                oof[te] = [_raw_score(state["spans"][span], rows[i], span, use_gbm) for i in te]
                continue
            sub = _fit_span([rows[i] for i in tr], span, use_gbm)
            for i in te:
                oof[i] = _raw_score(sub, rows[i], span, use_gbm)
        state["maps"][span] = _quantile_map(oof, [r["true6"] for r in rows])
    return state


def _predict(state, rec, span):
    span = int(max(1, min(5, span)))
    st = state["spans"].get(span) or state["spans"][max(state["spans"])]
    raw = _raw_score(st, rec, span, state["use_gbm"])
    if not state["transport"]:
        return float(raw)
    m = state["maps"].get(span)
    return _apply_map(m, raw) if m else float(raw)


# --- the exported candidate API --------------------------------------------

def fit(train_rows):
    """Primary arm: rate-anchored two-part score, quantile-transported."""
    return _fit(train_rows, use_gbm=False, transport=True)


def predict(state, rec, span):
    return _predict(state, rec, span)


# --- sibling arms, reported for transparency (not the pre-selected headline) -
def fit_raw(rows):
    return _fit(rows, use_gbm=False, transport=False)


def fit_gbm(rows):
    return _fit(rows, use_gbm=True, transport=True)


def fit_gbm_raw(rows):
    return _fit(rows, use_gbm=True, transport=False)


CANDIDATES = {
    "R1_rate_anchored":     (fit, predict),          # PRE-SELECTED headline
    "R2_rate_raw":          (fit_raw, _predict),
    "R3_rate_gbm":          (fit_gbm, _predict),
    "R4_rate_gbm_raw":      (fit_gbm_raw, _predict),
}


# ---------------------------------------------------------------------------
# replication check: re-run the same simulation on shifted cohort splits. The
# official split (early 2011-15 / mid 2016-18 / test 2019-20) is a single draw;
# a real instrument should survive re-cutting the calendar.
# ---------------------------------------------------------------------------

ALT_SPLITS = (((2011, 2015), (2016, 2018), (2019, 2020), "OFFICIAL"),
              ((2011, 2013), (2014, 2015), (2016, 2018), "ALT-A test 2016-18"),
              ((2011, 2013), (2014, 2016), (2017, 2019), "ALT-B test 2017-19"),
              ((2011, 2014), (2015, 2017), (2018, 2020), "ALT-C test 2018-20"))


def replicate(spans=(2, 3, 4), boot=1500, seed=11):
    from efv_model import _vec, _fit_ols_fv, _pred_ols, _feature_spec
    from prospect_path import _spearman, _fit_ridge, _predict as _rpredict
    pool = H.build_pool("pit")
    keys, _ = _feature_spec("pit")
    rng = np.random.default_rng(seed)

    def grp(lo, hi):
        return [r for r in pool if lo <= r["dy"] <= hi]

    def arm(early, mid, labels, test):
        data = [{"feats": _vec(r["row"], "pit"), "target": float(t),
                 "fv": float(r["row"]["consensus_fv_raw"]), "player_key": r["pk"]}
                for r, t in ([(x, x["true6"]) for x in early] + list(zip(mid, labels)))
                if t is not None]
        ridge = _fit_ridge(data, keys)
        ols = _fit_ols_fv(data)
        return np.array([(1 - H.LAM_PIT) * max(0.0, _pred_ols(ols, float(r["row"]["consensus_fv_raw"])))
                         + H.LAM_PIT * _rpredict(ridge, _vec(r["row"], "pit")) for r in test])

    for e, m, t, tag in ALT_SPLITS:
        early, mid, test = grp(*e), grp(*m), grp(*t)
        truth = np.array([r["true6"] for r in test])
        st = fit(early)
        print(f"\n{tag}: early {e} n={len(early)} | mid {m} n={len(mid)} | test {t} n={len(test)}")
        for span in spans:
            km = arm(early, mid, [H.km_label(r, span) for r in mid], test)
            orc = arm(early, mid, [r["true6"] for r in mid], test)
            r1 = arm(early, mid, [predict(st, r, span) for r in mid], test)

            def rho(p, i):
                return _spearman(list(p[i]), list(truth[i]))

            full = np.arange(len(test))
            d = np.array([rho(r1, i) - rho(km, i)
                          for i in (rng.integers(0, len(test), len(test)) for _ in range(boot))])
            print(f"   span{span}: KM {rho(km, full):+.4f}  ORACLE {rho(orc, full):+.4f}  "
                  f"R1 {rho(r1, full):+.4f}   R1-KM {rho(r1, full) - rho(km, full):+.4f} "
                  f"CI95[{np.quantile(d, .025):+.4f},{np.quantile(d, .975):+.4f}] P(>0)={np.mean(d > 0):.3f}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if "--replicate" in args:
        replicate()
    else:
        for sp in ([int(a) for a in args] or [2, 3, 4]):
            print("=" * 78)
            H.run_gate(CANDIDATES, span=sp, side="pit")
            print()
