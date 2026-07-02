# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time glossary add (2026-07-02): the gmLI 3yr deployment-context entry.

Ships with the X-D1 leverage-consistency wiring (holistic pass 3): the
/mlbstats/ Bullpen Leaderboards gain a "gmLI 3yr" column joined from
data/leverage_consistency_eval.json, and every displayed metric needs a
glossary entry per the standing methodology rule.

Idempotent: the insert is guarded on the slug, so a re-run is a no-op apart
from the version stamp. Kept for provenance like its siblings
(build_glossary_data.py, build_glossary_v2_update.py,
build_glossary_copy_pass.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from build_glossary_data import glossary_version

PATH = Path(__file__).parent / "data" / "glossary.json"

ENTRY = {
    "id": "gmli_3yr",
    "term": "gmLI 3yr (three-year deployment leverage)",
    "category": "custom-index",
    "module": ["mlbstats"],
    "aliases": ["gmLI 3yr", "leverage consistency", "three-year gmLI"],
    "priority": 21,
    "definition": (
        "The relief-entry-weighted average gmLI a pitcher's managers assigned "
        "him over the trailing three seasons, shown with his pool percentile. "
        "Deployment context, not skill: it says how he has been used, not how "
        "well he pitched. About 1.0 is average; established high-leverage arms "
        "run 1.5 and up."
    ),
    "methodology": (
        "Each season's gmLI (entry-point Leverage Index, computed in house "
        "from the MLB win-probability feed) is averaged across the trailing "
        "three seasons, weighted by relief entries. The multi-year framing is "
        "gate-validated: year-over-year gmLI rank correlation on qualified "
        "relievers is 0.47 pooled over 2018-2025 (excluding 2020), with "
        "within-season split-half stability of 0.53, so a manager's leverage "
        "assignment is a persistent trait worth displaying.\n\n"
        "Players with fewer than 2 seasons or 60 relief entries in the window "
        "carry a provisional mark. gmLI 3yr never feeds REM+, which "
        "deliberately excludes leverage from the skill scale."
    ),
    "seeAlso": ["gmli", "leverage_index", "rem_plus"],
}


def main() -> None:
    d = json.loads(PATH.read_text(encoding="utf-8"))
    entries = d["entries"]
    if not any(e["id"] == ENTRY["id"] for e in entries):
        # Insert right after the gmli entry so the pair reads together.
        idx = next((i for i, e in enumerate(entries) if e["id"] == "gmli"),
                   len(entries) - 1)
        entries.insert(idx + 1, dict(ENTRY))
        print(f"inserted {ENTRY['id']} after gmli")
    else:
        print(f"{ENTRY['id']} already present - no-op")
    d["version"] = glossary_version()
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"wrote {PATH.name} - {len(entries)} entries, version {d['version']}")


if __name__ == "__main__":
    main()
