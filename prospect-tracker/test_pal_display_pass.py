# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /pal/ display pass (DISPLAY_pal, 2026-10-08).

One test per surface-quality finding the pass fixed, where a test can pin it:

  QREA14  light-theme ink: the RP->SP FIT score, the RP->SP direction chip and
          the SP->RP chip read at AA on the paper they sit on (the SP->RP chip
          lost its .85 opacity, which put it at 3.88:1).
  QREA15  the Conversion History and Position Fit sub-view strips are real
          tabs (role, selected state, the panel they control); a header that
          does not sort does not show the sort cursor; the per-row FIT term
          keeps its glossary hook but leaves the Tab order.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from test_qual_light_theme_ink import SITE, _decl, _light_dark, _ratio, _rule

ROOT = Path(__file__).parent
PAL_JS = (ROOT / "assets" / "pal.js").read_text(encoding="utf-8")


# ---- QREA14 -----------------------------------------------------------------
@pytest.mark.parametrize("selector", [".pal-hi", ".pal-dir--rp2sp", ".pal-dir--sp2rp"])
def test_pal_score_and_direction_inks_read_aa_in_light(selector):
    light, dark = _light_dark()
    body = _rule(SITE, selector)
    assert _decl(body, "opacity") is None, f"{selector} dims its text with opacity again"
    colour = _decl(body, "color")
    tok = re.fullmatch(r"var\((--[a-z0-9-]+)\)", colour or "")
    assert tok, (selector, colour)
    ink = light[tok.group(1)]
    for g in ("--bg-primary", "--bg-secondary", "--bg-tertiary"):
        r = _ratio(ink, light[g])
        assert r >= 4.5, f"{selector} {ink} on {g} {light[g]} reads {r:.2f}:1"


def test_the_cyan_reading_ink_leaves_dark_on_its_accent():
    _, dark = _light_dark()
    assert dark["--text-cyan"] == dark["--accent-cyan"]


# ---- QREA15 -----------------------------------------------------------------
def test_unsortable_pal_headers_do_not_show_the_sort_cursor():
    body = _rule(SITE, ".pal-app .mlbstats-table th:not([data-col])")
    assert _decl(body, "cursor") == "default"


def test_sub_view_strips_are_tabs_that_name_their_panel():
    src = PAL_JS[PAL_JS.index("function viewTab"):PAL_JS.index("function historyToggle")]
    assert 'role="tab"' in src and "aria-selected" in src and 'aria-controls="pal-view"' in src
    assert 'id="pal-view" role="tabpanel"' in src
    toggle = PAL_JS[PAL_JS.index("function historyToggle"):PAL_JS.index("function renderHistory")]
    assert 'viewTab("data-histview"' in toggle
    assert 'viewTab("data-pfview"' in PAL_JS


def test_the_row_fit_term_keeps_its_hook_and_leaves_the_tab_order():
    fit = PAL_JS[PAL_JS.index("function fitCell"):PAL_JS.index("function dirClass")]
    assert 'data-gl="' in fit and 'tabindex="-1"' in fit


# ---- QREP10 -----------------------------------------------------------------
DATA = ROOT / "data"


def _load(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"data/{name} not built in this tree")
    return json.loads(p.read_text(encoding="utf-8"))


def test_the_page_core_and_tab_files_reassemble_the_artifact():
    import pal_export as P
    full = _load("pal.json")
    core = _load("pal_core.json")
    assert not set(core) & P.CORE_EXCLUDE, "a row block rode into the boot core"
    built = dict(core)
    for name, fname, keys in P.PAGE_SIDECARS:
        side = _load(fname)
        assert side.get("generated_at") == full.get("generated_at"), name
        for k in keys:
            built[k] = side[k]
    full.pop("prospect_watch_all", None)
    assert built == full


def test_the_artifact_is_compact_and_the_boot_core_is_small():
    for name in ("pal.json", "pal_core.json"):
        if not (DATA / name).exists():
            pytest.skip(f"data/{name} not built in this tree")
    assert b'{"generated_at":' == (DATA / "pal.json").read_bytes()[:16], "pal.json is pretty-printed again"
    assert (DATA / "pal_core.json").stat().st_size < 20_000


