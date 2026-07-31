"""RECONCILE lane: independent re-derivation of the divergence + switch test.
GOTCHA (inherited, re-verified): fa_market does `from value_framework import _config as _vf_config`
so it binds the ORIGINAL lru_cached function. Mutate the returned dict IN PLACE."""
import json, importlib
import value_framework as vf, fa_market as fam

cfg = vf._config()
print("SET", cfg.get("_valuation_set"))
print("flat", cfg["dollars_per_war"]["flat"])
print("rates", cfg["dollars_per_war"]["tiered"]["rates"])
print("fa_implied", cfg["dollars_per_war"].get("fa_implied"))
print("_fa_reanchor", cfg["dollars_per_war"].get("_fa_reanchor"))
print("infl", cfg.get("dollars_per_war_inflation"), "disc", cfg["discount_rate"])
print("same obj as fa_market sees:", fam._vf_config() is cfg)

ser = json.loads(open("data/fa_dpw_series.json").read())["usd_per_war_by_winter"]
print("series tail", {k: ser[k] for k in sorted(ser)[-5:]})

W = [2.5]*6
def prices():
    dpw = fam.winter_dpw(2027) if hasattr(fam, "winter_dpw") else None
    return dpw
# locate the winter dpw fn
print([n for n in dir(fam) if "winter" in n.lower() or "dpw" in n.lower()])
