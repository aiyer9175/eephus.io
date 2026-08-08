# Lane D (wave 2): does the bust label reach the served hitter model through a shipped feature, and is the as-of anchor itself outcome-selected?

Producer: `python tools/efv_feature_leak_lab.py all`
Ledger: `data/xfv_feature_leak_eval.json`
Read-only on `efv_model.py` and `efv_dataset.py`. Any edit this lane wants is reported, not applied.

## 0. Pre-registration

**Written before any line of `tools/efv_feature_leak_lab.py` existed and before any
accuracy number was computed.** Sections 1 through 4 below are the registered criteria.
Section 5 is a placeholder and is the ONLY section that may be appended to after the run.

### 0.1 What was inspected BEFORE this document was written

Full disclosure, because wave 1's pre-registration claims were the thing that did not
survive verification. Before writing this file I ran, in a throwaway shell, only:

1. `import efv_model` and printed `_FEATURES_HIT` / `_FEATURES_PIT` (the membership facts
   the brief asked me to confirm myself).
2. The wave-1 descriptive reproduction: `P(bust | stale)` and the `n_milb_seasons`
   debuted-vs-bust means on both matrices. Reproduced exactly.
3. Row-schema and cost probes: matrix keys, `cutoff` and `asof_date` month histograms by
   kind, the `debut_year - asof_year` histogram, per-chain wall time, and a parity check
   that `tools/efv_cohort_floor_lab.chain` reproduces the shipped artifact rho.

No blend rho was computed under ANY feature edit or ANY alternative anchor before this
document was complete. The criteria below were not fitted to a result.

### 0.2 Membership facts, confirmed by import, not by grep

`_FEATURES_HIT` = fv, obp_rel, k_rel, peak_k_rel, age_rel_level, **n_milb_seasons**,
tool_hit, tool_speed, **milb_missing**, is_ifa, is_college, ops_rel, age, level_rank.

`_FEATURES_PIT` = fv, peak_k_rel, k_rel, bb_rel, age_rel_level, x_era_k, tool_fb, age,
**seasons_at_level**.

- `stale` is in NEITHER set. Confirmed by set membership on the imported lists.
- `milb_season` and `decision_year` are in neither set.
- `n_milb_seasons` and `milb_missing` are HIT-ONLY. They are NOT pitcher features. The
  brief's "on BOTH sides" cannot be executed literally for them. The pitcher side is run
  on `seasons_at_level`, the pitcher feature that takes the SAME one-season truncation,
  and it is labelled EXPLORATORY, not a replication.

### 0.3 Which fit is at risk

`efv_model.fit_production_stack` (the ONE production fit, shared by
`efv_score._fit_production` and `rank_calibration`) trains on
`[r for r in rows if not (kind == "bust" and bust_recent)]`, the FULL POOL. So the
debuted/bust group separation is present in the SERVED fit.

`_run_eval("debuted_km")`, the published headline rho, trains and tests inside the
debuted pool only. It contains no bust rows, so a group-separation leak is INVISIBLE to
it by construction. `full_pool_km` is the cut that mirrors the served frame.

Consequence, registered in advance: the primary frame for every group-separation
instrument is `full_pool`. On `debuted` the within-kind permutation is degenerate (one
kind) and is identical to the across-all permutation by construction; it is reported as
a structural identity, not as an independent result.

## 1. Estimator, floor, and the threshold this lane adds

### 1.1 Estimator

Forward-chained over `efv_model.SCORED_YEARS` (11 folds, 2014-2024), pair-weighted
Spearman, primitives imported from `tools/efv_mde_lab.py` and pools from
`tools/efv_cohort_floor_lab.load_pool`. Not reimplemented. Parity with the shipped
artifact is asserted in code (`repro` mode) and printed.

The reported quantity for every arm is the **blend rho** and its change against the
shipped arm. The consensus leg depends only on `fv` and is byte-identical across feature
arms within a draw, so the change in blend rho equals the change in the
model-minus-consensus margin. Both are reported so no reader has to take that on trust.

### 1.2 The floor, and the threshold I am adding

