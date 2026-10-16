# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The position-centred G-A re-check registration pins (task SDR_POSCENTRED_REGISTER,
owner decision EW3-33, SDR-GA-Q1 part 2).

docs/sdr-2026-08-18/SDR_POSCENTRED_GATE.md was committed ALONE before any number of
its estimands exists; its outcome season (2027) has not been played. Each clause is
pinned by the sentence that makes it bind, on a whitespace-flattened copy so that
re-wrapping a paragraph is not a failure. Results go in part 13, never above it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "sdr-2026-08-18" / "SDR_POSCENTRED_GATE.md"
GA = ROOT / "docs" / "sdr-2026-08-18" / "SDR_EVAL_GATE.md"
FROZEN = ROOT / ".cache" / "sdr" / "frozen_predictor_2026"
RESULTS = "## 13. Results and dated notes"

HASHES = {
    "sdr_defense_card__2026-10-15.csv":
        "8a41d1c20ce37a45fec3150fcf87ceae67f74a16d77cbdf53f44edc44691358e",
    "06_defense_plus_2026__no_drs.csv":
        "bba48de839389910f2832ef285b464631816bdd503478ead6e8424853ae7762e",
    "06_defense_plus_2026__no_statcast.csv":
        "39ff933faae677d6cf1318137e95012be2f9e273ce6c473504ce556ba67b77cd",
    "06_defense_plus_2026.csv":
        "86ffa794d39dce368185432d5cce91b104260d8b14cca73dbafe5626135c0822",
    "fg_field_full_2026.csv":
        "58e53c3a5ca76befeae87a5d5d32035da9fb7073f88275c69914b3263fe671cc",
    "fg_field_split_2026.csv":
        "a6c4d620b5bf4f87d949d2226633f0d89d0491da452811e20d67fd7f62594713",
    "fg_team_pit_2026.csv":
        "aa00708026f99132db490403d9be6750028bb02a32bd7d0ab7584e5b949dc023",
    "bat.parquet":
        "e9571c428cb4db444e4b8214bb9adc5834925529e7d10db4271993f79fc3fd55",
}


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _above() -> str:
    return _flat(_doc().split(RESULTS, 1)[0])


def test_registered_alone_and_read_after_the_2027_season():
    flat = _flat(_doc())
    assert flat.startswith("# SDR_POSCENTRED_GATE: the position-centred G-A re-check on unseen "
                           "pairs (registered 2026-10-16)")
    assert "Read once, not before 2027-11-01, by the queued task SDR_POSCENTRED_READ." in flat
    assert "it needs data that does not exist yet (the 2027 season)" in flat
    assert RESULTS in _doc()


def test_one_unseen_pair_season_and_frozen_predictors():
    flat = _above()
    assert "Predictor season Y = 2026, outcome season Y + 1 = 2027." in flat
    assert "No other season pair is scored by a deciding leg." in flat
    assert "a mismatch STOPS the read" in flat
    for name, digest in HASHES.items():
        assert f"`{name}`" in flat and digest in flat, name


def test_the_centring_and_the_comparators():
    flat = _above()
    assert "c_m(i, Y) = rate_m(i, Y) - mu_m(P(i, Y), Y)" in flat
    assert "(tie: the earlier of C, 1B, 2B, 3B, SS, LF, CF, RF)" in flat
    assert "a cell with fewer than 8 eligible player-seasons is dropped" in flat
    assert "C1c clears Z when LB95(rho_SDR) > 0" in flat
    assert "LB95(d_PT) > 0 (clears PT)" in flat
    assert "C2 also needs LB95(rho_SDR) > 0 (clears Z)" in flat
    assert "LB95(g_Z) > 0" in flat


def test_unchanged_legs_seeds_and_verdict():
    flat = _above()
    assert "C2: club runs allowed beyond FIP (deciding, G-A's leg unchanged)" in flat
    assert "C5: the EW3-23 leg (deciding for that read, Holm family k = 1, G-A's leg unchanged)" in flat
    assert "Holm** across C1c and C2 at alpha 0.05 (k = 2)" in flat
    for seed in ("seed 20271101", "seed 20271102", "seed 20271103"):
        assert seed in flat
    assert "PASS when C1c and C2 both pass; PARTIAL when one passes; FAIL when neither does." in flat


def test_planted_recovery_before_the_read():
    flat = _above()
    for world in ("**PLANTED.**", "**NULL.**", "**POSITION ONLY.**", "**PLAYING TIME ONLY.**"):
        assert world in flat
    assert "the read does not run: the defect is fixed and recorded in part 13 before the read" in flat


def test_no_fv_stratification_and_no_eWAR_until_the_read():
    flat = _above()
    assert "no stratification by consensus-FV level anywhere" in flat
    assert "SDR stays out of eWAR." in flat
    assert "that gate read PARTIAL on 2026-10-16" in flat


def test_ga_carries_the_pointer_note():
    flat = _flat(GA.read_text(encoding="utf-8"))
    assert ("### Note 2026-10-16: the position-centred re-check is registered "
            "(owner decision EW3-33)") in flat
    assert "G-A's verdict stands." in flat.rsplit("position-centred re-check is registered", 1)[1]


@pytest.mark.skipif(not FROZEN.exists(), reason="frozen predictor copies live in the local cache")
def test_frozen_copies_match_the_registered_hashes():
    for name, digest in HASHES.items():
        got = hashlib.sha256((FROZEN / name).read_bytes()).hexdigest()
        assert got == digest, name
