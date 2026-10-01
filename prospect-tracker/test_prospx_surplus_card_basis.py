# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The detail-page Surplus value card reads one basis: eFV under an eFV headline.

WHY THIS EXISTS (census M01-02, 2026-09-24, four verifiers PARTLY: the detail-card
half confirmed, the board-cell and bucket-name halves struck). With the board on eFV
(the default), the Surplus value card is titled "eFV . outcome-grounded" and headlines
the eFV surplus, but its footer line read the consensus engine's dist: Jesus Made
printed "P(bust) 5% . risk-adj $69M" under the eFV $100M, while the eFV grade card on
the same page printed P(bust) 35%. 4,614 of 4,679 prospect pages showed two different
P(bust) values, 687 of them 10 or more points apart. The board Surplus cell and the GFX
surplus block already read the eFV dist in eFV mode; the detail card now does too.

Consensus mode is untouched: there the card is titled "career-path mixture engine"
and carries the consensus engine's numbers, labelled by basis.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
DATA = ROOT / "data"


def _baked_detail_block() -> str:
    src = PROSPX.read_text(encoding="utf-8")
    i = src.find('let bakedDetailRow = "";')
    assert i != -1, "bakedDetailRow vanished from prospx/index.html; re-point this test"
    j = src.find("let dvmRow", i)
    assert j != -1
    return src[i:j]


def test_the_card_reads_the_efv_dist_under_an_efv_headline():
    block = _baked_detail_block()
    assert re.search(r"const d = _useEfv \? \(_xf\.dist \|\| \{\}\) : \(_baked\.dist \|\| \{\}\);",
                     block), (
        "bakedDetailRow must read the eFV dist when _useEfv, or the eFV-headlined card "
        "prints the consensus engine's P(bust) and risk-adj beside the eFV surplus")


def _js_round_pct(v: float) -> int:
    return math.floor(v * 100 + 0.5)


def test_efv_dist_p_bust_is_the_grade_card_p_bust():
    """The fix makes the card print dist.p_bust while the grade card prints p_bust. They
    are one number in efv_score today; if they ever split, the page shows two again."""
    path = DATA / "xfv.json"
    if not path.exists():
        pytest.skip("data/xfv.json not built")
    by = json.loads(path.read_text(encoding="utf-8")).get("by_player") or {}
    n, bad = 0, []
    for k, x in by.items():
        d = (x or {}).get("dist") or {}
        if x.get("p_bust") is None or d.get("p_bust") is None:
            continue
        n += 1
        if _js_round_pct(x["p_bust"]) != _js_round_pct(d["p_bust"]):
            bad.append((k, x["p_bust"], d["p_bust"]))
    assert n, "no xfv row carries both p_bust fields; this check proved nothing"
    assert not bad, f"{len(bad)} rows print two eFV P(bust) values: {bad[:5]}"


@pytest.fixture(scope="module")
def booted_page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        page.goto(base + "prospx/index.html", wait_until="load", timeout=60_000)
        page.wait_for_function(
            "() => document.querySelectorAll('#rows .player-row').length > 5", timeout=120_000)
        yield page, errs
        browser.close()


_READ = r"""() => {
  const body = document.getElementById('player-detail-body');
  if (!body) return null;
  const t = [...body.querySelectorAll('.detail-title')].find(e => /Surplus value/.test(e.textContent));
  let card = t ? t.nextElementSibling : null;
  while (card && !card.classList.contains('detail-card')) card = card.nextElementSibling;
  return {primary: _gradePrimary(),
          pbust: [...body.innerText.matchAll(/P\(bust\) (\d+)%/g)].map(m => m[1]),
          title: t ? t.textContent : null,
          card: card ? card.innerText : null};
}"""


