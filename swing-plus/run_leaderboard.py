# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
run_leaderboard.py - Build Swing+ leaderboards for 2023_H2 through 2025_H2.

Steps:
  1. Pull pitch-level Statcast for each half (weekly chunks, parquet-cached).
  2. Score each half with the deployable model.
  3. Write three leaderboards: player-half, player-season, all-time.

Re-running is cheap: cached halves load from disk; only changed halves re-pull.
Add a new half by appending to SEASON_HALVES.
"""

from __future__ import annotations

import argparse
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from swing_plus import SwingPlusModel
from predicted_stats import OUTPUT_COLS, PredictedStatsModel
from pa_value import PAValueModel
from pa_features import (
    APPROACH_FEATS, compute_approach_features, compute_observed_pa_stats,
    compute_observed_bip_stats,
)

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
RAW.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

ARTIFACT = PROJECT / "swing_plus_model_v1.joblib"
STATS_ARTIFACT = PROJECT / "predicted_stats_models.joblib"
PA_ARTIFACT = PROJECT / "pa_value_models.joblib"
EV90_ARTIFACT = PROJECT / "ev90_model.joblib"

# Board inclusion floor in competitive swings (overrides the model's 180).
# Players below this are too noisy to show; above it, reliability weighting +
# the UI sample selector manage sample-size differences.
MIN_SWINGS = 50

# Swing+ reliability shrinkage. The artifact ships k=360, but that was a chosen
# (not derived) value borrowed from outcome-stat reliability. Swing+ is built on
# swing-tracking means that stabilize fast (half-to-half r=0.86), and a grid
# search on next-half prediction puts the MSE-optimal k at ~50. k=360 over-shrank
# every player toward 100 (worse than no shrinkage). 50 is the calibrated value.
RELIABILITY_K = 50

# Predicted batted-ball stats and their observed counterparts. Keyed by the
# shared suffix so pred_<key> / obs_<key> / bbdiff_<key> line up.
PRED_COLS = list(OUTPUT_COLS.values()) + ["pred_avg_ev90"]   # +90th-pctile EV (top-end power)
BB_KEYS = [k.replace("pred_", "") for k in PRED_COLS]   # avg_ev, hard_hit_pct, ..., avg_ev90
OBS_BB_COLS = [f"obs_{k}" for k in BB_KEYS]
BBDIFF_COLS = [f"bbdiff_{k}" for k in BB_KEYS]
# Full-PA value columns. Observed/predicted xwOBA & wOBA are averaged across
# halves (PA-weighted), then blended fresh at each aggregation level.
PA_OBS_COLS = ["obs_xwoba", "obs_woba"]
PA_PRED_COLS = ["pred_xwoba", "pred_woba"]

# Bat tracking is only available from 2023-07-11 onward. Split halves at the
# All-Star break, matching the convention the model was trained on.
SEASON_HALVES: dict[str, tuple[str, str]] = {
    "2023_H2": ("2023-07-14", "2023-10-01"),
    "2024_H1": ("2024-03-28", "2024-07-15"),
    "2024_H2": ("2024-07-19", "2024-09-29"),
    "2025_H1": ("2025-03-27", "2025-07-14"),
    "2025_H2": ("2025-07-18", "2025-09-28"),
    # 2026 H1 in progress — partial half, pulled through the current date.
    "2026_H1": ("2026-03-25", "2026-05-28"),
}

SEASONS: dict[str, list[str]] = {
    "2023": ["2023_H2"],
    "2024": ["2024_H1", "2024_H2"],
    "2025": ["2025_H1", "2025_H2"],
    "2026": ["2026_H1"],
}


def pull_half(label: str, start: str, end: str) -> pd.DataFrame:
    """Weekly-chunked Statcast pull with parquet cache."""
    cache = RAW / f"statcast_{label}.parquet"
    if cache.exists():
        print(f"[{label}] cached: {cache.name}")
        return pd.read_parquet(cache)

    from pybaseball import statcast

    print(f"[{label}] pulling {start} -> {end}")
    cursor = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    chunks: list[pd.DataFrame] = []
    while cursor <= end_d:
        chunk_end = min(cursor + timedelta(days=6), end_d)
        try:
            df = statcast(start_dt=cursor.isoformat(), end_dt=chunk_end.isoformat())
            if df is not None and len(df) > 0:
                chunks.append(df)
            print(f"  {cursor} -> {chunk_end}: {0 if df is None else len(df):,} rows")
        except Exception as e:
            print(f"  {cursor} -> {chunk_end}: FAILED ({e})")
        cursor = chunk_end + timedelta(days=1)

    if not chunks:
        raise RuntimeError(f"No data pulled for {label}")
    full = pd.concat(chunks, ignore_index=True)
    full.to_parquet(cache, index=False)
    print(f"[{label}] saved {len(full):,} rows -> {cache.name}")
    return full


def load_all_halves() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for label, (start, end) in SEASON_HALVES.items():
        df = pull_half(label, start, end)
        df["half"] = label
        df["season"] = label.split("_")[0]
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    print(f"\nTotal pitches across halves: {len(combined):,}")
    print(f"With bat_speed: {combined['bat_speed'].notna().sum():,}")
    return combined


TRAJ_WINDOW = 100   # trailing competitive swings per rolling point
TRAJ_MIN = 30       # min swings before the first point of a season
SWITCH_IDS: set = set()   # MLBAM ids of switch hitters (set in main); used for name suffix

# Component groups for the Swing+ driver decomposition (Shapley). Group name ->
# the model features it bundles. Shapley distributes the nonlinear interactions
# fairly and sums exactly to (Swing+ - league baseline).
SHAP_GROUPS = [
    ("bat_speed", ["bat_speed_mean", "bat_speed_std"]),
    ("attack_angle", ["attack_angle_mean", "attack_angle_std"]),
    ("swing_length", ["swing_length_mean"]),
    ("attack_direction", ["attack_direction_mean"]),
    ("swing_tilt", ["swing_path_tilt_mean"]),
    ("contact_point", ["intercept_ball_minus_batter_pos_x_inches_mean",
                       "intercept_ball_minus_batter_pos_y_inches_mean"]),
]


def shapley_group_contrib(X: np.ndarray, model: SwingPlusModel,
                          baseline: np.ndarray) -> dict[str, np.ndarray]:
    """Group-level Shapley contributions to raw Swing+ for each row of X (the
    9-feature profile matrix). Returns {group_name: contribution array}; the
    contributions sum exactly to (raw Swing+ - baseline Swing+)."""
    from math import factorial
    ng = len(SHAP_GROUPS)
    gcols = [[model.features.index(f) for f in feats] for _, feats in SHAP_GROUPS]
    P = len(X)
    base_tile = np.tile(baseline, (P, 1))
    f = np.empty((1 << ng, P))
    for si in range(1 << ng):
        M = base_tile.copy()
        for gi in range(ng):
            if si & (1 << gi):
                for c in gcols[gi]:
                    M[:, c] = X[:, c]
        df = pd.DataFrame(M, columns=model.features)
        df["n_swings"] = TRAJ_WINDOW
        f[si] = model.score_profiles(df, reliability_weight=False)["swing_plus_raw"].values
    out = {}
    for gi, (name, _) in enumerate(SHAP_GROUPS):
        bit = 1 << gi
        acc = np.zeros(P)
        for si in range(1 << ng):
            if si & bit:
                continue
            s = bin(si).count("1")
            wt = factorial(s) * factorial(ng - s - 1) / factorial(ng)
            acc += wt * (f[si | bit] - f[si])
        out[name] = acc
    return out


def build_trajectories(pitches: pd.DataFrame, model: SwingPlusModel,
                       baseline: np.ndarray | None = None) -> pd.DataFrame:
    """Per-(batter, season) rolling raw Swing+ over time. Rolling resets each
    season (no off-season carryover), so each season is its own trajectory.
    Raw score (no reliability shrinkage) — we're tracking one hitter's path,
    not comparing across players."""
    sw = model.filter_swings(pitches).copy()
    sw["game_date"] = pd.to_datetime(sw["game_date"])
    order = ["batter", "season", "game_date"] + [
        c for c in ["at_bat_number", "pitch_number"] if c in sw.columns]
    sw = sw.sort_values(order).reset_index(drop=True)

    g = sw.groupby(["batter", "season"], sort=False)
    prof = pd.DataFrame(index=sw.index)
    for col in model.tracking_cols:
        prof[f"{col}_mean"] = g[col].transform(
            lambda s: s.rolling(TRAJ_WINDOW, min_periods=TRAJ_MIN).mean())
        prof[f"{col}_std"] = g[col].transform(
            lambda s: s.rolling(TRAJ_WINDOW, min_periods=TRAJ_MIN).std())
    prof["n_swings"] = TRAJ_WINDOW
    prof = prof.dropna(subset=model.features)
    scored = model.score_profiles(prof, reliability_weight=False)
    res = pd.DataFrame({
        "batter": sw.loc[scored.index, "batter"].values,
        "season": sw.loc[scored.index, "season"].values,
        "game_date": sw.loc[scored.index, "game_date"].values,
        "swing_plus": scored["swing_plus_raw"].values,
        "bat_speed": scored["bat_speed_mean"].values,
    })
    for fcol in model.features:           # carry the profile for Shapley
        res[fcol] = scored[fcol].values
    # one point per game date (last window value that day)
    aggd = {"swing_plus": ("swing_plus", "last"), "bat_speed": ("bat_speed", "last")}
    aggd.update({fc: (fc, "last") for fc in model.features})
    res = res.groupby(["batter", "season", "game_date"], as_index=False).agg(**aggd)

    # Swing+ driver decomposition (Shapley) per point
    if baseline is not None:
        shap = shapley_group_contrib(res[model.features].values, model, baseline)
        for gname, arr in shap.items():
            res[f"shap_{gname}"] = arr
    res = res.drop(columns=model.features)
    res["game_date"] = res["game_date"].dt.strftime("%Y-%m-%d")
    return res


def compute_aa_bip(pitches: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Mean attack angle on balls in play (committed/contact swings) — closer
    to Savant's displayed attack angle than our all-competitive-swing mean,
    which includes flat defensive/foul swings. Display only; not a model input."""
    bip = pitches[(pitches["type"] == "X")
                  & pitches["bat_speed"].notna()
                  & pitches["attack_angle"].notna()]
    return (bip.groupby(keys, observed=True)
            .agg(attack_angle_bip=("attack_angle", "mean"))
            .reset_index())