def test_the_page_names_every_tab_file_the_exporter_writes():
    import pal_export as P
    urls = set(re.findall(r'"/data/(pal_[a-z0-9_]+)\.json"', PAL_JS))
    want = {"pal_core"} | {f[:-5] for _, f, _k in P.PAGE_SIDECARS}
    assert want <= urls, want - urls


def _record_fetches(hash_):
    """Render with a fetch stub that answers each split file with only its own
    keys and records every URL asked for."""
    from py_mini_racer import MiniRacer
    import test_pal_smoke as S
    import pal_export as P
    sample = json.loads(S.SAMPLE)
    files = {"/data/pal_core.json": {k: v for k, v in sample.items() if k not in P.CORE_EXCLUDE},
             "/data/pal.json": sample}
    for name, fname, keys in P.PAGE_SIDECARS:
        files["/data/" + fname] = {k: sample.get(k, []) for k in keys}
    stub = ("var __urls=[]; var __files=" + json.dumps(files) + ";"
            "var fetch=function(u){__urls.push(u); var j=__files[u];"
            "return FT({ok:true,json:function(){return FT(j===undefined?{}:j);}});};")
    ctx = MiniRacer()
    ctx.eval(S._prelude(hash_) + stub + S.JS)
    return json.loads(ctx.eval("JSON.stringify(__urls)")), ctx.eval("__html['pal-app-root'] || ''")


def test_the_default_tab_boots_on_the_core_and_its_own_rows():
    pytest.importorskip("py_mini_racer")
    urls, html = _record_fetches("")
    data = [u for u in urls if u.startswith("/data/pal")]
    assert data == ["/data/pal_core.json", "/data/pal_sp2rp.json"], data
    assert "Power Starter" in html


def test_a_card_tab_reads_only_its_own_rows():
    pytest.importorskip("py_mini_racer")
    urls, html = _record_fetches("#prospects")
    data = [u for u in urls if u.startswith("/data/pal")]
    assert data == ["/data/pal_core.json", "/data/pal_prospect_watch.json"], data
    assert "Thin Starter Prospect" in html


# ---- QREC14 -----------------------------------------------------------------
def test_the_disclaimer_says_backtest_code_not_harness():
    import pal_export as P
    text = P._disclaimer({}, None)
    assert "the same repaired backtest code" in text and "harness" not in text
    served = (_load("pal.json").get("backtest") or {}).get("disclaimer") or ""
    assert "harness" not in served and "repaired backtest code" in served


# ---- QREC13 -----------------------------------------------------------------
def _render_ladder(pf: dict) -> str:
    """Render #posfit=ladder against a positional-fit payload (the smoke
    harness answers every fetch with the one payload it is given)."""
    pytest.importorskip("py_mini_racer")
    import test_pal_smoke as S
    from py_mini_racer import MiniRacer
    ctx = MiniRacer()
    ctx.eval(S._prelude("#posfit=ladder").replace(f"var SAMPLE={S.SAMPLE};", "var SAMPLE=" + json.dumps(pf) + ";") + S.JS)
    return ctx.eval("__html['pal-app-root'] || ''")


def test_the_window_note_reads_and_cites_the_recency_eval():
    pf = _load("positional_fit_ui.json")
    ev = _load("positional_ladder_recency_eval.json")
    W = pf["ladder"].get("windowEval")
    assert W, "the ladder block lost windowEval"
    res = ev["results"]["challenger_w"]
    assert W["dmae"] == res["dmae_mean"] and W["ci95"] == res["ci95"]
    assert W["nSeasons"] == len(ev["per_season"])
    assert W["nSeasonsBetter"] == sum(1 for v in ev["per_season"].values() if v["dmae_w"] > 0)
    html = _render_ladder(pf)
    want = "pool by %.2f runs per 650 PA (95%% CI %.2f to %.2f" % (W["dmae"], W["ci95"][0], W["ci95"][1])
    assert want in html, want
    assert "data/positional_ladder_recency_eval.json" in html
    note = PAL_JS[PAL_JS.index("function pfWindowNote"):PAL_JS.index("function pfFolkloreNote")]
    assert "0.10 runs" not in note and "0.08 to" not in note, "the window figures are typed again"


def test_without_the_eval_the_window_note_prints_no_figure():
    pf = _load("positional_fit_ui.json")
    pf = json.loads(json.dumps(pf))
    pf["ladder"].pop("windowEval", None)
    html = _render_ladder(pf)
    assert "chosen on held-out error, at the cost of wider intervals" in html
    assert "runs per 650 PA (95% CI" not in html.split("Window:")[1].split("</div>")[0]


