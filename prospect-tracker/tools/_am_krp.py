# Scratch lab (audit-mode, lane=plusmetrics), item (c): is KRP+ genuinely live?
from __future__ import annotations
import json, os, sys, math
import numpy as np
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
D = os.path.join(ROOT, "data")
import efv_score as ES
import efv_model as EM

served = json.load(open(os.path.join(D, "xfv_scored_live_pitcher.json"), encoding="utf-8"))
mat = json.load(open(os.path.join(D, "xfv_live_pitcher_matrix.json"), encoding="utf-8"))
mat = mat["rows"] if isinstance(mat, dict) and "rows" in mat else mat
by = {r["player_key"]: r for r in mat}

k = np.array([np.nan if r.get("krp_plus") is None else float(r["krp_plus"]) for r in served])
print(f"served pitcher rows      : {len(served)}")
print(f"krp_plus present         : {int((~np.isnan(k)).sum())}  missing {int(np.isnan(k).sum())}")
print(f"mean {np.nanmean(k):.3f}  pop-sd {np.nanstd(k):.3f}  min {np.nanmin(k):.1f}  max {np.nanmax(k):.1f}")
print(f"distinct values          : {len(set(k[~np.isnan(k)]))}")
print(f"unclamped below 40       : {int(np.nansum(k < 40))}   above 160: {int(np.nansum(k > 160))}")

# recompute display raw from the matrix and confirm the served pill matches
raws, keys = {}, []
elig = 0
for r in mat:
    m = r.get("milb") or {}
    ok = (m.get("era_rel") is not None and float(m.get("rates_missing", 1.0) or 0.0) == 0.0)
    if not ok:
        continue
    elig += 1
    raws[r["player_key"]] = ES._krp_display_raw(float(m["era_rel"]),
                                                float(m.get("k_rel") or 0.0))
print(f"\n_krp_eligible rows in matrix: {elig}  (served with a pill: {int((~np.isnan(k)).sum())})")
vals = np.array(list(raws.values()))
mu, sd = vals.mean(), vals.std()
recomp = {pk: 100 + 10 * (v - mu) / sd for pk, v in raws.items()}
diffs = []
for r in served:
    if r.get("krp_plus") is None:
        continue
    v = recomp.get(r["player_key"])
    if v is None:
        diffs.append(999.0)
    else:
        diffs.append(abs(round(v, 1) - float(r["krp_plus"])))
diffs = np.array(diffs)
print(f"served-vs-recomputed |diff|: max {diffs.max():.4f}  mean {diffs.mean():.6f}  "
      f"n exact {int((diffs < 1e-9).sum())}/{len(diffs)}")

# double-bad quadrant: is it spread, or flat at ~99.3 (the pre-H2 dead read)?
db, nb = [], []
for r in served:
    pk = r["player_key"]; mm = (by.get(pk) or {}).get("milb") or {}
    if r.get("krp_plus") is None or mm.get("era_rel") is None:
        continue
    er = float(mm["era_rel"]); kr = float(mm.get("k_rel") or 0.0)
    (db if (er > 0 and kr < 0) else nb).append(float(r["krp_plus"]))
db, nb = np.array(db), np.array(nb)
print(f"\ndouble-bad quadrant  n={len(db)}  mean {db.mean():7.2f}  sd {db.std(ddof=1):6.2f}"
      f"  min {db.min():.1f}  max {db.max():.1f}  distinct {len(set(db))}")
print(f"rest of pool         n={len(nb)}  mean {nb.mean():7.2f}  sd {nb.std(ddof=1):6.2f}")

# does the MODEL feature still see the zeroed quadrant?
mz = [EM._x_era_k(float((by[r['player_key']].get('milb') or {}).get('era_rel') or 0.0),
                  float((by[r['player_key']].get('milb') or {}).get('k_rel') or 0.0))
      for r in served if r['player_key'] in by]
mz = np.array(mz)
print(f"\nMODEL x_era_k exact zeros: {int((mz == 0.0).sum())}/{len(mz)}  "
      f"(display decouple is working iff this is large AND the pill above is spread)")

# is KRP+ redundant with the served eFV grade it is displayed beside?
g = np.array([float(r["xfv_grade_display"]) for r in served if r.get("krp_plus") is not None
              and r.get("xfv_grade_display") is not None])
kk = np.array([float(r["krp_plus"]) for r in served if r.get("krp_plus") is not None
               and r.get("xfv_grade_display") is not None])
print(f"\nrho(KRP+, served eFV grade) = {stats.spearmanr(kk, g).statistic:+.4f}  n={len(g)}")
era = np.array([float((by[r['player_key']].get('milb') or {}).get('era_rel'))
                for r in served if r.get('krp_plus') is not None
                and (by.get(r['player_key']) or {}).get('milb', {}).get('era_rel') is not None])
kp2 = np.array([float(r['krp_plus']) for r in served if r.get('krp_plus') is not None
                and (by.get(r['player_key']) or {}).get('milb', {}).get('era_rel') is not None])
print(f"rho(KRP+, era_rel)          = {stats.spearmanr(kp2, era).statistic:+.4f}  n={len(era)}")
