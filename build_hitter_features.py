from pathlib import Path

import numpy as np
import pandas as pd


OUT_DIR = Path("hitter_model_outputs")
NCAA_FILES = [
    ("NCAA_05_08.csv", 2024, "NCAA"),
    ("B1G 2025.csv", 2025, "B1G"),
]

PITCH_QUALIFIER = 200
BIP_QUALIFIER = 30

USECOLS = [
    "Date",
    "Batter",
    "BatterId",
    "BatterSide",
    "BatterTeam",
    "PitcherThrows",
    "TaggedPitchType",
    "PitchCall",
    "KorBB",
    "TaggedHitType",
    "PlayResult",
    "Balls",
    "Strikes",
    "PlateLocHeight",
    "PlateLocSide",
    "RelSpeed",
    "ExitSpeed",
    "Angle",
    "Direction",
    "Distance",
]

SWING_CALLS = {
    "InPlay",
    "StrikeSwinging",
    "FoulBallNotFieldable",
    "FoulBallFieldable",
    "FoulBall",
}

CONTACT_CALLS = {"InPlay", "FoulBallNotFieldable", "FoulBallFieldable", "FoulBall"}

PITCH_TYPE_MAP = {
    "FourSeamFastBall": "Fastball",
    "Four-Seam": "Fastball",
    "Fastball": "Fastball",
    "TwoSeamFastBall": "Sinker",
    "OneSeamFastBall": "Sinker",
    "SInker": "Sinker",
    "Sinker": "Sinker",
    "Changeup": "ChangeUp",
    "ChangeUp": "ChangeUp",
    "Slider": "Slider",
    "Sweeper": "Sweeper",
    "Curveball": "Curveball",
    "Cutter": "Cutter",
    "Splitter": "Splitter",
    "Knuckleball": "Other",
    "Other": "Other",
}

PITCH_GROUPS = {
    "Fastball": "Fastball",
    "Sinker": "Fastball",
    "Cutter": "Breaking",
    "Slider": "Breaking",
    "Sweeper": "Breaking",
    "Curveball": "Breaking",
    "ChangeUp": "Offspeed",
    "Splitter": "Offspeed",
}


