# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Surface-quality audit 2026-10-02, home and shell group (DISPLAY_home_shell).

One test per finding where a test can pin it. The shared runtime findings
(QHOA04 palette roles, QHOA05 tooltips, QHOP02 term index, QHOP06 palette
index) read assets/eephus-gl.js and the two index writers; the page findings
read the builders' own output.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GL = (ROOT / "assets" / "eephus-gl.js").read_text(encoding="utf-8")


# ---- QHOA04: the quick-search palette is a combobox over a listbox ----------

def test_palette_input_is_a_combobox_over_a_listbox_of_options():
    assert 'role="combobox"' in GL and 'aria-controls="qk-results"' in GL
    assert 'aria-expanded="false"' in GL
    assert 'id="qk-results" class="qk-results" role="listbox"' in GL
    assert 'role="option" aria-selected=' in GL and 'id="qk-opt-${i}"' in GL
    assert 'setAttribute("aria-activedescendant", "qk-opt-" + _qkActive)' in GL
    assert 'id="qk-status"' in GL and 'role="status" aria-live="polite"' in GL


# ---- QHOA05: tooltips survive the focus scroll; static terms are wired ------

def test_a_focused_term_keeps_its_tooltip_through_the_scroll_focus_causes():
    body = GL.split('window.addEventListener("scroll", () => {', 1)[1].split("}, { passive: true });", 1)[0]
    assert "span === document.activeElement" in body and "tipShow(span); return;" in body


def test_every_server_rendered_term_is_wired_for_screen_readers():
    i = GL.index("try { wire(document); } catch (e) { /* optional */ }")
    assert i < GL.index("window.EEPHUS_GL = {")


# ---- QHOP02: pages read a slim term index, not the 515 KB corpus ------------

def test_the_term_index_carries_only_the_fields_the_runtime_reads(tmp_path):
    import build_site as B
    out = B.write_glossary_index(tmp_path / "glossary_index.json")
    idx = json.loads(out.read_text(encoding="utf-8"))
    full = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in idx["entries"]] == [e["id"] for e in full["entries"]]
    assert all(set(e) <= set(B.GL_INDEX_FIELDS) for e in idx["entries"])
    assert all(e["definition"] == f["definition"] for e, f in zip(idx["entries"], full["entries"]))
    assert out.stat().st_size < 0.4 * (ROOT / "data" / "glossary.json").stat().st_size


def test_only_the_glossary_and_prospx_fetch_the_full_corpus():
    assert 'glossaryURL("glossary_index.json")' in GL
    assert re.search(r"/\^\\/\(glossary\|library\|prospx\)\(\\/\|\$\)/", GL)
    load = GL.split("  function load() {", 1)[1].split("\n  }\n", 1)[0]
    assert "FULL ? fetchJSON(GL_URL) : fetchJSON(GL_INDEX_URL).catch(() => fetchJSON(GL_URL))" in load
    # no eager fetch outside FULL pages: the only unconditional call is guarded
    assert "\n  if (FULL) load();\n" in GL.replace("\r\n", "\n")


# ---- QHOP06: the palette reads a five-field player index --------------------

def test_the_palette_player_index_is_the_five_fields_of_by_key(tmp_path, monkeypatch):
    import mlb_player_export as mpe
    links = {"generated_at": "2026-10-07",
             "byKey": {"juan_soto": {"key": "juan_soto", "name": "Juan Soto", "team": "NYM", "pos": "RF",
                                     "prospx": None, "mlbam": 665742, "fa": False, "proj": True},
                       "x": {"key": "x", "name": None}},
             "byMlbam": {"665742": {"key": "juan_soto"}}}
    monkeypatch.setattr(mpe, "DATA_DIR", tmp_path)
    doc = mpe.write_player_search(links)
    assert doc["fields"] == ["key", "name", "team", "pos", "prospx"]
    assert doc["rows"] == [["juan_soto", "Juan Soto", "NYM", "RF", ""]]
    assert json.loads((tmp_path / "player_search.json").read_text(encoding="utf-8")) == doc
    assert 'fetch("/data/player_search.json"' in GL and "H.linksStarted && H.linksStarted()" in GL


