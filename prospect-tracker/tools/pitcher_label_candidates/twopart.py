# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""TWO-PART (hurdle) pitcher label instrument.

    label = observed early WAR (seasons 0..span-1)
          + P(accrues meaningful MLB workload in seasons span..5 | early window)
            * E[late WAR | it does]

Part 1 (hazard) is an L2 logistic on early-window workload/role/rate/age signals - the
features the attrition diagnostic showed carry survival information that early WAR does
not (seasons_pitched, ip_per_season, g, kbb, k_pct, age at debut).

Part 2 (magnitude) comes in two shapes:
  LIN   ridge on late WAR among early-cohort survivors.
  MULT  structural decoupling of BULK from QUALITY, which is the failure mode the
        transmission diagnostic identified (slow-burn aces on an IP cap under-ranked,
        early innings-eaters over-ranked):  E[late WAR] = IP_hat * (WAR/IP)_hat, with
        IP_hat fit on log1p(late IP) from workload/role and (WAR/IP)_hat fit on rate
        quality (k_pct, kbb, era) rather than realized early WAR/IP.

Every arm is offered raw and QUANTILE-MAPPED onto the early-cohort TRUE-6yr marginal:
the transmission diagnostic showed the label->model channel is ~pure rank (true ranks +
KM magnitudes captured 97.7% of the oracle headroom), so the monotone remap is free
insurance on level while preserving the instrument's ordering exactly.

CIRCULARITY: every input is post-debut REALIZED outcome data (career WAR by season, MLB
pitching lines, TJ years, age off the MLB line). rec['row'] (consensus FV, tool grades,
draft pick/bonus) is NEVER read.