**DISCLOSED SELF-ADDED THRESHOLD (standing rule B).** The repo's existing drop gates
(pitcher `age` 2026-07-30, hitter `age` 2026-08-04) scored a dropped feature against
`MDE95_POOLED_RHO`, the model-VERSUS-CONSENSUS floor (0.044 hit / 0.0436 pit weighted,
`data/xfv_mde_floor.json`). That floor is measured on a contrast between two DIFFERENT
predictors. It is the wrong floor for a contrast between two fits of the SAME model that
differ in one column, because those two arms share nearly all of their sampling
variability, and the paired contrast's own sd is much smaller.

This lane therefore uses, as its primary bar, **the paired-bootstrap MDE95 of each
contrast itself**: resample the whole pool once per draw, refit BOTH arms on the same
draw, take the difference of blend rhos, and set MDE95 = 1.96 \* sd(difference),
two-sided (a feature edit may help or hurt).

Standing rule F applies and is why this substitution is made in this direction. This
lane's product includes NULL verdicts. A floor that is too WIDE is the permissive
direction for a null, so importing the 0.044 model-vs-consensus floor here would let this
lane declare "no leak" without power. Both numbers are reported for every contrast: the
paired floor is the bar, the 0.044/0.0436 figure is printed beside it for continuity with
the older ledger entries.

If any verdict below would flip under the 0.044 floor, that is stated explicitly in
section 5 and in the headline.

### 1.3 Multiplicity

Registered family, primary: 2 features (`n_milb_seasons`, `milb_missing`) x 1 side (hit)
x 2 frames (full, debuted) x 4 feature arms = 16 tests. Every "significant" claim reports
its Bonferroni-adjusted p at m = 16 alongside the raw one. The pitcher arms
(`seasons_at_level`, `age`) and the `fv` instrument-sensitivity arms are EXPLORATORY and
are counted in their own families, declared in section 5, never pooled into the primary.

### 1.4 Bootstrap

B = 1000 draws, seed 20260807. Permutation arms draw a FRESH permutation on every
bootstrap draw, so permutation variability is inside the interval rather than conditioned
away. Point estimates for permutation arms are the mean over R = 50 independent
permutations at full sample, with the spread reported.

## 2. Part A. Does `n_milb_seasons` carry the label through group separation?

### 2.1 Arms, per (side, frame, feature)

| arm | construction | what it destroys | what it keeps |
|-----|--------------|------------------|---------------|
| A0 | shipped feature set | nothing | everything |
| A1 | feature column removed, refit | the column | -- |
| A2 | column row-permuted across the whole pool, kept in the set | individual signal AND group separation | dimensionality |
| A3 | column permuted WITHIN `debuted` and WITHIN `bust` separately | individual signal | group separation, marginal distribution per group |
| A3b | column permuted within (kind x decision_year) | individual signal | group separation AND fold-level structure |
| A4 | column replaced by its within-kind MEAN (a two-level indicator) | individual signal and within-group spread | group separation only |

A3b exists so that "you also destroyed the year structure" is not available as an
objection to A3.

### 2.2 Controls that could embarrass this lane (standing rule D)

- **Instrument-sensitivity control.** A3 applied to `fv`, the dominant and legitimately
  earned feature. `fv` separates the kinds strongly AND carries real individual signal.
  If A3 on `fv` does NOT cost accuracy, this instrument cannot detect individual signal
  and NO A3 result in this lane may be interpreted. This is a gate on the instrument, not
  on the feature, and it is checked first.
- **Negative control.** `milb_missing` on the hitter side is a declared-inert feature
  whose own drop gate moved pooled rho by -0.00022. All of its arms should be null. If
  any `milb_missing` arm fires, the instrument is producing false positives and every
  positive finding in this lane is downgraded to PLAUSIBLE.
- **The dumbest explanation.** A4 IS that control: a two-level column carrying nothing but
  the group means. If A4 reproduces the shipped accuracy, the feature's entire
  contribution is the label separation.

### 2.3 Registered verdicts, per (feature, side, frame)

Let d(arm) = rho_blend(arm) - rho_blend(A0), and M = that contrast's own paired MDE95.

- **LEAK.** |d(A3)| < M AND |d(A3b)| < M AND d(A2) <= -M AND |d(A4)| < M. The feature
  loses nothing when its individual content is destroyed but the group separation is
  kept, loses real accuracy when the separation goes too, and is fully reproduced by a
  group-mean stub. The column is a label indicator.
