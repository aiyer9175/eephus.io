# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""swing_anim_mockup.py — Animated 3D swing concept.
The bat sweeps a full arc (load -> downswing -> contact -> follow-through). The
load/downswing/follow-through are a GENERIC canned motion (we can't measure them);
the COMPETITIVE CONTACT ZONE is highlighted and its geometry (attack angle, attack
direction, swing tilt, contact depth) reflects the player's REAL data. Renders a
GIF + a 6-frame montage PNG."""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from mpl_toolkits.mplot3d import Axes3D  # noqa

PROC = Path(__file__).parent / "data" / "processed"
PLAYER = dict(name="Aaron Judge 2024", attack_angle=14.1, attack_dir=-3.9, tilt=39.6, depth=29.5)
HI = "#1f6fd6"     # highlighted measured zone
GHOST = "#c4c8d0"  # generic un-measured motion

R = 2.5                                   # arc radius (ft)
PHI = np.linspace(-2.5, 1.5, 220)         # full swing sweep (rad), 0 = contact
WIN = 0.42                                # +/- rad around contact = "measured zone"


def swing_arc(p):
    aa, az, tilt = map(np.radians, (p["attack_angle"], p["attack_dir"], p["tilt"]))
    xc = p["depth"] / 12.0
    contact = np.array([xc, 0.0, 2.6])
    t = np.array([np.cos(aa)*np.cos(az), np.cos(aa)*np.sin(az), np.sin(aa)])   # tangent @ contact
    up = np.array([0, 0, 1.0])
    n0 = np.cross(t, up); n0 /= np.linalg.norm(n0)
    ang = tilt - np.radians(45)                       # swing-tilt rotates the plane about tangent
    n = (n0*np.cos(ang) + np.cross(t, n0)*np.sin(ang) + t*np.dot(t, n0)*(1-np.cos(ang)))
    O = contact + R * n                                # arc center
    a = (contact - O) / R                              # contact direction from center
    b = t                                              # travel direction at contact
    path = O[None,:] + R*(np.cos(PHI)[:,None]*a[None,:] + np.sin(PHI)[:,None]*b[None,:])
    return path, contact


def setup_ax(ax):
    # strike zone + ground
    for z in (1.6, 3.4):
        ax.plot([0,0], [-0.7,0.7], [z,z], color="#e2e2e2", lw=1)
    for yy in (-0.7, 0.7):
        ax.plot([0,0], [yy,yy], [1.6,3.4], color="#e2e2e2", lw=1)
    ax.plot([5.0, PLAYER["depth"]/12], [0.3,0], [4.4,2.6], color="#e0a93c", lw=2)
    ax.set_xlim(-2.6,5.2); ax.set_ylim(-2.2,2.2); ax.set_zlim(0,4.7)
    ax.set_xlabel("out front (ft)", fontsize=8); ax.set_ylabel("oppo ◀ ▶ pull", fontsize=8)
    ax.set_zlabel("height", fontsize=8); ax.view_init(elev=15, azim=-60)
    ax.set_box_aspect((1.7,1.2,1.0)); ax.tick_params(labelsize=7)


def main():
    path, contact = swing_arc(PLAYER)
    inwin = np.abs(PHI) <= WIN

    # ---- montage: 6 frames across the swing ----
    frames = [40, 80, 120, 150, 175, 210]
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), subplot_kw={"projection": "3d"}, facecolor="white")
    labels = ["load", "downswing", "approach", "CONTACT", "extension", "follow-through"]
    for ax, fr, lab in zip(axes.ravel(), frames, labels):
        setup_ax(ax)
        ax.plot(path[:,0], path[:,1], path[:,2], color="#eee", lw=1)          # full arc faint
        seg = path[:fr+1]
        # generic (ghost) part of the traveled trail
        ax.plot(seg[:,0], seg[:,1], seg[:,2], color=GHOST, lw=2.4)
        # highlight measured zone wherever it's been traveled
        hw = inwin[:fr+1]
        if hw.any():
            hi = seg[hw]
            ax.plot(hi[:,0], hi[:,1], hi[:,2], color=HI, lw=4)
        head = path[fr]
        ax.scatter([head[0]],[head[1]],[head[2]], color=(HI if inwin[fr] else GHOST), s=55, zorder=6)
        intitle = " · measured zone" if inwin[fr] else ""
        ax.set_title(f"{lab}{intitle}", fontsize=10,
                     color=(HI if inwin[fr] else "#888"), fontweight="bold")
    fig.suptitle(f"Animated swing concept — {PLAYER['name']}\n"
                 "grey = generic motion (not tracked) · blue = measured contact zone (real data)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.93])
    fig.savefig(PROC/"swing_anim_frames.png", dpi=110, bbox_inches="tight", facecolor="white")
    print("saved swing_anim_frames.png")

    # ---- the actual GIF ----
    figG = plt.figure(figsize=(7,6), facecolor="white"); axG = figG.add_subplot(111, projection="3d")
    def update(fr):
        axG.clear(); setup_ax(axG)
        axG.plot(path[:,0],path[:,1],path[:,2], color="#f0f0f0", lw=1)
        seg = path[:fr+1]
        axG.plot(seg[:,0],seg[:,1],seg[:,2], color=GHOST, lw=2.4)
        hw = inwin[:fr+1]
        if hw.any():
            hi = seg[hw]; axG.plot(hi[:,0],hi[:,1],hi[:,2], color=HI, lw=4)
        head = path[fr]
        axG.scatter([head[0]],[head[1]],[head[2]], color=(HI if inwin[fr] else GHOST), s=55)
        axG.set_title(f"{PLAYER['name']} — blue = measured contact zone", fontsize=10)
    anim = FuncAnimation(figG, update, frames=range(0,len(PHI),3), interval=60)
    anim.save(PROC/"swing_anim.gif", writer=PillowWriter(fps=18))
    print("saved swing_anim.gif")


if __name__ == "__main__":
    main()
