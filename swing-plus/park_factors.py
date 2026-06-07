# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
park_factors.py — team-controlled (home/road) park factors for HR and ISO, used to
add PARK-NEUTRAL observed HR%/ISO columns alongside the raw ones.

Method (how Statcast/FanGraphs derive published factors): for each park, compare the
HR / extra-base rate there to the SAME hitters' rate everywhere else — so a park's
factor isn't inflated by the home team's hitter quality (naive HR/PA-at-park is).
Lightly regressed toward 1.0 by sample. Per player we use their PA-weighted exposure
(road games dilute it), so the adjustment is honest, not a blanket home-park multiplier.

NOTE: park-neutralizing does NOT improve the swing→HR/ISO model (per-player effect is
small once road games dilute it); its value is interpretive — a fair HR%/ISO for
extreme parks (Coors/Dodger vs PNC/Oracle).
"""
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).parent
HALVES = {"2023_H2": "2023", "2024_H1": "2024", "2024_H2": "2024",
          "2025_H1": "2025", "2025_H2": "2025", "2026_H1": "2026"}
_NONPA = {"truncated_pa"}
_REG = 8000          # regression strength (park-PA equivalent) toward neutral 1.0


def _pa_level() -> pd.DataFrame:
    rows = []
    for h, season in HALVES.items():
        f = ROOT / "data" / "raw" / f"statcast_{h}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["batter", "home_team", "events"])
        d = d[d["events"].notna() & ~d["events"].isin(_NONPA)]
        e = d["events"]
        hr = e.eq("home_run")
        bb = e.isin({"walk", "intent_walk"}); hbp = e.eq("hit_by_pitch")
        sac = e.isin({"sac_fly", "sac_fly_double_play", "sac_bunt", "sac_bunt_double_play"})
        s2 = e.eq("double"); s3 = e.eq("triple")
        d = d.assign(hr=hr.astype(int), season=season, pa=1,
                     ab=(~(bb | hbp | sac)).astype(int),
                     isopts=(s2.astype(int) + 2 * s3.astype(int) + 3 * hr.astype(int)))
        rows.append(d[["batter", "home_team", "season", "hr", "pa", "ab", "isopts"]])
    return pd.concat(rows, ignore_index=True)


def _homeroad_factor(pa: pd.DataFrame, num: str, denom: str) -> pd.Series:
    """Park factor for rate num/denom: park's actual vs the same hitters' rate elsewhere."""
    g = pa.groupby(["batter", "home_team"]).agg(n=(num, "sum"), d=(denom, "sum"))
    bt = pa.groupby("batter").agg(tn=(num, "sum"), td=(denom, "sum"))
    g = g.join(bt, on="batter")
    other_rate = (g["tn"] - g["n"]) / (g["td"] - g["d"]).replace(0, np.nan)
    g["exp"] = g["d"] * other_rate
    pf = g.groupby("home_team").apply(lambda x: x["n"].sum() / x["exp"].sum())
    nd = pa.groupby("home_team")[denom].sum()
    return (pf * nd + 1.0 * _REG) / (nd + _REG)          # regress toward 1.0


def factors():
    pa = _pa_level()
    return pa, _homeroad_factor(pa, "hr", "pa").rename("pf_hr_park"), \
        _homeroad_factor(pa, "isopts", "ab").rename("pf_iso_park")


def weighted(grain: str) -> pd.DataFrame:
    """Per (batter, period): PA-weighted HR park factor, AB-weighted ISO park factor."""
    pa, pf_hr, pf_iso = factors()
    pa["pf_hr"] = pa["home_team"].map(pf_hr)
    pa["pf_iso"] = pa["home_team"].map(pf_iso)
    keys = {"half": ["batter", "season"], "season": ["batter", "season"],
            "alltime": ["batter"]}[grain]
    # HR weighted by PA (=rows), ISO weighted by AB
    g = pa.groupby(keys)
    hr = g.apply(lambda d: d["pf_hr"].mean()).rename("wpf_hr")
    iso = g.apply(lambda d: np.average(d["pf_iso"], weights=d["ab"]) if d["ab"].sum() else np.nan).rename("wpf_iso")
    return pd.concat([hr, iso], axis=1).reset_index()


def add_park_neutral(board: pd.DataFrame, grain: str) -> pd.DataFrame:
    """Add obs_hr_pct_pn / obs_iso_pn (park-neutral) + park-neutral diff vs pred."""
    w = weighted(grain)
    if grain == "alltime":
        b = board.merge(w, on="batter", how="left")
    else:                                  # half board joins on (batter, season)
        bb = board.copy()
        if "season" not in bb.columns and "half" in bb.columns:
            bb["season"] = bb["half"].str[:4]
        b = bb.merge(w, on=["batter", "season"], how="left")
    if "obs_hr_pct" in b.columns:
        b["obs_hr_pct_pn"] = (b["obs_hr_pct"] / b["wpf_hr"]).round(1)
        if "pred_hr_pct" in b.columns:
            b["xdiff_hr_pct_pn"] = (b["obs_hr_pct_pn"] - b["pred_hr_pct"]).round(1)
    if "obs_iso" in b.columns:
        b["obs_iso_pn"] = (b["obs_iso"] / b["wpf_iso"]).round(3)
        if "pred_iso" in b.columns:
            b["xdiff_iso_pn"] = (b["obs_iso_pn"] - b["pred_iso"]).round(3)
    return b


if __name__ == "__main__":
    pa, pf_hr, pf_iso = factors()
    print("HR / ISO park factors (home/road, team-controlled, regressed):")
    print(pd.concat([pf_hr, pf_iso], axis=1).sort_values("pf_hr_park", ascending=False).round(3).to_string())
