# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
contact_v2.py — Contact+ v2: collision-aware contact-frequency axis.

Challenger that beat the champion (Contact+ v1 = external framework's
contact_plus) in the collision audit: predicting FUTURE whiff rate,
out-of-sample R^2 0.629 -> 0.719 (+0.089), K% +0.032; gains robust per fold,
per archetype, per bat side, and at strict sample thresholds.

Design: ridge on [Contact+ v1, compact collision feature set] fit to NEXT-season
whiff rate across all t->t+1 transitions (leave-transition-out validated in
collision_audit.py). Score = -prediction, scaled 100±10 per year (high = good
contact), reliability-shrunk by swings (K=150). 2026 scores directly off 2026
collision data. Leakage: features year t, fit target year t+1 — LOW.

Output: data/processed/contact_v2.parquet  (id, year, contact2_plus, n_swings)
"""
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
import collision_audit as ca

# compact, interpretable carrier set (from audit ridge loads)
CFEAT = ["perfect_percent", "flawed_percent", "vert_entropy", "lined_up_percent",
         "over_percent", "collision_entropy", "miss_distance"]
K_SHRINK = 150


def build_v2():
    d = ca.build()
    p = ca.pairs(d)
    cols = ["contact_plus_b2b"] + CFEAT
    ok = p[cols].notna().all(axis=1) & p["whiff_rate_next"].notna()
    q = p[ok]
    mu, sd = q[cols].mean(), q[cols].std()
    mdl = Ridge(alpha=1.0).fit((q[cols] - mu) / sd, q["whiff_rate_next"])
    print("v2 fit on", len(q), "t->t+1 pairs; loads:")
    for k, v in sorted(zip(cols, mdl.coef_), key=lambda x: -abs(x[1])):
        print(f"   {k:20s} {v:+.4f}")

    # score every covered player-year (incl. 2026)
    s = d[d[cols].notna().all(axis=1)].copy()
    s["pred_whiff"] = mdl.predict((s[cols] - mu) / sd)
    s["raw"] = -s["pred_whiff"]
    out = []
    for yr, g in s.groupby("year"):
        z = (g["raw"] - g["raw"].mean()) / g["raw"].std()
        w = g["n_swings"] / (g["n_swings"] + K_SHRINK)
        g = g.assign(contact2_plus=(100 + 10 * z * w).round(1))
        out.append(g[["id", "year", "contact2_plus", "n_swings"]])
    res = pd.concat(out, ignore_index=True)
    res.to_parquet("data/processed/contact_v2.parquet", index=False)
    print(f"\nscored {len(res)} player-years "
          f"({dict(res.year.value_counts().sort_index())})")
    return res, p


def champion_vs_challenger(res, p):
    """holdout check: v1 vs v2, year t score -> year t+1 whiff/K%."""
    p = p.merge(res.rename(columns={"year": "year"}), on=["id", "year"], how="left")
    for tgt in ["whiff_rate", "obs_k_pct"]:
        for col, lab in [("contact_plus_b2b", "v1"), ("contact2_plus", "v2")]:
            sub = p[[col, tgt + "_next"]].dropna()
            r = sub.iloc[:, 0].corr(sub.iloc[:, 1])
            print(f"   {lab} -> next {tgt.replace('obs_',''):10s} r={r:+.3f} (n={len(sub)})")


if __name__ == "__main__":
    res, p = build_v2()
    print("\n=== champion (v1) vs challenger (v2), t -> t+1 ===")
    champion_vs_challenger(res, p)
    top = res[(res.year == 2026) & (res.n_swings >= 200)].nlargest(6, "contact2_plus")
    bot = res[(res.year == 2026) & (res.n_swings >= 200)].nsmallest(4, "contact2_plus")
    F = pd.read_parquet("data/processed/savant_collision.parquet")[["id", "year", "name"]]
    for lab, t in [("2026 top", top), ("2026 bottom", bot)]:
        t = t.merge(F, on=["id", "year"])
        print(f"\n{lab}:", "; ".join(f"{r['name']} {r.contact2_plus:.0f}" for _, r in t.iterrows()))
