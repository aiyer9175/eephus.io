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
    /team/         -> team/index.html          (the Masthead, from data/team.json)

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
import awards_core
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

# The slim term index every page but /glossary/ and PROSPX reads (QHOP02).
# eephus-gl.js reads a term's name, short line, aliases, category, module and
# priority off it; the long fields stay in data/glossary.json for the two
# pages that render them. A pure function of glossary.json, so _GL_DATA_VER
# versions its url too. Written by main(); gitignored, rebuilt by every build.
GL_INDEX_FIELDS = ("id", "term", "definition", "aliases", "category", "module", "priority")


def glossary_index_doc() -> dict:
    doc = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    return {"source": "data/glossary.json", "groups": doc.get("groups") or {},
            "entries": [{k: e[k] for k in GL_INDEX_FIELDS if k in e}
                        for e in doc.get("entries") or []]}


def write_glossary_index(path: Path | None = None) -> Path:
    out = path or (ROOT / "data" / "glossary_index.json")
    text = json.dumps(glossary_index_doc(), ensure_ascii=False, separators=(",", ":"))
    if not out.exists() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    return out


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
# /franchise/ - Franchises (2026-09-23, D3): the org-level grade tree.
# /franchises/ -> a noindex redirect to /franchise/ (the TEAM-1 rename).
_FRANCHISE_VER = _asset_ver("assets/franchise.js")
_FRANCHISE_CSS_VER = _asset_ver("assets/franchise.css")
# /team/ - the Masthead (TEAM-5, 2026-10-02): the baseball-card staff page.
_TEAM_VER = _asset_ver("assets/team.js")
_TEAM_CSS_VER = _asset_ver("assets/team.css")
# /scores/ - Scores / Standings (SCORES_3, behind scores_core.SCORES_LIVE): the
# page shell and its two eager assets. The lazy video and bracket chunks
# (SCORES_4a, SCORES_4b) get their own stamps when they land.
_SCORES_VER = _asset_ver("assets/scores.js")
_SCORES_CSS_VER = _asset_ver("assets/scores.css")
# The lazy video chunk (SCORES_4a): scores.js loads it on the first game-view
# open from the mount root's data-vv stamp, never as a tag in the shell.
_SCORES_VIDEO_VER = _asset_ver("assets/scores-video.js")
_SCORES_BRACKET_VER = _asset_ver("assets/scores-bracket.js")   # the lazy bracket chunk (SCORES_4b)
_SCORES_PREGAME_VER = _asset_ver("assets/scores-pregame.js")   # the pregame context (SCORES_6), eager
_HOF_CSS_VER = _asset_ver("assets/hof.css")
# /awards/ - the Awards section of Awards / HoF (AWARDS_7), behind awards_core.AWARDS_LIVE.
_AWARDS_VER = _asset_ver("assets/awards.js")
_AWARDS_CSS_VER = _asset_ver("assets/awards.css")
# My Ballot (AWARDS_9): the lazy chunk and its stylesheet, loaded by awards.js on the
# first My Ballot open from the stamped URLs on the mount's data attributes.
_AWARDS_BALLOT_VER = _asset_ver("assets/awards-ballot.js")
_AWARDS_BALLOT_CSS_VER = _asset_ver("assets/awards-ballot.css")
# /models/ - the model accountability hub. Client is filter-only: every row,
# count and date on that page is server-rendered here at build time, so the
# surface still tells the truth with JavaScript off.
_ACCT_HUB_VER = _asset_ver("assets/accountability.js")
_ACCT_HUB_CSS_VER = _asset_ver("assets/accountability.css")
# /models/updates/ - Model Updates (LIBRARY_12): the same filter-only client
# shape; the page is complete server-side.
_MU_VER = _asset_ver("assets/model_updates.js")
_MU_CSS_VER = _asset_ver("assets/model_updates.css")
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
    had. An empty map emits no script tag at all.

    The scores files (/data/scores/, written by tools/scores_job.py between
    builds) are refused for the same reason: a build-time stamp would pin a
    stale scoreboard."""
    stamps: dict[str, str] = {}
    for name in names:
        if name.startswith("betting"):
            raise ValueError(
                f"{name} is a close-job payload and must never be content-stamped: "
                "it mutates intra-day without a rebuild, and a build-time stamp "
                "would serve a week-stale copy under the /data/ max-age.")
        if name.startswith("scores"):
            raise ValueError(
                f"{name} is a scores job payload and must never be content-stamped: "
                "the job rewrites it between builds, and a build-time stamp would "
                "pin a stale scoreboard under the /data/ max-age.")
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
# redirects there through the 404 page's map (RETIRED_ROUTES) and the nav
# entry is gone.
# A nav entry is either a LEAF (key, label, href) or a GROUP dict
#   {"group": <label>, "key": <group key>, "children": [(key, label, href), ...]}
# rendered as a click dropdown in the top bar (_nav) and a nested sub-block in
# the homepage sidebar. The MLB-facing modules (Free Agency, Projections, MLB
# Stats) live under one "MLB Modules" group; PROSPX/CollegeSavant stay top-level
# (MiLB + amateur). This is the SINGLE source - _nav(), the sidebar, and the
# hand-maintained static nav copies (prospx + the two CollegeSavant pages) all
# mirror it; test_collegesavant_nav_in_sync guards the static copies.
# The glossary module's display name (owner ask 2026-10-02, "rename glossary
# to Library"). The module KEY "glossary", the URL /glossary/ and the data file
# names stay, so every link already shared keeps working; /library/ is a
# redirect stub to /glossary/. Every place a reader sees the module's name
# reads this constant, never a literal.
GLOSSARY_DISPLAY_NAME = "Library"

NAV_ITEMS = [
    ("home",     "Home",             "/"),
    ("prospx",   "PROSPX",           "/prospx/"),
    ("collegesavant", "CollegeSavant", "/collegesavant/"),
    {"group": "MLB Modules", "key": "mlb", "children": [
        # Franchises (2026-09-23, D3; renamed from "Franchise" 2026-10-02,
        # owner decision TEAM-1, key and URL unchanged): the hub before the
        # modules, FIRST in the group by owner decision. The hand-kept static
        # copies carry the same entry in the same slot
        # (test_collegesavant_nav_in_sync).
        ("franchise",   "Franchises",  "/franchise/"),
        # Scores / Standings (SCORES_5b; owner answer SC-NAV, second in the
        # group directly after Franchises; renamed from "MLB Scores" by the
        # 2026-10-02 Standings plan). One leaf: /standings/ passes
        # active="scores". The hand-kept static copies carry the same entry in
        # the same slot (test_collegesavant_nav_in_sync).
        ("scores",      "Scores / Standings", "/scores/"),
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
    # and /dfs/ forward through the 404 page's hash-preserving map
    # (RETIRED_ROUTES), so every bookmark written against the split still
    # lands on the board it named. Every page in this
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
    ("glossary", GLOSSARY_DISPLAY_NAME, "/glossary/"),
    # The Masthead (owner decision TEAM-5, 2026-10-02): the staff page, with
    # the Developers and the Writers and Analysts groups. Key and URL kept.
    ("team",     "Masthead",          "/team/"),
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
# THE MLB NEWS TYPE REGISTRY (HOME_2; site-pass plan 3.1 to 3.3, LANE_HOME
# 2.1 and 2.2). Colour names the FAMILY, the pictogram names the event inside
# it, the value text carries the number or the terms. Every news surface reads
# these two tables: the ticker, the rail, /news/, /history/, the /news/ GFX
# painter, and through EEPHUS_HUB.wireType and EEPHUS_HUB.wireFamily in
# assets/eephus-hub.js (test_wire_type_system.py pins the copies equal) the
# /projections/ timeline strip. A family's colour is its CSS token: --wire-<fam>
# on page ground, --wire-<fam>-panel on the theme-fixed terminal panel.
# tag: the key's label. sr: the hidden prefix every row carries. label: the
# filter chip. mark: the family's pictogram on the key and the chips.
_WIRE_FAMILIES = {
    "pro": {"tag": "PRO", "sr": "Prospect:", "label": "Prospects", "mark": "prospx"},
    "mlb": {"tag": "MLB", "sr": "MLB:", "label": "MLB", "mark": "franchise"},
    "fa":  {"tag": "FA", "sr": "Free agency:", "label": "Free agency", "mark": "ev-signing"},
    "trd": {"tag": "TRD", "sr": "Trade:", "label": "Trades", "mark": "ev-trade"},
    "inj": {"tag": "IL", "sr": "Injury:", "label": "Injuries", "mark": "ev-il"},
}
# type code -> fam, ico (pictogram key), val (value label), weight, rail.
# ico is the interim symbol of plan 3.3 (HOME_7 swaps in the final keys once
# PX_SYSTEM_SWEEP draws them); ev-draft and ev-intl are ICON_FOR aliases.
# weight is the rail and ticker order of plan 3.5 item 4 (0: grade moves order
# by step size; a 60-day IL placement takes 85; a code the plan does not weigh
# takes 60 when rail-eligible and 40 otherwise). rail: True, False, or "board"
# (board players only). The selection that applies weight and rail is HOME_3's;
# today's rail and ticker keep their order. fa_elect is the one code the plan
# does not list: the /history/ ledger's DFA rows ("declared free agency").
_WIRE_TYPES = {
    "grade_up":      {"fam": "pro", "ico": "ev-up", "val": "grade up", "weight": 0, "rail": True},
    "grade_down":    {"fam": "pro", "ico": "ev-down", "val": "grade down", "weight": 0, "rail": True},
    "promo":         {"fam": "pro", "ico": "ev-promo", "val": "promotion", "weight": 50, "rail": True},
    "demo":          {"fam": "pro", "ico": "ev-demo", "val": "demotion", "weight": 50, "rail": True},
    "debut":         {"fam": "pro", "ico": "ev-debut", "val": "MLB debut", "weight": 95, "rail": True},
    "draft_sign":    {"fam": "pro", "ico": "ev-draft", "val": "signed", "weight": 50, "rail": "board"},
    "intl_sign":     {"fam": "pro", "ico": "ev-intl", "val": "IFA signing", "weight": 50, "rail": "board"},
    "callup":        {"fam": "mlb", "ico": "ev-promo", "val": "contract selected", "weight": 70, "rail": True},
    "recall":        {"fam": "mlb", "ico": "ev-promo", "val": "recalled", "weight": 40, "rail": False},
    "optioned":      {"fam": "mlb", "ico": "ev-demo", "val": "optioned", "weight": 40, "rail": False},
    "dfa":           {"fam": "mlb", "ico": "franchise", "val": "DFA", "weight": 80, "rail": True},
    "outright":      {"fam": "mlb", "ico": "franchise", "val": "outrighted", "weight": 40, "rail": False},
    "claim":         {"fam": "mlb", "ico": "franchise", "val": "claimed", "weight": 75, "rail": True},
    "release":       {"fam": "mlb", "ico": "franchise", "val": "released", "weight": 60, "rail": True},
    "retire":        {"fam": "mlb", "ico": "franchise", "val": "retired", "weight": 60, "rail": True},
    "suspend":       {"fam": "mlb", "ico": "franchise", "val": "suspended", "weight": 60, "rail": True},
    "rule5":         {"fam": "mlb", "ico": "franchise", "val": "Rule 5 pick", "weight": 58, "rail": True},
    "award":         {"fam": "mlb", "ico": "hof", "val": "award", "weight": 60, "rail": True},
    "fa_sign":       {"fam": "fa", "ico": "ev-signing", "val": "MLB deal", "weight": 90, "rail": True},
    "minor_deal":    {"fam": "fa", "ico": "ev-signing", "val": "MiLB deal", "weight": 40, "rail": False},
    "opt_declined":  {"fam": "fa", "ico": "ev-signing", "val": "option declined", "weight": 45, "rail": True},
    "opt_exercised": {"fam": "fa", "ico": "ev-signing", "val": "option exercised", "weight": 45, "rail": True},
    "qo":            {"fam": "fa", "ico": "ev-signing", "val": "QO offered", "weight": 44, "rail": True},
    "fa_elect":      {"fam": "fa", "ico": "ev-signing", "val": "elected free agency", "weight": 40, "rail": False},
    "trade":         {"fam": "trd", "ico": "ev-trade", "val": "trade", "weight": 100, "rail": True},
    "il_place":      {"fam": "inj", "ico": "ev-il", "val": "IL", "weight": 65, "rail": True},
    "il_return":     {"fam": "inj", "ico": "ev-il", "val": "activated", "weight": 40, "rail": False},
}
# The two pictogram keys that are aliases, not drawings (plan 3.3).
_WIRE_ICON_ALIAS = {"ev-draft": "px-draft", "ev-intl": "px-intl"}
# type code -> the sprite symbol it draws, derived from the registry.
_WIRE_ICON = {code: _WIRE_ICON_ALIAS.get(row["ico"], row["ico"]) for code, row in _WIRE_TYPES.items()}


def _merge_icon_maps(*maps: dict) -> dict:
    out: dict = {}
    for m in maps:
        for k, v in m.items():
            if out.get(k, v) != v:
                raise ValueError(f"icon key {k!r} maps to both i-{out[k]} and i-{v}")
            out[k] = v
    return out


# A nav key whose drawing is named for its display name, not its key: the
# glossary module reads "Library" and draws i-library (owner ask 2026-10-02).
_NAV_ICON = {"glossary": "library"}

ICON_FOR = _merge_icon_maps(
    {k: _NAV_ICON.get(k, k) for k, _label, _href in nav_leaves()},
    {k: k for k in ("models", "parks", "news", "history", "watchlist", "scores")},
    _PX_SECTION_ICON,
    _WIRE_ICON,
    _WIRE_ICON_ALIAS,
    # The Awards symbols (AWARDS_7): the podium on the module strip and the award
    # cards, the ballot card on the My Ballot tab.
    {k: k for k in ("aw-podium", "aw-ballot")},
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
    """The wire pictogram (PX-17): a registry type draws its 12 px icon; an
    unknown type keeps its text glyph. The GFX blob keeps the text glyph for
    the canvas painter's fallback (PX-18)."""
    return _ico(_WIRE_ICON[typ], 12) if typ in _WIRE_ICON else html.escape(glyph or "")


def _wire_attrs(typ: str) -> str:
    """' data-fam="trd" data-type="trade"' for a registry type code, '' for any
    other: the family the stylesheet colours by and the code a filter reads."""
    row = _WIRE_TYPES.get(typ)
    return f' data-fam="{row["fam"]}" data-type="{typ}"' if row else ""


def _wire_lead(typ: str) -> str:
    """The row lead on every news surface (LANE_HOME 2.3): the type's 12 px
    pictogram, which takes its family colour, then the family's hidden prefix
    ("Trade: ") so a screen reader hears the family the colour shows. '' for a
    type outside the registry, whose text glyph stays in its value."""
    row = _WIRE_TYPES.get(typ)
    if not row:
        return ""
    return (f'<span class="wire-ico">{_ico(_WIRE_ICON[typ], 12)}</span>'
            f'{_sr(_WIRE_FAMILIES[row["fam"]]["sr"])}')


def _wire_key_html(attr: str, fams: tuple = tuple(_WIRE_FAMILIES),
                   lead: tuple = (), tail: tuple = (), tags: bool = False) -> str:
    """The family key as a filter bar: one aria-pressed button per family (its
    mark in the family colour, then the tag or the chip label), with optional
    `lead` and `tail` (value, label) buttons around them (All, Grades). `attr`
    names the data attribute the page's filter script reads."""
    def btn(val: str, inner: str, pressed: bool, fam: str = "", title: str = "") -> str:
        fa = f' data-fam="{fam}"' if fam else ""
        tip = f' title="{html.escape(title)}"' if title else ""
        return (f'<button type="button" class="chip wire-chip{" active" if pressed else ""}"{fa}{tip} '
                f'aria-pressed="{"true" if pressed else "false"}" {attr}="{val}">{inner}</button>')
    out = [btn(v, html.escape(lbl), i == 0) for i, (v, lbl) in enumerate(lead)]
    for f in fams:
        fam = _WIRE_FAMILIES[f]
        text = fam["tag"] if tags else fam["label"]
        out.append(btn(f, f'<span class="wire-ico">{_ico(fam["mark"], 12)}</span>{html.escape(text)}',
                       False, fam=f, title=fam["label"] if tags else ""))
    out += [btn(v, html.escape(lbl), False) for v, lbl in tail]
    return "".join(out)


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
    # QHOA10: every [data-theme-toggle] carries aria-pressed (true = dark), set
    # once the buttons exist and again on every toggle.
    'function eephusThemeSync(){try{var d=document.documentElement.getAttribute("data-theme")==="dark"?"true":"false";'
    'document.querySelectorAll("[data-theme-toggle]").forEach(function(b){b.setAttribute("aria-pressed",d);});}catch(e){}}'
    'document.addEventListener("DOMContentLoaded",eephusThemeSync);'
    'function eephusToggleTheme(){try{var c=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";'
    'document.documentElement.setAttribute("data-theme",c);localStorage.setItem("prospect-tracker.theme",c);}catch(e){}eephusThemeSync();}</script>'
)
# QHOP03 (2026-10-07): both PixelMplus12 faces load with font-display: swap,
# and with no preload the wider pixel face landed after first paint and
# rewrapped the page (CLS 0.27 on /history/, 0.15 on /404.html with the woff2
# held 400 ms). Preloading them from the head puts the face in before layout.
# The three hand pages get the same two lines from restamp_hand_authored_pages.
FONT_PRELOAD = (
    '<link rel="preload" href="/assets/fonts/pixelmplus12-regular.woff2" as="font" type="font/woff2" crossorigin>\n'
    '<link rel="preload" href="/assets/fonts/pixelmplus12-bold.woff2" as="font" type="font/woff2" crossorigin>'
)
_FONT_PRELOAD_RE = re.compile(r'(\n([ \t]*)<meta name="viewport"[^>]*>)')


def _ensure_font_preload(text: str) -> str:
    """Insert FONT_PRELOAD after a hand page's viewport meta, once."""
    if 'pixelmplus12-regular.woff2" as="font"' in text:
        return text
    m = _FONT_PRELOAD_RE.search(text)
    if not m:
        return text
    ind = m.group(2)
    lines = "".join(f"\n{ind}{ln}" for ln in FONT_PRELOAD.split("\n"))
    return text[:m.end()] + lines + text[m.end():]


# Favicons + PWA + theme-color - SVG primary (crisp at any size), ICO + 32px PNG
# fallbacks, apple-touch for home-screen pins, the web manifest (installable
# identity), and theme-color for the mobile browser chrome (navy on light,
# near-black on dark). The artifacts are committed (tools/generate_brand_assets.py
# regenerates them when the brand changes); hand-edited pages (prospx,
# collegesavant) carry the same literal block. FAVICON_LINKS itself is chosen
# by the PIXEL_BRAND flag beside EEPHUS_VERSION below.
_FAVICON_LINKS_LEGACY = (
    '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">\n'
    '<link rel="icon" href="/favicon.ico" sizes="32x32">\n'
    '<link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">\n'
    '<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">\n'
    '<link rel="manifest" href="/assets/site.webmanifest">\n'
    '<meta name="theme-color" content="#0E2B4D" media="(prefers-color-scheme: light)">\n'
    '<meta name="theme-color" content="#0C0C0E" media="(prefers-color-scheme: dark)">'
)
# The pixel set (BR-04, tools/pixel_brand.py writes assets/brand/): the favicon
# strikes 16/32/48 (pixel-equal to the served PX-23 copies), the app icons as
# ball strike 32 at 4x, 4x, 12x and 9x on the dark field, and a manifest whose
# icons point at the same folder.
_FAVICON_LINKS_PIXEL = (
    '<link rel="icon" href="/assets/brand/favicon.svg" type="image/svg+xml">\n'
    '<link rel="icon" href="/assets/brand/favicon.ico" sizes="32x32">\n'
    '<link rel="icon" href="/assets/brand/favicon-32.png" type="image/png" sizes="32x32">\n'
    '<link rel="apple-touch-icon" href="/assets/brand/apple-touch-icon.png">\n'
    '<link rel="manifest" href="/assets/brand/site.webmanifest">\n'
    '<meta name="theme-color" content="#0E2B4D" media="(prefers-color-scheme: light)">\n'
    '<meta name="theme-color" content="#0C0C0E" media="(prefers-color-scheme: dark)">'
)

# Default Open Graph / Twitter share image - every page emits social-card tags
# (a shared eephus.io link should never render as a bare URL). Pages with a
# richer card (per-article share-card.png) override it.
DEFAULT_SHARE_IMAGE = f"{SITE_ORIGIN}/assets/share-default.png"
# The pixel share cards (PB-07 / BR-07, tools/pixel_brand.py): a lowercase
# default card in assets/brand/ and one card per module in assets/og/<key>.png.
# Served only under PIXEL_BRAND; off, every page keeps DEFAULT_SHARE_IMAGE.
DEFAULT_SHARE_IMAGE_PIXEL = f"{SITE_ORIGIN}/assets/brand/share-default.png"
OG_CARD_KEYS = ("prospx", "collegesavant", "franchise", "fa", "projections", "mlbstats", "pal",
                "trademachine", "arbitration", "ledger", "management", "hof", "fantasy",
                "betting", "diamond")


def default_share_image() -> str:
    """The card a page without its own card unfurls with, read at call time."""
    return DEFAULT_SHARE_IMAGE_PIXEL if PIXEL_BRAND else DEFAULT_SHARE_IMAGE


def module_share_image(key: str) -> str:
    """A module page's own card under PIXEL_BRAND; "" (the default card) off."""
    assert key in OG_CARD_KEYS, key
    return f"{SITE_ORIGIN}/assets/og/{key}.png" if PIXEL_BRAND else ""

# Contact / feedback channel for the Open Beta - one address, linked from the
# footer of every page. Plain mailto keeps it dependency-free until the
# account layer ships.
FEEDBACK_MAILTO = (
    "mailto:arkndjl@gmail.com?subject=eephus.io%20beta%20feedback"
)

# Display name of the /news/ event feed (owner rename 2026-10-02). The rail
# head, ticker tag, footer link, /news/ h1 and title and the GFX cards read
# this one constant; the URL stays /news/.
NEWS_LABEL = "MLB News"

# ONE NAME PER DESTINATION (QHOC11). The footer said About for the page the
# nav calls Masthead and This Day for Today in Prospect History, and the home
# card said Model Ledger (easily read as the Club Ledger) for Model
# Accountability. Nav leaves keep their NAV_ITEMS label; the three pages with
# no nav row are named here, and every surface that links them reads this map.
PAGE_LABELS = {h: lab for _k, lab, h in nav_leaves()}
PAGE_LABELS.update({"/history/": "Today in Prospect History",
                    "/models/": "Model Accountability",
                    "/models/updates/": "Model Updates",
                    "/news/": NEWS_LABEL})


