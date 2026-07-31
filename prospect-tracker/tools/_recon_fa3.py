"""Read-only FA recon part 3: bug quantification. Writes nothing."""
import math, statistics as st, sys
from collections import Counter, defaultdict
sys.path.insert(0, ".")
import fa_market as fm

enr = fm.enriched_signings(2015, 2026)
dpw = fm.dollars_per_war_by_winter(enr)
model = fm.MarketModel(enr, dpw)

FEATS_GUAR = ["1", "years", "war_y1", "war_y1*years", "age", "qo", "supply_z",
              "log(dpw)", "log_comps_guar", "log_rational", "prime_war", "woba", "fip_headroom"]
print("=== coef_guar with names (log-guarantee stage, OLS, ridge=0) ===")
for n, c in zip(FEATS_GUAR, model.coef_guar):
    print(f"   {n:>16s}  {c:+.4f}")

print("\n=== BUG: proj_aav divides the UNROUNDED-years guarantee by the ROUNDED years ===")
bad = []
for s in model.train_pool:
    yf, g = model._point(s)
    yi = max(1, int(round(yf)))
    aav_served = g / yi
    aav_true = g / yf
    bad.append((abs(aav_served / aav_true - 1.0), yf, yi, s.get("player_name")))
bad.sort(reverse=True)
print(f"   mean |AAV distortion| = {st.mean(b[0] for b in bad):.1%}; "
      f"rows distorted >10%: {sum(1 for b in bad if b[0] > .10)}/{len(bad)}")
print("   worst 5:", [(f'{b[0]:.0%}', round(b[1], 2), b[2], b[3]) for b in bad[:5]])

print("\n=== BUG: comps_for `<=` lets a TRAIN row see its OWN winter; serve rows never can ===")
strict = []
for s in model.train_pool:
    cs_all = fm.comps_for(s, model.train_pool)
    prior_pool = [c for c in model.train_pool if c["class_year"] < s["class_year"]]
    cs_pri = fm.comps_for(s, prior_pool) if prior_pool else []
    if not cs_all or not cs_pri:
        continue
    ma = st.median(c["guarantee_usd"] for c in cs_all)
    mp = st.median(c["guarantee_usd"] for c in cs_pri)
    strict.append((ma, mp, s))
d = [(a - p) / 1e6 for a, p, _ in strict]
print(f"   n={len(strict)}  mean comps-anchor shift (same-winter-allowed minus strict) "
      f"= ${st.mean(d):+.3f}M  median ${st.median(d):+.3f}M")
print(f"   |shift| > $1M on {sum(1 for x in d if abs(x) > 1)}/{len(d)} rows; "
      f"max ${max(d):+.1f}M / min ${min(d):+.1f}M")

print("\n=== comps-envelope clamp / mega-blend binding rate ===")
n_lo = n_hi = n_mega = 0
for s in model.train_pool:
    _cs = model._comps_stats(s)
    fy = fm._features_years(s, _cs[0], _cs[3])
    yrs = min(max(math.exp(float(sum(c * x for c, x in zip(model.coef_years, fy)))), 1.0), 15.0)
    dpw_y = fm.winter_dpw(model.dpw_series, s["class_year"])
    fg = fm._features_guar(s, yrs, dpw_y, model._supply_z(s), _cs[1],
                           model._log_rational(s, yrs, dpw_y), model._prime_war(s))
    raw = math.exp(float(sum(c * x for c, x in zip(model.coef_guar, fg))))
    cg = math.exp(_cs[1])
    if raw < cg / 2.5:
        n_lo += 1
    if raw > cg * 2.5:
        n_hi += 1
    if math.log(cg) > math.log(50e6):
        n_mega += 1
print(f"   n={len(model.train_pool)}: clamped UP to comps/2.5 {n_lo}; clamped DOWN to comps*2.5 {n_hi}; "
      f"mega-blend active (comps median > $50M) {n_mega}")

print("\n=== supply feature at serve vs train support ===")
sup_all = [c for by in model.supply_by_year.values() for c in by.values()]
print(f"   train supply counts: n={len(sup_all)} mean={model.sup_mean:.1f} sd={model.sup_sd:.1f} "
      f"min={min(sup_all):.0f} max={max(sup_all):.0f}")
print("   2027 served class counts (from the wave-2 diagnostic): SP 56 / RP 77 / C 14 / POS 74")
for g, c in (("SP", 56), ("RP", 77), ("C", 14), ("POS", 74)):
    z = (c - model.sup_mean) / model.sup_sd
    print(f"      {g:>4s} z={z:+.2f}  -> log-guar multiplier exp({model.coef_guar[6]:.4f}*z) "
          f"= {math.exp(model.coef_guar[6]*z):.3f}")
