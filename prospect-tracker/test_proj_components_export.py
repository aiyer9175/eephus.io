"""PJ_6_COMPONENT_EXPORT_DARK: the component lines ride the veteran build dark.

Plan Part 9 section 9.2 'Component projections', LANE_A sections 2.2, 2.7 and
2.8. Class 2: PROJ_COMPONENTS_LIVE defaults False, and while it is False the
blocks go only to the preview under .cache and no served key moves. These
tests run the real _veteran_rows on a handful of real players three ways:

  A  the component context missing (the code path before this task: every
     row comes out exactly as it did, no block is built);
  B  the context present, flag False (the shipped default);
  C  the context present, flag True (the PJ_8 flip, measured here only).

The curves and the component context are fitted once on the WHOLE corpus and
handed to all three runs, so the slice changes nothing but the row count.
"""
from __future__ import annotations

import copy
import json

import pytest

import fa_projection as fp
import mlb_player_export as mpe
import proj_components as PC
import proj_export as pe

#: Shohei Ohtani (two-way), Aaron Judge, Cal Raleigh, Tarik Skubal, Emmanuel
#: Clase (reliever), Juan Soto.
_IDS = (660271, 592450, 663728, 669373, 661403, 665742)

#: The pre-existing veteran keys the spec names; downstream readers
#: (lineup_strength reads woba[0], star_out reads warY1Champ, trade values, FA,
#: arbitration, Ledger and Franchise read the WAR and surplus keys).
_PINNED = ("war", "warChamp", "warY1Champ", "warPTH", "warP10", "warP90", "woba",
           "wrc", "fip", "sur", "surNpv", "surTotal", "salPath")


def _rows(monkeypatch, corpus, fit, ctx, live: bool) -> tuple[list[dict], dict]:
    monkeypatch.setattr(pe, "PROJ_COMPONENTS_LIVE", live)
    monkeypatch.setattr(pe, "_components_context", lambda _c: ctx)
    monkeypatch.setattr(fp, "fitted_models", lambda _c, _s: fit)
    rows = pe._veteran_rows(corpus, pe._display_names(), {}, pe._winter_dpw(pe.FIRST_SEASON))
    return copy.deepcopy(rows), copy.deepcopy(pe._COMPONENT_BLOCKS)


def _shifted_ranges(real):
    """project_components with every range end moved (+7 runs, +700 PA,
    +70 IP): run D, the causal probe of the range test."""
    def shifted(*a, **kw):
        res = real(*a, **kw)
        for side in ("hit", "pit"):
            blk = res.get(side)
            for ln in ((blk or {}).get("lines") or {}).values():
                for rk, ends in list((ln.get("ranges") or {}).items()):
                    bump = 700.0 if rk == "pa" else 70.0 if rk == "ip" else 7.0
                    ln["ranges"][rk] = tuple(None if e is None else e + bump for e in ends)
        return res
    return shifted


@pytest.fixture(scope="module")
def runs():
    full = fp.build_corpus()
    fit = fp.fitted_models(full, pe.FIRST_SEASON - 1)
    ctx = pe._components_context(full)
    if ctx is None:
        pytest.skip("component context unavailable (params or frozen vintage missing)")
    keep = set(_IDS)
    corpus = dict(full)
    for side in ("hit", "pit"):
        corpus[side] = [r for r in full[side] if r.get("mlbam") in keep]
    mp = pytest.MonkeyPatch()
    try:
        a = _rows(mp, corpus, fit, None, False)
        b = _rows(mp, corpus, fit, ctx, False)
        c = _rows(mp, corpus, fit, ctx, True)
        mp.setattr(PC, "project_components", _shifted_ranges(PC.project_components))
        d = _rows(mp, corpus, fit, ctx, True)
    finally:
        mp.undo()
    return {"A": a, "B": b, "C": c, "D": d, "ctx": ctx}


