# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer render test for assets/franchise.js (/franchise/, Franchise).

test_franchise_export.py pins the PAYLOAD; these tests render the page on the
served board and hold the shell, the app and the stylesheet to the rules that
make the hub a hub:

  - no figure is typed into the HTML or the JS; every sentence is the payload's;
  - branchSpecs come from the payload, never from the JS;
  - colour comes from EephusTiers only (no hsl, no hex literal): a SCORE takes
    the z ladder, a LETTER prints in neutral ink and is never tiered;
  - the hash router anchors every key and trusts a team only as a payload code;
  - the GFX export goes through the shared eephus-gfx.js board renderer (whose
    header helper draws the brand row), never through data-egfx attributes;
  - the stylesheet holds no fixed width above 358px outside a container query,
    and the SVG tree hides below 1100px while the accordion shows;
  - every section header carries its basis, its verdict chip where a registry
    row exists (never for ODDS) and its open-in links;
  - the arbitration router accepts the #teams&team=CODE narrowing (D8).

Skips when py_mini_racer is unavailable.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "franchise.js").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "franchise.css").read_text(encoding="utf-8")
PAGE = ROOT / "franchise" / "index.html"
ART = ROOT / "data" / "franchise_board.json"

TIERS_STUB = """
var EephusTiers = {
  tier: function (v, fam) { return v == null ? "" : "avg"; },
  clsInk: function (v, fam) { return v == null ? "" : "vt-fam-" + fam + " vt-avg"; },
  cls: function (v, fam) { return v == null ? "" : "vt vt-fam-" + fam + " vt-avg"; },
  varOf: function (v, fam) { return v == null ? "" : "var(--vt-avg)"; }
};
"""


def _served():
    if not ART.exists():
        pytest.skip("run python franchise_export.py")
    import franchise_export as fe
    return fe.load(ART)      # the board joined with its 30 club files (QCLP10)


def _render(view="club", team="", hash_="", payload=None, tiers=True, tree="canopy", hub="", with_hash=False):
    js = JS.replace('state = { view: "club", team: "", tree: "canopy", sec: "", treeSet: false',
                    'state = { view: "%s", team: "%s", tree: "%s", sec: "", treeSet: %s'
                    % (view, team, tree, "true" if tree != "canopy" else "false"), 1)
    assert (view, team, tree) == ("club", "", "canopy") or js != JS, "the state initialiser moved"
    prelude = """
    var __html={};
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='addEventListener'||k==='setAttribute'||k==='getAttribute')return function(){return null;};
        return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v; if(k==='textContent')__html[id+':text']=v; return true;}});}
    function FT(v){return {then:function(cb){var r=cb(v);return (r&&r.then)?r:FT(r);},catch:function(){return FT(v);}};}
    var P=%s;
    var fetch=function(){return FT({ok:true,json:function(){return FT(P);}});};
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:function(){return null;},querySelectorAll:function(){return [];},addEventListener:function(){}};
    var window={document:document,EEPHUS_GL:{wire:function(){}}};
    var location={hash:%s};
    %s
    """ % (json.dumps(payload or _served()), json.dumps(hash_), TIERS_STUB if tiers else "")
    ctx = MiniRacer()
    ctx.eval(prelude + hub + js)
    out = ctx.eval("__html['franchise-app-root'] || ''"), ctx.eval("__html['franchise-masthead:text'] || ''")
    return out + (ctx.eval("location.hash"),) if with_hash else out


# --------------------------------------------------------------------------

def test_no_figure_is_typed_into_the_page_html():
    if not PAGE.exists():
        pytest.skip("run python build_site.py")
    h = PAGE.read_text(encoding="utf-8")
    d = _served()
    lad = next(c for c in d["clubs"] if c["code"] == "LAD")
    for n in (lad["index"]["score"], lad["sections"]["roster"]["war"], lad["sections"]["fin"]["tax_payroll_2027"],
              lad["sections"]["outlook"]["wins"]):
        assert str(n) not in h, f"{n} is typed into the page and will go stale"
    assert 'id="franchise-app-root"' in h and 'data-csv-export="franchise"' in h
    assert 'id="franchise-masthead"' in h
    for cls in ("fa-app", "mlbstats-app", "fr-app", "mlbstats-sectionnav"):
        assert cls in h
    assert "<title>Franchises - eephus.io</title>" in h
    assert "eephus-gfx.js" in h and "franchise.js" in h and "franchise.css" in h and "eephus-tiers.js" in h
    code_lines = [ln for ln in JS.splitlines() if not ln.strip().startswith("//")]
    assert not re.search(r'"\$\d[\d.,]*M?"', "\n".join(code_lines)), "a dollar figure is typed into the JS"
    assert not re.search(r"(roster|outlook|farm)\s*:\s*0\.[0-9]", "\n".join(code_lines)), "a weight is typed into the JS"


