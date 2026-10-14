"""Record look W in data/model_registry.json (idempotent; task TL_12_TOOL_WEIGHTS_LOOK,
docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part 8 'Look W', 2026-10-14).

Reads data/tool_accuracy_eval.json and, once: points tool_source_accuracy at it (a row
that carries an artifact may not read unvalidated, so the verdict moves to provisional,
measured_not_adopted: the look is VOID under W.7 and equal weight retains), rewrites its
summary and registration status and appends one dated note; points
tool_implied_production at the same artifact (its TAG tables and TIP_f3 tables live under
result.tag) and appends one dated note; appends the pointer note on ba_tool_grade_weight
(superseded at look W by tool_source_accuracy). Keeps the file's line endings (CRLF) and
its one-space indent. Running it twice changes nothing. Then regenerate
MODEL_REGISTRY.md:

    python tools/register_tool_look_w.py
    python tools/gen_audit_docs.py   (or render_one("MODEL_REGISTRY.md") alone)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART = ROOT / "data" / "tool_accuracy_eval.json"
ART_REL = "data/tool_accuracy_eval.json"
DATE = "2026-10-14"
MARK = f"LOOK W {DATE} (TL_12_TOOL_WEIGHTS_LOOK)"


def _primary_line(tool: str, blk: dict) -> str:
    a = blk["arms"]["A_fg_vs_pipeline"]
    pr, g, bt, hz = a.get("primary") or {}, a.get("gate") or {}, a.get("bootstrap") or {}, blk.get("holm") or {}
    ev = a.get("evaluable_years")
    return (f"{tool} ({blk['stat']}) {blk['verdict']}: n {pr.get('n')}, evaluable board years {ev}, "
            f"equal rho {(pr.get('equal') or {}).get('spearman')} weighted rho {(pr.get('weighted') or {}).get('spearman')}, "
            f"d_rho {pr.get('d_rho')} (F_rho {g.get('F_rho')}, lo95 {bt.get('d_rho_lo95')}, hi95 {bt.get('d_rho_hi95')}), "
            f"d_auc {pr.get('d_auc')}, permutation p {g.get('p_rho')}, Holm step {hz.get('step')} rejected {hz.get('rejected')}, "
            f"G1 to G5 {g.get('G1_to_G5')}, loss clause {g.get('loss_clause')}, shuffled outcome collapsed "
            f"{g.get('shuffled_outcome_collapsed')}, verdict moves between seeds {g.get('verdict_moves_between_seeds')}")


def notes(art: dict, sha: str) -> dict:
    res = art["result"]
    spd = res["primaries"]["speed"]["arms"]["A_fg_vs_pipeline"]["C63_shuffled_outcome_null"]
    band = 2.5 / (spd["n"] ** 0.5)
    prim = "; ".join(_primary_line(t, b) for t, b in res["primaries"].items())
    tag_bits = []
    for tool, t in res["tag"].items():
        srcs = "; ".join(f"{s} n {b.get('n')} ordering {b.get('ordering')} bias {b.get('bias_regressed')} "
                         f"PIT {b.get('bias_pit')} error {b.get('error_abs_regressed')}"
                         + (" NOT COMPUTABLE" if not b.get("computable") else "")
                         for s, b in (t.get("by_source") or {}).items())
        tag_bits.append(f"{tool} to {t.get('stat')} (frame {t.get('n_frame')}, k_m {t.get('k_m')}, "
                        f"regressed {'yes' if t.get('regressed') else 'NOT COMPUTABLE'}): {srcs}")
    uc = art.get("universe_counts") or {}
    tsa = (f"{MARK}: read once from HEAD 01593da7 by python -u tools/tool_accuracy_lab.py --look W --gate-sha "
           f"{art['gate_sha']} --rlv-record {art['rlv_record']}, an OWNER-WAIVED EARLY READ under EW3-5 (owner "
           f"2026-10-14; registered day 2026-12-03 replaced by W.11's rule, both waived). Artifact {ART_REL} sha256 {sha}, "
           f"spent; inputs unchanged through the run ({len(art.get('inputs_sha256_start') or {})} inputs); display copy only "
           f"at .cache/tool_accuracy/preview/tool_source_accuracy.json. Frame W.8: board years 2017 to 2024 (2020 and 2021 "
           f"admitted on the R-LV record), debut year at most 2024, MLB seasons through 2026; universe rows {uc.get('rows')}. "
           f"VERDICT: THE LOOK IS VOID (W.7): the speed cell's C6.3 shuffled-outcome control did not collapse (weighted blend "
           f"Spearman {spd['weighted']['spearman']} on the within-board-year permuted outcome at n {spd['n']}, band 2.5 / sqrt(n) "
           f"{band:.4f}). Per-tool lines, credited to nothing: {prim}. Arm B NULL by construction (Baseball America's earliest "
           f"tool vintage 2023); board years 2017 to 2019 carry flat weights and are skipped (W.9), so the informative rows are "
           f"BA2's own board years and a hit result is not independent of BA2. Secondaries descriptive only, BA2's verdicts "
           f"stand. EQUAL WEIGHT RETAINS for every tool; tools_consensus_w is not built; no served number moves. A re-read of "
           f"look W needs a new registration (Part 5 clause 5: no second run, seed, frame or estimator). Every number is "
           f"accuracy AMONG DEBUTS (Part 0.6). No FV cell was read, grouped or labelled.")
    tip = (f"{MARK}: the TAG tables of W.5 were computed on look W's frame and live in {ART_REL} under result.tag (the "
           f"leave-one-board-year-out TIP_f3 tables per board year with thin bins, and per source and board year the gap, the "
           f"PIT and, where k_m exists, the regressed gap; sprint speed, OAA and arm strength have no regressed TAG). "
           f"Per tool, pooled: {'; '.join(tag_bits)}. Descriptive; the look itself is VOID under W.7; nothing served reads a table.")
    ba2 = (f"SUPERSEDED AT LOOK W ({DATE}) by tool_source_accuracy: that row re-read the tool pairs on board years 2017 to "
           f"2024 after the R-LV record ({ART_REL}; the look is VOID under its gate's W.7 and equal weight retains), and "
           f"carries the current reading. This row's 2026-08-08 result stands as recorded and is credited to no eFV V2 "
           f"candidate (TOOL_IMPLIED_PRODUCTION_GATE.md Part 0.1).")
    return {"tool_source_accuracy": tsa, "tool_implied_production": tip, "ba_tool_grade_weight": ba2}


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    by_id = {r["model_id"]: r for r in doc["models"]}
    art = json.loads(ART.read_text(encoding="utf-8"))
    assert art.get("look") == "W" and art.get("spent") is True, "data/tool_accuracy_eval.json is not look W's record"
    sha = hashlib.sha256(ART.read_bytes()).hexdigest()
    nts = notes(art, sha)
    changed = []

    r = by_id["tool_source_accuracy"]
    if MARK not in (r.get("notes") or ""):
        r["eval_artifact"] = ART_REL
        r["verdict"] = "provisional"
        r["provisional_kind"] = "measured_not_adopted"
        r["registration_status"] = f"read once {DATE} (look W): VOID under W.7, equal weight retains"
        r["summary"] = ("Read once (look W, 2026-10-14): VOID under W.7, the speed cell's shuffled-outcome control "
                        "did not collapse; hit NULL, field NULL, throw LOSS, credited to nothing. Equal weight retains.")
        r["metric"] = r["metric"].replace("Registered, not computed: ", f"Computed once at look W ({DATE}), the look VOID under W.7: ", 1)
        r["notes"] = (r.get("notes") or "").rstrip() + " " + nts["tool_source_accuracy"]
        changed.append("tool_source_accuracy")

    r = by_id["tool_implied_production"]
    if MARK not in (r.get("notes") or ""):
        r["eval_artifact"] = ART_REL
        r["provisional_kind"] = "measurement_only"
        r["registration_status"] = f"TAG tables computed once at look W ({DATE}); the tables are read by nothing served"
        r["summary"] = ("Provisional, measured once at look W (2026-10-14): grade-to-stat tables (TIP) for the tool "
                        "framework and the TAG tables per source, tool and board year; nothing served reads them.")
        r["metric"] = r["metric"].replace("Registered, not computed: ", f"Computed once at look W ({DATE}): ", 1)
        r["notes"] = (r.get("notes") or "").rstrip() + " " + nts["tool_implied_production"]
        changed.append("tool_implied_production")

    r = by_id["ba_tool_grade_weight"]
    if "SUPERSEDED AT LOOK W" not in (r.get("notes") or ""):
        r["notes"] = (r.get("notes") or "").rstrip() + " " + nts["ba_tool_grade_weight"]
        changed.append("ba_tool_grade_weight")

    if not changed:
        print("registry already carries the look W record; nothing written")
        return 0
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))
    print("registry written:", ", ".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
