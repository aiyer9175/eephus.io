# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
sanity_check.py — Battery of health checks on the Swing+ / predicted-stats /
PA-value model family. Prints PASS / WARN / FAIL with reference ranges.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

PROC = Path(__file__).parent / "data" / "processed"
ROOT = Path(__file__).parent
n_pass = n_warn = n_fail = 0


def check(name, value, ok_lo, ok_hi, fmt="{:.3f}", warn_only=False):
    global n_pass, n_warn, n_fail
    v = float(value)
    ok = ok_lo <= v <= ok_hi
    tag = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    if ok: n_pass += 1
    elif warn_only: n_warn += 1
    else: n_fail += 1
    print(f"  [{tag}] {name:<48} {fmt.format(v):>10}   expect [{ok_lo}, {ok_hi}]")


def main():
    half = pd.read_parquet(PROC / "leaderboard_half.parquet")
    at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")

    print("=" * 80)
    print("1. ARTIFACTS LOAD")
    print("=" * 80)
    from swing_plus import SwingPlusModel
    from predicted_stats import PredictedStatsModel
    from pa_value import PAValueModel
    sp = SwingPlusModel(ROOT / "swing_plus_model_v1.joblib")
    ps = PredictedStatsModel(ROOT / "predicted_stats_models.joblib")
    pv = PAValueModel(ROOT / "pa_value_models.joblib")
    print(f"  [PASS] Swing+ v{sp.version}, {len(sp.features)} feats | "
          f"PredStats {len(ps.models)} models | PA-value v{pv.version}, {len(pv.features)} feats")
    global n_pass; n_pass += 1

    print("\n" + "=" * 80)
    print("2. COVERAGE")
    print("=" * 80)
    print(f"  players: {at['batter'].nunique()} | player-halves: {len(half)} | "
          f"halves: {sorted(half['half'].unique())}")
    thin = (half['n_pa'] < 150).mean() * 100
    check("% player-halves with <150 PA (thin)", thin, 0, 35, "{:.0f}%", warn_only=True)
    check("dup (batter,half) rows", half.duplicated(['batter','half']).sum(), 0, 0, "{:.0f}")
    check("unmapped player names (half)", half['name'].isna().sum(), 0, 0, "{:.0f}")

    print("\n" + "=" * 80)
    print("3. SCALE vs KNOWN MLB AVERAGES  (PA/swing-weighted over qualified sample)")
    print("=" * 80)
    wsp = np.average(half['swing_plus'], weights=half['n_swings'])
    check("Swing+ mean (calibrated to 100)", wsp, 96, 104, "{:.1f}")
    check("league obs_xwOBA (PA-wtd)", np.average(half['obs_xwoba'], weights=half['n_pa']), .305, .335)
    check("league blended_xwOBA (PA-wtd)", np.average(half['blended_xwoba'], weights=half['n_pa']), .305, .335)
    check("league pred_avg_ev", np.average(half['pred_avg_ev'], weights=half['n_swings']), 87, 90, "{:.1f}")
    check("league pred_hard_hit_pct", np.average(half['pred_hard_hit_pct'], weights=half['n_swings']), 35, 43, "{:.1f}")
    check("league pred_barrel_pct", np.average(half['pred_barrel_pct'], weights=half['n_swings']), 6, 10, "{:.1f}")

    print("\n" + "=" * 80)
    print("4. APPROACH FEATURE RANGES (plausibility)")
    print("=" * 80)
    for col, lo, hi in [("whiff_rate", .08, .40), ("chase_rate", .12, .45),
                        ("swing_rate", .35, .60), ("z_contact_rate", .70, .98),
                        ("o_contact_rate", .35, .85)]:
        if col in half.columns:
            check(f"{col} median", half[col].median(), lo, hi)

    print("\n" + "=" * 80)
    print("5. FACE VALIDITY")
    print("=" * 80)
    top = at.nlargest(5, 'swing_plus')['name'].tolist()
    bot = at.nsmallest(5, 'swing_plus')['name'].tolist()
    print(f"  Swing+ TOP5:    {top}")
    print(f"  Swing+ BOTTOM5: {bot}")
    topx = at.nlargest(5, 'blended_xwoba')['name'].tolist()
    print(f"  xwOBA  TOP5:    {topx}")
    elite = {"Aaron Judge","Shohei Ohtani","Juan Soto","Kyle Schwarber","Giancarlo Stanton","Yordan Álvarez"}
    hit = len(set(top) & elite) + len(set(topx) & elite)
    check("elite names in top lists (of 10 slots)", hit, 4, 10, "{:.0f}")

    print("\n" + "=" * 80)
    print("6. INTERNAL CONSISTENCY (correlations across metrics)")
    print("=" * 80)
    c1 = at['swing_plus'].corr(at['pred_xwobacon'])
    check("Swing+ vs pred_xwOBAcon", c1, .70, .99)
    c2 = at['swing_plus'].corr(at['blended_xwoba'])
    check("Swing+ vs blended_xwOBA", c2, .45, .90)
    c3 = at['pred_barrel_pct'].corr(at['pred_avg_ev'])
    check("pred Barrel% vs pred EV", c3, .70, .99)

    print("\n" + "=" * 80)
    print("7. CALIBRATION (high-PA: blended xwOBA should be ~unbiased vs observed)")
    print("=" * 80)
    hi = at[at['n_pa'] >= 1000]
    bias = (hi['blended_xwoba'] - hi['obs_xwoba']).mean()
    check("blended - obs bias (PA>=1000)", abs(bias), 0, .012, "{:.4f}")
    mae = (hi['blended_xwoba'] - hi['obs_xwoba']).abs().mean()
    check("blended vs obs MAE (PA>=1000)", mae, 0, .020, "{:.4f}")

    print("\n" + "=" * 80)
    print("8. STABILITY (half-to-half reliability)")
    print("=" * 80)
    def nxt(h):
        s, sh = h.split("_"); return f"{s}_H2" if sh=="H1" else f"{int(s)+1}_H1"
    half2 = half.copy(); half2['next_half'] = half2['half'].map(nxt)
    for col, lo in [("swing_plus", .80), ("blended_xwoba", .55), ("pred_barrel_pct", .70)]:
        nx = half[['batter','half',col]].rename(columns={'half':'next_half', col:col+'_n'})
        pr = half2.merge(nx, on=['batter','next_half'])
        r = pr[col].corr(pr[col+'_n'])
        check(f"{col} half-to-half r", r, lo, 1.0)

    print("\n" + "=" * 80)
    print(f"SUMMARY: {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL")
    print("=" * 80)


if __name__ == "__main__":
    main()
