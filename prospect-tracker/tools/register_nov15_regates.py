# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Move the registry rows of the 2026-11-15 re-gates (NOV15_REGATES) from
their artifacts, one item per call, idempotently.

    python tools/register_nov15_regates.py pwoba    data/pwoba_blend_regate_eval.json -> pwoba_blend_regate
    python tools/register_nov15_regates.py bat      data/bat_tracking_eval.json       -> bat_tracking_hitters
    python tools/register_nov15_regates.py nov_a    data/bat_tracking_nov_a_eval.json -> bat_tracking_nov_a (new row)
    python tools/register_nov15_regates.py dem      data/dem_plus_eval.json holdout   -> dem_plus (notes only)

Every number written here is READ from the item's artifact; nothing is typed.
A row is moved only when its artifact carries the owner-waived early read
(owner_waived_early_read, or the holdout block), and a second call changes
nothing (the notes carry a marker). Keeps the file's CRLF line endings and
one-space indent. Then: python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
RUN_DATE = "2026-10-14"
MARK = f"OWNER-WAIVED EARLY READ ({RUN_DATE}"
WAIVER = ("owner 2026-10-14, EW3-5 look days waived and EW3-6 the explicit "
          "season-complete override treating 2026 as complete as of 2026-10-01; "
          "the registered date was 2026-11-15")


def _ci(c):
    return (f"mean {c['mean']:+.4f} lo95 {c['lo95']:+.4f} hi95 {c['hi95']:+.4f}"
            if c else "none")


def _load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _read_registry():
    raw = REG.read_bytes()
    return json.loads(raw.decode("utf-8")), (b"\r\n" in raw)


def _write_registry(doc, crlf):
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))


# --------------------------------------------------------------------------- #
def pwoba(row: dict) -> bool:
    art = _load("data/pwoba_blend_regate_eval.json")
    if not art.get("owner_waived_early_read") or MARK in (row.get("notes") or ""):
        return False
    reg = art["registered_regate"]
    v = art["verdict"]
    g1 = reg["gap_ci_blend_minus_incumbent_v1"]
    g2 = reg["gap_ci_blend_minus_incumbent_v2"]
    rhos = reg["rhos_v1"]
    acc = art["new_pair_accounting"]
    passed = v["status"] == "PASS"
    n = reg["n"]
    row["summary"] = (
        f"Re-gate {'PASS' if passed else 'FAIL'} at the extended n: frozen blend rho "
        f"{rhos['output_blend']} vs pWOBA {rhos['fa_projection']} (n {n:,}, lo95 "
        f"{g1['lo95']:+.4f}); {'production diff proposed behind a flag' if passed else 'the no-ship stands'}.")
    row["verdict"] = "validated" if passed else "deprecated"
    row["predicts"] = ("Re-test of the frozen output blend (b=0.2, g=0.1) vs the incumbent "
                       f"pWOBA at the {RUN_DATE} vintage with the 2025 to 2026 cohort resolved")
    row["notes"] = (
        f"RE-GATE {v['status']} ({RUN_DATE}; {MARK}; {WAIVER}). The frozen arm b=0.2 on the "
        f"registered complete-outcome pair set now holds n {n:,} (pred years {reg['pred_years']}): "
        f"{acc['new_resolved_pairs_entering_gate']} resolved 2025->2026 pairs entered the gate set. "
        f"Rhos v1: output_blend {rhos['output_blend']}, fa_projection {rhos['fa_projection']}, "
        f"xwoba_alone {rhos['xwoba_alone']}, gap_corrected {rhos['gap_corrected']}. Gap CI blend minus "
        f"incumbent: v1 {_ci(g1)} (pass_v1 {reg['pass_v1']}), v2 {_ci(g2)} (pass_under_v2 "
        f"{reg['pass_under_v2']}). Criterion: {v['criterion']}. Reason: {v['reason']} "
        f"Vintage reproduction of the original 711-pair gate: reproduces_original "
        f"{art['vintage_reproduction']['reproduces_original']} (n_gate_now on the original years is "
        f"inside n {n:,}; see the artifact). Train stability check argmax_matches_frozen "
        f"{art['train_stability_check']['argmax_matches_frozen']} (check only, no re-selection). "
        + ("PRODUCTION DIFF (recorded, NOT applied): hitter_export._join_pwoba blends the current-season "
           "Savant est_woba at 0.2 into w; it is a served change (plan Part 8 class 3) built behind a flag "
           "defaulting off and flipped only by the owner. "
           if passed else
           "No production diff: the keep-alive is spent by this verdict and the no-ship stands. ")
        + "Prior history: RE-GATE FAIL (2026-07-23) with zero new resolved pairs, the keep-alive preserved "
          "until the 2025->2026 cohort resolved; companion of registry row pwoba_xwoba_blend (original eval "
          "data/xwoba_projection_blend_eval.json). Season-complete override: "
        + json.dumps(art["season_complete_override"]["seasons"]) + ".")
    return True


