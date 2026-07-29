# SCRATCH: explore per-source FV structure vs consensus_fv_raw.
import json, sys
from pathlib import Path
import numpy as np
from scipy.stats import rankdata
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def spear(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float)
    ra,rb=rankdata(a),rankdata(b); ra=ra-ra.mean(); rb=rb-rb.mean()
    d=np.sqrt((ra**2).sum()*(rb**2).sum())
    return float((ra*rb).sum()/d) if d else float('nan')

for side,fn in (("hit","xfv_hitter_matrix.json"),("pit","xfv_pitcher_matrix.json")):
    rows=json.loads((ROOT/"data"/fn).read_text("utf-8"))
    print("="*70); print(side, len(rows))
    import collections
    pat=collections.Counter()
    for r in rows:
        f=r.get("fv_fangraphs"); m=r.get("fv_mlb_pipeline")
        pat[("FG" if f is not None else "-")+"/"+("MLB" if m is not None else "-")]+=1
    print("source pattern:", dict(pat))
    # both-graded rows: how close is consensus_fv_raw to the plain mean?
    both=[r for r in rows if r.get("fv_fangraphs") is not None and r.get("fv_mlb_pipeline") is not None]
    d=[r["consensus_fv_raw"]-(r["fv_fangraphs"]+r["fv_mlb_pipeline"])/2 for r in both]
    d=np.array(d)
    print(f"both n={len(both)} cons - plainmean: mean {d.mean():+.3f} sd {d.std():.3f} "
          f"|d|>0.5 frac {(np.abs(d)>0.5).mean():.3f} max|d| {np.abs(d).max():.2f}")
    # single source rows
    for key,other in (("fv_fangraphs","fv_mlb_pipeline"),("fv_mlb_pipeline","fv_fangraphs")):
        only=[r for r in rows if r.get(key) is not None and r.get(other) is None]
        dd=np.array([r["consensus_fv_raw"]-r[key] for r in only])
        print(f"  {key}-only n={len(only)} cons-src mean {dd.mean():+.3f} sd {dd.std():.3f}")
    none=[r for r in rows if r.get("fv_fangraphs") is None and r.get("fv_mlb_pipeline") is None]
    print("  no per-source FV rows:", len(none))
    # per-source predictive power on DEBUTED rows
    deb=[r for r in rows if r["kind"]=="debuted" and r.get("target_censored") is not None]
    print(f"debuted n={len(deb)}")
    for key in ("consensus_fv_raw","fv_fangraphs","fv_mlb_pipeline"):
        sub=[r for r in deb if r.get(key) is not None]
        print(f"  {key:22s} n={len(sub):4d} rho(WAR)={spear([r[key] for r in sub],[r['target_censored'] for r in sub]):.4f}")
    # common set
    com=[r for r in deb if r.get("fv_fangraphs") is not None and r.get("fv_mlb_pipeline") is not None]
    y=[r["target_censored"] for r in com]
    print(f"  COMMON n={len(com)}")
    for key in ("consensus_fv_raw","fv_fangraphs","fv_mlb_pipeline"):
        print(f"    {key:22s} rho={spear([r[key] for r in com],y):.4f}")
    fg=np.array([r["fv_fangraphs"] for r in com]); mp=np.array([r["fv_mlb_pipeline"] for r in com])
    print(f"    corr(FG,MLB) pearson={np.corrcoef(fg,mp)[0,1]:.4f} spear={spear(fg,mp):.4f}")
    print(f"    FG mean {fg.mean():.2f} sd {fg.std():.2f} | MLB mean {mp.mean():.2f} sd {mp.std():.2f}")
    # decision year distribution
    dy=collections.Counter(int(str(r.get('asof_date') or '')[:4] or 0) for r in deb)
    print("  asof-year:", dict(sorted(dy.items())))