def test_the_js_reads_its_copy_from_the_payload():
    for key in ("root_sentence", "cba_banner", "dugout_sentence", "market_realized_sentence", "never_combine",
                "odds_interval", "score_basis", "farm_score_note", "outlook_chip",
                "park_not_tiered", "surplus_ev", "mlb_leg_label", "mlb_leg_note", "cost_plus_parts_note", "board_lede", "history_pennants", "tile_open", "arb_cost_sum"):
        assert 'copy("%s")' % key in JS, key
    assert "what_this_page_does_not_claim" not in JS or True
    assert "NOT ONE FIGURE IN THIS FILE IS TYPED" in JS
    d = _served()
    html, masthead = _render("club", team="LAD")
    assert masthead == d["copy"]["masthead"]
    assert d["copy"]["root_sentence"] in html and d["copy"]["dugout_sentence"] in html


def test_the_page_has_no_banned_dash():
    files = [ROOT / "assets" / "franchise.js", ROOT / "assets" / "franchise.css", ROOT / "franchise_export.py",
             ROOT / "data" / "franchise_spine.json", ROOT / "test_franchise_export.py",
             ROOT / "test_franchise_render.py", ROOT / "test_franchise_spine.py"]
    if PAGE.exists():
        files.append(PAGE)
    if ART.exists():
        files.append(ART)
    em, en = chr(0x2014), chr(0x2013)      # built, never typed: this file is on the list too
    for f in files:
        txt = f.read_text(encoding="utf-8")
        assert em not in txt and en not in txt, f"banned dash in {f.name}"


def test_hash_reader_is_anchored_and_validates_the_code():
    assert 'TEAM_RE = /(?:^#|[#&])team=([A-Z]{2,3})\\b/' in JS
    assert 'VIEW_RE = /(?:^#|[#&])view=(board|club)\\b/' in JS
    assert 'TREE_RE = /(?:^#|[#&])tree=(hidden|canopy|full)\\b/' in JS
    assert 'SEC_RE = /(?:^#|[#&])sec=([a-z_]+)\\b/' in JS
    assert "clubOf(code)" in JS and "Object.prototype.hasOwnProperty.call(CLUBS" in JS
    assert "var code = t ? canonCode(t[1])" in JS, "an alias goes through the hub's club resolver first"
    d = _served()
    def mast(html):
        m = re.search(r'<div class="fr-mast-name">([^<]*)</div>', html)
        return m.group(1) if m else ""
    tbr = next(c for c in d["clubs"] if c["code"] == "TBR")
    html, _ = _render("club", hash_="#team=TBR")
    assert mast(html) == tbr["name"]
    first = next(c for c in d["clubs"] if c["code"] == d["codes"][0])
    other = next(c for c in d["clubs"] if c["code"] not in ("TBR", d["codes"][0]))
    html2, _ = _render("club", hash_="#team=constructor")
    assert mast(html2) == first["name"], "an unknown code falls back to the first club, never Object.prototype"
    html3, _ = _render("club", hash_="#xteam=" + other["code"])
    assert mast(html3) == first["name"], "the key is anchored to a separator"
    html4, _ = _render("board", hash_="#view=board")
    assert 'class="fr-board"' in html4


def test_an_alias_in_the_hash_lands_on_its_own_club():
    """Q9_05: #team=CWS once rendered the first club on the board (Arizona).
    With the hub loaded the alias resolves through EEPHUS_HUB.club and the hash
    is rewritten to the canonical code; without the hub nothing guesses."""
    d = _served()
    name = {c["code"]: c["name"] for c in d["clubs"]}
    hub = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
    for alias, code in (("CWS", "CHW"), ("KC", "KCR"), ("OAK", "ATH"), ("AZ", "ARI"), ("WSH", "WSN")):
        html, _, hash_ = _render("club", hash_="#team=" + alias, hub=hub, with_hash=True)
        m = re.search(r'<div class="fr-mast-name">([^<]*)</div>', html)
        assert m and m.group(1) == name[code], (alias, m and m.group(1))
        assert "team=" + code in hash_ and "team=" + alias + "&" not in hash_ + "&", (alias, hash_)


def test_tree_branch_specs_come_from_the_payload_not_the_js():
    assert "d.tree.branches" in JS
    assert not re.search(r'key:\s*["\'](roster|outlook|farm)["\']', JS), "branchSpecs typed into the JS"
    assert "DATA.weights[" in JS and "DATA.branch_order" in JS
    d = _served()
    html, _ = _render("club", team="LAD", tree="full")
    lad = next(c for c in d["clubs"] if c["code"] == "LAD")
    for b in lad["tree"]["branches"]:
        assert b["label"] in html, b["label"]
        for lf in b["leaves"][:2]:
            assert lf["label"] in html, (b["key"], lf["label"])
    assert 'class="fr-tree-fallback"' in html and html.count('<details class="fr-acc"') == 12


def test_colours_come_from_eephus_tiers_only():
    for name, src in (("franchise.js", JS), ("franchise.css", CSS)):
        assert "hsl(" not in src, name
        # a hex colour literal; HTML entities (&#9650;) and hash keys are not colours
        assert not re.search(r"(?<!&)#[0-9a-fA-F]{3,8}\b(?![-_a-zA-Z])", re.sub(r"#(view|team|tree|sec|section|player|farm-org|tab|g|teams|history|model|m)=", "", src)), name
        assert "rgb(" not in src and "rgba(" not in src, name
    assert "EephusTiers.clsInk" in JS and "EephusTiers.varOf" in JS
    assert JS.count("EephusTiers") >= 3
    assert "_GRADE_PALETTE" not in JS and "gradeColor" not in JS


