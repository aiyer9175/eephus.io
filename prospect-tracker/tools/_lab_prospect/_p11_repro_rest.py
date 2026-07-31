"""Lane: prospect. (a) reproduce the remaining registered claims. persist=False."""
import json, sys, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))

def hdr(s):
    print("\n" + "=" * 76 + "\n" + s + "\n" + "=" * 76)

# ---------------------------------------------------------------- surplus ---
hdr("prospect_surplus  (data/surplus_backtest_real.json)")
try:
    import surplus_backtest_real as sbr
    t = time.time(); rep = sbr.run(persist=False)
    old = L("surplus_backtest_real.json")
    print("re-run %.1fs" % (time.time() - t))
    def dig(d, *ks):
        for k in ks:
            d = (d or {}).get(k)
        return d
    for path in [("full_pool", "n_players"),
                 ("full_pool", "binned_calibration", "slope"),
                 ("full_pool", "binned_calibration", "intercept"),
                 ("full_pool", "raw_calibration", "slope"),
                 ("full_pool", "raw_errors", "bias"),
                 ("full_pool", "raw_errors", "mae"),
                 ("full_pool", "raw_errors", "spearman")]:
        print(f"  {'.'.join(path):46s} old={dig(old,*path)!s:24s} new={dig(rep,*path)!s}")
    print("  new top-level keys:", list(rep.keys()))
except Exception:
    traceback.print_exc()

# ------------------------------------------------------- surplus calib fit ---
hdr("prospect_surplus v3 calibration curve (registry: FV40 $1.5M / 45 $6.9M / 50 $17.9M / 55 $31.9M / 60 $65.6M hitters)")
try:
    import value_framework as vf
    for fv in (40, 45, 50, 55, 60, 65, 70):
        s = vf.point_estimate_surplus_usd(float(fv), False, "SS")
        sp = vf.point_estimate_surplus_usd(float(fv), True, "SP")
        print(f"  FV{fv}  hitter ${(s or 0)/1e6:8.1f}M   pitcher ${(sp or 0)/1e6:8.1f}M")
    fit = L("surplus_calibration_fit.json")
    print("  surplus_calibration_fit.json:", json.dumps(fit)[:900])
except Exception:
    traceback.print_exc()

# --------------------------------------------------------------- star odds ---
hdr("star_odds  (data/star_odds_eval.json)")
try:
    so = L("star_odds_eval.json")
    mx = 0.0; where = None
    for role, blk in (so.get("calibration", {}).get("roles") or {}).items():
        for t in blk.get("tiers", []):
            if t.get("abs_dev") is not None and t["abs_dev"] > mx:
                mx, where = t["abs_dev"], (role, t["tier"], t.get("published"), t.get("model"))
    print("  registry claim: max abs tier deviation about 0.64 (pitcher 70 FV), tolerance 0.1")
    print(f"  artifact max abs_dev = {mx:.4f} at {where}")
    print("  gate pass?", mx <= 0.1)
    print("  blocks:", list(so.keys()))
    rc = so.get("realized_calibration")
    if rc:
        print("  realized_calibration sample:", json.dumps(rc)[:1200])
except Exception:
    traceback.print_exc()

# ----------------------------------------------------------- positional -----
hdr("positional_ladder  (data/positional_ladder_eval.json)")
try:
    pl = L("positional_ladder_eval.json")
    print("  keys:", list(pl.keys()))
    print(json.dumps({k: v for k, v in pl.items()
                      if k in ("fit", "shipped_ladder", "accuracy_gate", "shape_gate",
                               "ladder", "coefficients", "held_out")}, indent=1)[:2500])
except Exception:
    traceback.print_exc()

# ------------------------------------------------------------ eta hazard ----
hdr("eta_hazard_lite  (data/eta_hazard_eval.json)")
try:
    eh = L("eta_hazard_eval.json")
    print("  pooled_debuted:", json.dumps(eh.get("pooled_debuted"), indent=1))
    print("  gate:", json.dumps(eh.get("gate") or eh.get("verdict") or {}, indent=1)[:900])
    print("  keys:", list(eh.keys()))
except Exception:
    traceback.print_exc()

# ------------------------------------------------------------------- dpw ----
hdr("fa_dpw_series  (data/dpw_forecast_eval.json)")
try:
    dp = L("dpw_forecast_eval.json")
    import statistics
    for m in ("flat5", "trend", "trend_cbt"):
        ap = [w[m]["ape"] for w in dp["per_winter"] if w.get(m)]
        print(f"  {m:10s} MAPE={statistics.mean(ap):.4f}  n={len(ap)}")
    print("  registry: flat-5% 0.102 BEAT fitted trend 0.122 and trend+CBT 0.132")
    print("  artifact summary block:", json.dumps({k: v for k, v in dp.items()
                                                   if k != "per_winter"}, indent=1)[:800])
except Exception:
    traceback.print_exc()
