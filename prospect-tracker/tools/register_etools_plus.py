# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Register eTools+ (docs/tools-2026-10/ETOOLS_PLUS.md, owner decision EW3-28) in
data/model_registry.json (one provisional, descriptive row) and data/glossary.json (one
entry). Idempotent. Every figure is read from data/etools_plus.json (python etools_plus.py),
which carries the weights, the pools and the descriptive check's pooled numbers; nothing is
typed here. Each file keeps its own line endings, indent and ASCII setting. Then:

    python tools/register_etools_plus.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from register_etools import _load, _render, REG, GLO  # noqa: E402

SIDECAR = ROOT / "data" / "etools_plus.json"
ARTIFACT = "data/etools_plus.json"


def _pct(x) -> str:
    return f"{round(float(x) * 100)}%"


def _weights_text(doc: dict, side: str) -> str:
    keys, names = doc["keys"], doc["names"]
    w = doc["sides"][side]["weights"]
    return ", ".join(f"{keys.get(t) or names.get(t, t)} {_pct(x)}" for t, x in w.items() if x > 0)


def _check_text(doc: dict) -> str:
    c = doc.get("check") or {}
    out = []
    for fid, label in (("lv_dev", "list years 2017 to 2019"), ("vm_dev", "debut classes 2017 to 2023")):
        f = (c.get("frames") or {}).get(fid) or {}
        for side, who in (("hit", "hitters"), ("pit", "pitchers")):
            e = (f.get(side) or {}).get("etools_plus")
            if not e:
                continue
            out.append(f"{label}, {who} (n {e['n']}): {e['vs_outcome']:.3f} with the eFV outcome label, "
                       f"{e['vs_consensus_fv']:.3f} with consensus FV")
    return "; ".join(out)


def registry_row(doc: dict) -> dict:
    hit, pit = doc["sides"]["hit"], doc["sides"]["pit"]
    return {
        "model_id": "etools_plus",
        "summary": ("Provisional, descriptive: the shown eTools weighted by eFV's re-weight tool weights "
                    f"(hitters {_weights_text(doc, 'hit')}; pitchers {_weights_text(doc, 'pit')}), "
                    "100 = side average, 10 per SD."),
        "surface": ("PROSPX: the eT+ chip on the list row's tool strip (tooltip: each tool's weight, grade and "
                    "push), the eTools+ board sort and the eTools+ line on the player page's Tools card; "
                    "shown while the eTools are the shown grades"),
        "predicts": "nothing; a descriptive 100-centred summary of a prospect's shown eTools",
        "champion": ("etools_plus.py: S = the weighted mean of the available tool z scores (pool: the side's "
                     "players in data/etools.json with a weighted eTool), eTools+ = 100 + 10 x z(S), nearest; "
                     "weights from production.E.tool_weights of data/_labs/efv5/efv_etools_reweight_fit.json"),
        "baseline": "the same weights on the consensus tool grades (reported beside it, not compared)",
        "metric": ("descriptive check only (registered): within-(side, year) Spearman with the eFV outcome label "
                   "and with consensus FV on the development frames, no FV-level cut, no verdict"),
        "eval_artifact": ARTIFACT,
        "verdict": "provisional",
        "notes": (f"Owner decision EW3-28 (2026-10-15). Registered in docs/tools-2026-10/ETOOLS_PLUS.md before "
                  f"any value. Pools: {hit['pool_n']} hitters, {pit['pool_n']} pitchers. Hitter eTools+ is "
                  f"ePOW alone (eHIT was refused in the hit slot of the re-weight's head); tools at weight 0 "
                  f"are listed in the sidecar and the tooltip. Default D-1 (the re-weight read's owner "
                  f"question 2, default (a)); the owner may pick other weights. Descriptive check, read once: "
                  f"{_check_text(doc)}. No claim that it beats or predicts better than anything."),
        "registration_status": "registered in docs/tools-2026-10/ETOOLS_PLUS.md; descriptive check read once 2026-10-19",
        "last_checked": str(doc.get("generated_at") or "")[:10],
        "stale": False,
        "artifact_age_days": 0,
    }


def glossary_entry(doc: dict) -> dict:
    return {
        "id": "etools_plus",
        "term": "eTools+",
        "category": "custom-index",
        "section": "Prospects",
        "module": ["prospx"],
        "aliases": ["eT+", "eTools plus", "eTool plus"],
        "priority": 39,
        "definition": ("One tools number per prospect: his eTools weighted the way eFV's re-weight read weighted "
                       "them, on a plus scale where 100 is the average hitter or pitcher prospect with an eTool "
                       "and 10 points is one standard deviation."),
        "methodology": (
            "Each weighted eTool is put on a common scale (how many standard deviations it sits from the "
            "average prospect of his side), the scores are averaged with the weights, and the average is "
            "rescaled so the side's average is 100 and one standard deviation is 10, rounded to the nearest "
            "whole number. The weights are the tool weights of the eFV re-weight read (the fit with the "
            f"eTools in eFV's tool slots), scaled to sum to 1: hitters {_weights_text(doc, 'hit')}; "
            f"pitchers {_weights_text(doc, 'pit')}. The hit eTool did not keep one sign across years in that "
            "fit, so it carries no weight, and hitter eTools+ is game power alone. Tools with no eFV weight "
            "(pitch selection, bat control, raw power, speed, field, arm and the secondary pitches) "
            "contribute nothing. A prospect missing a weighted eTool takes the weighted mean of the ones he "
            "has, with the coverage shown. The card tooltip lists each tool's weight, grade and push in "
            "points.\n\n"
            "It is descriptive. On the development frames, read once: " + _check_text(doc) + ". It is a "
            "summary of the stat-moved tool grades, not a forecast, and no claim is made that it beats any "
            "other number."),
        "formula": "eTools+ = 100 + 10 x (S - mean S) / sd S, S = sum of w_t z_t over the available tools / sum of their w_t",
        "seeAlso": ["etools", "etool_composite", "epow", "efb", "ecmd"],
        "shelf": "ark",
        "origin": "Arkmetric, original to eephus.io.",
    }


def _upsert(path: Path, list_key: str, id_key: str, item: dict, after: str) -> str:
    doc, raw, ea = _load(path)
    items = doc[list_key]
    by_id = {x[id_key]: x for x in items}
    cur = by_id.get(item[id_key])
    if cur is not None:
        items[items.index(cur)] = dict(item)
    else:
        anchor = by_id.get(after)
        at = (items.index(anchor) + 1) if anchor is not None else len(items)
        items.insert(at, dict(item))
    out = _render(doc, raw, ea)
    if out == raw:
        return f"{path.name} unchanged"
    path.write_bytes(out)
    return f"{path.name} written"


def main() -> int:
    doc = json.loads(SIDECAR.read_text(encoding="utf-8"))
    if not doc.get("check"):
        raise SystemExit("refusing: the sidecar carries no descriptive check yet")
    row, entry = registry_row(doc), glossary_entry(doc)
    for t in (row, entry):
        blob = json.dumps(t, ensure_ascii=False)
        if chr(0x2014) in blob or chr(0x2013) in blob:
            raise SystemExit("refusing: a dash in the registration text")
    print(_upsert(REG, "models", "model_id", row, "etool_composite"))
    print(_upsert(GLO, "entries", "id", entry, "etool_composite"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
