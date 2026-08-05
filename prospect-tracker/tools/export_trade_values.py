"""Regenerate data/trade_values.json on its own, without a full rebuild_only.

WHY THIS EXISTS. Until 2026-08-05 the only caller of
bayes_trade_value.export_trade_values_json was run_monthly's rebuild_only path
(run_monthly.py:986-1006), so the only supported way to refresh the trade board
was to re-run consensus, the full site export, the eFV regen and the GRPO
retrain alongside it. That is the right coupling on a pipeline night and the
wrong one after a change that moves ONLY the projection inputs: the surplus
basis moves, the board goes stale against /projections/, and the cross-surface
consistency guard (test_calibration_vintage) goes red with no cheap way to fix
it.

TWO PASSES, ALWAYS. bayes_trade_value.apply_platform_surplus re-points served
rows at the platform surplus, and that re-point reads artifacts the first pass
itself rewrites, so a single pass leaves the board one step behind. This is the
same two-pass rule the value-framework runbook states for any basis change.

The player set mirrors rebuild_only exactly: timeseries.json plus the optional
debuts.json and graduates.json sidecars. graduates.json has no producer in this
repo, so its absence is normal and is logged rather than raised (the 2026-07-31
lesson: `if exists()` made a missing declared input indistinguishable from an
empty one).

Usage:
    python tools/export_trade_values.py            # two passes, data/
    python tools/export_trade_values.py --passes 1 # diagnostic only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("export_trade_values")


def _load_players(data_dir: Path) -> tuple[list, dict | None]:
    ts_path = data_dir / "timeseries.json"
    if not ts_path.exists():
        raise SystemExit(f"missing {ts_path}; nothing to price")
    ts = json.loads(ts_path.read_text(encoding="utf-8"))
    players = list(ts.get("players") or [])
    log.info("timeseries.json: %d players", len(players))

    for sidecar in ("debuts.json", "graduates.json"):
        path = data_dir / sidecar
        if path.exists():
            rows = json.loads(path.read_text(encoding="utf-8"))
            players += rows
            log.info("%s: contributed %d rows", sidecar, len(rows))
        else:
            log.warning("%s ABSENT - no producer exists in this repo; the board "
                        "is built without it", sidecar)
    return players, ts.get("level_norms")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--passes", type=int, default=2,
                    help="2 is correct; 1 is a diagnostic that leaves the "
                         "platform re-point one step behind")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    data_dir = Path(args.data_dir)
    out_path = data_dir / "trade_values.json"

    from bayes_trade_value import export_trade_values_json, _reset_cache

    players, level_norms = _load_players(data_dir)
    if args.passes < 2:
        log.warning("running %d pass(es): the platform surplus re-point needs "
                    "TWO to settle", args.passes)

    n = 0
    for i in range(1, max(1, args.passes) + 1):
        _reset_cache()
        n = export_trade_values_json(players, out_path, level_norms=level_norms)
        log.info("pass %d: exported %d players", i, n)

    log.info("wrote %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
