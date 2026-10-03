# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Take the FV-tier freeze once (lane D E3-Q3 = A, 2026-10-02; EFV3_D2).

Writes data/efv_fv_tier_frozen.json from the three artifacts as they stand on disk:

    source_backtest        data/source_backtest.json       cohorts[rater].tiers
    efv_scoreboard         data/xfv_scoreboard_eval.json   sides[side].by_fv_tier / t45 / wm
    source_cohort_accuracy data/source_cohort_accuracy.json accuracy.by_fv_tier and its
                                                            range-restriction warning

Each block is copied verbatim with the artifact's generated_at and sha256 beside it,
and for the two tracked artifacts the bytes are checked against git HEAD so the
frozen values are the COMMITTED ones. The producers then serve these blocks, with the
chip source_backtest.FV_TIER_FREEZE_CHIP, until the anchor look record exists
(docs/PROSPECT_ANCHOR_GATE.md section 18) or the owner flips
source_backtest.FV_TIER_FREEZE.

Idempotent: an existing frozen file is left alone (exit 0) unless --refresh is passed,
which is an owner action, never a nightly one. Nothing here reads a grade against an
outcome: the script copies blocks that already exist.

Run once:  python tools/efv_fv_tier_freeze.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import source_backtest as SB  # noqa: E402

OUT_PATH = SB.FV_TIER_FROZEN_PATH
SOURCES = {
    "source_backtest": "data/source_backtest.json",
    "efv_scoreboard": "data/xfv_scoreboard_eval.json",
    "source_cohort_accuracy": "data/source_cohort_accuracy.json",
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _head_bytes(rel: str) -> bytes | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:./{rel}"],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _load(rel: str) -> tuple[dict, dict]:
    p = ROOT / rel
    raw = p.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    head = _head_bytes(rel)
    # git stores LF; the working tree is CRLF, so compare normalized text.
    same_as_head = (head is not None
                    and head.replace(b"\r\n", b"\n") == raw.replace(b"\r\n", b"\n"))
    return doc, {"path": rel, "generated_at": doc.get("generated_at"),
                 "sha256": _sha(raw), "tracked": head is not None,
                 "equals_git_head": bool(same_as_head)}


def build() -> dict:
    sb, sb_src = _load(SOURCES["source_backtest"])
    sc, sc_src = _load(SOURCES["efv_scoreboard"])
    ca, ca_src = _load(SOURCES["source_cohort_accuracy"])
    frozen = {
        "frozen_on": date.today().isoformat(),
        "decision": ("lane D E3-Q3 = A, recorded 2026-10-02 under the owner's standing "
                     "instruction (docs/efv-v2/EFV_V2_GATE.md s8.3; EFV3_PLAN.md s9)"),
        "chip": SB.FV_TIER_FREEZE_CHIP,
        "rule": ("the three producers serve these blocks verbatim, with the chip, until "
                 "the look record in docs/PROSPECT_ANCHOR_GATE.md section 18 exists; "
                 "the rest of each artifact regenerates as before"),
        "owner_line": "source_backtest.FV_TIER_FREEZE = False resumes the nightly recompute",
        "written_by": "tools/efv_fv_tier_freeze.py (once; --refresh is an owner action)",
        "sources": {"source_backtest": sb_src, "efv_scoreboard": sc_src,
                    "source_cohort_accuracy": ca_src},
        "source_backtest": {r: (v or {}).get("tiers") or []
                            for r, v in (sb.get("cohorts") or {}).items()},
        "efv_scoreboard": {s: {"by_fv_tier": (b or {}).get("by_fv_tier") or {},
                               "t45": (b or {}).get("t45"),
                               "wm": (b or {}).get("wm")}
                           for s, b in (sc.get("sides") or {}).items()},
        "source_cohort_accuracy": {
            "by_fv_tier": (ca.get("accuracy") or {}).get("by_fv_tier") or {},
            "by_fv_tier_range_restriction_warning":
                (ca.get("accuracy") or {}).get("by_fv_tier_range_restriction_warning")},
    }
    return frozen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--refresh", action="store_true",
                    help="overwrite an existing frozen file (owner action)")
    a = ap.parse_args(argv)
    if OUT_PATH.exists() and not a.refresh:
        print(f"frozen file exists, left alone: {OUT_PATH}")
        return 0
    doc = build()
    OUT_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    for k, v in doc["sources"].items():
        print(f"  {k}: {v['path']} generated_at {v['generated_at']} tracked {v['tracked']} "
              f"equals_git_head {v['equals_git_head']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
