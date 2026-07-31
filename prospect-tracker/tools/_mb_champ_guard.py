# Scratch: apply the mean-blend artifact's OWN ship rule - "MAE must stay
# below the prior champion (marcel_decay_v2) at every validatable horizon" -
# on the same 4 forward-chained bases and the same rows the re-measurement used.
from __future__ import annotations
import pickle, sys, os
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fa_market as fm
import fa_projection as fp
import proj_ml

SCR = Path(os.environ["PROJ_LAB_SCRATCH"])
BASES = [2019, 2020, 2021, 2022]
corpus = pickle.load(open(SCR / "fa_corpus_SHIPPED.pkl", "rb"))
rows = []
for B in BASES:
    rows.extend(pickle.load(open(SCR / f"mblab_rows_base{B}.pkl", "rb")))
league = corpus["league"]

by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
war_actual = {}
for side in ("hit", "pit"):
    for r in corpus[side]:
        if r.get("mlbam"):
            by_player[side][r["mlbam"]][r["season"]] = r
            if r.get("war") is not None:
                k = (r["mlbam"], r["season"])
                war_actual[k] = war_actual.get(k, 0.0) + r["war"]

champ = {}
for B in BASES:
    curves, war_map = fp.fitted_models(corpus, B - 1, use_cache=False)
    for side in ("hit", "pit"):
        for mlbam, seasons in by_player[side].items():
            hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
            if not hist:
                continue
            ar = next((h for h in hist if h.get("age")), None)
            if ar is None:
                continue
            age = ar["age"] + (B - ar["season"])
            proj = fp.project_player(hist, side, B, curves, league, age)
            if proj is None:
                continue
            w1 = fp.war_from_projection(proj, side, war_map, league, B)
            role = fp.profile_role(hist, side, proj["role"], league)
            path = fm._decay_path(w1, proj["pt_proj"], side, role, age, curves)
            for h in range(1, 6):
                champ[(B, side, mlbam, h)] = path[h - 1]

lam = {"1": 1.0, "2": 1.0, "3": 1.0, "4": 0.5, "5": 0.5}
slam = {"5": 1.0}
agg = defaultdict(lambda: {"n": 0, "c": 0.0, "off": 0.0, "on": 0.0,
                           "cb": 0.0, "offb": 0.0, "onb": 0.0})
miss = 0
for r in rows:
    key = (r["B"], r["side"], r["m"], r["h"])
    if key not in champ:
        miss += 1
        continue
    q10, q25, q50, q75, q90 = r["q"]
    off = q50
    if r["star"] and slam.get(str(r["h"]), 0) > 0:
        off = off + slam[str(r["h"])] * (proj_ml._implied_mean(q10, q25, off, q75, q90) - off)
    on = q50
    l = lam.get(str(r["h"]), 0.0)
    gap = proj_ml._implied_mean(q10, q25, q50, q75, q90) - q50
    if l > 0 and l * gap > 0:
        on = q50 + l * gap
    if r["star"] and slam.get(str(r["h"]), 0) > 0:
        on = on + slam[str(r["h"])] * (proj_ml._implied_mean(q10, q25, on, q75, q90) - on)
    a = r["act"]; c = champ[key]
    s = agg[r["h"]]
    s["n"] += 1
    s["c"] += abs(c - a); s["off"] += abs(off - a); s["on"] += abs(on - a)
    s["cb"] += c - a; s["offb"] += off - a; s["onb"] += on - a

print(f"rows {len(rows)}  matched {len(rows)-miss}  missing champ {miss}")
print(f"{'h':>2} {'n':>6} {'champMAE':>9} {'mlOffMAE':>9} {'mlOnMAE':>9} | "
      f"{'champBias':>10} {'offBias':>9} {'onBias':>9} | guard")
for h in sorted(agg):
    s = agg[h]; n = s["n"]
    cm, om, nm = s["c"]/n, s["off"]/n, s["on"]/n
    cb, ob, nb = s["cb"]/n, s["offb"]/n, s["onb"]/n
    guard = "PASS" if nm < cm else "FAIL"
    print(f"{h:>2} {n:>6} {cm:>9.4f} {om:>9.4f} {nm:>9.4f} | "
          f"{cb:>10.4f} {ob:>9.4f} {nb:>9.4f} | {guard}")
