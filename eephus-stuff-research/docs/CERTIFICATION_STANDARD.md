# Certification Standard

## Reproduction gate (Part AX)

Before extending any prior Eephus work, reproduce the foundational result it
depends on. A reproduction gate reports, in this exact shape:

```
EXPECTED:
OBSERVED:
ABSOLUTE DIFFERENCE:
RELATIVE DIFFERENCE:
TOLERANCE:
STATUS:        PASS | FAIL | BLOCKED
```

If a value cannot be reproduced, the status is `FAIL` or `BLOCKED` — never
silently continue using the inherited number. See
`src/eephus_research/certification/reproduction_gate.py`.

## Frozen baselines (Part AY)

Once a prior stage is certified, its outputs are frozen (checksummed,
manifest-recorded — `src/eephus_research/provenance/manifest.py`). Future
changes are compared against the frozen baseline and reported as deltas
using whichever of these is appropriate to the artifact:

```
ROWS Δ:   MEAN Δ:   TOTAL Δ:   MAX ABS Δ:   CORRELATION:   BYTE IDENTITY:
```

## Certification gates

Every research program in this repository ends with an explicit gate table,
each gate assigned exactly one status from:

```
PASS  PASS_WITH_FINDINGS  FAIL  BLOCKED  NOT_ATTEMPTED  NOT_IDENTIFIED
NOT_MEASURED  NOT_APPLICABLE  INSUFFICIENT_EVIDENCE  NEEDS_REVIEW
```

`src/eephus_research/certification/gates.py` provides the `Gate` and
`GateTable` types used to build these tables and render them consistently.

## No averaged certification (Part BA)

Some gates are **critical**. A failed critical gate blocks certification
regardless of how many other gates pass — `29/30 PASS` is not a
certification if the one failure is, say, "no train/test leakage." Critical
gates are marked explicitly in the gate table (`critical: true` in
`GateTable` entries) and `src/eephus_research/certification/gates.py`
refuses to compute or display an aggregate pass-rate number for a table that
contains any critical gate — aggregate pass-rates are exactly the mechanism
this rule exists to prevent.

## Reporting standard (Part BB)

Every research program ends with a machine-verifiable summary in this shape,
followed by detailed interpretation:

```
PROGRAM:
VERDICT:

DATA:
OBSERVATIONS:
PLAYERS:
SEASONS:

PRIMARY ENDPOINT:
RESULT:

COMPUTATIONAL VALIDITY:
STATISTICAL VALIDITY:
CONSTRUCT VALIDITY:
PRODUCTION READINESS:

TESTS:
CERTIFICATION:

BLOCKERS:

PRODUCTION FILES MODIFIED:
GITHUB MODIFIED:
```

`docs/PROGRAM_0_CERTIFICATION.md` is this program's instance of that report.

## Research / candidate / production states (Part BS)

Every model or artifact belongs to exactly one state:

```
EXPLORATORY  RESEARCH  CANDIDATE  CERTIFIED  PRODUCTION  RETIRED
```

Promotion between states requires the relevant gates to actually pass, not
just a decision to call it promoted — see `registry/decisions/` for how a
promotion decision is recorded once a future program reaches that point.

## Publication claim boundary (Part BT)

A public claim must never be stronger than the validation actually run
supports. If a model predicts outcome variation only among pitchers already
represented in training, the claim may not say it "measures intrinsic
pitcher skill that generalizes to new pitchers" — that specific sentence
requires unseen-pitcher (`PLAYER_TRANSPORTABLE`) evidence, per the
interpretation ladder in `STATISTICAL_GOVERNANCE.md`.

## Independent red-team pass (Part AW)

Before certifying a completed research program, a reviewer who did not build
it should receive the preregistration, mathematical contracts, code, test
outputs, empirical results, and claim registry, and be asked specifically:
*what is the strongest technically credible argument that this result is
invalid?* — not *does this look correct?* This program's own self-audit
(`PROGRAM_0_CERTIFICATION.md`, "Self-audit") is the closest available
substitute for a true independent red-team pass on Program 0 itself, since
Program 0 has no prior empirical claims to red-team, but the mechanism must
be used by every future program that does.

## Documenting failure (Part BU)

Failures are research outputs. When a gate fails: identify the precise
failure, preserve the supporting artifacts, distinguish an implementation
bug from a conceptual failure, and do not delete or overwrite the failed
experiment's record. A negative result belongs in `registry/experiments/`
with status reflecting what actually happened, not removed once superseded.
