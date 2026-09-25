# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Driver System V2 assembly receipt: DS-07 to DS-10, the BMI re-test and PV-12
(docs/efv-v2/DRIVER_SYSTEM_V2.md s4.3 and s5; efv_v2_model "DRIVER SYSTEM V2 assembly").

WHAT THIS WRITES. data/efv_v2_assembly.json, the registration of the assembled V2
BEFORE any development read of it:

    weights     w_skill and w_time per side from efv_v2_model.combiner_rule (DS-08),
                with the rule's receipt: every (source, year) it read, all at or
                before RULE_LAST_YEAR, the pooled OLS coefficients and their SEs.
    arms        the admission rule (DS-06) on the LIST-VINTAGE frame for every V2
                candidate (skill and timing, both sides), inside every development
                fold V2 may be scored on (list vintages 2017 to 2019, training on the
                earlier vintages with every player in the V frame left out) and on all
                development vintages together. These are looks at the label and count
                in the program's forking-path total (tools/efv_arm_ledger.py reads them).
    folds       per fold, what the assembled model would carry: admitted keys, the
                penalty, whether pitchers fall back to the consensus order (owner
                DS-Q2). Fits only; no test row is scored.
    coverage    DS-09 protection status by list vintage (league transaction feed on
                outcome-blind ids), BMI as of the read by vintage, and the PV-12 slot.
    probes      the combiner rule's reads, one per side.

NOTHING HERE SCORES V2 against consensus, a source or an outcome on a scored row. The
development read is DS-16 (tools/efv_v2_dev_read.py), after this registration.

NEVER READ: list vintages 2020 and 2021 (R-LV) and the 2025+ debut cohorts (R-VM). The
frame builders raise on a reserved vintage; the label join drops reserved_vm rows; the
guards run first. Nothing is grouped by consensus-FV level.

Run:  python tools/efv_v2_assemble.py            (writes the artifact)
      python tools/efv_v2_assemble.py --dry-run  (prints, writes nothing)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_drivers as DRV  # noqa: E402
import efv_labels as L  # noqa: E402
import efv_model as V1  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

OUT = H.ASSEMBLY_PATH
#: The development folds V2 may be scored on (after the rule's years, before R-LV).
DEV_FOLDS: tuple[int, ...] = tuple(v for v in F.DEV_VINTAGES
                                   if v >= H.V2_FIRST_SCORED_YEAR)
PRIOR_BIO_TESTS = (
    "Height, weight, BMI and frame were tested twice before, both null: the D-2 driver "
    "arms (data/xfv_driver_extras.json) and the archetype bio lab "
    "(tools/_arch_bio_result.json: pitcher BMI d_rho +0.0102, CI95 -0.023 to +0.043, 5 of "
    "6 folds positive, NULL below the MDE, beside the full pitcher block that is now "
    "scrapped). The pitcher BMI candidate here is ONE pre-declared re-test in a new "
    "context (list-vintage frame, W3 label, residual to consensus, admission rule), "
    "counted in the forking-path total.")


def _guards() -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    bad = sorted(set(F.DEV_VINTAGES) & set(F.RESERVED_LV))
    if bad:
        raise F.ReservedFrameError(f"DEV_VINTAGES overlaps RESERVED_LV: {bad}")
    if any(v in F.RESERVED_LV or v > max(F.DEV_VINTAGES) for v in DEV_FOLDS):
        raise F.ReservedFrameError(f"a development fold is reserved: {DEV_FOLDS}")
    if H.RULE_LAST_YEAR >= min(DEV_FOLDS):
        raise ValueError("the combiner rule's years overlap the scored folds")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "lv_vintages_read": list(F.DEV_VINTAGES),
            "rule_last_year": H.RULE_LAST_YEAR, "scored_folds": list(DEV_FOLDS)}


def build_frames() -> dict[str, dict[int, tuple[list[dict], list[dict]]]]:
    """{side: {V: (frame rows with sidecars, labels)}} on development vintages only."""
    universe = F.load_universe()
    war = L.war_seasons_table()
    tx = DRV.load_league_transactions(max(F.DEV_VINTAGES) - 1)
    panel = DRV.load_bio_panel()
    out: dict = {}
    for side in F.SIDES:
        for V in F.DEV_VINTAGES:
            F.guard_score_request(V, purpose="V2 assembly")
            rows = F.build_frame(side, V, universe=universe)
            DRV.protection_for_frame(rows, index=tx)
            DRV.bmi_for_rows(rows, panel=panel)
            DRV.pl_revision_for_rows(rows)
            labs = L.labels_for_frame(rows, universe=universe, war=war)
            out.setdefault(side, {})[V] = (rows, labs)
    return out


