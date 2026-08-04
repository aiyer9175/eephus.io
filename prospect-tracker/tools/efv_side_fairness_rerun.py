"""R4.3 -- re-run the standing eFV 3.4 F-SIDE side-fairness eval and (optionally)
decompose the delta into a lambda leg and a data-drift leg.

WHY THIS EXISTS
---------------
The F-SIDE artifact (data/xfv_side_fairness_eval.json) is the standing gate that
governs the joint top-band side mix. It is produced inside efv_model.run() as a
by-product, so the only way to refresh it used to be a full eval run, and the
only record of a re-run lived in whatever scratch directory the session used.
The 2026-08-04 audit found the shipped artifact stamped on lambdas
{hit 0.85, pit 0.54} while the served model had moved to {hit 0.70, pit 0.57}
(efv_model._BLEND_LAMBDA_RESELECT), i.e. the gate was scored on a configuration
that does not exist. This runner makes the refresh a one-liner and makes the
lambda-vs-drift decomposition reproducible.

MEASUREMENT NOTE (do not skip)
------------------------------
Comparing today's artifact against a stamp from N days ago confounds TWO things:
the lambda change and N days of matrix / label drift. --control re-runs the same
line on TODAY's rows at the OLD stamped lambdas, which isolates the lambda leg.
Anything that survives the control is drift, not the lambda move.

USAGE
  python tools/efv_side_fairness_rerun.py                 # dry run, no writes
  python tools/efv_side_fairness_rerun.py --persist       # rewrite the artifact
  python tools/efv_side_fairness_rerun.py --control 0.85 0.54   # lambda leg
  python tools/efv_side_fairness_rerun.py --out PATH      # write elsewhere

This module is measurement-only: it imports efv_model and calls the existing
_side_fairness_eval. It edits no model code and writes no player payload.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fmt_ci(ci):
    if not ci:
        return "n/a"
    return "[%.2f, %.2f]" % (ci[0], ci[1])


def _excludes_zero(ci) -> bool:
    return bool(ci) and (ci[0] * ci[1] > 0)


def summarize(art: dict) -> dict:
    """The numbers the S1 gate and the B1-B4 clauses actually turn on."""
    full = art["frames"]["full_pool_km"]
    top = full["joint_bands_display_grade"]["001-025"]
    boot = top["boot"]
    br = art["binding_rules"]
    return {
        "generated_at": art["generated_at"],
        "lambdas": art["protocol"]["lambdas"],
        "lambda_source": art["protocol"]["lambda_source"],
        "n_hit": full["n_hit"], "n_pit": full["n_pit"],
        "top25_n_hit": top["hit"]["n"], "top25_n_pit": top["pit"]["n"],
        "mean_diff": boot["mean_diff"], "mean_ci90": boot["mean_ci90"],
        "mean_se": boot["mean_se"],
        "median_diff": boot["median_diff"], "median_ci90": boot["median_ci90"],
        "median_se": boot["median_se"],
        "p_hit_gt_pit": boot["p_hit_gt_pit"],
        "mean_ci90_excludes_zero": _excludes_zero(boot["mean_ci90"]),
        "median_ci90_excludes_zero": _excludes_zero(boot["median_ci90"]),
        "B1_pass": br["B1_fold_sign_agreement"]["pass"],
        "B2_pass": br["B2_dual_frame_sign"]["pass"],
        "B3_pass": br["B3_ipcw_identity_where_uncensored"].get("pass"),
        "B4_coded_pass": br["B4_ci90_excludes_zero"]["pass"],
        "S4_all_negative": art["standing_gates"][
            "S4_midband_pit_outperformance"]["sign_now_all_negative"],
        "S5_tripped": art["standing_gates"][
            "S5_fold_guards_and_2024_tripwire"]["first_trainable_2024_fold"]["tripped"],
    }


def report(tag: str, s: dict) -> None:
    print("\n=== %s ===" % tag)
    print("  generated_at %s   lambdas %s   (%s)"
          % (s["generated_at"], json.dumps(s["lambdas"]), s["lambda_source"]))
    print("  pool n hit/pit %s/%s   top-25 hit/pit %s/%s"
          % (s["n_hit"], s["n_pit"], s["top25_n_hit"], s["top25_n_pit"]))
    print("  top-25 hit-minus-pit MEAN   %+.2f  CI90 %s  SE %.3f  excludes0 %s"
          % (s["mean_diff"], _fmt_ci(s["mean_ci90"]), s["mean_se"],
             s["mean_ci90_excludes_zero"]))
    print("  top-25 hit-minus-pit MEDIAN %+.2f  CI90 %s  SE %.3f  excludes0 %s"
          % (s["median_diff"], _fmt_ci(s["median_ci90"]), s["median_se"],
             s["median_ci90_excludes_zero"]))
    print("  p(hit>pit) %.3f" % s["p_hit_gt_pit"])
    # Label corrected 2026-08-04: B4 now tests BOTH co-primary legs (the check
    # used to read the mean only and ignore the median it stamped).
    print("  B1 %s  B2 %s  B3 %s  B4(mean AND median) %s"
          % (s["B1_pass"], s["B2_pass"], s["B3_pass"], s["B4_coded_pass"]))
    print("  S4 mid-band all-negative %s   S5 2024 tripwire tripped %s"
          % (s["S4_all_negative"], s["S5_tripped"]))
    if s["B4_coded_pass"] and not s["median_ci90_excludes_zero"]:
        print("  ** CLAUSE-SCOPE DEFECT: S1 names mean AND median co-primary, but the")
        print("     coded B4 check tests the MEAN leg only. The MEDIAN CI90 includes 0,")
        print("     so B4 reports pass on a clause its own code does not evaluate.")


def run_once(lam_override=None, persist=False, out_path=None) -> dict:
    """One F-SIDE computation. lam_override={'hit':x,'pit':y} runs the control leg."""
    os.chdir(ROOT)
    import efv_model as em

    em._SF_CACHE.clear()
    if lam_override is not None:
        lam = {"hit": float(lam_override["hit"]), "pit": float(lam_override["pit"])}
        em._sf_live_lambdas = lambda: (
            lam, "CONTROL override (efv_side_fairness_rerun --control)")
    t0 = time.time()
    art = em._side_fairness_eval(persist=persist, out_path=out_path)
    print("  computed in %.1fs" % (time.time() - t0))
    return art


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--persist", action="store_true",
                    help="rewrite data/xfv_side_fairness_eval.json (default: dry run)")
    ap.add_argument("--out", default=None,
                    help="write the artifact to this path instead of the shipped one")
    ap.add_argument("--control", nargs=2, type=float, metavar=("HIT", "PIT"),
                    default=None,
                    help="also run the same line on today's rows at these OLD lambdas, "
                         "to split the delta into a lambda leg and a drift leg")
    args = ap.parse_args(argv)

    os.chdir(ROOT)
    import efv_model as em

    print("shipped _BLEND_LAMBDA_RESELECT pin:", json.dumps(em._BLEND_LAMBDA_RESELECT))
    lam, src = em._sf_live_lambdas()
    print("stamped live lambdas: %s  (%s)" % (json.dumps(lam), src))
    if lam != {k: float(v) for k, v in em._BLEND_LAMBDA_RESELECT.items()
               if v is not None}:
        print("WARNING: the stamped live lambdas do not match the served pin. The "
              "F-SIDE gate would be scored on a configuration that is not shipped.")

    persist = bool(args.persist or args.out)
    out_path = Path(args.out) if args.out else None
    shipped = summarize(run_once(persist=persist, out_path=out_path))
    report("SHIPPED LAMBDAS %s" % json.dumps(lam), shipped)
    if persist:
        print("  wrote %s" % (out_path or (ROOT / "data" / "xfv_side_fairness_eval.json")))
    else:
        print("  (dry run: nothing written; pass --persist to rewrite the artifact)")

    if args.control:
        ctrl = summarize(run_once(
            lam_override={"hit": args.control[0], "pit": args.control[1]},
            persist=False))
        report("CONTROL LAMBDAS %s (today's rows)" % json.dumps(ctrl["lambdas"]), ctrl)
        print("\n=== DECOMPOSITION (same rows, lambda leg only) ===")
        print("  mean   control %+.2f -> shipped %+.2f   lambda leg %+.2f"
              % (ctrl["mean_diff"], shipped["mean_diff"],
                 shipped["mean_diff"] - ctrl["mean_diff"]))
        print("  median control %+.2f -> shipped %+.2f   lambda leg %+.2f"
              % (ctrl["median_diff"], shipped["median_diff"],
                 shipped["median_diff"] - ctrl["median_diff"]))
        print("  median CI90 excludes 0: control %s -> shipped %s"
              % (ctrl["median_ci90_excludes_zero"],
                 shipped["median_ci90_excludes_zero"]))
        if not ctrl["median_ci90_excludes_zero"]:
            print("  NOTE: the control already fails the median exclusion, so that loss "
                  "is DATA DRIFT, not the lambda change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
