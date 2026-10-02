# GRPO forward gate (registered 2026-08-19)

Registration of the FIRST forward eval of the GRPO breakout badge (W2.1 of
docs/master-plan-2026-08-19-holistic-audit.md). Clauses below are FROZEN as of
this date, before any matured cohort exists. No result may be filled in until
the first admissible look date; anything filled earlier is a protocol
violation, not a result.

## 0. Scope

- Model: grpo_prospect.py (HistGradientBoostingRegressor policy, monthly
  retrain keyed by a training fingerprint). Registry row: grpo_prospect.
- Claim under test: THE BADGE ORDERING ONLY. The breakout badge surfaces
  players with high within-group breakout_score; the claim is that this
  ordering predicts forward consensus FV movement.
- OUT OF SCOPE: the FV-pricing path. bayes_trade_value.py sets
  grpo_fv_adj = 0.0 deliberately (C3, 2026-08-03) and the score ships
  display-only. That zero STAYS ZEROED regardless of any outcome here.
  Nothing in this gate can arm pricing; un-zeroing C3 is a separate owner
  decision with its own gate.
- GRPO never enters eFV features, so the closed eFV driver frontier
  (2026-08-14b) is not implicated.

## 1. Why the eval could never be built before today

data/grpo_scores.json is overwritten in place by every retrain. No prior
vintage of any score survived, so no forward window could ever be anchored.
Fixed 2026-08-19: run_monthly rebuild_only now appends every scored player to
the prospects.db table grpo_score_history (snapshot_date, player_key, score),
INSERT OR IGNORE on the composite key, reading the just-written artifact and
never recomputing. History begins 2026-08-19 and cannot be back-filled.

## 2. Frozen design (the editorial_eval template)

This is the design that already passed for the editorial flags eval
(data/editorial_eval.json: per-date flag cohorts, 30/60-day maturation on
consensus FV movement with hit rule fv_delta +5.0 direction +1, hit-rate CIs
vs a control cohort, clears_control verdict per horizon, kill rule after
enough matured cohorts). This gate reuses it with a 90-day window added.

### 2.1 Cohorts

- A cohort is one snapshot_date in grpo_score_history: all players archived
  on that date.
- The archive accrues on every nightly rebuild, so consecutive daily cohorts
  are pseudo-replicated (scores only change on retrain). PRIMARY READ:
  monthly-spaced cohorts, defined as the FIRST snapshot_date of each calendar
  month present in the table. Daily cohorts are sensitivity only and carry no
  verdict weight.

### 2.2 Flag definition

- Within each cohort, the flagged set is the TOP DECILE by archived score
  (ties at the decile boundary all included). This proxies the served badge
  while staying threshold-stable across retrains; the served badge chip
  threshold (0.55) is reported as a sensitivity cut, not the primary flag.

### 2.3 Hit rule (identical to editorial_eval riser)

- Hit = the player's consensus FV rises by >= +5.0 (one FV bucket) between
  the cohort date and maturation, measured from metric_snapshots (the same
  server-side board history editorial_eval reads). Players with no matured
  board row are excluded from numerator and denominator, never counted as
  misses.

### 2.4 Maturation windows

- 30, 60, and 90 days after the cohort date. A cohort is matured for window W
  when a board snapshot exists on or after cohort_date + W days.

### 2.5 Controls (both required)

- CONTROL A, zero information: within each cohort, shuffle the archived
  scores across the cohort's players (1,000 permutations), re-select the top
  decile, apply the same hit rule. Control rate = permutation mean; its CI =
  the 2.5/97.5 permutation percentiles.
- CONTROL B, FV-only: within each cohort, rank by consensus FV at the cohort
  date (ties by consensus board rank), take the top decile, same hit rule.
  This asks whether the badge adds anything beyond a sorted FV column.

### 2.6 Gate clauses (frozen verdict logic)

- G-1: the badge clears CONTROL A when the badge hit-rate 95% Wilson CI and
  the permutation CI do not overlap, badge above, on a given window.
- G-2: the badge clears CONTROL B when the badge hit-rate 95% Wilson CI and
  the FV-only 95% Wilson CI do not overlap, badge above, on a given window.
- VERDICT LADDER: G-1 and G-2 both cleared on any window = badge validated
  for that window. G-1 cleared but G-2 not = the badge repackages consensus
  FV; the registry note must say exactly that and the badge copy may not
  claim model signal. G-1 not cleared = zero information; see kill rule.
- KILL RULE: after 6 matured monthly cohorts on the 30-day window, if G-1
  still fails, the verdict recommendation is de-list the badge or re-label
  it descriptive (mirrors the editorial_eval kill-rule shape).
