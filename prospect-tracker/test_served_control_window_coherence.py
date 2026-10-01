# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""THE cross-module invariant, stated once (owner report 2026-09-17):

    No surface may show a control horizon shorter than the last season its own
    surplus prices, for any row.

Measured on the served artifacts the morning this was written, BEFORE the
change: the first assertion failed on 481 of 1,383 projection rows, and the
free-agency-year assertion failed on 30 of 77 joinable trade rows. After it,
both are 0 by construction.

This runs against SERVED artifacts, not fixtures, and it belongs in the nightly
as well as in CI: it catches a regen that changes the population as surely as it
catches a code change. It is written as a PROPERTY and pins no counts, because
the counts move by a few dozen rows every regen pass (`salThru > thru` read 535
then 561 across two passes on one afternoon) and a pinned count would start
failing for the wrong reason.

Standing operational rule: do NOT run this while run_monthly.py is writing
data/ - the conftest guard reverts the regen's writes.
"""
from __future__ import annotations

import json
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


def _priced_end(v):
    """The last season this row's SURPLUS actually prices: the last salPath
    season the tender cliff did not cut. A cut season carries a price the club
    is projected never to pay, so it is not what the surplus rests on."""
    best = None
    for st in v.get("salPath") or []:
        if len(st) > 6 and st[6]:
            continue
        s = int(st[0])
        best = s if best is None or s > best else best
    return best


# ------------------------------------------------------ /projections/ --------
def test_no_projection_row_shows_a_horizon_shorter_than_its_own_money():
    bad = []
    for v in _vets():
        end = _priced_end(v)
        if end is None:
            continue
        ct = v.get("ctrlThru")
        if ct is None or ct < end:
            bad.append((v["key"], ct, end, v.get("surTotal")))
    assert not bad, (
        f"{len(bad)} rows print a control end before the last season their own "
        f"surplus prices: {bad[:5]}")


def test_the_control_end_is_the_max_of_the_two_facts_on_every_row():
    """`ctrlThru` is derived, once, in salary_path.control_end. Any row where it
    is not max(thru, salThru) means a consumer re-derived it, which is the
    failure mode that gave this site five answers to one question."""
    bad = [(v["key"], v.get("thru"), v.get("salThru"), v.get("ctrlThru"))
           for v in _vets()
           if (v.get("thru") is not None or v.get("salThru") is not None)
           and v.get("ctrlThru") != max(v.get("thru") or 0, v.get("salThru") or 0)]
    assert not bad, bad[:5]


# ------------------------------------------------------ the player card ------
# Every key mlb_player_export copies VERBATIM from the board row
# (mlb_player_export.build_payload). M05-08 (2026-09-24): after a standalone
# --rebuild-only the card sat one vintage behind the board on 143 surplus rows
# and one control window, and a check over the four ctrl keys alone saw only
# the one row.
_CARD_COPY_KEYS = ("war", "warP10", "warP90", "warTotal", "warTotalP10",
                   "warTotalP90", "sur", "surNpv", "surTotal", "surRos", "rosWar",
                   "rosFrac", "salPath", "salThru", "salSrc", "surSalLo",
                   "surSalHi", "salCut", "salTrunc", "salOpt", "salOptDecl", "salVintage",
                   "ctrlThru", "ctrlOpen", "ctrlEst", "ctrlWhy", "thru", "aav",
                   "warHit", "warPit", "warTail", "warP10Tail", "warP90Tail")


def test_the_card_copy_list_is_the_one_the_exporter_uses():
    """The key list above has to be the exporter's list, or the agreement test
    below silently stops covering a field the card prints."""
    import ast
    src = (ROOT / "mlb_player_export.py").read_text(encoding="utf-8")
    lists = [tuple(ast.literal_eval(n)) for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Tuple) and n.elts
             and all(isinstance(e, ast.Constant) for e in n.elts)
             and "surTotal" in [e.value for e in n.elts]
             and "ctrlThru" in [e.value for e in n.elts]]
    assert lists, "no verbatim copy tuple found in mlb_player_export.py"
    assert set(lists[0]) == set(_CARD_COPY_KEYS)


def test_a_standalone_rebuild_rebakes_the_player_cards(monkeypatch):
    """`run_monthly.py --rebuild-only` re-writes the board, so it must also
    re-bake the cards that copy it; before M05-08 only the nightly d9b2 did."""
    import mlb_player_export
    import run_monthly
    calls = []
    monkeypatch.setattr(run_monthly, "rebuild_only",
                        lambda out_dir=None, **kw: calls.append("board"))
    monkeypatch.setattr(mlb_player_export, "export", lambda: calls.append("cards"))
    run_monthly.rebuild_only_cli(out_dir=Path("unused"))
    assert calls == ["board", "cards"]


def test_the_card_and_the_board_agree_on_every_row():
    """mlb_player_export copies the salary block VERBATIM and the control keys
    ride in the same copy list. The moment it starts deriving one, the card and
    the board can disagree about one player's window."""
    det = _doc("mlb_player_detail.json").get("players") or {}
    by_key = {v["key"]: v for v in _vets()}
    bad = []
    for key, p in det.items():
        v = by_key.get(key)
        if v is None:
            continue
        pr = p.get("proj") or {}
        for k in _CARD_COPY_KEYS:
            if (pr.get(k) or None) != (v.get(k) or None):
                bad.append((key, k, pr.get(k), v.get(k)))
    assert not bad, (
        f"{len(bad)} card keys differ from the board (a board re-bake the card "
        f"never followed?): {bad[:5]}")


