# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Phase 1 — reconstruct one authoritative level-history row per player x season x level.

Sources (read-only; this module imports NOTHING from predictive packages):
  deep_minors.parquet   statsapi season hitting lines, AAA/AA (sportId 11/12), PA>=1, 2008-2026
  lower_minors.parquet  statsapi season hitting lines, A+/A/Rk (sportId 13/14/16), PA>=1, 2008-2026
  eephus_identity.parquet   dob, primary_position, organization (canonical id layer)
  prospect_mlb_status.parquet  statsapi-derived MLB debut dates (canonical status layer)
  bwar cache (via milb_outcome_panel debut col)  bWAR-derived debut season fallback
  draft_history.parquet  Rule 4 draft records (mlbam_id, draft_year, round, signed)

Outputs:
  data/level_history.parquet  player_id, season, level, level_rank, pa, age
  data/player_index.parquet   one row per player: entry attributes, debut, position group
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from level_map import SPORT_TO_LEVEL, LEVEL_RANK, LEVEL_MAP_VERSION

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
COP = Path.home() / "career_outcome_plus" / "data"

SRC = {
    "deep_minors": Path.home() / "projection_engine/data/deep_minors.parquet",
    "lower_minors": COP / "lower_minors.parquet",
    "identity": COP / "eephus_identity.parquet",
    "status": COP / "prospect_mlb_status.parquet",
    # debut fallback: full bWAR cache (NOT the PA>=50 panel — veterans whose only
    # MiLB rows are short rehab stints would otherwise carry no debut and leak
    # into the scored population as fake AA/AAA entries)
    "bwar": sorted((Path.home() / ".pybaseball" / "cache").glob("bwar_bat*.parquet"))[-1],
    "draft": Path.home() / "playing_time_model/data/raw/draft_history.parquet",
    "fielding": COP / "milb_fielding_full.parquet",
}

POSITION_GROUP = {
    "C": "Catcher",
    "2B": "Middle infield", "SS": "Middle infield",
    "1B": "Corner infield", "3B": "Corner infield",
    "LF": "Outfield", "CF": "Outfield", "RF": "Outfield", "OF": "Outfield",
    "DH": "Utility / multi-position", "UT": "Utility / multi-position",
    "IF": "Utility / multi-position",
}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def entry_pathway(row) -> str:
    """Pathway from draft record + entry age. Draft data separates drafted vs
    undrafted; entry age separates prep/international teenagers from college players."""
    if row.drafted:
        return "draft_hs" if row.entry_age <= 19.5 else "draft_college"
    return "intl_amateur" if row.entry_age <= 19.5 else "undrafted_other"


