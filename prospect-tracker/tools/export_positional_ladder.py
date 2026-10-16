# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
export_positional_ladder.py - publish the fitted defensive positional
adjustments to `positional-adjustments/` for Will's eWAR and SDR work.

READ-ONLY BY CONSTRUCTION. This slices `data/positional_fit.json`; it never
refits. positional_fit.fit_ladder is THE ladder (prospect_def_value.py states
the one-owner rule, and two independently refitted ladders once disagreed by
0.35 runs), so an exporter that computed its own copy would be a second owner
by the back door. If the artifact is missing this refuses rather than building
one.

BOTH BASES SHIP, NAMED. This is the module's recurring failure mode and the
export is the likeliest place to repeat it:

  * `values` is the exposure-weighted-zero column. Every internal valuation
    runs on it, and it is the one that matches the Baseball-Reference frame
    eWAR rides. USE THIS ONE unless you have a reason not to.
  * `values_fielder_centred` is the folklore-comparable column: the eight
    fielding rungs sum to zero and DH sits outside the sum. Display convention.

They differ by a single constant, so every GAP between two positions is
identical in both. Shipping one column without naming its basis is what
produced the "the ladder does not sum to zero" report the identification block
exists to answer, so the identification block ships with it.

THE THREE SUMS, because a receiver will otherwise "fix" one of them:
  * exposure-weighted over all nine rungs = 0, imposed by the fit.
  * equal-weight over nine rungs = -1.87, and SHOULD NOT be zero: DH is about
    9% of exposure, not a ninth, so equal-weighting over-counts its penalty.
  * equal-weight over the eight fielders on the model column = +11.83, which is
    forced arithmetically once the weighted sum is pinned.

V2, THE POSITION-SWITCHER LADDER (EWAR_LADDER_REDERIVE, 2026-10-15). The
bundle also carries positional_ladder_v2.json and .csv, sliced read-only from
data/positional_ladder_v2.json (ladder_v2.py), its read's record
data/positional_ladder_v2_eval.json and the read's verification
data/positional_ladder_v2_verify.json, and the README is generated here from the
payloads, so its tables cannot drift from the files beside it. v1 is current:
Position Fit, DEM+ and eWAR's S4 candidate read it. v2 served Position Fit for
one day and is a lab artifact under re-read since LADDER_V2_REVERT (2026-10-15),
because an all-zero fielding ladder scores as well on its own test.

Usage:
    python tools/export_positional_ladder.py            # write the bundle
    python tools/export_positional_ladder.py --check    # verify, write nothing
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "data" / "positional_fit.json"
V2_ARTIFACT = ROOT / "data" / "positional_ladder_v2.json"
V2_EVAL = ROOT / "data" / "positional_ladder_v2_eval.json"
V2_VERIFY = ROOT / "data" / "positional_ladder_v2_verify.json"
RECENCY_EVAL = ROOT / "data" / "positional_ladder_recency_eval.json"
OUT_DIR = ROOT.parent / "positional-adjustments"

#: Bumped by hand when the SHAPE changes, not when the numbers move. A refit is
#: a new `generated_at`, not a new schema version.
SCHEMA_VERSION = "1.0.0"

POS_ORDER = ("C", "SS", "2B", "3B", "CF", "LF", "RF", "1B", "DH")


