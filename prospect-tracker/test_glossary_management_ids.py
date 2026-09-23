# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every glossary hook on /management/ resolves.

THE SPLIT THIS KILLS: build_management used _gl("sb_break_even") while management.js
used "steal_break_even", and NEITHER id existed in data/glossary.json, so both hooks
were inert. The page and the JS now share one slug set, each id exists, each carries
the management module tag, and the fourteen ids the spec names are present."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
GL = ROOT / "data" / "glossary.json"
PAGE = ROOT / "management" / "index.html"
JS = ROOT / "assets" / "management.js"

SPEC_IDS = ("decision_value", "execution_residual", "realized_mwpa", "dvs", "steal_break_even",
            "win_expectancy", "run_expectancy", "hook_z", "pen_z", "bench_z", "ibb_z", "visit_z",
            "li_at_decision", "manager_agent")


def _ids():
    g = json.loads(GL.read_text(encoding="utf-8"))
    return {e["id"]: e for e in g["entries"]}


def test_every_data_gl_hook_on_the_page_resolves():
    ids = _ids()
    hooks = set()
    if PAGE.exists():
        hooks |= set(re.findall(r'data-gl="([a-z_]+)"', PAGE.read_text(encoding="utf-8")))
    js = JS.read_text(encoding="utf-8")
    hooks |= set(re.findall(r'gl\("[^"]*",\s*"([a-z_]+)"\)', js))
    assert hooks, "no glossary hooks found on the page or in the JS"
    missing = sorted(h for h in hooks if h not in ids)
    assert not missing, f"glossary hooks that resolve to nothing: {missing}"
    assert "sb_break_even" not in hooks and "steal_break_even" in hooks


def test_the_management_ids_exist_with_the_module_tag():
    ids = _ids()
    for slug in SPEC_IDS:
        assert slug in ids, slug
        e = ids[slug]
        assert "management" in e["module"], slug
        assert e["shelf"] in ("ark", "industry", "foundation"), slug
        for ref in e.get("seeAlso", []):
            assert ref in ids, (slug, ref)
        for k in ("definition", "methodology", "formula", "example"):
            v = e.get(k) or ""
            assert chr(0x2014) not in v and chr(0x2013) not in v, (slug, k)
    import mgmt_decisions as MD
    assert ids["realized_mwpa"]["definition"] == MD.REALIZED_SENTENCE
    assert ids["manager_agent"]["definition"].startswith(MD.AGENT_SENTENCE)


def test_the_shell_no_longer_uses_the_dead_slug():
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    i = src.index("def build_management")
    j = src.index("def build_hof")
    assert "sb_break_even" not in src[i:j]
