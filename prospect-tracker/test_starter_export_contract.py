# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Served-artifact data contract for data/starter_leaderboards.json (SEM+).

The starter board shipped with smoke tests only while the bullpen board
carried a real contract. This is the SEM+ analogue of
test_bullpen_export.test_data_contract, ported to THIS metric's own pool
definition: sem_plus.build_pool contributes on `ip >= POOL_MIN_IP` and anchors
on the IP-weighted mean of the shrunk skill FIP, so the weighting quantity is
IP (it is TBF for relievers and PA for hitters).

WHAT IS DELIBERATELY NOT IN HERE: a value band. "REM+ must land in 40..200"
was a comfort range, and Mason Miller's honest 203 broke it on 2026-07-30
without anything being wrong with the metric. Bands on '+' metrics are banned;
a clamp to satisfy one would be a display lie. Every assertion below is an
INVARIANT the metric satisfies BY CONSTRUCTION, so a genuine outlier passes
and a scale break (a z-score remap, a doubled constant, a lost pool
re-normalization) fails.

Skips when the artifact is absent, so the suite never triggers an export.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sem_plus

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "starter_leaderboards.json"
VERDICTS = {"validated", "provisional", "unvalidated", "deprecated"}

pytestmark = pytest.mark.skipif(
    not DATA.exists(), reason="starter_leaderboards.json not generated")


def _doc() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _pool_rows(d: dict) -> list[dict]:
    """The rows that CONTRIBUTE to the anchor, by sem_plus.build_pool's own
    rule: `s.ip >= POOL_MIN_IP and s.ip > 0`. IP is served verbatim on the
    row, so this reproduces pool membership exactly rather than approximating
    it."""
    return [r for r in d["starters"]
            if r.get("sem_plus") and (r.get("ip") or 0) >= sem_plus.POOL_MIN_IP]


def test_top_level_shape():
    d = _doc()
    for k in ("season", "as_of", "verdict", "pool", "starters", "teams"):
        assert k in d, f"missing top-level key {k}"
    assert d["verdict"] in VERDICTS
    assert isinstance(d["starters"], list) and d["starters"]
    assert isinstance(d["teams"], list) and d["teams"]
    for k in ("n", "mean_fip", "n_qualified", "n_provisional"):
        assert k in d["pool"], f"pool missing {k}"
    r0 = d["starters"][0]
    for k in ("key", "name", "team", "sem_plus", "sem_plus_raw", "qualified",
              "role", "ip", "gs", "tbf", "fip"):
        assert k in r0, f"starter missing {k}"


def test_thirty_team_rotations():
    d = _doc()
    teams = [t["team"] for t in d["teams"]]
    assert len(teams) == 30, teams
    assert len(set(teams)) == 30, "team codes fragmented or duplicated"
    for k in ("team", "n_starters", "rotation_plus", "starter_ip", "rotation"):
        assert k in d["teams"][0], f"team missing {k}"
    rots = [t.get("rotation_plus") for t in d["teams"]]
    assert rots == sorted(rots, key=lambda v: (v is None, -(v or 0))), \
        "team table not sorted by Rotation+ desc"


def test_board_sorted_by_sem_plus_desc():
    d = _doc()
    sems = [r["sem_plus"] for r in d["starters"] if r["sem_plus"] is not None]
    assert sems == sorted(sems, reverse=True), "board not sorted by SEM+ desc"


def test_sem_plus_within_its_structural_ceiling():
    """SEM+ is a RATIO index (100 * pool_mean_FIP / player_FIP, the ERA+ /
    wRC+ / REM+ family), NOT a z-score, so it has no upper bound in principle:
    a starter whose shrunk skill FIP is half the pool mean scores 200 and that
    is honest. The ONLY structural ceiling is the max(fip, 1.0) numerical
    floor inside sem_plus.fip_skill, which caps the ratio at
    100 * mean_fip / 1.0. Positivity is structural too: both sides of the
    ratio are positive by construction."""
    d = _doc()
    ceiling = 100.0 * d["pool"]["mean_fip"] / 1.0
    sems = [r["sem_plus"] for r in d["starters"] if r["sem_plus"] is not None]
    assert sems, "no scored starters"
    assert all(0 < x <= ceiling for x in sems), (min(sems), max(sems), ceiling)


