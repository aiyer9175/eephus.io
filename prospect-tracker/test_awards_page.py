# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /awards/ assets (AWARDS_7_PAGE_SELECTIONS; AWARDS_PLAN 5.12 'Theme and the pixel
idiom', 5.14 'Motion and budgets' and 6 'Invariants and tests' row I15).

Budgets: assets/awards.js at most 60 KB raw and assets/awards.css at most 12 KB. No
@keyframes in awards.css and no requestAnimationFrame in awards.js (the page adds no motion;
the loading lamp is EephusState's). awards.css types no hex and holds no theme media query.
The two Awards symbols are drawn in the sprite and mapped in ICON_FOR. The client reads the
payload's own fields for every number and label it prints, never a typed WAR unit. No test
opens a socket or a browser; the page against the payload is tools/awards_render_check.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import build_site as B

ROOT = Path(__file__).resolve().parent
JS = ROOT / "assets" / "awards.js"
CSS = ROOT / "assets" / "awards.css"
HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{1,5})?\b")


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


def test_budgets():
    assert JS.stat().st_size <= 60 * 1024, JS.stat().st_size
    assert CSS.stat().st_size <= 12 * 1024, CSS.stat().st_size


def test_no_new_motion():
    assert "@keyframes" not in _css()
    assert not re.search(r"\banimation(-[a-z]+)?\s*:", _css())
    assert "requestAnimationFrame" not in _js()


def test_css_is_tokens_only():
    css = _css()
    assert not HEX.findall(css), HEX.findall(css)
    assert "prefers-color-scheme" not in css
    assert "@media (prefers" not in css
    for prop in re.findall(r"(?:^|[;{\s])(?:color|fill|stroke|background(?:-color)?)\s*:\s*([^;}]+)", css):
        v = prop.strip()
        assert v.startswith(("var(", "none", "inherit", "transparent", "color-mix(in srgb, currentColor")), v


def test_js_types_no_colour_and_reuses_the_shared_pieces():
    js = _js()
    assert not HEX.findall(js), HEX.findall(js)
    assert "rgb(" not in js and "hsl(" not in js
    assert "EephusState" in js and "EephusTiers" in js
    assert "EephusUI.wireTablist" in js, "the shared tablist handler (QCLA19) is reused"
    for kind in ("loading", "failed", "unmeasured"):
        assert f'stateBox("{kind}"' in js


def test_the_state_sentences_are_the_plans():
    js = _js()
    for s in ("Loading the awards.", "The awards could not load.", "This section is being built.",
              "Weekly standings are not on file for ", ". The card shows the season-end order only.",
              "numbers may be out of date."):
        assert s in js, s


def test_share_renders_only_when_the_shell_names_the_engine():
    """AWARDS_10: Share is a chip only when the mount carries data-gfx-js, and the engine
    loads on the first press (never in the cold paint)."""
    js = _js()
    assert 'var GFX = root.getAttribute("data-gfx-js")' in js
    assert "return GFX ? '<button type=\"button\" class=\"aw-share\"" in js
    out = B.build_awards(live=True)
    assert f'data-gfx-js="/assets/eephus-gfx.js?v={B._asset_ver("assets/eephus-gfx.js")}"' in out
    assert '<script src="/assets/eephus-gfx.js' not in out, "the engine is not in the cold paint"
    assert 'kind: "awards"' in js and "drawAwards" in js


def test_no_war_unit_is_typed_in_the_client():
    js = _js()
    for unit in ("eWAR v2", "eWAR v3", "fWAR"):
        assert unit not in js, unit
    assert "rule.unit" in js and "dr.unit_label" in js


def test_the_awards_symbols_are_drawn_and_mapped():
    keys = set(json.loads((ROOT / "assets" / "eephus-icons.json").read_text(encoding="utf-8")))
    svg = (ROOT / "assets" / "eephus-icons.svg").read_text(encoding="utf-8")
    for k in ("aw-podium", "aw-ballot"):
        assert k in keys and B.ICON_FOR[k] == k and k in B.ICON_KEYS
        assert f'<symbol id="i-{k}"' in svg
    assert B.ICON_FOR["hof"] == "hof", "the leaf icon stays i-hof"
    assert "#i-aw-ballot" not in _js() and 'ico("aw-ballot", 12)' in _js()
    assert 'ico("aw-podium", 16)' in _js()


def test_lamp_geometry_is_the_plans():
    js = _js()
    assert "s: { w: 4, h: 10, p: 5 }, l: { w: 6, h: 12, p: 8 }" in js
    assert "MAX_LAMPS = 60" in js
    assert "p === 1 ? 12 : p === 2 ? 8 : 4" in js
    assert 'shape-rendering="crispEdges"' in js
    assert 'preserveAspectRatio="none"' not in js



# --- My Ballot (AWARDS_9; AWARDS_PLAN 5.8, 5.14 and 6 rows I14 and I15) -------------------------

