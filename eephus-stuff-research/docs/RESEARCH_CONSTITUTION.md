# Research Constitution

The goal of this repository is not to maximize sophistication. It is to
maximize the probability that sophisticated mistakes are exposed before they
become Eephus conclusions.

A clean implementation is not sufficient. A high predictive score is not
sufficient. A familiar statistical method is not sufficient. A large dataset
is not sufficient. A famous benchmark is not ground truth. **Passing software
tests must never be treated as proof that a scientific claim is correct.**

Every claim in this repository must be certifiable against a four-layer
hierarchy. No lower layer implies a higher layer — passing Layer 1 says
nothing about Layer 2, and so on.

## Layer 1 — Computational correctness

**Question:** Did the code calculate what the specification says it should
calculate?

This is the only layer software tests can fully answer. Evidence:

- Unit tests (`tests/unit/`)
- Invariant tests — mathematical identities and conservation rules
  (`tests/invariants/`)
- Regression tests — previously verified outputs don't silently change
  (`tests/regression/`)
- Independent implementation — a second, differently-written implementation
  of the same formula, compared against the first (Part T)
- Deterministic reproduction — same inputs, same config, same seed produces
  byte-identical or numerically-identical output
- Conservation identities — where math implies `A = B + C`, test
  `A - (B + C) == 0` within a named tolerance, never `corr(A, B+C) ≈ 1`.
  Correlation is not reconciliation.

## Layer 2 — Statistical validity

**Question:** Does the estimator and validation design justify the empirical
claim?

Software tests cannot answer this on their own — a function can be computed
correctly and still be the wrong function to compute. Evidence:

- Sampling design and what population it generalizes to
- Clustering structure and whether it was accounted for
- Uncertainty quantification appropriate to the estimand
- Resampling / bootstrap where analytical uncertainty isn't available
- Validation architecture appropriate to the generalization claim being made
  (random row / game-grouped / pitcher-grouped / temporal — see
  `docs/STATISTICAL_GOVERNANCE.md`)
- Temporal and grouped holdouts, not just random splits
- Robustness analysis across reasonable alternative specifications
- Calibration, not just correlation or discrimination
- Simulation against a known data-generating process where feasible
- Sensitivity analysis against plausible alternative choices

## Layer 3 — Construct / scientific validity

**Question:** Does the quantity actually represent the baseball construct
claimed?

**This layer cannot be certified by software tests alone, ever.** It
requires human, domain-grounded judgment applied to:

- An explicit, written construct definition (what is this actually
  measuring, and what is it not measuring?)
- Falsification attempts — what observation would prove this construct
  wrong, and did anyone go look for it?
- Competing explanations — pitcher identity, role, velocity alone, park,
  selection effects, survivorship, tracking-source artifacts — ruled out,
  not just unmentioned
- Baseball-domain reasoning from someone who can sanity-check the output
  against what a scout or analyst would expect
- Transportability checks — does it mean the same thing across levels,
  seasons, organizations, tracking systems?
- Discriminant validity — does it actually differ from things it's supposed
  to be distinct from (e.g. is a "command" score actually distinct from raw
  strike rate)?
- Appropriate benchmarks, isolated per `docs/DATA_GOVERNANCE.md`'s benchmark
  classification, not folded silently into training

## Layer 4 — Production readiness

**Question:** Even if scientifically useful, is the system safe and stable
enough for operational use?

- Source stability (does the upstream data feed keep working the same way?)
- Coverage (is the population it can actually score representative of the
  population it's meant to describe?)
- Deterministic refresh (can it be re-run and produce the same thing?)
- Monitoring (will silent drift be noticed?)
- Schema guarantees (will an upstream change break it loudly, not silently?)
- Latency, if it needs to run on a schedule or serve requests
- Artifact contracts (are outputs versioned and content-addressable?)
- Rollback (can a bad promotion be undone?)
- Versioning of every scientific object that feeds it (Part BR)
- Publication rights, if the output or any input has licensing constraints

## How the layers interact with claims

Every claim registered in `registry/claims/` should be honest about which
layer(s) it has actually cleared. A claim that has only cleared Layer 1
("the code computes the formula correctly") must not be written up, spoken
about, or promoted as if it had cleared Layer 3 ("this measures pitch
quality"). See `docs/CERTIFICATION_STANDARD.md` for how this is enforced at
the gate level, and Part AV's interpretation ladder
(`OBSERVED → ASSOCIATED → PREDICTIVE_IN_SAMPLE → PREDICTIVE_OUT_OF_SAMPLE →
TEMPORALLY_TRANSPORTABLE → PLAYER_TRANSPORTABLE → MEASUREMENT_VALIDATED →
CAUSALLY_IDENTIFIED`) reproduced in `docs/STATISTICAL_GOVERNANCE.md`. Never
jump levels.
