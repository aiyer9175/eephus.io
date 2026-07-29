"""RECONCILE (b)+(c) final: post-REFIT blast radius + the coherence trade test.
The level enters the calibration's slope, so the honest blast radius is measured
with the calibration REFIT per arm, not with the shipped map held fixed."""
import sys, json, copy
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import numpy as np, value_framework as vf
import surplus_backtest_real as sbr, backtest as bt, fa_market as fam

cfg = vf._config(); ORIG = copy.deepcopy(cfg)
def restore():
    cfg.clear(); cfg.update(copy.deepcopy(ORIG)); vf._reset_derived_caches()
def set_arm(fa_on, infl=None, disc=None):
    restore()
    if fa_on:
        cfg["dollars_per_war"]["fa_implied"]["enabled"] = True
        vf._apply_fa_implied_reanchor(cfg)
    if infl is not None: cfg["dollars_per_war_inflation"] = infl
    if disc is not None: cfg["discount_rate"] = disc
    vf._reset_derived_caches()

CUR = {int(k): dict(v) for k, v in ORIG["historical_dollars_per_war"].items()}
board = json.loads((HERE/"data"/"xfv.json").read_text())["by_player"]
rows = [(k, v) for k, v in board.items()
        if v.get("surplus_mm") is not None and v.get("xfv_grade_quantile") is not None]
grades = [(v["xfv_grade_quantile"], v.get("side") == "P") for _, v in rows]
names = [k for k, _ in rows]

def refit_slope():
    """Refit the level map for the CURRENT arm on realized outcomes (OLS realized~pred)."""
    recs, _ = sbr.build_cohorts()
    rep = bt.run_backtest(sbr._resolved_only(recs), discount_rate=float(cfg["discount_rate"]),
                          dpw_by_year={k: dict(v) for k, v in CUR.items()},
                          correction_method="isotonic_binned")
    rc = rep["raw_calibration"]
    return float(rc["slope"]), float(rc["intercept"])

def raw_board():
    return np.array([(vf.expected_surplus_usd(g, p, None) or 0.0)/1e6 for g, p in grades])

ARMS = [("A production", False, None, None),
        ("B fa_implied", True, None, None),
        ("C +infl .0483", True, 0.0483099, None),
        ("D coherent gross", True, 0.0483099, 0.10)]
print(f"{'arm':17s} {'flat$M':>7s} {'refit slope':>11s} {'icept':>7s} {'RAW agg$M':>11s} {'REFIT agg$M':>12s} {'vs A':>8s}")
print("-"*82)
res = {}
for nm, fa, infl, disc in ARMS:
    set_arm(fa, infl, disc)
    s, i = refit_slope(); rb = raw_board()
    cal = np.maximum(0.0, s*rb + i)
    res[nm] = (cfg["dollars_per_war"]["flat"], s, i, rb.sum(), cal.sum(), cal)
    baseagg = res["A production"][4]
    print(f"{nm:17s} {cfg['dollars_per_war']['flat']/1e6:7.2f} {s:11.4f} {i:7.3f} {rb.sum():11,.0f} {cal.sum():12,.0f} {100*(cal.sum()/baseagg-1):+7.2f}%")

print("\nPOST-REFIT per-player movement vs arm A:")
A = res["A production"][5]
for nm in ("B fa_implied", "C +infl .0483", "D coherent gross"):
    d = res[nm][5] - A
    print(f"  {nm:17s} mean {d.mean():+.3f}M  median {np.median(d):+.3f}M  p95 {np.percentile(d,95):+.3f}M  "
          f"max {d.max():+.3f}M  |d|>1M {(np.abs(d)>1).sum()}")
    idx = np.argsort(-np.abs(d))[:5]
    print("      movers: " + ", ".join(f"{names[i]} {A[i]:.1f}->{res[nm][5][i]:.1f}" for i in idx))

# ---------------- COHERENCE TRADE TEST ----------------
print("\n" + "="*78)
print("COHERENCE TEST: net an FA-priced asset against a prospect-priced asset.")
print("Trade: club receives a FA-signed veteran on a 6yr/2.5-WAR path;")
print("       club sends a prospect whose control window is that SAME 6yr/2.5-WAR path.")
print("A coherent platform values the two production streams IDENTICALLY (ratio 1.000).")
SER = {int(k): float(v) for k, v in
       json.loads((HERE/"data"/"fa_dpw_series.json").read_text())["usd_per_war_by_winter"].items()}
CY = 2027; DPW = fam.winter_dpw(SER, CY); DEST = fam._destale_rate(SER, CY)
print(f"\n{'arm':17s} {'FA value $M':>12s} {'prospect $M':>12s} {'ratio':>7s} {'gap $M':>10s}")
print("-"*64)
for nm, fa, infl, disc in ARMS:
    set_arm(fa, infl, disc)
    for wr, yrs in [(2.5, 6)]:
        W = [wr]*yrs
        fav = fam.rational_value_usd(W, CY, DPW, infl=DEST)/1e6
        r = cfg["discount_rate"]; g = cfg["dollars_per_war_inflation"]
        pv = sum(vf.tiered_war_value_usd(w)*((1+g)**t)/((1+r)**t) for t, w in enumerate(W))/1e6
        print(f"{nm:17s} {fav:12,.1f} {pv:12,.1f} {fav/pv:7.4f} {fav-pv:+10,.1f}")
print("\nSame test across WAR levels and horizons (arm A vs arm C):")
for nm in ("A production", "C +infl .0483"):
    fa_, infl, disc = (False, None, None) if nm.startswith("A") else (True, 0.0483099, None)
    set_arm(fa_, infl, disc)
    print(f"  {nm}:")
    for wr in (1.5, 2.5, 4.0):
        line = []
        for yrs in (3, 6, 7):
            W = [wr]*yrs
            fav = fam.rational_value_usd(W, CY, DPW, infl=DEST)/1e6
            r = cfg["discount_rate"]; g = cfg["dollars_per_war_inflation"]
            pv = sum(vf.tiered_war_value_usd(w)*((1+g)**t)/((1+r)**t) for t, w in enumerate(W))/1e6
            line.append(f"{yrs}yr {fav/pv:.4f}")
        print(f"    {wr} WAR/yr: " + "  ".join(line))
restore()
