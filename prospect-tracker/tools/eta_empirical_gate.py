# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ETA empirical-table gate lab (2026-08-19).

Registered gate: docs/eta-2026-08-19/ETA_EMPIRICAL_TABLE_GATE.md (clauses
frozen before this lab ran). Candidate: eta v40 = forward-chained empirical
per-level years-to-debut table where defined, champion heuristic fallback
everywhere else.

Clauses (see the gate doc for the frozen text):
  C1 row-matched MAE, player-clustered bootstrap MDE95 (B=2000, seed 20260819)
  C2 row-matched within-1y, CI95 excludes zero
  C3 pooled system (challenger-where-defined + champion-fallback) MAE on the
     full champion frame
  C4 overdue guardrail on the censored_active pool, limit +110 vs champion
  C5 leak check: table construction must be forward-chained (vintages < Y)

Read-only against the DB and caches; writes nothing except its own result
JSON to the path passed via --out (for the doc/eval merge step). It never
touches data/eta_eval.json itself.

Run (from prospect-tracker/):
  python tools/eta_empirical_gate.py --out <result.json>
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eta_backtest import (  # noqa: E402
    LAST_FULL_SEASON,
    VINTAGE_YEARS,
    _empirical_table,
    build_cohort,
)

SEED = 20260819
B = 2000
OVERDUE_LIMIT = 110  # frozen in the gate doc; v39 precedent was +101

ARTIFACT = Path(__file__).resolve().parent.parent / "data" / "eta_eval.json"


def _mae(pairs):
    return sum(abs(p - a) for p, a in pairs) / len(pairs)


