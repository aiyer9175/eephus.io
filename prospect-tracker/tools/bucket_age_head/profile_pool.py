# Bucket-head gate: pool profiling (read-only against the repo).
import bisect
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

REPO = Path(r"C:/Users/noah/baseball-projects/BaseballR/prospect-tracker")
sys.path.insert(0, str(REPO))

import value_framework as vf  # noqa: E402

BUCKETS = ("bust", "bench", "regular", "good", "star")
BUCKET_EDGES = (0.5, 1.5, 2.5, 4.0)
TARGET_SEASONS = 6.0
AGE_BANDS = ("le22", "23_24", "25p")


def tier(fv):
    return int(round(fv / 5) * 5)


def age_band(age):
    if age is None:
        return None
    a = float(age)
    if a < 23.0:
        return "le22"
    if a < 25.0:
        return "23_24"
    return "25p"


def age_decision(r):
    """Age at the decision cutoff. birth_date preferred (exact); fallback =
    milb.age (season age) advanced by the cutoff-vs-season staleness."""
    bd, cut = r.get("birth_date"), r.get("cutoff")
    if bd and cut:
        try:
            b = date.fromisoformat(str(bd)[:10])
            c = date.fromisoformat(str(cut)[:10])
            return round((c - b).days / 365.25, 2)
        except ValueError:
            pass
    m = r.get("milb") or {}
    if m.get("age") is not None and not m.get("age_missing"):
        try:
            cy = int(str(cut)[:4])
            adj = max(0, cy - int(m.get("milb_season") or cy))
            return float(m["age"]) + adj
        except (TypeError, ValueError):
            return float(m["age"])
    return None


def decision_year(r):
    if r["kind"] == "debuted":
        return int(r["debut_year"])
    c = r.get("cutoff") or ""
    return (int(c[:4]) + 1) if c[:4].isdigit() else 2026


def realized_bucket(t):
    return bisect.bisect_right(BUCKET_EDGES, t / TARGET_SEASONS)


rows = json.loads((REPO / "data" / "xfv_pitcher_matrix.json").read_text(encoding="utf-8"))
pool = [r for r in rows
        if r.get("is_pitcher")
        and not (r["kind"] == "bust" and r.get("bust_recent"))
        and not r.get("censored")
        and r.get("consensus_fv_raw") is not None
        and r.get("target_resolved") is not None]

print("pool n:", len(pool), Counter(r["kind"] for r in pool))
print("weights:", Counter(round(float(r.get("weight", 1.0)), 2) for r in pool))
print("target_resolved == target_censored mismatches:",
      sum(1 for r in pool if abs(float(r["target_resolved"]) - float(r["target_censored"])) > 1e-9))

for r in pool:
    r["_dy"] = decision_year(r)
    r["_age"] = age_decision(r)
    r["_ab"] = age_band(r["_age"])
    r["_gb"] = tier(float(r["consensus_fv_raw"]))
    r["_y"] = realized_bucket(float(r["target_resolved"]))

print("\ndecision-year composition (kind):")
for y in sorted(set(r["_dy"] for r in pool)):
    sub = [r for r in pool if r["_dy"] == y]
    print(f"  {y}: n={len(sub)}  {dict(Counter(r['kind'] for r in sub))}  "
          f"age-known={sum(1 for r in sub if r['_age'] is not None)}")

print("\nage coverage:", Counter(r["_ab"] if r["_ab"] else "missing" for r in pool))
print("age coverage by kind:")
for k in ("debuted", "bust"):
    sub = [r for r in pool if r["kind"] == k]
    print(f"  {k}: {Counter(r['_ab'] if r['_ab'] else 'missing' for r in sub)}")

print("\ngrade band spread:", dict(sorted(Counter(r["_gb"] for r in pool).items())))

print("\ncells (grade_band x age_band), FULL resolved pool:")
cells = defaultdict(list)
for r in pool:
    if r["_ab"]:
        cells[(r["_gb"], r["_ab"])].append(r)
for gb in sorted(set(k[0] for k in cells)):
    for ab in AGE_BANDS:
        grp = cells.get((gb, ab))
        if not grp:
            continue
        cnt = Counter(r["_y"] for r in grp)
        dist = [round(cnt.get(i, 0) / len(grp), 3) for i in range(5)]
        print(f"  fv{gb:>3} {ab:>5}: n={len(grp):>4} p_bucket_emp={dist}")

# band-empirical Moore cell: grade band 45, age 25+
grp = cells.get((45, "25p"), [])
if grp:
    print(f"\nMoore cell (fv45, 25+): n={len(grp)}, "
          f"emp p_bust={sum(1 for r in grp if r['_y'] == 0)/len(grp):.3f}, "
          f"mean WAR6={sum(float(r['target_resolved']) for r in grp)/len(grp):.2f}")
for ab in AGE_BANDS:
    grp = cells.get((45, ab), [])
    if grp:
        print(f"  fv45 {ab}: n={len(grp)} mean WAR6="
              f"{sum(float(r['target_resolved']) for r in grp)/len(grp):.2f} "
              f"p_bust_emp={sum(1 for r in grp if r['_y'] == 0)/len(grp):.3f}")

# incumbent sanity: Moore's numbers
for g in (45.0, 45.8, 48.0):
    p = vf.p_bucket_given_fv(g, True)
    print(f"incumbent p_bucket(fv={g}, pit): bust={p[0]:.3f} bench={p[1]:.3f} "
          f"reg={p[2]:.3f} good={p[3]:.3f} star={p[4]:.3f}")

# fold guards check (forward chain 2020-2023)
for y in (2020, 2021, 2022, 2023):
    tr = [r for r in pool if r["_dy"] < y]
    te = [r for r in pool if r["_dy"] == y]
    te_age = [r for r in te if r["_ab"] is not None]
    te_25p = [r for r in te if r["_ab"] == "25p"]
    print(f"fold {y}: train={len(tr)} test={len(te)} "
          f"test_age_known={len(te_age)} test_25p={len(te_25p)} "
          f"test_kinds={dict(Counter(r['kind'] for r in te))}")
