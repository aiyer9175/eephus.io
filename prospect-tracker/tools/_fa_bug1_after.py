"""BUG-1 before/after on the SERVED future-class payloads (in memory only;
writes nothing)."""
import sys, os, json, statistics
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fa_export as fx

def summarize(d, tag):
    ms = d.get("members") or []
    pr = [m for m in ms if m.get("projGuar")]
    dp = sorted(m["dealPlus"] for m in pr if m.get("dealPlus") is not None)
    negp = sum(1 for m in ms if any(w < 0 for w in (m.get("warPath") or [])))
    negl = sum(1 for m in ms if any(w < 0 for w in (m.get("warPathP10") or [])))
    bad = sum(1 for m in ms
              if m.get("warPath") and m.get("warPathP90")
              and any(a > b for a, b in zip(m["warPath"], m["warPathP90"])))
    y1 = [m["warY1"] for m in ms if m.get("warY1") is not None]
    g = [m["projGuar"] / 1e6 for m in pr]
    print(f"{tag}: {len(ms)} members / {len(pr)} priced")
    print(f"   warY1 sum {sum(y1):.1f}  median {statistics.median(y1):.2f}")
    if dp:
        print(f"   Deal+ p10/p50/p90 {dp[len(dp)//10]}/{dp[len(dp)//2]}/{dp[9*len(dp)//10]}"
              f"  verdicts {dict(Counter(m.get('verdict') for m in pr))}")
    print(f"   projGuar median ${statistics.median(g):.2f}M  sum ${sum(g):.0f}M")
    print(f"   NEGATIVE season in warPath {negp}, in warPathP10 {negl};"
          f"  rows where mean > p90: {bad}")

if __name__ == "__main__":
    for y in (2028, 2029):
        summarize(fx.build_fa_class_payload(y), f"fa_class_{y} AFTER")