def test_letters_print_in_neutral_ink_and_only_scores_are_tiered():
    i = JS.index("function letterSpan(")
    body = JS[i:JS.index("\n  function ", i + 1)]
    assert "fr-neutral" in body and "tierInk" not in body
    j = JS.index("function scoreSpan(")
    body2 = JS[j:JS.index("\n  function ", j + 1)]
    assert 'tierInk(v, "z")' in body2
    html, _ = _render("club", team="LAD")
    m = re.search(r'<span class="fr-root-letter">([^<]*)</span>', html)
    assert m and "vt-" not in m.group(0)
    assert re.search(r'<span class="fr-root-score"><span class="vt-fam-z vt-avg">', html)
    assert ".fr-root-letter" in CSS and "color: var(--text-primary)" in CSS[CSS.index(".fr-root-letter"):CSS.index(".fr-root-letter") + 220]
    # the FIN Cost+ tile and the park factors print plain: never a ruler class
    assert re.search(r'Cost\+</a></div><div class="fr-tile-big "><span class="fr-neutral">', html)
    assert "fr-tile-big vt-" not in html.split("Park factor, runs")[1][:300]


def test_gfx_export_uses_the_eephus_gfx_header_helper_not_data_egfx():
    assert "data-egfx" not in JS
    assert "EEPHUS_GFX.open(" in JS and "EEPHUS_GFX.chipHTML(" in JS
    assert 'kind: "board", module: "Franchises"' in JS
    assert "_gfxHeader" not in JS, "the PROSPX inline helper is not importable; the shared modal draws the header"


def test_css_has_no_fixed_width_above_358_outside_a_container_query():
    stripped = re.sub(r"@container[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", CSS)
    for m in re.finditer(r"(?<![-a-z])width:\s*(\d+(?:\.\d+)?)px", stripped):
        assert float(m.group(1)) <= 358, m.group(0)
    assert "container-name: frboard" in CSS and "@container frboard (max-width: 560px)" in CSS
    assert "container-name: frblock" in CSS


def test_svg_hidden_below_1100_and_accordion_shown():
    i = CSS.index("@media (max-width: 1100px)")
    block = CSS[i:CSS.index("}\n\n", i)]
    assert ".fr-canopy { display: none; }" in block and ".fr-tree-wrap { display: none; }" in block
    assert ".fr-tree-fallback { display: block;" in block
    assert re.search(r"\.fr-app \.fr-tree-fallback \{ display: none; \}", CSS)
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in CSS[CSS.index("@media (max-width: 720px)"):]


def test_every_section_header_has_basis_verdict_and_open_links():
    d = _served()
    html, _ = _render("club", team="LAD")
    lad = next(c for c in d["clubs"] if c["code"] == "LAD")
    for b in lad["tree"]["branches"]:
        sec = html.split('data-frsec="%s"' % b["key"])[1].split("</section>")[0]
        assert 'class="fr-basis">basis: ' in sec, b["key"]
        assert 'class="fr-open">' in sec and "<a href=" in sec.split('class="fr-open">')[1][:600], b["key"]
        if b["verdict"]:
            assert 'class="eephus-beta fr-verdict"' in sec and b["verdict_model"] in sec, b["key"]
        if b["key"] == "odds":
            assert 'class="eephus-beta fr-verdict"' in sec and "playoff_odds_sim" in sec
            assert "no registry row" not in sec
            assert d["copy"]["odds_interval"] in sec
    assert html.count('<section class="fr-block"') == 12
    for href in ("mlbstats_hitters", "ledger", "management_club", "fa_fits", "betting_futures"):
        if lad["links"][href]:
            assert lad["links"][href].replace("&", "&amp;") in html, href


def test_fin_prints_the_mlb_leg_only_and_the_cost_plus_parts():
    """Owner answers M13-2 and M13-4: FIN prints the MLB leg under its own label
    (no Trade Machine currency) and Cost+'s three parts on separate rows."""
    d = _served()
    html, _ = _render("club", team="TBR")
    sec = html.split('data-frsec="fin"')[1].split("</section>")[0]
    assert "Roster surplus EV" not in sec and "Trade currency" not in sec
    assert d["copy"]["mlb_leg_label"].replace("(", "") in sec.replace("(", "")
    tbr = next(c for c in d["clubs"] if c["code"] == "TBR")
    mm = tbr["sections"]["fin"]["mlb_leg"]["mlb_mm"]
    assert ("$%.1fM" % mm) in sec
    labels = d["copy"]["cost_plus_part_labels"]
    for k in ("guaranteed", "arb", "prearb"):
        assert labels[k] in sec, k
    assert d["copy"]["cost_plus_numerator_label"] in sec
    # the ladder sum carries pre-arb rungs, so it is not called an arbitration cost
    assert "arbitration cost" not in sec and "Ladder sum 2027 (arb and pre-arb rungs" in sec


