# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
bayes_blend.py — Principled Bayesian (conjugate Normal-Normal) version of the
xwOBA blend, replacing the grid-searched constant k.

Model per player-half:
    observed xwOBA_i ~ Normal(true_i, sigma_obs_i^2),  sigma_obs_i^2 = s2_pa_i / n_pa_i
    prior            true_i ~ Normal(model_pred_i, tau^2)
Posterior (closed form):
    post_mean_i = (obs_i/sigma_obs_i^2 + pred_i/tau^2) / (1/sigma_obs_i^2 + 1/tau^2)
    post_sd_i   = sqrt( 1 / (1/sigma_obs_i^2 + 1/tau^2) )     -> credible interval
    w_i (weight on observed) = (1/sigma_obs_i^2) / (1/sigma_obs_i^2 + 1/tau^2)

Note the constant-k blend w = n_pa/(n_pa+k) is the SPECIAL CASE where s2_pa is
constant across players (then k = s2_pa/tau^2). So this generalizes it by using
each player's actual per-PA xwOBA variance, and yields credible intervals.

s2_pa (per-PA xwOBA variance) and tau^2 are estimated empirically (method of
moments) using OUT-OF-FOLD model predictions so the value test is honest.

SANITY checks + VALUE-ADDED check (next-half OOF) vs the current constant-k
blend. If it doesn't beat (or at least tie) the constant-k blend, ditch it.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
from pa_value import PAValueModel
from train_pa_value import make_pipe

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROC = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
PV = PAValueModel(PROJECT / "pa_value_models.joblib")
FEATS = PV.features
K_CONST = PV.blend_k["xwoba"]   # current grid-searched k (250)


def pa_with_var(label):
    df = pd.read_parquet(RAW / f"statcast_{label}.parquet",
                         columns=["batter", "type", "woba_value", "woba_denom",
                                  "estimated_woba_using_speedangle"])
    pa = df[df["woba_denom"] == 1].copy()
    pa["xw"] = pa["estimated_woba_using_speedangle"]
    nb = pa["type"] != "X"
    pa.loc[nb, "xw"] = pa.loc[nb, "woba_value"]
    out = pa.groupby("batter").agg(
        n_pa=("woba_denom", "sum"),
        obs_xwoba=("xw", "mean"),
        pa_var=("xw", "var"),
    ).reset_index()
    out["half"] = label
    return out


def cv_oof(frame, feats, target):
    sub = frame.dropna(subset=feats + [target]).reset_index(drop=True)
    X, y, g = sub[feats], sub[target], sub["batter"]
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    sub["oof"] = oof
    return sub