def attach_names(df: pd.DataFrame, id_col: str = "batter") -> pd.DataFrame:
    from pybaseball import playerid_reverse_lookup

    ids = df[id_col].dropna().unique().tolist()
    print(f"\nLooking up names for {len(ids)} batters...")
    table = playerid_reverse_lookup(ids, key_type="mlbam")
    table["name"] = (
        table["name_first"].str.title() + " " + table["name_last"].str.title()
    )
    name_map = dict(zip(table["key_mlbam"], table["name"]))
    df = df.copy()
    df["name"] = df[id_col].map(name_map)
    # Fallback 1: MLB Stats API for ids the Chadwick register misses (recent
    # rookies/prospects). Bulk lookup in one request.
    missing = df["name"].isna()
    if missing.any():
        import json, urllib.request
        ids = df.loc[missing, id_col].dropna().astype(int).unique().tolist()
        extra = {}
        try:
            url = ("https://statsapi.mlb.com/api/v1/people?personIds="
                   + ",".join(map(str, ids)))
            data = json.load(urllib.request.urlopen(url, timeout=25))
            extra = {p["id"]: p["fullName"] for p in data.get("people", [])}
            print(f"  resolved {len(extra)} names via MLB Stats API")
        except Exception as e:
            print(f"  MLB Stats API fallback failed: {e}")
        df["name"] = df["name"].fillna(df[id_col].map(extra))
    # Fallback 2: last resort, label by id (should be empty now).
    still = df["name"].isna()
    if still.any():
        df.loc[still, "name"] = "MLBAM " + df.loc[still, id_col].astype("Int64").astype(str)
        print(f"  {int(still.sum())} ids still unresolved -> MLBAM label")
    # Switch hitters appear twice (one row per stand) — suffix the name so they're
    # distinguishable, e.g. "Francisco Lindor (L)".
    if "stand" in df.columns and SWITCH_IDS:
        sw = df[id_col].isin(SWITCH_IDS)
        df.loc[sw, "name"] = df.loc[sw, "name"] + " (" + df.loc[sw, "stand"] + ")"
    return df


