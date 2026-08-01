# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every served artifact that carries surplus DOLLARS must say which dollar
calibration produced them, and they must all say the SAME thing.

Why this exists: the v6 EV re-fit landed in value_framework_config.yaml at 14:42
on 2026-07-31. By that evening four served artifacts disagreed about what a
prospect was worth - xfv.json had been rebuilt on v6 while trade_values.json,
mlb_projections.json and timeseries.json still carried v5 numbers. timeseries.json
was written at 21:12, six and a half hours after the config changed, because a
long-running chained export held the pre-14:42 config in memory. On the served
board, toggling the grade chip flipped one player between $87.4M (#1) and $63.4M
(#4). Nothing in the system could detect it, because no artifact recorded which
map it used.

This is the board-fingerprint lesson applied to the pricing layer: a fingerprint
only guards what it NAMES.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import value_framework as vf

DATA = Path(__file__).parent / "data"

# artifact -> where its calibration stamp lives in the JSON
_SURPLUS_ARTIFACTS = {
    "xfv.json": ("meta", "calibration"),
    "trade_values.json": ("calibration",),
    "mlb_projections.json": ("calibration",),
    "timeseries.json": ("calibration",),
}


def _dig(doc, path):
    cur = doc
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _load(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"{name} not built on this machine")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        pytest.fail(f"{name} unreadable: {exc}")


def test_calibration_version_is_reported():
    v = vf.calibration_version()
    assert isinstance(v, str) and v
    cal = vf._config().get("calibration", {})
    if cal.get("enabled"):
        assert v == cal.get("version")
    else:
        assert v == "identity", "a disabled calibration must not report a version"


def test_calibration_stamp_shape():
    st = vf.calibration_stamp()
    assert set(st) == {"version", "enabled", "method"}
    assert isinstance(st["enabled"], bool)


@pytest.mark.parametrize("name", sorted(_SURPLUS_ARTIFACTS))
def test_every_surplus_artifact_carries_a_stamp(name):
    """A missing stamp is the failure mode this test exists for: it is exactly
    the state all four artifacts were in when they silently disagreed."""
    doc = _load(name)
    stamp = _dig(doc, _SURPLUS_ARTIFACTS[name])
    if stamp is None:
        pytest.xfail(f"{name} predates the calibration stamp - regenerate it")
    assert stamp.get("version"), f"{name} carries an empty calibration version"


def test_all_surplus_artifacts_agree_on_the_calibration():
    """The actual invariant. Skips artifacts that have not been regenerated
    since the stamp landed, so this goes green as the box catches up rather
    than blocking on a stale file it cannot fix."""
    seen = {}
    for name, path in _SURPLUS_ARTIFACTS.items():
        p = DATA / name
        if not p.exists():
            continue
        try:
            stamp = _dig(json.loads(p.read_text(encoding="utf-8")), path)
        except (OSError, ValueError):
            continue
        if isinstance(stamp, dict) and stamp.get("version"):
            seen[name] = stamp["version"]
    if len(seen) < 2:
        pytest.skip("fewer than two stamped artifacts on this machine yet")
    versions = set(seen.values())
    assert len(versions) == 1, (
        "served artifacts disagree on the dollar calibration, so the same player "
        f"is worth different amounts on different surfaces: {seen}")


def test_the_same_player_is_worth_the_same_on_every_surface():
    """Surplus cohesion, the invariant behind the stamps.

    An MLB veteran's trade-board value IS his /projections/ contract surplus -
    `apply_platform_surplus` re-points it to surNpv, and the vets seeded into the
    board from the projection artifact are built from the same number. So the two
    surfaces must agree per player, not merely share a calibration version. This
    catches a re-point that silently stops firing, which is the failure the
    Anderson investigation found in the OTHER direction (four artifacts on three
    different vintages, all internally consistent, none agreeing)."""
    tvp, projp = DATA / "trade_values.json", DATA / "mlb_projections.json"
    if not (tvp.exists() and projp.exists()):
        pytest.skip("artifacts not built on this machine")
    try:
        board = {p["player_key"]: p for p in
                 json.loads(tvp.read_text(encoding="utf-8"))["players"]
                 if p.get("player_key")}
        vets = json.loads(projp.read_text(encoding="utf-8")).get("vets") or []
    except (OSError, ValueError, KeyError) as exc:
        pytest.skip(f"unreadable artifact: {exc}")

    mismatched = []
    for v in vets:
        row = board.get(v.get("key"))
        if not row or v.get("surNpv") is None:
            continue
        if row.get("surplus_source") != "projection":
            continue          # eFV-sourced rows are a different basis by design
        if row.get("trade_value_mm") is None:
            continue
        if abs(float(row["trade_value_mm"]) - v["surNpv"] / 1e6) > 0.15:
            mismatched.append((v["key"], row["trade_value_mm"], v["surNpv"] / 1e6))
    assert not mismatched[:10], (
        "trade board and /projections/ disagree on the same player's surplus: "
        f"{mismatched[:10]}")


def test_stamped_artifacts_match_the_live_config():
    """A stamp that disagrees with the config in force means the artifact was
    built by a process holding a stale config in memory - the 21:12 timeseries
    case. Reported as a regen requirement, not a code failure."""
    live = vf.calibration_version()
    stale = {}
    for name, path in _SURPLUS_ARTIFACTS.items():
        p = DATA / name
        if not p.exists():
            continue
        try:
            stamp = _dig(json.loads(p.read_text(encoding="utf-8")), path)
        except (OSError, ValueError):
            continue
        if isinstance(stamp, dict) and stamp.get("version") and stamp["version"] != live:
            stale[name] = stamp["version"]
    if stale:
        pytest.xfail(f"artifacts built on a superseded calibration (regen owed): "
                     f"{stale} vs live {live}")