def build(artifact: Path = ARTIFACT) -> dict:
    if not artifact.exists():
        raise SystemExit(f"FATAL: {artifact} not found. This exporter slices the "
                         "committed artifact and deliberately cannot refit it; "
                         "run positional_fit.py first.")
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    L = (doc.get("fit") or {}).get("ladder") or {}
    if not L.get("values"):
        raise SystemExit("FATAL: artifact carries no fit.ladder.values")

    ident = L.get("identification") or {}
    fb = L.get("folklore_basis") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_artifact": "prospect-tracker/data/positional_fit.json",
        "source_generated_at": doc.get("generated_at"),
        "model_id": "positional_ladder",
        "what_this_is": (
            "Defensive positional adjustments re-estimated from "
            "Baseball-Reference's own construction rather than taken from the "
            "folklore table. Least squares of BRef runs_position per 650 PA on "
            "per-row innings shares, no intercept, recentred so the "
            "exposure-weighted sum over all nine positions is zero."),
        "important": (
            "This is an INVERSION, not an independent measure of defensive "
            "difficulty. A rung reads as what Baseball-Reference PRICES that "
            "position at. For work that rides the bWAR frame (eWAR) that is the "
            "feature; for a from-scratch defensive model it is a constraint."),
        "units": L.get("units"),
        "method": L.get("method"),
        "bases": {
            "primary": "values",
            "values": {
                "basis": "exposure_weighted_zero",
                "use_for": ("everything that rides the bWAR frame, including "
                            "eWAR; this is what every internal valuation uses"),
                "values": {p: L["values"].get(p) for p in POS_ORDER
                           if L["values"].get(p) is not None},
            },
            "values_fielder_centred": {
                "basis": "fielder_centred_zero",
                "use_for": ("comparison against the published folklore table, "
                            "whose eight fielders also sum to zero with DH "
                            "outside it"),
                "values": {p: (ident.get("values_fielder_centred") or {}).get(p)
                           for p in POS_ORDER
                           if (ident.get("values_fielder_centred") or {}).get(p) is not None},
            },
            "note": ("the two differ by one constant, so every gap between two "
                     "positions is identical in both"),
        },
        "identification": ident,
        "ci95": L.get("ci95"),
        "fit": {
            "seasons": L.get("seasons"),
            "window_seasons": L.get("window_seasons"),
            "window_basis": L.get("window_basis"),
            "n_player_seasons": L.get("n_player_seasons"),
            "min_pa": L.get("min_pa"),
            "r2": L.get("r2"),
            "resid_sd": L.get("resid_sd"),
            "inn_per_pa": L.get("inn_per_pa"),
            "dh_exposure_spec": L.get("dh_exposure_spec"),
        },
        # The reliability constants ewar.py already consumes. SDR shrinkage will
        # want an equivalent, and they are the part of positional_fit Will's
        # fielding work actually touches.
        "signal_k_inn": {p: ((doc.get("fit") or {}).get("signal") or {}).get(p, {}).get("k_inn")
                         for p in POS_ORDER
                         if ((doc.get("fit") or {}).get("signal") or {}).get(p, {}).get("k_inn") is not None},
        "era_splits": L.get("era_splits"),
        "window_sensitivity": L.get("window_sensitivity"),
        "folklore_comparison": {
            "folklore_ladder_as_quoted": L.get("folklore_ladder"),
            "basis": fb,
            "read_this": (
                "the folklore table is quoted per full defensive season and "
                "ours per 650 PA of exposure, so subtracting them directly "
                "overstates folklore by about 14 percent. Both the raw and the "
                "rescaled comparison are published and neither is presented as "
                "the answer: the convention is ambiguous across sources, and "
                "the folklore ladder is FanGraphs/Tango while this fit inverts "
                "Baseball-Reference."),
        },
    }


def write(payload: dict, out_dir: Path = OUT_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    p_json = out_dir / "positional_ladder_v1.json"
    p_json.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    written.append(p_json)

    # CSV carries BOTH columns and their CI, because a one-column CSV is the
    # shape that loses the basis.
    p_csv = out_dir / "positional_ladder_v1.csv"
    prim = payload["bases"]["values"]["values"]
    fc = payload["bases"]["values_fielder_centred"]["values"]
    ci = payload.get("ci95") or {}
    with p_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["position", "runs_per_650pa_exposure_weighted",
                    "runs_per_650pa_fielder_centred", "ci95_low", "ci95_high"])
        for p in POS_ORDER:
            if prim.get(p) is None:
                continue
            lo, hi = (ci.get(p) or [None, None])[:2] or (None, None)
            w.writerow([p, prim.get(p), fc.get(p), lo, hi])
    written.append(p_csv)
    return written


