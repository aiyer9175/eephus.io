"""Read-only FA recon part 2: model diagnostics + bug demos. Writes nothing."""
import json, math, statistics as st, sys
from collections import Counter, defaultdict
sys.path.insert(0, ".")
import fa_market as fm
import fa_projection as fp

enr = fm.enriched_signings(2015, 2026)
dpw = fm.dollars_per_war_by_winter(enr)

print("=== BUG A: comps trend-inflation is dead (dpw_inflation == 0) ===")
print("fm._dpw_inflation() =", fm._dpw_inflation())
print("de-stale factor applied to a 2015 comp priced into a 2027 anchor:",
      (1 + fm._dpw_inflation()) ** (2027 - 2015))
print("factor the REALIZED dpw series implies:", round(dpw[2026] / dpw[2015], 3))
print("factor the DOCUMENTED 5%/yr implies:", round(1.05 ** 12, 3))

print("\n=== BUG B: comps_for includes the SAME winter (docstring says prior only) ===")
import inspect
src = inspect.getsource(fm.comps_for)
print([l.strip() for l in src.splitlines() if "class_year" in l and "<=" in l])
# count how often a training row's comps come from its own winter
model = fm.MarketModel(enr, dpw)
same_w = tot = 0
for s in model.train_pool[:400]:
    cs = fm.comps_for(s, model.train_pool)
    for c in cs:
        tot += 1
        if c["class_year"] == s["class_year"]:
            same_w += 1
print(f"same-winter comps among first 400 train rows: {same_w}/{tot} = {same_w/max(tot,1):.1%}")

print("\n=== MODEL COEFFICIENTS ===")
print("n_train", model.n_train)
print("coef_years", [round(v, 4) for v in model.coef_years])
print("coef_guar ", [round(v, 4) for v in model.coef_guar])
print("supply mean/sd", round(model.sup_mean, 2), round(model.sup_sd, 2))
print("resid_log_guar sd", round(st.pstdev(model.resid_log_guar), 3),
      "q10/q90", [round(q, 3) for q in (st.quantiles(model.resid_log_guar, n=10)[0],
                                        st.quantiles(model.resid_log_guar, n=10)[-1])])

print("\n=== IN-SAMPLE ERROR BY SLICE (train-fit, not a gate) ===")
rows = []
for s in model.train_pool:
    py, pg = model._point(s)
    act = fm._npv_of(s)
    rows.append({"g": fm._pos_group(s.get("position")), "age": s["_age"],
                 "cy": s["class_year"], "act": act, "pred": pg,
                 "ay": s["years"], "py": py, "qo": bool(s.get("qo")),
                 "err": (pg - act) / 1e6, "abserr": abs(pg - act) / 1e6,
                 "name": s.get("player_name")})


def slice_report(label, keyfn):
    print(f"-- {label}")
    b = defaultdict(list)
    for r in rows:
        b[keyfn(r)].append(r)
    for k in sorted(b, key=lambda x: str(x)):
        v = b[k]
        print(f"   {k!s:>14}  n={len(v):4d}  MAE=${st.mean(x['abserr'] for x in v):7.2f}M "
              f"bias=${st.mean(x['err'] for x in v):+7.2f}M  yrsMAE={st.mean(abs(x['py']-x['ay']) for x in v):.2f}")


slice_report("pos group", lambda r: r["g"])
slice_report("age band", lambda r: ("<=27" if r["age"] <= 27 else "28-30" if r["age"] <= 30
                                    else "31-33" if r["age"] <= 33 else "34+"))
slice_report("actual guarantee band", lambda r: ("<$5M" if r["act"] < 5e6 else "$5-25M" if r["act"] < 25e6
                                                 else "$25-100M" if r["act"] < 100e6 else ">=$100M"))
slice_report("QO", lambda r: "QO" if r["qo"] else "noQO")
slice_report("contract length", lambda r: ("1yr" if r["ay"] == 1 else "2-3yr" if r["ay"] <= 3
                                           else "4-6yr" if r["ay"] <= 6 else "7yr+"))
