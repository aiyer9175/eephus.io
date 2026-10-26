# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PORT_RED_TESTS_CLEAR (2026-10-26): three served sentences the copy gate
(test_copy_gates.py, docs/COPY_STYLE.md rules L1 and L8) found new since its baseline.

  * glossary `war` definition: one 66-word sentence (L1) splits in two at the point
    where it starts describing fWAR; no word changes.
  * registry `xm` predicts: one 70-word sentence (L1) splits in three, and the docs
    path it carried (L8) leaves the served text (the row's eval_artifact and gate
    fields keep the provenance).
  * registry `xm` metric: the docs path and the eight-digit seed (L8) leave the served
    text; the seed stays in the eval artifact.

Edits the raw JSON text in place (line endings, indent and key order untouched) and is
idempotent: a second run finds the new text and writes nothing.

    python tools/port_copy_gate_fixes.py          # apply
    python tools/port_copy_gate_fixes.py --check  # exit 1 if any edit is still due
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EDITS = {
    "data/glossary.json": [
        ("the arbitration model is published fWAR, frozen per season from the 2026-10 epoch: "
         "FanGraphs' WAR adopted wholesale, with its 57/43",
         "the arbitration model is published fWAR, frozen per season from the 2026-10 epoch. "
         "That is FanGraphs' WAR adopted wholesale, with its 57/43"),
    ],
    "data/model_registry.json": [
        ("with a P10-P90 band, for signed MLB free agents; pre-arbitration and arbitration rows "
         "are priced as if free agents this winter (counterfactual, no accuracy claim); prospect "
         "rows carry no xM$, withheld as outside the market model's range, and show Fair $ only, "
         "the NPV of the eFV WAR path at the market $/WAR (docs/xm/XM_GATE.md section 16)",
         "with a P10-P90 band, for signed MLB free agents. Pre-arbitration and arbitration rows "
         "are priced as if free agents this winter (counterfactual, no accuracy claim). Prospect "
         "rows carry no xM$, withheld as outside the market model's range, and show Fair $ only, "
         "the NPV of the eFV WAR path at the market $/WAR"),
        ("player-clustered bootstrap (B 4000, seed 20261019), one-sided 95 percent lower bound "
         "above 0; holdout winters 2025 and 2026 read once (docs/xm/XM_GATE.md section 9)",
         "player-clustered bootstrap (B 4000, fixed seed), one-sided 95 percent lower bound "
         "above 0; holdout winters 2025 and 2026 read once"),
    ],
}


def _enc(s: str) -> str:
    """The text as it appears inside a JSON string literal (ensure_ascii=False)."""
    return json.dumps(s, ensure_ascii=False)[1:-1]


def run(check: bool = False) -> int:
    due = 0
    for rel, pairs in EDITS.items():
        p = ROOT / rel
        raw = p.read_bytes().decode("utf-8")
        out = raw
        for old, new in pairs:
            o, n = _enc(old), _enc(new)
            if n in out and o not in out:
                continue
            if out.count(o) != 1:
                raise SystemExit(f"{rel}: expected one occurrence of {old[:60]!r}, found {out.count(o)}")
            due += 1
            out = out.replace(o, n)
        if out != raw and not check:
            json.loads(out)
            p.write_bytes(out.encode("utf-8"))
            print(f"{rel}: written")
        else:
            print(f"{rel}: {'due' if out != raw else 'unchanged'}")
    return 1 if (check and due) else 0


if __name__ == "__main__":
    sys.exit(run(check="--check" in sys.argv[1:]))
