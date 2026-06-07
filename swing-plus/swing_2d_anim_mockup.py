# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""swing_2d_anim_mockup.py — 2D side-view animated swing concept.
Bat sweeps load -> downswing -> contact -> follow-through. Generic motion is grey
(not tracked); the measured CONTACT ZONE lights up blue with the player's real
attack-angle/contact-depth geometry. Shows CURRENT vs ADJUSTED. Renders a frame
montage PNG + a looping GIF."""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

PROC = Path(__file__).parent / "data" / "processed"
ACTUAL = dict(attack_angle=14.1, depth=29.5)
ADJ    = dict(attack_angle=22.0, depth=33.0)
GHOST, HI, ADJC = "#c4c8d0", "#1f6fd6", "#1c7a44"

R = 2.7
PHI = np.linspace(-2.3, 1.4, 240)     # full swing sweep, 0 = contact
WIN = 0.45                            # +/- rad = measured contact zone


def arc(p):
    """Side-view bat-head arc; tangent at contact = attack angle. x=out front, z=height."""
    aa = np.radians(p["attack_angle"]); xc = p["depth"]/12.0; zc = 2.6
    contact = np.array([xc, zc])
    t = np.array([np.cos(aa), np.sin(aa)])          # travel dir at contact
    n = np.array([np.sin(aa), -np.cos(aa)])         # toward arc center (below path)
    O = contact + R*n
    a = (contact - O)/R
    b = t
    pts = O[None,:] + R*(np.cos(PHI)[:,None]*a[None,:] + np.sin(PHI)[:,None]*b[None,:])
    return pts


def setup(ax):
    ax.axhline(0, color="#ddd", lw=1); ax.text(-1.4, .05, "ground", color="#bbb", fontsize=8)
    # strike zone
    ax.add_patch(plt.Rectangle((-0.25,1.6), 0.5, 1.8, fill=False, ec="#e2e2e2", lw=1))
    ax.plot([5.0, ACTUAL["depth"]/12],[4.4,2.6], color="#e0a93c", lw=2)
    ax.text(4.5,4.4,"pitch", color="#c8902e", fontsize=9)
    ax.set_xlim(-1.6,5.4); ax.set_ylim(-0.3,4.8); ax.set_aspect("equal")
    ax.set_xlabel("distance out front (ft) →", fontsize=9); ax.set_yticks([])
    for s in ["top","right","left"]: ax.spines[s].set_visible(False)


def trail(ax, pts, fr, ghost, hi, inwin, lw):
    seg = pts[:fr+1]
    ax.plot(seg[:,0], seg[:,1], color=ghost, lw=lw)
    hw = inwin[:fr+1]
    if hw.any():
        h = seg[hw]; ax.plot(h[:,0], h[:,1], color=hi, lw=lw+2)
    head = pts[fr]
    # bat at head
    if fr>0:
        d = pts[fr]-pts[fr-1]; d=d/ (np.linalg.norm(d)+1e-9)
        bat = np.array([head-0.55*d, head+0.3*d])
        ax.plot(bat[:,0],bat[:,1], color=(hi if inwin[fr] else ghost), lw=lw+3, solid_capstyle="round")
    ax.scatter([head[0]],[head[1]], color=(hi if inwin[fr] else ghost), s=45, zorder=6)


def main():
    cur, adj = arc(ACTUAL), arc(ADJ)
    inwin = np.abs(PHI) <= WIN

    # montage
    frames=[35,90,130,150,180,225]; labels=["load","downswing","approach","CONTACT","extension","follow-through"]
    fig,axes=plt.subplots(2,3,figsize=(14,7),facecolor="white")
    for ax,fr,lab in zip(axes.ravel(),frames,labels):
        setup(ax)
        ax.plot(cur[:,0],cur[:,1],color="#f0f0f0",lw=1)
        trail(ax,cur,fr,GHOST,HI,inwin,2.4)
        intit=" · measured zone" if inwin[fr] else ""
        ax.set_title(f"{lab}{intit}",fontsize=10,color=(HI if inwin[fr] else "#888"),fontweight="bold")
    fig.suptitle("2D side-view swing — grey = generic motion (not tracked) · blue = measured contact zone (real data)",
                 fontsize=12,fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.94])
    fig.savefig(PROC/"swing_2d_frames.png",dpi=110,bbox_inches="tight",facecolor="white"); print("saved swing_2d_frames.png")

    # GIF: current vs adjusted, both sweeping
    figG,axG=plt.subplots(figsize=(8,5.2),facecolor="white")
    def upd(fr):
        axG.clear(); setup(axG)
        axG.plot(cur[:,0],cur[:,1],color="#f3f3f3",lw=1); axG.plot(adj[:,0],adj[:,1],color="#eaf1fb",lw=1)
        trail(axG,cur,fr,GHOST,"#7f8794",inwin,2.0)           # current = greyer blue zone
        trail(axG,adj,fr,"#aebfd6",ADJC,inwin,2.6)            # adjusted = green zone
        axG.set_title("Current (grey) vs Adjusted (blue/green = measured zone)",fontsize=10)
        axG.text(-1.5,4.5,"Adjusted: +8° attack angle, further out front",color=ADJC,fontsize=9,fontweight="bold")
    anim=FuncAnimation(figG,upd,frames=range(0,len(PHI),3),interval=55)
    anim.save(PROC/"swing_2d_anim.gif",writer=PillowWriter(fps=20)); print("saved swing_2d_anim.gif")


if __name__=="__main__":
    main()
