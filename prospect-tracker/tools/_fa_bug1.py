"""BUG-1 evidence: fa_export splices a MEDIAN-basis ML path into a stack
whose pricer and market model both expect the CHAMPION MEAN path."""
import sys, os, json, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

mp = json.load(open(os.path.join(DATA, "mlb_projections.json")))
vets = {v["mlbam"]: v for v in mp["vets"] if v.get("mlbam")}
print("mlb_projections first_season", mp["first_season"], " vets", len(vets))
for k in ("war", "warChamp"):
    tot = sum(v[k][0] for v in vets.values())
    neg = sum(1 for v in vets.values() if any(w < 0 for w in v[k]))
    print(f"  {k:<9} year-1 league sum {tot:>7.1f}   vets with a negative season {neg}")

cls = json.load(open(os.path.join(DATA, "fa_class.json")))
mem = cls.get("members") or cls.get("class") or []
print("\nfa_class 2027 members", len(mem))
same = []
byname = {v["name"]: v for v in vets.values()}
bykey = {v["key"]: v for v in vets.values()}
for m in mem:
    v = bykey.get(m.get("key")) or byname.get(m.get("name"))
    if v and m.get("warPath"):
        same.append((m["name"], m["warPath"][0], v["war"][0], v["warChamp"][0]))
print(f"same player, SAME season 2027: n={len(same)}")
print(f"  FA champion warY1 sum   {sum(x[1] for x in same):>7.1f}")
print(f"  mlb_projections war[0]  {sum(x[2] for x in same):>7.1f}   ratio {sum(x[2] for x in same)/sum(x[1] for x in same):.3f}")
print(f"  mlb_projections champ[0]{sum(x[3] for x in same):>7.1f}   ratio {sum(x[3] for x in same)/sum(x[1] for x in same):.3f}")

for y in (2028, 2029):
    p = os.path.join(DATA, f"fa_class_{y}.json")
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    ms = d.get("members") or []
    pr = [m for m in ms if m.get("projGuar")]
    dp = sorted(m["dealPlus"] for m in pr if m.get("dealPlus") is not None)
    from collections import Counter
    print(f"\nfa_class_{y}: {len(ms)} members, {len(pr)} priced, "
          f"warSource=mlb_projections {sum(1 for m in ms if m.get('warSource')=='mlb_projections')}")
    if dp:
        print(f"  Deal+ p10/p50/p90 = {dp[len(dp)//10]}/{dp[len(dp)//2]}/{dp[9*len(dp)//10]}"
              f"   verdicts {dict(Counter(m.get('verdict') for m in pr))}")
    negp = sum(1 for m in ms if any(w < 0 for w in (m.get("warPath") or [])))
    negl = sum(1 for m in ms if any(w < 0 for w in (m.get("warPathP10") or [])))
    print(f"  members with a NEGATIVE season in served warPath {negp}, in warPathP10 {negl}")
