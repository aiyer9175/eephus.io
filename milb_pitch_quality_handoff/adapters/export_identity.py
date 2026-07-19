#!/usr/bin/env python3
"""Read-only export adapter: player identity, with mandatory dob redaction.

See ../definitions/IDENTITY_SYSTEM.md and ../contracts/identity.schema.json.
Never joins to the team/affiliate/park mapping system (that system is
classified NOT_NEEDED -- reconstructable from the public MLB Stats API,
see reports/ARTIFACT_INVENTORY.md group D). Never fabricates an
effective-dating column that doesn't exist upstream.

Redaction (unconditional, not configurable): the full `dob` column is
replaced with `birth_year` before export.

Env vars (optional):
  EEPHUS_CAREER_OUTCOME_PLUS_DIR   default: ~/career_outcome_plus
  EEPHUS_HANDOFF_PRIVATE_OUT       default: ~/eephus_handoff_private_exports
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "contracts" / "identity.schema.json"


def source_path() -> Path:
    base = Path(os.environ.get("EEPHUS_CAREER_OUTCOME_PLUS_DIR", "~/career_outcome_plus")).expanduser()
    return base / "data" / "eephus_identity.parquet"


def output_path() -> Path:
    out_dir = Path(os.environ.get("EEPHUS_HANDOFF_PRIVATE_OUT", "~/eephus_handoff_private_exports")).expanduser() / "identity"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "eephus_identity_redacted.parquet"


def _redact(df):
    if "dob" in df.columns:
        df = df.copy()
        df["birth_year"] = df["dob"].astype("string").str.slice(0, 4).astype("Int64")
        df = df.drop(columns=["dob"])
    return df


def main() -> int:
    try:
        import pandas as pd
    except ImportError:
        print("pandas is required to run this adapter", file=sys.stderr)
        return 1

    with open(SCHEMA_PATH) as f:
        contract = json.load(f)

    src = source_path()
    if not src.exists():
        print(f"SKIP identity: source not found at {src}", file=sys.stderr)
        return 1

    df = pd.read_parquet(src)

    dup_count = int(df.duplicated(subset=["mlbam_id"]).sum())
    if dup_count:
        print(f"WARN identity: {dup_count} duplicate mlbam_id rows in source -- collision handling upstream is undocumented, see definitions/IDENTITY_SYSTEM.md", file=sys.stderr)

    df = _redact(df)

    missing = [c for c in contract["required_columns"] if c not in df.columns]
    if missing:
        print(f"WARN identity: missing required columns (documented, not fabricated): {missing}", file=sys.stderr)

    if "dob" in df.columns:
        print("ERROR identity: dob column survived redaction -- refusing to export", file=sys.stderr)
        return 1

    out = output_path()
    df.to_parquet(out, index=False)
    print(f"OK identity: {len(df)} rows (dob redacted to birth_year) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
