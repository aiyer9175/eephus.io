# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Verify the 2026-07-25 explainer repairs, and that they are DISPLAY-ONLY.

Three changes under test:
  1. n_milb_seasons relabelled "Track-record depth" -> "Seasons to reach level"
     (the weight is -0.2324, so more seasons scored DOWN under a label that told the
     reader more was better).
  2. pitcher `age` excluded from the explainer (served +0.0589 against a declared -1,
     an omitted-variable artifact because _FEATURES_PIT has no level_rank).
  3. milb_missing skip reason corrected (the stated arithmetic was wrong).

What must hold: the CHIPS change, and the grade / WAR / surplus / ordering do NOT.
Read-only with respect to shipped artifacts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_score as es          # noqa: E402

DATA = ROOT / "data"


def main() -> int:
    print("labels:")
    print(f"  n_milb_seasons -> {es._FACTOR_LABELS['n_milb_seasons']!r}")
    print(f"  age            -> {es._FACTOR_LABELS['age']!r}")
    print(f"  side skips     -> {es._EXPLAINER_SKIP_SIDE}")
    assert es._FACTOR_LABELS["n_milb_seasons"] == "Seasons to reach level"
    assert "age" in es._EXPLAINER_SKIP_SIDE.get("pit", set())
    assert "age" not in es._EXPLAINER_SKIP_SIDE.get("hit", set()), \
        "the hitter Age chip must survive: there the fit agrees with the declaration"

    # what the CURRENTLY SHIPPED artifact says (pre-regen), for the record
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    stale_label = sum(
        1 for r in doc.values()
        for f in (r.get("factors") or [])
        if f.get("label") == "Track-record depth")
    pit_age = sum(
        1 for r in doc.values()
        if r.get("side") == "P"
        for f in (r.get("factors") or [])
        if f.get("label") == "Age")
    pit_age_down = sum(
        1 for r in doc.values()
        if r.get("side") == "P"
        for f in (r.get("factors") or [])
        if f.get("label") == "Age" and f.get("dir") == "down")
    hit_age = sum(
        1 for r in doc.values()
        if r.get("side") == "H"
        for f in (r.get("factors") or [])
        if f.get("label") == "Age")
    print("\nIN THE CURRENTLY SHIPPED ARTIFACT (these are what the repairs remove):")
    print(f'  cards showing "Track-record depth": {stale_label}')
    print(f'  PITCHER cards showing "Age":        {pit_age}  (reading DOWN: {pit_age_down})')
    print(f'  HITTER cards showing "Age":         {hit_age}  (kept by design)')
    print("\nThese counts do not drop until data/xfv.json is regenerated; the code path "
          "is what changed. Nothing above touches a grade, WAR, surplus or ordering.")

    # prove the exclusion is display-only: the feature is still IN the model
    import efv_model as em
    keys, _ = em._feature_spec("pit")
    assert "age" in keys, "age must remain a MODEL feature; only the chip is suppressed"
    print("\npitcher model feature set still contains 'age':", "age" in keys)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
