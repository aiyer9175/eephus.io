# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the positional ladder v2 (EWAR_LADDER_REDERIVE, owner EW3-25,
2026-10-15; docs/ewar/LADDER_V2_GATE.md).

1. The method: on a fixture built the way every real source is (fielding runs
   centred within position and season, moves after bad years), the amended
   network (A1) recovers the planted ladder, and the amended scoring predictor
   (A2) scores the planted ladder best. Hermetic.
2. The record: the read's verdict follows its own intervals under the gate's
   fixed-sequence rule, the served ladder artifact is the read's, and Position
   Fit reads v2 exactly when the read passed it.
3. The one-run-scale rule (gate part 8): an average glove is worth the same at
   every fielding position, and the served rows obey it.
4. The export bundle beside v1 and its generated README.
5. The Library's Positional Ladder view: registered, the "Standalone version"
   placeholder present with no link, and it renders at 390 px in both themes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import ladder_v2 as L2  # noqa: E402
import positional_fit as pf  # noqa: E402

EVAL = ROOT / "data" / "positional_ladder_v2_eval.json"
V2 = ROOT / "data" / "positional_ladder_v2.json"
PF = ROOT / "data" / "positional_fit.json"
PF_UI = ROOT / "data" / "positional_fit_ui.json"


def _json(p: Path):
    if not p.exists():
        pytest.skip(f"{p.name} not built")
    return json.loads(p.read_text(encoding="utf-8"))


# ---- 1. the method, on fixtures ------------------------------------------------

@pytest.fixture(scope="module")
def fixture():
    import ladder_v2_lab as lab
    recs, target, e9 = lab.fixture_records()
    return recs, target, e9, L2.build_rows(recs)


def test_the_network_recovers_a_planted_ladder_on_centred_runs(fixture):
    """Amendment A1. The registered first form flattened this same ladder to
    about a third of its size; the persistence form must land within 1.25 runs
    of every planted rung on the Baseball-Reference-shaped leg."""
    _recs, target, e9, rows = fixture
    fit = L2.fit_network(rows["BREF"], e9)
    leg = L2.source_ladder(fit, e9)
    m7 = L2.mean7(target, e9)
    off = {p: abs(leg[p][0] - (target[p] - m7)) for p in L2.OAA7}
    assert max(off.values()) < 1.25, off
    assert 0.2 < fit["k"] < 0.9, fit["k"]


def test_the_scoring_predictor_is_lowest_at_the_planted_ladder(fixture):
    """Amendment A2: scaled copies of the planted ladder score worse than it."""
    _recs, target, e9, rows = fixture
    seasons = set(range(2016, 2027))
    ladders = {f"x{s}": {p: s * v for p, v in target.items()} for s in (0.5, 1.0, 1.5)}
    loss = []
    for t in sorted(seasons):
        loss.extend(L2.score_rows({"BREF": rows["BREF"]}, ladders, t, seasons - {t}))
    mae = {k: v["mae"] for k, v in L2.summarize(loss, ladders).items()}
    assert mae["x1.0"] < mae["x0.5"] and mae["x1.0"] < mae["x1.5"], mae


def test_the_cluster_bootstrap_is_paired_and_seeded():
    rows = [(i % 7, "BREF", "across", 1.0, {"a": (1.0 + 0.1 * (i % 3), 0.0), "b": (1.0, 0.0)}, 2020)
            for i in range(60)]
    one = L2.cluster_boot(rows, "a", "b", draws=200, seed=3)
    two = L2.cluster_boot(rows, "a", "b", draws=200, seed=3)
    assert one == two
    assert one["dmae"] > 0 and one["n_players"] == 7


# ---- 2. the record ---------------------------------------------------------------

def test_the_verdict_follows_the_fixed_sequence_rule():
    ev = _json(EVAL)
    t, v = ev["tests"], ev["verdict"]
    step1 = t["v1_minus_b_pooled"]["ci95"][0] > 0 and t["v1_minus_b_across"]["ci95"][1] >= 0
    assert v["step1_b_replaces_v1"] is step1
    if step1:
        assert v["step2_d_replaces_b"] is (t["b_minus_d_b_pooled"]["ci95"][0] > 0)
    else:
        assert v["step2_d_replaces_b"] is None
    assert v["served_on_position_fit"] == ("v2" if step1 else "v1")
    assert ev["seeds"] == {"bootstrap": 20261015, "draws": 2000, "ci": 11, "ci_draws": 400}
    assert ev["registered_commit"] == "7fa62e8a"


