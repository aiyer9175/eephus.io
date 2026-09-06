# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the Diamond section scaffold (2026-08-05).

Six new public pages (Dynasty, Redraft, DFS, Sports Betting, Card Market,
Diamond Pass) landed as one nav group on 2026-08-05. On 2026-08-07 the first
three merged back into one Fantasy module and became redirect stubs, so the
group is four leaves over six shipping dirs. That is four things that can
drift independently:

  1. `build_site.NAV_ITEMS` and the three hand-maintained static nav copies.
     test_collegesavant_nav_in_sync already guards the copies against the
     canonical leaf list; what it CANNOT catch is the group vanishing from
     NAV_ITEMS entirely, because then both sides agree on the wrong thing.
     The nav tests here pin the intended shape, not just the agreement.
  2. `deploy/publish_paths.txt`. A page dir that is not on that list 404s in
     production even though every test is green (the 2026-07-14 incident).
     test_publish_manifest catches a dir that already has an index.html;
     these pins catch the window BEFORE the first build, when the dir does
     not exist yet and the sweep has nothing to find.
  3. The entitlement migration. `diamond_until` is worthless as a privilege
     unless it is inside the guard trigger: without that line any signed-in
     user can PATCH their own profile and hand themselves a membership.
     That is a one-line mistake with a real blast radius, so it gets a test.
  4. The gate flag. It ships OFF by owner decision. If a future edit flips
     `gating` to true without also building the members-only data path, the
     site starts hiding UI while the payload stays readable in /data/. Pin
     the shipped value so that flip is deliberate.

No page-render assertions here: the six pages do not exist on disk until
build_site.main() runs, and this file is meant to pass before that.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_site
from build_site import MODULE_STAGE, NAV_ITEMS, nav_leaves

ROOT = Path(__file__).parent

# The leaves, in nav order, exactly as the group declares them.
#
# FOUR, not the original six. Dynasty / Redraft / DFS merged back into one
# /fantasy/ module on 2026-08-07 (owner decision 10): they are sub-modules
# behind one module bar now, and three of six dropdown entries being three tabs
# of one product is what the merge was asked to fix.
DIAMOND_LEAVES = [
    ("fantasy", "Fantasy", "/fantasy/"),
    ("betting", "Sports Betting", "/betting/"),
    ("diamond", "Diamond Pass", "/diamond/"),
]
# The page DIRS are still six, and that is the point: /dynasty/, /redraft/ and
# /dfs/ were public addresses for two days, so they still build and still ship
# as hash-preserving redirect stubs.
DIAMOND_DIRS = ["betting", "dfs", "diamond", "dynasty", "fantasy", "redraft"]
MERGED_DIRS = ["dynasty", "redraft", "dfs"]


def _diamond_group() -> dict:
    for item in NAV_ITEMS:
        if isinstance(item, dict) and item.get("group") == "Diamond":
            return item
    pytest.fail('NAV_ITEMS has no "Diamond" group')


# ---------------------------------------------------------------------------
# 1. Nav
# ---------------------------------------------------------------------------

def test_diamond_group_carries_its_leaves_in_order():
    assert list(_diamond_group()["children"]) == DIAMOND_LEAVES


def test_diamond_group_sits_after_the_mlb_modules_group():
    """Owner-set nav order: the MLB modules, then Diamond, then the editorial
    links. A group that drifts to the end of the bar is a different site."""
    groups = [i["group"] for i in NAV_ITEMS if isinstance(i, dict)]
    assert groups.index("Diamond") == groups.index("MLB Modules") + 1
    keys = [k for k, _l, _h in nav_leaves()]
    assert keys.index("fantasy") > keys.index("trademachine")
    assert keys.index("diamond") < keys.index("articles")


def test_group_key_does_not_collide_with_the_diamond_leaf():
    """_nav() matches `active` against LEAF keys. A group whose key is also a
    leaf key is an ambiguity waiting to be read the wrong way."""
    leaf_keys = {k for k, _l, _h in nav_leaves()}
    for item in NAV_ITEMS:
        if isinstance(item, dict):
            assert item["key"] not in leaf_keys, (
                f'group key {item["key"]!r} collides with a leaf key')


