# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Spotlights track-record receipt says what its control actually is.

WHY THIS EXISTS (census M02-04, 2026-09-25, two verifiers CONFIRMED). editorial_eval
v1 scores a flag from its stored FV and a control from the median of source snapshots,
and draws the controls as the first unflagged players by player_key (4,827 faller
draws from 37 players), while the /glossary/ receipt called them "matched unflagged
players in the same FV band and window". The disclosure shipped first; the owner then
chose the re-score (answer 2026-09-25, batch 4), and v2 now serves: one basis, seeded
random in-cell controls, monthly cohorts, player-clustered intervals. These pins keep
the receipt and the registry row describing the control that is actually served.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_receipt_describes_the_served_v2_control():
    src = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert "matched unflagged players in the same FV band and window" not in src
    i = src.index("spotlights: {")
    spec = src[i:src.index("fa_projection_engine: {", i)]
    assert "drawn at random from the flag's own FV band x level x age band" in spec
    assert "first unflagged players by key" in spec      # the before column is named


def test_registry_row_describes_the_served_control():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(m for m in reg["models"] if m["model_id"] == "spotlights_movement")
    assert "drawn at random" in row["baseline"] and "v2" in row["baseline"]
    assert "2026-07-14" not in row["notes"]      # the stale first-scoring figures are gone
    assert row["verdict"] == "provisional"
    assert row["card"]["derived_from"]["headline"][0]["champion"].startswith("v2.")
