# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xM$ export (XM_2_EXPORT_ROLLUPS_DARK): the pure pieces, the flags, the dark
consumers and the served invariants of data/xm_players.json and
data/xm_clubs.json.

Served invariants: no NaN and no missing point, P10 <= P50 <= P90 on years, AAV
and the guarantee, the counterfactual flag false exactly on the free-agent rows,
every priced row in at most one club block, and every club figure equal to the
sum of its listed player rows (roster, market-rate surplus, farm, and each
Fair $ counterpart). Nothing here reads or computes anything by consensus FV.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

import xm_export as X

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


# ---------------------------------------------------------------------------
# pure pieces
# ---------------------------------------------------------------------------
def test_prospect_path_follows_the_gate_section_11_rule():
    p = X.prospect_path(6.0, 2029, 21, 2027, n_years=15)
    assert p[:2] == [0.0, 0.0]                     # before the ETA season
    assert p[2:8] == [1.0] * 6                     # six seasons at war_6yr / 6
    # held until age 30: season 2027 + t at age 21 + t; t = 9 is age 30
    assert p[9] == 1.0
    assert p[10] == 0.5 and p[11] == 0.0 and p[14] == 0.0
    # no ETA or a past ETA starts in the class season; negative WAR floors at 0
    assert X.prospect_path(3.0, None, 25, 2027)[0] == 0.5
    assert X.prospect_path(3.0, 2020, 25, 2027)[0] == 0.5
    assert set(X.prospect_path(-2.0, 2027, 25, 2027)) == {0.0}


def test_clip_scales_down_and_flags_but_never_scales_up():
    box = {"age": [24.0, 44.0], "war_y1": [0.0, 6.0], "war_tot": [0.0, 40.0]}
    a, wy, f, out = X.clip_to_support(20, [1.0, 1.0], box)
    assert (a, wy, f, out) == (24.0, [1.0, 1.0], 1.0, True)
    a, wy, f, out = X.clip_to_support(28, [8.0] + [4.0] * 9, box)
    assert out and f == pytest.approx(min(6.0 / 8.0, 40.0 / 44.0))
    assert wy[0] <= 6.0 + 1e-9 and sum(wy) <= 40.0 + 1e-9
    a, wy, f, out = X.clip_to_support(30, [2.0, 2.0], box)
    assert (a, wy, f, out) == (30.0, [2.0, 2.0], 1.0, False)
    a, wy, f, out = X.clip_to_support(30, [-1.0, 0.5], box)
    assert out and wy == [-1.0, 0.5]                # below the floor: flagged, kept


def test_ordered_band():
    assert X.ordered_band(5, 3, 1) == (3, 3, 3)
    assert X.ordered_band(1, 3, 5) == (1, 3, 5)
    assert X.ordered_band(None, 3, None) == (3, 3, 3)


def test_control_surplus_is_the_registered_sum():
    aav, sal = 10e6, [1e6, 2e6]
    idx, disc = [1.0, 1.05], [1.0, 1 / 1.07]
    fair = [8e6, 7e6]
    xm, fr = X.control_surplus(aav, sal, fair, idx, disc)
    assert xm == round((10e6 - 1e6) + (10e6 * 1.05 - 2e6) / 1.07)
    assert fr == round((8e6 - 1e6) + (7e6 - 2e6 / 1.07))
    assert X.control_surplus(aav, [], fair, [], [])[0] == 0


# ---------------------------------------------------------------------------
# flags, writer and the dark consumers
# ---------------------------------------------------------------------------
def test_flags_ship_data_only():
    assert X.XM_EXPORT_ON is True
    assert X.XM_DISPLAY_ON is False


def test_the_writer_goes_to_preview_while_export_is_off(monkeypatch, tmp_path):
    monkeypatch.setattr(X, "XM_EXPORT_ON", False)
    monkeypatch.setattr(X, "PREVIEW_DIR", tmp_path / "preview")
    monkeypatch.setattr(X, "OUT_PLAYERS", tmp_path / "data" / "xm_players.json")
    monkeypatch.setattr(X, "OUT_CLUBS", tmp_path / "data" / "xm_clubs.json")
    paths = X.write({"a": 1}, {"b": 2})
    assert all(Path(p).parent == tmp_path / "preview" for p in paths)
    assert not (tmp_path / "data").exists()