def test_the_three_split_leaves_are_gone_from_the_nav():
    """Dynasty / Redraft / DFS merged back into /fantasy/ on 2026-08-07. A
    leftover leaf would point at a redirect stub and read as a module of its
    own, which is exactly the shape the merge retired."""
    keys = {k for k, _l, _h in nav_leaves()}
    hrefs = {h for _k, _l, h in nav_leaves()}
    assert "fantasy" in keys and "/fantasy/" in hrefs
    for gone in MERGED_DIRS:
        assert gone not in keys, f"{gone} is still a nav leaf"
        assert f"/{gone}/" not in hrefs, f"/{gone}/ is still a nav href"


def test_nav_leaves_are_unique():
    leaves = nav_leaves()
    keys = [k for k, _l, _h in leaves]
    hrefs = [h for _k, _l, h in leaves]
    assert len(set(keys)) == len(keys), "duplicate nav leaf key"
    assert len(set(hrefs)) == len(hrefs), "duplicate nav leaf href"


# ---------------------------------------------------------------------------
# 2. The three hand-maintained static nav copies
# ---------------------------------------------------------------------------
# Reuses the canonical guard's own helpers so there is one regex for the nav
# block on the whole suite. That test asserts agreement with nav_leaves(); this
# one asserts the Diamond block is specifically THERE, so a nav change that
# dropped the group from both sides at once still goes red here.

from test_collegesavant_nav_in_sync import (  # noqa: E402  (import after ROOT)
    _LINK_RE,
    _NAV_RE,
    STATIC_NAV_PAGES,
)


