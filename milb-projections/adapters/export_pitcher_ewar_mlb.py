#!/usr/bin/env python3
"""Read-only export adapter: MLB pitcher eWAR (champion).

See ../definitions/PITCHER_EWAR.md. Reads the authoritative parquet as-is,
validates against ../contracts/pitcher_ewar.schema.json, writes to a private
output location. Never recomputes a value.

Env vars (optional):
  EEPHUS_PITCHER_EWAR_DIR      default: ~/pitcher_ewar
  EEPHUS_HANDOFF_PRIVATE_OUT   default: ~/eephus_handoff_private_exports
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "contracts" / "pitcher_ewar.schema.json"


def _source_dir() -> Path:
    return Path(os.environ.get("EEPHUS_PITCHER_EWAR_DIR", "~/pitcher_ewar")).expanduser()


def _output_dir() -> Path:
    out = Path(os.environ.get("EEPHUS_HANDOFF_PRIVATE_OUT", "~/eephus_handoff_private_exports")).expanduser() / "pitcher_ewar_mlb"
    out.mkdir(parents=True, exist_ok=True)
    return out


def main() -> int:
    try:
        import pandas as pd
    except ImportError:
        print("pandas is required to run this adapter", file=sys.stderr)
        return 1

    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    contract = schema["artifacts"]["mlb_pitcher_ewar"]

    src_path = _source_dir() / "data" / "pitcher_ewar.parquet"
    if not src_path.exists():
        print(f"SKIP mlb_pitcher_ewar: source not found at {src_path}", file=sys.stderr)
        return 1

    df = pd.read_parquet(src_path)

    missing = [c for c in contract["required_columns"] if c not in df.columns]
    if missing:
        print(f"WARN mlb_pitcher_ewar: missing required columns (documented, not fabricated): {missing}", file=sys.stderr)

    pk = contract["primary_key"]
    if all(c in df.columns for c in pk) and df.duplicated(subset=pk).any():
        print(f"WARN mlb_pitcher_ewar: {int(df.duplicated(subset=pk).sum())} duplicate rows on {pk}", file=sys.stderr)

    out_path = _output_dir() / "pitcher_ewar.parquet"
    df.to_parquet(out_path, index=False)
    print(f"OK mlb_pitcher_ewar: {len(df)} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
