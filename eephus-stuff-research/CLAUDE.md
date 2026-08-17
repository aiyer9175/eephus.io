# Operating contract for `eephus-stuff-research/`

This file governs every Claude Code session working inside this directory. It
is more durable than any single conversation — read it fresh each session
rather than trusting what a previous conversation summary says is true.

## J1 — Machine state beats conversational memory

Always inspect the relevant files and artifacts before asserting anything
about their contents or existence. Do not claim a dataset, script, test
result, or prior conclusion exists because a previous conversation (this
one's history, a memory file, a chat summary) said it existed. Re-check.
`docs/MACHINE_STATE.md` and `docs/REPOSITORY_INVENTORY.md` are themselves
snapshots that go stale — treat their contents as "true as of the date
recorded," not as current fact, and re-run the underlying commands if it
matters.

## J2 — Existing empirical claims require reproduction

Do not inherit a numeric result as truth merely because it appears in a
report, a registry entry, or a prior session's summary. Before depending on
it:

1. Confirm the originating artifact exists (file, manifest entry, registry
   entry with a real `artifact_refs` pointer).
2. Confirm its provenance is known (who/what produced it, from what inputs,
   with what configuration — `src/eephus_research/provenance/`).
3. Run the relevant reproduction gate (see `docs/CERTIFICATION_STANDARD.md`,
   Part AX) and confirm it passes.

If any of the three fail, the claim is not usable as-is. Mark it
`BLOCKED` or re-derive it; do not quietly continue using the inherited
number.

## J3 — No fabrication

Never invent: sample sizes, correlations, confidence intervals, test counts,
filenames, data coverage, historical results, benchmark values, model
scores, or git state. If something was not measured, say `NOT_MEASURED`. This
applies to numbers reported in chat exactly as much as numbers written to a
file.

## J4 — Unknown is an acceptable result

Use the explicit status vocabulary everywhere a result needs a status:

```
PASS  PASS_WITH_FINDINGS  FAIL  BLOCKED  NOT_ATTEMPTED  NOT_IDENTIFIED
NOT_MEASURED  NOT_APPLICABLE  INSUFFICIENT_EVIDENCE  NEEDS_REVIEW
```

Do not force every research question into PASS/FAIL. A well-reasoned
`INSUFFICIENT_EVIDENCE` is a better research output than a fabricated PASS.

## J5 — Production remains frozen

The following are production and are **read-only** from this directory,
without exception, unless a future program explicitly documents an
authorized promotion in `registry/decisions/`:

- `eephus.io`'s `main` branch and anything merged into it
- `defense-plus/`, `swing-plus/`, `milb-decision-plus/`, `playing-time-model/`,
  `xRV models/`, `advancement_pace/`, `milb-projections/`, `prospect-tracker/`
- `xwoba_model.pkl`, `NCAA 26 Averages S+.csv` at the `eephus.io` repo root

See `docs/DATA_GOVERNANCE.md` for the enforced boundary and
`registry/decisions/D-001.yaml` for why research still lives inside this
repository despite the freeze.

## J6 — No benchmark chasing

Do not repeatedly change feature sets, targets, filters, hyperparameters,
endpoints, or validation windows until a preferred conclusion appears. Any
material change made *after* seeing results must be registered as a POST_HOC
amendment to the relevant experiment in `registry/experiments/`, not silently
folded into a "cleaner" rerun.

## J7 — Separate observation from interpretation

Every major report must distinguish, as separate labeled sections:

- **Measured result** — the number, exactly as computed, with its uncertainty.
- **Statistical interpretation** — what the estimator and validation design
  license you to say about that number.
- **Baseball interpretation** — what a domain expert would conclude, and
  what competing explanations remain live.
- **Production implication** — what, if anything, this means for anything
  that ships. Usually "none yet."

## How to work in this repository

- Model tier policy (Fable for methodological adjudication, Opus as default
  research lead, Sonnet for well-specified implementation, Haiku for
  low-risk clerical work only) is a policy for the *human operator* choosing
  which Claude Code session/model to run — a single running session cannot
  self-escalate to a different underlying model. If a task in this repo
  clearly calls for methodological adjudication beyond what the current
  session should decide alone (see the escalation triggers below), say so
  explicitly and ask the operator to open a session with the appropriate
  model, rather than quietly deciding a foundational question yourself.
- **Escalate rather than improvise** on: an unidentified estimand, ambiguity
  in the target, unclear statistical dependence, uncertainty over
  train/test structure, conflicting mathematical definitions, a possible
  leakage mechanism, disagreement between independent implementations,
  unexplained benchmark superiority, unstable inference, an unexpected sign
  reversal, a result driven by a small number of players, a conclusion
  requiring causal interpretation, an important domain assumption lacking
  evidence, or any choice that materially changes the scientific conclusion.
  Record the escalation (a decision entry with status `BLOCKED`, or a note in
  the relevant report) — do not conceal it by silently choosing a plausible
  default.
- **Every experiment gets an ID before it runs.** See
  `docs/STATISTICAL_GOVERNANCE.md` and `registry/experiments/`.
- **Every consequential claim gets an ID.** See `registry/claims/` and
  `docs/CERTIFICATION_STANDARD.md`.
- **Every dataset gets an ID.** See `registry/datasets/`.
- **Learned transformations fit on training data only.** Use
  `src/eephus_research/validation/` helpers rather than hand-rolled
  `fit`/`transform` calls — they exist specifically to make full-dataset
  fitting hard to do by accident (Part AG).
- **No critical certification gate is average-able away.** 29/30 passing
  gates does not certify anything if the failed gate is critical. See
  `docs/CERTIFICATION_STANDARD.md`.
- **Do not fit, tune, select, or evaluate a Stuff/pitch-quality model from
  this repository's current state.** That is explicitly out of scope until a
  future program (Stuff Research Program 1) starts it deliberately.

## Session continuity

This filesystem — not any conversation transcript — is the canonical research
record. At the start of a session, reconstruct state from `docs/`,
`registry/`, `data/manifests/`, and recent `git log`, rather than relying
primarily on remembered chat context. See `docs/BEGINNER_OPERATIONS.md` for
exact commands.
