import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict


INPUT = Path("B1G 2025.csv")
OUT_DIR = Path("stuff_plus_outputs")
QUALIFIER_PITCHES = 500
PITCH_TYPE_QUALIFIER = 50


USECOLS = [
    "Pitcher",
    "PitcherId",
    "PitcherThrows",
    "PitcherTeam",
    "TaggedPitchType",
    "PitchCall",
    "KorBB",
    "PlayResult",
    "Balls",
    "Strikes",
    "RelSpeed",
    "EffectiveVelo",
    "SpinRate",
    "SpinAxis",
    "RelHeight",
    "RelSide",
    "Extension",
    "InducedVertBreak",
    "HorzBreak",
    "VertApprAngle",
    "HorzApprAngle",
    "x0",
    "z0",
    "ax0",
    "az0",
]


PITCH_TYPE_MAP = {
    "FourSeamFastBall": "Fastball",
    "Four-Seam": "Fastball",
    "Fastball": "Fastball",
    "SInker": "Sinker",
    "Sinker": "Sinker",
    "Changeup": "ChangeUp",
    "ChangeUp": "ChangeUp",
    "Slider": "Slider",
    "Sweeper": "Sweeper",
    "Curveball": "Curveball",
    "Cutter": "Cutter",
    "Splitter": "Splitter",
}

FASTBALL_TYPES = {"Fastball", "Sinker"}


def clean_pitch_type(value: object) -> object:
    if pd.isna(value):
        return np.nan
    return PITCH_TYPE_MAP.get(str(value), np.nan)


def pitch_rv_proxy(row: pd.Series) -> float:
    """Crude batter run-value proxy. Positive is better for hitter, worse for pitcher."""
    korbb = row["KorBB"]
    if korbb == "Strikeout":
        return -0.27
    if korbb == "Walk":
        return 0.33

    call = row["PitchCall"]
    result = row["PlayResult"]
    balls = row["Balls"]
    strikes = row["Strikes"]

    if call in {"BallCalled", "BallinDirt"}:
        return 0.06 if balls != 3 else 0.33
    if call == "HitByPitch":
        return 0.33
    if call == "BallIntentional":
        return 0.10
    if call in {"StrikeCalled", "StrikeSwinging", "StrikeC'alled"}:
        return -0.07 if strikes != 2 else -0.27
    if call in {"FoulBallNotFieldable", "FoulBallFieldable", "FoulBall"}:
        return -0.02 if strikes != 2 else 0.00

    if call == "InPlay":
        return {
            "Out": -0.27,
            "FieldersChoice": -0.10,
            "Sacrifice": 0.05,
            "Error": 0.47,
            "Single": 0.47,
            "Double": 0.75,
            "Triple": 1.05,
            "HomeRun": 1.40,
            "Homerun": 1.40,
        }.get(result, 0.00)

    return np.nan


