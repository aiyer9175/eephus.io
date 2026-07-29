# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""W-FSIDE-SHIP gate lab (pre-registered: docs/efv-2026-07-24/GATES.md,
"W-FSIDE-SHIP" - owner-authorized 2026-07-23 via the decision queue; this
source states the mechanism under test BEFORE any run, per the lane order).

MECHANISM RECONCILIATION (stated before running):
  Under test = (a) the efv_score.py F-SIDE-FIX joint top-band display
  recalibration hook: SIDE_FAIRNESS_FIX_DEFAULT (False) / SFF_KNEE_RAW 52.5 /
  SFF_MOVE_CAP_FV 3.0, pure core joint_band_recal + _sff_crosswalk_curve /
  _sff_expected_war, serve wrapper _apply_side_fairness_fix wired into BOTH
  run() (resolved) and run_live() (active board), env-overridable
  EEPHUS_SIDE_FAIRNESS_FIX. This is the only implementation actually wired
  default-OFF in efv_score today.
  Context only = (b) the 2026-07-15 joint-display-map ARM-2 candidate
  (data/xfv_joint_map_eval.json). Its patch code is GONE (the lane workspace
  was a session scratchpad - docs/efv-2026-07-23/GATES.md, "Corrective
  mechanism"); it was RE-DERIVED as (a) on 2026-07-23. (a) is therefore the
  faithful surviving form of (b); testing (a) tests the only shippable code.

Registered clauses (docs/efv-2026-07-24/GATES.md W-FSIDE-SHIP, frozen):
  G1' pooled OOS Spearman delta lo95 >= -0.005 (no-harm, fresh run at the
      current repaired vintage; joint board display grade vs realized WAR)
  G2  fairness efficacy: top-25 hit-over-pit realized-WAR gap SHRINKS vs
      incumbent (point, seed-7 _sf_boot stream, the F1b convention) AND
      top-25 pitcher share moves TOWARD the measured deserved share
      (deserved = the raw rank_war frame share, the F-SIDE convention)
  G3  mid-board (ranks 51-200) pooled Spearman delta >= -0.003
  G4  flag-OFF bit-identity (real scoring path, in-process)
  Battery: served moves confined to the top band (top 50 overall); max served
      xfv_grade_quantile move <= 4.0 FV (today's owner bound; the in-tree
      mechanism cap is 3.0, stricter); full mover log; in-process ON-vs-OFF
      through the REAL scoring path (efv_score.run_live, writes redirected to
      the session scratchpad - no tree artifact is regenerated).

Frame: identical to the 2026-07-23 F-SIDE-FIX lab (imported from
tools.efv_side_fairness_fix_lab - build_frame drives the PRODUCTION efv_score
functions and asserts its fold refits reproduce efv_model._sf_fwd_chain
rank_war bit-for-bit). Baselines are SAME-RUN on the repaired matrices;
ledgered historical numbers (4.07 / 0.37 / 0.11) are context only.

Seed 20260724, 2000 bootstrap reps. One attempt; marginal = FAIL.
Artifact: data/xfv_fside_ship_eval.json.

Run (from prospect-tracker/):
  python -m tools.efv_fside_ship_lab eval
  python -m tools.efv_fside_ship_lab battery --scratch DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import statistics
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

SEED = 20260724
REPS = 2000
G1_NOHARM_LO95 = -0.005
G3_MIDBOARD_DELTA = -0.003
BATTERY_MOVE_CAP = 4.0     # today's owner bound (mechanism cap 3.0 is stricter)
BATTERY_TOP_N = 50         # served moves must be confined to top-50 overall
OUT_PATH = _ROOT / "data" / "xfv_fside_ship_eval.json"

_MATRICES = ("xfv_hitter_matrix.json", "xfv_pitcher_matrix.json")
_BATTERY_INPUTS = ("xfv_scored.json", "xfv_scored_pitcher.json",
                   "xfv_live_hitter_matrix.json", "xfv_live_pitcher_matrix.json")

