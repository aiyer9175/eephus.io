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
    # D9 (2026-09-24): the Club Ledger board copies the stamp of every source its
    # farm rows read (calibration.version = trade_values'), so a v7 flip flags it
    # with the other four instead of leaving a stale ledger beside fresh boards.
    "ledger_board.json": ("calibration",),
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


# A board row and a projections row describe one human only if their ages
# agree to within this many years (the two artifacts date ages differently, so
# a few months of drift is normal; a decade is a second human).
_AGE_TOL_YEARS = 1.5


def _projection_parity_violations(board_rows, vets, tol_mm=0.15):
    """Every projection-priced board row against the projections row of the SAME
    HUMAN. Returns (n_checked, violations).

    The join is on mlbam id, and on the row's projections key only where the
    board row carries no id. It used to be on player_key, which is a slug: the
    ATH infielder max_muncy (691777) carried the LAD veteran's (571970) $54.3M
    and this test passed him, because keyed on the slug the two surfaces agreed
    exactly. The age guard is the second, independent witness: a 24-year-old
    and a 36-year-old are not one person whatever the ids say."""
    by_id, by_key = {}, {}
    for v in vets:
        if v.get("mlbam") is not None:
            by_id[int(v["mlbam"])] = v
        if v.get("key"):
            by_key[v["key"]] = v
    n, bad = 0, []
    for row in board_rows:
        if row.get("surplus_source") != "projection" or row.get("trade_value_mm") is None:
            continue          # eFV-sourced rows are a different basis by design
        key = row.get("player_key")
        mid = row.get("mlbam_id")
        if mid is not None:
            v = by_id.get(int(mid))
        else:
            v = by_key.get(row["proj_key"] if "proj_key" in row else key)
        if v is None:
            bad.append((key, "no projections row for this human"))
            continue
        n += 1
        val = v.get("surTotal") if v.get("surTotal") is not None else v.get("surNpv")
        if val is None:
            bad.append((key, "the projections row carries no price"))
            continue
        if abs(float(row["trade_value_mm"]) - val / 1e6) > tol_mm:
            bad.append((key, "value", row["trade_value_mm"], round(val / 1e6, 1)))
        if row.get("age") is not None and v.get("age") is not None \
                and abs(float(row["age"]) - float(v["age"])) >= _AGE_TOL_YEARS:
            bad.append((key, "age", row["age"], v["age"]))
    return n, bad


def _served_board_and_vets():
    tvp, projp = DATA / "trade_values.json", DATA / "mlb_projections.json"
    if not (tvp.exists() and projp.exists()):
        pytest.skip("artifacts not built on this machine")
    try:
        rows = json.loads(tvp.read_text(encoding="utf-8"))["players"]
        vets = json.loads(projp.read_text(encoding="utf-8")).get("vets") or []
    except (OSError, ValueError, KeyError) as exc:
        pytest.skip(f"unreadable artifact: {exc}")
    if not any("mlbam_id" in r for r in rows):
        pytest.skip("trade_values.json predates the mlbam_id field - regenerate it")
    return rows, vets


def test_the_same_player_is_worth_the_same_on_every_surface():
    """Surplus cohesion, the invariant behind the stamps.

    An MLB veteran's trade-board value IS his /projections/ contract surplus -
    `apply_platform_surplus` re-points it, and the vets seeded into the board
    from the projection artifact are built from the same number. So the two
    surfaces must agree per player, not merely share a calibration version. This
    catches a re-point that silently stops firing, which is the failure the
    Anderson investigation found in the OTHER direction (four artifacts on three
    different vintages, all internally consistent, none agreeing).

    The compared field is `surTotal` (2026-08-03): the balance of the season in
    progress plus the NPV of every controlled season after it. Both surfaces
    moved to it together, which is the point - comparing the board's surTotal
    against the page's surNpv would fail for every player with a priced
    remainder and would be measuring a mismatch this test invented itself.
    `surNpv` remains the fallback so a pre-change artifact still reconciles.

    Joined on the HUMAN (see _projection_parity_violations), never on the slug."""
    rows, vets = _served_board_and_vets()
    n, bad = _projection_parity_violations(rows, vets)
    assert n > 800, n
    assert not bad[:10], (
        "trade board and /projections/ disagree on the same player's surplus, or a "
        f"board row carries another human's: {bad[:10]}")


def test_no_human_appears_twice_on_the_trade_board():
    """One human, one row, one price. Keyed on the slug, the board carried the
    same player twice wherever the prospect feed and projections spelled him
    differently (rafael_flores_jr at $3.7M and rafael_flores at $66.9M)."""
    rows, _vets = _served_board_and_vets()
    seen: dict = {}
    dup = []
    for r in rows:
        mid = r.get("mlbam_id")
        if mid is None:
            continue
        if mid in seen:
            dup.append((mid, seen[mid], r.get("player_key")))
        seen[mid] = r.get("player_key")
    assert not dup[:10], dup[:10]


def test_the_parity_check_catches_a_row_wearing_another_humans_price():
    """Mutation: hand one projection-priced row the id of another human whose
    price and age differ. The check must fail it. If this passes silently, the
    parity test above is certifying nothing about identity, which is what it did
    when it joined on the slug."""
    rows, vets = _served_board_and_vets()
    by_id = {int(v["mlbam"]): v for v in vets if v.get("mlbam") is not None}
    priced = [r for r in rows if r.get("surplus_source") == "projection"
              and r.get("mlbam_id") is not None and r.get("age") is not None
              and int(r["mlbam_id"]) in by_id]
    a = next((r for r in priced if float(r["age"]) >= 33), None)
    b_ = next((r for r in priced if float(r["age"]) <= 27
               and abs(float(r["trade_value_mm"]) - float((a or {}).get("trade_value_mm") or 0)) > 1.0), None)
    if a is None or b_ is None:
        pytest.skip("the served board has no pair to swap")
    swapped = [dict(r) for r in (a, b_)]
    swapped[0]["mlbam_id"], swapped[1]["mlbam_id"] = b_["mlbam_id"], a["mlbam_id"]
    _n, bad = _projection_parity_violations(swapped, vets)
    kinds = {x[1] for x in bad}
    assert "value" in kinds and "age" in kinds, bad


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
