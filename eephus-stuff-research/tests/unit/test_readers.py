from __future__ import annotations

import pytest

from eephus_research.io.readers import read_validated
from eephus_research.validation.schema import ColumnContract, SchemaContract, SchemaValidationError


def _schema() -> SchemaContract:
    return SchemaContract(
        name="t", version="1",
        columns=[ColumnContract("a", "int", is_key=True), ColumnContract("b", "float")],
    )


def test_read_validated_csv_passes_valid_data(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,1.5\n2,2.5\n")
    df = read_validated(f, _schema())
    assert len(df) == 2


def test_read_validated_csv_raises_on_schema_violation(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,1.5\n1,2.5\n")  # duplicate key
    with pytest.raises(SchemaValidationError):
        read_validated(f, _schema())


def test_read_validated_parquet_passes_valid_data(tmp_path):
    import pandas as pd

    f = tmp_path / "data.parquet"
    pd.DataFrame({"a": [1, 2], "b": [1.5, 2.5]}).to_parquet(f)
    df = read_validated(f, _schema())
    assert len(df) == 2


def test_read_validated_rejects_unsupported_extension(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("not tabular")
    with pytest.raises(ValueError, match="Unsupported extension"):
        read_validated(f, _schema())
