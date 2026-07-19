# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Ground-truth audit + historical baselines (Models A-E).

Targets: next-season K%, BB%, BB-K% (primary next-season level by PA).
Baselines are statline-only and use deep history. Decision+ features are
merged in (Models D/E) when --decision-file is provided, so the incremental
value of pitch-level behavior is measured against an honest baseline.

Validation: time-based. Train on seasons <= train_end, evaluate on later
seasons. All rates are EB-shrunk within level-season before modeling.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, OUTPUTS, log_run

MIN_PA = 100
MIN_NEXT_PA = 100
SEED = 42


def eb_shrink(df: pd.DataFrame, rate_col: str, n_col: str, group_cols: list[str]) -> pd.Series:
    """Empirical-Bayes shrink a rate toward its group mean (moment matching)."""
    out = pd.Series(index=df.index, dtype=float)
    for _, idx in df.groupby(group_cols).groups.items():
        g = df.loc[idx]
        p, n = g[rate_col].astype(float), g[n_col].astype(float)
        mu = np.average(p, weights=n)
        var_obs = np.average((p - mu) ** 2, weights=n)
        # noise term weighted like var_obs, else tiny-sample players inflate
        # it past var_obs and k explodes (crushes everyone to the mean)
        mean_noise = np.average(mu * (1 - mu) / n, weights=n)
        var_true = max(var_obs - mean_noise, 1e-6)
        k = min(mu * (1 - mu) / var_true, 5000.0)  # effective prior sample size
        out.loc[idx] = (p * n + mu * k) / (n + k)
    return out


def load_frame() -> pd.DataFrame:
    spine = pd.read_parquet(DATA_PROCESSED / "statline_spine.parquet")
    pairs = pd.read_parquet(DATA_PROCESSED / "next_season_pairs.parquet")
    pairs = pairs[(pairs.pa >= MIN_PA) & (pairs.next_pa >= MIN_NEXT_PA)].copy()
    # primary next-season row = the level with the most PA
    pairs = (pairs.sort_values("next_pa", ascending=False)
             .drop_duplicates(subset=["player_id", "season", "level"], keep="first"))
    pairs["bbk"] = pairs.bb_pct - pairs.k_pct
    pairs["next_bbk"] = pairs.next_bb_pct - pairs.next_k_pct
    pairs["k_pct_shrunk"] = eb_shrink(pairs, "k_pct", "pa", ["level", "season"])
    pairs["bb_pct_shrunk"] = eb_shrink(pairs, "bb_pct", "pa", ["level", "season"])
    pairs["log_pa"] = np.log(pairs.pa)
    return pairs


