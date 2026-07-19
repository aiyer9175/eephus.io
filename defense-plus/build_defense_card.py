# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
build_defense_card.py — per-player defensive value card for downstream models
(Variance+ total value). Ships the Defense+ COMPOSITE (innings-shrunk, beats
OAA-alone OOS) as the headline def value, plus the SUB-COMPONENTS so the card
can still show the breakdown.

  def_runs : Defense+ composite fielding runs (dplus_runs; shrunk, no posadj)
  def_sd   : per-player uncertainty (sd_runs; calibrated 80%)
  sub      : OAA / DRS / FRP / framing from the latest full season
Output -> ~/swing_plus/data/processed/defense_card.parquet
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent
DST = Path.home() / "swing_plus" / "data" / "processed" / "defense_card.parquet"


def main():
    comp = pd.read_csv(ROOT / "reports" / "06_defense_plus_2025.csv")          # composite + sd
    comp = comp.rename(columns={"id": "batter", "dplus_runs": "def_runs", "sd_runs": "def_sd"})

    # sub-components from the latest full season
    fg = pd.read_csv(ROOT / "data" / "raw" / "fg_field_full_2025.csv")
    fg = fg.rename(columns={"xMLBAMID": "batter"})
    subcols = {"OAA": "d_oaa", "DRS": "d_drs", "FRP": "d_frp", "CFraming": "d_framing"}
    keep = ["batter"] + [c for c in subcols if c in fg.columns]
    sub = fg[keep].rename(columns=subcols)
    # one row per player (sum across stints/positions for the sub-components)
    sub = sub.groupby("batter", as_index=False).sum(numeric_only=True)

    card = comp[["batter", "Pos", "Inn", "def_runs", "dplus_total", "def_sd"]].merge(
        sub, on="batter", how="left")
    card["def_source"] = "dplus_composite"
    card["batter"] = card["batter"].astype("int64")
    card[["def_runs", "dplus_total", "def_sd"]] = card[["def_runs", "dplus_total", "def_sd"]].round(2)
    card.to_parquet(DST, index=False)
    print(f"saved {DST} ({len(card)} players)")
    print(f"  def_runs range [{card.def_runs.min():.1f},{card.def_runs.max():.1f}], "
          f"mean def_sd {card.def_sd.mean():.1f}; subcomponents: {[c for c in card.columns if c.startswith('d_')]}")


if __name__ == "__main__":
    main()