def build_v2(artifact: Path = V2_ARTIFACT, eval_path: Path = V2_EVAL,
             verify_path: Path = V2_VERIFY) -> dict:
    """The v2 slice: the read's vector, both bases, its CI, the read's verdict, the
    comparison columns and the verification that withdrew it (LADDER_V2_REVERT).
    Read-only; refuses when any of the three files is missing."""
    for f in (artifact, eval_path, verify_path):
        if not f.exists():
            raise SystemExit(f"FATAL: {f} not found. Run tools/ladder_v2_lab.py --read "
                             "(once) and python ladder_v2.py first.")
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    ev = json.loads(eval_path.read_text(encoding="utf-8"))
    vals = doc.get("values") or {}
    ident = doc.get("identification") or {}
    t = ev.get("tests") or {}
    ver = json.loads(verify_path.read_text(encoding="utf-8"))
    vz = ver.get("zero_ladder") or {}
    vs = ver.get("savant_centring") or {}

    def _test(k):
        d = t.get(k) or {}
        return None if not d else {"dmae": d.get("dmae"), "ci95": d.get("ci95"),
                                   "n_rows": d.get("n_rows"), "n_players": d.get("n_players")}
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_artifact": "prospect-tracker/data/positional_ladder_v2.json",
        "source_eval": "prospect-tracker/data/positional_ladder_v2_eval.json",
        "read_at": ev.get("read_at"),
        "model_id": "positional_ladder_v2",
        "gate": doc.get("gate"),
        "status": doc.get("status"),
        "what_this_is": (
            "The positional adjustment measured on players who changed position: the "
            "fielding runs the same player gains or loses when he moves, fit separately "
            "on Baseball-Reference runs_field, FanGraphs fld and Statcast fielding runs "
            "prevented, then pooled by inverse variance. Catcher keeps the v1 rung "
            "(too few catchers change position); DH is first base plus the first-base "
            "fielding of the players who DH."),
        "units": doc.get("units"),
        "method": doc.get("method"),
        "bases": {
            "primary": "values",
            "values": {"basis": "exposure_weighted_zero",
                       "values": {p: vals.get(p) for p in POS_ORDER if vals.get(p) is not None}},
            "values_fielder_centred": {
                "basis": "fielder_centred_zero",
                "values": {p: (ident.get("values_fielder_centred") or {}).get(p)
                           for p in POS_ORDER
                           if (ident.get("values_fielder_centred") or {}).get(p) is not None}},
            "note": ("the two differ by one constant, so every gap between two positions "
                     "is identical in both"),
        },
        "identification": ident,
        "ci95": doc.get("ci95"),
        "ci_draws": doc.get("ci_draws"),
        "seasons": doc.get("seasons"),
        "c_branch": doc.get("c_branch"),
        "dh_mu": doc.get("dh_mu"),
        "source_fits": doc.get("source_fits"),
        "era_splits": doc.get("era_splits"),
        "verdict": ev.get("verdict"),
        "held_out_test": {
            "v1_minus_v2_pooled": _test("v1_minus_b_pooled"),
            "v1_minus_v2_next_season_form": _test("v1_minus_b_across"),
            "v1_minus_v2_by_source": {s: _test_d(d) for s, d in
                                      (t.get("v1_minus_b_by_source") or {}).items()},
            "v2_minus_per_season_shrunk": _test("b_minus_d_b_pooled"),
            "read_this": ("dMAE = MAE(first) - MAE(second) in runs per 650 PA on players who "
                          "changed position, each season 2016-2026 held out in turn; positive "
                          "favours the second"),
        },
        "comparison": ev.get("comparison"),
        "verification": {
            "source": "prospect-tracker/data/positional_ladder_v2_verify.json",
            "generated_at": ver.get("generated_at"),
            "finding": ver.get("finding"),
            "zero_minus_v2": _test_d((vz.get("tests") or {}).get("zero_minus_b")),
            "v1_minus_zero": _test_d((vz.get("tests") or {}).get("v1_minus_zero")),
            "mae_pooled": vz.get("mae_pooled"),
            "mae_by_scale": vz.get("mae_by_scale"),
            "savant_league_rate_per_1277_7_inn": {
                p: (r or {}).get("pooled_2016_2026")
                for p, r in (vs.get("savant_league_rate_per_1277_7_inn") or {}).items()},
            "cf_minus_ss_by_source_leg": {
                k: (v or {}).get("CF_minus_SS")
                for k, v in ((ver.get("bridges") or {}).get("legs") or {}).items()},
            "read_this": ("zero is a ladder with every fielding position at 0 (C and DH as "
                          "v2's), scored on the read's own rows, folds and draws; dMAE = "
                          "MAE(first) - MAE(second), positive favours the second"),
        },
    }


