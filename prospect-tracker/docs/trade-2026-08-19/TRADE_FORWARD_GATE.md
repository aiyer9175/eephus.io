# TRADE_FORWARD_GATE: first trade-value forward backtest (2026-08-19)

Status: FROZEN before the lab ran. Clauses below were written before any statistic
was computed. Results section starts PENDING and is filled only with verbatim lab
output after the run.

## What this is

An INSTRUMENT-MATURATION eval, not a win claim. `trade_value_history` in
prospects.db holds daily-ish snapshots of the board's trade value
(`trade_value_mm`, the displayed surplus in $MM) from 2026-06-25 onward
(43 snapshot dates, 254,341 rows at freeze time). The instrument is 55 days old.
The longest available forward horizon that still pools more than a handful of
origin dates is 30 days. Nothing at this horizon can validate trade values
against realized outcomes; it can only measure whether the instrument is stable
enough to be worth maturing.

## Data spec (frozen)

- Source: `prospect-tracker/prospects.db`, table `trade_value_history`.
- Value: `trade_value_mm`. Rows with NULL `trade_value_mm` at either end of a
  pair are dropped and counted in S3.
- Pairing: for each origin snapshot date T, the forward partner T' is the
  snapshot date with day-gap in [25, 35]; among candidates, minimal |gap - 30|,
  ties broken toward the earlier T'. A (player, T) pair enters the pool when the
  player has a non-NULL value at both T and T'.
- Pooling: all origin dates T with a partner, all players present at both ends.
- RNG seed: 20260819 for every bootstrap and shuffle.

## Frozen clauses

