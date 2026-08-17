# Experiment registry

Preregistration-oriented. Every experiment gets an ID (`E-NNN`) and a YAML
entry validated against `schemas/experiment.schema.json`, **written before
the experiment runs**. See `TEMPLATE.yaml` for the required fields and
`docs/STATISTICAL_GOVERNANCE.md` for what each field means and why it's
required.

No experiments have run yet — Program 0 is infrastructure only. The first
real entry (`E-001`) belongs to Stuff Research Program 1.

Once results have been inspected, any material change (feature set, target,
filters, split regime, etc.) must create either a new experiment ID or an
explicit `post_hoc_amendments` entry on the existing one. Never rewrite an
experiment's original preregistered fields after results are known — that
defeats the entire point of preregistration.
