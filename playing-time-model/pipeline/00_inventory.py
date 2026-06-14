# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 0 — Data inventory + join validation.

Audits every candidate source before anything is modeled (framework rule: no
source is accepted unless it passes join validation).

Sources audited:
  A. Prospect tracker DB  (~/Desktop/eephus.io/prospect-tracker/prospects.db)
       players, snapshots (FV/rank/tools by source+date), statlines (mlbam bridge),
       roster_status (40-man/options/service), player_transactions, career_war
  B. Deep history         (~/projection_engine/data/deep_mlb.parquet, deep_minors.parquet)
  C. Talent layer         (~/swing_plus/data/processed/stat_projections.parquet)

Outputs:
  data/processed/key_bridge.parquet   (player_key slug <-> mlbam_id)
  data/processed/grades_long.parquet  (timestamped FV/rank/tool grades, long form)
  data/processed/roster_status.parquet (parsed 40-man/options/service payloads)
  reports/00_join_validation.md
"""
import json
import sqlite3

import pandas as pd

DB = "/Users/willcahoon/Desktop/eephus.io/prospect-tracker/prospects.db"
DEEP_MLB = "/Users/willcahoon/projection_engine/data/deep_mlb.parquet"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"
PROJ = "/Users/willcahoon/swing_plus/data/processed/stat_projections.parquet"
OUT = "/Users/willcahoon/playing_time_model"

lines = ["# Module 0 — Data Pull / Join Validation Report", ""]
flags = []


def log(s=""):
    lines.append(s)
    print(s)


def flag(s):
    flags.append(s)
    log(f"- **FLAG** {s}")


con = sqlite3.connect(DB)

# ---------------------------------------------------------------- A. tracker
log("## A. Prospect tracker DB")
players = pd.read_sql("SELECT * FROM players", con)
log(f"- players: {len(players)} rows, {players.player_key.nunique()} unique keys")
dupe_keys = players.player_key.value_counts()
if (dupe_keys > 1).any():
    flag(f"{(dupe_keys > 1).sum()} duplicate player_keys in players table")
miss = {c: int(players[c].isna().sum() + (players[c] == '').sum())
        for c in ["position", "org", "birth_date"]}
log(f"- missing fields: {miss}")

# mlbam bridge from statlines payloads
sl = pd.read_sql("SELECT player_key, season, payload_json FROM statlines", con)
sl["mlbam_id"] = sl.payload_json.map(lambda j: json.loads(j).get("mlbam_id"))
bridge = (sl.dropna(subset=["mlbam_id"])
            .astype({"mlbam_id": int})
            .groupby("player_key")["mlbam_id"]
            .agg(["nunique", "first"]).reset_index()
            .rename(columns={"first": "mlbam_id", "nunique": "n_ids"}))
multi = bridge[bridge.n_ids > 1]
if len(multi):
    flag(f"{len(multi)} player_keys map to >1 mlbam_id: {multi.player_key.tolist()[:5]}")
rev = bridge.groupby("mlbam_id").player_key.nunique()
ambiguous_ids = rev[rev > 1].index.tolist()
if ambiguous_ids:
    n_drop = bridge.mlbam_id.isin(ambiguous_ids).sum()
    flag(f"{len(ambiguous_ids)} mlbam_ids map to >1 player_key (tracker name-collision "
         f"bug, e.g. brennen_davis/brendon_davis) — dropping {n_drop} ambiguous "
         f"bridge rows: {ambiguous_ids}")
    bridge = bridge[~bridge.mlbam_id.isin(ambiguous_ids)]
covered = bridge.player_key.nunique()
log(f"- mlbam bridge: {covered}/{len(players)} tracker players have an mlbam_id "
    f"({covered/len(players):.0%} coverage)")
no_id = set(players.player_key) - set(bridge.player_key)
log(f"- {len(no_id)} tracker players lack mlbam_id (mostly never-rostered/intl)")
bridge[["player_key", "mlbam_id"]].to_parquet(
    f"{OUT}/data/processed/key_bridge.parquet", index=False)

# snapshots → grades_long
snap = pd.read_sql("SELECT * FROM snapshots", con)
log(f"\n- snapshots: {len(snap)} rows, sources: "
    f"{snap.groupby('source').size().to_dict()}")
sd = snap.groupby("source").snapshot_date.agg(["min", "max"])
log(f"- snapshot date ranges:\n{sd.to_string()}")
# interval_label distinguishes list scope: Top 100 rank vs org Top 30 rank vs
# debut events vs international — rank is only meaningful within its scope
def scope_of(label):
    if "Top 100" in label:
        return "top100"
    if "Top 30" in label:
        return "org"
    if "debut" in label.lower():
        return "debut"
    if "International" in label:
        return "international"
    return "list"  # ESPN/TJ/JB national lists


snap["scope"] = snap.interval_label.map(scope_of)
log(f"- snapshot scopes: {snap.scope.value_counts().to_dict()}")
dup_snap = snap.duplicated(
    subset=["source", "snapshot_date", "interval_label", "player_key"]).sum()
if dup_snap:
    flag(f"{dup_snap} duplicate (source, date, list, player) snapshot rows")
stale = (pd.Timestamp("2026-06-11") - pd.to_datetime(sd["max"])).dt.days
for src, days in stale.items():
    if days > 180:
        flag(f"snapshot source '{src}' is stale ({days} days since last snapshot)")


def parse_tools(j):
    if not j:
        return {}
    try:
        d = json.loads(j)
        return {k: v for k, v in d.items() if k != "_extras" and v is not None}
    except (json.JSONDecodeError, TypeError):
        return {}


tools = snap.tools_json.map(parse_tools)
tool_cols = sorted({k for d in tools for k in d})
log(f"- tool grade fields present: {tool_cols}")
grades = snap[["source", "snapshot_date", "interval_label", "scope", "player_key",
               "player_name", "position", "org", "rank", "fv"]].copy()
for c in tool_cols:
    grades[c] = tools.map(lambda d, c=c: d.get(c))
grades = grades.merge(bridge[["player_key", "mlbam_id"]], on="player_key", how="left")
grades.to_parquet(f"{OUT}/data/processed/grades_long.parquet", index=False)
log(f"- grades_long saved: {grades.shape}, "
    f"{grades.mlbam_id.notna().mean():.0%} rows mlbam-linked")

# org consistency: players.org vs latest snapshot org
latest = (snap.sort_values("snapshot_date")
              .groupby("player_key").last().reset_index()[["player_key", "org"]]
              .rename(columns={"org": "snap_org"}))
oc = players.merge(latest, on="player_key")
mism = oc[(oc.org != oc.snap_org) & oc.org.ne("") & oc.snap_org.ne("")]
log(f"- org mismatch (players vs latest snapshot): {len(mism)}/{len(oc)} "
    f"(expected: trades since last snapshot)")
if len(mism) > len(oc) * 0.15:
    flag("org mismatch rate >15% — check tracker org update job")

# roster_status → parsed
rs = pd.read_sql("SELECT player_key, payload_json, fetched_at FROM roster_status", con)
parsed = pd.json_normalize(rs.payload_json.map(json.loads))
parsed["player_key"] = rs.player_key.values
parsed["fetched_at"] = rs.fetched_at.values
keep = [c for c in ["player_key", "fetched_at", "mlb_debut_date", "on_40_man",
                    "options_used", "options_remaining", "active_roster_days",
                    "rookie_exhausted", "service_phase", "career_mlb_ab"]
        if c in parsed.columns]
roster = parsed[keep].merge(bridge[["player_key", "mlbam_id"]],
                            on="player_key", how="left")
roster.to_parquet(f"{OUT}/data/processed/roster_status.parquet", index=False)
log(f"\n- roster_status parsed: {roster.shape}; on_40_man coverage "
    f"{roster.on_40_man.notna().mean():.0%}, options_remaining coverage "
    f"{roster.options_remaining.notna().mean():.0%}")
log(f"- NOTE roster_status is a current snapshot (fetched_at "
    f"{pd.to_datetime(roster.fetched_at).max():%Y-%m-%d}); historical option/40-man "
    f"state must come from transactions — timestamp-validity flagged for leakage audit")

# ------------------------------------------------------------ B. deep history
log("\n## B. Deep history (projection_engine)")
mlb = pd.read_parquet(DEEP_MLB)
mins = pd.read_parquet(DEEP_MIN)
for name, df in [("deep_mlb", mlb), ("deep_minors", mins)]:
    dup = df.duplicated(subset=["batter", "season", "sport"]).sum()
    log(f"- {name}: {df.shape}, seasons {df.season.min()}-{df.season.max()}, "
        f"{df.batter.nunique()} players, dup (batter,season,sport) rows: {dup}")
    if dup:
        flag(f"{name} has {dup} duplicate seasonal rows")

# ------------------------------------------------------------ C. talent layer
log("\n## C. Talent layer (swing_plus stat_projections)")
proj = pd.read_parquet(PROJ)
dupp = proj.duplicated(subset=["batter", "season"]).sum()
log(f"- stat_projections: {proj.shape}, seasons "
    f"{proj.season.min()}-{proj.season.max()}, dup rows: {dupp}")
if dupp:
    flag(f"stat_projections has {dupp} duplicate (batter, season) rows")

# ------------------------------------------------------------ D. cross joins
log("\n## D. Cross-source joins")
tracker_ids = set(bridge.mlbam_id)
log(f"- tracker∩deep_mlb: {len(tracker_ids & set(mlb.batter))} players")
log(f"- tracker∩deep_minors: {len(tracker_ids & set(mins.batter))} players")
recent = mlb[mlb.season >= 2024]
pj = set(proj.batter)
log(f"- stat_projections∩deep_mlb(2024+): "
    f"{len(pj & set(recent.batter))}/{len(pj)} projection players matched")

log("\n## Verdict")
if flags:
    log(f"{len(flags)} flags raised (see above). Sources usable with noted caveats.")
else:
    log("All sources PASS join validation.")

with open(f"{OUT}/reports/00_join_validation.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
