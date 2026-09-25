# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Spotlights track-record receipt says what its control actually is.

WHY THIS EXISTS (census M02-04, 2026-09-25, two verifiers CONFIRMED). editorial_eval
scores a flag from its stored FV and a control from the median of source snapshots,
and draws the controls as the first unflagged players by player_key (4,827 faller
draws from 37 players). The /glossary/ receipt called them "matched unflagged players
in the same FV band and window" and the registry row called them "fv-band matched
controls", while its notes still quoted the 2026-07-14 first scoring. The eval
correction itself (one basis, random in-cell controls, clustered CIs) changes
kill-rule verdicts, which are owner-committed, so it is held for the owner; this
pins the disclosure until then.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_receipt_does_not_claim_matched_controls():
    src = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert "matched unflagged players" not in src
    assert "the first five by player key, not a random draw" in src
    assert "Method caveat (audit 2026-09-25)" in src


def test_registry_row_describes_the_served_control():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(m for m in reg["models"] if m["model_id"] == "spotlights_movement")
    assert "matched controls" not in row["baseline"]
    assert "not a random matched draw" in row["baseline"]
    assert "2026-07-14" not in row["notes"]      # the stale first-scoring figures are gone
    assert row["verdict"] == "provisional"