- **CLEAN.** d(A3) <= -M. Destroying individual content within group costs accuracy, so
  the feature carries within-group information and is not a pure label indicator.
- **INERT.** |d(A1)| < M AND |d(A2)| < M AND |d(A3)| < M. The column contributes nothing
  at all, so there is nothing for it to leak through. This is the registered PASS
  condition for the `milb_missing` negative control.
- **AMBIGUOUS.** Anything else. Reported as such, with the pattern, and it is NOT a leak
  finding.

A LEAK verdict is a MEASUREMENT and a recommendation only. Gate standard section 6
forbids removing a feature on this evidence and this lane removes nothing. The
deliverable in that case is a plan-level item with its own gate doc.

## 3. Part B. Is the as-of anchor itself outcome-selected?

`efv_dataset.build_matrix` sets, for a debuted row, `decision_year = debut_year` and
`cutoff = debut_date`; for a bust row, `decision_year = last_list_year + 1` and
`cutoff = last_list_date`. The rule that decides which MiLB seasons a row may see is
chosen by the label. Registered as the real content of plan item E1.

### 3.1 B-DESC. The mechanism, measured, before any accuracy number

Registered descriptive quantities, both sides, both kinds:

1. `first_season`, the loop bound `_milb_features` actually used, recomputed from
   `decision_year` and `cutoff` by the shipped formula.
2. `cut_lag = cutoff_year - milb_season` and `win_lag = first_season - milb_season`.
   These measure feature FRESHNESS against the decision date, which is what a leak would
   have to run through, as opposed to `stale`, which measures freshness against
   `decision_year`.
3. `P(bust | cut_lag)` and `P(bust | win_lag)`, the label-blind analogues of the wave-1
   `P(bust | stale)` table.

**Registered meaning, declared in advance.** Wave 1 read `P(bust | stale == 0) = 0.000`
as "row timing still determines the label". `stale` is defined as
`decision_year - 1 - milb_season`, and `decision_year` is offset by one relative to the
cutoff for busts and not for debuted rows. So:

- **DEFINITIONAL.** If `cut_lag` (and `win_lag`) do NOT separate the kinds materially
  while `stale` does, then the wave-1 separation is an artifact of the `decision_year`
  OFFSET, the feature WINDOW is symmetric in the cutoff, and the wave-1 headline
  overstates the defect. This lane must say so plainly if that is what it finds, even
  though it cuts against its own brief.
- **REAL WINDOW ASYMMETRY.** If `win_lag` separates the kinds too, the anchor really does
  hand busts a staler production read and every MiLB-derived feature, not just
  `n_milb_seasons`, is contaminated.

"Materially" is registered as: a difference in kind means of at least 0.25 seasons on
`win_lag`, or any `win_lag` cell with P(bust) outside [0.05, 0.95] at n >= 50.

### 3.2 B-ACC. The label-blind anchor arms

Debuted rows only are re-anchored; bust rows are untouched. The alternative anchor is the
BUST rule applied to a debuted row: `decision_year = asof_year + 1`, `cutoff = asof_date`,
where `asof_date` is the row's own last prospect-list snapshot. `milb` features are
recomputed by calling the shipped `efv_dataset._milb_features`, and a parity assertion
that the shipped anchor reproduces the stored block bit-for-bit is a precondition for
running this part at all.

| arm | features | decision_year | isolates |
|-----|----------|---------------|----------|
| B0 | shipped | shipped | -- |
| B1a | re-anchored | shipped | the feature-content channel |
| B1b | re-anchored | re-anchored | the full label-blind rule |
| B1c | shipped | re-anchored | the fold-assignment channel |

**Caveat registered in advance, not discovered afterwards.** `asof_date` for a debuted row
is the last list STRICTLY BEFORE the debut, so which snapshot is "last" is still selected
on the debut date. B1 removes part, not all, of the anchor's label-dependence. It is
therefore a CONSERVATIVE test: a positive result is strong, a null is a partial null and
must be reported as a partial null.

