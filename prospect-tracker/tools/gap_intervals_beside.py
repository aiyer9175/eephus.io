# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Write each LIBRARY_14 interval beside the points its producer last wrote.

The seven producers named in LIBRARY_14 (eta_backtest, farm_grade_backtest,
the eWAR eval, proj_backtest, prospect_path, tools/arb_gate_a for A6 and
betting_model for the market tier) now compute a paired, clustered bootstrap
interval on each scored gap and write it with their points. This tool adds that
block to an artifact the producer wrote on an earlier day WITHOUT regenerating
it: it re-runs the producer in memory, and gap_intervals.write_beside refuses,
writing nothing, unless every protected block reproduces exactly. So a point
value never moves here; an artifact whose inputs drifted since its last run is
reported as not reproducing and keeps no interval until its producer is rerun
on purpose.

Usage:
    python tools/gap_intervals_beside.py            # dry run: report only
    python tools/gap_intervals_beside.py --write    # write the reproducing ones
    python tools/gap_intervals_beside.py --only eta ewar
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gap_intervals as gi                                     # noqa: E402

DATA = ROOT / "data"


def _stored(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _all_but(doc: dict, prefix: str, skip: tuple = ()) -> list[str]:
    return [f"{prefix}{k}" for k in doc if k not in skip]


def _eta():
    import eta_backtest as E
    fresh = E.run(persist=False)
    return ("eta_eval.json", fresh, ["champion_on_baseline_rows.gap_ci_vs_naive"],
            _all_but(fresh, "", ("generated_at",)))


def _farm():
    import farm_grade_backtest as F
    fresh = F.run(persist=False)
    return ("farm_grade_eval.json", fresh, ["mean_spearman_gap_ci_vs_count"],
            _all_but(fresh, "", ("generated_at",)))


def _ewar():
    import ewar
    # The eval scores the war_daily frames its build read. A refetch would be
    # a different input, so the cached frames are read whatever their age; a
    # missing cache still fetches, and then the rerun simply fails to reproduce.
    ewar.BWAR_CACHE_TTL_S = float("inf")
    stored = _stored("ewar_eval.json")
    first, last = stored["eval_window"]
    model = ewar.build(first=2011, last=None, shrink=True)
    fresh = ewar.evaluate(model, None, first=first, last=last)
    protect = ["eval_window", "gate_1_team_wins", "gate_1b_team_runs",
               "gate_2_pitcher_persistence", "gate_3_coverage_identity",
               "accounting_league_sum", "face_validity"]
    return ("ewar_eval.json", fresh,
            ["gate_1_team_wins.gap_ci_vs_bwar",
             "gate_2_pitcher_persistence.gap_ci_vs_bwar_ra"], protect)


def _team():
    import proj_backtest as PB
    fresh = {"retro_backtest": PB.run(persist=False)}
    return ("team_outlook_eval.json", fresh,
            ["retro_backtest.ship_decision.holdout_gap_ci_vs_prior_wins"],
            _all_but(fresh["retro_backtest"], "retro_backtest.", ("generated_at",)))


def _path():
    import prospect_path as PP
    fresh = PP.run(persist=False)
    return ("prospect_path_eval.json", fresh, ["baseline_gap_ci_vs_challenger"],
            _all_but(fresh, "", ("generated_at",)))


def _arb():
    import arb_gate_a as G
    import arb_mde_lab as L
    stored = _stored("arbitration_eval.json")
    # The stored block's own frame and pool (docs/ARBITRATION_GATE.md
    # sections 15 and 16), so the rerun is the producer's run.
    rows, metrics = L.load_pool(stored.get("frame", "award"))
    seasons = sorted({r["season"] for r in rows})
    a6 = stored.get("a6_swartz") or {}
    fresh = {"a6_swartz": G._swartz_head_to_head(
        rows, metrics, seasons, stored["B"], pool=a6.get("pool", "frozen"),
        units=a6.get("units", "frozen"))}
    return ("arbitration_eval.json", fresh, ["a6_swartz.gap_ci_vs_swartz"],
            ["a6_swartz"])


def _betting():
    import betting_model as B
    stored = _stored("betting_model_eval.json")
    games = B.completed_games(stored.get("season"))
    teams, parks, starters = B.team_inputs(), B.park_index(), B.starter_inputs()
    lv = B._vintage_module()
    cov = (lv.coverage(game_dates=[g.get("date") for g in games if g.get("date")])
           if lv else {})
    vint = B._backtest_block(("vintage", None), games, teams, parks, starters,
                             None, cov)["value"]
    per_game = vint.pop("_per_game_p", None) or {}
    vint.pop("_per_game_markets", None)
    fresh = {"vintage": vint, "benchmarks": B._benchmarks_block(games, vint, per_game)}
    # n_vintages counts the leaderboard archive, which keeps growing after the
    # last graded game; every graded number of the block is protected.
    protect = ["benchmarks"] + _all_but(stored["vintage"], "vintage.", ("n_vintages",))
    return ("betting_model_eval.json", fresh,
            ["benchmarks.tiers.market_open_devig.gap_ci_model_vs_market"], protect)


PRODUCERS = {"eta": _eta, "farm": _farm, "ewar": _ewar, "team": _team,
             "path": _path, "arb": _arb, "betting": _betting}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only", nargs="*", choices=sorted(PRODUCERS))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    for key in args.only or PRODUCERS:
        t0 = time.perf_counter()
        name, fresh, new_keys, protect = PRODUCERS[key]()
        path = DATA / name
        try:
            if args.write:
                blocks = gi.write_beside(path, fresh, new_keys, protect=protect)
                state = "WROTE"
            else:
                blocks = gi.check_beside(path, fresh, new_keys, protect=protect)
                state = "REPRODUCES"
        except RuntimeError as exc:
            print(f"{key}: NOT WRITTEN, {exc} ({time.perf_counter() - t0:.1f} s)")
            continue
        print(f"{key}: {state} {name} ({time.perf_counter() - t0:.1f} s)")
        for k, blk in blocks.items():
            legs = {lg: v for lg, v in blk.items() if isinstance(v, dict)}
            print(f"  {k}: {json.dumps(legs)} B {blk['B']} seed {blk['seed']} "
                  f"clusters {blk['clusters']} n {blk['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
