# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The trade board must price every MLB veteran the projection system prices.

WHY THIS EXISTS. The board population is assembled from timeseries.json +
debuts.json + graduates.json, all three of which are PROSPECT-derived: a player
is in them only if this platform once tracked him as a prospect. An established
veteran who was never in our ranking coverage therefore never reached the trade
board at all, no matter how completely /projections/ modelled him.

Measured 2026-08-01, before the fix: **325 of 1,319 projected vets (24.6%) were
absent, including AARON JUDGE** ($24.6M surplus through 2031), garrett_crochet
and matt_chapman. Nothing reported it. The question that surfaced it was a user
asking why a specific reliever was missing.

The subtlety worth preserving: `apply_platform_surplus` RE-PRICES records that
exist and has no path to ADD one, so no amount of work inside that loop could
ever have fixed this. The population had to grow.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bayes_trade_value as btv

DATA = Path(__file__).parent / "data"


def _artifact(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"{name} not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


# ---- the invariant ----------------------------------------------------------

def test_every_priced_vet_is_on_the_trade_board():
    """THE regression guard. A priced vet missing from the board is a player the
    site values in one module and cannot trade in another."""
    tv = _artifact("trade_values.json")
    cov = tv.get("coverage")
    if not cov or not cov.get("available"):
        pytest.xfail("trade_values.json predates the coverage stamp - regenerate it")
    assert cov["missing"] == 0, (
        f"{cov['missing']} priced vets are absent from the trade board "
        f"(e.g. {cov.get('examples')}). The board population regressed: it is "
        f"prospect-derived, so a veteran never tracked as a prospect falls out.")


def test_coverage_block_is_stamped_into_the_artifact():
    """A log line nobody reads is not a guard. The number rides in the data."""
    tv = _artifact("trade_values.json")
    cov = tv.get("coverage")
    if not cov:
        pytest.xfail("trade_values.json predates the coverage stamp")
    for k in ("vets", "priced_vets", "priced_on_board", "missing",
              "unpriceable", "unpriceable_expiring", "unpriceable_no_contract"):
        assert k in cov, f"coverage block missing {k}"
    assert cov["priced_on_board"] + cov["missing"] == cov["priced_vets"]


def test_unpriceable_vets_are_published_with_a_reason():
    """The remainder is NOT silently dropped: a real major-leaguer must never
    return nothing from search just because he has no surplus to trade."""
    tv = _artifact("trade_values.json")
    if "unpriced" not in tv:
        pytest.xfail("trade_values.json predates the unpriced block")
    rows = tv["unpriced"]
    assert rows, "no unpriceable vets published at all - suspicious"
    for r in rows[:50]:
        assert r.get("key") and r.get("reason") in ("expiring", "no_contract")


def test_no_unpriceable_vet_leaked_into_the_valued_board():
    """They are published for SEARCH, not for the value ranking. A null-valued
    row inside players[] would sort to the bottom of every board."""
    tv = _artifact("trade_values.json")
    if "unpriced" not in tv:
        pytest.xfail("trade_values.json predates the unpriced block")
    board = {p["player_key"] for p in tv["players"] if p.get("player_key")}
    for r in tv["unpriced"]:
        assert r["key"] not in board, f"{r['key']} is both unpriced and on the board"


# ---- the mechanism ----------------------------------------------------------

def test_projection_only_rows_price_on_the_projection_basis():
    """Added vets must be indistinguishable in BASIS from an MLB row that was
    always there: value = surNpv, source = "projection", eFV bands null.
    Inventing an FV to get a player onto a board is the defect class this repo
    has removed twice (BA-statcast FV-40, performance_ingest FV-35)."""
    proj = _artifact("mlb_projections.json")
    proj_sur = {v["key"]: v["surNpv"] / 1e6
                for v in proj.get("vets") or []
                if v.get("key") and v.get("surNpv") is not None}
    if not proj_sur:
        pytest.skip("no priced vets in the projection artifact")
    records: list[dict] = []
    n = btv._append_projection_only_rows(records, proj_sur, {}, {}, DATA)
    assert n == len(records) == len(proj_sur)
    for r in records:
        assert r["surplus_source"] == "projection"
        assert r["board_entry"] == "projection_only"
        assert r["trade_value_lo"] is None and r["trade_value_hi"] is None
        # tolerance is the ONE-DECIMAL rounding half-width from bayes_trade_value.py:3671
        # (`round(..., 1)`), plus float slack. At exactly 0.05 a projection landing on a
        # .X5 boundary fails on representation alone: the eWAR label epoch moved a vet to
        # -1.25, which rounds to -1.2, and -1.2 - -1.25 evaluates to 0.05000000000000004.
        # That is the float, not the code, so the fix is one slack step rather than a
        # looser gate.
        assert r["trade_value_mm"] == pytest.approx(
            proj_sur[r["player_key"]], abs=0.05 + 1e-9)
        assert r["trade_value_grade"] and r["trade_value_tier"]
        assert "fv" not in r and "xfv_grade" not in r, "no grade may be invented"


def test_existing_rows_are_never_duplicated():
    """The seeder must skip anyone already on the board, or a star appears twice."""
    proj = _artifact("mlb_projections.json")
    vets = [v for v in proj.get("vets") or [] if v.get("surNpv") is not None]
    if not vets:
        pytest.skip("no priced vets")
    proj_sur = {v["key"]: v["surNpv"] / 1e6 for v in vets}
    existing = [{"player_key": vets[0]["key"], "trade_value_mm": 1.0}]
    n = btv._append_projection_only_rows(existing, proj_sur, {}, {}, DATA)
    assert n == len(proj_sur) - 1
    keys = [r["player_key"] for r in existing]
    assert len(keys) == len(set(keys))


def test_unpriceable_split_is_the_two_documented_reasons():
    """expiring = contract ends before the horizon opens (a pending free agent
    is not a trade asset); no_contract = nothing on file to subtract from value.
    A.J. Minter is the canonical `expiring` case - the question that started
    this - and his absence from the VALUED board is correct."""
    rows = btv._unpriced_vets(DATA)
    if not rows:
        pytest.skip("no projection artifact on this machine")
    assert {r["reason"] for r in rows} <= {"expiring", "no_contract"}
    proj = _artifact("mlb_projections.json")
    first = proj.get("first_season")
    for r in rows:
        if r["reason"] == "expiring":
            assert r["thru"] is not None and r["thru"] < first
        else:
            assert r["thru"] is None or r["thru"] >= first


def test_coverage_is_computed_off_valued_rows_only():
    """A row carrying a null trade value does not count as covered - that is how
    the inactive-drop path leaves players, and it must not mask a gap."""
    cov = btv._projection_coverage(
        [{"player_key": "x", "trade_value_mm": None}], DATA)
    if not cov.get("available"):
        pytest.skip("no projection artifact")
    assert cov["missing"] == cov["priced_vets"], (
        "a null-valued row was counted as board coverage")
