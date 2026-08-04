# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Served-artifact data contract for data/hitter_leaderboards.json (HEM+).

The hitter board shipped with smoke tests only while the bullpen board carried
a real contract. This is the HEM+ analogue of
test_bullpen_export.test_data_contract, ported to THIS metric's own pool
definition and, importantly, to its own SCALE.

HEM+ IS NOT A RATIO INDEX. REM+ and SEM+ are (100 * pool_mean / player), so
their anchor is a weighted HARMONIC mean. hem_plus.hem_plus is AFFINE in the
shrunk skill wOBA:

    HEM+ = 100 + HEM_SPREAD_GAIN * (100 * woba_skill / pool.mean_woba - 100)

so the correct anchor invariant here is the weighted ARITHMETIC mean, and the
weight is the wOBA denominator (hem_plus._woba_denom = AB + BB - IBB + SF +
HBP), which is what build_pool weights by. Porting the harmonic form or the
IP/TBF weight to this board would be testing a different metric's algebra.

WHAT IS DELIBERATELY NOT IN HERE: a value band. "REM+ must land in 40..200"
was a comfort range, and Mason Miller's honest 203 broke it on 2026-07-30
without anything being wrong with the metric. Bands on '+' metrics are banned.
Everything below is an INVARIANT the metric satisfies BY CONSTRUCTION.

Skips when the artifact is absent, so the suite never triggers an export.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import hem_plus

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "hitter_leaderboards.json"
VERDICTS = {"validated", "provisional", "unvalidated", "deprecated"}

pytestmark = pytest.mark.skipif(
    not DATA.exists(), reason="hitter_leaderboards.json not generated")


def _doc() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _pool_rows(d: dict) -> list[dict]:
    """The rows that CONTRIBUTE to the anchor, as closely as the served row
    permits.

    hem_plus.build_pool contributes on `_woba_denom(h) >= POOL_MIN_PA`, and
    the wOBA denominator is NOT served on the row (hitter_row publishes pa,
    ab, hr, bb, sb but not ibb / sf / hbp). PA is its exact upper bound:
    PA - woba_denom == IBB + sacrifice bunts, both non-negative. So the PA
    rule selects a SUPERSET of the true pool, differing only for a hitter
    sitting within an intentional walk or two of the 50-PA line. That is why
    the count assertion below is stated as the inequality that always holds
    rather than an equality that would flake on one IBB."""
    return [r for r in d["hitters"]
            if r.get("hem_plus") is not None
            and (r.get("pa") or 0) >= hem_plus.POOL_MIN_PA]


def test_top_level_shape():
    d = _doc()
    for k in ("season", "as_of", "verdict", "pool", "hitters", "teams"):
        assert k in d, f"missing top-level key {k}"
    assert d["verdict"] in VERDICTS
    assert isinstance(d["hitters"], list) and d["hitters"]
    assert isinstance(d["teams"], list) and d["teams"]
    for k in ("n", "mean_woba", "n_qualified", "n_provisional"):
        assert k in d["pool"], f"pool missing {k}"
    assert d["pool"]["mean_woba"] > 0
    r0 = d["hitters"][0]
    for k in ("key", "name", "team", "hem_plus", "hem_plus_raw", "qualified",
              "tier", "pa", "woba"):
        assert k in r0, f"hitter missing {k}"


def test_thirty_team_offenses():
    d = _doc()
    teams = [t["team"] for t in d["teams"]]
    assert len(teams) == 30, teams
    assert len(set(teams)) == 30, "team codes fragmented or duplicated"
    for k in ("team", "n_hitters", "offense_plus", "team_pa", "lineup"):
        assert k in d["teams"][0], f"team missing {k}"
    offs = [t.get("offense_plus") for t in d["teams"]]
    assert offs == sorted(offs, key=lambda v: (v is None, -(v or 0))), \
        "team table not sorted by Offense+ desc"


def test_board_sorted_by_hem_plus_desc():
    d = _doc()
    hems = [r["hem_plus"] for r in d["hitters"] if r["hem_plus"] is not None]
    assert hems == sorted(hems, reverse=True), "board not sorted by HEM+ desc"


def test_hem_plus_within_its_structural_bounds():
    """HEM+ has no comfort range, but it does have structural ones.

    woba_skill is a linear-weights combination of SHRUNK event rates that
    share one denominator, so it cannot exceed the largest weight (a hitter
    whose every wOBA event is a home run) and cannot go below zero. Feeding
    those two extremes through the affine HEM+ definition gives the only
    bounds that exist. They are wide on purpose: an honest 167 has to pass,
    the same way REM+ 203 had to."""
    d = _doc()
    mean_woba = d["pool"]["mean_woba"]
    gain = hem_plus.HEM_SPREAD_GAIN
    ceiling = 100.0 + gain * (100.0 * hem_plus.W_HR / mean_woba - 100.0)
    floor = 100.0 - gain * 100.0            # woba_skill -> 0
    hems = [r["hem_plus"] for r in d["hitters"] if r["hem_plus"] is not None]
    assert hems, "no scored hitters"
    assert all(floor <= x <= ceiling for x in hems), \
        (min(hems), max(hems), floor, ceiling)


