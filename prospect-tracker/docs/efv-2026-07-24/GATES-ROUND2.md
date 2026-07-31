# eFV round-2 program (2026-07-24e) - peak-WAR target, injury model, Pipeline Top-30 daily, disagreements, measurement calibration

Owner directives (this batch): (1) incorporate Peak WAR and/or 3yr-peak WAR (not just cumulative
first-6yr) into the eFV backtest/backfill if it improves the model; (2) keep bugfixing eFV +
surplus, push hit Spearman >.38 / AUC >.755 (hit currently 0.3834/0.7762 - both met; pit
0.303/0.7197 structurally lower); (3) improve eFV on the biggest disagreements; (4) calibrate the
measurement model for "what counts as more accurate", Clemens 2026 framework as basis; (5) MLB
Pipeline per-team Top 30 for 2026 updated recently - ingest correctly + apply to active prospects;
(6) get the team Top 30 grades FRESH DAILY, wired into run_daily/run_monthly; (7) improve the eFV
injury penalty to truly use injury history/severity.

Discipline unchanged: OOS-measured (efv_lab_runner / scoreboard), ship measured wins, ledger
losses. Same-run baseline = current shipped tree (hit 0.3834/0.7762, pit 0.303/0.7197).

## L1 PIPELINE-TOP30-DAILY (concrete data/pipeline fix, owner-explicit)
Diagnosis (verified): the per-team Top 30s in snapshots are stale at 2026-01-22 (the Jan preseason
release); MLB_PIPELINE_ORG_INTERVALS (scrapers.py:1740) hardcodes the {y}-01-22 date and runs only
as an occasional backfill (scrapers.py:3413), NOT daily. The daily Live Top-100
(run_mlb_pipeline_live, scrapers.py:1973, stamped today's date, wired run_monthly:775 d0b) is the
pattern to mirror. Fix: a run_mlb_pipeline_org_live() that scrapes the 30 /prospects/{cur}/{slug}
pages with TODAY's date stamp + a parse-health gate, wired into run_monthly d0b (and run_daily) so
per-team Top 30 grades refresh daily with proper vintage and flow to consensus (consensus.py:407
already maps "... Astros Top 30" -> HOU org). Verify: fresh-dated per-team rows land, ~800
non-Top-100 prospects get current grades, an active-board sample shows the updated grade. No gate
(data correctness). Registry note on the pipeline ingestion.

## L2 INJURY-HISTORY (eFV injury penalty improvement, owner-explicit)
Current _injury_factor (efv_score.py ~303-332) fires ONLY on il_on (currently-on-IL); base
0.70/0.82/0.90 by type, deepened by trailing 12mo days/stints, floor 0.5. The post-TJ
unconditional penalty was removed (healthy post-TJ is not an injury). GAP: it ignores a player's
injury HISTORY/durability track record when currently healthy. il_history now has coverage (DB
il_history: 2017 5 / ... / 2025 105 / 2026 993 rows). Build a durability signal from il_history
(career IL stints + days, recency-weighted; major-injury flags e.g. multiple TJ / shoulder) and
test TWO integration modes: (a) a LIVE overlay factor in efv_score (like _age_factor - a small
multiplicative durability discount for high-injury-history players even when healthy), and (b) a
TRAINED feature if resolved-cohort IL coverage now supports it (the 2027-revisit may have partly
arrived - CHECK il_history coverage on the resolved debuted cohort; if still ~zero pre-2024,
overlay-only). Gate the overlay on a ground-truth durability study (does career IL history predict
future missed time / lower realized WAR on the resolved pool?); ship the overlay if it is
signed-correct and bounded. Trained feature only if it clears the OOS bar. Artifact
data/xfv_injury_history_eval.json.

## L3 PEAK-WAR-TARGET (measurement calibration + model; owner-explicit + creative)
Current eFV target = first-6-season cumulative bWAR (bust-inclusive). Peak-WAR (single best season)
or 3yr-peak WAR (best consecutive-3 sum) rewards CEILING over accumulation - and FV is a talent/
ceiling scale, so a peak target may align better with what the grade should measure. Build peak +
3yr-peak WAR labels from career_war (the same per-season bWAR the cumulative target uses). Then:
(a) MEASUREMENT: re-score the CURRENT eFV predictions against the peak / 3yr-peak ground truth -
does eFV already rank peak-WAR well? does consensus? (this is "calibrate what counts as accurate").
(b) MODEL: retrain the eFV ridge with peak / 3yr-peak / a blend as the TARGET, forward-chained,
and measure OOS Spearman/AUC against BOTH the cumulative and the peak ground truth. Ship a target
change ONLY if it improves OOS rank accuracy without degrading the cumulative-WAR accuracy that
prices surplus (surplus needs cumulative for $; a peak-target grade + cumulative-target surplus can
coexist - state the split). Clemens-2026 basis: also test a SURPLUS-WEIGHTED accuracy metric (rank
players by realized surplus-value under the clemens_2026 valuation, so getting high-value players
right counts more) as the "more accurate" measurement. Artifact data/xfv_peak_war_eval.json +
data/xfv_measurement_calibration_eval.json.

## L4 BUGHUNT-2 + DISAGREEMENTS (owner: keep bugfixing + closer on biggest disagreements)
(a) Bug hunt round 2 on eFV + surplus (the G-BUGS pattern: adversarial find + verify; fresh eyes
on the wave-B/E/H changes - the calibration seam, the lambda override, the K-rebuild, the overlay,
the KRP decouple - for any regression or new defect). (b) Biggest-disagreements deep-dive: from the
scoreboard disagreement receipts (largest |eFV - consensus|, 58.9% right), characterize WHERE eFV
loses on the biggest misses and whether a feature/recalibration closes the gap - the int'l-bat AUC
weak cell + the top-of-board disagreements. Ship only measured wins. Artifacts
data/xfv_bughunt2_eval.json + data/xfv_disagreements_eval.json.

## Execution
L1 + L2 + L3 + L4 in parallel (disjoint files; scrapers/run_monthly for L1, efv_score/il_history
for L2, labs for L3/L4). Consolidate: apply concrete fixes (L1 ingestion, L2 overlay if it passes),
ship measured model wins (L3 target if it clears, L4 disagreement fixes), regen, scoreboard
re-baseline, golden/registry/RESULTS. No board-movement ceilings (owner standing directive).

## RESULTS
(appended after runs)

## RESULTS (round 2, 2026-07-24e)
- L1 PIPELINE-TOP30-DAILY: SHIPPED. Diagnosis confirmed - the per-team Top 30s were frozen at
  2026-01-22 (829 prospects in a team Top 30 but NOT the overall Top 100 carried stale January
  grades). New scrapers.run_mlb_pipeline_org_live() (30 org pages, today's date, parse-health
  gate validate_pipeline_org_boards >= 25 orgs x >= 20 players) wired into run_monthly d0b-ii
  (reached by run_daily both paths). RAN the refresh: 900 rows upserted to 2026-07-24 (upsert
  bumps the frozen Jan rows in place, no dup; grades re-freshen too - Max Clark seed 55 -> 60).
  Fresh grades flow to consensus (consensus.py:407 org mapping verified). Current 2026 org pages
  are published (board tops carry the 2026 draft class). eFV/consensus regenerated on the fresh
  vintage.
- L2 INJURY-HISTORY: LEDGER (coverage-starved, no ship). Ground-truth study: il_history tracking
  effectively began 2026-06 (993/1240 stints >= 2026; 96% of players have exactly 1 stint);
  il_stints_pre nonzero on 2/845 debuted hitters, 0/981 pitchers -> a TRAINED feature is
  impossible. Contemporaneous cross-section is WRONG-signed (severe-IL players realize HIGHER WAR
  - a 40-man-status selection artifact). The one causally-valid forward test (pre-2026 IL ->
  2026 WAR) is correctly-signed (has-history 0.297 vs 0.511) but NULL (n=21, p=0.18). Delivered
  a bounded default-OFF overlay scaffold (efv_score, flag EEPHUS_INJURY_HISTORY, floor 0.85, 10
  hit + 10 pit if enabled) - flag OFF = byte-identical, no served change. Revival when IL history
  matures (~2028 resolved cohorts). Artifact data/xfv_injury_history_eval.json.
- L3 PEAK-WAR + MEASUREMENT CALIBRATION: LEDGER (keep cumulative target) + VALUABLE MEASUREMENT
  VALIDATION. eFV ranks peak-WAR EVEN BETTER than cumulative (hit peak1 0.5251 / peak3 0.476 vs
  cumul 0.3834; pit 0.373/0.329 vs 0.303) and beats consensus on peak both sides - the model
  demonstrably tracks ceiling/talent, validating the grade against the "is it a real talent
  scale" critique. Surplus-weighted (clemens_2026): eFV wins broad (weighted Spearman + top-decile
  both sides) but thins at the high-surplus tip. MODEL: retraining on peak1/peak3/blend targets =
  NO variant clears lo95>0; training on peak3 ranks peak3 WORSE (0.471) than the cumulative-trained
  model (0.476) - the cumulative target is Pareto-optimal (ranks ceiling as well as a peak model
  AND prices surplus). VERDICT: keep first-6yr cumulative bWAR; no split needed. Artifacts
  data/xfv_peak_war_eval.json + data/xfv_measurement_calibration_eval.json.
