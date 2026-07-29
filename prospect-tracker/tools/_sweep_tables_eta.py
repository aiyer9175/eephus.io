"""Lane TABLES: _LEVEL_ETA re-derived from realized level-season -> MLB debut timing."""
import sys, pathlib, json, statistics as st, random
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import milb_history as mh
LV=["DSL","CPX","A","A+","AA","AAA"]
SHIP={"DSL":6.0,"CPX":5.0,"A":4.5,"A+":3.5,"AA":2.5,"AAA":1.5}
D=pathlib.Path(__file__).parent.parent/"data"
deb=json.loads((D/"debuts.json").read_text(encoding="utf-8"))
inact=json.loads((D/"inactive.json").read_text(encoding="utf-8"))
tgt={}
for r in deb:
    if r.get("mlbam_id") and r.get("debut_date"):
        tgt[int(r["mlbam_id"])]=int(r["debut_date"][:4])
never=set()
for r in inact:
    if r.get("mlbam_id") and not r.get("debut_date"): never.add(int(r["mlbam_id"]))
first={}   # (mlbam, level) -> earliest qualified season
for season in range(2014,2027):
    for group,minx,key in (("hitting",50,"pa"),("pitching",60,"bf")):
        idx=mh.player_index(season,group,fetch=False)
        for m,rs in idx.items():
            for row in rs:
                lv=row.get("level")
                if lv not in LV: continue
                try: e=float(row.get(key))
                except (TypeError,ValueError): continue
                if e<minx: continue
                k=(int(m),lv)
                if k not in first or season<first[k]: first[k]=season
def boot(v,B=2000,seed=8):
    rnd=random.Random(seed);n=len(v)
    s=sorted(sum(v[rnd.randrange(n)] for _ in range(n))/n for _ in range(B))
    return round(s[int(.025*B)],2),round(s[int(.975*B)],2)
print("_LEVEL_ETA (efv_ungraded, years-to-MLB by level) re-derived on 2014-2026 MiLB level-seasons")
print(f"{'lvl':>4} {'shipped':>8} {'n_debuted':>10} {'mean yrs':>9} {'CI95':>16} {'median':>7} {'n_never':>8} {'P(never MLB)':>13} {'E[yrs|censored@10]':>19}")
for lv in LV:
    ids=[(m,s) for (m,l),s in first.items() if l==lv]
    d=[tgt[m]-s for m,s in ids if m in tgt and tgt[m]>=s]
    nn=sum(1 for m,s in ids if m in never)
    tot=sum(1 for m,s in ids if m in tgt or m in never)
    if not d: continue
    p_never=nn/tot if tot else float('nan')
    # ETA that a surplus seam should use = E[years] over debutants, plus the never-MLB mass
    ecens=(1-p_never)*st.mean(d)+p_never*10.0
    print(f"{lv:>4} {SHIP[lv]:8.1f} {len(d):10d} {st.mean(d):9.2f} {str(boot(d)):>16} {st.median(d):7.1f} {nn:8d} {p_never:13.3f} {ecens:19.2f}")
