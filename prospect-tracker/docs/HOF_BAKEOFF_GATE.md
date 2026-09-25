# HOF-BAKEOFF: the public benchmark bake-off

Frozen 2026-09-06, before the battery was run. The frame rules, the fold rules, the
comparator families, the leak guards and the stop rule below were fixed first. The Results
section was empty when they were written.

## G-0 HONESTY CLAUSE, and it comes first

**The discrimination leg is NOT pre-registered.** A design pass read raw AUC figures on this
frame on 2026-09-06 while scoping the lane, so the numbers exist before this document does.
They are recorded below as PRIORS and the run either reproduces them or it does not. Calling
them pre-registered would be false.

**The calibration leg IS unread.** No Platt fit has been run, no Brier, no log loss and no
calibration error. Its clauses in G-4 are pre-registration in the ordinary sense.

## What this lane is for

Every later Hall of Fame model needs a bar, and the bar has to come from the public work
rather than from nothing. This scores Baseball-Reference's own HoF Monitor and HoF Standards
against our WAR shelf on the same rows, twice: raw, and calibrated per fold.

The honest expectation is that we lose. HoF Monitor is built from batting titles, MVP
shares, All-Star selections and postseason play, and none of that is in our feature set.

## G-1 FRAME, frozen

**The unit is the player, forever.** The shelf ships 4,278 ballot-APPEARANCE rows over 1,322
players. The five metric values are constant per player, measured: **0 of 1,322 vary**, so
collapsing is lossless. Reading the file without collapsing gives a replicated frame that
looks entirely reasonable and moves every AUC, by more than the whole arm spread.

**Only resolved rows enter.** Selected with `.notna()` and then `== 1.0`, never by
truthiness: the label columns are float64, a censored row carries NaN, and `bool(nan)` is
True. A censored player scored as a zero is refused, and the refusal is enforced rather
than documented.

**Common support is the complete-case intersection over every arm**, computed once before
any statistic is read. Public columns are NEVER imputed. A zero HoF Monitor for Roberto
Clemente guarantees a misranking, and a NaN is worse: numpy sorts NaN last, so a positive
with a missing score would be awarded the top rank.

**The drop is published with its positive and negative split and its names, and a drop
concentrated in one induction route or era REFUSES the pooled comparison** regardless of any
percentage threshold. Measured on the repaired ledger before freezing:

| label | resolved | with a shelf row | dropped | dropped positives | dropped negatives |
|---|---|---|---|---|---|
| label_bbwaa | 1,219 | 1,219 | 0 | 0 | 0 |
| label_any | 935 | 918 | 17 | 17 | 0 |

The seventeen are Roberto Clemente, Monte Irvin, Buck Leonard, Judy Johnson, Biz Mackey,
Mule Suttles, Jud Wilson, Ben Taylor, Andy Cooper, Willard Brown, Cristobal Torriente, Jim
O'Rourke, Clark Griffith, Miller Huggins, Bill McKechnie, Ned Hanlon and Dick Williams:
Negro Leagues honourees and manager inductions who never appeared on a Baseball-Reference
election page, so the scrape never produced a row for them. **The hole is perfectly
correlated with the outcome**: 17 of the label's 286 positives, and none of its 649
negatives. A 90 percent positive-share threshold would not fire on that, which is exactly
the case such a threshold would exist for. That is why the rule is route concentration and
not a percentage.

## G-2 FOLDS, frozen

Forward-chained on `hof_data.resolution_year`, expanding window, five-year test blocks.
Fold k tests resolution years in `[burn + 1 + 5(k-1), burn + 5 + 5(k-1)]` and trains on
every row resolving strictly before that block. A player occupies exactly one row in exactly
one fold. Burn-in requires at least 150 rows and at least 25 of each class.

**The discrimination leg fits nothing.** AUC on pooled test predictions of raw scores is
identical to AUC on those rows' raw scores, so the fold structure changes it not at all. The
folds exist for the calibration leg only, and the published discrimination bar is on the
FULL resolved common-support frame, which is fold-free, with the test-pool figure beside it
and labelled as the calibration-leg population.

## G-3 DISCRIMINATION, transcribed at freeze

AUC by Mann-Whitney over average ranks with ties at one half, through
`source_backtest._auc_np`, with the concordant, discordant and tied decomposition and the
distinct-value count per arm published beside it.

**The Holm family is EIGHT distinct metrics, not eleven.** `JAWS` and `jaws`, `WAR_career`
and `career_war`, `WAR_peak7` and `war7` are the scraped and in-house versions of the same
three quantities. Counting them separately would overstate the family, make Holm needlessly
conservative on the comparisons that matter, and pollute the argmax candidate set. The three
pairs are published separately as a reproduction check, which extends the fifteen hand-checked
cells to over a thousand players.

