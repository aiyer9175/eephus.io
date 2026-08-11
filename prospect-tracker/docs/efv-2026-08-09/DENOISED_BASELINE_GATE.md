# B-L6: the denoised-baseline fairness control

**Pre-registration. Written 2026-08-10, BEFORE the control was run.** Nothing in the
Results section existed when the Design and Decision-rule sections were written; the
commit that adds this file with an empty Results section is the receipt.

Lane owner: Track B. Depends on C-A1 (precision estimates, shipped in
`data/source_cohort_accuracy.json`) and on B-L1 (the head-to-head floor under both
estimators, shipped in `data/xfv_power_eval.json -> partb_floors.cells.headtohead_common`).

---

## 1. The question

Every published eFV-vs-consensus claim compares eFV against the consensus **as served**.
The consensus as served is a noisy aggregate of noisy raters. If a meaningful part of
eFV's margin is eFV beating *the aggregation error* rather than beating *the raters*,
then the honest headline is "the consensus can be built better", not "the model beats
the boards".

That control has never been run. It could not be run: identifying per-source precision
needs a third instrument, and until the Baseball America backfill landed on 2026-08-10
there were only two scored sources. `precision_label_free` reported
`identified: false`. It now reports `identified: true` on 6,286 rows.

## 2. The incumbent being challenged

From `data/xfv_power_eval.json`, cell `headtohead_common`, basis 2026-08-08:

| quantity | value |
| --- | --- |
| scored rows | 3,224 |
| player clusters | 1,051 |
| rho(consensus, war) | 0.32070 |
| rho(eFV, war) | 0.35387 |
| **delta** | **+0.03318** |
| MDE95 under E_refit | 0.0345 -> margin **0.963x** -> **NULL** |
| MDE95 under E_cond | 0.0322 -> margin **1.031x** -> **RESOLVABLE WIN** |

The incumbent is already split. It is a win under one registered estimator and a null
under the other, by 3.7% and 3.6% respectively. **Any baseline improvement worth more
than about 0.001 rho kills the E_cond win.** That is the whole reason this control has
teeth, and it is why the prior below is not lopsided.

## 3. The denoised baseline, and what it is not

Model, from C-A1: `x_is = a_s + b_s * mu_i + e_is`, `Var(e_is) = sigma_s^2`.

BLUE of the latent `mu_i` from the observed grades is the GLS combination

```
mu_hat_i  proportional to  sum_s (b_s / sigma_s^2) * (x_is - a_s)
```

with `w_s ∝ b_s / sigma_s^2`, **not** `1 / sigma_s^2`. The naive inverse-variance form
rewards range compression: a source publishing a narrow range has a small `b_s` and a
small raw variance, so inverse variance upweights whichever source expresses the least
information. This is C-A1's finding and it is not re-litigated here.

Weights taken frozen from `precision_label_free.estimator_primary_em_fiml`:

| source | b_s | sigma_s | w_s = b/sigma^2 |
| --- | --- | --- | --- |
| fangraphs | 4.3417 | 3.1542 | 0.43638 |
| mlb_pipeline | 4.6111 | 2.9969 | 0.51340 |
| baseballamerica | 4.4211 | 4.8076 | 0.19128 |

Normalized over the two scored sources, `alpha_fg = 0.4595`.

**Baseball America is the identifying instrument, not a term in the baseline.** Adding
BA to the scored set collapses the common set from 4,284 rows to 295 and flips
`consensus_wins`; that is a settled finding and it is not reopened. BA's role here is
that with three sources the two-source system stops being underdetermined
(`two_source_identification.identified: false` — two sources give three second moments
against four unknowns), so `b` and `sigma` for FanGraphs and Pipeline become estimable.
The baseline itself is then computed on FanGraphs and Pipeline only, on exactly the rows
the incumbent already scores. **Zero rows are added or removed by this lane.** A row-set
change is a pre-registered abort condition (section 5).

Two of the three ingredients the master plan named for this baseline were retired by
C-A1's own evidence, and are demoted to sensitivity arms rather than dropped silently:

- **lattice correction (Sheppard `h^2/12 = 2.0833`).** C-A1 declines to subtract it from
  the served weight because the served aggregator observes the quantized grade, so
  lattice noise is real noise in the quantity being combined. For a *baseline* the
  question is at least arguable, so it runs as arm S1 and does not move the primary.
- **`lambda_k` shrinkage.** C-A1 recorded this NULL, not a lane: coverage dependence
  collapses to p 0.944 post-shrinkage, and the resolvable `k=1` stratum has 56 rows
  against the ~2,000 its interaction gate needs. Arm S2 runs the reliability-shrunk
  variant anyway, because shrinking toward a per-*year* mean is not a global monotone
  transform and therefore *can* move a pooled Spearman.

## 4. The caveat that must be printed wherever this number is

**The precision estimate is not vintage-disciplined over the scored window.**
`vintage_availability` makes precision estimable for board years 2023-2026 only. The
head-to-head scores board years 2014-2024, and `MIN_LAG_YEARS = 3` means the resolvable
window can never reach 2024+ until 2027. **The two sets are very nearly disjoint.**

So the denoised baseline is defined using an estimate computed partly on the rows it
scores. That is legitimate for a **baseline definition** — a baseline is not a
prediction, and the control asks "was eFV's margin against a *well-built* aggregate",
which is a question about the aggregate's construction, not about forecasting. It is
**not** legitimate to quote this baseline as an out-of-sample result, and any surface
that shows it must carry the label. Registered artifact key:
`basis.vintage_disciplined: false`.

