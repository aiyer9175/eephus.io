# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Content stamps for the Diamond section's build-time data payloads.

THE TRADE UNDER TEST. nginx serves /data/ with max-age=604800, so every
client used to fetch its payload with cache:"no-cache": a forced revalidation
round trip per page view, on files that only ever change when the site
rebuilds (data/fantasy.json alone is ~585KB). build_site._data_vers_script now
emits window.EEPHUS_DATA_VERS = {"<file>": "<8-hex content hash>"} on the
pages that consume these payloads (/fantasy/, /cards/, /diamond/), and the
clients append ?v=<stamp> and fetch under DEFAULT caching, exactly the trade
_GL_DATA_VER made for the glossary corpus. Same freshness, one transfer per
version.

THE RULE THE STAMP MUST NEVER CROSS. data/betting.json,
data/betting_record.json and the settlement/CLV sidecars are mutated
INTRA-DAY by the close job with no page rebuild in between. A build-time
stamp on any of them would pin a week-stale copy of a live betting record
under that same max-age, on the pages that ask for money on the strength of
that record being honest. So the betting payloads keep no-cache
revalidation, the helper REFUSES betting names outright, and betting.js
never reads the stamp global at all.

MUTATIONS PROVEN BEFORE LANDING (each has a test below that fails on it):
  * stamp computed from the FILENAME rather than the content -> the
    stamp-changes-with-content test fails (a name hash never moves);
  * a client appends the stamp but KEEPS cache:"no-cache" -> the cache-mode
    assertions fail (the whole win is the default cache mode), and the
    live-mutant test builds that exact client and watches the guard catch it;
  * a betting file sneaks into a stamp list -> the helper raises, and the
    source scans on the shipped lists and on betting.js fail.

ALSO HERE: the /diamond/ 360px checks. The page's injected stylesheet has
zero media queries by design (auto-fit/minmax grids), so a static floor
analysis plus a narrow-viewport browser smoke pin that the page cannot pan
sideways on a phone. They ride in this file because this lane owns no other
test module; the smoke follows the serve_site + playwright pattern from
test_board_card_typography and skips cleanly where playwright or chromium is
absent.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

import build_site
from conftest import serve_site

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"

# The shipped lists, one per consuming page. A name added to a client's reads
# without landing here simply stays on no-cache (safe); a name added here
# without a consumer is a few wasted bytes of inline JSON (also safe). What
# must never happen is a betting name in any of them, and that is enforced.
SHIPPED_LISTS = {
    "build_fantasy": ("fantasy.json", "dfs.json",
                      "hitter_history.json", "starter_history.json"),
    "build_cards": ("card_market.json",),
    "build_diamond": ("xfv_scoreboard_eval.json",),
}

_STAMP_RE = re.compile(r'<script>window\.EEPHUS_DATA_VERS=({[^<]+});</script>')


def _emitted(page_html: str) -> dict:
    m = _STAMP_RE.search(page_html)
    assert m, "the page emits no EEPHUS_DATA_VERS block"
    return json.loads(m.group(1))


# ===========================================================================
# 1. The build-side helper
# ===========================================================================