def reliability_shrink(score_raw: pd.Series, n: pd.Series, k: int) -> pd.Series:
    w = n / (n + k)
    return w * score_raw + (1 - w) * 100.0


def add_residuals(df: pd.DataFrame) -> pd.DataFrame:
    """obs - pred deltas. Positive = player outperformed the model's
    expectation; near zero = model fits them well. Covers the full-PA value
    stats (xwOBA/wOBA) and the batted-ball stats (EV/HH%/Barrel%/LA/xwOBAcon)."""
    for key in ("xwoba", "woba"):
        o, p = f"obs_{key}", f"pred_{key}"
        if o in df.columns and p in df.columns:
            df[f"{key}_resid"] = df[o] - df[p]
    for key in BB_KEYS:
        o, p = f"obs_{key}", f"pred_{key}"
        if o in df.columns and p in df.columns:
            df[f"bbdiff_{key}"] = df[o] - df[p]
    return df


# Swing-weighted across halves (swing-level metrics). Includes the full 9-feature
# swing profile so the what-if/adjustment tool has a season baseline to perturb.
_WAVG_COLS = [
    "swing_plus_raw", "p_bip_pred", "rv_bip_pred",
    "bat_speed_mean", "attack_angle_mean", "swing_length_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
] + APPROACH_FEATS   # carry approach features so the what-if can hold them fixed
# BIP-weighted across halves (contact-quality metrics: predicted + observed
# batted-ball stats and the Savant-style attack angle).
_BIPWAVG_COLS = ["attack_angle_bip"] + PRED_COLS + OBS_BB_COLS


