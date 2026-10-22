# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The glossary sentences that name eFV's training label, moved with the headline eWAR label
check's switch (docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md part 3 under amendment 9.2;
war_source.EFV_LABEL_EWAR_HEADLINE). Three passages: `war` definition and methodology, and the
graduates-and-busts line of `xfv` formula. Clause (l) of the fWAR label epoch binds every
sentence: a basis change, no accuracy claim.

Idempotent: each edit replaces an exact old passage with its new one, and a second run (the new
passage already present) writes nothing. Keeps the file's line endings and one-space indent;
refuses when a plain round trip would rewrite the file or when neither passage is found.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from register_ewar_v3 import GLOSSARY, _render   # noqa: E402

EDITS: tuple[tuple[str, str, str, str], ...] = (
    ("war", "definition",
     "The training label behind eFV, the projections, the FV-to-WAR anchors, the draft slot curve, star "
     "odds, WAG and the arbitration model is published fWAR, frozen per season from the 2026-10 epoch: "
     "FanGraphs' WAR adopted wholesale, with its 57/43 replacement split, its league pool and positional "
     "ladder, and Statcast fielding with catcher framing inside it.",
     "The training label behind the projections, the FV-to-WAR anchors, the draft slot curve, star odds, "
     "WAG and the arbitration model is published fWAR, frozen per season from the 2026-10 epoch: "
     "FanGraphs' WAR adopted wholesale, with its 57/43 replacement split, its league pool and positional "
     "ladder, and Statcast fielding with catcher framing inside it. eFV's own training label (first-six-"
     "season WAR) is, from 2026-10-22, the headline eWAR: that published fWAR plus the ABS part from 2026, "
     "so the two are the same in every season before 2026. It is a change of definition, and no accuracy "
     "gain is claimed from it."),
    ("war", "methodology",
     "Everything trained or anchored on WAR is measured on it: eFV's labels, the FV-to-WAR anchors, the "
     "projections, the draft slot curve, star odds, WAG's observed leg, farm WAR per season and the "
     "arbitration model's WAR spine.",
     "Everything trained or anchored on WAR is measured on it: eFV's development-read labels, the FV-to-WAR "
     "anchors, the projections, the draft slot curve, star odds, WAG's observed leg, farm WAR per season and "
     "the arbitration model's WAR spine. The one exception, from 2026-10-22, is eFV's first-six-season "
     "training label, which is the headline eWAR: published fWAR plus the ABS part from 2026, equal to fWAR "
     "in every earlier season. That move is an owner basis decision taken after a check that could only "
     "confirm the two agree wherever a next-season outcome exists; no accuracy gain is claimed from it."),
    ("xfv", "formula",
     "eFV grade = outcome_implied_fv( E[6yr WAR] ) on the training label (published fWAR from the 2026-10 "
     "epoch), the inverse of the pooled empirical outcome curve fit on resolved cohorts;",
     "eFV grade = outcome_implied_fv( E[6yr WAR] ) on eFV's training label (from 2026-10-22 the headline "
     "eWAR, published fWAR plus the ABS part from 2026; published fWAR from the 2026-10 epoch before it), "
     "the inverse of the pooled empirical outcome curve fit on resolved cohorts;"),
)


def apply(doc: dict) -> list[str]:
    """Apply EDITS in place; returns the (id, field) pairs changed. Raises on a passage that is
    neither old nor new (the glossary moved under this script)."""
    by_id = {e.get("id"): e for e in doc["entries"]}
    changed = []
    for eid, field, old, new in EDITS:
        e = by_id.get(eid)
        text = (e or {}).get(field)
        if not isinstance(text, str):
            raise RuntimeError(f"glossary entry {eid!r} has no {field!r}")
        if new in text:
            continue
        if text.count(old) != 1:
            raise RuntimeError(f"glossary {eid}.{field}: the old passage is not found exactly once")
        e[field] = text.replace(old, new)
        changed.append(f"{eid}.{field}")
    return changed


def main() -> int:
    raw = GLOSSARY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if _render(raw, doc) != raw:
        print("refusing: a plain round trip would rewrite glossary.json")
        return 2
    try:
        changed = apply(doc)
    except RuntimeError as e:
        print(f"refusing: {e}")
        return 2
    if changed:
        GLOSSARY.write_bytes(_render(raw, doc))
        print("glossary.json: " + ", ".join(changed))
    else:
        print("glossary.json: nothing to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
