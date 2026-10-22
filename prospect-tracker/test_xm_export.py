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

Gate section 16 (task XM_2C_PROSPECT_FAIR_ONLY, owner answers XM2B-Q1 and
XM2-Q2): a prospect shows Fair $ only, the NPV of his eFV WAR path at the
market rate with no reach weight, and his xM$ is withheld (every xM$ column
null); the farm block holds every board prospect and carries Fair $ only,
reconciled to its rows; the Ledger is handed the roster and farm blocks only,
so the Club Ledger never-list holds.
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


def test_arrival_year_is_the_eta_and_never_before_the_winter():
    assert X.arrival_year(2029, 2027) == 2029
    assert X.arrival_year(2025, 2027) == 2027
    assert X.arrival_year(None, 2027) == 2027


def test_prospect_fair_is_the_linear_npv_of_the_path_with_no_reach_weight():
    wy = [0.0, 1.0, 2.0]
    idx, disc = [1.0, 1.04, 1.04 ** 2], [1.0, 1 / 1.07, 1 / 1.07 ** 2]
    dpw = 10_000_000
    assert X.prospect_fair_usd(wy, dpw, idx, disc) == round(
        dpw * (1.0 * 1.04 / 1.07 + 2.0 * 1.04 ** 2 / 1.07 ** 2))
    # linear in WAR (no tier curve on an expectation): twice the path, twice the value
    assert abs(X.prospect_fair_usd([2 * w for w in wy], dpw, idx, disc)
               - 2 * X.prospect_fair_usd(wy, dpw, idx, disc)) <= 1
    assert X.prospect_fair_usd([0.0] * 3, dpw, idx, disc) == 0
    with pytest.raises(ValueError):
        X.prospect_fair_usd(wy, dpw, idx[:2], disc)
    # the bust risk is counted once: no reach machinery is left in the export
    for gone in ("reach_prob", "arrival_factor", "scale_pred", "REACH_FLOOR"):
        assert not hasattr(X, gone), gone


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
    assert "market_surplus" in blk["AAA"]                 # Franchise gets the surplus
    led = X.club_blocks(tmp_path, surface="ledger")
    assert set(led["AAA"]) == {"as_of", "model_id", "roster", "farm"}
    with pytest.raises(ValueError):
        X.club_blocks(tmp_path, surface="nowhere")


@pytest.mark.parametrize("mod,surface", [("ledger_export.py", "ledger"),
                                         ("franchise_export.py", "franchise")])
def test_the_boards_attach_the_block_only_through_the_flagged_reader(mod, surface):
    src = (ROOT / mod).read_text(encoding="utf-8")
    assert src.count("_xm.club_blocks(") == 1
    assert src.count(f'_xm.club_blocks(DATA, surface="{surface}")') == 1
    assert '["xm"] = _xmb[' in src


# The Club Ledger never-list (owner answer XM2-Q2): no single projected payroll
# line, no club surplus total, no cap-space cell, no ladder on a salary cell, no
# style z-score. The xM$ block the Ledger is handed must carry none of them.
LEDGER_FORBIDDEN_TOKENS = ("surplus", "cap", "space", "ladder", "z", "projected", "forecast",
                           "revenue", "attendance", "tv", "valuation")


def _keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", str(k)
            yield from _keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _keys(v, f"{path}[{i}]")