def ground_truth_audit(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for level, g in pairs.groupby("level"):
        for tgt, cur in [("next_k_pct", "k_pct"), ("next_bb_pct", "bb_pct"),
                         ("next_bbk", "bbk")]:
            gg = g.dropna(subset=[tgt, cur])
            if len(gg) < 50:
                continue
            rows.append({
                "level": level, "target": tgt, "n": len(gg),
                "y2y_pearson": round(pearsonr(gg[cur], gg[tgt])[0], 4),
                "y2y_spearman": round(spearmanr(gg[cur], gg[tgt])[0], 4),
                "sd_current": round(float(gg[cur].std()), 4),
                "sd_next": round(float(gg[tgt].std()), 4),
            })
    return pd.DataFrame(rows)


def eval_model(train: pd.DataFrame, test: pd.DataFrame, feats: list[str], tgt: str,
               residual_on: str | None = None) -> dict:
    tr = train.dropna(subset=feats + [tgt])
    te = test.dropna(subset=feats + [tgt])
    if len(tr) < 100 or len(te) < 50:
        return {}
    if residual_on:
        comp = [f for f in feats if f != residual_on]
        sc = StandardScaler().fit(tr[comp])
        rmodel = Ridge(alpha=RESIDUAL_ALPHA, random_state=SEED).fit(
            sc.transform(tr[comp]), tr[tgt] - tr[residual_on])
        pred = te[residual_on].values + rmodel.predict(sc.transform(te[comp]))
    else:
        sc = StandardScaler().fit(tr[feats])
        model = Ridge(alpha=1.0, random_state=SEED).fit(sc.transform(tr[feats]), tr[tgt])
        pred = model.predict(sc.transform(te[feats]))
    err = pred - te[tgt]
    ss_res = float((err ** 2).sum())
    ss_tot = float(((te[tgt] - tr[tgt].mean()) ** 2).sum())
    return {
        "n_train": len(tr), "n_test": len(te),
        "pearson": round(pearsonr(pred, te[tgt])[0], 4),
        "spearman": round(spearmanr(pred, te[tgt])[0], 4),
        "r2": round(1 - ss_res / ss_tot, 4),
        "mae": round(float(np.abs(err).mean()), 5),
        "rmse": round(float(np.sqrt((err ** 2).mean())), 5),
    }


MODEL_FEATURES = {
    "A_histK": ["k_pct_shrunk"],
    "B_histBB": ["bb_pct_shrunk"],
    "C_hist_age": ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa"],
}
DECISION_FEATURES = {
    "D_plus_decision": ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa", "decision_plus"],
    # whiff deliberately excluded: whiff% == 1 - contact% (perfect collinearity)
    "E_plus_components": ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa", "decision_plus",
                          "contact_shrunk", "take_ball_shrunk"],
    # Z: adds universal-zone behavior (chase, in-zone take, z-contact)
    "Z_plus_zone": ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa", "decision_plus",
                    "contact_shrunk", "take_ball_shrunk",
                    "chase_shrunk", "z_take_shrunk", "zcontact_shrunk"],
    # F: deep-history Model-C prediction fused with behavior components
    "F_fusion": ["c_deep_pred", "decision_plus", "contact_shrunk", "take_ball_shrunk"],
    # G: deep prediction kept intact; components learn only the residual
    "G_residual": ["c_deep_pred", "decision_plus", "contact_shrunk", "take_ball_shrunk"],
}
RESIDUAL_ALPHA = 25.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-end", type=int, default=2023)
    ap.add_argument("--decision-file", type=str, default=None)
    ap.add_argument("--tag", type=str, default="baselines_v1")
    ap.add_argument("--common-sample", action="store_true",
                    help="restrict ALL models to rows where every feature "
                         "(incl. Decision+) exists, so deltas are honest")
    args = ap.parse_args()

    pairs = load_frame()
    model_specs = dict(MODEL_FEATURES)
    if args.decision_file:
        dec = pd.read_parquet(args.decision_file)
        keep = ["batter_id", "season", "level", "decision_plus", "take_ball_shrunk",
                "chase_shrunk", "z_take_shrunk", "zcontact_shrunk",
                "contact_pct", "whiff_pct", "swing_pct", "pitches"]
        dec = dec[[c for c in keep if c in dec.columns]].rename(
            columns={"contact_pct": "contact_raw", "whiff_pct": "whiff_raw",
                     "pitches": "pitches_dec"})
        pairs = pairs.merge(dec, left_on=["player_id", "season", "level"],
                            right_on=["batter_id", "season", "level"], how="left")
        pairs["swings_est"] = (pairs.pitches_dec * pairs.swing_pct).clip(lower=1)
        ok = pairs.contact_raw.notna()
        pairs.loc[ok, "contact_shrunk"] = eb_shrink(
            pairs[ok].rename(columns={"contact_raw": "r"}), "r", "swings_est",
            ["level", "season"]).values
        pairs.loc[ok, "whiff_shrunk"] = eb_shrink(
            pairs[ok].rename(columns={"whiff_raw": "r"}), "r", "swings_est",
            ["level", "season"]).values
        model_specs.update(DECISION_FEATURES)

    out_dir = OUTPUTS / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)

    gt = ground_truth_audit(pairs)
    gt.to_csv(out_dir / f"{args.tag}_ground_truth_audit.csv", index=False)
    print("=== ground truth audit (y2y) ===")
    print(gt.to_string(index=False))

    # stage-1 deep-history Model C predictions (per level/target), fit on the
    # FULL deep train window before any common-sample restriction.
    # Train-window rows get OUT-OF-FOLD predictions (5-fold by player) so the
    # stage-2 residual learner never sees in-sample stage-1 residuals.
    if args.decision_file:
        c_feats = MODEL_FEATURES["C_hist_age"]
        rng = np.random.default_rng(SEED)
        for tgt in ["next_k_pct", "next_bb_pct", "next_bbk"]:
            col = f"c_deep_pred_{tgt}"
            pairs[col] = np.nan
            for level in pairs.level.unique():
                lv_mask = pairs.level == level
                tr_mask = lv_mask & (pairs.season <= args.train_end)
                tr = pairs[tr_mask].dropna(subset=c_feats + [tgt])
                if len(tr) < 150:
                    continue
                players = tr.player_id.unique()
                fold_of = dict(zip(players, rng.integers(0, 5, size=len(players))))
                tr_folds = tr.player_id.map(fold_of)
                for fold in range(5):
                    fit_rows = tr[tr_folds != fold]
                    oof_rows = tr[tr_folds == fold]
                    if len(fit_rows) < 100 or len(oof_rows) == 0:
                        continue
                    sc = StandardScaler().fit(fit_rows[c_feats])
                    mdl = Ridge(alpha=1.0, random_state=SEED).fit(
                        sc.transform(fit_rows[c_feats]), fit_rows[tgt])
                    pairs.loc[oof_rows.index, col] = mdl.predict(
                        sc.transform(oof_rows[c_feats]))
                # full-train model for post-train_end rows
                sc = StandardScaler().fit(tr[c_feats])
                mdl = Ridge(alpha=1.0, random_state=SEED).fit(
                    sc.transform(tr[c_feats]), tr[tgt])
                ok = lv_mask & (pairs.season > args.train_end) & \
                    pairs[c_feats].notna().all(axis=1)
                pairs.loc[ok, col] = mdl.predict(sc.transform(pairs.loc[ok, c_feats]))

    if args.common_sample:
        all_feats = sorted({f for fs in model_specs.values() for f in fs
                            if f != "c_deep_pred"})
        pairs = pairs.dropna(subset=[f for f in all_feats if f in pairs.columns])
    train = pairs[pairs.season <= args.train_end]
    test = pairs[pairs.season > args.train_end]
    rows = []
    for level in ["AAA", "AA", "A+", "A", "CPX", "MLB"]:
        tr, te = train[train.level == level], test[test.level == level]
        for tgt in ["next_k_pct", "next_bb_pct", "next_bbk"]:
            if args.decision_file:
                tr = tr.copy(); te = te.copy()
                tr["c_deep_pred"] = tr[f"c_deep_pred_{tgt}"]
                te["c_deep_pred"] = te[f"c_deep_pred_{tgt}"]
            for name, feats in model_specs.items():
                res = eval_model(tr, te, feats, tgt,
                                 residual_on="c_deep_pred" if name == "G_residual" else None)
                if res:
                    rows.append({"level": level, "target": tgt, "model": name, **res})
    res_df = pd.DataFrame(rows)
    res_df.to_csv(out_dir / f"{args.tag}_model_race.csv", index=False)
    print("\n=== baseline race (time holdout: train<=%d) ===" % args.train_end)
    print(res_df.to_string(index=False))
    log_run(args.tag, train_end=args.train_end, decision_file=args.decision_file,
            n_pairs=len(pairs))


if __name__ == "__main__":
    main()
