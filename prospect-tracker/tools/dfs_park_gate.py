# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""dfs_park_gate.py - the pre-registered gate for the /fantasy/ DFS park leg.

Registered in docs/dfs-park-leg-gate-2026-08-07.md BEFORE this script was run.
Read that document first; it fixes the sample, the two predictors, the metric
and the decision rule, and this file only computes them.

READ ONLY. It touches .cache/betting/completed_games.json and data/fa_meta.json
and writes nothing anywhere. Run it as often as you like.

    python tools/dfs_park_gate.py
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GAMES = ROOT / ".cache" / "betting" / "completed_games.json"
META = ROOT / "data" / "fa_meta.json"
SEED = 20260807
N_PERM = 10000


def _park_index() -> dict:
    """{org: runs index / 100}. The same read betting_model.park_index does; a
    local copy so this gate has no import-time dependency on the betting stack."""
    meta = json.loads(META.read_text(encoding="utf-8"))
    out = {}
    for org, v in (meta.get("park_factors") or {}).items():
        try:
            out[str(org)] = float((v or {}).get("runs") or 100) / 100.0
        except (TypeError, ValueError):
            continue
    return out


def _team_games(pf: dict) -> list[tuple[str, float]]:
    """[(home_org, runs)] over both sides of every completed game whose park is
    in the index. Excluded-because-no-factor is counted by the caller."""
    rows = json.loads(GAMES.read_text(encoding="utf-8"))
    out, skipped = [], 0
    for g in rows:
        home = g.get("home_org")
        if home not in pf:
            skipped += 1
            continue
        for k in ("home_runs", "away_runs"):
            r = g.get(k)
            if isinstance(r, (int, float)):
                out.append((home, float(r)))
    return out, skipped, len(rows)


def _rmse(pairs, mult: dict, mu: float) -> float:
    s = sum((r - mu * mult.get(park, 1.0)) ** 2 for park, r in pairs)
    return math.sqrt(s / len(pairs))


def _mae(pairs, mult: dict, mu: float) -> float:
    return sum(abs(r - mu * mult.get(park, 1.0)) for park, r in pairs) / len(pairs)


def main() -> int:
    pf = _park_index()
    pairs, skipped, n_games = _team_games(pf)
    mu = sum(r for _, r in pairs) / len(pairs)
    neutral: dict = {}

    rmse_a, rmse_b = _rmse(pairs, neutral, mu), _rmse(pairs, pf, mu)
    mae_a, mae_b = _mae(pairs, neutral, mu), _mae(pairs, pf, mu)

    orgs = sorted(pf)
    vals = [pf[o] for o in orgs]
    rng = random.Random(SEED)
    beat = 0
    for _ in range(N_PERM):
        shuf = vals[:]
        rng.shuffle(shuf)
        if _rmse(pairs, dict(zip(orgs, shuf)), mu) <= rmse_b:
            beat += 1
    p = beat / N_PERM

    print(f"sample: {n_games} completed games, {len(pairs)} team-games priced, "
          f"{skipped} games dropped (home park has no fa_meta entry)")
    print(f"league mean runs per team-game (mu): {mu:.4f}")
    print(f"park index spread: {min(vals):.3f}..{max(vals):.3f} over {len(orgs)} parks")
    print(f"A neutral   RMSE {rmse_a:.5f}   MAE {mae_a:.5f}")
    print(f"B park leg  RMSE {rmse_b:.5f}   MAE {mae_b:.5f}")
    print(f"delta RMSE  {rmse_b - rmse_a:+.5f}   delta MAE {mae_b - mae_a:+.5f}")
    print(f"permutation control ({N_PERM} draws, seed {SEED}): "
          f"{beat} shuffled indices did at least as well -> p = {p:.4f}")
    cond1, cond2 = rmse_b < rmse_a, p < 0.05
    print(f"condition 1 (RMSE improves): {'PASS' if cond1 else 'FAIL'}")
    print(f"condition 2 (p < 0.05):      {'PASS' if cond2 else 'FAIL'}")
    print("VERDICT:", "SHIP" if (cond1 and cond2) else "NO-SHIP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
