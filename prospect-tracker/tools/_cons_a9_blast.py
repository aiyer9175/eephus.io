# A9 -- BLAST RADIUS of the grade-normalization continuous-offset fix on the
# SERVED board. The fix is already live (daily run 2026-07-25 10:56-11:06 UTC);
# this measures what it moved, by reconstructing the counterfactual raw-scale
# consensus from the same exported per-source published grades.
from __future__ import annotations

import collections
import json
import math
from pathlib import Path

import numpy as np

from _cons_data import DATA, OUT

SHIPPED_W = {"fangraphs": 0.9363, "mlb_pipeline": 1.0637}
SYNTH = {"performance_ingest", "draft_signing"}
PITCH = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP", "CL", "P"}


def is_pitcher(pos):
    if not pos:
        return False
    return any(tok in PITCH for tok in str(pos).upper().split("/"))


def load_board():
    ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))
    return ts["players"]


players = load_board()
print(f"active board players: {len(players)}")

# --- collect the latest point per player -----------------------------------
recs = []
for p in players:
    pts = [q for q in (p.get("points") or []) if q.get("snapshot_date")]
    if not pts:
        continue
    pt = max(pts, key=lambda q: q["snapshot_date"])
    per = pt.get("per_source") or {}
    srcs = {}
    for s, v in per.items():
        fv = v.get("fv_published")
        if fv is None:
            continue
        srcs[s] = {"fv": float(fv), "yr": int(str(v.get("snapshot_date") or
                                                 pt["snapshot_date"])[:4]),
                   "dropped": bool(v.get("dropped_off"))}
    if not srcs:
        continue
    recs.append({"key": p["player_key"], "name": p.get("player_name"),
                 "role": "pitcher" if is_pitcher(p.get("position")) else "hitter",
                 "srcs": srcs, "pre": pt.get("consensus_fv_pre_shrinkage"),
                 "cons": pt.get("consensus_fv_raw"),
                 "disp": pt.get("consensus_fv"),
                 "fv_close": p.get("fv_close"),
                 "rank": p.get("overall_rank")})
print(f"with >=1 published FV on the latest point: {len(recs)}")

# --- derive the LIVE per (source, role, year) offset from single-source rows --
off = {}
cnt = collections.Counter()
for r in recs:
    if len(r["srcs"]) != 1 or r["pre"] is None:
        continue
    s, v = next(iter(r["srcs"].items()))
    if v["dropped"]:
        continue
    k = (s, r["role"], v["yr"])
    d = v["fv"] - r["pre"]
    off.setdefault(k, []).append(d)
    cnt[k] += 1
OFF = {k: float(np.median(v)) for k, v in off.items() if len(v) >= 3}
print("\n=== A9a. LIVE per-(source, role, year) offset, solved from single-source "
      "served values (FV points SUBTRACTED from that outlet's grade) ===")
print(f"{'source':>22} {'role':>8} {'yr':>5} {'n':>5} {'offset':>8} {'spread':>8}")
for k in sorted(OFF, key=lambda k: (k[0], k[1], k[2])):
    v = np.array(off[k])
    print(f"{k[0]:>22} {k[1]:>8} {k[2]:>5} {len(v):>5} {OFF[k]:>8.3f} "
          f"{v.max()-v.min():>8.3f}")

DEFAULT_OFF = {}
for (s, role, yr), v in OFF.items():
    DEFAULT_OFF.setdefault((s, role), []).append(v)
DEFAULT_OFF = {k: float(np.median(v)) for k, v in DEFAULT_OFF.items()}