def test_pool_contributors_never_exceed_the_50_pa_population():
    """The pool count contract, stated in the direction that is exactly true.

    Contribution is gated on the wOBA denominator, which never exceeds PA
    (PA - denom == IBB + sac bunts >= 0). So the declared pool n can never be
    larger than the number of published hitters with 50+ PA, and every pool
    contributor is on the board. A violation means the anchor is being set by
    rows that are not published, or by a population rule that no longer
    matches hem_plus.POOL_MIN_PA."""
    d = _doc()
    assert d["pool"]["n"] <= len(_pool_rows(d)), \
        (d["pool"]["n"], len(_pool_rows(d)))
    assert d["pool"]["n"] <= len(d["hitters"])
    assert all((r.get("pa") or 0) > 0 for r in _pool_rows(d))


def test_pool_anchor_scores_exactly_100():
    """THE invariant, in HEM+'s own algebra.

    hem_plus.build_pool sets mean_woba to the wOBA-denominator-weighted mean
    of every pool bat's SHRUNK wOBA, and HEM+ is affine in that same shrunk
    wOBA with one shared slope. So the weighted ARITHMETIC mean of HEM+ over
    the pool is 100 identically:

        mean(HEM+) = 100 + gain * (100 * mean(woba_skill) / mean_woba - 100)
                   = 100 + gain * (100 - 100) = 100

    regardless of HEM_SPREAD_GAIN, which is why widening the display spread
    (2026-07) could not move the anchor and a scale break cannot hide behind
    it. An honest outlier at any level leaves this untouched; a z-score remap,
    a doubled constant or a lost pool re-normalization move it by tens.

    Weight caveat: the exact weight is the wOBA denominator, which the row
    does not publish, so PA stands in for it. PA differs from it only by IBB
    plus sac bunts, a sub-1% share of the total that carries HEM+ values from
    the same distribution, so the substitution perturbs the anchor far less
    than the tolerance. Tolerance 1.0 matches the bullpen contract and also
    absorbs the served integer rounding; measured 100.01 on the 2026-08-01
    artifact."""
    d = _doc()
    pool = _pool_rows(d)
    assert pool, "no pool-contributing hitters"
    w = sum(r["pa"] for r in pool)
    anchor = sum(r["hem_plus"] * r["pa"] for r in pool) / w
    assert abs(anchor - 100.0) < 1.0, (
        f"HEM+ pool anchor is {anchor:.2f}, not 100 - the pool "
        "re-normalization in hem_plus.build_pool is broken or HEM+ is no "
        "longer affine in the shrunk wOBA")


def test_hem_plus_is_the_served_woba_deviation():
    """The scale DEFINITION, pinned row by row against the numbers actually
    served: hem_plus_raw == 100 + GAIN * (100 * woba / mean_woba - 100).

    This is what catches a silent change to HEM_SPREAD_GAIN, which the anchor
    test provably cannot see.

    Tolerance is derived from the served precision, not chosen for comfort.
    `woba` and `mean_woba` are rounded to 3dp (|delta| <= 0.0005 each), which
    propagates to at most ~0.32 on the ratio term and ~0.72 after the gain;
    hem_plus_raw is rounded to 1dp (<= 0.05). Measured worst case on the
    2026-08-01 artifact: 0.48."""
    d = _doc()
    mean_woba = d["pool"]["mean_woba"]
    gain = hem_plus.HEM_SPREAD_GAIN
    checked = 0
    for r in d["hitters"]:
        if r.get("woba") is None or r.get("hem_plus_raw") is None:
            continue
        expected = 100.0 + gain * (100.0 * r["woba"] / mean_woba - 100.0)
        assert abs(expected - r["hem_plus_raw"]) < 1.0, (
            r["name"], r["woba"], r["hem_plus_raw"], expected)
        checked += 1
    assert checked > 0.9 * len(d["hitters"]), \
        f"only {checked}/{len(d['hitters'])} rows carried a servable wOBA"


def test_qualified_split_reconciles_with_the_rows():
    """pool.n_qualified / n_provisional are counted over the SERVED board, so
    they must partition it exactly. A drift here means the qualification rule
    and the published rows disagree about who is on the leaderboard."""
    d = _doc()
    rows = d["hitters"]
    n_qual = sum(1 for r in rows if r.get("qualified"))
    assert n_qual == d["pool"]["n_qualified"], (n_qual, d["pool"]["n_qualified"])
    assert (d["pool"]["n_qualified"] + d["pool"]["n_provisional"]) == len(rows)
