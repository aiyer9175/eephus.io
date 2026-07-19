# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
swing_grade.py — grade INDIVIDUAL swings on INDIVIDUAL pitches (matchup execution).

For every competitive MLB swing we have the pitch (velo/location/movement/spin) AND the
hitter's bat-tracking ON that pitch. We model two things at the pitch level:
  whiff  = P(miss | pitch, swing-path)         (vs a pitch-only league baseline)
  contact= E[xwOBAcon | pitch, swing-path]     (vs a pitch-only league baseline)
A swing's expected value vs the pitch = (1-whiff)*contact. Subtracting the
pitch-only (league) baseline isolates the SWING's contribution — i.e. how well his
path fit THIS pitch, controlling for how hard the pitch is. That's the swing grade.

Leakage-safe: swing features are PATH only (bat speed / attack angle / swing length /
direction / tilt) — NOT the contact-point intercept (which encodes the miss).
Caveat: the path doesn't encode timing, so grades read execution/fit, not timing.

v2 improvements:
  - PITCH side is BATTER-RELATIVE (plate_x / pfx_x mirrored by handedness) so "inside"
    means the same thing for both hands  -> whiff AUC 0.850 -> 0.861 (GroupKFold by batter).
  - Adds platoon (same_hand), spin rate, extension, spin axis, zone-normalized height.
  - Grades are scored OUT-OF-FOLD (GroupKFold by batter) so the decile validity is honest
    rather than in-sample. A full-data model is still saved for any live scoring.
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import roc_auc_score, r2_score

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OUT = PROC / "swing_grades.parquet"
MODELS = ROOT / "swing_grade_models.joblib"

HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2", "2026_H1"]
SW = {"hit_into_play", "foul", "swinging_strike", "swinging_strike_blocked", "foul_tip"}
WH = {"swinging_strike", "swinging_strike_blocked", "foul_tip"}
# raw measured columns we must have to keep a row
CORE = ["release_speed", "plate_x", "plate_z", "pfx_x", "pfx_z"]
PATH = ["bat_speed", "attack_angle", "swing_length", "attack_direction", "swing_path_tilt"]
# batter-relative / engineered pitch feature set fed to the models (HistGBT handles NaN natively)
PITCH = ["release_speed", "plate_x_h", "plate_z", "plate_z_n", "pfx_x_h", "pfx_z",
         "release_spin_rate", "release_extension", "spin_axis", "same_hand"]
EXTRA = ["p_throws", "release_spin_rate", "release_extension", "spin_axis", "sz_top", "sz_bot"]
COLS = (["batter", "stand", "game_date", "pitch_type", "balls", "strikes", "description",
         "events", "launch_speed", "estimated_woba_using_speedangle"] + CORE + PATH + EXTRA)


def load_swings() -> pd.DataFrame:
    parts = []
    for h in HALVES:
        f = RAW / f"statcast_{h}.parquet"
        if f.exists():
            d = pd.read_parquet(f, columns=COLS)
            d["season"] = h[:4]; parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    d = d[d["description"].isin(SW)].dropna(subset=CORE + PATH).reset_index(drop=True)
    d["whiff"] = d["description"].isin(WH).astype(int)
    # batter-relative geometry: inside is +x for everyone
    sgn = np.where(d["stand"].values == "L", -1.0, 1.0)
    d["plate_x_h"] = d["plate_x"].values * sgn
    d["pfx_x_h"] = d["pfx_x"].values * sgn
    d["plate_z_n"] = (d["plate_z"] - d["sz_bot"]) / (d["sz_top"] - d["sz_bot"])
    d["same_hand"] = (d["stand"] == d["p_throws"]).astype(int)
    # HistGBT wants real floats with np.nan, not pandas nullable NAType
    for c in set(PITCH + PATH):
        d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")
    return d


def _gbtC(): return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=300, min_samples_leaf=80)
def _gbtR(): return HistGradientBoostingRegressor(max_depth=4, learning_rate=0.06, max_iter=300, min_samples_leaf=60)