- Eval artifact: the future lab writes data/grpo_forward_eval.json and the
  integrator adds it to the grpo_prospect registry row at that time.

## 3. First admissible look (date arithmetic)

Archive start = 2026-08-19 (today's snapshot, section 5). The 2026-08-19
cohort is the first cohort. Earliest admissible look per window:

- 30-day: 2026-08-19 + 30d = 2026-09-18. First look = first run on or after
  2026-09-18 with a board snapshot on or after that date.
- 60-day: 2026-08-19 + 60d = 2026-10-18.
- 90-day: 2026-08-19 + 90d = 2026-11-17.

Single-cohort reads are admissible but weak (n of one cohort); the kill rule
needs 6 matured monthly cohorts, i.e. no kill verdict before roughly
2027-02-18 (cohorts of 2026-08-19 through 2027-01, each + 30d).

## 4. Retrospective feasibility: investigated, answer NO

Question: can a leak-free retrospective eval run today instead of waiting?
Answer: NO. Three independent blockers, each sufficient, from a read of
grpo_prospect.py on 2026-08-19:

1. LABEL LEAK, unfixable from the artifacts. build_training_dataset labels
   each graduate via _outcome_label from career_war.war_per_yr and
   war_seasons_count as they stand TODAY in debuts.json. These are cumulative
   career aggregates with no per-season ledger in the artifact, so a label
   "as of date D" cannot be reconstructed by truncation. Any model scored on
   an as-of-D cohort would have trained on careers partly realized after D.
2. FEATURE LEAK, no as-of feature source. extract_features reads the CURRENT
   timeseries.json row: current_level, age, fv_close, statline rates,
   zone_metrics, statcast contact quality including max_ev. No served
   artifact preserves those fields as of a past date. metric_snapshots holds
   consensus rank/FV and the Arkmetric family only, not the statcast/zone/
   level features the policy consumes.
3. NO SCORE VINTAGES. grpo_scores.json is overwritten; before today there is
   no record of what the model output on any past date, so even a
   "score-frozen" retrospective has nothing to read.

Conclusion: the forward archive is the only admissible path. That is what
section 1 ships.

## 5. Archive initialization (lab result, verbatim)

COMPLETE 2026-08-19. One snapshot taken by calling snapshot_grpo_scores()
directly from prospect-tracker/ after the wiring landed, then a same-day
re-run to prove idempotency live. Verbatim lab output:

```
INFO:grpo_prospect:grpo history: 4690 of 4690 scores archived for 2026-08-19 (dupes ignored)
inserted=4690
recount: [('2026-08-19', 4690)]
INFO:grpo_prospect:grpo history: 0 of 4690 scores archived for 2026-08-19 (dupes ignored)
rerun same-day inserted=0
recount after rerun: [('2026-08-19', 4690)]
artifact generated_at=2026-08-19 scored_count=4690
```

4,690 rows = the artifact's full scored_count; the same-day re-run inserted
0. The 2026-08-19 cohort exists and the section 3 dates are live.

## 6. Eval results

### 30-day look, run 2026-10-02 at HEAD 53d68e25 (python -u tools/grpo_forward_lab.py)

```
GRPO forward read (docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md, section 2 frozen 2026-08-19)
run date 2026-10-02, HEAD 53d68e25, seed 20260819, permutations 1000
archive: 145298 rows, 31 snapshot dates (2026-08-19 to 2026-10-02), null scores 0
board: 90 metric_snapshots nights, latest 2026-10-02
monthly cohorts (primary): 2026-08-19, 2026-09-03, 2026-10-01
hit rule: consensus FV +5.0 or more, base night on the cohort date or up to 3 days before, end night first on or after cohort + W

PRIMARY (monthly cohorts, top decile), 30-day window:
  cohort 2026-08-19: base 2026-08-19, end 2026-09-18, archived 4690, null scores 0, flagged 470 (scoreable 463, hits 0), Control B 468 (scoreable 451, hits 0)
  cohort 2026-09-03: not matured
  cohort 2026-10-01: not matured
  cohorts matured: 1; flagged n: 470
  badge hit rate:     0.0000 [0.0000, 0.0082] (0/463)
  Control A (shuffle): 0.0000 [0.0000, 0.0000] (1000 permutations)
  Control B (FV only): 0.0000 [0.0000, 0.0084] (0/451)
  G-1 vs Control A: not cleared; G-2 vs Control B: not cleared
  ladder: zero information
SENSITIVITY chip cut (monthly cohorts, score >= 0.55) (sensitivity, no verdict weight), 30-day window:
  cohort 2026-08-19: base 2026-08-19, end 2026-09-18, archived 4690, null scores 0, flagged 1892 (scoreable 1875, hits 0), Control B 468 (scoreable 451, hits 0)
  cohort 2026-09-03: not matured
  cohort 2026-10-01: not matured
  cohorts matured: 1; flagged n: 1892
  badge hit rate:     0.0000 [0.0000, 0.0020] (0/1875)
  Control A (shuffle): 0.0000 [0.0000, 0.0000] (1000 permutations)
  Control B (FV only): 0.0000 [0.0000, 0.0084] (0/451)
  G-1 vs Control A: not cleared; G-2 vs Control B: not cleared
  ladder: zero information (sensitivity only)
SENSITIVITY daily cohorts (top decile) (sensitivity, no verdict weight), 30-day window:
  cohort 2026-08-19: base 2026-08-19, end 2026-09-18, archived 4690, null scores 0, flagged 470 (scoreable 463, hits 0), Control B 468 (scoreable 451, hits 0)
  cohort 2026-08-20: base 2026-08-20, end 2026-09-19, archived 4692, null scores 0, flagged 472 (scoreable 469, hits 0), Control B 468 (scoreable 453, hits 0)
  cohort 2026-08-21: base 2026-08-21, end 2026-09-21, archived 4695, null scores 0, flagged 472 (scoreable 466, hits 0), Control B 468 (scoreable 453, hits 0)
  cohort 2026-08-23: base 2026-08-23, end 2026-09-23, archived 4695, null scores 0, flagged 471 (scoreable 467, hits 0), Control B 468 (scoreable 453, hits 0)
  cohort 2026-08-24: base 2026-08-24, end 2026-09-23, archived 4695, null scores 0, flagged 478 (scoreable 473, hits 0), Control B 469 (scoreable 454, hits 0)
  cohort 2026-08-27: base 2026-08-27, end 2026-09-26, archived 4693, null scores 0, flagged 471 (scoreable 465, hits 0), Control B 468 (scoreable 454, hits 0)
  cohort 2026-08-30: base 2026-08-30, end 2026-09-30, archived 4688, null scores 0, flagged 472 (scoreable 468, hits 0), Control B 468 (scoreable 456, hits 0)
  cohort 2026-08-31: base 2026-08-31, end 2026-09-30, archived 4693, null scores 0, flagged 475 (scoreable 472, hits 0), Control B 468 (scoreable 456, hits 0)
  cohort 2026-09-03: not matured
  cohort 2026-09-04: not matured
  cohort 2026-09-05: not matured
  cohort 2026-09-06: not matured
  cohort 2026-09-07: not matured
  cohort 2026-09-09: not matured
  cohort 2026-09-10: not matured
  cohort 2026-09-11: not matured
  cohort 2026-09-13: not matured
  cohort 2026-09-14: not matured
  cohort 2026-09-16: not matured
  cohort 2026-09-17: not matured
  cohort 2026-09-18: not matured
  cohort 2026-09-19: not matured
  cohort 2026-09-21: not matured
  cohort 2026-09-23: not matured
  cohort 2026-09-24: not matured
  cohort 2026-09-25: not matured
  cohort 2026-09-26: not matured
  cohort 2026-09-27: not matured
  cohort 2026-09-30: not matured
  cohort 2026-10-01: not matured
  cohort 2026-10-02: not matured
  cohorts matured: 8; flagged n: 3781
  badge hit rate:     0.0000 [0.0000, 0.0010] (0/3743)
  Control A (shuffle): 0.0000 [0.0000, 0.0000] (1000 permutations)
  Control B (FV only): 0.0000 [0.0000, 0.0011] (0/3630)
  G-1 vs Control A: not cleared; G-2 vs Control B: not cleared
  ladder: zero information (sensitivity only)

PRIMARY (monthly cohorts, top decile), 60-day window:
  cohort 2026-08-19: not matured
  cohort 2026-09-03: not matured
  cohort 2026-10-01: not matured
  window: not matured, no verdict

PRIMARY (monthly cohorts, top decile), 90-day window:
  cohort 2026-08-19: not matured
  cohort 2026-09-03: not matured
  cohort 2026-10-01: not matured
  window: not matured, no verdict

kill rule: not yet evaluable (1 of 6 matured monthly cohorts on the 30-day window)
pricing: grpo_fv_adj stays 0.0 (gate section 0); this read moves no served number
wrote grpo_forward_eval.json: windows recorded 30-day
```
