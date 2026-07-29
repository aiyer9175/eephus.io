"""RECONCILE (d): REALIZED-OUTCOME validation of the $/WAR level.
Runs surplus_backtest_real under each $/WAR arm, persist=False (writes nothing).
NOTE the offset discovered by this lane: imputed ARB SALARIES scale with
vf.tiered_war_value_usd (surplus_backtest_real.py:181), so raising $/WAR raises
BOTH the value of wins and the imputed salary. The realized target is NOT fixed.
Realized win VALUE is priced at ERA rates (backtest.realized_sv_pv <- historical
_dollars_per_war), so only the salary leg moves on the target side."""
import sys, json, copy, time
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import numpy as np, value_framework as vf
import surplus_backtest_real as sbr, backtest as bt

cfg = vf._config(); ORIG = copy.deepcopy(cfg)
def restore():
    cfg.clear(); cfg.update(copy.deepcopy(ORIG)); vf._reset_derived_caches()
def set_arm(fa_on, infl, disc=None):
    restore()
    if fa_on:
        cfg["dollars_per_war"]["fa_implied"]["enabled"] = True
        vf._apply_fa_implied_reanchor(cfg)
    cfg["dollars_per_war_inflation"] = infl
    if disc is not None: cfg["discount_rate"] = disc
    vf._reset_derived_caches()

DESTALE = 0.0483099
ARMS = [("A_production",      False, 0.0,     0.07),
        ("B_fa_implied",      True,  0.0,     0.07),
        ("C_fa_plus_infl",    True,  DESTALE, 0.07),
        ("D_coherent_gross",  True,  DESTALE, 0.10)]

out = {}
for name, fa_on, infl, disc in ARMS:
    t0 = time.time(); set_arm(fa_on, infl, disc)
    dpwy = {int(k): dict(v) for k, v in (cfg.get("historical_dollars_per_war") or {}).items()}
    recs, acct = sbr.build_cohorts()
    res = sbr._resolved_only(recs)
    rep = bt.run_backtest(res, discount_rate=float(cfg["discount_rate"]),
                          dpw_by_year=dpwy, correction_method="isotonic_binned")
    out[name] = {"flat": cfg["dollars_per_war"]["flat"], "infl": infl, "disc": disc,
                 "n_resolved": len(res), "report": rep, "secs": round(time.time()-t0,1)}
    print(f"{name}: flat {cfg['dollars_per_war']['flat']:,.0f} n={len(res)} {time.time()-t0:.0f}s", flush=True)
restore()
P = Path(r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
P.mkdir(parents=True, exist_ok=True)
(P/"recon_valid.json").write_text(json.dumps(out, default=str, indent=1))
print("WROTE", P/"recon_valid.json")