def r(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    return float(np.corrcoef(a[m], b[m])[0, 1])


def main():
    half = pd.read_parquet(PROC / "leaderboard_half.parquet")
    pav = pd.concat([pa_with_var(h) for h in HALVES], ignore_index=True)
    m = half.merge(pav[["batter", "half", "pa_var"]], on=["batter", "half"], how="inner")
    m = m[m["n_pa"] >= 50].dropna(subset=FEATS + ["obs_xwoba", "pa_var"]).reset_index(drop=True)
    m = cv_oof(m, FEATS, "obs_xwoba")           # honest model pred

    s2_pa_league = float(m["pa_var"].median())
    # sigma_obs^2 per player: per-player var (shrunk toward league to stabilize)
    m["s2_pa_shrunk"] = (m["pa_var"] * m["n_pa"] + s2_pa_league * 100) / (m["n_pa"] + 100)
    m["sig2_obs_pp"] = m["s2_pa_shrunk"] / m["n_pa"]
    m["sig2_obs_lg"] = s2_pa_league / m["n_pa"]

    # tau^2 via method of moments: Var(obs - pred) = tau^2 + E[sigma_obs^2]
    resid = m["obs_xwoba"] - m["oof"]
    tau2 = float(resid.var() - m["sig2_obs_lg"].mean())
    tau2 = max(tau2, 1e-5)
    implied_k = s2_pa_league / tau2

    def posterior(sig2_obs):
        prec_o, prec_p = 1 / sig2_obs, 1 / tau2
        pm = (m["obs_xwoba"] * prec_o + m["oof"] * prec_p) / (prec_o + prec_p)
        psd = np.sqrt(1 / (prec_o + prec_p))
        w = prec_o / (prec_o + prec_p)
        return pm, psd, w

    m["bayes_lg"], m["bayes_sd"], m["w_lg"] = posterior(m["sig2_obs_lg"])
    m["bayes_pp"], _, m["w_pp"] = posterior(m["sig2_obs_pp"])
    w_const = m["n_pa"] / (m["n_pa"] + K_CONST)
    m["blend_const"] = w_const * m["obs_xwoba"] + (1 - w_const) * m["oof"]

    print("=" * 74)
    print("SANITY CHECKS")
    print("=" * 74)
    print(f"  league per-PA xwOBA variance s2_pa = {s2_pa_league:.4f}  (sd/PA={np.sqrt(s2_pa_league):.3f})")
    print(f"  estimated tau^2 (model irreducible) = {tau2:.5f}  (tau={np.sqrt(tau2):.3f})")
    print(f"  implied k = s2_pa/tau^2 = {implied_k:.0f}   vs grid-searched k = {K_CONST}")
    print(f"  weight-on-observed by PA bucket (should rise with PA):")
    m["pab"] = pd.cut(m["n_pa"], [50, 150, 300, 500, 5000])
    print(m.groupby("pab", observed=True)[["w_lg", "w_pp", "bayes_sd"]].mean().round(3).to_string())
    print(f"  bayes_lg vs constant-k blend corr = {r(m['bayes_lg'].values, m['blend_const'].values):.4f} "
          f"(should be ~1.0 — bayes-league reduces to constant-k)")
    print(f"  post_mean in [obs,pred] range: "
          f"{float(((m['bayes_pp']>=np.minimum(m.obs_xwoba,m.oof)-1e-9)&(m['bayes_pp']<=np.maximum(m.obs_xwoba,m.oof)+1e-9)).mean()*100):.0f}%")
    print(f"  credible-interval width (±1.96 sd) by PA: "
          f"50-150PA ±{1.96*m[m.n_pa<150].bayes_sd.mean():.3f}, 500+PA ±{1.96*m[m.n_pa>=500].bayes_sd.mean():.3f}")

    # ---------- VALUE-ADDED: next-half OOF ----------
    def nh(h):
        s, sh = h.split("_"); return f"{s}_H2" if sh == "H1" else f"{int(s)+1}_H1"
    m["next_half"] = m["half"].map(nh)
    nxt = m[["batter", "half", "obs_xwoba", "n_pa"]].rename(
        columns={"half": "next_half", "obs_xwoba": "xw_next", "n_pa": "n_pa_next"})
    pf = m.merge(nxt, on=["batter", "next_half"], how="inner")
    pf = pf[pf["n_pa_next"] >= 100]
    a = pf["xw_next"].values
    print("\n" + "=" * 74)
    print(f"VALUE-ADDED: predict next-half xwOBA (OOF), n={len(pf)}")
    print("=" * 74)
    rows = {
        "observed only (persistence)": pf["obs_xwoba"].values,
        "model only (appr17)":          pf["oof"].values,
        f"constant-k blend (k={K_CONST}) [current]": pf["blend_const"].values,
        "BAYES (league var)":           pf["bayes_lg"].values,
        "BAYES (per-player var)":       pf["bayes_pp"].values,
    }
    for lbl, v in rows.items():
        print(f"  {lbl:<40} r = {r(v, a):.4f}")
    # low-PA tail (where Bayesian per-player var should help most)
    lo = pf[pf["n_pa"] < 250]
    al = lo["xw_next"].values
    print(f"\n  LOW-PA tail (H_t < 250 PA), n={len(lo)}:")
    for lbl, col in [("constant-k blend", "blend_const"),
                     ("BAYES (league var)", "bayes_lg"),
                     ("BAYES (per-player var)", "bayes_pp")]:
        print(f"    {lbl:<26} r = {r(lo[col].values, al):.4f}")

    # ---------- CREDIBLE-INTERVAL CALIBRATION (the value of #2) ----------
    # Predictive interval for next-half obs = post_mean ± 1.96*sqrt(post_var + sig2_obs_next).
    # Well-calibrated => ~95% coverage. Uses the league-var posterior (point est
    # ties the constant-k blend, so CIs are consistent with the shipped number).
    print("\n" + "=" * 74)
    print("CREDIBLE-INTERVAL CALIBRATION (next-half coverage; target 95% / 50%)")
    print("=" * 74)
    post_var = pf["bayes_sd"].values ** 2
    sig2_next = s2_pa_league / pf["n_pa_next"].values
    pred_sd = np.sqrt(post_var + sig2_next)
    z = np.abs(pf["xw_next"].values - pf["bayes_lg"].values) / pred_sd
    print(f"  95% interval coverage: {float((z <= 1.96).mean()*100):.1f}%   (target ~95%)")
    print(f"  50% interval coverage: {float((z <= 0.674).mean()*100):.1f}%   (target ~50%)")
    print(f"  mean |z|: {float(np.mean(z)):.2f}  (well-calibrated ~0.80)")


if __name__ == "__main__":
    main()