**Power rule, registered.** Report `treated_fraction` = the share of debuted rows whose
`milb` block changes any value under the re-anchor. If it is below 0.10, B1a and B1b are
declared UNDERPOWERED and reported as such. An underpowered arm is NOT a null.

### 3.3 The information-loss yardstick, and the registered DiD

Re-anchoring gives debuted rows an older production read. That is a loss of information
regardless of any leak. The dumbest explanation for any accuracy fall under B1 is
therefore "the features got staler", not "the leak was removed".

The `debuted` cut contains NO bust rows, so it cannot host a group-separation leak. Any
accuracy it loses under B1 is pure information loss. That makes it the yardstick.

Registered difference-in-differences:

    DiD = [rho(B1, full) - rho(B0, full)] - [rho(B1, debuted) - rho(B0, debuted)]

with its own paired-bootstrap MDE95 (both cuts refit on the same draw).

- **ANCHOR-LEAK.** DiD <= -MDE95(DiD) AND section 3.1 returned REAL WINDOW ASYMMETRY. The
  full-pool fit loses MORE than information loss alone explains, so the anchor was doing
  label work the features were credited for.
- **ANCHOR-CLEAN.** |DiD| < MDE95(DiD). The full-pool and debuted-only cuts lose the same
  amount, which is what information loss looks like. No leak is demonstrated through this
  channel.
- **UNDERPOWERED.** treated_fraction < 0.10, or MDE95(DiD) exceeds 0.02 in blend-rho
  units, in which case the instrument cannot resolve an effect the size of the eFV
  margin itself and says so.

## 4. What this lane will NOT do

- It will not remove, reorder, or reweight a feature. Gate standard section 6.
- It will not edit `efv_model.py` or `efv_dataset.py`. Edits are reported with exact
  old/new text.
- It will not write any file outside its OWNS block. It will not run pytest.
- It will not report a number that does not reproduce from
  `data/xfv_feature_leak_eval.json` (standing rule E). Every figure in section 5 carries
  the ledger key it came from.

## 5. RESULT (appended after the run)

`python tools/efv_feature_leak_lab.py all 1000`, B = 1000, seed 20260807, 660 s.
Ledger `data/xfv_feature_leak_eval.json`. Every number below carries its ledger key.
Nothing in sections 0 through 4 was edited after the run.

### 5.0 Headline

**No leak is demonstrated, and the premise the lane was handed does not survive contact
with the arithmetic.** The wave-1 statement "ROW TIMING STILL DETERMINES THE LABEL" is
true of the key `stale` and of nothing else: `stale` equals `cut_lag - 1[debuted]` on
1,133 of 1,134 hitter rows and 1,025 of 1,027 pitcher rows, i.e. the label is
arithmetically subtracted into the key by the `decision_year` convention. The MiLB
feature WINDOW that the anchor actually controls is `cutoff_year - 1` for 100.0% of
hitter rows and 1,025 of 1,027 pitcher rows, **identically for both kinds**, and the
label-blind freshness measure `win_lag` separates the kinds by 0.039 (hit) and 0.085
(pit) seasons against `stale`'s 1.037 and 1.085. `n_milb_seasons` is a measured NULL on
both cuts against a floor 4.1x tighter than the one the repo's prior drop gates used.

**Two disclosures that a reader must have before using any of this (standing rule B).**

1. **This lane's primary bar is a threshold the plan does not contain**: the
   paired-contrast MDE95 rather than `MDE95_POOLED_RHO` (0.044 hit / 0.0436 pit). It did
   NOT determine a single Part A verdict: all 48 Part A contrasts are non-resolvable
   under BOTH floors (`resolvable_paired` and `resolvable_legacy_floor` are `false` on
   every one). It did determine the Part B verdicts, where the paired floors are 0.006 to
   0.041 rather than 0.044.
2. **The pre-registered instrument-sensitivity control FAILED on all four cuts.**
   Permuting `fv`, the dominant feature, is not resolvable against its own paired floor
   anywhere (best case hit/debuted, -0.0222 against a floor of 0.0417, 0.53x). By section
   2.2 as I implemented it, that means **no A3 within-kind result in this lane may be
   read as evidence of absence**. What carries the Part A conclusion is the A1 drop arm,
   whose floor is genuinely tight because it has no permutation noise, plus the Part B
   descriptive arithmetic, which needs no accuracy instrument at all.

