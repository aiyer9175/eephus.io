# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Register the six passing eTools (docs/tools-2026-10/ETOOLS_GATE.md and its two
amendments) in data/model_registry.json (one provisional row per eTool) and
data/glossary.json (an eTools entry and one entry per eTool). Idempotent.

Every figure is read from data/etools_eval.json (python etools.py --library), the
summary the eTools builder copies out of the lab artifacts; nothing is typed here.
Each file keeps its own line endings, indent and ASCII setting; the script refuses
when a plain round trip would rewrite either file. Then:

    python tools/register_etools.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
GLO = ROOT / "data" / "glossary.json"
SUMMARY = ROOT / "data" / "etools_eval.json"
ARTIFACT = "data/etools_eval.json"

#: eTool key -> (glossary id, plain name, the outcome in words, card tool name)
ETOOLS = {
    "eHIT": ("ehit", "eHIT", "MLB strikeout rate (lower is better), the framework's hit outcome", "Hit"),
    "ePOW": ("epow", "ePOW", "MLB ISO, the framework's game-power outcome", "Game Power"),
    "eSEL": ("esel", "eSEL", "MLB chase rate (lower is better), 2026 season", "Pitch Sel"),
    "eBAT": ("ebat", "eBAT", "MLB zone-contact rate, 2026 season", "Bat Ctrl"),
    "eFB": ("efb", "eFB", "MLB pitcher strikeout rate", "Fastball"),
    "eCMD": ("ecmd", "eCMD", "MLB pitcher walk rate (lower is better)", "Command"),
}


def _n(v, dp=3) -> str:
    x = float(v)
    return f"{x:+.{dp}f}"


def _r(v, dp=3) -> str:
    return f"{float(v):.{dp}f}"


def _summary() -> dict:
    d = json.loads(SUMMARY.read_text(encoding="utf-8"))
    return {t["key"]: t for t in d["tools"]}, d


def _subs(t: dict) -> str:
    labs = [a["label"] for a in t.get("admitted") or []]
    return labs[0] if len(labs) == 1 else ", ".join(labs[:-1]) + " and " + labs[-1]


def registry_row(t: dict, doc: dict) -> dict:
    gid, _name, outcome, card = ETOOLS[t["key"]]
    m, u = t["labels"]["mlb"], t["labels"]["um"]
    pr = t.get("promotion_reads") or {}
    dr = t.get("drift") or {}
    look = str((doc.get("gate") or {}).get("look_at") or "")[:10]
    fp = str(((doc.get("amendments") or [{}, {}])[1] or {}).get("read_at") or "")[:10]
    prom = []
    if pr.get("l_any_unmeasured"):
        prom.append(f"on the rows with no debut and no Double-A line {_n(pr['l_any_unmeasured']['d'])} "
                    f"(LB {_n(pr['l_any_unmeasured']['lb95'])})")
    if pr.get("ipw_um"):
        prom.append(f"re-weighted for promotion {_n(pr['ipw_um']['d'])} (LB {_n(pr['ipw_um']['lb95'])})")
    return {
        "model_id": f"etool_{gid}",
        "summary": (f"Provisional: beats the consensus {t['name'].lower()} grade on both labels, MLB "
                    f"{_r(m['rho_consensus'])} to {_r(m['rho_etool'])} (LB {_n(m['lb95'])}), minors "
                    f"{_r(u['rho_consensus'])} to {_r(u['rho_etool'])} (LB {_n(u['lb95'])}); shown site-wide since 2026-10-15."),
        "surface": ("The shown tool grade (marked e, to the nearest whole grade) on PROSPX cards, list rows, the "
                    "compare table, GFX cards and the tool sort and filter, the MLB player page's Scouting pills "
                    "and the Alchemy Lab's Prospect Watch bars (data/etools.json, written by etools.py --preview); "
                    "the Library's eTools view. Since 2026-10-15 the tool composites, the tool flags, the "
                    "tiebreaks, the farm Tool Quality and the Alchemy Lab starter shape read it too. eFV and the "
                    "POW+, HIT+ and DISC+ blends do not read it"),
        "predicts": f"The tool's outcome stat: {outcome}; and its translated Double-A and Triple-A equivalent",
        "champion": (f"{t['key']} (etools.py): the consensus {t['name'].lower()} grade plus the weighted residuals "
                     f"of its sub-drivers ({_subs(t)}), fit on the grade scale by leave one board year out, "
                     f"re-centred on the scoring cohort (amendment 2 F1.7)"),
        "baseline": "the consensus tool grade (the plain mean of FanGraphs, MLB Pipeline and Baseball America)",
        "metric": ("within-board-year Spearman against the outcome, eTool minus consensus, board years 2011 to "
                   "2019 and 2022 to 2024; pass iff the one-sided 95% lower bound is above 0 on both the MLB "
                   "label (among debuts) and the translated upper-minors label; player-clustered bootstrap B 2000"),
        "eval_artifact": ARTIFACT,
        "verdict": "provisional",
        "notes": (
            f"Registered in docs/tools-2026-10/ETOOLS_GATE.md (3f240da6), read once {look}; amendment 1 (8f369ae2) "
            f"and amendment 2 (9121d710, read {fp}). Served since 2026-10-15 by owner decision EW3-27 "
            f"(ETOOLS_ON True); provisional because its passes are development reads with no forward read yet. "
            f"EFV_ETOOLS_REWEIGHT decides whether eFV reads it. MLB d {_n(m['d'])} "
            f"(n {m['n']}), minors d {_n(u['d'])} (n {u['n']}). Flip checks: "
            + ("; ".join(prom) + "; " if prom else "")
            + f"label {t.get('promotion_label') or 'n/a'}; 2026 boards shift {_n(dr.get('live_shift'), 2)} "
              f"(development years {_n(dr.get('dev_min'), 2)} to {_n(dr.get('dev_max'), 2)}"
              f"{', outside' if dr.get('drifted') else ''}), served re-centred. Lower bounds hold with each "
              f"bootstrap draw re-ranked ({_n((t.get('reranked_lb95') or {}).get('mlb'))} MLB, "
              f"{_n((t.get('reranked_lb95') or {}).get('um'))} minors)."
        ),
        "registration_status": ("read once at the gate look and amendments 1 and 2; served since 2026-10-15 "
                                "(owner decision EW3-27)"),
        "last_checked": fp or look,
        "stale": False,
        "artifact_age_days": 0,
    }


