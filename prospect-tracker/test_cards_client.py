# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/cards/ client honesty guards (assets/cards.js + the ingest and watchlist seams).

Three seams, one theme. The board has served 40 tracked / 0 priced for its
whole life; the export has said WHY since 2026-08-07 (meta.ingest, state
fetch_blocked, red true, 22 attempted / 0 fetched / 22 errors); and until
2026-08-16 the client never rendered one byte of that block while its empty
copy promised comps would land. These tests pin the repair:

  * the ingest banner renders above every board when state != "ok", carrying
    the state, the export's why sentence, the last scrape's counters and the
    days since a comp last reached the store;
  * the empty copy branches on the ingest state, so "fills in as sold comps
    land" can only print when the ingest itself reports ok;
  * card_prices_ingest --validate dry-runs a drop CSV with per-row verdicts
    and never opens the DB, so the drop seam is testable the day a source
    exists;
  * build_watchlist honors data/card_watchlist_overrides.json, so a
    regeneration off a moved board cannot demote the owner's hand-picked hot
    cards.

The rendering half drives assets/cards.js in py_mini_racer on the
test_fantasy_cards harness pattern: a Proxy DOM that captures innerHTML
writes, section-button stubs whose clicks re-render, and a synchronous FT
thenable standing in for fetch. KNOWN TRAP, inherited from that harness: FT
is a fake thenable and cannot satisfy Promise.all. cards.js uses plain .then
chains only; if it ever grows a Promise.all, these stubs must grow real
promises first, not another fake.

Every test states its mutation: the single product edit that must turn it red.
Tests avoid pytest fixtures on purpose (tempfile + try/finally instead), so
each one is also runnable directly via python -c while the suite is owned by
the orchestrator.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
JS_PATH = ROOT / "assets" / "cards.js"
JS = JS_PATH.read_text(encoding="utf-8")

import card_prices_ingest as ci  # noqa: E402  (stdlib-only at import time)


# ===========================================================================
# Source guards (no py_mini_racer needed)
# ===========================================================================

def test_client_reads_meta_ingest_and_render_leads_with_the_banner():
    """MUTATION: delete the `ingestBanner() +` call from render() (or the
    function's DATA.meta.ingest read). The server has published the whole
    "why is this board empty" block since 2026-08-07; the client not reading
    it is exactly the defect this file exists to keep out."""
    assert "DATA.meta.ingest" in JS, "cards.js no longer reads meta.ingest"
    assert re.search(r"root\.innerHTML\s*=\s*ingestBanner\(\)\s*\+", JS), (
        "render() no longer leads every board with the ingest banner")


def test_shell_attribute_normalized_and_client_shim_kept():
    """MUTATION: revert the build_cards() attribute to data-cardssection, or
    drop either spelling from the client's SECTION_NODES shim. The shell and
    the client disagreed by one letter until 2026-08-16 and three of the four
    boards were unreachable; the fix is the shell on the singular name AND
    the client still accepting both (backward armor for a cached shell)."""
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert 'data-cardsection="screen"' in src, "shell lost the normalized attribute"
    assert 'data-cardssection="' not in src, "the misspelled shell attribute is back"
    assert '"[data-cardsection],[data-cardssection]"' in JS, (
        "the client shim must keep accepting both spellings")


def test_empty_copy_is_not_unconditionally_optimistic():
    """MUTATION: hand renderList a bare string again in renderBuy or
    renderMovers, bypassing emptyBoardCopy. The optimistic sentence may only
    exist as emptyBoardCopy's okTail argument, where the state branch decides
    whether it prints; the rendering tests below prove the branch itself."""
    buy = JS.split("function renderBuy()")[1].split("function renderMovers()")[0]
    movers = JS.split("function renderMovers()")[1].split("function renderWatchlist()")[0]
    for name, body in (("renderBuy", buy), ("renderMovers", movers)):
        assert re.search(r"renderList\(rows,\s*emptyBoardCopy\(", body), (
            f"{name} no longer routes its empty copy through emptyBoardCopy")


# ===========================================================================
# Rendering: the banner and the branched empty copy, in a real JS engine
# ===========================================================================

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

WHY = ("Every one of at least 3 scrape requests failed before a page came back. "
       "Nothing was fetched, so no parser change can help: the source is refusing "
       "the fetcher and the board stays dark until a reachable source is wired.")

