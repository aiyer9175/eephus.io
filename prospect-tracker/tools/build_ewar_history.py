# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Build the eWAR history record (docs/ewar/EWAR_HISTORY_GATE.md; task
EWAR_BACKGRADE_HISTORY).

    python tools/build_ewar_history.py            # build and print the report, write nothing
    python tools/build_ewar_history.py --write    # write data/ewar_history.json

Reads the frozen fWAR vintage (data/fwar_vintage.json) and data/ewar_v3.json; fetches
nothing. Writes one file: the season stamps, the groups, the identities' results and
the CORE-versus-FULL gap report per season and part (no per-player row). A missed
identity refuses the build and nothing is written.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ewar_history as H   # noqa: E402


def report(payload: dict, log=print) -> None:
    log(f"eWAR history {payload['version']}: {payload['first_season']} to {payload['last_season']} "
        f"on fWAR vintage {payload['fwar_vintage_id']}")
    for g in payload["groups"]:
        log(f"  {g['text']}")
    log("  gap per part (wins): season side part: sd / max_abs / cells moved at 1dp (share) / "
        "Spearman CORE vs FULL (frame n)")
    for s, blk in payload["seasons"].items():
        for side in ("bat", "pit"):
            for part, g in blk["gap"][side].items():
                if not g["nonzero"]:
                    continue
                log(f"    {s} {side} {part}: {g['sd']:.4f} / {g['max_abs']:.4f} / {g['cells_moved_1dp']} "
                    f"({g['share_moved_1dp']:.1%}) / {g['spearman_core_full']} ({g['frame_n']})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    try:
        payload = H.build(log=print)
    except H.EwarHistoryRefusal as e:
        print(f"REFUSED: {e}")
        return 2
    report(payload)
    if a.write:
        print(f"written {H.write(payload)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
