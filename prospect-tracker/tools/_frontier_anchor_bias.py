# SCRATCH: the WELL-POWERED half of the claim -- measure the FanGraphs/MLB-Pipeline FV
# scale offset three independent ways and show the shipped consensus does not remove it.
from __future__ import annotations
import json, io, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import _frontier_anchor_level2 as L

OUT = Path(__file__).resolve().parent / "_frontier_out"
RNG = np.random.default_rng(20260724)
res = {}


def ci(v, lo=2.5, hi=97.5):
    return float(np.percentile(v, lo)), float(np.percentile(v, hi))


print("=" * 78)
print("A. PAIRED GRADE OFFSET (same players, both outlets), historical eFV pool")
tot = []
for s in ("hit", "pit"):
    a = L.load(s)
    both = np.isfinite(a["fg"]) & np.isfinite(a["mp"])
    d = a["mp"][both] - a["fg"][both]
    b = np.array([d[RNG.integers(0, len(d), len(d))].mean() for _ in range(4000)])
    lo, hi = ci(b)
    print(f"  {s}: n_pair={len(d):5d} mean {d.mean():+.3f} sd {d.std():.2f} "
          f"SE {d.std()/np.sqrt(len(d)):.3f} CI95 [{lo:+.3f},{hi:+.3f}] "
          f"median {np.median(d):+.1f}  P(MP>FG) {(d>0).mean():.3f} P(MP<FG) {(d<0).mean():.3f}")
    res[f"paired_{s}"] = {"n": int(len(d)), "mean": float(d.mean()), "sd": float(d.std()),
                          "se": float(d.std() / np.sqrt(len(d))), "ci": [lo, hi]}
    tot.append(d)
d = np.concatenate(tot)
print(f"  BOTH: n_pair={len(d)} mean {d.mean():+.3f} SE {d.std()/np.sqrt(len(d)):.3f}")
res["paired_all"] = {"n": int(len(d)), "mean": float(d.mean()),
                     "se": float(d.std() / np.sqrt(len(d)))}

print("\nB. LIVE BOARD (data/timeseries.json, latest point per player)")
ts = json.load(io.open(Path(__file__).resolve().parent.parent / "data" / "timeseries.json",
                       encoding="utf-8"))
gp, cdiff = [], []
for p in ts["players"]:
    pts = p.get("points") or []
    if not pts:
        continue
    pt = pts[-1]
    per = pt.get("per_source") or {}
    f = (per.get("fangraphs") or {}).get("fv_published")
    m = (per.get("mlb_pipeline") or {}).get("fv_published")
    c = pt.get("consensus_fv_raw")
    if f is None or m is None or c is None:
        continue
    gp.append(m - f)
    cdiff.append(c - (f + m) / 2.0)
gp = np.array(gp, float); cdiff = np.array(cdiff, float)
b = np.array([gp[RNG.integers(0, len(gp), len(gp))].mean() for _ in range(4000)])
lo, hi = ci(b)
print(f"  n_pair={len(gp)} MP-FG mean {gp.mean():+.3f} SE {gp.std()/np.sqrt(len(gp)):.3f} "
      f"CI95 [{lo:+.3f},{hi:+.3f}] median {np.median(gp):+.1f}")
print(f"  shipped consensus_fv_raw minus the plain 2-source mean: {cdiff.mean():+.4f} "
      f"(sd {cdiff.std():.3f})  -> the grade-normalization layer removes "
      f"{abs(cdiff.mean())/ (gp.mean()/2) * 100:.1f}% of the {gp.mean()/2:+.2f} it would need to")
res["live"] = {"n": int(len(gp)), "gap_mean": float(gp.mean()),
               "gap_se": float(gp.std() / np.sqrt(len(gp))), "gap_ci": [lo, hi],
               "cons_minus_plainmean": float(cdiff.mean())}

print("\nC. OUTCOME-EQUIVALENCE OFFSET (paired players only): the FV at which each outlet's")
print("   grade implies the SAME expected first-6yr WAR.  WAR ~ a + b*FV fit per outlet")
print("   on the identical player set, so coverage cannot explain the difference.")
for s in ("hit", "pit"):
    a = L.load(s)
    both = np.flatnonzero(np.isfinite(a["fg"]) & np.isfinite(a["mp"]))
    fg, mp, y, w = a["fg"][both], a["mp"][both], a["y"][both], a["w"][both]

    def offs(idx):
        of = L.wols(fg[idx], y[idx], w[idx])
        om = L.wols(mp[idx], y[idx], w[idx])
        # FV level of each outlet at the common mean WAR
        ybar = float(np.average(y[idx], weights=w[idx]))
        return ((ybar - om[0]) / om[1]) - ((ybar - of[0]) / of[1]), of[1], om[1]
    pt, bf, bm = offs(np.arange(len(both)))
    bs = np.array([offs(RNG.integers(0, len(both), len(both)))[0] for _ in range(2000)])
    lo, hi = ci(bs)
    print(f"  {s}: n={len(both)} outcome-equivalence offset (MP minus FG, FV pts) "
          f"{pt:+.2f} CI95 [{lo:+.2f},{hi:+.2f}]  | WAR-per-FV slope FG {bf:.4f} MP {bm:.4f}")
    res[f"outcome_offset_{s}"] = {"n": int(len(both)), "offset": float(pt), "ci": [lo, hi],
                                  "slope_fg": float(bf), "slope_mp": float(bm)}

print("\nD. STABILITY OF THE OFFSET BY DECISION YEAR (paired rows)")
for s in ("hit", "pit"):
    a = L.load(s)
    line = []
    for Y in range(2017, 2026):
        m = (a["dy"] == Y) & np.isfinite(a["fg"]) & np.isfinite(a["mp"])
        if m.sum() < 10:
            continue
        dd = a["mp"][m] - a["fg"][m]
        line.append(f"{Y}:{dd.mean():+.2f}(n{int(m.sum())})")
    print(f"  {s}: " + "  ".join(line))
    res.setdefault("by_year", {})[s] = line

json.dump(res, open(OUT / "_anchor_bias.json", "w"), indent=1, default=float)
print("\nwrote", OUT / "_anchor_bias.json")