@pytest.mark.parametrize("ci,word", [((-0.1826, -0.0936), "better than the model"),
                                     ((-0.05, 0.04), "not separable from the model"),
                                     ((0.02, 0.09), "worse than the model")])
def test_the_oaa_comparator_is_read_off_its_interval(ci, word):
    pf = json.loads(json.dumps(_load("positional_fit_ui.json")))
    pf["demotionNull"]["modelMinus"]["raw_oaa"] = {"mean": round((ci[0] + ci[1]) / 2, 4), "ci95": list(ci)}
    html = _render_ladder(pf)
    assert word in html, word
    others = {"better than the model", "not separable from the model", "worse than the model"} - {word}
    assert not any(o in html for o in others)


# ---- ORG FILTER (owner ask 2026-09-25) --------------------------------------
# Every Alchemy Lab list that names players carries the one org filter (the
# shared team picker over the hub's canonical club codes) and an Org column or
# card tag; the filter rides the hash as &org=XXX.
_ALIAS = {"AZ": "ARI", "CWS": "CHW", "KC": "KCR", "SD": "SDP", "SF": "SFG", "TB": "TBR",
          "WSH": "WSN", "OAK": "ATH", "FLA": "MIA"}


def _canon(t):
    t = (t or "").upper()
    return _ALIAS.get(t, t)


def test_every_player_list_renders_the_org_filter_and_honours_the_hash():
    pytest.importorskip("py_mini_racer")
    import test_pal_smoke as S
    from py_mini_racer import MiniRacer
    for hash_, name in (("#sp2rp", "Power Starter"), ("#rp2sp", "Deep Reliever"),
                        ("#history", "Converted Guy"), ("#pitchadd", "Deep Reliever"),
                        ("#platoon", "Reverse Guy"), ("#prospects", "Thin Starter Prospect")):
        ctx = MiniRacer()
        ctx.eval(S._prelude(hash_) + S.JS)
        html = ctx.eval("__html['pal-app-root'] || ''")
        assert 'id="pal-org" data-team-picker' in html, hash_
        assert name in html, hash_
        ctx = MiniRacer()
        ctx.eval(S._prelude(hash_ + "&org=ZZZ") + S.JS)
        html = ctx.eval("__html['pal-app-root'] || ''")
        assert name not in html and "No ZZZ rows match these filters." in html, hash_


def test_the_org_column_sorts_on_the_canonical_code():
    for cols in ("RP_COLS", "SP_COLS", "HISTORY_COLS", "PLATOON_COLS", "POSFIT_COLS"):
        block = PAL_JS[PAL_JS.index("var " + cols + " = ["):]
        block = block[:block.index("];")]
        assert '{ key: "org", label: "Org", kind: "org", asc: true }' in block, cols
    assert 'if (col && col.kind === "org") return sortByOrg(' in PAL_JS


@pytest.fixture(scope="module")
def site():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site
    with serve_site() as base, sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip("chromium unavailable: %s" % e)
        yield base, b
        b.close()


_COUNT = r"""
(kind) => {
  const root = document.querySelector('#pal-app-root');
  const rows = kind === 'cards' ? root.querySelectorAll('.pal-mix-grid .pal-mix-card')
    : root.querySelectorAll('.mlbstats-table tbody tr:not(.pal-why-tr)');
  return { n: rows.length, orgs: Array.from(rows).map(r => {
    const a = r.querySelector('a.club-link'); return a ? a.getAttribute('data-club') : null; }) };
}
"""


def _views():
    pal = _load("pal.json")
    pf = _load("positional_fit_ui.json")
    plat = [r for r in pal["reverse_platoon"] if (r.get("reverse") or r.get("extreme"))
            and (r.get("min_tbf") is None or r["min_tbf"] >= 100)]
    return {
        "sp2rp": (pal["sp2rp"], "team", "table"),
        "rp2sp": (pal["rp2sp"], "team", "table"),
        "history": (pal["history"], "team", "table"),
        "pitchadd": (pal["pitch_add"], "team", "cards"),
        "platoon": (plat, "team", "table"),
        "prospects": (pal["prospect_watch"], "org", "cards"),
        "posfit=board": (pf["rows"], "team", "table"),
    }


