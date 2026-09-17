# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The ask-C blast radius, ASSERTED rather than believed
(docs/ARBITRATION_GATE.md section 11f).

The control-window salary path moves about $8.8B of served surplus and
re-orders the trade board. Everything in section 11f prices through a
DIFFERENT path and must be untouched by it. "Must not move" is only worth
something if a test can fail on it, so each item here is an assertion:

  * /arbitration/'s published `tot`, `l` ladder and `ou_war` - class closure
    lives in salary_path.py and build_board is untouched (decision D3);
  * projection rows whose whole control window is contracted;
  * the veterans with no board row and no contract, unpriced before and after;
  * every prospect row, on the projection board and on the trade board;
  * /fa/ Contract Surplus, farm surplus, Sur+, OrgSur+, Grad-Contract Surplus
    and every eFV number - they price through value_framework, which this
    change does not enter.

The last family is asserted as an IMPORT-GRAPH invariant, not as a pinned
number: a pinned dollar figure goes stale on the next nightly and starts
failing for the wrong reason, while "value_framework never learns about the
salary path" is the property that actually makes the claim true and stays
checkable forever.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _doc(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"data/{name} not built")
    return json.loads(p.read_text("utf-8"))


def _vets():
    return [v for v in (_doc("mlb_projections.json").get("vets") or []) if v.get("key")]


# --------------------------------------------------------------- /arbitration/
def test_the_board_total_is_its_own_ladder_and_nothing_else():
    """`tot` means "remaining arbitration cost on Spotrac's grid". If class
    closure had been implemented in arb_export.build_board instead of in
    salary_path.py, this number would have silently grown by 467 seasons across
    245 rows. Decision D3 is why it did not, and this is the assertion."""
    board = _doc("arbitration.json")
    bad = []
    for r in board.get("rows") or []:
        own = sum(s[1] or 0 for s in (r.get("l") or []))
        if (r.get("tot") or 0) != own:
            bad.append((r.get("n"), r.get("tot"), own))
    assert not bad, f"tot disagrees with its own ladder on {len(bad)} rows: {bad[:3]}"


def test_the_board_never_learns_about_the_salary_path():
    """The one-line structural guarantee behind the three /arbitration/ numbers.
    arb_export must not import salary_path, or `tot`, `l` and `ou_war` stop
    being what their field_key says they are."""
    src = (ROOT / "arb_export.py").read_text("utf-8")
    assert "salary_path" not in src
    assert "import salary_path" not in src


def test_the_board_publishes_no_surplus_and_no_cut():
    """`ou_war` is a VALUE residual and is deliberately never combined with the
    model residual. The salary path must not have introduced a third."""
    board = _doc("arbitration.json")
    for key in ("sur", "surNpv", "surTotal", "salPath", "salCut"):
        assert key not in (board.get("field_key") or {})
    for r in (board.get("rows") or [])[:50]:
        assert not set(r) & {"sur", "surNpv", "surTotal", "salPath", "salCut"}


# ------------------------------------------------------- contracted windows
def test_a_window_the_contract_prices_end_to_end_takes_nothing_from_the_path():
    """The 135 rows signed through 2028 or later measured an add of exactly $0.
    The rule behind that number: where a row's whole priced window is
    `contract`, no season of it may carry an arbitration source."""
    bad = []
    for v in _vets():
        path = v.get("salPath") or []
        if not path:
            continue
        srcs = {s[5] for s in path}
        if srcs == {"contract"}:
            assert v.get("salSrc") in ("contract", "contract+arb"), v["key"]
            if v.get("salCut") is not None:
                bad.append(v["key"])         # a guaranteed season is never cuttable
    assert not bad, f"the tender cliff fired on an all-contract window: {bad[:5]}"


def test_a_contracted_season_never_carries_an_arbitration_token():
    """Rule 1, on the served payload: a season a contract prices reads
    src "contract" and token "signed", whatever the status grid says."""
    for v in _vets():
        for s in v.get("salPath") or []:
            if s[5] == "contract":
                assert s[4] == "signed", (v["key"], s)
                assert s[2] == s[1] == s[3], (v["key"], s)   # dollars, not a band


