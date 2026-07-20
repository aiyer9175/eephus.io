# Implementation Sequence

Phase 11. Converts the architecture into a one-module-at-a-time build order, per the charter's suggested pattern (Module → Validation → Consumer integration → Publication → Regression → next module), avoiding parallel implementation except where dependencies are genuinely independent (`MODULE_INTERACTION.md`'s confirmed DAG).

## Step 1: Module 1, independent path (GO, per `MODULE1_READINESS.md`)

1. Build Module 1's production pipeline (incremental `pitch_dataset_v2`, per `REFRESH_EXECUTION_PLAN.md`'s engineering gap).
2. Implement the output contract (`DATA_CONTRACTS.md`) and schema-validation test.
3. Build the PROSPX pitcher-card consumer (`CONSUMER_WIRING_PLAN.md`'s interim design) — new field, not replacing `stuff_plus_aaa`'s existing pill.
4. Consumer validation per `CONSUMER_VALIDATION.md`'s checklist.
5. Publish: glossary entry, model-registry entry (`verdict: "provisional"`), wire into `run_monthly.py --daily`, add to `deploy/publish_paths.txt`.
6. Regression tests pass; only then move to Step 2.

## Step 2: Module 2 (Arsenal Construction) — parallelizable with Step 1's later stages

Since Module 2 shares Module 1's raw input and has no dependency on Module 1's output (`MODULE_INTERACTION.md`), its pipeline can be built in parallel with Step 1. Its family-restricted reliability test (the open gap since Phase 1B) should run before any consumer work — per `CONSUMER_WIRING_PLAN.md`, no public consumer is recommended for Module 2 until that closes, so Step 2 stops at "internal infrastructure feeding Module 3," not a full publish cycle.

## Step 3: Module 3a/3b (Miss-Inducing Ability) — depends on Steps 1-2 for the decomposition, not for the raw whiff-rate estimate itself

The raw whiff-rate computation has no hard dependency and could ship even before Modules 1-2 are consumer-integrated; the stuff/mix/location *decomposition* is a value-add once Modules 1-2 exist. Sequence: ship the raw estimate first (own reliability already confirmed, Phase 1B), add the decomposition once Modules 1-2 are stable.

## Step 4: Module 4 (Ground-Ball Tendency) — parallelizable with Step 3

Depends on Module 1's movement output as a covariate, not on Module 3. Its own-reliability test (the named gap) is the required gate before any consumer work, mirroring Module 2's pattern.

## Step 5: Module 5 (Damage Suppression) — not scheduled

Remains research-only indefinitely, per `MODULE_INTERFACES.md`'s explicit no-production-interface decision. Not part of this sequence.

## Separately-tracked, not sequenced with the above: the `stuff_plus_aaa` reconciliation experiment

The data-source reconciliation and subsequent augmentation experiment (`STUFF_PLUS_RECONCILIATION.md`) is **not slotted into this sequence** — it's a separate engineering/research task with its own prerequisites (touching `stuff_plus_aaa`'s actual training code, out of this charter's authority to schedule). It can proceed independently of Steps 1-5 and should not block any of them.

## What must NOT happen in parallel

Per the charter's instruction ("avoid parallel implementation unless dependencies are completely independent"): Module 3's decomposition feature and Module 4 both depend on Module 1's output — building them simultaneously with Module 1 itself (not just with each other) risks building against a moving target. Module 1's independent path (Step 1) should reach "regression tests pass" before Modules 3's decomposition or Module 4 begin in earnest, even though their own basic pipelines could start earlier.

## Observed evidence / Inference / Speculation

The sequencing is Inference, directly derived from `MODULE_INTERACTION.md`'s confirmed dependency structure (Observed evidence) and `MODULE1_READINESS.md`'s split verdict. No new empirical claims are introduced.

## Future work

Steps 2 and 4's reliability-test gates are the two concrete pieces of *research* work (not engineering) still outstanding before this sequence can fully execute — flagged consistently since Phase 1B and not resolved by any of the four charters in this research program so far.
