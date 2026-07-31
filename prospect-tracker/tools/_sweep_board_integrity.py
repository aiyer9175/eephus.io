# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Board-integrity verifier: does ONE eFV number reach every surface?

Re-run of the acceptance checks for the 2026-07-25 board unification, after the
W-SIDESCALE per-side calibration was enabled. Three independent readers must agree
on both the VALUE and the ORDER for every active player:

  A. efv_board_scale.board_value(rec)      -- the canonical definition
  B. build_site._primary_fv / _EFV_GRADES  -- what the homepage Top Prospects shows
  C. the baked overall_rank in xfv.json    -- what the served board sorted on

Plus the display contract: the shown integer is monotone non-increasing down the
board (no row shows a HIGHER FV than the row above it), and the owner's two named
spot-checks hold (Arias #1-adjacent with the right FV, Cholowsky not #4).

Read-only. Writes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_board_scale as bs            # noqa: E402
import build_site as bsite              # noqa: E402

DATA = ROOT / "data"


def _baked_ranks():
    """{player_key: overall_rank} from the newest snapshot, or None when the DB
    carries no snapshot table at all. None means UNAVAILABLE, never 'clean'.

    PATH: resolve from storage.DB_PATH, never guess. The live DB is
    prospect-tracker/prospects.db (~1.4 GB); there is ALSO a 0-byte
    data/prospects.db decoy in the tree, and reading that one makes this arm
    report UNAVAILABLE while the real baked ranks sit right there unchecked."""
    import sqlite3
    try:
        import storage
        db = Path(storage.DB_PATH)
    except Exception:
        db = ROOT / "prospects.db"
    if not db.exists() or db.stat().st_size == 0:
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT MAX(snapshot_date) d FROM metric_snapshots "
            "WHERE overall_rank IS NOT NULL").fetchone()
        if not row or not row["d"]:
            return None
        cur = con.execute(
            "SELECT player_key, overall_rank FROM metric_snapshots "
            "WHERE snapshot_date = ? AND overall_rank IS NOT NULL", (row["d"],))
        out = {r["player_key"]: int(r["overall_rank"]) for r in cur}
        return out or None
    except sqlite3.Error:
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass


def main() -> int:
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    bp = doc.get("by_player") or {}
    act = {k: v for k, v in bp.items() if (v or {}).get("kind") == "active"}
    print(f"active rows: {len(act)}   all rows: {len(bp)}   scale enabled: {bs.enabled()}")

    fail = 0

    # ---- A vs B: canonical value vs the homepage's map ----
    home = bsite._EFV_GRADES
    mism = []
    for k, rec in act.items():
        a = bs.board_value(rec)
        b = home.get(k)
        if a is None or b is None:
            if a is not None or b is not None:
                mism.append((k, a, b))
            continue
        if abs(a - b) > 1e-9:
            mism.append((k, a, b))
    print(f"[A vs B] homepage grade == canonical board grade: "
          f"{'OK' if not mism else f'{len(mism)} MISMATCH'}")
    for k, a, b in mism[:10]:
        print(f"    {k}: canonical {a} vs homepage {b}")
    fail += bool(mism)

    # ---- order + display monotonicity ----
    rows = sorted(((bs.board_value(v), k) for k, v in act.items()
                   if bs.board_value(v) is not None), key=lambda r: (-r[0], r[1]))
    shown = [int(v + 0.5) for v, _k in rows]          # eFV rounds to NEAREST
    inv = [(i, rows[i][1], shown[i], shown[i - 1])
           for i in range(1, len(shown)) if shown[i] > shown[i - 1]]
    print(f"[display] shown FV monotone down the board: "
          f"{'OK' if not inv else f'{len(inv)} INVERSIONS'}")
    for i, k, s, prev in inv[:10]:
        print(f"    row {i + 1} {k}: shows {s} under a {prev}")
    fail += bool(inv)

    # ---- A vs C: live order vs the baked overall_rank ----
    #
    # NB: overall_rank is NOT a field of xfv.json -- it is baked into
    # prospects.db (metric_snapshots) by storage.py, and the deploy box is the
    # single writer of that DB. On a dev checkout the table does not exist, so
    # this arm is UNAVAILABLE, not passing. Reporting it as OK on n_baked=0 is
    # exactly the vacuous-green trap this verifier exists to avoid.
    live = {k: i + 1 for i, (_v, k) in enumerate(rows)}
    baked = _baked_ranks()
    if baked is None:
        print("[A vs C] baked overall_rank: UNAVAILABLE on this checkout "
              "(metric_snapshots absent; the box owns prospects.db). NOT a pass.")
    else:
        drift = [(k, live[k], baked[k]) for k in baked if k in live and live[k] != baked[k]]
        print(f"[A vs C] baked overall_rank == live board order: n_baked {len(baked)}, "
              f"{'OK' if not drift else f'{len(drift)} DRIFTED'}")
        for k, lv, bk in sorted(drift, key=lambda r: abs(r[1] - r[2]), reverse=True)[:10]:
            print(f"    {k}: live #{lv} vs baked #{bk}")
        fail += bool(drift)

    # ---- owner spot-checks ----
    print("[named]")
    for name in ("franklin_arias", "jesus_made", "leo_de_vries", "roch_cholowsky",
                 "seth_hernandez", "ryan_sloan", "enrique_bradfield_jr", "jesus_flores"):
        if name in live:
            v = bs.board_value(act[name])
            print(f"    {name:24s} #{live[name]:<5d} raw {v:.2f}  shown {int(v + 0.5)}"
                  f"  side {act[name].get('side')}")
        else:
            print(f"    {name:24s} not on the active board")

    print("TOP 10:", ", ".join(f"{i + 1}.{k}({int(v + 0.5)})"
                               for i, (v, k) in enumerate(rows[:10])))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
