# Scratch lab (audit-mode, lane=plusmetrics): prospect-side '+' correlation
# matrix on a common player population + the swingman coverage gap.
from __future__ import annotations
import json, os, sys, collections
import numpy as np
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
load = lambda f: json.load(open(os.path.join(D, f), encoding="utf-8"))


def dig(p, path):
    cur = p
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
        if cur is None:
            return None
    return cur


print("=== swingman coverage gap: pitchers on NEITHER MLB '+' board ===")
rel = {r["mlbam"] for r in load("bullpen_leaderboards.json")["relievers"] if r.get("mlbam")}
sta = {r["mlbam"] for r in load("starter_leaderboards.json")["starters"] if r.get("mlbam")}
print(f"  relievers {len(rel)}  starters {len(sta)}  overlap {len(rel & sta)}")
print("  rem_plus qualification: GS/G <= 0.10 ; sem_plus: GS/G >= 0.50")
print("  -> any pitcher with 0.10 < GS/G < 0.50 carries NO '+' metric on this site.")

print("\n=== prospect-side '+' family, common served population ===")
ts = load("timeseries.json")
players = ts["players"]
players = list(players.values()) if isinstance(players, dict) else players
print(f"  timeseries players: {len(players)}")
sample = players[0]
FIELDS = collections.OrderedDict([
    ("statcast_plus", ["statcast_plus"]),
    ("rps_plus", ["statline", "rps_plus"]),
    ("stf_plus_periph", ["statline", "stf_plus_periph"]),
    ("ops_plus_level", ["statline", "ops_plus_level"]),
    ("era_minus_level", ["statline", "era_minus_level"]),
    ("level_plus_pct", ["statline", "level_plus_pct"]),
    ("stuff_plus", ["tools", "composite_stuff_plus"]),
    ("cmd_plus", ["tools", "composite_cmd_plus"]),
    ("dollar_dvm_plus", ["dollar_dvm_plus"]),
    ("fv_close_plus", ["fv_close_plus"]),
])
cov = {}
vals = {k: [] for k in FIELDS}
keys = []
for p in players:
    keys.append(p.get("player_key") or p.get("key"))
    for k, path in FIELDS.items():
        v = dig(p, path)
        try:
            vals[k].append(float(v)) if v is not None else vals[k].append(np.nan)
        except (TypeError, ValueError):
            vals[k].append(np.nan)
arr = {k: np.array(v) for k, v in vals.items()}
for k in FIELDS:
    cov[k] = int((~np.isnan(arr[k])).sum())
print("  coverage:", cov)

# KRP+ from the served pitcher board, joined by player_key
krp = {r["player_key"]: r["krp_plus"] for r in load("xfv_scored_live_pitcher.json")
       if r.get("krp_plus") is not None}
efv = {r["player_key"]: r.get("xfv_grade_display") for r in load("xfv_scored_live_pitcher.json")}
efvh = {r["player_key"]: r.get("xfv_grade_display") for r in load("xfv_scored_live.json")}
arr["krp_plus"] = np.array([krp.get(k, np.nan) for k in keys], dtype=float)
arr["efv_grade"] = np.array([efv.get(k, efvh.get(k, np.nan)) for k in keys], dtype=float)
cov["krp_plus"] = int((~np.isnan(arr["krp_plus"])).sum())
cov["efv_grade"] = int((~np.isnan(arr["efv_grade"])).sum())
print("  + krp_plus:", cov["krp_plus"], " efv_grade:", cov["efv_grade"])

names = [k for k in arr if cov.get(k, 0) >= 40]
print("\n  " + " " * 17 + " ".join(f"{n[:9]:>10}" for n in names))
pairs = []
for a in names:
    line = f"  {a[:16]:<16} "
    for b in names:
        m = ~(np.isnan(arr[a]) | np.isnan(arr[b]))
        if m.sum() < 25:
            line += f"{'.':>10} "
            continue
        r = stats.spearmanr(arr[a][m], arr[b][m]).statistic
        line += f"{r:>10.3f} "
        if a < b:
            pairs.append((a, b, r, int(m.sum())))
    print(line)
print("\n  pairs |rho| >= 0.85:")
hits = [p for p in pairs if p[2] == p[2] and abs(p[2]) >= 0.85]
for a, b, r, n in sorted(hits, key=lambda t: -abs(t[2])):
    print(f"    {a:<18} {b:<18} rho={r:+.4f}  n={n}")
if not hits:
    print("    (none)")
print("\n  pairs 0.70 <= |rho| < 0.85 (watchlist):")
for a, b, r, n in sorted([p for p in pairs if p[2] == p[2] and 0.70 <= abs(p[2]) < 0.85],
                         key=lambda t: -abs(t[2])):
    print(f"    {a:<18} {b:<18} rho={r:+.4f}  n={n}")
