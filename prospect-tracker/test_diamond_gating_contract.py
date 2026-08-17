# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Diamond gating contract (assets/eephus-diamond.js), pinned end to end.

Written 2026-08-16, the day the five module clients stopped carrying private
copies of the gate. What the private copies actually did is the reason every
test in this file exists:

  * dynasty/redraft/dfs each read EEPHUS_DIAMOND.isMember and .previewRows,
    two keys assets/diamond-config.js has NEVER defined, so the day the flag
    flipped, a PAYING member would have been capped at 25 rows like everyone
    else (isMember undefined reads falsy, previewRows undefined reads 25);
  * betting.js probed EephusAccount.isDiamond() synchronously at boot, before
    the deferred account layer could resolve a session, so a member's first
    paint would have been the preview slice;
  * cards.js had no gate at all.

Three sections. (a) SOURCE conformance: exactly two assets may read the raw
window.EEPHUS_DIAMOND config (the config itself and the helper), plus a
documented exemption for diamond.js; the ghost keys are banned from client
code; every module client routes through window.EephusDiamond. (b) The
helper's truth table, executed in a real JS engine, dead-man's switch
included. (c) A row-cap behavior proof: the REAL helper plus the REAL
dynasty.js render a gated board at exactly the configured cap, with the gate
note, and re-render open when membership resolves; the same wiring is proven
on betting.js as the payload-refetch fix.

HARNESS TRAP, inherited from test_betting/test_fantasy_cards: the FT/SyncP
fetch stubs are fake thenables and cannot satisfy Promise.all. None of the
drivers here gates a render on Promise.all; if one ever does, these stubs
must grow real promises first, not another fake.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
HELPER_PATH = ASSETS / "eephus-diamond.js"
CONFIG_PATH = ASSETS / "diamond-config.js"
HELPER = HELPER_PATH.read_text(encoding="utf-8")

# The five module clients on the Diamond pass surfaces. diamond.js (the pass
# page itself) is deliberately NOT in this list: it belongs to another lane,
# renders copy about the gate rather than capping any rows, and reads only the
# flag; its exemption is pinned separately below.
CLIENTS = {
    "dynasty": ASSETS / "dynasty.js",
    "redraft": ASSETS / "redraft.js",
    "dfs": ASSETS / "dfs.js",
    "cards": ASSETS / "cards.js",
    "betting": ASSETS / "betting.js",
}


def _code(path: Path) -> str:
    """Source with whole-line comments removed. The bans below are about what
    the CODE does; a comment naming the ghost read it killed is the
    documentation working, not a violation."""
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("//"))


# ===========================================================================
# (a) Source conformance: one config, one reader, five callers
# ===========================================================================

def test_raw_config_global_has_exactly_two_readers_plus_the_pass_page():
    """MUTATION: paste `window.EEPHUS_DIAMOND` back into any module client
    (or any other asset). The raw config global may appear in the config, in
    the helper, and in diamond.js only.

    THE diamond.js EXEMPTION IS DOCUMENTED, NOT ACCIDENTAL: the pass page is
    another lane's file, it reads the flag to choose its own sales copy, and
    it caps nothing, so the ghost-key hazard this contract kills does not
    reach it. It is still held to the ghost-key ban below."""
    allowed = {"diamond-config.js", "eephus-diamond.js", "diamond.js"}
    offenders = []
    for path in sorted(ASSETS.glob("*.js")):
        if path.name in allowed:
            continue
        if "EEPHUS_DIAMOND" in _code(path):
            offenders.append(path.name)
    assert not offenders, f"raw EEPHUS_DIAMOND read outside the contract: {offenders}"
    assert "EEPHUS_DIAMOND" in _code(CONFIG_PATH)
    assert "EEPHUS_DIAMOND" in _code(HELPER_PATH)