@pytest.mark.parametrize("org", ["LAD", "ARI", "ATH"])
def test_the_org_filter_narrows_each_list_exactly(site, org):
    base, b = site
    page = b.new_page(viewport={"width": 1280, "height": 900})
    page.route(re.compile(r"^https://a\.espncdn\.com/.*"), lambda route: route.abort())
    try:
        for view, (rows, field, kind) in _views().items():
            want = sum(1 for r in rows if _canon(r.get(field)) == org)
            page.goto("about:blank")
            page.goto(base + "pal/#" + view + "&org=" + org, wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(300)
            got = page.evaluate(_COUNT, kind)
            assert got["n"] == want, (view, org, want, got["n"])
            assert all(o == org for o in got["orgs"]), (view, org, got["orgs"])
    finally:
        page.close()


def test_picking_an_org_in_the_select_filters_and_writes_the_hash(site):
    base, b = site
    page = b.new_page(viewport={"width": 1280, "height": 900})
    page.route(re.compile(r"^https://a\.espncdn\.com/.*"), lambda route: route.abort())
    try:
        page.goto(base + "pal/#history", wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(300)
        rows = _load("pal.json")["history"]
        assert page.evaluate(_COUNT, "table")["n"] == len(rows)
        page.evaluate("""() => { const s = document.querySelector('#pal-org'); s.value = 'LAD';
            s.dispatchEvent(new Event('change', {bubbles: true})); }""")
        page.wait_for_timeout(300)
        assert page.evaluate(_COUNT, "table")["n"] == sum(1 for r in rows if _canon(r["team"]) == "LAD")
        assert page.evaluate("() => location.hash") == "#history&org=LAD"
        page.evaluate("""() => { const s = document.querySelector('#pal-org'); s.value = '';
            s.dispatchEvent(new Event('change', {bubbles: true})); }""")
        page.wait_for_timeout(300)
        assert page.evaluate(_COUNT, "table")["n"] == len(rows)
        assert page.evaluate("() => location.hash") == "#history"
    finally:
        page.close()


# ---- COPY TRIM (owner 2026-09-25: "get rid of a lot of bloated copy") --------
# The lede leads; the gate sentence, its caveat, the tier cuts, the coverage
# counts and the disclaimer move into one collapsed "How this works" fold. They
# are moved, never dropped, so the smoke tests that pin them still find them.
def _render_sections(hash_, payload=None):
    pytest.importorskip("py_mini_racer")
    import test_pal_smoke as S
    from py_mini_racer import MiniRacer
    pre = S._prelude(hash_)
    if payload is not None:
        pre = pre.replace(f"var SAMPLE={S.SAMPLE};", "var SAMPLE=" + json.dumps(payload) + ";")
    ctx = MiniRacer()
    ctx.eval(pre + S.JS)
    return ctx.eval("__html['pal-app-root'] || ''"), ctx.eval("__html['pal-banner'] || ''")


@pytest.mark.parametrize("hash_,folded", [
    ("#sp2rp", ("Gate: validated", "SP ERA is the need signal", "Bullpen Upside</b> (55.0+")),
    ("#rp2sp", ("Gate: structural screen", "Worth a Look</b> (55.0+")),
    ("#history", ("A screen, not a success-probability model.", "Arsenal shift: pitches")),
    ("#prospects", ("prospect pitchers scanned", "severe</b> at 20.0+")),
])
def test_the_method_prose_sits_in_the_fold_under_the_lede(hash_, folded):
    html, _ = _render_sections(hash_)
    fold = html.find('<details class="fa-valmap pal-how"><summary>How this works</summary>')
    assert fold >= 0, hash_
    for text in folded:
        at = html.find(text)
        assert at > fold, (hash_, text, "is above the fold or gone")


def test_the_banner_states_the_build_not_the_verdicts_again():
    import test_pal_smoke as S
    d = json.loads(S.SAMPLE)
    d["generated_at"] = "2026-10-03"
    _, banner = _render_sections("#sp2rp", d)
    assert "built 2026-10-03" in banner
    assert "candidate screen, not a projection" in banner
    assert "SP&rarr;RP:" not in banner and "RP&rarr;SP:" not in banner, "the banner repeats the masthead"
    assert "[provisional]" in banner
