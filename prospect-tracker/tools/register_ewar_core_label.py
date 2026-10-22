# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The core eWAR label's registry row (docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md
part 3): `ewar_core_label`, provisional, measurement_only, with the circularity guard's
record as its eval artifact. It claims no accuracy and names the guard's verdict.

Idempotent: a second run changes nothing. Keeps the file's line endings and one-space
indent; refuses when a plain round trip would rewrite it. Then python tools/gen_audit_docs.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from register_ewar_v3 import REGISTRY, _render, _upsert   # noqa: E402

GUARD = ROOT / "docs" / "efv-2026-10-22" / "ewar_core_label_guard.json"
GUARD_REL = "docs/efv-2026-10-22/ewar_core_label_guard.json"


def row(rec: dict) -> dict:
    g1, g2, v = rec["g1"], rec["g2"], rec["verdict"]
    outs = "; ".join(f"{k} dT {o['dT']:+.4f}" for k, o in g2["outcomes"].items())
    return {
        "model_id": "ewar_core_label",
        "summary": ("Measured, not a prediction: core eWAR (fWAR less the rest of baserunning and "
                    "framing), a candidate eFV label whose circularity guard did not hold."),
        "surface": "None served: data/ewar_core_label.json (off the webroot) and war_source provider ewar_core, "
                   "behind LABEL_EWAR_CORE = False",
        "predicts": "Nothing: a label definition, checked against next-season published fWAR and club runs and wins",
        "champion": (f"{rec['label']['vintage_id']} (ewar_core_label.py, tools/build_ewar_core_label.py) on the "
                     f"frozen fWAR vintage {rec['label']['fwar_vintage_id']}"),
        "baseline": "published fWAR (the label in force)",
        "metric": ("Circularity guard (gate part 4): G-1 within-season Spearman gap against next-season fWAR, "
                   "NON-INFERIOR when the 5th percentile is above -0.02; G-2 the eBR gate's team guard 11.2.4"),
        "eval_artifact": GUARD_REL,
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "notes": (f"Guard read once on 2026-10-22 (task EFV_LABEL_EPOCH_EWAR, owner EW3-17 and EW3-20): "
                  f"G-1 gap {g1['gap']:+.4f} (5th percentile {g1['lower']:+.4f}, n {g1['n_pairs']} pairs), "
                  f"not non-inferior; permuted twin gap {g1['twin']['gap']:+.4f}; G-2 {outs}; "
                  f"guard holds: {v['guard_holds']}. The label stays published fWAR. Owner question EWLE-Q2 "
                  "was answered (b), the headline eWAR after its own check (task EFV_LABEL_HEADLINE_EWAR_CHECK, "
                  "row ewar_headline_label), so the core label epoch is closed without a flip and "
                  "LABEL_EWAR_CORE stays False. No accuracy claim is made for any label."),
    }


def main() -> int:
    if not GUARD.exists():
        print(f"refusing: {GUARD_REL} is absent (the guard look writes it)")
        return 2
    rec = json.loads(GUARD.read_text(encoding="utf-8"))
    raw = REGISTRY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if _render(raw, doc) != raw:
        print("refusing: a plain round trip would rewrite model_registry.json")
        return 2
    changed = _upsert(doc["models"], "model_id", row(rec), after="ewar_history")
    if changed:
        REGISTRY.write_bytes(_render(raw, doc))
        print("model_registry.json: wrote ewar_core_label")
    else:
        print("model_registry.json: nothing to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
