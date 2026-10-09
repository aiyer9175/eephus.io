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

THE SLIM SIDECAR (owner answer M10-1, 2026-09-25). The PROSPX Transactions
Trade Audit and the debuted Trade value lead read nine fields per player from
the 4.9 MB board. write_slim_sidecar copies exactly those fields, with the
board's generated_at, to data/trade_values_slim.json beside it, and it is
written after the last pass from the file just written, so the two can never
disagree. run_monthly's rebuild path calls the same function after its own
export. The sidecar ships at data/ depth one, so both deploy consumers carry
it with every other data/*.json file (deploy/data_exclude.txt does not list it).

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

SLIM_NAME = "trade_values_slim.json"
# Exactly the fields prospx/index.html reads off a trade-value row: the pricer
# (_taBuildIndex / _taPriceParty) and the debuted lead (_dtvRow, which also
# checks mlbam_id). trade_value_lo / trade_value_hi are never copied.
SLIM_FIELDS = ("player_key", "mlbam_id", "player_name", "org", "status", "fv",
               "position", "surplus_source", "trade_value_mm")


def write_slim_sidecar(tv_path: Path | str, out_path: Path | str | None = None) -> int:
    """Write the slim Transactions sidecar from a written trade_values.json.

    Returns the number of rows written. out_path defaults to SLIM_NAME beside
    tv_path, so a caller that redirects the board redirects the sidecar too.
    """
    tv_path = Path(tv_path)
    out_path = Path(out_path) if out_path is not None else tv_path.parent / SLIM_NAME
    doc = json.loads(tv_path.read_text(encoding="utf-8"))
    rows = [{k: r.get(k) for k in SLIM_FIELDS} for r in (doc.get("players") or [])]
    slim = {
        "generated_at": doc.get("generated_at"),
        "source": tv_path.name,
        "fields": list(SLIM_FIELDS),
        "count": len(rows),
        "players": rows,
    }
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(slim, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out_path)
    log.info("wrote %s (%d rows)", out_path, len(rows))
    return len(rows)


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


#: The third output: the Trade Audit deal list trade_audit_export writes (W07).
DEALS_NAME = "trade_audit_deals.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--passes", type=int, default=2,
                    help="2 is correct; 1 is a diagnostic that leaves the "
                         "platform re-point one step behind")
    args = ap.parse_args(argv)

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
    write_slim_sidecar(out_path, data_dir / SLIM_NAME)
    # The Trade Audit's deal list (wiring W07), repriced on the board just written so
    # the Trade Machine's Comparable real trades panel and the PROSPX audit print one
    # value per party. It follows --data-dir like the sidecar; a dir without the
    # audit's inputs writes nothing.
    try:
        import trade_audit_export
        trade_audit_export.export(out_path=data_dir / DEALS_NAME, data_dir=data_dir,
                                  log=log.info)
    except Exception:
        log.exception("trade audit deals failed; the board and the sidecar are written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
