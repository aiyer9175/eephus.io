"""Record the veteran playing-time cap's flip in data/model_registry.json (idempotent).

Task AG_4_CHAMPION_PT_CAP (owner answer AG-Q5 'Fix both now'): appends one dated
sentence to the notes of fa_aging_curves (the engine the cap clamps) and of
fa_war_paths_decay (the paths it moves, with the ML feature pin), and moves no
verdict, metric or claim. Keeps the file's line endings (CRLF) and its one-space
indent. Running it twice changes nothing.

    python tools/register_pt_cap_rows.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
MARK = "VETERAN PT CAP (2026-10-21"

FA_AGING_CURVES_NOTE = (
    " VETERAN PT CAP (2026-10-21, AG_4_CHAMPION_PT_CAP, owner answer AG-Q5 'Fix both now'): "
    "fa_projection.fit_aging_curves stores meta.pt_cap, the 99.5th percentile of single-season "
    "exposure by side and base role over corpus rows with season <= max_season (PA: C, H; BF: SP, RP; "
    "on the served fit C 652.0, H 725.0, SP 983.19, RP 531.47), the same cap as the aging v3 comparator "
    "(docs/AGING_V3_GATE.md section 4). With fa_config.yaml projection.pt_cap_enabled true the year-1 PT "
    "and every decay step are clamped at it (call-scoped pt_cap on fitted_models, project_player, "
    "contract_war_path and _decay_path; capped fits cache under a _ptcap1 suffix). A defect repair, not a "
    "refit: the curves are unchanged and no accuracy claim is made."
)

FA_WAR_PATHS_NOTE = (
    " VETERAN PT CAP (2026-10-21, AG_4_CHAMPION_PT_CAP): the champion decay path (warChamp, warChampTail, "
    "the h6+ chain) is clamped at the fitted PT cap; on the flip 7 of 1,400 served veterans' champion "
    "paths moved, warY1Champ and the displayed war and woba moved on none. proj_ml.build_features passes "
    "pt_cap=False and a capped contract_war_path hands the heads an uncapped champion, so the ML feature "
    "vector is byte-identical (train/serve parity with the shipped bundle)."
)


GLOSSARY = ROOT / "data" / "glossary.json"
GLOSSARY_ENTRY = {
    "id": "veteran_pt_cap",
    "term": "Veteran playing-time cap",
    "category": "methodology",
    "section": "Players & Stats",
    "module": ["projections", "fa", "ledger", "franchise"],
    "aliases": ["PT cap", "playing-time cap"],
    "priority": 44,
    "definition": "The ceiling on a veteran's projected playing time in any season: the 99.5th percentile of one season's plate appearances (hitters) or batters faced (pitchers) for his role. Without it, the aging curve added the league's average playing-time gain to a young regular every year, so a 22-year-old with 650 PA was walked past 800 PA by 26.",
    "methodology": "The projection engine fits the cap from the same corpus as its aging curves, by side and base role (catcher and other hitters; starters and relievers), over the seasons before the projected one; it is never tuned. The year-1 projection and every later season of the aging path are clamped at it. It touches only the WAR path behind team totals, contract tails and surplus; the displayed WAR and wOBA lines, the fantasy and hitter boards and the FA Fit's team baseline do not move with it.",
    "seeAlso": ["projected_playing_time"],
    "shelf": "ark",
    "origin": "Arkmetric, original to eephus.io (fa_projection.fit_pt_cap, task AG_4_CHAMPION_PT_CAP).",
}


def _glossary() -> bool:
    raw = GLOSSARY.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    ids = [e["id"] for e in doc["entries"]]
    if GLOSSARY_ENTRY["id"] in ids:
        return False
    # beside projected_playing_time, the entry it qualifies
    at = ids.index("projected_playing_time") + 1 if "projected_playing_time" in ids else len(ids)
    doc["entries"].insert(at, dict(GLOSSARY_ENTRY))
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if raw.endswith(b"\n"):
        text += "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    GLOSSARY.write_bytes(text.encode("utf-8"))
    return True


def main() -> int:
    if _glossary():
        print("glossary written: veteran_pt_cap")
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    by_id = {r["model_id"]: r for r in doc["models"]}
    changed = []
    for mid, note in (("fa_aging_curves", FA_AGING_CURVES_NOTE),
                      ("fa_war_paths_decay", FA_WAR_PATHS_NOTE)):
        row = by_id.get(mid)
        if row is not None and MARK not in row["notes"]:
            row["notes"] = row["notes"].rstrip() + note
            changed.append(f"{mid} notes")
    if not changed:
        print("registry already carries the PT cap notes; nothing written")
        return 0
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if raw.endswith(b"\n"):
        text += "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))
    print("registry written:", ", ".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
