"""Member-level before/after on the SERVED 2027 board (in memory, writes nothing)."""
import sys, os, statistics, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fa_market as fm, fa_export as fx

def build(mode, strict):
    fm.LAB_RESET()
    fm.DESTALE_MODE = mode
    fm.COMPS_STRICT_PRIOR = strict
    fx._MLB_PROJ_CACHE = None
    return fx.build_fa_class_payload(2027)

if __name__ == "__main__":
    a = build("vf", False)      # pre-lane
    b = build("series", True)   # shipped
    fm.LAB_RESET()
    A = {m["key"]: m for m in a["members"]}
    B = {m["key"]: m for m in b["members"]}
    keys = [k for k in A if k in B and A[k].get("projGuar") and B[k].get("projGuar")]
    print(f"n compared {len(keys)}   dpw ${a['dpw_usd']/1e6:.2f}M -> ${b['dpw_usd']/1e6:.2f}M"
          f"   infl {a['dpw_infl']} -> {b['dpw_infl']}")
    rg = [B[k]["projGuar"] / A[k]["projGuar"] for k in keys]
    rr = [B[k]["rational"] / max(A[k]["rational"], 1) for k in keys]
    print(f"projGuar  ratio after/before: median {statistics.median(rg):.3f}  mean {statistics.mean(rg):.3f}")
    print(f"rational  ratio after/before: median {statistics.median(rr):.3f}  mean {statistics.mean(rr):.3f}")
    print("\nbiggest projGuar movers:")
    for k in sorted(keys, key=lambda k: -abs(B[k]["projGuar"] - A[k]["projGuar"]))[:12]:
        x, y = A[k], B[k]
        print(f"  {x['name']:<22} {x['projYears']}yr ${x['projGuar']/1e6:>6.1f}M D+{x['dealPlus']:>4}"
              f"   ->  {y['projYears']}yr ${y['projGuar']/1e6:>6.1f}M D+{y['dealPlus']:>4}"
              f"   warY1 {x.get('warY1')}")
