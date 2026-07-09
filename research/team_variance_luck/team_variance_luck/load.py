"""Load the stable ELO feature table from disk."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .schema import validate_elo_features


def load_elo_features(path: str | Path) -> pd.DataFrame:
    """Load CSV or Parquet ELO features and validate the public contract."""
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(source)
    elif suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(source)
    else:
        raise ValueError(f"Unsupported ELO feature format: {source.suffix or '<none>'}")
    return validate_elo_features(frame)
