# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Render a report-card graphic for the MLB Swing-Decision (Plate Discipline+) model.
Numbers are passed in via the RESULTS dict (filled from audit_decision.py output)."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np

# ---- results (from the v2 base-out audit) ----
R = dict(
    overall="A-",
    coverage="802 hitters scored  (external model: 148)",
    components=[  # (label, grade, detail)
        ("Reliability",         "A",  "split-half r 0.80 · year-to-year r 0.75"),
        ("Calibration / build", "A",  "called-strike + base-out run-value tables clean"),
        ("Selectivity",         "A",  "R² 0.31 (swing rate) -> 0.87 (+selectivity)"),
        ("Run value (base-out)","A-", "delta_run_exp · ~30 wOBA pts/yr best-worst spread"),
        ("Face validity",       "A",  "Choi/Belt/Tucker top · Baez/Cron bottom"),
        ("vs SEAGER (discipline)","A-","beats on BB% proj 0.49 vs 0.29 & stability 0.75 vs 0.66"),
        ("Predictiveness",      "B",  "same-yr wOBA r 0.24 (orthogonal to power by design)"),
        ("Leakage",             "B+", "low; EV_swing uses own outcomes (by design)"),
    ],
    tests=[
        ("Coverage", "802"),
        ("Split-half reliability", "r 0.80"),
        ("Year-to-year (Self)", "r 0.75"),
        ("Optimal-policy accuracy", "69%"),
        ("Selectivity R^2", "0.87"),
        ("Decision entropy corr", "-0.55"),
        ("Expected RV spread", "~30 runs/yr"),
        ("vs external Decision+", "r 0.64"),
        ("vs swing-decision talent+", "r 0.79"),
        ("Next-yr BB% (vs SEAGER)", "0.49 vs 0.29"),
        ("Same-season wOBA", "r 0.24"),
        ("Damage-aware variant", "r 0.99 to pure"),
    ],
)


def render(res, out="data/processed/decision_report_card.png"):
    fig = plt.figure(figsize=(11, 8.0), dpi=150)
    fig.patch.set_facecolor("#0e1014")
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    teal = "#35b66a"; amber = "#e0a64a"; txt = "#e6e9ef"; mut = "#8a93a3"; panel = "#161a22"; bord = "#262c38"
    gcol = {"A":"#35b66a","A-":"#5fbf7e","A−":"#5fbf7e","B+":"#9ec06a","B":"#cbb256","B-":"#d39a4a"}
    # header
    ax.text(4, 95, res.get("title", "Plate Discipline+"), fontsize=27, fontweight="bold", color=txt, va="top")
    ax.text(4, 89.5, res.get("subtitle", "MLB swing-tailored decision model · independent audit"), fontsize=12, color=mut, va="top")
    ax.text(4, 85.6, res["coverage"], fontsize=11, color=teal, va="top")
    # overall grade badge
    cir = plt.Circle((88, 90), 7.2, color=gcol.get(res["overall"], teal), transform=ax.transData)
    ax.add_patch(cir)
    ax.text(88, 90, res["overall"], fontsize=30, fontweight="bold", color="#10120f", ha="center", va="center")
    ax.text(88, 80.3, "OVERALL", fontsize=10, color=mut, ha="center")
    # components grid (left)
    ax.text(4, 78, "COMPONENTS", fontsize=12, fontweight="bold", color=txt)
    y = 73
    for lab, g, det in res["components"]:
        ax.add_patch(FancyBboxPatch((4, y-4.4), 56, 5.4, boxstyle="round,pad=0.3,rounding_size=0.6",
                                    fc=panel, ec=bord, lw=1))
        ax.add_patch(plt.Circle((8.5, y-1.7), 2.5, color=gcol.get(g, mut)))
        ax.text(8.5, y-1.7, g, fontsize=11, fontweight="bold", color="#10120f", ha="center", va="center")
        ax.text(13.5, y-0.6, lab, fontsize=12, fontweight="bold", color=txt, va="center")
        ax.text(13.5, y-3.1, det.format(**res), fontsize=9.5, color=mut, va="center")
        y -= 6.2
    # tests run (right)
    ax.text(64, 78, "TESTS RUN", fontsize=12, fontweight="bold", color=txt)
    y = 73
    for name, val in res["tests"]:
        ax.text(64, y, "•", fontsize=12, color=teal, va="center")
        ax.text(66, y, name, fontsize=10.5, color=txt, va="center")
        ax.text(96, y, val, fontsize=10.5, color=amber, va="center", ha="right", fontweight="bold")
        y -= 4.5
    ax.text(4, 4.5, res.get("footer", "Run value via Statcast delta_run_exp (full base-out × count). 50/100 = league avg.  Tailored: EV_swing uses the hitter's own swing outcomes."),
            fontsize=8.5, color=mut, va="center")
    fig.savefig(out, facecolor=fig.get_facecolor(), bbox_inches="tight")
    print("wrote", out)


if __name__ == "__main__":
    render(R, out="web/static/decision_report_card.png")
