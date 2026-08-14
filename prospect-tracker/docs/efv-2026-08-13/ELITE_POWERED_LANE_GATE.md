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

Measured 2026-08-14, `tools/efv_elite_band_lab.py 2000`, artifact
`data/xfv_elite_band_eval.json`, forward-chained on `SCORED_YEARS`.

### An ambiguity in my own abort condition, resolved against myself

The gate says "ABORT if the primary band has fewer than 150 rows" and does not say
whether that is per side or overall. Measured: **hit 165, pit 110**, total 275.

Read as a total it passes; read per side the pitcher arm fails. I am NOT taking the
reading that lets the lane report: the pitcher primary band is treated as
**UNDERPOWERED**, its result is reported but may not carry a verdict, and the
hitter band (165) carries the primary result. The next registration writes the
threshold per side.

### Sanity control PASSES

On the full pool the correction beats uncorrected decisively, reproducing the
effect it was fitted to produce:

| side | A corrected MAE | B uncorrected MAE | paired A-B | CI95 | favours |
| --- | --- | --- | --- | --- | --- |
| hit | 2.2870 | 2.5657 | **-0.2787** | [-0.334, -0.224] | A |
| pit | 1.6288 | 1.7702 | **-0.1415** | [-0.173, -0.109] | A |

Both exclude zero. The harness measures what it claims to.

### PRIMARY: on a consensus-selected elite band the correction does NOT hurt

| band | n | A MAE | B MAE | paired A-B | CI95 | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| hit cons >= 50 | 165 | **7.2986** | 7.7319 | -0.4333 | [-0.933, +0.061] | NULL |
| pit cons >= 50 | 110 | **4.9171** | 5.1339 | -0.2168 | [-0.561, +0.138] | NULL (underpowered) |
| hit cons >= 55 | 70 | **8.6306** | 8.6829 | -0.0523 | [-1.060, +0.882] | NULL |
| pit cons >= 55 | 27 | **5.8865** | 6.5011 | -0.6146 | [-1.618, +0.391] | NULL |

**Decision rule branch 3: NULL.** The CI covers zero on every band. Per the
pre-registration this is a real outcome and is NOT a win for the incumbent.

But note the direction: the corrected arm is nominally BETTER on all four bands,
never worse. Whatever the elite deflation is, **it is not visible as damage to
predictive accuracy on a band chosen before the outcome was known.**

### THE PRE-REGISTERED SELECTION EFFECT IS CONFIRMED, and it is large

The same comparison on the BIASED cut, the top decile of realized WAR, the rule the
original tail-MAE clause used:

| cut | side | paired A-B | CI95 | favours |
| --- | --- | --- | --- | --- |
| consensus >= 50 (unbiased) | hit | -0.4333 | [-0.933, +0.061] | neither |
| **realized top decile (biased)** | hit | **+1.1890** | **[0.832, 1.526]** | **B** |
| consensus >= 50 (unbiased) | pit | -0.2168 | [-0.561, +0.138] | neither |
| **realized top decile (biased)** | pit | **+0.5340** | **[0.377, 0.683]** | **B** |

The correction loses RESOLVABLY on the outcome-selected cut and does not lose at
all on the pre-decision cut, on both sides. This is exactly the pattern the gate
predicted in advance and the reason the prediction was written down first.

**Consequence: the tail-MAE clause that failed the affine map, and that motivated
the whole of C-1b, was measuring a selection artifact rather than a defect.**
Conditioning on a high realized outcome preferentially selects rows where a
high-variance predictor guessed high, so the over-dispersed arm wins there by
construction. The clause should never have been promoted to gating in C-1b on that
evidence, and C-1b's clause 2 is retrospectively unsound. Its ABORT still stands,
because clause 3 (elite inversion) failed independently of clause 2.

### A finding this lane was not looking for: consensus beats eFV on elite hitters

On the hitter primary band, `C_consensus` is the best arm on BOTH metrics:

    C_consensus   MAE 6.9850   rho +0.3400
    A_corrected   MAE 7.2986   rho +0.2991
    B_uncorrected MAE 7.7319   rho +0.2991

That is the branch the gate flagged in advance: if consensus beats both eFV arms,
the finding is about eFV at the top generally, not about the correction. It does
NOT hold on pitchers, where consensus is the worst arm on MAE (5.3381 against A's
4.9171). Recorded as an open question with its own power, not adjudicated here.

### Bias, which is the quantity the owner actually saw

| band | A bias | B bias | C bias |
| --- | --- | --- | --- |
| hit cons >= 50 | **-1.33** | +1.78 | -0.56 |
| pit cons >= 50 | -2.52 | **-0.74** | +1.34 |

On elite hitters the corrected arm is LESS biased in absolute terms than the
uncorrected one (1.33 against 1.78), in the opposite direction. On elite pitchers
the uncorrected arm is less biased. So "the correction pushes the elite down" is
true as a statement about the served grade and is NOT true as a statement about
error against outcomes on the hitter side.

### What ships

Nothing changes. The correction stays, now on evidence rather than on the C-1b
abort default: it is not measurably worse at the top on any pre-decision band, and
the clause that said it was has been shown to select on the outcome.

Two things are owed to the reader and are NOT resolved here: the top of the board
remains the least resolved part of the model (every elite band returns NULL), and
consensus outperforming both eFV arms on elite hitters deserves its own lane.