BJS = ROOT / "assets" / "awards-ballot.js"
BCSS = ROOT / "assets" / "awards-ballot.css"


def _bjs() -> str:
    return BJS.read_text(encoding="utf-8")


def _served_bytes(p: Path) -> int:
    """The served file is the git blob, which holds LF line ends; a Windows working tree
    checks it out with CRLF, so the budget counts the LF bytes."""
    return len(p.read_bytes().replace(b"\r\n", b"\n"))


def test_ballot_budgets_and_no_motion():
    assert _served_bytes(BJS) <= 35 * 1024, _served_bytes(BJS)
    assert _served_bytes(BCSS) <= 10 * 1024, _served_bytes(BCSS)
    css = BCSS.read_text(encoding="utf-8")
    assert "@keyframes" not in css and not re.search(r"\banimation(-[a-z]+)?\s*:", css)
    assert "transition" not in css
    assert "requestAnimationFrame" not in _bjs()


def test_ballot_css_is_tokens_only():
    css = BCSS.read_text(encoding="utf-8")
    assert not HEX.findall(css), HEX.findall(css)
    assert "prefers-color-scheme" not in css and "--vt-" not in css
    for prop in re.findall(r"(?:^|[;{\s])(?:color|fill|stroke|background(?:-color)?)\s*:\s*([^;}]+)", css):
        v = prop.strip()
        assert v.startswith(("var(", "none", "inherit", "transparent")), v


def test_ballot_loads_lazily_from_stamped_urls():
    out = B.build_awards(live=True)
    assert f'data-ballot-js="/assets/awards-ballot.js?v={B._asset_ver("assets/awards-ballot.js")}"' in out
    assert f'data-ballot-css="/assets/awards-ballot.css?v={B._asset_ver("assets/awards-ballot.css")}"' in out
    assert '<script src="/assets/awards-ballot.js' not in out, "the chunk is not in the cold paint"
    js = _js()
    assert 'root.getAttribute("data-ballot-js")' in js and 'if (s.section === "ballot") { ballot(panel, s); return; }' in js
    assert "awards_candidates" not in js, "the cold paint never names the candidate file"
    bjs = _bjs()
    assert bjs.count("fetch(") == 1 and 'fetch("/data/awards_candidates_" + season + ".json"' in bjs


def test_ballot_storage_is_one_key_inside_try():
    js = _bjs()
    assert js.count('"eephus.awards.ballot.v1"') == 1
    for banned in ("sessionStorage", "indexedDB", "document.cookie", "XMLHttpRequest", "sendBeacon", "navigator.send"):
        assert banned not in js, banned
    uses = [m.start() for m in re.finditer(r"localStorage\.(getItem|setItem)", js)]
    assert len(uses) == 2
    for i in uses:
        assert "try {" in js[max(0, i - 80):i], "storage access outside try"
    assert "}, 300);" in js, "written 300 ms after an edit"


def test_ballot_link_alphabet_and_ids():
    js = _bjs()
    assert "/^[a-z0-9._:,-]+$/" in js
    assert "toString(36)" in js and "parseInt(tok, 36)" in js
    assert "/^c[a-z]{2,4}$/" in js, "Manager ids are c plus a club code"
    assert 'history.replaceState(null, "", "#" + hashOf(s))' in _js()


def test_ballot_never_prefills_or_scores():
    js = _bjs()
    assert "score_display" in js       # the rule's served number in its own column only
    for banned in ("agree", "same as", "overlap", "percent of", "suggested"):
        assert banned not in js.lower(), banned
    assert "Eephus place" in js and 'role="switch" data-act="${act}"' in js
    assert "Show the eephus selection" in js


def test_ballot_copy_is_the_plans():
    js = _bjs()
    for s in ("Loading the candidates.", "The candidates could not load.",
              "You are viewing a shared ballot. It is not saved in this browser.", "Copy to my ballot",
              "Keep mine", "Saved in this browser only. Nothing is sent to eephus.io; there is no account behind this page.",
              "This browser is not saving your ballot (private window or blocked storage).",
              "Below the rule&#39;s playing-time floor.", "Outside the site&#39;s rookie test.",
              "Two-way: batting and pitching shown.", "Hitters", "Pitchers", "Show every player",
              "Above the floor only", "Your slot", "Copy link", "Copy text", "Move up", "Move down", "Remove"):
        assert s in js, s
    for unit in ("eWAR v2", "eWAR v3", "fWAR"):
        assert unit not in js, unit
    # AWARDS_10: Save image renders only when the page carries the engine (cx.gfx), and the
    # save note names the image only then; the chunk never names the engine itself.
    assert '(cx.gfx ? btn("img", "Save image") : "")' in js
    assert 'NOTE.ok + (cx.gfx ? " or save the image." : ".")' in js
    assert "eephus-gfx" not in js and "EEPHUS_GFX" not in js
