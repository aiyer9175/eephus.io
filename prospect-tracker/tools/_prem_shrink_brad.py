# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""What does the blend lambda actually DO to Enrique Bradfield Jr's served numbers?

Method: re-score the live hitter board at lam=0 (rank_war == the consensus leg
cons_war) and at lam=1 (rank_war == the model leg xfv_war). Those two runs recover
BOTH legs exactly for every player, so any global OR per-stratum lambda can then be
evaluated exactly, including the headline quantile grade (a rank-preserving quantile
map of rank_war) and the board slot (BOARD_GRADE_FIELD = xfv_grade).

Writes only into the scratch dir; data/ is never touched.
"""
from __future__ import annotations
import sys, json, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

import efv_model as XM
import efv_score as S
from efv_dataset import live_matrix_path

PK = "enrique_bradfield_jr"
SCRATCH = Path(tempfile.mkdtemp(prefix="prem_shrink_"))


def _stratum(r):
    m = r.get("milb") or {}
    lr, arl, ops = m.get("level_rank"), m.get("age_rel_level"), m.get("ops_rel")
    if lr is None or arl is None:
        return None
    return ("HIGH" if lr >= 5 else ("MID" if lr >= 4 else "LOW"),
            "OLD" if arl >= 0 else "YOUNG",
            "BELOW" if (ops is not None and ops < 0) else "ABOVE")


def score_at(lam):
    """Run the production live scorer at a forced global hit lambda; return rows."""
    orig_lam, orig_path = XM.blend_lambda, S.scored_live_path
    dest = SCRATCH / f"live_{lam:.2f}.json"
    try:
        XM.blend_lambda = lambda side, _l=lam: (_l if side == "hit" else orig_lam(side))
        S.blend_lambda = XM.blend_lambda
        S.scored_live_path = lambda side, _d=dest: _d
        S.run_live(persist=True, side="hit")
    finally:
        XM.blend_lambda = orig_lam
        S.blend_lambda = orig_lam
        S.scored_live_path = orig_path
    return json.loads(dest.read_text(encoding="utf-8"))


def quantile_grades(rows, rank_of):
    """efv_score's exact headline map: rank-preserving quantile of rank_war onto the
    pool's consensus FV distribution."""
    pool = [r for r in rows if rank_of(r) is not None and r.get("consensus_fv") is not None]
    target = sorted(r["consensus_fv"] for r in pool)
    order = sorted(range(len(pool)), key=lambda i: (rank_of(pool[i]), pool[i]["player_key"]))
    m = len(pool)
    out = {}
    for rank_pos, i in enumerate(order):
        p = (rank_pos / (m - 1)) if m > 1 else 0.0
        pos = p * (m - 1)
        lo = int(pos); hi = min(m - 1, lo + 1); frac = pos - lo
        out[pool[i]["player_key"]] = target[lo] * (1 - frac) + target[hi] * frac
    return out


def main():
    live = {r["player_key"]: r for r in
            json.loads(live_matrix_path("hit").read_text(encoding="utf-8"))}
    brad = live[PK]
    print(f"Bradfield ex-ante stratum: {_stratum(brad)}   consensus_fv_raw={brad['consensus_fv_raw']}"
          f"  age={brad['milb']['age']}  ops_rel={brad['milb']['ops_rel']:.4f}"
          f"  level={brad['milb']['milb_level']}\n")

    r0 = {r["player_key"]: r for r in score_at(0.0)}
    r1 = {r["player_key"]: r for r in score_at(1.0)}
    keys = [k for k in r0 if k in r1]
    print(f"live hitter board scored: {len(keys)} players\n")

    legs = {}
    for k in keys:
        legs[k] = {"cons": r0[k]["rank_war"], "model": r1[k]["rank_war"],
                   "grade": r1[k]["xfv_grade"], "cons_fv": r1[k]["consensus_fv"],
                   "strat": _stratum(live.get(k, {}))}

    # BOARD number check: xfv_grade under lam=0 vs lam=1
    g0 = {k: r0[k]["xfv_grade"] for k in keys}
    g1 = {k: r1[k]["xfv_grade"] for k in keys}
    n_diff = sum(1 for k in keys if abs(g0[k] - g1[k]) > 1e-9)
    print(f"BOARD-GRADE INVARIANCE CHECK (storage.BOARD_GRADE_FIELD = xfv_grade):")
    print(f"  players whose board grade differs between lam=0.00 and lam=1.00: "
          f"{n_diff} / {len(keys)}")
    print(f"  Bradfield xfv_grade  lam=0.00 -> {g0[PK]}   lam=1.00 -> {g1[PK]}\n")

    rows_for_q = [{"player_key": k, "consensus_fv": legs[k]["cons_fv"]} for k in keys]
    tgt_strat = ("HIGH", "OLD", "BELOW")
    n_tgt = sum(1 for k in keys if legs[k]["strat"] == tgt_strat)
    print(f"Bradfield's ex-ante stratum HIGH/OLD/BELOW on the live board: {n_tgt} players\n")

    def arm(name, lam_of):
        rw = {k: (1 - lam_of(k)) * legs[k]["cons"] + lam_of(k) * legs[k]["model"]
              for k in keys}
        q = quantile_grades(rows_for_q, lambda r: rw[r["player_key"]])
        board = sorted(keys, key=lambda k: (-legs[k]["grade"], k))
        slot_board = board.index(PK) + 1
        slot_rank = sorted(keys, key=lambda k: (-rw[k], k)).index(PK) + 1
        print(f"{name:28s} BOARD grade={legs[PK]['grade']:.4f} (slot {slot_board:4d})   "
              f"quantile grade={q[PK]:5.2f} (prem {q[PK]-legs[PK]['cons_fv']:+5.2f}, "
              f"rank_war slot {slot_rank:4d})")
        return {"board_grade": legs[PK]["grade"], "board_slot": slot_board,
                "quantile_grade": round(q[PK], 3),
                "quantile_prem": round(q[PK] - legs[PK]["cons_fv"], 3),
                "rank_war_slot": slot_rank}

    res = {}
    print("---- GLOBAL lambda arms ----")
    for lam in (0.00, 0.30, 0.50, 0.70, 0.85, 1.00):
        res[f"GLOB:{lam:.2f}"] = arm(f"GLOB lam={lam:.2f}", lambda k, _l=lam: _l)
    print("\n---- CONDITIONAL: shrink ONLY HIGH/OLD/BELOW, rest stays at 0.70 ----")
    for ls in (0.00, 0.20, 0.35, 0.50):
        res[f"COND:{ls:.2f}"] = arm(
            f"COND stratum lam={ls:.2f}",
            lambda k, _l=ls: (_l if legs[k]["strat"] == tgt_strat else 0.70))

    Path("tools/_prem_shrink_brad_out.json").write_text(
        json.dumps({"arms": res, "n_board": len(keys), "n_stratum": n_tgt,
                    "board_grade_differs_lam0_vs_lam1": n_diff}, indent=1), encoding="utf-8")
    print(f"\nwrote tools/_prem_shrink_brad_out.json  (scratch runs in {SCRATCH})")


if __name__ == "__main__":
    raise SystemExit(main())
