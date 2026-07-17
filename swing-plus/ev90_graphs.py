# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""ev90_graphs.py — Predicted vs observed 90th-pctile EV: value scatter (Pearson) + rank view (Spearman)."""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROC = Path(__file__).parent / "data" / "processed"
PA_MIN = 400

at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")
d = at[at["n_pa"] >= PA_MIN].dropna(subset=["pred_avg_ev90", "obs_avg_ev90"]).copy()
p, o = d["pred_avg_ev90"].to_numpy(), d["obs_avg_ev90"].to_numpy()
r = float(np.corrcoef(p, o)[0, 1])
rho = stats.spearmanr(p, o).correlation
mae = float(np.abs(p - o).mean())
d["pr"] = d["pred_avg_ev90"].rank(ascending=False, method="min")
d["orr"] = d["obs_avg_ev90"].rank(ascending=False, method="min")
n = len(d)

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig, ax = plt.subplots(1, 2, figsize=(13, 5.6), facecolor="white")

# Panel 1: predicted vs observed value
a = ax[0]
a.scatter(p, o, s=22, alpha=0.5, color="#1f6fd6", edgecolors="none")
lim = [min(p.min(), o.min()) - 1, max(p.max(), o.max()) + 1]
a.plot(lim, lim, "--", color="#d04545", lw=1.3, label="perfect (y = x)")
a.set_xlim(lim); a.set_ylim(lim)
a.set_xlabel("predicted EV90 (mph)"); a.set_ylabel("observed EV90 (mph)")
a.set_title(f"Predicted vs observed EV90\nPearson r = {r:.3f}   ·   R² = {r**2:.2f}   ·   MAE = {mae:.2f} mph",
            fontsize=12)
a.legend(frameon=False, fontsize=10, loc="upper left")
a.grid(True, color="#eee")

# Panel 2: rank view
b = ax[1]
b.scatter(d["pr"], d["orr"], s=22, alpha=0.5, color="#2e9e6b", edgecolors="none")
rl = [0, n + 1]
b.plot(rl, rl, "--", color="#d04545", lw=1.3)
b.set_xlim(rl); b.set_ylim(rl); b.invert_xaxis(); b.invert_yaxis()
b.set_xlabel("predicted rank"); b.set_ylabel("observed rank")
b.set_title(f"EV90 player ranking: predicted vs observed\nSpearman ρ = {rho:.3f}   (n = {n})", fontsize=12)
b.grid(True, color="#eee")

for axis in ax:
    for s in ["top", "right"]:
        axis.spines[s].set_visible(False)
fig.suptitle(f"90th-percentile EV — career-qualified hitters (n_pa ≥ {PA_MIN})", fontsize=13)
fig.tight_layout()
out = PROC / "ev90_graphs.png"
fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
print(f"saved {out}")
print(f"n={n}  Pearson r={r:.3f}  R2={r**2:.3f}  Spearman rho={rho:.3f}  MAE={mae:.2f} mph")
# top-25 / top-10 overlap
t25 = len(set(d.nsmallest(25,'pr').batter) & set(d.nsmallest(25,'orr').batter))
t10 = len(set(d.nsmallest(10,'pr').batter) & set(d.nsmallest(10,'orr').batter))
print(f"top-25 overlap: {t25}/25   top-10 overlap: {t10}/10")
print(f"median |rank delta|: {int((d.pr-d.orr).abs().median())} of {n}")
