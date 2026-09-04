# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Build eWAR v2 -> data/ewar.json + data/ewar_eval.json.

    python tools/build_ewar.py                 # build + gates, print, write nothing
    python tools/build_ewar.py --write         # ...and commit both artifacts
    python tools/build_ewar.py --first 2011 --last 2026 --write
    python tools/build_ewar.py --no-sensitivity --write

The only network call is pybaseball's cached bwar_bat / bwar_pitch static CSV
pull (--force-fetch to bypass the local 7-day pickle cache). Everything else -
the FIP corpus, Statcast OAA, fielding innings, the k_inn constants, the
standings used by the team-wins gate - is read from disk.

TWO WINDOWS, on purpose, since 2026-09-03.
  * BUILD window (--first/--last, default 2011..current year): the seasons the
    artifact carries. 2011 is the first season the eFV first-6yr label pool
    reaches (debuts.json backfill), and the FIP corpus prices it in full:
    707/707, 721/723, 724/729, 743/748, 808/810 war_daily pitcher rows FIP-
    priced for 2011..2015, ip_share 1.0000 each season (build 2026-09-03).
    Fielding is all-fallback before 2016 (no Statcast OAA), which at the
    shipped fielding_blend_w of 0.0 changes nothing: position players carry
    bWAR exactly in EVERY season until the SDR defense drop lands.
  * GATE window (--eval-first/--eval-last, default 2016..last completed
    season): the seasons the validity gates score. It stays 2016-2025 so the
    gate record (team wins r 0.8595 vs 0.8803, persistence 0.3617 vs 0.1768)
    remains comparable across rebuilds; extending the BUILD window must not
    silently move the GATE window, which is what evaluate()'s default (first =
    the model's first season) would do.
  The full-build accounting (league sum per season over EVERY built season) is
  printed and written beside the windowed block so the pre-2016 seasons are
  still checked, just not scored.

OWNER DECISION 2026-09-03: eWAR v2 becomes the SERVED and LABEL WAR site-wide
(the basis shift). bWAR remains the INPUT frame this is built on. The build is
arithmetic on inputs, so that decision changes nothing here except that the
artifact must now cover the label window; the consumer wiring is other lanes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ewar                              # noqa: E402

# First season the served artifact must carry. The eFV first-6yr label pool
# reaches back to 2011 debuts, and the label series has to exist for every
# season a label sums over, so the artifact starts where the labels start.
# ewar.DEFAULT_FIRST_SEASON (2016) stays the GATE anchor: it is the OAA era
# the shipped gate record was measured on, not the label window.
LABEL_FIRST_SEASON = 2011


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


def _fmt_build(model: dict, payload: dict) -> str:
    """Per built season: player-seasons in the artifact, pitcher rows and the
    FIP-priced share. This is the coverage table for the WHOLE build, printed
    because gate 3 only reports the gate window."""
    per: dict[int, int] = {}
    for by_year in payload["players"].values():
        for s in by_year:
            per[int(s)] = per.get(int(s), 0) + 1
    pit = model["meta"]["pitching"]["by_season"]
    lines = ["  BUILD  player-seasons and FIP coverage per season"]
    for season in sorted(per):
        p = pit.get(season) or pit.get(str(season)) or {}
        lines.append(f"    {season}  player-seasons {per[season]:>5}   "
                     f"pitcher rows FIP-priced {p.get('n_covered', 0):>4}/"
                     f"{p.get('n_rows', 0):<4}  ip_share {p.get('ip_share', 0.0):.4f}")
    return "\n".join(lines)