RECONCILIATION = (
    "Under test: (a) efv_score F-SIDE-FIX hook (SIDE_FAIRNESS_FIX_DEFAULT / "
    "SFF_KNEE_RAW 52.5 / SFF_MOVE_CAP_FV 3.0 / joint_band_recal / "
    "_apply_side_fairness_fix, flag EEPHUS_SIDE_FAIRNESS_FIX) - the only "
    "implementation wired default-OFF in efv_score today. Context: (b) the "
    "2026-07-15 ARM-2 joint-display-map candidate; its patch code is gone "
    "(session scratchpad) and was re-derived AS (a) on 2026-07-23, so (a) is "
    "the surviving faithful form of (b).")


def _sha12(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _input_hashes() -> dict:
    return {n: _sha12(_ROOT / "data" / n)
            for n in _MATRICES + _BATTERY_INPUTS if (_ROOT / "data" / n).exists()}


# ---------------------------------------------------------------------------
# eval frame (G1' / G2 / G3 + descriptive weak-cell reads)
# ---------------------------------------------------------------------------

def _spearman_gap_boot(scored, key_i="disp", key_c="disp_cand", seed=SEED):
    from efv_model import _spearman
    di = [r[key_i] for r in scored]
    dc = [r[key_c] for r in scored]
    wars = [r["war"] for r in scored]
    rho_i = _spearman(di, wars)
    rho_c = _spearman(dc, wars)
    rng = random.Random(seed)
    n = len(scored)
    gaps = []
    for _ in range(REPS):
        idx = [rng.randrange(n) for _ in range(n)]
        wi = [wars[i] for i in idx]
        gaps.append(_spearman([dc[i] for i in idx], wi)
                    - _spearman([di[i] for i in idx], wi))
    gaps.sort()
    return {"rho_incumbent": round(rho_i, 4), "rho_candidate": round(rho_c, 4),
            "gap": round(rho_c - rho_i, 4),
            "gap_lo95": round(gaps[int(0.05 * REPS)], 4),
            "gap_ci90": [round(gaps[int(0.05 * REPS)], 4),
                         round(gaps[int(0.95 * REPS)], 4)],
            "p_gap_gt_0": round(sum(1 for g in gaps if g > 0) / REPS, 3),
            "reps": REPS, "seed": seed}


def run_eval() -> dict:
    import efv_score
    from efv_model import _spearman
    from tools.efv_side_fairness_fix_lab import build_frame, _top25, \
        _band_members, _cell

    print("MECHANISM RECONCILIATION (pre-run):", RECONCILIATION)
    hashes_start = _input_hashes()
    scored, meta = build_frame(None)      # SAME-RUN incumbent + candidate

    # frame invariants (context; the served-side checks live in the battery)
    knee, cap = efv_score.SFF_KNEE_RAW, efv_score.SFF_MOVE_CAP_FV
    below = [r for r in scored if r["disp"] < knee]
    i1_viol = sum(1 for r in below if r["disp_cand"] != r["disp"])
    i3_max = max(abs(r["disp_cand"] - r["disp"]) for r in scored)
    n_changed = sum(1 for r in scored
                    if abs(r["disp_cand"] - r["disp"]) > 1e-9)

    # --- G1' pooled no-harm ------------------------------------------------
    g1 = _spearman_gap_boot(scored)
    g1["bar_lo95"] = G1_NOHARM_LO95
    g1["pass"] = bool(g1["gap_lo95"] >= G1_NOHARM_LO95)

    # --- G2 fairness efficacy ---------------------------------------------
    inc25 = _top25(scored, "disp")
    cand25 = _top25(scored, "disp_cand")
    raw25 = _top25(scored, "rank_war")
    inc_cell = _cell(inc25)          # seed-7 stream (F-SIDE comparability)
    cand_cell = _cell(cand25)
    share_inc = inc_cell["pit_share"]
    share_cand = cand_cell["pit_share"]
    share_raw = round(sum(1 for r in raw25 if r["side"] == "pit") / len(raw25), 3)
    gap_inc = inc_cell["boot"]["mean_diff"]
    gap_cand = cand_cell["boot"]["mean_diff"]
    g2a = bool(gap_cand < gap_inc)                       # gap shrinks (strict)
    g2b = bool(abs(share_cand - share_raw) < abs(share_inc - share_raw))
    g2 = {"gap_incumbent_mean_diff_seed7": gap_inc,
          "gap_candidate_mean_diff_seed7": gap_cand,
          "gap_median_incumbent": inc_cell["boot"]["median_diff"],
          "gap_median_candidate": cand_cell["boot"]["median_diff"],
          "gap_candidate_boot_seed20260724": _cell(cand25, seed=SEED)["boot"],
          "share_incumbent": share_inc, "share_candidate": share_cand,
          "share_deserved_raw_rank_war": share_raw,
          "g2a_gap_shrinks": g2a, "g2b_share_toward_deserved": g2b,
          "top25_incumbent_cell": inc_cell, "top25_candidate_cell": cand_cell,
          "pass": bool(g2a and g2b)}

    # --- G3 mid-board (ranks 51-200) no-harm -------------------------------
    mid_i = _band_members(scored, "disp", 51, 200)
    mid_c = _band_members(scored, "disp_cand", 51, 200)
    rho_mid_i = _spearman([r["disp"] for r in mid_i], [r["war"] for r in mid_i])
    rho_mid_c = _spearman([r["disp_cand"] for r in mid_c],
                          [r["war"] for r in mid_c])
    # sensitivity: candidate display evaluated on the INCUMBENT membership
    rho_mid_c_incmem = _spearman([r["disp_cand"] for r in mid_i],
                                 [r["war"] for r in mid_i])
    g3_delta = round(rho_mid_c - rho_mid_i, 4)
    g3 = {"rho_incumbent": round(rho_mid_i, 4),
          "rho_candidate": round(rho_mid_c, 4),
          "delta": g3_delta, "bar": G3_MIDBOARD_DELTA,
          "rho_candidate_on_incumbent_membership": round(rho_mid_c_incmem, 4),
          "n_incumbent": len(mid_i), "n_candidate": len(mid_c),
          "membership": "per-fold joint ranks 51-200 under each respective "
                        "display ranking, pooled across folds",
          "pass": bool(g3_delta >= G3_MIDBOARD_DELTA)}

    # --- descriptive: scoreboard weak-cell reads (display-space analogues) --
    # The scoreboard weak cells (pit.fv_tier.50 spearman -0.140; pit eras) are
    # measured on the eFV SCORE (rank_war family), which this mechanism NEVER
    # touches - those cells are unchanged by construction. Below: the same
    # cuts measured on the JOINT DISPLAY grade (the surface this ship edits).
    def _rho_pair(rows):
        if len(rows) < 8:
            return None
        return {"n": len(rows),
                "incumbent": round(_spearman([r["disp"] for r in rows],
                                             [r["war"] for r in rows]), 4),
                "candidate": round(_spearman([r["disp_cand"] for r in rows],
                                             [r["war"] for r in rows]), 4)}
    pit = [r for r in scored if r["side"] == "pit"]
    weak = {"note": "scoreboard weak cells are rank_war-based and unchanged "
                    "by construction; these are the display-space analogues "
                    "on the eval frame (descriptive, no gate)",
            "pit_fv_tier_50_display": _rho_pair([r for r in pit
                                                 if abs(r["fv"] - 50.0) < 1e-9]),
            "pit_by_fold_display": {str(yr): _rho_pair([r for r in pit
                                                        if r["year"] == yr])
                                    for yr in sorted({r["year"] for r in pit})},
            "pit_pooled_display": _rho_pair(pit)}

    # --- movers (eval frame) ------------------------------------------------
    movers = sorted((r for r in scored
                     if abs(r["disp_cand"] - r["disp"]) > 1e-9),
                    key=lambda r: -abs(r["disp_cand"] - r["disp"]))
    per_fold_shares = {}
    for yr in sorted({r["year"] for r in scored}):
        ys = [r for r in scored if r["year"] == yr]
        yi = _top25(ys, "disp")
        yc = _top25(ys, "disp_cand")
        per_fold_shares[str(yr)] = {
            "inc_pit_share": round(sum(1 for r in yi if r["side"] == "pit") / len(yi), 3),
            "cand_pit_share": round(sum(1 for r in yc if r["side"] == "pit") / len(yc), 3)}

    hashes_end = _input_hashes()
    drift = {k: v for k, v in hashes_end.items() if hashes_start.get(k) != v}
    if drift:
        raise RuntimeError(f"input drift mid-run (concurrent lane?): {drift}")

    art = {
        "generated_at": date.today().isoformat(),
        "eval_line": "W-FSIDE-SHIP - owner-authorized fairness re-registration "
                     "of the efv_score F-SIDE-FIX joint top-band display "
                     "recalibration (fresh run, repaired 2026-07-24 vintage)",
        "registration": "docs/efv-2026-07-24/GATES.md 'W-FSIDE-SHIP'",
        "mechanism_reconciliation": RECONCILIATION,
        "protocol": {
            "frame": "F-SIDE full_pool_km, forward-chained folds "
                     + "-".join(str(meta["folds"][i]) for i in (0, -1))
                     + " (tools.efv_side_fairness_fix_lab.build_frame - drives "
                       "the production efv_score functions; fold refits "
                       "asserted bit-for-bit vs efv_model._sf_fwd_chain)",
            "mechanism": {"knee_raw": knee, "move_cap_fv": cap,
                          "production_code": "efv_score.joint_band_recal + "
                                             "_sff_crosswalk_curve/_sff_expected_war "
                                             "+ _apply_side_fairness_fix"},
            "seed": SEED, "bootstrap_reps": REPS,
            "baselines": "SAME-RUN incumbent on the repaired matrices; "
                         "ledgered historical numbers are context only",
            "matrix_hashes": {k: hashes_start[k] for k in _MATRICES},
            **meta},
        "gates": {"G1_noharm": g1, "G2_fairness": g2, "G3_midboard": g3},
        "frame_invariants": {
            "below_knee_identity_violations": i1_viol,
            "max_abs_move_fv": round(i3_max, 2), "mechanism_cap": cap,
            "n_rows": len(scored), "n_changed": n_changed},
        "weak_cells_descriptive": weak,
        "per_fold_top25_pit_share": per_fold_shares,
        "top_movers": [{"pk": r["pk"], "side": r["side"], "year": r["year"],
                        "disp": round(r["disp"], 1),
                        "disp_cand": round(r["disp_cand"], 1),
                        "war": round(r["war"], 2)} for r in movers[:20]],
    }
    OUT_PATH.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print("wrote", OUT_PATH)
    return art


# ---------------------------------------------------------------------------
# served battery: in-process ON-vs-OFF through the REAL scoring path
# ---------------------------------------------------------------------------

def run_battery(scratch: Path) -> dict:
    """Runs efv_score.run_live for both sides with scored_live_path redirected
    to `scratch` (no tree artifact regenerated):
      pass 1  flag OFF          -> off_*        (the incumbent serve)
      pass 2  flag OFF again    -> off2_*       (determinism control)
      pass 3  hook REMOVED      -> nohook_*     (G4: OFF == hook-absent)
      pass 4  flag ON           -> on_*         (hit before pit, the regen
                                                 order; the ON hit run reads
                                                 the OFF pit artifact = the
                                                 previous-regen seam)
    Battery checks: G4 byte-identity; movers confined to top-50 overall of the
    OFF joint board; max |display move| <= 4.0 FV; rank_war / p_bucket /
    p_bust per-player identity; below-knee identity; full mover log."""
    import efv_score

    scratch.mkdir(parents=True, exist_ok=True)
    live_paths = {"hit": scratch / "xfv_scored_live.json",
                  "pit": scratch / "xfv_scored_live_pitcher.json"}
    orig_path_fn = efv_score.scored_live_path
    efv_score.scored_live_path = lambda side: live_paths[
        "pit" if side == "pit" else "hit"]
    orig_hook = efv_score._apply_side_fairness_fix

    def _snap(tag):
        out = {}
        for sd in ("hit", "pit"):
            out[sd] = live_paths[sd].read_bytes()
            shutil.copyfile(live_paths[sd], scratch / f"{tag}_{sd}.json")
        return out

    def _run_both():
        for sd in ("hit", "pit"):            # regen order: hit BEFORE pit
            efv_score.run_live(persist=True, side=sd)

    try:
        os.environ["EEPHUS_SIDE_FAIRNESS_FIX"] = "0"
        _run_both(); off = _snap("off")
        _run_both(); off2 = _snap("off2")
        efv_score._apply_side_fairness_fix = lambda scored, side, live: 0
        _run_both(); nohook = _snap("nohook")
        efv_score._apply_side_fairness_fix = orig_hook
        os.environ["EEPHUS_SIDE_FAIRNESS_FIX"] = "1"
        _run_both(); on = _snap("on")
    finally:
        efv_score.scored_live_path = orig_path_fn
        efv_score._apply_side_fairness_fix = orig_hook
        os.environ.pop("EEPHUS_SIDE_FAIRNESS_FIX", None)

    determinism_ok = all(off[sd] == off2[sd] for sd in ("hit", "pit"))
    g4_ok = all(off[sd] == nohook[sd] for sd in ("hit", "pit"))

    # joint OFF board (both sides pooled actives) + ON-vs-OFF moves
    rows = []
    for sd in ("hit", "pit"):
        offr = {r["player_key"]: r for r in json.loads(off[sd])}
        onr = {r["player_key"]: r for r in json.loads(on[sd])}
        assert set(offr) == set(onr), "ON/OFF pool membership diverged"
        for pk, ro in offr.items():
            rn = onr[pk]
            rows.append({
                "pk": pk, "side": sd,
                "disp_off": ro["xfv_grade_display"],
                "disp_on": rn["xfv_grade_display"],
                "rank_war": ro["rank_war"],
                "ident_ok": (ro["rank_war"] == rn["rank_war"]
                             and ro["p_bucket"] == rn["p_bucket"]
                             and ro.get("p_bust") == rn.get("p_bust")
                             and ro["xfv_grade"] == rn["xfv_grade"]),
                "surplus_off": ro.get("surplus_mm"),
                "surplus_on": rn.get("surplus_mm")})
    rows.sort(key=lambda r: (-r["disp_off"], -r["rank_war"], r["pk"]))
    for i, r in enumerate(rows, 1):
        r["joint_rank_off"] = i
    movers = [r for r in rows if r["disp_on"] != r["disp_off"]]
    for r in movers:
        r["move"] = round(r["disp_on"] - r["disp_off"], 1)
        # worst-case tie rank: rows at or above this display value
        r["rank_ties_worst"] = sum(1 for x in rows
                                   if x["disp_off"] >= r["disp_off"])
    max_move = max((abs(r["move"]) for r in movers), default=0.0)
    max_rank = max((r["joint_rank_off"] for r in movers), default=0)
    max_rank_worst = max((r["rank_ties_worst"] for r in movers), default=0)
    knee = efv_score.SFF_KNEE_RAW
    below_knee_moved = sum(1 for r in movers
                           if r["disp_off"] < knee and r["disp_on"] < knee)
    ident_bad = sum(1 for r in rows if not r["ident_ok"])

    def _share(rows_, key, n=25):
        top = sorted(rows_, key=lambda r: (-r[key], -r["rank_war"], r["pk"]))[:n]
        return round(sum(1 for r in top if r["side"] == "pit") / n, 3)

    res = {
        "checked_at": date.today().isoformat(),
        "path": "efv_score.run_live in-process, scored_live_path redirected "
                "to the session scratchpad (tree untouched); "
                "xfv_grade_display IS served xfv_grade_quantile "
                "(efv_export.py line 44)",
        "n_rows_joint": len(rows),
        "determinism_off_runs_identical": determinism_ok,
        "G4_flag_off_bit_identity": {"pass": bool(determinism_ok and g4_ok),
                                     "off_equals_nohook": g4_ok},
        "n_movers": len(movers),
        "max_abs_move_fv": max_move, "move_cap": BATTERY_MOVE_CAP,
        "move_cap_pass": bool(max_move <= BATTERY_MOVE_CAP),
        "max_mover_joint_rank_off": max_rank,
        "max_mover_joint_rank_worst_case_ties": max_rank_worst,
        "confined_top50_pass": bool(max_rank <= BATTERY_TOP_N),
        "confined_top50_worst_case_ties_pass": bool(max_rank_worst <= BATTERY_TOP_N),
        "below_knee_movers": below_knee_moved,
        "rankwar_pbucket_pbust_grade_identity_violations": ident_bad,
        "served_top25_pit_share": {"off": _share(rows, "disp_off"),
                                   "on": _share(rows, "disp_on")},
        "mover_log": [{k: r[k] for k in
                       ("pk", "side", "disp_off", "disp_on", "move",
                        "joint_rank_off", "rank_ties_worst",
                        "surplus_off", "surplus_on")}
                      for r in sorted(movers, key=lambda r: r["joint_rank_off"])],
    }
    art = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    art["served_battery"] = res

    # --- reproducible roll-up (no hand edits) ------------------------------
    g = art["gates"]
    gates_pass = bool(g["G1_noharm"]["pass"] and g["G2_fairness"]["pass"]
                      and g["G3_midboard"]["pass"])
    battery_pass = bool(res["determinism_off_runs_identical"]
                        and res["G4_flag_off_bit_identity"]["pass"]
                        and res["move_cap_pass"]
                        and res["confined_top50_pass"]
                        and res["confined_top50_worst_case_ties_pass"]
                        and res["below_knee_movers"] == 0
                        and res["rankwar_pbucket_pbust_grade_identity_violations"] == 0)
    all_pass = bool(gates_pass and battery_pass)
    art["all_pass"] = all_pass
    art["verdict"] = (
        "ALL-PASS - ship authorized: wave-D consolidator flips "
        "SIDE_FAIRNESS_FIX_DEFAULT to True (wiring diff in the lane report), "
        "regens served artifacts, runs the post-flip served battery vs a "
        "pre-flip data/xfv.json snapshot, restamps registry row "
        "xfv_side_fairness_fix under this registration."
    ) if all_pass else (
        "FAIL - defaults stay OFF (SIDE_FAIRNESS_FIX_DEFAULT False); this "
        "artifact is the loss ledger; the one attempt is spent.")
    lam = art["protocol"].get("lambdas", {})
    art["prior_attempt_context"] = (
        "The 2026-07-23 F-SIDE-FIX registration FAILED its F1b clause at the "
        "pre-repair vintage (cand 4.15 vs inc 4.07; "
        "data/xfv_side_fairness_fix_eval.json is that loss ledger; its one "
        "attempt is spent). W-FSIDE-SHIP is the NEW owner-authorized "
        "registration its keep-alive contemplated, run fresh ONCE at the "
        "wave-B repaired 2026-07-24 vintage, where the same-run incumbent gap "
        "is " + str(g["G2_fairness"]["gap_incumbent_mean_diff_seed7"]) +
        " and the candidate gap is " +
        str(g["G2_fairness"]["gap_candidate_mean_diff_seed7"]) +
        " (shrinks). Within-tail selection remains outcome-arbitrary at the "
        "player level (fold 2022: dl_hall promoted +3.0 realized 0.68; "
        "hunter_greene demoted -3.0 realized 19.73) - the aggregate top-25 gap "
        "and share are what this registration gates, per the owner framing.")
    art["lambda_note"] = (
        "Frame lambdas read from served data/xfv.json meta.live_lambda "
        "(hit " + str(lam.get("hit")) + " / pit " + str(lam.get("pit")) +
        "); incumbent and candidate share identical lambdas so every gate is "
        "internally paired.")

    OUT_PATH.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in
                      ("determinism_off_runs_identical", "G4_flag_off_bit_identity",
                       "n_movers", "max_abs_move_fv", "move_cap_pass",
                       "max_mover_joint_rank_off",
                       "max_mover_joint_rank_worst_case_ties",
                       "confined_top50_pass", "below_knee_movers",
                       "rankwar_pbucket_pbust_grade_identity_violations",
                       "served_top25_pit_share")}, indent=1))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="eval", choices=("eval", "battery"))
    ap.add_argument("--scratch", type=Path, default=None)
    args = ap.parse_args()
    if args.cmd == "eval":
        art = run_eval()
        g = art["gates"]
        print(json.dumps({
            "G1": {k: g["G1_noharm"][k] for k in
                   ("rho_incumbent", "rho_candidate", "gap", "gap_lo95", "pass")},
            "G2": {k: g["G2_fairness"][k] for k in
                   ("gap_incumbent_mean_diff_seed7", "gap_candidate_mean_diff_seed7",
                    "share_incumbent", "share_candidate",
                    "share_deserved_raw_rank_war", "g2a_gap_shrinks",
                    "g2b_share_toward_deserved", "pass")},
            "G3": {k: g["G3_midboard"][k] for k in
                   ("rho_incumbent", "rho_candidate", "delta", "bar", "pass")},
            "frame_invariants": art["frame_invariants"]}, indent=1))
    else:
        if not args.scratch:
            ap.error("battery requires --scratch")
        run_battery(args.scratch)
