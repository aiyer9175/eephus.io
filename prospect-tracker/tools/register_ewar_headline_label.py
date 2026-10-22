# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The headline eWAR label's registry row (docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md
part 3): `ewar_headline_label`, provisional, measurement_only, with the circularity guard's
record as its eval artifact. It claims no accuracy, names the guard's verdict and says the
pass was an identity reading that cannot see the eABS part. The notes follow
war_source.EFV_LABEL_EWAR_HEADLINE, so the flag commit re-runs this script.

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

GUARD = ROOT / "docs" / "efv-2026-10-22" / "ewar_headline_label_guard.json"
GUARD_REL = "docs/efv-2026-10-22/ewar_headline_label_guard.json"


def row(rec: dict, switch_on: bool) -> dict:
    g1, g2, v = rec["g1"], rec["g2"], rec["verdict"]
    outs = "; ".join(f"{k} dT {o['dT']:+.4f}" for k, o in g2["outcomes"].items())
    state = ("eFV's label is this series (war_source.EFV_LABEL_EWAR_HEADLINE = True, owner default "
             "EWHL-Q1 (a)); DEFAULT_PROVIDER and every other label reader stay published fWAR"
             if switch_on else
             "The switch is cleared and not yet flipped (war_source.EFV_LABEL_EWAR_HEADLINE = False)")
    return {
        "model_id": "ewar_headline_label",
        "summary": ("Measured, not a prediction: the headline eWAR (published fWAR plus the eABS part from "
                    "2026) as eFV's training label, frozen as its own vintage."),
        "surface": ("None served directly: data/ewar_headline_label.json (off the webroot), read by eFV's "
                    "label through war_source.efv_label_seasons under EFV_LABEL_EWAR_HEADLINE"),
        "predicts": "Nothing: a label definition, checked against next-season published fWAR and club runs and wins",
        "champion": (f"{rec['label']['vintage_id']} (ewar_headline_label.py, tools/build_ewar_headline_label.py) "
                     f"on the frozen fWAR vintage {rec['label']['fwar_vintage_id']}"),
        "baseline": "published fWAR (the label before the switch)",
        "metric": ("Circularity guard (the core label gate's part 4 on this series): G-1 within-season Spearman "
                   "gap against next-season fWAR, NON-INFERIOR when the 5th percentile is above -0.02; G-2 the "
                   "eBR gate's team guard 11.2.4 with the label on both sides"),
        "eval_artifact": GUARD_REL,
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "notes": (f"Guard read once on 2026-10-22 (task EFV_LABEL_HEADLINE_EWAR_CHECK, owner answer EWLE-Q2): "
                  f"G-1 gap {g1['gap']:+.4f} (5th percentile {g1['lower']:+.4f}, n {g1['n_pairs']} pairs, "
                  f"{g1['n_pairs_departing']} departing); permuted twin gap {g1['twin']['gap']:+.4f}; G-2 {outs}; "
                  f"guard holds: {v['guard_holds']}, by identity: the label carries no departure before 2026, "
                  "so the guard cannot see the eABS part (gate part 4.5); its own read EWHL-R1 needs the 2027 "
                  f"season's data. {state}. No accuracy claim is made for any label."),
    }


def main() -> int:
    if not GUARD.exists():
        print(f"refusing: {GUARD_REL} is absent (the guard look writes it)")
        return 2
    import war_source
    rec = json.loads(GUARD.read_text(encoding="utf-8"))
    raw = REGISTRY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if _render(raw, doc) != raw:
        print("refusing: a plain round trip would rewrite model_registry.json")
        return 2
    changed = _upsert(doc["models"], "model_id", row(rec, bool(war_source.EFV_LABEL_EWAR_HEADLINE)),
                      after="ewar_core_label")
    if changed:
        REGISTRY.write_bytes(_render(raw, doc))
        print("model_registry.json: wrote ewar_headline_label")
    else:
        print("model_registry.json: nothing to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
