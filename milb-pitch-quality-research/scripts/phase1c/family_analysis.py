"""Phase 1C, steps 2-3: per-pitcher feature-family aggregates, incremental-
information analysis (block-wise R^2 increments, numpy least-squares -- no
statsmodels/sklearn dependency, consistent with Phase 1B), and redundancy
analysis (pairwise + partial correlation among family-representative
metrics).

Explicitly descriptive, not predictive: R^2 here quantifies how much of a
chosen downstream metric's *variance across pitchers* is explained by each
feature-family block, added in a scientifically motivated order (physical
traits before outcome-derived ones) -- not a model being tuned or evaluated
for leaderboard accuracy, per the charter's own governing philosophy for
this phase.

Population: pitchers with >=100 TRACKED pitches (the "Branch A" population
Phase 1B already established -- AAA + the tracked Low-A/FSL venues) for the
physical-to-outcome chain, since most families here require tracking.
A second, much shorter chain uses the ALL_LEVELS population (>=100 total
pitches, any level) for the one chain available without tracking.

Outputs: reports/phase1c/INCREMENTAL_STATS.json, REDUNDANCY_STATS.json

Usage: python family_analysis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA_CACHE, REPORTS_DIR  # noqa: E402

MIN_TRACKED_PITCHES = 100
MIN_TOTAL_PITCHES = 100
MIN_BATTED_BALLS = 15

PITCH_FAMILY = {
    "FF": "fastball", "SI": "fastball", "FT": "fastball", "FC": "fastball",
    "SL": "breaking", "CU": "breaking", "KC": "breaking", "ST": "breaking",
    "SV": "breaking", "CS": "breaking", "SC": "breaking",
    "CH": "offspeed", "FS": "offspeed", "FO": "offspeed", "KN": "offspeed",
}
ZONE_STRIKE = {1, 2, 3, 4, 5, 6, 7, 8, 9}
ZONE_CHASE = {11, 12, 13, 14}


def shannon_entropy(shares: pd.Series) -> float:
    p = shares[shares > 0]
    if len(p) == 0:
        return 0.0
    return float(-(p * np.log(p)).sum())


def build_pitcher_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per pitcher, columns = family-representative metrics.
    Tracked-only families are computed on the tracked subset; ALL_LEVELS
    families on all pitches. NaN where a pitcher doesn't clear the minimum
    volume for a given family."""
    df = df.copy()
    df["family"] = df["pitch_type_code"].map(PITCH_FAMILY)

    tracked = df[df["tracked"]]
    tracked_counts = tracked.groupby("pitcher_id").size()
    tracked_eligible = tracked_counts[tracked_counts >= MIN_TRACKED_PITCHES].index

    rows = {}

    # Velocity, Movement, Spin (tracked-only physical families)
    phys = tracked[tracked["pitcher_id"].isin(tracked_eligible)]
    g = phys.groupby("pitcher_id")
    rows["velocity"] = g["start_speed"].mean()
    rows["movement_pfx_x"] = g["pfx_x"].mean()
    rows["movement_pfx_z"] = g["pfx_z"].mean()
    rows["spin_rate"] = g["spin_rate"].mean()

    # Pitch mix / diversity (tracked-only, needs pitch_type_code)
    fam_counts = phys.dropna(subset=["family"]).groupby(["pitcher_id", "family"]).size().unstack(fill_value=0)
    fam_shares = fam_counts.div(fam_counts.sum(axis=1), axis=0)
    rows["share_fastball"] = fam_shares.get("fastball", pd.Series(dtype=float))
    rows["share_breaking"] = fam_shares.get("breaking", pd.Series(dtype=float))
    rows["share_offspeed"] = fam_shares.get("offspeed", pd.Series(dtype=float))
    rows["pitch_entropy"] = fam_shares.apply(shannon_entropy, axis=1)

    # Location / Swing decision (tracked-only, needs zone)
    zoned = phys[phys["zone"].notna()]
    zg = zoned.groupby("pitcher_id")
    rows["zone_rate"] = zg.apply(lambda d: d["zone"].isin(ZONE_STRIKE).mean())
    chase_pool = zoned[zoned["zone"].isin(ZONE_CHASE)]
    rows["chase_rate"] = chase_pool.groupby("pitcher_id")["is_swing"].mean()

    # Whiff ability (ALL_LEVELS in principle, but computed here on the
    # tracked population for a fair like-for-like incremental chain)
    swings = phys[phys["is_swing"]]
    rows["whiff_rate"] = swings.groupby("pitcher_id")["is_whiff"].mean()

    # Weak contact / damage suppression / ground-ball tendency (tracked-only,
    # needs hitData -- restricted to batted balls)
    bip = phys[phys["has_hit_data"]]
    bip_counts = bip.groupby("pitcher_id").size()
    bip_eligible = bip_counts[bip_counts >= MIN_BATTED_BALLS].index
    bip = bip[bip["pitcher_id"].isin(bip_eligible)]
    rows["avg_launch_speed"] = bip.groupby("pitcher_id")["launch_speed"].mean()
    rows["hard_hit_rate"] = bip.groupby("pitcher_id")["is_hard_hit"].mean()
    rows["ground_ball_rate"] = bip.groupby("pitcher_id")["is_ground_ball"].mean()

    table = pd.DataFrame(rows)

    # ALL_LEVELS chain: swing_rate, whiff_rate computed on the full (any-level) population
    all_counts = df.groupby("pitcher_id").size()
    all_eligible = all_counts[all_counts >= MIN_TOTAL_PITCHES].index
    all_df = df[df["pitcher_id"].isin(all_eligible)]
    table["swing_rate_all_levels"] = all_df.groupby("pitcher_id")["is_swing"].mean()
    swings_all = all_df[all_df["is_swing"]]
    table["whiff_rate_all_levels"] = swings_all.groupby("pitcher_id")["is_whiff"].mean()

    return table


