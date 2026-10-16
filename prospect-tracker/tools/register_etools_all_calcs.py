# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Register ETOOLS_ALL_CALCS (docs/tools-2026-10/ETOOLS_ALL_CALCS.md) in
data/model_registry.json and data/glossary.json. Idempotent.

Registry: a new `etool_composite` row (the shown Tool composite family, descriptive) and
a dated note on the rows whose basis the task decided (tool_implied_production,
mlb_projections_prospects_statline, fv_stuff_plus, composite_cmd_plus, tbs_prospect,
farm_grades). Glossary: a new `etool_composite` entry and one basis sentence on the Tool,
O-Tool, D-Tool and FVStuff+ entries. Every re-read figure is read from
data/_labs/etools/etools_all_calcs_reread.json; nothing is typed here. Each file keeps its
line endings, indent and ASCII setting (register_etools._load and _render). Then:

    python tools/register_etools_all_calcs.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import register_etools as RE  # noqa: E402

READS = ROOT / "data" / "_labs" / "etools" / "etools_all_calcs_reread.json"
DOC = "docs/tools-2026-10/ETOOLS_ALL_CALCS.md"
TAG = "ETOOLS_ALL_CALCS 2026-10-15:"
TOOL_NAME = {"hit": "hit to MLB K%", "game_pwr": "game power to ISO", "fb": "fastball to pitcher K%",
             "cmd": "command to pitcher BB%"}


def _reads() -> dict:
    return json.loads(READS.read_text(encoding="utf-8"))


def _tip_line(reads: dict) -> str:
    tip = (reads.get("R_TIP") or {}).get("tools") or {}
    parts = []
    for t in ("hit", "game_pwr", "fb", "cmd"):
        r = tip.get(t) or {}
        if r.get("mae_etool") is None:
            continue
        parts.append(f"{TOOL_NAME[t]} MAE {r['mae_etool']:.4g} vs {r['mae_consensus']:.4g} "
                     f"(UB95 {r['ub95']:+.4g}, margin {r['margin']:.4g}, n {r['n']}): {r['verdict'].lower()}")
    return "; ".join(parts)


