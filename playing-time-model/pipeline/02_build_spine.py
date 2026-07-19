# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 2 — Usage spine.

Builds the canonical player-season usage table from the raw statsapi pulls:
PA, G, total starts (defensive + DH), games/starts by position, primary
position, position count, premium-position flags, DH share. Cross-validates
PA against the independently pulled deep_mlb parquet (join validation between
two statsapi pulls made years apart).

Output: data/processed/usage_spine.parquet, reports/02_spine.md
"""
import pandas as pd

RAW = "/Users/willcahoon/playing_time_model/data/raw"
OUT = "/Users/willcahoon/playing_time_model"
DEEP_MLB = "/Users/willcahoon/projection_engine/data/deep_mlb.parquet"

POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "P"]

lines = ["# Module 2 — Usage Spine Report", ""]


def log(s=""):
    lines.append(s)
    print(s)


def innings_to_float(s):
    if pd.isna(s):
        return 0.0
    whole, _, frac = str(s).partition(".")
    return float(whole) + (int(frac) if frac else 0) / 3.0


hit = pd.read_parquet(f"{RAW}/usage_hitting.parquet")
fld = pd.read_parquet(f"{RAW}/usage_fielding.parquet")
fld["inn"] = fld.innings.map(innings_to_float)

# wide fielding: games / starts per position
g = fld.pivot_table(index=["mlbam_id", "season"], columns="position",
                    values="games", aggfunc="sum").fillna(0)
gs = fld.pivot_table(index=["mlbam_id", "season"], columns="position",
                     values="games_started", aggfunc="sum").fillna(0)
g.columns = [f"g_{c.lower()}" for c in g.columns]
gs.columns = [f"gs_{c.lower()}" for c in gs.columns]
wide = g.join(gs).reset_index()

spine = hit.merge(wide, on=["mlbam_id", "season"], how="left")
for p in POSITIONS:
    for pre in ("g_", "gs_"):
        col = f"{pre}{p.lower()}"
        if col not in spine:
            spine[col] = 0.0
        spine[col] = spine[col].fillna(0)

gs_cols = [f"gs_{p.lower()}" for p in POSITIONS]
g_cols = [f"g_{p.lower()}" for p in POSITIONS]
spine["gs_total"] = spine[gs_cols].sum(axis=1)
spine["g_field_total"] = spine[[c for c in g_cols if c != "g_dh"]].sum(axis=1)

# primary position = most starts (games as tiebreak)
def primary_pos(row):
    best, best_key = None, (-1, -1)
    for p in POSITIONS:
        key = (row[f"gs_{p.lower()}"], row[f"g_{p.lower()}"])
        if key > best_key:
            best, best_key = p, key
    return best if best_key > (0, 0) else "PH"


spine["primary_pos"] = spine.apply(primary_pos, axis=1)

# positions played: >=5 games at a real defensive position (not DH/P)
def_pos = [p for p in POSITIONS if p not in ("DH", "P")]
spine["n_positions"] = sum(
    (spine[f"g_{p.lower()}"] >= 5).astype(int) for p in def_pos)
spine["premium_pos"] = ((spine.g_c >= 5) | (spine.g_ss >= 5) |
                        (spine.g_cf >= 5)).astype(int)
spine["dh_share"] = (spine.gs_dh / spine.gs_total.clip(lower=1)).fillna(0)

# hitter filter: drop pitchers-who-batted (only P appearances + trivial PA).
# Ohtani-types survive via DH games.
is_pitcher_only = ((spine.primary_pos == "P") &
                   (spine.g_dh + spine.g_field_total - spine.g_p <= 0))
n_drop = int(is_pitcher_only.sum())
spine = spine[~is_pitcher_only].copy()
log(f"- dropped {n_drop} pitcher-only batting rows (pre-universal-DH NL pitchers)")
log(f"- spine: {spine.shape[0]} player-seasons, {spine.mlbam_id.nunique()} players, "
    f"seasons {spine.season.min()}-{spine.season.max()}")

# cross-validate PA vs deep_mlb (independent pull)
deep = pd.read_parquet(DEEP_MLB)[["batter", "season", "pa", "age", "woba",
                                  "k_pct", "bb_pct", "iso", "obp"]]
deep = deep.rename(columns={"batter": "mlbam_id", "pa": "pa_deep"})
m = spine.merge(deep, on=["mlbam_id", "season"], how="left")
both = m.dropna(subset=["pa_deep"])
exact = (both.pa == both.pa_deep).mean()
mad = (both.pa - both.pa_deep).abs().mean()
log(f"- PA cross-check vs deep_mlb: {len(both)} matched rows, "
    f"{exact:.1%} exact match, mean abs diff {mad:.2f} PA")
if exact < 0.98:
    log("- **FLAG** PA agreement <98% — investigate before modeling")
unmatched = m.pa_deep.isna() & (m.pa >= 50)
log(f"- spine rows >=50 PA missing from deep_mlb: {int(unmatched.sum())} "
    f"(deep_mlb had its own filters; spine is the authority for usage)")

m = m.drop(columns=["pa_deep"])
m.to_parquet(f"{OUT}/data/processed/usage_spine.parquet", index=False)
log(f"- saved usage_spine.parquet: {m.shape}")

# quick sanity: league PA by season
sanity = m.groupby("season").pa.sum()
log("\n## League PA by season (sanity)")
log(sanity.to_string())

with open(f"{OUT}/reports/02_spine.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
