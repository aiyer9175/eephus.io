# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Library's Page Index and the 404 redirect map (LIBRARY_8, 2026-10-07).

1. THE INDEX IS GENERATED. The view was a hand list in assets/glossary.js that
   called itself every page with its own address and had missed 14 module
   roots. build_site.page_index_groups() now writes the rows from NAV_ITEMS and
   sitemap_pages(), so a page added to the sitemap without a name and a purpose
   line fails here. Every in-module view row is checked against the router of
   the module it opens, so a view that a module stops accepting cannot stay
   listed.

2. THE RETIRED FOLDERS STILL LAND. /teams/, /dfs/, /dynasty/ and /redraft/ were
   redirect folders with no link from the site (owner answer LB-Q3). The box
   answers a missing path with 404.html, and its redirect map
   (build_site.RETIRED_ROUTES) is driven here in a real JS engine against the
   stubs' own scripts, copied below as they shipped, so every bookmark lands
   exactly where the folder sent it, hash included.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site

ROOT = Path(__file__).resolve().parent

RETIRED = ("teams", "dfs", "dynasty", "redraft")


def _rows() -> list[list[str]]:
    return [r for g in build_site.page_index_groups() for r in g["rows"]]


# ---------------------------------------------------------------------------
# 1. The Page Index
# ---------------------------------------------------------------------------

def test_every_sitemap_and_nav_page_has_an_index_row_with_a_purpose():
    rows = {r[0]: r for r in _rows()}
    pages = [p for p, _f, _p in build_site.sitemap_pages()]
    pages += [h for _k, _l, h in build_site.nav_leaves()]
    missing = [p for p in pages if p not in rows]
    assert not missing, f"sitemap or nav pages with no Page Index row: {missing}"
    blank = [p for p in pages if not rows[p][1].strip() or not rows[p][2].strip()]
    assert not blank, (
        f"Page Index rows with no name or no purpose: {blank}. Add the page to "
        "build_site.PAGE_INDEX_PURPOSE (and PAGE_INDEX_NAMES when it has no nav entry).")


def test_the_index_has_its_four_groups_and_no_duplicate_row():
    groups = build_site.page_index_groups()
    assert [g["title"] for g in groups] == [
        "Modules", "Reference pages", "Views inside a module", "Player cards"]
    hrefs = [r[0] for r in _rows()]
    assert len(hrefs) == len(set(hrefs)), "a route is listed twice"
    for g in groups:
        assert g["rows"], f"{g['title']} is empty"
        for href, name, purpose in g["rows"]:
            assert href.startswith("/") and name and purpose, (href, name, purpose)


def test_no_retired_or_dark_address_is_listed():
    hrefs = [r[0] for r in _rows()]
    for d in RETIRED:
        assert f"/{d}/" not in hrefs
    assert not [h for h in hrefs if "tape=1" in h or "cards=1" in h], \
        "the index leaked a dark-preview route"


def _fa_views() -> set[str]:
    src = (ROOT / "assets" / "fa.js").read_text(encoding="utf-8")
    block = re.search(r"const VIEWS = \[(.*?)\];", src, re.S).group(1)
    views = set(re.findall(r'\["(\w+)",', block))
    dpw = (ROOT / "assets" / "fa_dpw.js").read_text(encoding="utf-8")
    if 'get("view") === "dpw"' in dpw:
        views.add("dpw")
    return views


def _projections_views() -> set[str]:
    src = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    m = re.search(r'\[([^\]]*)\]\.includes\(p\.get\("view"\)\)', src)
    return set(re.findall(r'"(\w+)"', m.group(1)))


def _prospx_tabs() -> tuple[set[str], set[str]]:
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    tabs = set(re.findall(r'class="section-tab[^"]*" data-section="([\w-]+)"', src))
    m = re.search(r"const YEAR_VIEWS = \[([^\]]*)\]", src)
    return tabs, set(re.findall(r'"([\w-]+)"', m.group(1)))


