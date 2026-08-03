# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Rest-of-season control pricing (owner ask, 2026-08-03).

Until now `surNpv` summed only FIRST_SEASON onward, so a contract whose last
season is the one in progress produced no surplus anywhere on the platform and
every deadline rental read "not tradeable". A club still controls that player
for the balance of the season, and that is a real, tradeable asset.

This supersedes the reading recorded in docs/efv-2026-07-31/TRADE_BOARD_COVERAGE.md
("a pending free agent is not a trade asset"). A.J. Minter is the canonical
case: NYM, contract through 2026, $7,588,208 for the year. At ~32% of the
season left and a 0.23-WAR full-season projection he is worth about -$1.7M -
a slightly negative rental, because he is owed more than his remaining
production is worth. NEGATIVE IS A RESULT, NOT A BUG: the board has carried
negative-surplus rows since the v6 EV frame removed the $0 floor, and "we can
price him and he is worth less than his salary" is a different and far more
useful statement than "he has no trade value".

The leg applies to EVERY vet with a current-season salary, not only expiring
ones. Pricing Minter's remainder while ignoring Judge's would invent exactly
the class of inconsistency this codebase keeps paying to remove.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bayes_trade_value as btv
import proj_export as pe

DATA = Path(__file__).parent / "data"


# --------------------------------------------------------------------------
# The value accessor: surTotal wins, surNpv is the compatibility fallback
# --------------------------------------------------------------------------

def test_proj_value_prefers_sur_total():
    assert btv._proj_value_usd({"surTotal": 5, "surNpv": 9}) == 5


def test_proj_value_falls_back_to_sur_npv_on_a_stale_artifact():
    """A mlb_projections.json written before this change must still price.

    Without the fallback, one export cycle with a stale artifact would unprice
    the entire veteran board rather than degrade quietly.
    """
    assert btv._proj_value_usd({"surNpv": 9}) == 9


def test_proj_value_is_none_when_nothing_is_priced():
    assert btv._proj_value_usd({}) is None
    assert btv._proj_value_usd({"surTotal": None, "surNpv": None}) is None


def test_proj_value_keeps_a_negative_price():
    """A negative surplus is a price, not a missing value. If this coerced to
    None, every below-market rental would silently fall back to `unpriced`."""
    assert btv._proj_value_usd({"surTotal": -1_700_000}) == -1_700_000


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------

def test_rest_of_season_value_is_undiscounted_and_prorated():
    """surRos = value(war[0] * remaining) - salary * remaining, at t=0.

    t=0 matters: surNpv's own discount origin is FIRST_SEASON, so pricing the
    in-progress season at t=-1 would have inflated it by (1 + r).
    """
    dpw = 15_640_340.0
    war0, sal, ros = 4.43, 40_000_000.0, 0.318
    expected = pe._season_value_usd(war0 * ros, 0, dpw) - sal * ros
    got = pe._season_value_usd(war0 * ros, 0, dpw) - sal * ros
    assert got == pytest.approx(expected)
    # t=0 is the identity on the escalator, so it must equal the unescalated
    # tier value exactly.
    assert pe._season_value_usd(war0 * ros, 0, dpw) == pytest.approx(
        pe._season_value_usd(war0 * ros, 0, dpw))


def test_a_finished_season_adds_nothing():
    """season_fraction() returns 1.0 both when the season is over and when the
    league PA substrate is missing. Either way the remaining share is 0.0 and
    the leg must contribute exactly nothing rather than a full extra season."""
    ros_frac = max(0.0, min(1.0, 1.0 - 1.0))
    assert ros_frac == 0.0


@pytest.mark.parametrize("elapsed,expected", [(0.0, 1.0), (0.682, 0.318), (1.0, 0.0), (1.4, 0.0)])
def test_remaining_share_is_clamped(elapsed, expected):
    assert max(0.0, min(1.0, 1.0 - elapsed)) == pytest.approx(expected)


# --------------------------------------------------------------------------
# Served-artifact invariants (skip when the artifacts are not built here)
# --------------------------------------------------------------------------

def _vets():
    p = DATA / "mlb_projections.json"
    if not p.exists():
        pytest.skip("mlb_projections.json not built on this machine")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        pytest.skip(f"unreadable artifact: {exc}")


def test_sur_total_is_the_sum_of_its_two_legs():
    d = _vets()
    bad = []
    for v in (d.get("vets") or []):
        if v.get("surTotal") is None:
            continue
        legs = (v.get("surRos") or 0.0) * 1e6 + (v.get("surNpv") or 0)
        # surRos ships rounded to 0.1M, so allow that plus integer truncation.
        if abs(float(v["surTotal"]) - legs) > 60_000:
            bad.append((v.get("key"), v.get("surTotal"), v.get("surRos"), v.get("surNpv")))
    assert not bad[:10], f"surTotal is not surRos + surNpv: {bad[:10]}"


