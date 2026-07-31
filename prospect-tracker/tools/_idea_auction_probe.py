import sqlite3, json, collections, statistics
c=sqlite3.connect('prospects.db')
rows=[json.loads(r[0]) for r in c.execute("select payload_json from fa_signings")]
print("n signings", len(rows))
keys=collections.Counter()
for r in rows: keys.update(r.keys())
print("KEYS:", keys.most_common())
by=collections.Counter((r['class_year'], bool(r.get('mlb_deal'))) for r in rows)
for y in sorted(set(k[0] for k in by)):
    print(y, "mlb", by[(y,True)], "minor", by[(y,False)])
print("--- payroll ---")
pr=[json.loads(r[0]) for r in c.execute("select payload_json from fa_team_payroll")]
print(collections.Counter(p.get('season') for p in pr))
print(json.dumps(pr[0], indent=1)[:900])
