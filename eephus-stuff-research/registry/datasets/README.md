# Dataset registry

Every research dataset (raw, external, or derived) gets an ID (`DS-NNN`) and
a YAML entry validated against `schemas/dataset.schema.json`. Derived
datasets list their parents via `raw_parent`, so provenance chains back to
an acquisition event rather than dead-ending at an unexplained file. See
`TEMPLATE.yaml` and `docs/DATA_GOVERNANCE.md`.

No datasets have been registered yet — Program 0 does not acquire or
transform any research data. The first entries belong to Stuff Research
Program 1. Note: the ~1 GB MiLB data cache documented in
`docs/REPOSITORY_INVENTORY.md` (`milb-pitch-quality-research/data_cache/`)
was deliberately **not** registered here (decision `D-002`) — it belongs to
an orphaned prior effort this program did not adopt.