def robust_z(series: pd.Series) -> pd.Series:
    median = series.median()
    iqr = series.quantile(0.75) - series.quantile(0.25)
    scale = iqr / 1.349 if iqr and not math.isclose(iqr, 0) else series.std()
    if not scale or pd.isna(scale) or math.isclose(scale, 0):
        return series * 0
    return (series - median) / scale


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    df = pd.read_csv(INPUT, usecols=lambda col: col in USECOLS, low_memory=False)
    df["pitch_type"] = df["TaggedPitchType"].map(clean_pitch_type)
    df = df.dropna(subset=["Pitcher", "PitcherId", "PitcherThrows", "pitch_type"])

    numeric_cols = [
        "RelSpeed",
        "EffectiveVelo",
        "SpinRate",
        "SpinAxis",
        "RelHeight",
        "RelSide",
        "Extension",
        "InducedVertBreak",
        "HorzBreak",
        "VertApprAngle",
        "HorzApprAngle",
        "x0",
        "z0",
        "ax0",
        "az0",
        "Balls",
        "Strikes",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Mirror horizontal dimensions for left-handed pitchers so arm-side/glove-side
    # shapes have comparable signs across handedness.
    left = df["PitcherThrows"].eq("Left")
    for col in ["RelSide", "HorzBreak", "HorzApprAngle", "x0", "ax0"]:
        df[f"{col}_mirrored"] = df[col]
        df.loc[left, f"{col}_mirrored"] = -df.loc[left, col]

    df["spin_sin"] = np.sin(np.deg2rad(df["SpinAxis"]))
    df["spin_cos"] = np.cos(np.deg2rad(df["SpinAxis"]))
    df["raw_movement"] = np.sqrt(
        df["InducedVertBreak"].pow(2) + df["HorzBreak_mirrored"].pow(2)
    )

    fb = df[df["pitch_type"].isin(FASTBALL_TYPES)].copy()
    fb_usage = (
        fb.groupby(["PitcherId", "pitch_type"])
        .size()
        .rename("n")
        .reset_index()
        .sort_values(["PitcherId", "n"], ascending=[True, False])
    )
    primary_fb = fb_usage.drop_duplicates("PitcherId")[["PitcherId", "pitch_type"]]
    primary_fb = primary_fb.rename(columns={"pitch_type": "primary_fb_type"})
    fb = fb.merge(primary_fb, on="PitcherId", how="inner")
    fb = fb[fb["pitch_type"].eq(fb["primary_fb_type"])]
    fb_ref = (
        fb.groupby("PitcherId")
        .agg(
            fb_velo=("RelSpeed", "mean"),
            fb_ax=("ax0_mirrored", "mean"),
            fb_az=("az0", "mean"),
            fb_ivb=("InducedVertBreak", "mean"),
            fb_hb=("HorzBreak_mirrored", "mean"),
        )
        .reset_index()
    )
    df = df.merge(fb_ref, on="PitcherId", how="left")
    df["speed_diff"] = df["RelSpeed"] - df["fb_velo"]
    df["ax_diff"] = df["ax0_mirrored"] - df["fb_ax"]
    df["az_diff"] = df["az0"] - df["fb_az"]
    df["ivb_diff"] = df["InducedVertBreak"] - df["fb_ivb"]
    df["hb_diff"] = df["HorzBreak_mirrored"] - df["fb_hb"]

    df["rv_proxy"] = df.apply(pitch_rv_proxy, axis=1)
    feature_cols = [
        "RelSpeed",
        "EffectiveVelo",
        "SpinRate",
        "Extension",
        "RelHeight",
        "RelSide_mirrored",
        "InducedVertBreak",
        "HorzBreak_mirrored",
        "raw_movement",
        "VertApprAngle",
        "HorzApprAngle_mirrored",
        "x0_mirrored",
        "z0",
        "ax0_mirrored",
        "az0",
        "spin_sin",
        "spin_cos",
        "speed_diff",
        "ax_diff",
        "az_diff",
        "ivb_diff",
        "hb_diff",
    ]
    model_df = df.dropna(subset=feature_cols + ["rv_proxy"]).copy()

    for col in feature_cols:
        model_df[f"{col}_rz"] = model_df.groupby("pitch_type")[col].transform(robust_z)
    rz_cols = [f"{col}_rz" for col in feature_cols]
    x = pd.get_dummies(model_df[["pitch_type"] + rz_cols], columns=["pitch_type"], dtype=float)
    y = model_df["rv_proxy"].to_numpy()
    groups = model_df["PitcherId"].to_numpy()

    n_groups = model_df["PitcherId"].nunique()
    n_splits = min(5, n_groups)
    model = HistGradientBoostingRegressor(
        learning_rate=0.045,
        max_iter=300,
        l2_regularization=0.05,
        max_leaf_nodes=31,
        random_state=17,
    )
    cv = GroupKFold(n_splits=n_splits)
    pred = cross_val_predict(model, x, y, groups=groups, cv=cv)
    model_df["xrv_proxy"] = pred

    mean = model_df["xrv_proxy"].mean()
    std = model_df["xrv_proxy"].std()
    model_df["stuff_plus"] = 100 - 10 * ((model_df["xrv_proxy"] - mean) / std)

    metrics = {
        "rows_in_file": len(df),
        "model_rows": len(model_df),
        "qualified_pitchers_500": int((model_df.groupby("PitcherId").size() >= QUALIFIER_PITCHES).sum()),
        "cv_r2": float(r2_score(y, pred)),
        "cv_mae": float(mean_absolute_error(y, pred)),
    }
    pd.Series(metrics).to_csv(OUT_DIR / "model_summary.csv", header=["value"])

    agg = (
        model_df.groupby(["PitcherId", "Pitcher", "PitcherTeam", "PitcherThrows"])
        .agg(
            pitches=("stuff_plus", "size"),
            stuff_plus=("stuff_plus", "mean"),
            avg_velocity=("RelSpeed", "mean"),
            avg_extension=("Extension", "mean"),
            avg_vaa=("VertApprAngle", "mean"),
            avg_raw_movement=("raw_movement", "mean"),
            whiff_rate=("PitchCall", lambda s: (s == "StrikeSwinging").mean()),
        )
        .reset_index()
    )
    agg["stuff_plus"] = agg["stuff_plus"].round(1)
    for col in ["avg_velocity", "avg_extension", "avg_vaa", "avg_raw_movement", "whiff_rate"]:
        agg[col] = agg[col].round(3)
    leaders = agg[agg["pitches"].ge(QUALIFIER_PITCHES)].sort_values("stuff_plus", ascending=False)
    leaders.to_csv(OUT_DIR / "pitcher_stuff_plus_leaders_500.csv", index=False)

    by_pitch = (
        model_df.groupby(["PitcherId", "Pitcher", "PitcherTeam", "PitcherThrows", "pitch_type"])
        .agg(
            pitches=("stuff_plus", "size"),
            stuff_plus=("stuff_plus", "mean"),
            avg_velocity=("RelSpeed", "mean"),
            avg_extension=("Extension", "mean"),
            avg_vaa=("VertApprAngle", "mean"),
            avg_raw_movement=("raw_movement", "mean"),
            whiff_rate=("PitchCall", lambda s: (s == "StrikeSwinging").mean()),
        )
        .reset_index()
    )
    by_pitch["stuff_plus"] = by_pitch["stuff_plus"].round(1)
    for col in ["avg_velocity", "avg_extension", "avg_vaa", "avg_raw_movement", "whiff_rate"]:
        by_pitch[col] = by_pitch[col].round(3)
    by_pitch = by_pitch[by_pitch["pitches"].ge(PITCH_TYPE_QUALIFIER)]
    by_pitch = by_pitch.sort_values(["pitch_type", "stuff_plus"], ascending=[True, False])
    by_pitch.to_csv(OUT_DIR / "pitch_type_stuff_plus_leaders_50.csv", index=False)

    print(pd.Series(metrics).to_string())
    print("\nTop 20 qualified pitchers:")
    print(leaders.head(20).to_string(index=False))
    print("\nTop pitch by type:")
    print(by_pitch.groupby("pitch_type").head(5).to_string(index=False))


if __name__ == "__main__":
    main()
