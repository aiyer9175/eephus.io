# Module 19 — Registered Forward Test: 2026 vs FG Depth Charts

- trained on 14584 pairs (targets <=2025); scored 667 incumbents for 2026
- steamer_2026 archive NOT served (500) — frozen without it
- zips_2026 archive NOT served (500) — frozen without it
- frozen table saved: (667, 10); coverage {'pa_ours': '100%', 'pa_dc': '83%', 'pa_atc': '84%', 'pa_steamer': '0%', 'pa_zips': '0%'}

## PROVISIONAL scoreboard — Spearman vs 2026 PA through 6/11 (~40% of season; levels not comparable, ranks only; n=538)
- pa_ours: rho 0.8254 (n=538)
- pa_dc: rho 0.7597 (n=538)
- pa_atc: rho 0.7374 (n=538)
- pa_steamer: insufficient coverage
- pa_zips: insufficient coverage

Final scoring after the 2026 season: rerun pipeline/01 pull, then join realized PA to forward_test_2026.parquet and score all systems on R2/RMSE/MAE/Spearman. Universe = incumbents (MLB PA in 2025); our model excludes injury info BY DESIGN — DC/ATC embed spring injury news; note this when reading MAE.
