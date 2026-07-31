# scratch lab: intlalias step 3 -- resolved-outcome availability for the intl cohort.
import sys, sqlite3, json, collections
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
DB = HERE / "prospects.db"
con = sqlite3.connect(str(DB)); cur = con.cursor()

intl = {}
for pk, first_y, name in cur.execute(
    "SELECT player_key, MIN(substr(snapshot_date,1,4)), MIN(player_name) FROM snapshots "
    "WHERE source='mlb_pipeline_international' AND fv IS NOT NULL GROUP BY player_key"):
    intl[pk] = (first_y, name)
print("distinct intl-graded players ever:", len(intl))

deb = json.load(open(HERE / "data" / "debuts_lite.json", encoding="utf-8"))
dmap = {d["player_key"]: d for d in deb}
print("debuts_lite rows:", len(deb))
hit = {pk: dmap[pk] for pk in intl if pk in dmap}
print("intl players present in debuts_lite:", len(hit))
st = collections.Counter(v.get("status") for v in hit.values())
print("  status counts:", dict(st))
lv = collections.Counter(v.get("current_level") for v in hit.values())
print("  current_level:", dict(lv))
for pk, v in sorted(hit.items()):
    if v.get("status") == "debuted":
        print("   DEBUTED:", pk, v.get("player_name"), v.get("debut_date"), v.get("age"))

# Does any WAR-bearing artifact cover them?
for fn in ("war_cohort_eval.json", "xfv_peak_war_eval.json", "star_label_view.json"):
    p = HERE / "data" / fn
    try:
        j = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print(fn, "ERR", e); continue
    print("\n", fn, type(j), (list(j.keys())[:10] if isinstance(j, dict) else len(j)))

# the eFV training label source
import glob
print("\n--- searching the DB for a WAR table ---")
for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print("  ", r[0])
con.close()
