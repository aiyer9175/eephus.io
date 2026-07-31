"""PREMISE ATTACK part 3: how biased is a k-season partial sum as an estimate of
the 6-season total? Measured on fully-elapsed hitter careers from career_war.

If the ratio E[sum_6] / E[sum_k] is much larger than the linear 6/k the dataset
assumes, then the lead's stratum mean (dominated by 2-season partial sums) is a
downward-biased outcome record and the premise fails on censoring alone.
"""
import json, collections, statistics, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import storage, efv_dataset as ed
rows = json.load(open(os.path.join(ROOT, "data", "xfv_hitter_matrix.json")))
print("DB:", storage.DB_PATH, os.path.getsize(storage.DB_PATH))

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
print("career_war players:", len(cw))

RT = ed.RESOLVED_THROUGH
# elapsed hitter debuts: debut_year + 5 <= RESOLVED_THROUGH
E = [r for r in rows if r["kind"] == "debuted" and r.get("debut_year")
     and r["debut_year"] + 5 <= RT and r["player_key"] in cw]
print("fully elapsed hitter debut rows with career_war: %d (debut years %s)"
      % (len(E), sorted(set(r["debut_year"] for r in E))))

def partial(pk, dy, k):
    s = cw[pk]
    return sum(s.get(dy + i, 0.0) for i in range(k))

print()
print("=== TRUNCATION BIAS: k-season partial sum vs the true 6-season total ===")
print("%3s %6s %9s %9s %9s %9s %9s" %
      ("k", "n", "mean_k", "mean_6", "ratio", "linear6/k", "bias_x"))
ratios = {}
for k in (1, 2, 3, 4, 5, 6):
    pk_ = [(partial(r["player_key"], r["debut_year"], k),
            partial(r["player_key"], r["debut_year"], 6)) for r in E]
    mk = statistics.mean(a for a, b in pk_)
    m6 = statistics.mean(b for a, b in pk_)
    ratio = m6 / mk if mk else float("nan")
    ratios[k] = ratio
    print("%3d %6d %9.3f %9.3f %9.3f %9.3f %9.3f"
          % (k, len(pk_), mk, m6, ratio, 6.0 / k, ratio / (6.0 / k)))

print()
print("=== same, restricted to LATE debuts (debut age >= 24), the relevant class ===")
def debut_age(r):
    bd = r.get("birth_date") or ""
    if len(bd) < 4 or not r.get("debut_year"):
        return None
    try:
        return r["debut_year"] - int(bd[:4])
    except Exception:
        return None
L = [r for r in E if (debut_age(r) or 0) >= 24]
print("n=%d" % len(L))
ratios_late = {}
for k in (1, 2, 3, 4, 5, 6):
    pk_ = [(partial(r["player_key"], r["debut_year"], k),
            partial(r["player_key"], r["debut_year"], 6)) for r in L]
    mk = statistics.mean(a for a, b in pk_)
    m6 = statistics.mean(b for a, b in pk_)
    ratios_late[k] = m6 / mk if mk else float("nan")
    print("k=%d n=%d mean_k %.3f mean_6 %.3f ratio %.3f (linear %.3f)"
          % (k, len(pk_), mk, m6, ratios_late[k], 6.0 / k))

print()
print("=== APPLY the measured multiplier to the lead's n=69 stratum ===")
def m(r):
    return r.get("milb") or {}
S = [r for r in rows
     if m(r).get("level_rank") == 5.0 and (m(r).get("age") or 0) >= 23.5
     and (m(r).get("ops_rel") is not None and m(r)["ops_rel"] < 0)]
tot_lin, tot_emp, tot_emp_late, n = 0.0, 0.0, 0.0, 0
skipped = 0
for r in S:
    if r["kind"] == "bust":
        skipped += 1
        continue
    k = r.get("observed_seasons") or 6
    v = r["target_resolved"]
    tot_lin += v * (6.0 / k)
    tot_emp += v * ratios.get(k, 6.0 / k)
    tot_emp_late += v * ratios_late.get(k, 6.0 / k)
    n += 1
print("debuted rows n=%d (busts excluded: %d, their 0.0 label is hardcoded)" % (n, skipped))
print("  linear (dataset's target_censored logic) mean-6yr : %.3f" % (tot_lin / n))
print("  empirical multiplier, all elapsed debuts          : %.3f" % (tot_emp / n))
print("  empirical multiplier, late debuts (age>=24)       : %.3f" % (tot_emp_late / n))

import value_framework as vf
for lbl, v in (("raw partial sums (the lead's 0.494)", 0.4942),
               ("linear extrapolation", tot_lin / n),
               ("empirical, all", tot_emp / n),
               ("empirical, late debuts", tot_emp_late / n),
               ("elapsed-window rows only (n=9)", 1.8878)):
    print("  implied FV @ %-38s %.3f -> %.2f"
          % (lbl, v, vf.realized_implied_fv(v, False, age=31.0, position="CF",
                                            exposure_seasons=6)))
