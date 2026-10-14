"""Record the W2 Tier-2 veto read on the proj_component_stack registry row
(idempotent; task PJ_9_STACK_ARM_DARK, docs/PROJ_COMPONENTS_GATE.md section 6).

Appends one dated note to the row's notes, naming the veto read's result
(data/proj_horizon_eval.json challenger_blocks.component_stack_tier2_veto),
and restates the summary and registration status. eval_artifact stays null:
the verdict artifact is the 2027 look's (PJ_11). Keeps the file's line
endings (CRLF) and its one-space indent. Running it twice changes nothing.
Then regenerate MODEL_REGISTRY.md:

    python tools/register_component_stack_veto.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ARTIFACT = ROOT / "data" / "proj_horizon_eval.json"
MODEL_ID = "proj_component_stack"
MARKER = "VETO READ 2026-10-14 (PJ_9_STACK_ARM_DARK)"


def _block() -> dict:
    doc = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    blk = (doc.get("challenger_blocks") or {}).get("component_stack_tier2_veto")
    if not blk:
        raise SystemExit("data/proj_horizon_eval.json carries no component_stack_tier2_veto block; "
                         "run tools/proj_component_stack.py --veto-read first")
    return blk


def note_text(blk: dict) -> str:
    p = blk.get("pooled") or {}
    sv = blk.get("survived_only") or {}
    st = blk.get("star_slice") or {}
    pb = blk.get("per_base") or {}
    ps = blk.get("per_side") or {}

    def f(v, d=4):
        return "n/a" if v is None else f"{v:+.{d}f}"

    bases = ", ".join(f"{b} n {s.get('n')} delta {f(s.get('delta'))}" for b, s in pb.items())
    sides = ", ".join(f"{b} n {s.get('n')} delta {f(s.get('delta'))}" for b, s in ps.items())
    verdict = "VETOED" if blk.get("vetoed") else "not vetoed"
    return (
        f"{MARKER}: the W2 Tier-2 veto read (gate section 6, round 4 leakage 9) ran on 2026-10-14 as an "
        f"owner-waived early read (EW3-5: it was registered to follow the path-shape ARM B verdict, which "
        f"does not exist yet, so the twin is a twin of the incumbent serving bundle, train_hash "
        f"{(blk.get('serving_bundle') or {}).get('train_hash')}, max_label_season "
        f"{(blk.get('serving_bundle') or {}).get('max_label_season')}, war_provider fwar). "
        f"Bases {blk.get('bases')}, h1, forward-chained point-in-time twin and incumbent bundles (labels at most "
        f"B - 1, full quantiles, no blend lambdas, raw q50), identical rows, absent season 0 WAR, paired "
        f"bootstrap clustered on player B {blk['bootstrap']['B']} seed {blk['bootstrap']['seed']} VIF "
        f"{blk['bootstrap']['vif']}, label READ. Pooled: n {p.get('n_rows')} rows, {p.get('n_players')} players, "
        f"MAE twin {f(p.get('mae_twin'))} incumbent {f(p.get('mae_incumbent'))}, delta {f(p.get('delta'))}, "
        f"one-sided 95% upper bound {f(p.get('ub95'))}, MDE95 {f(p.get('mde95'))} against the bar +0.0065: "
        f"{verdict}. Survived only: n {sv.get('n_rows')}, delta {f(sv.get('delta'))}, ub95 {f(sv.get('ub95'))}. "
        f"Star slice (base WAR at least 4): n {st.get('n_rows')}, delta {f(st.get('delta'))}, ub95 {f(st.get('ub95'))}. "
        f"Per base: {bases}. Per side: {sides}. Stack schema {blk.get('schema_tag')}: the serving schema plus "
        f"bsr_rate_proj, fld_rate_proj, pos_rate_proj, sprint_l1, sprint_missing (hitters) and gmli_proj, "
        f"ra9_gap_proj (pitchers) from the DEV-frozen component heads (params sha256 "
        f"{blk.get('component_params_sha256')}), vintage {blk.get('vintage_id')}. No number here is cited "
        f"for a pass; the 2027 look (PJ_11) is the verdict artifact and eval_artifact stays null. "
        + ("The twin is not saved to model/proj_lgbm_components/ for the Opening Day freeze."
           if blk.get("vetoed") else
           "The twin bundle for the Opening Day freeze (model/proj_lgbm_components/) is trained by "
           "tools/proj_component_stack.py --final on the serving max_label_season and is never loaded "
           "by the served path (test_proj_component_stack.py).")
    )


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    row = next((r for r in doc["models"] if r["model_id"] == MODEL_ID), None)
    if row is None:
        raise SystemExit(f"registry has no {MODEL_ID} row")
    blk = _block()
    verdict = "VETOED" if blk.get("vetoed") else "not vetoed"
    # at most 30 words (model_registry.SUMMARY_MAX_WORDS)
    summary = (
        "Registered, not read: a dark twin of the serving WAR-path bundle with component stack "
        f"features, never served; its 2026-10-14 Tier-2 veto read left it {verdict} "
        f"(ub95 {(blk.get('pooled') or {}).get('ub95'):+.4f}).")
    status = ("registered, not read on 2027; the Tier-2 veto read of 2026-10-14 is "
              "recorded in notes and in data/proj_horizon_eval.json (READ, no verdict)")
    if MARKER in (row.get("notes") or ""):
        if row.get("summary") == summary and row.get("registration_status") == status:
            print("registry already carries the veto read note; nothing written")
            return 0
    else:
        row["notes"] = (row.get("notes") or "").rstrip() + " " + note_text(blk)
    row["summary"] = summary
    row["registration_status"] = status
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))
    print(f"registry written: {MODEL_ID} ({verdict})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
