# SDR / eWAR intake request to Will (2026-08-18)

Context: the 2026-08-16 master plan makes SDR + eWAR the site-primary defense
and WAR metrics. Your method stack is in the repo (defense-plus/,
milb-projections/ contracts + adapters + fixtures) and the receiving seam now
exists on our side (prospect-tracker/sdr_intake.py, tested against your own
pitcher_ewar_mlb fixture and contract). What is missing is DATA: no parquet,
no raw inputs, and no export path for the defense card. This doc is the exact
ask, shortest path first.

## 1. What we need dropped (data/drops/wills/, parquet or csv)

| # | stream | source on your side | status |
|---|---|---|---|
| 1 | pitcher_ewar_mlb | ~/pitcher_ewar/data/pitcher_ewar.parquet via adapters/export_pitcher_ewar_mlb.py | adapter EXISTS, run it |
| 2 | pitcher_ewar_milb_aaa | ~/milb_pitcher_ewar/data/aaa_pitcher_ewar.parquet via export_pitcher_ewar_milb.py | adapter EXISTS, run it |
| 3 | sdr_defense_card | ~/swing_plus/data/processed/defense_card.parquet (build_defense_projection.py output) plus the per-season composite rows behind it | NO adapter exists, see 2. |
| 4 | identity | your identity export | adapter EXISTS, run it |

File naming: `<stream>__<YYYY-MM-DD>.parquet`. Preflight on our side:
`python sdr_intake.py --stream <stream> --validate <file>` (exit 0 = clean;
the census prints with it). Nothing is accepted without it.

## 2. The defense card needs an export contract (the one real gap)

defense-plus writes to your home dir with no handoff contract or adapter.
We declared a receiving contract in sdr_intake.DEFENSE_CARD_CONTRACT; adopt
it or amend it, but per-row we need at minimum:

- player_id (mlbam), season, primary_position, innings, sdr_runs
- component columns where applicable: range_runs, arm_runs, framing_runs,
  blocking_runs, dp_runs. IMPORTANT: a drop whose only live signal is
  range-class is refused by the intake, because an OAA/rfield-class blend is
  a settled loss on the eWAR w-grid; the components are what make SDR new
  (your 05_skill_composites + 25_catcher_components are exactly that).
- context: level (MLB or the MiLB level), as_of_date per row (vintage
  stamping; your pitcher-eWAR contract already does this), sdr_runs_sd or
  reliability (your N0 innings-shrinkage convention is fine), player_name.

We need PER-SEASON rows (the observed composite per season), not only the
projection card: validation runs on year-over-year persistence and forward
team-runs legs, which a single projected row cannot support.

## 3. Questions the census cannot answer without you

1. Does 15_milb_translation produce PLAYER-LEVEL MiLB SDR (by level and
   season)? If yes, drop it as part of stream 3 (level column distinguishes);
   if no, say so and the MiLB gate records "no MiLB coverage" instead of
   waiting forever.
2. Catcher coverage: do framing/blocking components ship for catchers across
   all seasons, or from a tracking cutoff? Which seasons?
3. Coverage declaration per stream: seasons, positions, levels, and the
   innings floor you consider reliable.
4. Refresh cadence you can sustain (monthly is fine; the manifest ledger
   handles any cadence).
5. Attribution and licensing line for publishing SDR values on the site
   (the page will credit the model; we need the exact line you want).

## 4. What happens on arrival (so the bar is visible)

Census committed first (data/sdr_census.json), then three pre-registered
gates run in order: docs/sdr-2026-08-18/SDR_EVAL_GATE.md (MLB validation),
EWAR_V3_MERGE_GATE.md (the w-grid re-run your components qualify for),
MILB_SDR_EVAL_GATE.md (the source of every public MiLB SDR claim). Clauses
are frozen now, before data, and will not move after.