def bat(row: dict) -> bool:
    art = _load("data/bat_tracking_eval.json")
    if not art.get("owner_waived_early_read") or MARK in (row.get("notes") or ""):
        return False
    a, b, vd = art["arm_a_pwoba_residual"], art["arm_b_descriptive_blend"], art["verdicts"]
    ga, gb = a["gate"]["gap_ci_v1"], b["gate"]["gap_ci_v1"]
    ra, rb = a["results_by_convention"]["v1"]["rhos"], b["results_by_convention"]["v1"]["rhos"]
    pa, pb = a["gate"]["pass"], b["gate"]["pass"]
    row["summary"] = (
        f"Frozen re-run with complete 2026 outcomes: residual arm rho {ra['bt_corrected']} vs "
        f"{ra['fa_projection']} (n {a['n_pairs']}, lo95 {ga['lo95']:+.4f}); blend arm "
        f"{rb['bt_blend_candidate']} vs {rb['fwdhem_incumbent']} (n {b['n_pairs']}, lo95 {gb['lo95']:+.4f}).")
    row["verdict"] = "provisional" if (pa or pb) else "deprecated"
    row["baseline"] = ("same incumbents; folds 2024->2025 + 2025->2026, both complete outcomes "
                       f"at the {RUN_DATE} re-run")
    row["notes"] = (
        f"FROZEN RE-RUN ({RUN_DATE}; {MARK}; {WAIVER}): the identical protocol, seed 20260723, 2000 reps, "
        "no researcher degrees of freedom, with the 2025->2026 fold's outcome half complete "
        f"(partial_outcome_kept arm A {a['drops'].get('partial_outcome_kept')}, arm B "
        f"{b['drops'].get('partial_outcome_kept')}). ARM A {vd['arm_a']}: rho(bt_corrected) "
        f"{ra['bt_corrected']} vs incumbent {ra['fa_projection']} on {a['n_pairs']} pooled pairs, gap CI v1 "
        f"{_ci(ga)}, pass_under_v2 {a['gate']['pass_under_v2']}; per fold "
        + "; ".join(f"{k} n {f['n']} rho_fa {f['rho_fa']} rho_bt {f['rho_bt_corrected']}"
                    for k, f in a["folds"].items())
        + f". ARM B {vd['arm_b']}: rho(bt_blend) {rb['bt_blend_candidate']} vs fwdHEM+ incumbent "
        f"{rb['fwdhem_incumbent']} on {b['n_pairs']} pooled pairs, gap CI v1 {_ci(gb)}, pass_under_v2 "
        f"{b['gate']['pass_under_v2']}; vs xwoba_z_alone "
        f"{_ci(b['results_by_convention']['v1']['gap_ci_candidate_minus'].get('xwoba_z_alone'))}; per fold "
        + "; ".join(f"{k} n {f['n']} rho_fwdhem {f['rho_fwdhem']} rho_bt_blend {f['rho_bt_blend']}"
                    for k, f in b["folds"].items())
        + ". " + (("Gate PASSED, provisional and small-n (two folds); any served change is built behind a flag "
                   "defaulting off and flipped only by the owner. ") if (pa or pb) else
                  "Both arms NULL again on the frozen protocol; the registered keep-alive is spent and the "
                  "lane is CLOSED as tested. ")
        + "Descriptive context (not gated) is in the artifact; the 2026 bat-tracking rows of that context "
          "are the 2026-07-23 capture (.cache/bat_tracking), which no verdict reads. Prior history: BOTH ARMS "
          "NULL on 2026-07-23 (arm A lo95 -0.0164 n 468; arm B lo95 -0.0009 n 482) with the 2026 outcome "
          "partial; registered keep-alive was this re-run. Season-complete override: "
        + json.dumps(art["season_complete_override"]["seasons"]) + ".")
    return True