def _agg_row(g: pd.DataFrame) -> pd.Series:
    """Aggregate one batter's halves: swing-weighted swing metrics,
    BIP-weighted contact metrics, PA-weighted value metrics."""
    w = g["n_swings"]
    row = {
        "n_swings": int(w.sum()),
        "n_bip": int(g["n_bip"].sum()),
        "n_halves": int(g["half"].nunique()),
    }
    for col in _WAVG_COLS:
        sub = g[[col]].assign(w=w).dropna(subset=[col])
        row[col] = float(np.average(sub[col], weights=sub["w"])) if len(sub) else np.nan

    # BIP-weighted contact metrics.
    bipw = g["n_bip"].fillna(0)
    for col in _BIPWAVG_COLS:
        if col in g.columns:
            sub = g[[col]].assign(w=bipw).dropna(subset=[col])
            sub = sub[sub["w"] > 0]
            row[col] = float(np.average(sub[col], weights=sub["w"])) if len(sub) else np.nan

    # PA-value columns: PA-weighted, and carry total PA for the re-blend.
    if "n_pa" in g.columns:
        pa = g["n_pa"].fillna(0)
        row["n_pa"] = int(pa.sum())
        for col in PA_OBS_COLS + PA_PRED_COLS:
            if col in g.columns:
                sub = g[[col]].assign(w=pa).dropna(subset=[col])
                sub = sub[sub["w"] > 0]
                row[col] = float(np.average(sub[col], weights=sub["w"])) if len(sub) else np.nan
    return pd.Series(row)


def _reblend(grouped: pd.DataFrame, pv: PAValueModel | None) -> pd.DataFrame:
    """Recompute the blended PA-value estimate at an aggregated level using
    summed PA, so blend weight reflects the full-season/career sample."""
    if pv is None or "n_pa" not in grouped.columns:
        return grouped
    grouped = pv.add_blended(
        grouped, n_pa_col="n_pa",
        obs={"xwoba": "obs_xwoba", "woba": "obs_woba"},
    )
    return grouped