# ---- QHOP01: editorial logos come resized, not as 500 px masters ------------

def test_editorial_logos_come_through_the_combiner_at_twice_their_drawn_size():
    import build_site as B
    assert "mlb/500/nym.png&amp;h=48&amp;w=48" in B._team_logo("NYM")
    for cls in ("feed-logo", "otd-logo", "tk-logo"):
        assert "mlb/500/nym.png&amp;h=34&amp;w=34" in B._team_logo("NYM", cls)
    for page in ("index.html", "news/index.html", "history/index.html"):
        html = (ROOT / page).read_text(encoding="utf-8")
        assert not re.search(r'src="https://a\.espncdn\.com/i/teamlogos/mlb/500/[a-z]+\.png"', html), page


# ---- QHOP03: both webfont faces are preloaded from every head ---------------

def test_every_head_preloads_both_webfont_faces():
    import build_site as B
    heads = [B.page("t", "", "<p>x</p>"), B.page_home("t", "<main></main>")]
    heads += [(ROOT / p).read_text(encoding="utf-8") for p in B.HAND_AUTHORED_PAGES]
    for h in heads:
        head = h.split("</head>", 1)[0]
        for face in ("regular", "bold"):
            assert (f'<link rel="preload" href="/assets/fonts/pixelmplus12-{face}.woff2" '
                    'as="font" type="font/woff2" crossorigin>') in head
    t = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert B._ensure_font_preload(t) == t, "the hand-page insertion is idempotent"
    import subprocess
    pages = subprocess.run(["git", "ls-files", "*.html"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for rel in pages:
        txt = (ROOT / rel).read_text(encoding="utf-8")
        if '<link rel="stylesheet" href="/assets/site.css' in txt and not rel.startswith(("data/", "test_fixtures/")):
            assert 'pixelmplus12-regular.woff2" as="font"' in txt.split("</head>", 1)[0], rel


# ---- QHOA06 / QHOA07 / QHOA11 / QHOA12 / QHOA13: homepage markup ------------

def _home_html() -> str:
    return (ROOT / "index.html").read_text(encoding="utf-8")


def test_the_ticker_news_tag_is_out_of_the_tab_order_like_its_items():
    h = _home_html()
    tick = h[h.index('<div class="home-ticker" aria-hidden="true">'):h.index('<div class="ticker-track">')]
    assert '<a href="/news/" tabindex="-1">' in tick


def test_the_homepage_opens_on_a_skip_link_to_its_main_column():
    h = _home_html()
    body = h.split('<body class="eephus-page eephus-home">', 1)[1].lstrip()
    assert body.startswith('<a class="skip-link" href="#main">Skip to content</a>')
    assert '<main class="home-main" id="main" tabindex="-1">' in h


def test_the_homepage_has_one_h1_and_named_rail_landmarks():
    h = _home_html()
    assert h.count("<h1") == 1, "the wordmark is the page's one h1; the lead story is an h2"
    # HOME_4: the module list is the shared header's; the rail is the news.
    assert '<aside class="home-rail" id="home-rail" aria-label="MLB News">' in h
    assert '<nav class="band-links" aria-label="PROSPX sections">' in h
    assert ".lead-story h1, .lead-story h2 {" in (ROOT / "assets" / "site.css").read_text(encoding="utf-8")


def test_the_scatter_teaser_is_gone_with_its_contrast_finding():
    # QHOA12 was fixed in the teaser; HOME_4 (LANE_HOME 3.2 row 24) removed it.
    import build_site as B
    assert not hasattr(B, "_scatter_teaser")
    assert 'class="scatter-teaser"' not in _home_html()


def test_module_rows_name_their_numbers_for_screen_readers():
    import build_site as B
    p = {"player_key": "zz_nobody", "player_name": "A B", "org": "NYM", "position": "SS",
         "fv_close": 45, "overall_rank": 7}
    top = B._row_top(p, 7)
    assert '<span class="visually-hidden">rank </span><span class="row-rank">7</span>' in top
    assert '<span class="visually-hidden">FV </span><span class="fv-pill">' in top
    assert '<span class="visually-hidden">change </span><span class="row-delta' in B._row_mover(p, 3)
    g = {"debuted_value": {"wag": {"regressed_wag": 0.5}}}
    assert "WAG<span class=\"visually-hidden\">, WAR Above Grade </span>" in B._wag_badge(g)


# ---- QHOA08: filter chips are a labelled group of toggle buttons ------------

def test_filter_chips_expose_pressed_state_and_announce_the_count():
    for page, k in (("news/index.html", "news"), ("history/index.html", "hist")):
        h = (ROOT / page).read_text(encoding="utf-8")
        assert f'id="{k}-filter-bar" role="group" aria-labelledby="{k}-filter-label"' in h
        assert f'aria-pressed="true" data-{k}-filter="all"' in h
        assert f'id="{k}-filter-status" role="status" aria-live="polite"' in h
        assert "x.setAttribute('aria-pressed',x===b?'true':'false')" in h
        assert f"getElementById('{k}-filter-status')" in h


# ---- QHOA09: 44 px targets at phone width -----------------------------------

def test_phone_targets_on_the_home_group_are_44_px():
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8").replace("\r\n", "\n")
    block = css.split("/* 44 px touch targets at phone width on the home and shell pages (QHOA09):", 1)[1]
    block = block.split("\n}\n", 1)[0]
    for sel in (".news-app button.chip", ".feed-day-tm", ".kicker .see-all", ".xmod-link",
                ".eephus-footer-links a", ".px-404-rail a"):
        assert sel in block, sel
    assert "min-height: 44px" in block
    assert '<nav class="px-404-rail" aria-label="Modules">' in (ROOT / "404.html").read_text(encoding="utf-8")


# ---- QHOA10: theme toggles expose their state -------------------------------

def test_theme_toggles_carry_aria_pressed():
    import build_site as B
    assert 'b.setAttribute("aria-pressed",d)' in B.THEME_INIT
    assert 'document.addEventListener("DOMContentLoaded",eephusThemeSync)' in B.THEME_INIT
    assert "eephusThemeSync();}</script>" in B.THEME_INIT


# ---- QHOC03: the Model Accountability card counts every registry row --------

def test_the_model_card_lists_every_verdict_and_counts_registry_rows():
    import build_site as B
    strip = B._xmod_cards_html()
    i = strip.index("registry rows by verdict")
    card = strip[strip.rindex('<div class="xmod-card">', 0, i):]
    card = card[:card.index('<div class="xmod-card">', 10)] if card.count('<div class="xmod-card">') > 1 else card
    n = int(re.search(r"(\d+) registry rows by verdict", card).group(1))
    vals = [int(v) for v in re.findall(r'<span class="xmod-val">(\d+)</span>', card)]
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))["models"]
    assert n == len(reg) == sum(vals), (n, len(reg), vals)
    assert "Provisional" in card and "models with a predictive claim" not in strip