def _pal_hashes() -> tuple[set[str], set[str]]:
    src = (ROOT / "assets" / "pal.js").read_text(encoding="utf-8")
    sec = re.search(r"var m = /\^#\(([\w|]+)\)/\.exec\(h\)", src).group(1)
    pos = re.search(r"var v = /\^#posfit=\(([\w|]+)\)/\.exec\(h\)", src).group(1)
    return set(sec.split("|")), set(pos.split("|"))


def _fantasy_modules() -> set[str]:
    return set(re.findall(r'data-fantasymodule="(\w+)"', build_site.build_fantasy()))


def _glossary_views() -> set[str]:
    return {v["id"] for v in build_site.GLOSSARY_VIEWS
            if v.get("body") and v.get("listed", True) is not False}


def _routable(href: str) -> bool:
    """True when the module the href opens accepts its hash."""
    path, _, frag = href.partition("#")
    params = dict(p.split("=", 1) if "=" in p else (p, "") for p in frag.split("&"))
    if path == "/fa/":
        return set(params) == {"view"} and params["view"] in _fa_views()
    if path == "/projections/":
        return set(params) == {"view"} and params["view"] in _projections_views()
    if path == "/prospx/":
        tabs, dviews = _prospx_tabs()
        ok = params.get("tab") in tabs
        if "dview" in params:
            ok = ok and params["tab"] == "draft" and params["dview"] in dviews
        return ok and set(params) <= {"tab", "dview"}
    if path == "/pal/":
        sections, posfit = _pal_hashes()
        if "posfit" in params and params["posfit"]:
            return params["posfit"] in posfit
        return len(params) == 1 and next(iter(params)) in sections
    if path == "/fantasy/":
        return set(params) == {"m"} and params["m"] in _fantasy_modules()
    if path == "/glossary/":
        return set(params) == {"view"} and params["view"] in _glossary_views()
    return False


def test_every_in_module_view_is_accepted_by_its_module_router():
    bad = [href for href, _n, _p in build_site.PAGE_INDEX_VIEWS if not _routable(href)]
    assert not bad, (
        f"Page Index view rows their module's router does not accept: {bad}. "
        "Fix the row in build_site.PAGE_INDEX_VIEWS or the router.")


def test_library_view_rows_take_their_label_from_the_view_registry():
    groups = build_site.page_index_groups()
    views = {r[0]: r[1] for r in groups[2]["rows"]}
    labels = {v["id"]: v["label"] for v in build_site.GLOSSARY_VIEWS}
    for href, name, _p in build_site.PAGE_INDEX_VIEWS:
        if href.startswith("/glossary/") and name is None:
            vid = href.split("#view=", 1)[1]
            assert views[href] == f"{build_site.GLOSSARY_DISPLAY_NAME} · {labels[vid]}"


def test_the_glossary_shell_carries_the_generated_rows_and_the_client_reads_them():
    shell = build_site.build_glossary()
    m = re.search(r'<script type="application/json" id="page-index-data">(.*?)</script>',
                  shell, re.S)
    assert m, "the /glossary/ shell has no page-index-data script"
    assert json.loads(m.group(1)) == build_site.page_index_groups()
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert 'document.getElementById("page-index-data")' in js
    # the old hand list is gone from the client
    assert '["/parks/", "MiLB Park Factors"' not in js
    assert "Every page on eephus.io with its own address" in js


def test_the_built_glossary_page_lists_every_sitemap_page():
    path = ROOT / "glossary" / "index.html"
    if not path.exists():
        pytest.skip("glossary/index.html is generated by build_site and is not in the tree yet")
    m = re.search(r'<script type="application/json" id="page-index-data">(.*?)</script>',
                  path.read_text(encoding="utf-8"), re.S)
    assert m, "the built /glossary/ page predates the generated Page Index (rebuild it)"
    served = {r[0] for g in json.loads(m.group(1)) for r in g["rows"]}
    missing = [p for p, _f, _p in build_site.sitemap_pages() if p not in served]
    assert not missing, f"the built Page Index misses sitemap pages {missing} (rebuild /glossary/)"


# ---------------------------------------------------------------------------
# 2. The 404 redirect map
# ---------------------------------------------------------------------------

