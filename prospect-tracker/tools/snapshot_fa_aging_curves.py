"""Regenerate data/fa_aging_curves.json, the DOCUMENTATION SNAPSHOT of the
incumbent v2 aging curves, from the corpus cache (read-only).

Nothing reads this file at run time (the only reference in the tree is the
writer, fa_projection.CURVES_PATH); the served curves are refit live through
fa_projection.fitted_models from the corpus-keyed cache. The snapshot exists so
a reader can inspect the curves without a corpus. Its meta says so.

    python tools/snapshot_fa_aging_curves.py
"""
from __future__ import annotations

import datetime as _dt
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_projection as fp  # noqa: E402

NOTE = ("documentation snapshot, not read at run time: the served curves are refit live "
        "from the corpus-keyed cache by fa_projection.fitted_models; see docs/AGING_V3_GATE.md "
        "(registry rows fa_aging_curves and aging_v3)")


def main() -> int:
    with open(fp.CORPUS_CACHE, "rb") as fh:
        corpus = pickle.load(fh)
    curves = fp.fit_aging_curves(corpus, max_season=None, write=False)
    curves["meta"].update({
        "provider": corpus.get("war_provider"),
        "corpus_sig": fp._corpus_sig(corpus),
        "generated_at": _dt.date.today().isoformat(),
        "note": NOTE,
    })
    path = fp.CURVES_PATH
    crlf = path.exists() and b"\r\n" in path.read_bytes()
    text = json.dumps(curves, indent=1)
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    n = sum(len(c) for side in ("hit", "pit") for comps in curves[side].values() for c in comps.values())
    print(f"wrote {path.name}: provider {curves['meta']['provider']}, corpus {curves['meta']['corpus_seasons']}, "
          f"{n} age cells, lambda {curves['meta']['lambda']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
