# C-1c: is the elite deflation a defect, or is eFV right? Pre-registration.

Pre-registered 2026-08-14 BEFORE any estimator was compared on the elite band.
Results section deliberately empty at commit so git timestamps this.

Opened on the owner's decision after C-1b aborted. C-1b asked "can a monotone map
calibrate the level without deflating the elite" and answered no. **This lane asks
the prior question C-1b assumed: SHOULD the elite be deflated at all.**

## The question, and why the earlier evidence cannot answer it

The affine correction serves Jesus Made at eFV 56.5 against a consensus of 60.8. Two
readings, and nothing measured so far separates them:

1. the correction is over-shrinking genuine elite talent, or
2. the model over-predicts at the top and the correction is right, so eFV is
   correctly disagreeing with scouts.

C-1b could not tell these apart because it measured on **14 active rows**. This lane
measures on the RESOLVED cohort, where realized WAR is known.

Available power, counted before any comparison was run:

| band | hit | pit | total |
| --- | --- | --- | --- |
| consensus_fv_raw >= 50 | 182 | 120 | **302** |
| consensus_fv_raw >= 55 | 73 | 29 | **102** |

Against 14. **PRIMARY band is >= 50** (302 rows). `>= 55` is reported as a
SECONDARY cut and is not permitted to carry the verdict on its own, because the
pitcher side is 29 rows there and 8 at >= 60.

## THE DEFECT IN THE CLAUSE THAT STARTED THIS, stated before measuring

The tail-MAE clause that failed the affine map, and that motivated C-1b, selects on
the **top decile of REALIZED WAR**. That is selection on the OUTCOME, and it is
biased in a direction that is knowable in advance.

Among rows whose realized WAR came out high, the predictor with MORE spread is
closer ON AVERAGE, for the same reason a stopped-clock beats a slow one twice a
day: conditioning on a high outcome preferentially selects rows where the
high-variance predictor guessed high. So an over-dispersed predictor will beat a
calibrated one on any metric computed inside an outcome-selected tail, whether or
not it is the better predictor.

**This means the +15.8% tail-MAE "failure" of the affine correction may be an
artifact of the selection rule rather than evidence that the correction hurts the
elite.** I am recording that BEFORE measuring, because if the result comes out
favourable to the correction it would otherwise look like a rationalisation
invented afterwards.

The corresponding unbiased cut is selection on **consensus FV**, which is fixed
before the outcome is observed. That is why the bands above are defined on
`consensus_fv_raw` and not on realized WAR.

## Estimand

On the elite band, out of fold, which estimator is closer to REALIZED first-6-season
WAR:

    A  corrected eFV      max(-2, a_c + b_c * raw)      the shipped map
    B  uncorrected eFV    max(-2, raw)                  the incumbent before tonight
    C  consensus-implied  the pooled outcome curve read forward at consensus_fv_raw

C is included because it is the thing the owner's question compared against. If
consensus beats BOTH eFV arms on the elite band, the interesting finding is about
eFV at the top generally, not about the correction.

## Metrics, declared with their direction

- **Primary: MAE against realized WAR**, per arm, on the primary band. Lower wins.
- **Secondary: bias (mean signed error)**, which is the quantity the owner actually
  observed. A negative bias means the arm reads BELOW what those players produced.
- **Tertiary: Spearman** against realized WAR within the band, for ordering.
- Paired bootstrap over players, B = 2000, seed 7, for A vs B on the primary metric.

## Decision rule, declared in advance

1. **If A beats B on MAE with a paired CI95 excluding 0**: the deflation is
   CORRECT. The elite complaint is resolved as "eFV is disagreeing with scouts and
   is right to", the correction stays, and the glossary says so in those terms.
2. **If B beats A with a paired CI95 excluding 0**: the deflation is a genuine
   defect at the top. The correction is referred for reversion or for a gated
   band-limited variant, with this lane as the evidence.
3. **If the CI covers 0**: NULL. Neither reading is supported, the correction stays
   by the C-1b abort default, and the copy discloses that the top of the board is
   the least resolved part of the model. A null is a real outcome here and is NOT
   to be reported as a win for the incumbent.

## Controls

- **Sanity control**: on the FULL pool (not the elite band) A must beat B on MAE.
  That is the effect the correction was fitted to produce, and it was already
  measured at -10.7% / -8.0%. If it does not reproduce here the harness is wrong
  and no band result may be read.
- **Outcome-selected replication**: recompute the SAME comparison on the top decile
  of realized WAR, the biased cut, and report both side by side. If A loses on the
  outcome-selected cut and wins on the consensus-selected cut, that is the selection
  effect made visible rather than argued.
- Bands are computed from `consensus_fv_raw`, which is a pre-decision quantity. No
  band may be defined on anything the model or the outcome produced.

## Abort conditions

- ABORT if the sanity control fails.
- ABORT if the primary band has fewer than 150 rows after the pool filters.
- No band, metric or decision rule may be added or changed after the first look.

## Results

(empty at pre-registration)