### 5.1 Membership, confirmed by import (`membership.checks`)

| key | in `_FEATURES_HIT` | in `_FEATURES_PIT` |
|-----|-----|-----|
| `stale` | no | no |
| `milb_season` | no | no |
| `decision_year` | no | no |
| `n_milb_seasons` | **yes** | no |
| `milb_missing` | **yes** | no |
| `seasons_at_level` | no | **yes** |

The brief's "on BOTH sides" is not executable for `n_milb_seasons` or `milb_missing`:
they are hitter-only. The pitcher side runs `seasons_at_level`, the pitcher feature that
takes the same one-season truncation, as an EXPLORATORY analogue.

`fit_production_stack` (the served fit) trains on the full pool, so the group separation
IS present in the served model. `_run_eval("debuted_km")`, the published rho, trains
debuted-only and is structurally blind to it. That asymmetry is why `full_pool` is the
primary frame here.

### 5.2 Parity (`repro`)

| cut | replica cons / blend | shipped artifact |
|-----|----------------------|------------------|
| hit `full_pool_km` | 0.30016 / 0.27873 (n 1792) | 0.3002 / 0.2787 (n 1792) |
| hit `debuted_km` | 0.39192 / 0.39933 (n 755) | 0.3919 / 0.3993 (n 755) |
| pit `full_pool_km` | 0.20150 / 0.21721 (n 1885) | 0.2013 / 0.2171 (n 1886) |
| pit `debuted_km` | 0.24937 / 0.25606 (n 890) | 0.2495 / 0.2562 (n 890) |

The one-row pitcher full-pool difference is the same known replica gap
`tools/efv_cohort_floor_lab.py repro` reports.

**Correction to section 1.1, recorded here rather than by editing the registration.**
Section 1.1 said pools would come from `tools/efv_cohort_floor_lab.load_pool`. They do
not: the lab has a LOCAL `base_pool`, because Part B must build the same pool from
MODIFIED rows and that loader only reads the matrix from disk. The fit and metric
primitives are still imported from `tools/efv_mde_lab.py` as registered. The parity table
above is what makes the substitution checkable, and it reproduces the shipped artifacts
to the fourth decimal on all four cuts.

Self-check (`part_a.*.selfcheck_max_abs_d_blend_minus_d_margin`) = **0.0 exactly** on
both sides: every feature arm moves the model-minus-consensus margin by precisely the
amount it moves blend rho, because the consensus leg never touches the design matrix. So
every "margin" reading below is the same number as its "accuracy" reading.

### 5.3 Part B descriptive: the wave-1 premise is DEFINITIONAL, not a window asymmetry

Ledger `part_b_desc`. Registered verdict on both sides: **DEFINITIONAL**.

| quantity | hit debuted mean | hit bust mean | gap | pit gap |
|---|---|---|---|---|
| `stale` = `decision_year - 1 - milb_season` | 0.129 | 1.166 | **+1.037** | **+1.085** |
| `cut_lag` = `cutoff_year - milb_season` | 1.127 | 1.166 | +0.039 | +0.088 |
| `win_lag` = `first_season - milb_season` | 0.127 | 0.166 | **+0.039** | **+0.085** |

`P(bust | stale)`: 0.000 at 0 (n 509), 0.871 at 1 (n 541), 0.987 at 2 (n 75). Wave 1
reproduced exactly.

`P(bust | win_lag)`, the same table on the label-blind freshness measure: **0.480 at 0
(n 981), 0.517 at 1 (n 143)**. The base rate is 0.488. There is no separation.

Two identities, both in the ledger:

- `identity_stale_is_cutlag_minus_label`: `stale == cut_lag - 1[kind == debuted]` holds
  on **1,133 / 1,134** hitter rows and **1,025 / 1,027** pitcher rows. `stale` is not a
  freshness measurement. It is `cut_lag` with the label subtracted into it.
- `identity_window_is_cutoff_year_minus_1`: `first_season - (cutoff_year - 1)` is **0 for
  all 553 bust and all 581 debuted** hitter rows, and 0 for all 334 bust and 691 of 693
  debuted pitcher rows. After the 2026-07-24 repair the MiLB feature window is a function
  of the CUTOFF DATE alone and the rule is the same for both kinds.

