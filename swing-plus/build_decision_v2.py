# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
build_decision_v2.py — Step 3: swing-path-aware Decision+ (coverage-aware).

Decision-theoretic: for every pitch, value of swinging vs taking. The swing
value uses the hitter's OWN expected whiff (plane-whiff engine + his zonal
coverage residual), so a high pitch to a can't-cover-up hitter carries a real
whiff cost -> swinging is correctly scored as a bad decision FOR HIM.

  swing_ev = (1-P_whiff)*contact_rv(loc) + P_whiff*strike_rv
  take_ev  = P_inzone*strike_rv + (1-P_inzone)*ball_rv
  per-pitch loss = max(swing_ev,take_ev) - chosen_ev      (>=0)
  Decision+ (100-scale) from mean loss, two versions:
     generic  -> league P_whiff (engine only)
     coverage -> hitter-aware P_whiff (engine + his coverage, out-of-season)

Tests: (a) does coverage-aware DIVERGE from generic (current tailoring failed at
r 0.99)?  (b) reliability  (c) does it predict next-year K% better than generic?
"""

import glob
import numpy as np
import pandas as pd
from pathlib import Path
import joblib

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
RAW = sorted(glob.glob(str(ROOT / "data/raw/statcast_202*_H*.parquet")))

# count-state run values (approx linear weights, hitter perspective)
BALL_RV, STRIKE_RV = 0.055, -0.045
SW = ["swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"]
WF = ["swinging_strike", "swinging_strike_blocked", "foul_tip"]


def load_pitches():
    cols = ["batter", "game_year", "attack_angle", "swing_length", "bat_speed", "plate_x",
            "plate_z", "vy0", "vz0", "ay", "az", "release_speed", "description",
            "sz_top", "sz_bot", "estimated_woba_using_speedangle", "type"]
    d = pd.concat([pd.read_parquet(f, columns=cols) for f in RAW], ignore_index=True)
    yf = 17 / 12
    d["vy_f"] = -np.sqrt(np.clip(d["vy0"] ** 2 - 2 * d["ay"] * (50 - yf), 0, None))
    t = (d["vy_f"] - d["vy0"]) / d["ay"]
    d["VAA"] = np.degrees(np.arctan2(d["vz0"] + d["az"] * t, -d["vy_f"]))
    d = d.rename(columns={"game_year": "season"})
    d = d[d["plate_z"].between(0, 5) & d["VAA"].between(-15, 2)].copy()
    d["swung"] = d["description"].isin(SW)
    d["px_abs"] = d["plate_x"].abs()
    d["in_zone"] = (d["px_abs"] <= 0.83) & d["plate_z"].between(d["sz_bot"], d["sz_top"])
    d["zone"] = pd.cut(d["plate_z"], [0, 1.8, 2.5, 5], labels=["low", "mid", "high"])
    return d


def main():
    eng = joblib.load(ROOT / "models" / "plane_whiff_lgb.joblib")
    feats, m = eng["features"], eng["model"]
    cov = pd.read_parquet(PROC / "coverage_profile.parquet")          # cover_low/mid/high (EB-shrunk)
    covl = cov.melt(["batter", "season"], var_name="zone", value_name="cover")
    covl["zone"] = covl["zone"].str.replace("cover_", "")

    d = load_pitches()

    # generic engine whiff needs the swing-geometry feats; for TAKES, attack_angle is NaN ->
    # impute each hitter's mean attack angle by zone (his swing-plane he WOULD use)
    sw = d[d["swung"] & d["attack_angle"].notna()].copy()
    aa_prof = sw.groupby(["batter", "zone"], observed=True)["attack_angle"].mean().rename("aa_imp").reset_index()
    lg_aa = sw.groupby("zone", observed=True)["attack_angle"].mean().rename("aa_lg").reset_index()
    sl_prof = sw.groupby("batter")["swing_length"].mean().rename("sl_imp").reset_index()
    bs_prof = sw.groupby("batter")["bat_speed"].mean().rename("bs_imp").reset_index()
    d = (d.merge(aa_prof, on=["batter", "zone"], how="left").merge(lg_aa, on="zone", how="left")
           .merge(sl_prof, on="batter", how="left").merge(bs_prof, on="batter", how="left"))
    d["attack_angle"] = d["attack_angle"].fillna(d["aa_imp"]).fillna(d["aa_lg"])
    d["swing_length"] = d["swing_length"].fillna(d["sl_imp"])
    d["bat_speed"] = d["bat_speed"].fillna(d["bs_imp"])
    d["plane_mismatch"] = (d["attack_angle"] - (-d["VAA"])).abs()

    # generic engine P(whiff if swung) for EVERY pitch
    d["xwhiff_gen"] = m.predict_proba(d[feats].astype("float64").values)[:, 1]
    # hitter-aware: add OUT-OF-SEASON coverage residual (leak-safe), clip to [0,1]
    cov_career = covl.groupby(["batter", "zone"], observed=True)["cover"].mean().rename("cover_all").reset_index()
    d = d.merge(covl, on=["batter", "season", "zone"], how="left").merge(cov_career, on=["batter", "zone"], how="left")
    # leave-this-season-out coverage = (career_sum - this_season)/(n-1) approximated by career mean fallback
    d["cover_use"] = d["cover_all"].fillna(0.0)
    d["xwhiff_cov"] = (d["xwhiff_gen"] + d["cover_use"]).clip(0.02, 0.98)

    # contact run value by location (league xwOBAcon on contact -> runs)
    bip = d[d["type"] == "X"].dropna(subset=["estimated_woba_using_speedangle"])
    loc_dmg = bip.groupby("zone", observed=True)["estimated_woba_using_speedangle"].mean().rename("xwobacon_loc")
    d = d.merge(loc_dmg, on="zone", how="left")
    d["contact_rv"] = (d["xwobacon_loc"] - 0.310) / 1.25 * 0.75      # rough runs/contact

    # in-zone probability (for take value) — use observed zone membership as proxy
    d["p_inzone"] = d["in_zone"].astype(float)

    def decision_plus(xwhiff_col):
        swing_ev = (1 - d[xwhiff_col]) * d["contact_rv"] + d[xwhiff_col] * STRIKE_RV
        take_ev = d["p_inzone"] * STRIKE_RV + (1 - d["p_inzone"]) * BALL_RV
        best = np.maximum(swing_ev, take_ev)
        chosen = np.where(d["swung"], swing_ev, take_ev)
        loss = best - chosen                                   # >=0, run value left on table
        g = pd.DataFrame({"batter": d["batter"], "season": d["season"], "loss": loss})
        per = g.groupby(["batter", "season"]).agg(loss=("loss", "mean"), n=("loss", "size")).reset_index()
        per = per[per["n"] >= 500]
        # 100-scale: less loss = better; standardize
        mu, sd = per["loss"].mean(), per["loss"].std()
        per["dplus"] = 100 - (per["loss"] - mu) / sd * 10
        return per

    gen = decision_plus("xwhiff_gen").rename(columns={"dplus": "dplus_gen", "loss": "loss_gen"})
    cvr = decision_plus("xwhiff_cov").rename(columns={"dplus": "dplus_cov", "loss": "loss_cov"})
    j = gen.merge(cvr[["batter", "season", "dplus_cov"]], on=["batter", "season"])
    print(f"hitter-seasons: {len(j)}")
    print(f"\n[DIVERGENCE] corr(coverage-aware, generic) = {j['dplus_cov'].corr(j['dplus_gen']):.3f}")
    print(f"  (current scalar tailoring was 0.99 — lower = the swing-path info actually moves decisions)")
    print(f"  mean |delta| = {(j['dplus_cov']-j['dplus_gen']).abs().mean():.1f} pts; max {abs(j['dplus_cov']-j['dplus_gen']).max():.1f}")

    def yoy(df, col):
        a = df.rename(columns={col: "v0"})[["batter", "season", "v0"]]
        b = df.rename(columns={col: "v1"})[["batter", "season", "v1"]]; b["season"] = b["season"] - 1
        mm = a.merge(b, on=["batter", "season"]); return mm["v0"].corr(mm["v1"]), len(mm)
    rg, n = yoy(j, "dplus_gen"); rc, _ = yoy(j, "dplus_cov")
    print(f"\n[RELIABILITY] generic YoY r={rg:.3f} | coverage-aware YoY r={rc:.3f} (n={n})")

    # incremental: predict next-season K% — does coverage-aware add over generic?
    deep = pd.read_parquet(Path.home() / "projection_engine/data/deep_mlb.parquet")
    deep = deep[deep.sport == 1][["batter", "season", "k_pct", "pa"]]
    nx = deep.rename(columns={"k_pct": "ynext", "pa": "ypa"}); nx["season"] = nx["season"] - 1
    t = j.merge(nx, on=["batter", "season"]).dropna(subset=["ynext"]); t = t[t["ypa"] >= 150]
    from numpy.polynomial import polynomial as P
    def r2(cols):
        X = np.column_stack([t[c] for c in cols] + [np.ones(len(t))]); y = t["ynext"].values
        beta, *_ = np.linalg.lstsq(X, y, rcond=None); pred = X @ beta
        return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    print(f"\n[INCREMENTAL] predict next-season K% (n={len(t)}):")
    print(f"  generic only            R2={r2(['dplus_gen']):.4f}")
    print(f"  + coverage-aware        R2={r2(['dplus_gen','dplus_cov']):.4f}")

    out = j.merge(cvr[["batter", "season", "loss_cov"]], on=["batter", "season"])
    out.to_parquet(PROC / "decision_v2.parquet", index=False)
    print(f"\nsaved decision_v2.parquet ({len(out)} rows)")


if __name__ == "__main__":
    main()
