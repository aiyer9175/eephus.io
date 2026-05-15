from pathlib import Path

import numpy as np
import pandas as pd


INPUT = Path("B1G 2025.csv")
OUT_DIR = Path("bat_plus_outputs")
PITCH_QUALIFIER = 200
BIP_QUALIFIER = 30


USECOLS = [
    "Batter",
    "BatterId",
    "BatterSide",
    "BatterTeam",
    "PitchCall",
    "PlayResult",
    "TaggedHitType",
    "KorBB",
    "Balls",
    "Strikes",
    "PlateLocHeight",
    "PlateLocSide",
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


def plus_scale(series: pd.Series) -> pd.Series:
    std = series.std()
    if not std or pd.isna(std):
        return series * 0 + 100
    return 100 + 10 * ((series - series.mean()) / std)


def batted_ball_value(df: pd.DataFrame) -> pd.Series:
    """Physical contact score from exit speed and launch angle only.

    This intentionally avoids using the play result, so it behaves like a
    batted-ball-quality metric rather than a descriptive batting line.
    """
    ev = df["ExitSpeed"]
    la = df["Angle"]
    ev_z = (ev - ev.mean()) / ev.std()

    # Launch angle quality peaks around hard line drives and lower fly balls.
    # The second, smaller term gives very hard high flies some credit.
    launch_shape = np.exp(-((la - 16) / 18) ** 2) + 0.35 * np.exp(-((la - 27) / 13) ** 2)
    launch_z = (launch_shape - launch_shape.mean()) / launch_shape.std()

    return 0.68 * ev_z + 0.32 * launch_z


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    df = pd.read_csv(INPUT, usecols=lambda col: col in USECOLS, low_memory=False)
    df = df.dropna(subset=["Batter", "BatterId", "BatterSide", "BatterTeam"]).copy()

    numeric_cols = [
        "Balls",
        "Strikes",
        "PlateLocHeight",
        "PlateLocSide",
        "ExitSpeed",
        "Angle",
        "Direction",
        "Distance",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Generic strike-zone approximation for college TrackMan/Hawkeye exports.
    # This should be swapped for batter-specific zones if those fields are added.
    df["zone"] = df["PlateLocSide"].abs().le(0.83) & df["PlateLocHeight"].between(1.5, 3.5)
    df["swing"] = df["PitchCall"].isin(SWING_CALLS)
    df["contact"] = df["PitchCall"].isin(
        {"InPlay", "FoulBallNotFieldable", "FoulBallFieldable", "FoulBall"}
    )

    decision_mask = df["PlateLocSide"].notna() & df["PlateLocHeight"].notna()
    df["decision_value"] = np.nan
    df.loc[decision_mask & df["zone"] & df["swing"], "decision_value"] = 1.0
    df.loc[decision_mask & df["zone"] & ~df["swing"], "decision_value"] = -1.0
    df.loc[decision_mask & ~df["zone"] & ~df["swing"], "decision_value"] = 1.0
    df.loc[decision_mask & ~df["zone"] & df["swing"], "decision_value"] = -1.0
    df.loc[decision_mask & ~df["zone"] & df["PitchCall"].eq("StrikeSwinging"), "decision_value"] = -1.25

    bip = df["ExitSpeed"].notna() & df["Angle"].notna()
    df["contact_quality_raw"] = np.nan
    df.loc[bip, "contact_quality_raw"] = batted_ball_value(df.loc[bip])

    hitter = (
        df.groupby(["BatterId", "Batter", "BatterTeam", "BatterSide"])
        .agg(
            pitches_seen=("PitchCall", "size"),
            decision_pitches=("decision_value", "count"),
            decision_raw=("decision_value", "mean"),
            batted_balls=("contact_quality_raw", "count"),
            contact_raw=("contact_quality_raw", "mean"),
            avg_ev=("ExitSpeed", "mean"),
            max_ev=("ExitSpeed", "max"),
            avg_la=("Angle", "mean"),
            hard_hit_rate=("ExitSpeed", lambda s: s.dropna().ge(95).mean()),
            sweet_spot_rate=("Angle", lambda s: s.dropna().between(8, 32).mean()),
            barrelish_rate=(
                "ExitSpeed",
                lambda s: np.nan
                if (s.notna() & df.loc[s.index, "Angle"].notna()).sum() == 0
                else (
                    s.notna()
                    & df.loc[s.index, "Angle"].notna()
                    & s.ge(95)
                    & df.loc[s.index, "Angle"].between(8, 32)
                ).sum()
                / (s.notna() & df.loc[s.index, "Angle"].notna()).sum(),
            ),
            swing_rate=("swing", "mean"),
            whiff_rate=("PitchCall", lambda s: s.eq("StrikeSwinging").mean()),
        )
        .reset_index()
    )

    # Recompute plate-discipline rates with clear denominators.
    group_cols = ["BatterId", "Batter", "BatterTeam", "BatterSide"]
    out_zone = df[decision_mask & ~df["zone"]].groupby(group_cols)
    in_zone = df[decision_mask & df["zone"]].groupby(group_cols)
    hitter = hitter.merge(
        out_zone["swing"].mean().rename("chase_rate").reset_index(),
        on=group_cols,
        how="left",
    )
    hitter = hitter.merge(
        in_zone["swing"].mean().rename("zone_swing_rate").reset_index(),
        on=group_cols,
        how="left",
    )
    hitter = hitter.merge(
        out_zone["PitchCall"].size().rename("out_zone_pitches").reset_index(),
        on=group_cols,
        how="left",
    )
    hitter = hitter.merge(
        in_zone["PitchCall"].size().rename("zone_pitches").reset_index(),
        on=group_cols,
        how="left",
    )

    hitter["decision_plus"] = plus_scale(hitter["decision_raw"])
    hitter["contact_plus"] = plus_scale(hitter["contact_raw"])
    hitter["bat_plus"] = 0.40 * hitter["decision_plus"] + 0.60 * hitter["contact_plus"]

    output_cols = [
        "BatterId",
        "Batter",
        "BatterTeam",
        "BatterSide",
        "pitches_seen",
        "batted_balls",
        "bat_plus",
        "decision_plus",
        "contact_plus",
        "avg_ev",
        "max_ev",
        "avg_la",
        "hard_hit_rate",
        "sweet_spot_rate",
        "barrelish_rate",
        "chase_rate",
        "zone_swing_rate",
        "swing_rate",
        "whiff_rate",
    ]
    for col in [
        "bat_plus",
        "decision_plus",
        "contact_plus",
        "avg_ev",
        "max_ev",
        "avg_la",
        "hard_hit_rate",
        "sweet_spot_rate",
        "barrelish_rate",
        "chase_rate",
        "zone_swing_rate",
        "swing_rate",
        "whiff_rate",
    ]:
        hitter[col] = hitter[col].round(3)

    qualified = hitter[
        hitter["pitches_seen"].ge(PITCH_QUALIFIER) & hitter["batted_balls"].ge(BIP_QUALIFIER)
    ].sort_values("bat_plus", ascending=False)
    qualified[output_cols].to_csv(OUT_DIR / "bat_plus_leaders_200p_30bip.csv", index=False)

    all_hitters = hitter.sort_values("bat_plus", ascending=False)
    all_hitters[output_cols].to_csv(OUT_DIR / "bat_plus_all_hitters.csv", index=False)

    summary = pd.Series(
        {
            "rows_in_file": len(df),
            "tracked_batted_balls": int(bip.sum()),
            "hitters": int(hitter["BatterId"].nunique()),
            "qualified_hitters_200p_30bip": int(len(qualified)),
            "bat_plus_weight_contact": 0.60,
            "bat_plus_weight_decision": 0.40,
            "zone_horizontal_half_width_ft": 0.83,
            "zone_bottom_ft": 1.5,
            "zone_top_ft": 3.5,
        }
    )
    summary.to_csv(OUT_DIR / "bat_plus_summary.csv", header=["value"])

    print(summary.to_string())
    print("\nTop 25 qualified Bat+ hitters:")
    print(qualified[output_cols].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