def registry_rows(reads: dict) -> tuple[dict, dict]:
    tv = reads.get("R_TV") or {}
    row = {
        "model_id": "etool_composite",
        "summary": ("Unvalidated, descriptive: the tool composites built from the shown grades (eTool where one "
                    "passed, else consensus) by the unchanged formula; served since 2026-10-15."),
        "surface": ("Every PROSPX surface that prints or sorts on the Tool composite: the card chips (with the "
                    "consensus composite as 'cons N'), the row Tool pill, the strip TOOL chip, sorts, filters, "
                    "compare, GFX and the TBS term. Also FVStuff+ and Command+, the composite and per-tool flags, "
                    "the tiebreak inside exact board-grade ties, the farm Tool Quality leaf and the IFA class tool "
                    "line. tools.composite_cons keeps the consensus composites"),
        "predicts": "descriptive 20-80 composites of a prospect's shown tool grades",
        "champion": ("storage._compute_tool_composites on etool_composite.shown_grades (data/etools.json, matched by "
                     "player key then MLBAM id; the one Power grade reads game power's eTool, as the card does)"),
        "baseline": "the same composites on the consensus grades (tools.composite_cons)",
        "metric": ("none standalone; each passing eTool is measured under its own row (etool_*), and the registered "
                   "re-reads of the task decide the registered consumers"),
        "eval_artifact": None,
        "verdict": "unvalidated",
        "notes": (f"Owner decision EW3-30 (2026-10-15). Flag etool_composite.ETOOLS_COMPOSITE_ON (True); False "
                  f"reproduces the consensus payload byte for byte. Amateurs, IFA and overseas players have no "
                  f"minor-league line, so their eTool is the consensus grade and no number of theirs moves. Kept "
                  f"on consensus: the POW+, HIT+ and DISC+ blends (each already blends in the minor-league rate an "
                  f"eTool is built from), tool histories and deltas, per-source accuracy tables, comps (donor "
                  f"basis), eFV inputs (EFV_ETOOLS_REWEIGHT). R-TV (trade-value archetype policy, "
                  f"{tv.get('ran_at', 'not run')}): {tv.get('players_whose_output_differs')} of {tv.get('players')} "
                  f"priced rows read differently on the eTool FVStuff+ (a policy tag among them), so the policy "
                  f"stays on the consensus FVStuff+ (bayes_trade_value.POLICY_STUFF_PLUS_BASIS); its only scorer "
                  f"of a difference is the banned backtest. R-TIP: {_tip_line(reads)}."),
        "registration_status": "registered in " + DOC + "; re-reads R-TIP and R-TV read once 2026-10-15",
        "last_checked": "2026-10-15",
        "stale": False,
        "artifact_age_days": 0,
    }
    notes = {
        "tool_implied_production": (f"{TAG} R-TIP ({DOC} 3.1) read a TIP table at the eTool against one at the "
                                    f"consensus start on the eTools development frame: {_tip_line(reads)}. No served "
                                    f"reader takes a TIP table at the shown grade (the Source Accuracy tab scores "
                                    f"each outlet's own grade), so nothing served moves; the result licenses eTool "
                                    f"inputs in a later stat-line registration."),
        "mlb_projections_prospects_statline": (f"{TAG} kept on consensus tool inputs: its gate freezes the candidate "
                                               f"(Amendment 1) and allows one development read before TL_17's look, so "
                                               f"an eTool-input variant is a new registration after that look ({DOC} "
                                               f"3.2), licensed by R-TIP."),
        "fv_stuff_plus": (f"{TAG} served FVStuff+ is now the index of the eTool stuff composite (eFB in place of the "
                          f"consensus fastball where it passed); the consensus index rides under "
                          f"tools.composite_cons and is what the trade-value archetype policy reads (R-TV kept it)."),
        "composite_cmd_plus": (f"{TAG} served Command+ is now the index of eCMD where it passed (the command "
                               f"composite is the command grade); the consensus index rides under tools.composite_cons."),
        "tbs_prospect": (f"{TAG} the Tool composite term and the per-tool max read the shown grades (eTools where "
                         f"they passed), in the browser TBS and in the server tiebreak inside exact board-grade ties."),
        "farm_grades": (f"{TAG} the Tool Quality leaf (top-10 mean of the Tool composite) reads the eTool composite; "
                        f"it enters only the legacy blend, so the farm score, the farm letter and the farm rank do "
                        f"not move."),
    }
    return row, notes


def registry(row: dict, notes: dict) -> str:
    doc, raw, ea = RE._load(RE.REG)
    models = doc["models"]
    by_id = {r["model_id"]: r for r in models}
    cur = by_id.get(row["model_id"])
    if cur is not None:
        models[models.index(cur)] = dict(row)
    else:
        anchor = by_id.get("etool_ecmd")
        at = (models.index(anchor) + 1) if anchor is not None else len(models)
        models.insert(at, dict(row))
    for mid, note in notes.items():
        r = by_id.get(mid)
        if r is None:
            raise SystemExit(f"refusing: no registry row {mid}")
        cur_notes = r.get("notes") or ""
        if TAG in cur_notes:
            cur_notes = cur_notes[:cur_notes.index(TAG)].rstrip("\n ")
        r["notes"] = (cur_notes + "\n" + note) if cur_notes else note
    out = RE._render(doc, raw, ea)
    if out == raw:
        return "registry unchanged"
    RE.REG.write_bytes(out)
    return "registry written"