# The stubs' scripts exactly as they shipped (build_site.build_teams_redirect
# and _fantasy_redirect at 7dc79b24), the reference the map must reproduce.
_STUB_JS = {
    "teams": 'location.replace("/projections/#view=teams");',
    **{mod: ('(function(){var h=(location.hash||"").replace(/^#/,"").replace(/(^|&)m=[^&]*/g,"")'
             '.replace(/^&+/,"");\nlocation.replace("/fantasy/#m=' + mod + '"+(h?"&"+h:""));})();')
       for mod in ("dfs", "dynasty", "redraft")},
}

SAMPLE_HASHES = ("", "#", "#section=ros_sp&sys=sabr", "#m=dynasty&view=slate",
                 "#player=shohei_ohtani", "#a=1&m=x&b=2", "#team=NYY")


@pytest.fixture(scope="module")
def js():
    mini = pytest.importorskip("py_mini_racer")
    return mini.MiniRacer()


def _run(js, script: str, pathname: str, hash_: str):
    prelude = ("var __out = null; var location = {pathname: %s, hash: %s, "
               "replace: function (u) { __out = u; }};"
               % (json.dumps(pathname), json.dumps(hash_)))
    return js.eval("(function(){" + prelude + script + "; return __out;})()")


def _map_js() -> str:
    tag = build_site._retired_routes_script()
    assert tag.startswith("<script>") and tag.endswith("</script>")
    return tag[len("<script>"):-len("</script>")]


def test_the_map_is_the_one_constant_and_names_the_four_stubs():
    assert set(build_site.RETIRED_ROUTES) == {f"/{d}/" for d in RETIRED}
    assert build_site.RETIRED_ROUTES["/teams/"] == ("/projections/#view=teams", False)
    for mod in ("dfs", "dynasty", "redraft"):
        assert build_site.RETIRED_ROUTES[f"/{mod}/"] == (f"/fantasy/#m={mod}", True)


@pytest.mark.parametrize("name", RETIRED)
def test_each_retired_path_lands_where_its_stub_sent_it(js, name):
    for h in SAMPLE_HASHES:
        want = _run(js, _STUB_JS[name], f"/{name}/", h)
        for pathname in (f"/{name}/", f"/{name}", f"/{name}/index.html"):
            got = _run(js, _map_js(), pathname, h)
            assert got == want, (pathname, h, got, want)


def test_sample_targets_are_the_documented_ones(js):
    assert _run(js, _map_js(), "/redraft/", "#section=ros_sp&sys=sabr") == \
        "/fantasy/#m=redraft&section=ros_sp&sys=sabr"
    assert _run(js, _map_js(), "/dfs", "#m=dynasty&view=slate") == "/fantasy/#m=dfs&view=slate"
    assert _run(js, _map_js(), "/dynasty/index.html", "") == "/fantasy/#m=dynasty"
    assert _run(js, _map_js(), "/teams/", "#team=NYY") == "/projections/#view=teams"


@pytest.mark.parametrize("pathname", ["/", "/404.html", "/team/", "/teamsx/", "/fantasy/",
                                      "/teams/extra/", "/constructor/", "/__proto__/"])
def test_any_other_path_stays_on_the_not_found_page(js, pathname):
    assert _run(js, _map_js(), pathname, "#view=teams") is None


def test_the_404_page_runs_the_map_before_anything_else():
    page = build_site.build_404()
    head = page.split("<head>", 1)[1]
    assert head.lstrip().startswith(build_site._retired_routes_script())
    built = ROOT / "404.html"
    if built.exists():
        assert build_site._retired_routes_script() in built.read_text(encoding="utf-8"), \
            "404.html predates the redirect map (rebuild it)"


def test_the_retired_folders_and_their_writers_are_gone():
    for d in RETIRED:
        assert not (ROOT / d).exists(), f"{d}/ is back in the tree"
    for fn in ("build_teams_redirect", "_fantasy_redirect", "build_dynasty",
               "build_redraft", "build_dfs"):
        assert not hasattr(build_site, fn), fn
    assert "/teams/" not in build_site.build_robots()
    for target, _carry in build_site.RETIRED_ROUTES.values():
        assert (ROOT / target.split("#")[0].strip("/") / "index.html").exists() or \
            target.split("#")[0] in {h for _k, _l, h in build_site.nav_leaves()}
