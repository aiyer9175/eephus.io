# M4 pre-registration: consensus denoising (derive the shrinkage, do not fit a constant)

**Sections 0 through 6 of this document were written BEFORE the lab existed and BEFORE any
outcome statistic was computed.** Section 7 holds literal placeholders that the lab fills
in. This is the J1 protocol, adopted because it is the only lane in the 2026-08-07b program
whose pre-registration a verifier could confirm from the transcript.

Plan: `docs/master-plan-2026-08-08-efv-conviction.md` lane M4 and section 9.3.
Prior measurement this lane inherits: `docs/efv-2026-08-08/WAVE0_RECORD.md` sections 3, 4.

---

## 0. What is already known, so the lane cannot claim it

Wave 0 already identified the INPUTS with no labels. Those are not this lane's result and
must not be re-reported as one:

- Per-source noise, Sheppard-corrected, WITHIN year:
  2023 FG 2.585 / MLBP 2.440 / BA 3.236; 2024 2.565 / 2.660 / 3.113;
  2025 2.880 / 2.246 / 3.540; 2026 2.569 / 2.302 / 2.160.
- The cross-year POOLED estimate (BA 5.891, ratio 2.78) is an ARTIFACT of BA's 2026 basis
  change. It must not appear in any headline.
- Publisher coverage over 18,327 player-years: k=1 58.2%, k=2 35.6%, k=3 6.3%.
- FanGraphs-to-Pipeline offset drift 2017-2026: +4.175, +4.747, +4.222, +4.487, +4.165,
  +4.181, +3.903, +3.790, +3.312, +3.269 at SE 0.131-0.160. The drift question is CLOSED
  in the affirmative; this lane does not re-open it.

## 1. The defect this lane attacks

`consensus.py:166-167` sets `SINGLE_SOURCE_PRIOR = 35.0` and `SINGLE_SOURCE_K = 0.5`, both
hand-set and never fitted, firing on the k=1 regime that is 58.2% of player-years and about
63% of the live board. A single constant cannot be correct across coverage levels, because
the correct shrinkage is a function of how many publishers graded the player:

```
lambda_k = sigma_true^2 / (sigma_true^2 + sigma_pub^2 / k)
```

At sigma_true = 5 and the measured sigma_pub this is roughly 0.705 at k=1 against 0.877 at
k=3, so a player 15 FV above the mean should be predicted about 10.6 with one source and
about 13.2 with three. One constant is wrong for at least one of them.

## 2. Arms

| arm | description |
|---|---|
| **A0 incumbent** | `SINGLE_SOURCE_K = 0.5`, `SINGLE_SOURCE_PRIOR = 35.0`, equal source weights. THE NULL HYPOTHESIS, not the challenger. |
| **A1 precision** | Inverse-variance source weights from the within-year Sheppard-corrected sigma_s. |
| **A2 lambda_k** | Coverage-aware reliability shrinkage replacing the constant. |
| **A3 joint** | A1 + A2 + extremization `mu + gamma*(consensus - mu)`, gamma fitted JOINTLY with lambda_k. |
| **C1 zero-information** | Source labels permuted WITHIN each player's grade vector. |
| **C2 permuted-k** | The k covariate permuted across players. |
| **C3 no-shrink** | lambda = 1 everywhere. |

**A3 must fit gamma and lambda_k jointly or not at all.** Extremization runs in the
opposite direction from reliability shrinkage; fitting them separately double-counts.

## 3. The primary gate, and why it is NOT pooled delta-R^2

**Pre-registering a pooled delta-R^2 gate would be pre-registering a null.** The effect is
about 0.007 on the labeled frame against an MDE of about 0.054. It is also
under-credited there by roughly 3.6x relative to the served frame, because coverage
correlates with level.

PRIMARY: the interaction test. Regress

```
y ~ x_obs + x_obs * (k - k_bar)
```

and test the interaction coefficient. A non-zero interaction is the direct statement that
the correct shrinkage depends on coverage, which is what A2 claims. Design power at
n = 2,000 is about 78%.

SECONDARY, reported always, never used to ship alone: reference reconstruction (how well
an arm predicts the multi-source consensus from a single source), and OOS consensus
accuracy under M3's forward-chained protocol.

## 4. PASS clauses (all must hold to ship)

1. **P1 interaction.** The interaction coefficient differs from zero at the registered
   level under the estimator named in the result, with the permuted-k control (C2) inside
   its null band.
2. **P2 beats the incumbent.** A candidate arm beats A0 on reference reconstruction with a
   paired bootstrap CI excluding zero, resampled BY PLAYER, never by row.
3. **P3 zero-information control fails.** C1 must NOT reproduce the gain. If permuting
   source labels within a player reproduces it, there is no result.
4. **P4 does not degrade the baseline's own accuracy.** OOS consensus accuracy under M3's
   protocol must not fall by more than its own floor.
5. **P5 per-year stability.** The sign must hold in at least 3 of the 4 years with
   three-source coverage. **The lane must report the within-year sigma ratio beside every
   number, because it straddles the 1.25 bar (1.33 / 1.21 / 1.58 / 1.19) and in 2026
   Baseball America is the QUIETEST source.**
6. **P6 churn disclosed.** Live-board movement counted and reported at decision time
   whatever the verdict. Owner decision 4 is "ship if gated, disclose churn".

## 5. Controls, mandatory

Paired bootstrap resampling BY PLAYER with any refit inside the draw; the C1 and C2
permutation nulls above; effect averaged over the 4 available three-source years; and a
two-sided coverage check if a new floor is derived here.

## 6. Stop clauses, written before the answer is known

- If the within-year sigma ratio is below 1.25 in a majority of years, **A1 does not
  ship** regardless of its point estimate, and the lane records the bound.
- If P1 passes but P3 fails, the lane records a NULL and closes A2. It does not go looking
  for a different gate.
- If the interaction is significant but the served-frame effect is smaller than the
  live-board churn it would cause, the lane reports it and defers to the owner rather than
  shipping on a technicality.
- **No arm is promoted after the fact.** If A3 wins only under a specification not listed
  in section 2, that is a post-hoc finding and must be labelled one in the headline.

## 7. RESULTS (literal placeholders; the lab fills these in)

```
STATUS: NOT RUN
primary_interaction_t:        <PENDING>
primary_interaction_p:        <PENDING>
control_C2_permuted_k_band:   <PENDING>
control_C1_permuted_source:   <PENDING>
reference_reconstruction:     <PENDING>
per_year_sign:                <PENDING>
oos_consensus_delta:          <PENDING>
live_board_churn:             <PENDING>
VERDICT:                      <PENDING>
```

## 8. What this lane may NOT conclude

It may not conclude anything about outlet ACCURACY weighting, which is a different and
closed lane (reverted 2026-07-25, and only 2 of 8 outlets have resolvable history with
indistinguishable precisions). This lane weights by measured NOISE, estimated with no
labels and no outcomes, which is why it is admissible where the accuracy lane was not.
It also may not re-open the offset-drift question, which wave 0 closed.
