# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
betting_market_blend_lab.py - B1. Should the model's probability be blended
toward the market's?

WHY THIS WAS THE TOP BETTING ITEM. The honest backtest has the model LOSING to
"always take the home team" (n_graded 221, skill -0.0009). A market-anchored
blend was the plan's single most likely Brier gain, because the de-vigged market
price is the strongest cheap baseline in this problem.

WHAT THIS LAB IS FOR. It measures, it does not fit. The calibration ledger is
the only place model probability, market fair probability and a settled outcome
sit on the same row, and right now it holds a very small number of GAMES. So the
question this answers is "is a blend worth building yet", not "what is the
weight".

THE DEGENERACY THAT MATTERS MORE THAN THE BRIER. If the sweep's optimum is
w = 1.0, that is not a model to ship: blending all the way to the market makes
the fair price equal the market price, so every edge is identically zero and the
board can never publish a bet. A blend is only a PRODUCT for w < 1, so an
optimum at the boundary means the data is telling you the model contributes
nothing, not that you have found a good weight.

CLUSTERING IS NOT OPTIONAL HERE. The rows are ~3 markets per game, so resampling
rows would treat one game as three independent observations and roughly triple
the apparent evidence. The bootstrap resamples GAMES.

Writes data/betting_market_blend_eval.json.

Usage:
    python tools/betting_market_blend_lab.py
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / ".cache" / "betting" / "calibration.jsonl"
OUT = ROOT / "data" / "betting_market_blend_eval.json"

SEED = 20260812
#: Below this many distinct GAMES the lab reports and refuses to recommend.
MIN_GAMES_TO_RECOMMEND = 150


def load_rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    raw = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                raw.append(json.loads(line))
            except ValueError:
                continue
    op = {r["cal_id"]: r for r in raw if r.get("phase") == "open" and r.get("cal_id")}
    out = []
    for s in raw:
        if s.get("phase") != "settled" or s.get("result") not in ("won", "lost"):
            continue
        o = op.get(s.get("cal_id"))
        if not o or o.get("model_prob") is None or o.get("market_fair_prob") is None:
            continue
        out.append({"game_pk": o.get("game_pk"), "slate_date": o.get("slate_date"),
                    "market": o.get("market"),
                    "model": float(o["model_prob"]),
                    "mkt": float(o["market_fair_prob"]),
                    "y": 1.0 if s["result"] == "won" else 0.0})
    return out


def _brier(rows, w):
    return st.mean(((1 - w) * r["model"] + w * r["mkt"] - r["y"]) ** 2 for r in rows)


def run(boot: int) -> dict:
    rows = load_rows()
    if len(rows) < 20:
        return {"verdict": "NO_DATA", "n_rows": len(rows),
                "reason": ("the calibration ledger carries too few settled rows with "
                           "both a model and a market probability to measure anything")}

    games = collections.defaultdict(list)
    for r in rows:
        games[r["game_pk"]].append(r)
    n_games = len(games)
    slates = sorted({r["slate_date"] for r in rows if r.get("slate_date")})

    sweep = {f"{w:.1f}": round(_brier(rows, w), 5) for w in (i / 10 for i in range(11))}
    best_w = min(((w, _brier(rows, w)) for w in (i / 20 for i in range(21))),
                 key=lambda t: t[1])
    b_model, b_mkt = _brier(rows, 0.0), _brier(rows, 1.0)

    rng = random.Random(SEED)
    keys = list(games)
    diffs = []
    for _ in range(boot):
        samp = [r for g in (keys[rng.randrange(len(keys))] for _ in keys)
                for r in games[g]]
        diffs.append(_brier(samp, 0.0) - _brier(samp, 1.0))
    diffs.sort()
    lo = diffs[int(0.025 * (len(diffs) - 1))]
    hi = diffs[int(0.975 * (len(diffs) - 1))]
    resolvable = lo > 0 or hi < 0

    boundary = best_w[0] >= 0.999
    enough = n_games >= MIN_GAMES_TO_RECOMMEND
    if not enough:
        verdict = "UNDERPOWERED"
    elif boundary:
        verdict = "DEGENERATE"
    elif resolvable:
        verdict = "BUILD"
    else:
        verdict = "NOT_RESOLVABLE"

    return {
        "verdict": verdict,
        "n_rows": len(rows), "n_games": n_games, "slates": slates,
        "min_games_to_recommend": MIN_GAMES_TO_RECOMMEND,
        "brier_model_only": round(b_model, 5),
        "brier_market_only": round(b_mkt, 5),
        "model_minus_market": round(b_model - b_mkt, 5),
        "ci95_model_minus_market": [round(lo, 5), round(hi, 5)],
        "resolvable": resolvable,
        "blend_sweep": sweep,
        "best_weight_on_this_sample": round(best_w[0], 3),
        "optimum_at_boundary": boundary,
        "why_the_boundary_matters": (
            "w = 1.0 sets the fair price equal to the market price, so every edge is "
            "identically zero and no bet can ever be published. An optimum there means "
            "the model contributes nothing on this sample, not that a good weight was "
            "found. A blend is only a product for w < 1."),
        "clustering": ("bootstrap resamples GAMES, not rows: the rows are about three "
                       "markets per game and row resampling would treat one game as "
                       "three independent observations"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=4000)
    args = ap.parse_args()
    res = run(args.boot)
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_id": "betting_market_blend",
        # Checkout-relative, not str(LEDGER): the absolute form published the
        # build machine's filesystem layout and OS username (payload-hygiene
        # sweep, 2026-08-16).
        "basis": {"seed": SEED, "bootstrap_B": args.boot,
                  "source": ".cache/betting/calibration.jsonl"},
        **res,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"verdict: {res['verdict']}")
    if res.get("n_games") is not None:
        print(f"rows {res['n_rows']} across {res['n_games']} game(s), slates {res.get('slates')}")
        print(f"Brier  model {res['brier_model_only']}  market {res['brier_market_only']}  "
              f"delta {res['model_minus_market']:+} {res['ci95_model_minus_market']}")
        print(f"best weight on this sample: {res['best_weight_on_this_sample']} "
              f"(boundary={res['optimum_at_boundary']})")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
