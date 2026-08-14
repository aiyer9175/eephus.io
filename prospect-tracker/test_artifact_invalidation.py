# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The freshness gate must honour an EXPLICIT invalidation ahead of age.

WHY THIS FILE EXISTS. `run_monthly._artifact_fresh` gates expensive derived
steps on the artifact's own `generated_at`. That is the right question for an
artifact whose inputs only accumulate, and the WRONG question for one whose
inputs can be RE-KEYED underneath it.

Measured case, 2026-08-12 to 2026-08-14: the jesus_lopez identity repair split
a Boston DSL RHP (mlbam 838819) off a Texas catcher's key (805052).
data/positions_played.json had been built 2026-08-11, one day earlier, so at
VERSA_FRESH_DAYS = 7 every run skipped step 3a-ii and kept serving the
merge-window value, the catcher credited with the RHP's pitching line. A
COMPLETED repair therefore kept failing its own gate for three days, and the
baseline entry's leave condition concluded the repair must be incomplete. It
was not.

The fix is a separate key rather than a backdated stamp: `generated_at` is
provenance, and moving it to buy a rebuild would be falsifying a measurement.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import run_monthly as rm

ROOT = Path(__file__).resolve().parent
VERSA = ROOT / "data" / "positions_played.json"


def _write(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "artifact.json"
    p.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    return p


def test_a_young_artifact_is_fresh(tmp_path):
    """The control. Without this the invalidation test below could pass on an
    always-False gate, which would be a guard that asserts nothing."""
    from datetime import date
    p = _write(tmp_path, {"generated_at": date.today().isoformat(), "players": {}})
    assert rm._artifact_fresh(p, 7) is True


def test_an_explicit_invalidation_beats_a_young_stamp(tmp_path):
    """THE CONTRACT. A same-day artifact carrying `invalidated_by` is stale."""
    from datetime import date
    p = _write(tmp_path, {"generated_at": date.today().isoformat(),
                          "invalidated_by": "identity repair",
                          "players": {}})
    assert rm._artifact_fresh(p, 7) is False, (
        "an explicitly invalidated artifact must force a rebuild no matter how "
        "young its generated_at is")


def test_an_empty_invalidation_string_does_not_invalidate(tmp_path):
    """Falsy values must not trip the gate, or every artifact that ever grows
    the key with a blank default rebuilds forever."""
    from datetime import date
    p = _write(tmp_path, {"generated_at": date.today().isoformat(),
                          "invalidated_by": "",
                          "players": {}})
    assert rm._artifact_fresh(p, 7) is True


def test_a_non_dict_artifact_fails_open(tmp_path):
    """FAIL-OPEN is the module's stated posture: anything unreadable rebuilds
    rather than being trusted."""
    p = tmp_path / "a.json"
    p.write_text("[1,2,3]", encoding="utf-8")
    assert rm._artifact_fresh(p, 7) is False


def test_the_versa_artifact_is_currently_invalidated_and_says_why():
    """THE LIVE PIN, and it is deliberately narrow.

    This asserts the CURRENT state: positions_played.json is invalidated and
    names the repair. It is expected to go away on the next rebuild of step
    3a-ii, at which point the artifact regenerates without the key and this
    test skips rather than fails. It exists so the invalidation cannot be
    silently dropped before the rebuild that consumes it.
    """
    if not VERSA.exists():
        pytest.skip("positions_played.json absent")
    doc = json.loads(VERSA.read_text(encoding="utf-8"))
    reason = doc.get("invalidated_by")
    if not reason:
        pytest.skip("versa artifact has been regenerated; invalidation consumed")
    assert "identity repair" in reason, (
        "an invalidation must say what invalidated it, so the next reader can "
        "tell a deliberate rebuild request from a stray key")
    assert rm._artifact_fresh(VERSA, rm.VERSA_FRESH_DAYS) is False, (
        "the live versa artifact carries invalidated_by but the gate still "
        "reads it as fresh; step 3a-ii would skip and the stale merge-window "
        "fielding line would keep serving")
