"""The club's right to decline a losing club option (owner answer VAL2-Q2,
2026-09-30).

A club option season the club would decline prices at zero, never below, so a
losing club-option season contributes max(0, surplus). Player and mutual options
are not club rights and keep their treatment. ONE rule
(salary_path.club_option_floor), applied where the surplus is priced
(proj_export), and read, never re-priced, by the trade board, the Trade Machine
and the Club Ledger; /fa/ prices a pending club option as the club's call,
which is never below zero either. Today the only curated club options are
Bobby Witt Jr.'s 2035-2037."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import bayes_trade_value as btv
import fa_market as fm
import proj_export as pe
import salary_path as sp

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _cell(season, opt=None, usd=20_000_000):
    return {"t": season - 2027, "season": season, "usd": usd, "lo": usd, "hi": usd,
            "src": "contract", "tok": "signed", "cls": None, "s2": False,
            "opt": opt, "cut": False}


# ------------------------------------------------------------ the one rule --
def test_a_losing_club_option_season_prices_at_zero_and_nothing_else_moves():
    seasons = [_cell(2027), _cell(2028, "club"), _cell(2029, "club"),
               _cell(2030, "player"), _cell(2031, "club", usd=None)]
    d = [-5e6, -7e6, 3e6, -9e6, None]
    out, declined = sp.club_option_floor(seasons, d)
    assert out == [-5e6, 0.0, 3e6, -9e6, None]
    assert declined == [2028]
    assert d == [-5e6, -7e6, 3e6, -9e6, None], "the input is not mutated"


def test_the_flag_off_is_the_d10_revert(monkeypatch):
    monkeypatch.setattr(sp, "CLUB_OPTION_DECLINE", False)
    out, declined = sp.club_option_floor([_cell(2028, "club")], [-7e6])
    assert out == [-7e6] and declined == []


def test_the_award_band_endpoints_keep_the_club_s_right():
    path = {"seasons": [_cell(2027), _cell(2028, "club", usd=60_000_000)]}
    war = [2.0, 0.1]
    dpw = 17_000_000
    lo = pe._band_npv(path, war, dpw, 0.07, "hi", False)
    first = pe._season_value_usd(2.0, 0, dpw) - 20_000_000
    assert lo == pytest.approx(first), "the losing option adds 0, never a negative"


# ------------------------------------------------------------ the consumers --
def test_fa_prices_a_pending_club_option_as_the_club_s_call():
    """/fa/: a club option far out of the money is worth about zero to the club
    and never less (fa_market.option_value_usd)."""
    pred = {"proj_aav_usd": 5_000_000, "proj_aav_p10_usd": 3_000_000,
            "proj_aav_p90_usd": 8_000_000}
    ov = fm.option_value_usd(pred, "club_option", 60_000_000)
    assert ov["held_by"] == "team" and 0 <= ov["team_value_usd"] < 1_000
    assert fm.enter_probability_v2(pred, "club_option", 60_000_000)["enter_prob"] > 0.99


def test_the_legacy_trade_compute_never_prices_a_losing_club_option_below_zero(monkeypatch):
    """bayes_trade_value._contract_surplus_mm (rows the projection does not
    re-point): a club option worth less than its price ends control and adds
    nothing, so the season prices at zero."""
    y = date.today().year
    player = {"player_key": "x_guy", "player_name": "X Guy", "age": 30,
              "position": "SS", "roster_status": {"mlb_debut_date": "2018-04-01"},
              "current_contract": {"salary_by_year": {str(y + 1): 10_000_000,
                                                      str(y + 2): 400_000_000}}}
    monkeypatch.setattr(btv, "_CONTRACT_OPTIONS_CACHE",
                        {"x_guy": {"club_options": [{"year": y + 2, "price_usd": 400_000_000}],
                                   "player_options": []}})
    with_opt = btv._contract_surplus_mm(player, 3.0, 2)
    one_year = btv._contract_surplus_mm(player, 3.0, 1)
    assert with_opt == pytest.approx(one_year)


def _j(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return json.loads(p.read_text(encoding="utf-8"))


def test_no_served_club_option_season_carries_a_negative_surplus():
    d = _j("mlb_projections.json")
    if not sp.CLUB_OPTION_DECLINE:
        pytest.skip("rule off")
    first = d["first_season"]
    n = 0
    for v in d["vets"]:
        clubs = {s for s, k in (v.get("salOpt") or []) if k == "club"}
        for s in clubs:
            t = s - first
            sur = (v.get("sur") or [])
            if t < len(sur) and sur[t] is not None:
                assert sur[t] >= 0 or s not in (v.get("salOptDecl") or []), v["key"]
                assert sur[t] >= 0, (v["key"], s, sur[t])
                n += 1
        for s in v.get("salOptDecl") or []:
            assert s in clubs and v["sur"][s - first] == 0.0, (v["key"], s)
    cen = d["accountability"]["salary_path"]["club_option_decline"]
    assert cen["enabled"] is True
    assert cen["rows"] == sum(1 for v in d["vets"] if v.get("salOptDecl"))
    assert cen["seasons"] == sum(len(v.get("salOptDecl") or []) for v in d["vets"])


def test_every_page_agrees_on_witt():
    """/projections/, the player card, the trade board (and so the Trade
    Machine) and the Club Ledger carry one Witt number and one set of declined
    seasons."""
    import ledger_export as le
    proj = {v["key"]: v for v in _j("mlb_projections.json")["vets"]}
    v = proj.get("bobby_witt_jr")
    if v is None:
        pytest.skip("Witt not on the board")
    decl = v.get("salOptDecl") or []
    first = _j("mlb_projections.json")["first_season"]
    for s in decl:
        assert v["sur"][s - first] == 0.0
    card = (_j("mlb_player_detail.json").get("players") or {}).get("bobby_witt_jr") or {}
    if card:
        assert card["proj"]["surTotal"] == v["surTotal"]
        assert (card["proj"].get("salOptDecl") or []) == decl
    tv = {p["player_key"]: p for p in _j("trade_values.json")["players"]}
    r = tv.get("bobby_witt_jr")
    assert r is not None
    assert r.get("surplus_source") == "projection"
    assert r["trade_value_mm"] == pytest.approx(v["surTotal"] / 1e6, abs=0.06)
    assert (r.get("club_option_declined") or []) == decl
    shard = DATA / "ledger_clubs" / "KCR.json"
    if not shard.exists():
        pytest.skip("ledger shard not built")
    k = json.loads(shard.read_text(encoding="utf-8"))
    cols = le.COLUMNS["contracts.paths"]
    rows = (k.get("contracts") or {}).get("paths") or []
    row = next((x for x in rows if x and x[0] == "bobby_witt_jr"), None)
    assert row is not None
    rec = dict(zip(cols, row))
    assert rec["sur_npv_usd"] == v["surNpv"] and rec["sur_mm"] == v["sur"]
    assert rec["club_opt_declined"] == decl
    assert abs(rec["npv_check_usd"] - v["surNpv"]) < 250_000


def test_the_trade_machine_names_the_declined_seasons():
    src = (ROOT / "assets" / "trademachine.js").read_text(encoding="utf-8")
    assert "p.club_option_declined" in src
    js = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert "m.salOptDecl" in js
    assert "the club's choice to decline it is not modelled" not in js
