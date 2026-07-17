# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""swing_path_3d_mockup.py — 3D illustrative bat-path mockup for the Adjust panel.
One 3D view encodes ALL slider inputs at once:
  attack_angle  -> vertical slope of the path at contact
  attack_dir    -> horizontal azimuth (pull/oppo) of the path
  tilt          -> the plane the swing travels in (rotates the arc plane)
  depth         -> where along x the ball is met (contact point)
Current (grey) vs Adjusted (blue). Schematic, not a measured 3D reconstruction."""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa

PROC = Path(__file__).parent / "data" / "processed"
ACTUAL = dict(bat_speed=76.1, attack_angle=14.1, attack_dir=-3.9, tilt=39.6, depth=29.5)
ADJ    = dict(bat_speed=80.0, attack_angle=22.0, attack_dir=8.0,  tilt=42.0, depth=33.0)
GREY, BLUE = "#9aa0aa", "#1f6fd6"


def swing_path(p, R=3.2, contact_height=2.6):
    """Bat-head path as a circular arc whose plane is tilted (swing tilt) and
    rotated in azimuth (attack direction); tangent at contact = attack angle.
    Returns (path Nx3, contact point xyz, bat segment 2x3). Axes: x=out front,
    y=pull(+)/oppo(-), z=up."""
    aa = np.radians(p["attack_angle"])
    az = np.radians(p["attack_dir"])
    tilt = np.radians(p["tilt"])
    xc = p["depth"] / 12.0
    contact = np.array([xc, 0.0, contact_height])

    # arc in its own plane (u along path tangent, v = in-plane normal)
    phis = np.linspace(-np.radians(70), np.radians(20), 90)
    local = np.column_stack([R * np.sin(phis), R * (1 - np.cos(phis)) - 0  # bowl
                             , np.zeros_like(phis)])
    # tangent direction at contact in 3D from attack angle + azimuth
    t = np.array([np.cos(aa) * np.cos(az), np.cos(aa) * np.sin(az), np.sin(aa)])
    # in-plane "down toward the bowl" axis, set by swing tilt about the tangent
    up = np.array([0, 0, 1.0])
    n0 = np.cross(t, up); n0 /= np.linalg.norm(n0)
    # rotate n0 around t by (tilt - 45deg) to express plane steepness
    k = t
    ang = tilt - np.radians(45)
    n = (n0 * np.cos(ang) + np.cross(k, n0) * np.sin(ang)
         + k * np.dot(k, n0) * (1 - np.cos(ang)))
    # build path: start behind contact along -t, curving along n
    s = np.linspace(-3.0, 0.8, 90)
    curve = 0.16
    path = contact[None, :] + np.outer(s, t) + np.outer(curve * s**2, n)
    bat = np.array([contact - 0.55 * t, contact + 0.30 * t])
    return path, contact, bat


def draw(ax, p, color, label, lw):
    path, c, bat = swing_path(p)
    ax.plot(path[:, 0], path[:, 1], path[:, 2], color=color, lw=lw, label=label)
    ax.plot(bat[:, 0], bat[:, 1], bat[:, 2], color=color, lw=lw + 3, solid_capstyle="round", alpha=.85)
    ax.scatter([c[0]], [c[1]], [c[2]], color=color, s=45, zorder=6)


def main():
    fig = plt.figure(figsize=(11, 8), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")

    # strike-zone-ish reference + ground
    zx = 0.0
    for z0, z1 in [(1.6, 1.6), (3.4, 3.4)]:
        ax.plot([zx, zx], [-0.7, 0.7], [z0, z1], color="#ddd", lw=1)
    for yy in (-0.7, 0.7):
        ax.plot([zx, zx], [yy, yy], [1.6, 3.4], color="#ddd", lw=1)
    # incoming pitch
    ax.plot([5.0, ACTUAL["depth"]/12], [0.25, 0], [4.3, 2.6], color="#e0a93c", lw=2)
    ax.text(5.0, 0.25, 4.45, "pitch", color="#c8902e", fontsize=9)

    draw(ax, ACTUAL, GREY, "Current swing", 2.6)
    draw(ax, ADJ, BLUE, "Adjusted swing", 3.2)

    ax.set_xlabel("out front (ft)"); ax.set_ylabel("oppo  ◀  ▶  pull")
    ax.set_zlabel("height (ft)")
    ax.set_xlim(-2.5, 5.2); ax.set_ylim(-2, 2); ax.set_zlim(0, 4.6)
    ax.view_init(elev=16, azim=-62)
    ax.set_box_aspect((1.7, 1.2, 1.0))
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    try: ax.set_facecolor("white")
    except Exception: pass
    ax.grid(True, color="#eee")
    fig.suptitle("Illustrative 3D swing path (to scale from slider inputs) — Aaron Judge 2024",
                 fontsize=13, fontweight="bold", y=0.94)
    fig.text(0.5, 0.04,
             "Current (grey) vs Adjusted (blue): +8° attack angle, more pull, steeper plane, +4 mph.\n"
             "Encodes attack angle (vertical), attack direction (pull/oppo), swing tilt (plane), contact depth — "
             "schematic, not a measured 3D reconstruction.",
             ha="center", fontsize=9, color="#777")
    out = PROC / "swing_path_3d_mockup.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
