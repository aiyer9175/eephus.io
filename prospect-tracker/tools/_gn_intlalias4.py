# scratch lab: intlalias -- date confound + resolved-outcome availability (step 3).
import sys, sqlite3, json, collections
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
DB = HERE / "prospects.db"
con = sqlite3.connect(str(DB)); cur = con.cursor()

print("=== main mlb_pipeline snapshot dates per year (count) ===")
for r in cur.execute("""SELECT substr(snapshot_date,1,4) y, snapshot_date, COUNT(*)
                        FROM snapshots WHERE source='mlb_pipeline'
                        GROUP BY snapshot_date ORDER BY snapshot_date"""):
    print("  ", r)

print("\n=== fangraphs snapshot dates per year (count) ===")
for r in cur.execute("""SELECT substr(snapshot_date,1,4) y, COUNT(DISTINCT snapshot_date), COUNT(*)
                        FROM snapshots WHERE source='fangraphs'
                        GROUP BY y ORDER BY y"""):
    print("  ", r)

# Same-player same-cycle intl vs main, but pair on the NEAREST-in-time main snapshot
print("\n=== same-player same-year intl-vs-main gap by year (all years) ===")
q = """SELECT substr(a.snapshot_date,1,4) y, a.player_key, a.snapshot_date, a.fv,
              b.snapshot_date, b.fv
       FROM snapshots a JOIN snapshots b
         ON a.player_key=b.player_key
        AND substr(a.snapshot_date,1,4)=substr(b.snapshot_date,1,4)
       WHERE a.source='mlb_pipeline_international' AND b.source='mlb_pipeline'
         AND a.fv IS NOT NULL AND b.fv IS NOT NULL"""
rows = list(cur.execute(q))
# keep latest per (player, year) for each side
best = {}
for y, pk, ad, af, bd, bf in rows:
    k = (y, pk)
    cur_a = best.get(k)
    if cur_a is None or (ad, bd) > (cur_a[0], cur_a[2]):
        best[k] = (ad, af, bd, bf)
byy = collections.defaultdict(list)
for (y, pk), (ad, af, bd, bf) in best.items():
    byy[y].append((af - bf, ad, bd))
for y in sorted(byy):
    v = byy[y]
    print(f"  {y}: n={len(v):3d} intl-main={np.mean([x[0] for x in v]):+7.3f}  "
          f"intl_date={v[0][1]} main_date={v[0][2]}")

# Which cohort is affected: intl grade present, NO main-pipeline grade that cycle
print("\n=== affected population per cycle (intl-only, i.e. alias RELABELED) ===")
for y in ['2021','2022','2023','2024','2025','2026']:
    intl = {r[0] for r in cur.execute(
        "SELECT DISTINCT player_key FROM snapshots WHERE source='mlb_pipeline_international' "
        "AND substr(snapshot_date,1,4)=? AND fv IS NOT NULL", (y,))}
    main = {r[0] for r in cur.execute(
        "SELECT DISTINCT player_key FROM snapshots WHERE source='mlb_pipeline' "
        "AND substr(snapshot_date,1,4)=? AND fv IS NOT NULL", (y,))}
    print(f"  {y}: intl={len(intl):3d} also_on_main={len(intl&main):3d} INTL_ONLY={len(intl-main):3d}")

# ---- resolved outcomes for the intl cohort ----
print("\n=== resolved outcomes: do any intl-list players have MLB WAR? ===")
allintl = {r[0]: r[1] for r in cur.execute(
    "SELECT DISTINCT player_key, MIN(substr(snapshot_date,1,4)) FROM snapshots "
    "WHERE source='mlb_pipeline_international' GROUP BY player_key")}
print("  distinct intl players ever:", len(allintl))
dat = HERE / "data"
for fn in ["debuts.json", "efv_labels.json", "career_war.json"]:
    p = dat / fn
    print("  ", fn, "exists" if p.exists() else "MISSING")
import glob
print("\n  data/*.json candidates with war/debut in name:")
for p in sorted(dat.glob("*.json")):
    n = p.name.lower()
    if "war" in n or "debut" in n or "label" in n or "outcome" in n:
        print("   ", p.name, p.stat().st_size)
con.close()
