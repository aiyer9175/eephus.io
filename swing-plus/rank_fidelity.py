# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
rank_fidelity.py — How well does the PREDICTED ordering of players match the
OBSERVED ordering, for predicted xwOBA + the 5 batted-ball stats?

Uses the career (all-time) board, qualified hitters (so observed rankings are
stable, not sampling noise). Reports per stat:
  - Spearman rho, Kendall tau  (rank agreement)
  - rank-displacement distribution |pred_rank - obs_rank|: median / mean / p90
  - top-25 and top-10 overlap (precision@N)
  - the #1 predicted player and where he ranks observed (and vice versa)
Saves a small-multiples scatter of predicted rank vs observed rank.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROC = Path(__file__).parent / "data" / "processed"
PA_MIN = 400   # career-qualified: stable observed rankings

STATS = [
    ("pred_xwoba",       "obs_xwoba",       "Predicted xwOBA (PA)", 3),
    ("pred_xwobacon",    "obs_xwobacon",    "xwOBAcon",             3),
    ("pred_avg_ev",      "obs_avg_ev",      "Avg EV",               1),
    ("pred_hard_hit_pct","obs_hard_hit_pct","Hard-Hit%",            1),
    ("pred_barrel_pct",  "obs_barrel_pct",  "Barrel%",              1),
    ("pred_avg_la",      "obs_avg_la",      "Avg LA",               1),
]


def main():
    at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")
    q = at[at["n_pa"] >= PA_MIN].copy()
    print(f"Career board, qualified n_pa>={PA_MIN}: {len(q)} hitters\n")

    rows = []
    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    for ax, (pc, oc, label, dec) in zip(axes.ravel(), STATS):
        d = q.dropna(subset=[pc, oc]).copy()
        d["pr"] = d[pc].rank(ascending=False, method="min")
        d["orr"] = d[oc].rank(ascending=False, method="min")
        rho = stats.spearmanr(d[pc], d[oc]).correlation
        tau = stats.kendalltau(d[pc], d[oc]).correlation
        disp = (d["pr"] - d["orr"]).abs()
        n = len(d)
        top25_p = set(d.nsmallest(25, "pr")["batter"])
        top25_o = set(d.nsmallest(25, "orr")["batter"])
        top10_p = set(d.nsmallest(10, "pr")["batter"])
        top10_o = set(d.nsmallest(10, "orr")["batter"])
        # #1 predicted -> observed rank
        p1 = d.loc[d["pr"].idxmin()]
        o1 = d.loc[d["orr"].idxmin()]
        rows.append({
            "stat": label, "n": n,
            "spearman": round(rho, 3), "kendall": round(tau, 3),
            "med|Δrank|": int(disp.median()), "mean|Δrank|": round(disp.mean(), 1),
            "p90|Δrank|": int(disp.quantile(0.9)),
            "top25 ovlp": f"{len(top25_p & top25_o)}/25",
            "top10 ovlp": f"{len(top10_p & top10_o)}/10",
            "#1 pred (obs rank)": f"{p1['name']} (obs #{int(p1['orr'])})",
        })
        ax.scatter(d["pr"], d["orr"], s=14, alpha=0.45, color="#4f9eff", edgecolors="none")
        lim = [0, n + 1]
        ax.plot(lim, lim, "--", color="#bbb", lw=1)
        ax.set_title(f"{label}\nSpearman ρ={rho:.3f}", fontsize=11)
        ax.set_xlabel("predicted rank"); ax.set_ylabel("observed rank")
        ax.set_xlim(lim); ax.set_ylim(lim); ax.invert_xaxis(); ax.invert_yaxis()
    fig.suptitle(f"Predicted vs observed player rank (career, n_pa≥{PA_MIN}, n={len(q)})",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(PROC / "rank_fidelity.png", dpi=130, bbox_inches="tight", facecolor="white")

    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    print(f"\n(med|Δrank| = typical positions a player moves between the two orders, of {len(q)})")
    print(f"saved {PROC/'rank_fidelity.png'}")

    # Concrete #1-#5 side by side for EV and xwOBA
    for pc, oc, label, dec in [("pred_avg_ev", "obs_avg_ev", "Avg EV", 1),
                               ("pred_xwoba", "obs_xwoba", "xwOBA", 3)]:
        d = q.dropna(subset=[pc, oc]).copy()
        print(f"\nTop 5 by PREDICTED {label}  (obs rank in parens):")
        d["orr"] = d[oc].rank(ascending=False, method="min").astype(int)
        top = d.nlargest(5, pc)
        for _, r in top.iterrows():
            print(f"   {r['name']:<20} pred {r[pc]:.{dec}f}  ->  obs {r[oc]:.{dec}f}  (obs #{int(r['orr'])})")


if __name__ == "__main__":
    main()