def plus_scale(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    values = series.astype(float)
    std = values.std()
    if not std or pd.isna(std):
        return values * 0 + 100
    z = (values - values.mean()) / std
    if not higher_is_better:
        z = -z
    return 100 + 10 * z


def clean_pitch_type(value: object) -> object:
    if pd.isna(value):
        return np.nan
    return PITCH_TYPE_MAP.get(str(value), np.nan)


def load_ncaa() -> pd.DataFrame:
    frames = []
    for path, season, source in NCAA_FILES:
        csv_path = Path(path)
        if not csv_path.exists():
            continue
        print(f"Reading {csv_path}...")
        df = pd.read_csv(csv_path, usecols=lambda col: col in USECOLS, low_memory=False)
        df["Season"] = season
        df["Source"] = source
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No NCAA CSV files found.")
    return pd.concat(frames, ignore_index=True)


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = [
        "Balls",
        "Strikes",
        "PlateLocHeight",
        "PlateLocSide",
        "RelSpeed",
        "ExitSpeed",
        "Angle",
        "Direction",
        "Distance",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["BatterId"] = pd.to_numeric(df["BatterId"], errors="coerce")
    df = df.dropna(subset=["Batter", "BatterId", "BatterSide", "BatterTeam"]).copy()

    df["pitch_type"] = df["TaggedPitchType"].map(clean_pitch_type)
    df["pitch_group"] = df["pitch_type"].map(PITCH_GROUPS)

    df["zone"] = df["PlateLocSide"].abs().le(0.83) & df["PlateLocHeight"].between(1.5, 3.5)
    df["shadow"] = df["PlateLocSide"].abs().between(0.708, 1.083) | df[
        "PlateLocHeight"
    ].between(1.25, 1.75) | df["PlateLocHeight"].between(3.25, 3.75)
    df["location_tracked"] = df["PlateLocSide"].notna() & df["PlateLocHeight"].notna()
    df["swing"] = df["PitchCall"].isin(SWING_CALLS)
    df["contact"] = df["PitchCall"].isin(CONTACT_CALLS)
    df["whiff"] = df["PitchCall"].eq("StrikeSwinging")
    df["bip"] = df["ExitSpeed"].notna() & df["Angle"].notna()
    df["hard_hit"] = df["ExitSpeed"].ge(95)
    df["sweet_spot"] = df["Angle"].between(8, 32)
    df["barrelish"] = df["hard_hit"] & df["sweet_spot"]
    df["gb"] = df["TaggedHitType"].eq("GroundBall")
    df["ld"] = df["TaggedHitType"].eq("LineDrive")
    df["fb"] = df["TaggedHitType"].eq("FlyBall")
    df["popup"] = df["TaggedHitType"].eq("Popup")
    df["pull_side"] = np.where(
        df["BatterSide"].eq("Right"),
        df["Direction"].lt(-15),
        np.where(df["BatterSide"].eq("Left"), df["Direction"].gt(15), np.nan),
    )
    df["oppo_side"] = np.where(
        df["BatterSide"].eq("Right"),
        df["Direction"].gt(15),
        np.where(df["BatterSide"].eq("Left"), df["Direction"].lt(-15), np.nan),
    )

    df["decision_value"] = np.nan
    mask = df["location_tracked"]
    df.loc[mask & df["zone"] & df["swing"], "decision_value"] = 1.0
    df.loc[mask & df["zone"] & ~df["swing"], "decision_value"] = -1.0
    df.loc[mask & ~df["zone"] & ~df["swing"], "decision_value"] = 1.0
    df.loc[mask & ~df["zone"] & df["swing"], "decision_value"] = -1.0
    df.loc[mask & ~df["zone"] & df["whiff"], "decision_value"] = -1.25
    return df


def rate(numer: pd.Series, denom: pd.Series) -> float:
    d = denom.sum()
    if d == 0:
        return np.nan
    return numer.sum() / d


def aggregate_hitter(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    grouped = df.groupby(group_cols, dropna=False, sort=False)
    for keys, g in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_data = dict(zip(group_cols, keys))
        swings = g["swing"]
        tracked = g["location_tracked"]
        zone = g["zone"] & tracked
        out_zone = ~g["zone"] & tracked
        bip = g["bip"]
        row = {
            **key_data,
            "pitches_seen": len(g),
            "decision_pitches": int(tracked.sum()),
            "swings": int(swings.sum()),
            "contacts": int((g["contact"] & swings).sum()),
            "batted_balls": int(bip.sum()),
            "decision_raw": g["decision_value"].mean(),
            "swing_rate": swings.mean(),
            "chase_rate": rate(g["swing"] & out_zone, out_zone),
            "zone_swing_rate": rate(g["swing"] & zone, zone),
            "shadow_swing_rate": rate(g["swing"] & g["shadow"] & tracked, g["shadow"] & tracked),
            "contact_rate": rate(g["contact"] & swings, swings),
            "zone_contact_rate": rate(g["contact"] & swings & zone, swings & zone),
            "out_zone_contact_rate": rate(g["contact"] & swings & out_zone, swings & out_zone),
            "whiff_rate": rate(g["whiff"], swings),
            "called_strike_rate": g["PitchCall"].eq("StrikeCalled").mean(),
            "avg_ev": g.loc[bip, "ExitSpeed"].mean(),
            "ev90": g.loc[bip, "ExitSpeed"].quantile(0.9),
            "max_ev": g.loc[bip, "ExitSpeed"].max(),
            "avg_la": g.loc[bip, "Angle"].mean(),
            "hard_hit_rate": g.loc[bip, "hard_hit"].mean(),
            "sweet_spot_rate": g.loc[bip, "sweet_spot"].mean(),
            "barrelish_rate": g.loc[bip, "barrelish"].mean(),
            "gb_rate": g.loc[bip, "gb"].mean(),
            "ld_rate": g.loc[bip, "ld"].mean(),
            "fb_rate": g.loc[bip, "fb"].mean(),
            "popup_rate": g.loc[bip, "popup"].mean(),
            "pull_rate": g.loc[bip, "pull_side"].mean(),
            "oppo_rate": g.loc[bip, "oppo_side"].mean(),
            "avg_pitch_speed_seen": g["RelSpeed"].mean(),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def add_component_scores(hitter: pd.DataFrame) -> pd.DataFrame:
    out = hitter.copy()
    out["decision_plus"] = plus_scale(out["decision_raw"])

    contact_raw = (
        plus_scale(out["contact_rate"])
        + plus_scale(out["zone_contact_rate"])
        + plus_scale(out["whiff_rate"], higher_is_better=False)
    ) / 3
    damage_raw = (
        plus_scale(out["avg_ev"])
        + plus_scale(out["ev90"])
        + plus_scale(out["max_ev"])
        + plus_scale(out["hard_hit_rate"])
        + plus_scale(out["barrelish_rate"])
        + plus_scale(out["popup_rate"], higher_is_better=False)
    ) / 6

    out["contact_ability_plus"] = contact_raw
    out["damage_plus"] = damage_raw
    out["hitter_plus"] = (
        0.35 * out["decision_plus"]
        + 0.25 * out["contact_ability_plus"]
        + 0.40 * out["damage_plus"]
    )
    return out


def rounded(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    df = add_flags(load_ncaa())
    print(f"Rows after cleaning: {len(df):,}")

    season_cols = ["Season", "Source", "BatterId", "Batter", "BatterTeam", "BatterSide"]
    hitter_season = aggregate_hitter(df, season_cols)
    hitter_season = add_component_scores(hitter_season)
    hitter_season = hitter_season.sort_values(["Season", "hitter_plus"], ascending=[True, False])
    rounded(hitter_season).to_csv(OUT_DIR / "ncaa_hitter_season_features.csv", index=False)

    overall_cols = ["BatterId", "Batter", "BatterTeam", "BatterSide"]
    hitter_overall = aggregate_hitter(df, overall_cols)
    hitter_overall = add_component_scores(hitter_overall)
    qualified = hitter_overall[
        hitter_overall["pitches_seen"].ge(PITCH_QUALIFIER)
        & hitter_overall["batted_balls"].ge(BIP_QUALIFIER)
    ].sort_values("hitter_plus", ascending=False)
    rounded(qualified).to_csv(OUT_DIR / "ncaa_hitter_plus_leaders.csv", index=False)

    pitch_group = df.dropna(subset=["pitch_group"])
    hitter_pitch_group = aggregate_hitter(
        pitch_group,
        ["Season", "BatterId", "Batter", "BatterTeam", "BatterSide", "pitch_group"],
    )
    hitter_pitch_group = add_component_scores(hitter_pitch_group)
    hitter_pitch_group = hitter_pitch_group[
        hitter_pitch_group["pitches_seen"].ge(50) & hitter_pitch_group["batted_balls"].ge(10)
    ].sort_values(["Season", "pitch_group", "hitter_plus"], ascending=[True, True, False])
    rounded(hitter_pitch_group).to_csv(
        OUT_DIR / "ncaa_hitter_pitch_group_splits.csv", index=False
    )

    overlap = (
        hitter_season.groupby("BatterId")
        .filter(lambda g: g["Season"].nunique() > 1)
        .sort_values(["BatterId", "Season"])
    )
    rounded(overlap).to_csv(OUT_DIR / "ncaa_hitter_year_over_year_overlap.csv", index=False)

    summary = pd.Series(
        {
            "rows": len(df),
            "hitters": int(df["BatterId"].nunique()),
            "tracked_batted_balls": int(df["bip"].sum()),
            "qualified_overall_hitters": int(len(qualified)),
            "pitch_qualifier": PITCH_QUALIFIER,
            "bip_qualifier": BIP_QUALIFIER,
            "decision_weight": 0.35,
            "contact_ability_weight": 0.25,
            "damage_weight": 0.40,
        }
    )
    summary.to_csv(OUT_DIR / "hitter_model_summary.csv", header=["value"])

    display_cols = [
        "Batter",
        "BatterTeam",
        "BatterSide",
        "pitches_seen",
        "batted_balls",
        "hitter_plus",
        "decision_plus",
        "contact_ability_plus",
        "damage_plus",
        "avg_ev",
        "ev90",
        "max_ev",
        "chase_rate",
        "contact_rate",
        "whiff_rate",
    ]
    print(summary.to_string())
    print("\nTop 25 NCAA Hitter+ leaders:")
    print(rounded(qualified[display_cols].head(25)).to_string(index=False))


if __name__ == "__main__":
    main()
