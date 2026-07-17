# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Build MiLB Decision+ with EB shrinkage, data-quality tiers, and context.

Decision+ core uses only call-code DECISION components (available at every
level): take quality, 2-strike called-strike avoidance, count-state swing
selectivity. Contact/whiff are execution skills and are deliberately kept
out of the composite (they enter Model E of the incremental audit
separately). Zone components (chase, in-zone take, zone recognition) are a
Tier-A overlay where tracking exists -- never imputed where it does not.

Component weights are learned on next-season BB-K with training seasons
<= TRAIN_END only, so the composite is validated against the future and is
not mechanically the player's own BB%.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, OUTPUTS, log_run

TRAIN_END = 2023
SEED = 42
MIN_PITCHES_B = 300      # below this, behavior sample too thin -> Tier C
TRACKED_SHARE_A = 0.5    # at/above this share with enough tracked pitches -> Tier A
MIN_TRACKED_A = 500

CORE_COMPONENTS = {
    # name: (rate_col, n_col, direction)  direction: +1 higher=better discipline
    "take_ball": ("take_ball_share", "n_takes_eff", +1),
    "ts_called": ("ts_called_share", "ts_pitches", -1),
    "fp_swing": ("fp_swing_pct", "fp_pitches", 0),   # direction learned
    "tb_swing": ("tb_swing_pct", "tb_pitches", 0),
    "swing": ("swing_pct", "pitches", 0),
    # zone components: universal coverage via calibrated stringer coords
    # (95.9% in/out agreement holdout; 93.5% OOD minors-stringer parks)
    "chase": ("o_swing_pct", "o_pitches", -1),
    "z_take": ("z_take_pct", "z_pitches", 0),
    "zone_rec": ("zone_recognition", "z_pitches", +1),
}
ZONE_COMPONENTS: dict = {}  # merged into core now that coverage is universal


def eb_shrink_with_rel(df, rate_col, n_col, group_cols):
    """Moment-matching EB shrink; returns (shrunk, reliability)."""
    shrunk = pd.Series(np.nan, index=df.index)
    rel = pd.Series(np.nan, index=df.index)
    ok = df[rate_col].notna() & (df[n_col] > 0)
    for _, idx in df[ok].groupby(group_cols).groups.items():
        g = df.loc[idx]
        p, n = g[rate_col].astype(float), g[n_col].astype(float)
        if len(g) < 20:
            continue
        mu = np.average(p, weights=n)
        var_obs = np.average((p - mu) ** 2, weights=n)
        pq = max(mu * (1 - mu), 1e-4)
        # noise term weighted like var_obs, else tiny-sample players inflate
        # it past var_obs and k explodes (crushes everyone to the mean)
        mean_noise = np.average(pq / n, weights=n)
        var_true = max(var_obs - mean_noise, 1e-6)
        k = min(pq / var_true, 5000.0)
        shrunk.loc[idx] = (p * n + mu * k) / (n + k)
        rel.loc[idx] = n / (n + k)
    return shrunk, rel


