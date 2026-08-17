"""Schema-validated readers -- validation happens immediately on load, not sometime later.

Deliberately thin: production-quality data ingestion adapters are premature
for Program 0 (no dataset has been registered yet -- registry/datasets/).
This exists so a future program has one obvious place to load a CSV/parquet
through a SchemaContract instead of reading it raw.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from eephus_research.validation.schema import SchemaContract


def read_validated(path: str | Path, schema: SchemaContract) -> pd.DataFrame:
    p = Path(path)
    if p.suffix == ".csv":
        df = pd.read_csv(p)
    elif p.suffix in (".parquet", ".pq"):
        df = pd.read_parquet(p)
    else:
        raise ValueError(f"Unsupported extension '{p.suffix}' for {p}")
    schema.validate(df)
    return df