def _dump(rows: list[dict]) -> str:
    return json.dumps(rows, sort_keys=True, separators=(",", ":"))


def test_flag_false_rows_are_byte_identical_to_the_rows_without_the_component_code(runs):
    rows_a, blocks_a = runs["A"]
    rows_b, blocks_b = runs["B"]
    assert blocks_a == {}, "no context, no block"
    assert len(rows_b) >= 5
    assert _dump(rows_b) == _dump(rows_a)
    assert all("pa" not in r and "ip" not in r for r in rows_b)
    assert len(blocks_b) == len(rows_b), "every sliced veteran gets a preview block"


def test_flag_false_writes_only_the_preview(runs, tmp_path, monkeypatch):
    rows_b, blocks_b = runs["B"]
    preview = tmp_path / "cache" / "preview" / "components.json"
    live = tmp_path / "data" / "mlb_proj_components.json"
    monkeypatch.setattr(pe, "PROJ_COMPONENTS_LIVE", False)
    monkeypatch.setattr(pe, "COMPONENTS_PREVIEW_PATH", preview)
    monkeypatch.setattr(pe, "COMPONENTS_LIVE_PATH", live)
    monkeypatch.setattr(pe, "_COMPONENT_BLOCKS", blocks_b)
    assert pe._write_components(rows_b) == preview
    assert not live.exists()
    doc = json.loads(preview.read_text(encoding="utf-8"))
    assert doc["components_live"] is False and doc["frame"] == "FanGraphs frame"
    assert doc["n_rows"] == len(rows_b) and set(doc["rows"]) == {r["key"] for r in rows_b}


def test_flag_true_adds_only_the_year_one_exposure(runs):
    rows_a, _ = runs["A"]
    rows_c, blocks_c = runs["C"]
    by_a = {r["key"]: r for r in rows_a}
    assert set(by_a) == {r["key"] for r in rows_c}
    for r in rows_c:
        old = by_a[r["key"]]
        for k, v in old.items():
            assert json.dumps(r.get(k), sort_keys=True) == json.dumps(v, sort_keys=True), (r["key"], k)
        assert set(r) - set(old) <= {"pa", "ip"}, (r["key"], set(r) - set(old))
        blk = blocks_c[r["mlbam"]]
        if blk["hit"]:
            assert r["pa"] == blk["hit"]["pa"][0]
        if blk["pit"]:
            assert r["ip"] == blk["pit"]["ip"][0]
    # The generic loop above covers every key; the named ones must exist on
    # the slice (sur / surNpv / salPath need a contract, which the slice
    # passes none of, so no money key is asserted here).
    for k in _PINNED:
        if k in ("sur", "surNpv", "surTotal", "salPath"):
            continue
        assert any(k in r for r in rows_c), k


def test_component_war_plus_gap_is_the_served_war(runs):
    rows_c, blocks_c = runs["C"]
    n = 0
    for r in rows_c:
        blk = blocks_c[r["mlbam"]]
        for t, w in enumerate(r["war"]):
            wc, g = blk["warComp"][t], blk["gap"][t]
            if wc is None:
                continue
            assert abs(wc + g - w) <= 0.01, (r["key"], t, wc, g, w)
            n += 1
    assert n >= 5 * 5


def test_copied_rate_lines_are_the_rows_own_arrays(runs):
    rows_c, blocks_c = runs["C"]
    for r in rows_c:
        blk = blocks_c[r["mlbam"]]
        if blk["hit"]:
            assert blk["hit"]["woba"] == r.get("woba") and blk["hit"]["wrc"] == r.get("wrc")
        if blk["pit"]:
            assert blk["pit"]["fip"] == r.get("fip")
            if blk["pit"]["gmli"] is not None:
                assert blk["pit"]["gmli"][0] is not None


