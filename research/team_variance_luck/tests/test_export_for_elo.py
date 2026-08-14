from __future__ import annotations

import importlib.util

import pytest

from team_variance_luck.schema import REQUIRED_ELO_COLUMNS
from test_schema import valid_frame

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pyarrow") is None,
    reason="pyarrow is required to write the mandated Parquet export",
)


def test_export_selects_only_canonical_columns(tmp_path) -> None:
    from scripts.export_for_elo import export_for_elo

    source = tmp_path / "internal.csv"
    output = tmp_path / "nested" / "elo.parquet"
    csv_output = tmp_path / "nested" / "elo.csv"
    valid_frame().assign(safe_internal_note="drop me").to_csv(source, index=False)

    result = export_for_elo(source, output, csv_output)

    assert list(result.columns) == REQUIRED_ELO_COLUMNS
    assert output.exists()
    assert csv_output.exists()


def test_export_rejects_forbidden_columns(tmp_path) -> None:
    from scripts.export_for_elo import export_for_elo

    source = tmp_path / "internal.csv"
    valid_frame().assign(diagnosis="must not export").to_csv(source, index=False)

    with pytest.raises(ValueError, match="Forbidden"):
        export_for_elo(source, tmp_path / "elo.parquet")