def test_ghost_keys_are_dead_in_every_client_and_in_the_pass_page():
    """MUTATION: resurrect `isMember` or a bare `previewRows` config read in
    any module client. The only surviving spelling of previewRows outside the
    helper is the helper CALL with a literal module name, so a client can
    neither read the config key nor pass a variable that drifts."""
    call = re.compile(r'\.previewRows\("(dynasty|redraft|dfs|cards)"\)')
    for name, path in sorted(CLIENTS.items()):
        code = _code(path)
        assert "isMember" not in code, f"{name}.js grew a membership read of its own"
        occurrences = [m.start() for m in re.finditer(r"previewRows", code)]
        called = [m.start() + m.group(0).index("previewRows")
                  for m in call.finditer(code)]
        assert occurrences == called, (
            f"{name}.js spells previewRows outside the helper call shape")
        for m in call.finditer(code):
            assert m.group(1) == name, (
                f"{name}.js asks for another module's preview cap: {m.group(0)}")
    # diamond.js is exempt from the raw-global ban (it renders sales copy off
    # the flag) but not from the ghost keys: it caps nothing and must never
    # start. Its `isMember` is a local parameter fed from EephusAccount, which
    # is why the ban here is on the config-read spelling, not the bare word.
    dj = _code(ASSETS / "diamond.js")
    assert ".previewRows" not in dj, "diamond.js reads a preview cap it must not own"
    assert "CFG.isMember" not in dj and "EEPHUS_DIAMOND.isMember" not in dj, (
        "diamond.js reads the ghost membership key off the config")


def test_every_module_client_routes_through_the_helper():
    """MUTATION: delete the EephusDiamond call from any client. Each of the
    five must consult the one contract, and each must subscribe to
    entitlement changes, because membership resolves after first paint."""
    for name, path in sorted(CLIENTS.items()):
        code = _code(path)
        assert "EephusDiamond" in code, f"{name}.js does not call the helper"
        assert "onEntitlement" in code, (
            f"{name}.js never re-renders when membership resolves")


def test_helper_is_pure_contract_no_fetch_no_storage():
    """MUTATION: give the helper a fetch or a localStorage read. It answers
    questions; it owns no payload and no persistence."""
    code = _code(HELPER_PATH)
    assert "fetch(" not in code
    assert "localStorage" not in code
    assert "setInterval" not in code and "setTimeout" not in code, (
        "the entitlement seam is poll-free by design")


def test_config_carries_the_preview_caps_and_build_site_parses_them():
    """MUTATION: drop the preview_rows map from diamond-config.js, or move a
    cap. The caps are data and live in the config; _diamond_cfg() parses them
    so a build-side consumer never regex-scrapes the file a second way."""
    import build_site
    cfg = build_site._diamond_cfg()
    assert cfg.get("preview_rows") == {
        "dynasty": 25, "redraft": 25, "dfs": 25, "cards": 40}
    # A config without the map still parses (the three price keys stay the
    # only hard requirement, pinned in test_diamond_scaffold).
    bare = build_site._diamond_cfg(
        "window.EEPHUS_DIAMOND = { gating: true, price_usd_month: 20, "
        "founding_rate_usd: 12.50 };")
    assert "preview_rows" not in bare


# ===========================================================================
# (b) The truth table, in V8
# ===========================================================================
# Each case builds a fresh context: a stub window/document, the configuration
# under test, then the REAL helper file. document.readyState is "complete"
# unless a case says otherwise, so the helper's DOM-ready hook runs at eval.

BASE_ENV = r"""
var __warns = [];
var console = { warn: function (m) { __warns.push(String(m)); } };
var __domcb = [];
var document = {
  readyState: "complete",
  addEventListener: function (t, cb) { if (t === "DOMContentLoaded") __domcb.push(cb); }
};
var window = {};
var __fires = [];
function __sub() {
  window.EephusDiamond.onEntitlement(function (s) { __fires.push(s); });
}
"""


def _helper_ctx(setup_js: str, ready: str = "complete"):
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    env = BASE_ENV.replace('readyState: "complete"', f'readyState: "{ready}"')
    c.eval(env + setup_js + HELPER)
    return c


CFG_OFF = 'window.EEPHUS_DIAMOND = { gating: false, price_usd_month: 15, founding_rate_usd: 9.99 };\n'
CFG_ON = ('window.EEPHUS_DIAMOND = { gating: true, price_usd_month: 15, '
          'founding_rate_usd: 9.99, '
          'preview_rows: { dynasty: 25, redraft: 25, dfs: 25, cards: 40 } };\n')
ACCT_TMPL = """
var __member = %s;
var __auth = [];
window.EephusAccount = {
  enabled: function () { return %s; },
  isDiamond: function () { return __member; },
  onAuthChange: function (cb) { __auth.push(cb); return function () {}; }
};
"""


def test_gating_off_is_not_gated():
    c = _helper_ctx(CFG_OFF)
    assert c.eval("window.EephusDiamond.gating()") is False
    assert c.eval("window.EephusDiamond.gated()") is False
    assert c.eval("__warns.length") == 0