def r_squared(y: np.ndarray, X_cols: list[np.ndarray]) -> float:
    """OLS R^2 for y ~ intercept + X_cols (each a 1D array), pairwise
    complete cases only (rows with any NaN across y/X_cols dropped)."""
    mat = np.column_stack([y] + X_cols)
    mat = mat[~np.isnan(mat).any(axis=1)]
    if len(mat) < 10:
        return None, len(mat)
    y_c = mat[:, 0]
    X = mat[:, 1:]
    X_design = np.column_stack([np.ones(len(X)), X])
    coef, *_ = np.linalg.lstsq(X_design, y_c, rcond=None)
    y_hat = X_design @ coef
    ss_res = np.sum((y_c - y_hat) ** 2)
    ss_tot = np.sum((y_c - y_c.mean()) ** 2)
    if ss_tot == 0:
        return None, len(mat)
    return float(1 - ss_res / ss_tot), len(mat)


def incremental_chain(table: pd.DataFrame, target: str, blocks: list[tuple[str, list[str]]]) -> list[dict]:
    """blocks: ordered list of (family_name, [columns]). Returns cumulative
    R^2 and the increment each block adds, in the given order."""
    y = table[target].to_numpy()
    results = []
    cum_cols: list[np.ndarray] = []
    prev_r2 = 0.0
    for family_name, cols in blocks:
        for c in cols:
            cum_cols.append(table[c].to_numpy())
        r2, n = r_squared(y, cum_cols)
        increment = None if r2 is None else round(r2 - prev_r2, 4)
        results.append(
            {
                "family_added": family_name,
                "columns": cols,
                "cumulative_r2": None if r2 is None else round(r2, 4),
                "incremental_r2": increment,
                "n_pitchers": n,
            }
        )
        if r2 is not None:
            prev_r2 = r2
    return results


def partial_correlation(table: pd.DataFrame, x: str, y: str, controls: list[str]) -> dict:
    cols = [x, y] + controls
    sub = table[cols].dropna()
    if len(sub) < 10:
        return {"status": "insufficient_data", "n": len(sub)}

    def residualize(target_col, control_cols):
        y_arr = sub[target_col].to_numpy()
        X = np.column_stack([np.ones(len(sub))] + [sub[c].to_numpy() for c in control_cols])
        coef, *_ = np.linalg.lstsq(X, y_arr, rcond=None)
        return y_arr - X @ coef

    if controls:
        rx = residualize(x, controls)
        ry = residualize(y, controls)
    else:
        rx = sub[x].to_numpy()
        ry = sub[y].to_numpy()
    r = float(np.corrcoef(rx, ry)[0, 1])
    return {"partial_r": round(r, 4), "n": len(sub), "controls": controls}


