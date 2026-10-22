# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Freeze the core eWAR label vintage, data/ewar_core_label.json (written ONCE).

    python tools/build_ewar_core_label.py            # build and check, no write
    python tools/build_ewar_core_label.py --write    # write once; refuses other content

docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md part 3. Reads only the frozen fWAR
vintage and data/ewar_v3.json (for R2); never a feed. Every identity of part 3 is checked
before anything is written.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ewar_core_label as C   # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    try:
        payload = C.build(log=print)
    except C.EwarCoreLabelRefusal as e:
        print(f"REFUSED: {e}")
        return 2
    n_bat = sum(len(b["bat"]) for b in payload["seasons"].values())
    n_r2 = sum(len(b["pit_r2"]) for b in payload["seasons"].values())
    print(f"core eWAR label {payload['vintage_id']}: seasons {payload['first_season']} to "
          f"{payload['last_season']}, {n_bat} hitting departures, {n_r2} R2 departures "
          f"(content_sha256 {payload['content_sha256']})")
    if a.write:
        try:
            path, how = C.write(payload)
        except C.EwarCoreLabelRefusal as e:
            print(f"REFUSED: {e}")
            return 3
        print(f"{how}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