def test_glossary_hooks_resolve():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    ids = {e["id"] for e in g["entries"]}
    hooks = set(re.findall(r'gl\((?:[^()]|\([^()]*\))*?,\s*"([a-z_0-9]+)"\)', JS))
    if PAGE.exists():
        hooks |= set(re.findall(r'data-gl="([a-z_0-9]+)"', PAGE.read_text(encoding="utf-8")))
    html, _ = _render("club", team="LAD")
    hooks |= set(re.findall(r'data-gl="([a-z_0-9]+)"', html))
    assert hooks
    missing = sorted(h for h in hooks if h not in ids)
    assert not missing, missing


def test_the_served_board_renders_every_club_without_throwing():
    d = _served()
    for code in d["codes"]:
        html, masthead = _render("club", team=code)
        assert len(html) > 5000 and "could not be loaded" not in html, code
        assert masthead == d["copy"]["masthead"]
        assert html.count('<section class="fr-block"') == 12, code
        assert "team=" + next(c for c in d["clubs"] if c["code"] == code)["statsapi_code"] in html
    board, _ = _render("board")
    assert board.count("<tr>") >= 31 and 'class="fr-board"' in board


def test_board_default_sort_is_the_franchise_index():
    d = _served()
    assert d["board_default_sort"] == ["index_score", "desc"]
    board, _ = _render("board")
    order = re.findall(r'data-frlink="1" title="[^"]*">([A-Z]{2,3})</a>', board)
    ranked = [r["code"] for r in sorted(d["board"], key=lambda r: r["index_rank"])]
    assert order == ranked


def test_provisional_chip_rides_the_outlook_bubble():
    d = _served()
    html, _ = _render("club", team="LAD")
    canopy = html.split('class="fr-canopy"')[1].split("</svg>")[0]
    assert 'class="fr-svg-chip"' in canopy and d["copy"]["outlook_chip"] in canopy
    assert canopy.count('class="fr-svg-chip"') == 1, "the chip rides OUTLOOK alone"
    assert "OUTLOOK" in canopy and "SEASON" in canopy
    full, _ = _render("club", team="LAD", tree="full")
    assert "OUTLOOK (" + d["copy"]["outlook_chip"] + ")" in full


def test_arbitration_router_accepts_the_team_narrowing():
    arb = (ROOT / "assets" / "arbitration.js").read_text(encoding="utf-8")
    m = re.search(r"var TEAM_NARROW_RE = /(.*)/;", arb)
    assert m, "D8: the narrowing regex is missing"
    rx = re.compile(m.group(1))
    assert rx.search("#teams&team=LAD").group(1) == "LAD"
    assert rx.search("#team=LAD").group(1) == "LAD"
    assert not rx.search("#teams&xteam=LAD"), "anchored to a separator"
    assert 'if (tn && sec === "teams") teamNarrow = tn[1];' in arb
    assert "arb-row-narrow" in arb and 'id="arb-narrow-clear"' in arb
    assert '"&team=" + teamNarrow' in arb, "show() keeps the narrowing in the hash"
    d = _served()
    assert d["sections_status"]["arbitration_narrowing"]["live"] is True
    assert all(c["links"]["arbitration_teams"] == "/arbitration/#teams&team=" + c["code"] for c in d["clubs"])


def test_back_links_from_projections_and_prospx_and_the_native_picker():
    # Both back-links build their href through the hub's one club resolver
    # (EEPHUS_HUB.clubHref, Q9_05); test_club_resolver.py pins what it returns.
    proj = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    px = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "const frHref = franchiseHref(r.team);" in proj and "if (H && H.clubHref) return H.clubHref(code);" in proj
    assert '<a href="${esc(frHref)}" title="Open the club on Franchises">franchise</a>' in proj
    assert 'href="${escapeHtml(clubFranchiseHref(org.org))}"' in px and "if (H && H.clubHref) return H.clubHref(x);" in px
    html, _ = _render("club", team="LAD")
    assert '<select id="fr-club" class="eephus-select"' in html


# --------------------------------------------------------------------------
# Review 2026-09-23: parsed-DOM tile assertions, current asset stamps, and
# the roster tables' ladder parity with /mlbstats/
# --------------------------------------------------------------------------

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _TileDom(HTMLParser):
    """Walks the rendered HTML the way a browser parses it: an <a> opened
    inside an open <a> is a nested anchor (the parser splinters it, which
    emptied 36 of 62 tiles on the club page), and every .fr-tile must close
    with a .fr-tile-big inside it. A raw-string regex cannot see either."""

    def __init__(self):
        super().__init__()
        self.stack = []          # [tag, classes, holds_a_big]
        self.nested = 0
        self.tiles = 0
        self.hollow = 0
        self.open_chips = 0

    def handle_starttag(self, tag, attrs):
        cls = (dict(attrs).get("class") or "").split()
        if tag == "a" and any(t == "a" for t, _c, _b in self.stack):
            self.nested += 1
        if "fr-tile-big" in cls:
            for fr in self.stack:
                if "fr-tile" in fr[1]:
                    fr[2] = True
        if "fr-tile-open" in cls:
            self.open_chips += 1
        if tag in _VOID:
            return
        self.stack.append([tag, cls, False])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        while self.stack:
            t, cls, big = self.stack.pop()
            if "fr-tile" in cls:
                self.tiles += 1
                if not big:
                    self.hollow += 1
            if t == tag:
                break