def test_club_blocks_read_nothing_while_display_is_off(monkeypatch, tmp_path):
    assert X.club_blocks(tmp_path) is None
    doc = {"as_of": "2026-10-22", "model_id": "fa_market", "clubs": {"AAA": {
        "roster": {"n": 1, "xm_aav_usd": 5, "ids": ["1"]},
        "market_surplus": {"n": 0, "xm_usd": 0, "ids": []},
        "farm": {"n": 0, "xm_total_usd": 0, "ids": []}}}}
    (tmp_path / "xm_clubs.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(X, "XM_DISPLAY_ON", True)
    blk = X.club_blocks(tmp_path)
    assert blk["AAA"]["roster"] == {"n": 1, "xm_aav_usd": 5}
    assert "ids" not in blk["AAA"]["farm"] and blk["AAA"]["model_id"] == "fa_market"


@pytest.mark.parametrize("mod", ["ledger_export.py", "franchise_export.py"])
def test_the_boards_attach_the_block_only_through_the_flagged_reader(mod):
    src = (ROOT / mod).read_text(encoding="utf-8")
    assert src.count("_xm.club_blocks(DATA)") == 1
    assert '["xm"] = _xmb[' in src


def test_the_served_boards_carry_no_xm_block_while_dark():
    for name, get in (("ledger_board.json", lambda d: d["clubs"].values()),
                      ("franchise_board.json", lambda d: d["clubs"])):
        p = DATA / name
        if not p.is_file():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        assert not any("xm" in c for c in get(doc)), name


# ---------------------------------------------------------------------------
# served artifacts
# ---------------------------------------------------------------------------
def _served():
    pp, pc = DATA / "xm_players.json", DATA / "xm_clubs.json"
    if not (pp.is_file() and pc.is_file()):
        pytest.skip("xm_players.json / xm_clubs.json not built")
    players = json.loads(pp.read_text(encoding="utf-8"))
    clubs = json.loads(pc.read_text(encoding="utf-8"))
    cols = players["columns"]
    rows = {k: dict(zip(cols, v)) for k, v in players["players"].items()}
    return players, clubs, rows


def test_served_rows_have_points_and_ordered_bands():
    players, _, rows = _served()
    assert players["columns"] == X.COLUMNS and players["n"] == len(rows) > 0
    for k, r in rows.items():
        for c in ("years", "aav", "total", "fair", "years_p10", "years_p90", "aav_p10",
                  "aav_p90", "total_p10", "total_p90"):
            v = r[c]
            assert isinstance(v, int) and not (isinstance(v, float) and math.isnan(v)), (k, c)
        assert 1 <= r["years_p10"] <= r["years"] <= r["years_p90"], k
        assert r["aav_p10"] <= r["aav"] <= r["aav_p90"], k
        assert r["total_p10"] <= r["total"] <= r["total_p90"], k
        assert r["aav"] > 0 and r["total"] > 0, k


def test_served_flags_and_keys():
    players, _, rows = _served()
    assert players["model_id"] == "fa_market" and players["fair_model_id"] == "fa_rational_value"
    assert players["class_year"] == 2027 and players["display_on"] is False
    for k, r in rows.items():
        assert r["pop"] in ("fa", "mlb", "prospect"), k
        assert r["cf"] is (r["pop"] != "fa"), k
        assert isinstance(r["clip"], bool), k
        if r["pop"] in ("fa", "mlb"):
            assert k == str(r["mlbam"]) and r["on40"] is True, k
        else:
            assert k == r["key"], k
        assert r["bucket"] in ("roster", "farm", "fa"), k
        if r["msur_xm"] is not None:
            assert r["bucket"] == "roster" and r["ctrl"] > 0 and r["msur_fair"] is not None, k
    # the support-clip report is by population only (docs/PROSPECT_ANCHOR_GATE.md)
    assert set(players["support_clip_by_population"]) <= {"fa", "mlb", "prospect"}


def test_free_agent_rows_copy_the_fa_class_board():
    players, _, rows = _served()
    fa = json.loads((DATA / "fa_class.json").read_text(encoding="utf-8"))
    if (players.get("inputs_generated_at") or {}).get("fa_class") != fa.get("generated_at"):
        pytest.skip("fa_class.json was rebuilt after the xM$ export")
    by = {str(m["mlbam"]): m for m in fa["members"] if m.get("mlbam")}
    n = 0
    for k, r in rows.items():
        if r["pop"] != "fa":
            continue
        m = by[k]
        assert (r["years"], r["aav"], r["total"], r["fair"]) == (
            m["projYears"], m["projAav"], m["projGuar"], m["rational"]), k
        n += 1
    assert n > 0


def test_every_club_figure_is_the_sum_of_its_rows():
    _, clubs, rows = _served()
    seen = set()
    for c, cd in clubs["clubs"].items():
        ro, ms, fm = cd["roster"], cd["market_surplus"], cd["farm"]
        for blk in (ro, fm):
            assert not (set(blk["ids"]) & seen), c
            seen |= set(blk["ids"])
        assert set(ms["ids"]) <= set(ro["ids"]), c
        for k in ro["ids"] + fm["ids"]:
            assert rows[k]["club"] == c, (c, k)
        assert ro["n"] == len(ro["ids"]) and fm["n"] == len(fm["ids"]) and ms["n"] == len(ms["ids"])
        assert all(rows[k]["bucket"] == "roster" for k in ro["ids"]), c
        assert all(rows[k]["bucket"] == "farm" for k in fm["ids"]), c
        assert ro["xm_aav_usd"] == sum(rows[k]["aav"] for k in ro["ids"]), c
        assert ro["fair_aav_usd"] == sum(round(rows[k]["fair"] / max(rows[k]["years"], 1))
                                         for k in ro["ids"]), c
        assert ms["xm_usd"] == sum(rows[k]["msur_xm"] for k in ms["ids"]), c
        assert ms["fair_usd"] == sum(rows[k]["msur_fair"] for k in ms["ids"]), c
        assert ms["seasons"] == sum(rows[k]["ctrl"] for k in ms["ids"]), c
        assert fm["xm_aav_usd"] == sum(rows[k]["aav"] for k in fm["ids"]), c
        assert fm["xm_total_usd"] == sum(rows[k]["total"] for k in fm["ids"]), c
        assert fm["fair_usd"] == sum(rows[k]["fair"] for k in fm["ids"]), c
        # every roster row with a priced control window is in the surplus sum
        assert set(ms["ids"]) == {k for k in ro["ids"] if rows[k]["msur_xm"] is not None}, c
    # every roster and farm row is in its club's block
    assert seen == {k for k, r in rows.items() if r["bucket"] in ("roster", "farm")}
    assert len(clubs["clubs"]) == clubs["n_clubs"] == 30