def test_no_served_key_is_built_from_component_range_ends(runs):
    """No served key is a sum of component p10 or p90 values. Causal form
    (an equality search hits coincidences at 0.1-run rounding): run C's
    pre-existing keys equal run A's, where no range exists at all (the test
    above), and run D moves every range end of every block and nothing outside
    p10 / p90 moves: not a row key (the year-1 pa / ip included), not a block
    mean, not warComp or gap. No range dict names a WAR range."""
    rows_c, blocks_c = runs["C"]
    rows_d, blocks_d = runs["D"]
    assert _dump(rows_d) == _dump(rows_c)
    assert set(blocks_d) == set(blocks_c)
    n_moved = 0
    for mid, bc in blocks_c.items():
        bd = blocks_d[mid]
        assert bd["warComp"] == bc["warComp"] and bd["gap"] == bc["gap"]
        for side in ("hit", "pit"):
            if not bc[side]:
                assert not bd[side]
                continue
            for k, v in bc[side].items():
                if k in ("p10", "p90"):
                    assert not any(n.lower().startswith("war") for n in v), "no WAR range"
                    n_moved += sum(1 for name in v for x, y in zip(v[name], bd[side][k][name])
                                   if x is not None and x != y)
                    continue
                assert bd[side][k] == v, (mid, side, k)
    assert n_moved > 0, "the probe moved range ends"


def test_two_way_rows_carry_both_sides_and_sum_them(runs):
    rows_c, blocks_c = runs["C"]
    two = [r for r in rows_c if r.get("twoWay")]
    assert two, "the slice holds a two-way veteran"
    for r in two:
        blk = blocks_c[r["mlbam"]]
        assert blk["twoWay"] and blk["hit"] and blk["pit"]
        assert "pa" in r and "ip" in r
        for t in range(pe.HORIZON):
            h, p = blk["hit"]["warComp"][t], blk["pit"]["warFip"][t]
            if h is not None and p is not None:
                assert abs(blk["warComp"][t] - (h + p)) <= 0.011


def test_payload_flag_is_only_set_when_live():
    import inspect
    src = inspect.getsource(pe._build_payload_body)
    assert '**({"components_live": True} if PROJ_COMPONENTS_LIVE else {})' in src
    assert pe.PROJ_COMPONENTS_LIVE is False


def test_detail_reads_no_component_lines_while_dark(tmp_path, monkeypatch):
    path = tmp_path / "mlb_proj_components.json"
    path.write_text(json.dumps({"rows": {"a_b": {"warComp": [1.0]}}}), encoding="utf-8")
    monkeypatch.setattr(mpe, "COMPONENTS_PATH", path)
    assert mpe._component_rows({"vets": []}) is None
    assert mpe._component_rows({"components_live": True}) == {"a_b": {"warComp": [1.0]}}


def test_the_comp_block_rides_the_card_shard_only(tmp_path, monkeypatch):
    """Owner answer PJ6-SIZE (a): proj.comp lands in the per-card shard, and the
    whole-set payload object handed in is not touched."""
    monkeypatch.setattr(mpe, "DATA_DIR", tmp_path)
    payload = {"generated_at": "2026-10-14", "first_season": 2027, "horizon": 5,
               "players": {"a_b": {"key": "a_b", "proj": {"war": [1.0]}},
                           "c_d": {"key": "c_d", "proj": {"war": [2.0]}}}}
    before = json.dumps(payload, sort_keys=True)
    assert mpe._export_shards(payload, {"a_b": {"warComp": [0.9], "gap": [0.1]}}) == 2
    assert json.dumps(payload, sort_keys=True) == before
    a = json.loads((tmp_path / "mlb_player_detail" / "a_b.json").read_text(encoding="utf-8"))
    c = json.loads((tmp_path / "mlb_player_detail" / "c_d.json").read_text(encoding="utf-8"))
    assert a["player"]["proj"] == {"war": [1.0], "comp": {"warComp": [0.9], "gap": [0.1]}}
    assert "comp" not in c["player"]["proj"]
