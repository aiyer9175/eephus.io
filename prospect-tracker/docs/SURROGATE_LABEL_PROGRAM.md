# eFV Surrogate-Label Program (scoping, 2026-07-24)

The 2026-07-24 data-sourcing program established that no public source lifts eFV,
because the binding constraint is structural: the **label-horizon trap**. The
cohorts with the best features (2019-2024, plus every Statcast/measurement source)
have censored or unresolved 6-year WAR labels; the cohorts with resolved labels
(2011-2018) predate the good features. Two experiments (MiLB backfill, TJ surgery)
confirmed that feature-filling does not escape this. This document scopes the lever
that does: replacing the slow 6-year label with fast-resolving surrogates.

## Why it works (measured, not asserted)

On the 463 resolved debuted hitters, a short-horizon surrogate already carries
almost all of the target's rank information:

| surrogate | Spearman vs first-6yr WAR | resolves in |
|---|---|---|
| WAR through debut + 2 seasons | **0.742** | ~2 years |
| WAR through debut + 3 seasons | **0.880** | ~3 years |
| first-6yr WAR (the current target) | 1.000 | ~6 years |

A 3-year surrogate recovers 88% of the rank signal in half the time. There are
**833 censored debuted rows** (382 hitters + 451 pitchers) that currently ride on a
KM rate-projection assumption; a 3-year surrogate would replace that assumption with
observed outcome for every 2021-2023 debut, roughly doubling the *resolved,
feature-rich* training sample two-to-three years sooner than the 6-year target
allows. That is the entire game: the modern featured cohorts become trainable now.

## The design: a two-stage label

Stage 1 (deep historical, already available): fit **surrogate -> first-6yr WAR** on
the resolved 2011-2018 cohorts. This is the calibration map that turns a 3-year
outcome into a 6-year-WAR-equivalent. It is a small, stable regression (the table
above is its univariate core; the real map adds age, level, and role).

Stage 2 (modern shallow window): the eFV feature model is trained against the
**surrogate-derived WAR-equivalent** for the 2019-2023 cohorts (observed 2-3 season
outcome mapped through Stage 1), and against the true 6-year WAR for 2011-2018. Both
label types coexist with a source indicator and a variance weight (surrogate labels
carry the Stage-1 residual variance, so they are down-weighted, not treated as exact).

This is strictly more information than today's design, which throws the 2021-2023
cohorts into a rate-projection guess or right-censors them out of the clean cut.

## Surrogate ladder (by how far a prospect has progressed)

The 3-year-WAR surrogate only applies once a player has debuted. The full ladder,
coarsest to finest, lets every population contribute a resolvable outcome sooner:

1. **Reached MLB (y/n)** and **accumulated 200 MLB PA/BF** - resolves in 2-4 years
   from the prospect read; the coarsest survival signal, and the one that
   distinguishes a washout (observed 0) from a censored A-baller (unobserved). This
   is the survival-analysis backbone the injury-history ledger already needs.
2. **Survived to Double-A / reached AAA** - a pure-MiLB surrogate that resolves
   without an MLB debut at all, so it labels the deep-minors population the 6-year
   target never sees in time.
3. **MLE performance at the next level** - the CollegeSavant / milb_translation
   machinery already estimates level-to-level translation; the realized next-level
   line is the surrogate, and it resolves in one season.
4. **WAR through 2-3 MLB seasons** (the 0.880 map above) - the finest surrogate, for
   debuted players.

Each rung is a separate Stage-1 map to first-6yr WAR; a prospect is labeled by the
finest rung that has resolved for them.

## What the data-sourcing program contributes here

The surrogate program is label engineering, not a scrape, but three verified sources
from this session feed it directly:

- **Transaction / release / retirement data** (StatsAPI, already ingested) is the
  censoring backbone: it is what separates an observed washout (rung 1 = 0) from a
  censored still-active prospect. This is why Tier D was ranked a labeling
  dependency, not a feature.
- **MiLB level history** (the warmed 2005-2013 cache) gives rungs 2 and 3 their deep
  historical Stage-1 calibration window.
- **MLB Pipeline grade vintages** (the new open-GraphQL find) let Stage 2 read the
  pre-debut grade as-of the decision date without leakage, which matters more once
  the label resolves faster and the feature/label time gap shrinks.

## Phases + estimate

1. **Stage-1 maps** (~2 days): fit and cross-validate surrogate -> 6yr-WAR for each
   ladder rung on the 2011-2018 resolved cohorts; emit the maps + residual variances
   as a committed eval artifact (the model-audit house rule).