FETCH_BLOCKED = {
    "state": "fetch_blocked", "why": WHY, "red": True, "scrape_armed": False,
    "comps_on_file": 0, "cards_with_comps": 0, "last_ingest_on": None,
    "days_since_ingest": None,
    "last_scrape": {"ran_on": "2026-08-06", "scope": "hot",
                    "cards_attempted": 22, "cards_fetched": 0, "cards_zero_rows": 0,
                    "fetch_errors": 22, "rows_parsed": 0, "rows_stored": 0},
}
OK_INGEST = {"state": "ok", "why": "Comps are being ingested on schedule.",
             "red": False, "days_since_ingest": 0, "last_ingest_on": "2026-08-16",
             "last_scrape": None}
STALE_INGEST = {"state": "stale",
                "why": ("Comps are on file but nothing new has been stored in 14 "
                        "days. The scheduled ingest is not reaching the store."),
                "red": False, "days_since_ingest": 21, "last_ingest_on": "2026-07-26",
                "last_scrape": {"ran_on": "2026-07-26", "scope": "hot",
                                "cards_attempted": 5, "cards_fetched": 5,
                                "fetch_errors": 0}}


def _payload(ingest) -> dict:
    """Two tracked, zero priced: the shape /cards/ has served since it shipped."""
    return {
        "as_of": "2026-08-16", "screen": True, "method": {}, "disclaimer": {},
        "meta": {"n_cards": 2, "n_priced": 0, "n_unpriced": 2, "min_comps": 5,
                 "raw_comps_published": False, "ingest": ingest},
        "cards": [
            {"card_id": "jesus-made|bowman-chrome-prospect-auto|psa-10",
             "name": "Jesus Made", "org": "MIL", "set": "Bowman Chrome Prospect Auto",
             "grade": "PSA 10", "tier": "prospect", "efv": 61.9, "efv_kind": "model",
             "index_usd": None, "prior_index_usd": None, "trend_pct": None,
             "gap": None, "talent_pct": 98.0, "market_pct": None,
             "signal": "unpriced", "history": [], "index_n": 0,
             "comp_count_total": 0, "index_reason": "none"},
            {"card_id": "tarik-skubal|topps-chrome-rookie-refractor|psa-10",
             "name": "Tarik Skubal", "org": "DET",
             "set": "Topps Chrome Rookie Refractor", "grade": "PSA 10",
             "tier": "mlb", "efv": 60.0, "efv_kind": "debuted",
             "index_usd": None, "prior_index_usd": None, "trend_pct": None,
             "gap": None, "talent_pct": None, "market_pct": None,
             "signal": "unpriced", "history": [], "index_n": 0,
             "comp_count_total": 0, "index_reason": "none"},
        ],
    }


PRELUDE_TMPL = r"""
var __html = {};
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function () { return __el(id + 'q'); };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'focus' || k === 'appendChild' || k === 'insertBefore') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'dataset') return {};
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
// The section buttons carry ONLY the misspelled shell attribute on purpose:
// the client shim must keep accepting data-cardssection, and these stubs are
// what proves it stays wired.
function __btn(sec) {
  var hs = [];
  return { __sec: sec,
    getAttribute: function (n) { return n === 'data-cardssection' ? sec : null; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {},
                 toggle: function () {}, contains: function () { return false; } },
    addEventListener: function (t, cb) { if (t === 'click') hs.push(cb); },
    click: function () { hs.forEach(function (h) { h({}); }); } };
}
var __btns = ['screen', 'movers', 'watchlist', 'method'].map(__btn);
function __render(sec) {
  for (var i = 0; i < __btns.length; i++) if (__btns[i].__sec === sec) __btns[i].click();
  return __html['cards-app-root'] || '';
}
function FT(val) { return { then: function (cb) { var r = cb(val); return (r && r.then) ? r : FT(r); },
                            catch: function () { return FT(val); } }; }
var PAYLOAD = %s;
var fetch = function (url) {
  if (String(url).indexOf('card_market') >= 0) {
    return FT({ ok: true, json: function () { return FT(PAYLOAD); } });
  }
  return FT({ ok: true, json: function () { return FT({ byMlbam: {} }); } });
};
var location = { href: '', hash: '', pathname: '/cards/' };
var history = { replaceState: function () {} };
var document = { readyState: 'complete',
  getElementById: function (id) { return __el(id); },
  querySelector: function () { return __el('q'); },
  querySelectorAll: function (sel) {
    return String(sel).indexOf('cardsection') >= 0 ? __btns : [];
  },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var window = { location: location, document: document, fetch: fetch,
               addEventListener: function () {} };
"""


def _boot(ingest) -> "MiniRacer":
    c = MiniRacer()
    c.eval((PRELUDE_TMPL % json.dumps(_payload(ingest))) + JS)
    return c