def test_helper_stamps_existing_files_and_omits_missing_ones(tmp_path, monkeypatch):
    """A missing file is an OMISSION, never a crash: the client sees no entry
    and keeps its no-cache read, and the build ships."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.json").write_bytes(b'{"x": 1}')
    monkeypatch.setattr(build_site, "ROOT", tmp_path)
    out = build_site._data_vers_script(("a.json", "never_written.json"))
    m = _STAMP_RE.search(out)
    assert m, out
    vers = json.loads(m.group(1))
    assert list(vers) == ["a.json"]
    assert re.fullmatch(r"[0-9a-f]{8}", vers["a.json"])
    assert vers["a.json"] == hashlib.md5(b'{"x": 1}').hexdigest()[:8]


def test_helper_emits_nothing_when_no_file_exists(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(build_site, "ROOT", tmp_path)
    assert build_site._data_vers_script(("never_written.json",)) == ""


def test_stamp_follows_the_content_not_the_filename(tmp_path, monkeypatch):
    """MUTATION: hash the NAME instead of the bytes. The stamp would never
    move, every deploy would serve the week-old cached payload, and the whole
    scheme would be a silent staleness bug. Same content must also restamp
    identically, or every rebuild would bust caches that did not change."""
    (tmp_path / "data").mkdir()
    f = tmp_path / "data" / "a.json"
    monkeypatch.setattr(build_site, "ROOT", tmp_path)
    f.write_bytes(b'{"rows": 1}')
    first = _emitted(build_site._data_vers_script(("a.json",)))["a.json"]
    f.write_bytes(b'{"rows": 1}')
    assert _emitted(build_site._data_vers_script(("a.json",)))["a.json"] == first, (
        "identical content restamped differently; a rebuild would bust every cache")
    f.write_bytes(b'{"rows": 2}')
    second = _emitted(build_site._data_vers_script(("a.json",)))["a.json"]
    assert second != first, (
        "the stamp did not move with the content; it is a filename stamp")


def test_helper_refuses_betting_names_loudly():
    """MUTATION: a betting file sneaks into a stamp list. The helper must
    raise rather than ship a build-time stamp on a payload the close job
    mutates intra-day."""
    for name in ("betting.json", "betting_record.json", "betting_status.json"):
        with pytest.raises(ValueError):
            build_site._data_vers_script((name,))


def test_no_shipped_list_carries_a_betting_name():
    for fn, names in SHIPPED_LISTS.items():
        assert not any(n.startswith("betting") for n in names), (fn, names)
    assert build_site.FANTASY_DATA_STAMPS == SHIPPED_LISTS["build_fantasy"]
    assert build_site.CARDS_DATA_STAMPS == SHIPPED_LISTS["build_cards"]
    assert build_site.DIAMOND_DATA_STAMPS == SHIPPED_LISTS["build_diamond"]


# ===========================================================================
# 2. The pages emit their maps
# ===========================================================================

@pytest.mark.parametrize("fn,names", sorted(SHIPPED_LISTS.items()))
def test_page_emits_its_own_stamp_map(fn, names):
    """Each consuming page carries exactly its own payload set, stamped with
    the file's current content hash, and the inline block sits BEFORE the
    deferred client tags (inline scripts run at parse time, deferred scripts
    after, so the global exists whenever a client reads it)."""
    out = getattr(build_site, fn)()
    vers = _emitted(out)
    expected = {n for n in names if (ROOT / "data" / n).exists()}
    assert set(vers) == expected, (fn, vers)
    for name, v in vers.items():
        assert v == hashlib.md5((ROOT / "data" / name).read_bytes()).hexdigest()[:8], name
    assert out.index("EEPHUS_DATA_VERS") < out.index("diamond-config.js")


def test_betting_page_emits_no_stamp_map():
    """/betting/ is the page whose payloads mutate intra-day; it must never
    grow the global, or a copy-pasted client helper there would start pinning
    stale odds."""
    assert "EEPHUS_DATA_VERS" not in build_site.build_betting()


# ===========================================================================
# 3. The clients, executed in V8
# ===========================================================================
# The same stub-DOM + synchronous-thenable shape as test_diamond_scaffold's
# harness, plus a fetch that RECORDS (url, options). options === undefined is
# recorded as null: that is the "default cache mode" the stamp exists to buy.

_DOM = r"""
var __fetches = [];
var _els = {};
function _mkEl(id){ return {id:id, innerHTML:"", textContent:"", style:{}, children:[],
  querySelector:function(){return null;}, querySelectorAll:function(){return [];},
  addEventListener:function(){}, appendChild:function(){}, removeAttribute:function(){},
  setAttribute:function(){}, getAttribute:function(){return null;},
  classList:{toggle:function(){},add:function(){},remove:function(){},contains:function(){return false;}} }; }
