"""Lane: prospect. (a) DERIVE THE MISSING FLOOR for the farm_grades claim.

Re-implements the farm_grade_backtest scoring loop but keeps the per-org
(pred, realized) table so the sampling unit (ORG within vintage) can be
bootstrapped. Reports:
  - mean-of-5-vintage Spearman for every candidate ranking
  - paired cluster bootstrap of the DIFFERENCE vs the count baseline and vs the
    FV50+ depth baseline (refit rank correlation each draw)
  - a row-permuted zero-information twin of the candidate column
  - a permutation null band
"""
import json, statistics, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import storage, value_framework as vf
from source_backtest import _spearman
from farm_grade_backtest import (_load, VINTAGE_YEARS, WINDOW, MIN_ORG_N)

listings, cw, bio = _load()
by_ov = defaultdict(list)
for (pk, vy), li in listings.items():
    if li["org"]:
        by_ov[(li["org"], vy)].append((pk, li["fv"]))

KEYS = ("sum_surplus_mm", "sum_expected_war", "count", "count_fv50plus")
TAB = {}   # vintage -> list of (org, {key: pred}, realized)
for vy in VINTAGE_YEARS:
    rows = []
    for org in sorted({o for (o, y) in by_ov if y == vy}):
        members = by_ov[(org, vy)]
        if len(members) < MIN_ORG_N:
            continue
        sur = war6 = cnt50 = real = 0.0
        for pk, fv in members:
            b = bio.get(pk) or {}
            is_pit = vf.is_pitcher_position(b.get("position"))
            s = vf.point_estimate_surplus_usd(fv, is_pit, b.get("position"))
            if s:
                sur += s / 1e6
            war6 += vf.fv_to_6yr_avg_war(fv) or 0.0
            if fv >= 50:
                cnt50 += 1
            seasons = cw.get(pk) or {}
            debut = min(seasons) if seasons else None
            if debut is not None and vy <= debut <= vy + WINDOW:
                real += sum(w for y, w in seasons.items() if vy <= y <= vy + WINDOW)
        rows.append((org, {"sum_surplus_mm": sur, "sum_expected_war": war6,
                           "count": float(len(members)), "count_fv50plus": cnt50},
                     real))
    TAB[vy] = rows

def mean_rho(sel=None, col_override=None):
    out = []
    for vy, rows in TAB.items():
        idx = range(len(rows)) if sel is None else sel[vy]
        ys = [rows[i][2] for i in idx]
        xs = [col_override(rows[i]) for i in idx] if col_override else None
        out.append((xs, ys))
    return out

def score(key, sel=None, override=None):
    vals = []
    for vy, rows in TAB.items():
        idx = list(range(len(rows))) if sel is None else sel[vy]
        ys = [rows[i][2] for i in idx]
        xs = ([override[vy][j] for j in range(len(idx))] if override is not None
              else [rows[i][1][key] for i in idx])
        r = _spearman(xs, ys)
        if r is not None:
            vals.append(r)
    return statistics.mean(vals) if vals else None

print("orgs per vintage:", {vy: len(r) for vy, r in TAB.items()})
base = {k: score(k) for k in KEYS}
print("mean-of-5-vintage Spearman:", {k: round(v, 4) for k, v in base.items()})

rng = np.random.default_rng(20260725)
B = 4000
def boot_delta(k1, k2, B=B):
    out = np.empty(B)
    for b in range(B):
        sel = {vy: list(rng.integers(0, len(rows), len(rows))) for vy, rows in TAB.items()}
        out[b] = score(k1, sel) - score(k2, sel)
    return out

print("\nPAIRED CLUSTER BOOTSTRAP over orgs (B=%d), refit rho each draw" % B)
for k2 in ("count", "count_fv50plus", "sum_expected_war"):
    d = boot_delta("sum_surplus_mm", k2)
    lo, hi = np.percentile(d, [2.5, 97.5])
    print(f"  surplus_mass - {k2:16s} obs={base['sum_surplus_mm']-base[k2]:+.4f} "
          f"mean={d.mean():+.4f} sd={d.std():.4f} CI95=[{lo:+.4f},{hi:+.4f}] "
          f"P(>0)={float((d>0).mean()):.3f}  MDE95={1.96*d.std():.4f}")

print("\nZERO-INFORMATION CONTROL (row-permuted surplus column, per vintage)")
ctrl = {}
for vy, rows in TAB.items():
    v = [r[1]["sum_surplus_mm"] for r in rows]
    rng.shuffle(v)
    ctrl[vy] = v
print("  permuted surplus mean rho =", round(score(None, override=ctrl), 4),
      " vs real", round(base["sum_surplus_mm"], 4))

print("\nPERMUTATION NULL BAND (B=2000)")
nulls = []
for b in range(2000):
    ov = {}
    for vy, rows in TAB.items():
        v = [r[1]["sum_surplus_mm"] for r in rows]
        rng.shuffle(v); ov[vy] = v
    nulls.append(score(None, override=ov))
nulls = np.array(nulls)
print(f"  null mean rho={nulls.mean():+.4f} CI95=[{np.percentile(nulls,2.5):+.4f},"
      f"{np.percentile(nulls,97.5):+.4f}]  p_emp(real >= null)="
      f"{float((nulls >= base['sum_surplus_mm']).mean()):.4f}")

print("\nPER-VINTAGE (the >=4 independent time splits)")
for vy, rows in TAB.items():
    ys = [r[2] for r in rows]
    line = {k: round(_spearman([r[1][k] for r in rows], ys), 4) for k in KEYS}
    print(f"  {vy} n_orgs={len(rows):3d} {line}")