def _footer() -> str:
    """The shared page footer: identity line left, useful links right.
    Every editorial surface and the homepage emit the same block."""
    year = date.today().year
    links = (
        f'<a href="/team/">{PAGE_LABELS["/team/"]}</a>'
        f'<a href="/news/">{NEWS_LABEL}</a>'
        # /history/ (Today in Prospect History) is a full generated surface but
        # carried NO nav entry anywhere - its only inbound link was the homepage
        # module's "See all" kicker, so it was unreachable from every other page.
        f'<a href="/history/">{PAGE_LABELS["/history/"]}</a>'
        f'<a href="/parks/">Park Factors</a>'
        # The model ledger carries no nav row (the nav has three hand-maintained
        # static copies), so the footer is its primary address on every page.
        f'<a href="/models/">{PAGE_LABELS["/models/"]}</a>'
        f'<a href="/models/updates/">{PAGE_LABELS["/models/updates/"]}</a>'
        f'<a href="/sources/">Data Sources</a>'
        # The artifact catalog (what we publish, on what cadence, how stable)
        # is the second half of /sources/. It gets its own footer link because
        # nobody looking for an API looks under "Data Sources", and a page you
        # cannot find is the same as a page that does not exist.
        f'<a href="/sources/#api">Public Data</a>'
        f'<a href="/glossary/">{GLOSSARY_DISPLAY_NAME}</a>'
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
    # draw of the vector ball read as an "O". Under PIXEL_BRAND it reads the
    # same strike from the pixel set in assets/brand/.
    src = "/assets/brand/favicon-16.png" if PIXEL_BRAND else "/assets/favicon-16.png"
    mark = (f'<img src="{src}" alt="" aria-hidden="true" width="16" height="16" '
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
# PIXEL_BRAND (owner ask 2, Part 8 pixel_branding lane): the pixel brand swap.
# Off by default, and off builds byte-identical pages. On, FAVICON_LINKS and the
# footer mark read the pixel set in assets/brand/ (BR-04), and (PB-07) every
# page unfurls with the pixel default card or its module's own card. It flips in
# its own commit (PB-10). The wordmark no longer rides it: every eephus.io wordmark
# (nav, homepage sidebar, homepage hero, the three hand-kept navs) serves the
# committed pixel lockup from assets/brand/ whatever the flag says (owner ask
# 2026-10-02, PX_LOGO_ANIMATION; see eephus_merged_wordmark()).
PIXEL_BRAND = False
FAVICON_LINKS = _FAVICON_LINKS_PIXEL if PIXEL_BRAND else _FAVICON_LINKS_LEGACY
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
    # Franchises (2026-09-23). Slot 0 is the sigil, as the rows above.
    "franchise": ("β", "Beta. Franchise Index is a descriptive rank, not a forecast"),
    "forums": ("β", "Forums is in beta"),
    "parks": ("β", "Beta. Display only: no model reads these factors"),
    "management": ("β", "Beta. Realized value only; the gate returned a bounded null for the steal and no family is ranked by skill"),
    "hof": ("β", "Beta. Every unpublished section names its blocker"),
    # Scores / Standings (SCORES_3, behind scores_core.SCORES_LIVE).
    "scores": ("β", "Beta. Scores, win probability and video come from MLB; Stars of the Game is a published rule"),
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

# The dev byline that sat above every module masthead is gone (owner decision
# TEAM-2, 2026-10-02): attribution lives on the Masthead (/team/) only. It
# carried no build version, so nothing moved to the Library's release notes.
# The .section-head--byline wrapper stays as the stacked-title layout.

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

# eephus.io wordmark: the pixel lockup (PB-03, PB-Q1 B Stepped), served on
# every page since the owner's 2026-10-02 ask ("the logo animation on the
# homepage is still showing the old animation"; PX_LOGO_ANIMATION). The
# committed fragment for the placement: s 2 in the nav and the sidebar, s 6 on
# the hero with the s 4 phone twin (switched by a media query under 540 px),
# the words kept as visually hidden text. The hero fragments carry the pitch
# (wm-px--play: the arc lights run by run, then the ball drops in whole
# pixels); every lockup replays it on hover. The old vector mark (gradient arc
# plus em-scaled ball) and its dash draw-on are retired.
_PIXEL_WORDMARK_SCALES = {"mast": (6, 4)}


@functools.lru_cache(maxsize=None)
def pixel_wordmark_fragment(scale: int) -> str:
    """The committed DOM fragment assets/brand/wordmark-s{scale}.svg, byte for
    byte (tools/pixel_brand.py writes it; nothing here edits it)."""
    return (ROOT / "assets" / "brand" / f"wordmark-s{scale}.svg").read_bytes().decode("utf-8").strip()


def pixel_wordmark(uid: str, tag: str = "h1") -> str:
    """The pixel lockup: the placement's fragment(s) plus the words as
    visually hidden text, so the homepage h1 stays an h1 that reads eephus.io."""
    svgs = "".join(pixel_wordmark_fragment(s) for s in _PIXEL_WORDMARK_SCALES.get(uid, (2,)))
    return (f'<{tag} class="nameplate eephus-wordmark-px">{svgs}'
            f'<span class="wm-txt">eephus.io</span></{tag}>')


def eephus_merged_wordmark(uid: str, tag: str = "h1") -> str:
    """Every eephus.io wordmark on the site: the pixel lockup for the placement
    (``uid`` "mast" is the hero; any other is the s 2 nav and sidebar mark)."""
    return pixel_wordmark(uid, tag)

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
    """Homepage hero lockup: the pixel wordmark with the β tag and the
    @eephus_io chip stacked beside it (β on top, X under - the X chip carries
    the link accent so it reads clickable)."""
    chips = (
        f'<div class="eephus-logo-chips">{BETA_BADGE}'
        f'{_x_link("eephus_io", cls="eph-xlink--beta eph-xlink--live")}'
        f'{_discord_link(cls="eph-xlink--beta eph-xlink--live")}</div>'
    ) if badge else ""
    # The hero fragments carry their own one-shot (wm-px--play: the pitch, then
    # one glint per page view); it runs under Reduce Motion as well, see
    # assets/site.css. The nav and sidebar lockups replay it on hover only.
    return f'<div class="eephus-logo">{eephus_merged_wordmark("mast")}{chips}</div>'

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

def _png_size(path: Path) -> tuple[int, int] | None:
    """(width, height) from a PNG's IHDR chunk, or None if not a readable PNG."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")

_ARTICLE_IMG_RE = re.compile(r"<img\b([^>]*?)\s*/?>", re.I)

def _size_article_images(body_html: str) -> str:
    """Give every inline article image that points at a local PNG its intrinsic
    width and height (read from the file header, so the page reserves the box
    and does not shift as images arrive) plus loading="lazy" and
    decoding="async" (bloat finding AS15: nine inline PNGs, 838 KB, loaded
    eagerly with no size). The stylesheet's `.article-body img { max-width:
    100%; height: auto; }` keeps the rendered size responsive. A tag that
    already carries a width, or names a file we cannot size, is left alone."""
    def fix(m: re.Match) -> str:
        attrs = m.group(1)
        if re.search(r"\bwidth\s*=", attrs, re.I):
            return m.group(0)
        src = re.search(r'\bsrc\s*=\s*"(/assets/[^"?#]+\.png)"', attrs, re.I)
        size = _png_size(ROOT / src.group(1).lstrip("/")) if src else None
        if not size:
            return m.group(0)
        return (f'<img{attrs} width="{size[0]}" height="{size[1]}" '
                f'loading="lazy" decoding="async">')
    return _ARTICLE_IMG_RE.sub(fix, body_html)

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
    meta["body_html"] = _linkify_players(_size_article_images(render_markdown(body)))
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
    """Stable per-person anchor slug for a Masthead card (e.g.
    'Will Cahoon' -> 'will-cahoon'). data/team.json keys follow it, so the
    card id and the article byline deep-link always line up."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")

def _team_index() -> dict:
    """name(lowercased) -> {slug, handle} from data/team.json (the Masthead
    roster) - the single source of truth for team identity + X handles. The
    slug is the member's key, which is also the card's #member-<key> anchor.
    Empty on any error."""
    idx: dict = {}
    try:
        members = json.loads((ROOT / "data" / "team.json").read_text(encoding="utf-8"))["members"]
    except Exception:
        return idx
    for m in members:
        nm = (m.get("name") or "").strip()
        if nm:
            idx[nm.lower()] = {"slug": m.get("key") or _member_slug(nm),
                               "handle": ((m.get("front") or {}).get("handle") or None)}
    return idx

def _byline(meta: dict, sep: str = " · ", link_handle: bool = True) -> str:
    # link_handle=False when the byline sits INSIDE a card <a> (nested <a> is
    # invalid HTML and the browser splits the card apart) - render the author +
    # @handle as text there, and only deep-link on the standalone article page.
    author = (meta.get("author", "") or "").strip()
    member = _team_index().get(author.lower())  # None for guest authors
    # Author name → their Masthead card (deep-linked) when they're on the
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
        '<button class="eephus-nav-ctrl" type="button" data-qk-open aria-label="Quick search (Ctrl+K)" title="Search players, terms, metrics (Ctrl+K)">'
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
    image = image or default_share_image()
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
{FONT_PRELOAD}
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
# Players whose served grade is the provisional map's production read (the
# xfv grade_basis provisional_capped or xfv_ungraded), filled by
# _load_xfv_grades. PROSPX calls that number the production grade (QHOC04).
_EFV_PROD_KEYS: set = set()


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
            if rec.get("xfv_ungraded") or rec.get("grade_basis") == "provisional_capped":
                _EFV_PROD_KEYS.add(key)
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

# LOGO SIZE (QHOP01, 2026-10-07). Every editorial logo was the 500 x 500
# master PNG (9 to 46 KB) drawn at 15 to 24 px: / pulled 746 KB of them and
# /news/ 1.1 MB. They now come through ESPN's resizing combiner at twice the
# drawn size, the rule eephus-hub.js set for the module pages (QCLP05): the
# 24 px row mark at 48 px, the 15 to 17 px feed, ticker and history marks at
# the hub's own 34 px, so those share one cached URL with every hub logo.
_TEAM_LOGO_PX = {"row-logo": 48}


def _team_logo_url(slug: str, px: int) -> str:
    return f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/{slug}.png&h={px}&w={px}"


def _team_logo(org: str | None, cls: str = "row-logo") -> str:
    """Clean ESPN CDN team logo (falls back to the ORG abbreviation chip).
    `cls` lets callers reuse it at other sizes (e.g. the ticker's tk-logo)."""
    if not org:
        return ""
    o = html.escape(org)
    slug = ESPN_SLUGS.get(org, org.lower())
    src = html.escape(_team_logo_url(slug, _TEAM_LOGO_PX.get(cls) or _club_logo_px()))
    return (f'<img class="{cls}" src="{src}" alt="{o}" loading="lazy" '
            f"onerror=\"this.outerHTML='<span class=&quot;{cls}&quot; style=&quot;font:700 9px var(--font-retro-mono);display:inline-flex;align-items:center;justify-content:center&quot;>{o}</span>'\">")


# ---- club links (owner ask 9): the server mirror of EEPHUS_HUB.clubHref ----
# ONE table: the rows are read from assets/eephus-hub.js (_CLUB_ROWS and
# _CLUB_OLD_NAMES), so the two sides cannot drift. Exact keys only: the 30
# codes, the aliases (AZ CWS KC SD SF TB WSH OAK FLA), exact full and former
# names, and MLBAM ids through trades.canonical_org_from_id. Never
# trades.canonical_org (it passes any short uppercase string, so "TEX" the
# Texas League survives, and token-searches prose) and never
# _org_from_team_name (a nickname suffix matcher).
_CLUB_ROW_RE = re.compile(r'\["([A-Z]{3})", "([a-z]+)", "([^"]+)", (\d+)((?:, "[A-Z]+")*)\]')
_CLUB_OLD_RE = re.compile(r'"([a-z. ]+)": "([A-Z]{3})"')
_CLUB_LOGO_PX_RE = re.compile(r"var LOGO_PX = (\d+);")


@functools.lru_cache(maxsize=1)
def _club_logo_px() -> int:
    """The hub's default logo size (eephus-hub.js LOGO_PX)."""
    js = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
    return int(_CLUB_LOGO_PX_RE.search(js).group(1))


@functools.lru_cache(maxsize=1)
def _club_table() -> dict:
    js = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
    rows_block = js[js.index("var _CLUB_ROWS"):js.index("var _CLUB_OLD_NAMES")]
    old_block = js[js.index("var _CLUB_OLD_NAMES"):js.index("};", js.index("var _CLUB_OLD_NAMES"))]
    # The hub's _logoSrc at its default size (LOGO_PX), so a logo matches byte for byte.
    px = int(_CLUB_LOGO_PX_RE.search(js).group(1))
    rows = []
    for code, slug, name, mlbam, al in _CLUB_ROW_RE.findall(rows_block):
        rows.append({"code": code, "slug": slug, "name": name, "id": int(mlbam),
                     "aliases": re.findall(r'"([A-Z]+)"', al),
                     "logo": f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/{slug}.png&h={px}&w={px}"})
    if len(rows) != 30:
        raise RuntimeError(f"eephus-hub.js _CLUB_ROWS parsed to {len(rows)} rows, not 30")
    by_code = {}
    for r in rows:
        by_code[r["code"]] = r
        for a in r["aliases"]:
            by_code[a] = r
    by_name = {r["name"].lower(): r for r in rows}
    for n, c in _CLUB_OLD_RE.findall(old_block):
        by_name[n] = by_code[c]
    return {"rows": rows, "by_code": by_code, "by_name": by_name,
            "codes": frozenset(r["code"] for r in rows)}


def _club_code(x) -> str | None:
    """The canonical club code for a club mention, or None (never a guess)."""
    if x is None or isinstance(x, bool):
        return None
    t = _club_table()
    if isinstance(x, float):
        if x != x or not x.is_integer():
            return None
        x = int(x)
    if isinstance(x, int):
        s = str(x)
    else:
        s = str(x).strip()
    if not s:
        return None
    if s.isascii() and s.isdigit():
        import trades
        got = trades.canonical_org_from_id(int(s))
        return got if got in t["codes"] else None
    r = t["by_code"].get(s.upper()) or t["by_name"].get(s.lower())
    return r["code"] if r else None


def _club_href(x, ctx: str = "franchise") -> str:
    """'' when x is not one of the 30 clubs; ctx 'farm' -> the PROSPX farm page."""
    code = _club_code(x)
    if not code:
        return ""
    return ("/prospx/#farm-org=" if ctx == "farm" else "/franchise/#team=") + code


def _esc_hub(s) -> str:
    """EEPHUS_HUB.esc, byte for byte (& < > and the double quote)."""
    return (str("" if s is None else s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _club_link(x, text: str = "code", logo: bool = False, ctx: str = "franchise", stop: bool = False) -> str:
    """The server twin of EEPHUS_HUB.clubLinkHTML: the same markup for the same input."""
    code = _club_code(x)
    t = "code" if text is None else str(text)
    if not code:
        raw = ("" if x is None else str(x)) if t in ("code", "name") else t
        return f'<span data-club-nolink="unresolved">{_esc_hub(raw)}</span>' if raw else ""
    r = _club_table()["by_code"][code]
    label = code if t == "code" else r["name"] if t == "name" else t
    if not label and not logo:
        label = code
    farm = ctx == "farm"
    title = r["name"] + (": farm system" if farm else ": franchise overview")
    logo_only = bool(logo) and not label
    img = ""
    if logo:
        onerr = f"this.outerHTML='<span>{code}</span>'" if logo_only else "this.remove()"
        img = (f'<img class="club-link-logo" src="{_esc_hub(r["logo"])}" alt="{_esc_hub(r["name"]) if logo_only else ""}" '
               f'loading="lazy" onerror="{onerr}">')
    return (f'<a class="club-link{" club-link--logo-only" if logo_only else ""}" '
            f'href="{_club_href(code, "farm" if farm else "franchise")}" data-club="{code}" title="{_esc_hub(title)}"'
            + (' onclick="event.stopPropagation()"' if stop else "") + ">"
            + img + (f"<span>{_esc_hub(label)}</span>" if label else "") + "</a>")

# Round HALF-UP (ties toward +infinity) - the JS `Math.round` convention.
# THE ONE ROUNDER for every eFV number this file prints or steps. Python's
# built-in round() is banker's (half-to-EVEN): round(64.5)==64 while
# Math.round(64.5)==65, so any x.5 eFV grade made the homepage disagree with
# the PROSPX board / player card / projections, which all round in JS. It is
# correct for signed values too (grade DELTAS): floor(-1.5+0.5) == -1, exactly
# what Math.round(-1.5) returns, where round(-1.5) would give -2.
# Consensus FV is NOT this: it rounds CEIL (see _fv_label's fallback branch).
from scores_core import round_half_up as _round_half_up  # noqa: E402

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


def _sr(text: str) -> str:
    """Words a screen reader hears and the page does not show (QHOA13): the
    unit in front of a bare number. Absolutely positioned, so it takes no
    flex or grid slot."""
    return f'<span class="visually-hidden">{html.escape(text)} </span>'


def _fv_pill(p: dict) -> str:
    """The grade pill on editorial rows. Two eFV states are labelled, as on the
    PROSPX card: a grade on the eFV floor reads "floor" (QHOC07), and a player no
    source has graded wears a dashed pill whose title names the number, the
    production grade where the provisional map produced it (QHOC04)."""
    label = _fv_label(p)
    key = p.get("player_key")
    if _EFV_GRADES.get(key) is None:
        return f'{_sr("FV")}<span class="{_fv_tier_class(label)}">{html.escape(label)}</span>'
    m = re.match(r"-?\d+", label.strip())
    if m and int(m.group()) <= _EFV_FLOOR:
        return (f'{_sr("eFV")}<span class="fv-pill fv-floor" '
                'title="eFV floor: no projection">floor</span>')
    if p.get("source_graded") is False:
        if key in _EFV_PROD_KEYS:
            word = "production grade"
            tip = (f"Production grade {label}: today's map value from his translated MiLB "
                   "stats. No source has graded him, so he has no board rank.")
        else:
            word = "eFV"
            tip = f"eFV {label}: no source has graded him yet, so he has no board rank."
        return (f'{_sr(word)}<span class="{_fv_tier_class(label)} fv-prod" '
                f'title="{html.escape(tip)}">{html.escape(label)}</span>')
    return f'{_sr("eFV")}<span class="{_fv_tier_class(label)}">{html.escape(label)}</span>'

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
            f'{_sr("rank") if rank else ""}{rank_html}{_team_logo(p.get("org"))}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(_pos_label(p.get("position")))}</span>'
            f'{spark_html}{_fv_pill(p)}{_sr("change")}'
            f'<span class="row-delta {"up" if up else "down"}">{"▲" if up else "▼"} {"+" if up else ""}{d}</span></a>')

def _row_top(p: dict, rank: int) -> str:
    return (f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'{_sr("rank")}<span class="row-rank">{rank}</span>{_team_logo(p.get("org"))}'
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
            f'{_sr("rank") if rank else ""}{rank_html}{date_html}{_team_logo(g.get("org"))}'
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
            f'{_sr("rank") if rank else ""}{rank_html}{logos}'
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
            f'{_sr("rank")}<span class="row-rank">{rank}</span>{_team_logo(o.get("org"))}'
            f'<span class="row-name">{html.escape(name)}</span>'
            f'<span class="row-meta">{o.get("count", "")} prospects</span>'
            f'{_sr("farm grade")}<span class="fv-pill{gcls}">{html.escape(str(grade))}</span></a>')

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

# FA option rows are inferred from a Spotrac status diff, never confirmed by a
# transaction feed (HOME_1, 2026-10-02), so their wire rows name that basis.
_WIRE_VAL_OPT_DECLINED = "opt-out → FA"
_WIRE_VAL_OPT_EXERCISED = "option exercised"

def _wire_row_title(dt: str, key, val: str) -> str:
    """The title attribute a wire row carries, or "" for none: the two FA
    option rows say what they rest on and the day the pipeline first saw it."""
    if str(key or "").startswith("fa:") and val in (_WIRE_VAL_OPT_DECLINED, _WIRE_VAL_OPT_EXERCISED):
        return f"Spotrac status change, first seen {dt}"
    return ""

def _load_fa_events_for_wire() -> list:
    """Recent winter events from the FA module's own export (the events
    block in data/fa_class.json). Additive: an absent or pre-events export
    just yields no items. Dates are the pipeline's first-seen stamps."""
    return _cached_data_json("fa_class.json").get("events") or []

@functools.lru_cache(maxsize=None)
def _fa_member_teams() -> dict:
    """FA class member key -> the club the member comes from (the members
    block of data/fa_class.json, field "from"), read once per build."""
    return {m["key"]: m.get("from") for m in (_cached_data_json("fa_class.json").get("members") or [])
            if isinstance(m, dict) and m.get("key")}

def _fa_member_team(key) -> str | None:
    """The club of FA class member `key`, or None."""
    return _fa_member_teams().get(key) or None if key else None

def _collect_events(players: list, graduates: list, fa_events: list | None = None) -> list:
    # Each event is (date, typ, glyph, ticker_text, key, org, name, val);
    # `typ` is a type code of the MLB News registry (_WIRE_TYPES):
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
            add(il.get("since"), "il_place", "✚", f'{nm} to {il_label}', key, org,
                name=nm, val=il_label, weight=70)
    _save_wire_fv_ledger(fv_ledger, {p.get("player_key") for p in players})
    for g in graduates:
        add(g.get("debut_date"), "debut", "★", f'{g.get("player_name", "")} debuted · {g.get("org", "")}',
            g.get("player_key"), g.get("org"),
            name=g.get("player_name") or "", val="debut", weight=100)
    # Free-agency winter events (signings / option resolutions / QOs) from
    # the FA module's export. "fa:"-prefixed keys route to /fa/, never to a
    # PROSPX player page; the signing org carries the logo. An option or QO
    # event carries no club of its own (its payload has no "from"), so it takes
    # the club its fa_class member row lists (_fa_member_team).
    for e in (fa_events or []):
        nm = e.get("name") or ""
        club = e.get("from") or _fa_member_team(e.get("key"))
        key = f'fa:{e.get("key", "")}'
        t = e.get("type")
        if t == "signing":
            milb = bool(e.get("milb"))
            terms = ("MiLB deal" if milb
                     else f'{e.get("years", "?")}y/${(e.get("guar") or 0) / 1e6:.0f}M')
            add(e.get("date"), "minor_deal" if milb else "fa_sign", "✎", f'{nm} signs · {e.get("to", "?")} {terms}',
                key, e.get("to"), name=nm, val=terms, weight=95)
        elif t == "option_declined":
            add(e.get("date"), "opt_declined", "✎", f'{nm} declines option - enters FA class',
                key, club, name=nm, val=_WIRE_VAL_OPT_DECLINED, weight=85)
        elif t == "option_exercised":
            add(e.get("date"), "opt_exercised", "✎", f'{nm} option exercised - off the FA board',
                key, club, name=nm, val=_WIRE_VAL_OPT_EXERCISED, weight=85)
        elif t == "qo_offered":
            add(e.get("date"), "qo", "✎", f'{nm} receives qualifying offer',
                key, club, name=nm, val="QO offered", weight=84)
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
            add(d8, "grade_up" if up else "grade_down", "▲" if up else "▼",
                f'{nm} {"▲" if up else "▼"} {val}', key, org,
                name=nm, val=val, weight=weight)
    ev.sort(key=lambda e: (e[0], e[8]), reverse=True)
    return [e[:8] for e in ev]

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

def _wire_val_html(typ, glyph, val) -> str:
    """The row's value in its family colour. A registry type's pictogram leads
    the row (_wire_lead); a type outside the registry keeps its text glyph
    here."""
    g = "" if typ in _WIRE_TYPES else _wire_glyph(typ, glyph)
    return f'<span class="feed-val">{g}{html.escape(val)}</span>'

def _feed_item_html(typ, glyph, text, key, org, name, val, cat: str = "",
                    title: str = "") -> str:
    """One wire row (LANE_HOME 2.3): pictogram in the family colour | hidden
    family prefix | logo | name in ink (ellipsized) | value in the family
    colour. data-fam and data-type carry the family and the type code for the
    stylesheet and the filters. `cat` (optional) adds a data-cat tag; `title`
    (optional) is the row's basis tooltip. Shared by the homepage feed + the
    /news/ page."""
    logo = _team_logo(org, "feed-logo") if org else ""
    data_cat = f' data-cat="{html.escape(cat)}"' if cat else ""
    tip = f' title="{html.escape(title)}"' if title else ""
    return (f'<a class="feed-item" href="{_player_href(key)}"{_wire_attrs(typ)}{data_cat}{tip}>'
            f'{_wire_lead(typ)}{logo}<span class="feed-name">{html.escape(name or text)}</span>'
            f'{_wire_val_html(typ, glyph, val)}</a>')

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

def _news_item_html(typ, glyph, text, key, org, name, val, cat, pmap, title: str = "") -> str:
    """Richer /news/ row: pictogram | hidden family prefix | logo | name +
    scouting line | current-FV chip | value. Reuses _feed_item_html's classes so it inherits the wire palette; the
    detail line + FV pill are scoped to .news-feed in CSS, so the homepage
    sidebar wire is untouched. `pmap` maps player_key -> record (players +
    graduates); rows with no match (FA signings) degrade to the plain layout."""
    logo = _team_logo(org, "feed-logo") if org else ""
    data_cat = f' data-cat="{html.escape(cat)}"' if cat else ""
    p = pmap.get(key) if pmap else None
    detail = _news_detail(p, typ)
    meta = f'<span class="news-meta">{detail}</span>' if detail else ""
    fv = _fv_pill(p) if (p and p.get("fv_close") is not None) else ""
    tip = f' title="{html.escape(title)}"' if title else ""
    return (f'<a class="feed-item news-item" href="{_player_href(key)}"{_wire_attrs(typ)}{data_cat}{tip}>'
            f'{_wire_lead(typ)}{logo}'
            f'<span class="news-main"><span class="feed-name">{html.escape(name or text)}</span>{meta}</span>'
            f'{fv}'
            f'{_wire_val_html(typ, glyph, val)}</a>')

def _feed_html(events: list, n: int = 12) -> str:
    # Day-grouped wire (homepage sidebar): a thin per-date header carries the
    # timestamp + Time Machine link; rows are structured logo|name|value chip.
    out = []
    last_day = None
    for dt, typ, glyph, text, key, org, name, val in events[:n]:
        if dt != last_day:
            last_day = dt
            out.append(_feed_day_header(dt))
        out.append(_feed_item_html(typ, glyph, text, key, org, name, val,
                                   title=_wire_row_title(dt, key, val)))
    return "".join(out)

def _ticker_html(events: list, n: int = 14) -> str:
    # Each item is a mouse-clickable link to the player (or spotlights) in the
    # row markup of every news surface (LANE_HOME 2.3): the pictogram and the
    # value in the family colour, the name in the panel ink. A type outside the
    # registry keeps its one-string text in the ink. tabindex=-1 keeps it out of
    # the keyboard/AT path - the ticker is aria-hidden decoration; the sidebar
    # MLB News feed is the accessible, keyboard-navigable equivalent.
    items = []
    for dt, typ, glyph, text, key, org, name, val in events[:n]:
        href = _player_href(key) if key else "/prospx/#tab=spotlights"
        logo = _team_logo(org, "tk-logo") if org else ""
        title = _wire_row_title(dt, key, val)
        tip = f' title="{html.escape(title)}"' if title else ""
        if typ in _WIRE_TYPES and name:
            body = (f'{_wire_lead(typ)}{logo}<span class="tk-name">{html.escape(name)}</span> '
                    f'<span class="feed-val">{html.escape(val)}</span>')
        else:
            body = f'{logo}<span class="glyph">{_wire_glyph(typ, glyph)}</span> {html.escape(text)}'
        items.append(f'<a href="{html.escape(href)}" tabindex="-1"{_wire_attrs(typ)}{tip}>{body}</a>')
    if not items:
        items = [f'<span><span class="glyph">◆</span> {NEWS_LABEL} · live</span>']
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
    recent activity; each row's data-fam and data-type let the filter chips
    show/hide by family (and the Grades chip by type). Each day is wrapped in a .news-day block so a filtered-empty
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
        out.append(_news_item_html(typ, glyph, text, key, org, name, val, "", pmap,
                                   title=_wire_row_title(dt, key, val)))
    if open_day:
        out.append("</div>")
    return "".join(out)

# Tiny dependency-free filter for the /news/ chips (the family key, HOME_2):
# "all", a family (rows whose data-fam matches) or "grades" (owner decision
# M20-4: the grade_up and grade_down rows). Hides any day block left with no
# visible items and announces the visible count in the polite status line
# (the QHOA08 pattern; mirrors the glossary/FA static-page chip idiom).
_NEWS_FILTER_JS = """<script>
(function(){
  var bar=document.getElementById('news-filter-bar'),feed=document.getElementById('news-feed');
  if(!bar||!feed)return;
  var empty=null;
  function match(it,f){
    if(f==='all')return true;
    if(f==='grades'){var t=it.getAttribute('data-type');return t==='grade_up'||t==='grade_down';}
    return it.getAttribute('data-fam')===f;
  }
  bar.addEventListener('click',function(e){
    var b=e.target.closest('[data-news-filter]');if(!b)return;
    var f=b.getAttribute('data-news-filter');
    bar.querySelectorAll('[data-news-filter]').forEach(function(x){x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',x===b?'true':'false');});
    var shown=0;
    feed.querySelectorAll('.news-day').forEach(function(day){
      var any=false;
      day.querySelectorAll('.feed-item').forEach(function(it){
        var show=match(it,f);
        it.style.display=show?'':'none';if(show){any=true;shown++;}
      });
      day.style.display=any?'':'none';
    });
    if(!empty){
      empty=document.createElement('div');
      empty.className='news-empty';
      feed.appendChild(empty);
    }
    if(shown===0){empty.textContent='No '+b.textContent.trim()+' rows in this window.';empty.style.display='';}
    else{empty.style.display='none';}
    var st=document.getElementById('news-filter-status');
    if(st)st.textContent=shown+(shown===1?' row':' rows')+' shown';
  });
})();
</script>"""

# Server-rendered "Generate GFX" chip - mirrors EEPHUS_GFX.chipHTML() (the
# engine loads deferred, so the static page ships the chip itself and the
# inline wire-up below just listens for the click).
def _gfx_chip_html(chip_id: str) -> str:
    return (f'<button class="chip egfx-chip" id="{chip_id}" type="button" '
            'title="Share graphic of this view">'
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
# TYPE, ICO and CLR read the MLB News registry (_WIRE_TYPES, HOME_2), written
# into the script by _news_gfx_js(): a type's label, its pictogram's sprite key
# and its family colour as a token pair, the page token on a light frame and
# the panel token on a dark one (the painter resolves the pair at draw time).
_NEWS_GFX_JS = """<script>
(function(){
  var el=document.getElementById('news-gfx-data'),evs=[];
  try{evs=JSON.parse(el?el.textContent:'[]')||[];}catch(e){}
  var WT=__WIRE_TYPES__,TYPE={},ICO={},CLR={};
  Object.keys(WT).forEach(function(k){
    TYPE[k]=WT[k][0];ICO[k]=WT[k][2];
    CLR[k]={light:'--wire-'+WT[k][1],dark:'--wire-'+WT[k][1]+'-panel'};
  });
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
    return {kind:'board',module:'MLB News',accentToken:'--accent-lilac',
      title:'MLB News - '+mon,
      subtitle:evs.length+' moves - debuts, trades, promos, FV',
      url:'eephus.io/news',filenameBase:'mlb-news-'+iso,format:'twitter',
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
                val:e.val||'',glyph:e.glyph||'',ico:ICO[e.typ]||'',c:CLR[e.typ]||null,
                shot:shotURL(e),logo:logoURL(e)};
      });
    var dt=new Date(day+'T12:00:00');
    var lbl=isNaN(+dt)?day:dt.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
    return {kind:'newsday',module:'MLB News',accentToken:'--accent-lilac',
      title:'MLB News - '+lbl,dateLabel:lbl,
      subtitle:items.length+(items.length===1?' update':' updates')+' - every move from this date',
      url:'eephus.io/news',filenameBase:'mlb-news-'+day,items:items};
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

def _news_gfx_js() -> str:
    """_NEWS_GFX_JS with the registry written in: code -> [type label, family,
    sprite key]."""
    wt = {code: [row["val"][:1].upper() + row["val"][1:], row["fam"], _WIRE_ICON[code]]
          for code, row in _WIRE_TYPES.items()}
    return _NEWS_GFX_JS.replace("__WIRE_TYPES__", json.dumps(wt, separators=(",", ":")))

def build_news(data: dict | None = None) -> str:
    """/news/ - the expanded MLB News page: the full recent event feed
    (debuts, trades, promotions/demotions, IL, FV grade changes, FA signings
    and option decisions),
    day-grouped with category filter chips. Same event pipeline + row markup as
    the homepage sidebar feed, just a wider window. Reached by clicking the
    MLB News header (sidebar feed or top ticker) on the homepage. The name is
    NEWS_LABEL; the URL stays /news/."""
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
    # The family key as the filter bar: All, the five families (each with its
    # mark), and Grades (owner decision M20-4, DECISIONS_FOR_OWNER.md:515).
    chips = _wire_key_html("data-news-filter",
                           lead=(("all", "All"),), tail=(("grades", "Grades"),))
    body = (
        '<div class="news-app">'
        f'<div class="section-head"><h1>{_masthead_icon("news")}{NEWS_LABEL}</h1>'
        '<span class="section-sub">debuts, trades, level moves, IL, eFV changes, FA signings and options</span>'
        f'{_gfx_chip_html("news-gfx-chip")}</div>'
        f'<p class="news-intro">The {_gl("wire_ticker", "wire")}, last 30 days, newest first.</p>'
        '<details class="news-how"><summary>How this works</summary><ul>'
        '<li>Grade rows are eFV moves of 2 or more.</li>'
        '<li>&quot;to eFV floor&quot; and &quot;off eFV floor&quot; mark a player reaching or leaving '
        'the model floor, not a re-grade.</li>'
        '<li>A dashed grade is a player no source has graded yet; &quot;floor&quot; is the eFV floor.</li>'
        '</ul></details>'
        '<div class="filter-bar" id="news-filter-bar" role="group" aria-labelledby="news-filter-label">'
        f'<span class="filter-label" id="news-filter-label">Filter</span>{chips}</div>'
        '<div class="visually-hidden" id="news-filter-status" role="status" aria-live="polite"></div>'
        f'<div class="sb-feed news-feed" id="news-feed">{feed}</div>'
        '</div>'
        # Page-scoped sizing for the per-date GFX chips (site.css owns the base
        # .chip/.egfx-chip look; this only shrinks them into the thin day rows).
        '<style>.news-feed .feed-day{gap:10px;}'
        '.news-app .news-feed button.chip.egfx-day-chip{margin-left:auto;font-size:10px;'
        'padding:2px 8px;line-height:1.5;}</style>'
        + _news_gfx_blob(recent, pmap)
        + _NEWS_FILTER_JS
        + _news_gfx_js()
        # Shared Generate GFX engine (same two-script injection as /fa/).
        + f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        + f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
    )
    # Claims rule C9: this names what the feed carries today. The words "MLB
    # transactions" join it in the commit that serves MLB rows (Q9_22c).
    return page(f"{NEWS_LABEL} - eephus.io", "news", body,
                f"{NEWS_LABEL} on eephus.io: prospect level moves, MLB debuts, trades, IL "
                "moves, eFV grade changes, free-agency signings and option decisions, "
                "filterable by type.",
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
    # The direction tokens become a class, so the stylesheet paints the line
    # (.px-spark.up / .dn); any other colour keeps an explicit fill.
    cls = _SPARK_DIR.get(color.replace(" ", ""))
    fill = "" if cls else f' fill="{color}"'
    return (f'<svg class="px-spark{" " + cls if cls else ""}" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<path class="gl" d="{"".join(rules)}"/>'
            f'<path class="ln"{fill} d="{"".join(ink)}"/></svg>')


_SPARK_DIR = {"var(--accent-green)": "up", "var(--up)": "up",
              "var(--accent-red)": "dn", "var(--down)": "dn"}

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
            # spotlights.py tags every hot-bucket entry "Breakout"; the word is
            # only true of a player whose breakout_flag is set (QHOC05).
            if why == "Breakout" and not p.get("breakout_flag"):
                why = "Hot sample"
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
{FONT_PRELOAD}
<link rel="stylesheet" href="/assets/site.css?v={_CSS_VER}">
<script src="/assets/eephus-nav.js?v={_NAV_VER}" defer></script>
<script src="/assets/eephus-tiers.js?v={_TIERS_VER}" defer></script>
<script src="/assets/eephus-state.js?v={_STATE_VER}" defer></script>
{ACCOUNT_CSS_LINK}
</head>
<body class="eephus-page eephus-home">
<a class="skip-link" href="#main">Skip to content</a>
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
            f'{sign}{wag_r:.1f} WAG{_sr(", WAR Above Grade")}</span>')


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
        f'<a class="otd-row" href="{_player_href(g.get("player_key"))}"{_wire_attrs("debut")}{cat}>'
        f'{_wire_lead("debut")}'
        f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
        f'<span class="otd-body" title="{nm} debuted{pos_tail}">{logo} <strong>{nm}</strong> '
        f'<span class="wire-val">debuted</span>{pos_tail}</span>'
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
        f'<a class="otd-row otd-trade" href="{_player_href(p.get("player_key"))}"{_wire_attrs("trade")}{cat}>'
        f'{_wire_lead("trade")}'
        f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
        f'<span class="otd-body" title="→ {nm}{pos_tail} traded">{logos} <strong>{nm}</strong>{pos_tail} '
        f'<span class="wire-val">traded</span></span>'
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
        f'<div class="kicker"><h2>{PAGE_LABELS["/history/"]}</h2>'
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


def _hist_tx_type(code: str, p: dict | None, minor: bool) -> str:
    """The MLB News type code (_WIRE_TYPES) of one prospects.db ledger row: TR
    a trade; SFA a free-agent deal, minor_deal when its description names a
    minor league contract; DFA ("declared free agency") fa_elect; SGN the
    player's own signing, intl_sign for a player the board acquired as an
    international free agent and draft_sign otherwise; an SGN of a player off
    the board is minor_deal, the rule mlb_events.py applies to an SGN of a
    player in no draft file."""
    if code == "TR":
        return "trade"
    if code == "SFA":
        return "minor_deal" if minor else "fa_sign"
    if code == "DFA":
        return "fa_elect"
    if not p:
        return "minor_deal"
    method = (p.get("acquisition") or {}).get("method")
    return "intl_sign" if method == "international_fa" else "draft_sign"

# One-pass, once-per-build cache of the prospects.db history ledgers grouped
# by calendar date. ~175k dated transaction events across 7,471 payloads
# group in ~0.3s; il_history is tiny. Module-level so a rebuild that calls
# build_this_day() more than once (tests) never re-reads the DB.
_HIST_DB_CACHE: tuple[dict, dict] | None = None

def _load_history_db() -> tuple[dict, dict]:
    """Group prospects.db player_transactions (SGN/TR/DFA/SFA only) and
    il_history by MM-DD. STRICTLY read-only (file:...?mode=ro) - the build
    must never write the pipeline's DB. Returns
    ({mmdd: [(iso_date, code, player_key, team_name, minor), ...]},
     {mmdd: [(iso_since, player_key, il_type), ...]}); empty dicts when the
    DB is absent (cold checkouts / CI without a seeded DB). `minor` is True
    for a row whose StatsAPI description names a minor league contract."""
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
                        minor = "minor league contract" in str(t.get("description") or "").lower()
                        tx.setdefault(dt[5:10], []).append((dt[:10], code, key, team, minor))
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

# /history/ family filter - same tiny dependency-free idiom as the /news/
# chips (_NEWS_FILTER_JS): toggle .otd-row visibility by data-fam, hide any
# section left with no visible rows, announce the visible count.
_HIST_FILTER_JS = """<script>
(function(){
  var bar=document.getElementById('hist-filter-bar'),wrap=document.getElementById('hist-sections');
  if(!bar||!wrap)return;
  var empty=null;
  bar.addEventListener('click',function(e){
    var b=e.target.closest('[data-hist-filter]');if(!b)return;
    var f=b.getAttribute('data-hist-filter');
    bar.querySelectorAll('[data-hist-filter]').forEach(function(x){x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',x===b?'true':'false');});
    var shown=0;
    wrap.querySelectorAll('.hist-section').forEach(function(sec){
      var any=false;
      sec.querySelectorAll('.otd-row').forEach(function(it){
        var show=(f==='all')||it.getAttribute('data-fam')===f;
        it.style.display=show?'':'none';if(show){any=true;shown++;}
      });
      sec.style.display=any?'':'none';
    });
    if(!empty){
      empty=document.createElement('div');
      empty.className='news-empty';
      wrap.appendChild(empty);
    }
    if(shown===0){empty.textContent='No '+b.textContent.trim()+' rows on this date.';empty.style.display='';}
    else{empty.style.display='none';}
    var st=document.getElementById('hist-filter-status');
    if(st)st.textContent=shown+(shown===1?' row':' rows')+' shown';
  });
})();
</script>"""

def _hist_spans(tx_all: dict, il_all: dict) -> str:
    """' Transactions from 2010, IL placements from 2017.' off the ledgers
    themselves (QHOC06: the copy said 2019 over rows from 2015)."""
    tx = min((t[0][:4] for rows in tx_all.values() for t in rows), default=None)
    il = min((t[0][:4] for rows in il_all.values() for t in rows), default=None)
    parts = ([f"Transactions from {tx}"] if tx else []) + ([f"IL placements from {il}"] if il else [])
    return (" " + ", ".join(parts) + ".") if parts else ""


def _wag_gate_clause() -> str:
    """' once the player is past 200 PA or 80 IP', read from the WAG model's own
    meaningful_exposure (value_framework_config.yaml), the gate _wag_badge honours."""
    try:
        y = (ROOT / "value_framework_config.yaml").read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"meaningful_exposure:\s*\{hitter_pa:\s*(\d+),\s*pitcher_ip:\s*(\d+)\}", y)
    return f" once the player is past {m.group(1)} PA or {m.group(2)} IP" if m else ""


def build_this_day(data: dict | None = None) -> str:
    """/history/ - Today in Prospect History as a full page: every debut
    anniversary and prospect trade landing on today's exact calendar date
    (past seasons only), plus the prospects.db transaction ledger (signings /
    free agency) and IL placements for the same MM-DD; the intro prints the
    first year each ledger holds, read from prospects.db at build time.

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
    debut_rows = [_otd_debut_row(g, d) for _, d, g in debut_cands]

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
    trade_rows = [_otd_trade_row(p, tr, d) for _, d, p, tr in trade_cands]

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
    for dt, code, key, team, *rest in tx_today[:TX_CAP]:
        p = pmap.get(key)
        nm = html.escape((p or {}).get("player_name") or _name_from_key(key))
        pos = _pos_label((p or {}).get("position"))
        d = date.fromisoformat(dt)
        verb = _HIST_TX_VERBS.get(code, "moved")
        logo = _team_logo(_org_from_team_name(team), "otd-logo")
        wt = _hist_tx_type(code, p, bool(rest and rest[0]))
        pos_tail = (" · " + html.escape(pos)) if pos else ""
        inner = (f'{_wire_lead(wt)}<span class="otd-when">{html.escape(_otd_date(d))}</span>'
                 f'<span class="otd-body" title="{nm} {verb}{pos_tail}">{logo} <strong>{nm}</strong> '
                 f'<span class="wire-val">{verb}</span>{pos_tail}</span>')
        if p:
            tx_rows.append(f'<a class="otd-row" href="{_player_href(key)}"{_wire_attrs(wt)}>{inner}{_fv_pill(p)}</a>')
        else:
            tx_rows.append(f'<div class="otd-row"{_wire_attrs(wt)}>{inner}</div>')
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
        inner = (f'{_wire_lead("il_place")}<span class="otd-when">{html.escape(_otd_date(d))}</span>'
                 f'<span class="otd-body" title="{nm} placed on the {html.escape(label)}{pos_tail}">'
                 f'<strong>{nm}</strong> <span class="wire-val">placed on the {html.escape(label)}</span>'
                 f'{pos_tail}</span>')
        if p:
            il_rows.append(f'<a class="otd-row" href="{_player_href(key)}"{_wire_attrs("il_place")}>{inner}{_fv_pill(p)}</a>')
        else:
            il_rows.append(f'<div class="otd-row"{_wire_attrs("il_place")}>{inner}</div>')

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

    # The family key as the filter bar (HOME_2): All and the five families.
    chips = _wire_key_html("data-hist-filter", lead=(("all", "All"),))

    body = (
        '<div class="news-app hist-app">'
        f'<div class="section-head"><h1>{_masthead_icon("history")}Today in Prospect History - {html.escape(mon_d)}</h1>'
        '<span class="section-sub">debut anniversaries, trades, signings &amp; IL moves on this calendar date</span></div>'
        '<p class="news-intro">Past seasons on this exact date.</p>'
        '<details class="news-how"><summary>How this works</summary><ul>'
        f'<li>{_hist_spans(tx_all, il_all).strip() or "Ledgers read from prospects.db."}</li>'
        f'<li>Debut rows carry {_gl("wag", "WAG")}{_wag_gate_clause()}.</li>'
        '<li>No eFV-move section: grade history is stamped at model re-run dates, '
        'not the day a grade changed.</li></ul></details>'
        '<div class="filter-bar" id="hist-filter-bar" role="group" aria-labelledby="hist-filter-label">'
        f'<span class="filter-label" id="hist-filter-label">Filter</span>{chips}</div>'
        '<div class="visually-hidden" id="hist-filter-status" role="status" aria-live="polite"></div>'
        f'<div id="hist-sections" style="max-width:760px;">{sections}</div>'
        '</div>'
        + _HIST_FILTER_JS
    )
    return page("Today in Prospect History - eephus.io", "", body,
                "Prospect history for this calendar date: MLB debut anniversaries, prospect trades, "
                "signings and IL moves from past seasons.",
                url=f"{SITE_ORIGIN}/history/")

def _postseason_live(today: date) -> bool:
    """True while data/bracket_sim.json says this year's postseason is on: the
    file is this season's, its serve block is on, it was built inside the 14
    days before today, and the World Series is not decided. No file, an older season, a
    stale file or a decided World Series all read False, so the callout never
    says "Underway" off a guess."""
    bs = _cached_data_json("bracket_sim.json")
    if not bs:
        return False
    try:
        if int(bs.get("season") or 0) != today.year:
            return False
        built = date.fromisoformat(str(bs.get("as_of") or "")[:10])
    except (TypeError, ValueError):
        return False
    if not (bs.get("serve") or {}).get("on") or not 0 <= (today - built).days <= 14:
        return False
    series = bs.get("series") or []
    ws = [s for s in series if s.get("round") == "W"]
    return bool(series) and not (ws and all(s.get("decided") for s in ws))


def _date_callout(band: str, today: date | None = None) -> str:
    """The band's date-aware callout (HOME_4, LANE_HOME 3.2 row 11): MLB events
    in the MLB band, prospect events in the Prospects band, one callout per band.

    Events carry a (start, end) range rather than a single date - the MLB
    Draft runs three days (Jul 11-13), not one, so "days until" has to count
    down to the START, and the callout needs an in-progress state for the
    days the event is actually happening, not just before/after.

    DATES. Read from data where a data source exists: the postseason is live
    while data/bracket_sim.json says so (_postseason_live). Every other range
    is a RECURRING window, not a scraped date: the trade deadline has sat on
    Jul 31 since 2019, the Rule 5 draft closes the Winter Meetings (a moving
    day inside the second week of December, hence a window rather than a
    false-precision single date), the Futures Game is All-Star Saturday, and
    FanGraphs' offseason org lists run through the late fall. Anything softer
    than that does not belong here, which is why the option and qualifying
    offer window, the free-agent market and the arbitration exchange have no
    callout: no served file carries their dates.

    ORDER MATTERS: the loop returns the FIRST event (by start date) that is
    live or inside the 45-day horizon, so windows are kept short deliberately.
    A months-long "list season" range would sit "Underway" across December and
    January and swallow both the Rule 5 draft and the international window.
    """
    today = today or date.today()
    yr = today.year
    if band == "mlb":
        if _postseason_live(today):
            return ('<a class="home-callout" href="/scores/">'
                    '<span class="cal-tag">◆ Live</span>'
                    '<span class="cal-msg"><strong>Postseason</strong> · Underway</span>'
                    '<span class="cal-go">View →</span></a>')
        events = [
            (date(yr, 7, 31), date(yr, 7, 31), "MLB trade deadline", "/prospx/#tab=traded"),
        ]
    else:
        ifa = date(yr if today <= date(yr, 1, 15) else yr + 1, 1, 15)
        events = [
            # All-Star Saturday. Listed BEFORE the Draft so that on a shared start
            # date the one-day event wins the (stable-sorted) tie and the Draft
            # takes the slot back for the rest of its run.
            (date(yr, 7, 11), date(yr, 7, 11), "Futures Game", "/prospx/"),
            (date(yr, 7, 11), date(yr, 7, 13), "MLB Draft", "/prospx/#tab=draft"),
            # FanGraphs list season - the offseason org-list run that re-grades the
            # consensus board. Capped at November on purpose (see ORDER MATTERS).
            (date(yr, 11, 1), date(yr, 11, 30), "FanGraphs list season", "/prospx/"),
            # Rule 5 draft - final day of the Winter Meetings; the window spans the
            # days that day has landed on rather than asserting one.
            (date(yr, 12, 8), date(yr, 12, 12), "Rule 5 draft", "/prospx/#tab=traded"),
            (ifa, ifa, "International signing period", "/prospx/#tab=ifa"),
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

def _tm_seed_key(p: dict) -> str:
    """The key a /trademachine/#tm= seed carries for one trade_values row. An MLB
    row seeds on the projections key of its human (`proj_key`, stamped only
    where the row's own slug names a different human there); a prospect row
    seeds on its player_key, which is the PROSPX key."""
    if p.get("status") in ("graduated", "debuted") and p.get("proj_key"):
        return p["proj_key"]
    return p["player_key"]


_FA_OFF_BOARD = ("signed", "option_exercised")


def _park_window_label(pf: dict, year: int) -> str:
    """'2024-2026 window' and, when the file was built inside the window's last
    season, the date its games run through (milb_park_factors.json was built
    2026-07-23, so its 2026 leg is a partial season)."""
    lab = f"{year - 2}-{year} window"
    built = str(pf.get("generated_at") or "")[:10]
    try:
        b = date.fromisoformat(built)
    except ValueError:
        return lab
    if b.year == year and b.month < 11:
        lab += f", {year} through {b.strftime('%b')} {b.day}"
    return lab


def _xmod_cards() -> dict:
    """The homepage module cards by id: (title, href, sub-head, rows). Reads
    the committed sidecars at build time; any missing file just drops its
    card. The bands place them (HOME_4): FA, Projections, Trade Machine and
    Alchemy Lab in the MLB band, MLB Stats, Defense and Leverage merged into
    the Leaders card, Fantasy and Diamond merged into the Diamond strip,
    CollegeSavant and Park Factors in the Prospects band, the model verdict
    counts in the site strip."""
    cards: dict = {}
    # MLB Free Agency - top of the current class board
    try:
        fa = _cached_data_json("fa_class.json")
        # Only players still on the FA board, the same filter as /fa/'s
        # 'remaining' list (fa.js): a signed player or an exercised option never
        # reaches this market (QHOC02). A pending option is listed but says so.
        top = sorted((m for m in fa.get("members") or []
                      if m.get("projGuar") and m.get("status") not in _FA_OFF_BOARD),
                     key=lambda m: -m["projGuar"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/fa/#player={html.escape(m["key"])}"'
            + (' title="Pending option: the projected deal applies only if he reaches the market."'
               if m.get("status") == "pending_option" else '') + '>'
            f'<span class="xmod-name">{html.escape(m["name"])}</span>'
            + (f'<span class="xmod-sub" style="white-space:normal;line-height:1.25;">'
               f'{html.escape(m.get("pos") or "")} · if he reaches the market</span>'
               if m.get("status") == "pending_option" else
               f'<span class="xmod-sub">{html.escape(m.get("pos") or "")}</span>') +
            f'<span class="xmod-val">{m.get("projYears") or "?"}y / ${(m["projGuar"] / 1e6):.0f}M</span></a>'
            for m in top)
        if rows:
            cards["fa"] = (f'{_ico("fa", 16)}Free Agency', '/fa/',
                          f'{fa.get("class_year", 2027) - 1}-{str(fa.get("class_year", 2027))[2:]} projected market leaders', rows)
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
            cards["projections"] = (f'{_ico("projections", 16)}MLB Projections', '/projections/',
                          'five-year eWAR leaders', rows)
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
            cards["trademachine"] = (f'{_ico("trademachine", 16)}Trade Machine', '/trademachine/',
                          'surplus trade value, prospects + MLB', rows)
    except (OSError, ValueError, KeyError):
        pass
    # CollegeSavant - static teaser (its data bundles stay in-module)
    cards["collegesavant"] = (f'{_ico("collegesavant", 16)}CollegeSavant', '/collegesavant/',
                  'college baseball percentiles',
                  '<a class="xmod-row" href="/collegesavant/"><span class="xmod-name">Hitter dashboard</span><span class="xmod-val">EV · xwOBA · discipline →</span></a>'
                  '<a class="xmod-row" href="/collegesavant/pitcher_index.html"><span class="xmod-name">Pitcher dashboard</span><span class="xmod-val">Stuff+ · shapes →</span></a>')
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
            cards["mlbstats"] = (f'{_ico("mlbstats", 16)}MLB Stats', '/mlbstats/#section=bullpen',
                          'top relievers by REM+', rows)
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
            cards["leverage"] = (f'{_ico("li", 16)}Leverage', '/mlbstats/#section=leverage',
                          'realized win-probability added', rows)
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
            cards["defense"] = (f'{_ico("defense", 16)}Defense', '/mlbstats/#section=defense',
                          'top qualified fielders by DEM+', rows)
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
            cards["pal"] = (f'{_ico("pal", 16)}Alchemy Lab', '/pal/',
                          'reliever-to-starter conversion screen', rows)
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
            cards["fantasy"] = (f'{_ico("fantasy", 16)}Fantasy', '/fantasy/#m=redraft&amp;section=ros_hitter',
                          'rest-of-season hitter points leaders', rows)
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
            cards["parks"] = (f'{_ico("parks", 16)}Park Factors', '/parks/',
                          f'MiLB venues that add the most offense ({_park_window_label(pf, year)})', rows)
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
                ("provisional", "Provisional", "partly measured"),
                ("unvalidated", "Unvalidated", "serving, not yet gated"),
                ("deprecated", "Deprecated", "measured, failed, retired")))
        if tally:
            # QHOC03: the head counts registry rows, every verdict listed under
            # it (provisional was missing, and some rows are datasets or
            # pre-registered tests rather than models).
            cards["models"] = (f'{_ico("models", 16)}{PAGE_LABELS["/models/"]}', '/models/',
                          f'{sum(tally.values())} registry rows by verdict',
                          rows)
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
    cards["diamond"] = (f'{_ico("diamond", 16)}Diamond', '/diamond/',
                  'the paid tier: fantasy and betting',
                  '<a class="xmod-row" href="/fantasy/"><span class="xmod-name">Fantasy</span><span class="xmod-val">redraft · dynasty · DFS →</span></a>'
                  '<a class="xmod-row" href="/betting/"><span class="xmod-name">Sports Betting</span><span class="xmod-val">model vs the book price →</span></a>'
                  f'<a class="xmod-row" href="/diamond/"><span class="xmod-name">Diamond Pass</span><span class="xmod-val">{free_line} →</span></a>')
    return cards


def _xmod_card_html(card: tuple, cls: str = "") -> str:
    """One module card: icon and title, the open link, the sub-head, the rows."""
    title, href, sub, rows = card
    return (f'<div class="xmod-card{" " + cls if cls else ""}"><div class="xmod-head"><span class="xmod-title">{title}</span>'
            f'<a class="xmod-link" href="{href}">open →</a></div>'
            f'<div class="xmod-sub-head">{html.escape(sub)}</div>{rows}</div>')


def _xmod_cards_html(ids: tuple | None = None) -> str:
    """The named module cards in order (every card when ids is None); a card
    whose file is missing is simply absent."""
    cards = _xmod_cards()
    return "".join(_xmod_card_html(cards[i]) for i in (ids or tuple(cards)) if i in cards)


def _xmod_first_row(rows: str) -> str:
    """The first xmod-row anchor of a card's rows (its leader)."""
    end = rows.find("</a>")
    return rows[:end + 4] if end >= 0 else ""


def _home_leaders_card(cards: dict) -> str:
    """The MLB band's Leaders card (HOME_4, LANE_HOME 3.2 row 21): the MLB
    Stats REM+, Defense DEM+ and Leverage WPA cards merged into one row each,
    the leader each card already printed, each row linking its own section."""
    rows = "".join(_xmod_first_row(cards[k][3]) for k in ("mlbstats", "defense", "leverage") if k in cards)
    if not rows:
        return ""
    return _xmod_card_html((f'{_ico("mlbstats", 16)}Leaders', "/mlbstats/",
                            "top reliever by REM+, fielder by DEM+, batter by WPA", rows))


def _home_diamond_strip(cards: dict) -> str:
    """One Diamond strip (HOME_4): the Fantasy card's rows beside the Diamond
    card's three links, under the Diamond card's head."""
    if "diamond" not in cards:
        return ""
    title, href, sub, rows = cards["diamond"]
    fan = ""
    if "fantasy" in cards:
        _ft, f_href, f_sub, f_rows = cards["fantasy"]
        fan = (f'<div class="xmod-part"><a class="xmod-part-head" href="{f_href}">'
               f'{_ico("fantasy", 12)}Fantasy</a>'
               f'<div class="xmod-sub-head">{html.escape(f_sub)}</div>{f_rows}</div>')
    body = f'<div class="xmod-split">{fan}<div class="xmod-part">{rows}</div></div>'
    return _xmod_card_html((title, href, sub, body), cls="xmod-strip-card")


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
# The production-grade series (source_graded False rows; glossary xfv_ungraded)
# is a neutral grey, outside the navy-to-lilac ramp, so it can never read as an
# eFV tier.
_EFV_PROD_FILL, _EFV_PROD_OP = "var(--text-tertiary)", "0.45"

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
    dropping it.

    TWO BASES, NEVER POOLED (QHOC01, 2026-10-03). A row the export marks
    source_graded False has no grade from any label source, so eFV abstains on
    it and the number it carries is the production grade (glossary
    xfv_ungraded), not an eFV. Those rows are stacked above the eFV bars as
    their own muted series with their own legend entry, and the caption and
    tooltips count each basis separately: the eFV count, median and floor read
    the source-graded rows alone. A row with no flag (a pre-flag payload)
    stays on the eFV side, as row_in_prov_section keeps it ranked."""
    grades, prod = [], []
    for p in players:
        v = _primary_fv(p)
        if isinstance(v, (int, float)):
            (prod if p.get("source_graded") is False else grades).append(_round_half_up(v))
    if not grades:
        return ""
    floor_n = sum(1 for g in grades if g <= _EFV_FLOOR)
    plotted = sorted(g for g in grades if g > _EFV_FLOOR)
    if len(plotted) < 10:            # nothing to shape a histogram out of
        return ""
    prod_floor_n = sum(1 for g in prod if g <= _EFV_FLOOR)
    prod_plotted = sorted(g for g in prod if g > _EFV_FLOOR)
    lo = min(plotted[0], prod_plotted[0]) if prod_plotted else plotted[0]
    hi = max(plotted[-1], prod_plotted[-1]) if prod_plotted else plotted[-1]
    counts: dict[int, int] = {}
    for g in plotted:
        counts[g] = counts.get(g, 0) + 1
    prod_counts: dict[int, int] = {}
    for g in prod_plotted:
        prod_counts[g] = prod_counts.get(g, 0) + 1
    n_bkt = hi - lo + 1
    top_c = max(counts.get(g, 0) + prod_counts.get(g, 0) for g in range(lo, hi + 1))
    total = len(plotted)
    prod_total = len(prod_plotted)
    median = plotted[total // 2] if total % 2 else plotted[total // 2 - 1]
    prod_median = (None if not prod_total else
                   prod_plotted[prod_total // 2] if prod_total % 2 else prod_plotted[prod_total // 2 - 1])

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
        h = 0.0
        if c:
            _, _, tier_key, _, fill, op = _efv_tier(g)
            h = max(1.0, (c / top_c) * plot_h)
            pct = 100.0 * c / total
            bars.append(
                f'<rect x="{x_of(g):.1f}" y="{base - h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                f'style="fill:{fill};fill-opacity:{op};">'
                f'<title>eFV {g} ({tier_key}) - {c} source-graded prospect{"s" if c != 1 else ""}, '
                f'{pct:.1f}% of the source-graded board</title></rect>')
        pc = prod_counts.get(g, 0)
        if pc:
            ph = max(1.0, (pc / top_c) * plot_h)
            ppct = 100.0 * pc / prod_total
            bars.append(
                f'<rect x="{x_of(g):.1f}" y="{base - h - ph:.1f}" width="{bar_w:.1f}" height="{ph:.1f}" '
                f'style="fill:{_EFV_PROD_FILL};fill-opacity:{_EFV_PROD_OP};">'
                f'<title>Production grade {g} - {pc} prospect{"s" if pc != 1 else ""} with no source grade '
                f'(not an eFV), {ppct:.1f}% of the production-grade rows</title></rect>')

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
        f'aria-label="Histogram of eephusFV grades for source-graded prospects, banded by rarity tier'
        f'{", with production grades for prospects no source has graded stacked above in grey" if prod_total else ""}">'
        f'<title>eFV distribution: {total} source-graded prospects, median {median}'
        f'{f"; {prod_total} production grades stacked above" if prod_total else ""}; '
        f'grades {lo} to {hi}</title>'
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
    if prod_total:
        chips.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;">'
            f'<span aria-hidden="true" style="width:10px;height:10px;flex:none;'
            f'background:{_EFV_PROD_FILL};opacity:{_EFV_PROD_OP};"></span>production grade, no source grade'
            f'<span style="color:var(--text-tertiary)">{prod_total:,}</span></span>')
    legend = ('<div style="display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px;'
              'font-family:var(--font-retro-mono);font-size:11px;color:var(--text-secondary);">'
              + "".join(chips) + '</div>')
    caption = (
        f'<div style="margin-top:6px;font-family:var(--font-retro-mono);font-size:11px;'
        f'color:var(--text-tertiary);line-height:1.5;">'
        f'{total:,} source-graded prospects · median {_gl("xfv", "eFV")} {median} · '
        f'{floor_n:,} at the eFV {int(_EFV_FLOOR)} floor (no projection), not plotted · '
        + (f'{prod_total:,} {_gl("xfv_ungraded", "production grades")} for prospects no source has '
           f'graded, in grey, not eFV ('
           + (f'median {prod_median}, ' if prod_median is not None else '')
           + f'{prod_floor_n:,} at {int(_EFV_FLOOR)}, not plotted) · '
           if prod else '')
        + f'bands are {_gl("rarity_tiers", "rarity tiers")}</div>')
    return _home_module("eFV Distribution", "/prospx/", "Full board",
                        svg + legend + caption, full=True)


# The rail's family key (HOME_2): five aria-pressed buttons, one per family.
# Pressing one leaves only that family's rows (data-fam) and the date headers
# that still have a row; pressing it again shows every row. The polite status
# line gives the visible count; a family with no row in the rail says so.
_WIRE_RAIL_JS = '''<script>
(function () {
  "use strict";
  var bar = document.getElementById("wire-key");
  var feed = document.getElementById("wire-rows");
  if (!bar || !feed) return;
  var st = document.getElementById("wire-key-status");
  var empty = document.getElementById("wire-empty");
  // At 900 px and below the rail is a block in the page that shows 6 rows
  // (HOME_4); a filter there shows the first 6 rows of its family.
  var mq = window.matchMedia ? window.matchMedia("(max-width: 900px)") : null;
  var cur = "", curBtn = null;
  function apply(announce) {
    var cap = mq && mq.matches ? 6 : Infinity;
    var shown = 0, day = null, dayAny = false;
    function closeDay() { if (day) day.style.display = dayAny ? "flex" : "none"; }
    Array.prototype.forEach.call(feed.children, function (el) {
      if (el.classList.contains("feed-day")) { closeDay(); day = el; dayAny = false; return; }
      if (!el.classList.contains("feed-item")) return;
      var show = (!cur || el.getAttribute("data-fam") === cur) && shown < cap;
      el.style.display = show ? "flex" : "none";
      if (show) { shown++; dayAny = true; }
    });
    closeDay();
    if (empty) {
      empty.hidden = shown !== 0;
      if (!shown && curBtn) empty.textContent = "No " + curBtn.getAttribute("title") + " rows in this list.";
    }
    if (st && announce) st.textContent = shown + (shown === 1 ? " row" : " rows") + " shown";
  }
  bar.addEventListener("click", function (e) {
    var b = e.target.closest("[data-wire-filter]");
    if (!b) return;
    cur = b.getAttribute("aria-pressed") === "true" ? "" : b.getAttribute("data-wire-filter");
    curBtn = cur ? b : null;
    bar.querySelectorAll("[data-wire-filter]").forEach(function (x) {
      var on = !!cur && x === b;
      x.classList.toggle("active", on);
      x.setAttribute("aria-pressed", on ? "true" : "false");
    });
    apply(true);
  });
  if (mq) {
    var onmq = function () { apply(false); };
    if (mq.addEventListener) mq.addEventListener("change", onmq);
    else if (mq.addListener) mq.addListener(onmq);
  }
})();
</script>'''


# The homepage's two bands (HOME_4, SP-D1): MLB first, then Prospects. A
# reversal is this one line; the jump bar and the band order both read it.
HOME_BAND_ORDER = ("mlb", "pro")
# Band id -> (anchor, h2, jump-bar label, 32 px mark). The mark is the family's
# key mark (_WIRE_FAMILIES), so the band and the news key read as one system;
# the rule under each band head is the family colour (--wire-mlb, --wire-pro).
_HOME_BANDS = {
    "mlb": ("band-mlb", "MLB", "MLB", _WIRE_FAMILIES["mlb"]["mark"]),
    "pro": ("band-pro", "Prospects", "Prospects", _WIRE_FAMILIES["pro"]["mark"]),
}
# The rail's row count on desktop; at 900 px and below the rail shows the
# first _HOME_RAIL_PHONE_ROWS (the server marks the rest wire-more).
_HOME_RAIL_ROWS = 20
_HOME_RAIL_PHONE_ROWS = 6
# The lead story runs only while the newest article is this fresh; an older
# article is one line in the site strip (H10).
_HOME_LEAD_MAX_DAYS = 30
# The Prospects band's PROSPX link row: these six sections, then the rest under
# "All sections" (every PROSPX_SUBNAV link stays one click away).
_HOME_PROSPX_LINKS = ("/prospx/", "/prospx/#tab=farm", "/prospx/#tab=leaderboards",
                      "/prospx/#tab=draft", "/prospx/#tab=timemachine", "/prospx/#tab=charts")


def _home_band(band: str, count_line: str, body: str, extra_head: str = "") -> str:
    """One band: its masthead (32 px mark, h2, one count line read from served
    data, a 2 px rule in the family colour) and its blocks."""
    anchor, h2, _jump, mark = _HOME_BANDS[band]
    return (f'<section class="home-band home-band--{band}" id="{anchor}" aria-labelledby="{anchor}-h">'
            f'<div class="band-head"><span class="band-mark">{_ico(mark, 32)}</span>'
            f'<div class="band-titles"><h2 id="{anchor}-h">{html.escape(h2)}</h2>'
            f'<span class="band-count">{count_line}</span></div></div>'
            f'{extra_head}{body}</section>')


def _home_club_logos() -> str:
    """The 30 club logos (HOME_4), each linking its Franchises club view by the
    hash assets/franchise.js reads (#view=club&team=<CODE>). The logo is the
    hub's own small URL (QHOP01), the same bytes every module page caches."""
    rows = sorted(_club_table()["rows"], key=lambda r: r["code"])
    links = "".join(
        f'<a class="club-logo-link" href="/franchise/#view=club&amp;team={r["code"]}" '
        f'title="{_esc_hub(r["name"])}: franchise overview">'
        f'<img class="club-logo" src="{_esc_hub(r["logo"])}" alt="{_esc_hub(r["name"])}" width="28" height="28" '
        f'loading="lazy" onerror="this.outerHTML=\'<span class=&quot;club-logo&quot;>{r["code"]}</span>\'"></a>'
        for r in rows)
    return f'<nav class="club-logos" aria-label="MLB clubs">{links}</nav>'


def _home_prospx_links() -> str:
    """The Prospects band's link row: six PROSPX sections with their 12 px tab
    icons, then "All sections" opening the rest (the old rail sub-nav)."""
    def a(label, href):
        return f'<a href="{href}">{_ico(_prospx_subnav_section(href), 12)}{html.escape(label)}</a>'
    main = [a(lab, h) for lab, h in PROSPX_SUBNAV if h in _HOME_PROSPX_LINKS]
    rest = [a(lab, h) for lab, h in PROSPX_SUBNAV if h not in _HOME_PROSPX_LINKS]
    more = (f'<details class="band-links-more"><summary>All sections</summary>'
            f'<div class="band-links-menu">{"".join(rest)}</div></details>') if rest else ""
    return (f'<nav class="band-links" aria-label="PROSPX sections">'
            f'{_ico("prospx", 12)}<span class="band-links-lab">PROSPX</span>{"".join(main)}{more}</nav>')


def _home_article_age(a: dict, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(str(a.get("date_sort") or "")[:10])).days
    except ValueError:
        return None


def build_home(articles: list[dict], data: dict | None = None) -> str:
    """Homepage (HOME_4, LANE_HOME 3): the shared site header, the MLB News
    rail on the left, and in the main column a slim masthead, then the MLB
    band and the Prospects band in HOME_BAND_ORDER, then the site strip. Every
    block keeps its builder and its numbers; this layer only places them."""
    data = data or {}
    players = data.get("players") or []
    org_summary = data.get("org_summary") or []
    graduates = data.get("graduates") or []
    as_of = data.get("as_of", " - ")
    today_d = date.today()
    today = datetime.now().strftime("%A, %B %d, %Y").replace(" 0", " ")
    events = _collect_events(players, graduates, _load_fa_events_for_wire())
    spotlight_buckets = data.get("spotlights") or {}

    # ---- the MLB News rail (LANE_HOME 3.2 row 6) ----
    # Its own sticky scroller above 900 px; at 900 px and below a block after
    # the masthead showing _HOME_RAIL_PHONE_ROWS rows (rows past it carry
    # wire-more, which the phone stylesheet hides), never inside a drawer.
    feed = _feed_html(events, _HOME_RAIL_ROWS)
    if feed:
        parts = re.split(r'(?=<a class="feed-item")|(?=<div class="feed-day")', feed)
        n_rows, out, pending_day = 0, [], ""
        for part in parts:
            if part.startswith('<div class="feed-day"'):
                pending_day = part
                continue
            if not part:
                continue
            n_rows += 1
            more = n_rows > _HOME_RAIL_PHONE_ROWS
            if pending_day:
                out.append(pending_day.replace('class="feed-day"', 'class="feed-day wire-more"', 1)
                           if more else pending_day)
                pending_day = ""
            out.append(part.replace('class="feed-item"', 'class="feed-item wire-more"', 1) if more else part)
        feed = "".join(out)
    else:
        feed = _px_state("empty", "No recent activity.")
    rail = (
        f'<aside class="home-rail" id="home-rail" aria-label="{NEWS_LABEL}">'
        f'<div class="sb-feed"><div class="feed-head"><a href="/news/" title="All {NEWS_LABEL}"><span class="blip"></span>{NEWS_LABEL}<span class="feed-head-more">all →</span></a></div>'
        # The family key (HOME_2): mark plus tag, a filter over the rows below.
        f'<div class="filter-bar wire-key" id="wire-key" role="group" aria-label="Filter {NEWS_LABEL} by family">'
        f'{_wire_key_html("data-wire-filter", tags=True)}</div>'
        '<div class="visually-hidden" id="wire-key-status" role="status" aria-live="polite"></div>'
        f'<div class="wire-rows" id="wire-rows">{feed}</div>'
        '<p class="news-empty" id="wire-empty" hidden></p>'
        f'<a class="feed-all" href="/news/">All {NEWS_LABEL} →</a>'
        f'<p class="feed-asof">As of {html.escape(as_of)}</p></div>'
        '</aside>'
        + _WIRE_RAIL_JS
    )

    # ---- top wire ticker ----
    # Decorative scrolling marquee - duplicates the accessible MLB News rail,
    # so it's hidden from assistive tech (aria-hidden) to avoid reading the
    # same items twice / announcing a moving region.
    ticker = (f'<div class="home-ticker" aria-hidden="true"><span class="ticker-tag"><a href="/news/" tabindex="-1"><span class="blip"></span>{NEWS_LABEL}</a></span>'
              f'<div class="ticker-track">{_ticker_html(events)}</div></div>')

    # ---- slim masthead (row 9) and the phone jump bar ----
    masthead = (
        '<div class="masthead">'
        f'{eephus_logo_lockup()}'
        '<div class="dateline"><span>Sabermetric Analysis</span>'
        f'<span>{html.escape(today)}</span><span>Data as of {html.escape(as_of)}</span></div></div>'
    )
    jump = ('<nav class="home-jump" aria-label="Homepage bands">'
            + "".join(f'<a href="#{_HOME_BANDS[b][0]}">{html.escape(_HOME_BANDS[b][2])}</a>'
                      for b in HOME_BAND_ORDER)
            + '</nav>')
    # Draft War Room banner: hidden by default, revealed by a small client-side
    # check ONLY while the live draft feed reports status "live" (draft night).
    # Links into the PROSPX draft section's War Room view. No em dashes (copy
    # rule). It sits in the Prospects band's callout slot (row 10).
    war_room = (
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

    # ---- lead story (row 12) ----
    # Owner decision 2026-08-04: the homepage editorial section carries HUMAN
    # editorials only. The full lead runs only while the newest article is
    # _HOME_LEAD_MAX_DAYS old or less; an older one is a line in the site strip.
    latest = articles[0] if articles else None
    age = _home_article_age(latest, today_d) if latest else None
    lead = ""
    if latest and age is not None and age <= _HOME_LEAD_MAX_DAYS:
        lead = (
            '<article class="lead-story no-img">'
            '<div><div class="lead-kicker">Latest</div>'
            f'<h2>{html.escape(latest["title"])}</h2>'
            f'<div class="byline">{_byline(latest, link_handle=False)}</div>'
            f'<p class="excerpt">{html.escape(latest.get("summary", ""))}</p>'
            f'<a class="read" href="/articles/{latest["slug"]}/">Read the full story →</a></div>'
            '</article>'
        )
        sec = articles[1:4]
        if sec:
            lead += ('<div class="secondary-stories">' + "".join(
                f'<a href="/articles/{a["slug"]}/"><div class="s-kicker">{html.escape(a.get("date_disp", ""))}</div>'
                f'<h3>{html.escape(a["title"])}</h3></a>' for a in sec) + '</div>')

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

    spot = _spotlight_html(players, spotlight_buckets)
    spot = f'<section class="home-module spot-module">{spot}</section>' if spot else ""
    otd = _this_day_html(graduates, players)
    trades_mod = _recent_trades_html(players)
    efv_dist = _efv_distribution_html(players)
    cards = _xmod_cards()

    # ---- the MLB band (LANE_HOME 3.2 rows 11, 21; new blocks) ----
    # The Scores / Standings strip slot is empty until HOME_6 fills it.
    mlb_cells = [c for c in (
        _xmod_card_html(cards["fa"]) if "fa" in cards else "",
        _xmod_card_html(cards["projections"]) if "projections" in cards else "",
        _home_leaders_card(cards),
        _xmod_card_html(cards["trademachine"]) if "trademachine" in cards else "",
        _xmod_card_html(cards["pal"]) if "pal" in cards else "",
    ) if c]
    n_clubs = len(_club_table()["rows"])
    mlb_band = _home_band(
        "mlb", f"{n_clubs} clubs",
        _date_callout("mlb", today_d)
        + '<div class="home-scores-slot" id="home-scores-slot" hidden></div>'
        + _home_club_logos()
        + f'<div class="band-grid">{"".join(mlb_cells)}</div>'
        + _home_diamond_strip(cards))

    # ---- the Prospects band (rows 7, 8, 10, 14 to 20, 21) ----
    n_ranked = sum(1 for p in players if p.get("overall_rank"))
    n_farms = sum(1 for o in org_summary if o.get("farm_rank"))
    pro_count = " · ".join(x for x in (
        f"{n_ranked:,} ranked prospects" if n_ranked else "",
        f"{n_farms} farm systems" if n_farms else "") if x) or "the prospect board"
    pro_cards = "".join(_xmod_card_html(cards[k]) for k in ("collegesavant", "parks") if k in cards)
    pro_band = _home_band(
        "pro", pro_count,
        _date_callout("pro", today_d) + war_room
        + f'<div class="module-cols">{spot}{topp}{movers}{grads}{farm}{otd}{trades_mod}</div>'
        + efv_dist
        + (f'<div class="band-grid">{pro_cards}</div>' if pro_cards else ""),
        extra_head=_home_prospx_links())

    bands = {"mlb": mlb_band, "pro": pro_band}

    # ---- site strip: Articles, Model Accountability, Library ----
    if latest and not lead:
        art_rows = (f'<a class="xmod-row xmod-row--stack" href="/articles/{latest["slug"]}/">'
                    f'<span class="xmod-name">{html.escape(latest["title"])}</span>'
                    f'<span class="xmod-sub">{html.escape(latest.get("date_disp", ""))}</span></a>')
        art_sub = "the latest piece"
    else:
        art_rows = '<a class="xmod-row" href="/articles/"><span class="xmod-name">Every article</span><span class="xmod-val">open →</span></a>'
        art_sub = "long-form analysis"
    strip = [_xmod_card_html((f'{_ico("articles", 16)}Articles', "/articles/", art_sub, art_rows))]
    if "models" in cards:
        strip.append(_xmod_card_html(cards["models"]))
    strip.append(_xmod_card_html((
        f'{_ico("glossary", 16)}{GLOSSARY_DISPLAY_NAME}', "/glossary/",
        "definitions and methodology for every metric on the site",
        f'<a class="xmod-row" href="/glossary/"><span class="xmod-name">Terms and models</span>'
        f'<span class="xmod-val">open →</span></a>')))
    site_strip = f'<section class="home-site-strip" aria-label="Across eephus.io"><div class="band-grid band-grid--3">{"".join(strip)}</div></section>'

    # eephus.io - Forums module (third content pillar). Hydrated client-side by
    # eephus-ui.js (#eph-home-forums): bump/Hot ordering, last-active first.
    #
    # COLLAPSED UNTIL THE ACCOUNT LAYER IS LIVE. assets/eephus-config.js is
    # absent on the public tree, so eephus-ui.js's LIVE gate has no Supabase
    # project, mountForumsList paints "Threads open at launch" and the
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
        '<main class="home-main" id="main" tabindex="-1">'
        f'{lead}'
        + "".join(bands[b] for b in HOME_BAND_ORDER)
        + f'{forums_mod}{site_strip}'
        '</main>'
    )
    inner = (f'{ticker}{_nav("home")}<div class="home-shell">'
             f'<div class="home-head">{masthead}</div>{jump}{rail}{main}</div>')
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
    recently active first. Static shell gives SEO + first paint + a nav home.

    Until the account layer is configured (REDESIGN_home_shell, 2026-10-07)
    the page shows one 'unmeasured' state card, not the empty Active / Hot
    list with its preview flag. The list mount stays in the page, hidden, and
    the same condition the homepage Forums slot gates on (window.EEPHUS_SUPABASE
    carrying url + anonKey) swaps the card for the list, so configuring the
    accounts needs no rebuild."""
    state = _px_state(
        "unmeasured",
        "<strong>Forums are not open yet.</strong> They open when accounts go live; "
        "each prospect, farm system and article will carry its own thread.",
        "eph-forums-closed")
    body = (
        f'<div class="section-head"><h1>{_masthead_icon("forums")}Forums '
        f'{_stage_chip("forums")}</h1>'
        '<span class="section-sub">Discussion across prospects, farm systems, and articles</span></div>'
        '<div class="eph-forums-index-page">'
        f'<div id="eph-forums-closed">{state}</div>'
        '<div id="eph-forums-live" hidden><div id="eph-forums-index"></div></div></div>'
        '<script>(function(){function r(){try{var c=window.EEPHUS_SUPABASE;'
        'if(c&&c.url&&c.anonKey){var l=document.getElementById("eph-forums-live"),'
        's=document.getElementById("eph-forums-closed");'
        'if(l)l.removeAttribute("hidden");if(s)s.hidden=true;}}catch(e){}}'
        'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",r);'
        'else r();})();</script>'
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
        f'<div class="section-head section-head--byline"><div class="section-head-titles"><h1>{_masthead_icon("fa")}MLB Free Agency '
        f'{_stage_chip("fa")}</h1></div>'
        '<span class="section-sub">predicted contract vs '
        f'{_gl("rational_value", "rational value")}</span></div>'
        '<div id="fa-banner"></div>'
        '<div class="filter-bar"><span class="filter-label">View</span>'
        '<span id="fa-view-chips"></span></div>'
        f'<div id="fa-rows" class="fa-hold"{_csv_optin("fa-class")}></div>'
        # QMLP04: the empty board can paint before fa.js runs, so a tall view
        # holds one viewport from the first frame; the card and the tracker are
        # short and drop the hold before that frame.
        '<script>(function(){var r=document.getElementById("fa-rows");'
        'if(r&&/(^|[#&])(player=|view=tracker)/.test(location.hash))r.classList.remove("fa-hold");})();</script>'
        '<nav class="fa-related" aria-label="Related modules">Related'
        '<a href="/projections/">Projections</a><a href="/arbitration/">Arbitration</a>'
        '<a href="/trademachine/">Trade Machine</a><a href="/ledger/">Club Ledger</a>'
        '<a href="/franchise/">Franchises</a></nav>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/fa.js?v={_FA_VER}" defer></script>'
        f'<script src="/assets/fa_dpw.js?v={_FA_DPW_VER}" defer></script>'
    )
    return page("Free Agency - eephus.io", "fa", body,
                f"The {_fa_span} MLB free-agent class: projected contracts with floor, mean and "
                "ceiling bands, value vs predicted price, team fits, and "
                f"{_fa_winters} archived winters of realized surplus.",
                url=f"{SITE_ORIGIN}/fa/", image=module_share_image("fa"))


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
    <h2 class="newsprint-eyebrow-label tm-eyebrow-h2"><span class="g-term" data-gl="trade_machine">Deal builder</span></h2>
  </div>
  <div id="trade-machine"></div>
  <div id="tm-live" class="visually-hidden" role="status" aria-live="polite"></div>
  <details class="tm-how"><summary>How this works</summary><ul>
    <li><strong>One currency.</strong> Each player carries the surplus the rest of the site prints: a prospect's eFV surplus NPV, an MLB player's club control window surplus (guaranteed seasons in full, unsigned seasons through the fifth projected season).</li>
    <li><strong>Rental leg:</strong> remaining season fraction &times; full-season surplus (projected WAR value minus salary). No floor: negative means the salary still owed exceeds the production.</li>
    <li><strong>Verdict.</strong> Gap = |Side A &minus; Side B| over the larger side. Under $5M reads balanced; otherwise it names the side that receives less. It predicts no club's answer.</li>
    <li><strong>Board.</strong> Bayesian surplus, contract-aware, positional scarcity, opt-out adjusted. A row's tooltip names its range and the basis of the range.</li>
  </ul></details>
  <div class="newsprint-eyebrow tm-board-eyebrow">
    <h2 class="newsprint-eyebrow-label tm-eyebrow-h2" id="tm-board-title">Trade-value board</h2>
  </div>
  <div class="filter-toggle-row">
    <button class="filter-toggle" type="button" data-collapse-target="tradeboard-filter-bar" aria-expanded="false" title="Show / hide Trade Board filters">
      <span class="filter-toggle-label">Filter &amp; Sort</span>
      <span class="filter-toggle-arrow" aria-hidden="true">&#9662;</span>
    </button>
    <input id="tb-search" type="search" placeholder="Search player name..." aria-label="Search the trade-value board by player name" autocomplete="off" spellcheck="false">
  </div>
  <div id="tradeboard-filter-bar" class="filter-bar collapsible-filter-bar">
    <div class="filter-group"><span class="filter-label">Pool</span>
      <button class="chip active" data-tb-pool="all" type="button" aria-pressed="true">All</button>
      <button class="chip" data-tb-pool="milb" type="button" aria-pressed="false">MiLB</button>
      <button class="chip" data-tb-pool="mlb" type="button" aria-pressed="false">MLB</button>
    </div>
    <div class="filter-group"><span class="filter-label">Tier</span>
      <button class="chip active" data-tb-tier="all" type="button" aria-pressed="true">All tiers</button>
      <button class="chip" data-tb-tier="elite" type="button" aria-pressed="false">Elite ($40M+)</button>
      <button class="chip" data-tb-tier="high" type="button" aria-pressed="false">High ($20-40M)</button>
      <button class="chip" data-tb-tier="mid" type="button" aria-pressed="false">Mid ($8-20M)</button>
    </div>
    <div class="filter-group"><span class="filter-label">Position</span>
      <button class="chip active" data-tb-pos="all" type="button" aria-pressed="true">All</button>
      <button class="chip" data-tb-pos="C" type="button" aria-pressed="false">C</button>
      <button class="chip" data-tb-pos="1B" type="button" aria-pressed="false">1B</button>
      <button class="chip" data-tb-pos="2B" type="button" aria-pressed="false">2B</button>
      <button class="chip" data-tb-pos="SS" type="button" aria-pressed="false">SS</button>
      <button class="chip" data-tb-pos="3B" type="button" aria-pressed="false">3B</button>
      <button class="chip" data-tb-pos="LF" type="button" aria-pressed="false">LF</button>
      <button class="chip" data-tb-pos="CF" type="button" aria-pressed="false">CF</button>
      <button class="chip" data-tb-pos="RF" type="button" aria-pressed="false">RF</button>
      <button class="chip" data-tb-pos="SP" type="button" aria-pressed="false">SP</button>
      <button class="chip" data-tb-pos="RP" type="button" aria-pressed="false">RP</button>
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
  <div id="tb-group-panel" style="display:none;margin:8px 0;padding:12px 16px;background:var(--bg-secondary);border:1px solid var(--border-subtle);border-radius:8px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span id="tb-group-title" style="font-weight:700;font-size:13px;"></span>
      <button type="button" aria-label="Close the profile group" onclick="document.getElementById('tb-group-panel').style.display='none';" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:16px;">&#10005;</button>
    </div>
    <div id="tb-group-body"></div>
  </div>
  <div id="tradeboard-content" data-csv-export="trade-board"><div class="spinner-wrap"><span class="spinner"></span></div></div>
  <nav class="tm-related" aria-label="Related modules">Related: <a href="/projections/">MLB Projections</a> &middot; <a href="/prospx/">PROSPX</a> &middot; <a href="/ledger/">Club Ledger</a> &middot; <a href="/arbitration/">Arbitration</a></nav>""")

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


def _mlb_events_attr() -> str:
    """The player pages' timeline switch (Q9_22b): ' data-mlb-events="live"' on
    #proj-rows while mlb_events.MLB_EVENTS_LIVE is True, and nothing otherwise, so
    with the flag off the shell is byte-identical and assets/projections.js makes
    no request under /data/mlb_events/. mlb_events holds the one definition."""
    try:
        import mlb_events
    except Exception:  # noqa: BLE001
        return ""
    return ' data-mlb-events="live"' if getattr(mlb_events, "MLB_EVENTS_LIVE", False) else ""


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
        f'<div class="section-head section-head--byline"><div class="section-head-titles"><h1>{_masthead_icon("projections")}MLB Projections '
        f'{_stage_chip("projections")}</h1></div>'
        f'<span class="section-sub">five-year {_gl("ewar", "eWAR")} paths for every MLB player and prospect · '
        f'{_gl("proj_buckets", "floor / mean / ceiling")} · contract surplus</span></div>'
        '<div id="proj-view-projections">'
        '<div id="proj-banner"></div>'
        '<div class="filter-bar" id="proj-filters"></div>'
        f'<div id="proj-rows"{_csv_optin("mlb-projections")}{_mlb_events_attr()}></div>'
        '</div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/projections.js?v={_PROJ_VER}" defer></script>'
        + _PROJ_TM_REDIRECT
    )
    return page("MLB Projections - eephus.io", "projections", body,
                "Five-year WAR projections for every MLB player, trained on published fWAR: floor, mean and ceiling paths, "
                "club-control surplus, and PROSPX prospects at their ETA.",
                url=f"{SITE_ORIGIN}/projections/", image=module_share_image("projections"))



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
            "over an intercept-plus-WAR baseline, in minimum detectable effects",
            "green" if a1.get("resolvable") else "orange"))
    if a2:
        tiles.append(tile(
            "%.2fx" % (a2.get("gain_over_floor") or 0), "arb-2+ vs its floor",
            "under 1.00: a NULL against a step multiplier", "orange"))
    if a6.get("n"):
        tiles.append(tile(
            "%.1fx" % (a6.get("ratio_ours_over_swartz") or 0),
            "Swartz is more accurate",
            "on %d settled seasons with an MLBTR projection"
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

    # QCLC21 (2026-10-02): the frozen a6 statement explains the Swartz gap by
    # counting stats, and no ablation in the artifact measures that. The page
    # quotes it with that sentence compressed to what is known (assets/ledger.js
    # does the same); the artifact is the gate's record and is not edited.
    def _loss_text(s):
        return re.sub(r"The mechanism is not mysterious:[^.]*\.",
                      "Swartz uses counting stats (HR, RBI, saves, wins) this model "
                      "excludes; how much of the gap that explains is not measured.",
                      str(s or ""))

    losses = []
    for entry in ev.get("loss_ledger") or []:
        losses.append('<li><strong>%s</strong>: %s</li>'
                      % (html.escape(str(entry.get("claim", ""))),
                         html.escape(_loss_text(entry.get("statement", "")))))

    # The substitute-source agreement figures live in the artifact
    # (conventions.pool); this list names the limit and does not retype them.
    gaps = (
        "<ul>"
        "<li>It prices the system, not the hearing: no filed figures, so a panel "
        "case is scored on its award alone.</li>"
        "<li>Steps before 2022 are reconstructed from substitute service-time "
        "sources: reported, not scored.</li>"
        "<li>2020 is never a label year (salaries paid at 60/162, reported on "
        "inconsistent bases).</li>"
        "<li>The CBA expires 2026-12-01. Seasons from 2027 assume the arbitration "
        "structure survives; no interval here covers that.</li>"
        "<li>Non-tendered players are absent, so summed projections overstate what "
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
            '<dt>status</dt><dd>Registered 2026-09-16. None of its clauses has been scored, so the surplus '
            'the path prices on /projections/, /trademachine/ and the player '
            'card has no receipt yet.</dd></dl></details>'
            % html.escape(sp_mode))

    return (
        '<div class="arb-scorecard">%s</div>'
        '<div class="section-head"><h2>What was measured</h2>'
        '<span class="section-sub">pre-registered</span></div>'
        '%s'
        '<div class="section-head"><h2>Downstream gates</h2>'
        '<span class="section-sub">built on this model</span></div>'
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
        + '<h1>' + _masthead_icon("arbitration") + 'Arbitration Predictor ' + _stage_chip("arbitration") + '</h1></div>'
        '<span class="section-sub">Projected and settled '
        + _gl("arb_award_model", "arbitration awards")
        + '. Arb 1 is model-priced (it beat its baseline); '
        'Arb 2+ a step multiplier (the model did not).</span></div>'
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
        # Related modules, linked once (display pass 2026-10-03).
        '<nav class="arb-related" aria-label="Related modules">Related: '
        '<a href="/ledger/">Club Ledger</a> &middot; <a href="/franchise/">Franchises</a> &middot; '
        '<a href="/projections/">Projections</a> &middot; <a href="/trademachine/">Trade Machine</a></nav>'
        '</div>'
        '<script src="/assets/eephus-hub.js?v=' + _HUB_VER + '" defer></script>'
        '<script src="/assets/eephus-teampick.js?v=' + _TEAMPICK_VER + '" defer></script>'
        '<script src="/assets/arbitration.js?v=' + _ARB_VER + '" defer></script>'
    )
    return page("Arbitration Predictor - eephus.io", "arbitration", body,
                "Projected arbitration salaries for every eligible MLB player, "
                "and a per-season record of who the arbitration market overpaid "
                "and underpaid.",
                url=SITE_ORIGIN + "/arbitration/", image=module_share_image("arbitration"))


def build_trademachine() -> str:
    """The /trademachine/ Trade Machine module (top-level, module by Anirudh
    Iyer). Build and value a deal both ways - prospects on eFV surplus, MLB
    players on projection surplus - then the full Bayesian trade-value board.
    Static shell + assets/trademachine.js on the standalone trade_values.json /
    mlb_projections.json data. Was formerly a #view=trademachine tab inside MLB
    Projections."""
    body = (
        # The module stylesheet comes BEFORE the markup it styles: written after
        # it, Chromium painted the builder and board heads once unstyled and then
        # moved them when the sheet landed (a 0.31 layout shift at 390 px).
        f'<link rel="stylesheet" href="/assets/trademachine.css?v={_TM_CSS_VER}">'
        # id="proj-view-trademachine" is kept for trademachine.js, which scopes its
        # filter + collapse wiring to that id; .tm-app carries the standalone theming.
        '<div class="fa-app proj-app tm-app" id="proj-view-trademachine">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles"><h1>{_masthead_icon("trademachine")}Trade Machine '
        f'{_stage_chip("trademachine")}</h1></div>'
        f'<span class="section-sub">One currency of {_gl("surplus_value", "surplus")}: '
        'prospects on eFV, MLB players on projections, and a debuted player no projection prices on his '
        'locked eFV backgrade (registry row xfv_backgrade, provisional)</span></div>'
        + _TRADE_MACHINE_BODY +
        '</div>'
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
                url=f"{SITE_ORIGIN}/trademachine/", image=module_share_image("trademachine"))

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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("mlbstats")}MLB Stats {_stage_chip("mlbstats")}</h1></div>'
        # One line: each board's number once, and the scale. The tabs under it
        # name the boards, and the year-range term rides the Years label of
        # every board's own control (display pass 2026-10-07).
        f'<span class="section-sub">{_gl("ewar", "eWAR")}, {_gl("hem_plus", "HEM+")}, '
        f'{_gl("sem_plus", "SEM+")}, {_gl("rem_plus", "REM+")}, {_gl("dem_plus", "DEM+")} and '
        f'{_gl("wpa", "WPA")} leaderboards. 100 is league average on every + scale.</span></div>'
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
                "MLB leaderboards: every player by eWAR, season or year range; HEM+, SEM+, "
                "REM+, RIV+ and DEM+ boards; WPA leverage; team Bullpen+, Rotation+, Offense+, "
                "DEM+.",
                url=f"{SITE_ORIGIN}/mlbstats/", image=module_share_image("mlbstats"))

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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
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
                url=f"{SITE_ORIGIN}/pal/", image=module_share_image("pal"))

def _fantasy_panel(mod: str, blurb: str, bar: str, nav_label: str,
                   tabs: list[tuple[str, str]], csv_name: str,
                   active: bool, how: str = "") -> str:
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
    `:empty` rule takes the emptied slot out of layout.

    `blurb` is the one-line lede; `how` is the method, folded into a closed
    "How this works" block under it (display pass 2026-10-07), so the board
    sits higher and the method stays one click away."""
    btns = "".join(
        f'<button type="button" class="mlbstats-sectionbtn{" active" if i == 0 else ""}" '
        f'data-{mod}section="{key}" role="tab" '
        f'aria-selected="{"true" if i == 0 else "false"}">{label}</button>'
        for i, (key, label) in enumerate(tabs))
    return (
        f'<div class="fantasy-mod" id="fantasy-mod-{mod}" data-fantasypanel="{mod}" '
        f'role="tabpanel" aria-label="{nav_label}"{"" if active else " hidden"}>'
        f'<span class="section-sub fantasy-modsub">{blurb}</span>'
        + (f'<details class="fh-how"><summary>How this works</summary><p>{how}</p></details>'
           if how else '') +
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
        "Ranks and streamers in your league's scoring format.",
        # redraft.js fills this from data/fantasy.json scoring_catalog, and only
        # on the three tabs S.system can actually move.
        '<div id="redraft-scoring" class="fantasy-scoring-bar" aria-label="League scoring format"></div>',
        "Redraft",
        [("streamers", "Daily Streamers"), ("two_start", "Two-Start SP"),
         ("ros_sp", "ROS SP"), ("ros_rp", "ROS RP"), ("ros_hitter", "ROS Hitters"),
         ("buysell", "Buy / Sell"), ("closers", "Closer Grid")],
        "redraft-board", True,
        how="Formats: Ottoneu FanGraphs Points (the default), SABR Points, Old School 5x5 and "
            "Ottoneu 4x4. Lines come from the MLB Projections engine; matchup context from "
            f"{_gl('rem_plus', 'REM+')}, {_gl('sem_plus', 'SEM+')}, {_gl('hem_plus', 'HEM+')}, "
            "Offense+ and Bullpen+.")
    dynasty = _fantasy_panel(
        "dynasty",
        f"Prospects on {_gl('xfv', 'eFV')}, for dynasty and keeper leagues.",
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
        "dynasty-board", False,
        how="The Dynasty Board ranks prospects only: eFV first, blended with the star (Elite) "
            "bucket share, bust risk, ETA and surplus. Call-up Watch lists who is next. Fantasy "
            "Rank ranks MLB players and prospects on projected fantasy value in your format, not "
            "on WAR. The keeper calculator compares a rank with the pick a keeper costs, in a "
            "prospects-only draft or, on its All players pool, a draft of both.")
    dfs = _fantasy_panel(
        "dfs",
        "Today's slate, re-scored per game. No salary feed is scraped.",
        # No slot: the contest-format selector renders inline at the top of the
        # DFS section, which is where it was before the merge.
        "",
        "DFS",
        [("slate", "Today's Slate"), ("value", "Value Plays"),
         ("optimizer", "Lineup Optimizer"), ("stacks", "Stacks")],
        "dfs-slate", False,
        how="The Redraft engine re-scored per game for the probable pitcher, park and bullpen. "
            "Paste or import your DFS salaries and the optimizer builds against them.")
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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
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
                url=f"{SITE_ORIGIN}/fantasy/", image=module_share_image("fantasy"))


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
# /dynasty/, /redraft/ and /dfs/ were pages of their own for two days and were
# redirect stubs from 2026-08-07. Since 2026-10-07 (owner answer LB-Q3) the
# stub dirs are gone and the 404 page forwards each address, hash and all,
# through RETIRED_ROUTES.
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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("betting")}Sports Betting {_stage_chip("betting")}</h1></div>'
        f'<span class="section-sub">Model probability vs the {_gl("devig", "de-vigged")} book price. '
        'The public record is append-only, one unit per pick, '
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
        # QREP04 (2026-10-07): betting.js paints the feed strip and the section
        # after the payload lands, so the shell reserves both slots before
        # first paint. Without this the strip pushed the tabs down and the
        # section grew from the loader past the footer: CLS 0.31 to 0.67.
        # The legal card's compact type lives here too, not in betting.js, so
        # it is in place at first paint and cannot move the tabs later. Its
        # words are unchanged; it took 312 px of a 390 px phone's first screen.
        '<style>#betting-feedhealth:empty{min-height:37px}#betting-section{min-height:70vh;display:flow-root}'
        '.betting-app .betting-disclaimer{padding:12px 16px}.betting-app .betting-disclaimer h3{margin:0 0 4px}'
        '.betting-app .betting-disclaimer p{font-size:13px;line-height:1.5}'
        '@media (max-width:640px){#betting-feedhealth:empty{min-height:54px}}</style>'
        '<div id="betting-feedhealth"></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Sports Betting sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-bettingsection="potd" role="tab" id="bt-tab-potd" aria-controls="betting-section" aria-selected="true">Pick of the Day</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="teams" role="tab" id="bt-tab-teams" aria-controls="betting-section" aria-selected="false">Team Bets</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="props" role="tab" id="bt-tab-props" aria-controls="betting-section" aria-selected="false">Player Props</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="parlays" role="tab" id="bt-tab-parlays" aria-controls="betting-section" aria-selected="false">Parlays</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="calculators" role="tab" id="bt-tab-calculators" aria-controls="betting-section" aria-selected="false">Calculators</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="record" role="tab" id="bt-tab-record" aria-controls="betting-section" aria-selected="false">The Record</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="validation" role="tab" id="bt-tab-validation" aria-controls="betting-section" aria-selected="false">Validation</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="futures" role="tab" id="bt-tab-futures" aria-controls="betting-section" aria-selected="false">Futures</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-bettingsection="mybets" role="tab" id="bt-tab-mybets" aria-controls="betting-section" aria-selected="false">My Bets</button>'
        '</div>'
        '<div id="betting-section" class="mlbstats-section" role="tabpanel" aria-labelledby="bt-tab-potd">'
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
                url=f"{SITE_ORIGIN}/betting/", image=module_share_image("betting"))



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
            f'model, {GLOSSARY_DISPLAY_NAME} and articles stay open to everyone.</p>'
            '</div>'
        )
    else:
        money = (
            '<div class="card diamond-price">'
            f'<h3>${price} a month, when it goes live</h3>'
            f'<p>At launch Diamond is ${price} a month.</p>'
            f'<p>Founding rate: ${founding} a month, held for a year, for everyone using the preview.</p>'
            '<p class="diamond-fine">Diamond funds the free site: the board, projections, free agency '
            f'model, {GLOSSARY_DISPLAY_NAME} and articles stay open to everyone.</p>'
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
         f"projections, free agency model, {GLOSSARY_DISPLAY_NAME} and articles stay public.")
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
        sub = 'Paid tier for fantasy and betting.'
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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("diamond")}Diamond Pass {_stage_chip("diamond")}</h1></div>'
        f'<span class="section-sub">{sub}</span></div>'
        f'{banner}'
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
        # DISPLAY PASS (2026-10-07): the report-card sentence introduces the
        # receipts, so it sits on them instead of between the banner and the
        # price, where it was read before anything it describes.
        '<div class="gl-intro">'
        '<p>eephus.io publishes its own report card: the prospect model\'s out-of-sample record '
        'against the public consensus, failed experiments included.</p>'
        '</div>'
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
                url=f"{SITE_ORIGIN}/diamond/", image=module_share_image("diamond"))

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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("parks")}MiLB Park Factors {_stage_chip("parks")}</h1></div>'
        f'<span class="section-sub">Run and home-run {_gl("milb_park_factor", "park factors")} for every '
        'affiliated venue, Triple-A to the DSL. Display only: no model reads them.</span></div>'
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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("management")}In-Game Management {_stage_chip("management")}</h1></div>'
        '<span class="section-sub">Every in-game decision in the play corpus, with the '
        f'{_gl("realized_mwpa", "realized win probability")} it governed and, where priced, its '
        f'{_gl("decision_value", "decision value")}. Realized value records outcomes, not skill. '
        'No club is ranked.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Management sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-mgmtsection="league" role="tab" id="mgmt-tab-league" aria-controls="mgmt-section" aria-selected="true">League</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="running" role="tab" id="mgmt-tab-running" aria-controls="mgmt-section" aria-selected="false">Running Game</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="bunt" role="tab" id="mgmt-tab-bunt" aria-controls="mgmt-section" aria-selected="false">Bunt</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="decisions" role="tab" id="mgmt-tab-decisions" aria-controls="mgmt-section" aria-selected="false">Decisions</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="clubs" role="tab" id="mgmt-tab-clubs" aria-controls="mgmt-section" aria-selected="false">Clubs</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="managers" role="tab" id="mgmt-tab-managers" aria-controls="mgmt-section" aria-selected="false">Managers</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="challenges" role="tab" id="mgmt-tab-challenges" aria-controls="mgmt-section" aria-selected="false">Challenges</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="lineups" role="tab" id="mgmt-tab-lineups" aria-controls="mgmt-section" aria-selected="false">Lineups</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="reference" role="tab" id="mgmt-tab-reference" aria-controls="mgmt-section" aria-selected="false">Run Expectancy</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mgmtsection="gate" role="tab" id="mgmt-tab-gate" aria-controls="mgmt-section" aria-selected="false">Club Gate</button>'
        '</div>'
        '<div id="mgmt-section" class="mlbstats-section" role="tabpanel" aria-labelledby="mgmt-tab-league">'
        f'<div id="mgmt-app-root"{_csv_optin("in-game-management")}></div>'
        '</div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/management.css?v={_MGMT_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'<script src="/assets/management.js?v={_MGMT_VER}" defer></script>'
    )
    return page("In-Game Management - eephus.io", "management", body,
                "Every in-game decision in the play corpus, with the win probability that "
                "moved after it. Realized value per family; no cross-family total, no plus metric.",
                url=f"{SITE_ORIGIN}/management/", image=module_share_image("management"))


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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
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
                "Every club's CBT payroll, commitments and controlled surplus, from Spotrac and "
                "our own models, each on its own scale. No revenue, valuations or TV money.",
                url=f"{SITE_ORIGIN}/ledger/", image=module_share_image("ledger"))


def _scores_module_head(active: str) -> str:
    """The Scores / Standings masthead (STANDINGS_PLAN 3, the rename): the 32 px
    icon, the h1 with the stage chip, the sub line and, only once
    standings_core.STANDINGS_LIVE is True, a two-link strip with aria-current
    on the page shown. /scores/ calls it with active="scores"; STANDINGS_4
    reuses it with "standings"."""
    try:
        import standings_core
        strip = bool(getattr(standings_core, "STANDINGS_LIVE", False))
    except ImportError:
        strip = False
    nav = ""
    if strip:
        links = []
        for key, label, href in (("scores", "Scores", "/scores/"), ("standings", "Standings", "/standings/")):
            cur = ' aria-current="page"' if key == active else ""
            links.append(f'<a class="mlbstats-sectionbtn{" active" if cur else ""}" href="{href}"{cur}>{label}</a>')
        nav = f'<nav class="mlbstats-sectionnav" aria-label="Scores / Standings">{"".join(links)}</nav>'
    return (
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("scores")}Scores / Standings {_stage_chip("scores")}</h1></div>'
        '<span class="section-sub">MLB games by date: the score, MLB\'s win probability, the plays that '
        'moved it with MLB\'s video, box scores, and three stars chosen by a published rule.</span></div>'
        + nav
    )


def build_scores() -> str:
    """The /scores/ shell (SCORES_3), a pure reader of /data/scores/.

    BEHIND THE FLAG. main() writes scores/index.html while
    scores_core.SCORES_LIVE is True (from SCORES_5a, the flip, 2026-10-07);
    with the flag False only write_scores_page() renders this shell, into
    .cache/scores/preview/site/, and nothing public changes.

    Shell on the build_ledger pattern: the byline section head (through
    _scores_module_head), one mount root, then the module css, eephus-hub.js,
    eephus-teampick.js and assets/scores.js, deferred. The shell types no
    number; every number on the page is read by assets/scores.js from the
    job's files. No EEPHUS_DATA_VERS: the job rewrites its files between
    builds (_data_vers_script refuses scores names). The mount root carries
    the stamped path of the lazy bracket chunk (SCORES_4b), which scores.js
    loads only on #bracket=<season> or for the October rail at 1400 px.
    SCORES_6 adds the Diamond config and helper (scores.js asks
    window.EephusDiamond before it prints a model number), the eager
    assets/scores-pregame.js, and BETTING_DISCLAIMER in an inert template the
    chunk prints once wherever the pregame model number renders."""
    body = (
        '<div class="fa-app scores-app">'
        + _scores_module_head("scores")
        + f'<div id="scores-app-root" data-vv="{_SCORES_VIDEO_VER}"'
        f' data-bracket-src="/assets/scores-bracket.js?v={_SCORES_BRACKET_VER}"></div>'
        # SCORES_6: the site's betting note, printed once wherever the pregame
        # model number renders (plan 9); inert until scores-pregame.js copies it
        f'<template id="scores-betnote">{BETTING_DISCLAIMER}</template>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/scores.css?v={_SCORES_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-teampick.js?v={_TEAMPICK_VER}" defer></script>'
        f'{DIAMOND_CONFIG_SCRIPT}'
        f'<script src="/assets/scores-pregame.js?v={_SCORES_PREGAME_VER}" defer></script>'
        f'<script src="/assets/scores.js?v={_SCORES_VER}" defer></script>'
    )
    return page("MLB Scores - eephus.io", "scores", body,
                "MLB scores by date: MLB's live win probability, the biggest plays with MLB's video, "
                "box scores, and Stars of the Game by a published rule.",
                url=f"{SITE_ORIGIN}/scores/")


#: Where the shell renders while scores_core.SCORES_LIVE is False (plan 5.1).
SCORES_PREVIEW_SITE = ROOT / ".cache" / "scores" / "preview" / "site"


def write_scores_page(preview_root=None) -> str:
    """Write the /scores/ shell where the flag allows, and return the path.

    A preview_root always gets the preview copy, whatever the flag says (the
    render tests build their temporary site this way, so a test never writes
    the published tree). With no preview_root: SCORES_LIVE True writes the
    published scores/index.html, False only the preview copy under
    SCORES_PREVIEW_SITE. main() names the published route by literal, because
    tools/gen_audit_docs.py reads the literal _write calls there (SCORES_5a),
    and calls this only while the flag is off."""
    import scores_core
    rel = "scores/index.html"
    if preview_root is None and scores_core.SCORES_LIVE:
        _write(rel, build_scores())
        return str(ROOT / rel)
    root = Path(preview_root) if preview_root is not None else SCORES_PREVIEW_SITE
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_scores(), encoding="utf-8")
    print(f"  wrote {path.as_posix()} (the preview copy, not the published tree)")
    return str(path)


def build_franchise() -> str:
    """The /franchise/ Franchises module (2026-09-23, D3; named Franchise
    Overview until the owner's TEAM-1 rename on 2026-10-02).

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
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("franchise")}Franchises {_stage_chip("franchise")}</h1></div>'
        f'<span class="section-sub" id="franchise-masthead">The {_gl("franchise_index", "Franchise Index")} of every club '
        f'and the {_gl("franchise_branch_score", "branch scores")} beneath it, re-standardised across 30 clubs, '
        'with every number on the scale it was computed on.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Franchises sections">'
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
    return page("Franchises - eephus.io", "franchise", body,
                "One page per club: the Franchise Index and its three branches (roster eWAR, "
                "provisional 2027 projection, PROSPX farm), re-standardised across 30 clubs.",
                url=f"{SITE_ORIGIN}/franchise/", image=module_share_image("franchise"))


def build_hof(live: bool | None = None) -> str:
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
    unreachable before that); the three static nav copies carry it too.

    The head comes from _hof_module_head("hof") (AWARDS_7). With
    awards_core.AWARDS_LIVE False this page is byte-identical to the shell
    before the Awards section except its asset stamps; with it True the h1
    reads "Awards / HoF", the Awards | Hall of Fame strip sits under it, and
    the four section buttons move to the underline tab row, keeping their
    ARIA. `live` overrides the flag for the render checks only."""
    on = _awards_live(live)
    body = (
        '<div class="fa-app mlbstats-app hof-app">'
        + _hof_module_head("hof", on) + _hof_section_row(on) +
        '<div id="hof-section" class="mlbstats-section">'
        f'<div id="hof-app-root"{_csv_optin("hall-of-fame")}></div>'
        '</div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/hof.css?v={_HOF_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/hof.js?v={_HOF_VER}" defer></script>'
    )
    return page("Hall of Fame - eephus.io", "hof", body,
                "Career WAR, WAR7 and JAWS for every ten-season player (Baseball-Reference "
                "daily WAR), with the ballot record. No Hall line or snub list.",
                url=f"{SITE_ORIGIN}/hof/", image=module_share_image("hof"))


# --------------------------------------------------------------------------- #
# Awards / HoF: the shared module head and /awards/ (AWARDS_7; AWARDS_PLAN 3 'The
# rename' and 5.1 'URL, shell, tabs, hash'). ONE masthead site serves two pages,
# /awards/ and /hof/ (Q11_06_MODULE_MASTHEADS counts it once). While
# awards_core.AWARDS_LIVE is False the head renders the Hall of Fame h1 exactly as
# before and no strip, main() writes no awards/index.html, and /awards/ renders
# only into the preview folder below for the render checks. AWARDS_11 flips it.
# --------------------------------------------------------------------------- #
AWARDS_PREVIEW_SITE = ROOT / ".cache" / "awards" / "preview" / "site"
_AWARDS_SUB = ("The eephus selection for each BBWAA award, chosen by a published rule over the "
               "site's own numbers, with superlatives from the same numbers and a ballot of your own. "
               "Not a forecast of the writers' vote.")
_AWARDS_DESCRIPTION = ("MVP, Cy Young, Rookie and Manager of the Year: the eephus selection by a "
                       "published rule over eWAR and the site's metrics, season races, superlatives, "
                       "and a ballot you can fill in, save and share. Not a forecast of the vote.")
# The /hof/ section row: one list, two styles (boxed buttons while the flag is False,
# the underline tab row once it is True), the same ARIA either way.
_HOF_SECTIONS = (("board", "Leaderboards"), ("franchises", "Franchises"),
                 ("blocked", "Bake-off &amp; What Is Not Published"), ("method", "Method &amp; Sample"))


def _awards_live(live: bool | None = None) -> bool:
    """The module flag, read at call time so a test can set it."""
    return bool(awards_core.AWARDS_LIVE if live is None else live)


def _hof_sub() -> str:
    return (f'Career WAR, {_gl("war7", "WAR7")} and {_gl("jaws", "JAWS")} for '
            'every ten-season player (Baseball-Reference daily WAR), with the ballot record. '
            'Bands: eligible, active, five-year wait. No Hall line or snub list (Bake-off says why).')


def _hof_module_head(active: str, live: bool | None = None) -> str:
    """The masthead of both Awards / HoF pages: icon, h1, stage chip, the page's
    sub line and (flag True) the link strip with aria-current on `active`
    ("awards" or "hof"). The strip items are links, not tabs: each loads a page."""
    sub = _AWARDS_SUB if active == "awards" else _hof_sub()
    if not _awards_live(live):
        return ('<div class="section-head section-head--byline"><div class="section-head-titles">'
                f'<h1>{_masthead_icon("hof")}Hall of Fame {_stage_chip("hof")}</h1></div>'
                f'<span class="section-sub">{sub}</span></div>')
    name = html.escape(awards_core.MODULE_LABEL)
    links = []
    for key, label, href, icon in (("awards", "Awards", "/awards/", "aw-podium"),
                                   ("hof", "Hall of Fame", "/hof/", "hof")):
        cur = key == active
        links.append(f'<a class="mlbstats-sectionbtn{" active" if cur else ""}" href="{href}"'
                     + (' aria-current="page"' if cur else "")
                     + f'>{_ico(icon, 12)}{label}</a>')
    return ('<div class="section-head section-head--byline"><div class="section-head-titles">'
            f'<h1>{_masthead_icon("hof")}{name} {_stage_chip("hof")}</h1></div>'
            f'<span class="section-sub">{sub}</span></div>'
            f'<nav class="mlbstats-sectionnav hof-modstrip" aria-label="{name}">' + "".join(links) + "</nav>")


def _hof_section_row(live: bool) -> str:
    box, btn = ("mlbstats-tabs", "mlbstats-tab") if live else ("mlbstats-sectionnav", "mlbstats-sectionbtn")
    out = [f'<div class="{box}" role="tablist" aria-label="Hall of Fame sections">']
    for i, (key, label) in enumerate(_HOF_SECTIONS):
        on = i == 0
        out.append(f'<button type="button" class="{btn}{" active" if on else ""}" data-hofsection="{key}" '
                   f'role="tab" aria-selected="{"true" if on else "false"}">{label}</button>')
    out.append("</div>")
    return "".join(out)


def build_awards(live: bool | None = None) -> str:
    """The /awards/ page of Awards / HoF: the shared head, then one mount that
    assets/awards.js fills from data/awards.json (Selections; My Ballot is the lazy
    assets/awards-ballot.js chunk, AWARDS_9; Share and Save image load eephus-gfx.js
    on the first press, AWARDS_10; Superlatives, Rule and vote and Method
    land with AWARDS_8). The value
    ruler and the state component ride the shared head block. Not written to the
    published tree while awards_core.AWARDS_LIVE is False (write_awards_page)."""
    body = (
        '<div class="fa-app mlbstats-app aw-app">'
        + _hof_module_head("awards", live) +
        f'<div id="awards-app-root" class="aw-root"{_csv_optin("awards")}'
        f' data-ballot-js="/assets/awards-ballot.js?v={_AWARDS_BALLOT_VER}"'
        f' data-ballot-css="/assets/awards-ballot.css?v={_AWARDS_BALLOT_CSS_VER}"'
        f' data-gfx-js="/assets/eephus-gfx.js?v={_GFX_VER}"></div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/awards.css?v={_AWARDS_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/awards.js?v={_AWARDS_VER}" defer></script>'
    )
    # The module card (AWARDS_10, tools/pixel_brand_src.AWARDS_CARD) is written only
    # with the flag on, so a flag-off build keeps the shelf's card.
    image = (f"{SITE_ORIGIN}/assets/og/awards.png" if PIXEL_BRAND and _awards_live(live)
             else module_share_image("hof"))
    return page("MLB Awards - eephus.io", "hof", body, _AWARDS_DESCRIPTION,
                url=f"{SITE_ORIGIN}/awards/", image=image)


def write_awards_preview(site: Path | None = None) -> Path:
    """Render /awards/ (head and strip as the flag-on build draws them) into the
    preview folder, never the published tree."""
    out = (site or AWARDS_PREVIEW_SITE) / "awards" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_awards(live=True), encoding="utf-8")
    return out


def write_awards_page() -> str:
    """main()'s one awards step: awards/index.html when the flag is True, else the
    preview copy only. Returns the path written."""
    if _awards_live():
        _write("awards/index.html", build_awards())
        return "awards/index.html"
    out = write_awards_preview()
    try:
        rel = out.relative_to(ROOT).as_posix()
    except ValueError:
        rel = out.as_posix()
    print(f"  held awards/index.html (AWARDS_LIVE False); preview {rel}")
    return rel


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
    """One registry row, server-rendered. The row's `summary` leads the open
    row; `notes` (the lab log) is left to the glossary card on purpose (see
    the section header comment)."""
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
        _acct_kv("Summary", m.get("summary") or "")
        + _acct_kv("Predicts", m.get("predicts") or "")
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
        # Linked ahead of the markup so the tiles paint as a grid (QREP05).
        f'<link rel="stylesheet" href="/assets/accountability.css?v={_ACCT_HUB_CSS_VER}">'
        f'<div class="fa-app mlbstats-app acct-app" data-acct-stale-days="{model_registry.STALE_DAYS}">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("models")}Model Accountability</h1></div>'
        '<span class="section-sub">Every model with a predictive claim, its '
        f'{_gl("model_verdict", "verdict")}, and the eval artifact behind it, read from the registry '
        'and the artifacts at build time.</span></div>'
        '<div class="acct-intro">'
        f'<p>Registry vintage: <strong>{html.escape(_fmt_iso_date(reg.get("checked_at")))}</strong>. '
        f'Version <code>{html.escape(str(reg.get("version") or ""))}</code>. Source: '
        '<a href="/data/model_registry.json"><code>data/model_registry.json</code></a>; each row\'s '
        f'full note is on the <a href="/glossary/#view=models">{GLOSSARY_DISPLAY_NAME} ledger</a>.</p>'
        "<p>Each model's score history and edge over its benchmark: <a href=\"/models/updates/\">"
        f'{PAGE_LABELS["/models/updates/"]}</a>.</p>'
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


# --------------------------------------------------------------------------- #
# /models/updates/ - Model Updates (LIBRARY_12; owner ask 2026-10-02; plan
# LIBRARY_PLAN.md section 4.5, lane LANE_UPDATES.md sections 7 and 8).
#
# A pure reader of data/model_updates.json (model_updates.py writes it). Every
# number and every edge text is copied from that file: this builder computes
# no statistic and prints no verdict word of its own; the edge words come from
# model_updates.edge() through the file. The only arithmetic is layout: the
# lamp ladder's scale (one lamp = a fifth of the largest |edge| or |bound| in
# a leg's history) and the artifact age against the build clock, which
# assets/model_updates.js re-derives against the reader's clock.
#
# Server-rendered end to end on the /models/ precedent: with JavaScript off the
# stands table, every fold, the default timetable and the drawers (shown by a
# noscript rule) are all on the page. The client filters rows that are already
# in the DOM and opens drawers; it fetches nothing. Not in NAV_ITEMS: discovery
# rides the footer, the /models/ hub line, the Library's Evidence leaf and
# sitemap.xml.
# --------------------------------------------------------------------------- #
_MU_SCORED_STATES = ("lead", "tie", "trails", "unresolved", "no_contest")
# The folds for served models without a measured edge, in page order.
_MU_FOLDS = (
    ("no_benchmark", "No benchmark registered"),
    ("no_eval", "No eval artifact"),
    ("unwired", "Benchmark named; headline not wired yet"),
    ("card_error", "Card does not derive from its artifact"),
)
# Change-kind chips: (chip key, label, producer kinds). A kind outside these
# (artifact change, frame change, backfill, removed, note) shows under All.
_MU_KIND_CHIPS = (
    ("model", "model change", ("model_change",)),
    ("correction", "correction", ("scoring_correction", "data_correction")),
    ("verdict", "verdict", ("verdict",)),
    ("rescored", "rescored", ("rescored",)),
    ("first", "first scored", ("first_scored",)),
    ("registered", "registered", ("registered",)),
)
_MU_KIND_OF = {k: key for key, _l, kinds in _MU_KIND_CHIPS for k in kinds}
# The toggles, off by default: (layer, label). Development reads also show the
# update rows of the development models, which have no served page.
_MU_TOGGLES = (
    ("development", "development reads"),
    ("typed", "typed history"),
    ("registration", "registrations"),
)
_MU_LAYER_TAG = {"development": "development read", "typed": "typed history",
                 "registration": "registration", "note": "note"}
# eFV's frames by name, for the pinned row's benchmark cell and the ladder's
# column order (vm1 columns, a gap, then vm2; plan 4.5, lane 8).
_MU_EFV_IDS = ("efv_v1", "efv_v2")
_MU_EFV_FRAME_ORDER = {"vm": 0, "vm2": 1}
_MU_EFV_FRAME_LABEL = {"vm": "vintage-matched frame (vm1)",
                       "vm2": "vintage-matched timing-pinned frame (vm2)"}
_MU_LADDER_COLS = (24, 12)          # drawer, row cell (lane 8: 1280 and 390)
_MU_STAND_COLS = 8                  # Model .. Last update, plus the ladder


def _mu_isnum(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _mu_fmt(v, d) -> str:
    """A copied number at the leg's own digits (the card's, else as copied)."""
    if not _mu_isnum(v):
        return "-"
    return f"{v:.{d}f}" if isinstance(d, int) else f"{v:g}"


def _mu_n(v) -> str:
    return f"{v:,}" if _mu_isnum(v) else "-"


def _mu_interval(x: dict, d) -> str:
    """The interval cell for one leg or edge: the 95% interval on the gap,
    else the one-sided t, else the artifact's detection floor, else the words
    'no interval on record' (copy rule)."""
    d = d if isinstance(d, int) else 4
    ci = x.get("ci95")
    if isinstance(ci, (list, tuple)) and len(ci) == 2 and all(_mu_isnum(c) for c in ci):
        return f"{ci[0]:+.{d}f} to {ci[1]:+.{d}f}"
    if _mu_isnum(x.get("t")):
        return f"t {x['t']:.3f}"
    if _mu_isnum(x.get("mde95")):
        return f"floor {x['mde95']:.{d}f}"
    return "no interval on record"


def _mu_age(day: str | None) -> str:
    """'2026-10-02 6d' as a <time> the client re-ages against the reader's clock."""
    if not day:
        return "-"
    try:
        age = (date.today() - date.fromisoformat(day[:10])).days
    except ValueError:
        return html.escape(day)
    days = f' <small class="mu-age">{age}d</small>' if age >= 0 else ""
    return f'<time datetime="{html.escape(day[:10])}">{html.escape(day)}</time>{days}'


def _mu_plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _mu_leg_cols(events: list, leg: dict, frame_order: dict | None = None) -> list:
    """One leg's edge history, oldest first: one column per scored event whose
    legs carry this leg (same stat, same benchmark), None for the gap a frame
    change draws. Development and typed rows never draw."""
    key = (leg.get("stat"), leg.get("benchmark_label"))
    rows = []
    for i, ev in enumerate(events):
        if ev.get("layer") not in ("headline", "secondary"):
            continue
        lg = next((x for x in ev.get("legs") or []
                   if (x.get("stat"), x.get("benchmark_label")) == key), None)
        if lg is None or not _mu_isnum(lg.get("delta")):
            continue
        st = ev.get("statistic") or {}
        fr = st.get("frame")
        rank = (frame_order or {}).get(fr, 0)
        rows.append((rank, ev.get("sort_date") or "", i, fr, ev, lg, st))
    rows.sort(key=lambda r: r[:3])
    cols, prev = [], None
    for _r, _d, _i, fr, ev, lg, st in rows:
        if cols and fr and prev and fr != prev:
            cols.append(None)
        prev = fr or prev
        cols.append({"delta": lg["delta"], "ci": lg.get("ci95"),
                     "state": lg.get("edge_state") or "tie",
                     "date": ev.get("date") or "",
                     "changed": st.get("before") is not None and not st.get("same_rows")})
    return cols


def _mu_ladder(cols: list, *, name: str, leg: dict, max_cols: int, lamp_px: int = 6) -> tuple:
    """(svg, scale text) for one leg: the edge lamp ladder of lane section 8.
    11 lamp rows, the middle one the tie line; the interval as lit lamps, the
    point lamp coloured by the edge state the rule printed (green and red only
    for lead and trails); a 1 px tick over a column whose rows changed; an
    empty column where the frame changed. role=img; the timetable is its text
    equivalent."""
    cols = list(cols)
    kept, n_real = [], 0
    for c in reversed(cols):
        if c is not None:
            if n_real == max_cols:
                break
            n_real += 1
        kept.append(c)
    cols = list(reversed(kept))
    while cols and cols[0] is None:
        cols.pop(0)
    real = [c for c in cols if c is not None]
    if not real:
        return "", ""
    d = leg.get("digits") if isinstance(leg.get("digits"), int) else 4
    big = 0.0
    for c in real:
        big = max(big, abs(c["delta"]))
        if isinstance(c["ci"], (list, tuple)) and len(c["ci"]) == 2:
            big = max(big, abs(c["ci"][0]), abs(c["ci"][1]))
    scale = big / 5 if big > 0 else 1.0

    def row_of(v):
        return 5 - max(-5, min(5, int(round(v / scale))))

    # The drawer draws 6 px lamps on an 8 px pitch (lane 8); the row cell the
    # same grid at half size, 3 px on 4, so a row stays one text block tall.
    L = lamp_px
    P = L + max(1, L // 3)
    top = 2 if L < 6 else 4

    def lamp(x, r):
        return f"M{x} {top + r * P}h{L}v{L}h-{L}z"

    w = len(cols) * P - (P - L)
    h = top + 11 * P - (P - L)
    board, zero, lit = [], [], []
    step = min(120, 1200 // max(1, len(real)))
    k = 0
    for j, c in enumerate(cols):
        if c is None:
            continue
        x = j * P
        board.append("".join(lamp(x, r) for r in range(11) if r != 5))
        zero.append(lamp(x, 5))
        p = row_of(c["delta"])
        inner = []
        ci = c["ci"]
        if isinstance(ci, (list, tuple)) and len(ci) == 2:
            top, bot = row_of(ci[1]), row_of(ci[0])
            d_ci = "".join(lamp(x, r) for r in range(top, bot + 1) if r != p)
            if d_ci:
                inner.append(f'<path class="li" d="{d_ci}"/>')
        st = c["state"] if c["state"] in ("lead", "trails", "tie", "unresolved") else "tie"
        if st == "unresolved":
            inner.append(f'<rect class="lp-unresolved" x="{x + 0.5}" y="{top + p * P + 0.5}" '
                         f'width="{L - 1}" height="{L - 1}"/>')
        else:
            inner.append(f'<path class="lp-{st}" d="{lamp(x, p)}"/>')
        if c["changed"]:
            inner.append(f'<path class="tk" d="M{x} 0h{L}v1h-{L}z"/>')
        lit.append(f'<g class="c" style="animation-delay:{k * step}ms">{"".join(inner)}</g>')
        k += 1
    counts = {s: sum(1 for c in real if c["state"] == s) for s in ("lead", "tie", "trails", "unresolved")}
    stat = leg.get("stat") or ""
    label = (f"{name} {stat}: latest {leg.get('edge_text') or ''}; "
             f"{_mu_plural(counts['lead'], 'lead')}, {_mu_plural(counts['tie'], 'tie')}, "
             f"{_mu_plural(counts['trails'], 'trail')}"
             + (f", {counts['unresolved']} with no interval" if counts["unresolved"] else "")
             + f" over {_mu_plural(len(real), 'update')} since {real[0]['date']}")
    svg = (f'<svg class="px-lamp mu-lad" role="img" aria-label="{html.escape(label)}" width="{w}" '
           f'height="{h}" viewBox="0 0 {w} {h}" shape-rendering="crispEdges">'
           f'<path class="lo" d="{"".join(board)}"/><path class="lz" d="{"".join(zero)}"/>'
           f'{"".join(lit)}</svg>')
    return svg, f"1 lamp = {scale:.{d}f} {stat.split(' vs ')[0]}"


def _mu_ladder_key() -> str:
    return ('<div class="px-lamp-key mu-key"><span>point = edge, bar = 95% interval, '
            'middle row = tie line, tick = rows changed</span>'
            '<span><i class="px-lk mu-lk-lead"></i>lead</span>'
            '<span><i class="px-lk mu-lk-tie"></i>tie</span>'
            '<span><i class="px-lk mu-lk-trails"></i>trails</span>'
            '<span><i class="px-lk mu-lk-unresolved"></i>no interval on record</span></div>')


def _mu_source(src: dict, legs: list) -> str:
    """The artifact path (a link when it ships at data/ depth one, else named,
    the /models/ rule), the key the number came from, and the commit."""
    path = (src or {}).get("path") or ""
    url, _why = _acct_artifact_url(path) if path else (None, "")
    out = []
    if path:
        p = html.escape(path)
        out.append(f'<a href="{html.escape(url)}">{p}</a>' if url else f"<code>{p}</code>")
    key = (src or {}).get("run_id")
    if not key and legs and isinstance(legs[0].get("keys"), dict):
        key = legs[0]["keys"].get("model")
    if key:
        out.append(f'<span class="mu-key-path">{html.escape(str(key))}</span>')
    commit = (src or {}).get("commit") or (src or {}).get("model_commit")
    if commit:
        out.append(f'<span class="mu-commit">commit {html.escape(str(commit))}</span>')
    return " ".join(out) or "-"


def _mu_statistic(st: dict | None, d) -> str:
    """Before to after, labelled 'same rows' with the change, or 'rows changed'
    with no change figure (plan 4.6: an improvement prints only on the same
    rows)."""
    if not st or not st.get("stat"):
        return "-"
    d = d if isinstance(d, int) else 4
    name = html.escape(st["stat"])
    after = _mu_fmt(st.get("after"), d)
    if st.get("before") is None:
        return f"{name} {after}"
    body = f"{name} {_mu_fmt(st['before'], d)} to {after}"
    if st.get("same_rows"):
        imp = st.get("improvement")
        return body + (f" ({imp:+.{d}f}, same rows)" if _mu_isnum(imp) else " (same rows)")
    nb, n = st.get("n_before"), st.get("n")
    if _mu_isnum(nb) and _mu_isnum(n) and nb != n:
        return body + f" (rows changed {_mu_n(nb)} to {_mu_n(n)})"
    return body + " (rows changed)"


def _mu_legs_html(legs: list, field) -> str:
    """One <div class="mu-leg"> per leg so the legs of a row stay paired by
    index across its cells."""
    return "".join(f'<div class="mu-leg" data-leg="{i}">{field(lg)}</div>'
                   for i, lg in enumerate(legs))


def _mu_bench_label(lg: dict, efv: bool) -> str:
    b = lg.get("benchmark_label") or "-"
    if efv and lg.get("role") == "headline":
        fr = ((lg.get("source") or {}).get("run_id") or "").split("|")
        frame = fr[1] if len(fr) > 2 else ""
        if frame in _MU_EFV_FRAME_LABEL:
            b = f"{b}, {_MU_EFV_FRAME_LABEL[frame]}"
    return b


def _mu_drawer(m: dict, evs: list, ladders: list, colspan: int) -> str:
    """The per-model drawer: the leg ladders with their scale, the key, and the
    model's dated history newest first (every layer, labelled)."""
    parts = []
    if ladders:
        parts.append('<div class="mu-ladders">' + "".join(
            f'<figure class="mu-lfig"><figcaption>{html.escape(cap)}</figcaption>{svg}'
            f'<span class="mu-scale">{html.escape(sc)}</span></figure>'
            for cap, svg, sc in ladders) + "</div>" + _mu_ladder_key())
    hist = []
    ordered = sorted(enumerate(evs), key=lambda ie: (ie[1].get("sort_date") or "", ie[0]), reverse=True)
    for _i, ev in ordered:
        tag = _MU_LAYER_TAG.get(ev.get("layer")) if ev.get("layer") != "registration" else None
        ed = ev.get("edge") or {}
        hist.append(
            f'<li><time>{html.escape(ev.get("date") or "")}</time> '
            f'{html.escape(ev.get("change") or "")}'
            + (f' <span class="mu-tag">{html.escape(tag)}</span>' if tag else "")
            + (f'<span class="mu-hedge">{html.escape(ed.get("text") or "")}</span>'
               if ed.get("state") not in ("none", "note", None) else "")
            + "</li>")
    parts.append(f'<ol class="mu-hist" aria-label="{html.escape(m["label"])} history">'
                 + "".join(hist) + "</ol>" if hist else
                 '<p class="mu-none">No dated update on record.</p>')
    mid = html.escape(m["model_id"])
    return (f'<tr class="mu-drawer" id="mu-d-{mid}" data-model="{mid}" hidden>'
            f'<td colspan="{colspan}">{"".join(parts)}</td></tr>')


def _mu_latest_first(ms: list) -> list:
    """Latest update first (a model with none last), then by name; stable."""
    out = sorted(ms, key=lambda m: m.get("label") or "")
    return sorted(out, key=lambda m: m.get("last_update") or "", reverse=True)


def _mu_open(m: dict) -> str:
    mid = html.escape(m["model_id"])
    return (f'<button class="mu-open" type="button" aria-expanded="false" aria-controls="mu-d-{mid}">'
            f'{html.escape(m["label"])}</button><code class="mu-id">{mid}</code>')


def _mu_events_of(m: dict, events: list) -> list:
    mid = m["model_id"]
    if mid == "efv_v2":
        return [e for e in events if e.get("model_id") in _MU_EFV_IDS]
    return [e for e in events
            if e.get("model_id") == mid or mid in (e.get("registry_ids") or [])]


def _mu_stand_row(m: dict, evs: list) -> tuple:
    """(row, sub-row, drawer) for one scored model. eFV prints its two headline
    legs and folds its four industry legs under 'against each source' (LB-Q1:
    two legs side by side, no summed figure)."""
    efv = m["model_id"] == "efv_v2"
    legs = list(m.get("today") or [])
    shown = [lg for lg in legs if lg.get("role") == "headline"] if efv else legs
    folded = [lg for lg in legs if lg.get("role") != "headline"] if efv else []
    order = _MU_EFV_FRAME_ORDER if efv else None
    ladders, cell_svg = [], ""
    for i, lg in enumerate(legs):
        cols = _mu_leg_cols(evs, lg, order)
        svg, sc = _mu_ladder(cols, name=m["label"], leg=lg, max_cols=_MU_LADDER_COLS[0])
        if svg:
            stat = lg.get("stat") or "-"
            cap = stat if " vs " in stat else f'{stat} vs {lg.get("benchmark_label") or "-"}'
            ladders.append((cap, svg, sc))
        if i == 0 and cols:
            cell_svg, _s = _mu_ladder(cols, name=m["label"], leg=lg, max_cols=_MU_LADDER_COLS[1],
                                      lamp_px=3)
    mid = html.escape(m["model_id"])
    # One table row per leg; the Model, Last update and History cells span
    # the model's legs, so the model reads as one row and a leg's cells stay
    # on one line however its benchmark wraps.
    span = f' rowspan="{len(shown)}"' if len(shown) > 1 else ""

    def leg_cells(lg):
        return (f'<td class="mu-c-stat">{html.escape(lg.get("stat") or "-")}</td>'
                f'<td class="mu-c-bench">{html.escape(_mu_bench_label(lg, efv))}</td>'
                f'<td class="mu-c-edge">{html.escape(lg.get("edge_text") or "-")}</td>'
                f'<td class="num mu-c-n">{_mu_n(lg.get("n"))}</td>'
                f'<td class="num mu-c-int">{html.escape(_mu_interval(lg, lg.get("digits")))}</td>')
    row = (
        f'<tr class="mu-stand" id="model={mid}" data-model="{mid}"'
        f'{" data-pinned" if efv else ""}>'
        f'<th scope="row" class="mu-mname"{span}>{_mu_open(m)}</th>'
        + leg_cells(shown[0])
        + f'<td class="mu-c-last"{span}>{_mu_age(m.get("last_update"))}</td>'
        f'<td class="mu-c-lad"{span}>{cell_svg}</td></tr>'
        + "".join(f'<tr class="mu-legrow" data-model="{mid}"{" data-pinned" if efv else ""}>'
                  f'{leg_cells(lg)}</tr>' for lg in shown[1:]))
    sub = ""
    if folded:
        lrows = "".join(
            f'<tr><th scope="row">{html.escape(lg.get("benchmark_label") or "-")}</th>'
            f'<td>{html.escape(lg.get("stat") or "-")}</td>'
            f'<td class="mu-c-edge">{html.escape(lg.get("edge_text") or "-")}</td>'
            f'<td class="num">{_mu_n(lg.get("n"))}</td>'
            f'<td class="num">{html.escape(_mu_interval(lg, lg.get("digits")))}</td></tr>'
            for lg in folded)
        sub = (f'<tr class="mu-sub" data-model="{mid}"><td colspan="{_MU_STAND_COLS}">'
               f'<details class="mu-src"><summary>against each source ({len(folded)} legs)</summary>'
               '<table class="mu-legs"><caption class="visually-hidden">'
               f'{html.escape(m["label"])} against each source</caption><thead><tr>'
               '<th scope="col">Source</th><th scope="col">Scored on</th><th scope="col">Edge</th>'
               '<th scope="col" class="num">n</th><th scope="col" class="num">Interval</th></tr></thead>'
               f'<tbody>{lrows}</tbody></table></details></td></tr>')
    return row, sub, _mu_drawer(m, evs, ladders, _MU_STAND_COLS)


def _mu_fold_table(title: str, models: list, events: list, n_cols: int = 5) -> str:
    rows = []
    for m in models:
        mid = html.escape(m["model_id"])
        rows.append(
            f'<tr class="mu-stand" id="model={mid}" data-model="{mid}">'
            f'<th scope="row" class="mu-mname">{_mu_open(m)}</th>'
            f'<td>{html.escape(m.get("family") or "-")}</td>'
            f'<td>{html.escape(m.get("verdict") or "-")}</td>'
            f'<td class="mu-c-edge">{html.escape((m.get("edge") or {}).get("text") or "-")}</td>'
            f'<td class="mu-c-last">{_mu_age(m.get("last_update"))}</td></tr>'
            + _mu_drawer(m, _mu_events_of(m, events), [], n_cols))
    return (f'<details class="mu-fold"><summary>{html.escape(title)} '
            f'<span class="mu-count">{len(models)}</span></summary>'
            f'<div class="mu-scroll"><table class="mu-table mu-foldt"><caption class="visually-hidden">'
            f'{html.escape(title)}</caption><thead><tr><th scope="col">Model</th>'
            '<th scope="col">Family</th><th scope="col">Verdict</th><th scope="col">Edge</th>'
            f'<th scope="col">Last update</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            '</div></details>')


def _mu_event_row(ev: dict, linkable: set) -> str:
    """One timetable row. Lean markup on purpose (481 rows today): the column
    styles key off the cell position, the filters off four data attributes,
    and the search off the Model cell's own text."""
    legs = [lg for lg in ev.get("legs") or [] if lg.get("role") == "headline"]
    st = ev.get("statistic")
    d = next((lg.get("digits") for lg in legs if isinstance(lg.get("digits"), int)), None)
    layer = ev.get("layer") or ""
    mid = ev.get("model_id")
    name = ev.get("label") or ev.get("family") or "-"
    if mid in linkable:
        who = f'<a href="#model={html.escape(mid)}">{html.escape(name)}</a>'
    elif mid in _MU_EFV_IDS:
        who = f'<a href="#model=efv_v2">{html.escape(name)}</a>'
    else:
        who = html.escape(name)
    tag = _MU_LAYER_TAG.get(layer) if layer != "registration" else None
    change = html.escape(ev.get("change") or "") + (
        f' <span class="mu-tag">{html.escape(tag)}</span>' if tag else "")
    bench = ev.get("benchmark") or {}
    parts = [bench.get("label") or ""]
    if _mu_isnum(bench.get("value")):
        parts.append(_mu_fmt(bench.get("value"), d))
    bench_txt = " ".join(x for x in parts if x) or "-"
    if legs and all(_mu_isnum(lg.get("delta")) for lg in legs):
        edge_c = _mu_legs_html(legs, lambda lg: html.escape(lg.get("edge_text") or "-"))
        int_c = _mu_legs_html(legs, lambda lg: html.escape(_mu_interval(lg, lg.get("digits"))))
    else:
        edge_c = html.escape((ev.get("edge") or {}).get("text") or "-")
        int_c = "-"
    attrs = (f' data-f="{html.escape(ev.get("family") or "")}"'
             f' data-k="{html.escape(_MU_KIND_OF.get(ev.get("kind"), ev.get("kind") or ""))}"'
             + (f' data-l="{html.escape(layer)}"' if layer != "headline" else "")
             + ("" if ev.get("served") else ' data-s="0"')
             + ("" if ev.get("default_view") else " hidden"))
    return (
        f'<tr{attrs}><td><time datetime="{html.escape((ev.get("sort_date") or "")[:10])}">'
        f'{html.escape(ev.get("date") or "")}</time></td>'
        f'<th scope="row">{who}</th><td>{change}</td><td>{_mu_statistic(st, d)}</td>'
        f'<td>{html.escape(bench_txt)}</td><td>{edge_c}</td>'
        f'<td>{_mu_n((st or {}).get("n"))}</td><td>{int_c}</td>'
        f'<td>{_mu_source(ev.get("source") or {}, legs)}</td></tr>')


def build_model_updates() -> str:
    """/models/updates/ - Model Updates: where each served model stands
    against its benchmark, and the dated timetable of every model update."""
    import model_updates as MU
    doc = MU.load() or {}
    models = list(doc.get("models") or [])
    events = list(doc.get("events") or [])
    fam_rank = {f: i for i, f in enumerate(doc.get("families") or [])}
    served = [m for m in models if m.get("served")]
    scored = [m for m in served if m.get("state") in _MU_SCORED_STATES and m.get("today")]
    scored_ids = {m["model_id"] for m in scored}
    # Scored first: family order, eFV pinned at the top, latest update first
    # within a family.
    scored = _mu_latest_first(scored)
    scored.sort(key=lambda m: (fam_rank.get(m.get("family"), 99), m["model_id"] != "efv_v2"))
    linkable = {m["model_id"] for m in models}

    body_rows, fam = [], None
    for m in scored:
        if m.get("family") != fam:
            if fam is not None:
                body_rows.append("</tbody>")
            fam = m.get("family")
            body_rows.append(f'<tbody><tr class="mu-famrow"><th scope="rowgroup" colspan="{_MU_STAND_COLS}">'
                             f'{html.escape(fam or "-")}</th></tr>')
        row, sub, drawer = _mu_stand_row(m, _mu_events_of(m, events))
        body_rows.append(row + sub + drawer)
    if fam is not None:
        body_rows.append("</tbody>")
    stands = (
        '<div class="mu-scroll"><table class="mu-table mu-stands">'
        '<caption class="visually-hidden">Where each scored model stands against its benchmark</caption>'
        '<thead><tr><th scope="col">Model</th><th scope="col">Scored on</th><th scope="col">Benchmark</th>'
        '<th scope="col">Edge</th><th scope="col" class="num">n</th><th scope="col" class="num">Interval</th>'
        '<th scope="col">Last update</th><th scope="col">History</th></tr></thead>'
        + "".join(body_rows) + "</table></div>")

    latest_first = _mu_latest_first
    folds = []
    for state, title in _MU_FOLDS:
        ms = [m for m in served if m["model_id"] not in scored_ids and m.get("state") == state]
        if ms:
            folds.append(_mu_fold_table(title, latest_first(ms), events))
    other = [m for m in served if m["model_id"] not in scored_ids
             and m.get("state") not in {s for s, _t in _MU_FOLDS}]
    if other:
        folds.append(_mu_fold_table("Other states", latest_first(other), events))
    dev = [m for m in models if not m.get("served")]
    dev_fold = _mu_fold_table("Development models, not served", latest_first(dev), events) if dev else ""

    # The timetable: newest first, append order breaking ties the newest way.
    order = sorted(range(len(events)),
                   key=lambda i: (events[i].get("sort_date") or "", i), reverse=True)
    ev_rows = "".join(_mu_event_row(events[i], linkable) for i in order)
    n_default = sum(1 for e in events if e.get("default_view"))
    fams = sorted({e.get("family") for e in events if e.get("family")},
                  key=lambda f: (fam_rank.get(f, 99), f))
    chip = ('<button class="chip{on}" type="button" aria-pressed="{p}" {attr}="{key}">'
            '{label}</button>')
    fam_chips = chip.format(on=" active", p="true", attr="data-mu-fam", key="all",
                            label="All families") + "".join(
        chip.format(on="", p="false", attr="data-mu-fam", key=html.escape(f), label=html.escape(f))
        for f in fams)
    kind_chips = chip.format(on=" active", p="true", attr="data-mu-kind", key="all",
                             label="All changes") + "".join(
        chip.format(on="", p="false", attr="data-mu-kind", key=k, label=html.escape(lab))
        for k, lab, _ks in _MU_KIND_CHIPS)
    tog_n = {lay: sum(1 for e in events if not e.get("default_view")
                      and (e.get("layer") == lay or (lay == "development" and not e.get("served")
                                                     and e.get("layer") in ("headline", "secondary"))))
             for lay, _l in _MU_TOGGLES}
    toggles = "".join(
        f'<button class="chip mu-tog" type="button" aria-pressed="false" data-mu-layer="{lay}">'
        f'{html.escape(lab)} <span class="mu-count">{tog_n[lay]}</span></button>'
        for lay, lab in _MU_TOGGLES)

    sources = doc.get("sources") or []
    own = {MU.REGISTRY_REL, MU.PROGRESS_REL, MU.TYPED_REL}
    n_art = sum(1 for s in sources if s.get("path") not in own)
    gen_day = (doc.get("generated_at") or "")[:10]
    stamp = (f"Updated {gen_day} from the model registry, the eFV progress ledger and "
             f"{_mu_plural(n_art, 'eval artifact')}.")
    sc_href = "/glossary/#view=source-comparison"
    body = (
        f'<link rel="stylesheet" href="/assets/model_updates.css?v={_MU_CSS_VER}">'
        '<noscript><style>.mu-app .mu-drawer[hidden]{display:table-row}'
        '.mu-app .mu-filter-btn,.mu-app .mu-bar{display:none}</style></noscript>'
        f'<div class="fa-app mu-app" data-mu-total="{len(events)}">'
        '<div class="section-head section-head--byline"><div class="section-head-titles">'
        f'<h1>{_masthead_icon("models")}Model Updates</h1></div>'
        '<span class="section-sub">Every model update on record, with the statistic it is scored on '
        'and where it stands against its benchmark.</span>'
        f'<span class="mu-stamp">{html.escape(stamp)}</span></div>'
        '<section class="mu-sec" aria-labelledby="mu-h-stands">'
        '<div class="section-head"><h2 id="mu-h-stands">Where each model stands</h2>'
        f'<span class="section-sub">{len(served)} served models, {len(scored)} scored</span></div>'
        '<p class="mu-intro">One row per served model, the scored ones first. A lead prints only when '
        'the interval clears zero, a one-sided paired t reaches 1.645, or, with neither on record, '
        "the gap clears the artifact's detection floor; a covered interval prints tie.</p>"
        f"{stands}{''.join(folds)}{dev_fold}</section>"
        '<section class="mu-sec" aria-labelledby="mu-h-time">'
        '<div class="section-head"><h2 id="mu-h-time">Timetable</h2>'
        f'<span class="section-sub">{n_default} updates in the default view, {len(events)} on record</span></div>'
        '<p class="mu-intro">Newest first. An improvement prints only when the rows are the same; '
        'a change in rows is labelled.</p>'
        '<button class="chip mu-filter-btn" type="button" aria-expanded="false" '
        'aria-controls="mu-bar">Filter</button>'
        '<div class="mu-bar" id="mu-bar">'
        f'<div class="filter-bar" role="group" aria-label="Family">{fam_chips}</div>'
        f'<div class="filter-bar" role="group" aria-label="Change">{kind_chips}</div>'
        f'<div class="filter-bar" role="group" aria-label="Show">{toggles}'
        '<input class="mu-search" id="mu-q" type="search" placeholder="Search model names" '
        'aria-label="Search model names" autocomplete="off"></div></div>'
        f'<p class="mu-status" id="mu-status" aria-live="polite">Showing {n_default} of {len(events)} updates.</p>'
        '<div id="mu-empty"></div>'
        '<div class="mu-scroll"><table class="mu-table mu-time">'
        '<caption class="visually-hidden">Timetable of model updates, newest first</caption>'
        '<thead><tr><th scope="col">Date</th><th scope="col">Model</th><th scope="col">What changed</th>'
        '<th scope="col">Statistic</th><th scope="col">Benchmark</th><th scope="col">Edge</th>'
        '<th scope="col" class="num">n</th><th scope="col" class="num">Interval</th>'
        f'<th scope="col">Source</th></tr></thead><tbody id="mu-rows">{ev_rows}</tbody></table></div>'
        '</section>'
        f'<p class="mu-foot">The eFV story in full: <a href="{sc_href}">Source Comparison</a>. '
        f'Each model\'s full row and its verdict: <a href="/models/">{PAGE_LABELS["/models/"]}</a>.</p>'
        '</div>'
        f'<script src="/assets/model_updates.js?v={_MU_VER}" defer></script>'
    )
    return page("Model Updates - eephus.io", "models", body,
                "Every eephus.io model update on record: the statistic each model is scored on, "
                "before and after, and its edge over the benchmark it is trying to beat.",
                url=f"{SITE_ORIGIN}/models/updates/")

# The Library's shelves and leaves (LIBRARY_3, plan section 3.1), in strip
# order. This is the Python half of ONE view registry: VIEWS in
# assets/glossary.js carries the same ids, shelves, labels, bodies, hrefs,
# aliases and listed flags, and test_library_section_registry asserts the two
# are equal. The client generates its URL whitelist, body map and dispatch
# from VIEWS; this side emits the strip and the body containers. A view is
# therefore added in exactly these two lists (the 2026-06-10 Source Comparison
# lesson was a chip registered in one place of four).
#   body:    the container id an in-page view paints into (None: outbound leaf)
#   href:    the page an outbound leaf links to; the leaf is left out of the
#            strip while that page is not built, so the strip has no dead link
#   aliases: older #view= values that open the view
#   listed:  False keeps a leaf out of the strip until its task fills it; the
#            view still opens from its URL and shows its chip while current
GLOSSARY_SHELVES = (
    ("reference", "Reference"),
    ("methods", "Methods"),
    ("evidence", "Evidence"),
    ("sources", "Sources"),
)
GLOSSARY_VIEWS = (
    {"id": "terms", "shelf": "reference", "label": "Terms", "body": "glossary-rows"},
    {"id": "guide", "shelf": "reference", "label": "How to Read", "body": "guide-body"},
    {"id": "formulas", "shelf": "reference", "label": "Formulas", "body": "formulas-body"},
    {"id": "methodology", "shelf": "methods", "label": "Methodology", "body": "methodology-body"},
    {"id": "source-comparison", "shelf": "evidence", "label": "Source Comparison", "body": "source-comparison-body"},
    {"id": "source-accuracy", "shelf": "evidence", "label": "Source Accuracy", "body": "source-accuracy-body"},
    {"id": "calibration", "shelf": "evidence", "label": "Calibration", "body": "calibration-body"},
    # The in-page registry view stays a normal view (and keeps its URL) until
    # LIBRARY_7 forwards it; the strip lists the /models/ ledger instead.
    {"id": "models", "shelf": "evidence", "label": "Models & Proofs", "body": "models-body", "listed": False},
    {"id": "models-ledger", "shelf": "evidence", "label": "Models", "href": "/models/"},
    {"id": "model-updates", "shelf": "evidence", "label": "Model Updates", "href": "/models/updates/"},
    {"id": "source-updates", "shelf": "sources", "label": "Source Updates", "body": "source-updates-body"},
    {"id": "data-sources", "shelf": "sources", "label": "Data Sources", "href": "/sources/"},
    {"id": "index", "shelf": "sources", "label": "Page Index", "body": "index-body", "aliases": ("library",)},
)


def _glossary_leaf_shown(v: dict) -> bool:
    """A leaf is in the strip when it is listed and, for an outbound leaf, its
    page is built (the page's index.html exists under the module root)."""
    if v.get("listed", True) is False:
        return False
    href = v.get("href")
    return not href or (ROOT / href.strip("/") / "index.html").is_file()


def _glossary_strip(active: str = "terms") -> str:
    """The Library's two-row strip: the shelf chips (each with its count of
    leaves in the strip), then one leaf row per shelf with only the active
    shelf's row shown. The active leaf carries aria-current="page" and the
    active shelf aria-current="true"; assets/glossary.js moves both. An
    outbound leaf is a link with the trailing arrow, never a toggle."""
    views = {v["id"]: v for v in GLOSSARY_VIEWS}
    cur_shelf = views[active]["shelf"]
    shelves, rows = [], []
    for sid, slabel in GLOSSARY_SHELVES:
        leaves = [v for v in GLOSSARY_VIEWS if v["shelf"] == sid]
        n = sum(1 for v in leaves if _glossary_leaf_shown(v))
        on = sid == cur_shelf
        shelves.append(
            f'<button class="chip gl-shelf-chip{" active" if on else ""}" type="button"'
            f'{" aria-current=" + chr(34) + "true" + chr(34) if on else ""} data-gl-shelf-chip="{sid}">'
            f'<span class="gl-shelf-name">{html.escape(slabel)}</span>'
            f'<span class="gl-shelf-n">{n}</span></button>')
        chips = []
        for v in leaves:
            label = html.escape(v["label"])
            if v.get("href"):
                if _glossary_leaf_shown(v):
                    chips.append(f'<a class="chip gl-chip-out" href="{v["href"]}"'
                                 f' data-gl-leaf="{v["id"]}">{label} →</a>')
                continue
            cur = v["id"] == active
            unlisted = v.get("listed", True) is False
            chips.append(
                f'<button class="chip{" active" if cur else ""}" type="button"'
                f'{(" data-gl-unlisted" + ("" if cur else " hidden")) if unlisted else ""}'
                f'{" aria-current=" + chr(34) + "page" + chr(34) if cur else ""}'
                f' data-gl-shelf="{sid}" data-glossary-view="{v["id"]}">{label}</button>')
        rows.append(
            f'<div class="gl-strip-row gl-leaves" role="group" aria-label="{html.escape(slabel)}"'
            f' data-gl-leaves="{sid}"{"" if on else " hidden"}>{"".join(chips)}</div>')
    return (f'<nav class="gl-strip" aria-label="{html.escape(GLOSSARY_DISPLAY_NAME)} sections">'
            '<div class="gl-strip-row gl-shelves" role="group" aria-label="Shelves">'
            f'{"".join(shelves)}</div>{"".join(rows)}</nav>')


def _glossary_bodies(active: str = "terms") -> str:
    """One container per in-page view, from GLOSSARY_VIEWS. Every container
    but the default view's ships hidden so the client router owns visibility;
    the Terms rows come last, under the search bar."""
    out, last = [], ""
    for v in GLOSSARY_VIEWS:
        if not v.get("body"):
            continue
        if v["id"] == active:
            last = f'<div id="{v["body"]}"></div>'
        else:
            out.append(f'<div id="{v["body"]}" style="display:none;"></div>')
    return "".join(out) + last


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
    # The module's display name from NAV_ITEMS rides on the app root, so the
    # client labels a section with the module's current name, never a literal.
    _gl_name = next(lbl for key, lbl, _ in nav_leaves() if key == "glossary")
    body = (
        f'<div class="gl-app" data-module-name="{html.escape(_gl_name)}"'
        f' data-display-name="{html.escape(GLOSSARY_DISPLAY_NAME)}">'
        f'<div class="section-head"><h1>{_masthead_icon("glossary")}{GLOSSARY_DISPLAY_NAME}</h1>'
        '<span class="section-sub">terms, derivations, and each model\'s track record</span></div>'
        f"{intro}"
        f"{_glossary_strip()}"
        '<div id="gl-termbar">'
        '<input id="gl-search" class="gl-search" type="search" placeholder="Search terms, abbreviations, definitions…"'
        f' aria-label="Search {html.escape(GLOSSARY_DISPLAY_NAME)} terms">'
        '<div class="filter-bar" id="gl-cats"></div>'
        '<div id="gl-prov" role="group" aria-label="Provenance"></div>'
        '<div id="gl-az"></div>'
        '</div>'
        f"{_glossary_bodies()}"
        # The Page Index rows, generated (LIBRARY_8): see page_index_groups().
        f"{_page_index_data()}"
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
    return page(f"{GLOSSARY_DISPLAY_NAME} - eephus.io", "glossary", body,
                f"The eephus.io {GLOSSARY_DISPLAY_NAME}: definitions, model mechanics and "
                "methodology for every metric on the site, with each model's track record.",
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

TEAM_JSON = DATA_DIR / "team.json"
# How many credit badges the card FRONT shows before the rest fold behind a
# "+N" control that turns the card over (the back carries every credit).
TEAM_FRONT_BADGES = 10


def _load_team() -> dict:
    """data/team.json, the Masthead roster (owner decisions TEAM-1 to TEAM-7,
    2026-10-02): groups, the badge catalogue and one entry per member. A data
    edit adds a writer or a credit; nothing about a person is typed here."""
    return json.loads(TEAM_JSON.read_text(encoding="utf-8"))


def _watermark_counts() -> dict:
    """{watermark: tracked source files whose copyright header carries it}.

    Read off the tree at build time (team_facts.watermark_files: git ls-files
    over the WHOLE repository, then the first 300 bytes of each .py / .js /
    .css), so the count on a card back is derived rather than typed. Whole
    repository since TEAM_2 (2026-10-02): Will Cahoon's marked files sit in
    the sibling model trees, and a count of this module alone read 2 of his
    215. Empty when git is unavailable: the card then prints the mark without
    a count."""
    import team_facts
    return team_facts.watermark_counts()


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p[:1].isalpha()]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][1:2])).upper()


# Social marks on a card back: third-party brand glyphs, drawn as given (the
# pixel set never redraws a third-party mark), riding currentColor.
_SOC_SVG = {
    "x": ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 '
          '8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 '
          '17.52h1.833L7.084 4.126H5.117z"/></svg>'),
    "linkedin": ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 '
                 '0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 '
                 '5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 '
                 '0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>'),
    "web": ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm7.93 '
            '9h-3.46a15.6 15.6 0 0 0-1.21-5.07A8.03 8.03 0 0 1 19.93 11zM12 4.06c.93 1.28 1.85 3.7 2.16 '
            '6.94H9.84c.31-3.24 1.23-5.66 2.16-6.94zM4.07 13h3.46c.18 1.85.6 3.6 1.21 5.07A8.03 8.03 0 0 1 4.07 '
            '13zm3.46-2H4.07a8.03 8.03 0 0 1 4.67-5.07A15.6 15.6 0 0 0 7.53 11zM12 19.94c-.93-1.28-1.85-3.7-2.16-6.94h4.32c-.31 '
            '3.24-1.23 5.66-2.16 6.94zm3.26-1.87c.61-1.47 1.03-3.22 1.21-5.07h3.46a8.03 8.03 0 0 1-4.67 5.07z"/></svg>'),
    "github": ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 '
               '9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 '
               '18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 '
               '2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 '
               '1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 '
               '2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 '
               '3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 '
               '22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>'),
    "mail": ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 '
             '2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z"/></svg>'),
}


def _team_socials(m: dict) -> str:
    f = m.get("front") or {}
    name = html.escape(m["name"])
    chips = []

    def chip(href: str, label: str, key: str, external: bool = True) -> None:
        tgt = ' target="_blank" rel="noopener noreferrer"' if external else ""
        chips.append(f'<a class="tc-soc" href="{html.escape(href)}"{tgt} title="{html.escape(label)}" '
                     f'aria-label="{html.escape(label)}">{_SOC_SVG[key]}</a>')

    handle = (f.get("handle") or "").lstrip("@")
    if handle:
        chip(f"https://x.com/{handle}", f"X: @{handle}", "x")
    linkedin = (f.get("linkedin") or "").strip().rstrip("/").rsplit("/", 1)[-1]
    if linkedin:
        chip(f"https://www.linkedin.com/in/{linkedin}/", f"LinkedIn: {m['name']}", "linkedin")
    email = (f.get("email") or "").strip()
    if email:
        chip(f"mailto:{email}", f"Email: {email}", "mail", external=False)
    website = (f.get("website") or "").strip()
    if website:
        chip(website, f"Website: {website.split('//', 1)[-1].strip('/')}", "web")
    github = (f.get("github") or "").strip().rstrip("/").rsplit("/", 1)[-1]
    if github:
        chip(f"https://github.com/{github}", f"GitHub: {github}", "github")
    if not chips:
        return ""
    return f'<div class="tc-socials" aria-label="{name}: profiles">{"".join(chips)}</div>'


def _team_card_number(group: dict, order: int) -> str:
    return f'{group.get("number_prefix", "")}{order:02d}'


def _team_card(m: dict, group: dict, team: dict) -> str:
    """One Masthead card in the PROSPX player-card idiom (TEAM-7): a 2.5 by 3.5
    front with the photo window, the name plate, the role as the position line,
    the group as the team line, the card number and the credit badges as the
    stats line; a card back with the stat table of every credit, the record
    lines and the set name. The owner's card (owner: true, exactly one) wears
    the set's one legendary foil edge and the founder plate (TEAM-3)."""
    key = m["key"]
    name = m["name"]
    e_name = html.escape(name)
    no = _team_card_number(group, int(m["order"]))
    owner = bool(m.get("owner"))
    catalogue = team["badges"]
    credits = team.get("credits", {})
    badges = [b for b in (m.get("badges") or []) if b.get("key") in catalogue]

    def badge_label(b: dict) -> tuple[str, str]:
        return catalogue[b["key"]]["label"], credits.get(b.get("credit", ""), "")

    # ---- front
    photo = m.get("photo")
    if photo and not (ROOT / photo.lstrip("/")).exists():
        photo = None
    mono = f'<span class="tc-mono" aria-hidden="true">{html.escape(_initials(name))}</span>'
    img = (f'<img src="{html.escape(photo)}" alt="{e_name}" width="600" height="600" loading="lazy" '
           f'onerror="this.remove()">') if photo else ""
    plate = (f'<span class="tc-plate">{_ico("b-founder", 12)}<span>Owner and founder</span></span>'
             if owner else "")
    pos = html.escape(m.get("role") or "")
    if m.get("role_extra"):
        pos += " · " + html.escape(m["role_extra"])
    shown = badges if len(badges) <= TEAM_FRONT_BADGES + 1 else badges[:TEAM_FRONT_BADGES]
    rest = len(badges) - len(shown)
    chips = []
    for b in shown:
        label, credit = badge_label(b)
        tip = f"{label}: {credit}" if credit else label
        chips.append(f'<li class="tc-badge" data-badge="{html.escape(b["key"])}" title="{html.escape(tip)}">'
                     f'{_ico(catalogue[b["key"]]["icon"], 16)}'
                     f'<span class="visually-hidden">{html.escape(tip)}</span></li>')
    more = (f'<button class="tc-more" type="button" data-flip="back" '
            f'aria-label="{rest} more credits on the back of {e_name}\'s card">+{rest}</button>'
            if rest else "")
    stats = (f'<div class="tc-stats"><ul class="tc-badges" aria-label="{e_name}: credits">{"".join(chips)}</ul>'
             f'{more}</div>') if chips else '<div class="tc-stats"></div>'
    group_line = f'{_ico(group.get("icon") or "team", 12)}<span>{html.escape(group["label"])}</span>'
    # ---- back
    rows = []
    for b in badges:
        label, credit = badge_label(b)
        rows.append(f'<tr data-badge="{html.escape(b["key"])}"><td>{_ico(catalogue[b["key"]]["icon"], 12)}'
                    f'<span>{html.escape(label)}</span></td><td>{html.escape(credit)}</td></tr>')
    table = ('<table class="tc-table"><caption class="visually-hidden">'
             f'{e_name}: modules and systems</caption>'
             '<thead><tr><th scope="col">Module or system</th><th scope="col">Credit</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table>') if rows else ""
    # The record (TEAM_2, 2026-10-02): loose lines under 'Record', or the
    # owner's resume groups; {{tokens}} are filled from the repository by
    # team_facts, and a line whose source is missing is left off.
    import team_facts
    bio = "".join(
        f'<h4 class="tc-back-h">{html.escape(head)}</h4><ul class="tc-bio">'
        + "".join(f"<li>{html.escape(ln)}</li>" for ln in lines) + "</ul>"
        for head, lines in team_facts.back_groups(m))
    vitals = []
    school = ((m.get("front") or {}).get("school") or "").strip()
    if school:
        vitals.append(f"<dt>School</dt><dd>{html.escape(school)}</dd>")
    mark = m.get("watermark")
    if mark:
        n = _watermark_counts().get(mark)
        files = f", {n:,} source file{'s' if n != 1 else ''}" if n else ""
        vitals.append(f"<dt>Code mark</dt><dd>{html.escape(mark)}{files}</dd>")
    vit = f'<dl class="tc-vitals">{"".join(vitals)}</dl>' if vitals else ""
    back_body = f'{table}{bio}{vit}{_team_socials(m)}'
    # REDESIGN_home_shell (2026-10-07): a member with nothing for the back
    # (no credit, no record line, no vitals, no link) gets a one-sided card:
    # no back face and no turn control, never a back that only says the
    # record is to come. team.js skips .no-back cards when it turns the set.
    has_back = bool(back_body)
    flip = (f'<button class="tc-btn tc-flipbtn" type="button" data-flip="back" '
            f'aria-label="Turn {e_name}\'s card to the back">{_ico("b-flip", 12)}<span>Back</span></button>'
            if has_back else "")
    front = (
        '<div class="tc-face tc-front">'
        f'<div class="tc-top"><span class="tc-no">No. {no}</span>'
        f'<span class="tc-set">{html.escape(team.get("set", ""))}</span></div>'
        f'<div class="tc-photo">{mono}{img}{plate}</div>'
        f'<div class="tc-nameplate"><h3 class="tc-name">{e_name}</h3></div>'
        f'<p class="tc-pos">{pos}</p>'
        f'<p class="tc-team">{group_line}</p>'
        f'{stats}'
        '<div class="tc-foot">'
        f'{flip}'
        f'<button class="tc-btn tc-gfx" type="button" data-gfx hidden '
        f'aria-label="Share {e_name}\'s card as an image">Share</button>'
        '</div></div>'
    )
    back = (
        '<div class="tc-face tc-back">'
        f'<div class="tc-back-head"><span class="tc-no">No. {no}</span>'
        f'<span class="tc-back-name">{e_name}</span>'
        f'<span class="tc-back-pos">{pos}</span></div>'
        f'<div class="tc-back-body" tabindex="0" role="region" aria-label="{e_name}: credits and record">'
        f'{back_body}</div>'
        '<div class="tc-foot">'
        f'<span class="tc-setname">{html.escape(team.get("set", ""))} · No. {no}</span>'
        f'<button class="tc-btn tc-flipbtn" type="button" data-flip="front" '
        f'aria-label="Turn {e_name}\'s card to the front">{_ico("b-flip", 12)}<span>Front</span></button>'
        '</div></div>'
    ) if has_back else ""
    cls = "tc-card" + (" is-owner" if owner else "") + ("" if has_back else " no-back")
    badge_keys = ",".join(b["key"] for b in badges)
    return (f'<li class="tc-slot"><article class="{cls}" id="member-{html.escape(key)}" '
            f'data-member="{html.escape(key)}" data-no="{no}" data-badges="{html.escape(badge_keys)}" '
            f'aria-label="{e_name}, card {no}">'
            f'<div class="tc-inner">{front}{back}</div></article></li>')


def _team_placeholder(group: dict, team: dict) -> str:
    """The 'to be named' face for a group with no members yet, on the same
    card template, carrying the group's honest empty state through the state
    component (no invented names)."""
    no = _team_card_number(group, 1)
    state = _px_state("empty", html.escape(group.get("empty") or ""), "tc-state")
    return (
        '<li class="tc-slot"><article class="tc-card is-unnamed" '
        f'aria-label="{html.escape(group["label"])}: to be named">'
        '<div class="tc-inner"><div class="tc-face tc-front">'
        f'<div class="tc-top"><span class="tc-no">No. {no}</span>'
        f'<span class="tc-set">{html.escape(team.get("set", ""))}</span></div>'
        f'<div class="tc-photo">{state}</div>'
        '<div class="tc-nameplate"><h3 class="tc-name">To be named</h3></div>'
        f'<p class="tc-team">{_ico(group.get("icon") or "team", 12)}'
        f'<span>{html.escape(group["label"])}</span></p>'
        '</div></div></article></li>'
    )


def build_team() -> str:
    """/team/ - the Masthead (owner decisions TEAM-1 to TEAM-7, 2026-10-02).

    The site's staff page and the one place attribution lives: the 'Created by'
    byline that sat on every module masthead is gone (TEAM-2). Two groups,
    Developers and Writers and Analysts, each a set of baseball cards ordered
    by the data file's order field (TEAM-6), every member and every credit read
    from data/team.json. Layout chosen: the cards stay, as trading cards (front
    first; the full credit table and the record on the back), because a card
    front reads at 390 and 1280 alike and the back holds the long record
    without crowding the grid. assets/team.js turns the cards (whole-pixel
    steps), remembers the set-wide 'show the backs' choice per viewer, and
    hands one card to the GFX engine as a 2x PNG."""
    team = _load_team()
    groups = sorted(team["groups"], key=lambda g: g.get("order", 0))
    members = team["members"]
    sections = []
    for g in groups:
        mine = sorted((m for m in members if m.get("group") == g["key"]), key=lambda m: m["order"])
        cards = "".join(_team_card(m, g, team) for m in mine) if mine else _team_placeholder(g, team)
        count = (f'{len(mine)} card{"s" if len(mine) != 1 else ""}' if mine else "to be named")
        gid = f'tc-g-{html.escape(g["key"])}'
        sections.append(
            f'<section class="tc-group" data-group="{html.escape(g["key"])}" aria-labelledby="{gid}">'
            f'<h2 class="tc-group-head" id="{gid}">{_ico(g.get("icon") or "team", 16)}'
            f'<span>{html.escape(g["label"])}</span><span class="tc-group-count">{count}</span></h2>'
            f'<ol class="tc-grid">{cards}</ol></section>'
        )
    follow = (
        '<div class="team-follow"><span class="team-follow-label">Follow</span>'
        f'{_x_link("eephus_io")}{_x_link("MLBPROSPX")}{_discord_link()}</div>'
    )
    # A set with no card back (every member one-sided) drops the turn line
    # and the 'Show card backs' toggle with it (REDESIGN_home_shell).
    any_back = any('tc-face tc-back' in s for s in sections)
    turn_line = " Turn a card over for the full record." if any_back else ""
    mission = (
        f'<p class="team-mission">The people who build, run and write eephus.io. Every module and '
        'system on the site carries its builder&#39;s badge here, and this page is the only place '
        f'the site keeps its credits.{turn_line}</p>'
        '<p class="team-mission">Building on the data? Every model artifact is public JSON, '
        'catalogued on <a href="/sources/#api">the public data page</a>.</p>'
    )
    toolbar = (
        '<div class="tc-toolbar"><button class="tc-btn tc-flipall" type="button" aria-pressed="false">'
        f'{_ico("b-flip", 16)}<span>Show card backs</span></button></div>'
    ) if any_back else ""
    body = (
        f'<div class="section-head"><h1>{_masthead_icon("team")}Masthead</h1>'
        '<span class="section-sub">who builds, runs and writes the site</span></div>'
        f'{mission}{follow}{toolbar}'
        f'<div class="tc-set-wrap" data-set="{html.escape(team.get("set", ""))}">{"".join(sections)}</div>'
        f'<link rel="stylesheet" href="/assets/team.css?v={_TEAM_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/team.js?v={_TEAM_VER}" defer></script>'
    )
    return page("Masthead - eephus.io", "team", body,
                "The people who build, run and write eephus.io: the developers and the writers "
                "and analysts, with every module and system credited to the person who built it.",
                url=f"{SITE_ORIGIN}/team/")


# --------------------------------------------------------------------------- #
# /teams/ - RETIRED standalone module (merged into MLB Projections
# 2026-06-12). The org-dashboard columns (farm rank/score, farm surplus,
# top prospect, cross-module links) now ride the Team Outlook view's
# baked farm blocks (proj_export._org_farm_blocks). The URL stays alive
# through the 404 page's redirect map (RETIRED_ROUTES) so bookmarks and
# external links keep working.
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
            f'<details class="src-fold"><summary>Show the {n} file{"" if n == 1 else "s"}</summary>'
            f'<div class="article-grid">{cards}</div></details>')
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


# /sources/ table and folds. Scoped here rather than in assets/site.css (a
# shared file other lanes edit); every colour is a theme token.
_SOURCES_STYLE = (
    '<style>'
    '.src-table-wrap{overflow-x:auto;margin:0 0 16px;}'
    '.src-table{width:100%;border-collapse:collapse;font-size:13px;line-height:1.45;}'
    '.src-table th,.src-table td{padding:8px 10px;border-bottom:1px solid var(--border-light);'
    'text-align:left;vertical-align:top;}'
    '.src-table thead th{font-family:var(--font-retro-mono);font-size:10px;font-weight:700;'
    'letter-spacing:.04em;text-transform:uppercase;color:var(--text-tertiary);}'
    '.src-table tbody th{font-weight:700;white-space:nowrap;}'
    '.src-table td{color:var(--text-secondary);}'
    '.src-table .src-none{color:var(--text-tertiary);}'
    '.src-fold{margin:0 0 20px;}'
    '.src-fold>summary{cursor:pointer;padding:10px 0;color:var(--text-secondary);font-size:13px;}'
    '.src-fold[open]>summary{margin-bottom:8px;}'
    '@media (max-width:640px){.src-table{font-size:12px;}.src-table th,.src-table td{padding:8px 6px;}'
    '.src-table tbody th{white-space:normal;}}'
    '</style>'
)


def _source_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# The upstreams /sources/ credits, one dict per source (REDESIGN_home_shell,
# 2026-10-07). The table at the top of the page and the per-source notes under
# it both read this list, so adding or retiring a source is one edit here.
# take and cadence are the short table cells (cadence from the pipeline phases
# in DATA_SOURCES.md); use is the full note; terms is the publisher's own terms,
# licence or copyright page, opened on 2026-10-07, or None where we could not
# open one (no link on the home page, or the site refuses scripted requests).
# test_sources_attribution.py holds every ingest host to a row here (census
# X07-08, 2026-09-25, added MLB Trade Rumors, The Odds API and Open-Meteo).
SOURCE_ROWS = [
    {"name": "FanGraphs", "url": "https://www.fangraphs.com/",
     "take": "Rankings, FV and tool grades, reports; league stats, park factors",
     "cadence": "Monthly (CSV drops)",
     "terms": "https://www.fangraphs.com/about/terms-of-service", "terms_label": "Terms",
     "use": ("Prospect rankings, FV grades, tool grades, and prospect and draft scouting reports "
             "(one of the seven PROSPX consensus inputs); league stats and park factors.")},
    {"name": "MLB Pipeline", "url": "https://www.mlb.com/prospects",
     "take": "Rankings, grades, reports; draft pools and slot values",
     "cadence": "Daily",
     "terms": "https://www.mlb.com/official-information/terms-of-use", "terms_label": "Terms",
     "use": ("Prospect rankings, grades, and prospect and draft scouting reports (consensus "
             "input); draft bonus pools and slot values.")},
    {"name": "Baseball America", "url": "https://www.baseballamerica.com/",
     "take": "Rankings, grades, reports",
     "cadence": "Each published list",
     "terms": None, "terms_label": None,
     "use": ("Prospect rankings, grades, and prospect and draft scouting reports (consensus input).")},
    {"name": "ESPN", "url": "https://www.espn.com/mlb/",
     "take": "Rankings, reports; club logo images",
     "cadence": "Each published list",
     "terms": "https://disneytermsofuse.com/english/", "terms_label": "Terms",
     "use": ("Prospect rankings and scouting reports (consensus input); the club logo images "
             "on team pickers and boards load from ESPN's image server (the logos are the "
             "clubs' trademarks).")},
    {"name": "The Athletic", "url": "https://www.nytimes.com/athletic/",
     "take": "Rankings",
     "cadence": "Each published list",
     "terms": None, "terms_label": None,
     "use": ("Prospect rankings (consensus input).")},
    {"name": "Just Baseball", "url": "https://www.justbaseball.com/",
     "take": "Rankings, reports",
     "cadence": "Daily",
     "terms": None, "terms_label": None,
     "use": ("Prospect rankings and scouting reports (consensus input).")},
    {"name": "TJStats", "url": "https://x.com/TJStats",
     "take": "Rankings, movers wire",
     "cadence": "Daily",
     "terms": "https://x.com/en/tos", "terms_label": "Terms (X)",
     "use": ("Prospect rankings (consensus input) and movers wire.")},
    {"name": "MLB Stats API / Baseball Savant", "url": "https://baseballsavant.mlb.com/",
     "take": "Game logs, transactions, rosters, Statcast, headshots; live scores and video",
     "cadence": "Daily; live during games",
     "terms": "http://gdx.mlb.com/components/copyright.txt", "terms_label": "Copyright notice",
     "use": ("Game logs, transactions, rosters, the sabermetrics feed (league wOBA constants; the "
             "fielding and framing runs behind DEM+), Statcast tracking data (pitch, batted-ball "
             "and zone metrics), and player headshots via MLB static media; on the Scores / "
             "Standings page, live scores, win probability, box scores and highlight video "
             "played in MLB's own embedded player.")},
    {"name": "Baseball-Reference", "url": "https://www.baseball-reference.com/",
     "take": "war_daily (bWAR), historical player pages",
     "cadence": "Daily",
     "terms": "https://www.sports-reference.com/termsofuse.html", "terms_label": "Terms",
     "use": ("war_daily (bWAR): the run frame the served eWAR is built on and the source the Hall "
             "of Fame board reproduces, plus historical player pages.")},
    {"name": "pybaseball", "url": "https://github.com/jldbc/pybaseball",
     "take": "The Python toolkit behind the Statcast, FanGraphs and Baseball-Reference pulls",
     "cadence": "With those pulls",
     "terms": "https://github.com/jldbc/pybaseball/blob/master/LICENSE", "terms_label": "License (MIT)",
     "use": ("Open-source Python toolkit used to pull Statcast, FanGraphs, and "
             "Baseball-Reference data programmatically.")},
    {"name": "Spotrac", "url": "https://www.spotrac.com/",
     "take": "Contracts, payrolls, free-agent classes, international signings",
     "cadence": "Monthly",
     "terms": None, "terms_label": None,
     "use": ("Contracts, payrolls, free-agent classes, and international signing trackers.")},
    {"name": "MLB Trade Rumors", "url": "https://www.mlbtraderumors.com/",
     "take": "Arbitration projections and results (comparator)",
     "cadence": "By hand, cached",
     "terms": None, "terms_label": None,
     "use": ("Arbitration salary projections (Matt Swartz's model) and the arbitration "
             "results tracker: the comparator /arbitration/ scores its own model against, "
             "and a record of settled salaries the arbitration dataset reads.")},
    {"name": "The Odds API", "url": "https://the-odds-api.com/",
     "take": "Moneylines, run lines, totals",
     "cadence": "Daily (open and close)",
     "terms": "https://the-odds-api.com/terms-and-conditions.html", "terms_label": "Terms",
     "use": ("Sportsbook moneylines, run lines and totals for the /betting/ board, and the "
             "game lines /fantasy/ DFS pricing reads.")},
    {"name": "Open-Meteo", "url": "https://open-meteo.com/",
     "take": "Game-time weather forecasts (not shown yet)",
     "cadence": "Nightly",
     "terms": "https://open-meteo.com/en/terms", "terms_label": "Terms",
     "use": ("Game-time weather forecasts, captured nightly for a pre-registered betting "
             "candidate; no page shows them yet. Weather data by Open-Meteo.com (CC BY 4.0).")},
]


def build_sources() -> str:
    """/sources/ - data sources and attribution, plus the published-data catalog.

    Trust page for the Open Beta: names every upstream the platform reads, what
    it's used for, and the editorial stance (consensus across sources; the lede
    names whose report excerpts the cards carry). The second half (anchor #api) is the other direction of
    the same question: which artifacts the platform PUBLISHES, on what cadence,
    and how stable each one is. See _sources_api_section for why the catalog
    lives on this route."""
    def _terms(s: dict) -> str:
        if not s.get("terms"):
            return '<span class="src-none">none linked</span>'
        return (f'<a href="{html.escape(s["terms"])}" target="_blank" rel="noopener noreferrer">'
                f'{html.escape(s.get("terms_label") or "Terms")}</a>')

    trs = "".join(
        f'<tr><th scope="row"><a href="#src-{_source_slug(s["name"])}">{html.escape(s["name"])}</a></th>'
        f'<td>{html.escape(s["take"])}</td><td>{html.escape(s["cadence"])}</td>'
        f'<td>{_terms(s)}</td></tr>'
        for s in SOURCE_ROWS)
    table = (
        '<div class="src-table-wrap"><table class="src-table">'
        '<caption class="visually-hidden">Data sources: what we take, how often, and the '
        'publisher&#39;s terms</caption>'
        '<thead><tr><th scope="col">Source</th><th scope="col">What we take</th>'
        '<th scope="col">Cadence</th><th scope="col">Terms</th></tr></thead>'
        f'<tbody>{trs}</tbody></table></div>')
    cards = "".join(
        f'<div class="card source-card" id="src-{_source_slug(s["name"])}"><h3><a href="{html.escape(s["url"])}" '
        f'target="_blank" rel="noopener noreferrer">{html.escape(s["name"])}</a></h3>'
        f'<p>{html.escape(s["use"])}</p></div>'
        for s in SOURCE_ROWS
    )
    body = (
        '<div class="section-head"><h1>Data: sources, attribution and what we publish</h1>'
        '<span class="section-sub">upstreams we read, artifacts we publish</span></div>'
        # The table leads (REDESIGN_home_shell); the attribution lede follows it.
        '<div class="section-head"><h2>Where the data comes from</h2>'
        f'<span class="section-sub">{len(SOURCE_ROWS)} sources</span></div>'
        f'{_SOURCES_STYLE}{table}'
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
        '<details class="src-fold" id="src-notes"><summary>What each source supplies, in full</summary>'
        f'<div class="article-grid">{cards}</div></details>'
        f'{_sources_api_section()}'
        # A link into a folded block (#src-<source> from the table, or an old
        # deep link) opens the fold it lands in.
        '<script>(function(){function o(){try{var h=location.hash.slice(1);if(!h)return;'
        'var e=document.getElementById(h);var d=e&&e.closest("details");'
        'if(d&&!d.open){d.open=true;e.scrollIntoView();}}catch(x){}}'
        'window.addEventListener("hashchange",o);'
        'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",o);else o();})();</script>'
    )
    return page("Data Sources, Attribution & the Public Data - eephus.io", "", body,
                "Every data source behind eephus.io - prospect ranking inputs, Statcast and "
                "league data, contracts - plus the catalog of public JSON artifacts the site "
                "publishes, their update cadence and how stable each one is.",
                url=f"{SITE_ORIGIN}/sources/")


def build_bug_report() -> str:
    """/report/ - the "Report a bug" destination linked from every footer.

    A plain page (REDESIGN_home_shell, 2026-10-07): the address and what to
    put in the message. The Google Form embed it once waited for was never
    configured, so the page served an empty form shell; there is no form
    here now, and a form, if one comes, is a new decision rather than a
    constant left blank."""
    include = (
        ("The page", "the address in the bar, or the module and tab."),
        ("The steps", "what you clicked or typed, in order, and what you expected to see."),
        ("What you saw", "the wrong number, the error message, or a screenshot."),
        ("Your browser", "its name and version, and the device or screen width."),
    )
    items = "".join(f"<li><strong>{html.escape(k)}</strong>: {html.escape(v)}</li>"
                    for k, v in include)
    body = (
        '<div class="section-head"><h1>Report a bug</h1>'
        '<span class="section-sub">tell us what broke and where</span></div>'
        '<div class="card report-plain">'
        '<p>Email <a href="' + FEEDBACK_MAILTO + '">arkndjl@gmail.com</a> with:</p>'
        f'<ul style="margin:8px 0;padding-left:20px;line-height:1.6;">{items}</ul>'
        '<p>One bug per message keeps each one easy to track.</p>'
        '</div>'
    )
    return page("Report a bug - eephus.io", "", body,
                "Report a bug on eephus.io - tell us what happened and which section "
                "it is in.",
                url=f"{SITE_ORIGIN}/report/")


# Retired addresses forwarded by the 404 page (owner answer LB-Q3, 2026-10-02;
# built 2026-10-07). Each was a redirect folder of its own with no link from
# the site: /teams/ since 2026-06-12, /dfs/, /dynasty/ and /redraft/ since
# 2026-08-07. The box answers every missing path with 404.html
# (`error_page 404 /404.html;`), so the map below does what the four folders
# did. Value: (target, carry_hash). carry_hash False drops the incoming hash,
# as the /teams/ folder did; True carries it the way the fantasy folders did:
# every m= pair is removed and the rest is appended after the target's own
# m=, so /redraft/#section=ros_sp&sys=sabr lands on
# /fantasy/#m=redraft&section=ros_sp&sys=sabr.
RETIRED_ROUTES = {
    "/teams/": ("/projections/#view=teams", False),
    "/dfs/": ("/fantasy/#m=dfs", True),
    "/dynasty/": ("/fantasy/#m=dynasty", True),
    "/redraft/": ("/fantasy/#m=redraft", True),
}


def _retired_routes_script() -> str:
    """The inline redirect the 404 page runs first, written from
    RETIRED_ROUTES. The path matches with and without the trailing slash and
    with index.html; any other path renders the not-found page."""
    table = json.dumps({p: [t, 1 if carry else 0]
                        for p, (t, carry) in RETIRED_ROUTES.items()},
                       separators=(",", ":"))
    return (
        "<script>(function(){var R=" + table + ";"
        'var p=location.pathname.replace(/index\\.html$/,"");'
        'if(p.charAt(p.length-1)!=="/")p+="/";'
        "if(!Object.prototype.hasOwnProperty.call(R,p))return;"
        "var t=R[p][0];"
        'if(R[p][1]){var h=(location.hash||"").replace(/^#/,"")'
        '.replace(/(^|&)m=[^&]*/g,"").replace(/^&+/,"");if(h)t+="&"+h;}'
        "location.replace(t);})();</script>"
    )


def build_404() -> str:
    """The not-found page (nginx: `error_page 404 /404.html;`). On-theme,
    no dead ends: home link + the module rail + the palette hint. The rail is
    read off nav_leaves() so a module added to NAV_ITEMS lands here too (the
    hand-typed list had stopped at seven modules and missed ten). A retired
    address in RETIRED_ROUTES forwards before the page paints: the redirect
    script is the first thing in <head>."""
    rail = "".join(f'<a href="{h}">{html.escape(l)}</a>'
                   for k, l, h in nav_leaves() if k != "home")
    body = (
        '<div class="section-head"><h1>404: page not found</h1>'
        '<span class="section-sub">it does not exist, or it moved</span></div>'
        f'<div class="px-404">{_PX_404_ART}</div>'
        '<div class="gl-intro">'
        f'<nav class="px-404-rail" aria-label="Modules"><a href="/">Home</a>{rail}</nav>'
        '<p>Player search: <strong>Ctrl+K</strong> (⌘K on Mac).</p>'
        '</div>'
    )
    out = page("Page not found - eephus.io", "", body,
               "Page not found on eephus.io.", robots="noindex")
    return out.replace("<head>\n", "<head>\n" + _retired_routes_script() + "\n", 1)


def build_robots() -> str:
    """robots.txt - crawl everything except the data payloads (multi-MB JSON
    sidecars are for the apps, not crawlers) and the resolver stubs."""
    return (
        "User-agent: *\n"
        "Disallow: /data/\n"
        "Disallow: /player/\n"
        "Allow: /\n"
        f"Sitemap: {SITE_ORIGIN}/sitemap.xml\n"
    )


def sitemap_pages() -> list[tuple]:
    """The canonical public surfaces as (path, changefreq, priority): the one
    page list sitemap.xml and the Library's Page Index both read."""
    return [
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
        ("/scores/", "hourly", "0.8"),
        # /dynasty/, /redraft/ and /dfs/ are retired addresses the 404 page
        # forwards into /fantasy/ (RETIRED_ROUTES), so they are deliberately
        # absent here (same treatment as /teams/). Their content is one
        # crawlable page.
        ("/fantasy/", "daily", "0.8"),
        ("/betting/", "daily", "0.8"),
        ("/diamond/", "monthly", "0.6"),
        ("/parks/", "weekly", "0.6"),
        ("/hof/", "weekly", "0.6"),
        ("/management/", "weekly", "0.6"),
        ("/models/", "daily", "0.6"),
        ("/models/updates/", "daily", "0.6"),
        ("/articles/", "weekly", "0.7"),
        ("/forums/", "daily", "0.6"),
        ("/glossary/", "weekly", "0.7"),
        ("/sources/", "monthly", "0.3"),
        ("/team/", "monthly", "0.3"),
        ("/report/", "monthly", "0.2"),
    ]


def build_sitemap(articles: list[dict]) -> str:
    """sitemap.xml over the canonical public surfaces. lastmod is the build
    date for app pages (data refreshes nightly) and the article date for
    articles."""
    today = date.today().isoformat()
    urls = []
    for path, freq, prio in sitemap_pages():
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


# --------------------------------------------------------------------------- #
# The Library's Page Index (LIBRARY_8, 2026-10-07). The view used to be a hand
# list in assets/glossary.js that called itself every page with its own address
# and had missed 14 module roots. Its rows are now written here at build time:
# the full pages from NAV_ITEMS and sitemap_pages(), the in-module views from
# PAGE_INDEX_VIEWS (each checked against its module's router by
# test_page_index), the player cards as before. A page with no purpose line
# prints an empty cell and fails test_page_index, so a page added to the
# sitemap without a row cannot pass.
# --------------------------------------------------------------------------- #

# Names for the sitemap pages that have no top-bar entry (a top-bar page takes
# its NAV_ITEMS label).
PAGE_INDEX_NAMES = {
    "/news/": "MLB News",
    "/history/": "Today in Prospect History",
    "/collegesavant/pitcher_index.html": "CollegeSavant Pitchers",
    "/parks/": "MiLB Park Factors",
    "/models/": "Model Accountability",
    "/models/updates/": "Model Updates",
    "/sources/": "Data Sources & Attribution",
    "/report/": "Report a bug",
}

# One line per page: what a reader finds there.
PAGE_INDEX_PURPOSE = {
    "/": "the front page, with a card for every module",
    "/prospx/": "the prospect board: eFV grades, consensus FV, surplus value and every list source",
    "/collegesavant/": "percentile profiles for college hitters: batted-ball quality, plate discipline and year-over-year change",
    "/collegesavant/pitcher_index.html": "percentile profiles for college pitchers",
    "/franchise/": "one page per club: the Franchise Index and its three branches",
    "/scores/": "MLB scores by date: win probability, box scores and Stars of the Game",
    "/fa/": "the free-agent class: projected contracts, rational value against price, deal verdicts and team fits",
    "/projections/": "five-year WAR projections for every MLB player, with club-control surplus",
    "/mlbstats/": "MLB leaderboards: eWAR and the plus-stat boards, by season or year range",
    "/pal/": "role and position conversions: reliever to starter, starter to relief, position fit and pitch add",
    "/trademachine/": "value a trade in one currency: eFV surplus for prospects, projection surplus for MLB players",
    "/arbitration/": "projected arbitration salaries for every eligible player, and a per-season record of the market",
    "/ledger/": "each club's CBT payroll and contract commitments, from Spotrac and our own models",
    "/management/": "every in-game decision in the play corpus, with the win probability that moved after it",
    "/hof/": "career WAR, WAR7 and JAWS for every ten-season player, with the ballot record",
    "/fantasy/": "fantasy baseball: Redraft ranks in your league format, the Dynasty and keeper board, and the DFS slate",
    "/betting/": "game win probabilities against de-vigged book prices, with the flat-stake public record",
    "/diamond/": "the paid tier: what Diamond includes and what stays free",
    "/articles/": "long-form editorial pieces, newest first",
    "/forums/": "community discussion across prospects, farm systems and articles",
    "/glossary/": "terms, methods, evidence and sources; this index is one of its views",
    "/team/": "who builds, runs and writes the site: the one page that carries the credits",
    "/news/": "the full event wire: debuts, trades, promotions, IL moves, grade changes and FA signings",
    "/history/": "debut anniversaries, prospect trades, signings and IL moves that landed on today's calendar date",
    "/parks/": "run environments for every affiliated park; the Methodology tab (/parks/#method) documents the estimator",
    "/models/": "the model ledger: every model that makes a predictive claim, its verdict and the eval artifact behind it",
    "/models/updates/": "one row per model update: the scored statistic before and after, and the edge over the benchmark",
    "/sources/": "every upstream the site reads, what it is used for, and the public data catalog",
    "/report/": "how to report a bug and what to put in the message",
}

# Views inside a module that have their own address: (href, name, purpose).
# A None name on a /glossary/ row takes the view's label from GLOSSARY_VIEWS.
# PUBLIC ONLY: the dark previews (#tape=1, #cards=1) and the plain module
# leaderboards are deliberately not listed.
PAGE_INDEX_VIEWS = (
    ("/fa/#view=dpw", "FA · $/WAR by winter", "the full signings-implied price-of-a-win series and how it is estimated"),
    ("/fa/#view=tracker", "FA · Signing Tracker", "actual vs predicted contract for every signing"),
    ("/fa/#view=fits", "FA · Team Fits", "which clubs fit which free agents, component by component"),
    ("/fa/#view=archive", "FA · Archive", "past winters with realized WAR and realized surplus per signing"),
    ("/fa/#view=model", "FA · Model Accountability", "the FA market model held to its own record"),
    ("/projections/#view=teams", "Projections · Team Outlook", "club-level projected standings built from the player projections"),
    ("/projections/#view=accountability", "Projections · Accountability", "the projection engine scored against what happened"),
    ("/prospx/#tab=timemachine", "PROSPX · Time Machine", "the board as it stood at any past snapshot, or a diff of two dates"),
    ("/prospx/#tab=charts", "PROSPX · Scatterplots", "build-your-own X/Y charts across every prospect group"),
    ("/prospx/#tab=draft", "PROSPX · MLB Draft/HS", "draft boards, slots, bonuses, and High School Details"),
    ("/prospx/#tab=draft&dview=war-room", "PROSPX · Draft War Room", "pick-by-pick draft planning on the live board"),
    ("/prospx/#tab=farm", "PROSPX · Farm Systems", "org rankings and detail pages; each org page carries a Tendencies tab (development habits by org)"),
    ("/pal/#posfit=ladder", "Alchemy Lab · Positional Ladder", "the fielder-centred positional-fit ladder"),
    ("/pal/#rp2sp", "Alchemy Lab · RP to SP", "relievers with starter traits, ranked by conversion fit"),
    ("/pal/#sp2rp", "Alchemy Lab · SP to RP", "starters whose stuff plays up in relief"),
    ("/pal/#history", "Alchemy Lab · History", "past role conversions and how they went"),
    ("/pal/#pitchadd", "Alchemy Lab · Pitch Add", "which pitch each arm should add next"),
    ("/pal/#platoon", "Alchemy Lab · Platoon", "platoon-split profiles and pairings"),
    ("/pal/#prospects", "Alchemy Lab · Prospect Watch", "the pipeline read through the lab's conversion lenses"),
    ("/fantasy/#m=dynasty", "Fantasy · Dynasty", "the eFV-graded dynasty board, Call-up Watch and the keeper calculator"),
    ("/fantasy/#m=dfs", "Fantasy · DFS", "the day's slate with per-game projections and the lineup optimizer"),
    ("/glossary/#view=guide", None, "how to read a player card, the FV history chart and a farm-system page"),
    ("/glossary/#view=formulas", None, "every term that carries a formula, each linking its definition"),
    ("/glossary/#view=methodology", None, "how eFV, consensus FV, the Arkmetrics and the value framework are built"),
    ("/glossary/#view=source-comparison", None, "eFV against each prospect source on the same graduates"),
    ("/glossary/#view=source-accuracy", None, "which source grades which cohort better"),
    ("/glossary/#view=source-updates", None, "the dates each prospect outlet published a list or changed a live list, newest first, grouped by outlet"),
)

PAGE_INDEX_PLAYER_ROWS = (
    ("/prospx/#player=", "PROSPX prospect pages", "the full prospect card: grades, history, statlines, eFV explainers (append the player key)"),
    ("/projections/#player=", "MLB player cards", "projection cards for every MLB player (append the player key)"),
    ("/fa/#player=", "FA player cards", "contract projection and rational value for each free agent (append the player key)"),
)


def page_index_groups() -> list[dict]:
    """The Page Index rows, grouped: the top-bar pages in nav order, the other
    sitemap pages in sitemap order, the in-module views, the player cards.
    Each row is [href, name, purpose]."""
    nav = [(href, label) for key, label, href in nav_leaves()]
    nav_hrefs = {h for h, _ in nav}
    modules = [[h, label, PAGE_INDEX_PURPOSE.get(h, "")] for h, label in nav]
    reference = [[p, PAGE_INDEX_NAMES.get(p, ""), PAGE_INDEX_PURPOSE.get(p, "")]
                 for p, _f, _p in sitemap_pages() if p not in nav_hrefs]
    gviews = {v["id"]: v for v in GLOSSARY_VIEWS}
    views = []
    for href, name, purpose in PAGE_INDEX_VIEWS:
        if name is None:
            vid = href.split("#view=", 1)[1]
            name = f"{GLOSSARY_DISPLAY_NAME} · {gviews[vid]['label']}" if vid in gviews else ""
        views.append([href, name, purpose])
    return [
        {"title": "Modules", "sub": "every entry in the top bar", "rows": modules},
        {"title": "Reference pages", "sub": "reached from the footer, the homepage or a module",
         "rows": reference},
        {"title": "Views inside a module", "sub": "addresses that open one view of a module app",
         "rows": views},
        {"title": "Player cards", "sub": "per-player cards, addressable by URL",
         "rows": [list(r) for r in PAGE_INDEX_PLAYER_ROWS]},
    ]


def _page_index_data() -> str:
    """The Page Index rows as an inert JSON script the glossary client reads."""
    blob = json.dumps(page_index_groups(), ensure_ascii=False, separators=(",", ":"))
    # "</" would terminate the script element mid-blob; the JSON-safe escape keeps it inert.
    return ('<script type="application/json" id="page-index-data">'
            + blob.replace("</", "<\\/") + "</script>")


def build_library_redirect() -> str:
    """/library/ (owner ask 2026-10-02): the glossary module reads "Library",
    so its new name resolves. The page lives at /glossary/ for link stability;
    this stub is noindex, names /glossary/ as canonical, and carries the hash
    across (/library/#view=models opens /glossary/#view=models). It stays in
    deploy/publish_paths.txt: a redirect that does not ship is a 404."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{GLOSSARY_DISPLAY_NAME} - eephus.io</title>
{FAVICON_LINKS}
<meta name="robots" content="noindex">
<link rel="canonical" href="{SITE_ORIGIN}/glossary/">
<meta http-equiv="refresh" content="0; url=/glossary/">
<script>location.replace("/glossary/"+(location.hash||""));</script>
</head><body>
<p style="font-family:monospace;padding:2rem;">The {GLOSSARY_DISPLAY_NAME} lives at
<a href="/glossary/">/glossary/</a>.</p>
</body></html>
"""


def build_franchises_redirect() -> str:
    """/franchises/ -> /franchise/ (owner decision TEAM-1, 2026-10-02).

    The module's display name became "Franchises" while its key and URL stayed
    /franchise/, so the plural address a reader might type resolves too. A
    canonical, noindex stub (the shape of the retired /teams/ folder) that
    carries the incoming hash across, so /franchises/#team=NYY opens that
    club. It ships (deploy/publish_paths.txt) and stays out of the sitemap."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Franchises - eephus.io</title>
{FAVICON_LINKS}
<meta name="robots" content="noindex">
<link rel="canonical" href="{SITE_ORIGIN}/franchise/">
<meta http-equiv="refresh" content="0; url=/franchise/">
<script>location.replace("/franchise/"+(location.hash||""));</script>
</head><body>
<p style="font-family:monospace;padding:2rem;">Franchises lives at
<a href="/franchise/">/franchise/</a>.</p>
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
# /data/value_framework.js is the one /data/ payload a hand page loads by <script
# src>; /data/ is served with a 7-day max-age, so it is stamped like an asset
# (QPRP11) or a re-emitted $/WAR table can sit stale in a browser for a week.
_ASSET_URL_RE = re.compile(r'((?:href|src)=")(/assets/[^"?#]+|/data/value_framework\.js)(?:\?v=[^"#]*)?(#[^"]*)?(")')


def _restamp_html(text: str) -> str:
    """Return `text` with every /assets/ stylesheet href, script src and <use>
    href (and the /data/value_framework.js script src) stamped with the asset's
    current content hash, any #fragment kept.
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


# The nav lockup inside each hand-kept page's brand link: the retired vector
# mark, or a pixel lockup an earlier build wrote (so a regenerated fragment
# re-syncs). One line each, no nested <span class="nameplate">.
_HAND_NAV_LOCKUP_RE = re.compile(
    r'(<a class="eephus-wordmark" href="/" aria-label="eephus\.io home">)'
    r'(<span class="nameplate eephus-wordmark-merged">.*?eephus<span class="dot">\.io</span></span>'
    r'|<span class="nameplate eephus-wordmark-px">.*?<span class="wm-txt">eephus\.io</span></span>)'
    r'(</a>)')


def pixel_brand_hand_nav(text: str) -> str:
    """PB-03: the hand-kept nav lockup replaced by the generated s 2 pixel
    lockup, byte for byte what _nav() serves. Nothing else on the page moves."""
    return _HAND_NAV_LOCKUP_RE.sub(
        lambda m: m.group(1) + pixel_wordmark("nav", tag="span") + m.group(3), text, count=1)


# PB-07: each hand-kept page's og:image and twitter:image, today's default card
# or a card an earlier PIXEL_BRAND build wrote (so the sync is idempotent).
HAND_OG_CARD = {
    "prospx/index.html": "prospx",
    "collegesavant/index.html": "collegesavant",
    "collegesavant/pitcher_index.html": "collegesavant",
}
_HAND_OG_IMAGE_RE = re.compile(
    r'(<meta (?:property="og:image"|name="twitter:image") content=")'
    + re.escape(SITE_ORIGIN)
    + r'/assets/(?:share-default\.png|brand/share-default\.png|og/[a-z]+\.png)(")')


def pixel_brand_hand_og(text: str, rel: str) -> str:
    """PB-07: the hand-kept page's og:image and twitter:image point at its
    module's card (assets/og/<key>.png). Nothing else on the page moves."""
    url = f"{SITE_ORIGIN}/assets/og/{HAND_OG_CARD[rel]}.png"
    return _HAND_OG_IMAGE_RE.sub(lambda m: m.group(1) + url + m.group(2), text)


def restamp_hand_authored_pages() -> None:
    """Stamp every /assets/ stylesheet, script and <use> ref in the
    hand-authored pages with the asset's current content hash (_restamp_html),
    and sync the nav lockup to the pixel lockup _nav() serves. With PIXEL_BRAND
    on, the og:image and twitter:image are synced to the page's module card too."""
    for rel in HAND_AUTHORED_PAGES:
        path = ROOT / rel
        if not path.exists():
            print(f"  skipped {rel} (absent)")
            continue
        original = path.read_text(encoding="utf-8")
        stamped = _ensure_font_preload(pixel_brand_hand_nav(_restamp_html(original)))
        if PIXEL_BRAND:
            stamped = pixel_brand_hand_og(stamped, rel)
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
    write_glossary_index()

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
    # Diamond section (2026-08-05). Three public pages; the gate flag is off.
    # /dynasty/, /redraft/ and /dfs/ forward through 404.html (RETIRED_ROUTES).
    _write("betting/index.html", build_betting())
    _write("diamond/index.html", build_diamond())
    _write("parks/index.html", build_parks())
    _write("hof/index.html", build_hof())
    write_awards_page()
    _write("management/index.html", build_management())
    _write("franchise/index.html", build_franchise())
    _write("franchises/index.html", build_franchises_redirect())
    _write("ledger/index.html", build_ledger())
    # /scores/ ships behind scores_core.SCORES_LIVE: the published page from
    # the flip (SCORES_5a), the preview copy only while it is False (SCORES_3).
    import scores_core
    if scores_core.SCORES_LIVE:
        _write("scores/index.html", build_scores())
    else:
        write_scores_page()
    _write("models/index.html", build_models())
    _write("models/updates/index.html", build_model_updates())
    _write("glossary/index.html", build_glossary())
    _write("library/index.html", build_library_redirect())
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
