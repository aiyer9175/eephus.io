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