def coverage(frames) -> dict:
    out = {}
    for side, by_v in frames.items():
        rows = [r for V in sorted(by_v) for r in by_v[V][0]]
        bmi = {}
        pl = {}
        for V in sorted(by_v):
            rr = by_v[V][0]
            bmi[str(V)] = {"rows": len(rr),
                           "observed": sum(1 for r in rr if r.get("bmi_at_read") is not None)}
            pl[str(V)] = {"pipeline_anchored": sum(1 for r in rr if DRV.pipeline_anchored(r)),
                          "observed": sum(1 for r in rr
                                          if r.get("pl_rev_at_read") is not None)}
        out[side] = {"protection": DRV.protection_coverage(rows), "bmi": bmi,
                     "pl_rev": pl}
    out["protection_feed"] = {
        "months_on_disk": sum(DRV.league_tx_months(max(F.DEV_VINTAGES) - 1).values()),
        "first_month": "%d-%02d" % DRV.LEAGUE_TX_FIRST,
        "complete_from_year": DRV.LEAGUE_TX_FULL_FROM,
        "join": "outcome-blind id (efv_identity via efv_vintage_frame); never the record id",
        "known_gap": ("a pre-2012 draftee signed to a major league contract is on the "
                      "40-man from signing, but the league feed's signing line does not "
                      "say so, so he reads off the 40-man until his first option or "
                      "recall")}
    out["pl_rev_source"] = {
        "first_anchor": DRV.PL_REV_FIRST_ANCHOR,
        "first_list_vintage": DRV.PL_REV_FIRST_LIST_VINTAGE,
        "in_repo": False,
        "note": ("the forward-chained PG2 Pipeline prediction exists for anchors 2021 to "
                 "2025 only (provisional lane PG2/PG3, not committed), so no development "
                 "or R-LV row can carry it; the admission rule refuses it for want of "
                 "vintages that give a t")}
    return out


def _fold_rows(rows: list[dict], frame_keys: set[str] | None, V: int | None) -> list[dict]:
    if V is None:
        return rows
    return [r for r in rows if r["decision_year"] < V and r["player_key"] not in frame_keys]


def arms_and_folds(side: str, lv_rows: list[dict], frames, weights) -> tuple[dict, dict]:
    ab = H.absence_admitted(side)
    cands = ([("skill", k, "u_y", True) for k in H.skill_candidates(side)]
             + [("timing", k, "reached", False)
                for k in H.timing_candidates(side, ids_outcome_blind=True,
                                             absence_admitted=ab)])
    folds_keys = {V: {r["player_key"] for r in frames[V][0]} for V in DEV_FOLDS}
    arms = {}
    for head, key, target, hb in cands:
        full = H.admission_for_key(lv_rows, key, target=target, has_block_only=hb)
        by_fold = {}
        for V in DEV_FOLDS:
            tr = _fold_rows(lv_rows, folds_keys[V], V)
            chk = H.admission_for_key(tr, key, target=target, has_block_only=hb)
            by_fold[str(V)] = {"admitted": chk["admitted"],
                               "n_valid_vintages": chk["n_valid_vintages"],
                               "per_vintage_signs": chk["per_vintage_signs"],
                               "mean_abs_t": chk["mean_abs_t"], "reason": chk["reason"]}
        tag = f"V2-LV:{side}.{head}.{key}"
        arms[tag] = {
            "tag": tag, "side": side, "head": head, "driver": key, "target": target,
            "frame": "lv_dev (list vintages 2011 to 2019, W3 / R3, outcome-blind ids)",
            "item": {"k_rel": "DS-10" if side == "pit" else "DS-06",
                     "bmi": "BMI re-test", "pl_rev": "PV-12",
                     "on_40man": "DS-09", "nov_add": "DS-09"}.get(key, "DS-06"),
            "rows": "has_block" if hb else "all (unobserved at the observed train means)",
            "verdict": "ADMITTED" if full["admitted"] else "REFUSED",
            "per_vintage_signs": full["per_vintage_signs"],
            "t_by_vintage": full["t_by_vintage"],
            "vintages_without_t": full["vintages_without_t"],
            "mean_abs_t": full["mean_abs_t"], "n_valid_vintages": full["n_valid_vintages"],
            "admitted": full["admitted"], "reason": full["reason"],
            "verdict_scope": "all development vintages 2011 to 2019 together",
            "by_fold": by_fold,
            "n_folds_admitted": sum(1 for v in by_fold.values() if v["admitted"]),
        }
    folds = {}
    for V in DEV_FOLDS:
        tr = _fold_rows(lv_rows, folds_keys[V], V)
        m = H.fit_v2(tr, side, frame="lv", weights=weights)
        folds[str(V)] = _fold_summary(m)
    return arms, folds


def _fold_summary(m: dict) -> dict:
    def head(h):
        if h is None:
            return None
        return {"keys": h["keys"], "alpha": H._akey(h["alpha"]), "n_train": h["n_train"],
                "b_uc": round(h["b_uc"], 6),
                "beta": [round(b, 6) for b in h["beta"]],
                "refused": [k for k in h.get("candidates", []) if k not in h["keys"]]}
    return {"n_train": m["n_train"], "train_years": m["train_years"],
            "skill": head(m["skill"]), "timing": head(m["timing"]),
            "w_skill": m["w_skill"], "w_time": m["w_time"],
            "consensus_only": m["consensus_only"],
            "consensus_only_reason": m["consensus_only_reason"]}


