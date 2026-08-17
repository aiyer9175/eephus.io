# Model registry

Empty by design. Program 0 fits no models (see
`docs/PROGRAM_0_CERTIFICATION.md`, gate `P0-24`, critical). Once a future
program builds a candidate model, it gets a registry entry here recording
its state (`EXPLORATORY | RESEARCH | CANDIDATE | CERTIFIED | PRODUCTION |
RETIRED`, per `docs/CERTIFICATION_STANDARD.md`) and the claim/experiment/
dataset IDs it depends on. No schema exists yet for this registry — write
one (`schemas/model.schema.json`) when the first entry is needed, modeled on
the pattern in `schemas/claim.schema.json` and friends, rather than
speculatively building it now for a model that doesn't exist.
