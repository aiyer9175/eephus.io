import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


WOBA_WEIGHTS = {
    "Out": 0.000,
    "Error": 0.000,
    "FieldersChoice": 0.000,
    "Sacrifice": 0.000,
    "Single": 0.880,
    "Double": 1.250,
    "Triple": 1.590,
    "HomeRun": 2.030,
    "Homerun": 2.030,
}


DEFAULT_FEATURES = [
    "ExitSpeed",
    "Angle",
    "Direction",
    "Distance",
    "HangTime",
    "BatterSide",
    "PitcherThrows",
    "TaggedHitType",
]


def build_training_frame(input_csv):
    df = pd.read_csv(input_csv, low_memory=False, na_values=["NA", "Undefined", ""])

    bip = df[
        (df["PitchCall"] == "InPlay")
        & df["PlayResult"].isin(WOBA_WEIGHTS)
        & df["ExitSpeed"].notna()
        & df["Angle"].notna()
    ].copy()

    bip["woba_value"] = bip["PlayResult"].map(WOBA_WEIGHTS)
    return bip


def train_model(bip):
    features = [col for col in DEFAULT_FEATURES if col in bip.columns]
    numeric_features = [
        col
        for col in features
        if col in ["ExitSpeed", "Angle", "Direction", "Distance", "HangTime"]
        and bip[col].notna().sum() > 0
        and bip[col].nunique(dropna=True) >= 2
    ]
    categorical_features = [
        col for col in features
        if col not in numeric_features
        and bip[col].notna().sum() > 0
        and bip[col].nunique(dropna=True) >= 1
    ]
    features = numeric_features + categorical_features
    if not features:
        raise ValueError("No usable model features found after filtering empty/constant columns.")

    X = bip[features]
    y = bip["woba_value"]

    if "GameID" in bip.columns and bip["GameID"].nunique(dropna=True) >= 2:
        splitter = GroupShuffleSplit(test_size=0.2, n_splits=1, random_state=42)
        train_idx, test_idx = next(splitter.split(X, y, groups=bip["GameID"]))
    else:
        train_idx, test_idx = train_test_split(
            np.arange(len(bip)), test_size=0.2, random_state=42
        )

    preprocess = ColumnTransformer(
        transformers=[
            ("num", "passthrough", numeric_features),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
        ]
    )

    model = Pipeline(
        steps=[
            ("prep", preprocess),
            (
                "model",
                HistGradientBoostingRegressor(
                    max_iter=500,
                    learning_rate=0.03,
                    max_leaf_nodes=31,
                    l2_regularization=0.05,
                    random_state=42,
                ),
            ),
        ]
    )

    model.fit(X.iloc[train_idx], y.iloc[train_idx])

    pred = np.clip(model.predict(X.iloc[test_idx]), 0, 2.1)
    metrics = {
        "training_rows": int(len(bip)),
        "features": features,
        "mae": float(mean_absolute_error(y.iloc[test_idx], pred)),
        "rmse": float(np.sqrt(mean_squared_error(y.iloc[test_idx], pred))),
        "r2": float(r2_score(y.iloc[test_idx], pred)),
    }

    artifact = {
        "model": model,
        "features": features,
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "woba_weights": WOBA_WEIGHTS,
        "prediction_clip": [0.0, 2.1],
        "model_type": "contact_xwoba",
    }

    return artifact, metrics


def main():
    parser = argparse.ArgumentParser(description="Train and export a contact xwOBA model.")
    parser.add_argument("--input", required=True, help="Path to the TrackMan-style CSV.")
    parser.add_argument("--output", default="xwoba_model.pkl", help="Output pickle path.")
    parser.add_argument(
        "--metrics-output",
        default="xwoba_model_metrics.json",
        help="Output metrics JSON path.",
    )
    args = parser.parse_args()

    bip = build_training_frame(args.input)
    if bip.empty:
        raise ValueError("No usable in-play rows found for xwOBA training.")

    artifact, metrics = train_model(bip)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)

    metrics_path = Path(args.metrics_output)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(json.dumps(metrics, indent=2))
    print(f"Saved model to {output_path}")
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