def test_pool_row_count_equals_the_declared_pool_n():
    d = _doc()
    assert len(_pool_rows(d)) == d["pool"]["n"], \
        (len(_pool_rows(d)), d["pool"]["n"])


def test_pool_anchor_scores_exactly_100():
    """THE invariant, the one a band was really groping for.

    sem_plus.build_pool sets mean_fip to the IP-weighted mean of every
    pool arm's shrunk skill FIP, and SEM+ = 100 * mean_fip / fip. Substituting
    one into the other, the IP-weighted HARMONIC mean of SEM+ over the
    pool-contributing starters is 100 identically:

        sum(ip) / sum(ip / SEM+) = 100 * mean_fip * sum(ip) / sum(ip * fip)
                                 = 100 * mean_fip / mean_fip = 100

    An honest outlier at any level leaves this untouched. A z-score remap, a
    doubled constant, or a dropped pool re-normalization move it by tens.

    Tolerance 1.0 (the same the bullpen contract uses) absorbs the served
    integer rounding of SEM+; measured 99.99 on the 2026-08-01 artifact."""
    d = _doc()
    pool = _pool_rows(d)
    assert pool, "no pool-contributing starters"
    anchor = (sum(r["ip"] for r in pool)
              / sum(r["ip"] / r["sem_plus"] for r in pool))
    assert abs(anchor - 100.0) < 1.0, (
        f"SEM+ pool anchor is {anchor:.2f}, not 100 - the pool "
        "re-normalization in sem_plus.build_pool is broken or the scale is no "
        "longer a ratio index")


def test_sem_plus_is_the_served_fip_ratio():
    """The scale DEFINITION, pinned row by row against the numbers actually
    served: sem_plus_raw == 100 * pool.mean_fip / fip.

    Tolerance is derived from the served precision, not chosen for comfort.
    `fip` and `mean_fip` are rounded to 2dp (|delta| <= 0.005 each) and
    sem_plus_raw to 1dp (<= 0.05); propagating those through the ratio at the
    smallest served FIP bounds the disagreement below 1.0. Measured worst case
    on the 2026-08-01 artifact: 0.26."""
    d = _doc()
    mean_fip = d["pool"]["mean_fip"]
    checked = 0
    for r in d["starters"]:
        if not r.get("fip") or r.get("sem_plus_raw") is None:
            continue
        expected = 100.0 * mean_fip / r["fip"]
        assert abs(expected - r["sem_plus_raw"]) < 1.0, (
            r["name"], r["fip"], r["sem_plus_raw"], expected)
        checked += 1
    assert checked > 0.9 * len(d["starters"]), \
        f"only {checked}/{len(d['starters'])} rows carried a servable FIP"


def test_qualified_split_reconciles_with_the_rows():
    """pool.n_qualified / n_provisional are counted over the SERVED board, so
    they must partition it exactly. A drift here means the qualification rule
    and the published rows disagree about who is on the leaderboard."""
    d = _doc()
    rows = d["starters"]
    n_qual = sum(1 for r in rows if r.get("qualified"))
    assert n_qual == d["pool"]["n_qualified"], (n_qual, d["pool"]["n_qualified"])
    assert (d["pool"]["n_qualified"] + d["pool"]["n_provisional"]) == len(rows)


def test_pool_contributors_are_a_subset_of_the_board():
    """Every arm that moves the anchor is published. A pool larger than the
    board means the anchor is being set by rows nobody can see."""
    d = _doc()
    assert d["pool"]["n"] <= len(d["starters"])
    assert all((r.get("ip") or 0) > 0 for r in _pool_rows(d))
