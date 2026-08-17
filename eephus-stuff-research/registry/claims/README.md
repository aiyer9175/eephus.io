# Claim registry

Every important research conclusion gets an ID (`C-NNN`) and a YAML entry
validated against `schemas/claim.schema.json`, with evidence linkage
(`artifact_refs`, `code_refs`, `dataset_refs`, `experiment_refs`) — no
important public-facing conclusion may exist without one. `claim_type` is
one of `DEFINITIONAL | MATHEMATICAL | EMPIRICAL | INTERPRETIVE |
OPERATIONAL`.

Current entries: `C-001`, a `DEFINITIONAL` claim from this program's own
repository archaeology (no fitted pitch-quality model exists yet). No
`EMPIRICAL` claims exist yet — Program 0 fits no models (see
`docs/PROGRAM_0_CERTIFICATION.md`, gate `P0-24`). The first empirical claims
belong to Stuff Research Program 1.