def _root(c) -> str:
    return c.eval("__html['cards-app-root'] || ''")


def test_fetch_blocked_renders_the_ingest_banner():
    """MUTATION: remove `ingestBanner() +` from render() in cards.js. The
    payload the server already writes must reach the page: state, why, the
    last scrape's counters, its date, and the never-ingested fact."""
    html = _root(_boot(FETCH_BLOCKED))
    assert "fetch blocked" in html, "state tag missing (underscores swapped for spaces)"
    assert "the source is refusing the fetcher" in html, "the payload's why sentence missing"
    assert "22 attempted, 0 fetched, 22 errors" in html, "last_scrape counters missing"
    assert "2026-08-06" in html, "last_scrape ran_on missing"
    assert "No comp has ever reached the store." in html, "days-since-ingest fact missing"
    # ingest banner plus the standing Screen banner
    assert html.count("cards-screen-banner") == 2, html.count("cards-screen-banner")


def test_banner_leads_every_board_not_only_buy():
    """MUTATION: move the ingestBanner() call from render() into renderBuy()
    alone; Movers, Watchlist and Method go quiet again."""
    c = _boot(FETCH_BLOCKED)
    for sec in ("movers", "watchlist", "method"):
        html = c.eval("__render('%s')" % sec)
        assert "fetch blocked" in html, f"{sec} lost the ingest banner"


def test_fetch_blocked_empty_copy_is_honest_on_buy_and_movers():
    """MUTATION: make emptyBoardCopy() return `lead + okTail` unconditionally
    (the pre-fix behavior). The optimistic sentence was false the whole time
    the source 403d every request."""
    c = _boot(FETCH_BLOCKED)
    buy = _root(c)
    assert "The price source is refusing automated reads" in buy
    assert "stays dark until a licensed or manual source is wired" in buy
    assert "fills in as sold comps land" not in buy, "optimistic copy under a blocked fetcher"
    movers = c.eval("__render('movers')")
    assert "No card has two priced windows yet." in movers
    assert "refusing automated reads" in movers
    assert "fill in as history accumulates" not in movers


def test_ok_state_keeps_the_optimistic_copy_and_no_banner():
    """MUTATION: invert the state branch in emptyBoardCopy() (pessimistic copy
    under ok), or drop the state guard in ingestBanner() so it renders always.
    Honest does not mean gloomy: with a healthy ingest and thin data, the
    original sentences are true and must survive."""
    c = _boot(OK_INGEST)
    buy = _root(c)
    assert "The screen fills in as sold comps land in the window." in buy
    assert "refusing automated reads" not in buy
    assert buy.count("cards-screen-banner") == 1, "ingest banner rendered on state ok"
    movers = c.eval("__render('movers')")
    assert "Movers fill in as history accumulates." in movers


def test_missing_ingest_block_makes_no_claim():
    """MUTATION: make emptyBoardCopy() fall through to the optimistic tail when
    meta.ingest is null. The export publishes null to say "no claim made", and
    the page must not upgrade that to a promise."""
    buy = _root(_boot(None))
    assert "no claim is made about when comps will land" in buy
    assert "fills in as sold comps land" not in buy
    assert buy.count("cards-screen-banner") == 1


def test_stale_state_points_at_the_banner_and_counts_the_days():
    """MUTATION: hardcode the fetch_blocked sentence for every non-ok state.
    Stale is not blocked: the copy must defer to the banner, and the banner
    must carry the day count the payload published."""
    buy = _root(_boot(STALE_INGEST))
    assert "Last comp stored 21 days ago." in buy
    assert "the notice above" in buy
    assert "refusing automated reads" not in buy
    assert "fills in as sold comps land" not in buy


def test_watchlist_rows_still_render_under_the_banner():
    """MUTATION: any banner edit that throws mid-render (the failure mode of
    string-built HTML) blanks the whole board; the tracked rows must survive."""
    c = _boot(FETCH_BLOCKED)
    wl = c.eval("__render('watchlist')")
    assert "Jesus Made" in wl and "Tarik Skubal" in wl
    assert "fetch blocked" in wl


# ===========================================================================
# --validate: the drop-CSV preflight (nothing stored, ever)
# ===========================================================================

VALIDATE_WATCHLIST = {"version": 1, "cards": [
    {"card_id": "jesus-made|bowman-chrome-prospect-auto|psa-10",
     "player_key": "jesus_made", "player_name": "Jesus Made",
     "set_desc": "Bowman Chrome Prospect Auto", "grade_bucket": "PSA 10",
     "mlbam": 800100, "hot": True},
]}

