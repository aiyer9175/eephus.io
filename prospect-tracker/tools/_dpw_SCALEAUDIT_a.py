# SCRATCH LAB (lane: scale-audit) part (a)+(c). Read-only.
# Paired difference distribution between the calibration-fit scale (RAW median
# snapshot FV) and the production scale (NORMALIZED consensus), plus the same
# comparison under the PRE-repair normalizer.
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
OUT = _HERE / "tools" / "_dpw_out"
POOL = json.loads((OUT / "scale_pool.json").read_text(encoding="utf-8"))

CAL_YEARS = (2017, 2018, 2019)
RNG = np.random.default_rng(20260725)


def stats(d):
    d = np.asarray(d, dtype=float)
    return dict(n=int(d.size), mean=float(d.mean()), median=float(np.median(d)),
                sd=float(d.std(ddof=1)) if d.size > 1 else 0.0,
                p01=float(np.percentile(d, 1)), p05=float(np.percentile(d, 5)),
                p25=float(np.percentile(d, 25)), p75=float(np.percentile(d, 75)),
                p95=float(np.percentile(d, 95)), p99=float(np.percentile(d, 99)),
                mn=float(d.min()), mx=float(d.max()),
                pct_moved=float(100 * np.mean(np.abs(d) > 1e-9)),
                mean_abs=float(np.mean(np.abs(d))))


def boot_mean(d, key, reps=2000):
    """Player-clustered bootstrap of the mean paired difference. Cells are
    (player, cycle); we resample PLAYERS so repeat cycles stay together."""
    byp = {}
    for r in d:
        byp.setdefault(r["player_key"], []).append(r[key] - r["raw"])
    keys = list(byp)
    vals = [byp[k] for k in keys]
    out = []
    for _ in range(reps):
        idx = RNG.integers(0, len(keys), len(keys))
        s = [v for i in idx for v in vals[i]]
        out.append(float(np.mean(s)))
    o = np.array(out)
    return float(np.percentile(o, 2.5)), float(np.percentile(o, 97.5))


def profile(rows, key, label):
    print(f"\n  {label}: difference AS A FUNCTION OF the fit-scale FV")
    print(f"    {'raw FV band':>14} {'n':>6} {'mean d':>8} {'median d':>9} "
          f"{'sd':>6} {'p05':>7} {'p95':>7} {'%moved':>7}")
    bands = [(40, 45), (45, 50), (50, 55), (55, 60), (60, 65), (65, 100)]
    for lo, hi in bands:
        sub = [r for r in rows if lo <= r["raw"] < hi]
        if len(sub) < 10:
            continue
        d = [r[key] - r["raw"] for r in sub]
        s = stats(d)
        band = f"{lo}-{hi - 1 if hi < 100 else '80'}"
        print(f"    {band:>14} {s['n']:>6} {s['mean']:>8.3f} {s['median']:>9.3f} "
              f"{s['sd']:>6.3f} {s['p05']:>7.2f} {s['p95']:>7.2f} {s['pct_moved']:>6.1f}%")


def report(rows, tag):
    print(f"\n================ {tag}  (n cells {len(rows)}) ================")
    for key, lbl in (("new", "NEW normalized (post 2026-07-25 repair, SHIPS NOW)"),
                     ("old", "OLD normalized (pre-repair, what was live)")):
        d = [r[key] - r["raw"] for r in rows]
        s = stats(d)
        lo, hi = boot_mean(rows, key)
        print(f"\n  {lbl}  minus RAW-median (the calibration-fit scale), FV points")
        print(f"    n {s['n']}  mean {s['mean']:+.4f} [player-boot 95% {lo:+.4f}, {hi:+.4f}]"
              f"  median {s['median']:+.3f}  sd {s['sd']:.3f}")
        print(f"    mean|d| {s['mean_abs']:.4f}  pct of cells moved {s['pct_moved']:.1f}%")
        print(f"    pctiles  p01 {s['p01']:+.2f}  p05 {s['p05']:+.2f}  p25 {s['p25']:+.2f}  "
              f"p75 {s['p75']:+.2f}  p95 {s['p95']:+.2f}  p99 {s['p99']:+.2f}  "
              f"[min {s['mn']:+.2f}, max {s['mx']:+.2f}]")
        profile(rows, key, lbl)


