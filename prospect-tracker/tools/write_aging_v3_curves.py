"""Write data/aging_v3_curves.json, the accepted composition of the aging v3
ladder fitted on the full fWAR corpus, and record that composition's level()
peak ages and slopes in data/aging_v3_eval.json (task AG_7_AGING_V3_LOOK;
docs/AGING_V3_GATE.md sections 7 and 16).

Reads the look artifact (final_composition, final_cfg8) and the DEV
selections (never re-selected), fits aging_v3.fit on .cache/fa_corpus.pkl
read-only with the cached sidecar (use_cache=False: no .cache fit file is
read or written), and writes the model's to_dict() with its meta carrying
fetched_at, corpus_sig, the composition and the look artifact's sha256. The
file is served by no page and read by no consumer until AG_8 flips
proj_display (every fa_config.yaml aging_v3.consumers flag is false).

The eval artifact gains one block, "accepted_level": per cell the peak age and
mean annual slopes of level() before and after the peak, with n and the
shrinkage weight per cell, from two fits of the accepted composition: through
the last GATE base season (the fit the look's last base walked) and on the full
corpus (the served fit). Neither reads a label: level() is a property of the
fit, so no GATE, TIER-2 or CONFIRM number moves. With no accepted composition
nothing is written and the block records why.

    python tools/write_aging_v3_curves.py
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import aging_v3 as A              # noqa: E402
import aging_v3_lab as L          # noqa: E402
import fa_projection as fp        # noqa: E402

CURVES = A.SERVED_CURVES_PATH


def _dump(doc: dict) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    if not L.EVAL_PATH.exists():
        raise SystemExit(f"{L.EVAL_PATH} is absent: the look has not been written")
    look = json.loads(L.EVAL_PATH.read_text(encoding="utf-8"))
    mde = json.loads(L.MDE_PATH.read_text(encoding="utf-8"))
    if look.get("task") != "AG_7_AGING_V3_LOOK" or look.get("protocol_hash") != L.PROTOCOL_HASH:
        raise SystemExit("data/aging_v3_eval.json is not the AG_7 look artifact under this protocol")
    final = list(look.get("final_composition") or [])
    sel = mde["selected"]
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not final:
        print("no accepted composition (no arm survived the ladder and the vetoes): data/aging_v3_curves.json "
              "is not written, no cell's level() is reported, and the eval artifact is left as the look wrote it")
        return 0
    cfg = L.composition_cfg(final, sel)
    if A.config_hash(cfg) != look["final_cfg8"]:
        raise SystemExit(f"the composition's cfg8 {A.config_hash(cfg)} != the artifact's {look['final_cfg8']}")
    corpus, sidecar = L.load_real()
    if fp._corpus_sig(corpus) != look["corpus"]["sig"]:
        raise SystemExit("the corpus on disk is not the one the look read")
    last_gate_base = max(look["frames"]["GATE"]["bases"])
    model_gate = A.fitted(corpus, last_gate_base - 1, cfg, sidecar=sidecar, use_cache=False)
    model_full = A.fitted(corpus, None, cfg, sidecar=sidecar, use_cache=False)
    look["accepted_level"] = {
        "generated_at": now, "composition": final, "cfg8": look["final_cfg8"],
        "note": "peak age and mean annual slopes of level() before and after the peak per cell, with n and "
                "the shrinkage weight per age; from the fit, no label read",
        "gate_fit": {"fit_through_season": last_gate_base - 1, "level": L.level_summary(model_gate),
                     "cells": L.cell_counts(model_gate)},
        "full_fit": {"fit_through_season": corpus.get("last"), "level": L.level_summary(model_full),
                     "cells": L.cell_counts(model_full)},
    }
    L.EVAL_PATH.write_text(_dump(look), encoding="utf-8")
    eval_sha = hashlib.sha256(L.EVAL_PATH.read_bytes()).hexdigest()
    doc = model_full.to_dict()
    doc["meta"] = dict(doc["meta"], **{
        "fetched_at": now, "generated_at": now, "task": "AG_7_AGING_V3_LOOK",
        "gate": "docs/AGING_V3_GATE.md sections 7, 9 and 16",
        "composition": final, "eval_artifact": "data/aging_v3_eval.json", "eval_artifact_sha256": eval_sha,
        "selected": sel,
        "served": "no page and no consumer reads this file until AG_8 flips fa_config.yaml "
                  "aging_v3.consumers.proj_display; every consumer door selects aging=\"v2\" until then",
    })
    doc["generated_at"] = now
    CURVES.write_text(_dump(doc), encoding="utf-8")
    back = A.AgingModel.from_dict(json.loads(CURVES.read_text(encoding="utf-8")))
    assert back.meta["cfg8"] == look["final_cfg8"] and back.cfg["arms"] == cfg["arms"]
    for side in A.SIDES:
        assert back.cells[side].keys() == model_full.cells[side].keys()
    n_cells = sum(len(c) for side in A.SIDES for comps in model_full.cells[side].values() for c in comps.values())
    print(f"written {CURVES.name}: composition {'+'.join(final)} cfg8 {look['final_cfg8']} version "
          f"{model_full.meta['version']} corpus {model_full.meta['corpus_sig']} {model_full.meta['corpus_seasons']} "
          f"{n_cells} age cells, {CURVES.stat().st_size:,} bytes; eval artifact gains accepted_level")
    return 0


if __name__ == "__main__":
    sys.exit(main())
