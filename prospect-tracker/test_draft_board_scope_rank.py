# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The draft board prints a #n ordinal only where a whole-class rank exists.

Final-pass findings M03-01 and M03-09 (2026-09-24). Baseball America's HS and
College lists rank a SUBSET of a draft class; the ingest keeps that number at
tool_grades.baseballamerica_draft._extras.ba_scope_rank and never writes it into
`rank` (baseballamerica_csv.scope_rank_is_global), because BA never published
how the two lists interleave.

Two served defects came from that seam:
  * M03-01: BA's HS Top 150 (2026-07-17) postdated its Top 100 (2026-07-15),
    so the scope snapshot stood as BA's latest and erased the global rank of
    all 41 HS players on the Top 100, BA #1 Dylan Seward included (tested in
    test_draft_export_polish.ScopeBoardRankVote).
  * M03-09: with no FV and no rank, the Rankings board numbered the 2028 class
    (and the 2027 unranked tail) in the export's alphabetical order, under a
    tooltip that said "Sequential rank by consensus FV".

This test drives the real page, because the defect lived in which rows the
page stamped, not in any one helper.
"""
from __future__ import annotations

import pytest
from conftest import load_data_doc, serve_site

PROSPX = "prospx/index.html"


def _classes():
    doc = load_data_doc("draft_timeseries.json")
    if not doc:
        pytest.skip("data/draft_timeseries.json not built")
    return {c["year"]: c for c in doc.get("classes") or []}


def _years_with_scope_tail():
    """Classes that hold prospects with neither FV nor a whole-class rank."""
    out = []
    for y, c in _classes().items():
        if any(p.get("consensus_fv") is None and p.get("consensus_rank") is None
               for p in c.get("prospects") or []):
            out.append(y)
    return sorted(out)


@pytest.fixture(scope="module")
def page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg._draft_base = base
        pg._draft_errs = errs
        try:
            yield pg
        finally:
            browser.close()


def _open(pg, year, view="rankings"):
    pg.goto(f"{pg._draft_base}{PROSPX}#tab=draft&dyear={year}&dview={view}",
            wait_until="load", timeout=90_000)
    sel = ".draft-card" if view == "rankings" else ".draft-table"
    try:
        pg.wait_for_selector(sel, timeout=180_000)
    except Exception as exc:                                  # noqa: BLE001
        pytest.skip(f"draft {view} did not paint for {year}: {exc}")


_CARD_SCAN = r"""
(year) => {
  state.pageSizes.draft = 5000; state.pages.draft = 1; render();
  const cls = ((DATA.draft || {}).classes || []).find(c => c.year === year) || {};
  const byKey = {};
  for (const p of (cls.prospects || [])) byKey[p.player_key] = p;
  return [...document.querySelectorAll('.draft-card')].map(e => {
    const m = (e.getAttribute('onclick') || '').match(/goToDraftee\('([^']+)'/);
    const rec = m ? byKey[m[1]] : null;
    const ex = rec && rec.tool_grades && rec.tool_grades.baseballamerica_draft
      ? (rec.tool_grades.baseballamerica_draft._extras || {}) : {};
    return {
      key: m ? m[1] : null,
      medal: (e.querySelector('.rank-num-inner') || {}).textContent.trim(),
      title: (e.querySelector('.rank-num') || {}).title || '',
      ranked: !!rec && (rec.consensus_fv != null || rec.consensus_rank != null),
      scope: ex.ba_rank_is_global === false ? (ex.ba_scope || null) : null,
      scopeRank: ex.ba_rank_is_global === false ? ex.ba_scope_rank : null,
      meta: (e.querySelector('.draft-card-meta') || {}).textContent || '',
    };
  });
}
"""


@pytest.mark.parametrize("year", [2026, 2027, 2028])
def test_ordinal_only_on_ranked_cards(page, year):
    if year not in _classes():
        pytest.skip(f"no {year} class in the artifact")
    _open(page, year)
    cards = page.evaluate(_CARD_SCAN, year)
    assert cards, f"{year}: no cards rendered"
    assert all(c["key"] for c in cards), "a card lost its draftee key"
    ranked = [c for c in cards if c["ranked"]]
    tail = [c for c in cards if not c["ranked"]]
    # Ranked cards carry #1..#K in order; unranked cards carry no ordinal.
    assert [c["medal"] for c in ranked] == [f"#{i}" for i in range(1, len(ranked) + 1)]
    bad = [c for c in tail if c["medal"].startswith("#")]
    assert not bad, f"{year}: {len(bad)} unranked cards print an ordinal, e.g. {bad[:3]}"
    assert not any("by consensus FV" in c["title"] for c in tail)
    # Ranked rows all precede the unranked tail.
    if ranked and tail:
        first_tail = next(i for i, c in enumerate(cards) if not c["ranked"])
        assert all(not c["ranked"] for c in cards[first_tail:])
    # A BA scope rank shows as a labelled chip, never as a bare number.
    for c in tail:
        if c["scope"] and c["scopeRank"] is not None:
            assert f"#{c['scopeRank']}" in c["meta"] and "BA " in c["meta"], c
    assert not page._draft_errs, page._draft_errs


def test_tail_is_ordered_in_scope_blocks_never_merged(page):
    years = [y for y in _years_with_scope_tail() if y >= 2027]
    if not years:
        pytest.skip("no current class with an unranked BA scope tail")
    for year in years:
        _open(page, year)
        tail = [c for c in page.evaluate(_CARD_SCAN, year)
                if not c["ranked"] and c["scope"]]
        if not tail:
            continue
        pools = ["HS" if c["scope"].upper().startswith("HS") else "COL" for c in tail]
        # HS block, then College block: once College starts, HS never returns.
        if "COL" in pools:
            assert "HS" not in pools[pools.index("COL"):], f"{year}: HS and College interleaved"
        # Inside each scope list, BA's own order.
        for scope in {c["scope"] for c in tail}:
            rks = [c["scopeRank"] for c in tail if c["scope"] == scope]
            assert rks == sorted(rks), f"{year} {scope}: not in BA order"


def test_header_names_only_sources_present(page):
    labels = {"fangraphs": "FanGraphs", "espn_draft": "ESPN draft",
              "mlb_pipeline_draft": "MLB Pipeline draft",
              "baseballamerica_draft": "Baseball America draft"}
    for year in (2017, 2019, 2026, 2027, 2028):
        cls = _classes().get(year)
        if not cls:
            continue
        present = {pt.get("source") for p in cls.get("prospects") or []
                   for pt in p.get("points") or [] if pt.get("source")}
        _open(page, year)
        # The class note is a closed <details> under the cards (site pass
        # REDESIGN_prospx); textContent reads its body too.
        head = page.evaluate(
            "() => (document.querySelector('.draft-class-note') || {}).textContent || ''")
        assert "Sources:" in head, head[:300]
        for src, lbl in labels.items():
            assert (lbl in head) == (src in present), f"{year}: header {lbl!r} vs sources {present}"


def test_leaderboard_numbers_only_ranked_rows(page):
    for year in _years_with_scope_tail():
        if year < 2027:
            continue
        _open(page, year, "leaderboard")
        rows = page.evaluate(r"""
          (year) => {
            state.draftLeaderShowAll = true; renderDraft();
            const cls = ((DATA.draft || {}).classes || []).find(c => c.year === year) || {};
            const byKey = {};
            for (const p of (cls.prospects || [])) byKey[p.player_key] = p;
            return [...document.querySelectorAll('.draft-results-grid .draft-table tbody tr')].map(tr => {
              const m = (tr.getAttribute('onclick') || '').match(/goToDraftee\('([^']+)'/);
              const rec = m ? byKey[m[1]] : null;
              return { first: tr.cells[0].textContent.trim(),
                       ranked: !!rec && (rec.consensus_fv != null || rec.consensus_rank != null) };
            });
          }""", year)
        assert rows, f"{year}: leaderboard rendered no rows"
        numbered = [r for r in rows if r["first"].isdigit()]
        assert all(r["ranked"] for r in numbered), f"{year}: an unranked row carries a number"
        assert [int(r["first"]) for r in numbered] == list(range(1, len(numbered) + 1))


def test_no_report_fallback_names_only_the_prospects_sources(page):
    """The no-scouting-reports line named ESPN draft / MLB Pipeline / FanGraphs
    on every draftee page; the 489 prospects that reach it are all on one or
    two of those outlets (census M03-02, second hardcoded list)."""
    src = open(PROSPX, encoding="utf-8").read()
    assert "ESPN draft / MLB Pipeline / FanGraphs sources" not in src
    _open(page, 2019)
    out = page.evaluate(r"""
      () => {
        const cls = DATA.draft.classes.find(c => c.year === 2019);
        const p = (cls.prospects || []).find(q => !Object.values(q.tool_grades || {})
          .some(g => String(((g || {})._extras || {}).report || '').trim().length > 30));
        if (!p) return null;
        return { srcs: [...new Set((p.points || []).map(pt => pt.source))],
                 html: _renderProspectScoutingReports(p) };
      }""")
    if not out:
        pytest.skip("every 2019 prospect carries a report")
    labels = {"fangraphs": "FanGraphs", "espn_draft": "ESPN draft",
              "mlb_pipeline_draft": "MLB Pipeline draft"}
    for key, lbl in labels.items():
        assert (lbl in out["html"]) == (key in out["srcs"]), (out["srcs"], out["html"])


# Owner answer M8-1 (2026-09-25): the unranked tail shows ONE Baseball America list at a
# time, the one the Pool (HS / College) filter names, and the HS list under All. Ranked
# rows are untouched and the two lists never sit in one sequence.
_POOL_SCAN = r"""
(args) => {
  const [year, pool] = args;
  state.draftPool = pool; state.pageSizes.draft = 5000; state.pages.draft = 1;
  restoreUIFromState(); render();
  const cls = ((DATA.draft || {}).classes || []).find(c => c.year === year) || {};
  const byKey = {};
  for (const p of (cls.prospects || [])) byKey[p.player_key] = p;
  const cards = [...document.querySelectorAll('.draft-card')].map(e => {
    const m = (e.getAttribute('onclick') || '').match(/goToDraftee\('([^']+)'/);
    const rec = m ? byKey[m[1]] : null;
    const ex = rec && rec.tool_grades && rec.tool_grades.baseballamerica_draft
      ? (rec.tool_grades.baseballamerica_draft._extras || {}) : {};
    return { ranked: !!rec && (rec.consensus_fv != null || rec.consensus_rank != null),
             scope: ex.ba_rank_is_global === false ? (ex.ba_scope || null) : null,
             type: rec ? (rec.player_type || '') : '' };
  });
  const head = (document.querySelector('.draft-class-note') || {}).textContent || '';
  return { cards, head };
}
"""


def _pool_of(scope):
    return "HS" if scope.upper().startswith("HS") else "College"


@pytest.mark.parametrize("year", [2027, 2028])
def test_rankings_show_one_ba_list_at_a_time(page, year):
    cls = _classes().get(year)
    if not cls:
        pytest.skip(f"no {year} class in the artifact")
    scoped = [p for p in cls.get("prospects") or []
              if p.get("consensus_fv") is None and p.get("consensus_rank") is None
              and (((p.get("tool_grades") or {}).get("baseballamerica_draft") or {})
                   .get("_extras") or {}).get("ba_rank_is_global") is False]
    n_by = {"HS": 0, "College": 0}
    for p in scoped:
        n_by[_pool_of(p["tool_grades"]["baseballamerica_draft"]["_extras"].get("ba_scope") or "")] += 1
    if not (n_by["HS"] and n_by["College"]):
        pytest.skip(f"{year}: the class does not carry both BA lists")
    _open(page, year)
    try:
        for pool, shown in (("all", "HS"), ("HS", "HS"), ("COL", "College")):
            got = page.evaluate(_POOL_SCAN, [year, pool])
            tail = [c for c in got["cards"] if not c["ranked"] and c["scope"]]
            assert tail, f"{year} Pool {pool}: no BA tail rendered"
            assert {_pool_of(c["scope"]) for c in tail} == {shown}, (
                f"{year} Pool {pool}: the tail mixes BA lists")
            assert len(tail) == n_by[shown], (year, pool, len(tail), n_by)
            other = "College" if shown == "HS" else "HS"
            assert f"the {n_by[other]} unranked prospects on BA's {other} list" in got["head"], got["head"]
            # Ranked rows are not touched by the one-list rule (Pool All keeps every one).
            if pool == "all":
                n_ranked = sum(1 for p in cls["prospects"]
                               if p.get("consensus_fv") is not None or p.get("consensus_rank") is not None)
                assert sum(c["ranked"] for c in got["cards"]) == n_ranked
        assert not page._draft_errs, page._draft_errs
    finally:
        page.evaluate("() => { state.draftPool = 'all'; restoreUIFromState(); render(); }")


def test_leaderboard_ba_switch_shows_one_list(page):
    years = [y for y in _years_with_scope_tail() if y >= 2027]
    if not years:
        pytest.skip("no current class with an unranked BA scope tail")
    year = max(years)
    _open(page, year, "leaderboard")
    scan = r"""
      () => {
        state.draftLeaderShowAll = true; renderDraft();
        return { chips: [...document.querySelectorAll('.draft-results-grid .draft-table tbody tr')]
                   .map(tr => tr.cells[0].textContent.trim()).filter(t => t.startsWith('BA ')),
                 active: [...document.querySelectorAll('[data-draft-lb-ba].active')].map(b => b.dataset.draftLbBa) };
      }"""
    try:
        page.evaluate("() => { state.draftPool = 'all'; }")
        got = page.evaluate(scan)
        assert got["chips"] and all(c.startswith("BA HS #") for c in got["chips"]), got["chips"][:5]
        assert got["active"] == ["HS"]
        page.click('[data-draft-lb-ba="COL"]')
        got = page.evaluate(scan)
        assert got["chips"] and all(c.startswith("BA Col #") for c in got["chips"]), got["chips"][:5]
        assert got["active"] == ["COL"]
        assert page.evaluate("() => state.draftPool") == "COL"
        assert not page._draft_errs, page._draft_errs
    finally:
        page.evaluate("() => { state.draftPool = 'all'; restoreUIFromState(); }")
