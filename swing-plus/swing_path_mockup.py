# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""swing_path_mockup.py — Mockup of an illustrative bat-path visual for the Adjust panel.
Shows the player's CURRENT swing (grey) vs an ADJUSTED swing (blue), to scale from
the slider inputs. Side view (attack angle + contact depth + tilt) + top-down (attack
direction). Schematic, not a measured 3D reconstruction."""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROC = Path(__file__).parent / "data" / "processed"

# Judge 2024 actual vs a sample adjustment (what the sliders would feed)
ACTUAL = dict(bat_speed=76.1, attack_angle=14.1, attack_dir=-3.9, tilt=39.6, depth=29.5)
ADJ    = dict(bat_speed=80.0, attack_angle=22.0, attack_dir=8.0,  tilt=42.0, depth=33.0)

GREY, BLUE = "#9aa0aa", "#1f6fd6"


def bat_arc(attack_angle_deg, depth_in, R=3.3, height=2.6):
    """Bat-head path as a circular arc; tangent at contact = attack angle."""
    a = np.radians(attack_angle_deg)
    xc, yc = depth_in / 12.0, height                 # contact point (ft)
    O = np.array([xc + R * np.sin(a), yc - R * np.cos(a)])   # circle center
    phi_c = a - np.pi / 2
    phis = np.linspace(phi_c - np.radians(55), phi_c + np.radians(22), 80)
    pts = O + R * np.column_stack([np.cos(phis), np.sin(phis)])
    return pts, (xc, yc), a


def draw_side(ax, p, color, label, lw):
    pts, (xc, yc), a = bat_arc(p["attack_angle"], p["depth"])
    ax.plot(pts[:, 0], pts[:, 1], color=color, lw=lw, label=label, solid_capstyle="round")
    # short bat at contact (along tangent)
    t = np.array([np.cos(a), np.sin(a)])
    bat = np.array([[xc, yc]]) + np.outer([-0.55, 0.35], t)
    ax.plot(bat[:, 0], bat[:, 1], color=color, lw=lw + 2.5, solid_capstyle="round", alpha=.85)
    ax.plot(xc, yc, "o", color=color, ms=7, zorder=5)
    # attack-angle annotation
    ax.annotate(f"{label}: {p['attack_angle']:.0f}° AA",
                xy=(xc, yc), xytext=(xc + 0.3, yc + (0.55 if color == BLUE else -0.75)),
                color=color, fontsize=9, fontweight="bold")


def draw_topdown(ax, p, color, label, lw):
    """Spray/bat direction from contact: + = pull. (Judge bats R → pull = left field.)"""
    ang = np.radians(90 + p["attack_dir"])      # 90° = straight up the middle
    L = 2.6
    x, y = L * np.cos(ang), L * np.sin(ang)
    ax.annotate("", xy=(x, y), xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=18))


def main():
    fig, (axS, axT) = plt.subplots(1, 2, figsize=(12, 5), facecolor="white",
                                   gridspec_kw={"width_ratios": [1.7, 1]})

    # ---- Side view ----
    axS.axhline(0, color="#cfcfcf", lw=1)                       # ground
    axS.text(0.05, 0.02, "ground", color="#bbb", fontsize=8)
    # incoming pitch (descending toward contact)
    axS.annotate("", xy=(ACTUAL["depth"]/12, 2.6), xytext=(5.2, 4.4),
                 arrowprops=dict(arrowstyle="-|>", color="#e0a93c", lw=2, mutation_scale=16))
    axS.text(4.4, 4.4, "pitch", color="#c8902e", fontsize=9)
    draw_side(axS, ACTUAL, GREY, "Current", 2.4)
    draw_side(axS, ADJ, BLUE, "Adjusted", 3.0)
    axS.set_xlim(-0.5, 5.5); axS.set_ylim(-0.3, 4.8)
    axS.set_aspect("equal"); axS.set_title("Side view — bat path through the zone", fontsize=11)
    axS.set_xlabel("distance out front (ft) →"); axS.set_yticks([]); axS.legend(loc="upper left", frameon=False)
    for s in ["top", "right", "left"]: axS.spines[s].set_visible(False)

    # ---- Top-down ----
    # field wedge
    for fl in (45, 135):
        axT.plot([0, 3 * np.cos(np.radians(fl))], [0, 3 * np.sin(np.radians(fl))], color="#ddd", lw=1)
    axT.plot(0, 0, "ko", ms=5)
    axT.text(0, -0.35, "home", ha="center", color="#999", fontsize=8)
    axT.text(-2.4, 2.4, "oppo (RF)", color="#bbb", fontsize=8)
    axT.text(1.5, 2.4, "pull (LF)", color="#bbb", fontsize=8)
    draw_topdown(axT, ACTUAL, GREY, "Current", 2.4)
    draw_topdown(axT, ADJ, BLUE, "Adjusted", 3.0)
    axT.annotate(f"{ACTUAL['attack_dir']:+.0f}°", xy=(0,0), xytext=(-1.7,1.0), color=GREY, fontsize=9, fontweight="bold")
    axT.annotate(f"{ADJ['attack_dir']:+.0f}°", xy=(0,0), xytext=(1.0,1.4), color=BLUE, fontsize=9, fontweight="bold")
    axT.set_xlim(-3, 3); axT.set_ylim(-0.6, 3); axT.set_aspect("equal")
    axT.set_title("Top-down — attack direction", fontsize=11); axT.axis("off")

    fig.suptitle("Illustrative swing path (to scale from the slider inputs) — Aaron Judge 2024",
                 fontsize=13, fontweight="bold")
    fig.text(0.5, 0.01, "Current (grey) vs Adjusted (blue: +8° attack angle, more pull, +4 mph). "
             "Schematic from attack angle / direction / contact depth — not a measured 3D path.",
             ha="center", fontsize=9, color="#777")
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])
    out = PROC / "swing_path_mockup.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