def aggregate_to_season(half_board: pd.DataFrame, model: SwingPlusModel,
                        pv: PAValueModel | None = None) -> pd.DataFrame:
    """Swing-weighted average of raw Swing+ across halves of each season."""
    out = []
    for season, halves in SEASONS.items():
        sub = half_board[half_board["half"].isin(halves)]
        if sub.empty:
            continue
        grouped = (
            sub.groupby(["batter", "stand"], as_index=False)
            .apply(_agg_row, include_groups=False)
            .reset_index(drop=False)
        )
        grouped["season"] = season
        grouped["swing_plus"] = reliability_shrink(
            grouped["swing_plus_raw"], grouped["n_swings"], model.reliability_k
        )
        grouped["reliability"] = grouped["n_swings"] / (grouped["n_swings"] + model.reliability_k)
        out.append(_reblend(grouped, pv))
    return pd.concat(out, ignore_index=True)


def aggregate_alltime(half_board: pd.DataFrame, model: SwingPlusModel,
                      pv: PAValueModel | None = None) -> pd.DataFrame:
    grouped = (
        half_board.groupby(["batter", "stand"], as_index=False)
        .apply(_agg_row, include_groups=False)
        .reset_index(drop=False)
    )
    grouped["swing_plus"] = reliability_shrink(
        grouped["swing_plus_raw"], grouped["n_swings"], model.reliability_k
    )
    grouped["reliability"] = grouped["n_swings"] / (grouped["n_swings"] + model.reliability_k)
    return _reblend(grouped, pv)


def write_outputs(half: pd.DataFrame, season: pd.DataFrame, alltime: pd.DataFrame) -> None:
    # swing-based predicted K%/HR%/ISO (obs/pred/diff). Robust: skip on any failure.
    try:
        import extra_stats
        half, season, alltime = extra_stats.add_to_boards(half, season, alltime)
    except Exception as e:
        print(f"  (extra_stats skipped: {e})")
    try:                                # park-neutral HR%/ISO (separate columns)
        import park_factors
        half = park_factors.add_park_neutral(half, "half")
        season = park_factors.add_park_neutral(season, "season")
        alltime = park_factors.add_park_neutral(alltime, "alltime")
    except Exception as e:
        print(f"  (park_factors skipped: {e})")
    try:                                # external MLB swing-Decision+ (orthogonal axis)
        import decision_plus
        half, season, alltime = decision_plus.add_to_boards(half, season, alltime)
    except Exception as e:
        print(f"  (decision_plus skipped: {e})")
    try:                                # MLB-native swing-tailored decision (full coverage)
        import mlb_decision
        half = mlb_decision.add_to_boards(half)
        season = mlb_decision.add_to_boards(season)
        alltime = mlb_decision.add_to_boards(alltime)
    except Exception as e:
        print(f"  (mlb_decision skipped: {e})")
    try:                                # SwingDecision+ combo (Swing+ x Decision+)
        import combo_plus
        half = combo_plus.add_to_boards(half)
        season = combo_plus.add_to_boards(season)
        alltime = combo_plus.add_to_boards(alltime)
    except Exception as e:
        print(f"  (combo_plus skipped: {e})")
    try:                                # Bat-to-Ball+ (3rd axis) + Hitter+ (3-axis combo)
        import bat_to_ball, hitter_plus
        half = hitter_plus.add_to_boards(bat_to_ball.add_to_boards(half))
        season = hitter_plus.add_to_boards(bat_to_ball.add_to_boards(season))
        alltime = hitter_plus.add_to_boards(bat_to_ball.add_to_boards(alltime))
    except Exception as e:
        print(f"  (bat_to_ball/hitter_plus skipped: {e})")
    half_out = half.sort_values("swing_plus", ascending=False).reset_index(drop=True)
    season_out = season.sort_values(["season", "swing_plus"], ascending=[True, False]).reset_index(drop=True)
    alltime_out = alltime.sort_values("swing_plus", ascending=False).reset_index(drop=True)
    alltime_out["rank"] = alltime_out["swing_plus"].rank(method="min", ascending=False).astype(int)

    # Store attack_direction_mean pull-POSITIVE (Savant convention) for display. The
    # raw Statcast sign is pull-negative; swing_plus is already scored above on the
    # raw sign, so we only flip the stored display value here. Consumers that re-score
    # (whatif.py, aging.py) flip it back to raw before feeding the model.
    for df in (half_out, season_out, alltime_out):
        if "attack_direction_mean" in df.columns:
            df["attack_direction_mean"] = -df["attack_direction_mean"]

    for df, name in [
        (half_out, "leaderboard_half"),
        (season_out, "leaderboard_season"),
        (alltime_out, "leaderboard_alltime"),
    ]:
        df.to_csv(PROCESSED / f"{name}.csv", index=False)
        df.to_parquet(PROCESSED / f"{name}.parquet", index=False)
        print(f"  wrote {name}.csv ({len(df)} rows)")


