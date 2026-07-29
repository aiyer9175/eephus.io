# Scratch: before/after evidence for the proj_export payload fixes.
# Read-only against data/mlb_projections.json + value_framework.
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import value_framework as vf
import proj_export as pe

pay = json.loads((ROOT / "data" / "mlb_projections.json").read_text(encoding="utf-8"))
rows = list(pay["vets"]) + list(pay["prospects"])
FS, H = pe.FIRST_SEASON, pe.HORIZON

print("=== P-PWINDOW: prospect warTotal window ===")
pros = [m for m in rows if m.get("src") == "prospect"]
late = [m for m in pros if (m.get("eta") or FS) > FS]
old_sum = new_sum = 0.0
worst = []
for m in late:
    war = m.get("war") or []
    old = round(sum(war[:H]), 1)
    inw = max(0, H - (int(m["eta"]) - FS))
    new = round(sum(war[:inw]), 1)
    old_sum += old; new_sum += new
    worst.append((old - new, m["name"], m["eta"], old, new))
print(f"prospects total {len(pros)}, eta>{FS}: {len(late)}")
print(f"  shipped warTotal sum {old_sum:.1f} vs in-window {new_sum:.1f} "
      f"(ratio {old_sum/max(new_sum,1e-9):.2f}x)")
worst.sort(reverse=True)
for d, nm, eta, o, n in worst[:6]:
    print(f"   {nm:<26} eta={eta} warTotal {o} -> {n}")

print("\n=== P-ETACLAMP: prospect debut-age anchor ===")
n_shift = 0
deltas = []
for m in pros:
    age, eta = m.get("age"), m.get("eta")
    if age is None or eta is None:
        continue
    # raw eta is not on the row (it was clamped at export). Reconstruct the
    # affected population: a prospect whose eta EQUALS FIRST_SEASON is the
    # clamp target; the raw eta is recoverable only from the source board.
    pass
ps = json.loads((ROOT/"data"/"timeseries.json").read_text(encoding="utf-8")).get("players") or []
raw_eta = {}
for p in ps:
    k = p.get("player_key")
    e = (p.get("eta") or {}).get("year")
    if k and e:
        raw_eta[k] = int(e)
aff = [m for m in pros if raw_eta.get(m.get("key")) is not None
       and raw_eta[m["key"]] < FS]
print(f"  prospects with a RAW eta before {FS} (clamped on export): {len(aff)} of {len(pros)}")
tot_o = tot_n = 0.0
ex = []
for m in aff[:400]:
    age = m.get("age")
    if age is None:
        continue
    fv = m.get("fv")
    pos = m.get("pos")
    is_pit = vf.is_pitcher_position(pos)
    rel = vf.is_reliever_position(pos)
    role = vf._role_key(is_pit)
    price_fv = fv
    probs = vf.p_bucket_given_fv(float(price_fv), is_pit)
    if not probs:
        continue
    scale = vf._war_scale_for(float(price_fv), role)
    for label, da in (("old", float(age) + max(0, raw_eta[m["key"]] - (FS - 1))),
                      ("new", float(age) + max(0, FS - (FS - 1)))):
        paths = [vf._bucket_season_wars(role, i, rel, da, scale)
                 for i in range(5)]
        mp = [sum(pr * paths[i][t] for i, pr in enumerate(probs))
              for t in range(len(paths[0]))]
        if label == "old":
            o = sum(mp[:H]); da_o = da
        else:
            n = sum(mp[:H]); da_n = da
    tot_o += o; tot_n += n
    ex.append((abs(n - o), m["name"], round(da_o, 1), round(da_n, 1), round(o, 2), round(n, 2)))
print(f"  affected+priced n={len(ex)}  5y mean-path sum {tot_o:.1f} -> {tot_n:.1f} "
      f"({(tot_n-tot_o):+.1f} WAR, {(tot_n/max(tot_o,1e-9)-1)*100:+.1f}%)")
ex.sort(reverse=True)
for d, nm, dao, dan, o, n in ex[:6]:
    print(f"   {nm:<26} debutAge {dao} -> {dan}   5y {o} -> {n}")

print("\n=== P-POSVAL: contract position vocabulary ===")
bad = [(m.get("key"), m.get("name"), m.get("pos"), m.get("team"), m.get("aav"))
       for m in rows if m.get("src") != "prospect" and not pe._valid_pos(m.get("pos"))]
print(f"  vet rows failing the whitelist: {len(bad)}")
from collections import Counter
print("  ", Counter(b[2] for b in bad).most_common(8))
for b in bad[:4]:
    print("   ", b)
