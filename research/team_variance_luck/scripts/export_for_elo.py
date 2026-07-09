#!/usr/bin/env python3
"""Export an internal team feature table through the stable ELO contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Permit direct execution from the repository root without installation.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from team_variance_luck.elo_features import select_elo_feature_columns


def _read_input(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(source)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(source)
    raise ValueError(f"Unsupported input format: {source.suffix or '<none>'}")


def export_for_elo(
    input_path: str | Path,
    output_path: str | Path,
    csv_output: str | Path | None = None,
) -> pd.DataFrame:
    """Validate an internal table and write canonical ELO exports."""
    output = Path(output_path)
    if output.suffix.lower() not in {".parquet", ".pq"}:
        raise ValueError("--output must be a Parquet path")

    exported = select_elo_feature_columns(_read_input(input_path))
    output.parent.mkdir(parents=True, exist_ok=True)
    exported.to_parquet(output, index=False)

    if csv_output is not None:
        csv_path = Path(csv_output)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        exported.to_csv(csv_path, index=False)

    return exported


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Internal CSV or Parquet input")
    parser.add_argument("--output", required=True, help="Canonical Parquet output")
    parser.add_argument("--csv-output", help="Optional canonical CSV output")
    args = parser.parse_args()

    exported = export_for_elo(args.input, args.output, args.csv_output)
    print(f"Exported {len(exported)} rows to {Path(args.output)}")


if __name__ == "__main__":
    main()