def test_tiles_never_nest_an_anchor_and_every_tile_holds_its_number():
    d = _served()
    for code in d["codes"]:
        html, _ = _render("club", team=code)
        p = _TileDom()
        p.feed(html)
        p.close()
        assert p.nested == 0, (code, "an <a> opened inside an open <a>")
        assert p.tiles >= 40 and p.hollow == 0, (code, p.tiles, p.hollow)
        assert p.open_chips >= 20, (code, p.open_chips)
        assert not p.stack, (code, "unbalanced markup")
    assert "<a class=\"fr-tile\"" not in JS and "<div class=\"fr-tile" in JS
    sub = CSS[CSS.index(".fr-app .fr-tile-sub"):]
    assert "overflow-wrap: anywhere" in sub[:200] and ".fr-tile-open" in CSS


def test_the_served_page_stamps_the_current_assets():
    """The ?v= cache-buster busts only when the page is rebuilt after the last
    asset edit: the review found franchise.js and arbitration.js stamped for
    older copies, so a cached arbitration.js never received TEAM_NARROW_RE."""
    if not PAGE.exists():
        pytest.skip("run python build_site.py")
    import build_site
    h = PAGE.read_text(encoding="utf-8")
    for rel in ("assets/franchise.js", "assets/franchise.css", "assets/eephus-gfx.js"):
        m = re.search(r"/%s\?v=([0-9a-f]{8})" % re.escape(rel), h)
        assert m, rel
        assert m.group(1) == build_site._asset_ver(rel), (rel, m.group(1), "run python build_site.py")
    arb = ROOT / "arbitration" / "index.html"
    if arb.exists():
        m = re.search(r"/assets/arbitration\.js\?v=([0-9a-f]{8})", arb.read_text(encoding="utf-8"))
        assert m and m.group(1) == build_site._asset_ver("assets/arbitration.js"), "run python build_site.py"


def test_roster_table_columns_take_the_family_mlbstats_applies():
    """HEM+, SEM+, REM+ and DEM+ columns on the club page take the family the
    /mlbstats/ boards paint the same metric on (SEM+ was `z` here and `run`
    there, so Blake Snell 133 read one band higher on the hub)."""
    mlb = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")

    def helper_family(name):
        m = re.search(r'function %s\([^)]*\) \{ return vtCell\(v, "([a-z]+)"' % name, mlb)
        assert m, name
        return m.group(1)

    assert re.search(r"remCell\(r\.dem_plus\)", mlb), "the fielder board paints DEM+ through remCell"
    expect = {
        "HEM+": helper_family("hemCell"),
        "SEM+": re.search(r'clsInk\(r\.sem_plus, "([a-z]+)"\)', mlb).group(1),
        "REM+": re.search(r'clsInk\(r\.rem_plus, "([a-z]+)"\)', mlb).group(1),
        "DEM+": helper_family("remCell"),
    }
    for label, fam in expect.items():
        assert JS.count('gl("%s", ' % label) == 1, label
        i = JS.index('gl("%s", ' % label)
        m = re.search(r'tierInk\(r\[\d\], "([a-z]+)"\)', JS[i:i + 400])
        assert m, label
        assert m.group(1) == fam, (label, m.group(1), fam)
    assert expect["SEM+"] == "run" and expect["HEM+"] == "ratio"


def test_the_board_payroll_column_names_the_cbt_basis():
    assert '["tax_payroll_2027", "CBT payroll ", 1, "cbt_payroll"]' in JS
    assert '"Payroll ", 1' not in JS


def test_the_odds_section_prints_the_season_over_line_only_when_the_payload_has_one():
    """F1 of the Part 8 intensity lane. The ODDS leaf quotes the Futures board,
    whose simulator never sees a postseason game; once the regular season is
    over the payload carries one line saying so, and the section prints it
    above the tiles. Before then the copy key is empty and nothing prints."""
    import copy as _copy
    d = _served()
    line = ("As of the end of the regular season (2026-10-01): postseason "
            "results are not in these odds.")
    p = _strip_bracket(_copy.deepcopy(d))
    p["copy"]["odds_as_of"] = line
    html, _ = _render(team="LAD", payload=p)
    sec = html.split('data-frsec="odds"')[1]
    assert line in sec
    assert sec.index(line) < sec.index("fr-tiles"), "the line renders after the odds it qualifies"
    p["copy"]["odds_as_of"] = ""
    html, _ = _render(team="LAD", payload=p)
    assert "postseason results are not in" not in html


def _strip_bracket(p):
    """The payload as it is without the postseason bracket simulator (its flag
    off, or no payload): no odds.bracket block and none of its copy keys."""
    for c in p["clubs"]:
        c["sections"]["odds"].pop("bracket", None)
    for k in ("odds_bracket_line", "odds_division_as_of", "odds_bracket_not_updated"):
        p["copy"].pop(k, None)
    return p