Two comparator families, both published, only one carrying the ranking claim:

- **(a) against the pre-designated reference, JAWS.** Kept for the pre-designation
  discipline, not because it is expected to win.
- **(b) against the resampled public argmax.** This is the family that adjudicates, and it
  is labelled as such. Every delta carries its own paired E_cond floor derived in run, and
  **no floor measured on one comparator pair may be quoted over another pair's delta.**

### Arms refused, and why

- `JAWS_pos` is LABEL-DERIVED: it is the mean JAWS of the Hall of Famers at that position as
  of the scrape, so it is computed from the outcome and includes players in our own test
  folds. It ships as a string, which makes it look like a harmless identifier, and JAWS
  minus JAWS_pos is the most natural-looking normalization available. Admissible as a
  position identifier, never as a score and never as a normalizer.
- `bref_hof_marker_as_of_scrape` is a PERFECT LEAK and not what its name suggests: it is a
  flag on losing rows only. Never joined, featured or cross-checked on.
- Black Ink, Gray Ink, Hall Rating, wWAR and the Keltner rubric DO NOT EXIST in this repo.
  Our `ink` is an in-house metric ranking one thing, WAR, and is never presented as Black
  Ink.

### The priors read during design, recorded so the run cannot quietly beat them

Public rules are expected to sit near AUC 0.96 on this frame and `hof_monitor` is expected
to be the best public column on both labels. The in-house ordering is expected to be
`jaws < waa_pos < career_war`, and **that ordering is expected NOT to resolve**: the gaps
are smaller than their own floors.

## G-4 CALIBRATION, PRE-REGISTERED AND UNREAD

Per fold, per arm, Platt on the raw score, standardized on training rows only. The fit is an
L2-penalised Newton-IRLS, not a bare Hessian ridge: a ridge on the Hessian alone makes it
invertible and does NOT bound the coefficients, and under separation the MLE is at infinity.
With eight arms, small training sets and low-cardinality arms, quasi-separation is live.
Step halving on any iteration that increases deviance, and a hard logit clip.

**Only PAIRED deltas between arms are gated**, because both arms share folds and rows and
the fold mixture largely cancels. Per-arm LEVELS are published behind an explicit key saying
they are a fold mixture and not an arm calibration.

Primary Brier, secondary log loss, tertiary calibration error on ten quantile bins with
equal-width beside it as a sensitivity. Every published delta carries an in-run
player-clustered floor. **A delta below its floor is reported NOT RESOLVABLE, never as a win
and never as "directionally favours".**

Every calibration floor here is E_cond and the calibration claim is therefore the
conditional one: this lane refits a Platt map per fold, and a lane that refits needs E_refit
to speak unconditionally. That is stated in every calibration verdict rather than left to a
reader to notice.

## G-5 LEAK, frozen, five guards

1. The standardizer is fitted on training rows only.
2. The fit is stamped with its training horizon and application asserts against it.
3. **PER-FOLD** post-Platt AUC identical to per-fold raw AUC. The POOLED version of this
   check is deliberately DELETED: a mixture of K monotone maps is not one monotone map, so a
   correct implementation fails it and a builder would hunt a leak that is not there. The
   pooled raw-versus-calibrated shift is published per arm as a measured quantity instead.
4. A label-shuffle mutation: permuting test-fold labels must leave every training
   coefficient bit-identical. This is the only guard that catches a leak through a shared
   mutable frame.
5. Every training row's last season must fall before its fold's cut year, or the violation
   count is published per fold. The features are career-final, and the structural rescue
   that makes that safe is keyed to as-of 2026, not to the fold cut, so a training row can
   carry WAR earned after its own cut. This cannot move the raw AUC leg, but it contaminates
   the Platt fits.

## G-6 THE BAR FOR A MERIT MODEL, as a frame contract and not a number

Any later merit model must re-score every public arm on its OWN test rows and beat the
resampled argmax there, under Holm, on both labels. The bar is published on the full
resolved common-support frame with its argmax stability. If argmax stability falls below
0.90 on either label the bar is published as an interval over the contending rules. The
winner's-curse floor is DERIVED in run and published with its sign; it is not transcribed
here, because that floor can legitimately come back negative.

## G-7 STOP RULE

If no arm separates from its comparator above its floor, the lane ships as a coverage
receipt and states that the public rules are not distinguishable at this n. If the
calibration deltas are all below their floors, the lane publishes discrimination only and
does not report the sign of an unresolvable delta. If the per-fold AUC invariance check
fails, nothing ships.

## G-8 LABEL CONTAMINATION, fixed in the frame rather than carried as an arm