# Outlets that never appear ALONE (ESPN / Just Baseball / TJStats / BA) cannot be
# read off single-source rows. Solve them from multi-source rows where exactly one
# offset is still unknown; iterate to a fixed point.
for _ in range(4):
    solved = collections.defaultdict(list)
    for r in recs:
        if r["pre"] is None or any(v["dropped"] for v in r["srcs"].values()):
            continue
        unknown = [(s, v) for s, v in r["srcs"].items()
                   if s != "fangraphs" and s not in SYNTH
                   and (s, r["role"], v["yr"]) not in OFF]
        if len(unknown) != 1:
            continue
        su, vu = unknown[0]
        num = den = 0.0
        for s, v in r["srcs"].items():
            w = SHIPPED_W.get(s, 1.0)
            den += w
            if s == su:
                continue
            num += w * (v["fv"] - (0.0 if (s == "fangraphs" or s in SYNTH)
                                   else OFF[(s, r["role"], v["yr"])]))
        wu = SHIPPED_W.get(su, 1.0)
        # pre*den = num + wu*(fv_u - off_u)
        offu = vu["fv"] - (r["pre"] * den - num) / wu
        solved[(su, r["role"], vu["yr"])].append(offu)
    added = 0
    for k, v in solved.items():
        if len(v) >= 3 and np.std(v) < 0.5:
            OFF[k] = float(np.median(v))
            added += 1
    if not added:
        break
print("\n  offsets solved from multi-source rows (outlets that never appear alone):")
for k in sorted(OFF, key=lambda k: (k[0], k[1], k[2])):
    if k[0] in ("fangraphs", "mlb_pipeline") or k[0] in SYNTH:
        continue
    print(f"    {k[0]:>34} {k[1]:>8} {k[2]} -> {OFF[k]:+.3f}")
DEFAULT_OFF = {}
for (s, role, yr), v in OFF.items():
    DEFAULT_OFF.setdefault((s, role), []).append(v)
DEFAULT_OFF = {k: float(np.median(v)) for k, v in DEFAULT_OFF.items()}


def offset_for(s, role, yr):
    if s == "fangraphs" or s in SYNTH:
        return 0.0
    return OFF.get((s, role, yr), DEFAULT_OFF.get((s, role), 0.0))


# --- reconstruct served pre (validation) and the raw-scale counterfactual ----
def combine(r, use_offset):
    num = den = 0.0
    for s, v in r["srcs"].items():
        fv = v["fv"] - (offset_for(s, r["role"], v["yr"]) if use_offset else 0.0)
        if v["dropped"]:
            fv = (fv + 30.0) / 2.0
        w = SHIPPED_W.get(s, 1.0)
        num += w * fv
        den += w
    return num / den if den else None


ok = bad = 0
errs = []
for r in recs:
    if r["pre"] is None:
        continue
    rec = combine(r, True)
    if rec is None:
        continue
    e = abs(rec - r["pre"])
    errs.append(e)
    if e <= 0.05:
        ok += 1
    else:
        bad += 1
errs = np.array(errs)
print(f"\n=== A9b. reconstruction check vs served consensus_fv_pre_shrinkage ===")
print(f"  within 0.05 FV: {ok}/{ok+bad} ({ok/(ok+bad):.1%})   "
      f"median |err| {np.median(errs):.4f}  p95 {np.percentile(errs,95):.3f}")

# --- blast radius ------------------------------------------------------------
def snap(x):
    return float(math.ceil(max(20.0, min(80.0, x))))


rows = []
for r in recs:
    if r["pre"] is None or r["cons"] is None:
        continue
    new_pre = combine(r, True)
    old_pre = combine(r, False)
    if new_pre is None or old_pre is None:
        continue
    pulled = abs(r["cons"] - r["pre"]) > 1e-9
    def fin(pre):
        return (2 / 3) * pre + (1 / 3) * 35.0 if pulled else pre
    rows.append({"key": r["key"], "name": r["name"], "role": r["role"],
                 "n_src": len(r["srcs"]), "srcs": sorted(r["srcs"]),
                 "old": fin(old_pre), "new": fin(new_pre),
                 "old_disp": snap(fin(old_pre)), "new_disp": snap(fin(new_pre)),
                 "rank": r["rank"]})
