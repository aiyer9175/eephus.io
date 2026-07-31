"""Lane: divergence-origin (e). Is the fa_implied LEVEL move absorbable by the
shipped LINEAR surplus calibration?

Why this is the decisive test. surplus_backtest_real prices the PREDICTION side
at the standing config's $/WAR and the REALIZED (target) side at
historical_dollars_per_war (surplus_backtest_real.py:43-48, 251-252). So a level
move shifts predictions and NOT targets, and the refit calibration slope must
absorb it. The shipped map is corrected = max(0, a*raw - b), a single global
slope: if the level move were a uniform scale k on raw, then a' = a/k restores
served dollars EXACTLY and the whole reconciliation is a no-op on the board.

It is NOT a uniform scale, because surplus = value - salary and the arb salary is
itself a fraction of market value while league-min is not. This measures the
RESIDUAL TILT the linear map cannot absorb -- the only thing the direction choice
can actually buy or cost on served dollars.

Read-only: mutates only the in-process cached config dict."""
import json, sys, statistics
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import value_framework as vf

GRID = [35, 40, 45, 50, 55, 60, 65, 70]

def curve():
    return {fv: {"hit": vf.surplus_value_mm(fv, False),
                 "pit": vf.surplus_value_mm(fv, True)} for fv in GRID}

base = curve()

cfg = vf._config()
cfg["dollars_per_war"]["fa_implied"] = {"enabled": True, "trailing_years": 3}
vf._apply_fa_implied_reanchor(cfg)
vf._reset_derived_caches()
k_level = cfg["dollars_per_war"]["_fa_reanchor"]["scale"]
on = curve()

rows = []
for fv in GRID:
    for role in ("hit", "pit"):
        b, o = base[fv][role], on[fv][role]
        if b > 0:
            rows.append((fv, role, b, o, o / b))

ratios = [r[4] for r in rows]
k_fit = statistics.mean(ratios)          # the uniform scale the linear map WOULD absorb
print(f"config re-anchor scale (level)            k = {k_level:.4f}")
print(f"mean surplus ratio across the FV grid   k_s = {k_fit:.4f}")
print(f"\nAfter refitting the linear map by 1/k_s, the RESIDUAL per-FV move is:\n")
print(f"{'FV':>4} {'role':>5} {'prod $M':>10} {'reanch $M':>10} {'ratio':>7} {'residual':>9}")
resid = []
for fv, role, b, o, r in rows:
    res = r / k_fit - 1.0
    resid.append(abs(res))
    print(f"{fv:>4} {role:>5} {b:>10.1f} {o:>10.1f} {r:>7.4f} {res:>+8.1%}")
print(f"\nmax |residual| = {max(resid):.1%}   median |residual| = {statistics.median(resid):.1%}")
print("\nINTERPRETATION: the linear calibration absorbs the mean; only the residual")
print("column is a real change in served relative dollars once the map is refit.")
print("Sign of the residual at the TOP of the board is what the standing")
print("over-prediction objection cares about.")