def test_efv_mode_detail_page_prints_one_p_bust(booted_page):
    page, errs = booted_page
    key = "jesus_made"
    if not page.evaluate(f"() => DATA.players.some(p => p.player_key === '{key}')"):
        pytest.skip(f"{key} is not on the served board")
    page.evaluate(f"() => {{ location.hash = 'player={key}'; }}")
    page.wait_for_function(
        "() => { const b = document.getElementById('player-detail-body');"
        " return b && /Surplus value/.test(b.innerText); }", timeout=30_000)
    got = page.evaluate(_READ)
    assert got and got["primary"] == "xfv"
    assert "eFV" in (got["title"] or ""), got["title"]
    assert got["pbust"], "no P(bust) on the detail page; the check proved nothing"
    assert len(set(got["pbust"])) == 1, (
        f"eFV-mode detail page prints P(bust) {got['pbust']}: the Surplus value card is "
        "reading the consensus engine under an eFV headline")
    assert "risk-adj" not in (got["card"] or ""), (
        "the eFV-headlined Surplus value card prints the consensus engine's risk-adj")
    assert not errs, "JS errors:\n  " + "\n  ".join(errs)


# Owner answer M7-3 (2026-09-25): in Consensus mode the card's third meta figure is the
# consensus engine's dist.risk_adjusted_mm, which is mean - lambda x (mean - downside).
# risk_lambda is 0 on every served row, so no risk adjustment is applied and the figure
# is the plain simulated mean: it prints as "sim mean", never "risk-adj".
def test_served_rows_carry_lambda_zero_so_the_label_is_sim_mean():
    path = DATA / "timeseries.json"
    if not path.exists():
        pytest.skip("data/timeseries.json not built")
    rows = json.loads(path.read_text(encoding="utf-8")).get("players") or []
    lams = [((p.get("surplus") or {}).get("dist") or {}).get("risk_lambda") for p in rows
            if ((p.get("surplus") or {}).get("dist") or {}).get("risk_adjusted_mm") is not None]
    assert lams, "no served row carries risk_adjusted_mm; this check proved nothing"
    assert all(lam is not None and float(lam) == 0.0 for lam in lams), (
        "a served row carries a positive risk_lambda: re-read owner answer M7-3, "
        "that row now earns the risk-adj label and the copy must say what it applies")


def test_no_template_prints_a_hardcoded_risk_adj_label():
    src = PROSPX.read_text(encoding="utf-8")
    assert re.search(r"^function svRiskAdjLabel\(d\) \{", src, re.M), "svRiskAdjLabel vanished"
    hard = re.findall(r"[`'\"][^`'\"\n]*risk-adj \$\{", src)
    assert not hard, f"a template prints 'risk-adj' without svRiskAdjLabel: {hard[:3]}"


def test_sim_mean_label_follows_lambda():
    mr = pytest.importorskip("py_mini_racer")
    import warnings
    warnings.filterwarnings("ignore")
    src = PROSPX.read_text(encoding="utf-8")
    m = re.search(r"^function svRiskAdjLabel\(d\) \{.*?\n\}\n", src, re.S | re.M)
    assert m
    ctx = mr.MiniRacer()
    ctx.eval(m.group(0))
    assert ctx.eval("svRiskAdjLabel({risk_lambda: 0})") == "sim mean"
    assert ctx.eval("svRiskAdjLabel({risk_lambda: 0.0, risk_adjusted_mm: 69})") == "sim mean"
    assert ctx.eval("svRiskAdjLabel({})") == "sim mean"
    assert ctx.eval("svRiskAdjLabel({risk_lambda: 0.5})") == "risk-adj"


def test_consensus_mode_detail_card_prints_sim_mean(booted_page):
    page, errs = booted_page
    key = "jesus_made"
    if not page.evaluate(f"() => DATA.players.some(p => p.player_key === '{key}')"):
        pytest.skip(f"{key} is not on the served board")
    page.evaluate("() => { state.gradePrimary = 'fv'; location.hash = 'player=jesus_made'; render(); }")
    page.wait_for_function(
        "() => { const b = document.getElementById('player-detail-body');"
        " return b && /Surplus value/.test(b.innerText) && _gradePrimary() === 'fv'; }",
        timeout=30_000)
    page.wait_for_timeout(500)
    got = page.evaluate(_READ)
    try:
        assert got and got["primary"] == "fv"
        card = got["card"] or ""
        assert re.search(r"sim mean \$[0-9.]+[MK]", card), card[-400:]
        assert "risk-adj" not in card, card[-400:]
        assert not errs, "JS errors:\n  " + "\n  ".join(errs)
    finally:
        page.evaluate("() => { state.gradePrimary = 'xfv'; render(); }")