def build(verbose=True):
    d = load_swings()
    g = d["batter"].values
    bip_mask = (d["description"] == "hit_into_play") & d["estimated_woba_using_speedangle"].notna()
    bip = d[bip_mask].reset_index(drop=True)
    gb = bip["batter"].values

    # ---- final full-data models (saved for any live/ad-hoc scoring) ----
    whF = _gbtC().fit(d[PITCH + PATH].values, d["whiff"].values)
    whP = _gbtC().fit(d[PITCH].values, d["whiff"].values)
    coF = _gbtR().fit(bip[PITCH + PATH].values, bip["estimated_woba_using_speedangle"].values)
    coP = _gbtR().fit(bip[PITCH].values, bip["estimated_woba_using_speedangle"].values)
    joblib.dump({"whF": whF, "whP": whP, "coF": coF, "coP": coP, "PITCH": PITCH, "PATH": PATH}, MODELS)

    # ---- OUT-OF-FOLD scoring (honest): GroupKFold by batter ----
    cv = GroupKFold(5)
    if verbose: print("  out-of-fold whiff (full)…")
    d["whiff_prob"] = cross_val_predict(_gbtC(), d[PITCH + PATH].values, d["whiff"].values,
                                        cv=cv, groups=g, method="predict_proba")[:, 1]
    if verbose: print("  out-of-fold whiff (pitch-only)…")
    d["whiff_base"] = cross_val_predict(_gbtC(), d[PITCH].values, d["whiff"].values,
                                        cv=cv, groups=g, method="predict_proba")[:, 1]
    # contact: OOF within BIP; for non-BIP swings use the full model (those rows aren't training targets)
    if verbose: print("  out-of-fold contact…")
    co_oof = cross_val_predict(_gbtR(), bip[PITCH + PATH].values, bip["estimated_woba_using_speedangle"].values, cv=cv, groups=gb)
    cb_oof = cross_val_predict(_gbtR(), bip[PITCH].values, bip["estimated_woba_using_speedangle"].values, cv=cv, groups=gb)
    d["exp_con"] = coF.predict(d[PITCH + PATH].values)
    base_con = coP.predict(d[PITCH].values)
    d.loc[bip_mask, "exp_con"] = co_oof
    base_con[bip_mask.values] = cb_oof

    if verbose:
        s = d.sample(min(150000, len(d)), random_state=1)
        print(f"  whiff AUC  pitch-only={roc_auc_score(s['whiff'], s['whiff_base']):.3f}  "
              f"pitch+path={roc_auc_score(s['whiff'], s['whiff_prob']):.3f}  (OOF)")
        print(f"  contact R2 pitch-only={r2_score(bip['estimated_woba_using_speedangle'], cb_oof):.3f}  "
              f"pitch+path={r2_score(bip['estimated_woba_using_speedangle'], co_oof):.3f}  (OOF)")

    d["xrv"] = (1 - d["whiff_prob"]) * d["exp_con"]
    d["xrv_base"] = (1 - d["whiff_base"]) * base_con
    raw = d["xrv"] - d["xrv_base"]
    mu, sd = raw.mean(), raw.std() or 1.0
    d["swing_grade"] = np.clip(50 + 10 * (raw - mu) / sd, 20, 90).round(1)   # 20-90 scouting scale (1 SD = 10)
    d["contact_fit"] = (d["whiff_base"] - d["whiff_prob"]).round(3)   # + = path avoids whiff vs avg
    keep = ["batter", "stand", "season", "game_date", "pitch_type", "plate_x", "plate_z",
            "release_speed", "balls", "strikes", "bat_speed", "attack_angle", "swing_length",
            "description", "events", "launch_speed", "estimated_woba_using_speedangle",
            "whiff", "whiff_prob", "exp_con", "contact_fit", "swing_grade"]
    out = d[keep].copy()
    for c in ["plate_x", "plate_z", "release_speed", "bat_speed", "attack_angle", "swing_length",
              "launch_speed", "estimated_woba_using_speedangle", "whiff_prob", "exp_con",
              "contact_fit", "swing_grade"]:
        out[c] = out[c].astype("float32")
    out["whiff_prob"] = (out["whiff_prob"] * 100).round(1)        # store as %
    out.to_parquet(OUT, index=False)
    if verbose:
        print(f"  scored {len(out):,} swings -> {OUT}")
    return out


if __name__ == "__main__":
    out = build()
    o = out[(out.batter == 660271) & (out.pitch_type == "FC") & (out.plate_x > 0.25)]
    print(f"\nOhtani inside cutters: {len(o)}  mean swing grade={o.swing_grade.mean():.1f}  "
          f"whiff%={o.whiff.mean()*100:.0f}  mean model whiff prob={o.whiff_prob.mean():.0f}%")