def zscore_within(df, col, group_cols, weight_col=None):
    def _z(g):
        x = g[col]
        if weight_col:
            mu = np.average(x, weights=g[weight_col])
            sd = np.sqrt(np.average((x - mu) ** 2, weights=g[weight_col]))
        else:
            mu, sd = x.mean(), x.std()
        return (x - mu) / (sd if sd > 1e-9 else 1.0)
    return df.groupby(group_cols, group_keys=False).apply(_z, include_groups=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", default=str(DATA_PROCESSED / "player_season_level_metrics.parquet"))
    args = ap.parse_args()

    m = pd.read_parquet(args.metrics)
    m = m[m.pitches > 0].copy()
    m["n_takes_eff"] = m.balls_taken + m.called_strikes

    # ---------------- data-quality tiers ----------------
    # A = true ball-tracking zone data; B = calibrated stringer zone data
    # (universal; ~94-96% in/out accuracy); C = thin sample; D = inconsistent
    m["tier"] = "C"
    enough = m.pitches >= MIN_PITCHES_B
    m.loc[enough & (m.zone_coverage >= 0.8), "tier"] = "B"
    m.loc[enough & (m.tracked_share >= TRACKED_SHARE_A) & (m.n_tracked >= MIN_TRACKED_A), "tier"] = "A"
    # D: internal inconsistency (PA recorded but virtually no pitches)
    m.loc[(m.pa >= 50) & (m.pitches < 0.5 * m.pa), "tier"] = "D"

    # ---------------- EB shrink components ----------------
    grp = ["level", "season"]
    all_comps = {**CORE_COMPONENTS, **ZONE_COMPONENTS}
    for name, (rate, ncol, _) in all_comps.items():
        m[f"{name}_shrunk"], m[f"{name}_rel"] = eb_shrink_with_rel(m, rate, ncol, grp)
        m[f"{name}_z"] = zscore_within(m, f"{name}_shrunk", grp)
    # z-contact: execution skill, shrunk for the projection models but kept
    # OUT of the decision composite
    m["zcontact_shrunk"], _ = eb_shrink_with_rel(m, "z_contact_pct", "z_swings", grp)

    # ---------------- composite weights from future BB-K ----------------
    spine = pd.read_parquet(DATA_PROCESSED / "next_season_pairs.parquet")
    spine = spine[(spine.pa >= 100) & (spine.next_pa >= 100)]
    spine = (spine.sort_values("next_pa", ascending=False)
             .drop_duplicates(["player_id", "season", "level"]))
    spine["next_bbk"] = spine.next_bb_pct - spine.next_k_pct
    tgt = spine[["player_id", "season", "level", "next_bbk"]].rename(
        columns={"player_id": "batter_id"})
    mm = m.merge(tgt, on=["batter_id", "season", "level"], how="left")

    core_z = [f"{c}_z" for c in CORE_COMPONENTS]
    train = mm[(mm.season <= TRAIN_END) & mm.next_bbk.notna() & (mm.tier.isin(["A", "B"]))]
    train = train.dropna(subset=core_z)
    sc = StandardScaler().fit(train[core_z])
    ridge = Ridge(alpha=10.0, random_state=SEED).fit(
        sc.transform(train[core_z]), train.next_bbk)
    weights = pd.Series(ridge.coef_, index=core_z)
    wnorm = weights / weights.abs().sum()
    print("=== core component weights (target: next-season BB-K, train<=%d, n=%d) ===" % (TRAIN_END, len(train)))
    print(wnorm.round(4).to_string())

    # component standalone validation
    comp_rows = []
    for c in core_z + [f"{z}_z" for z in ZONE_COMPONENTS]:
        sub = mm[(mm.season <= TRAIN_END)].dropna(subset=[c, "next_bbk"])
        if len(sub) > 200:
            comp_rows.append({"component": c, "n": len(sub),
                              "r_next_bbk": round(pearsonr(sub[c], sub.next_bbk)[0], 4)})
    comp_df = pd.DataFrame(comp_rows)
    print("\n=== component standalone vs next BB-K ===")
    print(comp_df.to_string(index=False))

    # ---------------- score ----------------
    z_mat = mm[core_z].fillna(0.0)
    raw_val = z_mat @ wnorm.values
    mm["decision_value_raw"] = raw_val
    # rescale within level-season to Decision+ (100 +/- 15)
    mm["decision_z"] = zscore_within(mm, "decision_value_raw", grp)
    mm["decision_plus"] = 100 + 15 * mm.decision_z

    # composite reliability calibrated empirically from same-level y2y
    # stability of decision_z by pitch bucket (r=.30 @ ~300 pitches,
    # .64 @ ~2300; implied k_eff ~700-1300 -> use 900). Conservative:
    # y2y r also absorbs true talent change.
    K_EFF_PITCHES = 800.0  # re-calibrated post zone/shrinkage fix (y2y r .56@700, .75@2300)
    mm["reliability"] = mm.pitches / (mm.pitches + K_EFF_PITCHES)
    mm["posterior_sd"] = 15 * np.sqrt(np.clip(1 - mm.reliability, 0.02, 1.0))
    mm["ci80_lo"] = mm.decision_plus - 1.282 * mm.posterior_sd
    mm["ci80_hi"] = mm.decision_plus + 1.282 * mm.posterior_sd

    # ---------------- age/level context ----------------
    lvl_age = (mm.groupby(grp).apply(
        lambda g: np.average(g.age.dropna(), weights=g.loc[g.age.notna(), "pa"].clip(lower=1)),
        include_groups=False).rename("level_age_mean").reset_index())
    mm = mm.merge(lvl_age, on=grp, how="left")
    mm["age_vs_level"] = mm.age - mm.level_age_mean
    prior = mm[["batter_id", "season", "level"]].copy()
    prior["season"] += 1
    prior["repeat_level"] = True
    mm = mm.merge(prior.drop_duplicates(), on=["batter_id", "season", "level"], how="left")
    mm["repeat_level"] = mm.repeat_level.fillna(False)

    # ---------------- redundancy vs BB% ----------------
    print("\n=== redundancy check (within level, season<=%d) ===" % TRAIN_END)
    for level in ["AAA", "AA", "A+", "A", "CPX", "MLB"]:
        sub = mm[(mm.level == level) & (mm.season <= TRAIN_END) & (mm.pa >= 200)].dropna(
            subset=["decision_plus", "bb_pct", "k_pct", "next_bbk"])
        if len(sub) < 100:
            continue
        r_bb = pearsonr(sub.decision_plus, sub.bb_pct)[0]
        r_k = pearsonr(sub.decision_plus, sub.k_pct)[0]
        # partial: decision+ vs next_bbk controlling current bb%
        def resid(y, x):
            b = np.polyfit(x, y, 1)
            return y - np.polyval(b, x)
        pr = pearsonr(resid(sub.decision_plus, sub.bb_pct),
                      resid(sub.next_bbk, sub.bb_pct))[0]
        print(f"{level:>4}: r(D+,BB%)={r_bb:+.3f}  r(D+,K%)={r_k:+.3f}  "
              f"partial r(D+, next BBK | BB%)={pr:+.3f}  n={len(sub)}")

    # ---------------- write ----------------
    out_cols = ["batter_id", "batter_name", "season", "level", "tier", "age",
                "age_vs_level", "repeat_level", "pa", "pitches", "n_tracked",
                "tracked_share", "k_pct", "bb_pct",
                "decision_plus", "decision_z", "decision_value_raw", "reliability",
                "posterior_sd", "ci80_lo", "ci80_hi", "zone_overlay"] + \
        [f"{c}_shrunk" for c in all_comps] + [f"{c}_z" for c in all_comps] + \
        ["zcontact_shrunk", "zone_coverage", "contact_pct", "whiff_pct",
         "swing_pct", "o_swing_pct", "z_swing_pct",
         "z_contact_pct", "zone_rate", "take_ball_share", "csw_pct"]
    out = mm[[c for c in out_cols if c in mm.columns]].copy()
    out_path = DATA_PROCESSED / "decision_plus.parquet"
    out.to_parquet(out_path, index=False)
    wnorm.to_csv(OUTPUTS / "decision_plus_weights.csv")
    comp_df.to_csv(OUTPUTS / "decision_plus_component_validation.csv", index=False)
    print(f"\n{len(out)} rows -> {out_path}")
    print("tier distribution:")
    print(out.groupby(["level", "tier"]).size().unstack(fill_value=0).to_string())
    log_run("decision_plus_v1", n=len(out), train_end=TRAIN_END,
            weights=wnorm.round(4).to_dict())


if __name__ == "__main__":
    main()
