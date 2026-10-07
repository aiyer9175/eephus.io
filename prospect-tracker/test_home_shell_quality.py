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
