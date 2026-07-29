"""Read-only recon of the FA stack. Writes nothing."""
import json, math, statistics as st, sys
from collections import Counter, defaultdict
sys.path.insert(0, ".")
import fa_market as fm
import fa_projection as fp
from value_framework import _config as vfc

print("=== CONFIG ===")
c = vfc()
print("discount_rate", c["discount_rate"], "dpw_inflation", c["dollars_per_war_inflation"],
      "flat_dpw", c["dollars_per_war"]["flat"])
print("fm._discount_rate()", fm._discount_rate(), "fm._dpw_inflation()", fm._dpw_inflation())

print("\n=== ENRICHED CORPUS ===")
enr = fm.enriched_signings(2015, 2026)
print("n enriched", len(enr))
by_yr = Counter(s["class_year"] for s in enr)
print("by winter", dict(sorted(by_yr.items())))
print("pos groups", Counter(fm._pos_group(s.get("position")) for s in enr))

dpw = fm.dollars_per_war_by_winter(enr)
print("\ndpw by winter", {k: int(v) for k, v in dpw.items()})
print("winter_dpw(2027)", int(fm.winter_dpw(dpw, 2027)))
print("winter_dpw(2028)", int(fm.winter_dpw(dpw, 2028)))
print("winter_dpw(2015)", int(fm.winter_dpw(dpw, 2015)))

json.dump({"n": len(enr)}, open("tools/_recon_fa_stamp.json", "w"))
