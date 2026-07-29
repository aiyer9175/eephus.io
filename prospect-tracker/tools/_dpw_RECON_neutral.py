"""RECONCILE (d) part 2: is the realized-outcome test NEUTRAL between the two levels?
The first run priced the TARGET at the CURATED era table -- the same family as the
production config level -- so it cannot be read as independent evidence for the
curated level. Here the prediction level and the target era-series are varied
INDEPENDENTLY (2x2), which is the only way to tell a real result from a definitional one.
Noise floor: player-resampled bootstrap with a full REFIT of the OLS level slope per draw.
Zero-info control: shuffle realized against predicted. Permutation null on the arm CONTRAST."""
import sys, json, copy
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import numpy as np, value_framework as vf
import surplus_backtest_real as sbr, backtest as bt

cfg = vf._config(); ORIG = copy.deepcopy(cfg)
def restore():
    cfg.clear(); cfg.update(copy.deepcopy(ORIG)); vf._reset_derived_caches()
def set_level(fa_on):
    restore()
    if fa_on:
        cfg["dollars_per_war"]["fa_implied"]["enabled"] = True
        vf._apply_fa_implied_reanchor(cfg)
    vf._reset_derived_caches()

CUR = {int(k): dict(v) for k, v in ORIG["historical_dollars_per_war"].items()}
FASER = {int(k): float(v)/1e6 for k, v in
         json.loads((HERE/"data"/"fa_dpw_series.json").read_text())["usd_per_war_by_winter"].items()}
def fa_era_table():
    """Era table on the FA-implied series: scale every curated row so `overall`
    equals that winter's FA-implied rate (tier ratios preserved)."""
    out = {}
    for y, row in CUR.items():
        tgt = FASER.get(y)
        if tgt is None:
            yrs = sorted(FASER); tgt = FASER[min(yrs, key=lambda z: abs(z-y))]
        s = tgt/float(row["overall"])
        out[y] = {k: float(v)*s for k, v in row.items()}
    # extend to the FA series' own earlier winters so pre-2020 stops falling back
    base = CUR[min(CUR)]
    for y, v in FASER.items():
        if y not in out:
            s = v/float(base["overall"]); out[y] = {k: float(x)*s for k, x in base.items()}
    return out
FAT = fa_era_table()

def run(fa_level, era):
    set_level(fa_level)
    recs, _ = sbr.build_cohorts()
    res = sbr._resolved_only(recs)
    tbl = CUR if era == "curated" else FAT
    rep = bt.run_backtest(res, discount_rate=float(cfg["discount_rate"]),
                          dpw_by_year={k: dict(v) for k, v in tbl.items()},
                          correction_method="isotonic_binned")
    preds = np.array([p["predicted_sv_mm"] for p in rep["_preds"]]) if "_preds" in rep else None
    return rep

print(f"{'pred level':>14s} {'era target':>10s} | {'slope':>7s} {'ci90':>18s} {'bias':>8s} {'rmse':>8s}")
print("-"*72)
cells = {}
for lvl_name, fa_lvl in (("curated 11.74", False), ("fa_impl 14.89", True)):
    for era in ("curated", "fa_implied"):
        rep = run(fa_lvl, era)
        rc = rep["raw_calibration"]; ci = rep["raw_calibration_slope_ci90"]; er = rep["raw_errors"]
        cells[(lvl_name, era)] = (rc["slope"], ci, er["bias"], er["rmse"])
        print(f"{lvl_name:>14s} {era:>10s} | {rc['slope']:7.4f} [{ci[0]:6.4f},{ci[1]:6.4f}] {er['bias']:8.3f} {er['rmse']:8.3f}")
restore()
P = Path(r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
(P/"recon_neutral.json").write_text(json.dumps({f"{k[0]}|{k[1]}": v for k, v in cells.items()}, default=str, indent=1))
print("\nWROTE", P/"recon_neutral.json")