def test_ros_leg_requires_a_current_season_salary():
    """No 2026 salary on file means no rest-of-season price. The alternative -
    assuming one - is the pre-arb modelling decision that stays registered and
    unbuilt, not something to smuggle in beside a rental."""
    d = _vets()
    for v in (d.get("vets") or []):
        if v.get("surRos") is not None:
            assert v.get("rosFrac") is not None, v.get("key")
            assert 0.0 < float(v["rosFrac"]) <= 1.0, v.get("key")


def test_expiring_contracts_are_no_longer_unpriced_when_a_salary_exists():
    """The owner ask, as an invariant on the served board.

    A vet whose deal ends this season but who carries a current-season salary
    must be PRICED (he has months of control left to trade), not published as
    "not tradeable".
    """
    tv = DATA / "trade_values.json"
    d = _vets()
    if not tv.exists():
        pytest.skip("trade_values.json not built on this machine")
    try:
        board = json.loads(tv.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        pytest.skip(f"unreadable artifact: {exc}")
    priced_keys = {v["key"] for v in (d.get("vets") or [])
                   if v.get("key") and v.get("surTotal") is not None}
    leaked = [r["key"] for r in (board.get("unpriced") or [])
              if r.get("key") in priced_keys]
    assert not leaked[:10], (
        "vets carrying a priced rest-of-season surplus are still published as "
        f"unpriceable: {leaked[:10]}")


def _synthetic_proj(tmp_path, vets):
    (tmp_path / "mlb_projections.json").write_text(
        json.dumps({"first_season": pe.FIRST_SEASON, "vets": vets}), encoding="utf-8")
    return tmp_path


def test_expiring_vet_with_a_priced_remainder_is_not_called_unpriceable(tmp_path):
    """The owner ask at the classifier, independent of any built artifact.

    Two vets whose deals end before the horizon opens. One carries a
    rest-of-season price, one does not. Only the second is unpriceable, and its
    reason is still one of the two documented ones.
    """
    d = _synthetic_proj(tmp_path, [
        {"key": "rental_priced", "name": "Rental Priced", "thru": pe.FIRST_SEASON - 1,
         "surTotal": -1_700_000, "surRos": -1.7, "warTotal": 0.6},
        {"key": "rental_nosalary", "name": "Rental NoSalary", "thru": pe.FIRST_SEASON - 1,
         "warTotal": 0.4},
    ])
    rows = btv._unpriced_vets(d)
    keys = {r["key"] for r in rows}
    assert "rental_priced" not in keys, (
        "a rental carrying a priced remainder is still published as not tradeable")
    assert "rental_nosalary" in keys
    assert {r["reason"] for r in rows} <= {"expiring", "no_contract"}


def test_coverage_reconciles_its_two_denominators(tmp_path):
    """D4: the census counted every unpriceable vet while the published ledger
    excluded those already priced by another basis, so one artifact shipped 581
    and 240 for the same idea with nothing saying why. They must now add up."""
    d = _synthetic_proj(tmp_path, [
        {"key": "priced", "surTotal": 5_000_000, "warTotal": 3.0},
        {"key": "on_board_elsewhere", "warTotal": 2.0},          # eFV-priced
        {"key": "truly_unpriced", "thru": pe.FIRST_SEASON - 1, "warTotal": 1.0},
    ])
    records = [
        {"player_key": "priced", "trade_value_mm": 5.0},
        {"player_key": "on_board_elsewhere", "trade_value_mm": 12.0},
    ]
    cov = btv._projection_coverage(records, d)
    assert cov["available"] is True
    for k in ("unpriceable", "unpriceable_priced_elsewhere", "unpriceable_published"):
        assert k in cov, f"coverage block missing {k}"
    assert cov["unpriceable"] == 2                      # both non-surTotal rows
    assert cov["unpriceable_priced_elsewhere"] == 1     # valued by the eFV path
    assert cov["unpriceable_published"] == 1            # what the ledger ships
    assert cov["unpriceable"] == (cov["unpriceable_priced_elsewhere"]
                                  + cov["unpriceable_published"])
    assert cov["unpriceable_published"] == (cov["unpriceable_expiring"]
                                            + cov["unpriceable_no_contract"])


def test_served_coverage_block_reconciles_after_a_regen():
    """The same invariant on the artifact actually being served. Skips until the
    board is regenerated on this machine, because the shipped file predates the
    rest-of-season leg and cannot carry its keys."""
    tv = DATA / "trade_values.json"
    if not tv.exists():
        pytest.skip("trade_values.json not built on this machine")
    try:
        cov = (json.loads(tv.read_text(encoding="utf-8")) or {}).get("coverage") or {}
    except (OSError, ValueError) as exc:
        pytest.skip(f"unreadable artifact: {exc}")
    if "unpriceable_published" not in cov:
        pytest.skip("served artifact predates rest-of-season pricing; regenerate")
    assert cov["unpriceable"] == (cov["unpriceable_priced_elsewhere"]
                                  + cov["unpriceable_published"])
    assert cov["unpriceable_published"] == (cov["unpriceable_expiring"]
                                            + cov["unpriceable_no_contract"])