SELECTION (how the headline arm was picked, and why the scoreboard needs guardrails)
  The "% of the oracle headroom" number is NOT information-clean. A label that is
  RANK-IDENTICAL to KM but shifted in level (war3 + 1.8) scores +43.2% at span 3 and
  +157.5% at span 4 on the harness. So this module always runs, alongside the candidates:
    CONTROLS      rank-identical-to-KM labels at several levels/scales (K1..K4).
    rank_vs_level a per-candidate decomposition into
                    cand           = cand ranks + cand marginal
                    cand|KMrank    = KM   ranks + cand marginal   (LEVEL only, no info)
                    cand|KMdist    = cand ranks + KM   marginal   (INFO only, KM's level)
  Candidate choice was made on FOUR leakage-clean INNER splits (fit/label/score windows
  entirely inside 2011-2018, never touching the 2019-2020 harness test cohort). Full
  inner-split sweep is in the run log; mean paired delta vs KM over the 4 inner splits:
    span3  U2 +0.0278  U3 +0.0216  U5 +0.0206  U4 +0.0172  T1 +0.0100  T3 +0.0042
    span4  U2 +0.0050  U5 +0.0024  T3 -0.0165
  U2_hazard_flat (hurdle with the survivor-mean magnitude) was best or near-best at
  every inner span, so it is the headline. The %headroom RATIO on the inner splits is
  unusable (denominators near zero), which is why the paired delta is the selector.

Usage:  python tools/pitcher_label_candidates/twopart.py [span ...]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_pitcher_label_harness as H          # noqa: E402

TARGET_SEASONS = 6
SPANS_FIT = (2, 3, 4, 5)


# ---------------------------------------------------------------------------
# features (post-debut realized only)
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


AGE_FILL = 24.5


def feats(rec, span: int) -> dict:
    """H.window() plus per-season trajectory / sparsity fields."""
    w = dict(H.window(rec, span))
    war_by = [_f(rec["war"].get(i)) for i in range(span)]
    ips, gsr, appear = [], [], []
    for i in range(span):
        ln = rec["lines"].get(i)
        if not ln:
            ips.append(0.0)
            gsr.append(0.0)
            appear.append(0.0)
            continue
        ip_i = _f(ln.get("ip"))
        g_i = _f(ln.get("g"))
        ips.append(ip_i)
        gsr.append((_f(ln.get("gs")) / g_i) if g_i else 0.0)
        appear.append(1.0 if ip_i > 0 else 0.0)

    span_f = float(max(1, span))
    seen = w["seasons_pitched"]
    has_lines = 1.0 if seen > 0 else 0.0
    last = span - 1
    age = _age_debut(rec)

    w.update({
        "appear_frac": seen / span_f,
        "has_lines": has_lines,
        "log_ip_ps": math.log1p(max(0.0, w["ip"]) / span_f),
        "ip_max": max(ips) if ips else 0.0,
        "ip_last": ips[last] if ips else 0.0,
        "ip_slope": ((ips[last] - ips[0]) / max(1, span - 1)) if span > 1 else 0.0,
        "war_last": war_by[last] if war_by else 0.0,
        "war_slope": ((war_by[last] - war_by[0]) / max(1, span - 1)) if span > 1 else 0.0,
        "gs_ratio_last": gsr[last] if gsr else 0.0,
        "gs_ratio_delta": (gsr[last] - gsr[0]) if span > 1 else 0.0,
        "age_debut": age if age is not None else AGE_FILL,
        "age_missing": 0.0 if age is not None else 1.0,
    })
    # quality decoupled from bulk: rate stats only mean something with real exposure
    w["kbb_x"] = w["kbb"] * min(1.0, w["ip"] / 80.0)
    w["k_pct_x"] = w["k_pct"] * min(1.0, w["ip"] / 80.0)
    return w


HAZ_KEYS = ["war_per_season", "log_ip_ps", "appear_frac", "seasons_pitched",
            "gs_ratio", "kbb_x", "k_pct_x", "age_debut", "age_missing",
            "ip_last", "ip_slope", "war_slope", "has_lines", "tj_in_window"]

MAG_KEYS = ["war_per_season", "log_ip_ps", "k_pct_x", "kbb_x", "era", "gs_ratio",
            "gs_ratio_last", "gs_ratio_delta", "war_slope", "ip_last", "ip_max",
            "age_debut", "age_missing", "appear_frac", "war_per_ip", "has_lines"]

IPH_KEYS = ["log_ip_ps", "ip_last", "ip_max", "ip_slope", "gs_ratio", "gs_ratio_last",
            "gs_ratio_delta", "appear_frac", "seasons_pitched", "war_per_season",
            "age_debut", "age_missing", "kbb_x", "has_lines"]

QAL_KEYS = ["kbb_x", "k_pct_x", "era", "bb_pct", "war_per_ip", "gs_ratio",
            "age_debut", "age_missing", "log_ip_ps"]


# ---------------------------------------------------------------------------
# tiny fitters (numpy, standardized + L2)
# ---------------------------------------------------------------------------

def _design(rows_f, keys):
    import numpy as np
    return np.array([[_f(r.get(k)) for k in keys] for r in rows_f], dtype=float)


def _standardize(X):
    import numpy as np
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    return mu, sd, (X - mu) / sd


def fit_ridge(rows_f, ys, keys, lam=8.0):
    import numpy as np
    X = _design(rows_f, keys)
    y = np.asarray(ys, dtype=float)
    mu, sd, Xs = _standardize(X)
    b = float(y.mean())
    A = Xs.T @ Xs + lam * np.eye(len(keys))
    w = np.linalg.solve(A, Xs.T @ (y - b))
    return {"keys": keys, "mu": mu, "sd": sd, "w": w, "b": b}


def pred_ridge(m, f):
    z = m["b"]
    for k, mu, sd, w in zip(m["keys"], m["mu"], m["sd"], m["w"]):
        z += w * ((_f(f.get(k)) - mu) / (sd or 1.0))
    return float(z)


def fit_logit(rows_f, ys, keys, lam=6.0, iters=60):
    """IRLS with an L2 penalty on standardized features (intercept unpenalized)."""
    import numpy as np
    X = _design(rows_f, keys)
    y = np.asarray(ys, dtype=float)
    mu, sd, Xs = _standardize(X)
    n, p = Xs.shape
    Z = np.hstack([np.ones((n, 1)), Xs])
    beta = np.zeros(p + 1)
    p_bar = float(min(max(y.mean(), 1e-3), 1 - 1e-3))
    beta[0] = math.log(p_bar / (1 - p_bar))
    P = np.eye(p + 1) * lam
    P[0, 0] = 0.0
    for _ in range(iters):
        eta = Z @ beta
        pr = 1.0 / (1.0 + np.exp(-np.clip(eta, -30, 30)))
        Wd = np.clip(pr * (1 - pr), 1e-6, None)
        grad = Z.T @ (y - pr) - P @ beta
        Hm = (Z * Wd[:, None]).T @ Z + P
        try:
            step = np.linalg.solve(Hm, grad)
        except np.linalg.LinAlgError:
            break
        beta = beta + step
        if float(np.max(np.abs(step))) < 1e-7:
            break
    return {"keys": keys, "mu": mu, "sd": sd, "beta": beta}


def pred_logit(m, f):
    z = float(m["beta"][0])
    for k, mu, sd, w in zip(m["keys"], m["mu"], m["sd"], m["beta"][1:]):
        z += float(w) * ((_f(f.get(k)) - mu) / (sd or 1.0))
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


# ---------------------------------------------------------------------------
# targets (realized outcomes, computed on the FIT cohort only)
# ---------------------------------------------------------------------------

def _late_war(rec, span):
    return sum(_f(rec["war"].get(i)) for i in range(span, TARGET_SEASONS))


def _late_ip(rec, span):
    tot = 0.0
    for i in range(span, TARGET_SEASONS):
        ln = rec["lines"].get(i)
        if ln:
            tot += _f(ln.get("ip"))
    return tot


def _survived(rec, span):
    """Accrued MLB workload in seasons span..5. career-WAR based => id-independent
    (10/105 of the production 2021 cohort have no mlbam id and would otherwise read
    as zero-appearance busts)."""
    return 1.0 if any(abs(_f(rec["war"].get(i))) > 1e-9
                      for i in range(span, TARGET_SEASONS)) else 0.0


# ---------------------------------------------------------------------------
# quantile transport (monotone; preserves the instrument's ordering exactly)
# ---------------------------------------------------------------------------

def _qmap_state(scores, targets):
    return {"src": sorted(float(s) for s in scores),
            "dst": sorted(float(t) for t in targets)}


def _qmap(st, x):
    src, dst = st["src"], st["dst"]
    n = len(src)
    lo, hi = 0, n
    while lo < hi:
        m = (lo + hi) // 2
        if src[m] < x:
            lo = m + 1
        else:
            hi = m
    i = lo
    j = i
    while j < n and src[j] == x:
        j += 1
    q = ((i + j) / 2.0) / max(1, n)                    # fractional rank in [0,1]
    if x > src[-1]:                                     # extrapolate above the fit range
        q = 1.0 - 0.5 / max(1, n)
    pos = q * (len(dst) - 1)
    a = int(math.floor(pos))
    b = min(len(dst) - 1, a + 1)
    fr = pos - a
    return dst[a] * (1 - fr) + dst[b] * fr


# ---------------------------------------------------------------------------
# the instrument
# ---------------------------------------------------------------------------

DEFAULTS = {
    "mult": False,        # multiplicative IP x quality magnitude arm
    "qmap": False,        # quantile-transport onto the fit-cohort true6 marginal
    "lam_mag": 8.0,       # L2 on the magnitude ridge
    "lam_haz": 6.0,       # L2 on the hazard logistic
    "mag_log": False,     # fit the magnitude arm on signed log1p(late WAR)
    "shape": "hurdle",    # hurdle | direct | hazard_only | km | scale
    "mag_keys": None,
    "haz_keys": None,
    "scale": 2.0,         # shape='scale': label = early WAR * scale (rank-identical to KM)
    "shift": 0.0,         # shape='scale': additive constant
    "mag_weight": 0.5,    # shape='hurdle_shrunk': weight on the modelled magnitude
}

# hazard ablation: WAR-only covariates (no workload / role / rate / age)
HAZ_WAR_ONLY = ["war_per_season", "war_last", "war_slope", "war_per_ip"]


def _cfg(**kw):
    c = dict(DEFAULTS)
    c.update(kw)
    return c


def _slog(x):
    return math.copysign(math.log1p(abs(x)), x)


def _sexp(x):
    return math.copysign(math.expm1(abs(x)), x)


def _fit_span(train, span, cfg):
    mult = cfg["mult"]
    ft = [feats(r, span) for r in train]
    surv = [_survived(r, span) for r in train]
    haz = fit_logit(ft, surv, cfg["haz_keys"] or HAZ_KEYS, lam=cfg["lam_haz"])

    mk = cfg["mag_keys"] or MAG_KEYS
    if cfg["shape"] == "direct":                       # one-part control: no hurdle
        idx = list(range(len(train)))
    else:
        idx = [i for i, s in enumerate(surv) if s > 0.5]
    sub_f = [ft[i] for i in idx]
    sub_r = [train[i] for i in idx]
    ys = [_late_war(r, span) for r in sub_r]
    if cfg["mag_log"]:
        ys = [_slog(y) for y in ys]
    mag = fit_ridge(sub_f, ys, mk, lam=cfg["lam_mag"])

    st = {"haz": haz, "mag": mag, "cfg": cfg,
          "surv_mean_late": (sum(_late_war(train[i], span) for i in idx) / max(1, len(idx)))}
    if mult:
        ip_idx = [i for i, r in enumerate(sub_r) if r["mlbam"]]
        f_ip = [sub_f[i] for i in ip_idx]
        r_ip = [sub_r[i] for i in ip_idx]
        st["iph"] = fit_ridge(f_ip, [math.log1p(max(0.0, _late_ip(r, span))) for r in r_ip],
                              IPH_KEYS, lam=6.0)
        # WAR per 200 late IP, on arms with real late exposure (shrunk toward the mean)
        q_idx = [i for i, r in enumerate(r_ip) if _late_ip(r, span) >= 40.0]
        f_q = [f_ip[i] for i in q_idx]
        r_q = [r_ip[i] for i in q_idx]
        st["qal"] = fit_ridge(f_q, [200.0 * _late_war(r, span) / max(40.0, _late_ip(r, span))
                                    for r in r_q], QAL_KEYS, lam=6.0)
        st["q_mean"] = (sum(200.0 * _late_war(r, span) / max(40.0, _late_ip(r, span))
                            for r in r_q) / max(1, len(r_q)))
    return st


def _score_span(st, rec, span):
    cfg = st["cfg"]
    f = feats(rec, span)
    p = pred_logit(st["haz"], f)
    e_lin = pred_ridge(st["mag"], f)
    if cfg["mag_log"]:
        e_lin = _sexp(e_lin)
    if cfg["shape"] == "km":
        return f["war"] * (TARGET_SEASONS / max(1, span))
    if cfg["shape"] == "scale":                        # rank-identical to KM by construction
        return f["war"] * cfg["scale"] + cfg["shift"]
    if cfg["shape"] == "direct":
        return f["war"] + e_lin
    if cfg["shape"] == "hazard_only":
        return f["war"] + p * st["surv_mean_late"]
    if cfg["shape"] == "hurdle_shrunk":               # magnitude shrunk to the survivor mean
        w = cfg["mag_weight"]
        return f["war"] + p * (w * e_lin + (1 - w) * st["surv_mean_late"])
    if cfg["mult"] and rec["mlbam"] and "iph" in st:
        ip_hat = max(0.0, math.expm1(pred_ridge(st["iph"], f)))
        q_hat = pred_ridge(st["qal"], f)
        # shrink the rate arm toward the survivor mean (thin-exposure protection)
        k = min(1.0, f["ip"] / 150.0)
        q_hat = k * q_hat + (1 - k) * st["q_mean"]
        e_late = ip_hat * q_hat / 200.0
    else:
        e_late = e_lin
    early = f["war"]
    return early + p * e_late


def _make(**kw):
    cfg = _cfg(**kw)

    def fit(train):
        st = {"spans": {s: _fit_span(train, s, cfg) for s in SPANS_FIT}, "cfg": cfg}
        if cfg["qmap"]:
            st["qm"] = {}
            tgt = [r["true6"] for r in train]
            for s in SPANS_FIT:
                sc = [_score_span(st["spans"][s], r, s) for r in train]
                st["qm"][s] = _qmap_state(sc, tgt)
        return st

    def predict(st, rec, span):
        sp = st["spans"].get(span) or st["spans"][min(SPANS_FIT, key=lambda s: abs(s - span))]
        v = _score_span(sp, rec, span)
        if cfg["qmap"]:
            qm = st["qm"].get(span)
            if qm:
                v = _qmap(qm, v)
        return v
    return fit, predict


# public single-candidate API == U2_hazard_flat (see SELECTION in the module docstring):
#   label = observed early WAR + P(survive | early window) * mean(late WAR | survivor)
fit, predict = _make(shape="hazard_only")


CANDIDATES = {
    "T1_hurdle_lin":       _make(mult=False, qmap=False),
    "T2_hurdle_lin_qmap":  _make(mult=False, qmap=True),
    "T3_hurdle_mult":      _make(mult=True, qmap=False),
    "T4_hurdle_mult_qmap": _make(mult=True, qmap=True),
    "U1_direct_onepart":   _make(shape="direct"),
    "U2_hazard_flat":      _make(shape="hazard_only"),
    "U3_hazard_flat_WARonly": _make(shape="hazard_only", haz_keys=HAZ_WAR_ONLY),
    "U4_hurdle_shrunk50":  _make(shape="hurdle_shrunk", mag_weight=0.5),
    "U5_hurdle_shrunk25":  _make(shape="hurdle_shrunk", mag_weight=0.25),
}

# Rank-identical-to-KM controls. Any blend-rho move these produce is PURE MAGNITUDE
# (level/scale), not information - they exist to keep the two-part arms honest.
CONTROLS = {
    "K1_scale_1.0":  _make(shape="scale", scale=1.0),
    "K2_scale_1.4":  _make(shape="scale", scale=1.4),
    "K3_scale_1.0_shift_1.8": _make(shape="scale", scale=1.0, shift=1.8),
    "K4_scale_0.5":  _make(shape="scale", scale=0.5),
}


# ---------------------------------------------------------------------------
# paired bootstrap on the harness test cohort (arm-level rho has boot_sd ~0.074;
# only PAIRED deltas are interpretable)
# ---------------------------------------------------------------------------

def _blend_preds(train_pairs, test_recs, side="pit"):
    """Same construction as H._model_arm, but returns per-row blend predictions."""
    from efv_model import _vec, _fit_ols_fv, _pred_ols, _feature_spec
    from prospect_path import _fit_ridge as _pp_ridge, _predict as _pp_pred
    keys, _m = _feature_spec(side)
    data = [{"feats": _vec(r["row"], side), "target": float(t),
             "fv": float(r["row"]["consensus_fv_raw"]), "player_key": r["pk"]}
            for r, t in train_pairs if t is not None]
    ridge = _pp_ridge(data, keys)
    ols = _fit_ols_fv(data)
    if not ridge or not ols:
        return None
    lam = H.LAM_PIT
    out = []
    for r in test_recs:
        f = _vec(r["row"], side)
        p = _pp_pred(ridge, f)
        out.append((1 - lam) * max(0.0, _pred_ols(ols, float(r["row"]["consensus_fv_raw"])))
                   + lam * p)
    return out


def paired_bootstrap(span=3, side="pit", B=2000, seed=20260724):
    import random
    from prospect_path import _spearman
    pool = H.build_pool(side)
    early, mid, test = H._split(pool)
    base = [(r, r["true6"]) for r in early]
    arms = {
        "A_KM": _blend_preds(base + [(r, H.km_label(r, span)) for r in mid], test, side),
        "C_oracle": _blend_preds(base + [(r, r["true6"]) for r in mid], test, side),
    }
    arms["Z_drop_mid"] = _blend_preds(base, test, side)
    for nm, (fn_fit, fn_pred) in list(CANDIDATES.items()) + list(CONTROLS.items()):
        st = fn_fit(early)
        arms[nm] = _blend_preds(base + [(r, fn_pred(st, r, span)) for r in mid], test, side)
    truth = [r["true6"] for r in test]
    n = len(truth)
    rng = random.Random(seed)
    idxs = [[rng.randrange(n) for _ in range(n)] for _ in range(B)]
    print(f"\n  PAIRED BOOTSTRAP vs A_KM (span={span}, B={B}, n_test={n})")
    print(f"    {'arm':22} {'delta':>8} {'sd':>7} {'ci95_lo':>8} {'ci95_hi':>8} {'P(>0)':>7}")
    a = arms["A_KM"]
    for nm, pr in arms.items():
        if nm == "A_KM" or pr is None:
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
        print(f"    {nm:22} {mean:+8.4f} {sd:7.4f} {ds[int(.025*B)]:+8.4f} "
              f"{ds[int(.975*B)]:+8.4f} {pgt:7.3f}")


def _transport(src_labels, dst_labels):
    """Return src_labels' RANKS carrying dst_labels' MARGINAL (quantile transport)."""
    order = sorted(range(len(src_labels)), key=lambda i: src_labels[i])
    vals = sorted(dst_labels)
    out = [0.0] * len(src_labels)
    for pos, i in enumerate(order):
        out[i] = vals[pos]
    return out


def rank_vs_level(span=3, side="pit", B=1000, seed=20260724):
    """Decompose each candidate's model gain into INFORMATION (rank) and LEVEL (marginal).

      cand      = cand ranks  + cand marginal      (the instrument)
      twinKMdist= KM   ranks  + cand marginal      (same level, NO new information)
      candKMdist= cand ranks  + KM   marginal      (new information, KM's level)

    gain(cand) - gain(twinKMdist) is the part the instrument actually earns.
    """
    import random
    from prospect_path import _spearman
    pool = H.build_pool(side)
    early, mid, test = H._split(pool)
    base = [(r, r["true6"]) for r in early]
    truth = [r["true6"] for r in test]
    tmid = [r["true6"] for r in mid]
    km = [H.km_label(r, span) for r in mid]

    def arm(labels):
        return _blend_preds(base + list(zip(mid, labels)), test, side)

    preds = {"A_KM": arm(km), "C_oracle": arm(tmid)}
    lab_of = {"A_KM": km, "C_oracle": tmid}
    for nm, (ff, pf) in CANDIDATES.items():
        st = ff(early)
        lab = [pf(st, r, span) for r in mid]
        lab_of[nm] = lab
        preds[nm] = arm(lab)
        t1 = _transport(km, lab)
        lab_of[nm + "|KMrank"] = t1
        preds[nm + "|KMrank"] = arm(t1)
        t2 = _transport(lab, km)
        lab_of[nm + "|KMdist"] = t2
        preds[nm + "|KMdist"] = arm(t2)

    n = len(truth)
    rng = random.Random(seed)
    ix = [[rng.randrange(n) for _ in range(n)] for _ in range(B)]
    a = preds["A_KM"]
    kmr = _spearman(a, truth)
    orr = _spearman(preds["C_oracle"], truth)
    hd = orr - kmr
    print(f"\n  RANK-vs-LEVEL DECOMPOSITION (span={span}, n_mid={len(mid)}, n_test={n}, B={B})")
    print(f"  KM blend {kmr:.4f} -> oracle {orr:.4f} (headroom +{hd:.4f})")
    print(f"    {'arm':28} {'lab_rho':>7} {'lab_mean':>8} {'blend':>7} {'%hr':>7} "
          f"{'dPAIR':>8} {'sd':>6} {'P(>0)':>6}")
    for nm, pr in preds.items():
        if pr is None:
            continue
        lab = lab_of[nm]
        br = _spearman(pr, truth)
        lr = _spearman(lab, tmid)
        if nm == "A_KM":
            d, sd, pg = 0.0, 0.0, 0.5
        else:
            ds = [(_spearman([pr[i] for i in q], [truth[i] for i in q]) or 0.0)
                  - (_spearman([a[i] for i in q], [truth[i] for i in q]) or 0.0) for q in ix]
            m = sum(ds) / len(ds)
            d = m
            sd = (sum((x - m) ** 2 for x in ds) / len(ds)) ** 0.5
            pg = sum(1 for x in ds if x > 0) / len(ds)
        print(f"    {nm:28} {lr:>7.4f} {sum(lab)/len(lab):>8.3f} {br:>7.4f} "
              f"{((br-kmr)/hd*100 if hd else 0):>6.1f}% {d:>+8.4f} {sd:>6.4f} {pg:>6.3f}")
    print("    INFORMATION-ONLY (cand minus its KM-rank twin, same marginal), paired boot:")
    print(f"      {'cand':26} {'gain':>8} {'lvl_twin':>8} {'INFO':>8} {'%hr':>7} "
          f"{'sd':>6} {'P(>0)':>6}")
    for nm in CANDIDATES:
        g = _spearman(preds[nm], truth) - kmr
        tw = preds[nm + "|KMrank"]
        gt = _spearman(tw, truth) - kmr
        c = preds[nm]
        ds = [(_spearman([c[i] for i in q], [truth[i] for i in q]) or 0.0)
              - (_spearman([tw[i] for i in q], [truth[i] for i in q]) or 0.0) for q in ix]
        m = sum(ds) / len(ds)
        sd = (sum((x - m) ** 2 for x in ds) / len(ds)) ** 0.5
        pg = sum(1 for x in ds if x > 0) / len(ds)
        print(f"      {nm:26} {g:>+8.4f} {gt:>+8.4f} {g-gt:>+8.4f} "
              f"{((g-gt)/hd*100 if hd else 0):>6.1f}% {sd:>6.4f} {pg:>6.3f}")


if __name__ == "__main__":
    spans = [int(a) for a in sys.argv[1:]] or [3, 4]
    allc = dict(CANDIDATES)
    allc.update(CONTROLS)
    for sp in spans:
        print("=" * 78)
        print(f"TWO-PART (hurdle x magnitude) pitcher label instrument - span={sp}")
        print("=" * 78)
        H.run_gate(allc, span=sp, side="pit")
    for sp in spans:
        paired_bootstrap(span=sp, B=1000)
    for sp in spans:
        rank_vs_level(span=sp, B=1000)
