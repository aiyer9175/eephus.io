# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""error_bellcurve.py — Bell-curve visual of how close predicted xwOBA is to actual."""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.model_selection import GroupKFold
from pa_value import PAValueModel
from train_pa_value import make_pipe

PROC = Path(__file__).parent / "data" / "processed"
PV = PAValueModel(Path(__file__).parent / "pa_value_models.joblib")

half = pd.read_parquet(PROC / "leaderboard_half.parquet")
half["season"] = half["half"].str.split("_").str[0]
sub = half.dropna(subset=PV.features + ["obs_xwoba", "n_pa"]).reset_index(drop=True)

X, y, g = sub[PV.features], sub["obs_xwoba"], sub["batter"]
oof = np.full(len(y), np.nan)
for tr, te in GroupKFold(5).split(X, y, g):
    oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
sub["oof"] = oof
sub["err"] = sub["obs_xwoba"] - sub["oof"]

# half-season (>=200 PA) and full-season (PA-weighted to player-season, >=450 PA)
half_err = sub[sub.n_pa >= 200]["err"].to_numpy()
rows = []
for (b, s), gp in sub.groupby(["season", "batter"]):
    pa = gp.n_pa.to_numpy(float)
    rows.append({"pa": pa.sum(),
                 "err": np.average(gp.obs_xwoba, weights=pa) - np.average(gp.oof, weights=pa)})
ssn = pd.DataFrame(rows)
full_err = ssn[ssn.pa >= 450]["err"].to_numpy()

plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#ccc"})
fig, ax = plt.subplots(figsize=(10, 6))
xs = np.linspace(-0.12, 0.12, 400)

for err, color, label in [(half_err, "#e6a83c", "Half-season (≥200 PA)"),
                          (full_err, "#3f7fd6", "Full season (≥450 PA)")]:
    mu, sd = err.mean(), err.std(ddof=1)
    mae = np.abs(err).mean()
    ax.hist(err, bins=45, density=True, color=color, alpha=0.20)
    pdf = stats.norm.pdf(xs, mu, sd)
    ax.plot(xs, pdf, color=color, lw=2.5,
            label=f"{label}\n  ±1σ = ±{sd:.3f}  ·  avg miss = ±{mae:.3f}")
    # shade ±1 SD
    band = (xs >= mu - sd) & (xs <= mu + sd)
    ax.fill_between(xs[band], pdf[band], color=color, alpha=0.12)

ax.axvline(0, color="#444", ls="--", lw=1.2)
ax.set_xlim(-0.10, 0.10)
ax.set_ylim(bottom=0)
ax.set_xlabel("predicted xwOBA  −  actual xwOBA", fontsize=12)
ax.set_yticks([])
ax.set_title("How close is predicted xwOBA to actual results?\n"
             "out-of-fold error · 0 = perfect · ~68% of hitters within ±1σ",
             fontsize=14, pad=14)
ax.legend(fontsize=11, frameon=False, loc="upper left")
for s in ["top", "right", "left"]:
    ax.spines[s].set_visible(False)
ax.annotate("model nails it", xy=(0, stats.norm.pdf(0, full_err.mean(), full_err.std(ddof=1))),
            xytext=(0.035, 22), fontsize=10, color="#444",
            arrowprops=dict(arrowstyle="->", color="#888"))
fig.tight_layout()
out = PROC / "error_bellcurve.png"
fig.savefig(out, dpi=140, bbox_inches="tight", facecolor="white")
print(f"saved {out}")
print(f"half: n={len(half_err)} sd={half_err.std(ddof=1):.3f}  "
      f"full: n={len(full_err)} sd={full_err.std(ddof=1):.3f}")
