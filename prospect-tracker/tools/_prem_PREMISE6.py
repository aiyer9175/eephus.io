"""PREMISE ATTACK part 6: is the lead's headline CONTRAST (0.49 vs 7.02)
confounded by differential censoring between the two groups?"""
import json, collections, statistics, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import storage, efv_dataset as ed, value_framework as vf
rows = json.load(open(os.path.join(ROOT, "data", "xfv_hitter_matrix.json")))
def m(r):
    return r.get("milb") or {}

OLD = [r for r in rows if m(r).get("level_rank") == 5.0 and (m(r).get("age") or 0) >= 23.5
       and (m(r).get("ops_rel") is not None and m(r)["ops_rel"] < 0)]
YNG = [r for r in rows if m(r).get("level_rank") == 5.0 and (m(r).get("age") or 99) <= 22
       and (m(r).get("ops_rel") is not None and m(r)["ops_rel"] > 0)]
print("OLD/LOW n=%d mean %.3f | YOUNG/HIGH n=%d mean %.3f"
      % (len(OLD), statistics.mean(r["target_resolved"] for r in OLD),
         len(YNG), statistics.mean(r["target_resolved"] for r in YNG)))

print()
print("=== observed_seasons composition of each group ===")
for name, G in (("OLD/LOW", OLD), ("YOUNG/HIGH", YNG)):
    c = collections.Counter(r.get("observed_seasons") for r in G)
    nd = [r for r in G if r["kind"] == "debuted"]
    mo = statistics.mean(r.get("observed_seasons") or 6 for r in nd) if nd else float("nan")
    print("  %-11s %s   mean obs over debuted rows %.2f   busts %d"
          % (name, dict(sorted(c.items())), mo,
             sum(1 for r in G if r["kind"] == "bust")))

print()
print("=== milb_season composition ===")
for name, G in (("OLD/LOW", OLD), ("YOUNG/HIGH", YNG)):
    c = collections.Counter(m(r).get("milb_season") for r in G)
    print("  %-11s %s" % (name, dict(sorted(c.items(), key=lambda kv: (kv[0] is None, kv[0])))))

print()
print("=== THE CENSORING-MATCHED CONTRAST: same observed_seasons stratum ===")
print("%5s %8s %9s %8s %9s %10s" % ("obs", "n_old", "mean_old", "n_yng", "mean_yng", "gap"))
for k in (2, 3, 4, 5, 6):
    o = [r["target_resolved"] for r in OLD if (r.get("observed_seasons") == k) and r["kind"] == "debuted"]
    y = [r["target_resolved"] for r in YNG if (r.get("observed_seasons") == k) and r["kind"] == "debuted"]
    if not o and not y:
        continue
    print("%5d %8d %9s %8d %9s %10s"
          % (k, len(o), ("%.3f" % statistics.mean(o)) if o else "-",
             len(y), ("%.3f" % statistics.mean(y)) if y else "-",
             ("%.3f" % (statistics.mean(y) - statistics.mean(o))) if (o and y) else "-"))

print()
print("=== fully-elapsed-only contrast (the only honest one) ===")
def ela(r):
    return r["kind"] == "debuted" and (r.get("debut_year") or 9999) + 5 <= ed.RESOLVED_THROUGH
oe = [r["target_resolved"] for r in OLD if ela(r)]
ye = [r["target_resolved"] for r in YNG if ela(r)]
random.seed(3)
def boot(v, B=4000):
    ms = sorted(statistics.mean(random.choices(v, k=len(v))) for _ in range(B))
    return ms[int(0.025 * B)], ms[int(0.975 * B)]
for nm, v in (("OLD/LOW elapsed", oe), ("YOUNG/HIGH elapsed", ye)):
    if v:
        lo, hi = boot(v)
        print("  %-20s n=%2d mean %.3f CI95 [%.3f, %.3f] -> implied FV %.1f"
              % (nm, len(v), statistics.mean(v), lo, hi,
                 vf.realized_implied_fv(max(statistics.mean(v), 0.0), False, age=31.0,
                                        position="CF", exposure_seasons=6)))
if oe and ye:
    B = 4000
    d = sorted(statistics.mean(random.choices(ye, k=len(ye))) - statistics.mean(random.choices(oe, k=len(oe)))
               for _ in range(B))
    print("  GAP elapsed-only %.3f  CI95 [%.3f, %.3f]"
          % (statistics.mean(ye) - statistics.mean(oe), d[int(0.025 * B)], d[int(0.975 * B)]))
