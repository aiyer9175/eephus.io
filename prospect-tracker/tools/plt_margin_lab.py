# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Lineup Charts PLT chip margin (hem_plus.PLATOON_OPTION_MARGIN), re-derived on the
per-hand estimator platoon_ratio_v1 (owner answer M17HEM-1 = (b), 2026-10-01).

THE RECIPE is the one that produced the original 15 on 2026-09-11 (the P2 lineup
card design, its measurement step 3 part (b)), kept exactly:

  frame   every 2026 MLB hitter with a per-hand HEM+ on BOTH hands, from the
          StatsAPI statSplits feeds (sitCodes vl and vr, gameType R, playerPool
          All) scored by hem_plus.build_split_hem on the season pool, the same
          call hitter_export makes; bat side from sports/1/players batSide.
  cells   bat side L, R, S crossed with the vs-LHP plate-appearance bands
          [20,60), [60,100), [100,150), [150,250), [250,900); a cell counts
          when it holds 8 or more hitters.
  spread  the population SD of (vs-LHP HEM+ minus vs-RHP HEM+) within a cell.
  margin  the low end of the spread across counted cells, rounded UP to a
          multiple of 5. On 2026-09-11 the cells ran 13.5 to 22.3 over 635
          hitters and 13.5 became 15. Rounding up is the reading that keeps the
          margin at or above the measured spread, which the first value did
          (15 over 13.5); rounding to the nearest 5 also gives 15 there but
          gives 0 on the new construction, and a margin of 0 is no gate.

The regular season is final, so the vl / vr lines are fixed. The season rows
(hitter_export.load_season_hitting) and the raw split and batSide responses are
cached under .cache/plt_margin_lab/ on the first run and every rerun reads them,
so the derivation reruns offline byte for byte. No game outcome or price is read.

Run: python tools/plt_margin_lab.py   (writes .cache/plt_margin_lab/derivation.json)
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))

import hem_plus as H  # noqa: E402

SEASON = 2026
SIDES = ("L", "R", "S")
BANDS = ((20, 60), (60, 100), (100, 150), (150, 250), (250, 900))
MIN_CELL_N = 8
ROUND_TO = 5
CACHE = ROOT / ".cache" / "plt_margin_lab"
OUT = CACHE / "derivation.json"


def _cached(name: str, path: str, params: dict) -> dict:
    p = CACHE / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    import bullpen_export as be
    data = be._get_json(path, params)
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return data


def load_inputs(season: int = SEASON) -> tuple[list, dict, dict]:
    """(season hitting rows, {mlbam: batSide}, {'L': {mlbam: counts}, 'R': {...}})."""
    rows_path = CACHE / f"{season}_season_rows.json"
    if rows_path.exists():
        rows = json.loads(rows_path.read_text(encoding="utf-8"))
    else:
        import hitter_export as he
        rows = he.load_season_hitting(season)
        CACHE.mkdir(parents=True, exist_ok=True)
        rows_path.write_text(json.dumps(rows), encoding="utf-8")
    people = _cached(f"{season}_players.json", "sports/1/players",
                     {"season": int(season)}).get("people") or []
    bats = {int(p["id"]): (p.get("batSide") or {}).get("code") for p in people
            if p.get("id") and (p.get("batSide") or {}).get("code")}
    counts: dict = {}
    for hand, sit in (("L", "vl"), ("R", "vr")):
        data = _cached(f"{season}_{sit}.json", "stats", {
            "stats": "statSplits", "sitCodes": sit, "group": "hitting",
            "season": int(season), "gameType": "R", "sportId": 1,
            "playerPool": "All", "limit": 2000})
        counts[hand] = {int(sp["player"]["id"]): sp["stat"]
                        for sp in ((data.get("stats") or [{}])[0].get("splits") or [])
                        if (sp.get("player") or {}).get("id")
                        and isinstance(sp.get("stat"), dict)}
    return rows, bats, counts


def split_map(rows: list, bats: dict, counts: dict) -> dict:
    """The served per-hand map, built exactly as hem_plus.score_pool builds it."""
    import hitter_export as he
    hitters = he.build_hitters(rows)
    for h in hitters:
        if h.mlbam is not None and bats.get(int(h.mlbam)):
            h.bats = bats[int(h.mlbam)]
    pool_in = [h for h in hitters if H._woba_denom(h) > 0]
    for h in pool_in:
        H.derive_rates(h)
    pool = H.build_pool(pool_in)
    for h in pool_in:
        H.hem_plus(h, pool)
    return H.build_split_hem(counts, pool, pool_in) or {}


def cells(split: dict, bats: dict) -> tuple[int, list]:
    """(hitters with both hands, [cell dicts]) for the recipe's cells."""
    pairs = []
    for mid, sp in split.items():
        if sp.get("L") is None or sp.get("R") is None:
            continue
        n_l = (sp.get("pa") or {}).get("L") or 0
        pairs.append((bats.get(int(mid)), n_l, sp["L"] - sp["R"]))
    out = []
    for side in SIDES:
        for lo, hi in BANDS:
            d = [g for b, n, g in pairs if b == side and lo <= n < hi]
            if len(d) >= MIN_CELL_N:
                out.append({"bats": side, "vs_lhp_pa": [lo, hi], "n": len(d),
                            "mean": round(statistics.mean(d), 2),
                            "sd": round(statistics.pstdev(d), 2)})
    return len(pairs), out


def margin_from(cell_rows: list) -> tuple[float, int]:
    """(low end of the spread, the margin it rounds to)."""
    low = min(c["sd"] for c in cell_rows)
    return low, int(ROUND_TO * math.ceil(low / ROUND_TO))


def main() -> int:
    rows, bats, counts = load_inputs()
    split = split_map(rows, bats, counts)
    n_both, cell_rows = cells(split, bats)
    low, margin = margin_from(cell_rows)
    rec = {"season": SEASON, "estimator": H.SPLIT_ESTIMATOR,
           "n_hitters_both_hands": n_both, "min_cell_n": MIN_CELL_N,
           "bands": [list(b) for b in BANDS], "cells": cell_rows,
           "spread_low": low, "spread_high": max(c["sd"] for c in cell_rows),
           "round_to": ROUND_TO, "margin": margin,
           "module_margin": H.PLATOON_OPTION_MARGIN,
           "matches_module": margin == H.PLATOON_OPTION_MARGIN,
           "matches_frozen_cells": cell_rows == H.PLATOON_OPTION_MARGIN_DERIVATION["cells"]}
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(f"hitters with both hands: {n_both}")
    for c in cell_rows:
        print(f"  bats {c['bats']}, vs-LHP PA [{c['vs_lhp_pa'][0]},{c['vs_lhp_pa'][1]}): "
              f"n={c['n']:>3} mean(L-R)={c['mean']:+6.2f} SD(L-R)={c['sd']:5.2f}")
    print(f"spread {low} to {rec['spread_high']}; margin {margin} "
          f"(module {H.PLATOON_OPTION_MARGIN}, matches {rec['matches_module']}; "
          f"frozen cells match {rec['matches_frozen_cells']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