# ------------------------------------------------------ /trademachine/ -------
def test_the_trade_board_never_prints_a_shorter_window_than_it_prices():
    tv = _doc("trade_values.json")
    bad_thru, bad_fa = [], []
    for r in tv.get("players") or []:
        st = r.get("salary_thru")
        ct = r.get("control_thru")
        if st is None:
            continue
        if ct is None or ct < st:
            bad_thru.append((r.get("player_key"), ct, st))
        fa = (r.get("contract") or {}).get("fa_year")
        if fa is not None and ct is not None and fa <= ct:
            bad_fa.append((r.get("player_key"), fa, ct))
    assert not bad_thru, bad_thru[:5]
    assert not bad_fa, (
        f"{len(bad_fa)} trade rows print a free agency year at or before the "
        f"season the same row prices as controlled: {bad_fa[:5]}")


def test_the_two_boards_agree_on_every_player_they_share():
    tv = _doc("trade_values.json")
    by_key = {v["key"]: v for v in _vets()}
    bad = []
    for r in tv.get("players") or []:
        v = by_key.get(r.get("player_key"))
        if v is None or r.get("control_thru") is None:
            continue
        if r["control_thru"] != v.get("ctrlThru"):
            bad.append((r.get("player_key"), r["control_thru"], v.get("ctrlThru")))
    assert not bad, bad[:5]


# ------------------------------------------------------ /arbitration/ --------
def test_the_arbitration_board_states_no_control_end():
    """The board publishes the grid it was given. It cannot derive a free agency
    year from a grid that ends on a PRE-ARB token on more than half its rows, so
    it names none - decision D3 keeps class closure out of build_board, so the
    page does not know, so it must not say."""
    board = _doc("arbitration.json")
    keys = set(board.get("field_key") or {})
    for k in ("fa_year", "control_thru", "ctrlThru", "salThru"):
        assert k not in keys, k
    for r in board.get("rows") or []:
        for k in ("fa", "fa_year", "ctrlThru", "control_thru"):
            assert k not in r, (r.get("n"), k)


# ---------------------------------------------------------------- /fa/ -------
def test_a_class_member_priced_controlled_past_his_class_year_is_flagged():
    """Class membership is SCRAPED from Spotrac and never consults the
    arbitration board. This does not move membership; it asserts that where the
    two sources disagree, the row SAYS so."""
    cls = _doc("fa_class.json")
    cy = cls.get("class_year")
    if cy is None:
        pytest.skip("fa_class.json carries no class_year")
    by_key = {v["key"]: v for v in _vets()}
    bad = []
    for m in cls.get("members") or []:
        v = by_key.get(m.get("key"))
        if not v:
            continue
        ct, est = v.get("ctrlThru"), v.get("ctrlEst")
        if ct is not None and ct > cy and est and not m.get("ctrlFlag"):
            bad.append((m.get("key"), ct, cy))
    assert not bad, (
        "class members the arbitration board prices under club control past the "
        f"class year, published with no acknowledgement: {bad[:5]}")