def test_the_ledger_never_list_holds_for_the_xm_block(monkeypatch, tmp_path):
    assert X.SURFACE_BLOCKS["ledger"] == ("roster", "farm")
    assert "market_surplus" in X.SURFACE_BLOCKS["franchise"]
    src = DATA / "xm_clubs.json"
    if src.is_file():
        (tmp_path / "xm_clubs.json").write_bytes(src.read_bytes())
    else:
        doc = {"as_of": "2026-10-22", "model_id": "fa_market", "clubs": {"AAA": {
            "roster": {"n": 1, "xm_aav_usd": 5, "fair_aav_usd": 4, "ids": ["1"],
                       "payroll_spotrac": {"total_2026_usd": 9, "committed_2027_usd": 3,
                                           "note": X.PAYROLL_NOTE}},
            "market_surplus": {"n": 1, "xm_usd": 7, "fair_usd": 6, "ids": ["1"]},
            "farm": {"n": 0, "n_on40": 0, "fair_usd": 0, "ids": []}}}}
        (tmp_path / "xm_clubs.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(X, "XM_DISPLAY_ON", True)
    led = X.club_blocks(tmp_path, surface="ledger")
    assert led
    for c, blk in led.items():
        assert set(blk) == {"as_of", "model_id", "roster", "farm"}, c
        for path, k in _keys(blk):
            toks = k.lower().split("_")
            assert not any(t in LEDGER_FORBIDDEN_TOKENS for t in toks), (c, path)
        # payroll on file sits beside the roster sum, labelled, never netted
        pay = blk["roster"]["payroll_spotrac"]
        assert pay["note"] == "not a payroll projection", c
        assert set(pay) <= {"total_2026_usd", "committed_2027_usd", "note"}, c
        # the farm shows Fair $ only (gate section 16): no xM$ figure at all
        assert not any(k.startswith("xm_") for k in blk["farm"]), c


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
        assert isinstance(r["fair"], int), k
        if r["xm_withheld"]:
            # gate section 16: a prospect's xM$ is withheld, never extrapolated
            assert all(r[c] is None for c in X.XM_COLUMNS), k
            assert r["fair"] >= 0, k
            continue
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
        # gate section 16: a prospect shows Fair $ only, sits in the farm block
        # and carries the first season of his path; his xM$ is withheld
        if r["pop"] == "prospect":
            assert r["xm_withheld"] is True and r["bucket"] == "farm", k
            assert isinstance(r["arrive"], int) and r["arrive"] >= players["class_year"], k
            assert r["ctrl"] == 0 and r["msur_xm"] is None and r["clip"] is False, k
        else:
            assert r["xm_withheld"] is False and r["arrive"] is None, k
    # the support-clip report is by population only (docs/PROSPECT_ANCHOR_GATE.md)
    # and covers the rows the market model priced, never a withheld prospect
    assert set(players["support_clip_by_population"]) <= {"fa", "mlb"}
    assert players["prospect_pricing"]["xm_withheld_note"] == "outside the market model's range"
    by_arr = players["prospect_pricing"]["by_arrival_year"]
    assert sum(by_arr.values()) == sum(1 for r in rows.values() if r["pop"] == "prospect")
    assert players["counterfactual_note_prospect"] == X.CF_NOTE_PROSPECT


def test_served_gate_verdict_is_read_off_the_eval_artifact():
    players, clubs, _ = _served()
    ev = DATA / "xm_eval.json"
    if not ev.is_file():
        pytest.skip("xm_eval.json absent")
    verdict = (json.loads(ev.read_text(encoding="utf-8")).get("holdout") or {}).get("verdict")
    for doc in (players, clubs):
        assert doc["gate"]["verdict"] == verdict
        assert doc["gate"]["eval_artifact"] == "data/xm_eval.json"


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
        assert not any(key.startswith("xm_") for key in fm), c
        assert fm["fair_usd"] == sum(rows[k]["fair"] for k in fm["ids"]), c
        assert fm["n_on40"] == sum(1 for k in fm["ids"] if rows[k]["on40"]), c
        assert ro["n_on40_prospects_in_farm"] == fm["n_on40"], c
        assert all(rows[k]["pop"] == "prospect" for k in fm["ids"]), c
        assert ro["payroll_spotrac"]["note"] == X.PAYROLL_NOTE, c
        # every roster row with a priced control window is in the surplus sum
        assert set(ms["ids"]) == {k for k in ro["ids"] if rows[k]["msur_xm"] is not None}, c
    # every roster and farm row is in its club's block
    assert seen == {k for k, r in rows.items() if r["bucket"] in ("roster", "farm")}
    assert len(clubs["clubs"]) == clubs["n_clubs"] == 30
    assert clubs["surfaces"]["ledger"] == ["roster", "farm"]
    # the league farm total reconciles to the farm rows (gate section 16)
    farm_rows = [r for r in rows.values() if r["bucket"] == "farm"]
    assert sum(cd["farm"]["fair_usd"] for cd in clubs["clubs"].values()) == sum(
        r["fair"] for r in farm_rows)