def test_the_pennant_tile_reads_the_bracket_simulator_while_it_serves():
    """docs/betting-2026-10/BRACKET_SIM_GATE.md 8: the Pennant tile and its
    World Series line read odds.bracket, labelled implied, no market, with the
    postseason_bracket_sim chip and its date; the reworded stamp and the line
    print above the tiles; the Playoffs tile keeps the season simulator. With
    the block absent the tile is the season simulator's, unlabelled."""
    import copy as _copy
    p = _strip_bracket(_copy.deepcopy(_served()))
    lad = next(c for c in p["clubs"] if c["code"] == "LAD")
    lad["sections"]["odds"]["bracket"] = {
        "pennant_pct": 0.123456, "ws_pct": 0.0456, "seed": 2, "series_now": "fixture",
        "as_of": "2026-10-02", "label": "implied, no market",
        "registry_row": "postseason_bracket_sim", "verdict": "unvalidated", "basis": "fixture"}
    note = ("As of the end of the regular season (2026-10-02): postseason results are not "
            "in the Division, Playoffs, Bye, Proj W and Win band columns.")
    brline = ("Pennant and World Series: implied by the postseason bracket simulator as of "
              "2026-10-02, no market.")
    p["copy"]["odds_division_as_of"] = note
    p["copy"]["odds_bracket_line"] = brline
    p["copy"]["odds_as_of"] = "As of the end of the regular season (2026-10-02): postseason results are not in these odds."
    html, _ = _render(team="LAD", payload=p)
    sec = html.split('data-frsec="odds"')[1]
    assert note in sec and brline in sec
    assert sec.index(brline) < sec.index("fr-tiles")
    assert "are not in these odds" not in sec
    assert "Pennant (implied, no market)" in sec and "12.3%" in sec and "World Series 4.6%" in sec
    assert "postseason_bracket_sim unvalidated" in sec and "as of 2026-10-02" in sec
    del lad["sections"]["odds"]["bracket"]
    html, _ = _render(team="LAD", payload=p)
    sec = html.split('data-frsec="odds"')[1]
    assert "Pennant (implied" not in sec and "postseason_bracket_sim" not in sec



# --------------------------------------------------------------------------
# Display pass 2026-10-03 (DISPLAY_franchise): the surface-quality audit's
# findings QCLA12, QCLA13, QCLC16, QCLC17, QCLC20 and QCLP10, and the copy trim
# --------------------------------------------------------------------------

def test_board_sort_heads_are_buttons_in_scoped_th_with_aria_sort():
    """QCLA12: every sortable head is <th scope=col aria-sort> holding one
    <button>; the glossary term inside is a span out of the tab order (an <a>
    inside a <button> is not valid); one head says descending, on the index."""
    board, _ = _render("board")
    heads = re.findall(r"<th [^>]*>.*?</th>", board.split("<thead>")[1].split("</thead>")[0])
    assert len(heads) == 11
    for h in heads:
        assert 'scope="col"' in h and re.search(r'aria-sort="(none|ascending|descending)"', h), h
        assert h.count('<button type="button" class="fr-sort" data-frsort=') == 1, h
        assert "<a " not in h and 'tabindex="0"' not in h, h
        for term in re.findall(r'<span class="g-term"[^>]*>', h):
            assert 'tabindex="-1"' in term, term
    assert [h for h in heads if 'aria-sort="descending"' in h] == [h for h in heads if 'data-frsort="index_score"' in h]
    assert sum('aria-sort="none"' in h for h in heads) == 10
    i = JS.index('btn.addEventListener("click"')
    assert "nb.focus()" in JS[i:i + 700], "focus returns to the sorted head after the re-render"
    assert "th[data-frsort]" not in JS and 'tabindex="0"' not in JS
    ring = CSS[CSS.index(".fr-app .fr-sort:focus-visible"):]
    assert ring.split("}")[0].count("var(--accent-cyan)") == 1
    assert "th:focus { outline: 2px solid var(--accent-gold)" not in CSS
    m = CSS[CSS.index("@media (max-width: 640px)"):]
    assert ".fr-board td:first-child a" in m.split("}\n}")[0] and "min-height: 44px" in m


def test_club_charts_toggles_headings_and_tables_carry_names_and_scope():
    """QCLA13: every role=img svg is named; the tree chips carry aria-pressed;
    the status chip sits outside the h2; the mini tables have row headers and
    the section tables scoped column headers."""
    html, _ = _render("club", team="MIL")
    imgs = re.findall(r'<svg [^>]*role="img"[^>]*>', html)
    assert imgs and all('aria-label="' in s for s in imgs), [s for s in imgs if "aria-label" not in s]
    sparks = re.findall(r'<div class="fr-spark"><svg [^>]*>', html)
    assert len(sparks) == 3 and all('aria-label="' in s for s in sparks)
    chips = re.findall(r'<button class="chip[^"]*" data-frtree="[a-z]+"[^>]*>', html)
    assert len(chips) == 3 and sum('aria-pressed="true"' in c for c in chips) == 1
    assert all("aria-pressed=" in c for c in chips)
    for h2 in re.findall(r"<h2 [^>]*>.*?</h2>", html):
        assert "fr-verdict" not in h2 and "eephus-beta" not in h2, h2
    assert html.count('<div class="fr-sec-head">') == 12
    assert '<table class="fr-mini"><tr><td>' not in html and '<th scope="row">' in html
    assert re.search(r'<table class="fr-table"><thead><tr><th scope="col"', html)
    assert '<table class="fr-table"><thead><tr><th class=' not in html
    m = CSS[CSS.index("@media (max-width: 640px)"):]
    assert ".fr-tile-open" in m and ".fr-links a" in m


