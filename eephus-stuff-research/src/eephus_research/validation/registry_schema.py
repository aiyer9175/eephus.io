"""Validates registry/ entries (claims, decisions, experiments, datasets) against schemas/*.schema.json.

This is what makes "missing required provenance" (a dataset entry missing
its checksum, a claim missing evidence, ...) fail loudly at validation time
instead of silently at read time three steps downstream.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"


def load_schema(schema_name: str) -> dict[str, Any]:
    """schema_name e.g. 'claim.schema.json', 'decision.schema.json', 'experiment.schema.json', 'dataset.schema.json'."""
    path = _SCHEMA_DIR / schema_name
    if not path.exists():
        raise FileNotFoundError(f"No such schema: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_registry_entry(entry: dict[str, Any], schema_name: str) -> None:
    """Raises jsonschema.exceptions.ValidationError if entry doesn't satisfy the named schema."""
    schema = load_schema(schema_name)
    jsonschema.validate(instance=entry, schema=schema)


def validate_registry_file(path: str | Path, schema_name: str) -> None:
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        entry = yaml.safe_load(fh) if p.suffix in (".yaml", ".yml") else json.load(fh)
    validate_registry_entry(entry, schema_name)
