"""Lane: prospect. (e) DECISIVE leak test on the Pipeline vintage ETA.

The first probe found 250 players listed on >= 2 vintage boards whose published
eta is IDENTICAL on every board and ZERO whose eta ever moves. A genuine
point-in-time forecast must move as a player advances. Two decisive tests:

  L1  restrict to players with >= 2 boards each carrying a NON-NULL eta and count
      how many change.
  L2  horizon decay. A real forecast degrades with horizon: MAE must rise with
      (debut year - vintage year). A value frozen at the player's LAST board
      appearance does not degrade, because the long-horizon rows are carrying a
      short-horizon forecast.
"""
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
import eta_backtest as eb

pv = json.loads((D / "pipeline_vintages.json").read_text(encoding="utf-8"))["vintages"]
byp = defaultdict(dict)
for y, recs in pv.items():
    for r in recs:
        if r.get("mlbam"):
            byp[int(r["mlbam"])][int(y)] = r

print("--- L1 do published etas EVER move for a player across vintages? ---")
moved = same = 0
examples = []
for m, v in byp.items():
    es = [(y, int(str(r["eta"])[:4])) for y, r in sorted(v.items())
          if r.get("eta") not in (None, "None", "")]
    if len(es) < 2:
        continue
    if len({e for _, e in es}) > 1:
        moved += 1
        if len(examples) < 8:
            examples.append((m, es))
    else:
        same += 1
        if len(examples) < 8:
            examples.append((m, es))
print(f"  players with >=2 NON-NULL etas: {moved+same}   moved: {moved}   frozen: {same}")
for m, es in examples:
    print("   mlbam", m, es)

print("\n--- L2 horizon decay (does the published eta degrade with forecast horizon?) ---")
rows, _ = eb.build_cohort()
listings, cs, bio, debut_year, ident = eb._load_inputs()
mlbam = {k: int(v["mlbam"]) for k, v in ident.items() if v.get("mlbam")}
pipe = {}
for y, recs in pv.items():
    for r in recs:
        if r.get("mlbam") and r.get("eta") not in (None, "None", ""):
            pipe[(int(r["mlbam"]), int(y))] = int(str(r["eta"])[:4])
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
    last_board = max((y for y in byp[m] if y <= r["actual"]), default=None)
    J.append(dict(vy=r["vintage"], actual=r["actual"], ours=r["pred"], pipe=p,
                  h=r["actual"] - r["vintage"], last=last_board, m=m))
print("  joined n =", len(J))
for h in sorted({j["h"] for j in J}):
    s = [j for j in J if j["h"] == h]
    if len(s) < 12:
        continue
    mo = np.mean([abs(j["ours"] - j["actual"]) for j in s])
    mp = np.mean([abs(j["pipe"] - j["actual"]) for j in s])
    nlast = sum(1 for j in s if j["last"] is not None and j["last"] > j["vy"])
    print(f"   horizon={h}yr n={len(s):4d}  ours MAE={mo:.3f}  pipeline MAE={mp:.3f}  "
          f"rows whose player has a LATER board: {nlast} ({100*nlast/len(s):.0f}%)")

print("\n--- L2b split: vintage IS the player's last pre-debut board vs an EARLIER one ---")
for tag, sel in (("vintage == last pre-debut board", lambda j: j["last"] == j["vy"]),
                 ("vintage < last pre-debut board (a LATER board exists)",
                  lambda j: j["last"] is not None and j["last"] > j["vy"])):
    s = [j for j in J if sel(j)]
    if not s:
        continue
    mo = np.mean([abs(j["ours"] - j["actual"]) for j in s])
    mp = np.mean([abs(j["pipe"] - j["actual"]) for j in s])
    hh = np.mean([j["h"] for j in s])
    print(f"   {tag:52s} n={len(s):4d} meanHorizon={hh:.2f}  ours={mo:.3f}  pipeline={mp:.3f}  d={mp-mo:+.3f}")
