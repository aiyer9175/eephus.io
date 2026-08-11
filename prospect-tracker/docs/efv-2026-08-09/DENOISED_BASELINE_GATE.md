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

## 7a. Amendment 1 — the abort condition fired, and it was right

**Written after the parity run, before any denoised arm had been scored.** What I had
seen when I wrote this: the parity result and the incumbent's own numbers on today's
data. What I had not seen: any arm, any floor, any control, any verdict. Recorded that
precisely because an amendment written after seeing the answer is worthless.

The parity precondition **passed** — the reconstruction is bit-identical to
`efv_mde_lab._load_h2h` / `_h2h_pass` on all three legs. The registered abort conditions
**failed**, because the frame itself has moved since the incumbent floor was measured on
2026-08-08:

| quantity | registered (2026-08-08) | today | change |
| --- | --- | --- | --- |
| scored rows | 3,224 | **3,234** | +10 |
| player clusters | 1,051 | **1,051** | 0 |
| common-set players | 1,563 | **1,571** | +8 |
| rho(consensus, war) | 0.32070 | **0.31889** | -0.00181 |
| rho(eFV, war) | 0.35387 | **0.35027** | -0.00360 |
| **delta** | **+0.03318** | **+0.03138** | **-0.00180** |

**Cause, and it is this program's own work.** The cluster count is unchanged, so the eFV
matrix pool did not move; what moved is the set of common-set rows those same players
own. That is the Baseball America backfill (4,597 rows), the identity repairs (the
`garrett_wright` un-merge, six new aliases, five quarantined rows deleted) and the
`rebuild_only` that followed. More players now carry all three of FanGraphs, Pipeline and
a consensus grade in a preseason window, so the common set grew.

**This is the exact staleness that has already crossed a verdict boundary twice in this
program** — once when `EFV_GATE_STANDARD` s7.5 had to be retracted because the evals were
two days staler than the matrices, and once when the served matrices were found to
reproduce at only 74.8%. `efv_power_lab` carries a comment saying so in as many words:
mixing a 2026-08-08 sd with a 2026-08-09 delta is the failure mode.

**The amendment.** The hard abort is re-pointed rather than removed:

- **Structural integrity stays a hard abort**: parity must be bit-identical, no rho may
  be non-finite, and the cluster count may not collapse. These are unchanged.
- **The frame constants become a DRIFT REPORT, not an abort.** Their job was to prove
  the control runs on the incumbent's basis. They have now proved the opposite, which is
  information, not a reason to stop.
- **The incumbent is re-derived on today's frame, in the same run, under the same seeds
  and the same B**, and every comparison in section 6 is made against *that*. Both legs
  move together or neither does. No number from 2026-08-08 is mixed with a number from
  today.

**The decision rule in section 6 is not touched.** Same primary, same arms, same
controls, same five outcomes, same collapse pre-commitment, same prior. Only the basis
the rule is evaluated on is refreshed, which is what the one-basis discipline requires.

**A finding that already follows, independent of anything this lane does next.** The
incumbent E_cond floor was 0.0322 against a delta of +0.03318, a margin of 1.031x — the
entire published head-to-head win rested on 3.1% of headroom. Today's delta is +0.03138.
If today's E_cond floor lands anywhere near 0.0322, **the shipped win is already gone on
current data before a single denoising arm runs**, and that is a fact about the served
site, not about this control. It is reported in the Results section either way.

## 7b. Amendment 2 — the registered primary was the wrong estimator, and the correction cuts against us

**Written after the arms were scored, before the full-B floors existed.** Disclosed in
full because an amendment made after seeing a number is the kind that needs the most
scrutiny.

P1, as registered, centers each source **inside its board year**. The incumbent baseline
does not do that. So P1 is not a denoised consensus — it is a denoised consensus **plus a
within-year transform**, and the comparison is not like-for-like.

That matters here because the statistic is a **pooled** Spearman across board years, and
the mechanism block measures exactly what the transform costs: pooled consensus rho is
0.31889 against a mean within-year rho of 0.31096, so **+0.00793 of the statistic is
cross-cohort ranking**. Centering per year deletes that, which is essentially the whole
gap between P1 (0.30703) and S3 (0.31992).

Per-year centering is right where C-A1 uses it — estimating `sigma_s` — because a source
rebasing its scale between vintages would otherwise read as variance. It is wrong when
applied to a **served score** that is going to be pooled across years.

**The corrected primary is S3**: the same GLS precision weights, with a global per-source
intercept. Adjudicated under the identical rule.

**The direction is the tell.** S3 makes eFV look *worse*, not better: the margin falls
from +0.04324 against P1 to +0.03035 against S3, and the verdict moves from a spurious
win to a collapse. Choosing the specification that damages your own claim is the opposite
of spec-shopping. Both primaries are reported; the conservative one is the headline.

---

## 8. Results

Producer `tools/efv_denoised_baseline_lab.py`, artifact
`data/xfv_denoised_baseline_eval.json`. B = 2,000 both estimators, seed 20260809.
Parity precondition **passed**: the reconstructed frame is bit-identical to
`efv_mde_lab._load_h2h` / `_h2h_pass` on all three legs.

### 8.1 The headline is not about denoising

**The shipped head-to-head claim no longer clears its floor under EITHER estimator, on
today's data, against the consensus exactly as served.**

| basis | delta | E_cond floor | margin | E_refit floor | margin |
| --- | --- | --- | --- | --- | --- |
| registered 2026-08-08 | +0.03318 | 0.0322 | 1.031x **WIN** | 0.0345 | 0.963x NULL |
| **today, served consensus** | **+0.03138** | **0.0327** | **0.960x NULL** | **0.0353** | **0.889x NULL** |
| today, denoised baseline (S3) | +0.03035 | 0.0338 | 0.898x NULL | 0.0365 | 0.832x NULL |

