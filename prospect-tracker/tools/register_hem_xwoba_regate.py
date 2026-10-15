# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Apply the registry consequence of docs/HEM_XWOBA_REGATE_GATE.md section 6
to the rows xhem_plus, fwdhem_plus and hem_plus, from the artifact
data/hem_xwoba_regate_eval.json, idempotently.

    python tools/register_hem_xwoba_regate.py                 apply (then python tools/gen_audit_docs.py)
    python tools/register_hem_xwoba_regate.py --dry-run <artifact.json>
                                                              format from a fixture artifact, write nothing

Every number written here is READ from the artifact; nothing is typed. The
rows move only when the artifact's verdict status is RAN and it carries the
owner-waived early read; a second call changes nothing (a marker in the notes).
Keeps the registry's CRLF line endings and one-space indent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART_REL = "data/hem_xwoba_regate_eval.json"
GATE = "docs/HEM_XWOBA_REGATE_GATE.md"
PRIOR_ART = {"xhem_plus": "data/xhem_served_regate_eval.json",
             "fwdhem_plus": "data/xhem_served_regate_eval.json",
             "hem_plus": "data/hem_plus_eval.json"}
ARM_OF = {"xhem_plus": "A1_xhem_plus", "fwdhem_plus": "A2_fwdhem_plus",
          "hem_plus": "A3_hem_plus"}
WINDOW = "2016-2026 ex-2020, forward pairs (served column, D4)"


def _ci(c) -> str:
    return (f"mean {c['mean']:+.4f} lo95 {c['lo95']:+.4f} hi95 {c['hi95']:+.4f}"
            if c else "none")


def _read_registry(path: Path):
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), (b"\r\n" in raw)


def _write_registry(path: Path, doc, crlf: bool) -> None:
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def _mark(art: dict) -> str:
    return f"RE-BASELINE READ {art['owner_waived_early_read']['run_date']} (OWNER-WAIVED EARLY READ"


def _card(model_id: str, art: dict) -> dict:
    arm = ARM_OF[model_id]
    lad = f"arms.{arm}.ladder.D4.v1"
    base_label = {"xhem_plus": "actual wOBA", "fwdhem_plus": "Savant xwOBA alone",
                  "hem_plus": "Savant xwOBA alone"}[model_id]
    champ_label = {"xhem_plus": "xHEM+", "fwdhem_plus": "xHEM+ Blend", "hem_plus": "HEM+"}[model_id]
    heads = [{"label": f"Next-year offense (Spearman), served {champ_label} column",
              "better": "higher", "baseline_label": base_label, "stat": "Spearman"}]
    specs = [{"champion": f"{lad}.rho_primary", "baseline": f"{lad}.rho_baseline",
              "resolvable": f"{lad}.lo95_gt_0", "verdict": f"arms.{arm}.verdict_reason",
              "gap_ci": {"lo": f"{lad}.gap_ci.lo95", "hi": f"{lad}.gap_ci.hi95"}}]
    if model_id == "hem_plus":
        s = "sensitivity_A3s_served_hem_vs_actual_woba.v1"
        heads.append({"label": "Next-year offense (Spearman), served HEM+ column",
                      "better": "higher",
                      "baseline_label": "raw wOBA (the parent its gate names; sensitivity, no verdict weight)",
                      "stat": "Spearman"})
        specs.append({"champion": f"{s}.rho_primary", "baseline": f"{s}.rho_baseline",
                      "resolvable": {"above_zero": f"{s}.gap_ci.lo95"},
                      "gap_ci": {"lo": f"{s}.gap_ci.lo95", "hi": f"{s}.gap_ci.hi95"}})
    card = {"window": WINDOW, "headline": heads,
            "derived_from": {"n": f"n_forward_pairs.{arm[:2]}", "digits": 3,
                             "headline": specs}}
    sys.path.insert(0, str(ROOT))
    import model_registry  # noqa: PLC0415
    return model_registry.derive_card({"card": card, "eval_artifact": ART_REL}, art)


def _consequence(model_id: str, a: dict) -> tuple[str, str]:
    """(verdict, the claim sentence) per gate section 6 for this row."""
    row = a["table_row"]
    v = a["verdict"]
    if model_id == "fwdhem_plus":
        if row == "both":
            return "validated", ("PROMOTED back to validated: the registered re-read R1-12 "
                                 "named clears both conventions after Holm (k=3).")
        if row == "refuted":
            return "deprecated", "REFUTED at the extended n; the claim is contradicted."
        return "provisional", ("STAYS PROVISIONAL: the extended n did not separate the "
                               "served column from xwOBA alone either (table row "
                               f"{row}).")
    if model_id == "hem_plus":
        if row == "both":
            return "validated", ("VALIDATED against Savant xwOBA on the served construction; "
                                 "the baseline line adds xwOBA as a beaten baseline.")
        if row == "refuted":
            return "deprecated", ("REFUTED (loss ledger): the served HEM+ column is forecast "
                                  "better by the Savant xwOBA beside it; the column continues "
                                  "to ship, and its place beside xHEM+ is the display lane's "
                                  "question (gate section 9).")
        return "provisional", ("DEMOTED to provisional: not separable from Savant xwOBA on "
                               f"the served construction at this n (table row {row}); the "
                               "AVG win stays in the notes as history.")
    if row == "both":
        return "validated", "STAYS VALIDATED at the extended n after Holm (k=3)."
    if row == "refuted":
        return "deprecated", "REFUTED at the extended n; the claim is contradicted."
    return "provisional", f"DEMOTED to provisional at the extended n (table row {row})."