2. **Label assembly** (~2 days): extend `efv_dataset` to emit, per row, the finest
   resolved surrogate label + its WAR-equivalent + variance weight + a label-source
   indicator, alongside the existing resolved/censored targets. Leakage guard: the
   surrogate must resolve strictly after the feature decision date.
3. **Two-label training + gate** (~2 days): train the eFV models against the mixed
   label, forward-chained, and gate on the same both-metrics bar. The pre-registered
   win condition is a pooled OOS rank lift on the 2021-2023 test cohorts that today's
   censoring assumption cannot deliver.
4. **Backtest honesty** (~1 day): confirm the surrogate-trained model, evaluated
   against the *true* 6-year WAR on the 2011-2018 holdout, does not underperform the
   6-year-trained model there (the surrogate must add recent-cohort signal without
   costing old-cohort accuracy).

Total ~7 engineering-days. This is the highest-value eFV investment on the board:
unlike every source in the audit, it attacks the constraint that actually binds.

## Risks

- **Surrogate is not the target.** A 3-year peak can miss late-blooming WAR (the
  0.880 is strong but not 1.0). Mitigated by the variance weight and by keeping the
  true 6-year label for cohorts that have it.
- **Selection.** Reached-MLB is conditioned on org promotion decisions (private
  evaluation). That is a known confounder for every prospect model; the ladder's
  lower rungs (survived-to-AA, MLE) are less promotion-dependent and hedge it.
- **Double-counting.** A cohort must contribute either its true 6-year label or a
  surrogate, never both; the label-source indicator enforces this.

## Execution + gate (2026-07-24) - NO-SHIP, with a pitcher lead

Built (`efv_surrogate.py`, full-ladder Stage-1 maps + inverse-variance weights) and
gated via a production-mirroring simulation (`tools/efv_surrogate_lab.py`): map fit on
resolved 2011-2015, 2016-2018 stand in for the recently-censored cohorts, test on the
now-resolved 2019-2020 true first-6yr WAR. Three training arms: A = current KM censoring
label, B = 3yr-WAR surrogate, C = oracle (true labels). Gate = surrogate beats KM AND
recovers the oracle.

| side | KM (A) rho/mae | surrogate (B) | oracle (C) | verdict |
|---|---|---|---|---|
| hitters | 0.334 / 4.64 | 0.306 / 5.01 | 0.312 / 4.85 | NO-SHIP |
| pitchers | 0.122 / 2.56 | 0.125 / 2.53 | **0.226** / 2.55 | NO-SHIP |

Two findings. (1) HITTERS are at their label ceiling: even the oracle (perfect labels on
more cohorts) does not beat the current KM censoring, so no label engineering helps. The
surrogate itself is faithful (Spearman 0.874, MAE 2.37 vs true, better than KM's 2.52) -
the label is good, the model is just insensitive to it. (2) PITCHERS are the opposite:
the oracle nearly doubles rank (0.226 vs 0.122), so pitcher labels matter enormously - but
the 3-year-WAR surrogate is too noisy (0.768 vs true; pitcher WAR over 3 years is
role/injury-dominated) to capture it, so it only ties KM. And true labels are unavailable
for genuinely-censored cohorts by definition.

Disposition: NO-SHIP; `efv_surrogate.py` + the lab + `data/xfv_surrogate_eval*.json` kept
as the ledger; nothing wired into the shipped model.

**CORRECTION (2026-07-24, same day).** The pitcher row of the table above was read as "the
oracle proves the ceiling is real and large for arms," and a follow-up prototype was run on
that premise. It does not hold. A 13-agent adversarial program (docs/PITCHER_LABEL_LEDGER.md)
showed the pitcher oracle gap is substantially a MEASUREMENT ARTIFACT of this lab's small
unweighted eval: zero-information control labels (a constant, or pure noise) capture 87-113%
of the same "headroom", and a permutation null puts the oracle itself at p = 0.183. Under the
SHIPPED fit configuration (sample weights + the bust pool) a perfect pitcher label is worth
+0.0248 at production's real spans, and deleting the entire censored pitcher block moves the
served board by only 0.204 mean |dWAR| (top-50 churn 4). The pitcher-label lane is therefore
CLOSED on economic grounds, not merely unship-ed. The hitter row (oracle does not beat KM)
is unaffected and stands.

## Where this leaves eFV accuracy

Five label/feature experiments this program (MiLB backfill, TJ surgery, hitter surrogate,
pitcher surrogate, Pipeline grade vintages) all came back NO-SHIP. They converge on one
conclusion: the eFV hitter model is at its training-data ceiling - the consensus-anchored
blend does not improve from more or better-labeled cohorts. The remaining genuine eFV lever
is not data at all; it is the pitcher-label instrument above, which is a modeling problem,
not a sourcing one.