The dropped-off route is honoured only for elections from 1979, and only where the flag sits
on the player's LAST appearance. Both corrections live in `hof_data.resolution_year` and are
fixed in the frame before this gate is frozen, because carrying them as sensitivity arms
while the base run used a corrupt fold key would hand every later model a bar measured on a
chain with a decades-long look-ahead.

The ledger repair is likewise fixed upstream. Its pre-repair numbers are recorded as priors
so the repair cannot later be sold as a modelling improvement, and all six label_bbwaa cells
are asserted byte-identical across it: movement there is a bug, not a result.

### G-8 addendum, 2026-09-24: a second ledger repair, recorded under this clause

Four Negro Leagues inductees, Josh Gibson (1972), Oscar Charleston (1976), Cool Papa Bell
(1974) and Ray Brown (2006), were unresolved: StatsAPI names them by MLBAM ids the war_daily
parquets never carry. `hof_data.NEGRO_LEAGUES_ID_BRIDGE` now bridges them, keyed on the
MLBAM id and matched on birth date against the Chadwick register, never on a name. The
clauses above are unchanged; only the ledger the frame reads moved. Pre-repair numbers,
kept as priors:

| quantity | before | after |
|---|---|---|
| inductees in the eligible universe (label_any positives) | 286 | 290 |
| label_any negatives / censored | 649 / 2,685 | 649 / 2,681 |
| label_any resolved rows read by the bake-off | 935 | 939 |
| label_any shelf hole (dropped, all positive) | 17 | 21 |
| plaque role unverified inside the eligible universe | 147 | 151 |
| label_bbwaa cells (all six) | byte-identical | byte-identical |

None of the four has a public shelf row, so all four join the label_any hole and the
scored label_any frame (918 rows) is identical row for row. No AUC, floor or calibration
cell moves on either label. The G-1 table and the G-9 base rate above are the frozen
pre-repair figures and are left as written; read them with this table.

## G-9 POPULATION DISCLOSURE, frozen

**This frame is not the eligible universe.** It is almost exactly the set of players a
screening committee already put on a Baseball-Reference ballot page.

- Eligible universe 3,620, base rate 286 of 3,620, 7.9 percent on the repaired label.
- Scored label_bbwaa 1,219 rows, base rate 11.4 percent.
- Scored label_any 918 rows, base rate 29.3 percent.

**An AUC here is discrimination among candidates the screening committee already advanced**,
and that sentence travels with every number this lane publishes.

**label_bbwaa is the primary and only headline label.** `label_any`'s censoring is
outcome-dependent: induction resolves a one immediately while non-induction requires the
window close plus the committee horizon, so recent strata contribute positives and no
negatives. It is a disclosed sensitivity, and its shelf hole is seventeen positives and zero
negatives, which is a second and independent reason not to headline it.

## G-10 MULTIPLICITY

Holm through `tools/efv_power_lab.holm_family`, with k equal to the distinct-metric family
size per comparator family per label, asserted in a test rather than written as a literal.

## Pre-registered expectations

1. **The public rules win.** `hof_monitor` is the best column on both labels and no in-house
   column clears it after Holm. Wrong if any in-house delta exceeds its own floor and
   survives Holm.
2. **Most of the JAWS reference family does not resolve.**
3. **The calibration deltas are NOT resolvable.** After per-fold Platt every arm is
   calibrated by construction on its training distribution, and a ten-bin calibration error
   on a few hundred rows with a hundred-odd positives has a bootstrap spread large relative
   to the surviving gaps. Wrong if more than half the calibration cells clear their floors
   under Holm.
4. **The in-house ordering `jaws < waa_pos < career_war` is measurable but not resolvable.**
5. **The honest expected outcome for a later merit model is a tie on discrimination**, and
   this document exists to make that a statement about a measured bar rather than a guess.

## Results, 2026-09-06

Run at B=2000, seed 20260906, on the repaired induction ledger.

### The bar, label_bbwaa (primary), n = 1219, 139 positives, base rate 11.4 percent

| arm | AUC | tied pair share | distinct values |
|---|---|---|---|
| `hof_monitor` | 0.9697 | 0.0009 | 221 |
| `WAR_career` | 0.9442 | 0.0004 | 615 |
| `career_war` | 0.9442 | 0.0000 | 1143 |
| `hof_standard` | 0.9429 | 0.0056 | 80 |
| `waa_pos` | 0.9426 | 0.0000 | 1176 |
| `JAWS` | 0.9416 | 0.0006 | 536 |
| `jaws` | 0.9415 | 0.0000 | 1169 |
| `career_waa` | 0.9361 | 0.0000 | 1194 |
| `war7` | 0.9252 | 0.0001 | 1082 |
| `WAR_peak7` | 0.9252 | 0.0010 | 455 |
| `ink` | 0.8907 | 0.0619 | 30 |

