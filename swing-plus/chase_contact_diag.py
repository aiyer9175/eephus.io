# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
chase_contact_diag.py — Is the model under-crediting bad-ball hitters?

Hypothesis: players under-predicted on xwOBA (obs > pred: Franco, Devers,
Vlad Jr) are productive bad-ball hitters. The model has chase RATE and
out-of-zone contact RATE, but maybe not chase contact QUALITY (damage on
pitches out of the zone), so it treats their chasing as a generic negative.

We correlate the career xwOBA residual with:
  chase_rate            O-Swing% (swing at out-of-zone pitches)
  o_contact_rate        contact% on out-of-zone swings  [IN the model]
  chase_contact_vol     chase_rate * o_contact_rate     [poly term in model]
  ooz_xwobacon          xwOBAcon on out-of-zone BIP  (chase DAMAGE) [NOT in model]
  iz_xwobacon           xwOBAcon on in-zone BIP        (for contrast)

ooz_xwobacon is launch-derived (an outcome) so it can't be a model feature
without leakage — but it's a valid diagnostic for what the residual contains.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

PROC = Path(__file__).parent / "data" / "processed"
RAW = Path(__file__).parent / "data" / "raw"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
SWING = {"hit_into_play", "foul", "swinging_strike", "swinging_strike_blocked", "foul_tip"}
WHIFF = {"swinging_strike", "swinging_strike_blocked"}


def per_half(label):
    df = pd.read_parquet(RAW / f"statcast_{label}.parquet",
                         columns=["batter", "description", "zone", "type",
                                  "estimated_woba_using_speedangle"])
    df["_sw"] = df["description"].isin(SWING)
    df["_wh"] = df["description"].isin(WHIFF)
    df["_out"] = ~df["zone"].between(1, 9).fillna(False)
    df["_in"] = df["zone"].between(1, 9).fillna(False)
    g = df.groupby("batter")
    out = pd.DataFrame({
        "n_out": g["_out"].sum(),
        "n_ozsw": g.apply(lambda x: (x["_sw"] & x["_out"]).sum()),
        "n_ozwh": g.apply(lambda x: (x["_wh"] & x["_out"]).sum()),
    })
    out["chase_sw"] = out["n_ozsw"]
    # out-of-zone BIP production (chase damage) and in-zone BIP production
    bip = df[df["type"] == "X"]
    ooz_bip = bip[bip["_out"]].groupby("batter").agg(
        n_ooz_bip=("estimated_woba_using_speedangle", "size"),
        ooz_xwobacon=("estimated_woba_using_speedangle", "mean"))
    iz_bip = bip[bip["_in"]].groupby("batter").agg(
        iz_xwobacon=("estimated_woba_using_speedangle", "mean"))
    out = out.join(ooz_bip).join(iz_bip).reset_index()
    out["half"] = label
    return out


def main():
    raw = pd.concat([per_half(h) for h in HALVES], ignore_index=True)
    at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")
    half = pd.read_parquet(PROC / "leaderboard_half.parquet")

    # Aggregate raw chase stats to career (sum counts; PA-ish weight for rates)
    agg = raw.groupby("batter").agg(
        n_out=("n_out", "sum"), n_ozsw=("n_ozsw", "sum"), n_ozwh=("n_ozwh", "sum"),
        n_ooz_bip=("n_ooz_bip", "sum"),
        ooz_xwobacon=("ooz_xwobacon", "mean"), iz_xwobacon=("iz_xwobacon", "mean"),
    ).reset_index()
    agg["chase_rate"] = agg["n_ozsw"] / agg["n_out"]
    agg["o_contact_rate"] = 1 - agg["n_ozwh"] / agg["n_ozsw"]
    agg["chase_contact_vol"] = agg["chase_rate"] * agg["o_contact_rate"]

    m = at.merge(agg, on="batter", how="inner")
    m = m[m["n_pa"] >= 400].copy()
    m["resid"] = m["obs_xwoba"] - m["pred_xwoba"]

    print(f"=== Career players, PA>=400 (n={len(m)}) ===")
    print("Correlation of xwOBA residual (obs - pred) with chase metrics:")
    for col, lbl, note in [
        ("chase_rate", "chase_rate (O-Swing%)", "in model"),
        ("o_contact_rate", "o_contact_rate", "IN model"),
        ("chase_contact_vol", "chase x contact", "poly term in model"),
        ("ooz_xwobacon", "OOZ xwOBAcon (chase DAMAGE)", "NOT in model"),
        ("iz_xwobacon", "in-zone xwOBAcon", "contrast"),
    ]:
        s = m.dropna(subset=[col, "resid"])
        r = np.corrcoef(s[col], s["resid"])[0, 1]
        print(f"  {lbl:<30} r = {r:+.3f}   [{note}]")

    print("\n=== The named bad-ball hitters ===")
    cols = ["name", "n_pa", "obs_xwoba", "pred_xwoba", "resid",
            "chase_rate", "o_contact_rate", "ooz_xwobacon", "iz_xwobacon"]
    names = ["Wander Franco", "Rafael Devers", "Vladimir Guerrero",
             "Bobby Witt", "Shohei Ohtani", "Aaron Judge"]
    # Franco isn't PA>=400; pull from full merge
    full = at.merge(agg, on="batter", how="inner")
    full["resid"] = full["obs_xwoba"] - full["pred_xwoba"]
    show = full[full["name"].isin(names)][cols].copy()
    for c in ["obs_xwoba", "pred_xwoba", "resid", "chase_rate", "o_contact_rate",
              "ooz_xwobacon", "iz_xwobacon"]:
        show[c] = show[c].round(3)
    lg = {"chase_rate": agg["chase_rate"].median(),
          "o_contact_rate": agg["o_contact_rate"].median(),
          "ooz_xwobacon": m["ooz_xwobacon"].median()}
    print(show.to_string(index=False))
    print(f"\n  league medians: chase_rate={lg['chase_rate']:.3f}  "
          f"o_contact_rate={lg['o_contact_rate']:.3f}  ooz_xwobacon={lg['ooz_xwobacon']:.3f}")

    # Do high-chase-DAMAGE guys get under-predicted as a group?
    print("\n=== Residual by OOZ-xwOBAcon (chase damage) quartile, PA>=400 ===")
    m["ooz_q"] = pd.qcut(m["ooz_xwobacon"], 4, labels=["Q1 weak", "Q2", "Q3", "Q4 crushes"])
    print(m.groupby("ooz_q")["resid"].agg(["mean", "count"]).round(4).to_string())

    print("\n=== Most UNDER-predicted (top resid, PA>=400) — chase profile ===")
    top = m.nlargest(10, "resid")[["name", "resid", "chase_rate", "o_contact_rate", "ooz_xwobacon"]]
    print(top.round(3).to_string(index=False))
    print("\n=== Most OVER-predicted (bottom resid, PA>=400) — chase profile ===")
    bot = m.nsmallest(10, "resid")[["name", "resid", "chase_rate", "o_contact_rate", "ooz_xwobacon"]]
    print(bot.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
