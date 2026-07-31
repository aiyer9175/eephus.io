"""PREMISE ATTACK part 2: reproduce the lead's exact n=69 and decompose it."""
import json, collections, statistics, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import efv_dataset as ed
rows = json.load(open(os.path.join(ROOT, "data", "xfv_hitter_matrix.json")))

def m(r):
    return r.get("milb") or {}

S = [r for r in rows
     if m(r).get("level_rank") == 5.0 and (m(r).get("age") or 0) >= 23.5
     and (m(r).get("ops_rel") is not None and m(r)["ops_rel"] < 0)]
print("n=%d" % len(S))
for key in ("target_resolved", "target_censored"):
    t = [r[key] for r in S]
    print("%-16s mean %.4f median %.4f  frac<0.5 %.4f  frac<3.0 %.4f"
          % (key, statistics.mean(t), statistics.median(t),
             sum(1 for x in t if x < 0.5) / len(t),
             sum(1 for x in t if x < 3.0) / len(t)))

print()
print("=== decomposition of the n=69 by row provenance and label truthfulness ===")
buckets = collections.defaultdict(list)
for r in S:
    if r["kind"] == "bust":
        y = (r.get("cutoff") or "")[:4]
        el = y.isdigit() and int(y) + 5 <= ed.RESOLVED_THROUGH
        buckets["bust_hardcoded_0" + ("_window_elapsed" if el else "_window_NOT_elapsed")].append(r)
    else:
        dy = r.get("debut_year") or 9999
        if dy + 5 <= ed.RESOLVED_THROUGH:
            buckets["debut_window_ELAPSED"].append(r)
        else:
            buckets["debut_window_CENSORED_extrapolated"].append(r)
for k in sorted(buckets):
    v = buckets[k]
    t = [r["target_resolved"] for r in v]
    tc = [r["target_censored"] for r in v]
    print("  %-42s n=%2d  res_mean %7.3f  cens_mean %7.3f  frac<0.5(res) %.3f"
          % (k, len(v), statistics.mean(t), statistics.mean(tc),
             sum(1 for x in t if x < 0.5) / len(t)))

print()
print("=== per-row detail (the whole cohort the owner's case rests on) ===")
print("%-28s %-8s %-6s %-6s %-5s %-6s %7s %7s %5s %6s" %
      ("player", "kind", "cut", "milbY", "obs", "wt", "res", "cens", "age", "ops_rel"))
for r in sorted(S, key=lambda r: (r["kind"], r.get("cutoff") or "")):
    mm = m(r)
    print("%-28s %-8s %-6s %-6s %-5s %-6s %7.2f %7.2f %5.1f %6.3f"
          % (r["player_key"][:28], r["kind"], (r.get("cutoff") or "")[:4],
             mm.get("milb_season"), r.get("observed_seasons"), r.get("weight"),
             r["target_resolved"], r["target_censored"], mm.get("age"), mm.get("ops_rel")))

print()
print("=== MiLB SEASON (era) distribution of the stratum ===")
c = collections.Counter(m(r).get("milb_season") for r in S)
for y in sorted(c, key=lambda x: (x is None, x)):
    print("  %s : %d" % (y, c[y]))

print()
print("=== stratum-implied FV via the config's own map, by subset ===")
import value_framework as vf
def implied(mean_war):
    # inverse of value_framework fv_to_6yr_avg_war on the ANNUAL average
    try:
        return vf.realized_implied_fv(mean_war, False, age=31.0, position="CF",
                                      exposure_seasons=6)
    except Exception as e:
        return "err:%s" % e
for name, sub in (("ALL 69", S),
                  ("elapsed debuts only", buckets["debut_window_ELAPSED"]),
                  ("all debuts", [r for r in S if r["kind"] == "debuted"])):
    if not sub:
        continue
    mw = statistics.mean(r["target_resolved"] for r in sub)
    mc = statistics.mean(r["target_censored"] for r in sub)
    print("  %-22s n=%2d  resolved-mean %.3f -> implied %s | censored-mean %.3f -> implied %s"
          % (name, len(sub), mw, implied(mw), mc, implied(mc)))