var document = {
  readyState: "complete",
  getElementById: function (id) { if (!_els[id]) _els[id] = _mkEl(id); return _els[id]; },
  createElement: function (t) { return _mkEl("<"+t+">"); },
  querySelector: function(){ return null; },
  querySelectorAll: function(){ return []; },
  head: { appendChild: function () {} },
  body: { appendChild: function () {} },
  addEventListener: function () {}
};
var location = { hash: "", href: "http://x/" };
var history = { replaceState: function(){} };
function SyncP(v,e){ this.v=v; this.e=e; this.failed=arguments.length>1; }
SyncP.prototype.then=function(ok,bad){ if(this.failed) return bad?_c(bad,this.e):this; return ok?_c(ok,this.v):this; };
SyncP.prototype.catch=function(bad){ return this.then(null,bad); };
SyncP.prototype.finally=function(f){ f(); return this; };
function _c(fn,a){ try{ var r=fn(a); return (r instanceof SyncP)?r:new SyncP(r);}catch(err){ return new SyncP(undefined,err);} }
function fetch(url, opts){
  __fetches.push({url:url, opts:(opts===undefined? null : opts)});
  return new SyncP({ ok:true, json:function(){ return new SyncP({}); } });
}
var window = { addEventListener: function(){} };
"""


def _run_client(name: str, pre: str = "", post: str = "", src: str | None = None) -> list:
    """Boot a client over the stub DOM; returns the recorded fetches."""
    mr = pytest.importorskip("py_mini_racer")
    ctx = mr.MiniRacer()
    ctx.eval(_DOM)
    if pre:
        ctx.eval(pre)
    ctx.eval(src if src is not None else (ASSETS / name).read_text(encoding="utf-8"))
    if post:
        ctx.eval(post)
    return json.loads(ctx.eval("JSON.stringify(__fetches)"))


def _by_path(fetches: list) -> dict:
    return {f["url"].split("?")[0]: f for f in fetches}


def test_hub_json_rides_the_stamp_under_default_caching_and_memoizes_once():
    fetches = _run_client(
        "fantasy-hub.js",
        pre='window.EEPHUS_DATA_VERS = {"fantasy.json": "cafe1234"};',
        post='window.EEPHUS_FANTASY_HOST.json("/data/fantasy.json");'
             'window.EEPHUS_FANTASY_HOST.json("/data/fantasy.json");'
             'window.EEPHUS_FANTASY_HOST.corpus();')
    assert fetches == [{"url": "/data/fantasy.json?v=cafe1234", "opts": None}], (
        "stamped: expected ONE fetch, versioned URL, default cache mode; the "
        "memo key must stay the bare url so three callers share one download")


def test_hub_json_keeps_the_no_cache_read_when_no_stamp_exists():
    """A hand-served page or a missing emission means no global; the current
    behavior must survive byte for byte."""
    fetches = _run_client(
        "fantasy-hub.js",
        post='window.EEPHUS_FANTASY_HOST.json("/data/fantasy.json");')
    assert fetches == [{"url": "/data/fantasy.json", "opts": {"cache": "no-cache"}}]


@pytest.mark.parametrize("name,stamps,path,ver", [
    ("dynasty.js", '{"fantasy.json": "cafe1234"}', "/data/fantasy.json", "cafe1234"),
    ("redraft.js", '{"fantasy.json": "cafe1234"}', "/data/fantasy.json", "cafe1234"),
    ("dfs.js", '{"dfs.json": "beef5678"}', "/data/dfs.json", "beef5678"),
])
def test_board_client_standalone_load_honors_the_stamp(name, stamps, path, ver):
    """The standalone fallback (no /fantasy/ host on the page) takes the same
    trade: versioned URL, default cache mode."""
    fetches = _run_client(name, pre=f"window.EEPHUS_DATA_VERS = {stamps};")
    assert fetches == [{"url": f"{path}?v={ver}", "opts": None}], fetches


@pytest.mark.parametrize("name,path", [
    ("dynasty.js", "/data/fantasy.json"),
    ("redraft.js", "/data/fantasy.json"),
    ("dfs.js", "/data/dfs.json"),
])
def test_board_client_standalone_load_unchanged_without_a_stamp(name, path):
    fetches = _run_client(name)
    assert fetches == [{"url": path, "opts": {"cache": "no-cache"}}], fetches


def test_cards_stamps_its_own_payload_and_leaves_player_links_alone():
    by = _by_path(_run_client(
        "cards.js", pre='window.EEPHUS_DATA_VERS = {"card_market.json": "0a1b2c3d"};'))
    assert by["/data/card_market.json"] == {
        "url": "/data/card_market.json?v=0a1b2c3d", "opts": None}
    # player_links.json is not on the /cards/ stamp list; its read must stay
    # the revalidating one it always was.
    assert by["/data/player_links.json"] == {
        "url": "/data/player_links.json", "opts": {"cache": "no-cache"}}


def test_diamond_stamps_the_scoreboard_and_never_the_record():
    by = _by_path(_run_client(
        "diamond.js",
        pre='window.EEPHUS_DATA_VERS = {"xfv_scoreboard_eval.json": "abcd0123"};'))
    assert by["/data/xfv_scoreboard_eval.json"] == {
        "url": "/data/xfv_scoreboard_eval.json?v=abcd0123", "opts": None}
    assert by["/data/betting_record.json"] == {
        "url": "/data/betting_record.json", "opts": {"cache": "no-cache"}}


def test_diamond_record_stays_no_cache_even_against_a_rogue_map_entry():
    """Defense in depth: the build helper refuses betting names, and the
    record call site passes fresh:true so even a hand-emitted rogue entry
    could not pin the record."""
    by = _by_path(_run_client(
        "diamond.js",
        pre='window.EEPHUS_DATA_VERS = {"xfv_scoreboard_eval.json": "abcd0123",'
            ' "betting_record.json": "deadbeef"};'))
    assert by["/data/betting_record.json"] == {
        "url": "/data/betting_record.json", "opts": {"cache": "no-cache"}}, (
        "a rogue stamp map entry pinned the live betting record")


def test_diamond_unstamped_behavior_is_the_old_behavior():
    fetches = _run_client("diamond.js")
    assert all(f["opts"] == {"cache": "no-cache"} and "?" not in f["url"]
               for f in fetches), fetches


def test_live_mutant_stamp_plus_no_cache_is_caught():
    """MUTATION, executed: a client that appends ?v= but keeps the no-cache
    option gets the revalidation round trip AND the cache-busting URL, the
    worst of both. Build that exact mutant and confirm the same predicate the
    real tests use rejects it, so the guard is known to bite."""
    real = (ASSETS / "diamond.js").read_text(encoding="utf-8")
    needle = 'var opts = stamped ? undefined : { cache: "no-cache" };'
    assert needle in real, "the option-selection line moved; update this mutant"
    mutant = real.replace(needle, 'var opts = { cache: "no-cache" };')
    by = _by_path(_run_client(
        "diamond.js", src=mutant,
        pre='window.EEPHUS_DATA_VERS = {"xfv_scoreboard_eval.json": "abcd0123"};'))
    assert by["/data/xfv_scoreboard_eval.json"]["opts"] == {"cache": "no-cache"}, (
        "the mutant did not behave as expected; the guard proves nothing")
    assert by["/data/xfv_scoreboard_eval.json"]["opts"] is not None  # the guard predicate


# ===========================================================================
# 4. Source-level pins on the do-not-stamp rule
# ===========================================================================

def _code(path: Path) -> str:
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("//"))


def test_betting_js_never_reads_the_stamp_global():
    """betting.js is the client whose payloads mutate intra-day. It must not
    grow a stampedURL helper or an EEPHUS_DATA_VERS read: its no-cache
    fetches ARE the correctness mechanism for the close job."""
    src = (ASSETS / "betting.js").read_text(encoding="utf-8")
    assert "EEPHUS_DATA_VERS" not in src
    assert "stampedURL" not in src


def test_diamond_record_call_site_passes_fresh():
    code = _code(ASSETS / "diamond.js")
    assert "getJSON(RECORD_URL, true)" in code, (
        "the betting-record read lost its fresh flag; a stamp could pin it")
    assert re.search(r"getJSON\(SCOREBOARD_URL\)", code), (
        "the scoreboard read stopped being stamp-eligible")


@pytest.mark.parametrize("name", ["fantasy-hub.js", "dynasty.js", "redraft.js",
                                  "dfs.js", "cards.js", "diamond.js",
                                  "fantasy-card.js"])
def test_every_stamped_client_keeps_the_no_cache_fallback(name):
    """The fallback is load-bearing: a hand-served page emits no global, and
    dropping the no-cache option there would serve week-stale payloads under
    the /data/ max-age with NO stamp to bust them."""
    code = _code(ASSETS / name)
    assert '{ cache: "no-cache" }' in code, f"{name} lost the no-cache fallback"
    assert "stampedURL" in code, f"{name} lost the stamp lookup"
    assert "EEPHUS_DATA_VERS" in code, f"{name} no longer reads the page global"


# ===========================================================================
# 5. /diamond/ at 360px
# ===========================================================================

def test_diamond_injected_sheet_grids_fit_a_360px_viewport():
    """Static floor analysis, since the injected sheet carries zero media
    queries by design. Available width at a 360px viewport:

        360 - 2*16 (.eephus-wrap phone padding, site.css <=640px block)
            - 2*16 (.diamond-app .card padding, the injected sheet)
            - 2*1  (card border)                                  = 294px

    Every grid in the sheet must be repeat(auto-fit/fill, minmax(<floor>px,
    1fr)) with its floor at or under that, so auto-fit collapses to one
    fitting column instead of forcing a horizontal pan. Wide TABLES are
    exempted by a different mechanism: they ride .mlbstats-scroll and scroll
    inside their own container."""
    src = (ASSETS / "diamond.js").read_text(encoding="utf-8")
    cols = re.findall(r"grid-template-columns:([^;}\"']+)", src)
    assert cols, "the injected sheet lost its grids; re-derive this analysis"
    floors = []
    for c in cols:
        m = re.fullmatch(r"repeat\(auto-(?:fit|fill),minmax\((\d+)px,1fr\)\)",
                         c.replace(" ", ""))
        assert m, f"grid column spec without an auto minmax floor: {c!r}"
        floors.append(int(m.group(1)))
    assert max(floors) <= 294, (
        f"grid floor(s) {floors} overflow a 360px viewport (294px available)")
    assert 'class="mlbstats-scroll"' in src, (
        "the archetype table lost its scroll container; at 360px it would pan the page")


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def test_diamond_at_360px_does_not_scroll_sideways(server):
    """Narrow-viewport smoke on the REAL page over the real artifacts: after
    the receipts paint, the document must not overflow 360px horizontally.
    Wide tables may scroll inside .mlbstats-scroll; the page itself may not."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        try:
            page = browser.new_page(viewport={"width": 360, "height": 780})
            page.goto(server + "diamond/", wait_until="load", timeout=60_000)
            page.wait_for_selector("#diamond-receipts .card", timeout=30_000)
            page.wait_for_timeout(500)
            m = page.evaluate(
                """() => {
                     const d = document.documentElement;
                     return {scrollW: d.scrollWidth, clientW: d.clientWidth,
                             bodyScrollW: document.body.scrollWidth};
                   }""")
            assert m["scrollW"] <= m["clientW"], (
                f"/diamond/ at 360px pans sideways: the document needs "
                f"{m['scrollW']}px but has {m['clientW']}px")
            assert m["bodyScrollW"] <= m["clientW"], (
                f"/diamond/ body overflows at 360px: {m['bodyScrollW']}px "
                f"in a {m['clientW']}px viewport")
        finally:
            browser.close()
