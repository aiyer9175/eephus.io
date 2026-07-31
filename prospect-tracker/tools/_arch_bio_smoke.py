import sys, time
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools")
import _arch_bio_gate as G
for side in ("hit", "pit"):
    rows = G.load(side)
    nb = sum(1 for r in rows if r["bio"]["bmi"] is not None)
    nf = sum(1 for r in rows if r["bio"]["frame"] is not None)
    print(f"== {side}: lab pool n={len(rows)}  bmi {nb} ({nb/len(rows):.1%})  frame {nf} ({nf/len(rows):.1%})")
    for kind in ("none", "bmi", "linear", "frame", "arch_inter", "arch_strat"):
        t = time.time(); r = G.evaluate(rows, kind, side)
        print(f"  {kind:11s} n={r['n']:4d} rho={r['rho']:.4f} pure={r['rho_pure']:.4f} "
              f"t45={r['t45']:.4f} wtm={r['within_tier_wm']:.4f}  ({time.time()-t:.1f}s)")