**What this changes.** The brief said the repair "moved the proxy one year left and
sharpened it into a perfect NEGATIVE proxy". Measured: the repair made the WINDOW
symmetric, and the residual perfect proxy lives entirely in a derived key that no model
reads. The plan's E1 framing ("the cutoff that decides which MiLB seasons a row gets is
chosen by the label") is FALSE as stated for the post-repair builder: the cutoff decides
the window through `cutoff_year - 1` and both kinds go through the same expression. What
remains label-chosen is the cutoff DATE itself, and it turns out not to matter because
essentially every cutoff month is below the October boundary, so only the cutoff YEAR
survives into the window.

`n_milb_seasons` still separates the kinds (gap -1.367 hit, -0.783 pit). That separation
therefore comes from the players, not from the anchor: busts really do accumulate fewer
observed MiLB seasons before their last listing than debuted players do before their
debut. Part A asks whether the model converts that into accuracy.

### 5.4 Part A: nothing is resolvable, in either direction, on any cut

Ledger `part_a`. Full grid: 48 contrasts (2 sides x 2 cuts x 12 arms). **Zero are
resolvable against their own paired floor, and zero against the 0.044/0.0436 legacy
floor.** Smallest raw two-sided p anywhere in the grid is **0.070**; Bonferroni at
m = 16 (primary family) or m = 20 (pitcher exploratory family) puts every adjusted p at
**1.000**. Nothing in this lane is significant before or after adjustment.

`n_milb_seasons`, hitter, the primary question:

| cut | arm | d blend | own paired MDE95 | margin | raw p |
|-----|-----|---------|------------------|--------|-------|
| full | A1 drop | +0.00596 | 0.01076 | 0.55x | 0.702 |
| full | A2 perm all | +0.00564 | 0.01352 | 0.42x | 0.734 |
| full | A3 perm within kind | +0.00616 | 0.01466 | 0.42x | 0.784 |
| full | A3b perm within kind x year | +0.00665 | 0.01472 | 0.45x | 0.864 |
| full | A4 kind-mean stub | +0.00574 | 0.02602 | 0.22x | 0.866 |
| debuted | A1 drop | +0.00035 | 0.02622 | 0.01x | 0.716 |
| debuted | A2 perm all | +0.00058 | 0.02822 | 0.02x | 0.764 |
| debuted | A3 perm within kind | +0.00119 | 0.02789 | 0.04x | 0.728 |
| debuted | A3b perm within kind x year | -0.00055 | 0.03113 | 0.02x | 0.958 |
| debuted | A4 kind-mean stub | +0.00021 | 0.02751 | 0.01x | 0.694 |

Read the SPREAD, not the significance. On each cut all five arms agree with each other to
within 0.001 in blend rho. Deleting the column, shuffling it, shuffling it inside each
label group, and replacing it with nothing but the two group means all produce the same
model. A column whose entire content can be replaced by its group means without moving
anything is not converting the label into accuracy, because it is not converting anything
into accuracy. And the sign is wrong for a leak in both cuts: dropping the feature nudges
rho UP, it does not cost the model the accuracy a leaking feature would be supplying.

The A1 drop floor on hit/full is **0.01076**, which is **4.1x tighter** than the 0.044
the prior drop gates used, and the observed effect is 0.55x of even that. This is the one
contrast in the lane with real power, and it is a null.

The `milb_missing` negative control behaves exactly as registered: A1/A2/A3/A3b all
within 0.0015 of shipped on both cuts, at floors as tight as 0.00324. The instrument is
not manufacturing positives.

**Registered verdicts** (`part_a_verdicts`): INERT for `n_milb_seasons` and
`milb_missing` on both hitter cuts and for `seasons_at_level` and `age` on both pitcher
cuts. NOT_SENSITIVE for the `fv` instrument control on all four cuts, which is the
failure described in 5.0 and re-stated in 5.6.

### 5.5 The one result that did not come out clean, reported as sub-floor

`part_a.pit.cuts.full.arms`. On the PITCHER full pool, replacing a feature column with a
pure two-level label indicator RAISES blend rho:

