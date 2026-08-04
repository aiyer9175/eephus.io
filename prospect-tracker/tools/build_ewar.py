# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Build eWAR v1 -> data/ewar.json + data/ewar_eval.json.

    python tools/build_ewar.py                 # build + gates, print, write nothing
    python tools/build_ewar.py --write         # ...and commit both artifacts
    python tools/build_ewar.py --first 2016 --last 2026 --write
    python tools/build_ewar.py --no-sensitivity --write

The only network call is pybaseball's cached bwar_bat / bwar_pitch static CSV
pull (--force-fetch to bypass the local 7-day pickle cache). Everything else -
the FIP corpus, Statcast OAA, fielding innings, the k_inn constants, the
standings used by the team-wins gate - is read from disk.

NOTHING CONSUMES eWAR. This writes a module artifact and a measurement.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ewar                              # noqa: E402


def _fmt_gate1(g: dict) -> str:
    if not g.get("n_team_seasons"):
        return f"  gate 1: {g.get('note')}"
    e, b = g["ewar"], g["bwar"]
    return (f"  gate 1 TEAM WINS  n={g['n_team_seasons']} team-seasons "
            f"{g['seasons'][0]}-{g['seasons'][1]}\n"
            f"    r            eWAR {e['r']:+.4f}   bWAR {b['r']:+.4f}\n"
            f"    MAE (fit)    eWAR {e['mae_fit']:.3f}    bWAR {b['mae_fit']:.3f}\n"
            f"    MAE (0-par)  eWAR {e['mae_zero_param']:.3f}    "
            f"bWAR {b['mae_zero_param']:.3f}\n"
            f"    verdict      {g['verdict']}")


def _fmt_gate2(g: dict) -> str:
    if g.get("n_pairs", 0) < 30:
        return f"  gate 2: {g.get('note')} (n={g.get('n_pairs')})"
    f = g["forecast_next_year_actual_runs"]
    return (f"  gate 2 PITCHER PERSISTENCE  n={g['n_pairs']} pairs, "
            f"min {g['min_ip']:.0f} IP both years\n"
            f"    self r (y -> y+1)          FIP {g['self_r_ewar_fip']:+.4f}   "
            f"RA {g['self_r_bwar_ra']:+.4f}\n"
            f"    predicts next-year actual  FIP {f['from_ewar_fip']:+.4f}   "
            f"RA {f['from_bwar_ra']:+.4f}\n"
            f"    verdict                    {g['verdict']}")


def _fmt_gate3(g: dict) -> str:
    lines = ["  gate 3 COVERAGE"]
    for season, blk in g["fielding"]["by_season"].items():
        lines.append(f"    {season}  innings covered {blk['share_within_oaa_positions']:.3f} "
                     f"within the 7 OAA positions / "
                     f"{blk['fielding_innings_share_covered']:.3f} of all defense   "
                     f"non-pitcher player-seasons with a read "
                     f"{blk['n_with_statcast_read']}/"
                     f"{blk['n_non_pitcher_player_seasons']}")
    p = g["pitching"]
    lines.append(f"    pitching: {p['n_fip_priced']}/{p['n_rows']} rows FIP-priced, "
                 f"{p['ip_share_fip_priced']:.4f} of IP")
    return "\n".join(lines)


def _fmt_sum(g: dict) -> str:
    lines = ["  ACCOUNTING  league WAR sum per season"]
    for season, blk in g["by_season"].items():
        lines.append(f"    {season}  target {blk['target']:>7.1f}   "
                     f"bWAR {blk['bwar_sum']:>7.1f}   "
                     f"eWAR pre {blk['ewar_sum_pre_rescale']:>7.1f}   "
                     f"eWAR {blk['ewar_sum']:>7.1f}   "
                     f"rep x{blk['replacement_scale']:.4f}")
    lines.append(f"    max |eWAR sum - target| = {g['max_abs_deviation_from_target']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=ewar.DEFAULT_FIRST_SEASON)
    ap.add_argument("--last", type=int, default=None)
    ap.add_argument("--write", action="store_true", help="write both artifacts")
    ap.add_argument("--force-fetch", action="store_true",
                    help="bypass the local bwar pickle cache")
    ap.add_argument("--no-sensitivity", action="store_true",
                    help="skip the unshrunk-fielding sensitivity build")
    ap.add_argument("--eval-last", type=int, default=None,
                    help="last COMPLETED season for the gates (default: last year)")
    args = ap.parse_args()

    model = ewar.build(first=args.first, last=args.last,
                       shrink=True, force_fetch=args.force_fetch)
    print(f"eWAR v1: {len(model['rows'])} war_daily rows, "
          f"seasons {model['meta']['seasons']}")

    unshrunk, arms = None, None
    if not args.no_sensitivity:
        unshrunk = ewar.build(first=args.first, last=args.last, shrink=False)
        arms = {
            "fielding_swap_only": ewar.build(first=args.first, last=args.last,
                                             swap_pitching=False),
            "pitching_swap_only": ewar.build(first=args.first, last=args.last,
                                             swap_fielding=False),
        }

    ev = ewar.evaluate(model, unshrunk, last=args.eval_last, arms=arms)
    print(_fmt_gate1(ev["gate_1_team_wins"]))
    print(_fmt_gate2(ev["gate_2_pitcher_persistence"]))
    print(_fmt_gate3(ev["gate_3_coverage_identity"]))
    print(_fmt_sum(ev["accounting_league_sum"]))
    if "attribution_gate_1" in ev:
        a = ev["attribution_gate_1"]
        print("  ATTRIBUTION (gate 1, same rows)")
        for label in ("bwar_baseline", "fielding_swap_only",
                      "pitching_swap_only", "both_swaps_shipped"):
            blk = a.get(label) or {}
            print(f"    {label:<20} r {blk.get('r')}   "
                  f"MAE0 {blk.get('mae_zero_param')}   "
                  f"next-season r {blk.get('next_season_r')}")
    n = (ev["gate_1_team_wins"].get("next_season_wins") or {})
    if n:
        print(f"  NEXT-SEASON WINS  n={n['n']}  eWAR {n['r_ewar']:+.4f}   "
              f"bWAR {n['r_bwar']:+.4f}")
    if unshrunk is not None:
        s = ev["sensitivity_unshrunk_fielding"]["gate_1_team_wins"]
        print(f"  SENSITIVITY unshrunk fielding: gate 1 r {s['ewar']['r']:+.4f} "
              f"(shipped shrunk {ev['gate_1_team_wins']['ewar']['r']:+.4f}, "
              f"bWAR {s['bwar']['r']:+.4f})")
    print(f"  gates passed: {len(ev['gates_passed'])}, "
          f"failed: {len(ev['gates_failed'])}")
    for line in ev["gates_failed"]:
        print(f"    FAILED  {line}")

    payload = ewar.export_payload(model)
    print(f"  artifact: {payload['n_player_seasons']} player-seasons")
    if args.write:
        ewar.OUT.write_text(json.dumps(payload, separators=(",", ":")),
                            encoding="utf-8")
        ewar.EVAL_OUT.write_text(json.dumps(ev, indent=1), encoding="utf-8")
        print(f"  wrote {ewar.OUT.relative_to(ROOT)} "
              f"({ewar.OUT.stat().st_size / 1e6:.2f} MB)")
        print(f"  wrote {ewar.EVAL_OUT.relative_to(ROOT)} "
              f"({ewar.EVAL_OUT.stat().st_size / 1e3:.1f} KB)")
    else:
        print("  (dry run; pass --write to commit the artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
