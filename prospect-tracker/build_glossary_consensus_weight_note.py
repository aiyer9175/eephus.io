# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time glossary extend (2026-07-07, WS-C): finish the Consensus FV
methodology's accuracy-weighting paragraph.

Three surgical edits to the existing consensus_fv entry in data/glossary.json:
  1. sharpen the vintage rule to the actual forward-chained cutoff (a board
     year uses only track-record seasons at least three years old, no lookahead),
  2. refresh the live weights to the shipped values (MLB Pipeline 1.07,
     FanGraphs 0.93 from data/source_weights.json),
  3. state that the amateur draft board stays equal-weight because its own
     source backtest did not clear the ship gate.

Idempotent: guarded on the draft-board clause, so a re-run only re-stamps the
version. Kept for provenance like its siblings (build_glossary_data.py,
build_glossary_gmli_add.py, build_glossary_v2_update.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from build_glossary_data import glossary_version

PATH = Path(__file__).parent / "data" / "glossary.json"

# (old, new) methodology replacements. Each old string must appear verbatim
# in the current consensus_fv methodology or the edit aborts loudly.
EDITS = [
    (
        "vintage-disciplined: a board year only uses track records resolvable before it",
        "vintage-disciplined: a board year uses only track-record seasons at "
        "least three years old, so nothing the weights read is newer than the "
        "board itself",
    ),
    (
        "Current weights: MLB Pipeline 1.06, FanGraphs 0.94",
        "Current weights: MLB Pipeline 1.07, FanGraphs 0.93",
    ),
    (
        "disagreement metrics stay unweighted. Cross-source normalization",
        "disagreement metrics stay unweighted. The amateur draft board stays "
        "equal-weight: its own source backtest did not clear the ship gate, so "
        "no draft source outvotes another there. Cross-source normalization",
    ),
]

GUARD = "amateur draft board stays"


def main() -> None:
    d = json.loads(PATH.read_text(encoding="utf-8"))
    entry = next((e for e in d["entries"] if e["id"] == "consensus_fv"), None)
    if entry is None:
        raise SystemExit("consensus_fv entry missing - nothing to extend")
    meth = entry.get("methodology", "")
    if GUARD in meth:
        print("consensus_fv already carries the draft-board clause - no-op")
    else:
        for old, new in EDITS:
            if old not in meth:
                raise SystemExit(f"anchor not found, aborting: {old[:60]!r}")
            meth = meth.replace(old, new)
        entry["methodology"] = meth
        print("extended consensus_fv methodology (vintage cutoff + live weights "
              "+ draft-board equal-weight)")
    d["version"] = glossary_version()
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {PATH.name} - version {d['version']}")


if __name__ == "__main__":
    main()
