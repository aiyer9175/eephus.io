# Team Variance and Luck

This package exposes team-level luck, variance, and roster-health context
features for downstream ELO modeling. It is not currently connected to the
website or website build.

The current stable interface is the exported ELO feature table documented in
[`docs/elo_data_contract.md`](docs/elo_data_contract.md). Full model code will
be added later under `team_variance_luck/core/` without changing how ELO
consumers load the exported table.

The feature scope, owner, inputs, outputs, data dependencies, and definition of
done are recorded in [`docs/feature_spec.md`](docs/feature_spec.md).

From the repository root, make the package importable with:

```bash
export PYTHONPATH="$PWD/research/team_variance_luck:$PYTHONPATH"
```

Then load a validated export:

```python
from team_variance_luck.load import load_elo_features

df = load_elo_features(
    "research/team_variance_luck/artifacts/team_luck_elo_features.parquet"
)
```

To produce an ELO-safe export from an internal CSV or Parquet table:

```bash
python research/team_variance_luck/scripts/export_for_elo.py \
  --input path/to/internal_output.parquet \
  --output research/team_variance_luck/artifacts/team_luck_elo_features.parquet
```

Parquet input and output require an optional pandas Parquet engine such as
`pyarrow`. CSV loading and validation require only `pandas`.