def print_summary(half: pd.DataFrame, season: pd.DataFrame, alltime: pd.DataFrame) -> None:
    cols = ["name", "swing_plus", "n_swings",
            "pred_barrel_pct", "pred_xwobacon",
            "obs_xwoba", "pred_xwoba", "blended_xwoba"]
    cols = [c for c in cols if c in alltime.columns]
    round_map = {"swing_plus": 1, "pred_barrel_pct": 1, "pred_xwobacon": 3,
                 "obs_xwoba": 3, "pred_xwoba": 3, "blended_xwoba": 3}
    round_map = {c: n for c, n in round_map.items() if c in cols}
    fmt = alltime.sort_values("swing_plus", ascending=False).head(25)[cols].copy()
    for c, n in round_map.items():
        fmt[c] = fmt[c].round(n)
    print("\n" + "=" * 88)
    print("TOP 25 — ALL-TIME (2023 H2 – 2025 H2, swing-weighted, reliability-shrunk)")
    print("=" * 88)
    print(fmt.to_string(index=False))

    fmt2 = alltime.sort_values("swing_plus").head(15)[cols].copy()
    for c, n in round_map.items():
        fmt2[c] = fmt2[c].round(n)
    print("\n" + "=" * 88)
    print("BOTTOM 15 — ALL-TIME")
    print("=" * 88)
    print(fmt2.to_string(index=False))

    print("\n" + "=" * 88)
    print("2025 SEASON — TOP 20")
    print("=" * 88)
    s25 = season[season["season"] == "2025"].sort_values("swing_plus", ascending=False).head(20)[cols].copy()
    for c, n in round_map.items():
        s25[c] = s25[c].round(n)
    print(s25.to_string(index=False))


