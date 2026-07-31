# Scratch lab (audit-mode, lane=plusmetrics): how far do the SHRUNK values shown
# under the standard-stat labels ("FIP", "wOBA") sit from the real stat?
from __future__ import annotations
import json, os, sys
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
D = os.path.join(ROOT, "data")
import rem_plus as RP
load = lambda f: json.load(open(os.path.join(D, f), encoding="utf-8"))

print("=== pitcher boards: displayed 'FIP' is fip_skill (EB-shrunk), not FIP ===")
for f, key, ipk in [("bullpen_leaderboards.json", "relievers", "ip"),
                    ("starter_leaderboards.json", "starters", "ip")]:
    rows = load(f)[key]
    d = []
    for r in rows:
        tbf, ip = r.get("tbf"), r.get("ip")
        if not tbf or not ip:
            continue
        so = (r.get("k_pct") or 0) * tbf
        bb = (r.get("bb_pct") or 0) * tbf
        hr = (r.get("hr9") or 0) * ip / 9.0
        # raw FIP with the SAME cFIP the module used (back out from the pool):
        raw = (RP.FIP_HR * hr + RP.FIP_BBHBP * bb - RP.FIP_K * so) / ip
        d.append((r["name"], r["fip"], raw, ip, tbf, r.get("qualified")))
    # cFIP such that the IP-weighted raw FIP over the board equals the shown pool era
    pool_era = load(f)["pool"]["pool_era"] if "pool" in load(f) else None
    ips = np.array([x[3] for x in d]); raws = np.array([x[2] for x in d])
    shown = np.array([x[1] for x in d])
    cf = np.average(shown, weights=ips) - np.average(raws, weights=ips)
    est = raws + cf
    gap = shown - est
    q = np.array([bool(x[5]) for x in d])
    print(f"\n{f}  n={len(d)}  (cFIP backed out = {cf:.3f})")
    print(f"  |shown 'FIP' - reconstructed real FIP|  mean {np.abs(gap).mean():.3f}"
          f"  p50 {np.median(np.abs(gap)):.3f}  p90 {np.percentile(np.abs(gap),90):.3f}"
          f"  max {np.abs(gap).max():.3f}")
    print(f"  qualified only: mean {np.abs(gap[q]).mean():.3f}  max {np.abs(gap[q]).max():.3f}")
    ordr = np.argsort(-np.abs(gap))[:5]
    for i in ordr:
        print(f"    {d[i][0]:<24} shown {d[i][1]:5.2f}   real ~{est[i]:5.2f}   IP {d[i][3]:6.1f}")

print("\n=== hitter board: displayed 'wOBA' is woba_skill (EB-shrunk) ===")
rows = load("hitter_leaderboards.json")["hitters"]
sh = np.array([r["woba"] for r in rows if r.get("woba") is not None and r.get("woba_raw") is not None])
rw = np.array([r["woba_raw"] for r in rows if r.get("woba") is not None and r.get("woba_raw") is not None])
print(f"  n={len(sh)}  mean|shown - actual| {np.abs(sh-rw).mean():.4f}"
      f"  p90 {np.percentile(np.abs(sh-rw),90):.4f}  max {np.abs(sh-rw).max():.4f}")
print(f"  shown sd {sh.std(ddof=1):.4f}  actual sd {rw.std(ddof=1):.4f}"
      f"  (shrink compresses spread by {100*(1-sh.std(ddof=1)/rw.std(ddof=1)):.1f}%)")
