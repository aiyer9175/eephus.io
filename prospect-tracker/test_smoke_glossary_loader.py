"""SRE04: /glossary/ paints the pixel loader while data/glossary.json loads.

eephus-gl.js fetches data/glossary.json once for the whole site; assets/
glossary.js waited on its 'eephus-glossary-ready' event and painted nothing
until then, so every view (Source Comparison included) showed an empty
bordered strip under the search box: 0 px-state boxes and 0 lob lamps with
the file held for 1.5 s, and a blank page forever on a rejected fetch.

The page must load the shared state component (assets/eephus-state.js), and
glossary.js must paint EephusState's loading kind on the boot path before the
ready event resolves, with the failed kind wired to the failure event.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_glossary_paints_the_state_loader_before_glossary_json_resolves():
    page = (ROOT / "glossary" / "index.html").read_text(encoding="utf-8")
    src = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    boot = re.search(r"\n  function boot\(\) \{.*?\n  \}\n", src, re.S)
    paint = re.search(r"\n  function _paintGlState\(el\) \{.*?\n  \}\n", src, re.S)
    router = re.search(r"\n  function render\(\) \{.*?\n  \}\n", src, re.S)
    ok = (
        re.search(r'<script src="/assets/eephus-state\.js\?v=[0-9a-f]{8}" defer>', page) is not None
        and boot is not None and paint is not None and router is not None
        # boot listens for ready AND failure, and paints before either fires
        and re.search(r'addEventListener\("eephus-glossary-ready", start', boot.group(0)) is not None
        and 'addEventListener("eephus-glossary-failed"' in boot.group(0)
        and re.search(r'_GL_STATE = window\.EEPHUS_GLOSSARY_FAILED \? "failed" : "loading";\s*render\(\);',
                      boot.group(0)) is not None
        # the router short-circuits to the state box until the data is ready
        and re.search(r'if \(_GL_STATE !== "ready"\) \{ _paintGlState\(', router.group(0)) is not None
        # the box is the shared component's loading and failed kinds
        and 'S.html("loading"' in paint.group(0)
        and 'S.html("failed"' in paint.group(0)
        and "window.EephusState" in paint.group(0)
    )
    assert ok, ("glossary.js must paint window.EephusState's loading kind before glossary.json resolves "
                "(and the failed kind on a rejected fetch), and glossary/index.html must load eephus-state.js")