# Header line 1; data rows are lines 2..7 and the verdicts are keyed that way.
CSV_GOOD_AND_BAD = (
    "card_id,player_key,set_desc,grade,sold_date,price_usd,title\n"
    'jesus-made|bowman-chrome-prospect-auto|psa-10,,,PSA 10,2026-08-01,"$1,250.00",listing one\n'
    ",jesus_made,Bowman Chrome Prospect Auto,PSA 10,08/02/2026,980,listing two\n"
    ",other_guy,Topps Sapphire,RAW,2026-08-03,55.50,listing three\n"
    ",jesus_made,Bowman Chrome Prospect Auto,PSA 10,2026-08-04,n/a,bad price\n"
    ",jesus_made,Bowman Chrome Prospect Auto,PSA 10,someday,80,bad date\n"
    ",,Topps Sapphire,RAW,2026-08-05,60,no identity\n"
)


def _no_db(*_a, **_k):
    raise AssertionError("--validate touched the DB; it must be a pure dry run")


def test_validate_accepts_good_rows_and_rejects_bad_ones_without_the_db():
    """MUTATION: invert the price reject in validate_drop_csv (`if price is
    None` to `if price is not None`): row 5 flips to accept, rows 2 to 4 flip
    to reject, and both assertions below go red. The _connect stub is its own
    guard: any DB touch raises."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "card_comps_2026-08-16.csv"
        p.write_text(CSV_GOOD_AND_BAD, encoding="utf-8")
        real_connect = ci._connect
        ci._connect = _no_db
        try:
            rep = ci.validate_drop_csv(p, watchlist=VALIDATE_WATCHLIST)
        finally:
            ci._connect = real_connect
    assert rep["ok"] and rep["error"] is None, rep
    v = {r["row"]: r for r in rep["rows"]}
    assert [v[n]["accept"] for n in (2, 3, 4, 5, 6, 7)] == \
        [True, True, True, False, False, False], v
    # row 2 matched by card_id, row 3 by the (player_key, set, grade) triple
    assert v[2]["on_watchlist"] and v[3]["on_watchlist"]
    assert v[3]["card_id"] == "jesus-made|bowman-chrome-prospect-auto|psa-10"
    # row 4 is a known-player, unlisted card: accepted off-list under a derived id
    assert not v[4]["on_watchlist"]
    assert v[4]["card_id"] == "other-guy|topps-sapphire|raw"
    # rejects carry the reason a human can act on
    assert "price" in v[5]["reason"], v[5]
    assert "date" in v[6]["reason"], v[6]
    assert "identity" in v[7]["reason"], v[7]
    assert (rep["accepted"], rep["rejected"]) == (3, 3)
    assert (rep["on_watchlist"], rep["off_list"]) == (2, 1)


def test_validate_cli_exit_codes():
    """MUTATION: make validate_drop_csv report ok=True when the required
    price/date columns are absent (or main() stop returning 1 on a rejected
    file). Exit 0 must mean 'the file parses'; a broken column contract or a
    missing file must exit 1 so a preflight in a script actually gates."""
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "card_comps_good.csv"
        good.write_text(CSV_GOOD_AND_BAD, encoding="utf-8")
        bad = Path(td) / "card_comps_bad.csv"
        bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
        assert ci.main(["--validate", str(good)]) == 0
        assert ci.main(["--validate", str(bad)]) == 1
        assert ci.main(["--validate", str(Path(td) / "absent.csv")]) == 1


def test_validate_never_writes_the_drop_ledger():
    """MUTATION: route --validate through ingest_csv. The whole point of the
    flag is a read-only look at a candidate file; the ledger and the comp
    store must be byte-identical before and after. Proven by stubbing the one
    connection seam: validate_drop_csv must finish without it."""
    src = (ROOT / "card_prices_ingest.py").read_text(encoding="utf-8")
    body = src.split("def validate_drop_csv(")[1].split("\ndef ")[0]
    for banned in ("store_comps", "ingest_csv", "_connect", "card_drop_files"):
        assert banned not in body, f"validate_drop_csv references {banned}"


# ===========================================================================
# build_watchlist: the hot overrides merge
# ===========================================================================

def _fixture_board(d: Path, n: int = 14) -> None:
    """xfv + timeseries fixtures: n prospects ranked by a stub board value."""
    players, by_player = [], {}
    for i in range(1, n + 1):
        k = f"prospect_{i:02d}"
        players.append({"player_key": k, "player_name": f"Prospect {i:02d}",
                        "mlbam_id": 900000 + i, "org": "AAA", "position": "SS",
                        "eta": {"year": 2027}})
        by_player[k] = {"kind": "active", "side": "H", "v": 100.0 - i}
    (d / "xfv.json").write_text(json.dumps({"by_player": by_player}), encoding="utf-8")
    (d / "timeseries.json").write_text(json.dumps({"players": players}), encoding="utf-8")


def test_build_watchlist_honors_the_hot_overrides_file():
    """MUTATION: delete the overrides merge at the end of build_watchlist (the
    loop that forces c["hot"] = True for listed ids). prospect_14 ranks 14th,
    the generator flags only the top 12 hot, so without the merge the pinned
    card comes back hot=False and the regeneration has destroyed a hand-pick.
    board_value is stubbed via sys.modules so the fixture stays three keys."""
    stub = types.SimpleNamespace(board_value=lambda rec: rec.get("v"))
    real = sys.modules.get("efv_board_scale")
    sys.modules["efv_board_scale"] = stub
    try:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _fixture_board(d)
            pin = ci.card_id("prospect_14", ci._PROSPECT_SET, ci._DEFAULT_GRADE)
            (d / "card_watchlist_overrides.json").write_text(
                json.dumps({"version": 1, "hot": [pin]}), encoding="utf-8")
            doc = ci.build_watchlist(n_prospects=14, n_mlb=0, data_dir=d)
    finally:
        if real is None:
            sys.modules.pop("efv_board_scale", None)
        else:
            sys.modules["efv_board_scale"] = real
    by_id = {c["card_id"]: c for c in doc["cards"]}
    assert len(by_id) == 14
    assert by_id[pin]["hot"] is True, "the override did not win over the rank rule"
    # unlisted cards keep the generated flag, in both directions
    p13 = ci.card_id("prospect_13", ci._PROSPECT_SET, ci._DEFAULT_GRADE)
    p01 = ci.card_id("prospect_01", ci._PROSPECT_SET, ci._DEFAULT_GRADE)
    assert by_id[p13]["hot"] is False, "overrides must not hot unlisted cards"
    assert by_id[p01]["hot"] is True, "the generator's own top-12 flag was lost"


def test_build_watchlist_survives_a_missing_or_broken_overrides_file():
    """MUTATION: read the overrides file without the `or {}` fallback (or key
    into it without .get). A fresh checkout has no overrides file and a broken
    one must degrade to the generated flags, never crash the build."""
    stub = types.SimpleNamespace(board_value=lambda rec: rec.get("v"))
    real = sys.modules.get("efv_board_scale")
    sys.modules["efv_board_scale"] = stub
    try:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _fixture_board(d, n=3)
            doc = ci.build_watchlist(n_prospects=3, n_mlb=0, data_dir=d)  # no file
            assert len(doc["cards"]) == 3
            (d / "card_watchlist_overrides.json").write_text("{not json", encoding="utf-8")
            doc = ci.build_watchlist(n_prospects=3, n_mlb=0, data_dir=d)  # broken file
            assert len(doc["cards"]) == 3
    finally:
        if real is None:
            sys.modules.pop("efv_board_scale", None)
        else:
            sys.modules["efv_board_scale"] = real


def test_committed_overrides_are_coherent_with_the_committed_watchlist():
    """MUTATION: add a card_id to data/card_watchlist_overrides.json that
    data/card_watchlist.json does not carry, or demote a pinned card's hot
    flag by hand without touching the overrides. Overrides win on the next
    regeneration, so the two committed files must agree TODAY: every pinned
    id exists on the watchlist and is hot there."""
    ov = json.loads((ROOT / "data" / "card_watchlist_overrides.json")
                    .read_text(encoding="utf-8"))
    wl = json.loads((ROOT / "data" / "card_watchlist.json").read_text(encoding="utf-8"))
    assert isinstance(ov.get("hot"), list) and ov["hot"], "empty or malformed hot list"
    assert all(isinstance(x, str) and x for x in ov["hot"])
    ids = {c["card_id"] for c in wl["cards"]}
    missing = [x for x in ov["hot"] if x not in ids]
    assert not missing, f"override ids not on the watchlist: {missing}"
    hot_now = {c["card_id"] for c in wl["cards"] if c.get("hot")}
    stray = [x for x in ov["hot"] if x not in hot_now]
    assert not stray, (
        f"pinned but not hot in the committed watchlist (reconcile deliberately, "
        f"overrides win on regeneration): {stray}")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
