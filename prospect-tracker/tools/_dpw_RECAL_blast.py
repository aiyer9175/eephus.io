# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE recalibrate -- blast radius of the calibration refit on SERVED dollars.

Every served surplus dollar passes through vf.apply_calibration exactly once
(efv_score's F1 seam, storage.surplus_value_mm, proj_export, bayes_trade_value).
The shipped map is invertible above its zero-cross, so the served numbers
themselves can be walked back to their raw input and re-priced under the new map:

    raw = (served + 2.318551) / 1.382491        for served > 0
    raw in [0, 1.677]                            for served == 0 (bounded, not exact)

Read-only: opens the served artifacts, writes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHIP_A, SHIP_B = 1.382491, -2.318551
ZERO_CROSS = -SHIP_B / SHIP_A


def invert(served: float) -> float | None:
    if served is None:
        return None
    return (float(served) - SHIP_B) / SHIP_A if served > 0 else None


def report(name: str, served: list[float], new_coef) -> dict:
    a, b = new_coef
    s = np.array([v for v in served if v is not None], dtype=float)
    pos = s[s > 0]
    raw = (pos - SHIP_B) / SHIP_A
    new = np.maximum(0.0, a * raw + b)
    d = new - pos
    zeros = int((s == 0).sum())
    return {"artifact": name, "n_rows": int(len(s)), "n_zero_served": zeros,
            "n_positive": int(len(pos)),
            "agg_served_musd": float(pos.sum()),
            "agg_new_musd": float(new.sum()),
            "agg_pct": float(100 * (new.sum() / pos.sum() - 1)) if pos.sum() else 0.0,
            "per_player_mean_delta": float(d.mean()) if len(d) else 0.0,
            "per_player_median_delta": float(np.median(d)) if len(d) else 0.0,
            "max_delta": float(d.max()) if len(d) else 0.0,
            "p90_delta": float(np.percentile(d, 90)) if len(d) else 0.0,
            "zero_row_bound_musd": zeros * max(0.0, a * ZERO_CROSS + b)}


def main(a: float, b: float) -> None:
    rows = []
    x = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    live = [r for r in x.values() if r.get("kind") == "active"]
    rows.append(report("data/xfv.json (all scored)",
                       [r.get("surplus_mm") for r in x.values()], (a, b)))
    rows.append(report("data/xfv.json (live board, kind=active)",
                       [r.get("surplus_mm") for r in live], (a, b)))
    rows.append(report("data/xfv.json consensus_surplus_mm",
                       [r.get("consensus_surplus_mm") for r in x.values()], (a, b)))
    tv = json.loads((ROOT / "data" / "trade_values.json").read_text(encoding="utf-8"))
    tvp = tv["players"] if isinstance(tv, dict) else tv
    vals = []
    for r in (tvp.values() if isinstance(tvp, dict) else tvp):
        for k in ("surplus_mm", "trade_value_mm", "value_mm"):
            if isinstance(r, dict) and r.get(k) is not None:
                vals.append(r[k])
                break
    rows.append(report("data/trade_values.json", vals, (a, b)))
    print(f"new map: corrected = max(0, {a:.6f}*raw + {b:.6f})   "
          f"(shipped {SHIP_A}*raw {SHIP_B})")
    for r in rows:
        print(f"\n{r['artifact']}")
        print(f"  rows {r['n_rows']:6d}  served>0 {r['n_positive']:6d}  served==0 {r['n_zero_served']:6d}")
        print(f"  aggregate  ${r['agg_served_musd']:,.0f}M -> ${r['agg_new_musd']:,.0f}M "
              f"({r['agg_pct']:+.2f}%)")
        print(f"  per player delta  mean {r['per_player_mean_delta']:+.3f}M  "
              f"median {r['per_player_median_delta']:+.3f}M  p90 {r['p90_delta']:+.3f}M  "
              f"max {r['max_delta']:+.3f}M")
        print(f"  served==0 rows can only rise, bounded by "
              f"${max(0.0, a*ZERO_CROSS+b):.2f}M each "
              f"(<= ${r['zero_row_bound_musd']:,.0f}M in aggregate)")
    return rows


if __name__ == "__main__":
    a = float(sys.argv[1]) if len(sys.argv) > 1 else 1.667100
    b = float(sys.argv[2]) if len(sys.argv) > 2 else -0.083200
    main(a, b)