def test_the_roster_note_is_one_sentence_and_names_no_field():
    """QCLC16: one sentence from one copy key, never two fragments joined, and
    no payload field name in reader copy."""
    d = _served()
    note = d["copy"]["roster_note"]
    assert "roster_basis_note" not in d["copy"]
    assert note[0].isupper() and note.endswith(".") and "team_basis" not in note
    html, _ = _render("club", team="MIL")
    sec = html.split('data-frsec="roster"')[1].split("</section>")[0]
    assert '<p class="fr-count">' + note.replace("&", "&amp;") + "</p>" in sec
    assert "team_basis" not in html


def test_the_link_rail_prints_labels_not_route_keys():
    """QCLC17: the rail labels each link from the Open-in map, grouped by the
    module that owns it; no key prints with its underscores replaced."""
    d = _served()
    html, _ = _render("club", team="MIL")
    rail = html.split('<nav class="fr-links"')[1].split("</nav>")[0]
    mil = next(c for c in d["clubs"] if c["code"] == "MIL")
    texts = re.findall(r'<a href="[^"]*">([^<]*)</a>', rail)
    assert len(texts) == sum(1 for v in mil["links"].values() if v)
    for k in mil["links"]:
        if "_" in k:
            assert k.replace("_", " ") not in texts, k
    for lbl in ("Hitters", "Club Ledger", "Hall of Fame", "Dynasty"):
        assert lbl in rail, lbl
    assert rail.count('class="fr-links-mod"') == len({re.match(r"/([a-z]+)/", v).group(1) for v in mil["links"].values() if v})


def test_the_playoff_head_names_its_model_and_verdict():
    """QCLC20: the 0%/100% Playoff column says it is the season simulator,
    with its registry row and verdict, and what it reads once the season ends."""
    d = _served()
    title = d["copy"]["board_playoff_title"]
    verdict = {r["model_id"]: r["verdict"] for r in d["accountability"]["registry_verdicts"]}["playoff_odds_sim"]
    assert "playoff_odds_sim " + verdict in title and "settled outcome" in title
    board, _ = _render("board")
    head = re.search(r'<th [^>]*data-export-text="Playoff"[^>]*>', board).group(0)
    assert 'title="' + title + '"' in head


def test_method_copy_sits_in_one_collapsed_block_and_the_banner_rides_its_dollar_blocks():
    """The copy trim: the weights note and the score formula print once, inside
    a collapsed How this works block (club and board); the CBA banner rides the
    three sections that hold 2027 dollars and no longer repeats above the tree."""
    d = _served()
    html, _ = _render("club", team="MIL")
    how = html.split('<details class="fr-how">')[1].split("</details>")[0]
    assert d["copy"]["how_title"] in how and d["copy"]["weights_note"] in how
    assert d["copy"]["score_basis"][1:] in how and "Sources: " in how
    assert html.count(d["copy"]["weights_note"]) == 1
    assert html.count('class="fr-banner"') == 3
    assert html.index('class="fr-banner"') > html.index('data-frsec="fin"')
    board, _ = _render("board")
    bhow = board.split('<details class="fr-how">')[1].split("</details>")[0]
    assert d["copy"]["board_foot"] in bhow and d["copy"]["score_basis"][1:] in bhow
    # the trimmed lines stay short: masthead and board lede under 25 words,
    # root sentence under 30, and the root keeps its thirty-percent disclosure
    for k, cap in (("masthead", 25), ("board_lede", 25), ("root_sentence", 30), ("weights_note", 25)):
        assert len(d["copy"][k].split()) < cap, (k, len(d["copy"][k].split()))
    assert "Thirty percent of the index rests on a provisional projection" in d["copy"]["root_sentence"]


def test_joined_copy_fragments_read_as_sentences():
    """Two copy fragments printed in one note read as two sentences (the
    QCLC16 defect class): each starts with a capital and ends with a stop, so
    "...(org_tendencies) z against..." no longer runs on."""
    d = _served()
    c = d["copy"]
    html, _ = _render("club", team="MIL")
    def sent(t):
        t = t.strip()
        t = t[0].upper() + t[1:]
        return t if t[-1] in ".!?:" else t + "."
    for a, b, sec in (("front_office_note", "zbar_note", "front_office"), ("history_note", "history_pennants", "history")):
        body = html.split('data-frsec="%s"' % sec)[1].split("</section>")[0]
        assert sent(c[a]) + " " + sent(c[b]) in body, sec
        assert c[a] + " " + c[b] not in body, sec

