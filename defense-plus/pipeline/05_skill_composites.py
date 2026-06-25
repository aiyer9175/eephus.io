# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Module 05 — skill composites beyond range (Part 2 cont.).

Applies the Module-04 result (reliability-weighted composite of same-skill indicators
beats any single metric and beats factor analysis) to the other skill domains:
  arm (OF), double play (IF), errors/hands (all), catcher framing, catcher throwing.

For each skill: compute component year-to-year reliability (extends Part 1), build the
reliability-weighted z-composite within position-year, and OOS-validate (composite_t vs
next-year skill consensus, vs the best single indicator).
"""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

RAW = os.path.expanduser("~/defense_plus/data/raw"); REP = os.path.expanduser("~/defense_plus/reports")
YEARS = list(range(2021, 2026))

# ---- load FG fielding + join Savant arm / poptime / framing ----
def load():
    fg = []
    for y in YEARS:
        d = pd.read_csv(os.path.join(RAW, f"fg_field_full_{y}.csv")).rename(columns={"xMLBAMID": "id"})
        d["year"] = y; fg.append(d)
    F = pd.concat(fg, ignore_index=True)
    F["id"] = pd.to_numeric(F["id"], errors="coerce")
    def sav(stem, idcol, cols):
        out = []
        for y in YEARS:
            d = pd.read_csv(os.path.join(RAW, f"{stem}_{y}.csv")); d["year"] = y
            d = d.rename(columns={idcol: "id"})
            out.append(d[["id", "year"] + cols])
        return pd.concat(out, ignore_index=True)
    arm = sav("arm", "player_id", ["arm_overall", "total_throws"])
    pop = sav("poptime", "entity_id", ["pop_2b_sba", "pop_2b_sba_count"])
    F = F.merge(arm, on=["id", "year"], how="left").merge(pop, on=["id", "year"], how="left")
    return F

F = load()
NUMC = ["Inn", "rARM", "ARM", "arm_overall", "rGDP", "DPR", "ErrR", "rGFP", "CFraming",
        "rSB", "pop_2b_sba", "total_throws", "pop_2b_sba_count"]
for c in NUMC:
    if c in F.columns: F[c] = pd.to_numeric(F[c], errors="coerce")
F["pop_inv"] = -F["pop_2b_sba"]   # lower pop time = better -> invert so higher=better

SKILLS = {
    "arm_OF":     dict(pos=["CF", "LF", "RF"],            inds=["rARM", "ARM", "arm_overall"]),
    "dp_IF":      dict(pos=["SS", "2B", "3B"],            inds=["rGDP", "DPR"]),
    "errors":     dict(pos=["SS", "2B", "3B", "CF", "LF", "RF", "1B"], inds=["ErrR", "rGFP"]),
    "C_framing":  dict(pos=["C"],                          inds=["CFraming"]),  # + Savant rv_tot below
    "C_throw":    dict(pos=["C"],                          inds=["rSB", "pop_inv"]),
}
MIN_INN = 300

def yoy_reliability(d, ind):
    pairs = []
    for y in YEARS[:-1]:
        a = d[d.year == y][["id", ind]]; b = d[d.year == y + 1][["id", ind]].rename(columns={ind: "v2"})
        pairs.append(a.merge(b, on="id"))
    P = pd.concat(pairs).dropna()
    return (P[ind].corr(P["v2"]), len(P)) if len(P) >= 25 else (np.nan, len(P))

print("=== component year-to-year reliability + reliability-weighted composite (OOS) ===\n")
results = []
for skill, cfg in SKILLS.items():
    d = F[F.Pos.isin(cfg["pos"]) & (F.Inn >= MIN_INN)].copy()
    inds = list(cfg["inds"])
    if skill == "C_framing":  # add Savant framing rv_tot as 2nd framing indicator
        fr = []
        for y in YEARS:
            t = pd.read_csv(os.path.join(RAW, f"framing_{y}.csv")).rename(columns={"id": "id"}); t["year"] = y
            fr.append(t[["id", "year", "rv_tot"]])
        d = d.merge(pd.concat(fr), on=["id", "year"], how="left")
        inds = ["CFraming", "rv_tot"]
    rel = {}
    for c in inds:
        r, n = yoy_reliability(d.dropna(subset=[c]), c)
        rel[c] = r
    # z within position-year; reliability-weighted composite
    for c in inds:
        d[c + "z"] = d.groupby(["Pos", "year"])[c].transform(lambda x: (x - x.mean()) / x.std())
    use = [c for c in inds if pd.notna(rel[c]) and rel[c] > 0]
    if len(use) < 2:
        print(f"## {skill:10} ({'/'.join(cfg['pos'])}) — indicators {inds}: "
              + ", ".join(f"{c} r={rel[c]:.2f}" if pd.notna(rel[c]) else f"{c} n/a" for c in inds)
              + "  [single usable indicator -> it IS the estimate]\n")
        results.append(dict(skill=skill, indicators="+".join(inds), composite_beats_best="n/a (1 ind)"))
        continue
    w = np.array([rel[c] for c in use]); w = w / w.sum()
    dd = d.dropna(subset=[c + "z" for c in use]).copy()
    dd["comp"] = (dd[[c + "z" for c in use]].values * w).sum(axis=1)
    # OOS: estimator_t vs next-year consensus (mean z of indicators)
    pairs = []
    for pos, g in dd.groupby("Pos"):
        for y in YEARS[:-1]:
            a = g[g.year == y]; b = g[g.year == y + 1]
            pairs.append(a.merge(b, on="id", suffixes=("", "_n")))
    P = pd.concat(pairs, ignore_index=True)
    if len(P) < 30:
        print(f"## {skill}: too few pairs ({len(P)})\n"); continue
    tgt = P[[c + "z_n" for c in use]].mean(axis=1).values
    r_comp = np.corrcoef(P["comp"].values, tgt)[0, 1]
    r_singles = {c: np.corrcoef(P[c + "z"].values, tgt)[0, 1] for c in use}
    best = max(r_singles, key=r_singles.get)
    print(f"## {skill:10} ({'/'.join(cfg['pos'])})  indicators+weights:")
    for c in use: print(f"     {c:12} rel={rel[c]:.2f}  w={w[list(use).index(c)]:.2f}  OOS-single r={r_singles[c]:.3f}")
    print(f"     COMPOSITE OOS r={r_comp:.3f}  vs best single ({best}) {r_singles[best]:.3f}  "
          f"-> {(r_comp-r_singles[best])/r_singles[best]*100:+.1f}%\n")
    results.append(dict(skill=skill, indicators="+".join(use), n_pairs=len(P),
                        r_composite=round(r_comp, 3), r_best_single=round(r_singles[best], 3),
                        lift_pct=round((r_comp - r_singles[best]) / r_singles[best] * 100, 1)))

pd.DataFrame(results).to_csv(os.path.join(REP, "05_skill_composites.csv"), index=False)
print(f"wrote {os.path.join(REP,'05_skill_composites.csv')}")
print("\nNote: IF arm = Savant arm-strength only (rARM/ARM are OF-only) -> single-indicator, no composite.")
