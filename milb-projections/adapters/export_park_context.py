#!/usr/bin/env python3
"""Read-only export adapter: MiLB park context (v2, authoritative).

Does NOT recompute park factors. Reads milb_park_factors_v2.parquet as-is
and writes an identical copy to a private output location, after validating
against ../contracts/milb_park_context.schema.json. This is deliberately a
pass-through, not a transformation -- see
../tests/test_park_context_compatibility.py, which asserts the export
matches the authoritative source exactly for the same model_version.

Env vars (optional):
  EEPHUS_MILB_PARK_REBUILD_DIR   default: ~/milb_park_rebuild
  EEPHUS_HANDOFF_PRIVATE_OUT     default: ~/eephus_handoff_private_exports
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "contracts" / "milb_park_context.schema.json"


def source_path() -> Path:
    base = Path(os.environ.get("EEPHUS_MILB_PARK_REBUILD_DIR", "~/milb_park_rebuild")).expanduser()
    return base / "data" / "milb_park_factors_v2.parquet"


def output_path() -> Path:
    out_dir = Path(os.environ.get("EEPHUS_HANDOFF_PRIVATE_OUT", "~/eephus_handoff_private_exports")).expanduser() / "park_context"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "milb_park_factors_v2.parquet"


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
        print(f"SKIP milb_park_context: source not found at {src}", file=sys.stderr)
        return 1

    df = pd.read_parquet(src)

    missing = [c for c in contract["required_columns"] if c not in df.columns]
    if missing:
        print(f"WARN milb_park_context: missing required columns (documented, not fabricated): {missing}", file=sys.stderr)

    pk = contract["primary_key"]
    if all(c in df.columns for c in pk) and df.duplicated(subset=pk).any():
        print(f"WARN milb_park_context: {int(df.duplicated(subset=pk).sum())} duplicate rows on {pk}", file=sys.stderr)

    inv = contract["invariants"]
    if inv.get("coverage_share_equals_1_0") and "coverage_share" in df.columns:
        if not (df["coverage_share"] == 1.0).all():
            print("WARN milb_park_context: coverage_share invariant violated", file=sys.stderr)
    if inv.get("weather_required_always_false") and "weather_required" in df.columns:
        if df["weather_required"].any():
            print("WARN milb_park_context: weather_required invariant violated", file=sys.stderr)

    out = output_path()
    df.to_parquet(out, index=False)
    print(f"OK milb_park_context: {len(df)} rows -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
