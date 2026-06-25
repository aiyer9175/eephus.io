# MiLB Decision+ (rebuilt)

Full rebuild of the MiLB swing-decision system. See `REPORT.md` for the complete
research report (validation gates, incremental-value audits, approved/rejected
outputs).

## Open the tool

```bash
open outputs/tool/milb_decision_plus_tool.html
```

## Pipeline (run order)

```bash
.venv/bin/python scripts/build_game_manifest.py        # schedules -> game universe
.venv/bin/python scripts/extract_pitches.py            # 68,866 game feeds (resumable)
.venv/bin/python scripts/pull_official_statlines.py    # ground-truth statlines
.venv/bin/python scripts/build_player_metrics.py       # behavior aggregation
.venv/bin/python scripts/validate_reconstruction.py    # PA/K/BB gate (must PASS)
.venv/bin/python scripts/build_transitions.py          # spine + transition pairs
.venv/bin/python scripts/build_decision_plus.py        # Decision+ + tiers + EB
.venv/bin/python scripts/ground_truth_and_baselines.py --decision-file data/processed/decision_plus.parquet --common-sample --tag X
.venv/bin/python scripts/model_strategy_race.py        # ridge/EN/GAM/GBM race
.venv/bin/python scripts/build_level_translation.py    # ladder + promotion fits
.venv/bin/python scripts/run_audits.py                 # leakage/calibration/stress
.venv/bin/python scripts/ship_projections.py           # 2026 projections
.venv/bin/python scripts/build_tool.py                 # leaderboards + HTML tool
```

Run log: `reports/run_log.jsonl`. Exports for the main projection model:
`outputs/exports/`.

## Headlines

- Dataset gate PASS: reconstructed PA/K/BB match official lines (K/BB ≥99.6% exact).
- AA/A+ have **zero** public pitch tracking; the call-code core (take-ball share,
  2-strike discipline, count-state selectivity) works at every level.
- Composite Decision+ = descriptive only. Components add projection value at A/A+
  (+1.5–3.9pp R²); deep statline history wins at AAA/AA; ridge ships everywhere.
