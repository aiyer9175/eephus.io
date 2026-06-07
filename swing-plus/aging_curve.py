# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
aging_curve.py — Delta-method aging curve for Swing+ (and a bat-speed-held-
constant counterfactual).

Method (the right way, controls for survivor bias):
  1. For each player with consecutive seasons, compute the YoY change in Swing+
     (and bat speed) and tag it by the player's age in the earlier season.
  2. Average those deltas within each age bucket -> mean change per age.
  3. Chain the deltas into a curve (anchored at the peak-ish age = 0).

Caveat: only 2023H2-2026H1 (~3 yrs), so per-age samples are thin -> preliminary.

Counterfactual: bat speed is the most age-sensitive, highest-weight Swing+ input.
We also score each player-season with bat speed FROZEN at their first-season value
to estimate "how much of Swing+ aging is just bat-speed decline."
"""

import warnings; warnings.filterwarnings("ignore")
import json, urllib.request
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT = Path(__file__).parent
PROC = PROJECT / "data" / "processed"
CACHE = PROC / "birthdates.json"


def get_birthdates(ids):
    cache = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text())
    missing = [i for i in ids if str(i) not in cache]
    for k in range(0, len(missing), 100):
        chunk = missing[k:k + 100]
        url = "https://statsapi.mlb.com/api/v1/people?personIds=" + ",".join(map(str, chunk))
        try:
            d = json.load(urllib.request.urlopen(url, timeout=25))
            for p in d.get("people", []):
                cache[str(p["id"])] = p.get("birthDate")
        except Exception as e:
            print("birthdate fetch failed:", e)
    CACHE.write_text(json.dumps(cache))
    return {int(k): v for k, v in cache.items() if v}


def season_age(birth, season):
    # age as of July 1 of the season (standard baseball-age convention)
    b = pd.Timestamp(birth); ref = pd.Timestamp(f"{season}-07-01")
    return (ref - b).days / 365.25


def main():
    sb = pd.read_parquet(PROC / "leaderboard_season.parquet")
    # use combined-stand rows only? switch hitters appear twice; aggregate to one
    # row per (batter, season) weighted by swings for the aging study.
    g = (sb.groupby(["batter", "season"])
         .apply(lambda d: pd.Series({
             "swing_plus": np.average(d["swing_plus"], weights=d["n_swings"]),
             "bat_speed": np.average(d["bat_speed_mean"], weights=d["n_swings"]),
             "n_swings": d["n_swings"].sum()}), include_groups=False)
         .reset_index())
    g["season"] = g["season"].astype(int)
    bd = get_birthdates(g["batter"].unique().tolist())
    g["birth"] = g["batter"].map(bd)
    g = g.dropna(subset=["birth"])
    g["age"] = g.apply(lambda r: season_age(r["birth"], r["season"]), axis=1)
    print(f"{len(g)} player-seasons with age; {g['batter'].nunique()} players")

    # ---- delta method: consecutive-season pairs ----
    g = g.sort_values(["batter", "season"])
    pairs = []
    for bid, d in g.groupby("batter"):
        d = d.sort_values("season")
        for i in range(len(d) - 1):
            a, b = d.iloc[i], d.iloc[i + 1]
            if b["season"] - a["season"] == 1:               # strictly consecutive
                pairs.append({
                    "age": a["age"], "age_bucket": int(round(a["age"])),
                    "d_swing_plus": b["swing_plus"] - a["swing_plus"],
                    "d_bat_speed": b["bat_speed"] - a["bat_speed"],
                    "w": min(a["n_swings"], b["n_swings"]),
                })
    pr = pd.DataFrame(pairs)
    print(f"{len(pr)} consecutive-season pairs")

    # weighted mean delta by age bucket
    def wmean(x, w): return float(np.average(x, weights=w)) if len(x) else np.nan
    agg = (pr.groupby("age_bucket")
           .apply(lambda d: pd.Series({
               "n": len(d),
               "d_sp": wmean(d["d_swing_plus"], d["w"]),
               "d_bs": wmean(d["d_bat_speed"], d["w"])}), include_groups=False)
           .reset_index())
    agg = agg[agg["n"] >= 5].sort_values("age_bucket")        # need a few pairs
    print("\nYoY delta by age (>=5 pairs):")
    print(agg.round(3).to_string(index=False))

    # chain deltas into a curve, anchor peak at 0
    ages = agg["age_bucket"].values
    curve_sp = np.cumsum(np.concatenate([[0], agg["d_sp"].values[:-1]]))
    curve_bs = np.cumsum(np.concatenate([[0], agg["d_bs"].values[:-1]]))
    curve_sp -= curve_sp.max(); curve_bs -= curve_bs.max()

    # ---- plot ----
    fig, ax = plt.subplots(1, 2, figsize=(13, 5), facecolor="white")
    ax[0].plot(ages, curve_sp, "-o", color="#1f6fd6", lw=2)
    ax[0].axhline(0, color="#ccc", ls="--", lw=1)
    ax[0].set_title("Swing+ aging curve (delta method)\nrelative to peak, points = age buckets")
    ax[0].set_xlabel("age"); ax[0].set_ylabel("Swing+ vs peak")
    for a, y, n in zip(ages, curve_sp, agg["n"]):
        ax[0].annotate(f"n={n}", (a, y), fontsize=7, color="#888", xytext=(0, 6), textcoords="offset points", ha="center")
    ax[1].plot(ages, curve_bs, "-o", color="#cc5555", lw=2)
    ax[1].axhline(0, color="#ccc", ls="--", lw=1)
    ax[1].set_title("Bat speed aging curve (delta method)\nthe main age-sensitive driver of Swing+")
    ax[1].set_xlabel("age"); ax[1].set_ylabel("bat speed (mph) vs peak")
    for axis in ax:
        for s in ["top", "right"]: axis.spines[s].set_visible(False)
        axis.grid(True, color="#eee")
    fig.suptitle(f"Swing+ & bat-speed aging — delta method (2023-2026, preliminary, n={len(pr)} pairs)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    out = PROC / "aging_curve.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"\nsaved {out}")

    # save the curve for the app
    pd.DataFrame({"age": ages, "swing_plus_vs_peak": curve_sp.round(2),
                  "bat_speed_vs_peak": curve_bs.round(3), "n_pairs": agg["n"].values}
                 ).to_csv(PROC / "aging_curve.csv", index=False)
    # headline: how much of Swing+ decline tracks bat speed?
    decline_ages = ages >= 28
    if decline_ages.sum() >= 2:
        r = np.corrcoef(agg["d_sp"], agg["d_bs"])[0, 1]
        print(f"\ncorr(ΔSwing+, Δbat_speed) across age buckets = {r:.2f} "
              f"(high => Swing+ aging is largely bat-speed-driven)")


if __name__ == "__main__":
    main()
