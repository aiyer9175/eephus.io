"""RECONCILE: does the served dollar level follow the CONFIG $/WAR or the
calibration's ERA-TARGET convention? Refit the level map under each
(prediction level x era target) cell and reprice the served board."""
import sys, json, copy
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import numpy as np, value_framework as vf
import surplus_backtest_real as sbr, backtest as bt
cfg = vf._config(); ORIG = copy.deepcopy(cfg)
def restore(): cfg.clear(); cfg.update(copy.deepcopy(ORIG)); vf._reset_derived_caches()
def set_level(fa):
    restore()
    if fa:
        cfg["dollars_per_war"]["fa_implied"]["enabled"] = True
        vf._apply_fa_implied_reanchor(cfg)
    vf._reset_derived_caches()
CUR = {int(k): dict(v) for k, v in ORIG["historical_dollars_per_war"].items()}
FASER = {int(k): float(v)/1e6 for k, v in
         json.loads((HERE/"data"/"fa_dpw_series.json").read_text())["usd_per_war_by_winter"].items()}
def fa_era():
    out = {}; base = CUR[min(CUR)]
    for y, row in CUR.items():
        t = FASER.get(y) or FASER[min(FASER, key=lambda z: abs(z-y))]
        s = t/float(row["overall"]); out[y] = {k: float(v)*s for k, v in row.items()}
    for y, v in FASER.items():
        if y not in out:
            s = v/float(base["overall"]); out[y] = {k: float(x)*s for k, x in base.items()}
    return out
FAT = fa_era()
board = json.loads((HERE/"data"/"xfv.json").read_text())["by_player"]
gr = [(v["xfv_grade_quantile"], v.get("side") == "P") for v in board.values()
      if v.get("surplus_mm") is not None and v.get("xfv_grade_quantile") is not None]
print(f"{'pred level':>14s} {'era target':>11s} | {'slope':>7s} {'icept':>7s} {'raw agg':>9s} {'SERVED agg':>11s} {'vs prod':>9s}")
print("-"*74)
base_served = None
for lname, fa in (("curated 11.74", False), ("fa_impl 14.89", True)):
    for ename, tbl in (("curated", CUR), ("fa_implied", FAT)):
        set_level(fa)
        recs, _ = sbr.build_cohorts()
        rep = bt.run_backtest(sbr._resolved_only(recs), discount_rate=float(cfg["discount_rate"]),
                              dpw_by_year={k: dict(v) for k, v in tbl.items()},
                              correction_method="isotonic_binned")
        s = float(rep["raw_calibration"]["slope"]); i = float(rep["raw_calibration"]["intercept"])
        raw = np.array([(vf.expected_surplus_usd(g, p, None) or 0.0)/1e6 for g, p in gr])
        served = np.maximum(0.0, s*raw + i)
        if base_served is None: base_served = served.sum()
        print(f"{lname:>14s} {ename:>11s} | {s:7.4f} {i:7.3f} {raw.sum():9,.0f} {served.sum():11,.0f} "
              f"{100*(served.sum()/base_served-1):+8.2f}%")
restore()
