# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""
build_site.py - static-site generator for the editorial pages of eephus.io.

Reads `content/` and writes the static pages that share the PROSPX theme
(`assets/site.css`) + the site-wide nav:

    /              -> index.html              (Home: brand hero + module cards)
    /articles/     -> articles/index.html     (grid of article cards, newest first)
    /articles/<s>/ -> articles/<slug>/index.html  (one page per content/articles/<slug>.md)
    /team/         -> team/index.html          (from content/team.json)

PROSPX lives at /prospx/index.html and is NOT touched by this script (its nav +
asset paths were wired once, by hand). `run_monthly.py` (the data pipeline that
writes data/*.json) is also independent of this build.

Add an article = drop a markdown file in content/articles/ with frontmatter
(title/author/handle/date/summary) and rerun `python build_site.py`. Embed a
YouTube clip on its own line with `@youtube: <url-or-id>`.

Usage:  python build_site.py
"""
from __future__ import annotations

import functools
import hashlib
import html
import json
import math
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import markdown as md

# Two build-time companions, both stdlib-only at import so they cost the same
# as a constant here: the public artifact catalog rendered on /sources/#api, and
# the eFV movement alerts feed written at the end of main().
import data_catalog
import efv_alerts
# The registry loader/validator behind /models/. Imported for load(), STALE_DAYS
# and the artifact-date reader ONLY; refresh_stamps() is the sole writer in that
# module and it runs under run_monthly, never here.
import model_registry
from report_excerpt import EXCERPT_MAX_CHARS as REPORT_EXCERPT_CHARS

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
SITE_ORIGIN = "https://eephus.io"   # absolute base for canonical + social-card (og/twitter) URLs

# Cache-bust assets/site.css by content hash so browsers/CDNs always pull the
# latest stylesheet after a rebuild - otherwise a stale cached CSS shows the old
# layout (frozen ticker, unstyled callout, etc.) even though the files updated.
def _asset_ver(rel: str) -> str:
    try:
        return hashlib.md5((ROOT / rel).read_bytes()).hexdigest()[:8]
    except OSError:
        return "1"
_CSS_VER = _asset_ver("assets/site.css")
_NAV_VER = _asset_ver("assets/eephus-nav.js")
# The value ruler (assets/eephus-tiers.js): the ONE file that knows a colour cut.
# Its tag rides the shared head block immediately after the nav script rather than
# ACCOUNT_SCRIPTS, which is injected after {body}. Deferred scripts run in document
# order, so the head position makes "the ruler is defined before a board renders"
# deterministic rather than lucky.
_TIERS_VER = _asset_ver("assets/eephus-tiers.js")
# The pixel state component (final-pass plan 5.7, PX-11): rides the head block
# beside the ruler for the same reason, since a module paints its loading line
# the moment its own deferred script runs, before ACCOUNT_SCRIPTS.
_STATE_VER = _asset_ver("assets/eephus-state.js")
_ACCT_VER = _asset_ver("assets/eephus-account.js")
# The pixel icon sprite (final-pass plan 5.7, PX-02), referenced by external
# <use href="/assets/eephus-icons.svg?v=<hash>#i-key"> from _ico() below.
_ICONS_VER = _asset_ver("assets/eephus-icons.svg")
_UI_VER = _asset_ver("assets/eephus-ui.js")
_ACCT_CSS_VER = _asset_ver("assets/eephus-account.css")
_BG_VER = _asset_ver("assets/eephus-bg.js")
_FA_VER = _asset_ver("assets/fa.js")
# $/WAR-by-winter detail view, reached from the FA rail sparkline (#view=dpw).
# Self-contained: it mounts its own section and hides #fa-rows while active,
# so it never shares state with fa.js.
_FA_DPW_VER = _asset_ver("assets/fa_dpw.js")
_GL_VER = _asset_ver("assets/eephus-gl.js")
_GLAPP_VER = _asset_ver("assets/glossary.js")
# CONTENT version of the glossary DATA (not the runtime that reads it).
# assets/eephus-gl.js used to fetch the ~366KB data/glossary.json with
# cache:"no-cache" on EVERY page view - a forced revalidation on the single
# heaviest recurring transfer on the site. The runtime now fetches
# /data/glossary.json?v=<this hash> under NORMAL caching, so the payload is
# served from the browser cache until the file actually changes. The hash rides
# a tiny inline global (below) rather than a query param on the script tag:
# restamp_hand_authored_pages() rewrites `/assets/x.js?v=<hash>` wholesale on
# the hand-authored pages, so any extra param on that URL would be stripped.
_GL_DATA_VER = _asset_ver("data/glossary.json")
_PROJ_VER = _asset_ver("assets/projections.js")
_MLBSTATS_VER = _asset_ver("assets/mlbstats.js")
_PAL_VER = _asset_ver("assets/pal.js")
_ARB_VER = _asset_ver("assets/arbitration.js")
_TM_VER = _asset_ver("assets/trademachine.js")
_TM_CSS_VER = _asset_ver("assets/trademachine.css")
_HUB_VER = _asset_ver("assets/eephus-hub.js")
# The team picker (assets/eephus-teampick.js): upgrades every select[data-team-picker]
# to a logo listbox and keeps the native select as the value. It reads the club
# table from eephus-hub.js, so its tag always follows the hub's in document order.
_TEAMPICK_VER = _asset_ver("assets/eephus-teampick.js")
_GFX_VER = _asset_ver("assets/eephus-gfx.js")
# assets/fantasy.js is FROZEN and no page loads it. It is the pre-split parity
# reference that test_fantasy_split drives assets/redraft.js against in a JS
# engine, so it ships with the assets dir and keeps a stamp, and the stamp is
# what makes a silent edit to it visible. Do not resurrect it as a client.
_FANTASY_VER = _asset_ver("assets/fantasy.js")
_EXPORT_VER = _asset_ver("assets/eephus-export.js")
# Per-board CSV DOWNLOAD. Separate from eephus-export.js on purpose: that module
# owns the copy-to-clipboard chip (a share affordance), this one writes a file
# to disk, which is the thing /diamond/ advertised as "data exports". It borrows
# EephusExport.scrape + formats.csv rather than carrying a second serializer, and
# it stays inert on any page with no [data-csv-export] host.
_CSV_VER = _asset_ver("assets/eephus-csv.js")
_PARKS_VER = _asset_ver("assets/parks.js")
_PARKS_CSS_VER = _asset_ver("assets/parks.css")
_HOF_VER = _asset_ver("assets/hof.js")
_MGMT_VER = _asset_ver("assets/management.js")
_MGMT_CSS_VER = _asset_ver("assets/management.css")
# /ledger/ - Club Ledger (2026-09-23, D1).
_LEDGER_VER = _asset_ver("assets/ledger.js")
_LEDGER_CSS_VER = _asset_ver("assets/ledger.css")
# /franchise/ - Franchise Overview (2026-09-23, D3): the org-level grade tree.
_FRANCHISE_VER = _asset_ver("assets/franchise.js")
_FRANCHISE_CSS_VER = _asset_ver("assets/franchise.css")
_HOF_CSS_VER = _asset_ver("assets/hof.css")
# /models/ - the model accountability hub. Client is filter-only: every row,
# count and date on that page is server-rendered here at build time, so the
# surface still tells the truth with JavaScript off.
_ACCT_HUB_VER = _asset_ver("assets/accountability.js")
# Diamond section (2026-08-05): one config script, five module apps, and the
# Diamond Pass client. The five module apps are owned by their own lanes. A
# file that is not on disk yet hashes to "1" here rather than raising, so the
# scaffold builds and each page paints its own empty state until its app lands.
_DIAMOND_CFG_VER = _asset_ver("assets/diamond-config.js")
# The three fantasy sub-clients. They are NOT script tags on the shell any more
# (2026-08-07 merge): the coordinator injects one of them on first activation,
# so these stamps ride data-src attributes on the module bar instead. The stamp
# still has to be computed here, because the injected URL needs the same
# content hash every other asset URL carries or a client update never reaches a
# browser that cached the old one.
_DYNASTY_VER = _asset_ver("assets/dynasty.js")
_REDRAFT_VER = _asset_ver("assets/redraft.js")
_DFS_VER = _asset_ver("assets/dfs.js")
# The /fantasy/ coordinator: module bar, the "#m=" hash namespace, lazy boot,
# and one memoized load of the 576KB corpus for the two clients that read it.
_FANTASY_HUB_VER = _asset_ver("assets/fantasy-hub.js")
# The fantasy player card: one overlay shared by the fantasy board clients. It
# holds no data of its own - the host client hands it the payload already in the
# browser - so it loads BEFORE its host and simply publishes the API the host
# attaches to. There is no page-per-player build behind it.
_FANTASY_CARD_VER = _asset_ver("assets/fantasy-card.js")
_BETTING_VER = _asset_ver("assets/betting.js")
_DIAMOND_VER = _asset_ver("assets/diamond.js")
# The gate switch lives in ONE file (assets/diamond-config.js:
# window.EEPHUS_DIAMOND = {gating:false, ...}) and the ONE reader of it is
# assets/eephus-diamond.js (window.EephusDiamond, 2026-08-16), which folds the
# account layer's answer into the flag so a paying member is never capped by a
# client that guessed at membership. Every Diamond page loads config then
# helper BEFORE its module app. All three are deferred, and deferred scripts
# run in document order, so the config wins the race by position rather than
# by luck and the helper reads a flag that already exists.
_DIAMOND_HELPER_VER = _asset_ver("assets/eephus-diamond.js")
DIAMOND_CONFIG_SCRIPT = (
    f'<script src="/assets/diamond-config.js?v={_DIAMOND_CFG_VER}" defer></script>'
    f'<script src="/assets/eephus-diamond.js?v={_DIAMOND_HELPER_VER}" defer></script>'
)


# CONTENT stamps for the Diamond section's BUILD-TIME-ONLY data payloads, the
# same trade _GL_DATA_VER made for the glossary corpus. These payloads are
# written by the pipeline and only change when the site rebuilds, yet every
# client fetched them with cache:"no-cache", a forced revalidation on multi
# hundred KB files on every page view. Each consuming page now carries a tiny
# inline global, window.EEPHUS_DATA_VERS = {"<file>": "<8-hex>"}, and the
# clients append ?v=<stamp> and fetch under DEFAULT caching: nginx serves
# /data/ with max-age=604800, so the browser keeps the payload until the
# content hash moves and the new file lands under a URL no cache has seen.
# Same freshness, one transfer per version.
def _data_vers_script(names: tuple[str, ...]) -> str:
    """The inline EEPHUS_DATA_VERS block for one page's payload list.

    THE DO-NOT-STAMP RULE, which this helper enforces rather than documents:
    data/betting.json, data/betting_record.json and the settlement/CLV
    sidecars are mutated INTRA-DAY by the close job with no page rebuild in
    between, so a build-time stamp on any of them would pin a week-stale copy
    under that same /data/ max-age. They keep the no-cache revalidation, and
    a betting name in a stamp list is refused loudly here instead of shipping
    a stale betting record.

    A missing file is simply omitted (no stamp, never a crash): the client
    sees no entry for it and falls back to the exact no-cache read it always
    had. An empty map emits no script tag at all."""
    stamps: dict[str, str] = {}
    for name in names:
        if name.startswith("betting"):
            raise ValueError(
                f"{name} is a close-job payload and must never be content-stamped: "
                "it mutates intra-day without a rebuild, and a build-time stamp "
                "would serve a week-stale copy under the /data/ max-age.")
        try:
            stamps[name] = hashlib.md5((ROOT / "data" / name).read_bytes()).hexdigest()[:8]
        except OSError:
            continue
    if not stamps:
        return ""
    return f"<script>window.EEPHUS_DATA_VERS={json.dumps(stamps, sort_keys=True)};</script>"


# The per-page payload lists. Per page rather than one site-wide map so each
# page's consumption set sits next to its builder and a betting name showing
# up in one is a visible one-line diff. hitter_history.json and
# starter_history.json are the fantasy card's season-history boards: monthly
# build-time artifacts like the rest, and the two heaviest lazy fetches in
# the module, which is exactly the transfer the stamp exists to save.
FANTASY_DATA_STAMPS = ("fantasy.json", "dfs.json", "fantasy_rank.json",
                       "hitter_history.json", "starter_history.json")
DIAMOND_DATA_STAMPS = ("xfv_scoreboard_eval.json",)

# eephus.io account layer (Parts 1-7), injected before </body> on every editorial
# page. OPTIONAL by design: assets/eephus-config.js is git-ignored and absent on
# the public tree, so its <script> 404s harmlessly and window.EEPHUS_SUPABASE stays
# undefined - eephus-account.js then runs fully inert (no Supabase SDK fetch, no
# behavior change) and the page renders exactly as today. When config IS present
# the module self-injects the SDK and lights up the account UI.
ACCOUNT_SCRIPTS = (
    f'<script src="/assets/eephus-config.js" defer></script>\n'
    f'<script src="/assets/eephus-account.js?v={_ACCT_VER}" defer></script>\n'
    f'<script src="/assets/eephus-ui.js?v={_UI_VER}" defer></script>\n'
    # Dark-theme phosphor-starfield background (shared with PROSPX). Rides the
    # per-page script block; inert (mounts nothing) under the light theme.
    f'<script src="/assets/eephus-bg.js?v={_BG_VER}" defer></script>\n'
    # Shared glossary runtime: data loader + ⌘K palette + term tooltips.
    # The inline global carries the DATA hash so the runtime can request a
    # content-versioned /data/glossary.json and let the browser cache it
    # normally. Inline (non-defer) => it always runs before the deferred module
    # below. Absent (the hand-authored pages carry their own <script> tags and
    # never see this block) the runtime falls back to the unversioned URL under
    # default caching, which is still cheaper than the old forced revalidation.
    f'<script>window.EEPHUS_GL_DATA_VER="{_GL_DATA_VER}";</script>\n'
    f'<script src="/assets/eephus-gl.js?v={_GL_VER}" defer></script>\n'
    # Universal copy/export: a quiet chip on every table + chart (text + image).
    f'<script src="/assets/eephus-export.js?v={_EXPORT_VER}" defer></script>\n'
    # Per-board CSV download. Loaded site-wide but OPT-IN per board: it only
    # renders a control inside an element carrying data-csv-export, so a page
    # that has not opted in pays one cached script and gains nothing visible.
    # Loaded AFTER eephus-export.js so the shared scrape/serializer it prefers
    # is already defined on first scan (both are deferred, and deferred scripts
    # run in document order, so this is ordering by position not by luck).
    f'<script src="/assets/eephus-csv.js?v={_CSV_VER}" defer></script>'
)
# Account/forum stylesheet - linked in <head> after site.css on every editorial
# page (scoped under .eph-*; the circular avatar is the one sanctioned curve).
ACCOUNT_CSS_LINK = f'<link rel="stylesheet" href="/assets/eephus-account.css?v={_ACCT_CSS_VER}">'


def _csv_optin(name: str) -> str:
    """The per-board CSV download opt-in: one attribute on the mount point.

    The client helper watches for elements carrying `data-csv-export` and, once
    the board has painted a table with rows inside one, adds a Download CSV
    control that serializes exactly what is on screen (current sort, current
    filter, the displayed number formats). `name` becomes the filename stem.

    Why an attribute on the SERVER rather than a call in each board's JS: the
    module apps are owned by their own lanes and each would have needed the same
    edit, which is how two boards end up with two slightly different exports.
    One attribute on the shell means no module app changed, and a board that has
    not opted in renders exactly as before."""
    return f' data-csv-export="{html.escape(name, quote=True)}"'

# Unified prospect-photo resolution - mirrors PROSPX's headshotURL(): consult the
# resolved context map (data/photo_ctx.json, built by headshots.py) and use the
# REAL MiLB/MLB photo for resolved ids ('67'/'milb').
# Single source of truth so the homepage shows the same coverage as PROSPX,
# instead of the old hardcoded '67' that silhouetted every milb-only prospect.
#
# FACE CROP (2026-08-05). img.mlbstatic.com is Cloudinary and honours
# `c_fill,g_face`: c_fill returns EXACTLY the requested box, g_face centres that
# crop on the detected face. Source headshots are 480x720 (2:3), so every
# consumer that wanted some other box was cropping blind - here through
# `background: center top/cover`, which is a guess about where the face sits.
# Asking the CDN for the real box removes the guess. Verified live on both the
# '67' and 'milb' contexts: exact pixel dimensions back, ACAO:* intact. Same
# transform string as PROSPX's _GFX_FACE_CROP and projections.js's FACE_CROP;
# c_thumb was rejected there for zooming too tight and is not reconsidered here.
_FACE_CROP = "c_fill,g_face"

def _load_photo_ctx() -> dict:
    try:
        return (json.loads((ROOT / "data" / "photo_ctx.json").read_text(encoding="utf-8")).get("ctx")) or {}
    except (OSError, ValueError, AttributeError):
        return {}
_PHOTO_CTX = _load_photo_ctx()

def _headshot_url(mlbam, box_w: int = 84, box_h: int | None = None) -> str | None:
    """Face-cropped headshot URL for a `box_w` x `box_h` CSS-pixel well, or None
    when there is no usable photo (no MLBAM id, or the resolver validated 'none')
    and the caller should render its own empty/silhouette state.

    The `d_people:generic` overlay is DELIBERATELY not used: it answers HTTP 200
    with a silhouette, so a caller can never tell a real photo from a miss and no
    onerror/degrade path downstream can fire. Without it a genuine miss 404s and
    the caller's own empty state shows through.
    """
    if not mlbam:
        return None
    ctx = _PHOTO_CTX.get(str(mlbam))
    if ctx == "none":                       # resolver checked: no photo on file
        return None
    # Unresolved ids (added since the last monthly photo_ctx backfill) ask the
    # real '67' set with no overlay, so a miss 404s instead of silhouetting.
    seg = ctx if ctx in ("67", "milb") else "67"
    bw = max(20, int(box_w))
    bh = max(20, int(box_h if box_h is not None else box_w))
    # 2x for retina, clamped PROPORTIONALLY so a large well cannot ask the CDN
    # for an absurd render and cannot distort the aspect on the way (clamping
    # one axis alone would).
    k = max(1.0, min(2.0, 1400 / max(bw, bh)))
    w, h = round(bw * k), round(bh * k)
    return (f"https://img.mlbstatic.com/mlb-photos/image/upload/"
            f"{_FACE_CROP},w_{w},h_{h},q_auto:best/v1/people/{mlbam}/headshot/{seg}/current")

# Owner-set order (2026-06-11): Home, PROSPX, CollegeSavant (directly under
# PROSPX), FA, Projections, Articles, Forums, Glossary, Team.
# 2026-06-12: the standalone Teams module merged into MLB Projections
# (Team Outlook view carries the org-dashboard columns); /teams/ now
# redirects there and the nav entry is gone.
# A nav entry is either a LEAF (key, label, href) or a GROUP dict
#   {"group": <label>, "key": <group key>, "children": [(key, label, href), ...]}
# rendered as a click dropdown in the top bar (_nav) and a nested sub-block in
# the homepage sidebar. The MLB-facing modules (Free Agency, Projections, MLB
# Stats) live under one "MLB Modules" group; PROSPX/CollegeSavant stay top-level
# (MiLB + amateur). This is the SINGLE source - _nav(), the sidebar, and the
# hand-maintained static nav copies (prospx + the two CollegeSavant pages) all
# mirror it; test_collegesavant_nav_in_sync guards the static copies.
NAV_ITEMS = [
    ("home",     "Home",             "/"),
    ("prospx",   "PROSPX",           "/prospx/"),
    ("collegesavant", "CollegeSavant", "/collegesavant/"),
    {"group": "MLB Modules", "key": "mlb", "children": [
        # Franchise (2026-09-23, D3): the hub before the modules, FIRST in the
        # group by owner decision. The hand-kept static copies carry the same
        # entry in the same slot (test_collegesavant_nav_in_sync).
        ("franchise",   "Franchise",   "/franchise/"),
        ("fa",          "Free Agency", "/fa/"),
        ("projections", "Projections", "/projections/"),
        ("mlbstats",    "MLB Stats",   "/mlbstats/"),
        ("pal",         "Alchemy Lab", "/pal/"),
        ("trademachine", "Trade Machine", "/trademachine/"),
        ("arbitration", "Arbitration", "/arbitration/"),
        # Club Ledger (2026-09-23, D1): the finances module, directly after
        # Arbitration by owner decision. The hand-kept static copies carry the
        # same entry in the same slot (test_collegesavant_nav_in_sync).
        ("ledger",      "Club Ledger", "/ledger/"),
        # SHIPPED 2026-09-06 AND UNREACHABLE UNTIL NOW. Both pages were built,
        # both were registered in the sitemap, and both already pass their own
        # key to page() as the nav `active` marker, so they were authored
        # expecting an entry here. There was none, and NAV_ITEMS is the single
        # source for the top bar, the sidebar and the hand-kept static copies.
        # A reader could reach either module only by typing its URL.
        ("management", "In-Game Management", "/management/"),
        ("hof",        "Hall of Fame",       "/hof/"),
    ]},
    # 2026-08-05: the Diamond section. 2026-08-07: Dynasty / Redraft / DFS
    # collapsed back into ONE "Fantasy" leaf, because three of the group's six
    # entries were three tabs of one module and the dropdown read as six
    # products. They are sub-modules of /fantasy/ now and /dynasty/, /redraft/
    # and /dfs/ are hash-preserving redirect stubs, so every bookmark written
    # against the split still lands on the board it named. Every page in this
    # group ships PUBLIC with "Diamond preview" labeling. The group key is
    # deliberately NOT "diamond" so it cannot be confused with the leaf of that
    # name (the leaf key is what _nav() matches `active` against).
    {"group": "Diamond", "key": "diamondgrp", "children": [
        ("fantasy",  "Fantasy",        "/fantasy/"),
        ("betting",  "Sports Betting", "/betting/"),
        ("diamond",  "Diamond Pass",   "/diamond/"),
    ]},
    ("articles", "Articles",         "/articles/"),
    ("forums",   "Forums",           "/forums/"),
    ("glossary", "Glossary",         "/glossary/"),
    ("team",     "Developers",        "/team/"),
]

def _nav_is_group(item) -> bool:
    """A NAV_ITEMS entry is a group when it's a dict (vs a (key,label,href) leaf)."""
    return isinstance(item, dict)

def nav_leaves() -> list[tuple]:
    """Flatten NAV_ITEMS (groups + leaves) to (key, label, href) in nav order -
    the canonical link set the static nav copies must mirror."""
    out: list[tuple] = []
    for item in NAV_ITEMS:
        if _nav_is_group(item):
            out.extend(item["children"])
        else:
            out.append(item)
    return out

# PROSPX sub-sections - deep links into the app (section = `tab` query param in
# the hash; `active` is the default so it has no param).
PROSPX_SUBNAV = [
    ("Prospects",     "/prospx/"),
    ("Farm Systems",  "/prospx/#tab=farm"),
    ("Leaderboards",  "/prospx/#tab=leaderboards"),
    ("Transactions",  "/prospx/#tab=traded"),
    ("Injured List",  "/prospx/#tab=injured"),
    ("Spotlights",    "/prospx/#tab=spotlights"),
    ("Debuted",       "/prospx/#tab=debuts"),
    ("MLB Draft",     "/prospx/#tab=draft"),
    ("International",  "/prospx/#tab=ifa"),
    ("Overseas",      "/prospx/#tab=overseas"),
    ("Time Machine",  "/prospx/#tab=timemachine"),
    ("Scatterplots",  "/prospx/#tab=charts"),
    # Glossary intentionally omitted - it's a top-level module of its own
    # ("Glossary & Methodology" in the Modules nav), so listing it here too
    # was redundant.
]

# The pixel icon set (final-pass plan 5.7, PX-02). tools/pixel_icons.py draws
# every icon once into assets/eephus-icons.svg (symbol id "i-" + icon key) and
# writes the same keys to assets/eephus-icons.json, which is read here so a
# key with no drawing fails the build instead of shipping an empty box.
# ICON_FOR maps each caller vocabulary to its symbol: a NAV_ITEMS key, a footer
# route, a PROSPX section-tab data-section, a wire event type. The vocabularies
# are merged into one map, and a key two of them use for different symbols
# refuses to import. A symbol key ("px-farm", "ev-up") passes through _ico()
# unmapped.
ICON_SIZES = (12, 16, 24, 32)


def _icon_keys() -> frozenset:
    try:
        return frozenset(json.loads((ROOT / "assets" / "eephus-icons.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return frozenset()


ICON_KEYS = _icon_keys()
_PX_SECTION_ICON = {
    "active": "px-prospects", "spotlights": "px-spotlights", "farm": "px-farm",
    "traded": "px-transactions", "injured": "px-il", "leaderboards": "px-leaderboards",
    "debuts": "px-debuted", "draft": "px-draft", "ifa": "px-intl",
    "overseas": "px-overseas", "timemachine": "px-timemachine", "charts": "px-scatter",
}
_WIRE_ICON = {t: f"ev-{t}" for t in ("up", "down", "promo", "demo", "il", "debut", "trade", "signing")}


def _merge_icon_maps(*maps: dict) -> dict:
    out: dict = {}
    for m in maps:
        for k, v in m.items():
            if out.get(k, v) != v:
                raise ValueError(f"icon key {k!r} maps to both i-{out[k]} and i-{v}")
            out[k] = v
    return out


ICON_FOR = _merge_icon_maps(
    {k: k for k, _label, _href in nav_leaves()},
    {k: k for k in ("models", "parks", "news", "history", "watchlist")},
    _PX_SECTION_ICON,
    _WIRE_ICON,
)


def _ico(key: str, size: int) -> str:
    """One pixel icon as an inline <svg class="ico"> over the shared sprite.

    Sizes are 12, 16, 24 or 32 and nothing else (plan 5.7.1 line 2). 12 and 24
    crop to the 12 x 12 core (viewBox "2 2 12 12"); 16 and 32 show the full
    16 x 16 box. Decoration only: aria-hidden, the label beside it carries the
    meaning."""
    if size not in ICON_SIZES:
        raise ValueError(f"icon size {size} is not one of {ICON_SIZES}")
    sym = ICON_FOR.get(key, key)
    if sym not in ICON_KEYS:
        raise ValueError(f"no pixel icon i-{sym} for key {key!r} in assets/eephus-icons.svg")
    href = f"/assets/eephus-icons.svg?v={_ICONS_VER}#i-{sym}"
    if size in (12, 24):
        return (f'<svg class="ico" width="{size}" height="{size}" viewBox="2 2 12 12" '
                f'aria-hidden="true" focusable="false"><use href="{href}" width="16" height="16"/></svg>')
    return (f'<svg class="ico" width="{size}" height="{size}" viewBox="0 0 16 16" '
            f'aria-hidden="true" focusable="false"><use href="{href}"/></svg>')


def _masthead_icon(key: str) -> str:
    """The 32 px module icon at the head of a module masthead h1 (PX-07): the
    16 x 16 drawing at 2x, before the title text; the stage chip after the
    title is unchanged."""
    return _ico(key, 32)


def _wire_glyph(typ: str, glyph: str) -> str:
    """The wire pictogram (PX-17): a known event type draws its 12 px icon,
    which takes the colour of the type's own span (trade in the panel's ink,
    owner answer PX-Q3); an unknown type keeps its text glyph. The GFX blob
    keeps the text glyph for the canvas painter (PX-18)."""
    return _ico(_WIRE_ICON[typ], 12) if typ in _WIRE_ICON else html.escape(glyph or "")


# The pixel state scenes (final-pass plan 5.7, PX-11), byte-equal to the ART
# table in assets/eephus-state.js (test_state_component.py pins the pair). The
# build-time pages (the homepage rail and lead) draw their empty states from
# here; every module draws its own through window.EephusState.
_PX_STATE_ART = {
    "empty": '<svg class="px-art" aria-hidden="true" width="64" height="32" viewBox="0 0 32 16" shape-rendering="crispEdges"><path class="s" d="M10 3h12v1h-12zM6 4h4v1h-4zM22 4h4v1h-4zM4 5h2v1h-2zM26 5h2v1h-2zM3 6h1v2h-1zM28 6h1v2h-1zM4 8h2v1h-2zM26 8h2v1h-2zM6 9h4v1h-4zM22 9h4v1h-4zM10 10h12v1h-12zM4 13h2v1h-2zM4 14h16v1h-16zM4 15h2v1h-2z"/><path class="k" d="M20 13h9v1h-9zM20 14h10v1h-10zM20 15h9v1h-9z"/></svg>',
    "unmeasured": '<svg class="px-art" aria-hidden="true" width="64" height="32" viewBox="0 0 32 16" shape-rendering="crispEdges"><path class="s" d="M2 1h28v1h-28zM2 2h1v9h-1zM29 2h1v9h-1zM2 11h28v1h-28zM8 12h2v3h-2zM22 12h2v3h-2zM0 15h32v1h-32z"/><path class="k" d="M10 6h5v1h-5zM16 6h5v1h-5z"/></svg>',
    "failed": '<svg class="px-art" aria-hidden="true" width="64" height="32" viewBox="0 0 32 16" shape-rendering="crispEdges"><path class="s" d="M2 1h28v1h-28zM2 2h1v9h-1zM29 2h1v9h-1zM2 11h28v1h-28zM8 12h2v3h-2zM22 12h2v3h-2zM0 15h32v1h-32z"/><path class="k" d="M13 3h5v1h-5zM13 4h1v2h-1zM13 6h4v1h-4zM13 7h1v2h-1zM13 9h5v1h-5z"/></svg>',
}


def _px_state(kind: str, msg_html: str, cls: str = "") -> str:
    """One still pixel state box: empty, unmeasured or failed (the loader only
    ever runs client side). msg_html is already escaped; the art is
    aria-hidden and the message carries the meaning."""
    if kind not in _PX_STATE_ART:
        raise ValueError(f"no still pixel state {kind!r}")
    role = ' role="alert"' if kind == "failed" else ""
    return (f'<div class="px-state is-{kind}{" " + cls if cls else ""}"{role}>'
            f'{_PX_STATE_ART[kind]}<div class="px-state-msg">{msg_html}</div></div>')


# The 404 foul ball (PX-13): the wordmark's arc hooks left of the foul pole and
# out of the park while the board reads 404. One shot of 0.75 s, CSS step-end
# (site.css .px-foul); the base style is the final frame, so a screenshot sees
# the finished play. It plays under Reduce Motion too (owner, 2026-10-01).
_PX_404_ART = ('<svg class="px-art px-foul" aria-hidden="true" focusable="false" width="128" height="56" viewBox="0 0 64 28" shape-rendering="crispEdges"><path class="s" d="M30 2h1v1h-1zM29 3h1v1h-1zM31 3h1v1h-1zM30 4h1v1h-1zM36 4h25v1h-25zM29 5h1v1h-1zM31 5h1v1h-1zM36 5h1v13h-1zM60 5h1v13h-1zM30 6h1v1h-1zM29 7h1v1h-1zM31 7h1v1h-1zM30 8h1v1h-1zM29 9h1v1h-1zM31 9h1v1h-1zM36 18h25v1h-25zM42 19h1v1h-1zM54 19h1v1h-1zM0 20h28v1h-28zM29 20h35v1h-35zM0 21h1v5h-1zM8 21h1v5h-1zM16 21h1v5h-1zM24 21h1v5h-1zM32 21h1v5h-1zM40 21h1v5h-1zM48 21h1v5h-1zM56 21h1v5h-1zM0 26h28v1h-28zM29 26h35v1h-35zM0 27h64v1h-64z"/><path class="k" d="M28 1h1v26h-1zM43 8h1v1h-1zM47 8h3v1h-3zM55 8h1v1h-1zM42 9h2v1h-2zM46 9h1v3h-1zM50 9h1v1h-1zM54 9h2v1h-2zM41 10h1v1h-1zM43 10h1v2h-1zM49 10h2v1h-2zM53 10h1v1h-1zM55 10h1v2h-1zM40 11h1v1h-1zM48 11h1v1h-1zM50 11h1v3h-1zM52 11h1v1h-1zM40 12h5v1h-5zM46 12h2v1h-2zM52 12h5v1h-5zM43 13h1v2h-1zM46 13h1v1h-1zM55 13h1v2h-1zM47 14h3v1h-3z"/><rect class="t" x="23" y="16" width="1" height="1" style="animation-duration:0.04s"/><rect class="t" x="22" y="14" width="1" height="1" style="animation-duration:0.07s"/><rect class="t" x="21" y="11" width="1" height="1" style="animation-duration:0.11s"/><rect class="t" x="20" y="9" width="1" height="1" style="animation-duration:0.16s"/><rect class="t" x="19" y="7" width="1" height="1" style="animation-duration:0.21s"/><rect class="t" x="17" y="5" width="1" height="1" style="animation-duration:0.26s"/><rect class="t" x="16" y="3" width="1" height="1" style="animation-duration:0.32s"/><rect class="t" x="14" y="1" width="1" height="1" style="animation-duration:0.38s"/><rect class="t" x="11" y="0" width="1" height="1" style="animation-duration:0.45s"/><rect class="t" x="4" y="0" width="1" height="1" style="animation-duration:0.67s"/><rect class="t" x="1" y="2" width="1" height="1" style="animation-duration:0.72s"/><rect class="b" x="23" y="18" width="2" height="2" style="animation-delay:0.00s;animation-duration:0.07s"/><rect class="b" x="21" y="13" width="2" height="2" style="animation-delay:0.07s;animation-duration:0.07s"/><rect class="b" x="19" y="9" width="2" height="2" style="animation-delay:0.15s;animation-duration:0.07s"/><rect class="b" x="17" y="5" width="2" height="2" style="animation-delay:0.22s;animation-duration:0.07s"/><rect class="b" x="15" y="2" width="2" height="2" style="animation-delay:0.30s;animation-duration:0.07s"/><rect class="b" x="13" y="0" width="2" height="2" style="animation-delay:0.38s;animation-duration:0.07s"/><rect class="b" x="11" y="-1" width="2" height="2" style="animation-delay:0.45s;animation-duration:0.07s"/><rect class="b" x="8" y="-2" width="2" height="2" style="animation-delay:0.53s;animation-duration:0.07s"/><rect class="b" x="5" y="-2" width="2" height="2" style="animation-delay:0.60s;animation-duration:0.07s"/><rect class="b" x="2" y="-1" width="2" height="2" style="animation-delay:0.67s;animation-duration:0.07s"/><rect class="b z" x="-1" y="1" width="2" height="2" style="animation-duration:0.75s"/></svg>')


def _prospx_subnav_section(href: str) -> str:
    """The PROSPX data-section a PROSPX_SUBNAV deep link opens: the hash's
    tab= value, or "active" (the default board) when there is none."""
    m = re.search(r"[#&]tab=([\w-]+)", href)
    return m.group(1) if m else "active"


def _nav_drawer_ico(key: str) -> str:
    """The 12 px icon on a top-level nav leaf, shown ONLY in the phone drawer
    (PX-04). The one-line top bar stays text (plan 5.7.1 line 9, owner answer
    PX-Q2): site.css hides .nav-drawer-ico everywhere except the open drawer at
    640px and below. The three hand-kept static navs carry the same markup."""
    return f'<span class="nav-drawer-ico">{_ico(key, 12)}</span>'

# Site-wide theme: read the shared key PROSPX uses (prospect-tracker.theme) and
# set <html data-theme> synchronously in <head> (no flash); toggle persists to
# the same key so light/dark stays in sync across the whole site incl. PROSPX.
THEME_INIT = (
    '<script>(function(){try{var t=localStorage.getItem("prospect-tracker.theme");'
    'if(!t)t=(window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches)?"dark":"light";'
    'document.documentElement.setAttribute("data-theme",t);}catch(e){}})();'
    'function eephusToggleTheme(){try{var c=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";'
    'document.documentElement.setAttribute("data-theme",c);localStorage.setItem("prospect-tracker.theme",c);}catch(e){}}</script>'
)
THEME_BTN = (
    '<button type="button" class="home-theme-toggle" data-theme-toggle onclick="eephusToggleTheme()" aria-label="Toggle dark mode">'
    f'<span class="lbl-dark">{_ico("theme-dark", 12)}Dark</span>'
    f'<span class="lbl-light">{_ico("theme-light", 12)}Light</span></button>'
)

# Favicons + PWA + theme-color - SVG primary (crisp at any size), ICO + 32px PNG
# fallbacks, apple-touch for home-screen pins, the web manifest (installable
# identity), and theme-color for the mobile browser chrome (navy on light,
# near-black on dark). The artifacts are committed (tools/generate_brand_assets.py
# regenerates them when the brand changes); hand-edited pages (prospx,
# collegesavant) carry the same literal block.
FAVICON_LINKS = (
    '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">\n'
    '<link rel="icon" href="/favicon.ico" sizes="32x32">\n'
    '<link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">\n'
    '<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">\n'
    '<link rel="manifest" href="/assets/site.webmanifest">\n'
    '<meta name="theme-color" content="#0E2B4D" media="(prefers-color-scheme: light)">\n'
    '<meta name="theme-color" content="#0C0C0E" media="(prefers-color-scheme: dark)">'
)

# Default Open Graph / Twitter share image - every page emits social-card tags
# (a shared eephus.io link should never render as a bare URL). Pages with a
# richer card (per-article share-card.png) override it.
DEFAULT_SHARE_IMAGE = f"{SITE_ORIGIN}/assets/share-default.png"

# Contact / feedback channel for the Open Beta - one address, linked from the
# footer of every page. Plain mailto keeps it dependency-free until the
# account layer ships.
FEEDBACK_MAILTO = (
    "mailto:arkndjl@gmail.com?subject=eephus.io%20beta%20feedback"
)

# Google Form embed for the /report/ "Report a bug" page. Owner: paste the
# embeddable form URL here (the .../viewform?embedded=true variant from the
# form's Send > <> embed dialog). Left empty, /report/ shows an on-theme
# placeholder card plus the mailto fallback until the form is wired up.
BUG_FORM_URL = ""

def _footer() -> str:
    """The shared page footer: identity line left, useful links right.
    Every editorial surface and the homepage emit the same block."""
    year = date.today().year
    links = (
        f'<a href="/team/">About</a>'
        f'<a href="/news/">Prospect News</a>'
        # /history/ (Today in Prospect History) is a full generated surface but
        # carried NO nav entry anywhere - its only inbound link was the homepage
        # module's "See all" kicker, so it was unreachable from every other page.
        f'<a href="/history/">This Day</a>'
        f'<a href="/parks/">Park Factors</a>'
        # The model ledger carries no nav row (the nav has three hand-maintained
        # static copies), so the footer is its primary address on every page.
        f'<a href="/models/">Model Accountability</a>'
        f'<a href="/sources/">Data Sources</a>'
        # The artifact catalog (what we publish, on what cadence, how stable)
        # is the second half of /sources/. It gets its own footer link because
        # nobody looking for an API looks under "Data Sources", and a page you
        # cannot find is the same as a page that does not exist.
        f'<a href="/sources/#api">Public Data</a>'
        f'<a href="/glossary/">Glossary</a>'
        # The pass page. It has a nav group, but the editorial surfaces are
        # where a reader decides the site is worth funding, so the footer
        # carries the address on every page too.
        f'<a href="/diamond/">Diamond</a>'
        f'<a href="/report/">Report a bug</a>'
        f'<a href="https://x.com/eephus_io" target="_blank" rel="noopener noreferrer">@eephus_io</a>'
        f'<a href="{html.escape(DISCORD_URL)}" target="_blank" rel="noopener noreferrer">Discord</a>'
    )
    # Footer carries the compact mark (the favicon ball) so the identity closes
    # every page - it reads on both themes (cream face, navy outline). It is the
    # hand-tuned 16 px ball strike (owner answer PX-Q4, PX-23), drawn 1:1 at
    # 16 px with pixelated scaling so no browser resamples it; the old 18 px
    # draw of the vector ball read as an "O".
    mark = ('<img src="/assets/favicon-16.png" alt="" aria-hidden="true" width="16" height="16" '
            'style="width:16px;height:16px;image-rendering:pixelated;vertical-align:-3px;margin-right:7px">')
    return (
        '<footer class="eephus-footer">\n'
        f'  <span>{mark}eephus.io - sabermetrics · {html.escape(EEPHUS_VERSION)}</span>\n'
        f'  <nav class="eephus-footer-links" aria-label="Footer">{links}</nav>\n'
        f'  <span>© {year} eephus.io</span>\n'
        '</footer>'
    )

# --------------------------------------------------------------------------- #
# Brand: one version string + one beta badge, the eephus.io placeholder logo,
# and a shared X/social link. THE SINGLE SOURCE for the version is EEPHUS_VERSION
# here; the prospx/index.html static header mirrors the same literal (its own
# hand-edited file) and points back to this constant in a comment.
# --------------------------------------------------------------------------- #
EEPHUS_VERSION = "β v1.0"
BETA_BADGE = (
    f'<span class="eephus-beta" title="eephus.io is in beta - version 1.0">'
    f'{html.escape(EEPHUS_VERSION)}</span>'
)

# Module lifecycle stage - β = in beta (the Open Beta launch promoted every
# module to beta). Rendered ONLY as a bordered chip on each module's own
# masthead (Open Beta polish: the nav links and the homepage sidebar carry no
# sigils; version is noted where you land, not where you browse). The homepage
# hero keeps the site-wide chip (eephus.io is in beta).
MODULE_STAGE = {
    "prospx": ("β", "PROSPX is in beta"),
    "trademachine": ("β", "Trade Machine is in beta"),
    "fa": ("β", "MLB Free Agency is in beta"),
    "projections": ("β", "MLB Projections is in beta"),
    "mlbstats": ("β", "MLB Stats is in beta"),
    "pal": ("β", "Alchemy Lab is in beta"),
    "arbitration": ("β", "Beta. Arb-1 model gated; arb-2+ is a population multiplier"),
    # Club Ledger (2026-09-23). Slot 0 is the SIGIL the rows above carry, not the
    # word: the shell writes sigil plus word itself, as the legacy shells do.
    "ledger": ("β", "Beta. Descriptive ledger: no payroll forecast, no revenue"),
    # Franchise (2026-09-23). Slot 0 is the sigil, as the rows above.
    "franchise": ("β", "Beta. Franchise Index is a descriptive rank, not a forecast"),
    "forums": ("β", "Forums is in beta"),
    "parks": ("β", "Beta. Display only: no model reads these factors"),
    "management": ("β", "Beta. Realized value only; the gate returned a bounded null for the steal and no family is ranked by skill"),
    "hof": ("β", "Beta. Every unpublished section names its blocker"),
    # Diamond section (2026-08-05). These rows carry the FULL chip text in
    # slot [0]; the rows above carry the sigil, which STAGE_CHIP_TEXT turns
    # into the chip text. Every row renders through _stage_chip(). Nothing is
    # gated: these pages are public and free while the section is built out.
    # One row for the merged module (2026-08-07). Dynasty, Redraft and DFS are
    # sub-modules under one masthead now, so there is one chip, not three.
    "fantasy": ("◆ Diamond preview", "Diamond preview: free and public"),
    "betting": ("◆ Diamond preview", "Diamond preview: free and public"),
    "diamond": ("◆ Diamond preview", "Nothing is for sale yet; the whole site is free"),
}

# Chip text per stage sigil. Census X07-10 (2026-09-25): eleven module shells
# wrote "β beta" by hand beside this helper, so renaming the stage meant editing
# eleven f-strings. Every masthead chip now renders through _stage_chip(), and
# the visible word for a sigil lives here once. A MODULE_STAGE slot 0 that is
# not a key here (the Diamond rows) is already the full chip text.
STAGE_CHIP_TEXT = {"β": "β beta"}


def _stage_chip(key: str) -> str:
    """The lifecycle chip on a module masthead: MODULE_STAGE[key] = (sigil or
    visible text, hover title). Reuses the existing .eephus-beta chip so the
    Diamond modules inherit the same sharp-cornered treatment as the beta chips."""
    label, title = MODULE_STAGE[key]
    label = STAGE_CHIP_TEXT.get(label, label)
    return (f'<span class="eephus-beta" title="{html.escape(title)}">'
            f'{html.escape(label)}</span>')

def _gl(slug: str, label: str) -> str:
    """One glossary term in shell copy: the hover definition comes from
    eephus-gl.js (it delegates on any [data-gl] in the document, so a static
    shell needs no wire() call) and the href opens the canonical entry. Shell
    copy names a concept once and points here instead of explaining it."""
    s = html.escape(slug, quote=True)
    return f'<a class="g-term" href="/glossary/#g={s}" data-gl="{s}">{html.escape(label)}</a>'

# Every betting surface carries this block. It is not decoration: it is the
# legal floor the module ships under (21+, informational only, state-by-state
# legality, no affiliate relationships, problem-gambling helpline). Any new
# betting surface renders it too.
BETTING_DISCLAIMER = (
    '<div class="card betting-disclaimer" role="note">'
    '<h3>21+. Informational and entertainment only.</h3>'
    '<p>eephus.io is not a sportsbook: no wagers, no cut, no affiliate links. Nothing here is betting advice. '
    'Sports betting is not legal in every state, and the rules differ where it is. '
    'Odds are captured when a selection posts and move after. No model wins every bet. '
    'If betting stops being fun, call 1-800-GAMBLER or visit '
    '<a href="https://www.1800gamblerhelp.org/" target="_blank" rel="noopener noreferrer">1800gamblerhelp.org</a>.</p>'
    '</div>'
)

# Dev byline - the same "Created by" signature PROSPX renders above its
# masthead (prospx/index.html .build-banner). FA + Projections carry it too
# (owner ask 2026-06-12); the .build-banner rule lives in assets/site.css.
CREATED_BY_BANNER = (
    '<div class="build-banner" aria-label="Build version">Created by '
    '<span aria-hidden="true">🜎</span> Noah J. Dengler / @ARKNDJL</div>'
)

# Modern X (Twitter) glyph - module-level so social links on every surface share
# one mark. (build_team keeps its own local copy for the per-member chips.)
_X_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 '
          '8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 '
          '17.52h1.833L7.084 4.126H5.117z"/></svg>')

def _x_link(handle: str, cls: str = "") -> str:
    """An on-theme X link: glyph + @handle. Sharp corners, opens in a new tab.
    `cls` appends a modifier (e.g. eph-xlink--beta sizes it to the β chip)."""
    h = handle.lstrip("@")
    return (f'<a class="eph-xlink{" " + cls if cls else ""}" href="https://x.com/{html.escape(h)}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="Follow @{html.escape(h)} on X">'
            f'{_X_SVG}<span class="eph-xlink-handle">@{html.escape(h)}</span></a>')

# Community Discord server - one module-level constant so every surface points
# at the same invite. Inline glyph mirrors the _X_SVG treatment (no external art).
DISCORD_URL = "https://discord.gg/UdC4C34uA"
_DISCORD_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.317 4.369a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037 '
                'c-.211.375-.445.865-.608 1.249a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.036 '
                '19.736 19.736 0 0 0-4.885 1.515.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 '
                '19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 '
                '13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .077-.01 '
                'c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.009c.12.099.246.198.373.292a.077.077 0 0 1-.006.127 '
                '12.3 12.3 0 0 1-1.873.891.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 '
                '19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.055c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028z'
                'M8.02 15.331c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.955-2.42 2.157-2.42 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.419-2.157 2.419z'
                'm7.975 0c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.955-2.42 2.157-2.42 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.419-2.157 2.419z"/></svg>')

def _discord_link(cls: str = "") -> str:
    """An on-theme Discord link: glyph + label. Mirrors _x_link (sharp corners,
    new tab); points at the single DISCORD_URL invite. Glyph is inline SVG."""
    return (f'<a class="eph-xlink{" " + cls if cls else ""}" href="{html.escape(DISCORD_URL)}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="Join the eephus.io Discord">'
            f'{_DISCORD_SVG}<span class="eph-xlink-handle">Discord</span></a>')

# eephus.io merged brand mark - the "signature pitch" arc is now PART of the
# lettering: the lob launches off the leading "e", crests with the ball at
# apex, and lands on the "o". Everything is em-scaled inside the nameplate,
# so the same mark renders at masthead (clamp 2.4-4rem) and sidebar (20px)
# sizes without separate art. Arc carries the cardinal→gold→green→navy
# masthead gradient (vector-effect keeps the stroke crisp under the
# stretch-to-width scaling); the ball is its own fixed-aspect SVG so it can
# never squash, punches through via .eephus-logo-ball (theme-aware bg fill),
# and the seam rides currentColor.
def eephus_merged_wordmark(uid: str, tag: str = "h1") -> str:
    grad = f"eephus-arc-{uid}" # per-instance gradient id - two marks per page
    arc = (
        f'<svg class="ew-arc" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">'
        f'<defs><linearGradient id="{grad}" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#B91C1C"/><stop offset="38%" stop-color="#C9A227"/>'
        '<stop offset="68%" stop-color="#1F7A3A"/><stop offset="100%" stop-color="#0E2B4D"/>'
        '</linearGradient></defs>'
        f'<path d="M 3 30 Q 50 -24 97 30" pathLength="100" fill="none" stroke="url(#{grad})" '
        'stroke-width="2.4" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>'
        f'<svg class="ew-ball" viewBox="0 0 24 24" aria-hidden="true">'
        f'<circle class="eephus-logo-ball" cx="12" cy="12" r="8.5" stroke="url(#{grad})" stroke-width="3"/>'
        # Two seam arcs bulging outward (the px-ball / favicon read) so the apex
        # ball is clearly a baseball, not a plain circle.
        '<path class="eephus-logo-seam" d="M 16 5.6 Q 20.5 12 16 18.4" fill="none" stroke="currentColor" stroke-width="1.3"/>'
        '<path class="eephus-logo-seam" d="M 8 5.6 Q 3.5 12 8 18.4" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>'
    )
    return (f'<{tag} class="nameplate eephus-wordmark-merged">{arc}'
            f'eephus<span class="dot">.io</span></{tag}>')

def prospx_ball_logo(uid: str, px: int = 16) -> str:
    """The PROSPX baseball badge - a self-contained copy of the app
    masthead's .h1-logo SVG (cream ball, gradient seams, P/X monogram) for
    sidebar/nav lockups. Fills ride the theme tokens via inline style; the
    seam gradient keeps the masthead's literal stops (SVG gradients can't
    read CSS var()). ``uid`` keeps gradient ids unique per placement."""
    gid = f"px-seam-{uid}"
    return (
        f'<svg class="px-ball" width="{px}" height="{px}" viewBox="0 0 44 44" aria-hidden="true">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#B91C1C"/><stop offset="35%" stop-color="#C9A227"/>'
        '<stop offset="65%" stop-color="#1F7A3A"/><stop offset="100%" stop-color="#0E2B4D"/>'
        '</linearGradient></defs>'
        '<circle cx="22" cy="22" r="19" style="fill:var(--bg-secondary);stroke:var(--text-primary);stroke-width:2"/>'
        f'<path stroke="url(#{gid})" d="M 32 8 Q 40 22 32 36" style="fill:none;stroke-width:3;stroke-linecap:round"/>'
        '<path d="M 32 8 Q 40 22 32 36" style="fill:none;stroke:var(--text-primary);stroke-width:1.2;stroke-linecap:round;stroke-dasharray:1.5 3"/>'
        f'<path stroke="url(#{gid})" d="M 12 8 Q 4 22 12 36" style="fill:none;stroke-width:3;stroke-linecap:round"/>'
        '<path d="M 12 8 Q 4 22 12 36" style="fill:none;stroke:var(--text-primary);stroke-width:1.2;stroke-linecap:round;stroke-dasharray:1.5 3"/>'
        '<g text-anchor="middle" style="font-family:\'Old English Text MT\',\'UnifrakturCook\',Georgia,serif;'
        'font-weight:800;fill:var(--text-primary);stroke:var(--bg-secondary);stroke-width:0.7;paint-order:stroke">'
        '<text x="18.5" y="30" font-size="22">P</text><text x="26" y="30" font-size="23">X</text></g>'
        '</svg>'
    )

def eephus_logo_lockup(badge: bool = True) -> str:
    """Homepage hero lockup: the merged arc-wordmark with the β tag and the
    @eephus_io chip stacked beside it (β on top, X under - the X chip carries
    the link accent so it reads clickable)."""
    chips = (
        f'<div class="eephus-logo-chips">{BETA_BADGE}'
        f'{_x_link("eephus_io", cls="eph-xlink--beta eph-xlink--live")}'
        f'{_discord_link(cls="eph-xlink--beta eph-xlink--live")}</div>'
    ) if badge else ""
    # eephus-logo--animate plays the one-shot arc-draw + ball-settle on the
    # homepage hero only (the nav/sidebar lockups stay static). It plays under
    # Reduce Motion as well; see assets/site.css.
    return f'<div class="eephus-logo eephus-logo--animate">{eephus_merged_wordmark("mast")}{chips}</div>'

# --------------------------------------------------------------------------- #
# Markdown + YouTube
# --------------------------------------------------------------------------- #
_YT_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([A-Za-z0-9_-]{11})"
)

def _youtube_id(raw: str) -> str | None:
    raw = raw.strip()
    m = _YT_RE.search(raw)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):   # bare id
        return raw
    return None

def _youtube_embed(video_id: str) -> str:
    src = f"https://www.youtube.com/embed/{video_id}"
    return (
        '<div class="video-embed">'
        f'<iframe src="{src}" title="YouTube video" loading="lazy" '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
        'picture-in-picture" allowfullscreen></iframe></div>'
    )

def render_markdown(text: str) -> str:
    """Render article markdown to HTML, with a clean `@youtube: <url>` directive.
    The directive is swapped for a placeholder before conversion, then back to a
    responsive iframe afterward, so the markdown engine never mangles the embed."""
    placeholders: dict[str, str] = {}
    out_lines = []
    for line in text.splitlines():
        m = re.match(r"^\s*@youtube:\s*(\S+)\s*$", line)
        if m:
            vid = _youtube_id(m.group(1))
            if vid:
                token = f"@@YT_{len(placeholders)}@@"
                placeholders[token] = _youtube_embed(vid)
                out_lines.append("")
                out_lines.append(token)
                out_lines.append("")
                continue
        out_lines.append(line)
    body = md.markdown(
        "\n".join(out_lines),
        extensions=["extra", "sane_lists", "smarty"],
        output_format="html5",
    )
    for token, embed in placeholders.items():
        body = body.replace(f"<p>{token}</p>", embed).replace(token, embed)
    return body

# --------------------------------------------------------------------------- #
# Prospect deep-linking - turn the first mention of a known player's name into a
# link to their PROSPX detail page (/prospx/#player=<key>), the same deep link the
# homepage modules use. Matching is accent/'.'-insensitive so Will's "Rodríguez" /
# "Witt Jr" resolve against the data's "Rodriguez" / "Witt Jr.".
# --------------------------------------------------------------------------- #
def _norm_map(s: str):
    """Accent-stripped, lowercased copy of `s` plus an index map back to the
    original character positions (so we can wrap the original spelling)."""
    out, idx = [], []
    for i, ch in enumerate(s):
        for d in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(d):
                continue
            out.append(d.lower())
            idx.append(i)
    return "".join(out), idx

@functools.lru_cache(maxsize=1)
def _player_links() -> tuple:
    """(normalized full name, player_key) pairs from the live data layer (prospects +
    graduates), longest first. Only players with a real PROSPX page are linkable."""
    data = load_site_data() or {}
    seen, pairs = set(), []
    for p in (data.get("players") or []) + (data.get("graduates") or []):
        nm = (p.get("player_name") or "").strip()
        key = p.get("player_key")
        if not nm or not key or " " not in nm:      # full "First Last" names only
            continue
        norm = _norm_map(nm)[0].rstrip(".").strip()
        if len(norm) < 6 or norm in seen:
            continue
        seen.add(norm)
        pairs.append((norm, key))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return tuple(pairs)

def _linkify_players(body_html: str) -> str:
    """Link the first mention of each known player name. Operates only on text nodes
    (tags + their attributes, e.g. image alt text, and existing <a>…</a> are skipped)."""
    pairs = _player_links()
    if not pairs:
        return body_html
    linked = set()
    parts = re.split(r'(<[^>]+>)', body_html)
    in_link = False
    for i, tok in enumerate(parts):
        if tok[:1] == "<":
            t = tok.lower()
            if t.startswith("<a"):
                in_link = True
            elif t.startswith("</a"):
                in_link = False
            continue
        if in_link or not tok.strip():
            continue
        nrm, idx = _norm_map(tok)
        hits = []
        for norm, key in pairs:
            if key in linked:
                continue
            pos = nrm.find(norm)
            if pos < 0:
                continue
            end = pos + len(norm)
            before = nrm[pos - 1] if pos > 0 else " "
            after = nrm[end] if end < len(nrm) else " "
            if before.isalnum() or after.isalnum():     # require clean word boundaries
                continue
            hits.append((idx[pos], idx[end - 1] + 1, key))
        if not hits:
            continue
        out, cur = [], 0
        for s, e, key in sorted(hits):
            if s < cur:                                 # drop overlapping matches
                continue
            href = f"/prospx/#player={html.escape(key)}"
            out.append(tok[cur:s])
            out.append(f'<a class="px-link" href="{href}">{html.escape(tok[s:e])}</a>')
            linked.add(key)
            cur = e
        out.append(tok[cur:])
        parts[i] = "".join(out)
    return "".join(parts)

# --------------------------------------------------------------------------- #
# Frontmatter
# --------------------------------------------------------------------------- #
def parse_article(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            fm = raw[3:end].strip("\n")
            body = raw[end + 4:].lstrip("\n")
            for ln in fm.splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    meta[k.strip()] = v.strip()
    meta.setdefault("title", path.stem.replace("-", " ").title())
    meta["slug"] = path.stem
    meta["body_html"] = _linkify_players(render_markdown(body))
    meta["date_sort"] = meta.get("date", "")
    meta["date_disp"] = _fmt_date(meta.get("date", ""))
    return meta

def _fmt_date(s: str) -> str:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").strftime("%B %-d, %Y")
    except (ValueError, AttributeError):
        try:  # Windows strftime has no %-d
            return datetime.strptime(s.strip(), "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            return s

def _member_slug(name: str) -> str:
    """Stable per-person anchor slug for a Development Team card (e.g.
    'Will Cahoon' -> 'will-cahoon'). Used by both the team-card id and the
    article byline deep-link so they always line up."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")

def _team_index() -> dict:
    """name(lowercased) -> {slug, handle} from content/team.json - the single
    source of truth for dev-team identity + X handles. Empty on any error."""
    idx: dict = {}
    try:
        members = json.loads((CONTENT / "team.json").read_text(encoding="utf-8"))
    except Exception:
        return idx
    for m in members:
        nm = (m.get("name") or "").strip()
        if nm:
            idx[nm.lower()] = {"slug": _member_slug(nm), "handle": (m.get("handle") or None)}
    return idx

def _byline(meta: dict, sep: str = " · ", link_handle: bool = True) -> str:
    # link_handle=False when the byline sits INSIDE a card <a> (nested <a> is
    # invalid HTML and the browser splits the card apart) - render the author +
    # @handle as text there, and only deep-link on the standalone article page.
    author = (meta.get("author", "") or "").strip()
    member = _team_index().get(author.lower())  # None for guest authors
    # Author name → their Development Team card (deep-linked) when they're on the
    # team and we're allowed to emit a link; otherwise plain text. No broken
    # anchors - a guest author with no card simply isn't linked.
    if author and member and link_handle:
        author_html = (f'<a class="byline-author" href="/team/#member-{member["slug"]}">'
                       f'{html.escape(author)}</a>')
    elif author:
        author_html = f'<span class="author">{html.escape(author)}</span>'
    else:
        author_html = ""
    # Handle → X profile. Prefer the dev-team handle (single source of truth);
    # fall back to the article's own handle only for guests not on the team.
    # Missing handle → hidden, never a guessed URL.
    if member:
        handle = (member.get("handle") or "").lstrip("@") or None
    else:
        handle = (meta.get("handle") or "").lstrip("@") or None
    parts = [author_html] if author_html else []
    if handle:
        parts.append(
            f'<a class="byline-handle" href="https://x.com/{html.escape(handle)}" '
            f'target="_blank" rel="noopener noreferrer">@{html.escape(handle)}</a>'
            if link_handle else f'<span class="handle">@{html.escape(handle)}</span>'
        )
    if meta.get("date_disp"):
        parts.append(html.escape(meta["date_disp"]))
    return sep.join(parts)

# --------------------------------------------------------------------------- #
# Page shell
# --------------------------------------------------------------------------- #
def _nav(active: str) -> str:
    # The top bar runs one line, always - long labels get a short form
    # here (the homepage sidebar keeps the full names).
    short = {}
    items = []
    for item in NAV_ITEMS:
        if _nav_is_group(item):
            children = item["children"]
            active_in = any(k == active for k, _l, _h in children)
            clinks = []
            for k, l, h in children:
                ccls = ' class="is-active"' if k == active else ""
                # PX-04: a 12 px pixel icon before the unchanged label, in the
                # desktop dropdown and in the phone drawer alike.
                clinks.append(f'<a href="{h}" role="menuitem"{ccls}>{_ico(k, 12)}{html.escape(short.get(k, l))}</a>')
            gcls = " is-active" if active_in else ""
            # Native <details> dropdown: click-toggles, keyboard-accessible with
            # zero JS. assets/eephus-nav.js adds outside-click/Esc close and
            # fixed-positions the menu so it escapes the nav's overflow clip.
            items.append(
                f'<details class="eephus-nav-group{gcls}" data-nav-group>'
                f'<summary aria-haspopup="true">{html.escape(item["group"])}'
                f'<span class="nav-caret" aria-hidden="true">▾</span></summary>'
                f'<div class="eephus-nav-menu" role="menu">{"".join(clinks)}</div>'
                '</details>'
            )
        else:
            key, label, href = item
            cls = ' class="is-active"' if key == active else ""
            items.append(f'<a href="{href}"{cls}>{_nav_drawer_ico(key)}{html.escape(short.get(key, label))}</a>')
    # Site-wide controls (right-aligned), matching PROSPX's primary nav: a
    # Watchlist deep-link into PROSPX + the Dark Mode toggle. PX-22 (owner
    # answer PX-Q2): the three glyphs are pixel icons now (the old ⌘ and ☾ fell
    # back to a system face); same buttons, boxes, labels and aria-labels.
    controls = (
        '<div class="eephus-nav-controls">'
        '<button class="eephus-nav-ctrl" type="button" data-qk-open aria-label="Quick search (Ctrl+K)" title="Search any term or metric - Ctrl+K / ⌘K">'
        f'{_ico("search", 12)}<span class="eephus-nav-ctrl-label">Search</span></button>'
        '<a class="eephus-nav-ctrl" href="/prospx/#tab=watchlist" aria-label="Watchlist">'
        f'{_ico("watchlist", 12)}<span class="eephus-nav-ctrl-label">Watchlist</span></a>'
        '<button class="eephus-nav-ctrl" type="button" data-theme-toggle onclick="eephusToggleTheme()" aria-label="Toggle dark mode">'
        f'<span class="theme-icon lbl-dark" aria-hidden="true">{_ico("theme-dark", 12)}</span>'
        f'<span class="theme-icon lbl-light" aria-hidden="true">{_ico("theme-light", 12)}</span>'
        '<span class="eephus-nav-ctrl-label"><span class="lbl-dark">Dark Mode</span><span class="lbl-light">Light Mode</span></span>'
        '</button></div>'
    )
    return (
        '<header class="eephus-nav">'
        f'<span class="eephus-brand"><a class="eephus-wordmark" href="/" aria-label="eephus.io home">'
        f'{eephus_merged_wordmark("nav", tag="span")}</a></span>'
        f'<nav class="eephus-links">{"".join(items)}</nav>'
        f'{controls}'
        "</header>"
    )

def _social_meta(title: str, description: str, image: str = "", url: str = "",
                 og_type: str = "website") -> str:
    """Open Graph + Twitter card tags so a shared link (X/Facebook/iMessage) renders a
    rich preview. Every page gets the default brand card; articles override `image`
    with their per-piece share card and `og_type` with "article"."""
    t, d = html.escape(title), html.escape(description)
    image = image or DEFAULT_SHARE_IMAGE
    tags = [f'<meta property="og:type" content="{html.escape(og_type)}">',
            f'<meta property="og:title" content="{t}">',
            f'<meta property="og:description" content="{d}">',
            '<meta property="og:site_name" content="eephus.io">']
    if url:
        tags += [f'<meta property="og:url" content="{html.escape(url)}">',
                 f'<link rel="canonical" href="{html.escape(url)}">']
    tags += [f'<meta property="og:image" content="{html.escape(image)}">',
             '<meta name="twitter:card" content="summary_large_image">',
             f'<meta name="twitter:title" content="{t}">',
             f'<meta name="twitter:description" content="{d}">',
             f'<meta name="twitter:image" content="{html.escape(image)}">']
    return "\n".join(tags)

def page(title: str, active: str, body: str, description: str = "",
         image: str = "", url: str = "", og_type: str = "website",
         robots: str = "") -> str:
    desc = html.escape(description or "eephus.io - sabermetrics")
    social = _social_meta(title, description or "eephus.io - sabermetrics",
                          image, url, og_type)
    robots_meta = (f'\n<meta name="robots" content="{html.escape(robots)}">'
                   if robots else "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{robots_meta}
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
{social}
{FAVICON_LINKS}
<link rel="stylesheet" href="/assets/site.css?v={_CSS_VER}">
<script src="/assets/eephus-nav.js?v={_NAV_VER}" defer></script>
<script src="/assets/eephus-tiers.js?v={_TIERS_VER}" defer></script>
<script src="/assets/eephus-state.js?v={_STATE_VER}" defer></script>
{ACCOUNT_CSS_LINK}
</head>
<body class="eephus-page">
{_nav(active)}
<main class="eephus-wrap">
{body}
</main>
{_footer()}
{ACCOUNT_SCRIPTS}
</body>
</html>
"""

# --------------------------------------------------------------------------- #
# Page builders
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Live PROSPX data (build-time). Reads the same data/*.json PROSPX uses so the
# homepage modules + wire feed regenerate on each build (run after run_monthly).
# --------------------------------------------------------------------------- #
DATA_DIR = ROOT / "data"
ORG_NAMES = {
    "ARI": "Diamondbacks", "ATH": "Athletics", "ATL": "Braves", "BAL": "Orioles",
    "BOS": "Red Sox", "CHC": "Cubs", "CHW": "White Sox", "CIN": "Reds",
    "CLE": "Guardians", "COL": "Rockies", "DET": "Tigers", "HOU": "Astros",
    "KCR": "Royals", "LAA": "Angels", "LAD": "Dodgers", "MIA": "Marlins",
    "MIL": "Brewers", "MIN": "Twins", "NYM": "Mets", "NYY": "Yankees",
    "PHI": "Phillies", "PIT": "Pirates", "SDP": "Padres", "SEA": "Mariners",
    "SFG": "Giants", "STL": "Cardinals", "TBR": "Rays", "TEX": "Rangers",
    "TOR": "Blue Jays", "WSN": "Nationals",
}

# --------------------------------------------------------------------------- #
# eFV grade map (data/xfv.json -> {player_key: headline xfv_grade}).
#
# eFV is the flagship outcome-grounded FV model (the PROSPX primary grade). The
# homepage Top Prospects module historically ranked + displayed CONSENSUS
# `fv_close`; this map lets it lead with eFV instead, with consensus as the
# fallback for any player eFV abstains on (no MiLB track record => absent from
# by_player). Loaded once at module import - missing/corrupt file => empty map,
# so the homepage behaves EXACTLY as before. Since the 2026-07-06 quantile flip
# the DISPLAYED eFV site-wide is `xfv_grade` (RAW, as of the 2026-07-25 unification;
# it was `xfv_grade_quantile` between 2026-07-06 and then) (the model ranking on the
# 20-80 consensus scale; the grade surplus is priced on) - prefer it here so the
# homepage Top Prospects grade matches the PROSPX board and /projections/, with
# the realized grade, then the raw grade, as legacy fallbacks.
def _load_xfv_grades() -> dict:
    try:
        doc = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    try:
        from efv_board_scale import board_value as _scale
    except Exception:                                       # pragma: no cover
        def _scale(rec):
            return (rec or {}).get("xfv_grade")
    out = {}
    for key, rec in (doc.get("by_player") or {}).items():
        rec = rec or {}
        # BASIS REPAIR 2026-07-25. The board was unified on xfv_grade (one number
        # for display, sort and overall_rank - see storage.BOARD_GRADE_FIELD and
        # prospx efvBoardValue), so reading xfv_grade_quantile FIRST here made the
        # homepage Top Prospects module disagree with the board it is supposed to
        # mirror: same player, different FV. Precedence now matches the board exactly.
        # Do not reorder these without changing BOARD_GRADE_FIELD too.
        #
        # W-SIDESCALE 2026-07-25: the board SCALE is owned by efv_board_scale, not by
        # this reader. board_value() re-derives from `xfv_grade_model_raw` when the
        # artifact has been stamped, so the homepage grade equals the prospx board
        # grade for the same player under either state of the flag, and there is no
        # second copy of the coefficients here to drift.
        g = _scale(rec)
        if g is None:
            g = rec.get("xfv_grade_realized")
        if g is None:
            g = rec.get("xfv_grade_quantile")
        if isinstance(g, (int, float)):
            out[key] = float(g)
    return out
_EFV_GRADES = _load_xfv_grades()

def _primary_fv(p: dict):
    """RAW primary FV for a player: the eFV grade when eFV has a grade for this
    player_key, else the consensus close. Consensus is the fallback EVERYWHERE
    so players eFV abstains on are unchanged. Returns a float or None.

    NB: raw (unrounded) - callers that DISPLAY a grade must ceil-round per the
    repo's grades-round-UP rule; sort/tier logic uses the raw value."""
    g = _EFV_GRADES.get(p.get("player_key"))
    if g is not None:
        return g
    fv = p.get("fv_close")
    if fv is None:
        fv = p.get("consensus_fv")
    return fv

def _fmt_iso_date(s: str | None) -> str:
    if not s:
        return " - "
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return " - "

def load_site_data() -> dict | None:
    ts_path = DATA_DIR / "timeseries.json"
    if not ts_path.exists():
        return None
    ts = json.loads(ts_path.read_text(encoding="utf-8"))
    grads = []
    dpath = DATA_DIR / "debuts.json"
    if dpath.exists():
        d = json.loads(dpath.read_text(encoding="utf-8"))
        grads = d if isinstance(d, list) else (d.get("players") or d.get("debuts") or [])
    # The homepage surfaces daily-fresh content (movers, transactions,
    # graduates), so its "Data as of" tracks the freshest run (daily refresh
    # when one has happened, else the monthly generated_at).
    fresh = ts.get("data_freshness") or {}
    as_of_iso = fresh.get("transactions_updated_at") or ts.get("generated_at")
    return {
        "as_of": _fmt_iso_date(as_of_iso),
        # The same stamp unformatted. The pages want the prose date; a derived
        # JSON artifact wants the machine one, and re-reading the 74MB
        # timeseries.json just to recover it is not a trade worth making.
        "as_of_iso": as_of_iso or "",
        "players": ts.get("players") or [],
        "org_summary": ts.get("org_summary") or [],
        "graduates": grads,
        # The movement engine's three published buckets (risers / rebounders /
        # fallers, plus the legacy `hot` alias of risers - see
        # test_spotlights_three_buckets.py). Carried through here so the sidebar
        # spotlight can rotate over them without re-parsing timeseries.json.
        "spotlights": ts.get("spotlights") or {},
    }

def _player_href(key: str) -> str:
    # "fa:" keys belong to the Free Agency surface (separate from PROSPX) - 
    # they deep-link the /fa/ player card, not a PROSPX player page.
    if key and key.startswith("fa:"):
        return f"/fa/#player={key[3:]}"
    return f"/prospx/#player={key}" if key else "/prospx/"

# ORG abbreviation -> ESPN logo slug (mirrors ESPN_LOGO_SLUGS in prospx/index.html).
ESPN_SLUGS = {
    "ARI": "ari", "ATH": "ath", "ATL": "atl", "BAL": "bal", "BOS": "bos",
    "CHC": "chc", "CHW": "chw", "CIN": "cin", "CLE": "cle", "COL": "col",
    "DET": "det", "HOU": "hou", "KCR": "kc",  "LAA": "laa", "LAD": "lad",
    "MIA": "mia", "MIL": "mil", "MIN": "min", "NYM": "nym", "NYY": "nyy",
    "PHI": "phi", "PIT": "pit", "SDP": "sd",  "SEA": "sea", "SFG": "sf",
    "STL": "stl", "TBR": "tb",  "TEX": "tex", "TOR": "tor", "WSN": "wsh",
}

def _team_logo(org: str | None, cls: str = "row-logo") -> str:
    """Clean ESPN CDN team logo (falls back to the ORG abbreviation chip).
    `cls` lets callers reuse it at other sizes (e.g. the ticker's tk-logo)."""
    if not org:
        return ""
    o = html.escape(org)
    slug = ESPN_SLUGS.get(org, org.lower())
    return (f'<img class="{cls}" src="https://a.espncdn.com/i/teamlogos/mlb/500/{slug}.png" alt="{o}" loading="lazy" '
            f"onerror=\"this.outerHTML='<span class=&quot;{cls}&quot; style=&quot;font:700 9px var(--font-retro-mono);display:inline-flex;align-items:center;justify-content:center&quot;>{o}</span>'\">")

def _round_half_up(x: float) -> int:
    """Round HALF-UP (ties toward +infinity) - the JS `Math.round` convention.

    THE ONE ROUNDER for every eFV number this file prints or steps. Python's
    built-in round() is banker's (half-to-EVEN): round(64.5)==64 while
    Math.round(64.5)==65, so any x.5 eFV grade made the homepage disagree with
    the PROSPX board / player card / projections, which all round in JS. It is
    correct for signed values too (grade DELTAS): floor(-1.5+0.5) == -1, exactly
    what Math.round(-1.5) returns, where round(-1.5) would give -2.

    Consensus FV is NOT this: it rounds CEIL (see _fv_label's fallback branch)."""
    return int(math.floor(x + 0.5))

def _fv_label(p: dict) -> str:
    # Lead with the eFV grade when eFV has graded this player (round-to-NEAREST: eFV is the
    # true-model grade, so it rounds nearest, not up). For players eFV abstains on, keep the
    # EXACT prior behavior: the published consensus label off points[] (which carries
    # snapping / '+' upside), else ceil(fv_close) (consensus FV still rounds up).
    g = _EFV_GRADES.get(p.get("player_key"))
    if g is not None:
        return str(_round_half_up(g))
    pts = p.get("points") or []
    if pts and pts[-1].get("consensus_fv_label") is not None:
        return str(pts[-1]["consensus_fv_label"])
    fv = p.get("fv_close")
    return str(int(math.ceil(fv))) if fv is not None else " - "

def _fv_tier_class(label: str) -> str:
    """Tier class from the DISPLAYED integer, not the raw grade.

    Keying tiers on the raw grade while printing the rounded one meant the
    number and its colour could disagree: roch_cholowsky (eFV 59.9) printed
    "60" in a plain pill while franklin_arias (60.3) and leo_de_vries (60.2)
    printed the same "60" in gold, and jesus_made (60.9) printed "61" without
    reaching holo. Any raw grade in [59.5, 60) or [60.5, 61) hit this window.

    This is the JS rule (fvClass parses the label it is handed), so the
    generated homepage and the PROSPX board can no longer disagree."""
    m = re.match(r"-?\d+", (label or "").strip())
    if not m:
        return "fv-pill"
    disp = int(m.group())
    if disp >= 61:
        return "fv-pill holo"
    if disp >= 60:
        return "fv-pill gold"
    return "fv-pill"


def _fv_pill(p: dict) -> str:
    label = _fv_label(p)
    return f'<span class="{_fv_tier_class(label)}">{html.escape(label)}</span>'

def _meta(*parts) -> str:
    return html.escape(" · ".join(str(x) for x in parts if x))

# Baseball America's 2023 org boards print "CP" as the position line of every
# catcher (61 rows on the 2023-02-15 boards, all catchers, no other board), and
# a graduate whose last board was BA 2023 carries that token into debuts.json
# (16 debuted catchers on 2026-10-01: Bo Naylor, Francisco Alvarez, Gabriel
# Moreno and others). Every other reader of a position string takes CP for a
# closer, so the page printed "debuted · CP" for a catcher. The printed label
# says what the player is: CP prints as C. Display only: the position field and
# every model read of it stay as they are (SHO01).
_POS_LABEL_FIX = {"CP": "C"}


def _pos_label(pos) -> str:
    """The position as a page prints it. Unchanged unless a "/" token is in
    _POS_LABEL_FIX, so "OF / C" and every other label keeps its own spelling."""
    s = str(pos or "")
    toks = s.split("/")
    if not any(t.strip().upper() in _POS_LABEL_FIX for t in toks):
        return s
    return "/".join(_POS_LABEL_FIX.get(t.strip().upper(), t.strip()) for t in toks)

# --------------------------------------------------------------------------- #
# Real consensus-grade movement, computed from the player's own points[].
#
# `stock` in timeseries.json is the PERFORMANCE-ANCHORED MOVEMENT ENGINE
# (spotlights.compute_movement): its `delta` is a composite score (perf +
# skills + list-jump + pedigree) and its from/to dates are simply the last two
# snapshots - with daily TJStats Live captures that's "yesterday → today" for
# every active prospect. The homepage was written against the legacy
# stock_movement shape (a true FV delta over a meaningful window) and silently
# broke when storage switched the field to the engine: the wire showed engine
# scores as "▲ +5 FV" items dated at the latest Live refresh. These helpers
# read the published grade history directly so a "+N FV" on the homepage is
# always a real grade change - and wire items are dated when the consensus
# actually moved, not when a daily capture re-confirmed it.
# --------------------------------------------------------------------------- #
def _label_series(p: dict) -> list[tuple[str, int]]:
    """(snapshot_date, consensus grade as int) per point, oldest → newest.

    NOT an eFV read, so it deliberately does NOT take _round_half_up:
    `consensus_fv_label` is the PUBLISHED consensus label, already an integer on
    every point, so the round() here is a type coercion and never breaks a tie."""
    out = []
    for pt in (p.get("points") or []):
        d = pt.get("snapshot_date")
        try:
            v = int(round(float(pt.get("consensus_fv_label"))))
        except (TypeError, ValueError):
            continue
        if d:
            out.append((str(d)[:10], v))
    return out

def _fv_window_delta(p: dict, days: int = 365) -> int | None:
    """Consensus-grade change over the trailing window (label units). Anchor
    mirrors consensus.stock_movement v12: latest grade minus the grade at the
    snapshot closest to (latest − days) without crossing it; falls back to the
    earliest snapshot when history is shorter than the window."""
    series = _label_series(p)
    if len(series) < 2:
        return None
    last_d, last_v = series[-1]
    try:
        cutoff = date.fromisoformat(last_d) - timedelta(days=days)
    except ValueError:
        return last_v - series[-2][1]
    prior_v = series[0][1]
    for d, v in series[:-1]:
        try:
            if date.fromisoformat(d) <= cutoff:
                prior_v = v
            else:
                break
        except ValueError:
            continue
    return last_v - prior_v

def _latest_fv_change(p: dict) -> tuple[str, int, int] | None:
    """The most recent ACTUAL grade change as (date_of_change, step,
    new_grade). None when the published grade has never moved. This is what
    the wire treats as FV news - daily Live re-confirmations of an unchanged
    grade are not events.

    CAUTION: when the change pair ends at the rolling daily Live point, the
    returned date is that point's snapshot_date - which the daily capture
    RE-STAMPS to today on every run. The wire must not consume it raw (a
    player would ride the most-recent-day bucket forever); _collect_events
    pins it through the first-seen ledger below."""
    series = _label_series(p)
    for i in range(len(series) - 1, 0, -1):
        prev_v = series[i - 1][1]
        cur_d, cur_v = series[i]
        if cur_v != prev_v:
            return (cur_d, cur_v - prev_v, cur_v)
    return None


# First-seen ledger for wire FV items (the fa_events stamping pattern).
# The daily Live snapshot re-dates its point every run, so a grade change
# detected against it would re-date daily and pin the player to the wire's
# most-recent-day bucket indefinitely (Cleiner Ramirez, 3 straight days,
# 2026-06-12 report). The ledger records the date each (player, new grade)
# was FIRST published and serves that date forever after.
_WIRE_FV_LEDGER = DATA_DIR / "wire_fv_first_seen.json"

def _wire_fv_first_seen(ledger: dict, key: str, new_fv: int, seen_date: str) -> str:
    entry = ledger.get(key)
    if entry and entry.get("fv") == new_fv:
        return entry["first_seen"]
    ledger[key] = {"fv": new_fv, "first_seen": seen_date}
    return seen_date

def _load_wire_fv_ledger() -> dict:
    try:
        d = json.loads(_WIRE_FV_LEDGER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}

def _save_wire_fv_ledger(ledger: dict, live_keys: set) -> None:
    """Prune departed players, write only on real change (stable output so
    test runs and no-op rebuilds never churn the committed file)."""
    pruned = {k: v for k, v in sorted(ledger.items()) if k in live_keys}
    raw = json.dumps(pruned, indent=0, sort_keys=True)
    try:
        if _WIRE_FV_LEDGER.exists() and _WIRE_FV_LEDGER.read_text(encoding="utf-8") == raw:
            return
    except OSError:
        pass
    _WIRE_FV_LEDGER.write_text(raw, encoding="utf-8")

_HOME_MOVER_RECENCY_DAYS = 365

def _genuine_mover_step(p: dict) -> int | None:
    """Homepage Top Movers selector: the de-noised grade step from the movement
    engine (carried on `stock`), gated to genuine, recent moves.

    eFV is the site's primary grade, so the PRIMARY mover signal is the eFV
    "since last real change" step (basis="xfv"): the eFV trajectory already
    de-bands (walks back to the last >=0.5 step), so an eFV move IS a genuine
    move and needs no source-confidence gate. Where a player has no eFV history
    the engine falls back to the de-noised same-source consensus step
    (basis="same_source"), which DOES keep its confidence gate (it excludes
    panel-composition shifts and lone-outlier re-grades). Because the homepage
    module is a recency surface ("moving now"), the step must have landed within
    the trailing year. Returns the signed integer grade step (>=2 in magnitude)
    or None. The per-player stock chips keep showing each player's last real move
    regardless of age; this module is the recent-movers view."""
    st = p.get("stock") or {}
    basis = st.get("basis")
    if st.get("delta") is None or st.get("direction") in ("flat", "debuted", None):
        return None
    if basis == "xfv":
        pass                                          # eFV step is self-de-noised
    elif basis == "same_source":
        if st.get("confidence") not in ("high", "medium"):
            return None
    else:
        return None
    try:
        moved = date.fromisoformat(str(st.get("to_date"))[:10])
    except (TypeError, ValueError):
        return None
    if moved < date.today() - timedelta(days=_HOME_MOVER_RECENCY_DAYS):
        return None
    step = _round_half_up(st["delta"])   # eFV-basis step -> half-up, like the JS
    return step if abs(step) >= 2 else None


def _mover_at_floor(p: dict) -> bool:
    """True when an eFV-basis move has an endpoint on the model floor (eFV 20.0).

    Such a step is the player reaching or leaving the floor route, not a
    re-grade: on the 2026-09-23 board 316 of the 322 steps of 15 or more were
    this kind. The predicate is efv_alerts._at_floor, imported so the feed and
    the home page split the two event types the same way. It is applied at the
    home call sites and NOT inside _genuine_mover_step, because efv_alerts uses
    that gate too and deliberately keeps floor rows under a share cap."""
    st = p.get("stock") or {}
    return st.get("basis") == "xfv" and efv_alerts._at_floor(st)


def _mover_unit(p: dict) -> str:
    """The grade a mover step is measured in: eFV on the xfv basis, FV on the
    consensus fallback."""
    return "eFV" if (p.get("stock") or {}).get("basis") == "xfv" else "FV"

def _row_mover(p: dict, d: int) -> str:
    up = d > 0
    # Mini FV-history sparkline - reinforces the stock-chart identity. Colored
    # by direction; drawn as the pixel step line (PX-16): 56 x 20, so eight
    # snapshots get 7 px each and no column is resampled.
    spark = _fv_sparkline(p.get("points"), "var(--accent-green)" if up else "var(--accent-red)", w=56, h=20)
    spark_html = f'<span class="row-spark">{spark}</span>' if spark else '<span class="row-spark"></span>'
    # Rank + team logo lead the row (same idiom as Top Prospects); position +
    # FV chip sit before the move delta so a mover reads like a ranked entry
    # with its grade, not just an arrow. Rank slot stays present (blank) when a
    # player has no overall rank so the columns line up.
    rank = p.get("overall_rank")
    rank_html = f'<span class="row-rank">{rank}</span>' if rank else '<span class="row-rank"></span>'
    return (f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'{rank_html}{_team_logo(p.get("org"))}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(_pos_label(p.get("position")))}</span>'
            f'{spark_html}{_fv_pill(p)}'
            f'<span class="row-delta {"up" if up else "down"}">{"▲" if up else "▼"} {"+" if up else ""}{d}</span></a>')

def _row_top(p: dict, rank: int) -> str:
    return (f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'<span class="row-rank">{rank}</span>{_team_logo(p.get("org"))}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(_pos_label(p.get("position")))}</span>{_fv_pill(p)}</a>')

def display_metric_for(p: dict) -> dict:
    """Single source of truth for which realized metric a player's shared
    "value" slot shows. The metric ESCALATES with on-field information:

      graduated to MLB          -> WAR  (career-since-debut eWAR + WAR/yr)
      prospect, settled sample  -> WAG  (regressed WAR-above-grade)
      prospect / no real sample -> FV   (the scouting-consensus projection)

    Why: WAG (WAR Above Grade) is only meaningful once a real sample has
    stabilized. It is misleading on a graduate (who now has actual MLB WAR to
    show) and on a prospect who hasn't played a pro season. So a graduate shows
    WAR, and a sub-threshold prospect shows FV - never a WAG number.

    The sample gate is the WAG model's OWN `below_meaningful_exposure` flag
    (config wag.meaningful_exposure = 200 PA / 80 IP ≈ ⅓ season); display and
    methodology share one source of truth rather than a re-invented threshold.

    NB on the data model: WAG (`debuted_value.wag`) is computed FROM a player's
    MLB sample, so in practice only graduates carry one - the WAG branch below is
    reachable only if a pre-graduation WAG is ever added; today every WAG-carrier
    graduates to the WAR branch. That is intended, not dead weight.

    Returns {metric: 'WAR'|'WAG'|'FV'|None, cls, html} - `metric` labels the
    value so a number sitting in a shared slot is never mistaken for another now
    that the slot can hold any of three. `html` is render-ready and HTML-safe."""
    cw = p.get("career_war") or {}
    is_grad = (p.get("status") == "debuted") or (cw.get("career_war") is not None)

    # 1) Graduated -> raw MLB WAR (career-since-debut eWAR: B-Ref frame, FIP
    #    pitching; hitters match bWAR unless they pitched). WAR/yr stays in
    # the hover tooltip only - as a visible suffix it was noise on the
    #    homepage grad rows, where most players have one partial MLB season
    #    and the per-year rate is just the WAR number echoed back.
    if is_grad:
        war = cw.get("career_war")
        if war is None:
            # WAR hasn't posted yet (brand-new debut) - keep it a WAR slot and be
            # honest the sample hasn't landed; never fabricate a number.
            return {"metric": "WAR", "cls": "flat",
                    "html": '<span class="row-meta" title="MLB WAR not yet posted"> - WAR</span>'}
        war_r = round(war, 1) + 0.0          # collapse -0.0
        cls = "up" if war_r > 0 else ("down" if war_r < 0 else "flat")
        wpy = cw.get("war_per_yr")
        nseas = cw.get("war_seasons_count")
        title = f"{war_r:.1f} career eWAR"
        if isinstance(wpy, (int, float)):
            title += f" · {wpy:.2f}/yr"
        if nseas:
            title += f" · {nseas} MLB season{'s' if nseas != 1 else ''}"
        return {"metric": "WAR", "cls": cls,
                "html": (f'<span class="row-delta {cls}" title="{html.escape(title)}">'
                         f'{war_r:.1f} WAR</span>')}

    # 2) Still a prospect with a SETTLED sample -> WAG (WAR above grade).
    wag = (p.get("debuted_value") or {}).get("wag") or {}
    rw = wag.get("regressed_wag")
    if rw is not None and not wag.get("below_meaningful_exposure"):
        wag_r = round(rw, 1) + 0.0
        cls = "up" if wag_r > 0 else ("down" if wag_r < 0 else "flat")
        sign = "+" if wag_r > 0 else ""      # negatives carry their own '-'; zero is unsigned
        return {"metric": "WAG", "cls": cls,
                "html": f'<span class="row-delta {cls}">{sign}{wag_r:.1f} WAG</span>'}

    # 3) No meaningful on-field sample yet -> FV (PRIMARY: eFV when graded, else
    #    the scouting consensus). `_primary_fv` already falls back fv_close ->
    #    consensus_fv; keep `fv` as a last-ditch legacy fallback.
    fv = _primary_fv(p) or p.get("fv")
    if fv is not None:
        return {"metric": "FV", "cls": "flat",
                "html": (f'<span class="row-meta" title="Final prospect FV - no MLB sample yet">'
                         # eFV-primary -> rounds to NEAREST, HALF-UP (_round_half_up),
                         # NOT python's banker's round(): that printed FV 64 for a 64.5
                         # eFV while the board beside it printed 65.
                         f'FV {_round_half_up(fv)}</span>')}
    return {"metric": None, "cls": "flat", "html": '<span class="row-meta">debut</span>'}


def _row_grad(g: dict) -> str:
    # "Recent Debuts": overall rank + the debut date (same compact gold stamp
    # as Today in Prospect History) + the player's final prospect FV. Career
    # WAR / WAG still live on the player + Debuted pages.
    rank = g.get("overall_rank")
    rank_html = f'<span class="row-rank">{rank}</span>' if rank else '<span class="row-rank"></span>'
    date_html = ""
    dd = g.get("debut_date")
    if dd:
        try:
            date_html = f'<span class="otd-when">{html.escape(_otd_date(date.fromisoformat(str(dd)[:10])))}</span>'
        except ValueError:
            pass
    return (f'<a class="row-link" href="{_player_href(g.get("player_key"))}">'
            f'{rank_html}{date_html}{_team_logo(g.get("org"))}'
            f'<span class="row-name">{html.escape(g.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(_pos_label(g.get("position")))}</span>{_fv_pill(g)}</a>')

def _recent_trades_html(players: list, n: int = 5) -> str:
    """'Recent Trades' module - the latest prospect trades from the tracked
    pool, newest first. Top 5, to sit level with Recent Graduates in the
    bottom grid row."""
    trs = []
    for p in players:
        for tr in (p.get("trades") or []):
            dt = str(tr.get("trade_date") or "")[:10]
            if len(dt) == 10:
                trs.append((dt, p, tr))
    # Recency floor mirrors the Top Movers window so "Recent Trades" can't show a
    # year-old deal as recent; ISO date strings compare lexicographically. With
    # nothing recent the module returns "" and drops out of the grid entirely.
    cutoff = (date.today() - timedelta(days=_HOME_MOVER_RECENCY_DAYS)).isoformat()
    trs = [t for t in trs if t[0] >= cutoff]
    if not trs:
        return ""
    trs.sort(key=lambda t: t[0], reverse=True)
    rows = []
    for dt, p, tr in trs[:n]:
        frm = html.escape(tr.get("from_org") or "?")
        to = html.escape(tr.get("to_org") or "?")
        rank = p.get("overall_rank")
        rank_html = f'<span class="row-rank">{rank}</span>' if rank else '<span class="row-rank"></span>'
        # From -> to as team logos (same idiom as Today in Prospect History's
        # trade rows), replacing the old "FRM ⇄ TO" text.
        logos = (f'<span class="trade-logos" title="Traded {frm} → {to}">'
                 f'{_team_logo(tr.get("from_org"), "otd-logo")}'
                 f'<span class="otd-arrow">→</span>'
                 f'{_team_logo(tr.get("to_org"), "otd-logo")}</span>')
        rows.append(
            f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'{rank_html}{logos}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(_pos_label(p.get("position")))}</span>'
            f'<span class="row-meta">{dt[5:7]}/{dt[8:10]}</span>'
            # FV chip trails the row so it lines up with the Recent Debuts
            # FV column beside it (both modules end with a flush-right pill).
            f'{_fv_pill(p)}</a>'
        )
    return _home_module("Recent Trades", "/prospx/#tab=traded", "All transactions", "".join(rows))

def _row_farm(o: dict, rank: int) -> str:
    # Match the PROSPX board: it shows the trailing-window letter (7y default)
    # first, falling back to the canonical overall grade. Both sides read the
    # same org_summary objects, so the homepage must use the same lookup.
    grade = ((o.get("letter_by_window") or {}).get("7y")
             or (o.get("grades") or {}).get("overall") or " - ")
    gcls = " gold" if str(grade).startswith("A") else ""
    name = ORG_NAMES.get(o.get("org"), o.get("org") or " - ")
    return (f'<a class="row-link" href="/prospx/#farm-org={html.escape(o.get("org") or "")}">'
            f'<span class="row-rank">{rank}</span>{_team_logo(o.get("org"))}'
            f'<span class="row-name">{html.escape(name)}</span>'
            f'<span class="row-meta">{o.get("count", "")} prospects</span>'
            f'<span class="fv-pill{gcls}">{html.escape(str(grade))}</span></a>')

# One mass re-grade (a single source dropping a 17-player international list)
# would otherwise fill the entire 12/14-item wire by itself; cap FV items per
# day (biggest grade steps win) so debuts / promotions / IL news from the same
# window keep their slots.
_WIRE_MAX_FV_PER_DAY = 6

@functools.lru_cache(maxsize=None)
def _cached_data_json(name: str) -> dict:
    """Parse a build-time JSON sidecar at most once per build. The home
    wire (_load_fa_events_for_wire) and the cross-module strip both read
    fa_class.json / mlb_projections.json; without this they were parsed
    twice each run. Committed sidecars don't change mid-build, so the cache
    is safe - callers must treat the result as read-only (shared instance)."""
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

def _load_fa_events_for_wire() -> list:
    """Recent winter events from the FA module's own export (the events
    block in data/fa_class.json). Additive: an absent or pre-events export
    just yields no items. Dates are the pipeline's first-seen stamps."""
    return _cached_data_json("fa_class.json").get("events") or []

def _collect_events(players: list, graduates: list, fa_events: list | None = None) -> list:
    # Each event is (date, typ, glyph, ticker_text, key, org, name, val):
    # `ticker_text` is the one-string form the scrolling WIRE marquee uses;
    # `name`/`val` are the structured halves the sidebar feed lays out as
    # name-left / value-right (PROSPX row idiom - no wrapping, scannable).
    # Internally a trailing weight orders same-date items editorially - 
    # debut > trade > promo/demo > IL > FV, bigger grade steps leading the
    # FV items. Stripped before return.
    ev = []
    def add(dt, typ, glyph, text, key, org=None, name="", val="", weight=0):
        if dt:
            ev.append((str(dt)[:10], typ, glyph, text, key, org, name, val, weight))
    fv_items = []
    fv_ledger = _load_wire_fv_ledger()
    for p in players:
        nm = p.get("player_name") or ""
        key = p.get("player_key")
        org = p.get("org")
        # FV news = the most recent GENUINE grade move carried on stock. Two
        # bases qualify: "xfv" (the live PRIMARY grade - movement.py emits a
        # numeric delta with a string "eFV NN.N" to_label) and the legacy
        # "same_source" consensus move (only sources grading the player at both
        # endpoints count, gated on high/medium confidence). Panel-composition
        # shifts (basis "panel_update") and thin samples (confidence "low")
        # never reach the wire. Dated at FIRST SIGHT via the ledger (the raw
        # change date rides the daily Live point and re-stamps to today every
        # run - see _latest_fv_change CAUTION). When stock is absent (older
        # payloads / tests), fall back to the raw grade-change detector.
        mv = p.get("stock") or {}
        chg = None
        if p.get("status") != "debuted":
            if (mv.get("basis") == "same_source" and mv.get("delta") is not None
                    and mv.get("direction") not in ("flat", "debuted")
                    and mv.get("confidence") in ("high", "medium")):
                step = _round_half_up(mv["delta"])
                try:
                    new_grade = _round_half_up(float(mv.get("to_label")))
                except (TypeError, ValueError):
                    new_grade = None
                if abs(step) >= 2 and new_grade is not None:
                    chg = (str(mv.get("to_date"))[:10], step, new_grade)
            elif (mv.get("basis") == "xfv" and mv.get("delta") is not None
                    and mv.get("direction") not in ("flat", "debuted")):
                step = _round_half_up(mv["delta"])
                # to_label is the string "eFV NN.N" for the xfv basis; pull the
                # number out and round it to nearest, HALF-UP - this is an eFV
                # value, so it takes the same rounder as _fv_label. Banker's
                # round() published "eFV 60" in the wire for a 60.5 grade the
                # board rendered as 61.
                _m = re.search(r"-?\d+(?:\.\d+)?", str(mv.get("to_label") or ""))
                try:
                    new_grade = _round_half_up(float(_m.group())) if _m else None
                except (TypeError, ValueError):
                    new_grade = None
                if abs(step) >= 2 and new_grade is not None:
                    chg = (str(mv.get("to_date"))[:10], step, new_grade)
            elif "stock" not in p:
                raw = _latest_fv_change(p)
                if raw and abs(raw[1]) >= 2:
                    chg = (str(raw[0])[:10], raw[1], raw[2])
        if chg:
            d_first = _wire_fv_first_seen(fv_ledger, key, chg[2], chg[0])
            # The row names the grade that moved: eFV on the xfv basis, FV on
            # the consensus fallbacks. A step with an endpoint on the eFV floor
            # is the player reaching or leaving the floor, so it reads as that
            # event and not as a signed grade step.
            fv_items.append((d_first, chg[1], nm, key, org,
                             _mover_unit(p), _mover_at_floor(p)))
        for lc in (p.get("level_changes") or []):
            if lc.get("kind") in ("promotion", "demotion"):
                promo = lc["kind"] == "promotion"
                lvls = f'{lc.get("from_level", "?")}→{lc.get("to_level", "?")}'
                add(lc.get("date"), "promo" if promo else "demo", "↑" if promo else "↓",
                    f'{nm} {"promoted" if promo else "demoted"} {lvls}', key, org,
                    name=nm, val=lvls, weight=80)
        for tr in (p.get("trades") or []):
            orgs = f'{tr.get("from_org", "?")}→{tr.get("to_org", "?")}'
            add(tr.get("trade_date"), "trade", "⇄", f'{nm} traded {orgs}', key,
                tr.get("to_org") or org, name=nm, val=orgs, weight=90)
        il = p.get("il_status") or {}
        if il.get("is_on_il") and il.get("since"):
            il_label = f'{il.get("type", "")} IL'.strip()
            add(il.get("since"), "il", "✚", f'{nm} to {il_label}', key, org,
                name=nm, val=il_label, weight=70)
    _save_wire_fv_ledger(fv_ledger, {p.get("player_key") for p in players})
    for g in graduates:
        add(g.get("debut_date"), "debut", "★", f'{g.get("player_name", "")} debuted · {g.get("org", "")}',
            g.get("player_key"), g.get("org"),
            name=g.get("player_name") or "", val="debut", weight=100)
    # Free-agency winter events (signings / option resolutions / QOs) from
    # the FA module's export. "fa:"-prefixed keys route to /fa/, never to a
    # PROSPX player page; the signing org carries the logo.
    for e in (fa_events or []):
        nm = e.get("name") or ""
        key = f'fa:{e.get("key", "")}'
        t = e.get("type")
        if t == "signing":
            terms = ("MiLB deal" if e.get("milb")
                     else f'{e.get("years", "?")}y/${(e.get("guar") or 0) / 1e6:.0f}M')
            add(e.get("date"), "signing", "✎", f'{nm} signs · {e.get("to", "?")} {terms}',
                key, e.get("to"), name=nm, val=terms, weight=95)
        elif t == "option_declined":
            add(e.get("date"), "signing", "✎", f'{nm} declines option - enters FA class',
                key, e.get("from"), name=nm, val="opt-out → FA", weight=85)
        elif t == "option_exercised":
            add(e.get("date"), "signing", "✎", f'{nm} option exercised - off the FA board',
                key, e.get("from"), name=nm, val="option exercised", weight=85)
        elif t == "qo_offered":
            add(e.get("date"), "signing", "✎", f'{nm} receives qualifying offer',
                key, e.get("from"), name=nm, val="QO offered", weight=84)
    # TJStats board movers are intentionally NOT folded into the wire/ticker
    # (owner ask 2026-06-13). tjstats.export_movers still writes the movers
    # sidecar + source events for the consensus; only the wire display drops.
    by_day: dict[str, list] = {}
    for it in fv_items:
        by_day.setdefault(it[0], []).append(it)
    for day, items in by_day.items():
        # Re-grades lead the day's slots; floor steps follow, so a 20-point
        # floor crossing never pushes a real re-grade out of the per-day cap.
        items.sort(key=lambda t: (t[6], -abs(t[1])))
        for d8, step, nm, key, org, unit, floor in items[:_WIRE_MAX_FV_PER_DAY]:
            up = step > 0
            if floor:
                val = "off eFV floor" if up else "to eFV floor"
                weight = 1
            else:
                val = f'{"+" if up else ""}{step} {unit}'
                weight = abs(step)
            add(d8, "up" if up else "down", "▲" if up else "▼",
                f'{nm} {"▲" if up else "▼"} {val}', key, org,
                name=nm, val=val, weight=weight)
    ev.sort(key=lambda e: (e[0], e[8]), reverse=True)
    return [e[:8] for e in ev]

# Event type -> coarse filter category for the /news/ page filter chips.
_EVENT_CAT = {"debut": "debut", "trade": "trade", "promo": "move", "demo": "move",
              "il": "il", "up": "fv", "down": "fv", "signing": "signing"}

def _feed_day_header(dt: str, gfx: bool = False) -> str:
    """One thin date header row that deep-links into Time Machine at that date
    (the full board as of that day). Shared by the homepage feed + /news/.
    gfx=True (the /news/ page only) adds a per-date Generate GFX chip that
    renders THAT day's items - all of them - as a shareable card (the
    data-gfx-date delegation in _NEWS_GFX_JS wires it to the shared engine)."""
    ts = f"{dt[5:7]}/{dt[8:10]}" if len(dt) >= 10 else dt
    btn = ""
    if gfx and len(dt) >= 10:
        md = f"{int(dt[5:7])}/{int(dt[8:10])}"
        btn = (f'<button class="chip egfx-chip egfx-day-chip" type="button" data-gfx-date="{dt}" '
               f'title="Generate a shareable graphic of every news item from {dt}">'
               f'<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>GFX {md}</button>')
    return (f'<div class="feed-day"><span class="feed-day-date">{ts}</span>'
            f'{btn}'
            f'<a class="feed-day-tm" href="/prospx/#tab=timemachine&tm={dt}" '
            f'title="Time Machine - the full board as of {dt}">Time Machine →</a></div>')

def _feed_item_html(typ, glyph, text, key, org, name, val, cat: str = "") -> str:
    """One wire row: logo | name (ellipsized) | colored value chip. The type
    glyph lives only in the value chip. `cat` (optional) tags the row for the
    /news/ filter chips. Shared by the homepage feed + the /news/ page."""
    logo = _team_logo(org, "feed-logo") if org else ""
    data_cat = f' data-cat="{html.escape(cat)}"' if cat else ""
    return (f'<a class="feed-item" href="{_player_href(key)}"{data_cat}>'
            f'{logo}<span class="feed-name">{html.escape(name or text)}</span>'
            f'<span class="feed-val {typ}">{_wire_glyph(typ, glyph)}{html.escape(val)}</span></a>')

def _news_detail(p: dict, typ: str) -> str:
    """Scouting line under a player's name on the /news/ page: position, age,
    overall rank, and ETA - or career WAR for a debut. Empty when the event has
    no resolved player record (e.g. FA signings, keyed off the PROSPX map)."""
    if not p:
        return ""
    parts = []
    if p.get("position"):
        parts.append(_pos_label(p["position"]))
    if p.get("age") is not None:
        parts.append(f'{p["age"]:.1f} yo')
    if p.get("overall_rank"):
        parts.append(f'#{int(p["overall_rank"])}')
    if typ == "debut":
        cw = p.get("career_war")
        war = cw.get("career_war") if isinstance(cw, dict) else cw
        if war is not None and abs(war) >= 0.1:  # skip the +0.0 of a fresh debut
            parts.append(f"{war:+.1f} career WAR")
    else:
        yr = (p.get("eta") or {}).get("year")
        if yr:
            parts.append(f"ETA {yr}")
    return _meta(*parts)

def _news_item_html(typ, glyph, text, key, org, name, val, cat, pmap) -> str:
    """Richer /news/ row: logo | name + scouting line | current-FV chip | event
    chip. Reuses _feed_item_html's classes so it inherits the wire palette; the
    detail line + FV pill are scoped to .news-feed in CSS, so the homepage
    sidebar wire is untouched. `pmap` maps player_key -> record (players +
    graduates); rows with no match (FA signings) degrade to the plain layout."""
    logo = _team_logo(org, "feed-logo") if org else ""
    data_cat = f' data-cat="{html.escape(cat)}"' if cat else ""
    p = pmap.get(key) if pmap else None
    detail = _news_detail(p, typ)
    meta = f'<span class="news-meta">{detail}</span>' if detail else ""
    fv = _fv_pill(p) if (p and p.get("fv_close") is not None) else ""
    return (f'<a class="feed-item news-item" href="{_player_href(key)}"{data_cat}>'
            f'{logo}'
            f'<span class="news-main"><span class="feed-name">{html.escape(name or text)}</span>{meta}</span>'
            f'{fv}'
            f'<span class="feed-val {typ}">{_wire_glyph(typ, glyph)}{html.escape(val)}</span></a>')

def _feed_html(events: list, n: int = 12) -> str:
    # Day-grouped wire (homepage sidebar): a thin per-date header carries the
    # timestamp + Time Machine link; rows are structured logo|name|value chip.
    out = []
    last_day = None
    for dt, typ, glyph, text, key, org, name, val in events[:n]:
        if dt != last_day:
            last_day = dt
            out.append(_feed_day_header(dt))
        out.append(_feed_item_html(typ, glyph, text, key, org, name, val))
    return "".join(out)

def _ticker_html(events: list, n: int = 14) -> str:
    # Each item is a mouse-clickable link to the player (or spotlights), color-
    # coded by type. tabindex=-1 keeps it out of the keyboard/AT path - the
    # ticker is aria-hidden decoration; the sidebar Prospect Wire feed is the
    # accessible, keyboard-navigable equivalent.
    items = []
    known = ("up", "down", "promo", "demo", "il", "debut", "trade", "signing")
    for dt, typ, glyph, text, key, org, name, val in events[:n]:
        cls = typ if typ in known else "glyph"
        href = _player_href(key) if key else "/prospx/#tab=spotlights"
        logo = _team_logo(org, "tk-logo") if org else ""
        items.append(f'<a href="{html.escape(href)}" tabindex="-1">{logo}'
                     f'<span class="{cls}">{_wire_glyph(typ, glyph)}</span> {html.escape(text)}</a>')
    if not items:
        items = ['<span><span class="glyph">◆</span> PROSPX - live prospect wire</span>']
    return " ".join(items * 2)  # duplicated for seamless scroll

def _news_recent_events(events: list, window_days: int = 30,
                        max_items: int = 500, min_items: int = 60) -> list:
    """The /news/ page's event window: recent activity, falling back to the
    most-recent `min_items` when the window is sparse (off-season). Shared by
    the rendered feed and the Generate GFX data blob so the graphic always
    digests exactly the feed the reader is looking at."""
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    recent = [e for e in events if e[0] >= cutoff]
    if len(recent) < min_items:
        recent = events[:min_items]
    return recent[:max_items]

def _news_feed_html(events: list, pmap: dict | None = None) -> str:
    """Day-grouped feed for the standalone /news/ page: a richer row than the
    homepage sidebar (name + scouting line + current-FV chip), windowed to
    recent activity and tagged with data-cat so the filter chips can show/hide
    by category. Each day is wrapped in a .news-day block so a filtered-empty
    day hides cleanly. `pmap` resolves player_key -> record for the detail."""
    recent = _news_recent_events(events)
    out = []
    last_day = None
    open_day = False
    for dt, typ, glyph, text, key, org, name, val in recent:
        if dt != last_day:
            if open_day:
                out.append("</div>")
            last_day = dt
            out.append('<div class="news-day">')
            out.append(_feed_day_header(dt, gfx=True))
            open_day = True
        out.append(_news_item_html(typ, glyph, text, key, org, name, val,
                                   _EVENT_CAT.get(typ, ""), pmap))
    if open_day:
        out.append("</div>")
    return "".join(out)

# Tiny dependency-free filter for the /news/ chips: toggles row visibility by
# data-cat and hides any day block left with no visible items (mirrors the
# glossary/FA static-page chip idiom).
_NEWS_FILTER_JS = """<script>
(function(){
  var bar=document.getElementById('news-filter-bar'),feed=document.getElementById('news-feed');
  if(!bar||!feed)return;
  var empty=null;
  bar.addEventListener('click',function(e){
    var b=e.target.closest('[data-news-filter]');if(!b)return;
    var f=b.getAttribute('data-news-filter');
    bar.querySelectorAll('[data-news-filter]').forEach(function(x){x.classList.toggle('active',x===b);});
    var shown=0;
    feed.querySelectorAll('.news-day').forEach(function(day){
      var any=false;
      day.querySelectorAll('.feed-item').forEach(function(it){
        var show=(f==='all')||it.getAttribute('data-cat')===f;
        it.style.display=show?'':'none';if(show){any=true;shown++;}
      });
      day.style.display=any?'':'none';
    });
    if(!empty){
      empty=document.createElement('div');
      empty.className='news-empty';
      empty.style.cssText='padding:2rem 1rem;text-align:center;color:var(--text-tertiary,#888);';
      feed.appendChild(empty);
    }
    if(shown===0){empty.textContent='No items in this category.';empty.style.display='';}
    else{empty.style.display='none';}
  });
})();
</script>"""

# Server-rendered "Generate GFX" chip - mirrors EEPHUS_GFX.chipHTML() (the
# engine loads deferred, so the static page ships the chip itself and the
# inline wire-up below just listens for the click).
def _gfx_chip_html(chip_id: str) -> str:
    return (f'<button class="chip egfx-chip" id="{chip_id}" type="button" '
            'title="Generate a shareable graphic (theme-aware, multiple formats)">'
            '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button>')

def _news_gfx_blob(recent: list, pmap: dict, max_events: int | None = None) -> str:
    """The /news/ Generate GFX data model: the current feed's events as a
    compact JSON list of {date, typ, glyph, name, pos, org, val, mlbam?,
    pctx?, logo?}, embedded as an inert application/json script the digest
    AND per-date specs read client-side. Carries the SAME windowed list the
    rendered feed shows (the per-date card contract: every item from that
    date, nothing silently dropped), so no cap beyond the feed's own window.
    mlbam + pctx let the client rebuild the resolved headshot URL (the
    _headshot_url chain). pctx carries ALL THREE resolver verdicts, including
    'none': the client needs to tell "no photo on file" apart from "not resolved
    yet" so it can emit no URL at all for the former rather than fetch a
    known-404. Absent pctx = unresolved, and the client asks the '67' set.
    logo is the org's ESPN CDN logo slug."""
    items = []
    for dt, typ, glyph, text, key, org, name, val in (
            recent if max_events is None else recent[:max_events]):
        p = pmap.get(key) or {}
        it = {"date": dt, "typ": typ, "glyph": glyph,
              "name": name or text, "pos": _pos_label(p.get("position")),
              "org": org or "", "val": val}
        mlbam = p.get("mlbam_id")
        if mlbam:
            it["mlbam"] = mlbam
            ctx = _PHOTO_CTX.get(str(mlbam))
            if ctx in ("67", "milb", "none"):
                it["pctx"] = ctx
        if org and org in ESPN_SLUGS:
            it["logo"] = ESPN_SLUGS[org]
        items.append(it)
    blob = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    # "</" would terminate the script element mid-blob; the JSON-safe escape keeps it inert.
    return ('<script type="application/json" id="news-gfx-data">'
            + blob.replace("</", "<\\/") + "</script>")

# Inline wire-up for the /news/ Generate GFX affordances: the header chip
# builds the whole-digest board spec; each date header's "GFX m/d" chip builds
# a per-date card spec (kind:"newsday") that renders EVERY item from that date
# with headshots + team logos and each event's wire pictogram (the canvas
# painter, PX-18, with the text glyph as its fallback). Both read the embedded data blob and hand off
# to the shared EEPHUS_GFX engine (same modal the FA / Projections surfaces
# use). Twitter-card 1200px width; the per-date card grows taller as needed.
_NEWS_GFX_JS = """<script>
(function(){
  var el=document.getElementById('news-gfx-data'),evs=[];
  try{evs=JSON.parse(el?el.textContent:'[]')||[];}catch(e){}
  var TYPE={debut:'Debut',trade:'Trade',promo:'Promo',demo:'Demo',il:'IL',
            up:'Grade up',down:'Grade down',signing:'Signing'};
  var CLR={up:'pos',down:'neg',il:'neg',debut:'accent'};
  var CDN='https://img.mlbstatic.com/mlb-photos/image/upload/';
  // SQUARE face crop, 2026-08-05. renderNewsDay (eephus-gfx.js) draws this into
  // an SxS box with drawImage, which has no object-fit, so a 480x720 source was
  // arriving VERTICALLY SQUASHED - the CONTRACT note there says the fix belongs
  // at this supplier, and this is that supplier. S = rowH-12 over the fit
  // ladder's 40..58px rows, so 46px is the largest box; at the engine's 2x
  // supersample that is 92 device px, and 96 covers it (the width the plain
  // form already asked for). c_fill returns exactly the box, g_face centres it
  // on the detected face. Verified live on both contexts, ACAO:* intact, so the
  // crop stays canvas-export-safe.
  // No d_people:generic: it answers 200 with a silhouette, which would draw a
  // squashed grey outline that no fallback can detect. pctx 'none' means the
  // resolver checked and there is no photo - return null and let the renderer
  // draw its initials disc instead of fetching a known-404.
  function shotURL(e){
    if(!e.mlbam||e.pctx==='none')return null;
    var seg=(e.pctx==='67'||e.pctx==='milb')?e.pctx:'67';
    return CDN+'c_fill,g_face,w_96,h_96,q_auto:best/v1/people/'+e.mlbam+'/headshot/'+seg+'/current';
  }
  function logoURL(e){
    return e.logo?'https://a.espncdn.com/i/teamlogos/mlb/500/'+e.logo+'.png':null;
  }
  function mdOf(d){return d.length>=10?(+d.slice(5,7))+'/'+(+d.slice(8,10)):d;}
  function _newsDigestSpec(){
    var rows=evs.map(function(e){
      var sub=[e.pos,e.org].filter(Boolean).join(' - ');
      return {cells:[
        {t:mdOf(String(e.date||''))},
        {t:TYPE[e.typ]||e.typ||''},
        {t:e.name||'',sub:sub},
        {t:(e.glyph?e.glyph+' ':'')+(e.val||''),c:CLR[e.typ]}
      ]};
    });
    var now=new Date();
    var mon=now.toLocaleDateString('en-US',{month:'short',day:'numeric'});
    var iso=now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+
            String(now.getDate()).padStart(2,'0');
    return {kind:'board',module:'Prospect News',accentToken:'--accent-lilac',
      title:'Prospect News - '+mon,
      subtitle:evs.length+' moves - debuts, trades, promos, FV',
      url:'eephus.io/news',filenameBase:'prospect-news-'+iso,format:'twitter',
      board:{defaultCount:25,counts:[10,25,50],columns:[
        {label:'Date',frac:0.10},
        {label:'Type',frac:0.15},
        {label:'Player',frac:0.45},
        {label:'Event',frac:0.30}
      ],rows:rows}};
  }
  function _newsDaySpec(day){
    var items=evs.filter(function(e){return String(e.date||'').slice(0,10)===day;})
      .map(function(e){
        return {name:e.name||'',sub:[e.pos,e.org].filter(Boolean).join(' - '),
                type:TYPE[e.typ]||e.typ||'',
                val:e.val||'',glyph:e.glyph||'',ico:TYPE[e.typ]?'ev-'+e.typ:'',c:CLR[e.typ]||null,
                shot:shotURL(e),logo:logoURL(e)};
      });
    var dt=new Date(day+'T12:00:00');
    var lbl=isNaN(+dt)?day:dt.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
    return {kind:'newsday',module:'Prospect News',accentToken:'--accent-lilac',
      title:'Prospect News - '+lbl,dateLabel:lbl,
      subtitle:items.length+(items.length===1?' update':' updates')+' - every move from this date',
      url:'eephus.io/news',filenameBase:'prospect-news-'+day,items:items};
  }
  var chip=document.getElementById('news-gfx-chip');
  if(chip)chip.addEventListener('click',function(){
    if(window.EEPHUS_GFX)window.EEPHUS_GFX.open(_newsDigestSpec());
  });
  var feed=document.getElementById('news-feed');
  if(feed)feed.addEventListener('click',function(ev){
    var b=ev.target.closest('[data-gfx-date]');
    if(b&&window.EEPHUS_GFX)window.EEPHUS_GFX.open(_newsDaySpec(b.getAttribute('data-gfx-date')));
  });
})();
</script>"""

def build_news(data: dict | None = None) -> str:
    """/news/ - the expanded Prospect News page: the full recent event feed
    (debuts, trades, promotions/demotions, IL, FV grade changes, FA signings),
    day-grouped with category filter chips. Same event pipeline + row markup as
    the homepage sidebar feed, just a wider window. Reached by clicking the
    Prospect News header (sidebar feed or top ticker) on the homepage."""
    data = data or load_site_data() or {}
    events = _collect_events(data.get("players") or [], data.get("graduates") or [],
                             _load_fa_events_for_wire())
    # player_key -> record, so each row can carry the player's current FV chip
    # and scouting line. Active prospects win ties; graduates fill the debuts.
    pmap: dict = {}
    for p in (data.get("players") or []):
        if p.get("player_key"):
            pmap[p["player_key"]] = p
    for g in (data.get("graduates") or []):
        if g.get("player_key") and g["player_key"] not in pmap:
            pmap[g["player_key"]] = g
    feed = _news_feed_html(events, pmap)
    recent = _news_recent_events(events)
    chip_defs = [("all", "All"), ("debut", "Debuts"), ("trade", "Trades"),
                 ("move", "Moves"), ("il", "IL"), ("fv", "Grades"), ("signing", "Signings")]
    chips = "".join(
        f'<button class="chip{" active" if c == "all" else ""}" '
        f'data-news-filter="{c}">{html.escape(lbl)}</button>'
        for c, lbl in chip_defs)
    body = (
        '<div class="news-app">'
        f'<div class="section-head"><h1>{_masthead_icon("news")}Prospect News</h1>'
        '<span class="section-sub">debuts, trades, level moves, IL, eFV changes and FA signings</span>'
        f'{_gfx_chip_html("news-gfx-chip")}</div>'
        f'<p class="news-intro">The {_gl("wire_ticker", "wire")}, last ~30 days, newest first. '
        'Grade rows show eFV moves of 2 or more; a row reading &quot;to eFV floor&quot; or &quot;off eFV floor&quot; is the player reaching or leaving the model floor, not a re-grade. A date header opens Time Machine on that date.</p>'
        f'<div class="filter-bar" id="news-filter-bar"><span class="filter-label">Filter</span>{chips}</div>'
        f'<div class="sb-feed news-feed" id="news-feed">{feed}</div>'
        '</div>'
        # Page-scoped sizing for the per-date GFX chips (site.css owns the base
        # .chip/.egfx-chip look; this only shrinks them into the thin day rows).
        '<style>.news-feed .feed-day{gap:10px;}'
        '.news-app .news-feed button.chip.egfx-day-chip{margin-left:auto;font-size:10px;'
        'padding:2px 8px;line-height:1.5;}</style>'
        + _news_gfx_blob(recent, pmap)
        + _NEWS_FILTER_JS
        + _NEWS_GFX_JS
        # Shared Generate GFX engine (same two-script injection as /fa/).
        + f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        + f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
    )
    return page("Prospect News - eephus.io", "news", body,
                "The eephus.io prospect wire: debuts, trades, promotions, IL moves, eFV grade "
                "changes and Free Agency signings, filterable by type.",
                url=f"{SITE_ORIGIN}/news/")

def _fv_step_runs(n: int, w: int) -> list:
    """Integer [x0, x1) column spans for n board snapshots across w pixels.
    With n <= w every snapshot owns one run of whole pixels (the widths differ
    by at most 1 px, so the line fills the box); with more snapshots than
    pixels each pixel column shows the snapshot standing at its left edge."""
    if n <= w:
        return [(i, i * w // n, (i + 1) * w // n) for i in range(n)]
    return [(x * n // w, x, x + 1) for x in range(w)]


def _fv_sparkline(points: list, color: str, w: int = 150, h: int = 34) -> str:
    """The consensus FV history as a pixel STEP line (final-pass plan 5.7,
    PX-16, V3). Board snapshots are discrete, so each value is held flat until
    the next board rather than interpolated between them: one 2 px run per
    snapshot, a 2 px riser where the grade changed. The dotted rules are the
    grade lines at every multiple of 5 inside the band, so a reader sees which
    band the line crossed without an axis. Every coordinate is a whole pixel
    and the box is drawn at its own w x h (integer), so nothing is resampled."""
    vals = [pt.get("consensus_fv_raw") for pt in (points or []) if pt.get("consensus_fv_raw") is not None]
    if len(vals) < 2:
        return ""
    w, h = int(w), int(h)
    lo = math.floor(min(vals) / 5) * 5 - 2.5
    hi = math.ceil(max(vals) / 5) * 5 + 2.5
    k = (h - 2) / (hi - lo)

    def y_of(v: float) -> int:
        return int(round((hi - v) * k))

    rules = []
    g = math.ceil(lo / 5) * 5
    while g <= hi:
        rules.append("".join(f"M{x} {y_of(g)}h1v1h-1z" for x in range(0, w, 2)))
        g += 5
    runs = [[x0, x1, y_of(vals[i])] for i, x0, x1 in _fv_step_runs(len(vals), w)]
    if len(vals) > w:  # one run per pixel column: merge the flat stretches
        merged = [runs[0]]
        for r in runs[1:]:
            if r[2] == merged[-1][2]:
                merged[-1][1] = r[1]
            else:
                merged.append(r)
        runs = merged
    ink, prev = [], None
    for x0, x1, y in runs:
        if prev is not None and prev != y:
            a, b = sorted((prev, y))
            ink.append(f"M{max(x0 - 1, 0)} {a}h2v{b - a + 2}h-2z")
        ink.append(f"M{x0} {y}h{x1 - x0}v2h-{x1 - x0}z")
        prev = y
    return (f'<svg class="px-spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<path class="gl" d="{"".join(rules)}"/>'
            f'<path class="ln" fill="{color}" d="{"".join(ink)}"/></svg>')

def _spotlight_card(label: str, p: dict, chip: str, spark_color: str) -> str:
    """ONE spotlight card - the baseball-card markup every rotation slot shares.
    `label` is the sb-group caption, `chip` the ready-made status chip that sits
    beside the FV pill. Split out of _spotlight_html so riser / faller /
    hot-sample are byte-identical in structure and only the caption, the chip and
    the sparkline colour differ."""
    # Tier the holo border off the DISPLAYED integer, matching _fv_pill (a raw
    # threshold here disagreed with the pill rendered inside the same card).
    holo = " holo" if "holo" in _fv_tier_class(_fv_label(p)) else ""
    # .spotlight .sp-photo is an 84x128 well (site.css); ask the CDN for exactly
    # that, face-centred, instead of letting `background: center top/cover` guess
    # where the face sits in a 480x720 source.
    url = _headshot_url(p.get("mlbam_id"), 84, 128)   # unified chain (resolves milb-only ids)
    photo = f"background-image:url('{url}');" if url else ""
    # 120 x 34: the card's text column is about 123 px wide at the 292 px
    # sidebar, so the pixel step line draws at its own size, never scaled.
    spark = _fv_sparkline(p.get("points"), spark_color, w=120, h=34)
    return (
        f'<div class="sb-group"><div class="sb-group-label">{html.escape(label)}</div>'
        f'<a class="spotlight{holo}" href="{_player_href(p.get("player_key"))}" style="text-decoration:none;color:inherit;">'
        f'<div class="sp-photo" style="{photo}"></div>'
        '<div style="flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center;gap:2px;">'
        f'<div class="sp-name">{html.escape(p.get("player_name") or "")}</div>'
        f'<div class="sp-meta">{_meta(_pos_label(p.get("position")), p.get("org"))}</div>'
        # flex-wrap + nowrap chip: under the wide MS-Gothic metrics the pill +
        # delta can outgrow the narrow sidebar column - wrap the chip as a unit
        # below the pill instead of letting it overflow into the card border.
        f'<div style="display:flex;align-items:center;gap:8px;row-gap:2px;margin-top:4px;flex-wrap:wrap;">{_fv_pill(p)}'
        f'{chip}</div>'
        f'{spark}</div></a></div>'
    )

def _spotlight_html(players: list, spotlights: dict | None = None) -> str:
    """Sidebar spotlight, ROTATED by day-of-year across the movement engine's
    three published buckets instead of always showing the same Top Riser.

    Slot 1 (Top Riser) and slot 2 (Top Faller) come from `_genuine_mover_step` -
    the de-noised genuine grade move, the same selector the Top Movers module
    uses - so the "+N eFV" / "-N eFV" caption (FV on the consensus fallback)
    names the grade that moved and the hero card never disagrees with the
    movers list or the per-player stock chips. Floor crossings are left out,
    as on Top Movers (_mover_at_floor).
    Slot 3 (Hot Sample) is the engine's own performance bucket
    (timeseries.spotlights.hot, the alias of `risers` guarded by
    test_spotlights_three_buckets), captioned with that entry's published stat
    line rather than a grade step - the bucket is scored on performance, so
    printing an FV delta there would be a category error.

    Deterministic per day (tm_yday), and the rotation only ever contains slots
    that actually resolved, so a thin data day silently shows whatever exists
    rather than an empty rail. Returns "" only when NO slot fills."""
    steps = [(d, p) for p in players
             if p.get("status") != "debuted"
             and (d := _genuine_mover_step(p)) is not None
             and not _mover_at_floor(p)]
    chip_style = "font-family:var(--font-retro-mono);font-size:12px;white-space:nowrap;"
    slots: list[tuple[str, dict, str, str]] = []

    risers = [t for t in steps if t[0] > 0]
    if risers:
        d, p = max(risers, key=lambda t: t[0])
        slots.append(("Spotlight - Top Riser", p,
                      f'<span class="row-delta up" style="{chip_style}">▲ +{d} {_mover_unit(p)}</span>',
                      "var(--accent-green)"))
    fallers = [t for t in steps if t[0] < 0]
    if fallers:
        d, p = min(fallers, key=lambda t: t[0])
        # d is already negative, so it carries its own sign - never print "+-3".
        slots.append(("Spotlight - Top Faller", p,
                      f'<span class="row-delta down" style="{chip_style}">▼ {d} {_mover_unit(p)}</span>',
                      "var(--accent-red)"))

    # Hot sample: the top entry of the engine's performance bucket that still
    # resolves to a player on the board (an entry whose player left the pool is
    # skipped, not rendered as a dead card).
    bucket = (spotlights or {}).get("hot") or (spotlights or {}).get("risers") or []
    if bucket:
        by_key = {p.get("player_key"): p for p in players}
        for e in bucket:
            p = by_key.get((e or {}).get("player_key"))
            line = (e or {}).get("line")
            if not p or not line:
                continue
            why = (e or {}).get("why") or "Hot sample"
            slots.append((
                "Spotlight - Hot Sample", p,
                # .row-delta is flex:none + min-width:46px + text-align:right,
                # so white-space:normal alone never wrapped: a flex item that
                # cannot shrink is laid out at max-content even on its own flex
                # line, and a 26-char statline pushed through the card border of
                # the ~124px sidebar text column. flex:1 1 100% + min-width:0
                # give the statline its own full-width row under the FV pill.
                f'<span class="row-delta up" title="{html.escape(str(why))} - current-season sample" '
                f'style="font-family:var(--font-retro-mono);font-size:11px;white-space:normal;'
                f'flex:1 1 100%;min-width:0;text-align:left;">'
                f'{html.escape(str(line))}</span>',
                "var(--accent-green)"))
            break

    if not slots:
        return ""
    label, p, chip, color = slots[datetime.now().timetuple().tm_yday % len(slots)]
    return _spotlight_card(label, p, chip, color)

# Homepage teaser rotation - curated Arkmetrics showcase. The phrases are
# label expansions (hints), not definitions; the canonical entry lives in
# data/glossary.json and the link deep-links it by slug.
_GLOSSARY_TERMS = [
    ("dvm_plus", "DvM+", "development vs. mean"),
    ("tvi", "Sur+", "FV-implied surplus value"),
    ("rps_plus", "RPS+", "rate performance vs. same-age peers"),
    ("statcast_plus", "SC+", "Statcast composite"),
    ("wag", "WAG", "WAR above grade"),
    ("tool", "Tool+", "20-80 tool composite"),
]

# The teaser used to rotate the six hardcoded pairs above out of the 285 real
# entries in data/glossary.json, so 279 of them were unreachable from the
# homepage and the six drifted from their canonical definitions. It now rotates
# the REAL Arkmetrics shelf (the `custom-index` + `farm` categories, which
# glossary.json's own `groups` map calls "Arkmetrics" - the same grouping
# /glossary/ renders), keyed by day-of-year exactly as before.
_GLOSSARY_TEASER_GROUP = "Arkmetrics"

def _glossary_hint(text: str, limit: int = 76) -> str:
    """A one-line hint from a canonical definition: first sentence, clipped at a
    WORD boundary. The teaser slot is a single narrow line, and the real entries
    run to ~250 characters."""
    s = " ".join(str(text or "").split())
    # First sentence, but only when the period really ends one ("2.5 WAR" and
    # "vs. peers" must not split the line).
    m = re.search(r"(?<=[a-z0-9)\]])\.(?=\s+[A-Z(])", s)
    if m:
        s = s[:m.start()]
    if len(s) > limit:
        cut = s[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
        s = (cut or s[:limit]) + "…"
    return s

@functools.lru_cache(maxsize=1)
def _glossary_teaser_terms() -> tuple:
    """(slug, term, hint) for every Arkmetrics entry, ordered by slug so the
    day-of-year rotation is STABLE across rebuilds (glossary.json's entry order
    is a build artifact and must not be allowed to reshuffle the calendar).
    Falls back to the curated six when the file is missing or has no group."""
    doc = _cached_data_json("glossary.json")
    groups = doc.get("groups") or {}
    out = []
    for e in (doc.get("entries") or []):
        e = e or {}
        if groups.get(e.get("category")) != _GLOSSARY_TEASER_GROUP:
            continue
        slug, term, defn = e.get("id"), e.get("term"), e.get("definition")
        if slug and term and defn:
            out.append((str(slug), str(term), _glossary_hint(defn)))
    out.sort(key=lambda t: t[0])
    return tuple(out) or tuple(_GLOSSARY_TERMS)

def page_home(title: str, inner: str, description: str = "") -> str:
    desc = html.escape(description or "eephus.io - sabermetrics")
    social = _social_meta(title, description or "eephus.io - sabermetrics",
                          url=f"{SITE_ORIGIN}/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
{social}
{FAVICON_LINKS}
<link rel="stylesheet" href="/assets/site.css?v={_CSS_VER}">
{ACCOUNT_CSS_LINK}
</head>
<body class="eephus-page eephus-home">
{inner}
{_footer()}
{ACCOUNT_SCRIPTS}
</body>
</html>
"""

def _home_module(kicker: str, see_all_href: str, see_all: str, body: str, full: bool = False) -> str:
    head = (f'<div class="kicker"><h2>{html.escape(kicker)}</h2>'
            f'<a class="see-all" href="{see_all_href}">{html.escape(see_all)} →</a></div>')
    return f'<section class="home-module{" full" if full else ""}">{head}{body}</section>'

def _debut_org(g: dict) -> str | None:
    """Org the player DEBUTED with - point-in-time, never the current org.
    Primary source: the debut-season MLB stat row (its first org is the debut
    org by construction - the first MLB appearance IS the debut). If that exact
    season isn't retained in career_stats (older debuts get trimmed - e.g.
    Alzolay debuted 2019 with CHC but career_stats starts 2021, still CHC,
    while his current org is NYM), use the EARLIEST retained MLB season as the
    proxy - far closer to the debut than the current org. Only when there are
    no MLB stat rows at all do we fold the trade history back from the current
    org. Mirrors the career-table rule: a historical event never silently
    wears the current org."""
    dd = str(g.get("debut_date") or "")[:10]
    if not dd:
        return g.get("org")
    try:
        debut_year = int(dd[:4])
    except ValueError:
        return g.get("org")

    def _row_org(row: dict) -> str | None:
        stints = [s for s in (row.get("stints") or []) if s.get("org")]
        return stints[0]["org"] if stints else row.get("org")

    mlb_rows = [r for r in (g.get("career_stats") or [])
                if str(r.get("level") or "") == "MLB" and r.get("season") is not None]
    # Exact debut-season row - the first MLB appearance IS the debut.
    for row in mlb_rows:
        if row.get("season") == debut_year:
            o = _row_org(row)
            if o:
                return o
    # Debut season trimmed: the earliest retained MLB season is the best proxy.
    if mlb_rows:
        o = _row_org(min(mlb_rows, key=lambda r: r["season"]))
        if o:
            return o
    # No MLB stat rows at all: unwind post-debut trades from the current org.
    org = g.get("org")
    for tr in sorted((g.get("trades") or []), key=lambda t: t.get("trade_date") or "", reverse=True):
        td = str(tr.get("trade_date") or "")[:10]
        if td and td > dd:
            org = tr.get("from_org") or org
        else:
            break
    return org

def _wag_badge(g: dict) -> str:
    """A graduate's WAG (WAR Above Grade) as a signed, color-classed chip -
    how the player has performed against their FV-implied expectation. Gated
    on the WAG model's own meaningful-exposure flag (the same gate
    display_metric_for() uses), so a thin sample shows nothing rather than a
    misleading number. Returns "" when there's no settled WAG to show."""
    wag = (g.get("debuted_value") or {}).get("wag") or {}
    rw = wag.get("regressed_wag")
    if rw is None or wag.get("below_meaningful_exposure"):
        return ""
    wag_r = round(rw, 1) + 0.0                # collapse -0.0
    cls = "up" if wag_r > 0 else ("down" if wag_r < 0 else "flat")
    sign = "+" if wag_r > 0 else ""           # negatives carry their own '-'; zero unsigned
    return (f'<span class="otd-wag row-delta {cls}" '
            f'title="WAR Above Grade - career WAR/yr vs the player\'s FV-implied expectation">'
            f'{sign}{wag_r:.1f} WAG</span>')


def _otd_date(d: "date") -> str:
    """Compact numeric mono date stamp for the This Day rows: "6/20/15".
    Replaces the verbose "June 20, 2015" + separate "Ny ago" tag (the
    two-digit year already says how long ago it was), tightening each row."""
    return f"{d.month}/{d.day}/{d.strftime('%y')}"


def _otd_debut_row(g: dict, d: "date", data_cat: str = "") -> str:
    """One debut-anniversary row (shared by the homepage This Day module and
    the full /history/ page). Shows the org the player DEBUTED with, not where
    they play now - this is a history row. WAG sits LEFT of the FV chip so
    every row's FV chip lines up in the same right-hand column."""
    nm = html.escape(g.get("player_name") or "")
    pos = _pos_label(g.get("position"))
    logo = _team_logo(_debut_org(g), "otd-logo")
    pos_tail = (" · " + html.escape(pos)) if pos else ""
    cat = f' data-cat="{data_cat}"' if data_cat else ""
    return (
        f'<a class="otd-row" href="{_player_href(g.get("player_key"))}"{cat}>'
        f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
        f'<span class="otd-body" title="{nm} debuted{pos_tail}">{logo} <strong>{nm}</strong> debuted{pos_tail}</span>'
        f'{_wag_badge(g)}{_fv_pill(g)}</a>'
    )


def _otd_trade_row(p: dict, tr: dict, d: "date", data_cat: str = "") -> str:
    """One trade-anniversary row (shared by the homepage module and /history/):
    the trade's from->to org logos, point-in-time."""
    nm = html.escape(p.get("player_name") or "")
    pos = _pos_label(p.get("position"))
    logos = (f'{_team_logo(tr.get("from_org"), "otd-logo")}'
             f'<span class="otd-arrow">→</span>'
             f'{_team_logo(tr.get("to_org"), "otd-logo")}')
    pos_tail = (" · " + html.escape(pos)) if pos else ""
    cat = f' data-cat="{data_cat}"' if data_cat else ""
    return (
        f'<a class="otd-row otd-trade" href="{_player_href(p.get("player_key"))}"{cat}>'
        f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
        f'<span class="otd-body" title="→ {nm}{pos_tail} traded">{logos} <strong>{nm}</strong>{pos_tail} traded</span>'
        f'{_fv_pill(p)}</a>'
    )


def _this_day_html(graduates: list, players: list | None = None, n: int = 5) -> str:
    """'This day in prospect history' - graduates who debuted on (or within a
    few days of) today's calendar date in past seasons, plus prospect trades
    that happened on the same calendar date. Up to `n` debut rows, exact-date
    anniversaries first, then by prominence (final FV, then WAG); each row
    carries the player's FV chip and (for debuts) their WAG. Shows the org each
    player DEBUTED with / the trade's from->to orgs (point-in-time, not where
    they play now - this is a history module). Links into Time Machine at the
    lead anniversary date."""
    today = date.today()

    def _anniv_prox(d: "date") -> int | None:
        """Days between `d`'s nearest anniversary and today; None if the
        date is this year/later or doesn't map onto a nearby year (Feb 29).
        Checks the adjacent years too so a late-Dec/early-Jan anniversary
        survives the year boundary; the event date itself never counts
        (a days-old December debut is not history on Jan 1)."""
        if d.year >= today.year:
            return None
        prox = None
        for yr in (today.year - 1, today.year, today.year + 1):
            try:
                anniv = date(yr, d.month, d.day)
            except ValueError:
                continue
            if anniv == d:
                continue
            p = abs((anniv - today).days)
            prox = p if prox is None else min(prox, p)
        return prox if prox is not None and prox <= 4 else None

    # ---- Debuts on this day ----
    cands = []  # (date_proximity, -prominence, debut_date, grad)
    for g in graduates:
        dd = g.get("debut_date")
        if not dd:
            continue
        try:
            d = date.fromisoformat(str(dd)[:10])
        except ValueError:
            continue
        prox = _anniv_prox(d)
        if prox is None:
            continue
        prom = g.get("fv_close") or ((g.get("debuted_value") or {}).get("wag") or {}).get("regressed_wag") or 0
        cands.append((prox, -float(prom), d, g))
    cands.sort(key=lambda c: c[:2])

    rows = [_otd_debut_row(g, d) for _, _, d, g in cands[:n]]

    # ---- Trades on this day ----
    # Aggregate prospect trades across the active board (timeseries) + graduates,
    # deduped by player_key (board wins, it's fresher). Only mlb_api trades carry
    # an exact calendar date, so inferred-date trades are excluded by source.
    entities = {}
    for src in (players or [], graduates):
        for p in src:
            k = p.get("player_key")
            if k and k not in entities:
                entities[k] = p
    trade_cands = []  # (prox, -fv, trade_date, entity, trade)
    for p in entities.values():
        for tr in (p.get("trades") or []):
            if tr.get("source") != "mlb_api":
                continue
            td = str(tr.get("trade_date") or "")[:10]
            try:
                d = date.fromisoformat(td)
            except ValueError:
                continue
            # Trades must fall EXACTLY on today's calendar date (prox == 0),
            # not merely near it - "Trades on this day" means this day.
            prox = _anniv_prox(d)
            if prox != 0:
                continue
            fv = p.get("fv_close") or 0
            trade_cands.append((prox, -float(fv), d, p, tr))
    trade_cands.sort(key=lambda c: c[:2])

    trade_rows = [_otd_trade_row(p, tr, d) for _, _, d, p, tr in trade_cands[:n]]

    if not rows and not trade_rows:
        return ""
    trades_block = (
        f'<div class="otd-subhead">Trades on this day</div>{"".join(trade_rows)}'
        if trade_rows else ""
    )
    return (
        '<section class="home-module otd-module">'
        '<div class="kicker"><h2>Today in Prospect History</h2>'
        '<a class="see-all" href="/history/">See all →</a></div>'
        + "".join(rows) + trades_block +
        '</section>'
    )

# --------------------------------------------------------------------------- #
# /history/ - the full Today in Prospect History page (generalizes the
# homepage This Day module: every exact-date match, plus the prospects.db
# transaction + IL ledgers the homepage never reads).
# --------------------------------------------------------------------------- #

# Transaction codes surfaced on /history/ (MLB StatsAPI type_code values):
# SGN = signed (draft/int'l), SFA = signed as a free agent, DFA = declared
# free agency, TR = trade. Verbs are per-row row copy.
_HIST_TX_CODES = ("SGN", "TR", "DFA", "SFA")
_HIST_TX_VERBS = {"SGN": "signed", "SFA": "signed as a free agent",
                  "DFA": "declared free agency", "TR": "traded"}

# One-pass, once-per-build cache of the prospects.db history ledgers grouped
# by calendar date. ~175k dated transaction events across 7,471 payloads
# group in ~0.3s; il_history is tiny. Module-level so a rebuild that calls
# build_this_day() more than once (tests) never re-reads the DB.
_HIST_DB_CACHE: tuple[dict, dict] | None = None

def _load_history_db() -> tuple[dict, dict]:
    """Group prospects.db player_transactions (SGN/TR/DFA/SFA only) and
    il_history by MM-DD. STRICTLY read-only (file:...?mode=ro) - the build
    must never write the pipeline's DB. Returns
    ({mmdd: [(iso_date, code, player_key, team_name), ...]},
     {mmdd: [(iso_since, player_key, il_type), ...]}); empty dicts when the
    DB is absent (cold checkouts / CI without a seeded DB)."""
    global _HIST_DB_CACHE
    if _HIST_DB_CACHE is not None:
        return _HIST_DB_CACHE
    tx: dict[str, list] = {}
    il: dict[str, list] = {}
    db = ROOT / "prospects.db"
    if db.exists():
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
            try:
                seen: set = set()
                for key, pj in con.execute(
                        "SELECT player_key, payload_json FROM player_transactions"):
                    try:
                        events = json.loads(pj) or []
                    except ValueError:
                        continue
                    for t in events:
                        code = t.get("type_code")
                        if code not in _HIST_TX_CODES:
                            continue
                        dt = str(t.get("date") or "")
                        if len(dt) < 10:
                            continue
                        sig = (key, dt[:10], code)
                        if sig in seen:
                            continue
                        seen.add(sig)
                        team = t.get("to_team_name") or t.get("from_team_name") or ""
                        tx.setdefault(dt[5:10], []).append((dt[:10], code, key, team))
                seen.clear()
                for key, since, il_type in con.execute(
                        "SELECT player_key, since, il_type FROM il_history"):
                    s = str(since or "")
                    if len(s) < 10 or (key, s[:10]) in seen:
                        continue
                    seen.add((key, s[:10]))
                    il.setdefault(s[5:10], []).append((s[:10], key, il_type or ""))
            finally:
                con.close()
        except sqlite3.Error:
            pass
    _HIST_DB_CACHE = (tx, il)
    return _HIST_DB_CACHE

def _org_from_team_name(team: str | None) -> str | None:
    """MLB club abbreviation from a transaction's full team name ("Seattle
    Mariners" -> SEA) via nickname suffix match; None for minor-league
    affiliates / foreign clubs (they get no big-league logo, correctly)."""
    if not team:
        return None
    for abbr, nick in ORG_NAMES.items():
        if team.endswith(nick):
            return abbr
    return None

def _name_from_key(key: str) -> str:
    """Readable fallback name for a DB player_key with no board/graduate
    record ("travis_kuhn" -> "Travis Kuhn"; the "__noid" disambiguator and
    friends are dropped)."""
    base = (key or "").split("__")[0]
    return base.replace("_", " ").title()

# /history/ category filter - same tiny dependency-free idiom as the /news/
# chips (_NEWS_FILTER_JS): toggle .otd-row visibility by data-cat, hide any
# section left with no visible rows.
_HIST_FILTER_JS = """<script>
(function(){
  var bar=document.getElementById('hist-filter-bar'),wrap=document.getElementById('hist-sections');
  if(!bar||!wrap)return;
  var empty=null;
  bar.addEventListener('click',function(e){
    var b=e.target.closest('[data-hist-filter]');if(!b)return;
    var f=b.getAttribute('data-hist-filter');
    bar.querySelectorAll('[data-hist-filter]').forEach(function(x){x.classList.toggle('active',x===b);});
    var shown=0;
    wrap.querySelectorAll('.hist-section').forEach(function(sec){
      var any=false;
      sec.querySelectorAll('.otd-row').forEach(function(it){
        var show=(f==='all')||it.getAttribute('data-cat')===f;
        it.style.display=show?'':'none';if(show){any=true;shown++;}
      });
      sec.style.display=any?'':'none';
    });
    if(!empty){
      empty=document.createElement('div');
      empty.className='news-empty';
      empty.style.cssText='padding:2rem 1rem;text-align:center;color:var(--text-tertiary,#888);';
      wrap.appendChild(empty);
    }
    if(shown===0){empty.textContent='No items in this category.';empty.style.display='';}
    else{empty.style.display='none';}
  });
})();
</script>"""

def build_this_day(data: dict | None = None) -> str:
    """/history/ - Today in Prospect History as a full page: every debut
    anniversary and prospect trade landing on today's exact calendar date
    (past seasons only), plus the prospects.db transaction ledger (signings /
    free agency, 2019+) and IL placements (2017+) for the same MM-DD.

    Big eFV moves are DELIBERATELY not a section: data/xfv_history.json dates
    grade changes at model snapshot re-runs (over half of all |delta| >= 3
    steps share one monthly restamp date), so a calendar-day match would
    misstate when the move actually happened. Revisit if the history ever
    carries first-seen event dates."""
    data = data or load_site_data() or {}
    players = data.get("players") or []
    graduates = data.get("graduates") or []
    today = date.today()
    mmdd = f"{today.month:02d}-{today.day:02d}"
    mon_d = f"{today.strftime('%B')} {today.day}"

    # player_key -> record; active board wins ties, graduates fill the rest
    # (same dedupe the news page + homepage trades use).
    pmap: dict = {}
    for p in players:
        if p.get("player_key"):
            pmap[p["player_key"]] = p
    for g in graduates:
        if g.get("player_key") and g["player_key"] not in pmap:
            pmap[g["player_key"]] = g

    def _is_anniv(d: "date") -> bool:
        # Exact calendar date, past seasons only (the full page never uses the
        # homepage's near-date padding - "on this day" means this day here).
        return d.year < today.year and (d.month, d.day) == (today.month, today.day)

    # ---- Debut anniversaries (every exact match, prominence-ordered) -------
    debut_cands = []
    for g in graduates:
        try:
            d = date.fromisoformat(str(g.get("debut_date") or "")[:10])
        except ValueError:
            continue
        if not _is_anniv(d):
            continue
        prom = g.get("fv_close") or ((g.get("debuted_value") or {}).get("wag") or {}).get("regressed_wag") or 0
        debut_cands.append((-float(prom), d, g))
    debut_cands.sort(key=lambda c: c[0])
    debut_rows = [_otd_debut_row(g, d, data_cat="debut") for _, d, g in debut_cands]

    # ---- Trades on this day (exact-dated mlb_api rows only) ----------------
    trade_cands = []
    for p in pmap.values():
        for tr in (p.get("trades") or []):
            if tr.get("source") != "mlb_api":
                continue
            try:
                d = date.fromisoformat(str(tr.get("trade_date") or "")[:10])
            except ValueError:
                continue
            if _is_anniv(d):
                trade_cands.append((-float(p.get("fv_close") or 0), d, p, tr))
    trade_cands.sort(key=lambda c: c[0])
    trade_rows = [_otd_trade_row(p, tr, d, data_cat="trade") for _, d, p, tr in trade_cands]

    # ---- Transaction ledger (SGN / SFA / DFA / TR) -------------------------
    tx_all, il_all = _load_history_db()
    tx_today = [t for t in tx_all.get(mmdd, []) if int(t[0][:4]) < today.year]
    # Known board/graduate players first (FV-ranked), then the rest of the
    # ledger newest-first; capped - July draft-signing anniversaries alone can
    # run to hundreds of rows.
    tx_today.sort(key=lambda t: t[0], reverse=True)
    tx_today.sort(key=lambda t: (0, -(_primary_fv(pmap[t[2]]) or 0)) if t[2] in pmap else (1, 0))
    TX_CAP = 40
    tx_rows = []
    for dt, code, key, team in tx_today[:TX_CAP]:
        p = pmap.get(key)
        nm = html.escape((p or {}).get("player_name") or _name_from_key(key))
        pos = _pos_label((p or {}).get("position"))
        d = date.fromisoformat(dt)
        verb = _HIST_TX_VERBS.get(code, "moved")
        logo = _team_logo(_org_from_team_name(team), "otd-logo")
        cat = "trade" if code == "TR" else "signing"
        pos_tail = (" · " + html.escape(pos)) if pos else ""
        inner = (f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
                 f'<span class="otd-body" title="{nm} {verb}{pos_tail}">{logo} <strong>{nm}</strong> {verb}'
                 f'{pos_tail}</span>')
        if p:
            tx_rows.append(f'<a class="otd-row" href="{_player_href(key)}" data-cat="{cat}">{inner}{_fv_pill(p)}</a>')
        else:
            tx_rows.append(f'<div class="otd-row" data-cat="{cat}">{inner}</div>')
    if len(tx_today) > TX_CAP:
        tx_rows.append(
            '<div class="otd-more" style="margin:8px 4px;font-family:var(--font-retro-mono);'
            'font-size:11px;color:var(--text-tertiary);">'
            f'+ {len(tx_today) - TX_CAP} more transactions on {html.escape(mon_d)} in the ledger</div>')

    # ---- IL on this day ----------------------------------------------------
    il_today = [t for t in il_all.get(mmdd, []) if int(t[0][:4]) < today.year]
    il_today.sort(key=lambda t: t[0], reverse=True)
    il_rows = []
    for dt, key, il_type in il_today:
        p = pmap.get(key)
        nm = html.escape((p or {}).get("player_name") or _name_from_key(key))
        pos = _pos_label((p or {}).get("position"))
        d = date.fromisoformat(dt)
        label = f"{il_type} IL".strip() if il_type else "IL"
        pos_tail = (" · " + html.escape(pos)) if pos else ""
        inner = (f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
                 f'<span class="otd-body" title="✚ {nm} placed on the {html.escape(label)}{pos_tail}">'
                 f'✚ <strong>{nm}</strong> placed on the {html.escape(label)}{pos_tail}</span>')
        if p:
            il_rows.append(f'<a class="otd-row" href="{_player_href(key)}" data-cat="il">{inner}{_fv_pill(p)}</a>')
        else:
            il_rows.append(f'<div class="otd-row" data-cat="il">{inner}</div>')

    # ---- assemble ----------------------------------------------------------
    def _section(title: str, rows: list) -> str:
        if not rows:
            return ""
        return ('<section class="home-module otd-module hist-section">'
                f'<div class="kicker"><h2>{html.escape(title)}</h2></div>'
                + "".join(rows) + '</section>')

    sections = (
        _section("Debut anniversaries", debut_rows)
        + _section("Trades on this day", trade_rows)
        + _section("Signings & free agency on this day", tx_rows)
        + _section("IL on this day", il_rows)
    )
    if not sections:
        sections = ('<p class="news-intro">No tracked prospect history on '
                    f'{html.escape(mon_d)}.</p>')

    chip_defs = [("all", "All"), ("debut", "Debuts"), ("trade", "Trades"),
                 ("signing", "Signings"), ("il", "IL")]
    chips = "".join(
        f'<button class="chip{" active" if c == "all" else ""}" '
        f'data-hist-filter="{c}">{html.escape(lbl)}</button>'
        for c, lbl in chip_defs)

    body = (
        '<div class="news-app hist-app">'
        f'<div class="section-head"><h1>{_masthead_icon("history")}Today in Prospect History - {html.escape(mon_d)}</h1>'
        '<span class="section-sub">debut anniversaries, trades, signings &amp; IL moves on this calendar date</span></div>'
        '<p class="news-intro">Exact calendar-date matches from past seasons. Transactions from 2019, '
        f'IL placements from 2017. Debut rows carry {_gl("wag", "WAG")}.</p>'
        f'<div class="filter-bar" id="hist-filter-bar"><span class="filter-label">Filter</span>{chips}</div>'
        f'<div id="hist-sections" style="max-width:760px;">{sections}</div>'
        '<p class="news-intro" style="font-size:11px;">No eFV-move section: grade history is stamped '
        'at model re-run dates, not the day a grade changed.</p>'
        '</div>'
        + _HIST_FILTER_JS
    )
    return page("Today in Prospect History - eephus.io", "", body,
                "Prospect history for this calendar date: MLB debut anniversaries, prospect trades, "
                "signings and IL moves from past seasons.",
                url=f"{SITE_ORIGIN}/history/")

def _date_callout() -> str:
    """Date-aware countdown when a prospect-calendar event is near.

    Events carry a (start, end) range rather than a single date - the MLB
    Draft runs three days (Jul 11-13), not one, so "days until" has to count
    down to the START, and the callout needs an in-progress state for the
    days the event is actually happening, not just before/after.

    CALENDAR COVERAGE. The table used to hold only the Draft and the January
    international window, so from mid-July through the end of November the
    callout rendered nothing at all - the emptiest stretch of the site's year
    covered none of the events a prospect reader actually tracks. The four
    additions below close it. Ranges are the RECURRING windows, not scraped
    dates: the trade deadline has sat on Jul 31 since 2019, the Rule 5 draft
    closes the Winter Meetings (a moving day inside the second week of
    December, hence a window rather than a false-precision single date), the
    Futures Game is All-Star Saturday, and FanGraphs' offseason org lists run
    through the late fall. Anything softer than that does not belong here.

    ORDER MATTERS: the loop returns the FIRST event (by start date) that is
    live or inside the 45-day horizon, so windows are kept short deliberately.
    A months-long "list season" range would sit "Underway" across December and
    January and swallow both the Rule 5 draft and the international window.
    """
    today = date.today()
    yr = today.year
    events = [
        # All-Star Saturday. Listed BEFORE the Draft so that on a shared start
        # date the one-day event wins the (stable-sorted) tie and the Draft
        # takes the slot back for the rest of its run.
        (date(yr, 7, 11), date(yr, 7, 11), "Futures Game", "/prospx/"),
        (date(yr, 7, 11), date(yr, 7, 13), "MLB Draft", "/prospx/#tab=draft"),
        (date(yr, 7, 31), date(yr, 7, 31), "MLB trade deadline", "/prospx/#tab=traded"),
        # FanGraphs list season - the offseason org-list run that re-grades the
        # consensus board. Capped at November on purpose (see ORDER MATTERS).
        (date(yr, 11, 1), date(yr, 11, 30), "FanGraphs list season", "/prospx/"),
        # Rule 5 draft - final day of the Winter Meetings; the window spans the
        # days that day has landed on rather than asserting one.
        (date(yr, 12, 8), date(yr, 12, 12), "Rule 5 draft", "/prospx/#tab=traded"),
        (date(yr if today <= date(yr, 1, 15) else yr + 1, 1, 15),
         date(yr if today <= date(yr, 1, 15) else yr + 1, 1, 15),
         "International signing period", "/prospx/#tab=ifa"),
    ]
    for start, end, name, href in sorted(events, key=lambda e: e[0]):
        if today > end:
            continue
        days = (start - today).days
        if start <= today <= end:
            tag, when = "◆ Live", "Underway"
        elif 0 <= days <= 45:
            tag = "◆ Upcoming"
            when = "Tomorrow" if days == 1 else f"in {days} days"
        else:
            continue
        md = start.strftime("%b %d").replace(" 0", " ")
        if end != start:
            md += "-" + end.strftime("%d").lstrip("0")
        return (f'<a class="home-callout" href="{href}">'
                f'<span class="cal-tag">{tag}</span>'
                f'<span class="cal-msg"><strong>{html.escape(name)}</strong> · {md} · {when}</span>'
                f'<span class="cal-go">View →</span></a>')
    return ""

# The eFV model floors at 20 for the long tail of organizational filler it has
# no projection for. Those rows are a spike ON the floor, not a distribution, so
# every homepage read of the eFV shape excludes them and SAYS it excludes them.
_EFV_FLOOR = 20.0

def _scatter_points(players: list, n: int) -> list[tuple[float, float]]:
    """`n` REAL (age, eFV) pairs spread across the graded board, chosen
    deterministically from the day's ordinal.

    Spread along the GRADE AXIS, not uniformly and not by rank. A uniform draw
    is ~72% floor rows, and even with the floor dropped it piles two thirds of
    its dots into the 38-49 band - a horizontal smear, not a scatter. Equal-COUNT
    strata are barely better: the board is right-skewed, so the top sixteenth
    still spans 48-61 and the elite corner usually goes unrepresented. Walking
    evenly UP THE GRADE RANGE and taking the nearest real player at each step
    (each used once) spans 21 to 61 with sixteen actual prospects. It samples the
    board, it does not estimate its density - the caption says exactly that."""
    import random
    by_grade: dict[int, list] = {}
    for p in players:
        age, fv = p.get("age"), _primary_fv(p)
        if not (isinstance(age, (int, float)) and isinstance(fv, (int, float))):
            continue
        # Gate on the DISPLAYED grade, exactly as the histogram does - a raw
        # 20.2 displays as 20 and is a floor row, not a graded one.
        g = _round_half_up(fv)
        if g > _EFV_FLOOR:
            by_grade.setdefault(g, []).append((float(age), float(fv)))
    present = sorted(by_grade)
    if not present:
        return []
    rnd = random.Random(date.today().toordinal())
    lo_g, hi_g = present[0], present[-1]
    out = []
    for k in range(n):
        target = lo_g + (hi_g - lo_g) * k / max(1, n - 1)
        # Nearest grade that still has an unused player; ties break low.
        for g in sorted(present, key=lambda q: (abs(q - target), q)):
            if by_grade[g]:
                out.append(by_grade[g].pop(rnd.randrange(len(by_grade[g]))))
                break
        else:
            break                       # board exhausted (tiny/test data layer)
    return out

def _scatter_teaser(players: list | None = None) -> str:
    """Tiny inline scatter linking to the Scatterplots builder.

    The dots used to be 16 RANDOM coordinates seeded off the date - a picture of
    nothing, on the front page of a site whose whole claim is measured numbers.
    They are now 16 real prospects plotted as age (x) against eFV (y), on the
    real domains, with the fill carrying the tier split the rest of the page
    uses (foil and up = gold). Same SVG budget: same box, same dot count, no
    fetch. With no data layer the card renders without its chart rather than
    falling back to invented dots."""
    pts_data = _scatter_points(players or [], 16)
    svg = ""
    if len(pts_data) >= 2:
        ages = [a for a, _ in pts_data]
        fvs = [f for _, f in pts_data]
        a_lo, a_hi = min(ages), max(ages)
        f_lo, f_hi = min(fvs), max(fvs)
        a_span = (a_hi - a_lo) or 1.0
        f_span = (f_hi - f_lo) or 1.0
        pts = "".join(
            f'<circle cx="{8 + ((a - a_lo) / a_span) * 134:.0f}" '
            f'cy="{42 - ((f - f_lo) / f_span) * 36:.0f}" r="2.2" '
            f'style="fill:var(--accent-{"gold" if f >= 50 else "green"});opacity:0.85;"/>'
            for a, f in pts_data)
        cap = (f'{len(pts_data)} prospects sampled across the graded board: '
               f'age {a_lo:.1f}-{a_hi:.1f} on x, '
               f'eFV {_round_half_up(f_lo)}-{_round_half_up(f_hi)} on y')
        svg = (f'<div class="st-svg"><svg viewBox="0 0 150 48" preserveAspectRatio="none" '
               f'role="img" aria-label="{html.escape(cap)}"><title>{html.escape(cap)}</title>'
               f'<line x1="6" y1="44" x2="144" y2="44" style="stroke:var(--border);stroke-width:1;"/>'
               f'<line x1="6" y1="4" x2="6" y2="44" style="stroke:var(--border);stroke-width:1;"/>'
               f'{pts}</svg></div>')
    return (f'<a class="scatter-teaser" href="/prospx/#tab=charts">'
            f'{svg}'
            f'<div class="st-txt"><strong>Build a scatterplot</strong>'
            f'<span>Any X/Y metric · color &amp; size encodings · brush-to-zoom</span></div>'
            f'<span class="st-go">Scatterplots →</span></a>')

def _tm_seed_key(p: dict) -> str:
    """The key a /trademachine/#tm= seed carries for one trade_values row. An MLB
    row seeds on the projections key of its human (`proj_key`, stamped only
    where the row's own slug names a different human there); a prospect row
    seeds on its player_key, which is the PROSPX key."""
    if p.get("status") in ("graduated", "debuted") and p.get("proj_key"):
        return p["proj_key"]
    return p["player_key"]


def _cross_module_strip() -> str:
    """Across eephus.io - the homepage's window into the non-PROSPX
    modules (cohesion: every module surfaces on the front page). Reads
    the committed sidecars at build time; any missing file just drops
    its card."""
    cards = []
    # MLB Free Agency - top of the current class board
    try:
        fa = _cached_data_json("fa_class.json")
        top = sorted((m for m in fa.get("members") or [] if m.get("projGuar")),
                     key=lambda m: -m["projGuar"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/fa/#player={html.escape(m["key"])}">'
            f'<span class="xmod-name">{html.escape(m["name"])}</span>'
            f'<span class="xmod-sub">{html.escape(m.get("pos") or "")}</span>'
            f'<span class="xmod-val">{m.get("projYears") or "?"}y / ${(m["projGuar"] / 1e6):.0f}M</span></a>'
            for m in top)
        if rows:
            cards.append((f'{_ico("fa", 16)}Free Agency', '/fa/',
                          f'{fa.get("class_year", 2027) - 1}-{str(fa.get("class_year", 2027))[2:]} projected market leaders', rows))
    except (OSError, ValueError, KeyError):
        pass
    # MLB Projections - 5y WAR leaders
    try:
        mp = _cached_data_json("mlb_projections.json")
        top = sorted((v for v in mp.get("vets") or [] if v.get("warTotal")),
                     key=lambda v: -v["warTotal"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/projections/#player={html.escape(v["key"])}">'
            f'<span class="xmod-name">{html.escape(v["name"])}</span>'
            f'<span class="xmod-sub">{html.escape(v.get("pos") or "")}{" · two-way" if v.get("twoWay") else ""}</span>'
            f'<span class="xmod-val">{v["warTotal"]:.1f} WAR</span></a>'
            for v in top)
        if rows:
            cards.append((f'{_ico("projections", 16)}MLB Projections', '/projections/',
                          'five-year eWAR leaders', rows))
    except (OSError, ValueError, KeyError):
        pass
    # Trade Machine - top surplus trade values (prospects + MLB, one currency).
    # DEEP LINKS: every other card in this strip opens the player it names, but
    # these rows all pointed at a bare /trademachine/. The app DOES support a
    # per-player seed - _tmSeedFromURL() in assets/trademachine.js reads
    # `#tm=<kind>:<key>` off the hash and pre-loads that player into Side A, and
    # renderTradeMachine() calls it on mount, so the standalone page honours it,
    # not just the PROSPX-embedded view. `kind` is the app's own split
    # (_tbIsMlb: status graduated/debuted => "mlb", else "prospect"); the seed
    # needs posterior_surplus_mm, which is exactly what the board price is
    # derived from, so a row that renders here always seeds.
    try:
        tv = _cached_data_json("trade_values.json")
        top = sorted((p for p in tv.get("players") or []
                      if p.get("trade_value_mm") is not None
                      and p.get("posterior_surplus_mm") is not None
                      and p.get("player_key")),
                     key=lambda p: -p["trade_value_mm"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/trademachine/#tm='
            f'{"mlb" if p.get("status") in ("graduated", "debuted") else "prospect"}:'
            # an MLB seed resolves on the projections key of the row's human
            f'{html.escape(_tm_seed_key(p))}">'
            f'<span class="xmod-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(_pos_label(p.get("position")))} · {html.escape(p.get("org") or "")}</span>'
            f'<span class="xmod-val">${p["trade_value_mm"]:.0f}M</span></a>'
            for p in top)
        if rows:
            cards.append((f'{_ico("trademachine", 16)}Trade Machine', '/trademachine/',
                          'surplus trade value, prospects + MLB', rows))
    except (OSError, ValueError, KeyError):
        pass
    # CollegeSavant - static teaser (its data bundles stay in-module)
    cards.append((f'{_ico("collegesavant", 16)}CollegeSavant', '/collegesavant/',
                  'college baseball percentiles',
                  '<a class="xmod-row" href="/collegesavant/"><span class="xmod-name">Hitter dashboard</span><span class="xmod-val">EV · xwOBA · discipline →</span></a>'
                  '<a class="xmod-row" href="/collegesavant/pitcher_index.html"><span class="xmod-name">Pitcher dashboard</span><span class="xmod-val">Stuff+ · shapes →</span></a>'))
    # MLB Stats / REM+ - top relievers by REM+ (the reliever run-prevention metric)
    try:
        bl = _cached_data_json("bullpen_leaderboards.json")
        top = sorted((r for r in bl.get("relievers") or [] if r.get("rem_plus") is not None),
                     key=lambda r: -r["rem_plus"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/mlbstats/#section=bullpen">'
            f'<span class="xmod-name">{html.escape(r.get("name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(r.get("team") or "")}{" · " + html.escape(r["role"]) if r.get("role") else ""}</span>'
            f'<span class="xmod-val">{round(r["rem_plus"])} REM+</span></a>'
            for r in top)
        if rows:
            cards.append((f'{_ico("mlbstats", 16)}MLB Stats', '/mlbstats/#section=bullpen',
                          'top relievers by REM+', rows))
    except (OSError, ValueError, KeyError):
        pass
    # Leverage Leaderboards - realized win-probability impact, the one side of
    # /mlbstats/ the REM+ card above never reaches (that card is relievers only,
    # and leverage_leaderboards.json carries BOTH batters and starters). WPA is
    # descriptive realized value, not a projection - the sub-head says so.
    # Deep-links the section the app's own readHash() understands:
    # #section=leverage, plus lview= for the starters view.
    try:
        lv = _cached_data_json("leverage_leaderboards.json")
        bat = sorted((b for b in lv.get("batters") or [] if b.get("wpa") is not None),
                     key=lambda b: -b["wpa"])[:2]
        sp = sorted((s for s in lv.get("starters") or [] if s.get("wpa") is not None),
                    key=lambda s: -s["wpa"])[:1]
        rows = "".join(
            f'<a class="xmod-row" href="/mlbstats/#section=leverage">'
            f'<span class="xmod-name">{html.escape(b.get("name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(b.get("team") or "")} · batter</span>'
            f'<span class="xmod-val">{b["wpa"]:+.1f} WPA</span></a>'
            for b in bat)
        rows += "".join(
            f'<a class="xmod-row" href="/mlbstats/#section=leverage&amp;lview=starters">'
            f'<span class="xmod-name">{html.escape(s.get("name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(s.get("team") or "")} · starter</span>'
            f'<span class="xmod-val">{s["wpa"]:+.1f} WPA</span></a>'
            for s in sp)
        if rows:
            # i-li, the win-probability swing (the old ⇅ glyph, redrawn).
            cards.append((f'{_ico("li", 16)}Leverage', '/mlbstats/#section=leverage',
                          'realized win-probability added', rows))
    except (OSError, ValueError, KeyError):
        pass
    # Defense Leaderboards (DEM+, 2026-09-11) - the fifth /mlbstats/ section and
    # the only one the strip did not reach. Qualified fielders only, the same
    # innings bar the board's own default view applies, so the card cannot lead
    # with a 60-inning outlier the leaderboard itself would flag provisional.
    try:
        dl = _cached_data_json("defense_leaderboards.json")
        top = sorted((f for f in dl.get("fielders") or []
                      if f.get("qualified") and f.get("dem_plus") is not None),
                     key=lambda f: -f["dem_plus"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/mlbstats/#section=defense">'
            f'<span class="xmod-name">{html.escape(f.get("name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(f.get("team") or "")}'
            f'{" · " + html.escape(f["pos"]) if f.get("pos") else ""}</span>'
            f'<span class="xmod-val">{round(f["dem_plus"])} DEM+</span></a>'
            for f in top)
        if rows:
            cards.append((f'{_ico("defense", 16)}Defense', '/mlbstats/#section=defense',
                          'top qualified fielders by DEM+', rows))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Alchemy Lab - highest RP->SP fit scores. The copy says "screen", not
    # "candidates": the rp2sp direction's backtest came back sign-wrong
    # (rho -0.17, n=35, no-ship), so the page frames fit as a structural screen
    # and this teaser must not promote it to a ranking claim on the way out.
    try:
        pal = _cached_data_json("pal.json")
        top = sorted((c for c in pal.get("rp2sp") or [] if c.get("fit") is not None),
                     key=lambda c: -c["fit"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/pal/">'
            f'<span class="xmod-name">{html.escape(c.get("name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(c.get("team") or "")}</span>'
            f'<span class="xmod-val">{round(c["fit"])} FIT</span></a>'
            for c in top)
        if rows:
            cards.append((f'{_ico("pal", 16)}Alchemy Lab', '/pal/',
                          'reliever-to-starter conversion screen', rows))
    except (OSError, ValueError, KeyError):
        pass
    # Fantasy - rest-of-season projected points leaders off the Redraft
    # sub-module. The section lists in fantasy.json are BARE mlbam ids and the
    # side comes from the section they sit in (assets/redraft.js resolves them
    # the same way), so a two-way player has one record per side and the lookup
    # has to be keyed (mlbam, side) or it prints Ohtani's pitching total on the
    # hitter board. The rows deep-link into the board they came from, which the
    # 2026-08-07 merge made addressable: the namespaced hash names the module
    # AND the tab, so the reader lands on ROS Hitters rather than on whatever
    # tab the module opens with.
    try:
        ff = _cached_data_json("fantasy.json")
        by_side = {(p.get("mlbam"), p.get("side")): p for p in ff.get("players") or []}
        ids = ((ff.get("sections") or {}).get("ros_hitter") or [])[:24]
        cand = [by_side.get((i, "hit")) for i in ids]
        top = sorted((c for c in cand if c and c.get("fpts_fgp") is not None),
                     key=lambda c: -c["fpts_fgp"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/fantasy/#m=redraft&amp;section=ros_hitter">'
            f'<span class="xmod-name">{html.escape(c.get("name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(c.get("team") or "")}</span>'
            f'<span class="xmod-val">{c["fpts_fgp"]:.0f} FG pts</span></a>'
            for c in top)
        if not rows and ff:
            # The artifact loaded but the board is empty (the 2026-09-23 build
            # served 0 players). Dropping the card said nothing; the card now
            # says the board is empty and when it was built.
            built = str(ff.get("generated_at") or "")[:10] or "date unknown"
            rows = ('<a class="xmod-row" href="/fantasy/#m=redraft&amp;section=ros_hitter">'
                    '<span class="xmod-name">No rows</span>'
                    f'<span class="xmod-sub">board built {html.escape(built)} is empty</span>'
                    '<span class="xmod-val">open →</span></a>')
        if rows:
            cards.append((f'{_ico("fantasy", 16)}Fantasy', '/fantasy/#m=redraft&amp;section=ros_hitter',
                          'rest-of-season hitter points leaders', rows))
    except (OSError, ValueError, KeyError):
        pass
    # MiLB Park Factors - the most offense-inflating venues on the current
    # 3-season window (display-only context; no model reads these).
    try:
        pf = _cached_data_json("milb_park_factors.json")
        venues = pf.get("venues") or []
        year = max((int(y) for v in venues for y in (v.get("window_run_pf") or {})),
                   default=None)
        # venue_id -> the level its clubs played at in that window
        lvl_of: dict = {}
        for t in pf.get("team_seasons") or []:
            if year is not None and year - 2 <= t.get("season", 0) <= year:
                lvl_of.setdefault(t.get("venue_id"), t.get("level"))
        rated = [(v, (v.get("window_run_pf") or {}).get(str(year))) for v in venues]
        top = sorted(((v, f) for v, f in rated if f is not None),
                     key=lambda vf: -vf[1])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/parks/">'
            f'<span class="xmod-name">{html.escape(v.get("venue_name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(lvl_of.get(v.get("venue_id")) or "")}</span>'
            f'<span class="xmod-val">{f:.2f} run PF</span></a>'
            for v, f in top)
        if rows:
            cards.append((f'{_ico("parks", 16)}Park Factors', '/parks/',
                          f'MiLB venues that add the most offense ({year} window)', rows))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Model Accountability - the verdict split, counted off the registry at build
    # time. Deprecated is on the card on purpose: a ledger that teases only its
    # wins on the homepage is the thing the ledger exists to argue against.
    try:
        reg = _cached_data_json("model_registry.json")
        tally: dict = {}
        for m in reg.get("models") or []:
            tally[m.get("verdict")] = tally.get(m.get("verdict"), 0) + 1
        rows = "".join(
            f'<a class="xmod-row" href="/models/">'
            f'<span class="xmod-name">{html.escape(lab)}</span>'
            f'<span class="xmod-sub">{html.escape(sub)}</span>'
            f'<span class="xmod-val">{tally.get(key, 0)}</span></a>'
            for key, lab, sub in (
                ("validated", "Validated", "beat their stated baseline"),
                ("deprecated", "Deprecated", "measured, failed, retired"),
                ("unvalidated", "Unvalidated", "serving, not yet gated")))
        if tally:
            cards.append((f'{_ico("models", 16)}Model Ledger', '/models/',
                          f'{sum(tally.values())} models with a predictive claim',
                          rows))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Diamond - static teaser (CollegeSavant's pattern: no data dependency; the
    # pass page carries its own live receipts). Names the two member modules,
    # and the free-preview line renders only while diamond-config.js ships
    # gating false, so the homepage cannot promise a preview the config has
    # closed. No try/except: a broken config already fails the /diamond/ build
    # in this same run, and a quiet missing card would just hide that earlier.
    free_line = ("member pass" if _diamond_cfg()["gating"]
                 else "free during the founding preview")
    cards.append((f'{_ico("diamond", 16)}Diamond', '/diamond/',
                  'the paid tier: fantasy and betting',
                  '<a class="xmod-row" href="/fantasy/"><span class="xmod-name">Fantasy</span><span class="xmod-val">redraft · dynasty · DFS →</span></a>'
                  '<a class="xmod-row" href="/betting/"><span class="xmod-name">Sports Betting</span><span class="xmod-val">model vs the book price →</span></a>'
                  f'<a class="xmod-row" href="/diamond/"><span class="xmod-name">Diamond Pass</span><span class="xmod-val">{free_line} →</span></a>'))
    body = "".join(
        f'<div class="xmod-card"><div class="xmod-head"><span class="xmod-title">{title}</span>'
        f'<a class="xmod-link" href="{href}">open →</a></div>'
        f'<div class="xmod-sub-head">{html.escape(sub)}</div>{rows}</div>'
        for title, href, sub, rows in cards)
    return (f'<div class="xmod-strip"><div class="xmod-eyebrow">Across eephus.io</div>'
            f'<div class="xmod-grid">{body}</div></div>')


# --------------------------------------------------------------------------- #
# eFV distribution - a build-time histogram of the board's own grade shape.
#
# The bands are the RARITY RAMP, mirrored from prospx rankNumRarityClass()
# (45 shine / 50 foil / 55 chrome / 61 holo / 70 legendary) so the chart and a
# player's card treatment can never disagree about where a tier starts. Keyed
# on the DISPLAYED integer, like _fv_tier_class, for the same reason: a raw
# threshold would colour a bar labelled "60" as if it were 61.
#
# COLOUR. Grade is an ORDERED quantity, so the bars take a single-hue
# SEQUENTIAL ramp (the brand navy, which is the refractor cyan on dark),
# escalating in weight through the common/shine/foil/chrome tiers, and the rare
# tail takes the site's holo accent as a highlight hue. That is deliberately not
# six categorical colours: a hue per band would be a rainbow on ordered data.
# Both themes were checked - the ramp is monotonic in lightness (4.1:1 -> 12.5:1
# on paper, 5.0:1 -> 11.8:1 on the dark field) and the chrome/holo pair clears
# colour-blind separation (deutan dE 26.6 light, 14.5 dark).
#
# Zero runtime cost: no fetch, no script, no client work - just rects.
# --------------------------------------------------------------------------- #
_EFV_TIERS = (
    # lo (None = open) | hi (None = open) | key | axis label | fill | fill-opacity
    (None,   44, "common",    "under 45", "var(--accent-navy)", "0.62"),
    (45,     49, "shine",     "45-49",    "var(--accent-navy)", "0.78"),
    (50,     54, "foil",      "50-54",    "var(--accent-navy)", "0.92"),
    (55,     60, "chrome",    "55-60",    "var(--accent-navy)", "1"),
    (61,     69, "holo",      "61-69",    "var(--accent-lilac)", "1"),
    (70,   None, "legendary", "70+",      "var(--accent-lilac)", "1"),
)

def _efv_tier(g: int) -> tuple:
    """The rarity-ramp row a DISPLAYED integer grade falls in."""
    for row in reversed(_EFV_TIERS):
        if row[0] is None or g >= row[0]:
            return row
    return _EFV_TIERS[0]

def _efv_distribution_html(players: list) -> str:
    """Full-width homepage module: the distribution of displayed eFV grades
    across the board, banded by rarity tier.

    THE FLOOR IS EXCLUDED AND SAID SO. eFV floors at 20 for the long tail of
    organizational filler it has no projection for - today roughly 7 of every 10
    rows. Plotting that spike would drown every real bar at ~1px and misread as
    "the board is all replacement level", so the histogram covers the graded
    range and the caption states the floor count outright rather than quietly
    dropping it."""
    grades = []
    for p in players:
        v = _primary_fv(p)
        if isinstance(v, (int, float)):
            grades.append(_round_half_up(v))
    if not grades:
        return ""
    floor_n = sum(1 for g in grades if g <= _EFV_FLOOR)
    plotted = sorted(g for g in grades if g > _EFV_FLOOR)
    if len(plotted) < 10:            # nothing to shape a histogram out of
        return ""
    lo, hi = plotted[0], plotted[-1]
    counts: dict[int, int] = {}
    for g in plotted:
        counts[g] = counts.get(g, 0) + 1
    n_bkt = hi - lo + 1
    top_c = max(counts.values())
    total = len(plotted)
    median = plotted[total // 2] if total % 2 else plotted[total // 2 - 1]

    # ---- geometry (viewBox units; the SVG scales to the module width) ----
    pad, w, base, top = 10, 720, 118, 16
    plot_h = base - top
    slot = (w - 2 * pad) / n_bkt
    bar_w = max(1.2, slot - 2)       # 2u surface gap between bars

    def x_of(g: int) -> float:
        """Left edge of grade `g`'s bucket."""
        return pad + (g - lo) * slot

    # NB: every themed colour below rides `style=`, never a bare presentation
    # attribute - a CSS custom property in `fill="var(...)"` is not reliably
    # substituted, and the failure mode is a silent fallback to black.
    bars = []
    for g in range(lo, hi + 1):
        c = counts.get(g, 0)
        if not c:
            continue
        _, _, tier_key, _, fill, op = _efv_tier(g)
        h = max(1.0, (c / top_c) * plot_h)
        pct = 100.0 * c / total
        bars.append(
            f'<rect x="{x_of(g):.1f}" y="{base - h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'style="fill:{fill};fill-opacity:{op};">'
            f'<title>eFV {g} ({tier_key}) - {c} prospect{"s" if c != 1 else ""}, '
            f'{pct:.1f}% of the graded board</title></rect>')

    # Tier boundary rules + the threshold number, drawn only for thresholds that
    # actually fall inside the plotted range (a rule for a tier nobody reaches
    # would be furniture).
    rules = []
    for t_lo, _, _, _, _, _ in _EFV_TIERS:
        if t_lo is None or not (lo < t_lo <= hi):
            continue
        x = x_of(t_lo)
        rules.append(
            f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{base}" '
            f'style="stroke:var(--border);stroke-width:1;stroke-dasharray:2 3;"/>')
        # Only label a threshold the x axis does not already carry (the ticks
        # below run every 5 grades, so 45/50/55 would print twice); 61 is the
        # off-grid one and is the only band edge that needs saying.
        if t_lo % 5:
            rules.append(
                f'<text x="{x + 3:.1f}" y="{top - 7}" '
                f'style="font:9px var(--font-retro-mono);fill:var(--text-tertiary);">{t_lo}</text>')

    # x ticks every 5 grades - selective labels, never one per bar.
    ticks = []
    for g in range(lo + (-lo % 5), hi + 1, 5):
        ticks.append(
            f'<text x="{x_of(g) + bar_w / 2:.1f}" y="{base + 13}" text-anchor="middle" '
            f'style="font:9px var(--font-retro-mono);fill:var(--text-tertiary);">{g}</text>')

    svg = (
        f'<svg viewBox="0 0 {w} 136" style="width:100%;height:auto;display:block;" role="img" '
        f'aria-label="Histogram of eephusFV grades across the board, banded by rarity tier">'
        f'<title>eFV distribution: {total} graded prospects from {lo} to {hi}, '
        f'median {median}</title>'
        f'<line x1="{pad}" y1="{base}" x2="{w - pad}" y2="{base}" '
        f'style="stroke:var(--border);stroke-width:1;"/>'
        f'{"".join(rules)}{"".join(bars)}{"".join(ticks)}</svg>')

    # Legend doubles as the table view: every tier that has players, with its
    # count, so identity never rests on colour alone.
    chips = []
    for t_lo, t_hi, _, t_label, fill, op in _EFV_TIERS:
        n = sum(c for g, c in counts.items()
                if (t_lo is None or g >= t_lo) and (t_hi is None or g <= t_hi))
        if not n:
            continue
        chips.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;">'
            f'<span aria-hidden="true" style="width:10px;height:10px;flex:none;'
            f'background:{fill};opacity:{op};"></span>{html.escape(t_label)}'
            f'<span style="color:var(--text-tertiary)">{n:,}</span></span>')
    legend = ('<div style="display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px;'
              'font-family:var(--font-retro-mono);font-size:11px;color:var(--text-secondary);">'
              + "".join(chips) + '</div>')
    caption = (
        f'<div style="margin-top:6px;font-family:var(--font-retro-mono);font-size:11px;'
        f'color:var(--text-tertiary);line-height:1.5;">'
        f'{total:,} graded prospects · median {_gl("xfv", "eFV")} {median} · '
        f'{floor_n:,} at the eFV {int(_EFV_FLOOR)} floor (no projection), not plotted · '
        f'bands are {_gl("rarity_tiers", "rarity tiers")}</div>')
    return _home_module("eFV Distribution", "/prospx/", "Full board",
                        svg + legend + caption, full=True)


_HOME_DRAWER_JS = '''<script>
/* Homepage sidebar drawer (<=900px): the hamburger in .sb-brand opens the
   search + module list + wire feed; Esc / outside click close it; resizing
   back to desktop resets the state. Desktop widths ignore all of this
   (the .home-nav-toggle is display:none above 900px). */
(function () {
  "use strict";
  var sb = document.getElementById("home-sidebar");
  var btn = sb ? sb.querySelector(".home-nav-toggle") : null;
  if (!sb || !btn) return;
  function set(open) {
    if (open) sb.setAttribute("data-nav-open", "");
    else sb.removeAttribute("data-nav-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  }
  btn.addEventListener("click", function () { set(!sb.hasAttribute("data-nav-open")); });
  document.addEventListener("click", function (e) {
    if (sb.hasAttribute("data-nav-open") && !sb.contains(e.target)) set(false);
  });
  document.addEventListener("keydown", function (e) {
    if ((e.key === "Escape" || e.key === "Esc") && sb.hasAttribute("data-nav-open")) {
      set(false);
      btn.focus();
    }
  });
  var mq = window.matchMedia ? window.matchMedia("(max-width: 900px)") : null;
  if (mq) {
    var onmq = function () { if (!mq.matches) set(false); };
    if (mq.addEventListener) mq.addEventListener("change", onmq);
    else if (mq.addListener) mq.addListener(onmq);
  }
})();
</script>'''


def build_home(articles: list[dict], data: dict | None = None) -> str:
    """Homepage = sidebar + newspaper-style main, with live PROSPX modules + a
    prospect wire feed read from the build-time data layer."""
    data = data or {}
    players = data.get("players") or []
    org_summary = data.get("org_summary") or []
    graduates = data.get("graduates") or []
    as_of = data.get("as_of", " - ")
    today = datetime.now().strftime("%A, %B %d, %Y").replace(" 0", " ")
    events = _collect_events(players, graduates, _load_fa_events_for_wire())
    spotlight_buckets = data.get("spotlights") or {}

    # ---- sidebar ----
    # The sidebar has room for fuller module names than the horizontal
    # header nav, so a couple of labels expand here (key → sidebar label).
    # Every module carries its 16 px pixel icon (final-pass plan 5.7, PX-05),
    # drawn once in assets/eephus-icons.svg and keyed by the NAV_ITEMS key;
    # PROSPX's 16 px ball monogram became i-prospx (no monogram below 40 px).
    # The unicode glyph map this replaced was a third icon vocabulary.
    # Lifecycle sigils live on module mastheads, not here.
    sidebar_labels = {"fa": "MLB Free Agency", "projections": "MLB Projections",
                      "collegesavant": "CollegeSavant",
                      "glossary": "Glossary & Methodology"}
    def _sb_link(key, label, href, grouped=False):
        classes = []
        if key == "home":
            classes.append("is-active")   # the sidebar only renders on the homepage
        if grouped:
            classes.append("sb-grouped")
        cls = f' class="{" ".join(classes)}"' if classes else ""
        icon = f'<span class="sb-ico" aria-hidden="true">{_ico(key, 16)}</span>'
        return f'<a href="{href}"{cls}>{icon}{html.escape(label)}</a>'
    nav = []
    for item in NAV_ITEMS:
        if _nav_is_group(item):
            # A nested, always-expanded sub-block in the vertical rail (the
            # dropdown is for the horizontal top bar; the rail has room).
            nav.append(f'<div class="sb-subhead">{html.escape(item["group"])}</div>')
            for k, l, h in item["children"]:
                nav.append(_sb_link(k, l, h, grouped=True))   # leaf label under the subhead
        else:
            key, label, href = item
            nav.append(_sb_link(key, sidebar_labels.get(key, label), href))
    # The PROSPX sub-nav: each deep link carries its section tab's 12 px icon
    # (PX-05), the same symbol the PROSPX tab strip draws, where a cyan "›"
    # used to repeat on every row.
    sub = "".join(f'<a href="{href}">{_ico(_prospx_subnav_section(href), 12)}{html.escape(label)}</a>'
                  for label, href in PROSPX_SUBNAV)
    feed = _feed_html(events, 12) or _px_state("empty", "No recent activity.")
    spotlight = _spotlight_html(players, spotlight_buckets)
    search = ('<input class="sb-search" type="search" placeholder="Search prospects…" aria-label="Search prospects" '
              "onkeydown=\"if(event.key==='Enter'&&this.value.trim()){location.href='/prospx/#q='+encodeURIComponent(this.value.trim());}\">")
    # Mobile drawer (<=900px): the homepage does not load eephus-nav.js, so the
    # sidebar carries its own hamburger + inline wiring; site.css collapses
    # everything but .sb-brand until [data-nav-open]. Desktop is unaffected
    # (.home-nav-toggle is display:none above 900px).
    drawer_btn = ('<button type="button" class="home-nav-toggle" '
                  'aria-controls="home-sidebar" aria-expanded="false" '
                  'aria-label="Open menu">☰</button>')
    sidebar = (
        '<aside class="home-sidebar" id="home-sidebar">'
        f'<div class="sb-brand"><a class="wm" href="/">{eephus_merged_wordmark("sb", tag="span")}</a>{THEME_BTN}{drawer_btn}</div>'
        # eephus.io - account entry point for the homepage (page_home has no
        # .eephus-nav top bar). refreshNav() in eephus-ui.js injects the Sign-in /
        # avatar control into any .eephus-nav-controls, including this sidebar slot.
        '<div class="sb-account eephus-nav-controls"></div>'
        f'{search}'
        f'<div class="sb-group"><div class="sb-group-label">Modules</div><nav class="sb-nav">{"".join(nav)}</nav></div>'
        # Prospect News feed sits high (where the PROSPX sub-nav used to be);
        # the PROSPX sub-nav drops below the spotlight feature.
        f'<div class="sb-group"><div class="sb-feed"><div class="feed-head"><a href="/news/" title="All prospect news"><span class="blip"></span>Prospect News<span class="feed-head-more">all →</span></a></div>{feed}</div></div>'
        f'{spotlight}'
        f'<div class="sb-group"><div class="sb-group-label sb-group-label--lockup">{_ico("prospx", 12)}PROSPX</div><nav class="sb-subnav">{sub}</nav></div>'
        '</aside>'
        + _HOME_DRAWER_JS
    )

    # ---- top wire ticker ----
    # Decorative scrolling marquee - duplicates the accessible Prospect Wire feed
    # in the sidebar, so it's hidden from assistive tech (aria-hidden) to avoid
    # reading the same items twice / announcing a moving region.
    ticker = (f'<div class="home-ticker" aria-hidden="true"><span class="ticker-tag"><a href="/news/"><span class="blip"></span>News</a></span>'
              f'<div class="ticker-track">{_ticker_html(events)}</div></div>')

    # ---- masthead ----
    masthead = (
        '<div class="masthead">'
        f'{eephus_logo_lockup()}'
        '<div class="dateline"><span>Sabermetric Analysis</span>'
        f'<span>{html.escape(today)}</span><span>Data as of {html.escape(as_of)}</span></div></div>'
    )
    # Draft War Room banner: hidden by default, revealed by a small client-side
    # check ONLY while the live draft feed reports status "live" (draft night).
    # Links into the PROSPX draft section's War Room view. No em dashes (copy rule).
    masthead += (
        '<div id="draft-war-room-banner" style="display:none;margin:10px 0 0;">'
        '<a href="/prospx/#tab=draft&amp;dview=war-room" '
        'style="display:block;padding:10px 14px;border-radius:8px;'
        'background:var(--brand-navy,#0E2B4D);color:#fff;font-weight:600;'
        'text-decoration:none;">'
        '<span class="blip"></span> The MLB Draft is live. Draft War Room: every pick '
        'priced against the board in surplus dollars.</a></div>'
        '<script>(function(){try{fetch("/data/draft_live.json",{cache:"no-cache"})'
        '.then(function(r){return r.ok?r.json():null;})'
        '.then(function(j){if(j&&j.status==="live"){'
        'var e=document.getElementById("draft-war-room-banner");if(e)e.style.display="";}})'
        '.catch(function(){});}catch(e){}})();</script>'
    )

    # ---- lead story (latest human-written article) ----
    # Owner decision 2026-08-04: the homepage editorial section carries HUMAN
    # editorials only. The generated "From the data" lead card that used to take
    # this slot on a stale article is deleted; the same wire facts still appear on
    # /news/, in the sidebar feed, the ticker and the movers modules.
    latest = articles[0] if articles else None
    if latest:
        lead = (
            '<article class="lead-story no-img">'
            '<div><div class="lead-kicker">Latest</div>'
            f'<h1>{html.escape(latest["title"])}</h1>'
            f'<div class="byline">{_byline(latest, link_handle=False)}</div>'
            f'<p class="excerpt">{html.escape(latest.get("summary", ""))}</p>'
            f'<a class="read" href="/articles/{latest["slug"]}/">Read the full story →</a></div>'
            '</article>'
        )
    else:
        lead = ('<article class="lead-story no-img"><div><div class="lead-kicker">Latest</div>'
                + _px_state("empty", "<strong>No articles yet</strong>") + '</div></article>')
    sec = articles[1:4]
    if sec:
        secondary = ('<div class="secondary-stories">' + "".join(
            f'<a href="/articles/{a["slug"]}/"><div class="s-kicker">{html.escape(a.get("date_disp", ""))}</div>'
            f'<h3>{html.escape(a["title"])}</h3></a>' for a in sec) + '</div>')
    elif latest:
        # Single-piece front: only one story so far. Keep the broadsheet rhythm
        # (the same double rule the secondary row carries) and say so plainly
        # rather than leaving a bare gap under the lead.
        secondary = ('<div class="more-soon-strip"><span>More analysis soon</span>'
                     '<a href="/articles/">All articles →</a></div>')
    else:
        secondary = ""

    # ---- live PROSPX modules ----
    # Top Movers = biggest GENUINE moves from the de-noised movement engine
    # (movement.compute_genuine_movement, carried on each player's `stock`):
    # only same-source consensus steps count, so a source merely re-publishing
    # or the panel changing no longer fires a fake mover. Gated to the trailing
    # year so the homepage stays a "moving now" surface, matching the FV
    # sparkline beside each row. The driver-chip view lives on the PROSPX
    # spotlights tab this module links to.
    # A step with an endpoint on the eFV floor is a floor crossing, not a
    # re-grade, and is left out here (it still reads on the wire as "to eFV
    # floor" / "off eFV floor"); see _mover_at_floor.
    mv = [(d, p) for p in players
          if p.get("status") != "debuted"
          and (d := _genuine_mover_step(p)) is not None
          and not _mover_at_floor(p)]
    # Top 5 movers: 3 biggest risers + 2 biggest fallers (the module shows both
    # directions; the spotlights tab it links to carries the full list).
    risers = sorted((t for t in mv if t[0] > 0), key=lambda t: -t[0])[:3]
    fallers = sorted((t for t in mv if t[0] < 0), key=lambda t: t[0])[:2]
    movers_body = "".join(_row_mover(p, d) for d, p in risers + fallers)
    movers = _home_module("Top Movers", "/prospx/#tab=spotlights", "All movers", movers_body) if movers_body else ""

    # Rank by PRIMARY FV (eFV when graded, else consensus close), RAW/unrounded -- the eFV
    # DECIMAL, matching the board's efvRankValue. The board's v42 tiebreak on an exact-decimal
    # tie is the '+' upside flag, then the JS-only Tiebreaker Score (TBS), then name; the
    # homepage can match the primary + '+' but not TBS, so it approximates the rest by stable
    # order. (Was tie-broken by consensus FV, which the board no longer uses since v42.)
    def _top_key(p):
        return (_primary_fv(p) if _primary_fv(p) is not None else -1,
                1 if p.get("fv_close_plus") else 0)
    # ONE ORDERING, READ NOT RE-DERIVED (2026-09-05). Top Prospects are the first five rows
    # of THE board rank, `overall_rank`, which storage bakes from one ordering
    # (BOARD_GRADE_FIELD -> board_sort_key -> '+' -> TBS proxy -> avg_rank) and re-bakes on
    # the fresh eFV file after the regen (storage.rebake_board_ranks). This module used to
    # re-sort on (primary FV, '+') and label rows by position: that chain carried no
    # sub-decimal term, so an exact-grade tie fell through to list order, which was the
    # rank baked from the PREVIOUS run's eFV file. Josue De Paula and Theo Gillen (58.3,
    # keys 9.617 vs 9.670) rendered #4 / #5 here and #5 / #4 on the board. The old key stays
    # only as the fallback for a payload that carries no ranks at all.
    ranked = sorted((p for p in players if p.get("overall_rank")),
                    key=lambda p: int(p["overall_rank"]))
    topN = ranked[:5] or sorted(players, key=_top_key, reverse=True)[:5]
    top_body = "".join(_row_top(p, int(p.get("overall_rank") or i))
                       for i, p in enumerate(topN, 1))
    topp = _home_module("Top Prospects", "/prospx/", "Full board", top_body) if top_body else ""

    gr = sorted((g for g in graduates if g.get("debut_date")), key=lambda g: g["debut_date"], reverse=True)[:5]
    grad_body = "".join(_row_grad(g) for g in gr)
    grads = _home_module("Recent Debuts", "/prospx/#tab=debuts", "All debuts", grad_body) if grad_body else ""

    fm = sorted((o for o in org_summary if o.get("farm_rank")), key=lambda o: o["farm_rank"])[:5]
    farm_body = "".join(_row_farm(o, o.get("farm_rank") or i) for i, o in enumerate(fm, 1))
    farm = _home_module("Top Farm Systems", "/prospx/#tab=farm", "Farm systems", farm_body) if farm_body else ""

    # Rotates the real Arkmetrics shelf out of data/glossary.json (110 entries),
    # not the six hardcoded pairs, still keyed by day-of-year.
    terms = _glossary_teaser_terms()
    slug, term, defn = terms[datetime.now().timetuple().tm_yday % len(terms)]
    glossary = (f'<div class="glossary-teaser"><span>Today\'s term: <strong>{html.escape(term)}</strong> - {html.escape(defn)}</span>'
                f'<a href="/glossary/#g={slug}">Glossary →</a></div>')

    callout = _date_callout()
    otd = _this_day_html(graduates, players)
    trades_mod = _recent_trades_html(players)
    scatter = _scatter_teaser(players)
    cross = _cross_module_strip()
    # Full-width band under the 2x3 grid: a histogram wants width, and it reads
    # as the summary of the six ranking modules above it rather than a seventh
    # competing card (a 7th cell would also strand a half-empty grid row).
    efv_dist = _efv_distribution_html(players)
    # eephus.io - Forums module (third content pillar). Hydrated client-side by
    # eephus-ui.js (#eph-home-forums): bump/Hot ordering, last-active first.
    #
    # COLLAPSED UNTIL THE ACCOUNT LAYER IS LIVE. assets/eephus-config.js is
    # absent on the public tree, so eephus-ui.js's LIVE gate has no Supabase
    # project, mountForumsList paints "Discussion opens at launch" and the
    # homepage donated a full-width band to a placeholder. The slot is now
    # server-rendered hidden and revealed by the same condition the client
    # gates on (window.EEPHUS_SUPABASE carrying url + anonKey), so the module
    # still hydrates the moment config appears - nothing to re-deploy - and
    # costs one hidden div until then. Inline + DOMContentLoaded so it runs
    # after the deferred config script has (or has not) defined the global.
    forums_mod = (
        '<div id="home-forums-slot" hidden>'
        + _home_module("Forums", "/forums/", "All discussions",
                       '<div id="eph-home-forums"></div>', full=True)
        + '</div>'
        '<script>(function(){function r(){try{var c=window.EEPHUS_SUPABASE;'
        'if(c&&c.url&&c.anonKey){var e=document.getElementById("home-forums-slot");'
        'if(e)e.removeAttribute("hidden");}}catch(e){}}'
        'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",r);'
        'else r();})();</script>'
    )
    main = (
        '<main class="home-main">'
        f'{masthead}{callout}{lead}{secondary}'
        # 2-col grid, paired by row: [This Day | Top Movers] (today's activity),
        # [Top Prospects | Farm] (rankings), [Recent Graduates | Recent Trades]
        # (recent transactions).
        f'<div class="module-cols">{otd}{movers}{topp}{farm}{grads}{trades_mod}</div>'
        f'{efv_dist}'
        f'{cross}'
        f'{forums_mod}'
        f'<div class="teaser-row">{glossary}{scatter}</div>'
        '</main>'
    )
    inner = f'{ticker}<div class="home-shell">{sidebar}{main}</div>'
    return page_home("eephus.io - sabermetrics", inner,
                     "Prospect board graded by eFV, plus MLB free agency, projections, leaderboards, "
                     "fantasy and betting models.")

def build_articles_index(articles: list[dict]) -> str:
    cards = []
    for a in articles:
        excerpt = html.escape(a.get("summary", ""))
        cards.append(
            f'<a class="card article-card" href="/articles/{a["slug"]}/">'
            '<div class="eyebrow">Article</div>'
            f'<p class="meta">{_byline(a, link_handle=False)}</p>'
            f'<h3>{html.escape(a["title"])}</h3>'
            f"<p>{excerpt}</p>"
            '<span class="card-cta">Read →</span></a>'
        )
    grid = "".join(cards) or '<p>No articles yet.</p>'
    body = (
        f'<div class="section-head"><h1>{_masthead_icon("articles")}Articles</h1></div>'
        f'<div class="article-grid">{grid}</div>'
    )
    return page("Articles - eephus.io", "articles", body, "Long-form baseball analysis from eephus.io.",
                url=f"{SITE_ORIGIN}/articles/")

def build_forums_index() -> str:
    """The /forums/ index - the third content pillar. The thread list is hydrated
    client-side by eephus-ui.js (#eph-forums-index): bump / Hot ordering, most
    recently active first. Static shell gives SEO + first paint + a nav home."""
    body = (
        f'<div class="section-head"><h1>{_masthead_icon("forums")}Forums '
        f'{_stage_chip("forums")}</h1>'
        '<span class="section-sub">Discussion across prospects, farm systems, and articles</span></div>'
        '<div class="eph-forums-index-page"><div id="eph-forums-index"></div></div>'
    )
    return page("Forums - eephus.io", "forums", body,
                "Community discussion across prospects, farm systems, and articles on eephus.io.",
                url=f"{SITE_ORIGIN}/forums/")

def build_fa() -> str:
    """The /fa/ Free Agency app - its own surface, SEPARATE from PROSPX.

    Static shell + assets/fa.js, which fetches the fa_export.py sidecars
    (data/fa_class.json / fa_archive.json / fa_meta.json) directly. Shares the
    site chrome and styles (.fa-app block in site.css) but loads none of the
    PROSPX boot payload or script. Views route via #view= (board / fits /
    archive / model / glossary)."""
    # Derive the class label + archive count from the data so the subtitle never goes stale.
    _fa_cy = _cached_data_json("fa_class.json").get("class_year") or 2027
    _fa_span = f"{_fa_cy - 1}-{str(_fa_cy)[2:]}"
    _fa_winters = len(_cached_data_json("fa_archive.json").get("winters") or []) or 12
    body = (
        '<div class="fa-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}<h1>{_masthead_icon("fa")}MLB Free Agency '
        f'{_stage_chip("fa")}</h1></div>'
        f'<span class="section-sub">the {_fa_span} class · projected contracts, '
        f'{_gl("rational_value", "rational value")}, team fits · {_fa_winters} archived winters</span></div>'
        '<div id="fa-banner"></div>'
        '<div class="filter-bar"><span class="filter-label">View</span>'
        '<span id="fa-view-chips"></span></div>'
        f'<div id="fa-rows"{_csv_optin("fa-class")}></div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/fa.js?v={_FA_VER}" defer></script>'
        f'<script src="/assets/fa_dpw.js?v={_FA_DPW_VER}" defer></script>'
    )
    return page("Free Agency - eephus.io", "fa", body,
                f"The {_fa_span} MLB free-agent class: projected contracts with floor, mean and "
                "ceiling bands, rational value vs predicted price, deal verdicts, team fits, and "
                f"{_fa_winters} archived winters with a realized-surplus ledger.",
                url=f"{SITE_ORIGIN}/fa/")


# Trade Machine markup - now the body of its own top-level /trademachine/ module
# (was a view inside MLB Projections; originally a PROSPX module by Anirudh Iyer).
# The board + evaluator run from assets/trademachine.js on the standalone data
# files; this is the markup the module mounts into.
# The CSV opt-in on #tradeboard-content is written as a literal attribute rather
# than through _csv_optin() because this constant is a plain string, not an
# f-string, and converting it would put every existing brace in this markup at
# the mercy of the formatter. It rides the TRADE BOARD wrapper, not the
# deal-builder mount above it: the board is the surface with the table.
_TRADE_MACHINE_BODY = ("""<div class="newsprint-eyebrow">
    <span class="newsprint-eyebrow-label">Trade Machine</span>
    <span class="newsprint-eyebrow-meta">module by Anirudh Iyer</span>
  </div>
  <div id="trade-machine"></div>
  <div class="tm-ros-note" style="margin:10px 0 2px;max-width:760px;color:var(--text-secondary);font-size:11px;line-height:1.55;">
    <strong>Rental leg:</strong> remaining season fraction &times; full-season surplus (projected WAR value minus salary). No floor: negative means the salary still owed exceeds the production.
  </div>
  <div class="trademachine-board-head detail-title" style="margin:18px 0 4px;font-size:13px;">Trade-value board <span class="detail-title-sub">Bayesian surplus, contract-aware, positional scarcity, opt-out adjusted</span></div>
  <div class="filter-toggle-row">
    <button class="filter-toggle" type="button" data-collapse-target="tradeboard-filter-bar" aria-expanded="false" title="Show / hide Trade Board filters">
      <span class="filter-toggle-label">Filter &amp; Sort</span>
      <span class="filter-toggle-arrow" aria-hidden="true">&#9662;</span>
    </button>
  </div>
  <div id="tradeboard-filter-bar" class="filter-bar collapsible-filter-bar">
    <div class="filter-group"><span class="filter-label">Pool</span>
      <button class="chip active" data-tb-pool="all" type="button">All</button>
      <button class="chip" data-tb-pool="milb" type="button">MiLB</button>
      <button class="chip" data-tb-pool="mlb" type="button">MLB</button>
    </div>
    <div class="filter-group"><span class="filter-label">Tier</span>
      <button class="chip active" data-tb-tier="all" type="button">All tiers</button>
      <button class="chip" data-tb-tier="elite" type="button">Elite ($40M+)</button>
      <button class="chip" data-tb-tier="high" type="button">High ($20-40M)</button>
      <button class="chip" data-tb-tier="mid" type="button">Mid ($8-20M)</button>
    </div>
    <div class="filter-group"><span class="filter-label">Position</span>
      <button class="chip active" data-tb-pos="all" type="button">All</button>
      <button class="chip" data-tb-pos="C" type="button">C</button>
      <button class="chip" data-tb-pos="1B" type="button">1B</button>
      <button class="chip" data-tb-pos="2B" type="button">2B</button>
      <button class="chip" data-tb-pos="SS" type="button">SS</button>
      <button class="chip" data-tb-pos="3B" type="button">3B</button>
      <button class="chip" data-tb-pos="LF" type="button">LF</button>
      <button class="chip" data-tb-pos="CF" type="button">CF</button>
      <button class="chip" data-tb-pos="RF" type="button">RF</button>
      <button class="chip" data-tb-pos="SP" type="button">SP</button>
      <button class="chip" data-tb-pos="RP" type="button">RP</button>
    </div>
    <div class="filter-group"><span class="filter-label">Org</span>
      <select class="chip" id="tb-org-filter" data-team-picker title="Filter Trade Board by organization"><option value="all">All orgs</option></select>
    </div>
    <div class="filter-group"><span class="filter-label">Exact pos</span>
      <select class="chip" id="tb-exact-pos-filter" title="Filter Trade Board by primary position"><option value="all">All positions</option></select>
    </div>
    <div class="filter-group"><span class="filter-label">Sort</span>
      <select class="chip" id="tb-sort-select" title="Sort Trade Board">
        <option value="surplus_desc">Surplus ($)</option>
        <option value="trade_desc">eFV grade (prospects)</option>
        <option value="age_asc">Youngest</option>
        <option value="age_desc">Oldest</option>
        <option value="fv_desc">FV</option>
        <option value="org_asc">Org</option>
        <option value="pos_asc">Position</option>
      </select>
    </div>
  </div>
  <div style="padding:8px 0 4px;">
    <input id="tb-search" type="search" placeholder="Search player name..." style="width:100%;max-width:340px;padding:7px 10px;border-radius:6px;border:1px solid var(--text-tertiary);background:var(--bg-secondary);color:var(--text-primary);" autocomplete="off" spellcheck="false">
  </div>
  <div id="tb-group-panel" style="display:none;margin:8px 0;padding:12px 16px;background:var(--bg-secondary);border:1px solid var(--border-subtle);border-radius:8px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span id="tb-group-title" style="font-weight:700;font-size:13px;"></span>
      <button onclick="document.getElementById('tb-group-panel').style.display='none';" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:16px;">&#10005;</button>
    </div>
    <div id="tb-group-body"></div>
  </div>
  <div id="tradeboard-content" data-csv-export="trade-board"><div class="spinner-wrap"><span class="spinner"></span></div></div>""")

# Legacy redirect shim for /projections/: the Trade Machine used to live here as
# a #view=trademachine tab. It is now its own top-level module at /trademachine/,
# but old bookmarks and inbound hash links (incl. the #tm=<seed> player deep-link)
# must still land on it. A hash change can't be caught by a server redirect, so
# this runs client-side on /projections/ and forwards, preserving the tm= seed.
_PROJ_TM_REDIRECT = """<script>
(function(){
  function forward(){
    var h=location.hash||'';
    if(!(/(?:^|[#&])(?:view|tab)=trademachine/.test(h) || /[#&]tm=/.test(h))) return;
    var m=/[#&]tm=([^&]+)/.exec(h);
    location.replace('/trademachine/' + (m?('#tm='+m[1]):''));
  }
  window.addEventListener('hashchange', forward);
  forward();
})();
</script>"""

# Standalone /trademachine/ init: mount the board on load, and re-mount on a
# hashchange so an inbound #tm=<seed> re-seeds the evaluator.
_TRADE_MACHINE_INIT = """<script>
(function(){
  function mount(){ if(window.TradeMachine && window.TradeMachine.mount) window.TradeMachine.mount(); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', mount); else mount();
  window.addEventListener('hashchange', mount);
})();
</script>"""


def build_projections() -> str:
    """The /projections/ MLB Projections app - the FA module's projection
    engine applied to the whole league plus post-ETA PROSPX prospects.
    Static shell + assets/projections.js, which fetches the proj_export.py
    sidecar (data/mlb_projections.json). Styles ride the .fa-app block plus
    a small .proj-app extension in site.css. The Trade Machine is now its own
    top-level module at /trademachine/ (a redirect shim forwards old
    #view=trademachine bookmarks there)."""
    body = (
        '<div class="fa-app proj-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}<h1>{_masthead_icon("projections")}MLB Projections '
        f'{_stage_chip("projections")}</h1></div>'
        f'<span class="section-sub">five-year {_gl("ewar", "eWAR")} paths for every MLB player · '
        f'{_gl("proj_buckets", "floor / mean / ceiling")} · surplus over the club control window, a longer guarantee through its last season · '
        'prospects join at their PROSPX ETA</span></div>'
        '<div id="proj-view-projections">'
        '<div id="proj-banner"></div>'
        '<div class="filter-bar" id="proj-filters"></div>'
        f'<div id="proj-rows"{_csv_optin("mlb-projections")}></div>'
        '</div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/projections.js?v={_PROJ_VER}" defer></script>'
        + _PROJ_TM_REDIRECT
    )
    return page("MLB Projections - eephus.io", "projections", body,
                "Five-year eWAR projections for every MLB player: floor, mean and ceiling paths, "
                "surplus over the club control window (every guaranteed season, unsigned seasons inside the five), and PROSPX prospects joining at their ETA.",
                url=f"{SITE_ORIGIN}/projections/")



def _arb_model_panel() -> str:
    """The Model section, SERVER-RENDERED so it is complete with JavaScript off.

    An accountability surface that needs a script to say what it measured is not
    an accountability surface. Same argument as assets/accountability.js:8-14.
    Reads data/arbitration_eval.json at BUILD time, so the artifact costs zero
    bytes on the wire.
    """
    import json as _json
    src = ROOT / "data" / "arbitration_eval.json"
    if not src.exists():
        return ('<div class="card arb-note"><p><strong>The gate has not been '
                'run.</strong> No eval artifact yet: nothing on this page is '
                'validated.</p></div>')
    try:
        ev = _json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ('<div class="card arb-note"><p>The evaluation artifact is '
                'unreadable.</p></div>')

    res = ev.get("results") or {}
    a6 = ev.get("a6_swartz") or {}
    pool = ev.get("pool") or {}

    def tile(num, lab, defn, tone="navy"):
        return (f'<div class="arb-tile arb-tile--{tone}">'
                f'<div class="arb-tilen">{html.escape(str(num))}</div>'
                f'<div class="arb-tilelab">{html.escape(lab)}</div>'
                f'<div class="arb-tiledef">{html.escape(defn)}</div></div>')

    tiles = []
    a1 = res.get("arb1") or {}
    a2 = res.get("arb2plus") or {}
    if a1:
        tiles.append(tile(
            "%.2fx" % (a1.get("gain_over_floor") or 0), "arb-1 vs its floor",
            "gain over an intercept-plus-WAR baseline, in multiples of the "
            "minimum detectable effect",
            "green" if a1.get("resolvable") else "orange"))
    if a2:
        tiles.append(tile(
            "%.2fx" % (a2.get("gain_over_floor") or 0), "arb-2+ vs its floor",
            "under 1.00 is a NULL against a step multiplier", "orange"))
    if a6.get("n"):
        tiles.append(tile(
            "%.1fx" % (a6.get("ratio_ours_over_swartz") or 0),
            "Swartz is more accurate",
            "on %d settled seasons with an MLB Trade Rumors projection"
            % a6["n"], "red"))
    tiles.append(tile(
        pool.get("rows", "-"), "scored player-seasons",
        "%s players over %s forward-chained folds"
        % (pool.get("players", "-"), pool.get("folds", "-"))))

    rows = []
    for name, r in res.items():
        ctl = r.get("a3_control") or {}
        rows.append(
            '<details class="arb-row"><summary class="arb-sum">'
            '<span class="arb-vd arb-vd--%s">%s</span> %s</summary><dl>'
            '<dt>baseline</dt><dd>%s</dd>'
            '<dt>MdAPE, model</dt><dd>%.4f</dd>'
            '<dt>MdAPE, baseline</dt><dd>%.4f</dd>'
            '<dt>gain</dt><dd>%+.5f</dd>'
            '<dt>floor (MDE95, one-sided)</dt><dd>%.5f</dd>'
            '<dt>gain over floor</dt><dd>%.2fx</dd>'
            '<dt>zero-information control</dt><dd>permuted p95 %+.5f, '
            'P(permuted at or above real) = %.3f</dd>'
            '<dt>paired rows</dt><dd>%d</dd></dl></details>'
            % ("pass" if r.get("verdict") == "PASS" else "null",
               html.escape(str(r.get("verdict", "?"))), html.escape(name),
               html.escape(str(r.get("bar_description", ""))),
               r.get("mdape_champion") or 0, r.get("mdape_bar") or 0,
               r.get("mdape_gain") or 0, r.get("mde95_onesided") or 0,
               r.get("gain_over_floor") or 0,
               ctl.get("permuted_p95") or 0, ctl.get("p_perm_ge_real") or 0,
               r.get("n_paired") or 0))

    losses = []
    for entry in ev.get("loss_ledger") or []:
        losses.append('<li><strong>%s</strong>: %s</li>'
                      % (html.escape(str(entry.get("claim", ""))),
                         html.escape(str(entry.get("statement", "")))))

    # The substitute-source agreement figures live in the artifact
    # (conventions.pool); this list names the limit and does not retype them.
    gaps = (
        "<ul>"
        "<li>It prices the SYSTEM, not the hearing: no filed figures, so a panel "
        "case is scored on its award alone.</li>"
        "<li>Steps before 2022 are reconstructed from substitute service-time "
        "sources: reported, NOT scored.</li>"
        "<li>2020 is never a label year (salaries paid at 60/162, reported on "
        "inconsistent bases).</li>"
        "<li>The CBA expires 2026-12-01. Seasons from 2027 assume the arbitration "
        "structure survives; no interval here covers that.</li>"
        "<li>Non-tendered players are absent, so summed projections OVERSTATE what "
        "a club owes.</li>"
        "</ul>")

    # DOWNSTREAM GATES. The salary path that prices every club-controlled
    # season on /projections/, /trademachine/ and the player card consumes this
    # model, and its gates write into the same artifact: GATE C (scored
    # 2026-08-19, the gate_c_verification block) and GATE C2 (registered
    # 2026-09-16, the gate_c2 block). Neither was rendered anywhere, so the
    # page never said that the coverage extension serving since 2026-09-17 has
    # no scored clause. Both lines read the artifact; an absent block is
    # printed as not scored, never as a pass.
    def _musd(v):
        return "$%.2fM" % (float(v) / 1e6) if v is not None else "-"

    downstream = []
    gc = ev.get("gate_c_verification") or {}
    if gc:
        c1 = gc.get("c1_per_player_vs_ladders") or {}
        mae = c1.get("mae_usd") or {}
        popn = gc.get("population") or {}
        vd = str(gc.get("verdict", "?"))
        downstream.append(
            '<details class="arb-row"><summary class="arb-sum">'
            '<span class="arb-vd arb-vd--%s">%s</span> GATE C, the surplus '
            'consumer (scored %s)</summary><dl>'
            '<dt>window MAE, served chain</dt><dd>%s</dd>'
            '<dt>window MAE, clemens_2026 ladder</dt><dd>%s</dd>'
            '<dt>window MAE, fitted ladder</dt><dd>%s</dd>'
            '<dt>paired players</dt><dd>%s</dd>'
            '<dt>scope</dt><dd>the %s no-contract rows priced when it '
            'shipped; the 2026-09-16 coverage extension is GATE C2</dd>'
            '</dl></details>'
            % ("pass" if vd == "PASS" else "null", html.escape(vd),
               html.escape(str(gc.get("scored_at", "?"))),
               _musd(mae.get("served")), _musd(mae.get("clemens_2026")),
               _musd(mae.get("fitted")), html.escape(str(c1.get("n_paired", "-"))),
               html.escape(str(popn.get("ship_day_count", "-")))))
    g2 = ev.get("gate_c2") or {}
    try:
        import salary_path as _sp
        sp_mode = str(_sp.SALARY_PATH_MODE)
    except Exception:
        sp_mode = "?"
    if g2:
        vd = str(g2.get("verdict", "?"))
        downstream.append(
            '<details class="arb-row"><summary class="arb-sum">'
            '<span class="arb-vd arb-vd--%s">%s</span> GATE C2, the '
            'club-control-window salary path (scored %s)</summary><dl>'
            '<dt>served mode</dt><dd>%s</dd></dl></details>'
            % ("pass" if vd == "PASS" else "null", html.escape(vd),
               html.escape(str(g2.get("scored_at") or g2.get("generated_at") or "?")),
               html.escape(sp_mode)))
    else:
        downstream.append(
            '<details class="arb-row" open><summary class="arb-sum">'
            '<span class="arb-vd arb-vd--null">NOT SCORED</span> GATE C2, the '
            'club-control-window salary path</summary><dl>'
            '<dt>served mode</dt><dd>%s</dd>'
            '<dt>status</dt><dd>Registered 2026-09-16 (docs/ARBITRATION_GATE.md '
            'section 11). None of its clauses has been scored, so the surplus '
            'the path prices on /projections/, /trademachine/ and the player '
            'card has no receipt yet.</dd></dl></details>'
            % html.escape(sp_mode))

    return (
        '<div class="arb-scorecard">%s</div>'
        '<div class="section-head"><h2>What was measured</h2>'
        '<span class="section-sub">pre-registered</span></div>'
        '%s'
        '<div class="section-head"><h2>Downstream gates</h2>'
        '<span class="section-sub">the salary path built on this model</span></div>'
        '%s'
        '<div class="section-head"><h2>Losses</h2></div>'
        '<ul class="arb-losses">%s</ul>'
        '<div class="section-head"><h2>What this model cannot tell you</h2></div>'
        '<div class="card arb-note">%s</div>'
        % ("".join(tiles), "".join(rows), "".join(downstream),
           "".join(losses) or "<li>No rejected variants recorded.</li>",
           gaps))


def build_arbitration() -> str:
    """The /arbitration/ module: what a club still owes its arbitration-eligible
    players, and how the arbitration market has priced them.

    Four sections. Projections and Team View read data/arbitration.json;
    Arbitration History lazily fetches data/arb_history.json on first open,
    because it is the bigger payload and most visits never open it; the Model
    section is server-rendered and needs no script at all."""
    body = (
        '<div class="fa-app mlbstats-app arb-app">'
        '<div class="section-head section-head--byline"><div class="section-head-titles">'
        + CREATED_BY_BANNER
        + '<h1>' + _masthead_icon("arbitration") + 'Arbitration Predictor ' + _stage_chip("arbitration") + '</h1></div>'
        '<span class="section-sub">Projected '
        + _gl("arb_award_model", "arbitration awards")
        + ' and the market record against comparables. Arb-1 beats its baseline; '
        'arb-2+ is a population multiplier because the model did not.</span></div>'
        '<div id="arb-caveatbar"></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Arbitration sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-arbsection="projections" role="tab" aria-selected="true" aria-controls="arb-panel-projections">Projections</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-arbsection="history" role="tab" aria-selected="false" aria-controls="arb-panel-history">Arbitration History</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-arbsection="teams" role="tab" aria-selected="false" aria-controls="arb-panel-teams">Team View</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-arbsection="model" role="tab" aria-selected="false" aria-controls="arb-panel-model">Model</button>'
        '</div>'
        '<div id="arb-panel-projections" class="mlbstats-section" role="tabpanel" aria-label="Projections">'
        '<div id="arb-app-root"' + _csv_optin("arbitration") + '></div>'
        '</div>'
        '<div id="arb-panel-history" class="mlbstats-section" role="tabpanel" aria-label="Arbitration History" hidden></div>'
        '<div id="arb-panel-teams" class="mlbstats-section" role="tabpanel" aria-label="Team View" hidden></div>'
        '<div id="arb-panel-model" class="mlbstats-section" role="tabpanel" aria-label="Model" hidden>'
        + _arb_model_panel() + '</div>'
        '</div>'
        '<script src="/assets/eephus-hub.js?v=' + _HUB_VER + '" defer></script>'
        '<script src="/assets/eephus-teampick.js?v=' + _TEAMPICK_VER + '" defer></script>'
        '<script src="/assets/arbitration.js?v=' + _ARB_VER + '" defer></script>'
    )
    return page("Arbitration Predictor - eephus.io", "arbitration", body,
                "Projected arbitration salaries for every eligible MLB player, "
                "and a per-season record of who the arbitration market overpaid "
                "and underpaid.",
                url=SITE_ORIGIN + "/arbitration/")


def build_trademachine() -> str:
    """The /trademachine/ Trade Machine module (top-level, module by Anirudh
    Iyer). Build and value a deal both ways - prospects on eFV surplus, MLB
    players on projection surplus - then the full Bayesian trade-value board.
    Static shell + assets/trademachine.js on the standalone trade_values.json /
    mlb_projections.json data. Was formerly a #view=trademachine tab inside MLB
    Projections."""
    body = (
        # id="proj-view-trademachine" is kept for trademachine.js, which scopes its
        # filter + collapse wiring to that id; .tm-app carries the standalone theming.
        '<div class="fa-app proj-app tm-app" id="proj-view-trademachine">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}<h1>{_masthead_icon("trademachine")}Trade Machine '
        f'{_stage_chip("trademachine")}</h1></div>'
        f'<span class="section-sub">{_gl("surplus_value", "surplus")} in one currency: prospects on eFV, '
        'MLB players on projections, then the Bayesian trade-value board</span></div>'
        + _TRADE_MACHINE_BODY +
        '</div>'
        f'<link rel="stylesheet" href="/assets/trademachine.css?v={_TM_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/trademachine.js?v={_TM_VER}" defer></script>'
        + _TRADE_MACHINE_INIT
    )
    return page("Trade Machine - eephus.io", "trademachine", body,
                "Value MLB trades in one currency: prospects on eFV surplus, MLB players on "
                "projection surplus, plus a Bayesian trade-value board (contract-aware, "
                "positional scarcity, opt-out adjusted).",
                url=f"{SITE_ORIGIN}/trademachine/")

def build_mlbstats() -> str:
    """The /mlbstats/ MLB Stats module - league-wide MLB stat leaderboards.
    Six sections, one tab each, in the order a reader asks for them: Overall
    (eWAR, war_board_export.py: whole players, batting plus pitching on one
    board, plus the club rollup on both of its named bases), Hitters (HEM+,
    hitter_export.py), Starters (SEM+, starter_export.py), Bullpen (REM+,
    bullpen_export.py), Defense (DEM+, defense_export.py) and Leverage (WPA,
    leverage_export.py). Overall is FIRST and is what a bare /mlbstats/ URL
    opens (owner decision 2026-09-17); its hash value is still `war`, so every
    link ever copied off this page still opens what it named, and
    assets/mlbstats.js carries the same default in one place (`var section`).
    Static shell +
    assets/mlbstats.js, which lazy-fetches each section's data/*_leaderboards.json
    and *_history.json on first activation. Every section root opts into the
    Download CSV control (_csv_optin), which exports the columns on screen:
    hidden view columns carry data-export-skip. Styles ride the .fa-app block plus
    the .mlbstats-app extension in site.css; the Defense section reuses the
    existing board and depth-card classes, so it adds no CSS."""
    body = (
        # .mlbx is carried by THIS root only: every /mlbstats/ column-view rule in
        # site.css is scoped under it, because .mlbstats-app is shared by ten
        # module roots (test_mlbx_css_scope.py pins the scope).
        '<div class="fa-app mlbstats-app mlbx">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("mlbstats")}MLB Stats {_stage_chip("mlbstats")}</h1></div>'
        f'<span class="section-sub">Every player by {_gl("ewar", "eWAR")}, then hitters '
        f'({_gl("hem_plus", "HEM+")}), starters ({_gl("sem_plus", "SEM+")}), relievers '
        f'({_gl("rem_plus", "REM+")}), fielders ({_gl("dem_plus", "DEM+")}) and leverage '
        f'({_gl("wpa", "WPA")}), with team rollups. One season or a '
        f'{_gl("range", "year range")}. '
        '100 is league average on every + scale.</span></div>'
        # Section nav (built as a tablist; sections join here as they ship).
        # Short labels: the section is the noun, "Leaderboards" was the noise,
        # and the phone strip reads at a glance (2026-09-11 overhaul, wave 2).
        #
        # ORDER AND LANDING, owner decision 2026-09-17: the whole player first,
        # then the bats, then the two halves of the pitching staff, then the two
        # context boards. Overall carries `active` and its panel is the one that
        # is not `hidden`; assets/mlbstats.js opens the same section in `var
        # section`. The two have to move together, because readHash paints the
        # active tab from a deep link and a shell that disagrees would light the
        # wrong one. The hash VALUE stays `war`: renaming it would break every
        # link ever copied, and the label is what the owner asked to change.
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="MLB Stats sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-mlbsection="war" role="tab" aria-selected="true" aria-controls="mlbstats-section-war">Overall</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mlbsection="hitters" role="tab" aria-selected="false" aria-controls="mlbstats-section-hitters">Hitters</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mlbsection="starters" role="tab" aria-selected="false" aria-controls="mlbstats-section-starters">Starters</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mlbsection="bullpen" role="tab" aria-selected="false" aria-controls="mlbstats-section-bullpen">Bullpen</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mlbsection="defense" role="tab" aria-selected="false" aria-controls="mlbstats-section-defense">Defense</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mlbsection="leverage" role="tab" aria-selected="false" aria-controls="mlbstats-section-leverage">Leverage</button>'
        '</div>'
        # Panel order follows the nav, so tab order and reading order agree.
        '<div id="mlbstats-section-war" class="mlbstats-section" role="tabpanel" aria-label="Overall">'
        f'<div id="mlbstats-war-root"{_csv_optin("mlb-ewar")}></div>'
        '</div>'
        '<div id="mlbstats-section-hitters" class="mlbstats-section" role="tabpanel" aria-label="Hitters" hidden>'
        f'<div id="mlbstats-hitters-root"{_csv_optin("mlb-hitters")}></div>'
        '</div>'
        '<div id="mlbstats-section-starters" class="mlbstats-section" role="tabpanel" aria-label="Starters" hidden>'
        f'<div id="mlbstats-starters-root"{_csv_optin("mlb-starters")}></div>'
        '</div>'
        '<div id="mlbstats-section-bullpen" class="mlbstats-section" role="tabpanel" aria-label="Bullpen" hidden>'
        '<div id="mlbstats-banner"></div>'
        f'<div id="mlbstats-app-root"{_csv_optin("mlb-leaderboards")}></div>'
        '</div>'
        '<div id="mlbstats-section-defense" class="mlbstats-section" role="tabpanel" aria-label="Defense" hidden>'
        f'<div id="mlbstats-defense-root"{_csv_optin("mlb-defense")}></div>'
        '</div>'
        '<div id="mlbstats-section-leverage" class="mlbstats-section" role="tabpanel" aria-label="Leverage" hidden>'
        f'<div id="mlbstats-leverage-root"{_csv_optin("mlb-leverage")}></div>'
        '</div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/mlbstats.js?v={_MLBSTATS_VER}" defer></script>'
    )
    return page("MLB Stats - eephus.io", "mlbstats", body,
                "MLB leaderboards from eephus.io: every player by eWAR over one season or a year "
                "range, HEM+ hitters, SEM+ starters, REM+ relievers and RIV+ impact, DEM+ "
                "fielders, WPA leverage, and team Bullpen+, Rotation+, Offense+ and DEM+.",
                url=f"{SITE_ORIGIN}/mlbstats/")

_PAL_REVERSED_LABEL = {
    "neg_era_pre": "high pre-season ERA",
    "kbb_pre": "low pre-season K-BB%",
    "index_pre": "a low pre-season quality index",
}


def _pal_gate_clause(gate: dict, key: str) -> str:
    """One masthead clause per direction, derived from the gate block that
    pal_export carries out of data/pal_eval.json. Mirrors pal.js verdictPhrase:
    a failing direction is a screen, a passing one is validated unless the
    reversed (regression-to-the-mean) read of a registered baseline beats FIT,
    in which case the clause says the gate passed and names that read."""
    d = ((gate or {}).get("per_direction") or {}).get(key) or {}
    if not isinstance(d.get("pass"), bool):
        return "has no gate verdict in this build"
    if not d["pass"]:
        return "is a screen, not a ranking"
    if d.get("reversed_beats_fit") is True:
        lab = _PAL_REVERSED_LABEL.get(d.get("reversed_baseline"), str(d.get("reversed_baseline")))
        return f"passed its gate, though a sort on {html.escape(lab)} ranks the same events higher"
    return "is validated"


def build_pal() -> str:
    """The /pal/ Alchemy Lab - role-conversion evaluation for MLB players.
    Both halves of the surface now ship. Pitcher role conversion:
    RP->SP Candidates (which relievers profile as
    starters), SP->RP Candidates (which starters would shine in relief), and
    Conversion History (an archive of past SP<->RP switches that doubles as
    the model's backtest set, plus pitch-mix changes). Backtest evidence is
    per direction: SP->RP validated, RP->SP structural screen only.
    Hitter positional conversion: Position Fit (which hitters are worth more
    runs at a different position), from the positional_fit.py conversion model.
    Static shell + assets/pal.js, which fetches the pal_export.py sidecar
    (data/pal.json) plus the slim positional-fit view built here
    (data/positional_fit_ui.json - the full artifact never ships). Reuses the
    arsenal / velocity / platoon Statcast data, the validated REM+ model, and
    PROSPX prospect role history. Styles ride the .fa-app block plus the
    .mlbstats-app / .pal-app extensions in site.css."""
    # The masthead verdicts are READ from data/pal.json backtest.gate (final
    # pass M07-01): the line was static text, the one validity word on /pal/
    # that could not move with the gate artifact.
    gate = (_cached_data_json("pal.json").get("backtest") or {}).get("gate") or {}
    body = (
        '<div class="fa-app mlbstats-app pal-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("pal")}Alchemy Lab {_stage_chip("pal")}</h1></div>'
        f'<span class="section-sub">Role and position {_gl("pal_conversion", "conversions")}. '
        f'{_gl("sp_rp_fit", "SP to RP")} {_pal_gate_clause(gate, "SP->RP")}; '
        f'{_gl("rp_sp_fit", "RP to SP")} {_pal_gate_clause(gate, "RP->SP")}; '
        'position fit is validated for the size of a move, not for which players clubs move.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="PAL sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-palsection="rp2sp" role="tab" aria-selected="true" aria-controls="pal-section">RP&rarr;SP Candidates</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="sp2rp" role="tab" aria-selected="false" aria-controls="pal-section">SP&rarr;RP Candidates</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="posfit" role="tab" aria-selected="false" aria-controls="pal-section">Position Fit</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="history" role="tab" aria-selected="false" aria-controls="pal-section">Conversion History</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="pitchadd" role="tab" aria-selected="false" aria-controls="pal-section">Pitch-Add Lab</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="platoon" role="tab" aria-selected="false" aria-controls="pal-section">Reverse-Platoon Radar</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="prospects" role="tab" aria-selected="false" aria-controls="pal-section">Prospect Watch</button>'
        '</div>'
        '<div id="pal-section" class="mlbstats-section" role="tabpanel" aria-label="Alchemy Lab">'
        '<div id="pal-banner"></div>'
        f'<div id="pal-app-root"{_csv_optin("alchemy-lab")}></div>'
        '</div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/pal.js?v={_PAL_VER}" defer></script>'
    )
    # META PROVENANCE, corrected 2026-08-05. The old string ended "a fitted
    # positional ladder, computed from Statcast" and page() feeds this one
    # literal to name=description, og:description AND twitter:description, so
    # one wrong clause was published three times. The ladder is NOT Statcast:
    # positional_fit.fit_ladder is a no-intercept least squares of
    # Baseball-Reference's own runs_position per 650 PA on the player's innings
    # SHARES, which RECOVERS the constants BRef used (r2 0.9759, 4,968
    # player-seasons 2012-2026, min 200 PA; data/positional_fit_ui.json
    # ladder.method says exactly this, and the Position Fit tab shows it).
    # Statcast feeds other parts of the page - arsenal shape, velocity, platoon
    # splits, and the OAA the fielding side reads - so the attribution is split
    # rather than deleted. The tab list also went stale: Pitch-Add Lab,
    # Reverse-Platoon Radar and Prospect Watch all shipped after the copy was
    # written and were invisible to a search snippet. Length 270 chars after
    # the 2026-09-11 copy pass (296 before it, 325 before that); this page has
    # seven surfaces to name.
    return page("Alchemy Lab - eephus.io", "pal", body,
                "MLB role and position conversions: reliever-to-starter and starter-to-relief "
                "candidates, position fit, pitch-add, reverse-platoon and prospect boards, and the "
                "conversion backtest. Arsenals and velocity from Statcast; the positional ladder "
                "fitted from Baseball-Reference.",
                url=f"{SITE_ORIGIN}/pal/")

def _fantasy_panel(mod: str, blurb: str, bar: str, nav_label: str,
                   tabs: list[tuple[str, str]], csv_name: str,
                   active: bool) -> str:
    """One sub-module panel inside the combined /fantasy/ shell.

    THE IDS ARE THE MODULE'S OWN, ALWAYS. Every client resolves its mount
    through a candidate list that ends at the fantasy-era `fantasy-app-root`;
    on three separate pages that fallback was harmless tolerance, and in one
    document it is a triple-mount, because all three would resolve to the same
    node and the last paint would win. The fallback ids appear nowhere in this
    shell, and test_diamond_scaffold asserts that absence rather than trusting
    it.

    `bar` is the module's control slot above its section nav. It is a SLOT, not
    a fixture: the client empties it on the tabs its control cannot move, and a
    `:empty` rule takes the emptied slot out of layout."""
    btns = "".join(
        f'<button type="button" class="mlbstats-sectionbtn{" active" if i == 0 else ""}" '
        f'data-{mod}section="{key}" role="tab" '
        f'aria-selected="{"true" if i == 0 else "false"}">{label}</button>'
        for i, (key, label) in enumerate(tabs))
    return (
        f'<div class="fantasy-mod" id="fantasy-mod-{mod}" data-fantasypanel="{mod}" '
        f'role="tabpanel" aria-label="{nav_label}"{"" if active else " hidden"}>'
        f'<span class="section-sub fantasy-modsub">{blurb}</span>'
        f'{bar}'
        f'<div class="mlbstats-sectionnav" role="tablist" aria-label="{nav_label} sections">{btns}</div>'
        f'<div id="{mod}-section" class="mlbstats-section">'
        f'<div id="{mod}-banner"></div>'
        f'<div id="{mod}-app-root"{_csv_optin(csv_name)}></div>'
        '</div></div>'
    )


def build_fantasy() -> str:
    """/fantasy/ - one module, three sub-modules, one page.

    HISTORY, because both directions of this were deliberate. /fantasy/ was one
    page with nine tabs until 2026-08-05, when it split into /dynasty/,
    /redraft/ and /dfs/ over three named defects: one scoring selector sitting
    above surfaces it could not move, one flat hash namespace, and the dynasty
    board buried behind seven rest-of-season tabs. On 2026-08-07 the owner
    asked for one Fantasy module again. This shell is the shape that satisfies
    both: ONE page and one nav entry, with each sub-module keeping its own
    section nav, its own control slot and its own hash namespace, so none of
    the three defects comes back with the merge.

    WHAT MAKES IT SAFE TO PUT THREE CLIENTS IN ONE DOCUMENT:

      * mount ids are per module and the shared fantasy-era fallback ids are
        absent (see _fantasy_panel),
      * the address bar belongs to assets/fantasy-hub.js, which owns the
        "#m=<module>" prefix and hands each client only its own half,
      * only the active client is downloaded, on first activation, off the
        data-src stamps on the module bar. data/fantasy.json is 576KB and
        data/dfs.json 253KB, and a reader who opens the ROS board should pay
        for neither of the other two.

    Section keys, which are the contract with the clients (syncTabs compares
    the nav attribute value against the client's own canonical name):
      redraft  streamers | two_start | ros_sp | ros_rp | ros_hitter | buysell | closers
      dynasty  dynasty | callups | keeper | fantasy_rank
      dfs      slate | value | optimizer | stacks
    """
    redraft = _fantasy_panel(
        "redraft",
        "Rest-of-season ranks and daily streamers in your scoring format (Ottoneu FanGraphs "
        "Points default, SABR Points, Old School 5x5, Ottoneu 4x4). Projections from the MLB "
        f"Projections engine; matchup context from {_gl('rem_plus', 'REM+')}, "
        f"{_gl('sem_plus', 'SEM+')}, {_gl('hem_plus', 'HEM+')}, Offense+ and Bullpen+.",
        # redraft.js fills this from data/fantasy.json scoring_catalog, and only
        # on the three tabs S.system can actually move.
        '<div id="redraft-scoring" class="fantasy-scoring-bar" aria-label="League scoring format"></div>',
        "Redraft",
        [("streamers", "Daily Streamers"), ("two_start", "Two-Start SP"),
         ("ros_sp", "ROS SP"), ("ros_rp", "ROS RP"), ("ros_hitter", "ROS Hitters"),
         ("buysell", "Buy / Sell"), ("closers", "Closer Grid")],
        "redraft-board", True)
    dynasty = _fantasy_panel(
        "dynasty",
        f"Dynasty and keeper value: prospects ranked on {_gl('xfv', 'eFV')}, blended with star "
        "odds, bust risk, ETA and surplus. The board ranks prospects only. Call-up Watch flags who "
        "is next. Fantasy Rank ranks MLB players and prospects on projected fantasy value in your "
        "format, not on WAR. The keeper calculator compares a rank with the pick a keeper costs, "
        "in a prospects-only draft or, on its All players pool, a draft of both.",
        # dynasty.js fills this with the LENS control (board order / contending
        # / rebuilding) on the Dynasty Board, which is graded and has no
        # scoring formats, and with the FORMAT control on the Fantasy Rank and
        # the keeper's All players pool (2026-10-01). The class stays as-is
        # because redraft.js and dynasty.js style .fantasy-scoring-bar and
        # .dyn-lensbar independently.
        '<div id="dynasty-scoring" class="fantasy-scoring-bar" aria-label="Board lens or scoring format"></div>',
        "Dynasty",
        [("dynasty", "Dynasty Board"), ("callups", "Call-up Watch"),
         ("keeper", "Keeper Calculator"), ("fantasy_rank", "Fantasy Rank")],
        "dynasty-board", False)
    dfs = _fantasy_panel(
        "dfs",
        "Today's slate: the Redraft engine re-scored per game for the probable pitcher, park and "
        "bullpen. Paste or import your DFS salaries and the optimizer builds against them. No "
        "salary feed is scraped.",
        # No slot: the contest-format selector renders inline at the top of the
        # DFS section, which is where it was before the merge.
        "",
        "DFS",
        [("slate", "Today's Slate"), ("value", "Value Plays"),
         ("optimizer", "Lineup Optimizer"), ("stacks", "Stacks")],
        "dfs-slate", False)
    modbar = (
        '<div class="fantasy-modbar" role="tablist" aria-label="Fantasy modules">'
        f'<button type="button" class="fantasy-modbtn active" data-fantasymodule="redraft" '
        f'data-src="/assets/redraft.js?v={_REDRAFT_VER}" role="tab" aria-selected="true" '
        'aria-controls="fantasy-mod-redraft">Redraft'
        '<span class="fh-modsub">Rest of season</span></button>'
        f'<button type="button" class="fantasy-modbtn" data-fantasymodule="dynasty" '
        f'data-src="/assets/dynasty.js?v={_DYNASTY_VER}" role="tab" aria-selected="false" '
        'aria-controls="fantasy-mod-dynasty">Dynasty'
        '<span class="fh-modsub">Keepers and prospects</span></button>'
        f'<button type="button" class="fantasy-modbtn" data-fantasymodule="dfs" '
        f'data-src="/assets/dfs.js?v={_DFS_VER}" role="tab" aria-selected="false" '
        'aria-controls="fantasy-mod-dfs">DFS'
        "<span class=\"fh-modsub\">Tonight's slate</span></button>"
        '</div>'
    )
    body = (
        '<div class="fa-app mlbstats-app fantasy-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("fantasy")}Fantasy {_stage_chip("fantasy")}</h1></div>'
        '<span class="section-sub">Redraft, dynasty and DFS on one projection engine.</span>'
        f'{_partof_diamond()}</div>'
        f'{modbar}{redraft}{dynasty}{dfs}'
        '</div>'
        # Inline (non-defer), so it runs at parse time and is guaranteed to be
        # set before any deferred client below reads it: the corpus, the DFS
        # slate and the card's two history boards fetch under content-stamped
        # URLs instead of forced revalidation. See _data_vers_script.
        f'{_data_vers_script(FANTASY_DATA_STAMPS)}'
        f'{DIAMOND_CONFIG_SCRIPT}'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/fantasy-card.js?v={_FANTASY_CARD_VER}" defer></script>'
        # LAST, and the only client-side script the shell names. It injects one
        # of the three module clients on first activation; their stamps ride the
        # data-src attributes above.
        f'<script src="/assets/fantasy-hub.js?v={_FANTASY_HUB_VER}" defer></script>'
    )
    return page("Fantasy - eephus.io", "fantasy", body,
                "Fantasy baseball from eephus.io: redraft ranks in your league format, an eFV-graded "
                "dynasty and keeper board, and a DFS slate with per-game projections and a lineup "
                "optimizer.",
                url=f"{SITE_ORIGIN}/fantasy/")


def _fantasy_redirect(title: str, module: str, label: str) -> str:
    """A retired fantasy page dir, kept as a HASH-PRESERVING redirect stub.

    Same shape as build_teams_redirect(), with one addition it does not need:
    these three URLs were the addresses of working boards for two days and
    people bookmarked deep links into them, so the stub carries the incoming
    hash across instead of dropping the reader on the module's default tab.
    `/redraft/#section=ros_sp&sys=sabr` becomes
    `/fantasy/#m=redraft&section=ros_sp&sys=sabr`, and the coordinator on the
    other side accepts the un-namespaced form too, so a hash this script cannot
    carry (JS off, meta refresh wins the race) still resolves.

    The dirs STAY in deploy/publish_paths.txt. A redirect that does not ship is
    a 404, which is the whole reason the stub exists."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - eephus.io</title>
{FAVICON_LINKS}
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=/fantasy/#m={module}">
<script>(function(){{var h=(location.hash||"").replace(/^#/,"").replace(/(^|&)m=[^&]*/g,"").replace(/^&+/,"");
location.replace("/fantasy/#m={module}"+(h?"&"+h:""));}})();</script>
</head><body>
<p style="font-family:monospace;padding:2rem;">{html.escape(label)} moved into
<a href="/fantasy/#m={module}">Fantasy &rarr; {html.escape(label)}</a>.</p>
</body></html>
"""

# --------------------------------------------------------------------------- #
# The Diamond section (2026-08-05, fantasy merged back 2026-08-07)
# --------------------------------------------------------------------------- #
# Four pages, one group in the nav, all of them PUBLIC. The gate flag exists
# (assets/diamond-config.js) and is OFF; nothing on these pages is withheld
# from anyone. Each shell is the build_fantasy shape it was cloned from:
# masthead + stage chip + section nav + a banner div + an app root, then the
# module's own deferred JS. Every shell is written to survive its app (and its
# data sidecar) not being there yet: the app root is empty until an app fills
# it, and each app owns its own loud empty state.
#
# Section keys are the CONTRACT between these shells and those apps. They are
# spelled out per builder; the data attribute is data-<module>section and the
# three ids are <module>-section / <module>-banner / <module>-app-root.
#
# /dynasty/, /redraft/ and /dfs/ were pages of their own for two days and are
# redirect stubs now. They still BUILD and still SHIP, because the addresses
# were public and a redirect that does not ship is a 404.
# --------------------------------------------------------------------------- #

def _diamond_cfg(src: str | None = None) -> dict:
    """The Diamond prices and the gate flag, parsed at build time OUT OF the
    one file that owns them (assets/diamond-config.js). build_diamond() used
    to carry the same numbers as literals in three places (the money card, the
    FAQ, the meta description), which is exactly the drift a single-source
    config exists to prevent: the served page could disagree with the flag the
    client reads. A missing key is a BUILD FAILURE, not a default, because a
    pricing page that guesses its own price is worse than a build that stops.

    `src` exists for tests; the default reads the shipped config."""
    if src is None:
        src = (ROOT / "assets" / "diamond-config.js").read_text(encoding="utf-8")
    out: dict = {}
    for key, pat, conv in (
        ("gating", r"gating:\s*(true|false)\b", lambda s: s == "true"),
        ("price_usd_month", r"price_usd_month:\s*([0-9]+(?:\.[0-9]+)?)", float),
        ("founding_rate_usd", r"founding_rate_usd:\s*([0-9]+(?:\.[0-9]+)?)", float),
    ):
        m = re.search(pat, src)
        if m is None:
            raise ValueError(
                f"assets/diamond-config.js carries no {key}; /diamond/ prices "
                "itself off that file and refuses to guess")
        out[key] = conv(m.group(1))
    # The per-module preview caps (2026-08-16), OPTIONAL where the three price
    # keys are not: no build reads them yet (the client-side reader is
    # EephusDiamond.previewRows), so a config without the map parses fine and
    # the older config fixtures in the tests stay valid.
    m = re.search(r"preview_rows:\s*\{([^}]*)\}", src)
    if m is not None:
        out["preview_rows"] = {
            k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", m.group(1))}
    return out


def _usd(v: float) -> str:
    """Price copy, not math display: $15 stays $15 (never $15.0), $9.99 stays
    $9.99. The dollar sign is the caller's."""
    return str(int(v)) if float(v).is_integer() else f"{float(v):.2f}"


def _betting_serve_clv() -> bool:
    """betting_export.SERVE_CLV, read at build time: the one switch that says
    whether the record is graded against the closing line. The shell copy on
    /betting/ and /diamond/ reads it here rather than repeating a sentence the
    owner retired on 2026-09-07 (M12-04, 2026-09-25). An import failure reads
    as off, because off is the served state and the weaker claim."""
    try:
        import betting_export
    except Exception:  # noqa: BLE001 - any import failure is the off state
        return False
    return bool(getattr(betting_export, "SERVE_CLV", False))


def _betting_grading_clause(short: bool = False) -> str:
    """How the public record is graded, in the words the served flag allows."""
    if _betting_serve_clv():
        return "graded against the close" if short else "graded against the closing line"
    return "graded on realized results"


def _partof_diamond(extra: str = "") -> str:
    """One masthead line under each Diamond module naming the pass it belongs
    to. Gating-aware so the line cannot promise a free preview after the flag
    flips: the free clause renders only while diamond-config.js ships
    gating false. `extra` is a plain-words status tail (the retired /cards/
    masthead carried its frozen-index note through it)."""
    free = "" if _diamond_cfg()["gating"] else " Free during the founding preview."
    tail = f" {html.escape(extra)}" if extra else ""
    return (f'<span class="section-sub">Part of <a href="/diamond/">Diamond</a>.'
            f'{html.escape(free)}{tail}</span>')


def _diamond_ledger_card() -> str:
    """The Model Ledger tally, server-rendered on /diamond/. The report card
    is the product, so the pass page carries the same verdict split the
    homepage strip counts, off the same registry, at build time. Deprecated
    rows are in the sentence on purpose: a ledger that only lists its wins is
    an ad, not a ledger."""
    try:
        reg = model_registry.load()
    except (OSError, ValueError):
        return ""
    tally: dict = {}
    for m in reg.get("models") or []:
        tally[m.get("verdict")] = tally.get(m.get("verdict"), 0) + 1
    total = sum(tally.values())
    if not total:
        return ""
    counts = ", ".join(
        f"{tally.get(k, 0)} {k}"
        for k in ("validated", "provisional", "unvalidated", "deprecated"))
    return (
        '<div class="card diamond-get">'
        '<h3><a href="/models/">Model ledger</a></h3>'
        f'<p>{total} models carry a predictive claim and a registry row: {counts}. '
        'Deprecated rows are shown on purpose.</p>'
        '<p class="diamond-fine">Counted at build time from data/model_registry.json.</p>'
        '</div>')


def build_dynasty() -> str:
    return _fantasy_redirect("Dynasty", "dynasty", "Dynasty")


def build_redraft() -> str:
    return _fantasy_redirect("Redraft", "redraft", "Redraft")


def build_dfs() -> str:
    return _fantasy_redirect("DFS", "dfs", "DFS")


def build_betting() -> str:
    """/betting/ - model probabilities against book prices. assets/betting.js
    reads data/betting.json (model win probabilities and edges) and
    data/betting_record.json (the append-only public record).

    THE RAILS ARE PART OF THE PAGE, not a footnote. BETTING_DISCLAIMER renders
    ABOVE the boards, not below them, so nobody reaches a pick without passing
    it. There are no affiliate links here and there never will be without legal
    review. The record is append-only and graded on the basis
    betting_export.SERVE_CLV names (realized results while CLV is retired), so
    it can embarrass us; that is the point of publishing it.

    THE SECTION IDS ARE A THREE-FILE CONTRACT. The `data-bettingsection` values
    below, `SECTIONS` in assets/betting.js and
    test_betting.py::test_shell_section_ids_match_the_client move together, and
    that test compares the two sets: a tab added here and nowhere else renders a
    button that does nothing, and a section added in the client and not here is
    unreachable except by hash.

    Section keys: potd | teams | props | parlays | calculators | record |
    validation | futures | mybets.

    FUTURES IS A TAB AND NOT A PAGE, deliberately. It renders the season-long
    outright board off data/futures.json and there is NO MARKET beside it: no
    futures price has ever been captured, so there is no edge column and the
    tab says which capture is missing rather than estimating one. A tab costs
    two lines here and one in the client; a page would cost the nav, the three
    hand-authored nav copies, the sitemap, the deploy list, the dash stripper
    and the route notes, for a surface that cannot yet make a betting claim."""
    body = (
        '<div class="fa-app mlbstats-app betting-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("betting")}Sports Betting {_stage_chip("betting")}</h1></div>'
        f'<span class="section-sub">Model probability vs the {_gl("devig", "de-vigged")} book price. '
        'Each published pick records its timestamp, book, odds and a flat one-unit stake; the '
        'record is append-only and '
        + (f'graded against the {_gl("clv", "closing line")}.' if _betting_serve_clv()
           else "graded on realized results.")
        + '</span>'
        f'{_partof_diamond()}</div>'
        f'{BETTING_DISCLAIMER}'
        # THE FEED-HEALTH STRIP, ABOVE THE TABS. betting.js paints it from
        # status.feed_health on every load, including the load where the payload
        # 404'd. It is above the nav rather than inside the section because the
        # state it reports ("no close snapshot has ever been captured, so no
        # pick on this page can ever be CLV-graded") is true on every tab, and a
        # strip that lived inside the section would only be true on one of them.
        '<div id="betting-feedhealth"></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Sports Betting sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-bettingsection="potd" role="tab" aria-selected="true">Pick of the Day</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="teams" role="tab" aria-selected="false">Team Bets</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="props" role="tab" aria-selected="false">Player Props</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="parlays" role="tab" aria-selected="false">Parlays</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="calculators" role="tab" aria-selected="false">Calculators</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="record" role="tab" aria-selected="false">The Record</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="validation" role="tab" aria-selected="false">Validation</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="futures" role="tab" aria-selected="false">Futures</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="mybets" role="tab" aria-selected="false">My Bets</button>'
        '</div>'
        '<div id="betting-section" class="mlbstats-section">'
        '<div id="betting-banner"></div>'
        f'<div id="betting-app-root"{_csv_optin("betting-board")}></div>'
        '</div>'
        '</div>'
        f'{DIAMOND_CONFIG_SCRIPT}'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/betting.js?v={_BETTING_VER}" defer></script>'
    )
    return page("Sports Betting - eephus.io", "betting", body,
                "MLB betting model from eephus.io: game win probabilities against de-vigged book "
                "prices, every bet on the slate in one sortable board, a flat-stake public record, "
                "betting calculators, and a personal bet tracker. 21+, informational only.",
                url=f"{SITE_ORIGIN}/betting/")



def build_diamond() -> str:
    """/diamond/ - the Diamond Pass page.

    A marketing page that tries very hard not to read like one. The structure
    is server-rendered here so the page is complete with JavaScript off; the
    LIVE numbers (the eFV scoreboard receipts and the betting record card) are
    filled in by assets/diamond.js from the artifacts themselves, because a
    hardcoded accuracy claim is a claim that rots.

    Copy rules the owner set, enforced here rather than in review:
      1. Public framing is "Diamond funds the free site". The internal
         subsidy framing does not appear on this page.
      2. Nothing is gated today. The page says that plainly instead of
         implying a paywall exists.
      3. PRICES AND THE GATE FLAG COME FROM _diamond_cfg(), never from
         literals here (2026-08-16): the page renders the copy variant the
         parsed flag selects, so the day assets/diamond-config.js flips to
         gating true, this page stops claiming a free preview without anyone
         remembering to edit it.
      4. The member list is Fantasy + Sports Betting (owner de-list
         2026-08-16): /prospx/ is a free page and does not belong on a "what
         members get" list, and the Card Market left the pass until a
         licensed price source is wired. The FAQ says where it went."""
    cfg = _diamond_cfg()
    gated = cfg["gating"]
    price = _usd(cfg["price_usd_month"])
    founding = _usd(cfg["founding_rate_usd"])
    if gated:
        money = (
            '<div class="card diamond-price">'
            f'<h3>${price} a month</h3>'
            f'<p>Diamond is live at ${price} a month. The rest of eephus.io stays free.</p>'
            f'<p>Founding members (preview users) pay ${founding} a month, held for a year.</p>'
            '<p class="diamond-fine">Diamond funds the free site: the board, projections, free agency '
            'model, glossary and articles stay open to everyone.</p>'
            '</div>'
        )
    else:
        money = (
            '<div class="card diamond-price">'
            f'<h3>${price} a month, when it goes live</h3>'
            f'<p>Nothing is for sale today. At launch Diamond is ${price} a month; the rest of '
            'eephus.io stays free.</p>'
            f'<p>Founding rate: ${founding} a month, held for a year, for everyone using the preview.</p>'
            '<p class="diamond-fine">Diamond funds the free site: the board, projections, free agency '
            'model, glossary and articles stay open to everyone.</p>'
            '</div>'
        )
    gets = [
        # TWO cards (owner de-list 2026-08-16). /prospx/ came off because it is
        # a free page, and a free page on a "what members get" list was the one
        # dishonest card here. The Card Market module was REMOVED on 2026-09-05
        # (owner decision: no feasible price source with the current data); the
        # FAQ carries the honest line about where it went.
        ("Fantasy", "/fantasy/",
         "Redraft ranks in your scoring format, streamers, two-start pitchers and buy / sell; "
         "the dynasty board and keeper calculator; DFS projections and the lineup optimizer on "
         "your salaries."),
        ("Sports Betting", "/betting/",
         "Model prices on every game, the pick of the day, calculators, and the record "
         f"{_betting_grading_clause(short=True)}."),
    ]
    # THE EXTRAS, REWRITTEN AGAINST WHAT EXISTS (2026-08-05).
    #
    # Three of these four were claims with nothing behind them on a page whose
    # entire argument is receipts over claims, which made them the most
    # expensive copy on the site. Each now carries a state, and the state is the
    # truth:
    #   live    it works today and the card links to it
    #   partial the thing that produces the data exists and ships; the
    #           member-facing half does not, and the card says which half
    #   planned nothing is built. Named as an intention, never as a benefit.
    # `href` is None for anything not yet linkable, so a "planned" card cannot
    # accidentally become a link to a page that does not exist.
    extras = [
        ("Data exports and a JSON API", "live", "/sources/#api",
         "Every model artifact is public static JSON with a documented catalog (contents, "
         "cadence, stability). Every board has a Download CSV control."),
        ("eFV movement alerts", "partial", "/data/efv_alerts.json",
         "Published every rebuild: the biggest genuine eFV moves with their drivers. No "
         "delivery yet: following players needs the account layer, which is off."),
        ("The DFS lineup optimizer", "live", "/fantasy/#m=dfs&section=optimizer",
         "Salary-cap solver over our per-game projections, run on salaries you bring."),
        ("A members-only weekly newsletter", "planned", None,
         "Not built: no list, no signup, no issue."),
    ]
    module_cards = "".join(
        f'<div class="card diamond-get"><h3><a href="{href}">{html.escape(name)}</a></h3>'
        f'<p>{html.escape(what)}</p></div>'
        for name, href, what in gets
    )

    def _extra_card(name: str, state: str, href: str | None, what: str) -> str:
        head = (f'<a href="{html.escape(href)}">{html.escape(name)}</a>'
                if href else html.escape(name))
        label = {"live": "live now", "partial": "feed only",
                 "planned": "planned, not built"}[state]
        return ('<div class="card diamond-get">'
                f'<h3>{head}</h3>'
                f'<p class="diamond-fine">{html.escape(label)}</p>'
                f'<p>{html.escape(what)}</p></div>')

    extra_cards = "".join(_extra_card(*e) for e in extras)
    gate_faq = (
        ("Is any of this gated right now?",
         f"Yes. Member modules are ${price} a month. The free site is unchanged: the prospect board, "
         "projections, free agency model, glossary and articles stay public.")
        if gated else
        ("Is any of this gated right now?",
         "No. Every Diamond page is public and free while we build it: no paywall, no card form, no "
         "trial. Any change is announced before it happens."))
    faq = [
        gate_faq,
        ("Will the price go up?",
         f"List price is ${price} a month. Founding members pay ${founding} for twelve months and are "
         f"not moved if the list price rises above ${price} in that year."),
        ("Where is the Card Market?",
         "Removed on 2026-09-05: it ran on public sold prices with no licensed feed, and no feasible "
         "source turned up. It is not a member benefit and returns only if a licensed price source is "
         "wired."),
        ("Do you guarantee I will make money betting?",
         "No. The record is built to be audited: each published pick carries its timestamp, book and "
         f"odds, a flat one-unit stake, nothing deleted, each {_betting_grading_clause()}."),
        ("What happens to the free site?",
         "It stays free."),
        ("Who is behind this?",
         "One person writes the models; a small group writes the articles. Every model publishes its "
         "eval artifacts, failed experiments included."),
    ]
    faq_html = "".join(
        f'<div class="card diamond-faq"><h3>{html.escape(q)}</h3><p>{html.escape(a)}</p></div>'
        for q, a in faq
    )
    # The banner is the first thing on the page with or without JavaScript, so
    # it is the first thing that must change when the flag flips.
    if gated:
        banner = (
            '<div class="card diamond-banner" role="note">'
            '<h3>Diamond is live</h3>'
            f'<p>Member modules: ${price} a month, ${founding} for founding members. The rest of the '
            'site stays free.</p>'
            '</div>'
        )
        cta = (
            '<div id="diamond-cta" class="card diamond-cta">'
            '<h3>Membership runs through your account</h3>'
            '<p>Sign in to manage it. If no sign-in control renders on this build, accounts are not '
            'wired here and nothing can be bought on this page.</p>'
            '</div>'
        )
        sub = 'Paid tier for fantasy and betting.'
        desc = (f"Diamond is the eephus.io paid tier: fantasy and sports betting tools for ${price} "
                "a month. The rest of the site stays free, including the public data artifacts.")
    else:
        banner = (
            '<div class="card diamond-banner" role="note">'
            '<h3>Founding preview: everything is free while we build</h3>'
            '<p>Diamond is not switched on. Every page here is open to everyone; preview users become '
            'founding members.</p>'
            '</div>'
        )
        # The honest static CTA (2026-08-16). The old card told the reader to
        # use "the sign-in control in the top bar", a control this build does
        # not render; diamond.js only replaces this card when the account layer
        # is configured and on, so this text is what most readers see.
        cta = (
            '<div id="diamond-cta" class="card diamond-cta">'
            '<h3>There is nothing to buy yet</h3>'
            '<p>There is no signup: accounts are not switched on. When they open, founding status '
            'will be honored for preview users.</p>'
            '</div>'
        )
        sub = 'Paid tier for fantasy and betting. Not selling anything yet.'
        desc = (f"Diamond is the eephus.io paid tier: fantasy and sports betting tools for ${price} "
                "a month when it launches. The rest of the site stays free, including the public "
                "data artifacts. Nothing is gated today.")
    # The section-sub counts follow the lists, not a literal: the last rewrite
    # left "four modules" over a two-module grid for a day.
    words = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
    n_mod, n_ex = len(gets), len(extras)
    counts_sub = (
        f'{words[n_mod] if n_mod < len(words) else n_mod} '
        f'module{"" if n_mod == 1 else "s"}, plus '
        f'{words[n_ex] if n_ex < len(words) else n_ex} '
        f'extra{"" if n_ex == 1 else "s"}, each labeled with its state today')
    body = (
        '<div class="fa-app mlbstats-app diamond-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("diamond")}Diamond Pass {_stage_chip("diamond")}</h1></div>'
        f'<span class="section-sub">{sub}</span></div>'
        f'{banner}'
        '<div class="gl-intro">'
        '<p>eephus.io publishes its own report card: the prospect model\'s out-of-sample record '
        'against the public consensus, failed experiments included.</p>'
        '</div>'
        f'{money}'
        '<div class="section-head"><h2>What members get</h2>'
        f'<span class="section-sub">{counts_sub}</span></div>'
        f'<div class="article-grid">{module_cards}</div>'
        f'<div class="article-grid">{extra_cards}</div>'
        # Live receipts. diamond.js fills the two mounts from the artifacts; the
        # static fallback text says what the section IS, so an absent sidecar
        # reads as "not loaded yet" rather than a blank rectangle. The ledger
        # card is server-rendered: its registry is read at build time, and the
        # card says so.
        '<div class="section-head"><h2>The receipts</h2>'
        '<span class="section-sub">scoreboard read live from its artifact; ledger counted at build'
        '</span></div>'
        f'{_diamond_ledger_card()}'
        '<div id="diamond-receipts" class="diamond-receipts">'
        '<div class="card"><p>The prospect model scoreboard loads here from its eval artifact. If '
        'this line is still here, the artifact did not load and no accuracy is claimed.</p></div>'
        '</div>'
        '<div id="diamond-betting-record" class="diamond-record" '
        f'data-serve-clv="{1 if _betting_serve_clv() else 0}">'
        '<div class="card"><p>The betting record loads here. If this line is still here, the '
        'record has not published yet.</p></div>'
        '</div>'
        '<div class="section-head"><h2>Questions</h2></div>'
        f'<div class="article-grid">{faq_html}</div>'
        # diamond.js replaces the static CTA only when the account layer is
        # configured and switched on; on every other build the static card IS
        # the call to action, so it claims no control it cannot show.
        f'{cta}'
        '<p class="diamond-fine">Sports betting content on this site is informational and for entertainment. '
        '21+. Sports betting is not legal in every state. No affiliate links. '
        'If betting stops being fun, call 1-800-GAMBLER.</p>'
        '</div>'
        # Content stamp for data/xfv_scoreboard_eval.json only. The betting
        # record is deliberately ABSENT from this map: betting_record.json is
        # a close-job payload and stays on no-cache revalidation (see
        # _data_vers_script for the rule this enforces).
        f'{_data_vers_script(DIAMOND_DATA_STAMPS)}'
        f'{DIAMOND_CONFIG_SCRIPT}'
        f'<script src="/assets/diamond.js?v={_DIAMOND_VER}" defer></script>'
    )
    return page("Diamond Pass - eephus.io", "diamond", body, desc,
                url=f"{SITE_ORIGIN}/diamond/")

def build_parks() -> str:
    """The /parks/ MiLB Park Factors module - the venue context board.

    Static shell + assets/parks.js, which fetches data/milb_park_factors.json
    (tools/park_line_lab.py): 202 venues across sports 11/12/13/14/16, run and
    home-run factors per venue-season plus the vintage-safe 3-season window,
    joined client-side to the club-season rows that carry level / league /
    affiliate / home-game counts.

    DISPLAY ONLY. Nothing on this page feeds a model. The experiment that built
    the table (efv_park_line.py) is flag-gated off under a registered fail
    verdict, and the Method section says that on the page rather than burying
    it. The board also shows the UNCLAMPED factors; the clamps in the artifact
    belong to that disabled model path, not to the display.

    Not in NAV_ITEMS on purpose: the nav definition is mirrored by three
    hand-maintained static copies (prospx + the two CollegeSavant pages) that
    test_collegesavant_nav_in_sync pins, so a nav row lands with those copies.
    Discovery meanwhile rides the footer link, the homepage Across-eephus.io
    strip, and sitemap.xml."""
    body = (
        '<div class="fa-app mlbstats-app parks-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("parks")}MiLB Park Factors {_stage_chip("parks")}</h1></div>'
        f'<span class="section-sub">Run and home-run {_gl("milb_park_factor", "park factors")} for every '
        'affiliated venue, Triple-A through the DSL: home vs road scoring, league-centered, shrunk toward '
        'neutral by sample. Display only: no model reads them.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Park Factors sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-parksection="board" role="tab" aria-selected="true">Venue Board</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-parksection="leagues" role="tab" aria-selected="false">League Spread</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-parksection="method" role="tab" aria-selected="false">Method &amp; Sample</button>'
        '</div>'
        '<div id="parks-section" class="mlbstats-section">'
        '<div id="parks-banner"></div>'
        f'<div id="parks-app-root"{_csv_optin("milb-park-factors")}></div>'
        '</div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/parks.css?v={_PARKS_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/parks.js?v={_PARKS_VER}" defer></script>'
    )
    return page("MiLB Park Factors - eephus.io", "parks", body,
                "Minor-league park factors for every affiliated venue: run and home-run factors by "
                "season and on a three-season window, with the level, affiliate and home-game sample "
                "behind each. Home vs road scoring, league-centered, sample-shrunk. Display only.",
                url=f"{SITE_ORIGIN}/parks/")

def build_management() -> str:
    """The /management/ In-Game Management module.

    THERE IS NO PLUS METRIC HERE AND THAT IS THE FINDING. The gate battery in
    docs/IN_GAME_MANAGEMENT_GATE.md was frozen before it ran and came back a
    BOUNDED null: the season-controlled split-half correlation of a club's
    decision value in the running game is 0.069 against a permutation band of
    -0.150 to 0.124, and the battery would have detected a true per-club effect
    of 0.0005 wins per attempt. So no club is ranked by decision quality, and
    the club board carries volume, success rate and target mix only.

    What the null makes sayable is worth a page on its own. Over 13,973 priced
    attempts across eight seasons the league steals second at 75.00 percent
    against a swing-weighted break-even of 75.29 percent, which is minus two and
    a half wins for the entire league. Steals of third pay, steals of home do
    not, and the whole running game costs everybody who plays it about
    three quarters of a win.

    Those figures moved on 2026-09-10 and the page does not carry any of them as
    typed copy: audit finding F07-02 found the win model fitted and queried on a
    POST-play score against a PRE-play base-out state, and correcting it flipped
    the league net from plus 1.79 wins to minus 0.75. The board's own sentence is
    derived in mgmt_export._headline_sentence so this docstring can go stale
    without the page going stale with it.

    The run-expectancy matrix and the measured half-inning-start table ship as a
    reference surface, because they need no gate: they are what every break-even
    on the page is computed from.

    In NAV_ITEMS under MLB Modules since the 2026-09-06 nav fix.

    THE DECISION LEDGER (2026-09-23, D2 Wave A). Nine families the play corpus can
    name (pitching change, pinch hitter, pinch runner, defensive sub, intentional
    walk, bunt, steal, mound visit, ejection), each valued as the win probability that
    actually moved from the decision to the last play it governed: REALIZED value, not
    skill, per family and never as a cross-family total. The agent is the club-season
    until the manager ledger (a network ingest) lands. Ten tabs, a hash router on the
    /mlbstats/ idiom (#section=clubs&team=CODE&season=YYYY, #section=decisions&...
    family=F[&game=PK&ab=N]) so the franchise page can link into a club, and per
    club-season shards under data/mgmt_decisions/ for the drill-down. No figure is
    typed here: the masthead names two glossary terms and nothing else."""
    body = (
        '<div class="fa-app mlbstats-app mgmt-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("management")}In-Game Management {_stage_chip("management")}</h1></div>'
        '<span class="section-sub">Every in-game decision the play corpus can name, with the '
        f'{_gl("realized_mwpa", "realized win probability")} it governed beside the priced '
        f'{_gl("decision_value", "decision value")} where one exists; realized value is a record of what '
        'happened, not a measure of skill, and no club is ranked by decision quality.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Management sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-mgmtsection="league" role="tab" aria-selected="true">League</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="running" role="tab" aria-selected="false">Running Game</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="bunt" role="tab" aria-selected="false">Bunt</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="decisions" role="tab" aria-selected="false">Decisions</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="clubs" role="tab" aria-selected="false">Clubs</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="managers" role="tab" aria-selected="false">Managers</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="challenges" role="tab" aria-selected="false">Challenges</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="lineups" role="tab" aria-selected="false">Lineups</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="reference" role="tab" aria-selected="false">Run Expectancy</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="gate" role="tab" aria-selected="false">Club Gate</button>'
        '</div>'
        '<div id="mgmt-section" class="mlbstats-section">'
        f'<div id="mgmt-app-root"{_csv_optin("in-game-management")}></div>'
        '</div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/management.css?v={_MGMT_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/management.js?v={_MGMT_VER}" defer></script>'
    )
    return page("In-Game Management - eephus.io", "management", body,
                "Every in-game decision the play corpus can name: pitching changes, pinch "
                "hitters and runners, defensive subs, intentional walks, bunts, steals, "
                "mound visits and ejections, with the win probability that moved after each. "
                "Realized value per family, never a cross-family total, never a plus metric. "
                "Club pages, a per-decision drill-down and the priced steal and bunt families.",
                url=f"{SITE_ORIGIN}/management/")


def build_ledger() -> str:
    """The /ledger/ Club Ledger module (2026-09-23, D1).

    A LEDGER, NOT A FORECAST. What each club has on the books, owes and controls,
    from Spotrac and the platform's own models, with what each dollar is projected
    to buy. Every figure is read off a served artifact by ledger_export.py and
    rendered by assets/ledger.js from data/ledger_board.json; this shell types no
    number and no sentence of copy beyond two glossary hooks, and the masthead
    line itself is filled from the payload.

    THREE THINGS THE PAGE NEVER SERVES, decided before it was built. A single
    projected payroll (the commitments block is three labelled segments plus the
    count of unpriced vets, never summed: a club payroll forecast would need
    registry row club_payroll_path and the 2016-2025 payroll history as labels).
    Revenue, attendance money, TV money, valuations, revenue-sharing status,
    minor-league payroll, actual CBT bills paid (no source in the tree carries
    them, and the exporter refuses any key by those names). A colour on a salary,
    a club surplus total or a cap-space cell: only Cost+ and OrgSur+, both
    100+10z indexes, take the z ladder.

    Shell on the build_management pattern: section-head with the byline and the
    stage chip (sigil from MODULE_STAGE slot 0, the chip text in the title), the
    .mlbstats-sectionnav tablist (League, Club, Rules, Method), one mount root
    with the CSV opt-in, module css + eephus-hub.js + module js deferred. Hash
    grammar: #section=league|club|rules|method, #section=club&team=CODE
    [&season=2026|2027][&block=...], and #team=CODE as the shorthand the
    franchise page links with."""
    body = (
        '<div class="fa-app mlbstats-app ledger-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("ledger")}Club Ledger {_stage_chip("ledger")}</h1></div>'
        f'<span class="section-sub" id="ledger-masthead">Every club\'s {_gl("cbt_payroll", "CBT payroll")}, '
        f'commitments and {_gl("controlled_surplus", "controlled surplus")}, on the scale each was computed on.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Ledger sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-ledgersection="league" role="tab" aria-selected="true">League</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-ledgersection="club" role="tab" aria-selected="false">Club</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-ledgersection="rules" role="tab" aria-selected="false">Rules</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-ledgersection="method" role="tab" aria-selected="false">Method</button>'
        '</div>'
        '<div id="ledger-section" class="mlbstats-section">'
        f'<div id="ledger-app-root"{_csv_optin("club-ledger")}></div>'
        '</div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/ledger.css?v={_LEDGER_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/ledger.js?v={_LEDGER_VER}" defer></script>'
    )
    return page("Club Ledger - eephus.io", "ledger", body,
                "Every dollar a club has on the books, from Spotrac and the platform's own "
                "models, with what each dollar is projected to buy: CBT payroll on both "
                "bases, the computed tax beside Spotrac's estimate, contract dollars on file "
                "and projected arbitration steps as separate keys, controlled surplus, farm "
                "capital and the free agency ledger. No revenue, no valuations, no TV money.",
                url=f"{SITE_ORIGIN}/ledger/")


def build_franchise() -> str:
    """The /franchise/ Franchise Overview module (2026-09-23, D3).

    A HUB, NOT A MODEL. One page per club re-serving what every module already
    publishes, on the scale each was computed on, with a labelled basis and a
    deep link back to the module that owns it. It computes exactly two new
    things, both descriptive: a branch score (100 + 10z of one served value
    across the 30 clubs) for ROSTER, OUTLOOK and FARM, and the Franchise Index,
    the weighted mean of those three re-standardised to 100 + 10z across the
    30 before any rank or letter is taken from it. Thirty percent of the index
    rests on a provisional projection (team_win_projections) and the root card
    says so. Every figure is read off a served artifact by franchise_export.py
    and rendered by assets/franchise.js from data/franchise_board.json; this
    shell types no number and no sentence beyond two glossary hooks, and the
    masthead line is filled from the payload.

    NEVER HERE: pennants or titles, any club decision-quality grade, any
    manager skill claim, revenue or valuation figures. Letters print in neutral
    ink and only scores take the z ladder. The Hall of Fame tile went live
    2026-09-25 on the owner's frozen attribution rule (hof_export's Franchises
    section, docs/HOF_FRANCHISE_ATTRIBUTION.md) and stays dark if that section
    is dark.

    Shell on the build_ledger pattern: section-head with the byline and the
    stage chip, the .mlbstats-sectionnav tablist (Club, Board), one mount root
    with the CSV opt-in, module css + eephus-hub.js + eephus-gfx.js (the GFX
    export goes through the shared header helper) + module js deferred. Hash
    grammar: #team=CODE (validated against the payload's 30 codes),
    #view=board|club, #tree=hidden|canopy|full, #sec=<branch key>."""
    body = (
        '<div class="fa-app mlbstats-app fr-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("franchise")}Franchise Overview {_stage_chip("franchise")}</h1></div>'
        f'<span class="section-sub" id="franchise-masthead">The {_gl("franchise_index", "Franchise Index")} of every club '
        f'and the {_gl("franchise_branch_score", "branch scores")} beneath it, re-standardised across 30 clubs, '
        'with every number on the scale it was computed on.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Franchise sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-frsection="club" role="tab" aria-selected="true">Club</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-frsection="board" role="tab" aria-selected="false">Board</button>'
        '</div>'
        '<div id="franchise-section" class="mlbstats-section">'
        f'<div id="franchise-app-root"{_csv_optin("franchise")}></div>'
        '</div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/franchise.css?v={_FRANCHISE_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/franchise.js?v={_FRANCHISE_VER}" defer></script>'
    )
    return page("Franchise Overview - eephus.io", "franchise", body,
                "One page per club: the Franchise Index and its three graded branches (roster eWAR, "
                "the provisional 2027 projection, the PROSPX farm composite), re-standardised across "
                "30 clubs, with nine descriptive sections re-serving the season, finances, free agency, "
                "front office, dugout, arbitration, park, history and the model's season view, each "
                "number on its own scale and linked back to the module that owns it.",
                url=f"{SITE_ORIGIN}/franchise/")


def build_hof() -> str:
    """The /hof/ Hall of Fame module.

    Static shell + assets/hof.js, which fetches data/hof_board.json
    (hof_export.py). SIX SECTIONS LIVE (the bake-off went live reporting a
    loss; Franchises went live 2026-09-25 on the owner's frozen attribution
    rule), TWO DARK, and the dark ones each name their blocker on the page.
    The shell types no section count: the payload's `sections` block owns it.

    WHAT IT IS NOT. It is not a Hall-of-Fame predictor and it does not tell a
    reader who belongs. The Hall-sized line is dark because a Hall-SIZED line
    needs the count of players inducted AS PLAYERS, and no field in this data
    says what a plaque says: the source records which ELECTORATE voted, and
    manager and executive plaques reach the eligible universe. The page ships
    the JAWS quantile ladder instead, which is honest without knowing the size
    of the Hall.

    THE THIRD BAND IS THE ONE THAT MATTERS FOR A 2026 READER. Eligible and
    Cooperstown Watch leave out everybody who last played in 2022 through 2024
    and has not cleared the five-year wait, which is Albert Pujols, Zack
    Greinke, Robinson Cano, Miguel Cabrera, Joey Votto and 136 others. Not Yet
    Eligible carries them, and the exporter refuses to write a payload whose
    three bands do not partition the ten-plus-season population exactly.

    In NAV_ITEMS under MLB Modules since the 2026-09-06 nav fix (it shipped
    unreachable before that); the three static nav copies carry it too."""
    body = (
        '<div class="fa-app mlbstats-app hof-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("hof")}Hall of Fame {_stage_chip("hof")}</h1></div>'
        f'<span class="section-sub">Career WAR, {_gl("war7", "WAR7")} and {_gl("jaws", "JAWS")} for '
        'every ten-season player, reproduced from Baseball-Reference\'s daily WAR file, with the '
        'writers\' ballot record. Three bands: eligible, active, and inside the five-year wait. No Hall '
        'line and no snub list; the Bake-off tab says why.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Hall of Fame sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-hofsection="board" role="tab" aria-selected="true">Leaderboards</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-hofsection="franchises" role="tab" aria-selected="false">Franchises</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-hofsection="blocked" role="tab" aria-selected="false">Bake-off &amp; What Is Not Published</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-hofsection="method" role="tab" aria-selected="false">Method &amp; Sample</button>'
        '</div>'
        '<div id="hof-section" class="mlbstats-section">'
        f'<div id="hof-app-root"{_csv_optin("hall-of-fame")}></div>'
        '</div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/hof.css?v={_HOF_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/hof.js?v={_HOF_VER}" defer></script>'
    )
    return page("Hall of Fame - eephus.io", "hof", body,
                "Career WAR, WAR7 and JAWS for every ten-season player, reproduced from "
                "Baseball-Reference's daily WAR file, with the ballot record. Eligible, active and "
                "not-yet-eligible boards, a JAWS quantile ladder and a benchmark bake-off; "
                "unpublished sections name their blockers. No Hall line, no snub list.",
                url=f"{SITE_ORIGIN}/hof/")


# --------------------------------------------------------------------------- #
# /models/ - the model accountability hub
# --------------------------------------------------------------------------- #
# Nothing on this page is typed in. Every row, count, date and link is read at
# build time out of data/model_registry.json and out of the eval artifacts
# themselves, because a hand-written verdict on an accountability page is the
# one lie the page exists to prevent.
#
# The glossary already carries a Models & Proofs view over the same registry
# (assets/glossary.js, /glossary/#view=models) and this page does NOT replace
# it. That view is a browsable card per model with the full accountability
# note. This one answers the three questions that view cannot, because they
# need the filesystem at build time rather than the registry alone:
#   1. does the proof link actually resolve on the deployed site
#   2. what does the artifact say about itself, in its own words
#   3. how old is the measurement, by the artifact's own stamp
# The long `notes` field (322KB across the registry, one row alone is 16KB) is
# deliberately NOT duplicated here; the page links the glossary card for it.
_ACCT_VERDICTS = (
    ("validated", "Validated",
     "A forward-chained out-of-sample backtest is committed and the champion "
     "beats the named baseline."),
    ("provisional", "Provisional",
     "Partly measured: a backtest on synthetic data only, a short window, or a descriptive "
     "correlation instead of a forward test."),
    ("unvalidated", "Unvalidated",
     "Registered and serving, with no measurement yet. Its gate has not been run, "
     "which is not the same thing as a model that is wrong."),
    ("deprecated", "Deprecated",
     "Measured, failed its gate, retired or demoted. Kept on the ledger."),
)

# Parse ceiling for reading an artifact's own stamp, mirroring
# model_registry._MAX_STAMP_PARSE_BYTES. A file over this reads as undated
# rather than costing the build a multi-megabyte parse.
_ACCT_MAX_PARSE_BYTES = 4_000_000


@functools.lru_cache(maxsize=1)
def _acct_data_excludes() -> frozenset:
    """The data/ basenames deploy/data_exclude.txt holds back from the webroot."""
    out = set()
    path = ROOT / "deploy" / "data_exclude.txt"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.add(line)
    except OSError:
        pass
    return frozenset(out)


def _acct_artifact_url(rel: str) -> tuple:
    """(public URL, reason there is none) for one registry eval_artifact path.

    BOTH deploy consumers ship data/ at depth one only: the nightly rsync
    include list is `/data/*.json` plus three named shard dirs, and the CI
    workflow runs `find data -maxdepth 1`. An artifact under docs/ or tools/,
    or one nested in a data/ subdirectory, exists in this tree and does not
    exist on the webroot. Linking it would put a 404 on the page whose entire
    claim is that its receipts resolve, so those rows are rendered as unlinked
    with the reason stated instead."""
    p = (rel or "").strip().replace("\\", "/")
    if not p:
        return None, "no eval artifact is registered for this row"
    if not p.startswith("data/") or p.count("/") != 1:
        return None, "outside the published /data/ directory"
    if p.split("/", 1)[1] in _acct_data_excludes():
        return None, "held back by deploy/data_exclude.txt"
    if not (ROOT / p).exists():
        return None, "not in this build"
    return "/" + p, ""


def _acct_artifact_facts(rel: str) -> dict:
    """Everything the page says about one eval artifact, read off the file.

    `date` is the artifact's SELF-DECLARED production stamp, via the registry's
    own reader, never the file mtime: the deploy box runs `git checkout -- .`
    every night, which rewrites every tracked mtime to the moment of checkout,
    so an mtime age would read "brand new" exactly where staleness matters. An
    artifact with no stamp of its own gets no age here at all rather than a
    flattering one, and reads as undated on the page.

    `verdict` is a TOP-LEVEL string field only. Several artifacts carry `gate`,
    `gates`, `ship` or a `verdicts` map instead, in shapes that differ per lane;
    inferring a verdict from those would be this page writing the verdict rather
    than reading it."""
    url, why = _acct_artifact_url(rel)
    out = {"path": (rel or "").strip().replace("\\", "/"),
           "url": url, "why": why, "date": None, "age": None,
           "verdict": None, "size": None}
    if not out["path"]:
        return out
    path = ROOT / out["path"]
    try:
        out["size"] = path.stat().st_size
    except OSError:
        return out
    try:
        stamped = model_registry._artifact_date(path)
    except Exception:                       # noqa: BLE001 - undated, never fatal
        stamped = None
    if stamped is not None:
        out["date"] = stamped.date().isoformat()
        out["age"] = (datetime.now() - stamped).days
    if path.suffix == ".json" and (out["size"] or 0) <= _ACCT_MAX_PARSE_BYTES:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = None
        if isinstance(doc, dict) and isinstance(doc.get("verdict"), str):
            out["verdict"] = doc["verdict"].strip()
    return out


def _acct_orphan_artifacts(claimed: set) -> list:
    """data/*_eval.json files that ship but that NO registry row claims.

    The registry is the ledger; an eval nobody registered is measured work the
    ledger cannot show you. Listing them is the only way that gap is visible,
    and the list is a glob so it closes itself when a row is added."""
    out = []
    for path in sorted((ROOT / "data").glob("*_eval.json")):
        rel = f"data/{path.name}"
        if rel in claimed:
            continue
        if _acct_artifact_url(rel)[0] is None:
            continue
        out.append(_acct_artifact_facts(rel))
    return out


def _acct_chip(verdict: str) -> str:
    v = verdict if verdict in {k for k, _l, _d in _ACCT_VERDICTS} else "unknown"
    return f'<b data-v="{html.escape(v)}">{html.escape(verdict or "unknown")}</b>'


def _acct_kv(label: str, value: str, raw: bool = False) -> str:
    """One field of an open row. Bare dt/dd, no classes: the ledger renders
    around 1,300 of these and a class attribute per element cost ~85KB of
    markup on a page that is already the largest thing build_site writes."""
    if not value:
        return ""
    body = value if raw else html.escape(value)
    return f"<dt>{html.escape(label)}</dt><dd>{body}</dd>"


def _acct_age_html(f: dict) -> str:
    """The freshness stamp for one artifact, as a bare <time>.

    A datetime attribute means the artifact dated itself and the client may
    recompute the age against the reader's clock; no datetime means it did not,
    and the page says undated rather than reading a file timestamp the deploy
    box rewrites nightly. The stale threshold rides the app root, not 200 copies
    of the same attribute."""
    if not f.get("date"):
        return '<time>undated</time>'
    stale = f.get("age") is not None and f["age"] > model_registry.STALE_DAYS
    days = "" if f.get("age") is None else f'{f["age"]}d'
    cls = ' class="is-stale"' if stale else ""
    return f'<time datetime="{html.escape(f["date"])}"{cls}>{html.escape(days)}</time>'


def _acct_row_flags(f: dict) -> list:
    """The audit flags on one row, which are the same thing the gap counts at
    the top of the page are counting. One definition so a chip that says 12
    cannot show 11 rows."""
    flags = []
    if not f.get("path"):
        flags.append("noeval")
    else:
        if not f.get("date"):
            flags.append("undated")
        if not f.get("url"):
            flags.append("nolink")
        if f.get("age") is not None and f["age"] > model_registry.STALE_DAYS:
            flags.append("stale")
    return flags


_ACCT_FLAG_LABELS = (
    ("noeval", "No eval artifact"),
    ("nolink", "Artifact not published"),
    ("undated", "Undated artifact"),
    ("stale", "Stale eval"),
)


def _acct_row(m: dict, f: dict) -> str:
    """One registry row, server-rendered. `notes` is left to the glossary card
    on purpose (see the section header comment)."""
    if f.get("url"):
        proof = (f'<a href="{html.escape(f["url"])}"><code>{html.escape(f["path"])}</code></a>'
                 + (f' · produced {html.escape(_fmt_iso_date(f["date"]))}' if f.get("date") else ""))
    elif f.get("path"):
        proof = (f'<code>{html.escape(f["path"])}</code> '
                 f'<span class="acct-nolink">not published: {html.escape(f["why"])}</span>')
    else:
        proof = f'<span class="acct-nolink">{html.escape(f["why"])}</span>'
    flags = _acct_row_flags(f)
    # `champion` and the long `notes` field are the glossary card's job, and
    # duplicating them here would have made this page a second copy of that view
    # rather than the thing it adds. What stays is the minimum a verdict needs to
    # be auditable: the claim, the bar it had to clear, how it was measured, the
    # receipt, and whatever the receipt says about itself.
    body = (
        _acct_kv("Predicts", m.get("predicts") or "")
        + _acct_kv("Baseline it must beat", m.get("baseline") or "")
        + _acct_kv("How it is measured", m.get("metric") or "")
        + _acct_kv("Proof", proof, raw=True)
        + _acct_kv("The artifact's own words", m.get("__artifact_verdict") or "")
    )
    flag_attr = f' data-acct-flags="{html.escape(" ".join(flags))}"' if flags else ""
    return (
        f'<details class="acct-row"{flag_attr}>'
        f'<summary class="acct-sum">'
        f'<code>{html.escape(m.get("model_id") or "")}</code>'
        f'{_acct_chip(m.get("verdict") or "")}'
        f'<i>{html.escape(m.get("surface") or "")}</i>'
        f'{_acct_age_html(f)}'
        f'</summary>'
        f'<dl class="acct-body">{body}</dl>'
        f'</details>'
    )


def build_models() -> str:
    """/models/ - the model accountability hub.

    Server-rendered end to end. assets/accountability.js only filters what is
    already in the DOM and re-derives the artifact ages against the reader's
    clock, so with JavaScript off the page still shows every row, every verdict
    and every link.

    Not in NAV_ITEMS, for the same reason /parks/ is not: the nav definition is
    mirrored by three hand-maintained static copies that
    test_collegesavant_nav_in_sync pins, and those copies belong to other
    lanes. Discovery rides the footer link, the homepage Across-eephus.io strip
    and sitemap.xml, which is exactly the /parks/ pattern."""
    reg = model_registry.load()
    models = list(reg.get("models") or [])
    facts = {}
    for m in models:
        rel = (m.get("eval_artifact") or "").strip()
        if rel not in facts:
            facts[rel] = _acct_artifact_facts(rel)
        m["__artifact_verdict"] = facts[rel].get("verdict") or ""

    counts = {}
    for m in models:
        counts[m.get("verdict")] = counts.get(m.get("verdict"), 0) + 1
    n_models = len(models)
    with_art = [m for m in models if (m.get("eval_artifact") or "").strip()]
    art_facts = [f for k, f in facts.items() if k]
    dated = [f for f in art_facts if f.get("date")]
    undated = [f for f in art_facts if not f.get("date")]
    stale = [f for f in dated if f["age"] > model_registry.STALE_DAYS]
    unlinkable = [f for f in art_facts if not f.get("url")]
    unlinkable_rows = [m for m in with_art
                       if not facts[(m.get("eval_artifact") or "").strip()].get("url")]
    orphans = _acct_orphan_artifacts({k for k in facts if k})
    oldest = max((f["age"] for f in dated), default=None)

    tiles = "".join(
        f'<div class="acct-tile acct-tile--{key}">'
        f'<div class="acct-tilen">{counts.get(key, 0)}</div>'
        f'<div class="acct-tilelab">{html.escape(label)}</div>'
        f'<div class="acct-tiledef">{html.escape(desc)}</div></div>'
        for key, label, desc in _ACCT_VERDICTS)

    # The registry's own notes, rendered verbatim. The first one is the caveat
    # that matters most on this page: a verdict is hand-committed next to its
    # eval, so the label is a claim by the author and the artifact beside it is
    # the evidence for that claim. Saying so here is cheaper than pretending the
    # verdict column is machine-derived.
    reg_notes = "".join(f"<li>{html.escape(str(n))}</li>"
                        for n in (reg.get("notes") or []))
    problems = reg.get("problems") or []
    problems_html = (
        '<div class="card acct-note"><h3>Registry validator problems</h3>'
        '<ul class="acct-list">'
        + "".join(f"<li>{html.escape(str(p))}</li>" for p in problems)
        + "</ul></div>") if problems else ""

    fresh_bits = [
        f"{len(with_art)} of {n_models} rows name an eval artifact ({len(art_facts)} "
        "distinct files).",
        f"{len(dated)} of those files carry their own production date.",
    ]
    if oldest is not None:
        fresh_bits.append(f"Oldest dated artifact: {oldest} days.")
    fresh_bits.append(
        f"Stale past {model_registry.STALE_DAYS} days: {len(stale)} today.")
    if undated:
        fresh_bits.append(
            f"{len(undated)} files are undated and show no age (file timestamps are "
            "rewritten on every deploy checkout).")

    gaps = []
    no_eval = [m for m in models if not (m.get("eval_artifact") or "").strip()]
    if no_eval:
        by_v = {}
        for m in no_eval:
            by_v[m.get("verdict")] = by_v.get(m.get("verdict"), 0) + 1
        split = ", ".join(f"{n} {html.escape(str(v))}"
                          for v, n in sorted(by_v.items(), key=lambda kv: -kv[1]))
        gaps.append(f"{len(no_eval)} rows have no eval artifact ({split}).")
    if unlinkable:
        gaps.append(
            f"{len(unlinkable)} artifacts behind {len(unlinkable_rows)} rows are not "
            "published: named, not linked.")
    if orphans:
        gaps.append(
            f"{len(orphans)} eval artifacts in /data/ have no registry row; listed at "
            "the foot of this page.")

    orphan_html = ""
    if orphans:
        rows = "".join(
            f'<li><a href="{html.escape(f["url"])}"><code>{html.escape(f["path"])}</code></a>'
            + (f' · {html.escape(_fmt_iso_date(f["date"]))}' if f.get("date") else "")
            + (f'<div class="acct-verbatim">{html.escape(f["verdict"])}</div>'
               if f.get("verdict") else "")
            + "</li>"
            for f in orphans)
        orphan_html = (
            '<div class="section-head"><h2>Unregistered evals</h2>'
            '<span class="section-sub">shipped eval artifacts no registry row claims</span></div>'
            f'<div class="card acct-note"><ul class="acct-list acct-orphans">{rows}</ul></div>')

    # The last group is a catch-all for a verdict outside the enum. It should
    # always be empty (model_registry.validate() rejects one), but grouping by a
    # fixed list means an off-enum row would otherwise vanish from the ledger
    # without failing anything, which is the exact behaviour this page exists to
    # make impossible.
    off_enum = sorted({m.get("verdict") for m in models}
                      - {k for k, _l, _d in _ACCT_VERDICTS})
    plan = list(_ACCT_VERDICTS) + [
        (v, str(v) if v else "(no verdict)",
         "Not one of the four registry verdicts; shown, not dropped.")
        for v in off_enum]
    groups = []
    for key, label, desc in plan:
        rows = sorted((m for m in models if m.get("verdict") == key),
                      key=lambda m: (m.get("model_id") or ""))
        if not rows:
            continue
        groups.append(
            f'<div class="acct-group" data-acct-group="{html.escape(str(key))}">'
            f'<div class="acct-grouphead"><span class="acct-grouptitle">{html.escape(label)}</span>'
            f'<span class="acct-groupn">{len(rows)}</span></div>'
            f'<p class="acct-groupdef">{html.escape(desc)}</p>'
            + "".join(_acct_row(m, facts[(m.get("eval_artifact") or "").strip()])
                      for m in rows)
            + '</div>')

    flag_counts = {}
    for m in models:
        for fl in _acct_row_flags(facts[(m.get("eval_artifact") or "").strip()]):
            flag_counts[fl] = flag_counts.get(fl, 0) + 1
    filters = ([("all", "All", n_models)]
               + [(k, lab, counts.get(k, 0)) for k, lab, _d in _ACCT_VERDICTS]
               + [(k, lab, flag_counts[k]) for k, lab in _ACCT_FLAG_LABELS
                  if flag_counts.get(k)])
    chips = "".join(
        f'<button class="chip{" active" if k == "all" else ""}" type="button" '
        f'data-acct-filter="{k}">{html.escape(lab)} <span class="acct-count">{n}</span></button>'
        for k, lab, n in filters)

    body = (
        f'<div class="fa-app mlbstats-app acct-app" data-acct-stale-days="{model_registry.STALE_DAYS}">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>{_masthead_icon("models")}Model Accountability</h1></div>'
        '<span class="section-sub">Every model with a predictive claim, its '
        f'{_gl("model_verdict", "verdict")}, and the eval artifact behind it, read from the registry '
        'and the artifacts at build time.</span></div>'
        '<div class="acct-intro">'
        f'<p>Registry vintage: <strong>{html.escape(_fmt_iso_date(reg.get("checked_at")))}</strong>. '
        f'Version <code>{html.escape(str(reg.get("version") or ""))}</code>. Source: '
        '<a href="/data/model_registry.json"><code>data/model_registry.json</code></a>; each row\'s '
        'full note is on the <a href="/glossary/#view=models">glossary ledger</a>.</p>'
        '</div>'
        f'<div class="acct-tiles">{tiles}</div>'
        '<div class="section-head"><h2>Freshness</h2>'
        '<span class="section-sub">by each artifact\'s own stamp</span></div>'
        '<div class="card acct-note"><ul class="acct-list">'
        + "".join(f"<li>{html.escape(b)}</li>" for b in fresh_bits)
        + '</ul></div>'
        + ('<div class="section-head"><h2>Gaps</h2></div>'
           '<div class="card acct-note"><ul class="acct-list">'
           + "".join(f"<li>{html.escape(g)}</li>" for g in gaps)
           + '</ul></div>' if gaps else "")
        + ('<div class="card acct-note"><h3>Registry notes</h3>'
           f'<ul class="acct-list">{reg_notes}</ul></div>' if reg_notes else "")
        + problems_html
        + '<div class="section-head"><h2>The ledger</h2>'
          '<span class="section-sub">open a row for claim, baseline and receipt</span></div>'
        + f'<div class="filter-bar acct-filters">{chips}</div>'
        + f'<div id="acct-rows">{"".join(groups)}</div>'
        + orphan_html
        + '</div>'
        f'<script src="/assets/accountability.js?v={_ACCT_HUB_VER}" defer></script>'
    )
    return page("Model Accountability - eephus.io", "models", body,
                "The eephus.io model ledger: every model with a predictive claim, its verdict, "
                "its baseline, and the eval artifact behind it, failed models included.",
                url=f"{SITE_ORIGIN}/models/")

def build_glossary() -> str:
    """The /glossary/ unified Glossary & Methodology module - the canonical
    definition layer's page. Static shell + assets/glossary.js; definitions
    come from data/glossary.json via the shared eephus-gl.js runtime. The
    How to Read guide, methodology derivations + interactive widgets, and
    the source-vs-source backtest were ported here from the retired PROSPX
    Glossary/Methodology tab (owner decision 2026-06-10)."""
    intro = (
        '<div class="gl-intro">'
        "<p>Every number on eephus.io resolves to an entry here; hover definitions and the Ctrl+K "
        f"palette read the same file. Site-wide WAR is {_gl('ewar', 'eWAR')}. Value and price are "
        f"kept apart ({_gl('value_framework', 'value framework')}). Missing data shows a dash.</p>"
        "</div>"
    )
    body = (
        '<div class="gl-app">'
        f'<div class="section-head"><h1>{_masthead_icon("glossary")}Glossary &amp; Methodology</h1>'
        '<span class="section-sub">terms, derivations, and each model\'s track record</span></div>'
        f"{intro}"
        '<div class="filter-bar"><span class="gl-microlabel">View</span>'
        '<button class="chip active" data-glossary-view="terms">Terms</button>'
        '<button class="chip" data-glossary-view="guide">How to Read</button>'
        '<button class="chip" data-glossary-view="methodology">Methodology</button>'
        '<button class="chip" data-glossary-view="models">Models &amp; Proofs</button>'
        '<button class="chip" data-glossary-view="source-comparison">Source Comparison</button>'
        # C-A4 (2026-08-10). FOUR registration points and a chip is only one of
        # them: the view name must also be in the URL whitelist
        # (assets/glossary.js syncFromURL), the view -> container id map, and
        # the render() dispatch chain, or the chip renders as a dead button
        # while the suite stays green. That is the 2026-06-10 Source Comparison
        # lesson; test_glossary_page_loads.test_view_chips_match_whitelist now
        # asserts all four agree.
        '<button class="chip" data-glossary-view="source-accuracy">Source Accuracy</button>'
        '<button class="chip" data-glossary-view="library">Library</button>'
        # Outbound link (not a view toggle) to the full attribution page, so the
        # Data Sources & Attribution page is reachable from this section, not just
        # the footer. The trailing arrow signals it navigates away.
        '<a class="chip gl-chip-out" href="/sources/">Data Sources &amp; Attribution →</a>'
        '</div>'
        '<div id="gl-termbar">'
        '<input id="gl-search" class="gl-search" type="search" placeholder="Search terms, abbreviations, definitions…" aria-label="Search glossary">'
        '<div class="filter-bar" id="gl-cats"></div>'
        '<div id="gl-az"></div>'
        '</div>'
        '<div id="guide-body" style="display:none;"></div>'
        '<div id="methodology-body" style="display:none;"></div>'
        '<div id="models-body" style="display:none;"></div>'
        '<div id="source-comparison-body" style="display:none;"></div>'
        '<div id="source-accuracy-body" style="display:none;"></div>'
        '<div id="library-body" style="display:none;"></div>'
        '<div id="glossary-rows"></div>'
        '</div>'
        # Shared GFX engine (hub + gfx, the FA / news inject pattern): powers
        # the Source Comparison "Generate GFX" share card. Loaded BEFORE
        # glossary.js so window.EEPHUS_GFX exists when the view renders.
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        # STAMPED 2026-08-06 (plan item H8). This was the last local asset on
        # the site shipping unversioned, so a CDN could serve a stale
        # value_framework.js beside a fresh /glossary/ page and the surplus
        # numbers a reader saw would come from a different vintage than the
        # prose explaining them. Every other asset here is content-hashed;
        # this one is generated into data/ rather than assets/, which is the
        # only reason it was missed.
        f'<script src="/data/value_framework.js?v={_asset_ver("data/value_framework.js")}" defer></script>'
        f'<script src="/assets/glossary.js?v={_GLAPP_VER}" defer></script>'
    )
    return page("Glossary & Methodology - eephus.io", "glossary", body,
                "Definitions, model mechanics and methodology for every metric on eephus.io, "
                "with each model's track record.",
                url=f"{SITE_ORIGIN}/glossary/")

def build_article_page(a: dict) -> str:
    body = (
        '<a class="back-link" href="/articles/">← All articles</a>'
        '<article class="article">'
        '<header class="article-header">'
        f'<h1>{html.escape(a["title"])}</h1>'
        f'<div class="byline">{_byline(a)}</div>'
        "</header>"
        + (f'<p class="article-summary">{html.escape(a["summary"])}</p>' if a.get("summary") else "")
        + f'<div class="article-body">{a["body_html"]}</div>'
        "</article>"
        # eephus.io - article comment thread (the same forum component PROSPX uses),
        # auto-mounted client-side by eephus-ui.js from these data-* hints.
        f'<div id="eph-forum-mount" class="eph-article-forum" data-forum-scope="article" '
        f'data-forum-key="{html.escape(a["slug"])}" data-forum-title="{html.escape(a["title"])}"></div>'
    )
    # Per-article social card (assets/articles/<slug>/share-card.png) is optional - 
    # only emit og:image/twitter when one was generated for this piece.
    slug = a["slug"]
    card = ROOT / "assets" / "articles" / slug / "share-card.png"
    image = f"{SITE_ORIGIN}/assets/articles/{slug}/share-card.png" if card.exists() else ""
    return page(f'{a["title"]} - eephus.io', "articles", body, a.get("summary", ""),
                image=image, url=f"{SITE_ORIGIN}/articles/{slug}/", og_type="article")

def build_team() -> str:
    team = json.loads((CONTENT / "team.json").read_text(encoding="utf-8"))
    # Twitter / LinkedIn icon SVGs (same marks as the old masthead chips, rehomed
    # here on the team page where per-person socials belong).
    _TW_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 '
               '8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 '
               '17.52h1.833L7.084 4.126H5.117z"/></svg>')
    _LI_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 '
               '0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 '
               '5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 '
               '0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>')
    # Personal website - globe glyph (stroke-style, rides currentColor like the rest).
    _WEB_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm7.93 '
                '9h-3.46a15.6 15.6 0 0 0-1.21-5.07A8.03 8.03 0 0 1 19.93 11zM12 4.06c.93 1.28 1.85 3.7 2.16 '
                '6.94H9.84c.31-3.24 1.23-5.66 2.16-6.94zM4.07 13h3.46c.18 1.85.6 3.6 1.21 5.07A8.03 8.03 0 0 1 4.07 '
                '13zm3.46-2H4.07a8.03 8.03 0 0 1 4.67-5.07A15.6 15.6 0 0 0 7.53 11zM12 19.94c-.93-1.28-1.85-3.7-2.16-6.94h4.32c-.31 '
                '3.24-1.23 5.66-2.16 6.94zm3.26-1.87c.61-1.47 1.03-3.22 1.21-5.07h3.46a8.03 8.03 0 0 1-4.67 5.07z"/></svg>')
    # GitHub mark.
    _GH_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 '
               '9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 '
               '18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 '
               '2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 '
               '1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 '
               '2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 '
               '3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 '
               '22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>')
    # Email - classic envelope mark (rides currentColor like the rest).
    _MAIL_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 '
                 '2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z"/></svg>')
    def _initials(name: str) -> str:
        parts = [p for p in name.split() if p[:1].isalpha()]
        if not parts:
            return "?"
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][1:2])).upper()
    def _team_photo(m: dict) -> str | None:
        # Explicit `photo` path wins; otherwise auto-detect assets/team/<first>.<ext>
        # so a member just drops a file (e.g. assets/team/noah.jpg) and rebuilds - 
        # no JSON edit, and no 404 since we only emit <img> when the file exists.
        if m.get("photo"):
            return m["photo"]
        slug = (m["name"].split() or [""])[0].lower()
        for ext in ("jpg", "jpeg", "png", "webp"):
            if (ROOT / "assets" / "team" / f"{slug}.{ext}").exists():
                return f"/assets/team/{slug}.{ext}"
        return None
    # Credit badges: a LOGO mark per credit (no text), the role name on hover.
    # A crown perches on every "Creator" badge (the founder mark); non-creator
    # roles (e.g. Site Design) wear the mark alone. Marks ride currentColor so
    # the per-module accent (and both themes) flow through one style hook.
    _CROWN = ('<svg class="team-badge-crown" viewBox="0 0 24 14" aria-hidden="true">'
              '<path d="M2 12h20l-1.6-8-4.9 4L12 2 8.5 8 3.6 4z" fill="currentColor" '
              'stroke="rgba(0,0,0,.28)" stroke-width="0.5" stroke-linejoin="round"/>'
              '<circle cx="2" cy="3.2" r="1.3" fill="currentColor"/>'
              '<circle cx="12" cy="1.3" r="1.4" fill="currentColor"/>'
              '<circle cx="22" cy="3.2" r="1.3" fill="currentColor"/></svg>')
    # PX-08: each credit wears its module's pixel icon at 24 px (the 12 x 12
    # core at 2x), the same drawing as the nav, rail and masthead, which
    # retires the ten hand-drawn 24 px marks that were a fourth icon
    # vocabulary. Site design wears the pen (the drawing the wire's signing
    # pictogram uses) and any unmapped role, Writer and Analyst included, the
    # Articles pilcrow. The two gold accents became primary ink: the pixel set
    # draws no icon in gold (plan 5.7.1 line 7).
    def _badge_for(note: str) -> str:
        n = note.lower()
        if "prospx" in n:                         key, accent = "prospx", "var(--text-primary)"
        elif "projection" in n:                   key, accent = "projections", "var(--accent-cyan)"
        elif "free agency" in n:                  key, accent = "fa", "var(--accent-green)"
        elif "collegesavant" in n or "college" in n: key, accent = "collegesavant", "var(--accent-lilac)"
        elif "eephus" in n:                       key, accent = "home", "var(--text-primary)"
        elif "stats" in n:                        key, accent = "mlbstats", "var(--neon-amber)"
        elif "alchemy" in n:                      key, accent = "pal", "var(--neon-violet)"
        elif "webmaster" in n or "web" in n:      key, accent = "team", "var(--accent-navy)"
        elif "design" in n:                       key, accent = "ev-signing", "var(--text-secondary)"
        elif "trade" in n:                        key, accent = "trademachine", "var(--accent-orange)"
        else:                                     key, accent = "articles", "var(--accent-red)"   # Writer/Analyst + any unmapped role
        mark = _ico(key, 24)
        creator = "creator" in n or "lead" in n or "webmaster" in n   # crown any lead/creator/webmaster role
        cls = "team-badge" + (" is-creator" if creator else "")
        label = html.escape(note)
        return (f'<span class="{cls}" title="{label}" aria-label="{label}" '
                f'style="--badge-accent:{accent}">{_CROWN if creator else ""}'
                f'<span class="team-badge-mark">{mark}</span></span>')
    # School affiliation: the school's wordmark mark (or an image at school_logo,
    # if a member provides one) plus the full name. Add a school to _SCHOOL_MARKS
    # to give its short mark a brand color.
    _SCHOOL_MARKS = {"New York University": {"short": "NYU", "color": "#57068C", "logo": "nyu.png"},
                     "University of Oklahoma": {"short": "OU", "color": "#841617", "logo": "ou.png"},
                     "Boston University": {"short": "BU", "color": "#CC0000", "logo": "bu.png"},
                     "Utah College": {"short": "UTAH", "color": "#CC0000", "logo": "utah.png"},
                     "University of California, Los Angeles": {"short": "UCLA", "color": "#2774AE", "logo": "ucla.png"},
                     "Merrimack College": {"short": "MACK", "color": "#003263", "logo": "merrimack.png"}}
    def _school_html(m: dict) -> str:
        school = (m.get("school") or "").strip()
        if not school:
            return ""
        sm = _SCHOOL_MARKS.get(school) or {}
        # Logo image (explicit school_logo, or the school's default) is used ONLY
        # when the file exists on disk - otherwise we fall back to the wordmark so
        # a missing file never renders a broken icon. A bare filename resolves
        # under assets/team/; an absolute path is used as given.
        logo = (m.get("school_logo") or sm.get("logo") or "").strip()
        mark = ""
        if logo:
            rel = logo.lstrip("/") if "/" in logo else f"assets/team/{logo}"
            if (ROOT / rel).exists():
                mark = (f'<img class="team-school-logo" src="/{html.escape(rel)}" '
                        f'alt="{html.escape(school)} logo" loading="lazy">')
        if not mark and sm.get("short"):
            mark = f'<span class="team-school-mark" style="color:{sm["color"]};">{html.escape(sm["short"])}</span>'
        return f'<div class="team-school" title="{html.escape(school)}">{mark}<span>{html.escape(school)}</span></div>'
    cards = []
    for m in team:
        handle = (m.get("handle") or "").lstrip("@")
        linkedin = (m.get("linkedin") or "").strip().rstrip("/").rsplit("/", 1)[-1]
        # Headshot: provided image (rectangular, sharp) over a monogram fallback
        # that shows when there's no photo or the file 404s - never a broken image.
        mono = f'<span class="team-monogram" aria-hidden="true">{html.escape(_initials(m["name"]))}</span>'
        photo = _team_photo(m)
        if photo:
            img = (f'<img src="{html.escape(photo)}" alt="{html.escape(m["name"])}" '
                   f'loading="lazy" onerror="this.style.display=\'none\'">')
            photo_html = f'<div class="team-photo">{mono}{img}</div>'
        else:
            photo_html = f'<div class="team-photo">{mono}</div>'
        chips = []
        if handle:
            chips.append(f'<a class="team-soc" href="https://x.com/{html.escape(handle)}" target="_blank" '
                         f'rel="noopener" title="Twitter / X - @{html.escape(handle)}" aria-label="Twitter / X - @{html.escape(handle)}">{_TW_SVG}</a>')
        if linkedin:
            chips.append(f'<a class="team-soc" href="https://www.linkedin.com/in/{html.escape(linkedin)}/" target="_blank" '
                         f'rel="noopener" title="LinkedIn - {html.escape(m["name"])}" aria-label="LinkedIn - {html.escape(m["name"])}">{_LI_SVG}</a>')
        email = (m.get("email") or "").strip()
        if email:
            chips.append(f'<a class="team-soc" href="mailto:{html.escape(email)}" '
                         f'title="Email - {html.escape(email)}" aria-label="Email - {html.escape(email)}">{_MAIL_SVG}</a>')
        website = (m.get("website") or "").strip()
        if website:
            _host = website.split("//", 1)[-1].strip("/")
            chips.append(f'<a class="team-soc" href="{html.escape(website)}" target="_blank" '
                         f'rel="noopener" title="Website - {html.escape(_host)}" aria-label="Website - {html.escape(_host)}">{_WEB_SVG}</a>')
        github = (m.get("github") or "").strip().rstrip("/").rsplit("/", 1)[-1]
        if github:
            chips.append(f'<a class="team-soc" href="https://github.com/{html.escape(github)}" target="_blank" '
                         f'rel="noopener" title="GitHub - {html.escape(github)}" aria-label="GitHub - {html.escape(github)}">{_GH_SVG}</a>')
        socials_html = f'<div class="team-socials">{"".join(chips)}</div>' if chips else ""
        # Optional credit pills (e.g. "PROSPX Creator"). `note` may be a single
        # string or a list - members with several credits get one pill each,
        # wrapped in a flex row so they reflow cleanly inside the card.
        notes = m.get("note")
        if isinstance(notes, str):
            notes = [notes]
        notes = [n for n in (notes or []) if n]
        # Module credit badges (a logo mark per role, a crown on creator/lead/webmaster
        # roles, full role name on hover) render on the FRONT face under the socials.
        note_html = (
            '<div class="team-notes">'
            + "".join(_badge_for(n) for n in notes)
            + "</div>"
        ) if notes else ""
        slug = _member_slug(m["name"])
        # Back face: the owner fills in the specific sections / models / metrics
        # each developer built later. Optional `back` field in team.json (a list
        # of strings, or a preformatted HTML string) drives it; absent -> a plain
        # placeholder so the flip always has something to show.
        back = m.get("back")
        if isinstance(back, str) and back.strip():
            back_body = back
        elif isinstance(back, list) and back:
            back_body = ('<ul class="team-back-list">'
                         + "".join(f'<li>{html.escape(str(b))}</li>' for b in back if b)
                         + "</ul>")
        else:
            back_body = '<p class="team-back-empty">Detailed contributions coming soon.</p>'
        front_face = (
            f'<div class="card team-card-face team-card-front">{photo_html}'
            f'<p class="name">{html.escape(m["name"])}</p>{_school_html(m)}{socials_html}{note_html}'
            '<span class="team-flip-hint" aria-hidden="true">flip &#8635;</span></div>'
        )
        back_face = (
            '<div class="card team-card-face team-card-back">'
            f'<div class="team-back-head">{html.escape(m["name"])}</div>{back_body}'
            '<span class="team-flip-hint" aria-hidden="true">back &#8635;</span></div>'
        )
        cards.append(
            f'<div class="team-card team-flip" id="member-{slug}" tabindex="0" role="button" '
            f'aria-pressed="false" aria-label="{html.escape(m["name"])}: flip for contributions">'
            f'<div class="team-card-inner">{front_face}{back_face}</div></div>'
        )
    follow = (
        '<div class="team-follow"><span class="team-follow-label">Follow</span>'
        f'{_x_link("eephus_io")}{_x_link("MLBPROSPX")}{_discord_link()}</div>'
    )
    mission = (
        "<p class=\"team-mission\">eephus.io is built by the development team below, college "
        "students working toward careers in baseball. Contact any of us for questions, "
        "feedback or opportunities.</p>"
        # This leaf is labeled "Developers" in the nav, so a developer arriving
        # here looking for the data finds a pointer instead of a dead end. The
        # catalog itself lives on /sources/ (see _sources_api_section for why).
        "<p class=\"team-mission\">Building on the data? Every model artifact is public JSON, "
        "catalogued on <a href=\"/sources/#api\">the public data page</a>.</p>"
    )
    # Click / keyboard flip: toggles .is-flipped on a card. Clicks on the social
    # links (or any future back-face link/button) do NOT flip, so links still
    # work. Self-contained inline script (page() inserts body raw); plain ASCII,
    # no em-dashes (copy gate scans generated HTML).
    flip_js = (
        '<script>(function(){'
        'function toggle(card){var f=card.classList.toggle("is-flipped");'
        'card.setAttribute("aria-pressed",f?"true":"false");}'
        'document.querySelectorAll(".team-flip").forEach(function(card){'
        'card.addEventListener("click",function(e){'
        'if(e.target.closest("a,button"))return;toggle(card);});'
        'card.addEventListener("keydown",function(e){'
        'if(e.key==="Enter"||e.key===" "){e.preventDefault();toggle(card);}});'
        '});})();</script>'
    )
    body = (
        f'<div class="section-head"><h1>{_masthead_icon("team")}Developers</h1></div>'
        f'{mission}'
        f'{follow}'
        f'<div class="team-grid">{"".join(cards)}</div>'
        f'{flip_js}'
    )
    return page("Developers - eephus.io", "team", body, "The team behind eephus.io.",
                url=f"{SITE_ORIGIN}/team/")

# --------------------------------------------------------------------------- #
# /teams/ - RETIRED standalone module (merged into MLB Projections
# 2026-06-12). The org-dashboard columns (farm rank/score, farm surplus,
# top prospect, cross-module links) now ride the Team Outlook view's
# baked farm blocks (proj_export._org_farm_blocks). The URL stays alive
# as a redirect so bookmarks and external links keep working.
# --------------------------------------------------------------------------- #
def _artifact_card(row: dict) -> str:
    """One published-artifact card for the /sources/ catalog.

    Every number on the card is read off the file at build time (size, the
    artifact's own stamped vintage) or verified against the tree (the test that
    pins the shape). Nothing here is typed in by hand, which is the only way a
    table of two dozen files stays true a month from now.

    Styled with inline rules on the theme tokens rather than new classes:
    assets/site.css belongs to another lane, `.card p` carries `margin: 0`, and
    a multi-paragraph card needs its own spacing. Every value here is a var()
    so both themes still flow through."""
    # The literal middot is the separator the rest of the site uses in meta
    # lines (see the module subtitles); it goes in AFTER escaping so it stays a
    # separator rather than turning into a visible entity.
    meta = [row["cadence"], row["size_label"]]
    if row.get("vintage"):
        meta.append("as of " + _fmt_iso_date(row["vintage"]))
    meta_line = " · ".join(html.escape(m) for m in meta if m)
    tier = row["stability"]
    tier_note = ("field names hold, new fields can appear at any time"
                 if tier == data_catalog.STABLE
                 else "shape can change or the file can disappear on any run")
    fine = ("margin-top:8px;font-family:var(--font-retro-mono);font-size:11px;"
            "line-height:1.5;color:var(--text-tertiary);")
    tail = [f'<strong>{html.escape(tier)}</strong>: {html.escape(tier_note)}']
    if row.get("note"):
        tail.append(html.escape(row["note"]))
    if row.get("pinned_by"):
        tail.append("Shape pinned by <code>"
                    + html.escape(row["pinned_by"]) + "</code>")
    return (
        '<div class="card source-card">'
        f'<h3>{html.escape(row["title"])}</h3>'
        f'<p>{html.escape(row["what"])}</p>'
        f'<p style="{fine}"><a href="{html.escape(row["url"])}"><code>'
        f'{html.escape(row["url"])}</code></a><br>{meta_line}</p>'
        f'<p style="{fine}">' + "<br>".join(tail) + '</p>'
        '</div>'
    )


def _sources_api_section() -> str:
    """The published-data half of /sources/: the artifact catalog.

    WHY IT LIVES HERE AND NOT AT /developers/. A dedicated route was the first
    choice and is still the right long-term home, but a new top-level page dir
    needs a line in deploy/publish_paths.txt and a regenerated SITE_MAP.md,
    neither of which this change owns. An unshipped page dir is exactly the
    2026-07-14 incident (whole modules 404ing in production while every test
    stayed green), and shipping the documentation on a page that already
    deploys beats shipping a 404 that reads well locally. /sources/ is the
    natural host: it already answers "where does this data come from", and the
    catalog answers the other half of the same question. Promotion to
    /developers/ is a redirect plus those two lines whenever someone owns them.

    The catalog itself is data_catalog.ARTIFACTS, verified against the tree and
    against deploy/data_exclude.txt before anything renders."""
    groups = data_catalog.rows_by_group()
    if not groups:
        # No verified artifact in the tree (fresh checkout). Say nothing rather
        # than render an empty promise; the attribution half of the page stands
        # on its own.
        return ""
    c = data_catalog.counts()
    blocks = []
    for _key, label, rows in groups:
        cards = "".join(_artifact_card(r) for r in rows)
        n = len(rows)
        blocks.append(
            f'<div class="section-head"><h2>{html.escape(label)}</h2>'
            f'<span class="section-sub">{n} file{"" if n == 1 else "s"}</span></div>'
            f'<div class="article-grid">{cards}</div>')
    return (
        '<div class="section-head" id="api"><h2>The data we publish</h2>'
        '<span class="section-sub">contents, cadence and stability of every served artifact</span></div>'
        '<div class="gl-intro">'
        f'<p>Every model writes a static JSON file under <code>/data/</code>; the site reads the '
        f'same files. No key, no quota, no sign-up. {c["n"]} artifacts documented below, '
        f'{c["stable"]} of them stable.</p>'
        '<p>Not promised: version headers, deprecation windows, uptime, or byte layout. Fields can '
        'be added without notice. A field named here keeps its name and meaning.</p>'
        f'<p>{c["withheld"]} more files stay local (model internals and pipeline inputs no page '
        'fetches) and are not listed.</p>'
        '</div>'
        '<div class="card">'
        '<h3>CSV from any board</h3>'
        '<p>Download CSV writes what is on screen: current sort, filters and display formats. '
        'Use the artifacts for whole boards.</p>'
        '</div>'
        '<div class="card">'
        '<h3>eFV movement alerts: feed only, no delivery</h3>'
        '<p>Each rebuild publishes the biggest genuine eFV moves, with drivers, to '
        '<a href="/data/efv_alerts.json"><code>/data/efv_alerts.json</code></a>. Nothing is '
        'emailed or pushed; the artifact\'s <code>delivery</code> field says so.</p>'
        '<p>A move with an endpoint at the eFV 20 floor is a player entering or leaving the graded '
        'pool, not a re-grade; filter on <code>at_floor</code>.</p>'
        '</div>'
        + "".join(blocks)
    )


# The sources whose scouting reports the site shows today: the prospect cards
# read the scout_reports chunks, the draft cards read the draft board payload.
# Since the owner's answer of 2026-09-25 (census X07-02 option b) both carry an
# excerpt of at most REPORT_EXCERPT_CHARS characters plus a link to the
# source's page for the player or, since the owner's answer of 2026-10-01
# (REPEX-1 option b), to the source's page for the list (report_excerpt.py);
# the full text is not in the public data. The /sources/ lede names both sets;
# test_claims_freshness holds the tuples to the payloads and
# test_report_excerpt.py holds every served report to the excerpt limit.
SCOUT_REPORT_SOURCES = ("FanGraphs", "MLB Pipeline", "Baseball America", "ESPN",
                        "Just Baseball")
DRAFT_REPORT_SOURCES = ("FanGraphs", "MLB Pipeline", "Baseball America")


def _name_series(names) -> str:
    """'A, B and C' for a short list of names."""
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def build_sources() -> str:
    """/sources/ - data sources and attribution, plus the published-data catalog.

    Trust page for the Open Beta: names every upstream the platform reads, what
    it's used for, and the editorial stance (consensus across sources; the lede
    names whose report excerpts the cards carry). The second half (anchor #api) is the other direction of
    the same question: which artifacts the platform PUBLISHES, on what cadence,
    and how stable each one is. See _sources_api_section for why the catalog
    lives on this route."""
    rows = [
        ("FanGraphs", "https://www.fangraphs.com/",
         "Prospect rankings, FV grades, tool grades, and prospect and draft scouting reports "
         "(one of the seven PROSPX consensus inputs); league stats and park factors."),
        ("MLB Pipeline", "https://www.mlb.com/prospects",
         "Prospect rankings, grades, and prospect and draft scouting reports (consensus "
         "input); draft bonus pools and slot values."),
        ("Baseball America", "https://www.baseballamerica.com/",
         "Prospect rankings, grades, and prospect and draft scouting reports (consensus input)."),
        ("ESPN", "https://www.espn.com/mlb/",
         "Prospect rankings and scouting reports (consensus input); the club logo images "
         "on team pickers and boards load from ESPN's image server (the logos are the "
         "clubs' trademarks)."),
        ("The Athletic", "https://www.nytimes.com/athletic/",
         "Prospect rankings (consensus input)."),
        ("Just Baseball", "https://www.justbaseball.com/",
         "Prospect rankings and scouting reports (consensus input)."),
        ("TJStats", "https://x.com/TJStats",
         "Prospect rankings (consensus input) and movers wire."),
        ("MLB Stats API / Baseball Savant", "https://baseballsavant.mlb.com/",
         "Game logs, transactions, rosters, the sabermetrics feed (league wOBA constants; the "
         "fielding and framing runs behind DEM+), Statcast tracking data (pitch, batted-ball "
         "and zone metrics), and player headshots via MLB static media."),
        ("Baseball-Reference", "https://www.baseball-reference.com/",
         "war_daily (bWAR): the run frame the served eWAR is built on and the source the Hall "
         "of Fame board reproduces, plus historical player pages."),
        ("pybaseball", "https://github.com/jldbc/pybaseball",
         "Open-source Python toolkit used to pull Statcast, FanGraphs, and "
         "Baseball-Reference data programmatically."),
        ("Spotrac", "https://www.spotrac.com/",
         "Contracts, payrolls, free-agent classes, and international signing trackers."),
        # Census X07-08 (2026-09-25): three upstreams the platform reads that
        # this list never named. test_sources_attribution.py holds every
        # external host in the ingest modules to a row here.
        ("MLB Trade Rumors", "https://www.mlbtraderumors.com/",
         "Arbitration salary projections (Matt Swartz's model) and the arbitration "
         "results tracker: the comparator /arbitration/ scores its own model against, "
         "and a record of settled salaries the arbitration dataset reads."),
        ("The Odds API", "https://the-odds-api.com/",
         "Sportsbook moneylines, run lines and totals for the /betting/ board, and the "
         "game lines /fantasy/ DFS pricing reads."),
        ("Open-Meteo", "https://open-meteo.com/",
         "Game-time weather forecasts, captured nightly for a pre-registered betting "
         "candidate; no page shows them yet. Weather data by Open-Meteo.com (CC BY 4.0)."),
    ]
    cards = "".join(
        f'<div class="card source-card"><h3><a href="{html.escape(url)}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(name)}</a></h3><p>{html.escape(use)}</p></div>'
        for name, url, use in rows
    )
    body = (
        '<div class="section-head"><h1>Data: sources, attribution and what we publish</h1>'
        '<span class="section-sub">upstreams we read, artifacts we publish</span></div>'
        '<div class="gl-intro">'
        "<p>PROSPX grades are a consensus of seven industry sources. A player's card shows "
        "each source's own FV grade beside the consensus, and excerpts of the scouting "
        f"reports {_name_series(SCOUT_REPORT_SOURCES)} have published on that player: the "
        f"opening of each report, at most {REPORT_EXCERPT_CHARS} characters, labelled with its "
        "source, list and publication date, with a View on link to the player's page at the "
        "source where we know it and otherwise to the source's page for that list. The draft "
        "board shows excerpts of the draft reports from "
        f"{_name_series(DRAFT_REPORT_SOURCES)} the same way. The full reports stay with their "
        "publishers. Trademarks, data and report text belong to their owners.</p>"
        "<p>Sources with a question or concern: "
        '<a href="mailto:arkndjl@gmail.com">arkndjl@gmail.com</a>.</p>'
        '<p>Building on the data: <a href="#api">the data we publish</a>.</p>'
        "</div>"
        '<div class="section-head"><h2>Where the data comes from</h2></div>'
        f'<div class="article-grid">{cards}</div>'
        f'{_sources_api_section()}'
    )
    return page("Data Sources, Attribution & the Public Data - eephus.io", "", body,
                "Every data source behind eephus.io - prospect ranking inputs, Statcast and "
                "league data, contracts - plus the catalog of public JSON artifacts the site "
                "publishes, their update cadence and how stable each one is.",
                url=f"{SITE_ORIGIN}/sources/")


def build_bug_report() -> str:
    """/report/ - the "Report a bug" destination linked from every footer.
    Embeds the owner's Google Form when BUG_FORM_URL is set; otherwise shows
    an on-theme placeholder card with the mailto fallback so the page is never
    a dead end during the Open Beta."""
    intro = (
        '<div class="gl-intro"><p>Say what happened and which section; the form has a '
        'section picker.</p></div>'
    ) if BUG_FORM_URL else ""
    if BUG_FORM_URL:
        form = (
            f'<iframe src="{html.escape(BUG_FORM_URL)}" width="100%" height="820" '
            'style="border:0" title="Report a bug form">Loading the form...</iframe>'
        )
    else:
        form = (
            '<div class="card">'
            '<h3>The form is not configured yet</h3>'
            '<p>Email the details, with the section, to '
            '<a href="' + FEEDBACK_MAILTO + '">arkndjl@gmail.com</a>.</p>'
            '</div>'
        )
    body = (
        '<div class="section-head"><h1>Report a bug</h1>'
        '<span class="section-sub">tell us what broke and where</span></div>'
        f'{intro}{form}'
    )
    return page("Report a bug - eephus.io", "", body,
                "Report a bug on eephus.io - tell us what happened and which section "
                "it is in.",
                url=f"{SITE_ORIGIN}/report/")


def build_404() -> str:
    """The not-found page (nginx: `error_page 404 /404.html;`). On-theme,
    no dead ends: home link + the module rail + the palette hint. The rail is
    read off nav_leaves() so a module added to NAV_ITEMS lands here too (the
    hand-typed list had stopped at seven modules and missed ten)."""
    rail = " · ".join(f'<a href="{h}">{html.escape(l)}</a>'
                      for k, l, h in nav_leaves() if k != "home")
    body = (
        '<div class="section-head"><h1>404: page not found</h1>'
        '<span class="section-sub">it does not exist, or it moved</span></div>'
        f'<div class="px-404">{_PX_404_ART}</div>'
        '<div class="gl-intro">'
        f'<p><a href="/">Home</a> · {rail}</p>'
        '<p>Player search: <strong>Ctrl+K</strong> (⌘K on Mac).</p>'
        '</div>'
    )
    return page("Page not found - eephus.io", "", body,
                "Page not found on eephus.io.", robots="noindex")


def build_robots() -> str:
    """robots.txt - crawl everything except the data payloads (multi-MB JSON
    sidecars are for the apps, not crawlers) and the resolver stubs."""
    return (
        "User-agent: *\n"
        "Disallow: /data/\n"
        "Disallow: /player/\n"
        "Disallow: /teams/\n"
        "Allow: /\n"
        f"Sitemap: {SITE_ORIGIN}/sitemap.xml\n"
    )


def build_sitemap(articles: list[dict]) -> str:
    """sitemap.xml over the canonical public surfaces. lastmod is the build
    date for app pages (data refreshes nightly) and the article date for
    articles."""
    today = date.today().isoformat()
    pages = [
        ("/", "daily", "1.0"),
        ("/news/", "daily", "0.8"),
        ("/history/", "daily", "0.6"),
        ("/prospx/", "daily", "1.0"),
        ("/collegesavant/", "weekly", "0.8"),
        ("/collegesavant/pitcher_index.html", "weekly", "0.7"),
        ("/fa/", "daily", "0.9"),
        ("/projections/", "daily", "0.9"),
        ("/mlbstats/", "daily", "0.8"),
        ("/pal/", "daily", "0.8"),
        ("/trademachine/", "daily", "0.8"),
        ("/arbitration/", "daily", "0.8"),
        ("/ledger/", "daily", "0.7"),
        ("/franchise/", "daily", "0.7"),
        # /dynasty/, /redraft/ and /dfs/ are redirect stubs into /fantasy/ and
        # carry meta robots=noindex, so they are deliberately absent here (same
        # treatment as /teams/). Their content is one crawlable page.
        ("/fantasy/", "daily", "0.8"),
        ("/betting/", "daily", "0.8"),
        ("/diamond/", "monthly", "0.6"),
        ("/parks/", "weekly", "0.6"),
        ("/hof/", "weekly", "0.6"),
        ("/management/", "weekly", "0.6"),
        ("/models/", "daily", "0.6"),
        ("/articles/", "weekly", "0.7"),
        ("/forums/", "daily", "0.6"),
        ("/glossary/", "weekly", "0.7"),
        ("/sources/", "monthly", "0.3"),
        ("/team/", "monthly", "0.3"),
        ("/report/", "monthly", "0.2"),
    ]
    urls = []
    for path, freq, prio in pages:
        urls.append(
            f"  <url><loc>{SITE_ORIGIN}{path}</loc><lastmod>{today}</lastmod>"
            f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        )
    for a in articles:
        lastmod = a.get("date_sort") or today
        urls.append(
            f"  <url><loc>{SITE_ORIGIN}/articles/{a['slug']}/</loc><lastmod>{lastmod}</lastmod>"
            f"<changefreq>monthly</changefreq><priority>0.6</priority></url>"
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def build_teams_redirect() -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Teams - eephus.io</title>
{FAVICON_LINKS}
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=/projections/#view=teams">
<script>location.replace("/projections/#view=teams");</script>
</head><body>
<p style="font-family:monospace;padding:2rem;">The Teams dashboard moved into
<a href="/projections/#view=teams">MLB Projections &rarr; Team Outlook</a>.</p>
</body></html>
"""

# --------------------------------------------------------------------------- #
# Derived BROWSER payloads
# --------------------------------------------------------------------------- #
# Some model artifacts are far too heavy (or too internal) to hand a browser.
# data/positional_fit.json is 580KB of per-player evidence rows and is pinned
# in deploy/data_exclude.txt (it never reaches the webroot), and swing_plus.json
# is a model input rather than a served payload. These builders bake the SLIM,
# display-only slice each surface actually needs into its own data/*.json, which
# ships normally. Nothing is recomputed here: every number is copied straight
# off the model artifact, and anything the artifact does not carry is simply
# absent rather than filled in.
# --------------------------------------------------------------------------- #

def _team_by_mlbam() -> dict:
    """{mlbam: team} from the cross-module identity map (player_links.json).
    The positional-fit artifact carries no team; the links map is the same
    join every module already uses to cross-link a player."""
    links = _cached_data_json("player_links.json")
    out = {}
    for row in (links.get("byMlbam") or {}).values():
        try:
            mid = int(row.get("mlbam"))
        except (TypeError, ValueError):
            continue
        if row.get("team"):
            out[mid] = row["team"]
    return out


def build_positional_fit_payload() -> dict | None:
    """Slim, display-only view of data/positional_fit.json for the Alchemy Lab
    Position Fit section.

    Carries the fitted ladder (with its CI and the folklore ladder it replaces),
    the out-of-sample conversion accuracy, the DEMOTION-PREDICTION NULL, and one
    row per qualified hitter. The full artifact keeps the per-player evidence
    logs and the unqualified rows; none of that is served."""
    src = _cached_data_json("positional_fit.json")
    if not src or not src.get("players"):
        return None
    teams = _team_by_mlbam()
    fit = src.get("fit") or {}
    ladder = fit.get("ladder") or {}
    conv = src.get("conversion_accuracy") or {}
    val = src.get("validation") or {}

    def _display_name(raw: str | None) -> str:
        """The artifact stores BRef-style "Last, First"; every other surface on
        the site prints "First Last"."""
        if not raw or "," not in raw:
            return raw or ""
        last, _, first = raw.partition(",")
        return f"{first.strip()} {last.strip()}".strip()

    def _pos_history(p: dict, fit: dict) -> list[dict]:
        """Per (season, position) defensive line plus its reliability weight.

        Collapses the model's own evidence log to what a reader needs: how much he
        played there, what the glove did, and HOW MUCH TO TRUST IT. The last one is
        the part that was missing, and without it the other two mislead: 40 innings
        in right field and 900 at first are not comparable readings of a player even
        though both print an OAA.
        """
        sig = (fit.get("signal") or {})
        out = []
        for e in (p.get("evidence") or []):
            pos = e.get("pos")
            inn = e.get("inn") or 0.0
            k = ((sig.get(pos) or {}).get("k_inn") or 0.0)
            out.append({
                "season": e.get("season"), "pos": pos, "inn": inn,
                "oaa": e.get("oaa"), "frp": e.get("frp"),
                "z": e.get("z_read"),
                # None rather than a fabricated 0 when the position has no fitted
                # constant (catchers, and anything Savant does not cover).
                "rel": round(inn / (inn + k), 3) if k > 0 and inn > 0 else None,
            })
        # newest first, then by exposure, so the most informative line leads
        out.sort(key=lambda r: (-(r["season"] or 0), -(r["inn"] or 0)))
        return out

    # ---- Rng+ (legs), display-only, LF/CF destinations ONLY -----------------
    # Owner ask 1's surviving half. The ARM half was measured and no-shipped
    # (docs/efv-2026-07-30/CONVERSION_ARM_GATE_VERDICT.md): context-adjusted, the
    # infield arm spread collapses to 1.94 mph against a within-position sd of
    # 3.80, and 3B minus SS is +0.50, so arm barely selects positions. Sprint
    # speed does, but ONLY in the outfield, and that restriction is the finding
    # rather than caution about it. Measured against OAA per 1000 innings at the
    # position played (>=400 inn, 2016-2026): CF r=+0.428 [+0.342,+0.507],
    # LF +0.416 [+0.323,+0.501], but SS -0.020 [-0.122,+0.083] and 3B -0.004
    # [-0.108,+0.100]. A speed meter on an infield row would be a picture of a
    # measured zero.
    #
    # RF IS EXCLUDED even though it clears the headline bar (+0.269
    # [+0.167,+0.365]), because its PURE-CORNER subgroup does not: right fielders
    # with under 100 career CF innings are r=+0.075 [-0.111,+0.256], which cannot
    # clear zero. The RF signal is carried by displaced centre fielders, so the
    # column would be telling corner-only right fielders something not measured
    # on players like them. LF survives the identical test (+0.359
    # [+0.163,+0.528], n=89) and is not restriction-of-range.
    #
    # NOTHING here enters the model: positional_fit's own field() gets no sprint
    # term. OAA already contains the legs, so a sprint feature would double-count,
    # which is the same argument that rejected the arm feature.
    _RNG_SHIP = ("LF", "CF")
    _RNG_R = {"CF": {"r": 0.428, "ci95": [0.342, 0.507]},
              "LF": {"r": 0.416, "ci95": [0.323, 0.501]},
              "RF": {"r": 0.269, "ci95": [0.167, 0.365],
                     "excluded": "pure-corner subgroup r=+0.075 CI [-0.111,+0.256]"}}
    _rng_meta: dict = {}
    _sprint: dict = {}
    _pos_pool: dict = {}
    try:
        import savant_sprint as _ss
        _by = (_ss._payload().get("by_mlbam") or {})
        _season = int(src.get("target_season") or 0)

        def _fts(mlbam):
            """Current season, else one back, with the season we actually used."""
            yr = (_by.get(str(mlbam)) or {})
            for s in (_season, _season - 1):
                rec = yr.get(str(s))
                if rec and rec.get("ft_s"):
                    return float(rec["ft_s"]), s
            return None, None

        _pool = [float(r["ft_s"]) for _m, ys in _by.items()
                 for _s, r in ys.items() if _s == str(_season) and r.get("ft_s")]
        if len(_pool) >= 50:
            _mu = sum(_pool) / len(_pool)
            _sd = (sum((x - _mu) ** 2 for x in _pool) / len(_pool)) ** 0.5
            # Incumbent pools for the per-destination percentile: everyone with
            # >=400 innings at that position over the trailing three seasons. This
            # is the number a reader acts on, because "28.3 ft/s" means nothing
            # until you know it is the 28th percentile of centre fielders and the
            # 77th of left fielders.
            for _pos in _RNG_SHIP:
                _inn: dict = {}
                for _p in src["players"]:
                    tot = sum((e.get("inn") or 0.0) for e in (_p.get("evidence") or [])
                              if e.get("pos") == _pos
                              and (e.get("season") or 0) >= _season - 2)
                    if tot >= 400:
                        _inn[_p.get("mlbam")] = tot
                vals = sorted(v for v in (_fts(m)[0] for m in _inn) if v is not None)
                if len(vals) >= 20:
                    _pos_pool[_pos] = vals
            for _p in src["players"]:
                f, yr = _fts(_p.get("mlbam"))
                if f is None:
                    continue
                pct = {}
                for _pos, vals in _pos_pool.items():
                    below = sum(1 for v in vals if v < f)
                    pct[_pos] = int(round(100.0 * below / len(vals)))
                _sprint[_p.get("mlbam")] = {
                    "plus": round(100.0 + 10.0 * (f - _mu) / _sd),
                    "fts": round(f, 1), "season": yr, "pct": pct,
                }
            _rng_meta = {
                "anchor": {"season": _season, "n": len(_pool),
                           "mean": round(_mu, 2), "sd": round(_sd, 2)},
                "scale": "100 + 10z on the current-season MLB position-player pool",
                "shipPositions": list(_RNG_SHIP),
                "r": _RNG_R,
                "pools": {k: {"n": len(v), "p10": v[int(0.10 * (len(v) - 1))],
                              "p50": v[int(0.50 * (len(v) - 1))],
                              "p90": v[int(0.90 * (len(v) - 1))]}
                          for k, v in _pos_pool.items()},
                "note": ("Display only. Sprint speed is not a model input: OAA already "
                         "contains the legs, so adding it would double-count."),
            }
    except Exception as e:
        # `log` was never defined in this module, so this handler raised NameError
        # and destroyed the graceful degradation it exists to provide (2026-08-03).
        print(f"[site] Rng+ block skipped ({e!r}); Position Fit renders without it")

    def _row(p: dict) -> dict:
        pos_totals = {k: v.get("def_total") for k, v in (p.get("by_position") or {}).items()
                      if v.get("feasible") and v.get("def_total") is not None}
        row = {
            "mlbam": p.get("mlbam"),
            "name": _display_name(p.get("name")),
            "age": p.get("age"),
            "pa": p.get("pa"),
            "pos": p.get("current_pos"),
            "best": p.get("best_pos"),
            "gain": p.get("gain_runs_per_650"),
            "gainSe": p.get("gain_se"),
            "demPos": p.get("demotion_pos"),
            "demGain": p.get("demotion_gain"),
            "demSe": p.get("demotion_se"),
            "demPlayer": p.get("demotion_gain_player_part"),
            "demLeague": p.get("demotion_gain_league_part"),
            "gloveZ": p.get("glove_z"),
            "gloveZSe": p.get("glove_z_se"),
            "gloveRuns": p.get("glove_runs_per_650_at_current"),
            "bat": p.get("bat_runs_per_650"),
            "misplaced": bool(p.get("flagged_misplaced")),
            "demoted": bool(p.get("flagged_demotion")),
            "byPos": pos_totals,
            # Per-position defensive HISTORY, newly served 2026-07-30 (owner ask 1:
            # "check their OAA/DRS at specific positions they've played to see which
            # position they've performed best at, while also calibrating this for
            # sample size"). The evidence log was already computed and deliberately
            # not served; the missing half was the sample-size read, which is what
            # makes the comparison legitimate.
            #
            # `rel` is that read: innings/(innings + k_inn) for the position, using
            # the per-position stabilization constants the model already FITTED
            # (fit.signal.k_inn, 632 innings at CF through 2,539 at 1B). Identical
            # raw OAA means very different things at the two ends of that range, so
            # a reader comparing a player's spots without it would be comparing
            # confidence as if it were performance. 1.0 means a fully stabilized
            # read; 0.2 means treat the number as a rumour.
            "hist": _pos_history(p, fit),
        }
        if p.get("mlbam") in teams:
            row["team"] = teams[p["mlbam"]]
        if p.get("mlbam") in _sprint:
            row["rng"] = _sprint[p["mlbam"]]
        return {k: v for k, v in row.items() if v is not None}

    rows = [_row(p) for p in src["players"]
            if p.get("qualified") and not p.get("c_out_of_scope")
            and p.get("current_pos") and p.get("gain_runs_per_650") is not None]
    rows.sort(key=lambda r: -(r.get("gain") or 0))

    # ---- which runs/650 column the PAGE prints (owner decision 2026-08-04) ----
    # DISPLAY ONLY. The model is untouched. `ladder.values` carries the model's
    # own identification, an EXPOSURE-weighted sum-to-zero that
    # positional_fit._recentre imposes exactly; every downstream consumer
    # (prospect_def_value.py, the per-player gains in `rows` above) keeps using
    # it and it is still forwarded here. But a reader adds the nine printed
    # rungs, gets -3.96, and reads that as a broken table, because the identity
    # people check by hand is the folklore one: the EIGHT FIELDING positions sum
    # to zero. The artifact already publishes exactly that column,
    # `identification.values_fielder_centred`, and it differs from `values` by a
    # single constant (the fielder mean), so every difference between two
    # positions - which is the entire content of a positional adjustment - is
    # bit-for-bit identical. So the page prints the fielder-centred column, with
    # DH shown against that same zero line.
    # Absent on artifacts generated before 2026-07-31, in which case this falls
    # back to `values` and the renderer says so instead of claiming a convention
    # the numbers do not have.
    _ident = ladder.get("identification") or {}
    _vals_fc = _ident.get("values_fielder_centred") or None
    return {
        "generated_at": src.get("generated_at"),
        "model": src.get("model"),
        "season": src.get("target_season"),
        "valueIdentity": src.get("value_identity"),
        "nPlayers": src.get("n_players"),
        "nQualified": src.get("n_qualified"),
        "nFlagged": src.get("n_flagged"),
        "nFlaggedDemotion": src.get("n_flagged_demotion"),
        "flagRule": src.get("flag_rule"),
        "outOfScope": src.get("out_of_scope"),
        "sources": src.get("sources"),
        "caveats": src.get("caveats"),
        "rngMeta": _rng_meta or None,
        "ladder": {
            "units": ladder.get("units"),
            "method": ladder.get("method"),
            # The model's own column (exposure-weighted zero). Kept because the
            # CIs, the folklore diffs and every consumer are on this basis.
            "values": ladder.get("values"),
            # The column the table PRINTS. See the block above _ident.
            "valuesDisplay": _vals_fc or ladder.get("values"),
            "valuesDisplayBasis": "fielder_centred" if _vals_fc else "exposure_weighted",
            "ci95": ladder.get("ci95"),
            "folklore": ladder.get("folklore_ladder"),
            # The basis the folklore column is quoted on, which is NOT ours.
            # Forwarded so the page can show the like-for-like difference beside
            # the raw one instead of silently subtracting per-162-game numbers
            # from per-650-PA ones. Absent from artifacts generated before
            # 2026-08-12; the consumer falls back to the raw column alone.
            "folkloreBasis": ladder.get("folklore_basis"),
            "r2": ladder.get("r2"),
            "residSd": ladder.get("resid_sd"),
            "nPlayerSeasons": ladder.get("n_player_seasons"),
            "seasons": ladder.get("seasons"),
            "minPa": ladder.get("min_pa"),
            # The sum question, forwarded so the page can answer it. Only the
            # EXPOSURE-WEIGHTED sum is zero, and it is zero by construction
            # (positional_fit._recentre imposes it). Equal-weighting the nine
            # displayed rungs does not sum to zero and should not: DH is ~7%
            # of league exposure, not a ninth, so it over-counts the big
            # negative DH rung. Without this block the ladder simply looks
            # like it fails an identity it was never claiming.
            # Absent from artifacts generated before 2026-07-31; the consumer
            # renders the explanation only when it is present.
            "identification": ladder.get("identification"),
        },
        "accuracy": {
            "nConversions": conv.get("n_conversions"),
            "minInningsEachSide": conv.get("min_innings_each_side"),
            "mae": conv.get("mae"),
            "rmse": conv.get("rmse"),
            "corr": conv.get("corr_with_actual"),
            "advantage": conv.get("mae_advantage_over"),
            "permNull95": conv.get("perm_null95_mae_advantage"),
            "nTimeSplits": conv.get("n_time_splits"),
            "seasonAdvantageMean": conv.get("season_advantage_mean"),
            "seasonAdvantagePositiveIn": conv.get("season_advantage_positive_in"),
        },
        "demotionNull": {
            "nScored": val.get("n_scored"),
            "nMovedDown": val.get("n_moved_down"),
            "baseRate": val.get("base_rate_moved_down"),
            "auc": val.get("auc"),
            "modelMinus": val.get("model_minus"),
            "permNull95": val.get("perm_null95_auc_minus_half"),
            "nTimeSplits": val.get("n_time_splits"),
            "seasonAucMean": val.get("season_auc_mean"),
            "seasonAucSd": val.get("season_auc_sd"),
            "flagRule": val.get("flag_rule"),
            "flagRuleControl": val.get("flag_rule_control"),
            "destinationTop1": val.get("destination_top1"),
            "promotionSide": val.get("promotion_side"),
            "labelDefinition": val.get("label_definition"),
        },
        "rows": rows,
    }


# Bat-speed delta. swing_plus.json is a model input (per-season Swing+ from MLB
# bat tracking, 2024+). Only players with BOTH of the last two tracked seasons
# have a computable year-over-year delta - everyone else gets an explicit
# no-data state on the card rather than a chip implying coverage we don't have.
# The alert cut is the 10th percentile of the MEASURED delta distribution in
# this same population (a distributional flag, not a validated predictor), so
# no threshold is hand-set here.
_SWING_MIN_N = 180          # the swing_plus low_n convention (partial tracking)


def build_swing_delta_payload() -> dict | None:
    src = _cached_data_json("swing_plus.json")
    players = (src or {}).get("players") or {}
    if not players:
        return None
    seasons: set[int] = set()
    for row in players.values():
        for y in (row.get("seasons") or {}):
            try:
                seasons.add(int(y))
            except (TypeError, ValueError):
                pass
    if len(seasons) < 2:
        return None
    latest, prior = sorted(seasons)[-1], sorted(seasons)[-2]
    out, deltas = {}, []
    n_latest_only = 0
    for mlbam, row in players.items():
        ss = row.get("seasons") or {}
        a, b = ss.get(str(prior)), ss.get(str(latest))
        if not b or b.get("swing_plus") is None:
            continue
        if not a or a.get("swing_plus") is None:
            n_latest_only += 1
            continue
        d = round(float(b["swing_plus"]) - float(a["swing_plus"]), 1)
        deltas.append(d)
        out[str(mlbam)] = {
            "d": d,
            "prior": round(float(a["swing_plus"]), 1),
            "latest": round(float(b["swing_plus"]), 1),
            "nPrior": a.get("n_swings"),
            "nLatest": b.get("n_swings"),
            "lowN": bool((a.get("n_swings") or 0) < _SWING_MIN_N
                         or (b.get("n_swings") or 0) < _SWING_MIN_N),
        }
    if len(deltas) < 30:
        return None
    ds = sorted(deltas)

    def _pct(q: float) -> float:
        i = q * (len(ds) - 1)
        lo, hi = int(math.floor(i)), int(math.ceil(i))
        return round(ds[lo] + (ds[hi] - ds[lo]) * (i - lo), 2)

    return {
        "generated_at": src.get("generated_at"),
        "model": src.get("model"),
        "priorSeason": prior,
        "latestSeason": latest,
        "minSwings": _SWING_MIN_N,
        "n": len(out),
        "nLatestOnly": n_latest_only,
        "nScored": src.get("n_scored"),
        "dist": {"p10": _pct(0.10), "p25": _pct(0.25), "p50": _pct(0.50),
                 "p75": _pct(0.75), "p90": _pct(0.90),
                 "mean": round(sum(ds) / len(ds), 2)},
        "players": out,
    }


# Current-season MLB stat line, keyed by MLBAM, for the modules whose rows carry
# no stats of their own (the FA class board is a market payload). Every field is
# lifted verbatim from a shipped leaderboard; nothing is recomputed. NOTE what is
# NOT here: this site DERIVES no wRC+ and no xFIP, so neither is derived into
# this payload - HEM+ (offense-rate index), Skill FIP and ERA are the numbers the
# site actually computes.
#
# The `fip` key is NOT the standard FIP (audit F05-02). It is the boards' `fip`
# field, which rem_plus.reliever_row / sem_plus.starter_row fill from
# fip_skill: component rates shrunk toward the ROLE pool by sample size plus a
# role-pool constant. The key keeps its name because assets/fa.js reads it; the
# note below and the tile label say which number it is.
#
# Sharpened 2026-07-31, because the MLB Stats hitter board now shows a wRC+
# column and a reader could otherwise read "no wRC+" as contradicting it. Both
# statements are true and they are about different things: the site derives no
# wRC+ of its own, and the board's wRC+ is MLB's PUBLISHED value read verbatim
# (hitter_export.load_published_wrc_plus). Display is not derivation. This
# payload deliberately stays a derived-numbers payload and does not carry the
# published figure, so a downstream module cannot mistake a passed-through
# industry number for one of ours.
def build_current_lines_payload() -> dict | None:
    hit = _cached_data_json("hitter_leaderboards.json")
    sp = _cached_data_json("starter_leaderboards.json")
    rp = _cached_data_json("bullpen_leaderboards.json")
    if not (hit.get("hitters") or sp.get("starters")):
        return None
    out: dict[str, dict] = {}
    for h in (hit.get("hitters") or []):
        if h.get("mlbam") is None:
            continue
        out[str(h["mlbam"])] = _clean_line({
            "side": "hit", "team": h.get("team"), "bats": h.get("bats"),
            "pa": h.get("pa"), "hr": h.get("hr"), "sb": h.get("sb"),
            "avg": h.get("avg"), "obp": h.get("obp"), "slg": h.get("slg"),
            "ops": h.get("ops"), "woba": h.get("woba_raw"),
            "hem": h.get("hem_plus"), "xhem": h.get("xhem_plus"),
            "tier": h.get("tier"), "qual": h.get("qualified"),
        })
    for s in (sp.get("starters") or []):
        if s.get("mlbam") is None:
            continue
        out[str(s["mlbam"])] = _clean_line({
            "side": "sp", "team": s.get("team"), "role": s.get("role"),
            "ip": s.get("ip"), "gs": s.get("gs"), "era": s.get("era"),
            "fip": s.get("fip"), "kPct": s.get("k_pct"), "bbPct": s.get("bb_pct"),
            "sem": s.get("sem_plus"), "xsem": s.get("xsem_plus"),
            "qual": s.get("qualified"),
        })
    for r in (rp.get("relievers") or []):
        if r.get("mlbam") is None or str(r["mlbam"]) in out:
            continue
        out[str(r["mlbam"])] = _clean_line({
            "side": "rp", "team": r.get("team"), "role": r.get("role"),
            "ip": r.get("ip"), "era": r.get("era"), "fip": r.get("fip"),
            "kPct": r.get("k_pct"), "bbPct": r.get("bb_pct"),
            "rem": r.get("rem_plus"), "gmli": r.get("gmli"),
            "qual": r.get("qualified"),
        })
    if not out:
        return None
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "season": hit.get("season") or sp.get("season"),
        "asOf": hit.get("as_of") or sp.get("as_of"),
        "note": ("Current-season MLB lines lifted verbatim from the eephus.io "
                 "leaderboards. This site derives no wRC+ and no xFIP of its "
                 "own, so neither is served here: HEM+ is the offense-rate "
                 "index it does compute, and Skill FIP, SEM+ and REM+ are the "
                 "run-prevention numbers. The fip field is Skill FIP, the "
                 "sample-shrunk FIP with a starter-pool or reliever-pool "
                 "constant that SEM+ and REM+ are built on, and not the "
                 "standard FIP; the key keeps its name so existing readers do "
                 "not break. The MLB Stats hitter board does show "
                 "a wRC+ column, but that figure is MLB's published wRC+ "
                 "displayed verbatim rather than anything this site derives, "
                 "and it is deliberately not carried in this payload."),
        "n": len(out),
        "players": out,
    }


def _clean_line(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


# --------------------------------------------------------------------------- #
def _write(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {rel}")

# --------------------------------------------------------------------------- #
# Hand-authored surfaces are not written by any generator, so their /assets/
# refs carried a hand-bumped date stamp that nothing forced anyone to bump.
# On 2026-08-03 site.css had changed on 07-31 while all three pages still
# advertised ?v=20260730 (pitcher_index ?v=20260709), so the 7-day max-age on
# /assets/ served up to a week of stale CSS to exactly the pages that hand-edit
# it. They are now stamped from the same content hash the generated pages use,
# so any asset edit propagates on the next build with no hand step.
#
# Scoped to stylesheet links, script srcs and SVG <use> hrefs (the pixel icon
# sprite, final-pass plan 5.7 PX-09), matching test_asset_versioning's scope
# exactly: icons, manifest, canonical and preconnect are deliberately left
# alone because a momentarily stale one does not break rendering, and stamping
# them would only churn a 55k-line file. `?v=` is optional in the URL pattern
# so a newly added ref is stamped on its first build rather than waiting for
# someone to notice test_asset_versioning going red. A <use> href ends in a
# #fragment (the symbol id): the URL pattern stops the path and the old stamp
# at "#" and writes the fragment back after the new stamp, so
# "/assets/eephus-icons.svg?v=old#i-ledger" becomes "?v=<hash>#i-ledger".
HAND_AUTHORED_PAGES = (
    "prospx/index.html",
    "collegesavant/index.html",
    "collegesavant/pitcher_index.html",
)

_STYLESHEET_TAG_RE = re.compile(r"<link\b[^>]*\brel=[\"']stylesheet[\"'][^>]*>", re.I)
_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*\bsrc=[\"'][^\"']+[\"'][^>]*>", re.I)
_USE_TAG_RE = re.compile(r"<use\b[^>]*\bhref=[\"'][^\"']+[\"'][^>]*>", re.I)
_ASSET_URL_RE = re.compile(r'((?:href|src)=")(/assets/[^"?#]+)(?:\?v=[^"#]*)?(#[^"]*)?(")')


def _restamp_html(text: str) -> str:
    """Return `text` with every /assets/ stylesheet href, script src and <use>
    href stamped with the asset's current content hash, any #fragment kept.
    Refs whose target is absent from the tree keep whatever they carry - there
    is no content to hash."""

    def _stamp_url(m: "re.Match[str]") -> str:
        asset = m.group(2).lstrip("/")
        if not (ROOT / asset).exists():
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}?v={_asset_ver(asset)}{m.group(3) or ''}{m.group(4)}"

    def _stamp_tag(m: "re.Match[str]") -> str:
        return _ASSET_URL_RE.sub(_stamp_url, m.group(0))

    for tag_re in (_STYLESHEET_TAG_RE, _SCRIPT_TAG_RE, _USE_TAG_RE):
        text = tag_re.sub(_stamp_tag, text)
    return text


def restamp_hand_authored_pages() -> None:
    """Stamp every /assets/ stylesheet, script and <use> ref in the
    hand-authored pages with the asset's current content hash (_restamp_html)."""
    for rel in HAND_AUTHORED_PAGES:
        path = ROOT / rel
        if not path.exists():
            print(f"  skipped {rel} (absent)")
            continue
        original = path.read_text(encoding="utf-8")
        stamped = _restamp_html(original)
        if stamped != original:
            path.write_text(stamped, encoding="utf-8")
            print(f"  restamped {rel}")
        else:
            print(f"  {rel} asset stamps already current")


def main() -> None:
    print("build_site.py - generating editorial pages")
    art_dir = CONTENT / "articles"
    articles = [parse_article(p) for p in sorted(art_dir.glob("*.md"))] if art_dir.exists() else []
    articles.sort(key=lambda a: a.get("date_sort", ""), reverse=True)  # newest first

    data = load_site_data()
    print(" data layer:", "loaded" if data else "MISSING (run run_monthly) - modules will be empty")

    _write("index.html", build_home(articles, data))
    _write("news/index.html", build_news(data))
    _write("history/index.html", build_this_day(data))
    _write("articles/index.html", build_articles_index(articles))
    for a in articles:
        _write(f"articles/{a['slug']}/index.html", build_article_page(a))
    _write("forums/index.html", build_forums_index())
    _write("fa/index.html", build_fa())
    _write("projections/index.html", build_projections())
    _write("mlbstats/index.html", build_mlbstats())
    _write("pal/index.html", build_pal())
    _write("trademachine/index.html", build_trademachine())
    _write("arbitration/index.html", build_arbitration())
    _write("fantasy/index.html", build_fantasy())
    # Diamond section (2026-08-05). Six public pages; the gate flag is off.
    _write("dynasty/index.html", build_dynasty())
    _write("redraft/index.html", build_redraft())
    _write("dfs/index.html", build_dfs())
    _write("betting/index.html", build_betting())
    _write("diamond/index.html", build_diamond())
    _write("parks/index.html", build_parks())
    _write("hof/index.html", build_hof())
    _write("management/index.html", build_management())
    _write("franchise/index.html", build_franchise())
    _write("ledger/index.html", build_ledger())
    _write("models/index.html", build_models())
    _write("glossary/index.html", build_glossary())
    _write("teams/index.html", build_teams_redirect())
    _write("team/index.html", build_team())
    _write("sources/index.html", build_sources())
    _write("report/index.html", build_bug_report())
    _write("404.html", build_404())
    _write("robots.txt", build_robots())
    _write("sitemap.xml", build_sitemap(articles))

    # The hand-authored pages share /assets/ with everything above, so they are
    # re-stamped on the same pass rather than by hand (see the note above).
    restamp_hand_authored_pages()

    # Derived browser payloads (slim, display-only slices of heavier or
    # non-shipping model artifacts). Absent source => the file is left exactly
    # as it was, and the surface paints its own empty state.
    for rel, builder in (("data/positional_fit_ui.json", build_positional_fit_payload),
                         ("data/swing_delta.json", build_swing_delta_payload),
                         ("data/mlb_current_lines.json", build_current_lines_payload)):
        payload = builder()
        if payload:
            _write(rel, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"  skipped {rel} (source artifact missing or too thin)")

    # eFV movement alerts feed (data/efv_alerts.json). Built from the players
    # list already parsed above, so the 74MB data/timeseries.json is read once
    # per build rather than twice. The gate is _genuine_mover_step, the SAME
    # selector the homepage Top Movers module uses, passed in rather than
    # copied so an alert can never fire on something the board does not call a
    # move; the board grade rides _EFV_GRADES, the canonical map. The
    # refuse-to-publish-empty guard lives inside efv_alerts.build_payload, so
    # an empty run keeps the previous feed and files RED instead of publishing
    # "nothing moved".
    _write_efv_alerts(data)

    print(f"done - {len(articles)} article(s).")


def _write_efv_alerts(data: dict | None) -> None:
    """Write data/efv_alerts.json from the loaded board data.

    Separate from the derived-payload loop above because that loop's builders
    take no arguments and this one needs the already-parsed players. Never
    raises: an alerts feed is an additive surface and must not be the reason a
    site rebuild fails."""
    players = (data or {}).get("players") or []
    if not players:
        print("  skipped data/efv_alerts.json (no board data loaded)")
        return
    try:
        payload = efv_alerts.build_payload(
            players, mover_step=_genuine_mover_step, board_grades=_EFV_GRADES,
            source_as_of=(data or {}).get("as_of_iso") or None)
    except Exception:                       # noqa: BLE001 - never fail the build
        print("  skipped data/efv_alerts.json (builder raised; prior feed kept)")
        return
    guard = payload.get("guard") or {}
    _write("data/efv_alerts.json",
           json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    if guard.get("stale"):
        print(f"  efv_alerts: 0 movers this run, kept the previous "
              f"{guard.get('n')} (vintage {guard.get('kept_from')})")
    else:
        print(f"  efv_alerts: {payload.get('n_alerts')} movers "
              f"({payload.get('n_at_floor')} at the model floor)")

if __name__ == "__main__":
    main()