def test_dead_mans_switch_no_account_layer_at_all():
    """MUTATION: make gating() return the raw flag. A flag that is on while
    nobody can sign in must answer OPEN, with one warn naming why: capping
    every reader behind a join CTA nobody can complete is an outage, not a
    paywall."""
    c = _helper_ctx(CFG_ON)
    assert c.eval("window.EephusDiamond.gating()") is False
    assert c.eval("window.EephusDiamond.gated()") is False
    # one warn, however often the question is asked
    c.eval("window.EephusDiamond.gated(); window.EephusDiamond.gated()")
    assert c.eval("__warns.length") == 1
    warn = c.eval("__warns[0]")
    assert "account" in warn and "absent" in warn


def test_dead_mans_switch_account_layer_present_but_unconfigured():
    """The shipped state of this checkout: EephusAccount exists but Supabase
    is blank, so enabled() is false everywhere. Same neutralization, warn
    names the configuration rather than the absence."""
    c = _helper_ctx(CFG_ON + ACCT_TMPL % ("false", "false"))
    assert c.eval("window.EephusDiamond.gating()") is False
    assert c.eval("window.EephusDiamond.gated()") is False
    assert c.eval("__warns.length") == 1
    assert "not configured" in c.eval("__warns[0]")


def test_member_is_not_gated_when_the_gate_is_live():
    c = _helper_ctx(CFG_ON + ACCT_TMPL % ("true", "true"))
    assert c.eval("window.EephusDiamond.gating()") is True
    assert c.eval("window.EephusDiamond.member()") is True
    assert c.eval("window.EephusDiamond.gated()") is False
    assert c.eval("__warns.length") == 0


def test_non_member_is_gated_when_the_gate_is_live():
    c = _helper_ctx(CFG_ON + ACCT_TMPL % ("false", "true"))
    assert c.eval("window.EephusDiamond.gating()") is True
    assert c.eval("window.EephusDiamond.member()") is False
    assert c.eval("window.EephusDiamond.gated()") is True


def test_preview_rows_map_and_fallback():
    """MUTATION: read the map without the own-property guard (a `constructor`
    module name would then hand back a function), or change the 25 default."""
    c = _helper_ctx(CFG_ON + ACCT_TMPL % ("false", "true"))
    assert c.eval('window.EephusDiamond.previewRows("dynasty")') == 25
    assert c.eval('window.EephusDiamond.previewRows("cards")') == 40
    assert c.eval('window.EephusDiamond.previewRows("parks")') == 25
    assert c.eval('window.EephusDiamond.previewRows("constructor")') == 25
    bare = _helper_ctx(CFG_OFF)  # config with no map at all
    assert bare.eval('window.EephusDiamond.previewRows("dynasty")') == 25
    junk = _helper_ctx('window.EEPHUS_DIAMOND = { gating: false, '
                       'preview_rows: { dynasty: "lots" } };\n')
    assert junk.eval('window.EephusDiamond.previewRows("dynasty")') == 25


def test_price_reads_the_config():
    c = _helper_ctx(CFG_OFF)
    assert json.loads(c.eval("JSON.stringify(window.EephusDiamond.price())")) == {
        "month": 15, "founding": 9.99}


def test_on_entitlement_fires_once_post_dom_in_every_environment():
    """MUTATION: drop the DOM-ready fire, or the immediate fire for a late
    subscriber. Every environment gets exactly one initial callback carrying
    {gating, member, gated}."""
    for setup, want in (
        (CFG_OFF, {"gating": False, "member": False, "gated": False}),
        (CFG_ON, {"gating": False, "member": False, "gated": False}),   # dead-man
        (CFG_ON + ACCT_TMPL % ("true", "true"),
         {"gating": True, "member": True, "gated": False}),
        (CFG_ON + ACCT_TMPL % ("false", "true"),
         {"gating": True, "member": False, "gated": True}),
    ):
        # subscribe AFTER DOM ready (readyState complete): immediate fire
        c = _helper_ctx(setup)
        c.eval("__sub()")
        assert json.loads(c.eval("JSON.stringify(__fires)")) == [want], setup
        # subscribe BEFORE DOM ready: fires when DOMContentLoaded lands
        c2 = _helper_ctx(setup, ready="loading")
        c2.eval("__sub()")
        assert c2.eval("__fires.length") == 0
        c2.eval("__domcb.forEach(function (cb) { cb(); })")
        assert json.loads(c2.eval("JSON.stringify(__fires)")) == [want], setup