def glossary_entries(tools: dict, doc: dict) -> list[dict]:
    keys = [k for k in ETOOLS if (tools.get(k) or {}).get("verdict") == "PASS"]
    out = [{
        "id": "etools",
        "term": "eTools",
        "category": "custom-index",
        "section": "Prospects",
        "module": ["prospx"],
        "aliases": ["eTool", "stat-adjusted tool grades"] + keys,
        "priority": 40,
        "definition": ("A scouting tool grade moved by the prospect's own minor-league stats: the consensus "
                       "grade, plus what the stats that predict the tool's outcome say beyond it. Built for the "
                       f"tools where it beat the consensus grade on both outcomes: {', '.join(keys)}."),
        "methodology": (
            "Each tool grade has an outcome stat it predicts in the FanGraphs framework: the hit tool, MLB "
            "strikeout rate; game power, ISO; pitch selection, chase rate; bat control, zone contact; the "
            "fastball, a pitcher's strikeout rate; command, his walk rate. For each tool, minor-league stats "
            "dated before the list (translated across levels and leagues and shrunk toward the average by "
            "sample size) were tested for what they add to the consensus grade at predicting that stat, with "
            "each list year held out in turn and its players removed from the fit. Up to three that added "
            "with a lower bound above zero became the tool's sub-drivers. The eTool is the consensus grade "
            "plus each sub-driver's surprise (its value minus what the grade already implies), weighted on "
            "the grade scale. It passed only when it beat the consensus grade on both MLB players (among "
            "debuts) and the translated Double-A and Triple-A line.\n\n"
            "Before any card shows one, four checks ran once: the 2026 boards against the development "
            "years (eFB sat outside them, so every eTool is centred on the board it scores), the gain on "
            "players who never reached Double-A or the majors, and two arithmetic fixes. Raw power, speed, "
            "field, arm and the secondary pitches keep the consensus grade.\n\n"
            "Since 2026-10-15 (owner decision) the eTool is the grade the site shows for these six tools "
            "wherever it prints a tool grade, marked e. It is a model grade, so it rounds to the nearest "
            "whole grade, like eFV; consensus tool grades round up and are marked c. The card keeps the "
            "consensus grade beside each eTool, with the 80% band and each sub-driver's push in grade "
            "points. Since ETOOLS_ALL_CALCS the tool composites (Tool, O-Tool, D-Tool, FVStuff+, Command), "
            "the tool flags, the tiebreaks and the Alchemy Lab starter shape read the eTools too. Not in eFV "
            "or the POW+, HIT+ and DISC+ blends, which already blend in the minor-league rates an eTool is "
            "built from."
        ),
        "formula": ("eTool = consensus + sum over sub-drivers j of c_j x (z_j - a_j - b_j x consensus - delta_j); "
                    "band = eTool +/- 1.2816 x the fit's residual sd"),
        "seeAlso": ["hit_tool", "game_power", "pitch_sel", "bat_ctrl", "fastball_grade", "command_grade"],
        "shelf": "ark",
        "origin": "Arkmetric, original to eephus.io, measured on FanGraphs, MLB Pipeline and Baseball America tool grades.",
    }]
    see = {"eHIT": "hit_tool", "ePOW": "game_power", "eSEL": "pitch_sel", "eBAT": "bat_ctrl",
           "eFB": "fastball_grade", "eCMD": "command_grade"}
    for k in keys:
        t = tools[k]
        gid, name, outcome, card = ETOOLS[k]
        m, u = t["labels"]["mlb"], t["labels"]["um"]
        text = (f"The consensus {t['name'].lower()} grade moved by {_subs(t)}. Against {outcome}, the "
                f"consensus grade ranked prospects at a rank correlation of {_r(m['rho_consensus'])} and {name} at "
                f"{_r(m['rho_etool'])}, among players who debuted; on the translated upper-minors line, "
                f"{_r(u['rho_consensus'])} and {_r(u['rho_etool'])}.")
        if k == "eHIT":
            text += " It measures strikeout avoidance, not batting average."
        out.append({
            "id": gid,
            "term": name,
            "category": "custom-index",
            "section": "Prospects",
            "module": ["prospx"],
            "aliases": [f"{t['name']} eTool"],
            "priority": 38,
            "definition": (f"The {t['name'].lower()} tool grade sharpened by the prospect's own minor-league "
                           f"stats ({_subs(t)}). The {card} grade the site shows, marked e and rounded to the "
                           f"nearest whole grade, with the consensus grade beside it and an 80% band."),
            "methodology": text + " The Library's eTools view has the test and the checks.",
            "seeAlso": ["etools", see[k]],
            "shelf": "ark",
            "origin": "Arkmetric, original to eephus.io.",
        })
    return out