# ---------------------------------------------------------- unpriced veterans
def test_an_unpriced_vet_is_still_unpriced_and_now_says_so():
    """The veterans with no board row and no contract stay at no price. What
    changed for them is a DISCLOSURE, not a number: salSrc "pending"."""
    for v in _vets():
        if v.get("salSrc") != "pending":
            continue
        assert v.get("surNpv") is None and v.get("surTotal") is None, v["key"]
        assert not v.get("salPath") and v.get("salThru") is None


# ----------------------------------------------------------------- prospects
def test_no_prospect_row_is_arb_priced_on_either_board():
    """GATE C's C6 clause, carried forward. A never-debuted player has no prior
    salary for the award model to raise off; docs/ARBITRATION_GATE.md section 6
    keeps the clemens_2026 ladder for him on purpose."""
    proj = _doc("mlb_projections.json")
    for p in proj.get("prospects") or []:
        for k in ("salPath", "salThru", "salCut", "salTrunc", "salSrc"):
            assert p.get(k) is None, (p.get("key"), k)
    tv = _doc("trade_values.json")
    for r in tv.get("players") or []:
        if r.get("surplus_source") in ("xfv", "xfv_backgrade"):
            assert r.get("salary_basis") is None, r.get("player_key")


# -------------------------------------------------- value_framework consumers
VF_CONSUMERS = ("value_framework.py", "efv_score.py", "efv_export.py",
                "fa_market.py", "fa_export.py", "fa_class.py")


def test_the_value_framework_side_of_the_house_never_reads_the_salary_path():
    """/fa/ Contract Surplus, farm surplus, Sur+, OrgSur+, Grad-Contract
    Surplus and every eFV number price through value_framework. This change
    does not enter it, and this is what makes that sentence checkable."""
    missing = []
    for name in VF_CONSUMERS:
        p = ROOT / name
        if not p.exists():
            missing.append(name)
            continue
        src = p.read_text("utf-8")
        assert not re.search(r"^\s*import\s+salary_path", src, re.M), name
        assert not re.search(r"from\s+salary_path\s+import", src), name
        assert "salPath" not in src, name
    assert not missing, f"expected consumers are gone: {missing}"


def test_the_prospect_ladder_and_the_salary_path_stay_two_named_things():
    """Decision D6: keep both, document the seam. Measured, the two differ by a
    median -$2.6M and up to $84M on stars, so a silent merge would move every
    prospect price."""
    src = (ROOT / "salary_path.py").read_text("utf-8")
    assert "clemens_2026" in src and "never prices a never-debuted prospect" in src


# ------------------------------------------------------------ the flag itself
def test_the_revert_is_one_constant():
    """docs/ARBITRATION_GATE.md section 11e turns every failing clause into a
    value of this constant. It has to exist, be one of the four, and be the one
    the owner ordered."""
    import salary_path as sp
    assert sp.MODES == ("off", "ladder", "closure", "full")
    assert sp.SALARY_PATH_MODE == "full"


def test_the_served_payload_stamps_the_board_it_priced_off():
    """R6/decision D9: there is no ordering bug to fix, so the cadence is
    DISCLOSED instead of re-plumbed. A payload that cannot say which board it
    read is a payload nobody can check."""
    proj = _doc("mlb_projections.json")
    board = _doc("arbitration.json")
    cen = ((proj.get("accountability") or {}).get("salary_path") or {})
    if not cen:
        pytest.skip("payload predates the salary-path census")
    assert cen.get("vintage") == board.get("generated_at")
    assert proj.get("generated_at") >= board.get("generated_at")
    for v in _vets():
        if v.get("salPath"):
            assert v.get("salVintage") == board.get("generated_at"), v["key"]