This cuts *against* eFV, not for it: a baseline fitted with hindsight on its own scoring
rows is the strongest opponent eFV could face. If eFV's margin survives that, it
survives. If it does not, the collapse is partly an artifact of the advantage handed to
the baseline, and the write-up must say so in the same breath.

## 5. Design, frozen

Producer: `tools/efv_denoised_baseline_lab.py`, entry `run(B=2000, write=True)`,
artifact `data/xfv_denoised_baseline_eval.json`.

**Frame.** The identical 3,224-row / 1,051-cluster head-to-head frame, target `war`,
unweighted pooled Spearman, one row per (player, board-year, common-set pair). Built by
calling `source_backtest._load_universe`, `_resolved_years`, `_rater_grades_for_year`,
`_outcome` and `efv_mde_lab._h2h_pass` — the shipped primitives — never a private copy.

**PARITY IS A HARD PRECONDITION.** Before any arm is scored, the lab asserts that its
reconstructed consensus leg and target leg are **bit-identical** to `_h2h_pass`'s, and
that `rho(consensus, war)` reproduces 0.32070 and `delta` reproduces +0.03318. If parity
fails the lab **raises and writes nothing**. This is the `parity_x1` discipline: a
reimplemented pool is how two labs stop measuring the same thing.

**Arms.**

| arm | baseline leg |
| --- | --- |
| P0 | published `prospx_consensus` (the incumbent, for parity) |
| **P1 (primary)** | GLS `w_s ∝ b_s/sigma_s^2` on per-(source, board-year) centered FG and MP |
| S1 | P1 with `sigma_s^2` reduced by Sheppard `h^2/12` before weighting |
| S2 | P1 shrunk toward the per-board-year mean by reliability |
| S3 | P1 without per-year centering (global centering only) |
| S4 | equal-weight FG/MP, `alpha = 0.5` |
| C1 | **weight-swap control**: FG and MP weights exchanged |
| C2 | **random-weight control**: 200 draws of `alpha ~ U(0.2857, 0.7143)`, the shipped `WEIGHT_CLAMP` reachable range |

**Floors.** Both estimators, same protocol and same seeds as B-L1 so the numbers are
comparable to the incumbent cell without rescaling. E_cond: player-cluster bootstrap,
B = 2,000. E_refit: resample the eFV matrix pool by player, refit the forward chain,
rescore both legs, B = 2,000. Seed 20260809.

## 6. Decision rule, registered before the result

Let `d1 = rho(eFV) - rho(P1)` be the primary.

1. **The control is only informative if the baseline actually improved.** If
   `rho(P1) <= rho(P0)`, the denoised construction is not a better aggregate on this
   frame and the control says nothing about eFV. Report it as **UNINFORMATIVE**. Do not
   report it as a win for eFV. Do not then go looking for an arm that does move.
2. **No-op check.** If `spearman(P1, P0) >= 0.999` on these rows, the two baselines are
   the same ranking and any delta difference is numerical noise. Report **NO-OP** and
   say the precision weighting is not reachable through this statistic.
3. **SURVIVES** if `d1 >= MDE95_cond(d1)`. The claim is then carried at exactly the
   strength of its weakest surviving estimator, as today: E_cond win, E_refit null. It
   does not get upgraded by having survived.
4. **COLLAPSES** if `d1 < MDE95_cond(d1)`, i.e. the E_cond win the site currently rests
   on is gone against a better-built baseline.
5. `d1 < 0` is a **REVERSAL** and is reported as one.

**The pre-commitment, per master-plan decision 3.** If the edge COLLAPSES or REVERSES:

- The finding ships as a **baseline improvement**. The headline becomes "aggregating the
  boards by measured precision beats aggregating them as served", and the eFV
  head-to-head claim is withdrawn to whatever survives.
- **The conviction copy gets harder to clear.** Every surface asserting eFV beats the
  consensus must state that the comparison is against the served consensus and that a
  precision-weighted consensus closes N% of the gap, with N printed.
- No arm-shopping. P1 is the primary and was named before the run. S1-S4 are
  sensitivities and cannot become the headline; if a sensitivity disagrees with P1 that
  fact is reported as instability, which is a *weaker* result, not a stronger one.

**The controls are adjudicated too.** If C1 (swapped weights) or a majority of C2
(random admissible weights) also beat the published consensus, then the finding is not
"precision weighting works" but "**the shipped consensus construction is beatable by
almost any reweighting**", which is a defect report against `consensus.py` and must be
written as one.

**Abort conditions.** Row count != 3,224, cluster count != 1,051, P0 delta != +0.03318
to 5 decimals, or any arm producing a non-finite rho. Any of these means the frame moved
and the lane stops rather than reporting on a frame that is not the incumbent's.

## 7. Prior

Registered before running, per the master plan: **P(eFV's edge survives) = 0.50.**

Reasoning recorded so it can be scored later. Against survival: the incumbent E_cond
margin is 1.031x, so ~0.001 rho of baseline improvement kills it, and the baseline is
being handed a hindsight-fitted weight. For survival: `alpha_fg` moves only 0.5 ->
0.4595, the reachable alpha range is narrow (0.4491-0.4979 per C-A1), Spearman is
rank-only so a small reweighting may not move ranks at all, and C-A1's `oracle_ceiling`
found the *global* oracle gain over the served consensus is only +0.0040 — which is a
real bound on how much any reweighting of these sources can buy.

That last number is the honest tell, and it is registered here rather than after the
fact: **an oracle reweighting is worth +0.0040 rho, and the margin that must be
destroyed is +0.0332.** A pure-reweighting baseline improvement is therefore very
unlikely to be sufficient on its own. If the edge collapses anyway, the cause is
something other than the weights and that must be found before the collapse is
published.

---

## 8. Results

*Empty at pre-registration. Filled by the run.*
