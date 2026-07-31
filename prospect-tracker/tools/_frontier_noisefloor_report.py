# SCRATCH (not shipped): render the noise-floor tables from the run artifact.
from __future__ import annotations

import json
import sys
from pathlib import Path

P = Path(sys.argv[1])
d = json.loads(P.read_text("utf-8"))


def f(x, nd=4):
    return "na" if x is None else f"{x:+.{nd}f}"


print("=" * 100)
print("(a) PAIRED BOOTSTRAP (resample train AND test, refit ridge+OLS each draw)")
print("=" * 100)
hdr = f"{'combo':22s} {'n':>5s} {'stat':>14s} {'point':>9s} {'boot mean':>10s} {'sd':>8s} {'CI95':>21s} {'P(>0)':>7s}"
print(hdr)
for k, r in d.items():
    pt, bo = r["point"], r["boot"]
    tag = f"{k} lam={r['lam']}"
    for stat in ("rho_base", "rho_ridge", "rho_blend", "d_rho_ridge", "d_rho_blend",
                 "mae_base", "mae_ridge", "mae_blend", "d_mae_ridge", "d_mae_blend",
                 "t45_blend"):
        b = bo.get(stat, {})
        if not b.get("n_draws"):
            continue
        print(f"{tag:22s} {pt['n']:5d} {stat:>14s} {pt[stat]:+9.4f} {b['mean']:+10.4f} "
              f"{b['sd']:8.4f} [{b['ci95'][0]:+.4f},{b['ci95'][1]:+.4f}] {b['p_gt0']:7.3f}")
        tag = ""
    print("-" * 100)

print()
print("=" * 100)
print("(b) PERMUTATION NULL - train target (+its KM weight) shuffled, refit")
print("=" * 100)
print(f"{'combo':22s} {'stat':>14s} {'null mean':>10s} {'null sd':>9s} {'null p95':>9s} {'null CI95':>21s} {'REAL':>9s}")
for k, r in d.items():
    nl, pt = r["null_shuffled_train_target"], r["point"]
    tag = k
    for stat in ("rho_base", "rho_ridge", "rho_blend", "d_rho_ridge", "d_rho_blend", "t45_blend"):
        b = nl.get(stat, {})
        if not b.get("n_draws"):
            continue
        print(f"{tag:22s} {stat:>14s} {b['mean']:+10.4f} {b['sd']:9.4f} {b['p95']:+9.4f} "
              f"[{b['ci95'][0]:+.4f},{b['ci95'][1]:+.4f}] {pt[stat]:+9.4f}")
        tag = ""
    print("-" * 100)

print()
print("=" * 100)
print("(c) MINIMUM DETECTABLE EFFECT  (MDE95 = 1.645 * bootstrap sd of the delta)")
print("=" * 100)
print(f"{'combo':22s} {'quantity':>24s} {'point':>9s} {'boot sd':>9s} {'MDE95':>9s} {'null p95':>9s} {'P(>0)':>7s}")
for k, r in d.items():
    bo, nl, pt = r["boot"], r["null_shuffled_train_target"], r["point"]
    tag = k
    quants = [q for q in bo if q.startswith(("d_rho_", "dfeat_rho_", "dfeat_t45_", "dlam_rho_",
                                             "dfeat_rhoridge_", "dlam_t45_"))]
    for q in quants:
        b = bo[q]
        n95 = nl.get(q, {}).get("p95")
        print(f"{tag:22s} {q:>24s} {pt.get(q, float('nan')):+9.4f} {b['sd']:9.4f} "
              f"{1.645*b['sd']:9.4f} {('%+.4f' % n95) if n95 is not None else 'na':>9s} {b['p_gt0']:7.3f}")
        tag = ""
    print("-" * 100)

print()
print("=" * 100)
print("(b2) PLACEBO-FEATURE NULL - the SAME column, values permuted across rows")
print("     (identical marginal distribution, zero information) -> apparent gain from adding it")
print("=" * 100)
print(f"{'combo':22s} {'feature':>14s} {'metric':>10s} {'null mean':>10s} {'null sd':>9s} "
      f"{'null p95':>9s} {'REAL add':>9s}")
for k, r in d.items():
    pl, pt = r["null_placebo_feature"], r["point"]
    tag = k
    for feat, blk in pl.items():
        for mk, real_key in (("pooled_rho", f"dfeat_rho_{feat}"), ("t45", f"dfeat_t45_{feat}")):
            b = blk[mk]
            print(f"{tag:22s} {feat:>14s} {mk:>10s} {b['mean']:+10.4f} {b['sd']:9.4f} "
                  f"{b['p95']:+9.4f} {pt.get(real_key, float('nan')):+9.4f}")
            tag = ""
    print("-" * 100)
