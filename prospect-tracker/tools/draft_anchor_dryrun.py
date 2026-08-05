# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/draft_anchor_dryrun.py -- READ-ONLY validation of draft_anchor_backfill.

Opens prospects.db with sqlite `mode=ro` (the connection PHYSICALLY cannot
write) and monkeypatches storage.connect onto it, so nothing in this process
can touch the database even by accident. Then:

  1. runs the backfill's own pure-read find_candidates()
  2. reads each candidate's CURRENT explicit-FV snapshot rows
  3. re-runs consensus.build_timeseries BASELINE vs TREATED, where TREATED
     appends exactly the Snapshot rows draft_anchor_backfill.build(apply=True)
     would insert -- same source, date, interval_label, fv
  4. joins the served eFV artifact (data/xfv.json) for the downstream picture

Writes a JSON blob to stdout. Never writes to the DB or to data/.

Run: python tools/draft_anchor_dryrun.py > out.json
"""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_URI = "file:" + (ROOT / "prospects.db").as_posix() + "?mode=ro"


def _ro_connect():
    con = sqlite3.connect(DB_URI, uri=True, timeout=30.0)
    con.row_factory = sqlite3.Row
    return con


def _patch_storage():
    """Force every storage.connect() in this process onto a read-only handle."""
    import storage

    @contextmanager
    def _c():
        con = _ro_connect()
        try:
            yield con
        finally:
            con.close()

    storage.connect = _c


def main() -> None:
    _patch_storage()

    import consensus
    import draft_anchor_backfill as dab
    from scrapers import Snapshot

    cands = dab.find_candidates()
    keys = {c["player_key"] for c in cands}

    # --- current snapshot state for exactly these players -------------------
    con = _ro_connect()
    ph = ",".join("?" * len(keys))
    rows = con.execute(
        f"""SELECT source, snapshot_date, interval_label, player_key, player_name,
                   position, org, rank, fv, status, tools_json, fv_plus
              FROM snapshots WHERE player_key IN ({ph})""",
        sorted(keys),
    ).fetchall()
    con.close()

    import storage as _st
    base_snaps: list[Snapshot] = []
    for r in rows:
        d = dict(r)
        d["player_key"] = _st.canonical_player_key(d["player_key"])
        d["fv_plus"] = bool(d.pop("fv_plus", 0) or 0)
        d.pop("tools_json", None)
        base_snaps.append(Snapshot(**d, tools=None))

    # --- the rows the backfill WOULD write (verbatim from build(apply=True)) --
    try:
        from trades import canonical_org
    except ImportError:  # pragma: no cover
        def canonical_org(t):
            return t

    seeds = [
        Snapshot(
            source=dab.SOURCE_LABEL,
            snapshot_date=c["board_date"],
            interval_label=f"{c['draft_year']} Draft Class",
            player_key=c["player_key"],
            player_name=c["player_name"],
            position=None,
            org=canonical_org(c["team"]) or c["team"],
            rank=None,
            fv=float(c["fv"]),
            status="active",
        )
        for c in cands
    ]

    norm = consensus.ADOPT_NORMALIZED_CONSENSUS
    base_ts = {t.player_key: t for t in consensus.build_timeseries(list(base_snaps), normalize=norm)}
    treat_ts = {t.player_key: t for t in consensus.build_timeseries(base_snaps + seeds, normalize=norm)}

    def _latest(ts):
        if ts is None or not ts.points:
            return None
        p = ts.points[-1]
        return {
            "consensus_fv": p.consensus_fv,
            "consensus_fv_raw": p.consensus_fv_raw,
            "pre_shrinkage": p.consensus_fv_pre_shrinkage,
            "shrinkage_weight": getattr(p, "shrinkage_weight", None),
            "date": p.snapshot_date,
            "sources": sorted((p.per_source or {}).keys()),
        }

    served = (json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8")) or {}).get("by_player") or {}

    out = []
    for c in cands:
        k = c["player_key"]
        sv = served.get(k) or {}
        out.append({
            **c,
            "base": _latest(base_ts.get(k)),
            "treat": _latest(treat_ts.get(k)),
            "served_consensus_fv": sv.get("consensus_fv"),
            "served_xfv": sv.get("xfv_grade"),
            "served_surplus_mm": sv.get("surplus_mm"),
            "served_side": sv.get("side"),
            "served_kind": sv.get("kind"),
        })

    print(json.dumps({"n": len(out), "normalize": norm, "rows": out}, indent=1))


if __name__ == "__main__":
    main()
