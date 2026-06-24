# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Ship current-season projections for every qualified player-season-level.

Fits the champion per (level, target) on all completed transition pairs
(behavior seasons through 2025 -> outcomes through 2026-to-date), then
predicts from current 2026 behavior:
  - projected next K% / BB% (level-adjusted, at the player's current level)
  - projected MLB-equivalent K% / BB% via the level ladder + promotion fit
  - MLB-equivalent Decision+ via within-player same-season component offsets

Outputs one shipping parquet consumed by the leaderboard tool and the main
projection model integration.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, LEVEL_ORDER, OUTPUTS, log_run
from ground_truth_and_baselines import eb_shrink, load_frame

SEED = 42
SHIP_SEASON = 2026
MIN_PITCHES = 150


# champion spec from the strategy race + incremental audit (all ridge):
#   AAA/AA/CPX -> Model C on deep statline history (still beats short-window
#                 component models for K%/BB% by 7-15pp R2)
#   A+/A       -> Model Z (statline + decision components + universal-zone
#                 behavior; beats E on BB% by ~2pp, ties K%)
C_FEATS = ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa"]
Z_FEATS = C_FEATS + ["decision_plus", "contact_shrunk", "take_ball_shrunk",
                     "chase_shrunk", "z_take_shrunk", "zcontact_shrunk"]
LEVEL_FEATURES = {"AAA": C_FEATS, "AA": C_FEATS, "CPX": C_FEATS,
                  "A+": Z_FEATS, "A": Z_FEATS}


def main() -> None:
    pairs = load_frame()
    dec = pd.read_parquet(DATA_PROCESSED / "decision_plus.parquet")
    dkeep = ["batter_id", "batter_name", "season", "level", "decision_plus",
             "decision_z", "tier", "reliability", "posterior_sd", "ci80_lo",
             "ci80_hi", "age_vs_level", "repeat_level", "take_ball_shrunk",
             "ts_called_shrunk", "fp_swing_shrunk", "tb_swing_shrunk",
             "swing_shrunk", "chase_shrunk", "z_take_shrunk", "zone_rec_shrunk",
             "zcontact_shrunk", "zone_coverage",
             "contact_pct", "whiff_pct", "swing_pct", "tracked_share", "pitches",
             "pa", "k_pct", "bb_pct", "age"]
    dec_t = dec[[c for c in dkeep if c in dec.columns]]
    train_frame = pairs.merge(
        dec_t.drop(columns=["pa", "k_pct", "bb_pct", "age"], errors="ignore"),
        left_on=["player_id", "season", "level"],
        right_on=["batter_id", "season", "level"], how="left")
    train_frame["swings_est"] = (train_frame.pitches * train_frame.swing_pct).clip(lower=1)
    ok = train_frame.contact_pct.notna()
    train_frame.loc[ok, "contact_shrunk"] = eb_shrink(
        train_frame[ok].rename(columns={"contact_pct": "r"}), "r", "swings_est",
        ["level", "season"]).values

    models: dict[tuple[str, str], object] = {}
    for level in ["AAA", "AA", "A+", "A", "CPX"]:
        lv = train_frame[(train_frame.level == level)]
        feats = LEVEL_FEATURES[level]
        for tgt in ["next_k_pct", "next_bb_pct"]:
            sub = lv.dropna(subset=feats + [tgt])
            if len(sub) < 150:
                continue
            m = make_pipeline(StandardScaler(), Ridge(alpha=1.0, random_state=SEED))
            m.fit(sub[feats], sub[tgt])
            models[(level, tgt)] = m
            print(f"champion fit {level} {tgt}: n={len(sub)} feats={len(feats)}")

    # ---- current-season frame (2026 behavior) ----
    cur = dec_t[(dec_t.season == SHIP_SEASON) & (dec_t.pitches >= MIN_PITCHES)].copy()
    cur = cur[cur.level.isin(["AAA", "AA", "A+", "A", "CPX"])]
    cur["k_pct_shrunk"] = eb_shrink(cur.assign(pa_f=cur.pa.clip(lower=1)),
                                    "k_pct", "pa_f", ["level"])
    cur["bb_pct_shrunk"] = eb_shrink(cur.assign(pa_f=cur.pa.clip(lower=1)),
                                     "bb_pct", "pa_f", ["level"])
    cur["log_pa"] = np.log(cur.pa.clip(lower=1))
    cur["swings_est"] = (cur.pitches * cur.swing_pct).clip(lower=1)
    okc = cur.contact_pct.notna()
    cur.loc[okc, "contact_shrunk"] = eb_shrink(
        cur[okc].rename(columns={"contact_pct": "r"}), "r", "swings_est",
        ["level"]).values

    for tgt, col in [("next_k_pct", "proj_k_pct"), ("next_bb_pct", "proj_bb_pct")]:
        cur[col] = np.nan
        for level in cur.level.unique():
            m = models.get((level, tgt))
            if m is None:
                continue
            feats = LEVEL_FEATURES[level]
            mask = (cur.level == level) & cur[feats].notna().all(axis=1)
            if mask.any():
                cur.loc[mask, col] = m.predict(cur.loc[mask, feats])

    # ---- MLB-equivalent via level ladder ----
    ladder = pd.read_csv(OUTPUTS / "translation" / "level_ladder_offsets.csv")
    direct = ladder.set_index(["from_level", "to_level"])
    step_up = {"CPX": "A", "A": "A+", "A+": "AA", "AA": "AAA", "AAA": "MLB"}

    def chain_offsets(level: str) -> tuple[float, float]:
        if (level, "MLB") in direct.index and level in ("AAA", "AA"):
            r = direct.loc[(level, "MLB")]
            return float(r.k_pct_offset), float(r.bb_pct_offset)
        k_off = bb_off = 0.0
        lv = level
        while lv != "MLB":
            nxt = step_up[lv]
            if (lv, nxt) in direct.index:
                r = direct.loc[(lv, nxt)]
                k_off += float(r.k_pct_offset)
                bb_off += float(r.bb_pct_offset)
            lv = nxt
        return k_off, bb_off

    for level in cur.level.unique():
        k_off, bb_off = chain_offsets(level)
        mask = cur.level == level
        cur.loc[mask, "mlb_equiv_k_pct"] = cur.loc[mask, "proj_k_pct"] + k_off
        cur.loc[mask, "mlb_equiv_bb_pct"] = cur.loc[mask, "proj_bb_pct"] + bb_off

    # ---- MLB-equivalent Decision+ via component level offsets ----
    # within-player same-season offsets of the core take-quality component
    multi = dec_t.merge(dec_t, on=["batter_id", "season"], suffixes=("_lo", "_hi"))
    multi = multi[(multi.level_lo.map(LEVEL_ORDER) < multi.level_hi.map(LEVEL_ORDER))
                  & (multi.pitches_lo >= 200) & (multi.pitches_hi >= 200)]
    dz_off = (multi.groupby(["level_lo", "level_hi"])
              .apply(lambda g: np.average(g.decision_z_hi - g.decision_z_lo,
                                          weights=np.minimum(g.pitches_lo, g.pitches_hi)),
                     include_groups=False).rename("dz_offset").reset_index())
    dz_direct = dz_off.set_index(["level_lo", "level_hi"]).dz_offset

    def chain_dz(level: str) -> float:
        if (level, "MLB") in dz_direct.index:
            return float(dz_direct.loc[(level, "MLB")])
        off, lv = 0.0, level
        while lv != "MLB":
            nxt = step_up[lv]
            if (lv, nxt) in dz_direct.index:
                off += float(dz_direct.loc[(lv, nxt)])
            lv = nxt
        return off

    for level in cur.level.unique():
        cur.loc[cur.level == level, "mlb_equiv_decision_plus"] = (
            100 + 15 * (cur.loc[cur.level == level, "decision_z"] + chain_dz(level)))

    out_path = DATA_PROCESSED / "shipped_projections_2026.parquet"
    cur.to_parquet(out_path, index=False)
    dz_off.to_csv(OUTPUTS / "translation" / "decision_z_level_offsets.csv", index=False)
    print(f"{len(cur)} shipped rows -> {out_path}")
    print(cur.groupby("level").agg(
        n=("batter_id", "size"),
        med_dplus=("decision_plus", "median"),
        med_projk=("proj_k_pct", "median"),
        med_projbb=("proj_bb_pct", "median"),
        med_mlb_k=("mlb_equiv_k_pct", "median")).round(3).to_string())
    print("\ndecision_z level offsets:")
    print(dz_off.round(3).to_string(index=False))
    log_run("ship_projections_v1", season=SHIP_SEASON, n=len(cur))


if __name__ == "__main__":
    main()