def main() -> None:
    df = pd.read_parquet(DATA_CACHE / "derived" / "pitch_dataset_v2.parquet")
    df = df.dropna(subset=["pitcher_id"])

    table = build_pitcher_table(df)
    out_dir = REPORTS_DIR / "phase1c"
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(DATA_CACHE / "derived" / "pitcher_family_table.csv")  # gitignored, internal
    print(f"Pitcher family table: {len(table)} pitchers, columns: {list(table.columns)}")

    # --- Incremental information: physical -> whiff (tracked population) ---
    chain_whiff = incremental_chain(
        table,
        target="whiff_rate",
        blocks=[
            ("velocity", ["velocity"]),
            ("movement", ["movement_pfx_x", "movement_pfx_z"]),
            ("spin", ["spin_rate"]),
            ("pitch_mix_diversity", ["share_fastball", "share_breaking", "pitch_entropy"]),
            ("location", ["zone_rate"]),
            ("swing_decision", ["chase_rate"]),
        ],
    )

    # --- Incremental information: physical + whiff -> damage suppression (tracked population) ---
    chain_damage = incremental_chain(
        table,
        target="avg_launch_speed",
        blocks=[
            ("velocity", ["velocity"]),
            ("movement", ["movement_pfx_x", "movement_pfx_z"]),
            ("spin", ["spin_rate"]),
            ("location", ["zone_rate"]),
            ("whiff_ability", ["whiff_rate"]),
        ],
    )
    chain_hard_hit = incremental_chain(
        table,
        target="hard_hit_rate",
        blocks=[
            ("velocity", ["velocity"]),
            ("movement", ["movement_pfx_x", "movement_pfx_z"]),
            ("spin", ["spin_rate"]),
            ("location", ["zone_rate"]),
            ("whiff_ability", ["whiff_rate"]),
        ],
    )
    chain_gb = incremental_chain(
        table,
        target="ground_ball_rate",
        blocks=[
            ("velocity", ["velocity"]),
            ("movement", ["movement_pfx_x", "movement_pfx_z"]),
            ("spin", ["spin_rate"]),
        ],
    )

    # --- ALL_LEVELS chain (no tracking required): swing decision -> whiff ---
    chain_all_levels = incremental_chain(
        table,
        target="whiff_rate_all_levels",
        blocks=[("swing_decision_all_levels", ["swing_rate_all_levels"])],
    )

    incremental_results = {
        "population": {
            "tracked_chain_n_pitchers": int(table["velocity"].notna().sum()),
            "all_levels_chain_n_pitchers": int(table["whiff_rate_all_levels"].notna().sum()),
            "min_tracked_pitches": MIN_TRACKED_PITCHES,
            "min_total_pitches": MIN_TOTAL_PITCHES,
            "min_batted_balls": MIN_BATTED_BALLS,
        },
        "chain_physical_to_whiff": chain_whiff,
        "chain_physical_whiff_to_avg_launch_speed": chain_damage,
        "chain_physical_whiff_to_hard_hit_rate": chain_hard_hit,
        "chain_physical_to_ground_ball_rate": chain_gb,
        "chain_all_levels_swing_to_whiff": chain_all_levels,
    }
    with open(out_dir / "INCREMENTAL_STATS.json", "w", encoding="utf-8") as f:
        json.dump(incremental_results, f, indent=2, default=str)
    print(f"Wrote {out_dir / 'INCREMENTAL_STATS.json'}")

    # --- Redundancy: pairwise correlation matrix among family-representative metrics ---
    family_repr_cols = [
        "velocity", "movement_pfx_z", "spin_rate", "pitch_entropy",
        "zone_rate", "chase_rate", "whiff_rate", "avg_launch_speed",
        "hard_hit_rate", "ground_ball_rate",
    ]
    corr_matrix = table[family_repr_cols].corr(min_periods=10)

    # Partial correlations for the pairs the charter's own example chain highlights
    partials = {
        "velocity_vs_whiff_controlling_for_movement_spin": partial_correlation(
            table, "velocity", "whiff_rate", ["movement_pfx_z", "spin_rate"]
        ),
        "whiff_vs_avg_launch_speed_controlling_for_physical": partial_correlation(
            table, "whiff_rate", "avg_launch_speed", ["velocity", "movement_pfx_z", "spin_rate"]
        ),
        "zone_rate_vs_chase_rate_controlling_for_velocity": partial_correlation(
            table, "zone_rate", "chase_rate", ["velocity"]
        ),
        "spin_rate_vs_movement_controlling_for_velocity": partial_correlation(
            table, "spin_rate", "movement_pfx_z", ["velocity"]
        ),
    }

    redundancy_results = {
        "pairwise_correlation_matrix": corr_matrix.round(4).to_dict(),
        "partial_correlations": partials,
        "n_pitchers_used": {c: int(table[c].notna().sum()) for c in family_repr_cols},
    }
    with open(out_dir / "REDUNDANCY_STATS.json", "w", encoding="utf-8") as f:
        json.dump(redundancy_results, f, indent=2, default=str)
    print(f"Wrote {out_dir / 'REDUNDANCY_STATS.json'}")


if __name__ == "__main__":
    main()
