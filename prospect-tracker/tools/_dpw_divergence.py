"""Lane: divergence-origin. Re-derive the two $/WAR curves from shipped code.
Read-only. No production file is touched."""
import json, sys, math
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import value_framework as vf
import fa_market as fm
import valuation_sets as vs

out = {}
cfg = vf._config()
dpw = cfg["dollars_per_war"]
out["active_set"] = cfg.get("_valuation_set")
out["vf_flat"] = dpw["flat"]
out["vf_tiered"] = dpw["tiered"]
out["vf_fa_implied"] = dpw.get("fa_implied")
out["vf_reanchor"] = dpw.get("_fa_reanchor")
out["vf_inflation"] = cfg["dollars_per_war_inflation"]
out["vf_discount"] = cfg["discount_rate"]

series_raw = json.loads((HERE / "data" / "fa_dpw_series.json").read_text())["usd_per_war_by_winter"]
series = {int(k): float(v) for k, v in series_raw.items()}
out["series"] = series_raw

CY = 2027
out["fa_winter_dpw_2027"] = fm.winter_dpw(series, CY)
out["fa_destale_2027"] = fm._destale_rate(series, CY)
out["fa_forecast_method"] = fm._dpw_forecast_method()
out["level_ratio_yr0"] = out["fa_winter_dpw_2027"] / out["vf_flat"]

# what the fa_implied re-anchor WOULD produce if enabled (trailing 3)
winters = sorted(series)
for n in (1, 3, 5):
    tail = winters[-n:]
    out[f"fa_implied_level_trailing{n}"] = sum(series[y] for y in tail) / len(tail)
out["fa_implied_scale_trailing3"] = out["fa_implied_level_trailing3"] / out["vf_flat"]

# --- Identical 6-year WAR path priced both ways ---
def prospect_price(path, infl=None, dpwlevel=None):
    """value_framework convention: tiered convex price, escalate at vf inflation,
    discount at vf rate. Level = vf flat (level factor 1.0)."""
    r = cfg["discount_rate"]
    i = cfg["dollars_per_war_inflation"] if infl is None else infl
    lvl = 1.0 if dpwlevel is None else dpwlevel / dpw["flat"]
    return sum(vf.tiered_war_value_usd(w) * lvl * ((1 + i) ** t) / ((1 + r) ** t)
               for t, w in enumerate(path))

def fa_price(path, cy=CY):
    return fm.rational_value_usd(path, cy, out["fa_winter_dpw_2027"],
                                 infl=out["fa_destale_2027"])

out["paths"] = {}
for war in (1.5, 2.5, 4.0):
    p = [war] * 6
    fa = fa_price(p)
    pr = prospect_price(p)
    out["paths"][str(war)] = {"fa": fa, "prospect": pr, "ratio": fa / pr}

# per-year ratio widening
out["per_year_ratio"] = {}
for t in range(7):
    p = [0.0] * t + [2.5]
    fa = fa_price(p)
    pr = prospect_price(p)
    out["per_year_ratio"][t] = {"fa": fa, "prospect": pr, "ratio": fa / pr}

print(json.dumps(out, indent=1, default=str))