@pytest.mark.parametrize("page", STATIC_NAV_PAGES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_static_navs_carry_the_diamond_group(page: Path):
    nav = _NAV_RE.search(page.read_text(encoding="utf-8"))
    assert nav, f'{page.name}: no <nav class="eephus-links"> block'
    nav = nav.group(1)
    assert ">Diamond<" in nav, f"{page.name}: missing the Diamond group summary"
    for _key, label, href in DIAMOND_LEAVES:
        assert f'href="{href}"' in nav, f"{page.name}: missing {href}"
        assert f">{label}<" in nav, f"{page.name}: missing the {label} label"
    for gone in MERGED_DIRS:
        assert f'"/{gone}/"' not in nav, f"{page.name}: stale /{gone}/ nav link"
    assert len(_LINK_RE.findall(nav)) == len(nav_leaves())


# ---------------------------------------------------------------------------
# 3. Pages, stage chips, sitemap, deploy manifest
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", [k for k, _l, _h in DIAMOND_LEAVES])
def test_every_diamond_key_has_a_stage_chip_row(key: str):
    assert key in MODULE_STAGE, f"MODULE_STAGE has no row for {key}"
    label, title = MODULE_STAGE[key]
    assert label and title
    chip = build_site._stage_chip(key)
    assert 'class="eephus-beta"' in chip and label in chip


def test_the_three_content_modules_are_labeled_diamond_preview():
    """Owner decision: ships public, labeled preview, gate flag off. The label
    is the honest part of that arrangement, so it is pinned. One row for
    Fantasy since the merge: three sub-modules under one masthead carry one
    chip, not three."""
    for key in ("fantasy", "betting"):
        assert "Diamond preview" in MODULE_STAGE[key][0]


@pytest.mark.parametrize("rel,fn", [
    ("fantasy/index.html", "build_fantasy"),
    ("dynasty/index.html", "build_dynasty"),
    ("redraft/index.html", "build_redraft"),
    ("dfs/index.html", "build_dfs"),
    ("betting/index.html", "build_betting"),
    ("diamond/index.html", "build_diamond"),
])
def test_builder_is_registered_in_main(rel: str, fn: str):
    import inspect
    src = inspect.getsource(build_site.main)
    assert f'_write("{rel}", {fn}())' in src, (
        f"{fn} is not wired into build_site.main() - the page would never be written")


def test_diamond_routes_are_in_the_sitemap():
    sitemap = build_site.build_sitemap([])
    for _key, _label, href in DIAMOND_LEAVES:
        assert f"<loc>{build_site.SITE_ORIGIN}{href}</loc>" in sitemap


@pytest.mark.parametrize("mod", MERGED_DIRS)
def test_the_split_dirs_are_hash_preserving_redirects_into_fantasy(mod: str):
    """The merge reversed the 2026-08-05 direction: /fantasy/ is the module and
    the three split dirs are the stubs. HASH-PRESERVING is the load-bearing
    word. These three URLs carried working boards for two days and people
    bookmarked deep links into them, so a stub that dropped the hash would
    answer every one of those bookmarks with the module's default tab."""
    html = getattr(build_site, f"build_{mod}")()
    assert f'content="0; url=/fantasy/#m={mod}"' in html
    assert f'location.replace("/fantasy/#m={mod}"' in html
    assert 'location.hash' in html, "the stub drops the incoming hash"
    assert 'name="robots" content="noindex"' in html
    # And it never sends the reader back to a page that is now a stub itself.
    for other in MERGED_DIRS:
        assert f'"/{other}/"' not in html, f"{mod} stub links at /{other}/"


def test_the_fantasy_module_is_the_only_one_of_the_four_in_the_sitemap():
    """A noindex redirect in the sitemap is a crawl budget spent on a 302 that
    is not even a 302. The module page is the crawlable surface."""
    sitemap = build_site.build_sitemap([])
    assert f"<loc>{build_site.SITE_ORIGIN}/fantasy/</loc>" in sitemap
    for mod in MERGED_DIRS:
        assert f"<loc>{build_site.SITE_ORIGIN}/{mod}/</loc>" not in sitemap


def _manifest_paths() -> list[str]:
    out = []
    for line in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_publish_paths_carry_every_diamond_dir():
    manifest = _manifest_paths()
    missing = [d for d in DIAMOND_DIRS if d not in manifest]
    assert not missing, f"deploy/publish_paths.txt is missing {missing} - they will 404 in production"


def test_the_retired_fantasy_dirs_still_ship():
    """They are redirect stubs, and a redirect that does not ship is a 404.
    This is the direction that flipped on 2026-08-07: /fantasy/ is the module
    and /dynasty/, /redraft/ and /dfs/ are the stubs."""
    manifest = _manifest_paths()
    for d in MERGED_DIRS + ["fantasy"]:
        assert d in manifest, (
            f"/{d}/ is not on the deploy list; every bookmark to it becomes a 404")


# ---------------------------------------------------------------------------
# 4. Entitlements migration
# ---------------------------------------------------------------------------

MIGRATION = ROOT / "supabase" / "migrations" / "0005_diamond.sql"


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert MIGRATION.exists(), "supabase/migrations/0005_diamond.sql is missing"
    return MIGRATION.read_text(encoding="utf-8")


def test_migration_is_a_single_transaction(migration_sql: str):
    assert migration_sql.count("\nbegin;") == 1
    assert migration_sql.count("\ncommit;") == 1
    assert migration_sql.index("\nbegin;") < migration_sql.index("\ncommit;")


def test_migration_creates_the_bets_table(migration_sql: str):
    assert "create table if not exists bets" in migration_sql
    for col in ("user_id", "sport", "market", "selection", "odds", "stake",
                "placed_at", "settled_at", "result", "payload"):
        assert re.search(rf"^\s+{col}\s", migration_sql, re.M), f"bets is missing {col}"
    assert "references profiles(id) on delete cascade" in migration_sql
    assert "create type bet_result as enum ('open', 'won', 'lost', 'void')" in migration_sql


def test_bets_are_owner_only_and_never_public_read(migration_sql: str):
    """watchlist's shape, not favorites': a bet log has no public-read policy.
    This asserts the absence, which is the part a copy-paste would get wrong."""
    assert "alter table bets enable row level security" in migration_sql
    body = migration_sql[migration_sql.index("create table if not exists bets"):]
    # Whitespace-tolerant on purpose: the policy lines are column-aligned in
    # the migration, so a fixed single space silently skipped one of them.
    bets_policies = re.findall(
        r'create policy\s+"[^"]+"\s+on\s+bets\s+for\s+(\w+)([^;]*);', body)
    assert {verb for verb, _rest in bets_policies} == {"select", "insert", "update", "delete"}
    for verb, rest in bets_policies:
        assert "auth.uid() = user_id" in rest, f"bets {verb} policy is not owner-scoped"
        assert "using (true)" not in rest, f"bets {verb} policy is public read"


def test_migration_seeds_the_diamond_badge(migration_sql: str):
    assert "insert into badges" in migration_sql
    assert "'diamond'" in migration_sql
    assert "on conflict (slug) do nothing" in migration_sql


def test_diamond_until_is_inside_the_privileged_column_guard(migration_sql: str):
    """The whole entitlement rests on this. profiles is client-updatable under
    the 0001 owner policy, so a diamond_until that the guard does not pin is a
    membership any signed-in user can grant themselves in one request."""
    assert "add column if not exists diamond_until timestamptz" in migration_sql
    guard = migration_sql[migration_sql.index("guard_profile_privileged_cols"):]
    assert "new.diamond_until is distinct from old.diamond_until" in guard
    assert "new.diamond_until := old.diamond_until" in guard
    assert "create trigger trg_guard_profile before update on profiles" in guard


# ---------------------------------------------------------------------------
# 5. The gate flag + the account API it leans on
# ---------------------------------------------------------------------------

CONFIG_JS = ROOT / "assets" / "diamond-config.js"
ACCOUNT_JS = ROOT / "assets" / "eephus-account.js"


def test_gate_flag_ships_off():
    src = CONFIG_JS.read_text(encoding="utf-8")
    assert "window.EEPHUS_DIAMOND" in src
    assert re.search(r"gating:\s*false", src), (
        "assets/diamond-config.js must ship gating:false - the Diamond section "
        "launches public by owner decision, and flipping this alone does not "
        "actually protect any payload on a static site")
    assert re.search(r"price_usd_month:\s*15\b", src)
    assert re.search(r"founding_rate_usd:\s*9\.99", src)


def test_every_diamond_page_loads_the_config_before_its_app():
    """All tags are deferred, so order in the document IS execution order. A
    module app that ran before the flag existed would read undefined.

    TWO TAGS since 2026-08-16: the config (pure data) and then
    assets/eephus-diamond.js, the one gating contract every module client
    routes through. Config first, because the helper reads the flag; both
    stamped with the same content-hash scheme every other asset URL carries,
    or a helper update never reaches a browser that cached the old one."""
    import inspect
    for fn_name in ("build_fantasy", "build_betting", "build_diamond"):
        src = inspect.getsource(getattr(build_site, fn_name))
        assert "DIAMOND_CONFIG_SCRIPT" in src, f"{fn_name} does not load diamond-config.js"
    block = build_site.DIAMOND_CONFIG_SCRIPT
    tags = re.findall(r"<script[^>]*>", block)
    assert len(tags) == 2, f"DIAMOND_CONFIG_SCRIPT is not the two-tag shape: {block}"
    assert "diamond-config.js" in tags[0], "config must load before the helper"
    assert "eephus-diamond.js" in tags[1], "the gating helper tag is missing"
    for tag in tags:
        assert "defer" in tag, f"un-deferred Diamond tag: {tag}"
        assert re.search(r"\?v=[0-9a-f]{8}", tag), f"unstamped Diamond tag: {tag}"


def test_account_layer_exposes_the_diamond_and_bets_api():
    src = ACCOUNT_JS.read_text(encoding="utf-8")
    for fn in ("isDiamond:", "listBets:", "addBet:", "updateBet:",
               "deleteBet:", "mergeLocalBets:"):
        assert fn in src, f"EephusAccount is missing {fn}"
    # The tracker has to work logged out, which is the only reason the local
    # fallback exists; assert the storage key rather than the whole adapter.
    assert "eephus.bets.v1" in src


def test_betting_surfaces_carry_the_legal_block():
    """Non-negotiable rail: 21+, informational only, state-by-state legality,
    no affiliate links, and the helpline. Asserted on the RENDERED page, not on
    the builder source, so a constant that stops being interpolated still fails."""
    d = build_site.BETTING_DISCLAIMER
    for needle in ("21+", "1-800-GAMBLER", "not legal in every state",
                   "affiliate", "not a sportsbook"):
        assert needle in d, f"BETTING_DISCLAIMER is missing {needle!r}"
    betting = build_site.build_betting()
    assert d in betting, "/betting/ does not render BETTING_DISCLAIMER"
    # The Diamond Pass page talks about the betting record, so it carries the
    # short form too rather than sending a reader to the rails on another page.
    diamond = build_site.build_diamond()
    assert "1-800-GAMBLER" in diamond and "21+" in diamond


def test_no_betting_surface_carries_an_affiliate_link():
    """Where affiliate relationships attach is where state licensing attaches.
    There are none, and a stray outbound sportsbook link is the way one would
    appear by accident."""
    page = build_site.build_betting()
    books = ("draftkings", "fanduel", "betmgm", "caesars", "bet365",
             "pointsbet", "barstool", "espnbet")
    low = page.lower()
    for b in books:
        assert b not in low, f"sportsbook link/mention on /betting/: {b}"
    assert "aff=" not in low and "affiliate.com" not in low


def test_diamond_page_never_uses_the_internal_subsidy_framing():
    """Owner instruction: the public line is "Diamond funds the free site".
    The internal framing stays in the plan doc where it belongs. Checked on the
    RENDERED html rather than the source, because the builder's own docstring
    is allowed to name the thing it is avoiding."""
    html_out = build_site.build_diamond().lower()
    assert "diamond funds the free site" in html_out
    for banned in ("subsidize", "subsidise", "subsidy"):
        assert banned not in html_out, (
            f"internal framing leaked into public copy: {banned}")


def test_diamond_page_states_the_price_and_that_nothing_is_gated_yet():
    out = build_site.build_diamond()
    assert "$15" in out and "$9.99" in out
    assert "Founding preview" in out
    low = out.lower()
    assert "not switched on" in low
    assert "stays free" in low


# ---------------------------------------------------------------------------
# 6. The honest-page pass (2026-08-16): prices from the config, claims gated
#    by the artifact, links that exist
# ---------------------------------------------------------------------------
# D0/D1 plus the C2 de-list. /diamond/ prices itself out of
# assets/diamond-config.js through build_site._diamond_cfg(); the receipts
# card may only paint a win the scoreboard artifact itself resolves
# (verdict_vs_consensus.resolvable); the member list is Fantasy + Sports
# Betting; the static CTA claims no control the build does not render. Every
# behavioral pin below was proven against an in-memory mutation before it
# landed (forced win paint, reintroduced price literal, stripped footer link,
# removed CTA guard), so a red here is a regression, not noise.

import inspect  # noqa: E402
import json  # noqa: E402
from datetime import date  # noqa: E402
from unittest import mock  # noqa: E402

DIAMOND_JS = ROOT / "assets" / "diamond.js"

# The claim rail (owner rule): the site may call eFV and the public consensus
# statistically indistinguishable; it may never claim a win the backtest does
# not resolve. These are the phrasings a win claim would arrive in.
BANNED_CLAIMS = ("beats the consensus", "orders better", "discriminates better",
                 "outperforms")
PARTOF_LINE = 'Part of <a href="/diamond/">Diamond</a>.'


# ---- the config is the single price source ---------------------------------

def test_diamond_cfg_parses_the_shipped_config():
    cfg = build_site._diamond_cfg()
    assert cfg["gating"] is False
    assert cfg["price_usd_month"] == 15.0
    assert cfg["founding_rate_usd"] == 9.99


def test_diamond_cfg_refuses_a_config_missing_a_key():
    """A pricing page that guesses its own price is worse than a build that
    stops. Each key is load-bearing on its own."""
    with pytest.raises(ValueError):
        build_site._diamond_cfg("window.EEPHUS_DIAMOND = { gating: false };")
    with pytest.raises(ValueError):
        build_site._diamond_cfg(
            "window.EEPHUS_DIAMOND = { price_usd_month: 15, founding_rate_usd: 9.99 };")
    cfg = build_site._diamond_cfg(
        "window.EEPHUS_DIAMOND = { gating: true, price_usd_month: 20, "
        "founding_rate_usd: 12.50 };")
    assert cfg == {"gating": True, "price_usd_month": 20.0, "founding_rate_usd": 12.5}


def test_diamond_page_prices_are_the_configs_prices():
    """Parity: what _diamond_cfg parses is what the page prints, in the money
    card, the FAQ and the meta description alike."""
    cfg = build_site._diamond_cfg()
    price = build_site._usd(cfg["price_usd_month"])
    founding = build_site._usd(cfg["founding_rate_usd"])
    out = build_site.build_diamond()
    assert f"${price} a month" in out
    assert f"${founding}" in out
    assert f"tools for ${price}" in out, "meta description lost the config price"


def test_build_diamond_source_carries_no_price_literal():
    src = inspect.getsource(build_site.build_diamond)
    assert "$15" not in src, "hardcoded list price is back"
    assert "9.99" not in src, "hardcoded founding rate is back"
    assert "_diamond_cfg(" in src, "the page no longer reads the config"


def test_gated_variant_renders_member_framing_when_the_flag_flips():
    """Both copy variants exist NOW, selected by the parsed flag, so the day
    diamond-config.js flips to gating true the page stops claiming a free
    preview without anyone editing it. Asserted through a patched cfg because
    the shipped flag is pinned off (section 5)."""
    cfg = {"gating": True, "price_usd_month": 15.0, "founding_rate_usd": 9.99}
    with mock.patch.object(build_site, "_diamond_cfg", return_value=cfg):
        out = build_site.build_diamond()
    assert "free while we build" not in out
    assert "Founding preview" not in out
    assert "Diamond is live" in out
    assert "$15 a month" in out and "$9.99" in out
    low = out.lower()
    for claim in BANNED_CLAIMS:
        assert claim not in low, f"gated variant ships a win claim: {claim}"


# ---- the claim rail --------------------------------------------------------

def test_no_banned_accuracy_claim_ships_on_any_diamond_surface():
    js = DIAMOND_JS.read_text(encoding="utf-8").lower()
    page = build_site.build_diamond().lower()
    for claim in BANNED_CLAIMS:
        assert claim not in js, f"diamond.js carries a win claim: {claim}"
        assert claim not in page, f"/diamond/ carries a win claim: {claim}"


# ---- receipts honesty, executed in V8 --------------------------------------
# The harness runs the real assets/diamond.js over a stub DOM and a
# SYNCHRONOUS thenable fetch. Real promises never settle here (nothing pumps
# the microtask queue between evals, and a Promise.all in the harness would
# hang silently), so resolution happens inline through .then/.catch, which is
# every async shape diamond.js uses.

_JS_HARNESS = r"""
var __fixtures = {};
function __setFixture(url, doc) { __fixtures[url] = doc; }
var _els = {};
function _mkEl(id) {
  return { id: id, innerHTML: "", textContent: "",
           querySelector: function () { return null; },
           addEventListener: function () {},
           appendChild: function () {} };
}
var document = {
  readyState: "complete",
  getElementById: function (id) { if (!_els[id]) _els[id] = _mkEl(id); return _els[id]; },
  createElement: function (t) { return _mkEl("<" + t + ">"); },
  head: { appendChild: function () {} },
  addEventListener: function () {}
};
var window = { EEPHUS_DIAMOND: { gating: false, price_usd_month: 15, founding_rate_usd: 9.99 } };
function SyncP(val, err) { this.val = val; this.err = err; this.failed = arguments.length > 1; }
SyncP.prototype.then = function (ok, bad) {
  if (this.failed) return bad ? _call(bad, this.err) : this;
  return ok ? _call(ok, this.val) : this;
};
SyncP.prototype.catch = function (bad) { return this.then(null, bad); };
function _call(fn, arg) {
  try { var r = fn(arg); return (r instanceof SyncP) ? r : new SyncP(r); }
  catch (e) { return new SyncP(undefined, e); }
}
function fetch(url) {
  if (url in __fixtures) {
    var doc = __fixtures[url];
    return new SyncP({ ok: true, json: function () { return new SyncP(doc); } });
  }
  return new SyncP(undefined, new Error("HTTP 404"));
}
function __els() {
  var out = {}; for (var k in _els) out[k] = _els[k].innerHTML; return out;
}
"""


def _run_diamond_js(fixture: dict, extra_js: str = "") -> dict:
    """Boot diamond.js against `fixture` as the scoreboard artifact; returns
    {element id: innerHTML} for everything the client touched."""
    mr = pytest.importorskip("py_mini_racer")
    ctx = mr.MiniRacer()
    ctx.eval(_JS_HARNESS)
    if extra_js:
        ctx.eval(extra_js)
    ctx.eval("__setFixture('/data/xfv_scoreboard_eval.json', %s)" % json.dumps(fixture))
    ctx.eval(DIAMOND_JS.read_text(encoding="utf-8"))
    return json.loads(ctx.eval("JSON.stringify(__els())"))


def _scoreboard(resolvable: bool, generated_at: str | None = None) -> dict:
    return {
        "generated_at": generated_at or date.today().isoformat(),
        "head_to_head": {
            "protocol": "forward-chained scoring on identical rows",
            "verdict_vs_consensus": {
                "n": 3210, "delta": 0.0297, "mde95": 0.0352,
                "mde95_estimator": "E_refit", "resolvable": resolvable,
            },
            "vs": {"prospx_consensus": {
                "label": "MLB Pipeline",
                "spearman": {"efv": 0.394, "consensus": 0.396, "n": 3210, "win": False},
                "auc_contributor": {"efv": 0.71, "consensus": 0.70, "n": 3210, "win": True},
            }},
            "by_archetype_vs_consensus": [
                {"label": "Hit-first", "n": 400,
                 "spearman": {"efv": 0.41, "consensus": 0.39, "win": True}},
                {"label": "Arms", "n": 250,
                 "spearman": {"efv": 0.30, "consensus": 0.33, "win": False}},
            ],
        },
    }


def test_receipts_lead_with_the_tie_when_the_artifact_says_unresolvable():
    """resolvable:false is the shipped state of the artifact, so this is the
    render every reader sees: no win paint anywhere, and the card's lead
    sentence IS the verdict."""
    htm = _run_diamond_js(_scoreboard(False))["diamond-receipts"]
    assert "dm-ours" not in htm, "win colour painted on an unresolvable verdict"
    assert "dm-win" not in htm, "per-row archetype win paint is back"
    assert ("statistically indistinguishable on both ordering and discrimination"
            in htm), "the tie lead sentence is gone"
    assert "same players out of sample" in htm
    assert "tie whatever its sign" in htm
    assert "No per-group winner is called" in htm
    assert "point estimates on small groups" in htm


def test_receipts_win_paint_unlocks_only_when_the_artifact_resolves_it():
    htm = _run_diamond_js(_scoreboard(True))["diamond-receipts"]
    assert "dm-ours" in htm, "a resolvable win no longer unlocks the colour"
    assert "dm-win" not in htm, "archetype rows call winners; they carry no floor"
    assert "real lead" in htm
    assert "statistically indistinguishable" not in htm, (
        "the tie lead renders over a resolvable win")


def test_receipts_print_the_scoring_date_and_flag_a_stale_artifact():
    fresh = _run_diamond_js(_scoreboard(False))["diamond-receipts"]
    assert f"Scored as of {date.today().isoformat()}" in fresh
    assert "three weeks old" not in fresh, "a fresh artifact is flagged stale"
    stale = _run_diamond_js(_scoreboard(False, "2026-01-01"))["diamond-receipts"]
    assert "Scored as of 2026-01-01" in stale
    assert "three weeks old" in stale, "a stale scoreboard renders with no warning"


def test_diamond_js_comment_block_lost_its_stale_numerics():
    """The E_refit vs E_cond comment used to quote the floors themselves,
    which rotted the moment the artifact moved. The explanation stays; the
    numbers live in the artifacts it points at."""
    src = DIAMOND_JS.read_text(encoding="utf-8")
    assert "E_refit" in src and "E_cond" in src
    assert "xfv_power_eval.json" in src
    for stale in ("0.03318", "0.0345", "0.0322", "54.1", "50.4", "64.2",
                  "0.128", "0.0123", "0.541", "0.735"):
        assert stale not in src, f"stale floor value back in a comment: {stale}"


def test_diamond_js_no_longer_emits_the_dead_diamond_card_class():
    """class="card diamond-card" had zero CSS rules on any theme; the class
    was dead weight in every card the client painted."""
    src = DIAMOND_JS.read_text(encoding="utf-8")
    assert 'class="card diamond-card"' not in src


# ---- the call to action tells the truth ------------------------------------

def test_static_cta_claims_no_control_the_build_does_not_render():
    out = build_site.build_diamond()
    assert "sign-in control" not in out, (
        "the static CTA references a control that does not render")
    assert "There is no signup" in out
    assert "founding status will be honored" in out


def test_cta_card_is_untouched_when_the_account_layer_is_absent():
    """renderCTA must leave the server-rendered truth alone unless
    window.EephusAccount exists AND EephusAccount.enabled() is true."""
    els = _run_diamond_js(_scoreboard(False))
    assert els.get("diamond-cta", "") == "", (
        "diamond.js painted the CTA with no account layer configured")


def test_cta_card_is_replaced_when_the_account_layer_is_enabled():
    """The gate has to open too, or the guard is just a deleted feature."""
    els = _run_diamond_js(_scoreboard(False), extra_js="""
        window.EephusAccount = {
          enabled: function () { return true; },
          ready: function () { return new SyncP(undefined); },
          isSignedIn: function () { return false; }
        };
    """)
    cta = els.get("diamond-cta", "")
    assert "Create a free account" in cta
    assert "nothing to buy yet" in cta.lower()


# ---- the member list, the ledger, the links --------------------------------

def test_member_gets_list_is_fantasy_and_betting_only():
    """Owner de-list 2026-08-16: /prospx/ is a free page (the one dishonest
    card) and the Card Market waits on a licensed price source. Asserted on
    card headings, not bare hrefs: the shared nav links /prospx/ on every
    page of the site."""
    out = build_site.build_diamond()
    assert '<h3><a href="/fantasy/">Fantasy</a></h3>' in out
    assert '<h3><a href="/betting/">Sports Betting</a></h3>' in out
    assert '<h3><a href="/prospx/">' not in out
    assert '<h3><a href="/cards/">' not in out
    assert "two modules" in out, "the section-sub count no longer follows the list"
    assert "Removed on 2026-09-05" in out and "licensed price source" in out, (
        "the honest Card Market line is gone")


def test_diamond_ledger_card_matches_the_registry():
    """The report card is the product: /diamond/ renders the same verdict
    split the homepage counts, off model_registry.load(), at build time."""
    import model_registry
    tally: dict = {}
    for m in model_registry.load().get("models") or []:
        tally[m.get("verdict")] = tally.get(m.get("verdict"), 0) + 1
    out = build_site.build_diamond()
    assert f"{sum(tally.values())} models" in out
    for k in ("validated", "provisional", "unvalidated", "deprecated"):
        assert f"{tally.get(k, 0)} {k}" in out, f"ledger count drifted for {k}"
    assert 'href="/models/"' in out
    assert "on purpose" in out, "the deprecations-shown-on-purpose sentence is gone"


def test_footer_carries_the_diamond_link():
    assert '<a href="/diamond/">Diamond</a>' in build_site._footer()


def test_homepage_strip_carries_the_static_diamond_card():
    strip = build_site._cross_module_strip()
    assert "◆ Diamond" in strip
    assert 'href="/diamond/"' in strip
    assert "free during the founding preview" in strip
    assert 'href="/fantasy/"' in strip and 'href="/betting/"' in strip


def test_diamond_module_mastheads_carry_the_part_of_line():
    """One server-rendered line under the fantasy and betting mastheads (the
    cards masthead went with the module on 2026-09-05); the free-preview
    clause is gating-aware and ships because the pinned flag is off."""
    for fn in ("build_fantasy", "build_betting"):
        out = getattr(build_site, fn)()
        assert PARTOF_LINE in out, f"{fn} lost the Part of Diamond line"
        assert "Free during the founding preview." in out, fn