The E_cond win the site rests on is **gone before the control even runs**, and the
attribution block says why:

- moved by **frame drift**: **-0.00180** (64%)
- moved by **denoising**: **-0.00103** (36%)

The drift is this program's own Baseball America backfill and identity repairs landing in
the common set. It is a separate finding from B-L6 and is reported separately.

### 8.2 Verdicts

- **Registered primary P1: UNINFORMATIVE.** `rho(P1) = 0.30703 < rho(P0) = 0.31889`, so
  the construction is not a better aggregate and decision rule 1 fires. eFV "beating" P1
  by +0.04324 at 1.310x its floor is **not a win** and is not reported as one — it is
  eFV beating a baseline that was handicapped by the transform Amendment 2 identifies.
  This is precisely the outcome rule 1 exists to catch.
- **Corrected primary S3: COLLAPSES.** +0.03035 against an E_cond floor of 0.0338
  (0.898x) and an E_refit floor of 0.0365 (0.832x). Null under both.
- Neither NO-OP nor REVERSAL fired. The denoised baseline is a genuinely different
  ranking (`rank_corr_with_published` well under the 0.999 no-op threshold), and eFV
  stays ahead of it in point estimate.

### 8.3 What denoising actually bought: almost exactly nothing

`rho(S3) - rho(P0) = +0.00103`. That is the best any precision-weighted recombination of
FanGraphs and Pipeline achieves on this frame, and it is far below any floor.

**This was predicted in section 7 and is the pre-registration paying off.** C-A1's
`oracle_ceiling` put a *perfect hindsight* reweighting at **+0.0040** rho. A measured
weighting landing at +0.0010 against a +0.0040 ceiling is the expected result, not a
surprise, and it was written down before the run.

**The precision estimates are nevertheless directionally right.** Among arms sharing the
same centering, the ordering is exactly what precision weighting predicts and holds under
both centerings:

| arm | rho | vs served |
| --- | --- | --- |
| S3 GLS precision (global centering) | 0.31992 | **+0.00103** |
| P0 served consensus | 0.31889 | — |
| P1 GLS precision (per-year centering) | 0.30703 | -0.01186 |
| S4 equal weight | 0.30123 | -0.01766 |
| C1 **weights swapped** | 0.29690 | -0.02199 |

GLS beats equal weight, which beats the deliberately-wrong swapped weights, monotonically.
The measurement is real. Its **magnitude** is negligible.

### 8.4 The controls exonerate `consensus.py`

**C1 (weights swapped): does not beat the served consensus** (-0.02199), and is the worst
arm in the family.

**C2 (200 random admissible reweightings inside the shipped `WEIGHT_CLAMP` alpha range
[0.2857, 0.7143]): 0 of 200 beat the served consensus.** Mean 0.30323, max 0.31296,
against 0.31889.

Registered reading: had a majority of arbitrary reweightings beaten it, the finding would
have been a **defect report against `consensus.py`**. They did not. The shipped consensus
construction is doing real work that a linear reweighting of two sources cannot
reproduce, and it survives this lane with its reputation improved.

### 8.5 The information confound was measured, not assumed away

The served consensus is not a two-source object, so a two-source baseline could have lost
on **inputs** rather than on **method**. Measured: **2,894 of 3,234 rows (89.5%) carry
exactly two sources**; only 10.5% carry three.

Restricted to the two-source rows, where the baseline has everything the served consensus
had, the ordering is **unchanged**: P0 0.31919, S3 0.31986, P1 0.30585, S4 0.29988,
C1 0.29467. The confound is real but small and does not drive any verdict.

### 8.6 The pre-commitment, and the branch that did not apply

The collapse branch fires. But the pre-commitment's remedy — "**it ships as a baseline
improvement**" — **does not apply, because there is no baseline improvement to ship.**
Denoising bought +0.001 rho, sub-floor, and shipping it would be shipping noise. That
would violate the zero-weights-ship discipline C-A1 established for exactly this reason.

What remains binding is the second half: **the conviction copy gets harder to clear.**
The honest claim after this lane is:

> eFV's out-of-sample grade ranks the common set ahead of the consensus by +0.031 rho,
> and **that margin does not clear its own detection floor under either registered
> estimator**. It is a consistent point-estimate lead, not a measured win.

That is weaker than what the site said before, and it is what the evidence supports.

### 8.7 Prior scored

Registered prior: **P(edge survives) = 0.50.** Outcome: **it did not survive** — but for a
reason the prior did not contemplate. The prior imagined survival being decided by how
much denoising bought. Denoising bought +0.001; the margin died mostly because the frame
moved and because it was never more than 1.03x its floor to begin with.

The reasoning recorded in section 7 was right on the mechanism (the oracle ceiling
correctly predicted denoising would be worth almost nothing) and wrong on which variable
would decide the outcome. Recorded as such.

### 8.8 What this lane does NOT license

- It does not say eFV is worse than the consensus. The point estimate is ahead on every
  basis tested, on 3,234 rows.
- It does not say the consensus should be reweighted. Zero weights ship, unchanged.
- It does not retire the head-to-head statistic. It says the statistic is **underpowered
  for the claim being made on it**, which B-L1 already established (refit share of
  variance 0.128, E_refit floor asymptote 0.0123 at infinite test n).
- It is **not vintage-disciplined** (section 4) and must never be quoted as out-of-sample.
