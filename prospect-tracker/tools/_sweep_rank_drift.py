# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Characterise baked-vs-live board rank drift: real re-ranking or tie churn?

The board basis moved to xfv_grade and W-SIDESCALE was enabled on 2026-07-25, so
SOME drift against the last box bake is expected and is exactly what the golden
restamp is owed for. What matters is WHICH kind:

  * drift among players who share an identical grade is TIE CHURN. With thousands
    of actives pinned at the FV floor the tiebreak is arbitrary, so a basis change
    reshuffles them without any ranking claim changing. Benign.
  * drift among players with DISTINCT grades is real re-ranking, and it is what the
    movement engine would publish as player movement.

The second number is the one that decides whether the epoch gate is holding.
Read-only.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_board_scale as bs        # noqa: E402
import storage                      # noqa: E402
import json                         # noqa: E402

DATA = ROOT / "data"


def main() -> int:
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    act = {k: v for k, v in (doc.get("by_player") or {}).items()
           if (v or {}).get("kind") == "active"}
    rows = sorted(((bs.board_value(v), k) for k, v in act.items()
                   if bs.board_value(v) is not None), key=lambda r: (-r[0], r[1]))
    live = {k: i + 1 for i, (_v, k) in enumerate(rows)}
    val = {k: v for v, k in rows}

    con = sqlite3.connect(f"file:{Path(storage.DB_PATH)}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    d = con.execute("SELECT MAX(snapshot_date) d FROM metric_snapshots "
                    "WHERE overall_rank IS NOT NULL").fetchone()["d"]
    baked = {r["player_key"]: int(r["overall_rank"]) for r in con.execute(
        "SELECT player_key, overall_rank FROM metric_snapshots "
        "WHERE snapshot_date = ? AND overall_rank IS NOT NULL", (d,))}
    con.close()
    print(f"baked snapshot date: {d}   n_baked {len(baked)}   n_live {len(live)}")
    print(f"BOARD_RANK_BASIS_EPOCH = {getattr(storage, 'BOARD_RANK_BASIS_EPOCH', '?')}")

    shared = [k for k in baked if k in live]
    # how many players share each grade -> tie mass
    tie = Counter(round(val[k], 4) for k in shared)
    tied = [k for k in shared if tie[round(val[k], 4)] > 1]
    distinct = [k for k in shared if tie[round(val[k], 4)] == 1]
    print(f"\nshared {len(shared)}: {len(tied)} sit on a SHARED grade (tie churn "
          f"possible), {len(distinct)} hold a UNIQUE grade")

    def report(name, keys):
        moved = [k for k in keys if live[k] != baked[k]]
        if not keys:
            print(f"  {name:34s} n=0")
            return
        big = [k for k in keys if abs(live[k] - baked[k]) > 25]
        print(f"  {name:34s} n={len(keys):5d}  moved {len(moved):5d} "
              f"({100*len(moved)/len(keys):5.1f}%)  |move|>25: {len(big):5d}")

    print("\nDRIFT BY TIE STATUS")
    report("shared-grade (tie churn)", tied)
    report("unique-grade (real re-rank)", distinct)

    print("\nDRIFT BY LIVE BOARD DEPTH")
    for lo, hi in ((1, 10), (11, 25), (26, 50), (51, 100), (101, 300),
                   (301, 1000), (1001, 99999)):
        seg = [k for k in shared if lo <= live[k] <= hi]
        report(f"live rank {lo}-{hi if hi < 99999 else 'end'}", seg)

    print("\nTOP-25 DETAIL (live vs baked)")
    for _v, k in rows[:25]:
        b = baked.get(k)
        print(f"  #{live[k]:<3d} {k:26s} grade {val[k]:6.2f}  baked "
              f"{b if b is not None else 'absent'}")

    tiegrades = [g for g, n in tie.most_common(5)]
    print("\nLARGEST TIE BLOCKS (grade: n players):",
          ", ".join(f"{g}:{tie[g]}" for g in tiegrades))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
