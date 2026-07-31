"""Lane: divergence-origin (d). What does dollars_per_war.fa_implied DO when
enabled?

HARNESS NOTE: fa_market does `from value_framework import _config as _vf_config`,
binding the ORIGINAL lru_cached object. Rebinding vf._config is therefore INVISIBLE
to fa_market and produces a false result (measured: it made the FA price appear to
move x1.2682 when it does not move at all). The correct method is to mutate the
CACHED CONFIG DICT IN PLACE -- every binding shares that one object -- then clear
the derived caches, which is exactly what value_framework._reset_derived_caches is
documented for."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import value_framework as vf
import fa_market as fm

series = {int(k): float(v) for k, v in
          json.loads((HERE / "data" / "fa_dpw_series.json").read_text())
          ["usd_per_war_by_winter"].items()}
CY = 2027
PATH = [2.5] * 6

def snapshot(tag):
    cfg = vf._config()
    d = cfg["dollars_per_war"]
    dpw27 = fm.winter_dpw(series, CY)
    destale = fm._destale_rate(series, CY)
    r = cfg["discount_rate"]; i = cfg["dollars_per_war_inflation"]
    prospect = sum(vf.tiered_war_value_usd(w) * ((1 + i) ** t) / ((1 + r) ** t)
                   for t, w in enumerate(PATH))
    fa = fm.rational_value_usd(PATH, CY, dpw27, infl=destale)
    return {
        "tag": tag, "set": cfg.get("_valuation_set"),
        "flat": d["flat"], "reanchor_scale": (d.get("_fa_reanchor") or {}).get("scale"),
        "inflation": i, "discount": r,
        "vf_seen_by_fa_market": fm._vf_config()["dollars_per_war"]["flat"],
        "tier_price_2.5war": vf.tiered_war_value_usd(2.5),
        "fa_winter_dpw_2027": dpw27,
        "fa_level_factor": dpw27 / fm._vf_config()["dollars_per_war"]["flat"],
        "prospect_6yr": prospect, "fa_6yr": fa, "ratio": fa / prospect,
        "surplus_45fv_hit_musd": vf.surplus_value_mm(45, False),
        "surplus_50fv_hit_musd": vf.surplus_value_mm(50, False),
        "surplus_60fv_hit_musd": vf.surplus_value_mm(60, False),
        "surplus_70fv_hit_musd": vf.surplus_value_mm(70, False),
        "surplus_60fv_pit_musd": vf.surplus_value_mm(60, True),
    }

res = [snapshot("A. PRODUCTION (clemens_2026, fa_implied OFF, infl 0.0)")]

# --- B. switch ON only: mutate the shared cached dict in place ---
cfg = vf._config()
cfg["dollars_per_war"]["fa_implied"] = {"enabled": True, "trailing_years": 3}
vf._apply_fa_implied_reanchor(cfg)      # mutates cfg["dollars_per_war"] in place
vf._reset_derived_caches()
assert fm._vf_config()["dollars_per_war"]["flat"] == cfg["dollars_per_war"]["flat"]
res.append(snapshot("B. fa_implied ON (trailing 3), infl still 0.0"))

# --- C. switch ON + escalation reconciled to the FA series rate ---
cfg["dollars_per_war_inflation"] = fm._destale_rate(series, CY)
vf._reset_derived_caches()
res.append(snapshot("C. fa_implied ON + infl = FA series destale 0.0483"))

print(json.dumps(res, indent=1, default=str))
print("\n=== DELTAS vs PRODUCTION ===")
keys = ("flat", "tier_price_2.5war", "fa_winter_dpw_2027", "fa_level_factor",
        "prospect_6yr", "fa_6yr", "ratio", "surplus_45fv_hit_musd",
        "surplus_50fv_hit_musd", "surplus_60fv_hit_musd",
        "surplus_70fv_hit_musd", "surplus_60fv_pit_musd")
a = res[0]
for r in res[1:]:
    print("\n--", r["tag"])
    for k in keys:
        print(f"  {k:24s} {a[k]:>18,.4f} -> {r[k]:>18,.4f}   x{r[k]/a[k]:.4f}")
