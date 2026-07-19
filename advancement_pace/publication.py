# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Phase 12 — versioned publication artifact for future player-card use.

Writes data/advancement_pace_public.parquet + schema.json + provenance_manifest.json
+ example_players.json. NOT wired into the live site: this is a staged,
publication-ready artifact for a later frontend charter.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import contracts
from score import build_scores, METHODOLOGY_VERSION, MEANINGFUL_PA_THRESHOLD

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

EXAMPLE_NAMES = ["Jackson Chourio", "Nick Kurtz", "Samuel Basallo", "Byron Chourio",
                 "Ethan Holliday", "Jesús Made", "Dalton Rushing", "Jordan Lawlar"]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def build_public(scores: pd.DataFrame) -> pd.DataFrame:
    pub = scores[scores.scoreable & scores.active].copy()
    pub["as_of_date"] = pub.season.astype(int).astype(str) + "-09-30"
    pub["active_pro_seasons"] = pub.active_seasons.astype(int)
    pub["meaningful_assignments"] = pub.meaningful_assignments.astype(int)
    pub["advancement_pace_plus_internal"] = pub.advancement_pace_plus  # uncapped + unshrunk kept below
    pub["advancement_pace_plus_raw_internal"] = pub.advancement_pace_plus_raw
    pub["advancement_pace_plus"] = pub.advancement_pace_plus_display
    lineage = json.loads((DATA / "lineage.json").read_text())
    pub["data_version"] = "-".join(sorted(v["sha256_16"][:8] for v in lineage["sources"].values()))[:32]
    pub["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pub["stat_type"] = contracts.STAT_TYPE
    pub["model_eligible"] = contracts.MODEL_ELIGIBLE
    cols = contracts.PUBLIC_SCHEMA + ["advancement_pace_plus_internal",
                                      "advancement_pace_plus_raw_internal", "name"]
    return pub[cols].sort_values(["player_id", "season"]).reset_index(drop=True)


def main():
    scores = build_scores(MEANINGFUL_PA_THRESHOLD)
    scores.to_parquet(DATA / "scores_full.parquet", index=False)
    pub = build_public(scores)

    errs = contracts.validate_public(pub)
    if errs:
        raise SystemExit(f"PUBLICATION CONTRACT FAILED: {errs}")

    out = DATA / "advancement_pace_public.parquet"
    pub.to_parquet(out, index=False)

    schema = {
        "artifact": "advancement_pace_public.parquet",
        "methodology_version": METHODOLOGY_VERSION,
        "meaningful_pa_threshold": MEANINGFUL_PA_THRESHOLD,
        "stat_type": contracts.STAT_TYPE,
        "model_eligible": contracts.MODEL_ELIGIBLE,
        "grain": "player_id x season (as-of end of season)",
        "columns": {c: str(pub[c].dtype) for c in pub.columns},
        "display_cap": [70, 130],
        "scale": "100 = typical peer-adjusted advancement pace; 110 ~ one standard unit faster",
    }
    (DATA / "schema.json").write_text(json.dumps(schema, indent=2))

    lineage = json.loads((DATA / "lineage.json").read_text())
    manifest = {
        "artifact_sha256_16": _sha(out),
        "rows": len(pub), "players": int(pub.player_id.nunique()),
        "seasons": [int(pub.season.min()), int(pub.season.max())],
        "methodology_version": METHODOLOGY_VERSION,
        "level_map_version": lineage["level_map_version"],
        "generated_at": pub.generated_at.iloc[0],
        "inputs": lineage["sources"],
        "consumers_permitted": ["descriptive publication layer", "internal QC reports",
                                "player-card UI (future charter)",
                                "data exports labeled descriptive"],
        "consumers_forbidden": ["Career Outcome+", "p_reach", "xWAR", "xFV", "eFV",
                                "eWAR", "eoWAR", "readiness", "opportunity",
                                "career-state routing", "any predictive/valuation head"],
    }
    (DATA / "provenance_manifest.json").write_text(json.dumps(manifest, indent=2))

    ex = pub[pub.name.isin(EXAMPLE_NAMES)].sort_values(["name", "season"])
    keep = ["name", "season", "advancement_pace_plus", "advancement_percentile",
            "sample_quality", "starting_level", "current_level", "active_pro_seasons",
            "meaningful_assignments", "entry_pathway", "position_group"]
    (DATA / "example_players.json").write_text(
        json.dumps(json.loads(ex[keep].to_json(orient="records")), indent=1))

    print(f"published {len(pub):,} rows / {pub.player_id.nunique():,} players -> {out.name}")
    print("contract: PASS")


if __name__ == "__main__":
    main()