def vm_folds(side: str, mat_rows: list[dict], weights) -> dict:
    out = {}
    for yr in V1.SCORED_YEARS:
        if yr <= H.RULE_LAST_YEAR:
            continue
        tr = [r for r in mat_rows if r["decision_year"] < yr]
        if len(tr) < H.MIN_TRAIN_ROWS:
            continue
        out[str(yr)] = _fold_summary(H.fit_v2(tr, side, frame="vm", weights=weights))
    return out


def run() -> dict:
    guards = _guards()
    frames = build_frames()
    lv = {s: H.lv_training_rows(s, frames[s]) for s in F.SIDES}
    mat = {s: [r for r in H.matrix_training_rows(s)
               if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR] for s in F.SIDES}
    rules = {s: H.combiner_rule(s, {"matrix": mat[s], "lv": lv[s]}) for s in F.SIDES}
    for s, rule in rules.items():
        for src in rule["sources"].values():
            if src["years"] and max(src["years"]) > H.RULE_LAST_YEAR:
                raise ValueError(f"{s}: the combiner rule read a year after the rule window")
    weights = {s: {"w_skill": rules[s]["w_skill"], "w_time": rules[s]["w_time"],
                   "a": rules[s]["a"], "status": rules[s]["status"]} for s in F.SIDES}
    arms, lv_folds = {}, {}
    for s in F.SIDES:
        a, f = arms_and_folds(s, lv[s], frames[s], weights)
        arms.update(a)
        lv_folds[s] = f
    probes = {f"DS-08:{s}.combiner_rule": {
        "tag": f"DS-08:{s}.combiner_rule", "verdict": rules[s]["status"].upper(),
        "reads": {k: v["years"] for k, v in rules[s]["sources"].items()},
        "n_pooled": rules[s]["n_pooled"]} for s in F.SIDES}
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_v2_assemble.py",
        "model_id": H.V2_ASSEMBLED_ID,
        "role": "development",
        "adjudicates": False,
        "registered_before_any_read": True,
        "what": ("the assembled Driver System V2 (s4.3): weights fixed by the DS-08 rule, "
                 "admission per development fold, sidecar coverage; no V2 score on any "
                 "scored row"),
        "guards": guards,
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                  "skill_target": "W3 percentile within (side, list vintage)",
                  "timing_target": "R3 (debut inside V..V+3)"},
        "code": {"commit": commit},
        "model": {
            "order_idx": "u_c + w_skill * e_skill + w_time * e_time",
            "e_units": ("each head's driver sum over its own consensus slope "
                        "(consensus-percentile equivalents)"),
            "grade": "consensus FV value of (side, V) at order_idx's within-group rank, "
                     "ties averaged (DS-07)",
            "war": "continuous WLS line of the training target on consensus FV, "
                   "evaluated at the eFV grade (pricing only)",
            "skill_candidates": {s: list(H.skill_candidates(s)) for s in F.SIDES},
            "timing_candidates_lv": {s: list(H.timing_candidates(
                s, ids_outcome_blind=True, absence_admitted=H.absence_admitted(s)))
                for s in F.SIDES},
            "timing_candidates_vm": {s: list(H.timing_candidates(s)) for s in F.SIDES},
            "pitchers": ("owner DS-Q2: consensus order in any fold where no pitcher skill "
                         "driver is admitted"),
            "scrapped": H.V2_SCRAPPED,
        },
        "weights": weights,
        "rule": {s: rules[s] for s in F.SIDES},
        "rule_statement": H.combiner_rule.__doc__,
        "prior_bio_tests": PRIOR_BIO_TESTS,
        "coverage": coverage(frames),
        "arms": arms,
        "n_arms": len(arms),
        "admitted": sorted(t for t, a in arms.items() if a["admitted"]),
        "refused": sorted(t for t, a in arms.items() if not a["admitted"]),
        "folds": {"lv": lv_folds,
                  "vm": {s: vm_folds(s, mat[s], weights) for s in F.SIDES}},
        "probes": probes,
        "n_probes": len(probes),
        "not_in_efv_progress": ("no V2 score is read here; the first V2 row in "
                                "data/efv_progress.json is DS-16's development read"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    doc = run()
    for s in F.SIDES:
        r = doc["rule"][s]
        print(f"{s}: rule {r['status']} n {r['n_pooled']} coef {r['coef']} "
              f"w_skill {r['w_skill']} w_time {r['w_time']} a {r['a']}")
    for tag, a in doc["arms"].items():
        print(f"{a['verdict']:9s} {tag:34s} signs {a['per_vintage_signs']} "
              f"mean|t| {a['mean_abs_t']} folds {a['n_folds_admitted']}/{len(DEV_FOLDS)}")
    for s in F.SIDES:
        for V, f in doc["folds"]["lv"][s].items():
            print(s, V, "skill", (f["skill"] or {}).get("keys"), "timing",
                  (f["timing"] or {}).get("keys"), "consensus_only", f["consensus_only"])
    if not args.dry_run:
        OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
