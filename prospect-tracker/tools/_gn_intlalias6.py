# scratch lab: intlalias -- within-outlet control + career_war coverage.
import sys, sqlite3, json, collections
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
DB = HERE / "prospects.db"
con = sqlite3.connect(str(DB)); cur = con.cursor()

print("=== career_war schema/coverage for intl cohort ===")
for r in cur.execute("PRAGMA table_info(career_war)"):
    print("  ", r[1], r[2])
intl = [r[0] for r in cur.execute(
    "SELECT DISTINCT player_key FROM snapshots WHERE source='mlb_pipeline_international' AND fv IS NOT NULL")]
qm = ",".join("?" * len(intl))
try:
    rows = list(cur.execute(f"SELECT * FROM career_war WHERE player_key IN ({qm})", intl))
    print("  career_war rows for intl cohort:", len(rows))
    for r in rows[:20]:
        print("   ", r)
except Exception as e:
    print("  ERR", e)
    rows = list(cur.execute("SELECT * FROM career_war LIMIT 3"))
    print("  sample:", rows)

print("\n=== interval_label values for mlb_pipeline ===")
for r in cur.execute("""SELECT interval_label, COUNT(*) FROM snapshots
                        WHERE source='mlb_pipeline' GROUP BY interval_label
                        ORDER BY 2 DESC LIMIT 20"""):
    print("  ", r)

print("\n=== CONTROL: within-mlb_pipeline multi-row same date/player FV disagreement ===")
# a player appearing more than once from mlb_pipeline on the SAME date = 2 lists
q = """SELECT player_key, snapshot_date, COUNT(*) c, MIN(fv), MAX(fv)
       FROM snapshots WHERE source='mlb_pipeline' AND fv IS NOT NULL
       GROUP BY player_key, snapshot_date HAVING c >= 2"""
ctl = list(cur.execute(q))
print("  same-date multi-list player rows:", len(ctl))
if ctl:
    d = [abs(r[4] - r[3]) for r in ctl]
    sg = [r[4] - r[3] for r in ctl]
    print(f"  mean |list-to-list FV gap| within mlb_pipeline = {np.mean(d):.3f}  "
          f"(max {max(d):.1f}, share nonzero {np.mean([x>0 for x in d]):.3f}, n={len(d)})")

print("\n=== CONTROL 2: fangraphs multi-row same date/player ===")
q2 = """SELECT player_key, snapshot_date, COUNT(*) c, MIN(fv), MAX(fv)
        FROM snapshots WHERE source='fangraphs' AND fv IS NOT NULL
        GROUP BY player_key, snapshot_date HAVING c >= 2"""
ctl2 = list(cur.execute(q2))
print("  n:", len(ctl2))
if ctl2:
    d2 = [abs(r[4] - r[3]) for r in ctl2]
    print(f"  mean |gap| = {np.mean(d2):.3f}  share nonzero {np.mean([x>0 for x in d2]):.3f}")

# ---- the within-outlet intl-vs-main gap with a player-clustered bootstrap ----
print("\n=== WITHIN-OUTLET intl-vs-main gap, player-clustered bootstrap ===")
q3 = """SELECT a.player_key, substr(a.snapshot_date,1,4) y, a.fv, b.fv, a.snapshot_date, b.snapshot_date
        FROM snapshots a JOIN snapshots b
          ON a.player_key=b.player_key AND substr(a.snapshot_date,1,4)=substr(b.snapshot_date,1,4)
        WHERE a.source='mlb_pipeline_international' AND b.source='mlb_pipeline'
          AND a.fv IS NOT NULL AND b.fv IS NOT NULL"""
raw = list(cur.execute(q3))
best = {}
for pk, y, af, bf, ad, bd in raw:
    k = (pk, y)
    if k not in best or (ad, bd) > best[k][3]:
        best[k] = (af, bf, y, (ad, bd))
rows = [dict(pk=pk, y=y, gap=af - bf) for (pk, y), (af, bf, _y, _d) in best.items()]
print("  n player-cycles:", len(rows), " distinct players:", len({r['pk'] for r in rows}))

def cboot(rows, B=4000, seed=11):
    cl = collections.defaultdict(list)
    for r in rows: cl[r["pk"]].append(r)
    ks = list(cl); rng = np.random.default_rng(seed)
    pt = float(np.mean([r["gap"] for r in rows]))
    dr = []
    for _ in range(B):
        idx = rng.integers(0, len(ks), len(ks))
        s = [x for i in idx for x in cl[ks[i]]]
        dr.append(np.mean([r["gap"] for r in s]))
    return pt, float(np.percentile(dr, 2.5)), float(np.percentile(dr, 97.5))

pt, lo, hi = cboot(rows)
print(f"  intl - main_pipeline (SAME OUTLET, SAME PLAYER, SAME CYCLE) = {pt:+.3f} CI95 [{lo:+.3f}, {hi:+.3f}]")
# per-year leave-one-year-out (>=4 time splits)
yrs = sorted({r["y"] for r in rows})
print("  per-year (time splits):")
for y in yrs:
    s = [r for r in rows if r["y"] == y]
    p, l, h = cboot(s, B=2000)
    print(f"    {y}: n={len(s):3d} gap={p:+7.3f} CI95 [{l:+.3f}, {h:+.3f}]")
print("  leave-one-year-out:")
for y in yrs:
    s = [r for r in rows if r["y"] != y]
    p, l, h = cboot(s, B=1500)
    print(f"    drop {y}: n={len(s):3d} gap={p:+7.3f} CI95 [{l:+.3f}, {h:+.3f}]")

# sign-permutation null: if the gap were noise, signs are exchangeable
rng = np.random.default_rng(5)
g = np.array([r["gap"] for r in rows])
null = [float(np.mean(g * rng.choice([-1, 1], len(g)))) for _ in range(5000)]
print(f"  sign-permutation null: mean {np.mean(null):+.4f}, p95 band "
      f"[{np.percentile(null,2.5):+.3f}, {np.percentile(null,97.5):+.3f}]  observed {pt:+.3f}")
con.close()