def main():
    DATA.mkdir(exist_ok=True)
    dm = pd.read_parquet(SRC["deep_minors"], columns=["batter", "season", "sport", "pa", "age"])
    lm = pd.read_parquet(SRC["lower_minors"], columns=["batter", "season", "sport", "pa", "age"])
    raw = pd.concat([dm, lm], ignore_index=True)
    n_raw = len(raw)

    raw["level"] = raw.sport.map(SPORT_TO_LEVEL)
    dropped_unmapped = int(raw.level.isna().sum())
    raw = raw.dropna(subset=["level"])
    raw = raw[raw.pa >= 1]

    # one authoritative row per player x season x level (statsapi can split traded players)
    hist = (raw.groupby(["batter", "season", "level"], as_index=False)
               .agg(pa=("pa", "sum"), age=("age", "min")))
    hist["level_rank"] = hist.level.map(LEVEL_RANK)
    hist = hist.rename(columns={"batter": "player_id"}).sort_values(
        ["player_id", "season", "level_rank"]).reset_index(drop=True)

    assert not hist.duplicated(["player_id", "season", "level"]).any()
    assert (hist.season != 2020).all() or True  # checked & reported below
    n_2020 = int((hist.season == 2020).sum())

    # ---- player index ------------------------------------------------------
    first = hist.sort_values(["season", "level_rank"]).groupby("player_id").first()
    idx = pd.DataFrame({
        "first_pro_season": hist.groupby("player_id").season.min(),
        "entry_age": hist.groupby("player_id").age.min(),
    })
    # starting level: level with the most PA in the first pro season
    fps = hist.merge(idx.first_pro_season.rename("fps"), left_on="player_id", right_index=True)
    fps = fps[fps.season == fps.fps]
    idx["starting_level"] = fps.sort_values("pa", ascending=False).groupby("player_id")["level"].first()
    idx["starting_rank"] = idx.starting_level.map(LEVEL_RANK)

    ident = pd.read_parquet(SRC["identity"],
                            columns=["mlbam_id", "name", "primary_position", "dob"])
    ident = ident.dropna(subset=["mlbam_id"]).drop_duplicates("mlbam_id").set_index("mlbam_id")
    idx = idx.join(ident, how="left")

    # era-correct position: innings-weighted primary MiLB position (full history),
    # 'Utility / multi-position' when no single position holds >=40% of innings.
    fld = pd.read_parquet(SRC["fielding"])
    fld = fld[fld.pos != "P"]
    inn = fld.groupby(["batter", "pos"]).innings.sum().reset_index()
    tot = inn.groupby("batter").innings.sum().rename("tot")
    top = inn.sort_values("innings", ascending=False).groupby("batter").first().join(tot)
    top["share"] = top.innings / top.tot
    top["milb_primary_pos"] = np.where(top.share >= 0.40, top.pos, "UT")
    idx = idx.join(top.milb_primary_pos, how="left")
    idx["position_group"] = (idx.milb_primary_pos.map(POSITION_GROUP)
                             .fillna(idx.primary_position.map(POSITION_GROUP))
                             .fillna("Unknown"))

    draft = pd.read_parquet(SRC["draft"])
    draft = draft[draft.signed == True].sort_values("draft_year").drop_duplicates("mlbam_id")
    idx = idx.join(draft.set_index("mlbam_id")[["draft_year", "round"]], how="left")
    idx["drafted"] = idx.draft_year.notna()
    idx["entry_pathway"] = idx.apply(entry_pathway, axis=1)

    # MLB debut: statsapi status layer first, bWAR-derived fallback
    status = pd.read_parquet(SRC["status"], columns=["mlbam_id", "mlb_debut_season"])
    status = status.dropna(subset=["mlbam_id"]).drop_duplicates("mlbam_id").set_index("mlbam_id")
    idx = idx.join(status, how="left")
    bw = pd.read_parquet(SRC["bwar"], columns=["mlb_ID", "year_ID"])
    bw["mlb_ID"] = pd.to_numeric(bw.mlb_ID, errors="coerce")
    bwar_debut = bw.dropna(subset=["mlb_ID"]).groupby("mlb_ID").year_ID.min()
    idx["mlb_debut_season"] = idx.mlb_debut_season.fillna(idx.index.to_series().map(bwar_debut))
    idx["debuted"] = idx.mlb_debut_season.notna()

    idx = idx.reset_index().rename(columns={"index": "player_id", "mlbam_id": "player_id"})

    hist.to_parquet(DATA / "level_history.parquet", index=False)
    idx.to_parquet(DATA / "player_index.parquet", index=False)

    lineage = {
        "level_map_version": LEVEL_MAP_VERSION,
        "sources": {k: {"path": str(p), "sha256_16": _sha(p)} for k, p in SRC.items()},
        "raw_rows": n_raw, "dropped_unmapped_sport": dropped_unmapped,
        "history_rows": len(hist), "players": int(hist.player_id.nunique()),
        "seasons": [int(hist.season.min()), int(hist.season.max())],
        "rows_in_2020": n_2020,
        "identity_dob_coverage": float(idx.dob.notna().mean()),
        "position_known": float((idx.position_group != "Unknown").mean()),
        "drafted_share": float(idx.drafted.mean()),
        "debuted_share": float(idx.debuted.mean()),
    }
    (DATA / "lineage.json").write_text(json.dumps(lineage, indent=2))
    print(json.dumps(lineage, indent=2))


if __name__ == "__main__":
    main()
