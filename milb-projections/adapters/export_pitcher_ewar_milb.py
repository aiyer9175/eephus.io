#!/usr/bin/env python3
"""Read-only export adapter: MiLB pitcher eWAR (AAA, AA, High-A only).

Low-A is INTERNAL_ONLY (publication withheld per its own build ruling) and is
deliberately never read or exported by this adapter -- see
../PUBLICATION_POLICY.md and ../reports/ARTIFACT_INVENTORY.md.

Also exports the AAA Contact Management+ component
(aaa_contact_runs.parquet) for incremental-value testing.

See ../definitions/MILB_PITCHER_PROJECTION.md, ../definitions/AAA_CONTACT_PLUS.md,
../definitions/LOWER_LEVEL_PITCHER_COMPONENT.md.

Env vars (optional):
  EEPHUS_MILB_PITCHER_EWAR_DIR   default: ~/milb_pitcher_ewar
  EEPHUS_HANDOFF_PRIVATE_OUT     default: ~/eephus_handoff_private_exports
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "contracts" / "pitcher_ewar.schema.json"

# Deliberately excludes lowa_pitcher_ewar.parquet -- do not add it here
# without a documented change to the Low-A publication ruling.
LEVEL_ARTIFACTS = {
    "aaa": ("data/aaa_pitcher_ewar.parquet", "milb_pitcher_ewar_aaa"),
    "aa": ("data/aa_pitcher_ewar.parquet", "milb_pitcher_ewar_aa_higha"),
    "higha": ("data/higha_pitcher_ewar.parquet", "milb_pitcher_ewar_aa_higha"),
}

COMPONENT_ARTIFACTS = {
    "aaa_contact_management_plus": ("data/aaa_contact_runs.parquet", "aaa_contact_management_plus"),
}


def _source_dir() -> Path:
    return Path(os.environ.get("EEPHUS_MILB_PITCHER_EWAR_DIR", "~/milb_pitcher_ewar")).expanduser()


def _output_dir() -> Path:
    out = Path(os.environ.get("EEPHUS_HANDOFF_PRIVATE_OUT", "~/eephus_handoff_private_exports")).expanduser() / "pitcher_ewar_milb"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _export_one(df, name: str, contract_name: str, contract: dict, out_dir: Path) -> None:
    entry = contract["artifacts"][contract_name]
    missing = [c for c in entry["required_columns"] if c not in df.columns]
    if missing:
        print(f"WARN {name}: missing required columns (documented, not fabricated): {missing}", file=sys.stderr)
    pk = entry.get("primary_key", [])
    if pk and all(c in df.columns for c in pk) and df.duplicated(subset=pk).any():
        print(f"WARN {name}: {int(df.duplicated(subset=pk).sum())} duplicate rows on {pk}", file=sys.stderr)
    out_path = out_dir / f"{name}.parquet"
    df.to_parquet(out_path, index=False)
    print(f"OK {name}: {len(df)} rows -> {out_path}")


def main() -> int:
    try:
        import pandas as pd
    except ImportError:
        print("pandas is required to run this adapter", file=sys.stderr)
        return 1

    with open(SCHEMA_PATH) as f:
        schema = json.load(f)

    src_dir = _source_dir()
    out_dir = _output_dir()
    exit_code = 0

    for level_name, (rel_path, contract_name) in LEVEL_ARTIFACTS.items():
        src_path = src_dir / rel_path
        if not src_path.exists():
            print(f"SKIP {level_name}_pitcher_ewar: source not found at {src_path}", file=sys.stderr)
            exit_code = 1
            continue
        df = pd.read_parquet(src_path)
        _export_one(df, f"{level_name}_pitcher_ewar", contract_name, schema, out_dir)

    for out_name, (rel_path, contract_name) in COMPONENT_ARTIFACTS.items():
        src_path = src_dir / rel_path
        if not src_path.exists():
            print(f"SKIP {out_name}: source not found at {src_path}", file=sys.stderr)
            exit_code = 1
            continue
        df = pd.read_parquet(src_path)
        _export_one(df, out_name, contract_name, schema, out_dir)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
