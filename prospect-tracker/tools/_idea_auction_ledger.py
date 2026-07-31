import sqlite3, json, collections, statistics
c=sqlite3.connect('prospects.db')
rows=[json.loads(r[0]) for r in c.execute("select payload_json from fa_signings")]
mlb=[r for r in rows if r.get('mlb_deal')]
led=[r for r in mlb if r.get('ledger')]
print("mlb deals",len(mlb),"with ledger",len(led))
comp=[r for r in led if r['ledger'].get('complete')]
print("complete ledgers",len(comp))
print("keys",sorted(led[0]['ledger']))
# surplus stats by guarantee size
def sur(r): return r['ledger']['surplus_to_date_usd']/1e6
big=[r for r in comp if r['guarantee_usd']>=50e6]
small=[r for r in comp if r['guarantee_usd']<50e6]
for nm,g in (("all",comp),(">=50M",big),("<50M",small)):
    s=[sur(r) for r in g]
    print(f"{nm:8s} n={len(s):4d} mean surplus ${statistics.mean(s):8.1f}M median ${statistics.median(s):8.1f}M  frac<0 {sum(1 for x in s if x<0)/len(s):.2f}")
# by contract length
byy=collections.defaultdict(list)
for r in comp: byy[min(r['years'],6)].append(sur(r))
for y in sorted(byy): print("yrs",y,"n",len(byy[y]),"mean",round(statistics.mean(byy[y]),1))
# by qo
for q in (True,False):
    s=[sur(r) for r in comp if bool(r.get('qo'))==q]
    print("qo",q,"n",len(s),"mean",round(statistics.mean(s),1))
# how many teams are distinct signers per winter
print(collections.Counter(r['class_year'] for r in comp))
