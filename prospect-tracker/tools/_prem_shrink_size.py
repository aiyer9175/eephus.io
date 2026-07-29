# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SIZING pass for the conditional-lambda (shrinkage) lane. Read-only.

Counts, per side, how the forward-chained OOS test rows distribute across the
ex-ante stratum grid, and how many are in the SERVED (has-MiLB-track-record)
population. No model claims here; this only tells us which strata are even
measurable before any lambda is fit.
"""
from __future__ import annotations
import sys, json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

from efv_dataset import matrix_path
import efv_lab_runner as LR

SCORED_YEARS = LR.SCORED_YEARS


def strat_keys(side):
    """Ex-ante stratum assignment from the matrix milb block only."""
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    out = {}
    for r in rows:
        m = r.get("milb") if isinstance(r.get("milb"), dict) else {}
        lvl = m.get("milb_level")
        lr = m.get("level_rank")
        age = m.get("age")
        ops = m.get("ops_rel")
        served = bool(lvl) and not m.get("age_missing") is None
        out[r["player_key"]] = {
            "lvl": lvl, "level_rank": lr, "age": age, "ops_rel": ops,
            "served": bool(lvl),
            "age_rel_level": m.get("age_rel_level"),
        }
    return out


def bucket(s):
    lr = s.get("level_rank")
    if lr is None:
        return None
    lvl = "HIGH" if lr >= 5 else ("MID" if lr >= 4 else "LOW")
    arl = s.get("age_rel_level")
    if arl is None:
        return None
    ageb = "OLD" if arl >= 0 else "YOUNG"
    ops = s.get("ops_rel")
    prod = "BELOW" if (ops is not None and ops < 0) else "ABOVE"
    return f"{lvl}/{ageb}/{prod}"


def main():
    for side in ("hit", "pit"):
        sk = strat_keys(side)
        rows = LR.data_for(side)
        # replicate the fold filter of run_variant
        test_rows = []
        for yr in SCORED_YEARS:
            tr = [r for r in rows if r["decision_year"] < yr]
            te = [r for r in rows if r["decision_year"] == yr]
            if len(te) < 12 or len(tr) < 50:
                continue
            test_rows.extend(te)
        print(f"\n===== {side}  pooled OOS test rows n={len(test_rows)} "
              f"(train pool total n={len(rows)}) =====")
        served = [r for r in test_rows if (sk.get(r['player_key']) or {}).get('served')]
        print(f"  served (has MiLB level): {len(served)} / {len(test_rows)} "
              f"= {len(served)/max(1,len(test_rows)):.3f}")
        c = Counter()
        for r in test_rows:
            b = bucket(sk.get(r["player_key"]) or {})
            c[b] += 1
        for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
            print(f"   {str(k):24s} {v:4d}")
        # the lead's exact target profile
        tgt = [r for r in test_rows
               if (sk.get(r['player_key']) or {}).get('lvl') == 'AAA'
               and ((sk.get(r['player_key']) or {}).get('age') or 0) >= 23.5
               and ((sk.get(r['player_key']) or {}).get('ops_rel') or 0) < 0]
        print(f"  LEAD TARGET PROFILE (AAA, age>=23.5, ops_rel<0) in OOS test: {len(tgt)}")
        # train-side sizes by fold
        for yr in SCORED_YEARS:
            tr = [r for r in rows if r["decision_year"] < yr]
            n_t = sum(1 for r in tr
                      if (sk.get(r['player_key']) or {}).get('lvl') == 'AAA'
                      and ((sk.get(r['player_key']) or {}).get('age') or 0) >= 23.5
                      and ((sk.get(r['player_key']) or {}).get('ops_rel') or 0) < 0)
            print(f"    fold {yr}: train n={len(tr):4d}  target-profile in train={n_t:4d}")


if __name__ == "__main__":
    raise SystemExit(main())