def _test_d(d):
    return None if not d else {"dmae": d.get("dmae"), "ci95": d.get("ci95"),
                               "n_rows": d.get("n_rows"), "n_players": d.get("n_players")}


def write_v2(payload: dict, out_dir: Path = OUT_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    p_json = out_dir / "positional_ladder_v2.json"
    p_json.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    written.append(p_json)
    p_csv = out_dir / "positional_ladder_v2.csv"
    prim = payload["bases"]["values"]["values"]
    fc = payload["bases"]["values_fielder_centred"]["values"]
    ci = payload.get("ci95") or {}
    cols = ((payload.get("comparison") or {}).get("columns") or {})
    v1 = cols.get("v1_served") or {}
    fg = cols.get("fg_table_rescaled") or {}
    with p_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["position", "runs_per_650pa_exposure_weighted",
                    "runs_per_650pa_fielder_centred", "ci95_low", "ci95_high",
                    "v1_bref_inversion_exposure_weighted", "fangraphs_table_rescaled"])
        for p in POS_ORDER:
            if prim.get(p) is None:
                continue
            lo, hi = (ci.get(p) or [None, None])[:2]
            w.writerow([p, prim.get(p), fc.get(p), lo, hi, v1.get(p), fg.get(p)])
    written.append(p_csv)
    return written


def _f(v, dp=2, sign=True):
    if v is None:
        return "-"
    return f"{float(v):+.{dp}f}" if sign else f"{float(v):.{dp}f}"