def test_the_census_reconciles_with_the_rows_it_describes():
    """A census nobody checks is a claim. This one has to add up."""
    proj = _doc("mlb_projections.json")
    cen = ((proj.get("accountability") or {}).get("salary_path") or {})
    if not cen or cen.get("mode") == "off":
        pytest.skip("salary path is off or the census predates it")
    vets = _vets()
    seasons = {}
    for v in vets:
        for s in v.get("salPath") or []:
            seasons[s[5]] = seasons.get(s[5], 0) + 1
    assert cen["salary_path_seasons"] == dict(sorted(seasons.items()))
    assert cen["cliff_rows"] == sum(1 for v in vets if v.get("salCut") is not None)
    trunc = {}
    for v in vets:
        if v.get("salTrunc"):
            trunc[v["salTrunc"]] = trunc.get(v["salTrunc"], 0) + 1
    assert cen["truncated"] == dict(sorted(trunc.items()))


def test_class_closure_actually_ran_on_the_served_artifact():
    """CLOSURE CAN NO-OP IN SILENCE, and it prices 467 seasons on 245 rows -
    17.8% of the money this change adds.
    `salary_path.board_raise_fn()` builds a panel and fits a deflator plus the
    banded multipliers; on any exception it caches "unavailable" and returns
    None, every row closes to [], and the only trace used to be one census
    string nothing asserted. proj_export now raises rather than serving the
    short window, and this is the assertion on the ARTIFACT that says the raise
    actually happened."""
    proj = _doc("mlb_projections.json")
    cen = ((proj.get("accountability") or {}).get("salary_path") or {})
    if not cen:
        pytest.skip("payload predates the salary-path census")
    if cen.get("mode") not in ("closure", "full"):
        pytest.skip("class closure is not part of the served mode")
    assert cen.get("closure_estimator") == "fitted", cen.get("closure_estimator")
    assert (cen.get("salary_path_seasons") or {}).get("class_closure", 0) > 0
    assert (cen.get("salary_path_rows") or {}).get("class_closure", 0) > 0


def test_no_contract_reached_a_row_without_reaching_the_salary_path():
    """RULE 1, COUNTED. `_resolve_contracts` deliberately leaves a CONTESTED
    Spotrac key out of the assigned map and the collision-winner loop applies it
    afterwards, so handing the assigned map to the path pass showed it ct=None
    for exactly the row that had just taken a contract: rule 1's second lock off
    and the board grid free to price a season the contract already buys.
    `rule1_repairs` is the count of seasons a contract priced that the path did
    not return as `contract`. It has to be empty."""
    proj = _doc("mlb_projections.json")
    cen = ((proj.get("accountability") or {}).get("salary_path") or {})
    if not cen or cen.get("mode") == "off":
        pytest.skip("salary path is off or the census predates it")
    assert cen.get("rule1_repairs") == [], cen.get("rule1_repairs")


def test_the_published_band_brackets_the_published_surplus():
    """THE PAIR EVERY SURFACE PRINTS TOGETHER. `surSalLo`/`surSalHi` sit beside
    `surTotal` in the board detail line, under the player-card Surplus tile and
    in the trade row's `surplus_salary_band_mm` beside `trade_value_mm`. A band
    over the projected seasons alone left 69 of 307 band rows with a headline
    surplus ABOVE the top of its own published band. The invariant is asserted
    on the SERVED pair, not on the intermediate the surfaces do not show."""
    bad = []
    for v in _vets():
        lo, hi, tot = v.get("surSalLo"), v.get("surSalHi"), v.get("surTotal")
        if lo is None or hi is None or tot is None:
            continue
        if not (lo <= hi and lo <= tot <= hi):
            bad.append((v["key"], lo, tot, hi))
    assert not bad, f"the award band does not bracket the surplus it is printed beside: {bad[:5]}"


def test_the_service_time_field_cannot_move_a_prediction():
    """`sv`/`svy` exist so a lab can say how old its evidence is. They are not
    features: nothing in arb_model reads them, so populating them cannot move
    the board's `l` or `tot`. Measured the hard way as well - arb_export was run
    with and without the arb_dataset change and 0 of 852 rows moved on either
    field - but the property that stays true is this one."""
    import arb_model
    keys = set(arb_model.CHAMPION_KEYS) | set(arb_model.CEILING_KEYS)
    assert "service_time" not in keys
    assert "service_years" not in keys
    assert "svy" not in keys
