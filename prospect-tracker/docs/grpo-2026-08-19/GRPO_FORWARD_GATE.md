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

PENDING. First admissible look 2026-09-18 (section 3). Do not fill before a
matured cohort exists; fill with verbatim lab output only.