def render_readme(v1: dict, v2: dict, recency: dict | None = None) -> str:
    """README.md for the bundle, generated from the two payloads (and the v1 window
    gate's record), so every number in it is the files'. v1 is the current ladder;
    v2 is a lab artifact under re-read (LADDER_V2_REVERT, 2026-10-15)."""
    p1 = v1["bases"]["values"]["values"]
    f1 = v1["bases"]["values_fielder_centred"]["values"]
    i1 = v1.get("identification") or {}
    fit1 = v1.get("fit") or {}
    shift1 = round(p1["C"] - f1["C"], 2)
    p2 = v2["bases"]["values"]["values"]
    f2 = v2["bases"]["values_fielder_centred"]["values"]
    ci2 = v2.get("ci95") or {}
    i2 = v2.get("identification") or {}
    ht = v2.get("held_out_test") or {}
    pool = ht.get("v1_minus_v2_pooled") or {}
    nxt = ht.get("v1_minus_v2_next_season_form") or {}
    by_src = ht.get("v1_minus_v2_by_source") or {}
    ver = v2.get("verification") or {}
    zb = ver.get("zero_minus_v2") or {}
    v1z = ver.get("v1_minus_zero") or {}
    scale = ver.get("mae_by_scale") or {}
    rate = ver.get("savant_league_rate_per_1277_7_inn") or {}
    legs = ver.get("cf_minus_ss_by_source_leg") or {}
    src_name = {"BREF": "Baseball-Reference", "FG": "FanGraphs", "SAVANT": "Statcast"}
    nC = max([(f or {}).get("n_c_change") or 0 for f in (v2.get("source_fits") or {}).values()] or [0])
    rec = ((recency or {}).get("results") or {}).get("challenger_w") or {}
    per = (recency or {}).get("per_season") or {}
    L = []
    a = L.append
    a("# Defensive positional adjustments")
    a("")
    a("Fitted positional adjustments from eephus.io, published for Will's eWAR and SDR")
    a("work. Generated by:")
    a("")
    a("    python prospect-tracker/tools/export_positional_ladder.py")
    a("")
    a("**v1 is the current ladder.** It is the one Position Fit (the Alchemy Lab),")
    a("DEM+'s Pos (ours) and prospect defensive value use. v2 is a lab artifact under")
    a("re-read; do not take it up.")
    a("")
    a("Files:")
    a("")
    a("| file | what it is |")
    a("| --- | --- |")
    a("| `positional_ladder_v1.json` | v1, current: the ladder fitted on Baseball-Reference's positional runs, both bases, CIs, era splits, window sensitivity, the identification block, the folklore comparison |")
    a("| `positional_ladder_v1.csv` | v1's two ladders plus CI, one row per position |")
    a("| `positional_ladder_v2.json` | v2, lab artifact under re-read: the position-switcher ladder, both bases, CIs, its read, the verification that withdrew it, era and source splits |")
    a("| `positional_ladder_v2.csv` | v2's two bases plus CI, beside v1 and the FanGraphs table, one row per position |")
    a("")
    a("Both are in runs per 650 PA of exposure, relative to the league-average")
    a("defensive position (an exposure-weighted zero over all nine rungs).")
    a("")
    a("## v1: the current ladder, fitted on Baseball-Reference's positional runs")
    a("")
    a("| Pos | Exposure-weighted | Fielder-centred |")
    a("| --- | ---: | ---: |")
    for p in POS_ORDER:
        a(f"| {p} | {_f(p1.get(p))} | {_f(f1.get(p))} |")
    a("")
    a("**Use the exposure-weighted column** unless you have a specific reason not to.")
    a("It is the basis that matches the Baseball-Reference frame eWAR rides, and it is")
    a("what DEM+'s Pos (ours) runs on.")
    a("")
    a(f"The two columns differ by a single constant ({abs(shift1):.2f} runs), so every GAP between")
    a("two positions is identical in both. Only the zero point moves.")
    a("")
    a("### Three sums, and only one of them is zero")
    a("")
    a("This is the part that generates bug reports, so it is worth reading once.")
    a("")
    a("- **Exposure-weighted over all nine rungs = 0.** Imposed by the fit. This is the")
    a("  only sum that is a constraint.")
    a(f"- **Equal-weight over nine rungs = {_f(i1.get('sum_equal_weight_9'), 2)}.** Not a defect. DH is about "
      f"{100 * float((i1.get('exposure_share') or {}).get('DH') or 0):.0f}% of")
    a("  league exposure, not one ninth, so equal-weighting over-counts its large")
    a("  negative rung.")
    a("- **Equal-weight over the eight fielders, on the exposure-weighted column =")
    a(f"  {_f(i1.get('sum_equal_weight_fielders'), 2)}.** Also not a defect: once the weighted sum is pinned at zero, this")
    a("  value is forced arithmetically.")
    a("")
    a("On the fielder-centred column the eight fielders do sum to zero, with DH outside")
    a("the sum. That is the folklore convention and it is why that column exists.")
    a("")
    a("### What v1 is, and what it is not")
    a("")
    a("The ladder is a least-squares **inversion** of Baseball-Reference's own")
    a("`runs_position` per 650 PA on per-row innings shares, no intercept, recentred so")
    a(f"the exposure-weighted sum is zero. Fit: {(fit1.get('seasons') or ['?', '?'])[0]}-"
      f"{(fit1.get('seasons') or ['?', '?'])[1]}, n={fit1.get('n_player_seasons') or 0:,}")
    a(f"player-seasons, min {fit1.get('min_pa')} PA, R-squared {_f(fit1.get('r2'), 3, False)}.")
    a("")
    a("So a rung reads as **what Baseball-Reference prices that position at**, not as")
    a("an independent measure of how hard the position is to play. v2 tried to be that")
    a("measure and is under re-read (below).")
    a("")
    if rec.get("dmae_mean") is not None:
        ci = rec.get("ci95") or [None, None]
        better = sum(1 for v in per.values() if (v.get("dmae_w") or 0) > 0)
        a("The rolling six-season window is a measured choice, not an assumption: it beat")
        a(f"the 2012-onward pool by {_f(rec['dmae_mean'], 2, False)} runs per 650 PA of held-out error (bootstrap")
        a(f"interval {_f(ci[0], 3, False)} to {_f(ci[1], 3, False)}, better in {better} of {len(per)} held-out seasons) under a")
        a("pre-registered forward-chained gate.")
        a("")
    a("Era drift is real and larger than the sampling intervals, which is why the")
    a("window rolls. `era_splits` in the JSON carries the per-era rungs.")
    a("")
    a("### The folklore comparison, and its trap")
    a("")
    a("`folklore_comparison` in the v1 JSON holds the FanGraphs/Tango table everyone")
    a("quotes (C +12.5, SS +7.5, 2B/3B/CF +2.5, LF/RF -7.5, 1B -12.5, DH -17.5).")
    a("")
    a("**Do not subtract it from ours directly.** That table is quoted per full")
    a("defensive season (162 games, 1,458 innings); ours is per 650 PA of exposure,")
    a("about 1,278 innings. The JSON carries both the raw table and a rescaled one,")
    a("and neither is presented as the answer: the convention is ambiguous across")
    a("sources, and the folklore table is the FanGraphs ladder while v1 inverts")
    a("Baseball-Reference.")
    a("")
    a("## v2: the position-switcher ladder (lab artifact, under re-read)")
    a("")
    a("Status: " + str(v2.get("status") or "not current") + ".")
    a("")
    a("| Pos | Exposure-weighted | Fielder-centred | 95% CI |")
    a("| --- | ---: | ---: | --- |")
    for p in POS_ORDER:
        c = ci2.get(p) or [None, None]
        a(f"| {p} | {_f(p2.get(p))} | {_f(f2.get(p))} | {_f(c[0])} to {_f(c[1])} |")
    a("")
    a("**What it tried to measure.** How many fielding runs the same players gain or")
    a("lose when they change position, on three fielding sources fit one at a time")
    a("(Baseball-Reference runs_field, FanGraphs fld, Statcast fielding runs")
    a("prevented) and pooled by inverse variance, seasons "
      + f"{(v2.get('seasons') or ['?', '?'])[0]}-{(v2.get('seasons') or ['?', '?'])[1]}. For a player with 300 or more")
    a("fielded innings in two straight seasons, his fielding runs per 650 PA of")
    a("innings are fit on last season's rate, his age and the change in where he")
    a("played; Statcast adds same-season pairs.")
    a("")
    a("**Its read.** One registered read (`prospect-tracker/docs/ewar/LADDER_V2_GATE.md`):")
    a("each season 2016-2026 held out in turn, predicting the fielding plus positional")
    a(f"runs of players who changed position, v2's error was {_f(pool.get('dmae'), 3, False)} runs per 650 PA lower")
    a(f"than v1's refit on the same seasons (95% CI {_f((pool.get('ci95') or [None])[0], 3, False)} to "
      f"{_f((pool.get('ci95') or [None, None])[1], 3, False)}; {pool.get('n_rows') or 0:,} rows, "
      f"{pool.get('n_players') or 0:,} players). Next-season rows")
    a(f"alone: {_f(nxt.get('dmae'), 3, False)} ({_f((nxt.get('ci95') or [None])[0], 3, False)} to "
      f"{_f((nxt.get('ci95') or [None, None])[1], 3, False)}). By source: "
      + ", ".join(f"{src_name.get(k, k)} {_f((d or {}).get('dmae'), 3, False)}" for k, d in by_src.items()) + ".")
    a("")
    a("**Why it was withdrawn.** The read's pass rule compared v2 only with v1. The")
    a("verification (`prospect-tracker/tools/ladder_v2_verify.py`) reran the same test")
    a("with a ladder that puts every fielding position at zero:")
    a("")
    a(f"- Zero ties v2: zero's error was {_f(zb.get('dmae'), 3, False)} runs per 650 PA higher than v2's")
    a(f"  (95% CI {_f((zb.get('ci95') or [None])[0], 3)} to {_f((zb.get('ci95') or [None, None])[1], 3)}), and "
      f"{_f(v1z.get('dmae'), 3, False)} lower than v1's. The read")
    a("  measured what v1's spread costs on this test, not a ladder v2 measured.")
    a("- Shrinking v1 toward zero lowers this test's error at every step (x1.0, x0.5, x0: "
      f"{_f((scale.get('v1') or {}).get('1.0'), 3, False)}, {_f((scale.get('v1') or {}).get('0.5'), 3, False)}, "
      f"{_f((scale.get('v1') or {}).get('0.0'), 3, False)});")
    a(f"  v2's error barely moves ({_f((scale.get('b') or {}).get('1.0'), 3, False)}, "
      f"{_f((scale.get('b') or {}).get('0.5'), 3, False)}, {_f((scale.get('b') or {}).get('0.0'), 3, False)}).")
    a("- The DH rung enters no scored row, and catcher barely enters one.")
    a("- Statcast's fielding runs are not centred within a position: per 1,277.7 innings")
    a(f"  the league books {_f(rate.get('CF'))} in CF, "
      f"{_f(rate.get('LF'))} in LF and "
      f"{_f(rate.get('RF'))} in RF.")
    a("- The infield and outfield levels rest on the few dozen players who moved")
    a("  between them, and CF reads above SS on most source legs (CF minus SS: "
      + ", ".join(f"{src_name.get(k.replace('_centred', ''), k)}{' centred' if k.endswith('_centred') else ''} "
                  f"{_f(v)}" for k, v in legs.items()) + ").")
    a("")
    a("**Catcher and DH.** "
      + (f"Too few catchers change position to measure their rung ({nC} rows), so C keeps"
         if v2.get("c_branch") == "carried_from_v1" else "C is measured on the catchers who changed position;"))
    a(("v1's offset to the average fielder. " if v2.get("c_branch") == "carried_from_v1" else "")
      + f"DH is first base plus the first-base fielding of the")
    a(f"players who DH ({_f(v2.get('dh_mu'))} runs per 650 PA).")
    a("")
    a("**Bases.** The two v2 bases differ by")
    a(f"one constant ({_f(round(p2['C'] - f2['C'], 2))} runs); only the exposure-weighted sum is zero")
    a(f"(equal-weight over nine rungs {_f(i2.get('sum_equal_weight_9'))}, over the eight fielders "
      f"{_f(i2.get('sum_equal_weight_fielders'))}).")
    a("")
    a("## Reliability constants")
    a("")
    a("`signal_k_inn` in the v1 JSON carries the per-position innings constants")
    a("`ewar.py` already consumes for shrinkage. SDR needs an equivalent.")
    a("")
    a("## Provenance")
    a("")
    a("v1 is sliced read-only from `prospect-tracker/data/positional_fit.json`")
    a("(`fit.ladder`); v2 from `prospect-tracker/data/positional_ladder_v2.json`, the")
    a("record of its one read, `prospect-tracker/data/positional_ladder_v2_eval.json`,")
    a("and its verification, `prospect-tracker/data/positional_ladder_v2_verify.json`.")
    a("The exporter refits nothing. `source_generated_at` and `read_at` in the JSON")
    a("are the artifacts' own stamps.")
    a("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="build and validate, write nothing")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    payload = build()
    prim = payload["bases"]["values"]["values"]
    fc = payload["bases"]["values_fielder_centred"]["values"]
    if len(prim) != 9:
        raise SystemExit(f"FATAL: expected 9 rungs, got {sorted(prim)}")
    # The export must not be the place a basis silently collapses: the two
    # columns have to differ by ONE constant across every position.
    shifts = {round(prim[p] - fc[p], 6) for p in prim if fc.get(p) is not None}
    if len(shifts) != 1:
        raise SystemExit(f"FATAL: the two bases differ by more than one "
                         f"constant ({sorted(shifts)}); they are not the same "
                         f"ladder and must not ship as one export")
    print(f"ladder ok: 9 rungs, bases differ by a single constant "
          f"{shifts.pop():+.4f}")
    v2 = build_v2()
    p2 = v2["bases"]["values"]["values"]
    f2 = v2["bases"]["values_fielder_centred"]["values"]
    if len(p2) != 9:
        raise SystemExit(f"FATAL: v2 carries {sorted(p2)}, not nine rungs")
    s2 = {round(p2[p] - f2[p], 2) for p in p2 if f2.get(p) is not None}
    if len(s2) != 1:
        raise SystemExit(f"FATAL: v2's two bases differ by more than one constant ({sorted(s2)})")
    print(f"v2 ok: 9 rungs, bases differ by a single constant {s2.pop():+.2f}")
    recency = (json.loads(RECENCY_EVAL.read_text(encoding="utf-8"))
               if RECENCY_EVAL.exists() else None)
    readme = render_readme(payload, v2, recency)
    if args.check:
        print("--check: nothing written")
        return 0
    for p in write(payload, args.out) + write_v2(v2, args.out):
        print(f"wrote {p}")
    rp = args.out / "README.md"
    rp.write_text(readme, encoding="utf-8")
    print(f"wrote {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