- L4 BUGHUNT-2 + DISAGREEMENTS: no served defect + ONE measurement fix SHIPPED. Bug hunt: all 6
  invariants PASS across the session's changes (calibration once, surplus not double-applied,
  overlay bounded max 2.16/2.36 FV, lambda 0.85/0.54 correct) - the many changes are internally
  consistent. SHIPPED the OBS-1 fix: source_backtest archetype AUC was scoring player-YEARS (no
  dedup, intl_bat ~2.4x inflated) vs the leakage-clean per-player convention - the source of the
  misleading "intl_bat weak cell". Deduped to one row per player; eFV's intl_bat AUC is within
  noise / wins on the ship metric (forward-chain IFA 0.7382 vs 0.7194). Disagreements: NO SHIP
  (irreducible variance - eFV right ~55% of biggest disagreements; the misses are relievers it
  fades that spike, a role-feature structural blocker; 3 bounded interventions all fail the OOS
  bar). OBS-2 (FSIDE cold-build sibling-staleness) noted, bounded/self-correcting. Artifacts
  data/xfv_bughunt2_eval.json + data/xfv_disagreements_eval.json.

## Round-2 conclusion
Two ships (Pipeline Top-30 daily refresh - a real data-freshness win for ~829 prospects; the
scoreboard intl_bat dedup - a measurement-honesty fix). Three rigorous ledgers (injury
coverage-starved; peak-WAR validates the grade but cumulative is Pareto-optimal; disagreements
irreducible). The peak-WAR measurement result is the headline: eFV tracks CEILING better than it
tracks accumulation, so the grade is a genuine talent scale. No eFV accuracy regression; the bug
hunt cleared the whole session's changes.
