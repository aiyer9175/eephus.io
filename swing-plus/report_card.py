# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
report_card.py — One-page model report card: metrics table + predicted-vs-actual
scatter for every predicted stat, on career-qualified hitters.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROC = Path(__file__).parent / "data" / "processed"
PA_MIN = 400

# (stat key, label, decimals, unit)
STATS = [
    ("xwoba", "xwOBA (full PA)", 3, ""),
    ("xwobacon", "xwOBAcon", 3, ""),
    ("avg_ev", "Avg EV", 1, " mph"),
    ("avg_ev90", "EV90", 1, " mph"),
    ("barrel_pct", "Barrel%", 1, ""),
    ("hard_hit_pct", "Hard-Hit%", 1, ""),
    ("avg_la", "Avg LA", 1, "°"),
]


def main():
    at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")
    d = at[at["n_pa"] >= PA_MIN].copy()
    n = len(d)

    metrics = []
    for k, label, dec, unit in STATS:
        s = d.dropna(subset=[f"pred_{k}", f"obs_{k}"])
        p, o = s[f"pred_{k}"].to_numpy(), s[f"obs_{k}"].to_numpy()
        r = float(np.corrcoef(p, o)[0, 1])
        rho = float(stats.spearmanr(p, o).correlation)
        mae = float(np.abs(p - o).mean())
        metrics.append((label, r, r ** 2, mae, rho, dec, unit))

    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig = plt.figure(figsize=(16, 9.5), facecolor="white")
    gs = fig.add_gridspec(2, 4, hspace=0.42, wspace=0.28)

    # ---- metrics table (top-left cell) ----
    axt = fig.add_subplot(gs[0, 0]); axt.axis("off")
    rows = [[lab, f"{r:.3f}", f"{r2:.2f}", f"±{mae:.{dec+1 if dec==3 else 1}f}", f"{rho:.3f}"]
            for (lab, r, r2, mae, rho, dec, unit) in metrics]
    tbl = axt.table(cellText=rows,
                    colLabels=["Stat", "r", "R²", "MAE", "Spearman ρ"],
                    cellLoc="center", colLoc="center", loc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.55)
    for (rr, cc), cell in tbl._cells.items():
        if rr == 0:
            cell.set_facecolor("#1f6fd6"); cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor("#f4f7fb" if rr % 2 else "#ffffff")
        cell.set_edgecolor("#dddddd")

    # ---- scatter per stat (remaining 7 cells) ----
    cells = [gs[0, 1], gs[0, 2], gs[0, 3], gs[1, 0], gs[1, 1], gs[1, 2], gs[1, 3]]
    for cell, (k, label, dec, unit) in zip(cells, STATS):
        ax = fig.add_subplot(cell)
        s = d.dropna(subset=[f"pred_{k}", f"obs_{k}"])
        p, o = s[f"pred_{k}"].to_numpy(), s[f"obs_{k}"].to_numpy()
        r = float(np.corrcoef(p, o)[0, 1]); mae = float(np.abs(p - o).mean())
        ax.scatter(p, o, s=14, alpha=0.45, color="#1f6fd6", edgecolors="none")
        lim = [min(p.min(), o.min()), max(p.max(), o.max())]
        pad = (lim[1] - lim[0]) * 0.05
        lim = [lim[0] - pad, lim[1] + pad]
        ax.plot(lim, lim, "--", color="#d04545", lw=1.2)
        ax.set_xlim(lim); ax.set_ylim(lim)
        ax.set_title(f"{label}\nr={r:.3f}  R²={r**2:.2f}  MAE=±{mae:.{3 if dec==3 else 1}f}{unit}", fontsize=10)
        ax.set_xlabel("predicted", fontsize=8); ax.set_ylabel("observed", fontsize=8)
        ax.tick_params(labelsize=7); ax.grid(True, color="#eee")
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)

    fig.suptitle(f"Swing+ family — predicted batted-ball stats vs actual results "
                 f"· career-qualified hitters (n_pa≥{PA_MIN}, n={n})",
                 fontsize=14, fontweight="bold", y=1.00)
    fig.text(0.5, 0.005,
             "Full-sample fit (descriptive). Honest out-of-fold predictive r runs ~0.05–0.10 lower; "
             "see error-band tables. Dashed line = perfect prediction.",
             ha="center", fontsize=9, color="#666")
    out = PROC / "report_card.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"saved {out}\n")
    print(f"{'Stat':<18}{'r':>7}{'R²':>7}{'MAE':>9}{'Spearman':>10}")
    for (lab, r, r2, mae, rho, dec, unit) in metrics:
        print(f"{lab:<18}{r:>7.3f}{r2:>7.2f}{mae:>9.3f}{rho:>10.3f}")


if __name__ == "__main__":
    main()
