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
    ("cards", "Card Market", "/cards/"),
    ("diamond", "Diamond Pass", "/diamond/"),
]
# The page DIRS are still six, and that is the point: /dynasty/, /redraft/ and
# /dfs/ were public addresses for two days, so they still build and still ship
# as hash-preserving redirect stubs.
DIAMOND_DIRS = ["betting", "cards", "dfs", "diamond", "dynasty", "fantasy", "redraft"]
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
    for key in ("fantasy", "betting", "cards"):
        assert "Diamond preview" in MODULE_STAGE[key][0]


@pytest.mark.parametrize("rel,fn", [
    ("fantasy/index.html", "build_fantasy"),
    ("dynasty/index.html", "build_dynasty"),
    ("redraft/index.html", "build_redraft"),
    ("dfs/index.html", "build_dfs"),
    ("betting/index.html", "build_betting"),
    ("cards/index.html", "build_cards"),
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
    """Both tags are deferred, so order in the document IS execution order. A
    module app that ran before the flag existed would read undefined."""
    import inspect
    for fn_name in ("build_fantasy", "build_betting", "build_cards", "build_diamond"):
        src = inspect.getsource(getattr(build_site, fn_name))
        assert "DIAMOND_CONFIG_SCRIPT" in src, f"{fn_name} does not load diamond-config.js"
        assert "diamond-config.js" in build_site.DIAMOND_CONFIG_SCRIPT


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