| arm | d blend | own paired MDE95 | margin | raw p | Bonferroni (m 20) |
|-----|---------|------------------|--------|-------|-------------------|
| `age` A4 kind-mean | **+0.02271** | 0.02888 | 0.79x | 0.070 | 1.000 |
| `seasons_at_level` A4 kind-mean | **+0.01699** | 0.02957 | 0.57x | 0.146 | 1.000 |

For scale, the published pitcher full-pool eFV-over-consensus margin is +0.0157
(`data/xfv_cohort_floors.json reproduction.replica.pit.full_pool_km.delta` = 0.01571,
reproduced here as 0.21721 - 0.20150). A pure label indicator buys **1.45x that entire
margin**. Both figures are sub-floor and non-significant at every multiplicity level, so
this is NOT a finding about any shipped feature and no feature is implicated.

What it measures is how EXPLOITABLE the `full_pool_km` cut is by any label-correlated
column, which is the same worry `docs/EFV_GATE_STANDARD.md` lines 110-133 raise as the
debut/no-debut carve-out and which `tools/efv_cohort_floor_lab.py carveout` tested for
AUC. It is escalated as a P2 measurement note, not as a defect, and it is the natural
next probe if anyone wants to open this. It cuts AGAINST this lane's own null: it says
the cut where the served fit lives has room for a leak, even though no shipped feature is
currently occupying it.

### 5.6 The failed instrument control, stated plainly

Section 2.2 registered: "If A3 on `fv` does NOT cost accuracy, this instrument cannot
detect individual signal and NO A3 result in this lane may be interpreted."

The doc said "cost accuracy". The lab implemented that as "cost accuracy beyond its own
paired floor", a stricter reading chosen when the lab was written, after the doc. Both
readings are reported because the choice matters:

| cut | `fv` A3 d blend | own paired MDE95 | strict reading | loose reading |
|-----|-----------------|------------------|----------------|---------------|
| hit full | **+0.00685** | 0.03079 | NOT_SENSITIVE | NOT_SENSITIVE (it HELPS) |
| hit debuted | -0.02215 | 0.04171 | NOT_SENSITIVE | SENSITIVE |
| pit full | -0.01104 | 0.02979 | NOT_SENSITIVE | SENSITIVE |
| pit debuted | -0.00963 | 0.03490 | NOT_SENSITIVE | SENSITIVE |

On hit/full the control fails under BOTH readings and for a reason worth recording:
permuting `fv` inside the model leg IMPROVES full-pool blend rho, because the hitter
full-pool model leg is worse than its own consensus baseline (0.27873 vs 0.30016, the
lane-I4 loss), so degrading model information pulls the blend toward the better baseline.
On that cut, destroying information is a route to a higher score, and no ablation-style
instrument can be read at face value there. That is the "dumbest possible explanation"
control from standing rule D doing its job, and it disqualifies the cut, not the feature.

The consequence for the deliverable: the sharp instrument the brief asked to lead with,
permute-within-kind, **cannot certify the absence of a leak at this sample size**. The
Part A null rests on the drop arm and on the arm-agreement pattern. For the control alone
to clear on the best cut (hit/debuted, margin 0.531x) the pool would have to be **3.6x**
larger, since the floor falls as 1/sqrt(n); the `n_milb_seasons` A3 arms themselves sit at
0.42x (full) and 0.04x (debuted), so certifying THEM would take 5.7x and 625x. Those pools
do not exist.

### 5.7 Part B accuracy: the label-blind anchor changes nothing measurable

Ledger `part_b`. Precondition met: the shipped anchor reproduces the stored `milb` block
on **581 / 581** hitter and **693 / 693** pitcher debuted rows (`meta.parity_rate` = 1.0),
so any movement is attributable to the re-anchor and not to cache drift.

Treated fraction: **62 / 581 = 0.1067** (hit) and **69 / 693 = 0.0996** (pit) of the
debuted rows that carry a MiLB block, which is 0.073 and 0.070 of all debuted rows. The
re-anchor is nearly a no-op precisely BECAUSE of 5.3: since the window is already
`cutoff_year - 1` for both kinds, swapping a debuted row onto the bust rule only moves it
when its last list fell in an earlier calendar year than its debut.