def test_the_served_ladder_artifact_is_the_reads():
    ev, doc = _json(EVAL), _json(V2)
    assert doc["values"] == ev["ladder_artifact"]["values"]
    assert set(doc["values"]) == set(L2.LADDER9)
    for p, val in doc["values"].items():
        lo, hi = doc["ci95"][p]
        assert lo - 0.01 <= val <= hi + 0.01, p
    ident = doc["identification"]
    assert abs(ident["sum_exposure_weighted"]) < 0.01
    fc = ident["values_fielder_centred"]
    assert abs(sum(fc[p] for p in L2.FIELD)) < 0.05
    shifts = {round(doc["values"][p] - fc[p], 2) for p in L2.LADDER9}
    assert max(shifts) - min(shifts) <= 0.011


def test_position_fit_reads_v2_exactly_when_the_read_passed_it():
    ev = _json(EVAL)
    passed = ev["verdict"]["step1_b_replaces_v1"]
    assert pf.POSFIT_LADDER == ("v2" if passed else "v1")
    fit = _json(PF)["fit"]
    assert fit["ladder_posfit"]["basis"] == pf.POSFIT_LADDER
    if passed:
        assert fit["ladder_posfit"]["values"] == _json(V2)["values"]
        ui = _json(PF_UI)["ladder"]
        assert ui["basis"] == "v2"
        assert ui["valuesDisplay"] == _json(V2)["identification"]["values_fielder_centred"]
        assert ui["verdict"]["dmae"] == ev["tests"]["v1_minus_b_pooled"]["dmae"]


def test_the_blocks_other_models_read_are_carried_not_refit():
    """fit.ladder (DEM+, prospect_def_value, the export) and fit.signal (eWAR's
    k_inn) are carried from the artifact a rebuild replaces, with the refit's
    difference on record, so this task moves neither."""
    fit = _json(PF)["fit"]
    c = fit["carried"]
    assert c["on"] is pf.V1_CARRY
    if c["ladder"]:
        assert set(c["ladder_refit_minus_carried"]) == set(L2.LADDER9)
    if c["signal"]:
        assert set(c["signal_k_inn_refit_minus_carried"]) == set(pf.OAA_POSITIONS)


# ---- 3. one run scale --------------------------------------------------------------

def test_an_average_glove_is_worth_the_same_at_every_fielding_position():
    assert pf.POSFIT_ONE_SCALE is True
    lad = {"C": 9.0, "1B": -4.0, "2B": -2.0, "3B": -1.5, "SS": 1.0, "LF": 0.5,
           "CF": 1.5, "RF": 0.2, "DH": -7.0}
    sig = {p: {"signal_sd": 2.0 + i} for i, p in enumerate(pf.OAA_POSITIONS)}
    D = {p: 3.0 * (i - 3) for i, p in enumerate(pf.OAA_POSITIONS)}
    k = 1277.7
    tot0 = {p: pf.field_runs(p, 0.0, D, sig, lad, k) + lad[p] for p in pf.OAA_POSITIONS}
    assert max(tot0.values()) - min(tot0.values()) < 1e-9
    assert tot0["SS"] == pytest.approx(pf.league_term(lad))
    z = -1.3
    a, b = "SS", "1B"
    gap = (pf.field_runs(b, z, D, sig, lad, k) + lad[b]) - (pf.field_runs(a, z, D, sig, lad, k) + lad[a])
    assert gap == pytest.approx((sig[b]["signal_sd"] - sig[a]["signal_sd"]) * z * k / 1000.0)


def test_the_served_rows_obey_the_one_scale_rule():
    doc = _json(PF)
    fit = doc["fit"]
    sig = fit["signal"]
    k = fit["inn_per_650pa"]
    assert fit["one_scale"]["on"] is True
    lv = fit["ladder_posfit"]["values"]
    assert fit["one_scale"]["league_term_per_650pa"] == pytest.approx(pf.league_term(lv), abs=0.001)
    n = 0
    for r in doc["players"]:
        by = {p: v for p, v in r["by_position"].items() if p in pf.OAA_POSITIONS}
        ps = sorted(by)
        for a, b in zip(ps, ps[1:]):
            want = (sig[b]["signal_sd"] - sig[a]["signal_sd"]) * r["glove_z"] * k / 1000.0
            assert by[b]["def_total"] - by[a]["def_total"] == pytest.approx(want, abs=0.05), (r["name"], a, b)
            n += 1
        if r.get("demotion_gain_league_part") is not None and r.get("demotion_pos") != "DH":
            assert r["demotion_gain_league_part"] == pytest.approx(0.0, abs=0.01)
    assert n > 200
    M = fit["conversion_matrix"]
    for a in pf.OAA_POSITIONS:
        for b in pf.OAA_POSITIONS:
            assert M[a][b]["net_for_average_glove_per_650pa"] == pytest.approx(0.0, abs=0.01)


