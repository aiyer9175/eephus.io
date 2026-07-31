"""SCRATCH round 2: is the FA adverse-selection gap concentrated in fringe
non-tenders, or does it survive among the contracts the module actually prices?
Also: conditional-on-played, and multi-horizon (does the gap persist into year 2?).
"""
from __future__ import annotations
import json, math, sqlite3, sys, pickle, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fa_projection as fp

corpus = pickle.load(open(ROOT / ".cache" / "fa_corpus.pkl", "rb"))
league = corpus["league"]
hist = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
for side in ("hit", "pit"):
    for r in corpus[side]:
        hist[side][r["mlbam"]][r["season"]] = r

db = sqlite3.connect(ROOT / "prospects.db")
sign = {}          # (year, mid) -> signing payload
for pk, cy, pj in db.execute("select player_key, class_year, payload_json from fa_signings"):
    p = json.loads(pj)
    if p.get("mlbam_id"):
        sign[(int(cy), int(p["mlbam_id"]))] = p

MINPA = {"hit": 250, "pit": 150}
EXPO = {"hit": "pa", "pit": "bf"}
rows = []
for W in range(2015, 2025):
    curves, war_map = fp.fitted_models(corpus, max_season=W - 1)
    for side in ("hit", "pit"):
        for mid, bys in hist[side].items():
            prev = bys.get(W - 1)
            if not prev or (prev.get(EXPO[side]) or 0) < MINPA[side]:
                continue
            age = prev.get("age")
            if age is None or not (27 <= age <= 40):
                continue
            h = [bys[s] for s in (W - 1, W - 2, W - 3) if s in bys]
            proj = fp.project_player(h, side, W, curves, league, age + 1, role=prev.get("role"))
            if not proj:
                continue
            pw = fp.war_from_projection(proj, side, war_map, league, W)
            s = sign.get((W, mid))
            cur = bys.get(W)
            # 2-year realized (year W and W+1), replacement=0 when absent
            r2 = sum((bys.get(y, {}).get("war") or 0.0) for y in (W, W + 1))
            rows.append({
                "W": W, "side": side, "age": age + 1, "D": 1 if s else 0,
                "proj_war": pw,
                "real_war": (cur or {}).get("war") if cur else None,
                "war0": (cur.get("war") if cur else 0.0) or 0.0,
                "war2": r2,
                "guar": (s or {}).get("guarantee_usd") or 0,
                "yrs": (s or {}).get("years") or 0,
                "mlb_deal": bool((s or {}).get("mlb_deal")),
                "moved": bool(s and s.get("from_team") != s.get("to_team")),
                "qo": bool((s or {}).get("qo")),
            })

def stat(a, b, key, proj="proj_war", label=""):
    if len(a) < 15 or len(b) < 15:
        print(f"{label:34s} n too small ({len(a)}/{len(b)})"); return
    ra = [r[key] - r[proj] for r in a]
    rb = [r[key] - r[proj] for r in b]
    se = math.sqrt(statistics.pvariance(ra)/len(ra) + statistics.pvariance(rb)/len(rb))
    d = statistics.mean(ra) - statistics.mean(rb)
    print(f"{label:34s} nD1={len(a):5d} nD0={len(b):5d} resid {statistics.mean(ra):+.3f} vs "
          f"{statistics.mean(rb):+.3f}  DIFF {d:+.3f} +- {1.96*se:.3f}  t={d/se:+.2f}")

D0 = [r for r in rows if r["D"] == 0]
print("== year-1 WAR residual (absent=0) ==")
stat([r for r in rows if r["D"] == 1], D0, "war0", label="all entrants")
for lo, hi, nm in ((1, 5e6, "guar < $5M / MiLB"), (5e6, 25e6, "$5-25M"),
                   (25e6, 1e9, "$25M+")):
    stat([r for r in rows if r["D"] == 1 and lo <= r["guar"] < hi], D0, "war0",
         label=f"  entrants {nm}")
stat([r for r in rows if r["D"] == 1 and r["guar"] == 0], D0, "war0", label="  entrants, no guar on file")
stat([r for r in rows if r["D"] == 1 and r["qo"]], D0, "war0", label="  QO recipients")
print()
print("== conditional on PLAYING in W (drops the absent) ==")
P = [r for r in rows if r["real_war"] is not None]
stat([r for r in P if r["D"] == 1], [r for r in P if r["D"] == 0], "real_war", label="all, played only")
for side in ("hit", "pit"):
    Ps = [r for r in P if r["side"] == side]
    stat([r for r in Ps if r["D"] == 1], [r for r in Ps if r["D"] == 0], "real_war",
         label=f"  played only, {side}")
print()
print("== 2-year realized vs 1-year projection*2 (persistence) ==")
for r in rows:
    r["proj2"] = r["proj_war"] * 2
stat([r for r in rows if r["D"] == 1], D0, "war2", proj="proj2", label="2yr, all entrants")
stat([r for r in rows if r["D"] == 1 and r["guar"] >= 25e6], D0, "war2", proj="proj2",
     label="  2yr, $25M+ signings")
print()
print("== among SIGNED only: does gap vary with guarantee? (dose response) ==")
S = [r for r in rows if r["D"] == 1 and r["guar"] > 0]
S.sort(key=lambda r: r["guar"])
q = len(S)//4
for i in range(4):
    ch = S[i*q:(i+1)*q] if i < 3 else S[3*q:]
    rr = [r["war0"] - r["proj_war"] for r in ch]
    print(f"  guar quartile {i+1}: n={len(ch):4d} median ${statistics.median([r['guar'] for r in ch])/1e6:6.1f}M "
          f"resid {statistics.mean(rr):+.3f} +- {1.96*statistics.stdev(rr)/math.sqrt(len(rr)):.3f} "
          f"projWAR {statistics.mean([r['proj_war'] for r in ch]):.2f}")
