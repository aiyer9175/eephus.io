"""SCRATCH: does the PRICE residual (what the market paid above/below what our
projection justifies) carry information about future WAR?

 - If beta > 0: the market has private information our projection misses ->
   price should be an INPUT to the WAR projection (revealed-preference feature).
 - If beta ~ 0 or < 0: prices are noise / winner's curse -> the surplus column
   is the product and we should not chase the market.
Also splits by QO (an incumbent-team revealed signal) and by moved/stayed.
"""
from __future__ import annotations
import json, math, pickle, sqlite3, statistics, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import fa_projection as fp

corpus = pickle.load(open(ROOT / ".cache" / "fa_corpus.pkl", "rb"))
league = corpus["league"]
hist = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
for side in ("hit", "pit"):
    for r in corpus[side]:
        hist[side][r["mlbam"]][r["season"]] = r

db = sqlite3.connect(ROOT / "prospects.db")
recs = []
fits_cache = {}
for pk, cy, pj in db.execute("select player_key, class_year, payload_json from fa_signings"):
    p = json.loads(pj); W = int(cy); mid = p.get("mlbam_id")
    g = p.get("guarantee_usd"); yrs = p.get("years")
    if not mid or not g or g <= 0 or not p.get("mlb_deal"):
        continue
    if W not in fits_cache:
        fits_cache[W] = fp.fitted_models(corpus, max_season=W - 1)
    curves, war_map = fits_cache[W]
    for side in ("hit", "pit"):
        bys = hist[side].get(int(mid))
        if not bys: continue
        prev = bys.get(W - 1)
        expo = "pa" if side == "hit" else "bf"
        if not prev or (prev.get(expo) or 0) < 200:
            continue
        age = prev.get("age")
        if age is None: continue
        h = [bys[s] for s in (W-1, W-2, W-3) if s in bys]
        proj = fp.project_player(h, side, W, curves, league, age + 1, role=prev.get("role"))
        if not proj: continue
        pw = fp.war_from_projection(proj, side, war_map, league, W)
        war3 = sum((bys.get(y, {}).get("war") or 0.0) for y in (W, W+1, W+2))
        recs.append({"W": W, "side": side, "age": age + 1, "proj": pw,
                     "war1": (bys.get(W, {}).get("war") or 0.0),
                     "war3": war3, "guar": g, "yrs": yrs or 1,
                     "aav": g / max(1, yrs or 1), "qo": bool(p.get("qo")),
                     "moved": p.get("from_team") != p.get("to_team")})
print("n signings with usable platform season:", len(recs))

years = sorted({r["W"] for r in recs})
def design(rs):
    X = []
    for r in rs:
        X.append([1.0, r["proj"], max(0.0, r["proj"])**2, r["age"], 1.0 if r["side"]=="pit" else 0.0]
                 + [1.0 if r["W"] == y else 0.0 for y in years[1:]])
    return np.array(X)

# stage 1: price model on projection + age + side + winter FE
y = np.array([math.log(r["aav"]) for r in recs])
X = design(recs)
b, *_ = np.linalg.lstsq(X, y, rcond=None)
pres = y - X @ b
for r, e in zip(recs, pres):
    r["price_resid"] = float(e)
print("stage-1 log(AAV) R2 = %.3f, resid sd = %.3f" % (1 - pres.var()/y.var(), pres.std()))

def stage2(rs, label, ykey="war1"):
    if len(rs) < 40:
        print(f"{label:26s} n={len(rs)} too small"); return
    yy = np.array([r[ykey] - (r["proj"] if ykey == "war1" else 3*r["proj"]) for r in rs])
    XX = np.column_stack([design(rs), np.array([r["price_resid"] for r in rs])])
    bb, *_ = np.linalg.lstsq(XX, yy, rcond=None)
    rr = yy - XX @ bb
    s2 = float(rr @ rr)/(len(yy)-XX.shape[1])
    se = np.sqrt(np.diag(s2*np.linalg.pinv(XX.T @ XX)))[-1]
    print(f"{label:26s} n={len(rs):4d}  beta(price_resid -> {ykey} resid) = {bb[-1]:+.3f} "
          f"se {se:.3f}  t {bb[-1]/se:+.2f}")

print()
stage2(recs, "all signings", "war1")
stage2(recs, "all signings", "war3")
stage2([r for r in recs if r["side"]=="hit"], "hitters", "war1")
stage2([r for r in recs if r["side"]=="pit"], "pitchers", "war1")
stage2([r for r in recs if r["guar"] >= 20e6], "guar >= $20M", "war1")
stage2([r for r in recs if r["moved"]], "changed teams", "war1")
stage2([r for r in recs if not r["moved"]], "re-signed w/ incumbent", "war1")

print("\nQO as an incumbent-team signal (mean WAR residual):")
for flag in (True, False):
    ch = [r for r in recs if r["qo"] == flag]
    rr = [r["war1"] - r["proj"] for r in ch]
    if len(ch) > 20:
        print(f"  qo={flag}: n={len(ch):4d} resid {statistics.mean(rr):+.3f} "
              f"+- {1.96*statistics.stdev(rr)/math.sqrt(len(rr)):.3f} projWAR "
              f"{statistics.mean([r['proj'] for r in ch]):.2f}")
print("\nre-signed vs moved (mean WAR residual):")
for flag in (False, True):
    ch = [r for r in recs if r["moved"] == flag]
    rr = [r["war1"] - r["proj"] for r in ch]
    print(f"  moved={flag}: n={len(ch):4d} resid {statistics.mean(rr):+.3f} "
          f"+- {1.96*statistics.stdev(rr)/math.sqrt(len(rr)):.3f} projWAR "
          f"{statistics.mean([r['proj'] for r in ch]):.2f}")