# ---- 4. the export ---------------------------------------------------------------

def test_the_export_writes_v2_beside_v1(tmp_path):
    import export_positional_ladder as X
    v2 = X.build_v2()
    paths = X.write_v2(v2, tmp_path)
    assert sorted(p.name for p in paths) == ["positional_ladder_v2.csv", "positional_ladder_v2.json"]
    got = json.loads((tmp_path / "positional_ladder_v2.json").read_text(encoding="utf-8"))
    assert got["bases"]["values"]["values"] == {p: _json(V2)["values"][p] for p in X.POS_ORDER}
    lines = (tmp_path / "positional_ladder_v2.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10 and lines[0].startswith("position,")


def test_the_committed_readme_is_the_generated_one():
    import export_positional_ladder as X
    rec = ROOT / "data" / "positional_ladder_recency_eval.json"
    text = X.render_readme(X.build(), X.build_v2(),
                           json.loads(rec.read_text(encoding="utf-8")) if rec.exists() else None)
    committed = (X.OUT_DIR / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == text
    assert chr(0x2014) not in text and chr(0x2013) not in text


# ---- 5. the Library view -----------------------------------------------------------

GLJS = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_view_is_registered_on_the_methods_shelf():
    import build_site as B
    v = {x["id"]: x for x in B.GLOSSARY_VIEWS}["positional-ladder"]
    assert (v["shelf"], v["label"], v["body"]) == ("methods", "Positional Ladder", "positional-ladder-body")
    assert ('{ id: "positional-ladder", shelf: "methods", label: "Positional Ladder", '
            'body: "positional-ladder-body", render: renderPositionalLadder, aliases: ["ladder"] },') in GLJS
    assert any(h == "/glossary/#view=positional-ladder" for h, _n, _p in B.PAGE_INDEX_VIEWS)
    blk = GLJS[GLJS.index("// ---- Methods > Positional Ladder"):GLJS.index("// ---- Library view")]
    assert "Standalone version" in blk and 'function _pladUrl() { return ""; }' in blk
    assert chr(0x2014) not in blk and chr(0x2013) not in blk


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        yield b
        b.close()


_PROBE = """() => {
  const el = document.getElementById('positional-ladder-body');
  const tables = el ? el.querySelectorAll('.warc-table') : [];
  const link = el ? el.querySelector('.warc-link') : null;
  const fr = el ? el.querySelector('.warc-frame') : null;
  return { shown: !!el && el.style.display !== 'none', tables: tables.length,
           rows0: tables.length ? tables[0].querySelectorAll('tbody tr').length : 0,
           text: el ? el.textContent : '', linkText: link ? link.textContent.trim() : null,
           linkHref: link && link.querySelector('a') ? link.querySelector('a').getAttribute('href') : null,
           frameRight: fr ? fr.getBoundingClientRect().right : null,
           theme: document.documentElement.getAttribute('data-theme'),
           scrollW: document.documentElement.scrollWidth, innerW: innerWidth };
}"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_view_renders_at_390_without_a_page_scroll(browser, theme):
    ev = _json(EVAL)
    errors: list[str] = []
    with serve_site() as base:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.add_init_script(f'try {{ localStorage.setItem("prospect-tracker.theme", "{theme}"); }} catch (e) {{}}')
        page.on("pageerror", lambda e: errors.append(e.message))
        try:
            page.goto(base + "glossary/index.html#view=positional-ladder", wait_until="load", timeout=15_000)
            page.wait_for_selector("#positional-ladder-body .warc-table", timeout=10_000)
            out = page.evaluate(_PROBE)
        finally:
            page.close()
    assert not errors, errors
    assert out["theme"] == theme
    assert out["shown"] and out["tables"] == 3 and out["rows0"] == 9
    assert out["linkText"] == "Standalone version" and out["linkHref"] is None
    want = "%+.2f" % ev["tests"]["v1_minus_b_pooled"]["dmae"]
    assert want in out["text"], want
    assert out["scrollW"] == out["innerW"], "the page scrolls sideways at 390"
    assert out["frameRight"] <= out["innerW"]
