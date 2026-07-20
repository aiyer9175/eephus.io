"""Phase 1B, step 5: exploratory promotion/level-transfer check.

Explicitly exploratory, not a validated reliability figure -- the sample of
pitchers appearing at 2+ levels within this pilot is small, and "which level
came first" is used as a purely chronological ordering (earlier level ->
later level), not a confirmed promotion (a pitcher could have been demoted,
optioned, or on a rehab assignment; the public schedule/feed data used here
doesn't distinguish those). Only ALL_LEVELS metrics are used, since those
are the only ones computable at every level for a fair before/after
comparison (TRACKED_ONLY metrics would confound "level changed" with
"tracking availability changed").

Output: reports/phase1b/PROMOTION_SEAM_STATS.json

Usage: python promotion_seam_check.py
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import METRICS  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA_CACHE, REPORTS_DIR  # noqa: E402

MIN_PITCHES_PER_LEVEL = 20
MIN_PAIRS_FOR_CORRELATION = 8


def main() -> None:
    df = pd.read_parquet(DATA_CACHE / "derived" / "pitch_dataset.parquet")
    df = df.dropna(subset=["pitcher_id", "game_date"])

    results = {}
    all_levels_metrics = [m for m in METRICS if m.scope == "ALL_LEVELS"]

    for metric in all_levels_metrics:
        mask = metric.denominator_filter(df)
        sub = df[mask].copy()
        if metric.kind == "rate":
            sub["_value"] = metric.numerator(sub).astype(float)
        else:
            sub["_value"] = sub[metric.value_col].astype(float)

        per_pitcher_level = sub.groupby(["pitcher_id", "level"]).agg(
            value=("_value", "mean"),
            n=("_value", "size"),
            first_date=("game_date", "min"),
        )
        per_pitcher_level = per_pitcher_level[per_pitcher_level["n"] >= MIN_PITCHES_PER_LEVEL]

        pairs = []
        for pitcher_id, group in per_pitcher_level.groupby(level=0):
            levels_present = group.index.get_level_values("level").tolist()
            if len(levels_present) < 2:
                continue
            rows = group.reset_index()
            for (i, row_a), (j, row_b) in combinations(rows.iterrows(), 2):
                if row_a["first_date"] <= row_b["first_date"]:
                    earlier, later = row_a, row_b
                else:
                    earlier, later = row_b, row_a
                pairs.append(
                    {
                        "pitcher_id": int(pitcher_id),
                        "from_level": earlier["level"],
                        "to_level": later["level"],
                        "value_before": round(float(earlier["value"]), 4),
                        "value_after": round(float(later["value"]), 4),
                        "n_before": int(earlier["n"]),
                        "n_after": int(later["n"]),
                    }
                )

        pairs_df = pd.DataFrame(pairs)
        entry = {
            "n_pitcher_level_transitions": len(pairs_df),
            "status": "exploratory_only_low_power" if len(pairs_df) < MIN_PAIRS_FOR_CORRELATION else "exploratory",
        }
        if len(pairs_df) >= MIN_PAIRS_FOR_CORRELATION:
            r = pairs_df["value_before"].corr(pairs_df["value_after"])
            entry["before_after_correlation"] = None if pd.isna(r) else round(float(r), 4)
            entry["mean_signed_diff_after_minus_before"] = round(
                float((pairs_df["value_after"] - pairs_df["value_before"]).mean()), 4
            )
        entry["transitions_by_level_pair"] = (
            {f"{a}->{b}": int(n) for (a, b), n in pairs_df.groupby(["from_level", "to_level"]).size().items()}
            if len(pairs_df)
            else {}
        )
        entry["sample_transitions"] = pairs[:10]
        results[metric.name] = entry
        print(f"{metric.name}: {len(pairs_df)} pitcher-level transitions found")

    out_path = REPORTS_DIR / "phase1b" / "PROMOTION_SEAM_STATS.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
