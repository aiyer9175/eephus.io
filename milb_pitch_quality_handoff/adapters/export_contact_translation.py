#!/usr/bin/env python3
"""Read-only export adapter: MiLB rate-skill translation (contact-portability substitute).

See ../definitions/CONTACT_PORTABILITY.md for what this is and is not.

This adapter never recomputes a value. It reads the authoritative parquet
files as-is, validates required columns against
../contracts/contact_translation.schema.json, and writes the real data to a
private, non-git output location. It never re-derives, joins, or scores.

Configuration (env vars, all optional, defaults shown):
  EEPHUS_CAREER_OUTCOME_PLUS_DIR   default: ~/career_outcome_plus
  EEPHUS_HANDOFF_PRIVATE_OUT       default: ~/eephus_handoff_private_exports

Usage:
  python3 export_contact_translation.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "contracts" / "contact_translation.schema.json"

SOURCE_ARTIFACTS = {
    "latent_rate_talent": "data/latent_rate_talent.parquet",
    "milb_xwar_projection": "data/milb_xwar_projection.parquet",
}


def _source_dir() -> Path:
    return Path(os.environ.get("EEPHUS_CAREER_OUTCOME_PLUS_DIR", "~/career_outcome_plus")).expanduser()


def _output_dir() -> Path:
    out = Path(os.environ.get("EEPHUS_HANDOFF_PRIVATE_OUT", "~/eephus_handoff_private_exports")).expanduser()
    out = out / "contact_translation"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _validate(df, artifact_name: str, schema: dict) -> list[str]:
    """Return a list of human-readable validation problems; empty if none."""
    required = list(schema["artifacts"][artifact_name]["required_columns"].keys())
    problems = []
    missing = [c for c in required if c not in df.columns]
    if missing:
        problems.append(f"{artifact_name}: missing required columns {missing} (documented, not fabricated)")
    pk = schema["artifacts"][artifact_name]["primary_key"]
    if all(c in df.columns for c in pk) and df.duplicated(subset=pk).any():
        dup_count = int(df.duplicated(subset=pk).sum())
        problems.append(f"{artifact_name}: {dup_count} duplicate rows on primary key {pk}")
    return problems


def main() -> int:
    try:
        import pandas as pd
    except ImportError:
        print("pandas is required to run this adapter", file=sys.stderr)
        return 1

    schema = _load_schema()
    src_dir = _source_dir()
    out_dir = _output_dir()

    exit_code = 0
    for artifact_name, rel_path in SOURCE_ARTIFACTS.items():
        src_path = src_dir / rel_path
        if not src_path.exists():
            print(f"SKIP {artifact_name}: source not found at {src_path}", file=sys.stderr)
            exit_code = 1
            continue

        df = pd.read_parquet(src_path)
        problems = _validate(df, artifact_name, schema)
        for p in problems:
            print(f"WARN {p}", file=sys.stderr)

        out_path = out_dir / f"{artifact_name}.parquet"
        df.to_parquet(out_path, index=False)
        print(f"OK {artifact_name}: {len(df)} rows -> {out_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
