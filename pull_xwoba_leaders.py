from pathlib import Path
import pickle

import numpy as np
import pandas as pd


MODEL_PATH = Path("xwoba_model.pkl")
OUT_DIR = Path("hitter_model_outputs")
NCAA_FILES = [
    ("NCAA_05_08.csv", 2024, "NCAA"),
    ("B1G 2025.csv", 2025, "B1G"),
]

BIP_QUALIFIER = 30
CHUNK_SIZE = 200_000

USECOLS = [
    "BatterId",
    "Batter",
    "BatterTeam",
    "BatterSide",
    "PitcherThrows",
    "TaggedHitType",
    "PlayResult",
    "ExitSpeed",
    "Angle",
    "Direction",
    "Distance",
    "HangTime",
]


def load_model() -> dict:
    with MODEL_PATH.open("rb") as handle:
        return pickle.load(handle)


def score_file(path: str, season: int, source: str, model_bundle: dict) -> pd.DataFrame:
    model = model_bundle["model"]
    features = model_bundle["features"]
    prediction_low, prediction_high = model_bundle.get("prediction_clip", [0.0, 2.1])
    frames = []

    for chunk in pd.read_csv(path, usecols=lambda col: col in USECOLS, chunksize=CHUNK_SIZE, low_memory=False):
        chunk = chunk.dropna(
            subset=[
                "BatterId",
                "Batter",
                "BatterTeam",
                "BatterSide",
                "PitcherThrows",
                "TaggedHitType",
                "ExitSpeed",
                "Angle",
            ]
        ).copy()
        if chunk.empty:
            continue

        for col in ["ExitSpeed", "Angle", "Direction", "Distance", "HangTime"]:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

        model_input = chunk[features].copy()
        chunk["xwoba"] = np.clip(model.predict(model_input), prediction_low, prediction_high)
        chunk["Season"] = season
        chunk["Source"] = source
        frames.append(
            chunk[
                [
                    "Season",
                    "Source",
                    "BatterId",
                    "Batter",
                    "BatterTeam",
                    "BatterSide",
                    "TaggedHitType",
                    "PlayResult",
                    "ExitSpeed",
                    "Angle",
                    "xwoba",
                ]
            ]
        )

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def aggregate(scored: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    grouped = scored.groupby(group_cols, dropna=False)
    out = grouped.agg(
        batted_balls=("xwoba", "size"),
        xwoba=("xwoba", "mean"),
        xwoba_sum=("xwoba", "sum"),
        avg_ev=("ExitSpeed", "mean"),
        max_ev=("ExitSpeed", "max"),
        avg_la=("Angle", "mean"),
        hard_hit_rate=("ExitSpeed", lambda s: s.ge(95).mean()),
        sweet_spot_rate=("Angle", lambda s: s.between(8, 32).mean()),
    ).reset_index()

    out["xwoba_plus"] = 100 + 10 * ((out["xwoba"] - out["xwoba"].mean()) / out["xwoba"].std())
    return out.sort_values(["xwoba", "batted_balls"], ascending=[False, False])


def rounded(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    model_bundle = load_model()

    scored_frames = []
    for path, season, source in NCAA_FILES:
        csv_path = Path(path)
        if not csv_path.exists():
            continue
        print(f"Scoring {csv_path}...")
        scored = score_file(path, season, source, model_bundle)
        if not scored.empty:
            scored_frames.append(scored)

    if not scored_frames:
        raise FileNotFoundError("No scoreable NCAA batted-ball data found.")

    scored_all = pd.concat(scored_frames, ignore_index=True)
    rounded(scored_all).to_csv(OUT_DIR / "ncaa_batted_ball_xwoba.csv", index=False)

    season = aggregate(
        scored_all,
        ["Season", "Source", "BatterId", "Batter", "BatterTeam", "BatterSide"],
    )
    rounded(season).to_csv(OUT_DIR / "ncaa_xwoba_season_leaders.csv", index=False)

    overall = aggregate(scored_all, ["BatterId", "Batter", "BatterTeam", "BatterSide"])
    qualified = overall[overall["batted_balls"].ge(BIP_QUALIFIER)]
    rounded(qualified).to_csv(OUT_DIR / "ncaa_xwoba_leaders.csv", index=False)

    summary = pd.Series(
        {
            "scored_batted_balls": len(scored_all),
            "hitters": int(scored_all["BatterId"].nunique()),
            "qualified_hitters": int(len(qualified)),
            "bip_qualifier": BIP_QUALIFIER,
            "model_type": model_bundle.get("model_type", "unknown"),
        }
    )
    summary.to_csv(OUT_DIR / "xwoba_leader_summary.csv", header=["value"])

    display_cols = [
        "Batter",
        "BatterTeam",
        "BatterSide",
        "batted_balls",
        "xwoba",
        "xwoba_plus",
        "avg_ev",
        "max_ev",
        "avg_la",
        "hard_hit_rate",
        "sweet_spot_rate",
    ]
    print(summary.to_string())
    print("\nTop 25 NCAA contact xwOBA leaders:")
    print(rounded(qualified[display_cols].head(25)).to_string(index=False))


if __name__ == "__main__":
    main()