def _block(model_id: str, art: dict) -> str:
    arm = art["arms"][ARM_OF[model_id]]
    d4 = arm["ladder"]["D4"]
    cov = art["coverage"]
    n = art["n_forward_pairs"][ARM_OF[model_id][:2]]
    ow = art["owner_waived_early_read"]
    verdict, claim = _consequence(model_id, arm)
    holm = {}
    for conv in ("v1", "v2"):
        for r in art["multiplicity"][conv].get("cells", []):
            if r.get("key") == ARM_OF[model_id]:
                holm[conv] = r
    s = (f"{_mark(art)}; registered date {ow['registered_date']}; {ow['authority']}). "
         f"{GATE}, arm {ARM_OF[model_id]}, verdict rung D4 (the served integer column): on the "
         f"extended pair set n {n:,} (predictor seasons {json.dumps(cov['pair_set_n_by_predictor_season'])}; "
         f"the {cov['new_block_predictor_season']} block adds {cov['new_block_n']} pairs under the logged "
         f"override {json.dumps(ow['season_complete_override']['seasons'])}), rho {d4['v1']['rho_primary']} "
         f"against {arm['baseline']} {d4['v1']['rho_baseline']}, gap v1 {_ci(d4['v1']['gap_ci'])} "
         f"(in-run MDE95 {d4['v1']['mde95_in_run']}), v2 rho {d4['v2']['rho_primary']} against "
         f"{d4['v2']['rho_baseline']}, gap v2 {_ci(d4['v2']['gap_ci'])} (MDE95 {d4['v2']['mde95_in_run']}). "
         f"Holm k = 3: v1 p {holm.get('v1', {}).get('p_one_sided')} reject {holm.get('v1', {}).get('reject_holm')}, "
         f"v2 p {holm.get('v2', {}).get('p_one_sided')} reject {holm.get('v2', {}).get('reject_holm')}; "
         f"passes_v1_after_holm {arm['passes_v1_after_holm']}, passes_v2_after_holm {arm['passes_v2_after_holm']}; "
         f"table row {arm['table_row']}. CONSEQUENCE: {claim} Pre-registered expectation: "
         f"{arm['pre_registered_expectation']}. ")
    if model_id == "hem_plus":
        a3s = art["sensitivity_A3s_served_hem_vs_actual_woba"]
        a1s = art["sensitivity_A1s_served_xhem_vs_served_hem"]
        s += (f"SENSITIVITIES, zero verdict weight: served HEM+ against raw actual wOBA(Y) on the same rows "
              f"(A3s) rho {a3s['v1']['rho_primary']} vs {a3s['v1']['rho_baseline']}, gap v1 {_ci(a3s['v1']['gap_ci'])}, "
              f"v2 {_ci(a3s['v2']['gap_ci'])}; served xHEM+ against served HEM+ (A1s) rho {a1s['v1']['rho_primary']} "
              f"vs {a1s['v1']['rho_baseline']}, gap v1 {_ci(a1s['v1']['gap_ci'])}. The served construction is "
              f"{arm['served_construction']} Unrounded D3: rho {arm['ladder']['D3']['v1']['rho_primary']} "
              f"(rounding to the served integer costs the difference to D4); ties at D4 {d4['n_tied_rows']} of {n:,}. "
              f"The row's ORIGINAL gate ({PRIOR_ART['hem_plus']}, 2012-2024 StatsAPI frame, 3,372 pairs: beats AVG "
              f"lo95 +0.145, ties raw wOBA lo95 -0.0096, OPS lo95 -0.013) is retained as history and is not the "
              f"claim this verdict grades. ")
    else:
        rep = art["frozen_subset_reproduction"][ARM_OF[model_id]]
        n_old = art["frozen_subset_reproduction"]["n_old_rows"][ARM_OF[model_id][:2]]
        s += (f"Frozen-subset reproduction of the 2026-09-18 D4 cells ({PRIOR_ART[model_id]}, "
              f"{n_old} rows): reproduces {rep['reproduces']}. Ladder at the extended n "
              f"(v1 rho): " + ", ".join(f"{r} {arm['ladder'][r]['v1']['rho_primary']}"
                                        for r in ("D0", "D1", "D2", "D3", "D4")) + ". ")
    s += ("Coverage: the gate speaks only about the PA >= 200 subset while the board stamps every tracked "
          "hitter at PA >= 100 (served pools per season "
          f"{json.dumps({y: v['xhem_pool_pa_ge_100'] for y, v in cov['served_normalizer_pool_by_season'].items()})}). "
          f"Artifact {ART_REL}; producer tools/hem_xwoba_regate_lab.py (seed {art['seed']}, {art['boot']} reps); mover "
          "tools/register_hem_xwoba_regate.py. Next re-baseline not before 2027-11-16, in its own document.")
    return s


