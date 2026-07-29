"""PREMISE ATTACK part 7: bracket the honest stratum level between its two
opposing biases, and check the never-debuted arm for the 2018-2019 window."""
import json, collections, statistics, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import storage, efv_dataset as ed, value_framework as vf
rows = json.load(open(os.path.join(ROOT, "data", "xfv_hitter_matrix.json")))
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
def m(r):
    return r.get("milb") or {}
S = [r for r in rows if m(r).get("level_rank") == 5.0 and (m(r).get("age") or 0) >= 23.5
     and (m(r).get("ops_rel") is not None and m(r)["ops_rel"] < 0)]

print("=== 1. is the honest n=9 window free of never-debuted busts? ===")
aaa_busts = [r for r in rows if r["kind"] == "bust" and m(r).get("level_rank") == 5.0]
print("  ALL hitter busts with a AAA milb block: %d" % len(aaa_busts))
for r in sorted(aaa_busts, key=lambda r: (r.get("cutoff") or "")):
    print("    %-24s cutoff %s milb_season %s age %s ops_rel %s"
          % (r["player_key"][:24], (r.get("cutoff") or "")[:10], m(r).get("milb_season"),
             m(r).get("age"), round(m(r).get("ops_rel") or 0, 3)))
print("  -> AAA bust rows anchored in 2018-2020 (the only elapsed window): %d"
      % sum(1 for r in aaa_busts if (r.get("cutoff") or "")[:4] in ("2018", "2019", "2020")))

print()
print("=== 2. BRACKET the honest 6-year mean for the stratum ===")
RT = ed.RESOLVED_THROUGH
E = [r for r in rows if r["kind"] == "debuted" and r.get("debut_year")
     and r["debut_year"] + 5 <= RT and r["player_key"] in cw]
def psum(r, k):
    s = cw[r["player_key"]]
    return sum(s.get(r["debut_year"] + i, 0.0) for i in range(k))
def debut_age(r):
    bd = r.get("birth_date") or ""
    try:
        return r["debut_year"] - int(bd[:4])
    except Exception:
        return None
L = [r for r in E if (debut_age(r) or 0) >= 24]
ratio = {}
for k in range(1, 7):
    mk = statistics.mean(psum(r, k) for r in L)
    ratio[k] = statistics.mean(psum(r, 6) for r in L) / mk if mk else 6.0 / k

deb = [r for r in S if r["kind"] == "debuted"]
corr = [r["target_resolved"] * ratio.get(r.get("observed_seasons") or 6, 1.0) for r in deb]
est_debuts_only = statistics.mean(corr)
est_with_busts = sum(corr) / len(S)      # 7 fabricated 0.0 rows included
elapsed_only = statistics.mean(r["target_resolved"] for r in deb
                               if (r.get("debut_year") or 9999) + 5 <= RT)
def ifv(w):
    return vf.realized_implied_fv(max(w, 0.0), False, age=31.0, position="CF", exposure_seasons=6)
print("  LOWER bound  (lead's raw truncated sums, 0 for busts) %.3f WAR -> FV %.1f" % (0.4942, ifv(0.4942)))
print("  truncation-corrected, busts kept at 0.0               %.3f WAR -> FV %.1f" % (est_with_busts, ifv(est_with_busts)))
print("  truncation-corrected, debuted rows only               %.3f WAR -> FV %.1f" % (est_debuts_only, ifv(est_debuts_only)))
print("  UPPER bound  (fully elapsed windows only, n=9)        %.3f WAR -> FV %.1f" % (elapsed_only, ifv(elapsed_only)))
print()
print("  Bradfield: consensus 45.64, served eFV 50.97.")
print("  WAR the inverter needs to print 45.64 / 50.97:")
lo, hi = 0.0, 12.0
for target in (45.64, 50.97):
    a, b = 0.0, 15.0
    for _ in range(80):
        mid = (a + b) / 2
        if ifv(mid) < target:
            a = mid
        else:
            b = mid
    print("    FV %.2f  <=>  %.3f WAR" % (target, (a + b) / 2))

print()
print("=== 3. bust-rate under each estimator (shipped band: 6yr summed < 3.0) ===")
random.seed(5)
def boot(v, B=4000):
    ms = sorted(statistics.mean(random.choices(v, k=len(v))) for _ in range(B))
    return ms[int(.025 * B)], ms[int(.975 * B)]
raw = [1.0 if r["target_resolved"] < 3.0 else 0.0 for r in S]
lo1, hi1 = boot(raw)
print("  raw truncated sums   %.3f CI95 [%.3f,%.3f]" % (statistics.mean(raw), lo1, hi1))
cr = [1.0 if v < 3.0 else 0.0 for v in corr]
lo2, hi2 = boot(cr)
print("  truncation-corrected %.3f CI95 [%.3f,%.3f]" % (statistics.mean(cr), lo2, hi2))
el = [1.0 if r["target_resolved"] < 3.0 else 0.0 for r in deb
      if (r.get("debut_year") or 9999) + 5 <= RT]
lo3, hi3 = boot(el)
print("  elapsed only (n=%d)   %.3f CI95 [%.3f,%.3f]" % (len(el), statistics.mean(el), lo3, hi3))
print("  Bradfield served p_bust 0.239 (odds lane proposes 0.573)")
