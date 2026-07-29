"""Lane: prospect. CANDIDATE F-PROD: the farm_grades validation prices its
"surplus mass" with vf.point_estimate_surplus_usd, whose own docstring says
"COLLAPSED comparator (NOT the production path). Mirrors the v1 mistake of
aggregating BEFORE the nonlinear transforms". Every served surface (trade
machine, proj_export, storage, eFV) prices with vf.surplus_value_mm.

Measure: does the PRODUCTION surplus rank orgs better than the comparator, and
does either beat the count / FV50+ baselines? Same protocol, same rows,
paired cluster bootstrap over orgs.
"""
import statistics, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import value_framework as vf
from source_backtest import _spearman
from farm_grade_backtest import _load, VINTAGE_YEARS, WINDOW, MIN_ORG_N

listings, cw, bio = _load()
by_ov = defaultdict(list)
for (pk, vy), li in listings.items():
    if li["org"]:
        by_ov[(li["org"], vy)].append((pk, li["fv"]))

KEYS = ("sur_collapsed", "sur_production", "sum_expected_war", "count", "count_fv50plus")
TAB = {}
for vy in VINTAGE_YEARS:
    rows = []
    for org in sorted({o for (o, y) in by_ov if y == vy}):
        members = by_ov[(org, vy)]
        if len(members) < MIN_ORG_N:
            continue
        d = dict.fromkeys(KEYS, 0.0)
        real = 0.0
        for pk, fv in members:
            b = bio.get(pk) or {}
            pos = b.get("position")
            is_pit = vf.is_pitcher_position(pos)
            s = vf.point_estimate_surplus_usd(fv, is_pit, pos)
            if s:
                d["sur_collapsed"] += s / 1e6
            sp = vf.surplus_value_mm(float(fv), is_pit, pos)
            if sp:
                d["sur_production"] += float(sp)
            d["sum_expected_war"] += vf.fv_to_6yr_avg_war(fv) or 0.0
            d["count"] += 1
            if fv >= 50:
                d["count_fv50plus"] += 1
            seasons = cw.get(pk) or {}
            debut = min(seasons) if seasons else None
            if debut is not None and vy <= debut <= vy + WINDOW:
                real += sum(w for y, w in seasons.items() if vy <= y <= vy + WINDOW)
        rows.append((org, d, real))
    TAB[vy] = rows

def score(key, sel=None):
    v = []
    for vy, rows in TAB.items():
        idx = list(range(len(rows))) if sel is None else sel[vy]
        r = _spearman([rows[i][1][key] for i in idx], [rows[i][2] for i in idx])
        if r is not None:
            v.append(r)
    return statistics.mean(v)

base = {k: score(k) for k in KEYS}
print("mean-of-5-vintage Spearman vs realized graduate WAR:")
for k, v in base.items():
    print(f"   {k:20s} {v:+.4f}")

rng = np.random.default_rng(20260725)
def boot(k1, k2, B=4000):
    out = np.empty(B)
    for b in range(B):
        sel = {vy: list(rng.integers(0, len(r), len(r))) for vy, r in TAB.items()}
        out[b] = score(k1, sel) - score(k2, sel)
    return out

print("\nPAIRED CLUSTER BOOTSTRAP over orgs (B=4000)")
for a, b in (("sur_production", "sur_collapsed"), ("sur_production", "count"),
             ("sur_production", "count_fv50plus"), ("sur_collapsed", "count_fv50plus")):
    d = boot(a, b)
    lo, hi = np.percentile(d, [2.5, 97.5])
    print(f"  {a} - {b:18s} obs={base[a]-base[b]:+.4f} mean={d.mean():+.4f} sd={d.std():.4f} "
          f"CI95=[{lo:+.4f},{hi:+.4f}] P(>0)={float((d>0).mean()):.3f} MDE95={1.96*d.std():.4f}")

print("\nPER-VINTAGE")
for vy, rows in TAB.items():
    ys = [r[2] for r in rows]
    print(f"  {vy} " + "  ".join(f"{k}={_spearman([r[1][k] for r in rows], ys):+.3f}" for k in KEYS))