def _fmt_sum(g: dict, title: str = "league WAR sum per season") -> str:
    lines = [f"  ACCOUNTING  {title}"]
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
    ap.add_argument("--first", type=int, default=LABEL_FIRST_SEASON,
                    help="first BUILT season (default 2011, the label window)")
    ap.add_argument("--last", type=int, default=None)
    ap.add_argument("--write", action="store_true", help="write both artifacts")
    ap.add_argument("--force-fetch", action="store_true",
                    help="bypass the local bwar pickle cache")
    ap.add_argument("--no-sensitivity", action="store_true",
                    help="skip the unshrunk-fielding sensitivity build")
    ap.add_argument("--eval-first", type=int, default=ewar.DEFAULT_FIRST_SEASON,
                    help="first season the GATES score (default 2016, the OAA "
                         "era the shipped gate record was measured on)")
    ap.add_argument("--eval-last", type=int, default=None,
                    help="last COMPLETED season for the gates (default: last year)")
    args = ap.parse_args()
    if args.eval_first < args.first:
        ap.error(f"--eval-first {args.eval_first} precedes --first {args.first}; "
                 f"the gates cannot score seasons that were not built")

    model = ewar.build(first=args.first, last=args.last,
                       shrink=True, force_fetch=args.force_fetch)
    print(f"eWAR v2: {len(model['rows'])} war_daily rows, "
          f"seasons {model['meta']['seasons']}")

    unshrunk, arms = None, None
    if not args.no_sensitivity:
        # AT w=1.0 EXPLICITLY, for the same reason fielding_swap_only is, and
        # this line got the trap the comment below was written about. The OAA
        # reliability shrinkage multiplies the STATCAST fielding term; at the
        # shipped w of 0.0 that term is multiplied by zero, so an unshrunk build
        # at the default is bit-identical to the shipped build and the whole
        # sensitivity block reproduced gate 1 to the last decimal while claiming
        # to test something. Verified: r 0.8595 / mae0 4.306 in BOTH arms.
        # The shrinkage question only exists where the Statcast read is used.
        unshrunk = ewar.build(first=args.first, last=args.last, shrink=False,
                              fielding_blend_w=1.0)
        arms = {
            # AT w=1.0 EXPLICITLY. The shipped default became 0.0 on 2026-08-04
            # (the w grid found both forward legs monotone decreasing in w), so
            # an arm built at the default would apply no Statcast fielding at
            # all and come back as bWAR wearing the label "fielding_swap_only".
            # That reads as "the fielding swap is fine now" and is the exact
            # opposite of what was measured. This arm exists to answer "what
            # does the Statcast fielding swap DO", so it must ask at full
            # strength regardless of what the default happens to be.
            "fielding_swap_only": ewar.build(first=args.first, last=args.last,
                                             swap_pitching=False,
                                             fielding_blend_w=1.0),
            "pitching_swap_only": ewar.build(first=args.first, last=args.last,
                                             swap_fielding=False),
        }

    ev = ewar.evaluate(model, unshrunk, first=args.eval_first,
                       last=args.eval_last, arms=arms)
    # The gates are windowed (eval_window). The accounting identity has to hold
    # on every season the artifact SERVES, so it is also run on the whole build
    # and written beside the windowed block under its own key.
    ev["accounting_league_sum_build_window"] = {
        "build_window": list(model["meta"]["seasons"]),
        "why": "eval_window scores the gates; this block checks the league-sum "
               "identity on every built season, including the pre-2016 label "
               "seasons the gates do not score. The in-progress last season "
               "is scaled against season-to-date team-games, so its "
               "replacement_scale reads near 1.0 only when the war_daily pull "
               "and the standings blob are from the same day (2026-09-03: "
               "0.9997 fresh, 1.2672 with an Aug 4 pull against a Sep 3 "
               "blob). A scale far from 1.0 there says refresh the pull; it "
               "is not a break in the identity.",
        **ewar.gate_league_sum(model),
    }
    print(_fmt_gate1(ev["gate_1_team_wins"]))
    print(_fmt_gate2(ev["gate_2_pitcher_persistence"]))
    print(_fmt_gate3(ev["gate_3_coverage_identity"]))
    print(_fmt_sum(ev["accounting_league_sum"],
                   f"league WAR sum per season, gate window {ev['eval_window']}"))
    print(_fmt_sum(ev["accounting_league_sum_build_window"],
                   f"league WAR sum per season, build window {model['meta']['seasons']}"))
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
    print(_fmt_build(model, payload))
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