| side | arm | d full | d debuted | DiD | DiD MDE95 | registered verdict |
|------|-----|--------|-----------|-----|-----------|--------------------|
| hit | B1a features only | +0.00005 | +0.00098 | -0.00093 | 0.01168 | **ANCHOR-CLEAN** |
| hit | B1b features + fold | +0.00766 | +0.00376 | +0.00389 | 0.03625 | UNDERPOWERED |
| hit | B1c fold only | +0.00902 | +0.00487 | +0.00415 | 0.03478 | UNDERPOWERED |
| pit | B1a features only | -0.00274 | +0.00338 | -0.00612 | 0.01250 | UNDERPOWERED |
| pit | B1b features + fold | -0.00695 | +0.01252 | -0.01947 | 0.02844 | UNDERPOWERED |
| pit | B1c fold only | -0.01123 | +0.01336 | -0.02459 | 0.03402 | UNDERPOWERED |

The hitter feature-channel arm, the one the plan's E1 actually asks about, moves the
served-frame accuracy by **+0.00005**, five parts in a hundred thousand, against a floor
of 0.0117. ANCHOR-CLEAN.

**Where a registered threshold changed a LABEL but not the answer (rule B).** Pitcher B1a
is called UNDERPOWERED only because `treated_fraction` = 0.0996 fell 0.0004 below the
0.10 rule registered in section 3.2. That is a knife edge and it is disclosed rather than
leaned on. Its DiD, -0.00612 against a floor of 0.01250, would read ANCHOR-CLEAN on the
section 3.3 criterion. The substantive answer is the same under either label. Likewise
B1b and B1c on both sides would all read ANCHOR-CLEAN on the DiD comparison alone; they
are called UNDERPOWERED because their floors exceed the registered 0.02 cap, which is the
conservative direction and is exactly what standing rule F asks for when the product is a
null.

The fold-assignment channel (B1c) is the largest anchor effect measured, not the feature
channel: on the pitcher side moving debuted rows to their label-blind fold costs -0.0112
on the full pool while ADDING +0.0134 on the debuted cut, DiD -0.0246 at 0.72x its floor.
Suggestive, unresolved, and it is about which fold a row is trained in, not about what
the row can see. Registered as the follow-up worth power if E1 is reopened.

**Registered caveat honoured.** `asof_date` for a debuted row is the last list strictly
BEFORE the debut, so B1 removes part, not all, of the anchor's label-dependence. The Part
B null is therefore a PARTIAL null. It is decisive only in combination with 5.3, which
shows there is very little left for the anchor to do.

### 5.8 Verdict, per the registered grid

| question | registered verdict |
|----------|--------------------|
| Is `stale` a shipped feature? | NO, confirmed by import on both sides |
| Does `n_milb_seasons` carry the label into served accuracy? | **NO measurable leak.** INERT on both hitter cuts; drop arm null at 0.55x a floor 4.1x tighter than prior gates, sign wrong for a leak |
| Same, `milb_missing` (negative control) | INERT, as registered. Instrument produces no false positives |
| Same, `seasons_at_level` / `age` (pitcher, exploratory) | INERT on both cuts |
| Can the within-kind instrument certify absence? | **NO.** Its own `fv` control fails on all four cuts. The null rests on the drop arm |
| Is the as-of anchor outcome-selected in the FEATURE WINDOW? | **NO.** `first_season == cutoff_year - 1` for both kinds, 1134/1134 hit, 1025/1027 pit |
| Is the wave-1 `stale` proxy a leak? | **NO, it is a definitional identity.** `stale == cut_lag - 1[debuted]`, 1133/1134 and 1025/1027 |
| Does a label-blind anchor change served-frame accuracy? | **NO.** Hitter feature channel +0.00005 at a 0.0117 floor. ANCHOR-CLEAN, partial |
| Anything escalated? | One P2 measurement note: a pure label indicator buys +0.0227 on the pitcher full pool, 1.45x the published margin, sub-floor at 0.79x and p 0.070 raw / 1.000 adjusted |

No feature was removed, reordered or reweighted. No shipped file was edited. Requested
edits are documentation only and are listed in the lane report.