def _render(doc, raw: bytes, ensure_ascii: bool) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=ensure_ascii)
    crlf = b"\r\n" in raw
    if crlf:
        text = text.replace("\n", "\r\n")
    if raw.endswith(b"\n"):
        text += "\r\n" if crlf else "\n"
    return text.encode("utf-8")


def _load(path: Path):
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    for ea in (False, True):
        if _render(doc, raw, ea) == raw:
            return doc, raw, ea
    raise SystemExit(f"refusing: a plain round trip would rewrite {path.name}")


def registry(rows: list[dict]) -> str:
    doc, raw, ea = _load(REG)
    models = doc["models"]
    by_id = {r["model_id"]: r for r in models}
    anchor = by_id.get("tool_tables_rederived")
    at = (models.index(anchor) + 1) if anchor is not None else len(models)
    for row in rows:
        cur = by_id.get(row["model_id"])
        if cur is not None:
            models[models.index(cur)] = dict(row)
        else:
            models.insert(at, dict(row))
            at += 1
    out = _render(doc, raw, ea)
    if out == raw:
        return "registry unchanged"
    REG.write_bytes(out)
    return "registry written"


def glossary(entries: list[dict]) -> str:
    doc, raw, ea = _load(GLO)
    ents = doc["entries"]
    by_id = {e["id"]: e for e in ents}
    anchor = by_id.get("hit_tool")
    at = (ents.index(anchor) + 1) if anchor is not None else len(ents)
    for entry in entries:
        cur = by_id.get(entry["id"])
        if cur is not None:
            ents[ents.index(cur)] = dict(entry)
        else:
            ents.insert(at, dict(entry))
            at += 1
    out = _render(doc, raw, ea)
    if out == raw:
        return "glossary unchanged"
    GLO.write_bytes(out)
    return "glossary written"


def main() -> int:
    tools, doc = _summary()
    rows = [registry_row(tools[k], doc) for k in ETOOLS if (tools.get(k) or {}).get("verdict") == "PASS"]
    entries = glossary_entries(tools, doc)
    for t in rows + entries:
        blob = json.dumps(t, ensure_ascii=False)
        if chr(0x2014) in blob or chr(0x2013) in blob:
            raise SystemExit("refusing: a dash in the registration text")
    print(registry(rows))
    print(glossary(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