GLOSSARY_ENTRY = {
    "id": "etool_composite",
    "term": "eTool composite",
    "category": "custom-index",
    "section": "Prospects",
    "module": ["prospx"],
    "aliases": ["eTool composite", "Tool composite (eTools)", "eTool Tool", "eTools composite"],
    "priority": 41,
    "definition": ("The Tool, O-Tool, D-Tool, FVStuff+ and Command composites built from the tool grades the site "
                   "shows: the eTool where one passed (eHIT, ePOW, eSEL, eBAT, eFB, eCMD) and the consensus grade "
                   "for every other tool. It is the composite the site shows, with the consensus composite beside "
                   "it."),
    "methodology": ("Same formula, same inputs, one change: each tool with a passing eTool enters at its eTool "
                    "instead of its consensus grade, and the one Power grade reads game power's eTool, as the card "
                    "does. Frame, Athleticism and Delivery enter as before. The consensus composite is computed "
                    "beside it and printed as 'cons N'. Draft, IFA and overseas players have no minor-league line, so "
                    "there is no eTool for them and their composite is the consensus one. The composite is "
                    "descriptive: it has no outcome test of its own (each eTool has its own). The flags, the "
                    "same-grade tiebreak, the farm Tool Quality leaf and the Alchemy Lab starter shape read the "
                    "same shown grades. POW+, HIT+ and DISC+ keep the consensus grades because each already "
                    "blends in the minor-league rate an eTool is built from."),
    "formula": ("eTool composite = the composite formula on {eTool where passed, else consensus}; e.g. Tool = "
                "(sum g^4 / n)^(1/4) over hit, pwr (game power eTool), run, field, arm, pitch_sel, bat_ctrl, frame, "
                "athl"),
    "seeAlso": ["tool", "o_tool", "d_tool", "stuff_grade_plus", "etools"],
    "shelf": "ark",
    "origin": "Arkmetric, original to eephus.io.",
}

BASIS_SENTENCE = {
    "tool": ("Since 2026-10-15 it is built from the shown grades (an eTool where one passed); the consensus "
             "composite prints beside it (see eTool composite)."),
    "o_tool": ("Since 2026-10-15 it is built from the shown grades (eHIT, ePOW, eSEL and eBAT where they passed); the "
               "consensus composite prints beside it."),
    "d_tool": ("Field, arm and speed have no passing eTool, so D-Tool reads the consensus grades; it is computed "
               "under the eTool composite rule and equals the consensus composite."),
    "stuff_grade_plus": ("Since 2026-10-15 the stuff composite reads eFB where it passed (the shown fastball grade); "
                         "the consensus index is kept beside it."),
}


def glossary() -> str:
    doc, raw, ea = RE._load(RE.GLO)
    ents = doc["entries"]
    by_id = {e["id"]: e for e in ents}
    cur = by_id.get(GLOSSARY_ENTRY["id"])
    if cur is not None:
        ents[ents.index(cur)] = dict(GLOSSARY_ENTRY)
    else:
        anchor = by_id.get("d_tool")
        at = (ents.index(anchor) + 1) if anchor is not None else len(ents)
        ents.insert(at, dict(GLOSSARY_ENTRY))
    for gid, sentence in BASIS_SENTENCE.items():
        e = by_id.get(gid)
        if e is None:
            raise SystemExit(f"refusing: no glossary entry {gid}")
        m = e.get("methodology") or ""
        if sentence not in m:
            e["methodology"] = (m.rstrip() + " " + sentence) if m else sentence
        see = e.setdefault("seeAlso", [])
        if "etool_composite" not in see:
            see.append("etool_composite")
    out = RE._render(doc, raw, ea)
    if out == raw:
        return "glossary unchanged"
    RE.GLO.write_bytes(out)
    return "glossary written"


def main() -> int:
    reads = _reads()
    row, notes = registry_rows(reads)
    for blob in [json.dumps(row, ensure_ascii=False), json.dumps(notes, ensure_ascii=False),
                 json.dumps(GLOSSARY_ENTRY, ensure_ascii=False), json.dumps(BASIS_SENTENCE, ensure_ascii=False)]:
        if chr(0x2014) in blob or chr(0x2013) in blob:
            raise SystemExit("refusing: a dash in the registration text")
    print(registry(row, notes))
    print(glossary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