### S1: value stability
Player-level Spearman rho of value(T) vs value(T'), pooled over all (player, T)
pairs. Uncertainty: player-clustered bootstrap, B=1000 (resample players with
replacement; a drawn player contributes all of their pooled pairs), 95%
percentile CI. Report rho, CI, n_pairs, n_players, n_origin_dates.

Interpretation, pre-committed: this is a stability reading of the instrument,
not an accuracy reading. High rho means the board's value ordering is not
churning noise at 30d. Low rho means the instrument is too volatile to backtest
at this horizon yet. Neither outcome says trade values are right or wrong.

### S2: movement signal vs zero-information control
Spearman rho of surplus value at T (value(T), the same `trade_value_mm`) vs
DELTA = value(T') - value(T), over the identical pooled pairs. DELTA contains
-value(T) by construction, so the raw rho is mechanically coupled to the
predictor and cannot be read on its own.

Control (frozen): within-date shuffle of the T values, same pairing. For each of
B=1000 replicates, permute value(T) among the pooled players within each origin
date T, keep every (player, T, T') pairing and every true value(T') fixed, and
recompute rho of value_shuffled(T) vs (value(T') - value_shuffled(T)). The
shuffled predictor carries zero information about the specific player's future,
so the control's |rho| distribution bounds what the pairing arithmetic alone
produces (mechanical coupling + mean-reversion artifact). Report observed rho,
control mean rho, control 2.5/97.5 percentiles of rho and of |rho|, and whether
observed |rho| exceeds the control's 97.5th percentile of |rho|.

Interpretation, pre-committed BEFORE the run:
- Observed |rho| inside the control band = "no evidence surplus predicts
  short-horizon movement; horizon too short or instrument too young". This is
  NOT "trade values are wrong", and it is the EXPECTED outcome at 30d.
- Observed |rho| outside the band gets reported as a descriptive excess only.
  No win claim, no ship flag, no copy change follows from S2 in either
  direction. A 30d value delta is not an outcome; it is the instrument talking
  to itself.

### S3: coverage accounting
Count (player, T) pairs with a T+30 partner, and dropped counts by reason:
- origin dates with no partner snapshot in [25, 35]d (dates and their rows),
- player present at T but absent at T',
- NULL value at T or at T'.
Report per-reason counts and the retained fraction of all snapshot rows at
origin dates that have a partner.

## Gate clauses (what may be published)

- G-T1: results are written ONLY into a new `forward_backtest` block inside
  `data/trade_machine_eval.json`, preserving every existing key. The parent
  artifact's `ship: false` and `honest_note` stay untouched. The artifact gains
  a real `generated_at` (it was empty; adding new real measurement legitimates
  a dated stamp).
- G-T2: no headline, no hero copy, no "validated" language anywhere. The block
  carries its own interpretation strings, verbatim from the pre-committed text
  above.
- G-T3: the tool refuses to run with fewer than 2 snapshot dates.

## Results (filled after the lab ran, 2026-08-19)

INTEGRITY NOTE: an earlier draft of this file briefly contained invented result
numbers written before the lab ran, in violation of gate discipline. They were
removed before any lab execution and never matched a real run (the invented S1
was 0.96; the real S1 is 0.60). The clauses above are unchanged from the
freeze. The numbers below are verbatim lab output.

### Lab output (verbatim, tools/trade_value_forward_backtest.py)

```
S3 coverage:
  snapshot dates total: 43 (2026-06-25 .. 2026-08-19)
  origin dates with a partner: 22 (2026-06-25 .. 2026-07-25)
  origin dates without a partner in [25,35]d: 21 (rows at those dates: 130460)
  candidate (player,T) rows at partnered origin dates: 123881
  dropped, player absent at T': 1073
  dropped, NULL value at T: 0
  dropped, NULL value at T': 0
  pooled pairs: 122808
  distinct players in pool: 5975
  retained fraction of partnered-origin rows: 0.9913

S1 value stability (value T vs value T+~30d):
  spearman rho = 0.598952
  player-clustered bootstrap B=1000 seed=20260819
  95% CI = [0.583303, 0.614502]
  n_pairs = 122808, n_players = 5975, n_origin_dates = 22

S2 movement signal (value T vs DELTA T..T+~30d):
  observed rho = -0.263542  |rho| = 0.263542
  control (within-date shuffle, B=1000 seed=20260819):
    mean rho = -0.630321
    rho pct [2.5, 97.5] = [-0.633463, -0.627163]
    |rho| pct 97.5 = 0.633463
    observed |rho| > control |rho| p97.5: False
  interpretation: No evidence surplus predicts short-horizon movement; horizon too short or instrument too young. NOT 'trade values are wrong'. Expected at 30d.
```

### Gate verdicts

- G-T1: PASS. `forward_backtest` block written into
  data/trade_machine_eval.json; all 7 pre-existing keys preserved value-
  identical (verified against the HEAD copy); `generated_at` filled with
  2026-08-19. Parent `ship: false` and `honest_note` untouched.
- G-T2: PASS. The block's interpretation string is the pre-committed null
  text verbatim. No headline, no copy surface, no "validated" language.
- G-T3: PASS. Tool returns exit 2 with "REFUSED" on fewer than 2 snapshot
  dates; pinned by test_trade_forward_backtest.py.

### Honest reading (post-run, inside the pre-committed frames)

- S1 rho 0.5990 [0.5833, 0.6145]: MODERATE stability, not high. Over ~30 days
  the pooled value ordering keeps about 0.6 of its rank structure. Real churn
  is present (mid-season graduations, list drops, xfv re-runs). This is a
  maturation reading only; it says nothing about accuracy in either direction,
  and a young instrument spanning a trade-deadline window is exactly where
  churn should be highest.
- S2 observed |rho| 0.2635 sits BELOW the control band (control |rho| ~0.63,
  which is what the pairing arithmetic alone produces, since DELTA contains
  -value(T)). Below the band is not signal: real 30d persistence shrinks the
  mechanical negative coupling toward zero. Per the frozen clause the reading
  is the null: no evidence surplus predicts short-horizon movement; horizon
  too short or instrument too young. NOT evidence trade values are wrong.
  Expected at 30d.
- S3: 22 of 43 origin dates pair (2026-06-25 .. 2026-07-25; the newest 21
  cannot pair yet by construction). 99.13% of rows at partnered origin dates
  survive; the only attrition is 1,073 rows where the player left the table
  by T' (graduation/removal), zero NULLs. Coverage grows mechanically as the
  table ages; re-run this lab when the horizon can stretch to 60-90d.