def main():
    cal = [r for r in POOL if r["year"] in CAL_YEARS and r["raw"] >= 40.0]
    allc = [r for r in POOL if r["raw"] >= 40.0]
    report(cal, "CALIBRATION FIT WINDOW 2017-2019 (the linearmap-v5 n=2,236 lineage pool)")
    report(allc, "ALL CYCLES 2017-2026")

    print("\n\n=== FORWARD-CHAINED TIME SPLITS (per listing cycle) ===")
    print(f"  {'cycle':>6} {'n':>6} | {'NEW mean d':>11} {'NEW p95|d| top':>15} | "
          f"{'OLD mean d':>11} {'OLD mean|d|':>12}")
    for y in sorted({r["year"] for r in allc}):
        sub = [r for r in allc if r["year"] == y]
        if len(sub) < 20:
            continue
        dn = np.array([r["new"] - r["raw"] for r in sub])
        do = np.array([r["old"] - r["raw"] for r in sub])
        top = np.array([r["new"] - r["raw"] for r in sub if r["raw"] >= 55])
        tv = float(top.mean()) if top.size else float("nan")
        print(f"  {y:>6} {len(sub):>6} | {dn.mean():>+11.4f} {tv:>+15.4f} | "
              f"{do.mean():>+11.4f} {float(np.abs(do).mean()):>12.4f}")

    print("\n\n=== (c) DID THE GAP EXIST BEFORE THE REPAIR?  fat middle vs top ===")
    print("  'fat middle' = raw median FV in [40,50) (68% of the fit window);"
          " 'top' = raw >= 55")
    for tag, rows in (("2017-2019 fit window", cal), ("all cycles", allc)):
        mid = [r for r in rows if 40 <= r["raw"] < 50]
        top = [r for r in rows if r["raw"] >= 55]
        print(f"  {tag}: middle n={len(mid)} ({100*len(mid)/len(rows):.0f}% of pool), top n={len(top)}")
        for lbl, sub in (("middle", mid), ("top   ", top)):
            do = np.array([r["old"] - r["raw"] for r in sub])
            dn = np.array([r["new"] - r["raw"] for r in sub])
            print(f"    {lbl}  OLD mean {do.mean():+.4f} mean|d| {np.abs(do).mean():.4f} "
                  f"moved {100*np.mean(np.abs(do)>1e-9):.1f}%   |   "
                  f"NEW mean {dn.mean():+.4f} mean|d| {np.abs(dn).mean():.4f} "
                  f"moved {100*np.mean(np.abs(dn)>1e-9):.1f}%")

    print("\n=== POOL-MEMBERSHIP SHIFT (the MIN_FV 40 gate is applied on the RAW scale) ===")
    for tag, yrs in (("2017-2019", CAL_YEARS), ("all cycles", tuple(range(2017, 2027)))):
        rows = [r for r in POOL if r["year"] in yrs]
        nr = sum(1 for r in rows if r["raw"] >= 40)
        nn = sum(1 for r in rows if r["new"] >= 40)
        no = sum(1 for r in rows if r["old"] >= 40)
        drop = sum(1 for r in rows if r["raw"] >= 40 and r["new"] < 40)
        add = sum(1 for r in rows if r["raw"] < 40 and r["new"] >= 40)
        print(f"  {tag}: raw-gated {nr}  old-gated {no}  new-gated {nn}   "
              f"(cells the new scale would DROP {drop}, ADD {add}; "
              f"net {100*(nn-nr)/nr:+.1f}% of the fit pool)")


if __name__ == "__main__":
    main()
