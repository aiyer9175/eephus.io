# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Scaffold guards for /arbitration/.

These assert the wiring whose failure is SILENT: a module that renders locally,
passes every content test, and 404s in production. No page-render assertions
here, so this file passes before build_site.main() has ever run.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent


def _mlb_children():
    for item in B.NAV_ITEMS:
        if isinstance(item, dict) and item.get("group") == "MLB Modules":
            return item["children"]
    raise AssertionError("MLB Modules group missing")


def test_arbitration_is_a_leaf_of_the_mlb_modules_group():
    assert ("arbitration", "Arbitration", "/arbitration/") in _mlb_children()


# The MLB Modules order as it stood when Arbitration was appended. A new module
# must go AFTER these, never between them.
_MLB_PREFIX_AT_ARBITRATION = ("fa", "projections", "mlbstats", "pal",
                              "trademachine", "arbitration")


def test_a_new_module_appends_and_never_reorders_the_existing_ones():
    """The invariant is STABLE ORDER for the modules already there, not that any
    one of them stays last forever.

    This used to assert `_mlb_children()[-1] == "arbitration"`, which is what
    "appended last" meant on the day Arbitration shipped and which then blocked
    the next two modules from being added at all. Nothing indexes the nav by
    position (checked: no caller subscripts NAV_ITEMS, nav_leaves() or the
    group's children), so what actually matters is that appending does not move
    anything that was already in the list.
    """
    keys = tuple(k for k, _l, _h in _mlb_children())
    # 2026-09-23: the Franchise hub sits FIRST in the group by owner decision
    # (the hub before the modules, not a module appended to them), so it is
    # skipped here and the invariant still reads the modules' own order.
    keys = tuple(k for k in keys if k != "franchise")
    assert keys[:len(_MLB_PREFIX_AT_ARBITRATION)] == _MLB_PREFIX_AT_ARBITRATION, (
        f"the MLB Modules group was REORDERED, not appended to: {keys}")


def test_group_keys_never_collide_with_leaf_keys():
    """_nav() matches `active` against LEAF keys only, so a group key that
    shadows a leaf silently mis-highlights the nav."""
    leaves = {k for k, _l, _h in B.nav_leaves()}
    groups = {i["key"] for i in B.NAV_ITEMS if isinstance(i, dict)}
    assert not (leaves & groups)
    assert "arbitration" in leaves


def test_nav_leaves_are_unique():
    keys = [k for k, _l, _h in B.nav_leaves()]
    hrefs = [h for _k, _l, h in B.nav_leaves()]
    assert len(keys) == len(set(keys))
    assert len(hrefs) == len(set(hrefs))


@pytest.mark.parametrize("rel", [
    "prospx/index.html",
    "collegesavant/index.html",
    "collegesavant/pitcher_index.html",
])
def test_the_three_static_nav_mirrors_carry_it(rel):
    """These three pages hand-maintain a copy of the nav. A partial edit is a
    red suite rather than a silent 404, which is the whole reason the mirror
    test exists - and it is why a new leaf must land in the same commit."""
    s = (ROOT / rel).read_text("utf-8", errors="ignore")
    assert 'href="/arbitration/"' in s
    assert ">Arbitration<" in s


def test_module_stage_row_exists_and_says_what_is_gated():
    chip, title = B.MODULE_STAGE["arbitration"]
    assert chip and title
    # The stage text must not overclaim: arb2+ is a NULL and the chip says so.
    assert "multiplier" in title


def test_builder_is_registered_in_main_in_the_exact_literal_form():
    """tools/gen_audit_docs parses _write("<rel>", <fn>()) by regex out of
    main()'s source, so a variable form drops the route from SITE_MAP.md
    without failing anything."""
    src = inspect.getsource(B.main)
    assert '_write("arbitration/index.html", build_arbitration())' in src


def test_route_is_in_the_sitemap():
    assert f"<loc>{B.SITE_ORIGIN}/arbitration/</loc>" in B.build_sitemap([])


def test_publish_paths_carries_arbitration():
    """Omitting this 404s the live module while every test stays green. The
    file's own header records that incident from 2026-07-14."""
    lines = [l.strip() for l in
             (ROOT / "deploy" / "publish_paths.txt").read_text("utf-8").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    assert "arbitration" in lines


def test_the_emdash_gate_scans_the_page():
    s = (ROOT / "tools" / "strip_emdashes.py").read_text("utf-8")
    assert '"arbitration/index.html"' in s


def test_the_page_dir_is_pruned_from_collection():
    s = (ROOT / "pytest.ini").read_text("utf-8")
    assert re.search(r"^\s+arbitration\s*$", s, re.M)


def test_asset_version_constant_exists_and_a_missing_file_hashes_to_one():
    """The whole build order rests on this: the scaffold can land and stay green
    before assets/arbitration.js exists."""
    assert isinstance(B._ARB_VER, str) and B._ARB_VER
    assert B._asset_ver("assets/definitely-not-here.js") == "1"


def test_route_note_is_registered():
    import tools.gen_audit_docs as G
    assert "arbitration/index.html" in G._ROUTE_NOTES


def test_sidebar_icon_is_a_single_terminal_safe_codepoint():
    src = inspect.getsource(B.build_home)
    m = re.search(r'"arbitration":\s*"([^"]+)"', src)
    assert m, "sidebar icon missing"
    g = m.group(1)
    assert len(g) == 1 and ord(g) < 0x1F000


def test_the_model_panel_is_server_rendered():
    """An accountability surface that needs a script to say what it measured is
    not an accountability surface."""
    html = B.build_arbitration()
    assert "arb-panel-model" in html
    assert "What this model cannot tell you" in html
    # The verdicts are in the HTML itself, not fetched.
    assert "arb-scorecard" in html


def test_every_section_has_a_real_tabpanel():
    """/mlbstats/ and /pal/ emit role=tab with no tabpanel and no aria-controls,
    so a screen reader announces a tab and cannot find what it controls. This
    module is built correctly from day one."""
    html = B.build_arbitration()
    assert len(re.findall(r'role="tabpanel"', html)) == 4
    assert len(re.findall(r"aria-controls=", html)) == 4


def test_the_client_never_fetches_an_excluded_data_file():
    """Duplicates test_publish_manifest on purpose, with a message naming why:
    the failure is a 404 in production only."""
    src = (ROOT / "assets" / "arbitration.js").read_text("utf-8")
    excl = [l.strip() for l in
            (ROOT / "deploy" / "data_exclude.txt").read_text("utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]
    for name in excl:
        assert name not in src, f"{name} never ships to the webroot"
