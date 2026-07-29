"""PREMISE ATTACK part 4: uncertainty, the cited comps, and era comparability."""
import json, collections, statistics, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import storage, efv_dataset as ed, value_framework as vf
rows = json.load(open(os.path.join(ROOT, "data", "xfv_hitter_matrix.json")))

def m(r):
    return r.get("milb") or {}
S = [r for r in rows
     if m(r).get("level_rank") == 5.0 and (m(r).get("age") or 0) >= 23.5
     and (m(r).get("ops_rel") is not None and m(r)["ops_rel"] < 0)]

random.seed(11)
def boot(vals, B=4000):
    n = len(vals)
    ms = sorted(statistics.mean(random.choices(vals, k=n)) for _ in range(B))
    return ms[int(0.025 * B)], ms[int(0.975 * B)]

print("=== BOOTSTRAP CIs ON THE STRATUM MEAN (the whole basis of the complaint) ===")
raw = [r["target_resolved"] for r in S]
lo, hi = boot(raw)
print("all 69, raw partial sums   mean %.3f  CI95 [%.3f, %.3f]  -> implied FV [%.1f, %.1f]"
      % (statistics.mean(raw), lo, hi,
         vf.realized_implied_fv(lo, False, age=31.0, position="CF", exposure_seasons=6),
         vf.realized_implied_fv(hi, False, age=31.0, position="CF", exposure_seasons=6)))
el = [r["target_resolved"] for r in S
      if r["kind"] == "debuted" and (r.get("debut_year") or 9999) + 5 <= ed.RESOLVED_THROUGH]
lo, hi = boot(el)
print("n=9 elapsed only           mean %.3f  CI95 [%.3f, %.3f]  -> implied FV [%.1f, %.1f]"
      % (statistics.mean(el), lo, hi,
         vf.realized_implied_fv(max(lo, 0.0), False, age=31.0, position="CF", exposure_seasons=6),
         vf.realized_implied_fv(hi, False, age=31.0, position="CF", exposure_seasons=6)))
bl = [r["target_censored"] for r in S if r["kind"] == "debuted"]
lo, hi = boot(bl)
print("62 debuts, linear 6yr est  mean %.3f  CI95 [%.3f, %.3f]"
      % (statistics.mean(bl), lo, hi))

print()
print("=== BUST-RATE CI (the '78.3%') ===")
b = [1.0 if r["target_resolved"] < 0.5 else 0.0 for r in S]
lo, hi = boot(b)
print("all 69   %.3f  CI95 [%.3f, %.3f]" % (statistics.mean(b), lo, hi))
be = [1.0 if v < 0.5 else 0.0 for v in el]
lo, hi = boot(be)
print("n=9 elapsed %.3f CI95 [%.3f, %.3f]" % (statistics.mean(be), lo, hi))

print()
print("=== THE FOUR CITED COMPS: are their careers actually over? ===")
comps = ["brandon_lockridge", "greg_jones", "corey_ray", "jacob_robson"]
by_key = {r["player_key"]: r for r in rows}
cw = {}
with storage.connect() as con:
    for r in con.execute("SELECT player_key, payload_json FROM career_war"):
        try:
            p = json.loads(r["payload_json"])
        except Exception:
            continue
        s = p.get("seasons") or p
        d = {}
        for k, v in (s.items() if isinstance(s, dict) else []):
            try:
                d[int(k)] = float(v)
            except Exception:
                pass
        if d:
            cw[r["player_key"]] = d
for c in comps:
    r = by_key.get(c)
    if not r:
        print("  %-20s NOT IN MATRIX" % c)
        continue
    s = cw.get(c, {})
    print("  %-20s debut %s  obs_seasons %s/6  target_resolved %.2f  seasons_on_file %s"
          % (c, r.get("debut_year"), r.get("observed_seasons"), r["target_resolved"],
             sorted(s.items())))

print()
print("=== ERA: is a 2019 AAA 24-year-old the same population as a 2023 one? ===")
# every hitter matrix row with a AAA milb block, by milb_season
by_season = collections.defaultdict(list)
for r in rows:
    mm = m(r)
    if mm.get("level_rank") == 5.0 and mm.get("milb_season") and mm.get("age") is not None:
        by_season[mm["milb_season"]].append(r)
print("%6s %5s %8s %8s %8s %8s" % ("season", "n", "mean_age", "p_age>=23.5", "mean_ops_rel", "p_debuted"))
for y in sorted(by_season):
    v = by_season[y]
    ages = [m(r)["age"] for r in v]
    ops = [m(r)["ops_rel"] for r in v if m(r).get("ops_rel") is not None]
    print("%6s %5d %8.2f %8.3f %8.4f %8.3f"
          % (y, len(v), statistics.mean(ages),
             sum(1 for a in ages if a >= 23.5) / len(ages),
             statistics.mean(ops) if ops else float("nan"),
             sum(1 for r in v if r["kind"] == "debuted") / len(v)))

print()
print("=== ERA 2: elapsed-window availability by milb_season (the vise) ===")
for y in sorted(by_season):
    v = [r for r in by_season[y] if (m(r).get("age") or 0) >= 23.5
         and (m(r).get("ops_rel") or 0) < 0]
    if not v:
        continue
    ela = sum(1 for r in v
              if r["kind"] == "debuted" and (r.get("debut_year") or 9999) + 5 <= ed.RESOLVED_THROUGH)
    print("  milb %s: stratum rows %2d, of which fully elapsed %2d" % (y, len(v), ela))
