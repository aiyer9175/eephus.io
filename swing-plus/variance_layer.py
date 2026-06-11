# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
variance_layer.py — luck/regression layer from the external variance model
(~/variance_model_handoff.zip, M0-M12 complete 2026-06-10).

skill_estimate[t] = e2_t + PA/(PA+k_t) * resid2_t     (babip: park-adj residual)
luck[t]           = observed_t - skill_estimate_t     (the part projected to vanish)

2023-25: straight from the handoff table (e2 cross-fitted, no identity leakage).
2026: e2 refit on 2023-25 with the handoff's exact recipe — PA-weighted OLS on the
five composites (Swing+, Decision+, Contact+ v1, B2B+, DCV+) + sprint speed +
season dummies (2026 scored on the 2025 environment dummy; league renorm is an
engine concern per the handoff) — then the same shrinkage constants. Partial-season
PA -> small carry, as intended.

Holdout validation (2025->2026, never seen by the model): next-wOBA r .255 (naive
carry) -> .323 (skill estimate), MAE -11%; ISO .435 -> .509; AVG .205 -> .237.

Output: data/processed/variance_layer.parquet
        (batter, season, pa, sk_woba, luck_woba, sk_iso, luck_iso, sk_avg, luck_avg)
"""
import io, json, urllib.request
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression

HAND = Path("data/processed/variance_handoff")
OUT = Path("data/processed/variance_layer.parquet")
FEATS = ["swing_plus", "decision_plus_mlb", "contact_plus", "bat_to_ball_plus",
         "dcv_plus", "sprint_speed"]
SHOW = ["woba", "iso", "avg"]
SPRINT_URL = ("https://baseballsavant.mlb.com/leaderboard/sprint_speed"
              "?min_season={y}&max_season={y}&position=&team=&min=5&csv=true")


def sprint(years):
    rows = []
    for y in years:
        req = urllib.request.Request(SPRINT_URL.format(y=y),
                                     headers={"User-Agent": "Mozilla/5.0"})
        d = pd.read_csv(io.StringIO(urllib.request.urlopen(req, timeout=60)
                                    .read().decode("utf-8-sig")))
        rows.append(pd.DataFrame({"batter": d.player_id, "season": y,
                                  "sprint_speed": pd.to_numeric(d.sprint_speed,
                                                                errors="coerce")}))
    return pd.concat(rows, ignore_index=True)


def composites():
    """(batter, season) five composites + observed stats from our sources, 2023-26
    (the handoff table carries only e2/resid outputs, not the feature values)."""
    b2b = pd.read_parquet("data/processed/bat_to_ball_plus.parquet")
    b2b["season"] = b2b.season.astype(int)
    b2b = b2b[["batter", "season", "bat_to_ball_plus", "contact_plus"]]
    dcv = pd.read_parquet("data/processed/dcv_plus.parquet")[
        ["batter", "season", "dcv_plus"]]
    dcv["batter"] = dcv.batter.astype("int64")
    lb = pd.read_parquet("data/processed/leaderboard_season.parquet")
    lb["season"] = lb.season.astype(int)
    lbg = lb.groupby(["batter", "season"], as_index=False)[
        ["swing_plus", "obs_woba", "obs_iso", "n_pa"]].mean()
    dec = pd.read_parquet("data/processed/mlb_decision.parquet")[
        ["batter", "decision_plus_mlb"]].drop_duplicates("batter")
    rates = pd.read_parquet("data/processed/obs_rates.parquet")[
        ["batter", "year", "obs_avg", "pa"]].rename(columns={"year": "season"})
    d = (lbg.merge(b2b, on=["batter", "season"], how="inner")
            .merge(dcv, on=["batter", "season"], how="inner")
            .merge(dec, on="batter", how="inner")
            .merge(rates, on=["batter", "season"], how="left"))
    d = d.rename(columns={"obs_woba": "woba", "obs_iso": "iso", "obs_avg": "avg"})
    d["pa"] = d["pa"].fillna(d["n_pa"])
    return d


def _design(df, train_seasons):
    X = df[FEATS].astype(float).copy()
    for s in sorted(train_seasons)[1:]:
        X[f"season_{s}"] = (np.minimum(df.season, max(train_seasons)) == s).astype(float)
    return X                                   # 2026 rows get the 2025 dummy


if __name__ == "__main__":
    v = pd.read_parquet(HAND / "variance_model_output.parquet")
    ks = pd.read_csv(HAND / "shrinkage_constants.csv").set_index("target")

    # 2023-25 straight from the handoff
    hist = v[["batter", "season", "pa"]].copy()
    for t in SHOW:
        carry = v.pa / (v.pa + ks.loc[t, "k_pa"])
        r = v["resid2_babip_adj"] if t == "babip" else v[f"resid2_{t}"]
        hist[f"sk_{t}"] = v[f"e2_{t}"] + carry * r
        hist[f"luck_{t}"] = v[t] - hist[f"sk_{t}"]

    # 2026: refit e2 with the handoff recipe, validate vs their cross-fitted e2
    spd = sprint([2023, 2024, 2025, 2026])
    cmp_ = composites().merge(spd, on=["batter", "season"], how="left")
    cmp_ = cmp_[cmp_[FEATS].notna().all(axis=1) & cmp_.pa.notna()]
    tr = cmp_[cmp_.season < 2026].merge(
        v[["batter", "season"] + [f"e2_{t}" for t in SHOW]],
        on=["batter", "season"], how="inner")
    out26 = cmp_[cmp_.season == 2026].copy().reset_index(drop=True)
    both = pd.concat([tr, out26], ignore_index=True)
    Xall = _design(both, [2023, 2024, 2025])
    ntr = len(tr)
    mu, sd = Xall.iloc[:ntr].mean(), Xall.iloc[:ntr].std().replace(0, 1)
    Xn = ((Xall - mu) / sd).values
    print(f"e2 refit: train n={ntr}, 2026 score n={len(out26)}")
    for t in SHOW:
        m = LinearRegression().fit(Xn[:ntr], tr[t].values, sample_weight=tr.pa.values)
        rr = np.corrcoef(m.predict(Xn[:ntr]), tr[f"e2_{t}"].values)[0, 1]
        e2 = m.predict(Xn[ntr:])
        carry = out26.pa / (out26.pa + ks.loc[t, "k_pa"])
        out26[f"sk_{t}"] = e2 + carry * (out26[t] - e2)
        out26[f"luck_{t}"] = out26[t] - out26[f"sk_{t}"]
        print(f"   {t:5s}: refit-vs-handoff e2 r={rr:.3f}")

    res = pd.concat([hist, out26[["batter", "season", "pa"]
                                 + [c for c in out26 if c.startswith(("sk_", "luck_"))]]],
                    ignore_index=True)
    for c in res.columns:
        if c.startswith(("sk_", "luck_")):
            res[c] = res[c].round(4)
    res.to_parquet(OUT, index=False)
    print(f"saved {OUT}: {len(res)} rows {dict(res.season.value_counts().sort_index())}")
    nm = v[["batter", "name"]].drop_duplicates("batter")
    big = out26.merge(nm, on="batter", how="left").dropna(subset=["luck_woba"])
    big = big[big.pa >= 150]
    print("\n2026 most over skill (due for regression):",
          "; ".join(f"{r['name']} +{r.luck_woba:.3f}" for _, r in big.nlargest(4, "luck_woba").iterrows()))
    print("2026 most under skill (due for bounce-back):",
          "; ".join(f"{r['name']} {r.luck_woba:.3f}" for _, r in big.nsmallest(4, "luck_woba").iterrows()))
