# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Re-bake the served board ranks on the CURRENT data/xfv.json.

    python tools/rebake_board_ranks.py            # rewrite data/timeseries.json in place
    python tools/rebake_board_ranks.py --dry-run  # report how many ranks would move

Thin CLI over storage.rebake_board_ranks, which run_monthly.rebuild_only calls right after
efv_export.regen_all. Use it standalone when data/xfv.json was regenerated without a
rebuild (a lab re-score, a box repair) and the baked overall_rank must follow it. The
dry run touches nothing, including metric_snapshots.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--path", default=str(ROOT / "data" / "timeseries.json"))
    args = ap.parse_args(argv)
    import storage
    out = storage.rebake_board_ranks(Path(args.path), write=not args.dry_run,
                                     update_metric_snapshots=not args.dry_run)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