def nov_a(rows: list, by_id: dict) -> bool:
    art = _load("data/bat_tracking_nov_a_eval.json")
    if not art.get("owner_waived_early_read"):
        return False
    if "bat_tracking_nov_a" in by_id and MARK in (by_id["bat_tracking_nov_a"].get("notes") or ""):
        return False
    a, b, vd = art["arm_a_pwoba_residual"], art["arm_b_descriptive_blend"], art["verdicts"]
    ga, gb = a["gate"]["gap_ci_v1"], b["gate"]["gap_ci_v1"]
    ra, rb = a["results_by_convention"]["v1"]["rhos"], b["results_by_convention"]["v1"]["rhos"]
    pa, pb = a["gate"]["pass"], b["gate"]["pass"]
    sp = art["registration"]["swing_plus_source"]
    row = {
        "model_id": "bat_tracking_nov_a",
        "summary": (
            f"NOV-A {'PASS' if (pa or pb) else 'null'}: per-season Swing+ as the BT leg reads "
            f"{ra['bt_corrected']} vs {ra['fa_projection']} (n {a['n_pairs']}, lo95 {ga['lo95']:+.4f}) and "
            f"{rb['bt_blend_candidate']} vs {rb['fwdhem_incumbent']} (n {b['n_pairs']}, lo95 {gb['lo95']:+.4f})."),
        "surface": ("Lab artifact, rendered nowhere: the registered NOV-A arm of the bat-tracking lane "
                    "(tools/bat_tracking_lab.py --nov-a)"),
        "predicts": ("Whether the vendored Swing+ composite, per season, improves next-season wOBA as the BT "
                     "leg of the pWOBA residual arm and of the fwdHEM+ blend arm"),
        "champion": "incumbents unchanged: fa_projection pWOBA (arm A) and fwdhem_plus (arm B)",
        "baseline": ("same incumbents and pair sets as data/bat_tracking_eval.json with the Swing+ season "
                     "slice required; folds 2024->2025 + 2025->2026, complete outcomes"),
        "metric": "Pooled paired bootstrap lo95 > 0 vs the incumbent, 2000 reps, seed 20260723 (bars inherited)",
        "eval_artifact": "data/bat_tracking_nov_a_eval.json",
        "verdict": "provisional" if (pa or pb) else "deprecated",
        "notes": (
            f"NOV-A RUN ONCE ({RUN_DATE}; {MARK}; {WAIVER}). Registered 2026-07-23 in docs/wills-2026-07-23/GATES.md "
            "W-NOV and docs/efv-2026-07-23/RECHECKS.md before any 2026 outcome was seen: the vendored Swing+ "
            "per-season variant (data/swing_plus.json seasons slices, W6, generated "
            f"{sp['generated_at']}, {sp['model']}, reliability_k {sp['reliability_k']}, coverage "
            f"{json.dumps(sp['per_season_coverage'])}, low_n slices kept as given {json.dumps(sp['per_season_low_n'])}) "
            "replaces the raw bat-tracking z-aggregates as the BT leg in both arms; the parent BT row gate stays "
            f"and a pair without a Swing+ slice drops as leg_missing (arm A {a['drops'].get('leg_missing')}, arm B "
            f"{b['drops'].get('leg_missing')}). ARM A {vd['arm_a']}: rho(bt_corrected) {ra['bt_corrected']} vs "
            f"incumbent {ra['fa_projection']} on {a['n_pairs']} pooled pairs, gap CI v1 {_ci(ga)}, pass_under_v2 "
            f"{a['gate']['pass_under_v2']}. ARM B {vd['arm_b']}: rho(bt_blend) {rb['bt_blend_candidate']} vs "
            f"fwdHEM+ incumbent {rb['fwdhem_incumbent']} on {b['n_pairs']} pooled pairs, gap CI v1 {_ci(gb)}, "
            f"pass_under_v2 {b['gate']['pass_under_v2']}. "
            + ("Gate PASSED, provisional and small-n; any served change is built behind a flag defaulting off "
               "and flipped only by the owner. " if (pa or pb) else
               "Neither arm clears its inherited bar; NOV-A is NULL and closed as tested. ")
            + "NOV-B (the pa_value-style k-blend of observed and swing-model xwOBA as the est_woba leg) is "
              "NOT_AVAILABLE: no per-player-season swing-model xwOBA exists on the platform (the vendored "
              "artifact model/swing_plus/swing_plus_model_v1.joblib carries no xwOBA model and its reliability_k "
              "is 360; the registered k 250 belongs to the un-vendored research file swing-plus/pa_value_models.joblib), "
              "so the arm was not run and nothing substituted. Season-complete override: "
            + json.dumps(art["season_complete_override"]["seasons"]) + "."),
    }
    if "bat_tracking_nov_a" in by_id:
        by_id["bat_tracking_nov_a"].update(row)
    else:
        idx = next((i for i, r in enumerate(rows) if r["model_id"] == "bat_tracking_hitters"),
                   len(rows) - 1)
        rows.insert(idx + 1, row)
    return True