# ---- QHOC04 / QHOC07: the pill says what its number is ----------------------

def test_unsourced_grades_wear_the_dashed_production_pill_and_the_floor_says_floor(monkeypatch):
    import build_site as B
    monkeypatch.setitem(B._EFV_GRADES, "zz_prod", 28.6)
    monkeypatch.setitem(B._EFV_GRADES, "zz_v2", 41.2)
    monkeypatch.setitem(B._EFV_GRADES, "zz_floor", 20.0)
    monkeypatch.setitem(B._EFV_GRADES, "zz_graded", 52.4)
    monkeypatch.setattr(B, "_EFV_PROD_KEYS", {"zz_prod"})
    prod = B._fv_pill({"player_key": "zz_prod", "source_graded": False})
    assert 'class="fv-pill fv-prod" title="Production grade 29:' in prod and ">29</span>" in prod
    assert "production grade </span>" in prod
    v2 = B._fv_pill({"player_key": "zz_v2", "source_graded": False})
    assert "fv-prod" in v2 and 'title="eFV 41: no source has graded him yet' in v2
    floor = B._fv_pill({"player_key": "zz_floor", "source_graded": False})
    assert 'class="fv-pill fv-floor" title="eFV floor: no projection">floor</span>' in floor
    graded = B._fv_pill({"player_key": "zz_graded", "source_graded": True})
    assert 'class="fv-pill">52</span>' in graded and "fv-prod" not in graded