def test_on_entitlement_refires_on_an_auth_change_that_moves_the_answer():
    """MUTATION: stop hooking EephusAccount.onAuthChange, or fire every auth
    event through unfiltered. A sign-in that resolves membership re-fires;
    an auth event that changes nothing does not double-paint the page."""
    c = _helper_ctx(CFG_ON + ACCT_TMPL % ("false", "true"))
    c.eval("__sub()")
    assert c.eval("__fires.length") == 1
    assert c.eval("__fires[0].gated") is True
    # an auth event with no entitlement movement: no re-fire
    c.eval("__auth.forEach(function (cb) { cb(); })")
    assert c.eval("__fires.length") == 1
    # membership resolves: re-fire with the new answer
    c.eval("__member = true; __auth.forEach(function (cb) { cb(); })")
    assert c.eval("__fires.length") == 2
    assert c.eval("__fires[1].member") is True
    assert c.eval("__fires[1].gated") is False


# ===========================================================================
# (c) Row-cap behavior: the real helper driving the real clients
# ===========================================================================
# The dynasty harness is the test_betting Proxy-DOM pattern: innerHTML writes
# are captured per element id, everything else is inert, and fetch is a
# synchronous FT thenable (see the module docstring for the Promise.all trap).

DYN_PRELUDE = r"""
var __html = {};
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},
                                     toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function () { return null; };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'appendChild' || k === 'insertBefore' || k === 'focus') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function FT(v) { return { then: function (cb) { var r = cb(v); return (r && r.then) ? r : FT(r); },
                          catch: function () { return FT(v); } }; }
var location = { hash: '', href: '', pathname: '/dynasty/' };
var document = { readyState: 'complete',
  getElementById: function (id) { return __el(id); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var console = { warn: function () {} };
var window = { location: location, document: document, addEventListener: function () {} };
var PAYLOAD = %s;
var fetch = function () { return FT({ ok: true, json: function () { return FT(PAYLOAD); } }); };
"""

ACCT_LIVE = ACCT_TMPL % ("false", "true")


def _dynasty_payload(n: int = 40) -> str:
    rows = [{"rank": i, "name": "Player %02d" % i, "mlbam": 1000 + i,
             "org": "BOS", "pos": "SS", "efv": 50, "eta": "2027",
             "tier": "Tier 2", "star": 20, "bust": 30, "surplus": 10,
             "band": [1, 20]} for i in range(1, n + 1)]
    return json.dumps({"season": 2026, "sections": {"dynasty": rows,
                                                    "callup_watch": []}})


def _dynasty_ctx(gate_setup: str):
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval((DYN_PRELUDE % _dynasty_payload())
           + gate_setup
           + HELPER
           + (ASSETS / "dynasty.js").read_text(encoding="utf-8"))
    return c


def _dyn_rows(c) -> int:
    return c.eval(
        "(__html['dynasty-app-root'] || '').split('mlb-card ff-card dyn-card').length - 1")


def test_dynasty_gated_renders_exactly_the_preview_cap_with_the_note():
    """MUTATION: point capRows at the wrong module name, drop the slice, or
    lose the gate note. A live gate over a 40-row fixture shows exactly 25
    rows and says what it withheld, with the /diamond/ link."""
    c = _dynasty_ctx(CFG_ON + ACCT_LIVE)
    assert _dyn_rows(c) == 25
    root = c.eval("__html['dynasty-app-root'] || ''")
    assert "Diamond preview: showing the top 25 of 40 rows" in root
    assert 'href="/diamond/"' in root


def test_dynasty_open_renders_every_row_and_no_note():
    """Gating off (the shipped state): all 40 rows, no gate note. The same
    fixture, so the only variable is the flag."""
    c = _dynasty_ctx(CFG_OFF)
    assert _dyn_rows(c) == 40
    assert "Diamond preview:" not in c.eval("__html['dynasty-app-root'] || ''")


def test_dynasty_rerenders_open_when_membership_resolves():
    """THE GHOST-KEY BUG, inverted and killed: a paying member whose session
    resolves after first paint must get the full board without touching the
    page. MUTATION: drop the onEntitlement subscription from dynasty.js."""
    c = _dynasty_ctx(CFG_ON + ACCT_LIVE)
    assert _dyn_rows(c) == 25
    c.eval("__member = true; __auth.forEach(function (cb) { cb(); })")
    assert _dyn_rows(c) == 40
    assert "Diamond preview:" not in c.eval("__html['dynasty-app-root'] || ''")