def dem(row: dict) -> bool:
    art = _load("data/dem_plus_eval.json")
    h = art.get("confirmatory_holdout_2025_to_2026")
    if not h or MARK in (row.get("notes") or ""):
        return False
    if h.get("status") != "SCORED":
        add = (f" CONFIRMATORY HOLDOUT ({RUN_DATE}; {MARK}; {WAIVER}): NOT SCORED, {h.get('reason')}; "
               "the verdict is unchanged.")
    else:
        fs = h["forward_spearman_vs_rate_next"]
        add = (
            f" CONFIRMATORY HOLDOUT ({RUN_DATE}; {MARK}; {WAIVER}), DEM_PLUS_GATE.md section 7, reported BESIDE "
            f"the verdict and never merged into it: X-D1's estimator unchanged on the {h['n_pairs']} 2025->2026 "
            f"pairs: DEM+ rho {fs['dem_plus']} vs raw rate {fs['raw_rate']}, fielding percentage {fs['fld_pct']}, "
            f"innings {fs['innings']}; twin {fs['twin']} (fails_as_required {h['twin']['fails_as_required']}). "
            f"Gap CIs v1: vs fielding percentage {_ci(h['gap_ci_vs_fld_pct'])}, vs innings "
            f"{_ci(h['gap_ci_vs_innings'])}, vs the raw rate {_ci(h['gap_ci_vs_raw_rate'])}; clauses v1 "
            f"{json.dumps(h['clauses_v1'])}, v2 {json.dumps(h['clauses_v2'])}. The X-D1 verdict (validated, "
            "2021-2024) and X-D2's provisional status do not move from the holdout. Season-complete override: "
            + json.dumps(h["season_complete_override"]["seasons"]) + ".")
    row["notes"] = (row.get("notes") or "") + add
    return True


def main(argv) -> int:
    if len(argv) != 1 or argv[0] not in ("pwoba", "bat", "nov_a", "dem"):
        print(__doc__)
        return 2
    item = argv[0]
    doc, crlf = _read_registry()
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    if item == "pwoba":
        changed = pwoba(by_id["pwoba_blend_regate"])
    elif item == "bat":
        changed = bat(by_id["bat_tracking_hitters"])
    elif item == "nov_a":
        changed = nov_a(rows, by_id)
    else:
        changed = dem(by_id["dem_plus"])
    if not changed:
        print(f"{item}: registry already carries this run (or the artifact has no owner-waived read); "
              "nothing written")
        return 0
    _write_registry(doc, crlf)
    sys.path.insert(0, str(ROOT))
    import model_registry
    problems = model_registry.validate(model_registry.load())
    print(f"{item}: registry written; validate -> {problems or 'clean'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