d = np.array([x["new"] - x["old"] for x in rows])
dd = np.array([x["new_disp"] - x["old_disp"] for x in rows])
print(f"\n=== A9c. BLAST RADIUS on the served board (n={len(rows)} graded players) ===")
print(f"  raw consensus FV : mean {d.mean():+.3f}  median {np.median(d):+.3f}  "
      f"min {d.min():+.2f}  max {d.max():+.2f}")
print(f"  moved at all (|d| > 0.01) : {int((np.abs(d)>0.01).sum())} "
      f"({(np.abs(d)>0.01).mean():.1%})")
print(f"  DISPLAYED (ceil) grade moved : {int((dd!=0).sum())} ({(dd!=0).mean():.1%})")
print(f"  displayed moved DOWN {int((dd<0).sum())}   UP {int((dd>0).sum())}")
print(f"  displayed shift distribution: " +
      "  ".join(f"{k:+d}FV:{v}" for k, v in sorted(collections.Counter(dd.astype(int)).items())))
print("\n  by source set (mean raw-FV move):")
bys = collections.defaultdict(list)
for x, dv in zip(rows, d):
    bys["+".join(x["srcs"])].append(dv)
for k, v in sorted(bys.items(), key=lambda kv: -len(kv[1]))[:12]:
    print(f"    {k:>52} n={len(v):>5}  mean {np.mean(v):+.3f}")
print("\n  by displayed-grade tier (pre-fix):")
for lo, hi, lbl in ((60, 99, "60+"), (55, 60, "55-59"), (50, 55, "50-54"),
                    (45, 50, "45-49"), (40, 45, "40-44"), (0, 40, "<40")):
    sub = [x for x in rows if lo <= x["old_disp"] < hi]
    if not sub:
        continue
    v = np.array([x["new"] - x["old"] for x in sub])
    print(f"    {lbl:>6} n={len(sub):>5}  mean {v.mean():+.3f}  "
          f"displayed moved {sum(1 for x in sub if x['new_disp']!=x['old_disp'])}")

big = sorted(rows, key=lambda x: x["new"] - x["old"])[:10]
print("\n  10 largest DOWNWARD moves:")
for x in big:
    print(f"    {x['name']:>28}  {x['old']:.2f} -> {x['new']:.2f}  "
          f"({x['old_disp']:.0f} -> {x['new_disp']:.0f})  srcs={'+'.join(x['srcs'])}")
big = sorted(rows, key=lambda x: -(x["new"] - x["old"]))[:5]
print("  5 largest UPWARD moves:")
for x in big:
    print(f"    {x['name']:>28}  {x['old']:.2f} -> {x['new']:.2f}  "
          f"({x['old_disp']:.0f} -> {x['new_disp']:.0f})  srcs={'+'.join(x['srcs'])}")

# rank churn on the top of the board
scored = [x for x in rows if x["rank"]]
old_order = sorted(scored, key=lambda x: -x["old"])
new_order = sorted(scored, key=lambda x: -x["new"])
oldpos = {x["key"]: i for i, x in enumerate(old_order)}
newpos = {x["key"]: i for i, x in enumerate(new_order)}
moves = np.array([abs(newpos[k] - oldpos[k]) for k in oldpos])
top100_old = {x["key"] for x in old_order[:100]}
top100_new = {x["key"] for x in new_order[:100]}
print(f"\n  board rank churn (n={len(scored)}): median |move| {np.median(moves):.0f} "
      f"places, p95 {np.percentile(moves,95):.0f}")
print(f"  Top-100 turnover: {len(top100_old - top100_new)} players in/out")

json.dump({"n": len(rows), "mean_raw_move": float(d.mean()),
           "displayed_moved": int((dd != 0).sum()),
           "displayed_moved_share": float((dd != 0).mean()),
           "offsets": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in OFF.items()}},
          open(OUT / "a9_blast.json", "w"), indent=1)
print("\nwrote", OUT / "a9_blast.json")