# ---- betting: the payload swap on entitlement -------------------------------
# betting.js does not cap rows client-side; its preview is a different FILE
# (betting_preview.json, written server-side). The contract here is that the
# entitlement answer picks the file, and a late-resolving membership re-fetches
# the right one, which is the member-first-paint bug this lane fixed.

BET_PRELUDE = r"""
var __html = {};
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},
                                     toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function () { return null; };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'appendChild' || k === 'insertBefore' || k === 'focus') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'parentNode' || k === 'firstChild' || k === 'nextSibling') return null;
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function FT(v) { return { then: function (cb) { var r = cb(v); return (r && r.then) ? r : FT(r); },
                          catch: function () { return FT(v); } }; }
function FR(e) { return { then: function () { return FR(e); },
                          catch: function (cb) { var r = cb(e); return (r && r.then) ? r : FT(r); } }; }
var __nav = { querySelector: function () { return null; }, appendChild: function () {} };
var location = { href: '', hash: '', origin: 'https://eephus.io', pathname: '/betting/' };
var history = { replaceState: function () {} };
var document = { readyState: 'complete',
  getElementById: function (id) { return __el(id); },
  querySelector: function (sel) { return sel === '.mlbstats-sectionnav' ? __nav : null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var console = { warn: function () {} };
var window = { location: location, document: document, addEventListener: function () {} };
var __fetched = [];
var __ROUTES = { "/data/betting.json": %s, "/data/betting_preview.json": %s };
var fetch = function (url) {
  __fetched.push(String(url));
  var d = __ROUTES[url];
  if (d === undefined) return FR(new Error('HTTP 404'));
  return FT({ ok: true, json: function () { return FT(d); } });
};
"""


def _bet_payload(slate: str) -> str:
    return json.dumps({
        "slate_date": slate, "n_games": 1,
        "status": {"odds_feed": "not_configured"},
        "model": {"validated": False, "stage": "Diamond preview"},
        "disclaimer": {"age": "21+ only.", "purpose": "Informational.",
                       "legality": "Not legal in all states.",
                       "help": "1-800-GAMBLER", "helpline": "1-800-GAMBLER",
                       "affiliates": "none", "staking": "flat"},
        "pick_of_the_day": None, "pick_reason": "unvalidated",
        "team_bets": [], "props_fair_lines": {"model_only": True, "pitchers": [],
                                              "hitters": []},
        "parlay_context": {"rules": [], "legs": []},
        "record": {"n_rows": 0},
    })


def _payload_fetches(c) -> list:
    """The board-payload fetches only. betting.js also lazily fetches the aux
    artifacts (learning/evald/clv) whose 404s are part of normal rendering;
    they are not what this contract is about."""
    urls = json.loads(c.eval("JSON.stringify(__fetched)"))
    return [u for u in urls
            if u in ("/data/betting.json", "/data/betting_preview.json")]


def test_betting_member_first_paint_refetches_the_full_payload():
    """MUTATION: remove the onEntitlement wiring beside boot(), or the
    LOADED_URL comparison inside it. Gate live, member unresolved at boot:
    the first fetch is the preview file. Membership resolving true must
    re-fetch the FULL payload and repaint off it; the pre-fix client would
    have left the member staring at the preview until a manual reload."""
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval((BET_PRELUDE % (_bet_payload("FULL-SLATE"), _bet_payload("PREVIEW-SLATE")))
           + CFG_ON + ACCT_LIVE + HELPER
           + (ASSETS / "betting.js").read_text(encoding="utf-8"))
    assert _payload_fetches(c) == ["/data/betting_preview.json"]
    assert "PREVIEW-SLATE" in c.eval("__html['betting-banner'] || ''")
    c.eval("__member = true; __auth.forEach(function (cb) { cb(); })")
    assert _payload_fetches(c) == ["/data/betting_preview.json",
                                   "/data/betting.json"]
    assert "FULL-SLATE" in c.eval("__html['betting-banner'] || ''")
    # and an auth event that moves nothing does not re-fetch
    c.eval("__auth.forEach(function (cb) { cb(); })")
    assert len(_payload_fetches(c)) == 2


def test_betting_gate_off_fetches_the_full_payload_once():
    """The shipped state: gating false, one fetch, the full file."""
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval((BET_PRELUDE % (_bet_payload("FULL-SLATE"), _bet_payload("PREVIEW-SLATE")))
           + CFG_OFF + HELPER
           + (ASSETS / "betting.js").read_text(encoding="utf-8"))
    assert _payload_fetches(c) == ["/data/betting.json"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