def _w1(pairs):
    return sum(1 for p, a in pairs if abs(p - a) <= 1) / len(pairs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="write full result JSON here")
    args = ap.parse_args()

    rows, acct = build_cohort()
    deb = [r for r in rows if r["outcome"] == "debuted"]
    censored = [r for r in rows if r["outcome"] == "censored_active"]
    print(f"cohort: listed={acct['listed']} debuted={len(deb)} "
          f"censored_active={len(censored)} washed_out={acct['washed_out']}")

    # ── challenger tables, forward-chained exactly as eta_backtest builds them
    tables: dict[int, dict[str, float]] = {}
    for vy in VINTAGE_YEARS:
        t = _empirical_table([r for r in rows if r["vintage"] < vy])
        if t:
            tables[vy] = t

    # C5: construction is forward-chained by definition of the loop above
    # (train = vintages strictly < Y). Cross-check the re-derived tables
    # against the artifact of record.
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    art_tables = art.get("empirical_tables_by_vintage") or {}
    rederived = {str(k): {lv: float(v) for lv, v in tt.items()}
                 for k, tt in tables.items()}
    art_norm = {str(k): {lv: float(v) for lv, v in tt.items()}
                for k, tt in art_tables.items()}
    c5_match = rederived == art_norm
    c5_pass = c5_match  # forward-chained is structural; match is the check
    print("C5 LEAK CHECK: construction forward-chained (train = vintages < Y, "
          f"debuted-only, min_n=10); re-derived tables match artifact "
          f"empirical_tables_by_vintage: {c5_match} -> "
          f"{'PASS' if c5_pass else 'FAIL'}")

    def chall_pred(r):
        t = tables.get(r["vintage"])
        if t and r["level"] in t:
            return r["vintage"] + round(t[r["level"]])
        return None

    # ── C1 / C2: row-matched frame ─────────────────────────────────────────
    matched = [(r, chall_pred(r)) for r in deb]
    matched = [(r, cp) for r, cp in matched if cp is not None]
    champ_pairs = [(r["pred"], r["actual"]) for r, _ in matched]
    chall_pairs = [(cp, r["actual"]) for r, cp in matched]
    mae_c, mae_x = _mae(champ_pairs), _mae(chall_pairs)
    w1_c, w1_x = _w1(champ_pairs), _w1(chall_pairs)
    d_mae, d_w1 = mae_c - mae_x, w1_x - w1_c

    # player-clustered bootstrap (B=2000, seed 20260819)
    by_player: dict[str, list[tuple[int, int, int]]] = {}
    for r, cp in matched:
        by_player.setdefault(r["player_key"], []).append(
            (r["pred"], cp, r["actual"]))
    players = sorted(by_player)
    rng = random.Random(SEED)
    d_maes, d_w1s = [], []
    for _ in range(B):
        draw = [by_player[players[rng.randrange(len(players))]]
                for _ in range(len(players))]
        trip = [t for grp in draw for t in grp]
        n = len(trip)
        mc = sum(abs(p - a) for p, _, a in trip) / n
        mx = sum(abs(c - a) for _, c, a in trip) / n
        d_maes.append(mc - mx)
        wc = sum(1 for p, _, a in trip if abs(p - a) <= 1) / n
        wx = sum(1 for _, c, a in trip if abs(c - a) <= 1) / n
        d_w1s.append(wx - wc)

    def pct(xs, q):
        s = sorted(xs)
        return s[min(len(s) - 1, max(0, int(q * len(s))))]

    mde95 = 1.96 * statistics.pstdev(d_maes)
    mae_lo, mae_hi = pct(d_maes, 0.025), pct(d_maes, 0.975)
    w1_lo, w1_hi = pct(d_w1s, 0.025), pct(d_w1s, 0.975)
    c1_pass = (mae_x < mae_c) and (d_mae > mde95)
    c2_pass = (w1_x > w1_c) and (w1_lo > 0)
    print(f"C1 ROW-MATCHED MAE: n={len(matched)} champion {mae_c:.3f} vs "
          f"challenger {mae_x:.3f}; dMAE {d_mae:+.3f} MDE95 {mde95:.3f} "
          f"CI95 [{mae_lo:+.3f}, {mae_hi:+.3f}] -> "
          f"{'PASS' if c1_pass else 'FAIL'}")
    print(f"C2 ROW-MATCHED WITHIN-1Y: champion {w1_c:.3f} vs challenger "
          f"{w1_x:.3f}; d {d_w1:+.3f} CI95 [{w1_lo:+.3f}, {w1_hi:+.3f}] -> "
          f"{'PASS' if c2_pass else 'FAIL'}")

    # ── C3: pooled system on ALL champion-scoreable debuted rows ──────────
    pooled_pairs = [((chall_pred(r) if chall_pred(r) is not None
                      else r["pred"]), r["actual"]) for r in deb]
    champ_all = [(r["pred"], r["actual"]) for r in deb]
    mae_pool, mae_all = _mae(pooled_pairs), _mae(champ_all)
    c3_pass = mae_pool < mae_all
    n_defined = sum(1 for r in deb if chall_pred(r) is not None)
    print(f"C3 POOLED SYSTEM MAE (challenger-where-defined [{n_defined}] + "
          f"champion fallback, all {len(deb)} champion rows): pooled "
          f"{mae_pool:.3f} vs champion {mae_all:.3f} -> "
          f"{'PASS' if c3_pass else 'FAIL'}")

    # ── C4: overdue guardrail on censored_active (live-board proxy) ───────
    ship_table = _empirical_table(rows)  # full window: what would ship
    overdue_champ = sum(1 for r in censored if r["pred"] <= LAST_FULL_SEASON)
    overdue_sys = 0
    for r in censored:
        if r["level"] in ship_table:
            p = r["vintage"] + round(ship_table[r["level"]])
        else:
            p = r["pred"]
        if p <= LAST_FULL_SEASON:
            overdue_sys += 1
    d_over = overdue_sys - overdue_champ
    c4_pass = d_over <= OVERDUE_LIMIT
    print(f"C4 OVERDUE GUARDRAIL: censored_active n={len(censored)}; champion "
          f"overdue {overdue_champ} vs shipped-system overdue {overdue_sys}; "
          f"delta {d_over:+d} vs limit +{OVERDUE_LIMIT} -> "
          f"{'PASS' if c4_pass else 'FAIL'}")
    print(f"full-window ship table: "
          f"{ {lv: ship_table[lv] for lv in sorted(ship_table)} }")

    passes = {"C1": c1_pass, "C2": c2_pass, "C3": c3_pass,
              "C4": c4_pass, "C5": c5_pass}
    ship = all(passes.values())
    failed = [k for k, v in passes.items() if not v]
    print(f"VERDICT: {'SHIP eta v40' if ship else 'NO SHIP (' + ', '.join(failed) + ' failed)'}")

    result = {
        "gate": "docs/eta-2026-08-19/ETA_EMPIRICAL_TABLE_GATE.md",
        "date": date.today().isoformat(),
        "seed": SEED, "B": B,
        "candidate": "eta v40: forward-chained empirical table where defined, champion fallback",
        "row_matched": {
            "n": len(matched),
            "champion": {"mae": round(mae_c, 3), "within_1y": round(w1_c, 3)},
            "challenger": {"mae": round(mae_x, 3), "within_1y": round(w1_x, 3)},
            "d_mae": round(d_mae, 3), "mde95_mae": round(mde95, 3),
            "d_mae_ci95": [round(mae_lo, 3), round(mae_hi, 3)],
            "d_within_1y": round(d_w1, 3),
            "d_within_1y_ci95": [round(w1_lo, 3), round(w1_hi, 3)],
        },
        "pooled_system": {
            "n": len(deb), "n_challenger_defined": n_defined,
            "pooled_mae": round(mae_pool, 3),
            "champion_mae": round(mae_all, 3),
        },
        "overdue_guardrail": {
            "censored_n": len(censored),
            "champion": overdue_champ, "shipped_system": overdue_sys,
            "delta": d_over, "limit": OVERDUE_LIMIT,
        },
        "leak_check": {
            "forward_chained": True,
            "rederived_tables_match_artifact": c5_match,
        },
        "full_window_ship_table": {lv: ship_table[lv]
                                   for lv in sorted(ship_table)},
        "clauses": {k: ("PASS" if v else "FAIL") for k, v in passes.items()},
        "decision": "SHIP" if ship else "NO_SHIP",
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1),
                                  encoding="utf-8")
        print(f"result written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