**PREDICTION 1 HELD. `hof_monitor` is the best column and no in-house column clears it.** Against the resampled public argmax, EVERY in-house arm loses above its own floor and survives Holm:

| arm | delta vs hof_monitor | in-run MDE95 | verdict |
|---|---|---|---|
| `hof_standard` | -0.02674 | 0.01446 | the comparator separates (E_cond, MDE95 0.01446) |
| `career_war` | -0.02546 | 0.01423 | the comparator separates (E_cond, MDE95 0.01423) |
| `war7` | -0.04443 | 0.01783 | the comparator separates (E_cond, MDE95 0.01783) |
| `jaws` | -0.02818 | 0.01513 | the comparator separates (E_cond, MDE95 0.01513) |
| `career_waa` | -0.03361 | 0.01373 | the comparator separates (E_cond, MDE95 0.01373) |
| `waa_pos` | -0.02710 | 0.01321 | the comparator separates (E_cond, MDE95 0.01321) |
| `ink` | -0.07897 | 0.02451 | the comparator separates (E_cond, MDE95 0.02451) |

**PREDICTION 2 HELD.** Against the pre-designated JAWS reference, five of eight cells do not resolve; only `hof_monitor`, `war7` and `ink` separate.

**PREDICTION 4 HELD.** The in-house ordering is measurable and mostly not resolvable: `career_war` beats `jaws` by +0.00265 against a floor of 0.00319, and `waa_pos` beats `jaws` by +0.00101 against 0.00546. Neither clears.

### Calibration, label_bbwaa

`hof_monitor` carries the lowest pooled Brier, so it is the comparator here too. **13 of 30 cells clear Holm.**

- `brier`: 4 of 10 reject (`WAR_peak7`, `war7`, `career_waa`, `ink`)
- `log_loss`: 9 of 10 reject (`WAR_career`, `WAR_peak7`, `JAWS`, `career_war`, `war7`, `jaws`, `career_waa`, `waa_pos`, `ink`)
- `ece_quantile10`: 0 of 10 reject, none

**PREDICTION 3 HELD ON THE PRIMARY LABEL AND FAILED ON THE SENSITIVITY.** The clause was "wrong if more than half the calibration cells clear their floors under Holm". On label_bbwaa it is 13 of 30, under half. On label_any it is 18 of 30, over half. The calibration-error leg resolves NOTHING on either label, which is the half of the prediction that was exactly right; Brier and log loss resolve, and every resolved cell points the same way, at `hof_monitor`.

### The guards

- Per-fold post-Platt AUC identical to per-fold raw AUC: max absolute difference **0.0** over 165 checks. Exactly zero, which is what a correct implementation gives.

- The POOLED shift, which the deleted clause would have asserted was zero, runs -0.0181 to -0.0015. A mixture of fold-specific monotone maps is not one monotone map, and a builder chasing that as a leak would have been chasing arithmetic.

- Training rows carrying a season at or after their own fold cut: **2**. Published rather than assumed away; it cannot move the raw AUC leg.

### label_any is a disclosed sensitivity and its pooled comparison is REFUSED

935 resolved rows, 918 with a shelf row, **17 dropped and every one a positive**. The hole is perfectly correlated with the outcome, so the route-concentration rule fires and the pooled comparison on this label is refused. A ninety percent positive-share threshold would not have fired on 17 of 935, which is exactly the case it would have existed for.

The seventeen are Andy Cooper, Ben Taylor, Bill McKechnie, Biz Mackey, Buck Leonard, Clark Griffith, Cristóbal Torriente, Dick Williams, Jim O'Rourke, Jud Wilson, Judy Johnson, Miller Huggins, Monte Irvin, Mule Suttles, Ned Hanlon, Roberto Clemente, Willard Brown.

### The reproduction check

The scraped and in-house versions of the same three quantities, on 1219 players, which extends the fifteen hand-checked cells by two orders of magnitude:

| pair | exact to a tenth | mean absolute difference | largest |
|---|---|---|---|
| `JAWS_vs_jaws` | 1095 of 1219 | 0.0525 | 10.01 |
| `WAR_career_vs_career_war` | 1125 of 1219 | 0.0695 | 20.32 |
| `WAR_peak7_vs_war7` | 1127 of 1219 | 0.0350 | 5.86 |

The large residuals are the Negro Leagues and pre-1901 population, where the two sources count different seasons. That is the same population the leaderboard's own reproduction note names.

### What this bar means for a merit model

A later model must beat `hof_monitor` at **AUC 0.9697** on label_bbwaa, on its own test rows, under Holm. `hof_monitor` is built from batting titles, MVP shares, All-Star selections and postseason play, and NONE of that is in our feature set. The honest expected outcome is a loss on discrimination and a statement about the missing awards data, not a modelling failure.
