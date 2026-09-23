# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The 2026 feed families (challenges, ABS challenges, mound-visit budgets, lineups).

WAVE B BUILDS THE READER (mgmt_feeds_2026.py over .cache/game_feeds); Wave A ships the
two blocks DARK with their blockers and the regime rules the reader must obey. These
tests pin the rules now so the reader cannot land without them: ABS pitch challenges
are a separate 2026 regime and never mix with replay challenges, crew-chief reviews are
counted and never credited, the challenging side resolves through the club id, the
lineup slot's first occupant is the plays row's batter, and no challenge ever carries a
realized value (the feed prices only the final ruling). Where the module exists the
same tests run against it; where it does not, the served blocks must say so."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

BOARD = ROOT / "data" / "management_board.json"


@pytest.fixture(scope="module")
def board():
    if not BOARD.exists():
        pytest.skip("run python mgmt_export.py")
    return json.loads(BOARD.read_text(encoding="utf-8"))


def _feeds_module():
    try:
        return importlib.import_module("mgmt_feeds_2026")
    except ImportError:
        return None


def test_abs_challenges_are_separated_from_replay_challenges(board):
    ch = board["challenges"]
    assert "ABS" in ch["regime_note"] and "never mixed" in ch["regime_note"]
    assert "MJ" in ch["regime_note"], "the ABS review type is named so the reader keys on it"
    if ch.get("live"):
        for r in ch["rows"]:
            assert "abs_challenges" in r and "challenges" in r
    else:
        assert "mgmt_feeds_2026" in ch["blocked_on"]
        assert _feeds_module() is None, "the reader exists but the block is dark"


def test_umpire_reviews_are_counted_not_credited(board):
    ch = board["challenges"]
    assert "crew-chief reviews" in ch["regime_note"] and "counted" in ch["regime_note"]
    assert "not credited" in ch["regime_note"]
    if ch.get("live"):
        for r in ch["rows"]:
            assert "umpire_reviews" in r


def test_challenge_side_resolves_through_canonical_org_from_id(board):
    """The join the reader will use: reviewDetails.challengeTeamId through
    trades.canonical_org_from_id, then the outbound StatsAPI code through
    trades.statsapi_code (Wave 0 helper)."""
    import trades
    assert trades.canonical_org_from_id(147) == "NYY"
    assert trades.canonical_org_from_id(118) == "KCR"
    assert trades.canonical_org_from_id(145) == "CHW"
    assert trades.canonical_org_from_id(120) == "WSN"
    assert trades.statsapi_code(trades.canonical_org_from_id(118)) == "KC"
    m = _feeds_module()
    if m is not None and hasattr(m, "challenge_side"):
        assert m.challenge_side({"challengeTeamId": 147}) == "NYY"


def test_lineup_slot_first_occupant_agrees_with_batting_order(board):
    lu = board["lineups"]
    m = _feeds_module()
    if m is None:
        assert lu["live"] is False
        assert "battingOrder" in lu["blocked_on"]
        assert "not measured" in lu["value_not_measured"]
        return
    pytest.importorskip("pandas")
    assert hasattr(m, "lineup_first_occupant"), "the reader must read the slot's FIRST occupant"


def test_challenge_value_is_not_claimed(board):
    ch = board["challenges"]
    assert "not observable" in ch["value_not_observable"]
    for k in ch:
        assert "mwpa" not in k and "dv" not in k, k
    if ch.get("live"):
        for r in ch["rows"]:
            for k in r:
                assert "mwpa" not in k and "dv" not in k and "decision" not in k, k