def main() -> None:
    p = argparse.ArgumentParser(description="Build Swing+ leaderboards.")
    p.add_argument("--no-pull", action="store_true",
                   help="Use cached halves only; fail if any half is missing.")
    args = p.parse_args()

    print(f"Loading model from {ARTIFACT.name}")
    model = SwingPlusModel(ARTIFACT)
    # Board inclusion floor. The model's documented min is 180 (calibrated for
    # full halves); for partial seasons that over-excludes. Lower it so more
    # players appear — reliability shrinkage (k=360) regresses small samples
    # toward 100, and the sample selector lets users filter back up.
    model.min_swings = MIN_SWINGS
    model.reliability_k = RELIABILITY_K   # recalibrated (see note above)
    print(f"  version={model.version}  features={len(model.features)}  "
          f"min_swings={model.min_swings} (board floor)  k={model.reliability_k} (recalibrated)")

    if args.no_pull:
        for label in SEASON_HALVES:
            if not (RAW / f"statcast_{label}.parquet").exists():
                raise SystemExit(f"missing cache for {label} (run without --no-pull)")

    pitches = load_all_halves()

    # Switch hitters: identify batters who swing meaningfully from BOTH sides,
    # so we can split their L and R swings into separate rows (a blended L+R
    # profile is meaningless). Single-stand hitters are unaffected.
    sw_all = model.filter_swings(pitches)
    stand_counts = sw_all.groupby(["batter", "stand"]).size().unstack(fill_value=0)
    global SWITCH_IDS
    SWITCH_IDS = set(stand_counts.index[
        (stand_counts.get("L", 0) >= MIN_SWINGS) & (stand_counts.get("R", 0) >= MIN_SWINGS)])
    print(f"\n{len(SWITCH_IDS)} switch hitters will be split by stand (L/R)")

    print("Scoring (filter -> profile -> score, split by stand)...")
    half_board = model.score_pitch_level(pitches, group_by=["stand", "half"])
    print(f"  {len(half_board)} qualifying (player, stand, half) rows "
          f"(>= {model.min_swings} competitive swings)")
    half_board["season"] = half_board["half"].str.split("_").str[0]
    KEY = ["batter", "stand", "half"]

    print(f"Predicting batted-ball stats with {STATS_ARTIFACT.name}...")
    pstats = PredictedStatsModel(STATS_ARTIFACT)
    half_board = pstats.predict_into(half_board)
    print(f"  added {len(pstats.output_cols)} columns: {', '.join(pstats.output_cols)}")

    # 90th-percentile EV (top-end power) — separate companion model.
    if EV90_ARTIFACT.exists():
        import joblib
        ev90 = joblib.load(EV90_ARTIFACT)
        feats = ev90["features"]
        valid = half_board[feats].notna().all(axis=1)
        half_board["pred_avg_ev90"] = np.nan
        half_board.loc[valid, "pred_avg_ev90"] = ev90["model"].predict(
            half_board.loc[valid, feats].values)
        print(f"  added pred_avg_ev90 (90th-pctile EV, OOF r={ev90.get('oof_r')})")

    # Savant-style attack angle (on balls in play / committed swings).
    aa_bip = compute_aa_bip(pitches, keys=KEY)
    half_board = half_board.merge(aa_bip, on=KEY, how="left")
    print(f"  added attack_angle_bip (Savant-style, BIP only)")

    # Observed batted-ball stats (beside the predictions) + pred-vs-obs delta.
    obs_bb = compute_observed_bip_stats(pitches, keys=KEY)
    half_board = half_board.merge(obs_bb, on=KEY, how="left")
    print(f"  added observed batted-ball stats: {', '.join(OBS_BB_COLS)}")

    # --- Full-PA value: approach features -> appr17 -> blended xwOBA/wOBA ---
    pv = None
    if PA_ARTIFACT.exists():
        print(f"Computing approach features + observed PA value...")
        approach = compute_approach_features(pitches, keys=KEY)
        obs_pa = compute_observed_pa_stats(pitches, keys=KEY)
        half_board = (half_board
                      .merge(approach, on=KEY, how="left")
                      .merge(obs_pa, on=KEY, how="left"))
        pv = PAValueModel(PA_ARTIFACT)
        print(f"  PA-value model v{pv.version}, blend k={pv.blend_k}")
        half_board = pv.predict(half_board)
        half_board = pv.add_blended(
            half_board, n_pa_col="n_pa",
            obs={"xwoba": "obs_xwoba", "woba": "obs_woba"})
        print(f"  added blended_xwoba / blended_woba "
              f"(+ obs_*, pred_* for transparency)")
    else:
        print(f"  [skip] {PA_ARTIFACT.name} not found — run train_pa_value.py")

    season_board = aggregate_to_season(half_board, model, pv)
    alltime_board = aggregate_alltime(half_board, model, pv)

    half_board = add_residuals(half_board)
    season_board = add_residuals(season_board)
    alltime_board = add_residuals(alltime_board)

    half_board = attach_names(half_board)
    season_board = attach_names(season_board)
    alltime_board = attach_names(alltime_board)

    print("\nBuilding per-season Swing+ trajectories + driver decomposition...")
    # league-average profile (baseline that scores ~100) for Shapley attribution
    baseline = np.array([
        float(np.average(half_board[fc].dropna(),
                         weights=half_board.loc[half_board[fc].notna(), "n_swings"]))
        for fc in model.features])
    traj = build_trajectories(pitches, model, baseline)
    traj.to_parquet(PROCESSED / "trajectories.parquet", index=False)
    print(f"  wrote trajectories.parquet "
          f"({len(traj):,} points, {traj['batter'].nunique()} players)")

    print("\nWriting outputs to data/processed/")
    write_outputs(half_board, season_board, alltime_board)
    print_summary(half_board, season_board, alltime_board)


if __name__ == "__main__":
    main()