# ---- QHOC05: "Breakout" only for a player the flag marks --------------------

def test_hot_sample_tooltip_says_breakout_only_for_a_flagged_player():
    import build_site as B
    bucket = {"hot": [{"player_key": "zz_hot", "why": "Breakout", "line": "2.55 ERA"}]}
    for flag, word in ((False, "Hot sample"), (True, "Breakout")):
        p = {"player_key": "zz_hot", "player_name": "Z", "breakout_flag": flag}
        assert f'title="{word} - current-season sample"' in B._spotlight_html([p], bucket)


# ---- QHOC06: the /history/ intro reads its spans off the ledgers ------------

def test_history_intro_years_and_wag_gate_are_read_not_typed():
    import build_site as B
    tx = {"10-02": [("2015-10-02", "SGN", "a", "")], "10-03": [("2012-10-03", "TR", "b", "")]}
    il = {"10-02": [("2017-10-02", "b", "10-Day")]}
    assert B._hist_spans(tx, il) == " Transactions from 2012, IL placements from 2017."
    assert B._hist_spans({}, {}) == ""
    assert B._wag_gate_clause() == " once the player is past 200 PA or 80 IP"
    assert "Transactions from 2019" not in (ROOT / "history" / "index.html").read_text(encoding="utf-8")


# ---- QHOC11: one name per destination ---------------------------------------

def test_footer_rail_and_cards_use_one_name_per_destination():
    import build_site as B
    foot = B._footer()
    for href in ("/team/", "/history/", "/models/", "/glossary/", "/news/"):
        assert f'<a href="{href}">{B.PAGE_LABELS[href]}</a>' in foot, href
    assert B.PAGE_LABELS["/team/"] == dict((h, lab) for _k, lab, h in B.nav_leaves())["/team/"]
    assert ">About<" not in foot and ">This Day<" not in foot
    assert "Model Ledger" not in B._xmod_cards_html()


# ---- display pass: ledes stay one line, disclosures fold, nothing is lost ---

def test_news_and_history_fold_their_reading_rules_without_dropping_them():
    news = (ROOT / "news" / "index.html").read_text(encoding="utf-8")
    hist = (ROOT / "history" / "index.html").read_text(encoding="utf-8")
    for h in (news, hist):
        assert '<details class="news-how"><summary>How this works</summary>' in h
    how = news.split('<details class="news-how">', 1)[1].split("</details>", 1)[0]
    assert "eFV moves of 2 or more" in how and "not a re-grade" in how
    how = hist.split('<details class="news-how">', 1)[1].split("</details>", 1)[0]
    assert "IL placements from" in how and 'data-gl="wag"' in how and "model re-run dates" in how


def test_park_window_names_its_seasons_and_a_partial_last_season():
    import build_site as B
    assert B._park_window_label({"generated_at": "2026-07-23"}, 2026) == "2024-2026 window, 2026 through Jul 23"
    assert B._park_window_label({"generated_at": "2026-11-20"}, 2026) == "2024-2026 window"
    assert B._park_window_label({"generated_at": "2027-02-01"}, 2026) == "2024-2026 window"
    js = (ROOT / "assets" / "parks.js").read_text(encoding="utf-8")
    assert '(state.season - 2) + "-" + state.season + " window"' in js
    assert "function partialNote(year)" in js and '" games through "' in js
