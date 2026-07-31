# scratch lab: intlalias step 2b -- what IS the intl grade? provenance check.
import sys, sqlite3, collections
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
DB = HERE / "prospects.db"
con = sqlite3.connect(str(DB))
cur = con.cursor()

print("=== snapshots schema ===")
for r in cur.execute("PRAGMA table_info(snapshots)"):
    print("  ", r[1], r[2])

print("\n=== mlb_pipeline_international snapshot dates x count, fv-null share ===")
for r in cur.execute("""SELECT snapshot_date, COUNT(*), SUM(fv IS NULL), MIN(fv), MAX(fv),
                        MIN(rank), MAX(rank)
                        FROM snapshots WHERE source='mlb_pipeline_international'
                        GROUP BY snapshot_date ORDER BY snapshot_date"""):
    print("  ", r)

print("\n=== intl FV value histogram ===")
for r in cur.execute("""SELECT fv, COUNT(*) FROM snapshots
                        WHERE source='mlb_pipeline_international' AND fv IS NOT NULL
                        GROUP BY fv ORDER BY fv"""):
    print("  fv", r[0], "n", r[1])

print("\n=== main mlb_pipeline FV histogram (for shape comparison) ===")
for r in cur.execute("""SELECT fv, COUNT(*) FROM snapshots
                        WHERE source='mlb_pipeline' AND fv IS NOT NULL
                        GROUP BY fv ORDER BY fv"""):
    print("  fv", r[0], "n", r[1])

print("\n=== intl rank vs fv (2026) ===")
for r in cur.execute("""SELECT rank, fv, COUNT(*) FROM snapshots
                        WHERE source='mlb_pipeline_international'
                          AND substr(snapshot_date,1,4)='2026'
                        GROUP BY rank, fv ORDER BY rank LIMIT 60"""):
    print("  rank", r[0], "fv", r[1], "n", r[2])

print("\n=== same-player same-year: intl vs main pipeline examples (2026 hitters) ===")
q = """SELECT a.player_key, a.player_name, a.rank, a.fv, b.rank, b.fv
       FROM snapshots a JOIN snapshots b
         ON a.player_key=b.player_key
        AND substr(a.snapshot_date,1,4)=substr(b.snapshot_date,1,4)
       WHERE a.source='mlb_pipeline_international' AND b.source='mlb_pipeline'
         AND substr(a.snapshot_date,1,4)='2026' AND a.fv IS NOT NULL AND b.fv IS NOT NULL
       GROUP BY a.player_key LIMIT 30"""
for r in cur.execute(q):
    print("  ", r)
con.close()
