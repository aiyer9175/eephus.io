# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR history's registry row (docs/ewar/EWAR_HISTORY_GATE.md part 6; task
EWAR_BACKGRADE_HISTORY): `ewar_history`, provisional, measurement_only, with
data/ewar_history.json as its eval artifact. The glossary entry `ewar` carries the
season stamps through tools/register_ewar_v3.py, which owns that entry.

Idempotent: a second run changes nothing. Keeps the file's line endings and
one-space indent; refuses when a plain round trip would rewrite it. Reads
data/ewar_history.json (build it first: python tools/build_ewar_history.py --write).
Then python tools/gen_audit_docs.py.
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

ARTIFACT = ROOT / "data" / "ewar_history.json"


def _span(g: dict) -> str:
    return str(g["first"]) if g["first"] == g["last"] else f"{g['first']} to {g['last']}"


def row(art: dict) -> dict:
    groups = art.get("groups") or []
    seasons = art.get("seasons") or {}
    gaps = []
    for part, side, lab in (("framing", "bat", "catcher framing"), ("bsr_rest", "bat", "the rest of baserunning"),
                            ("r2", "pit", "realized pitching")):
        vals = [(s, (blk.get("gap") or {}).get(side, {}).get(part)) for s, blk in seasons.items()]
        vals = [(s, g) for s, g in vals if g]
        if vals:
            sds = [g["sd"] for _s, g in vals]
            rho = [g["spearman_core_full"] for _s, g in vals if g.get("spearman_core_full") is not None]
            gaps.append(f"{lab} {vals[0][0]} to {vals[-1][0]}: sd {min(sds):.2f} to {max(sds):.2f} wins"
                        + (f", Spearman CORE vs FULL {min(rho):.3f} to {max(rho):.3f}" if rho else ""))
    return {
        "model_id": "ewar_history",
        "summary": (f"Measured, not a prediction: the displayed eWAR shown for every season "
                    f"{art.get('first_season')} to {art.get('last_season')}, each season stamped with the parts "
                    "its eWAR carries."),
        "surface": ("/mlbstats/ eWAR board year selector and windows (data/war_seasons.json components), MLB "
                    "player pages' season lines (careerHist, ewarParts in the per-card shard), the league averages' "
                    "eWAR rows; data/ewar_history.json"),
        "predicts": "Nothing forward: which parts each season's eWAR carries, and how far the later parts move it",
        "champion": (f"{art.get('version')} (ewar_history.py, tools/build_ewar_history.py): stamps measured on the "
                     f"frozen fWAR vintage {art.get('fwar_vintage_id')} and data/ewar_v3.json; groups "
                     + "; ".join(_span(g) for g in groups)),
        "baseline": "CORE: eWAR from the parts present in every season (batting, wSB, fielding, positional, "
                    "league and replacement, pitching), re-centred per PA at FanGraphs' own per-season RPW",
        "metric": ("Refusing identities, no forward claim: FULL minus CORE equals the named parts per row; CORE "
                   "and FULL side totals equal fWAR's; a season with no later part has CORE equal to FULL. The "
                   "per-part gap is reported, never scored"),
        "eval_artifact": "data/ewar_history.json",
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "notes": (f"Built by tools/build_ewar_history.py (task EWAR_BACKGRADE_HISTORY, owner EW3-17) on fWAR vintage "
                  f"{art.get('fwar_vintage_id')} and the eWAR artifact built {art.get('ewar_v3_generated_at')}; "
                  "registered in docs/ewar/EWAR_HISTORY_GATE.md (committed alone before any number; amendments 9.1 "
                  "and 9.2 fix two identity definitions before any gap number). It admits no part and moves no "
                  "served eWAR number of 2011 to 2026: it adds seasons 2000 to 2010 to the displayed eWAR's "
                  "history and stamps every season. " + art.get("why_it_stops", "") + " Gap per part (descriptive, "
                  "deciding nothing): " + "; ".join(gaps) + ". CORE is recorded as per-season summaries only and "
                  "never displayed."),
    }


def main() -> int:
    if not ARTIFACT.exists():
        print("refusing: data/ewar_history.json is not built (python tools/build_ewar_history.py --write first)")
        return 2
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    raw = REGISTRY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if _render(raw, doc) != raw:
        print("refusing: a plain round trip would rewrite model_registry.json")
        return 2
    changed = _upsert(doc["models"], "model_id", row(art), after="ewar_v3_realized")
    if changed:
        REGISTRY.write_bytes(_render(raw, doc))
        print("model_registry.json: wrote ewar_history")
    else:
        print("model_registry.json: nothing to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
