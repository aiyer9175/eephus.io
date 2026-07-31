"""SCRATCH (ideation only, no repo writes): CBT bunching feasibility probe."""
import sys, json, statistics, collections
sys.path.insert(0,'.')
import fa_sources, fa_cba
rows=[]
for y in range(2017,2027):
    try:
        tax=fa_sources.scrape_spotrac_tax(y)
    except Exception as e:
        print(y,"ERR",e); continue
    thr=fa_cba.cbt_threshold(y)["threshold_usd"]
    for r in tax:
        v=r.get("tax_payroll_usd")
        if v: rows.append({"y":y,"team":r["team"],"tax":v,"thr":thr,"rel":(v-thr)/thr,
                           "payor":r.get("payor_status_raw")})
print("team-seasons:",len(rows), "seasons:",sorted(set(r['y'] for r in rows)))
print("sample:",rows[0])
# histogram of normalized distance to threshold, 2.5% bins
bins=collections.Counter()
for r in rows:
    b=round(r["rel"]/0.025)
    bins[b]+=1
for b in sorted(bins):
    if -8<=b<=8:
        print(f"{b*2.5:+6.1f}% .. {b*2.5+2.5:+5.1f}%  n={bins[b]:3d} {'#'*bins[b]}")
below=[r for r in rows if -0.05<=r["rel"]<0]
above=[r for r in rows if 0<=r["rel"]<0.05]
print("within -5%..0 :",len(below)," 0..+5% :",len(above))