def _summary(model_id: str, art: dict) -> str:
    arm = art["arms"][ARM_OF[model_id]]
    d4 = arm["ladder"]["D4"]["v1"]
    n = art["n_forward_pairs"][ARM_OF[model_id][:2]]
    verdict, _ = _consequence(model_id, arm)
    head = {"validated": "Validated", "provisional": "Provisional", "deprecated": "Refuted"}[verdict]
    base = {"xhem_plus": "actual wOBA", "fwdhem_plus": "xwOBA alone", "hem_plus": "Savant xwOBA"}[model_id]
    return (f"{head} on the served construction at the extended n ({art['owner_waived_early_read']['run_date']}): "
            f"rho {d4['rho_primary']} vs {base} {d4['rho_baseline']} (n {n:,}, lo95 {d4['gap_ci']['lo95']:+.4f}, "
            f"hi95 {d4['gap_ci']['hi95']:+.4f}).")


def apply(doc: dict, art: dict, force: bool = False) -> list[str]:
    """Move the three rows in place; returns the ids moved ([] when nothing).
    `force` is the dry run's switch: it formats from a fixture artifact whose
    status is not RAN, and the dry run never writes."""
    ran = art.get("verdict", {}).get("status") == "RAN"
    if (not ran and not force) or not art.get("owner_waived_early_read") or "arms" not in art:
        return []
    by_id = {r["model_id"]: r for r in doc["models"]}
    moved = []
    for model_id in ("xhem_plus", "fwdhem_plus", "hem_plus"):
        row = by_id[model_id]
        if _mark(art) in (row.get("notes") or ""):
            continue
        arm = art["arms"][ARM_OF[model_id]]
        verdict, _claim = _consequence(model_id, arm)
        row["summary"] = _summary(model_id, art)
        row["verdict"] = verdict
        if model_id == "hem_plus":
            # The HEM+ card layout is an OWNER ANSWER (M27-1, 2026-09-25: AVG, raw
            # wOBA and OPS, each read from data/hem_plus_eval.json; pinned by
            # test_model_report_cards.py), which the registration of 2026-10-15 did
            # not know. The card and the eval_artifact therefore STAY; the verdict,
            # the summary, the baseline and metric lines and the notes carry the
            # re-gate, with the artifact cited by path. Recorded in the gate
            # document's section 12 as a disagreement, not edited away.
            row["metric"] = ((row.get("metric") or "").rstrip(".") + "; re-gated 2026-10-15 on the SERVED "
                             "integer column against Savant xwOBA alone, bootstrap lo95 > 0 under both "
                             "conventions, Holm k = 3 (" + GATE + ", " + ART_REL + ")")
            row["baseline"] = ("AVG (naive rate baseline) and raw wOBA (its parent), the original gate; "
                               "Savant xwOBA alone, the 2026-10-15 re-gate baseline ("
                               + ("beaten" if verdict == "validated" else
                                  "not beaten" if verdict == "provisional" else "lost to")
                               + ")")
        else:
            row["eval_artifact"] = ART_REL
            row["card"] = _card(model_id, art)
            row["metric"] = ("Spearman of the served column vs next-year wOBA against "
                             + ("actual wOBA" if model_id == "xhem_plus" else "xwOBA alone")
                             + "; bootstrap lo95 > 0 under both conventions, Holm k = 3 (" + GATE + ")")
        row["notes"] = _block(model_id, art) + " PRIOR NOTES (retained, through 2026-10-14): " + (row.get("notes") or "")
        row["last_checked"] = art["owner_waived_early_read"]["run_date"]
        if model_id != "hem_plus":          # its artifact is new today; hem_plus keeps its own
            row["stale"] = False
            row["artifact_age_days"] = 0
        moved.append(model_id)
    return moved


def main(argv: list[str]) -> int:
    if argv[:1] == ["--dry-run"]:
        art = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        doc, _crlf = _read_registry(REG)
        moved = apply(doc, art, force=True)
        for r in doc["models"]:
            if r["model_id"] in moved:
                print(json.dumps({k: r[k] for k in ("model_id", "summary", "verdict", "eval_artifact",
                                                    "baseline", "card")}, indent=1))
                print("NOTES:", r["notes"][:1200])
        print(f"dry run: {moved or 'nothing'} would move; nothing written")
        return 0
    if argv:
        print(__doc__)
        return 2
    art = json.loads((ROOT / ART_REL).read_text(encoding="utf-8"))
    doc, crlf = _read_registry(REG)
    moved = apply(doc, art)
    if not moved:
        print("registry already carries this run (or the artifact did not RAN); nothing written")
        return 0
    _write_registry(REG, doc, crlf)
    sys.path.insert(0, str(ROOT))
    import model_registry  # noqa: PLC0415
    problems = model_registry.validate(model_registry.load())
    print(f"moved {moved}; validate -> {problems or 'clean'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
