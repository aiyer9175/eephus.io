"""RECONCILE (a): divergence re-derivation + switch arms. READ-ONLY on prod files.
HARNESS RULES (both cost time already this session):
  1. fa_market does `from value_framework import _config as _vf_config` -> binds the
     FUNCTION; the returned dict is SHARED. Mutate IN PLACE, call vf._reset_derived_caches().
     NEVER rebind vf._config (makes FA look like it moves when it does not).
  2. rational_value_usd(war_by_year, class_year, dpw_usd, infl) -- class_year is 2nd.
     Production passes infl=_destale_rate(series, class_year) EXPLICITLY (fa_export:399-411),
     not vf's dollars_per_war_inflation."""
import sys, json, copy
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import value_framework as vf, fa_market as fam

cfg = vf._config(); ORIG = copy.deepcopy(cfg)
SER = {int(k): float(v) for k, v in
       json.loads((HERE/"data"/"fa_dpw_series.json").read_text())["usd_per_war_by_winter"].items()}

def restore():
    cfg.clear(); cfg.update(copy.deepcopy(ORIG)); vf._reset_derived_caches()

def set_arm(fa_on, infl):
    restore()
    if fa_on:
        cfg["dollars_per_war"]["fa_implied"]["enabled"] = True
        vf._apply_fa_implied_reanchor(cfg)
    cfg["dollars_per_war_inflation"] = infl
    vf._reset_derived_caches()

CY = 2027
DESTALE = fam._destale_rate(SER, CY)
DPW = fam.winter_dpw(SER, CY)
print(f"winter_dpw({CY}) {DPW:,.2f}   destale {DESTALE:.7f}   vf_flat(prod) {ORIG['dollars_per_war']['flat']:,.0f}"
      f"   level {DPW/ORIG['dollars_per_war']['flat']:.5f}")

def fa_price(W, infl=None):
    return fam.rational_value_usd(W, CY, DPW, infl=DESTALE if infl is None else infl)
def pro_price(W):
    r = cfg["discount_rate"]; g = cfg["dollars_per_war_inflation"]
    return sum(vf.tiered_war_value_usd(w)*((1+g)**t)/((1+r)**t) for t, w in enumerate(W))

W6 = [2.5]*6
print("\n--- ARMS (6yr @ 2.5 WAR/yr) ---")
res = {}
for name, fa_on, infl in [("A production", False, 0.0),
                          ("B fa_implied ON", True, 0.0),
                          ("C ON + infl=destale", True, DESTALE)]:
    set_arm(fa_on, infl)
    f, p = fa_price(W6), pro_price(W6)
    res[name] = (f, p)
    print(f"{name:22s} vf_flat {cfg['dollars_per_war']['flat']:>12,.0f}  FA6yr {f:>13,.0f}  PRO6yr {p:>13,.0f}  ratio {f/p:.5f}")
print("FA price byte-identical across arms:", len({v[0] for v in res.values()}) == 1, sorted({v[0] for v in res.values()}))

set_arm(False, 0.0)
print("\n--- scale invariance (production arm) ---")
for wr in (1.5, 2.5, 4.0):
    W = [wr]*6
    print(f"  {wr} WAR/yr: ratio {fa_price(W)/pro_price(W):.7f}")
print("\n--- per-year widening ---")
for n in range(1, 8):
    W = [2.5]*n
    print(f"  {n}yr: {fa_price(W)/pro_price(W):.4f}")
restore()
