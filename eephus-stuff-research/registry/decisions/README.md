# Decision registry

Research *choices*, not findings. One YAML file per decision, ID `D-NNN`
(zero-padded, 3+ digits), validated against `schemas/decision.schema.json`.
Status is one of `DECIDED | PROVISIONAL | BLOCKED | REJECTED | SUPERSEDED`.
Never delete or silently edit a past decision to change what it says — if a
later decision reverses it, create a new `D-NNN` with `supersedes` pointing
back, and update the old one's `status` to `SUPERSEDED` with
`superseded_by` pointing forward.

Current entries: `D-001` (workbench location), `D-002` (leftover
milb-pitch-quality-research/ folder), `D-003` (governance self-containment
vs. deferring to milb-projections/) — all three decided by the operator
during Program 0, 2026-08-16.
