"""Lane: prospect. (e) NEW DATA into ETA.

data/pipeline_vintages.json carries a POINT-IN-TIME published `eta` (a debut
year) for every one of the ~1,197 MLB Pipeline Top-100 entries, 2015-2026, at
100% mlbam coverage -- far denser than the sparse grade block that failed for
eFV. Three questions, forward-chained by vintage over the 2018-2023 window the
eta backtest already scores:

  E1  how accurate is the PUBLISHED Pipeline ETA on its own, on rows our model
      also predicts (identical rows, same actual)?
  E2  does BLENDING it with our champion beat the champion?
  E3  does a fitted per-vintage shave learned forward-chained on prior vintages
      transfer?

Controls: paired bootstrap over players (refit the blend weight each draw), a
row-permuted zero-information twin of the pipeline column, a permutation null
band, and each vintage reported separately (6 independent splits).
"""
import json, statistics, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
import eta_backtest as eb

rows, acct = eb.build_cohort()
listings, cs, bio, debut_year, ident = eb._load_inputs()
mlbam = {k: int(v["mlbam"]) for k, v in ident.items() if v.get("mlbam")}
print("cohort rows:", len(rows), " with mlbam:", sum(1 for r in rows if r['player_key'] in mlbam))

pv = json.loads((D / "pipeline_vintages.json").read_text(encoding="utf-8"))["vintages"]
pipe = {}
for y, recs in pv.items():
    for r in recs:
        if r.get("mlbam") and r.get("eta"):
            try:
                pipe[(int(r["mlbam"]), int(y))] = int(str(r["eta"])[:4])
            except (TypeError, ValueError):
                pass
print("pipeline (mlbam,year)->eta rows:", len(pipe))

J = []
for r in rows:
    if r["outcome"] != "debuted" or r["actual"] is None:
        continue
    m = mlbam.get(r["player_key"])
    if m is None:
        continue
    p = pipe.get((m, r["vintage"]))
    if p is None:
        continue
    J.append(dict(k=r["player_key"], vy=r["vintage"], actual=r["actual"],
                  ours=r["pred"], pipe=p, level=r["level"], fv=r["fv"]))
print("joined debuted rows (our model AND a published Pipeline ETA):", len(J))
print("by vintage:", {v: sum(1 for j in J if j['vy'] == v) for v in sorted({j['vy'] for j in J})})
if len(J) < 60:
    print("INSUFFICIENT OVERLAP - reporting UNAVAILABLE")
    sys.exit(0)

def sc(pred, act):
    e = [p - a for p, a in zip(pred, act)]
    return (float(np.mean(np.abs(e))), float(np.mean(e)),
            float(np.mean([abs(v) <= 1 for v in e])), float(np.mean([v == 0 for v in e])))

act = [j["actual"] for j in J]
ours = [j["ours"] for j in J]
pipep = [j["pipe"] for j in J]
print("\n--- E1 head to head on identical rows (n=%d) ---" % len(J))
for nm, p in (("our champion heuristic", ours), ("MLB Pipeline published ETA", pipep)):
    mae, bias, w1, ex = sc(p, act)
    print(f"  {nm:28s} MAE={mae:.3f} bias={bias:+.3f} within1y={w1:.3f} exact={ex:.3f}")

print("\n--- E2 blend: round(w*pipe + (1-w)*ours), w fitted FORWARD-CHAINED ---")
WS = [round(x, 2) for x in np.arange(0, 1.01, 0.05)]
def blend(w, o, p):
    return [int(round(w * pp + (1 - w) * oo)) for oo, pp in zip(o, p)]
vys = sorted({j["vy"] for j in J})
fc_pred, fc_act, fc_base, ws_used = [], [], [], {}
for vy in vys:
    tr = [j for j in J if j["vy"] < vy]
    te = [j for j in J if j["vy"] == vy]
    if len(tr) < 40 or not te:
        continue
    best = min(WS, key=lambda w: sc(blend(w, [j["ours"] for j in tr], [j["pipe"] for j in tr]),
                                    [j["actual"] for j in tr])[0])
    ws_used[vy] = best
    fc_pred += blend(best, [j["ours"] for j in te], [j["pipe"] for j in te])
    fc_base += [j["ours"] for j in te]
    fc_act += [j["actual"] for j in te]
print("  weights picked per vintage:", ws_used)
if fc_pred:
    mb, bb, wb, eb_ = sc(fc_base, fc_act)
    mm, bm, wm, em = sc(fc_pred, fc_act)
    print(f"  champion  n={len(fc_act)} MAE={mb:.3f} within1y={wb:.3f}")
    print(f"  blended   n={len(fc_act)} MAE={mm:.3f} within1y={wm:.3f}   dMAE={mm-mb:+.4f}")

print("\n--- PER-VINTAGE (independent time splits) ---")
for vy in vys:
    sub = [j for j in J if j["vy"] == vy]
    if len(sub) < 15:
        continue
    a = [j["actual"] for j in sub]
    mo = sc([j["ours"] for j in sub], a); mp = sc([j["pipe"] for j in sub], a)
    print(f"  {vy} n={len(sub):4d}  ours MAE={mo[0]:.3f} w1={mo[2]:.3f} | "
          f"pipeline MAE={mp[0]:.3f} w1={mp[2]:.3f} | dMAE={mp[0]-mo[0]:+.3f}")

print("\n--- PAIRED BOOTSTRAP (B=4000) on dMAE (pipeline - ours) ---")
rng = np.random.default_rng(20260725)
n = len(J)
o = np.array(ours, float); p = np.array(pipep, float); a = np.array(act, float)
d = np.empty(4000)
for i in range(4000):
    ix = rng.integers(0, n, n)
    d[i] = np.mean(np.abs(p[ix]-a[ix])) - np.mean(np.abs(o[ix]-a[ix]))
lo, hi = np.percentile(d, [2.5, 97.5])
print(f"  obs={np.mean(np.abs(p-a))-np.mean(np.abs(o-a)):+.4f} mean={d.mean():+.4f} sd={d.std():.4f} "
      f"CI95=[{lo:+.4f},{hi:+.4f}]  MDE95={1.96*d.std():.4f}")

print("\n--- ZERO-INFORMATION CONTROL (row-permuted pipeline column) ---")
pp = p.copy(); rng.shuffle(pp)
print(f"  permuted pipeline MAE={np.mean(np.abs(pp-a)):.3f}   real pipeline MAE={np.mean(np.abs(p-a)):.3f}"
      f"   ours MAE={np.mean(np.abs(o-a)):.3f}")

print("\n--- PERMUTATION NULL BAND for dMAE (B=2000) ---")
nl = np.array([np.mean(np.abs(p[rng.permutation(n)]-a)) - np.mean(np.abs(o-a))
               for _ in range(2000)])
print(f"  null mean={nl.mean():+.4f} CI95=[{np.percentile(nl,2.5):+.4f},{np.percentile(nl,97.5):+.4f}]")
