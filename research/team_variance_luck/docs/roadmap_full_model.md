# Full-model roadmap

The current package is an ELO-facing interface. It establishes a validated,
team-level export contract before the full rebuild pipeline exists.

Later work under `team_variance_luck/core/` will add reproducible components:

- `injury_context.py`
- `luck_model.py`
- `variance_model.py`
- `team_aggregation.py`
- `exports.py`

Health- and injury-heavy rebuild dependencies will remain optional for ELO
consumers. The exported ELO schema should remain backward compatible; additions
or semantic changes should use explicit versioning and migration notes.