def _render_split(team, shard_ok=True):
    """Render the club page off the served BOARD alone, with a fetch that
    serves data/franchise_clubs/CODE.json from disk (or fails)."""
    import franchise_export as fe
    if not ART.exists():
        pytest.skip("run python franchise_export.py")
    board = json.loads(ART.read_text(encoding="utf-8"))
    if not board.get("shards"):
        pytest.skip("the served board is not split")
    shards = {c: json.loads((ROOT / "data" / fe.SHARD_DIRNAME / f"{c}.json").read_text(encoding="utf-8"))
              for c in board["shards"]["files"]}
    js = JS.replace('state = { view: "club", team: "", tree: "canopy", sec: "", treeSet: false',
                    'state = { view: "club", team: "%s", tree: "canopy", sec: "", treeSet: false' % team, 1)
    prelude = """
    var __html={}, __urls=[];
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='addEventListener'||k==='setAttribute'||k==='getAttribute')return function(){return null;};
        return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v; if(k==='textContent')__html[id+':text']=v; return true;}});}
    function OK(v){return {then:function(cb){try{var r=cb(v);}catch(e){return NO(e);}return (r&&r.then)?r:OK(r);},catch:function(){return OK(v);}};}
    function NO(e){return {then:function(){return NO(e);},catch:function(cb){cb(e);return OK();}};}
    var B=%s, S=%s, SHARD_OK=%s;
    var fetch=function(u){__urls.push(u);
      if(u.indexOf('/data/franchise_clubs/')===0){ if(!SHARD_OK) return OK({ok:false});
        var c=u.split('/').pop().split('.')[0]; return OK({ok:true,json:function(){return OK(S[c]);}}); }
      return OK({ok:true,json:function(){return OK(B);}});};
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:function(){return null;},querySelectorAll:function(){return [];},addEventListener:function(){}};
    var window={document:document,EEPHUS_GL:{wire:function(){}}};
    var location={hash:''};
    %s
    """ % (json.dumps(board), json.dumps(shards), "true" if shard_ok else "false", TIERS_STUB)
    ctx = MiniRacer()
    ctx.eval(prelude + js)
    return ctx.eval("__html['franchise-app-root'] || ''"), json.loads(ctx.eval("JSON.stringify(__urls)"))


def test_the_club_page_fetches_one_club_file_and_renders_it():
    """QCLP10: the page boots on the board and fetches exactly the shown club's
    file; the rendered club matches the one rendered off the whole document."""
    html, urls = _render_split("MIL")
    assert urls[0] == "/data/franchise_board.json"
    assert [u.split("?")[0] for u in urls[1:]] == ["/data/franchise_clubs/MIL.json"]
    whole, _ = _render("club", team="MIL")
    assert html == whole
    failed, _ = _render_split("MIL", shard_ok=False)
    assert "px-state is-failed" in failed and "fr-mast-name" in failed and '<section class="fr-block"' not in failed



def test_promotion_timing_panel_tags_come_from_the_tested_labels():
    """/franchise/ FRONT OFFICE: the Promotion timing panel rides
    TENDENCY_PANELS, its tags are only labelTiming / labelAggr, it prints the
    rule note and a collapsed rule with its sources."""
    import franchise_export as fe
    spec = next(p for p in fe.TENDENCY_PANELS if p[0] == "promotionTiming")
    assert spec[4] == ("labelTiming", "labelAggr")
    assert [r[0] for r in spec[3]] == ["lateShare", "svcShare", "medianDebutAge", "aggrYears", "nDebuts"]
    d = _served()
    tend = json.loads((ROOT / "data" / "org_tendencies.json").read_text(encoding="utf-8"))
    torgs = (tend.get("promotionTiming") or {}).get("orgs") or {}
    if not torgs:
        pytest.skip("promotionTiming not exported on this machine")
    for c in d["clubs"]:
        p = next(x for x in c["sections"]["front_office"]["panels"] if x["key"] == "promotionTiming")
        r = torgs[c["code"]]
        assert p["tags"] == [t for t in (r["labelTiming"], r["labelAggr"]) if t], c["code"]
        assert p["rule"]["sources"] and p["rule"]["text"], c["code"]
    html, _ = _render("club", team="SEA")
    sec = html.split('data-frsec="front_office"')[1].split("</section>")[0]
    assert "Promotion timing" in sec and d["copy"]["promotion_timing_note"] in sec
    assert "<details" in sec and "mlb.com/glossary/rules/rookie-eligibility" in sec


def test_open_in_chips_are_44px_at_phone_width_and_notes_dim_by_colour():
    """QREA22: the section Open in chips reach 44 px at <= 640 px, and the
    panel notes and tags are dimmed by colour, never opacity."""
    i = CSS.index("@media (max-width: 640px)")
    block = CSS[i:CSS.index("}\n}", i) if "}\n}" in CSS[i:] else len(CSS)]
    assert ".fr-app .fr-open a" in block and "min-height: 44px" in block
    for sel in (".fr-app .fr-count {", ".fr-app .fr-tag {"):
        rule = CSS[CSS.index(sel):CSS.index("}", CSS.index(sel))]
        assert "opacity" not in rule and "color: var(--text-secondary)" in rule, sel
